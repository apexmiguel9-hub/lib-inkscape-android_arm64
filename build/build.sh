#!/usr/bin/env bash
# Cross-compile de las deps de Inkscape-for-Android que NO vienen en
# lib-android_arm64 oficial de Blender. arm64 / API 31 / NDK r30.
#
# Recetas adaptadas de blender_for_android: build_files/android/deps/build.sh
# (Wanderson M. Pimenta / Simfeo) + versiones verificadas contra los tarballs.
#
# Uso:
#   ANDROID_NDK_HOME=/ruta/ndk BLENDER_LIBS=/ruta/lib-android_arm64 \
#     build/build.sh [tier1|tier2|all|<lib> <lib>...]
#
# Cada lib se instala en .work/staging/<lib> y se "cosecha" a <repo>/<lib>/{include,lib}
# (mismo layout que projects.blender.org/blender/lib-android_arm64).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$ROOT/.work"
DL="$WORK/dl"
STG="$WORK/staging"
HOSTICU="$WORK/host-icu"
BLENDER_LIBS="${BLENDER_LIBS:-}"
API="${ANDROID_API:-31}"
TRIPLE="aarch64-linux-android"

[[ -n "${ANDROID_NDK_HOME:-}" ]] || { echo "ERROR: exporta ANDROID_NDK_HOME (setup-ndk en Actions)" >&2; exit 1; }
[[ -d "$BLENDER_LIBS" ]] || { echo "ERROR: BLENDER_LIBS no existe: '$BLENDER_LIBS' (clona lib-android_arm64 antes)" >&2; exit 1; }

TC="$ANDROID_NDK_HOME/toolchains/llvm/prebuilt/linux-x86_64"
export CC="$TC/bin/$TRIPLE$API-clang"
export CXX="$TC/bin/$TRIPLE$API-clang++"
export AR="$TC/bin/llvm-ar"
export RANLIB="$TC/bin/llvm-ranlib"
export STRIP="$TC/bin/llvm-strip"
export CFLAGS="-O2 -fPIC"
export CXXFLAGS="-O2 -fPIC"
NPROC="$(nproc)"
PKG_CONFIG="${PKG_CONFIG:-pkg-config}"

mkdir -p "$DL" "$STG"

# ---------------------------------------------------------------- versiones
U_ATOMIC_OPS="https://github.com/ivmai/libatomic_ops/releases/download/v7.8.2/libatomic_ops-7.8.2.tar.gz"
U_LIBICONV="https://ftp.gnu.org/gnu/libiconv/libiconv-1.17.tar.gz"
U_GETTEXT="https://ftp.gnu.org/gnu/gettext/gettext-0.23.tar.xz"
U_LIBFFI="https://github.com/libffi/libffi/releases/download/v3.5.2/libffi-3.5.2.tar.gz"
U_PCRE2="https://github.com/PCRE2Project/pcre2/releases/download/pcre2-10.44/pcre2-10.44.tar.gz"
U_EXPAT="https://github.com/libexpat/libexpat/releases/download/R_2_8_4/expat-2.8.4.tar.xz"
U_BDWGC="https://github.com/ivmai/bdwgc/releases/download/v8.2.6/gc-8.2.6.tar.gz"
U_LCMS2="https://github.com/mm2/Little-CMS/releases/download/lcms2.16/lcms2-2.16.tar.gz"
U_ICU="https://github.com/unicode-org/icu/releases/download/release-75-1/icu4c-75_1-src.tgz"
U_GSL="https://ftp.gnu.org/gnu/gsl/gsl-2.8.tar.gz"
U_DCONV="https://github.com/google/double-conversion/archive/refs/tags/v3.3.0.tar.gz"
U_PIXMAN="https://www.cairographics.org/releases/pixman-0.42.2.tar.gz"
U_LIBXSLT="https://download.gnome.org/sources/libxslt/1.1/libxslt-1.1.43.tar.xz"
U_BOOST="https://archives.boost.io/release/1.87.0/source/boost_1_87_0.tar.bz2"

