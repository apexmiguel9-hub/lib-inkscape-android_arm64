# Versiones

Todas verificadas por `HTTP HEAD` / `gh api` contra el tarball real (2026-09-22).
Si un día una URL da 404, actualizar aquí (el cache de Actions usa este archivo de clave).

## Tier1 — básicas (implementado en `build/build.sh`)

| Lib | Ver | URL | Build | Notas |
|---|---|---|---|---|
| libatomic_ops | 7.8.2 | <https://github.com/ivmai/libatomic_ops/releases/download/v7.8.2/libatomic_ops-7.8.2.tar.gz> | autotools | la necesita bdw-gc en ARM |
| libiconv | 1.17 | <https://ftp.gnu.org/gnu/libiconv/libiconv-1.17.tar.gz> | autotools | bionic no trae iconv completo |
| gettext | 0.23 | <https://ftp.gnu.org/gnu/gettext/gettext-0.23.tar.xz> | autotools | solo `libintl.a` (Inkscape: `find_package(Intl REQUIRED)`) |
| libffi | 3.5.2 | <https://github.com/libffi/libffi/releases/download/v3.5.2/libffi-3.5.2.tar.gz> | autotools | mismo que `deps.md` de Blender |
| pcre2 | 10.44 | <https://github.com/PCRE2Project/pcre2/releases/download/pcre2-10.44/pcre2-10.44.tar.gz> | autotools | la necesita glib (solo pcre2-8) |
| expat | 2.8.4 | <https://github.com/libexpat/libexpat/releases/download/R_2_8_4/expat-2.8.4.tar.xz> | cmake | la necesita fontconfig; Blender decía `2_7_5` pero su asset usa otro naming |
| bdw-gc | 8.2.6 | <https://github.com/ivmai/bdwgc/releases/download/v8.2.6/gc-8.2.6.tar.gz> | autotools | Inkscape: `bdw-gc` REQUIRED |
| lcms2 | 2.16 | <https://github.com/mm2/Little-CMS/releases/download/lcms2.16/lcms2-2.16.tar.gz> | autotools | Inkscape: `lcms2` REQUIRED |
| ICU | 75.1 | <https://github.com/unicode-org/icu/releases/download/release-75-1/icu4c-75_1-src.tgz> | 2 fases: host + `--with-cross-build` | Inkscape: `icu-uc` REQUIRED; NO está en las libs de Blender |
| GSL | 2.8 | <https://ftp.gnu.org/gnu/gsl/gsl-2.8.tar.gz> | autotools | Inkscape: `find_package(GSL REQUIRED)` |
| double-conversion | 3.3.0 | <https://github.com/google/double-conversion/archive/refs/tags/v3.3.0.tar.gz> | cmake (CONFIG) | Inkscape: `find_package(double-conversion CONFIG REQUIRED)` |
| pixman | 0.42.2 | <https://www.cairographics.org/releases/pixman-0.42.2.tar.gz> | meson si existe, si no autotools | la necesita cairo |
| libxslt | 1.1.43 | <https://download.gnome.org/sources/libxslt/1.1/libxslt-1.1.43.tar.xz> | autotools | Inkscape: `LibXslt REQUIRED`; necesita el shim `libxml-2.0.pc`. **Bajado de 1.1.45**: ésta exige `libxml2 >= 2.15.1` y reusamos el 2.14.6 de Blender (1.1.43 pide solo >= 2.6.27; 1.1.44 no existe, 404) |
| boost | 1.87.0 | <https://archives.boost.io/release/1.87.0/source/boost_1_87_0.tar.bz2> | headers + intento de `stacktrace_basic` | ojo: nombre con **guion bajos** `boost_1_87_0` |

## Tier2 — stack GNOME (implementado)

