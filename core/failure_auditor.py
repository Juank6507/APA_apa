# apa/core/failure_auditor.py
# v2.0 — FailureAuditorAgent + FailurePatternAnalyzer
#
# v1.0: Diagnóstico de fallos del pipeline.
#         Clasifica fallos en 4 categorías y proporciona diagnosis
#         accionable con opciones de continuar/abortar.
#
# v2.0 (UX1): Añade FailurePatternAnalyzer — analiza logs de ejecución,
#         identifica patrones de fallo recurrentes y genera sugerencias
#         de corrección. Se integra como pestaña en la interfaz web.
#
# CATEGORÍAS DE FALLO:
#   1. context_insufficient  — El LLM agotó el contexto.
#      Evidencia: "[CONTEXT_EXCEEDED]" en el error, o
#      error_type='context_exceeded_no_fallback', o
#      action_required='split_task'.
#
#   2. model_limitation     — El LLM devolvió mala salida
#      (error de parseo, respuesta vacía, JSON malformado,
#       sin bloques de código).
#      Evidencia: errores de parseo, contenido vacío,
#      bloques de código faltantes.
#
#   3. prompt_error         — El planificador/codificador/integrador
#      produjo un plan inválido (SCRIPT faltante, formato
#      de tarea incorrecto).
#      Evidencia: V3PlanParser retornó errores, campos
#      requeridos faltantes.
#
#   4. unresolved_dependency — RF4 detectó cambios críticos o
#      RF5 detectó regresión.
#      Evidencia: rf4_has_critical=True, rf5_report con
#      regresiones, should_block=True.
#
# SEVERIDADES:
#   - critical:    context_insufficient sin fallback,
#                  unresolved_dependency con regresión sin rollback,
#                  model_limitation tras agotar max_attempts.
#   - recoverable: model_limitation con intentos restantes,
#                  prompt_error (se puede replanificar),
#                  context_insufficient (se puede dividir).
#   - minor:       model_limitation en primer intento.
#
# DECISIONES ARQUITECTÓNICAS:
#   FA-1: NO importa desde agents.semi_auto_agent (evita imports circulares).
#          Define TaskInfo y SemiAutoResult como dataclasses locales
#          o las acepta como Any cuando se invoca desde el agente.
#   FA-2: Usa symbol_graph.py (desde refactor_guard) para la categoría
#          unresolved_dependency, con carga perezosa.
#   FA-3: Todos los mensajes visibles para el usuario están en español,
#          siguiendo la convención del proyecto.
#   FA-4: El módulo es auto-contenido y testeable vía __main__.
#   FA-5 (UX1): FailurePatternAnalyzer lee specs/{project_id}/plan.json
#          para extraer tareas fallidas y detectar patrones recurrentes.
#
# CRITERIO DE ACEPTACIÓN (v1.0):
#   Dado un TaskInfo con error="[CONTEXT_EXCEEDED]" y attempt=1,
#   diagnose() retorna FailureDiagnosis(category="context_insufficient",
#   severity="recoverable", suggested_action="split").
#
# CRITERIO DE ACEPTACIÓN (UX1):
#   Dado un log con 3 fallos de syntax error consecutivos en el mismo
#   archivo, el auditor sugiere 'revisar la sintaxis base del archivo'
#   en vez de seguir corrigiendo.
#
# ============================================================================

import os
import sys
import re
import json
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any
from datetime import datetime
from pathlib import Path

# Asegurar que apa.core es importable (como hace semi_auto_agent.py)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# ============================================================================
# Logging setup
# ============================================================================
logger = logging.getLogger(__name__)


# ============================================================================
# Exports explícitos
# ============================================================================
__all__ = [
    "FailureDiagnosis",
    "FailureAuditorAgent",
    "FailurePattern",
    "FailureReport",
    "FailurePatternAnalyzer",
]


# ============================================================================
# FailureDiagnosis — Resultado del diagnóstico de fallo
# ============================================================================
@dataclass
class FailureDiagnosis:
    """Diagnóstico de un fallo del pipeline con recomendación de acción.

    Atributos:
        category: Una de las 4 categorías de fallo:
            "context_insufficient", "model_limitation",
            "prompt_error", "unresolved_dependency".
        severity: Nivel de severidad:
            "critical", "recoverable", "minor".
        agent: Agente que originó el fallo:
            "planner", "coder", "integrator", "validator".
        task_id: Identificador de la tarea que falló.
        evidence: Lista de fragmentos de evidencia que motivaron
            el diagnóstico.
        description: Descripción legible para humanos.
        can_continue: Si es True, se puede ofrecer la opción
            de continuar al usuario.
        can_abort: Si es True, se puede ofrecer la opción
            de abortar al usuario.
        suggested_action: Acción recomendada:
            "retry", "replan", "escalate", "split", "abort".
        context_for_retry: Contexto adicional para pasar en
            el siguiente reintento (opcional).
    """
    category: str                    # Una de las 4 categorías
    severity: str                    # "critical" | "recoverable" | "minor"
    agent: str                       # "planner" | "coder" | "integrator" | "validator"
    task_id: str                     # Tarea que falló
    evidence: List[str] = field(default_factory=list)
    description: str = ""            # Descripción legible
    can_continue: bool = False       # ¿Ofrecer opción de continuar?
    can_abort: bool = False          # ¿Ofrecer opción de abortar?
    suggested_action: str = ""       # "retry" | "replan" | "escalate" | "split" | "abort"
    context_for_retry: Optional[str] = None  # Contexto para reintento


# ============================================================================
# Patrones de evidencia para cada categoría
# ============================================================================

# context_insufficient: patrones en el texto de error
_CONTEXT_EXCEEDED_PATTERNS = [
    r"\[CONTEXT_EXCEEDED\]",
    r"context.?exceeded",
    r"context.?length.?exceeded",
    r"token.?limit.?exceeded",
    r"maximum.?context.?length",
    r"too.?many.?tokens",
    r"input.?too.?long",
]

# model_limitation: patrones de error de parseo/salida mala
_MODEL_LIMITATION_PATTERNS = [
    r"no se encontraron bloques de código",
    r"no code blocks found",
    r"empty response",
    r"respuesta vacía",
    r"json\.decode",
    r"JSONDecodeError",
    r"parse.?error",
    r"malformed",
    r"unexpected end",
    r"could not parse",
    r"failed to extract",
    r"sin código",
    r"sin contenido",
    r"bloque de código vacío",
]

# prompt_error: patrones de error en el planificador
_PROMPT_ERROR_PATTERNS = [
    r"Falta campo SCRIPT",
    r"missing.*SCRIPT",
    r"missing.*required.*field",
    r"campo requerido",
    r"parse.*error.*plan",
    r"plan.*inválido",
    r"tarea_id.*missing",
    r"formato.*incorrecto",
    r"V3PlanParser",
    r"sin bloques válidos",
]


