# apa/tests/test_comprehensivo_fase0_4.py
# Test comprehensivo final — valida las 5 fases de limpieza en una sola ejecucion.
#
# Fase 0: Emergency harness en router.py v7.0
# Fase 1: Sin refs rotas en archivos productivos (pool, price_estimator, select_model, provider_manager)
# Fase 2: Sin EVT muertos en notifications.py ni notification_ui_bridge.py
# Fase 3: 6 modulos huérfanos eliminados del filesystem
# Fase 4: Tests obsoletos eliminados, sin imports residuales
# Cross: Sin escapes invalidos en .py productivos
#
# Ejecutar:
#   python c:/Python/Proyectos/APA/apa/tests/test_comprehensivo_fase0_4.py
# O con pytest:
#   cd C:\Python\Proyectos\APA && python -m pytest apa/tests/test_comprehensivo_fase0_4.py -v

import sys
import os
import ast
import warnings
import unittest
from types import ModuleType
from unittest.mock import MagicMock, patch

# --- Setup: project root en sys.path (3 niveles desde apa/tests/) ---
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# ============================================================================
# Mocks minimos para poder importar router
# ============================================================================

_mb_broker = ModuleType("broker")
_mb_broker.ModelBroker = MagicMock
_mb_pkg = ModuleType("model_broker")
_mb_pkg.broker = _mb_broker
sys.modules["model_broker"] = _mb_pkg
sys.modules["model_broker.broker"] = _mb_broker

import tempfile
_ut = ModuleType("usage_tracker")
_ut.UsageTracker = MagicMock
_ut.db_path = tempfile.mktemp(suffix=".db")
sys.modules["apa.core.usage_tracker"] = _ut
sys.modules["apa.core.usage_tracker.usage_tracker"] = _ut

_notif = ModuleType("notifications")
_notif.notify = MagicMock()
_notif.register_callback = MagicMock()
_notif.unregister_callback = MagicMock()
_notif.get_recent_events = MagicMock(return_value=[])
_notif.get_events_by_type = MagicMock(return_value=[])
sys.modules["apa.core.notifications"] = _notif
sys.modules["core.notifications"] = _notif

# ============================================================================
# Helpers
# ============================================================================

DEAD_MODULES = [
    "core/pool.py", "core/providers.py", "core/model_health.py",
    "core/arena_fetcher.py", "core/price_estimator.py", "core/normalizer.py",
]

DEAD_EVT_NAMES = [
    'EVT_HEALTH_MODEL_VERIFIED', 'EVT_HEALTH_MODEL_FAILED',
    'EVT_HEALTH_MODEL_RATE_LIMITED', 'EVT_HEALTH_MODEL_REMOVED',
    'EVT_HEALTH_CYCLE_START', 'EVT_HEALTH_CYCLE_END',
    'EVT_HEALTH_FLUSH_DISK', 'EVT_HEALTH_CACHE_LOADED',
    'EVT_HEALTH_POOL_SYNCED',
    'EVT_ARENA_REFRESH_START', 'EVT_ARENA_REFRESH_COMPLETE',
    'EVT_ARENA_REFRESH_FAILED', 'EVT_ARENA_CACHE_LOADED',
    'EVT_ARENA_CATEGORY_LOADED', 'EVT_ARENA_TOP_MODELS',
    'EVT_POOL_POPULATED', 'EVT_POOL_MODEL_UPDATED', 'EVT_POOL_SYNC_BATCH',
]

DEAD_IMPORT_KEYWORDS = [
    "from core.pool", "import core.pool",
    "from core.providers", "import core.providers",
    "from core.model_health", "import core.model_health",
    "from core.arena_fetcher", "import core.arena_fetcher",
    "from core.price_estimator", "import core.price_estimator",
    "from core.normalizer", "import core.normalizer",
]

SKIP_DIRS = {"__pycache__", ".git", ".venv", "venv", "node_modules", "scripts"}
PRODUCTION_DIRS = {"core", "agents", "interface", "config"}


def _read_source(rel_path: str) -> str:
    full_path = os.path.join(PROJECT_ROOT, "apa", rel_path)
    with open(full_path, "r", encoding="utf-8") as f:
        return f.read()


