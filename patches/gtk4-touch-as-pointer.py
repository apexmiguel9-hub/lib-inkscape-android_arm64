#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FASE 10: dedo primario = puntero (touch -> mouse) en el backend android de GTK.

GTK4 ya NO sintetiza touch->mouse (GTK3/X11 lo hacia). Con GDK_TOUCH_* puro:
  * GtkGestureClick de los botones solo ve un touch, y el GestureDrag
    touch-only del GtkScrolledWindow captura la secuencia al minimo movimiento
    => no se pueden tocar tools/colores (solo "a veces desliza la barra").
  * el lienzo de inkscape solo responde a puntero => no se dibuja con el dedo.

Este parche emula el dedo PRIMARIO como puntero con boton izquierdo:
  * ACTION_DOWN   -> GDK_BUTTON_PRESS (boton 1)
  * ACTION_MOVE   -> GDK_MOTION (arrastra/dibuja)
  * ACTION_UP/CANCEL -> GDK_BUTTON_RELEASE (boton 1)
Los dedos adicionales (POINTER_DOWN/UP) caen en default y se ignoran, quedando
reservados para el pinch/pan de la FASE 11.

Los eventos usan exactamente las mismas helpers que la rama POINTER
(gdk_android_events_emit_button_press / gdk_motion_event_new), y actualizan
dev_impl->button_state para que los motion lleven GDK_BUTTON1_MASK mientras
arrastra (imprescindible para el canvas de inkscape).

FASE 11B-ROUTE: Android entrega SIEMPRE el toque al view del toplevel (sesion
DIAG g56 06:36: 55/55 presses -> GdkAndroidToplevel, 0 -> GdkAndroidPopup), asi
que un popover abierto jamas recibe el click y GTK lo descarta como press
"fuera" (el menu PopoverMenuBar se cierra al tocar un item; igual con los
popovers de color picker). Un compositor rutearia el puntero al surface bajo el
cursor: elegimos por geometria el popup visible (child del toplevel) que
contiene el punto y emitimos sobre ESE surface con coords traducidas.

FASE 11C-ROUTE (determinista; reemplaza la logica de 11B):
  * El hit-test de Android es INESTABLE: un toque dentro del rect del popup a
    veces llega al SurfaceView del popup (coords locales) y a veces al del
    toplevel (coords del toplevel), segun una carrera de z/visibilidad.
    Normalizamos las coords AMotionEvent al espacio CSS del TOPLEVEL: escalamos
    con el cfg.scale DEL TOPLEVEL (estable; el cfg del popup recien presentado
    es 0/1 hasta el primer layout) y sumamos el ORIGEN del surface receptor
    (popup_bounds acumulado via ancestros; 0 si el receptor es el toplevel).
  * El pick por geometria usa popup_bounds (SINCRONO: se fija en present()
    ANTES del layout async de Java) en vez de cfg (ASYNC: 0,0,0,0 hasta el
    primer on_layout -> la carrera que cerraba los menus en el primer tap
    rapido tras abrirlos).
  * Target PEGAJOSO por gesto: el DOWN fija la superficie y MOVE/UP se quedan
    en ella aunque el dedo salga del rect (un drag sobre el popover de color /
    slider no salta al canvas y no arranca un select box).

Uso (desde build.sh):
  python3 "$ROOT/patches/gtk4-touch-as-pointer.py" "$src"
