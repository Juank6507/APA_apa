#!/usr/bin/env python3
"""
test_integracion.py — Validación de integración standalone del router v7.1.

Ubicación: apa/tests/test_integracion.py
Ejecución:  python apa/tests/test_integracion.py
             o:  python -m pytest apa/tests/test_integracion.py -v

Carga router.py directamente (sin estructura APA) para validar:
  1. Las 49 funciones esperadas por test_arnes_emergencia.py existen
  2. El arnés de emergencia funciona end-to-end SIN Model Broker
  3. initialize_router() funciona en modo standalone
  4. Los None guards (_llm_cache, _global_pool) no generan errores
  5. Mapa de descalado, imports limpios, funciones v7.1
"""

import sys
import os
import time
import types
import logging
import importlib.util
import inspect
import tempfile
import shutil

logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s')

# ============================================================================
# SETUP: Cargar router.py directamente (sin estructura APA)
# ============================================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# Resolver ruta del router: en APA es ../core/router.py, en /download/ es router_v7.py
_ROUTER_CANDIDATES = [
    os.path.join(SCRIPT_DIR, '..', 'core', 'router.py'),
    os.path.join(SCRIPT_DIR, 'router_v7.py'),
]
ROUTER_PATH = None
for _candidate in _ROUTER_CANDIDATES:
    if os.path.isfile(_candidate):
        ROUTER_PATH = _candidate
        break
if ROUTER_PATH is None:
    raise FileNotFoundError(
        f"No se encontró router.py en ninguno de: {_ROUTER_CANDIDATES}"
    )

# Mocks necesarios para que el router cargue en modo standalone
_core_mock = types.ModuleType('core')
_core_mock.__path__ = []
sys.modules['core'] = _core_mock

_core_settings_mock = types.ModuleType('core.settings')
sys.modules['core.settings'] = _core_settings_mock

class _MockSettings:
    model_broker_url = ''
    ollama_base_url = 'http://localhost:11434'
    max_retries = 3
    default_max_tokens = 2000
    default_temperature = 0.1
    cache_dir = None

sys.modules['config'] = types.ModuleType('config')
sys.modules['config.settings'] = types.ModuleType('config.settings')
sys.modules['config.settings'].settings = _MockSettings()

# Mock model_broker para que el import no falle
_mb_mock = types.ModuleType('model_broker')
_mb_mock.__path__ = []
sys.modules['model_broker'] = _mb_mock
_mb_broker_mock = types.ModuleType('model_broker.broker')
sys.modules['model_broker.broker'] = _mb_broker_mock

# Cargar router directamente desde el archivo
spec = importlib.util.spec_from_file_location("router_standalone", ROUTER_PATH)
router = importlib.util.module_from_spec(spec)
sys.modules['router_standalone'] = router
spec.loader.exec_module(router)

# Alias
R = router


# ============================================================================
# HELPERS
# ============================================================================

def _reset():
    """Limpia el estado del broker entre tests."""
    R._broker_instance = None
    R._broker_available = None
    R._last_emergency_notify_time = 0.0


# ============================================================================
# GRUPO A: Las 49 funciones esperadas existen y son callable
# ============================================================================

def test_funciones_v66():
    """Verifica las 34 funciones de v6.6."""
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
    for func_name in v66_funcs:
        assert hasattr(R, func_name) and callable(getattr(R, func_name)), \
            f"v6.6: {func_name}() falta o no es callable"


def test_funciones_arnes():
    """Verifica las 9 funciones del arnés de emergencia."""
    arnes_funcs = [
        '_has_mb_config', '_get_broker', 'reset_broker_status',
        '_notify_emergency_to_user', '_try_bootstrap_mb',
        '_find_ollama_model', '_find_last_working_model',
        '_emergency_call', '_run_emergency_harness',
    ]
    for func_name in arnes_funcs:
        assert hasattr(R, func_name) and callable(getattr(R, func_name)), \
            f"Arnés: {func_name}() falta o no es callable"


def test_funciones_v71():
    """Verifica las 6 funciones de v7.1."""
    v71_funcs = [
        '_get_cache_file_path', '_load_task_cache', '_save_task_cache',
        '_update_task_cache', 'get_task_priority', 'initialize_router',
    ]
    for func_name in v71_funcs:
        assert hasattr(R, func_name) and callable(getattr(R, func_name)), \
            f"v7.1: {func_name}() falta o no es callable"


# ============================================================================
# GRUPO B: Arnés de emergencia SIN MB — end-to-end
# ============================================================================

def test_arnes_sin_mb_has_config():
    """Sin URL de MB, _has_mb_config() retorna False."""
    _reset()
    R.settings.model_broker_url = ''
    assert R._has_mb_config() is False, "_has_mb_config() sin URL debe ser False"


