# apa/interface/app/exploration_handler.py
"""exploration_handler.py — Endpoints de exploración de proyectos para APA.

Expone endpoints seguros para navegar directorios y explorar la
estructura de proyectos. Valida que las rutas no escapen del
directorio raíz del proyecto (path traversal protection).

Clases:
    ExplorationHandler: Manejador de exploración de proyectos.

Funciones:
    register_exploration_routes: Registra los endpoints de exploración.
"""

import asyncio

import sys
from pathlib import Path
_THIS_DIR = Path(__file__).resolve()
sys.path.insert(0, str(_THIS_DIR.parent.parent))        # interface/ → resuelve 'app'
sys.path.insert(0, str(_THIS_DIR.parent.parent.parent))  # apa/ → resuelve 'core', 'config'

from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException

from app.config_apa import logger, WORK_DIRECTORIES
from app.models import BrowseDirectoryRequest, ExploreProjectRequest
from app.state import AppState
from core.project_reader import ProjectReader


class ExplorationHandler:
    """Manejador de exploración de proyectos.

    Proporciona endpoints seguros para navegar directorios y explorar
    la estructura de proyectos sin exponer el sistema de archivos completo.
    Valida que todas las rutas permanezcan dentro del directorio del proyecto.

    Attributes:
        _reader: Instancia de ProjectReader para lectura de proyectos.
    """

    def __init__(self) -> None:
        """Inicializa el manejador de exploración.

        Crea una instancia de ProjectReader para lectura de proyectos.
        Si ProjectReader no está disponible o falla al instanciarse
        (p. ej. requiere project_path que no se conoce aún), el handler
        sigue funcionando pero las operaciones que requieren reader
        se saltan con un warning.
        """
        try:
            self._reader = ProjectReader()
            logger.info("ExplorationHandler: ProjectReader inicializado")
        except Exception as exc:
            self._reader = None
            logger.warning(
                "ExplorationHandler: ProjectReader no inicializado (%s). "
                "Las operaciones de exploración avanzada se omitirán.", exc
            )

    def _validate_path_in_project(
        self, requested_path: Path, project_root: Path
    ) -> Path:
        """Valida que la ruta solicitada no escape del directorio raíz del proyecto.

        Args:
            requested_path: Ruta solicitada por el usuario.
            project_root: Directorio raíz del proyecto.

        Returns:
            Ruta resuelta y validada.

        Raises:
            HTTPException: Si la ruta intenta escapar del directorio del proyecto.
        """
        try:
            resolved = (project_root / requested_path).resolve()
            root_resolved = project_root.resolve()
        except Exception as exc:
            logger.error("ExplorationHandler: Error resolviendo rutas: %s", exc)
            raise HTTPException(
                status_code=400, detail=f"Ruta inválida: {exc}"
            )

        # Seguridad: impedir escapes de directorio (path traversal)
        try:
            resolved.relative_to(root_resolved)
        except ValueError:
            logger.warning(
                "ExplorationHandler: Intento de path traversal — %s fuera de %s",
                resolved, root_resolved,
            )
            raise HTTPException(
                status_code=403,
                detail="La ruta solicitada está fuera del directorio del proyecto",
            )

        return resolved

    def _build_entry_metadata(self, entry_path: Path) -> Dict[str, Any]:
        """Construye los metadatos de una entrada del sistema de archivos.

        Args:
            entry_path: Ruta de la entrada.

        Returns:
            Diccionario con nombre, tipo, tamaño y fecha de modificación.
        """
        try:
            stat = entry_path.stat()
            return {
                "name": entry_path.name,
                "type": "directory" if entry_path.is_dir() else "file",
                "size": stat.st_size if entry_path.is_file() else 0,
                "modified": stat.st_mtime,
            }
        except OSError as exc:
            logger.warning(
                "ExplorationHandler: No se pudieron leer metadatos de %s: %s",
                entry_path, exc,
            )
            return {
                "name": entry_path.name,
                "type": "unknown",
                "size": 0,
                "modified": 0,
                "error": str(exc),
            }

    async def browse_directory(
        self, request: BrowseDirectoryRequest
    ) -> Dict[str, Any]:
        """Lista el contenido de un directorio de forma segura.

        Valida que la ruta no escape del directorio del proyecto,
        luego lista los archivos y subdirectorios.

        Args:
            request: Solicitud con project_id y path.

        Returns:
            Diccionario con path y entries.
        """
        logger.info(
            "ExplorationHandler: browse_directory — proyecto=%s, path=%s",
            request.project_id, request.path,
        )

        project_root = Path(WORK_DIRECTORIES["projects_dir"])
        if request.project_id:
            project_root = project_root / request.project_id

        if not project_root.exists():
            return {
                "path": request.path,
                "entries": [],
                "error": f"Proyecto no encontrado: {request.project_id}",
            }

        # Validar seguridad
        target = Path(request.path)
        validated = self._validate_path_in_project(target, project_root)

        if not validated.is_dir():
            return {
                "path": str(validated),
                "entries": [],
                "error": "La ruta no es un directorio",
            }

        # Listar entradas
        entries: List[Dict[str, Any]] = []
        try:
            for child in sorted(validated.iterdir()):
                if child.name.startswith("."):
                    continue
                entries.append(self._build_entry_metadata(child))
        except PermissionError as exc:
            logger.error(
                "ExplorationHandler: Sin permisos para leer %s: %s",
                validated, exc,
            )
            return {
                "path": str(validated),
                "entries": [],
                "error": f"Sin permisos: {exc}",
            }

        logger.debug(
            "ExplorationHandler: %s — %d entradas", validated, len(entries)
        )
        return {"path": str(validated), "entries": entries}

    async def explore_project(
        self, request: ExploreProjectRequest
    ) -> Dict[str, Any]:
        """Explora la estructura de un proyecto.

        Genera un listado de archivos del proyecto con el foco
        solicitado, usando ProjectReader cuando sea posible.

        Args:
            request: Solicitud con project_id y focus (opcional).

        Returns:
            Diccionario con structure y files.
        """
        logger.info(
            "ExplorationHandler: explore_project — proyecto=%s, focus=%s",
            request.project_id, request.focus,
        )

        project_root = Path(WORK_DIRECTORIES["projects_dir"]) / request.project_id
        if not project_root.exists():
            return {
                "structure": {},
                "files": [],
                "error": f"Proyecto no encontrado: {request.project_id}",
            }

        # Intentar usar ProjectReader primero
        if self._reader is not None:
            try:
                structure = await asyncio.to_thread(
                    self._reader.get_structure, str(project_root)
                )
                files = await asyncio.to_thread(
                    self._reader.list_files, str(project_root)
                )
                return {
                    "structure": structure if isinstance(structure, dict) else {},
                    "files": files if isinstance(files, list) else [],
                }
            except Exception as exc:
                logger.warning(
                    "ExplorationHandler: ProjectReader falló, usando fallback: %s",
                    exc,
                )

        # Fallback: construir estructura manualmente
        structure, files = self._build_project_tree(project_root)
        return {"structure": structure, "files": files}

    def _build_project_tree(
        self, root: Path, max_depth: int = 4
    ) -> tuple:
        """Construye la estructura de árbol y listado de archivos de un proyecto.

        Args:
            root: Ruta raíz del proyecto.
            max_depth: Profundidad máxima de exploración.

        Returns:
            Tupla (structure_dict, files_list).
        """
        files: List[str] = []

        def _walk(path: Path, depth: int) -> Dict[str, Any]:
            node: Dict[str, Any] = {
                "name": path.name,
                "type": "directory" if path.is_dir() else "file",
            }
            if path.is_file():
                try:
                    stat = path.stat()
                    node["size"] = stat.st_size
                    node["modified"] = stat.st_mtime
                except OSError:
                    node["size"] = 0
                    node["modified"] = 0
                # Registrar archivo relativo
                try:
                    rel = path.relative_to(root)
                    files.append(str(rel))
                except ValueError:
                    pass
            elif path.is_dir() and depth < max_depth:
                children = []
                try:
                    for child in sorted(path.iterdir()):
                        if child.name.startswith("."):
                            continue
                        children.append(_walk(child, depth + 1))
                except PermissionError as exc:
                    logger.warning(
                        "ExplorationHandler: Sin permisos en %s: %s", path, exc
                    )
                node["children"] = children

            return node

        structure = _walk(root, 0)
        return structure, files


