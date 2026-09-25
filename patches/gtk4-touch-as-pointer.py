#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FASE 12: gestos de toque estilo Blender (port de Wanderson, GHOST_SystemAndroid)
en el backend android de GTK: dedo primario = puntero con click FIABLE.

FASE 10 emulaba el dedo como raton emitiendo el press EN el DOWN y el release
en la posicion final; FASE 10B anclaba los MOTION al punto de press hasta 8 css
px. El micro-movimiento del dedo REAL supera ese slop (jitter de ~10-20px),
asi que GTK veia "press en A, release en B" en un tap fisico => lo trataba como
drag => los taps con el dedo NO abrian menus ni botones (solo los de adb, que
no generan MOVE, producian click limpio).

FASE 12 importa el modelo del port de Blender para Android:
  * DOWN      -> NO se emite nada: solo se registra el gesto (pending) y donde
                 aterrizo el dedo (Blender: touch_pending_ + touch_down_*).
  * MOVE      -> jitter <= slop: NO se emite nada. > slop: se entrega el press
                 en el punto DONDE ATERRIZO el dedo y el motion sigue al dedo
                 (drag/dibujo genuino; Blender: touchSendButton en el down point).
  * UP (tap)  -> click en el punto de aterrizaje (fix de los taps fisicos;
                 Blender: UP con touch_pending_ => down+up en el down).
  * Stylus    -> press al contacto, sin deferral (Blender: el stylus no
                 participa del dedo diferido).

FASE 12.1 (device g56): el digitizador DOBLE-REPORTA cada tap fisico (~60 ms de
pc 1->2->1) y Android baraja los indices de puntero al irse/venir un contacto
(tras el P_UP de nuestro dedo, el stream sigue con la POSICION del otro dedo
bajo el indice 0). Por eso:
  * el gesto se rastrea por ID de puntero (estable), no por indice: gidx se
    resuelve en cada evento buscando nuestro pointer_id; con un 2o contacto en
    la secuencia NO se cancela el pending ('cancel pc>=2' dejaba muerto todo
    tap) y el slop->drag SOLO se clasificaba con pc==1 (stream fiable).
  * el gesto termina en el POINTER_UP de NUESTRO dedo (el ACTION_UP final no
    llega si queda otro contacto abajo): si pending => TAP en el aterrizaje;
    si arrastraba => release en la ultima posicion conocida.

