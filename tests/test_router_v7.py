# test_router_v7.py
# 7 escenarios de test para router_v7.py (desplegado como apa/core/router.py)
#
# USO:  python apa/tests/test_router_v7.py
#
# Los tests mockean ModelBroker para no depender de la instalacion real.
# Importa desde apa.core.router (import estandar del paquete).
#
# IMPORTANTE: Este fichero se despliega como apa/tests/test_router_v7.py
# y se ejecuta directamente. Por eso agrega el project root a sys.path.

import sys
import os
import types
import tempfile
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

# ============================================================================
# 1) Agregar project root a sys.path (para ejecucion directa)
# ============================================================================
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ============================================================================
# 2) Inyectar mocks en sys.modules ANTES de importar apa.core.router
#    Esto controla las dependencias que router.py importa al cargar.
# ============================================================================

# --- Mock de apa.config.settings ---
_settings_mod = types.ModuleType("apa.config.settings")


class _MockSettings:
    model_broker_url = "http://localhost:8100"
    model_broker_api_key = ""
    log_level = "INFO"
    ollama_base_url = ""
    usage_db_path = ""


    def get_emergency_keys(self):
        return {}

    def has_emergency_keys(self):
        return False


_settings_mod.settings = _MockSettings()

# --- Mock de apa.core.llm_cache ---
_cache_mod = types.ModuleType("apa.core.llm_cache")


class _MockCache:
    def __init__(self, **kwargs):
        self._store = {}

    def get(self, prompt, model, **params):
        key = (prompt, model, tuple(sorted(params.items())))
        return self._store.get(key)

    def set(self, prompt, model, response, **params):
        key = (prompt, model, tuple(sorted(params.items())))
        self._store[key] = response


_cache_mod.LLMCache = _MockCache

# --- Mock de apa.core.notifications ---
_notif_mod = types.ModuleType("apa.core.notifications")


def _mock_notify(event_type, message, data=None):
    pass


_notif_mod.notify = _mock_notify

# --- Mock de apa.core.usage_tracker ---
_tracker_mod = types.ModuleType("apa.core.usage_tracker")

# --- Inyectar solo los submodulos hoja en sys.modules ---
# NO mockear 'apa' ni 'apa.core' ni 'apa.config' como paquetes.
# Si los mockeamos con types.ModuleType (sin __path__), Python
# no los reconoce como paquetes y no puede importar submodulos.
# Al dejarlos fuera, Python los encuentra como paquetes reales en
# disco (gracias al project root en sys.path), y los submodulos
# mockeados se usan directamente desde sys.modules.
sys.modules["apa.config.settings"] = _settings_mod
sys.modules["apa.core.llm_cache"] = _cache_mod
sys.modules["apa.core.notifications"] = _notif_mod
sys.modules["apa.core.usage_tracker"] = _tracker_mod

# ============================================================================
# 3) Importar el router (usara los mocks que acabamos de inyectar)
# ============================================================================
import apa.core.router as router

# ============================================================================
# 4) Setup para tests: crear UsageTracker mock con DB temporal
# ============================================================================
_temp_dir = tempfile.mkdtemp()
_test_db = Path(_temp_dir) / "test_usage.db"


