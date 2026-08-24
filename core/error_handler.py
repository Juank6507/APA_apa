# apa/core/error_handler.py
# Modulo unificado de gestion de errores — fusion de PromptTuner + ErrorClassifier
# v1.0 — Combina: deteccion de patrones (36), clasificacion de complejidad,
#          instrucciones de reparacion, seleccion de modelo, urgencia progresiva,
#          reglas extensibles via JSON, y compatibilidad hacia atras.
import re
import json
import logging
import os
import sys
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Optional, Any, List, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
try:
    from config.settings import settings
except ImportError:
    class _DummySettings:
        SIMPLE_MODEL = "qwen/qwen3-coder:free"
        COMPLEX_MODEL = "nim/meta/llama-3.1-70b-instruct"
        log_level = "INFO"
    settings = _DummySettings()

logger = logging.getLogger(__name__)
logger.setLevel(getattr(logging, getattr(settings, 'log_level', 'INFO').upper(), logging.INFO))
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)


class ErrorComplexity(Enum):
    """Clasificacion binaria de complejidad del error."""
    SIMPLE = "simple"
    COMPLEX = "complex"


@dataclass
class ErrorDiagnosis:
    """Resultado completo del analisis de un error."""
    error_name: str              # Nombre normalizado (ej: "SyntaxError", "unknown")
    complexity: ErrorComplexity  # SIMPLE o COMPLEX
    remediation: Optional[str]   # Instruccion detallada para el LLM (o None)
    suggested_model: str         # Identificador del modelo recomendado
    matched_pattern: str = ""    # El patrón regex que coincidió


# ─── Tabla maestra de patrones ───────────────────────────────────────────────
# Cada entrada: (regex, nombre_error, complejidad)
# Fusion completa de PromptTuner (33 patrones) + ErrorClassifier (3 exclusivos) = 36
_ERROR_PATTERNS: List[Tuple[str, str, ErrorComplexity]] = [
    # --- Excepciones nombradas (de PromptTuner + ErrorClassifier) ---
    (r"\b(SyntaxError)\b",                "SyntaxError",      ErrorComplexity.SIMPLE),
    (r"\b(IndentationError)\b",           "IndentationError", ErrorComplexity.SIMPLE),
    (r"\b(TabError)\b",                   "TabError",         ErrorComplexity.SIMPLE),
    (r"\b(ImportError)\b",                "ImportError",      ErrorComplexity.SIMPLE),
    (r"\b(ModuleNotFoundError)\b",        "ModuleNotFoundError", ErrorComplexity.SIMPLE),
    (r"\b(NameError)\b",                  "NameError",        ErrorComplexity.SIMPLE),
    (r"\b(AttributeError)\b",             "AttributeError",   ErrorComplexity.SIMPLE),
    (r"\b(TypeError)\b",                  "TypeError",        ErrorComplexity.SIMPLE),
    (r"\b(ValueError)\b",                 "ValueError",       ErrorComplexity.COMPLEX),
    (r"\b(KeyError)\b",                   "KeyError",         ErrorComplexity.COMPLEX),
    (r"\b(IndexError)\b",                 "IndexError",       ErrorComplexity.COMPLEX),
    (r"\b(AssertionError)\b",             "AssertionError",   ErrorComplexity.COMPLEX),
    (r"\b(ZeroDivisionError)\b",          "ZeroDivisionError",ErrorComplexity.COMPLEX),
    (r"\b(FileNotFoundError)\b",          "FileNotFoundError",ErrorComplexity.COMPLEX),
    (r"\b(PermissionError)\b",            "PermissionError",  ErrorComplexity.COMPLEX),
    (r"\b(TimeoutError)\b",               "TimeoutError",     ErrorComplexity.COMPLEX),
    (r"\b(RuntimeError)\b",               "RuntimeError",     ErrorComplexity.COMPLEX),
    (r"\b(NotImplementedError)\b",        "NotImplementedError", ErrorComplexity.COMPLEX),

    # --- Patrones de texto descriptivo (fusionados de ambos modulos) ---
    (r"invalid syntax",                   "SyntaxError",      ErrorComplexity.SIMPLE),
    (r"unexpected indent",                "IndentationError", ErrorComplexity.SIMPLE),
    (r"unindent does not match",          "IndentationError", ErrorComplexity.SIMPLE),
    (r"no module named",                  "ModuleNotFoundError", ErrorComplexity.SIMPLE),
    (r"cannot import name",               "ImportError",      ErrorComplexity.SIMPLE),
    (r"is not defined",                   "NameError",        ErrorComplexity.SIMPLE),
    (r"has no attribute",                 "AttributeError",   ErrorComplexity.SIMPLE),
    (r"expected \d+ arguments",           "TypeError",        ErrorComplexity.SIMPLE),
    (r"takes \d+ positional arguments",   "TypeError",        ErrorComplexity.SIMPLE),
    (r"assertion failed",                 "AssertionError",   ErrorComplexity.COMPLEX),
    (r"criterio fallo",                   "AssertionError",   ErrorComplexity.COMPLEX),
    (r"key not found",                    "KeyError",         ErrorComplexity.COMPLEX),
    (r"list index out of range",          "IndexError",       ErrorComplexity.COMPLEX),
    (r"division by zero",                 "ZeroDivisionError",ErrorComplexity.COMPLEX),
    # Exclusivos de ErrorClassifier
    (r"unexpected eof",                   "SyntaxError",      ErrorComplexity.SIMPLE),
    (r"expected ':'",                     "SyntaxError",      ErrorComplexity.SIMPLE),
    (r"can't assign to literal",          "SyntaxError",      ErrorComplexity.SIMPLE),
]


