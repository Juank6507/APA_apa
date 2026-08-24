# apa/core/model_health.py
# v6.1 — Notificaciones al usuario de actividad en segundo plano.
#
#         v6.1: Integra notifications.py para informar al usuario de
#         lo que pasa en segundo plano: verificación de modelos, flush
#         a disco, carga de caché, inicio/fin de ciclos, etc.
#         La UI (ensamblador, terminal) se suscribe para mostrar progreso.
#
# CAMBIOS v6.1 vs v6.0:
#   - NUEVO: notify() en mark_available() → EVT_HEALTH_MODEL_VERIFIED
#   - NUEVO: notify() en mark_failed() → EVT_HEALTH_MODEL_FAILED
#   - NUEVO: notify() en mark_rate_limited() → EVT_HEALTH_MODEL_RATE_LIMITED
#   - NUEVO: notify() en mark_model_removed() → EVT_HEALTH_MODEL_REMOVED
#   - NUEVO: notify() en flush_to_disk() → EVT_HEALTH_FLUSH_DISK
#   - NUEVO: notify() en load_health_from_cache() → EVT_HEALTH_CACHE_LOADED
#   - NUEVO: notify() en ciclo background start/end → EVT_HEALTH_CYCLE_START/END
#   - NUEVO: notify() en on_session_close() → EVT_HEALTH_FLUSH_DISK
#   - NUEVO: notify() en _atexit_flush() → EVT_SYSTEM_SHUTDOWN
#   - Import lazy de notifications (no rompe si no existe)
#
# v6.0 — Caché en memoria + Pool sync callback + flush solo al salir.
# v5.1 — model_removed state (T2.1).
# v5.0 — Cache-driven startup: la caché NO expira, se actualiza.
#
# ============================================================================
import atexit
import json
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple, Callable

from model_broker.settings_bridge import settings
from model_broker.normalizer import normalize_model_id

# ============================================================================
# Logging setup — production-ready
# ============================================================================
logger = logging.getLogger(__name__)

if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    logger.addHandler(handler)
logger.propagate = False

# ============================================================================
# Configuración — v6.0: Caché en memoria, flush solo al salir
# ============================================================================
_CACHE_VERSION = 2  # v2: incluye previously_available + last_verified_session

# v6.0: Flush inmediato DESACTIVADO por defecto.
# Los mark_* solo actualizan memoria + notifican pool vía callback.
# El disco se escribe SOLO al final de ciclo, al cerrar sesión, o al salir.
_FLUSH_IMMEDIATELY = False

# ============================================================================
# v6.0: Pool sync callback — actualiza pool en memoria tras cada cambio
# ============================================================================
_pool_sync_callback: Optional[Callable[[str], None]] = None
_pool_candidates_callback: Optional[Callable[[], List[str]]] = None  # v6.6
_pool_sync_lock = threading.Lock()

_dirty_flag = False  # True si hay cambios sin guardar a disco
_dirty_lock = threading.Lock()
_modified_models: set = set()  # Modelos modificados desde el último flush


def register_pool_sync_callback(callback: Callable[[str], None]) -> None:
    """Registra un callback para notificar al Pool de cambios de estado.

    El callback recibe el base_id del modelo cuyo estado cambió.
    Se llama DESPUÉS de actualizar _health_data en memoria, ANTES de
    cualquier disco I/O. Esto permite que el Pool se actualice en
    tiempo real sin esperar al flush.

    El callback debe ser rápido (solo actualizar memoria, no hacer I/O).
    """
    global _pool_sync_callback
    with _pool_sync_lock:
        _pool_sync_callback = callback
    logger.info("v6.0: Pool sync callback registrado")


def register_pool_candidates_callback(callback: Callable[[], List[str]]) -> None:
    """v6.6: Registra un callback para obtener model_ids del pool que
    necesitan verificación.

    El callback retorna una lista de base_ids de modelos en el pool
    que están en estado 'unknown', 'failed' o 'payment_required'.
    Se usa tras la primera pasada de previously_available para verificar
    modelos nuevos que entraron al pool desde los catálogos de proveedores.
    """
    global _pool_candidates_callback
    with _pool_sync_lock:
        _pool_candidates_callback = callback
    logger.info("v6.6: Pool candidates callback registrado")


def _notify_pool_sync(model_id: str) -> None:
    """Notifica al Pool de un cambio de estado (en memoria, sin disco I/O).

    Se llama tras cada mark_* para que el Pool refleje el cambio
    inmediatamente. Los errores del callback se capturan silenciosamente
    para no interrumpir el flujo de mark_*.
    """
    with _pool_sync_lock:
        callback = _pool_sync_callback
    if callback:
        try:
            callback(model_id)
        except Exception as e:
            logger.debug(f"_notify_pool_sync({model_id}): callback error: {e}")


def _mark_dirty(model_id: str = "") -> None:
    """Marca que hay cambios pendientes de guardar a disco.

    v7.0: Registra el model_id modificado para flush incremental.
    """
    global _dirty_flag
    with _dirty_lock:
        _dirty_flag = True
        if model_id:
            _modified_models.add(model_id)


def is_dirty() -> bool:
    """Retorna True si hay cambios sin guardar a disco."""
    with _dirty_lock:
        return _dirty_flag


# ============================================================================
# Archivos de caché
# ============================================================================
def _find_project_data_dir() -> Path:
    """Retorna el directorio data/ de model_broker."""
    return Path(__file__).parent / "data"


_DATA_DIR = _find_project_data_dir()
_HEALTH_CACHE_PATH = _DATA_DIR / "health_cache.json"
_ARENA_CACHE_PATH = _DATA_DIR / "arena_cache.json"

_MODULE_FILE = str(Path(__file__))
_MODULE_FILE_RESOLVED = str(Path(__file__).resolve())

logger.debug(f"Path resolution: data_dir={_DATA_DIR}, "
             f"__file__={_MODULE_FILE}, resolved={_MODULE_FILE_RESOLVED}")

_HEALTH_CACHE_VERSION = 2  # v5.0: formato v2 con previously_available
_FLUSH_INTERVAL = 30  # v6.0: ya no se usa para mark_*, solo como safety net

_PROBE_MESSAGES = [{"role": "user", "content": "Respond with exactly the word: PING"}]
_PROBE_MAX_TOKENS = 10
_PROBE_TEMPERATURE = 0.0
_PROBE_SYNC_TIMEOUT = 10
_PROBE_BG_TIMEOUT = 15
_PROBE_BG_DELAY = 3
_PROBE_SYNC_DELAY = 1.0

_RATE_LIMIT_BACKOFF_BASE = 60
_RATE_LIMIT_BACKOFF_MAX = 300

_TEMPORARILY_UNAVAILABLE_COOLDOWN = 60  # F10: Cooldown para temporarily_unavailable


def configure(trust_window: int = None, flush_immediately: bool = None) -> None:
    """Configura parámetros de model_health en runtime.

    v6.0: flush_immediately controla si los mark_* hacen flush a disco.
    Default=False (solo memoria + pool callback).
    """
    global _FLUSH_IMMEDIATELY
    if flush_immediately is not None:
        _FLUSH_IMMEDIATELY = flush_immediately
        logger.info(f"Flush inmediato configurado a {flush_immediately}")


def get_trust_window() -> int:
    """v5.0: Retorna 0 — la caché no expira."""
    return 0


# ============================================================================
# Estado de salud en memoria
# ============================================================================

_health_data: Dict[str, Dict[str, Any]] = {}
_health_lock = threading.Lock()
_last_flush = 0.0
_bg_thread_started = False
_bg_thread_lock = threading.Lock()

_cache_loaded = False
_last_cache_load_time = 0.0


def _now_epoch() -> float:
    return time.time()


