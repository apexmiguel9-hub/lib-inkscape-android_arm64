#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FASE 10B: touch slop en la emulacion dedo->puntero (gdk android).

FASE 10 emula el dedo primario como raton; pero sin tolerancia, el minimo
temblor del dedo (jitter) al tocar produce MOVE de 1-2 px que:
  * cancelaba clicks "sloppy" de GtkButton (press y release en sitios
    ligeramente distintos -> "a veces hay que darle 2 veces"),
  * arrancaba rubber-bands/select-boxes accidentales al tocar el lienzo.

Fix estilo Android (ViewConfiguration.getScaledTouchSlop ~= 8dp):
mientras el dedo no supere ~8 css px de distancia al punto de press, los
eventos MOTION se emiten ANCLADOS al punto de press (el widget ve un toque
quieto -> tap=click fiable); al superar el slop el dedo empieza a seguir la
posicion real (drag/dibujo genuino).

Uso: python3 gtk4-touch-slop.py <srcdir-gtk>   (requiere FASE 10 aplicada)
"""
import sys

SRC_REL = "gdk/android/gdkandroidevents.c"

EDITS = [
    # 1) estado del slop + defines (ancla: macro COMPARE_MASK)
    (
        "#define GDK_ANDROID_EVENTS_COMPARE_MASK(val, mask) \\\n"
        "  (((val) & (mask)) == (mask))\n",
        "#define GDK_ANDROID_EVENTS_COMPARE_MASK(val, mask) \\\n"
        "  (((val) & (mask)) == (mask))\n"
        "\n"
        "/* FASE10B-SLOP: tolerancia de temblor del dedo en la emulacion\n"
        " * touch->puntero. ~8 css px (~8dp Android). Mientras no se supere,\n"
        " * los MOTION se anclan al punto de press (tap fiable sin jitter). */\n"
        "#define FASE10B_SLOP 8.0\n"
        "#define FASE10B_SLOP_SQ (FASE10B_SLOP * FASE10B_SLOP)\n"
        "static struct {\n"
        "    gdouble press_x;\n"
        "    gdouble press_y;\n"
        "    gboolean active;\n"
        "} g_touch_slop = {0.0, 0.0, FALSE};\n",
    ),
    # 2) DOWN: registrar el punto de press
    (
        "            case AMOTION_EVENT_ACTION_DOWN:\n"
        "              {\n"
        "                guint32 state = dev_impl->button_state | AMOTION_EVENT_BUTTON_PRIMARY;\n",
        "            case AMOTION_EVENT_ACTION_DOWN:\n"
        "              {\n"
        "                g_touch_slop.press_x = x;\n"
        "                g_touch_slop.press_y = y;\n"
        "                g_touch_slop.active = TRUE;\n"
        "                guint32 state = dev_impl->button_state | AMOTION_EVENT_BUTTON_PRIMARY;\n",
    ),
    # 3) MOVE: anclar al punto de press hasta superar el slop
    (
        "            case AMOTION_EVENT_ACTION_MOVE:\n"
        "              {\n"
        "                GdkDeviceTool *tool = gdk_android_seat_get_device_tool (display->seat, AMOTION_EVENT_TOOL_TYPE_FINGER);\n",
        "            case AMOTION_EVENT_ACTION_MOVE:\n"
        "              {\n"
        "                if (g_touch_slop.active) {\n"
        "                    gdouble _dx = x - g_touch_slop.press_x;\n"
        "                    gdouble _dy = y - g_touch_slop.press_y;\n"
        "                    if (_dx * _dx + _dy * _dy > FASE10B_SLOP_SQ) {\n"
        "                        g_touch_slop.active = FALSE; /* drag real: sigue al dedo */\n"
        "                    } else {\n"
        "                        x = g_touch_slop.press_x; /* jitter: toque quieto */\n"
        "                        y = g_touch_slop.press_y;\n"
        "                    }\n"
        "                }\n"
        "                GdkDeviceTool *tool = gdk_android_seat_get_device_tool (display->seat, AMOTION_EVENT_TOOL_TYPE_FINGER);\n",
    ),
    # 4) UP/CANCEL: limpiar el estado del slop
    (
        "            case AMOTION_EVENT_ACTION_UP:\n"
        "            case AMOTION_EVENT_ACTION_CANCEL:\n"
        "              {\n"
        "                guint32 state = dev_impl->button_state & ~AMOTION_EVENT_BUTTON_PRIMARY;\n",
        "            case AMOTION_EVENT_ACTION_UP:\n"
        "            case AMOTION_EVENT_ACTION_CANCEL:\n"
        "              {\n"
        "                g_touch_slop.active = FALSE;\n"
        "                guint32 state = dev_impl->button_state & ~AMOTION_EVENT_BUTTON_PRIMARY;\n",
    ),
]


def main() -> int:
    if len(sys.argv) != 2:
        print("uso: gtk4-touch-slop.py <srcdir-gtk>", file=sys.stderr)
        return 2
    path = sys.argv[1].rstrip("/") + "/" + SRC_REL
    with open(path, "r") as fh:
        src = fh.read()

    if "FASE10B-SLOP" in src:
        print("ERROR: parche FASE10B ya aplicado", file=sys.stderr)
        return 1
    for i, (old, new) in enumerate(EDITS, 1):
        n = src.count(old)
        if n != 1:
            print("ERROR: edit %d: patron encontrado %d veces (esperado 1); " % (i, n) +
                  "re-auditar (¿FASE 10 aplicada?)", file=sys.stderr)
            return 1
        src = src.replace(old, new)

    markers = ["FASE10B-SLOP", "g_touch_slop", "FASE10B_SLOP_SQ"]
    for m in markers:
        if m not in src:
            print("ERROR: marker '%s' no presente tras el parche" % m, file=sys.stderr)
            return 1

    with open(path, "w") as fh:
        fh.write(src)
    print("gtk4: touch slop aplicado en %s" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main())