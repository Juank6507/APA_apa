# apa/interface/app/failure_auditor_handler.py
"""
failure_auditor_handler.py — Endpoint de auditoría de fallos de APA.

Expone el endpoint de diagnóstico que delega en el agente
FailureAuditorAgent del core para analizar y diagnosticar errores
en los pipelines de proyectos.

Clases:
    FailureAuditorHandler: Manejador del auditor de fallos.

Funciones:
    register_auditor_routes: Registra POST /api/failure-auditor/diagnose.
"""

import sys
from pathlib import Path
_THIS_DIR = Path(__file__).resolve()
sys.path.insert(0, str(_THIS_DIR.parent.parent))        # interface/ → resuelve 'app'
sys.path.insert(0, str(_THIS_DIR.parent.parent.parent))  # apa/ → resuelve 'core', 'config'

import asyncio
from typing import Any, Dict, List, Optional

from fastapi import FastAPI

from app.config_apa import logger
from app.models import FailureAuditRequest

# Módulos funcionales — import directo
from core.failure_auditor import FailureAuditorAgent, FailureDiagnosis


class FailureAuditorHandler:
    """Manejador del auditor de fallos.

    Expone el endpoint de diagnóstico que delega en el agente
    FailureAuditorAgent del core para análisis profundo de errores.
    También usa FailureDiagnosis como modelo de datos del diagnóstico.

    Attributes:
        agent: Instancia del agente auditor del core.
    """

    def __init__(self) -> None:
        """Inicializa el manejador del auditor de fallos.

        Crea la instancia de FailureAuditorAgent del core.
        """
        self.agent = FailureAuditorAgent()
        logger.info("FailureAuditorHandler: FailureAuditorAgent inicializado")

    # ── Lógica de negocio ─────────────────────────────────────────────

    def _diagnose(
        self,
        project_id: str,
        task_id: Optional[str],
        error_context: Optional[str],
    ) -> Dict[str, Any]:
        """Ejecuta el diagnóstico de un fallo.

        Delega en FailureAuditorAgent para el análisis y extrae
        el diagnóstico y las recomendaciones del resultado.

        Args:
            project_id: ID del proyecto donde ocurrió el fallo.
            task_id: ID de la tarea que falló (opcional).
            error_context: Contexto adicional del error (opcional).

        Returns:
            Diccionario con "diagnosis" y "recommendations".
        """
        try:
            context: Dict[str, Any] = {
                "project_id": project_id,
                "task_id": task_id,
                "error_context": error_context,
            }

            result = self.agent.diagnose(context)

            if result is None:
                return {
                    "diagnosis": {
                        "success": False,
                        "error": "El agente no retornó resultados",
                    },
                    "recommendations": [],
                }

            # Extraer diagnóstico y recomendaciones
            diagnosis: Dict[str, Any] = {
                "success": result.get("success", True),
                "root_cause": result.get("root_cause"),
                "severity": result.get("severity", "unknown"),
                "steps": result.get("steps", []),
            }
            recommendations: List[str] = result.get("recommendations", [])

            return {
                "diagnosis": diagnosis,
                "recommendations": recommendations,
            }

        except Exception as exc:
            logger.error(
                "FailureAuditorHandler: error en diagnóstico: %s", exc
            )
            return {
                "diagnosis": {
                    "success": False,
                    "error": str(exc),
                },
                "recommendations": [],
            }


# ── Registro de rutas ────────────────────────────────────────────────────

def register_auditor_routes(app: FastAPI) -> None:
    """Registra los endpoints del auditor de fallos.

    Crea una instancia de FailureAuditorHandler y registra
    el endpoint POST /api/failure-auditor/diagnose.

    Args:
        app: Aplicación FastAPI donde registrar las rutas.
    """
    handler = FailureAuditorHandler()

    @app.post("/api/failure-auditor/diagnose")
    async def diagnose_failure_endpoint(
        request: FailureAuditRequest,
    ) -> Dict[str, Any]:
        """Ejecuta el diagnóstico de un fallo en el pipeline.

        Args:
            request: Petición con project_id, task_id, error_context.

        Returns:
            JSON con "diagnosis" y "recommendations".
        """
        # P1 bug fix: si diagnose usa call_llm (síncrona),
        # se ejecuta en hilo separado
        import asyncio as _aio
        result = await _aio.to_thread(
            handler._diagnose,
            request.project_id,
            request.task_id,
            request.error_context,
        )
        return result

    logger.info(
        "FailureAuditorHandler: ruta registrada — "
        "POST /api/failure-auditor/diagnose"
    )


if __name__ == "__main__":
    print("=== Validación de failure_auditor_handler.py ===")
    print()

    # 1. Crear instancia
    handler = FailureAuditorHandler()
    print("[OK] FailureAuditorHandler creado")
    assert handler.agent is not None
    print("[OK] FailureAuditorAgent inicializado")

    # 2. _diagnose retorna estructura correcta
    result = handler._diagnose(
        project_id="proj_001",
        task_id="T3",
        error_context="Timeout en la llamada LLM",
    )
    assert "diagnosis" in result
    assert "recommendations" in result
    assert isinstance(result["recommendations"], list)
    assert "success" in result["diagnosis"]
    print(f"[OK] _diagnose retorna estructura: diagnosis={result['diagnosis'].get('success')}")

    # 3. _diagnose sin task_id ni error_context
    result_min = handler._diagnose(
        project_id="proj_002",
        task_id=None,
        error_context=None,
    )
    assert "diagnosis" in result_min
    print("[OK] _diagnose funciona con campos opcionales None")

    # 4. register_auditor_routes no crashea
    from app.config_apa import create_app
    test_app = create_app()
    register_auditor_routes(test_app)
    print("[OK] register_auditor_routes() no crashea")

    # 5. Verificar rutas registradas
    routes = [r.path for r in test_app.routes]
    assert "/api/failure-auditor/diagnose" in routes
    print("[OK] Ruta POST /api/failure-auditor/diagnose registrada")

    # 6. Imports directos (sin try/except para módulos funcionales)
    from core.failure_auditor import (
        FailureAuditorAgent as _FAA,
        FailureDiagnosis as _FD,
    )
    print("[OK] core.failure_auditor.FailureAuditorAgent y FailureDiagnosis importados directamente")

    # 7. Type hints
    assert isinstance(handler.agent, FailureAuditorAgent)
    print("[OK] Type hints correctos en el agente")

    print()
    print("=== Todas las validaciones pasaron ===")
