# apa/interface/app/sdd_handler.py
"""
sdd_handler.py — Endpoints de evaluación y generación SDD de APA.

Expone endpoints para evaluar la madurez de aspectos del Software
Development Document (SDD) y generar especificaciones completas.
Usa los módulos funcionales de core de forma directa.

Clases:
    SDDHandler: Manejador de endpoints SDD.

Funciones:
    register_sdd_routes: Registra POST /api/sdd-status, /api/build-spec, /api/chat-reset-guide.
"""

import sys
from pathlib import Path
_THIS_DIR = Path(__file__).resolve()
sys.path.insert(0, str(_THIS_DIR.parent.parent))        # interface/ → resuelve 'app'
sys.path.insert(0, str(_THIS_DIR.parent.parent.parent))  # apa/ → resuelve 'core', 'config'

import asyncio
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config_apa import WORK_DIRECTORIES, logger
from app.models import BuildSpecRequest, SDDStatusRequest
from app.state import AppState

# Módulos funcionales — import directo
from core.sdd_maturity import SDDMaturityEvaluator
from core.sdd_guide import SDDGuide
from core.spec_builder import SpecBuilder

# P1 bug fix: call_llm es síncrona — usar asyncio.to_thread() en async endpoints


class SDDHandler:
    """Manejador de endpoints SDD (Software Development Document).

    Gestiona la evaluación de madurez de aspectos del SDD, la
    generación de especificaciones y el reset de la guía SDD.

    Attributes:
        evaluator: Instancia de SDDMaturityEvaluator.
        guide: Instancia de SDDGuide.
        spec_builder: Instancia de SpecBuilder.
    """

    def __init__(self) -> None:
        """Inicializa los evaluadores y constructores SDD."""
        self.evaluator = SDDMaturityEvaluator()
        self.guide = SDDGuide()
        self.spec_builder = SpecBuilder()
        logger.info("SDDHandler: componentes inicializados")

    # ── Lógica de negocio ─────────────────────────────────────────────

    def evaluate_maturity(
        self, aspect: str, content: str
    ) -> Dict[str, Any]:
        """Evalúa la madurez de un aspecto del SDD.

        Args:
            aspect: Nombre del aspecto a evaluar.
            content: Contenido del SDD o sección a evaluar.

        Returns:
            Diccionario con aspect, score, feedback, mature.
        """
        try:
            result = self.evaluator.evaluate(aspect, content)
            score = float(result.get("score", 0.0))
            feedback = str(result.get("feedback", ""))
            mature = score >= 7.0

            return {
                "aspect": aspect,
                "score": score,
                "feedback": feedback,
                "mature": mature,
            }
        except Exception as exc:
            logger.error("SDDHandler: error evaluando madurez: %s", exc)
            return {
                "aspect": aspect,
                "score": 0.0,
                "feedback": f"Error en evaluación: {exc}",
                "mature": False,
            }

    def build_spec(self, project_id: str) -> Dict[str, Any]:
        """Genera una especificación SDD para un proyecto.

        Args:
            project_id: ID del proyecto.

        Returns:
            Diccionario con spec_content y file_path.
        """
        try:
            specs_dir: str = str(WORK_DIRECTORIES["specs_dir"])
            result = self.spec_builder.build(project_id, output_dir=specs_dir)

            spec_content = str(result.get("content", ""))
            file_path = str(result.get("file_path", ""))

            return {
                "spec_content": spec_content,
                "file_path": file_path,
            }
        except Exception as exc:
            logger.error("SDDHandler: error construyendo spec: %s", exc)
            return {
                "spec_content": "",
                "file_path": "",
            }

    def reset_guide(self) -> Dict[str, str]:
        """Resetea la guía SDD.

        Returns:
            Diccionario con status: 'ok'.
        """
        try:
            self.guide.reset()
            logger.info("SDDHandler: guía SDD reseteada")
            return {"status": "ok"}
        except Exception as exc:
            logger.error("SDDHandler: error reseteando guía: %s", exc)
            return {"status": "error", "message": str(exc)}


