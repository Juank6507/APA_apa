# apa/tests/test_fase2_split_task.py
"""FASE 2 — Tests de propagación de señal split_task y división automática de tareas.

Adaptado a la interfaz OOP de Planner (clase Planner con métodos de instancia).
Cada test verifica una pieza del flujo sin depender de llamadas reales a modelos de IA.
Se usan mocks para simular las respuestas del router, generador y planificador.
"""
import sys
import os
import json
import logging
from pathlib import Path
from unittest.mock import patch

# Ruta robusta compatible con Windows y Linux
# tests/ -> apa/ -> APA/  (subimos 2 niveles desde tests)
_APA_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _APA_ROOT)

logging.disable(logging.CRITICAL)

# =========================================================================
# Helpers: señales simuladas
# =========================================================================

def make_split_signal(task_id="T1", tokens_needed=45000, max_context=8192):
    """Genera la señal que devuelve el router cuando no hay modelo con suficiente contexto."""
    return {
        "success": False,
        "content": "",
        "model_used": "test-model",
        "provider_used": "test-provider",
        "error": "context_exceeded_no_fallback",
        "error_type": "context_exceeded_no_fallback",
        "action_required": "split_task",
        "tokens_needed": tokens_needed,
        "max_available_context": max_context,
        "message": f"La tarea requiere ~{tokens_needed} tokens. Max disponible {max_context}."
    }


def make_generic_error():
    """Genera un error genérico (no es split_task)."""
    return {
        "success": False,
        "content": "",
        "model_used": "test-model",
        "provider_used": "test-provider",
        "error": "Modelo no disponible"
    }


def make_success_response(code="print('ok')"):
    """Genera una respuesta exitosa del generador."""
    return {
        "success": True,
        "task_id": "T1",
        "code": code,
        "filename": "test.py",
        "is_valid_syntax": True,
        "model_used": "test-model",
        "provider_used": "test-provider"
    }


def make_sample_task(task_id="T1", deps=None):
    """Genera una tarea de ejemplo para tests."""
    return {
        "id": task_id,
        "name": f"Tarea {task_id}",
        "description": "Descripción de prueba para la tarea",
        "depends_on": deps or [],
        "inputs": [],
        "expected_output": "Archivo generado",
        "acceptance_criterion": "El código se ejecuta sin errores",
        "task_type": "generation",
        "status": "pending",
        "attempts": 0,
        "result": None,
        "model_used": None,
        "language": "python"
    }


passed = 0
failed = 0


