# apa/core/symbol_graph.py
# v1.1 — RF1: Grafo de dependencias a nivel de símbolo.
#         Analiza código Python con AST para construir un grafo de
#         llamadas, importaciones y herencia entre símbolos.
#         Permite responder: "si refactorizo X, qué se rompe?"
#
# CAPACIDADES:
#   - Construcción de grafo de símbolos desde archivos Python
#   - Seguimiento de llamadas (quién llama a quién)
#   - Seguimiento de importaciones (quién importa qué)
#   - Herencia (clases base → derivadas)
#   - Contexto de refactorización: dado un símbolo, retorna
#     quién lo llama, a quién llama, código fuente de callers,
#     archivos dependientes y jerarquía de herencia.
#
# DECISIONES ARQUITECTÓNICAS:
#   RF1-1: AST puro — sin ejecución de código, solo análisis estático
#   RF1-2: Símbolos = funciones + clases + métodos (no variables)
#   RF1-3: Resolución de imports por nombre (heurística, no ejecución)
#   RF1-4: Grafo dirigido: caller → callee (llamado_por es inverso)
#   RF1-5: Un símbolo se identifica por (archivo, nombre_cualificado)
#
# CAMBIOS v1.1 (minimización de limitación heurística):
#   RF1-6: Detección de imports dinámicos (importlib.import_module, __import__)
#   RF1-7: Seguimiento de getattr() como alias dinámico
#   RF1-8: Resolución de imports relativos (from . import X)
#   RF1-9: Seguimiento de re-exportaciones vía __init__.py
#
# CAMBIOS v1.2 (erradicación de limitación heurística):
#   RF1-10: BUG FIX — from . import X ahora resuelve a X.py (no __init__.py)
#   RF1-11: Expansión de from X import * usando __all__ o símbolos del módulo
#   RF1-12: Verificación de existencia de archivos para imports absolutos
#   RF1-13: Resolución explícita de self.metodo() y cls.metodo()
#   RF1-14: Resolución de importlib.import_module(variable) con tracking
#
# CAMBIOS v1.3 (transparencia y reporte de cobertura):
#   RF1-15: get_coverage_report() — reporte de lo detectado vs no detectado
#   RF1-16: get_refactor_context() ahora incluye campo "advertencias"
#   RF1-17: Detección de imports condicionales (try/except, if)
#   RF1-18: Detección de llamadas no resueltas (callee_file=None)
#
# CRITERIO DE ACEPTACIÓN RF1:
#   Dado main.py que importa utils.py y llama a utils.validar(),
#   get_refactor_context("utils.py", "validar") retorna main.py en llamado_por.
#
# ============================================================================
import ast
import os
import sys
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Set, Tuple, Any

# ============================================================================
# Logging setup
# ============================================================================
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    logger.addHandler(handler)
logger.propagate = False


# ============================================================================
# Exports explícitos
# ============================================================================
__all__ = [
    "SymbolInfo",
    "CallEdge",
    "SymbolSignature",
    "SignatureChange",
    "SymbolGraph",
]


# ============================================================================
# SymbolInfo — información de un símbolo en el grafo
# ============================================================================
@dataclass
class SymbolInfo:
    """Información de un símbolo (función, clase, método) detectado por AST.

    RF1-2: Solo funciones, clases y métodos. No variables.
    RF1-5: Identificado por (archivo, nombre_cualificado).
    """
    name: str                          # Nombre simple (ej: "validar")
    qualified_name: str                # Nombre cualificado (ej: "Procesador.procesar")
    file: str                          # Archivo donde se define (basename)
    symbol_type: str                   # "function", "class", "method"
    lineno: int = 0                    # Línea de definición
    end_lineno: int = 0                # Línea final de definición
    source_code: str = ""              # Código fuente del símbolo
    base_classes: List[str] = field(default_factory=list)  # Clases base (solo para symbol_type="class")


# ============================================================================
# CallEdge — arista del grafo de llamadas
# ============================================================================
@dataclass
class CallEdge:
    """Arista dirigida: caller → callee.

    RF1-4: caller llama a callee. llamado_por es la inversa.
    """
    caller_file: str                   # Archivo del caller
    caller_symbol: str                 # Símbolo del caller (cualificado)
    callee_name: str                   # Nombre del callee (como aparece en la llamada)
    callee_file: Optional[str] = None  # Archivo del callee (resuelto si es posible)


# ============================================================================
# SymbolSignature — firma de un símbolo para comparación (RF1)
# ============================================================================
@dataclass
class SymbolSignature:
    """Firma de un símbolo para detección de cambios de firma.

    Permite comparar dos versiones de un símbolo y determinar si
    el cambio es breaking, compatible o solo de cuerpo.
    """
    name: str                           # Nombre simple
    qualified_name: str                 # Nombre cualificado (ej: "Procesador.procesar")
    symbol_type: str                    # "function", "class", "method"
    args: List[str] = field(default_factory=list)      # Nombres de argumentos
    defaults_count: int = 0             # Número de argumentos con valor por defecto
    has_kwargs: bool = False            # Tiene **kwargs
    has_varargs: bool = False           # Tiene *args
    body_hash: str = ""                 # Hash del cuerpo para detección de cambios


# ============================================================================
# SignatureChange — resultado de detect_signature_changes()
# ============================================================================
@dataclass
class SignatureChange:
    """Cambio detectado entre dos firmas de un símbolo.

    change_type puede ser:
      - "none": sin cambio real
      - "signature_breaking": firma cambió de forma incompatible
      - "signature_compatible": firma cambió pero es retrocompatible
      - "body_only": solo cambió el cuerpo, la firma es idéntica
      - "removed": símbolo eliminado
      - "added": símbolo nuevo
    """
    symbol: str                         # Nombre cualificado del símbolo
    change_type: str                    # Tipo de cambio
    old_signature: Optional[SymbolSignature] = None  # Firma anterior (None si added)
    new_signature: Optional[SymbolSignature] = None  # Firma nueva (None si removed)
    description: str = ""               # Descripción legible del cambio


