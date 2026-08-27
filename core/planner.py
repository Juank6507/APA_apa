# apa/core/planner.py
# -*- coding: utf-8 -*-
"""Planner — Generación y gestión de planes de tareas."""
import json
import logging
import re
import sys as _sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Path setup: asegurar que `core` sea importable cuando planner.py se
# ejecuta como script (python core/planner.py) además de como módulo.
_THIS_DIR_PLANNER = Path(__file__).resolve()
_APAPA_ROOT_PLANNER = _THIS_DIR_PLANNER.parent.parent  # apa/
if str(_APAPA_ROOT_PLANNER) not in _sys.path:
    _sys.path.insert(0, str(_APAPA_ROOT_PLANNER))


logger = logging.getLogger("apa.planner")

# TDM (Tech Domain Map) — Decisión 3 (Opción A) del Director:
# inyectar la base de conocimiento tecnológica en el prompt base del
# planificador para que cada tarea generada tenga el campo
# `programming_language` correcto según el dominio del proyecto.
try:
    from core.tech_domain_map import get_domain_knowledge_prompt as _tdm_knowledge
except Exception:  # pragma: no cover — fallback defensivo
    logging.getLogger("apa.planner").warning(
        "planner: tech_domain_map no disponible", exc_info=True
    )
    def _tdm_knowledge() -> str:  # type: ignore[no-redef]
        return ""

# ─── Constantes ───────────────────────────────────────────────────────────

# Campos obligatorios de cada tarea generada
TASK_REQUIRED_FIELDS = [
    "id", "name", "description", "dependencies", "inputs",
    "output", "acceptance_criteria", "task_type",
    "programming_language", "executor", "priority",
]

# Valores válidos para executor
VALID_EXECUTORS = ("apa", "user", "system")

# Valores válidos para priority
VALID_PRIORITIES = ("critical", "high", "medium", "low")

# Tipos de tarea válidos
VALID_TASK_TYPES = (
    "code_generation", "analysis", "testing", "configuration",
    "documentation", "deployment", "integration", "research",
    "review", "setup", "design",
)

# Patrones de parsing para Markdown
_SECTION_PATTERN = re.compile(r"^(#{2,3})\s+(.+)$", re.MULTILINE)
_H1_PATTERN = re.compile(r"^#\s+(.+)$", re.MULTILINE)
_YAML_PATTERN = re.compile(r"^---\s*\n", re.MULTILINE)

# Mapeo tipo de tarea -> ejecutor predeterminado
_EXECUTOR_MAP: Dict[str, str] = {
    "code_generation": "apa",
    "analysis": "apa",
    "testing": "apa",
    "configuration": "apa",
    "documentation": "apa",
    "deployment": "system",
    "integration": "apa",
    "research": "user",
    "review": "user",
    "setup": "system",
    "design": "user",
}

# Mapeo tipo de tarea -> prioridad base
_PRIORITY_MAP: Dict[str, str] = {
    "code_generation": "high",
    "analysis": "medium",
    "testing": "medium",
    "configuration": "high",
    "documentation": "low",
    "deployment": "critical",
    "integration": "high",
    "research": "low",
    "review": "medium",
    "setup": "critical",
    "design": "medium",
}

# Palabras clave que indican que una tarea requiere acción humana
_KEYWORDS_USER = [
    "decidir", "aprobar", "seleccionar", "elegir", "definir negocio",
    "requisito", "validar con cliente", "feedback", "revisión manual",
    "manual", "humano", "decision", "estético", "marca", "branding",
    "experiencia de usuario", "ux", "diseño visual", "wireframe", "prototipo",
    "color", "tipografía", "layout", "opinión del usuario",
]

# Palabras clave que indican que una tarea es del sistema
_KEYWORDS_SYSTEM = [
    "instalar", "desplegar", "deploy", "configurar entorno", "provisionar",
    "crear base de datos", "crear servidor", "certificado ssl", "dns",
    "dominio", "infraestructura", "servidor", "cloud", "pipeline",
    "ci/cd", "docker", "kubernetes", "terraform", "ansible",
]

