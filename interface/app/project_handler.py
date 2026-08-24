# apa/interface/app/project_handler.py
"""
project_handler.py — Endpoints de gestión de proyectos de APA.

Expone endpoints para listar proyectos, consultar detalles, ejecutar
pipelines y analizar proyectos. Delega en core.projects_handler
para lectura y en core.orchestrator.Orchestrator para ejecución.

Clases:
    ProjectHandler: Manejador de operaciones de proyectos.

Funciones:
    register_project_routes: Registra GET /projects, /api/project/{id},
                              POST /run, POST /analyze.
"""

import sys
from pathlib import Path
_THIS_DIR = Path(__file__).resolve()
sys.path.insert(0, str(_THIS_DIR.parent.parent))        # interface/ → resuelve 'app'
sys.path.insert(0, str(_THIS_DIR.parent.parent.parent))  # apa/ → resuelve 'core', 'config'

import asyncio
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException

from app.config_apa import logger
from app.models import AnalyzeRequest, RunRequest
from app.state import AppState

if TYPE_CHECKING:
    from app.dashboard import DashboardService

# Módulos funcionales — import con resiliencia ante core desactualizado
try:
    from core.orchestrator import Orchestrator
    _orchestrator_available = True
except ImportError:
    Orchestrator = None  # type: ignore[assignment, misc]
    _orchestrator_available = False

try:
    from core import projects_handler as core_projects
    _projects_handler_available = True
except ImportError:
    core_projects = None  # type: ignore[assignment, misc]
    _projects_handler_available = False


class ProjectHandler:
    """Manejador de operaciones de proyectos.

    Gestiona listado, detalles, ejecución de pipelines y análisis
    de proyectos. Delega en core.projects_handler para lectura y
    en core.orchestrator.Orchestrator para ejecución.

    Attributes:
        state: Estado global de la aplicación.
        dashboard: Servicio de métricas del dashboard.
        orchestrator: Instancia del orquestador del core.
    """

    def __init__(self, state: AppState, dashboard: "DashboardService") -> None:
        """Inicializa el manejador de proyectos.

        Args:
            state: Estado global de la aplicación.
            dashboard: Servicio de métricas del dashboard.
        """
        self.state = state
        self.dashboard = dashboard
        self.orchestrator = Orchestrator() if _orchestrator_available else None
        if _orchestrator_available:
            logger.info("ProjectHandler: inicializado con Orchestrator")
        else:
            logger.warning(
                "ProjectHandler: core.orchestrator no disponible — "
                "la ejecución de proyectos estará deshabilitada. Actualice core/ desde el repositorio."
            )

    # ── Lógica de negocio ─────────────────────────────────────────────

    def list_all_projects(self) -> List[Dict[str, Any]]:
        """Lista todos los proyectos disponibles.

        Delega en core.projects_handler.list_projects y retorna
        la lista cruda de proyectos.

        Returns:
            Lista de diccionarios con datos de cada proyecto.
        """
        if core_projects is None:
            # Fallback: proyectos del estado
            if isinstance(self.state.projects, dict):
                return [
                    {"id": pid, **data}
                    for pid, data in self.state.projects.items()
                ]
            return []
        try:
            projects = core_projects.list_projects()
            if isinstance(projects, list):
                return projects
        except Exception as exc:
            logger.error("ProjectHandler: error listando proyectos: %s", exc)

        # Fallback: proyectos del estado
        if isinstance(self.state.projects, dict):
            return [
                {"id": pid, **data}
                for pid, data in self.state.projects.items()
            ]
        return []

    def get_project_detail(self, project_id: str) -> Dict[str, Any]:
        """Obtiene el detalle de un proyecto específico.

        Delega en core.projects_handler.get_project_detail.

        Args:
            project_id: Identificador del proyecto.

        Returns:
            Diccionario con los datos del proyecto.

        Raises:
            HTTPException: Si el proyecto no se encuentra.
        """
        if core_projects is None:
            # Fallback: buscar en el estado
            try:
                return self.state.get_project(project_id)
            except ValueError:
                raise HTTPException(
                    status_code=404,
                    detail=f"Proyecto no encontrado: {project_id}",
                )
        try:
            detail = core_projects.get_project_detail(project_id)
            if detail is not None:
                return detail
        except Exception as exc:
            logger.error(
                "ProjectHandler: error obteniendo detalle: %s", exc
            )

        # Fallback: buscar en el estado
        try:
            return self.state.get_project(project_id)
        except ValueError:
            raise HTTPException(
                status_code=404,
                detail=f"Proyecto no encontrado: {project_id}",
            )

    def _run_pipeline(self, project_id: str) -> Dict[str, Any]:
        """Ejecuta el pipeline de un proyecto usando el orquestador.

        Args:
            project_id: ID del proyecto a ejecutar.

        Returns:
            Diccionario con status y project_id.
        """
        if self.orchestrator is None:
            return {
                "status": "error",
                "project_id": project_id,
                "error": "core.orchestrator no disponible — actualice core/ desde el repositorio",
            }
        try:
            self.orchestrator.run(project_id=project_id)
            return {"status": "started", "project_id": project_id}
        except Exception as exc:
            logger.error(
                "ProjectHandler: error ejecutando proyecto %s: %s",
                project_id, exc,
            )
            return {
                "status": "error",
                "project_id": project_id,
                "error": str(exc),
            }

    def _analyze_project(
        self, project_id: str, depth: str = "standard"
    ) -> Dict[str, Any]:
        """Analiza un proyecto.

        Args:
            project_id: ID del proyecto a analizar.
            depth: Profundidad del análisis.

        Returns:
            Diccionario con el resultado del análisis.
        """
        if core_projects is None:
            return {"analysis": {"error": "core.projects_handler no disponible — actualice core/"}}
        try:
            analysis = core_projects.analyze_project(
                project_id, depth=depth
            )
            return {"analysis": analysis}
        except Exception as exc:
            logger.error(
                "ProjectHandler: error analizando proyecto %s: %s",
                project_id, exc,
            )
            return {"analysis": {"error": str(exc)}}


