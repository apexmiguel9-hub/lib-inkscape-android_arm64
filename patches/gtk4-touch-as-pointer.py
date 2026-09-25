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
  * UP (tap)  -> press + release en el punto de aterrizaje => click limpio
                 aunque el dedo derive antes de levantar (fix de los taps
                 fisicos; Blender: UP con touch_pending_ => down+up en el down).
  * Long-press (500 ms sin exceder el slop de long-press) -> click derecho en
                 el punto de aterrizaje (menus de contexto con el dedo;
                 Blender: TOUCH_LONG_PRESS_MS / TOUCH_LONG_PRESS_MOVE_PX).
  * Stylus    -> press al contacto, sin deferral (Blender: el stylus no
                 participa del dedo diferido).

FASE 12.1 (device g56): el digitizador DOBLE-REPORTA cada tap fisico (~60 ms de
pc 1->2->1) y Android baraja los indices de puntero al irse/venir un contacto
(tras el P_UP de nuestro dedo, el stream sigue con la POSICION del otro dedo
bajo el indice 0). Por eso:
  * el gesto se rastrea por ID de puntero (estable), no por indice: gidx se
    resuelve en cada evento buscando nuestro pointer_id; con un 2o contacto en
    la secuencia NO se cancela el pending (un 'cancel pc>=2' hacia el clasico
    FASE12-CANCEL-PENDING: ningun tap sobrevivia => el menu de templates no
    clickeaba) y el slop->drag SOLO se clasifica con pc==1 (stream fiable).
  * el gesto termina en el POINTER_UP de NUESTRO dedo (el ACTION_UP final no
    llega si queda otro contacto abajo): si pending => TAP en el aterrizaje;
    si arrastraba => release en la ultima posicion conocida.

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
    "       * (lineage del parche), pero la logica de emision es ahora FASE12:",
    "       * modelo de gestos del port de Blender para Android",
    "       * (GHOST_SystemAndroid::handleMotionEvent). El press del dedo se",
    "       * DIFIERE hasta saber si es tap, drag o long-press: el micro-movimiento",
    "       * del dedo real superaba el slop de la FASE 10 y GTK trataba los taps",
    "       * como drag => los taps fisicos no abrian menus. Un tap entrega",
    "       * press+release en el punto DONDE ATERRIZO el dedo; un drag presiona",
    "       * ahi y sigue al dedo; 500 ms quieto = click derecho. El stylus",
    "       * presiona al contacto (sin deferral). */",
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
    "                g_touch_f12.tracking = FALSE;",
    "                if (AMotionEvent_getToolType (event, 0) == AMOTION_EVENT_TOOL_TYPE_FINGER)",
    "                  {",
    "                    /* dedo: diferir el press (Blender). El click se entrega en",
    "                     * el punto de aterrizaje (tap), tras superar el slop (drag)",
    "                     * o tras 500 ms quietos (long-press: click derecho). */",
    "                    g_touch_f12.pending = TRUE;",
    "                    g_touch_f12.tracking = TRUE;",
    "                    g_touch_f12.pointer_id = AMotionEvent_getPointerId (event, 0);",
    "                    g_touch_f12.down_x = x;",
    "                    g_touch_f12.down_y = y;",
    "                    g_touch_f12.last_x = x;",
    "                    g_touch_f12.last_y = y;",
    "                    g_touch_f12.down_ms = g_get_monotonic_time () / 1000;",
    "                    g_touch_f12.tool_type = AMOTION_EVENT_TOOL_TYPE_FINGER;",
    "                    /* ref fuerte al target durante todo el gesto: el long-press",
    "                     * se dispara 500 ms despues del DOWN y el popup podria",
    "                     * haberse cerrado/liberado en ese lapso. Se libera en UP,",
    "                     * en el POINTER_UP de nuestro dedo o al emitir el",
    "                     * long-press (FASE12). */",
    "                    g_touch_f12.target = g_object_ref (target);",
    "                    g_touch_f12_lp_id = g_timeout_add (FASE12_LONG_PRESS_MS,",
    "                                                       fase12_long_press_cb, NULL);",
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
    "                     * aterrizo el dedo). El slop->drag SOLO se clasifica con",
    "                     * pc==1: con un 2o contacto en la secuencia (g56: el tap",
    "                     * viene doble-reportado ~60 ms) el stream no es fiable y",
    "                     * el tap debe aterrizar en UP en su punto de aterrizaje. */",
    "                    if (pointers == 1)",
    "                      {",
    "                        gdouble dx = x - g_touch_f12.down_x;",
    "                        gdouble dy = y - g_touch_f12.down_y;",
    "                        if (dx * dx + dy * dy > FASE12_SLOP_SQ)",
    "                          {",
    "                            g_touch_f12.pending = FALSE;",
    "                            g_touch_f12_remove_lp ();",
    "                            guint32 state = dev_impl->button_state | AMOTION_EVENT_BUTTON_PRIMARY;",
    "                            g_debug (\"FASE12-DRAG target=%p [%s] press=%.0f,%.0f now=%.0f,%.0f\",",
    "                                     target, G_OBJECT_TYPE_NAME (target),",
    "                                     g_touch_f12.down_x - pcx, g_touch_f12.down_y - pcy,",
    "                                     x - pcx, y - pcy);",
    "                            gdk_android_events_emit_button_press (AMOTION_EVENT_BUTTON_PRIMARY, state,",
    "                                                                  GDK_BUTTON_PRIMARY,",
    "                                                                  target, event, dev,",
    "                                                                  time, mods,",
    "                                                                  g_touch_f12.down_x - pcx,",
    "                                                                  g_touch_f12.down_y - pcy);",
    "                            dev_impl->button_state = state;",
    "                          }",
    "                      }",
    "                  }",
    "                if (dev_impl->button_state & (AMOTION_EVENT_BUTTON_PRIMARY | AMOTION_EVENT_BUTTON_SECONDARY))",
    "                  {",
    "                    /* arrastre en curso (dedo, stylus o long-press): el motion",
    "                     * sigue al dedo. */",
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
    "                g_touch_f12_remove_lp ();",
    "                gfloat pcx = 0.0f, pcy = 0.0f;",
    "                if (target != toplevel)",
    "                  gdk_android_surface_popup_offset (target, toplevel, &pcx, &pcy);",
    "                if (g_touch_f12.pending)",
    "                  {",
    "                    /* TAP: press + release en el punto DONDE ATERRIZO el dedo",
    "                     * => click limpio aunque el dedo derive (fix taps fisicos). */",
    "                    g_touch_f12.pending = FALSE;",
    "                    guint32 state = dev_impl->button_state | AMOTION_EVENT_BUTTON_PRIMARY;",
    "                    g_debug (\"FASE12-TAP target=%p [%s] ev=%.0f,%.0f\",",
    "                             target, G_OBJECT_TYPE_NAME (target),",
    "                             g_touch_f12.down_x - pcx, g_touch_f12.down_y - pcy);",
    "                    gdk_android_events_emit_button_press (AMOTION_EVENT_BUTTON_PRIMARY, state,",
    "                                                          GDK_BUTTON_PRIMARY,",
    "                                                          target, event, dev,",
    "                                                          time, mods,",
    "                                                          g_touch_f12.down_x - pcx,",
    "                                                          g_touch_f12.down_y - pcy);",
    "                    guint32 up_state = state & ~AMOTION_EVENT_BUTTON_PRIMARY;",
    "                    gdk_android_events_emit_button_press (AMOTION_EVENT_BUTTON_PRIMARY, up_state,",
    "                                                          GDK_BUTTON_PRIMARY,",
    "                                                          target, event, dev,",
    "                                                          time, mods,",
    "                                                          g_touch_f12.down_x - pcx,",
    "                                                          g_touch_f12.down_y - pcy);",
    "                    dev_impl->button_state = up_state;",
    "                  }",
    "                else if (dev_impl->button_state & (AMOTION_EVENT_BUTTON_PRIMARY | AMOTION_EVENT_BUTTON_SECONDARY))",
    "                  {",
    "                    /* suelta el boton que estaba abajo (fin de drag o long-press). */",
    "                    guint32 mask = dev_impl->button_state & (AMOTION_EVENT_BUTTON_PRIMARY | AMOTION_EVENT_BUTTON_SECONDARY);",
    "                    guint button = (mask & AMOTION_EVENT_BUTTON_SECONDARY) ? GDK_BUTTON_SECONDARY : GDK_BUTTON_PRIMARY;",
    "                    guint32 state = dev_impl->button_state & ~mask;",
    "                    g_debug (\"FASE12-UP target=%p [%s] ev=%.0f,%.0f btn=%u\",",
    "                             target, G_OBJECT_TYPE_NAME (target), x - pcx, y - pcy, button);",
    "                    gdk_android_events_emit_button_press (mask, state, button,",
    "                                                          target, event, dev,",
    "                                                          time, mods,",
    "                                                          x - pcx, y - pcy);",
    "                    dev_impl->button_state = state;",
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
    "                    g_touch_f12_remove_lp ();",
    "                    gfloat pcx = 0.0f, pcy = 0.0f;",
    "                    if (target != toplevel)",
    "                      gdk_android_surface_popup_offset (target, toplevel, &pcx, &pcy);",
    "                    if (g_touch_f12.pending)",
    "                      {",
    "                        /* TAP igual que en UP: click en el punto de aterrizaje. */",
    "                        g_touch_f12.pending = FALSE;",
    "                        guint32 state = dev_impl->button_state | AMOTION_EVENT_BUTTON_PRIMARY;",
    "                        g_debug (\"FASE12-TAP target=%p [%s] ev=%.0f,%.0f (p-up)\",",
    "                                 target, G_OBJECT_TYPE_NAME (target),",
    "                                 g_touch_f12.down_x - pcx, g_touch_f12.down_y - pcy);",
    "                        gdk_android_events_emit_button_press (AMOTION_EVENT_BUTTON_PRIMARY, state,",
    "                                                              GDK_BUTTON_PRIMARY,",
    "                                                              target, event, dev,",
    "                                                              time, mods,",
    "                                                              g_touch_f12.down_x - pcx,",
    "                                                              g_touch_f12.down_y - pcy);",
    "                        guint32 up_state = state & ~AMOTION_EVENT_BUTTON_PRIMARY;",
    "                        gdk_android_events_emit_button_press (AMOTION_EVENT_BUTTON_PRIMARY, up_state,",
    "                                                              GDK_BUTTON_PRIMARY,",
    "                                                              target, event, dev,",
    "                                                              time, mods,",
    "                                                              g_touch_f12.down_x - pcx,",
    "                                                              g_touch_f12.down_y - pcy);",
    "                        dev_impl->button_state = up_state;",
    "                      }",
    "                    else if (dev_impl->button_state & (AMOTION_EVENT_BUTTON_PRIMARY | AMOTION_EVENT_BUTTON_SECONDARY))",
    "                      {",
    "                        guint32 mask = dev_impl->button_state & (AMOTION_EVENT_BUTTON_PRIMARY | AMOTION_EVENT_BUTTON_SECONDARY);",
    "                        guint button = (mask & AMOTION_EVENT_BUTTON_SECONDARY) ? GDK_BUTTON_SECONDARY : GDK_BUTTON_PRIMARY;",
    "                        guint32 state = dev_impl->button_state & ~mask;",
    "                        g_debug (\"FASE12-UP target=%p [%s] ev=%.0f,%.0f btn=%u (p-up)\",",
    "                                 target, G_OBJECT_TYPE_NAME (target),",
    "                                 g_touch_f12.last_x - pcx, g_touch_f12.last_y - pcy, button);",
    "                        gdk_android_events_emit_button_press (mask, state, button,",
    "                                                              target, event, dev,",
    "                                                              time, mods,",
    "                                                              g_touch_f12.last_x - pcx,",
    "                                                              g_touch_f12.last_y - pcy);",
    "                        dev_impl->button_state = state;",
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
 * no se emite en el DOWN; queda pendiente de clasificar (tap/drag/long-press)
 * y el click SIEMPRE se entrega en el punto donde aterrizo el dedo. */

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