| Lib | Ver | URL | Notas |
|---|---|---|---|
| glib | 2.88.0 | <https://download.gnome.org/sources/glib/2.88/glib-2.88.0.tar.xz> | meson; necesita pcre2/libffi/iconv/gettext del tier1 |
| cairo | 1.18.0 | <https://cairographics.org/releases/cairo-1.18.0.tar.xz> | meson; pixman + freetype + png + zlib |
| gdk-pixbuf | 2.42.12 | <https://download.gnome.org/sources/gdk-pixbuf/2.42/gdk-pixbuf-2.42.12.tar.xz> | loaders (riesgo 4 del README) |
| fontconfig | 2.17.1 | <https://gitlab.freedesktop.org/api/v4/projects/890/packages/generic/fontconfig/2.17.1/fontconfig-2.17.1.tar.xz> | pango 1.58 exige `fontconfig >= 2.17.0`; el release dir oficial se paró en 2.16 (2.15/2.16 siguen ahí); sha256 `9f5cae93f4fffc1fbc05ae99cdfc708cd60dfd6612ffc0512827025c026fa541`; sentinel `freetype_req = '>= 21.0.15'` sigue = shim 21.0.15 |
| pango | 1.58.0 | <https://download.gnome.org/sources/pango/1.58/pango-1.58.0.tar.xz> | par estables: dirs 1.54-1.58, `1.90` es dev |
| graphene | 1.10.8 | <https://download.gnome.org/sources/graphene/1.10/graphene-1.10.8.tar.xz> | meson, minúscula |
| gtk | 4.22.5 | <https://download.gnome.org/sources/gtk/4.22/gtk-4.22.5.tar.xz> | `-Dandroid-backend=true -Dandroid-runtime=true`; 5 parches = maduro |
| sigc++ | 3.8.0 | <https://gitlab.gnome.org/GNOME/sigcplusplus/-/archive/3.8.0/sigcplusplus-3.8.0.tar.gz> | **solo gitlab.gnome.org** (download.gnome.org y mirror GitHub = 404) |
| glibmm | 2.78.1 | <https://download.gnome.org/sources/glibmm/2.78/glibmm-2.78.1.tar.xz> | URL+SHA256=`f473f297…` sacados del propio CMake de Inkscape (fallback ExternalProject) |
| cairomm | 1.15.4 | <https://download.gnome.org/sources/cairomm/1.15/cairomm-1.15.4.tar.xz> | serie 1.15 = API/pc `cairomm-1.16` (no existe dir 1.16) |
| pangomm | 2.58.0 | <https://download.gnome.org/sources/pangomm/2.58/pangomm-2.58.0.tar.xz> | pc congelado `pangomm-2.48` |
| gtkmm | 4.14.0 | <https://download.gnome.org/sources/gtkmm/4.14/gtkmm-4.14.0.tar.xz> | la usa el propio ExternalProject de Inkscape ⇒ probada con él |
| libxkbcommon | 1.7.0 | <https://xkbcommon.org/download/libxkbcommon-1.7.0.tar.xz> | GTK4 la exige (deps oficiales); **1.8.0 no existe** (404); `xkeyboard-config` (datos) = runtime |

Toda la pila mm es **meson** en estas versiones ⇒ no hace falta `mm-common`/autotools.

## Reutilizadas de `lib-android_arm64` oficial (verificado en el tree real)

| Lib | Ver | Layout / notas |
|---|---|---|
| zlib | 1.3.1 | `include/zlib.h` plano; `libz.a` |
| libpng | 1.6.58 | `include/png.h` (+ `libpng16/`) |
| libjpeg | 2.1.3 | `include/jpeglib.h` plano |
| libwebp | 1.6.0 | `include/webp/…` |
| openjpeg | 2.5.3 | `include/openjpeg.h` plano |
| freetype | 2.13.3 | `include/freetype2/` y **`FT_CONFIG_OPTION_SYSTEM_ZLIB`** ⇒ `.pc` con `-lz` |
| harfbuzz | 10.0.1 | `include/harfbuzz/hb.h` (+ `libharfbuzz-subset.a`) |
| fribidi | 1.0.12 | `include/fribidi/fribidi.h` |
| libxml2 | 2.14.6 | `include/libxml2/libxml/parser.h` |
| libepoxy | 1.5.10 | `include/epoxy/gl.h` |
| potrace | 1.16 | `include/potracelib.h` plano — lo encuentra `FindPotrace.cmake` vía `CMAKE_PREFIX_PATH` (sin `.pc`) |
| python | 3.13.13 | runtime (APK); el CMake de Inkscape NO busca Python |
| zstd | 1.5.7 | plegado en `libxml-2.0.pc` |

**Ninguna trae `.pc`** → `scripts/gen-pc.sh` genera los shims en `pc-overlay/`.

## Tier3 — OFF en primera pasada

poppler, libwpg, libvisio, libcdr, gtksourceview-5, libspelling, tiff, jemalloc,
readline, ImageMagick/GraphicsMagick.