# ── Registro de rutas ────────────────────────────────────────────────────

def register_project_routes(
    app: FastAPI, handler: ProjectHandler
) -> None:
    """Registra los endpoints de proyectos en la aplicación FastAPI.

    Args:
        app: Aplicación FastAPI donde registrar las rutas.
        handler: Instancia de ProjectHandler ya inicializada.
    """

    @app.get("/projects")
    async def list_projects_endpoint() -> Dict[str, Any]:
        """Lista todos los proyectos.

        Returns:
            JSON con la clave "projects" conteniendo la lista.
        """
        projects = handler.list_all_projects()
        return {"projects": projects}

    @app.get("/api/project/{project_id}")
    async def get_project_endpoint(project_id: str) -> Dict[str, Any]:
        """Obtiene el detalle de un proyecto.

        Args:
            project_id: Identificador del proyecto.

        Returns:
            JSON con la clave "project" conteniendo los datos.
        """
        project = handler.get_project_detail(project_id)
        return {"project": project}

    @app.post("/run")
    async def run_project_endpoint(request: RunRequest) -> Dict[str, Any]:
        """Ejecuta un proyecto.

        Args:
            request: Petición con project_id.

        Returns:
            JSON con status y project_id.
        """
        # P1 bug fix: Orchestrator.run puede ser síncrona
        result = await asyncio.to_thread(
            handler._run_pipeline, request.project_id
        )
        return result

    @app.post("/analyze")
    async def analyze_project_endpoint(
        request: AnalyzeRequest
    ) -> Dict[str, Any]:
        """Analiza un proyecto.

        Args:
            request: Petición con project_id y depth.

        Returns:
            JSON con la clave "analysis".
        """
        result = handler._analyze_project(
            request.project_id,
            depth=request.depth or "standard",
        )
        return result

    logger.info(
        "ProjectHandler: rutas registradas — "
        "GET /projects, GET /api/project/{id}, POST /run, POST /analyze"
    )


if __name__ == "__main__":
    print("=== Validación de project_handler.py ===")
    print()

    from unittest.mock import MagicMock, patch
    _MODULE_NAME = __name__  # "__main__" if standalone, "project_handler" if imported

    # Patchear Orchestrator para evitar dependencias de sandbox/MB real
    _p_orch = patch(f"{_MODULE_NAME}.Orchestrator")
    _MockOrch = _p_orch.start()
    _MockOrch.return_value = MagicMock()

    # Forzar flag de disponibilidad para que el handler use el mock
    # (en Windows del Director, core.orchestrator puede no estar actualizado
    # y el flag queda en False; en validación forzamos True para usar el mock)
    import sys as _sys
    _sys.modules[_MODULE_NAME]._orchestrator_available = True

    # 1. Crear instancia con mocks
    state = AppState()
    mock_dashboard = MagicMock()

    handler = ProjectHandler(state=state, dashboard=mock_dashboard)
    print("[OK] ProjectHandler creado")
    assert handler.state is state
    assert handler.orchestrator is not None
    print("[OK] Componentes internos inicializados")

    # 2. list_all_projects retorna lista
    projects = handler.list_all_projects()
    assert isinstance(projects, list)
    print(f"[OK] list_all_projects retorna lista: {len(projects)} proyectos")

    # 3. get_project_detail con proyecto inexistente lanza 404
    try:
        handler.get_project_detail("no_existe_xyz")
        assert False, "Debería lanzar HTTPException"
    except HTTPException as he:
        assert he.status_code == 404
        print(f"[OK] get_project_detail lanza 404: {he.detail}")

    # 4. _run_pipeline retorna dict con status
    run_result = handler._run_pipeline("test_project")
    assert "status" in run_result
    assert "project_id" in run_result
    assert run_result["project_id"] == "test_project"
    print(f"[OK] _run_pipeline retorna: {run_result}")

    # 5. _analyze_project retorna dict con analysis
    analyze_result = handler._analyze_project("test_project")
    assert "analysis" in analyze_result
    print(f"[OK] _analyze_project retorna estructura correcta")

    # 6. register_project_routes no crashea
    from app.config_apa import create_app
    test_app = create_app()
    register_project_routes(test_app, handler)
    print("[OK] register_project_routes() no crashea")

    # 7. Verificar rutas registradas
    routes = [r.path for r in test_app.routes]
    assert "/projects" in routes
    assert "/api/project/{project_id}" in routes
    assert "/run" in routes
    assert "/analyze" in routes
    print("[OK] Todas las rutas de proyectos registradas")

    # 8. Imports directos (con resiliencia ante core desactualizado)
    try:
        from core.orchestrator import Orchestrator as _O
        print("[OK] core.orchestrator importado directamente")
    except ImportError:
        print("[OK] core.orchestrator no disponible en este entorno (mock usado en validación)")
    try:
        from core import projects_handler as _PH
        print("[OK] core.projects_handler importado directamente")
    except ImportError:
        print("[OK] core.projects_handler no disponible en este entorno")

    print()
    print("=== Todas las validaciones pasaron ===")
