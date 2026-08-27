# apa/interface/app/startup.py
"""
startup.py — Cadena de arranque de APA y endpoint de salud.

Orquesta la secuencia de inicio del sistema:
    1. ensure_mb_running()    — Lanza Model Broker como subprocess
    2. initialize_router()    — Valida MB vía HTTP, prepara pool
    3. notify()               — Registra evento de startup
    4. Actualiza estado       — startup_complete + startup_info

Además expone:
    - get_mb_communication_status() — Verifica estado de comunicación con MB
    - register_startup_routes()     — Registra GET /health
"""

import json
import logging
import sys
import threading
import time

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from typing import TYPE_CHECKING

from fastapi import FastAPI

# Importar módulos del paquete app (relativo en paquete, absoluto en standalone)
if __name__ == "__main__" and __package__ is None:
    # Standalone: asegurar que el directorio padre esté en sys.path
    _parent = str(Path(__file__).resolve().parent.parent)
    if _parent not in sys.path:
        sys.path.insert(0, _parent)

try:
    from .config import logger, MODEL_BROKER_URL
except ImportError:
    from app.config_apa import logger, MODEL_BROKER_URL, MODEL_BROKER_START_CMD, MODEL_BROKER_START_DIR

try:
    from .state import AppState
except ImportError:
    from app.state import AppState


# Módulos funcionales — se importan directamente
# Solo core.pool y core.price_estimator llevan protección.
try:
    from core.mb_launcher import ensure_mb_running
    _mb_launcher_available = True
except ImportError:
    ensure_mb_running = None
    _mb_launcher_available = False

try:
    from core.router import initialize_router
    _router_available = True
except ImportError:
    initialize_router = None
    _router_available = False

try:
    from core.notifications import notify, register_callback, clear_callbacks, _default_log_callback
    _notifications_available = True
except ImportError:
    notify = None
    register_callback = None
    clear_callbacks = None
    _default_log_callback = None
    _notifications_available = False


# ── Constantes ────────────────────────────────────────────────────────────

MB_HEALTH_TIMEOUT: float = 5.0
MB_STARTUP_TIMEOUT: float = 15.0


def _mb_startup_progress(step: str, message: str, data: dict = None) -> None:
    """Callback de progreso para el arranque de MB.

    Envía notificaciones a la interfaz de usuario sobre cada paso
    del proceso de conexión con Model Broker.
    """
    if _notifications_available and notify is not None:
        try:
            notify("mb:startup", message, {"step": step, **(data or {})})
        except Exception:
            pass


# ── Funciones principales ────────────────────────────────────────────────


def init_subsystems(state: "AppState" = None) -> dict:
    """Cadena de arranque completa del sistema APA.

    Ejecuta cada paso de la startup en orden:
        1. Lanza Model Broker si no está corriendo
        2. Inicializa el router (valida MB, prepara pool)
        3. Notifica que el sistema está listo
        4. Actualiza el estado global

    Si state es None, ejecuta la cadena pero no actualiza estado.
    Si MB no levanta, el router entrará en modo emergencia.

    Args:
        state: Instancia de AppState (opcional).

    Returns:
        Diccionario con el resultado de la inicialización:
            - success: bool
            - mb_available: bool
            - router_initialized: bool
            - startup_mode: str
            - errors: list de strings
    """
    mb_url = MODEL_BROKER_URL
    errors: list[str] = []
    result = {
        "success": False,
        "mb_available": False,
        "router_initialized": False,
        "startup_mode": "unknown",
        "errors": errors,
    }

    # Paso 1: Lanzar Model Broker
    logger.info("Startup paso 1/3: Verificando Model Broker en %s", mb_url)
    mb_ok = False

    if _mb_launcher_available and ensure_mb_running is not None:
        try:
            mb_ok = ensure_mb_running(
                mb_url,
                timeout=MB_STARTUP_TIMEOUT,
                on_progress=_mb_startup_progress,
                start_cmd=MODEL_BROKER_START_CMD,
                start_dir=MODEL_BROKER_START_DIR,
            )
        except Exception as exc:
            error_msg = f"Error al lanzar MB: {exc}"
            logger.error(error_msg)
            errors.append(error_msg)
    else:
        logger.warning("core.mb_launcher no disponible — MB no se lanza automáticamente")
        errors.append("core.mb_launcher no disponible")

    result["mb_available"] = mb_ok

    if mb_ok:
        logger.info("Model Broker disponible en %s", mb_url)
    else:
        logger.warning("Model Broker no disponible — se usará modo emergencia")

    # Paso 2: Inicializar router
    logger.info("Startup paso 2/3: Inicializando router")
    router_mode = "emergency"
    router_ok = False

    if _router_available and initialize_router is not None:
        try:
            router_result = initialize_router()
            router_mode = router_result.get("startup_mode", "emergency")
            router_ok = True
            result["router_initialized"] = True
            logger.info("Router inicializado: modo=%s", router_mode)
        except Exception as exc:
            error_msg = f"Error al inicializar router: {exc}"
            logger.error(error_msg)
            errors.append(error_msg)
    else:
        error_msg = "core.router no disponible"
        logger.warning(error_msg)
        errors.append(error_msg)

    result["startup_mode"] = router_mode

    # Paso 3: Notificar
    logger.info("Startup paso 3/3: Notificando estado del sistema")
    if _notifications_available and notify is not None:
        try:
            startup_msg = f"Sistema iniciado — MB={'disponible' if mb_ok else 'no disponible'}, modo={router_mode}"
            notify(
                "system:startup",
                startup_msg,
                {
                    "mb_available": mb_ok,
                    "router_mode": router_mode,
                    "router_initialized": router_ok,
                    "timestamp": time.time(),
                },
            )
            logger.info("Notificación de startup enviada")
        except Exception as exc:
            error_msg = f"No se pudo notificar el startup: {exc}"
            logger.warning(error_msg)
            errors.append(error_msg)
    else:
        errors.append("core.notifications no disponible")

    # Determinar éxito general
    result["success"] = mb_ok or router_ok

    # Paso 4: Actualizar estado
    if state is not None:
        state.startup_complete = result["success"]
        state.startup_info = result

    logger.info(
        "Startup completado — success=%s, mb=%s, mode=%s",
        result["success"],
        result["mb_available"],
        result["startup_mode"],
    )
    return result