def _file_exists(rel_path: str) -> bool:
    return os.path.isfile(os.path.join(PROJECT_ROOT, "apa", rel_path))


def _has_dead_import_in_code(source: str) -> list:
    """Busca imports muertos solo en codigo ejecutable (no docstrings)."""
    problems = []
    lines = source.split("\n")
    in_docstring = False
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if not in_docstring:
            count = stripped.count('"""')
            if count == 1:
                in_docstring = True
                continue
            elif count >= 2:
                continue
        else:
            if stripped.count('"""') >= 1:
                in_docstring = False
            continue
        if stripped and not stripped.startswith("#"):
            for kw in DEAD_IMPORT_KEYWORDS:
                if kw in line:
                    problems.append((i, kw))
                    break
    return problems


def _scan_production_files() -> list:
    """Retorna [(rel_path, [(lineno, keyword)])] para archivos productivos con imports muertos."""
    apa_dir = os.path.join(PROJECT_ROOT, "apa")
    results = []
    for root, dirs, files in os.walk(apa_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fname in files:
            if not fname.endswith(".py"):
                continue
            if fname.startswith("test_"):
                continue
            full = os.path.join(root, fname)
            rel = os.path.relpath(full, os.path.join(PROJECT_ROOT, "apa"))
            top = rel.split(os.sep)[0] if os.sep in rel else rel.split("/")[0]
            if top not in PRODUCTION_DIRS:
                continue
            try:
                source = _read_source(rel)
            except FileNotFoundError:
                continue
            hits = _has_dead_import_in_code(source)
            if hits:
                results.append((rel, hits))
    return results


# ============================================================================
# FASE 0: Emergency Harness
# ============================================================================

class TestFase0EmergencyHarness(unittest.TestCase):
    """Valida que el emergency harness existe y funciona."""

    def test_find_last_working_model_exists(self):
        from apa.core.router import _find_last_working_model
        self.assertTrue(callable(_find_last_working_model))

    def test_notify_emergency_to_user_exists(self):
        from apa.core.router import _notify_emergency_to_user
        self.assertTrue(callable(_notify_emergency_to_user))

    def test_emergency_throttle_constant(self):
        from apa.core.router import _EMERGENCY_NOTIFY_INTERVAL
        self.assertGreater(_EMERGENCY_NOTIFY_INTERVAL, 0)

    def test_find_last_working_filters_by_task_type(self):
        """SQL query incluye WHERE task_type = ? cuando se pasa task_type."""
        from apa.core.router import _find_last_working_model
        with patch("sqlite3.connect") as mock_connect:
            mock_cursor = MagicMock()
            mock_conn = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_connect.return_value = mock_conn
            mock_cursor.fetchone.return_value = None
            _find_last_working_model("coding")
            sql = mock_cursor.execute.call_args[0][0]
            self.assertIn("task_type = ?", sql)

    def test_notify_emergency_throttle(self):
        """No repite notificacion antes del intervalo."""
        from apa.core.router import _notify_emergency_to_user
        import apa.core.router as router_mod
        router_mod._emergency_notify_time = 0.0
        with patch("apa.core.router._notify") as mock_n, \
             patch("apa.core.router._find_last_working_model"):
            _notify_emergency_to_user("coding")
            _notify_emergency_to_user("planning")
            self.assertEqual(mock_n.call_count, 1)


# ============================================================================
# FASE 1: Sin refs rotas en produccion
# ============================================================================

class TestFase1NoBrokenRefs(unittest.TestCase):
    """Valida que los archivos productivos no tienen refs a modulos muertos."""

    def test_no_dead_imports_in_production(self):
        problems = _scan_production_files()
        if problems:
            lines = []
            for rel, hits in problems:
                for ln, kw in hits:
                    lines.append(f"  {rel}:{ln} -> {kw}")
            self.fail(f"{len(problems)} archivos con imports muertos:\n" + "\n".join(lines))

    def test_planner_no_select_model(self):
        source = _read_source("core/planner.py")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.ImportFrom, ast.Import)):
                text = ast.dump(node)
                if "select_model" in text:
                    self.fail(f"planner.py aun importa select_model")

    def test_orchestrator_no_provider_manager(self):
        source = _read_source("core/orchestrator.py")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.ImportFrom, ast.Import)):
                text = ast.dump(node)
                if "provider" in text.lower():
                    self.fail(f"orchestrator.py aun importa providers")

    def test_corrector_clean(self):
        source = _read_source("agents/corrector.py")
        hits = _has_dead_import_in_code(source)
        self.assertFalse(hits, f"corrector.py tiene imports muertos: {hits}")

    def test_documenter_no_price_estimator(self):
        source = _read_source("agents/documenter.py")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module and "price_estimator" in node.module:
                    self.fail(f"documenter.py aun importa price_estimator")

    def test_app_no_pool_import(self):
        source = _read_source("interface/app.py")
        tree = ast.parse(source)
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("core.pool"):
                    self.fail(f"app.py:{node.lineno} aun importa core.pool")


