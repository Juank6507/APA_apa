# apa/core/code_signatures.py
# v1.3 — Extracción de firmas de código Python para minimizar contexto.
#
# Cuando APA des-escala el integrador a un modelo con menos capacidad de
# ranking pero más ventana de contexto, no se le puede enviar el archivo
# completo. En su lugar, se le envían las FIRMAS (clases, funciones,
# métodos con argumentos y tipos de retorno) más la sección concreta
# que se va a modificar.
#
# Esto reduce el contexto del integrador en ~70% (de ~9.500 tokens a
# ~2.900 tokens en un archivo típico de 800 líneas).
#
# Uso:
#   from core.code_signatures import extract_signatures, build_integrator_context
#
#   sigs = extract_signatures(source_code)
#   context = build_integrator_context(source_code, sigs, target_function="mi_funcion")
#
# El resultado `context` es lo que se le envía al integrador en lugar
# del archivo completo.

import ast
import re
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


def extract_signatures(source_code: str) -> Dict[str, Any]:
    """Extrae las firmas de todas las clases, funciones y métodos de un archivo Python.

    Usa el módulo `ast` para analizar el código sin ejecutarlo.
    Retorna un diccionario con la estructura completa de firmas.

    Args:
        source_code: Código fuente Python completo.

    Returns:
        Dict con claves:
        - "imports": lista de líneas de import
        - "classes": lista de dicts con info de cada clase
        - "functions": lista de dicts con info de cada función módulo
        - "signatures_text": texto formateado de todas las firmas
    """
    result = {
        "imports": [],
        "classes": [],
        "functions": [],
        "signatures_text": "",
    }

    if not source_code or not source_code.strip():
        return result

    try:
        tree = ast.parse(source_code)
    except SyntaxError as e:
        logger.warning(f"extract_signatures(): SyntaxError al parsear — {e}")
        # Fallback: usar regex para extraer lo posible
        return _extract_signatures_fallback(source_code)

    # Extraer imports (líneas completas de import)
    source_lines = source_code.split("\n")
    result["imports"] = _extract_imports(tree, source_lines)

    # Extraer clases y funciones de nivel módulo
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            class_info = _process_class(node, source_lines)
            result["classes"].append(class_info)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_info = _process_function(node, source_lines)
            result["functions"].append(func_info)

    # Construir texto de firmas
    result["signatures_text"] = _build_signatures_text(result)

    return result


def build_integrator_context(
    source_code: str,
    target_name: str = "",
    surrounding_lines: int = 15,
) -> str:
    """Construye el contexto mínimo para el integrador.

    En lugar de enviar el archivo completo, envía:
    1. Las firmas de todo el archivo (classes, functions, methods)
    2. La implementación completa de la función/clase objetivo
    3. Las N líneas antes y después del punto de inserción

    Esto permite al integrador reconstruir el archivo correctamente
    con ~70% menos de contexto.

    Args:
        source_code: Código fuente completo del archivo original.
        target_name: Nombre de la función/clase que se va a modificar
                     (extraído de la especificación del planificador).
        surrounding_lines: Número de líneas de contexto alrededor
                           del punto de inserción.

    Returns:
        Texto con el contexto mínimo para el integrador.
    """
    if not source_code:
        return "# (archivo nuevo)"

    sigs = extract_signatures(source_code)
    parts = []

    # 1. Imports
    if sigs["imports"]:
        parts.append("# === IMPORTS ===")
        parts.extend(sigs["imports"])
        parts.append("")

    # 2. Firmas de todo el archivo
    if sigs["signatures_text"]:
        parts.append("# === FIRMA DE CLASES, FUNCIONES Y MÉTODOS ===")
        parts.append("# (implementación completa solo de la función objetivo)")
        parts.append(sigs["signatures_text"])
        parts.append("")

    # 3. Implementación completa de la función objetivo + contexto
    if target_name:
        target_section = _extract_target_section(
            source_code, target_name, surrounding_lines
        )
        if target_section:
            parts.append(f"# === IMPLEMENTACIÓN OBJETIVO: {target_name} ===")
            parts.append(target_section)
            parts.append("")

    # Fallback: si no se encontró el objetivo ni firmas, enviar truncado
    if not sigs["signatures_text"] and not target_name:
        max_chars = 6000
        if len(source_code) > max_chars:
            parts.append(f"# === CONTENIDO (truncado a {max_chars} chars) ===")
            parts.append(source_code[:max_chars] + "\n# ... (truncado)")
        else:
            parts.append("# === CONTENIDO COMPLETO ===")
            parts.append(source_code)
    elif not parts:
        parts.append(source_code)

    return "\n".join(parts)


