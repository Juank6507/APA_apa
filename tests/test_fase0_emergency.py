# apa/tests/test_fase0_emergency.py
# Tests independientes para Fase 0: Emergency Harness Enhancement
#
# Validaciones:
# 1. _find_last_working_model(task_type) filtra por task_type desde UsageTracker
# 2. _find_last_working_model() sin args retorna ultimo global
# 3. _notify_emergency_to_user emite notificacion con mensaje claro al usuario
# 4. _notify_emergency_to_user tiene throttle (no repite antes de 5 min)
# 5. _notify_emergency_to_user incluye info del modelo cacheado
# 6. call_llm activa emergency harness cuando MB no disponible
# 7. El mensaje de notificacion menciona "recursos minimos" y "Model Broker"
#
# Ejecutar (desde cualquier ubicacion):
#   python c:/Python/Proyectos/APA/apa/tests/test_fase0_emergency.py
# O con pytest:
#   cd C:\Python\Proyectos\APA && python -m pytest apa/tests/test_fase0_emergency.py -v

import sys
import os
import time
import tempfile
import unittest
from unittest.mock import MagicMock, patch, call
from types import ModuleType

# --- Setup: project root en sys.path ---
# El test esta en apa/tests/ (3 niveles desde project root)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# ============================================================================
# Mockear solo submodulos hoja (NUNCA paquetes padre apa / apa.core)
# ============================================================================

# 1. model_broker.broker (no instalado en este entorno)
_mb_broker = ModuleType("broker")
_mb_broker.ModelBroker = MagicMock
_mb_pkg = ModuleType("model_broker")
_mb_pkg.broker = _mb_broker
sys.modules["model_broker"] = _mb_pkg
sys.modules["model_broker.broker"] = _mb_broker

# 2. apa.core.usage_tracker — con db_path funcional para sqlite3
_ut = ModuleType("usage_tracker")
_ut.UsageTracker = MagicMock
_ut.db_path = tempfile.mktemp(suffix=".db")
sys.modules["apa.core.usage_tracker"] = _ut
sys.modules["apa.core.usage_tracker.usage_tracker"] = _ut

# 3. apa.core.notifications
_notif = ModuleType("notifications")
sys.modules["apa.core.notifications"] = _notif

# 4. Modulos huérfanos (seran eliminados en Fase 3)
_norm = ModuleType("normalizer")
_norm.normalize_model_id = lambda x: x
sys.modules["core.normalizer"] = _norm
sys.modules["apa.core.normalizer"] = _norm

_pool_mod = ModuleType("pool")
_pool_mod.PoolEntry = MagicMock
_pool_mod.HealthStatus = MagicMock
_pool_mod.pool = MagicMock()
sys.modules["core.pool"] = _pool_mod
sys.modules["apa.core.pool"] = _pool_mod

_mh_mod = ModuleType("model_health")
sys.modules["core.model_health"] = _mh_mod
sys.modules["apa.core.model_health"] = _mh_mod

# ============================================================================
# Importar router DESPUES de todos los mocks
# ============================================================================
from apa.core.router import (
    _find_last_working_model,
    _notify_emergency_to_user,
    call_llm,
    _emergency_notify_time,
    _EMERGENCY_NOTIFY_INTERVAL,
)


def _make_mock_row(model: str, provider: str):
    """Crea un mock de sqlite3.Row con los campos model y provider."""
    row = MagicMock()
    row.__getitem__ = lambda self, key: {"model": model, "provider": provider}[key]
    return row


class TestFindLastWorkingModelByTaskType(unittest.TestCase):
    """Test 1-2: _find_last_working_model filtra por task_type."""

    @patch("sqlite3.connect")
    def test_filtrar_por_task_type(self, mock_connect):
        """Busca el ultimo exitoso para el task_type dado."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        mock_cursor.fetchone.return_value = _make_mock_row("gpt-4o", "openai")

        result = _find_last_working_model("coding")

        sql = mock_cursor.execute.call_args[0][0]
        params = mock_cursor.execute.call_args[0][1]
        self.assertIn("task_type = ?", sql)
        self.assertEqual(params, ("coding",))
        self.assertIsNotNone(result)
        self.assertEqual(result["model"], "gpt-4o")
        self.assertEqual(result["provider"], "openai")

    @patch("sqlite3.connect")
    def test_fallback_global_sin_task_type(self, mock_connect):
        """Sin task_type, retorna el ultimo exitoso global."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        mock_cursor.fetchone.return_value = _make_mock_row("claude-3", "anthropic")

        result = _find_last_working_model()

        sql = mock_cursor.execute.call_args[0][0]
        self.assertNotIn("task_type = ?", sql)
        self.assertIn("success = 1", sql)
        self.assertEqual(result["model"], "claude-3")

    @patch("sqlite3.connect")
    def test_retorna_none_si_no_hay_datos(self, mock_connect):
        """Retorna None si no hay modelos exitosos."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        mock_cursor.fetchone.return_value = None

        result = _find_last_working_model("planning")
        self.assertIsNone(result)

    @patch("sqlite3.connect")
    def test_dos_llamadas_distintas(self, mock_connect):
        """Se puede llamar con task_type y luego sin el (fallback global)."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        # Primera: con task_type, retorna None
        mock_cursor.fetchone.return_value = None
        result_typed = _find_last_working_model("correction")
        self.assertIsNone(result_typed)
        sql1 = mock_cursor.execute.call_args[0][0]
        self.assertIn("task_type = ?", sql1)

        # Segunda: sin task_type, retorna modelo global
        mock_cursor.fetchone.return_value = _make_mock_row("deepseek", "deepseek")
        result_global = _find_last_working_model()
        self.assertEqual(result_global["model"], "deepseek")
        sql2 = mock_cursor.execute.call_args[0][0]
        self.assertNotIn("task_type = ?", sql2)


