# apa/interface/app_apa.py
"""app_apa.py — Integrador de la aplicación APA.

Módulo orquestador que conecta todas las dependencias desplegadas en core/
y los handlers de interface/app/. Cero lógica de negocio.

Responsabilidades:
  1. Crear la instancia FastAPI via config.create_app
  2. Instanciar estado global y servicios compartidos
  3. Registrar el evento de startup para inicialización en segundo plano
  4. Registrar todas las rutas distribuidas en los handlers
  5. Montar archivos estáticos
  6. Proporcionar el punto de entrada para uvicorn

Startup: uvicorn interface.app_apa:app --host 0.0.0.0 --port 7860 --reload
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

from app.config_apa import (
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

# Handlers que requieren instanciación explícita.
# Estos handlers crean Orchestrator() en su __init__, que a su vez
# intenta conectar al sandbox/MB. Orchestrator.__init__ es resiliente:
# si los agentes no pueden conectar, siguen en modo degradado (None).
# Por eso el scope global no se bloquea aunque el sandbox no responda.
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

    El servidor uvicorn YA está escuchando cuando este evento se ejecuta.
    PRIMERO registramos el callback SSE para capturar TODAS las notificaciones,
    INCLUYENDO las del arranque. Luego lanzamos los subsistemas en segundo plano.
    """
    # Registrar callback SSE ANTES de lanzar startup para no perder notificaciones
    sse.register_notification_callback()
    # Ahora lanzar subsistemas en segundo plano
    init_subsystems_threaded(state=state)
    logger.info("APA application started — servidor escuchando, subsistemas en background")


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
    # El servidor arranca INMEDIATAMENTE.
    # Los servicios pesados (MB, router, pool) se inicializan en segundo
    # plano vía init_subsystems_threaded() en el evento on_startup de FastAPI.
    # Eso evita que el usuario tenga que esperar a que el sandbox/MB responda
    # antes de poder abrir la interfaz web.
    logger.info("=" * 60)
    logger.info("Arrancando APA en %s:%d", DEFAULT_HOST, DEFAULT_PORT)
    logger.info("Los subsistemas pesados (MB, pool) se inicializan en background.")
    logger.info("=" * 60)
    uvicorn.run(app, host=DEFAULT_HOST, port=DEFAULT_PORT)
