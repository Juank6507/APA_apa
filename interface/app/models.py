# apa/interface/app/models.py
"""models.py — Modelos Pydantic para los endpoints de la aplicación APA.

Define los modelos de validación para las peticiones HTTP. Cada modelo
es una clase Pydantic independiente con campos bien tipados y
validaciones automáticas. No hay lógica de negocio aquí — solo
la definición de la estructura de datos de entrada.

Modelos definidos:
    - ChatRequest:         Mensaje al chat de APA
    - RunRequest:          Ejecutar un proyecto APA
    - AnalyzeRequest:      Analizar un proyecto
    - FailureAuditRequest: Auditar un fallo
    - SDDStatusRequest:    Evaluar madurez del SDD
    - BuildSpecRequest:    Generar especificación SDD
    - BrowseDirectoryRequest: Explorar un directorio
    - ExploreProjectRequest:  Explorar estructura de proyecto
    - PipelineResumeRequest:  Reanudar un pipeline pausado
    - TaskLogRequest:       Consultar bitácora de tareas
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from typing import Optional
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Petición de mensaje al chat de APA.

    Attributes:
        message: Texto del mensaje del usuario.
        project_id: Identificador del proyecto (opcional).
        model: Modelo LLM a usar (opcional, si None usa el por defecto).
    """

    message: str = Field(
        ..., min_length=1, description="Texto del mensaje del usuario"
    )
    project_id: Optional[str] = Field(
        None, description="ID del proyecto asociado"
    )
    model: Optional[str] = Field(
        None, description="Modelo LLM a usar (si None, usa el por defecto)"
    )


class RunRequest(BaseModel):
    """Petición para ejecutar un proyecto APA.

    Attributes:
        project_id: Identificador del proyecto a ejecutar.
    """

    project_id: str = Field(
        ..., min_length=1, description="ID del proyecto a ejecutar"
    )


class AnalyzeRequest(BaseModel):
    """Petición para analizar un proyecto.

    Attributes:
        project_id: Identificador del proyecto a analizar.
        depth: Profundidad del análisis (opcional, por defecto 'standard').
    """

    project_id: str = Field(
        ..., min_length=1, description="ID del proyecto a analizar"
    )
    depth: Optional[str] = Field(
        "standard",
        description="Profundidad del análisis (standard, deep, quick)",
    )


class FailureAuditRequest(BaseModel):
    """Petición para auditar un fallo.

    Attributes:
        project_id: ID del proyecto donde ocurrió el fallo.
        task_id: ID de la tarea que falló (opcional).
        error_context: Contexto adicional del error (opcional).
    """

    project_id: str = Field(
        ..., min_length=1, description="ID del proyecto del fallo"
    )
    task_id: Optional[str] = Field(
        None, description="ID de la tarea que falló"
    )
    error_context: Optional[str] = Field(
        None, description="Contexto adicional del error"
    )


class SDDStatusRequest(BaseModel):
    """Petición para evaluar la madurez del SDD.

    Attributes:
        project_id: Identificador del proyecto.
        aspect: Aspecto a evaluar del SDD.
        content: Contenido del SDD o sección a evaluar.
    """

    project_id: str = Field(
        ..., min_length=1, description="ID del proyecto"
    )
    aspect: str = Field(
        ..., min_length=1, description="Aspecto a evaluar del SDD"
    )
    content: str = Field(
        ..., min_length=1, description="Contenido del SDD a evaluar"
    )


class BuildSpecRequest(BaseModel):
    """Petición para generar una especificación SDD.

    Attributes:
        project_id: Identificador del proyecto.
    """

    project_id: str = Field(
        ..., min_length=1, description="ID del proyecto"
    )


class BrowseDirectoryRequest(BaseModel):
    """Petición para explorar un directorio del proyecto.

    Attributes:
        project_id: ID del proyecto.
        path: Ruta del directorio a explorar.
    """

    project_id: str = Field(
        ..., min_length=1, description="ID del proyecto"
    )
    path: str = Field(
        ..., min_length=1, description="Ruta del directorio a explorar"
    )


class ExploreProjectRequest(BaseModel):
    """Petición para explorar la estructura de un proyecto.

    Attributes:
        project_id: ID del proyecto a explorar.
        focus: Área de enfoque para la exploración (opcional).
    """

    project_id: str = Field(
        ..., min_length=1, description="ID del proyecto a explorar"
    )
    focus: Optional[str] = Field(
        None, description="Área de enfoque (backend, frontend, infra)"
    )


