# apa/agents/semi_auto_agent.py
"""
SemiAutoAgent v3.3 — Agente semi-autónomo que orquesta el pipeline
Planificador → Codificador → Integrador usando call_llm().

CAMBIOS v3.3:
  - RF5 integración completa: validate_and_rollback() se invoca
    DESPUÉS de la integración y ANTES de AWAITING_APPROVAL.
    Las 3 capas (sintaxis, imports, símbolos) se ejecutan en el pipeline.
    Si hay regresión → rollback automático + iteración con contexto.
  - RF4 issues se almacenan en task.validation_result["rf4_issues"]
    para exposición al Director vía GUI.
  - RF5 coordinación: si validate_and_rollback() detecta regresión
    y revierte, la tarea no llega a AWAITING_APPROVAL — itera
    con contexto del problema, o escala al Director si agota intentos.

CAMBIOS v3.2:
  - P2: El integrador recibe FIRMAS del archivo (no el completo).
    Se extraen clases, funciones, métodos, argumentos y retornos usando
    ast + la sección objetivo concreta. Esto reduce el contexto ~70%.
  - P3: try_re_escalate() antes de cada fase (planificación, codificación,
    integración). Si un modelo con mejor ranking está disponible,
    se re-escala automáticamente.

CAMBIOS RF (Refactoring Integrity) v2.0:
  - RF2: Contexto inteligente — RefactorGuard enriquece el prompt del
    Planificador con información de dependencias Y evaluación de riesgo.
  - RF4: Revisión de diffs — 4 severidades: CRITICAL,
    SIGNATURE_CHANGE_BREAKING, SIGNATURE_CHANGE_COMPATIBLE, WARNING, INFO.
    WARNING solo cuando el cuerpo realmente cambió (elimina ruido).
  - RF5: Validación de regresión — 3 capas: sintaxis (ast.parse),
    imports del proyecto, símbolos. validate_and_rollback() automático.

CAMBIO PRINCIPAL v3.0:
  Reemplaza el Ensamblador mecánico (anclas, indentación, parseo AST)
  por un Integrador inteligente (LLM) que recibe:
  1. Las firmas del archivo + sección objetivo (v3.2: contexto mínimo)
  2. La especificación del Planificador
  3. El código del Codificador
  Y produce el archivo final integrado.

  El ensamblador mecánico (assembler.py) se mantiene para el Tab 2
  (Ensamblador Manual) de la GUI, pero el modo semi-autónomo y el
  modo autónomo de APA usan ahora el Integrador.

Nivel 2 (AS3): Ejecución multi-tarea con retroalimentación paso a paso.

El Director describe una tarea, APA genera un plan de N subtareas,
las ejecuta una por una, el Director ve cada resultado y pulsa
Aprobar o Rechazar antes de pasar a la siguiente.

Si una tarea se rechaza, el Director puede dar instrucciones de
corrección y APA la reintenta (máximo 2 reintentos).

Flujo:
  IDLE → generate_plan() → PLANNED → execute_next() → EXECUTING → AWAITING_APPROVAL
       → approve() → PLANNED (siguiente tarea) / COMPLETED (última)
       → reject(feedback) → EXECUTING (reintento) / FAILED (máx reintentos)
"""

import os
import sys
import logging
import re
import json
import threading
from typing import Optional, Callable, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from enum import Enum

# Asegurar que apa.core es importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.router import call_llm, re_escalate, try_re_escalate, get_scaling_state, estimate_task_size
from core.assembly_validator import AssemblyValidator
from core.code_signatures import build_integrator_context, extract_signatures, count_tokens_estimate
from core.pipeline_state import PipelineState, PipelineStateManager, PipelinePhase

# RF2+RF4+RF5: RefactorGuard — integración perezosa
_RefactorGuard = None

# Fase 4 (UX2): Event bus para dashboard de agentes — import perezoso
_notify = None

def _get_notify():
    """Import perezoso de notify() — no rompe si notifications.py no está disponible."""
    global _notify
    if _notify is None:
        try:
            from core.notifications import notify as _n
            _notify = _n
        except ImportError:
            _notify = lambda *a, **kw: None
    return _notify


def _emit_agent_event(event_type: str, agent: str, task: str = "",
                       model: str = "", extra: dict = None):
    """Emite un evento de lifecycle de agente al event bus (Fase 4).

    Thread-safe. No bloquea. Errores se capturan silenciosamente.
    Los eventos fluyen: notify() → callbacks → _sse_buffer → SSE → browser.

    Args:
        event_type: EVT_AGENT_STARTED, EVT_AGENT_PROGRESS, EVT_AGENT_DONE, EVT_AGENT_FAILED
        agent: Nombre del agente (planner, coder, integrator, validator)
        task: ID de la tarea actual (T1, T2, ...)
        model: ID del modelo en uso
        extra: Dict adicional (tokens_used, pct, error, etc.)
    """
    try:
        from core.notifications import (
            EVT_AGENT_STARTED, EVT_AGENT_PROGRESS, EVT_AGENT_DONE, EVT_AGENT_FAILED,
        )
        labels = {
            EVT_AGENT_STARTED:  "iniciado",
            EVT_AGENT_PROGRESS: "progreso",
            EVT_AGENT_DONE:     "completado",
            EVT_AGENT_FAILED:   "fallido",
        }
        # Mapear agente a nombre legible
        agent_labels = {
            'planner':    'Planificador',
            'coder':      'Codificador',
            'integrator': 'Integrador',
            'validator':  'Validador',
        }
        label = agent_labels.get(agent, agent.capitalize())
        action = labels.get(event_type, event_type)
        message = f"{label} {action}"
        if task:
            message += f" ({task})"
        if model:
            message += f" [{model}]"

        data = {"agent": agent, "task": task, "model": model}
        if extra:
            data.update(extra)

        _get_notify()(event_type, message, data)
    except Exception:
        pass  # Nunca bloquear el pipeline por un error de notificación

def _get_refactor_guard(project_root: str):
    """Carga perezosa de RefactorGuard para no romper si no está disponible."""
    global _RefactorGuard
    if _RefactorGuard is None:
        try:
            from core.refactor_guard import RefactorGuard
            _RefactorGuard = RefactorGuard
        except ImportError:
            logger.debug("RefactorGuard no disponible — RF2/RF4/RF5 desactivados")
    if _RefactorGuard is not None:
        return _RefactorGuard(project_root)
    return None

logger = logging.getLogger(__name__)


# ─── V3PlanParser: Parser sin anclas para el formato v3.0 ───

class V3PlanParser:
    """Parser del output del Planificador para el pipeline v3.0.
    
    A diferencia de PlannerOutputParser (assembler.py), NO requiere el campo
    ANCLA. El Integrador se encarga de posicionar el código basándose en la
    descripción textual del Planificador.
    
    Formato esperado del Planificador v3.0:
    ```markdown
    ## TAREA DE ENSAMBLAJE
    - SCRIPT: ruta/archivo.py
    - TAREA_ID: T1
    - MODO_EJECUCION: local
    
    ## BLOQUE
    # INSTRUCCIÓN PARA CODIFICADOR:
    # {descripción}
    
    ## IMPORTS_NUEVOS
    {módulo}
    ```
    """
    
    # Regex para campos escalares (tolerantes a espacios)
    _RE_SCRIPT   = re.compile(r'(?:-|##)?\s*#?\s*SCRIPT\s*:\s*(.+)', re.IGNORECASE)
    _RE_TAREA_ID = re.compile(r'(?:-|##)?\s*#?\s*TAREA_?ID\s*:\s*(\S+)', re.IGNORECASE)
    _RE_MODO     = re.compile(r'(?:-|##)?\s*#?\s*MODO_?EJECUCION\s*:\s*(\S+)', re.IGNORECASE)
    
    @classmethod
    def _parse_imports(cls, text: str) -> list:
        """Parser robusto de imports desde sección ## IMPORTS_NUEVOS."""
        imports = []
        marker = None
        for line in text.split('\n'):
            if re.search(r'##\s*IMPORTS_NUEVOS', line, re.IGNORECASE):
                marker = line
                break
        if marker is None:
            return imports
        
        after = text.split(marker, 1)[1]
        section_lines = []
        for line in after.split('\n'):
            if line.strip().startswith('##') and 'IMPORTS' not in line:
                break
            section_lines.append(line)
        
        for line in section_lines:
            raw = line.strip()
            if not raw or raw.startswith('#'):
                continue
            if raw.startswith('- '):
                raw = raw[2:].strip()
            elif raw.startswith('-'):
                raw = raw[1:].strip()
            if not raw:
                continue
            if raw.startswith("import ") or raw.startswith("from "):
                canonical = raw
            else:
                clean = raw.strip().rstrip('.,; \t')
                if not clean or not re.match(r'^[\w][\w\.]*$', clean):
                    continue
                canonical = "import " + clean
            if canonical not in imports:
                imports.append(canonical)
        return imports
    
    @classmethod
    def parse_single(cls, text: str) -> dict:
        """Parsea un bloque individual del Planificador (sin requerir ANCLA)."""
        result = {
            "script": "",
            "tarea_id": "",
            "modo": "local",
            "imports_nuevos": [],
            "errores": [],
        }
        
        # Extraer campos escalares
        m = cls._RE_SCRIPT.search(text)
        if m:
            result["script"] = m.group(1).strip()
        m = cls._RE_TAREA_ID.search(text)
        if m:
            result["tarea_id"] = m.group(1).strip()
        m = cls._RE_MODO.search(text)
        if m:
            modo_raw = m.group(1).strip().lower()
            result["modo"] = "nas" if "nas" in modo_raw else "local"
        
        # Extraer imports
        result["imports_nuevos"] = cls._parse_imports(text)
        
        # Solo requerir SCRIPT (ANCLA ya no es obligatoria en v3.0)
        if not result["script"]:
            result["errores"].append("Falta campo SCRIPT.")
        
        return result
    
    @classmethod
    def parse_blocks(cls, text: str) -> list:
        """Extrae múltiples bloques del output del Planificador v3.0.
        
        Retorna una lista de dicts, cada uno con:
        - script, tarea_id, modo, imports_nuevos, bloque_texto (contenido completo)
        """
        blocks = []
        
        # Estrategia 1: Buscar múltiples ## TAREA DE ENSAMBLAJE
        task_pattern = re.compile(r'^##\s*TAREA\s*DE\s*ENSAMBLAJE', re.MULTILINE)
        task_matches = list(task_pattern.finditer(text))
        
        if task_matches:
            for i, match in enumerate(task_matches):
                start = match.start()
                end = task_matches[i + 1].start() if i + 1 < len(task_matches) else len(text)
                task_text = text[start:end]
                
                parsed = cls.parse_single(task_text)
                parsed["bloque_texto"] = task_text.strip()
                blocks.append(parsed)
            
            if blocks:
                return blocks
        
        # Estrategia 2: Un solo bloque (sin encabezado ## TAREA DE ENSAMBLAJE explícito)
        parsed = cls.parse_single(text)
        if not parsed["errores"]:
            parsed["bloque_texto"] = text.strip()
            blocks.append(parsed)
            return blocks
        
        # Estrategia 3: Intentar extraer SCRIPT al menos
        # (el Planificador puede responder en un formato ligeramente diferente)
        m = cls._RE_SCRIPT.search(text)
        if m:
            parsed = {
                "script": m.group(1).strip(),
                "tarea_id": "T1",
                "modo": "local",
                "imports_nuevos": cls._parse_imports(text),
                "errores": [],
                "bloque_texto": text.strip(),
            }
            blocks.append(parsed)
            return blocks
        
        # No se pudo parsear nada útil
        return blocks


