# apa/core/notifications.py
# v2.0 — Sistema de notificaciones en segundo plano.
#
# v2.0: Eliminados EVT_HEALTH_*, EVT_ARENA_*, EVT_POOL_* (módulos
#       reemplazados por Model Broker). Agregado EVT_EMERGENCY_MODE
#       para router v7.0.
#
#         Permite que los módulos de APA (agentes, sistema)
#         emitan eventos estructurados cuando ocurren acciones en background.
#         Cualquier UI (terminal, GUI del ensamblador) puede suscribirse
#         para mostrar al usuario lo que está pasando.
#
#         Los eventos NO bloquean — se ejecutan en el hilo del emisor.
#         Los errores de los callbacks se capturan silenciosamente.
#
# USO (emisor):
#   from core.notifications import notify, EVT_EMERGENCY_MODE
#   notify(EVT_EMERGENCY_MODE, "MB no disponible, modo emergencia", {"reason": "timeout"})
#
# USO (receptor / UI):
#   from core.notifications import register_callback, EVT_*
#   def on_event(event_type, message, data):
#       status_bar.update(f"{message}")
#   register_callback(on_event)
#
# ARCHIVO: notifications.py
# DESTINO: C:\Python\Proyectos\APA\apa\core\notifications.py

import threading
import time
from typing import Callable, Dict, Any, List, Optional


# ============================================================================
# Tipos de eventos — constantes para identificar cada tipo
# ============================================================================

# --- emergency mode (router v7.0) ---
EVT_EMERGENCY_MODE = "system:emergency_mode"                # MB no disponible, operando con recursos mínimos

# --- agent lifecycle (Fase 4: Dashboard de agentes UX2) ---
EVT_AGENT_STARTED  = "agent:started"                          # Agente fase iniciada (planner/coder/integrator/validator)
EVT_AGENT_PROGRESS = "agent:progress"                         # Progreso del agente (tokens, pct)
EVT_AGENT_DONE     = "agent:done"                             # Agente fase completada con éxito
EVT_AGENT_FAILED   = "agent:failed"                            # Agente fase fallida

# --- general ---
EVT_SYSTEM_SHUTDOWN = "system:shutdown"                        # APA cerrándose (atexit)
EVT_SYSTEM_ERROR = "system:error"                              # Error no recuperable
EVT_SYSTEM_STARTUP = "system:startup"                          # Evento de inicio/conexion


# ============================================================================
# Tipo del callback: (event_type, message, data) -> None
# ============================================================================
NotificationCallback = Callable[[str, str, Dict[str, Any]], None]


# ============================================================================
# Registro de callbacks (thread-safe)
# ============================================================================

_callbacks: List[NotificationCallback] = []
_callback_lock = threading.Lock()


def register_callback(cb: NotificationCallback) -> None:
    """Registra un callback para recibir todos los eventos.

    El callback recibe:
      - event_type: str — una de las constantes EVT_*
      - message: str — mensaje legible para el usuario
      - data: dict — datos estructurados del evento

    El callback se ejecuta en el hilo del emisor. Debe ser rápido.
    Errores dentro del callback se capturan silenciosamente.
    """
    with _callback_lock:
        if cb not in _callbacks:
            _callbacks.append(cb)


def unregister_callback(cb: NotificationCallback) -> bool:
    """Elimina un callback. Retorna True si existía."""
    with _callback_lock:
        if cb in _callbacks:
            _callbacks.remove(cb)
            return True
    return False


def clear_callbacks() -> int:
    """Elimina todos los callbacks. Retorna cuántos había."""
    with _callback_lock:
        count = len(_callbacks)
        _callbacks.clear()
        return count


def get_callback_count() -> int:
    """Retorna el número de callbacks registrados."""
    with _callback_lock:
        return len(_callbacks)


# ============================================================================
# Emisión de eventos
# ============================================================================

_last_events: List[Dict[str, Any]] = []  # Buffer de últimos N eventos
_event_buffer_size = 300
_event_lock = threading.Lock()


def notify(event_type: str, message: str, data: Dict[str, Any] = None) -> None:
    """Emite un evento a todos los callbacks registrados.

    Thread-safe. No bloquea. Errores de callbacks se capturan.
    También almacena el evento en un buffer circular para consulta posterior.
    """
    event = {
        "type": event_type,
        "message": message,
        "data": data or {},
        "timestamp": time.time(),
    }

    # Guardar en buffer circular
    with _event_lock:
        _last_events.append(event)
        if len(_last_events) > _event_buffer_size:
            _last_events.pop(0)

    # Notificar a callbacks (copia para thread-safety)
    with _callback_lock:
        callbacks = list(_callbacks)

    for cb in callbacks:
        try:
            cb(event["type"], event["message"], event["data"])
        except Exception:
            pass  # No dejar que un callback roto rompa el flujo