# ============================================================================
# FASE 2: Notifications limpias
# ============================================================================

class TestFase2NotificationsClean(unittest.TestCase):
    """Valida notifications.py y notification_ui_bridge.py sin EVT muertos."""

    def test_notifications_no_dead_constants(self):
        source = _read_source("core/notifications.py")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name) and t.id.startswith("EVT_"):
                        self.assertNotIn(t.id, DEAD_EVT_NAMES,
                            f"notifications.py define {t.id} (eliminado en v2.0)")

    def test_notifications_has_emergency_mode(self):
        source = _read_source("core/notifications.py")
        tree = ast.parse(source)
        found = any(
            isinstance(t, ast.Name) and t.id == "EVT_EMERGENCY_MODE"
            for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            for t in node.targets
        )
        self.assertTrue(found, "notifications.py debe definir EVT_EMERGENCY_MODE")

    def test_bridge_no_dead_imports(self):
        source = _read_source("core/notification_ui_bridge.py")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if "notifications" in node.module:
                    for alias in node.names:
                        self.assertNotIn(alias.name, DEAD_EVT_NAMES,
                            f"bridge importa {alias.name} (eliminado)")

    def test_bridge_event_types_list_count(self):
        source = _read_source("core/notification_ui_bridge.py")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name) and t.id == "EVENT_TYPES_LIST":
                        if isinstance(node.value, ast.List):
                            self.assertEqual(len(node.value.elts), 8)

    def test_bridge_html_no_arena_providers(self):
        source = _read_source("core/notification_ui_bridge.py")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in ("NOTIF_SECTION_HTML", "NOTIF_JS"):
                        val = ast.get_source_segment(source, node.value) or ""
                        self.assertNotIn("sm-arena", val,
                            f"{target.id} no deberia tener sm-arena")
                        self.assertNotIn("sm-provactive", val,
                            f"{target.id} no deberia tener sm-provactive")

    def test_documenter_no_dead_evt_import(self):
        source = _read_source("agents/documenter.py")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name in DEAD_EVT_NAMES:
                        self.fail(f"documenter.py importa {alias.name}")


# ============================================================================
# FASE 3: Modulos huérfanos eliminados
# ============================================================================

class TestFase3OrphansDeleted(unittest.TestCase):
    """Valida que los 6 modulos huérfanos no existen."""

    def test_all_orphans_gone(self):
        for mod in DEAD_MODULES:
            self.assertFalse(_file_exists(mod),
                f"{mod} aun existe (deberia eliminarse en Fase 3)")

    def test_no_orphan_pyc(self):
        for mod in DEAD_MODULES:
            pyc = mod.replace(".py", ".pyc")
            # Buscar en cualquier __pycache__
            name = os.path.basename(pyc)
            found = False
            for root, dirs, files in os.walk(os.path.join(PROJECT_ROOT, "apa")):
                if name in files:
                    found = True
                    break
            self.assertFalse(found, f"{pyc} aun existe en __pycache__")


# ============================================================================
# FASE 4: Tests obsoletos eliminados, sin residuos
# ============================================================================

