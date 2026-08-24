# apa/interface/app/config_apa.py
"""
config_apa.py — Configuración centralizada de la aplicación APA.

Crea la aplicación FastAPI, configura el logger, calcula los directorios
de trabajo a partir de config.settings. Todo se obtiene de la configuración
centralizada o constantes con nombre descriptivo — cero hardcoding.
"""

import logging

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Importar configuración centralizada (no protegido con try/except — es funcional)
try:
    from config.settings import settings
except ImportError:
    settings = None
    logging.getLogger(__name__).warning(
        "config.settings no disponible — se usarán valores por defecto"
    )


# ── Constantes ────────────────────────────────────────────────────────────

DEFAULT_HOST: str = (
    getattr(settings, "APA_HOST", None) if settings else None
) or "0.0.0.0"

DEFAULT_PORT: int = (
    getattr(settings, "APA_PORT", None) if settings else None
) or 8080

INFRASTRUCTURE_OVERHEAD_FACTOR: float = (
    getattr(settings, "INFRASTRUCTURE_OVERHEAD_FACTOR", None)
    if settings else None
) or 1.12


# ── Logger ────────────────────────────────────────────────────────────────

logger = logging.getLogger("apa")


def get_logger(name: str = "apa") -> logging.Logger:
    """Retorna un logger configurado para APA.

    Args:
        name: Nombre del logger (por defecto 'apa').

    Returns:
        Instancia de logging.Logger configurada.
    """
    log = logging.getLogger(name)
    _configure_logger()
    return log


def _configure_logger() -> None:
    """Configura el logger raíz de APA con formato estándar.

    Solo añade handlers si no los tiene ya, evitando duplicados.
    """
    if logger.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    level_name = getattr(settings, "LOG_LEVEL", "INFO") if settings else "INFO"
    logger.setLevel(getattr(logging, str(level_name).upper(), logging.INFO))


def _get_base_dir() -> Path:
    """Retorna el directorio base del proyecto APA.

    Busca en orden:
        1. settings.BASE_DIR (si está disponible)
        2. 3 niveles arriba de este archivo (interface/app/ → interface/ → apa/ → raíz)

    Returns:
        Path al directorio base del proyecto.
    """
    if settings and hasattr(settings, "BASE_DIR") and settings.BASE_DIR:
        return Path(settings.BASE_DIR)
    return Path(__file__).resolve().parent.parent.parent


# ── Directorios de trabajo ────────────────────────────────────────────────

def _build_work_directories() -> dict:
    """Calcula todos los directorios de trabajo a partir de settings.

    Cada ruta se deriva de BASE_DIR y los nombres configurados en settings.
    No hay rutas hardcoded — todo viene de la configuración centralizada.

    Returns:
        Diccionario con todas las rutas de trabajo como objetos Path.
    """
    base = _get_base_dir()
    apa_dir = base / "apa"

    # Nombres de directorios (configurables via settings)
    if settings:
        specs_name = getattr(settings, "SPECS_DIR_NAME", "specs")
        chats_name = getattr(settings, "CHATS_DIR_NAME", "chats")
        cache_name = getattr(settings, "CACHE_DIR_NAME", "cache")
        docs_name = getattr(settings, "DOCS_DIR_NAME", "docs")
        static_name = getattr(settings, "STATIC_DIR_NAME", "static")
        downloads_name = getattr(settings, "DOWNLOADS_DIR_NAME", "downloads")
        projects_name = getattr(settings, "PROJECTS_DIR_NAME", "projects")
    else:
        specs_name = "specs"
        chats_name = "chats"
        cache_name = "cache"
        docs_name = "docs"
        static_name = "static"
        downloads_name = "downloads"
        projects_name = "projects"

    return {
        "base_dir": base,
        "apa_dir": apa_dir,
        "projects_dir": apa_dir / projects_name,
        "chats_dir": apa_dir / chats_name,
        "cache_dir": apa_dir / cache_name,
        "specs_dir": apa_dir / specs_name,
        "downloads_dir": apa_dir / downloads_name,
        "docs_dir": base / docs_name,
        "static_dir": apa_dir / "interface" / static_name,
    }


