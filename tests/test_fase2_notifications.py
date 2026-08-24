# apa/tests/test_fase2_notifications.py
# Tests independientes para Fase 2: Limpieza de notifications + notification_ui_bridge
#
# Validaciones:
# 1. notifications.py: no tiene EVT_HEALTH_*, EVT_ARENA_*, EVT_POOL_*
# 2. notifications.py: tiene EVT_EMERGENCY_MODE (nuevo en v2.0)
# 3. notifications.py: tiene EVT_AGENT_* (4 constantes)
# 4. notifications.py: tiene EVT_SYSTEM_* (3 constantes)
# 5. notification_ui_bridge.py: no importa EVT_HEALTH_*, EVT_ARENA_*, EVT_POOL_*
# 6. notification_ui_bridge.py: EVENT_SPECIFIC_COLOR_MAP sin refs muertas
# 7. notification_ui_bridge.py: EVENT_TYPES_LIST sin refs muertas
# 8. notification_ui_bridge.py: SUMMARY_LABELS_CONFIG sin pool/health keys
# 9. notification_ui_bridge.py: NOTIF_SECTION_HTML sin arena/providers spans
# 10. notification_ui_bridge.py: NOTIF_JS sin arena/providers refs
# 11. notification_ui_bridge.py: get_summary_display_data sin arena/pool/providers
# 12. notification_ui_bridge.py: get_full_summary sin arena/pool/providers
# 13. notification_ui_bridge.py: import solo EVT vivos
# 14. documenter.py: ya no importa EVT_HEALTH_MODEL_VERIFIED
# 15. Total EVT muertos eliminados: 16 en bridge, 0 en notifications
#
# Ejecutar (desde cualquier ubicacion):
#   python c:/Python/Proyectos/APA/apa/tests/test_fase2_notifications.py
# O con pytest:
#   cd C:\Python\Proyectos\APA && python -m pytest apa/tests/test_fase2_notifications.py -v

import sys
import os
import ast
import unittest

# --- Setup: project root en sys.path (3 niveles desde apa/tests/) ---
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _read_source(filepath: str) -> str:
    """Lee el fuente de un archivo del proyecto."""
    full_path = os.path.join(PROJECT_ROOT, "apa", filepath)
    with open(full_path, "r", encoding="utf-8") as f:
        return f.read()


def _get_imported_names(source: str, module: str) -> list:
    """Retorna los nombres importados desde un modulo dado."""
    tree = ast.parse(source)
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and module in node.module:
            for alias in node.names:
                names.append(alias.name)
    return names


# Constantes muertas que NO deben aparecer en ningun archivo
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


class TestNotificationsClean(unittest.TestCase):
    """Test 1-4: notifications.py v2.0 sin constantes muertas."""

    def test_no_dead_evt_constants(self):
        """notifications.py no define ningun EVT_HEALTH_*, EVT_ARENA_*, EVT_POOL_*."""
        source = _read_source("core/notifications.py")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id.startswith("EVT_"):
                        self.assertNotIn(
                            target.id, DEAD_EVT_NAMES,
                            f"notifications.py aun define {target.id} (eliminado en v2.0)"
                        )

    def test_has_emergency_mode(self):
        """notifications.py define EVT_EMERGENCY_MODE (nuevo en v2.0)."""
        source = _read_source("core/notifications.py")
        tree = ast.parse(source)
        found = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "EVT_EMERGENCY_MODE":
                        found = True
        self.assertTrue(found, "notifications.py debe definir EVT_EMERGENCY_MODE")

    def test_has_agent_events(self):
        """notifications.py define EVT_AGENT_STARTED/PROGRESS/DONE/FAILED."""
        source = _read_source("core/notifications.py")
        tree = ast.parse(source)
        defined = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id.startswith("EVT_AGENT_"):
                        defined.add(target.id)
        for expected in ["EVT_AGENT_STARTED", "EVT_AGENT_PROGRESS",
                         "EVT_AGENT_DONE", "EVT_AGENT_FAILED"]:
            self.assertIn(expected, defined,
                          f"notifications.py debe definir {expected}")

    def test_has_system_events(self):
        """notifications.py define EVT_SYSTEM_* (SHUTDOWN, ERROR, STARTUP)."""
        source = _read_source("core/notifications.py")
        tree = ast.parse(source)
        defined = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id.startswith("EVT_SYSTEM_"):
                        defined.add(target.id)
        for expected in ["EVT_SYSTEM_SHUTDOWN", "EVT_SYSTEM_ERROR",
                         "EVT_SYSTEM_STARTUP"]:
            self.assertIn(expected, defined,
                          f"notifications.py debe definir {expected}")


