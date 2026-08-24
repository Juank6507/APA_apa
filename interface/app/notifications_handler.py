# apa/interface/app/notifications_handler.py
"""
notifications_handler.py — Endpoints de notificaciones de APA.

Expone endpoints para consultar eventos recientes, obtener un
resumen formateado y hacer streaming en tiempo real de
notificaciones del sistema.

Clases:
    NotificationsHandler: Manejador de notificaciones.

Funciones:
    register_notification_routes: Registra GET /notifications/recent,
                                    /notifications/summary, /notifications/stream.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
import json
from typing import TYPE_CHECKING, Any, AsyncGenerator, Dict, List, Optional

from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from app.config_apa import logger
from app.sse_manager import SSEManager
from app.state import AppState

if TYPE_CHECKING:
    pass

# Módulos funcionales — import directo
from core.notifications import (
    register_callback,
    unregister_callback,
    get_recent_events,
    notify,
)
from core import notification_ui_bridge


class NotificationsHandler:
    """Manejador de notificaciones.

    Gestiona la consulta de eventos recientes, resúmenes formateados
    y streaming en tiempo real de notificaciones del sistema.
    Usa core.notifications para el backend y core.notification_ui_bridge
    para el formateo de resúmenes.

    Attributes:
        sse: Gestor SSE para streaming de eventos.
    """

    def __init__(self, sse: SSEManager) -> None:
        """Inicializa el manejador de notificaciones.

        Args:
            sse: Instancia de SSEManager para streaming de eventos.
        """
        self.sse = sse
        logger.info("NotificationsHandler: inicializado con SSEManager")

    # ── Lógica de negocio ─────────────────────────────────────────────

    def get_recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Obtiene las notificaciones más recientes.

        Delega en core.notifications.get_recent_events.

        Args:
            limit: Cantidad máxima de eventos a retornar.

        Returns:
            Lista de diccionarios de eventos.
        """
        try:
            events = get_recent_events(limit=limit)
            if isinstance(events, list):
                return events
        except Exception as exc:
            logger.error(
                "NotificationsHandler: error en get_recent_events: %s", exc
            )

        # Fallback: eventos del buffer SSE
        return self.sse.get_events()

    def get_summary(self) -> str:
        """Obtiene un resumen formateado de las notificaciones.

        Delega en core.notification_ui_bridge.get_full_summary.

        Returns:
            Cadena de texto con el resumen formateado.
        """
        try:
            summary = notification_ui_bridge.get_full_summary()
            if isinstance(summary, str):
                return summary
        except Exception as exc:
            logger.error(
                "NotificationsHandler: error en get_full_summary: %s", exc
            )

        # Fallback: resumen simple del buffer
        events = self.sse.get_events()
        if not events:
            return "No hay notificaciones recientes."
        return (
            f"{len(events)} notificaciones en buffer. "
            f"Última: {events[-1].get('message', 'N/A')}"
        )

    async def _event_generator(self) -> AsyncGenerator[str, None]:
        """Genera el flujo SSE de notificaciones en tiempo real.

        Emite eventos del buffer SSE en formato SSE estándar
        con heartbeats para mantener la conexión viva.

        Yields:
            Strings con formato SSE (data: {...}\n\n).
        """
        try:
            while True:
                events = self.sse.get_events()
                for evt in events:
                    payload = json.dumps(evt, default=str)
                    yield f"data: {payload}\n\n"

                # Limpiar eventos enviados
                self.sse.clear_buffer()

                # Heartbeat
                yield ": heartbeat\n\n"
                await asyncio.sleep(15.0)

        except asyncio.CancelledError:
            logger.info("NotificationsHandler: flujo SSE cancelado")
        except Exception as exc:
            logger.error(
                "NotificationsHandler: error en flujo SSE: %s", exc
            )


# ── Registro de rutas ────────────────────────────────────────────────────

def register_notification_routes(
    app: FastAPI, handler: NotificationsHandler
) -> None:
    """Registra los endpoints de notificaciones en la aplicación FastAPI.

    Args:
        app: Aplicación FastAPI donde registrar las rutas.
        handler: Instancia de NotificationsHandler ya inicializada.
    """

    @app.get("/notifications/recent")
    async def get_recent_notifications(
        limit: int = 50
    ) -> Dict[str, Any]:
        """Retorna las notificaciones más recientes.

        Args:
            limit: Cantidad máxima de eventos (query param, default 50).

        Returns:
            JSON con la clave "events".
        """
        events = handler.get_recent(limit=limit)
        return {"events": events}

    @app.get("/notifications/summary")
    async def get_notifications_summary() -> Dict[str, str]:
        """Retorna un resumen formateado de las notificaciones.

        Returns:
            JSON con la clave "summary".
        """
        summary = handler.get_summary()
        return {"summary": summary}

    @app.get("/notifications/stream")
    async def stream_notifications_endpoint() -> StreamingResponse:
        """Flujo SSE de notificaciones en tiempo real.

        Returns:
            StreamingResponse con media_type text/event-stream.
        """
        return StreamingResponse(
            handler._event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    logger.info(
        "NotificationsHandler: rutas registradas — "
        "GET /notifications/recent, /notifications/summary, /notifications/stream"
    )


if __name__ == "__main__":
    print("=== Validación de notifications_handler.py ===")
    print()

    # 1. Crear instancia con SSEManager mock
    state = AppState()
    sse = SSEManager(state)
    handler = NotificationsHandler(sse=sse)
    print("[OK] NotificationsHandler creado")
    assert handler.sse is sse
    print("[OK] SSEManager inyectado correctamente")

    # 2. get_recent retorna lista
    events = handler.get_recent(limit=10)
    assert isinstance(events, list)
    print(f"[OK] get_recent retorna lista: {len(events)} eventos")

    # 3. get_summary retorna string
    summary = handler.get_summary()
    assert isinstance(summary, str)
    print(f"[OK] get_summary retorna string: {summary[:60]}...")

    # 4. get_recent con eventos en el buffer
    sse.add_event({
        "type": "info",
        "project_id": "p1",
        "message": "Pipeline iniciado",
    })
    sse.add_event({
        "type": "warning",
        "project_id": "p2",
        "message": "Cuota al 80%",
    })
    events_with_data = handler.get_recent()
    assert len(events_with_data) >= 2
    print(f"[OK] get_recent con datos en buffer: {len(events_with_data)} eventos")
    sse.clear_buffer()

    # 5. register_notification_routes no crashea
    from app.config_apa import create_app
    test_app = create_app()
    register_notification_routes(test_app, handler)
    print("[OK] register_notification_routes() no crashea")

    # 6. Verificar rutas registradas
    routes = [r.path for r in test_app.routes]
    assert "/notifications/recent" in routes
    assert "/notifications/summary" in routes
    assert "/notifications/stream" in routes
    print("[OK] Todas las rutas de notificaciones registradas")

    # 7. Imports directos (sin try/except para módulos funcionales)
    from core.notifications import get_recent_events as _gre
    from core import notification_ui_bridge as _nuib
    print("[OK] core.notifications y core.notification_ui_bridge importados directamente")

    print()
    print("=== Todas las validaciones pasaron ===")
