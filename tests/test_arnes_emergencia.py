"""
test_arnes_emergencia.py — Tests del arnés de emergencia del router v7.0.

Ubicación: apa/tests/test_arnes_emergencia.py
Ejecución:  python -m pytest apa/tests/test_arnes_emergencia.py -v
             o:  python apa/tests/test_arnes_emergencia.py

Valida que el router v7.0 fusionado (v6.6 + emergency harness):
  - Tiene las 34 funciones de v6.6 intactas
  - Tiene las 9 funciones nuevas del arnés
  - El arnés funciona correctamente (MB, bootstrap, Ollama, descaling)
  - Los imports de nivel de módulo están limpios
"""

import sys
import os
import time
import types
import logging
import unittest

# ----------------------------------------------------------------------------
# SETUP: Preparar mocks ANTES de importar el router
# ----------------------------------------------------------------------------

logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s')

# 1. Mock de core
_core_mock = types.ModuleType('core')
_core_mock.__path__ = []
sys.modules['core'] = _core_mock

# 2. Mock de core.pool
_pool_mock = types.ModuleType('core.pool')


class MockPoolEntry:
    def __init__(self, provider='mock', model_id='mock-model', **kw):
        self.provider = provider
        self.model_id = model_id
        self.composite_score = kw.get('composite_score', 80.0)
        self.health_status = kw.get('health_status', 'available')
        self.arena_score = kw.get('arena_score', None)
        self.context_length = kw.get('context_length', 128000)
        self.is_free = kw.get('is_free', False)


class MockPool:
    def __init__(self):
        self._entries = []

    def get_all_entries(self):
        return self._entries

    def get_entry(self, provider, model_id):
        for e in self._entries:
            if e.provider == provider and e.model_id == model_id:
                return e
        return None

    def get_available_entries(self):
        return [e for e in self._entries if e.health_status in ('available', 'unknown')]

    def mark_failed(self, provider, model_id):
        for e in self._entries:
            if e.provider == provider and e.model_id == model_id:
                e.health_status = 'failed'
                break

    def health_summary(self):
        return {'available': len(self.get_available_entries()), 'total': len(self._entries)}

    def size(self):
        return len(self._entries)

    def clear(self):
        self._entries.clear()

    def add_entry(self, entry):
        self._entries.append(entry)

    def mark_available(self, provider, model_id):
        pass

    def mark_payment_required(self, provider, model_id):
        pass

    def set_provider_confidence(self, provider, confidence):
        pass

    def get_best_for_context(self, provider, model_id, required_context=0):
        return None


_pool_mock.PoolEntry = MockPoolEntry
_pool_mock.HealthStatus = str
_pool_mock.pool = MockPool()
sys.modules['core.pool'] = _pool_mock
_core_mock.pool = _pool_mock

# 3. Mock de core.model_health
_mh_mock = types.ModuleType('core.model_health')


def _mock_is_context_exceeded(http_code, error_str):
    return http_code == 413 or 'context' in error_str.lower()


def _mock_classify_error(error_str):
    el = error_str.lower()
    if 'payment' in el or 'insufficient_quota' in el or '402' in el:
        return 'payment'
    if 'rate' in el or '429' in el or 'too many' in el:
        return 'rate_limit'
    if 'timeout' in el or 'timed out' in el:
        return 'timeout'
    if 'context' in el or '413' in el:
        return 'context_exceeded'
    if 'auth' in el or '401' in el or '403' in el:
        return 'auth'
    if '404' in el or 'not found' in el:
        return 'not_found'
    if '500' in el or '502' in el or '503' in el:
        return 'server_error'
    return 'unknown'


def _mock_get_diagnostic_info():
    return {'cache_path': '/tmp/mock', 'cache_exists': False, 'verified_models': 0,
            'trust_window': 300, 'available': 0, 'rate_limited': 0,
            'failed': 0, 'unknown': 0, 'pool_callback_registered': False,
            'dirty': False, 'flush_immediately': None}


