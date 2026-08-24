# apa/tests/test_fase3_fase4_cleanup.py
# Tests independientes para Fase 3 + Fase 4: Validacion post-limpieza
#
# Validaciones:
# 1. Los 6 modulos huérfanos NO existen en el filesystem
# 2. Ningun .py productivo importa los modulos muertos
# 3. Ningun test (excepto test_fase*) importa los modulos muertos
# 4. Los tests de fases (test_fase0/1/2) siguen existiendo
# 5. router.py no tiene imports a modulos muertos
# 6. app.py no tiene imports a modulos muertos
# 7. corrector.py no tiene imports a modulos muertos
# 8. documenter.py no tiene imports a modulos muertos
# 9. planner.py no tiene imports a modulos muertos
# 10. orchestrator.py no tiene imports a modulos muertos
#
# EJECUTAR DESPUES de cleanup_fase3_fase4.py:
#   python c:/Python/Proyectos/APA/apa/tests/test_fase3_fase4_cleanup.py
# O con pytest:
#   cd C:\Python\Proyectos\APA && python -m pytest apa/tests/test_fase3_fase4_cleanup.py -v

import sys
import os
import ast
import unittest

# --- Setup: project root en sys.path (3 niveles desde apa/tests/) ---
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# ============================================================================
# Modulos muertos eliminados en Fase 3
# ============================================================================

DEAD_MODULES = [
    "core/pool.py",
    "core/providers.py",
    "core/model_health.py",
    "core/arena_fetcher.py",
    "core/price_estimator.py",
    "core/normalizer.py",
]

DEAD_IMPORT_KEYWORDS = [
    "from core.pool", "import core.pool",
    "from core.providers", "import core.providers",
    "from core.model_health", "import core.model_health",
    "from core.arena_fetcher", "import core.arena_fetcher",
    "from core.price_estimator", "import core.price_estimator",
    "from core.normalizer", "import core.normalizer",
]

# Directorios a excluir del escaneo
SKIP_DIRS = {"__pycache__", ".git", ".venv", "venv", "node_modules", "scripts"}


def _file_exists(rel_path: str) -> bool:
    return os.path.isfile(os.path.join(PROJECT_ROOT, "apa", rel_path))


def _read_source(rel_path: str) -> str:
    full_path = os.path.join(PROJECT_ROOT, "apa", rel_path)
    with open(full_path, "r", encoding="utf-8") as f:
        return f.read()


def _scan_py_files(directory: str, skip_test_fases: bool = True) -> list:
    """Retorna lista de rutas relativas a PROJECT_ROOT/apa/ de todos los .py."""
    result = []
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fname in files:
            if not fname.endswith(".py"):
                continue
            if skip_test_fases and fname.startswith("test_fase"):
                continue
            full = os.path.join(root, fname)
            rel = os.path.relpath(full, os.path.join(PROJECT_ROOT, "apa"))
            result.append(rel)
    return result


def _has_dead_import(source: str) -> list:
    """Retorna lista de lineas con imports a modulos muertos (codigo ejecutable, no docstrings)."""
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


class TestOrphanModulesDeleted(unittest.TestCase):
    """Test 1: Los 6 modulos huérfanos no existen."""

    def test_all_orphans_deleted(self):
        """Los 6 modulos huérfanos deben haber sido eliminados."""
        for mod in DEAD_MODULES:
            exists = _file_exists(mod)
            self.assertFalse(exists,
                f"{mod} aun existe (deberia haber sido eliminado en Fase 3)")


class TestNoDeadImportsInProduction(unittest.TestCase):
    """Test 2: Ningun .py productivo importa modulos muertos."""

    def test_scan_all_production_files(self):
        """Escanea todos los .py productivos buscando imports muertos."""
        apa_dir = os.path.join(PROJECT_ROOT, "apa")
        py_files = _scan_py_files(apa_dir, skip_test_fases=True)

        problems = []
        for rel_path in py_files:
            # Solo escanear directorios core/, agents/, interface/, config/
            top_dir = rel_path.split(os.sep)[0] if os.sep in rel_path else rel_path.split("/")[0]
            if top_dir not in ("core", "agents", "interface", "config"):
                continue
            try:
                source = _read_source(rel_path)
            except FileNotFoundError:
                continue
            hits = _has_dead_import(source)
            for lineno, kw in hits:
                problems.append(f"  {rel_path}:{lineno} -> {kw}")

        if problems:
            self.fail(
                f"Se encontraron {len(problems)} imports a modulos muertos:\n"
                + "\n".join(problems)
            )