# Prompt base para el LLM con instrucción de executor y priority
_BASE_PLANNING_PROMPT = """Eres un planificador experto de proyectos de software.
Tu trabajo es convertir especificaciones técnicas en tareas atómicas y ejecutables.

CRÍTICO: Cada tarea DEBE incluir estos campos exactos:
- "id": identificador único (T001, T002, ...)
- "name": nombre corto de la tarea
- "description": descripción detallada de qué hacer
- "dependencies": lista de IDs de tareas que deben completarse antes
- "inputs": lista de artefactos o datos de entrada necesarios
- "output": descripción del resultado esperado
- "acceptance_criteria": criterios que definen la tarea como completada
- "task_type": uno de: code_generation, analysis, testing, configuration, documentation, deployment, integration, research, review, setup, design
- "programming_language": lenguaje de programación principal
- "executor": uno de: "apa" (el sistema lo ejecuta automáticamente), "user" (requiere acción humana), "system" (automatizado sin agente)
- "priority": uno de: "critical", "high", "medium", "low"

REGLAS PARA ASIGNAR executor:
- "apa": tareas de código, análisis, tests, configuración técnica -> el sistema las ejecuta
- "user": tareas que requieren decisión humana, aprobación, feedback, diseño visual
- "system": tareas de infraestructura (despliegue, DNS, certificados, servidores)

REGLAS PARA ASIGNAR priority:
- "critical": bloquea todo el proyecto si falla (setup, despliegue, core)
- "high": necesario para funcionalidad principal
- "medium": importante pero no bloqueante
- "low": nice-to-have, documentación adicional, refactorización

Responde ÚNICAMENTE con JSON válido dentro de un bloque ```json ... ```.
El JSON debe tener la forma: {"tasks": [...lista de tareas...]}
"""

# Decisión 3 (Opción A) del Director — TDM (Tech Domain Map):
# concatenar la base de conocimiento tecnológica al prompt base del
# planificador para que cada tarea generada lleve un campo
# `programming_language` acorde al dominio del proyecto.
try:
    _TDM_KNOWLEDGE_BLOCK = _tdm_knowledge()
    if _TDM_KNOWLEDGE_BLOCK:
        _BASE_PLANNING_PROMPT += (
            "\n\n--- BASE DE CONOCIMIENTO TECNOLOGICO (TDM) ---\n"
            + _TDM_KNOWLEDGE_BLOCK
        )
except Exception:  # pragma: no cover
    pass

_MULTI_FILE_PROMPT_EXTENSION = """

Este es un proyecto MULTI-ARCHIVO. Cada tarea debe indicar claramente
en su campo "output" qué archivo(s) crea o modifica.
Agrupa tareas por archivo/módulo cuando sea posible.
Las primeras tareas deben ser siempre de tipo "setup" o "configuration".
"""

_REPLAN_PROMPT = """Eres un planificador experto. Una tarea falló y necesita
ser reprogramada. Analiza el error y la ejecución anterior para generar
una versión corregida de la tarea.

CAMPOS OBLIGATORIOS (iguales que el plan original):
- "id": MISMO ID de la tarea original
- "name", "description", "dependencies", "inputs", "output"
- "acceptance_criteria", "task_type", "programming_language"
- "executor": "apa" | "user" | "system"
- "priority": "critical" | "high" | "medium" | "low"

La tarea reprogranada debe abordar la causa del fallo.
Si el fallo fue por modelo inadecuado, ajusta el approach.
Si fue por dependencia faltante, agrégala.

Responde ÚNICAMENTE con JSON: {"task": {...}}
"""

_SPLIT_PROMPT = """Eres un planificador experto. Una tarea es demasiado
compleja y necesita dividirse en subtareas más pequeñas y manejables.

Cada subtarea debe tener TODOS los campos obligatorios:
- "id": ID correlativo (ej: T003.1, T003.2, T003.3)
- "name", "description", "dependencies", "inputs", "output"
- "acceptance_criteria", "task_type", "programming_language"
- "executor": "apa" | "user" | "system"
- "priority": "critical" | "high" | "medium" | "low"

Las subtareas deben cubrir TODO el alcance de la tarea original.
La última subtarea puede depender de las anteriores.

Responde ÚNICAMENTE con JSON: {"subtasks": [...]} y {"original_task_id": "..."}
"""


# ─── Clase Planner ─────────────────────────────────────────────────────────