_mh_mock.is_context_exceeded = _mock_is_context_exceeded
_mh_mock._classify_error = _mock_classify_error
_mh_mock.get_diagnostic_info = _mock_get_diagnostic_info
_mh_mock.get_status = lambda x, p='': 'available'
_mh_mock.mark_available = lambda x, p='': None
_mh_mock.mark_failed = lambda x, p='': None
_mh_mock.report_health = lambda *a, **kw: None
_mh_mock.configure = lambda **kw: None
_mh_mock.mark_provider_paid_models = lambda p: None
_mh_mock.mark_provider_rate_limited = lambda p, **kw: None
_mh_mock.ensure_loaded = lambda: None
sys.modules['core.model_health'] = _mh_mock
_core_mock.model_health = _mh_mock

# 4. Mock de core.normalizer
_norm_mock = types.ModuleType('core.normalizer')
_norm_mock.normalize_model_id = lambda x: x
sys.modules['core.normalizer'] = _norm_mock
_core_mock.normalizer = _norm_mock

# 5. Mock de core.llm_cache
_cache_mock = types.ModuleType('core.llm_cache')


class MockLLMCache:
    def get(self, *a, **kw):
        return None

    def set(self, *a, **kw):
        pass


_cache_mock.LLMCache = MockLLMCache
sys.modules['core.llm_cache'] = _cache_mock
_core_mock.llm_cache = _cache_mock

# 6. Mock de config.settings
_cfg_mock = types.ModuleType('config')
sys.modules['config'] = _cfg_mock


class MockSettings:
    log_level = 'INFO'
    nas_sandbox_path = '/tmp/apa_sandbox'
    model_broker_url = ''
    model_broker_api_key = ''
    has_emergency = True
    emergency_keys = {"ollama_base_url": "http://localhost:11434", "ollama_model": "llama3.1"}
    ollama_base_url = 'http://localhost:11434'
    ollama_default_model = 'llama3.1'
    openrouter_api_key = ''

    @property
    def model_broker_config(self):
        return {"url": self.model_broker_url, "api_key": self.model_broker_api_key}


_settings_mock = types.ModuleType('config.settings')
_settings_mock.settings = MockSettings()
sys.modules['config.settings'] = _settings_mock
_cfg_mock.settings = _settings_mock.settings

# 7. Mock de model_broker

class MockBrokerImpl:
    """Mock controlable de ModelBroker para tests."""
    def __init__(self, *a, **kw):
        self.call_result = None
        self.call_should_raise = None
        self.get_models_result = []
        self.initialize_called = False

    def call(self, **kw):
        if self.call_should_raise:
            raise self.call_should_raise
        return self.call_result or {"success": False, "error": "mock: sin resultado"}

    def get_models(self):
        return self.get_models_result

    def initialize(self):
        self.initialize_called = True


_mb_mock = types.ModuleType('model_broker')
_mb_broker_mock = types.ModuleType('model_broker.broker')
_mb_broker_mock.ModelBroker = MockBrokerImpl
sys.modules['model_broker'] = _mb_mock
sys.modules['model_broker.broker'] = _mb_broker_mock

# 8. Mock de core.providers
_prov_mock = types.ModuleType('core.providers')


class MockProviderManager:
    providers = {}

    @staticmethod
    def parse_prefixed_id(model_id):
        return (None, model_id)

    @staticmethod
    def translate_model_id(base_id, provider_name):
        return base_id

    @staticmethod
    def call_with_fallback(base_id, messages, max_tokens, temperature):
        return {"success": False, "error": "No providers available (mock)"}

    @staticmethod
    def get_all_models(provider_name=None):
        return []


_prov_mock.provider_manager = MockProviderManager()
sys.modules['core.providers'] = _prov_mock
_core_mock.providers = _prov_mock

# 9. Mock de core.usage_tracker
_ut_mock = types.ModuleType('core.usage_tracker')
_ut_mock.UsageTracker = lambda: None
sys.modules['core.usage_tracker'] = _ut_mock
_core_mock.usage_tracker = _ut_mock

# 10. Mock de core.quota_tracker
_qt_mock = types.ModuleType('core.quota_tracker')

class _MockQuotaTracker:
    @staticmethod
    def get_instance():
        m = types.SimpleNamespace()
        m.record_spending = lambda *a, **kw: None
        return m