class TestNoDeadImportsInTests(unittest.TestCase):
    """Test 3: Ningun test (excepto test_fase*) importa modulos muertos."""

    def test_scan_all_test_files(self):
        """Escanea tests/ buscando imports a modulos muertos."""
        tests_dir = os.path.join(PROJECT_ROOT, "apa", "tests")
        if not os.path.isdir(tests_dir):
            self.skipTest("Directorio tests/ no encontrado")

        problems = []
        for fname in sorted(os.listdir(tests_dir)):
            if not fname.endswith(".py"):
                continue
            if fname.startswith("test_fase"):
                continue
            rel_path = os.path.join("tests", fname)
            try:
                source = _read_source(rel_path)
            except FileNotFoundError:
                continue
            hits = _has_dead_import(source)
            for lineno, kw in hits:
                problems.append(f"  {rel_path}:{lineno} -> {kw}")

        if problems:
            self.fail(
                f"Se encontraron {len(problems)} imports a modulos muertos en tests:\n"
                + "\n".join(problems)
            )


class TestFaseTestsStillExist(unittest.TestCase):
    """Test 4: Los tests de fases siguen existiendo."""

    def test_fase0_test_exists(self):
        self.assertTrue(_file_exists("tests/test_fase0_emergency.py"),
            "test_fase0_emergency.py fue eliminado accidentalmente")

    def test_fase1_test_exists(self):
        self.assertTrue(_file_exists("tests/test_fase1_critical.py"),
            "test_fase1_critical.py fue eliminado accidentalmente")

    def test_fase2_test_exists(self):
        self.assertTrue(_file_exists("tests/test_fase2_notifications.py"),
            "test_fase2_notifications.py fue eliminado accidentalmente")

    def test_this_test_exists(self):
        self.assertTrue(_file_exists("tests/test_fase3_fase4_cleanup.py"))


class TestCoreFilesClean(unittest.TestCase):
    """Test 5-10: Archivos core individuales sin imports muertos."""

    def _assert_clean(self, rel_path: str):
        source = _read_source(rel_path)
        hits = _has_dead_import(source)
        if hits:
            lines = "\n".join(f"    linea {ln}: {kw}" for ln, kw in hits)
            self.fail(f"{rel_path} tiene imports muertos:\n{lines}")

    def test_router_clean(self):
        self._assert_clean("core/router.py")

    def test_app_clean(self):
        self._assert_clean("interface/app.py")

    def test_corrector_clean(self):
        self._assert_clean("agents/corrector.py")

    def test_documenter_clean(self):
        self._assert_clean("agents/documenter.py")

    def test_planner_clean(self):
        self._assert_clean("core/planner.py")

    def test_orchestrator_clean(self):
        self._assert_clean("core/orchestrator.py")


class TestNoSelectModelOrProviderManager(unittest.TestCase):
    """Test extra: Ningun archivo productivo usa select_model ni provider_manager."""

    def test_no_select_model_in_production(self):
        """Ningun .py productivo (no tests) referencia select_model."""
        apa_dir = os.path.join(PROJECT_ROOT, "apa")
        py_files = _scan_py_files(apa_dir, skip_test_fases=True)

        problems = []
        for rel_path in py_files:
            top_dir = rel_path.split(os.sep)[0] if os.sep in rel_path else rel_path.split("/")[0]
            if top_dir not in ("core", "agents", "interface", "config"):
                continue
            try:
                source = _read_source(rel_path)
            except FileNotFoundError:
                continue

            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    for alias in node.names:
                        if "select_model" in alias.name:
                            problems.append(f"  {rel_path}:{node.lineno} -> from {node.module} import {alias.name}")
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if "select_model" in alias.name:
                            problems.append(f"  {rel_path}:{node.lineno} -> import {alias.name}")

        if problems:
            self.fail(f"Imports a select_model encontrados:\n" + "\n".join(problems))

    def test_no_provider_manager_in_production(self):
        """Ningun .py productivo referencia provider_manager en imports."""
        apa_dir = os.path.join(PROJECT_ROOT, "apa")
        py_files = _scan_py_files(apa_dir, skip_test_fases=True)

        problems = []
        for rel_path in py_files:
            top_dir = rel_path.split(os.sep)[0] if os.sep in rel_path else rel_path.split("/")[0]
            if top_dir not in ("core", "agents", "interface", "config"):
                continue
            try:
                source = _read_source(rel_path)
            except FileNotFoundError:
                continue

            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    if node.module and "provider" in node.module.lower():
                        for alias in node.names:
                            if "provider_manager" in alias.name:
                                problems.append(
                                    f"  {rel_path}:{node.lineno} -> "
                                    f"from {node.module} import {alias.name}"
                                )

        if problems:
            self.fail(f"Imports a provider_manager encontrados:\n" + "\n".join(problems))


if __name__ == "__main__":
    unittest.main(verbosity=2)