# ─── Reglas de reparacion por defecto ────────────────────────────────────────
_DEFAULT_RULES: Dict[str, str] = {
    "SyntaxError": (
        "IMPORTANTE: Revisa cuidadosamente la sintaxis Python. "
        "Verifica: parentesis balanceados, dos puntos despues de def/if/for/while, "
        "sangria consistente con espacios (no tabs), y comillas correctamente cerradas. "
        "El codigo debe ser parseable por ast.parse() sin errores."
    ),
    "IndentationError": (
        "IMPORTANTE: La sangria en Python es critica. Usa exclusivamente espacios "
        "(recomendado: 4 por nivel), nunca mezcles tabs con espacios. "
        "Asegura que todos los bloques (if, for, def, class) tengan sangria consistente."
    ),
    "TabError": (
        "IMPORTANTE: Python no permite mezclar tabs y espacios. Convierte todos los "
        "tabs a espacios (4 por nivel) y verifica la consistencia en todo el archivo."
    ),
    "ImportError": (
        "IMPORTANTE: Verifica que todos los modulos importados existen y estan "
        "disponibles en el entorno. Usa solo la biblioteca estandar o modulos "
        "explicitamente permitidos. Para imports relativos, asegurate de la ruta correcta."
    ),
    "ModuleNotFoundError": (
        "IMPORTANTE: El modulo mencionado no esta disponible. Elimina el import "
        "o reemplazalo con funcionalidad equivalente de la biblioteca estandar. "
        "No asumas que modulos externos estan instalados."
    ),
    "NameError": (
        "IMPORTANTE: Una variable o funcion no esta definida. Verifica: "
        "1) El nombre esta escrito exactamente como se definio (case-sensitive), "
        "2) La definicion aparece antes del uso, 3) No hay typos en el identificador."
    ),
    "AttributeError": (
        "IMPORTANTE: Se esta accediendo a un atributo que no existe. Verifica: "
        "1) El objeto tiene el atributo/metodo mencionado, 2) El nombre esta bien escrito, "
        "3) No confundir atributos de instancia con atributos de clase."
    ),
    "TypeError": (
        "IMPORTANTE: Hay un problema con los tipos de datos. Verifica: "
        "1) Los argumentos pasados a funciones coinciden con los esperados, "
        "2) Las operaciones son validas para los tipos involucrados, "
        "3) Convierte tipos explicitamente cuando sea necesario (str(), int(), etc.)."
    ),
    "ValueError": (
        "IMPORTANTE: Un valor tiene el tipo correcto pero contenido invalido. "
        "Verifica rangos, formatos de cadena, y valores esperados antes de operar. "
        "Agrega validacion de entrada si es necesario."
    ),
    "KeyError": (
        "IMPORTANTE: Se intenta acceder a una clave que no existe en un diccionario. "
        "Usa dict.get('clave', default) o verifica 'clave in dict' antes de acceder. "
        "Revisa que las claves esten escritas correctamente (case-sensitive)."
    ),
    "IndexError": (
        "IMPORTANTE: Indice fuera de rango en lista/tupla. Verifica que el indice "
        "este entre 0 y len(secuencia)-1, o usa slicing seguro. Considera iterar "
        "directamente sobre la secuencia en lugar de usar indices."
    ),
    "AssertionError": (
        "IMPORTANTE: El codigo se ejecuta pero no cumple el criterio esperado. "
        "Agrega prints de depuracion temporales para rastrear valores intermedios. "
        "Revisa la logica condicional y asegurate de que el caso de prueba "
        "se evalua correctamente. El bloque __main__ debe imprimir 'CRITERIO OK' "
        "cuando pase, o 'CRITERIO FALLO: detalle' cuando falle."
    ),
    "ZeroDivisionError": (
        "IMPORTANTE: Division por cero detectada. Agrega validacion antes de dividir: "
        "if divisor != 0: ... else: manejar_caso(). Nunca dividir sin verificar."
    ),
    "FileNotFoundError": (
        "IMPORTANTE: El archivo especificado no existe. Verifica la ruta (absoluta vs relativa), "
        "permisos de lectura, y que el archivo fue creado previamente si es esperado. "
        "Usa pathlib.Path para manejo portable de rutas."
    ),
    "PermissionError": (
        "IMPORTANTE: Sin permisos para acceder al recurso. Verifica permisos de archivo, "
        "no intentes escribir en directorios del sistema, y usa rutas dentro del sandbox."
    ),
    "RuntimeError": (
        "IMPORTANTE: Error en tiempo de ejecucion no especifico. Revisa el traceback "
        "completo para identificar la linea exacta del fallo. Agrega manejo de excepciones "
        "try/except alrededor de operaciones riesgosas."
    ),
    "NotImplementedError": (
        "IMPORTANTE: Funcionalidad no implementada. Completa el metodo o funcion "
        "con la logica requerida, o proporciona una implementacion alternativa valida."
    ),
    "TimeoutError": (
        "IMPORTANTE: Operacion excedio el tiempo limite. Optimiza el codigo para ser "
        "mas eficiente, evita bucles infinitos, y considera procesar datos en chunks "
        "si son muy grandes."
    ),
    "unknown": (
        "IMPORTANTE: Se ha detectado un error no estandar. Revisa el traceback completo, "
        "valida los tipos de datos de entrada y asegura que el entorno de ejecucion "
        "esta correctamente configurado. Si es posible, agrega manejo de excepciones especifico."
    ),
}


