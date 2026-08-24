"""
chat_sdd_flow.py — Flujo Chat -> SDD con 3 ramas (desacoplado de app.py).

Rama A (Normal):        Modelo rapido + arnes CV2. Boton NUNCA visible.
Rama B (Escalacion):     Regex 5/5 -> LLM confirma -> modelo superior valida.
Rama C (Post-escalacion): Modelo superior SIEMPRE. Boton SIEMPRE visible.

Dependencias se inyectan via ChatDependencies para poder testear sin infraestructura.

Validacion:
    python chat_sdd_flow.py
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Callable
from pathlib import Path

# Path setup: asegurar que `core` sea importable cuando se ejecuta
# como script (python core/chat_sdd_flow.py) además de como módulo.
_THIS_DIR = Path(__file__).resolve()
_APAPA_ROOT = _THIS_DIR.parent.parent  # apa/
import sys as _sys
if str(_APAPA_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_APAPA_ROOT))

# TDM (Tech Domain Map) — Decisiones 1+3 del Director:
# inyectar la base de conocimiento tecnológica en el prompt base del
# flujo Chat→SDD para que las 3 ramas (A, B, C) la compartan.
try:
    from core.tech_domain_map import get_domain_knowledge_prompt as _tdm_knowledge
except Exception:  # pragma: no cover — fallback defensivo
    logging.getLogger(__name__).warning(
        "chat_sdd_flow: tech_domain_map no disponible", exc_info=True
    )
    def _tdm_knowledge() -> str:  # type: ignore[no-redef]
        return ""


# =========================================================================
# Constantes: 18 aspectos de la especificacion
# =========================================================================

ASPECTS_FOR_LLM = {
    "IMPRESCINDIBLES": [
        ("what_is", "Que es y para quien"),
        ("problem", "Que problema resuelve"),
        ("features", "Que hace concretamente"),
        ("limits", "Que NO hace"),
        ("usage", "Como se usa paso a paso"),
    ],
    "NECESARIAS": [
        ("similar_existing", "Referencias o apps similares"),
        ("stakeholders", "Quien aprueba o revisa"),
        ("constraints", "Restricciones importantes"),
        ("success_criteria", "Como saber que quedo bien"),
        ("integrations", "Conexiones con sistemas externos"),
        ("states", "Estados o etapas del proceso"),
        ("invariants", "Reglas que siempre se cumplen"),
        ("edge_cases", "Que podria salir mal"),
    ],
    "PRESCINDIBLES": [
        ("alternatives", "Alternativas consideradas"),
        ("timeline", "Cronograma o fechas"),
        ("cross_team_impact", "Impacto en otros equipos"),
        ("testing_approach", "Como se va a probar"),
        ("open_questions", "Dudas pendientes"),
    ],
}

IMP_KEYS = [k for k, _ in ASPECTS_FOR_LLM["IMPRESCINDIBLES"]]
ALL_ASPECT_KEYS = [k for group in ASPECTS_FOR_LLM.values() for k, _ in group]


# =========================================================================
# Prompts de sistema
# =========================================================================

VALIDATION_SYSTEM_ADDITION = r"""
--- TAREA PRINCIPAL: VALIDACION DE MADUREZ ---
Has sido escalado porque el sistema detecto que los 5 aspectos imprescindibles pueden estar cubiertos.
Tu PRIMERA tarea es revisar TODO el contexto de la conversacion y determinar si realmente hay
suficiente detalle en los 5 aspectos imprescindibles para generar una SDD:
  a) Que es y para quien
  b) Que problema resuelve
  c) Que hace concretamente (funcionalidades)
  d) Que NO hace (limites)
  e) Como se usa paso a paso

Si consideras que hay suficiente detalle en los 5, continua la conversacion naturalmente
preguntando sobre los siguientes aspectos necesarios del proyecto.
Si consideras que falta precision o detalle en alguno de los 5 imprescindibles,
pregunta especificamente por lo que falte. NO confirmes que esta listo si hay ambiguedades.

--- LO QUE NUNCA DEBES HACER EN ESTE MODO ---
- NO generes codigo, especificaciones completas, ni tablas de tecnologias.
- NO avances por tu cuenta si el usuario no ha confirmado algo.
- NO respondas como si ya tuvieras toda la informacion si no es asi.
"""

POST_ESCALATION_SYSTEM_ADDITION = r"""
--- CONTEXTO: ESPECIFICACION IMPRESCINDIBLE CONFIRMADA ---
Los 5 aspectos imprescindibles han sido validados como maduros. El usuario puede generar la SDD.
Tu trabajo ahora es continuar la conversacion preguntando sobre los 13 aspectos restantes
(8 necesarios + 5 prescindibles) para enriquecer la especificacion.
- NO vuelvas a preguntar sobre los 5 imprescindibles ya confirmados.
- Trata UN aspecto por respuesta. No intentes cubrir todo de golpe.
- Si el usuario pregunta sobre tus capacidades, responde basandote en tu contexto.

Los 8 aspectos NECESARIOS son:
  1. Referencias o apps similares
  2. Quien aprueba o revisa
  3. Restricciones importantes
  4. Como saber que quedo bien
  5. Conexiones con sistemas externos
  6. Estados o etapas del proceso
  7. Reglas que siempre se cumplen
  8. Que podria salir mal

Los 5 aspectos PRESINDIBLES son:
  1. Alternativas consideradas
  2. Cronograma o fechas
  3. Impacto en otros equipos
  4. Como se va a probar
  5. Dudas pendientes

