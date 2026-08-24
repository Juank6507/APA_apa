"""
sdd_maturity_llm.py — Evaluacion de madurez del SDD via LLM.

Funcionalidad extraida de app.py (CORR-L).
Contiene la logica para evaluar la madurez de una conversacion usando el LLM,
incluyendo desescalado local, rotacion por pool, y parseo de resultados.
"""
import json
import re
import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

_MATURITY_SYSTEM_PROMPT = (
    "Eres un evaluador de especificaciones de software. Tu UNICA tarea es analizar "
    "una conversacion y determinar: (1) si describe un proyecto de software, "
    "(2) que aspectos de la especificacion estan cubiertos, y (3) un resumen del objetivo. "
    "Responde UNICAMENTE con JSON valido, sin texto adicional, sin markdown, sin bloques de codigo."
)

_ASPECTS_FOR_LLM = {
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

def _build_maturity_prompt(conversation_history: list) -> str:
    conv_lines = []
    for msg in conversation_history:
        role = "Usuario" if msg.get("role") == "user" else "Asistente"
        content = msg.get("content", "")
        if len(content) > 600:
            content = content[:600] + "..."
        conv_lines.append(role + ": " + content)
    conversation = "\n\n".join(conv_lines)

    aspects_text = []
    for category, aspects in _ASPECTS_FOR_LLM.items():
        aspects_text.append("  " + category + ":")
        for key, desc in aspects:
            aspects_text.append('    "' + key + '": "' + desc + '"')
    aspects_block = "\n".join(aspects_text)

    prompt = (
        "ANALIZA ESTA CONVERSACION y evalua la madurez de la especificacion.\n\n"
        "CONVERSACION:\n" + conversation + "\n\n"
        "ASPECTOS A EVALUAR (18 en total):\n" + aspects_block + "\n\n"
        "CRITERIOS:\n"
        '- "covered": El aspecto tiene informacion suficiente y especifica.\n'
        '- "partial": Se menciono pero es vago o incompleto.\n'
        '- "not_covered": No se ha mencionado.\n\n'
        '"is_project" debe ser false si NO describe ningun proyecto de software.\n\n'
        "Responde SOLO con JSON valido (sin markdown):\n"
        '{\n'
        '  "is_project": true o false,\n'
        '  "objective_summary": "Resumen de 1-2 frases del objetivo, vacio si no es proyecto",\n'
        '  "aspects": {\n'
        '    "what_is": "covered" o "partial" o "not_covered",\n'
        '    "problem": "covered" o "partial" o "not_covered",\n'
        '    "features": "covered" o "partial" o "not_covered",\n'
        '    "limits": "covered" o "partial" o "not_covered",\n'
        '    "usage": "covered" o "partial" o "not_covered",\n'
        '    "similar_existing": "covered" o "partial" o "not_covered",\n'
        '    "stakeholders": "covered" o "partial" o "not_covered",\n'
        '    "constraints": "covered" o "partial" o "not_covered",\n'
        '    "success_criteria": "covered" o "partial" o "not_covered",\n'
        '    "integrations": "covered" o "partial" o "not_covered",\n'
        '    "states": "covered" o "partial" o "not_covered",\n'
        '    "invariants": "covered" o "partial" o "not_covered",\n'
        '    "edge_cases": "covered" o "partial" o "not_covered",\n'
        '    "alternatives": "covered" o "partial" o "not_covered",\n'
        '    "timeline": "covered" o "partial" o "not_covered",\n'
        '    "cross_team_impact": "covered" o "partial" o "not_covered",\n'
        '    "testing_approach": "covered" o "partial" o "not_covered",\n'
        '    "open_questions": "covered" o "partial" o "not_covered"\n'
        '  }\n'
        '}'
    )
    return prompt


def _evaluate_maturity_with_llm(conversation_history: list, chat_model_used: str = None):
    """Evalua madurez del SDD usando el LLM. Retorna dict o None.

    Arquitectura Model Broker: usa call_llm(task_type="chat", ...)
    que ya maneja seleccion de modelo, fallback y emergency harness.
    Reintenta hasta 3 veces con task_type="chat", luego 2 con "analysis".
    """
    try:
        prompt = _build_maturity_prompt(conversation_history)
        messages = [
            {"role": "system", "content": _MATURITY_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        from core.router import call_llm

        # Reintentos: primero con chat, luego con analysis como fallback
        task_sequence = ["chat"] * 3 + ["analysis"] * 2
        for task_type in task_sequence:
            try:
                result = call_llm(
                    task_type=task_type,
                    system_prompt=_MATURITY_SYSTEM_PROMPT,
                    user_prompt=prompt,
                    max_tokens=900,
                    temperature=0.1,
                    messages=messages,
                )
                if result.get("success"):
                    return _parse_maturity_result(result)
            except Exception:
                continue

        logger.warning("CORR-L: Maturity desescalado agotado (5 intentos)")
        return None

    except Exception as e:
        logger.warning("CORR-L: Error en evaluacion de madurez: %s", e, exc_info=True)
        return None


# --- Funciones de pool eliminadas ---
# _find_pool_entry_for_maturity, _get_next_maturity_candidate, _call_maturity_direct
# fueron eliminadas porque core/providers.py no existe (Fase 3 cleanup).
# Toda la logica de routing ahora vive en core/router.py via call_llm().
# La funcion _evaluate_maturity_with_llm usa call_llm directamente.


def _parse_maturity_result(result: dict):
    """Parsea y valida el resultado JSON de madurez. Retorna dict o None."""
    import json as _json
    try:
        content = result.get("content", "").strip()
        # Limpiar markdown
        if content.startswith("```"):
            lines = content.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            content = "\n".join(lines).strip()

        parsed = _json.loads(content)
        if not isinstance(parsed.get("is_project"), bool):
            return None
        if not isinstance(parsed.get("aspects"), dict):
            return None

        # Validar 18 keys
        expected_keys = set()
        for aspects in _ASPECTS_FOR_LLM.values():
            for key, _ in aspects:
                expected_keys.add(key)
        for k in expected_keys - parsed["aspects"].keys():
            parsed["aspects"][k] = "not_covered"

        # Normalizar valores
        valid = {"covered", "partial", "not_covered"}
        for key in expected_keys:
            val = str(parsed["aspects"].get(key, "not_covered")).lower()
            parsed["aspects"][key] = val if val in valid else "not_covered"

        covered_aspects = {k: v for k, v in parsed["aspects"].items() if v != "not_covered"}
        logger.info("CORR-L: LLM maturity — is_project=%s, covered=%s", parsed["is_project"], covered_aspects)

        return {
            "is_project": parsed["is_project"],
            "objective_summary": parsed.get("objective_summary", "") or "",
            "aspects": parsed["aspects"],
        }
    except _json.JSONDecodeError as e:
        logger.warning("CORR-L: JSON parse error: %s", e)
        # Ultimo recurso: extraer JSON con regex
        try:
            raw = result.get("content", "")
            import re
            m = re.search(r'\{[\s\S]*\}', raw)
            if m:
                parsed = _json.loads(m.group())
                if isinstance(parsed.get("is_project"), bool) and isinstance(parsed.get("aspects"), dict):
                    logger.info("CORR-L: Recovered JSON via regex")
                    return {
                        "is_project": parsed["is_project"],
                        "objective_summary": parsed.get("objective_summary", "") or "",
                        "aspects": parsed["aspects"],
                    }
        except Exception:
            pass
        return None


def _build_sdd_status_from_llm(llm_result: dict):
    """Construye sdd_status desde resultado del LLM.
    Retorna (sdd_status, is_project, objective_summary, maturity_summary)
    """
    aspects = llm_result["aspects"]
    is_project = llm_result["is_project"]
    objective_summary = llm_result["objective_summary"]

    aspects_detail = {"imprescindibles": [], "necesarias": [], "prescindibles": []}
    for category, cat_aspects in _ASPECTS_FOR_LLM.items():
        prio_key = category.lower()
        for key, label_desc in cat_aspects:
            label = label_desc.split(" — ")[0]
            status = aspects.get(key, "not_covered").upper()
            entry = {"key": key, "label": label, "status": status, "evidence": ""}
            if prio_key in aspects_detail:
                aspects_detail[prio_key].append(entry)

    imp_covered = sum(1 for k, _ in _ASPECTS_FOR_LLM["IMPRESCINDIBLES"] if aspects.get(k) == "covered")
    imp_total = len(_ASPECTS_FOR_LLM["IMPRESCINDIBLES"])
    nec_covered = sum(1 for k, _ in _ASPECTS_FOR_LLM["NECESARIAS"] if aspects.get(k) == "covered")
    nec_total = len(_ASPECTS_FOR_LLM["NECESARIAS"])
    pre_covered = sum(1 for k, _ in _ASPECTS_FOR_LLM["PRESCINDIBLES"] if aspects.get(k) == "covered")
    pre_total = len(_ASPECTS_FOR_LLM["PRESCINDIBLES"])

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
    for category, cat_aspects in _ASPECTS_FOR_LLM.items():
        msum_lines.append("\n--- " + category + " ---")
        for key, label_desc in cat_aspects:
            label = label_desc.split(" — ")[0]
            val = aspects.get(key, "not_covered")
            mark = "+" if val == "covered" else ("~" if val == "partial" else "-")
            msum_lines.append("  [" + mark + "] " + label + ": " + val)
    maturity_summary = "\n".join(msum_lines)

    return sdd_status, is_project, objective_summary, maturity_summary



# =====================================================================
# TESTS AUTONOMOS
# =====================================================================
if __name__ == "__main__":
    import sys
    passed = 0
    failed = 0

    def _check(name, condition):
        global passed, failed
        if condition:
            print(f"  [PASS] {name}")
            passed += 1
        else:
            print(f"  [FAIL] {name}")
            failed += 1

    print("=" * 60)
    print("TESTS AUTONOMOS: sdd_maturity_llm.py")
    print("=" * 60)

    # Test 1: ASPECTS_FOR_LLM tiene 18 aspectos
    total_aspects = sum(len(v) for v in _ASPECTS_FOR_LLM.values())
    _check("18 aspectos totales", total_aspects == 18)
    _check("5 imprescindibles", len(_ASPECTS_FOR_LLM["IMPRESCINDIBLES"]) == 5)
    _check("8 necesarias", len(_ASPECTS_FOR_LLM["NECESARIAS"]) == 8)
    _check("5 prescindibles", len(_ASPECTS_FOR_LLM["PRESCINDIBLES"]) == 5)

    # Test 2: _build_maturity_prompt genera prompt con aspectos
    conv = [{"role": "user", "content": "Quiero una app de tareas"}]
    prompt = _build_maturity_prompt(conv)
    _check("prompt contiene conversacion", "Quiero una app de tareas" in prompt)
    _check("prompt contiene aspectos", "IMPRESCINDIBLES" in prompt)
    _check("prompt contiene what_is", 'what_is' in prompt)
    _check("prompt pide JSON", 'JSON' in prompt)

    # Test 3: _parse_maturity_result con resultado valido
    valid_result = {
        "content": '{"is_project": true, "objective_summary": "App de tareas", "aspects": {"what_is": "covered", "problem": "covered", "features": "covered", "limits": "not_covered", "usage": "not_covered", "similar_existing": "not_covered", "stakeholders": "not_covered", "constraints": "not_covered", "success_criteria": "not_covered", "integrations": "not_covered", "states": "not_covered", "invariants": "not_covered", "edge_cases": "not_covered", "alternatives": "not_covered", "timeline": "not_covered", "cross_team_impact": "not_covered", "testing_approach": "not_covered", "open_questions": "not_covered"}}'
    }
    parsed = _parse_maturity_result(valid_result)
    _check("parse resultado valido", parsed is not None)
    _check("parse is_project correcto", parsed["is_project"] is True)
    _check("parse objective_summary", parsed["objective_summary"] == "App de tareas")
    _check("parse what_is covered", parsed["aspects"]["what_is"] == "covered")

    # Test 4: _parse_maturity_result con markdown
    md_content = '\n'.join([
        '```json',
        '{"is_project": false, "objective_summary": "", "aspects": {"what_is": "not_covered", "problem": "not_covered", "features": "not_covered", "limits": "not_covered", "usage": "not_covered", "similar_existing": "not_covered", "stakeholders": "not_covered", "constraints": "not_covered", "success_criteria": "not_covered", "integrations": "not_covered", "states": "not_covered", "invariants": "not_covered", "edge_cases": "not_covered", "alternatives": "not_covered", "timeline": "not_covered", "cross_team_impact": "not_covered", "testing_approach": "not_covered", "open_questions": "not_covered"}}',
        '```',
    ])
    md_result = {"content": md_content}
    parsed = _parse_maturity_result(md_result)
    _check("parse con markdown", parsed is not None and parsed["is_project"] is False)

    # Test 5: _parse_maturity_result con JSON invalido
    invalid_result = {"content": "no es json"}
    parsed = _parse_maturity_result(invalid_result)
    _check("parse JSON invalido retorna None", parsed is None)

    # Test 6: _build_sdd_status_from_llm
    llm_result = {
        "is_project": True,
        "objective_summary": "App de gestion de tareas pendientes",
        "aspects": {
            "what_is": "covered", "problem": "covered", "features": "covered", "limits": "covered", "usage": "covered",
            "similar_existing": "covered", "stakeholders": "covered", "constraints": "covered", "success_criteria": "covered",
            "integrations": "covered", "states": "covered", "invariants": "covered", "edge_cases": "covered",
            "alternatives": "covered", "timeline": "not_covered", "cross_team_impact": "not_covered",
            "testing_approach": "not_covered", "open_questions": "not_covered",
        }
    }
    sdd_status, is_project, obj_summary, maturity_summary = _build_sdd_status_from_llm(llm_result)
    _check("sdd_status can_generate True", sdd_status["can_generate"] is True)
    _check("sdd_status maduro", sdd_status["maturity"] == "maduro")
    _check("sdd_status 5/5 imprescindibles", sdd_status["covered_count"] == 5)
    _check("sdd_status 8/8 necesarias", sdd_status["necesarias_covered"] == 8)
    _check("objective_summary correcto", obj_summary == "App de gestion de tareas pendientes")
    _check("maturity_summary tiene marcas", "+" in maturity_summary)

    # Test 7: _build_sdd_status_from_llm con partial
    llm_result2 = {
        "is_project": True, "objective_summary": "App", "aspects": {
            "what_is": "covered", "problem": "covered", "features": "covered", "limits": "not_covered", "usage": "not_covered",
            "similar_existing": "partial", "stakeholders": "not_covered", "constraints": "not_covered", "success_criteria": "not_covered",
            "integrations": "not_covered", "states": "not_covered", "invariants": "not_covered", "edge_cases": "not_covered",
            "alternatives": "not_covered", "timeline": "not_covered", "cross_team_impact": "not_covered",
            "testing_approach": "not_covered", "open_questions": "not_covered",
        }
    }
    sdd2, _, _, _ = _build_sdd_status_from_llm(llm_result2)
    _check("3/5 imprescindibles intermedio", sdd2["covered_count"] == 3)
    _check("maturity intermedio", sdd2["maturity"] == "intermedio")
    _check("can_generate False (3/5)", sdd2["can_generate"] is False)

    # Test 8: _build_sdd_status_from_llm no proyecto
    llm_result3 = {
        "is_project": False, "objective_summary": "", "aspects": {
            k: "not_covered" for k in [a for g in _ASPECTS_FOR_LLM.values() for a, _ in g]
        }
    }
    sdd3, is_p, _, _ = _build_sdd_status_from_llm(llm_result3)
    _check("no proyecto can_generate False", sdd3["can_generate"] is False)
    _check("no proyecto is_project False", is_p is False)

    print("-" * 60)
    total = passed + failed
    print(f"Resultado: {passed}/{total} pasaron")
    print("=" * 60)
    sys.exit(0 if failed == 0 else 1)