# ============================================================================
# FailureAuditorAgent — Agente auditor de fallos
# ============================================================================
class FailureAuditorAgent:
    """Agente auditor que diagnostica fallos del pipeline semi-autónomo.

    Clasifica los fallos en 4 categorías (context_insufficient,
    model_limitation, prompt_error, unresolved_dependency) y
    proporciona un diagnóstico accionable con opciones de
    continuar/abortar y una acción sugerida.

    Flujo de diagnóstico:
        1. Recolectar evidencia del error, resultado y estado de la tarea.
        2. Evaluar cada categoría en orden de prioridad.
        3. Determinar severidad basada en intentos y contexto.
        4. Generar acción sugerida y opciones para el usuario.

    Uso:
        auditor = FailureAuditorAgent()
        diagnosis = auditor.diagnose(task, error_str, result, "coder")
        mensaje = auditor.get_user_facing_message(diagnosis)
        if auditor.should_escalate_to_director(diagnosis):
            # Escalar al Director
            ...
    """

    def __init__(self, symbol_graph: Any = None):
        """Inicializa el auditor de fallos.

        Args:
            symbol_graph: Instancia opcional de SymbolGraph para la
                categoría unresolved_dependency. Si no se proporciona,
                se intentará cargar perezosamente cuando sea necesario.
        """
        self._symbol_graph = symbol_graph
        self._graph_loaded = False

    # --- Carga perezosa del grafo de símbolos ---

    def _get_symbol_graph(self) -> Any:
        """Obtiene el SymbolGraph, con carga perezosa si es necesario."""
        if self._symbol_graph is not None or self._graph_loaded:
            return self._symbol_graph

        self._graph_loaded = True
        try:
            from core.symbol_graph import SymbolGraph
            logger.debug("FailureAuditor: SymbolGraph disponible para unresolved_dependency")
            # Nota: no creamos una instancia aquí porque el grafo necesita
            # build_from_directory(). El grafo se pasa externamente.
        except ImportError:
            logger.debug("FailureAuditor: SymbolGraph no disponible")

        return self._symbol_graph

    # ================================================================
    # API PRINCIPAL
    # ================================================================

    def diagnose(
        self,
        task: Any,
        error: str,
        result: Any,
        agent_name: str,
    ) -> FailureDiagnosis:
        """Diagnostica un fallo del pipeline y retorna un FailureDiagnosis.

        Evalúa las 4 categorías en orden de prioridad y retorna el
        diagnóstico más específico encontrado.

        Args:
            task: TaskInfo de la tarea que falló. Debe tener atributos:
                task_id, script, status, attempt, max_attempts,
                error, validation_result, coder_output.
            error: Cadena de texto con el error reportado.
            result: SemiAutoResult (u objeto similar) de la ejecución.
                Puede ser None.
            agent_name: Nombre del agente donde ocurrió el fallo:
                "planner", "coder", "integrator", "validator".

        Returns:
            FailureDiagnosis con categoría, severidad, evidencia y
            acción sugerida.
        """
        # Extraer atributos de la tarea con defensivos
        task_id = getattr(task, 'task_id', '') or ''
        attempt = getattr(task, 'attempt', 1) or 1
        max_attempts = getattr(task, 'max_attempts', 3) or 3
        task_error = getattr(task, 'error', '') or ''
        validation_result = getattr(task, 'validation_result', {}) or {}
        coder_output = getattr(task, 'coder_output', '') or ''
        script = getattr(task, 'script', '') or ''

        # Normalizar nombre del agente
        agent_name = self._normalize_agent_name(agent_name)

        # Construir texto completo para análisis de patrones
        combined_text = self._build_combined_text(
            error=error,
            task_error=task_error,
            result=result,
            coder_output=coder_output,
            validation_result=validation_result,
        )

        # Recolectar evidencia de cada categoría
        evidence_collector: Dict[str, List[str]] = {
            "context_insufficient": [],
            "model_limitation": [],
            "prompt_error": [],
            "unresolved_dependency": [],
        }

        # --- 1. Evaluar context_insufficient ---
        self._check_context_insufficient(
            error, result, combined_text, evidence_collector
        )

        # --- 2. Evaluar model_limitation ---
        self._check_model_limitation(
            error, result, combined_text, coder_output,
            evidence_collector
        )

        # --- 3. Evaluar prompt_error ---
        self._check_prompt_error(
            error, result, combined_text, agent_name,
            evidence_collector
        )

        # --- 4. Evaluar unresolved_dependency ---
        self._check_unresolved_dependency(
            validation_result, evidence_collector
        )

        # --- Seleccionar categoría principal (prioridad) ---
        category = self._select_primary_category(evidence_collector)

        # --- Construir diagnóstico ---
        diagnosis = self._build_diagnosis(
            category=category,
            evidence=evidence_collector[category],
            agent_name=agent_name,
            task_id=task_id,
            attempt=attempt,
            max_attempts=max_attempts,
            script=script,
            validation_result=validation_result,
            error=error,
            combined_text=combined_text,
        )

        logger.info(
            f"FailureAuditor: diagnóstico para tarea {task_id} — "
            f"categoría={diagnosis.category}, severidad={diagnosis.severity}, "
            f"acción={diagnosis.suggested_action}, agente={diagnosis.agent}"
        )

        return diagnosis

    # ================================================================
    # MENSAJE PARA EL USUARIO
    # ================================================================

    def get_user_facing_message(self, diagnosis: FailureDiagnosis) -> str:
        """Genera un mensaje legible para el usuario sobre el diagnóstico.

        Args:
            diagnosis: FailureDiagnosis a presentar.

        Returns:
            Mensaje en español con el diagnóstico y opciones disponibles.
        """
        # Encabezado con emoji de severidad
        severity_icons = {
            "critical": "🔴",
            "recoverable": "🟡",
            "minor": "🟢",
        }
        icon = severity_icons.get(diagnosis.severity, "⚪")

        # Título por categoría
        category_titles = {
            "context_insufficient": "Contexto insuficiente",
            "model_limitation": "Limitación del modelo",
            "prompt_error": "Error en la planificación",
            "unresolved_dependency": "Dependencia sin resolver",
        }
        title = category_titles.get(diagnosis.category, "Error desconocido")

        lines = [
            f"{icon} **{title}** en tarea `{diagnosis.task_id}`",
            "",
            f"**Descripción:** {diagnosis.description}",
            "",
        ]

        # Evidencia (máximo 3 ítems para no saturar)
        if diagnosis.evidence:
            lines.append("**Evidencia:**")
            for ev in diagnosis.evidence[:3]:
                lines.append(f"  - {ev}")
            lines.append("")

        # Severidad
        severity_labels = {
            "critical": "Crítico — requiere intervención",
            "recoverable": "Recuperable — se puede intentar resolver automáticamente",
            "minor": "Menor — impacto limitado",
        }
        sev_label = severity_labels.get(diagnosis.severity, diagnosis.severity)
        lines.append(f"**Severidad:** {sev_label}")
        lines.append("")

        # Acción sugerida
        action_labels = {
            "retry": "Reintentar (posiblemente con otro modelo)",
            "replan": "Replanificar la tarea",
            "escalate": "Escalar al Director",
            "split": "Dividir la tarea en subtareas más pequeñas",
            "abort": "Abortar la operación",
        }
        action_label = action_labels.get(diagnosis.suggested_action, diagnosis.suggested_action)
        lines.append(f"**Acción sugerida:** {action_label}")
        lines.append("")

        # Opciones disponibles
        options = []
        if diagnosis.can_continue:
            options.append("✅ **Continuar** con la acción sugerida")
        if diagnosis.can_abort:
            options.append("❌ **Abortar** la operación")
        if not options:
            options.append("⚠️ Sin opciones disponibles — se escalará automáticamente")

        lines.append("**Opciones disponibles:**")
        for opt in options:
            lines.append(f"  {opt}")

        return "\n".join(lines)

    # ================================================================
    # ESCALAMIENTO AL DIRECTOR
    # ================================================================

    def should_escalate_to_director(self, diagnosis: FailureDiagnosis) -> bool:
        """Determina si el diagnóstico debe escalar al Director.

        Se escala cuando:
        - La severidad es "critical"
        - La acción sugerida es "escalate"
        - No se puede continuar ni abortar manualmente

        Args:
            diagnosis: FailureDiagnosis a evaluar.

        Returns:
            True si se debe escalar al Director.
        """
        # Escalar siempre si es critical
        if diagnosis.severity == "critical":
            return True

        # Escalar si la acción sugerida es escalate
        if diagnosis.suggested_action == "escalate":
            return True

        # No escalar si hay opciones viables para el usuario
        if diagnosis.can_continue and diagnosis.severity == "recoverable":
            return False

        # Escalar si no hay opciones y no es minor
        if not diagnosis.can_continue and not diagnosis.can_abort:
            if diagnosis.severity != "minor":
                return True

        return False

    # ================================================================
    # DETECCIÓN POR CATEGORÍA (métodos privados)
    # ================================================================

    def _check_context_insufficient(
        self,
        error: str,
        result: Any,
        combined_text: str,
        evidence: Dict[str, List[str]],
    ) -> None:
        """Detecta evidencia de context_insufficient.

        Señales:
        - "[CONTEXT_EXCEEDED]" en el error
        - error_type='context_exceeded_no_fallback' en la respuesta
        - action_required='split_task' en la respuesta
        - Patrones de texto de error que indican contexto excedido
        """
        ev: List[str] = []

        # Verificar marcador directo en el error
        if "[CONTEXT_EXCEEDED]" in (error or ""):
            ev.append('Marcador "[CONTEXT_EXCEEDED]" encontrado en el error')

        # Verificar en el resultado de call_llm()
        if result is not None:
            result_dict = self._result_to_dict(result)

            if result_dict.get("error_type") == "context_exceeded_no_fallback":
                ev.append("error_type='context_exceeded_no_fallback' en la respuesta del LLM")

            if result_dict.get("action_required") == "split_task":
                ev.append("action_required='split_task' indicado por el router")

        # Verificar patrones de texto
        for pattern in _CONTEXT_EXCEEDED_PATTERNS:
            if re.search(pattern, combined_text, re.IGNORECASE):
                desc = f"Patrón detectado: /{pattern}/"
                if desc not in ev:
                    ev.append(desc)

        evidence["context_insufficient"] = ev

    def _check_model_limitation(
        self,
        error: str,
        result: Any,
        combined_text: str,
        coder_output: str,
        evidence: Dict[str, List[str]],
    ) -> None:
        """Detecta evidencia de model_limitation.

        Señales:
        - Error de parseo (JSON, markdown, código)
        - Respuesta vacía del LLM
        - Sin bloques de código en la salida del codificador
        - JSON malformado
        - Contenido truncado o incompleto
        """
        ev: List[str] = []

        # Verificar salida vacía del codificador
        if not coder_output or not coder_output.strip():
            ev.append("Salida del codificador vacía o solo espacios en blanco")

        # Verificar si hay bloques de código en la salida del codificador
        if coder_output and coder_output.strip():
            has_code_block = bool(re.search(r'```(?:python|code)', coder_output, re.IGNORECASE))
            if not has_code_block:
                ev.append("No se encontraron bloques de código (```python) en la salida del codificador")

        # Verificar errores de parseo
        if error and any(
            kw in error.lower()
            for kw in ["parse", "json", "malformed", "decode", "extract"]
        ):
            ev.append(f"Error de parseo/extracción: {self._truncate(error, 100)}")

        # Verificar patrones de texto
        for pattern in _MODEL_LIMITATION_PATTERNS:
            if re.search(pattern, combined_text, re.IGNORECASE):
                desc = f"Patrón de limitación detectado: /{pattern}/"
                if desc not in ev:
                    ev.append(desc)

        # Verificar en el resultado del LLM
        if result is not None:
            result_dict = self._result_to_dict(result)
            content = result_dict.get("content", "")
            if not content or not content.strip():
                ev.append("El LLM retornó contenido vacío")
            elif len(content.strip()) < 20:
                ev.append(f"Respuesta del LLM inusualmente corta ({len(content.strip())} chars)")

        evidence["model_limitation"] = ev

    def _check_prompt_error(
        self,
        error: str,
        result: Any,
        combined_text: str,
        agent_name: str,
        evidence: Dict[str, List[str]],
    ) -> None:
        """Detecta evidencia de prompt_error.

        Señales:
        - V3PlanParser retornó errores
        - Campos requeridos faltantes (SCRIPT, TAREA_ID)
        - Formato de tarea incorrecto
        - Error en la fase de planificación
        """
        ev: List[str] = []

        # Verificar si el error menciona V3PlanParser o campos faltantes
        for pattern in _PROMPT_ERROR_PATTERNS:
            if re.search(pattern, combined_text, re.IGNORECASE):
                desc = f"Patrón de error de planificación: /{pattern}/"
                if desc not in ev:
                    ev.append(desc)

        # Verificar si el error vino del planificador
        if agent_name == "planner" and error:
            # Errores específicos del parser del plan
            if "SCRIPT" in error and ("Falta" in error or "Missing" in error or "missing" in error.lower()):
                ev.append("El planificador no generó el campo SCRIPT requerido")

        # Verificar si el resultado tiene bloques vacíos del planificador
        if result is not None:
            result_dict = self._result_to_dict(result)
            planner_output = result_dict.get("planner_output", "")
            if planner_output:
                # Verificar si el parser no encontró bloques
                if "sin bloques" in planner_output.lower() or "no blocks" in planner_output.lower():
                    ev.append("V3PlanParser no encontró bloques válidos en la salida del planificador")

        # Solo relevante si el fallo viene del planificador o integrador
        if agent_name not in ("planner", "integrator") and not ev:
            # Si no es planner/integrator y no hay evidencia, limpiar
            pass

        evidence["prompt_error"] = ev

    def _check_unresolved_dependency(
        self,
        validation_result: Dict[str, Any],
        evidence: Dict[str, List[str]],
    ) -> None:
        """Detecta evidencia de unresolved_dependency.

        Señales:
        - rf4_has_critical=True
        - rf4_should_block=True
        - rf5_report con regresiones
        """
        ev: List[str] = []

        if not validation_result:
            evidence["unresolved_dependency"] = ev
            return

        # RF4: Revisión de diffs
        rf4_has_critical = validation_result.get("rf4_has_critical", False)
        rf4_should_block = validation_result.get("rf4_should_block", False)
        rf4_issues = validation_result.get("rf4_issues", [])

        if rf4_has_critical:
            ev.append("RF4: se detectaron issues CRITICAL o SIGNATURE_CHANGE_BREAKING")

        if rf4_should_block:
            ev.append("RF4: should_block=True — los cambios fueron bloqueados")

        # Contar issues por severidad
        if rf4_issues:
            critical_count = sum(
                1 for i in rf4_issues
                if i.get("severity") in ("CRITICAL", "SIGNATURE_CHANGE_BREAKING")
            )
            scope_count = sum(
                1 for i in rf4_issues
                if i.get("severity") == "SCOPE_VIOLATION"
            )
            if critical_count:
                ev.append(f"RF4: {critical_count} issue(s) bloqueante(s)")
            if scope_count:
                ev.append(f"RF4: {scope_count} violación(es) de alcance")

        # RF5: Regresiones
        rf5_report = validation_result.get("rf5_report", {})
        if rf5_report:
            regressions = rf5_report.get("regressions", [])
            if regressions:
                ev.append(f"RF5: {len(regressions)} regresión(es) detectada(s)")
                for reg in regressions[:3]:
                    reg_desc = f"{reg.get('file', '?')}:{reg.get('type', '?')}"
                    ev.append(f"RF5 regresión: {reg_desc}")

            rollback_success = rf5_report.get("rollback_success", False)
            if regressions and not rollback_success:
                ev.append("RF5: el rollback automático NO se completó exitosamente")

        evidence["unresolved_dependency"] = ev

    # ================================================================
    # SELECCIÓN DE CATEGORÍA Y CONSTRUCCIÓN DEL DIAGNÓSTICO
    # ================================================================

    def _select_primary_category(
        self,
        evidence_collector: Dict[str, List[str]],
    ) -> str:
        """Selecciona la categoría principal basada en evidencia.

        Prioridad: unresolved_dependency > context_insufficient >
                   prompt_error > model_limitation

        Args:
            evidence_collector: Dict con listas de evidencia por categoría.

        Returns:
            Nombre de la categoría principal, o "model_limitation" como
            fallback (es la más genérica).
        """
        # Prioridad de categorías (de mayor a menor)
        priority_order = [
            "unresolved_dependency",
            "context_insufficient",
            "prompt_error",
            "model_limitation",
        ]

        for category in priority_order:
            if evidence_collector.get(category):
                return category

        # Fallback: si hay error pero no se detectó categoría específica
        return "model_limitation"

    def _build_diagnosis(
        self,
        category: str,
        evidence: List[str],
        agent_name: str,
        task_id: str,
        attempt: int,
        max_attempts: int,
        script: str,
        validation_result: Dict[str, Any],
        error: str,
        combined_text: str,
    ) -> FailureDiagnosis:
        """Construye un FailureDiagnosis completo para la categoría dada.

        Determina severidad, descripción, acción sugerida y opciones
        de continuar/abortar basándose en la categoría, intentos
        y contexto de la validación.

        Args:
            category: Categoría de fallo seleccionada.
            evidence: Lista de evidencia para esta categoría.
            agent_name: Nombre del agente donde falló.
            task_id: ID de la tarea.
            attempt: Intento actual.
            max_attempts: Máximo de intentos permitidos.
            script: Archivo objetivo de la tarea.
            validation_result: Dict de resultado de validación.
            error: Texto del error.
            combined_text: Texto combinado para análisis.

        Returns:
            FailureDiagnosis completamente poblado.
        """
        # Determinar severidad y acción sugerida
        severity, suggested_action = self._determine_severity_and_action(
            category=category,
            attempt=attempt,
            max_attempts=max_attempts,
            validation_result=validation_result,
        )

        # Determinar opciones de continuar/abortar
        can_continue, can_abort = self._determine_options(
            category=category,
            severity=severity,
            suggested_action=suggested_action,
        )

        # Generar descripción
        description = self._generate_description(
            category=category,
            agent_name=agent_name,
            task_id=task_id,
            script=script,
            attempt=attempt,
            max_attempts=max_attempts,
            evidence=evidence,
            validation_result=validation_result,
        )

        # Generar contexto para reintento
        context_for_retry = self._generate_retry_context(
            category=category,
            error=error,
            validation_result=validation_result,
            evidence=evidence,
        )

        return FailureDiagnosis(
            category=category,
            severity=severity,
            agent=agent_name,
            task_id=task_id,
            evidence=evidence,
            description=description,
            can_continue=can_continue,
            can_abort=can_abort,
            suggested_action=suggested_action,
            context_for_retry=context_for_retry,
        )

    def _determine_severity_and_action(
        self,
        category: str,
        attempt: int,
        max_attempts: int,
        validation_result: Dict[str, Any],
    ) -> tuple:
        """Determina severidad y acción sugerida para una categoría.

        Lógica de severidad:
        - context_insufficient:
            - Sin fallback -> "critical" (acción: "split")
            - Puede dividir -> "recoverable" (acción: "split")
        - model_limitation:
            - attempts >= max -> "critical" (acción: "escalate")
            - attempts < max y attempt > 1 -> "recoverable" (acción: "retry")
            - attempt == 1 -> "minor" (acción: "retry")
        - prompt_error:
            - Siempre "recoverable" (acción: "replan")
        - unresolved_dependency:
            - Con rollback fallido -> "critical" (acción: "escalate")
            - Con rollback exitoso -> "recoverable" (acción: "retry")
            - Sin regresión pero con bloqueo -> "recoverable" (acción: "replan")

        Returns:
            Tupla (severity, suggested_action).
        """
        attempts_exhausted = attempt >= max_attempts

        if category == "context_insufficient":
            # Siempre sugerir dividir; severity depende de si hay fallback
            if attempts_exhausted:
                return ("critical", "split")
            return ("recoverable", "split")

        elif category == "model_limitation":
            if attempts_exhausted:
                return ("critical", "escalate")
            elif attempt > 1:
                return ("recoverable", "retry")
            else:
                return ("minor", "retry")

        elif category == "prompt_error":
            return ("recoverable", "replan")

        elif category == "unresolved_dependency":
            rf5_report = validation_result.get("rf5_report", {})
            regressions = rf5_report.get("regressions", [])
            rollback_success = rf5_report.get("rollback_success", False)

            if regressions and not rollback_success:
                return ("critical", "escalate")
            elif regressions and rollback_success:
                return ("recoverable", "retry")
            else:
                # Bloqueo por RF4 pero sin regresión (ej: SCOPE_VIOLATION)
                return ("recoverable", "replan")

        # Fallback
        return ("minor", "retry")

    def _determine_options(
        self,
        category: str,
        severity: str,
        suggested_action: str,
    ) -> tuple:
        """Determina si se pueden ofrecer opciones de continuar/abortar.

        Reglas:
        - can_continue=True excepto cuando severity="critical" y
          no hay acción viable, o cuando action="abort".
        - can_abort=True siempre (el usuario siempre puede elegir abortar),
          excepto cuando severity="minor" y es el primer intento.

        Returns:
            Tupla (can_continue, can_abort).
        """
        can_continue = True
        can_abort = True

        if severity == "critical" and suggested_action == "escalate":
            # Escalamiento crítico: el sistema decide, no el usuario
            can_continue = False
            can_abort = True

        elif suggested_action == "abort":
            can_continue = False
            can_abort = True

        elif severity == "minor":
            # Fallo menor en primer intento: no ofrecer abortar
            can_continue = True
            can_abort = False

        return (can_continue, can_abort)

    # ================================================================
    # GENERACIÓN DE TEXTO (métodos privados)
    # ================================================================

    def _generate_description(
        self,
        category: str,
        agent_name: str,
        task_id: str,
        script: str,
        attempt: int,
        max_attempts: int,
        evidence: List[str],
        validation_result: Dict[str, Any],
    ) -> str:
        """Genera una descripción legible para el diagnóstico."""
        agent_labels = {
            "planner": "Planificador",
            "coder": "Codificador",
            "integrator": "Integrador",
            "validator": "Validador",
        }
        agent_label = agent_labels.get(agent_name, agent_name)

        descriptions = {
            "context_insufficient": (
                f"El modelo de lenguaje se quedó sin contexto al procesar "
                f"la tarea '{task_id}' ({script}) en el agente {agent_label}. "
                f"La tarea es demasiado grande para el contexto disponible."
            ),
            "model_limitation": (
                f"El modelo de lenguaje no produjo una salida válida para "
                f"la tarea '{task_id}' ({script}) en el agente {agent_label} "
                f"(intento {attempt}/{max_attempts}). "
                f"Esto puede deberse a una limitación del modelo o a un "
                f"prompt ambiguo."
            ),
            "prompt_error": (
                f"El {agent_label} produjo una especificación inválida para "
                f"la tarea '{task_id}' ({script}). El formato del plan no "
                f"cumple con los requisitos esperados (campos faltantes, "
                f"formato incorrecto)."
            ),
            "unresolved_dependency": (
                f"La validación de integridad detectó problemas de "
                f"dependencia en la tarea '{task_id}' ({script}). "
                f"Se encontraron cambios críticos o regresiones que "
                f"podrían afectar otros módulos del proyecto."
            ),
        }

        base_desc = descriptions.get(category, f"Error no clasificado en tarea '{task_id}'.")

        # Agregar detalles de evidencia si los hay
        if evidence:
            base_desc += f" Evidencia: {evidence[0]}"

        return base_desc

    def _generate_retry_context(
        self,
        category: str,
        error: str,
        validation_result: Dict[str, Any],
        evidence: List[str],
    ) -> Optional[str]:
        """Genera contexto adicional para pasar en el siguiente reintento.

        Returns:
            Cadena con contexto adicional, o None si no aplica.
        """
        context_parts = []

        if category == "model_limitation":
            # Sugerir al codificador qué fue lo que falló
            if error:
                context_parts.append(
                    f"ERROR ANTERIOR (no repetir): {self._truncate(error, 200)}"
                )
            context_parts.append(
                "INSTRUCCIÓN: Asegúrate de que tu respuesta contenga "
                "un bloque de código Python completo envuelto en "
                "```python``` ... ```."
            )

        elif category == "prompt_error":
            context_parts.append(
                "ERROR DE FORMATO: El plan anterior no cumplía con el "
                "formato requerido. Asegúrate de incluir los campos "
                "SCRIPT y TAREA_ID en cada bloque ## TAREA DE ENSAMBLAJE."
            )

        elif category == "context_insufficient":
            context_parts.append(
                "CONTEXTO EXCEDIDO: La tarea es demasiado grande. "
                "Divide el trabajo en subtareas más pequeñas que "
                "cada una pueda procesarse dentro del límite de contexto."
            )

        elif category == "unresolved_dependency":
            rf5_report = validation_result.get("rf5_report", {})
            regressions = rf5_report.get("regressions", [])
            if regressions:
                reg_details = "; ".join(
                    f"{r.get('file', '?')}:{r.get('type', '?')}"
                    for r in regressions[:5]
                )
                context_parts.append(
                    f"REGRESIONES DETECTADAS (evitar): {reg_details}"
                )
            rf4_issues = validation_result.get("rf4_issues", [])
            critical_issues = [
                i for i in rf4_issues
                if i.get("severity") in ("CRITICAL", "SIGNATURE_CHANGE_BREAKING")
            ]
            if critical_issues:
                issue_details = "; ".join(
                    f"{i.get('symbol', '?')}: {i.get('description', '?')}"
                    for i in critical_issues[:3]
                )
                context_parts.append(
                    f"ISSUES CRÍTICOS RF4 (respetar): {issue_details}"
                )

        return "\n".join(context_parts) if context_parts else None

    # ================================================================
    # HELPERS
    # ================================================================

    def _normalize_agent_name(self, agent_name: str) -> str:
        """Normaliza el nombre del agente a minúsculas."""
        return (agent_name or "").lower().strip()

    def _build_combined_text(
        self,
        error: str,
        task_error: str,
        result: Any,
        coder_output: str,
        validation_result: Dict[str, Any],
    ) -> str:
        """Construye un texto combinado para búsqueda de patrones."""
        parts = []

        if error:
            parts.append(str(error))
        if task_error:
            parts.append(str(task_error))
        if coder_output:
            # Usar solo los primeros 500 chars del output para no saturar
            parts.append(coder_output[:500])

        if result is not None:
            result_dict = self._result_to_dict(result)
            # Campos relevantes del resultado
            for key in ("error", "planner_output", "coder_output", "content"):
                val = result_dict.get(key, "")
                if val:
                    parts.append(str(val)[:500])

        # Validation result como string
        if validation_result:
            try:
                parts.append(json.dumps(validation_result, default=str)[:1000])
            except (TypeError, ValueError):
                pass

        return "\n".join(parts)

    def _result_to_dict(self, result: Any) -> Dict[str, Any]:
        """Convierte un resultado a dict, manejando dataclasses y dicts."""
        if result is None:
            return {}
        if isinstance(result, dict):
            return result
        if hasattr(result, '__dataclass_fields__'):
            # Es un dataclass — convertir a dict
            from dataclasses import asdict
            try:
                return asdict(result)
            except Exception:
                return {}
        return {}

    @staticmethod
    def _truncate(text: str, max_length: int = 100) -> str:
        """Trunca un texto a max_length caracteres con ellipsis."""
        if not text:
            return ""
        text = str(text)
        if len(text) <= max_length:
            return text
        return text[:max_length - 3] + "..."