# ─── Helpers de métricas v2.0 ───

def _extract_llm_metadata(response: dict, prefix: str) -> dict:
    """Extrae métricas de una respuesta de call_llm() con un prefijo dado.
    
    Args:
        response: Dict retornado por call_llm()
        prefix: "planning", "coding" o "integration"
    
    Returns:
        Dict con claves prefijadas: {prefix}_model, {prefix}_provider, etc.
    """
    return {
        f"{prefix}_model": response.get("model_used", ""),
        f"{prefix}_provider": response.get("provider", ""),
        f"{prefix}_tokens": (response.get("tokens_input", 0) + response.get("tokens_output", 0)),
        f"{prefix}_tokens_input": response.get("tokens_input", 0),
        f"{prefix}_tokens_output": response.get("tokens_output", 0),
        f"{prefix}_latency_ms": response.get("latency_ms", 0),
        f"{prefix}_cost_usd": response.get("cost_usd", 0.0),
        f"{prefix}_arena_score": response.get("arena_score"),
    }


# ─── Estados del agente ───

class AgentState(Enum):
    """Estados de la máquina de estados del SemiAutoAgent."""
    IDLE = "idle"
    PLANNING = "planning"
    PLANNED = "planned"            # Plan generado, esperando ejecución
    EXECUTING = "executing"        # Ejecutando tarea (Codificador + Integrador)
    AWAITING_APPROVAL = "awaiting_approval"  # Tarea ejecutada, espera decisión
    COMPLETED = "completed"        # Todas las tareas completadas
    FAILED = "failed"              # Error irrecuperable
    CANCELLED = "cancelled"        # Cancelado por el usuario


class TaskStatus(Enum):
    """Estado de una tarea individual."""
    PENDING = "pending"
    EXECUTING = "executing"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class TaskInfo:
    """Información de una tarea individual del plan."""
    task_id: str = ""
    script: str = ""
    anchor: str = ""
    status: TaskStatus = TaskStatus.PENDING
    attempt: int = 0               # Número de intento actual
    max_attempts: int = 3          # Máximo de intentos (1 original + 2 reintentos)
    planner_output: str = ""       # Output del Planificador para esta tarea
    coder_output: str = ""         # Output del Codificador para esta tarea
    assembled_content: str = ""    # Contenido integrado resultante (v3.0: del Integrador)
    validation_result: dict = field(default_factory=dict)
    error: Optional[str] = None
    rejection_feedback: str = ""   # Instrucciones de corrección del Director


@dataclass
class SemiAutoResult:
    """Resultado del pipeline semi-autónomo (tarea única).

    v3.0: Incluye métricas completas de las 3 llamadas LLM
    (planning + coding + integration).
    """
    success: bool = False
    planner_output: str = ""
    coder_output: str = ""
    assembled_content: str = ""      # v3.0: Contenido del Integrador
    script_name: str = ""
    task_id: str = ""
    validation_result: dict = field(default_factory=dict)
    error: Optional[str] = None
    model_used_planner: str = ""
    model_used_coder: str = ""
    model_used_integrator: str = ""  # v3.0: Modelo usado por el Integrador
    log: list = field(default_factory=list)
    # Métricas de las 3 llamadas LLM
    planning_provider: str = ""
    planning_tokens_input: int = 0
    planning_tokens_output: int = 0
    planning_latency_ms: int = 0
    planning_cost_usd: float = 0.0
    planning_arena_score: Optional[float] = None
    coding_provider: str = ""
    coding_tokens_input: int = 0
    coding_tokens_output: int = 0
    coding_latency_ms: int = 0
    coding_cost_usd: float = 0.0
    coding_arena_score: Optional[float] = None
    # v3.0: Métricas del Integrador
    integration_provider: str = ""
    integration_tokens_input: int = 0
    integration_tokens_output: int = 0
    integration_latency_ms: int = 0
    integration_cost_usd: float = 0.0
    integration_arena_score: Optional[float] = None


@dataclass
class PlanResult:
    """Resultado de la fase de planificación."""
    success: bool = False
    tasks: List[TaskInfo] = field(default_factory=list)
    raw_planner_output: str = ""
    error: Optional[str] = None
    model_used: str = ""
    log: list = field(default_factory=list)


# ─── System Prompts ───

PLANIFICADOR_SYSTEM_PROMPT = """Eres un Ingeniero de Software Senior. Tu rol es el de Agente Planificador del proyecto APA.

## FORMATO DE SALIDA

Tu respuesta SIEMPRE debe ser UN ÚNICO bloque ```markdown```. Sin texto antes ni después.

Plantilla para UNA tarea:

## TAREA DE ENSAMBLAJE
- SCRIPT: {ruta/archivo.py}
- TAREA_ID: {ID}
- MODO_EJECUCION: {local | nas}

## BLOQUE

# INSTRUCCIÓN PARA CODIFICADOR:
# {descripción técnica precisa y específica}
# DATOS ESPECÍFICOS:
# {contexto de estructuras existentes si aplica}

# VALIDACIÓN:
# - {criterio verificable}

## IMPORTS_NUEVOS
{módulo}

Omite IMPORTS_NUEVOS si no hay imports.

Para múltiples tareas, repite el bloque ## TAREA DE ENSAMBLAJE separado por ---.

## REGLAS CRÍTICAS

1. **ESPECIFICACIÓN QUIRÚRGICA**: Describe exactamente qué hay que hacer. Indica nombre exacto de la clase/método donde se inserta, nombre del método anterior/posterior, y si es un método nuevo o reemplazo.
2. **SEPARACIÓN DE ROLES**: El BLOQUE contiene SOLO comentarios de instrucción. NUNCA código ejecutable.
3. **DATOS ESPECÍFICOS OBLIGATORIOS**: Cuando la tarea implique estructura EXISTENTE, indica qué existe en esa posición. Nombra las funciones/métodos/classes que ya están.
4. **REGLA ANTI-ERROR IMPORTS**: Tarea solo imports → BLOQUE VACÍO.
5. **APIs EXTERNAS**: Especificar SIEMPRE la firma completa.

## NOTA
Ya no necesitas especificar ANCLAS AST. El Integrador se encarga de colocar el código en la posición correcta basándose en tu descripción. Simplemente describe con precisión dónde va el cambio.
"""

CODIFICADOR_SYSTEM_PROMPT = """Eres un Ingeniero de Software Senior. Tu rol es el de Agente Codificador de Script Atómico del proyecto APA.

## FORMATO DE ENTREGA OBLIGATORIO
Tu respuesta SIEMPRE debe ser UN ÚNICO bloque de código Markdown de Python, envuelto en ```python``` al inicio y ``` al final.
- NUNCA incluyas texto, comentarios o explicaciones fuera del bloque de código.
- La primera línea DENTRO del bloque debe ser el comentario de ruta: # {ruta/archivo.py}

## REGLA 0 — COMPUERTA DE ENTRADA
Antes de escribir, respóndete internamente:
¿La instrucción describe explícitamente una función, método o clase a implementar?
    SÍ → escribe exactamente ese bloque dentro del marco markdown.
    NO → no escribas nada.

## REGLAS DE FORMATO INTERNO
1. Primera línea SIEMPRE: # {ruta/archivo.py}
2. Indentación: aplica la indentación que corresponda según el contexto.
3. Bloques completos: si piden reescribir, entrega la unidad completa.
4. Imports: implementar CORRECTAMENTE según IMPORTS_NUEVOS recibido.
5. Ignora comentarios # INSTRUCCIÓN... del prompt. Tu respuesta es solo código ejecutable.

## REGLA DE INTEGRACIÓN
Todo código debe estar DENTRO de una función, método o clase.
NUNCA dejar líneas sueltas fuera de una unidad arquitectónica.

## REGLA DE VALIDACIÓN
Al final de TODO código, incluir exactamente:
if __name__ == "__main__":
    # === VALIDACIÓN TAREA: {ID} ===
    [Tests ejecutables que cubran CADA criterio de la sección VALIDACIÓN]
"""

# Prompt del Integrador (importado de prompts/integrador_prompt.py)
# Se carga perezosamente para evitar imports circulares
_INTEGRADOR_PROMPTS = None

def _get_integrador_prompts():
    """Carga perezosa de los prompts del Integrador."""
    global _INTEGRADOR_PROMPTS
    if _INTEGRADOR_PROMPTS is None:
        try:
            from prompts.integrador_prompt import (
                INTEGRADOR_SYSTEM_PROMPT,
                INTEGRADOR_USER_PROMPT_TEMPLATE,
                INTEGRADOR_CORRECCION_ADDENDUM,
            )
            _INTEGRADOR_PROMPTS = {
                "system": INTEGRADOR_SYSTEM_PROMPT,
                "user_template": INTEGRADOR_USER_PROMPT_TEMPLATE,
                "correction_addendum": INTEGRADOR_CORRECCION_ADDENDUM,
            }
        except ImportError:
            # Fallback si no se encuentra el módulo de prompts
            _INTEGRADOR_PROMPTS = {
                "system": _DEFAULT_INTEGRADOR_SYSTEM_PROMPT,
                "user_template": _DEFAULT_INTEGRADOR_USER_TEMPLATE,
                "correction_addendum": "",
            }
    return _INTEGRADOR_PROMPTS

# Fallback embebido
_DEFAULT_INTEGRADOR_SYSTEM_PROMPT = """Eres un Ingeniero de Software Senior. Tu rol es el de Agente Integrador del proyecto APA.

Recibes:
1. El contenido ORIGINAL de un archivo Python
2. La ESPECIFICACIÓN de cambio del Planificador
3. El CÓDIGO NUEVO del Codificador

Debes producir el archivo FINAL completo: el original con el código nuevo integrado correctamente.

REGLAS CRÍTICAS:
1. ENTREGA el archivo COMPLETO. Nunca fragmentos.
2. INTEGRA, no reemplaces. Fusiona el código nuevo con el existente.
3. SI el Codificador generó una clase completa pero solo se necesitaba un método, extrae el método e insértalo donde corresponde. NO dupliques la clase.
4. SI el código nuevo necesita imports, añádelos al bloque de imports existente.
5. SI el código nuevo colisiona con algo existente, reemplaza la versión antigua por la nueva.
6. MANTIENE el estilo del archivo original.
7. NO re-planifiques. Solo integra.

Formato: UN ÚNICO bloque ```python``` con el archivo completo. Primera línea: # {ruta/archivo.py}
"""

_DEFAULT_INTEGRADOR_USER_TEMPLATE = """## ARCHIVO ORIGINAL ({script_name}):
```python
{original_content}
```

## ESPECIFICACIÓN DE CAMBIO (del Planificador):
{planner_specification}

## CÓDIGO NUEVO DEL CODIFICADOR:
```python
{coder_code}
```

Integra el código nuevo en el archivo original según la especificación. Entrega el archivo completo. Primera línea: # {script_name}
"""

