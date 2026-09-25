#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FASE 13: tap simple estilo raton + FASE11C-ROUTE (click fiable + ruteo a popups).

El backend Android upstream emite eventos TOUCH puros (GDK_TOUCH_BEGIN/END)
para AINPUT_SOURCE_TOUCHSCREEN. Los widgets GTK (GtkButton, GtkMenuButton,
GtkPopoverMenuBar, GtkRange, GtkToggleToolButton, etc.) escuchan eventos
BUTTON/PRESS/RELEASE (puntero), no TOUCH. Por eso el enfoque de Blender/FASE10
emula el dedo como raton.

FASE 10 emitia press en DOWN y release en posicion final -> micro-jitter del
dedo real hacia que GTK viera "press en A, release en B" -> lo trataba como
drag -> taps fisicos NO abrian menus ni botones (solo adb funcionaba).

FASE 12 diferia el press hasta UP -> click limpio en aterrizaje, pero el
press+release instantaneo (mismo timestamp, misma iteracion main loop) dejaba
widgets en estado armado (scrollbar "sostenida", tools que no clickeaban).

FASE 13: modelo simple y robusto (estilo raton con correccion de slop en el
release SOLO para taps) + FASE11C-ROUTE (ruteo determinista a popups):
  * DOWN -> BUTTON_PRESS INMEDIATO en el punto de aterrizaje (arma el widget).
    Target = popup bajo el dedo (geometria popup_bounds) o toplevel.
    Target pegajoso durante todo el gesto (drag que sale del popup no salta).
  * MOVE -> MOTION siguiendo al dedo (drag/scroll genuino).
  * UP   -> BUTTON_RELEASE en el punto de aterrizaje si jitter < slop (tap),
            o en posicion actual si jitter >= slop (drag).
            Coordenadas convertidas al espacio del target (toplevel o popup).
  * Sin long-press, sin double-click, sin tracking por pointer-id,
    sin deferral del press. Solo click fiable + popups que no se cierran.

El slop (~12 css px) filtra el micro-jitter del dedo: si el dedo se movio
menos del slop entre DOWN y UP, forzamos el release en las coordenadas del
press -> GTK ve "press y release en el mismo sitio" -> click limpio.
Si se movio mas, es un drag genuino y el release va donde esta el dedo.

Uso (desde build.sh):
  python3 "$ROOT/patches/gtk4-touch-as-pointer.py" "$src"
