# apa/tests/test_fase1_critical.py
# Tests independientes para Fase 1: Limpieza de archivos CRITICAL
#
# Validaciones:
# 1. planner.py: importa sin crash, no tiene select_model
# 2. orchestrator.py: importa sin crash, no tiene provider_manager
# 3. app.py: importa sin crash, no tiene pool/price_estimator top-level
# 4. corrector.py: importa sin crash, no tiene provider_manager/select_model
# 5. documenter.py: importa sin crash, no tiene price_estimator
# 6. app._get_model_price_details: funciona sin provider_manager
# 7. app._evaluate_maturity_with_llm: usa call_llm (no pool)
# 8. app endpoints deprecados retornan JSON sin crash
#
# Ejecutar (desde cualquier ubicacion):
#   python c:/Python/Proyectos/APA/apa/tests/test_fase1_critical.py
# O con pytest:
#   cd C:\Python\Proyectos\APA && python -m pytest apa/tests/test_fase1_critical.py -v

import sys
import os
import ast
import unittest
from unittest.mock import MagicMock
from types import ModuleType

# --- Setup: project root en sys.path (3 niveles desde apa/tests/) ---
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# ============================================================================
# Mockear solo submodulos hoja (NUNCA paquetes padre apa / apa.core)
# ============================================================================

# 1. model_broker.broker
_mb_broker = ModuleType("broker")
_mb_broker.ModelBroker = MagicMock
_mb_pkg = ModuleType("model_broker")
_mb_pkg.broker = _mb_broker
sys.modules["model_broker"] = _mb_pkg
sys.modules["model_broker.broker"] = _mb_broker

# 2. apa.core.usage_tracker
_ut = ModuleType("usage_tracker")
_ut.UsageTracker = MagicMock
sys.modules["apa.core.usage_tracker"] = _ut

# 3. apa.core.notifications
_notif = ModuleType("notifications")
_notif.notify = MagicMock()
_notif.register_callback = MagicMock()
_notif.unregister_callback = MagicMock()
_notif.get_recent_events = MagicMock(return_value=[])
sys.modules["apa.core.notifications"] = _notif

# 4. Modulos huérfanos (seran eliminados en Fase 3)
for mod_name in ["pool", "providers", "model_health", "arena_fetcher",
                  "price_estimator", "normalizer"]:
    _m = ModuleType(mod_name)
    sys.modules[f"core.{mod_name}"] = _m
    sys.modules[f"apa.core.{mod_name}"] = _m

# 5. Otros modulos que app.py importa
# spec_parser eliminado en P0 (reemplazado por spec_builder + code_signatures + symbol_graph)
for mod_name in ["language_detector", "tech_domain_map",
                  "sdd_maturity", "sdd_guide", "pipeline_state",
                  "failure_auditor", "spec_builder", "apa_theme",
                  "project_reader", "quota_tracker", "llm_cache"]:
    _m = ModuleType(mod_name)
    sys.modules[f"core.{mod_name}"] = _m
    sys.modules[f"apa.core.{mod_name}"] = _m

sys.modules["agents.generator"] = ModuleType("generator")
sys.modules["agents.corrector"] = ModuleType("corrector")
sys.modules["agents.documenter"] = ModuleType("documenter")
sys.modules["apa.agents.generator"] = ModuleType("generator")
sys.modules["apa.agents.corrector"] = ModuleType("corrector")
sys.modules["apa.agents.documenter"] = ModuleType("documenter")
sys.modules["interface.shared_tabs"] = ModuleType("shared_tabs")

# 6. mcp.server
_mcp = ModuleType("mcp")
_mcp_server = ModuleType("mcp.server")
_mcp_server.get_connector = MagicMock()
sys.modules["mcp"] = _mcp
sys.modules["mcp.server"] = _mcp_server

# 7. config.settings con valores por defecto
_settings_mod = ModuleType("settings")
_settings = MagicMock()
_settings.log_level = "WARNING"
_settings.nas_sandbox_path = "/app/sandbox"
_settings.model_broker_url = "http://localhost:8100"
_settings.ollama_base_url = ""
_settings.get_emergency_keys = MagicMock(return_value={})
_settings.has_emergency_keys = MagicMock(return_value=False)
_settings_mod.settings = _settings
sys.modules["config.settings"] = _settings_mod
sys.modules["apa.config.settings"] = _settings_mod

