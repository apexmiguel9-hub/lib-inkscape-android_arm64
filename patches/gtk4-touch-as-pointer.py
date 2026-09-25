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
cursor: se elige por geometria el popup visible (child del toplevel) que
contiene el punto, y el evento se emite sobre ESE surface con las coords
traducidas a su espacio (x - cfg.x/scale, y - cfg.y/scale). Sin popup bajo el
dedo, target = toplevel (comportamiento identico al previo).

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
    "       * FASE11B-ROUTE: el target del evento es el surface bajo el dedo (popup",
    "       * visible si lo hay segun geometria, si no el toplevel) y las coords se",
    "       * traducen al espacio de ese surface (x - cfg.x/scale). */",
    "      (void) event_identifier;",
    "",
    "      size_t pointers = AMotionEvent_getPointerCount (event);",
    "      if (pointers > 0)",
    "        {",
    "          gfloat x = AMotionEvent_getX (event, 0) / surface->cfg.scale;",
    "          gfloat y = AMotionEvent_getY (event, 0) / surface->cfg.scale;",
    "",
    "          /* FASE11B-ROUTE: Android entrega SIEMPRE el toque al view del toplevel;",
    "           * sin este ruteo un popover abierto (menu PopoverMenuBar, popover de",
    "           * color) jamas recibe el click: GTK lo ve como press 'fuera' y lo",
    "           * descarta (el menu se cierra al tocar un item). Elegimos por geometria",
    "           * el popup visible bajo el dedo; target = toplevel si no hay ninguno. */",
    "          GdkAndroidSurface *target = gdk_android_surface_pick_child (surface, x, y);",
    "",
    "          switch (masked_action)",
    "            {",
    "            case AMOTION_EVENT_ACTION_DOWN:",
    "              {",
    "                guint32 state = dev_impl->button_state | AMOTION_EVENT_BUTTON_PRIMARY;",
    "                gfloat pcx = target == surface ? 0 : target->cfg.x / target->cfg.scale;",
    "                gfloat pcy = target == surface ? 0 : target->cfg.y / target->cfg.scale;",
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
    "                gfloat pcx = target == surface ? 0 : target->cfg.x / target->cfg.scale;",
    "                gfloat pcy = target == surface ? 0 : target->cfg.y / target->cfg.scale;",
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
    "                gfloat pcx = target == surface ? 0 : target->cfg.x / target->cfg.scale;",
    "                gfloat pcy = target == surface ? 0 : target->cfg.y / target->cfg.scale;",
    "                if (GDK_ANDROID_EVENTS_BUTTON_IS_DIFFERENT (state, dev_impl->button_state, AMOTION_EVENT_BUTTON_PRIMARY))",
    "                  gdk_android_events_emit_button_press (AMOTION_EVENT_BUTTON_PRIMARY, state,",
    "                                                        GDK_BUTTON_PRIMARY,",
    "                                                        target, event, dev,",
    "                                                        time, mods,",
    "                                                        x - pcx, y - pcy);",
    "                dev_impl->button_state = state;",
    "                gdk_android_device_maybe_update_surface ((GdkAndroidDevice *) dev, target, mods, time, x - pcx, y - pcy);",
    "              }",
    "              break;",
    "            default:",
    "              break;",
    "            }",
    "        }",
    "    }",
]

# FASE11B-ROUTE: helper de pick por geometria (popup visible bajo el dedo).
# Se inserta ANTES de gdk_android_events_handle_motion_event (ancla unica:
# la firma solo existe una vez en gdkandroidevents.c; el prototipo vive en
# gdkandroidevents-private.h con otro formato).
HELPER = """/* FASE11B-ROUTE: surface bajo el dedo para el puntero sintetico.
 * children de un toplevel = sus popups (g_list_prepend => el mas reciente /
 * topmost queda primero). cfg.x/y/width/height son px del view (layout de
 * Java); /scale => coords CSS del toplevel, el mismo espacio que las coords
 * de AMotionEvent. Devuelve el popup visible cuyo rect CSS contiene (x, y);
 * si no hay ninguno, el propio toplevel (comportamiento identico al previo). */
static GdkAndroidSurface *
gdk_android_surface_pick_child (GdkAndroidSurface *toplevel,
                                gfloat             x,
                                gfloat             y)
{
  GdkSurface *parent_surface = (GdkSurface *) toplevel;

  for (GList *l = parent_surface->children; l != NULL; l = l->next)
    {
      GdkAndroidSurface *child = l->data;
      if (!child->visible)
        continue;
      gfloat cx = child->cfg.x / child->cfg.scale;
      gfloat cy = child->cfg.y / child->cfg.scale;
      gfloat cw = child->cfg.width / child->cfg.scale;
      gfloat ch = child->cfg.height / child->cfg.scale;
      if (x >= cx && x < cx + cw && y >= cy && y < cy + ch)
        return child;
    }
  return toplevel;
}"""


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

    # FASE11B-ROUTE: insertar el helper antes de la definicion del handler.
    # El ancla incluye la linea 'void' (tipo de retorno) para no dejar un 'void'
    # colgante antes del helper.
    helper_anchor = "void\ngdk_android_events_handle_motion_event (GdkAndroidSurface *surface,"
    h = src.count(helper_anchor)
    if h != 1:
        print("ERROR: ancla del handler encontrada %d veces (esperado 1); " % h +
              "re-auditar", file=sys.stderr)
        return 1
    src = src.replace(helper_anchor, HELPER + "\n\n" + helper_anchor)

    markers = [
        "FASE10-TOUCH-AS-POINTER",
        "FASE11B-ROUTE",
        "gdk_android_surface_pick_child",
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
    print("gtk4: dedo primario->puntero + FASE11B-ROUTE aplicado en %s" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main())