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

# pc <nombre> <subdir-de-blender> <version> <Libs> [Cflags-extra] [Requires]
# Requires: los consumidores usan pkg-config sin --static, asi que la cadena
# estatica interna (freetype->brotli, harfbuzz->freetype) va por Requires,
# que SI expande siempre. Ver auditoria nm: el set de 14 libs es cerrado.
pc() {
  local name="$1" sub="$2" ver="$3" libs="$4" cflags="${5:-}" req="${6:-}"
  cat > "$OUT/$name.pc" <<EOF
prefix=$B/$sub
libdir=\${prefix}/lib
includedir=\${prefix}/include

Name: $name
Description: Shim generado para las libs precompiladas de Blender ($sub)
Version: $ver
Libs: -L\${libdir} $libs
Cflags: -I\${includedir} $cflags
${req:+Requires: $req}
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
# Version 21.0.15 (el real es 2.13.3): fontconfig 2.15 meson.build:22 exige
# '>= 21.0.15' por pkg-config — sentinel imposible que en escritorio redirige
# al metodo cmake, pero en nuestro cross ese metodo no existe y nos dejaba
# fuera. Solo lo leen comparadores '>=', sin techo (cairo/pango: >= 2.6).
# Requires libbrotlidec: deps.md oficial = freetype -> brotli (WOFF2); el
# linker exigia BrotliDecoderDecompress al enlazar fc-* (auditoria nm:
# freetype usa zlib(4)+brotli(1)). Nombres '-static' = como los compila Blender.
pc libbrotlicommon brotli 1.0.9  "-lbrotlicommon-static"
pc libbrotlidec    brotli 1.0.9  "-lbrotlidec-static -lbrotlicommon-static"
pc libbrotlienc    brotli 1.0.9  "-lbrotlienc-static -lbrotlicommon-static"
pc freetype2   freetype  21.0.15 "-lfreetype -lz -lm" "-I\${prefix}/include/freetype2" "libbrotlidec"
# harfbuzz -> freetype(27 simbolos FT_*) segun deps.md + auditoria nm.
# Cflags-extra: layout ANIDADO include/harfbuzz/hb.h pero el consumo es
# <hb.h> (pango-coverage.h:28 e inkscape) => -I al subdir, igual que el
# harfbuzz.pc upstream. Sin esto: 'hb.h file not found' (pango run #12).
pc harfbuzz    harfbuzz  10.0.1  "-lharfbuzz" "-I\${prefix}/include/harfbuzz" "freetype2"
# fribidi: mismo caso, anidado include/fribidi/ y pango incluye <fribidi.h>
# (upstream fribidi.pc tambien -I al subdir); habria petado justo tras hb.
pc fribidi     fribidi   1.0.12  "-lfribidi" "-I\${prefix}/include/fribidi"

# --- XML / GL ---
# xml2: layout include/libxml2/ (parser.h confirmado); zlib+zstd plegados en Libs
# para el link estático (blender lo compiló sin lzma).
pc libxml-2.0  xml2      2.14.6  "-lxml2 -lz -lzstd -lm" "-I\${prefix}/include/libxml2"
pc epoxy       epoxy     1.5.10  "-lepoxy"

echo "OK: $(find "$OUT" -name '*.pc' | wc -l) .pc shim en $OUT"
