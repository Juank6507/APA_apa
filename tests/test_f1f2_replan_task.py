# apa/tests/test_f1f2_replan_task.py
# F1+F2: Replanificación de tareas fallidas (adaptado a Planner OOP).
# Verifica que:
#   1. Planner.replan_task() devuelve tarea de reemplazo válida
#   2. Planner.replan_task() con LLM vacío devuelve tarea fallback
#   3. Planner.replan_task() con LLM que falla devuelve tarea fallback
#   4. Planner.replan_task() preserva original_task_id y replan_reason
#   5. Orchestrator._handle_task_replan() inserta tareas y redirige dependencias
#   6. Orchestrator._handle_task_replan() maneja fallo del planner
#   7. Tareas con attempts < 3 NO se replanifican
#   8. "replanned" cuenta como completado en el resultado final
#   9. Tareas replanned desbloquean sus dependientes

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
from unittest.mock import patch, MagicMock

from config.settings import settings

PASS = 0
FAIL = 0


def report(test_name: str, ok: bool, detail: str = ""):
    global PASS, FAIL
    if ok:
        PASS += 1
    else:
        FAIL += 1
        print(f"  ✗ {test_name} — {detail}")


def _make_task(task_id="T1", name="tarea test", attempts=0, deps=None):
    """Crea una tarea de prueba con los campos necesarios."""
    return {
        "id": task_id,
        "name": name,
        "description": "Descripción de prueba",
        "inputs": [],
        "expected_output": "output",
        "acceptance_criterion": "criterio",
        "task_type": "generation",
        "depends_on": deps or [],
        "status": "pending",
        "attempts": attempts,
        "result": None,
        "model_used": None,
        "language": "python"
    }


def _make_plan(project_id="test-proj", tasks=None, summary="Objetivo test"):
    """Crea un plan de prueba."""
    return {
        "project_id": project_id,
        "spec_summary": summary,
        "tasks": tasks or []
    }


def _mock_call_llm_json(content_json: dict):
    """Crea un mock de core.router.call_llm que devuelve JSON string."""
    def mock_call_llm(*args, **kwargs):
        return json.dumps(content_json)
    return mock_call_llm


def _mock_call_llm_empty(*args, **kwargs):
    """Mock que devuelve string vacío (LLM no respondió)."""
    return ""


def _mock_call_llm_error(*args, **kwargs):
    """Mock que lanza excepción (LLM caído)."""
    raise ConnectionError("Modelo no disponible")


# ─── Tests directos de Planner.replan_task() ─────────────────────────────


def test_replan_task_returns_valid_task():
    """Planner.replan_task() con LLM válido devuelve tarea de reemplazo."""
    from core.planner import Planner

    planner = Planner(settings)

    mock_response = {
        "task": {
            "id": "T3",
            "name": "Tarea corregida",
            "description": "Versión simplificada",
            "dependencies": [],
            "inputs": [],
            "output": "Código corregido",
            "acceptance_criteria": "Compila y pasa tests",
            "task_type": "code_generation",
            "programming_language": "python",
            "executor": "apa",
            "priority": "high",
        }
    }

    with patch("core.router.call_llm", _mock_call_llm_json(mock_response)):
        result = planner.replan_task("test-proj", "T3", "Error de compilación")

    report("replan_task retorna dict", isinstance(result, dict))
    report("Tiene clave 'task'", "task" in result)
    report("Tiene original_task_id",
           result.get("original_task_id") == "T3",
           f"obtenido: {result.get('original_task_id')}")
    report("Tiene replan_reason",
           result.get("replan_reason") == "Error de compilación")
    report("La tarea tiene ID correcto",
           result["task"].get("id") == "T3",
           f"obtenido: {result['task'].get('id')}")
    report("La tarea tiene nombre",
           len(result["task"].get("name", "")) > 0)
    report("La tarea tiene campos obligatorios",
           all(f in result["task"] for f in [
               "id", "name", "description", "dependencies",
               "inputs", "output", "acceptance_criteria",
               "task_type", "programming_language", "executor", "priority"
           ]))


def test_replan_task_llm_empty_response():
    """Planner.replan_task() con LLM vacío devuelve tarea fallback."""
    from core.planner import Planner

    planner = Planner(settings)

    with patch("core.router.call_llm", _mock_call_llm_empty):
        result = planner.replan_task("test-proj", "T5", "Error")

    report("replan_task retorna dict con LLM vacío", isinstance(result, dict))
    report("Tiene tarea fallback",
           "task" in result and isinstance(result["task"], dict))
    report("Fallback tiene ID correcto",
           result["task"].get("id") == "T5",
           f"obtenido: {result['task'].get('id')}")
    report("Tiene original_task_id",
           result.get("original_task_id") == "T5")