class TestFase4NoResiduals(unittest.TestCase):
    """Valida que no quedan imports muertos en ningun .py."""

    def test_no_dead_imports_in_tests(self):
        tests_dir = os.path.join(PROJECT_ROOT, "apa", "tests")
        if not os.path.isdir(tests_dir):
            return
        problems = []
        for fname in sorted(os.listdir(tests_dir)):
            if not fname.endswith(".py") or fname.startswith("test_fase"):
                continue
            # Excluir este propio archivo (contiene DEAD_IMPORT_KEYWORDS como datos)
            if fname == os.path.basename(__file__):
                continue
            rel = os.path.join("tests", fname)
            try:
                source = _read_source(rel)
            except FileNotFoundError:
                continue
            hits = _has_dead_import_in_code(source)
            for ln, kw in hits:
                problems.append(f"  {rel}:{ln} -> {kw}")
        if problems:
            self.fail(f"Imports muertos en tests:\n" + "\n".join(problems))

    def test_fase_tests_exist(self):
        for test in ["test_fase0_emergency.py", "test_fase1_critical.py",
                      "test_fase2_notifications.py", "test_fase3_fase4_cleanup.py"]:
            self.assertTrue(_file_exists(f"tests/{test}"),
                f"{test} fue eliminado accidentalmente")


# ============================================================================
# CROSS: Select model y provider manager
# ============================================================================

class TestCrossNoSelectModelNoProviderManager(unittest.TestCase):
    """Valida que select_model y provider_manager no existen en produccion."""

    def test_no_select_model_anywhere_production(self):
        apa_dir = os.path.join(PROJECT_ROOT, "apa")
        problems = []
        for root, dirs, files in os.walk(apa_dir):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for fname in files:
                if not fname.endswith(".py") or fname.startswith("test_"):
                    continue
                full = os.path.join(root, fname)
                rel = os.path.relpath(full, os.path.join(PROJECT_ROOT, "apa"))
                top = rel.split(os.sep)[0] if os.sep in rel else rel.split("/")[0]
                if top not in PRODUCTION_DIRS:
                    continue
                try:
                    source = _read_source(rel)
                except FileNotFoundError:
                    continue
                tree = ast.parse(source)
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom):
                        for alias in node.names:
                            if "select_model" in alias.name:
                                problems.append(f"  {rel}:{node.lineno} -> {alias.name}")
        if problems:
            self.fail(f"select_model encontrado:\n" + "\n".join(problems))

    def test_no_provider_manager_anywhere_production(self):
        apa_dir = os.path.join(PROJECT_ROOT, "apa")
        problems = []
        for root, dirs, files in os.walk(apa_dir):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for fname in files:
                if not fname.endswith(".py") or fname.startswith("test_"):
                    continue
                full = os.path.join(root, fname)
                rel = os.path.relpath(full, os.path.join(PROJECT_ROOT, "apa"))
                top = rel.split(os.sep)[0] if os.sep in rel else rel.split("/")[0]
                if top not in PRODUCTION_DIRS:
                    continue
                try:
                    source = _read_source(rel)
                except FileNotFoundError:
                    continue
                tree = ast.parse(source)
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom):
                        if node.module and "provider" in node.module.lower():
                            for alias in node.names:
                                if "provider_manager" in alias.name:
                                    problems.append(f"  {rel}:{node.lineno} -> {alias.name}")
        if problems:
            self.fail(f"provider_manager encontrado:\n" + "\n".join(problems))


# ============================================================================
# CROSS: Sin escapes invalidos en archivos productivos
# ============================================================================

class TestCrossNoInvalidEscapes(unittest.TestCase):
    """Valida que no hay DeprecationWarning por escapes invalidos."""

    def test_no_invalid_escape_sequences(self):
        warnings.filterwarnings("error", category=DeprecationWarning,
                                message="invalid escape sequence")
        try:
            for rel in ["core/router.py", "interface/app.py",
                         "agents/corrector.py", "agents/documenter.py",
                         "core/planner.py", "core/orchestrator.py",
                         "core/notifications.py", "core/notification_ui_bridge.py"]:
                source = _read_source(rel)
                try:
                    compile(source, rel, "exec")
                except DeprecationWarning as e:
                    self.fail(f"{rel}: {e}")
        finally:
            warnings.filterwarnings("default", category=DeprecationWarning)


if __name__ == "__main__":
    unittest.main(verbosity=2)