/* FASE12-TOUCH: estado del gesto diferido + click derecho por long-press.
 * FASE12_SLOP: ~12 css px (dedo real; el tap clickea en el aterrizaje igual).
 * El callback se dispara desde el main loop (g_timeout_add es seguro: los
 * eventos llegan via GlibContext.runOnMain, hilo del g_main_context). */
#define FASE12_SLOP 12.0
#define FASE12_SLOP_SQ (FASE12_SLOP * FASE12_SLOP)
#define FASE12_LONG_PRESS_MS 500

static struct {
    gboolean pending;      /* dedo abajo sin clasificar (tap/drag/long-press) */
    gboolean tracking;     /* gesto activo: rastrea por pointer_id (estable) */
    gint32 pointer_id;     /* id de puntero de NUESTRO dedo (g56: los indices
                              se barajan con un 2o contacto transitorio) */
    gdouble down_x;        /* donde aterrizo el dedo (css del toplevel) */
    gdouble down_y;
    gdouble last_x;        /* ultima posicion de nuestro dedo (para releases) */
    gdouble last_y;
    gint64 down_ms;        /* g_get_monotonic_time () / 1000 al aterrizar */
    gint32 tool_type;      /* AMOTION_EVENT_TOOL_TYPE_* al aterrizar */
    GdkAndroidSurface *target; /* ref fuerte durante el gesto (anti-dangling) */
} g_touch_f12 = {FALSE, FALSE, -1, 0.0, 0.0, 0.0, 0.0, 0, AMOTION_EVENT_TOOL_TYPE_UNKNOWN, NULL};

