# apa/interface/app/chat_handler.py
"""
chat_handler.py — Endpoints de gestión de conversaciones de APA.

Expone endpoints para cachear conversaciones en memoria,
guardarlas a disco, listar las existentes y cargarlas.
Usa core.chat_utils para las operaciones de persistencia.

Clases:
    ChatHandler: Manejador de operaciones de chat.

Funciones:
    register_chat_routes: Registra endpoints /api/chat-cache, /api/chat-commit,
                          /api/chat-list, /api/chat-load/{filename}.
"""

import sys
from pathlib import Path
_THIS_DIR = Path(__file__).resolve()
sys.path.insert(0, str(_THIS_DIR.parent.parent))        # interface/ → resuelve 'app'
sys.path.insert(0, str(_THIS_DIR.parent.parent.parent))  # apa/ → resuelve 'core', 'config'

from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config_apa import WORK_DIRECTORIES, logger
from app.state import AppState

# Módulo funcional — import directo
from core.chat_utils import (
    cache_chat,
    commit_chat,
    list_chats,
    load_chat,
)


# ── Modelos Pydantic inline (no dependen de models.py para ser standalone) ──

from pydantic import BaseModel, Field


class ChatCacheRequest(BaseModel):
    """Petición para cachear una conversación.

    Attributes:
        chat_id: ID de la conversación.
        messages: Lista de mensajes.
        project_name: Nombre del proyecto.
        project_path: Ruta del proyecto.
        project_variant: Variante del proyecto.
        sdd_status: Estado del SDD.
        objective_summary: Resumen del objetivo.
        maturity_summary: Resumen de madurez.
    """

    chat_id: str = Field(..., min_length=1, description="ID de la conversación")
    messages: List[Dict[str, Any]] = Field(
        default_factory=list, description="Lista de mensajes"
    )
    project_name: str = Field(default="", description="Nombre del proyecto")
    project_path: str = Field(default="", description="Ruta del proyecto")
    project_variant: str = Field(default="", description="Variante")
    sdd_status: Optional[str] = Field(default=None, description="Estado SDD")
    objective_summary: str = Field(default="", description="Resumen objetivo")
    maturity_summary: str = Field(default="", description="Resumen madurez")


class ChatCommitRequest(BaseModel):
    """Petición para guardar una conversación a disco.

    Attributes:
        chat_id: ID de la conversación.
        spec_generated: Si se generó especificación.
    """

    chat_id: str = Field(..., min_length=1, description="ID de la conversación")
    spec_generated: bool = Field(default=False, description="Spec generada")


class ChatHandler:
    """Manejador de operaciones de conversaciones de chat.

    Gestiona el cacheo en memoria y persistencia a disco de
    conversaciones usando core.chat_utils.

    Attributes:
        chats_dir: Ruta al directorio de conversaciones.
        cache: Diccionario de cache en memoria.
    """

    def __init__(self, chats_dir: str, cache: dict) -> None:
        """Inicializa el manejador con el directorio de chats y cache.

        Args:
            chats_dir: Ruta al directorio donde se guardan
                      las conversaciones.
            cache: Diccionario de cache compartido (inyectado).
        """
        self.chats_dir = Path(chats_dir)
        self.chats_dir.mkdir(parents=True, exist_ok=True)
        self.cache = cache
        logger.info("ChatHandler: chats_dir=%s", self.chats_dir)

    # ── Operaciones de cache ─────────────────────────────────────────

    def cache_conversation(self, request: ChatCacheRequest) -> Dict[str, Any]:
        """Cachear una conversación en memoria.

        Delega en core.chat_utils.cache_chat.

        Args:
            request: Petición con datos de la conversación.

        Returns:
            Dict con resultado del cacheo.
        """
        body = {
            "messages": request.messages,
            "project_name": request.project_name,
            "project_path": request.project_path,
            "project_variant": request.project_variant,
            "sdd_status": request.sdd_status,
            "objective_summary": request.objective_summary,
            "maturity_summary": request.maturity_summary,
        }
        result = cache_chat(
            chat_id=request.chat_id,
            body=body,
            cache=self.cache,
        )
        return result

    # ── Operaciones de persistencia ───────────────────────────────────

    def commit_conversation(self, request: ChatCommitRequest) -> Dict[str, Any]:
        """Guarda la conversación cacheada a disco.

        Delega en core.chat_utils.commit_chat.

        Args:
            request: Petición con chat_id y spec_generated.

        Returns:
            Dict con resultado del commit.
        """
        body = {"spec_generated": request.spec_generated}
        result = commit_chat(
            chat_id=request.chat_id,
            body=body,
            cache=self.cache,
            chats_dir=self.chats_dir,
        )
        return result

    def list_saved_conversations(self) -> Dict[str, Any]:
        """Lista las conversaciones guardadas en disco.

        Delega en core.chat_utils.list_chats.

        Returns:
            Dict con lista de conversaciones.
        """
        return list_chats(chats_dir=self.chats_dir)

    def load_saved_conversation(self, filename: str) -> Dict[str, Any]:
        """Carga una conversación guardada desde disco.

        Delega en core.chat_utils.load_chat.

        Args:
            filename: Nombre del archivo a cargar.

        Returns:
            Datos de la conversación.
        """
        return load_chat(filename=filename, chats_dir=self.chats_dir)