_qt_mock.QuotaTracker = _MockQuotaTracker
sys.modules['core.quota_tracker'] = _qt_mock
_core_mock.quota_tracker = _qt_mock

# 11. Mock de core.arena (para evitar import errors)
_arena_mock = types.ModuleType('core.arena')
sys.modules['core.arena'] = _arena_mock
_core_mock.arena = _arena_mock

# ----------------------------------------------------------------------------
# IMPORT: Ahora sí importar el router (usará los mocks)
# ----------------------------------------------------------------------------
import importlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
if 'apa.core.router' in sys.modules:
    del sys.modules['apa.core.router']
if 'core.router' in sys.modules:
    del sys.modules['core.router']
if 'config.settings_v2' in sys.modules:
    del sys.modules['config.settings_v2']
# Forzar que use nuestro mock de config.settings
if 'config' in sys.modules:
    del sys.modules['config']
sys.modules['config'] = _cfg_mock
sys.modules['config.settings'] = _settings_mock

from apa.core import router
from config.settings import settings

# ============================================================================
# TESTS
# ============================================================================

class TestFuncionesV66(unittest.TestCase):
    """Verifica que las 34 funciones de v6.6 están presentes."""

    def test_v66_funciones_presentes(self):
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
            self.assertTrue(
                hasattr(router, func) and callable(getattr(router, func)),
                f"v6.6: {func}() falta o no es callable"
            )


class TestFuncionesArnes(unittest.TestCase):
    """Verifica que las 9 funciones del arnés están presentes."""

    def test_arnes_funciones_presentes(self):
        arnes_funcs = [
            '_has_mb_config', '_get_broker', 'reset_broker_status',
            '_notify_emergency_to_user', '_try_bootstrap_mb',
            '_find_ollama_model', '_find_last_working_model',
            '_emergency_call', '_run_emergency_harness',
        ]
        for func in arnes_funcs:
            self.assertTrue(
                hasattr(router, func) and callable(getattr(router, func)),
                f"Arnés: {func}() falta o no es callable"
            )


class TestFuncionesV71(unittest.TestCase):
    """Verifica que las 6 funciones nuevas de v7.1 están presentes."""

    def test_v71_funciones_presentes(self):
        v71_funcs = [
            '_get_cache_file_path', '_load_task_cache', '_save_task_cache',
            '_update_task_cache', 'get_task_priority', 'initialize_router',
        ]
        for func in v71_funcs:
            self.assertTrue(
                hasattr(router, func) and callable(getattr(router, func)),
                f"v7.1: {func}() falta o no es callable"
            )

    def test_priority_map(self):
        self.assertEqual(router.get_task_priority('chat'), 'latency')
        self.assertEqual(router.get_task_priority('planning'), 'quality')
        self.assertEqual(router.get_task_priority('unknown'), 'quality')

    def test_initialize_router(self):
        import tempfile
        tmpdir = tempfile.mkdtemp()
        try:
            router._task_cache_initialized = False
            report = router.initialize_router(cache_dir=tmpdir)
            self.assertIsInstance(report, dict)
            self.assertTrue(report.get('cache_loaded'))
            self.assertIsInstance(report.get('startup_mode'), str)
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)
            router._task_cache_initialized = False
            router._task_cache_file = None


class TestHasMBConfig(unittest.TestCase):
    """Verifica _has_mb_config()."""

    def setUp(self):
        router._broker_instance = None
        router._broker_available = None
        self.original_url = getattr(router.settings, 'model_broker_url', '')

    def tearDown(self):
        router.settings.model_broker_url = self.original_url
        router._broker_instance = None
        router._broker_available = None

    def test_sin_url_false(self):
        router.settings.model_broker_url = ''
        self.assertFalse(router._has_mb_config())

    def test_con_url_true(self):
        router.settings.model_broker_url = 'http://localhost:8000'
        self.assertTrue(router._has_mb_config())


