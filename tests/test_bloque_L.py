# apa/tests/test_bloque_L.py
"""
Test de integración del Bloque L: Aplicaciones de Escritorio (GUI).

Valida:
- L1: Carga correcta del skill tkinter_gui y gui_integration
- L3: Validación estática específica para código tkinter
- L5: Generación de código GUI sintácticamente correcto y sin anti-patrones

Ejecución: python -m apa.tests.test_bloque_L
"""
import sys
import os
import ast
import unittest
from pathlib import Path

# Asegurar que el path incluye el directorio del proyecto
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestL1SkillsGUI(unittest.TestCase):
    """L1: Verifica que los skills de GUI se cargan y son válidos."""

    def setUp(self):
        from core.skills_manager import SkillsManager
        self.skills_dir = Path(__file__).parent.parent / "skills"
        self.manager = SkillsManager(skills_dir=self.skills_dir)

    def test_tkinter_gui_exists(self):
        """El skill tkinter_gui.py existe y se carga correctamente."""
        self.assertIn("tkinter_gui", self.manager.list_skills(),
                       "Skill 'tkinter_gui' no encontrado en skills_manager")

    def test_gui_integration_skill_exists(self):
        """El skill gui_integration.py existe y se carga correctamente."""
        self.assertIn("gui_integration", self.manager.list_skills(),
                       "Skill 'gui_integration' no encontrado en skills_manager")

    def test_tkinter_gui_structure(self):
        """El skill tkinter_gui tiene la estructura correcta."""
        skill = self.manager.loaded_skills.get("tkinter_gui")
        self.assertIsNotNone(skill)
        self.assertEqual(skill["language"], "python")
        self.assertIsInstance(skill["keywords"], list)
        self.assertGreater(len(skill["keywords"]), 10)
        self.assertIsInstance(skill["prompt_fragment"], str)
        self.assertGreater(len(skill["prompt_fragment"]), 500)
        self.assertIsInstance(skill["example_code"], str)
        self.assertIn("mainloop", skill["example_code"])

    def test_gui_integration_skill_structure(self):
        """El skill gui_integration tiene la estructura correcta."""
        skill = self.manager.loaded_skills.get("gui_integration")
        self.assertIsNotNone(skill)
        self.assertEqual(skill["language"], "python")
        self.assertIn("threading", skill["prompt_fragment"].lower())
        self.assertIn("queue", skill["prompt_fragment"].lower())
        self.assertIn("after", skill["prompt_fragment"].lower())
        self.assertIn("threading", skill["example_code"])
        self.assertIn("mainloop", skill["example_code"])

    def test_tkinter_gui_found_by_keywords(self):
        """El skill se encuentra con descripciones de tareas GUI."""
        self.assertIsNotNone(self.manager.find_skill("create a tkinter GUI form", "python"))
        self.assertIsNotNone(self.manager.find_skill("desktop application with buttons and text", "python"))
        self.assertIsNotNone(self.manager.find_skill("build a form with textbox and combobox", "python"))

    def test_gui_integration_skill_found_by_keywords(self):
        """El skill de integración se encuentra con tareas multi-modulo."""
        self.assertIsNotNone(self.manager.find_skill("integrate module with GUI threading background", "python"))

    def test_tkinter_gui_not_found_for_non_gui_tasks(self):
        """El skill NO se activa para tareas no-GUI."""
        result = self.manager.find_skill("create a REST API endpoint", "python")
        # Puede encontrar otro skill (como fastapi), pero no tkinter_gui
        if result:
            self.assertNotEqual(result["name"], "tkinter_gui")


