# apa/core/orchestrator.py
import sys
import os
import json
import logging
from pathlib import Path
from datetime import datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from config.settings import settings
from core.planner import Planner
from agents.generator import GeneratorAgent
from agents.corrector import CorrectorAgent
from agents.documenter import DocumenterAgent
from core.checkpoint import CheckpointManager
from core.parallel_executor import ParallelExecutor
from core.pipeline_state import (
    PipelineStateManager, PipelineState, PipelinePhase
)
logger = logging.getLogger(__name__)
logger.setLevel(getattr(logging, settings.log_level.upper(), logging.WARNING))
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)

class Orchestrator:
    def __init__(self):
        # Resiliente: si los agentes no pueden conectar al sandbox,
        # el Orquestador sigue funcionando en modo degradado.
        try:
            self.generator = GeneratorAgent()
        except Exception as exc:
            logger.warning("Orchestrator: GeneratorAgent no disponible (%s)", exc)
            self.generator = None
        try:
            self.corrector = CorrectorAgent()
        except Exception as exc:
            logger.warning("Orchestrator: CorrectorAgent no disponible (%s)", exc)
            self.corrector = None
        try:
            self.documenter = DocumenterAgent()
        except Exception as exc:
            logger.warning("Orchestrator: DocumenterAgent no disponible (%s)", exc)
            self.documenter = None
        self.current_plan = None
        self.project_id = None
        self.checkpoint_mgr: CheckpointManager | None = None
        try:
            self._pipeline_mgr = PipelineStateManager()
        except Exception:
            self._pipeline_mgr = None
        try:
            self._planner = Planner(settings)
        except Exception:
            self._planner = None

    def _emit(self, on_progress, event: dict):
        event["timestamp"] = datetime.utcnow().isoformat()
        if on_progress:
            try:
                on_progress(event)
            except Exception as e:
                logger.warning(f"on_progress callback error: {e}")

    def _persist_plan(self, plan: dict) -> None:
        try:
            if not self.project_id:
                return
            specs_dir = Path(__file__).parents[1] / "specs"
            project_dir = specs_dir / self.project_id
            project_dir.mkdir(parents=True, exist_ok=True)
            plan_path = project_dir / "plan.json"
            with open(plan_path, 'w', encoding='utf-8') as f:
                json.dump(plan, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to persist plan: {e}")

    def _generate_documentation(self, plan: dict, on_progress=None) -> dict:
        try:
            self._emit(on_progress, {
                "type": "documentation_started",
                "message": "Generando documentación del proyecto..."
            })

            files = []
            for task in plan.get("tasks", []):
                if task.get("status") == "completed" and task.get("result"):
                    result = task["result"]
                    if result.get("code") and result.get("filename"):
                        files.append({
                            "filename": result["filename"],
                            "code": result["code"],
                            "task_name": task["name"],
                            "acceptance_criterion": task.get("acceptance_criterion", "")
                        })

            if not files:
                return {"success": True, "skipped": True}

            doc_result = self.documenter.document_generated_files(
                project_id=self.project_id,
                files=files
            )

            self._emit(on_progress, {
                "type": "documentation_completed",
                "success": doc_result["success"],
                "doc_path": doc_result.get("doc_path", ""),
                "files_documented": doc_result.get("files_documented", 0),
                "message": f"Documentación generada: {doc_result.get('files_documented', 0)} archivos documentados"
            })

            return doc_result

        except Exception as e:
            logger.error(f"Documentation failed: {e}")
            self._emit(on_progress, {
                "type": "documentation_failed",
                "error": str(e)
            })
            return {"success": False, "error": str(e)}

    def _run_task(self, task: dict) -> dict:
        try:
            # A8: Preparar contexto de dependencias ANTES de generar y corregir
            dependency_codes = {}
            for dep_id in task.get("depends_on", []):
                dep_task = next((t for t in self.current_plan["tasks"] 
                               if t["id"] == dep_id and t["status"] == "completed"), None)
                if dep_task and dep_task.get("result", {}).get("code"):
                    dep_path = dep_task.get("target_path", dep_task.get("file_path", dep_id))
                    dependency_codes[dep_path] = dep_task["result"]["code"]
            
            if dependency_codes:
                task["dependency_codes"] = dependency_codes
                logger.info(f"Injected {len(dependency_codes)} dependency codes for task {task.get('id')}: {list(dependency_codes.keys())}")
            
            # PROPAGACIÓN DE project_id A GENERATOR Y CORRECTOR
            task["project_id"] = self.project_id
            
            gen_result = self.generator.generate_and_test(task)
            
            # FASE 2: Detectar señal split_task y propagarla
            if not gen_result.get("success") and gen_result.get("action_required") == "split_task":
                logger.info(f"Tarea {task['id']} requiere división por contexto excedido")
                return {
                    "success": False,
                    "code": "",
                    "filename": "",
                    "criterion_passed": False,
                    "attempts_used": 0,  # No consume intento real
                    "model_used": gen_result.get("model_used"),
                    "diagnosis": gen_result.get("split_message", "Contexto excedido, requiere división"),
                    "action_required": "split_task",
                    "error_type": gen_result.get("error_type", "context_exceeded_no_fallback"),
                    "tokens_needed": gen_result.get("tokens_needed", 0),
                    "max_available_context": gen_result.get("max_available_context", 0)
                }
            
            if not gen_result.get("success"):
                return {
                    "success": False,
                    "code": "",
                    "filename": "",
                    "criterion_passed": False,
                    "attempts_used": 1,
                    "model_used": None,
                    "diagnosis": "El generador no pudo producir código"
                }
            
            execution = gen_result.get("execution", {})
            criterion_passed = execution.get("criterion_passed", False)
            
            if criterion_passed:
                save_result = self.generator.save_to_sandbox(gen_result["code"], gen_result["filename"])
                return {
                    "success": True,
                    "code": gen_result["code"],
                    "filename": gen_result["filename"],
                    "criterion_passed": True,
                    "attempts_used": 1,
                    "model_used": gen_result.get("model_used"),
                    "diagnosis": "Generado y verificado en primer intento"
                }
            
            # dependency_codes ya está en task, el corrector lo usará
            correction_result = self.corrector.correction_loop(
                task=task,
                initial_code=gen_result["code"],
                initial_execution=gen_result["execution"],
                max_attempts=3
            )
            
            if correction_result.get("success"):
                save_result = self.generator.save_to_sandbox(
                    correction_result["code"], correction_result["filename"])
                attempts = correction_result.get("attempts_used", 0) + 1
                return {
                    "success": True,
                    "code": correction_result["code"],
                    "filename": correction_result["filename"],
                    "criterion_passed": True,
                    "attempts_used": attempts,
                    "model_used": correction_result.get("model_used"),
                    "diagnosis": f"Corregido en {attempts} intentos"
                }
            
            return {
                "success": False,
                "code": correction_result.get("code", ""),
                "filename": correction_result.get("filename", ""),
                "criterion_passed": False,
                "attempts_used": correction_result.get("attempts_used", 0) + 1,
                "model_used": correction_result.get("model_used"),
                "diagnosis": correction_result.get("diagnosis", "Corrección fallida")
            }
            
        except Exception as e:
            logger.error(f"Error in _run_task: {e}")
            return {
                "success": False,
                "code": "",
                "filename": "",
                "criterion_passed": False,
                "attempts_used": 1,
                "model_used": None,
                "diagnosis": f"Excepción en ejecución: {str(e)}"
            }

    def _handle_task_replan(self, task: dict, result: dict, plan: dict,
                                 completed_tasks: dict, on_progress=None) -> bool:
        """Gestiona la replanificación de una tarea que agotó sus intentos.

        Llama al planificador con toda la información del fracaso para que
        decida cómo proceder: dividir, simplificar, sustituir o eliminar.

        Returns:
            True si la replanificación fue exitosa, False si falló.
        """
        original_task_id = task["id"]
        task_result = task.get("result", {})

        logger.info(
            f"Iniciando replanificación de tarea {original_task_id}: "
            f"attempts={task_result.get('attempts_used', 0)}"
        )

        # Construir el contexto del error para el planificador
        error_context = {
            "diagnosis": task_result.get("diagnosis", "Fallo desconocido"),
            "attempts_used": task_result.get("attempts_used", 0),
            "last_code": task_result.get("code", ""),
            "last_filename": task_result.get("filename", "")
        }

        # Adaptación a Planner OOP: replan_task(project_id, task_id, reason)
        reason = error_context["diagnosis"]
        try:
            replan_result = self._planner.replan_task(
                self.project_id or "unknown",
                original_task_id,
                reason,
            )
            # Puente de interfaz: la nueva firma retorna {"task": ...}
            # El orchestrador espera {"success": ..., "action": ..., "replacement_tasks": [...]}
            replacement_task = replan_result.get("task")
            if not replacement_task:
                logger.error(f"No se pudo replanificar la tarea {original_task_id}: tarea vacía")
                return False
            replan_result = {
                "success": True,
                "action": "replaced",
                "replacement_tasks": [replacement_task],
                "reasoning": replan_result.get("replan_reason", reason),
            }
        except Exception as e:
            logger.error(f"Error en replan_task OOP para {original_task_id}: {e}")
            return False

        if not replan_result.get("success"):
            logger.error(
                f"No se pudo replanificar la tarea {original_task_id}: "
                f"{replan_result.get('error', 'Error desconocido')}"
            )
            return False

        action = replan_result["action"]
        replacement_tasks = replan_result["replacement_tasks"]
        reasoning = replan_result.get("reasoning", "")

        if action == "removed":
            # Marcar como 'replanned' y no insertar nada
            task["status"] = "replanned"
            task["result"] = {
                "success": False,
                "action_required": "replanned_removed",
                "diagnosis": f"Tarea eliminada por el planificador: {reasoning}",
                "model_used": replan_result.get("model_used")
            }

            # Redirigir dependencias: las tareas que dependían de esta
            # ahora dependen de las mismas dependencias que tenía la original
            original_deps = task.get("depends_on", [])
            for t in plan.get("tasks", []):
                if t["id"] == original_task_id:
                    continue
                deps = t.get("depends_on", [])
                if original_task_id in deps:
                    # Si la original tenía dependencias, heredarlas
                    # Si no, quitar la dependencia (la tarea ya no existe)
                    new_deps = [d for d in deps if d != original_task_id]
                    new_deps.extend(original_deps)
                    # Eliminar duplicados
                    t["depends_on"] = list(dict.fromkeys(new_deps))
                    logger.info(
                        f"Tarea {t['id']} actualizada: dependencias "
                        f"redirigidas de {original_task_id} a {t['depends_on']}"
                    )

            self._emit(on_progress, {
                "type": "task_replanned",
                "original_task_id": original_task_id,
                "original_task_name": task.get("name", ""),
                "action": "removed",
                "reasoning": reasoning,
                "message": (
                    f"Tarea '{task.get('name', original_task_id)}' eliminada "
                    f"por el planificador: {reasoning}"
                )
            })
            return True

        # action == 'replaced'
        # Marcar la tarea original como replanned
        task["status"] = "replanned"
        task["result"] = {
            "success": False,
            "action_required": "replanned_replaced",
            "diagnosis": f"Tarea replanificada: {reasoning}",
            "replaced_by": [rt["id"] for rt in replacement_tasks],
            "model_used": replan_result.get("model_used")
        }

        # Redirigir dependencias: tareas que dependían de la original
        # ahora dependen de la última tarea de reemplazo
        last_replacement_id = replacement_tasks[-1]["id"]
        for t in plan.get("tasks", []):
            if t["id"] == original_task_id:
                continue
            deps = t.get("depends_on", [])
            if original_task_id in deps:
                t["depends_on"] = [
                    last_replacement_id if d == original_task_id else d
                    for d in deps
                ]
                logger.info(
                    f"Tarea {t['id']} actualizada: depende de "
                    f"{last_replacement_id} (era {original_task_id})"
                )

        # Insertar las tareas de reemplazo en el plan
        plan["tasks"].extend(replacement_tasks)

        # Añadir al conjunto de tareas resueltas para desbloqueo
        # (la original queda como 'replanned', equivalente a resuelta)
        completed_tasks[original_task_id] = {"replanned": True}

        self._emit(on_progress, {
            "type": "task_replanned",
            "original_task_id": original_task_id,
            "original_task_name": task.get("name", ""),
            "action": "replaced",
            "replacement_task_ids": [rt["id"] for rt in replacement_tasks],
            "replacement_count": len(replacement_tasks),
            "reasoning": reasoning,
            "model_used": replan_result.get("model_used"),
            "message": (
                f"Tarea '{task.get('name', original_task_id)}' replanificada: "
                f"{len(replacement_tasks)} tareas de reemplazo — {reasoning}"
            )
        })

        logger.info(
            f"Tarea {original_task_id} replanificada exitosamente: "
            f"{len(replacement_tasks)} tareas de reemplazo"
        )
        return True

    def _handle_task_split(self, task: dict, result: dict, plan: dict,
                           completed_tasks: dict, on_progress=None) -> bool:
        """Gestiona la división de una tarea por contexto excedido.

        Llama al planificador para dividir la tarea en subtareas,
        las inserta en el plan actual y actualiza las dependencias
        de las demás tareas que dependían de la original.

        Returns:
            True si la división fue exitosa, False si falló.
        """
        original_task_id = task["id"]
        tokens_needed = result.get("tokens_needed", 0)
        max_context = result.get("max_available_context", 0)

        logger.info(
            f"Iniciando división de tarea {original_task_id}: "
            f"tokens_needed={tokens_needed}, max_context={max_context}"
        )

        # Adaptación a Planner OOP: split_task_into_subtasks(project_id, task_id, reason)
        reason = (
            f"Contexto excedido: necesitaba ~{tokens_needed} tokens, "
            f"máximo disponible {max_context}"
        )
        try:
            split_result = self._planner.split_task_into_subtasks(
                self.project_id or "unknown",
                original_task_id,
                reason,
            )
            # Puente de interfaz: la nueva firma retorna {"subtasks": [...], ...}
            # El orchestrador espera {"success": ..., "subtasks": [...]}  
            subtasks = split_result.get("subtasks", [])
            if not subtasks:
                logger.error(f"División de tarea {original_task_id} no produjo subtareas")
                return False
            split_result = {
                "success": True,
                "subtasks": subtasks,
                "model_used": split_result.get("model_used"),
            }
        except Exception as e:
            logger.error(f"Error en split_task_into_subtasks OOP para {original_task_id}: {e}")
            return False

        if not split_result.get("success"):
            logger.error(
                f"No se pudo dividir la tarea {original_task_id}: "
                f"{split_result.get('error', 'Error desconocido')}"
            )
            return False

        subtasks = split_result["subtasks"]
        if not subtasks:
            logger.error(f"División de tarea {original_task_id} no produjo subtareas")
            return False

        # Marcar la tarea original como dividida (no como fallida ni completada)
        task["status"] = "split"
        task["result"] = {
            "success": False,
            "action_required": "split_task",
            "diagnosis": result.get("diagnosis", "Tarea dividida por contexto excedido"),
            "split_into": [st["id"] for st in subtasks],
            "model_used": split_result.get("model_used")
        }

        # Reemplazar referencias a la tarea original en las dependencias
        # Si otra tarea dependía de la original, ahora depende de la última subtarea
        last_subtask_id = subtasks[-1]["id"]
        for t in plan.get("tasks", []):
            if t["id"] == original_task_id:
                continue
            deps = t.get("depends_on", [])
            if original_task_id in deps:
                t["depends_on"] = [last_subtask_id if d == original_task_id else d for d in deps]
                logger.info(
                    f"Tarea {t['id']} actualizada: depende de {last_subtask_id} "
                    f"(era {original_task_id})"
                )

        # Insertar las subtareas en el plan
        plan["tasks"].extend(subtasks)

        # Notificar via evento de progreso (Cambio 4)
        self._emit(on_progress, {
            "type": "task_split",
            "original_task_id": original_task_id,
            "original_task_name": task.get("name", ""),
            "subtask_ids": [st["id"] for st in subtasks],
            "subtask_count": len(subtasks),
            "tokens_needed": tokens_needed,
            "max_available_context": max_context,
            "model_used": split_result.get("model_used"),
            "message": (
                f"Tarea '{task.get('name', original_task_id)}' dividida en "
                f"{len(subtasks)} subtareas por contexto excedido "
                f"(necesitaba ~{tokens_needed} tokens, máximo {max_context})"
            )
        })

        logger.info(
            f"Tarea {original_task_id} dividida exitosamente en "
            f"{len(subtasks)} subtareas: {[st['id'] for st in subtasks]}"
        )
        return True

    def _execute_tasks(self, plan: dict, on_progress=None) -> dict:
        try:
            completed_tasks = {}
            failed_tasks = {}
            tasks = plan.get("tasks", [])
            max_iterations = len(tasks) * 3

            # FASE 3: Pre-poblar con tareas ya completadas (resume/checkpoint)
            for t in tasks:
                if t.get("status") == "completed" and t.get("result"):
                    completed_tasks[t["id"]] = t["result"]
            
            for iteration in range(max_iterations):
                pending = [t for t in tasks if t["status"] in ("pending", "running")]
                
                if not pending:
                    break
                
                executable = []
                split_task_ids = {t["id"] for t in tasks if t["status"] == "split"}
                replanned_task_ids = {t["id"] for t in tasks if t["status"] == "replanned"}
                for task in pending:
                    if task["status"] != "pending":
                        continue
                    deps = task.get("depends_on", [])
                    if all(dep_id in completed_tasks or dep_id in split_task_ids or dep_id in replanned_task_ids for dep_id in deps):
                        executable.append(task)
                
                if not executable:
                    if pending:
                        for task in pending:
                            task["status"] = "failed"
                            failed_tasks[task["id"]] = {
                                "diagnosis": "Bloqueo de dependencias",
                                "attempts_used": 0
                            }
                        self._persist_plan(plan)
                    break
                
                if len(executable) == 1:
                    task = executable[0]
                    task["status"] = "running"
                    self._persist_plan(plan)
                    if hasattr(self, 'checkpoint_mgr') and self.checkpoint_mgr:
                        self.checkpoint_mgr.save(self.current_plan)
                        n_completed = sum(1 for t in self.current_plan["tasks"] if t["status"] == "completed")
                        n_total = len(self.current_plan["tasks"])
                        self._emit(on_progress, {
                            "type": "checkpoint_saved",
                            "project_id": self.project_id,
                            "tasks_completed": n_completed,
                            "tasks_total": n_total
                        })
                    
                    self._emit(on_progress, {
                        "type": "task_started",
                        "task_id": task["id"],
                        "task_name": task["name"],
                        "task_type": task["task_type"]
                    })
                    
                    result = self._run_task(task)
                    
                    # FASE 2: Si la tarea requiere división, dividirla y continuar
                    if result.get("action_required") == "split_task":
                        split_ok = self._handle_task_split(
                            task, result, plan, completed_tasks, on_progress
                        )
                        if not split_ok:
                            # Si la división falló, marcar como fallida
                            task["status"] = "failed"
                            task["result"] = result
                            failed_tasks[task["id"]] = {
                                "diagnosis": result.get("diagnosis", "No se pudo dividir la tarea"),
                                "attempts_used": 0
                            }
                            self._emit(on_progress, {
                                "type": "task_failed",
                                "task_id": task["id"],
                                "task_name": task["name"],
                                "diagnosis": result.get("diagnosis", "No se pudo dividir la tarea"),
                                "attempts_used": 0
                            })
                        self._persist_plan(plan)
                        if hasattr(self, 'checkpoint_mgr') and self.checkpoint_mgr:
                            self.checkpoint_mgr.save(self.current_plan)
                        continue
                    
                    if result.get("success"):
                        task["status"] = "completed"
                        task["result"] = result
                        task["model_used"] = result.get("model_used")
                        completed_tasks[task["id"]] = result
                        self._emit(on_progress, {
                            "type": "task_completed",
                            "task_id": task["id"],
                            "task_name": task["name"],
                            "criterion_passed": result.get("criterion_passed", False),
                            "attempts_used": result.get("attempts_used", 0),
                            "model_used": result.get("model_used"),
                            "filename": result.get("filename")
                        })
                    else:
                        task["status"] = "failed"
                        task["result"] = result

                        # F1+F2: Si se agotaron los intentos, intentar replanificar
                        attempts = result.get("attempts_used", 0)
                        if attempts >= 3:
                            replan_ok = self._handle_task_replan(
                                task, result, plan, completed_tasks, on_progress
                            )
                            if replan_ok:
                                # No es failed, fue replanificada
                                self._persist_plan(plan)
                                if hasattr(self, 'checkpoint_mgr') and self.checkpoint_mgr:
                                    self.checkpoint_mgr.save(self.current_plan)
                                continue
                            # Si la replanificación falló, queda como failed

                        failed_tasks[task["id"]] = {
                            "diagnosis": result.get("diagnosis", "Fallo desconocido"),
                            "attempts_used": result.get("attempts_used", 0)
                        }
                        self._emit(on_progress, {
                            "type": "task_failed",
                            "task_id": task["id"],
                            "task_name": task["name"],
                            "diagnosis": result.get("diagnosis", "Fallo desconocido"),
                            "attempts_used": result.get("attempts_used", 0)
                        })
                    
                    self._persist_plan(plan)
                    if hasattr(self, 'checkpoint_mgr') and self.checkpoint_mgr:
                        self.checkpoint_mgr.save(self.current_plan)
                        n_completed = sum(1 for t in self.current_plan["tasks"] if t["status"] == "completed")
                        n_total = len(self.current_plan["tasks"])
                        self._emit(on_progress, {
                            "type": "checkpoint_saved",
                            "project_id": self.project_id,
                            "tasks_completed": n_completed,
                            "tasks_total": n_total
                        })
                else:
                    for task in executable:
                        task["status"] = "running"
                    self._persist_plan(plan)
                    if hasattr(self, 'checkpoint_mgr') and self.checkpoint_mgr:
                        self.checkpoint_mgr.save(self.current_plan)
                        n_completed = sum(1 for t in self.current_plan["tasks"] if t["status"] == "completed")
                        n_total = len(self.current_plan["tasks"])
                        self._emit(on_progress, {
                            "type": "checkpoint_saved",
                            "project_id": self.project_id,
                            "tasks_completed": n_completed,
                            "tasks_total": n_total
                        })
                    
                    for task in executable:
                        self._emit(on_progress, {
                            "type": "task_started",
                            "task_id": task["id"],
                            "task_name": task["name"],
                            "task_type": task["task_type"]
                        })
                    
                    executor = ParallelExecutor(max_workers=min(3, len(executable)))
                    parallel_results = executor.run(executable, self._run_task)
                    
                    for task in executable:
                        result = parallel_results["results"].get(task["id"])
                        if result is None:
                            error_msg = parallel_results["errors"].get(task["id"], "Error desconocido en ejecución paralela")
                            task["status"] = "failed"
                            task["result"] = {"diagnosis": error_msg}
                            failed_tasks[task["id"]] = {"diagnosis": error_msg, "attempts_used": 0}
                            self._emit(on_progress, {
                                "type": "task_failed",
                                "task_id": task["id"],
                                "task_name": task["name"],
                                "diagnosis": error_msg,
                                "attempts_used": 0
                            })
                            continue
                        
                        if result.get("success"):
                            task["status"] = "completed"
                            task["result"] = result
                            task["model_used"] = result.get("model_used")
                            completed_tasks[task["id"]] = result
                            self._emit(on_progress, {
                                "type": "task_completed",
                                "task_id": task["id"],
                                "task_name": task["name"],
                                "criterion_passed": result.get("criterion_passed", False),
                                "attempts_used": result.get("attempts_used", 0),
                                "model_used": result.get("model_used"),
                                "filename": result.get("filename")
                            })
                        else:
                            task["status"] = "failed"
                            task["result"] = result

                            # F1+F2: Si se agotaron los intentos, intentar replanificar
                            attempts = result.get("attempts_used", 0)
                            if attempts >= 3:
                                replan_ok = self._handle_task_replan(
                                    task, result, plan, completed_tasks, on_progress
                                )
                                if replan_ok:
                                    continue
                            # Si no se replanificó, queda como failed

                            failed_tasks[task["id"]] = {
                                "diagnosis": result.get("diagnosis", "Fallo desconocido"),
                                "attempts_used": result.get("attempts_used", 0)
                            }
                            self._emit(on_progress, {
                                "type": "task_failed",
                                "task_id": task["id"],
                                "task_name": task["name"],
                                "diagnosis": result.get("diagnosis", "Fallo desconocido"),
                                "attempts_used": result.get("attempts_used", 0)
                            })
                    
                    self._persist_plan(plan)
                    if hasattr(self, 'checkpoint_mgr') and self.checkpoint_mgr:
                        self.checkpoint_mgr.save(self.current_plan)
                        n_completed = sum(1 for t in self.current_plan["tasks"] if t["status"] == "completed")
                        n_total = len(self.current_plan["tasks"])
                        self._emit(on_progress, {
                            "type": "checkpoint_saved",
                            "project_id": self.project_id,
                            "tasks_completed": n_completed,
                            "tasks_total": n_total
                        })
            
            tasks_summary = []
            for task in tasks:
                result = task.get("result") or {}
                tasks_summary.append({
                    "id": task["id"],
                    "name": task["name"],
                    "status": task["status"],
                    "criterion_passed": result.get("criterion_passed", False),
                    "attempts_used": result.get("attempts_used", 0),
                    "filename": result.get("filename") if result.get("success") else None,
                    "model_used": task.get("model_used") or result.get("model_used"),
                    "diagnosis": result.get("diagnosis") if not result.get("success") else None
                })
            
            all_completed = all(t["status"] in ("completed", "split", "replanned") for t in tasks)
            
            return {
                "project_id": plan.get("project_id"),
                "success": all_completed,
                "completed": len(completed_tasks),
                "failed": len(failed_tasks),
                "tasks_summary": tasks_summary,
                "plan_path": str(Path(__file__).parents[1] / "specs" / plan.get("project_id") / "plan.json")
            }
            
        except Exception as e:
            logger.error(f"Error in _execute_tasks: {e}")
            return {
                "project_id": plan.get("project_id"),
                "success": False,
                "completed": 0,
                "failed": len(plan.get("tasks", [])),
                "tasks_summary": [],
                "plan_path": "",
                "error": str(e)
            }

    def _save_pipeline_state(self, phase: PipelinePhase, error: str = None) -> None:
        """Guarda el estado del pipeline para reanudación futura.

        Toma una foto completa del plan actual (incluyendo subtareas
        dinámicas de FASE 2) y la guarda en pipeline_state.json.
        """
        if not self.project_id or not self.current_plan:
            return
        try:
            state = PipelineState(
                project_id=self.project_id,
                phase=phase.value,
                current_task_index=-1,
                user_prompt=self.current_plan.get("spec_summary", ""),
                plan_tasks=self.current_plan.get("tasks", []),
                log=[f"Phase: {phase.value}"],
                error=error
            )
            self._pipeline_mgr.save(state)
            logger.info(f"PipelineState guardado: fase={phase.value}")
        except Exception as e:
            logger.error(f"Error guardando PipelineState: {e}")

    def resume(self, project_id: str, on_progress=None) -> dict:
        """Reanuda un pipeline interrumpido desde el estado guardado.

        Carga el pipeline_state.json, reconstruye el plan completo
        (incluyendo subtareas dinámicas de FASE 2) y continúa
        la ejecución desde donde se quedó.

        Returns:
            Resultado del pipeline reanudado.
        """
        try:
            logging.getLogger('agents.generator').setLevel(logging.WARNING)
            logging.getLogger('mcp.server').setLevel(logging.WARNING)
            logging.getLogger('core.validator').setLevel(logging.WARNING)
            logging.getLogger('core.llm_cache').setLevel(logging.WARNING)

            state = self._pipeline_mgr.load(project_id)
            if state is None:
                return {
                    "success": False,
                    "error": f"No se encontró estado guardado para {project_id}",
                    "project_id": project_id
                }

            if state.phase in (PipelinePhase.COMPLETED.value,
                               PipelinePhase.CANCELLED.value):
                return {
                    "success": False,
                    "error": f"Pipeline en estado '{state.phase}', no se puede reanudar",
                    "project_id": project_id
                }

            # Reconstruir el plan desde el estado guardado
            self.project_id = project_id
            self.current_plan = {
                "project_id": project_id,
                "spec_summary": state.user_prompt,
                "tasks": state.plan_tasks
            }
            self.checkpoint_mgr = CheckpointManager(project_id)

            # Contar tareas completadas para el evento
            completed_count = sum(
                1 for t in state.plan_tasks if t.get("status") == "completed"
            )
            split_count = sum(
                1 for t in state.plan_tasks if t.get("status") == "split"
            )

            self._emit(on_progress, {
                "type": "pipeline_resumed",
                "project_id": project_id,
                "phase": state.phase,
                "tasks_completed": completed_count,
                "tasks_split": split_count,
                "total_tasks": len(state.plan_tasks),
                "message": (
                    f"Pipeline reanudado: {completed_count} completadas, "
                    f"{split_count} divididas, "
                    f"{len(state.plan_tasks) - completed_count - split_count} pendientes"
                )
            })

            # Actualizar fase a EXECUTING y guardar
            self._save_pipeline_state(PipelinePhase.EXECUTING)

            result = self._execute_tasks(self.current_plan, on_progress)

            if result.get("success"):
                self._save_pipeline_state(PipelinePhase.COMPLETED)
                self._pipeline_mgr.clear(project_id)
            else:
                self._save_pipeline_state(
                    PipelinePhase.FAILED,
                    error=result.get("error", "Pipeline fallido tras reanudación")
                )

            if hasattr(self, 'checkpoint_mgr') and self.checkpoint_mgr:
                self.checkpoint_mgr.clear()

            doc_result = self._generate_documentation(self.current_plan, on_progress)
            result["documentation"] = doc_result

            return result

        except Exception as e:
            logger.error(f"Error en resume: {e}")
            return {
                "success": False,
                "error": f"Excepción al reanudar pipeline: {str(e)}",
                "project_id": project_id
            }

    def run(self, spec_path: str, on_progress=None) -> dict:
        try:
            # A5: Reducir verbosidad de logs de módulos secundarios
            logging.getLogger('agents.generator').setLevel(logging.WARNING)
            logging.getLogger('mcp.server').setLevel(logging.WARNING)
            logging.getLogger('core.validator').setLevel(logging.WARNING)
            logging.getLogger('core.llm_cache').setLevel(logging.WARNING)
            
            # Health check via Model Broker
            try:
                from model_broker.broker import ModelBroker
                _broker = ModelBroker()
                _models = _broker.get_models()
                self._emit(on_progress, {
                    "type": "health_check",
                    "broker_available": True,
                    "total_models": len(_models),
                })
            except Exception as e:
                logger.warning(f"MB health check failed: {e}")
                self._emit(on_progress, {
                    "type": "health_check",
                    "broker_available": False,
                    "total_models": 0,
                })
            
            self._emit(on_progress, {"type": "parsing_spec", "path": spec_path})

            # Adaptación a Planner OOP: generate_plan recibe el contenido del spec
            # y hace parsing + generación internamente
            try:
                spec_content = Path(spec_path).read_text(encoding="utf-8")
            except Exception as e:
                return {
                    "success": False,
                    "error": f"Error leyendo spec: {e}",
                    "project_id": None
                }

            self._emit(on_progress, {"type": "spec_parsed", "path": spec_path})
            self._emit(on_progress, {"type": "generating_plan"})

            try:
                plan = self._planner.generate_plan(spec_content)
            except Exception as e:
                logger.error(f"Error en Planner.generate_plan: {e}")
                return {
                    "success": False,
                    "error": f"Error generando plan: {e}",
                    "project_id": None
                }

            # Puente de interfaz: la nueva firma retorna "tasks" directamente
            if plan.get("validation_errors"):
                logger.warning(f"Plan generado con {len(plan['validation_errors'])} errores de validación")

            # Normalización: Planner OOP usa "dependencies" pero el
            # orchestrador y agentes esperan "depends_on"
            for t in plan.get("tasks", []):
                if "dependencies" in t and "depends_on" not in t:
                    t["depends_on"] = t.pop("dependencies")
                # Asegurar que cada tarea tiene status inicial
                if "status" not in t:
                    t["status"] = "pending"
            
            self.current_plan = plan
            self.project_id = plan["project_id"]
            self.checkpoint_mgr = CheckpointManager(self.project_id)

            # FASE 3: Guardar estado en fase PLANNING
            self._save_pipeline_state(PipelinePhase.PLANNING)

            if self.checkpoint_mgr.exists():
                restored_plan = self.checkpoint_mgr.restore()
                if restored_plan:
                    self.current_plan = restored_plan
                    self._emit(on_progress, {
                        "type": "checkpoint_restored",
                        "project_id": self.project_id,
                        "tasks_completed": sum(1 for t in restored_plan["tasks"] if t["status"] == "completed")
                    })
                    # FASE 3: Actualizar estado a EXECUTING al reanudar por checkpoint
                    self._save_pipeline_state(PipelinePhase.EXECUTING)

                    result = self._execute_tasks(self.current_plan, on_progress)
                    self.checkpoint_mgr.clear()
                    doc_result = self._generate_documentation(self.current_plan, on_progress)
                    result["documentation"] = doc_result
                    return result

            task_summaries = [
                {"id": t["id"], "name": t["name"], "status": t["status"]}
                for t in plan.get("tasks", [])
            ]
            
            self._emit(on_progress, {
                "type": "plan_generated",
                "project_id": plan["project_id"],
                "tasks_count": len(plan.get("tasks", [])),
                "tasks": task_summaries
            })

            # FASE 3: Actualizar estado a EXECUTING
            self._save_pipeline_state(PipelinePhase.EXECUTING)
            
            result = self._execute_tasks(plan, on_progress)

            if result.get("success"):
                self._save_pipeline_state(PipelinePhase.COMPLETED)
                self._pipeline_mgr.clear(self.project_id)
            else:
                self._save_pipeline_state(
                    PipelinePhase.FAILED,
                    error=result.get("error", "Pipeline fallido")
                )

            if hasattr(self, 'checkpoint_mgr'):
                self.checkpoint_mgr.clear()
      
            doc_result = self._generate_documentation(self.current_plan, on_progress)
            result["documentation"] = doc_result
            
            return result
            
        except Exception as e:
            logger.error(f"Error in run: {e}")
            # FASE 3: Guardar estado FAILED si hay excepción
            self._save_pipeline_state(
                PipelinePhase.FAILED,
                error=f"Excepción en orquestación: {str(e)}"
            )
            return {
                "success": False,
                "error": f"Excepción en orquestación: {str(e)}",
                "project_id": self.project_id
            }

    def get_status(self) -> dict:
        if not self.project_id or not self.current_plan:
            return {"status": "idle", "project_id": None}
        return {
            "status": "running",
            "project_id": self.project_id,
            "plan": self.current_plan
        }

if __name__ == "__main__":
    """Bloque de 10 validaciones atomicas para el Orquestador APA.

    Cada validacion es INDEPENDIENTE: si una falla, las demas siguen
    ejecutandose. No requiere Model Broker activo ni conexion al NAS -
    todos los externos (LLM, NAS, MB, agentes) se reemplazan con mocks
    (MagicMock / patch).

    Uso:
        cd /path/to/apa
        python3 core/orchestrator.py

    Salida esperada:
        [OK]   V01 - Instanciacion Orchestrator()
        ...
        Resultado: 10/10 pasaron, 0 fallaron
    """
    import logging as _logging
    import os as _os
    import shutil as _shutil
    import sys as _sys
    import tempfile as _tempfile
    import time as _time
    import traceback as _traceback
    from pathlib import Path as _Path
    from unittest.mock import MagicMock, patch

    _logging.basicConfig(level=_logging.ERROR)
    for _name in ["__main__", "core.orchestrator", "core.planner",
                   "core.checkpoint", "agents.generator", "agents.corrector",
                   "agents.documenter", "core.router", "mcp.server",
                   "core.broker", "core.pipeline_state"]:
        _logging.getLogger(_name).setLevel(_logging.WARNING)

    # Contador global de resultados
    _PASS = 0
    _FAIL = 0

    def _print_result(idx, name, ok, msg):
        """Imprime [OK]/[FAIL] con formato consistente y actualiza contadores."""
        global _PASS, _FAIL
        status = "[OK]  " if ok else "[FAIL]"
        if ok:
            _PASS += 1
        else:
            _FAIL += 1
        print(f"{status} V{idx:02d} - {name}")
        if msg:
            print(f"         {msg}")

    def _run_validation(idx, name, fn):
        """Ejecuta una validacion, capturando cualquier excepcion.

        Garantiza que un fallo en una validacion NO impida las siguientes.
        """
        try:
            ok, msg = fn()
            if not isinstance(ok, bool):
                ok = bool(ok)
            if not isinstance(msg, str):
                msg = str(msg)
            _print_result(idx, name, ok, msg)
        except Exception as e:
            tb_lines = _traceback.format_exc().strip().split("\n")
            last = tb_lines[-1] if tb_lines else str(e)
            _print_result(idx, name, False, f"Excepcion: {last}")

    # --- V01: Instanciacion del Orquestador -----------------------------
    def _v01_instantiation():
        """Verifica que Orchestrator() se crea sin error incluso sin MB/NAS."""
        o = Orchestrator()
        assert o is not None, "Orchestrator() devolvio None"
        # El orquestador es resiliente: generator/corrector/documenter pueden
        # ser None si los agentes no inicializan, pero la instancia se crea.
        return True, "Orchestrator() instanciado (modo resiliente OK)"

    # --- V02: _persist_plan(plan) ---------------------------------------
    def _v02_persist_plan():
        """Verifica que _persist_plan escribe plan.json en disco."""
        o = Orchestrator()
        test_id = f"test-atomic-v02-{int(_time.time())}"
        o.project_id = test_id
        plan = {
            "project_id": test_id,
            "spec_summary": "plan de prueba V02",
            "tasks": [
                {"id": "T1", "name": "tarea mock", "status": "pending"}
            ],
        }
        o._persist_plan(plan)
        plan_path = _Path(__file__).parents[1] / "specs" / test_id / "plan.json"
        if not plan_path.exists():
            return False, f"No se creo {plan_path}"
        loaded = json.loads(plan_path.read_text(encoding="utf-8"))
        if loaded.get("project_id") != test_id:
            return False, "project_id no coincide en plan.json"
        # Limpieza
        try:
            _shutil.rmtree(_Path(__file__).parents[1] / "specs" / test_id)
        except Exception:
            pass
        return True, "plan.json escrito en specs/<project_id>/ y verificado"

    # --- V03: _generate_documentation(plan) -----------------------------
    def _v03_generate_documentation():
        """Verifica que _generate_documentation retorna dict con success."""
        o = Orchestrator()
        test_id = f"test-atomic-v03-{int(_time.time())}"
        o.project_id = test_id
        # Mock del documenter: evita llamada al LLM
        o.documenter = MagicMock()
        o.documenter.document_generated_files.return_value = {
            "success": True,
            "doc_path": f"specs/{test_id}/docs.md",
            "files_documented": 1,
        }
        plan = {
            "project_id": test_id,
            "tasks": [
                {
                    "id": "T1", "name": "tarea mock", "status": "completed",
                    "result": {
                        "code": "print('hi')", "filename": "hi.py",
                        "success": True,
                    },
                    "acceptance_criterion": "imprime hi",
                },
            ],
        }
        result = o._generate_documentation(plan)
        if not isinstance(result, dict):
            return False, f"resultado no es dict: {type(result)}"
        if "success" not in result:
            return False, f"falta 'success' en resultado: {list(result.keys())}"
        if not result.get("success"):
            return False, f"documenter mock devolvio success=False: {result}"
        # Limpieza
        try:
            _shutil.rmtree(_Path(__file__).parents[1] / "specs" / test_id)
        except Exception:
            pass
        return True, (f"_generate_documentation devolvio dict con success=True "
                     f"(files={result.get('files_documented')})")

    # --- V04: _run_task(task) -------------------------------------------
    def _v04_run_task():
        """Verifica que _run_task marca la tarea como completada (con mock)."""
        o = Orchestrator()
        o.project_id = "test-atomic-v04"
        o.current_plan = {"tasks": []}
        # Mock del generator: evita llamada al LLM y al sandbox
        o.generator = MagicMock()
        o.generator.generate_and_test.return_value = {
            "success": True,
            "code": "print('ok')",
            "filename": "ok.py",
            "execution": {"criterion_passed": True},
            "model_used": "mock-model",
        }
        o.generator.save_to_sandbox.return_value = {"success": True}
        task = {
            "id": "T1", "name": "mock task",
            "description": "mock", "acceptance_criterion": "criterion mock",
            "depends_on": [], "status": "pending",
            "task_type": "code_generation",
        }
        result = o._run_task(task)
        if not isinstance(result, dict):
            return False, f"resultado no es dict: {type(result)}"
        if not result.get("success"):
            return False, f"task fallo pese a mock exitoso: {result}"
        if not result.get("criterion_passed"):
            return False, f"criterion_passed=False inesperado: {result}"
        return True, f"_run_task completo con exito (filename={result.get('filename')})"

    # --- V05: _handle_task_replan --------------------------------------
    def _v05_handle_task_replan():
        """Verifica que _handle_task_replan genera una tarea de reemplazo."""
        o = Orchestrator()
        o.project_id = "test-atomic-v05"
        # Mock del planner
        o._planner = MagicMock()
        replacement_task = {
            "id": "T1_replan", "name": "tarea reemplazo",
            "description": "version corregida", "task_type": "code_generation",
            "dependencies": [], "depends_on": [], "inputs": [], "output": "",
            "acceptance_criteria": "criterion", "acceptance_criterion": "criterion",
            "programming_language": "python", "executor": "apa",
            "priority": "high", "status": "pending",
        }
        o._planner.replan_task.return_value = {
            "task": replacement_task,
            "original_task_id": "T1",
            "replan_reason": "fallo simulado V05",
        }
        # Tarea original "fallida"
        task = {
            "id": "T1", "name": "tarea original",
            "depends_on": [], "status": "failed",
            "result": {"success": False, "attempts_used": 3,
                       "diagnosis": "fallo mock V05",
                       "code": "", "filename": ""},
        }
        plan = {
            "project_id": "test-atomic-v05",
            "tasks": [task, {
                "id": "T2", "name": "tarea dependiente",
                "depends_on": ["T1"], "status": "pending",
            }],
        }
        completed_tasks = {}
        ok = o._handle_task_replan(task, task["result"], plan, completed_tasks)
        if not ok:
            return False, "_handle_task_replan devolvio False"
        if task.get("status") != "replanned":
            return False, f"task.status={task.get('status')} (esperaba 'replanned')"
        # Verificar que la tarea de reemplazo fue anadida al plan
        replacement_added = any(t["id"] == "T1_replan" for t in plan["tasks"])
        if not replacement_added:
            return False, "tarea de reemplazo T1_replan no anadida al plan"
        return True, (f"replan OK: T1 marcada como 'replanned', "
                     f"{len(plan['tasks'])} tareas ahora en plan")

    # --- V06: _handle_task_split ---------------------------------------
    def _v06_handle_task_split():
        """Verifica que _handle_task_split divide la tarea en subtareas."""
        o = Orchestrator()
        o.project_id = "test-atomic-v06"
        o._planner = MagicMock()
        subtasks = [
            {"id": "T1.1", "name": "subtarea 1", "task_type": "code_generation",
             "depends_on": [], "status": "pending"},
            {"id": "T1.2", "name": "subtarea 2", "task_type": "code_generation",
             "depends_on": ["T1.1"], "status": "pending"},
        ]
        o._planner.split_task_into_subtasks.return_value = {
            "subtasks": subtasks,
            "original_task_id": "T1",
            "split_reason": "contexto excedido V06",
            "total_subtasks": 2,
        }
        task = {
            "id": "T1", "name": "tarea grande",
            "depends_on": [], "status": "running",
            "result": {},
        }
        result = {
            "success": False,
            "action_required": "split_task",
            "diagnosis": "contexto excedido",
            "tokens_needed": 8000, "max_available_context": 4000,
        }
        plan = {
            "project_id": "test-atomic-v06",
            "tasks": [task, {
                "id": "T2", "name": "tarea dependiente",
                "depends_on": ["T1"], "status": "pending",
            }],
        }
        completed_tasks = {}
        ok = o._handle_task_split(task, result, plan, completed_tasks)
        if not ok:
            return False, "_handle_task_split devolvio False"
        if task.get("status") != "split":
            return False, f"task.status={task.get('status')} (esperaba 'split')"
        # Verificar que las subtareas fueron anadidas
        added = sum(1 for t in plan["tasks"] if t["id"] in ("T1.1", "T1.2"))
        if added != 2:
            return False, f"solo {added}/2 subtareas anadidas"
        # Verificar redireccion de dependencias: T2 depende de T1.2
        t2 = next((t for t in plan["tasks"] if t["id"] == "T2"), None)
        if t2 and "T1.2" not in t2.get("depends_on", []):
            return False, f"dependencia de T2 no redirigida a T1.2: {t2.get('depends_on')}"
        return True, "split OK: 2 subtareas anadidas, dependencias redirigidas"

    # --- V07: _execute_tasks(plan) -------------------------------------
    def _v07_execute_tasks():
        """Verifica que _execute_tasks ejecuta todas las tareas del plan."""
        o = Orchestrator()
        o.project_id = f"test-atomic-v07-{int(_time.time())}"
        # Mock directo de _run_task para evitar llamada al LLM
        def mock_run_task(task):
            return {
                "success": True, "code": "print('ok')",
                "filename": f"{task['id']}.py",
                "criterion_passed": True, "attempts_used": 1,
                "model_used": "mock",
            }
        o._run_task = mock_run_task
        o.checkpoint_mgr = None  # evitar checkpoint durante test
        plan = {
            "project_id": o.project_id,
            "tasks": [
                {"id": "T1", "name": "tarea 1", "depends_on": [],
                 "status": "pending", "task_type": "code_generation"},
                {"id": "T2", "name": "tarea 2", "depends_on": ["T1"],
                 "status": "pending", "task_type": "code_generation"},
            ],
        }
        o.current_plan = plan
        result = o._execute_tasks(plan)
        if not isinstance(result, dict):
            return False, f"resultado no es dict: {type(result)}"
        if not result.get("success"):
            return False, f"_execute_tasks no completo: {result}"
        if result.get("completed") != 2:
            return False, f"completadas={result.get('completed')} (esperaba 2)"
        # Limpieza
        try:
            _shutil.rmtree(_Path(__file__).parents[1] / "specs" / o.project_id)
        except Exception:
            pass
        return True, f"_execute_tasks completo 2/2 tareas (failed={result.get('failed', 0)})"

    # --- V08: resume(project_id) ---------------------------------------
    def _v08_resume():
        """Verifica que resume() carga un estado guardado y continua."""
        o = Orchestrator()
        test_id = f"test-atomic-v08-{int(_time.time())}"
        # Crear estado guardado simulando 1 tarea completada y 1 pendiente
        specs_dir = _Path(__file__).parents[1] / "specs"
        proj_dir = specs_dir / test_id
        proj_dir.mkdir(parents=True, exist_ok=True)
        state = {
            "project_id": test_id,
            "phase": "executing",  # no COMPLETED ni CANCELLED -> se puede reanudar
            "current_task_index": -1,
            "user_prompt": "spec mock V08",
            "plan_tasks": [
                {"id": "T1", "name": "tarea ya hecha", "status": "completed",
                 "result": {"success": True, "code": "x=1", "filename": "x.py"}},
                {"id": "T2", "name": "tarea pendiente", "status": "pending",
                 "depends_on": ["T1"], "task_type": "code_generation"},
            ],
            "scaling_state": {}, "created_at": _time.time(),
            "updated_at": _time.time(), "log": [], "error": None,
        }
        state_path = proj_dir / "pipeline_state.json"
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        # Mock _execute_tasks para no ejecutar realmente
        def mock_exec(plan, on_progress=None):
            return {"project_id": test_id, "success": True,
                    "completed": 2, "failed": 0,
                    "tasks_summary": [], "plan_path": str(state_path)}
        o._execute_tasks = mock_exec
        # Mock _generate_documentation para no llamar LLM
        o._generate_documentation = MagicMock(return_value={"success": True, "skipped": True})
        # Mock checkpoint_mgr
        o.checkpoint_mgr = MagicMock()
        o.checkpoint_mgr.exists.return_value = False
        result = o.resume(test_id)
        # Limpieza
        try:
            _shutil.rmtree(proj_dir)
        except Exception:
            pass
        if not isinstance(result, dict):
            return False, f"resultado no es dict: {type(result)}"
        if result.get("project_id") != test_id:
            return False, f"project_id={result.get('project_id')} (esperaba {test_id})"
        if "documentation" not in result:
            return False, "falta 'documentation' en resultado"
        return True, f"resume OK: cargo estado '{state['phase']}' y continuo pipeline"

    # --- V09: run(spec_path) -------------------------------------------
    def _v09_run():
        """Verifica que run() ejecuta el pipeline completo (con mocks)."""
        o = Orchestrator()
        test_id = f"test-atomic-v09-{int(_time.time())}"
        # Spec minimo en tmp
        spec_path = _Path(_tempfile.gettempdir()) / f"spec_v09_{test_id}.md"
        spec_path.write_text(
            "# Proyecto mock V09\n\n## Objetivo\n\nDemo de run() con mocks.\n",
            encoding="utf-8",
        )
        # Mock del planner
        o._planner = MagicMock()
        o._planner.generate_plan.return_value = {
            "project_id": test_id,
            "generated_at": "2026-01-01T00:00:00Z",
            "tasks": [
                {"id": "T1", "name": "tarea mock", "task_type": "code_generation",
                 "depends_on": [], "status": "pending",
                 "acceptance_criterion": "criterion mock"},
            ],
            "total_tasks": 1,
            "validation_errors": [],
            "spec_summary": "Proyecto mock V09",
            "plan_type": "simple",
        }
        # Mock _execute_tasks y _generate_documentation para evitar red/LLM
        def mock_exec(plan, on_progress=None):
            return {"project_id": test_id, "success": True,
                    "completed": 1, "failed": 0,
                    "tasks_summary": [{"id": "T1", "name": "tarea mock",
                                        "status": "completed"}],
                    "plan_path": str(spec_path)}
        o._execute_tasks = mock_exec
        o._generate_documentation = MagicMock(return_value={"success": True, "skipped": True})
        # Nota: MB health check en run() tiene try/except que maneja
        # gracefully la ausencia de model_broker. No requiere mock extra.
        result = o.run(str(spec_path))
        # Limpieza
        try:
            spec_path.unlink()
        except Exception:
            pass
        try:
            _shutil.rmtree(_Path(__file__).parents[1] / "specs" / test_id)
        except Exception:
            pass
        if not isinstance(result, dict):
            return False, f"resultado no es dict: {type(result)}"
        if result.get("project_id") != test_id:
            return False, f"project_id={result.get('project_id')} (esperaba {test_id})"
        if "documentation" not in result:
            return False, "falta 'documentation' en resultado"
        return True, f"run OK: pipeline completo con mocks (completed={result.get('completed')})"

    # --- V10: get_status() --------------------------------------------
    def _v10_get_status():
        """Verifica que get_status() retorna dict con estructura esperada."""
        # Caso A: orchestrator sin state (idle)
        o = Orchestrator()
        status = o.get_status()
        if not isinstance(status, dict):
            return False, f"status no es dict: {type(status)}"
        if status.get("status") != "idle":
            return False, f"status={status.get('status')} (esperaba 'idle')"
        if status.get("project_id") is not None:
            return False, f"project_id={status.get('project_id')} (esperaba None)"
        # Caso B: orchestrator con state (running)
        o2 = Orchestrator()
        o2.project_id = "test-atomic-v10"
        o2.current_plan = {"project_id": "test-atomic-v10", "tasks": []}
        status2 = o2.get_status()
        if status2.get("status") != "running":
            return False, f"status2.status={status2.get('status')} (esperaba 'running')"
        if status2.get("project_id") != "test-atomic-v10":
            return False, f"project_id no propagado: {status2.get('project_id')}"
        if "plan" not in status2:
            return False, "falta 'plan' en status2"
        return True, "get_status OK en ambos estados (idle y running)"

    # --- Ejecucion de las 10 validaciones -------------------------------
    print("=" * 72)
    print("Orquestador APA - 10 validaciones atomicas (no requieren MB/NAS)")
    print("=" * 72)

    _run_validation(1,  "Instanciacion Orchestrator()",       _v01_instantiation)
    _run_validation(2,  "_persist_plan(plan)",                 _v02_persist_plan)
    _run_validation(3,  "_generate_documentation(plan)",      _v03_generate_documentation)
    _run_validation(4,  "_run_task(task)",                    _v04_run_task)
    _run_validation(5,  "_handle_task_replan(...)",           _v05_handle_task_replan)
    _run_validation(6,  "_handle_task_split(...)",            _v06_handle_task_split)
    _run_validation(7,  "_execute_tasks(plan)",              _v07_execute_tasks)
    _run_validation(8,  "resume(project_id)",                  _v08_resume)
    _run_validation(9,  "run(spec_path)",                    _v09_run)
    _run_validation(10, "get_status()",                      _v10_get_status)

    print("=" * 72)
    print(f"Resultado: {_PASS}/10 pasaron, {_FAIL} fallaron")
    print("=" * 72)
    _sys.exit(0 if _FAIL == 0 else 1)
