# apa/interface/app/task_log_handler.py
"""
task_log_handler.py — Endpoints de bitácora de tareas de APA.

Expone endpoints para consultar la bitácora de ejecución de
tareas de un proyecto. Usa core.task_log.TaskLog si está
disponible; si no, ofrece un fallback basado en archivos.

Clases:
    TaskLogHandler: Manejador de la bitácora de tareas.

Funciones:
    register_task_log_routes: Registra GET /api/task-log/{project_id},
                               /api/task-log/{project_id}/{task_id},
                               /api/task-log/{project_id}/{task_id}/summary.
"""

import json

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))            # interface/ → resuelve 'app'
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))    # apa/ → resuelve 'core', 'config'

from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException

from app.config_apa import logger

# Importar módulo funcional — import directo con fallback gracioso
try:
    from core.task_log import TaskLog
    _HAS_TASK_LOG = True
except ImportError:
    TaskLog = None  # type: ignore[assignment, misc]
    _HAS_TASK_LOG = False


class TaskLogHandler:
    """Manejador de la bitácora de tareas.

    Gestiona la consulta de la bitácora de ejecución de tareas
    de un proyecto usando core.task_log.TaskLog si está disponible,
    o un fallback basado en archivos JSONL.

    Attributes:
        specs_dir: Ruta al directorio de especificaciones.
        task_log: Instancia de TaskLog del core (o None).
    """

    def __init__(self, specs_dir: str) -> None:
        """Inicializa el manejador de la bitácora.

        Args:
            specs_dir: Ruta al directorio de especificaciones.
        """
        self.specs_dir = Path(specs_dir).resolve()
        # Activación (Sub-FUSIONES, Task 4): TaskLog requiere specs_dir como str
        self.task_log = TaskLog(str(self.specs_dir)) if _HAS_TASK_LOG else None
        if _HAS_TASK_LOG:
            logger.info(
                "TaskLogHandler: TaskLog del core disponible (specs_dir=%s)",
                self.specs_dir,
            )
        else:
            logger.warning(
                "TaskLogHandler: core.task_log no disponible, usando fallback JSONL"
            )

    # — Lógica de negocio ——————————————————————————————————————

    def _log_path(self, project_id: str) -> Path:
        """Ruta al archivo de bitácora JSONL del proyecto."""
        return self.specs_dir / project_id / "task_log.jsonl"

    def get_entries(self, project_id: str) -> List[Dict[str, Any]]:
        """Obtiene todas las entradas de la bitácora de un proyecto.

        Args:
            project_id: ID del proyecto.

        Returns:
            Lista de diccionarios con las entradas.
        """
        if self.task_log is not None:
            try:
                # Activación (Sub-FUSIONES, Task 4): renombrado get_entries → get_task_log
                entries = self.task_log.get_task_log(project_id)
                if isinstance(entries, list):
                    return entries
            except Exception as exc:
                logger.error(
                    "TaskLogHandler: error en TaskLog.get_task_log: %s", exc
                )

        # Fallback: leer JSONL directamente
        log_path = self._log_path(project_id)
        if not log_path.exists():
            return []
        try:
            entries = []
            for line in log_path.read_text(encoding="utf-8").strip().splitlines():
                if line.strip():
                    entries.append(json.loads(line))
            return entries
        except Exception as exc:
            logger.error("TaskLogHandler: error leyendo JSONL: %s", exc)
            return []

    def get_entry(self, project_id: str, task_id: str) -> Dict[str, Any]:
        """Obtiene una entrada específica de la bitácora.

        Args:
            project_id: ID del proyecto.
            task_id: ID de la tarea.

        Returns:
            Diccionario con los datos de la entrada.

        Raises:
            HTTPException: Si la entrada no existe.
        """
        if self.task_log is not None:
            try:
                # Activación (Sub-FUSIONES, Task 4): renombrado get_entry → get_task_entry
                entry = self.task_log.get_task_entry(project_id, task_id)
                if entry is not None:
                    return entry
            except Exception as exc:
                logger.error(
                    "TaskLogHandler: error en TaskLog.get_task_entry: %s", exc
                )

        # Fallback: buscar en JSONL
        for entry in self.get_entries(project_id):
            if entry.get("task_id") == task_id:
                return entry

        raise HTTPException(
            status_code=404,
            detail=(
                f"Entrada no encontrada: proyecto={project_id}, "
                f"tarea={task_id}"
            ),
        )

    def get_entry_summary(
        self, project_id: str, task_id: str
    ) -> str:
        """Obtiene un resumen formateado de una entrada para fiscalización.

        Args:
            project_id: ID del proyecto.
            task_id: ID de la tarea.

        Returns:
            Cadena de texto con el resumen formateado.
        """
        if self.task_log is not None:
            try:
                # Activación (Sub-FUSIONES, Task 4): renombrado get_summary → get_task_summary
                # Verificar existencia primero para preservar la semántica pública
                # (lanzar HTTPException 404 si la entrada no existe). El TaskLog real
                # siempre retorna un string, incluso para entradas inexistentes; el
                # fallback original lanzaba 404 vía get_entry(). Esta guarda mantiene
                # coherencia entre ambos caminos.
                if self.task_log.get_task_entry(project_id, task_id) is not None:
                    summary = self.task_log.get_task_summary(project_id, task_id)
                    if isinstance(summary, str) and summary:
                        return summary
            except Exception as exc:
                logger.error(
                    "TaskLogHandler: error en TaskLog.get_task_summary: %s", exc
                )

        # Fallback: generar resumen básico desde la entrada
        entry = self.get_entry(project_id, task_id)
        return (
            f"Tarea: {task_id}\n"
            f"Proyecto: {project_id}\n"
            f"Estado: {entry.get('status', 'desconocido')}\n"
            f"Datos: {entry.get('data', {})}"
        )


