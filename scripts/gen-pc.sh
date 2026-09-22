#!/usr/bin/env bash
# Genera los .pc shim que Blender NO incluye en lib-android_arm64 (su build usa
# rutas CMake, pero Inkscape/cairo/pango/fontconfig buscan TODO por pkg-config).
#
# Uso: scripts/gen-pc.sh <ruta-a-lib-android_arm64> [outdir]
#
# Versiones/paths verificados contra el tree real (ver deps.md).
set -euo pipefail

B="${1:?Uso: gen-pc.sh <ruta-a-lib-android_arm64> [outdir]}"
OUT="${2:-$PWD/pc-overlay}"
[[ -d "$B" ]] || { echo "ERROR: no existe $B" >&2; exit 1; }
mkdir -p "$OUT"

# pc <nombre> <subdir-de-blender> <version> <Libs> [Cflags-extra]
pc() {
  local name="$1" sub="$2" ver="$3" libs="$4" cflags="${5:-}"
  cat > "$OUT/$name.pc" <<EOF
prefix=$B/$sub
libdir=\${prefix}/lib
includedir=\${prefix}/include

Name: $name
Description: Shim generado para las libs precompiladas de Blender ($sub)
Version: $ver
Libs: -L\${libdir} $libs
Cflags: -I\${includedir} $cflags
EOF
}

# --- compresión / imagen ---
pc zlib        zlib      1.3.1   "-lz"
pc libpng      png       1.6.58  "-lpng16 -lz -lm"
pc libpng16    png       1.6.58  "-lpng16 -lz -lm"
pc libjpeg     jpeg      2.1.3   "-ljpeg -lm"
pc libwebp     webp      1.6.0   "-lwebp -lm"
pc libopenjp2  openjpeg  2.5.3   "-lopenjp2"

# --- texto ---
# freetype: layout include/freetype2/ (ft2build.h confirmado), zlib del sistema
# (FT_CONFIG_OPTION_SYSTEM_ZLIB definido) → -lz obligatorio.
pc freetype2   freetype  2.13.3  "-lfreetype -lz -lm" "-I\${prefix}/include/freetype2"
pc harfbuzz    harfbuzz  10.0.1  "-lharfbuzz"
pc fribidi     fribidi   1.0.12  "-lfribidi"

# --- XML / GL ---
# xml2: layout include/libxml2/ (parser.h confirmado); zlib+zstd plegados en Libs
# para el link estático (blender lo compiló sin lzma).
pc libxml-2.0  xml2      2.14.6  "-lxml2 -lz -lzstd -lm" "-I\${prefix}/include/libxml2"
pc epoxy       epoxy     1.5.10  "-lepoxy"

echo "OK: $(find "$OUT" -name '*.pc' | wc -l) .pc shim en $OUT"