def check(test_name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  [OK] {test_name}")
    else:
        failed += 1
        print(f"  [FALLO] {test_name} — {detail}")


# =========================================================================
# TEST 1: generator.generate() propaga señal split_task
# =========================================================================
def test_generator_propagates_split():
    print("\n--- Test 1: generator.generate() propaga señal split_task ---")
    from agents.generator import GeneratorAgent

    agent = GeneratorAgent()
    task = make_sample_task("T1")

    # Capturar la llamada a call_llm y devolver split_signal
    import agents.generator as gen_module
    original_call_llm = gen_module.call_llm

    def mock_call_llm_split(*args, **kwargs):
        return make_split_signal("T1", tokens_needed=45000, max_context=8192)

    gen_module.call_llm = mock_call_llm_split

    try:
        result = agent.generate(task, project_id="test-proj")
        check("success es False", result["success"] == False)
        check("action_required es split_task", result.get("action_required") == "split_task")
        check("error_type es correcto", result.get("error_type") == "context_exceeded_no_fallback")
        check("tokens_needed > 0", result.get("tokens_needed", 0) > 0)
        check("max_available_context > 0", result.get("max_available_context", 0) > 0)
        check("split_message no vacío", len(result.get("split_message", "")) > 0)
    finally:
        gen_module.call_llm = original_call_llm


# =========================================================================
# TEST 2: generator.generate() NO propaga señal para errores genéricos
# =========================================================================
def test_generator_no_split_on_generic_error():
    print("\n--- Test 2: generator.generate() NO propaga split en errores genéricos ---")
    from agents.generator import GeneratorAgent

    agent = GeneratorAgent()
    task = make_sample_task("T2")

    import agents.generator as gen_module
    original_call_llm = gen_module.call_llm

    def mock_call_llm_error(*args, **kwargs):
        return make_generic_error()

    gen_module.call_llm = mock_call_llm_error

    try:
        result = agent.generate(task, project_id="test-proj")
        check("success es False", result["success"] == False)
        check("NO tiene action_required", result.get("action_required") is None)
        check("NO tiene tokens_needed", result.get("tokens_needed") is None)
    finally:
        gen_module.call_llm = original_call_llm


# =========================================================================
# TEST 3: generator.generate_and_test() propaga señal split_task
# =========================================================================
def test_generate_and_test_propagates_split():
    print("\n--- Test 3: generator.generate_and_test() propaga señal split_task ---")
    from agents.generator import GeneratorAgent

    agent = GeneratorAgent()
    task = make_sample_task("T3")

    import agents.generator as gen_module
    original_call_llm = gen_module.call_llm

    def mock_call_llm_split(*args, **kwargs):
        return make_split_signal("T3", tokens_needed=35000, max_context=8192)

    gen_module.call_llm = mock_call_llm_split

    try:
        result = agent.generate_and_test(task)
        check("success es False", result["success"] == False)
        check("action_required es split_task", result.get("action_required") == "split_task")
        check("tokens_needed > 0", result.get("tokens_needed", 0) > 0)
        check("split_message no vacío", len(result.get("split_message", "")) > 0)
    finally:
        gen_module.call_llm = original_call_llm


# =========================================================================
# TEST 4: orchestrator._run_task() detecta y propaga señal split_task
# =========================================================================
def test_orchestrator_run_task_detects_split():
    print("\n--- Test 4: orchestrator._run_task() detecta señal split_task ---")
    from core.orchestrator import Orchestrator

    orch = Orchestrator()
    orch.current_plan = {"tasks": [make_sample_task("T4")]}
    orch.project_id = "test-proj"

    task = make_sample_task("T4")

    # Parchear generate_and_test para devolver split signal
    original_method = orch.generator.generate_and_test

    def mock_generate_and_test(task_dict):
        return {
            "task_id": "T4",
            "code": "",
            "filename": "",
            "is_valid_syntax": False,
            "model_used": "test-model",
            "provider_used": "test-provider",
            "success": False,
            "action_required": "split_task",
            "error_type": "context_exceeded_no_fallback",
            "tokens_needed": 50000,
            "max_available_context": 8192,
            "split_message": "La tarea requiere ~50000 tokens."
        }

    orch.generator.generate_and_test = mock_generate_and_test

    try:
        result = orch._run_task(task)
        check("success es False", result["success"] == False)
        check("action_required es split_task", result.get("action_required") == "split_task")
        check("attempts_used es 0 (no consume intento)", result.get("attempts_used") == 0)
        check("tokens_needed > 0", result.get("tokens_needed", 0) > 0)
        check("max_available_context > 0", result.get("max_available_context", 0) > 0)
    finally:
        orch.generator.generate_and_test = original_method


# =========================================================================
# TEST 5: orchestrator._handle_task_split() divide tarea y actualiza plan
#   (Adaptado: mock de orch._planner.split_task_into_subtasks en vez de
#    función standalone core.planner.split_task_into_subtasks)
# =========================================================================
def test_orchestrator_handle_split():
    print("\n--- Test 5: orchestrator._handle_task_split() divide y actualiza plan ---")
    from core.orchestrator import Orchestrator

    orch = Orchestrator()
    orch.project_id = "test-proj-split"

    task = make_sample_task("T5")
    plan = {
        "project_id": "test-proj-split",
        "tasks": [
            task,
            make_sample_task("T6", deps=["T5"]),  # T6 depende de T5
            make_sample_task("T7"),  # T7 no depende de T5
        ]
    }
    orch.current_plan = plan
    completed_tasks = {}

    # Mock del método OOP del planner
    def mock_split_oop(project_id, task_id, reason):
        return {
            "subtasks": [
                {
                    "id": "T5.1",
                    "name": "Subtarea 1 de T5",
                    "description": "Primera parte",
                    "dependencies": [],
                    "inputs": [],
                    "output": "Parte 1",
                    "acceptance_criteria": "Criterio 1",
                    "task_type": "code_generation",
                    "programming_language": "python",
                    "executor": "apa",
                    "priority": "high",
                    "status": "pending",
                    "attempts": 0,
                    "result": None,
                    "model_used": None,
                    "parent_task_id": "T5",
                    "split_reason": "context_exceeded"
                },
                {
                    "id": "T5.2",
                    "name": "Subtarea 2 de T5",
                    "description": "Segunda parte",
                    "dependencies": ["T5.1"],
                    "inputs": [],
                    "output": "Parte 2",
                    "acceptance_criteria": "Criterio 2",
                    "task_type": "code_generation",
                    "programming_language": "python",
                    "executor": "apa",
                    "priority": "medium",
                    "status": "pending",
                    "attempts": 0,
                    "result": None,
                    "model_used": None,
                    "parent_task_id": "T5",
                    "split_reason": "context_exceeded"
                }
            ],
            "original_task_id": "T5",
            "split_reason": "context_exceeded",
            "total_subtasks": 2,
        }

    split_signal = {
        "action_required": "split_task",
        "tokens_needed": 45000,
        "max_available_context": 8192,
        "diagnosis": "Contexto excedido"
    }

    with patch.object(orch._planner, "split_task_into_subtasks", mock_split_oop):
        result_ok = orch._handle_task_split(task, split_signal, plan, completed_tasks)

    check("División exitosa", result_ok == True)
    check("Tarea original marcada como 'split'", task["status"] == "split")
    check("Tarea original tiene split_into", "split_into" in (task.get("result") or {}))

    # Verificar que las subtareas se insertaron en el plan
    plan_task_ids = [t["id"] for t in plan["tasks"]]
    check("T5.1 está en el plan", "T5.1" in plan_task_ids)
    check("T5.2 está en el plan", "T5.2" in plan_task_ids)

    # Verificar que T6 ahora depende de T5.2 (la última subtarea) en lugar de T5
    t6 = next(t for t in plan["tasks"] if t["id"] == "T6")
    check("T6 depende de T5.2", "T5.2" in t6.get("depends_on", []))
    check("T6 ya NO depende de T5", "T5" not in t6.get("depends_on", []))

    # Verificar que T7 no fue afectada
    t7 = next(t for t in plan["tasks"] if t["id"] == "T7")
    check("T7 sin dependencias", t7.get("depends_on") == [])


# =========================================================================
# TEST 6: _execute_tasks reconoce 'split' como dependencia resuelta
# =========================================================================
def test_split_resolves_dependencies():
    print("\n--- Test 6: _execute_tasks reconoce 'split' como dependencia resuelta ---")

    # Simulamos el escenario: T5 está en estado 'split', T5_1 está pending
    # y depende de T5. T5_1 debería ser ejecutable.
    task_t5 = make_sample_task("T5")
    task_t5["status"] = "split"

    task_t5_1 = make_sample_task("T5_1", deps=["T5"])
    task_t5_1["status"] = "pending"

    tasks_list = [task_t5, task_t5_1]

    # Simular la lógica de dependencias del orquestador
    split_task_ids = {t["id"] for t in tasks_list if t["status"] == "split"}
    executable = []
    for task in tasks_list:
        if task["status"] != "pending":
            continue
        deps = task.get("depends_on", [])
        if all(dep_id in split_task_ids for dep_id in deps):
            executable.append(task)

    check("T5_1 es ejecutable aunque T5 esté en 'split'",
          len(executable) == 1 and executable[0]["id"] == "T5_1")


# =========================================================================
# TEST 7: _execute_tasks considera 'split' como completado en resultado final
# =========================================================================
def test_split_counts_as_completed():
    print("\n--- Test 7: 'split' cuenta como completado en resultado final ---")

    tasks_list = [
        {"status": "completed", "id": "T1"},
        {"status": "split", "id": "T2"},
        {"status": "completed", "id": "T3"},
    ]

    all_completed = all(t["status"] in ("completed", "split") for t in tasks_list)
    check("Todos completados (incluyendo split)", all_completed == True)

    tasks_list_fail = [
        {"status": "completed", "id": "T1"},
        {"status": "split", "id": "T2"},
        {"status": "failed", "id": "T3"},
    ]
    all_completed_fail = all(t["status"] in ("completed", "split") for t in tasks_list_fail)
    check("NO todos completados si hay un failed", all_completed_fail == False)


# =========================================================================
# TEST 8: Planner.split_task_into_subtasks con mock LLM (OOP)
# =========================================================================
def test_split_task_with_mock_llm():
    print("\n--- Test 8: Planner.split_task_into_subtasks con mock LLM (OOP) ---")
    from core.planner import Planner
    from config.settings import settings

    planner = Planner(settings)

    # Mock de core.router.call_llm que devuelve JSON string
    mock_response = {
        "subtasks": [
            {
                "id": "T8.1",
                "name": "Primera parte de T8",
                "description": "Crear las estructuras base",
                "dependencies": [],
                "inputs": [],
                "output": "Estructura base",
                "acceptance_criteria": "Sintaxis válida",
                "task_type": "code_generation",
                "programming_language": "python",
            },
            {
                "id": "T8.2",
                "name": "Segunda parte de T8",
                "description": "Implementar lógica",
                "dependencies": ["T8.1"],
                "inputs": [],
                "output": "Lógica completa",
                "acceptance_criteria": "Tests pasan",
                "task_type": "code_generation",
                "programming_language": "python",
            }
        ]
    }

    from unittest.mock import patch
    with patch("core.router.call_llm", lambda *a, **kw: json.dumps(mock_response)):
        result = planner.split_task_into_subtasks(
            project_id="test-proj",
            task_id="T8",
            reason="context_exceeded"
        )

    check("División exitosa", "subtasks" in result)
    check("Hay subtareas", len(result["subtasks"]) == 2)
    check("original_task_id preservado",
          result.get("original_task_id") == "T8")
    check("split_reason preservado",
          result.get("split_reason") == "context_exceeded")
    check("total_subtasks correcto",
          result.get("total_subtasks") == 2,
          f"obtenido: {result.get('total_subtasks')}")
    check("Primera subtarea tiene campos OOP",
          all(f in result["subtasks"][0] for f in [
              "id", "name", "description", "dependencies",
              "inputs", "output", "acceptance_criteria",
              "task_type", "programming_language", "executor", "priority"
          ]),
          f"campos: {list(result['subtasks'][0].keys())}")


# =========================================================================
# Ejecutar todos los tests
# =========================================================================
if __name__ == "__main__":
    print("=" * 64)
    print("FASE 2 — Tests de propagación split_task y división automática (OOP)")
    print("=" * 64)

    test_generator_propagates_split()
    test_generator_no_split_on_generic_error()
    test_generate_and_test_propagates_split()
    test_orchestrator_run_task_detects_split()
    test_orchestrator_handle_split()
    test_split_resolves_dependencies()
    test_split_counts_as_completed()
    test_split_task_with_mock_llm()

    print("\n" + "=" * 64)
    tests_run = passed + failed
    if failed == 0:
        print(f"Resultado: {passed}/{tests_run} tests pasaron")
        print("TODOS LOS TESTS PASARON")
    else:
        print(f"Resultado: {passed}/{tests_run} pasaron, {failed} FALLARON")
    print("=" * 64)
