#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FASE 10B -> ABSORBIDO por FASE 12 (no-op).

El touch slop de la FASE 10B quedo integrado en el modelo diferido de gestos de
gtk4-touch-as-pointer.py (FASE 12, modelo GHOST_SystemAndroid del port de
Blender):
  * el click de un tap se entrega como press+release en el punto donde aterrizo
    el dedo (ya no hace falta anclar los MOTION al punto de press),
  * FASE12_SLOP (~12 css px) es el umbral a partir del cual un gesto pasa a ser
    drag (press en el aterrizaje + motion siguiendo al dedo),
  * el long-press (500 ms) da click derecho.

Este archivo se mantiene por compatibilidad de la cadena de parches: NO hace
nada. build.sh NO lo invoca desde FASE 12; si alguien lo lanza sobre una fuente
con FASE 12 aplicada termina sin tocar nada.
"""
import sys


def main() -> int:
    if len(sys.argv) != 2:
        print("uso: gtk4-touch-slop.py <srcdir-gtk>   (no-op desde FASE 12)",
              file=sys.stderr)
        return 2
    print("gtk4: touch-slop absorbido por FASE 12 (no-op, no toca nada)")
    return 0


if __name__ == "__main__":
    sys.exit(main())