class TestGetBroker(unittest.TestCase):
    """Verifica _get_broker() y reset_broker_status()."""

    def setUp(self):
        router._broker_instance = None
        router._broker_available = None
        self.original_url = getattr(router.settings, 'model_broker_url', '')

    def tearDown(self):
        router.settings.model_broker_url = self.original_url
        router._broker_instance = None
        router._broker_available = None

    def test_con_url_retorna_mock(self):
        router.settings.model_broker_url = 'http://localhost:8000'
        broker = router._get_broker()
        self.assertIsNotNone(broker)

    def test_cache_negativo_none(self):
        router.settings.model_broker_url = 'http://localhost:8000'
        router._broker_available = False
        self.assertIsNone(router._get_broker())

    def test_reset_limpia_cache(self):
        router.settings.model_broker_url = 'http://localhost:8000'
        router._broker_available = False
        router.reset_broker_status()
        self.assertIsNone(router._broker_available)
        broker = router._get_broker()
        self.assertIsNotNone(broker)


class TestNotifyEmergency(unittest.TestCase):
    """Verifica _notify_emergency_to_user()."""

    def setUp(self):
        router._broker_instance = None
        router._broker_available = None

    def test_no_explota(self):
        router._notify_emergency_to_user('test message')
        self.assertTrue(True)

    def test_throttle(self):
        router._last_emergency_notify_time = time.time()
        router._notify_emergency_to_user('throttled')
        self.assertTrue(True)


class TestFindOllamaModel(unittest.TestCase):
    """Verifica _find_ollama_model()."""

    def setUp(self):
        router._broker_instance = None
        router._broker_available = None
        router._last_emergency_notify_time = 0.0

    def tearDown(self):
        router._broker_instance = None
        router._broker_available = None

    def test_sin_ollama(self):
        from unittest.mock import patch
        with patch('requests.get', side_effect=ConnectionError('no Ollama')):
            model = router._find_ollama_model()
        self.assertIsNotNone(model)
        self.assertIsInstance(model, str)
        self.assertEqual(model, 'llama3.1')


class TestEmergencyCall(unittest.TestCase):
    """Verifica _emergency_call() cuando Ollama no corre."""

    def setUp(self):
        router._broker_instance = None
        router._broker_available = None
        router._last_emergency_notify_time = 0.0

    def tearDown(self):
        router._broker_instance = None
        router._broker_available = None

    def test_sin_ollama_success_false(self):
        from unittest.mock import patch
        with patch('requests.post', side_effect=ConnectionError('no Ollama')):
            result = router._emergency_call(system_prompt='sys', user_prompt='hello')
        self.assertFalse(result.get('success'))

    def test_sin_ollama_via_emergency(self):
        result = router._emergency_call(system_prompt='sys', user_prompt='hello')
        self.assertTrue(result.get('via_emergency'))

    def test_sin_ollama_provider_ollama_local(self):
        result = router._emergency_call(system_prompt='sys', user_prompt='hello')
        self.assertEqual(result.get('provider'), 'ollama_local')

    def test_sin_ollama_error_menciona_ollama(self):
        from unittest.mock import patch
        with patch('requests.post', side_effect=ConnectionError('no Ollama')):
            result = router._emergency_call(system_prompt='sys', user_prompt='hello')
        error_msg = result.get('error') or ''
        self.assertIn('Ollama', error_msg)

    def test_no_menciona_openrouter(self):
        import inspect
        src = inspect.getsource(router._emergency_call)
        self.assertNotIn('openrouter', src.lower())


class TestTryBootstrapMB(unittest.TestCase):
    """Verifica _try_bootstrap_mb()."""

    def setUp(self):
        router._broker_instance = None
        router._broker_available = None
        router._last_emergency_notify_time = 0.0
        self.original_url = getattr(router.settings, 'model_broker_url', '')

    def tearDown(self):
        router.settings.model_broker_url = self.original_url
        router._broker_instance = None
        router._broker_available = None

    def test_sin_modelos_false(self):
        router.settings.model_broker_url = 'http://localhost:8000'
        captured = router._try_bootstrap_mb()
        self.assertFalse(captured)

    def test_con_modelos_true(self):
        router.settings.model_broker_url = 'http://localhost:8000'
        # Parchear el ModelBroker que el router inyecto en sys.modules
        _orig = sys.modules['model_broker.broker'].ModelBroker

        class BMWithModels(MockBrokerImpl):
            def __init__(self, *a, **kw):
                super().__init__(*a, **kw)
                self.get_models_result = [{"id": "gpt-4o", "score": 90.0}]
                self.call_result = {"success": True, "content": "OK", "model_used": "gpt-4o", "provider": "openai"}

        sys.modules['model_broker.broker'].ModelBroker = BMWithModels
        try:
            captured = router._try_bootstrap_mb()
            self.assertTrue(captured)
            self.assertTrue(router._broker_available)
        finally:
            sys.modules['model_broker.broker'].ModelBroker = _orig


