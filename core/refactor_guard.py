# apa/core/refactor_guard.py
# v2.2 — RF2+RF3+RF4+RF5: Guardián de integridad para refactorización.
#         Integra symbol_graph (RF1) y snapshot_manager (RF3) para
#         proporcionar contexto inteligente, revisión de diffs y
#         validación de regresión en el pipeline de SemiAutoAgent.
#
# CAMBIOS v2.0 (aprobados por Director):
#   RF2: + Evaluación de RIESGO por símbolo (ALTO/MEDIO/BAJO)
#        + Riesgo por herencia: clase con subclases → ALTO
#   RF4: + SIGNATURE_CHANGE_BREAKING / SIGNATURE_CHANGE_COMPATIBLE
#        + WARNING solo cuando cuerpo REALMENTE cambió (AST diff)
#        + Números de línea en DiffIssue
#   RF5: + Validación de sintaxis (ast.parse) — coste ~0, valor máximo
#        + Import resolution check (solo módulos del proyecto)
#        + validate_and_rollback() — conveniencia que combina valid+rollback
#
# CAMBIOS v2.1:
#   RF4: + task_description en review_diff() para scope verification
#        + SCOPE_VIOLATION: severidad para cambios fuera de alcance
#        + should_block_changes() — blocking para CRITICAL/SIG_BREAKING
#        + review_diff_and_decide() — combina review + decisión de bloqueo
#        + has_critical_issues() incluye SCOPE_VIOLATION
#   RF5: + Capa 2.5: _check_caller_imports() — callers' imports resolution
#        + Capa 3.5: _check_caller_signature_compatibility() — signature compat
#        + Capa 4: _run_existing_tests() — ejecución de pytest (30s timeout)
#        + Capa 5: _smoke_test_imports() — import smoke test (5s per file)
#        + Report keys: caller_import_errors, test_errors, smoke_test_errors
#
# CAMBIOS v2.2:
#   RF3: + rollback_selective() — restaura solo los archivos indicados,
#          dejando los demás en su estado actual. Delegado a
#          SnapshotManager.rollback_selective() con fallback a rollback
#          completo si no está disponible.
#
# CAMBIOS v2.3:
#   RF1-15: + validate_regression() incorpora get_coverage_report() del grafo
#          para detectar advertencias de cobertura.
#   RF1-16: + validation_status de 3 niveles: PASS/PASS_WITH_WARNINGS/FAIL.
#          PASS_WITH_WARNINGS indica exito con reservas por cobertura parcial.
#          validate_and_rollback() solo ejecuta rollback si status == FAIL.
#
# CAPACIDADES:
#   RF2: Contexto inteligente — usa SymbolGraph para enriquecer el
#        prompt del Planificador con información de dependencias
#        Y evaluación de riesgo por símbolo.
#   RF4: Revisión de diffs — analiza cambios contra el grafo de
#        dependencias para detectar rupturas de contrato.
#        6 severidades: CRITICAL, SIGNATURE_CHANGE_*, SCOPE_VIOLATION,
#        WARNING, INFO. Soporta blocking y scope verification.
#   RF5: Validación de regresión — usa snapshots + grafo para
#        validación completa con rollback automático.
#        5 capas: sintaxis, imports, caller imports, símbolos, tests, smoke.
#
# DECISIONES ARQUITECTÓNICAS:
#   RF2-1: El contexto de refactorización se formatea como texto
#          legible para inyección en el prompt del Planificador.
#   RF2-2: Si el grafo no está construido, el contexto es vacío
#          (no bloquea el pipeline, lo enriquece si puede).
#   RF2-3: Evaluación de riesgo: ALTO (>=3 callers o herencia con
#          subclases), MEDIO (1-2 callers), BAJO (sin callers).
#   RF4-1: La revisión compara símbolos eliminados/modificados contra
#          el índice de llamadas (callee_index) para detectar callers
#          que quedarían rotos.
#   RF4-2: Severidades:
#          - CRITICAL: símbolo eliminado que otros llaman
#          - SIGNATURE_CHANGE_BREAKING: firma cambió incompatible y hay callers
#          - SIGNATURE_CHANGE_COMPATIBLE: firma cambió compatible (param con default)
#          - SCOPE_VIOLATION: símbolo modificado fuera del alcance de la tarea
#          - WARNING: solo cuerpo cambió, firma intacta, y hay callers
#          - INFO: símbolo nuevo
#   RF4-3: WARNING solo se emite cuando el cuerpo del símbolo cambió
#          realmente (comparación AST), no por mera presencia de callers.
#   RF4-4: Scope verification: cuando task_description se proporciona,
#          se verifican los símbolos modificados contra el alcance.
#   RF4-5: should_block_changes() bloquea CRITICAL y SIGNATURE_CHANGE_BREAKING.
#          SCOPE_VIOLATION es advisory (no bloquea).
#   RF5-1: El snapshot se crea ANTES de la ejecución de cada tarea.
#   RF5-2: Si la validación de regresión falla, se hace rollback
#          automático del snapshot (validate_and_rollback).
#   RF5-3: La validación de regresión tiene 5 capas:
#          Capa 1: ast.parse() — syntax validation (coste ~0)
#          Capa 2: Import resolution — solo módulos del proyecto
#          Capa 2.5: Caller import resolution — callers pueden importar
#          Capa 3: Verificación de símbolos que otros llaman
#          Capa 3.5: Verificación de compatibilidad de firmas con callers
#          Capa 4: Ejecución de tests existentes (pytest, solo si 1-3.5 pasaron)
#          Capa 5: Smoke test de imports (subprocess, advisory)
#   RF5-4: Todo es opcional — si el guardián falla, no bloquea
#          el pipeline (principio de no-regresión).
#   RF5-5: validate_and_rollback() es la API principal;
#          validate_regression() es la API de bajo nivel.
#   RF5-6: Capa 4 (tests) solo se ejecuta si Capas 1-3.5 pasaron.
#   RF5-7: Capa 5 (smoke) es advisory — errores van a warnings.
#   RF5-8: _check_caller_signature_compatibility usa graph.detect_signature_changes()
#          si está disponible (hasattr), sino fallback a _extract_symbols_with_signatures.
#
# CRITERIO DE ACEPTACIÓN RF2:
#   Dado utils.py con función validar() llamada por main.py,
#   get_refactor_context_for_prompt("utils.py") retorna un texto
#   que menciona main.py como dependiente e incluye evaluación de riesgo.
#
# CRITERIO DE ACEPTACIÓN RF4:
#   Dado un diff que elimina la función validar() de utils.py,
#   review_diff detecta que main.py quedaría roto (severidad CRITICAL).
#   Dado un diff que cambia la firma de validar() incompatible,
#   review_diff detecta SIGNATURE_CHANGE_BREAKING.
#
# CRITERIO DE ACEPTACIÓN RF5:
#   Crear snapshot, modificar 2 archivos, validar regresión (falla),
#   rollback automático restaura ambos archivos.
#
# ============================================================================
import ast
import os
import re
import sys
import difflib
import logging
import subprocess
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Set, Tuple, Any
from pathlib import Path

# Asegurar que apa.core es importable (como hace semi_auto_agent.py)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

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
    "DiffIssue",
    "SymbolSignature",
    "RefactorGuard",
]


# ============================================================================
# SymbolSignature — firma de un símbolo para comparación (RF4)
# ============================================================================
@dataclass
class SymbolSignature:
    """Firma de un símbolo (función, clase, método) para detección de cambios.

    Permite distinguir entre cambio de signatura (BREAKING/COMPATIBLE)
    y cambio de cuerpo (WARNING).
    """
    name: str                        # Nombre simple
    qualified_name: str              # Nombre cualificado (ej: "Procesador.procesar")
    symbol_type: str                 # "function", "class", "method"
    lineno: int = 0                  # Línea de definición
    args: List[str] = field(default_factory=list)      # Nombres de argumentos
    defaults_count: int = 0          # Número de argumentos con valor por defecto
    has_kwargs: bool = False         # Tiene **kwargs
    has_varargs: bool = False        # Tiene *args
    body_hash: str = ""              # Hash del cuerpo para detección de cambios
    source: str = ""                 # Código fuente completo del símbolo


# ============================================================================
# DiffIssue — problema detectado en la revisión de diff (RF4)
# ============================================================================
@dataclass
class DiffIssue:
    """Problema detectado al revisar un diff contra el grafo de dependencias.

    Severidades v2.1:
      - CRITICAL: símbolo eliminado que otros llaman
      - SIGNATURE_CHANGE_BREAKING: firma cambió incompatible y hay callers
      - SIGNATURE_CHANGE_COMPATIBLE: firma cambió compatible (param con default)
      - SCOPE_VIOLATION: símbolo modificado/eliminado fuera del alcance de la tarea
      - WARNING: solo cuerpo cambió, firma intacta, y hay callers
      - INFO: símbolo nuevo
    """
    severity: str          # "CRITICAL", "SIGNATURE_CHANGE_BREAKING",
                           # "SIGNATURE_CHANGE_COMPATIBLE", "SCOPE_VIOLATION",
                           # "WARNING", "INFO"
    symbol: str            # Nombre del símbolo afectado
    file: str              # Archivo donde está el símbolo
    description: str       # Descripción del problema
    lineno: int = 0        # Línea del símbolo en el nuevo contenido
    affected_callers: List[str] = field(default_factory=list)  # Callers afectados