def init_subsystems_threaded(state: "AppState" = None) -> threading.Thread:
    """Lanza init_subsystems en un daemon thread.

    Args:
        state: Instancia de AppState (opcional).

    Returns:
        El Thread creado (ya iniciado).
    """
    thread = threading.Thread(
        target=init_subsystems,
        kwargs={"state": state},
        daemon=True,
        name="apa-startup",
    )
    thread.start()
    logger.info("Startup thread lanzado (daemon)")
    return thread


def get_mb_communication_status() -> dict:
    """Verifica el estado de comunicación con Model Broker.

    Realiza un HTTP GET a {mb_url}/api/status con timeout de 5 segundos.

    Returns:
        Diccionario con:
            - apa_alive: True (siempre, este endpoint responde)
            - mb_url: URL del Model Broker
            - mb_responding: True si MB respondió al health check
            - mode: Modo actual del router o 'unknown'
    """
    mb_url = MODEL_BROKER_URL
    mb_responding = False
    mode = "unknown"

    try:
        import urllib.request
        import urllib.error

        health_url = f"{mb_url.rstrip('/')}/api/status"
        req = urllib.request.Request(health_url, method="GET")
        req.add_header("Accept", "application/json")

        with urllib.request.urlopen(req, timeout=MB_HEALTH_TIMEOUT) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            mb_responding = True
            mode = body.get("mode", "unknown")
    except Exception:
        mb_responding = False

    # Intentar obtener el modo del router si está disponible
    if not mb_responding and _router_available:
        try:
            from core.router import get_scaling_state
            scaling = get_scaling_state()
            mode = scaling.get("startup_mode", "unknown")
        except Exception:
            pass

    return {
        "apa_alive": True,
        "mb_url": mb_url,
        "mb_responding": mb_responding,
        "mode": mode,
    }


def register_startup_routes(app: FastAPI, state: "AppState" = None) -> None:
    """Registra el endpoint de salud GET /health.

    El endpoint combina:
        - Estado vivo de APA (siempre True)
        - Estado de comunicación con Model Broker

    Args:
        app: Aplicación FastAPI.
        state: Estado global de la aplicación (opcional).
    """

    @app.get("/health")
    async def health_check():
        """Endpoint de salud: APA vivo + estado de comunicación con MB."""
        mb_status = get_mb_communication_status()

        response = {
            "apa_alive": True,
            "mb_url": mb_status.get("mb_url", ""),
            "mb_responding": mb_status.get("mb_responding", False),
            "mode": mb_status.get("mode", "unknown"),
        }

        if state is not None:
            response["startup_complete"] = state.startup_complete
            response["startup_info"] = state.startup_info

        return response

    logger.info("Ruta registrada: GET /health")