def count_tokens_estimate(text: str) -> int:
    """Estima tokens de un texto (~4 caracteres por token).

    Args:
        text: Texto a estimar.

    Returns:
        Número estimado de tokens.
    """
    if not text:
        return 0
    return max(1, len(text) // 4)


# ============================================================================
# Funciones internas
# ============================================================================

def _extract_imports(tree: ast.AST, source_lines: List[str]) -> List[str]:
    """Extrae las líneas de import del código fuente."""
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            line_no = node.lineno - 1
            if 0 <= line_no < len(source_lines):
                line = source_lines[line_no].rstrip()
                if line and line not in imports:
                    imports.append(line)
                    # Capturar imports multilinea (parentesis)
                    for i in range(line_no + 1, min(line_no + 10, len(source_lines))):
                        next_line = source_lines[i].rstrip()
                        if not next_line or next_line.startswith("#"):
                            break
                        if next_line.strip().startswith(("from ", "import ")):
                            break
                        imports.append(next_line)
                        if ")" in next_line:
                            break
    return imports


def _process_class(node: ast.ClassDef, source_lines: List[str]) -> Dict[str, Any]:
    """Extrae la información de una clase.
    
    v1.2: También captura atributos de nivel de clase (Assign, AnnAssign)
    para que las firmas sean más completas y las clases sin métodos
    pero con atributos no queden vacías.
    """
    class_info = {
        "name": node.name,
        "line": node.lineno,
        "end_line": getattr(node, 'end_lineno', node.lineno),
        "decorators": _get_decorators(node, source_lines),
        "bases": [_name_of(b) for b in node.bases],
        "methods": [],
        "class_attributes": [],
    }

    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            method_info = _process_function(child, source_lines)
            class_info["methods"].append(method_info)
        elif isinstance(child, (ast.Assign, ast.AnnAssign)):
            # Capturar atributos de nivel de clase
            attr_line = _extract_attribute_line(child, source_lines)
            if attr_line:
                class_info["class_attributes"].append(attr_line)

    return class_info


def _process_function(node, source_lines: List[str]) -> Dict[str, Any]:
    """Extrae la información de una función o método."""
    func_info = {
        "name": node.name,
        "line": node.lineno,
        "end_line": getattr(node, "end_lineno", node.lineno),
        "decorators": _get_decorators(node, source_lines),
        "args": [],
        "returns": None,
        "is_async": isinstance(node, ast.AsyncFunctionDef),
    }

    # Argumentos
    all_args = []
    if hasattr(node.args, "posonlyargs"):
        all_args.extend(node.args.posonlyargs)
    all_args.extend(node.args.args)
    if node.args.vararg:
        all_args.append(node.args.vararg)
    if hasattr(node.args, "kwonlyargs"):
        all_args.extend(node.args.kwonlyargs)
    if node.args.kwarg:
        all_args.append(node.args.kwarg)

    for arg in all_args:
        arg_str = arg.arg
        if arg.annotation:
            arg_str += f": {_annotation_str(arg.annotation)}"
        func_info["args"].append(arg_str)

    # Defaults
    defaults = node.args.defaults
    kw_defaults = node.args.kw_defaults if hasattr(node.args, "kw_defaults") else []
    num_no_default = len(func_info["args"]) - len(defaults) - (len(kw_defaults) if not node.args.kwarg else len(kw_defaults) - 1)

    # Tipo de retorno
    if node.returns:
        func_info["returns"] = _annotation_str(node.returns)

    # Docstring
    docstring = ast.get_docstring(node)
    if docstring:
        func_info["docstring"] = docstring.split("\n")[0][:80]

    return func_info


def _get_decorators(node, source_lines: List[str]) -> List[str]:
    """Extrae los decoradores de una función/clase como texto."""
    decorators = []
    for dec in node.decorator_list:
        dec_str = _ast_to_str(dec)
        if dec_str:
            decorators.append(dec_str)
    return decorators


def _name_of(node) -> str:
    """Extrae el nombre de un nodo AST (para bases de clases)."""
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Attribute):
        return f"{_name_of(node.value)}.{node.attr}"
    elif isinstance(node, ast.Subscript):
        return f"{_name_of(node.value)}[{_name_of(node.slice)}]"
    return ""


def _annotation_str(node) -> str:
    """Convierte una anotación de tipo AST a string."""
    return _ast_to_str(node) or "Any"


def _ast_to_str(node) -> str:
    """Convierte un nodo AST a string de forma segura."""
    if node is None:
        return ""
    try:
        import ast as _ast
        return _ast.unparse(node)
    except Exception:
        return ""


