#!/usr/bin/env python3
# FASE 6B - fix minimo del deadlock de inicializacion GTK4-android (gtk 4.22.5).
#
# Mecanismo del deadlock (confirmado en FASE 5 y 6, dispositivo Moto g56):
#   _gdk_android_toplevel_bind_native() corre dentro del runnable
#   sincronizante de GlibContext.blockForMain(), que mantiene al hilo
#   principal de Android esperando en un CountDownLatch. Emitir el commit de
#   night-mode (gdk_display_setting_changed + g_object_notify_by_pspec) con
#   el hilo principal aun bloqueado en el latch es una espera circular: la
#   cadena de notificacion (night_mode_changed -> update_window ->
#   postWindowConfiguration) necesita trabajo del hilo principal, que no
#   avanza hasta que este runnable retorne.
#
# FASE 6 diferia el commit a un g_idle del main context: el bind ya termina,
# PERO el idle corre apenas retorna el bind, cuando el latch todavia no se
# libero (el runnable de la activity por am-start aun esta en cola), y la
# cadena de notificacion se traba igual -> main context muerto, latch sin
# liberar, splash infinito (F6-BIND-END ... F6-CONFIG-RUN ... solo eso).
#
# Fix FASE 6B (un cambio minimo, sin arquitectura nueva):
#   * Durante el bind inicial (android_bind_depth > 0) el cambio de
#     night-mode SOLO se marca pendiente (night_mode_pending, ultimo valor
#     gana). NO se programa ningun idle -> el main context sigue vivo.
#   * El commit real (setting_changed + notify) lo dispara Java
#     (ToplevelActivity.onCreate) DESPUES de blockForMain(), con el latch ya
#     liberado, via GlibContext.runOnMain() ->
#     gdk_android_display_commit_pending_night_mode() (registrado como
#     metodo nativo "commitPendingNightMode" en GlibContext).
#   * El commit consume el pendiente antes de emitir: no-op si no hay valor
#     pendiente (permite N activities llamandolo; no hay doble notify).
#   * Fuera del bind (config changes posteriores) el commit es directo,
#     como en el backend original.
#
# Uso: python3 gtk4-nightmode-defer.py <srcdir-gtk-4.22.5>
#   Aplica sustituciones exactas (1 coincidencia cada una) y aborta si
#   cualquier texto esperado no aparece exactamente una vez.

import os
import sys


def patch_one(path, replacements):
    s = open(path, encoding="utf-8").read()
    for old, new, name in replacements:
        n = s.count(old)
        if n != 1:
            sys.exit("gtk4-nightmode-defer: '%s' count=%d (esperado 1) en %s"
                     % (name, n, path))
        s = s.replace(old, new)
    open(path, "w", encoding="utf-8").write(s)
    print("patched %s" % path)


# ---------------------------------------------------------------------------
# gdk/android/gdkandroiddisplay.c
# ---------------------------------------------------------------------------
FN_HEADER = """\
void
gdk_android_display_update_night_mode (GdkAndroidDisplay *self, jobject context)
{
"""

PREAMBLE = """\
/* FASE 6B: diferir el commit de night-mode hasta que el latch de
 * blockForMain este liberado. FASE 6 lo diferia a un g_idle del main
 * context, pero el idle corre apenas termina el bind, con el hilo principal
 * aun bloqueado en el CountDownLatch: la cadena de notificacion
 * (night_mode_changed -> update_window -> postWindowConfiguration)
 * necesita el hilo principal libre y se traba igual. En FASE 6B el cambio
 * se marca pendiente durante el bind (sin idle; el main context sigue
 * vivo) y el commit real se dispara desde Java (ToplevelActivity.onCreate)
 * DESPUES de blockForMain(), con el latch ya liberado, via
 * gdk_android_display_commit_pending_night_mode().
 */
static guint android_bind_depth = 0;
static GdkAndroidDisplayNightMode night_mode_pending = GDK_ANDROID_DISPLAY_NIGHT_UNDEFINED;

static void
gdk_android_display_set_night_mode (GdkAndroidDisplay *self,
                                    GdkAndroidDisplayNightMode night_mode)
{
  if (self->night_mode == night_mode)
    return;

  self->night_mode = night_mode;
  g_debug ("night mode changed");
  gdk_display_setting_changed ((GdkDisplay *) self, "gtk-application-prefer-dark-theme");
  g_object_notify_by_pspec ((GObject *) self, obj_properties[PROP_NIGHT_MODE]);
}

void
gdk_android_display_commit_pending_night_mode (void)
{
  GdkAndroidDisplay *display = gdk_android_display_get_display_instance ();

  if (night_mode_pending == GDK_ANDROID_DISPLAY_NIGHT_UNDEFINED)
    return;

  GdkAndroidDisplayNightMode pending = night_mode_pending;
  night_mode_pending = GDK_ANDROID_DISPLAY_NIGHT_UNDEFINED;

  g_message ("F6B-NIGHT-COMMIT-BEGIN commit night-mode pendiente (mode=%d)", pending);
  gdk_android_display_set_night_mode (display, pending);
  g_message ("F6B-NIGHT-COMMIT-END");
}

void
gdk_android_display_begin_bind (void)
{
  android_bind_depth++;
}

void
gdk_android_display_end_bind (void)
{
  if (android_bind_depth > 0)
    android_bind_depth--;
}

"""

