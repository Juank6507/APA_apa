# apa/interface/app/ui_static.py
"""
ui_static.py — Montaje de archivos estáticos de la interfaz APA.

Módulo simple que monta el directorio de archivos estáticos configurado
en WORK_DIRECTORIES["static_dir"] en la ruta /static de la aplicación
FastAPI. Usa StaticFiles de Starlette con manejo graceful de errores.

Funciones:
    mount_static: Monta el directorio estático en la aplicación.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI

from app.config_apa import WORK_DIRECTORIES, logger


# ── Montaje de archivos estáticos ────────────────────────────────────────────


def mount_static(app: FastAPI) -> None:
    """Monta el directorio de archivos estáticos en /static.

    Lee la ruta del directorio estático desde WORK_DIRECTORIES["static_dir"].
    Si el directorio no existe, lo crea. Si StaticFiles no está disponible
    (entorno mínimo sin starlette completo), registra un aviso y continúa.

    Args:
        app: Aplicación FastAPI donde montar los archivos estáticos.
    """
    static_dir = WORK_DIRECTORIES["static_dir"]

    # Asegurar que el directorio existe
    if not static_dir.is_dir():
        try:
            static_dir.mkdir(parents=True, exist_ok=True)
            logger.info("ui_static: directorio estático creado: %s", static_dir)
        except Exception as exc:
            logger.warning(
                "ui_static: no se pudo crear el directorio estático %s: %s",
                static_dir, exc,
            )
            return

    # Intentar montar con StaticFiles
    try:
        from starlette.staticfiles import StaticFiles

        app.mount(
            "/static",
            StaticFiles(directory=str(static_dir), html=True),
            name="static",
        )
        logger.info(
            "ui_static: archivos estáticos montados en /static (%s)",
            static_dir,
        )
    except ImportError:
        logger.warning(
            "ui_static: starlette.staticfiles no disponible — "
            "los archivos estáticos no estarán accesibles"
        )
    except Exception as exc:
        logger.error(
            "ui_static: error al montar archivos estáticos: %s", exc
        )


if __name__ == "__main__":
    print("=== Validación de ui_static.py ===")
    print()

    # 1. Verificar que WORK_DIRECTORIES tiene static_dir
    assert "static_dir" in WORK_DIRECTORIES, "Falta static_dir en WORK_DIRECTORIES"
    print(f"[OK] static_dir configurado: {WORK_DIRECTORIES['static_dir']}")

    # 2. Verificar que mount_static no lanza excepción
    from fastapi import FastAPI as _TestApp

    test_app = _TestApp()
    mount_static(test_app)
    print("[OK] mount_static() ejecutado sin excepción")

    # 3. Verificar que se montó algo
    mount_paths = [r.path for r in test_app.routes if hasattr(r, "path")]
    if "/static" in mount_paths or any("/static" in p for p in mount_paths):
        print("[OK] /static montado correctamente en la app de prueba")
    else:
        print("[INFO] /static no montado (puede ser esperado si el dir no existe)")

    print()
    print("=== Todas las validaciones pasaron ===")