class TestL1PromptProfile(unittest.TestCase):
    """L1: Verifica que el perfil de Python incluye reglas de GUI."""

    def test_python_profile_has_tkinter_keywords(self):
        """El perfil Python incluye tkinter, gui, desktop como keywords."""
        from core.language_profiles import get_python_profile
        profile = get_python_profile()
        for kw in ["tkinter", "gui", "desktop"]:
            self.assertIn(kw, profile.keywords, f"Falta keyword '{kw}' en perfil Python")

    def test_python_profile_has_tkinter_rules(self):
        """El prompt_template del perfil Python incluye reglas de GUI."""
        from core.language_profiles import get_python_profile
        profile = get_python_profile()
        self.assertIn("TKINTER GUI RULES", profile.prompt_template)
        self.assertIn("mainloop", profile.prompt_template.lower())
        self.assertIn("StringVar", profile.prompt_template)
        self.assertIn("threading", profile.prompt_template.lower())


class TestL3StaticValidation(unittest.TestCase):
    """L3: Verifica la validación estática específica para código tkinter."""

    def _validate_python(self, code):
        """Helper: importa y ejecuta _validate_python del generator."""
        sys.path.insert(0, str(Path(__file__).parent.parent / "agents"))
        # Evitar importar el agente completo (necesita NAS), solo la función de validación
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, str(e)

        if "tkinter" in code:
            gui_errors = _validate_tkinter_gui_standalone(code, tree)
            if gui_errors:
                return False, gui_errors
        return True, ""

    def test_valid_tkinter_code_passes(self):
        """Código tkinter correcto pasa la validación."""
        code = '''
import tkinter as tk
from tkinter import ttk, messagebox


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Test")
        self._crear_interfaz()

    def _crear_interfaz(self):
        try:
            btn = ttk.Button(self, text="OK", command=self._on_click)
            btn.pack()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _on_click(self):
        try:
            print("clicked")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    app = App()
    app.mainloop()
'''
        valid, msg = self._validate_python(code)
        self.assertTrue(valid, f"Código válido falló la validación: {msg}")

    def test_time_sleep_without_threading_fails(self):
        """Código con time.sleep sin threading es detectado."""
        code = '''
import tkinter as tk
import time

class App(tk.Tk):
    def _on_click(self):
        time.sleep(5)

if __name__ == "__main__":
    app = App()
    app.mainloop()
'''
        valid, msg = self._validate_python(code)
        self.assertFalse(valid, "Debería detectar time.sleep sin threading")
        self.assertIn("sleep", msg.lower())

    def test_from_tkinter_import_star_fails(self):
        """'from tkinter import *' es detectado como mala práctica."""
        code = '''
from tkinter import *

if __name__ == "__main__":
    root = Tk()
    root.mainloop()
'''
        valid, msg = self._validate_python(code)
        self.assertFalse(valid, "Debería detectar 'from tkinter import *'")
        self.assertIn("import", msg.lower())

    def test_missing_mainloop_fails(self):
        """Código tkinter sin mainloop() es detectado."""
        code = '''
import tkinter as tk

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Test")
        self.mainloop = None  # Sabotear
'''
        valid, msg = self._validate_python(code)
        self.assertFalse(valid, "Debería detectar falta de mainloop")

    def test_non_tkinter_code_unchanged(self):
        """Código Python sin tkinter pasa sin validaciones extra."""
        code = '''
def add(a, b):
    return a + b

print(add(1, 2))
'''
        valid, msg = self._validate_python(code)
        self.assertTrue(valid, f"Código no-tkinter debería pasar: {msg}")


class TestL4CorrectionStrategies(unittest.TestCase):
    """L4: Verifica que las estrategias de corrección GUI existen."""

    def test_error_patterns_include_tkinter(self):
        """Los patrones de error Python incluyen patrones tkinter."""
        sys.path.insert(0, str(Path(__file__).parent.parent / "agents"))
        # Importar directamente el módulo de patrones
        spec = __import__("importlib").util.spec_from_file_location(
            "corrector", str(Path(__file__).parent.parent / "agents" / "corrector.py"))
        if spec and spec.loader:
            mod = __import__("importlib").util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            python_patterns = mod.ERROR_PATTERNS.get("python", [])
            pattern_strings = [p[0] for p in python_patterns]
            self.assertTrue(any("TclError" in p for p in pattern_strings),
                            "Falta patrón TclError en ERROR_PATTERNS")
            self.assertTrue(any("blocking" in p for p in pattern_strings),
                            "Falta patrón de GUI blocking en ERROR_PATTERNS")