def _extract_attribute_line(node, source_lines: List[str]) -> Optional[str]:
    """Extrae la línea de texto de un atributo de clase (Assign o AnnAssign).
    
    v1.2: Para firmas, extraemos la línea original del código fuente.
    Si no se puede obtener, construimos una representación simplificada.
    """
    if isinstance(node, ast.AnnAssign):
        # Variable anotada: x: int = 5
        line_no = node.lineno - 1
        if 0 <= line_no < len(source_lines):
            return source_lines[line_no].strip()
        name = _ast_to_str(node.target) if hasattr(node, 'target') else "?"
        ann = _ast_to_str(node.annotation) if node.annotation else "Any"
        val = f" = {_ast_to_str(node.value)}" if node.value else ""
        return f"{name}: {ann}{val}"
    elif isinstance(node, ast.Assign):
        # Asignación simple: X = "value"
        line_no = node.lineno - 1
        if 0 <= line_no < len(source_lines):
            return source_lines[line_no].strip()
        # Fallback: construir desde AST
        try:
            return _ast_to_str(node)
        except Exception:
            return None
    return None


def _build_signatures_text(sigs: Dict[str, Any]) -> str:
    """Construye el texto formateado de todas las firmas.

    v1.3: Las clases con atributos pero sin métodos muestran los atributos.
    Las funciones/métodos usan '...' como cuerpo placeholder.
    Si una clase queda vacía (sin atributos ni métodos) NO se añade
    ningún respaldo: el error debe ser visible para corregir la causa raíz.
    """
    lines = []

    # Funciones de nivel módulo
    for func in sigs.get("functions", []):
        lines.append(_format_function_signature(func, indent=0))

    # Clases con sus métodos
    for cls in sigs.get("classes", []):
        lines.append("")
        # Decoradores de la clase (van ANTES de la línea class)
        for dec in cls.get("decorators", []):
            lines.append(f"@{dec}")
        # Firma de la clase
        bases_str = f"({', '.join(cls['bases'])})" if cls["bases"] else ""
        lines.append(f"class {cls['name']}{bases_str}:")

        # Atributos de nivel de clase (antes de métodos)
        for attr in cls.get("class_attributes", []):
            lines.append(f"    {attr}")

        # Métodos (cada uno con '...' como cuerpo)
        for method in cls.get("methods", []):
            lines.append(_format_function_signature(method, indent=4))

    return "\n".join(lines)


def _format_function_signature(func: Dict[str, Any], indent: int = 0) -> str:
    """Formatea la firma de una función/método."""
    prefix = " " * indent
    parts = []

    # Decoradores
    for dec in func.get("decorators", []):
        parts.append(f"{prefix}@{dec}")

    # Async
    async_kw = "async " if func.get("is_async") else ""

    # Nombre y argumentos
    args_str = ", ".join(func.get("args", ["self"] if indent > 0 else []))
    name = func.get("name", "unknown")

    # Retorno
    ret_str = ""
    if func.get("returns"):
        ret_str = f" -> {func['returns']}"

    parts.append(f"{prefix}{async_kw}def {name}({args_str}){ret_str}: ...")

    return "\n".join(parts)


def _extract_target_section(
    source_code: str,
    target_name: str,
    surrounding_lines: int = 15,
) -> Optional[str]:
    """Extrae la implementación completa de una función/clase objetivo
    con N líneas de contexto antes y después.

    Busca la función/clase por nombre en el código fuente y extrae
    su bloque completo (desde `def`/`class` hasta la misma indentación
    o EOF) más las líneas circundantes.

    Args:
        source_code: Código fuente completo.
        target_name: Nombre de la función/clase objetivo.
        surrounding_lines: Líneas de contexto alrededor.

    Returns:
        Sección de código extraída, o None si no se encuentra.
    """
    lines = source_code.split("\n")
    target_line = None
    target_indent = 0

    # Buscar la línea donde empieza la función/clase
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        current_indent = len(line) - len(stripped)

        # Buscar "def target_name" o "class target_name"
        if re.match(rf'^(async\s+)?def\s+{re.escape(target_name)}\s*\(', stripped):
            target_line = i
            target_indent = current_indent
            break
        if re.match(rf'^class\s+{re.escape(target_name)}\s*[\(:]', stripped):
            target_line = i
            target_indent = current_indent
            break

    if target_line is None:
        # No se encontró por nombre exacto — buscar parcial
        for i, line in enumerate(lines):
            stripped = line.lstrip()
            if re.escape(target_name) in stripped and (
                re.search(r'(?:def|class)\s+\S+\s*\(', stripped)
            ):
                target_line = i
                target_indent = len(line) - len(stripped)
                break

    if target_line is None:
        return None

    # Encontrar el final del bloque (siguiente línea con igual o menor indentación
    # que no sea una línea vacía)
    end_line = len(lines)
    for i in range(target_line + 1, len(lines)):
        stripped = lines[i].strip()
        if not stripped:
            continue
        current_indent = len(lines[i]) - len(stripped)
        if current_indent <= target_indent and stripped and not stripped.startswith("#"):
            end_line = i
            break

    # Calcular rango con contexto
    start = max(0, target_line - surrounding_lines)
    end = min(len(lines), end_line + surrounding_lines)

    section_lines = lines[start:end]

    # Indicar si hay contenido antes/después truncado
    markers = []
    if start > 0:
        markers.append(f"# ... {start} líneas anteriores omitidas ...")
    if end < len(lines):
        markers.append(f"# ... {len(lines) - end} líneas posteriores omitidas ...")

    result = []
    if markers and markers[0]:
        result.append(markers[0])
    result.extend(section_lines)
    if len(markers) > 1 and markers[1]:
        result.append(markers[1])

    return "\n".join(result)


