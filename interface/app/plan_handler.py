# apa/interface/app/plan_handler.py
"""
plan_handler.py — Endpoint de planes de proyecto de APA.

Expone el endpoint para obtener el plan actual de un proyecto.
Lee archivos PLAN_*.md del disco usando core.plan_handler.

Clases:
    PlanHandler: Manejador de planes de proyecto.

Funciones:
    register_plan_routes: Registra GET /api/plan.
"""

import sys
from pathlib import Path
_THIS_DIR = Path(__file__).resolve()
sys.path.insert(0, str(_THIS_DIR.parent.parent))        # interface/ → resuelve 'app'
sys.path.insert(0, str(_THIS_DIR.parent.parent.parent))  # apa/ → resuelve 'core', 'config'

from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Query

from app.config_apa import WORK_DIRECTORIES, logger

# Módulos funcionales — import directo
from core import plan_handler as core_plan_handler
from core.planner import Planner


class PlanHandler:
    """Manejador de planes de proyecto.

    Lee archivos de plan del disco a través de core.plan_handler
    y usa core.planner.Planner para generar nuevos planes.

    Attributes:
        specs_dir: Ruta al directorio de especificaciones.
    """

    def __init__(self) -> None:
        """Inicializa el manejador de planes."""
        self.specs_dir: Path = WORK_DIRECTORIES.get("specs_dir", Path("specs"))
        logger.info("PlanHandler: inicializado")

    # — Lógica de negocio ——————————————————————————————————————

    def get_plan(self, project_id: str) -> Dict[str, Any]:
        """Obtiene el plan actual de un proyecto.

        Delega en core.plan_handler.get_plan para leer el estado.

        Args:
            project_id: ID del proyecto.

        Returns:
            Diccionario con datos del plan.

        Raises:
            HTTPException: Si no se encuentra el plan.
        """
        try:
            result = core_plan_handler.get_plan(project_root=project_id)
            if result:
                return result
        except Exception as exc:
            logger.debug(
                "PlanHandler: core.plan_handler.get_plan falló para %s: %s",
                project_id, exc,
            )

        # Fallback: buscar archivo plan.json en specs/{project_id}/
        specs_dir = Path(self.specs_dir)
        plan_path = specs_dir / project_id / "plan.json"

        if not plan_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Plan no encontrado para el proyecto: {project_id}",
            )

        import json
        content = plan_path.read_text(encoding="utf-8")
        plan_data = json.loads(content)

        return {
            "plan": {
                "project_id": project_id,
                "tasks": plan_data.get("tasks", []),
                "total_tasks": len(plan_data.get("tasks", [])),
            },
            "file": str(plan_path),
        }


# — Registro de rutas ——————————————————————————————————————

def register_plan_routes(app: FastAPI) -> None:
    """Registra los endpoints de planes en la aplicación FastAPI.

    Crea una instancia de PlanHandler y registra el endpoint
    GET /api/plan.

    Args:
        app: Aplicación FastAPI donde registrar las rutas.
    """
    handler = PlanHandler()

    @app.get("/api/plan")
    async def get_plan_endpoint(
        project_id: str = Query(..., description="ID del proyecto"),
    ) -> Dict[str, Any]:
        """Obtiene el plan actual de un proyecto.

        Args:
            project_id: ID del proyecto (query param obligatorio).

        Returns:
            JSON con datos del plan.
        """
        return handler.get_plan(project_id)

    logger.info(
        "PlanHandler: ruta registrada — GET /api/plan"
    )


if __name__ == "__main__":
    print("=== Validación de plan_handler.py ===")
    print()

    from unittest.mock import patch
    _MODULE_NAME = __name__  # "__main__" if standalone, "plan_handler" if imported

    # Patchear core_plan_handler.get_plan para forzar el path de fallback (404)
    _p_get_plan = patch(f"{_MODULE_NAME}.core_plan_handler.get_plan", return_value=None)
    _p_get_plan.start()

    # 1. Crear instancia
    handler = PlanHandler()
    print("[OK] PlanHandler creado")

    # 2. get_plan con proyecto inexistente lanza 404
    try:
        handler.get_plan("no_existe_xyz_project")
        assert False, "Debería lanzar HTTPException"
    except HTTPException as he:
        assert he.status_code == 404
        print(f"[OK] get_plan lanza 404: {he.detail}")

    # 3. register_plan_routes no crashea
    from app.config_apa import create_app
    test_app = create_app()
    register_plan_routes(test_app)
    print("[OK] register_plan_routes() no crashea")

    # 4. Verificar rutas registradas
    routes = [r.path for r in test_app.routes]
    assert "/api/plan" in routes
    print("[OK] Ruta GET /api/plan registrada")

    # 5. Imports directos (sin try/except para módulos funcionales)
    from core import plan_handler as _cph
    from core.planner import Planner as _PlannerCls
    from config.settings import settings as _settings
    _planner = _PlannerCls(_settings)
    print("[OK] core.plan_handler y core.planner.Planner importados directamente")

    print()
    print("=== Todas las validaciones pasaron ===")