def test_arnes_sin_mb_get_broker_none():
    """Sin URL de MB, _get_broker() retorna None."""
    _reset()
    R.settings.model_broker_url = ''
    assert R._get_broker() is None, "_get_broker() sin URL debe ser None"


def test_arnes_con_mb_config():
    """Con URL de MB, _has_mb_config() retorna True."""
    _reset()
    R.settings.model_broker_url = 'http://localhost:8000'
    try:
        assert R._has_mb_config() is True, "_has_mb_config() con URL debe ser True"
    finally:
        R.settings.model_broker_url = ''


def test_arnes_reset_broker():
    """reset_broker_status() limpia cache negativo."""
    _reset()
    R.settings.model_broker_url = 'http://localhost:8000'
    R._broker_available = False
    R.reset_broker_status()
    assert R._broker_available is None, "reset debe poner _broker_available a None"
    broker = R._get_broker()
    assert broker is not None, "tras reset, _get_broker() debe retornar objeto"
    R.settings.model_broker_url = ''


def test_arnes_notify_no_explota():
    """_notify_emergency_to_user() no lanza excepción."""
    _reset()
    R._notify_emergency_to_user('test de notificación')


def test_arnes_notify_throttle():
    """_notify_emergency_to_user() respeta throttle (no explota)."""
    _reset()
    R._last_emergency_notify_time = time.time()
    R._notify_emergency_to_user('throttled')


def test_arnes_find_ollama_model():
    """_find_ollama_model() retorna un modelo (fallback o real de Ollama)."""
    _reset()
    model = R._find_ollama_model()
    assert isinstance(model, str) and len(model) > 0, "debe retornar string no vacío"
    # Si Ollama corre, retorna el primer modelo disponible;
    # si no, retorna el fallback 'llama3.1'
    assert ':' in model or model == 'llama3.1', \
        f"debe ser modelo válido, got '{model}'"


def test_arnes_emergency_call_structure():
    """_emergency_call() retorna dict con estructura correcta (con o sin Ollama)."""
    _reset()
    result = R._emergency_call(system_prompt='sys', user_prompt='hello')
    # Keys que siempre deben estar presentes
    always_keys = {'success', 'via_emergency', 'provider', 'model_used',
                   'content', 'attempts', 'latency_ms', 'cost_usd',
                   'tokens_input', 'tokens_output', 'arena_score'}
    assert isinstance(result, dict), "debe retornar dict"
    assert always_keys.issubset(result.keys()), f"faltan keys: {always_keys - result.keys()}"
    assert result.get('via_emergency') is True, "via_emergency debe ser True"
    assert result.get('provider') == 'ollama_local', "provider debe ser ollama_local"
    # Adapta la validación según si Ollama respondió o no
    if result.get('success'):
        # Ollama corriendo: debe tener contenido
        assert isinstance(result.get('content'), str), "content debe ser string"
    else:
        # Ollama no disponible: debe tener error
        assert 'error' in result, "sin éxito debe tener 'error'"
        assert 'Ollama' in (result.get('error') or ''), "error debe mencionar Ollama"


def test_arnes_emergency_call_no_openrouter():
    """_emergency_call() no menciona OpenRouter en su código fuente."""
    src = inspect.getsource(R._emergency_call)
    assert 'openrouter' not in src.lower(), "_emergency_call no debe mencionar openrouter"


def test_arnes_run_harness_structure():
    """_run_emergency_harness() retorna dict con keys requeridos."""
    _reset()
    R.settings.model_broker_url = 'http://localhost:8000'
    try:
        result = R._run_emergency_harness(
            task_type='chat', system_prompt='sys', user_prompt='hi',
            max_tokens=100, temperature=0.7, call_start_time=time.time(),
        )
        assert isinstance(result, dict), "debe retornar dict"
        assert 'success' in result, "debe tener 'success'"
        assert 'via_emergency' in result, "debe tener 'via_emergency'"
    finally:
        R.settings.model_broker_url = ''


def test_arnes_try_bootstrap_sin_modelos():
    """_try_bootstrap_mb() retorna False sin modelos disponibles."""
    _reset()
    R.settings.model_broker_url = 'http://localhost:8000'
    try:
        result = R._try_bootstrap_mb()
        assert result is False, "sin modelos debe retornar False"
    finally:
        R.settings.model_broker_url = ''


# ============================================================================
# GRUPO C: call_llm() SIN MB — flujo completo fallback
# ============================================================================

