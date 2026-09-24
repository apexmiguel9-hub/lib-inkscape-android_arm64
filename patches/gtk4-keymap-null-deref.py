#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FASE 10C: NULL deref en gdk_android_keymap_translate_keyboard_state.

Crash real de produccion (via crash-stack.txt FASE8):
  TextTool::root_handler -> get_latin_keyval_impl -> gdk_display_translate_key
    -> gdk_keymap_translate_keyboard_state -> SIGSEGV

get_latin_keyval_impl (src/ui/tools/tool-base.cpp) llama a
gdk_display_translate_key(display, keycode, state, group, &keyval,
                          nullptr /*effective_group*/, nullptr /*level*/,
                          &modifiers);
y el backend android hacia:

    if (*effective_group)      <-- dereferencia el OUT param sin validar
      *effective_group = 0;

=> cada tecla que llegaba al canvas (Text tool, numeros en toolbars, etc.)
   con effective_group==NULL era un SIGSEGV. El contrato de GdkKeymap: los
   OUT params son opcionales y pueden ser NULL (asi lo hace el resto del
   backend: `if (level) ...`).

Uso: python3 gtk4-keymap-null-deref.py <srcdir-gtk>
"""
import sys

SRC_REL = "gdk/android/gdkandroidkeymap.c"

OLD = "  if (*effective_group)\n    *effective_group = 0;\n"

NEW = (
    "  /* FASE10C-KEYMAP: effective_group es OUT opcional (puede ser NULL):\n"
    "   * get_latin_keyval de inkscape lo pasa nullptr y la vieja condicion\n"
    "   * dereferenciaba el puntero sin validar -> SIGSEGV por cada tecla. */\n"
    "  if (effective_group)\n"
    "    *effective_group = 0;\n"
)


def main() -> int:
    if len(sys.argv) != 2:
        print("uso: gtk4-keymap-null-deref.py <srcdir-gtk>", file=sys.stderr)
        return 2
    path = sys.argv[1].rstrip("/") + "/" + SRC_REL
    with open(path, "r") as fh:
        src = fh.read()

    if "FASE10C-KEYMAP" in src:
        print("ERROR: parche FASE10C ya aplicado", file=sys.stderr)
        return 1
    n = src.count(OLD)
    if n != 1:
        print("ERROR: patron buggy encontrado %d veces (esperado 1)" % n, file=sys.stderr)
        return 1
    src = src.replace(OLD, NEW)

    if "FASE10C-KEYMAP" not in src or "if (effective_group)" not in src:
        print("ERROR: markers FASE10C no presentes tras el parche", file=sys.stderr)
        return 1
    if "if (*effective_group)" in src:
        print("ERROR: sigue el deref NULL sin arreglar", file=sys.stderr)
        return 1

    with open(path, "w") as fh:
        fh.write(src)
    print("gtk4: NULL deref keymap corregido en %s" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main())