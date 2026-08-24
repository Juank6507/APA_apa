# apa/interface/app.py
"""app.py — Integrador de la aplicación APA.

Módulo orquestador que conecta todas las dependencias desplegadas en core/
y los handlers de interface/app/. Cero lógica de negocio.

Responsabilidades:
  1. Crear la instancia FastAPI via config.create_app
  2. Instanciar estado global y servicios compartidos
  3. Registrar el evento de startup para inicialización en segundo plano
  4. Registrar todas las rutas distribuidas en los handlers
  5. Montar archivos estáticos
  6. Proporcionar el punto de entrada para uvicorn

Startup: uvicorn interface.app.app:app --host 0.0.0.0 --port 7860 --reload
"""

from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import uvicorn
from fastapi import FastAPI
from typing import List


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Configuración y estado                                                    ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

from app.config import (
    create_app,
    logger,
    WORK_DIRECTORIES,
    DEFAULT_HOST,
    DEFAULT_PORT,
)
from app.state import AppState


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Servicios compartidos                                                     ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

from app.startup import (
    init_subsystems,
    init_subsystems_threaded,
    register_startup_routes,
)
from app.sse_manager import SSEManager, register_sse_routes
from app.pricing import PricingService
from app.dashboard import DashboardService, register_dashboard_routes
from app.self_context import SelfContextLoader


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Handlers especializados                                                  ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

from app.sdd_handler import register_sdd_routes
from app.chat_handler import register_chat_routes
from app.chat_engine import ChatEngine, register_chat_engine_routes
from app.exploration_handler import register_exploration_routes
from app.pipeline_handler import PipelineHandler, register_pipeline_routes
from app.scaling_handler import register_scaling_routes
from app.quota_handler import QuotaHandler, register_quota_routes
from app.project_handler import ProjectHandler, register_project_routes
from app.notifications_handler import NotificationsHandler, register_notification_routes
from app.failure_auditor_handler import register_auditor_routes
from app.plan_handler import register_plan_routes
from app.download_handler import DownloadHandler, register_download_routes
from app.task_log_handler import TaskLogHandler, register_task_log_routes
from app.ui_renderer import register_ui_routes
from app.ui_static import mount_static


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Creación de la aplicación y sus dependencias                            ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

app: FastAPI = create_app()

# Estado global centralizado
state = AppState()

# Servicios (inyección de dependencias)
pricing = PricingService()
dashboard = DashboardService(pricing=pricing)
sse = SSEManager(state=state)
context_loader = SelfContextLoader(docs_dir=str(WORK_DIRECTORIES["docs_dir"]))
chat_engine = ChatEngine(
    state=state,
    pricing=pricing,
    dashboard=dashboard,
    self_context=context_loader,
)

# Handlers que requieren instanciación explícita
pipeline_handler = PipelineHandler(state=state)
quota_handler = QuotaHandler(pricing=pricing)
project_handler = ProjectHandler(state=state, dashboard=dashboard)
notifications_handler = NotificationsHandler(sse=sse)
download_handler = DownloadHandler(
    downloads_dir=str(WORK_DIRECTORIES["downloads_dir"])
)
task_log_handler = TaskLogHandler(
    specs_dir=str(WORK_DIRECTORIES["specs_dir"])
)


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Evento de startup                                                        ║
# ╚═══════════════════════════════════════════════════════════════════════════╝


@app.on_event("startup")
async def on_startup() -> None:
    """Evento de inicio de la aplicación.

    Lanza los subsistemas pesados (MB, router, pool) en un hilo daemon
    para no bloquear el arranque de uvicorn. También registra el
    callback de SSE para notificaciones en tiempo real.
    """
    init_subsystems_threaded(state=state)
    sse.register_notification_callback()
    logger.info("APA application started successfully")


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Registro de rutas (18 handlers, ~29 rutas)                               ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

# 1. Startup y salud
register_startup_routes(app, state=state)

# 2. SSE (Server-Sent Events)
register_sse_routes(app, sse=sse)

# 3. Dashboard
register_dashboard_routes(app, dashboard=dashboard)

# 4. SDD (Software Design Documents)
register_sdd_routes(app, state=state)

# 5. Chat REST
register_chat_routes(app, state=state)

# 6. Chat Engine (motor avanzado con pricing y contexto)
register_chat_engine_routes(app, engine=chat_engine)

# 7. Exploración de proyectos
register_exploration_routes(app, state=state)

# 8. Pipelines
register_pipeline_routes(app, handler=pipeline_handler)

# 9. Escalado horizontal/vertical
register_scaling_routes(app)

# 10. Cuotas de uso
register_quota_routes(app, handler=quota_handler)

# 11. Gestión de proyectos CRUD
register_project_routes(app, handler=project_handler)

# 12. Notificaciones
register_notification_routes(app, handler=notifications_handler)

# 13. Auditoría de fallos
register_auditor_routes(app)

# 14. Planificación
register_plan_routes(app)

# 15. Descargas
register_download_routes(app, handler=download_handler)

# 16. Bitácora de tareas
register_task_log_routes(app, handler=task_log_handler)

# 17. Interfaz de usuario (HTML principal)
register_ui_routes(app, state=state, context_loader=context_loader)

# 18. Archivos estáticos
mount_static(app)


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Utilidad: listado de rutas registradas                                   ║
# ╚═══════════════════════════════════════════════════════════════════════════╝


def _list_routes() -> List[str]:
    """Retorna una lista con todas las rutas registradas en la aplicación.

    Returns:
        Lista de cadenas con formato 'MÉTODO /ruta' o 'MOUNT /ruta'.
    """
    routes: List[str] = []
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            methods = ",".join(sorted(route.methods))  # type: ignore[attr-defined]
            routes.append(f"{methods} {route.path}")
        elif hasattr(route, "path"):
            routes.append(f"MOUNT {route.path}")
    return routes


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Punto de entrada                                                         ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("APA Integrador — Validación y arranque")
    logger.info("=" * 60)

    # Verificar estado
    logger.info("Estado global: %s", state)

    # Verificar servicios
    _services = {
        "pricing": pricing,
        "dashboard": dashboard,
        "sse": sse,
        "context_loader": context_loader,
        "chat_engine": chat_engine,
        "pipeline_handler": pipeline_handler,
        "quota_handler": quota_handler,
        "project_handler": project_handler,
        "notifications_handler": notifications_handler,
        "download_handler": download_handler,
        "task_log_handler": task_log_handler,
    }
    for _name, _svc in _services.items():
        logger.info("  Servicio '%s': %s", _name, type(_svc).__name__)

    # Verificar rutas
    _all_routes = _list_routes()
    logger.info("Rutas registradas: %d", len(_all_routes))
    for _r in sorted(_all_routes):
        logger.info("  %s", _r)

    if len(_all_routes) >= 25:
        logger.info(
            "Rutas registradas: %d (minimo esperado: 25)", len(_all_routes)
        )
    else:
        logger.warning(
            "Solo %d rutas registradas (esperado: ~29+)", len(_all_routes)
        )

    logger.info("=" * 60)
    logger.info("Arrancando APA en %s:%d", DEFAULT_HOST, DEFAULT_PORT)
    logger.info("=" * 60)
    uvicorn.run(app, host=DEFAULT_HOST, port=DEFAULT_PORT)
