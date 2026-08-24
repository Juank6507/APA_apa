# apa/interface/app/state.py
"""state.py — Estado global centralizado de la aplicación APA.

Reúne todas las variables globales que antes estaban sueltas en app.py
en una única clase AppState. Cualquier módulo que necesite acceder al
estado lo hace a través de esta clase.

Campos principales:
    - projects:           Proyectos activos {id: datos}
    - event_queues:       Colas SSE por proyecto (asyncio.Queue)
    - sse_buffer:         Buffer de notificaciones SSE
    - sse_buffer_lock:    Lock para acceso seguro al buffer
    - chat_cache:         Cache de conversaciones maduras
    - price_cache:        Cache de precios por modelo
    - self_context:       Contenido de BITACORA/WHITEPAPER
    - startup_complete:   Indica si la startup terminó
    - startup_info:       Resultado de init_subsystems
"""

import asyncio
import threading
import time

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from typing import Any, Dict, List, Optional


class AppState:
    """Estado global centralizado de la aplicación APA.

    Agrupa proyectos activos, colas SSE, caches, y estado del sistema
    en una única clase con métodos seguros para acceso y modificación.
    Es thread-safe donde se requiere concurrencia.

    Attributes:
        projects:           Diccionario de proyectos activos {id: datos}.
        event_queues:       Colas asyncio.Queue de eventos SSE por proyecto.
        sse_buffer:         Buffer de notificaciones SSE pendientes.
        sse_buffer_lock:    Lock threading para acceso seguro al buffer SSE.
        chat_cache:         Cache de conversaciones maduras {project_id: datos}.
        price_cache:        Cache de precios por modelo {model: datos}.
        self_context:       Contenido cargado de BITACORA.md/WHITEPAPER.md.
        startup_complete:   True si init_subsystems terminó con éxito.
        startup_info:       Dict con resultado de la inicialización.
    """

    def __init__(self) -> None:
        """Inicializa el estado global con valores por defecto."""
        # Proyectos activos
        self.projects: Dict[str, Dict[str, Any]] = {}
        self._projects_lock = threading.Lock()

        # Colas de eventos SSE por proyecto (asyncio.Queue)
        self.event_queues: Dict[str, asyncio.Queue] = {}
        self._queues_lock = threading.Lock()

        # Buffer de notificaciones SSE
        self.sse_buffer: List[Dict[str, Any]] = []
        self.sse_buffer_lock = threading.Lock()

        # Cache de conversaciones maduras
        self.chat_cache: Dict[str, dict] = {}
        self._chat_cache_lock = threading.Lock()

        # Cache de precios por modelo
        self.price_cache: Dict[str, Dict[str, Any]] = {}
        self._price_cache_lock = threading.Lock()

        # Autoconocimiento (BITACORA/WHITEPAPER)
        self.self_context: str = ""

        # Estado de startup
        self.startup_complete: bool = False
        self.startup_info: Dict[str, Any] = {}

    # ── Proyectos ─────────────────────────────────────────────────────

    def get_project(self, project_id: str) -> Dict[str, Any]:
        """Retorna los datos de un proyecto.

        Args:
            project_id: Identificador del proyecto.

        Returns:
            Diccionario con los datos del proyecto.

        Raises:
            ValueError: Si el proyecto no existe.
        """
        with self._projects_lock:
            if project_id not in self.projects:
                raise ValueError(
                    f"Proyecto '{project_id}' no encontrado. "
                    f"Proyectos disponibles: {list(self.projects.keys())}"
                )
            return self.projects[project_id]

    def add_project(self, project_id: str, project_data: Dict[str, Any]) -> None:
        """Registra un nuevo proyecto.

        Args:
            project_id: Identificador del proyecto.
            project_data: Datos del proyecto.
        """
        with self._projects_lock:
            self.projects[project_id] = project_data

    def remove_project(self, project_id: str) -> None:
        """Elimina un proyecto del estado activo.

        Args:
            project_id: Identificador del proyecto a eliminar.

        Raises:
            ValueError: Si el proyecto no existe.
        """
        with self._projects_lock:
            if project_id not in self.projects:
                raise ValueError(
                    f"Proyecto '{project_id}' no encontrado. "
                    f"No se puede eliminar."
                )
            del self.projects[project_id]

    # ── Colas SSE ─────────────────────────────────────────────────────

    def get_event_queue(self, project_id: str) -> asyncio.Queue:
        """Retorna la cola de eventos SSE de un proyecto.

        Si la cola no existe, la crea automáticamente.
        Debe llamarse desde un contexto async para que asyncio.Queue
        funcione correctamente.

        Args:
            project_id: Identificador del proyecto.

        Returns:
            Cola asyncio.Queue para el proyecto.
        """
        with self._queues_lock:
            if project_id not in self.event_queues:
                self.event_queues[project_id] = asyncio.Queue()
            return self.event_queues[project_id]

    # ── SSE Buffer ────────────────────────────────────────────────────

    def add_sse_event(self, event: Dict[str, Any]) -> None:
        """Añade un evento al buffer de notificaciones SSE.

        Thread-safe. Los eventos se acumulan hasta que un cliente
        los consuma vía get_sse_events() o se limpien.

        Args:
            event: Diccionario con el evento a añadir.
        """
        with self.sse_buffer_lock:
            self.sse_buffer.append(event)

    def get_sse_events(self, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retorna los eventos SSE del buffer.

        Args:
            project_id: Si se proporciona, filtra eventos del proyecto.
                          Si es None, retorna todos los eventos.

        Returns:
            Lista de eventos. No modifica el buffer.
        """
        with self.sse_buffer_lock:
            if project_id is not None:
                return [
                    e for e in self.sse_buffer
                    if e.get("project_id") == project_id
                ]
            return list(self.sse_buffer)

    def clear_sse_buffer(self) -> None:
        """Limpia el buffer de notificaciones SSE.

        Thread-safe. Elimina todos los eventos acumulados.
        """
        with self.sse_buffer_lock:
            self.sse_buffer.clear()

    # ── Chat cache ────────────────────────────────────────────────────

    def get_chat_cache(self, project_id: str) -> Optional[dict]:
        """Retorna el cache de conversación de un proyecto.

        Args:
            project_id: Identificador del proyecto.

        Returns:
            Datos del cache o None si no existe.
        """
        with self._chat_cache_lock:
            return self.chat_cache.get(project_id)

    def set_chat_cache(self, project_id: str, data: dict) -> None:
        """Guarda una conversación en cache.

        Args:
            project_id: Identificador del proyecto.
            data: Datos de la conversación.
        """
        with self._chat_cache_lock:
            self.chat_cache[project_id] = data

    # ── Price cache ───────────────────────────────────────────────────

    def get_price(self, model: str) -> Optional[Dict[str, Any]]:
        """Retorna el precio cacheado de un modelo.

        Args:
            model: Nombre del modelo.

        Returns:
            Datos de precio o None si no existe.
        """
        with self._price_cache_lock:
            return self.price_cache.get(model)

    def set_price(self, model: str, price_data: Dict[str, Any]) -> None:
        """Cachea el precio de un modelo.

        Args:
            model: Nombre del modelo.
            price_data: Datos de precio.
        """
        with self._price_cache_lock:
            self.price_cache[model] = price_data

    # ── Representación ────────────────────────────────────────────────

    def __repr__(self) -> str:
        return (
            f"AppState(projects={len(self.projects)}, "
            f"queues={len(self.event_queues)}, "
            f"sse_buffer={len(self.sse_buffer)}, "
            f"startup_complete={self.startup_complete})"
        )


if __name__ == "__main__":
    print("=== Validación de state.py ===")
    print()

    state = AppState()
    print(f"[OK] AppState creado: {state}")

    # 1. Proyectos: get_project con ValueError
    try:
        state.get_project("no_existe")
        assert False, "Debería haber lanzado ValueError"
    except ValueError as e:
        print(f"[OK] get_project lanza ValueError: {e}")

    # 2. Proyectos: add y get
    state.add_project("p1", {"name": "Test", "status": "active"})
    assert state.get_project("p1")["name"] == "Test"
    print("[OK] add_project + get_project funcionan")

    # 3. Proyectos: remove
    state.remove_project("p1")
    try:
        state.get_project("p1")
        assert False
    except ValueError:
        print("[OK] remove_project elimina correctamente")

    # 4. Proyectos: remove inexistente lanza ValueError
    try:
        state.remove_project("no_existe")
        assert False
    except ValueError:
        print("[OK] remove_project inexistente lanza ValueError")

    # 5. Concurrencia en proyectos
    errors = []

    def writer(i):
        try:
            state.add_project(f"proj_{i}", {"idx": i})
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(errors) == 0
    assert state.get_project("proj_25")["idx"] == 25
    print("[OK] Concurrencia en proyectos (50 threads)")

    # 6. SSE Buffer
    state.clear_sse_buffer()
    state.add_sse_event({"type": "info", "msg": "test1", "project_id": "p1"})
    state.add_sse_event({"type": "info", "msg": "test2", "project_id": "p2"})
    all_events = state.get_sse_events()
    assert len(all_events) == 2
    print("[OK] add_sse_event + get_sse_events funcionan")

    p1_events = state.get_sse_events(project_id="p1")
    assert len(p1_events) == 1
    assert p1_events[0]["project_id"] == "p1"
    print("[OK] get_sse_events filtra por project_id")

    state.clear_sse_buffer()
    assert len(state.get_sse_events()) == 0
    print("[OK] clear_sse_buffer limpia el buffer")

    # 7. Event queues (asyncio.Queue)
    loop = asyncio.new_event_loop()
    q = state.get_event_queue("test_proj")
    assert isinstance(q, asyncio.Queue)
    loop.run_until_complete(q.put({"test": True}))
    result = loop.run_until_complete(q.get())
    assert result["test"] is True
    loop.close()
    print("[OK] get_event_queue crea y retorna asyncio.Queue")

    # 8. Chat cache
    state.set_chat_cache("p1", {"messages": []})
    assert state.get_chat_cache("p1")["messages"] == []
    assert state.get_chat_cache("no_existe") is None
    print("[OK] Chat cache funciona")

    # 9. Price cache
    state.set_price("gpt-4", {"input": 0.03, "output": 0.06})
    assert state.get_price("gpt-4")["input"] == 0.03
    assert state.get_price("no-existe") is None
    print("[OK] Price cache funciona")

    # 10. Startup info
    assert state.startup_complete is False
    state.startup_complete = True
    state.startup_info = {"mb_available": True, "mode": "normal"}
    assert state.startup_complete is True
    assert state.startup_info["mb_available"] is True
    print("[OK] Startup info se establece correctamente")

    # 11. Self context
    state.self_context = "APA es un sistema multiagente..."
    assert "multiagente" in state.self_context
    print("[OK] Self context se establece correctamente")

    # 12. SSE buffer thread-safety
    buffer_errors = []

    def sse_writer(i):
        try:
            state.add_sse_event({"idx": i})
        except Exception as e:
            buffer_errors.append(e)

    threads = [threading.Thread(target=sse_writer, args=(i,)) for i in range(100)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(buffer_errors) == 0
    assert len(state.get_sse_events()) == 100
    print("[OK] SSE buffer thread-safe (100 threads)")

    print()
    print("=== Todas las validaciones pasaron ===")
