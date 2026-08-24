# apa/core/project_state.py — Gestión del último proyecto por interfaz
# Cada interfaz (app web / ensamblador) mantiene su propio estado independiente.

import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Directorio base para almacenar estado por interfaz
_STATE_DIR = Path.home() / ".apa" / "state"


class ProjectState:
    """Gestiona el último proyecto abierto por cada interfaz de forma independiente.

    Cada interfaz (app, ensamblador) tiene su propio archivo de estado.
    Al iniciar, cada interfaz llama a load() para restaurar su último proyecto.
    """

    def __init__(self, interface_id: str, default_project_path: str | None = None):
        """
        Args:
            interface_id: Identificador único de la interfaz ('app' o 'ensamblador').
            default_project_path: Ruta del proyecto por defecto si no hay estado guardado.
        """
        self._interface_id = interface_id
        self._default_path = default_project_path
        self._state_dir = _STATE_DIR
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._state_file = self._state_dir / f"{interface_id}.json"

    @property
    def state_file(self) -> Path:
        return self._state_file

    def save(self, project_path: str, project_name: str) -> None:
        """Guardar el proyecto actual como último abierto para esta interfaz.

        Args:
            project_path: Ruta absoluta al directorio raíz del proyecto.
            project_name: Nombre legible del proyecto.
        """
        state = {
            "path": project_path,
            "name": project_name,
            "last_opened": datetime.now().isoformat(),
            "interface_id": self._interface_id,
        }
        try:
            with open(self._state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            logger.info(f"[{self._interface_id}] Estado guardado: {project_name} ({project_path})")
        except Exception as e:
            logger.error(f"[{self._interface_id}] Error guardando estado: {e}")

    def load(self) -> dict | None:
        """Cargar el último proyecto abierto por esta interfaz.

        Returns:
            Dict con 'path', 'name', 'last_opened', 'interface_id' o None si no hay estado.
        """
        if not self._state_file.exists():
            logger.debug(f"[{self._interface_id}] No hay archivo de estado ({self._state_file})")
            return None
        try:
            with open(self._state_file, "r", encoding="utf-8") as f:
                state = json.load(f)
            state["interface_id"] = self._interface_id
            logger.info(f"[{self._interface_id}] Estado cargado: {state.get('name', '?')} ({state.get('path', '?')})")
            return state
        except Exception as e:
            logger.error(f"[{self._interface_id}] Error cargando estado: {e}")
            return None

    def get_project_path(self) -> str | None:
        """Obtener la ruta del último proyecto, o el proyecto por defecto si existe.

        Returns:
            Ruta al proyecto o None si no hay estado ni default.
        """
        state = self.load()
        if state and state.get("path"):
            project_path = Path(state["path"])
            if project_path.exists():
                return str(project_path)
        if self._default_path:
            default = Path(self._default_path)
            if default.exists():
                return str(default)
        return None

    def get_project_name(self) -> str | None:
        """Obtener el nombre del último proyecto, o el nombre por defecto.

        Returns:
            Nombre del proyecto o None.
        """
        state = self.load()
        if state and state.get("name"):
            return state["name"]
        if self._default_path:
            return Path(self._default_path).name
        return None

    def clear(self) -> None:
        """Eliminar el estado guardado para esta interfaz."""
        if self._state_file.exists():
            try:
                self._state_file.unlink()
                logger.info(f"[{self._interface_id}] Estado eliminado")
            except Exception as e:
                logger.error(f"[{self._interface_id}] Error eliminando estado: {e}")



def save_project_state(interface_id: str, project_path: str, project_name: str) -> None:
    """Guardar el proyecto actual como último abierto para una interfaz.

    Método de conveniencia equivalente a:
        ProjectState(interface_id).save(project_path, project_name)
    """
    state = ProjectState(interface_id)
    state.save(project_path, project_name)


def load_project_state(interface_id: str) -> dict | None:
    """Cargar el último proyecto abierto para una interfaz.

    Método de conveniencia equivalente a:
        ProjectState(interface_id).load()
    """
    state = ProjectState(interface_id)
    return state.load()


def create_app_state() -> ProjectState:
    """Factory: crear estado para la app web (sin proyecto por defecto)."""
    return ProjectState("app", default_project_path=None)


def create_ensamblador_state() -> ProjectState:
    """Factory: crear estado para el ensamblador (APA como proyecto por defecto)."""
    # Detectar la ruta del proyecto APA automáticamente
    candidates = [
        Path(__file__).resolve().parent.parent.parent,  # apa/core/ -> APA/
        Path.cwd(),  # Directorio de trabajo actual
    ]
    for candidate in candidates:
        plan_file = candidate / "docs" / "PLAN_MEJORAS_APA.md"
        if plan_file.exists():
            logger.info(f"Proyecto APA detectado en: {candidate}")
            return ProjectState("ensamblador", default_project_path=str(candidate))
    logger.warning("No se detectó el proyecto APA; ensamblador sin proyecto por defecto")
    return ProjectState("ensamblador", default_project_path=None)


if __name__ == "__main__":
    # Test básico
    logging.basicConfig(level=logging.DEBUG)

    app_state = create_app_state()
    ens_state = create_ensamblador_state()

    print(f"App state file: {app_state.state_file}")
    print(f"Ens state file: {ens_state.state_file}")
    print(f"Ens default path: {ens_state.get_project_path()}")
    print(f"Ens default name: {ens_state.get_project_name()}")

    # Test save/load
    ens_state.save("/tmp/test_project", "Test Project")
    loaded = ens_state.load()
    print(f"Saved and loaded: {loaded}")
    ens_state.clear()
    print(f"After clear: {ens_state.load()}")