# tier2 — stack GNOME (opciones meson verificadas contra cada tarball)
U_FONTCONFIG="https://gitlab.freedesktop.org/api/v4/projects/890/packages/generic/fontconfig/2.17.1/fontconfig-2.17.1.tar.xz"
U_GLIB="https://download.gnome.org/sources/glib/2.88/glib-2.88.0.tar.xz"
U_LIBXKBCOMMON="https://xkbcommon.org/download/libxkbcommon-1.7.0.tar.xz"
U_GDK_PIXBUF="https://download.gnome.org/sources/gdk-pixbuf/2.42/gdk-pixbuf-2.42.12.tar.xz"
U_CAIRO="https://cairographics.org/releases/cairo-1.18.6.tar.xz"
U_PANGO="https://download.gnome.org/sources/pango/1.58/pango-1.58.0.tar.xz"
U_GRAPHENE="https://download.gnome.org/sources/graphene/1.10/graphene-1.10.8.tar.xz"
U_TIFF="https://download.osgeo.org/libtiff/tiff-4.7.2.tar.gz"
U_GTK4="https://download.gnome.org/sources/gtk/4.22/gtk-4.22.5.tar.xz"
U_SIGCPP="https://gitlab.gnome.org/GNOME/sigcplusplus/-/archive/3.8.0/sigcplusplus-3.8.0.tar.gz"
U_GLIBMM="https://download.gnome.org/sources/glibmm/2.78/glibmm-2.78.1.tar.xz"
U_CAIROMM="https://download.gnome.org/sources/cairomm/1.15/cairomm-1.15.4.tar.xz"
U_PANGOMM="https://download.gnome.org/sources/pangomm/2.58/pangomm-2.58.0.tar.xz"
U_GTKMM="https://download.gnome.org/sources/gtkmm/4.14/gtkmm-4.14.0.tar.xz"

TIER1=(atomic_ops libiconv gettext libffi pcre2 expat bdw-gc lcms2 icu gsl double-conversion pixman libxslt boost)
# orden = orden de dependencias: fontconfig ANTES de cairo (cairo-ft la exige)
TIER2=(fontconfig glib libxkbcommon gdk-pixbuf cairo pango graphene tiff gtk4 sigc++ glibmm cairomm pangomm gtkmm)

# solo las libs de blender que realmente usamos (evita colisiones de headers)
# brotli: cadena interna de freetype (WOFF2); ver shims libbrotli* en gen-pc.sh
BLENDER_WANT=(zlib png jpeg freetype harfbuzz fribidi xml2 epoxy potrace webp openjpeg zstd brotli)

log() { echo "[$(date +%H:%M:%S)] $*" >&2; }

# ---------------------------------------------------------------- fetch/extract
fetch() { # fetch <url> -> imprime path del tarball en stdout
  local url="$1" f="$DL/$(basename "$1")"
  if [[ ! -f "$f" ]]; then
    log "fetch $(basename "$f")"
    curl -fsSL --retry 3 -o "$f.tmp" "$url"
    mv "$f.tmp" "$f"
  fi
  echo "$f"
}

extract() { # extract <tarball> -> imprime directorio fuente
  local f="$1"
  rm -rf "$WORK/src"
  mkdir -p "$WORK/src"
  case "$f" in
    *.tar.gz|*.tgz) tar -xzf "$f" -C "$WORK/src" ;;
    *.tar.xz)       tar -xJf "$f" -C "$WORK/src" ;;
    *.tar.bz2)      tar -xjf "$f" -C "$WORK/src" ;;
    *) echo "ERROR: formato desconocido $f" >&2; exit 1 ;;
  esac
  find "$WORK/src" -mindepth 1 -maxdepth 1 -type d | head -1
}

# ---------------------------------------------------------------- env dinamico
HARVEST_ROOTS=()

