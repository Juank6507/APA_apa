# apa/interface/app/sse_manager.py
"""
sse_manager.py — Gestor de eventos Server-Sent Events (SSE) de APA.

Administra un buffer thread-safe de notificaciones en memoria y conecta
el sistema de notificaciones de core con las colas de eventos por
proyecto. Los clientes se conectan vía GET /stream/{project_id}
y reciben eventos en tiempo real.

Clases:
    SSEManager: Gestor central de eventos SSE.

Funciones:
    register_sse_routes: Registra el endpoint de streaming SSE.
"""

import asyncio
import json
import threading
import time

import sys
from pathlib import Path
_THIS_DIR = Path(__file__).resolve()
sys.path.insert(0, str(_THIS_DIR.parent.parent))        # interface/ → resuelve 'app'
sys.path.insert(0, str(_THIS_DIR.parent.parent.parent))  # apa/ → resuelve 'core', 'config'

from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from app.config_apa import logger
from app.state import AppState

# Módulo funcional — import directo
from core.notifications import register_callback
from core.notification_ui_bridge import format_event


# ── Constantes ────────────────────────────────────────────────────────────

SSE_MAX_BUFFER_AGE_SECONDS: float = 300.0  # 5 minutos
SSE_HEARTBEAT_INTERVAL: float = 15.0


class SSEManager:
    """Gestor central de eventos SSE.

    Mantiene un buffer thread-safe de eventos de notificación en
    state.sse_buffer. Se conecta al sistema core.notifications para
    recibir eventos y los distribuye a los clientes SSE conectados.

    Attributes:
        state: Estado global de la aplicación.
    """

    def __init__(self, state: AppState) -> None:
        """Inicializa el gestor SSE con el estado global.

        Args:
            state: Instancia de AppState compartida.
        """
        self.state = state

    # ── Callback de core.notifications ─────────────────────────────────

    def register_notification_callback(self) -> None:
        """Registra un callback con core.notifications.register_callback.

        El callback recibe un dict de evento, lo formatea con
        format_event() para añadir time_str/color/category/prefix,
        y lo añade al buffer SSE.
        """
        def _on_notification(event_type: str, message: str, data: dict) -> None:
            """Callback interno que añade eventos formateados al buffer SSE.

            Args:
                event_type: Tipo de evento (ej. 'system:startup').
                message: Mensaje legible para el usuario.
                data: Datos estructurados del evento.
            """
            raw_event = {
                'type': event_type,
                'message': message,
                'data': data or {},
                'timestamp': time.time(),
            }
            try:
                formatted = format_event(raw_event)
                # Preservar project_id si viene en data para filtrado SSE
                pid = (data or {}).get('project_id', '')
                if pid:
                    formatted['project_id'] = pid
                else:
                    formatted.setdefault('project_id', '')
            except Exception:
                formatted = raw_event
                formatted.setdefault('project_id', (data or {}).get('project_id', ''))
            with self.state.sse_buffer_lock:
                self.state.sse_buffer.append(formatted)
            logger.debug("SSE: evento recibido tipo=%s", formatted.get("type"))

        try:
            register_callback(_on_notification)
            logger.info("SSEManager: callback registrado con core.notifications")
        except Exception as exc:
            logger.error("SSEManager: error al registrar callback: %s", exc)

    # ── Operaciones del buffer ─────────────────────────────────────────

    def add_event(self, event: dict) -> None:
        """Añade un evento al buffer SSE.

        Args:
            event: Diccionario con al menos 'type', 'message'.
                   Se formatea con format_event() si tiene timestamp numérico.
        """
        if "timestamp" not in event:
            event["timestamp"] = time.time()
        try:
            formatted = format_event(event)
            formatted.setdefault('project_id', event.get('project_id', ''))
            event = formatted
        except Exception:
            event.setdefault('project_id', event.get('project_id', ''))
        with self.state.sse_buffer_lock:
            self.state.sse_buffer.append(event)
        logger.debug("SSE: evento añadido tipo=%s", event.get("type"))

    def get_events(self, project_id: Optional[str] = None) -> List[dict]:
        """Retorna eventos del buffer, opcionalmente filtrados por proyecto.

        Args:
            project_id: Si se proporciona, filtra eventos de ese proyecto.
                           Si es None, retorna todos los eventos.

        Returns:
            Lista de diccionarios de evento.
        """
        with self.state.sse_buffer_lock:
            if project_id is not None:
                return [
                    e for e in self.state.sse_buffer
                    if e.get("project_id") == project_id
                ]
            return list(self.state.sse_buffer)

    def clear_buffer(self) -> None:
        """Limpia todos los eventos del buffer SSE."""
        with self.state.sse_buffer_lock:
            self.state.sse_buffer.clear()
        logger.debug("SSE: buffer limpiado")

    # ── Generador de flujo SSE ────────────────────────────────────────

    async def _event_stream(self, project_id: str) -> None:
        """Genera el flujo de eventos SSE para un cliente conectado.

        Escucha la cola de eventos del proyecto y emite eventos en
        formato SSE (data: {...}\\n\\n). También envía heartbeats
        para mantener la conexión viva.

        Args:
            project_id: ID del proyecto a escuchar.

        Yields:
            Strings con formato SSE.
        """
        try:
            while True:
                # Obtener eventos pendientes del buffer para este proyecto
                events = self.get_events(project_id)
                for evt in events:
                    yield f"data: {json.dumps(evt, default=str)}\n\n"

                # Limpiar eventos ya enviados de este proyecto
                with self.state.sse_buffer_lock:
                    self.state.sse_buffer = [
                        e for e in self.state.sse_buffer
                        if e.get("project_id") != project_id
                    ]

                # Heartbeat para mantener conexión viva
                yield f": heartbeat\n\n"
                await asyncio.sleep(SSE_HEARTBEAT_INTERVAL)

        except asyncio.CancelledError:
            logger.info("SSE: flujo cancelado para proyecto %s", project_id)
        except Exception as exc:
            logger.error("SSE: error en flujo para %s: %s", project_id, exc)