class ErrorHandler:
    """
    Modulo unificado de gestion de errores para APA.
    Combina deteccion de patrones, clasificacion de complejidad,
    instrucciones de reparacion, seleccion de modelo y urgencia progresiva.

    Reemplaza a PromptTuner y ErrorClassifier con una unica interfaz.
    """

    def __init__(self, custom_rules_file: Optional[str] = None):
        """
        Inicializa el handler con patrones compilados y reglas de reparacion.

        Args:
            custom_rules_file: Ruta opcional a archivo JSON con reglas adicionales
                               para sobreescribir o ampliar las reglas por defecto.
        """
        # Compilar patrones una sola vez (rendimiento)
        self._compiled_patterns: List[Tuple[re.Pattern, str, ErrorComplexity]] = [
            (re.compile(p, re.IGNORECASE), name, comp)
            for p, name, comp in _ERROR_PATTERNS
        ]
        # Cargar reglas de reparacion
        self._rules: Dict[str, str] = dict(_DEFAULT_RULES)
        if custom_rules_file:
            self._load_custom_rules(custom_rules_file)

    def _load_custom_rules(self, rules_file: str) -> None:
        """Carga reglas adicionales desde un archivo JSON."""
        try:
            if os.path.exists(rules_file):
                with open(rules_file, 'r', encoding='utf-8') as f:
                    custom_rules = json.load(f)
                self._rules.update(custom_rules)
                logger.debug(f"Cargadas {len(custom_rules)} reglas personalizadas desde {rules_file}")
            else:
                logger.warning(f"Archivo de reglas no encontrado: {rules_file}")
        except json.JSONDecodeError as e:
            logger.error(f"JSON invalido en archivo de reglas {rules_file}: {e}")
        except Exception as e:
            logger.error(f"Error cargando reglas personalizadas desde {rules_file}: {e}")

    def detect_error_name(self, error_output: str) -> str:
        """
        Detecta el nombre normalizado del error a partir del texto.

        Args:
            error_output: Texto del error (stderr, traceback, mensaje).

        Returns:
            Nombre del error (ej: "SyntaxError") o "unknown" si no se reconoce.
        """
        if not error_output or not isinstance(error_output, str):
            return "unknown"

        text_lower = error_output.lower()
        for pattern, error_name, _ in self._compiled_patterns:
            if pattern.search(text_lower):
                return error_name

        return "unknown"

    def classify(self, error_output: str, code: Optional[str] = None,
                 execution_result: Optional[Dict[str, Any]] = None) -> ErrorComplexity:
        """
        Clasifica un error como SIMPLE o COMPLEX.

        Compatibilidad hacia atras con ErrorClassifier.classify().
        Los parametros code y execution_result se aceptan pero no se usan
        (coinciden con la firma original de ErrorClassifier).

        Args:
            error_output: Texto del error.
            code: (Deprecated) No se usa. Mantenido por compatibilidad.
            execution_result: (Deprecated) No se usa. Mantenido por compatibilidad.

        Returns:
            ErrorComplexity.SIMPLE o ErrorComplexity.COMPLEX.
        """
        if not error_output or not isinstance(error_output, str):
            logger.debug("Error output vacio o invalido, clasificado como COMPLEX por defecto")
            return ErrorComplexity.COMPLEX

        text_lower = error_output.lower()
        for pattern, _, complexity in self._compiled_patterns:
            if pattern.search(text_lower):
                logger.debug(f"Clasificacion: {complexity.value} (coincidio '{pattern.pattern}')")
                return complexity

        logger.debug("Clasificacion: COMPLEX (ningun patron detectado)")
        return ErrorComplexity.COMPLEX

    def get_remediation(self, error_name: str) -> Optional[str]:
        """
        Retorna la instruccion de reparacion para un tipo de error.

        Args:
            error_name: Nombre del error (ej: "SyntaxError").

        Returns:
            Instrucción detallada en español, o None si no existe regla.
        """
        return self._rules.get(error_name)

    def analyze(self, error_output: str) -> ErrorDiagnosis:
        """
        Analisis completo de un error: nombre + complejidad + reparacion + modelo.

        Args:
            error_output: Texto del error (stderr, traceback, mensaje).

        Returns:
            ErrorDiagnosis con toda la informacion del analisis.
        """
        error_name = self.detect_error_name(error_output)
        complexity = self.classify(error_output)
        remediation = self._rules.get(error_name)
        model = get_recommended_model(complexity)

        # Buscar que patron coincidió para referencia
        matched = ""
        if error_output and isinstance(error_output, str):
            text_lower = error_output.lower()
            for pattern, _, _ in self._compiled_patterns:
                if pattern.search(text_lower):
                    matched = pattern.pattern
                    break

        return ErrorDiagnosis(
            error_name=error_name,
            complexity=complexity,
            remediation=remediation,
            suggested_model=model,
            matched_pattern=matched,
        )

    def tune(self, original_prompt: str, error_message: str, attempt: int) -> str:
        """
        Ajusta un prompt inyectando instrucciones de reparacion segun el error.

        Compatibilidad hacia atras con PromptTuner.tune().
        La urgencia del prefijo escala con el numero de intento.

        Args:
            original_prompt: El prompt original sin modificar.
            error_message: Mensaje de error para analizar.
            attempt: Numero de intento actual (1-based).

        Returns:
            Prompt original con prefijo de instruccion si aplica,
            o prompt original si no se reconoce el error.
        """
        error_name = self.detect_error_name(error_message)
        instruction = self._rules.get(error_name)

        if not instruction:
            logger.debug(f"Sin regla de reparacion para '{error_name}', se retorna prompt original")
            return original_prompt

        # Urgencia progresiva
        if attempt == 1:
            prefix = f"[INSTRUCCION ADICIONAL]: {instruction}\n\n"
        else:
            prefix = f"[INSTRUCCION ADICIONAL (intento {attempt}) - CRITICO]: {instruction}\n\n"

        logger.debug(f"Regla de reparacion aplicada para '{error_name}' (intento {attempt})")
        return prefix + original_prompt