class TestCallLlmMBExitoso(unittest.TestCase):
    """Verifica call_llm() Capa 1: MB exitoso."""

    def setUp(self):
        router._broker_instance = None
        router._broker_available = None
        router._last_emergency_notify_time = 0.0
        self.original_url = getattr(router.settings, 'model_broker_url', '')

    def tearDown(self):
        router.settings.model_broker_url = self.original_url
        router._broker_instance = None
        router._broker_available = None

    def test_mb_exito(self):
        router.settings.model_broker_url = 'http://localhost:8000'
        broker = router._get_broker()
        broker.call_result = {
            'success': True, 'content': 'OK', 'model_used': 'gpt-4o',
            'provider': 'openai', 'tokens_input': 10, 'tokens_output': 20,
        }
        result = router.call_llm(task_type='chat', system_prompt='sys', user_prompt='hi')
        self.assertTrue(result.get('success'))
        self.assertFalse(result.get('via_emergency'))


class TestCallLlmMBConexoError(unittest.TestCase):
    """Verifica call_llm() Capa 2: MB caído → Emergency."""

    def setUp(self):
        router._broker_instance = None
        router._broker_available = None
        router._last_emergency_notify_time = 0.0
        self.original_url = getattr(router.settings, 'model_broker_url', '')

    def tearDown(self):
        router.settings.model_broker_url = self.original_url
        router._broker_instance = None
        router._broker_available = None
        if router._broker_instance:
            router._broker_instance.call_should_raise = None

    def test_connection_error_activa_emergency(self):
        router.settings.model_broker_url = 'http://localhost:8000'
        broker = router._get_broker()
        broker.call_should_raise = ConnectionError('MB caído')
        result = router.call_llm(task_type='chat', system_prompt='sys', user_prompt='hi')
        self.assertTrue(result.get('via_emergency'))
        self.assertFalse(router._broker_available)


class TestCallLlmMBModeloFalla(unittest.TestCase):
    """Verifica que MB modelo fallo NO activa emergency."""

    def setUp(self):
        router._broker_instance = None
        router._broker_available = None
        router._last_emergency_notify_time = 0.0
        self.original_url = getattr(router.settings, 'model_broker_url', '')

    def tearDown(self):
        router.settings.model_broker_url = self.original_url
        router._broker_instance = None
        router._broker_available = None

    def test_success_false_no_emergency(self):
        router.settings.model_broker_url = 'http://localhost:8000'
        broker = router._get_broker()
        broker.call_result = {'success': False, 'error': 'Model not available'}
        result = router.call_llm(task_type='chat', system_prompt='sys', user_prompt='hi')
        self.assertFalse(result.get('success'))
        self.assertNotEqual(router._broker_available, False)


class TestBootstrapExitoso(unittest.TestCase):
    """Verifica que bootstrap exitoso resuelve via MB."""

    def setUp(self):
        router._broker_instance = None
        router._broker_available = None
        router._last_emergency_notify_time = 0.0
        self.original_url = getattr(router.settings, 'model_broker_url', '')

    def tearDown(self):
        router.settings.model_broker_url = self.original_url
        router._broker_instance = None
        router._broker_available = None

    def test_bootstrap_resuelve(self):
        router.settings.model_broker_url = 'http://localhost:8000'
        # Parchear el ModelBroker que el router inyecto en sys.modules
        _orig = sys.modules['model_broker.broker'].ModelBroker

        class BMBootstrap(MockBrokerImpl):
            def __init__(self, *a, **kw):
                super().__init__(*a, **kw)
                self.get_models_result = [{"id": "gpt-4o", "score": 90.0}]
                self.call_result = {
                    'success': True, 'content': 'Resuelto via MB bootstrap',
                    'model_used': 'gpt-4o', 'provider': 'openai',
                }

        sys.modules['model_broker.broker'].ModelBroker = BMBootstrap
        try:
            router._broker_available = False
            router._broker_instance = None
            result = router.call_llm(task_type='chat', system_prompt='sys', user_prompt='hi')
            self.assertTrue(result.get('success'))
            self.assertTrue(result.get('mb_bootstrapped'))
        finally:
            sys.modules['model_broker.broker'].ModelBroker = _orig