Donde $src es el arbol fuente de gtk descargado por fetch()/extract() (4.22.5).
Este parche SUSTITUYE a gtk4-touch-slop.py (FASE 10B) y a gtk4-touch-as-pointer.py
FASE 12.x: el slop queda integrado en la logica de tap/drag.
NO aplicar gtk4-touch-slop.py despues.
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
    "      /* FASE13: el dedo primario emula raton (lineage FASE10/12),",
    "       * click fiable: press en DOWN, release en UP con correccion de",
    "       * slop para taps. FASE11C-ROUTE: ruteo determinista a popups",
    "       * (geometria popup_bounds sincrona + target pegajoso). */",
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
    "          static gboolean f13_down = FALSE;",
    "          static gdouble f13_down_x = 0.0, f13_down_y = 0.0;",
    "          static GdkAndroidSurface *f13_target = NULL;",
    "          static GdkAndroidSurface *f13_drag_surface = NULL;",
    "",
    "          switch (masked_action)",
    "            {",
    "            case AMOTION_EVENT_ACTION_DOWN:",
    "              {",
    "                if (f13_down)",
    "                  break; /* ya hay un gesto activo, ignoramos nuevo DOWN */",
    "                f13_down = TRUE;",
    "                f13_down_x = x;",
    "                f13_down_y = y;",
    "",
    "                /* FASE11C-ROUTE: pick por geometria en DOWN (pegajoso). */",
    "                GdkAndroidSurface *target = gdk_android_surface_pick_child (toplevel, toplevel, x, y, 0.0f, 0.0f, 0);",
    "                if (target == NULL)",
    "                  target = toplevel;",
    "                if (target != toplevel && !GDK_IS_ANDROID_POPUP (target))",
    "                  target = toplevel;",
    "                f13_target = target;",
    "                f13_drag_surface = target;",
    "                g_object_ref (f13_target);",
    "",
    "                gfloat pcx = 0.0f, pcy = 0.0f;",
    "                if (target != toplevel)",
    "                  gdk_android_surface_popup_offset (target, toplevel, &pcx, &pcy);",
    "                g_debug (\"FASE13-DOWN target=%p [%s] ev=%.0f,%.0f\",",
    "                         f13_target, G_OBJECT_TYPE_NAME (f13_target), x - pcx, y - pcy);",
    "                guint32 state = dev_impl->button_state | AMOTION_EVENT_BUTTON_PRIMARY;",
    "                gdk_android_events_emit_button_press (AMOTION_EVENT_BUTTON_PRIMARY, state,",
    "                                                      GDK_BUTTON_PRIMARY,",
    "                                                      f13_target, event, dev,",
    "                                                      time, mods, x - pcx, y - pcy);",
    "                dev_impl->button_state = state;",
    "                gdk_android_device_maybe_update_surface ((GdkAndroidDevice *) dev, f13_target, mods, time, x - pcx, y - pcy);",
    "              }",
    "              break;",
    "            case AMOTION_EVENT_ACTION_MOVE:",
    "              {",
    "                if (!f13_down)",
    "                  break;",
    "                /* FASE11C-ROUTE: target pegajoso (fijado en DOWN). */",
    "                GdkAndroidSurface *target = f13_drag_surface;",
    "                if (target != toplevel && !GDK_IS_ANDROID_POPUP (target))",
    "                  target = toplevel;",
    "",
    "                gfloat pcx = 0.0f, pcy = 0.0f;",
    "                if (target != toplevel)",
    "                  gdk_android_surface_popup_offset (target, toplevel, &pcx, &pcy);",
    "                GdkDeviceTool *tool = gdk_android_seat_get_device_tool (display->seat, AMotionEvent_getToolType (event, 0));",
    "                GdkEvent *ev = gdk_motion_event_new ((GdkSurface *) target, dev, tool,",
    "                                                     time, mods, x - pcx, y - pcy,",
    "                                                     gdk_android_seat_create_axes_from_motion_event (event, 0));",
    "                gdk_android_seat_consume_event ((GdkDisplay *) display, ev);",
    "                gdk_android_device_maybe_update_surface ((GdkAndroidDevice *) dev, target, mods, time, x - pcx, y - pcy);",
    "              }",
    "              break;",
    "            case AMOTION_EVENT_ACTION_UP:",
    "            case AMOTION_EVENT_ACTION_CANCEL:",
    "              {",
    "                if (!f13_down)",
    "                  break;",
    "                /* FASE11C-ROUTE: target pegajoso. */",
    "                GdkAndroidSurface *target = f13_drag_surface;",
    "                if (target != toplevel && !GDK_IS_ANDROID_POPUP (target))",
    "                  target = toplevel;",
    "",
    "                gfloat pcx = 0.0f, pcy = 0.0f;",
    "                if (target != toplevel)",
    "                  gdk_android_surface_popup_offset (target, toplevel, &pcx, &pcy);",
    "                /* slop ~12 css px para distinguir tap de drag */",
    "                #define F13_SLOP 12.0",
    "                gdouble dx = x - f13_down_x;",
    "                gdouble dy = y - f13_down_y;",
    "                gboolean is_tap = (dx * dx + dy * dy) <= (F13_SLOP * F13_SLOP);",
    "                gfloat rel_x = is_tap ? f13_down_x : x;",
    "                gfloat rel_y = is_tap ? f13_down_y : y;",
    "                guint32 up_state = dev_impl->button_state & ~AMOTION_EVENT_BUTTON_PRIMARY;",
    "                g_debug (\"FASE13-UP target=%p [%s] ev=%.0f,%.0f rel=%.0f,%.0f tap=%d\",",
    "                         target, G_OBJECT_TYPE_NAME (target),",
    "                         x - pcx, y - pcy, rel_x - pcx, rel_y - pcy, is_tap);",
    "                gdk_android_events_emit_button_press (AMOTION_EVENT_BUTTON_PRIMARY, up_state,",
    "                                                      GDK_BUTTON_PRIMARY,",
    "                                                      target, event, dev,",
    "                                                      time, mods, rel_x - pcx, rel_y - pcy);",
    "                dev_impl->button_state = up_state;",
    "                gdk_android_device_maybe_update_surface ((GdkAndroidDevice *) dev, target, mods, time, rel_x - pcx, rel_y - pcy);",
    "                f13_down = FALSE;",
    "                g_clear_object (&f13_target);",
    "                f13_drag_surface = NULL;",
    "              }",
    "              break;",
    "            case AMOTION_EVENT_ACTION_POINTER_DOWN:",
    "            case AMOTION_EVENT_ACTION_POINTER_UP:",
    "              /* Ignoramos dedos adicionales (reservado pinch/pan futuro) */",
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
 *    que cerraba los menus al tocar un item justo tras abrirlos).
 *    Fallback a cfg (Java side) si popup_bounds es 0 (present() no corrio
 *    o race). cfg está en device pixels; se convierte a CSS del toplevel.
 *    NULL si no hay ningun popup bajo el dedo.
 * 3) g_touch_drag_surface (aqui f13_drag_surface): target pegajoso del gesto
 *    (fijado en el DOWN) para que un drag que se salga del rect del popover
 *    no salte al canvas.
 *
 * FASE13-TOUCH: click estilo raton con correccion de slop en release. */

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
                                gfloat             ry,
                                guint              depth)
{
  if (depth > 8)
    {
      g_critical ("FASE11C-PICK: profundidad excesiva (%u) en %p [%s]",
                  depth, node, G_OBJECT_TYPE_NAME (node));
      return NULL;
    }

  g_debug ("FASE11C-PICK [%s] %p children=%u xy=%.0f,%.0f",
           G_OBJECT_TYPE_NAME (node), node,
           g_list_length (GDK_SURFACE (node)->children), x, y);

  for (GList *l = GDK_SURFACE (node)->children; l != NULL; l = l->next)
    {
      GdkAndroidSurface *child = l->data;

      /* Defensa anti-dangling: solo popups vivos y cuyo parent sea node.
       * NO filtramos por child->visible: un popup en la lista children con
       * bounds válidos (popup_bounds o cfg) DEBE ser pickeable aunque
       * visible=FALSE por race (present() corrió pero layout async pendiente). */
      if (child == NULL || !GDK_IS_ANDROID_POPUP (child))
        continue;
      if (GDK_SURFACE (child)->parent != (GdkSurface *) node)
        continue;
      /* if (!child->visible) continue;  <- race: click llega antes de visible=TRUE */

      GdkAndroidPopup *popup = GDK_ANDROID_POPUP (child);

      /* popup_bounds (calculado en present() sincrono) es la fuente primaria.
       * Si es 0 (present() no corrio aun o race), fallback a cfg (Java side),
       * convertido con scale del toplevel (ya validado > 0). */
      gfloat cx, cy, cw, ch;
      if (popup->popup_bounds.width > 0 && popup->popup_bounds.height > 0)
        {
          cx = rx + popup->popup_bounds.x;
          cy = ry + popup->popup_bounds.y;
          cw = popup->popup_bounds.width;
          ch = popup->popup_bounds.height;
        }
      else
        {
          /* Fallback: cfg del popup (actualizado por Java en on_layout async).
           * cfg está en device pixels; convertimos a CSS del toplevel. */
          GdkAndroidSurface *child_impl = (GdkAndroidSurface *) child;
          if (child_impl->cfg.width <= 0 || child_impl->cfg.height <= 0)
            continue;
          gfloat parent_scale = ((GdkAndroidSurface *) toplevel)->cfg.scale;
          if (parent_scale <= 0.0f)
            continue;
          cx = rx + child_impl->cfg.x / parent_scale;
          cy = ry + child_impl->cfg.y / parent_scale;
          cw = child_impl->cfg.width / parent_scale;
          ch = child_impl->cfg.height / parent_scale;
        }

      g_debug ("FASE11C-PICK  cand=%p [%s] vis=%d rect=%.0f,%.0f %.0fx%.0f",
               child, G_OBJECT_TYPE_NAME (child), child->visible, cx, cy, cw, ch);

      if (cw <= 0.0f || ch <= 0.0f)
        continue;

      if (x >= cx && x < cx + cw && y >= cy && y < cy + ch)
        {
          GdkAndroidSurface *inner = gdk_android_surface_pick_child (toplevel, child, x, y, cx, cy, depth + 1);
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
    if "FASE13" in src:
        print("ERROR: parche FASE13 ya aplicado", file=sys.stderr)
        return 1

    src = src.replace(old, "\n".join(NEW))

    # FASE11C-ROUTE: insertar los helpers antes de la definicion del handler.
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
        "FASE13-DOWN",
        "FASE13-UP",
        "FASE11C-ROUTE",
        "f13_down",
        "f13_down_x",
        "f13_target",
        "f13_drag_surface",
        "g_object_ref",
        "g_clear_object",
        "F13_SLOP",
        "AMOTION_EVENT_ACTION_POINTER_DOWN",
        "gdk_android_surface_pick_child",
        "gdk_android_surface_popup_offset",
        "gdkandroidpopup-private.h",
    ]
    for m in markers:
        if m not in src:
            print("ERROR: marker '%s' no presente tras el parche" % m, file=sys.stderr)
            return 1
    if "gdk_touch_event_new" in src:
        print("ERROR: gdk_touch_event_new sigue presente", file=sys.stderr)
        return 1

    with open(path, "w") as fh:
        fh.write(src)
    print("gtk4: FASE13 tap simple + FASE11C-ROUTE aplicado en %s" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main())