class TestNotifyEmergencyToUser(unittest.TestCase):
    """Test 3-5: _notify_emergency_to_user notificacion y throttle."""

    def setUp(self):
        """Resetear throttle antes de cada test."""
        import apa.core.router as router_mod
        router_mod._emergency_notify_time = 0.0

    @patch("apa.core.router._notify")
    @patch("apa.core.router._find_last_working_model")
    def test_emite_notificacion_clara(self, mock_find, mock_notify):
        """Primera llamada emite notificacion con mensaje claro."""
        mock_find.return_value = {"model": "gpt-4o", "provider": "openai"}

        _notify_emergency_to_user("coding")

        mock_notify.assert_called_once()
        event_type, message, data = mock_notify.call_args[0]
        self.assertEqual(event_type, "system:emergency_mode")
        self.assertIn("Model Broker no disponible", message)
        self.assertIn("recursos minimos", message)
        self.assertIn("gpt-4o", message)

    @patch("apa.core.router._notify")
    @patch("apa.core.router._find_last_working_model")
    def test_incluye_info_modelo_cacheado(self, mock_find, mock_notify):
        """La notificacion incluye datos del modelo en cache."""
        mock_find.return_value = {"model": "claude-3", "provider": "anthropic"}

        _notify_emergency_to_user("planning")

        _, _, data = mock_notify.call_args[0]
        self.assertEqual(data["cached_model"], "claude-3")
        self.assertEqual(data["cached_provider"], "anthropic")
        self.assertEqual(data["task_type"], "planning")

    @patch("apa.core.router._notify")
    @patch("apa.core.router._find_last_working_model")
    def test_mensaje_sin_cache(self, mock_find, mock_notify):
        """Si no hay cache, el mensaje dice 'No hay modelos en cache'."""
        mock_find.return_value = None

        _notify_emergency_to_user("coding")

        _, message, _ = mock_notify.call_args[0]
        self.assertIn("No hay modelos en cache", message)

    @patch("apa.core.router._notify")
    @patch("apa.core.router._find_last_working_model")
    def test_throttle_no_repite(self, mock_find, mock_notify):
        """No repite notificacion antes de _EMERGENCY_NOTIFY_INTERVAL."""
        mock_find.return_value = {"model": "gpt-4o", "provider": "openai"}

        _notify_emergency_to_user("coding")
        _notify_emergency_to_user("planning")

        self.assertEqual(mock_notify.call_count, 1)

    @patch("apa.core.router._notify")
    @patch("apa.core.router._find_last_working_model")
    def test_throttle_permite_despues_intervalo(self, mock_find, mock_notify):
        """Permite notificar de nuevo despues del intervalo."""
        mock_find.return_value = {"model": "gpt-4o", "provider": "openai"}

        import apa.core.router as router_mod

        _notify_emergency_to_user("coding")
        router_mod._emergency_notify_time = 0.0
        _notify_emergency_to_user("planning")

        self.assertEqual(mock_notify.call_count, 2)


class TestCallLlmEmergencyActivation(unittest.TestCase):
    """Test 6-7: call_llm activa emergency harness y notifica al usuario."""

    @patch("apa.core.router._notify_emergency_to_user")
    @patch("apa.core.router._emergency_call")
    @patch("apa.core.router._call_via_broker", return_value=None)
    def test_activa_emergency_cuando_mb_falla(self, mock_broker, mock_emergency, mock_notify_user):
        """Cuando MB no responde, activa emergency harness y notifica."""
        import apa.core.router as router_mod
        original = router_mod._MB_AVAILABLE
        router_mod._MB_AVAILABLE = False
        try:
            result = call_llm(
                task_type="coding",
                system_prompt="test system",
                user_prompt="test user",
            )
            mock_notify_user.assert_called_once_with("coding")
            mock_emergency.assert_called_once()
        finally:
            router_mod._MB_AVAILABLE = original


if __name__ == "__main__":
    unittest.main(verbosity=2)