class TestSilentDescaling(unittest.TestCase):
    """Verifica el mapa de descalado silencioso."""

    def test_planning_to_chat(self):
        self.assertEqual(router._DESCALE_MAP.get('planning'), 'generation')

    def test_spec_generation_to_chat(self):
        self.assertEqual(router._DESCALE_MAP.get('spec_generation'), 'generation')

    def test_chat_sin_descalar(self):
        self.assertIsNone(router._DESCALE_MAP.get('chat'))


class TestGetScalingState(unittest.TestCase):
    """Verifica get_scaling_state()."""

    def setUp(self):
        router._broker_instance = None
        router._broker_available = None
        router._last_emergency_notify_time = 0.0

    def tearDown(self):
        router._broker_instance = None
        router._broker_available = None

    def test_retorna_dict(self):
        state = router.get_scaling_state()
        self.assertIsInstance(state, dict)

    def test_tiene_emergency_active(self):
        state = router.get_scaling_state()
        self.assertIn('emergency_active', state)

    def test_tiene_current_model(self):
        state = router.get_scaling_state()
        self.assertIn('current_model', state)


class TestRunEmergencyHarness(unittest.TestCase):
    """Verifica _run_emergency_harness()."""

    def setUp(self):
        router._broker_instance = None
        router._broker_available = None
        router._last_emergency_notify_time = 0.0
        self.original_url = getattr(router.settings, 'model_broker_url', '')

    def tearDown(self):
        router.settings.model_broker_url = self.original_url
        router._broker_instance = None
        router._broker_available = None

    def test_retorna_dict(self):
        router.settings.model_broker_url = 'http://localhost:8000'
        result = router._run_emergency_harness(
            task_type='chat', system_prompt='sys', user_prompt='hi',
            max_tokens=100, temperature=0.7, call_start_time=time.time(),
        )
        self.assertIsInstance(result, dict)
        self.assertIn('success', result)
        self.assertIn('via_emergency', result)


class TestImportsLimpios(unittest.TestCase):
    """Verifica que no hay imports prohibidos a nivel de módulo."""

    def test_no_arena_fetcher(self):
        with open(router.__file__, encoding='utf-8') as f:
            source = f.read()
        module_imports = []
        for line in source.split('\n'):
            if line.startswith('def '):
                break
            stripped = line.strip()
            if stripped.startswith(('import ', 'from ')) and not stripped.startswith('#'):
                module_imports.append(stripped)
        block = '\n'.join(module_imports)
        self.assertNotIn('core.arena_fetcher', block)

    def test_no_price_estimator_nivel_modulo(self):
        with open(router.__file__, encoding='utf-8') as f:
            source = f.read()
        module_imports = []
        for line in source.split('\n'):
            if line.startswith('def '):
                break
            stripped = line.strip()
            if stripped.startswith(('import ', 'from ')) and not stripped.startswith('#'):
                module_imports.append(stripped)
        block = '\n'.join(module_imports)
        self.assertNotIn('core.price_estimator', block)


class TestValidateSelf(unittest.TestCase):
    """Verifica validate_self()."""

    def setUp(self):
        router._broker_instance = None
        router._broker_available = None
        router._last_emergency_notify_time = 0.0

    def tearDown(self):
        router._broker_instance = None
        router._broker_available = None

    def test_retorna_bool(self):
        self.assertIsInstance(router.validate_self(), bool)


if __name__ == '__main__':
    unittest.main()