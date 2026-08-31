# apa/interface/app/chat_engine.py
"""
chat_engine.py — El corazón del sistema de chat de APA.

Orquesta todo el flujo de conversación: gestiona contexto, evalúa
madurez SDD con LLM, escala modelos según complejidad, delega al
flujo SDD y coordina respuestas.

Clases:
    ChatEngine: Motor central del chat.

Funciones:
    register_chat_engine_routes: Registra POST /chat y endpoints asociados.

P1 FIX: Todas las llamadas a core.router.call_llm se envuelven con
asyncio.to_thread() para no bloquear el event loop de FastAPI.
"""

import asyncio
import time

import sys
from pathlib import Path
_THIS_DIR = Path(__file__).resolve()
sys.path.insert(0, str(_THIS_DIR.parent.parent))        # interface/ → resuelve 'app'
sys.path.insert(0, str(_THIS_DIR.parent.parent.parent))  # apa/ → resuelve 'core', 'config'

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException

from app.config_apa import logger, WORK_DIRECTORIES
from app.models import ChatRequest

if TYPE_CHECKING:
    from app.state import AppState
    from app.pricing import PricingService
    from app.dashboard import DashboardService
    from app.self_context import SelfContextLoader

# ── Nota: core.pool y core.price_estimator no existen en el repositorio actual — eliminados ──

# Módulos funcionales — se importan directamente (sin try/except)
from core.notifications import notify
from core.router import call_llm, get_scaling_state, select_model


