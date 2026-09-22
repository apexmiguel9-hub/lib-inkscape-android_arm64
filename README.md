# lib-inkscape-android_arm64

Libs **precompiladas para Android arm64 (API 31, NDK r30, estáticas)** de las ~25
dependencias que **Inkscape exige y `lib-android_arm64` oficial de Blender NO trae**.

Este repo existe para el port de **Inkscape a Android**
(<https://github.com/apexmiguel9-hub>). El port completo del renderer (Cairo/2geom)
es portable tal cual; GTK4 corre con su backend Android oficial (≥4.18). Lo que falta
compilar es justo este stack GNOME + utilidades que Blender jamás usa.

## Por qué

`CMakeScripts/DefineDependsandFlags.cmake` de Inkscape busca TODO por
`pkg_check_modules(REQUIRED)` / `find_package(REQUIRED)`:

- `fontconfig`, `bdw-gc`, `lcms2`, `icu-uc`, `Iconv`, `Intl`, `GSL`,
  `double-conversion`, `LibXslt`, `harfbuzz`, `pangocairo`, `pangoft2`, `gmodule-2.0`
- bloque mm: `cairomm-1.16`, `pangomm-2.48`, `gdk-pixbuf-2.0`, `graphene-1.0`,
  `gtk4>=4.14`, `glibmm-2.68>=2.78.1`, `gtkmm-4.0>=4.13.3`
- `find_package(LibXml2 REQUIRED)`, `find_package(Potrace REQUIRED)` (módulo propio)

Blender solo trae (reutilizables, ver `deps.md`): zlib, png, jpeg, webp, openjpeg,
freetype, harfbuzz, fribidi, xml2, epoxy, potrace, python 3.13, zstd. **No trae ni
un solo archivo `.pc`** (su build usa rutas CMake) → este repo genera los shims.

## Layout

Idéntico al de `projects.blender.org/blender/lib-android_arm64` para poder fusionar
los dos trees como un solo prefix:

```
<lib>/include/...
<lib>/lib/*.a
<lib>/lib/pkgconfig/*.pc   (reubicados con prefix=${pcfiledir}/../.. → relocatables)
pc-overlay/*.pc            (shims para las libs de Blender; NO se commitean)
```

## Cómo se construyen

Actions → workflow **`build-libs`** (`workflow_dispatch`, input `libs` =
`tier1` | `tier2` | `all` | lista):

1. Clona `lib-android_arm64` oficial (misma receta que
   `blender_wanderson_android/.github/workflows/build-android.yml`:
   `ls-remote`→clave de cache, `--depth 1`, `git lfs pull`, verificación de tamaño).
2. `scripts/gen-pc.sh` genera los `.pc` shim de esas libs.
3. NDK `r30` (fallback `r30-beta1`, la que usa Blender), cross a
   `aarch64-linux-android31`, `build/build.sh`.
4. Cosecha a carpetas → commit/push (con retry).

## Consumo (borrador del yml del port de Inkscape)

```yaml
- run: git clone --depth 1 https://projects.blender.org/blender/lib-android_arm64.git .blender-libs
      cd .blender-libs && git lfs install && git lfs pull
- run: git clone --depth 1 https://github.com/apexmiguel9-hub/lib-inkscape-android_arm64.git .ink-libs
      ./.ink-libs/scripts/gen-pc.sh "$PWD/.blender-libs" "$PWD/pc-overlay"
- env:
    PKG_CONFIG_LIBDIR: ${{ join(find .ink-libs pc-overlay -name pkgconfig -type d), ':' }}
    CMAKE_PREFIX_PATH: ${{ primer nivel de .ink-libs + .blender-libs }}
```

Todos los `.a` son estáticas → todo se empaqueta en `libinkscape.so` del APK.

## Stages

| Stage | Contenido | Estado |
|---|---|---|
| tier1 | atomic_ops, libiconv, gettext, libffi, pcre2, expat, bdw-gc, lcms2, ICU, GSL, double-conversion, pixman, libxslt, boost | implementado |
| tier2 | glib → cairo → gdk-pixbuf → fontconfig → pango → graphene → GTK4 (`-Dandroid-backend -Dandroid-runtime`) → sigc++/glibmm/cairomm/pangomm/gtkmm | pendiente (siguiente ronda) |
| tier3 | poppler, libwpg, libvisio, libcdr, gtksourceview-5, libspelling, tiff | OFF en primera pasada |

Nota: Inkscape trae fallbacks `ExternalProject` que intentan bajar glibmm/gtkmm y
compilarlos para el **host** → se evitan proveyendo todos los `.pc` desde tier2.

## Riesgos conocidos

1. **Boost `stacktrace_basic` en bionic**: `execinfo.h`/`backtrace()` no existen en
   Android → si `basic.cpp` no compila, hace falta un mínimo
   `if(ANDROID)` en `DefineDependsandFlags.cmake` (o stub de la lib).
2. **Deps estáticas transitivas**: `pkg_check_modules` sin `STATIC` no repasa
   `Libs.private` → al link final de Inkscape añadir safety-net
   (`-DCMAKE_SHARED_LINKER_FLAGS="-lz -lpng16 -lm..."`).
3. **fontconfig en Android**: `fonts.conf` → `/system/fonts`, caché en un dir
   escribible de la app (etapa APK).
4. **gdk-pixbuf loaders**: módulos vs builtin + cache (etapa imports de imagen).
5. **NDK**: oficial Blender se compiló con `r30-beta1`; si aparece mismatch de
   símbolos libc++ (`std::__ndk1::*`), bajar a `r30-beta1`.
6. **Python**: el CMake de Inkscape no busca Python (solo runtime) → la Python 3.13
   de Blender se empaqueta en el APK para las extensiones.

## Créditos

Recetas adaptadas de
[`blender_for_android`](https://github.com/dexapex377-coder/blender_wanderson_android)
(`build_files/android/deps/build.sh` — Wanderson M. Pimenta / Simfeo); versiones
cross-checkeadas contra `deps.md` de `projects.blender.org/blender/lib-android_arm64`
y contra los tarballs reales (ver `deps.md`).