refresh_env() { # recalcula include/lib/pkgconfig contra lo ya cosechado + blender
  HARVEST_ROOTS=()
  local pcs=() n
  for n in "${TIER1[@]}" "${TIER2[@]}"; do
    if [[ -d "$ROOT/$n" ]]; then
      HARVEST_ROOTS+=("$ROOT/$n")
      [[ -d "$ROOT/$n/lib/pkgconfig" ]] && pcs+=("$ROOT/$n/lib/pkgconfig")
    fi
  done
  for n in "${BLENDER_WANT[@]}"; do
    [[ -d "$BLENDER_LIBS/$n" ]] && HARVEST_ROOTS+=("$BLENDER_LIBS/$n")
  done
  [[ -d "$ROOT/pc-overlay" ]] && pcs+=("$ROOT/pc-overlay")

  local incs=() libs=() I
  for I in "${HARVEST_ROOTS[@]}"; do
    incs+=("-I$I/include")
    libs+=("-L$I/lib")
  done
  export CPPFLAGS="${incs[*]:-}"
  export LDFLAGS="${libs[*]:-}"

  # PKG_CONFIG_LIBDIR: SOLO nuestros .pc (aisla los .pc del host del runner)
  if [[ ${#pcs[@]} -gt 0 ]]; then
    local IFS=':'
    export PKG_CONFIG_LIBDIR="${pcs[*]}"
  fi
  unset PKG_CONFIG_PATH 2>/dev/null || true
  # por si acaso: sysroot anteponido a rutas absolutas de .pc = rutas muertas
  unset PKG_CONFIG_SYSROOT_DIR 2>/dev/null || true
}

cmake_prefix_path() {
  local IFS=':'
  echo "${HARVEST_ROOTS[*]:-}"
}

gen_cross() {
  cat > "$WORK/cross.ini" <<EOF
[binaries]
c = '$CC'
cpp = '$CXX'
ar = '$AR'
ranlib = '$RANLIB'
strip = '$STRIP'
pkg-config = '$PKG_CONFIG'

[host_machine]
system = 'android'
cpu_family = 'aarch64'
cpu = 'aarch64'
bits = '64'
endian = 'little'

[properties]
# SIN sys_root: meson lo usa como PKG_CONFIG_SYSROOT_DIR y anteponga el sysroot
# a los -I/-L ABSOLUTOS de nuestros .pc -> rutas inventadas
# (<sysroot>/home/runner/...) => 'ft2build.h not found' en fontconfig (y le pasaria
# a glib con zlib/pcre2). El sysroot real del NDK ya lo lleva el clang solo.
needs_exe_wrapper = true
EOF
}

# ---------------------------------------------------------------- harvest
harvest() { # harvest <lib>  mueve $STG/<lib> -> $ROOT/<lib> (atomico) y reubica .pc
  # en dos lineas: bash expande TODAS las palabras del 'local' antes de
  # ejecutarlo, asi que $name en la misma linea veria el scope exterior
  local name="$1"
  local src="$STG/$name" dst="$ROOT/$name" tmp="$ROOT/.harvest-$name"
  [[ -d "$src" ]] || { echo "ERROR: harvest: $src no existe" >&2; exit 1; }
  rm -rf "$dst" "$tmp"
  mkdir -p "$tmp"
  [[ -d "$src/include" ]] && cp -a "$src/include" "$tmp/"
  # algunos (gsl, icu...) instalan en lib64
  if [[ -d "$src/lib64" ]]; then
    mkdir -p "$tmp/lib"
    cp -a "$src/lib64/." "$tmp/lib/"
  fi
  if [[ -d "$src/lib" ]]; then
    mkdir -p "$tmp/lib"
    cp -a "$src/lib/." "$tmp/lib/"
  fi
  # pcs relocatables: prefix absoluto del staging -> relativo al propio .pc
  if [[ -d "$tmp/lib/pkgconfig" ]]; then
    find "$tmp/lib/pkgconfig" -name '*.pc' -type f | while read -r pc; do
      sed -i -E 's|^prefix=.*|prefix=${pcfiledir}/../..|' "$pc"
    done
  fi
  # atomico: o queda la carpeta completa o no queda nada
  mv "$tmp" "$dst"
  local npcs=0
  [[ -d "$dst/lib/pkgconfig" ]] && npcs=$(find "$dst/lib/pkgconfig" -name '*.pc' | wc -l)
  log "harvest $name: include=$([[ -d $dst/include ]] && echo si || echo no) libs=$(find "$dst/lib" -maxdepth 1 -name '*.a' 2>/dev/null | wc -l) pc=$npcs"
}

# ---------------------------------------------------------------- helpers de build
at_build() { # at_build <nombre> <srcdir> [opts de configure...]
  local name="$1" src="$2"; shift 2
  [[ -x "$src/configure" ]] || { echo "ERROR: $src no tiene configure" >&2; exit 1; }
  ( cd "$src" && ./configure --host="$TRIPLE" --prefix="$STG/$name" \
      --enable-static --disable-shared "$@" ) || {
    echo "=== configure de $name falló — tail de config.log ===" >&2
    tail -80 "$src/config.log" 2>/dev/null || true
    exit 1
  }
  make -C "$src" -j"$NPROC"
  make -C "$src" install
  harvest "$name"
}

cmake_build() { # cmake_build <nombre> <srcdir> [opts cmake...]
  local name="$1" src="$2"; shift 2
  cmake -S "$src" -B "$WORK/build-$name" \
    -DCMAKE_TOOLCHAIN_FILE="$ANDROID_NDK_HOME/build/cmake/android.toolchain.cmake" \
    -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM="android-$API" \
    -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF \
    -DCMAKE_POSITION_INDEPENDENT_CODE=ON \
    -DCMAKE_INSTALL_PREFIX="$STG/$name" \
    -DCMAKE_PREFIX_PATH="$(cmake_prefix_path)" \
    "$@"
  cmake --build "$WORK/build-$name" -j"$NPROC"
  cmake --install "$WORK/build-$name"
  harvest "$name"
}

meson_build() { # meson_build <nombre> <srcdir> [opts meson...]
  local name="$1" src="$2"; shift 2
  rm -rf "$WORK/build-$name"
  # nofallback: que NINGUN proyecto vendee subprojects en silencio (fontconfig
  # se colo con freetype2). Si falta un .pc, peta aqui y lo arreglamos de raiz.
  meson setup "$WORK/build-$name" "$src" \
    --cross-file "$WORK/cross.ini" \
    --prefix="$STG/$name" --libdir=lib \
    --default-library=static --buildtype=release \
    --wrap-mode=nofallback \
    "$@" || {
      echo "=== meson setup de '$name' fallo; tail de meson-log.txt ===" >&2
      tail -80 "$WORK/build-$name/meson-logs/meson-log.txt" 2>/dev/null >&2 || true
      exit 1
    }
  meson install -C "$WORK/build-$name"
  harvest "$name"
}

# ---------------------------------------------------------------- recetas tier1
build_atomic_ops() { at_build atomic_ops "$(extract "$(fetch "$U_ATOMIC_OPS")")"; }

build_libiconv() {
  at_build libiconv "$(extract "$(fetch "$U_LIBICONV")")" --disable-rpath
}

build_gettext() {
  # solo hace falta libintl (bionic no trae gettext/iconv completos)
  at_build gettext "$(extract "$(fetch "$U_GETTEXT")")" \
    --disable-java --disable-csharp --disable-curses --disable-openmp \
    --disable-acl --disable-rpath \
    --with-libiconv-prefix="$ROOT/libiconv"
}

build_libffi() {
  at_build libffi "$(extract "$(fetch "$U_LIBFFI")")" --disable-docs --disable-multiarch
}

build_pcre2() {
  at_build pcre2 "$(extract "$(fetch "$U_PCRE2")")" \
    --disable-pcre2-16 --disable-pcre2-32
}

build_expat() {
  cmake_build expat "$(extract "$(fetch "$U_EXPAT")")" \
    -DEXPAT_BUILD_TOOLS=OFF -DEXPAT_BUILD_EXAMPLES=OFF -DEXPAT_BUILD_TESTS=OFF
}

build_bdwgc() {
  # encuentra libatomic_ops via CPPFLAGS/LDFLAGS del harvest
  at_build bdw-gc "$(extract "$(fetch "$U_BDWGC")")"
}

build_lcms2() { at_build lcms2 "$(extract "$(fetch "$U_LCMS2")")"; }

build_icu() {
  # ICU cross = 2 árboles separados:
  #  - host: genera config/icucross.mk + tools (bin/) en su BUILD ROOT
  #  - target: out-of-source con --with-cross-build=<build root del host>
  # (pasar el prefix de install o hacer distclean rompe icucross.mk)
  local tgz hostroot tdir
  tgz="$(fetch "$U_ICU")"
  rm -rf "$WORK/icu-host" "$WORK/icu-target"
  mkdir -p "$WORK/icu-host" "$WORK/icu-target"
  tar -xzf "$tgz" -C "$WORK/icu-host"
  tar -xzf "$tgz" -C "$WORK/icu-target"
  hostroot="$WORK/icu-host/icu/source"
  tdir="$WORK/icu-target/icu"

  log "icu: fase host (nativo — anula el toolchain exportado)"
  ( cd "$hostroot"
    CC=gcc CXX=g++ AR=ar RANLIB=ranlib ./configure --prefix="$HOSTICU" \
      --disable-samples --disable-tests --enable-static --disable-shared
    make -j"$NPROC"
    make install )

  log "icu: fase target (out-of-source)"
  mkdir -p "$tdir/build"
  ( cd "$tdir/build"
    ../source/configure --host="$TRIPLE" --prefix="$STG/icu" \
      --with-cross-build="$hostroot" \
      --disable-samples --disable-tests \
      --enable-static --disable-shared \
      --with-data-packaging=library
    make -j"$NPROC"
    make install )
  harvest icu
}

build_gsl() { at_build gsl "$(extract "$(fetch "$U_GSL")")"; }

build_dconv() {
  cmake_build double-conversion "$(extract "$(fetch "$U_DCONV")")" \
    -DWITH_GFLAGS=OFF -DBUILD_TESTING=OFF
}

build_pixman() {
  local dir
  dir="$(extract "$(fetch "$U_PIXMAN")")"
  if [[ -f "$dir/meson.build" ]]; then
    # los .S NEON de a64 usan el pegado de tokens '&' de GNU as, que el
    # integrated assembler de clang (NDK) NO entiende -> paths C portables
    meson_build pixman "$dir" -Da64-neon=disabled
  else
    at_build pixman "$dir"
  fi
}

build_libxslt() {
  # necesita libxml-2.0.pc -> generado por scripts/gen-pc.sh ANTES de correr esto
  at_build libxslt "$(extract "$(fetch "$U_LIBXSLT")")" \
    --without-python --without-crypto --without-debugger --disable-rpath
}

build_boost() {
  # headers + intento de libboost_stacktrace_basic.a (riesgo: bionic sin
  # execinfo.h — si falla, ver README "riesgos conocidos")
  local dir
  dir="$(extract "$(fetch "$U_BOOST")")"
  local pfx="$STG/boost"
  rm -rf "$pfx"
  mkdir -p "$pfx/include" "$pfx/lib"
  cp -a "$dir/boost" "$pfx/include/"
  if "$CXX" $CXXFLAGS -I"$dir" -c "$dir/libs/stacktrace/src/basic.cpp" \
       -o "$WORK/boost_basic.o" 2>"$WORK/boost_err.log"; then
    "$AR" rcs "$pfx/lib/libboost_stacktrace_basic.a" "$WORK/boost_basic.o"
    log "boost: stacktrace_basic OK"
  else
    log "boost: stacktrace_basic FALLÓ (ver .work/boost_err.log) — solo headers por ahora"
  fi
  harvest boost
}

# ---------------------------------------------------------------- recetas tier2
# Cada flag viene verificado contra el meson.options / meson_options.txt del
# propietario tarball: boolean no admite 'disabled' ni feature admite 'false'
# en algunos => flag mal puesto es error duro de meson.

build_fontconfig() {
  # gperf (apt); expat(tier1) + freetype2(blender) via pc/CPPFLAGS
  # cache-build OFF: por defecto EJECUTA fc-cache en install (imposible cross)
  # 2.17.1: pango 1.58 exige fontconfig >= 2.17.0 (con 2.15 peta en
  # pango/meson.build:295). Flags verificados 1:1 contra el meson.options
  # real de 2.17.1; sentinel freetype2 '>= 21.0.15' sigue = shim 21.0.15.
  meson_build fontconfig "$(extract "$(fetch "$U_FONTCONFIG")")" \
    -Ddoc=disabled -Dnls=disabled -Dtests=disabled -Dcache-build=disabled
  # 2.17 movio freetype2 a Requires.private (2.15 lo tenia PUBLICO con
  # expat): los consumidores (meson/CMake) consultan sin --static y no lo
  # verian => enlaces estaticos sin -lfreetype/-lexpat. Forzamos el layout
  # publico equivalente al de 2.15 (ya validado en cadena con cairo).
  local pc="$ROOT/fontconfig/lib/pkgconfig/fontconfig.pc"
  sed -i -E '/^Requires(\.private)?:/d' "$pc"
  sed -i -E 's/^(Libs:.*)$/Requires: freetype2, expat\n\1/' "$pc"
  grep -q '^Requires: freetype2, expat$' "$pc" || {
    echo "ERROR: fontconfig.pc Requires no parcheado a publico" >&2; exit 1; }
}

build_glib() {
  # pcre2/libffi/zlib del tier1 y blender via pc; selinux/libmount ausentes
  # por aislamiento de pc pero los apagamos explicitos
  meson_build glib "$(extract "$(fetch "$U_GLIB")")" \
    -Dtests=false -Dinstalled_tests=false -Dman=false -Ddocumentation=false \
    -Dnls=disabled -Dintrospection=disabled \
    -Dselinux=disabled -Dlibmount=disabled

  # Los .pc de glib declaran variables-tools (glib_genmarshal, glib_mkenums,
  # glib_compile_resources, gdbus_codegen...) con ruta a $prefix/bin: harvest()
  # no cosecha bin/ y ademas serian binarios aarch64. gdk-pixbuf/pango/gtk4 las
  # ejecutan en el HOST (error classico: "tool variable ... erroneous value /
  # This is a distributor issue"). Reapuntar a /usr/bin (libglib2.0-dev-bin +
  # libglib2.0-bin del workflow); la salida de genmarshal y el formateo
  # gresource son estables (API 2.32), tools 2.80 -> lib 2.88 sin problema.
  sed -i -E \
    's@^([a-z_0-9]+)=.*/(glib-[a-z-]+|gdbus-codegen)$@\1=/usr/bin/\2@' \
    "$ROOT/glib/lib/pkgconfig/"*.pc
}

build_libxkbcommon() {
  # GTK4 la exige (deps oficiales); x11 off porque exigiria libX11
  # (enable-x11 construye la lib xkbcommon-x11); datos xkb = runtime.
  # LDFLAGS += -lc++ -lm: meson.build:661 auto-detecta icu-uc (required:false)
  # y NUESTRO icu-uc.pc (tier1) lo activa => test-keysyms enlaza libicuuc.a
  # (C++) con driver C (clang, sin -lc++ automatico) y sin libm (modf/pow/log).
  # La lib src/ NO usa ICU (solo test/keysym.c via #if HAVE_ICU) => el extra
  # solo afecta a los binarios de este proyecto; refresh_env recalcula
  # LDFLAGS por lib, asi que no se arrastra a nadie mas.
  export LDFLAGS="$LDFLAGS -lc++ -lm"
  meson_build libxkbcommon "$(extract "$(fetch "$U_LIBXKBCOMMON")")" \
    -Denable-tools=false -Denable-x11=false -Denable-wayland=false
}

build_gdk_pixbuf() {
  # builtin_loaders=all => TODO estatico: sin .so ni loaders.cache en runtime
  # (mata el riesgo README4); png/jpeg de blender por pc
  local src
  src="$(extract "$(fetch "$U_GDK_PIXBUF")")"
  # (1) loaders_deps (png/jpeg) cuelga SOLO de los mods staticpixbufloader-*;
  #     gdkpixbuf_dep no lo arrastra => los tools (csource/pixdata) y todo
  #     consumidor estatico (gtk4, inkscape) enlazan la tabla builtin de
  #     io-png/io-jpeg SIN -lpng16 -ljpeg => undefined png_*. Upstream no lo
  #     ve: en desktop los loaders son .so dinamicos. Unica linea
  #     'dependencies: gdk_pixbuf_deps,' de gdk-pixbuf/meson.build
  #     (pixops/meson.build es otro fichero, sin png: intacto).
  sed -i 's@^  dependencies: gdk_pixbuf_deps,$@  dependencies: gdk_pixbuf_deps + loaders_deps,@' \
    "$src/gdk-pixbuf/meson.build"
  meson_build gdk-pixbuf "$src" \
    -Dbuiltin_loaders=all -Dintrospection=disabled \
    -Dgtk_doc=false -Ddocs=false -Dman=false \
    -Dtests=false -Dinstalled_tests=false
  # (2) el .pc generado: png/jpeg/z en Libs PUBLICO (nunca Libs.private:
  #     meson y pkg_check_modules de inkscape consultan sin --static) para que
  #     gtk4/inkscape arrastren el cierre de io-png/io-jpeg en sus .a.
  sed -i -E 's@^(Libs:.*-lgdk_pixbuf-2.0)@\1 -lpng16 -ljpeg -lz -lm@' \
    "$ROOT/gdk-pixbuf/lib/pkgconfig/gdk-pixbuf-2.0.pc"
}

build_cairo() {
  # sin flags de backend: xlib/xcb no encontrados (aislamiento pc) => solo
  # ft/png/fontconfig activos
  # 1.18.6 (no 1.18.0): gtk4 4.22.5 exige cairo >= 1.18.2 (gtk/meson.build:25
  # cairo_req; error en :462) y cairo-gobject.pc arrastra el campo Version.
  # sha256 1c767308174337a74694da0f3ec069c271452163a1ef4540964c50c301f157d4.
  # tests=disabled (sigue feature en 1.18.6): mata perf/test/pdiff/etc; solo
  # necesitamos libcairo*/.pc. boilerplate/gobject/script NO cuelgan de tests.
  # NOTA: el parche previo de libmalloc-stats ya NO hace falta: upstream
  # elimino util/malloc-stats.c en 1.18.x (verificado en el tree real).
  meson_build cairo "$(extract "$(fetch "$U_CAIRO")")" \
    -Dtests=disabled
}

build_pango() {
  meson_build pango "$(extract "$(fetch "$U_PANGO")")" \
    -Ddocumentation=false -Dman-pages=false \
    -Dbuild-testsuite=false -Dbuild-examples=false \
    -Dintrospection=disabled -Dxft=disabled
}

build_graphene() {
  meson_build graphene "$(extract "$(fetch "$U_GRAPHENE")")" \
    -Dtests=false -Dinstalled_tests=false
}

build_tiff() {
  # libtiff-4: gtk4/meson.build:484 lo exige INCONDICIONAL (sin required: y
  # sin opcion en meson.options). Inkscape NO lo usa directo (DefineDepends)
  # => sube del tier3 por culpa de gtk4.
  # 4.7.2 sha256 672bd7d10aee4606171afb864f3570b83340f6a33e2c186dc0512f7145ffdf6a
  # Opciones verificadas 1:1 en el CMakeLists real: tiff-tools/tests/contrib/
  # docs/cxx OFF (nada de ejecutables). Codecs SOLO jpeg+zlib: el resto
  # defaulta a ${*_FOUND} y con nuestro set webp/zstd darían ON => sus -l
  # acabarian en Libs.private (ocultos sin --static) y romperian los enlaces
  # de las tools de gtk4 (misma clase de mina que gdk-pixbuf). lzma/jbig/
  # libdeflate/lerc no existen en el set, pero se ponen explicitos por
  # determinismo. pc instalado = libtiff-4.pc, Libs: -ltiff <-> libtiff.a ✓.
  cmake_build tiff "$(extract "$(fetch "$U_TIFF")")" \
    -Dtiff-tools=OFF -Dtiff-tests=OFF -Dtiff-contrib=OFF -Dtiff-docs=OFF \
    -Dtiff-cxx=OFF \
    -Djpeg=ON -Dzlib=ON -Djpeg12=OFF \
    -Dwebp=OFF -Dzstd=OFF -Dlzma=OFF -Djbig=OFF -Dlibdeflate=OFF -Dlerc=OFF
}

build_gtk4() {
  # android-backend (boolean) + android-runtime (feature); el resto verificado
  # en el meson.options de gtk 4.22.5 (todos existen y con el tipo correcto)
  local src
  src="$(extract "$(fetch "$U_GTK4")")"
  # hb-glib: Blender compilo harfbuzz SIN glib => sin hb-glib.h (33 headers)
  # y sin hb_glib_* en el .a, pero gtkmain.c lo incluye sin guardar ni gatear
  # (unico include hb-glib de todo el arbol gtk; unica llamada en :869;
  # meson de gtk tampoco lo gatea => implicit-function-declaration run #17).
  # Parche de semantica IDENTICA: se inlinea la linea real de hb-glib.cc de
  # harfbuzz 10.0.1 ('return (hb_script_t) g_unicode_script_to_iso15924
  # (script);'; guint32 -> tag hb_script_t, gunicode.h:696, visible en
  # gtkmain via gi18n-lib.h->glib.h:97). Los otros dos hb-* que usa gtk
  # (hb-ot.h, hb-subset.h) si existen en Blender (barrido completo 1:1).
  sed -i 's@^#include <hb-glib\.h>$@#include <hb.h>@' "$src/gtk/gtkmain.c"
  sed -i 's@hb_glib_script_to_script ((GUnicodeScript) scripts\[i\])@(hb_script_t) g_unicode_script_to_iso15924 ((GUnicodeScript) scripts[i])@' \
    "$src/gtk/gtkmain.c"
  grep -q '^#include <hb\.h>$' "$src/gtk/gtkmain.c" \
    || { echo "ERROR: sed de hb.h no aplico en gtkmain.c" >&2; exit 1; }
  ! grep -q 'hb_glib' "$src/gtk/gtkmain.c" \
    || { echo "ERROR: queda hb_glib sin parchear en gtkmain.c" >&2; exit 1; }
  meson_build gtk4 "$src" \
    -Dandroid-backend=true -Dandroid-runtime=enabled \
    -Dx11-backend=false -Dwayland-backend=false -Dbroadway-backend=false \
    -Dintrospection=disabled -Ddocumentation=false -Dman-pages=false \
    -Dbuild-demos=false -Dbuild-testsuite=false -Dbuild-examples=false \
    -Dbuild-tests=false \
    -Dvulkan=disabled -Dmedia-gstreamer=disabled -Daccesskit=disabled
}

build_sigcpp() {
  # sin meson.options => CERO flags (un flag inexistente = error de meson)
  meson_build sigc++ "$(extract "$(fetch "$U_SIGCPP")")"
}

build_glibmm() {
  # build-documentation (combo) ya desactivado en tarball (if-maintainer-mode);
  # OJO: aqui NO existe build-tests (no inventarlo)
  meson_build glibmm "$(extract "$(fetch "$U_GLIBMM")")" -Dbuild-examples=false
}

build_cairomm() {
  # sin meson.options => sin flags
  meson_build cairomm "$(extract "$(fetch "$U_CAIROMM")")"
}

build_pangomm() {
  # sin build-tests/build-examples en sus opciones => sin flags
  meson_build pangomm "$(extract "$(fetch "$U_PANGOMM")")"
}

build_gtkmm() {
  meson_build gtkmm "$(extract "$(fetch "$U_GTKMM")")" \
    -Dbuild-demos=false -Dbuild-tests=false
}

build_one() {
  refresh_env
  # si ya esta cosechada en el repo, no la recompilamos (FORCE=1 para obligar)
  if [[ "${FORCE:-0}" != "1" && ( -d "$ROOT/$1/lib" || -d "$ROOT/$1/include" ) ]]; then
    log "skip $1 (ya cosechada — FORCE=1 para recompilar)"
    return 0
  fi
  log "=== build $1 ==="
  case "$1" in
    atomic_ops)         build_atomic_ops ;;
    libiconv)           build_libiconv ;;
    gettext)            build_gettext ;;
    libffi)             build_libffi ;;
    pcre2)              build_pcre2 ;;
    expat)              build_expat ;;
    bdw-gc)             build_bdwgc ;;
    lcms2)              build_lcms2 ;;
    icu)                build_icu ;;
    gsl)                build_gsl ;;
    double-conversion)  build_dconv ;;
    pixman)             build_pixman ;;
    libxslt)            build_libxslt ;;
    boost)              build_boost ;;
    fontconfig)         build_fontconfig ;;
    glib)               build_glib ;;
    libxkbcommon)       build_libxkbcommon ;;
    gdk-pixbuf)         build_gdk_pixbuf ;;
    cairo)              build_cairo ;;
    pango)              build_pango ;;
    graphene)           build_graphene ;;
    tiff)               build_tiff ;;
    gtk4)               build_gtk4 ;;
    sigc++)             build_sigcpp ;;
    glibmm)             build_glibmm ;;
    cairomm)            build_cairomm ;;
    pangomm)            build_pangomm ;;
    gtkmm)              build_gtkmm ;;
    *) echo "ERROR: lib desconocida '$1'" >&2; exit 1 ;;
  esac
}