def test_call_llm_sin_mb():
    """call_llm() sin MB configurado no explota (cae a capa 3)."""
    _reset()
    R.settings.model_broker_url = ''
    result = R.call_llm(
        task_type='chat', system_prompt='sys', user_prompt='hi',
        max_tokens=50, temperature=0.1,
    )
    assert isinstance(result, dict), "debe retornar dict"
    assert 'success' in result, "debe tener 'success'"
    assert result.get('success') is False, "sin pool debe ser success=False"


def test_call_llm_none_guard_cache():
    """call_llm() no explota cuando _llm_cache es None."""
    _reset()
    R.settings.model_broker_url = ''
    original_cache = getattr(R, '_llm_cache', 'SENTINEL')
    R._llm_cache = None
    try:
        result = R.call_llm(
            task_type='chat', system_prompt='sys', user_prompt='hi',
            max_tokens=50, temperature=0.1,
        )
        assert isinstance(result, dict), "con cache=None debe retornar dict"
    finally:
        if original_cache != 'SENTINEL':
            R._llm_cache = original_cache


def test_call_llm_none_guard_pool():
    """get_scaling_state() no explota cuando _global_pool es None."""
    _reset()
    original_pool = R._global_pool
    R._global_pool = None
    try:
        state = R.get_scaling_state()
        assert isinstance(state, dict), "debe retornar dict"
        assert state.get('pool_size') == 0, "pool_size debe ser 0"
        assert state.get('broker_configured') is False, "broker_configured debe ser False"
    finally:
        R._global_pool = original_pool


# ============================================================================
# GRUPO D: initialize_router() en modo standalone (SIN MB)
# ============================================================================

def test_initialize_router_standalone():
    """initialize_router() funciona en modo standalone sin MB."""
    _reset()
    R.settings.model_broker_url = ''
    R._task_cache_initialized = False
    R._task_cache_file = None

    tmpdir = tempfile.mkdtemp()
    try:
        report = R.initialize_router(cache_dir=tmpdir)
        assert isinstance(report, dict), "debe retornar dict"
        assert report.get('cache_loaded') is True, "cache_loaded debe ser True"
        assert isinstance(report.get('startup_mode'), str), "startup_mode debe ser str"
        assert report.get('startup_mode') == 'standalone', "sin MB debe ser standalone"
        assert report.get('mb_validated') is False, "sin MB no debe validar"
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
        R._task_cache_initialized = False
        R._task_cache_file = None


def test_initialize_router_cache_persist():
    """El cache de tarea persiste entre inicializaciones."""
    _reset()
    R.settings.model_broker_url = ''
    R._task_cache_initialized = False
    R._task_cache_file = None

    tmpdir = tempfile.mkdtemp()
    try:
        R.initialize_router(cache_dir=tmpdir)
        R._update_task_cache(
            task_type='chat', model='test-model', provider='test-provider',
            arena_score=85.0, latency_ms=200,
        )
        R._save_task_cache()

        R._task_cache_initialized = False
        R._task_cache_file = None
        R._task_model_cache = {}
        R.initialize_router(cache_dir=tmpdir)

        assert 'chat' in R._task_model_cache, "cache debe persistir tipo 'chat'"
        assert R._task_model_cache.get('chat', {}).get('model') == 'test-model', \
            "modelo cacheado debe persistir"
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
        R._task_cache_initialized = False
        R._task_cache_file = None


# ============================================================================
# GRUPO E: Mapa de descalado y get_scaling_state
# ============================================================================

def test_descale_map():
    """Verifica el mapa de descalado silencioso."""
    assert R._DESCALE_MAP.get('planning') == 'generation', "planning → generation"
    assert R._DESCALE_MAP.get('spec_generation') == 'generation', "spec → generation"
    assert R._DESCALE_MAP.get('chat') is None, "chat no descala"
    assert R._DESCALE_MAP.get('generation') == 'coding', "generation → coding"


def test_get_scaling_state_structure():
    """get_scaling_state() retorna dict con las keys esperadas."""
    _reset()
    state = R.get_scaling_state()
    expected_keys = {'current_model', 'current_task_type', 'emergency_active',
                     'broker_available', 'broker_configured', 'pool_size',
                     'descale_map'}
    assert expected_keys.issubset(state.keys()), f"faltan keys: {expected_keys - state.keys()}"
    assert isinstance(state.get('emergency_active'), bool), "emergency_active debe ser bool"


def test_validate_self_retorna_bool():
    """validate_self() retorna un booleano."""
    _reset()
    assert isinstance(R.validate_self(), bool), "debe retornar bool"


# ============================================================================
# GRUPO F: Imports limpios (sin inline core.X)
# ============================================================================