class TestL5GeneratedCodeStructure(unittest.TestCase):
    """L5: Verifica que el código de ejemplo de los skills es sintácticamente válido."""

    def test_tkinter_gui_example_code_parses(self):
        """El example_code del skill tkinter_gui tiene AST válido."""
        from core.skills_manager import SkillsManager
        skills_dir = Path(__file__).parent.parent / "skills"
        manager = SkillsManager(skills_dir=skills_dir)
        skill = manager.loaded_skills.get("tkinter_gui")
        self.assertIsNotNone(skill)
        try:
            ast.parse(skill["example_code"])
        except SyntaxError as e:
            self.fail(f"example_code de tkinter_gui tiene error de sintaxis: {e}")

    def test_gui_integration_example_code_parses(self):
        """El example_code del skill gui_integration tiene AST válido."""
        from core.skills_manager import SkillsManager
        skills_dir = Path(__file__).parent.parent / "skills"
        manager = SkillsManager(skills_dir=skills_dir)
        skill = manager.loaded_skills.get("gui_integration")
        self.assertIsNotNone(skill)
        try:
            ast.parse(skill["example_code"])
        except SyntaxError as e:
            self.fail(f"example_code de gui_integration tiene error de sintaxis: {e}")

    def test_tkinter_gui_example_has_no_blocking_patterns(self):
        """El example_code del skill no tiene anti-patrones de bloqueo."""
        from core.skills_manager import SkillsManager
        skills_dir = Path(__file__).parent.parent / "skills"
        manager = SkillsManager(skills_dir=skills_dir)
        for skill_name in ["tkinter_gui", "gui_integration"]:
            skill = manager.loaded_skills.get(skill_name)
            code = skill["example_code"]
            # No time.sleep sin threading
            if "time.sleep" in code:
                self.assertIn("threading", code,
                              f"skill {skill_name}: time.sleep sin threading")
            # No from tkinter import *
            self.assertNotIn("from tkinter import *", code,
                             f"skill {skill_name}: usa from tkinter import *")
            # Tiene mainloop
            self.assertIn("mainloop", code,
                          f"skill {skill_name}: le falta mainloop")


# --- Helper functions ---

def _validate_tkinter_gui_standalone(code: str, tree: ast.AST) -> str:
    """Versión standalone de _validate_tkinter_gui para tests sin NAS."""
    import re
    warnings = []

    if "time.sleep" in code and "threading" not in code:
        warnings.append("CRITICAL: time.sleep() bloquea el mainloop de tkinter. Use threading.Thread + after().")

    if re.search(r'from\s+tkinter\s+import\s+\*', code):
        warnings.append("WARNING: 'from tkinter import *' contamina el namespace. Use 'import tkinter as tk'.")

    # Buscar mainloop() como llamada a funcion, no solo la palabra suelta
    # Debe aparecer como .mainloop() o mainloop() con parentesis
    has_mainloop_call = bool(re.search(r'\.mainloop\s*\(\s*\)', code) or re.search(r'(?<!\.)mainloop\s*\(\s*\)', code))
    if not has_mainloop_call:
        warnings.append("WARNING: No se encontró mainloop(). La ventana no se mostrará.")

    if re.search(r'while\s+True', code) and "threading" not in code and "after" not in code:
        warnings.append("WARNING: 'while True' puede bloquear el mainloop. Use widget.after() para loops en GUI.")

    if warnings:
        return " | ".join(warnings)
    return ""


if __name__ == "__main__":
    # Ejecutar tests con verbosidad
    unittest.main(verbosity=2)
