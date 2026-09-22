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
U_LIBXSLT="https://download.gnome.org/sources/libxslt/1.1/libxslt-1.1.45.tar.xz"
U_BOOST="https://archives.boost.io/release/1.87.0/source/boost_1_87_0.tar.bz2"

TIER1=(atomic_ops libiconv gettext libffi pcre2 expat bdw-gc lcms2 icu gsl double-conversion pixman libxslt boost)
TIER2=(glib cairo gdk-pixbuf fontconfig pango graphene gtk4 sigc++ glibmm cairomm pangomm gtkmm)

# solo las libs de blender que realmente usamos (evita colisiones de headers)
BLENDER_WANT=(zlib png jpeg freetype harfbuzz fribidi xml2 epoxy potrace webp openjpeg zstd)

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
sys_root = '$TC/sysroot'
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
  meson setup "$WORK/build-$name" "$src" \
    --cross-file "$WORK/cross.ini" \
    --prefix="$STG/$name" --libdir=lib \
    --default-library=static --buildtype=release \
    "$@"
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

# ---------------------------------------------------------------- tier2 (pendiente)
pendiente() {
  echo "RECETA PENDIENTE: '$1' — el tier2 (glib→gtkmm) se añade cuando tier1 esté verde." >&2
  exit 3
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
    glib|cairo|gdk-pixbuf|fontconfig|pango|graphene|gtk4|sigc++|glibmm|cairomm|pangomm|gtkmm)
      pendiente "$1" ;;
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
    tier2) pendiente "tier2 (grupo)" ;;
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