def test_replan_task_llm_exception():
    """Planner.replan_task() con LLM que lanza excepción devuelve tarea fallback."""
    from core.planner import Planner

    planner = Planner(settings)

    with patch("core.router.call_llm", _mock_call_llm_error):
        result = planner.replan_task("test-proj", "T6", "Error de conexión")

    report("replan_task retorna dict con excepción", isinstance(result, dict))
    report("Tiene tarea fallback con excepción",
           "task" in result and isinstance(result["task"], dict))
    report("Fallback tiene ID",
           result["task"].get("id") == "T6",
           f"obtenido: {result['task'].get('id')}")


def test_replan_task_preserves_metadata():
    """Planner.replan_task() preserva original_task_id y replan_reason."""
    from core.planner import Planner

    planner = Planner(settings)

    mock_response = {
        "task": {
            "id": "T7",
            "name": "Tarea replanificada",
            "description": "Nueva versión",
            "task_type": "code_generation",
            "programming_language": "python",
        }
    }

    with patch("core.router.call_llm", _mock_call_llm_json(mock_response)):
        result = planner.replan_task("proj-123", "T7", "Fallo tras 3 intentos")

    report("original_task_id preservado",
           result["original_task_id"] == "T7",
           f"obtenido: {result['original_task_id']}")
    report("replan_reason preservado",
           result["replan_reason"] == "Fallo tras 3 intentos",
           f"obtenido: {result['replan_reason']}")


# ─── Tests de integración con Orchestrator ───────────────────────────────


def test_handle_replan_replaced():
    """Orchestrator._handle_task_replan() inserta tarea y redirige dependencias."""
    from core.orchestrator import Orchestrator

    task = _make_task("T2", "tarea que falla", deps=["T1"])
    task["status"] = "failed"
    task["result"] = {
        "success": False,
        "attempts_used": 3,
        "diagnosis": "Corrección fallida 3 veces",
        "code": "bad code",
        "filename": "bad.py"
    }

    t1 = _make_task("T1", "tarea previa")
    t1["status"] = "completed"
    t1["result"] = {"code": "ok", "filename": "t1.py"}

    t3 = _make_task("T3", "tarea dependiente", deps=["T2"])

    plan = _make_plan(tasks=[t1, task, t3])
    completed_tasks = {"T1": t1["result"]}

    mock_replacement_task = {
        "id": "T2_r1",
        "name": "Tarea corregida",
        "description": "Versión corregida",
        "dependencies": [],
        "inputs": [],
        "output": "output",
        "acceptance_criteria": "ok",
        "task_type": "code_generation",
        "programming_language": "python",
        "executor": "apa",
        "priority": "high",
    }

    orch = Orchestrator()
    events = []

    def mock_replan(project_id, task_id, reason):
        return {
            "task": mock_replacement_task,
            "original_task_id": task_id,
            "replan_reason": reason,
        }

    with patch.object(orch._planner, "replan_task", mock_replan):
        ok = orch._handle_task_replan(
            task, task["result"], plan, completed_tasks,
            on_progress=lambda e: events.append(e)
        )

    report("Replan exitoso en orchestrator", ok is True)
    report("Tarea original marcada como 'replanned'",
           task["status"] == "replanned",
           f"obtenido: {task['status']}")
    report("T2_r1 insertada en el plan",
           any(t["id"] == "T2_r1" for t in plan["tasks"]))
    report("T3 ahora depende de T2_r1",
           "T2_r1" in t3.get("depends_on", []),
           f"deps: {t3.get('depends_on')}")
    report("T2 en completed_tasks (desbloqueada)",
           "T2" in completed_tasks)
    report("Evento task_replanned emitido",
           any(e.get("type") == "task_replanned" for e in events))


def test_handle_replan_planner_fails():
    """Orchestrator._handle_task_replan() maneja fallo del planner."""
    from core.orchestrator import Orchestrator

    task = _make_task("T2", "tarea que falla", deps=["T1"])
    task["status"] = "failed"
    task["result"] = {
        "success": False,
        "attempts_used": 3,
        "diagnosis": "No tiene sentido",
        "code": "",
        "filename": ""
    }

    t3 = _make_task("T3", "tarea dependiente", deps=["T2"])
    plan = _make_plan(tasks=[task, t3])
    completed_tasks = {}

    orch = Orchestrator()
    events = []

    def mock_replan_empty(project_id, task_id, reason):
        # Simula que el planner no pudo generar tarea
        return {"task": None, "original_task_id": task_id, "replan_reason": reason}

    with patch.object(orch._planner, "replan_task", mock_replan_empty):
        ok = orch._handle_task_replan(
            task, task["result"], plan, completed_tasks,
            on_progress=lambda e: events.append(e)
        )

    report("Replan fallido cuando planner devuelve None",
           ok is False,
           f"obtenido: {ok}")
    report("Tarea sigue como failed (no replanned)",
           task["status"] != "replanned",
           f"obtenido: {task['status']}")