# ── Registro de rutas ────────────────────────────────────────────────────

def register_sdd_routes(
    app: FastAPI,
    state: Optional[AppState] = None,
) -> None:
    """Registra los endpoints SDD en la aplicación FastAPI.

    Args:
        app: Aplicación FastAPI donde registrar las rutas.
        state: Estado global (opcional, para futuras extensiones).
    """
    handler = SDDHandler()

    @app.post("/api/sdd-status")
    async def sdd_status(request: SDDStatusRequest):
        """Evalúa la madurez de un aspecto del SDD.

        Args:
            request: Petición con project_id, aspect y content.

        Returns:
            JSON con aspect, score, feedback, mature.
        """
        # P1 bug fix: si evaluate_maturity usa call_llm (síncrona),
        # se ejecuta en hilo separado
        result = await asyncio.to_thread(
            handler.evaluate_maturity,
            request.aspect,
            request.content,
        )
        return result

    @app.post("/api/build-spec")
    async def build_spec(request: BuildSpecRequest):
        """Genera una especificación SDD para un proyecto.

        Args:
            request: Petición con project_id.

        Returns:
            JSON con spec_content y file_path.
        """
        # P1 bug fix: si build_spec usa call_llm (síncrona)
        result = await asyncio.to_thread(
            handler.build_spec,
            request.project_id,
        )
        return result

    @app.post("/api/chat-reset-guide")
    async def chat_reset_guide():
        """Resetea la guía SDD.

        Returns:
            JSON con status: 'ok'.
        """
        return handler.reset_guide()

    logger.info("Rutas registradas: POST /api/sdd-status, /api/build-spec, /api/chat-reset-guide")


if __name__ == "__main__":
    print("=== Validación de sdd_handler.py ===")
    print()

    # 1. Crear instancia
    handler = SDDHandler()
    print(f"[OK] SDDHandler creado")
    assert handler.evaluator is not None
    assert handler.guide is not None
    assert handler.spec_builder is not None
    print("[OK] Componentes internos inicializados")

    # 2. evaluate_maturity retorna estructura correcta
    # (Nota: sin LLM real, puede retornar error o valores por defecto)
    result = handler.evaluate_maturity("arquitectura", "El sistema usa microservicios.")
    assert "aspect" in result
    assert "score" in result
    assert "feedback" in result
    assert "mature" in result
    assert result["aspect"] == "arquitectura"
    assert isinstance(result["score"], float)
    assert isinstance(result["mature"], bool)
    print(f"[OK] evaluate_maturity retorna estructura: {result}")

    # 3. build_spec retorna estructura correcta
    spec_result = handler.build_spec("test_project")
    assert "spec_content" in spec_result
    assert "file_path" in spec_result
    assert isinstance(spec_result["spec_content"], str)
    assert isinstance(spec_result["file_path"], str)
    print(f"[OK] build_spec retorna estructura correcta")

    # 4. reset_guide retorna status ok
    reset_result = handler.reset_guide()
    assert "status" in reset_result
    print(f"[OK] reset_guide retorna: {reset_result}")

    # 5. register_sdd_routes no crashea
    from app.config_apa import create_app
    test_app = create_app()
    register_sdd_routes(test_app)
    print("[OK] register_sdd_routes() no crashea")

    # 6. Verificar rutas registradas
    routes = [r.path for r in test_app.routes]
    assert "/api/sdd-status" in routes
    assert "/api/build-spec" in routes
    assert "/api/chat-reset-guide" in routes
    print("[OK] Rutas SDD registradas correctamente")

    # 7. Type hints
    assert isinstance(handler.evaluator, SDDMaturityEvaluator)
    assert isinstance(handler.guide, SDDGuide)
    assert isinstance(handler.spec_builder, SpecBuilder)
    print("[OK] Type hints correctos en componentes")

    print()
    print("=== Todas las validaciones pasaron ===")