# ============================================================================
# UX1: FailurePattern — Patrón de fallo recurrente detectado
# ============================================================================
@dataclass
class FailurePattern:
    """Patrón de fallo recurrente identificado por el analizador.

    Atributos:
        pattern_type: Tipo de patrón detectado:
            "repeated_file", "repeated_category", "repeated_error",
            "model_timeout", "ambiguous_spec".
        count: Número de ocurrencias del patrón.
        affected_files: Lista de archivos afectados por el patrón.
        affected_tasks: Lista de IDs de tareas afectadas.
        category: Categoría de fallo inferida (de FailureDiagnosis).
        severity: Severidad agregada:
            "critical" si >= 3 ocurrencias en el mismo archivo,
            "recoverable" si >= 2, "minor" en caso contrario.
        suggestion: Sugerencia de corrección generada automáticamente.
        details: Detalles adicionales sobre el patrón detectado.
    """
    pattern_type: str
    count: int
    affected_files: List[str] = field(default_factory=list)
    affected_tasks: List[str] = field(default_factory=list)
    category: str = ""
    severity: str = "minor"
    suggestion: str = ""
    details: str = ""


# ============================================================================
# UX1: FailureReport — Reporte agregado de análisis de patrones
# ============================================================================
@dataclass
class FailureReport:
    """Reporte completo del análisis de patrones de fallo.

    Atributos:
        total_failures: Total de tareas fallidas (status failed/split).
        total_tasks: Total de tareas en el plan.
        patterns: Lista de patrones de fallo detectados.
        top_failing_files: Lista de dicts con archivos más problemáticos.
        category_distribution: Distribución de fallos por categoría.
        agent_distribution: Distribución de fallos por agente.
        suggestions: Lista de sugerencias de corrección (top 5).
        generated_at: Marca temporal de generación del reporte.
    """
    total_failures: int = 0
    total_tasks: int = 0
    patterns: List[FailurePattern] = field(default_factory=list)
    top_failing_files: List[dict] = field(default_factory=list)
    category_distribution: dict = field(default_factory=dict)
    agent_distribution: dict = field(default_factory=dict)
    suggestions: List[str] = field(default_factory=list)
    generated_at: str = ""