# ── Registro de rutas ────────────────────────────────────────────────────

def register_chat_routes(app: FastAPI, state: AppState) -> None:
    """Registra los endpoints de gestión de chat en FastAPI.

    Args:
        app: Aplicación FastAPI donde registrar las rutas.
        state: Estado global de la aplicación.
    """
    chats_dir: str = str(WORK_DIRECTORIES["chats_dir"])
    handler = ChatHandler(chats_dir=chats_dir, cache=state.chat_cache)

    @app.post("/api/chat-cache")
    async def chat_cache(request: ChatCacheRequest):
        """Cachea la conversación actual.

        Args:
            request: Petición con datos de la conversación.

        Returns:
            JSON con resultado del cacheo.
        """
        return handler.cache_conversation(request)

    @app.post("/api/chat-commit")
    async def chat_commit(request: ChatCommitRequest):
        """Guarda la conversación cacheada a disco.

        Args:
            request: Petición con chat_id y spec_generated.

        Returns:
            JSON con resultado del commit.
        """
        return handler.commit_conversation(request)

    @app.get("/api/chat-list")
    async def chat_list():
        """Lista las conversaciones guardadas.

        Returns:
            JSON con lista de conversaciones.
        """
        return handler.list_saved_conversations()

    @app.get("/api/chat-load/{filename}")
    async def chat_load(filename: str):
        """Carga una conversación guardada desde disco.

        Args:
            filename: Nombre del archivo a cargar.

        Returns:
            Datos de la conversación.
        """
        return handler.load_saved_conversation(filename=filename)

    logger.info(
        "ChatHandler: rutas registradas — POST /api/chat-cache, /api/chat-commit, "
        "GET /api/chat-list, GET /api/chat-load/{filename}"
    )


if __name__ == "__main__":
    import tempfile
    import json

    print("=== Validación de chat_handler.py ===")
    print()

    # 1. Crear instancia con directorio temporal
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = {}
        handler = ChatHandler(chats_dir=tmpdir, cache=cache)
        print(f"[OK] ChatHandler creado, chats_dir={handler.chats_dir}")

        # 2. cache_conversation
        req = ChatCacheRequest(
            chat_id="c1",
            messages=[{"role": "user", "content": "Hola"}],
            project_name="Test Project",
        )
        result = handler.cache_conversation(req)
        assert result.get("success") is True
        assert "c1" in cache
        print("[OK] cache_conversation funciona")

        # 3. commit_conversation
        commit_req = ChatCommitRequest(chat_id="c1", spec_generated=False)
        result_commit = handler.commit_conversation(commit_req)
        assert result_commit.get("committed") is True
        assert "filename" in result_commit
        print(f"[OK] commit_conversation: {result_commit['filename']}")

        # 4. list_saved_conversations
        listed = handler.list_saved_conversations()
        assert listed.get("success") is True
        assert len(listed.get("chats", [])) >= 1
        print(f"[OK] list_saved_conversations: {len(listed['chats'])} chats")

        # 5. load_saved_conversation
        filename = result_commit["filename"]
        loaded = handler.load_saved_conversation(filename)
        assert loaded.get("success") is True
        print("[OK] load_saved_conversation funciona")

        # 6. load_saved_conversation inexistente
        not_found = handler.load_saved_conversation("chat_999_no_existe.json")
        assert not_found.get("_status") == 404
        print("[OK] load_saved_conversation inexistente retorna 404")

    print()
    print("=== Todas las validaciones pasaron ===")