def test_imports_limpios():
    """No hay imports de core.arena_fetcher ni core.price_estimator a nivel módulo."""
    with open(ROUTER_PATH, encoding='utf-8') as f:
        source = f.read()

    module_imports = []
    for line in source.split('\n'):
        if line.startswith('def '):
            break
        stripped = line.strip()
        if stripped.startswith(('import ', 'from ')) and not stripped.startswith('#'):
            module_imports.append(stripped)
    block = '\n'.join(module_imports)

    assert 'core.arena_fetcher' not in block, "no debe importar core.arena_fetcher"
    assert 'core.price_estimator' not in block, "no debe importar core.price_estimator"


# ============================================================================
# GRUPO G: get_task_priority y funciones v7.1
# ============================================================================

def test_get_task_priority():
    """get_task_priority retorna la prioridad correcta."""
    assert R.get_task_priority('chat') == 'latency', "chat → latency"
    assert R.get_task_priority('planning') == 'quality', "planning → quality"
    assert R.get_task_priority('xyz_unknown') == 'quality', "desconocido → quality"


def test_cache_functions():
    """Las funciones de cache v7.1 funcionan correctamente."""
    R._task_cache_initialized = False
    R._task_cache_file = None
    R._task_model_cache = {}

    tmpdir = tempfile.mkdtemp()
    try:
        R._task_cache_file = None
        path = R._get_cache_file_path()
        assert isinstance(path, str), "debe retornar string"
        assert path.endswith('task_model_cache.json'), "debe terminar en .json"

        R._load_task_cache()
        assert isinstance(R._task_model_cache, dict), "cache debe ser dict"

        R._update_task_cache(
            task_type='planning', model='gpt-4o', provider='openai',
            arena_score=92.0, latency_ms=350,
        )
        assert 'planning' in R._task_model_cache, "debe añadir entrada"
        assert R._task_model_cache['planning']['model'] == 'gpt-4o', "modelo debe guardarse"

        R._save_task_cache()
        assert os.path.exists(path), "debe crear archivo"

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
        R._task_cache_initialized = False
        R._task_cache_file = None
        R._task_model_cache = {}


# ============================================================================
# STANDALONE RUNNER (python test_integracion.py directamente)
# ============================================================================

_ALL_TESTS = [
    ("Grupo A: 49 funciones esperadas", [
        test_funciones_v66, test_funciones_arnes, test_funciones_v71,
    ]),
    ("Grupo B: Arnés de emergencia SIN MB", [
        test_arnes_sin_mb_has_config, test_arnes_sin_mb_get_broker_none,
        test_arnes_con_mb_config, test_arnes_reset_broker,
        test_arnes_notify_no_explota, test_arnes_notify_throttle,
        test_arnes_find_ollama_model, test_arnes_emergency_call_structure,
        test_arnes_emergency_call_no_openrouter, test_arnes_run_harness_structure,
        test_arnes_try_bootstrap_sin_modelos,
    ]),
    ("Grupo C: call_llm() SIN MB", [
        test_call_llm_sin_mb, test_call_llm_none_guard_cache,
        test_call_llm_none_guard_pool,
    ]),
    ("Grupo D: initialize_router() standalone", [
        test_initialize_router_standalone, test_initialize_router_cache_persist,
    ]),
    ("Grupo E: Mapa de descalado y estado", [
        test_descale_map, test_get_scaling_state_structure,
        test_validate_self_retorna_bool,
    ]),
    ("Grupo F: Imports limpios", [
        test_imports_limpios,
    ]),
    ("Grupo G: Funciones v7.1", [
        test_get_task_priority, test_cache_functions,
    ]),
]


if __name__ == '__main__':
    print("="*70)
    print("Validación de integración — Router v7.1 (standalone, sin MB)")
    print("="*70)

    passed = 0
    failed = 0
    errors_list = []

    for group_name, tests in _ALL_TESTS:
        print(f"\n--- {group_name} ---")
        for test_fn in tests:
            try:
                test_fn()
                passed += 1
                print(f"  [PASS] {test_fn.__name__}")
            except AssertionError as e:
                failed += 1
                errors_list.append(test_fn.__name__)
                print(f"  [FAIL] {test_fn.__name__}: {e}")
            except Exception as e:
                failed += 1
                errors_list.append(test_fn.__name__)
                print(f"  [ERROR] {test_fn.__name__}: {e}")

    total = passed + failed
    print(f"\n{'='*70}")
    if failed == 0:
        print(f"Resultado: {passed}/{total} tests pasaron")
    else:
        print(f"Resultado: {passed}/{total} pasaron, {failed} FALLARON")
        for name in errors_list:
            print(f"  - {name}")
    print(f"{'='*70}")
    sys.exit(0 if failed == 0 else 1)