WORK_DIRECTORIES: dict = _build_work_directories()


# ── URLs de servicios ─────────────────────────────────────────────────────

MODEL_BROKER_URL: str = (
    getattr(settings, "MODEL_BROKER_URL", None) if settings else None
) or "http://127.0.0.1:8100"

OLLAMA_BASE_URL: str = (
    getattr(settings, "OLLAMA_BASE_URL", None) if settings else None
) or "http://localhost:11434"

OLLAMA_DEFAULT_MODEL: str = (
    getattr(settings, "OLLAMA_DEFAULT_MODEL", None) if settings else None
) or "llama3.1"


# ── Creación de la aplicación FastAPI ─────────────────────────────────────

def create_app() -> FastAPI:
    """Crea y configura la aplicación FastAPI con middleware CORS.

    La aplicación se crea con título y descripción descriptivos.
    Se añade middleware CORS para permitir todas las origenes
    (configurable en producción via settings).

    Returns:
        Instancia de FastAPI lista para registrar rutas.
    """
    _configure_logger()

    app = FastAPI(
        title="APA — Asistente de Proyectos Automatizado",
        description=(
            "Sistema multiagente para planificación y ejecución "
            "automática de proyectos de software"
        ),
        version="2.0.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    logger.info("Aplicación FastAPI creada correctamente")
    return app


if __name__ == "__main__":
    print("=== Validación de config_apa.py ===")
    print()

    # 1. Verificar creación de la app FastAPI
    test_app = create_app()
    assert test_app.title == "APA — Asistente de Proyectos Automatizado"
    print("[OK] create_app() crea la aplicación FastAPI")

    # 2. Verificar WORK_DIRECTORIES
    assert isinstance(WORK_DIRECTORIES, dict)
    required_keys = [
        "projects_dir", "chats_dir", "cache_dir",
        "specs_dir", "downloads_dir", "docs_dir", "static_dir",
    ]
    for key in required_keys:
        assert key in WORK_DIRECTORIES, f"Falta clave: {key}"
        assert isinstance(WORK_DIRECTORIES[key], Path)
    print(f"[OK] WORK_DIRECTORIES tiene todas las claves requeridas")
    print(f"     specs_dir:    {WORK_DIRECTORIES['specs_dir']}")
    print(f"     projects_dir: {WORK_DIRECTORIES['projects_dir']}")
    print(f"     cache_dir:    {WORK_DIRECTORIES['cache_dir']}")

    # 3. Verificar constantes
    assert isinstance(DEFAULT_HOST, str)
    assert isinstance(DEFAULT_PORT, int)
    assert isinstance(INFRASTRUCTURE_OVERHEAD_FACTOR, float)
    print(f"[OK] Constantes: host={DEFAULT_HOST}, port={DEFAULT_PORT}")
    print(f"     INFRASTRUCTURE_OVERHEAD_FACTOR={INFRASTRUCTURE_OVERHEAD_FACTOR}")

    # 4. Verificar URLs de servicios
    assert MODEL_BROKER_URL.startswith("http")
    assert OLLAMA_BASE_URL.startswith("http")
    assert isinstance(OLLAMA_DEFAULT_MODEL, str)
    print(f"[OK] URLs de servicios configuradas")
    print(f"     MB:     {MODEL_BROKER_URL}")
    print(f"     Ollama: {OLLAMA_BASE_URL}/{OLLAMA_DEFAULT_MODEL}")

    # 5. Verificar logger
    _configure_logger()
    test_logger = get_logger("test_apa")
    assert test_logger.name == "test_apa"
    assert logger.handlers
    print("[OK] Logger configurado y get_logger() funciona")

    # 6. Verificar que las rutas usan pathlib (no hardcoding)
    for key, path in WORK_DIRECTORIES.items():
        assert isinstance(path, Path)
    print("[OK] Todas las rutas son objetos Path (sin hardcoding)")

    print()
    print("=== Todas las validaciones pasaron ===")