# ============================================================================
# SymbolGraph — grafo de dependencias a nivel de símbolo
# ============================================================================
class SymbolGraph:
    """Grafo de dependencias a nivel de símbolo para refactorización segura.

    RF1-1: Análisis AST puro — sin ejecución de código.
    RF1-3: Resolución de imports por nombre (heurística).

    Uso principal:
        graph = SymbolGraph()
        graph.build_from_directory("/path/to/project")
        context = graph.get_refactor_context("utils.py", "validar")
        # context["llamado_por"] = [("main.py", "ejecutar"), ...]
    """

    def __init__(self):
        # Símbolos: (file, qualified_name) → SymbolInfo
        self._symbols: Dict[Tuple[str, str], SymbolInfo] = {}

        # Índice por archivo: file → [(qualified_name, SymbolInfo)]
        self._file_symbols: Dict[str, List[SymbolInfo]] = {}

        # Aristas de llamada: caller → [CallEdge]
        self._call_edges: List[CallEdge] = []

        # Índice invertido: callee_name → [CallEdge] (para llamado_por)
        self._callee_index: Dict[str, List[CallEdge]] = {}

        # Imports por archivo: file → [(import_name, import_as, from_file)]
        self._imports: Dict[str, List[Tuple[str, str, Optional[str]]]] = {}

        # Herencia: base_class_name → [(file, derived_class_name)]
        self._inheritance: Dict[str, List[Tuple[str, str]]] = {}

        # Código fuente completo por archivo
        self._file_sources: Dict[str, str] = {}

        # Mapping de alias de import: (file, local_name) → (source_file, original_name)
        self._import_aliases: Dict[Tuple[str, str], Tuple[str, str]] = {}

        # RF1-6: Mapeo de alias dinámicos: (file, var_name) → (source_file, original_name)
        # Para importlib.import_module() y __import__()
        self._dynamic_aliases: Dict[Tuple[str, str], Tuple[str, str]] = {}

        # RF1-7: Mapeo de getattr() alias: (file, var_name) → (source_file, attr_name)
        self._getattr_aliases: Dict[Tuple[str, str], Tuple[str, str]] = {}

        # RF1-8: Directorio base del proyecto para resolver imports relativos
        self._base_dir: str = ""

        # RF1-9: Re-exportaciones: nombre re-exportado → (archivo_real, nombre_real)
        self._re_exports: Dict[Tuple[str, str], Tuple[str, str]] = {}

        # RF1-14: Tracking de variables: (file, var_name) → valor literal asignado
        self._var_assignments: Dict[Tuple[str, str], str] = {}

        # RF1-12: Conjunto de archivos conocidos del proyecto
        self._known_files: Set[str] = set()

        # RF1-17: Imports condicionales detectados: (file, lineno, import_text, context)
        self._conditional_imports: List[Tuple[str, int, str, str]] = []

        # RF1-18: Llamadas no resueltas: (caller_file, caller_symbol, callee_name)
        self._unresolved_calls: List[Tuple[str, str, str]] = []

    # --- Construcción del grafo ---

    def build_from_directory(self, directory: str) -> int:
        """Escanea un directorio y construye el grafo de símbolos.

        Retorna el número de archivos procesados.
        """
        # RF1-8: Guardar directorio base para resolver imports relativos
        self._base_dir = os.path.abspath(directory)

        # RF1-12: PRIMERO registrar todos los archivos conocidos del proyecto.
        # Esto debe hacerse ANTES de parsear, para que _extract_imports
        # pueda verificar si un import apunta a un archivo real o es un
        # módulo externo (stdlib o terceros).
        for root, dirs, files in os.walk(directory):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
            for fname in files:
                if fname.endswith('.py'):
                    fpath = os.path.join(root, fname)
                    rel_path = os.path.relpath(fpath, self._base_dir)
                    self._known_files.add(rel_path)

        # Ahora parsear cada archivo (con _known_files ya poblado)
        processed = 0
        for root, dirs, files in os.walk(directory):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
            for fname in files:
                if fname.endswith('.py'):
                    fpath = os.path.join(root, fname)
                    rel_path = os.path.relpath(fpath, self._base_dir)
                    try:
                        with open(fpath, 'r', encoding='utf-8') as f:
                            source = f.read()
                        self._parse_file(rel_path, source)
                        self._file_sources[rel_path] = source
                        processed += 1
                    except (SyntaxError, UnicodeDecodeError) as e:
                        logger.warning(f"Error parseando {fname}: {e}")

        # RF1-9: Resolver re-exportaciones desde __init__.py
        self._resolve_re_exports()

        return processed

    def build_from_files(self, files: Dict[str, str], base_dir: str = "") -> int:
        """Construye el grafo desde un dict {filename: source_code}.

        Útil para tests donde no hay archivos en disco.
        Retorna el número de archivos procesados.

        Args:
            files: Dict {filename: source_code}.
            base_dir: Directorio base opcional para resolver imports relativos.
        """
        if base_dir:
            self._base_dir = base_dir

        # RF1-12: Registrar archivos conocidos ANTES de parsear
        # (misma lógica que build_from_directory)
        for fname in files:
            self._known_files.add(fname)

        for fname, source in files.items():
            try:
                self._parse_file(fname, source)
                self._file_sources[fname] = source
            except SyntaxError as e:
                logger.warning(f"Error parseando {fname}: {e}")

        # RF1-9: Resolver re-exportaciones desde __init__.py
        self._resolve_re_exports()

        return len(files)

    def _parse_file(self, filename: str, source: str) -> None:
        """Parsea un archivo y extrae símbolos, llamadas e imports."""
        tree = ast.parse(source, filename=filename)

        # Fase 0.5: Extraer asignaciones de variables (RF1-14)
        self._extract_var_assignments(filename, tree)

        # Fase 1: Extraer imports (incluye imports relativos RF1-8)
        self._extract_imports(filename, tree)

        # Fase 1.5: Extraer imports dinámicos (RF1-6 + RF1-14)
        self._extract_dynamic_imports(filename, tree)

        # Fase 1.7: Extraer aliases de getattr() (RF1-7)
        self._extract_getattr_aliases(filename, tree)

        # Fase 1.8: Extraer imports condicionales (RF1-17)
        self._extract_conditional_imports(filename, tree)

        # Fase 2: Extraer símbolos (funciones, clases, métodos)
        self._extract_symbols(filename, tree, source)

        # Fase 3: Extraer llamadas entre símbolos
        self._extract_calls(filename, tree)

    def _extract_imports(self, filename: str, tree: ast.AST) -> None:
        """Extrae imports de un archivo y construye índice de alias.

        RF1-8: Ahora resuelve imports relativos (from . import X)
        usando la posición del archivo dentro del proyecto.
        """
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    import_name = alias.name
                    import_as = alias.asname or alias.name
                    # Heurística: el módulo importado es un archivo del proyecto
                    from_file = import_name.replace('.', os.sep) + '.py'
                    # RF1-12: Solo registrar si el archivo existe en el proyecto
                    # o si no tenemos lista de archivos conocidos (modo tests)
                    if from_file in self._known_files or not self._known_files:
                        imports.append((import_name, import_as, from_file))
                        self._import_aliases[(filename, import_as)] = (from_file, import_as)
                    else:
                        imports.append((import_name, import_as, None))

            elif isinstance(node, ast.ImportFrom):
                module = node.module or ''
                level = getattr(node, 'level', 0)  # 0=absoluto, 1=., 2=..
                for alias in node.names:
                    import_name = alias.name
                    import_as = alias.asname or alias.name

                    # RF1-11: from X import * — expandir más tarde con _expand_star_imports
                    if import_name == '*':
                        imports.append((import_name, '*', None))
                        continue

                    # RF1-8: Resolver imports relativos
                    if level > 0 and self._base_dir:
                        from_file = self._resolve_relative_import(
                            filename, module, level, import_name
                        )
                    else:
                        from_file = module.replace('.', os.sep) + '.py' if module else None

                    imports.append((import_name, import_as, from_file))
                    # Registrar alias: el nombre local → (archivo_origen, nombre_original)
                    if from_file:
                        self._import_aliases[(filename, import_as)] = (from_file, import_name)
                    elif import_name:
                        # from X import Y — Y podría ser una función/clase de X
                        self._import_aliases[(filename, import_as)] = (module + '.py' if module else import_name, import_name)

        self._imports[filename] = imports

        # RF1-11: Expandir star imports después de registrar todos los imports normales
        self._expand_star_imports(filename)

    def _resolve_relative_import(
        self, filename: str, module: str, level: int,
        import_name: str = ""
    ) -> Optional[str]:
        """Resuelve un import relativo a la ruta del archivo.

        RF1-8: Convierte `from . import X` (level=1) o `from .. import Y` (level=2)
        en la ruta correcta del archivo dentro del proyecto.

        RF1-10: Cuando module está vacío y hay import_name,
        from . import X ahora resuelve a X.py en vez de __init__.py.

        Args:
            filename: Archivo actual (ruta relativa al base_dir).
            module: Nombre del módulo (puede estar vacío).
            level: Nivel de relatividad (1=., 2=.., etc.).
            import_name: Nombre del símbolo importado (para from . import X).

        Returns:
            Ruta del archivo importado, o None si no se puede resolver.
        """
        if not self._base_dir:
            return None

        # Directorio del archivo actual (relativo al base_dir)
        file_dir = os.path.dirname(filename)

        # Subir 'level - 1' niveles (level=1 = mismo dir, level=2 = un nivel arriba)
        # from . import X → mismo directorio
        # from .. import X → un directorio arriba
        for _ in range(level - 1):
            file_dir = os.path.dirname(file_dir)

        # Construir la ruta destino
        if module:
            # from .modulo import X → dir_actual/modulo.py
            dest = os.path.join(file_dir, module.replace('.', os.sep))
            # Puede ser un paquete (directorio) → agregar __init__.py
            return dest + '.py'
        else:
            # RF1-10: from . import X → intentar X.py primero, luego __init__.py
            if import_name:
                candidate = os.path.join(file_dir, import_name + '.py')
                if candidate in self._known_files:
                    return candidate
            # Fallback: from . import paquete → __init__.py del paquete
            return os.path.join(file_dir, '__init__.py')

    def _extract_symbols(self, filename: str, tree: ast.AST, source: str) -> None:
        """Extrae funciones, clases y métodos de un AST."""
        symbols = []
        source_lines = source.splitlines()

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                sym = self._make_symbol(filename, node.name, node.name,
                                        "function", node, source_lines)
                symbols.append(sym)
                self._symbols[(filename, node.name)] = sym

            elif isinstance(node, ast.ClassDef):
                sym = self._make_symbol(filename, node.name, node.name,
                                        "class", node, source_lines)
                # Extraer clases base
                for base in node.bases:
                    base_name = self._get_name(base)
                    if base_name:
                        sym.base_classes.append(base_name)
                        # Registrar herencia
                        if base_name not in self._inheritance:
                            self._inheritance[base_name] = []
                        self._inheritance[base_name].append((filename, node.name))

                symbols.append(sym)
                self._symbols[(filename, node.name)] = sym

                # Métodos de la clase
                for item in ast.iter_child_nodes(node):
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        qname = f"{node.name}.{item.name}"
                        method_sym = self._make_symbol(filename, item.name, qname,
                                                       "method", item, source_lines)
                        symbols.append(method_sym)
                        self._symbols[(filename, qname)] = method_sym

        self._file_symbols[filename] = symbols

    def _make_symbol(self, filename: str, name: str, qualified_name: str,
                     symbol_type: str, node: ast.AST, source_lines: List[str]) -> SymbolInfo:
        """Crea un SymbolInfo con código fuente extraído."""
        lineno = getattr(node, 'lineno', 0)
        end_lineno = getattr(node, 'end_lineno', lineno)

        # Extraer código fuente del símbolo
        if source_lines and 0 < lineno <= len(source_lines):
            end = min(end_lineno, len(source_lines))
            source_code = '\n'.join(source_lines[lineno - 1:end])
        else:
            source_code = ""

        return SymbolInfo(
            name=name,
            qualified_name=qualified_name,
            file=filename,
            symbol_type=symbol_type,
            lineno=lineno,
            end_lineno=end_lineno,
            source_code=source_code,
        )

    def _extract_calls(self, filename: str, tree: ast.AST) -> None:
        """Extrae llamadas a funciones/métodos desde cada símbolo.

        RF1-13: Pasa el nombre de la clase contenedora para resolver
        self.metodo() y cls.metodo() correctamente.
        """
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._extract_calls_from_symbol(filename, node.name, node)
            elif isinstance(node, ast.ClassDef):
                for item in ast.iter_child_nodes(node):
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        qname = f"{node.name}.{item.name}"
                        # RF1-13: Pasar nombre de clase para resolver self/cls
                        self._extract_calls_from_symbol(
                            filename, qname, item, class_name=node.name
                        )

    def _extract_calls_from_symbol(self, filename: str, caller_qname: str,
                                   func_node: ast.AST,
                                   class_name: str = "") -> None:
        """Extrae todas las llamadas dentro de un nodo de función.

        RF1-13: Si class_name está presente, resuelve self.metodo() y
        cls.metodo() como llamadas a métodos de la misma clase.
        """
        for node in ast.walk(func_node):
            if isinstance(node, ast.Call):
                callee_name = self._get_call_name(node)
                if callee_name:
                    # RF1-13: Resolver self.metodo() y cls.metodo()
                    if class_name and '.' in callee_name:
                        first_part = callee_name.split('.')[0]
                        if first_part in ('self', 'cls'):
                            # Reemplazar self.metodo → Clase.metodo
                            method_name = callee_name.split('.')[-1]
                            callee_name = f"{class_name}.{method_name}"
                    if callee_name:
                        # Intentar resolver el archivo del callee
                        callee_file = self._resolve_callee_file(filename, callee_name)
                        edge = CallEdge(
                            caller_file=filename,
                            caller_symbol=caller_qname,
                            callee_name=callee_name,
                            callee_file=callee_file,
                        )
                        self._call_edges.append(edge)
                        # Índice invertido — por nombre completo
                        if callee_name not in self._callee_index:
                            self._callee_index[callee_name] = []
                        self._callee_index[callee_name].append(edge)

                        # RF1-6/7: También indexar por la última parte del nombre
                        # para que mod.validar() sea encontrado al buscar "validar"
                        if '.' in callee_name:
                            short_name = callee_name.split('.')[-1]
                            if short_name not in self._callee_index:
                                self._callee_index[short_name] = []
                            self._callee_index[short_name].append(edge)

                        # RF1-18: Registrar llamadas no resueltas (sin archivo destino)
                        if callee_file is None and self._known_files:
                            # Filtrar llamadas a builtins que no necesitan resolución
                            builtin_names = {
                                'print', 'len', 'range', 'str', 'int', 'float',
                                'list', 'dict', 'set', 'tuple', 'bool', 'type',
                                'isinstance', 'hasattr', 'getattr', 'setattr',
                                'enumerate', 'zip', 'map', 'filter', 'sorted',
                                'min', 'max', 'sum', 'any', 'all', 'abs',
                                'open', 'super', 'property', 'staticmethod',
                                'classmethod', 'Exception', 'ValueError',
                                'TypeError', 'KeyError', 'IndexError',
                                'AttributeError', 'RuntimeError', 'NotImplementedError',
                                'ImportError', 'ModuleNotFoundError', 'OSError',
                                'IOError', 'FileNotFoundError', 'None',
                            }
                            callee_short = callee_name.split('.')[-1] if '.' in callee_name else callee_name
                            if callee_short not in builtin_names:
                                self._unresolved_calls.append(
                                    (filename, caller_qname, callee_name)
                                )

    def _get_call_name(self, call_node: ast.Call) -> Optional[str]:
        """Extrae el nombre de la función/método llamado."""
        func = call_node.func
        if isinstance(func, ast.Name):
            return func.id
        elif isinstance(func, ast.Attribute):
            # obj.method() → retorna "obj.method" y también "method"
            parts = []
            current = func
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
            parts.reverse()
            return '.'.join(parts)
        return None

    def _resolve_callee_file(self, caller_file: str, callee_name: str) -> Optional[str]:
        """Intenta resolver el archivo donde se define el callee.

        RF1-3: Resolución heurística por imports.
        RF1-6: También busca en imports dinámicos (importlib, __import__).
        RF1-7: También busca en aliases de getattr().
        RF1-9: También busca en re-exportaciones de __init__.py.
        """
        # Caso 1: callee_name es "module.func" → buscar module
        if '.' in callee_name:
            parts = callee_name.split('.')
            module_part = parts[0]
            # Buscar si caller_file importa este módulo (imports normales)
            alias_key = (caller_file, module_part)
            if alias_key in self._import_aliases:
                source_file, _ = self._import_aliases[alias_key]
                # RF1-12: Solo retornar si el archivo existe en el proyecto
                if source_file in self._known_files or not self._known_files:
                    return source_file
            # RF1-6: Buscar en imports dinámicos
            if alias_key in self._dynamic_aliases:
                source_file, _ = self._dynamic_aliases[alias_key]
                return source_file

        # Caso 2: callee_name es un nombre simple → buscar en imports
        alias_key = (caller_file, callee_name)
        if alias_key in self._import_aliases:
            source_file, original_name = self._import_aliases[alias_key]
            # RF1-12: Solo retornar si el archivo existe en el proyecto
            if source_file in self._known_files or not self._known_files:
                return source_file

        # RF1-6: Buscar en imports dinámicos
        if alias_key in self._dynamic_aliases:
            source_file, original_name = self._dynamic_aliases[alias_key]
            return source_file

        # RF1-7: Buscar en aliases de getattr()
        if alias_key in self._getattr_aliases:
            source_file, attr_name = self._getattr_aliases[alias_key]
            return source_file

        # Caso 3: buscar en símbolos del mismo archivo
        if (caller_file, callee_name) in self._symbols:
            return caller_file

        # Caso 4: buscar en todos los archivos (solo si no hay lista de archivos conocidos)
        if not self._known_files:
            for (f, qname), sym in self._symbols.items():
                if sym.name == callee_name or qname == callee_name:
                    return f

        # RF1-9: Buscar en re-exportaciones
        # Si el caller_file importa un paquete, y el paquete re-exporta
        # este símbolo, seguir la cadena
        caller_dir = os.path.dirname(caller_file)
        re_export_key = (caller_dir, callee_name)
        if re_export_key in self._re_exports:
            real_file, _ = self._re_exports[re_export_key]
            return real_file

        return None

    def _get_name(self, node: ast.AST) -> Optional[str]:
        """Extrae nombre de un nodo AST (para clases base)."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            parts = []
            current = node
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
            parts.reverse()
            return '.'.join(parts)
        return None

    # --- RF1-6: Imports dinámicos ---
    # --- RF1-14: Tracking de variables para imports dinámicos con variables ---

    def _extract_var_assignments(self, filename: str, tree: ast.AST) -> None:
        """Extrae asignaciones de variables a literales de cadena.

        RF1-14: Permite resolver patrones como:
          nombre = "utils"
          mod = importlib.import_module(nombre)
        """
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if not isinstance(target, ast.Name):
                        continue
                    if (isinstance(node.value, ast.Constant)
                            and isinstance(node.value.value, str)):
                        self._var_assignments[(filename, target.id)] = node.value.value

    def _extract_dynamic_imports(self, filename: str, tree: ast.AST) -> None:
        """Detecta imports dinámicos y registra sus alias.

        RF1-6: Detecta patrones como:
          mod = importlib.import_module("nombre")
          mod = __import__("nombre")
          mod = importlib.import_module("paquete.submodulo")

        RF1-14: También detecta cuando el argumento es una variable
        que contiene un string literal:
          nombre = "utils"
          mod = importlib.import_module(nombre)

        Estos alias se almacenan en _dynamic_aliases para que
        _resolve_callee_file pueda encontrarlos.
        """
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if not isinstance(target, ast.Name):
                        continue
                    var_name = target.id
                    dynamic_name = self._detect_dynamic_import_call(node.value)
                    if dynamic_name:
                        from_file = dynamic_name.replace('.', os.sep) + '.py'
                        self._dynamic_aliases[(filename, var_name)] = (from_file, dynamic_name)
                        logger.debug(
                            f"RF1-6: Import dinámico detectado en {filename}: "
                            f"{var_name} = {dynamic_name}"
                        )

    def _detect_dynamic_import_call(self, call_node: ast.AST,
                                     filename: str = "") -> Optional[str]:
        """Detecta si un nodo AST es una llamada a importlib.import_module o __import__.

        Retorna el nombre del módulo importado, o None.

        RF1-14: Si el primer argumento es una variable (Name node) en vez
        de un literal, busca su valor en _var_assignments.

        Args:
            call_node: Nodo AST a evaluar.
            filename: Archivo actual (para buscar variables).

        Returns:
            Nombre del módulo (string), o None si no es un import dinámico.
        """
        if not isinstance(call_node, ast.Call):
            return None

        func = call_node.func

        # Caso 1: importlib.import_module("nombre")
        if isinstance(func, ast.Attribute) and func.attr == 'import_module':
            # Verificar que el objeto es importlib
            if isinstance(func.value, ast.Name) and func.value.id == 'importlib':
                if call_node.args:
                    val = self._resolve_arg_to_string(call_node.args[0], filename)
                    if val:
                        return val

        # Caso 2: __import__("nombre")
        if isinstance(func, ast.Name) and func.id == '__import__':
            if call_node.args:
                val = self._resolve_arg_to_string(call_node.args[0], filename)
                if val:
                    return val

        return None

    def _resolve_arg_to_string(self, arg_node: ast.AST,
                                 filename: str) -> Optional[str]:
        """Intenta resolver un argumento AST a un string.

        RF1-14: Si es un literal de cadena, retorna directamente.
        Si es una variable (Name), busca su valor en _var_assignments.
        """
        # Literal de cadena
        if isinstance(arg_node, ast.Constant) and isinstance(arg_node.value, str):
            return arg_node.value

        # Variable — buscar en asignaciones conocidas
        if isinstance(arg_node, ast.Name) and filename:
            val = self._var_assignments.get((filename, arg_node.id))
            if val and isinstance(val, str):
                return val

        return None

    # --- RF1-7: Seguimiento de getattr() ---

    def _extract_getattr_aliases(self, filename: str, tree: ast.AST) -> None:
        """Detecta aliases creados con getattr() y los registra.

        RF1-7: Detecta patrones como:
          func = getattr(module, "nombre_funcion")
          handler = getattr(mod, "process")

        Si el primer argumento es un nombre conocido (import o alias),
        registra el resultado como alias para module.nombre.
        """
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if not isinstance(target, ast.Name):
                        continue
                    var_name = target.id
                    attr_info = self._detect_getattr_call(filename, node.value)
                    if attr_info:
                        source_file, attr_name = attr_info
                        self._getattr_aliases[(filename, var_name)] = (source_file, attr_name)
                        logger.debug(
                            f"RF1-7: getattr detectado en {filename}: "
                            f"{var_name} = ({source_file}, {attr_name})"
                        )

    def _detect_getattr_call(
        self, filename: str, call_node: ast.AST
    ) -> Optional[Tuple[str, str]]:
        """Detecta si un nodo AST es getattr(module, "attr").

        Retorna (source_file, attr_name) o None.

        Args:
            filename: Archivo donde se encuentra la llamada.
            call_node: Nodo AST a evaluar.

        Returns:
            Tupla (archivo_origen, nombre_atributo) o None.
        """
        if not isinstance(call_node, ast.Call):
            return None

        func = call_node.func

        # getattr(obj, "name") o getattr(obj, "name", default)
        if isinstance(func, ast.Name) and func.id == 'getattr':
            if len(call_node.args) >= 2:
                obj_ref = call_node.args[0]
                attr_arg = call_node.args[1]

                # El atributo debe ser una cadena literal
                if not (isinstance(attr_arg, ast.Constant)
                        and isinstance(attr_arg.value, str)):
                    return None

                attr_name = attr_arg.value

                # El objeto debe ser un Name que conozcamos
                if isinstance(obj_ref, ast.Name):
                    obj_name = obj_ref.id
                    # Buscar en aliases de import
                    alias_key = (filename, obj_name)
                    if alias_key in self._import_aliases:
                        source_file, original = self._import_aliases[alias_key]
                        return (source_file, attr_name)
                    # Buscar en aliases dinámicos (RF1-6)
                    if alias_key in self._dynamic_aliases:
                        source_file, original = self._dynamic_aliases[alias_key]
                        return (source_file, attr_name)

        return None

    # --- RF1-11: Expansión de star imports ---

    def _expand_star_imports(self, filename: str) -> None:
        """Expande from X import * registrando cada símbolo del módulo.

        RF1-11: Cuando un archivo tiene `from utils import *`, busca
        los símbolos exportados por utils.py (usando __all__ si existe,
        o todos los símbolos públicos) y los registra como alias
        individuales en _import_aliases.
        """
        for imp_name, imp_as, imp_file in list(self._imports.get(filename, [])):
            if imp_as != '*':
                continue

            # imp_file puede ser None si module estaba vacío
            if not imp_file:
                continue

            # Buscar el archivo del módulo en los archivos conocidos
            if imp_file not in self._known_files and self._known_files:
                continue

            # Obtener símbolos del módulo: prioridad __all__, luego públicos
            exported = self._get_module_exports(imp_file)
            if not exported:
                continue

            # Registrar cada símbolo exportado como alias individual
            for sym_name in exported:
                self._import_aliases[(filename, sym_name)] = (imp_file, sym_name)
                logger.debug(
                    f"RF1-11: star import expandido en {filename}: "
                    f"{sym_name} → {imp_file}"
                )

    def _get_module_exports(self, module_file: str) -> List[str]:
        """Retorna la lista de símbolos exportados por un módulo.

        RF1-11: Busca __all__ en el código fuente del módulo.
        Si no existe, retorna todos los símbolos públicos
        (los que no empiezan con _underscore).

        Args:
            module_file: Ruta del archivo del módulo.

        Returns:
            Lista de nombres de símbolos exportados.
        """
        source = self._file_sources.get(module_file)
        if not source:
            return []

        try:
            tree = ast.parse(source, filename=module_file)
        except SyntaxError:
            return []

        # Buscar asignación a __all__
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == '__all__':
                        if isinstance(node.value, ast.List):
                            names = []
                            for elt in node.value.elts:
                                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                    names.append(elt.value)
                            if names:
                                return names

        # Sin __all__: usar símbolos públicos del módulo
        syms = self._file_symbols.get(module_file, [])
        return [s.name for s in syms if not s.name.startswith('_')]

    # --- RF1-9: Re-exportaciones desde __init__.py ---

    def _resolve_re_exports(self) -> None:
        """Resuelve re-exportaciones desde archivos __init__.py.

        RF1-9: Cuando un archivo __init__.py tiene:
          from .utils import validar
        Y otro archivo hace:
          from package import validar

        Se registra que "validar" en el contexto de "package" viene
        realmente de "package/utils.py". Esto permite que el grafo
        siga la cadena de re-exportación.
        """
        for filename, source in self._file_sources.items():
            basename = os.path.basename(filename)
            if basename != '__init__.py':
                continue

            # Directorio del paquete (relativo al base_dir)
            pkg_dir = os.path.dirname(filename)
            if not pkg_dir:
                continue

            # Analizar imports del __init__.py
            tree = None
            try:
                tree = ast.parse(source, filename=filename)
            except SyntaxError:
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    level = getattr(node, 'level', 0)
                    module = node.module or ''

                    for alias in node.names:
                        import_name = alias.name
                        import_as = alias.asname or import_name

                        # Resolver de dónde viene realmente
                        if level > 0 and self._base_dir:
                            real_file = self._resolve_relative_import(
                                filename, module, level
                            )
                        else:
                            real_file = (module.replace('.', os.sep) + '.py'
                                        if module else None)

                        if real_file:
                            # Registrar: desde pkg_dir se puede acceder a import_name
                            # que viene de real_file
                            self._re_exports[(pkg_dir, import_as)] = (real_file, import_name)
                            logger.debug(
                                f"RF1-9: Re-export detectada: {pkg_dir}.{import_as} "
                                f"→ {real_file}"
                            )

    # --- Consultas ---

    # --- RF1-17: Detección de imports condicionales ---

    def _extract_conditional_imports(self, filename: str, tree: ast.AST) -> None:
        """Detecta imports dentro de bloques try/except o if que podrían no ejecutarse.

        RF1-17: Registra imports condicionales con su contexto (try/except, if, etc.)
        para que el reporte de cobertura pueda informar al Director qué imports
        son condicionales y requieren revisión manual.

        Casos detectados:
          - import X dentro de try/except ImportError
          - import X dentro de if sys.platform / hasattr / version checks
          - from X import Y dentro de cualquier bloque condicional
        """
        # Buscar imports dentro de bloques Try y If
        for node in ast.walk(tree):
            if isinstance(node, (ast.Try, ast.If)):
                context_type = ""
                context_detail = ""

                if isinstance(node, ast.Try):
                    # Verificar si es try/except ImportError
                    handlers = getattr(node, 'handlers', [])
                    for handler in handlers:
                        handler_type = getattr(handler, 'type', None)
                        if handler_type:
                            type_name = self._get_name(handler_type)
                            if type_name and ('Import' in type_name or 'Module' in type_name):
                                context_type = "try/except ImportError"
                                context_detail = f"try/except {type_name}"
                                break
                    if not context_type:
                        context_type = "try"
                        context_detail = "try/except (otro)"
                elif isinstance(node, ast.If):
                    test = node.test
                    if isinstance(test, ast.Compare):
                        context_type = "if/condicional"
                        context_detail = ast.unparse(test) if hasattr(ast, 'unparse') else "if (condición)"
                    elif isinstance(test, ast.Call) and isinstance(test.func, ast.Name):
                        if test.func.id in ('hasattr', 'callable'):
                            context_type = "if/hasattr"
                            context_detail = ast.unparse(test) if hasattr(ast, 'unparse') else "if hasattr(...)"
                        else:
                            context_type = "if/condicional"
                            context_detail = ast.unparse(test) if hasattr(ast, 'unparse') else "if (llamada)"
                    else:
                        context_type = "if/condicional"
                        try:
                            context_detail = ast.unparse(test) if hasattr(ast, 'unparse') else "if (expr)"
                        except Exception:
                            context_detail = "if (expresión)"

                if context_type:
                    # Buscar imports dentro de este bloque
                    for child in ast.walk(node):
                        if isinstance(child, ast.Import):
                            for alias in child.names:
                                lineno = getattr(child, 'lineno', 0)
                                import_text = f"import {alias.name}"
                                if alias.asname:
                                    import_text += f" as {alias.asname}"
                                self._conditional_imports.append(
                                    (filename, lineno, import_text, context_detail)
                                )
                        elif isinstance(child, ast.ImportFrom):
                            module = child.module or ''
                            level = getattr(child, 'level', 0)
                            for alias in child.names:
                                lineno = getattr(child, 'lineno', 0)
                                prefix = '.' * level if level > 0 else ''
                                module_text = f"{prefix}{module}" if module else prefix
                                import_text = f"from {module_text} import {alias.name}"
                                if alias.asname:
                                    import_text += f" as {alias.asname}"
                                self._conditional_imports.append(
                                    (filename, lineno, import_text, context_detail)
                                )

    def _is_builtin_or_stdlib(self, module_name: str) -> bool:
        """Verifica si un nombre de módulo es builtin o stdlib conocido.

        RF1-15: Usado por get_coverage_report() para clasificar imports
        externos como stdlib vs terceros.

        Args:
            module_name: Nombre del módulo (ej: "os", "requests").

        Returns:
            True si es builtin o stdlib.
        """
        stdlib_modules = {
            'abc', 'aifc', 'argparse', 'array', 'ast', 'asyncio', 'atexit',
            'base64', 'bdb', 'binascii', 'bisect', 'builtins', 'bz2',
            'calendar', 'cgi', 'cgitb', 'chunk', 'cmath', 'cmd', 'code',
            'codecs', 'codeop', 'collections', 'colorsys', 'compileall',
            'concurrent', 'configparser', 'contextlib', 'contextvars',
            'copy', 'copyreg', 'cProfile', 'csv', 'ctypes', 'curses',
            'dataclasses', 'datetime', 'dbm', 'decimal', 'difflib',
            'dis', 'distutils', 'doctest', 'email', 'encodings',
            'enum', 'errno', 'faulthandler', 'fcntl', 'filecmp',
            'fileinput', 'fnmatch', 'fractions', 'ftplib', 'functools',
            'gc', 'getopt', 'getpass', 'gettext', 'glob', 'graphlib',
            'grp', 'gzip', 'hashlib', 'heapq', 'hmac', 'html', 'http',
            'imaplib', 'imghdr', 'imp', 'importlib', 'inspect', 'io',
            'ipaddress', 'itertools', 'json', 'keyword', 'lib2to3',
            'linecache', 'locale', 'logging', 'lzma', 'mailbox',
            'mailcap', 'marshal', 'math', 'mimetypes', 'mmap',
            'modulefinder', 'multiprocessing', 'netrc', 'nis',
            'nntplib', 'numbers', 'operator', 'optparse', 'os',
            'ossaudiodev', 'pathlib', 'pdb', 'pickle', 'pickletools',
            'pipes', 'pkgutil', 'platform', 'plistlib', 'poplib',
            'posix', 'posixpath', 'pprint', 'profile', 'pstats',
            'pty', 'pwd', 'py_compile', 'pyclbr', 'pydoc', 'queue',
            'quopri', 'random', 're', 'readline', 'reprlib',
            'resource', 'rlcompleter', 'runpy', 'sched', 'secrets',
            'select', 'selectors', 'shelve', 'shlex', 'shutil',
            'signal', 'site', 'smtpd', 'smtplib', 'sndhdr', 'socket',
            'socketserver', 'spwd', 'sqlite3', 'ssl', 'stat',
            'statistics', 'string', 'struct', 'subprocess', 'sunau',
            'symtable', 'sys', 'sysconfig', 'syslog', 'tabnanny',
            'tarfile', 'telnetlib', 'tempfile', 'termios', 'test',
            'textwrap', 'threading', 'time', 'timeit', 'tkinter',
            'token', 'tokenize', 'trace', 'traceback', 'tracemalloc',
            'tty', 'turtle', 'turtledemo', 'types', 'typing', 'unicodedata',
            'unittest', 'urllib', 'uu', 'uuid', 'venv', 'warnings',
            'wave', 'weakref', 'webbrowser', 'winreg', 'winsound',
            'wsgiref', 'xdrlib', 'xml', 'xmlrpc', 'zipapp', 'zipfile',
            'zlib', 'zoneinfo',
        }
        # Verificar el primer componente del nombre
        top_level = module_name.split('.')[0]
        return top_level in stdlib_modules or top_level in sys.builtin_module_names

    # --- RF1-15: Reporte de cobertura ---

    def get_coverage_report(self) -> Dict[str, Any]:
        """Genera un reporte detallado de cobertura del análisis estático.

        RF1-15: Informa al Director qué se detectó, qué no, y por qué.
        Permite tomar decisiones informadas sobre cuándo confiar
        en el grafo y cuándo requiere revisión manual.

        El reporte incluye:
          - Resumen general: archivos, símbolos, imports, llamadas
          - Imports por categoría: resueltos, externos, condicionales, no resueltos
          - Llamadas no resueltas con detalle por archivo
          - Veredicto de confianza por archivo

        Returns:
            Dict con el reporte completo de cobertura.
        """
        report: Dict[str, Any] = {}

        # === RESUMEN GENERAL ===
        total_files = len(self._file_sources)
        total_symbols = len(self._symbols)
        total_call_edges = len(self._call_edges)
        total_imports = sum(len(imps) for imps in self._imports.values())

        report["resumen"] = {
            "archivos_procesados": total_files,
            "simbolos_detectados": total_symbols,
            "aristas_de_llamada": total_call_edges,
            "imports_totales": total_imports,
            "version_analisis": "v1.3",
            "decision_ast_puro": "RF1-1",
        }

        # === ANÁLISIS DE IMPORTS POR CATEGORÍA ===
        resolved_static = []     # (file, import_text) — resueltos a archivo del proyecto
        resolved_dynamic = []    # (file, import_text) — resueltos vía importlib/getattr
        resolved_relative = []   # (file, import_text) — resueltos vía imports relativos
        external_stdlib = []     # (file, import_text) — módulo externo stdlib
        external_third_party = [] # (file, import_text) — módulo externo terceros
        unresolved_conditional = [] # (file, lineno, import_text, context)
        unresolved_dynamic = [] # (file, import_text) — dinámico no resolvable

        for filename, imports in self._imports.items():
            for imp_name, imp_as, imp_file in imports:
                if imp_as == '*':
                    continue  # Los star imports se expanden, no se listan individualmente

                if imp_file:
                    # Import tiene un from_file calculado
                    if imp_file in self._known_files:
                        # Verificar si es relativo (contiene separador de ruta)
                        if os.sep in imp_file or '/' in imp_file:
                            resolved_relative.append((filename, f"from {imp_name} import {imp_as}"))
                        else:
                            resolved_static.append((filename, f"import {imp_name}"))
                    else:
                        # from_file apunta a algo que no existe en el proyecto
                        # Extraer el nombre del módulo desde imp_file (ej: "os.py" → "os")
                        module_for_check = imp_file.replace('.py', '').split(os.sep)[0]
                        if self._is_builtin_or_stdlib(module_for_check):
                            external_stdlib.append((filename, f"from {imp_name} import {imp_as}"))
                        else:
                            external_third_party.append((filename, f"from {imp_name} import {imp_as}"))
                else:
                    # Import sin from_file — verificar si es externo
                    top_module = imp_name.split('.')[0]
                    if self._is_builtin_or_stdlib(imp_name):
                        external_stdlib.append((filename, f"from {imp_name} import {imp_as}"))
                    else:
                        external_third_party.append((filename, f"from {imp_name} import {imp_as}"))

        # Imports dinámicos resueltos
        for (f, local_name), (src_file, orig_name) in self._dynamic_aliases.items():
            resolved_dynamic.append((f, f"{local_name} = importlib.import_module('{orig_name}')"))

        # Imports condicionales (RF1-17)
        for file, lineno, import_text, context in self._conditional_imports:
            unresolved_conditional.append((file, lineno, import_text, context))

        report["imports_por_categoria"] = {
            "resueltos_estaticos": {
                "count": len(resolved_static),
                "items": sorted(set(f"{f}: {t}" for f, t in resolved_static)),
                "confianza": "alta",
                "descripcion": "Imports estáticos resueltos a un archivo del proyecto",
            },
            "resueltos_dinamicos": {
                "count": len(resolved_dynamic),
                "items": sorted(set(f"{f}: {t}" for f, t in resolved_dynamic)),
                "confianza": "alta",
                "descripcion": "Imports dinámicos (importlib/__import__) resueltos con string literal o variable con literal",
            },
            "resueltos_relativos": {
                "count": len(resolved_relative),
                "items": sorted(set(f"{f}: {t}" for f, t in resolved_relative)),
                "confianza": "alta",
                "descripcion": "Imports relativos (from . import X) resueltos a archivo del proyecto",
            },
            "externos_stdlib": {
                "count": len(external_stdlib),
                "items": sorted(set(f"{f}: {t}" for f, t in external_stdlib)),
                "confianza": "no_aplica",
                "descripcion": "Módulos de la biblioteca estándar — no requieren resolución en el proyecto",
            },
            "externos_terceros": {
                "count": len(external_third_party),
                "items": sorted(set(f"{f}: {t}" for f, t in external_third_party)),
                "confianza": "no_aplica",
                "descripcion": "Módulos de terceros — no resueltos (dependencia externa)",
            },
            "condicionales_no_resueltos": {
                "count": len(unresolved_conditional),
                "items": sorted(set(f"{f}:{ln}: {t} ({ctx})" for f, ln, t, ctx in unresolved_conditional)),
                "confianza": "parcial",
                "descripcion": "Imports dentro de try/except o if — se detectan pero no se sabe qué rama se ejecuta",
                "accion_recomendada": "Revisar manualmente si la rama condicional puede variar en producción",
            },
        }

        # === LLAMADAS NO RESUELTAS (RF1-18) ===
        unresolved_by_file: Dict[str, List[str]] = {}
        for caller_file, caller_symbol, callee_name in self._unresolved_calls:
            if caller_file not in unresolved_by_file:
                unresolved_by_file[caller_file] = []
            unresolved_by_file[caller_file].append(
                f"{caller_symbol} → {callee_name}"
            )

        report["llamadas_no_resueltas"] = {
            "count": len(self._unresolved_calls),
            "por_archivo": {
                f: sorted(set(items))
                for f, items in unresolved_by_file.items()
            },
            "descripcion": "Llamadas a funciones/métodos cuyo archivo de definición no se pudo determinar",
            "posibles_causas": [
                "Función de módulo externo (terceros/stdlib)",
                "Llamada a través de variable o alias no rastreado",
                "Patrón de plugin o carga dinámica",
                "Método heredado no visible en el análisis estático",
            ],
        }

        # === VEREDICTO DE CONFIANZA POR ARCHIVO ===
        file_verdicts = {}
        for filename in self._file_sources:
            file_warnings = []
            unresolved_in_file = [c for c in self._unresolved_calls if c[0] == filename]
            conditionals_in_file = [c for c in self._conditional_imports if c[0] == filename]

            if not unresolved_in_file and not conditionals_in_file:
                verdict = "COMPLETO"
                confianza = "alta"
            elif unresolved_in_file and not conditionals_in_file:
                verdict = "PARCIAL"
                confianza = "media"
            elif conditionals_in_file and not unresolved_in_file:
                verdict = "CON_CONDICIONALES"
                confianza = "media"
            else:
                verdict = "PARCIAL_CON_CONDICIONALES"
                confianza = "baja"

            file_verdicts[filename] = {
                "veredicto": verdict,
                "confianza": confianza,
                "llamadas_no_resueltas": len(unresolved_in_file),
                "imports_condicionales": len(conditionals_in_file),
            }

        report["veredicto_por_archivo"] = file_verdicts

        # === VEREDICTO GENERAL ===
        total_unresolved = len(self._unresolved_calls)
        total_conditional = len(self._conditional_imports)
        total_files_with_issues = sum(
            1 for v in file_verdicts.values()
            if v["veredicto"] != "COMPLETO"
        )

        if total_files_with_issues == 0:
            verdict_general = "COMPLETO"
            confianza_general = "alta"
        elif total_files_with_issues <= max(1, total_files // 4):
            verdict_general = "ACEPTABLE"
            confianza_general = "alta"
        elif total_files_with_issues <= total_files // 2:
            verdict_general = "PARCIAL"
            confianza_general = "media"
        else:
            verdict_general = "LIMITADO"
            confianza_general = "baja"

        report["veredicto_general"] = {
            "estado": verdict_general,
            "confianza": confianza_general,
            "archivos_con_issues": total_files_with_issues,
            "archivos_sin_issues": total_files - total_files_with_issues,
            "total_llamadas_no_resueltas": total_unresolved,
            "total_imports_condicionales": total_conditional,
            "interpretacion": {
                "COMPLETO": "Todos los imports y llamadas fueron resueltos. Alta confianza en el grafo.",
                "ACEPTABLE": "La gran mayoría se resolvió. Los issues son pocos y probablemente externos.",
                "PARCIAL": "Una porción significativa no se resolvió. Revisar manualmente las advertencias.",
                "LIMITADO": "Muchos imports/llamadas no se resolvieron. El grafo puede ser incompleto.",
            },
        }

        return report

    def get_refactor_context(self, file: str, symbol_name: str) -> Dict[str, Any]:
        """Retorna contexto completo para refactorizar un símbolo.

        Args:
            file: Archivo donde está el símbolo (basename)
            symbol_name: Nombre del símbolo (simple o cualificado)

        Returns:
            Dict con:
              - llamado_por: [(file, caller_symbol), ...] — quién llama a este símbolo
              - llama_a: [symbol_name, ...] — a quién llama este símbolo
              - callers_source: [(file, symbol, source), ...] — código de callers
              - archivos_dependientes: [file, ...] — archivos que dependen de este símbolo
              - herencia: {base: [derivados], derived: [bases]} — jerarquía
        """
        context: Dict[str, Any] = {
            "llamado_por": [],
            "llama_a": [],
            "callers_source": [],
            "archivos_dependientes": [],
            "herencia": {},
        }

        # Buscar el símbolo
        target_sym = self._find_symbol(file, symbol_name)
        if not target_sym:
            logger.warning(f"No se encontro '{symbol_name}' en '{file}'")
            return context

        # 1. llamado_por: quién llama a este símbolo
        llamado_por_set: Set[Tuple[str, str]] = set()
        # Buscar por nombre simple y cualificado
        search_names = {target_sym.name, target_sym.qualified_name}
        # También buscar como "module.name" (ej: utils.validar)
        for imp_name, imp_as, imp_file in self._imports.get(file, []):
            if imp_as == target_sym.name:
                search_names.add(imp_name)

        # RF1-6: Buscar como alias de import dinámico
        # Si alguien hizo mod = importlib.import_module("utils"), y mod.validar()
        # es llamado, necesitamos "mod" en search_names para encontrar "mod.validar"
        for (f, local_name), (src_file, orig_name) in self._dynamic_aliases.items():
            if src_file == file:
                search_names.add(local_name)

        # RF1-7: Buscar como alias de getattr()
        # Si alguien hizo func = getattr(utils, "validar"), y func() es llamado,
        # necesitamos "func" en search_names
        for (f, local_name), (src_file, attr_name) in self._getattr_aliases.items():
            if src_file == file and attr_name == target_sym.name:
                search_names.add(local_name)

        # RF1-9: Buscar como re-exportación
        # Si el símbolo fue re-exportado desde un __init__.py, buscar
        # los callers que usan el paquete como prefijo
        for (pkg_dir, re_name), (real_file, real_name) in self._re_exports.items():
            if real_file == file and real_name == target_sym.name:
                search_names.add(re_name)
                # También buscar como "pkg_dir.re_name" (ej: "mi_paquete.validar")
                if pkg_dir:
                    search_names.add(f"{pkg_dir}.{re_name}" if '.' not in pkg_dir else re_name)

        for name in search_names:
            for edge in self._callee_index.get(name, []):
                llamado_por_set.add((edge.caller_file, edge.caller_symbol))

        context["llamado_por"] = sorted(llamado_por_set)

        # 2. llama_a: a quién llama este símbolo
        llama_a_set: Set[str] = set()
        for edge in self._call_edges:
            if edge.caller_file == file and edge.caller_symbol == target_sym.qualified_name:
                # Extraer el nombre final (después del último punto)
                callee_short = edge.callee_name.split('.')[-1] if '.' in edge.callee_name else edge.callee_name
                llama_a_set.add(callee_short)
        context["llama_a"] = sorted(llama_a_set)

        # 3. callers_source: código fuente de los callers
        callers_source = []
        for caller_file, caller_qname in context["llamado_por"]:
            sym = self._symbols.get((caller_file, caller_qname))
            if sym and sym.source_code:
                callers_source.append((caller_file, caller_qname, sym.source_code))
        context["callers_source"] = callers_source

        # 4. archivos_dependientes: archivos que usan este símbolo
        dep_files: Set[str] = set()
        dep_files.add(file)  # El propio archivo
        for caller_file, _ in context["llamado_por"]:
            dep_files.add(caller_file)
        # Buscar archivos que importan el archivo del símbolo
        for other_file, imports in self._imports.items():
            for imp_name, imp_as, imp_file in imports:
                if imp_file == file:
                    dep_files.add(other_file)
        context["archivos_dependientes"] = sorted(dep_files)

        # 5. herencia
        herencia: Dict[str, List[str]] = {}
        # Si es clase: buscar derivados
        if target_sym.symbol_type == "class":
            derivados = self._inheritance.get(target_sym.name, [])
            if derivados:
                herencia["derivados"] = [f"{f}:{cls}" for f, cls in derivados]
            # Buscar clases base
            if target_sym.base_classes:
                herencia["bases"] = target_sym.base_classes
        context["herencia"] = herencia

        # RF1-16: Advertencias de transparencia
        advertencias = []

        # Advertir sobre llamadas no resueltas desde el símbolo
        unresolved_from_symbol = [
            (cf, cs, cn) for cf, cs, cn in self._unresolved_calls
            if cs == target_sym.qualified_name
        ]
        if unresolved_from_symbol:
            for caller_f, caller_s, callee_n in unresolved_from_symbol:
                advertencias.append(
                    f"Llamada no resuelta: {target_sym.qualified_name} → {callee_n} "
                    f"(no se pudo determinar el archivo de destino)"
                )

        # Advertir sobre imports condicionales en archivos dependientes
        conditional_deps = [
            (f, ln, t, ctx) for f, ln, t, ctx in self._conditional_imports
            if f in [df for df, _ in context["llamado_por"]]
        ]
        if conditional_deps:
            seen = set()
            for f, ln, t, ctx in conditional_deps:
                key = f"{f}:{ln}:{t}"
                if key not in seen:
                    seen.add(key)
                    advertencias.append(
                        f"Import condicional en {f} línea {ln}: {t} — contexto: {ctx}"
                    )

        context["advertencias"] = advertencias

        return context

    def _find_symbol(self, file: str, symbol_name: str) -> Optional[SymbolInfo]:
        """Busca un símbolo por archivo y nombre (simple o cualificado)."""
        # Buscar por nombre cualificado exacto
        sym = self._symbols.get((file, symbol_name))
        if sym:
            return sym

        # Buscar por nombre simple entre los símbolos del archivo
        for (f, qname), sym in self._symbols.items():
            if f == file and (sym.name == symbol_name or qname == symbol_name):
                return sym

        # Buscar en todos los archivos
        for (f, qname), sym in self._symbols.items():
            if sym.name == symbol_name or qname == symbol_name:
                return sym

        return None

    def get_file_symbols(self, file: str) -> List[str]:
        """Retorna los nombres de símbolos en un archivo."""
        symbols = self._file_symbols.get(file, [])
        return [s.qualified_name for s in symbols]

    def get_inheritance(self, base_class_name: str) -> List[str]:
        """Retorna las clases derivadas de una clase base."""
        derivados = self._inheritance.get(base_class_name, [])
        return [f"{f}:{cls}" for f, cls in derivados]

    # --- Detección de cambios de firma ---

    def extract_signature(self, source_code: str, filename: str = "") -> Dict[str, SymbolSignature]:
        """Extrae las firmas de todos los símbolos de un código fuente.

        Retorna un dict {qualified_name: SymbolSignature}.
        Si el parseo falla, retorna dict vacío.

        Args:
            source_code: Código fuente Python a analizar.
            filename: Nombre de archivo (para mensajes de error).

        Returns:
            Dict mapeando nombres cualificados a sus firmas.
        """
        signatures = {}
        try:
            tree = ast.parse(source_code, filename=filename)
            source_lines = source_code.splitlines()

            for node in ast.iter_child_nodes(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    sig = self._make_signature_from_node(node, node.name, "function", source_lines)
                    signatures[node.name] = sig
                elif isinstance(node, ast.ClassDef):
                    sig = self._make_class_sig_from_node(node, source_lines)
                    signatures[node.name] = sig
                    for item in ast.iter_child_nodes(node):
                        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            qname = f"{node.name}.{item.name}"
                            method_sig = self._make_signature_from_node(
                                item, qname, "method", source_lines
                            )
                            signatures[qname] = method_sig
        except SyntaxError:
            pass
        return signatures

    def detect_signature_changes(
        self,
        before: str,
        after: str,
        filename: str = "",
    ) -> List[SignatureChange]:
        """Detecta cambios de firma entre dos versiones de código.

        Compara los símbolos en `before` y `after` y retorna una lista
        de SignatureChange describiendo cada cambio detectado.

        Este es el método público de RF1 que permite a RF4 y RF5
        detectar cambios de firma de forma reutilizable.

        Args:
            before: Código fuente anterior.
            after: Código fuente nuevo.
            filename: Nombre del archivo (para contexto en mensajes).

        Returns:
            Lista de SignatureChange con todos los cambios detectados.
        """
        changes = []

        before_sigs = self.extract_signature(before, filename)
        after_sigs = self.extract_signature(after, filename)

        before_names = set(before_sigs.keys())
        after_names = set(after_sigs.keys())

        # Símbolos eliminados
        for qname in sorted(before_names - after_names):
            changes.append(SignatureChange(
                symbol=qname,
                change_type="removed",
                old_signature=before_sigs[qname],
                new_signature=None,
                description=f"Símbolo eliminado: {qname}",
            ))

        # Símbolos nuevos
        for qname in sorted(after_names - before_names):
            changes.append(SignatureChange(
                symbol=qname,
                change_type="added",
                old_signature=None,
                new_signature=after_sigs[qname],
                description=f"Símbolo nuevo: {qname}",
            ))

        # Símbolos que se mantienen — comparar firmas
        for qname in sorted(before_names & after_names):
            old_sig = before_sigs[qname]
            new_sig = after_sigs[qname]
            change_type = self._compare_signatures(old_sig, new_sig)

            if change_type == "none":
                continue

            desc = {
                "signature_breaking": f"Firma de {qname} cambió de forma incompatible",
                "signature_compatible": f"Firma de {qname} cambió pero es retrocompatible",
                "body_only": f"Cuerpo de {qname} cambió (firma intacta)",
            }.get(change_type, f"Cambio en {qname}")

            changes.append(SignatureChange(
                symbol=qname,
                change_type=change_type,
                old_signature=old_sig,
                new_signature=new_sig,
                description=desc,
            ))

        return changes

    def _make_signature_from_node(
        self,
        node: ast.AST,
        qualified_name: str,
        symbol_type: str,
        source_lines: List[str],
    ) -> SymbolSignature:
        """Crea un SymbolSignature a partir de un nodo AST de función."""
        name = node.name
        lineno = getattr(node, 'lineno', 0)
        end_lineno = getattr(node, 'end_lineno', lineno)

        args = []
        defaults_count = 0
        has_kwargs = False
        has_varargs = False

        if hasattr(node, 'args') and node.args:
            func_args = node.args
            for arg in func_args.args:
                args.append(arg.arg)
            defaults_count = len(func_args.defaults) if func_args.defaults else 0
            if func_args.vararg:
                has_varargs = True
                args.append(f"*{func_args.vararg.arg}")
            if func_args.kwarg:
                has_kwargs = True
                args.append(f"**{func_args.kwarg.arg}")
            for arg in func_args.kwonlyargs:
                args.append(arg.arg)

        body_hash = ""
        if source_lines and 0 < lineno <= len(source_lines):
            end = min(end_lineno, len(source_lines))
            body_lines = source_lines[lineno:end]  # lineno es 1-based
            body_text = '\n'.join(body_lines)
            import hashlib
            body_hash = hashlib.md5(body_text.encode('utf-8')).hexdigest()[:12]

        return SymbolSignature(
            name=name,
            qualified_name=qualified_name,
            symbol_type=symbol_type,
            args=args,
            defaults_count=defaults_count,
            has_kwargs=has_kwargs,
            has_varargs=has_varargs,
            body_hash=body_hash,
        )

    def _make_class_sig_from_node(
        self,
        node: ast.ClassDef,
        source_lines: List[str],
    ) -> SymbolSignature:
        """Crea un SymbolSignature para una clase."""
        base_names = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                base_names.append(base.id)
            elif isinstance(base, ast.Attribute):
                base_names.append(self._get_name(base) or "")

        lineno = getattr(node, 'lineno', 0)
        end_lineno = getattr(node, 'end_lineno', lineno)
        body_hash = ""
        if source_lines and 0 < lineno <= len(source_lines):
            end = min(end_lineno, len(source_lines))
            body_lines = source_lines[lineno:end]
            body_text = '\n'.join(body_lines)
            import hashlib
            body_hash = hashlib.md5(body_text.encode('utf-8')).hexdigest()[:12]

        return SymbolSignature(
            name=node.name,
            qualified_name=node.name,
            symbol_type="class",
            args=base_names,
            body_hash=body_hash,
        )

    def _compare_signatures(
        self,
        orig: SymbolSignature,
        new: SymbolSignature,
    ) -> str:
        """Compara dos firmas y retorna el tipo de cambio.

        Returns:
            "none", "signature_breaking", "signature_compatible", o "body_only"
        """
        if orig.symbol_type == "class":
            if orig.args != new.args and orig.body_hash != new.body_hash:
                return "signature_breaking"
            if orig.args != new.args:
                return "signature_breaking"
            if orig.body_hash == new.body_hash:
                return "none"
            return "body_only"

        # Funciones/métodos
        signature_changed = False
        breaking = False

        orig_pos_names = [a for a in orig.args if not a.startswith('*')]
        new_pos_names = [a for a in new.args if not a.startswith('*')]

        orig_required_names = orig_pos_names[:len(orig_pos_names) - orig.defaults_count] if orig.defaults_count > 0 else orig_pos_names
        new_required_names = new_pos_names[:len(new_pos_names) - new.defaults_count] if new.defaults_count > 0 else new_pos_names

        if set(orig_required_names) - set(new_required_names):
            breaking = True
            signature_changed = True

        if set(new_required_names) - set(orig_required_names):
            breaking = True
            signature_changed = True

        new_with_defaults = set(new_pos_names) - set(orig_pos_names)
        if new_with_defaults and not breaking:
            signature_changed = True

        if orig.has_varargs != new.has_varargs or orig.has_kwargs != new.has_kwargs:
            signature_changed = True
            if orig.has_varargs and not new.has_varargs:
                breaking = True
            if orig.has_kwargs and not new.has_kwargs:
                breaking = True

        if signature_changed:
            return "signature_breaking" if breaking else "signature_compatible"

        if orig.body_hash == new.body_hash:
            return "none"

        return "body_only"

    # --- Actualización incremental del grafo ---

    def update_after_modification(
        self,
        file_path: str,
        new_content: str,
    ) -> bool:
        """Actualiza el grafo después de modificar un archivo.

        En lugar de reconstruir todo el grafo, solo re-parsea el
        archivo modificado y actualiza los índices afectados.

        Args:
            file_path: Nombre del archivo modificado (basename).
            new_content: Nuevo contenido del archivo.

        Returns:
            True si la actualización fue exitosa, False si falló.
        """
        fname = os.path.basename(file_path)

        try:
            # 1. Eliminar símbolos y aristas del archivo viejo
            old_symbols = self._file_symbols.get(fname, [])
            old_qualified_names = {s.qualified_name for s in old_symbols}

            # Eliminar del índice de símbolos
            for qname in old_qualified_names:
                self._symbols.pop((fname, qname), None)

            # Eliminar aristas donde el archivo es caller
            self._call_edges = [
                e for e in self._call_edges
                if e.caller_file != fname
            ]

            # Eliminar imports del archivo viejo
            self._imports.pop(fname, None)

            # Eliminar alias de import del archivo viejo
            keys_to_remove = [
                (f, n) for (f, n) in self._import_aliases
                if f == fname
            ]
            for key in keys_to_remove:
                del self._import_aliases[key]

            # Eliminar aliases dinámicos del archivo viejo (RF1-6)
            dyn_keys = [
                (f, n) for (f, n) in self._dynamic_aliases
                if f == fname
            ]
            for key in dyn_keys:
                del self._dynamic_aliases[key]

            # Eliminar aliases de getattr del archivo viejo (RF1-7)
            ga_keys = [
                (f, n) for (f, n) in self._getattr_aliases
                if f == fname
            ]
            for key in ga_keys:
                del self._getattr_aliases[key]

            # Eliminar imports condicionales del archivo viejo (RF1-17)
            self._conditional_imports = [
                c for c in self._conditional_imports if c[0] != fname
            ]

            # Eliminar llamadas no resueltas del archivo viejo (RF1-18)
            self._unresolved_calls = [
                u for u in self._unresolved_calls if u[0] != fname
            ]

            # Eliminar herencia definida en este archivo
            for base_name in list(self._inheritance.keys()):
                self._inheritance[base_name] = [
                    (f, cls) for f, cls in self._inheritance[base_name]
                    if f != fname
                ]
                if not self._inheritance[base_name]:
                    del self._inheritance[base_name]

            # 2. Re-construir índice invertido (callee_index)
            self._callee_index.clear()
            for edge in self._call_edges:
                if edge.callee_name not in self._callee_index:
                    self._callee_index[edge.callee_name] = []
                self._callee_index[edge.callee_name].append(edge)

            # 3. Parsear el nuevo contenido
            self._parse_file(fname, new_content)
            self._file_sources[fname] = new_content

            # 4. Re-construir callee_index con las nuevas aristas
            self._callee_index.clear()
            for edge in self._call_edges:
                if edge.callee_name not in self._callee_index:
                    self._callee_index[edge.callee_name] = []
                self._callee_index[edge.callee_name].append(edge)

            logger.info(
                f"Grafo actualizado incrementalmente para {fname} — "
                f"{len(self._symbols)} símbolos, {len(self._call_edges)} aristas"
            )
            return True

        except (SyntaxError, Exception) as e:
            logger.warning(f"Error actualizando grafo para {fname}: {e}")
            return False

    def get_symbol_count(self) -> Dict[str, int]:
        """Retorna conteo de símbolos por tipo."""
        counts: Dict[str, int] = {"function": 0, "class": 0, "method": 0}
        for sym in self._symbols.values():
            if sym.symbol_type in counts:
                counts[sym.symbol_type] += 1
        counts["total"] = sum(counts.values())
        return counts


# ============================================================================
# VALIDACIÓN AUTOCONTENIDA
# ============================================================================
def _run_validation() -> None:
    """Validacion autocontenida — 10 tests para RF1."""
    import sys

    test_results = []

    # --- Fixture: archivos de prueba ---
    main_py = '''
from utils import validar, Procesador
from helpers import verificar

def ejecutar():
    resultado = validar("datos")
    p = Procesador()
    p.procesar(resultado)
    verificar(resultado)
    return resultado
'''
    utils_py = '''
def validar(data):
    return bool(data)

def formatear(data):
    return str(data)

class Procesador:
    def __init__(self):
        self.data = None

    def procesar(self, data):
        self.data = validar(data)
        formatear(data)
        return self.data
'''
    helpers_py = '''
from utils import formatear

def verificar(data):
    return validar(data)

def limpiar(data):
    return formatear(data)
'''
    models_py = '''
class BaseValidator:
    def validate(self, data):
        return True

class StrictValidator(BaseValidator):
    def validate(self, data):
        return len(data) > 0
'''
    test_files_3 = {
        "main.py": main_py,
        "utils.py": utils_py,
        "helpers.py": helpers_py,
    }
    test_files = {
        "main.py": main_py,
        "utils.py": utils_py,
        "helpers.py": helpers_py,
        "models.py": models_py,
    }

    # --- Test 1: Construccion del grafo ---
    try:
        graph = SymbolGraph()
        graph.build_from_files(test_files_3)
        counts = graph.get_symbol_count()
        assert counts["total"] == 8, f"Esperado 8 simbolos, obtenido {counts['total']}"
        assert counts["function"] == 5, f"Esperado 5 funciones, obtenido {counts['function']}"
        assert counts["class"] == 1, f"Esperado 1 clase, obtenido {counts['class']}"
        assert counts["method"] == 2, f"Esperado 2 metodos, obtenido {counts['method']}"
        test_results.append(("Construccion del grafo (8 simbolos en 3 archivos)", True))
    except AssertionError:
        test_results.append(("Construccion del grafo (8 simbolos en 3 archivos)", False))

    # --- Test 2: get_refactor_context — llamado_por ---
    try:
        graph = SymbolGraph()
        graph.build_from_files(test_files)
        ctx = graph.get_refactor_context("utils.py", "validar")
        llamado_por = ctx["llamado_por"]
        llamado_por_names = [sym for _, sym in llamado_por]
        llamado_por_files = [f for f, _ in llamado_por]
        # validar es llamada por: ejecutar (main.py), Procesador.procesar (utils.py)
        # y verificar (helpers.py via import)
        assert len(llamado_por) > 0, "validar deberia tener callers"
        assert "ejecutar" in llamado_por_names, f"ejecutar deberia llamar a validar: {llamado_por_names}"
        test_results.append(("get_refactor_context — llamado_por", True))
    except AssertionError:
        test_results.append(("get_refactor_context — llamado_por", False))

    # --- Test 3: get_refactor_context — llama_a ---
    try:
        graph = SymbolGraph()
        graph.build_from_files(test_files)
        ctx = graph.get_refactor_context("utils.py", "Procesador.procesar")
        llama_a = ctx["llama_a"]
        assert "validar" in llama_a, f"procesar deberia llamar a validar: {llama_a}"
        assert "formatear" in llama_a, f"procesar deberia llamar a formatear: {llama_a}"
        test_results.append(("get_refactor_context — llama_a", True))
    except AssertionError:
        test_results.append(("get_refactor_context — llama_a", False))

    # --- Test 4: get_refactor_context — codigo fuente de callers ---
    try:
        graph = SymbolGraph()
        graph.build_from_files(test_files)
        ctx = graph.get_refactor_context("utils.py", "validar")
        callers = ctx["callers_source"]
        assert len(callers) > 0, "Deberia haber callers con codigo fuente"
        for caller_file, caller_sym, source in callers:
            assert source, f"Caller {caller_sym} deberia tener codigo fuente"
            assert len(source) > 0, f"Codigo fuente de {caller_sym} no deberia estar vacio"
        test_results.append(("get_refactor_context — codigo fuente de callers", True))
    except AssertionError:
        test_results.append(("get_refactor_context — codigo fuente de callers", False))

    # --- Test 5: get_refactor_context — firmas dependientes ---
    try:
        graph = SymbolGraph()
        graph.build_from_files(test_files)
        ctx = graph.get_refactor_context("utils.py", "validar")
        deps = ctx["archivos_dependientes"]
        assert "utils.py" in deps, f"utils.py deberia estar en dependientes: {deps}"
        assert "main.py" in deps, f"main.py deberia estar en dependientes: {deps}"
        test_results.append(("get_refactor_context — firmas dependientes", True))
    except AssertionError:
        test_results.append(("get_refactor_context — firmas dependientes", False))

    # --- Test 6: Herencia ---
    try:
        graph = SymbolGraph()
        graph.build_from_files({"models.py": models_py})
        derivados = graph.get_inheritance("BaseValidator")
        assert "models.py:StrictValidator" in derivados, f"StrictValidator deberia derivar de BaseValidator: {derivados}"
        test_results.append(("Herencia (BaseValidator → StrictValidator)", True))
    except AssertionError:
        test_results.append(("Herencia (BaseValidator → StrictValidator)", False))

    # --- Test 7: get_file_symbols ---
    try:
        graph = SymbolGraph()
        graph.build_from_files(test_files)
        symbols = graph.get_file_symbols("utils.py")
        assert "validar" in symbols, f"validar deberia estar en utils.py: {symbols}"
        assert "formatear" in symbols, f"formatear deberia estar en utils.py: {symbols}"
        assert "Procesador" in symbols, f"Procesador deberia estar en utils.py: {symbols}"
        test_results.append(("get_file_symbols — simbolos en utils.py", True))
    except AssertionError:
        test_results.append(("get_file_symbols — simbolos en utils.py", False))

    # --- Test 8: Simbolo no encontrado ---
    try:
        graph = SymbolGraph()
        graph.build_from_files(test_files)
        ctx = graph.get_refactor_context("utils.py", "no_existe")
        assert ctx["llamado_por"] == [], "Simbolo no existente deberia retornar contexto vacio"
        assert ctx["llama_a"] == [], "Simbolo no existente deberia retornar llama_a vacio"
        test_results.append(("Simbolo no encontrado (contexto vacio sin crash)", True))
    except AssertionError:
        test_results.append(("Simbolo no encontrado (contexto vacio sin crash)", False))

    # --- Test 9: Grafo sobre proyecto APA real ---
    try:
        graph = SymbolGraph()
        apa_dir = os.path.join(os.path.dirname(__file__), '..')
        if os.path.isdir(apa_dir):
            count = graph.build_from_directory(apa_dir)
            assert count > 0, "Deberia procesar al menos un archivo APA"
            test_results.append(("Grafo sobre proyecto APA real", True))
        else:
            # SKIP si el proyecto APA no está disponible
            test_results.append(("Grafo sobre proyecto APA real (SKIP)", True))
    except AssertionError:
        test_results.append(("Grafo sobre proyecto APA real", False))

    # --- Test 10: Criterio de aceptacion RF1 ---
    try:
        graph = SymbolGraph()
        graph.build_from_files(test_files)
        ctx = graph.get_refactor_context("utils.py", "validar")
        llamado_por_files = [f for f, _ in ctx["llamado_por"]]
        assert "main.py" in llamado_por_files, \
            f"CRITERIO RF1: main.py deberia aparecer en llamado_por de validar: {llamado_por_files}"
        test_results.append(("CRITERIO RF1: main.py en llamado_por de validar", True))
    except AssertionError:
        test_results.append(("CRITERIO RF1: main.py en llamado_por de validar", False))

    # --- Reporte ---
    passed = sum(1 for _, ok in test_results if ok)
    failed = len(test_results) - passed
    print(f"\n{'='*60}")
    print(f"symbol_graph.py v1.0 — RF1 Validation")
    print(f"{'='*60}")
    for name, ok in test_results:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}")
    print(f"\nResultado: {passed}/{len(test_results)} PASS, {failed} FAIL")
    print(f"{'='*60}")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    _run_validation()