class Planner:
    """Planificador APA que convierte SDD en planes de ejecución.

    Utiliza un LLM para analizar especificaciones de software y generar
    planes estructurados con tareas atómicas. Cada tarea incluye campos
    de 'executor' y 'priority' en todas las rutas de generación.

    Attributes:
        settings: Instancia de configuración de APA.
    """

    def __init__(self, settings: Any) -> None:
        """Inicializa el planificador con la configuración del sistema.

        Args:
            settings: Instancia de config.settings con la configuración
                centralizada del proyecto (modelos, URLs, etc.).
        """
        self.settings = settings
        logger.debug("Planner inicializado")

    def parse_spec(self, spec_content: str) -> dict:
        """Parsea el contenido de un SDD en secciones estructuradas.

        Extrae el título principal, secciones H2/H3, y opcionalmente
        metadatos de frontmatter YAML.

        Args:
            spec_content: Contenido completo del SDD como string.

        Returns:
            Diccionario con:
                - title: Título principal (primer H1)
                - sections: Lista de secciones con título, nivel y contenido
                - frontmatter: Metadatos YAML extraídos
                - content_length: Longitud del contenido
                - section_count: Número de secciones encontradas
        """
        if not spec_content or not spec_content.strip():
            logger.warning("parse_spec: contenido vacío")
            return {
                "title": "Sin título",
                "sections": [],
                "frontmatter": {},
                "content_length": 0,
                "section_count": 0,
            }

        title = self._extract_title(spec_content)
        frontmatter = self._extract_frontmatter(spec_content)
        sections = self._extract_sections(spec_content)

        result = {
            "title": title,
            "sections": [
                {
                    "title": s["title"],
                    "level": s["level"],
                    "content": s["content"],
                    "subsections": s["subsections"],
                }
                for s in sections
            ],
            "frontmatter": frontmatter,
            "content_length": len(spec_content),
            "section_count": len(sections),
        }

        logger.info(
            "SDD parseado: '%s', %d secciones, %d bytes",
            title,
            len(sections),
            len(spec_content),
        )
        return result

    def generate_plan(
        self, spec_content: str, project_id: str = None
    ) -> dict:
        """Punto de entrada principal: parsea SDD y genera plan.

        Args:
            spec_content: Contenido del SDD como string.
            project_id: ID del proyecto (opcional, se genera si None).

        Returns:
            Diccionario con:
                - project_id: ID del proyecto
                - generated_at: Timestamp de generación
                - tasks: Lista de tareas con todos los campos obligatorios
                - total_tasks: Número total de tareas
                - validation_errors: Lista de errores de validación
                - spec_summary: Resumen del SDD parseado
        """
        if project_id is None:
            project_id = f"proj_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

        logger.info(
            "Generando plan para proyecto '%s'", project_id
        )

        # 1. Parsear especificación
        parsed_spec = self.parse_spec(spec_content)

        # 2. Determinar tipo de plan (simple vs multi-archivo)
        is_multi_file = self._is_multi_file_project(parsed_spec)

        # 3. Generar tareas vía LLM
        if is_multi_file:
            tasks = self._generate_multi_file_plan(parsed_spec, project_id)
        else:
            tasks = self._generate_simple_plan(parsed_spec, project_id)

        # 4. Post-procesar: asegurar executor y priority en cada tarea
        tasks = self._ensure_executor_and_priority(tasks)

        # 5. Validar
        validation_errors = self._validate_plan_tasks(tasks)
        if validation_errors:
            logger.warning(
                "Validación del plan: %d problemas", len(validation_errors)
            )
            for error in validation_errors:
                logger.warning("  - %s", error)

        # 6. Construir resultado
        result = {
            "project_id": project_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "tasks": tasks,
            "total_tasks": len(tasks),
            "validation_errors": validation_errors,
            "spec_summary": parsed_spec.get("title", "Sin título"),
            "plan_type": "multi_file" if is_multi_file else "simple",
        }

        logger.info(
            "Plan generado: %d tareas para '%s'",
            len(tasks),
            project_id,
        )
        return result

    def _generate_simple_plan(
        self, parsed_spec: dict, project_id: str
    ) -> list[dict]:
        """Genera un plan simple (proyecto de un solo archivo o módulo).

        Envía el SDD parseado al LLM con instrucciones para generar
        tareas que incluyan executor y priority.

        Args:
            parsed_spec: Diccionario resultado de parse_spec().
            project_id: ID del proyecto.

        Returns:
            Lista de tareas, cada una con todos los campos obligatorios.
        """
        spec_text = self._build_spec_text_for_llm(parsed_spec)

        messages = [
            {"role": "system", "content": _BASE_PLANNING_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Genera un plan de ejecución para el siguiente SDD.\n\n"
                    f"Proyecto: {project_id}\n"
                    f"Título: {parsed_spec.get('title', 'Sin título')}\n\n"
                    f"## Especificación:\n{spec_text}"
                ),
            },
        ]

        return self._call_llm_for_tasks(messages, plan_type="simple")

    def _generate_multi_file_plan(
        self, parsed_spec: dict, project_id: str
    ) -> list[dict]:
        """Genera un plan para proyectos multi-archivo.

        Similar a _generate_simple_plan pero con instrucciones adicionales
        para manejar múltiples archivos y dependencias entre módulos.

        Args:
            parsed_spec: Diccionario resultado de parse_spec().
            project_id: ID del proyecto.

        Returns:
            Lista de tareas con todos los campos obligatorios.
        """
        spec_text = self._build_spec_text_for_llm(parsed_spec)

        prompt = _BASE_PLANNING_PROMPT + _MULTI_FILE_PROMPT_EXTENSION

        messages = [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": (
                    f"Genera un plan de ejecución MULTI-ARCHIVO.\n\n"
                    f"Proyecto: {project_id}\n"
                    f"Título: {parsed_spec.get('title', 'Sin título')}\n\n"
                    f"## Especificación:\n{spec_text}"
                ),
            },
        ]

        return self._call_llm_for_tasks(messages, plan_type="multi_file")

    def replan_task(
        self, project_id: str, task_id: str, reason: str
    ) -> dict:
        """Reprograma una tarea fallida.

        Genera una versión corregida de la tarea que falló, tomando
        en cuenta el motivo del fallo.

        Args:
            project_id: ID del proyecto.
            task_id: ID de la tarea a reprogramar.
            reason: Razón del fallo o motivo de la reprogramación.

        Returns:
            Diccionario con:
                - task: La tarea reprogranada con todos los campos.
                - original_task_id: ID de la tarea original.
                - replan_reason: Razón de la reprogramación.
        """
        logger.info(
            "Reprogramando tarea %s/%s: %s", project_id, task_id, reason
        )

        messages = [
            {"role": "system", "content": _REPLAN_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Reprograma la siguiente tarea fallida:\n\n"
                    f"Proyecto: {project_id}\n"
                    f"ID de tarea: {task_id}\n"
                    f"Razón del fallo: {reason}\n\n"
                    f"Genera una versión corregida que aborde el problema."
                ),
            },
        ]

        response = self._call_llm_raw(messages)
        task = self._parse_single_task(response, task_id)

        # Asegurar campos obligatorios
        task = self._normalize_single_task(task, task_id)

        return {
            "task": task,
            "original_task_id": task_id,
            "replan_reason": reason,
        }

    def split_task_into_subtasks(
        self, project_id: str, task_id: str, reason: str
    ) -> dict:
        """Divide una tarea compleja en subtareas más pequeñas.

        Args:
            project_id: ID del proyecto.
            task_id: ID de la tarea a dividir.
            reason: Razón por la que la tarea necesita dividirse.

        Returns:
            Diccionario con:
                - subtasks: Lista de subtareas con todos los campos.
                - original_task_id: ID de la tarea original.
                - split_reason: Razón de la división.
                - total_subtasks: Número de subtareas generadas.
        """
        logger.info(
            "Dividiendo tarea %s/%s: %s", project_id, task_id, reason
        )

        messages = [
            {"role": "system", "content": _SPLIT_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Divide la siguiente tarea en subtareas:\n\n"
                    f"Proyecto: {project_id}\n"
                    f"ID de tarea: {task_id}\n"
                    f"Razón: {reason}\n\n"
                    f"Genera subtareas con IDs como {task_id}.1, {task_id}.2, etc."
                ),
            },
        ]

        response = self._call_llm_raw(messages)
        subtasks = self._parse_subtasks(response, task_id)

        # Normalizar cada subtarea
        subtasks = [
            self._normalize_single_task(st, st.get("id", f"{task_id}.{i+1}"))
            for i, st in enumerate(subtasks)
        ]

        return {
            "subtasks": subtasks,
            "original_task_id": task_id,
            "split_reason": reason,
            "total_subtasks": len(subtasks),
        }

    # ─── Métodos de parsing interno ──────────────────────────────────────

    @staticmethod
    def _extract_title(content: str) -> str:
        """Extrae el título principal (primer H1) del contenido."""
        match = _H1_PATTERN.search(content)
        return match.group(1).strip() if match else "Sin título"

    @staticmethod
    def _extract_frontmatter(content: str) -> dict:
        """Extrae el bloque YAML frontmatter del inicio del documento."""
        if not _YAML_PATTERN.match(content):
            return {}
        parts = content.split("---")
        if len(parts) < 3 or not parts[1].strip():
            return {}
        frontmatter: dict = {}
        for line in parts[1].strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            key, _, value = line.partition(":")
            value = value.strip().strip("'\"")
            if value.lower() in ("true", "false"):
                value = value.lower() == "true"
            elif value.isdigit():
                value = int(value)
            frontmatter[key.strip()] = value
        return frontmatter

    @staticmethod
    def _extract_sections(content: str) -> list[dict]:
        """Extrae secciones H2 y H3 del contenido Markdown.

        Returns:
            Lista de diccionarios con title, level, content, subsections.
        """
        lines = content.split("\n")
        sections: list[dict] = []
        current: Optional[dict] = None

        for line in lines:
            match = _SECTION_PATTERN.match(line)
            if match:
                level = len(match.group(1))
                title = match.group(2).strip()
                new_section: dict = {
                    "title": title,
                    "level": level,
                    "content": "",
                    "subsections": [],
                }
                if level == 2:
                    sections.append(new_section)
                    current = new_section
                elif level == 3 and current is not None:
                    current["subsections"].append(new_section)
                else:
                    sections.append(new_section)
                    current = new_section
            elif current is not None:
                if current["content"]:
                    current["content"] += "\n" + line
                else:
                    current["content"] = line

        # Limpiar contenido
        for section in sections:
            section["content"] = section["content"].strip()
            for sub in section["subsections"]:
                sub["content"] = sub["content"].strip()

        return sections

    # ─── Métodos de LLM ──────────────────────────────────────────────────

    def _call_llm_raw(self, messages: list[dict]) -> str:
        """Llama al LLM y retorna la respuesta cruda como string.

        Args:
            messages: Lista de mensajes para el LLM.

        Returns:
            String con la respuesta del LLM, o string vacío en error.
        """
        try:
            from core.router import call_llm
            response = call_llm(
                messages=messages,
                model=getattr(self.settings, "DEFAULT_PLANNING_MODEL", None),
                max_tokens=getattr(self.settings, "PLANNING_MAX_TOKENS", 4096),
                temperature=getattr(self.settings, "PLANNING_TEMPERATURE", 0.3),
            )
            logger.debug("LLM respondió con %d caracteres", len(response))
            return response
        except Exception as exc:
            logger.error("Error llamando al LLM: %s", exc)
            return ""

    def _call_llm_for_tasks(
        self, messages: list[dict], plan_type: str = "simple"
    ) -> list[dict]:
        """Llama al LLM y parsea la respuesta como lista de tareas.

        Args:
            messages: Lista de mensajes para el LLM.
            plan_type: Tipo de plan (para logging).

        Returns:
            Lista de diccionarios de tareas, o lista vacía en error.
        """
        response = self._call_llm_raw(messages)

        if not response:
            logger.warning("LLM no respondió para plan %s", plan_type)
            return []

        tasks = self._extract_json_tasks(response)

        if not tasks:
            logger.warning("No se pudieron extraer tareas del plan %s", plan_type)
            return []

        logger.info(
            "LLM generó %d tareas (plan_type=%s)",
            len(tasks),
            plan_type,
        )
        return tasks

    # ─── Métodos de parsing de respuestas LLM ────────────────────────────

    @staticmethod
    def _extract_json_blocks(text: str) -> list[str]:
        """Extrae bloques JSON de un texto (dentro de ```json ... ```).

        Args:
            text: Texto que puede contener bloques JSON.

        Returns:
            Lista de strings JSON extraídos.
        """
        pattern = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)
        blocks = pattern.findall(text)

        if not blocks:
            # Intentar parsear el texto completo como JSON
            cleaned = text.strip()
            if cleaned.startswith("{"):
                blocks = [cleaned]

        return blocks

    def _extract_json_tasks(self, response: str) -> list[dict]:
        """Extrae y parsea tareas de la respuesta del LLM.

        Busca bloques JSON en la respuesta y extrae la lista de tareas.

        Args:
            response: Respuesta cruda del LLM.

        Returns:
            Lista de diccionarios de tareas.
        """
        json_blocks = self._extract_json_blocks(response)

        for block in json_blocks:
            try:
                data = json.loads(block)

                # La respuesta puede ser {"tasks": [...]} o directamente [...]
                if isinstance(data, dict) and "tasks" in data:
                    tasks = data["tasks"]
                elif isinstance(data, list):
                    tasks = data
                else:
                    continue

                if isinstance(tasks, list) and len(tasks) > 0:
                    return [
                        t for t in tasks if isinstance(t, dict)
                    ]
            except (json.JSONDecodeError, TypeError) as exc:
                logger.debug("Error parseando bloque JSON: %s", exc)
                continue

        return []

    def _parse_single_task(
        self, response: str, fallback_id: str
    ) -> dict:
        """Parsea una tarea individual de la respuesta del LLM.

        Args:
            response: Respuesta cruda del LLM.
            fallback_id: ID a usar si la tarea no incluye uno.

        Returns:
            Diccionario con los datos de la tarea.
        """
        json_blocks = self._extract_json_blocks(response)

        for block in json_blocks:
            try:
                data = json.loads(block)
                if isinstance(data, dict) and "task" in data:
                    return data["task"]
                elif isinstance(data, dict) and "id" in data:
                    return data
            except (json.JSONDecodeError, TypeError):
                continue

        # Fallback: tarea vacía con el ID
        return {"id": fallback_id, "name": "Reprogramed task"}

    def _parse_subtasks(
        self, response: str, parent_id: str
    ) -> list[dict]:
        """Parsea subtareas de la respuesta del LLM.

        Args:
            response: Respuesta cruda del LLM.
            parent_id: ID de la tarea padre.

        Returns:
            Lista de diccionarios de subtareas.
        """
        json_blocks = self._extract_json_blocks(response)

        for block in json_blocks:
            try:
                data = json.loads(block)
                if isinstance(data, dict) and "subtasks" in data:
                    return data["subtasks"]
                elif isinstance(data, list):
                    return data
            except (json.JSONDecodeError, TypeError):
                continue

        return []

    # ─── Métodos de normalización ────────────────────────────────────────

    def _ensure_executor_and_priority(
        self, tasks: list[dict]
    ) -> list[dict]:
        """Asegura que todas las tareas tienen executor y priority.

        Si una tarea no tiene estos campos, los infiere a partir del
        tipo de tarea y las palabras clave en la descripción.

        Args:
            tasks: Lista de tareas a normalizar.

        Returns:
            Lista de tareas con executor y priority garantizados.
        """
        total = len(tasks)
        for i, task in enumerate(tasks):
            # Executor
            if not task.get("executor") or task["executor"].strip() == "":
                task["executor"] = self._infer_executor(task)
            task["executor"] = str(task["executor"]).lower().strip()
            if task["executor"] not in VALID_EXECUTORS:
                logger.warning(
                    "Executor inválido '%s' en tarea %s, usando 'apa'",
                    task.get("executor"), task.get("id"),
                )
                task["executor"] = "apa"

            # Priority
            if not task.get("priority") or task["priority"].strip() == "":
                task["priority"] = self._infer_priority(task, i, total)
            task["priority"] = str(task["priority"]).lower().strip()
            if task["priority"] not in VALID_PRIORITIES:
                logger.warning(
                    "Prioridad inválida '%s' en tarea %s, usando 'medium'",
                    task.get("priority"), task.get("id"),
                )
                task["priority"] = "medium"

        return tasks

    def _normalize_single_task(self, task: dict, fallback_id: str) -> dict:
        """Normaliza una tarea individual asegurando campos obligatorios.

        Args:
            task: Diccionario de la tarea.
            fallback_id: ID por defecto si no tiene.

        Returns:
            Tarea normalizada.
        """
        task.setdefault("id", fallback_id)
        task.setdefault("name", "Tarea sin nombre")
        task.setdefault("description", "")
        task.setdefault("dependencies", [])
        task.setdefault("inputs", [])
        task.setdefault("output", "")
        task.setdefault("acceptance_criteria", "")
        task.setdefault("task_type", "code_generation")
        task.setdefault("programming_language", "python")
        task.setdefault("executor", "apa")
        task.setdefault("priority", "medium")

        # Normalizar executor y priority
        task["executor"] = str(task["executor"]).lower().strip()
        task["priority"] = str(task["priority"]).lower().strip()

        if task["executor"] not in VALID_EXECUTORS:
            task["executor"] = "apa"
        if task["priority"] not in VALID_PRIORITIES:
            task["priority"] = "medium"

        return task

    @staticmethod
    def _infer_executor(task: dict) -> str:
        """Infiere el executor a partir del tipo de tarea y palabras clave.

        Args:
            task: Diccionario de la tarea.

        Returns:
            Uno de: "apa", "user", "system".
        """
        task_type = task.get("task_type", "").lower()
        text = (
            task.get("name", "") + " " + task.get("description", "")
        ).lower()

        # Primero verificar palabras clave específicas
        for kw in _KEYWORDS_SYSTEM:
            if kw in text:
                return "system"

        for kw in _KEYWORDS_USER:
            if kw in text:
                return "user"

        # Luego usar mapeo por tipo
        return _EXECUTOR_MAP.get(task_type, "apa")

    @staticmethod
    def _infer_priority(task: dict, index: int, total: int) -> str:
        """Infiere la prioridad a partir del tipo y posición.

        Args:
            task: Diccionario de la tarea.
            index: Índice de la tarea en el plan.
            total: Número total de tareas.

        Returns:
            Uno de: "critical", "high", "medium", "low".
        """
        task_type = task.get("task_type", "").lower()
        base_priority = _PRIORITY_MAP.get(task_type, "medium")

        # Las primeras tareas (setup) suelen ser críticas
        if index < 2 and task_type in ("setup", "configuration"):
            return "critical"

        return base_priority

    # ─── Métodos de validación ────────────────────────────────────────────

    def _validate_plan_tasks(self, tasks: list[dict]) -> list[str]:
        """Valida que todas las tareas tienen los campos obligatorios.

        Args:
            tasks: Lista de tareas a validar.

        Returns:
            Lista de strings con los errores encontrados.
            Lista vacía si todo es válido.
        """
        errors: list[str] = []
        seen_ids: set[str] = set()

        for i, task in enumerate(tasks):
            task_id = task.get("id", f"T{i:03d}")

            # Verificar campos obligatorios
            for field in TASK_REQUIRED_FIELDS:
                if field not in task:
                    errors.append(
                        f"Tarea {task_id}: falta campo '{field}'"
                    )

            # Verificar IDs únicos
            if task_id in seen_ids:
                errors.append(f"Tarea {task_id}: ID duplicado")
            seen_ids.add(task_id)

            # Verificar valores válidos
            executor = task.get("executor", "")
            if executor not in VALID_EXECUTORS:
                errors.append(
                    f"Tarea {task_id}: executor inválido '{executor}'"
                )

            priority = task.get("priority", "")
            if priority not in VALID_PRIORITIES:
                errors.append(
                    f"Tarea {task_id}: priority inválida '{priority}'"
                )

            task_type = task.get("task_type", "")
            if task_type not in VALID_TASK_TYPES:
                errors.append(
                    f"Tarea {task_id}: task_type inválido '{task_type}'"
                )

            # Verificar que las dependencias referencian IDs existentes
            deps = task.get("dependencies", [])
            if isinstance(deps, list):
                for dep in deps:
                    if dep not in seen_ids and dep != task_id:
                        # La dependencia podría estar más adelante en el plan
                        pass

        return errors

    # ─── Métodos auxiliares ───────────────────────────────────────────────

    @staticmethod
    def _is_multi_file_project(parsed_spec: dict) -> bool:
        """Determina si el SDD describe un proyecto multi-archivo.

        Heurísticas:
            - Menciona múltiples archivos o módulos
            - Tiene secciones de "arquitectura" con múltiples componentes
            - El contenido es largo (> 5000 chars)

        Args:
            parsed_spec: Diccionario resultado de parse_spec().

        Returns:
            True si parece un proyecto multi-archivo.
        """
        content_length = parsed_spec.get("content_length", 0)
        sections = parsed_spec.get("sections", [])

        # Proyecto largo es más probablemente multi-archivo
        if content_length > 5000:
            return True

        # Buscar secciones que sugieran múltiples archivos
        multi_file_keywords = [
            "módulo", "modulo", "archivo", "paquete", "package",
            "directorio", "carpeta", "componente", "servicio",
            "microservicio", "endpoint", "api", "router", "controlador",
            "modelo", "vista", "controler", "module", "file",
        ]

        all_text = " ".join(
            s.get("title", "") + " " + s.get("content", "")
            for s in sections
        ).lower()

        keyword_hits = sum(
            1 for kw in multi_file_keywords if kw in all_text
        )
        return keyword_hits >= 3

    @staticmethod
    def _build_spec_text_for_llm(parsed_spec: dict) -> str:
        """Construye un resumen del SDD para enviar al LLM.

        Args:
            parsed_spec: Diccionario resultado de parse_spec().

        Returns:
            String formateado con las secciones del SDD.
        """
        parts: list[str] = []

        title = parsed_spec.get("title", "Sin título")
        parts.append(f"# {title}")
        parts.append("")

        for section in parsed_spec.get("sections", []):
            level = section.get("level", 2)
            prefix = "#" * level
            parts.append(f"{prefix} {section.get('title', '')}")
            if section.get("content"):
                parts.append(section["content"])
            parts.append("")

            for sub in section.get("subsections", []):
                sub_level = sub.get("level", 3)
                sub_prefix = "#" * sub_level
                parts.append(f"{sub_prefix} {sub.get('title', '')}")
                if sub.get("content"):
                    parts.append(sub["content"])
                parts.append("")

        return "\n".join(parts)