# ── Registro de rutas ──────────────────────────────────────────────────

def register_exploration_routes(
    app: FastAPI, state: AppState
) -> None:
    """Registra los endpoints de exploración en la aplicación FastAPI.

    Args:
        app: Instancia de la aplicación FastAPI.
        state: Estado global de la aplicación.
    """
    handler = ExplorationHandler()

    @app.post("/api/browse-directory")
    async def browse_directory(req: BrowseDirectoryRequest) -> Dict[str, Any]:
        """Lista el contenido de un directorio del proyecto.

        Valida que la ruta no escape del directorio del proyecto.

        Args:
            req: Solicitud con project_id y path.

        Returns:
            Diccionario con path y entries.
        """
        return await handler.browse_directory(req)

    @app.post("/api/explore-project")
    async def explore_project(req: ExploreProjectRequest) -> Dict[str, Any]:
        """Explora la estructura de un proyecto.

        Args:
            req: Solicitud con project_id y focus.

        Returns:
            Diccionario con structure y files.
        """
        return await handler.explore_project(req)

    logger.info("ExplorationHandler: rutas registradas")


# ── Validación independiente ───────────────────────────────────────────

if __name__ == "__main__":
    import asyncio
    import tempfile
    from unittest.mock import MagicMock, patch

    print("=== Validación de exploration_handler.py ===")
    print()

    # Crear estructura temporal para pruebas
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        (tmp / "src").mkdir()
        (tmp / "src" / "main.py").write_text("# main", encoding="utf-8")
        (tmp / "src" / "utils").mkdir()
        (tmp / "src" / "utils" / "helpers.py").write_text("# helpers", encoding="utf-8")
        (tmp / "README.md").write_text("# readme", encoding="utf-8")
        (tmp / ".hidden").write_text("oculto", encoding="utf-8")

        # Crear estructura de proyecto de prueba: tmp/test_project/src/...
        # (el handler busca projects_dir/project_id/)
        (tmp / "test_project" / "src" / "utils").mkdir(parents=True)
        (tmp / "test_project" / "src" / "utils" / "helpers.py").write_text(
            "# helpers", encoding="utf-8"
        )
        (tmp / "test_project" / "src" / "main.py").write_text(
            "print('hello')", encoding="utf-8"
        )
        (tmp / "test_project" / "README.md").write_text("# readme", encoding="utf-8")

        # Patchear WORK_DIRECTORIES para las pruebas
        original_projects_dir = WORK_DIRECTORIES["projects_dir"]
        WORK_DIRECTORIES["projects_dir"] = tmp

        # Patchear ProjectReader para no requerir dependencias reales
        with patch("exploration_handler.ProjectReader") as MockReader:
            mock_reader_instance = MagicMock()
            MockReader.return_value = mock_reader_instance
            mock_reader_instance.get_structure.return_value = {"type": "directory", "name": "src"}
            mock_reader_instance.list_files.return_value = ["src/main.py", "README.md"]

            handler = ExplorationHandler()

            # Prueba 1: browse_directory
            print("--- Prueba 1: browse_directory ---")
            req = BrowseDirectoryRequest(path="src", project_id="test_project")
            result = asyncio.run(handler.browse_directory(req))
            # Si hay error, fallar; si no, verificar entradas
            assert result.get("error") is None, f"Error inesperado: {result.get('error')}"
            assert len(result["entries"]) == 2  # utils/ y main.py
            print(f"  Entradas ({len(result['entries'])}): {[e['name'] for e in result['entries']]}")
            print("[OK] browse_directory funciona")

            # Prueba 2: explore_project
            print("--- Prueba 2: explore_project ---")
            req2 = ExploreProjectRequest(project_id="test_project")
            result2 = asyncio.run(handler.explore_project(req2))
            assert "structure" in result2
            assert "files" in result2
            print(f"  Archivos: {result2['files']}")
            print("[OK] explore_project funciona")

        # Prueba 3: Prevención de path traversal (sin patch para usar lógica real)
        # Crear handler sin ProjectReader real
        handler_real = ExplorationHandler.__new__(ExplorationHandler)
        handler_real._reader = None  # type: ignore[assignment]

        print("--- Prueba 3: prevención de path traversal ---")
        req3 = BrowseDirectoryRequest(path="../../etc", project_id="test_project")
        try:
            result3 = asyncio.run(handler_real.browse_directory(req3))
            assert result3.get("error") is not None, "Debería tener error"
            print(f"  Error capturado: {result3['error']}")
            print("[OK] Path traversal prevenido")
        except HTTPException as he:
            print(f"  HTTPException: {he.detail}")
            print("[OK] Path traversal prevenido (HTTPException)")

        # Prueba 4: Directorio inexistente
        print("--- Prueba 4: directorio inexistente ---")
        req4 = BrowseDirectoryRequest(path="/no/existe", project_id="fake_proj")
        result4 = asyncio.run(handler_real.browse_directory(req4))
        assert "error" in result4
        print(f"  Error: {result4['error']}")
        print("[OK] Directorio inexistente manejado")

        # Prueba 5: Entradas ocultas se filtran
        print("--- Prueba 5: entradas ocultas filtradas ---")
        req5 = BrowseDirectoryRequest(path=".", project_id="test_project")
        result5 = asyncio.run(handler_real.browse_directory(req5))
        names = [e["name"] for e in result5["entries"]]
        assert ".hidden" not in names
        assert "src" in names or "README.md" in names
        print(f"  Visible: {names}")
        print("[OK] Entradas ocultas filtradas")

        # Restaurar
        WORK_DIRECTORIES["projects_dir"] = original_projects_dir

    # Prueba 6: La clase se importa correctamente
    print("--- Prueba 6: imports ---")
    assert callable(ExplorationHandler._validate_path_in_project)
    assert callable(ExplorationHandler._build_entry_metadata)
    print("[OK] Métodos de ExplorationHandler son invocables")

    print()
    print("=== Todas las validaciones pasaron ===")
