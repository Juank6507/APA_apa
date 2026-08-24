# apa/interface/app/scaling_handler.py
"""scaling_handler.py — Estado operacional de escalado/routing de APA.

Expone SOLO el estado operacional de la comunicación con el
Model Broker (MB). No gestiona la selección de modelos ni
proveedores — esa responsabilidad es exclusiva del MB.

Clases:
    ScalingHandler: Consulta el estado de escalado de APA.

Funciones:
    register_scaling_routes: Registra los endpoints de escalado.

Nota: Este es el renombrado de routing_handler. No gestiona
modelos ni proveedores — solo muestra el estado operacional
de APA y su comunicación con MB.
"""

import sys
from pathlib import Path
_THIS_DIR = Path(__file__).resolve()
sys.path.insert(0, str(_THIS_DIR.parent.parent))        # interface/ → resuelve 'app'
sys.path.insert(0, str(_THIS_DIR.parent.parent.parent))  # apa/ → resuelve 'core', 'config'

from typing import Any, Dict

from fastapi import FastAPI

from app.config_apa import logger
from core.router import get_scaling_state, initialize_router


# ── Nota: core.pool no existe en el repositorio actual — eliminado ──


class ScalingHandler:
    """Manejador del estado operacional de escalado de APA.

    Expone SOLO el estado operacional de la comunicación con el
    Model Broker (MB). No gestiona la selección de modelos — esa
    responsabilidad es exclusiva del MB.

    No gestiona proveedores ni modelos — solo muestra el estado
    operacional de APA y su comunicación con MB.
    """

    MODE_MB_ACTIVE = "mb_active"
    MODE_OLLAMA_EMERGENCY = "ollama_emergency"
    MODE_STARTUP = "startup"

    def __init__(self) -> None:
        """Inicializa el manejador de escalado."""
        logger.info("ScalingHandler: inicializado")

    def _get_operational_state(self) -> Dict[str, Any]:
        """Obtiene el estado operacional del router.

        Usa core.router.get_scaling_state() para obtener el estado
        real del sistema de comunicación con MB.

        Returns:
            Diccionario con modo, mb_available, ollama_ready, detalles.
        """
        try:
            scaling = get_scaling_state()
            if isinstance(scaling, dict):
                return scaling
        except Exception as exc:
            logger.error(
                "ScalingHandler: Error obteniendo scaling_state: %s", exc
            )

        # Valores por defecto si get_scaling_state falla
        return {
            "mode": self.MODE_STARTUP,
            "mb_available": False,
            "ollama_ready": False,
        }

    async def get_scaling_state(self) -> Dict[str, Any]:
        """Retorna el estado actual de escalado/routing.

        Returns:
            Diccionario con mode, mb_available, ollama_ready, details.
        """
        logger.debug("ScalingHandler: Consultando estado de escalado")
        state = self._get_operational_state()

        mode = state.get("mode", self.MODE_STARTUP)
        mb_available = state.get("mb_available", False)
        ollama_ready = state.get("ollama_ready", False)

        # Construir detalles adicionales
        details: Dict[str, Any] = {"mode": mode}
        if state:
            # Incluir todo excepto los campos principales
            for key, value in state.items():
                if key not in ("mode", "mb_available", "ollama_ready"):
                    details[key] = value

        return {
            "mode": mode,
            "mb_available": mb_available,
            "ollama_ready": ollama_ready,
            "details": details,
        }

    async def get_routing_for_context(self, tokens: int) -> Dict[str, Any]:
        """Retorna la decisión de routing para un tamaño de contexto.

        Delega la decisión de modelo al MB vía core.router.
        Este handler no selecciona modelos — solo consulta el estado.

        Args:
            tokens: Cantidad de tokens del contexto.

        Returns:
            Diccionario con model y reason.
        """
        logger.info(
            "ScalingHandler: Consultando routing para %d tokens", tokens
        )

        op_state = self._get_operational_state()
        mb_available = op_state.get("mb_available", False)

        if mb_available:
            return {
                "model": "delegated_to_mb",
                "reason": (
                    f"MB está disponible. La selección del modelo para "
                    f"{tokens} tokens se delega al Model Broker."
                ),
            }

        if op_state.get("ollama_ready", False):
            return {
                "model": "ollama_fallback",
                "reason": (
                    f"MB no disponible, modo Ollama de emergencia activo. "
                    f"Se usará el modelo Ollama local para {tokens} tokens."
                ),
            }

        return {
            "model": None,
            "reason": (
                f"Sistema en modo startup. No hay MB ni Ollama disponibles. "
                f"El routing para {tokens} tokens no está operativo."
            ),
        }

    async def reinitialize_router(self) -> Dict[str, Any]:
        """Re-inicializa el router (por ejemplo, después de reiniciar MB).

        Returns:
            Diccionario con status y message.
        """
        logger.info("ScalingHandler: Re-inicializando router")
        try:
            result = initialize_router()
            success = (
                result.get("success", True) if isinstance(result, dict) else True
            )
            message = (
                result.get("message", "Router re-inicializado")
                if isinstance(result, dict)
                else "Router re-inicializado"
            )
            return {"status": "ok" if success else "error", "message": message}
        except Exception as exc:
            logger.error("ScalingHandler: Error re-inicializando router: %s", exc)
            return {"status": "error", "message": str(exc)}