static guint g_touch_f12_lp_id = 0;

static void
g_touch_f12_remove_lp (void)
{
  if (g_touch_f12_lp_id != 0)
    {
      g_source_remove (g_touch_f12_lp_id);
      g_touch_f12_lp_id = 0;
    }
}

static gboolean
fase12_long_press_cb (gpointer user_data)
{
  (void) user_data;

  if (!g_touch_f12.pending || g_touch_f12.target == NULL)
    return G_SOURCE_REMOVE;

  /* el dedo se movio en exceso antes del deadline: es un drag, no long-press */
  gint64 now_ms = g_get_monotonic_time () / 1000;
  if (now_ms - g_touch_f12.down_ms < FASE12_LONG_PRESS_MS)
    return G_SOURCE_CONTINUE;

  /* click derecho en el punto DONDE ATERRIZO el dedo (menus de contexto). */
  GdkAndroidSurface *target = g_touch_f12.target; /* valido por la ref */
  GdkAndroidSurface *toplevel = (GdkAndroidSurface *) gdk_android_surface_get_toplevel (target);
  gfloat pcx = 0.0f, pcy = 0.0f;
  if (target != toplevel)
    gdk_android_surface_popup_offset (target, toplevel, &pcx, &pcy);

  g_touch_f12.pending = FALSE;
  g_clear_object (&g_touch_f12.target);

  GdkAndroidDisplay *display = (GdkAndroidDisplay *) gdk_surface_get_display ((GdkSurface *) target);
  GdkDevice *dev = gdk_seat_get_pointer ((GdkSeat *) display->seat);
  GdkAndroidDevice *dev_impl = GDK_ANDROID_DEVICE (dev);
  guint32 state = dev_impl->button_state | AMOTION_EVENT_BUTTON_SECONDARY;
  GdkModifierType mods = gdk_android_events_buttons_to_gdkmods (state);
  guint32 time = (guint32) now_ms;
  GdkDeviceTool *tool = gdk_android_seat_get_device_tool (display->seat, g_touch_f12.tool_type);

  g_debug ("FASE12-LONGPRESS target=%p [%s] ev=%.0f,%.0f",
           target, G_OBJECT_TYPE_NAME (target),
           g_touch_f12.down_x - pcx, g_touch_f12.down_y - pcy);

  GdkEvent *ev = gdk_button_event_new (GDK_BUTTON_PRESS, (GdkSurface *) target, dev, tool,
                                       time, mods, GDK_BUTTON_SECONDARY,
                                       g_touch_f12.down_x - pcx, g_touch_f12.down_y - pcy,
                                       NULL);
  gdk_android_seat_consume_event ((GdkDisplay *) display, ev);
  dev_impl->button_state = state;
  gdk_android_device_maybe_update_surface ((GdkAndroidDevice *) dev, target, mods, time,
                                           g_touch_f12.down_x - pcx, g_touch_f12.down_y - pcy);
  return G_SOURCE_REMOVE;
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
        "FASE12-LONGPRESS",
        "fase12_long_press_cb",
        "g_touch_f12",
        "g_touch_f12_remove_lp",
        "g_touch_f12.tracking",
        "g_touch_f12.pointer_id",
        "g_touch_f12.last_x",
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
    print("gtk4: FASE12 gestos estilo Blender + FASE11C-ROUTE aplicado en %s" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main())