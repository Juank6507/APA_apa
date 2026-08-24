# apa/core/validator.py
import sys
import os
import ast
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
try:
    from config.settings import settings
except ImportError:
    class _DummySettings:
        log_level = 'INFO'
    settings = _DummySettings()

logger = logging.getLogger(__name__)
logger.setLevel(getattr(logging, getattr(settings, 'log_level', 'INFO').upper(), logging.INFO))
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)


@dataclass
class ValidationResult:
    """Resultado de la validación en capas."""
    is_valid: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)
        self.is_valid = False
        logger.warning(f"Validation error: {msg}")

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)
        logger.info(f"Validation warning: {msg}")


# Módulos de la stdlib permitidos por defecto
ALLOWED_MODULES = {
    "sys", "os", "json", "math", "random", "datetime", "time",
    "collections", "itertools", "functools", "pathlib", "typing",
    "re", "string", "copy", "hashlib", "unicodedata", "inspect",
    "traceback", "io", "textwrap", "pprint", "enum", "dataclasses",
    "contextlib", "abc", "logging", "unittest", "ast"
}


class SyntaxCheck:
    """Verifica que el código sea sintácticamente válido."""
    def run(self, code: str, result: ValidationResult) -> None:
        try:
            ast.parse(code)
        except SyntaxError as e:
            result.add_error(f"SyntaxError: {e}")


class ImportCheck:
    """Verifica que los módulos importados estén disponibles o sean seguros."""
    def __init__(self):
        self.allowed = ALLOWED_MODULES

    def _is_module_available(self, module_name: str) -> bool:
        """Verifica si el módulo está en la lista permitida o se puede importar."""
        if module_name in self.allowed:
            return True
        try:
            import importlib
            importlib.import_module(module_name)
            return True
        except (ImportError, ModuleNotFoundError):
            return False

    def run(self, code: str, result: ValidationResult) -> None:
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return  # SyntaxCheck ya capturará el error

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module_name = alias.name.split('.')[0]
                    if not self._is_module_available(module_name):
                        # A2d: Convertido de error a advertencia para permitir imports de módulos locales del proyecto
                        result.add_warning(f"Módulo no disponible localmente: {module_name} (se espera que exista en el NAS)")
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    module_name = node.module.split('.')[0]
                    if not self._is_module_available(module_name):
                        # A2d: Convertido de error a advertencia
                        result.add_warning(f"Módulo no disponible localmente: {module_name} (se espera que exista en el NAS)")


class SecurityCheck:
    """Bloquea llamadas peligrosas o ejecución dinámica no controlada."""
    DANGEROUS_CALLS = {"eval", "exec", "compile", "os.system", "os.popen", 
                       "subprocess.call", "subprocess.run", "subprocess.Popen",
                       "__import__", "globals", "locals", "execfile"}

    def run(self, code: str, result: ValidationResult) -> None:
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return

        for node in ast.walk(tree):
            # Verificar llamadas a funciones peligrosas
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in self.DANGEROUS_CALLS:
                    result.add_error(f"Llamada peligrosa detectada: {node.func.id}")
                elif isinstance(node.func, ast.Attribute):
                    attr_name = node.func.attr
                    # Resolver nombre completo: os.system, subprocess.call, etc.
                    if isinstance(node.func.value, ast.Name):
                        qualified = f"{node.func.value.id}.{attr_name}"
                    else:
                        qualified = attr_name
                    if qualified in self.DANGEROUS_CALLS or attr_name in self.DANGEROUS_CALLS:
                        result.add_error(f"Llamada peligrosa detectada: {qualified}")


def validate_code(code: str, task: dict) -> ValidationResult:
    """
    Ejecuta el pipeline de validación en capas sobre el código generado.
    Retorna ValidationResult con is_valid, errors y warnings.
    """
    result = ValidationResult()
    
    # Capa 1: Sintaxis
    SyntaxCheck().run(code, result)
    if not result.is_valid:
        return result
        
    # Capa 2: Imports (A2d: ahora usa advertencias en lugar de errores para módulos locales)
    ImportCheck().run(code, result)
    # Continuamos aunque haya warnings, ya que no invalidan la validación
    
    # Capa 3: Seguridad
    SecurityCheck().run(code, result)
    
    return result


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    
    print("=== PRUEBAS DE VALIDADOR (A2d) ===\n")
    
    # 1. Import de módulo local que no existe (debe pasar con advertencia)
    print("🔹 Prueba 1: Import de módulo local inexistente")
    code1 = "from utils.validators import algo"
    res1 = validate_code(code1, {})
    assert res1.is_valid, "Debería pasar con advertencia"
    assert any("Módulo no disponible localmente" in w for w in res1.warnings), "Debe generar advertencia"
    print("✅ PASÓ (con advertencia)")
    
    # 2. Import de módulo estándar sí disponible
    print("\n🔹 Prueba 2: Import de módulo estándar")
    code2 = "import sys; import json"
    res2 = validate_code(code2, {})
    assert res2.is_valid and len(res2.errors) == 0, "Import estándar debe pasar sin problemas"
    assert len(res2.warnings) == 0, "No debe haber advertencias para módulos stdlib"
    print("✅ PASÓ (limpio)")
    
    # 3. Código con llamada peligrosa (seguridad debe bloquear)
    print("\n🔹 Prueba 3: Llamada peligrosa")
    code3 = "import os; os.system('ls')"
    res3 = validate_code(code3, {})
    assert not res3.is_valid, "Seguridad debe seguir bloqueando"
    assert any("peligrosa" in e.lower() for e in res3.errors), "Debe reportar llamada peligrosa"
    print("✅ BLOQUEADO CORRECTAMENTE")
    
    # 4. SyntaxError
    print("\n🔹 Prueba 4: Sintaxis inválida")
    code4 = "def foo(\n  return True"
    res4 = validate_code(code4, {})
    assert not res4.is_valid, "SyntaxError debe invalidar"
    assert any("SyntaxError" in e for e in res4.errors), "Debe reportar SyntaxError"
    print("✅ BLOQUEADO CORRECTAMENTE")
    
    print("\n=== Todas las pruebas pasaron ===")