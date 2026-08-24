# apa/interface/app/__init__.py
"""__init__.py — Puerta de entrada del paquete interface/app/.

Exporta los componentes públicos que el integrador app.py necesita:
- create_app: Factory para crear la aplicación FastAPI (desde config)
- AppState:   Clase de estado global centralizado (desde state)
- register_*_routes: Funciones de registro de rutas (desde handlers)

Los módulos de handlers se importan de forma diferida cuando el paquete
completo está disponible. En aislamiento solo se exportan los módulos base.
"""

import sys
from pathlib import Path
_THIS_DIR = Path(__file__).resolve()
sys.path.insert(0, str(_THIS_DIR.parent))              # interface/ → resuelve 'app'
sys.path.insert(0, str(_THIS_DIR.parent.parent))        # apa/ → resuelve 'core', 'config'

from app.config_apa import create_app
from app.state import AppState

__all__ = [
    "create_app",
    "AppState",
]


def __getattr__(name: str):
    """Importación diferida de handlers para evitar errores en aislamiento.

    Permite que el integrador haga:
        from app import register_sdd_routes, register_chat_routes, ...

    Sin que el import falle si algún handler no está disponible.
    """
    if not name.startswith("register_") and not name.startswith("mount_"):
        raise AttributeError(f"módulo {__name__!r} no tiene atributo {name!r}")

    _handler_map = {
        "register_startup_routes": "app.startup",
        "register_sdd_routes": "app.sdd_handler",
        "register_chat_routes": "app.chat_handler",
        "register_chat_engine_routes": "app.chat_engine",
        "register_exploration_routes": "app.exploration_handler",
        "register_pipeline_routes": "app.pipeline_handler",
        "register_project_routes": "app.project_handler",
        "register_notification_routes": "app.notifications_handler",
        "register_auditor_routes": "app.failure_auditor_handler",
        "register_plan_routes": "app.plan_handler",
        "register_download_routes": "app.download_handler",
        "register_ui_routes": "app.ui_renderer",
        "register_health_routes": "app.health_handler",
        "register_quota_routes": "app.quota_handler",
        "register_routing_routes": "app.routing_handler",
        "mount_static": "app.ui_static",
    }

    module_path = _handler_map.get(name)
    if module_path is None:
        raise AttributeError(f"módulo {__name__!r} no tiene atributo {name!r}")

    try:
        import importlib
        mod = importlib.import_module(module_path)
        return getattr(mod, name)
    except (ImportError, AttributeError) as exc:
        raise AttributeError(
            f"No se pudo importar {name!r} desde {module_path}: {exc}"
        ) from exc


if __name__ == "__main__":
    print("=== Validación de __init__.py ===")
    print()

    # 1. Verificar exports públicos directos
    assert callable(create_app), "create_app no es callable"
    print("[OK] create_app exportada correctamente")
    assert AppState is not None, "AppState no está disponible"
    print(f"[OK] AppState exportada correctamente: {AppState.__name__}")

    # 2. Verificar __all__
    assert "create_app" in __all__, "create_app falta en __all__"
    assert "AppState" in __all__, "AppState falta en __all__"
    print(f"[OK] __all__ contiene: {__all__}")

    # 3. Verificar que el paquete 'app' se resuelve a este directorio
    import app as _app_pkg
    _expected_dir = str(_THIS_DIR.parent)
    assert _app_pkg.__path__[0] == _expected_dir, (
        f"El paquete 'app' no resuelve a este directorio: "
        f"{_app_pkg.__path__[0]} != {_expected_dir}"
    )
    print(f"[OK] Paquete 'app' resuelve a: {_app_pkg.__path__[0]}")

    # 4. Verificar importación diferida (__getattr__) de un handler
    try:
        _ui_routes = getattr(_app_pkg, "register_ui_routes")
        assert callable(_ui_routes), "register_ui_routes no es callable"
        print("[OK] Importación diferida de register_ui_routes funciona")
    except (ImportError, AttributeError) as exc:
        print(f"[INFO] Importación diferida no disponible en aislamiento: {exc}")

    # 5. Verificar que __getattr__ rechaza atributos inexistentes
    try:
        getattr(_app_pkg, "atributo_inexistente_xyz")
        assert False, "Debería haber lanzado AttributeError"
    except AttributeError:
        print("[OK] __getattr__ rechaza atributos inexistentes correctamente")

    print()
    print("=== Todas las validaciones pasaron ===")