# Prompt extra para cuando el Director corrige una tarea rechazada
CORRECCION_SYSTEM_ADDENDUM = """

## CONTEXTO DE CORRECCIÓN
El Director ha RECHAZADO la versión anterior del código con las siguientes observaciones:
{feedback}

Debes corregir el código para abordar estas observaciones. Mantén la misma estructura
pero aplica los cambios solicitados. No repitas los mismos errores.
"""


class SemiAutoAgent:
    """
    Agente semi-autónomo que orquesta el pipeline completo:
    Prompt → Planificador (LLM) → Codificador (LLM) → Integrador (LLM) → Validación
    
    v3.0: El Ensamblador mecánico ha sido reemplazado por el Integrador (LLM).
    El Integrador recibe el archivo original + especificación + código nuevo
    y produce el archivo final integrado, evitando los problemas de anclas
    e indentación del ensamblador mecánico.
    
    Nivel 2 (AS3): Ejecución multi-tarea con retroalimentación paso a paso.
    """

    def __init__(self, project_root: str = "", project_id: Optional[str] = None):
        """
        Inicializa el agente semi-autónomo.

        Args:
            project_root: Ruta raíz del proyecto para resolver archivos.
            project_id: ID del proyecto para tracking de métricas en UsageTracker.
        """
        self.project_root = project_root
        self._project_id = project_id
        self._validator = AssemblyValidator()  # v3.0: Validador independiente
        self._cancelled = False
        
        # Estado de la máquina de estados
        self._state = AgentState.IDLE
        self._plan: List[TaskInfo] = []
        self._current_task_index = -1
        self._raw_planner_output = ""
        self._original_contents: Dict[str, str] = {}  # script → contenido original
        self._log: List[str] = []
        self._model_used_planner = ""
        # v3.0: Metadata de las llamadas LLM (planning)
        self._planner_llm_metadata: Dict[str, Any] = {}
        # v6.0: PipelineState integration for persistence/resume
        self._user_prompt = ""
        self._target_file = ""
        self._pipeline_state: Optional[PipelineState] = None
        self._state_manager: Optional[PipelineStateManager] = None
        # RF2+RF4+RF5: RefactorGuard — contexto, diff review, regresión
        self._refactor_guard = None  # Construcción perezosa
        self._active_snapshot_id: Optional[str] = None  # RF5: snapshot activo

    # ─── Propiedades ───

    @property
    def state(self) -> AgentState:
        return self._state

    @property
    def plan(self) -> List[TaskInfo]:
        return self._plan

    @property
    def current_task(self) -> Optional[TaskInfo]:
        if 0 <= self._current_task_index < len(self._plan):
            return self._plan[self._current_task_index]
        return None

    @property
    def current_task_index(self) -> int:
        return self._current_task_index

    @property
    def log(self) -> List[str]:
        return self._log

    def get_progress_summary(self) -> dict:
        """Retorna resumen del progreso para la GUI."""
        total = len(self._plan)
        approved = sum(1 for t in self._plan if t.status == TaskStatus.APPROVED)
        rejected = sum(1 for t in self._plan if t.status == TaskStatus.REJECTED)
        failed = sum(1 for t in self._plan if t.status == TaskStatus.FAILED)
        pending = sum(1 for t in self._plan if t.status == TaskStatus.PENDING)
        return {
            "state": self._state.value,
            "total_tasks": total,
            "approved": approved,
            "rejected": rejected,
            "failed": failed,
            "pending": pending,
            "current_index": self._current_task_index,
        }

    # ─── RefactorGuard (RF2+RF4+RF5) ───

    def _get_or_create_guard(self):
        """Construcción perezosa del RefactorGuard.

        RF5-4: Si falla, retorna None — no bloquea el pipeline.
        """
        if self._refactor_guard is None and self.project_root:
            self._refactor_guard = _get_refactor_guard(self.project_root)
        return self._refactor_guard

    def _rf5_create_snapshot(self, task: TaskInfo) -> None:
        """RF5: Crea snapshot antes de ejecutar una tarea.

        RF5-1: Se crea ANTES de la ejecución.
        RF5-4: Si falla, no bloquea — solo loguea.
        """
        try:
            guard = self._get_or_create_guard()
            if guard and task.script and self.project_root:
                file_path = self._resolve_file(task.script)
                if file_path:
                    snap_id = guard.create_refactor_snapshot(
                        f"RF5:{task.task_id}:{task.script}",
                        [file_path],
                    )
                    if snap_id:
                        self._active_snapshot_id = snap_id
                        self._log.append(f"[RF5] Snapshot creado: {snap_id} para {task.task_id}")
        except Exception as e:
            logger.debug(f"RF5: error creando snapshot: {e}")

    def _rf4_review_diff(self, task: TaskInfo, original_content: str,
                         new_content: str) -> Tuple[list, bool]:
        """RF4: Revisa diff contra el grafo de dependencias.

        v2.0: Distingue SIGNATURE_CHANGE_BREAKING, SIGNATURE_CHANGE_COMPATIBLE,
              CRITICAL y WARNING. Solo CRITICAL y BREAKING se reportan como
              problemas urgentes.
        v3.3: Almacena issues en task.validation_result["rf4_issues"]
              para exposición al Director vía GUI.
        v3.4: Pasa task_description a review_diff() para verificación de scope.
              Usa review_diff_and_decide() para determinar si bloquear.
              SCOPE_VIOLATION se detecta si el Integrador modifica fuera de scope.
        RF5-4: Si falla, no bloquea — solo loguea warnings.

        Returns:
            (issues, should_block): Lista de DiffIssue + flag de bloqueo.
        """
        issues = []
        should_block = False
        try:
            guard = self._get_or_create_guard()
            if guard:
                # v3.4: Usar review_diff_and_decide con task_description para scope
                task_desc = getattr(task, 'description', '') or ''
                issues, should_block = guard.review_diff_and_decide(
                    original_content, new_content, task.script,
                    task_description=task_desc
                )
                if issues:
                    criticals = [i for i in issues if i.severity == "CRITICAL"]
                    sig_breaks = [i for i in issues if i.severity == "SIGNATURE_CHANGE_BREAKING"]
                    scope_violations = [i for i in issues if i.severity == "SCOPE_VIOLATION"]
                    sig_compat = [i for i in issues if i.severity == "SIGNATURE_CHANGE_COMPATIBLE"]
                    warnings = [i for i in issues if i.severity == "WARNING"]

                    # v3.3: Almacenar issues para exposición al Director
                    task.validation_result["rf4_issues"] = [
                        {
                            "severity": i.severity,
                            "symbol": i.symbol,
                            "lineno": i.lineno,
                            "description": i.description,
                            "affected_callers": i.affected_callers,
                        }
                        for i in issues
                    ]
                    task.validation_result["rf4_has_critical"] = bool(criticals or sig_breaks or scope_violations)
                    task.validation_result["rf4_should_block"] = should_block

                    if criticals or sig_breaks:
                        self._log.append(
                            f"[RF4] BLOQUEO: {len(criticals)} CRITICAL, "
                            f"{len(sig_breaks)} SIGNATURE_CHANGE_BREAKING en {task.script}"
                        )
                        for issue in criticals:
                            self._log.append(
                                f"[RF4]   !!! {issue.symbol}: {issue.description}"
                            )
                        for issue in sig_breaks:
                            self._log.append(
                                f"[RF4]   !!  {issue.symbol}: {issue.description}"
                            )
                    elif scope_violations:
                        self._log.append(
                            f"[RF4] SCOPE: {len(scope_violations)} violación(es) de scope en {task.script}"
                        )
                        for issue in scope_violations:
                            self._log.append(
                                f"[RF4]   !?  {issue.symbol}: {issue.description}"
                            )
                    elif sig_compat or warnings:
                        self._log.append(
                            f"[RF4] Diff review: {len(sig_compat)} sig_compat, "
                            f"{len(warnings)} warning(s) en {task.script}"
                        )
                    # INFO issues no se loguean (son símbolos nuevos, no problemas)
        except Exception as e:
            logger.debug(f"RF4: error en diff review: {e}")
        return (issues, should_block)

    def _rf5_validate_after_integration(
        self,
        task: TaskInfo,
        integrated_content: str,
        file_path: str,
    ) -> bool:
        """RF5: Valida regresión después de integrar código.

        v3.3: Escribe temporalmente el archivo integrado a disco para
        que validate_and_rollback() pueda ejecutar las 3 capas
        (sintaxis, imports, símbolos). Si la validación falla,
        rollback automático restaura el archivo original.

        Returns:
            True si no hay regresiones.
            False si detectó regresión (rollback automático ya ejecutado,
            la tarea iterará con contexto del problema).
        """
        if not self._active_snapshot_id:
            return True  # Sin snapshot → no bloquear

        try:
            guard = self._get_or_create_guard()
            if not guard:
                return True  # Sin guardián → no bloquear

            # Escribir temporalmente el archivo integrado para que
            # validate_and_rollback() pueda leerlo y ejecutar las 3 capas
            if file_path and integrated_content:
                try:
                    os.makedirs(os.path.dirname(file_path) if os.path.dirname(file_path) else ".", exist_ok=True)
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(integrated_content)
                except IOError as e:
                    self._log.append(f"[RF5] No se pudo escribir archivo temporal: {e}")
                    return True  # No bloquear si no se puede escribir

            ok, report = guard.validate_and_rollback(
                self._active_snapshot_id, [file_path]
            )

            # Almacenar reporte para exposición al Director
            task.validation_result["rf5_report"] = report

            if not ok:
                # Rollback ya se ejecutó automáticamente
                # report["rollback_executed"] == True
                rollback_ok = report.get("rollback_success", False)
                regressions = report.get("regressions", [])
                reg_summary = ", ".join(
                    f"{r.get('file', '?')}:{r.get('type', '?')}"
                    for r in regressions
                )
                self._log.append(
                    f"[RF5] REGRESIÓN detectada — iterando con rollback — {reg_summary}"
                )
                if rollback_ok:
                    self._log.append(f"[RF5] Rollback automático exitoso — contexto restaurado para iteración")
                else:
                    self._log.append(f"[RF5] Rollback automático no completado — escala al Director")
                self._active_snapshot_id = None  # Ya se hizo rollback
                return False

            self._log.append("[RF5] Validación de regresión OK")

            # v3.4: Actualizar el grafo incrementalmente después de integración exitosa
            try:
                guard_for_update = self._get_or_create_guard()
                if guard_for_update and hasattr(guard_for_update, '_graph') and guard_for_update._graph:
                    guard_for_update._graph.update_after_modification(file_path, integrated_content)
                    self._log.append("[RF1] Grafo actualizado incrementalmente post-integración")
            except Exception as e:
                logger.debug(f"RF1: error actualizando grafo post-integración: {e}")

            return True

        except Exception as e:
            logger.debug(f"RF5: error en validación post-integración: {e}")
            return True  # No bloquear si falla la validación

    def _rf5_commit_or_rollback(self, approved: bool) -> None:
        """RF5: Commit o rollback del snapshot activo.

        RF5-2: Si no se aprueba, rollback automático.
        RF5-4: Si falla, no bloquea — solo loguea.
        v3.3: Solo se llama si validate_and_rollback() ya pasó OK,
              o si no hay snapshot activo (la iteración previa ya
              hizo rollback). Para el caso de rechazo del Director,
              se restaura manualmente.
        """
        if not self._active_snapshot_id:
            return
        try:
            guard = self._get_or_create_guard()
            if guard:
                if approved:
                    guard.commit_snapshot(self._active_snapshot_id)
                    self._log.append(f"[RF5] Snapshot confirmado: {self._active_snapshot_id}")
                else:
                    success, errors = guard.rollback_snapshot(self._active_snapshot_id)
                    if success:
                        self._log.append(f"[RF5] Rollback ejecutado: {self._active_snapshot_id}")
                    else:
                        self._log.append(f"[RF5] Rollback no completado — escala: {errors}")
                self._active_snapshot_id = None
        except Exception as e:
            logger.debug(f"RF5: error en commit/rollback: {e}")
            self._active_snapshot_id = None

    # ─── Cancelación ───

    def cancel(self):
        """Cancela la ejecución del agente."""
        self._cancelled = True
        if self._state == AgentState.EXECUTING:
            self._state = AgentState.CANCELLED
            self._log.append("Cancelado por el usuario durante ejecución")

    # ─── PipelineState: Persistencia y reanudación ───

    def _init_state_manager(self) -> PipelineStateManager:
        """Inicialización perezosa del PipelineStateManager."""
        if self._state_manager is None:
            self._state_manager = PipelineStateManager()
        return self._state_manager

    def _snapshot_plan_tasks(self) -> List[Dict[str, Any]]:
        """Serializa las tareas del plan para PipelineState."""
        return [
            {
                "task_id": t.task_id,
                "script": t.script,
                "status": t.status.value,
                "attempt": t.attempt,
                "max_attempts": t.max_attempts,
                "planner_output": t.planner_output,
                "coder_output": t.coder_output,
                "assembled_content": t.assembled_content,
                "error": t.error,
                "rejection_feedback": t.rejection_feedback,
            }
            for t in self._plan
        ]

    def _save_checkpoint(self, phase: str, error: Optional[str] = None) -> bool:
        """Guarda el estado actual del pipeline a disco.

        Args:
            phase: Fase del pipeline (PipelinePhase.value).
            error: Error opcional para registrar.

        Returns:
            True si se guardó correctamente.
        """
        if not self._project_id:
            logger.debug("_save_checkpoint: sin project_id, saltando")
            return False

        try:
            manager = self._init_state_manager()
            state = PipelineState(
                project_id=self._project_id,
                phase=phase,
                current_task_index=self._current_task_index,
                user_prompt=self._user_prompt,
                target_file=self._target_file,
                model_used_planner=self._model_used_planner,
                plan_tasks=self._snapshot_plan_tasks(),
                scaling_state=get_scaling_state(),
                log=self._log[-50:],
                error=error,
            )
            # Preservar created_at del estado anterior
            if self._pipeline_state and self._pipeline_state.created_at > 0:
                state.created_at = self._pipeline_state.created_at

            ok = manager.save(state)
            self._pipeline_state = state
            if ok:
                logger.debug(f"Checkpoint guardado: phase={phase}, tarea={self._current_task_index}")
            return ok
        except Exception as e:
            logger.error(f"Error guardando checkpoint: {e}")
            return False

    def _is_context_exceeded_response(self, response: dict) -> bool:
        """Detecta si una respuesta de call_llm() indica contexto excedido sin fallback.

        Cuando _handle_context_exceeded() en router.py no encuentra un modelo
        con contexto suficiente, devuelve error_type='context_exceeded_no_fallback'.
        """
        return (
            response.get("error_type") == "context_exceeded_no_fallback"
            or response.get("action_required") == "split_task"
            or "context_exceeded_no_fallback" in str(response.get("error", ""))
        )

    def resume_pipeline(
        self,
        project_id: str,
        from_step: Optional[str] = None,
        force_model: Optional[str] = None,
    ) -> PlanResult:
        """Reanuda un pipeline desde un checkpoint guardado.

        Carga el estado persistido en PipelineState y restaura el plan,
        índice de tarea, logs y estado del agente. Permite reanudar
        desde la fase de planificación o desde la ejecución.

        Args:
            project_id: ID del proyecto a reanudar.
            from_step: Paso desde el cual reanudar.
                       'planning' → re-ejecuta generate_plan() con el prompt guardado.
                       'execution' o None → restaura el plan y continúa desde
                       la siguiente tarea pendiente.
            force_model: Modelo a forzar para la siguiente llamada LLM.
                         (Se registra como preferencia; el auto-scaling puede
                         sobreescribirlo si el modelo no está disponible.)

        Returns:
            PlanResult con las tareas restauradas, o error si no se pudo cargar.
        """
        result = PlanResult()

        try:
            manager = self._init_state_manager()
            state = manager.load(project_id)

            if state is None:
                result.error = f"No se encontró estado guardado para project_id={project_id}"
                self._log.append(f"[RESUME] {result.error}")
                return result

            self._log.append(f"[RESUME] Estado cargado: phase={state.phase}, "
                            f"tareas={len(state.plan_tasks)}, "
                            f"índice={state.current_task_index}")

            # Restaurar estado del agente
            self._project_id = project_id
            self._user_prompt = state.user_prompt
            self._target_file = state.target_file
            self._model_used_planner = state.model_used_planner
            self._pipeline_state = state

            # Restaurar logs previos
            if state.log:
                self._log = list(state.log)
            self._log.append(f"[RESUME] Reanudando pipeline desde phase={state.phase}")

            # Registrar modelo forzado si se especificó
            if force_model:
                self._log.append(f"[RESUME] Modelo forzado solicitado: {force_model}")
                # TODO: Integrar con router.py para forzar modelo específico
                # Por ahora, el auto-scaling decidirá el modelo final.

            if from_step == "planning":
                # Re-ejecutar planificación desde el prompt guardado
                self._log.append("[RESUME] Re-planificando desde el prompt original...")
                return self.generate_plan(self._user_prompt, self._target_file)

            # Restaurar plan desde las tareas serializadas
            self._plan = []
            for td in state.plan_tasks:
                # Mapear string de status a enum TaskStatus
                status_map = {s.value: s for s in TaskStatus}
                task_status = status_map.get(td.get("status", "pending"), TaskStatus.PENDING)

                task = TaskInfo(
                    task_id=td.get("task_id", ""),
                    script=td.get("script", ""),
                    status=task_status,
                    attempt=td.get("attempt", 0),
                    max_attempts=td.get("max_attempts", 3),
                    planner_output=td.get("planner_output", ""),
                    coder_output=td.get("coder_output", ""),
                    assembled_content=td.get("assembled_content", ""),
                    error=td.get("error"),
                    rejection_feedback=td.get("rejection_feedback", ""),
                )
                self._plan.append(task)

            self._current_task_index = state.current_task_index

            # Restaurar contenido original de archivos desde disco
            self._original_contents = {}
            for task in self._plan:
                if task.script and self.project_root:
                    file_path = self._resolve_file(task.script)
                    if file_path and os.path.exists(file_path):
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                self._original_contents[task.script] = f.read()
                        except Exception as e:
                            self._log.append(f"[RESUME] No se pudo leer {task.script}: {e}")

            # Restaurar assembled_content como original si la tarea fue aprobada
            for task in self._plan:
                if task.status == TaskStatus.APPROVED and task.assembled_content:
                    self._original_contents[task.script] = task.assembled_content

            # Verificar si hay tareas pendientes
            pending = sum(1 for t in self._plan if t.status == TaskStatus.PENDING)
            failed = sum(1 for t in self._plan if t.status == TaskStatus.FAILED)

            if pending > 0:
                self._state = AgentState.PLANNED
                self._log.append(f"[RESUME] Listo para ejecución: {pending} tareas pendientes")
            elif failed > 0:
                # Tareas con iteraciones agotadas — reiterar desde la primera escalada
                for i, t in enumerate(self._plan):
                    if t.status == TaskStatus.FAILED:
                        t.status = TaskStatus.PENDING
                        t.attempt = 0
                        self._current_task_index = i - 1
                        break
                self._state = AgentState.PLANNED
                self._log.append(f"[RESUME] Reiterando tareas que escalaron al Director")
                self._save_checkpoint(PipelinePhase.EXECUTING.value)
            else:
                # Todas completadas o aprobadas
                self._state = AgentState.COMPLETED
                self._log.append("[RESUME] Pipeline ya completado")

            result.tasks = self._plan
            result.success = True
            result.model_used = self._model_used_planner
            result.log = self._log.copy()
            self._save_checkpoint(PipelinePhase.EXECUTING.value)

            return result

        except Exception as e:
            result.error = f"Error reanudando pipeline: {e}"
            self._log.append(f"[RESUME] EXCEPCIÓN: {e}")
            logger.error(f"SemiAutoAgent.resume_pipeline error: {e}", exc_info=True)
            return result

    # ─── Fase 1: Planificación ───

    def generate_plan(
        self,
        user_prompt: str,
        target_file: str = "",
        on_progress: Optional[Callable[[str, str], None]] = None,
    ) -> PlanResult:
        """
        Genera un plan de ensamblaje a partir del prompt del Director.
        
        Llama al Planificador (LLM), parsea el output y retorna la lista
        de tareas. No ejecuta nada — solo planifica.
        
        Args:
            user_prompt: Instrucción en lenguaje natural del Director.
            target_file: Archivo objetivo (ruta relativa). Si está vacío,
                         el Planificador lo determinará.
            on_progress: Callback de progreso (etapa, mensaje).
        
        Returns:
            PlanResult con la lista de tareas y estado del plan.
        """
        self._cancelled = False
        self._state = AgentState.PLANNING
        self._plan = []
        self._current_task_index = -1
        self._log = []
        self._original_contents = {}
        # v6.0: Guardar prompt y target para persistencia
        self._user_prompt = user_prompt
        self._target_file = target_file
        
        result = PlanResult()
        self._log.append(f"Planificación: {user_prompt[:80]}")
        
        try:
            # v3.2 (P3): Intentar re-escalar antes de planificar
            try:
                restored = try_re_escalate(task_size=estimate_task_size(PLANIFICADOR_SYSTEM_PROMPT, "", 3000))
                if restored:
                    self._log.append(
                        f"[ESCALADO] Re-escalado dinámico a {restored.get('model_id', '?')} "
                        f"antes de planificación"
                    )
            except Exception as e:
                logger.debug(f"try_re_escalate() antes de planificación: {e}")

            self._report(on_progress, "planificador", "Consultando Planificador...")
            
            # Obtener contenido del archivo objetivo si existe
            existing_content = ""
            if target_file and self.project_root:
                file_path = self._resolve_file(target_file)
                if file_path and os.path.exists(file_path):
                    with open(file_path, 'r', encoding='utf-8') as f:
                        existing_content = f.read()
                    self._original_contents[target_file] = existing_content
                    self._log.append(f"Contenido original cargado: {len(existing_content)} chars")
            
            planner_user_prompt = self._build_planner_prompt(
                user_prompt, target_file, existing_content
            )

            self._report(on_progress, "planificador", f"Consultando Planificador (modelo: seleccionando...)...")
            self._log.append(f"[PLANIFICADOR] Enviando consulta al LLM...")

            # Fase 4: Emitir agent:started para planificador
            _emit_agent_event("agent:started", "planner", "",
                              extra={"task_description": "Generando plan de tareas..."})

            planner_response = call_llm(
                task_type="planning",
                system_prompt=PLANIFICADOR_SYSTEM_PROMPT,
                user_prompt=planner_user_prompt,
                max_tokens=3000,
                temperature=0.1,
                project_id=self._project_id,
            )

            if not planner_response.get("success"):
                detail = planner_response.get('error', 'sin respuesta')
                model = planner_response.get('model_used', 'desconocido')
                attempts = planner_response.get('attempts', '?')
                result.error = f"Error del Planificador (modelo: {model}, intentos: {attempts}): {detail}"
                self._log.append(f"[PLANIFICADOR] ERROR: {result.error}")
                self._report(on_progress, "planificador", f"Error: {detail}")
                # Fase 4: Emitir agent:failed para planificador
                _emit_agent_event("agent:failed", "planner", "",
                                  model=model, extra={"error": detail[:200]})
                self._state = AgentState.FAILED
                return result

            planner_output = planner_response["content"]
            result.raw_planner_output = planner_output
            result.model_used = planner_response.get("model_used", "")
            self._model_used_planner = result.model_used
            self._raw_planner_output = planner_output
            # v3.0: Guardar metadata del planificador
            self._planner_llm_metadata = _extract_llm_metadata(planner_response, "planning")
            result.log = self._log.copy()
            self._log.append(f"[PLANIFICADOR] OK — modelo: {result.model_used}, intentos: {planner_response.get('attempts', '?')}")
            self._report(on_progress, "planificador", f"Planificador respondió (modelo: {result.model_used})")

            if self._cancelled:
                self._state = AgentState.CANCELLED
                result.error = "Cancelado por el usuario"
                return result

            # Parsear output del Planificador en tareas (v3.0: usa V3PlanParser, sin anclas)
            self._log.append(f"[PLANIFICADOR] Parseando output ({len(planner_output)} chars)...")
            self._report(on_progress, "planificador", "Parseando plan...")
            blocks_data = V3PlanParser.parse_blocks(planner_output)
            
            if not blocks_data:
                result.error = "Error de parseo: No se pudo extraer ninguna tarea del output del Planificador."
                self._log.append(f"[PLANIFICADOR] ERROR parseo: sin bloques detectados")
                self._state = AgentState.FAILED
                return result
            
            # Verificar errores de parseo
            parse_errors = []
            for bd in blocks_data:
                for err in bd.get("errores", []):
                    parse_errors.append(err)
            if parse_errors:
                # Si solo faltan anclas, no es error en v3.0
                non_anchor_errors = [e for e in parse_errors if "ANCLA" not in e.upper()]
                if non_anchor_errors:
                    result.error = f"Error de parseo: {'; '.join(non_anchor_errors)}"
                    self._log.append(f"[PLANIFICADOR] ERROR parseo: {result.error}")
                    self._state = AgentState.FAILED
                    return result
            
            # Crear TaskInfo para cada bloque
            for bd in blocks_data:
                task = TaskInfo(
                    task_id=bd.get("tarea_id", f"T{len(self._plan)+1}"),
                    script=bd.get("script", target_file),
                    anchor="",  # v3.0: Ya no se usan anclas
                    planner_output=bd.get("bloque_texto", self._extract_task_block(planner_output, bd.get("tarea_id", ""))),
                    status=TaskStatus.PENDING,
                )
                self._plan.append(task)
                self._log.append(f"[PLANIFICADOR] Tarea planificada: {task.task_id} → {task.script}")
            
            result.tasks = self._plan
            result.success = True
            
            self._state = AgentState.PLANNED
            self._report(on_progress, "planificador", 
                         f"Plan generado: {len(self._plan)} tarea(s)")

            # Fase 4: Emitir agent:done para planificador
            _emit_agent_event("agent:done", "planner", "",
                              model=result.model_used,
                              extra={"pct": 100,
                                     "task_description": f"Plan generado: {len(self._plan)} tarea(s)"})
            
            # v6.0: Checkpoint después de planificación exitosa
            self._save_checkpoint(PipelinePhase.PLANNING.value)
            
            return result

        except Exception as e:
            result.error = f"Error inesperado en planificación: {e}"
            self._log.append(f"EXCEPCIÓN: {e}")
            logger.error(f"SemiAutoAgent.generate_plan error: {e}", exc_info=True)
            self._state = AgentState.FAILED
            return result

    # ─── Fase 2: Ejecución paso a paso ───

    def execute_next(
        self,
        on_progress: Optional[Callable[[str, str], None]] = None,
        on_complete: Optional[Callable[[SemiAutoResult], None]] = None,
    ) -> bool:
        """
        Ejecuta la siguiente tarea pendiente del plan.
        
        La ejecución es asíncrona (en un hilo separado). Cuando termina,
        llama a on_complete con el resultado y cambia el estado a
        AWAITING_APPROVAL.
        
        Args:
            on_progress: Callback de progreso (etapa, mensaje).
            on_complete: Callback cuando la tarea se completa.
        
        Returns:
            True si se inició la ejecución, False si no hay tareas pendientes.
        """
        if self._state not in (AgentState.PLANNED, AgentState.AWAITING_APPROVAL):
            return False
        
        # Encontrar la siguiente tarea pendiente
        next_index = -1
        for i, task in enumerate(self._plan):
            if task.status == TaskStatus.PENDING:
                next_index = i
                break
        
        if next_index < 0:
            # No hay más tareas pendientes
            self._state = AgentState.COMPLETED
            self._log.append("Todas las tareas completadas")
            return False
        
        self._current_task_index = next_index
        self._state = AgentState.EXECUTING
        self._cancelled = False
        
        task = self._plan[next_index]
        task.status = TaskStatus.EXECUTING
        task.attempt += 1
        
        self._log.append(f"Ejecutando {task.task_id} (intento {task.attempt}/{task.max_attempts})")

        # Fase 4: Emitir agent:started para la tarea
        _emit_agent_event("agent:started", "coder", task.task_id,
                          extra={"task_description": f"{task.task_id}: Generando codigo"})
        
        # RF5: Crear snapshot antes de ejecutar
        self._rf5_create_snapshot(task)
        
        # Ejecutar en hilo separado para no bloquear la GUI
        def _run():
            result = self._execute_single_task(task, on_progress)
            
            # v6.0: Detectar contexto excedido (sin fallback)
            is_ctx_exceeded = (
                result.error
                and "[CONTEXT_EXCEEDED]" in (result.error or "")
            )
            
            if self._cancelled:
                self._state = AgentState.CANCELLED
                task.status = TaskStatus.FAILED
                task.error = "Cancelado por el usuario"
                # v6.0: Checkpoint en cancelación durante ejecución
                self._save_checkpoint(PipelinePhase.CANCELLED.value)
            elif is_ctx_exceeded:
                # v6.0: Contexto excedido — pausar pipeline y guardar checkpoint
                self._state = AgentState.FAILED
                task.status = TaskStatus.FAILED
                task.error = result.error
                self._log.append(f"Tarea {task.task_id} PAUSADA — contexto excedido, "
                                f"pipeline puede reanudarse con resume_pipeline()")
                self._save_checkpoint(
                    PipelinePhase.FAILED.value,
                    error=f"Contexto excedido en {task.task_id}: {result.error}"
                )
            elif result.success:
                self._state = AgentState.AWAITING_APPROVAL
                task.status = TaskStatus.AWAITING_APPROVAL
                task.coder_output = result.coder_output
                task.assembled_content = result.assembled_content
                task.validation_result = result.validation_result
                self._log.append(f"Tarea {task.task_id} ejecutada OK — esperando aprobación")
                # v6.0: Checkpoint después de ejecución exitosa
                self._save_checkpoint(PipelinePhase.AWAITING_APPROVAL.value)
            else:
                # Error en la ejecución
                if task.attempt >= task.max_attempts:
                    task.status = TaskStatus.FAILED
                    task.error = result.error
                    self._log.append(f"Tarea {task.task_id} — iteraciones agotadas ({task.attempt} intentos), escala al Director: {result.error}")
                    # No cambiamos a FAILED global — las demás tareas pueden seguir
                    self._state = AgentState.PLANNED
                    # v6.0: Checkpoint — iteración agotada
                    self._save_checkpoint(PipelinePhase.EXECUTING.value, error=result.error)
                else:
                    # Reintento automático si es error de sintaxis
                    val = result.validation_result or {}
                    is_syntax_error = (
                        val.get("returncode", -1) != 0 and
                        "SyntaxError" in str(val.get("output", ""))
                    )
                    if is_syntax_error and task.attempt < task.max_attempts:
                        self._log.append(f"SyntaxError detectado — reintento automático ({task.attempt}/{task.max_attempts})")
                        task.rejection_feedback = f"SyntaxError en el código anterior: {val.get('output', '')[:500]}"
                        # Reintentar automáticamente
                        task.status = TaskStatus.PENDING
                        # v3.1: Programar reintento con Timer (fix bug: root_after_safe no existe)
                        def _retry():
                            try:
                                self.execute_next(on_progress, on_complete)
                            except Exception:
                                pass
                        retry_timer = threading.Timer(1.0, _retry)
                        retry_timer.daemon = True
                        retry_timer.start()
                        return
                    else:
                        task.status = TaskStatus.AWAITING_APPROVAL  # Pausar para intervención humana
                        self._state = AgentState.AWAITING_APPROVAL
                        task.error = result.error
                        task.coder_output = result.coder_output
                        task.assembled_content = result.assembled_content
                        task.validation_result = result.validation_result
                        self._log.append(f"Tarea {task.task_id} con errores — esperando decisión del Director")
                        # v6.0: Checkpoint en tarea con errores
                        self._save_checkpoint(PipelinePhase.EXECUTING.value, error=result.error)
            
            if on_complete:
                on_complete(result)
        
        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        return True

    def approve(self) -> bool:
        """
        Aprueba la tarea actual y guarda los cambios en disco.
        
        Returns:
            True si se aprobó correctamente, False si no hay tarea pendiente.
        """
        if self._state != AgentState.AWAITING_APPROVAL:
            return False
        
        task = self.current_task
        if not task:
            return False
        
        # Guardar el contenido integrado en disco
        if task.script and task.assembled_content and self.project_root:
            file_path = self._resolve_file(task.script)
            if file_path:
                # Crear directorio si no existe
                os.makedirs(os.path.dirname(file_path) if os.path.dirname(file_path) else ".", exist_ok=True)
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(task.assembled_content)
                self._log.append(f"Tarea {task.task_id} APROBADA — guardado en {file_path}")
                # Actualizar contenido original para la siguiente tarea
                self._original_contents[task.script] = task.assembled_content
            else:
                self._log.append(f"Tarea {task.task_id} APROBADA — archivo no encontrado para guardar")
        else:
            self._log.append(f"Tarea {task.task_id} APROBADA")
        
        task.status = TaskStatus.APPROVED
        self._state = AgentState.PLANNED
        
        # RF5: Confirmar snapshot (la refactorización fue aprobada)
        self._rf5_commit_or_rollback(approved=True)
        
        # Verificar si quedan tareas pendientes
        pending = sum(1 for t in self._plan if t.status == TaskStatus.PENDING)
        if pending == 0:
            self._state = AgentState.COMPLETED
            self._log.append("Plan completado — todas las tareas aprobadas")
            # v6.0: Checkpoint final — pipeline completado
            self._save_checkpoint(PipelinePhase.COMPLETED.value)
        else:
            # v6.0: Checkpoint después de aprobación
            self._save_checkpoint(PipelinePhase.EXECUTING.value)
        
        return True

    def reject(self, feedback: str = "") -> bool:
        """
        Rechaza la tarea actual. Si quedan intentos, se reintenta con
        las instrucciones de corrección. Si no, escala al Director.
        
        Args:
            feedback: Instrucciones de corrección del Director.
        
        Returns:
            True si se va a reiterar, False si escala al Director.
        """
        if self._state != AgentState.AWAITING_APPROVAL:
            return False
        
        task = self.current_task
        if not task:
            return False
        
        task.rejection_feedback = feedback
        task.status = TaskStatus.REJECTED
        self._log.append(f"Tarea {task.task_id} RECHAZADA — feedback: {feedback[:100]}")
        
        # RF5: Rollback del snapshot (la refactorización fue rechazada)
        self._rf5_commit_or_rollback(approved=False)
        
        if task.attempt < task.max_attempts:
            # Reintentar — cambiar estado a pendiente
            task.status = TaskStatus.PENDING
            self._state = AgentState.PLANNED
            self._log.append(f"Tarea {task.task_id} — reintento {task.attempt + 1}/{task.max_attempts}")
            # v6.0: Checkpoint en rechazo con reintento
            self._save_checkpoint(PipelinePhase.EXECUTING.value, error=f"Rechazada: {feedback[:100]}")
            return True
        else:
            # Iteraciones agotadas — escala al Director
            task.status = TaskStatus.FAILED
            self._state = AgentState.PLANNED
            self._log.append(f"Tarea {task.task_id} — iteraciones agotadas, escala al Director")
            # Verificar si quedan tareas pendientes
            pending = sum(1 for t in self._plan if t.status == TaskStatus.PENDING)
            if pending == 0:
                self._state = AgentState.COMPLETED
            # v6.0: Checkpoint — escala al Director por rechazo
            self._save_checkpoint(PipelinePhase.EXECUTING.value, error=f"Rechazada (máx intentos): {feedback[:100]}")
            return False

    def skip_task(self) -> bool:
        """
        Salta la tarea actual sin aprobarla ni guardarla.
        
        Returns:
            True si se saltó correctamente.
        """
        if self._state != AgentState.AWAITING_APPROVAL:
            return False
        
        task = self.current_task
        if not task:
            return False
        
        task.status = TaskStatus.SKIPPED
        self._state = AgentState.PLANNED
        self._log.append(f"Tarea {task.task_id} SALTADA")
        
        pending = sum(1 for t in self._plan if t.status == TaskStatus.PENDING)
        if pending == 0:
            self._state = AgentState.COMPLETED
        
        return True

    # ─── Ejecución de tarea única (interna) ───

    def _execute_single_task(
        self,
        task: TaskInfo,
        on_progress: Optional[Callable[[str, str], None]] = None,
    ) -> SemiAutoResult:
        """Ejecuta una tarea individual: Codificador → Integrador → Validación.
        
        v3.0: Reemplaza el Ensamblador mecánico por el Integrador (LLM).
        El Integrador recibe el archivo original, la especificación y el código
        del Codificador, y produce el archivo final integrado.
        """
        result = SemiAutoResult()
        result.task_id = task.task_id
        result.script_name = task.script
        
        try:
            # v3.2 (P3): Intentar re-escalar antes de codificar
            try:
                coder_sys = CODIFICADOR_SYSTEM_PROMPT
                restored = try_re_escalate(task_size=estimate_task_size(coder_sys, task.planner_output, 4000))
                if restored:
                    self._log.append(
                        f"[ESCALADO] Re-escalado dinámico a {restored.get('model_id', '?')} "
                        f"antes de codificación {task.task_id}"
                    )
            except Exception as e:
                logger.debug(f"try_re_escalate() antes de codificación: {e}")

            # ─── ETAPA 2: Llamar al Codificador ───
            self._report(on_progress, "codificador", 
                         f"Consultando Codificador para {task.task_id}...")
            self._log.append(f"[CODIFICADOR] {task.task_id} — Enviando consulta al LLM...")

            # Fase 4: Emitir agent:started para coder (detalle)
            _emit_agent_event("agent:started", "coder", task.task_id,
                              extra={"task_description": f"{task.task_id}: Generando codigo ({task.script})"})

            # Obtener contenido actual del archivo
            original_content = self._original_contents.get(task.script, "")
            if not original_content and task.script and self.project_root:
                file_path = self._resolve_file(task.script)
                if file_path and os.path.exists(file_path):
                    with open(file_path, 'r', encoding='utf-8') as f:
                        original_content = f.read()
            
            # Construir prompt del Codificador
            coder_user_prompt = self._build_coder_prompt(
                task.planner_output, original_content,
                correction_feedback=task.rejection_feedback if task.attempt > 1 else ""
            )

            coder_response = call_llm(
                task_type="generation",
                system_prompt=CODIFICADOR_SYSTEM_PROMPT,
                user_prompt=coder_user_prompt,
                max_tokens=4000,
                temperature=0.1,
                project_id=self._project_id,
            )

            if not coder_response.get("success"):
                result.error = f"Error del Codificador (modelo: {coder_response.get('model_used','?')}, intentos: {coder_response.get('attempts','?')}): {coder_response.get('error', 'sin respuesta')}"
                # v6.0: Detectar contexto excedido sin fallback
                if self._is_context_exceeded_response(coder_response):
                    result.error = f"[CONTEXT_EXCEEDED] {result.error}"
                    self._log.append(f"[CODIFICADOR] ERROR: Contexto excedido — sin modelo con contexto suficiente")
                else:
                    self._log.append(f"[CODIFICADOR] ERROR: {result.error}")
                self._report(on_progress, "codificador", f"Error: {coder_response.get('error', 'sin respuesta')}")
                # Fase 4: Emitir agent:failed
                _emit_agent_event("agent:failed", "coder", task.task_id,
                                  model=coder_response.get('model_used', ''),
                                  extra={"error": result.error[:200]})
                return result

            coder_output = coder_response["content"]
            result.coder_output = coder_output
            result.model_used_coder = coder_response.get("model_used", "")
            # Métricas del codificador
            result.coding_provider = coder_response.get("provider", "")
            result.coding_tokens_input = coder_response.get("tokens_input", 0)
            result.coding_tokens_output = coder_response.get("tokens_output", 0)
            result.coding_latency_ms = coder_response.get("latency_ms", 0)
            result.coding_cost_usd = coder_response.get("cost_usd", 0.0)
            result.coding_arena_score = coder_response.get("arena_score")
            self._log.append(f"[CODIFICADOR] OK — modelo: {result.model_used_coder}, intentos: {coder_response.get('attempts', '?')}")
            self._report(on_progress, "codificador", f"Código generado (modelo: {result.model_used_coder})")

            # Fase 4: Emitir agent:done + agent:progress para coder
            tokens_used = (result.coding_tokens_input + result.coding_tokens_output)
            ctx_max_coder = getattr(result, 'coding_context_max', 0) or 8000
            ctx_pct_coder = round(min(100, result.coding_tokens_input / ctx_max_coder * 100))
            _emit_agent_event("agent:done", "coder", task.task_id,
                              model=result.model_used_coder,
                              extra={"tokens_used": tokens_used,
                                     "latency_ms": result.coding_latency_ms,
                                     "task_description": f"{task.task_id}: Codigo generado",
                                     "context_used": result.coding_tokens_input,
                                     "context_max": ctx_max_coder})
            _emit_agent_event("agent:progress", "coder", task.task_id,
                              model=result.model_used_coder,
                              extra={"tokens_used": tokens_used, "pct": 40,
                                     "context_pct": ctx_pct_coder})

            if self._cancelled:
                result.error = "Cancelado por el usuario"
                return result

            # ─── ETAPA 3: Integrar (v3.0: reemplaza al Ensamblador mecánico) ───
            self._report(on_progress, "integrador", 
                         f"Integrando {task.task_id}...")
            self._log.append(f"[INTEGRADOR] {task.task_id} — Integrando código en {task.script}...")

            # Fase 4: Emitir agent:started para integrador
            _emit_agent_event("agent:started", "integrator", task.task_id,
                              extra={"task_description": f"{task.task_id}: Integrando en {task.script}"})

            # v3.2 (P3): Intentar re-escalar antes de integrar
            # (aunque la integración suele necesitar mucho contexto,
            # si el mejor modelo tiene suficiente, usarlo)
            try:
                integ_sys = _get_integrador_prompts()["system"]
                coder_code = self._extract_python_code(coder_output)
                restored = try_re_escalate(task_size=estimate_task_size(integ_sys, task.planner_output + coder_code, 8000))
                if restored:
                    self._log.append(
                        f"[ESCALADO] Re-escalado dinámico a {restored.get('model_id', '?')} "
                        f"antes de integración {task.task_id}"
                    )
            except Exception as e:
                logger.debug(f"try_re_escalate() antes de integración: {e}")

            integrator_prompts = _get_integrador_prompts()

            # v3.2 (P2): Usar contexto mínimo — firmas + sección objetivo
            # en lugar del archivo completo. Esto reduce el consumo de
            # contexto del integrador en ~70%.
            coder_code = self._extract_python_code(coder_output)
            if original_content and len(original_content) > 2000:
                # Extraer el nombre de la función/clase objetivo del parser
                target_name = ""
                parsed_spec = V3PlanParser.parse_single(task.planner_output)
                # Buscar nombre en la especificación
                for line in task.planner_output.split("\n"):
                    match = re.search(r'(?:def|class)\s+(\w+)', line)
                    if match:
                        target_name = match.group(1)
                        break

                # Construir contexto mínimo
                integrator_context = build_integrator_context(
                    original_content,
                    target_name=target_name,
                    surrounding_lines=15,
                )
                tokens_orig = count_tokens_estimate(original_content)
                tokens_min = count_tokens_estimate(integrator_context)
                self._log.append(
                    f"[INTEGRADOR] {task.task_id} — Contexto mínimo: "
                    f"~{tokens_orig} tokens → ~{tokens_min} tokens "
                    f"({100 - int(tokens_min / tokens_orig * 100) if tokens_orig > 0 else 0}% reducción)"
                )
            else:
                # Archivo pequeño o nuevo — enviar completo
                integrator_context = original_content if original_content else "# (archivo nuevo)"

            integrator_user_prompt = integrator_prompts["user_template"].format(
                script_name=task.script,
                original_content=integrator_context,
                planner_specification=task.planner_output,
                coder_code=coder_code,
            )

            # Si es un reintento, añadir contexto de corrección
            integrator_system = integrator_prompts["system"]
            if task.attempt > 1 and task.rejection_feedback:
                integrator_system += integrator_prompts["correction_addendum"].format(
                    feedback=task.rejection_feedback
                )

            integrator_response = call_llm(
                task_type="integration",
                system_prompt=integrator_system,
                user_prompt=integrator_user_prompt,
                max_tokens=8000,  # El integrador devuelve el archivo completo
                temperature=0.1,
                project_id=self._project_id,
            )

            if not integrator_response.get("success"):
                result.error = f"Error del Integrador (modelo: {integrator_response.get('model_used','?')}): {integrator_response.get('error', 'sin respuesta')}"
                # v6.0: Detectar contexto excedido sin fallback
                if self._is_context_exceeded_response(integrator_response):
                    result.error = f"[CONTEXT_EXCEEDED] {result.error}"
                    self._log.append(f"[INTEGRADOR] ERROR: Contexto excedido — sin modelo con contexto suficiente")
                else:
                    self._log.append(f"[INTEGRADOR] ERROR: {result.error}")
                self._report(on_progress, "integrador", f"Error: {integrator_response.get('error', 'sin respuesta')}")
                # Fase 4: Emitir agent:failed
                _emit_agent_event("agent:failed", "integrator", task.task_id,
                                  model=integrator_response.get('model_used', ''),
                                  extra={"error": result.error[:200]})
                return result

            integrated_content = self._extract_python_code(integrator_response["content"])
            result.assembled_content = integrated_content
            result.model_used_integrator = integrator_response.get("model_used", "")
            # Métricas del integrador
            result.integration_provider = integrator_response.get("provider", "")
            result.integration_tokens_input = integrator_response.get("tokens_input", 0)
            result.integration_tokens_output = integrator_response.get("tokens_output", 0)
            result.integration_latency_ms = integrator_response.get("latency_ms", 0)
            result.integration_cost_usd = integrator_response.get("cost_usd", 0.0)
            result.integration_arena_score = integrator_response.get("arena_score")

            self._log.append(f"[INTEGRADOR] OK — modelo: {result.model_used_integrator}")
            self._report(on_progress, "integrador", f"Código integrado (modelo: {result.model_used_integrator})")

            # Fase 4: Emitir agent:done + agent:progress para integrador
            tokens_used_int = (result.integration_tokens_input + result.integration_tokens_output)
            ctx_max_int = getattr(result, 'integration_context_max', 0) or 16000
            ctx_pct_int = round(min(100, result.integration_tokens_input / ctx_max_int * 100))
            _emit_agent_event("agent:done", "integrator", task.task_id,
                              model=result.model_used_integrator,
                              extra={"tokens_used": tokens_used_int,
                                     "latency_ms": result.integration_latency_ms,
                                     "task_description": f"{task.task_id}: Codigo integrado",
                                     "context_pct": ctx_pct_int})
            _emit_agent_event("agent:progress", "integrator", task.task_id,
                              model=result.model_used_integrator,
                              extra={"tokens_used": tokens_used_int, "pct": 75,
                                     "context_pct": ctx_pct_int})

            # RF4: Revisar diff contra el grafo de dependencias
            rf4_issues = []
            rf4_should_block = False
            if original_content and integrated_content:
                rf4_issues, rf4_should_block = self._rf4_review_diff(task, original_content, integrated_content)

            # v3.4: Si RF4 dice bloquear (CRITICAL/BREAKING), no aplicar cambios
            if rf4_should_block:
                self._log.append(
                    f"[RF4] Cambios BLOQUEADOS — {len(rf4_issues)} issue(s) crítico(s) en {task.script}"
                )
                # No escribir el archivo integrado — mantener el original
                # El Director verá los issues en validation_result
                result.assembled_content = original_content
                result.error = "RF4: Cambios bloqueados por issues críticos — requiere revisión"
                result.success = False
                return result

            # RF5 v3.3: Validar regresión después de integrar
            # Escribe temporalmente a disco, ejecuta 5 capas (sintaxis,
            # imports, caller imports, símbolos, firmas, tests, smoke).
            # Si detecta regresión → rollback + iteración.
            if integrated_content and task.script and self.project_root:
                file_path = self._resolve_file(task.script)
                if file_path:
                    rf5_ok = self._rf5_validate_after_integration(
                        task, integrated_content, file_path
                    )
                    if not rf5_ok:
                        # Regresión detectada — rollback ya ejecutado
                        # Leer contenido restaurado después del rollback
                        if os.path.exists(file_path):
                            try:
                                with open(file_path, 'r', encoding='utf-8') as f:
                                    restored_content = f.read()
                                result.assembled_content = restored_content
                            except IOError:
                                pass
                        result.error = "Regresión detectada por RF5 — iterando con rollback"
                        result.success = False
                        self._log.append(f"[RF5] Tarea {task.task_id} — iteración: regresión detectada, rollback ejecutado")
                        return result

            # v3.1/v3.2: RE-ESCALADO — si el integrador usó un modelo de-escalado
            # (porque la tarea era grande), volver al modelo superior para
            # la siguiente tarea de planificación que necesite el mejor modelo.
            # v3.2: También intenta re-escalar dinámicamente si un mejor modelo
            # está disponible ahora (salió de rate limit, fue verificado, etc.)
            try:
                # Primero: re-escalado estándar (desapilar)
                restored = re_escalate()
                if restored:
                    self._log.append(
                        f"[ESCALADO] Re-escalado a {restored.get('model_id', '?')} "
                        f"tras ensamblado con {result.model_used_integrator}"
                    )
                # Segundo: re-escalado dinámico si hay uno aún mejor disponible
                restored_dyn = try_re_escalate()
                if restored_dyn:
                    self._log.append(
                        f"[ESCALADO] Re-escalado dinámico a "
                        f"{restored_dyn.get('model_id', '?')} — mejor modelo disponible"
                    )
            except Exception as e:
                logger.debug(f"re_escalate() después de integración: {e}")

            # ─── ETAPA 4: Validar ───
            self._report(on_progress, "validador", "Validando código integrado...")
            self._log.append(f"[VALIDADOR] {task.task_id} — Validando...")

            # Fase 4: Emitir agent:started para validador
            _emit_agent_event("agent:started", "validator", task.task_id,
                              extra={"task_description": f"{task.task_id}: Validando codigo"})

            validation_result = AssemblyValidator.validate(
                content=integrated_content,
                script_path=task.script,
                validation_mode="auto",
            )
            # v3.3: Merge RF4/RF5 results into validation_result
            # (RF4/RF5 ya escribieron en task.validation_result,
            #  pero result.validation_result es un dict separado)
            result.validation_result = validation_result
            # Añadir datos RF4/RF5 que ya están en task.validation_result
            for rf_key in ("rf4_issues", "rf4_has_critical", "rf5_report"):
                if rf_key in task.validation_result:
                    result.validation_result[rf_key] = task.validation_result[rf_key]

            val_rc = validation_result.get("returncode", -1)
            if val_rc == 0:
                self._log.append(f"[VALIDADOR] Validación OK")
                result.success = True
                # Fase 4: Emitir agent:done para validador
                _emit_agent_event("agent:done", "validator", task.task_id,
                                  extra={"pct": 100,
                                         "task_description": f"{task.task_id}: Validacion OK"})
            else:
                val_out = validation_result.get("output", "")[:300]
                self._log.append(f"[VALIDADOR] Iteración necesaria — validación no superada: {val_out}")
                # v3.0: Si la validación no pasa, marcamos como no exitoso
                # pero aún entregamos el contenido para que el Director decida
                result.success = False
                result.error = f"Validación no superada — itera o escala al Director: {val_out}"
                # Fase 4: Emitir agent:failed para validador
                _emit_agent_event("agent:failed", "validator", task.task_id,
                                  extra={"error": val_out[:200], "pct": 90,
                                         "task_description": f"{task.task_id}: Validacion fallida"})

            result.planner_output = task.planner_output
            self._report(
                on_progress,
                "integrador",
                "Integración completada" if result.success else "Integración con errores de validación"
            )

            return result

        except Exception as e:
            result.error = f"Error inesperado: {e}"
            self._log.append(f"EXCEPCIÓN: {e}")
            logger.error(f"SemiAutoAgent._execute_single_task error: {e}", exc_info=True)
            return result

    # ─── Compatibilidad: run() para tarea única ───

    def run(
        self,
        user_prompt: str,
        target_file: str = "",
        original_content: str = "",
        on_progress: Optional[Callable[[str, str], None]] = None,
    ) -> SemiAutoResult:
        """
        Ejecuta el pipeline semi-autónomo completo (tarea única).
        
        Método de compatibilidad que combina generate_plan() + execute_next()
        en una sola llamada. Para multi-tarea, usar generate_plan() + execute_next().
        """
        self._cancelled = False
        result = SemiAutoResult()
        result.log.append(f"Inicio: {user_prompt[:80]}")

        try:
            # v3.2 (P3): Intentar re-escalar antes de planificar (run)
            try:
                restored = try_re_escalate(task_size=estimate_task_size(PLANIFICADOR_SYSTEM_PROMPT, "", 3000))
                if restored:
                    result.log.append(
                        f"[ESCALADO] Re-escalado dinámico a {restored.get('model_id', '?')}"
                    )
            except Exception:
                pass

            # ─── ETAPA 1: Llamar al Planificador ───
            self._report(on_progress, "planificador", "Consultando Planificador...")
            
            # Fase 4: Emitir agent:started para planificador
            _emit_agent_event("agent:started", "planner", "",
                              extra={"task_description": "Generando plan de tareas..."})

            planner_user_prompt = self._build_planner_prompt(
                user_prompt, target_file, original_content
            )

            planner_response = call_llm(
                task_type="planning",
                system_prompt=PLANIFICADOR_SYSTEM_PROMPT,
                user_prompt=planner_user_prompt,
                max_tokens=3000,
                temperature=0.1,
                project_id=self._project_id,
            )

            if not planner_response.get("success"):
                result.error = f"Error del Planificador: {planner_response.get('error', 'sin respuesta')}"
                result.log.append(f"ERROR Planificador: {result.error}")
                return result

            planner_output = planner_response["content"]
            result.planner_output = planner_output
            result.model_used_planner = planner_response.get("model_used", "")
            # Métricas del planificador
            result.planning_provider = planner_response.get("provider", "")
            result.planning_tokens_input = planner_response.get("tokens_input", 0)
            result.planning_tokens_output = planner_response.get("tokens_output", 0)
            result.planning_latency_ms = planner_response.get("latency_ms", 0)
            result.planning_cost_usd = planner_response.get("cost_usd", 0.0)
            result.planning_arena_score = planner_response.get("arena_score")
            # Guardar metadata del planificador
            planner_llm_metadata = _extract_llm_metadata(planner_response, "planning")
            result.log.append(f"Planificador OK (modelo: {result.model_used_planner})")

            if self._cancelled:
                result.error = "Cancelado por el usuario"
                return result

            # ─── ETAPA 1.5: Parsear output del Planificador (v3.0: sin anclas) ───
            parsed = V3PlanParser.parse_single(planner_output)
            non_anchor_errors = [e for e in parsed.get("errores", []) if "ANCLA" not in e.upper()]
            if non_anchor_errors:
                result.error = f"Error de parseo del Planificador: {'; '.join(non_anchor_errors)}"
                result.log.append(f"ERROR parseo: {result.error}")
                return result

            result.script_name = parsed.get("script", target_file)
            result.task_id = parsed.get("tarea_id", "T1")

            # Resolver archivo si no se proporcionó target_file
            if not target_file:
                target_file = result.script_name

            # Obtener contenido original si no se proporcionó
            if not original_content and self.project_root and target_file:
                file_path = self._resolve_file(target_file)
                if file_path and os.path.exists(file_path):
                    with open(file_path, 'r', encoding='utf-8') as f:
                        original_content = f.read()
                    result.log.append(f"Contenido original cargado: {len(original_content)} chars")

            self._report(on_progress, "planificador", f"Plan generado: {target_file} | {result.task_id}")

            # ─── ETAPA 2: Llamar al Codificador ───
            self._report(on_progress, "codificador", "Consultando Codificador...")

            coder_user_prompt = self._build_coder_prompt(planner_output, original_content)

            coder_response = call_llm(
                task_type="generation",
                system_prompt=CODIFICADOR_SYSTEM_PROMPT,
                user_prompt=coder_user_prompt,
                max_tokens=4000,
                temperature=0.1,
                project_id=self._project_id,
            )

            if not coder_response.get("success"):
                result.error = f"Error del Codificador (modelo: {coder_response.get('model_used','?')}, intentos: {coder_response.get('attempts','?')}): {coder_response.get('error', 'sin respuesta')}"
                result.log.append(f"ERROR Codificador: {result.error}")
                return result

            coder_output = coder_response["content"]
            result.coder_output = coder_output
            result.model_used_coder = coder_response.get("model_used", "")
            # Métricas del codificador
            result.coding_provider = coder_response.get("provider", "")
            result.coding_tokens_input = coder_response.get("tokens_input", 0)
            result.coding_tokens_output = coder_response.get("tokens_output", 0)
            result.coding_latency_ms = coder_response.get("latency_ms", 0)
            result.coding_cost_usd = coder_response.get("cost_usd", 0.0)
            result.coding_arena_score = coder_response.get("arena_score")
            result.log.append(f"Codificador OK (modelo: {result.model_used_coder})")

            if self._cancelled:
                result.error = "Cancelado por el usuario"
                return result

            # ─── ETAPA 3: Integrar (v3.0) ───
            self._report(on_progress, "integrador", "Integrando código...")

            integrator_prompts = _get_integrador_prompts()
            integrator_user_prompt = integrator_prompts["user_template"].format(
                script_name=target_file,
                original_content=original_content if original_content else "# (archivo nuevo)",
                planner_specification=planner_output,
                coder_code=self._extract_python_code(coder_output),
            )

            integrator_response = call_llm(
                task_type="integration",
                system_prompt=integrator_prompts["system"],
                user_prompt=integrator_user_prompt,
                max_tokens=8000,
                temperature=0.1,
                project_id=self._project_id,
            )

            if not integrator_response.get("success"):
                result.error = f"Error del Integrador: {integrator_response.get('error', 'sin respuesta')}"
                result.log.append(f"ERROR Integrador: {result.error}")
                return result

            integrated_content = self._extract_python_code(integrator_response["content"])
            result.assembled_content = integrated_content
            result.model_used_integrator = integrator_response.get("model_used", "")
            # Métricas del integrador
            result.integration_provider = integrator_response.get("provider", "")
            result.integration_tokens_input = integrator_response.get("tokens_input", 0)
            result.integration_tokens_output = integrator_response.get("tokens_output", 0)
            result.integration_latency_ms = integrator_response.get("latency_ms", 0)
            result.integration_cost_usd = integrator_response.get("cost_usd", 0.0)
            result.integration_arena_score = integrator_response.get("arena_score")
            result.log.append(f"Integrador OK (modelo: {result.model_used_integrator})")

            # ─── ETAPA 4: Validar ───
            self._report(on_progress, "validador", "Validando...")

            validation_result = AssemblyValidator.validate(
                content=integrated_content,
                script_path=target_file,
                validation_mode="auto",
            )
            result.validation_result = validation_result
            result.success = validation_result.get("returncode", -1) == 0

            result.log.append(f"Validación: {'OK' if result.success else 'CON ERRORES'}")

            return result

        except Exception as e:
            result.error = f"Error inesperado: {e}"
            result.log.append(f"EXCEPCIÓN: {e}")
            logger.error(f"SemiAutoAgent.run error: {e}", exc_info=True)
            return result

    # ─── Helpers ───

    def _build_planner_prompt(
        self,
        user_instruction: str,
        target_file: str,
        existing_content: str,
    ) -> str:
        """Construye el prompt de usuario para el Planificador.
        
        v3.0: Aumenta max_content a 8000 para que el Planificador tenga
        más contexto del archivo y pueda generar especificaciones más precisas.
        RF2 v2.2: Cuando el grafo de dependencias está disponible, usa
        contexto selectivo (símbolos priorizados por riesgo) en vez de
        truncación ciega. El grafo decide qué es importante; el fallback
        es truncación simple cuando no hay grafo.
        """
        prompt_parts = [f"INSTRUCCIÓN DEL DIRECTOR:\n{user_instruction}"]

        if target_file:
            prompt_parts.append(f"\nSCRIPT OBJETIVO: {target_file}")

        # RF2: Contexto inteligente de dependencias + fuente selectiva
        rf2_used_graph_source = False
        try:
            guard = self._get_or_create_guard()
            if guard:
                # Inyectar contexto de dependencias (quién llama a quién, riesgo)
                rf_context = guard.get_refactor_context_for_prompt(target_file)
                if rf_context:
                    prompt_parts.append(f"\n{rf_context}")
                    self._log.append("[RF2] Contexto de dependencias inyectado en prompt del Planificador")
                
                # Usar fuente selectiva basada en grafo (reemplaza truncación ciega)
                if existing_content and hasattr(guard, 'get_refactor_focused_source'):
                    focused_source = guard.get_refactor_focused_source(
                        target_file, existing_content, max_chars=8000
                    )
                    if focused_source != existing_content[:8000] + "\n# ... (truncado)":
                        # El grafo proporcionó contexto selectivo
                        prompt_parts.append(
                            f"\nCONTENIDO DEL ARCHIVO (contexto selectivo por riesgo):\n```python\n{focused_source}\n```"
                        )
                        rf2_used_graph_source = True
                        self._log.append("[RF2] Fuente selectiva (grafo) reemplazó truncación ciega")
        except Exception as e:
            logger.debug(f"RF2: error obteniendo contexto de dependencias: {e}")

        # Fallback: si RF2 no proporcionó fuente selectiva, truncar normalmente
        if existing_content and not rf2_used_graph_source:
            max_content = 8000
            content_to_include = existing_content
            if len(content_to_include) > max_content:
                content_to_include = content_to_include[:max_content] + "\n# ... (truncado)"
            prompt_parts.append(f"\nCONTENIDO ACTUAL DEL ARCHIVO:\n```python\n{content_to_include}\n```")

        # Si es un archivo nuevo, indicarlo
        if not existing_content and target_file:
            prompt_parts.append("\nNOTA: Este es un ARCHIVO NUEVO.")

        return "\n".join(prompt_parts)

    def _build_coder_prompt(
        self,
        planner_output: str,
        existing_content: str,
        correction_feedback: str = "",
    ) -> str:
        """Construye el prompt de usuario para el Codificador.
        
        v3.0: Aumenta max_content a 6000 para que el Codificador tenga
        más contexto del archivo existente.
        """
        prompt_parts = [planner_output]

        if existing_content:
            # v3.0: Aumentar límite de 3000 a 6000
            max_content = 6000
            content_to_include = existing_content
            if len(content_to_include) > max_content:
                content_to_include = content_to_include[:max_content] + "\n# ... (truncado)"
            prompt_parts.append(
                f"\nCONTEXTO — Código existente en el archivo:\n```python\n{content_to_include}\n```"
            )

        # Añadir contexto de corrección si es un reintento
        if correction_feedback:
            prompt_parts.append(
                f"\nOBSERVACIONES DEL DIRECTOR (versión anterior rechazada):\n{correction_feedback}"
            )
            prompt_parts.append(
                "\nCorrige el código para abordar estas observaciones. No repitas los mismos errores."
            )

        return "\n".join(prompt_parts)

    def _extract_python_code(self, llm_output: str) -> str:
        """Extrae el código Python de la respuesta del LLM.
        
        El Codificador y el Integrador devuelven código envuelto en
        ```python ... ```. Este método extrae solo el código.
        """
        # Intentar extraer bloque ```python ... ```
        pattern = r'```python\s*\n(.*?)```'
        match = re.search(pattern, llm_output, re.DOTALL)
        if match:
            return match.group(1).strip()
        
        # Intentar bloque genérico ``` ... ```
        pattern = r'```\s*\n(.*?)```'
        match = re.search(pattern, llm_output, re.DOTALL)
        if match:
            return match.group(1).strip()
        
        # Si no hay bloques, devolver tal cual
        return llm_output.strip()

    def _extract_task_block(self, planner_output: str, task_id: str) -> str:
        """Extrae el bloque del Planificador correspondiente a una tarea específica."""
        if not task_id:
            return planner_output
        
        # Buscar el bloque que contiene la tarea_id
        blocks = planner_output.split("---")
        for block in blocks:
            if task_id in block:
                return block.strip()
        
        # Si no se encuentra por task_id, devolver todo
        return planner_output

    def _resolve_file(self, script_name: str) -> Optional[str]:
        """Resuelve la ruta de un archivo relativo al proyecto."""
        if not self.project_root:
            return None

        # Buscar archivo en el proyecto
        root = self.project_root
        candidates = [
            os.path.join(root, script_name),
            os.path.join(root, "apa", script_name),
        ]

        for candidate in candidates:
            if os.path.exists(candidate):
                return candidate

        # Búsqueda recursiva
        for dirpath, dirnames, filenames in os.walk(root):
            # Ignorar dirs ocultos y __pycache__
            dirnames[:] = [d for d in dirnames if not d.startswith('.') and d != '__pycache__']
            basename = os.path.basename(script_name)
            if basename in filenames:
                return os.path.join(dirpath, basename)

        # Si no se encuentra, crear la ruta (para ARCHIVO_NUEVO)
        candidate = os.path.join(root, script_name)
        return candidate

    def _report(
        self,
        callback: Optional[Callable[[str, str], None]],
        stage: str,
        message: str,
    ):
        """Reporta progreso al callback."""
        if callback:
            try:
                callback(stage, message)
            except Exception:
                pass

    def root_after_safe(self, ms, fn):
        """Stub para root.after() — la GUI debe sobreescribir esto."""
        # En modo consola, ejecutar directamente
        try:
            fn()
        except Exception:
            pass
