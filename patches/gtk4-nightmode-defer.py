#!/usr/bin/env python3
# FASE 6 - fix minimo del deadlock de inicializacion GTK4-android (gtk 4.22.5).
#
# Mecanismo del deadlock (confirmado en FASE 5, dispositivo Moto g56):
#   _gdk_android_toplevel_bind_native() corre dentro del runnable
#   sincronizante de GlibContext.blockForMain(), que mantiene al hilo
#   principal de Android esperando en un CountDownLatch. Al final de ese
#   bind, gdk_android_display_update_night_mode() emite de forma reentrante
#   gdk_display_setting_changed() + g_object_notify_by_pspec("night-mode");
#   la cadena de notificacion (night_mode_changed -> update_window ->
#   postWindowConfiguration, y el arranque de GtkSettings/theme) necesita
#   trabajo que solo puede completar el hilo principal, que esta bloqueado
#   esperando a que este MISMO runnable termine => espera circular: bind
#   nunca retorna y el CountDownLatch nunca se libera.
#
# Fix: mientras el bind inicial esta activo (android_bind_depth > 0), el
# commit de night-mode (asignacion + setting_changed + notify) se difiere a
# un idle del main context de GLib; se aplica cuando el runnable ya termino,
# el latch fue liberado y el hilo principal puede avanzar. Sin cambios de
# API: solo control de flujo + un idle, sin tocar nada mas del backend.
#
# Uso: python3 gtk4-nightmode-defer.py <srcdir-gtk-4.22.5>
#   Aplica 4 sustituciones exactas (1 coincidencia cada una) y aborta si
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
/* FASE 6: diferir el commit de night-mode fuera de la seccion critica del
 * bind inicial. Mientras _gdk_android_toplevel_bind_native corre dentro del
 * runnable sincronizante de GlibContext.blockForMain (el hilo principal de
 * Android esperando el CountDownLatch), emitir gdk_display_setting_changed /
 * g_object_notify de forma reentrante puede bloquear al hilo GTK esperando
 * trabajo que solo puede completar el hilo principal (espera circular).
 * El commit se difiere a un idle del main context y se aplica cuando el
 * runnable ya termino y el latch fue liberado.
 */
static guint android_bind_depth = 0;
static GdkAndroidDisplayNightMode night_mode_pending = GDK_ANDROID_DISPLAY_NIGHT_UNDEFINED;
static guint night_mode_pending_idle = 0;

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

static gboolean
gdk_android_display_night_mode_pending_cb (gpointer user_data)
{
  GdkAndroidDisplay *self = GDK_ANDROID_DISPLAY (user_data);

  night_mode_pending_idle = 0;
  g_message ("F6-CONFIG-RUN commit night-mode diferido (mode=%d)", night_mode_pending);
  gdk_android_display_set_night_mode (self, night_mode_pending);
  night_mode_pending = GDK_ANDROID_DISPLAY_NIGHT_UNDEFINED;
  g_object_unref (self);

  return G_SOURCE_REMOVE;
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

  if (android_bind_depth > 0 || night_mode_pending_idle > 0)
    {
      /* commit pendiente: el ultimo valor gana; el idle lo aplica fuera del
       * runnable sincronizante (sin reentrancia hacia el hilo principal). */
      night_mode_pending = night_mode;
      if (night_mode_pending_idle == 0)
        {
          night_mode_pending_idle = g_idle_add_full (G_PRIORITY_DEFAULT_IDLE,
                                                     gdk_android_display_night_mode_pending_cb,
                                                     g_object_ref (self), NULL);
          g_message ("F6-CONFIG-DEFER commit night-mode diferido (idle %u)", night_mode_pending_idle);
        }
      else
        {
          g_message ("F6-CONFIG-DEFER valor night-mode actualizado (idle ya pendiente)");
        }
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
  g_message ("F6-BIND-BEGIN bind inicial de toplevel %p (seccion critica activa)", self);

  (*env)->CallVoidMethod (env, this, gdk_android_get_java_cache ()->toplevel.attach_toplevel_surface);

  gdk_android_toplevel_update_title (self);
  gdk_android_toplevel_update_window (self);

  gdk_android_display_update_night_mode (display, this);

  g_message ("F6-BIND-END bind inicial terminado (%p)", self);
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
        (OLD_HDR, NEW_HDR, "prototypes begin/end bind"),
    ])

    print("OK: gtk4-nightmode-defer aplicado sobre %s" % base)