FASE 12.2 (g56, feedback del device):
  * CLICK REAL-TIMED: el tap ya no entrega press+release PEGADOS (mismo
    instante, mismo timestamp, misma iteracion del main loop): en g56 eso
    dejaba botones ARMA DOS (p.ej. los GtkToggleToolButton de la caja de tools
    que nunca "clickeaban" => no cambiaba de tool) y rangos GtkRange en estado
    de drag/repeat infinito (un click en el trough de una scrollbar => "se
    queda sostenida y moviendose" hasta que otro gesto la descoloca). Ahora el
    press se entrega en el UP del dedo y el release llega ~FASE12_TAP_RELEASE_MS
    (15 ms) despues, con timestamp de monotonic (forma real-timed, la misma con
    la que los taps de adb en FASE10/11 SI funcionaban).
  * SIN long-press: se elimina el click derecho por mantener presionado
    (peticion explicita del usuario; su workaround hold+click dependia de el,
    pero prefiere quitar el menu de contexto accidental). Se conserva la ref
    fuerte anti-dangling al target durante el gesto y para el release diferido.
  * DOBLE-CLICK tolerante al dedo: GtkGestureClick cuenta clicks consecutivos
    por TIMEOUT (gtk-double-click-time ~400 ms) y para devices TOUCHSCREEN NO
    aplica la distancia de doble-click (solo MOUSE). Con el release real-timed,
    dos taps rapidos sobre templates / recientes / file-chooser (GtkListBox:
    row-activated en el 2o PRESS) ya activan el elemento.
  * DRAG con pc>=2: se quita el gate pointers==1 del slop->drag: el swipe con
    el pulgar de apoyo abajo (pc=2 sostenido es lo NORMAL en g56) clasifica
    drag usando las coords de NUESTRO puntero (estables por pointer id).

Se conserva FASE 11C-ROUTE (ruteo determinista por geometria sobre
popup_bounds SINCRONO + target pegajoso por gesto): el tap sobre un item de
menu entrega el click al GdkAndroidPopup bajo el dedo => los menus PopoverMenuBar
NO se cierran al tocar (bug 1), y el color picker de F&S recibe el click (bug 2).

Los dedos adicionales (POINTER_DOWN / contacts extras) se ignoran (reservados
para pinch/pan en una fase futura): no cancelan el pending ni emiten nada.

Uso (desde build.sh):
  python3 "$ROOT/patches/gtk4-touch-as-pointer.py" "$src"
Donde $src es el arbol fuente de gtk descargado por fetch()/extract() (4.22.5).
Este parche SUSTITUYE a gtk4-touch-slop.py (FASE 10B): el slop queda integrado
en el modelo diferido (FASE12_SLOP); NO aplicar gtk4-touch-slop.py despues.
"""
import sys

SRC_REL = "gdk/android/gdkandroidevents.c"

OLD = [
    "  if (GDK_ANDROID_EVENTS_COMPARE_MASK (src, AINPUT_SOURCE_TOUCHSCREEN))",
    "    {",
    "      // I think it might be better to drop the down time and only rely on the event identity",
    "      guint base_sequence = gdk_android_surface_long_hash ((guint64) AMotionEvent_getDownTime (event));",
    "      base_sequence ^= (guint) event_identifier;",
    "",
    "      size_t pointers = AMotionEvent_getPointerCount (event);",
    "      for (size_t i = 0; i < pointers; i++)",
    "        {",
    "          GdkEventType ev_type = gdk_android_events_touch_action_to_gdk (event, i);",
    "",
    "          guint sequence = base_sequence ^ gdk_android_events_int_hash(AMotionEvent_getPointerId (event, i));",
    "          gfloat x = AMotionEvent_getX (event, i) / surface->cfg.scale;",
    "          gfloat y = AMotionEvent_getY (event, i) / surface->cfg.scale;",
    "",
    "          GdkEvent *ev = gdk_touch_event_new (ev_type, GUINT_TO_POINTER (sequence), (GdkSurface *) surface,",
    "                                              display->seat->logical_touchscreen,",
    "                                              time, mods,",
    "                                              x, y,",
    "                                              gdk_android_seat_create_axes_from_motion_event (event, i), i == 0);",
    "          gdk_android_seat_consume_event ((GdkDisplay *) display, ev);",
    "        }",
    "    }",
]

NEW = [
    "  if (GDK_ANDROID_EVENTS_COMPARE_MASK (src, AINPUT_SOURCE_TOUCHSCREEN))",
    "    {",
    "      /* FASE10-TOUCH-AS-POINTER: el dedo primario sigue emulando al raton",
    "       * (lineage del parche), pero la logica de emision es FASE12 (12.1/12.2):",
    "       * modelo de gestos del port de Blender para Android",
    "       * (GHOST_SystemAndroid::handleMotionEvent). El press del dedo se",
    "       * DIFIERE hasta saber si es tap o drag: el micro-movimiento del dedo",
    "       * real superaba el slop de la FASE 10 y GTK trataba los taps como drag",
    "       * => los taps fisicos no abrian menus. Un tap entrega press en el punto",
    "       * DONDE ATERRIZO el dedo y el release ~15 ms despues (click real-timed:",
    "       * press+release pegados en el mismo instante dejaban botones armados y",
    "       * rangos en drag infinito en g56); un drag presiona en el aterrizaje y",
    "       * sigue al dedo. El stylus presiona al contacto (sin deferral). */",
    "      (void) event_identifier;",
    "",
    "      size_t pointers = AMotionEvent_getPointerCount (event);",
    "      if (pointers > 0)",
    "        {",
    "          /* FASE11C-ROUTE: superficie toplevel del receptor + origen (css) del",
    "           * receptor respecto a ese toplevel (0 si el receptor ES el toplevel). */",
    "          GdkAndroidSurface *toplevel = (GdkAndroidSurface *) gdk_android_surface_get_toplevel (surface);",
    "          gfloat recv_ox = 0.0f, recv_oy = 0.0f;",
    "          if (toplevel != surface)",
    "            gdk_android_surface_popup_offset (surface, toplevel, &recv_ox, &recv_oy);",
    "",
    "          /* indice de NUESTRO dedo en ESTE evento: se rastrea por id de",
    "           * puntero (estable); los indices se barajan al irse/venir un 2o",
    "           * contacto. En g56 el digitizador doble-reporta el tap ~60 ms",
    "           * (pc 1->2->1 en casi todo tap fisico): un 'cancel por pc>=2'",
    "           * dejaba muerto todo tap => el menu de templates no clickeaba. */",
    "          size_t gidx = 0;",
    "          if (g_touch_f12.tracking)",
    "            {",
    "              gidx = pointers;",
    "              for (size_t i = 0; i < pointers; i++)",
    "                if (AMotionEvent_getPointerId (event, i) == g_touch_f12.pointer_id)",
    "                  { gidx = i; break; }",
    "            }",
    "",
    "          /* coords en el espacio CSS del toplevel, scale del toplevel (estable). */",
    "          gfloat x = AMotionEvent_getX (event, gidx) / toplevel->cfg.scale + recv_ox;",
    "          gfloat y = AMotionEvent_getY (event, gidx) / toplevel->cfg.scale + recv_oy;",
    "",
    "          /* target del gesto: el DOWN lo fija (pegajoso para MOVE/UP); si no",
    "           * hay gesto activo se re-pickea por geometria. */",
    "          GdkAndroidSurface *target;",
    "          if (masked_action == AMOTION_EVENT_ACTION_DOWN)",
    "            {",
    "              target = gdk_android_surface_pick_child (toplevel, toplevel, x, y, 0.0f, 0.0f, 0);",
    "              /* fallback: sin popup bajo el dedo, el target es el toplevel. */",
    "              if (target == NULL)",
    "                target = toplevel;",
    "              if (target != toplevel && !GDK_IS_ANDROID_POPUP (target))",
    "                target = toplevel;",
    "              g_touch_drag_surface = target;",
    "            }",
    "          else if (g_touch_drag_surface != NULL)",
    "            {",
    "              target = g_touch_drag_surface;",
    "              if (target != toplevel && !GDK_IS_ANDROID_POPUP (target))",
    "                target = toplevel;",
    "            }",
    "          else",
    "            {",
    "              target = gdk_android_surface_pick_child (toplevel, toplevel, x, y, 0.0f, 0.0f, 0);",
    "              if (target == NULL)",
    "                target = toplevel;",
    "            }",
    "",
    "          switch (masked_action)",
    "            {",
    "            case AMOTION_EVENT_ACTION_DOWN:",
    "              {",
    "                /* suelta pendiente de un tap anterior (nuevo DOWN antes del",
    "                 * timeout del release): se entrega ya, antes del nuevo gesto. */",
    "                fase12_tap_do_release ();",
    "                g_touch_f12.tracking = FALSE;",
    "                if (AMotionEvent_getToolType (event, 0) == AMOTION_EVENT_TOOL_TYPE_FINGER)",
    "                  {",
    "                    /* dedo: diferir el press (Blender). El click se entrega en",
    "                     * el punto de aterrizaje (tap), o tras superar el slop (drag). */",
    "                    g_touch_f12.pending = TRUE;",
    "                    g_touch_f12.tracking = TRUE;",
    "                    g_touch_f12.pointer_id = AMotionEvent_getPointerId (event, 0);",
    "                    g_touch_f12.down_x = x;",
    "                    g_touch_f12.down_y = y;",
    "                    g_touch_f12.last_x = x;",
    "                    g_touch_f12.last_y = y;",
    "                    /* ref fuerte al target durante todo el gesto (anti-dangling:",
    "                     * el popup podria cerrarse entre DOWN y UP). Se libera en el",
    "                     * UP / POINTER_UP de nuestro dedo (FASE12). */",
    "                    g_touch_f12.target = g_object_ref (target);",
    "                    gfloat pcx = 0.0f, pcy = 0.0f;",
    "                    if (target != toplevel)",
    "                      gdk_android_surface_popup_offset (target, toplevel, &pcx, &pcy);",
    "                    g_debug (\"FASE12-PENDING target=%p [%s] ev=%.0f,%.0f\",",
    "                             target, G_OBJECT_TYPE_NAME (target), x - pcx, y - pcy);",
    "                    gdk_android_device_maybe_update_surface ((GdkAndroidDevice *) dev, target, mods, time, x - pcx, y - pcy);",
    "                  }",
    "                else",
    "                  {",
    "                    /* stylus/pencil: press al contacto (Blender, sin deferral). */",
    "                    guint32 state = dev_impl->button_state | AMOTION_EVENT_BUTTON_PRIMARY;",
    "                    gfloat pcx = 0.0f, pcy = 0.0f;",
    "                    if (target != toplevel)",
    "                      gdk_android_surface_popup_offset (target, toplevel, &pcx, &pcy);",
    "                    g_debug (\"FASE12-PEN-DOWN target=%p [%s] ev=%.0f,%.0f\",",
    "                             target, G_OBJECT_TYPE_NAME (target), x - pcx, y - pcy);",
    "                    gdk_android_events_emit_button_press (AMOTION_EVENT_BUTTON_PRIMARY, state,",
    "                                                          GDK_BUTTON_PRIMARY,",
    "                                                          target, event, dev,",
    "                                                          time, mods,",
    "                                                          x - pcx, y - pcy);",
    "                    dev_impl->button_state = state;",
    "                    g_touch_drag_surface = target;",
    "                    gdk_android_device_maybe_update_surface ((GdkAndroidDevice *) dev, target, mods, time, x - pcx, y - pcy);",
    "                  }",
    "              }",
    "              break;",
    "            case AMOTION_EVENT_ACTION_MOVE:",
    "              {",
    "                if (g_touch_f12.tracking && gidx == pointers)",
    "                  break; /* nuestro dedo ya no esta: secuencia del otro contacto */",
    "                gfloat pcx = 0.0f, pcy = 0.0f;",
    "                if (target != toplevel)",
    "                  gdk_android_surface_popup_offset (target, toplevel, &pcx, &pcy);",
    "                if (g_touch_f12.pending)",
    "                  {",
    "                    /* jitter <= slop: no se emite NADA (el tap clickea donde",
    "                     * aterrizo el dedo). El slop->drag usa las coords de NUESTRO",
    "                     * puntero (estables por id) con CUALQUIER pc: en g56 casi",
    "                     * todo gesto va con pc=2 (pulgar de apoyo) y el gate pc==1",
    "                     * dejaba los swipes sin clasificar ('no puedo deslizar'). */",
    "                    gdouble dx = x - g_touch_f12.down_x;",
    "                    gdouble dy = y - g_touch_f12.down_y;",
    "                    if (dx * dx + dy * dy > FASE12_SLOP_SQ)",
    "                      {",
    "                        g_touch_f12.pending = FALSE;",
    "                        g_touch_f12.dbl_armed = FALSE; /* un drag rompe el par */",
    "                        guint32 state = dev_impl->button_state | AMOTION_EVENT_BUTTON_PRIMARY;",
    "                        g_debug (\"FASE12-DRAG target=%p [%s] press=%.0f,%.0f now=%.0f,%.0f\",",
    "                                 target, G_OBJECT_TYPE_NAME (target),",
    "                                 g_touch_f12.down_x - pcx, g_touch_f12.down_y - pcy,",
    "                                 x - pcx, y - pcy);",
    "                        gdk_android_events_emit_button_press (AMOTION_EVENT_BUTTON_PRIMARY, state,",
    "                                                              GDK_BUTTON_PRIMARY,",
    "                                                              target, event, dev,",
    "                                                              time, mods,",
    "                                                              g_touch_f12.down_x - pcx,",
    "                                                              g_touch_f12.down_y - pcy);",
    "                        dev_impl->button_state = state;",
    "                      }",
    "                  }",
    "                if (dev_impl->button_state & AMOTION_EVENT_BUTTON_PRIMARY)",
    "                  {",
    "                    /* arrastre en curso (dedo o stylus): el motion sigue al dedo. */",
    "                    GdkDeviceTool *tool = gdk_android_seat_get_device_tool (display->seat, AMotionEvent_getToolType (event, gidx));",
    "                    GdkEvent *ev = gdk_motion_event_new ((GdkSurface *) target, dev, tool,",
    "                                                         time, mods,",
    "                                                         x - pcx, y - pcy,",
    "                                                         gdk_android_seat_create_axes_from_motion_event (event, gidx));",
    "                    gdk_android_seat_consume_event ((GdkDisplay *) display, ev);",
    "                    gdk_android_device_maybe_update_surface ((GdkAndroidDevice *) dev, target, mods, time, x - pcx, y - pcy);",
    "                  }",
    "                g_touch_f12.last_x = x;",
    "                g_touch_f12.last_y = y;",
    "              }",
    "              break;",
    "            case AMOTION_EVENT_ACTION_UP:",
    "            case AMOTION_EVENT_ACTION_CANCEL:",
    "              {",
    "                if (g_touch_f12.tracking && gidx == pointers)",
    "                  break; /* nuestro dedo ya se fue (su POINTER_UP lo cerro) */",
    "                gfloat pcx = 0.0f, pcy = 0.0f;",
    "                if (target != toplevel)",
    "                  gdk_android_surface_popup_offset (target, toplevel, &pcx, &pcy);",
    "                if (g_touch_f12.pending)",
    "                  {",
    "                    /* TAP: press en el punto DONDE ATERRIZO el dedo y release",
    "                     * real-timed ~FASE12_TAP_RELEASE_MS despues (click fiable;",
    "                     * en g56 el press+release pegados dejaban botones armados",
    "                     * y rangos en drag/repeat infinito). */",
    "                    g_touch_f12.pending = FALSE;",
    "                    gboolean is_dbl = g_touch_f12.dbl_armed &&",
    "                                      target == toplevel &&",
    "                                      (g_get_monotonic_time () / 1000 - g_touch_f12.dbl_ms) < FASE12_DBL_TIME_MS;",
    "                    guint32 state = dev_impl->button_state | AMOTION_EVENT_BUTTON_PRIMARY;",
    "                    g_debug (\"FASE12-TAP target=%p [%s] ev=%.0f,%.0f%s\",",
    "                             target, G_OBJECT_TYPE_NAME (target),",
    "                             g_touch_f12.down_x - pcx, g_touch_f12.down_y - pcy,",
    "                             is_dbl ? \" dbl\" : \"\");",
    "                    if (is_dbl)",
    "                      g_debug (\"FASE12-DBLCLICK target=%p [%s] par con 1er=%.0f,%.0f\",",
    "                               target, G_OBJECT_TYPE_NAME (target),",
    "                               g_touch_f12.dbl_x - pcx, g_touch_f12.dbl_y - pcy);",
    "                    gdk_android_events_emit_button_press (AMOTION_EVENT_BUTTON_PRIMARY, state,",
    "                                                          GDK_BUTTON_PRIMARY,",
    "                                                          target, event, dev,",
    "                                                          time, mods,",
    "                                                          g_touch_f12.down_x - pcx,",
    "                                                          g_touch_f12.down_y - pcy);",
    "                    dev_impl->button_state = state;",
    "                    fase12_tap_schedule_release (target, g_touch_f12.down_x, g_touch_f12.down_y);",
    "                    /* doble-click tolerante al dedo: solo se arma sobre el",
    "                     * TOPLEVEL (menus/popups jamás doble-cliclean) y con dos",
    "                     * taps rapidos (GtkGestureClick cuenta por timeout y sin",
    "                     * distancia en touchscreen). */",
    "                    if (target == toplevel)",
    "                      {",
    "                        g_touch_f12.dbl_armed = TRUE;",
    "                        g_touch_f12.dbl_x = g_touch_f12.down_x;",
    "                        g_touch_f12.dbl_y = g_touch_f12.down_y;",
    "                        g_touch_f12.dbl_ms = g_get_monotonic_time () / 1000;",
    "                      }",
    "                    else",
    "                      g_touch_f12.dbl_armed = FALSE;",
    "                  }",
    "                else if (dev_impl->button_state & AMOTION_EVENT_BUTTON_PRIMARY)",
    "                  {",
    "                    /* suelta el boton primario (fin de drag de dedo o stylus). */",
    "                    guint32 up_state = dev_impl->button_state & ~AMOTION_EVENT_BUTTON_PRIMARY;",
    "                    g_debug (\"FASE12-UP target=%p [%s] ev=%.0f,%.0f btn=1\",",
    "                             target, G_OBJECT_TYPE_NAME (target), x - pcx, y - pcy);",
    "                    gdk_android_events_emit_button_press (AMOTION_EVENT_BUTTON_PRIMARY, up_state,",
    "                                                          GDK_BUTTON_PRIMARY,",
    "                                                          target, event, dev,",
    "                                                          time, mods,",
    "                                                          x - pcx, y - pcy);",
    "                    dev_impl->button_state = up_state;",
    "                  }",
    "                g_touch_f12.pending = FALSE;",
    "                g_touch_f12.tracking = FALSE;",
    "                g_touch_f12.pointer_id = -1;",
    "                g_clear_object (&g_touch_f12.target);",
    "                g_touch_drag_surface = NULL;",
    "                gdk_android_device_maybe_update_surface ((GdkAndroidDevice *) dev, target, mods, time, x - pcx, y - pcy);",
    "              }",
    "              break;",
    "            case AMOTION_EVENT_ACTION_POINTER_UP:",
    "              {",
    "                /* se levanta uno de los dedos; si es el NUESTRO, el gesto termina",
    "                 * aqui: el ACTION_UP final no llega mientras quede otro contacto",
    "                 * abajo (g56: pulgar de apoyo). Un 'cancel por pc>=2' dejaba",
    "                 * muerto todo tap fisico (tap doble-reportado ~60 ms). */",
    "                size_t affected = (AMotionEvent_getAction (event) & AMOTION_EVENT_ACTION_POINTER_INDEX_MASK) >> AMOTION_EVENT_ACTION_POINTER_INDEX_SHIFT;",
    "                if (g_touch_f12.tracking &&",
    "                    AMotionEvent_getPointerId (event, affected) == g_touch_f12.pointer_id)",
    "                  {",
    "                    gfloat pcx = 0.0f, pcy = 0.0f;",
    "                    if (target != toplevel)",
    "                      gdk_android_surface_popup_offset (target, toplevel, &pcx, &pcy);",
    "                    if (g_touch_f12.pending)",
    "                      {",
    "                        /* TAP igual que en UP: press en el aterrizaje + release",
    "                         * real-timed. */",
    "                        g_touch_f12.pending = FALSE;",
    "                        gboolean is_dbl = g_touch_f12.dbl_armed &&",
    "                                          target == toplevel &&",
    "                                          (g_get_monotonic_time () / 1000 - g_touch_f12.dbl_ms) < FASE12_DBL_TIME_MS;",
    "                        guint32 state = dev_impl->button_state | AMOTION_EVENT_BUTTON_PRIMARY;",
    "                        g_debug (\"FASE12-TAP target=%p [%s] ev=%.0f,%.0f (p-up)%s\",",
    "                                 target, G_OBJECT_TYPE_NAME (target),",
    "                                 g_touch_f12.down_x - pcx, g_touch_f12.down_y - pcy,",
    "                                 is_dbl ? \" dbl\" : \"\");",
    "                        if (is_dbl)",
    "                          g_debug (\"FASE12-DBLCLICK target=%p [%s] par con 1er=%.0f,%.0f (p-up)\",",
    "                                   target, G_OBJECT_TYPE_NAME (target),",
    "                                   g_touch_f12.dbl_x - pcx, g_touch_f12.dbl_y - pcy);",
    "                        gdk_android_events_emit_button_press (AMOTION_EVENT_BUTTON_PRIMARY, state,",
    "                                                              GDK_BUTTON_PRIMARY,",
    "                                                              target, event, dev,",
    "                                                              time, mods,",
    "                                                              g_touch_f12.down_x - pcx,",
    "                                                              g_touch_f12.down_y - pcy);",
    "                        dev_impl->button_state = state;",
    "                        fase12_tap_schedule_release (target, g_touch_f12.down_x, g_touch_f12.down_y);",
    "                        if (target == toplevel)",
    "                          {",
    "                            g_touch_f12.dbl_armed = TRUE;",
    "                            g_touch_f12.dbl_x = g_touch_f12.down_x;",
    "                            g_touch_f12.dbl_y = g_touch_f12.down_y;",
    "                            g_touch_f12.dbl_ms = g_get_monotonic_time () / 1000;",
    "                          }",
    "                        else",
    "                          g_touch_f12.dbl_armed = FALSE;",
    "                      }",
    "                    else if (dev_impl->button_state & AMOTION_EVENT_BUTTON_PRIMARY)",
    "                      {",
    "                        guint32 up_state = dev_impl->button_state & ~AMOTION_EVENT_BUTTON_PRIMARY;",
    "                        g_debug (\"FASE12-UP target=%p [%s] ev=%.0f,%.0f btn=1 (p-up)\",",
    "                                 target, G_OBJECT_TYPE_NAME (target),",
    "                                 g_touch_f12.last_x - pcx, g_touch_f12.last_y - pcy);",
    "                        gdk_android_events_emit_button_press (AMOTION_EVENT_BUTTON_PRIMARY, up_state,",
    "                                                              GDK_BUTTON_PRIMARY,",
    "                                                              target, event, dev,",
    "                                                              time, mods,",
    "                                                              g_touch_f12.last_x - pcx,",
    "                                                              g_touch_f12.last_y - pcy);",
    "                        dev_impl->button_state = up_state;",
    "                      }",
    "                    g_touch_f12.pending = FALSE;",
    "                    g_touch_f12.tracking = FALSE;",
    "                    g_touch_f12.pointer_id = -1;",
    "                    g_clear_object (&g_touch_f12.target);",
    "                    g_touch_drag_surface = NULL;",
    "                    gdk_android_device_maybe_update_surface ((GdkAndroidDevice *) dev, target, mods, time, g_touch_f12.last_x - pcx, g_touch_f12.last_y - pcy);",
    "                  }",
    "              }",
    "              break;",
    "            default:",
    "              break;",
    "            }",
    "        }",
    "    }",
]

# FASE11C-ROUTE: helpers de ruteo del puntero sintetico (ver docstring).
# Se insertan ANTES de gdk_android_events_handle_motion_event (ancla unica:
# la firma solo existe una vez en gdkandroidevents.c).
HELPER = """/* FASE11C-ROUTE: helpers de ruteo del puntero sintetico (dedo primario).
 *
 * 1) gdk_android_surface_popup_offset: origen CSS de un surface respecto al
 *    toplevel. Un GdkAndroidPopup cuyo padre NO es el toplevel queda anidado:
 *    su popup_bounds esta en el espacio de SU padre, asi que se suman los
 *    popup_bounds de si mismo y de cada ancestro. El toplevel -> (0, 0).
 * 2) gdk_android_surface_pick_child: popup visible cuyo rect CSS (basado en
 *    popup_bounds, NUNCA en cfg) contiene el punto, en coords CSS del
 *    toplevel. children usa g_list_prepend => el mas reciente/topmost queda
 *    primero; se recursa primero en los hijos (vienen encima del padre).
 *    popup_bounds se fija en present() de forma SINCRONA, antes del layout
 *    async de Java (cfg seria 0,0,0,0 hasta el primer on_layout => la carrera
 *    que cerraba los menus al tocar un item justo tras abrirlos). NULL si no
 *    hay ningun popup bajo el dedo.
 * 3) g_touch_drag_surface: target pegajoso del gesto (fijado en el DOWN) para
 *    que un drag que se salga del rect del popover no salte al canvas.
 *
 * FASE12-TOUCH: estado del gesto diferido (modelo Blender). El press del dedo
 * no se emite en el DOWN; queda pendiente de clasificar (tap/drag) y el click
 * SIEMPRE se entrega en el punto donde aterrizo el dedo. FASE12.2: el click
 * del tap es REAL-TIMED (presion en el UP del dedo, suelta ~15 ms despues con
 * timestamp propio): en g56 el press+release pegados en el mismo instante
 * dejaban botones armados (toggle tools que nunca clickeaban) y rangos en
 * drag/repeat infinito (scrollbars "sostenidas"). Tambien arma el par de
 * doble-click tolerante al dedo (350 ms, solo TOPLEVEL) con el que los taps
 * gemelos abren templates/recientes/file-chooser (GtkListBox activa en el 2o
 * PRESS; GtkGestureClick cuenta por timeout y sin distancia en touchscreen). */

static GdkAndroidSurface *g_touch_drag_surface = NULL;

static void
gdk_android_surface_popup_offset (GdkAndroidSurface *surface,
                                  GdkAndroidSurface *toplevel,
                                  gfloat           *ox,
                                  gfloat           *oy)
{
  gfloat x = 0.0f, y = 0.0f;

  for (GdkAndroidSurface *s = surface; s != toplevel && s != NULL; s = (GdkAndroidSurface *) GDK_SURFACE (s)->parent)
    {
      GdkAndroidPopup *popup = GDK_ANDROID_POPUP (s);
      x += popup->popup_bounds.x;
      y += popup->popup_bounds.y;
    }

  *ox = x;
  *oy = y;
}

static GdkAndroidSurface *
gdk_android_surface_pick_child (GdkAndroidSurface *toplevel,
                                GdkAndroidSurface *node,
                                gfloat             x,
                                gfloat             y,
                                gfloat             rx,
                                gfloat             ry,
                                guint              depth)
{
  if (depth > 8)
    {
      g_critical ("FASE11C-PICK: profundidad excesiva (%u) en %p [%s]",
                  depth, node, G_OBJECT_TYPE_NAME (node));
      return NULL;
    }

  g_debug ("FASE11C-PICK [%s] %p children=%u xy=%.0f,%.0f",
           G_OBJECT_TYPE_NAME (node), node,
           g_list_length (GDK_SURFACE (node)->children), x, y);

  for (GList *l = GDK_SURFACE (node)->children; l != NULL; l = l->next)
    {
      GdkAndroidSurface *child = l->data;

      /* Defensa anti-dangling: solo popups vivos y cuyo parent sea node.
       * La lista children del backend puede contener entradas de popups ya
       * finalizados (no siempre se retiran al re-parentar/ocultar). */
      if (child == NULL || !GDK_IS_ANDROID_POPUP (child))
        continue;
      if (GDK_SURFACE (child)->parent != (GdkSurface *) node)
        continue;
      if (!child->visible)
        continue;

      GdkAndroidPopup *popup = GDK_ANDROID_POPUP (child);
      gfloat cx = rx + popup->popup_bounds.x;
      gfloat cy = ry + popup->popup_bounds.y;
      gfloat cw = popup->popup_bounds.width;
      gfloat ch = popup->popup_bounds.height;

      g_debug ("FASE11C-PICK  cand=%p [%s] vis=%d rect=%.0f,%.0f %.0fx%.0f",
               child, G_OBJECT_TYPE_NAME (child), child->visible, cx, cy, cw, ch);

      if (cw <= 0.0f || ch <= 0.0f)
        continue;

      if (x >= cx && x < cx + cw && y >= cy && y < cy + ch)
        {
          GdkAndroidSurface *inner = gdk_android_surface_pick_child (toplevel, child, x, y, cx, cy, depth + 1);
          if (inner != NULL)
            return inner;
          return child;
        }
    }

  return NULL;
}

/* FASE12-TOUCH: estado del gesto diferido + doble-click + release real-timed.
 * FASE12_SLOP: ~12 css px (dedo real; el tap clickea en el aterrizaje igual).
 * FASE12_TAP_RELEASE_MS: presion real del click sintetico del dedo (g56:
 * press+release pegados en el mismo instante dejaban botones armados y rangos
 * en drag infinito; el release diferido entrega un click real-timed como el
 * de adb/mouse en FASE10/11, que si funcionaba).
 * FASE12_DBL_TIME_MS: ventana del par de doble-click (GtkGestureClick usa el
 * gtk-double-click-time de settings, ~400 ms; 350 ms deja margen). */
#define FASE12_SLOP 12.0
#define FASE12_SLOP_SQ (FASE12_SLOP * FASE12_SLOP)
#define FASE12_TAP_RELEASE_MS 15
#define FASE12_DBL_TIME_MS 350

static struct {
    gboolean pending;      /* dedo abajo sin clasificar (tap/drag) */
    gboolean tracking;     /* gesto activo: rastrea por pointer_id (estable) */
    gint32 pointer_id;     /* id de puntero de NUESTRO dedo (g56: los indices
                              se barajan con un 2o contacto transitorio) */
    gdouble down_x;        /* donde aterrizo el dedo (css del toplevel) */
    gdouble down_y;
    gdouble last_x;        /* ultima posicion de nuestro dedo (para releases) */
    gdouble last_y;
    GdkAndroidSurface *target; /* ref fuerte durante el gesto (anti-dangling) */
    /* par de doble-click tolerante al dedo (solo TOPLEVEL, FASE12.2) */
    gboolean dbl_armed;
    gdouble dbl_x;         /* punto del tap anterior (css del toplevel) */
    gdouble dbl_y;
    gint64 dbl_ms;         /* monotonic ms del tap anterior */
    /* release diferido del TAP (click real-timed, FASE12.2) */
    gboolean rel_pending;
    guint rel_id;          /* source id del timeout de suelta */
    GdkAndroidSurface *rel_target; /* ref fuerte mientras la suelta esta pendiente */
    gdouble rel_x;         /* donde emitir el release (css del toplevel) */
    gdouble rel_y;
} g_touch_f12 = {FALSE, FALSE, -1, 0.0, 0.0, 0.0, 0.0, NULL, FALSE, 0.0, 0.0, 0, FALSE, 0, NULL, 0.0, 0.0};

/* Emite la suelta pendiente del tap (o no hace nada si no hay). Requiere el
 * main loop del display; se llama desde el timeout o desde el DOWN de un nuevo
 * gesto (flush) para que el release del tap anterior se entregue SIEMPRE. */
static void
fase12_tap_do_release (void)
{
  GdkAndroidSurface *target;
  GdkAndroidSurface *toplevel;
  GdkAndroidDisplay *display;
  GdkAndroidDevice *dev_impl;
  GdkDevice *dev;
  GdkModifierType mods;
  GdkDeviceTool *tool;
  guint32 up_state, time;
  gfloat pcx = 0.0f, pcy = 0.0f;

  if (!g_touch_f12.rel_pending)
    return;
  g_touch_f12.rel_pending = FALSE;
  if (g_touch_f12.rel_id != 0)
    {
      g_source_remove (g_touch_f12.rel_id);
      g_touch_f12.rel_id = 0;
    }

  target = g_touch_f12.rel_target;
  if (target == NULL)
    return;

  display = (GdkAndroidDisplay *) gdk_surface_get_display ((GdkSurface *) target);
  dev = gdk_seat_get_pointer ((GdkSeat *) display->seat);
  dev_impl = GDK_ANDROID_DEVICE (dev);
  toplevel = (GdkAndroidSurface *) gdk_android_surface_get_toplevel (target);
  if (target != toplevel)
    gdk_android_surface_popup_offset (target, toplevel, &pcx, &pcy);

  up_state = dev_impl->button_state & ~AMOTION_EVENT_BUTTON_PRIMARY;
  mods = gdk_android_events_buttons_to_gdkmods (up_state);
  time = (guint32) (g_get_monotonic_time () / 1000);
  tool = gdk_android_seat_get_device_tool (display->seat, AMOTION_EVENT_TOOL_TYPE_FINGER);

  g_debug ("FASE12-TAP-REL target=%p [%s] ev=%.0f,%.0f",
           target, G_OBJECT_TYPE_NAME (target),
           g_touch_f12.rel_x - pcx, g_touch_f12.rel_y - pcy);

  GdkEvent *ev = gdk_button_event_new (GDK_BUTTON_RELEASE, (GdkSurface *) target, dev, tool,
                                       time, mods, GDK_BUTTON_PRIMARY,
                                       g_touch_f12.rel_x - pcx, g_touch_f12.rel_y - pcy,
                                       NULL);
  gdk_android_seat_consume_event ((GdkDisplay *) display, ev);
  dev_impl->button_state = up_state;
  gdk_android_device_maybe_update_surface ((GdkAndroidDevice *) dev, target, mods, time,
                                           g_touch_f12.rel_x - pcx, g_touch_f12.rel_y - pcy);
  g_clear_object (&g_touch_f12.rel_target);
}

static gboolean
fase12_tap_release_cb (gpointer user_data)
{
  (void) user_data;
  fase12_tap_do_release ();
  return G_SOURCE_REMOVE;
}

/* Programa la suelta del tap ~FASE12_TAP_RELEASE_MS despues del press, en el
 * mismo punto (coords css del toplevel; el offset del popup se corrige al
 * emitir). Ref fuerte al target mientras la suelta este pendiente. */
static void
fase12_tap_schedule_release (GdkAndroidSurface *target,
                             gdouble            x,
                             gdouble            y)
{
  if (g_touch_f12.rel_pending)
    return; /* ya hay una suelta programada (no deberia pasar; defensivo) */

  g_touch_f12.rel_target = g_object_ref (target);
  g_touch_f12.rel_x = x;
  g_touch_f12.rel_y = y;
  g_touch_f12.rel_pending = TRUE;
  g_touch_f12.rel_id = g_timeout_add (FASE12_TAP_RELEASE_MS, fase12_tap_release_cb, NULL);
}"""

# FASE11C-ROUTE: include necesario para GdkAndroidPopup / popup_bounds /
# gdk_android_surface_get_toplevel (gdkandroidpopup-private.h trae tambien
# gdkandroidsurface-private.h, que declara ese prototype).
INCLUDE_OLD = '#include "gdkandroidevents-private.h"\n'
INCLUDE_NEW = ('#include "gdkandroidevents-private.h"\n'
               '#include "gdkandroidpopup-private.h"\n')


def main() -> int:
    if len(sys.argv) != 2:
        print("uso: gtk4-touch-as-pointer.py <srcdir-gtk>", file=sys.stderr)
        return 2
    path = sys.argv[1].rstrip("/") + "/" + SRC_REL
    with open(path, "r") as fh:
        src = fh.read()

    old = "\n".join(OLD)
    n = src.count(old)
    if n != 1:
        print("ERROR: bloque TOUCHSCREEN encontrado %d veces (esperado 1); " % n +
              "cambio upstream en 4.22.5; re-auditar", file=sys.stderr)
        return 1
    if "FASE10-TOUCH-AS-POINTER" in src:
        print("ERROR: parche FASE10 ya aplicado", file=sys.stderr)
        return 1

    src = src.replace(old, "\n".join(NEW))

    # FASE11C-ROUTE: insertar los helpers antes de la definicion del handler.
    # El ancla incluye la linea 'void' (tipo de retorno) para no dejar un 'void'
    # colgante antes de los helpers.
    helper_anchor = "void\ngdk_android_events_handle_motion_event (GdkAndroidSurface *surface,"
    h = src.count(helper_anchor)
    if h != 1:
        print("ERROR: ancla del handler encontrada %d veces (esperado 1); " % h +
              "re-auditar", file=sys.stderr)
        return 1
    src = src.replace(helper_anchor, HELPER + "\n\n" + helper_anchor)

    # FASE11C-ROUTE: include del popup-private (unica aparicion en este .c).
    i = src.count(INCLUDE_OLD)
    if i != 1:
        print("ERROR: include gdkandroidevents-private.h encontrado %d veces " % i +
              "(esperado 1); re-auditar", file=sys.stderr)
        return 1
    src = src.replace(INCLUDE_OLD, INCLUDE_NEW)

    markers = [
        "FASE12-TOUCH",
        "FASE12-PENDING",
        "FASE12-TAP",
        "FASE12-DRAG",
        "FASE12-TAP-REL",
        "FASE12-DBLCLICK",
        "fase12_tap_schedule_release",
        "fase12_tap_do_release",
        "fase12_tap_release_cb",
        "FASE12_TAP_RELEASE_MS",
        "FASE12_DBL_TIME_MS",
        "g_touch_f12",
        "g_touch_f12.tracking",
        "g_touch_f12.pointer_id",
        "g_touch_f12.last_x",
        "g_touch_f12.dbl_armed",
        "g_touch_f12.rel_pending",
        "g_object_ref",
        "g_clear_object",
        "g_timeout_add",
        "FASE12_SLOP",
        "AMOTION_EVENT_ACTION_POINTER_UP",
        "AMOTION_EVENT_ACTION_POINTER_INDEX_MASK",
        "FASE11C-ROUTE",
        "gdk_android_surface_pick_child",
        "gdk_android_surface_popup_offset",
        "g_touch_drag_surface",
        "gdkandroidpopup-private.h",
        "AMOTION_EVENT_TOOL_TYPE_FINGER",
        "gdk_motion_event_new",
        "case AMOTION_EVENT_ACTION_DOWN:",
        "case AMOTION_EVENT_ACTION_CANCEL:",
    ]
    for m in markers:
        if m not in src:
            print("ERROR: marker '%s' no presente tras el parche" % m, file=sys.stderr)
            return 1
    # el loop de touch OLD debe haber desaparecido
    if "gdk_touch_event_new" in src:
        print("ERROR: gdk_touch_event_new sigue presente", file=sys.stderr)
        return 1

    with open(path, "w") as fh:
        fh.write(src)
    print("gtk4: FASE12.2 gestos estilo Blender (click real-timed, sin long-press,"
          " doble-click dedo, drag pc>=2) + FASE11C-ROUTE aplicado en %s" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main())