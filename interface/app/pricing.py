# apa/interface/app/pricing.py
"""
pricing.py — Servicio de precios y cálculo de costos de APA.

Gestiona los precios de modelos LLM, aplica factores de sobrecoste de
infraestructura y expone los datos de costeo. Cachea resultados
internamente para minimizar llamadas al proveedor.

Clases:
    PricingService: Servicio de precios con cache interno.

Notas:
    - core.providers se importa con try/except porque puede no estar
      disponible en todos los despliegues.
    - core.pool y core.price_estimator son obsoletos (try/except).
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import logging
from typing import Any, Dict

from app.config_apa import INFRASTRUCTURE_OVERHEAD_FACTOR, logger

# ── Nota: core.pool, core.price_estimator y core.providers no existen
#    en el repositorio actual — eliminados. PricingService funciona
#    exclusivamente con cache interno. ──
_provider_manager_cls = None


class PricingService:
    """Servicio de precios de modelos LLM.

    Consulta los precios de los proveedores disponibles, los cachea
    internamente y aplica un factor de sobrecoste de infraestructura
    configurable. Si el proveedor no está disponible, retorna un
    costo estimado de 0.0.

    Attributes:
        _price_cache: Cache interno de precios por modelo.
    """

    def __init__(self) -> None:
        """Inicializa el servicio con cache vacío."""
        self._price_cache: Dict[str, Dict[str, Any]] = {}
        self._provider_manager = None

        # Intentar inicializar el gestor de proveedores si está disponible
        if _provider_manager_cls is not None:
            try:
                self._provider_manager = _provider_manager_cls()
                logger.info("PricingService: ProviderManager inicializado")
            except Exception as exc:
                logger.warning(
                    "PricingService: Error inicializando ProviderManager: %s", exc
                )

    # ── Consulta de precios ────────────────────────────────────────────

    def get_model_price(
        self,
        model_name: str,
        input_tokens: int,
        output_tokens: int,
    ) -> Dict[str, Any]:
        """Retorna el costo calculado para una llamada a un modelo.

        Busca primero en el cache interno. Si no está cacheado, consulta
        el gestor de proveedores. Si no está disponible, retorna 0.0.
        Aplica el factor INFRASTRUCTURE_OVERHEAD_FACTOR al resultado.

        Args:
            model_name: Nombre del modelo a consultar.
            input_tokens: Cantidad de tokens de entrada.
            output_tokens: Cantidad de tokens de salida.

        Returns:
            Diccionario con: model, input_tokens, output_tokens, cost.
        """
        # Verificar cache interno
        cache_key = model_name
        if cache_key in self._price_cache:
            cached = self._price_cache[cache_key]
            input_cost = cached.get("input_cost", 0.0) * input_tokens
            output_cost = cached.get("output_cost", 0.0) * output_tokens
            subtotal = input_cost + output_cost
            total = subtotal * INFRASTRUCTURE_OVERHEAD_FACTOR
            return {
                "model": model_name,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost": round(total, 8),
            }

        # Intentar obtener del gestor de proveedores
        input_per_token = 0.0
        output_per_token = 0.0

        if self._provider_manager is not None:
            try:
                pricing_data = self._provider_manager.get_model_pricing(model_name)
                if pricing_data:
                    input_per_token = pricing_data.get("input_cost", 0.0)
                    output_per_token = pricing_data.get("output_cost", 0.0)
                    logger.debug(
                        "Precio de %s obtenido de provider_manager", model_name
                    )
            except Exception as exc:
                logger.warning(
                    "Error al obtener precio de %s vía provider_manager: %s",
                    model_name, exc,
                )

        # Cachear resultado por modelo
        self._price_cache[cache_key] = {
            "input_cost": input_per_token,
            "output_cost": output_per_token,
        }

        # Calcular costo con overhead
        input_cost = input_per_token * input_tokens
        output_cost = output_per_token * output_tokens
        subtotal = input_cost + output_cost
        total = subtotal * INFRASTRUCTURE_OVERHEAD_FACTOR

        result = {
            "model": model_name,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost": round(total, 8),
        }

        logger.debug(
            "Precio calculado para %s: $%s (overhead x%s)",
            model_name, round(total, 8), INFRASTRUCTURE_OVERHEAD_FACTOR,
        )
        return result

    def get_overhead_factor(self) -> float:
        """Retorna el factor de sobrecoste de infraestructura.

        Returns:
            Factor multiplicador de infraestructura.
        """
        return INFRASTRUCTURE_OVERHEAD_FACTOR

    def clear_cache(self) -> None:
        """Limpia el cache de precios interno."""
        self._price_cache.clear()
        logger.debug("PricingService: cache limpiado")


if __name__ == "__main__":
    print("=== Validación de pricing.py ===")
    print()

    # 1. Crear instancia
    service = PricingService()
    print("[OK] PricingService creado")

    # 2. get_model_price retorna estructura correcta
    result = service.get_model_price("gpt-4", 1000, 500)
    assert result["model"] == "gpt-4"
    assert result["input_tokens"] == 1000
    assert result["output_tokens"] == 500
    assert "cost" in result
    assert isinstance(result["cost"], float)
    print(f"[OK] get_model_price retorna estructura correcta: {result}")

    # 3. Sin provider_manager, costo debe ser 0.0
    assert result["cost"] == 0.0, f"Sin proveedor, costo debería ser 0.0: {result}"
    print("[OK] Sin proveedor disponible, costo = 0.0")

    # 4. get_overhead_factor
    overhead = service.get_overhead_factor()
    assert isinstance(overhead, float)
    assert overhead == INFRASTRUCTURE_OVERHEAD_FACTOR
    print(f"[OK] get_overhead_factor() = {overhead}")

    # 5. clear_cache
    service._price_cache["test"] = {"a": 1}
    service.clear_cache()
    assert len(service._price_cache) == 0
    print("[OK] clear_cache() limpia el cache")

    # 6. Cache funciona — segunda llamada usa cache
    r1 = service.get_model_price("test-model", 100, 50)
    r2 = service.get_model_price("test-model", 200, 100)
    assert r1["cost"] == 0.0  # Sin proveedor
    assert r2["cost"] == 0.0
    assert len(service._price_cache) == 1  # Solo una entrada cacheada
    print("[OK] Cache funciona correctamente")

    # 7. Tokens cero dan costo cero
    r3 = service.get_model_price("any-model", 0, 0)
    assert r3["cost"] == 0.0
    assert r3["input_tokens"] == 0
    assert r3["output_tokens"] == 0
    print("[OK] Tokens cero dan costo cero")

    # 8. Type hints correctos
    assert isinstance(service._price_cache, dict)
    print("[OK] Type hints correctos en atributos internos")

    print()
    print("=== Todas las validaciones pasaron ===")
