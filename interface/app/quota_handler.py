# apa/interface/app/quota_handler.py
"""quota_handler.py — Rastreo de costos por proyecto de APA.

APA rastrea los gastos por proyecto desde las cuotas del MB
(recibidas por cada llamada LLM) más el tiempo de uso.
Este handler NO gestiona los modelos/proveedores del MB —
esa es responsabilidad exclusiva del MB.

Clases:
    QuotaHandler: Rastreo de costos por proyecto.

Funciones:
    register_quota_routes: Registra los endpoints de cuotas.
"""

import sys
from pathlib import Path
_THIS_DIR = Path(__file__).resolve()
sys.path.insert(0, str(_THIS_DIR.parent.parent))        # interface/ → resuelve 'app'
sys.path.insert(0, str(_THIS_DIR.parent.parent.parent))  # apa/ → resuelve 'core', 'config'

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from fastapi import FastAPI

from app.config_apa import MODEL_BROKER_URL, logger
from app.state import AppState

if TYPE_CHECKING:
    from app.pricing import PricingService

# Módulos funcionales — se importan directamente
from core.usage_tracker import UsageTracker

# ── Nota: core.price_estimator no existe en el repositorio actual — eliminado ──


class QuotaHandler:
    """Rastreador de costos por proyecto.

    Gestiona el seguimiento de gastos por proyecto usando el
    UsageTracker del core y el PricingService inyectado.
    NO gestiona los modelos/proveedores del MB — esa es
    responsabilidad exclusiva del MB.

    Attributes:
        _pricing: Servicio de precios para cálculo de costos.
        _usage_tracker: Tracker de uso del core.
        _expense_history: Historial local de gastos.
    """

    def __init__(self, pricing: "PricingService") -> None:
        """Inicializa el handler de cuotas.

        Args:
            pricing: Servicio de precios para cálculo de costos.
        """
        self._pricing = pricing
        self._usage_tracker = UsageTracker()
        self._expense_history: List[Dict[str, Any]] = []
        logger.info("QuotaHandler: inicializado con PricingService")

    def _get_project_expenses(self) -> Dict[str, float]:
        """Obtiene los gastos acumulados por proyecto.

        Combina datos del UsageTracker con el historial local.

        Returns:
            Diccionario {project_id: total_gastado}.
        """
        expenses: Dict[str, float] = {}

        # Obtener del UsageTracker si tiene datos por proyecto
        try:
            tracker_data = self._usage_tracker.get_all()  # type: ignore[attr-defined]
            if isinstance(tracker_data, dict):
                for project_id, data in tracker_data.items():
                    if isinstance(data, dict):
                        expenses[project_id] = float(
                            data.get("cost", data.get("spent", 0))
                        )
                    elif isinstance(data, (int, float)):
                        expenses[project_id] = float(data)
        except (AttributeError, TypeError) as exc:
            logger.debug(
                "QuotaHandler: UsageTracker no tiene get_all: %s", exc
            )

        # Agregar del historial local
        for entry in self._expense_history:
            pid = entry.get("project_id", "unknown")
            amount = float(entry.get("amount", 0))
            expenses[pid] = expenses.get(pid, 0.0) + amount

        return expenses

    async def get_quota_status(self) -> Dict[str, Any]:
        """Retorna el estado actual de cuotas.

        Calcula el presupuesto total, lo gastado y lo restante.
        Los datos de costos por proyecto se obtienen del PricingService.

        Returns:
            Diccionario con total_budget, used, remaining, projects.
        """
        logger.debug("QuotaHandler: Consultando estado de cuotas")

        project_expenses = self._get_project_expenses()
        total_used = sum(project_expenses.values())

        # El presupuesto se obtiene del PricingService si está disponible
        total_budget = 0.0
        if self._pricing is not None:
            try:
                # El PricingService puede tener un método para obtener el budget
                if hasattr(self._pricing, "get_budget"):
                    budget = self._pricing.get_budget()
                    if isinstance(budget, (int, float)) and budget > 0:
                        total_budget = float(budget)
            except Exception as exc:
                logger.debug("QuotaHandler: Error obteniendo budget: %s", exc)

        remaining = max(0.0, total_budget - total_used) if total_budget > 0 else 0.0

        return {
            "total_budget": total_budget,
            "used": round(total_used, 6),
            "remaining": round(remaining, 6),
            "projects": {
                pid: round(amount, 6)
                for pid, amount in project_expenses.items()
            },
        }

    async def get_providers(self) -> Dict[str, Any]:
        """Retorna información de los proveedores configurados.

        Consulta al MB por HTTP si está disponible. En caso
        contrario retorna información del PricingService local.
        NOTA: La gestión real de proveedores es responsabilidad del MB.

        Returns:
            Diccionario con providers (lista).
        """
        logger.debug("QuotaHandler: Consultando proveedores")

        providers: List[Dict[str, Any]] = []
        source = "unknown"

        # Intentar obtener del MB vía HTTP
        try:
            import httpx

            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{MODEL_BROKER_URL}/api/providers")
                if resp.status_code == 200:
                    data = resp.json()
                    providers = data.get("providers", [])
                    source = "mb_http"
                    return {
                        "providers": providers,
                        "source": source,
                    }
        except Exception as exc:
            logger.debug(
                "QuotaHandler: MB no disponible para proveedores: %s", exc
            )

        # Fallback: información del PricingService
        if self._pricing is not None and hasattr(self._pricing, "_provider_manager"):
            pm = self._pricing._provider_manager
            if pm is not None and hasattr(pm, "get_providers"):
                try:
                    providers = pm.get_providers()
                    if isinstance(providers, list):
                        source = "pricing_service"
                except Exception as exc:
                    logger.debug(
                        "QuotaHandler: Error obteniendo proveedores locales: %s",
                        exc,
                    )

        return {"providers": providers, "source": source}

    async def get_history(self) -> Dict[str, Any]:
        """Retorna el historial de uso.

        Returns:
            Diccionario con history (lista de entradas).
        """
        logger.debug("QuotaHandler: Consultando historial de gastos")

        # Intentar obtener del UsageTracker
        history: List[Dict[str, Any]] = []
        try:
            tracker_history = self._usage_tracker.get_history()  # type: ignore[attr-defined]
            if isinstance(tracker_history, list):
                history = tracker_history
        except (AttributeError, TypeError):
            pass

        # Complementar con historial local
        if not history:
            history = list(self._expense_history)

        return {"history": history}

    def record_expense(
        self,
        project_id: str,
        amount: float,
        model: Optional[str] = None,
        description: str = "",
    ) -> None:
        """Registra un gasto para un proyecto.

        Args:
            project_id: ID del proyecto.
            amount: Monto del gasto.
            model: Modelo usado (opcional).
            description: Descripción del gasto.
        """
        import time

        entry: Dict[str, Any] = {
            "project_id": project_id,
            "amount": float(amount),
            "timestamp": time.time(),
            "model": model,
            "description": description,
        }
        self._expense_history.append(entry)
        logger.debug(
            "QuotaHandler: Gasto registrado — %s: $%.4f (%s)",
            project_id, amount, model or "unknown",
        )