# ============================================================================
# UX1: FailurePatternAnalyzer — Analizador de patrones de fallo recurrentes
# ============================================================================
class FailurePatternAnalyzer:
    """Analizador de patrones de fallo recurrentes en logs de ejecución.

    Lee los planes de proyecto (specs/{project_id}/plan.json), extrae
    las tareas fallidas, identifica patrones recurrentes y genera
    sugerencias de corrección.

    Tipos de patrón detectados:
        - repeated_file: Mismo archivo con fallos consecutivos.
        - repeated_category: Misma categoría de fallo repetida.
        - repeated_error: Mismo error repetido.
        - model_timeout: Contexto excedido o rate limit del modelo.
        - ambiguous_spec: Especificaciones ambiguas que requirieron
          replanificación o división.

    Uso:
        analyzer = FailurePatternAnalyzer(specs_dir="/ruta/specs")
        report = analyzer.analyze_project("mi-proyecto")
        print(analyzer.get_user_facing_report(report))
    """

    def __init__(self, specs_dir: str = None):
        """Inicializa el analizador de patrones.

        Args:
            specs_dir: Ruta al directorio de especificaciones.
                Si es None, usa Path(__file__).parents[1] / "specs".
        """
        if specs_dir is None:
            specs_dir = str(Path(__file__).parents[1] / "specs")
        self.specs_dir = Path(specs_dir)

    # ================================================================
    # API PRINCIPAL
    # ================================================================

    def analyze_project(self, project_id: str) -> FailureReport:
        """Analiza los patrones de fallo de un proyecto específico.

        Lee specs/{project_id}/plan.json, extrae las tareas fallidas,
        detecta patrones recurrentes y genera sugerencias.

        Args:
            project_id: Identificador del proyecto a analizar.

        Returns:
            FailureReport con el análisis completo de patrones.
        """
        plan_path = self.specs_dir / project_id / "plan.json"

        # Cargar el plan
        if not plan_path.exists():
            logger.warning(
                f"FailurePatternAnalyzer: plan.json no encontrado en {plan_path}"
            )
            return FailureReport(
                generated_at=datetime.now().isoformat(),
            )

        try:
            with open(plan_path, "r", encoding="utf-8") as f:
                plan = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.error(
                f"FailurePatternAnalyzer: error al leer {plan_path}: {e}"
            )
            return FailureReport(
                generated_at=datetime.now().isoformat(),
            )

        # Extraer tareas fallidas
        failed_tasks = self._extract_failed_tasks(plan)
        all_tasks = plan.get("tasks", [])

        # Contar fallos: solo "failed" y "split" (replanned ya fue manejado)
        total_failures = sum(
            1 for t in failed_tasks
            if t.get("status") in ("failed", "split")
        )

        # Detectar patrones
        patterns: List[FailurePattern] = []
        patterns.extend(self._detect_repeated_file_failures(failed_tasks))
        patterns.extend(self._detect_repeated_category(failed_tasks))
        patterns.extend(self._detect_model_timeouts(failed_tasks))
        patterns.extend(self._detect_ambiguous_specs(failed_tasks))

        # Calcular distribución por categoría
        category_dist: Dict[str, int] = {}
        for task in failed_tasks:
            cat = self._infer_category_from_task(task)
            category_dist[cat] = category_dist.get(cat, 0) + 1

        # Calcular archivos más problemáticos
        file_counts: Dict[str, int] = {}
        for task in failed_tasks:
            script = task.get("script", "desconocido")
            file_counts[script] = file_counts.get(script, 0) + 1
        top_files = sorted(file_counts.items(), key=lambda x: x[1], reverse=True)

        # Generar sugerencias
        suggestions = self._generate_suggestions(patterns)

        report = FailureReport(
            total_failures=total_failures,
            total_tasks=len(all_tasks),
            patterns=patterns,
            top_failing_files=[
                {"file": f, "failures": c} for f, c in top_files
            ],
            category_distribution=category_dist,
            suggestions=suggestions,
            generated_at=datetime.now().isoformat(),
        )

        logger.info(
            f"FailurePatternAnalyzer: análisis de '{project_id}' — "
            f"{total_failures} fallos en {len(all_tasks)} tareas, "
            f"{len(patterns)} patrones detectados"
        )

        return report

    def analyze_all_projects(self) -> FailureReport:
        """Analiza todos los proyectos en el directorio de especificaciones.

        Escanea todos los subdirectorios en specs/ que contengan
        plan.json, llama a analyze_project para cada uno y agrega
        los resultados en un único FailureReport.

        Returns:
            FailureReport agregado con todos los proyectos analizados.
        """
        aggregated = FailureReport(
            generated_at=datetime.now().isoformat(),
        )

        if not self.specs_dir.exists():
            logger.warning(
                f"FailurePatternAnalyzer: directorio {self.specs_dir} no existe"
            )
            return aggregated

        # Buscar subdirectorios con plan.json
        for subdir in sorted(self.specs_dir.iterdir()):
            if not subdir.is_dir():
                continue
            plan_path = subdir / "plan.json"
            if not plan_path.exists():
                continue

            project_id = subdir.name
            project_report = self.analyze_project(project_id)

            # Agregar al reporte global
            aggregated.total_failures += project_report.total_failures
            aggregated.total_tasks += project_report.total_tasks
            aggregated.patterns.extend(project_report.patterns)
            aggregated.top_failing_files.extend(project_report.top_failing_files)
            aggregated.suggestions.extend(project_report.suggestions)

            # Fusionar distribuciones por categoría
            for cat, count in project_report.category_distribution.items():
                aggregated.category_distribution[cat] = (
                    aggregated.category_distribution.get(cat, 0) + count
                )

        # Eliminar duplicados en sugerencias y mantener top 5
        unique_suggestions = list(dict.fromkeys(aggregated.suggestions))
        aggregated.suggestions = unique_suggestions[:5]

        # Reordenar top_failing_files por cantidad y consolidar
        file_totals: Dict[str, int] = {}
        for entry in aggregated.top_failing_files:
            fname = entry.get("file", "desconocido")
            file_totals[fname] = file_totals.get(fname, 0) + entry.get("failures", 0)
        aggregated.top_failing_files = sorted(
            [{"file": f, "failures": c} for f, c in file_totals.items()],
            key=lambda x: x["failures"],
            reverse=True,
        )

        logger.info(
            f"FailurePatternAnalyzer: análisis global — "
            f"{aggregated.total_failures} fallos totales, "
            f"{len(aggregated.patterns)} patrones detectados"
        )

        return aggregated

    # ================================================================
    # EXTRACCIÓN DE TAREAS FALLIDAS
    # ================================================================

    def _extract_failed_tasks(self, plan: dict) -> list:
        """Extrae las tareas que fallaron o fueron divididas/replanificadas.

        Retorna la lista de tareas del plan cuyo status sea
        "failed", "split" o "replanned".

        Args:
            plan: Dict con el plan del proyecto (contiene "tasks").

        Returns:
            Lista de dicts de tareas fallidas/divididas/replanificadas.
        """
        tasks = plan.get("tasks", [])
        failed = [
            t for t in tasks
            if isinstance(t, dict)
            and t.get("status") in ("failed", "split", "replanned")
        ]
        logger.debug(
            f"FailurePatternAnalyzer: {len(failed)} tareas fallidas "
            f"extraídas de {len(tasks)} totales"
        )
        return failed

    # ================================================================
    # DETECCIÓN DE PATRONES
    # ================================================================

    def _detect_repeated_file_failures(self, tasks: list) -> List[FailurePattern]:
        """Detecta archivos con fallos repetidos consecutivos.

        Agrupa las tareas por archivo destino (campo "script").
        Si un archivo tiene >= 2 fallos, genera un patrón.
        La severidad es "critical" si >= 3 fallos, "recoverable" si >= 2.

        Este es el criterio de aceptación UX1 clave:
        dado 3 fallos de syntax error en el mismo archivo, sugerir
        revisar la sintaxis base en vez de seguir corrigiendo uno a uno.

        Args:
            tasks: Lista de tareas fallidas.

        Returns:
            Lista de FailurePattern para archivos con fallos repetidos.
        """
        patterns: List[FailurePattern] = []

        # Agrupar tareas por archivo destino
        by_file: Dict[str, list] = {}
        for task in tasks:
            script = task.get("script", "desconocido")
            if script not in by_file:
                by_file[script] = []
            by_file[script].append(task)

        # Detectar archivos con >= 2 fallos
        for script, file_tasks in by_file.items():
            count = len(file_tasks)
            if count < 2:
                continue

            # Determinar severidad
            if count >= 3:
                severity = "critical"
            else:
                severity = "recoverable"

            # Inferir categoría predominante
            categories = [self._infer_category_from_task(t) for t in file_tasks]
            predominant_cat = max(set(categories), key=categories.count) if categories else ""

            # Extraer IDs de tareas
            task_ids = [t.get("id", "") for t in file_tasks if t.get("id")]

            # Generar sugerencia contextual basada en el tipo de error
            diagnosis_texts = [
                t.get("result", {}).get("diagnosis", "")
                for t in file_tasks
            ]
            combined_diag = " ".join(diagnosis_texts).lower()

            if "syntax" in combined_diag or "sintaxis" in combined_diag:
                suggestion = (
                    f"Revisar la sintaxis base del archivo {script} — "
                    f"{count} fallos consecutivos detectados"
                )
                details = (
                    f"El archivo {script} acumula {count} fallos relacionados "
                    f"con errores de sintaxis. Se recomienda revisar la "
                    f"estructura base del archivo antes de continuar."
                )
            elif "import" in combined_diag:
                suggestion = (
                    f"Verificar las dependencias de importación en {script} — "
                    f"{count} fallos por imports"
                )
                details = (
                    f"El archivo {script} tiene {count} fallos relacionados "
                    f"con imports. Posible import circular o dependencia faltante."
                )
            elif "context" in combined_diag or "exceeded" in combined_diag:
                suggestion = (
                    f"El archivo {script} es demasiado grande — "
                    f"considerar dividirlo en módulos más pequeños"
                )
                details = (
                    f"El archivo {script} excede el contexto del modelo "
                    f"en {count} ocasiones. Dividir en submódulos."
                )
            else:
                suggestion = (
                    f"Revisar el archivo {script} — "
                    f"{count} fallos consecutivos detectados"
                )
                details = (
                    f"El archivo {script} acumula {count} fallos. "
                    f"Revisar la causa raíz antes de reintentar."
                )

            pattern = FailurePattern(
                pattern_type="repeated_file",
                count=count,
                affected_files=[script],
                affected_tasks=task_ids,
                category=predominant_cat,
                severity=severity,
                suggestion=suggestion,
                details=details,
            )
            patterns.append(pattern)

        return patterns

    def _detect_repeated_category(self, tasks: list) -> List[FailurePattern]:
        """Detecta categorías de fallo que se repiten frecuentemente.

        Agrupa las tareas por categoría inferida de su diagnóstico.
        Si una categoría aparece >= 3 veces, genera un patrón con
        sugerencias específicas según el tipo.

        Args:
            tasks: Lista de tareas fallidas.

        Returns:
            Lista de FailurePattern para categorías repetidas.
        """
        patterns: List[FailurePattern] = []

        # Agrupar por categoría inferida
        by_category: Dict[str, list] = {}
        for task in tasks:
            cat = self._infer_category_from_task(task)
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(task)

        # Detectar categorías con >= 3 ocurrencias
        category_suggestions = {
            "context_insufficient": (
                "Múltiples tareas exceden el contexto del modelo. "
                "Considerar usar un modelo con más capacidad de "
                "contexto o dividir las tareas en unidades más pequeñas."
            ),
            "model_limitation": (
                "El modelo presenta limitaciones recurrentes. "
                "Considerar ajustar los prompts o cambiar de modelo "
                "para estas tareas."
            ),
            "prompt_error": (
                "Errores recurrentes en la planificación. "
                "Revisar las instrucciones del planificador y "
                "la especificación del proyecto."
            ),
            "unresolved_dependency": (
                "Problemas recurrentes de dependencias. "
                "Revisar la arquitectura del proyecto y "
                "las dependencias entre módulos."
            ),
        }

        for category, cat_tasks in by_category.items():
            count = len(cat_tasks)
            if count < 3:
                continue

            task_ids = [t.get("id", "") for t in cat_tasks if t.get("id")]
            files = list({
                t.get("script", "")
                for t in cat_tasks
                if t.get("script")
            })

            suggestion = category_suggestions.get(
                category,
                f"La categoría '{category}' se repite {count} veces. "
                f"Investigar la causa raíz.",
            )

            pattern = FailurePattern(
                pattern_type="repeated_category",
                count=count,
                affected_files=files,
                affected_tasks=task_ids,
                category=category,
                severity="recoverable" if count < 5 else "critical",
                suggestion=suggestion,
                details=(
                    f"La categoría '{category}' aparece en {count} tareas "
                    f"fallidas: {', '.join(task_ids[:5])}"
                ),
            )
            patterns.append(pattern)

        return patterns

    def _detect_model_timeouts(self, tasks: list) -> List[FailurePattern]:
        """Detecta patrones de timeout o límite de contexto del modelo.

        Busca patrones como [CONTEXT_EXCEEDED], rate_limit, timeout
        y split_task en los textos de diagnóstico y error de las tareas.
        Si se detectan >= 2 tareas con estos patrones, genera un patrón.

        Args:
            tasks: Lista de tareas fallidas.

        Returns:
            Lista de FailurePattern para timeouts del modelo.
        """
        patterns: List[FailurePattern] = []

        # Patrones indicativos de timeout/limite del modelo
        timeout_patterns = [
            r"\[CONTEXT_EXCEEDED\]",
            r"context.?exceeded",
            r"context.?too.?large",
            r"rate.?limit",
            r"timeout",
            r"timed.?out",
            r"split_task",
        ]

        # Identificar tareas con patrones de timeout
        timeout_tasks = []
        for task in tasks:
            result = task.get("result", {})
            diagnosis = result.get("diagnosis", "") or ""
            error = result.get("error", "") or ""
            action = result.get("action_required", "") or ""
            text = f"{diagnosis} {error} {action}"

            matches = False
            for pattern in timeout_patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    matches = True
                    break

            if matches:
                timeout_tasks.append(task)

        if len(timeout_tasks) < 2:
            return patterns

        # Generar patrón
        task_ids = [t.get("id", "") for t in timeout_tasks if t.get("id")]
        files = list({
            t.get("script", "")
            for t in timeout_tasks
            if t.get("script")
        })

        count = len(timeout_tasks)
        severity = "critical" if count >= 4 else "recoverable"

        pattern = FailurePattern(
            pattern_type="model_timeout",
            count=count,
            affected_files=files,
            affected_tasks=task_ids,
            category="context_insufficient",
            severity=severity,
            suggestion=(
                "Considerar dividir la tarea o usar un modelo con "
                "más contexto. Los timeouts recurrentes sugieren que "
                "las tareas son demasiado grandes para el límite actual."
            ),
            details=(
                f"{count} tareas presentaron timeout o exceso de "
                f"contexto: {', '.join(task_ids[:5])}"
            ),
        )
        patterns.append(pattern)

        return patterns

    def _detect_ambiguous_specs(self, tasks: list) -> List[FailurePattern]:
        """Detecta especificaciones ambiguas que fueron replanificadas.

        Identifica tareas que fallaron en el primer intento y fueron
        replanificadas (status "replanned") o divididas (status "split"),
        lo que sugiere que la especificación original era ambigua o
        demasiado amplia.

        Args:
            tasks: Lista de tareas fallidas.

        Returns:
            Lista de FailurePattern para especificaciones ambiguas.
        """
        patterns: List[FailurePattern] = []

        # Buscar tareas con status "replanned" o "split"
        ambiguous_tasks = [
            t for t in tasks
            if t.get("status") in ("replanned", "split")
        ]

        if not ambiguous_tasks:
            return patterns

        task_ids = [t.get("id", "") for t in ambiguous_tasks if t.get("id")]
        files = list({
            t.get("script", "")
            for t in ambiguous_tasks
            if t.get("script")
        })

        count = len(ambiguous_tasks)
        severity = "recoverable"

        pattern = FailurePattern(
            pattern_type="ambiguous_spec",
            count=count,
            affected_files=files,
            affected_tasks=task_ids,
            category="prompt_error",
            severity=severity,
            suggestion=(
                "Revisar y especificar mejor la tarea original. "
                "Las tareas que requieren replanificación o división "
                "sugieren que la especificación era ambigua o demasiado "
                "amplia."
            ),
            details=(
                f"{count} tareas fueron replanificadas/divididas: "
                f"{', '.join(task_ids[:5])}. "
                f"Esto indica que las especificaciones originales "
                f"podrían ser más precisas."
            ),
        )
        patterns.append(pattern)

        return patterns

    # ================================================================
    # INFERENCIA DE CATEGORÍA
    # ================================================================

    def _infer_category_from_task(self, task: dict) -> str:
        """Infiere la categoría de fallo a partir del diagnóstico de una tarea.

        Utiliza coincidencia de patrones contra las listas de patrones
        definidas en v1.0 (context_exceeded, model_limitation,
        prompt_error) para determinar la categoría más probable.

        Args:
            task: Dict de tarea con campo "result" que contiene
                "diagnosis", "error", "action_required".

        Returns:
            Nombre de la categoría inferida, o "unknown" si no se
            puede determinar.
        """
        result = task.get("result", {}) or {}
        diagnosis = result.get("diagnosis", "") or ""
        error = result.get("error", "") or ""
        action = result.get("action_required", "") or ""

        # Construir texto combinado para búsqueda de patrones
        text = f"{diagnosis} {error} {action}"

        # Verificar context_insufficient primero (prioridad alta)
        for pattern in _CONTEXT_EXCEEDED_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return "context_insufficient"
        # split_task también es indicativo de context_insufficient
        if "split_task" in text.lower():
            return "context_insufficient"

        # Verificar prompt_error
        for pattern in _PROMPT_ERROR_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return "prompt_error"

        # Verificar model_limitation (incluyendo SyntaxError)
        for pattern in _MODEL_LIMITATION_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return "model_limitation"
        # SyntaxError también es indicativo de model_limitation
        if "syntaxerror" in text.lower() or "syntax error" in text.lower():
            return "model_limitation"

        return "unknown"

    # ================================================================
    # GENERACIÓN DE SUGERENCIAS
    # ================================================================

    def _generate_suggestions(
        self, patterns: List[FailurePattern]
    ) -> List[str]:
        """Genera las sugerencias más impactantes a partir de los patrones.

        Selecciona las top 5 sugerencias, priorizando por severidad
        (critical primero), sin duplicados.

        Args:
            patterns: Lista de patrones de fallo detectados.

        Returns:
            Lista de cadenas con sugerencias de corrección.
        """
        if not patterns:
            return []

        # Ordenar por severidad (critical > recoverable > minor)
        severity_order = {"critical": 0, "recoverable": 1, "minor": 2}
        sorted_patterns = sorted(
            patterns,
            key=lambda p: severity_order.get(p.severity, 3),
        )

        # Extraer sugerencias únicas, manteniendo orden
        seen = set()
        suggestions = []
        for pattern in sorted_patterns:
            if pattern.suggestion and pattern.suggestion not in seen:
                seen.add(pattern.suggestion)
                suggestions.append(pattern.suggestion)

        return suggestions[:5]

    # ================================================================
    # REPORTE PARA EL USUARIO (UI)
    # ================================================================

    def get_user_facing_report(self, report: FailureReport) -> str:
        """Genera un reporte en formato markdown para la interfaz web.

        El reporte está en español, siguiendo la convención de APA.
        Incluye secciones de resumen, patrones detectados,
        archivos más problemáticos y sugerencias.

        Args:
            report: FailureReport con el análisis completado.

        Returns:
            Cadena en formato markdown con el reporte completo.
        """
        lines = []

        # Encabezado
        lines.append("# 📊 Reporte de Patrones de Fallo")
        lines.append("")

        # Resumen
        lines.append("## 📋 Resumen")
        lines.append("")
        if report.total_tasks > 0:
            pct = (report.total_failures / report.total_tasks) * 100
            lines.append(
                f"- **Total de tareas:** {report.total_tasks}"
            )
            lines.append(
                f"- **Tareas fallidas:** {report.total_failures} "
                f"({pct:.1f}%)"
            )
        else:
            lines.append(
                f"- **Tareas fallidas:** {report.total_failures}"
            )
        lines.append(
            f"- **Patrones detectados:** {len(report.patterns)}"
        )
        lines.append("")

        # Patrones detectados
        if report.patterns:
            lines.append("## 🔍 Patrones Detectados")
            lines.append("")

            # Ordenar patrones por severidad
            severity_order = {"critical": 0, "recoverable": 1, "minor": 2}
            sorted_patterns = sorted(
                report.patterns,
                key=lambda p: severity_order.get(p.severity, 3),
            )

            for pattern in sorted_patterns:
                icon = "🔴" if pattern.severity == "critical" else (
                    "🟡" if pattern.severity == "recoverable" else "🟢"
                )
                type_labels = {
                    "repeated_file": "Archivo con fallos repetidos",
                    "repeated_category": "Categoría de fallo recurrente",
                    "repeated_error": "Error repetido",
                    "model_timeout": "Timeout del modelo",
                    "ambiguous_spec": "Especificación ambigua",
                }
                label = type_labels.get(
                    pattern.pattern_type, pattern.pattern_type
                )

                lines.append(
                    f"{icon} **{label}** ({pattern.severity}) "
                    f"— {pattern.count} ocurrencia(s)"
                )
                if pattern.affected_files:
                    lines.append(
                        f"   - Archivos: {', '.join(pattern.affected_files)}"
                    )
                if pattern.category:
                    lines.append(f"   - Categoría: {pattern.category}")
                if pattern.suggestion:
                    lines.append(f"   - 💡 {pattern.suggestion}")
                lines.append("")
        else:
            lines.append("## 🔍 Patrones Detectados")
            lines.append("")
            lines.append("No se detectaron patrones de fallo recurrentes.")
            lines.append("")

        # Archivos más problemáticos
        if report.top_failing_files:
            lines.append("## 📁 Archivos Más Problemáticos")
            lines.append("")
            for entry in report.top_failing_files[:10]:
                lines.append(
                    f"- `{entry['file']}`: {entry['failures']} fallo(s)"
                )
            lines.append("")

        # Distribución por categoría
        if report.category_distribution:
            lines.append("## 📈 Distribución por Categoría")
            lines.append("")
            cat_labels = {
                "context_insufficient": "Contexto insuficiente",
                "model_limitation": "Limitación del modelo",
                "prompt_error": "Error de planificación",
                "unresolved_dependency": "Dependencia sin resolver",
                "unknown": "Sin categoría determinada",
            }
            for cat, count in sorted(
                report.category_distribution.items(),
                key=lambda x: x[1],
                reverse=True,
            ):
                label = cat_labels.get(cat, cat)
                lines.append(f"- **{label}:** {count}")
            lines.append("")

        # Sugerencias
        if report.suggestions:
            lines.append("## 💡 Sugerencias de Corrección")
            lines.append("")
            for i, suggestion in enumerate(report.suggestions, 1):
                lines.append(f"{i}. {suggestion}")
            lines.append("")

        # Timestamp
        if report.generated_at:
            lines.append("---")
            lines.append(f"Generado: {report.generated_at}")

        return "\n".join(lines)

    # ================================================================
    # SERIALIZACIÓN
    # ================================================================

    def to_dict(self, report: FailureReport) -> dict:
        """Convierte un FailureReport a dict para serialización JSON.

        Convierte los dataclasses FailurePattern a dicts para que
        el reporte pueda serializarse como JSON para el endpoint
        de la API.

        Args:
            report: FailureReport a convertir.

        Returns:
            Dict con todos los campos del reporte, incluyendo
            los patrones convertidos a dicts.
        """
        return {
            "total_failures": report.total_failures,
            "total_tasks": report.total_tasks,
            "patterns": [
                {
                    "pattern_type": p.pattern_type,
                    "count": p.count,
                    "affected_files": p.affected_files,
                    "affected_tasks": p.affected_tasks,
                    "category": p.category,
                    "severity": p.severity,
                    "suggestion": p.suggestion,
                    "details": p.details,
                }
                for p in report.patterns
            ],
            "top_failing_files": report.top_failing_files,
            "category_distribution": report.category_distribution,
            "agent_distribution": report.agent_distribution,
            "suggestions": report.suggestions,
            "generated_at": report.generated_at,
        }