# ─── Funciones de conveniencia (modulo) ──────────────────────────────────────

def get_error_pattern(error_message: str) -> str:
    """
    Extrae un patron normalizado del mensaje de error.
    Compatibilidad hacia atras con prompt_tuner.get_error_pattern().

    Args:
        error_message: Texto del error.

    Returns:
        Nombre de la excepcion o 'unknown'.
    """
    if not error_message or not isinstance(error_message, str):
        return "unknown"

    text_lower = error_message.lower()
    for pattern, error_name, _ in _COMPILED_MODULE_PATTERNS:
        if pattern.search(text_lower):
            return error_name

    return "unknown"


def get_recommended_model(complexity: ErrorComplexity, task_type: str = "correction") -> str:
    """
    Retorna el modelo recomendado segun la complejidad del error.
    Compatibilidad hacia atras con error_classifier.get_recommended_model().

    Args:
        complexity: ErrorComplexity.SIMPLE o ErrorComplexity.COMPLEX
        task_type: Tipo de tarea (reservado para extensiones futuras).

    Returns:
        Identificador del modelo recomendado.
    """
    if complexity == ErrorComplexity.SIMPLE:
        return getattr(settings, 'SIMPLE_MODEL', "qwen/qwen3-coder:free")
    else:
        return getattr(settings, 'COMPLEX_MODEL', "nim/meta/llama-3.1-70b-instruct")