Donde $src es el arbol fuente de gtk descargado por fetch()/extract() (4.22.5).
Requiere gtk4-touch-slop.py aplicado DESPUES (sus anclas apuntan a este bloque;
las lineas-ancla DOWN/MOVE/UP se mantienen byte-identicas).
"""
import sys

SRC_REL = "gdk/android/gdkandroidevents.c"

OLD = [
    "  if (GDK_ANDROID_EVENTS_COMPARE_MASK (src, AINPUT_SOURCE_TOUCHSCREEN))",
    "    {",
    "      // I think it might be better to drop the down time and only rely on the event identity",
    "      guint base_sequence = gdk_android_surface_long_hash ((guint64) AMotionEvent_getDownTime (event));",
    "      base_sequence ^= (guint) event_identifier;",
    "",
    "      size_t pointers = AMotionEvent_getPointerCount (event);",
    "      for (size_t i = 0; i < pointers; i++)",
    "        {",
    "          GdkEventType ev_type = gdk_android_events_touch_action_to_gdk (event, i);",
    "",
    "          guint sequence = base_sequence ^ gdk_android_events_int_hash(AMotionEvent_getPointerId (event, i));",
    "          gfloat x = AMotionEvent_getX (event, i) / surface->cfg.scale;",
    "          gfloat y = AMotionEvent_getY (event, i) / surface->cfg.scale;",
    "",
    "          GdkEvent *ev = gdk_touch_event_new (ev_type, GUINT_TO_POINTER (sequence), (GdkSurface *) surface,",
    "                                              display->seat->logical_touchscreen,",
    "                                              time, mods,",
    "                                              x, y,",
    "                                              gdk_android_seat_create_axes_from_motion_event (event, i), i == 0);",
    "          gdk_android_seat_consume_event ((GdkDisplay *) display, ev);",
    "        }",
    "    }",
]

NEW = [
    "  if (GDK_ANDROID_EVENTS_COMPARE_MASK (src, AINPUT_SOURCE_TOUCHSCREEN))",
    "    {",
    "      /* FASE10-TOUCH-AS-POINTER: GTK4 ya NO sintetiza touch->mouse (GTK3/X11 lo",
    "       * hacia). Con GDK_TOUCH_* puro, GtkGestureClick de los botones ve un touch",
    "       * y el GestureDrag touch-only del GtkScrolledWindow captura la secuencia",
    "       * al minimo movimiento => no se pueden tocar tools/colores ni dibujar en",
    "       * el lienzo (solo responde a puntero). Emulamos el dedo primario como",
    "       * puntero con boton izquierdo: tap = click, arrastre = drag (dibujar).",
    "       * Los dedos adicionales se ignoran (reservados para pinch/pan en FASE11).",
    "       *",
    "       * FASE11C-ROUTE: ruteo determinista del puntero sintetico (ver helpers",
    "       * abajo). El toque puede llegar en el view del toplevel o en el del",
    "       * popup (hit-test Android inestable); normalizamos las coords al espacio",
    "       * CSS del toplevel, elegimos por geometria el popup bajo el dedo con",
    "       * popup_bounds SINCRONO (nunca cfg, evita la carrera del primer tap) y",
    "       * fijamos el target del gesto en el DOWN (drag no salta al canvas). */",
    "      (void) event_identifier;",
    "",
    "      size_t pointers = AMotionEvent_getPointerCount (event);",
    "      if (pointers > 0)",
    "        {",
    "          /* FASE11C-ROUTE: superficie toplevel del receptor + origen (css) del",
    "           * receptor respecto a ese toplevel (0 si el receptor ES el toplevel). */",
    "          GdkAndroidSurface *toplevel = (GdkAndroidSurface *) gdk_android_surface_get_toplevel (surface);",
    "          gfloat recv_ox = 0.0f, recv_oy = 0.0f;",
    "          if (toplevel != surface)",
    "            gdk_android_surface_popup_offset (surface, toplevel, &recv_ox, &recv_oy);",
    "",
    "          /* coords en el espacio CSS del toplevel, scale del toplevel (estable). */",
    "          gfloat x = AMotionEvent_getX (event, 0) / toplevel->cfg.scale + recv_ox;",
    "          gfloat y = AMotionEvent_getY (event, 0) / toplevel->cfg.scale + recv_oy;",
    "",
    "          /* target del gesto: el DOWN lo fija (pegajoso para MOVE/UP); si no",
    "           * hay gesto activo se re-pickea por geometria. */",
    "          GdkAndroidSurface *target;",
    "          if (masked_action == AMOTION_EVENT_ACTION_DOWN)",
    "            {",
    "              target = gdk_android_surface_pick_child (toplevel, toplevel, x, y, 0.0f, 0.0f);",
    "              g_touch_drag_surface = target;",
    "            }",
    "          else if (g_touch_drag_surface != NULL)",
    "            {",
    "              target = g_touch_drag_surface;",
    "            }",
    "          else",
    "            {",
    "              target = gdk_android_surface_pick_child (toplevel, toplevel, x, y, 0.0f, 0.0f);",
    "            }",
    "",
    "          switch (masked_action)",
    "            {",
    "            case AMOTION_EVENT_ACTION_DOWN:",
    "              {",
    "                guint32 state = dev_impl->button_state | AMOTION_EVENT_BUTTON_PRIMARY;",
    "                gfloat pcx = 0.0f, pcy = 0.0f;",
    "                if (target != toplevel)",
    "                  gdk_android_surface_popup_offset (target, toplevel, &pcx, &pcy);",
    "                gdk_android_events_emit_button_press (AMOTION_EVENT_BUTTON_PRIMARY, state,",
    "                                                      GDK_BUTTON_PRIMARY,",
    "                                                      target, event, dev,",
    "                                                      time, mods,",
    "                                                      x - pcx, y - pcy);",
    "                dev_impl->button_state = state;",
    "                gdk_android_device_maybe_update_surface ((GdkAndroidDevice *) dev, target, mods, time, x - pcx, y - pcy);",
    "              }",
    "              break;",
    "            case AMOTION_EVENT_ACTION_MOVE:",
    "              {",
    "                GdkDeviceTool *tool = gdk_android_seat_get_device_tool (display->seat, AMOTION_EVENT_TOOL_TYPE_FINGER);",
    "                gfloat pcx = 0.0f, pcy = 0.0f;",
    "                if (target != toplevel)",
    "                  gdk_android_surface_popup_offset (target, toplevel, &pcx, &pcy);",
    "                GdkEvent *ev = gdk_motion_event_new ((GdkSurface *) target, dev, tool,",
    "                                                     time, mods,",
    "                                                     x - pcx, y - pcy,",
    "                                                     gdk_android_seat_create_axes_from_motion_event (event, 0));",
    "                gdk_android_seat_consume_event ((GdkDisplay *) display, ev);",
    "                gdk_android_device_maybe_update_surface ((GdkAndroidDevice *) dev, target, mods, time, x - pcx, y - pcy);",
    "              }",
    "              break;",
    "            case AMOTION_EVENT_ACTION_UP:",
    "            case AMOTION_EVENT_ACTION_CANCEL:",
    "              {",
    "                guint32 state = dev_impl->button_state & ~AMOTION_EVENT_BUTTON_PRIMARY;",
    "                gfloat pcx = 0.0f, pcy = 0.0f;",
    "                if (target != toplevel)",
    "                  gdk_android_surface_popup_offset (target, toplevel, &pcx, &pcy);",
    "                if (GDK_ANDROID_EVENTS_BUTTON_IS_DIFFERENT (state, dev_impl->button_state, AMOTION_EVENT_BUTTON_PRIMARY))",
    "                  gdk_android_events_emit_button_press (AMOTION_EVENT_BUTTON_PRIMARY, state,",
    "                                                        GDK_BUTTON_PRIMARY,",
    "                                                        target, event, dev,",
    "                                                        time, mods,",
    "                                                        x - pcx, y - pcy);",
    "                dev_impl->button_state = state;",
    "                g_touch_drag_surface = NULL;",
    "                gdk_android_device_maybe_update_surface ((GdkAndroidDevice *) dev, target, mods, time, x - pcx, y - pcy);",
    "              }",
    "              break;",
    "            default:",
    "              break;",
    "            }",
    "        }",
    "    }",
]

# FASE11C-ROUTE: helpers de ruteo del puntero sintetico (ver docstring).
# Se insertan ANTES de gdk_android_events_handle_motion_event (ancla unica:
# la firma solo existe una vez en gdkandroidevents.c).
HELPER = """/* FASE11C-ROUTE: helpers de ruteo del puntero sintetico (dedo primario).
 *
 * 1) gdk_android_surface_popup_offset: origen CSS de un surface respecto al
 *    toplevel. Un GdkAndroidPopup cuyo padre NO es el toplevel queda anidado:
 *    su popup_bounds esta en el espacio de SU padre, asi que se suman los
 *    popup_bounds de si mismo y de cada ancestro. El toplevel -> (0, 0).
 * 2) gdk_android_surface_pick_child: popup visible cuyo rect CSS (basado en
 *    popup_bounds, NUNCA en cfg) contiene el punto, en coords CSS del
 *    toplevel. children usa g_list_prepend => el mas reciente/topmost queda
 *    primero; se recursa primero en los hijos (vienen encima del padre).
 *    popup_bounds se fija en present() de forma SINCRONA, antes del layout
 *    async de Java (cfg seria 0,0,0,0 hasta el primer on_layout => la carrera
 *    que cerraba los menus al tocar un item justo tras abrirlos). NULL si no
 *    hay ningun popup bajo el dedo.
 * 3) g_touch_drag_surface: target pegajoso del gesto (fijado en el DOWN) para
 *    que un drag que se salga del rect del popover no salte al canvas. */