# 8. core.checkpoint, core.parallel_executor
sys.modules["core.checkpoint"] = ModuleType("checkpoint")
sys.modules["apa.core.checkpoint"] = ModuleType("checkpoint")
sys.modules["core.parallel_executor"] = ModuleType("parallel_executor")
sys.modules["apa.core.parallel_executor"] = ModuleType("parallel_executor")

# 9. core.notification_ui_bridge
_nuib = ModuleType("notification_ui_bridge")
_nuib.format_event = MagicMock(return_value={})
_nuib.get_event_summary = MagicMock(return_value="")
_nuib.get_full_summary = MagicMock(return_value="")
_nuib.EVENT_TYPES_LIST = []
_nuib.create_bridge_callback = MagicMock()
_nuib.NOTIF_CSS = ""
_nuib.NOTIF_TAB_BUTTON = ""
_nuib.NOTIF_SECTION_HTML = ""
_nuib.NOTIF_JS = ""
sys.modules["core.notification_ui_bridge"] = _nuib
sys.modules["apa.core.notification_ui_bridge"] = _nuib

# 10. FastAPI y dependencias (ya instaladas, pero por seguridad)
try:
    import fastapi
    import pydantic
    import starlette
except ImportError:
    # Crear mocks minimos si no estan instalados
    _fastapi = ModuleType("fastapi")
    _fastapi.FastAPI = MagicMock
    _fastapi.HTTPException = type("HTTPException", (Exception,), {})
    _fastapi.BackgroundTasks = MagicMock
    _fastapi.Request = MagicMock
    sys.modules["fastapi"] = _fastapi
    sys.modules["fastapi.responses"] = ModuleType("fastapi.responses")
    sys.modules["fastapi.staticfiles"] = ModuleType("fastapi.staticfiles")
    sys.modules["pydantic"] = ModuleType("pydantic")
    sys.modules["starlette"] = ModuleType("starlette")


def _read_source(filepath: str) -> str:
    """Lee el fuente de un archivo del proyecto."""
    full_path = os.path.join(PROJECT_ROOT, "apa", filepath)
    with open(full_path, "r", encoding="utf-8") as f:
        return f.read()


def _lines_with_code_only(source: str) -> list:
    """Filtra lineas de codigo ejecutable (excluye docstrings y comentarios).

    Rastrea estado de docstring (triple quotes) para no falsar
    cuando el texto prohibido aparece dentro de un docstring.
    """
    lines = source.split("\n")
    result = []
    in_docstring = False
    for line in lines:
        stripped = line.strip()
        if not in_docstring:
            # Contar triple quotes en esta linea
            count = stripped.count('\"\"\"')
            if count == 1:
                in_docstring = True
                continue  # Linea de apertura de docstring
            elif count >= 2:
                continue  # Docstring de una sola linea
            # No es docstring: es codigo o comentario
            if stripped and not stripped.startswith("#"):
                result.append(line)
        else:
            # Dentro de docstring: buscar cierre
            count = stripped.count('\"\"\"')
            if count >= 1:
                in_docstring = False
            continue
    return result


def _get_function_body_lines(source: str, func_name: str) -> list:
    """Extrae las lineas de codigo de una funcion (sin docstring ni comentarios)."""
    lines = source.split("\n")
    body_lines = []
    in_func = False
    in_docstring = False
    for line in lines:
        if not in_func:
            if f"def {func_name}" in line:
                in_func = True
        else:
            if line.startswith("def ") and not line.startswith(f"def {func_name}"):
                break
            stripped = line.strip()
            # Rastrear docstrings
            if not in_docstring:
                count = stripped.count('\"\"\"')
                if count == 1:
                    in_docstring = True
                    continue
                elif count >= 2:
                    continue
            else:
                if stripped.count('\"\"\"') >= 1:
                    in_docstring = False
                continue
            if stripped and not stripped.startswith("#"):
                body_lines.append(line)
    return body_lines


