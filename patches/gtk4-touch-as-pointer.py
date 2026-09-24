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

Uso (desde build.sh):
  python3 "$ROOT/patches/gtk4-touch-as-pointer.py" "$src"
Donde $src es el arbol fuente de gtk descargado por fetch()/extract() (4.22.5).
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
    "       * Los dedos adicionales se ignoran (reservados para pinch/pan en FASE11). */",
    "      (void) event_identifier;",
    "",
    "      size_t pointers = AMotionEvent_getPointerCount (event);",
    "      if (pointers > 0)",
    "        {",
    "          gfloat x = AMotionEvent_getX (event, 0) / surface->cfg.scale;",
    "          gfloat y = AMotionEvent_getY (event, 0) / surface->cfg.scale;",
    "",
    "          switch (masked_action)",
    "            {",
    "            case AMOTION_EVENT_ACTION_DOWN:",
    "              {",
    "                guint32 state = dev_impl->button_state | AMOTION_EVENT_BUTTON_PRIMARY;",
    "                gdk_android_events_emit_button_press (AMOTION_EVENT_BUTTON_PRIMARY, state,",
    "                                                      GDK_BUTTON_PRIMARY,",
    "                                                      surface, event, dev,",
    "                                                      time, mods,",
    "                                                      x, y);",
    "                dev_impl->button_state = state;",
    "                gdk_android_device_maybe_update_surface ((GdkAndroidDevice *) dev, surface, mods, time, x, y);",
    "              }",
    "              break;",
    "            case AMOTION_EVENT_ACTION_MOVE:",
    "              {",
    "                GdkDeviceTool *tool = gdk_android_seat_get_device_tool (display->seat, AMOTION_EVENT_TOOL_TYPE_FINGER);",
    "                GdkEvent *ev = gdk_motion_event_new ((GdkSurface *) surface, dev, tool,",
    "                                                     time, mods,",
    "                                                     x, y,",
    "                                                     gdk_android_seat_create_axes_from_motion_event (event, 0));",
    "                gdk_android_seat_consume_event ((GdkDisplay *) display, ev);",
    "                gdk_android_device_maybe_update_surface ((GdkAndroidDevice *) dev, surface, mods, time, x, y);",
    "              }",
    "              break;",
    "            case AMOTION_EVENT_ACTION_UP:",
    "            case AMOTION_EVENT_ACTION_CANCEL:",
    "              {",
    "                guint32 state = dev_impl->button_state & ~AMOTION_EVENT_BUTTON_PRIMARY;",
    "                if (GDK_ANDROID_EVENTS_BUTTON_IS_DIFFERENT (state, dev_impl->button_state, AMOTION_EVENT_BUTTON_PRIMARY))",
    "                  gdk_android_events_emit_button_press (AMOTION_EVENT_BUTTON_PRIMARY, state,",
    "                                                        GDK_BUTTON_PRIMARY,",
    "                                                        surface, event, dev,",
    "                                                        time, mods,",
    "                                                        x, y);",
    "                dev_impl->button_state = state;",
    "                gdk_android_device_maybe_update_surface ((GdkAndroidDevice *) dev, surface, mods, time, x, y);",
    "              }",
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
    if "FASE10-TOUCH-AS-POINTER" in src:
        print("ERROR: parche FASE10 ya aplicado", file=sys.stderr)
        return 1

    src = src.replace(old, "\n".join(NEW))

    markers = [
        "FASE10-TOUCH-AS-POINTER",
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
    print("gtk4: dedo primario->puntero aplicado en %s" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main())