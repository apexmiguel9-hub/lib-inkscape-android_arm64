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
# dir oficial = libsigc++ (NO sigc++): 3.6.0 es la ultima publicada ahi
# (3.8/ = 404) y gitlab.gnome.org redirige a Sign in incluso por API/clone
U_SIGCPP="https://download.gnome.org/sources/libsigc++/3.6/libsigc++-3.6.0.tar.xz"
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

  local incs=() libs=() libdirs=() I
  for I in "${HARVEST_ROOTS[@]}"; do
    incs+=("-I$I/include")
    libs+=("-L$I/lib")
    [[ -d "$I/lib" ]] && libdirs+=("$I/lib")
  done
  export CPPFLAGS="${incs[*]:-}"
  export LDFLAGS="${libs[*]:-}"
  # LIBRARY_PATH: pangomm y gtkmm llaman cpp.find_library('glibmm_generate_extra_defs-2.68')
  # SIN dirs: => la sonda de meson es un enlace desnudo '-l...' y el driver del
  # compilador NO lee LDFLAGS (probado con clang/gcc: solo honra LIBRARY_PATH)
  # => "Cannot find library glibmm_generate_extra_defs-2.68" en su setup aunque
  # LDFLAGS ya lleve -L. El driver si resuelve via LIBRARY_PATH (empirico).
  if [[ ${#libdirs[@]} -gt 0 ]]; then
    local lp
    lp=$(IFS=:; echo "${libdirs[*]}")
    export LIBRARY_PATH="$lp${LIBRARY_PATH:+:$LIBRARY_PATH}"
  fi

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
  # pcs relocatables: absolutos del staging del CI -> relativos al propio .pc.
  # Runs #5/#6 del port: el sed '^prefix=.*' NO matcheaba 'prefix = ' con
  # espacios (icu) y gsl.pc lleva rutas absolutas incrustadas hasta en
  # Libs/Cflags (sin derivar de ${prefix}) => cmake muere en el generate con
  # "Imported target ... includes non-existent path". 2 reglas: sufijo tras
  # <name> conserva su ruta relativa; sin sufijo => la raíz del prefijo.
  if [[ -d "$tmp/lib/pkgconfig" ]]; then
    find "$tmp/lib/pkgconfig" -name '*.pc' -type f | while read -r pc; do
      sed -i -E \
        -e 's|/home/runner[^[:space:]]*/staging/([[:alnum:]_.+-]+)/|\${pcfiledir}/../../|g' \
        -e 's|/home/runner[^[:space:]]*/staging/([[:alnum:]_.+-]+)|\${pcfiledir}/../..|g' \
        "$pc"
    done
    # gate: ni un absoluto del runner en el harvest
    if grep -rl '/home/runner' "$tmp/lib/pkgconfig" --include='*.pc' >/dev/null 2>&1; then
      log "ERROR: harvest $name dejó .pc con rutas absolutas del runner"
      exit 1
    fi
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

meson_build() { # meson_build <nombre> <srcdir> [--shared] [opts meson...]
  local name="$1" src="$2"; shift 2
  # --shared: SOLO la familia glib (build_glib) sale como .so; el resto de
  # tier2 sigue static. Flag explicito (en vez de -Ddefault_library=shared
  # suelto en "$@"): meson ya recibe --default-library=static antes y la
  # semantica de ultimo-gana para opciones repetidas no esta garantizada.
  local dl=static
  if [[ "${1:-}" == "--shared" ]]; then dl=shared; shift; fi
  rm -rf "$WORK/build-$name"
  # nofallback: que NINGUN proyecto vendee subprojects en silencio (fontconfig
  # se colo con freetype2). Si falta un .pc, peta aqui y lo arreglamos de raiz.
  meson setup "$WORK/build-$name" "$src" \
    --cross-file "$WORK/cross.ini" \
    --prefix="$STG/$name" --libdir=lib \
    --default-library="$dl" --buildtype=release \
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
  # real de 2.17.1; sentinel freetype2 '>= 21.0.15' lo cumple el shim 26.2.20.
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
  # --shared: glib/gobject/gio/gmodule salen como .so (modelo oficial
  # gtk-android-builder) -> libgtk-4.so y libinkscape_base.so dejan de
  # embeberse copias estaticas del runtime (doble-GLib/GType -> assert).
  local src
  src="$(extract "$(fetch "$U_GLIB")")"
  # g_set_user_dirs es '/*< private > */' en GLib (no esta en gutils.h, nose
  # declara publicamente): con -fvisibility=hidden (GLib lo activa en build
  # shared) el simbolo queda LOCAL/HIDDEN y NO se exporta en libglib-2.0.so.
  # GTK4 la declara por su cuenta y la usa (gdk/android/gdkandroidruntime.c)
  # -> 'undefined symbol: g_set_user_dirs' al enlazar libgtk-4.so contra la
  # .so (con la .a vieja se resolvia extrayendo el miembro). Fix: forzar
  # visibilidad default en la definicion (parche de fuente, patron del repo).
  sed -i 's|^g_set_user_dirs (const gchar \*first_dir_type,$|__attribute__((visibility("default")))\ng_set_user_dirs (const gchar *first_dir_type,|' \
    "$src/glib/gutils.c"
  grep -q '__attribute__((visibility("default")))' "$src/glib/gutils.c" || {
    echo "ERROR: parche de visibilidad g_set_user_dirs no aplicado" >&2; exit 1; }
  meson_build glib "$src" --shared \
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

  # --- FASE 6B: diferir commit de night-mode hasta liberar el latch ---------
  # (deadlock de inicializacion: update_night_mode emitia setting_changed +
  # notify dentro del runnable sincronizante de blockForMain; el hilo GTK
  # esperaba trabajo que solo puede completar el hilo principal, y este
  # esperaba el CountDownLatch => espera circular en el bind inicial.
  # F6 demostro que el g_idle corria con el latch aun bloqueado -> mismo
  # deadlock; en 6B el commit pendiente lo dispara Java (ToplevelActivity)
  # DESPUES de blockForMain, via runOnMain->commitPendingNightMode).
  python3 "$ROOT/patches/gtk4-nightmode-defer.py" "$src" \
    || { echo "ERROR: parche F6B nightmode-defer no aplico en gtk 4.22.5" >&2; exit 1; }
  grep -q 'F6B-NIGHT-PENDING' "$src/gdk/android/gdkandroiddisplay.c" \
    || { echo "ERROR: verificacion F6B-NIGHT-PENDING fallo en gdkandroiddisplay.c" >&2; exit 1; }
  grep -q 'F6B-BIND-BEGIN' "$src/gdk/android/gdkandroidtoplevel.c" \
    || { echo "ERROR: verificacion F6B-BIND-BEGIN fallo en gdkandroidtoplevel.c" >&2; exit 1; }
  grep -q 'commitPendingNightMode' "$src/gdk/android/gdkandroidinit.c" \
    || { echo "ERROR: registro JNI commitPendingNightMode fallo en gdkandroidinit.c" >&2; exit 1; }

  # --- FASE 13: tap simple estilo raton (click fiable con el dedo) ---
  # Sustituye a FASE 10/12: el dedo emula raton (press en DOWN, release en UP).
  # Correccion de slop (~12 css px) SOLO en el release: si el jitter fue
  # minimo, el release va en las coords del press -> GTK ve click limpio.
  # Sin long-press, sin double-click, sin tracking por pointer-id,
  # sin deferral del press. Solo click fiable para menús, tools, color picker.
  python3 "$ROOT/patches/gtk4-touch-as-pointer.py" "$src" \
    || { echo "ERROR: parche FASE13 touch-as-pointer no aplico en gtk 4.22.5" >&2; exit 1; }
  grep -q 'FASE13-DOWN' "$src/gdk/android/gdkandroidevents.c" \
    || { echo "ERROR: verificacion FASE13-DOWN fallo en gdkandroidevents.c" >&2; exit 1; }
  grep -q 'FASE13-UP' "$src/gdk/android/gdkandroidevents.c" \
    || { echo "ERROR: verificacion FASE13-UP fallo en gdkandroidevents.c" >&2; exit 1; }
  grep -q 'F13_SLOP' "$src/gdk/android/gdkandroidevents.c" \
    || { echo "ERROR: verificacion F13_SLOP fallo en gdkandroidevents.c" >&2; exit 1; }
  grep -q 'AMOTION_EVENT_TOOL_TYPE_FINGER' "$src/gdk/android/gdkandroidevents.c" \
    || { echo "ERROR: verificacion FASE13 finger-motion fallo en gdkandroidevents.c" >&2; exit 1; }
  ! grep -q 'gdk_touch_event_new' "$src/gdk/android/gdkandroidevents.c" \
    || { echo "ERROR: queda gdk_touch_event_new sin parchear en gdkandroidevents.c" >&2; exit 1; }
  ! grep -q 'g_touch_slop\b' "$src/gdk/android/gdkandroidevents.c" \
    || { echo "ERROR: FASE10B slop (g_touch_slop) sigue presente; FASE13 manda" >&2; exit 1; }

  # --- FASE 10C: fix NULL deref en el keymap android (crasheo al teclear) -----
  # Crash real (crash-stack.txt FASE8): TextTool::root_handler ->
  # get_latin_keyval_impl -> gdk_display_translate_key -> translate_keyboard_state
  # -> SIGSEGV. get_latin_keyval_impl (tool-base.cpp) pasa effective_group=NULL
  # y el backend android hacia `if (*effective_group)` (deref sin validar el OUT
  # param). Con el contrato GdkKeymap los OUT params son opcionales: se valida el
  # puntero como hace el resto del backend (if (level) ...).
  python3 "$ROOT/patches/gtk4-keymap-null-deref.py" "$src" \
    || { echo "ERROR: parche FASE10C keymap no aplico en gtk 4.22.5" >&2; exit 1; }
  grep -q 'FASE10C-KEYMAP' "$src/gdk/android/gdkandroidkeymap.c" \
    || { echo "ERROR: verificacion FASE10C-KEYMAP fallo en gdkandroidkeymap.c" >&2; exit 1; }
  ! grep -q 'if (\*effective_group)' "$src/gdk/android/gdkandroidkeymap.c" \
    || { echo "ERROR: queda el deref NULL sin arreglar en gdkandroidkeymap.c" >&2; exit 1; }

  meson_build gtk4 "$src" \
    -Dandroid-backend=true -Dandroid-runtime=enabled \
    -Dx11-backend=false -Dwayland-backend=false -Dbroadway-backend=false \
    -Dintrospection=disabled -Ddocumentation=false -Dman-pages=false \
    -Dbuild-demos=false -Dbuild-testsuite=false -Dbuild-examples=false \
    -Dbuild-tests=false \
    -Dvulkan=disabled -Dmedia-gstreamer=disabled -Daccesskit=disabled
}

build_sigcpp() {
  # 3.6.0: Inkscape exige sigc++-3.0>=3.6 (DefineDependsandFlags.cmake:449),
  # glibmm pide >=3.0.0 => minimo oficial exacto. meson.options REALES de 3.6.0:
  # build-examples/build-tests/validation vienen en true (los apagamos; validation
  # solo busca xmllint/docbook) y maintainer-mode=if-git-build => false en tarball
  # (sin mm-common-get, sin gmmproc). NO inventar flags: los tres estan verificados.
  meson_build sigc++ "$(extract "$(fetch "$U_SIGCPP")")" \
    -Dbuild-examples=false -Dbuild-tests=false -Dvalidation=false
}

build_glibmm() {
  # build-documentation (combo) ya desactivado en tarball (if-maintainer-mode);
  # OJO: aqui NO existe build-tests (no inventarlo)
  local src ct n
  src="$(extract "$(fetch "$U_GLIBMM")")"

  # --- parche glibmm#118 (run #20) ------------------------------------------
  # contenttype.cc define content_type_guess(..., const std::basic_string<guchar>&, ...)
  # que el header YA no declara (commit upstream 84135b93); su cuerpo usa
  # data.c_str()/data.size() => instancia std::basic_string<unsigned char> =>
  # libc++ (NDK) NO define char_traits<unsigned char> (solo libstdc++ lo tolera
  # con su plantilla primaria generica) => run #20 murio en contenttype.cc:93:
  #   implicit instantiation of undefined template 'std::char_traits<unsigned char>'
  # Fix = el MISMO de upstream (issue glibmm#118, "clang 19 no le gusta la
  # version completa"): stub que no toca data. Dry-run local verificado: el .cc
  # queda IDENTICO a upstream master (salvo su bloque de comentario).
  ct="$src/gio/giomm/contenttype.cc"
  n=$(grep -c 'std::basic_string<guchar>& data' "$ct" || true)
  [[ "$n" == "1" ]] || { echo "ERROR: firma inesperada en contenttype.cc (n=$n); re-auditar parche glibmm#118" >&2; exit 1; }
  python3 - "$ct" <<'PY' || { echo "ERROR: parche glibmm#118 fallo" >&2; exit 1; }
import sys
p = sys.argv[1]
s = open(p).read()
sig_old = "const std::string& filename, const std::basic_string<guchar>& data, bool& result_uncertain)"
sig_new = "const std::string& /*filename*/, const std::basic_string<guchar>& /*data*/, bool& result_uncertain)"
body_old = """{
  gboolean c_result_uncertain = FALSE;
  const gchar* c_filename = filename.empty() ? nullptr : filename.c_str();
  gchar* cresult = g_content_type_guess(c_filename, data.c_str(), data.size(), &c_result_uncertain);
  result_uncertain = c_result_uncertain;
  return Glib::convert_return_gchar_ptr_to_ustring(cresult);
}"""
body_new = """{
  result_uncertain = true;
  return Glib::ustring();
}"""
if s.count(sig_old) != 1 or s.count(body_old) != 1:
    sys.exit("coincidencias firma=%d cuerpo=%d (esperado 1/1)" % (s.count(sig_old), s.count(body_old)))
open(p, "w").write(s.replace(sig_old, sig_new).replace(body_old, body_new))
print("glibmm: overload content_type_guess parcheado (upstream issue #118)")
PY
  grep -qF 'basic_string<guchar>& /*data*/' "$ct" || { echo "ERROR: firma nueva no quedo aplicada" >&2; exit 1; }
  # el cuerpo viejo debe desaparecer; el overload std::string usa el cast
  # (const guchar*)data.c_str() => NO debe empatar este gate
  if grep -qF 'g_content_type_guess(c_filename, data.c_str()' "$ct"; then
    echo "ERROR: cuerpo viejo de content_type_guess sigue presente" >&2; exit 1
  fi

  meson_build glibmm "$src" -Dbuild-examples=false
  # pangomm y gtkmm hacen find_library('glibmm_generate_extra_defs-2.68',
  # required:true) => si falta esta lib, SUS setups mueren. Compuerta ruidosa.
  ls "$ROOT/glibmm/lib/"libglibmm_generate_extra_defs* >/dev/null 2>&1 || {
    echo "ERROR: falta libglibmm_generate_extra_defs* en glibmm/lib (lo exigen pangomm/gtkmm)" >&2
    exit 1
  }
}

build_cairomm() {
  # cairomm 1.15.4 es SOLO autotools: trae configure/Makefile.in pero NO
  # meson.build (meson_build moria con "no build file meson.build") => at_build.
  # configure real: unica AC_ARG_ENABLE = tests (default NO, sin boost) y los
  # examples solo se construyen con `make check` => sin flags de features;
  # --disable-documentation salta entero el bloque de mm-common (solo doxygen).
  # 0 .ccg en el tarball => sin gmmproc ni m4. Deps: cairo>=1.10 (1.18.6) +
  # sigc++-3.0>=2.5.1 (3.6.0, ya cosechada antes en TIER2).
  at_build cairomm "$(extract "$(fetch "$U_CAIROMM")")" --disable-documentation
}

build_pangomm() {
  # sin build-tests/build-examples en sus opciones => sin flags
  meson_build pangomm "$(extract "$(fetch "$U_PANGOMM")")"
}

build_gtkmm() {
  local src ih n
  src="$(extract "$(fetch "$U_GTKMM")")"

  # --- parche skew gtkmm-4.14.0 vs gtk4.22.5 (run #21) ----------------------
  # gmmproc pre-genero untracked/gtk/gtkmm/iconpaintable.h pensando que
  # GtkIconPaintable era DERIVABLE y forward-declara la clase:
  #   using GtkIconPaintableClass = struct _GtkIconPaintableClass;
  # pero gtk4.22.5 ya la declara FINAL => G_DECLARE_FINAL_TYPE define
  #   typedef struct { GObjectClass parent_class; } GtkIconPaintableClass;
  # (struct ANONIMO) => tipos distintos => run #21 murio en wrap_init.cc:
  #   typedef redefinition with different types ('struct _GtkIconPaintableClass'
  #   vs 'struct GtkIconPaintableClass')
  # (gtk 4.14 la tenia derivable — por eso gtkmm 4.14 compila en escritorio;
  # gtk la convirtio a final entre 4.15 y 4.22.)
  # Barrido de la clase sobre los arbolles REALES (ojo: gdk/ y gsk/ viven
  # dentro de gtk4/include/gtk-4.0/, NO como gdk-4.0/gsk-4.0 — el primer
  # escaneo los omitio): 66 tipos FINALES (gtk 59, gsk 1, gdk 0) vs 246
  # using-lines de gtkmm+gdkmm pre-generados => UNICO caso GtkIconPaintable.
  # Fix: borrar la using-line de Clase e insertar '#include <gtk/gtk.h>' ANTES
  # del bloque DOXYEN (mismo patron que alertdialog.h:31 y las31 cabeceras que
  # ya compilan): el typedef de Clase sale de gtk, la instance-using (struct
  # _GtkIconPaintable) sigue y es del MISMO tipo que declara
  # G_DECLARE_FINAL_TYPE => redeclaracion legal, y private/iconpaintable_p.h
  # (BaseClassType) se beneficia via iconpaintable.cc -> iconpaintable.h.
  # OJO (run #22): NO servia '#include <gtk/gtkiconpaintable.h>' — gtk4 tiene
  # single-include check y aborta con '#error "Only <gtk/gtk.h> can be
  # included directly."'; por eso el upstream son <gtk/gtk.h> tambien.
  # (En wrap_init.cc NO exploto porque ahi gtk.h ya venia via alertdialog.h.)
  ih="$src/untracked/gtk/gtkmm/iconpaintable.h"
  n=$(grep -c '^using GtkIconPaintableClass = struct _GtkIconPaintableClass;$' "$ih" || true)
  [[ "$n" == "1" ]] || { echo "ERROR: anchor using-class en iconpaintable.h n=$n (cambio upstream; re-auditar skew gtkmm/gtk4)" >&2; exit 1; }
  n=$(grep -c '^#include <giomm/file.h>$' "$ih" || true)
  [[ "$n" == "1" ]] || { echo "ERROR: anchor giomm/file.h n=$n en iconpaintable.h" >&2; exit 1; }
  n=$(grep -c '^#include <gtk/gtk\.h>' "$ih" || true)
  [[ "$n" == "0" ]] || { echo "ERROR: iconpaintable.h ya trae gtk.h (n=$n); patron cambio, re-auditar" >&2; exit 1; }
  sed -i '/^using GtkIconPaintableClass = struct _GtkIconPaintableClass;$/d' "$ih"
  sed -i '/^#include <giomm\/file.h>$/a #include <gtk/gtk.h> // skew: gtkmm-4.14.0 genero esta clase como derivable; gtk4.22 la declara FINAL' "$ih"
  if grep -q 'using GtkIconPaintableClass = struct' "$ih"; then
    echo "ERROR: using-class de GtkIconPaintable sigue presente tras el parche" >&2; exit 1
  fi
  if grep -q '#include <gtk/gtkiconpaintable\.h>' "$ih"; then
    echo "ERROR: include suelto de gtkiconpaintable.h (gtk lo prohibe: 'Only <gtk/gtk.h>')" >&2; exit 1
  fi
  [[ "$(grep -c '^#include <gtk/gtk\.h>' "$ih")" == "1" ]] || {
    echo "ERROR: include <gtk/gtk.h> no quedo exactamente 1 vez" >&2; exit 1
  }
  [[ "$(grep -c 'using GtkIconPaintable = struct' "$ih")" == "1" ]] || {
    echo "ERROR: instance-using de GtkIconPaintable alterada" >&2; exit 1
  }

  meson_build gtkmm "$src" \
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