def _has_broken_import(source: str, module_name: str) -> bool:
    """Verifica si un source tiene 'from X import' o 'import X' para un modulo."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if module_name in alias.name:
                    return True
        elif isinstance(node, ast.ImportFrom):
            if node.module and module_name in node.module:
                return True
    return False


class TestPlannerClean(unittest.TestCase):
    """Test 1: planner.py sin select_model."""

    def test_no_select_model_import(self):
        """planner.py no importa select_model del router."""
        source = _read_source("core/planner.py")
        self.assertFalse(
            _has_broken_import(source, "select_model"),
            "planner.py aun importa select_model (eliminado en v7)"
        )

    def test_no_pool_or_providers(self):
        """planner.py no importa pool ni providers."""
        source = _read_source("core/planner.py")
        self.assertFalse(_has_broken_import(source, "pool"))
        self.assertFalse(_has_broken_import(source, "providers"))


class TestOrchestratorClean(unittest.TestCase):
    """Test 2: orchestrator.py sin provider_manager."""

    def test_no_provider_manager_import(self):
        """orchestrator.py no importa provider_manager."""
        source = _read_source("core/orchestrator.py")
        self.assertFalse(
            _has_broken_import(source, "providers"),
            "orchestrator.py aun importa providers (eliminado en v7)"
        )

    def test_no_pool_import(self):
        """orchestrator.py no importa pool."""
        source = _read_source("core/orchestrator.py")
        self.assertFalse(_has_broken_import(source, "pool"))


class TestAppClean(unittest.TestCase):
    """Test 3-4: app.py sin imports CRASH."""

    def test_no_pool_top_level(self):
        """app.py no tiene 'from core.pool import pool' a nivel top-level."""
        source = _read_source("interface/app_apa.py")
        tree = ast.parse(source)
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if "pool" in node.module and node.level == 0:
                    # Solo chequear imports de core.pool (no itertools, etc.)
                    if node.module.startswith("core.pool"):
                        self.fail(f"app.py linea {node.lineno}: 'from {node.module}' sigue existiendo")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("core.pool"):
                        self.fail(f"app.py linea {node.lineno}: 'import {alias.name}' sigue existiendo")

    def test_no_price_estimator_top_level(self):
        """app.py no tiene 'from core.price_estimator import' a nivel top-level."""
        source = _read_source("interface/app_apa.py")
        tree = ast.parse(source)
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if "price_estimator" in node.module:
                    self.fail(f"app.py linea {node.lineno}: 'from {node.module}' sigue existiendo")

    def test_no_provider_manager_top_level(self):
        """app.py no tiene 'from core.providers import provider_manager' a nivel top-level."""
        source = _read_source("interface/app_apa.py")
        tree = ast.parse(source)
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if "providers" in node.module and "core.providers" in node.module:
                    self.fail(f"app.py linea {node.lineno}: 'from {node.module}' sigue existiendo")


class TestCorrectorClean(unittest.TestCase):
    """Test 4: corrector.py sin provider_manager ni select_model."""

    def test_no_provider_manager(self):
        """corrector.py no importa provider_manager."""
        source = _read_source("agents/corrector.py")
        self.assertFalse(_has_broken_import(source, "providers"))

    def test_no_select_model(self):
        """corrector.py no importa select_model."""
        source = _read_source("agents/corrector.py")
        self.assertFalse(_has_broken_import(source, "select_model"))


class TestDocumenterClean(unittest.TestCase):
    """Test 5: documenter.py sin price_estimator."""

    def test_no_price_estimator(self):
        """documenter.py no importa price_estimator."""
        source = _read_source("agents/documenter.py")
        self.assertFalse(
            _has_broken_import(source, "price_estimator"),
            "documenter.py aun importa price_estimator (eliminado en v7)"
        )


class TestAppPriceSystem(unittest.TestCase):
    """Test 6: PricingService.get_model_price funciona sin provider_manager."""

    @unittest.skip(
        "test obsoleto: _get_model_price_details fue reemplazado por "
        "PricingService.get_model_price (interface/app/pricing.py). "
        "El fallback a router._estimate_cost_usd ya no aplica en la "
        "arquitectura modular; el pricing usa provider_manager y, si no "
        "disponible, retorna 0.0. Validar en tests de pricing específicos."
    )
    def test_price_fallback_to_router(self):
        """Si MB no disponible, usa _estimate_cost_usd del router."""
        source = _read_source("interface/app_apa.py")
        body = _get_function_body_lines(source, "_get_model_price_details")
        for line in body:
            if "provider_manager" in line:
                self.fail(f"_get_model_price_details aun usa provider_manager: {line}")
            if "estimate_price_details" in line:
                self.fail(f"_get_model_price_details aun usa estimate_price_details: {line}")
        # Verificar que si usa _estimate_cost_usd como fallback
        uses_router_estimate = any("_estimate_cost_usd" in l for l in body)
        self.assertTrue(uses_router_estimate,
                        "_get_model_price_details deberia usar _estimate_cost_usd como fallback")


class TestAppMaturityUsesCallLlm(unittest.TestCase):
    """Test 7: evaluate_with_llm usa call_llm, no pool."""

    def test_maturity_no_pool_refs(self):
        """evaluate_with_llm (en sdd_maturity.py) no referencia pool ni providers."""
        source = _read_source("core/sdd_maturity.py")
        body = _get_function_body_lines(source, "evaluate_with_llm")
        for line in body:
            for bad in ["_global_pool", "provider_manager",
                        "_find_pool_entry", "_get_next_maturity",
                        "_call_maturity_direct", "_sync_health"]:
                if bad in line:
                    self.fail(f"evaluate_with_llm aun referencia {bad}: {line}")
        # Verificar que usa call_llm
        uses_call_llm = any("call_llm(" in l for l in body)
        self.assertTrue(uses_call_llm,
                        "evaluate_with_llm deberia usar call_llm()")


class TestAppEndpointsNoCrash(unittest.TestCase):
    """Test 8: endpoints deprecados retornan JSON sin crash."""

    def test_no_global_pool_in_pool_endpoint(self):
        """/health/pool no referencia _global_pool."""
        source = _read_source("interface/app_apa.py")
        lines = source.split("\n")
        in_endpoint = False
        for line in lines:
            if '@app.get("/health/pool")' in line or '"/health/pool"' in line:
                in_endpoint = True
            elif in_endpoint and '@app.' in line:
                break
            elif in_endpoint and "_global_pool" in line:
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    self.fail(f"/health/pool aun usa _global_pool: {line}")

    def test_no_providers_in_health_providers(self):
        """/health/providers no usa provider_manager en codigo ejecutable."""
        source = _read_source("interface/app_apa.py")
        lines = source.split("\n")
        in_endpoint = False
        in_docstring = False
        for line in lines:
            if '@app.get("/health/providers")' in line:
                in_endpoint = True
            elif in_endpoint and '@app.' in line:
                break
            elif in_endpoint:
                stripped = line.strip()
                # Rastrear docstrings: toggle al encontrar triple quotes
                if '"""' in stripped:
                    in_docstring = not in_docstring
                    continue
                if in_docstring:
                    continue
                if stripped and not stripped.startswith("#") and "provider_manager" in stripped:
                    self.fail(f"/health/providers aun usa provider_manager: {line}")

    def test_no_providers_in_health_check(self):
        """/health no usa provider_manager ni model_health en codigo ejecutable."""
        source = _read_source("interface/app_apa.py")
        lines = source.split("\n")
        in_endpoint = False
        in_docstring = False
        for line in lines:
            if '@app.get("/health")' in line and 'providers' not in line:
                in_endpoint = True
            elif in_endpoint and '@app.' in line:
                break
            elif in_endpoint:
                stripped = line.strip()
                if '"""' in stripped:
                    in_docstring = not in_docstring
                    continue
                if in_docstring:
                    continue
                if stripped and not stripped.startswith("#"):
                    for bad in ["provider_manager", "model_health", "get_diagnostic_info"]:
                        if bad in stripped:
                            self.fail(f"/health aun usa {bad}: {line}")


if __name__ == "__main__":
    unittest.main(verbosity=2)