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
# Version 26.2.20 = version_info '26:2:20' real de freetype 2.13.3 (ft_version
# = tr : . en builds/unix) — OJO: es el esquema del .pc, NO la version real.
# cairo 1.18.6 meson.build:9 exige '>= 23.0.17' (= freetype 2.10 en esquema
# .pc): con el pin anterior 21.0.15 (que lei mal como si fuera '>= 2.6')
# rechazaba freetype_dep y apagaba CAIRO_HAS_FT en silencio => libcairo.a sin
# cairo_ft_* y peticion al enlazar libgtk-4.so (run #18). fontconfig 2.17.1:30
# pide '>= 21.0.15' y cairo '>= 23.0.17' → 26.2.20 cumple ambos; pango/gtk4 no
# pinnean freetype2 (barrido) y todos los lectores son comparadores '>='
# sin techo, asi que subir la version es seguro.
# Requires libbrotlidec: deps.md oficial = freetype -> brotli (WOFF2); el
# linker exigia BrotliDecoderDecompress al enlazar fc-* (auditoria nm:
# freetype usa zlib(4)+brotli(1)). Nombres '-static' = como los compila Blender.
pc libbrotlicommon brotli 1.0.9  "-lbrotlicommon-static"
pc libbrotlidec    brotli 1.0.9  "-lbrotlidec-static -lbrotlicommon-static"
pc libbrotlienc    brotli 1.0.9  "-lbrotlienc-static -lbrotlicommon-static"
pc freetype2   freetype  26.2.20 "-lfreetype -lz -lm" "-I\${prefix}/include/freetype2" "libbrotlidec"
# harfbuzz -> freetype(27 simbolos FT_*) segun deps.md + auditoria nm.
# Cflags-extra: layout ANIDADO include/harfbuzz/hb.h pero el consumo es
# <hb.h> (pango-coverage.h:28 e inkscape) => -I al subdir, igual que el
# harfbuzz.pc upstream. Sin esto: 'hb.h file not found' (pango run #12).
pc harfbuzz    harfbuzz  10.0.1  "-lharfbuzz" "-I\${prefix}/include/harfbuzz" "freetype2"
# harfbuzz-subset: gtk4/meson.build:469 lo exige INCONDICIONAL (sin
# required:) => harfbuzz-subset.pc + libharfbuzz-subset.a (verificado en
# Blender). Libs autocontenido '-lharfbuzz-subset -lharfbuzz' (orden de
# enlace estatico subset->core garantizado sin depender del dedup de meson;
# los -l repetidos son inocuos: precedente -lintl repetido en enlaces reales).
pc harfbuzz-subset harfbuzz 10.0.1 "-lharfbuzz-subset -lharfbuzz" "-I\${prefix}/include/harfbuzz"
# fribidi: mismo caso, anidado include/fribidi/ y pango incluye <fribidi.h>
# (upstream fribidi.pc tambien -I al subdir); habria petado justo tras hb.
pc fribidi     fribidi   1.0.12  "-lfribidi" "-I\${prefix}/include/fribidi"

# --- XML / GL ---
# xml2: layout include/libxml2/ (parser.h confirmado); zlib+zstd plegados en Libs
# para el link estático (blender lo compiló sin lzma).
pc libxml-2.0  xml2      2.14.6  "-lxml2 -lz -lzstd -lm" "-I\${prefix}/include/libxml2"
# epoxy: gtk4/meson.build:561 lee la variable epoxy_has_egl de epoxy.pc
# (get_variable con default '0'; solo setea HAVE_EGL si == '1'). HAVE_EGL
# gatea la DECL (gdkglcontextprivate.h:161) y la DEF (gdkglcontext.c:598) de
# gdk_gl_context_set_egl_native_window => sin la variable, el setup pasa en
# silencio y peta compilando gdkandroidsurface.c:403 con
# implicit-function-declaration (run #16). Valor 1 verificado en el binario:
# dispatch_egl.c.o + egl_generated.h presentes (modo conservative dlopen).
# Libs SOLO -lepoxy (verificado con nm): egl*/gl* se mapean a punteros
# epoxy_egl*/epoxy_gl* (D, dentro del .a, p.ej. egl_generated.h:1375
# '#define eglMakeCurrent epoxy_eglMakeCurrent') => NI -lEGL NI -lGLESv2.
pc epoxy       epoxy     1.5.10  "-lepoxy"
printf '%s\n' 'epoxy_has_egl=1' >> "$OUT/epoxy.pc"

echo "OK: $(find "$OUT" -name '*.pc' | wc -l) .pc shim en $OUT"