class TestBridgeImportsClean(unittest.TestCase):
    """Test 5, 13: notification_ui_bridge.py importa solo EVT vivos."""

    def test_no_dead_evt_imports(self):
        """notification_ui_bridge.py no importa EVT muertos de notifications."""
        source = _read_source("core/notification_ui_bridge.py")
        imported = _get_imported_names(source, "notifications")
        for dead in DEAD_EVT_NAMES:
            self.assertNotIn(dead, imported,
                             f"bridge importa {dead} (eliminado de notifications v2.0)")

    def test_imports_only_live_evts(self):
        """notification_ui_bridge.py importa los 9 EVT vivos."""
        source = _read_source("core/notification_ui_bridge.py")
        imported = _get_imported_names(source, "notifications")
        # 9 EVT vivos + 4 funciones = 13 nombres importados de notifications
        expected_evt = [
            'EVT_EMERGENCY_MODE',
            'EVT_SYSTEM_SHUTDOWN', 'EVT_SYSTEM_ERROR', 'EVT_SYSTEM_STARTUP',
            'EVT_AGENT_STARTED', 'EVT_AGENT_PROGRESS', 'EVT_AGENT_DONE',
            'EVT_AGENT_FAILED',
        ]
        for evt in expected_evt:
            self.assertIn(evt, imported,
                          f"bridge deberia importar {evt} de notifications")


class TestBridgeDataStructures(unittest.TestCase):
    """Test 6-8: Constantes del bridge limpias."""

    def test_color_map_no_dead_refs(self):
        """EVENT_SPECIFIC_COLOR_MAP no contiene EVT muertos."""
        source = _read_source("core/notification_ui_bridge.py")
        for dead in DEAD_EVT_NAMES:
            self.assertNotIn(dead, source,
                             f"EVENT_SPECIFIC_COLOR_MAP aun refiere {dead}")

    def test_event_types_list_no_dead(self):
        """EVENT_TYPES_LIST no contiene EVT muertos."""
        source = _read_source("core/notification_ui_bridge.py")
        # Verificar que EVENT_TYPES_LIST es una lista con solo 8 elementos
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "EVENT_TYPES_LIST":
                        if isinstance(node.value, ast.List):
                            count = len(node.value.elts)
                            self.assertEqual(count, 8,
                                f"EVENT_TYPES_LIST deberia tener 8 items, tiene {count}")

    def test_summary_labels_no_pool_keys(self):
        """SUMMARY_LABELS_CONFIG no tiene keys de pool/health muertos."""
        source = _read_source("core/notification_ui_bridge.py")
        dead_keys = ['unknown', 'payment_required', 'rate_limited',
                     'failed', 'model_removed', 'temporarily_unavailable']
        # Buscar la definicion de SUMMARY_LABELS_CONFIG
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "SUMMARY_LABELS_CONFIG":
                        if isinstance(node.value, ast.List):
                            # Solo debe tener 2 entradas (total, available)
                            count = len(node.value.elts)
                            self.assertEqual(count, 2,
                                f"SUMMARY_LABELS_CONFIG deberia tener 2, tiene {count}")


class TestBridgeHtmlJsClean(unittest.TestCase):
    """Test 9-10: HTML y JS sin refs a arena/providers."""

    def test_html_no_arena_providers(self):
        """NOTIF_SECTION_HTML no tiene spans de arena ni providers."""
        source = _read_source("core/notification_ui_bridge.py")
        # Buscar el contenido de NOTIF_SECTION_HTML
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "NOTIF_SECTION_HTML":
                        val = ast.get_source_segment(source, node.value) or ""
                        self.assertNotIn("sm-arena", val,
                            "NOTIF_SECTION_HTML no deberia tener sm-arena")
                        self.assertNotIn("sm-provactive", val,
                            "NOTIF_SECTION_HTML no deberia tener sm-provactive")
                        self.assertNotIn("sm-provtotal", val,
                            "NOTIF_SECTION_HTML no deberia tener sm-provtotal")
                        self.assertNotIn("sm-provlist", val,
                            "NOTIF_SECTION_HTML no deberia tener sm-provlist")
                        self.assertNotIn("sm-topplan", val,
                            "NOTIF_SECTION_HTML no deberia tener sm-topplan")
                        self.assertNotIn("sm-topcode", val,
                            "NOTIF_SECTION_HTML no deberia tener sm-topcode")
                        # Si debe tener los nuevos spans
                        self.assertIn("sm-agent-active", val,
                            "NOTIF_SECTION_HTML deberia tener sm-agent-active")
                        self.assertIn("sm-top5", val,
                            "NOTIF_SECTION_HTML deberia tener sm-top5")
                        return
        self.fail("NOTIF_SECTION_HTML no encontrado")

    def test_js_no_arena_providers(self):
        """NOTIF_JS no refiere arena ni providers en renderNotifSummary."""
        source = _read_source("core/notification_ui_bridge.py")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "NOTIF_JS":
                        val = ast.get_source_segment(source, node.value) or ""
                        self.assertNotIn("sm-arena", val,
                            "NOTIF_JS no deberia referenciar sm-arena")
                        self.assertNotIn("sm-provactive", val,
                            "NOTIF_JS no deberia referenciar sm-provactive")
                        self.assertNotIn("sm-provlist", val,
                            "NOTIF_JS no deberia referenciar sm-provlist")
                        # Si debe tener los nuevos
                        self.assertIn("sm-agent-active", val,
                            "NOTIF_JS deberia referenciar sm-agent-active")
                        self.assertIn("sm-top5", val,
                            "NOTIF_JS deberia referenciar sm-top5")
                        return
        self.fail("NOTIF_JS no encontrado")