def test_no_replan_under_3_attempts():
    """Una tarea con attempts < 3 NO se replanifica (queda como failed)."""
    from core.orchestrator import Orchestrator

    t1 = _make_task("T1", "previa")
    t1["status"] = "completed"
    t1["result"] = {"code": "ok", "filename": "t1.py"}

    t2 = _make_task("T2", "falla temprano", deps=["T1"])
    t2["status"] = "pending"

    plan = _make_plan(tasks=[t1, t2])

    orch = Orchestrator()
    orch.current_plan = plan
    orch.project_id = "test-no-replan"

    events = []

    def mock_run_task(task):
        return {
            "success": False,
            "code": "",
            "filename": "",
            "criterion_passed": False,
            "attempts_used": 1,
            "model_used": None,
            "diagnosis": "Fallo en primer intento"
        }

    # Verificar que replan_task NO se llama
    replan_called = []

    def mock_replan(*args, **kwargs):
        replan_called.append(True)
        return {"task": {"id": "T2_r1", "name": "mock"},
                "original_task_id": "T2", "replan_reason": "no debería llegar"}

    with patch.object(orch, "_run_task", mock_run_task):
        with patch.object(orch._planner, "replan_task", mock_replan):
            result = orch._execute_tasks(plan, on_progress=lambda e: events.append(e))

    report("replan_task NO fue llamada",
           len(replan_called) == 0,
           f"veces llamada: {len(replan_called)}")
    report("T2 marcada como failed",
           t2["status"] == "failed",
           f"obtenido: {t2['status']}")
    report("Pipeline reporta fallo",
           result.get("success") is False)


def test_replanned_counts_as_completed():
    """Las tareas 'replanned' cuentan como completadas en el resultado final."""
    from core.orchestrator import Orchestrator

    t1 = _make_task("T1", "tarea completada")
    t1["status"] = "completed"
    t1["result"] = {"code": "ok"}

    t2 = _make_task("T2", "tarea replanned")
    t2["status"] = "replanned"
    t2["result"] = {"success": False, "diagnosis": "eliminada"}

    plan = _make_plan(tasks=[t1, t2])

    orch = Orchestrator()
    orch.current_plan = plan
    orch.project_id = "test-replanned-count"

    result = orch._execute_tasks(plan)

    report("Pipeline exitoso con replanned",
           result.get("success") is True,
           f"obtenido: {result.get('success')}")


def test_replanned_unblocks_dependents():
    """Una tarea replanned desbloquea las tareas que dependían de ella."""
    from core.orchestrator import Orchestrator

    t1 = _make_task("T1", "completada")
    t1["status"] = "completed"
    t1["result"] = {"code": "ok", "filename": "t1.py"}

    t2 = _make_task("T2", "fallida y replanned", deps=["T1"])
    t2["status"] = "replanned"
    t2["result"] = {"success": False, "diagnosis": "eliminada"}

    t3 = _make_task("T3", "depende de T2", deps=["T2"])
    t3["status"] = "pending"

    plan = _make_plan(tasks=[t1, t2, t3])

    orch = Orchestrator()
    orch.current_plan = plan
    orch.project_id = "test-unblock"

    def mock_run_task(task):
        if task["id"] == "T3":
            return {
                "success": True,
                "code": "print('t3')",
                "filename": "t3.py",
                "criterion_passed": True,
                "attempts_used": 1,
                "model_used": "mock"
            }
        return {"success": False, "attempts_used": 0, "diagnosis": "no esperada"}

    orch.generator.save_to_sandbox = MagicMock(return_value={"success": True})

    with patch.object(orch, "_run_task", mock_run_task):
        result = orch._execute_tasks(plan)

    report("T3 se ejecutó (desbloqueada por replanned)",
           t3["status"] == "completed",
           f"obtenido: {t3['status']}")
    report("Pipeline exitoso",
           result.get("success") is True)


# === EJECUCIÓN ===
if __name__ == "__main__":
    print("=" * 60)
    print("TEST F1+F2: Replanificación de Tareas Fallidas (OOP)")
    print("=" * 60)

    tests = [
        ("replan_valid_task", test_replan_task_returns_valid_task),
        ("replan_llm_empty", test_replan_task_llm_empty_response),
        ("replan_llm_exception", test_replan_task_llm_exception),
        ("replan_preserves_metadata", test_replan_task_preserves_metadata),
        ("handle_replan_replaced", test_handle_replan_replaced),
        ("handle_replan_planner_fails", test_handle_replan_planner_fails),
        ("no_replan_under_3", test_no_replan_under_3_attempts),
        ("replanned_counts_completed", test_replanned_counts_as_completed),
        ("replanned_unblocks_deps", test_replanned_unblocks_dependents),
    ]

    for name, fn in tests:
        print(f"\n--- {name} ---")
        try:
            fn()
        except Exception as e:
            FAIL += 1
            print(f"  ✗ {name} — EXCEPCIÓN: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 60)
    print(f"RESULTADO: {PASS} pasaron, {FAIL} fallaron de {PASS + FAIL}")
    print("=" * 60)