OLD_TAIL = """\
  if (self->night_mode == night_mode)
    return;
  self->night_mode = night_mode;
  g_debug ("night mode changed");
  gdk_display_setting_changed ((GdkDisplay *) self, "gtk-application-prefer-dark-theme");
  g_object_notify_by_pspec ((GObject *) self, obj_properties[PROP_NIGHT_MODE]);
}
"""

NEW_TAIL = """\
  if (self->night_mode == night_mode)
    return;

  if (android_bind_depth > 0)
    {
      /* arranque en curso: el hilo principal sigue bloqueado en el latch de
       * blockForMain hasta que este bind retorne. Solo marcar pendiente (el
       * ultimo valor gana); el commit real lo dispara Java tras liberar el
       * latch (gdk_android_display_commit_pending_night_mode). Nada de
       * idle: el main context debe seguir despachando runnables. */
      night_mode_pending = night_mode;
      g_message ("F6B-NIGHT-PENDING night-mode pendiente (mode=%d)", night_mode);
      return;
    }

  gdk_android_display_set_night_mode (self, night_mode);
}
"""

# ---------------------------------------------------------------------------
# gdk/android/gdkandroidtoplevel.c
# ---------------------------------------------------------------------------
OLD_BIND = """\
  (*env)->CallVoidMethod (env, this, gdk_android_get_java_cache ()->toplevel.attach_toplevel_surface);

  gdk_android_toplevel_update_title (self);
  gdk_android_toplevel_update_window (self);

  gdk_android_display_update_night_mode (display, this);
}
"""

NEW_BIND = """\
  gdk_android_display_begin_bind ();
  g_message ("F6B-BIND-BEGIN bind inicial de toplevel %p (seccion critica activa)", self);

  (*env)->CallVoidMethod (env, this, gdk_android_get_java_cache ()->toplevel.attach_toplevel_surface);

  gdk_android_toplevel_update_title (self);
  gdk_android_toplevel_update_window (self);

  gdk_android_display_update_night_mode (display, this);

  g_message ("F6B-BIND-END bind inicial terminado (%p)", self);
  gdk_android_display_end_bind ();
}
"""

# ---------------------------------------------------------------------------
# gdk/android/gdkandroiddisplay-private.h
# ---------------------------------------------------------------------------
OLD_HDR = """\
void gdk_android_display_update_night_mode (GdkAndroidDisplay *self, jobject context);
"""

NEW_HDR = """\
void gdk_android_display_update_night_mode (GdkAndroidDisplay *self, jobject context);

void gdk_android_display_begin_bind (void);
void gdk_android_display_end_bind (void);
void gdk_android_display_commit_pending_night_mode (void);
"""

# ---------------------------------------------------------------------------
# gdk/android/gdkandroidinit.c  (registro JNI: commitPendingNightMode)
# ---------------------------------------------------------------------------
OLD_INIT = """\
static const JNINativeMethod glib_context_natives[] = {
  { .name = "runOnMain", .signature = "(Ljava/lang/Runnable;)V", .fnPtr = _gdk_android_glib_context_run_on_main }
};
"""

NEW_INIT = """\
static void
_gdk_android_glib_context_commit_pending_night_mode (JNIEnv *env, jclass this)
{
  gdk_android_display_commit_pending_night_mode ();
}

static const JNINativeMethod glib_context_natives[] = {
  { .name = "runOnMain", .signature = "(Ljava/lang/Runnable;)V", .fnPtr = _gdk_android_glib_context_run_on_main },
  { .name = "commitPendingNightMode", .signature = "()V", .fnPtr = _gdk_android_glib_context_commit_pending_night_mode }
};
"""


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("uso: python3 gtk4-nightmode-defer.py <srcdir-gtk-4.22.5>")
    base = sys.argv[1]

    patch_one(os.path.join(base, "gdk/android/gdkandroiddisplay.c"), [
        (FN_HEADER, PREAMBLE + FN_HEADER, "header update_night_mode"),
        (OLD_TAIL, NEW_TAIL, "tail commit update_night_mode"),
    ])
    patch_one(os.path.join(base, "gdk/android/gdkandroidtoplevel.c"), [
        (OLD_BIND, NEW_BIND, "bind_native seccion critica"),
    ])
    patch_one(os.path.join(base, "gdk/android/gdkandroiddisplay-private.h"), [
        (OLD_HDR, NEW_HDR, "prototypes begin/end/commit bind"),
    ])
    patch_one(os.path.join(base, "gdk/android/gdkandroidinit.c"), [
        (OLD_INIT, NEW_INIT, "registro JNI commitPendingNightMode"),
    ])

    print("OK: gtk4-nightmode-defer (FASE 6B) aplicado sobre %s" % base)