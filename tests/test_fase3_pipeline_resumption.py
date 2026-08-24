# apa/tests/test_fase3_pipeline_resumption.py
# FASE 3: Pipeline resumption integration.
# Verifica que:
#   1. _save_pipeline_state guarda la fase y las tareas correctamente
#   2. Incluye subtareas dinámicas de FASE 2
#   3. resume() carga estado y continúa la ejecución
#   4. resume() rechaza pipelines completados o cancelados
#   5. resume() rechaza cuando no hay estado guardado
#   6. La fase FAILED se guarda cuando el pipeline falla
#   7. PipelineState se limpia cuando el pipeline termina con éxito
#   8. list_states refleja el estado guardado

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
import shutil
import tempfile
import os
from unittest.mock import patch, MagicMock

from core.pipeline_state import (
    PipelineStateManager, PipelineState, PipelinePhase
)

PASS = 0
FAIL = 0


def report(test_name: str, ok: bool, detail: str = ""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ✓ {test_name}")
    else:
        FAIL += 1
        print(f"  ✗ {test_name} — {detail}")


def test_save_pipeline_state_saves_phase_and_tasks():
    """_save_pipeline_state guarda la fase correcta y todas las tareas del plan."""
    from core.orchestrator import Orchestrator

    with tempfile.TemporaryDirectory() as tmpdir:
        mgr = PipelineStateManager(specs_dir=tmpdir)

        orch = Orchestrator()
        orch._pipeline_mgr = mgr
        orch.project_id = "test-fase3-01"
        orch.current_plan = {
            "project_id": "test-fase3-01",
            "spec_summary": "Proyecto de prueba",
            "tasks": [
                {"id": "T1", "name": "tarea1", "status": "completed", "result": {}},
                {"id": "T2", "name": "tarea2", "status": "pending"},
                {"id": "T3", "name": "tarea3", "status": "pending", "depends_on": ["T1"]}
            ]
        }

        orch._save_pipeline_state(PipelinePhase.EXECUTING)

        # Verificar que se guardó
        state = mgr.load("test-fase3-01")
        report("Estado existe", state is not None, f"obtenido: {state}")
        if not state:
            return

        report("Fase correcta",
               state.phase == PipelinePhase.EXECUTING.value,
               f"esperaba 'executing', obtuvo '{state.phase}'")
        report("Project ID correcto",
               state.project_id == "test-fase3-01",
               f"obtenido: {state.project_id}")
        report("Tareas guardadas",
               len(state.plan_tasks) == 3,
               f"esperaba 3, obtuvo {len(state.plan_tasks)}")
        report("Especie en tareas",
               state.plan_tasks[0]["id"] == "T1",
               f"obtenido: {state.plan_tasks[0]['id']}")


def test_save_pipeline_state_includes_split_subtasks():
    """El pipeline state incluye subtareas dinámicas de FASE 2."""
    from core.orchestrator import Orchestrator

    with tempfile.TemporaryDirectory() as tmpdir:
        mgr = PipelineStateManager(specs_dir=tmpdir)

        orch = Orchestrator()
        orch._pipeline_mgr = mgr
        orch.project_id = "test-fase3-02"
        orch.current_plan = {
            "project_id": "test-fase3-02",
            "spec_summary": "Proyecto con división",
            "tasks": [
                {"id": "T1", "name": "tarea1", "status": "completed", "result": {}},
                {
                    "id": "T2", "name": "tarea_grande", "status": "split",
                    "result": {"split_into": ["T2_1", "T2_2"]}
                },
                {"id": "T2_1", "name": "subparte 1", "status": "completed",
                 "depends_on": ["T1"], "result": {}},
                {"id": "T2_2", "name": "subparte 2", "status": "pending",
                 "depends_on": ["T2_1"]},
                {"id": "T3", "name": "tarea3", "status": "pending",
                 "depends_on": ["T2_2"]}
            ]
        }

        orch._save_pipeline_state(PipelinePhase.EXECUTING)

        state = mgr.load("test-fase3-02")
        report("Estado existe con subtareas", state is not None)
        if not state:
            return

        report("Total de tareas incluye subtareas",
               len(state.plan_tasks) == 5,
               f"esperaba 5, obtuvo {len(state.plan_tasks)}")

        task_ids = [t["id"] for t in state.plan_tasks]
        report("Tarea dividida presente",
               "T2" in task_ids, f"IDs: {task_ids}")
        report("Subtarea 1 presente",
               "T2_1" in task_ids, f"IDs: {task_ids}")
        report("Subtarea 2 presente",
               "T2_2" in task_ids, f"IDs: {task_ids}")
        report("Tarea dividida mantiene estado split",
               state.plan_tasks[1]["status"] == "split",
               f"obtenido: {state.plan_tasks[1]['status']}")


def test_resume_loads_state_and_executes():
    """resume() carga el estado guardado y ejecuta las tareas pendientes."""
    from core.orchestrator import Orchestrator

    with tempfile.TemporaryDirectory() as tmpdir:
        mgr = PipelineStateManager(specs_dir=tmpdir)

        # Pre-guardar un estado con tareas parciales
        state = PipelineState(
            project_id="test-fase3-03",
            phase=PipelinePhase.EXECUTING.value,
            current_task_index=-1,
            user_prompt="Proyecto para reanudar",
            plan_tasks=[
                {"id": "T1", "name": "tarea1", "status": "completed",
                 "result": {"code": "print('ok')", "filename": "t1.py"}},
                {"id": "T2", "name": "tarea2", "status": "pending",
                 "depends_on": ["T1"],
                 "description": "Generar archivo",
                 "acceptance_criterion": "funciona",
                 "task_type": "script"}
            ],
            log=["ejecutando"]
        )
        mgr.save(state)

        orch = Orchestrator()
        orch._pipeline_mgr = mgr

        # Mock de generate_and_test para que T2 tenga éxito
        def mock_generate_and_test(task):
            return {
                "success": True,
                "code": "print('t2 ok')",
                "filename": "t2.py",
                "execution": {"criterion_passed": True},
                "model_used": "mock-model"
            }

        orch.generator.generate_and_test = mock_generate_and_test
        orch.generator.save_to_sandbox = MagicMock(return_value={"success": True})

        # Mock de documenter para no llamar LLM
        orch.documenter.document_generated_files = MagicMock(return_value={
            "success": True, "files_documented": 0, "doc_path": ""
        })

        result = orch.resume("test-fase3-03")

        report("Resume exitoso",
               result.get("success") is True,
               f"obtenido: {result}")
        report("T2 completada en resume (total 2, T1 pre-existente + T2 nueva)",
               result.get("completed") == 2,
               f"completadas: {result.get('completed')}")
        report("Sin fallos",
               result.get("failed") == 0,
               f"fallidas: {result.get('failed')}")


def test_resume_rejects_completed_pipeline():
    """resume() rechaza pipelines ya completados."""
    from core.orchestrator import Orchestrator

    with tempfile.TemporaryDirectory() as tmpdir:
        mgr = PipelineStateManager(specs_dir=tmpdir)

        state = PipelineState(
            project_id="test-fase3-04",
            phase=PipelinePhase.COMPLETED.value,
            plan_tasks=[],
            log=[]
        )
        mgr.save(state)

        orch = Orchestrator()
        orch._pipeline_mgr = mgr
        result = orch.resume("test-fase3-04")

        report("Resume rechazado para completado",
               result.get("success") is False,
               f"debería ser False, obtuvo: {result.get('success')}")
        report("Mensaje de error apropiado",
               "no se puede reanudar" in result.get("error", ""),
               f"error: {result.get('error')}")


def test_resume_rejects_missing_state():
    """resume() devuelve error cuando no hay estado guardado."""
    from core.orchestrator import Orchestrator

    with tempfile.TemporaryDirectory() as tmpdir:
        mgr = PipelineStateManager(specs_dir=tmpdir)

        orch = Orchestrator()
        orch._pipeline_mgr = mgr
        result = orch.resume("proyecto-inexistente")

        report("Resume rechazado sin estado",
               result.get("success") is False,
               f"debería ser False, obtuvo: {result.get('success')}")
        report("Mensaje de no encontrado",
               "No se encontró" in result.get("error", ""),
               f"error: {result.get('error')}")


def test_failed_state_saved_on_error():
    """Cuando el pipeline falla, se guarda estado FAILED."""
    from core.orchestrator import Orchestrator

    with tempfile.TemporaryDirectory() as tmpdir:
        mgr = PipelineStateManager(specs_dir=tmpdir)

        orch = Orchestrator()
        orch._pipeline_mgr = mgr
        orch.project_id = "test-fase3-06"
        orch.current_plan = {
            "project_id": "test-fase3-06",
            "spec_summary": "Proyecto que falla",
            "tasks": [
                {"id": "T1", "name": "tarea1", "status": "completed", "result": {}},
                {"id": "T2", "name": "tarea2", "status": "failed"}
            ]
        }

        orch._save_pipeline_state(
            PipelinePhase.FAILED,
            error="T2 falló y no hay más opciones"
        )

        state = mgr.load("test-fase3-06")
        report("Estado FAILED guardado", state is not None)
        if not state:
            return
        report("Fase es FAILED",
               state.phase == PipelinePhase.FAILED.value,
               f"esperaba 'failed', obtuvo '{state.phase}'")
        report("Error registrado",
               state.error is not None and "T2" in state.error,
               f"error: {state.error}")


def test_pipeline_state_cleared_on_success():
    """Cuando el pipeline termina con éxito, se limpia el estado."""
    from core.orchestrator import Orchestrator

    with tempfile.TemporaryDirectory() as tmpdir:
        mgr = PipelineStateManager(specs_dir=tmpdir)

        # Pre-guardar un estado
        state = PipelineState(
            project_id="test-fase3-07",
            phase=PipelinePhase.EXECUTING.value,
            plan_tasks=[
                {"id": "T1", "name": "tarea1", "status": "pending",
                 "description": "t", "acceptance_criterion": "c",
                 "task_type": "script"}
            ],
            log=[]
        )
        mgr.save(state)

        orch = Orchestrator()
        orch._pipeline_mgr = mgr

        # Mock: T1 completada con éxito
        def mock_generate_and_test(task):
            return {
                "success": True,
                "code": "print('ok')",
                "filename": "t1.py",
                "execution": {"criterion_passed": True},
                "model_used": "mock"
            }

        orch.generator.generate_and_test = mock_generate_and_test
        orch.generator.save_to_sandbox = MagicMock(return_value={"success": True})
        orch.documenter.document_generated_files = MagicMock(return_value={
            "success": True, "files_documented": 0, "doc_path": ""
        })

        result = orch.resume("test-fase3-07")

        report("Resume exitoso", result.get("success") is True)
        # Después del éxito, el estado debe haberse limpiado
        state_after = mgr.load("test-fase3-07")
        report("Estado limpiado tras éxito",
               state_after is None,
               f"debería ser None, obtuvo: {state_after}")


def test_list_states_shows_saved_pipeline():
    """list_states() del PipelineStateManager refleja el pipeline guardado."""
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr = PipelineStateManager(specs_dir=tmpdir)

        state = PipelineState(
            project_id="test-fase3-08",
            phase=PipelinePhase.EXECUTING.value,
            plan_tasks=[
                {"id": "T1", "status": "completed"},
                {"id": "T2", "status": "pending"}
            ],
            log=[]
        )
        mgr.save(state)

        states = mgr.list_states()
        report("Lista no vacía",
               len(states) > 0,
               f"esperaba al menos 1, obtuvo {len(states)}")
        if states:
            found = next(
                (s for s in states if s["project_id"] == "test-fase3-08"),
                None
            )
            report("Pipeline encontrado en lista",
                   found is not None, f"obtenido: {states}")
            if found:
                report("Fase correcta en lista",
                       found["phase"] == "executing",
                       f"obtenido: {found['phase']}")
                report("Total tareas correcto",
                       found["total_tasks"] == 2,
                       f"obtenido: {found['total_tasks']}")


# === EJECUCIÓN ===
if __name__ == "__main__":
    print("=" * 60)
    print("TEST FASE 3: Pipeline Resumption Integration")
    print("=" * 60)

    tests = [
        ("save_pipeline_state_saves_phase_and_tasks", test_save_pipeline_state_saves_phase_and_tasks),
        ("save_includes_split_subtasks", test_save_pipeline_state_includes_split_subtasks),
        ("resume_loads_and_executes", test_resume_loads_state_and_executes),
        ("resume_rejects_completed", test_resume_rejects_completed_pipeline),
        ("resume_rejects_missing", test_resume_rejects_missing_state),
        ("failed_state_saved_on_error", test_failed_state_saved_on_error),
        ("state_cleared_on_success", test_pipeline_state_cleared_on_success),
        ("list_states_shows_saved", test_list_states_shows_saved_pipeline),
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