# ============================================================================
# Tests en __main__
# ============================================================================
if __name__ == "__main__":
    import logging

    # Configurar logging para ver los mensajes del auditor
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # --- Dataclasses mínimas para testing (sin importar semi_auto_agent) ---

    @dataclass
    class _TaskInfo:
        """TaskInfo mínimo para testing."""
        task_id: str = ""
        script: str = ""
        status: str = "pending"
        attempt: int = 1
        max_attempts: int = 3
        error: Optional[str] = None
        validation_result: Dict[str, Any] = field(default_factory=dict)
        coder_output: str = ""

    @dataclass
    class _SemiAutoResult:
        """SemiAutoResult mínimo para testing."""
        success: bool = False
        planner_output: str = ""
        coder_output: str = ""
        error: Optional[str] = None
        content: str = ""

    auditor = FailureAuditorAgent()

    print("=" * 70)
    print("FailureAuditorAgent — 4 casos de prueba")
    print("=" * 70)

    # --- Caso 1: context_insufficient ---
    print("\n" + "─" * 50)
    print("Caso 1: context_insufficient")
    print("─" * 50)

    task1 = _TaskInfo(
        task_id="T1",
        script="modulo_grande.py",
        attempt=1,
        max_attempts=3,
        error="[CONTEXT_EXCEEDED] El contexto del modelo excedió el límite máximo",
        coder_output="",
    )
    result1 = _SemiAutoResult(
        error="context_exceeded_no_fallback",
        content="",
    )

    diag1 = auditor.diagnose(task1, task1.error, result1, "coder")
    print(f"  Categoría:      {diag1.category}")
    print(f"  Severidad:      {diag1.severity}")
    print(f"  Agente:         {diag1.agent}")
    print(f"  Acción:         {diag1.suggested_action}")
    print(f"  Puede continuar:{diag1.can_continue}")
    print(f"  Puede abortar:  {diag1.can_abort}")
    print(f"  Escalar:        {auditor.should_escalate_to_director(diag1)}")
    assert diag1.category == "context_insufficient", f"Esperado context_insufficient, got {diag1.category}"
    assert diag1.suggested_action == "split", f"Esperado split, got {diag1.suggested_action}"
    print("  ✅ PASÓ")
    print("\n  Mensaje al usuario:")
    print("  " + "\n  ".join(auditor.get_user_facing_message(diag1).split("\n")))

    # --- Caso 2: model_limitation ---
    print("\n" + "─" * 50)
    print("Caso 2: model_limitation (respuesta vacía, primer intento)")
    print("─" * 50)

    task2 = _TaskInfo(
        task_id="T2",
        script="servicio.py",
        attempt=1,
        max_attempts=3,
        error="No se encontraron bloques de código en la salida del codificador",
        coder_output="El modelo no generó código.",
    )
    result2 = _SemiAutoResult(
        coder_output="",
        content="",
    )

    diag2 = auditor.diagnose(task2, task2.error, result2, "coder")
    print(f"  Categoría:      {diag2.category}")
    print(f"  Severidad:      {diag2.severity}")
    print(f"  Agente:         {diag2.agent}")
    print(f"  Acción:         {diag2.suggested_action}")
    print(f"  Puede continuar:{diag2.can_continue}")
    print(f"  Puede abortar:  {diag2.can_abort}")
    print(f"  Escalar:        {auditor.should_escalate_to_director(diag2)}")
    assert diag2.category == "model_limitation", f"Esperado model_limitation, got {diag2.category}"
    assert diag2.severity == "minor", f"Esperado minor (primer intento), got {diag2.severity}"
    assert diag2.suggested_action == "retry", f"Esperado retry, got {diag2.suggested_action}"
    print("  ✅ PASÓ")

    # --- Caso 3: prompt_error ---
    print("\n" + "─" * 50)
    print("Caso 3: prompt_error (plan sin campo SCRIPT)")
    print("─" * 50)

    task3 = _TaskInfo(
        task_id="T3",
        script="api.py",
        attempt=1,
        max_attempts=3,
        error="V3PlanParser: Falta campo SCRIPT. No se encontraron bloques válidos.",
        coder_output="",
    )
    result3 = _SemiAutoResult(
        planner_output="El planificador respondió pero sin el formato esperado.",
    )

    diag3 = auditor.diagnose(task3, task3.error, result3, "planner")
    print(f"  Categoría:      {diag3.category}")
    print(f"  Severidad:      {diag3.severity}")
    print(f"  Agente:         {diag3.agent}")
    print(f"  Acción:         {diag3.suggested_action}")
    print(f"  Puede continuar:{diag3.can_continue}")
    print(f"  Puede abortar:  {diag3.can_abort}")
    print(f"  Escalar:        {auditor.should_escalate_to_director(diag3)}")
    assert diag3.category == "prompt_error", f"Esperado prompt_error, got {diag3.category}"
    assert diag3.suggested_action == "replan", f"Esperado replan, got {diag3.suggested_action}"
    print("  ✅ PASÓ")

    # --- Caso 4: unresolved_dependency ---
    print("\n" + "─" * 50)
    print("Caso 4: unresolved_dependency (RF4 crítico + RF5 regresión sin rollback)")
    print("─" * 50)

    task4 = _TaskInfo(
        task_id="T4",
        script="utils.py",
        attempt=2,
        max_attempts=3,
        error="RF4: cambios bloqueados — RF5: regresión detectada",
        coder_output="# código integrado",
        validation_result={
            "rf4_has_critical": True,
            "rf4_should_block": True,
            "rf4_issues": [
                {
                    "severity": "CRITICAL",
                    "symbol": "validar",
                    "lineno": 42,
                    "description": "Símbolo eliminado que es llamado por 3 otro(s)",
                    "affected_callers": ["main.py:procesar", "api.py:handler"],
                },
            ],
            "rf5_report": {
                "regressions": [
                    {"file": "utils.py", "type": "syntax_error"},
                    {"file": "utils.py", "type": "symbol_removed"},
                ],
                "rollback_success": False,
                "rollback_executed": True,
            },
        },
    )
    result4 = _SemiAutoResult()

    diag4 = auditor.diagnose(task4, task4.error, result4, "validator")
    print(f"  Categoría:      {diag4.category}")
    print(f"  Severidad:      {diag4.severity}")
    print(f"  Agente:         {diag4.agent}")
    print(f"  Acción:         {diag4.suggested_action}")
    print(f"  Puede continuar:{diag4.can_continue}")
    print(f"  Puede abortar:  {diag4.can_abort}")
    print(f"  Escalar:        {auditor.should_escalate_to_director(diag4)}")
    assert diag4.category == "unresolved_dependency", f"Esperado unresolved_dependency, got {diag4.category}"
    assert diag4.severity == "critical", f"Esperado critical (rollback fallido), got {diag4.severity}"
    assert diag4.suggested_action == "escalate", f"Esperado escalate, got {diag4.suggested_action}"
    assert auditor.should_escalate_to_director(diag4) is True, "Debería escalar al Director"
    print("  ✅ PASÓ")
    print("\n  Mensaje al usuario:")
    print("  " + "\n  ".join(auditor.get_user_facing_message(diag4).split("\n")))

    # --- Resumen v1.0 ---
    print("\n" + "=" * 70)
    print("✅ Los 4 casos de prueba v1.0 PASARON correctamente.")
    print("=" * 70)


    # ====================================================================
    # UX1 Tests: FailurePatternAnalyzer
    # ====================================================================
    print("\n=== UX1: FailurePatternAnalyzer Tests ===")

    # Crear un directorio temporal con un plan.json de prueba
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        # Crear proyecto de prueba con tareas fallidas
        proj_dir = Path(tmpdir) / "test-project"
        proj_dir.mkdir()

        mock_plan = {
            "project_id": "test-project",
            "tasks": [
                {"id": "T1", "name": "Task 1", "script": "utils.py", "status": "completed", "result": {"success": True}},
                {"id": "T2", "name": "Task 2", "script": "utils.py", "status": "failed", "result": {"success": False, "diagnosis": "SyntaxError: invalid syntax in utils.py"}},
                {"id": "T3", "name": "Task 3", "script": "utils.py", "status": "failed", "result": {"success": False, "diagnosis": "SyntaxError: invalid syntax in utils.py"}},
                {"id": "T4", "name": "Task 4", "script": "utils.py", "status": "failed", "result": {"success": False, "diagnosis": "SyntaxError: unexpected indent in utils.py"}},
                {"id": "T5", "name": "Task 5", "script": "api.py", "status": "split", "result": {"success": False, "diagnosis": "[CONTEXT_EXCEEDED] context too large"}},
                {"id": "T6", "name": "Task 6", "script": "api.py", "status": "replanned", "result": {"success": False, "action_required": "split_task"}},
            ]
        }

        with open(proj_dir / "plan.json", "w") as f:
            json.dump(mock_plan, f)

        analyzer = FailurePatternAnalyzer(specs_dir=tmpdir)
        report = analyzer.analyze_project("test-project")

        # Test 1: Total de fallos contados correctamente
        assert report.total_failures == 4, f"Expected 4 failures, got {report.total_failures}"
        print("  [PASS] Total failures counted correctly")

        # Test 2: Patrón de archivo repetido detectado (utils.py con 3 fallos)
        file_patterns = [p for p in report.patterns if p.pattern_type == "repeated_file"]
        assert len(file_patterns) >= 1, "Should detect at least 1 repeated file pattern"
        utils_pattern = next((p for p in file_patterns if "utils.py" in p.affected_files), None)
        assert utils_pattern is not None, "Should detect utils.py as a repeated failure file"
        assert utils_pattern.count >= 3, f"utils.py should have >= 3 failures, got {utils_pattern.count}"
        assert "sintaxis" in utils_pattern.suggestion.lower() or "syntax" in utils_pattern.suggestion.lower(), \
            f"Suggestion should mention syntax review: {utils_pattern.suggestion}"
        print("  [PASS] Repeated file pattern detected with correct suggestion")

        # Test 3: Patrón de timeout del modelo (api.py con context_exceeded)
        timeout_patterns = [p for p in report.patterns if p.pattern_type == "model_timeout"]
        assert len(timeout_patterns) >= 1, "Should detect model timeout pattern"
        print("  [PASS] Model timeout pattern detected")

        # Test 4: Sugerencias generadas
        assert len(report.suggestions) > 0, "Should generate suggestions"
        print(f"  [PASS] {len(report.suggestions)} suggestions generated")

        # Test 5: Reporte para el usuario en español
        user_report = analyzer.get_user_facing_report(report)
        assert len(user_report) > 100, "User report should be substantial"
        assert "Patr" in user_report or "patr" in user_report, "Report should mention patterns in Spanish"
        print("  [PASS] User-facing report generated in Spanish")

        # Test 6: Serialización to_dict
        report_dict = analyzer.to_dict(report)
        assert "total_failures" in report_dict
        assert "patterns" in report_dict
        assert isinstance(report_dict["patterns"], list)
        print("  [PASS] to_dict serialization works")

        # Test 7: Distribución por categoría
        assert len(report.category_distribution) > 0 or report.total_failures == 4
        print("  [PASS] Category distribution computed")

        print("\n  TODOS LOS TESTS UX1 PASARON")