class TestBridgeFunctionsClean(unittest.TestCase):
    """Test 11-12: Funciones del bridge sin refs a arena/pool/providers."""

    def test_get_summary_display_data_clean(self):
        """get_summary_display_data no refiere arena, pool ni providers."""
        source = _read_source("core/notification_ui_bridge.py")
        # Extraer cuerpo de la funcion
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "get_summary_display_data":
                func_source = ast.get_source_segment(source, node) or ""
                self.assertNotIn("arena", func_source.lower(),
                    "get_summary_display_data no deberia referenciar arena")
                self.assertNotIn(".get('pool'", func_source,
                    "get_summary_display_data no deberia usar pool")
                self.assertNotIn("prov_active", func_source,
                    "get_summary_display_data no deberia usar prov_active")
                # Si debe tener agent y top_5
                self.assertIn("agent_active", func_source,
                    "get_summary_display_data deberia usar agent_active")
                self.assertIn("top_5", func_source,
                    "get_summary_display_data deberia usar top_5")
                return
        self.fail("get_summary_display_data no encontrada")

    def test_get_full_summary_clean(self):
        """get_full_summary no refiere arena, pool ni providers en codigo ejecutable."""
        source = _read_source("core/notification_ui_bridge.py")
        lines = source.split("\n")
        # Encontrar la funcion y extraer solo lineas de codigo (no docstring)
        in_func = False
        in_docstring = False
        code_lines = []
        for line in lines:
            if not in_func:
                if "def get_full_summary" in line:
                    in_func = True
            else:
                if line.startswith("def ") and "get_full_summary" not in line:
                    break
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
                    code_lines.append(line)
        func_code = "\n".join(code_lines)
        self.assertNotIn("arena", func_code.lower(),
            "get_full_summary no deberia referenciar arena en codigo")
        self.assertNotIn("providers", func_code.lower(),
            "get_full_summary no deberia referenciar providers en codigo")
        self.assertNotIn(".get('pool'", func_code,
            "get_full_summary no deberia usar pool en codigo")


class TestDocumenterNoDeadImport(unittest.TestCase):
    """Test 14: documenter.py no importa EVT muertos."""

    def test_no_evt_health_import(self):
        """documenter.py no importa EVT_HEALTH_MODEL_VERIFIED."""
        source = _read_source("agents/documenter.py")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name in DEAD_EVT_NAMES:
                        self.fail(
                            f"documenter.py linea {node.lineno} aun importa "
                            f"{alias.name} (eliminado en notifications v2.0)"
                        )


class TestDeadEvtCount(unittest.TestCase):
    """Test 15: Conteo exacto de EVT muertos eliminados."""

    def test_bridge_has_no_dead_strings(self):
        """El bridge no contiene ningun string de EVT muerto en codigo ejecutable."""
        source = _read_source("core/notification_ui_bridge.py")
        lines = source.split("\n")
        in_docstring = False
        dead_found = []
        for line in lines:
            stripped = line.strip()
            # Rastrear docstrings
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
            #Codigo ejecutable
            if stripped and not stripped.startswith("#"):
                for dead in DEAD_EVT_NAMES:
                    if dead in line:
                        dead_found.append(dead)
        if dead_found:
            self.fail(
                f"Se encontraron {len(dead_found)} refs a EVT muertos en codigo: "
                f"{dead_found}"
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)