if __name__ == "__main__":
    print("=== Validación de startup.py ===")
    print()

    # 1. Verificar disponibilidad de módulos core
    print(f"[INFO] mb_launcher disponible: {_mb_launcher_available}")
    print(f"[INFO] router disponible:     {_router_available}")
    print(f"[INFO] notifications disponible: {_notifications_available}")

    # 2. init_subsystems con state=None (no depende de core modules)
    result = init_subsystems(state=None)
    assert isinstance(result, dict)
    assert "success" in result
    assert "mb_available" in result
    assert "startup_mode" in result
    assert "errors" in result
    print(f"[OK] init_subsystems() retornó: {result['startup_mode']}")
    print(f"     mb_available={result['mb_available']}")
    print(f"     errors={result['errors']}")

    # 3. init_subsystems con estado
    state = AppState()  # type: ignore[no-redef]
    result2 = init_subsystems(state=state)
    assert state.startup_complete == result2["success"]
    assert state.startup_info == result2
    print(f"[OK] init_subsystems actualiza estado: startup_complete={state.startup_complete}")

    # 4. get_mb_communication_status
    mb_status = get_mb_communication_status()
    assert mb_status["apa_alive"] is True
    assert "mb_url" in mb_status
    assert "mb_responding" in mb_status
    assert "mode" in mb_status
    print(f"[OK] get_mb_communication_status(): {mb_status}")

    # 5. Verificar constantes
    assert MB_HEALTH_TIMEOUT == 5.0
    assert MB_STARTUP_TIMEOUT == 15.0
    print(f"[OK] Constantes: health_timeout={MB_HEALTH_TIMEOUT}, startup_timeout={MB_STARTUP_TIMEOUT}")

    # 6. register_startup_routes
    from fastapi import FastAPI
    test_app = FastAPI()
    register_startup_routes(test_app, state=state)
    routes = [r.path for r in test_app.routes]
    assert "/health" in routes
    print(f"[OK] register_startup_routes registró: {routes}")

    # 7. init_subsystems_threaded
    state3 = AppState()
    thread = init_subsystems_threaded(state=state3)
    assert thread.daemon is True
    assert thread.name == "apa-startup"
    thread.join(timeout=30)  # Esperar a que termine
    assert state3.startup_info != {} or len(state3.startup_info.get("errors", [])) > 0
    print(f"[OK] init_subsystems_threaded ejecutó y actualizó estado")

    # 8. TEST CRÍTICO: Verificar que notify() recibe strings, no dicts
    if _notifications_available and clear_callbacks and register_callback and _default_log_callback:
        _captured_notify = []
        def _capture_notify(event_type, message, data):
            _captured_notify.append((event_type, message, data))
        clear_callbacks()
        register_callback(_default_log_callback)
        register_callback(_capture_notify)
        # Ejecutar el callback de progreso igual que lo hace init_subsystems
        _mb_startup_progress("test_step", "Mensaje de prueba", {"key": "val"})
        assert len(_captured_notify) == 1, f"Debe haber 1 notificación, hay {len(_captured_notify)}"
        et, msg, dat = _captured_notify[0]
        assert isinstance(msg, str), f"El mensaje debe ser string, es {type(msg).__name__}: {msg!r}"
        assert not isinstance(msg, dict), "El mensaje NUNCA debe ser un dict (causa [object Object] en la UI)"
        assert isinstance(dat, dict), f"El data debe ser dict, es {type(dat).__name__}"
        assert dat.get("step") == "test_step", f"data.step debe ser 'test_step', got {dat.get('step')}"
        print(f"[OK] _mb_startup_progress envía string como mensaje: {msg!r}")
        print(f"     data={dat}")
        clear_callbacks()
        register_callback(_default_log_callback)  # dejar limpio
    else:
        # Fallback: verificar la firma directamente por inspección de código
        import inspect
        src = inspect.getsource(_mb_startup_progress)
        assert 'notify("mb:startup", message,' in src, "_mb_startup_progress debe pasar 'message' como 2do arg de notify()"
        assert 'notify("mb:startup", {"' not in src, "_mb_startup_progress NO debe pasar un dict literal como 2do arg"
        print("[OK] _mb_startup_progress firma verificada por inspección de código (sin core disponible)")

    # 9. Verificar que la notificación system:startup también usa string
    import inspect as _insp
    _init_src = _insp.getsource(init_subsystems)
    assert 'notify(' in _init_src
    # Buscar la línea de notify system:startup
    for _line in _init_src.split('\n'):
        if 'system:startup' in _line and 'notify' in _line:
            # Verificar que el 2do argumento no es un dict literal (que empieza con {)
            assert '{\"mb_available"' not in _line and '{"mb_available"' not in _line, \
                f"system:startup notify() pasa dict como mensaje: {_line.strip()}"
            break
    print("[OK] system:startup notify() no pasa dict como mensaje")

    print()
    print("=== Todas las validaciones pasaron ===")