# ── Registro de rutas ────────────────────────────────────────────────────

def register_sse_routes(app: FastAPI, sse: SSEManager) -> None:
    """Registra los endpoints SSE en la aplicación FastAPI.

    Args:
        app: Aplicación FastAPI donde registrar las rutas.
        sse: Instancia de SSEManager ya inicializada.
    """

    @app.get("/stream/{project_id}")
    async def stream_events(project_id: str):
        """Endpoint de streaming SSE para un proyecto específico.

        Args:
            project_id: ID del proyecto a escuchar.

        Returns:
            StreamingResponse con eventos SSE en tiempo real.
        """
        logger.info("SSE: cliente conectado para proyecto %s", project_id)
        return StreamingResponse(
            sse._event_stream(project_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    logger.info("Ruta registrada: GET /stream/{project_id}")


if __name__ == "__main__":
    print("=== Validación de sse_manager.py ===")
    print()

    # 1. Crear instancia con estado
    state = AppState()
    sse = SSEManager(state)
    print(f"[OK] SSEManager creado: {sse}")

    # 2. Buffer inicial vacío
    events = sse.get_events()
    assert events == [], "El buffer debe estar vacío al inicio"
    print("[OK] Buffer inicial vacío")

    # 3. Añadir eventos y verificar que tienen campos de formato
    sse.add_event({
        "type": "mb:startup",
        "project_id": "proj_001",
        "message": "Verificando MB en la URL configurada...",
        "data": {"step": "checking_url"},
    })
    sse.add_event({
        "type": "agent:progress",
        "project_id": "proj_002",
        "message": "50% completado",
    })

    all_events = sse.get_events()
    assert len(all_events) == 2
    # TEST CRÍTICO: verificar campos de formato para la UI
    evt1 = all_events[0]
    assert evt1["type"] == "mb:startup"
    assert "time_str" in evt1, "FALTA time_str — la UI mostrará 'undefined'"
    assert "color" in evt1, "FALTA color — la UI mostrará 'undefined'"
    assert "category" in evt1, "FALTA category — la UI mostrará 'undefined'"
    assert "prefix" in evt1, "FALTA prefix — el filtro no funcionará"
    assert evt1["time_str"] != "", "time_str no debe estar vacío"
    assert evt1["prefix"] == "mb", f"prefix debe ser 'mb', got '{evt1.get('prefix')}'"
    print(f"[OK] add_event() formatea eventos: time_str={evt1['time_str']!r}, color={evt1['color']!r}, category={evt1['category']!r}")

    # 4. Verificar que project_id se preserva para filtrado
    p1_events = sse.get_events(project_id="proj_001")
    assert len(p1_events) == 1
    assert p1_events[0]["project_id"] == "proj_001"
    print("[OK] get_events(project_id=...) filtra correctamente")

    # 5. Filtrar por project_id inexistente
    none_events = sse.get_events(project_id="no_existe")
    assert len(none_events) == 0
    print("[OK] get_events con project_id inexistente retorna lista vacía")

    # 6. clear_buffer
    sse.clear_buffer()
    assert len(sse.get_events()) == 0
    print("[OK] clear_buffer() limpia el buffer")

    # 7. TEST DE INTEGRACIÓN: notify() → callback → buffer formateado
    from core.notifications import notify, clear_callbacks, _default_log_callback
    clear_callbacks()
    register_callback(_default_log_callback)  # re-registrar el default
    sse.register_notification_callback()
    notify("mb:startup", "Comando del sandbox no encontrado", {"step": "sandbox_cmd_not_found"})
    buf_events = sse.get_events()
    assert len(buf_events) >= 1, "notify() debe haber poblado el buffer SSE"
    evt_notif = buf_events[-1]
    assert evt_notif["message"] == "Comando del sandbox no encontrado", f"Mensaje incorrecto: {evt_notif['message']}"
    assert "time_str" in evt_notif, "Evento de notify() falta time_str"
    assert "color" in evt_notif, "Evento de notify() falta color"
    assert "category" in evt_notif, "Evento de notify() falta category"
    # Verificar que NO es [object Object] ni undefined
    assert not evt_notif["message"].startswith("{"), "El mensaje no debe ser un dict serializado"
    print(f"[OK] notify() → callback → buffer formateado correctamente")
    print(f"     message={evt_notif['message']!r}")
    print(f"     time_str={evt_notif['time_str']!r}, color={evt_notif['color']!r}, category={evt_notif['category']!r}")
    sse.clear_buffer()
    clear_callbacks()
    register_callback(_default_log_callback)  # dejar limpio

    # 8. Thread-safety
    errors: list = []
    def writer(i: int) -> None:
        try:
            sse.add_event({
                "type": "concurrent",
                "project_id": f"proj_{i}",
                "message": f"msg_{i}",
            })
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(100)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(errors) == 0
    assert len(sse.get_events()) == 100
    print("[OK] Thread-safety verificado (100 threads concurrentes)")

    # 9. Verificar que TODOS los eventos formateados tienen campos de UI
    sse_events = sse.get_events()
    for i, ev in enumerate(sse_events):
        assert "time_str" in ev, f"Evento {i} falta time_str"
        assert "color" in ev, f"Evento {i} falta color"
        assert "category" in ev, f"Evento {i} falta category"
        assert "prefix" in ev, f"Evento {i} falta prefix"
    print("[OK] Todos los 100 eventos tienen campos de formato para UI")

    print()
    print("=== Todas las validaciones pasaron ===")