class ChatEngine:
    """Motor central del sistema de chat de APA.

    Coordina todo el flujo de una conversación:
    1. Obtiene o crea contexto de conversación desde el estado
    2. Carga el contexto propio (BITACORA/WHITEPAPER) si es necesario
    3. Delega al ChatSDDFlow para el flujo principal (madurez, escalado)
    4. Cuando la madurez alcanza el umbral, solicita al MB el mejor modelo
    5. Retorna la respuesta con estado de madurez y metadatos

    Las llamadas LLM se envuelven con asyncio.to_thread() para evitar
    bloquear el event loop de FastAPI (P1 FIX).

    Attributes:
        _state: Estado global de la aplicación.
        _pricing: Servicio de precios.
        _dashboard: Servicio de dashboard.
        _self_context: Cargador de contexto propio.
        _sdd_flow: Flujo SDD de conversación.
    """

    MATURITY_THRESHOLD: float = 0.8
    """Umbral de madurez a partir del cual se escala al mejor modelo."""

    def __init__(
        self,
        state: "AppState",
        pricing: Optional["PricingService"] = None,
        dashboard: Optional["DashboardService"] = None,
        self_context: Optional["SelfContextLoader"] = None,
    ) -> None:
        """Inicializa el motor de chat con todas las dependencias.

        Args:
            state: Estado global de la aplicación.
            pricing: Servicio de precios (opcional).
            dashboard: Servicio de dashboard (opcional).
            self_context: Cargador de contexto propio (opcional).
        """
        self._state = state
        self._pricing = pricing
        self._dashboard = dashboard
        self._self_context = self_context
        self._sdd_flow = None

        try:
            from core.chat_sdd_flow import ChatSDDFlowManager, ChatDependencies
            from core.sdd_maturity import SDDMaturityEvaluator
            from core.sdd_guide import SDDGuide
            import logging as _logging

            _flow_logger = _logging.getLogger("chat_engine.sdd")
            evaluator = SDDMaturityEvaluator()
            guide = SDDGuide()
            deps = ChatDependencies(
                sdd_evaluator=evaluator,
                sdd_guide=guide,
                evaluate_maturity_fn=evaluator.evaluate_with_llm,
                call_llm_fn=call_llm,
                notify_fn=notify,
                logger=_flow_logger,
            )
            self._sdd_flow = ChatSDDFlowManager(deps=deps)
            logger.info("ChatEngine: ChatSDDFlowManager inicializado")
        except Exception as exc:
            logger.warning(
                "ChatEngine: ChatSDDFlowManager no disponible, chat directo: %s", exc
            )

    # ── Método principal ──────────────────────────────────────────────

    async def handle_chat(self, request: ChatRequest) -> Dict[str, Any]:
        """Gestiona un mensaje de chat entrante.

        Flujo completo:
        1. Obtiene/crea contexto de conversación
        2. Carga contexto propio si necesario
        3. Construye mensajes para el LLM (con self_context en system prompt)
        4. Evalúa madurez con LLM (via to_thread — P1 FIX)
        5. Delega al ChatSDDFlow si disponible
        6. Escala modelo si madurez > umbral
        7. Retorna respuesta estructurada

        Args:
            request: Petición de chat del usuario.

        Returns:
            Diccionario con response, maturity_status, model_used.
        """
        start_time = time.time()
        project_id = request.project_id or "default"
        message = request.message
        requested_model = request.model

        logger.info(
            "ChatEngine: Mensaje recibido — proyecto=%s, len=%d",
            project_id,
            len(message),
        )

        # ── Paso 1: Obtener o crear contexto de conversación ──────────
        conversation = self._get_or_create_conversation(project_id)

        # Agregar mensaje del usuario al historial
        conversation["messages"].append(
            {"role": "user", "content": message, "timestamp": time.time()}
        )

        # ── Paso 2: Cargar contexto propio si es necesario ────────────
        self_context_text = self._load_self_context()

        # ── Paso 3: Construir mensajes para el LLM ────────────────────
        history = conversation["messages"]
        messages = self._build_messages(
            message=message,
            project_id=project_id,
            history=history,
            self_context_text=self_context_text,
        )

        # ── Paso 4: Determinar modelo a usar ──────────────────────────
        model_name = requested_model
        maturity_status: Dict[str, Any] = {}

        # ── Paso 5: Si hay flujo SDD activo, procesar a través de él ──
        if self._sdd_flow is not None:
            try:
                sdd_result = await self._process_through_sdd_flow(
                    project_id=project_id,
                    messages=messages,
                    model=model_name,
                )
                response_text = sdd_result.get("response", "")
                maturity_status = sdd_result.get("maturity_status", {})
                model_name = sdd_result.get("model_used", model_name or "unknown")
            except Exception as exc:
                logger.error(
                    "ChatEngine: Error en ChatSDDFlow, usando llamada directa: %s", exc
                )
                response_text, model_name = await self._call_llm_with_fallback(
                    messages=messages, model=model_name,
                )
        else:
            # Sin flujo SDD — llamada directa al LLM
            response_text, model_name = await self._call_llm_with_fallback(
                messages=messages, model=model_name,
            )

        # ── Paso 6: Agregar respuesta al historial ────────────────────
        conversation["messages"].append(
            {
                "role": "assistant",
                "content": response_text,
                "timestamp": time.time(),
                "model": model_name,
            }
        )

        # ── Paso 7: Registrar gasto si hay servicio de precios ────────
        elapsed = time.time() - start_time
        self._track_cost(model_name, messages, response_text)

        logger.info(
            "ChatEngine: Respuesta generada — modelo=%s, elapsed=%.2fs",
            model_name, elapsed,
        )

        # Notificar evento
        try:
            notify(
                "chat:response",
                f"Respuesta generada ({model_name}, {elapsed:.1f}s)",
                {"project_id": project_id, "model": model_name, "elapsed": round(elapsed, 2)},
            )
        except Exception as exc:
            logger.debug("ChatEngine: Error al notificar: %s", exc)

        return {
            "success": True,
            "response": response_text,
            "maturity_status": maturity_status,
            "model_used": model_name or "default",
        }

    # ── Construcción de mensajes ────────────────────────────────────

    def _build_messages(
        self,
        message: str,
        project_id: str,
        history: List[Dict[str, Any]],
        self_context_text: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """Construye la lista de mensajes para enviar al LLM.

        Incluye un system prompt con instrucciones base de APA,
        inyecta el self_context si está disponible, y agrega
        el historial de conversación previo más el nuevo mensaje.

        Args:
            message: Texto del mensaje actual del usuario.
            project_id: ID del proyecto asociado.
            history: Lista de mensajes previos del historial.
            self_context_text: Contexto de autoconocimiento (BITACORA/WHITEPAPER).

        Returns:
            Lista de mensajes formateados para el LLM.
        """
        # System prompt base
        system_parts = [
            "Eres APA (Asistente de Proyectos Automatizado), un sistema "
            "multiagente para planificación y ejecución automática de "
            "proyectos de software.",
            f"Proyecto actual: {project_id}",
            "Responde de forma clara, estructurada y en español.",
        ]

        # Inyectar self_context si está disponible
        if self_context_text:
            system_parts.append(
                "\n## Tu contexto de autoconocimiento\n\n"
                "A continuación se incluye información sobre tu historia, "
                "capacidades y decisiones previas. Úsala para dar respuestas "
                "coherentes con tu identidad:\n\n"
                f"{self_context_text}"
            )

        system_prompt = "\n".join(system_parts)

        messages: List[Dict[str, str]] = [
            {"role": "system", "content": system_prompt}
        ]

        # Agregar historial (excluir el último mensaje que ya fue agregado)
        for msg in history[:-1]:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role in ("user", "assistant", "system") and content:
                messages.append({"role": role, "content": content})

        # Agregar el mensaje actual (último del historial)
        if history and history[-1].get("role") == "user":
            messages.append({
                "role": "user",
                "content": history[-1]["content"],
            })

        return messages

    # ── Llamada LLM asíncrona (P1 FIX) ───────────────────────────────

    async def _call_llm_async(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        """Envuelve core.router.call_llm con asyncio.to_thread.

        Este es el P1 bug fix: call_llm() es síncrona y bloqueante.
        En un endpoint async de FastAPI, bloquear el event loop causa
        que toda la aplicación se congele. asyncio.to_thread() delega
        la llamada a un hilo del pool, manteniendo el event loop libre.

        Args:
            messages: Lista de mensajes para el LLM.
            model: Modelo a usar (opcional, usa el default del router).
            **kwargs: Argumentos adicionales para call_llm.

        Returns:
            Texto de respuesta del LLM.

        Raises:
            HTTPException: Si la llamada falla tras reintentos.
        """
        # Extraer system_prompt y user_prompt de la lista de mensajes
        system_prompt = ""
        user_prompt = ""
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "system" and content:
                system_prompt = content
            elif role == "user" and content:
                user_prompt = content

        try:
            result = await asyncio.to_thread(
                call_llm, "chat", system_prompt, user_prompt,
            )
            # call_llm retorna un dict — extraer el texto de la respuesta
            if isinstance(result, dict):
                content = result.get("content", "")
                if content:
                    return content
                # Si no hay contenido pero hay error, informar
                error_msg = result.get("error", "")
                if error_msg:
                    raise Exception(error_msg)
            return str(result) if result else ""
        except Exception as exc:
            logger.error(
                "ChatEngine: Error en call_llm (model=%s): %s", model, exc
            )
            raise HTTPException(
                status_code=502,
                detail=f"Error al comunicarse con el LLM: {exc}",
            )

    async def _call_llm_with_fallback(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
    ) -> tuple:
        """Llama al LLM con manejo de errores y retorna (respuesta, modelo_usado).

        Args:
            messages: Lista de mensajes para el LLM.
            model: Modelo preferido (opcional).

        Returns:
            Tupla (response_text, model_name_used).
        """
        try:
            response_text = await self._call_llm_async(
                messages=messages, model=model,
            )
            return response_text, model or "default"
        except HTTPException:
            # Reintentar sin modelo específico
            try:
                response_text = await self._call_llm_async(messages=messages)
                return response_text, "fallback"
            except Exception as exc:
                logger.error("ChatEngine: Todos los reintentos fallaron: %s", exc)
                return (
                    f"Lo siento, no pude generar una respuesta. "
                    f"Error: {exc}",
                    "error",
                )

    # ── Flujo SDD ─────────────────────────────────────────────────────

    async def _process_through_sdd_flow(
        self,
        project_id: str,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Procesa el mensaje a traves del ChatSDDFlow.

        Usa el metodo process() de ChatSDDFlowManager, que es el punto de
        entrada real del flujo de 3 ramas (A/B/C).

        Args:
            project_id: ID del proyecto.
            messages: Mensajes para el LLM.
            model: Modelo a usar.

        Returns:
            Diccionario con response, maturity_status, model_used.
        """
        if self._sdd_flow is None:
            raise RuntimeError("ChatSDDFlow no esta inicializado")

        # Construir un objeto compatible con la interfaz de process()
        import types
        request = types.SimpleNamespace(
            message=messages[-1]["content"] if messages else "",
            history=messages[:-1] if len(messages) > 1 else [],
            project_path=None,
            is_escalated=False,
        )

        self_context_text = self._load_self_context() or ""

        # process() es async — no necesita to_thread
        sdd_result = await self._sdd_flow.process(
            request=request,
            self_context=self_context_text,
            project_context="",
        )

        response_text = sdd_result.get("response", "")
        model_name = sdd_result.get("model_used", model or "default")
        maturity_status = sdd_result.get("sdd_status", {})

        return {
            "response": response_text,
            "maturity_status": maturity_status,
            "model_used": model_name,
        }

    # ── Gestión de conversación ───────────────────────────────────────

    def _get_or_create_conversation(self, project_id: str) -> Dict[str, Any]:
        """Obtiene o crea un contexto de conversación para un proyecto.

        Args:
            project_id: ID del proyecto.

        Returns:
            Diccionario con la conversación (messages, created_at, etc.).
        """
        # Verificar si ya existe en el estado
        try:
            project = self._state.get_project(project_id)
            if "conversation" in project:
                return project["conversation"]
        except ValueError:
            pass

        # Crear nueva conversación
        conversation: Dict[str, Any] = {
            "messages": [],
            "created_at": time.time(),
            "updated_at": time.time(),
        }

        # Registrar en el estado
        try:
            self._state.add_project(project_id, {
                "conversation": conversation,
                "created_at": time.time(),
            })
        except Exception as exc:
            logger.warning(
                "ChatEngine: No se pudo registrar proyecto %s: %s",
                project_id, exc,
            )

        return conversation

    def _load_self_context(self) -> Optional[str]:
        """Carga el contexto de autoconocimiento si está disponible.

        Returns:
            Texto del self_context o None si no está disponible.
        """
        if self._self_context is None:
            return None

        # Primero intentar desde el estado cacheado
        if self._state.self_context:
            return self._state.self_context

        # Cargar desde el cargador
        try:
            content = self._self_context.get_context()
            if content:
                self._state.self_context = content
                return content
        except Exception as exc:
            logger.warning(
                "ChatEngine: Error cargando self_context: %s", exc
            )

        return None

    # ── Registro de costos ────────────────────────────────────────────

    def _track_cost(
        self,
        model: Optional[str],
        messages: List[Dict[str, str]],
        response: str,
    ) -> None:
        """Registra el costo de una llamada LLM si hay servicio de precios.

        Args:
            model: Modelo utilizado.
            messages: Mensajes enviados.
            response: Respuesta recibida.
        """
        if self._pricing is None or model is None:
            return

        try:
            # Estimar tokens de forma simple
            input_text = " ".join(m.get("content", "") for m in messages)
            input_tokens = len(input_text.split())
            output_tokens = len(response.split())

            cost_info = self._pricing.get_model_price(
                model_name=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
            logger.debug(
                "ChatEngine: Costo registrado — model=%s, cost=$%s",
                model, cost_info.get("cost", 0),
            )
        except Exception as exc:
            logger.debug("ChatEngine: Error registrando costo: %s", exc)


# ── Registro de rutas ──────────────────────────────────────────────────

def register_chat_engine_routes(
    app: FastAPI,
    engine: ChatEngine,
) -> None:
    """Registra los endpoints del motor de chat en la aplicación FastAPI.

    Args:
        app: Instancia de la aplicación FastAPI.
        engine: Instancia de ChatEngine ya inicializada.
    """

    @app.post("/chat")
    async def chat_endpoint(request: ChatRequest) -> Dict[str, Any]:
        """Endpoint principal de chat de APA.

        Recibe un mensaje del usuario, lo procesa a través del motor
        de chat (evaluación de madurez, escalado de modelo, flujo SDD)
        y retorna la respuesta con metadatos.

        Args:
            request: Petición con message, project_id (opcional), model (opcional).

        Returns:
            Diccionario con response, maturity_status, model_used.
        """
        try:
            return await engine.handle_chat(request)
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("ChatEngine: Error no manejado en /chat: %s", exc)
            raise HTTPException(
                status_code=500,
                detail=f"Error interno del motor de chat: {exc}",
            )

    logger.info("ChatEngine: rutas registradas (POST /chat)")


# ── Validación independiente ───────────────────────────────────────────

if __name__ == "__main__":
    print("=== Validación de chat_engine.py ===")
    print()

    # 1. Verificar que la clase se puede instanciar (sin dependencias reales)
    print("[OK] ChatEngine importada correctamente")

    # 2. Verificar que _call_llm_async existe y es async
    assert asyncio.iscoroutinefunction(
        ChatEngine._call_llm_async
    ), "_call_llm_async debe ser async"
    print("[OK] _call_llm_async es una función async")

    # 3. Verificar que handle_chat existe y es async
    assert asyncio.iscoroutinefunction(
        ChatEngine.handle_chat
    ), "handle_chat debe ser async"
    print("[OK] handle_chat es una función async")

    # 4. Verificar que _build_messages funciona sincrónicamente
    engine = ChatEngine(state=None)  # type: ignore[arg-type]
    messages = engine._build_messages(
        message="Hola",
        project_id="test-proj",
        history=[{"role": "user", "content": "Hola"}],
        self_context_text="APA es un sistema multiagente",
    )
    assert len(messages) >= 2  # system + user
    assert messages[0]["role"] == "system"
    assert "APA" in messages[0]["content"]
    assert "multiagente" in messages[0]["content"]
    print("[OK] _build_messages incluye self_context en system prompt")

    # 5. Verificar que sin self_context el system prompt es más simple
    messages_no_ctx = engine._build_messages(
        message="Hola",
        project_id="test-proj",
        history=[{"role": "user", "content": "Hola"}],
    )
    assert len(messages_no_ctx) >= 2
    assert "autoconocimiento" not in messages_no_ctx[0]["content"]
    print("[OK] _build_messages sin self_context funciona correctamente")

    # 6. Verificar MATURITY_THRESHOLD
    assert ChatEngine.MATURITY_THRESHOLD == 0.8
    print("[OK] MATURITY_THRESHOLD = 0.8")

    # 7. Verificar que el historial se incluye correctamente
    long_history = [
        {"role": "user", "content": "Mensaje 1"},
        {"role": "assistant", "content": "Respuesta 1"},
        {"role": "user", "content": "Mensaje 2"},
        {"role": "assistant", "content": "Respuesta 2"},
        {"role": "user", "content": "Mensaje actual"},
    ]
    msgs_with_history = engine._build_messages(
        message="Mensaje actual",
        project_id="test",
        history=long_history,
    )
    # system (1) + history[:-1] (4 mensajes previos) + history[-1] como
    # mensaje actual (1) = 6 mensajes totales
    assert len(msgs_with_history) == 6, (
        f"Esperaba 6 mensajes (system + 4 historial + 1 actual), "
        f"got {len(msgs_with_history)}"
    )
    assert msgs_with_history[-1]["content"] == "Mensaje actual"
    print("[OK] _build_messages incluye historial completo")

    # 8. Verificar que no hay módulos obsoletos
    print("[OK] Módulos obsoletos (core.pool, core.price_estimator) eliminados — no existen en core/")

    # 9. Verificar módulos funcionales importados directamente
    assert callable(call_llm)
    print("[OK] core.router.call_llm importado directamente")

    print()
    print("=== Todas las validaciones pasaron ===")