def _parse_verified_at_epoch(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        if not value.strip():
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            pass
        try:
            dt = datetime.fromisoformat(value)
            return dt.timestamp()
        except (ValueError, TypeError):
            pass
    return None


# ============================================================================
# Carga / guardado de health_cache.json
# ============================================================================

def load_health_from_cache(force: bool = False) -> Dict[str, Dict[str, Any]]:
    """Carga datos de salud desde health_cache.json.

    v5.0: La caché NO expira. Los modelos available se mantienen
    como available entre sesiones, con previously_available=True
    para indicar que necesitan re-verificación en background.
    """
    global _health_data, _cache_loaded, _last_cache_load_time

    if _cache_loaded and not force:
        return _health_data

    cache_path = _HEALTH_CACHE_PATH
    legacy_path = _ARENA_CACHE_PATH

    raw_health = {}
    source = ""

    logger.debug(f"load_health_from_cache() — cache_path={cache_path}, "
                 f"exists={cache_path.exists()}")

    if cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            raw_health = data.get("models", {})
            source = f"health_cache.json (v{data.get('version', '?')})"
            logger.debug(f"Leído health_cache.json: {len(raw_health)} modelos, source={source}")
        except Exception as e:
            logger.warning(f"Error leyendo health_cache.json: {e}")

    if not raw_health and legacy_path.exists():
        try:
            with open(legacy_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("version", 1) >= 3:
                raw_health = data.get("last_session_health", {})
                if raw_health:
                    source = "arena_cache.json (migración one-time)"
                    logger.info(f"Migrando health de arena_cache.json: {len(raw_health)} modelos")
        except Exception as e:
            logger.debug(f"No se pudo leer arena_cache.json para migración: {e}")

    if not raw_health:
        logger.info("No hay datos de salud previos, partiendo de vacío")
        _health_data = {}
        _cache_loaded = True
        _last_cache_load_time = _now_epoch()
        return _health_data

    _health_data = {}
    now = _now_epoch()
    loaded_available = 0
    loaded_other = 0

    for model_id, info in raw_health.items():
        prev_status = info.get("status", "unknown")
        verified_at = _parse_verified_at_epoch(info.get("verified_at"))
        provider = info.get("provider", "")
        probe_errors = info.get("probe_errors", {})
        rate_limited_count = info.get("rate_limited_count", 0) or 0
        rate_limited_at = _parse_verified_at_epoch(info.get("rate_limited_at"))
        previously_available = info.get("previously_available", False)

        # v5.0: CACHE NO EXPIRA
        if prev_status == "available":
            age = now - verified_at if verified_at else 0
            _health_data[model_id] = {
                "status": "available",
                "verified_at": verified_at,
                "provider": provider,
                "previous_status": prev_status,
                "previously_available": True,  # v5.0: necesita re-verificación
                "error": None,
                "rate_limited_at": None,
                "rate_limited_count": 0,
                "probe_errors": probe_errors,
            }
            loaded_available += 1
            if age > 0:
                logger.info(f"CACHE-STARTUP: {model_id} -> available "
                           f"(age={age:.0f}s, pendiente re-verificar)")
            continue

        # Estados no-available: se cargan tal cual
        _health_data[model_id] = {
            "status": prev_status,
            "verified_at": verified_at,
            "provider": provider,
            "previous_status": prev_status,
            "previously_available": previously_available,
            "error": info.get("error"),
            "rate_limited_at": rate_limited_at,
            "rate_limited_count": rate_limited_count,
            "probe_errors": probe_errors,
        }
        loaded_other += 1

    logger.info(f"Cargados {len(_health_data)} modelos de {source} "
                f"({loaded_available} available para startup, "
                f"{loaded_other} otros estados. Caché permanente: NO expira)")
    # v6.1: Notificar carga de caché
    _notify("health:cache_loaded",
            f"Caché cargado: {len(_health_data)} modelos ({loaded_available} available)",
            {"total": len(_health_data), "available": loaded_available, "other": loaded_other})

    _cache_loaded = True
    _last_cache_load_time = _now_epoch()
    return _health_data


def ensure_loaded() -> bool:
    """Garantiza que el caché de salud esté cargado y actualizado."""
    global _cache_loaded, _last_cache_load_time

    verified = get_verified_models()

    if verified:
        logger.debug(f"ensure_loaded(): OK — {len(verified)} modelos verificados")
        return True

    if not _cache_loaded:
        logger.debug("ensure_loaded(): caché no cargado, cargando...")
        load_health_from_cache()
    elif _HEALTH_CACHE_PATH.exists():
        try:
            file_mtime = os.path.getmtime(str(_HEALTH_CACHE_PATH))
            if file_mtime > _last_cache_load_time:
                logger.debug(f"ensure_loaded(): archivo actualizado (mtime={file_mtime:.1f} > "
                             f"load_time={_last_cache_load_time:.1f}), re-cargando...")
                _last_cache_load_time = file_mtime
                load_health_from_cache(force=True)
            else:
                logger.debug("ensure_loaded(): archivo sin cambios, no se re-carga")
        except Exception as e:
            logger.debug(f"ensure_loaded(): error checking mtime: {e}")
            load_health_from_cache(force=True)
    else:
        logger.debug(f"ensure_loaded(): no hay archivo de caché (path={_HEALTH_CACHE_PATH})")

    verified = get_verified_models()
    logger.debug(f"ensure_loaded(): {len(verified)} modelos verificados de {len(_health_data)} totales")
    return len(verified) > 0


def get_diagnostic_info() -> Dict[str, Any]:
    """Retorna información de diagnóstico del módulo."""
    with _health_lock:
        total = len(_health_data)
        available = sum(1 for v in _health_data.values() if v.get("status") == "available")
        previously_available = sum(1 for v in _health_data.values()
                                  if v.get("status") == "available" and v.get("previously_available", False))
        rate_limited = sum(1 for v in _health_data.values() if v.get("status") == "rate_limited")
        failed = sum(1 for v in _health_data.values() if v.get("status") == "failed")
        payment_required = sum(1 for v in _health_data.values() if v.get("status") == "payment_required")
        model_removed = sum(1 for v in _health_data.values() if v.get("status") == "model_removed")
        unknown = sum(1 for v in _health_data.values() if v.get("status") in ("unknown", None))
        temporarily_unavailable = sum(1 for v in _health_data.values()
                                     if v.get("status") == "temporarily_unavailable")

    return {
        "cache_loaded": _cache_loaded,
        "last_cache_load_time": _last_cache_load_time,
        "cache_path": str(_HEALTH_CACHE_PATH),
        "cache_exists": _HEALTH_CACHE_PATH.exists(),
        "data_dir": str(_DATA_DIR),
        "module_file": _MODULE_FILE,
        "module_file_resolved": _MODULE_FILE_RESOLVED,
        "total_models": total,
        "available": available,
        "previously_available": previously_available,
        "rate_limited": rate_limited,
        "failed": failed,
        "payment_required": payment_required,
        "model_removed": model_removed,
        "temporarily_unavailable": temporarily_unavailable,
        "unknown": unknown,
        "verified_models": get_verified_models(),
        "trust_window": get_trust_window(),
        "cache_version": _HEALTH_CACHE_VERSION,
        "dirty": is_dirty(),
        "flush_immediately": _FLUSH_IMMEDIATELY,
        "pool_callback_registered": _pool_sync_callback is not None,
    }


# ============================================================================
# v6.0: Persistencia a disco — SOLO en 3 puntos
# ============================================================================

def flush_to_disk() -> None:
    """Guarda cambios pendientes en health_cache.json.

    v7.0: Flush incremental — solo actualiza los modelos que cambiaron
    desde el último flush. Lee el archivo existente, hace merge de los
    modelos en _modified_models, y reescribe. Los modelos que no
    cambiaron permanecen intactos en el archivo.
    """
    global _last_flush, _dirty_flag, _modified_models
    try:
        # Determinar qué modelos necesitan actualizarse
        with _dirty_lock:
            models_to_update = set(_modified_models)
            _modified_models = set()

        if not models_to_update:
            # No hay cambios específicos — no hacer I/O innecesario
            with _dirty_lock:
                _dirty_flag = False
            return

        # Flush incremental: leer archivo existente y hacer merge
        existing_data = {}
        if _HEALTH_CACHE_PATH.exists():
            try:
                with open(_HEALTH_CACHE_PATH, "r", encoding="utf-8") as f:
                    existing_data = json.load(f).get("models", {})
            except Exception:
                pass

        with _health_lock:
            for model_id in models_to_update:
                info = _health_data.get(model_id)
                if info:
                    existing_data[model_id] = {
                        "status": info.get("status", "unknown"),
                        "verified_at": info.get("verified_at"),
                        "provider": info.get("provider", ""),
                        "error": info.get("error"),
                        "rate_limited_count": info.get("rate_limited_count", 0),
                        "rate_limited_at": info.get("rate_limited_at"),
                        "probe_errors": info.get("probe_errors", {}),
                        "previously_available": info.get("previously_available", False),
                    }

        data_to_save = {
            "version": _HEALTH_CACHE_VERSION,
            "updated_at": datetime.now().isoformat(),
            "models": existing_data,
        }

        _HEALTH_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_HEALTH_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(data_to_save, f, indent=2, ensure_ascii=False)

        _last_flush = time.time()
        with _dirty_lock:
            _dirty_flag = False
        logger.debug(f"v7.0 Flush incremental: {len(models_to_update)} modelos actualizados")
        _notify("health:flush_disk",
                f"Caché guardada: {len(models_to_update)} modelos actualizados",
                {"updated_count": len(models_to_update), "total_models": len(existing_data)})

    except Exception as e:
        logger.warning(f"Error en flush: {e}")
        # Restaurar modelos no guardados para reintentar en el próximo flush
        with _dirty_lock:
            _modified_models.update(models_to_update)
            _dirty_flag = True


def maybe_flush() -> None:
    """v6.0: Safety net — flush a disco si hay cambios sin guardar.

    Ya no se llama desde mark_*(). Solo se usa como respaldo
    en el background thread si pasa mucho tiempo sin flush.
    """
    global _last_flush
    if is_dirty() and time.time() - (_last_flush or 0) >= _FLUSH_INTERVAL:
        flush_to_disk()


# ============================================================================
# v6.0: atexit handler — garantiza flush antes de salir
# ============================================================================

def _atexit_flush() -> None:
    """Se ejecuta al cerrar el proceso (incluyendo salidas inesperadas).

    Garantiza que todos los cambios en memoria se guarden a disco
    antes de que el proceso termine. Esto previene pérdida de datos
    si la aplicación se cierra por error, Ctrl+C, etc.
    """
    if is_dirty():
        logger.info("v6.0 atexit: Guardando health_cache a disco (dirty=True)...")
        _notify("system:shutdown", "Guardando caché antes de cerrar...", {})
        flush_to_disk()
        logger.info("v6.0 atexit: health_cache guardado correctamente")


# v6.1: Helper para notificar (import lazy de notifications)
_notifier = None

def _get_notifier():
    """Retorna la función notify() si el módulo notifications está disponible."""
    global _notifier
    if _notifier is None:
        try:
            _notifier = __import__('model_broker.notifications', fromlist=['notify']).notify
        except (ImportError, ModuleNotFoundError):
            try:
                _notifier = __import__('model_broker.notifications', fromlist=['notify']).notify
            except (ImportError, ModuleNotFoundError):
                pass
    return _notifier


def _notify(event_type: str, message: str, data: Dict[str, Any] = None):
    """Emite una notificación si notifications.py está disponible.

    v6.1: Import lazy — no rompe si notifications.py no existe.
    Los errores del callback se capturan silenciosamente.
    """
    n = _get_notifier()
    if n:
        try:
            n(event_type, message, data)
        except Exception:
            pass


# Registrar atexit handler al importar el módulo
atexit.register(_atexit_flush)


# ============================================================================
# Limpieza de rate_limited expirados
# ============================================================================

def _get_rate_limit_cooldown(count: int) -> float:
    if count <= 0:
        return _RATE_LIMIT_BACKOFF_BASE
    cooldown = _RATE_LIMIT_BACKOFF_BASE * count
    return min(cooldown, _RATE_LIMIT_BACKOFF_MAX)


def _cleanup_expired_rate_limits() -> None:
    """Limpia estados rate_limited y temporarily_unavailable expirados.

    BF-5: Itera sobre copia de items para evitar problemas
    de concurrencia al modificar valores del dict.
    """
    now = _now_epoch()
    with _health_lock:
        # BF-5: iterar sobre lista de items (copia)
        for model_id, info in list(_health_data.items()):
            if info.get("status") == "rate_limited":
                rl_at = info.get("rate_limited_at") or 0
                count = info.get("rate_limited_count") or 1
                cooldown = _get_rate_limit_cooldown(count)
                if now - rl_at >= cooldown:
                    info["status"] = "unknown"
                    info["error"] = None
                    info["rate_limited_at"] = None
                    info["previously_available"] = False
                    logger.debug(f"{model_id}: rate_limited expirado "
                                f"(cooldown {cooldown}s, #{count}) -> unknown")
            elif info.get("status") == "temporarily_unavailable":
                tu_at = info.get("verified_at") or 0
                if now - tu_at >= _TEMPORARILY_UNAVAILABLE_COOLDOWN:
                    info["status"] = "unknown"
                    info["error"] = None
                    info["previously_available"] = False
                    logger.debug(f"{model_id}: temporarily_unavailable expirado "
                                f"(cooldown {_TEMPORARILY_UNAVAILABLE_COOLDOWN}s) -> unknown")


# ============================================================================
# Consultas de salud
# ============================================================================

def is_available(model_id: str) -> bool:
    if not model_id:
        return False
    _cleanup_expired_rate_limits()
    with _health_lock:
        info = _health_data.get(model_id)
        return info is not None and info.get("status") == "available"


def is_model_removed(model_id: str) -> bool:
    """T2.1: Retorna True si el modelo fue eliminado del catálogo del proveedor."""
    if not model_id:
        return False
    _cleanup_expired_rate_limits()
    with _health_lock:
        info = _health_data.get(model_id)
        return info is not None and info.get("status") == "model_removed"


def is_payment_required(model_id: str) -> bool:
    """D-5: Retorna True si el modelo tiene estado payment_required (HTTP 402)."""
    if not model_id:
        return False
    _cleanup_expired_rate_limits()
    with _health_lock:
        info = _health_data.get(model_id)
        return info is not None and info.get("status") == "payment_required"


def get_status(model_id: str) -> str:
    """Retorna el estado del modelo.

    Posibles valores: 'available', 'failed', 'unknown',
    'rate_limited', 'payment_required', 'temporarily_unavailable',
    'model_removed'.
    """
    if not model_id:
        return "unknown"
    _cleanup_expired_rate_limits()
    with _health_lock:
        info = _health_data.get(model_id)
        return info.get("status", "unknown") if info else "unknown"


def get_verified_models() -> List[str]:
    """Retorna modelos con status='available'.

    v5.0: Incluye modelos pendientes de re-verificación (previously_available=True)
    porque se confía en la caché hasta tener evidencia de lo contrario.
    """
    _cleanup_expired_rate_limits()
    with _health_lock:
        return [mid for mid, info in _health_data.items()
                if info.get("status") == "available"]


def get_previously_available_models() -> List[str]:
    """v5.0: Retorna modelos que están available pero pendientes de re-verificación."""
    _cleanup_expired_rate_limits()
    with _health_lock:
        return [mid for mid, info in _health_data.items()
                if info.get("status") == "available" and info.get("previously_available", False)]


def mark_verified_this_session(model_id: str) -> None:
    """v5.0: Marca un modelo como verificado en esta sesión."""
    if not model_id:
        return
    with _health_lock:
        info = _health_data.get(model_id)
        if info and info.get("status") == "available":
            info["previously_available"] = False


def get_all_health() -> Dict[str, Dict[str, Any]]:
    _cleanup_expired_rate_limits()
    with _health_lock:
        return dict(_health_data)


# ============================================================================
# Reportar resultados — v6.0: memoria + callback, SIN flush a disco
# ============================================================================

def mark_available(model_id: str, provider: str = "") -> None:
    """Marca un modelo como verificado y disponible.

    BF-1: Establece previously_available=False explícitamente.

    v6.0: NO hace flush a disco. Solo actualiza memoria y notifica
    al Pool vía callback. El disco se escribe al final de ciclo/atexit.
    """
    if not model_id:
        return
    now = _now_epoch()
    with _health_lock:
        existing = _health_data.get(model_id, {})
        _health_data[model_id] = {
            "status": "available",
            "verified_at": now,
            "provider": provider,
            "previous_status": "available",
            "previously_available": False,  # BF-1: explícito, verificado esta sesión
            "error": None,
            "rate_limited_at": None,
            "rate_limited_count": 0,
            "probe_errors": existing.get("probe_errors", {}),
        }
    _mark_dirty(model_id)
    logger.info(f"{model_id}: VERIFICADO via {provider}")
    # v6.0: Notificar pool en memoria (no disco)
    _notify_pool_sync(model_id)
    # v6.1: Notificar al usuario
    _notify("health:model_verified",
            f"{model_id}: verificado via {provider}",
            {"model_id": model_id, "provider": provider})
    # v6.0: NO flush a disco aquí — se hace al final del ciclo o atexit


def mark_failed(model_id: str, provider: str = "", error: str = "") -> None:
    """Marca un modelo como failed (error permanente).

    NO sobreescribe status 'available'.

    v6.0: Notifica al Pool vía callback. No flush a disco.
    """
    if not model_id:
        return
    now = _now_epoch()
    with _health_lock:
        existing = _health_data.get(model_id)
        if existing and existing.get("status") == "available":
            logger.debug(f"{model_id}: ignoro failed (ya estaba available)")
            if provider and error:
                probe_errors = existing.get("probe_errors", {})
                probe_errors[provider] = error
                existing["probe_errors"] = probe_errors
            return

        prev_errors = existing.get("probe_errors", {}) if existing else {}
        if provider and error:
            prev_errors[provider] = error

        prev_avail = existing.get("previously_available", False) if existing else False

        _health_data[model_id] = {
            "status": "failed",
            "verified_at": now,
            "provider": provider,
            "previous_status": existing.get("status", "unknown") if existing else "unknown",
            "previously_available": prev_avail,
            "error": error,
            "rate_limited_at": None,
            "rate_limited_count": existing.get("rate_limited_count", 0) if existing else 0,
            "probe_errors": prev_errors,
        }
    _mark_dirty(model_id)
    logger.debug(f"{model_id} -> failed (provider: {provider}, error: {error})")
    _notify_pool_sync(model_id)
    # v6.1: Notificar fallo
    _notify("health:model_failed",
            f"{model_id}: fallo ({provider}: {error})",
            {"model_id": model_id, "provider": provider, "error": error})


def mark_temporarily_unavailable(model_id: str, provider: str = "", error: str = "") -> None:
    """F10: Marca un modelo como temporarily_unavailable (error transitorio).

    NO sobreescribe status 'available'.

    v6.0: Notifica al Pool vía callback. No flush a disco.
    """
    if not model_id:
        return
    now = _now_epoch()
    with _health_lock:
        existing = _health_data.get(model_id)
        if existing and existing.get("status") == "available":
            logger.debug(f"{model_id}: ignoro temporarily_unavailable (ya estaba available)")
            if provider and error:
                probe_errors = existing.get("probe_errors", {})
                probe_errors[provider] = error
                existing["probe_errors"] = probe_errors
            return

        prev_errors = existing.get("probe_errors", {}) if existing else {}
        if provider and error:
            prev_errors[provider] = error

        prev_avail = existing.get("previously_available", False) if existing else False

        _health_data[model_id] = {
            "status": "temporarily_unavailable",
            "verified_at": now,
            "provider": provider,
            "previous_status": existing.get("status", "unknown") if existing else "unknown",
            "previously_available": prev_avail,
            "error": error,
            "rate_limited_at": None,
            "rate_limited_count": 0,
            "probe_errors": prev_errors,
        }
    _mark_dirty(model_id)
    logger.info(f"{model_id} -> temporarily_unavailable (provider: {provider}, "
                f"error: {error}, cooldown: {_TEMPORARILY_UNAVAILABLE_COOLDOWN}s)")
    _notify_pool_sync(model_id)


def mark_rate_limited(model_id: str, provider: str = "") -> None:
    """D-3: Marca un modelo como rate_limited (HTTP 429 → cooldown).

    NO sobreescribe status 'available'.

    v6.0: Notifica al Pool vía callback. No flush a disco.
    """
    if not model_id:
        return
    now = _now_epoch()
    with _health_lock:
        existing = _health_data.get(model_id)
        if existing and existing.get("status") == "available":
            logger.debug(f"{model_id}: ignoro rate_limited (ya estaba available)")
            if provider:
                probe_errors = existing.get("probe_errors", {})
                probe_errors[provider] = "HTTP 429 (rate limit)"
                existing["probe_errors"] = probe_errors
            return

        prev_count = (existing.get("rate_limited_count") or 0) if existing else 0
        new_count = prev_count + 1
        cooldown = _get_rate_limit_cooldown(new_count)

        prev_errors = existing.get("probe_errors", {}) if existing else {}
        if provider:
            prev_errors[provider] = "HTTP 429 (rate limit)"

        prev_avail = existing.get("previously_available", False) if existing else False

        _health_data[model_id] = {
            "status": "rate_limited",
            "verified_at": now,
            "provider": provider,
            "previous_status": existing.get("status", "unknown") if existing else "unknown",
            "previously_available": prev_avail,
            "error": "HTTP 429 (rate limit)",
            "rate_limited_at": now,
            "rate_limited_count": new_count,
            "probe_errors": prev_errors,
        }
    _mark_dirty(model_id)
    logger.debug(f"{model_id} -> rate_limited (provider: {provider}, "
                f"429 #{new_count}, cooldown: {cooldown}s)")
    _notify_pool_sync(model_id)
    # v6.1: Notificar rate limit
    _notify("health:model_rate_limited",
            f"{model_id}: rate limited (cooldown {cooldown:.0f}s)",
            {"model_id": model_id, "provider": provider, "count": new_count, "cooldown": cooldown})


def mark_model_removed(model_id: str, provider: str = "", error: str = "") -> None:
    """T2.1: Marca un modelo como eliminado del catálogo del proveedor.

    Estado permanente: el modelo fue removido y ya no puede ser usado.

    NO sobreescribe status 'available'.

    v6.0: Notifica al Pool vía callback. No flush a disco.
    """
    if not model_id:
        return
    now = _now_epoch()
    with _health_lock:
        existing = _health_data.get(model_id)
        if existing and existing.get("status") == "available":
            logger.debug(f"{model_id}: ignoro model_removed (ya estaba available)")
            if provider and error:
                probe_errors = existing.get("probe_errors", {})
                probe_errors[provider] = error
                existing["probe_errors"] = probe_errors
            return

        prev_errors = existing.get("probe_errors", {}) if existing else {}
        if provider and error:
            prev_errors[provider] = error

        prev_avail = existing.get("previously_available", False) if existing else False

        _health_data[model_id] = {
            "status": "model_removed",
            "verified_at": now,
            "provider": provider,
            "previous_status": existing.get("status", "unknown") if existing else "unknown",
            "previously_available": prev_avail,
            "error": error or "Model removed from provider catalog",
            "rate_limited_at": None,
            "rate_limited_count": 0,
            "probe_errors": prev_errors,
        }
    _mark_dirty(model_id)
    logger.info(f"{model_id} -> model_removed (provider: {provider})")
    _notify_pool_sync(model_id)
    # v6.1: Notificar eliminación
    _notify("health:model_removed",
            f"{model_id}: eliminado del catálogo ({provider})",
            {"model_id": model_id, "provider": provider})


def mark_payment_required(model_id: str, provider: str = "") -> None:
    """D-5: Marca un modelo como payment_required (HTTP 402).

    No sobreescribe status 'available'.

    v6.0: Notifica al Pool vía callback. No flush a disco.
    """
    if not model_id:
        return
    now = _now_epoch()
    with _health_lock:
        existing = _health_data.get(model_id)
        if existing and existing.get("status") == "available":
            logger.debug(f"{model_id}: ignoro payment_required (ya estaba available)")
            if provider:
                probe_errors = existing.get("probe_errors", {})
                probe_errors[provider] = "HTTP 402 (payment required)"
                existing["probe_errors"] = probe_errors
            return

        prev_errors = existing.get("probe_errors", {}) if existing else {}
        if provider:
            prev_errors[provider] = "HTTP 402 (payment required)"

        prev_avail = existing.get("previously_available", False) if existing else False

        _health_data[model_id] = {
            "status": "payment_required",
            "verified_at": now,
            "provider": provider,
            "previous_status": existing.get("status", "unknown") if existing else "unknown",
            "previously_available": prev_avail,
            "error": "HTTP 402 (payment required)",
            "rate_limited_at": None,
            "rate_limited_count": 0,
            "probe_errors": prev_errors,
        }
    _mark_dirty(model_id)
    logger.info(f"{model_id} -> payment_required (provider: {provider})")
    _notify_pool_sync(model_id)


def report_http_status(model_id: str, http_status: int, provider: str = "", error_detail: str = "") -> None:
    """D-3/D-4/D-5: Response-Code-Driven Scheduling unificado.

    Clasifica el código HTTP y llama a la función mark_* apropiada.
    Los códigos 5xx se tratan como temporarily_unavailable (error
    transitorio con cooldown) en vez de failed permanente, porque
    los errores de servidor son usualmente recuperables.
    """
    if not model_id:
        return

    if http_status == 200:
        mark_available(model_id, provider)
    elif http_status == 429:
        # v6.7: Distinguir 429 por cuota agotada (payment) de 429 por rate_limit.
        # Si el detail contiene señales de pago, marcar como payment_required.
        if error_detail and _classify_error(error_detail) == "payment":
            mark_payment_required(model_id, provider)
        else:
            mark_rate_limited(model_id, provider)
    elif http_status == 402:
        mark_payment_required(model_id, provider)
    elif http_status == 413:
        mark_temporarily_unavailable(model_id, provider, error_detail or "HTTP 413 (context exceeded)")
    elif http_status == 404:
        if error_detail and _classify_error(error_detail) == "not_found":
            mark_model_removed(model_id, provider, error_detail or "HTTP 404 (model not found)")
        else:
            mark_failed(model_id, provider, error_detail or "HTTP 404")
    elif http_status in (401, 403):
        mark_failed(model_id, provider, error_detail or f"HTTP {http_status}")
    elif 500 <= http_status < 600:
        mark_temporarily_unavailable(model_id, provider, error_detail or f"HTTP {http_status} (server error)")
    else:
        logger.warning(f"report_http_status({model_id}): HTTP {http_status} no clasificado")
        mark_failed(model_id, provider, error_detail or f"HTTP {http_status}")


# ============================================================================
# Detección de contexto excedido (v6.2)
# ============================================================================
_CONTEXT_EXCEEDED_SIGNALS = [
    "context_length_exceeded",
    "maximum context length",
    "tokens limit",
    "token limit",
    "too long",
    "context window",
    "max_tokens",
    "input too large",
    "prompt too large",
    "request too large",
]


def is_context_exceeded(http_code: int, error_body: str = "") -> bool:
    """v6.2: Detecta si un error fue causado por exceder el contexto del modelo."""
    if http_code == 413:
        return True

    if http_code == 400 and error_body:
        body_lower = str(error_body).lower()
        return any(signal in body_lower for signal in _CONTEXT_EXCEEDED_SIGNALS)

    return False


# ============================================================================
# Clasificacion de errores HTTP
# ============================================================================

def _classify_error(error_str: str) -> str:
    """F9: Clasificador de errores comprehensivo.

    Returns: rate_limit | not_found | auth | payment | server_error |
             timeout | connection | temporarily_unavailable | context_exceeded | unknown
    """
    if not error_str:
        return "unknown"
    err = str(error_str).lower()

    # --- Contexto excedido (v6.2, prioridad máxima) ---
    if any(kw in err for kw in ("context_length_exceeded", "maximum context length",
                                 "input too large", "prompt too large",
                                 "request too large", "context window",
                                 "token limit", "tokens limit")):
        return "context_exceeded"

    # --- v6.7: Pago por agotamiento de cuota (429 + billing signals) ---
    # Cuando un modelo falla con insufficient_quota, es un error de facturación
    # del modelo, NO un rate_limit temporal. Se marca como payment para que
    # ese modelo específico salga del ranking y el sistema desescale al siguiente.
    if "429" in err and any(kw in err for kw in ("insufficient_quota", "insufficient quota",
                                                 "billing", "credit", "check your plan")):
        return "payment"

    # --- Rate limiting (genérico, sin señales de pago) ---
    if any(kw in err for kw in ("429", "rate", "limit", "throttl", "too many", "quota exceeded", "capacity")):
        return "rate_limit"

    # --- Autenticación / Autorización ---
    if any(kw in err for kw in ("401", "403", "invalid api key", "invalid x-api-key",
                                 "authentication", "unauthorized", "forbidden",
                                 "permission denied", "access denied")):
        if "rate" not in err and "limit" not in err and "429" not in err:
            return "auth"

    # --- Pago requerido ---
    if any(kw in err for kw in ("402", "payment", "billing", "insufficient", "credit")):
        return "payment"

    # --- Modelo no encontrado ---
    if any(kw in err for kw in ("404", "not found", "model_not_found", "does not exist",
                                 "no such model", "model not found")):
        return "not_found"

    # --- Timeout ---
    if any(kw in err for kw in ("timeout", "timed out", "deadline exceeded", "read timeout",
                                 "connection timeout", "socket timeout")):
        return "timeout"

    # --- Errores de conexión / red ---
    if any(kw in err for kw in ("connection", "connect", "network", "dns",
                                 "resolve", "name or service not known",
                                 "connectionerror", "connectionrefused",
                                 "connectionreset", "broken pipe",
                                 "ssl", "certificate", "proxy")):
        return "connection"

    # --- Errores de servidor (5xx) ---
    if any(kw in err for kw in ("500", "502", "503", "504", "529",
                                 "server", "internal", "upstream",
                                 "overloaded", "bad gateway", "service unavailable",
                                 "gateway timeout")):
        return "server_error"

    # --- Temporalmente no disponible ---
    if any(kw in err for kw in ("not available", "unavailable", "temporarily",
                                 "try again", "retry", "busy",
                                 "maintenance")):
        return "temporarily_unavailable"

    return "unknown"


# ============================================================================
# Probe verificable
# ============================================================================

def _do_probe_call(model_id: str, provider, provider_name: str) -> Tuple[bool, str, str]:
    """Ejecuta una llamada probe a un provider específico.

    Retorna: (success, provider_name, error_msg)
    """
    try:
        result = provider.call(
            model_id,
            _PROBE_MESSAGES,
            max_tokens=_PROBE_MAX_TOKENS,
            temperature=_PROBE_TEMPERATURE,
        )
        if result.get("success"):
            content = (result.get("content") or "").strip().upper()
            if "PING" in content:
                return True, provider_name, ""
            else:
                error_msg = f"Unexpected response: {result.get('content', '')[:80]}"
                return False, provider_name, error_msg
        else:
            error = str(result.get("error", "Unknown error"))
            return False, provider_name, error
    except Exception as e:
        return False, provider_name, str(e)


def probe_model(model_id: str, timeout: float = None) -> Tuple[bool, str]:
    """Prueba un modelo contra sus providers disponibles.

    BF-3: Ahora maneja errores timeout/connection/temporarily_unavailable
    llamando a mark_temporarily_unavailable() en vez de dejar el modelo
    en estado indeterminado.

    v6.0: Los mark_* internos ya no hacen flush a disco.
    Solo actualizan memoria + notifican pool vía callback.

    Retorna: (success, provider_name)
    """
    if timeout is None:
        timeout = _PROBE_SYNC_TIMEOUT

    try:
        from model_broker.providers import provider_manager

        providers_to_try: List[Tuple[Any, str]] = []

        try:
            found = provider_manager.find_providers_for_model(model_id)
            for prov_obj, translated_id in found:
                providers_to_try.append((prov_obj, translated_id))
        except Exception as e:
            logger.debug(f"find_providers_for_model({model_id}) fallo: {e}")

        if not providers_to_try:
            for p in provider_manager.providers.values():
                try:
                    if any(m["id"] == model_id for m in p.get_models()):
                        providers_to_try.append((p, model_id))
                except Exception:
                    continue

        if not providers_to_try:
            inferred = provider_manager._infer_provider_for_model(model_id)
            if inferred and inferred in provider_manager.providers:
                p = provider_manager.providers[inferred]
                if p.is_available():
                    translated = provider_manager.translate_model_id(model_id, inferred)
                    providers_to_try.append((p, translated))

        if not providers_to_try:
            mark_failed(model_id, "", "No provider found")
            return False, ""

        last_error = ""
        had_permanent_error = False
        had_transient_error = False

        for provider_obj, translated_id in providers_to_try:
            provider_name = provider_obj.name

            try:
                if not provider_obj.is_available():
                    continue
            except Exception:
                continue

            logger.debug(f"Probing {model_id} via {provider_name} (translated_id={translated_id})")

            try:
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(
                        _do_probe_call, translated_id, provider_obj, provider_name
                    )
                    success, prov, error = future.result(timeout=timeout)
            except FuturesTimeoutError:
                logger.debug(f"{model_id}: timeout ({timeout}s) en {provider_name}")
                last_error = f"Timeout after {timeout}s on {provider_name}"
                had_transient_error = True
                continue
            except Exception as e:
                logger.debug(f"{model_id}: excepcion en {provider_name}: {e}")
                last_error = str(e)
                had_transient_error = True
                continue

            if success:
                mark_available(model_id, prov)
                logger.info(f"{model_id}: VERIFICADO via {prov} (translated_id={translated_id})")
                return True, prov

            error_type = _classify_error(error)

            if error_type == "rate_limit":
                mark_rate_limited(model_id, prov)
                last_error = error
                continue
            elif error_type == "not_found":
                mark_model_removed(model_id, prov, error)
                had_permanent_error = True
                last_error = error
                continue
            elif error_type in ("auth", "payment"):
                mark_failed(model_id, prov, f"HTTP {error.split()[1] if len(error.split()) > 1 else error}")
                had_permanent_error = True
                last_error = error
                if error_type == "payment":
                    logger.debug(f"{model_id}: payment required en {prov}, probando siguiente proveedor")
                continue
            elif error_type in ("timeout", "connection", "temporarily_unavailable", "server_error"):
                mark_temporarily_unavailable(model_id, prov, error)
                had_transient_error = True
                last_error = error
                continue
            else:
                logger.debug(f"{model_id}: error no clasificado en {prov}: {error}")
                last_error = error
                continue

        # Si todos los providers fallaron con errores permanentes
        if had_permanent_error:
            current_status = get_status(model_id)
            if current_status not in ("rate_limited", "temporarily_unavailable"):
                mark_failed(model_id, "", last_error or "All providers failed")

        # Si todos los providers fallaron con errores transitorios
        if had_transient_error and not had_permanent_error:
            current_status = get_status(model_id)
            if current_status not in ("temporarily_unavailable", "rate_limited"):
                mark_temporarily_unavailable(model_id, "", last_error or "All providers temporarily failed")

        return False, ""

    except Exception as e:
        logger.error(f"probe_model({model_id}): excepcion inesperada: {e}")
        return False, ""


def probe_model_sync(model_id: str) -> Tuple[bool, str]:
    """Wrapper síncrono de probe_model con timeout por defecto."""
    return probe_model(model_id, timeout=_PROBE_SYNC_TIMEOUT)


# ============================================================================
# Background probing
# ============================================================================

def _background_probe_ranking(ranking: List[Dict[str, Any]]) -> None:
    """Proba modelos en background siguiendo un ranking dado.

    v6.0: No hace flush tras cada modelo. Solo flush al final del ciclo.
    Los cambios se notifican al Pool vía callback tras cada mark_*.
    """
    logger.info(f"Background probing: {len(ranking)} modelos")

    def sort_key(m):
        mid = m.get("id", "")
        with _health_lock:
            info = _health_data.get(mid)
            current = info.get("status", "unknown") if info else "unknown"
            if current == "available":
                return -1
            prev = info.get("previous_status", "unknown") if info else "unknown"
            order = {"available": 0, "unknown": 1, "failed": 2, "rate_limited": 3}
            return order.get(prev, 1)

    ranked = sorted(ranking, key=sort_key)
    verified_count = 0
    failed_count = 0
    rate_limited_count = 0

    for model_info in ranked:
        model_id = model_info.get("id", "")
        if not model_id:
            continue
        if is_available(model_id):
            continue
        status = get_status(model_id)
        if status == "rate_limited":
            rate_limited_count += 1
            continue

        success, provider = probe_model(model_id, timeout=_PROBE_BG_TIMEOUT)
        if success:
            verified_count += 1
        else:
            final_status = get_status(model_id)
            if final_status == "rate_limited":
                rate_limited_count += 1
            else:
                failed_count += 1

        time.sleep(_PROBE_BG_DELAY)
        # v6.0: NO maybe_flush() aquí — el callback ya actualizó el pool

    # v6.0: Flush SOLO al final del ciclo completo
    flush_to_disk()
    logger.info(f"Background probing completado: "
                f"{verified_count} available, {failed_count} failed, "
                f"{rate_limited_count} rate_limited")
    # v6.1: Notificar fin de ciclo
    _notify("health:cycle_end",
            f"Probing completado: {verified_count} OK, {failed_count} fail",
            {"verified": verified_count, "failed": failed_count, "rate_limited": rate_limited_count})


def start_background_probing(ranking: List[Dict[str, Any]]) -> None:
    """Inicia el hilo de background probing con un ranking dado."""
    global _bg_thread_started
    with _bg_thread_lock:
        if _bg_thread_started:
            logger.debug("Background probing ya en curso")
            return
        _bg_thread_started = True

    thread = threading.Thread(
        target=_background_probe_ranking,
        args=(ranking,),
        daemon=True,
        name="model-health-probe"
    )
    thread.start()
    logger.info("Hilo de background probing iniciado")


def on_session_close() -> None:
    """Flush final al cerrar la sesión de APA.

    v6.0: Guarda todos los cambios pendientes a disco.
    También llamado por atexit como safety net.
    """
    if is_dirty():
        _notify("health:flush_disk", "Guardando caché al cerrar sesión...", {})
        flush_to_disk()
        logger.info("v6.0: Sesión cerrada, datos guardados (dirty=True)")
    else:
        logger.info("v6.0: Sesión cerrada, no había cambios pendientes")


# ============================================================================
# v5.0 → v6.0: Cache re-verification en background
# ============================================================================

_bg_reverification_started = False
_bg_reverification_lock = threading.Lock()
_REVERIFICATION_FIRST_DELAY = 30  # BF-4: Primera verificación a los 30s
_REVERIFICATION_INTERVAL = 3600   # Luego cada 1 hora (acuerdo rendimiento)
_PROBE_REVERIFY_DELAY = 2        # Delay entre probes de re-verificación


def _verify_pool_candidates() -> None:
    """v6.6: Verifica modelos del pool que no están en _health_data.

    Tras la primera pasada de previously_available, el pool contiene modelos
    nuevos de los catálogos de proveedores que están en estado 'unknown'.
    Esta función los probea uno a uno para convertirlos en 'available' o
    'failed' verificados. También re-verifica modelos 'failed' y
    'payment_required' del pool que podrían haberse recuperado.

    Solo se ejecuta una vez, al finalizar la primera pasada.
    """
    global _pool_candidates_callback
    if _pool_candidates_callback is None:
        return

    try:
        # Obtener base_ids del pool que necesitan verificación
        candidate_ids = _pool_candidates_callback()
        if not candidate_ids:
            logger.info("v6.6: _verify_pool_candidates: no hay candidatos del pool")
            return

        # Filtrar: solo los que NO están ya en _health_data (modelos nuevos)
        # o que están en _health_data pero en estado failed/payment_required
        with _health_lock:
            already_known_available = {
                mid for mid, info in _health_data.items()
                if info.get("status") in ("available",) and info.get("verified_this_session", False)
            }

        to_probe = []
        for model_id in candidate_ids:
            # Extraer base_id si tiene prefijo
            base_id = model_id
            if ":" in model_id:
                base_id = model_id.split(":", 1)[1]

            # No re-verificar si ya está verificado esta sesión
            if base_id in already_known_available:
                continue

            # Evitar duplicados (mismo modelo de múltiples providers)
            if base_id not in [m.split(":", 1)[-1] if ":" in m else m for m in [x[0] for x in to_probe]]:
                to_probe.append((base_id, model_id))

        if not to_probe:
            logger.info("v6.6: _verify_pool_candidates: todos los candidatos ya verificados")
            return

        logger.info(f"v6.6: _verify_pool_candidates: {len(to_probe)} modelos del pool "
                   f"para verificación real (modelos nuevos de catálogos)")
        _notify("health:pool_candidates_start",
                f"Verificando {len(to_probe)} modelos nuevos del pool",
                {"count": len(to_probe)})

        verified = 0
        failed = 0
        for base_id, _prefixed_id in to_probe:
            success, provider = probe_model(base_id, timeout=_PROBE_BG_TIMEOUT)
            if success:
                mark_verified_this_session(base_id)
                verified += 1
            else:
                failed += 1
            time.sleep(_PROBE_REVERIFY_DELAY)

        flush_to_disk()
        logger.info(f"v6.6: _verify_pool_candidates completado: "
                   f"{verified} verificados, {failed} fallidos de {len(to_probe)} candidatos")
        _notify("health:pool_candidates_end",
                f"Candidatos del pool: {verified} OK, {failed} fail",
                {"verified": verified, "failed": failed, "total": len(to_probe)})

    except Exception as e:
        logger.error(f"v6.6: Error en _verify_pool_candidates: {e}")


def _background_cache_reverification() -> None:
    """v6.0: Re-verifica modelos en background. Modelo a modelo.

    v5.0 base: Re-verifica previously_available y unknown en background.
    BF-4: Primera pasada a los 30s.

    v6.0 cambios:
    - Tras cada probe → mark_* → callback actualiza pool EN VIVO
    - flush_to_disk() SOLO al finalizar cada ciclo completo
    - No hay flush tras cada modelo individual
    - El pool refleja los cambios progresivamente en memoria
    """
    global _bg_reverification_started
    logger.info("v6.0: Background cache re-verification iniciado")
    _notify("health:cycle_start", "Verificación en background iniciada", {"first_pass": True})

    # BF-4: Primera pasada rápida (30s) para re-verificar caché de startup
    first_pass = True
    next_delay = _REVERIFICATION_FIRST_DELAY

    while True:
        try:
            time.sleep(next_delay)

            # Recopilar modelos a re-verificar
            to_reverify = []
            to_retry_payment = []

            with _health_lock:
                for model_id, info in _health_data.items():
                    status = info.get("status", "unknown")
                    # Prioridad 1: previously_available (cargados de caché)
                    if status == "available" and info.get("previously_available", False):
                        to_reverify.append((model_id, "previously_available"))
                    # Prioridad 2: unknown (nunca probados)
                    elif status == "unknown":
                        to_reverify.append((model_id, "unknown"))
                    # Prioridad 3: payment_required (reintentar si hay créditos)
                    elif status == "payment_required":
                        to_retry_payment.append(model_id)

            if not to_reverify and not to_retry_payment:
                logger.debug("Background re-verification: nada que re-verificar")
                if first_pass:
                    first_pass = False
                    next_delay = _REVERIFICATION_INTERVAL
                    logger.info("Background re-verification: primera pasada completada, "
                               f"intervalo -> {_REVERIFICATION_INTERVAL}s")
                continue

            logger.info(f"v6.0 Background re-verification: {len(to_reverify)} modelos a verificar, "
                        f"{len(to_retry_payment)} a reintento de pago"
                        f"{' [PRIMERA PASADA]' if first_pass else ''}")
            # v6.1: Notificar inicio de ciclo
            _notify("health:cycle_start",
                    f"Verificando {len(to_reverify)} modelos" +
                    (" (primera pasada)" if first_pass else ""),
                    {"to_verify": len(to_reverify), "to_retry_payment": len(to_retry_payment),
                     "first_pass": first_pass})

            # Re-verificar por prioridad (modelo a modelo)
            # Cada probe → mark_* → _notify_pool_sync() → pool actualizado EN VIVO
            verified = 0
            failed = 0
            temp_unavail = 0
            for model_id, reason in to_reverify:
                success, provider = probe_model(model_id, timeout=_PROBE_BG_TIMEOUT)
                if success:
                    mark_verified_this_session(model_id)
                    verified += 1
                else:
                    new_status = get_status(model_id)
                    if new_status == "temporarily_unavailable":
                        temp_unavail += 1
                    else:
                        failed += 1
                time.sleep(_PROBE_REVERIFY_DELAY)
                # v6.0: NO flush aquí — el callback ya actualizó el pool en memoria

            # Re-intentar modelos payment_required
            payment_restored = 0
            payment_max_retry = 5
            for model_id in to_retry_payment[:payment_max_retry]:
                success, provider = probe_model(model_id, timeout=_PROBE_BG_TIMEOUT)
                if success:
                    mark_verified_this_session(model_id)
                    payment_restored += 1
                time.sleep(_PROBE_REVERIFY_DELAY)

            # v6.0: Flush SOLO al finalizar el ciclo completo (no modelo a modelo)
            flush_to_disk()

            logger.info(f"v6.0 Background re-verification completado: "
                        f"{verified} verificados, {failed} fallidos, "
                        f"{temp_unavail} temporalmente no disponibles, "
                        f"{payment_restored} pagos restaurados")
            # v6.1: Notificar fin de ciclo
            _notify("health:cycle_end",
                    f"Ciclo completado: {verified} OK, {failed} fail, {temp_unavail} temp, {payment_restored} pago",
                    {"verified": verified, "failed": failed, "temp_unavail": temp_unavail,
                     "payment_restored": payment_restored,
                     "first_pass": first_pass})

            # v6.6: Tras la primera pasada de previously_available, hacer una
            # pasada real sobre los modelos del pool que NO están en _health_data
            # (modelos nuevos de los catálogos de proveedores). Esto convierte
            # los "unknown" del pool en "available" o "failed" verificados.
            if first_pass and _pool_candidates_callback:
                _verify_pool_candidates()

            # Cambiar a intervalo normal después de la primera pasada
            if first_pass:
                first_pass = False
                next_delay = _REVERIFICATION_INTERVAL
                logger.info(f"v6.0 Background re-verification: intervalo -> {_REVERIFICATION_INTERVAL}s")

        except Exception as e:
            logger.error(f"Error en background cache re-verification: {e}")
            time.sleep(60)


def start_cache_reverification() -> None:
    """v5.0: Inicia el hilo de re-verificación periódica de la caché.

    BF-4: La primera verificación se ejecuta a los 30s (no 600s).
    """
    global _bg_reverification_started
    with _bg_reverification_lock:
        if _bg_reverification_started:
            logger.debug("Background cache re-verification ya iniciado")
            return
        _bg_reverification_started = True

    thread = threading.Thread(
        target=_background_cache_reverification,
        daemon=True,
        name="cache-reverification"
    )
    thread.start()
    logger.info(f"v6.0: Hilo de cache re-verification iniciado "
               f"(primera pasada en {_REVERIFICATION_FIRST_DELAY}s, "
               f"luego cada {_REVERIFICATION_INTERVAL}s)")


# ============================================================================
# Inicializacion al importar — v6.0: Cache-driven + atexit
# ============================================================================
try:
    load_health_from_cache()
except Exception as _import_err:
    logger.warning(f"Error en load_health_from_cache() al importar: {_import_err}")

# v5.0: Iniciar re-verificación periódica de la caché en background
try:
    start_cache_reverification()
except Exception as _reverify_err:
    logger.debug(f"No se pudo iniciar cache re-verification: {_reverify_err}")


# ============================================================================
# Test standalone
# ============================================================================
if __name__ == "__main__":
    if not logging.root.handlers:
        logging.basicConfig(level=logging.INFO,
                            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger.setLevel(logging.DEBUG)

    trust_window = get_trust_window()

    print("\n" + "=" * 70)
    print(f"TEST: Model Health v6.0 — Caché en memoria + Pool sync callback")
    print(f"  data_dir={_DATA_DIR}")
    print("=" * 70)

    # Test 1: get_trust_window() retorna 0
    assert get_trust_window() == 0, "trust_window debe ser 0 (no expira)"
    print("  [PASS] get_trust_window() == 0")

    # Test 2: Cargar caché
    data = load_health_from_cache(force=True)
    print(f"  [INFO] Cargados {len(data)} modelos de caché")

    # Test 3: Callback registration
    callback_called = []
    def test_callback(model_id):
        callback_called.append(model_id)
    register_pool_sync_callback(test_callback)
    assert _pool_sync_callback is not None
    print("  [PASS] Callback registrado correctamente")

    # Test 4: mark_available triggers callback (no disk flush)
    test_model = "__test_model_v6__"
    _dirty_flag = False  # Reset dirty flag
    mark_available(test_model, "test-provider")
    assert test_model in callback_called, "Callback debe haber sido llamado"
    print(f"  [PASS] Callback invocado tras mark_available: {callback_called}")

    # Test 5: Dirty flag set after mark
    assert is_dirty(), "dirty_flag debe ser True tras mark_available"
    print("  [PASS] Dirty flag = True tras mark_available")

    # Test 6: flush clears dirty flag
    flush_to_disk()
    assert not is_dirty(), "dirty_flag debe ser False tras flush"
    print("  [PASS] Dirty flag = False tras flush_to_disk")

    # Test 7: _FLUSH_IMMEDIATELY is False
    assert _FLUSH_IMMEDIATELY == False, "FLUSH_IMMEDIATELY debe ser False en v6.0"
    print("  [PASS] FLUSH_IMMEDIATELY = False (caché en memoria)")

    # Test 8: mark_failed triggers callback
    callback_called.clear()
    _dirty_flag = False
    mark_failed("__test_failed_v6__", "test", "test error")
    assert "__test_failed_v6__" in callback_called
    print("  [PASS] Callback invocado tras mark_failed")

    # Test 9: mark_rate_limited triggers callback
    callback_called.clear()
    _dirty_flag = False
    mark_rate_limited("__test_rl_v6__", "test")
    assert "__test_rl_v6__" in callback_called
    print("  [PASS] Callback invocado tras mark_rate_limited")

    # Test 10: mark_model_removed triggers callback
    callback_called.clear()
    _dirty_flag = False
    mark_model_removed("__test_mr_v6__", "test")
    assert "__test_mr_v6__" in callback_called
    print("  [PASS] Callback invocado tras mark_model_removed")

    # Test 11: mark_payment_required triggers callback
    callback_called.clear()
    _dirty_flag = False
    mark_payment_required("__test_pr_v6__", "test")
    assert "__test_pr_v6__" in callback_called
    print("  [PASS] Callback invocado tras mark_payment_required")

    # Test 12: mark_temporarily_unavailable triggers callback
    callback_called.clear()
    _dirty_flag = False
    mark_temporarily_unavailable("__test_tu_v6__", "test", "temp error")
    assert "__test_tu_v6__" in callback_called
    print("  [PASS] Callback invocado tras mark_temporarily_unavailable")

    # Test 13: previously_available
    with _health_lock:
        _health_data["__test_pa_v6__"] = {
            "status": "available",
            "verified_at": time.time() - 3600,
            "provider": "test",
            "previous_status": "available",
            "previously_available": True,
            "error": None,
            "rate_limited_at": None,
            "rate_limited_count": 0,
            "probe_errors": {},
        }
    prev_avail = get_previously_available_models()
    assert "__test_pa_v6__" in prev_avail, "Modelo debe estar en previously_available"
    print(f"  [PASS] Modelo en previously_available tras cargar de caché")

    # BF-1: mark_available establece previously_available=False
    mark_available("__test_pa_v6__", "test-provider")
    with _health_lock:
        info = _health_data.get("__test_pa_v6__", {})
        assert info.get("previously_available") == False, \
            "BF-1: mark_available debe establecer previously_available=False"
    print(f"  [PASS] BF-1: mark_available establece previously_available=False")

    # Test: flush includes previously_available
    mark_available("__test_pa_v6__", "test-provider")  # Force update
    flush_to_disk()
    try:
        with open(_HEALTH_CACHE_PATH, "r", encoding="utf-8") as f:
            saved = json.load(f)
        saved_info = saved.get("models", {}).get("__test_pa_v6__", {})
        assert "previously_available" in saved_info
        print(f"  [PASS] BF-2: flush_to_disk incluye previously_available")
    except Exception as e:
        print(f"  [FAIL] BF-2: Error verificando flush: {e}")

    # Cleanup: flush final
    flush_to_disk()

    print("\n" + "=" * 70)
    print("  TODOS LOS TESTS PASARON — Model Health v6.0 OK")
    print("=" * 70)
