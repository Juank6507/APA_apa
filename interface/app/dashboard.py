# apa/interface/app/dashboard.py
"""
dashboard.py — Servicio de métricas y dashboard de APA.

Recopila métricas del sistema: entradas de cache LLM, llamadas
totales, costos por modelo y actividad reciente. Usa los módulos
core disponibles y hace fallback gracioso si no lo están.

Clases:
    DashboardService: Servicio de métricas del dashboard.

Funciones:
    register_dashboard_routes: Registra GET /dashboard/{project_id}.
"""

import sqlite3

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from typing import Any, Dict, List

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.config_apa import WORK_DIRECTORIES, logger
from app.pricing import PricingService

# Módulos funcionales — import directo (con fallback gracioso en uso)
try:
    from core.usage_tracker import UsageTracker
    _usage_tracker_available = True
except ImportError:
    UsageTracker = None  # type: ignore[assignment, misc]
    _usage_tracker_available = False

try:
    from core.llm_cache import LLMCache
    _llm_cache_available = True
except ImportError:
    LLMCache = None  # type: ignore[assignment, misc]
    _llm_cache_available = False


# ── Constantes ────────────────────────────────────────────────────────────

CACHE_DB_NAME: str = "llm_cache.db"


class DashboardService:
    """Servicio de métricas para el dashboard de APA.

    Recopila métricas de los distintos subsistemas: cache LLM,
    usage tracker, y costos por modelo. Hace fallback gracioso
    si algún módulo no está disponible.

    Attributes:
        pricing: Instancia de PricingService para cálculos de costo.
    """

    def __init__(self, pricing: PricingService) -> None:
        """Inicializa el servicio de dashboard.

        Args:
            pricing: Instancia de PricingService.
        """
        self.pricing = pricing
        self._usage_tracker = None

        if _usage_tracker_available and UsageTracker is not None:
            try:
                self._usage_tracker = UsageTracker()
                logger.info("DashboardService: UsageTracker inicializado")
            except Exception as exc:
                logger.warning(
                    "DashboardService: Error inicializando UsageTracker: %s", exc
                )

    # ── Recopilación de métricas ───────────────────────────────────────

    def get_dashboard_data(self) -> Dict[str, Any]:
        """Recopila todas las métricas del dashboard.

        Returns:
            Diccionario con:
                - cache_entries: int — entradas en cache SQLite.
                - total_calls: int — llamadas totales registradas.
                - model_costs: dict — costos acumulados por modelo.
                - recent_activity: list — actividad reciente.
        """
        cache_entries = self._count_cache_entries()

        total_calls = 0
        model_costs: Dict[str, float] = {}
        recent_activity: List[Dict[str, Any]] = []

        # Intentar obtener datos de UsageTracker
        if self._usage_tracker is not None:
            try:
                stats = self._usage_tracker.get_stats()
                total_calls = stats.get("total_calls", 0)
                model_costs = stats.get("model_costs", {})
                recent_activity = stats.get("recent_activity", [])
            except Exception as exc:
                logger.debug("UsageTracker.get_stats() falló: %s", exc)

        # Intentar obtener costos del cache de precios
        if not model_costs and self.pricing._price_cache:
            model_costs = {
                model: data.get("input_cost", 0.0) + data.get("output_cost", 0.0)
                for model, data in self.pricing._price_cache.items()
            }

        return {
            "cache_entries": cache_entries,
            "total_calls": total_calls,
            "model_costs": model_costs,
            "recent_activity": recent_activity,
        }

    def _count_cache_entries(self) -> int:
        """Cuenta las entradas en el archivo SQLite de cache LLM.

        Busca el archivo llm_cache.db en el directorio de cache
        configurado en WORK_DIRECTORIES["cache_dir"].

        Returns:
            Número de entradas en la tabla de cache, o 0 si no
            se puede acceder.
        """
        cache_dir: Path = WORK_DIRECTORIES["cache_dir"]
        db_path = cache_dir / CACHE_DB_NAME

        if not db_path.exists():
            logger.debug("Cache SQLite no encontrado: %s", db_path)
            return 0

        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()

            # Listar tablas y encontrar la principal
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = [row[0] for row in cursor.fetchall()]

            if not tables:
                conn.close()
                return 0

            # Contar entradas de la primera tabla
            table_name = tables[0]
            cursor.execute(f"SELECT COUNT(*) FROM [{table_name}]")
            count = cursor.fetchone()[0]
            conn.close()

            logger.debug(
                "Cache SQLite: %d entradas en tabla '%s'", count, table_name
            )
            return count

        except Exception as exc:
            logger.warning("Error contando cache SQLite: %s", exc)
            return 0


# ── Registro de rutas ────────────────────────────────────────────────────

def register_dashboard_routes(
    app: FastAPI,
    dashboard: DashboardService,
) -> None:
    """Registra los endpoints del dashboard en la aplicación FastAPI.

    Args:
        app: Aplicación FastAPI donde registrar las rutas.
        dashboard: Instancia de DashboardService.
    """

    @app.get("/dashboard/{project_id}")
    async def get_dashboard(project_id: str):
        """Retorna las métricas del dashboard para un proyecto.

        Args:
            project_id: ID del proyecto.

        Returns:
            JSON con las métricas del dashboard.
        """
        try:
            data = dashboard.get_dashboard_data()
            data["project_id"] = project_id
            return data
        except Exception as exc:
            logger.error("Error en /dashboard/%s: %s", project_id, exc)
            return JSONResponse(
                status_code=500,
                content={"error": f"Error obteniendo dashboard: {exc}"},
            )

    logger.info("Ruta registrada: GET /dashboard/{project_id}")


if __name__ == "__main__":
    print("=== Validación de dashboard.py ===")
    print()

    # 1. Crear servicio con PricingService
    pricing = PricingService()
    dashboard = DashboardService(pricing=pricing)
    print("[OK] DashboardService creado")

    # 2. get_dashboard_data retorna estructura correcta
    data = dashboard.get_dashboard_data()
    assert "cache_entries" in data
    assert "total_calls" in data
    assert "model_costs" in data
    assert "recent_activity" in data
    assert isinstance(data["cache_entries"], int)
    assert isinstance(data["total_calls"], int)
    assert isinstance(data["model_costs"], dict)
    assert isinstance(data["recent_activity"], list)
    print(f"[OK] get_dashboard_data() retorna estructura correcta")
    print(f"     cache_entries={data['cache_entries']}, total_calls={data['total_calls']}")

    # 3. _count_cache_entries retorna int (puede ser 0 si no hay DB)
    count = dashboard._count_cache_entries()
    assert isinstance(count, int)
    assert count >= 0
    print(f"[OK] _count_cache_entries() = {count}")

    # 4. Fallback gracioso sin UsageTracker
    if not _usage_tracker_available:
        assert data["total_calls"] == 0
        assert data["recent_activity"] == []
        print("[OK] Fallback gracioso sin UsageTracker")

    # 5. Fallback gracioso sin LLMCache
    if not _llm_cache_available:
        print("[OK] Fallback gracioso sin LLMCache (no se usa directamente)")

    # 6. model_costs usa pricing cache como fallback
    pricing._price_cache["test-model"] = {"input_cost": 0.03, "output_cost": 0.06}
    data2 = dashboard.get_dashboard_data()
    if not _usage_tracker_available:
        assert "test-model" in data2["model_costs"]
        print("[OK] model_costs usa pricing cache como fallback")
    pricing.clear_cache()

    print()
    print("=== Todas las validaciones pasaron ===")