def get_recent_events(n: int = 20) -> List[Dict[str, Any]]:
    """Retorna los últimos N eventos del buffer.

    Útil para que una UI muestre el historial de notificaciones
    cuando se conecta después de que ya empezó el background.
    """
    with _event_lock:
        events = list(_last_events)
    return events[-n:]


def get_events_by_type(event_type: str) -> List[Dict[str, Any]]:
    """Retorna todos los eventos del buffer de un tipo específico."""
    with _event_lock:
        return [e for e in _last_events if e["type"] == event_type]


# ============================================================================
# Callback de conveniencia: log automático
# ============================================================================

def _default_log_callback(event_type: str, message: str, data: Dict[str, Any]) -> None:
    """Callback por defecto: envía eventos al logger.

    Solo se registra si no hay otros callbacks (para no duplicar
    cuando una UI ya maneja las notificaciones).
    """
    import logging
    logger = logging.getLogger("apa.notifications")
    # Los eventos importantes van a INFO, los detallados a DEBUG
    important_events = {
        EVT_SYSTEM_SHUTDOWN, EVT_SYSTEM_ERROR, EVT_SYSTEM_STARTUP,
        EVT_EMERGENCY_MODE,
        EVT_AGENT_STARTED, EVT_AGENT_PROGRESS, EVT_AGENT_DONE, EVT_AGENT_FAILED,
    }
    level = logging.INFO if event_type in important_events else logging.DEBUG
    logger.log(level, f"[{event_type}] {message}")


# Registrar callback de log por defecto
# Las UIs pueden usar unregister_callback(_default_log_callback) si quieren
# controlar toda la salida
register_callback(_default_log_callback)


# ============================================================================
# Test standalone
# ============================================================================

if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.DEBUG,
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    print("\n" + "=" * 60)
    print("TEST: Notifications v2.0")
    print("=" * 60)

    collected = []

    def test_cb(event_type, message, data):
        collected.append((event_type, message, data))

    # Test 1: Registrar callback
    register_callback(test_cb)
    assert get_callback_count() >= 2  # test_cb + default_log_callback
    print("  [PASS] Callback registrado")

    # Test 2: Emitir evento
    notify(EVT_EMERGENCY_MODE, "MB no disponible",
           {"reason": "timeout"})
    assert len(collected) == 1
    assert collected[0][0] == EVT_EMERGENCY_MODE
    assert collected[0][1] == "MB no disponible"
    assert collected[0][2]["reason"] == "timeout"
    print("  [PASS] notify() envía datos correctos al callback")

    # Test 3: Múltiples eventos
    notify(EVT_AGENT_STARTED, "Agente iniciado", {"agent": "planner"})
    notify(EVT_AGENT_DONE, "Agente completado")
    assert len(collected) == 3
    print("  [PASS] Múltiples notify() acumulan en collected")

    # Test 4: get_recent_events
    recent = get_recent_events(2)
    assert len(recent) == 2
    assert recent[0]["type"] == EVT_AGENT_STARTED
    assert recent[1]["type"] == EVT_AGENT_DONE
    print("  [PASS] get_recent_events(2) retorna los últimos 2")

    # Test 5: get_events_by_type
    all_emergency = get_events_by_type(EVT_EMERGENCY_MODE)
    assert len(all_emergency) == 1
    print("  [PASS] get_events_by_type() filtra correctamente")

    # Test 6: unregister_callback
    unregister_callback(test_cb)
    assert get_callback_count() >= 1  # default_log_callback sigue
    notify(EVT_SYSTEM_ERROR, "Error de prueba", {"code": 500})
    assert len(collected) == 3  # No se añadió (desregistrado)
    print("  [PASS] unregister_callback() detiene la recepción")

    # Test 7: Callback roto no rompe el flujo
    def broken_cb(event_type, message, data):
        raise ValueError("Soy un callback roto")

    register_callback(broken_cb)
    notify(EVT_SYSTEM_ERROR, "Error de prueba", {})  # No debe lanzar
    print("  [PASS] Callback roto capturado silenciosamente")
    unregister_callback(broken_cb)

    # Test 8: clear_callbacks
    count_before = get_callback_count()
    cleared = clear_callbacks()
    assert get_callback_count() == 0
    assert cleared == count_before
    # Re-registrar el default para dejar el módulo limpio
    register_callback(_default_log_callback)
    print("  [PASS] clear_callbacks() elimina todos")

    print("\n" + "=" * 60)
    # Test 9: Nuevos tipos de evento v2.0
    assert EVT_EMERGENCY_MODE == "system:emergency_mode"
    assert EVT_SYSTEM_STARTUP == "system:startup"
    print("  [PASS] EVT_EMERGENCY_MODE definido correctamente (v2.0)")

    print("\n" + "=" * 60)
    print("  TODOS LOS TESTS PASARON — Notifications v2.0 OK")
    print("=" * 60)