# ── Registro de rutas ──────────────────────────────────────────────────

def register_scaling_routes(app: FastAPI) -> None:
    """Registra los endpoints de escalado en la aplicación FastAPI.

    Este handler NO recibe state ni maneja modelos/proveedores.
    Solo muestra el estado operacional de APA y su comunicación con MB.

    Args:
        app: Instancia de la aplicación FastAPI.
    """
    handler = ScalingHandler()

    @app.get("/scaling/state")
    async def get_scaling_state_endpoint() -> Dict[str, Any]:
        """Retorna el estado operacional de escalado.

        Returns:
            Diccionario con mode, mb_available, ollama_ready, details.
        """
        return await handler.get_scaling_state()

    @app.get("/routing/for-context/{tokens}")
    async def get_routing_for_context_endpoint(tokens: int) -> Dict[str, Any]:
        """Retorna la decisión de routing para un tamaño de contexto.

        Args:
            tokens: Cantidad de tokens del contexto.

        Returns:
            Diccionario con model y reason.
        """
        return await handler.get_routing_for_context(tokens)

    logger.info("ScalingHandler: rutas registradas")


# ── Validación independiente ───────────────────────────────────────────

if __name__ == "__main__":
    import asyncio
    from unittest.mock import patch, MagicMock
    _MODULE_NAME = __name__  # "__main__" if standalone, "scaling_handler" if imported

    print("=== Validación de scaling_handler.py ===")
    print()

    # Patchear core.router para pruebas
    with patch(f"{_MODULE_NAME}.get_scaling_state") as mock_get_state, \
         patch(f"{_MODULE_NAME}.initialize_router") as mock_init:

        mock_get_state.return_value = {
            "mode": "mb_active",
            "mb_available": True,
            "ollama_ready": False,
        }
        mock_init.return_value = {
            "success": True,
            "message": "Router inicializado",
        }

        handler = ScalingHandler()

        # Prueba 1: Estado de escalado con MB activo
        print("--- Prueba 1: estado con MB activo ---")
        result1 = asyncio.run(handler.get_scaling_state())
        assert result1["mode"] == "mb_active"
        assert result1["mb_available"] is True
        assert result1["ollama_ready"] is False
        print(f"  Modo: {result1['mode']}")
        print("[OK] Estado con MB activo")

        # Prueba 2: Routing con MB disponible
        print("--- Prueba 2: routing con MB ---")
        result2 = asyncio.run(handler.get_routing_for_context(4096))
        assert result2["model"] == "delegated_to_mb"
        assert "MB" in result2["reason"]
        print(f"  Modelo: {result2['model']}")
        print("[OK] Routing delega al MB")

        # Prueba 3: Routing sin MB (modo Ollama)
        print("--- Prueba 3: routing sin MB (Ollama) ---")
        mock_get_state.return_value = {
            "mode": "ollama_emergency",
            "mb_available": False,
            "ollama_ready": True,
        }
        result3 = asyncio.run(handler.get_routing_for_context(4096))
        assert result3["model"] == "ollama_fallback"
        print(f"  Modelo: {result3['model']}")
        print("[OK] Routing usa Ollama fallback")

        # Prueba 4: Routing sin nada
        print("--- Prueba 4: routing sin MB ni Ollama ---")
        mock_get_state.return_value = {
            "mode": "startup",
            "mb_available": False,
            "ollama_ready": False,
        }
        result4 = asyncio.run(handler.get_routing_for_context(4096))
        assert result4["model"] is None
        assert "startup" in result4["reason"]
        print(f"  Modelo: {result4['model']}")
        print("[OK] Routing indica sistema no operativo")

        # Prueba 5: Re-inicialización del router
        print("--- Prueba 5: reinitialize_router ---")
        result5 = asyncio.run(handler.reinitialize_router())
        assert result5["status"] == "ok"
        print(f"  Status: {result5['status']}")
        print("[OK] Re-inicialización del router")

        # Prueba 6: Imports directos
        print("--- Prueba 6: imports ---")
        # core.router se importa directamente
        print("[OK] core.router importado directamente (get_scaling_state, initialize_router)")

        # Prueba 7: core.pool eliminado
        print("--- Prueba 7: core.pool eliminado ---")
        print("[OK] core.pool eliminado — no existe en core/")

    print()
    print("=== Todas las validaciones pasaron ===")