class PipelineResumeRequest(BaseModel):
    """Petición para reanudar un pipeline pausado.

    Attributes:
        project_id: ID del proyecto cuyo pipeline se reanuda.
    """

    project_id: str = Field(
        ..., min_length=1, description="ID del proyecto"
    )


class TaskLogRequest(BaseModel):
    """Petición para consultar la bitácora de tareas.

    Attributes:
        project_id: ID del proyecto.
        task_id: ID de la tarea específica.
    """

    project_id: str = Field(
        ..., min_length=1, description="ID del proyecto"
    )
    task_id: str = Field(
        ..., min_length=1, description="ID de la tarea"
    )


if __name__ == "__main__":
    print("=== Validación de models.py ===")
    print()

    # 1. ChatRequest con datos válidos (solo mensaje obligatorio)
    chat = ChatRequest(message="Hola, quiero crear un proyecto")
    assert chat.message == "Hola, quiero crear un proyecto"
    assert chat.project_id is None
    assert chat.model is None
    print("[OK] ChatRequest con solo mensaje")

    # 2. ChatRequest con todos los campos
    chat_full = ChatRequest(
        message="Continuar proyecto",
        project_id="proj_001",
        model="gpt-4o",
    )
    assert chat_full.project_id == "proj_001"
    assert chat_full.model == "gpt-4o"
    print("[OK] ChatRequest con campos opcionales")

    # 3. ChatRequest con mensaje vacío debe fallar
    try:
        ChatRequest(message="")
        assert False, "Debería haber fallado"
    except Exception:
        print("[OK] ChatRequest rechaza mensaje vacío")

    # 4. RunRequest
    run = RunRequest(project_id="p1")
    assert run.project_id == "p1"
    print("[OK] RunRequest se crea correctamente")

    # 5. AnalyzeRequest con depth por defecto
    analyze = AnalyzeRequest(project_id="p1")
    assert analyze.depth == "standard"
    print("[OK] AnalyzeRequest con depth por defecto")

    # 6. AnalyzeRequest con depth personalizado
    analyze_deep = AnalyzeRequest(project_id="p1", depth="deep")
    assert analyze_deep.depth == "deep"
    print("[OK] AnalyzeRequest con depth personalizado")

    # 7. FailureAuditRequest
    audit = FailureAuditRequest(
        project_id="p1",
        task_id="T3",
        error_context="Timeout en la llamada LLM",
    )
    assert audit.task_id == "T3"
    assert audit.error_context == "Timeout en la llamada LLM"
    print("[OK] FailureAuditRequest con contexto de error")

    # 8. FailureAuditRequest con solo project_id
    audit_min = FailureAuditRequest(project_id="p1")
    assert audit_min.task_id is None
    print("[OK] FailureAuditRequest con solo project_id")

    # 9. SDDStatusRequest
    sdd = SDDStatusRequest(
        project_id="p1",
        aspect="arquitectura",
        content="El sistema usa una arquitectura de microservicios...",
    )
    assert sdd.aspect == "arquitectura"
    assert len(sdd.content) > 10
    print("[OK] SDDStatusRequest con todos los campos")

    # 10. BuildSpecRequest
    build = BuildSpecRequest(project_id="p1")
    assert build.project_id == "p1"
    print("[OK] BuildSpecRequest se crea correctamente")

    # 11. BrowseDirectoryRequest
    browse = BrowseDirectoryRequest(project_id="p1", path="/src/components")
    assert browse.path == "/src/components"
    print("[OK] BrowseDirectoryRequest se crea correctamente")

    # 12. ExploreProjectRequest
    explore = ExploreProjectRequest(project_id="p1", focus="backend")
    assert explore.focus == "backend"
    print("[OK] ExploreProjectRequest con focus")

    # 13. PipelineResumeRequest
    resume = PipelineResumeRequest(project_id="p1")
    assert resume.project_id == "p1"
    print("[OK] PipelineResumeRequest se crea correctamente")

    # 14. TaskLogRequest
    tl = TaskLogRequest(project_id="p1", task_id="T001")
    assert tl.task_id == "T001"
    print("[OK] TaskLogRequest se crea correctamente")

    # 15. Datos inválidos: project_id vacío
    try:
        RunRequest(project_id="")
        assert False, "Debería haber fallado"
    except Exception:
        print("[OK] RunRequest rechaza project_id vacío")

    # 16. Datos inválidos: campo faltante
    try:
        SDDStatusRequest(project_id="p1", aspect="test", content="")
        assert False, "Debería haber fallado"
    except Exception:
        print("[OK] SDDStatusRequest rechaza content vacío")

    print()
    print("=== Todas las validaciones pasaron ===")