static GdkAndroidSurface *g_touch_drag_surface = NULL;

static void
gdk_android_surface_popup_offset (GdkAndroidSurface *surface,
                                  GdkAndroidSurface *toplevel,
                                  gfloat           *ox,
                                  gfloat           *oy)
{
  gfloat x = 0.0f, y = 0.0f;

  for (GdkAndroidSurface *s = surface; s != toplevel && s != NULL; s = (GdkAndroidSurface *) GDK_SURFACE (s)->parent)
    {
      GdkAndroidPopup *popup = GDK_ANDROID_POPUP (s);
      x += popup->popup_bounds.x;
      y += popup->popup_bounds.y;
    }

  *ox = x;
  *oy = y;
}

static GdkAndroidSurface *
gdk_android_surface_pick_child (GdkAndroidSurface *toplevel,
                                GdkAndroidSurface *node,
                                gfloat             x,
                                gfloat             y,
                                gfloat             rx,
                                gfloat             ry)
{
  for (GList *l = GDK_SURFACE (node)->children; l != NULL; l = l->next)
    {
      GdkAndroidSurface *child = l->data;
      if (!child->visible)
        continue;

      GdkAndroidPopup *popup = GDK_ANDROID_POPUP (child);
      gfloat cx = rx + popup->popup_bounds.x;
      gfloat cy = ry + popup->popup_bounds.y;
      gfloat cw = popup->popup_bounds.width;
      gfloat ch = popup->popup_bounds.height;

      if (cw <= 0.0f || ch <= 0.0f)
        continue;

      if (x >= cx && x < cx + cw && y >= cy && y < cy + ch)
        {
          GdkAndroidSurface *inner = gdk_android_surface_pick_child (toplevel, child, x, y, cx, cy);
          if (inner != NULL)
            return inner;
          return child;
        }
    }

  return NULL;
}"""

# FASE11C-ROUTE: include necesario para GdkAndroidPopup / popup_bounds /
# gdk_android_surface_get_toplevel (gdkandroidpopup-private.h trae tambien
# gdkandroidsurface-private.h, que declara ese prototype).
INCLUDE_OLD = '#include "gdkandroidevents-private.h"\n'
INCLUDE_NEW = ('#include "gdkandroidevents-private.h"\n'
               '#include "gdkandroidpopup-private.h"\n')


def main() -> int:
    if len(sys.argv) != 2:
        print("uso: gtk4-touch-as-pointer.py <srcdir-gtk>", file=sys.stderr)
        return 2
    path = sys.argv[1].rstrip("/") + "/" + SRC_REL
    with open(path, "r") as fh:
        src = fh.read()

    old = "\n".join(OLD)
    n = src.count(old)
    if n != 1:
        print("ERROR: bloque TOUCHSCREEN encontrado %d veces (esperado 1); " % n +
              "cambio upstream en 4.22.5; re-auditar", file=sys.stderr)
        return 1
    if "FASE10-TOUCH-AS-POINTER" in src:
        print("ERROR: parche FASE10 ya aplicado", file=sys.stderr)
        return 1

    src = src.replace(old, "\n".join(NEW))

    # FASE11C-ROUTE: insertar los helpers antes de la definicion del handler.
    # El ancla incluye la linea 'void' (tipo de retorno) para no dejar un 'void'
    # colgante antes de los helpers.
    helper_anchor = "void\ngdk_android_events_handle_motion_event (GdkAndroidSurface *surface,"
    h = src.count(helper_anchor)
    if h != 1:
        print("ERROR: ancla del handler encontrada %d veces (esperado 1); " % h +
              "re-auditar", file=sys.stderr)
        return 1
    src = src.replace(helper_anchor, HELPER + "\n\n" + helper_anchor)

    # FASE11C-ROUTE: include del popup-private (unica aparicion en este .c).
    i = src.count(INCLUDE_OLD)
    if i != 1:
        print("ERROR: include gdkandroidevents-private.h encontrado %d veces " % i +
              "(esperado 1); re-auditar", file=sys.stderr)
        return 1
    src = src.replace(INCLUDE_OLD, INCLUDE_NEW)

    markers = [
        "FASE10-TOUCH-AS-POINTER",
        "FASE11C-ROUTE",
        "gdk_android_surface_pick_child",
        "gdk_android_surface_popup_offset",
        "g_touch_drag_surface",
        "gdkandroidpopup-private.h",
        "AMOTION_EVENT_TOOL_TYPE_FINGER",
        "gdk_motion_event_new",
        "case AMOTION_EVENT_ACTION_DOWN:",
        "case AMOTION_EVENT_ACTION_CANCEL:",
    ]
    for m in markers:
        if m not in src:
            print("ERROR: marker '%s' no presente tras el parche" % m, file=sys.stderr)
            return 1
    # el loop de touch OLD debe haber desaparecido
    if "gdk_touch_event_new" in src:
        print("ERROR: gdk_touch_event_new sigue presente", file=sys.stderr)
        return 1

    with open(path, "w") as fh:
        fh.write(src)
    print("gtk4: dedo primario->puntero + FASE11C-ROUTE aplicado en %s" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main())