# — Registro de rutas ——————————————————————————————————————

def register_task_log_routes(
    app: FastAPI, handler: TaskLogHandler
) -> None:
    """Registra los endpoints de bitácora en la aplicación FastAPI.

    Args:
        app: Aplicación FastAPI donde registrar las rutas.
        handler: Instancia de TaskLogHandler ya inicializada.
    """

    @app.get("/api/task-log/{project_id}")
    async def get_task_log_endpoint(
        project_id: str,
    ) -> Dict[str, Any]:
        """Obtiene la bitácora de tareas de un proyecto.

        Args:
            project_id: ID del proyecto.

        Returns:
            JSON con la clave "entries".
        """
        entries = handler.get_entries(project_id)
        return {"entries": entries}

    @app.get("/api/task-log/{project_id}/{task_id}")
    async def get_task_entry_endpoint(
        project_id: str,
        task_id: str,
    ) -> Dict[str, Any]:
        """Obtiene una entrada específica de la bitácora.

        Args:
            project_id: ID del proyecto.
            task_id: ID de la tarea.

        Returns:
            JSON con la clave "entry".
        """
        entry = handler.get_entry(project_id, task_id)
        return {"entry": entry}

    @app.get("/api/task-log/{project_id}/{task_id}/summary")
    async def get_task_summary_endpoint(
        project_id: str,
        task_id: str,
    ) -> Dict[str, str]:
        """Obtiene el resumen formateado de una entrada.

        Args:
            project_id: ID del proyecto.
            task_id: ID de la tarea.

        Returns:
            JSON con la clave "summary".
        """
        summary = handler.get_entry_summary(project_id, task_id)
        return {"summary": summary}

    logger.info(
        "TaskLogHandler: rutas registradas — "
        "GET /api/task-log/{project_id}, "
        "/api/task-log/{project_id}/{task_id}, "
        "/api/task-log/{project_id}/{task_id}/summary"
    )


if __name__ == "__main__":
    import tempfile

    print("=== Validación de task_log_handler.py ===")
    print()

    # 1. Crear instancia
    with tempfile.TemporaryDirectory() as tmpdir:
        handler = TaskLogHandler(specs_dir=tmpdir)
        print(f"[OK] TaskLogHandler creado (core disponible: {_HAS_TASK_LOG})")
        assert isinstance(handler.specs_dir, Path)
        print(f"[OK] specs_dir: {handler.specs_dir}")

        # 2. get_entries retorna lista
        entries = handler.get_entries("proj_test")
        assert isinstance(entries, list)
        print(f"[OK] get_entries retorna lista: {len(entries)} entradas")

        # 3. get_entry con entrada inexistente lanza 404
        try:
            handler.get_entry("proj_test", "task_no_existe")
            assert False, "Debería lanzar HTTPException"
        except HTTPException as he:
            assert he.status_code == 404
            print(f"[OK] get_entry lanza 404: {he.detail}")

        # 4. get_entry_summary lanza 404 para entrada inexistente
        try:
            handler.get_entry_summary("proj_test", "task_no_existe")
            assert False, "Debería lanzar HTTPException"
        except HTTPException:
            print("[OK] get_entry_summary propaga 404")

    # 5. register_task_log_routes no crashea
    from app.config_apa import create_app
    test_app = create_app()
    with tempfile.TemporaryDirectory() as tmpdir2:
        h2 = TaskLogHandler(specs_dir=tmpdir2)
        register_task_log_routes(test_app, handler=h2)
    print("[OK] register_task_log_routes() no crashea")

    # 6. Verificar rutas registradas
    routes = [r.path for r in test_app.routes]
    assert "/api/task-log/{project_id}" in routes
    assert "/api/task-log/{project_id}/{task_id}" in routes
    assert "/api/task-log/{project_id}/{task_id}/summary" in routes
    print("[OK] Todas las rutas de task-log registradas")

    print()
    print("=== Todas las validaciones pasaron ===")