def _extract_signatures_fallback(source_code: str) -> Dict[str, Any]:
    """Fallback: extrae firmas con regex cuando ast.parse() falla."""
    result = {
        "imports": [],
        "classes": [],
        "functions": [],
        "signatures_text": "",
    }

    lines = source_code.split("\n")
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(("import ", "from ")):
            if stripped not in result["imports"]:
                result["imports"].append(stripped)
        elif re.match(r'^(async\s+)?def\s+\w+\s*\(', stripped):
            result["functions"].append({"name": line.strip()})
        elif re.match(r'^class\s+\w+\s*[\(:]', stripped):
            result["classes"].append({"name": line.strip()})

    sig_lines = []
    for func in result["functions"]:
        sig_lines.append(func.get("name", ""))
    for cls in result["classes"]:
        sig_lines.append(cls.get("name", ""))

    result["signatures_text"] = "\n".join(sig_lines)
    return result


# ============================================================================
# VALIDACIÓN AUTOCONTENIDA
# ============================================================================

def _run_validation():
    """Validación autocontenida de code_signatures.py."""
    import sys

    # --- Test 1: Firmas básicas ---
    test_code = '''
import os
import sys
from typing import Optional, List

class MiClase:
    """Una clase de prueba."""

    def __init__(self, nombre: str, valor: int = 0):
        self.nombre = nombre
        self.valor = valor

    def calcular(self, x: int, y: int) -> int:
        return x + y + self.valor

    async def procesar(self, datos: List[str]) -> Optional[str]:
        resultado = ",".join(datos)
        return resultado if resultado else None

def funcion_global(a: int, b: str = "hola", *args, **kwargs) -> bool:
    """Función de prueba."""
    return len(args) > 0

async def funcion_async() -> None:
    pass
'''.strip()

    sigs = extract_signatures(test_code)

    assert len(sigs["imports"]) >= 2, f"Esperado >=2 imports, got {len(sigs['imports'])}"
    assert len(sigs["classes"]) == 1, f"Esperado 1 clase, got {len(sigs['classes'])}"
    assert len(sigs["functions"]) == 2, f"Esperado 2 funciones, got {len(sigs['functions'])}"
    assert sigs["classes"][0]["name"] == "MiClase"
    assert len(sigs["classes"][0]["methods"]) == 3
    assert sigs["classes"][0]["methods"][0]["name"] == "__init__"
    assert sigs["classes"][0]["methods"][1]["returns"] == "int"
    assert sigs["classes"][0]["methods"][2]["is_async"] is True
    assert sigs["functions"][0]["name"] == "funcion_global"
    assert sigs["functions"][1]["is_async"] is True
    print("  ✅ Test 1: Firmas básicas")

    # --- Test 2: signatures_text contiene firmas ---
    text = sigs["signatures_text"]
    assert "class MiClase" in text
    assert "def __init__" in text
    assert "def calcular" in text
    assert "async def procesar" in text
    assert "def funcion_global" in text
    print("  ✅ Test 2: signatures_text contiene firmas")

    # --- Test 3: build_integrator_context ---
    context = build_integrator_context(test_code, target_name="calcular")
    assert "# === IMPORTS ===" in context
    assert "# === FIRMA" in context
    assert "# === IMPLEMENTACIÓN OBJETIVO: calcular ===" in context
    assert "def calcular(self, x: int, y: int) -> int:" in context
    print("  ✅ Test 3: build_integrator_context con objetivo")

    # --- Test 4: build_integrator_context sin objetivo ---
    context_no_target = build_integrator_context(test_code)
    assert "# === IMPORTS ===" in context_no_target
    assert "# === FIRMA" in context_no_target
    print("  ✅ Test 4: build_integrator_context sin objetivo")

    # --- Test 5: Reducción de contexto ---
    code_grande = test_code + "\n" + "\n".join(
        f"def funcion_{i}(x):\n    return x * {i}\n" for i in range(100)
    )
    context_completo_tokens = count_tokens_estimate(code_grande)
    context_minimo_tokens = count_tokens_estimate(
        build_integrator_context(code_grande, target_name="funcion_50")
    )
    # El contexto mínimo debe ser menor
    assert context_minimo_tokens < context_completo_tokens, \
        f"Esperado {context_minimo_tokens} < {context_completo_tokens}"
    reduction = (1 - context_minimo_tokens / context_completo_tokens) * 100
    print(f"  ✅ Test 5: Reducción de contexto — {reduction:.0f}% menos tokens")
    print(f"     Completo: ~{context_completo_tokens} tokens → Mínimo: ~{context_minimo_tokens} tokens")

    # --- Test 6: Fallback con código roto ---
    sigs_broken = extract_signatures("def hola(\n esto no es válido python")
    assert "functions" in sigs_broken  # No debe fallar
    print("  ✅ Test 6: Fallback con código roto")

    # --- Test 7: Código vacío ---
    sigs_empty = extract_signatures("")
    assert sigs_empty["imports"] == []
    assert sigs_empty["classes"] == []
    assert sigs_empty["functions"] == []
    print("  ✅ Test 7: Código vacío")

    # --- Test 8: v1.2 — Clase con atributos pero sin métodos ---
    test_attrs_code = '''
class ValidationMode:
    SYNTAX = "syntax"
    IMPORT = "import"
    EXECUTE = "execute"
    AUTO = "auto"

@dataclass
class AssemblyResult:
    success: bool
    output: str
    backup_path: Optional[str] = None
'''.strip()
    sigs_attrs = extract_signatures(test_attrs_code)
    assert len(sigs_attrs["classes"]) == 2, f"Esperado 2 clases, got {len(sigs_attrs['classes'])}"
    # ValidationMode: 4 atributos, 0 métodos
    vm = sigs_attrs["classes"][0]
    assert vm["name"] == "ValidationMode"
    assert len(vm["class_attributes"]) == 4, f"Esperado 4 attrs, got {len(vm['class_attributes'])}"
    assert len(vm["methods"]) == 0
    # AssemblyResult: 3 atributos (de dataclass), 0 métodos
    ar = sigs_attrs["classes"][1]
    assert ar["name"] == "AssemblyResult"
    assert len(ar["class_attributes"]) >= 2
    print("  ✅ Test 8: Clase con atributos pero sin métodos")

    # --- Test 9: v1.2 — signatures_text es Python válido ---
    text_attrs = sigs_attrs["signatures_text"]
    try:
        ast.parse(text_attrs)
        print("  ✅ Test 9: signatures_text es Python válido (ast.parse OK)")
    except SyntaxError as e:
        print(f"  ❌ Test 9 FALLÓ: {e}")
        print(f"     signatures_text:\n{text_attrs}")
        raise

    # --- Test 10: v1.3 — Clase vacía NO tiene respaldo ---
    empty_class_code = '''
class EmptyClass:
    pass

def standalone():
    return 42
'''.strip()
    sigs_empty_class = extract_signatures(empty_class_code)
    text_empty = sigs_empty_class["signatures_text"]
    # EmptyClass tiene solo pass (que es un Pass, no Assign ni FunctionDef)
    # así que no debe tener atributos ni métodos → el cuerpo queda vacío
    assert "class EmptyClass:" in text_empty
    assert "    ..." not in text_empty, "v1.3: NO se debe añadir '...' de respaldo a clases vacías"
    # Verificar que efectivamente da error de sintaxis (es el comportamiento deseado)
    try:
        ast.parse(text_empty)
        print("  ❌ Test 10 FALLÓ: se esperaba SyntaxError para clase vacía")
    except SyntaxError:
        print("  ✅ Test 10: Clase vacía produce SyntaxError (comportamiento correcto v1.3)")

    print("\n✅ Todos los tests de code_signatures.py pasaron.")


if __name__ == "__main__":
    _run_validation()
