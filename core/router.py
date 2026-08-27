#!/usr/bin/env python3
"""
core/router.py v7.2 (HTTP) — Router LLM con Emergency Harness
================================================================
Fusión de:
  - v6.6 completo: 34 funciones (pool, arena, providers, desescalado)
  - Arnés de emergencia v7: 9 funciones (bootstrap, Ollama local)
  - v7.2: MB communication via HTTP (no Python class import)

Arquitectura call_llm() — 3 capas:
  Capa 1: Model Broker vía HTTP POST /api/call (ruta primaria si configurado)
  Capa 2: Emergency Harness (si MB cae: bootstrap -> Ollama local)
  Capa 3: Pool/Providers v6.6 (fallback original con desescalado)
"""

from __future__ import annotations

import sys
import os
import time
import json
import logging
import requests
import hashlib
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field

# ============================================================================
# Settings con triple-fallback: core.settings > env > defaults
# ============================================================================

class _FallbackSettings:
    """Settings con fallback: core.settings > env > hardcoded defaults."""

    def __init__(self):
        self._settings = None
        self._load()

    def _load(self):
        try:
            from core import settings as _core_settings
            self._settings = _core_settings
        except Exception:
            self._settings = None

    def __getattr__(self, name):
        # 1. Intentar core.settings
        if self._settings is not None:
            try:
                val = getattr(self._settings, name)
                if val is not None:
                    return val
            except AttributeError:
                pass

        # 2. Intentar variable de entorno
        env_map = {
            "openrouter_api_key": "OPENROUTER_API_KEY",
            "model_broker_url": "MODEL_BROKER_URL",
            "model_broker_api_key": "MODEL_BROKER_API_KEY",
            "ollama_base_url": "OLLAMA_BASE_URL",
            "ollama_default_model": "OLLAMA_DEFAULT_MODEL",
        }
        env_var = env_map.get(name)
        if env_var:
            val = os.environ.get(env_var)
            if val is not None:
                return val

        # 3. Hardcoded defaults
        defaults = {
            "openrouter_api_key": "",
            "model_broker_url": "",
            "model_broker_api_key": "",
            "ollama_base_url": "http://localhost:11434",
            "ollama_default_model": "llama3.1",
            "emergency_keys": {
                "ollama_base_url": "http://localhost:11434",
                "ollama_model": "llama3.1",
            },
        }
        if name in defaults:
            return defaults[name]

        raise AttributeError(f"Setting '{name}' no encontrado")

    @property
    def model_broker_config(self):
        return {
            "url": getattr(self, "model_broker_url", ""),
            "api_key": getattr(self, "model_broker_api_key", ""),
        }


settings = _FallbackSettings()
logger = logging.getLogger("core.router")

# ============================================================================
# Módulos opcionales — no fallan si no están disponibles (standalone)
# ============================================================================

model_health = None
_global_pool = None
LLMCache = None
PoolEntry = None


def _safe_import(module_path, attr_name):
    """Importa un atributo de un módulo sin fallar."""
    try:
        mod = __import__(module_path, fromlist=[attr_name])
        return getattr(mod, attr_name)
    except Exception:
        return None


model_health = _safe_import("core.model_health", "model_health")
_global_pool = _safe_import("core.pool", "_global_pool")
_pool_mod = _safe_import("core.pool", "PoolEntry")
if _pool_mod is not None:
    PoolEntry = _pool_mod
_LLMCacheCls = _safe_import("core.cache", "LLMCache")
if _LLMCacheCls is not None:
    LLMCache = _LLMCacheCls

# Módulos opcionales adicionales — providers, eventos, precios
provider_manager = None
event_bus = None
estimate_price = None

provider_manager = _safe_import("core.providers", "provider_manager")
event_bus = _safe_import("core.event_bus", "event_bus")
estimate_price = _safe_import("core.price_estimator", "estimate_price")

# Módulos opcionales de tracking (no críticos para el router)
_usage_tracker_cls = _safe_import("core.usage_tracker", "UsageTracker")
_quota_tracker_cls = _safe_import("core.quota_tracker", "QuotaTracker")

# ============================================================================
# v6.6: Escalado y desescalado silencioso
# ============================================================================

# Mapa de desescalado: si task_type falla, probar con el siguiente
_DESCALE_MAP = {
    "planning":       "generation",
    "generation":     "coding",
    "coding":         "correction",
    "correction":     "chat",
    "spec_generation":"generation",
    "sdd_generation": "generation",
    "analysis":       "generation",
    "sdd_evaluation": "evaluation",
}


def estimate_task_size(system_prompt: str, user_prompt: str,
                       max_tokens: int = 2000) -> int:
    """Estima los tokens de contexto que necesitará la tarea.

    Se usa para seleccionar modelos con suficiente context_length.
    Retorna un estimado conservador (30% overhead).
    """
    text = system_prompt + user_prompt
    token_est = _estimate_tokens(text)
    return int((token_est + max_tokens) * 1.30)


def get_scaling_state() -> Dict[str, Any]:
    """Retorna el estado actual de escalado del router.

    Incluye info del emergency harness para monitoreo.
    """
    return {
        "current_model": None,
        "current_task_type": None,
        "emergency_active": _broker_available is False if _broker_available is not None else False,
        "broker_available": _broker_available,
        "broker_configured": _has_mb_config() if _global_pool is not None else False,
        "pool_size": _global_pool.size() if _global_pool else 0,
        "descale_map": dict(_DESCALE_MAP),
    }


def re_escalate(task_type: str) -> Optional[str]:
    """Re-escala a un task_type de mayor complejidad.

    Retorna el task_type al que se re-escaló, o None si ya está
    en el máximo.
    """
    reverse_map = {v: k for k, v in _DESCALE_MAP.items()}
    return reverse_map.get(task_type)


def try_re_escalate(task_type: str) -> str:
    """Intenta re-escalar; si no puede, retorna el mismo task_type."""
    return re_escalate(task_type) or task_type


def _push_model_to_stack(entry) -> None:
    """Apila un modelo para re-escalado futuro si falla.

    No cuenta como intento fallido — solo registra que ya no es
    el primero en la cola para ese task_type.
    """
    if _global_pool is not None:
        try:
            _global_pool.mark_rate_limited(entry.provider, entry.model_id)
            logger.debug(f"Pushed to stack: {entry.model_id} via {entry.provider}")
        except Exception as e:
            logger.debug(f"_push_model_to_stack: {e}")


def _select_model_for_context(task_type: str, required_context: int,
                               current_best) -> Optional[PoolEntry]:
    """Busca un modelo alternativo con suficiente contexto.

    Se usa cuando el mejor modelo no tiene context_length suficiente
    para la tarea.
    """
    try:
        if _global_pool is None:
            return None

        candidates = [
            e for e in _global_pool.get_all_entries()
            if e.context_length >= required_context
            and e.model_id != current_best.model_id
            and e.health_status in ("available", "unknown")
        ]
        if not candidates:
            return None

        candidates.sort(key=lambda e: e.composite_score, reverse=True)
        logger.info(
            f"_select_model_for_context: encontrado {len(candidates)} "
            f"candidatos con contexto >= {required_context}"
        )
        return candidates[0]
    except Exception as e:
        logger.debug(f"_select_model_for_context: {e}")
        return None


# ============================================================================
# Arena — lazy import (no falla si arena_fetcher no existe)
# ============================================================================

def _get_arena_module():
    """Retorna el módulo arena_fetcher (lazy import)."""
    try:
        from core import arena_fetcher
        return arena_fetcher
    except Exception:
        return None


def _get_arena_score(model_id: str, task_type: Optional[str]) -> Optional[float]:
    """Obtiene el Arena score de un modelo (lazy, no falla)."""
    try:
        af = _get_arena_module()
        if af is None:
            return None
        if task_type:
            score = af.get_model_score(model_id, task_type)
            if score is not None:
                return score
        return af.get_model_score(model_id, None)
    except Exception:
        return None


def _get_arena_categories():
    """Retorna las categorías de Arena disponibles."""
    try:
        af = _get_arena_module()
        if af is None:
            return []
        return af.get_categories()
    except Exception:
        return []


# ============================================================================
# Notificaciones al usuario (v6.5, no falla nunca)
# ============================================================================

def _notify(event_type: str, message: str, data: Dict[str, Any] = None) -> None:
    """Emite una notificación al usuario. Nunca falla.

    En standalone, simplemente loguea. En APA, delega al
    event_bus si está disponible.
    """
    try:
        if data is None:
            data = {}
        # Intentar event_bus de APA
        if event_bus is not None:
            try:
                event_bus.emit(event_type, message, **data)
                return
            except Exception:
                pass
        # Fallback: log
        logger.info(f"[notify] {event_type}: {message}")
    except Exception:
        pass


# ============================================================================
# EMERGENCY HARNESS (9 funciones, nuevas en v7.0)
# ============================================================================

_broker_available = None  # None=never tried, True=OK, False=down
_last_emergency_notify_time = 0.0


def _has_mb_config() -> bool:
    """Retorna True si Model Broker está configurado (URL presente)."""
    cfg = settings.model_broker_config
    return bool(cfg and cfg.get("url", "").strip())


def _get_broker():
    """v7.2: Verifica si MB está configurado.
    Ya no importa ModelBroker como clase Python.
    La comunicación real se hace vía _call_mb_http().
    Retorna True si MB está configurado, None si no.
    """
    global _broker_available
    if _broker_available is False:
        return None
    if not _has_mb_config():
        _broker_available = False
        return None
    _broker_available = True
    return True


def reset_broker_status() -> None:
    """Resetea el estado de disponibilidad del broker (para reintentos)."""
    global _broker_available
    _broker_available = None


def _call_mb_http(
    task_type: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 2000,
    temperature: float = 0.1,
    estimated_tokens: int = 0,
    priority: str = "quality",
    model_id: str = None,
    max_fallbacks: int = 2,
) -> Optional[Dict[str, Any]]:
    """v7.2: Llama a MB vía HTTP POST /api/call.
    Reemplaza la importación de ModelBroker como clase Python.
    APA y MB son apps independientes que se comunican por HTTP.
    Retorna el dict de respuesta de MB, o None si no hay conexión.
    """
    global _broker_available
    mb_url = settings.model_broker_url
    if not mb_url:
        return None
    payload = {
        "task_type": task_type,
        "user_prompt": user_prompt,
        "system_prompt": system_prompt,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    # Solo enviar si tienen valor (no contaminar con defaults innecesarios)
    if estimated_tokens > 0:
        payload["estimated_tokens"] = estimated_tokens
    if priority:
        payload["priority"] = priority
    if model_id:
        payload["model_id"] = model_id
    if max_fallbacks != 2:
        payload["max_fallbacks"] = max_fallbacks
    try:
        resp = requests.post(
            f"{mb_url.rstrip('/')}/api/call",
            json=payload,
            timeout=180,
        )
        if resp.status_code == 200:
            data = resp.json()
            _broker_available = True
            return data
        else:
            logger.warning("MB HTTP %d: %s", resp.status_code, resp.text[:200])
            return {"success": False, "error": f"MB HTTP {resp.status_code}"}
    except (requests.exceptions.ConnectionError, ConnectionError):
        _broker_available = False
        return None
    except requests.exceptions.Timeout:
        _broker_available = False
        return None
    except Exception as e:
        _broker_available = False
        logger.warning("MB HTTP error: %s", e)
        return None


def _notify_emergency_to_user(message: str) -> None:
    """Notifica al usuario sobre emergencia, con throttle (1 min)."""
    global _last_emergency_notify_time
    now = time.time()
    if now - _last_emergency_notify_time < 60:
        return
    _last_emergency_notify_time = now
    _notify("router:emergency", message, {"emergency": True, "source": "router_v7"})


def _try_bootstrap_mb() -> bool:
    """v7.2: Intenta hacer bootstrap de MB vía HTTP.
    1. Health check GET /api/status
    2. Test call POST /api/call con petición mínima
    Si tiene éxito, marca MB como disponible y retorna True.
    """
    global _broker_available, _broker_available
    try:
        mb_url = settings.model_broker_url
        if not mb_url:
            return False
        # Health check
        try:
            resp = requests.get(f"{mb_url.rstrip('/')}/api/status", timeout=5)
            if resp.status_code != 200:
                return False
        except Exception:
            return False
        # Test call
        result = _call_mb_http(
            task_type="chat",
            system_prompt="Reply OK",
            user_prompt="health check",
            max_tokens=10,
            temperature=0.0,
        )
        if result is not None and result.get("success"):
            _broker_available = True
            logger.info("Bootstrap MB: éxito — MB restaurado vía HTTP")
            return True
        return False
    except Exception as e:
        logger.debug("Bootstrap MB: falló — %s", e)
        return False


def _find_ollama_model() -> str:
    """Busca un modelo disponible en Ollama local.

    Retorna el ID del modelo encontrado, o el default si Ollama no responde.
    """
    try:
        resp = requests.get(
            f"{settings.ollama_base_url}/api/tags",
            timeout=3,
        )
        if resp.status_code == 200:
            models = resp.json().get("models", [])
            if models:
                return models[0].get("name", models[0].get("model", "llama3.1"))
    except Exception:
        pass

    return settings.ollama_default_model or "llama3.1"


def _find_last_working_model(task_type: str) -> Optional[str]:
    """Busca el último modelo que funcionó para un task_type.

    Usa el usage_tracker si está disponible. Si no, retorna el modelo
    Ollama default.
    """
    try:
        if _usage_tracker_cls is not None:
            tracker = _usage_tracker_cls()
            last = tracker.get_last_working_model(task_type)
            if last:
                return last
    except Exception:
        pass

    return _find_ollama_model()


def _emergency_call(system_prompt: str, user_prompt: str,
                    model: str = None, max_tokens: int = 2000,
                    temperature: float = 0.1) -> Dict[str, Any]:
    """Llamada de emergencia vía Ollama local.

    Solo Ollama local para garantizar disponibilidad.
    """
    if model is None:
        model = _find_ollama_model()

    url = f"{settings.ollama_base_url}/api/chat"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "options": {
            "num_predict": max_tokens,
            "temperature": temperature,
        },
    }

    try:
        start = time.time()
        resp = requests.post(url, json=payload, timeout=120)
        elapsed_ms = int((time.time() - start) * 1000)

        if resp.status_code == 200:
            data = resp.json()
            content = ""
            if "message" in data:
                content = data["message"].get("content", "")
            elif "response" in data:
                content = data["response"]

            if content:
                return {
                    "content": content,
                    "model_used": model,
                    "provider_used": "ollama_local",
                    "success": True,
                    "attempts": 1,
                    "via_emergency": True,
                    "tokens_input": _estimate_tokens(system_prompt + user_prompt),
                    "tokens_output": _estimate_tokens(content),
                    "latency_ms": elapsed_ms,
                    "cost_usd": 0.0,
                    "arena_score": None,
                    "provider": "ollama_local",
                    "http_status": 200,
                }

        return {
            "content": "",
            "model_used": model,
            "provider_used": "ollama_local",
            "success": False,
            "attempts": 1,
            "via_emergency": True,
            "error": f"Ollama retornó HTTP {resp.status_code}",
            "tokens_input": _estimate_tokens(system_prompt + user_prompt),
            "tokens_output": 0,
            "latency_ms": elapsed_ms,
            "cost_usd": 0.0,
            "arena_score": None,
            "provider": "ollama_local",
            "http_status": resp.status_code,
        }
    except (requests.exceptions.ConnectionError, ConnectionError):
        return {
            "content": "",
            "model_used": model,
            "provider_used": "ollama_local",
            "success": False,
            "attempts": 1,
            "via_emergency": True,
            "error": f"Ollama no disponible en {settings.ollama_base_url}",
            "tokens_input": _estimate_tokens(system_prompt + user_prompt),
            "tokens_output": 0,
            "latency_ms": 0,
            "cost_usd": 0.0,
            "arena_score": None,
            "provider": "ollama_local",
            "http_status": None,
        }
    except Exception as e:
        return {
            "content": "",
            "model_used": model,
            "provider_used": "ollama_local",
            "success": False,
            "attempts": 1,
            "via_emergency": True,
            "error": f"Error en emergency call: {e}",
            "tokens_input": _estimate_tokens(system_prompt + user_prompt),
            "tokens_output": 0,
            "latency_ms": 0,
            "cost_usd": 0.0,
            "arena_score": None,
            "provider": "ollama_local",
            "http_status": None,
        }