# Patrones compilados a nivel de modulo para get_error_pattern()
_COMPILED_MODULE_PATTERNS: List[Tuple[re.Pattern, str, ErrorComplexity]] = [
    (re.compile(p, re.IGNORECASE), name, comp)
    for p, name, comp in _ERROR_PATTERNS
]


# ─── Tests de autoverificacion ───────────────────────────────────────────────

if __name__ == "__main__":
    logging.disable(logging.NOTSET)
    logger.setLevel(logging.DEBUG)

    handler = ErrorHandler()
    base_prompt = "Genera codigo Python que cumpla el criterio especificado."

    print("=== INICIO PRUEBAS ErrorHandler Unificado ===\n")

    # --- 1. Deteccion de patrones (deben pasar los 36) ---
    test_patterns = [
        ("SyntaxError: invalid syntax", "SyntaxError"),
        ("IndentationError: unexpected indent", "IndentationError"),
        ("TabError: inconsistent tabs", "TabError"),
        ("ImportError: cannot import name", "ImportError"),
        ("ModuleNotFoundError: No module named 'requests'", "ModuleNotFoundError"),
        ("NameError: name 'x' is not defined", "NameError"),
        ("AttributeError: 'NoneType' has no attribute", "AttributeError"),
        ("TypeError: unsupported operand", "TypeError"),
        ("ValueError: invalid literal for int()", "ValueError"),
        ("KeyError: 'missing_key'", "KeyError"),
        ("IndexError: list index out of range", "IndexError"),
        ("AssertionError: Expected True", "AssertionError"),
        ("ZeroDivisionError: division by zero", "ZeroDivisionError"),
        ("FileNotFoundError: [Errno 2]", "FileNotFoundError"),
        ("PermissionError: [Errno 13]", "PermissionError"),
        ("TimeoutError: timed out", "TimeoutError"),
        ("RuntimeError: something happened", "RuntimeError"),
        ("NotImplementedError: abstract method", "NotImplementedError"),
        # Patrones de texto descriptivo
        ("error: invalid syntax at line 5", "SyntaxError"),
        ("unexpected indent in block", "IndentationError"),
        ("unindent does not match any outer", "IndentationError"),
        ("no module named 'xyz'", "ModuleNotFoundError"),
        ("cannot import name 'foo'", "ImportError"),
        ("variable is not defined", "NameError"),
        ("object has no attribute 'bar'", "AttributeError"),
        ("expected 2 arguments but got 1", "TypeError"),
        ("takes 3 positional arguments", "TypeError"),
        ("assertion failed on test", "AssertionError"),
        ("criterio fallo en validacion", "AssertionError"),
        ("key not found in dict", "KeyError"),
        ("list index out of range", "IndexError"),
        ("division by zero detected", "ZeroDivisionError"),
        # Exclusivos de ErrorClassifier
        ("unexpected eof while parsing", "SyntaxError"),
        ("expected ':' after if", "SyntaxError"),
        ("can't assign to literal", "SyntaxError"),
    ]

    passed = 0
    for error_text, expected_name in test_patterns:
        detected = handler.detect_error_name(error_text)
        assert detected == expected_name, f"Fallo: '{error_text}' -> '{detected}' (esperado '{expected_name}')"
        passed += 1
    print(f"P1. Deteccion de patrones: {passed}/{len(test_patterns)} pasaron")

    # --- 2. Clasificacion de complejidad ---
    assert handler.classify("SyntaxError: invalid syntax") == ErrorComplexity.SIMPLE
    assert handler.classify("ModuleNotFoundError: No module") == ErrorComplexity.SIMPLE
    assert handler.classify("KeyError: 'missing'") == ErrorComplexity.COMPLEX
    assert handler.classify("ValueError: invalid literal") == ErrorComplexity.COMPLEX
    assert handler.classify("mensaje extrano sin patron") == ErrorComplexity.COMPLEX
    assert handler.classify("") == ErrorComplexity.COMPLEX
    print("P2. Clasificacion de complejidad: 6/6 pasaron")

    # --- 3. Analisis completo ---
    diag = handler.analyze("SyntaxError: invalid syntax at line 5")
    assert diag.error_name == "SyntaxError"
    assert diag.complexity == ErrorComplexity.SIMPLE
    assert diag.remediation is not None
    assert diag.suggested_model != ""
    print("P3. Analisis completo (ErrorDiagnosis): OK")

    # --- 4. tune() con urgencia progresiva ---
    tuned_1 = handler.tune(base_prompt, "SyntaxError: invalid syntax", attempt=1)
    assert "[INSTRUCCION ADICIONAL]:" in tuned_1
    assert base_prompt in tuned_1

    tuned_2 = handler.tune(base_prompt, "SyntaxError: invalid syntax", attempt=2)
    assert "intento 2" in tuned_2.lower()
    assert "CRITICO" in tuned_2
    print("P4. tune() urgencia progresiva: OK")

    # --- 5. tune() con error desconocido (debe usar regla fallback) ---
    tuned_unk = handler.tune(base_prompt, "algo muy raro paso", attempt=1)
    assert "error no estandar" in tuned_unk
    print("P5. tune() fallback unknown: OK")

    # --- 6. get_error_pattern() (compat PromptTuner) ---
    assert get_error_pattern("TypeError: unsupported operand") == "TypeError"
    assert get_error_pattern("invalid syntax at line 5") == "SyntaxError"
    assert get_error_pattern("mensaje generico sin patron") == "unknown"
    print("P6. get_error_pattern() compat: OK")

    # --- 7. get_recommended_model() (compat ErrorClassifier) ---
    simple_model = get_recommended_model(ErrorComplexity.SIMPLE)
    complex_model = get_recommended_model(ErrorComplexity.COMPLEX)
    assert simple_model != complex_model
    print(f"P7. get_recommended_model() -> SIMPLE: {simple_model}, COMPLEX: {complex_model}")

    # --- 8. classify() con params deprecados (compatibilidad) ---
    result = handler.classify("SyntaxError", code="def foo(", execution_result={"stderr": ""})
    assert result == ErrorComplexity.SIMPLE
    print("P8. classify() con params deprecados: OK")

    # --- 9. Reglas personalizadas via JSON ---
    import tempfile
    tmp_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_test_custom_rules.json")
    try:
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump({"unknown": "Instruccion personalizada de prueba"}, f)

        handler_custom = ErrorHandler(custom_rules_file=tmp_path)
        diag_custom = handler_custom.analyze("Error extrano nunca visto")
        assert "Instruccion personalizada de prueba" in (diag_custom.remediation or "")
        print("P9. Reglas personalizadas JSON: OK")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    print(f"\n=== Todas las pruebas pasaron ({passed + 9} checks) ===")