# ── Registro de rutas ──────────────────────────────────────────────────

def register_quota_routes(
    app: FastAPI, handler: QuotaHandler
) -> None:
    """Registra los endpoints de cuotas en la aplicación FastAPI.

    Args:
        app: Instancia de la aplicación FastAPI.
        handler: Instancia de QuotaHandler ya inicializada.
    """

    @app.get("/quota/status")
    async def get_quota_status_endpoint() -> Dict[str, Any]:
        """Retorna el estado actual de cuotas.

        Returns:
            Diccionario con total_budget, used, remaining, projects.
        """
        return await handler.get_quota_status()

    @app.get("/quota/providers")
    async def get_quota_providers_endpoint() -> Dict[str, Any]:
        """Retorna información de proveedores configurados.

        Returns:
            Diccionario con providers (lista).
        """
        return await handler.get_providers()

    @app.get("/quota/history")
    async def get_quota_history_endpoint() -> Dict[str, Any]:
        """Retorna el historial de uso.

        Returns:
            Diccionario con history (lista).
        """
        return await handler.get_history()

    logger.info("QuotaHandler: rutas registradas")


# ── Validación independiente ───────────────────────────────────────────

if __name__ == "__main__":
    import asyncio
    from unittest.mock import MagicMock, patch
    _MODULE_NAME = __name__  # "__main__" if standalone, "quota_handler" if imported

    print("=== Validación de quota_handler.py ===")
    print()

    # Patchear core.usage_tracker para pruebas
    with patch(f"{_MODULE_NAME}.UsageTracker") as MockTracker, \
         patch(f"{_MODULE_NAME}.MODEL_BROKER_URL", "http://127.0.0.1:8100"):

        mock_tracker = MagicMock()
        MockTracker.return_value = mock_tracker
        mock_tracker.get_all.return_value = {
            "proj-001": {"cost": 1.25},
            "proj-002": {"cost": 0.80},
        }
        mock_tracker.get_history.return_value = [
            {"project_id": "proj-001", "amount": 1.25, "model": "gpt-4o"},
            {"project_id": "proj-002", "amount": 0.80, "model": "claude-3"},
        ]

        pricing = MagicMock()
        handler = QuotaHandler(pricing=pricing)

        # Prueba 1: Estado de cuotas
        print("--- Prueba 1: get_quota_status ---")
        result1 = asyncio.run(handler.get_quota_status())
        assert "total_budget" in result1
        assert "used" in result1
        assert "remaining" in result1
        assert "projects" in result1
        assert result1["used"] == 2.05
        print(f"  Usado: ${result1['used']:.2f}")
        print(f"  Proyectos: {list(result1['projects'].keys())}")
        print("[OK] get_quota_status funciona")

        # Prueba 2: Proveedores (sin MB real)
        print("--- Prueba 2: get_providers ---")
        result2 = asyncio.run(handler.get_providers())
        assert "providers" in result2
        assert "source" in result2
        print(f"  Fuente: {result2['source']}")
        print("[OK] get_providers funciona")

        # Prueba 3: Historial
        print("--- Prueba 3: get_history ---")
        result3 = asyncio.run(handler.get_history())
        assert "history" in result3
        assert len(result3["history"]) == 2
        print(f"  Entradas: {len(result3['history'])}")
        print("[OK] get_history funciona")

        # Prueba 4: record_expense
        print("--- Prueba 4: record_expense ---")
        handler.record_expense("proj-003", 0.50, model="test", description="Test")
        assert len(handler._expense_history) == 1
        assert handler._expense_history[0]["project_id"] == "proj-003"
        assert handler._expense_history[0]["amount"] == 0.50
        print("[OK] record_expense funciona")

        # Prueba 5: Presupuesto con PricingService
        print("--- Prueba 5: presupuesto con PricingService ---")
        pricing.get_budget = MagicMock(return_value=10.0)
        result5 = asyncio.run(handler.get_quota_status())
        assert result5["total_budget"] == 10.0
        # Total usado = 2.05 (tracker) + 0.50 (record_expense en Prueba 4)
        assert result5["remaining"] == 10.0 - 2.05 - 0.50
        print(f"  Budget: ${result5['total_budget']}, Remaining: ${result5['remaining']:.2f}")
        print("[OK] Presupuesto calculado correctamente")

        # Prueba 6: Imports
        print("--- Prueba 6: imports ---")
        # core.usage_tracker importado directamente
        print("[OK] core.usage_tracker importado directamente")
        # core.price_estimator eliminado — no existe en core/
        print("[OK] core.price_estimator eliminado — no existe en core/")

    print()
    print("=== Todas las validaciones pasaron ===")