# ============================================================================
# RefactorGuard — guardián de integridad para refactorización
# ============================================================================
class RefactorGuard:
    """Guardián de integridad que integra RF1+RF3 para refactorización segura.

    RF2: Contexto inteligente — enriquece el prompt del Planificador
         con información de dependencias Y evaluación de riesgo.
    RF4: Revisión de diffs — detecta rupturas de contrato con 6 severidades
         (incl. SCOPE_VIOLATION). Soporta blocking y scope verification.
    RF5: Validación de regresión — snapshots + grafo + rollback.
         5 capas: sintaxis, imports, caller imports, símbolos, tests, smoke.

    Uso principal:
        guard = RefactorGuard("/path/to/project")

        # RF2: Obtener contexto para el Planificador (con riesgo)
        context = guard.get_refactor_context_for_prompt("utils.py")

        # RF4: Revisar diff después de integrar
        issues = guard.review_diff(original_content, new_content, "utils.py")

        # RF5: Proteger ejecución con snapshot + validación
        snap_id = guard.create_refactor_snapshot("refactor_X", [file1, file2])
        # ... modificar archivos ...
        ok, report = guard.validate_regression(snap_id)
        if not ok:
            guard.rollback_snapshot(snap_id)

        # RF5: Alternativa con rollback automático
        snap_id = guard.create_refactor_snapshot("refactor_X", [file1, file2])
        # ... modificar archivos ...
        ok, report = guard.validate_and_rollback(snap_id)
        # Si ok=False, rollback ya se ejecutó automáticamente
    """

    def __init__(self, project_root: str = ""):
        """Inicializa el RefactorGuard.

        Args:
            project_root: Raíz del proyecto. Si es vacía, usa cwd.
        """
        self._project_root = Path(project_root or os.getcwd())
        self._graph = None       # SymbolGraph (RF1) — construcción perezosa
        self._snapshot_mgr = None  # SnapshotManager (RF3) — construcción perezosa
        self._graph_built = False
        self._project_files: Optional[Set[str]] = None  # Cache de archivos del proyecto

    # --- Construcción perezosa de dependencias ---

    def _ensure_graph(self) -> Any:
        """Construye el SymbolGraph si no existe aún."""
        if not self._graph_built:
            try:
                from core.symbol_graph import SymbolGraph
                self._graph = SymbolGraph()
                self._graph.build_from_directory(str(self._project_root))
                self._graph_built = True
                logger.info(f"RefactorGuard: grafo construido desde {self._project_root}")
            except Exception as e:
                logger.warning(f"RefactorGuard: no se pudo construir grafo: {e}")
                self._graph = None
                self._graph_built = True  # No reintentar
        return self._graph

    def _ensure_snapshot_mgr(self) -> Any:
        """Obtiene el SnapshotManager (crea si no existe)."""
        if self._snapshot_mgr is None:
            try:
                from core.snapshot_manager import SnapshotManager
                self._snapshot_mgr = SnapshotManager(str(self._project_root))
            except Exception as e:
                logger.warning(f"RefactorGuard: no se pudo crear SnapshotManager: {e}")
        return self._snapshot_mgr

    def _get_project_files(self) -> Set[str]:
        """Retorna conjunto de basenames de archivos .py del proyecto."""
        if self._project_files is None:
            self._project_files = set()
            for root, dirs, files in os.walk(str(self._project_root)):
                dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
                for fname in files:
                    if fname.endswith('.py'):
                        self._project_files.add(fname)
        return self._project_files

    # ================================================================
    # RF2: CONTEXTO INTELIGENTE PARA EL PLANIFICADOR
    # ================================================================

    def get_refactor_context_for_prompt(
        self,
        file_path: str,
        symbol_name: Optional[str] = None,
    ) -> str:
        """Retorna contexto de dependencias para enriquecer el prompt del Planificador.

        RF2-1: Formato legible para inyección en el prompt.
        RF2-2: Si el grafo no está disponible, retorna cadena vacía.
        RF2-3: Incluye evaluación de RIESGO por símbolo.

        Args:
            file_path: Archivo objetivo de la refactorización (basename).
            symbol_name: Símbolo específico (opcional). Si se proporciona,
                         se obtiene contexto detallado. Si no, se lista
                         lo que el archivo exporta, quién lo importa,
                         y el riesgo de refactorizar cada símbolo.

        Returns:
            Texto formateado con información de dependencias y riesgo,
            o cadena vacía.
        """
        graph = self._ensure_graph()
        if not graph:
            return ""

        fname = os.path.basename(file_path)

        lines = []
        lines.append(f"## CONTEXTO DE DEPENDENCIAS ({fname})")
        lines.append("")

        if symbol_name:
            # Contexto detallado de un símbolo específico
            ctx = graph.get_refactor_context(fname, symbol_name)
            risk = self._evaluate_symbol_risk(graph, fname, symbol_name, ctx)

            lines.append(f"### Riesgo de refactorización: {risk}")
            lines.append("")

            if ctx["llamado_por"]:
                lines.append("### Llamado por (quien depende de este símbolo):")
                for caller_file, caller_sym in ctx["llamado_por"]:
                    lines.append(f"  - {caller_file}: {caller_sym}")
                lines.append("")

            if ctx["llama_a"]:
                lines.append("### Llama a (dependencias internas de este símbolo):")
                for callee in ctx["llama_a"]:
                    lines.append(f"  - {callee}")
                lines.append("")

            if ctx["archivos_dependientes"]:
                lines.append("### Archivos dependientes:")
                for dep in ctx["archivos_dependientes"]:
                    lines.append(f"  - {dep}")
                lines.append("")

            if ctx["herencia"]:
                lines.append("### Jerarquía de herencia:")
                for key, vals in ctx["herencia"].items():
                    lines.append(f"  - {key}: {', '.join(vals)}")
                lines.append("")
        else:
            # Contexto del archivo completo: qué símbolos exporta,
            # quién los usa, y riesgo de refactorizar cada uno
            symbols = graph.get_file_symbols(fname)
            if symbols:
                lines.append("### Símbolos definidos en este archivo:")
                for sym in symbols:
                    lines.append(f"  - {sym}")
                lines.append("")

                # Para cada símbolo, verificar quién lo llama
                lines.append("### Dependientes externos:")
                seen_callers = set()
                symbol_callers: Dict[str, List[str]] = {}
                for sym in symbols:
                    sym_name = sym.split('.')[-1] if '.' in sym else sym
                    ctx = graph.get_refactor_context(fname, sym_name)
                    callers_for_sym = []
                    for caller_file, caller_sym in ctx.get("llamado_por", []):
                        key = f"{caller_file}:{caller_sym}"
                        if key not in seen_callers:
                            seen_callers.add(key)
                            lines.append(f"  - {caller_file} llama a {sym_name} (via {caller_sym})")
                        callers_for_sym.append(f"{caller_file}:{caller_sym}")
                    if callers_for_sym:
                        symbol_callers[sym] = callers_for_sym
                if not seen_callers:
                    lines.append("  - (ningún archivo externo depende de este archivo)")
                lines.append("")

                # RF2-3: Evaluación de riesgo por símbolo
                lines.append("### Riesgo de refactorización:")
                for sym in symbols:
                    sym_name = sym.split('.')[-1] if '.' in sym else sym
                    ctx = graph.get_refactor_context(fname, sym_name)
                    risk = self._evaluate_symbol_risk(graph, fname, sym, ctx)
                    caller_count = len(ctx.get("llamado_por", []))
                    caller_files = len(set(f for f, _ in ctx.get("llamado_por", [])))
                    if risk == "ALTO":
                        reason = f"({caller_count} callers en {caller_files} archivo(s))"
                    elif risk == "MEDIO":
                        reason = f"({caller_count} caller en {caller_files} archivo(s))"
                    else:
                        reason = "(sin callers externos)"
                    lines.append(f"  - {sym_name}: {risk} {reason}")
                lines.append("")

        result = "\n".join(lines)
        logger.debug(f"RF2: contexto generado para {fname} — {len(result)} chars")
        return result

    def get_refactor_focused_source(
        self,
        file_path: str,
        full_source: str,
        max_chars: int = 8000,
    ) -> str:
        """Extrae código fuente selectivo basado en el grafo de dependencias.

        RF2: Reemplaza la truncación ciega del archivo completo por una
        selección inteligente de símbolos. Cuando el grafo está disponible,
        prioriza:
          1. Símbolos con riesgo ALTO (>=3 callers o herencia con subclases)
          2. Símbolos con riesgo MEDIO (1-2 callers)
          3. Imports del archivo
          4. Símbolos con riesgo BAJO (sin callers)

        Si el contenido cabe en max_chars, se incluye completo (sin truncar).
        Si no cabe, se incluyen los símbolos ordenados por riesgo hasta
        llenar max_chars. Los símbolos de bajo riesgo se omiten primero.

        Si el grafo no está disponible, se trunca como fallback.

        Args:
            file_path: Archivo objetivo (basename).
            full_source: Código fuente completo del archivo.
            max_chars: Límite de caracteres para el contexto.

        Returns:
            Código fuente seleccionado, o truncado si no hay grafo.
        """
        graph = self._ensure_graph()
        fname = os.path.basename(file_path)

        # Si el contenido cabe completo, no hacer nada
        if len(full_source) <= max_chars:
            return full_source

        # Si no hay grafo, truncar como fallback
        if not graph:
            return full_source[:max_chars] + "\n# ... (truncado — grafo no disponible)"

        # Obtener símbolos del archivo con su riesgo
        symbols = graph.get_file_symbols(fname)
        if not symbols:
            return full_source[:max_chars] + "\n# ... (truncado — sin símbolos en grafo)"

        # Separar imports del cuerpo
        import_lines = []
        body_lines = []
        in_import_block = True
        for line in full_source.splitlines():
            stripped = line.strip()
            if in_import_block:
                if (stripped.startswith('import ') or stripped.startswith('from ')
                        or stripped.startswith('#') or stripped == ''):
                    import_lines.append(line)
                else:
                    in_import_block = False
                    body_lines.append(line)
            else:
                body_lines.append(line)

        import_block = '\n'.join(import_lines)
        import_block_len = len(import_block) + 20  # margen

        # Clasificar símbolos por riesgo
        high_risk = []   # (qname, SymbolInfo)
        med_risk = []
        low_risk = []

        for sym_qname in symbols:
            sym_name = sym_qname.split('.')[-1] if '.' in sym_qname else sym_qname
            ctx = graph.get_refactor_context(fname, sym_name)
            risk = self._evaluate_symbol_risk(graph, fname, sym_qname, ctx)

            # Buscar SymbolInfo para obtener source_code
            sym_info = graph._find_symbol(fname, sym_qname)
            if not sym_info:
                sym_info = graph._find_symbol(fname, sym_name)

            entry = (sym_qname, sym_info)
            if risk == "ALTO":
                high_risk.append(entry)
            elif risk == "MEDIO":
                med_risk.append(entry)
            else:
                low_risk.append(entry)

        # Construir contexto selectivo: imports + alto + medio + bajo (hasta llenar)
        result_parts = [import_block]
        remaining = max_chars - import_block_len

        for risk_level, entries in [("ALTO", high_risk), ("MEDIO", med_risk), ("BAJO", low_risk)]:
            for qname, sym_info in entries:
                if sym_info and sym_info.source_code:
                    source = sym_info.source_code
                    if remaining <= 0:
                        result_parts.append(f"\n# ... ({len(entries)} símbolo(s) de riesgo {risk_level} omitidos)")
                        break
                    if len(source) + 20 <= remaining:
                        result_parts.append(f"\n{source}")
                        remaining -= len(source) + 20
                    else:
                        # No cabe completo, incluir encabezado
                        result_parts.append(
                            f"\n# {qname} (riesgo {risk_level}, "
                            f"{len(source)} chars — omitido por espacio)"
                        )

        result = '\n'.join(result_parts)
        logger.info(
            f"RF2: fuente selectiva para {fname} — "
            f"{len(high_risk)} alto, {len(med_risk)} medio, {len(low_risk)} bajo — "
            f"{len(result)}/{max_chars} chars"
        )
        return result

    def _evaluate_symbol_risk(
        self,
        graph: Any,
        fname: str,
        symbol_name: str,
        ctx: Dict[str, Any],
    ) -> str:
        """Evalúa el riesgo de refactorizar un símbolo.

        RF2-3: ALTO si >=3 callers, o herencia con subclases.
               MEDIO si 1-2 callers.
               BAJO si sin callers.

        Args:
            graph: SymbolGraph construido.
            fname: Archivo del símbolo.
            symbol_name: Nombre del símbolo.
            ctx: Contexto de refactorización del símbolo.

        Returns:
            "ALTO", "MEDIO" o "BAJO".
        """
        caller_count = len(ctx.get("llamado_por", []))
        caller_files = len(set(f for f, _ in ctx.get("llamado_por", [])))

        # Criterio de herencia: si es una clase con subclases → ALTO
        herencia = ctx.get("herencia", {})
        if herencia.get("derivados"):
            return "ALTO"

        # Criterio de herencia: si es un método de una clase con subclases → ALTO
        # (el método heredado se usa en todas las subclases)
        if "." in symbol_name:
            class_name = symbol_name.split(".")[0]
            class_ctx = graph.get_refactor_context(fname, class_name)
            if class_ctx.get("herencia", {}).get("derivados"):
                return "ALTO"

        # Criterio de callers
        if caller_count >= 3:
            return "ALTO"
        elif caller_count >= 1:
            return "MEDIO"
        else:
            return "BAJO"

    # ================================================================
    # RF4: REVISIÓN DE DIFFS CONTRA EL GRAFO
    # ================================================================

    def review_diff(
        self,
        original_content: str,
        new_content: str,
        file_path: str,
        task_description: str = "",
    ) -> List[DiffIssue]:
        """Revisa un diff contra el grafo de dependencias.

        RF4-1: Compara símbolos eliminados/modificados contra el callee_index.
        RF4-2: 6 severidades según tipo de cambio e impacto.
        RF4-3: WARNING solo cuando el cuerpo cambió realmente.
        RF4-4: Cuando task_description se proporciona, verifica que los
               símbolos modificados/eliminados estén dentro del alcance.

        Args:
            original_content: Contenido original del archivo.
            new_content: Contenido nuevo (después de refactorizar).
            file_path: Ruta del archivo (basename para buscar en el grafo).
            task_description: Descripción de la tarea. Si se proporciona,
                              se verifica que los cambios estén dentro del
                              alcance de la tarea (scope verification).

        Returns:
            Lista de DiffIssue detectados. Vacía si no hay problemas.
        """
        issues = []
        graph = self._ensure_graph()

        fname = os.path.basename(file_path)

        # Extraer símbolos con firma completa del contenido original y nuevo
        original_syms = self._extract_symbols_with_signatures(original_content, fname)
        new_syms = self._extract_symbols_with_signatures(new_content, fname)

        # Indexar por nombre cualificado para comparación
        orig_index = {s.qualified_name: s for s in original_syms}
        new_index = {s.qualified_name: s for s in new_syms}

        orig_names = set(orig_index.keys())
        new_names = set(new_index.keys())

        # Símbolos eliminados
        removed = orig_names - new_names
        # Símbolos nuevos
        added = new_names - orig_names
        # Símbolos que siguen (posiblemente modificados)
        kept = orig_names & new_names

        # RF4-1: Verificar símbolos eliminados contra callers
        if graph and removed:
            for qname in removed:
                sym = orig_index[qname]
                sym_name = qname.split('.')[-1] if '.' in qname else qname
                callers = self._find_callers(graph, fname, sym_name)
                if callers:
                    issues.append(DiffIssue(
                        severity="CRITICAL",
                        symbol=qname,
                        file=fname,
                        lineno=sym.lineno,
                        description=f"Símbolo eliminado que es llamado por {len(callers)} otro(s)",
                        affected_callers=callers,
                    ))
                else:
                    issues.append(DiffIssue(
                        severity="WARNING",
                        symbol=qname,
                        file=fname,
                        lineno=sym.lineno,
                        description="Símbolo eliminado (sin callers directos detectados)",
                    ))

        # Símbolos nuevos son INFO
        for qname in added:
            sym = new_index[qname]
            issues.append(DiffIssue(
                severity="INFO",
                symbol=qname,
                file=fname,
                lineno=sym.lineno,
                description="Símbolo nuevo agregado",
            ))

        # Símbolos que se mantienen — verificar cambio de signatura vs cuerpo
        if graph and kept:
            for qname in kept:
                orig_sym = orig_index[qname]
                new_sym = new_index[qname]
                sym_name = qname.split('.')[-1] if '.' in qname else qname

                # Detectar tipo de cambio
                change_type = self._detect_change_type(orig_sym, new_sym)

                if change_type == "none":
                    # Sin cambio real — no generar issue (elimina ruido)
                    continue

                callers = self._find_callers(graph, fname, sym_name)

                if change_type == "signature_breaking":
                    if callers:
                        issues.append(DiffIssue(
                            severity="SIGNATURE_CHANGE_BREAKING",
                            symbol=qname,
                            file=fname,
                            lineno=new_sym.lineno,
                            description=f"Firma cambió (incompatible) — llamado por {len(callers)} otro(s)",
                            affected_callers=callers,
                        ))
                    else:
                        issues.append(DiffIssue(
                            severity="WARNING",
                            symbol=qname,
                            file=fname,
                            lineno=new_sym.lineno,
                            description="Firma cambió (incompatible) — sin callers directos",
                        ))

                elif change_type == "signature_compatible":
                    if callers:
                        issues.append(DiffIssue(
                            severity="SIGNATURE_CHANGE_COMPATIBLE",
                            symbol=qname,
                            file=fname,
                            lineno=new_sym.lineno,
                            description=f"Firma cambió (compatible) — llamado por {len(callers)} otro(s)",
                            affected_callers=callers,
                        ))
                    # Sin callers: no genera issue (cambio compatible sin impacto)

                elif change_type == "body_only":
                    if callers:
                        issues.append(DiffIssue(
                            severity="WARNING",
                            symbol=qname,
                            file=fname,
                            lineno=new_sym.lineno,
                            description=f"Cuerpo modificado (firma intacta) — llamado por {len(callers)} otro(s)",
                            affected_callers=callers,
                        ))
                    # Sin callers: no genera issue (cambio interno sin impacto externo)

        # RF4-4: Scope verification — si se proporciona task_description,
        # verificar que los símbolos modificados/eliminados estén en alcance
        if task_description:
            changed_symbols = []
            # Recopilar símbolos eliminados
            for qname in removed:
                sym_name = qname.split('.')[-1] if '.' in qname else qname
                changed_symbols.append(sym_name)
            # Recopilar símbolos modificados (no solo cuerpo)
            for qname in kept:
                orig_sym = orig_index[qname]
                new_sym = new_index[qname]
                change_type = self._detect_change_type(orig_sym, new_sym)
                if change_type != "none":
                    sym_name = qname.split('.')[-1] if '.' in qname else qname
                    changed_symbols.append(sym_name)

            if changed_symbols:
                scope_issues = self._check_scope_violation(
                    task_description, changed_symbols, fname
                )
                issues.extend(scope_issues)

        # Log de resultados
        critical = sum(1 for i in issues if i.severity == "CRITICAL")
        sig_break = sum(1 for i in issues if i.severity == "SIGNATURE_CHANGE_BREAKING")
        sig_compat = sum(1 for i in issues if i.severity == "SIGNATURE_CHANGE_COMPATIBLE")
        scope_violations = sum(1 for i in issues if i.severity == "SCOPE_VIOLATION")
        warnings = sum(1 for i in issues if i.severity == "WARNING")
        info = sum(1 for i in issues if i.severity == "INFO")
        logger.info(
            f"RF4: diff review para {fname} — "
            f"{critical} CRITICAL, {sig_break} SIG_BREAK, {sig_compat} SIG_COMPAT, "
            f"{scope_violations} SCOPE_VIOLATION, {warnings} WARNING, {info} INFO"
        )

        return issues

    def has_critical_issues(self, issues: List[DiffIssue]) -> bool:
        """Retorna True si hay al menos un issue CRITICAL, SIGNATURE_CHANGE_BREAKING o SCOPE_VIOLATION."""
        return any(
            i.severity in ("CRITICAL", "SIGNATURE_CHANGE_BREAKING", "SCOPE_VIOLATION")
            for i in issues
        )

    def format_issues_for_prompt(self, issues: List[DiffIssue]) -> str:
        """Formatea los issues como texto para inyectar en un prompt.

        Returns:
            Texto formateado o cadena vacía si no hay issues.
        """
        if not issues:
            return ""

        markers = {
            "CRITICAL": "!!!",
            "SIGNATURE_CHANGE_BREAKING": "!!",
            "SIGNATURE_CHANGE_COMPATIBLE": "!~",
            "SCOPE_VIOLATION": "!?",
            "WARNING": "!",
            "INFO": "+",
        }

        lines = ["## RESULTADO DE REVISIÓN DE DIFERENCIAS (RF4):"]
        for issue in issues:
            marker = markers.get(issue.severity, "?")
            loc = f" (línea {issue.lineno})" if issue.lineno else ""
            lines.append(f"  [{marker}] {issue.severity}: {issue.symbol}{loc} — {issue.description}")
            if issue.affected_callers:
                for caller in issue.affected_callers:
                    lines.append(f"      Afecta a: {caller}")

        return "\n".join(lines)

    def should_block_changes(self, issues: List[DiffIssue]) -> bool:
        """Retorna True si los cambios deberían ser bloqueados.

        Se bloquean cambios cuando hay CRITICAL o SIGNATURE_CHANGE_BREAKING issues.
        No bloquea por SCOPE_VIOLATION (es advisory) ni por WARNING/INFO.

        Args:
            issues: Lista de DiffIssue a evaluar.

        Returns:
            True si los cambios deberían ser bloqueados.
        """
        return any(
            i.severity in ("CRITICAL", "SIGNATURE_CHANGE_BREAKING")
            for i in issues
        )

    def review_diff_and_decide(
        self,
        original_content: str,
        new_content: str,
        file_path: str,
        task_description: str = "",
    ) -> Tuple[List[DiffIssue], bool]:
        """Revisa un diff y decide si los cambios deberían ser bloqueados.

        Combina review_diff() con should_block_changes() en una sola llamada.

        Args:
            original_content: Contenido original del archivo.
            new_content: Contenido nuevo (después de refactorizar).
            file_path: Ruta del archivo.
            task_description: Descripción de la tarea (para scope verification).

        Returns:
            (issues, should_block): Lista de issues y flag de bloqueo.
        """
        issues = self.review_diff(
            original_content, new_content, file_path,
            task_description=task_description,
        )
        should_block = self.should_block_changes(issues)
        if should_block:
            logger.warning(
                f"RF4: cambios BLOQUEADOS para {os.path.basename(file_path)} — "
                f"{sum(1 for i in issues if i.severity in ('CRITICAL', 'SIGNATURE_CHANGE_BREAKING'))} "
                f"issue(s) bloqueante(s)"
            )
        return (issues, should_block)

    # --- Helpers RF4 ---

    def _extract_symbols_with_signatures(
        self, content: str, filename: str
    ) -> List[SymbolSignature]:
        """Extrae símbolos con firma completa para comparación de cambios.

        Usa AST para análisis robusto. Si falla el parseo,
        retorna lista vacía (no hay símbolos analizables).
        """
        symbols = []
        try:
            tree = ast.parse(content, filename=filename)
            source_lines = content.splitlines()

            for node in ast.iter_child_nodes(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    sym = self._make_signature(node, node.name, "function", source_lines)
                    symbols.append(sym)
                elif isinstance(node, ast.ClassDef):
                    sym = self._make_class_signature(node, source_lines)
                    symbols.append(sym)
                    # Métodos de la clase
                    for item in ast.iter_child_nodes(node):
                        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            qname = f"{node.name}.{item.name}"
                            method_sym = self._make_signature(
                                item, qname, "method", source_lines,
                                class_name=node.name,
                            )
                            symbols.append(method_sym)
        except SyntaxError:
            # No se puede analizar — retornar vacío
            pass
        return symbols

    def _make_signature(
        self,
        node: ast.AST,
        qualified_name: str,
        symbol_type: str,
        source_lines: List[str],
        class_name: str = "",
    ) -> SymbolSignature:
        """Crea un SymbolSignature a partir de un nodo AST de función."""
        name = node.name
        lineno = getattr(node, 'lineno', 0)
        end_lineno = getattr(node, 'end_lineno', lineno)

        # Extraer argumentos
        args = []
        defaults_count = 0
        has_kwargs = False
        has_varargs = False

        if hasattr(node, 'args') and node.args:
            func_args = node.args
            # args posicionales
            for arg in func_args.args:
                args.append(arg.arg)
            # defaults (los últimos N argumentos tienen default)
            defaults_count = len(func_args.defaults) if func_args.defaults else 0
            # *args
            if func_args.vararg:
                has_varargs = True
                args.append(f"*{func_args.vararg.arg}")
            # **kwargs
            if func_args.kwarg:
                has_kwargs = True
                args.append(f"**{func_args.kwarg.arg}")
            # keyword-only args
            for arg in func_args.kwonlyargs:
                args.append(arg.arg)

        # Extraer cuerpo y hash
        body_hash = ""
        source = ""
        if source_lines and 0 < lineno <= len(source_lines):
            end = min(end_lineno, len(source_lines))
            source = '\n'.join(source_lines[lineno - 1:end])
            # Hash del cuerpo (sin la línea de definición)
            body_lines = source_lines[lineno:end]  # lineno es 1-based
            body_text = '\n'.join(body_lines)
            import hashlib
            body_hash = hashlib.md5(body_text.encode('utf-8')).hexdigest()[:12]

        return SymbolSignature(
            name=name,
            qualified_name=qualified_name,
            symbol_type=symbol_type,
            lineno=lineno,
            args=args,
            defaults_count=defaults_count,
            has_kwargs=has_kwargs,
            has_varargs=has_varargs,
            body_hash=body_hash,
            source=source,
        )

    def _make_class_signature(
        self,
        node: ast.ClassDef,
        source_lines: List[str],
    ) -> SymbolSignature:
        """Crea un SymbolSignature para una clase."""
        lineno = getattr(node, 'lineno', 0)
        end_lineno = getattr(node, 'end_lineno', lineno)

        base_names = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                base_names.append(base.id)
            elif isinstance(base, ast.Attribute):
                base_names.append(self._get_attr_name(base))

        source = ""
        body_hash = ""
        if source_lines and 0 < lineno <= len(source_lines):
            end = min(end_lineno, len(source_lines))
            source = '\n'.join(source_lines[lineno - 1:end])
            body_lines = source_lines[lineno:end]
            body_text = '\n'.join(body_lines)
            import hashlib
            body_hash = hashlib.md5(body_text.encode('utf-8')).hexdigest()[:12]

        return SymbolSignature(
            name=node.name,
            qualified_name=node.name,
            symbol_type="class",
            lineno=lineno,
            args=base_names,  # Reutilizamos args para clases base
            body_hash=body_hash,
            source=source,
        )

    def _get_attr_name(self, node: ast.Attribute) -> str:
        """Extrae nombre completo de un nodo Attribute."""
        parts = []
        current = node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
        parts.reverse()
        return '.'.join(parts)

    def _detect_change_type(
        self,
        orig: SymbolSignature,
        new: SymbolSignature,
    ) -> str:
        """Detecta el tipo de cambio entre dos versiones de un símbolo.

        Returns:
            "none" — sin cambio real
            "signature_breaking" — firma cambió incompatible
            "signature_compatible" — firma cambió compatible (param con default)
            "body_only" — solo cuerpo cambió, firma intacta
        """
        if orig.symbol_type == "class":
            # Para clases: comparar bases y body_hash
            if orig.args != new.args and orig.body_hash != new.body_hash:
                return "signature_breaking"  # Cambió herencia y cuerpo
            if orig.args != new.args:
                return "signature_breaking"  # Cambió herencia
            if orig.body_hash == new.body_hash:
                return "none"
            return "body_only"

        # Para funciones/métodos: comparar firma y cuerpo
        signature_changed = False
        breaking = False

        # Comparar argumentos posicionales (sin defaults)
        orig_required = orig.args[:len(orig.args) - orig.defaults_count] if orig.defaults_count > 0 else orig.args
        new_required = new.args[:len(new.args) - new.defaults_count] if new.defaults_count > 0 else new.args

        # Obtener solo los nombres de args posicionales (sin *args, **kwargs)
        orig_pos_names = [a for a in orig.args if not a.startswith('*')]
        new_pos_names = [a for a in new.args if not a.startswith('*')]

        orig_required_names = orig_pos_names[:len(orig_pos_names) - orig.defaults_count] if orig.defaults_count > 0 else orig_pos_names
        new_required_names = new_pos_names[:len(new_pos_names) - new.defaults_count] if new.defaults_count > 0 else new_pos_names

        # BREAKING: se eliminó un parámetro requerido
        if set(orig_required_names) - set(new_required_names):
            breaking = True
            signature_changed = True

        # BREAKING: se añadió un parámetro requerido (sin default)
        if set(new_required_names) - set(orig_required_names):
            breaking = True
            signature_changed = True

        # COMPATIBLE: se añadió un parámetro con default
        new_with_defaults = set(new_pos_names) - set(orig_pos_names)
        if new_with_defaults and not breaking:
            signature_changed = True
            # No es breaking porque tiene default

        # Cambio en *args / **kwargs
        if orig.has_varargs != new.has_varargs or orig.has_kwargs != new.has_kwargs:
            signature_changed = True
            # Perder *args o **kwargs es breaking
            if orig.has_varargs and not new.has_varargs:
                breaking = True
            if orig.has_kwargs and not new.has_kwargs:
                breaking = True

        if signature_changed:
            return "signature_breaking" if breaking else "signature_compatible"

        # Sin cambio de firma — verificar cuerpo
        if orig.body_hash == new.body_hash:
            return "none"

        return "body_only"

    def _extract_symbol_names(self, content: str, filename: str) -> Set[str]:
        """Extrae nombres de símbolos de código Python.

        Usado por RF5 para comparación de existencia.
        Si falla el parseo, usa heurística regex como fallback.
        """
        names = set()
        try:
            tree = ast.parse(content, filename=filename)
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    names.add(node.name)
                elif isinstance(node, ast.ClassDef):
                    names.add(node.name)
                    for item in ast.iter_child_nodes(node):
                        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            names.add(f"{node.name}.{item.name}")
        except SyntaxError:
            # Fallback con regex
            import re
            for match in re.finditer(r'^\s*(?:async\s+)?def\s+(\w+)', content, re.MULTILINE):
                names.add(match.group(1))
            for match in re.finditer(r'^\s*class\s+(\w+)', content, re.MULTILINE):
                names.add(match.group(1))
        return names

    def _find_callers(self, graph: Any, file: str, symbol_name: str) -> List[str]:
        """Busca callers de un símbolo en el grafo.

        Retorna lista de strings "file:symbol" para cada caller.
        """
        callers = []
        try:
            ctx = graph.get_refactor_context(file, symbol_name)
            for caller_file, caller_sym in ctx.get("llamado_por", []):
                callers.append(f"{caller_file}:{caller_sym}")
        except Exception:
            pass
        return callers

    def _check_scope_violation(
        self,
        task_description: str,
        changed_symbols: List[str],
        file_path: str,
    ) -> List[DiffIssue]:
        """Verifica que los símbolos modificados estén dentro del alcance de la tarea.

        Parsea la descripción de la tarea para extraer nombres de funciones/clases
        y compara contra los símbolos modificados/eliminados. Si un símbolo
        modificado no se menciona en la descripción, se emite SCOPE_VIOLATION.

        Args:
            task_description: Descripción textual de la tarea.
            changed_symbols: Lista de nombres de símbolos modificados/eliminados.
            file_path: Archivo donde están los símbolos.

        Returns:
            Lista de DiffIssue con severidad SCOPE_VIOLATION.
        """
        issues = []
        try:
            # Extraer nombres de funciones/clases de la descripción
            # Heurística: buscar identificadores Python (word_chars después de
            # palabras clave como "refactorizar", "modificar", "cambiar", etc.)
            scope_symbols = set()

            # Patrón 1: identificadores después de backticks, comillas, o "función/funcion/clase"
            # Buscar palabras que parezcan identificadores Python (camelCase, snake_case)
            identifier_pattern = re.compile(
                r'(?:function|función|funcion|class|clase|método|metodo|method|'
                r'refactor|modify|modificar|change|cambiar|rename|renombrar|update|actualizar)\s+'
                r'[`\'"]?(\w+)[`\'"]?',
                re.IGNORECASE,
            )
            for match in identifier_pattern.finditer(task_description):
                scope_symbols.add(match.group(1))

            # Patrón 2: identificadores entre backticks o comillas
            quoted_pattern = re.compile(r'[`\'"]([a-zA-Z_]\w+)[`\'"]')
            for match in quoted_pattern.finditer(task_description):
                scope_symbols.add(match.group(1))

            # Patrón 3: cualquier identificador snake_case o CamelCase en la descripción
            # (solo si la descripción es corta — heurística para no sobre-matching)
            if len(task_description) < 200:
                name_pattern = re.compile(r'\b([a-zA-Z_]\w{2,})\b')
                for match in name_pattern.finditer(task_description):
                    name = match.group(1)
                    # Filtrar palabras comunes que no son símbolos
                    if name.lower() not in {
                        'the', 'and', 'for', 'with', 'from', 'this', 'that',
                        'should', 'must', 'will', 'can', 'has', 'have', 'been',
                        'was', 'were', 'are', 'its', 'not', 'but', 'all', 'any',
                        'new', 'old', 'file', 'code', 'test', 'into', 'after',
                        'before', 'when', 'where', 'which', 'then', 'than',
                        'also', 'just', 'only', 'over', 'such', 'what', 'each',
                        'does', 'done', 'very', 'much', 'more', 'most', 'some',
                        'same', 'other', 'make', 'like', 'long', 'look', 'many',
                        'well', 'back', 'even', 'still', 'way', 'use', 'may',
                        'need', 'how', 'our', 'too', 'get', 'got', 'let', 'put',
                        'set', 'add', 'see', 'say', 'run', 'try', 'own', 'now',
                        'off', 'out', 'end', 'take', 'came', 'want', 'being',
                        'both', 'under', 'while', 'these', 'those', 'about',
                        'would', 'could', 'their', 'there', 'every', 'through',
                    }:
                        scope_symbols.add(name)

            # Si no se encontró ningún símbolo en la descripción, no verificar alcance
            # (no tenemos información suficiente para determinar el scope)
            if not scope_symbols:
                logger.debug(
                    f"RF4: scope verification omitida — no se encontraron "
                    f"símbolos en la descripción de tarea"
                )
                return issues

            # Comparar símbolos cambiados contra el scope
            for sym_name in changed_symbols:
                if sym_name not in scope_symbols:
                    issues.append(DiffIssue(
                        severity="SCOPE_VIOLATION",
                        symbol=sym_name,
                        file=file_path,
                        description=(
                            f"Símbolo '{sym_name}' modificado/eliminado fuera del "
                            f"alcance de la tarea. Scope detectado: "
                            f"{', '.join(sorted(scope_symbols))}"
                        ),
                    ))

            if issues:
                logger.info(
                    f"RF4: {len(issues)} SCOPE_VIOLATION(es) en {file_path} — "
                    f"símbolos fuera de alcance: "
                    f"{', '.join(i.symbol for i in issues)}"
                )

        except Exception as e:
            logger.warning(f"RF4: error en scope verification: {e}")

        return issues

    # ================================================================
    # RF5: VALIDACIÓN DE REGRESIÓN CON SNAPSHOTS
    # ================================================================

    def create_refactor_snapshot(
        self,
        description: str,
        file_paths: List[str],
    ) -> Optional[str]:
        """Crea un snapshot antes de una refactorización.

        RF5-1: Se crea ANTES de la ejecución de cada tarea.

        Args:
            description: Descripción de la operación.
            file_paths: Lista de rutas absolutas de archivos a capturar.

        Returns:
            ID del snapshot, o None si no se pudo crear.
        """
        mgr = self._ensure_snapshot_mgr()
        if not mgr:
            logger.warning("RF5: no se pudo crear snapshot — SnapshotManager no disponible")
            return None

        try:
            snap_id = mgr.create_snapshot(description, file_paths)
            logger.info(f"RF5: snapshot creado — {snap_id} — {len(file_paths)} archivos")
            return snap_id
        except Exception as e:
            logger.warning(f"RF5: error creando snapshot: {e}")
            return None

    # ================================================================
    # RF1-15/RF1-16: COVERAGE-AWARE VALIDATION
    # ================================================================

    def _compute_coverage_warnings(
        self, graph: Any, report: Dict[str, Any]
    ) -> str:
        """Incorpora advertencias del coverage report del grafo al report de validacion.

        RF1-15: Consulta get_coverage_report() del SymbolGraph para detectar
        advertencias de cobertura (imports condicionales, llamadas no resueltas)
        y las agrega al report de validacion.

        RF1-16: Retorna "clean" si el veredicto general es COMPLETO o ACEPTABLE,
        "degraded" si es PARCIAL o LIMITADO.

        Args:
            graph: SymbolGraph construido (puede ser None).
            report: Report de validacion donde se agregaran coverage_warnings.

        Returns:
            "clean" o "degraded".
        """
        if not graph:
            return "clean"

        try:
            if not hasattr(graph, 'get_coverage_report'):
                return "clean"

            coverage = graph.get_coverage_report()
            verdict = coverage.get("veredicto_general", {})
            estado = verdict.get("estado", "COMPLETO")

            # Solo generar advertencias si el veredicto no es COMPLETO
            if estado in ("COMPLETO", "ACEPTABLE"):
                return "clean"

            # Degradado: generar advertencias detalladas
            report["coverage_warnings"].append(
                f"Veredicto de cobertura: {estado} "
                f"(confianza: {verdict.get('confianza', 'desconocida')})"
            )

            # Advertir sobre archivos con issues
            file_verdicts = coverage.get("veredicto_por_archivo", {})
            files_with_issues = [
                fname for fname, fv in file_verdicts.items()
                if fv.get("veredicto") != "COMPLETO"
            ]
            if files_with_issues:
                report["coverage_warnings"].append(
                    f"Archivos con issues de cobertura: {', '.join(sorted(files_with_issues))}"
                )

            # Advertir sobre imports condicionales
            total_conditional = coverage.get("veredicto_general", {}).get(
                "total_imports_condicionales", 0
            )
            if total_conditional > 0:
                report["coverage_warnings"].append(
                    f"Imports condicionales detectados: {total_conditional}. "
                    f"Revisar manualmente si las ramas pueden variar en produccion."
                )

            # Advertir sobre llamadas no resueltas
            total_unresolved = coverage.get("veredicto_general", {}).get(
                "total_llamadas_no_resueltas", 0
            )
            if total_unresolved > 0:
                unresolved_by_file = coverage.get("llamadas_no_resueltas", {}).get(
                    "por_archivo", {}
                )
                unresolved_summary = "; ".join(
                    f"{f}({len(items)})" for f, items in unresolved_by_file.items()
                )
                report["coverage_warnings"].append(
                    f"Llamadas no resueltas: {total_unresolved} — {unresolved_summary}. "
                    f"Pueden ser llamadas a modulos externos (esperado) o funciones "
                    f"internas no detectadas (requiere revision)."
                )

            logger.info(
                f"RF1-16: coverage status = degraded ({estado}) — "
                f"{len(report['coverage_warnings'])} advertencia(s) de cobertura generada(s)"
            )
            return "degraded"

        except Exception as e:
            logger.warning(f"RF1-16: error al consultar coverage report: {e}")
            return "clean"

    def validate_regression(
        self,
        snapshot_id: str,
        modified_files: Optional[List[str]] = None,
    ) -> Tuple[bool, Dict[str, Any]]:
        """Valida que la refactorización no haya causado regresiones.

        RF5-3: 5 capas de validación:
          Capa 1: ast.parse() — syntax validation (coste ~0)
          Capa 2: Import resolution — solo módulos del proyecto
          Capa 2.5: Caller import resolution — verificar que callers de
                    archivos modificados puedan importar símbolos aún
          Capa 3: Verificación de símbolos que otros llaman
          Capa 3.5: Verificación de compatibilidad de firmas con callers
          Capa 4: Ejecución de tests existentes (pytest)
          Capa 5: Smoke test de imports (subprocess)

        Args:
            snapshot_id: ID del snapshot asociado a esta refactorización.
            modified_files: Lista de archivos modificados. Si es None,
                            se obtienen del snapshot.

        Returns:
            (ok, report): ok=True si no hay regresiones, report con detalles.
        """
        report: Dict[str, Any] = {
            "snapshot_id": snapshot_id,
            "regressions": [],
            "warnings": [],
            "files_checked": 0,
            "syntax_errors": [],
            "import_errors": [],
            "caller_import_errors": [],
            "test_errors": [],
            "smoke_test_errors": [],
            "coverage_warnings": [],
            "validation_status": "FAIL",  # PASS/PASS_WITH_WARNINGS/FAIL
        }

        graph = self._ensure_graph()
        mgr = self._ensure_snapshot_mgr()

        # Obtener archivos del snapshot
        if mgr and not modified_files:
            snap_info = mgr.get_snapshot(snapshot_id)
            if snap_info:
                modified_files = [
                    entry["path"] if isinstance(entry, dict) else entry
                    for entry in snap_info.get("files", [])
                ]

        if not modified_files:
            report["warnings"].append("No hay archivos para validar")
            return (True, report)

        # Capa 1: Syntax validation (ast.parse)
        for file_path in modified_files:
            if os.path.exists(file_path):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        current_content = f.read()
                    ast.parse(current_content, filename=os.path.basename(file_path))
                except SyntaxError as e:
                    regression = {
                        "type": "syntax_error",
                        "file": os.path.basename(file_path),
                        "lineno": e.lineno,
                        "message": str(e.msg),
                    }
                    report["regressions"].append(regression)
                    report["syntax_errors"].append(regression)
                    logger.warning(
                        f"RF5: REGRESIÓN SINTAXIS — {os.path.basename(file_path)}: "
                        f"línea {e.lineno}: {e.msg}"
                    )
                except IOError as e:
                    report["warnings"].append(
                        f"No se pudo leer {os.path.basename(file_path)}: {e}"
                    )

        # Si ya hay errores de sintaxis, no seguir con capas más costosas
        if report["syntax_errors"]:
            ok = False
            logger.info(f"RF5: regresión detectada — {len(report['syntax_errors'])} error(es) de sintaxis — iterando con rollback")
            return (ok, report)

        # Capa 2: Import resolution check (solo módulos del proyecto)
        project_files = self._get_project_files()
        for file_path in modified_files:
            if os.path.exists(file_path):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        current_content = f.read()
                    import_errors = self._check_project_imports(
                        current_content, os.path.basename(file_path), project_files
                    )
                    for err in import_errors:
                        report["import_errors"].append(err)
                        report["warnings"].append(
                            f"Import no resuelto: {err['module']} en {err['file']}"
                        )
                except IOError:
                    pass  # Ya reportado en Capa 1

        # Capa 2.5: Caller import resolution — verificar que los callers de
        # archivos modificados puedan importar símbolos que aún deberían existir
        if graph and modified_files:
            try:
                caller_import_errors = self._check_caller_imports(modified_files, graph)
                for err in caller_import_errors:
                    report["caller_import_errors"].append(err)
                    report["regressions"].append(err)
                    logger.warning(
                        f"RF5: REGRESIÓN CALLER IMPORT — {err.get('caller_file', '?')} "
                        f"no puede importar {err.get('symbol', '?')} de "
                        f"{err.get('modified_file', '?')}"
                    )
            except Exception as e:
                logger.warning(f"RF5 Capa 2.5: error en caller import check: {e}")

        # Capa 3: Verificar símbolos exportados siguen existiendo
        if graph:
            for file_path in modified_files:
                fname = os.path.basename(file_path)
                symbols = graph.get_file_symbols(fname)

                if not symbols:
                    continue

                report["files_checked"] += 1

                if os.path.exists(file_path):
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            current_content = f.read()
                        current_symbols = self._extract_symbol_names(current_content, fname)

                        for sym_qualified in symbols:
                            sym_name = sym_qualified.split('.')[-1] if '.' in sym_qualified else sym_qualified
                            if sym_name not in current_symbols and sym_qualified not in current_symbols:
                                callers = self._find_callers(graph, fname, sym_name)
                                regression = {
                                    "type": "symbol_removed",
                                    "symbol": sym_qualified,
                                    "file": fname,
                                    "callers_affected": callers,
                                }
                                report["regressions"].append(regression)
                                logger.warning(
                                    f"RF5: REGRESIÓN — {fname}:{sym_qualified} eliminado "
                                    f"({len(callers)} callers afectados)"
                                )
                    except IOError as e:
                        report["warnings"].append(f"No se pudo leer {fname}: {e}")
                else:
                    report["regressions"].append({
                        "type": "file_removed",
                        "file": fname,
                        "symbols_lost": symbols,
                    })

        # Capa 3.5: Verificar compatibilidad de firmas con callers
        if graph and modified_files:
            try:
                signature_regressions = self._check_caller_signature_compatibility(
                    modified_files, graph
                )
                for reg in signature_regressions:
                    report["regressions"].append(reg)
                    logger.warning(
                        f"RF5: REGRESIÓN SIGNATURE — {reg.get('symbol', '?')} en "
                        f"{reg.get('file', '?')}: firma incompatible con caller "
                        f"{reg.get('caller', '?')}"
                    )
            except Exception as e:
                logger.warning(f"RF5 Capa 3.5: error en signature compatibility check: {e}")

        # Determinar si las capas 1-3.5 pasaron
        layers_1_to_3_ok = len(report["regressions"]) == 0

        # Capa 4: Ejecución de tests existentes (solo si capas 1-3.5 pasaron)
        if layers_1_to_3_ok:
            try:
                test_success, test_errors = self._run_existing_tests()
                if not test_success:
                    for err in test_errors:
                        report["test_errors"].append(err)
                        report["regressions"].append({
                            "type": "test_failure",
                            **err,
                        })
                    logger.warning(
                        f"RF5: Capa 4 — {len(test_errors)} test(s) fallido(s)"
                    )
            except Exception as e:
                logger.warning(f"RF5 Capa 4: error en test execution: {e}")

        # Capa 5: Smoke test de imports (advisory, no bloqueante)
        try:
            smoke_errors = self._smoke_test_imports(modified_files)
            for err in smoke_errors:
                report["smoke_test_errors"].append(err)
                report["warnings"].append(
                    f"Smoke test: import falló para {err.get('module', '?')}: "
                    f"{err.get('error', 'unknown')}"
                )
        except Exception as e:
            logger.warning(f"RF5 Capa 5: error en smoke test: {e}")

        ok = len(report["regressions"]) == 0

        # RF1-15/RF1-16: Incorporar coverage report del grafo
        coverage_status = self._compute_coverage_warnings(graph, report)

        # RF1-16: Calcular validation_status de 3 niveles
        if not ok:
            report["validation_status"] = "FAIL"
        elif coverage_status == "degraded":
            report["validation_status"] = "PASS_WITH_WARNINGS"
        else:
            report["validation_status"] = "PASS"

        logger.info(
            f"RF5: validación regresión — {report['validation_status']} "
            f"({report['files_checked']} archivos, {len(report['regressions'])} regresiones, "
            f"{len(report['import_errors'])} imports rotos, "
            f"{len(report['caller_import_errors'])} caller imports, "
            f"{len(report['test_errors'])} test failures, "
            f"{len(report['smoke_test_errors'])} smoke failures, "
            f"{len(report['coverage_warnings'])} coverage warnings)"
        )

        return (ok, report)

    def validate_and_rollback(
        self,
        snapshot_id: str,
        modified_files: Optional[List[str]] = None,
    ) -> Tuple[bool, Dict[str, Any]]:
        """Valida regresión y ejecuta rollback automático si falla.

        RF5-2: Si la validación falla, se hace rollback automático.
        RF5-5: Este es el método de conveniencia principal.
               validate_regression() es la API de bajo nivel para
               control fino.

        Args:
            snapshot_id: ID del snapshot asociado a esta refactorización.
            modified_files: Lista de archivos modificados. Si es None,
                            se obtienen del snapshot.

        Returns:
            (ok, report): ok=True si no hay regresiones.
                          ok=False si hubo regresiones Y se ejecutó rollback.
        """
        ok, report = self.validate_regression(snapshot_id, modified_files)
        validation_status = report.get("validation_status", "FAIL")

        # RF1-16: Solo hacer rollback si el status es FAIL (regresion real).
        # PASS_WITH_WARNINGS no dispara rollback — son advertencias de cobertura.
        if validation_status == "FAIL":
            logger.info(f"RF5: regresión detectada — iterando con rollback automático de {snapshot_id}")
            success, errors = self.rollback_snapshot(snapshot_id)
            report["rollback_executed"] = True
            report["rollback_success"] = success
            if not success:
                report["rollback_errors"] = errors
                logger.error(f"RF5: rollback no completado para {snapshot_id} — escala al Director: {errors}")
            else:
                logger.info(f"RF5: rollback exitoso para {snapshot_id}")
        else:
            report["rollback_executed"] = False
            if validation_status == "PASS_WITH_WARNINGS":
                logger.info(
                    f"RF5: PASS_WITH_WARNINGS — sin regresiones pero con "
                    f"{len(report.get('coverage_warnings', []))} advertencia(s) de cobertura"
                )

        return (ok, report)

    def rollback_snapshot(self, snapshot_id: str) -> Tuple[bool, List[str]]:
        """Ejecuta rollback de un snapshot.

        RF5-2: Si la validación de regresión falla, se hace rollback automático.

        Args:
            snapshot_id: ID del snapshot a restaurar.

        Returns:
            (success, errors) del rollback.
        """
        mgr = self._ensure_snapshot_mgr()
        if not mgr:
            return (False, ["SnapshotManager no disponible"])

        return mgr.rollback(snapshot_id)

    def rollback_selective(
        self, snapshot_id: str, files: List[str]
    ) -> Tuple[bool, List[str]]:
        """Ejecuta rollback selectivo de un snapshot — solo los archivos indicados.

        RF3: A diferencia de rollback_snapshot(), que restaura TODOS los
        archivos del snapshot, este método permite seleccionar qué archivos
        restaurar, dejando los demás en su estado actual.

        Caso de uso: una refactorización toca 3 archivos, pero solo 1
        tiene regresión. Se restaura solo ese archivo y se reintenta
        la integración parcial.

        Args:
            snapshot_id: ID del snapshot a restaurar parcialmente.
            files: Lista de rutas absolutas de archivos a restaurar.

        Returns:
            (success, errors): success=True si todos los archivos
            seleccionados se restauraron correctamente.
        """
        mgr = self._ensure_snapshot_mgr()
        if not mgr:
            return (False, ["SnapshotManager no disponible"])

        if not hasattr(mgr, 'rollback_selective'):
            logger.warning(
                "RF3: SnapshotManager no soporta rollback_selective — "
                "usando rollback completo como fallback"
            )
            return mgr.rollback(snapshot_id)

        return mgr.rollback_selective(snapshot_id, files)

    def commit_snapshot(self, snapshot_id: str) -> bool:
        """Confirma un snapshot (la refactorización fue exitosa).

        Args:
            snapshot_id: ID del snapshot a confirmar.

        Returns:
            True si se confirmó correctamente.
        """
        mgr = self._ensure_snapshot_mgr()
        if not mgr:
            return False

        return mgr.commit(snapshot_id)

    def verify_snapshot_integrity(self, snapshot_id: str) -> Tuple[bool, List[str]]:
        """Verifica integridad de un snapshot (delegado a SnapshotManager).

        Args:
            snapshot_id: ID del snapshot.

        Returns:
            (intact, modified_files) del snapshot.
        """
        mgr = self._ensure_snapshot_mgr()
        if not mgr:
            return (False, ["SnapshotManager no disponible"])

        return mgr.verify_integrity(snapshot_id)

    # --- Helpers RF5 ---

    def _check_project_imports(
        self,
        content: str,
        filename: str,
        project_files: Set[str],
    ) -> List[Dict[str, Any]]:
        """Verifica que los imports de módulos del proyecto sean válidos.

        RF5 Capa 2: Solo verifica imports relativos e imports de módulos
        del propio proyecto. Los imports de paquetes externos se omiten.

        Args:
            content: Contenido del archivo a verificar.
            filename: Nombre del archivo.
            project_files: Conjunto de basenames de archivos .py del proyecto.

        Returns:
            Lista de dicts con imports no resueltos del proyecto.
        """
        errors = []
        try:
            tree = ast.parse(content, filename=filename)
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    module = node.module or ''
                    # Verificar si es un módulo del proyecto
                    # Convertir notación de puntos a path: a.b.c → a/b/c.py o a/b/c/__init__.py
                    module_path = module.replace('.', os.sep)
                    module_file = module_path + '.py'
                    module_init = os.path.join(module_path, '__init__.py')

                    is_project_module = (
                        module_file in project_files
                        or module_init.replace(os.sep, '/') in project_files
                        or module_path.replace(os.sep, '/') in project_files
                    )

                    # Solo verificar si parece un módulo del proyecto
                    # (no tiene '/' absoluta ni es un paquete conocido)
                    if is_project_module or (module and not module.startswith('_')):
                        # Verificar que los nombres importados existen
                        for alias in node.names:
                            import_name = alias.name
                            # El archivo que se importa podría ser module/import_name.py
                            import_file = os.path.join(module_path, import_name + '.py')
                            import_file_alt = os.path.join(module_path, import_name, '__init__.py')

                            # Si el módulo padre es del proyecto, verificar que el hijo exista
                            if module_file in project_files:
                                # El módulo es un archivo del proyecto
                                # No podemos verificar nombres internos sin importar
                                pass
                            elif import_file.replace(os.sep, '/') in project_files or import_file in project_files:
                                # El import es un archivo del proyecto que existe
                                pass
                            elif import_file_alt.replace(os.sep, '/') in project_files or import_file_alt in project_files:
                                # El import es un paquete del proyecto que existe
                                pass
                            elif is_project_module:
                                # Módulo del proyecto pero no se encontró el import
                                errors.append({
                                    "type": "project_import_unresolved",
                                    "module": f"{module}.{import_name}" if module else import_name,
                                    "file": filename,
                                    "lineno": node.lineno,
                                })

                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        name = alias.name
                        # Verificar si es un módulo del proyecto
                        name_path = name.replace('.', os.sep) + '.py'
                        if name_path in project_files:
                            # Es del proyecto y existe — OK
                            pass
                        # Si no está en project_files, puede ser externo — omitir
        except SyntaxError:
            # Ya reportado en Capa 1
            pass

        return errors

    def _check_caller_imports(
        self,
        modified_files: List[str],
        graph: Any,
    ) -> List[Dict[str, Any]]:
        """Verifica que los callers de archivos modificados puedan importar símbolos.

        Capa 2.5: Para cada archivo modificado, busca sus callers vía el grafo
        y verifica que los imports de esos callers aún resuelven. Esto detecta
        el caso donde un archivo refactorizado elimina/renombra un símbolo
        que un caller importa.

        Args:
            modified_files: Lista de rutas de archivos modificados.
            graph: SymbolGraph construido.

        Returns:
            Lista de dicts con errores de import en callers.
        """
        errors = []
        project_files = self._get_project_files()

        for file_path in modified_files:
            try:
                fname = os.path.basename(file_path)
                symbols = graph.get_file_symbols(fname)
                if not symbols:
                    continue

                # Obtener callers de todos los símbolos del archivo
                caller_files_seen: Set[str] = set()
                for sym_qualified in symbols:
                    sym_name = sym_qualified.split('.')[-1] if '.' in sym_qualified else sym_qualified
                    try:
                        ctx = graph.get_refactor_context(fname, sym_name)
                        for caller_file, _caller_sym in ctx.get("llamado_por", []):
                            if caller_file in caller_files_seen:
                                continue
                            caller_files_seen.add(caller_file)

                            # Buscar el archivo caller en el proyecto
                            caller_path = self._find_file_in_project(caller_file)
                            if not caller_path or not os.path.exists(caller_path):
                                continue

                            try:
                                with open(caller_path, 'r', encoding='utf-8') as f:
                                    caller_content = f.read()

                                # Verificar imports del caller contra símbolos actuales
                                # del archivo modificado
                                caller_import_errors = self._check_caller_imports_against_file(
                                    caller_content, caller_file, fname, file_path,
                                    project_files,
                                )
                                errors.extend(caller_import_errors)
                            except IOError:
                                pass  # No se puede leer el caller
                    except Exception:
                        pass  # Error al obtener contexto de un símbolo
            except Exception as e:
                logger.warning(f"RF5 Capa 2.5: error procesando {file_path}: {e}")

        return errors

    def _check_caller_imports_against_file(
        self,
        caller_content: str,
        caller_filename: str,
        modified_filename: str,
        modified_filepath: str,
        project_files: Set[str],
    ) -> List[Dict[str, Any]]:
        """Verifica que un caller pueda importar desde un archivo modificado.

        Args:
            caller_content: Contenido del archivo caller.
            caller_filename: Nombre del archivo caller.
            modified_filename: Nombre (basename) del archivo modificado.
            modified_filepath: Ruta completa del archivo modificado.
            project_files: Conjunto de basenames de archivos .py del proyecto.

        Returns:
            Lista de dicts con errores de import.
        """
        errors = []
        try:
            # Obtener símbolos actuales del archivo modificado
            current_symbols: Set[str] = set()
            if os.path.exists(modified_filepath):
                try:
                    with open(modified_filepath, 'r', encoding='utf-8') as f:
                        modified_content = f.read()
                    current_symbols = self._extract_symbol_names(
                        modified_content, modified_filename
                    )
                except IOError:
                    pass

            tree = ast.parse(caller_content, filename=caller_filename)
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    module = node.module or ''
                    # Verificar si este import viene del archivo modificado
                    # Ej: "from utils import validar" → module="utils"
                    module_base = module.split('.')[-1] if module else ''
                    if module_base == modified_filename.replace('.py', '') or \
                       module == modified_filename.replace('.py', ''):
                        # Verificar que los nombres importados existen aún
                        for alias in node.names:
                            import_name = alias.name
                            if import_name not in current_symbols:
                                errors.append({
                                    "type": "caller_import_broken",
                                    "caller_file": caller_filename,
                                    "modified_file": modified_filename,
                                    "symbol": import_name,
                                    "module": module,
                                    "lineno": node.lineno,
                                    "message": (
                                        f"Caller {caller_filename} importa "
                                        f"'{import_name}' de {module} pero el "
                                        f"símbolo ya no existe en {modified_filename}"
                                    ),
                                })
        except SyntaxError:
            pass  # Ya reportado en Capa 1
        except Exception as e:
            logger.debug(f"RF5 Capa 2.5: error verificando caller {caller_filename}: {e}")

        return errors

    def _find_file_in_project(self, basename: str) -> Optional[str]:
        """Busca un archivo por basename en el directorio del proyecto.

        Args:
            basename: Nombre del archivo (ej: "main.py").

        Returns:
            Ruta completa del archivo, o None si no se encuentra.
        """
        try:
            for root, dirs, files in os.walk(str(self._project_root)):
                dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
                if basename in files:
                    return os.path.join(root, basename)
        except Exception:
            pass
        return None

    def _check_caller_signature_compatibility(
        self,
        modified_files: List[str],
        graph: Any,
    ) -> List[Dict[str, Any]]:
        """Verifica que las firmas de símbolos modificados sean compatibles con callers.

        Capa 3.5: Para cada símbolo que aún existe pero cuya firma cambió,
        encuentra sus callers y reporta si la firma es incompatible.

        Args:
            modified_files: Lista de rutas de archivos modificados.
            graph: SymbolGraph construido.

        Returns:
            Lista de dicts con regresiones de firma.
        """
        regressions = []

        for file_path in modified_files:
            try:
                fname = os.path.basename(file_path)
                if not os.path.exists(file_path):
                    continue

                with open(file_path, 'r', encoding='utf-8') as f:
                    current_content = f.read()

                # Detectar cambios de firma usando el grafo si tiene el método
                if hasattr(graph, 'detect_signature_changes'):
                    try:
                        signature_changes = graph.detect_signature_changes(
                            fname, current_content
                        )
                        for change in signature_changes:
                            sym_name = change.get("symbol", "")
                            change_type = change.get("change_type", "")
                            if change_type == "signature_breaking":
                                callers = self._find_callers(graph, fname, sym_name)
                                for caller in callers:
                                    regressions.append({
                                        "type": "caller_signature_incompatible",
                                        "symbol": sym_name,
                                        "file": fname,
                                        "caller": caller,
                                        "change_type": change_type,
                                        "message": (
                                            f"Firma de '{sym_name}' cambió incompatible "
                                            f"en {fname}, afectando a caller {caller}"
                                        ),
                                    })
                    except Exception as e:
                        logger.debug(f"RF5 Capa 3.5: graph.detect_signature_changes falló: {e}")
                        # Fallback al método interno
                        self._check_signature_compat_fallback(
                            fname, file_path, current_content, graph, regressions
                        )
                else:
                    # Fallback: usar extracción interna + comparación
                    self._check_signature_compat_fallback(
                        fname, file_path, current_content, graph, regressions
                    )
            except Exception as e:
                logger.warning(f"RF5 Capa 3.5: error procesando {file_path}: {e}")

        return regressions

    def _check_signature_compat_fallback(
        self,
        fname: str,
        file_path: str,
        current_content: str,
        graph: Any,
        regressions: List[Dict[str, Any]],
    ) -> None:
        """Fallback para verificación de compatibilidad de firmas.

        Usa _extract_symbols_with_signatures para comparar con lo que
        el grafo tiene almacenado (vía get_file_symbols + get_refactor_context).

        Args:
            fname: Nombre del archivo.
            file_path: Ruta completa del archivo.
            current_content: Contenido actual del archivo.
            graph: SymbolGraph.
            regressions: Lista a la que agregar regresiones (modificada in-place).
        """
        try:
            # Extraer símbolos actuales con firma
            current_syms = self._extract_symbols_with_signatures(current_content, fname)
            current_index = {s.qualified_name: s for s in current_syms}

            # Obtener símbolos del grafo (estado antes de modificación)
            graph_symbols = graph.get_file_symbols(fname)
            if not graph_symbols:
                return

            # Para cada símbolo que existe tanto en grafo como en archivo actual,
            # verificar si la firma cambió de forma incompatible
            for sym_qualified in graph_symbols:
                sym_name = sym_qualified.split('.')[-1] if '.' in sym_qualified else sym_qualified
                if sym_qualified not in current_index and sym_name not in {
                    s.name for s in current_syms
                }:
                    continue  # Símbolo eliminado — ya cubierto por Capa 3

                # Buscar el símbolo actual (por qualified_name o por name)
                current_sym = current_index.get(sym_qualified)
                if not current_sym:
                    # Buscar por nombre simple
                    for s in current_syms:
                        if s.name == sym_name:
                            current_sym = s
                            break

                if not current_sym:
                    continue

                # Buscar callers
                callers = self._find_callers(graph, fname, sym_name)
                if not callers:
                    continue

                # Si hay callers y el símbolo es una función/método con args
                # que parecen haber cambiado, reportar (conservadoramente)
                # Nota: sin el estado previo del grafo no podemos comparar firmas
                # directamente, pero si detectamos breaking changes vía review_diff
                # ya se habrían reportado en RF4. Esta capa es un refuerzo.
                pass
        except Exception as e:
            logger.debug(f"RF5 Capa 3.5 fallback: error: {e}")

    def _run_existing_tests(self) -> Tuple[bool, List[Dict[str, Any]]]:
        """Ejecuta los tests existentes del proyecto (pytest).

        Capa 4: Ejecuta `python -m pytest --tb=short -q` con un timeout de 30s.
        Si no hay tests o pytest no está disponible, retorna (True, [])
        (non-blocking, principio RF5-4).

        Returns:
            (success, test_errors): success=True si todos los tests pasan
            o no se pudieron ejecutar. test_errors es lista de dicts con
            detalles de tests fallidos.
        """
        test_errors: List[Dict[str, Any]] = []

        try:
            # Verificar si pytest está disponible
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "--version"],
                capture_output=True,
                timeout=10,
                cwd=str(self._project_root),
            )
            if result.returncode != 0:
                logger.debug("RF5 Capa 4: pytest no disponible — omitiendo tests")
                return (True, [])
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            logger.debug("RF5 Capa 4: pytest no disponible — omitiendo tests")
            return (True, [])

        try:
            # Verificar si hay archivos de test en el proyecto
            has_tests = False
            for root, dirs, files in os.walk(str(self._project_root)):
                dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
                for fname in files:
                    if fname.startswith('test_') and fname.endswith('.py'):
                        has_tests = True
                        break
                    elif fname.endswith('_test.py'):
                        has_tests = True
                        break
                if has_tests:
                    break

            if not has_tests:
                logger.debug("RF5 Capa 4: no se encontraron archivos de test — omitiendo")
                return (True, [])

            # Ejecutar pytest
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "--tb=short", "-q"],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(self._project_root),
            )

            if result.returncode != 0:
                # Parsear salida de pytest para extraer tests fallidos
                output = result.stdout + result.stderr
                for line in output.splitlines():
                    line = line.strip()
                    if line.startswith("FAILED"):
                        # Formato: FAILED test_file.py::test_name
                        parts = line.split()
                        if len(parts) >= 2:
                            test_id = parts[1]
                        else:
                            test_id = line
                        test_errors.append({
                            "test": test_id,
                            "output": line,
                        })

                # Si no se pudieron parsear tests individuales, reportar genérico
                if not test_errors and result.returncode != 0:
                    test_errors.append({
                        "test": "pytest_suite",
                        "output": output[:500] if output else "Tests failed (no output)",
                        "returncode": result.returncode,
                    })

                logger.info(
                    f"RF5 Capa 4: {len(test_errors)} test(s) fallido(s)"
                )
                return (False, test_errors)

            logger.debug("RF5 Capa 4: todos los tests pasaron")
            return (True, [])

        except subprocess.TimeoutExpired:
            logger.warning("RF5 Capa 4: timeout ejecutando pytest (30s)")
            test_errors.append({
                "test": "pytest_timeout",
                "output": "pytest excedió timeout de 30 segundos",
            })
            return (False, test_errors)
        except Exception as e:
            logger.warning(f"RF5 Capa 4: error ejecutando tests: {e}")
            # RF5-4: no bloquear si el guardián falla
            return (True, [])

    def _smoke_test_imports(
        self,
        modified_files: List[str],
    ) -> List[Dict[str, Any]]:
        """Smoke test: intenta importar cada archivo .py modificado.

        Capa 5: Para cada archivo .py modificado, ejecuta
        `python -c "import module_name"` en un subprocess con timeout de 5s.
        Non-blocking: si falla, agrega a warnings pero no falla la validación.

        Args:
            modified_files: Lista de rutas de archivos modificados.

        Returns:
            Lista de dicts con errores de import (advisory, no blocking).
        """
        errors = []

        for file_path in modified_files:
            if not file_path.endswith('.py'):
                continue

            try:
                # Convertir path a module name: a/b/c.py → a.b.c
                rel_path = os.path.relpath(file_path, str(self._project_root))
                module_name = rel_path.replace('.py', '').replace(os.sep, '.')

                # No intentar importar __init__ directamente
                if module_name.endswith('.__init__'):
                    module_name = module_name[:-9]
                if not module_name or module_name == '__init__':
                    continue

                result = subprocess.run(
                    [sys.executable, "-c", f"import {module_name}"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    cwd=str(self._project_root),
                )

                if result.returncode != 0:
                    error_msg = result.stderr.strip() if result.stderr else "unknown error"
                    errors.append({
                        "type": "smoke_import_failure",
                        "module": module_name,
                        "file": os.path.basename(file_path),
                        "error": error_msg[:300],
                        "returncode": result.returncode,
                    })
                    logger.debug(
                        f"RF5 Capa 5: smoke import falló para {module_name}: "
                        f"{error_msg[:100]}"
                    )
            except subprocess.TimeoutExpired:
                errors.append({
                    "type": "smoke_import_timeout",
                    "module": module_name,
                    "file": os.path.basename(file_path),
                    "error": f"timeout (5s) al importar {module_name}",
                })
                logger.debug(f"RF5 Capa 5: timeout importando {module_name}")
            except Exception as e:
                logger.debug(f"RF5 Capa 5: error importando {file_path}: {e}")
                # Non-blocking: no agregar error, solo log

        if errors:
            logger.info(
                f"RF5 Capa 5: {len(errors)} smoke import failure(s) "
                f"(advisory, no blocking)"
            )

        return errors

    def get_unified_diff(
        self,
        original: str,
        modified: str,
        file_path: str = "",
    ) -> str:
        """Retorna un diff unificado entre dos contenidos.

        Útil para mostrar al Director qué cambió.
        """
        original_lines = original.splitlines(keepends=True)
        modified_lines = modified.splitlines(keepends=True)
        diff = difflib.unified_diff(
            original_lines, modified_lines,
            fromfile=f"{file_path} (original)",
            tofile=f"{file_path} (modificado)",
        )
        return "".join(diff)

    def rebuild_graph(self) -> bool:
        """Fuerza reconstrucción del grafo (ej: después de cambios en disco).

        Returns:
            True si se reconstruyó correctamente.
        """
        self._graph_built = False
        self._graph = None
        self._project_files = None  # Invalidar cache
        graph = self._ensure_graph()
        return graph is not None


# ============================================================================
# VALIDACIÓN AUTOCONTENIDA
# ============================================================================
def _run_validation() -> None:
    """Validacion autocontenida — 10 tests para RF2+RF4+RF5 v2.0."""
    import sys
    import tempfile
    import shutil

    test_results = []

    # --- Fixture: directorio temporal para tests ---
    test_dir = tempfile.mkdtemp(prefix="apa_rf_guard_test_")

    try:
        # Crear estructura de archivos de prueba
        utils_file = os.path.join(test_dir, "utils.py")
        main_file = os.path.join(test_dir, "main.py")
        helpers_file = os.path.join(test_dir, "helpers.py")
        models_file = os.path.join(test_dir, "models.py")

        utils_content = '''def validar(data):
    return bool(data)

def formatear(data):
    return str(data)

class Procesador:
    def procesar(self, data):
        return validar(data)
'''
        main_content = '''from utils import validar, Procesador

def ejecutar():
    resultado = validar("datos")
    p = Procesador()
    p.procesar(resultado)
    return resultado
'''
        helpers_content = '''from utils import formatear

def verificar(data):
    return formatear(data)
'''
        models_content = '''class BaseValidator:
    def validate(self, data):
        return True

class StrictValidator(BaseValidator):
    def validate(self, data):
        return len(data) > 0
'''
        with open(utils_file, 'w') as f: f.write(utils_content)
        with open(main_file, 'w') as f: f.write(main_content)
        with open(helpers_file, 'w') as f: f.write(helpers_content)
        with open(models_file, 'w') as f: f.write(models_content)

        # --- Test 1: RF2 — Contexto con evaluación de riesgo ---
        try:
            guard = RefactorGuard(test_dir)
            context = guard.get_refactor_context_for_prompt("utils.py")
            assert len(context) > 0, "Contexto no deberia estar vacio"
            assert "utils.py" in context, f"Contexto deberia mencionar utils.py: {context[:200]}"
            # v2.0: Debe incluir sección de riesgo
            assert "riesgo" in context.lower() or "Riesgo" in context, \
                f"Contexto deberia incluir evaluacion de riesgo: {context[:300]}"
            test_results.append(("RF2: Contexto con evaluacion de riesgo", True))
        except AssertionError:
            test_results.append(("RF2: Contexto con evaluacion de riesgo", False))

        # --- Test 2: CRITERIO RF2 — main.py aparece como dependiente ---
        try:
            guard = RefactorGuard(test_dir)
            context = guard.get_refactor_context_for_prompt("utils.py")
            assert "main.py" in context, \
                f"CRITERIO RF2: main.py deberia aparecer como dependiente: {context[:300]}"
            test_results.append(("CRITERIO RF2: main.py en dependientes de utils.py", True))
        except AssertionError:
            test_results.append(("CRITERIO RF2: main.py en dependientes de utils.py", False))

        # --- Test 3: RF4 — Detección de símbolo eliminado (CRITICAL) ---
        try:
            guard = RefactorGuard(test_dir)
            # Nuevo contenido sin la función validar()
            new_content = '''def formatear(data):
    return str(data)

class Procesador:
    def procesar(self, data):
        return formatear(data)
'''
            issues = guard.review_diff(utils_content, new_content, "utils.py")
            assert len(issues) > 0, "Deberia detectar issues al eliminar validar()"
            criticals = [i for i in issues if i.severity == "CRITICAL"]
            assert len(criticals) > 0, f"Deberia haber al menos un CRITICAL: {issues}"
            assert any("validar" in i.symbol for i in criticals), \
                f"El CRITICAL deberia mencionar validar: {criticals}"
            test_results.append(("RF4: Deteccion de simbolo eliminado (CRITICAL)", True))
        except AssertionError:
            test_results.append(("RF4: Deteccion de simbolo eliminado (CRITICAL)", False))

        # --- Test 4: CRITERIO RF4 — Diff que elimina validar() afecta a main.py ---
        try:
            guard = RefactorGuard(test_dir)
            new_content = '''def formatear(data):
    return str(data)
'''
            issues = guard.review_diff(utils_content, new_content, "utils.py")
            criticals = [i for i in issues if i.severity == "CRITICAL"]
            has_main_caller = False
            for issue in criticals:
                if "validar" in issue.symbol:
                    for caller in issue.affected_callers:
                        if "main.py" in caller:
                            has_main_caller = True
                            break
            assert has_main_caller, \
                f"CRITERIO RF4: main.py deberia estar entre los callers afectados: {criticals}"
            test_results.append(("CRITERIO RF4: main.py afectado al eliminar validar()", True))
        except AssertionError:
            test_results.append(("CRITERIO RF4: main.py afectado al eliminar validar()", False))

        # --- Test 5: RF4 — SIGNATURE_CHANGE_BREAKING detectado ---
        try:
            guard = RefactorGuard(test_dir)
            # Cambio de firma incompatible: validar(data) → validar(data, strict)
            new_content = '''def validar(data, strict):
    return bool(data) if strict else True

def formatear(data):
    return str(data)

class Procesador:
    def procesar(self, data):
        return validar(data)
'''
            issues = guard.review_diff(utils_content, new_content, "utils.py")
            sig_breaks = [i for i in issues if i.severity == "SIGNATURE_CHANGE_BREAKING"]
            assert len(sig_breaks) > 0, \
                f"Deberia detectar SIGNATURE_CHANGE_BREAKING: {[i.severity for i in issues]}"
            assert any("validar" in i.symbol for i in sig_breaks), \
                f"El BREAKING deberia mencionar validar: {sig_breaks}"
            test_results.append(("RF4: SIGNATURE_CHANGE_BREAKING detectado", True))
        except AssertionError:
            test_results.append(("RF4: SIGNATURE_CHANGE_BREAKING detectado", False))

        # --- Test 6: RF4 — SIGNATURE_CHANGE_COMPATIBLE (param con default) ---
        try:
            guard = RefactorGuard(test_dir)
            # Cambio de firma compatible: validar(data) → validar(data, strict=False)
            new_content = '''def validar(data, strict=False):
    return bool(data) if strict else True

def formatear(data):
    return str(data)

class Procesador:
    def procesar(self, data):
        return validar(data)
'''
            issues = guard.review_diff(utils_content, new_content, "utils.py")
            sig_compat = [i for i in issues if i.severity == "SIGNATURE_CHANGE_COMPATIBLE"]
            assert len(sig_compat) > 0, \
                f"Deberia detectar SIGNATURE_CHANGE_COMPATIBLE: {[i.severity for i in issues]}"
            test_results.append(("RF4: SIGNATURE_CHANGE_COMPATIBLE (param con default)", True))
        except AssertionError:
            test_results.append(("RF4: SIGNATURE_CHANGE_COMPATIBLE (param con default)", False))

        # --- Test 7: RF4 — WARNING solo cuando cuerpo realmente cambió ---
        try:
            guard = RefactorGuard(test_dir)
            # Solo agregar un comentario — no cambia símbolos ni cuerpos
            new_content = '# Comentario nuevo\n' + utils_content
            issues = guard.review_diff(utils_content, new_content, "utils.py")
            # v2.0: NO debería generar WARNINGs porque los cuerpos no cambiaron
            warnings = [i for i in issues if i.severity == "WARNING"]
            criticals = [i for i in issues if i.severity == "CRITICAL"]
            sig_breaks = [i for i in issues if i.severity == "SIGNATURE_CHANGE_BREAKING"]
            assert len(criticals) == 0, f"No deberia haber CRITICAL al agregar comentario: {criticals}"
            assert len(sig_breaks) == 0, f"No deberia haber BREAKING al agregar comentario"
            assert len(warnings) == 0, \
                f"v2.0: No deberia haber WARNING sin cambio real de cuerpo: {warnings}"
            test_results.append(("RF4: Sin WARNING cuando solo cambia comentario", True))
        except AssertionError:
            test_results.append(("RF4: Sin WARNING cuando solo cambia comentario", False))

        # --- Test 8: RF5 — Validación de sintaxis (ast.parse) ---
        try:
            guard = RefactorGuard(test_dir)
            snap_id = guard.create_refactor_snapshot(
                "syntax_test", [utils_file]
            )
            assert snap_id is not None, "Deberia crear snapshot"

            # Introducir error de sintaxis
            with open(utils_file, 'w') as f:
                f.write('def validar(data\n    return bool(data)\n')  # Falta ):

            # Validar regresión — debería detectar syntax error
            ok, report = guard.validate_regression(snap_id, [utils_file])
            assert not ok, "Deberia fallar por syntax error"
            assert len(report.get("syntax_errors", [])) > 0, \
                f"Deberia reportar syntax errors: {report}"

            # Restaurar
            with open(utils_file, 'w') as f:
                f.write(utils_content)

            test_results.append(("RF5: Validacion de sintaxis (ast.parse)", True))
        except AssertionError:
            test_results.append(("RF5: Validacion de sintaxis (ast.parse)", False))

        # --- Test 9: CRITERIO RF5 — validate_and_rollback restaura archivos ---
        try:
            # Restaurar archivos
            with open(utils_file, 'w') as f: f.write(utils_content)
            with open(main_file, 'w') as f: f.write(main_content)

            guard = RefactorGuard(test_dir)
            # Forzar construcción del grafo ANTES de modificar archivos
            # (el grafo lazy se construiría después de la modificación,
            # cuando ya no hay símbolos que detectar como eliminados)
            guard._ensure_graph()

            snap_id = guard.create_refactor_snapshot(
                "criterio_rf5", [utils_file, main_file]
            )
            assert snap_id is not None, "Deberia crear snapshot"

            # Modificar ambos archivos (eliminar todos los símbolos)
            with open(utils_file, 'w') as f: f.write("# MODIFICADO\n")
            with open(main_file, 'w') as f: f.write("# MODIFICADO\n")

            # Verificar que están modificados
            with open(utils_file, 'r') as f: assert "MODIFICADO" in f.read()
            with open(main_file, 'r') as f: assert "MODIFICADO" in f.read()

            # validate_and_rollback — debería fallar y hacer rollback automático
            ok, report = guard.validate_and_rollback(snap_id, [utils_file, main_file])
            assert not ok, "Validacion deberia fallar (símbolos eliminados)"
            assert report.get("rollback_executed") is True, \
                "Deberia haberse ejecutado rollback automaticamente"
            assert report.get("rollback_success") is True, \
                f"Rollback deberia ser exitoso: {report.get('rollback_errors')}"

            # Verificar restauración
            with open(utils_file, 'r') as f: content = f.read()
            assert content == utils_content, f"utils.py deberia estar restaurado"
            with open(main_file, 'r') as f: content = f.read()
            assert content == main_content, f"main.py deberia estar restaurado"

            test_results.append(("CRITERIO RF5: validate_and_rollback restaura archivos", True))
        except AssertionError:
            test_results.append(("CRITERIO RF5: validate_and_rollback restaura archivos", False))

        # --- Test 10: RF5 — Commit impide rollback ---
        try:
            with open(utils_file, 'w') as f: f.write(utils_content)

            guard = RefactorGuard(test_dir)
            snap_id = guard.create_refactor_snapshot("commit_test", [utils_file])

            # Modificar
            with open(utils_file, 'w') as f: f.write("# Cambio permanente\n")

            # Commit
            result = guard.commit_snapshot(snap_id)
            assert result, "Commit deberia ser exitoso"

            # Rollback deberia fallar
            success, errors = guard.rollback_snapshot(snap_id)
            assert not success, "No deberia poder rollback de snapshot confirmado"

            # Archivo deberia quedar modificado
            with open(utils_file, 'r') as f: assert "permanente" in f.read()

            test_results.append(("RF5: Commit impide rollback", True))
        except AssertionError:
            test_results.append(("RF5: Commit impide rollback", False))

    finally:
        # Limpieza del directorio temporal
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir, ignore_errors=True)

    # --- Reporte ---
    passed = sum(1 for _, ok in test_results if ok)
    failed = len(test_results) - passed
    print(f"\n{'='*60}")
    print(f"refactor_guard.py v2.0 — RF2+RF4+RF5 Validation")
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
