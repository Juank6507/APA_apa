# apa/core/assembly_validator.py
"""
AssemblyValidator — Validación de código ensamblado/integrado.

Extraído de assembler.py v4.3 para uso independiente por SemiAutoAgent v3.0.
Proporciona validación en 3 niveles: sintaxis, imports, ejecución.

También incluye la detección automática del nivel de validación.
"""

import sys
import os
import ast
import logging
import tempfile
import subprocess
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class ValidationMode(Enum):
    """Niveles de validación para código ensamblado."""
    SYNTAX = "syntax"
    IMPORT = "import"
    EXECUTE = "execute"
    AUTO = "auto"


class AssemblyValidator:
    """Validador de código ensamblado/integrado.
    
    Extraído de Assembler.validate() y Assembler._detect_validation_mode()
    en assembler.py v4.3 para desacoplar la validación del ensamblaje mecánico.
    
    Modos de validación:
    - SYNTAX: Solo verifica que el código parsea con ast.parse()
    - IMPORT: Verifica sintaxis + que los imports se pueden resolver
    - EXECUTE: Ejecuta el código en un subprocess con timeout
    - AUTO: Detecta automáticamente el nivel apropiado
    """

    # Indicadores de tests pesados que requieren solo IMPORT (no EXECUTE)
    HEAVY_TEST_INDICATORS = [
        "NASConnector", "correction_loop", "call_llm", "subprocess.run",
        "unittest", "pytest", "test_", "_test(", "logging.basicConfig",
    ]

    @staticmethod
    def detect_validation_mode(content: str) -> ValidationMode:
        """Detecta automáticamente el nivel de validación apropiado.
        
        - Si el archivo tiene if __name__ == "__main__" con tests pesados → IMPORT
        - Si tiene if __name__ == "__main__" sin tests pesados → EXECUTE  
        - Si no tiene if __name__ → IMPORT
        
        Args:
            content: Contenido del archivo a validar.
            
        Returns:
            ValidationMode recomendado.
        """
        if "__name__" in content and "__main__" in content:
            for indicator in AssemblyValidator.HEAVY_TEST_INDICATORS:
                if indicator in content:
                    return ValidationMode.IMPORT
            return ValidationMode.EXECUTE
        return ValidationMode.IMPORT

    @staticmethod
    def validate(
        content: str,
        script_path: str = None,
        validation_mode: str = ValidationMode.AUTO,
    ) -> dict:
        """Valida el contenido ensamblado/integrado.
        
        Args:
            content: Código Python a validar.
            script_path: Ruta del script (para logging, no obligatorio).
            validation_mode: Nivel de validación (SYNTAX, IMPORT, EXECUTE, AUTO).
            
        Returns:
            Dict con claves:
            - success (bool): True si la validación pasó
            - output (str): Mensaje de resultado o error
            - returncode (int): 0 si OK, >0 si error
        """
        if validation_mode == ValidationMode.AUTO or validation_mode == "auto":
            validation_mode = AssemblyValidator.detect_validation_mode(content)
        
        # Normalizar a enum si viene como string
        if isinstance(validation_mode, str):
            try:
                validation_mode = ValidationMode(validation_mode)
            except ValueError:
                validation_mode = ValidationMode.SYNTAX
        
        output = ""
        returncode = -1

        if validation_mode == ValidationMode.SYNTAX:
            try:
                ast.parse(content)
                output = "Validacion de sintaxis exitosa."
                returncode = 0
            except SyntaxError as e:
                output = f"Error de sintaxis linea {e.lineno}: {e.msg}"
                returncode = 1

        elif validation_mode == ValidationMode.IMPORT:
            import importlib.util
            with tempfile.NamedTemporaryFile(
                mode='w', suffix='.py', delete=False, encoding='utf-8'
            ) as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            try:
                spec = importlib.util.spec_from_file_location(
                    "_validation_module", tmp_path
                )
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                output = "Imports validados correctamente."
                returncode = 0
            except Exception as e:
                output = f"Error al importar: {e}"
                returncode = 1
            finally:
                os.unlink(tmp_path)

        elif validation_mode == ValidationMode.EXECUTE:
            with tempfile.NamedTemporaryFile(
                mode='w', suffix='.py', delete=False, encoding='utf-8'
            ) as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            try:
                result = subprocess.run(
                    [sys.executable, tmp_path],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                output = result.stdout
                if result.stderr:
                    output += "\n" + result.stderr if result.stdout else result.stderr
                returncode = result.returncode
            except subprocess.TimeoutExpired:
                output = "Timeout: la ejecución superó 10 segundos."
                returncode = 1
            finally:
                os.unlink(tmp_path)

        return {"success": returncode == 0, "output": output, "returncode": returncode}