--- LO QUE NUNCA DEBES HACER EN ESTE MODO ---
- NO generes codigo, especificaciones completas, ni tablas de tecnologias.
- NO generes planes de tareas ni cronogramas por tu cuenta.
"""


def build_base_system_prompt(self_context: str) -> str:
    """Construye el prompt base del sistema (comun a todas las ramas).

    Decisiones 1+3 del Director: incluye la base de conocimiento tecnológico
    (TDM) para que el LLM conozca qué lenguaje/framework encaja con cada
    tipo de proyecto, y un bloque persuasivo para que explique SIEMPRE el
    porqué de sus recomendaciones de tecnología.
    """
    tdm_block = _tdm_knowledge()
    tdm_section = (
        f"\n\n--- BASE DE CONOCIMIENTO TECNOLOGICO (TDM) ---\n"
        f"{tdm_block}\n"
        if tdm_block else ""
    )
    persuasion_section = (
        "\n\n--- COMO RECOMENDAR TECNOLOGIA AL USUARIO ---\n"
        "Si durante la conversacion surge la oportunidad de sugerir un lenguaje, "
        "framework o herramienta, explica SIEMPRE por que lo recomiendas: "
        "ventajas concretas, encaje con el caso del usuario y por que es mejor "
        "que las alternativas habituales. Si el usuario propone otra tecnologia, "
        "respetala pero explica con honestidad y argumentos las ventajas de la "
        "recomendada y los riesgos de su eleccion. Persuade con argumentos "
        "tecnicos: si tras la explicacion el usuario mantiene su eleccion, "
        "acetala y adaptate a ella.\n"
    )
    return (
        f"Eres APA, un asistente de programacion autonoma. Aqui esta tu identidad y capacidades:\n\n"
        f"{self_context}\n\n"
        f"---\n\n"
        f"--- TU ROL EN ESTA CONVERSACION ---\n"
        f"Tu UNICO trabajo aqui es ayudar al usuario a definir su proyecto con suficiente detalle "
        f"para generar una SDD (Spec Driven Development). No es generar codigo, ni planificar tareas, "
        f"ni crear especificaciones completas. Tu trabajo termina cuando el usuario pulsa 'Generar la SDD'.\n\n"
        f"--- LO QUE NUNCA DEBES HACER ---\n"
        f"- NO generes planes de tareas, especificaciones completas, codigo, ni tablas de tecnologias.\n"
        f"- NO enumeres tareas atomicas, fases de desarrollo, ni cronogramas.\n"
        f"- NO generes tablas de stacks, arquitecturas detalladas, ni estructuras de directorios.\n"
        f"- Si el usuario aprueba algo que acabais de discutir, NO avances al siguiente paso por tu cuenta.\n"
        f"- NO respondas como si ya tuvieras toda la informacion. Si faltan aspectos, PREGUNTA.\n\n"
        f"--- COMO DEBES PROCEDER ---\n"
        f"1. Detecta si el usuario esta describiendo un proyecto de software.\n"
        f"2. Si lo esta, enfocate en cubrir estos 5 aspectos IMPRESCINDIBLES (uno por respuesta, no todos a la vez):\n"
        f"   a) Que es y para quien\n"
        f"   b) Que problema resuelve\n"
        f"   c) Que hace concretamente (funcionalidades)\n"
        f"   d) Que NO hace (limites)\n"
        f"   e) Como se usa paso a paso\n"
        f"3. Cuando los 5 imprescindibles esten cubiertos, avanza a los aspectos NECESARIOS (8) y luego PRESINDIBLES (5).\n"
        f"4. Solo cuando todos los aspectos esten cubiertos, sugiere al usuario generar la SDD.\n"
        f"5. Si el usuario pregunta sobre tus capacidades o lenguajes soportados, responde basandote en tu contexto.\n\n"
        f"--- ESTILO DE CONVERSACION ---\n"
        f"- Responde SIEMPRE en el mismo idioma que el usuario.\n"
        f"- Manten respuestas de 3 a 5 lineas. NO escribas respuestas largas.\n"
        f"- Trata UN aspecto por respuesta. No intentes cubrir todo de golpe.\n"
        f"- Haz pedagogia: si mencionas un termino tecnico, explicalo de forma sencilla.\n"
        f"- Ajustate al nivel del usuario.\n"
        f"- El tono debe ser ameno, como una conversacion entre colegas.\n\n"
        f"--- DETECCION DE VARIANTES ---\n"
        f"Debes determinar SIEMPRE si el usuario quiere:\n"
        f"A) CREAR UN PROYECTO NUEVO desde cero.\n"
        f"B) TRABAJAR SOBRE UN PROYECTO EXISTENTE (refactorizar, mejorar, extender).\n"
        f"C) El usuario habla de un proyecto y tu le pides la ubicacion (inducida por el modelo).\n\n"
        f"Para VARIANT A (proyecto nuevo):\n"
        f"- Cuando detectes que el usuario quiere crear algo nuevo, pregunta por el NOMBRE DEL PROYECTO.\n"
        f"- NO preguntes por la ubicacion; el sistema usara apa/APA Proyectos como default.\n\n"
        f"Para VARIANT B (proyecto existente):\n"
        f"- Pregunta por la UBICACION (ruta) de los scripts fuentes del proyecto.\n\n"
        f"Para VARIANT C (ubicacion inducida):\n"
        f"- Si el usuario describe un proyecto existente pero no menciona ubicacion, preguntale.\n\n"
        f"IMPORTANTE: Detecta la variante lo antes posible (en los primeros 1-2 mensajes).\n\n"
        f"--- ACCESO A ARCHIVOS DEL PROYECTO ---\n"
        f"Cuando un usuario proporciona la ruta de un proyecto existente, el sistema TIENE ACCESO "
        f"a todos los archivos de ese directorio. El sistema lee automaticamente los archivos y genera "
        f"un analisis que se incluye en el contexto de esta conversacion.\n"
        f"- NUNCA digas que no puedes acceder a los archivos del proyecto.\n"
        f"- Si necesitas informacion que no esta en el contexto, di exactamente que archivo necesitas."
        f"{tdm_section}"
        f"{persuasion_section}"
    )


# =========================================================================
# Funciones auxiliares
# =========================================================================

def build_sdd_status_from_llm(llm_result: dict):
    """Construye sdd_status desde resultado del evaluador LLM.
    Retorna (sdd_status, is_project, objective_summary, maturity_summary).
    """
    aspects = llm_result["aspects"]
    is_project = llm_result["is_project"]
    objective_summary = llm_result.get("objective_summary", "")

    aspects_detail = {"imprescindibles": [], "necesarias": [], "prescindibles": []}
    for category, cat_aspects in ASPECTS_FOR_LLM.items():
        prio_key = category.lower()
        for key, label_desc in cat_aspects:
            label = label_desc.split(" — ")[0]
            status = aspects.get(key, "not_covered").upper()
            entry = {"key": key, "label": label, "status": status, "evidence": ""}
            if prio_key in aspects_detail:
                aspects_detail[prio_key].append(entry)

    imp_covered = sum(1 for k, _ in ASPECTS_FOR_LLM["IMPRESCINDIBLES"] if aspects.get(k) == "covered")
    imp_total = len(ASPECTS_FOR_LLM["IMPRESCINDIBLES"])
    nec_covered = sum(1 for k, _ in ASPECTS_FOR_LLM["NECESARIAS"] if aspects.get(k) == "covered")
    nec_total = len(ASPECTS_FOR_LLM["NECESARIAS"])
    pre_covered = sum(1 for k, _ in ASPECTS_FOR_LLM["PRESCINDIBLES"] if aspects.get(k) == "covered")
    pre_total = len(ASPECTS_FOR_LLM["PRESCINDIBLES"])

    can_generate = (imp_covered >= imp_total) if is_project else False
    if can_generate and nec_covered >= nec_total:
        maturity = "maduro"
    elif can_generate or imp_covered >= 3:
        maturity = "intermedio"
    else:
        maturity = "inicial"

    sdd_status = {
        "can_generate": can_generate,
        "is_project": is_project,
        "maturity": maturity,
        "project_confidence": 1.0 if is_project else 0.0,
        "covered_count": imp_covered,
        "total_essentials": imp_total,
        "necesarias_covered": nec_covered,
        "necesarias_total": nec_total,
        "prescindibles_covered": pre_covered,
        "prescindibles_total": pre_total,
        "aspects_detail": aspects_detail,
    }

    msum_lines = ["=== ESTADO DE LA ESPECIFICACION DEL PROYECTO ==="]
    for category, cat_aspects in ASPECTS_FOR_LLM.items():
        msum_lines.append("\n--- " + category + " ---")
        for key, label_desc in cat_aspects:
            label = label_desc.split(" — ")[0]
            val = aspects.get(key, "not_covered")
            mark = "+" if val == "covered" else ("~" if val == "partial" else "-")
            msum_lines.append("  [" + mark + "] " + label + ": " + val)
    maturity_summary = "\n".join(msum_lines)

    return sdd_status, is_project, objective_summary, maturity_summary


def build_fallback_sdd_status() -> dict:
    """Genera un sdd_status minimo con todos los aspectos en not_covered."""
    return {
        "can_generate": False,
        "is_project": False,
        "maturity": "inicial",
        "project_confidence": 0.0,
        "covered_count": 0,
        "total_essentials": len(IMP_KEYS),
        "necesarias_covered": 0,
        "necesarias_total": len(ASPECTS_FOR_LLM["NECESARIAS"]),
        "prescindibles_covered": 0,
        "prescindibles_total": len(ASPECTS_FOR_LLM["PRESCINDIBLES"]),
        "aspects_detail": {
            "imprescindibles": [
                {"key": k, "label": d, "status": "NOT_COVERED", "evidence": ""}
                for k, d in ASPECTS_FOR_LLM["IMPRESCINDIBLES"]
            ],
            "necesarias": [
                {"key": k, "label": d, "status": "NOT_COVERED", "evidence": ""}
                for k, d in ASPECTS_FOR_LLM["NECESARIAS"]
            ],
            "prescindibles": [
                {"key": k, "label": d, "status": "NOT_COVERED", "evidence": ""}
                for k, d in ASPECTS_FOR_LLM["PRESCINDIBLES"]
            ],
        },
    }


def count_imp_covered(aspects: dict) -> int:
    """Cuenta cuantos aspectos imprescindibles estan 'covered'."""
    return sum(1 for k in IMP_KEYS if aspects.get(k) == "covered")


def all_imp_covered(aspects: dict) -> bool:
    """Verifica si los 5 imprescindibles estan covered."""
    return count_imp_covered(aspects) >= len(IMP_KEYS)


# =========================================================================
# Inyeccion de dependencias
# =========================================================================

@dataclass
class ChatDependencies:
    """Dependencias inyectadas. Permite testear sin infraestructura APA real."""
    sdd_evaluator: Any              # Objeto con .evaluate(history) -> resultado
    sdd_guide: Any                  # Objeto con .process_message(msg, hist), .get_system_prompt_addition(hint)
    evaluate_maturity_fn: Callable  # fn(history, chat_model_used=None) -> dict|None
    call_llm_fn: Callable           # fn(task_type, system_prompt, user_prompt, max_tokens, temperature) -> dict
    notify_fn: Callable             # fn(event_type, message, data)
    logger: logging.Logger


# =========================================================================
# Gestor del flujo
# =========================================================================

class ChatSDDFlowManager:
    """Gestiona el flujo de 3 ramas del endpoint /chat.

    Uso:
        deps = ChatDependencies(...)
        manager = ChatSDDFlowManager(deps)
        resultado = await manager.process(request, self_context, project_context)
    """

    def __init__(self, deps: ChatDependencies):
        self._deps = deps
        self._log = deps.logger

    # -----------------------------------------------------------------
    # Punto de entrada
    # -----------------------------------------------------------------

    async def process(self, request, self_context: str, project_context: str = "") -> dict:
        """Decide la rama, ejecuta, y devuelve el dict listo para JSONResponse.

        Args:
            request: Objeto con .message, .history, .project_path, .is_escalated.
            self_context: Texto de autoconocimiento de APA.
            project_context: Texto del contexto del proyecto (si hay ruta).

        Returns:
            dict con claves: response, model_used, success, error,
                           sdd_status, objective_summary, escalation_confirmed,
                           project_variant, project_name, project_path, maturity_summary
        """
        base_prompt = build_base_system_prompt(self_context)
        full_history = (request.history or []) + [{"role": "user", "content": request.message}]
        loop = asyncio.get_event_loop()

        # Inicializar variables de resultado
        result = {"success": False, "content": "", "model_used": "", "error": None}
        sdd_status = None
        objective_summary = ""
        is_project = False
        escalation_confirmed = False
        response_maturity_summary = ""

        # --- RAMA C: Post-escalacion ---
        if getattr(request, 'is_escalated', False):
            result, sdd_status, is_project, escalation_confirmed, response_maturity_summary, objective_summary = \
                await self._handle_rama_c(request, base_prompt, project_context, full_history, loop)

        # --- RAMA A / RAMA B: Pre-escalacion ---
        else:
            regex_result = self._regex_evaluate(full_history)
            result, sdd_status, is_project, escalation_confirmed, response_maturity_summary, objective_summary = \
                await self._handle_pre_escalation(request, base_prompt, project_context, full_history, loop, regex_result)

        # --- Comun: deteccion de variante ---
        variant_data = self._detect_variant(full_history, result.get("content", ""), getattr(request, 'project_path', None))

        # --- Construir respuesta final ---
        response = {
            "response": result.get("content", ""),
            "model_used": result.get("model_used", ""),
            "success": result.get("success", False),
            "error": result.get("error"),
        }
        if sdd_status:
            response["sdd_status"] = sdd_status
        if is_project:
            response["objective_summary"] = objective_summary
        if escalation_confirmed:
            response["escalation_confirmed"] = True
        response.update(variant_data)
        if response_maturity_summary:
            response["maturity_summary"] = response_maturity_summary

        self._log.info("FINAL sdd_status -- is_project=%s, can_gen=%s, imp=%s/%s, escalation=%s",
                        sdd_status.get("is_project") if sdd_status else None,
                        sdd_status.get("can_generate") if sdd_status else None,
                        sdd_status.get("covered_count") if sdd_status else None,
                        sdd_status.get("total_essentials") if sdd_status else None,
                        escalation_confirmed)

        return response

    # -----------------------------------------------------------------
    # RAMA C: Post-escalacion
    # -----------------------------------------------------------------

    async def _handle_rama_c(self, request, base_prompt, project_context, full_history, loop):
        """Modelo superior SIEMPRE, boton SIEMPRE visible, sin arnes CV2.

        Returns: (result, sdd_status, is_project, escalation_confirmed, maturity_summary, objective_summary)
        """
        self._log.info("Rama C: Post-escalacion activa — usando modelo superior")
        system_prompt = base_prompt + POST_ESCALATION_SYSTEM_ADDITION

        user_prompt = self._build_full_prompt(request, full_history, project_context)
        result = await self._call_llm_async("planning", system_prompt, user_prompt, loop)
        self._notify_model(result, "capable")

        # Evaluador LLM para seguimiento de los 13 aspectos restantes
        updated_history = full_history + [{"role": "assistant", "content": result.get("content", "")}]
        sdd_status, is_project, obj_sum, mat_sum = await self._evaluate_maturity_async(
            updated_history, result.get("model_used"), loop)

        if sdd_status:
            sdd_status["can_generate"] = True  # Rama C: siempre visible
        else:
            sdd_status = build_fallback_sdd_status()
            sdd_status["can_generate"] = True
            is_project = True
            user_msgs = [m.get("content", "") for m in full_history if m.get("role") == "user"]
            obj_sum = user_msgs[0][:200].strip() if user_msgs else ""

        return result, sdd_status, is_project, False, mat_sum, obj_sum

    # -----------------------------------------------------------------
    # RAMA A / B: Pre-escalacion
    # -----------------------------------------------------------------

    async def _handle_pre_escalation(self, request, base_prompt, project_context, full_history, loop, regex_result):
        """Decide entre Rama A (normal) y Rama B (escalacion).

        Returns: (result, sdd_status, is_project, escalation_confirmed, maturity_summary, objective_summary)
        """
        # Si el regex indica 5/5, intentar escalacion (Rama B)
        if regex_result and getattr(regex_result, 'can_generate_project', False):
            return await self._handle_rama_b(request, base_prompt, project_context, full_history, loop, regex_result)

        # Si no, Rama A
        return await self._handle_rama_a(request, base_prompt, project_context, full_history, loop, regex_result)

    # -----------------------------------------------------------------
    # RAMA B: Punto de escalacion
    # -----------------------------------------------------------------

    async def _handle_rama_b(self, request, base_prompt, project_context, full_history, loop, regex_result):
        """Regex dice 5/5. LLM confirma. Modelo superior valida.

        Returns: (result, sdd_status, is_project, escalation_confirmed, maturity_summary, objective_summary)
        """
        self._log.info("Rama B: Regex indica 5/5 — consultando LLM para confirmar")

        # Paso 1: LLM confirma 5/5
        llm_confirm = await self._evaluate_maturity_async(full_history, None, loop, return_raw=True)
        llm_confirm = llm_confirm[0] if llm_confirm else None  # Desempaquetar de tuple

        if not llm_confirm or not llm_confirm.get("is_project") or not all_imp_covered(llm_confirm["aspects"]):
            self._log.info("Rama B: LLM desestimo la escalacion — cayendo a Rama A")
            return await self._handle_rama_a(request, base_prompt, project_context, full_history, loop, regex_result)

        # Paso 2: Escalar a modelo superior
        self._log.info("Rama B: Escalando a modelo superior (planning)")
        system_prompt = base_prompt + VALIDATION_SYSTEM_ADDITION
        user_prompt = self._build_full_prompt(request, full_history, project_context)
        result = await self._call_llm_async("planning", system_prompt, user_prompt, loop)
        self._notify_model(result, "capable")
        try:
            self._deps.notify_fn("chat_escalate", "Modelo escalado a tier 'capable'", {"task_type": "planning"})
        except Exception:
            pass

        # Paso 3: Re-evaluar despues de la respuesta del superior
        updated_history = full_history + [{"role": "assistant", "content": result.get("content", "")}]
        sdd_status, is_project, obj_sum, mat_sum = await self._evaluate_maturity_async(
            updated_history, result.get("model_used"), loop)

        # Paso 4: El superior mantuvo la madurez?
        escalation_confirmed = False
        if sdd_status:
            # Verificar que los 5 imprescindibles siguen cubiertos
            if is_project and sdd_status["covered_count"] >= sdd_status["total_essentials"]:
                escalation_confirmed = True
                self._log.info("Rama B: ESCALACION CONFIRMADA")
            sdd_status["can_generate"] = escalation_confirmed
        else:
            # Fallback: usar resultado de confirmacion pre-superior
            sdd_status, is_project, obj_sum, mat_sum = build_sdd_status_from_llm(llm_confirm)
            sdd_status["can_generate"] = False

        return result, sdd_status, is_project, escalation_confirmed, mat_sum, obj_sum

    # -----------------------------------------------------------------
    # RAMA A: Flujo normal
    # -----------------------------------------------------------------

    async def _handle_rama_a(self, request, base_prompt, project_context, full_history, loop, regex_result):
        """Modelo rapido + arnes CV2. Boton NUNCA visible.

        Returns: (result, sdd_status, is_project, escalation_confirmed, maturity_summary, objective_summary)
        """
        system_prompt = base_prompt

        # CV2: Inyectar arnes invisible
        try:
            hint = self._deps.sdd_guide.process_message(request.message, request.history or [])
            if hint:
                addition = self._deps.sdd_guide.get_system_prompt_addition(hint)
                if addition:
                    system_prompt = system_prompt + "\n\n" + addition
                    self._log.info("CV2: Arnes inyectado — focus=%s", getattr(hint, 'focus_label', '?'))
        except Exception as e:
            self._log.warning("CV2: Error inyectando arnes: %s", e)

        # Prompt con ultimos 20 mensajes + resumen de aspectos
        aspects_text = self._build_aspects_summary_text(regex_result)
        user_prompt = self._build_recent_prompt(request, full_history, project_context, aspects_text)

        self._log.info("Rama A: Llamando modelo rapido")
        result = await self._call_llm_async("chat", system_prompt, user_prompt, loop)
        self._notify_model(result, "fast")

        # Evaluador LLM solo para seguimiento visual, NO decide boton
        updated_history = full_history + [{"role": "assistant", "content": result.get("content", "")}]
        sdd_status, is_project, obj_sum, mat_sum = await self._evaluate_maturity_async(
            updated_history, result.get("model_used"), loop)

        if sdd_status:
            sdd_status["can_generate"] = False  # Rama A: NUNCA activa boton
        else:
            # Fallback: regex
            sdd_status, is_project, obj_sum, mat_sum = self._fallback_regex_status(updated_history, regex_result)

        if sdd_status is None:
            sdd_status = build_fallback_sdd_status()
            user_text = " ".join(m.get("content", "") for m in full_history if m.get("role") == "user")
            is_project = len(user_text) >= 40
            sdd_status["is_project"] = is_project
            user_msgs = [m.get("content", "") for m in full_history if m.get("role") == "user"]
            obj_sum = user_msgs[0][:200].strip() if user_msgs else ""

        return result, sdd_status, is_project, False, mat_sum, obj_sum

    # -----------------------------------------------------------------
    # Utilidades internas
    # -----------------------------------------------------------------

    def _regex_evaluate(self, full_history):
        """Ejecuta el evaluador regex. Retorna resultado o None."""
        try:
            return self._deps.sdd_evaluator.evaluate(full_history)
        except Exception as e:
            self._log.warning("Error evaluador regex: %s", e)
            return None

    async def _call_llm_async(self, task_type, system_prompt, user_prompt, loop):
        """Llama al LLM en thread pool."""
        return await loop.run_in_executor(
            None,
            lambda: self._deps.call_llm_fn(
                task_type=task_type,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=1000,
                temperature=0.7
            )
        )

    async def _evaluate_maturity_async(self, history, model_used, loop, return_raw=False):
        """Ejecuta el evaluador LLM de madurez. Retorna (sdd_status, is_project, obj_sum, mat_sum) o (raw,)."""
        user_text = " ".join(m.get("content", "") for m in history if m.get("role") == "user")
        if len(user_text) < 80:
            if return_raw:
                return (None,)
            return None, False, "", ""

        try:
            from functools import partial
            raw = await loop.run_in_executor(
                None, partial(self._deps.evaluate_maturity_fn, history, chat_model_used=model_used),
            )
            if return_raw:
                return (raw,)
            if raw:
                return build_sdd_status_from_llm(raw)
        except Exception as e:
            self._log.warning("Error evaluador LLM: %s", e)
        if return_raw:
            return (None,)
        return None, False, "", ""

    def _notify_model(self, result, tier):
        """Notifica al frontend que modelo se uso."""
        try:
            m = result.get('model_used', '?')
            self._deps.notify_fn("chat_model_selected", f"Modelo: {m}", {"model": m, "tier": tier})
        except Exception:
            pass

    def _build_full_prompt(self, request, full_history, project_context):
        """Construye prompt con TODO el historial (para modelo superior)."""
        all_lines = []
        for msg in (request.history or []):
            role_label = "Usuario" if msg.get("role") == "user" else "Asistente"
            all_lines.append(f"{role_label}: {msg.get('content', '')}")
        all_formateado = "\n".join(all_lines) if all_lines else "(Sin historial previo)"

        parts = [f"Historial completo de la conversacion:\n{all_formateado}"]
        if project_context:
            parts.append(project_context.strip())
        parts.append(f"Usuario: {request.message}\nAsistente:")
        return "\n\n".join(parts)

    def _build_recent_prompt(self, request, full_history, project_context, aspects_text):
        """Construye prompt con ultimos 20 mensajes (para modelo rapido)."""
        recent = (request.history or [])[-20:]
        lines = []
        for msg in recent:
            label = "Usuario" if msg.get("role") == "user" else "Asistente"
            lines.append(f"{label}: {msg.get('content', '')}")
        recent_text = "\n".join(lines) if lines else "(Sin historial previo)"

        parts = []
        if aspects_text:
            parts.append(aspects_text)
        parts.append(f"Historial reciente de la conversacion:\n{recent_text}")
        if project_context:
            parts.append(project_context.strip())
        parts.append(f"Usuario: {request.message}\nAsistente:")
        return "\n\n".join(parts)

    def _build_aspects_summary_text(self, regex_result):
        """Construye texto de resumen de aspectos desde resultado regex."""
        if not regex_result or not getattr(regex_result, 'is_project_conversation', False):
            return ""
        lines = ["=== ESTADO DE LA ESPECIFICACION DEL PROYECTO ==="]
        for key, aspect in regex_result.aspects.items():
            cov = aspect.coverage.name if hasattr(aspect.coverage, 'name') else str(aspect.coverage)
            evidence = "; ".join(aspect.evidence[:2]) if aspect.evidence else "sin informacion"
            evidence = evidence[:100]
            mark = "+" if cov == "COVERED" else ("~" if cov == "PARTIAL" else "-")
            lines.append(f"  [{mark}] {aspect.label}: {evidence}")
        return "\n".join(lines)

    def _fallback_regex_status(self, updated_history, regex_result):
        """Construye sdd_status desde resultado regex (fallback)."""
        try:
            mr = self._deps.sdd_evaluator.evaluate(updated_history)
            _prio = {"imprescindible": "imprescindibles", "necesaria": "necesarias", "prescindible": "prescindibles"}
            detail = {"imprescindibles": [], "necesarias": [], "prescindibles": []}
            for key, aspect in mr.aspects.items():
                cov = aspect.coverage.name if hasattr(aspect.coverage, 'name') else str(aspect.coverage)
                ev = "; ".join(aspect.evidence[:2]) if aspect.evidence else ""
                pk = _prio.get(aspect.priority.value, "necesarias") if hasattr(aspect.priority, 'value') else "necesarias"
                if pk in detail:
                    detail[pk].append({"key": key, "label": aspect.label, "status": cov, "evidence": ev[:120]})

            is_proj = mr.is_project_conversation
            sdd = {
                "can_generate": False,
                "is_project": is_proj,
                "maturity": mr.maturity_label,
                "project_confidence": round(mr.project_confidence, 2),
                "covered_count": mr.imprescindibles_covered,
                "total_essentials": mr.imprescindibles_total,
                "necesarias_covered": mr.necesarias_covered,
                "necesarias_total": mr.necesarias_total,
                "prescindibles_covered": mr.prescindibles_covered,
                "prescindibles_total": mr.prescindibles_total,
                "aspects_detail": detail,
            }
            mat_sum = ""
            if is_proj:
                mlines = ["=== ESTADO ==="]
                for mk, ma in mr.aspects.items():
                    mcn = ma.coverage.name if hasattr(ma.coverage, 'name') else str(ma.coverage)
                    mev = "; ".join(ma.evidence[:2]) if ma.evidence else "sin info"
                    mlines.append("  [%s] %s: %s" % ("+" if mcn == "COVERED" else "~" if mcn == "PARTIAL" else "-", ma.label, mev[:100]))
                mat_sum = "\n".join(mlines)
            umsgs = [m.get("content", "") for m in updated_history if m.get("role") == "user"]
            obj = umsgs[0][:200].strip() if umsgs else ""
            if len(umsgs) > 1:
                obj += "..."
            return sdd, is_proj, obj, mat_sum
        except Exception:
            return None, False, "", ""

    def _detect_variant(self, full_history, result_content, project_path):
        """Detecta variante del proyecto (A/B/C). Retorna dict con claves variant, name, path."""
        import re
        out = {}
        all_msgs = full_history + ([{"role": "assistant", "content": result_content}] if result_content else [])
        all_text = " ".join(m.get("content", "") for m in all_msgs).lower()

        b_markers = ["refactori", "mejorar", "extender", "existente", "ya tengo un proyecto",
                      "trabajo en", "proyecto actual", "codigo existente", "migrar", "mantener",
                      "proyecto que ya", "tengo un proyecto", "ya funciona"]
        b_score = sum(1 for m in b_markers if m in all_text)

        if b_score >= 2:
            out["project_variant"] = "B"
        else:
            out["project_variant"] = "A"

        if out["project_variant"] == "A":
            for msg in [m.get("content", "") for m in full_history if m.get("role") == "user"]:
                for pat in [r'(?:ll[ao]mar|nombre)(?:le|lo)?\s+(?:al proyecto\s+)?[\x22\x27]?([\w\-\s]+)[\x22\x27]?',
                          r'(?:proyecto\s+(?:se\s+)?llam[a\xe1]\s+)[\x22\x27]?([\w\-\s]+)[\x22\x27]?']:
                    match = re.search(pat, msg, re.IGNORECASE)
                    if match:
                        out["project_name"] = match.group(1).strip().title()
                        break
                if "project_name" in out:
                    break

        if out.get("project_variant") == "B":
            for msg in [m.get("content", "") for m in full_history if m.get("role") == "user"]:
                paths = re.findall(r'(?:/[\w\-\.\/]+|[A-Za-z]:\\[\w\\\-\.]+)', msg)
                if paths:
                    out["project_path"] = paths[0].strip()
                    if not project_path:
                        out["project_variant"] = "C"
                    break

        if out.get("project_variant") == "B" and project_path:
            p = Path(project_path.strip())
            if p.exists() and p.is_dir():
                out["project_path"] = project_path

        return out


# ========================================================================
# VALIDACION AUTONOMA
# ========================================================================

class _MockRequest:
    """Request simulado para tests."""
    def __init__(self, message, history=None, project_path=None, is_escalated=False):
        self.message = message
        self.history = history or []
        self.project_path = project_path
        self.is_escalated = is_escalated


class _MockRegexResult:
    """Resultado del evaluador regex simulado."""
    def __init__(self, is_project=True, can_generate=False, imp_covered=0):
        self.is_project_conversation = is_project
        self.can_generate_project = can_generate
        self.imprescindibles_covered = imp_covered
        self.imprescindibles_total = 5
        self.necesarias_covered = 0
        self.necesarias_total = 8
        self.prescindibles_covered = 0
        self.prescindibles_total = 5
        self.project_confidence = 1.0 if is_project else 0.0
        self.maturity_label = "intermedio"
        self.aspects = {}


class _MockGuide:
    """SDDGuide simulado."""
    def process_message(self, msg, hist):
        return None
    def get_system_prompt_addition(self, hint):
        return "[ARNES CV2 SIMULADO]"


def _make_all_covered_aspects():
    """Retorna dict con los 5 imprescindibles en 'covered' y el resto 'not_covered'."""
    aspects = {}
    for group in ASPECTS_FOR_LLM.values():
        for key, _ in group:
            aspects[key] = "covered" if key in IMP_KEYS else "not_covered"
    return aspects


def _make_partial_aspects(covered_keys):
    """Retorna dict con solo las keys indicadas en 'covered'."""
    aspects = {}
    for group in ASPECTS_FOR_LLM.values():
        for key, _ in group:
            aspects[key] = "covered" if key in covered_keys else "not_covered"
    return aspects


def _make_deps(**overrides):
    """Crea ChatDependencies con mocks por defecto, sobreescribiendo lo que se pase."""
    import types

    # Evaluador regex mock
    regex_result = overrides.pop("regex_result", _MockRegexResult(is_project=True, can_generate=False, imp_covered=2))
    evaluator = types.SimpleNamespace(evaluate=lambda h, _rr=regex_result: _rr)

    # LLM maturity mock
    maturity_result = overrides.pop("maturity_result", {"is_project": True, "objective_summary": "Test", "aspects": _make_partial_aspects(["what_is", "problem"])
        })
    evaluate_fn = lambda h, chat_model_used=None, _mr=maturity_result: _mr

    # call_llm mock
    llm_response = overrides.pop("llm_response", {"success": True, "content": "Respuesta de prueba", "model_used": "test/model", "error": None})
    _llm_resp = llm_response
    call_fn = lambda **kw: _llm_resp

    log = logging.getLogger("test_chat_flow")
    log.setLevel(logging.DEBUG)

    deps = ChatDependencies(
        sdd_evaluator=evaluator,
        sdd_guide=_MockGuide(),
        evaluate_maturity_fn=evaluate_fn,
        call_llm_fn=call_fn,
        notify_fn=lambda *a, **k: None,
        logger=log,
    )
    return deps


# --- Tests ---

async def _test_rama_c_boton_visible():
    """Rama C: el boton SIEMPRE debe estar visible."""
    deps = _make_deps()
    mgr = ChatSDDFlowManager(deps)
    req = _MockRequest("Hola", history=[{"role": "user", "content": "Quiero una app de tareas"} for _ in range(5)], is_escalated=True)
    result = await mgr.process(req, "self context", "")
    assert result["sdd_status"]["can_generate"] is True, f"can_generate deberia ser True en Rama C, fue {result['sdd_status']['can_generate']}"
    assert result.get("escalation_confirmed") != True, "escalation_confirmed no deberia estar en Rama C"
    return "PASS"


async def _test_rama_a_boton_nunca_visible():
    """Rama A: el boton NUNCA debe estar visible."""
    deps = _make_deps()  # regex can_generate=False por defecto
    mgr = ChatSDDFlowManager(deps)
    req = _MockRequest("Quiero una app", history=[{"role": "user", "content": "Quiero una app de gestion"}])
    result = await mgr.process(req, "self context", "")
    assert result["sdd_status"]["can_generate"] is False, f"can_generate deberia ser False en Rama A, fue {result['sdd_status']['can_generate']}"
    assert result.get("escalation_confirmed") != True, "No deberia haber escalacion en Rama A"
    return "PASS"


async def _test_rama_b_escalacion_confirmada():
    """Rama B: regex 5/5, LLM confirma 5/5, post-superior confirma -> boton visible."""
    all_cov = _make_all_covered_aspects()
    deps = _make_deps(
        regex_result=_MockRegexResult(is_project=True, can_generate=True, imp_covered=5),
        maturity_result={"is_project": True, "objective_summary": "App madura", "aspects": all_cov},
    )
    mgr = ChatSDDFlowManager(deps)
    req = _MockRequest("Ya tengo todo definido", history=[
        {"role": "user", "content": "Es una app de tareas para equipos"},
        {"role": "user", "content": "Resuelve que los equipos pierden seguimiento"},
        {"role": "user", "content": "Tiene CRUD de tareas, notificaciones, calendario"},
        {"role": "user", "content": "No hace facturacion ni contabilidad"},
        {"role": "user", "content": "Te logueas, creas proyecto, agregas tareas, asignas"},
    ])
    result = await mgr.process(req, "self context", "")
    assert result.get("escalation_confirmed") is True, f"escalation_confirmed deberia ser True, fue {result.get('escalation_confirmed')}"
    assert result["sdd_status"]["can_generate"] is True, f"can_generate deberia ser True tras escalacion confirmada"
    return "PASS"


async def _test_rama_b_llm_desestima_cae_a_a():
    """Rama B: regex 5/5 pero LLM dice que no -> cae a Rama A, boton no visible."""
    partial_cov = _make_partial_aspects(["what_is", "problem", "features"])  # solo 3/5
    deps = _make_deps(
        regex_result=_MockRegexResult(is_project=True, can_generate=True, imp_covered=5),
        maturity_result={"is_project": True, "objective_summary": "Incompleto", "aspects": partial_cov},
    )
    mgr = ChatSDDFlowManager(deps)
    req = _MockRequest("Algo", history=[{"role": "user", "content": "Texto de prueba"} for _ in range(10)])
    result = await mgr.process(req, "self context", "")
    assert result.get("escalation_confirmed") is not True, "No deberia haber escalacion si LLM desestimo"
    assert result["sdd_status"]["can_generate"] is False, "Boton no deberia ser visible"
    return "PASS"


async def _test_sdd_status_siempre_presente():
    """Todas las ramas deben devolver sdd_status."""
    for label, req in [
        ("Rama A", _MockRequest("Test", history=[{"role": "user", "content": "Texto " * 20}], is_escalated=False)),
        ("Rama C", _MockRequest("Test", history=[{"role": "user", "content": "Texto " * 20}], is_escalated=True)),
    ]:
        deps = _make_deps()
        mgr = ChatSDDFlowManager(deps)
        result = await mgr.process(req, "self context", "")
        assert "sdd_status" in result and result["sdd_status"] is not None, f"{label}: sdd_status falta"
    return "PASS"


async def _test_variant_a_detectada():
    """Texto sin marcadores de refactorizacion -> variante A."""
    deps = _make_deps()
    mgr = ChatSDDFlowManager(deps)
    req = _MockRequest("Quiero crear una app nueva", history=[{"role": "user", "content": "Crear un sistema de inventario desde cero"}])
    result = await mgr.process(req, "self context", "")
    assert result.get("project_variant") == "A", f"Deberia ser variante A, fue {result.get('project_variant')}"
    return "PASS"


async def _test_build_sdd_status_from_llm():
    """La funcion build_sdd_status_from_llm produce estructura correcta."""
    all_cov = _make_all_covered_aspects()
    llm_result = {"is_project": True, "objective_summary": "Test", "aspects": all_cov}
    sdd, is_proj, obj, mat = build_sdd_status_from_llm(llm_result)
    assert sdd["can_generate"] is True, "5/5 covered -> can_generate True"
    assert sdd["covered_count"] == 5, f"Deberia ser 5, fue {sdd['covered_count']}"
    assert sdd["total_essentials"] == 5
    assert is_proj is True
    return "PASS"


async def _test_build_fallback():
    """build_fallback_sdd_status tiene estructura valida y can_generate=False."""
    sdd = build_fallback_sdd_status()
    assert sdd["can_generate"] is False
    assert sdd["covered_count"] == 0
    assert "imprescindibles" in sdd["aspects_detail"]
    assert len(sdd["aspects_detail"]["imprescindibles"]) == 5
    return "PASS"


async def _test_all_imp_covered_util():
    """all_imp_covered y count_imp_covered funcionan correctamente."""
    assert all_imp_covered(_make_all_covered_aspects()) is True
    assert all_imp_covered(_make_partial_aspects(["what_is"])) is False
    assert count_imp_covered(_make_all_covered_aspects()) == 5
    assert count_imp_covered(_make_partial_aspects(["what_is", "problem"])) == 2
    return "PASS"


async def _test_rama_b_superior_quita_madurez():
    """Rama B: LLM confirma 5/5 pero superior hace preguntas que cambian aspectos -> no confirmado."""
    pre_cov = _make_all_covered_aspects()  # Pre-escalacion: 5/5
    post_cov = _make_partial_aspects(["what_is", "problem", "features", "limits"])  # Post: 4/5

    call_count = [0]
    def alternating_maturity(h, chat_model_used=None):
        call_count[0] += 1
        if call_count[0] == 1:
            return {"is_project": True, "objective_summary": "Pre", "aspects": pre_cov}
        else:
            return {"is_project": True, "objective_summary": "Post", "aspects": post_cov}

    deps = _make_deps(
        regex_result=_MockRegexResult(is_project=True, can_generate=True, imp_covered=5),
    )
    deps = ChatDependencies(
        sdd_evaluator=deps.sdd_evaluator,
        sdd_guide=deps.sdd_guide,
        evaluate_maturity_fn=alternating_maturity,
        call_llm_fn=deps.call_llm_fn,
        notify_fn=deps.notify_fn,
        logger=deps.logger,
    )
    mgr = ChatSDDFlowManager(deps)
    req = _MockRequest("Test", history=[{"role": "user", "content": "Texto " * 20}])
    result = await mgr.process(req, "self context", "")
    assert result.get("escalation_confirmed") is not True, "No deberia confirmar si superior quito madurez"
    return "PASS"


TESTS = [
 ("Rama C: boton siempre visible", _test_rama_c_boton_visible),
    ("Rama A: boton nunca visible", _test_rama_a_boton_nunca_visible),
    ("Rama B: escalacion confirmada", _test_rama_b_escalacion_confirmada),
    ("Rama B: LLM desestima -> Rama A", _test_rama_b_llm_desestima_cae_a_a),
    ("sdd_status siempre presente", _test_sdd_status_siempre_presente),
    ("Variante A detectada", _test_variant_a_detectada),
    ("build_sdd_status_from_llm", _test_build_sdd_status_from_llm),
    ("build_fallback_sdd_status", _test_build_fallback),
    ("all_imp_covered util", _test_all_imp_covered_util),
    ("Rama B: superior quita madurez", _test_rama_b_superior_quita_madurez),
]


async def _run_all_tests():
    """Ejecuta todos los tests y reporta resultados."""
    passed = 0
    failed = 0
    errors = 0

    print("=" * 60)
    print("VALIDACION AUTONOMA: chat_sdd_flow.py")
    print("=" * 60)

    for name, test_fn in TESTS:
        try:
            result = await test_fn()
            if result == "PASS":
                print(f"  [PASS] {name}")
                passed += 1
            else:
                print(f"  [FAIL] {name}: {result}")
                failed += 1
        except AssertionError as e:
            print(f"  [FAIL] {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"  [ERROR] {name}: {type(e).__name__}: {e}")
            errors += 1

    print("-" * 60)
    total = passed + failed + errors
    print(f"Resultado: {passed}/{total} pasaron, {failed} fallaron, {errors} errores")
    print("=" * 60)
    return failed == 0 and errors == 0


if __name__ == "__main__":
    ok = asyncio.run(_run_all_tests())
    exit(0 if ok else 1)