# ─── Validación standalone ─────────────────────────────────────────────────


if __name__ == "__main__":
    print("=== Validación de core/planner.py ===")
    print()

    # 1. Crear mock de settings
    class MockSettings:
        DEFAULT_PLANNING_MODEL = None
        PLANNING_MAX_TOKENS = 4096
        PLANNING_TEMPERATURE = 0.3

    settings = MockSettings()
    planner = Planner(settings)
    print("[OK] Planner instanciado con settings")

    # 2. Probar parse_spec con contenido SDD de ejemplo
    sdd_content = """# Sistema de Gestión de Inventarios

## Requisitos Funcionales
El sistema debe permitir gestionar productos, categorías y proveedores.
Debe soportar búsqueda, filtrado y reportes.

### Gestión de Productos
CRUD completo de productos con validación de stock mínimo.

### Gestión de Categorías
Árbol jerárquico de categorías con hasta 5 niveles.

## Arquitectura Técnica
Backend en Python con FastAPI.
Base de datos PostgreSQL.
Frontend en React con TypeScript.

## Módulos
- Módulo de autenticación
- Módulo de inventario
- Módulo de reportes
"""

    parsed = planner.parse_spec(sdd_content)
    assert parsed["title"] == "Sistema de Gestión de Inventarios"
    assert parsed["section_count"] > 0
    print(f"[OK] parse_spec: título='{parsed['title']}', {parsed['section_count']} secciones")

    # 3. Probar con contenido vacío
    empty_parsed = planner.parse_spec("")
    assert empty_parsed["title"] == "Sin título"
    assert empty_parsed["section_count"] == 0
    print("[OK] parse_spec con contenido vacío")

    # 4. Probar detección multi-archivo
    is_multi = planner._is_multi_file_project(parsed)
    print(f"[OK] Detección multi-archivo: {is_multi}")

    # 5. Probar inferencia de executor
    task_apa = {"name": "Crear endpoint de login", "task_type": "code_generation"}
    assert planner._infer_executor(task_apa) == "apa"
    print("[OK] Inferencia executor: code_generation -> apa")

    task_user = {"name": "Aprobar diseño visual del dashboard", "task_type": "design"}
    assert planner._infer_executor(task_user) == "user"
    print("[OK] Inferencia executor: diseño visual -> user")

    task_system = {"name": "Desplegar en AWS", "task_type": "deployment"}
    assert planner._infer_executor(task_system) == "system"
    print("[OK] Inferencia executor: deployment -> system")

    # 6. Probar inferencia de priority
    task_critical = {"name": "Setup", "task_type": "setup"}
    assert planner._infer_priority(task_critical, 0, 10) == "critical"
    print("[OK] Inferencia priority: setup(index=0) -> critical")

    task_low = {"name": "Docs", "task_type": "documentation"}
    assert planner._infer_priority(task_low, 5, 10) == "low"
    print("[OK] Inferencia priority: documentation -> low")

    # 7. Probar ensure_executor_and_priority
    raw_tasks = [
        {"id": "T001", "name": "Task 1", "task_type": "setup"},
        {"id": "T002", "name": "Task 2", "task_type": "documentation", "executor": "invalid", "priority": "urgent"},
    ]
    normalized = planner._ensure_executor_and_priority(raw_tasks)
    assert normalized[0]["executor"] in VALID_EXECUTORS
    assert normalized[0]["priority"] in VALID_PRIORITIES
    assert normalized[1]["executor"] == "apa"  # Normalizado de "invalid"
    assert normalized[1]["priority"] == "medium"  # Normalizado de "urgent"
    print("[OK] ensure_executor_and_priority normaliza correctamente")

    # 8. Probar validación
    valid_tasks = [
        {
            "id": "T001", "name": "Setup", "description": "Configurar entorno",
            "dependencies": [], "inputs": ["requisitos"], "output": "entorno configurado",
            "acceptance_criteria": "El entorno responde", "task_type": "setup",
            "programming_language": "python", "executor": "system", "priority": "critical",
        },
        {
            "id": "T002", "name": "Auth module", "description": "Crear auth",
            "dependencies": ["T001"], "inputs": ["entorno"], "output": "auth.py",
            "acceptance_criteria": "Tests pasan", "task_type": "code_generation",
            "programming_language": "python", "executor": "apa", "priority": "high",
        },
    ]
    errors = planner._validate_plan_tasks(valid_tasks)
    assert len(errors) == 0, f"Errores inesperados: {errors}"
    print("[OK] Validación de tareas válidas: sin errores")

    # 9. Probar validación con errores
    invalid_tasks = [
        {"id": "T001", "name": "Bad task"},  # Faltan campos
        {"id": "T001", "name": "Dup"},  # ID duplicado
    ]
    errors = planner._validate_plan_tasks(invalid_tasks)
    assert len(errors) > 0
    print(f"[OK] Validación detecta {len(errors)} errores en tareas inválidas")

    # 10. Probar normalización de tarea individual
    raw_task = {"name": "Test task"}
    normalized = planner._normalize_single_task(raw_task, "T099")
    assert normalized["id"] == "T099"
    assert normalized["executor"] == "apa"
    assert normalized["priority"] == "medium"
    assert normalized["dependencies"] == []
    assert normalized["inputs"] == []
    print("[OK] normalize_single_task completa campos faltantes")

    # 11. Probar extracción de bloques JSON
    test_response = '''Aquí está el plan:
```json
{"tasks": [{"id": "T001", "name": "Test", "executor": "apa", "priority": "high"}]}
```
Espero que te sirva.'''
    blocks = Planner._extract_json_blocks(test_response)
    assert len(blocks) == 1
    parsed_tasks = planner._extract_json_tasks(test_response)
    assert len(parsed_tasks) == 1
    assert parsed_tasks[0]["id"] == "T001"
    print("[OK] Extracción de bloques JSON funciona")

    # 12. Probar build_spec_text_for_llm
    spec_text = planner._build_spec_text_for_llm(parsed)
    assert "Sistema de Gestión de Inventarios" in spec_text
    assert "Arquitectura" in spec_text or "Arquitectura Técnica" in spec_text
    print("[OK] build_spec_text_for_llm genera texto correcto")

    # 13. Probar extract_frontmatter
    fm_content = '''---
title: Mi Proyecto
version: 2
active: true
---

# Mi Proyecto

## Intro
Contenido.
'''
    fm = Planner._extract_frontmatter(fm_content)
    assert fm["title"] == "Mi Proyecto"
    assert fm["version"] == 2
    assert fm["active"] is True
    print("[OK] extract_frontmatter parsea YAML correctamente")

    # 14. Verificar que todos los prompts incluyen executor y priority
    assert "executor" in _BASE_PLANNING_PROMPT
    assert "priority" in _BASE_PLANNING_PROMPT
    assert "executor" in _REPLAN_PROMPT
    assert "priority" in _REPLAN_PROMPT
    assert "executor" in _SPLIT_PROMPT
    assert "priority" in _SPLIT_PROMPT
    print("[OK] Todos los prompts del LLM incluyen executor y priority")

    print()
    print("=== Todas las validaciones pasaron ===")