def _setup_usage_tracker():
    """Crea un UsageTracker mock con DB temporal y lo inyecta en router."""
    # Crear tabla manualmente en DB temporal
    conn = sqlite3.connect(str(_test_db))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL,
            model TEXT NOT NULL,
            tokens INTEGER NOT NULL DEFAULT 0,
            request_type TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            provider TEXT DEFAULT '',
            tokens_input INTEGER DEFAULT 0,
            tokens_output INTEGER DEFAULT 0,
            latency_ms INTEGER DEFAULT 0,
            cost_usd REAL DEFAULT 0.0,
            arena_score REAL DEFAULT NULL,
            success INTEGER DEFAULT 1,
            error_type TEXT DEFAULT ''
        )
    """)

    # Insertar un registro de ultimo modelo que funciono
    conn.execute(
        "INSERT INTO usage (project_id, model, tokens, request_type, "
        "timestamp, provider, tokens_input, tokens_output, latency_ms, "
        "cost_usd, success) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("test_proj", "openai/gpt-4o-mini", 500, "chat",
         "2026-07-08T12:00:00", "openrouter", 300, 200, 800,
         0.01, 1)
    )
    conn.commit()
    conn.close()

    # Crear mock de UsageTracker
    mock_tracker = MagicMock()
    mock_tracker.db_path = _test_db
    mock_tracker.log_usage = MagicMock()
    mock_tracker.get_column_names = MagicMock(return_value=[
        "id", "project_id", "model", "tokens", "request_type", "timestamp",
        "provider", "tokens_input", "tokens_output", "latency_ms",
        "cost_usd", "arena_score", "success", "error_type",
    ])

    # Inyectar el mock en sys.modules para que los imports internos
    # del router (from apa.core.usage_tracker import UsageTracker)
    # usen nuestro mock
    _tracker_mod.UsageTracker = lambda: mock_tracker

    return mock_tracker


# ============================================================================
# TESTS — 7 escenarios
# ============================================================================
passed = 0
failed = 0


def _run_test(name, fn):
    global passed, failed
    print(f"\n[Test] {name}")
    try:
        fn()
        print(f"  OK — {name}")
        passed += 1
    except AssertionError as e:
        print(f"  FAIL — {name}: {e}")
        failed += 1
    except Exception as e:
        print(f"  ERROR — {name}: {type(e).__name__}: {e}")
        failed += 1


# --- Test 1: call_llm con MB disponible ---
def test_call_llm_mb_available():
    """call_llm con MB disponible retorna resultado exitoso."""
    mock_broker = MagicMock()
    mock_broker.call.return_value = {
        "success": True,
        "content": "Respuesta del modelo",
        "model_used": "anthropic/claude-sonnet-4",
        "provider": "anthropic",
        "tokens_input": 100,
        "tokens_output": 50,
        "cost_usd": 0.005,
        "latency_ms": 500,
        "arena_score": 88.5,
        "error": "",
    }

    # Patchear el modulo router
    original_mb = router.ModelBroker
    original_available = router._MB_AVAILABLE
    router.ModelBroker = lambda: mock_broker
    router._MB_AVAILABLE = True

    # Limpiar cache para test limpio
    router._llm_cache._store.clear()

    mock_tracker = _setup_usage_tracker()

    result = router.call_llm(
        task_type="planning",
        system_prompt="Eres un asistente.",
        user_prompt="Hola",
        max_tokens=100,
        temperature=0.1,
        project_id="test_proj",
    )

    # Restaurar
    router.ModelBroker = original_mb
    router._MB_AVAILABLE = original_available

    assert result["success"] is True, f"Esperado success=True: {result}"
    assert result["content"] == "Respuesta del modelo"
    assert result["model_used"] == "anthropic/claude-sonnet-4"
    assert result["provider"] == "anthropic"
    assert result["attempts"] == 1
    assert result.get("emergency_mode") is not True


# --- Test 2: call_llm con MB caido -> emergency ---
def test_call_llm_mb_down_emergency():
    """call_llm con MB caido activa emergency harness."""
    import requests as _req

    def _raise_connection_error(**kwargs):
        raise _req.exceptions.ConnectionError("Connection refused")

    mock_broker = MagicMock()
    mock_broker.call.side_effect = _raise_connection_error

    original_mb = router.ModelBroker
    original_available = router._MB_AVAILABLE
    router.ModelBroker = lambda: mock_broker
    router._MB_AVAILABLE = True

    # Sin emergency keys ni Ollama -> debe fallar graceful
    mock_tracker = _setup_usage_tracker()

    result = router.call_llm(
        task_type="chat",
        system_prompt="Eres un asistente.",
        user_prompt="Hola",
        project_id="test_proj",
    )

    router.ModelBroker = original_mb
    router._MB_AVAILABLE = original_available

    # Sin emergency keys ni Ollama, debe retornar error controlado
    assert result["success"] is False, f"Esperado success=False: {result}"
    assert result.get("emergency_mode") is True, (
        f"Esperado emergency_mode=True: {result}"
    )
    assert "no_provider" in result.get("error_type", ""), (
        f"Esperado error_type='no_provider': {result.get('error_type')}"
    )


# --- Test 3: planning falla -> desescala a chat ---
def test_planning_fails_descale_to_chat():
    """Si planning falla, se reintenta con task_type='chat'."""
    call_count = {"n": 0}

    def _mock_call(**kwargs):
        call_count["n"] += 1
        task = kwargs.get("task_type", "")
        if task == "planning":
            return {
                "success": False,
                "content": "",
                "model_used": "some/model",
                "provider": "test",
                "tokens_input": 0,
                "tokens_output": 0,
                "cost_usd": 0.0,
                "latency_ms": 100,
                "arena_score": None,
                "error": "Model overloaded",
            }
        elif task == "chat":
            return {
                "success": True,
                "content": "Respuesta desescalada",
                "model_used": "other/model",
                "provider": "test",
                "tokens_input": 50,
                "tokens_output": 25,
                "cost_usd": 0.001,
                "latency_ms": 200,
                "arena_score": 70.0,
                "error": "",
            }
        return {"success": False, "error": "unknown"}

    mock_broker = MagicMock()
    mock_broker.call.side_effect = _mock_call

    original_mb = router.ModelBroker
    original_available = router._MB_AVAILABLE
    router.ModelBroker = lambda: mock_broker
    router._MB_AVAILABLE = True

    mock_tracker = _setup_usage_tracker()

    result = router.call_llm(
        task_type="planning",
        system_prompt="Planifica esto.",
        user_prompt="Crea un plan",
        project_id="test_proj",
    )

    router.ModelBroker = original_mb
    router._MB_AVAILABLE = original_available

    assert result["success"] is True, f"Desescalado fallo: {result}"
    assert result["content"] == "Respuesta desescalada"
    assert result["attempts"] == 2, f"Esperados 2 intentos: {result['attempts']}"
    assert result.get("descaled_from") == "planning", (
        f"Esperado descaled_from='planning': {result.get('descaled_from')}"
    )
    assert call_count["n"] == 2, (
        f"Esperadas 2 llamadas a broker: {call_count['n']}"
    )


# --- Test 4: cache hit on second call ---
def test_cache_hit_second_call():
    """Segunda llamada identica retorna cache (sin llamar a MB)."""
    call_count = {"n": 0}

    def _mock_call(**kwargs):
        call_count["n"] += 1
        return {
            "success": True,
            "content": "Cached response",
            "model_used": "test/model",
            "provider": "test",
            "tokens_input": 10,
            "tokens_output": 5,
            "cost_usd": 0.001,
            "latency_ms": 100,
            "arena_score": 80.0,
            "error": "",
        }

    mock_broker = MagicMock()
    mock_broker.call.side_effect = _mock_call

    original_mb = router.ModelBroker
    original_available = router._MB_AVAILABLE
    router.ModelBroker = lambda: mock_broker
    router._MB_AVAILABLE = True

    # Limpiar cache para test limpio
    router._llm_cache._store.clear()

    mock_tracker = _setup_usage_tracker()

    # Primera llamada — cache MISS
    r1 = router.call_llm(
        task_type="chat",
        system_prompt="Sys",
        user_prompt="Hello cache",
        max_tokens=50,
        temperature=0.1,
        project_id="test_proj",
    )

    # Segunda llamada identica — cache HIT
    r2 = router.call_llm(
        task_type="chat",
        system_prompt="Sys",
        user_prompt="Hello cache",
        max_tokens=50,
        temperature=0.1,
        project_id="test_proj",
    )

    router.ModelBroker = original_mb
    router._MB_AVAILABLE = original_available

    assert r1["success"] is True
    assert r2["success"] is True
    assert call_count["n"] == 1, (
        f"Esperada 1 llamada a MB (cache hit en 2da): {call_count['n']}"
    )


# --- Test 5: escalate_model returns better model ---
def test_escalate_model():
    """escalate_model retorna un modelo mejor del ranking de MB."""
    mock_broker = MagicMock()
    mock_broker.get_models.return_value = [
        {"id": "anthropic/claude-opus-4", "score": 95},
        {"id": "anthropic/claude-sonnet-4", "score": 88},
        {"id": "openai/gpt-4o", "score": 82},
        {"id": "openai/gpt-4o-mini", "score": 70},
    ]

    original_mb = router.ModelBroker
    original_available = router._MB_AVAILABLE
    router.ModelBroker = lambda: mock_broker
    router._MB_AVAILABLE = True

    result = router.escalate_model("openai/gpt-4o")

    assert result == "anthropic/claude-sonnet-4", (
        f"Esperado claude-sonnet-4, got {result}"
    )

    # Si ya es el mejor, retorna el mismo
    result_top = router.escalate_model("anthropic/claude-opus-4")
    assert result_top == "anthropic/claude-opus-4", (
        f"Esperado claude-opus-4 (ya es el mejor), got {result_top}"
    )

    # Si no esta en la lista, retorna el mismo
    result_unknown = router.escalate_model("unknown/model")
    assert result_unknown == "unknown/model", (
        f"Esperado unknown/model (no encontrado), got {result_unknown}"
    )

    router.ModelBroker = original_mb
    router._MB_AVAILABLE = original_available


# --- Test 6: UsageTracker records call ---
def test_usage_tracker_records():
    """Las llamadas exitosas se registran en UsageTracker."""
    mock_broker = MagicMock()
    mock_broker.call.return_value = {
        "success": True,
        "content": "Test response",
        "model_used": "test/model",
        "provider": "test_provider",
        "tokens_input": 200,
        "tokens_output": 100,
        "cost_usd": 0.01,
        "latency_ms": 300,
        "arena_score": 85.0,
        "error": "",
    }

    mock_tracker = _setup_usage_tracker()

    original_mb = router.ModelBroker
    original_available = router._MB_AVAILABLE
    router.ModelBroker = lambda: mock_broker
    router._MB_AVAILABLE = True

    router.call_llm(
        task_type="coding",
        system_prompt="Code expert",
        user_prompt="Write a function",
        project_id="tracker_test",
    )

    router.ModelBroker = original_mb
    router._MB_AVAILABLE = original_available

    # Verificar que log_usage fue llamado
    mock_tracker.log_usage.assert_called_once()
    call_kwargs = mock_tracker.log_usage.call_args[1]
    assert call_kwargs["project_id"] == "tracker_test", (
        f"project_id incorrecto: {call_kwargs.get('project_id')}"
    )
    assert call_kwargs["model"] == "test/model", (
        f"model incorrecto: {call_kwargs.get('model')}"
    )
    assert call_kwargs["provider"] == "test_provider", (
        f"provider incorrecto: {call_kwargs.get('provider')}"
    )
    assert call_kwargs["success"] is True, (
        f"success incorrecto: {call_kwargs.get('success')}"
    )
    assert call_kwargs["tokens_input"] == 200, (
        f"tokens_input incorrecto: {call_kwargs.get('tokens_input')}"
    )
    assert call_kwargs["tokens_output"] == 100, (
        f"tokens_output incorrecto: {call_kwargs.get('tokens_output')}"
    )


# --- Test 7: validate_self() passes ---
def test_validate_self():
    """validate_self() retorna True cuando hay MB o emergency keys."""
    # Con MB mock que responde
    mock_broker = MagicMock()
    mock_broker.get_models.return_value = [
        {"id": "model-1"}, {"id": "model-2"},
    ]

    mock_tracker = _setup_usage_tracker()

    original_mb = router.ModelBroker
    original_available = router._MB_AVAILABLE
    router.ModelBroker = lambda: mock_broker
    router._MB_AVAILABLE = True

    result = router.validate_self()

    router.ModelBroker = original_mb
    router._MB_AVAILABLE = original_available

    assert result is True, f"validate_self() deberia retornar True: {result}"

    # Sin MB, sin emergency keys, sin Ollama -> tambien True
    # (validate_self no hace hard fail, solo warnings)
    router._MB_AVAILABLE = False
    result2 = router.validate_self()
    router._MB_AVAILABLE = original_available

    assert result2 is True, (
        f"validate_self() sin MB deberia retornar True: {result2}"
    )


# ============================================================================
# Ejecutar todos los tests
# ============================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("TESTS — router_v7.py (7 escenarios)")
    print("=" * 60)
    print(f"Project root: {_PROJECT_ROOT}")
    print(f"Router module: {router.__file__}")

    _run_test(
        "1. call_llm con MB disponible",
        test_call_llm_mb_available,
    )
    _run_test(
        "2. call_llm con MB caido -> emergency",
        test_call_llm_mb_down_emergency,
    )
    _run_test(
        "3. planning falla -> desescala a chat",
        test_planning_fails_descale_to_chat,
    )
    _run_test(
        "4. cache hit on second call",
        test_cache_hit_second_call,
    )
    _run_test(
        "5. escalate_model returns better model",
        test_escalate_model,
    )
    _run_test(
        "6. UsageTracker records call",
        test_usage_tracker_records,
    )
    _run_test(
        "7. validate_self() passes",
        test_validate_self,
    )

    # Cleanup
    try:
        import shutil
        shutil.rmtree(_temp_dir, ignore_errors=True)
    except Exception:
        pass

    print("\n" + "=" * 60)
    print(
        f"RESULTADO: {passed} PASSED, {failed} FAILED "
        f"(de {passed + failed} tests)"
    )
    if failed == 0:
        print("VALIDACION COMPLETADA — router_v7.py OK")
    else:
        print("HAY TESTS FALLIDOS — revisar arriba")
    print("=" * 60)

    sys.exit(0 if failed == 0 else 1)