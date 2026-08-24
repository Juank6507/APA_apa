# apa/core/pipeline_state.py
# v1.0 — Persistencia de progreso del pipeline para reanudación.
#
# Guarda el estado completo de un pipeline en ejecución para que,
# si se interrumpe, pueda reanudarse desde el último punto.
#
# Funcionalidad:
#   - save(): guarda el estado actual a disco
#   - load(): carga un estado previo desde disco
#   - resume(): reanuda un pipeline desde el estado guardado
#   - clear(): limpia el estado guardado
#
# El estado se guarda como JSON en el directorio specs/<project_id>/
# junto con el plan.json del proyecto.

import json
import logging
import os
import time
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field, asdict
from pathlib import Path
from enum import Enum

logger = logging.getLogger(__name__)


class PipelinePhase(Enum):
    """Fases del pipeline semi-autónomo."""
    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING = "executing"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskSnapshot:
    """Instantánea del estado de una tarea individual."""
    task_id: str = ""
    script: str = ""
    status: str = "pending"
    attempt: int = 0
    max_attempts: int = 3
    planner_output: str = ""
    coder_output: str = ""
    assembled_content: str = ""
    error: Optional[str] = None
    rejection_feedback: str = ""


@dataclass
class PipelineState:
    """Estado completo del pipeline para persistencia.

    Se guarda como JSON cuando el pipeline cambia de fase, y se
    puede cargar para reanudar desde el último punto guardado.
    """
    project_id: str = ""
    phase: str = PipelinePhase.IDLE.value
    current_task_index: int = -1
    user_prompt: str = ""
    target_file: str = ""
    model_used_planner: str = ""
    plan_tasks: List[Dict[str, Any]] = field(default_factory=list)
    scaling_state: Dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    updated_at: float = 0.0
    log: List[str] = field(default_factory=list)
    error: Optional[str] = None


class PipelineStateManager:
    """Gestor de persistencia del pipeline.

    Guarda y carga el estado del pipeline desde el directorio
    specs/<project_id>/pipeline_state.json.
    """

    def __init__(self, specs_dir: Optional[str] = None):
        """Inicializa el gestor.

        Args:
            specs_dir: Directorio base para los estados. Si es None,
                        usa el directorio por defecto del proyecto.
        """
        if specs_dir:
            self._specs_dir = Path(specs_dir)
        else:
            # Buscar el directorio specs/ del proyecto APA
            project_root = Path(__file__).resolve()
            for _ in range(6):
                candidate = project_root / "specs"
                if candidate.is_dir():
                    self._specs_dir = candidate
                    break
                project_root = project_root.parent
            else:
                self._specs_dir = Path(__file__).resolve().parent.parent / "specs"
        self._specs_dir.mkdir(parents=True, exist_ok=True)

    def _state_path(self, project_id: str) -> Path:
        """Ruta al archivo de estado para un proyecto."""
        return self._specs_dir / project_id / "pipeline_state.json"

    def save(self, state: PipelineState) -> bool:
        """Guarda el estado del pipeline a disco.

        Args:
            state: Estado a guardar.

        Returns:
            True si se guardó correctamente.
        """
        try:
            state.updated_at = time.time()
            if state.created_at == 0:
                state.created_at = state.updated_at

            state_path = self._state_path(state.project_id)
            state_path.parent.mkdir(parents=True, exist_ok=True)

            data = {
                "project_id": state.project_id,
                "phase": state.phase,
                "current_task_index": state.current_task_index,
                "user_prompt": state.user_prompt,
                "target_file": state.target_file,
                "model_used_planner": state.model_used_planner,
                "plan_tasks": state.plan_tasks,
                "scaling_state": state.scaling_state,
                "created_at": state.created_at,
                "updated_at": state.updated_at,
                "log": state.log[-50:],  # Últimas 50 líneas
                "error": state.error,
            }

            with open(state_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            logger.debug(f"PipelineState guardado: {state.project_id} ({state.phase})")
            return True

        except Exception as e:
            logger.error(f"Error guardando PipelineState: {e}")
            return False

    def load(self, project_id: str) -> Optional[PipelineState]:
        """Carga el estado del pipeline desde disco.

        Args:
            project_id: ID del proyecto.

        Returns:
            PipelineState o None si no existe.
        """
        try:
            state_path = self._state_path(project_id)
            if not state_path.exists():
                return None

            with open(state_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            state = PipelineState(
                project_id=data.get("project_id", project_id),
                phase=data.get("phase", PipelinePhase.IDLE.value),
                current_task_index=data.get("current_task_index", -1),
                user_prompt=data.get("user_prompt", ""),
                target_file=data.get("target_file", ""),
                model_used_planner=data.get("model_used_planner", ""),
                plan_tasks=data.get("plan_tasks", []),
                scaling_state=data.get("scaling_state", {}),
                created_at=data.get("created_at", 0.0),
                updated_at=data.get("updated_at", 0.0),
                log=data.get("log", []),
                error=data.get("error"),
            )

            logger.info(f"PipelineState cargado: {state.project_id} ({state.phase})")
            return state

        except Exception as e:
            logger.error(f"Error cargando PipelineState: {e}")
            return None

    def clear(self, project_id: str) -> bool:
        """Elimina el estado guardado de un proyecto.

        Args:
            project_id: ID del proyecto.

        Returns:
            True si se eliminó correctamente.
        """
        try:
            state_path = self._state_path(project_id)
            if state_path.exists():
                state_path.unlink()
                logger.debug(f"PipelineState eliminado: {project_id}")
            return True
        except Exception as e:
            logger.error(f"Error eliminando PipelineState: {e}")
            return False

    def list_states(self) -> List[Dict[str, Any]]:
        """Lista todos los proyectos con estado guardado.

        Returns:
            Lista de resúmenes de estado.
        """
        states = []
        try:
            for project_dir in self._specs_dir.iterdir():
                if not project_dir.is_dir():
                    continue
                state_file = project_dir / "pipeline_state.json"
                if not state_file.exists():
                    continue

                try:
                    with open(state_file, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    states.append({
                        "project_id": data.get("project_id", project_dir.name),
                        "phase": data.get("phase", "unknown"),
                        "current_task_index": data.get("current_task_index", -1),
                        "total_tasks": len(data.get("plan_tasks", [])),
                        "updated_at": data.get("updated_at", 0),
                        "has_error": data.get("error") is not None,
                    })
                except Exception:
                    continue
        except Exception:
            pass

        states.sort(key=lambda s: s.get("updated_at", 0), reverse=True)
        return states


# Instancia por defecto
_default_manager: Optional[PipelineStateManager] = None


def get_manager() -> PipelineStateManager:
    """Retorna el gestor de estado por defecto (singleton)."""
    global _default_manager
    if _default_manager is None:
        _default_manager = PipelineStateManager()
    return _default_manager