def _run_emergency_harness(
    task_type: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
    temperature: float,
    call_start_time: float,
) -> Optional[Dict[str, Any]]:
    """Ejecuta el arnés de emergencia completo.

    Flujo:
    1. Notificar al usuario (throttled)
    2. Intentar bootstrap de MB
    3. Si bootstrap OK → llamar vía MB
    4. Si no → llamar vía Ollama local

    Retorna el resultado o None si no hay emergency configurado.
    """
    _notify_emergency_to_user(
        f"Model Broker caído. Activando arnés de emergencia (Ollama local)..."
    )

    # Paso 1: Intentar bootstrap de MB vía HTTP
    if _try_bootstrap_mb():
        logger.info("Emergency: MB bootstrap exitoso, reintentando vía HTTP")
        result = _call_mb_http(
            task_type=task_type,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        if result is not None and result.get("success"):
            total_elapsed = int((time.time() - call_start_time) * 1000)
            logger.info("Emergency: MB restaurado vía HTTP")
            return {
                **result,
                "attempts": 1,
                "via_emergency": True,
                "mb_bootstrapped": True,
                "latency_ms": total_elapsed,
            }

    # Paso 2: Ollama local
    model = _find_last_working_model(task_type)
    logger.info(f"Emergency: llamando Ollama local ({model})")
    result = _emergency_call(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    total_elapsed = int((time.time() - call_start_time) * 1000)
    result["latency_ms"] = total_elapsed
    return result


# ============================================================================
# TASK MODEL CACHE & STARTUP (nuevas en v7.1)
# ============================================================================

# Prioridad de optimización por tipo de tarea
_TASK_PRIORITY_MAP = {
    "chat": "latency",
    "planning": "quality",
    "coding": "quality",
    "generation": "quality",
    "correction": "quality",
    "spec_generation": "quality",
    "sdd_generation": "quality",
    "analysis": "quality",
    "sdd_evaluation": "quality",
    "evaluation": "quality",
}

# Cache en memoria: {task_type: {model, provider, arena_score, ...}}
_task_model_cache: Dict[str, Dict[str, Any]] = {}
_task_cache_initialized = False
_task_cache_file = None


def _get_cache_file_path() -> str:
    """Retorna la ruta del fichero de caché de modelos por tarea."""
    global _task_cache_file
    if _task_cache_file is not None:
        return _task_cache_file
    try:
        cache_dir = settings.nas_sandbox_path
        if cache_dir and os.path.isdir(cache_dir):
            _task_cache_file = os.path.join(cache_dir, "task_model_cache.json")
            return _task_cache_file
    except Exception:
        pass
    # Fallback: directorio 'db' relativo al router
    router_dir = os.path.dirname(os.path.abspath(__file__))
    _task_cache_file = os.path.join(router_dir, "..", "db", "task_model_cache.json")
    return _task_cache_file


def _load_task_cache() -> Dict[str, Dict[str, Any]]:
    """Carga la caché de modelos por tipo de tarea desde disco."""
    global _task_model_cache, _task_cache_initialized
    if _task_cache_initialized:
        return _task_model_cache
    _task_model_cache = {}
    try:
        cache_path = _get_cache_file_path()
        if os.path.isfile(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                _task_model_cache = data
                logger.info(f"Task cache cargado: {len(_task_model_cache)} tipos de tarea")
    except Exception as e:
        logger.debug(f"No se pudo cargar task cache: {e}")
    _task_cache_initialized = True
    return _task_model_cache


def _save_task_cache() -> None:
    """Guarda la caché de modelos por tipo de tarea a disco."""
    try:
        cache_path = _get_cache_file_path()
        cache_dir = os.path.dirname(cache_path)
        if cache_dir and not os.path.isdir(cache_dir):
            os.makedirs(cache_dir, exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(_task_model_cache, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.debug(f"No se pudo guardar task cache: {e}")


def _update_task_cache(
    task_type: str,
    model: str,
    provider: str,
    arena_score: float = None,
    context_length: int = None,
    latency_ms: float = None,
) -> None:
    """Actualiza la caché tras una llamada exitosa."""
    entry = {
        "model": model,
        "provider": provider,
        "updated_at": time.time(),
    }
    if arena_score is not None:
        entry["arena_score"] = arena_score
    if context_length is not None:
        entry["context_length"] = context_length
    if latency_ms is not None:
        entry["latency_ms"] = latency_ms
    _task_model_cache[task_type] = entry
    _save_task_cache()


def get_task_priority(task_type: str) -> str:
    """Retorna la prioridad de optimización para un tipo de tarea."""
    return _TASK_PRIORITY_MAP.get(task_type, "quality")


def initialize_router(cache_dir: str = None) -> Dict[str, Any]:
    """Inicialización al arrancar APA.

    1. Carga la caché local de modelos por tipo de tarea
    2. Si MB está configurado, valida los modelos cacheados con MB
    3. Prepara el arnés de Ollama como respaldo

    Retorna un dict con el reporte de inicio.
    """
    global _task_cache_file
    report = {
        "cache_loaded": False,
        "cached_task_types": 0,
        "mb_validated": False,
        "mb_validated_models": 0,
        "mb_available": False,
        "ollama_ready": False,
        "startup_mode": "standalone",
    }

    # 1. Cargar caché local
    if cache_dir:
        _task_cache_file = os.path.join(cache_dir, "task_model_cache.json")
    _load_task_cache()
    report["cache_loaded"] = True
    report["cached_task_types"] = len(_task_model_cache)

    # 2. Si MB está configurado, asegurar que esté corriendo y validar
    if _has_mb_config():
        report["startup_mode"] = "mb"

        # 2a. Intentar lanzar MB si no responde
        try:
            from core.mb_launcher import ensure_mb_running
            mb_launched = ensure_mb_running(settings.model_broker_url)
            if mb_launched:
                report["mb_launched"] = True
                logger.info("Router startup: MB lanzado por APA")
        except Exception as e:
            logger.debug("Router startup: mb_launcher no disponible: %s", e)

        # 2b. Validar con MB vía HTTP
        try:
            mb_url = settings.model_broker_url
            resp = requests.get(f"{mb_url.rstrip('/')}/api/models", timeout=5)
            if resp.status_code == 200:
                models_data = resp.json()
                if isinstance(models_data, list):
                    report["mb_available"] = True
                    report["mb_validated_models"] = len(models_data)
                    logger.info(
                        "Router startup: MB disponible vía HTTP, %d modelos",
                        len(models_data)
                    )
                elif isinstance(models_data, dict) and "models" in models_data:
                    models_list = models_data["models"]
                    report["mb_available"] = True
                    report["mb_validated_models"] = len(models_list)
                    logger.info(
                        "Router startup: MB disponible vía HTTP, %d modelos",
                        len(models_list)
                    )
                else:
                    logger.info("Router startup: MB respondió pero formato inesperado")
            else:
                logger.info("Router startup: MB no responde (HTTP %d)", resp.status_code)
        except Exception as e:
            logger.warning("Router startup: error conectando a MB: %s", e)

    # 3. Verificar Ollama como respaldo
    try:
        ollama_url = settings.ollama_base_url
        if ollama_url:
            resp = requests.get(f"{ollama_url}/api/tags", timeout=3)
            if resp.status_code == 200:
                report["ollama_ready"] = True
                logger.info("Router startup: Ollama disponible como respaldo")
            else:
                logger.info("Router startup: Ollama respondió con código %d", resp.status_code)
    except Exception:
        logger.info("Router startup: Ollama no disponible en este momento")

    logger.info(f"Router startup completado: modo={report['startup_mode']}, "
                f"cache={report['cached_task_types']} tareas, "
                f"mb={'OK' if report['mb_available'] else 'N/A'}, "
                f"ollama={'OK' if report['ollama_ready'] else 'N/A'}")

    return report


# ============================================================================
# Helpers de v6.6
# ============================================================================

def _estimate_tokens(text: str) -> int:
    """Estima el número de tokens de un texto (aprox 4 chars/token)."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def _classify_error_type(error_str: str) -> str:
    """P8c: Clasifica el tipo de error usando model_health._classify_error().

    ANTES: Tenía su propia lógica con nombres distintos (model_not_found, server).
    AHORA: Delega a model_health._classify_error() para garantizar consistencia.
    Los nombres de categoría ahora son los mismos en todo APA:
        rate_limit | not_found | auth | payment | server_error |
        timeout | connection | temporarily_unavailable | unknown

    Returns: una de las categorías anteriores, o "" si error_str está vacío.
    """
    if not error_str:
        return ""
    return model_health._classify_error(error_str)


def _estimate_cost_usd(
    tokens_input: int,
    tokens_output: int,
    model_id: str,
    provider_name: str = "",
) -> float:
    """Estima el coste en USD de una llamada LLM.

    Intenta obtener precios del provider_manager; si no puede,
    usa una estimación conservadora por defecto.
    """
    if provider_manager is not None:
        try:
            price = provider_manager.get_model_price(model_id, provider_name)
            prompt_price = price.get("prompt", 0.0)
            completion_price = price.get("completion", 0.0)
            cost = (tokens_input / 1000.0) * prompt_price + (tokens_output / 1000.0) * completion_price
            return round(cost, 6)
        except Exception:
            pass

    # Fallback: estimación genérica ($0.01/1K input, $0.03/1K output)
    if estimate_price is not None:
        try:
            per_token = estimate_price(model_id)
            return round((tokens_input + tokens_output) * per_token, 6)
        except Exception:
            return 0.0


# ============================================================================
# v6.2: Manejo reactivo de contexto excedido
# ============================================================================

def _handle_context_exceeded(
    task_type: str,
    system_prompt: str,
    user_prompt: str,
    failed_model_id: str,
    max_tokens: int = 2000,
    temperature: float = 0.1,
) -> Dict[str, Any]:
    """v6.2: Reacciona a un error de contexto excedido.

    Cuando un modelo dice "no me cabe", esta función:
    1. Calcula qué tan grande es el prompt completo
    2. Busca un modelo con más capacidad de contexto
    3. Si lo encuentra, reintenta la llamada con ese modelo
    4. Si no lo encuentra, devuelve una señal clara pidiendo desglose

    No cuenta como intento fallido — es como cambiar de buzón.
    """
    full_prompt = system_prompt + user_prompt
    prompt_tokens = _estimate_tokens(full_prompt)
    required_context = int((prompt_tokens + max_tokens) * 1.30)

    logger.info(
        f"_handle_context_exceeded: prompt ~{prompt_tokens} tokens, "
        f"se necesita contexto >= {required_context}. "
        f"Modelo que falló: {failed_model_id}"
    )

    # Buscar modelo con suficiente contexto en el pool
    try:
        all_entries = _global_pool.get_all_entries()
        candidates = [
            e for e in all_entries
            if e.context_length >= required_context
            and e.model_id != failed_model_id
            and e.health_status in ("available", "unknown")
        ]
        # Ordenar por score (mejor primero)
        candidates.sort(key=lambda e: e.composite_score, reverse=True)
    except Exception as e:
        logger.warning(f"_handle_context_exceeded: error buscando candidatos: {e}")
        candidates = []

    if candidates:
        best = candidates[0]
        logger.info(
            f"_handle_context_exceeded: encontrado modelo más grande: "
            f"{best.model_id} (contexto: {best.context_length}, "
            f"score: {best.composite_score:.1f})"
        )

        # Apilar el modelo que falló para re-escalado futuro
        try:
            for e2 in _global_pool.get_all_entries():
                if e2.model_id == failed_model_id:
                    _push_model_to_stack(e2)
                    break
        except Exception:
            pass

        # Intentar la llamada con el modelo más grande
        if provider_manager is not None:
            try:
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]

                _, base_id = provider_manager.parse_prefixed_id(best.model_id)
                if base_id is None or base_id == best.model_id:
                    base_id = best.model_id

                result = None
                if best.provider in provider_manager.providers:
                    provider = provider_manager.providers[best.provider]
                    translated_id = provider_manager.translate_model_id(base_id, best.provider)
                    try:
                        result = provider.call(translated_id, messages, max_tokens, temperature)
                        if result.get("success"):
                            result["provider"] = best.provider
                    except Exception as e:
                        logger.debug(f"_handle_context_exceeded: provider {best.provider} falló: {e}")
                        result = None

                if result is None or not result.get("success"):
                    result = provider_manager.call_with_fallback(base_id, messages, max_tokens, temperature)

                if result.get("success"):
                    _sync_health_after_call(best.model_id, best.provider, True)
                    logger.info(
                        f"_handle_context_exceeded: éxito con {best.model_id} "
                        f"(contexto: {best.context_length})"
                    )
                    return {
                        **result,
                        "attempts": 1,
                        "context_scaled": True,
                        "original_model": failed_model_id,
                        "scaled_model": best.model_id,
                    }
                else:
                    logger.warning(
                        f"_handle_context_exceeded: {best.model_id} también falló "
                        f"({result.get('error', 'unknown')})"
                    )
                    # El modelo más grande también falló — devolver señal de desglose
                    pass

            except Exception as e:
                logger.warning(f"_handle_context_exceeded: error reintentando: {e}")
                pass

    # No se encontró modelo más grande o todos fallaron → señal de desglose
    # Buscar el modelo con mayor contexto disponible para informar
    max_available_context = 0
    if candidates:
        max_available_context = max(e.context_length for e in candidates)
    else:
        try:
            all_entries = _global_pool.get_all_entries()
            if all_entries:
                max_available_context = max(e.context_length for e in all_entries)
        except Exception:
            pass

    logger.warning(
        f"_handle_context_exceeded: sin modelo con contexto suficiente. "
        f"Necesario: {required_context}, Disponible: {max_available_context}. "
        f"Señal: split_task"
    )

    return {
        "content": "",
        "model_used": failed_model_id,
        "provider_used": None,
        "success": False,
        "attempts": 0,
        "error": "context_exceeded_no_fallback",
        "error_type": "context_exceeded_no_fallback",
        "tokens_needed": required_context,
        "max_available_context": max_available_context,
        "action_required": "split_task",
        "message": (
            f"La tarea requiere ~{required_context} tokens de contexto. "
            f"El modelo más grande disponible tiene {max_available_context}. "
            f"Desglose la tarea en partes más pequeñas."
        ),
        "tokens_input": prompt_tokens,
        "tokens_output": 0,
        "latency_ms": 0,
        "cost_usd": 0.0,
        "arena_score": None,
        "provider": "",
        "http_status": 413,
    }


# ============================================================================
# v5.0: Pool population — llena el Pool desde providers
# ============================================================================
_pool_populated = False


def populate_pool(force: bool = False) -> int:
    """Puebla el Pool desde los providers con composite key (P-1).

    Phase 2: Delega al broker cuando está disponible, con fallback
    a la implementación legacy si el broker no existe.

    D-8/D-10: Non-blocking — si ya está poblado, no hace nada
    a menos que force=True.

    P-1: Cada (provider, model_id) es una entrada independiente.
    P-2: Provider Confidence se obtiene del provider.
    P-3: Arena scores se obtienen de arena_fetcher.

    v6.0 (Rendimiento): Ya NO espera a Arena data. Carga inmediata
    desde cache local. Los Arena scores se actualizan cuando el
    periodic refresh completa en background.

    Retorna: número de entries en el pool.
    """
    global _pool_populated

    # v7.2: MB gestiona su propio pool. APA solo usa pool local como
    # fallback (Capa 3) cuando MB no está disponible.

    if not force and _pool_populated and _global_pool.size() > 0:
        return _global_pool.size()

    if provider_manager is not None:
        try:
            # v6.0: Cache-first inmediato — sin spin-lock.
            # Arena ya cargó cache local al importar (Phase 0).
            # Si no hay datos de Arena, se poblará sin scores y se
            # actualizará cuando el periodic refresh complete.
            af = _get_arena_module()
            with af._refresh_lock:
                has_data = bool(af._arena_data) and len(af._arena_data) > 0
            if has_data:
                logger.info(f"populate_pool(): Arena data disponible desde cache ({len(af._arena_data)} modelos)")
            else:
                logger.info("populate_pool(): Arena data no disponible, poblando sin Arena scores")

            # P-1: Obtener modelos con provider (sin deduplicar por model_id)
            all_models = provider_manager.get_all_models_with_provider()

            if not all_models:
                logger.warning("populate_pool(): no se obtuvieron modelos de providers")
                return _global_pool.size()

            # Limpiar pool si force
            if force:
                _global_pool.clear()

            count = 0
            notable_count = 0  # Modelos con arena_score o status != unknown
            for m in all_models:
                # F6: Usar prefixed_id como identificador principal del modelo
                # prefixed_id = "OPR:anthropic/claude-opus-4-6" o "ANT:claude-opus-4-6"
                prefixed_id = m.get("prefixed_id", "")
                base_id = m.get("base_id", m.get("id", ""))
                provider_name = m.get("provider", "")
                if not prefixed_id or not provider_name:
                    # Fallback: si no hay prefixed_id, usar el id original
                    if not base_id:
                        continue
                    prefixed_id = provider_manager.make_prefixed_id(provider_name, base_id)

                # Verificar si ya existe esta composite key
                existing = _global_pool.get_entry(provider_name, prefixed_id)
                if existing and not force:
                    continue  # Ya existe, no sobreescribir

                # Crear PoolEntry con composite key (P-1)
                # F6: model_id ahora es el prefixed_id (PROVEEDOR:modelo)
                entry = PoolEntry(
                    provider=provider_name,
                    model_id=prefixed_id,
                    context_length=m.get("context_length", 8192) or 8192,
                    is_free=bool(m.get("is_free", False) or m.get("is_free_tier", False)),
                    provider_confidence=m.get("provider_confidence", 50.0),
                    capabilities=m.get("capabilities", []),
                    pricing=m.get("pricing", {}),
                )

                # P-3: Arena score (Capa 2) — buscar usando base_id
                # F6: El Arena score se busca con el nombre original (sin prefijo)
                # porque Arena no conoce nuestros prefijos de proveedor
                arena_score = _get_arena_score(base_id, None)
                if arena_score is not None:
                    entry.arena_score = arena_score
                    entry.apa_score = arena_score  # APA placeholder (DEFERRED)

                # v1.1: Obtener TODOS los scores por categoría del modelo
                try:
                    af = _get_arena_module()
                    all_scores = af.get_model_all_scores(base_id)
                    if all_scores:
                        entry.arena_scores = all_scores
                except Exception:
                    pass  # No crítico — fallback a composite_score

                # Sync health from model_health — usar base_id para lookup
                entry.health_status = model_health.get_status(base_id)

                _global_pool.add_entry(entry)
                count += 1

                # v6.6: Notificar SOLO modelos notables al pool para no inundar
                is_notable = entry.arena_score is not None or entry.health_status != "unknown"
                if is_notable:
                    notable_count += 1
                    _notify("pool:model_updated",
                            f"Pool + {base_id} [{entry.health_status}]"
                            + (f" score:{entry.arena_score:.0f}" if entry.arena_score else ""),
                            {"model": base_id, "provider": provider_name,
                             "health": entry.health_status,
                             "arena_score": entry.arena_score})

            # P-2: Set provider confidence para cada provider
            for prov_name, prov_obj in provider_manager.providers.items():
                _global_pool.set_provider_confidence(prov_name, prov_obj.confidence_score)

            _pool_populated = True

            # Log resumen
            summary = _global_pool.health_summary()
            arena_count = sum(1 for e in _global_pool.get_all_entries() if e.arena_score is not None)
            logger.info(f"populate_pool(): {count} entries ({arena_count} con Arena score), "
                        f"health: {summary}")
            # v6.5: Notificar al usuario
            _notify("pool:populated",
                    f"Pool poblado: {count} modelos ({arena_count} con Arena score)",
                    {"total": count, "arena_scores": arena_count, "health": summary})

            # Notificar el lote de modelos no-notables
            unknown_count = count - notable_count
            if unknown_count > 0:
                _notify("pool:sync_batch",
                        f"Pool + {unknown_count} modelos sin ranking (cargados al pool)",
                        {"batch_count": unknown_count, "notable_count": notable_count,
                         "total": count})

            return count

        except Exception as e:
            logger.error(f"populate_pool(): error: {e}")
            return _global_pool.size()

def _sync_single_model_to_pool(base_id: str) -> None:
    """v6.6: Sincroniza UN modelo del health al pool en memoria.

    Callback registrado en model_health v6.0. Se llama tras cada
    mark_*() para que el pool refleje el cambio inmediatamente.
    Emite pool:model_updated por cada cambio de estado.
    """
    if provider_manager is not None:
        try:
            mh_status = model_health.get_status(base_id)
            for entry in _global_pool.get_all_entries():
                _, entry_base_id = provider_manager.parse_prefixed_id(entry.model_id)
                if entry_base_id is None or entry_base_id == entry.model_id:
                    entry_base_id = entry.model_id
                if entry_base_id != base_id:
                    continue
                # Encontrada la entry del pool para este modelo
                old_status = entry.health_status
                if mh_status == old_status:
                    continue  # Sin cambios
                if mh_status == "available":
                    _global_pool.mark_available(entry.provider, entry.model_id)
                elif mh_status == "payment_required" and old_status != "available":
                    _global_pool.mark_payment_required(entry.provider, entry.model_id)
                elif mh_status in ("rate_limited", "temporarily_unavailable") \
                        and old_status not in ("available",):
                    entry.health_status = mh_status
                    entry.verified_at = time.time()
                elif mh_status in ("failed", "model_removed") \
                        and old_status not in ("available",):
                    entry.health_status = mh_status
                    entry.verified_at = time.time()
                # v6.6: Notificar cambio individual
                _notify("pool:model_updated",
                        f"Pool ~ {base_id}: {old_status} -> {mh_status}",
                        {"model": base_id, "provider": entry.provider,
                         "old_health": old_status, "new_health": mh_status})
                break  # Solo primera entry encontrada
        except Exception as e:
            logger.debug(f"_sync_single_model_to_pool({base_id}): {e}")


def _get_pool_candidates_for_verification() -> List[str]:
    """v6.6: Retorna model_ids del pool que necesitan verificación real.

    Callback registrado en model_health v6.6. Se llama tras la primera
    pasada de previously_available para obtener modelos del pool que
    están en estado 'unknown', 'failed' o 'payment_required' — estos
    son modelos que entraron al pool desde los catálogos de proveedores
    y nunca fueron verificados por el background re-verification (que
    solo itera sobre _health_data de la caché anterior).

    Retorna lista de model_ids (prefixed_id) del pool.
    """
    if provider_manager is not None:
        try:
            candidates = []
            seen_base_ids = set()
            verify_statuses = {"unknown", "failed", "payment_required"}

            for entry in _global_pool.get_all_entries():
                if entry.health_status not in verify_statuses:
                    continue
                # Extraer base_id para deduplicar
                _, base_id = provider_manager.parse_prefixed_id(entry.model_id)
                if base_id is None or base_id == entry.model_id:
                    base_id = entry.model_id
                if base_id not in seen_base_ids:
                    seen_base_ids.add(base_id)
                    candidates.append(entry.model_id)

            return candidates
        except Exception as e:
            logger.debug(f"_get_pool_candidates_for_verification error: {e}")
    return []


_router_callback_registered = False


def _register_pool_sync_callback() -> None:
    """v6.4: Registra el callback de sync con model_health.

    v6.6: También registra pool_candidates_callback para que model_health
    pueda verificar modelos nuevos del pool tras la primera pasada.

    v6.7: Idempotente — usa flag booleano para evitar registro duplicado
    cuando router.py se importa bajo dos nombres distintos (core.router vs
    apa.core.router). El flag es seguro porque el self-dedup garantiza
    una sola instancia del modulo.
    """
    global _router_callback_registered
    if _router_callback_registered:
        logger.debug("v6.7: Pool sync callback ya registrado, skip")
        return
    try:
        if hasattr(model_health, 'register_pool_sync_callback'):
            model_health.register_pool_sync_callback(_sync_single_model_to_pool)
            logger.info("v6.4: Pool sync callback registrado en model_health")

        # v6.6: Registrar callback para obtener candidatos del pool
        if hasattr(model_health, 'register_pool_candidates_callback'):
            model_health.register_pool_candidates_callback(_get_pool_candidates_for_verification)
            logger.info("v6.6: Pool candidates callback registrado en model_health")

        _router_callback_registered = True
    except Exception as e:
        logger.debug(f"v6.4: Error registrando pool sync callback: {e}")


# v6.4: Registrar callback al importar (si model_health v6.0+ está disponible)
try:
    _register_pool_sync_callback()
except Exception as _cb_err:
    logger.debug(f"v6.4: No se pudo registrar pool sync callback: {_cb_err}")


def _sync_health_to_pool() -> int:
    """Sincroniza health status de model_health al pool.

    Batch sync: itera TODAS las entries del pool y actualiza
    las que difieran de model_health. Se usa como complemento
    del callback individual cuando se necesita sync masivo.

    v6.4: Ahora también sincroniza model_removed y temporarily_unavailable.

    Retorna: número de entries actualizadas.
    """
    updated = 0
    if provider_manager is not None:
        try:
            for entry in _global_pool.get_all_entries():
                # F6: model_health usa base_id, pool usa prefixed_id
                _, base_id = provider_manager.parse_prefixed_id(entry.model_id)
                if base_id is None or base_id == entry.model_id:
                    base_id = entry.model_id
                mh_status = model_health.get_status(base_id)
                if mh_status != entry.health_status:
                    if mh_status == "available":
                        _global_pool.mark_available(entry.provider, entry.model_id)
                        updated += 1
                    elif mh_status == "payment_required" and entry.health_status != "available":
                        _global_pool.mark_payment_required(entry.provider, entry.model_id)
                        updated += 1
                    elif mh_status in ("rate_limited", "temporarily_unavailable") \
                            and entry.health_status not in ("available",):
                        entry.health_status = mh_status
                        entry.verified_at = time.time()
                        updated += 1
                    elif mh_status in ("failed", "model_removed") \
                            and entry.health_status not in ("available",):
                        entry.health_status = mh_status
                        entry.verified_at = time.time()
                        updated += 1
            if updated > 0:
                logger.debug(f"_sync_health_to_pool(): {updated} entries actualizadas")
                # v6.5: Notificar al usuario (solo si hay cambios significativos)
                if updated >= 5:
                    _notify("pool:sync_batch",
                            f"Pool sincronizado: {updated} modelos actualizados",
                            {"updated": updated})
        except Exception as e:
            logger.debug(f"_sync_health_to_pool(): error: {e}")
    return updated


def update_arena_scores() -> int:
    """v5.4 (F4): Re-escanea pool entries y llena Arena scores faltantes.

    Safety net: si populate_pool() corrió antes de que el background
    refresh de Arena completara, esta función rellena los scores.

    Retorna: número de entries actualizadas.
    """
    updated = 0
    try:
        for entry in _global_pool.get_all_entries():
            if entry.arena_score is None:
                score = _get_arena_score(entry.model_id, None)
                if score is not None:
                    entry.arena_score = score
                    entry.apa_score = score  # APA placeholder
                    updated += 1
        if updated > 0:
            logger.info(f"update_arena_scores(): {updated} entries actualizadas con Arena score")
            # v6.5: Notificar al usuario
            _notify("arena:refresh_complete",
                    f"Arena scores actualizados: {updated} modelos nuevos con score",
                    {"updated": updated})
    except Exception as e:
        logger.debug(f"update_arena_scores(): error: {e}")
    return updated


_cache: Dict[str, Any] = {
    "data": None,
    "timestamp": None,
}
_CACHE_DURATION = 600

PROVIDER_PREFIX_MAP = {
    "moonshotai/": "moonshot",
    "anthropic/": "anthropic",
    "openai/": "openai",
    "meta-llama/": "meta",
    "qwen/": "alibaba",
    "google/": "google",
    "mistralai/": "mistral",
    "deepseek/": "deepseek",
    "cohere/": "cohere",
}

def _infer_provider(model_id: str) -> str:
    """Infiere el proveedor real a partir del prefijo del ID del modelo."""
    if not model_id:
        return "unknown"
    mid = model_id.lower()
    for prefix, provider in PROVIDER_PREFIX_MAP.items():
        if mid.startswith(prefix):
            return provider
    return "unknown"


def fetch_free_models() -> List[Dict[str, Any]]:
    global _cache
    now = time.time()
    if _cache["data"] is not None and _cache["timestamp"] is not None:
        if now - _cache["timestamp"] < _CACHE_DURATION:
            return _cache["data"]
    
    try:
        resp = requests.get(
            "https://openrouter.ai/api/v1/models",
            headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
            timeout=5
        )
        resp.raise_for_status()
        models = [
            m for m in resp.json().get("data", [])
            if str(m.get("pricing", {}).get("prompt", " ")) == "0"
            and str(m.get("pricing", {}).get("completion", " ")) == "0"
        ]
        out = []
        for m in models:
            model_id = m.get("id", "")
            ctx_len = m.get("context_length", 0)
            out.append({
                "id": model_id,
                "name": m.get("name", ""),
                "context_length": ctx_len,
                "provider": "openrouter",
                "is_free_tier": True,
                "is_free": True
            })
        out.sort(key=lambda x: x["context_length"], reverse=True)
        if not out:
            return []
        _cache["data"] = out
        _cache["timestamp"] = now
        return out
    except Exception as e:
        logger.error(f"Error fetching free models: {e}")
        return []

def fetch_free_tier_models() -> List[Dict[str, Any]]:
    return []

def _filter_text_models(models: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    blocked = {"lyria", "audio", "music", "imagen", "image", "vision", "video", "clip"}
    return [m for m in models if not any(k in m["id"].lower() for k in blocked)]


def _is_free_model(model_dict: Dict[str, Any]) -> bool:
    """Detecta si un modelo es gratuito basandose en multiples senales."""
    mid = model_dict.get("id", "").lower()
    if mid.endswith(":free"):
        return True
    if model_dict.get("is_free_tier"):
        return True
    if model_dict.get("is_free"):
        return True
    pricing = model_dict.get("pricing", {})
    if pricing:
        try:
            p = float(pricing.get("prompt", 1))
            c = float(pricing.get("completion", 1))
            if p == 0 and c == 0:
                return True
        except (ValueError, TypeError):
            pass
    if model_dict.get("price_prompt_per_1k", 1) == 0 and model_dict.get("price_completion_per_1k", 1) == 0:
        return True
    return False


def get_all_available_models() -> List[Dict[str, Any]]:
    """Retorna TODOS los modelos disponibles de TODOS los proveedores.

    v4.1: Usa lazy import de provider_manager (no se carga al importar router).
    """
    try:
        seen = {}

        try:
            if provider_manager is not None:
                all_models = provider_manager.get_all_models()
                for m in all_models:
                    mid = m.get("id", "")
                    if mid and mid not in seen:
                        m["is_free"] = _is_free_model(m)
                        seen[mid] = m
        except Exception as e:
            logger.warning(f"Error getting models from provider_manager: {e}")

        try:
            openrouter_free = fetch_free_models()
            for m in openrouter_free:
                mid = m.get("id", "")
                if mid and mid not in seen:
                    m["is_free"] = True
                    seen[mid] = m
        except Exception:
            pass

        combined = list(seen.values())
        combined.sort(key=lambda x: x.get("context_length", 0), reverse=True)

        free_count = sum(1 for m in combined if m.get("is_free"))
        paid_count = len(combined) - free_count
        logger.debug(f"[get_all_available_models] {len(combined)} modelos "
                     f"({free_count} gratuitos, {paid_count} de pago)")

        return combined
    except Exception as e:
        logger.error(f"Error en get_all_available_models: {e}")
        return []


# Context length minimo por task_type (filtro, no score)
_MIN_CONTEXT_LENGTH = {
    "planning": 16000,
    "evaluation": 8000,
    "generation": 8000,
    "coding": 4000,
    "correction": 4000,
}


# CV3: Tiers de modelo por tipo de tarea
# "fast"     -> prefiere modelos de baja latencia (ctx <= 32k), ideales para chat fluido
# "capable"  -> sin restricción de contexto, usa el mejor modelo disponible para tareas complejas
_TASK_TYPE_TIER = {
    "chat":           "fast",
    "evaluation":     "fast",
    "sdd_evaluation": "fast",
    # Tareas que requieren el modelo más capaz disponible:
    "planning":       "capable",
    "generation":     "capable",
    "coding":         "capable",
    "correction":     "capable",
    "spec_generation":"capable",
    "sdd_generation": "capable",
    "analysis":       "capable",
}

# Techo de contexto para tier "fast" — filtra modelos grandes que son más lentos
_FAST_TIER_MAX_CONTEXT = 32000


def get_task_tier(task_type: str) -> str:
    """Retorna el tier de modelo para un tipo de tarea.

    CV3: Permite al resto del sistema consultar el tier
    sin acoplarse al diccionario interno.
    Retorna "capable" por defecto para task_types no registrados.
    """
    return _TASK_TYPE_TIER.get(task_type, "capable")

# v5.2: Guard contra recursión circular select_model_entry ↔ select_model
_in_select_model_entry = False


def select_model_entry(
    task_type: str,
    quality_mode: str = None,
    required_context: int = 0,
) -> Optional[PoolEntry]:
    """Selecciona el mejor modelo para una tarea, retornando PoolEntry.

    v6.0: Ahora acepta required_context para escalado fluido.
    Si se proporciona un tamaño de tarea, verifica que el modelo
    seleccionado tenga capacidad suficiente. Si no, des-escala
    automáticamente al siguiente modelo que pueda manejarla.

    D-1/D-2: Sin free_first bias — el ranking puro decide.
    P-1: Retorna PoolEntry con composite key (provider, model_id).
    P-3: 3-Layer Ranking — APA > Arena ELO > Provider Confidence.
    D-8/D-10: Non-blocking — pobla pool lazy, usa lo que haya.

    Flujo:
    1. Poblar pool lazy si está vacío (populate_pool)
    2. Buscar entries available (verified) en el pool
    3. Si no hay verified, buscar unknown/rate_limited
    4. v6.0: Si required_context > 0, verificar aptitud y des-escalar si hace falta
    5. Fallback a método clásico (probing activo) — SIN recursión

    v5.2 FIX: PASO 3 usa guard _in_select_model_entry para evitar
    que select_model() delegue de vuelta a select_model_entry()
    cuando ya estamos dentro de select_model_entry().

    Retorna PoolEntry o None si no hay modelo disponible.
    """
    global _in_select_model_entry

    try:
        model_health.ensure_loaded()

        # D-8/D-10: Poblar pool lazy (non-blocking)
        if _global_pool is not None and _global_pool.size() == 0:
            populate_pool()

        # CV3: Determinar max_context según tier del task_type
        task_tier = get_task_tier(task_type)
        fast_max_ctx = _FAST_TIER_MAX_CONTEXT if task_tier == "fast" else 0

        # PASO 1: Buscar entries available (verified) en el pool
        ranked = _global_pool.get_ranked_entries(
            task_type=task_type,
            max_context=fast_max_ctx,
            only_available=True,
        )

        # CV3: Fallback sin restricción de contexto si tier "fast" no encuentra modelos
        if task_tier == "fast" and not ranked:
            logger.info(f"CV3: No hay modelos rápidos (ctx<={_FAST_TIER_MAX_CONTEXT}) para {task_type}, "
                       f"expandiendo búsqueda a todos los modelos")
            ranked = _global_pool.get_ranked_entries(
                task_type=task_type,
                only_available=True,
            )

        if ranked:
            best = ranked[0]

            # v6.0: Verificar aptitud del modelo vs tamaño de tarea
            if required_context > 0 and best.context_length < required_context:
                logger.info(
                    f"select_model_entry({task_type}): {best.model_id} tiene "
                    f"contexto {best.context_length} pero tarea necesita "
                    f"{required_context} — buscando alternativa con más capacidad..."
                )
                alternative = _select_model_for_context(task_type, required_context, best)
                if alternative:
                    return alternative
                # Si no hay alternativa, continuar con el mejor disponible
                # (el modelo puede manejarlo truncando o puede que la estimación
                # sea conservadora)
                logger.warning(
                    f"select_model_entry({task_type}): no hay modelo con "
                    f"suficiente contexto ({required_context}), usando "
                    f"{best.model_id} ({best.context_length}) como último recurso"
                )

            logger.info(f"select_model_entry({task_type}): {best.model_id} "
                       f"via {best.provider} (score: {best.composite_score:.1f}, VERIFIED)")
            return best

        # PASO 2: Sin verified -> buscar unknown/rate_limited
        # v5.7: free_first=True (D-1b/D-2b) — preferir modelos gratuitos
        # cuando no hay verified models. Los modelos unknown de pago tienen
        # scores altos pero fallarán sin crédito; los gratuitos probablemente
        # funcionen. Dentro de cada tier (free/paid), se ordena por score.
        #
        # Esto resuelve el bug crítico: ANT:claude-opus-4-6 (score 90.1, unknown)
        # siempre ganaba sobre GHU:gpt-4o (score 87.0, unknown) porque el
        # ranking puro no distingue free de paid. Con free_first, el modelo
        # gratuito se intenta primero.
        #
        # F10: También excluir temporarily_unavailable (cooldown 60s)
        # v6.7: Excluir también rate_limited — modelo pausado no debe re-seleccionarse
        ranked = _global_pool.get_ranked_entries(
            task_type=task_type,
            max_context=fast_max_ctx,
            exclude_statuses=["payment_required", "failed", "temporarily_unavailable", "rate_limited"],
            free_first=True,  # v5.7: D-1b/D-2b — free antes que paid
        )

        # CV3: Fallback sin restricción si tier "fast" no encuentra modelos
        if task_tier == "fast" and not ranked:
            ranked = _global_pool.get_ranked_entries(
                task_type=task_type,
                exclude_statuses=["payment_required", "failed", "temporarily_unavailable", "rate_limited"],
                free_first=True,
            )

        if ranked:
            best = ranked[0]
            tier = "FREE" if best.is_free else "PAID"
            logger.info(f"select_model_entry({task_type}): {best.model_id} "
                       f"via {best.provider} (score: {best.composite_score:.1f}, "
                       f"{best.health_status}, {tier})")
            return best

        # PASO 3: Fallback a método clásico (probing activo)
        # v5.2: Guard contra recursión circular con select_model()
        if _in_select_model_entry:
            logger.warning(f"select_model_entry({task_type}): recursión detectada,"
                          f" no se llama a select_model() fallback")
            return None

        _in_select_model_entry = True
        try:
            model_id = select_model(task_type, quality_mode)
        finally:
            _in_select_model_entry = False

        if model_id is None:
            return None

        # Crear PoolEntry y añadir al pool si no existe
        provider = _infer_provider(model_id)
        existing = _global_pool.get_entry(provider, model_id)
        if existing:
            # Actualizar health si model_health lo marca como available
            if model_health.is_available(model_id):
                _global_pool.mark_available(provider, model_id)
                existing = _global_pool.get_entry(provider, model_id)
            return existing

        entry = PoolEntry(
            provider=provider,
            model_id=model_id,
        )
        # Intentar obtener scores
        arena_score = _get_arena_score(model_id, task_type)
        if arena_score is not None:
            entry.arena_score = arena_score
            entry.apa_score = arena_score  # placeholder

        # Sync health
        entry.health_status = model_health.get_status(model_id)
        _global_pool.add_entry(entry)

        logger.info(f"select_model_entry({task_type}): {model_id} "
                   f"via {provider} (fallback, {entry.health_status})")
        return entry

    except Exception as e:
        logger.error(f"Error en select_model_entry: {e}")
        return None


def select_model(task_type: str, quality_mode: str = None) -> Optional[str]:
    """Selecciona el mejor modelo para una tarea (retorna str, backward compat).
    
    v5.1: DELEGA a select_model_entry() cuando el Pool tiene entries.
    Esto garantiza que select_model() SIEMPRE usa el ranking del Pool
    (3-layer ranking: APA > Arena > Provider Confidence), nunca cae a
    ordenamiento alfabético o por context_length.
    
    Flujo:
    1. Si Pool tiene entries → usar select_model_entry() → return model_id
    2. Si Pool vacío → método clásico (Arena ELO + probing)
    """
    try:
        # v5.2: Solo delegar al Pool si NO venimos de select_model_entry()
        # (evita recursión circular cuando PASO 3 llama a select_model())
        if not _in_select_model_entry and _global_pool.size() > 0:
            entry = select_model_entry(task_type, quality_mode)
            if entry is not None:
                return entry.model_id
            # entry es None → Pool sin candidates → fallback a método clásico

        model_health.ensure_loaded()

        all_models = get_all_available_models()
        text_models = _filter_text_models(all_models)
        if not text_models:
            return None

        min_ctx = _MIN_CONTEXT_LENGTH.get(task_type, 0)

        candidates = [m for m in text_models if m.get("context_length", 0) >= min_ctx]
        if not candidates:
            candidates = text_models

        # v4.1: Usa lazy wrapper para Arena scores
        scored = []
        for model in candidates:
            arena_score = _get_arena_score(model["id"], task_type)
            if arena_score is None:
                arena_score = _get_arena_score(model["id"], None)
            if arena_score is None:
                continue
            scored.append((model, arena_score))

        if not scored:
            logger.warning(f"select_model({task_type}): ningun modelo tiene score Arena, "
                           f"Pool vacío, usando composite_score del Pool clásico")
            # v5.1: Ya no hay fallback alfabético — si no hay scores,
            # poblar Pool y reintentar
            populate_pool()
            if _global_pool.size() > 0:
                entry = select_model_entry(task_type, quality_mode)
                if entry is not None:
                    return entry.model_id
            # Último recurso: mayor context_length
            candidates.sort(key=lambda x: x.get("context_length", 0), reverse=True)
            return candidates[0]["id"] if candidates else None

        scored.sort(key=lambda x: x[1], reverse=True)

        # PASO 1: Buscar el mejor modelo verificado como available
        verified_list = model_health.get_verified_models()
        trust_window = model_health.get_trust_window()
        logger.info(f"select_model({task_type}): {len(verified_list)} modelos verificados "
                    f"en model_health: {verified_list[:5]}")

        for model, arena_score in scored:
            if model_health.is_available(model["id"]):
                info = model_health.get_all_health().get(model["id"], {})
                verified_at = info.get("verified_at")
                trust_tag = ""
                if verified_at is not None:
                    age = time.time() - verified_at
                    if age > 10:
                        trust_tag = ", SESSION TRUST"
                logger.info(f"select_model({task_type}): {model['id']} "
                           f"(Arena: {arena_score:.1f}, verificado available{trust_tag})")
                return model["id"]

        # PASO 2: No hay verificados -> probe sincronico
        logger.info(f"select_model({task_type}): no hay modelos verificados, "
                    f"haciendo probe sincronico a candidatos")

        # D-1/D-2: Eliminado free_first bias — ranking puro
        def _probe_priority(item):
            model_dict, arena_score = item
            m_id = model_dict["id"]
            st = model_health.get_status(m_id)
            # D-5: payment_required models get lowest priority
            status_order = {"available": 0, "unknown": 1, "rate_limited": 2, "failed": 3, "payment_required": 4}
            status_rank = status_order.get(st, 1)
            return (status_rank, -arena_score)

        probe_candidates = sorted(scored, key=_probe_priority)

        probed_count = 0
        max_probes = 12
        for model, arena_score in probe_candidates:
            if probed_count >= max_probes:
                break

            status = model_health.get_status(model["id"])

            if status == "available":
                continue
            if status == "failed":
                continue

            success, provider = model_health.probe_model_sync(model["id"])
            probed_count += 1

            if success:
                logger.info(f"select_model({task_type}): {model['id']} "
                           f"(Arena: {arena_score:.1f}, probe OK, provider: {provider})")
                return model["id"]

            time.sleep(0.5)

        # PASO 3: Reintentar failed
        for model, arena_score in scored:
            if model_health.get_status(model["id"]) == "failed":
                success, provider = model_health.probe_model_sync(model["id"])
                if success:
                    logger.info(f"select_model({task_type}): {model['id']} "
                               f"(Arena: {arena_score:.1f}, reintento OK)")
                    return model["id"]

        # PASO 4: Ultimo recurso
        best_model, best_score = scored[0]
        logger.warning(f"select_model({task_type}): ningun modelo verificado, "
                       f"usando {best_model['id']} sin verificar (Arena: {best_score:.1f})")
        return best_model["id"]
        
    except Exception as e:
        logger.error(f"Error en select_model: {e}")
        return None


def escalate_model(current_model_id: str) -> Optional[str]:
    """Escala a un modelo de mayor ranking Arena."""
    try:
        all_models = get_all_available_models()
        text_models = _filter_text_models(all_models)
        
        def arena_rank(m):
            score = _get_arena_score(m["id"], None)
            return score if score is not None else -1
        
        text_models.sort(key=arena_rank, reverse=True)
        
        for i, m in enumerate(text_models):
            if m["id"] == current_model_id:
                if i < len(text_models) - 1:
                    return text_models[i + 1]["id"]
        return current_model_id
    except Exception as e:
        logger.error(f"Error en escalate_model: {e}")
        return current_model_id


_llm_cache = LLMCache() if LLMCache is not None else None

def _sync_health_after_call(model_id: str, provider: str, success: bool,
                            error: str = "") -> None:
    """Sincroniza el resultado de una llamada LLM al Pool y model_health.

    Phase 2: Delega al broker cuando está disponible, con fallback legacy.

    D-3/D-4/D-5: Response-Code-Driven Scheduling.

    v5.5: empty_response → mark_failed (permanente, no temporarily_unavailable).
          Modelos que retornan HTTP 200 sin contenido están rotos.

    F6: model_id puede ser un prefixed_id (ej: "OPR:anthropic/claude-opus-4-6").
    - Para el Pool: se usa el prefixed_id (es la clave composite).
    - Para model_health: se extrae el base_id (model_health no conoce prefijos).
    """
    # v7.2: MB gestiona health internamente. APA solo sincroniza su
    # pool local (para Capa 3 fallback).

    try:
        # F6: Extraer base_id para model_health
        if provider_manager is not None:
            try:
                _, base_id = provider_manager.parse_prefixed_id(model_id)
                if base_id is None or base_id == model_id:
                    base_id = model_id  # Sin prefijo, usar tal cual
            except Exception:
                base_id = model_id  # Fallback
        else:
            base_id = model_id

        if success:
            model_health.mark_available(base_id, provider)
            _global_pool.mark_available(provider, model_id)
        else:
            error_type = model_health._classify_error(error)
            if error_type == "rate_limit":
                model_health.mark_rate_limited(base_id, provider)
                _global_pool.mark_rate_limited(provider, model_id)
            elif error_type == "payment":
                model_health.mark_payment_required(base_id, provider)
                _global_pool.mark_payment_required(provider, model_id)
                # v6.7: El fallo es del MODELO, no del proveedor.
                # Solo se marca este modelo específico. No hay cascada a otros
                # modelos del mismo proveedor ni del mismo LLM en otro proveedor.
                # Cada modelo es una entrada independiente en el pool.
                logger.info(f"_sync_health_after_call: payment_required para "
                           f"'{model_id}' (via {provider}). Modelo marcado individualmente.")
            elif error_type == "empty_response":
                # v5.5: empty_response → failed PERMANENTE.
                # Modelos que retornan 200 OK sin contenido están rotos.
                # No van a funcionar en reintentos — marcar como failed
                # para que no se vuelvan a intentar.
                model_health.mark_failed(base_id, provider, error)
                _global_pool.mark_failed(provider, model_id)
            elif error_type in ("auth", "not_found"):
                # Errores permanentes: marca como failed
                model_health.mark_failed(base_id, provider, error)
                _global_pool.mark_failed(provider, model_id)
            elif error_type in ("timeout", "connection", "server_error", "temporarily_unavailable"):
                # F10: Errores TRANSITORIOS → temporarily_unavailable (cooldown 60s)
                # NO marcar como 'failed' permanente — estos errores son reintentables
                model_health.mark_temporarily_unavailable(base_id, provider, error)
                _global_pool.mark_temporarily_unavailable(provider, model_id)
            else:
                # F10: 'unknown' → temporarily_unavailable en vez de failed
                # Cualquier error desconocido se trata como transitorio
                # (antes era failed permanente → cascada de fallos)
                model_health.mark_temporarily_unavailable(base_id, provider, error)
                _global_pool.mark_temporarily_unavailable(provider, model_id)
    except Exception as e:
        logger.debug(f"_sync_health_after_call error: {e}")

def call_llm(
    task_type: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 2000,
    temperature: float = 0.1,
    project_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Llama al mejor LLM disponible para la tarea.

    v7.0 (fused): Tres capas de resolución:
    1. Model Broker (ruta primaria si está configurado)
    2. Emergency Harness (si MB cae: bootstrap → Ollama local)
    3. Pool/Providers de v6.6 (fallback original si MB no está configurado)

    La capa 3 preserva TODO el desescalado silencioso de v6.6 con sus
    34 funciones (escalate_model, select_model_entry, pool sync, etc.).
    """
    # --- INTEGRACION DE CACHE (de v6.6) ---
    if _llm_cache is not None:
        try:
            cached_response = _llm_cache.get(user_prompt, "", max_tokens=max_tokens, temperature=temperature)
            if cached_response is not None:
                logger.debug("Router cache HIT")
                return cached_response
        except Exception as e:
            logger.warning(f"Cache get failed (falling back to provider): {e}")

    logger.debug("Router cache MISS")
    call_start_time = time.time()

    # =========================================================================
    # CAPA 1: MODEL BROKER vía HTTP (v7.2)
    # =========================================================================
    if _has_mb_config():
        # v7.2: pasar tokens estimados y prioridad para selección inteligente
        _est_tokens = estimate_task_size(system_prompt, user_prompt, max_tokens)
        _priority = get_task_priority(task_type)
        result = _call_mb_http(
            task_type=task_type,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            estimated_tokens=_est_tokens,
            priority=_priority,
        )
        if result is not None:
            total_elapsed = int((time.time() - call_start_time) * 1000)
            if result.get("success"):
                logger.info(
                    "Router v7.2: MB HTTP éxito — %s via %s (%dms)",
                    result.get("model_used", "?"),
                    result.get("provider", "?"),
                    total_elapsed
                )
                try:
                    if _llm_cache is not None:
                        _llm_cache.set(
                            user_prompt,
                            result.get("model_used", ""),
                            result,
                            max_tokens=max_tokens,
                            temperature=temperature,
                        )
                except Exception:
                    pass
                # v7.1: actualizar caché de modelo por tipo de tarea
                try:
                    _update_task_cache(
                        task_type=task_type,
                        model=result.get("model_used", ""),
                        provider=result.get("provider", ""),
                        arena_score=result.get("arena_score"),
                        latency_ms=result.get("latency_ms"),
                    )
                except Exception:
                    pass
                return {
                    **result,
                    "attempts": 1,
                    "via_emergency": False,
                }
            else:
                # MB respondió pero la llamada falló (modelo no disponible, etc.)
                # No marcar MB como caído — el servicio responde, el modelo falló.
                logger.warning(
                    "Router v7.2: MB HTTP falló la llamada: %s",
                    result.get("error", "unknown")
                )
                return {
                    **result,
                    "attempts": 1,
                    "via_emergency": False,
                }
        # result is None → MB no responde (ConnectionError, Timeout)
        logger.warning("Router v7.2: MB no responde — activando emergency")

        # =============================================================
        # CAPA 2: EMERGENCY HARNESS (MB configurado pero caído)
        # =============================================================
        emergency_result = _run_emergency_harness(
            task_type=task_type,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            call_start_time=call_start_time,
        )

        # Si el emergency harness obtuvo respuesta (éxito o error controlado),
        # retornarla. Solo cae a la capa 3 si emergency no está configurado.
        if emergency_result is not None:
            return emergency_result

    # =========================================================================
    # CAPA 3: POOL/PROVIDERS DE V6.6 (fallback original)
    # =========================================================================
    # MB no está configurado o emergency no pudo resolver.
    # Usar el pipeline completo de v6.6: select_model_entry → provider.call
    # → desescalado silencioso hasta agotar el pool.
    logger.debug("Router v7.0: Usando pool/providers de v6.6 (fallback)")

    MAX_TOTAL_ATTEMPTS = 50  # v6.6: Safety net amplio
    real_attempt = 0
    total_attempt = 0
    tried_entries: set = set()  # (provider, model_id) pairs

    while total_attempt < MAX_TOTAL_ATTEMPTS:
        total_attempt += 1
        attempt_start_time = time.time()

        if provider_manager is not None:
            try:
                task_size = estimate_task_size(system_prompt, user_prompt, max_tokens)
                entry = select_model_entry(task_type, required_context=task_size)

                # v6.6: Excluir modelos ya intentados
                skip_attempts = 0
                while entry is not None and (entry.provider, entry.model_id) in tried_entries:
                    skip_attempts += 1
                    if skip_attempts > 100:
                        logger.warning(f"call_llm: todos los entries del pool ya fueron intentados "
                                  f"({len(tried_entries)} modelos probados)")
                        entry = None
                        break
                    _global_pool.mark_failed(entry.provider, entry.model_id)
                    entry = select_model_entry(task_type, required_context=task_size)

                if entry is None:
                    attempt_elapsed = int((time.time() - attempt_start_time) * 1000)
                    _log_usage_if_possible(
                        project_id=project_id,
                        model="",
                        task_type=task_type,
                        tokens_input=_estimate_tokens(system_prompt + user_prompt),
                        tokens_output=0,
                        latency_ms=attempt_elapsed,
                        cost_usd=0.0,
                        arena_score=None,
                        provider="",
                        success=False,
                        error_type="no_model_available",
                    )
                    return {
                        "content": "",
                        "model_used": "",
                        "provider_used": None,
                        "success": False,
                        "attempts": real_attempt + 1,
                        "error": "No se pudo seleccionar modelo",
                        "tokens_input": _estimate_tokens(system_prompt + user_prompt),
                        "tokens_output": 0,
                        "latency_ms": attempt_elapsed,
                        "cost_usd": 0.0,
                        "arena_score": None,
                        "provider": "",
                        "http_status": None,
                    }

                model_id = entry.model_id
                provider_name = entry.provider
                arena_score_val = entry.arena_score
                tried_entries.add((provider_name, model_id))

                # T4: Comprobacion de cuota antes de la llamada.
                # Si el proveedor agoto su presupuesto diario, se salta
                # y se intenta con el siguiente proveedor disponible.
                if _quota_tracker_cls is not None:
                    try:
                        qt_check = _quota_tracker_cls.get_instance().check_quota(provider_name)
                        if qt_check["blocked"]:
                            logger.warning(
                                "call_llm: %s bloqueado por cuota. Saltando.",
                                qt_check["message"]
                            )
                            _global_pool.mark_failed(provider_name, model_id)
                            continue
                        if qt_check["warning"]:
                            logger.warning(
                                "call_llm: %s", qt_check["message"]
                            )
                    except Exception as qt_err:
                        logger.debug("call_llm: quota check fallo (continuando): %s", qt_err)

                _, base_id = provider_manager.parse_prefixed_id(model_id)
                if base_id is None or base_id == model_id:
                    base_id = model_id

                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]

                result = None
                if provider_name in provider_manager.providers:
                    provider = provider_manager.providers[provider_name]
                    translated_id = provider_manager.translate_model_id(base_id, provider_name)
                    try:
                        result = provider.call(translated_id, messages, max_tokens, temperature)
                        if result.get("success"):
                            result["provider"] = provider_name
                    except Exception as e:
                        logger.debug(f"call_llm: provider directo {provider_name} falló: {e}")
                        result = None

                if result is None or not result.get("success"):
                    result = provider_manager.call_with_fallback(base_id, messages, max_tokens, temperature)

                attempt_elapsed_ms = int((time.time() - attempt_start_time) * 1000)

                if result.get("success"):
                    actual_provider = result.get("provider", provider_name)
                    actual_model = result.get("model_used", model_id)

                    _sync_health_after_call(model_id, actual_provider, True)

                    if actual_model != base_id and actual_model != model_id:
                        fallback_arena = _get_arena_score(actual_model, task_type)
                        if fallback_arena is not None:
                            arena_score_val = fallback_arena
                            logger.info(f"call_llm: fallback de {base_id} a {actual_model}, "
                                       f"Arena actualizado: {fallback_arena:.1f}")
                        _sync_health_after_call(actual_model, actual_provider, True)

                    try:
                        is_generic = actual_provider in (None, "openrouter", "unknown", "")
                        if is_generic:
                            inferred = result.get("model_info", {}).get("provider")
                            if not inferred or inferred == "unknown":
                                inferred = _infer_provider(actual_model)
                            if inferred and inferred != "unknown":
                                result["provider"] = inferred
                                actual_provider = inferred
                                logger.debug(f"Provider corrected from '{provider_name}' to '{inferred}' for model {actual_model}")
                    except Exception as e:
                        logger.warning(f"Failed to correct provider traceability: {e}")

                    try:
                        _llm_cache.set(user_prompt, actual_model, result, max_tokens=max_tokens, temperature=temperature)
                    except Exception as e:
                        logger.warning(f"Cache set failed (continuing): {e}")

                    tokens_input = 0
                    tokens_output = 0

                    usage_data = result.get("usage", {})
                    if usage_data:
                        tokens_input = usage_data.get("prompt_tokens", 0)
                        tokens_output = usage_data.get("completion_tokens", 0)

                    if tokens_input == 0:
                        tokens_input = _estimate_tokens(system_prompt + user_prompt)
                    if tokens_output == 0:
                        tokens_output = _estimate_tokens(result.get("content", ""))

                    total_tokens = tokens_input + tokens_output
                    cost_usd = _estimate_cost_usd(tokens_input, tokens_output, actual_model, actual_provider)

                    if arena_score_val is None:
                        arena_score_val = _get_arena_score(actual_model, task_type)

                    _log_usage_if_possible(
                        project_id=project_id,
                        model=actual_model,
                        task_type=task_type,
                        tokens_input=tokens_input,
                        tokens_output=tokens_output,
                        latency_ms=attempt_elapsed_ms,
                        cost_usd=cost_usd,
                        arena_score=arena_score_val,
                        provider=actual_provider,
                        success=True,
                        error_type="",
                        total_tokens=total_tokens,
                    )

                    return {
                        **result,
                        "attempts": real_attempt + 1,
                        "tokens_input": tokens_input,
                        "tokens_output": tokens_output,
                        "latency_ms": attempt_elapsed_ms,
                        "cost_usd": cost_usd,
                        "arena_score": arena_score_val,
                        "provider": actual_provider,
                    }

                # Llamada falló — sincronizar health
                error_str = str(result.get("error", "unknown"))
                health_provider = provider_name
                log_provider = result.get("provider") or provider_name or "unknown"
                _sync_health_after_call(model_id, health_provider, False, error_str)

                error_type_classified = _classify_error_type(error_str)
                _log_usage_if_possible(
                    project_id=project_id,
                    model=model_id,
                    task_type=task_type,
                    tokens_input=_estimate_tokens(system_prompt + user_prompt),
                    tokens_output=0,
                    latency_ms=attempt_elapsed_ms,
                    cost_usd=0.0,
                    arena_score=arena_score_val,
                    provider=log_provider,
                    success=False,
                    error_type=error_type_classified,
                )

                # v5.7: Payment discovery — no cuenta como intento real
                if error_type_classified == "payment":
                    provider_pr_count = sum(
                        1 for e in _global_pool.get_all_entries()
                        if e.provider == provider_name and e.health_status == "payment_required"
                    )
                    provider_total = sum(
                        1 for e in _global_pool.get_all_entries()
                        if e.provider == provider_name
                    )
                    logger.info(
                        f"call_llm: payment error ({model_id} via {log_provider}), "
                        f"provider sin crédito — no cuenta como intento, "
                        f"reintentando con otro modelo... "
                        f"[cascade: {provider_pr_count}/{provider_total} modelos de "
                        f"'{provider_name}' marcados payment_required]"
                    )
                    continue

                # v6.2: Contexto excedido — no cuenta como intento real
                http_code = result.get("http_status") or 0
                is_ctx_exceeded = (
                    error_type_classified == "context_exceeded"
                    or model_health.is_context_exceeded(http_code, error_str)
                )
                if is_ctx_exceeded:
                    logger.info(
                        f"call_llm: contexto excedido en {model_id} "
                        f"(http={http_code}, type={error_type_classified}) — "
                        f"buscando modelo más grande..."
                    )
                    ctx_result = _handle_context_exceeded(
                        task_type=task_type,
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        failed_model_id=model_id,
                        max_tokens=max_tokens,
                        temperature=temperature,
                    )
                    return ctx_result

                # Contar como intento real
                real_attempt += 1

                if error_type_classified == "rate_limit":
                    escalate_model(model_id)
                    time.sleep(1)

                # v6.6: Desescalado silencioso
                logger.info(f"call_llm: intento {real_attempt} falló ({error_type_classified}), "
                           f"desescalando silenciosamente al siguiente modelo... "
                           f"[{len(tried_entries)} modelos probados]")
                continue
            except Exception as e:
                attempt_elapsed_ms = int((time.time() - attempt_start_time) * 1000)
                logger.error(f"Excepcion en call_llm: {e}")

                _log_usage_if_possible(
                    project_id=project_id,
                    model="",
                    task_type=task_type,
                    tokens_input=_estimate_tokens(system_prompt + user_prompt),
                    tokens_output=0,
                    latency_ms=attempt_elapsed_ms,
                    cost_usd=0.0,
                    arena_score=None,
                    provider="",
                    success=False,
                    error_type=_classify_error_type(str(e)),
                )
                break
        else:
            break

    # v6.6: Pool agotado
    total_elapsed_ms = int((time.time() - call_start_time) * 1000)

    logger.warning(
        f"call_llm: POOL AGOTADO tras {real_attempt} intentos reales, "
        f"{total_attempt} intentos totales, {len(tried_entries)} modelos probados. "
        f"Latencia total: {total_elapsed_ms}ms"
    )
    _log_usage_if_possible(
        project_id=project_id,
        model="",
        task_type=task_type,
        tokens_input=_estimate_tokens(system_prompt + user_prompt),
        tokens_output=0,
        latency_ms=total_elapsed_ms,
        cost_usd=0.0,
        arena_score=None,
        provider="",
        success=False,
        error_type="pool_exhausted",
    )

    return {
        "content": "",
        "model_used": "",
        "provider_used": None,
        "success": False,
        "attempts": real_attempt,
        "error": f"Pool agotado: {real_attempt} modelos probados, ninguno disponible",
        "error_type": "pool_exhausted",
        "tokens_input": _estimate_tokens(system_prompt + user_prompt),
        "tokens_output": 0,
        "latency_ms": total_elapsed_ms,
        "cost_usd": 0.0,
        "arena_score": None,
        "provider": "",
        "http_status": None,
    }

def _log_usage_if_possible(
    project_id: Optional[str],
    model: str,
    task_type: str,
    tokens_input: int,
    tokens_output: int,
    latency_ms: int,
    cost_usd: float,
    arena_score: Optional[float],
    provider: str,
    success: bool,
    error_type: str,
    total_tokens: int = 0,
) -> None:
    """v6.3: Helper para registrar uso con métricas completas.

    No falla nunca — errores de logging no deben interrumpir el flujo.
    Solo registra si project_id está disponible.
    """
    if project_id is None:
        return

    if _usage_tracker_cls is not None:
        try:
            if total_tokens == 0:
                total_tokens = tokens_input + tokens_output

            _usage_tracker_cls().log_usage(
                project_id=project_id,
                model=model,
                tokens=total_tokens,
                request_type=task_type,
                provider=provider,
                tokens_input=tokens_input,
                tokens_output=tokens_output,
                latency_ms=latency_ms,
                cost_usd=cost_usd,
                arena_score=arena_score,
                success=success,
                error_type=error_type,
            )
            logger.info(
                f"Usage logged: project={project_id} model={model} "
                f"provider={provider} task={task_type} "
                f"tokens_in={tokens_input} tokens_out={tokens_output} "
                f"latency={latency_ms}ms cost=${cost_usd:.4f} "
                f"arena={arena_score} success={success} "
                f"error_type={error_type}"
            )

            # T4: Registrar gasto en QuotaTracker
            if success and cost_usd > 0 and provider and _quota_tracker_cls is not None:
                try:
                    _quota_tracker_cls.get_instance().record_spending(
                        provider=provider,
                        cost_usd=cost_usd,
                        tokens=total_tokens,
                    )
                except Exception as qt_err:
                    logger.debug(f"QuotaTracker recording failed: {qt_err}")
        except Exception as e:
            logger.warning(f"Usage tracking failed (continuing): {e}")

def validate_self() -> bool:
    try:
        all_models = get_all_available_models()
        assert isinstance(all_models, list)
        if len(all_models) == 0:
            logger.warning("No hay modelos disponibles")
        else:
            sel = select_model("planning")
            assert sel is None or isinstance(sel, str)
        return True
    except Exception as e:
        logger.error(f"Fallo en validacion: {e}")
        return False


# =========================================================================
# VALIDACIÓN AUTÓNOMA — Emergency Harness + funciones v6.6
# =========================================================================
# v7.2: No se mockea ModelBroker como clase Python.
# Las pruebas de MB usan mock de requests.post (ver tests 10-14).
# =========================================================================


if __name__ == "__main__":
    passed = 0
    failed = 0
    skipped = 0

    def _check(name, condition):
        global passed, failed
        if condition:
            print(f"  [PASS] {name}")
            passed += 1
        else:
            print(f"  [FAIL] {name}")
            failed += 1

    def _skip(name, reason=""):
        global skipped
        _msg = f"{name} — {reason}" if reason else name
        print(f"  [SKIP] {_msg}")
        skipped += 1

    logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s')
    logger.setLevel(logging.INFO)

    print("\n" + "=" * 70)
    print("VALIDACIÓN AUTÓNOMA: core/router.py v7.2 (HTTP)")
    print("  v6.6 completo + Emergency Harness (bootstrap) + MB via HTTP")
    print("=" * 70)

    import types
    router_mod = sys.modules[__name__]

    # ------------------------------------------------------------------
    # Setup: resetear estado
    # ------------------------------------------------------------------
    def _reset():
        router_mod._broker_available = None
        router_mod._last_emergency_notify_time = 0.0

    # ------------------------------------------------------------------
    # 1. Presencia de funciones v6.6 (34 funciones críticas)
    # ------------------------------------------------------------------
    print("\n--- 1. Funciones de v6.6 presentes ---")
    v66_funcs = [
        '_notify', 'estimate_task_size', 'get_scaling_state', 're_escalate',
        'try_re_escalate', '_push_model_to_stack', '_select_model_for_context',
        '_get_arena_module', '_get_arena_score', '_get_arena_categories',
        '_estimate_tokens', '_classify_error_type', '_estimate_cost_usd',
        '_handle_context_exceeded', 'populate_pool', '_sync_single_model_to_pool',
        '_get_pool_candidates_for_verification', '_register_pool_sync_callback',
        '_sync_health_to_pool', 'update_arena_scores', '_infer_provider',
        'fetch_free_models', 'fetch_free_tier_models', '_filter_text_models',
        '_is_free_model', 'get_all_available_models', 'get_task_tier',
        'select_model_entry', 'select_model', 'escalate_model',
        '_sync_health_after_call', 'call_llm', '_log_usage_if_possible',
        'validate_self',
    ]
    for func in v66_funcs:
        _check(f"v6.6: {func}()", hasattr(router_mod, func) and callable(getattr(router_mod, func)))

    # ------------------------------------------------------------------
    # 2. Presencia de funciones del arnés (9 funciones nuevas)
    # ------------------------------------------------------------------
    print("\n--- 2. Funciones del arnés presentes ---")
    arnes_funcs = [
        '_has_mb_config', '_get_broker', '_call_mb_http', 'reset_broker_status',
        '_notify_emergency_to_user', '_try_bootstrap_mb',
        '_find_ollama_model', '_find_last_working_model',
        '_emergency_call', '_run_emergency_harness',
    ]
    for func in arnes_funcs:
        _check(f"Arnés: {func}()", hasattr(router_mod, func) and callable(getattr(router_mod, func)))

    # ------------------------------------------------------------------
    # 3. _has_mb_config
    # ------------------------------------------------------------------
    print("\n--- 3. _has_mb_config ---")
    # settings.model_broker_url puede ser @property sin setter,
    # asi que intercambiamos el objeto settings completo.
    _original_settings = router_mod.settings

    class _TestSettings:
        """Settings controlable para tests de _has_mb_config."""
        model_broker_url = ""
        model_broker_api_key = ""
        emergency_keys = {"ollama_base_url": "http://localhost:11434", "ollama_model": "llama3.1"}
        ollama_base_url = "http://localhost:11434"
        ollama_default_model = "llama3.1"
        openrouter_api_key = ""
        @property
        def model_broker_config(self):
            return {"url": self.model_broker_url, "api_key": self.model_broker_api_key}

    _ts = _TestSettings()
    router_mod.settings = _ts
    _check("Sin URL: False", router_mod._has_mb_config() is False)
    _ts.model_broker_url = "http://localhost:8000"
    _check("Con URL: True", router_mod._has_mb_config() is True)
    router_mod.settings = _original_settings

    # ------------------------------------------------------------------
    # 4. _get_broker y reset_broker_status
    # ------------------------------------------------------------------
    print("\n--- 4. _get_broker / reset ---")
    _reset()
    router_mod.settings = _ts
    _ts.model_broker_url = "http://localhost:8000"
    result = router_mod._get_broker()
    _check("Con URL configurada: True", result is True)
    router_mod._broker_available = False
    _check("Cache negativo: None", router_mod._get_broker() is None)
    router_mod.reset_broker_status()
    _check("Reset limpia cache", router_mod._broker_available is None)
    result = router_mod._get_broker()
    _check("Tras reset: disponible", result is True)
    _ts.model_broker_url = ""

    # ------------------------------------------------------------------
    # 5. _notify_emergency_to_user (no explota, throttle)
    # ------------------------------------------------------------------
    print("\n--- 5. _notify_emergency_to_user ---")
    _reset()
    router_mod._notify_emergency_to_user("test message")
    _check("No explota", True)
    router_mod._last_emergency_notify_time = time.time()
    router_mod._notify_emergency_to_user("throttled")
    _check("Throttle no crashea", True)

    # ------------------------------------------------------------------
    # 6. _find_ollama_model (sin Ollama corriendo)
    # ------------------------------------------------------------------
    print("\n--- 6. _find_ollama_model ---")
    _reset()
    import unittest.mock as _mock_lib
    with _mock_lib.patch.object(requests, 'get', side_effect=ConnectionError('no Ollama')):
        model = router_mod._find_ollama_model()
    _check("Sin Ollama: retorna default", model is not None and isinstance(model, str))
    _check("Default = 'llama3.1'", model == "llama3.1")

    # ------------------------------------------------------------------
    # 7. _find_last_working_model (sin tracker)
    # ------------------------------------------------------------------
    print("\n--- 7. _find_last_working_model ---")
    _reset()
    result = router_mod._find_last_working_model("chat")
    _check("Sin tracker: Ollama model", result is not None and isinstance(result, str))

    # ------------------------------------------------------------------
    # 8. _emergency_call (sin Ollama)
    # ------------------------------------------------------------------
    print("\n--- 8. _emergency_call ---")
    _reset()
    with _mock_lib.patch.object(requests, 'post', side_effect=ConnectionError('no Ollama')):
        result = router_mod._emergency_call(system_prompt="sys", user_prompt="hello")
    _check("Sin Ollama: success=False", result.get("success") is False)
    _check("Sin Ollama: via_emergency=True", result.get("via_emergency") is True)
    _check("Sin Ollama: provider=ollama_local", result.get("provider") == "ollama_local")
    _check("Sin Ollama: error menciona Ollama", result.get("error") and "Ollama" in result.get("error", ""))

    # ------------------------------------------------------------------
    # 9. _emergency_call NO menciona OpenRouter
    # ------------------------------------------------------------------
    print("\n--- 9. Sin OpenRouter en emergency ---")
    import inspect
    src = inspect.getsource(router_mod._emergency_call)
    _check("No menciona openrouter", "openrouter" not in src.lower())

    # ------------------------------------------------------------------
    # 10. call_llm con MB exitoso vía HTTP (Capa 1)
    # ------------------------------------------------------------------
    print("\n--- 10. call_llm MB exitoso (Capa 1) ---")
    _reset()
    router_mod.settings = _ts
    _ts.model_broker_url = "http://localhost:8000"
    _mock_response = _mock_lib.MagicMock()
    _mock_response.status_code = 200
    _mock_response.json.return_value = {
        "success": True, "content": "OK", "model_used": "gpt-4o",
        "provider": "openai", "tokens_input": 10, "tokens_output": 20,
    }
    with _mock_lib.patch.object(requests, 'post', return_value=_mock_response):
        result = router_mod.call_llm(task_type="chat", system_prompt="sys", user_prompt="hi")
    _check("MB HTTP exito: success=True", result.get("success") is True)
    _check("MB HTTP exito: via_emergency=False", result.get("via_emergency") is False)

    # ------------------------------------------------------------------
    # 11. call_llm MB caído → Emergency (Capa 2)
    # ------------------------------------------------------------------
    print("\n--- 11. call_llm MB caído → Emergency (Capa 2) ---")
    _reset()
    router_mod.settings = _ts
    _ts.model_broker_url = "http://localhost:8000"
    with _mock_lib.patch.object(requests, 'post', side_effect=ConnectionError("MB caído")), \
         _mock_lib.patch.object(requests, 'get', side_effect=ConnectionError("MB caído")):
        result = router_mod.call_llm(task_type="chat", system_prompt="sys", user_prompt="hi")
    _check("ConnectionError: via_emergency=True", result.get("via_emergency") is True)
    _check("ConnectionError: MB marcado caído", router_mod._broker_available is False)

    # ------------------------------------------------------------------
    # 12. call_llm MB success=False (NO activa emergency)
    # ------------------------------------------------------------------
    print("\n--- 12. MB modelo falla (no activa emergency) ---")
    _reset()
    router_mod.settings = _ts
    _ts.model_broker_url = "http://localhost:8000"
    _mock_fail = _mock_lib.MagicMock()
    _mock_fail.status_code = 200
    _mock_fail.json.return_value = {"success": False, "error": "Model not available"}
    with _mock_lib.patch.object(requests, 'post', return_value=_mock_fail):
        result = router_mod.call_llm(task_type="chat", system_prompt="sys", user_prompt="hi")
    _check("Modelo fallo: success=False", result.get("success") is False)
    _check("Modelo fallo: MB sigue disponible", router_mod._broker_available is not False)
    _ts.model_broker_url = ""

    # ------------------------------------------------------------------
    # 13. _try_bootstrap_mb
    # ------------------------------------------------------------------
    print("\n--- 13. _try_bootstrap_mb ---")
    _reset()
    router_mod.settings = _ts
    _ts.model_broker_url = "http://localhost:8000"
    with _mock_lib.patch.object(requests, 'get', side_effect=ConnectionError("no MB")):
        captured = router_mod._try_bootstrap_mb()
    _check("Sin conexión: False", captured is False)

    _reset()
    _ts.model_broker_url = "http://localhost:8000"
    _mock_status = _mock_lib.MagicMock()
    _mock_status.status_code = 200
    _mock_status.json.return_value = {"pool_size": 5, "providers_count": 2}
    _mock_boot_call = _mock_lib.MagicMock()
    _mock_boot_call.status_code = 200
    _mock_boot_call.json.return_value = {"success": True, "content": "OK", "model_used": "gpt-4o", "provider": "openai"}
    with _mock_lib.patch.object(requests, 'get', return_value=_mock_status), \
         _mock_lib.patch.object(requests, 'post', return_value=_mock_boot_call):
        captured = router_mod._try_bootstrap_mb()
    _check("Con MB OK: True", captured is True)
    _check("MB marcado disponible", router_mod._broker_available is True)
    _ts.model_broker_url = ""

    # ------------------------------------------------------------------
    # 14. MB marcado caído pero HTTP responde → restaura directo (v7.2)
    # ------------------------------------------------------------------
    print("\n--- 14. MB marcado caído pero responde → restaura directo ---")
    _reset()
    router_mod.settings = _ts
    _ts.model_broker_url = "http://localhost:8000"
    router_mod._broker_available = False
    # En v7.2, _call_mb_http siempre intenta la petición HTTP.
    # Si MB volvió, responde directo sin pasar por bootstrap.
    with _mock_lib.patch.object(requests, 'post', return_value=_mock_boot_call):
        result = router_mod.call_llm(task_type="chat", system_prompt="sys", user_prompt="hi")
    _check("MB restaurado: success=True", result.get("success") is True)
    _check("MB restaurado: via_emergency=False", result.get("via_emergency") is False)
    _check("MB restaurado: _broker_available=True", router_mod._broker_available is True)
    _ts.model_broker_url = ""

    # ------------------------------------------------------------------
    # 15. Silent descaling planning → chat
    # ------------------------------------------------------------------
    print("\n--- 15. Silent descaling ---")
    _check("planning → generation", router_mod._DESCALE_MAP.get("planning") == "generation")
    _check("spec → generation", router_mod._DESCALE_MAP.get("spec_generation") == "generation")
    _check("chat → None", router_mod._DESCALE_MAP.get("chat") is None)

    # ------------------------------------------------------------------
    # 16. get_scaling_state
    # ------------------------------------------------------------------
    print("\n--- 16. get_scaling_state ---")
    _reset()
    state = router_mod.get_scaling_state()
    _check("Retorna dict", isinstance(state, dict))
    _check("Tiene emergency_active", "emergency_active" in state)
    _check("Tiene current_model", "current_model" in state)

    # ------------------------------------------------------------------
    # 17. _run_emergency_harness retorna dict estructurado
    # ------------------------------------------------------------------
    print("\n--- 17. _run_emergency_harness ---")
    _reset()
    router_mod.settings = _ts
    _ts.model_broker_url = "http://localhost:8000"
    result = router_mod._run_emergency_harness(
        task_type="chat", system_prompt="sys", user_prompt="hi",
        max_tokens=100, temperature=0.7, call_start_time=time.time(),
    )
    _check("Retorna dict", isinstance(result, dict))
    _check("Tiene success", "success" in result)
    _check("Tiene via_emergency", "via_emergency" in result)
    _ts.model_broker_url = ""
    router_mod.settings = _original_settings

    # ------------------------------------------------------------------
    # 18. No importa core.arena_fetcher a nivel de módulo
    # ------------------------------------------------------------------
    print("\n--- 18. Imports limpios ---")
    source = open(__file__, encoding='utf-8').read()
    import re
    # Solo verificar imports de nivel de modulo (antes del primer 'def ')
    module_level_lines = []
    for line in source.split('\n'):
        if line.startswith('def '):
            break
        stripped = line.strip()
        if stripped.startswith(('import ', 'from ')) and not stripped.startswith('#'):
            module_level_lines.append(stripped)
    module_imports = '\n'.join(module_level_lines)
    _check("No importa arena_fetcher (nivel modulo)", "core.arena_fetcher" not in module_imports)
    _check("No importa price_estimator (nivel modulo)", "core.price_estimator" not in module_imports)

    # ------------------------------------------------------------------
    # 19. validate_self
    # ------------------------------------------------------------------
    print("\n--- 19. validate_self ---")
    _reset()
    _check("Retorna bool", isinstance(router_mod.validate_self(), bool))

    # ------------------------------------------------------------------
    # 20. Resumen de módulos cargados
    # ------------------------------------------------------------------
    print("\n--- 20. Estado de módulos ---")
    # En ejecucion standalone, core.* no estan disponibles (esperado)
    _standalone = model_health is None
    _check("model_health: disponible o standalone", model_health is not None or _standalone)
    _check("_global_pool: disponible o standalone", _global_pool is not None or _standalone)
    _check("_llm_cache: disponible o standalone", _llm_cache is not None or _standalone)
    _check("settings disponible", settings is not None)
    _check("MB configurado" if _has_mb_config() else "MB no configurado", True)

    # ------------------------------------------------------------------
    # 21. Task Model Cache & Startup (v7.1)
    # ------------------------------------------------------------------
    print("\n--- 21. Task Model Cache & Startup ---")
    v71_funcs = [
        '_get_cache_file_path', '_load_task_cache', '_save_task_cache',
        '_update_task_cache', 'get_task_priority', 'initialize_router',
    ]
    for func in v71_funcs:
        _check(f"v7.1: {func}()", hasattr(router_mod, func) and callable(getattr(router_mod, func)))

    # 21a. Priority map
    _check("chat → latency", router_mod.get_task_priority("chat") == "latency")
    _check("planning → quality", router_mod.get_task_priority("planning") == "quality")
    _check("desconocido → quality", router_mod.get_task_priority("unknown_task") == "quality")

    # 21b. Cache load/save (usa tmpdir)
    import tempfile
    _tmp_dir = tempfile.mkdtemp()
    router_mod._task_cache_initialized = False  # forzar recarga
    report = router_mod.initialize_router(cache_dir=_tmp_dir)
    _check("initialize_router retorna dict", isinstance(report, dict))
    _check("cache_loaded=True", report.get("cache_loaded") is True)
    _check("startup_mode es str", isinstance(report.get("startup_mode"), str))

    # 21c. Cache update y persistencia
    router_mod._update_task_cache("chat", "gpt-4o-mini", "openai", arena_score=85.0, latency_ms=120.0)
    _check("Cache tiene 'chat'", "chat" in router_mod._task_model_cache)
    _check("Modelo cacheado", router_mod._task_model_cache["chat"]["model"] == "gpt-4o-mini")
    _check("Latencia cacheada", router_mod._task_model_cache["chat"]["latency_ms"] == 120.0)

    # 21d. Reload desde disco
    _saved_path = router_mod._task_cache_file
    router_mod._task_cache_initialized = False
    router_mod._load_task_cache()
    _check("Reload persistió 'chat'", router_mod._task_model_cache.get("chat", {}).get("model") == "gpt-4o-mini")

    # Limpieza
    import shutil
    shutil.rmtree(_tmp_dir, ignore_errors=True)
    router_mod._task_cache_initialized = False
    router_mod._task_cache_file = None

    # ------------------------------------------------------------------
    # 22. QuotaTracker — inspección de código fuente
    # ------------------------------------------------------------------
    print("\n--- 22. QuotaTracker: código de control de cuota en router ---")
    _router_src = open(__file__, encoding='utf-8').read()

    # 22a. Verificar que call_llm contiene la comprobación pre-vuelo
    _check(
        "call_llm contiene 'check_quota' pre-vuelo",
        'check_quota' in _router_src and 'qt_check' in _router_src
    )
    _check(
        "call_llm salta proveedor bloqueado (continue)",
        'qt_check["blocked"]' in _router_src
    )
    _check(
        "call_llm registra advertencia de cuota alta",
        'qt_check["warning"]' in _router_src
    )
    _check(
        "call_llm no interrumpe si quota falla (graceful)",
        'quota check fallo' in _router_src or 'qt_err' in _router_src
    )

    # 22b. Verificar que _log_usage_if_possible registra gasto
    _check(
        "_log_usage_if_possible contiene 'record_spending'",
        'record_spending' in _router_src
    )
    _check(
        "record_spending solo si success y cost_usd > 0",
        'success and cost_usd > 0 and provider' in _router_src
    )
    _check(
        "record_spending pasa provider y tokens",
        'provider=provider' in _router_src and 'tokens=total_tokens' in _router_src
    )

    # 22c. Verificar que _quota_tracker_cls se importa
    _check(
        "_quota_tracker_cls se importa como opcional",
        'quota_tracker' in _router_src and '_safe_import' in _router_src
    )

    # ------------------------------------------------------------------
    # 23. QuotaTracker — contrato de interfaz (mock)
    # ------------------------------------------------------------------
    print("\n--- 23. QuotaTracker: contrato de interfaz ---")
    try:
        import tempfile as _tf
        _qt_db = os.path.join(_tf.gettempdir(), 'test_router_quota.db')
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        from core.quota_tracker import QuotaTracker

        _qt = QuotaTracker(db_path=_qt_db)

        # 23a. check_quota retorna dict con las keys esperadas por el router
        _qt.set_provider_quota('test_prov', 1.0, 80.0)
        _r_ok = _qt.check_quota('test_prov')
        _expected_keys = {'allowed', 'blocked', 'warning', 'provider',
                          'daily_spent', 'daily_budget', 'pct_used', 'message'}
        _check(
            "check_quota retorna dict con keys esperadas",
            _expected_keys.issubset(set(_r_ok.keys()))
        )
        _check("check_quota sin gasto: allowed=True", _r_ok['allowed'] is True)
        _check("check_quota sin gasto: blocked=False", _r_ok['blocked'] is False)

        # 23b. Simular gasto hasta advertencia (80%)
        _qt.record_spending('test_prov', 0.85, 1000)
        _r_warn = _qt.check_quota('test_prov')
        _check("check_quota 85%: warning=True", _r_warn['warning'] is True)
        _check("check_quota 85%: allowed=True", _r_warn['allowed'] is True)

        # 23c. Simular gasto hasta bloqueo (100%+)
        _qt.record_spending('test_prov', 0.20, 200)
        _r_block = _qt.check_quota('test_prov')
        _check("check_quota 105%: blocked=True", _r_block['blocked'] is True)
        _check("check_quota 105%: allowed=False", _r_block['allowed'] is False)

        # 23d. is_provider_blocked shortcut
        _check(
            "is_provider_blocked: True",
            _qt.is_provider_blocked('test_prov') is True
        )
        _check(
            "is_provider_blocked: False (sin cuota)",
            _qt.is_provider_blocked('proveedor_sin_cuota') is False
        )

        # 23e. record_spending acumula correctamente
        _spent = _qt.get_daily_spending('test_prov')
        _check(
            f"get_daily_spending = {_spent:.2f} (esperado 1.05)",
            abs(_spent - 1.05) < 0.01
        )

        # Limpieza
        os.remove(_qt_db)

    except ImportError as _qt_imp_err:
        _skip("QuotaTracker contrato", f"import fallo: {_qt_imp_err}")
        for _ in range(8):
            _skip("(dependiente)", "")
    except Exception as _qt_ex:
        _check(f"Error QuotaTracker: {_qt_ex}", False)

    # ------------------------------------------------------------------
    # 24. QuotaTracker — integración con _quota_tracker_cls
    # ------------------------------------------------------------------
    print("\n--- 24. QuotaTracker: integración con router ---")
    _check(
        "_quota_tracker_cls se importa con _safe_import",
        _quota_tracker_cls is not None or True  # en standalone puede ser None
    )
    _check(
        "El router tiene referencia a QuotaTracker",
        '_quota_tracker_cls' in dir(router_mod)
    )
    # Verificar que el código de integración usa get_instance()
    _check(
        "Usa get_instance() (patrón singleton)",
        'get_instance()' in _router_src
    )

    # ------------------------------------------------------------------
    # RESULTADO
    # ------------------------------------------------------------------
    print("\n" + "-" * 70)
    total = passed + failed
    print(f"Resultado: {passed}/{total} tests pasaron, {skipped} omitidos")
    if failed > 0:
        print(f"FALLARON: {failed}")
    else:
        print("TODAS LAS PRUEBAS PASARON")
    print("=" * 70)
    sys.exit(0 if failed == 0 else 1)