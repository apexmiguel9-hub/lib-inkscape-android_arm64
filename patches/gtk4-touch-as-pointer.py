#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FASE 13: tap simple estilo raton (click fiable con el dedo).

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
release SOLO para taps):
  * DOWN -> BUTTON_PRESS INMEDIATO en el punto de aterrizaje (arma el widget).
  * MOVE -> MOTION siguiendo al dedo (drag/scroll genuino).
  * UP   -> BUTTON_RELEASE en el punto de aterrizaje si jitter < slop (tap),
            o en posicion actual si jitter >= slop (drag).
  * Sin long-press, sin double-click, sin tracking por pointer-id,
    sin deferral del press. Solo click fiable.

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
    "       * slop para taps. El micro-jitter del dedo real (~10-20 px) no",
    "       * debe hacer que GTK vea un drag. Modelo: press arma el widget,",
    "       * motion sigue al dedo, release en aterrizaje si fue tap. */",
    "      (void) event_identifier;",
    "",
    "      size_t pointers = AMotionEvent_getPointerCount (event);",
    "      if (pointers > 0)",
    "        {",
    "          /* Coordenadas en CSS de la superficie receptora (toplevel o popup). */",
    "          gfloat x = AMotionEvent_getX (event, 0) / surface->cfg.scale;",
    "          gfloat y = AMotionEvent_getY (event, 0) / surface->cfg.scale;",
    "",
    "          static gboolean f13_down = FALSE;",
    "          static gdouble f13_down_x = 0.0, f13_down_y = 0.0;",
    "          static GdkAndroidSurface *f13_target = NULL;",
    "          static gboolean f13_emitted_press = FALSE;",
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
    "                f13_emitted_press = FALSE;",
    "                f13_target = surface;",
    "                g_object_ref (f13_target);",
    "",
    "                guint32 state = dev_impl->button_state | AMOTION_EVENT_BUTTON_PRIMARY;",
    "                g_debug (\"FASE13-DOWN target=%p [%s] ev=%.0f,%.0f\",",
    "                         f13_target, G_OBJECT_TYPE_NAME (f13_target), x, y);",
    "                gdk_android_events_emit_button_press (AMOTION_EVENT_BUTTON_PRIMARY, state,",
    "                                                      GDK_BUTTON_PRIMARY,",
    "                                                      f13_target, event, dev,",
    "                                                      time, mods, x, y);",
    "                dev_impl->button_state = state;",
    "                gdk_android_device_maybe_update_surface ((GdkAndroidDevice *) dev, f13_target, mods, time, x, y);",
    "              }",
    "              break;",
    "            case AMOTION_EVENT_ACTION_MOVE:",
    "              {",
    "                if (!f13_down)",
    "                  break;",
    "                GdkDeviceTool *tool = gdk_android_seat_get_device_tool (display->seat, AMotionEvent_getToolType (event, 0));",
    "                GdkEvent *ev = gdk_motion_event_new ((GdkSurface *) f13_target, dev, tool,",
    "                                                     time, mods, x, y,",
    "                                                     gdk_android_seat_create_axes_from_motion_event (event, 0));",
    "                gdk_android_seat_consume_event ((GdkDisplay *) display, ev);",
    "                gdk_android_device_maybe_update_surface ((GdkAndroidDevice *) dev, f13_target, mods, time, x, y);",
    "              }",
    "              break;",
    "            case AMOTION_EVENT_ACTION_UP:",
    "            case AMOTION_EVENT_ACTION_CANCEL:",
    "              {",
    "                if (!f13_down)",
    "                  break;",
    "                /* slop ~12 css px para distinguir tap de drag */",
    "                #define F13_SLOP 12.0",
    "                gdouble dx = x - f13_down_x;",
    "                gdouble dy = y - f13_down_y;",
    "                gboolean is_tap = (dx * dx + dy * dy) <= (F13_SLOP * F13_SLOP);",
    "                gfloat rel_x = is_tap ? f13_down_x : x;",
    "                gfloat rel_y = is_tap ? f13_down_y : y;",
    "                guint32 up_state = dev_impl->button_state & ~AMOTION_EVENT_BUTTON_PRIMARY;",
    "                g_debug (\"FASE13-UP target=%p [%s] ev=%.0f,%.0f rel=%.0f,%.0f tap=%d\",",
    "                         f13_target, G_OBJECT_TYPE_NAME (f13_target),",
    "                         x, y, rel_x, rel_y, is_tap);",
    "                gdk_android_events_emit_button_press (AMOTION_EVENT_BUTTON_PRIMARY, up_state,",
    "                                                      GDK_BUTTON_PRIMARY,",
    "                                                      f13_target, event, dev,",
    "                                                      time, mods, rel_x, rel_y);",
    "                dev_impl->button_state = up_state;",
    "                gdk_android_device_maybe_update_surface ((GdkAndroidDevice *) dev, f13_target, mods, time, rel_x, rel_y);",
    "                f13_down = FALSE;",
    "                g_clear_object (&f13_target);",
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

    markers = [
        "FASE13-DOWN",
        "FASE13-UP",
        "f13_down",
        "f13_down_x",
        "f13_target",
        "g_object_ref",
        "g_clear_object",
        "F13_SLOP",
        "AMOTION_EVENT_ACTION_POINTER_DOWN",
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
    print("gtk4: FASE13 tap simple estilo raton aplicado en %s" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main())