selftest() {
  # compila un programa minimo con el MISMO entorno que usan las recetas;
  # si esto falla, el problema es el toolchain/entorno, no la lib
  log "selftest toolchain: $CC"
  df -h . | tail -1 | sed 's/^/[df] /' >&2 || true
  echo 'int main(void){return 0;}' > "$WORK/st.c"
  if ! "$CC" $CFLAGS ${CPPFLAGS:-} ${LDFLAGS:-} "$WORK/st.c" -o "$WORK/st.out" 2>"$WORK/st.err"; then
    echo "=== TOOLCHAIN ROTO (no es la lib) ===" >&2
    cat "$WORK/st.err" >&2
    "$CC" -v 2>&1 | tail -15 >&2 || true
    ls -la "$TC/bin/clang" >&2 || true
    exit 1
  fi
  log "selftest OK"
}

# ---------------------------------------------------------------- main
gen_cross
refresh_env
selftest
ARGS=("$@")
[[ ${#ARGS[@]} -eq 0 ]] && ARGS=(tier1)

JOBS=()
for a in "${ARGS[@]}"; do
  case "$a" in
    tier1) JOBS+=("${TIER1[@]}") ;;
    tier2) JOBS+=("${TIER2[@]}") ;;
    all)   JOBS+=("${TIER1[@]}" "${TIER2[@]}") ;;
    *)     JOBS+=("$a") ;;
  esac
done

log "trabajos: ${JOBS[*]}"
for j in "${JOBS[@]}"; do
  build_one "$j"
done

refresh_env
log "LISTO. libs en el repo:"
for j in "${JOBS[@]}"; do
  [[ -d "$ROOT/$j" ]] && echo "  $j  ($(du -sh "$ROOT/$j" | cut -f1))"
done
