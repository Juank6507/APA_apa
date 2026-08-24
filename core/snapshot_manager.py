# apa/core/snapshot_manager.py
# v1.0 — RF3: Snapshots atómicos para rollback seguro en refactorización.
#         Antes de modificar archivos, se crea un snapshot que guarda
#         el contenido original. Si la operación falla, se restaura
#         todo al estado anterior con un solo comando.
#
# CAPACIDADES:
#   - Crear snapshots atómicos de archivos antes de refactorizar
#   - Rollback: restaurar todos los archivos de un snapshot al estado original
#   - Commit: marcar snapshot como exitoso (la refactorización funcionó)
#   - Snapshots anidados: se pueden crear snapshots dentro de otros
#   - Limpieza automática de snapshots confirmados
#   - Listado de snapshots activos y su estado
#
# DECISIONES ARQUITECTÓNICAS:
#   RF3-1: Snapshots en memoria + disco — memoria para velocidad, disco para persistencia
#   RF3-2: Archivos nuevos (no existían) se eliminan en rollback
#   RF3-3: Archivos modificados se restauran con contenido original
#   RF3-4: Un snapshot se identifica por ID (string) — formato: snap_YYYYMMDD_HHMMSS_N
#   RF3-5: Rollback es atómico — si falla un archivo, se intenta restaurar el resto
#   RF3-6: Snapshots en .apa_snapshots/ dentro del proyecto
#
# CRITERIO DE ACEPTACIÓN RF3:
#   Modificar 3 archivos, hacer que el 3ro falle,
#   y restaurar los 3 al estado anterior con un solo comando.
#
# ============================================================================
import os
import sys
import json
import time
import shutil
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, List, Set, Tuple, Any
from pathlib import Path

# ============================================================================
# Logging setup
# ============================================================================
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    logger.addHandler(handler)
logger.propagate = False


# ============================================================================
# Exports explícitos
# ============================================================================
__all__ = [
    "SnapshotEntry",
    "Snapshot",
    "SnapshotManager",
]


# ============================================================================
# SnapshotEntry — registro de un archivo dentro de un snapshot
# ============================================================================
@dataclass
class SnapshotEntry:
    """Registro de un archivo capturado en un snapshot.

    RF3-2: Si el archivo no existía (was_new=True), se elimina en rollback.
    RF3-3: Si existía, se restaura con el contenido original.
    """
    filepath: str                       # Ruta absoluta del archivo
    original_content: Optional[str]     # Contenido original (None si no existía)
    original_hash: Optional[str]        # Hash MD5 del contenido original
    was_new: bool = False               # True si el archivo no existía antes
    encoding: str = "utf-8"            # Encoding del archivo


# ============================================================================
# Snapshot — colección atómica de archivos capturados
# ============================================================================
@dataclass
class Snapshot:
    """Snapshot atómico de un conjunto de archivos.

    RF3-4: Identificado por ID único.
    RF3-5: Rollback atómico — restaura todos los archivos.
    """
    snapshot_id: str                        # ID único del snapshot
    created_at: str                         # Timestamp ISO
    entries: Dict[str, SnapshotEntry] = field(default_factory=dict)  # filepath → entry
    committed: bool = False                 # True si la refactorización fue exitosa
    description: str = ""                   # Descripción humana de la operación
    parent_id: Optional[str] = None         # ID del snapshot padre (anidación)


# ============================================================================
# SnapshotManager — gestor de snapshots atómicos
# ============================================================================
class SnapshotManager:
    """Gestor de snapshots atómicos para rollback seguro en refactorización.

    RF3-1: Memoria + disco — velocidad y persistencia.
    RF3-6: Snapshots en .apa_snapshots/ dentro del proyecto.

    Uso principal:
        mgr = SnapshotManager("/path/to/project")
        snap_id = mgr.create_snapshot(
            "refactor_validar",
            ["/path/to/utils.py", "/path/to/main.py", "/path/to/helpers.py"]
        )
        # ... modificar archivos ...
        # Si algo falla:
        mgr.rollback(snap_id)
        # Si todo sale bien:
        mgr.commit(snap_id)
    """

    def __init__(self, project_root: Optional[str] = None):
        """Inicializa el SnapshotManager.

        Args:
            project_root: Raíz del proyecto. Si es None, usa el directorio actual.
                          Los snapshots se guardan en .apa_snapshots/ dentro del root.
        """
        self._project_root = Path(project_root or os.getcwd())
        self._snapshots_dir = self._project_root / ".apa_snapshots"
        self._snapshots: Dict[str, Snapshot] = {}
        self._snapshot_counter = 0

        # Cargar snapshots existentes desde disco
        self._load_from_disk()

    # --- Creación de snapshots ---

    def create_snapshot(self, description: str, file_paths: List[str],
                        parent_id: Optional[str] = None) -> str:
        """Crea un snapshot atómico de los archivos especificados.

        Lee el contenido actual de cada archivo y lo guarda. Si un archivo
        no existe, se registra como 'was_new' para eliminación en rollback.

        Args:
            description: Descripción de la operación que se va a realizar.
            file_paths: Lista de rutas absolutas de archivos a capturar.
            parent_id: ID del snapshot padre (para anidación).

        Returns:
            ID del snapshot creado.

        Raises:
            ValueError: Si parent_id no existe.
        """
        if parent_id and parent_id not in self._snapshots:
            raise ValueError(f"Snapshot padre '{parent_id}' no existe")

        # Generar ID único
        self._snapshot_counter += 1
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshot_id = f"snap_{timestamp}_{self._snapshot_counter:03d}"

        # Crear snapshot
        snapshot = Snapshot(
            snapshot_id=snapshot_id,
            created_at=datetime.now().isoformat(),
            description=description,
            parent_id=parent_id,
        )

        # Capturar archivos
        for fpath in file_paths:
            abs_path = str(Path(fpath).resolve())
            entry = self._capture_file(abs_path)
            snapshot.entries[abs_path] = entry

        # Guardar en memoria y disco
        self._snapshots[snapshot_id] = snapshot
        self._save_to_disk(snapshot)

        logger.info(f"Snapshot creado: {snapshot_id} — {len(snapshot.entries)} archivos — '{description}'")
        return snapshot_id

    def _capture_file(self, abs_path: str) -> SnapshotEntry:
        """Captura el estado actual de un archivo.

        RF3-2: Si no existe, se marca como was_new.
        RF3-3: Si existe, se guarda el contenido original.
        """
        if os.path.exists(abs_path):
            try:
                with open(abs_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                content_hash = self._hash_content(content)
                return SnapshotEntry(
                    filepath=abs_path,
                    original_content=content,
                    original_hash=content_hash,
                    was_new=False,
                    encoding="utf-8",
                )
            except (UnicodeDecodeError, IOError) as e:
                logger.warning(f"No se pudo leer {abs_path}: {e}")
                return SnapshotEntry(
                    filepath=abs_path,
                    original_content=None,
                    original_hash=None,
                    was_new=False,
                )
        else:
            # Archivo no existe — será nuevo después de la refactorización
            return SnapshotEntry(
                filepath=abs_path,
                original_content=None,
                original_hash=None,
                was_new=True,
            )

    # --- Rollback ---

    def rollback(self, snapshot_id: str) -> Tuple[bool, List[str]]:
        """Restaura todos los archivos de un snapshot al estado original.

        RF3-5: Rollback atómico — si falla un archivo, se intenta restaurar
        el resto y se reportan los fallos.

        Args:
            snapshot_id: ID del snapshot a restaurar.

        Returns:
            (success, errors): success=True si todos los archivos se restauraron,
            errors es lista de mensajes de error.
        """
        snapshot = self._snapshots.get(snapshot_id)
        if not snapshot:
            return (False, [f"Snapshot '{snapshot_id}' no encontrado"])

        if snapshot.committed:
            return (False, [f"Snapshot '{snapshot_id}' ya fue confirmado — no se puede rollback"])

        errors = []
        restored = 0

        for abs_path, entry in snapshot.entries.items():
            try:
                if entry.was_new:
                    # RF3-2: Archivo era nuevo — eliminar
                    if os.path.exists(abs_path):
                        os.remove(abs_path)
                        logger.info(f"Rollback: eliminado archivo nuevo {abs_path}")
                    restored += 1
                else:
                    # RF3-3: Archivo existía — restaurar contenido original
                    if entry.original_content is not None:
                        # Asegurar que el directorio existe
                        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
                        with open(abs_path, 'w', encoding=entry.encoding) as f:
                            f.write(entry.original_content)
                        logger.info(f"Rollback: restaurado {abs_path}")
                        restored += 1
                    else:
                        errors.append(f"No se pudo restaurar {abs_path}: contenido original no disponible")
            except IOError as e:
                errors.append(f"Error restaurando {abs_path}: {e}")

        success = len(errors) == 0
        if success:
            logger.info(f"Rollback exitoso: {snapshot_id} — {restored} archivos restaurados")
        else:
            logger.warning(f"Rollback con errores: {snapshot_id} — {restored} restaurados, {len(errors)} errores")

        return (success, errors)

    def rollback_selective(self, snapshot_id: str, files: List[str]) -> Tuple[bool, List[str]]:
        """Restaura solo los archivos especificados de un snapshot.

        A diferencia de rollback(), que restaura todos los archivos,
        este método permite seleccionar qué archivos restaurar,
        dejando los demás en su estado actual.

        RF3: Caso de uso del asesor — a veces solo quieres restaurar
        ciertos archivos, no todos.

        Args:
            snapshot_id: ID del snapshot a restaurar parcialmente.
            files: Lista de rutas absolutas de archivos a restaurar.

        Returns:
            (success, errors): success=True si todos los archivos
            seleccionados se restauraron correctamente.
        """
        snapshot = self._snapshots.get(snapshot_id)
        if not snapshot:
            return (False, [f"Snapshot '{snapshot_id}' no encontrado"])

        if snapshot.committed:
            return (False, [f"Snapshot '{snapshot_id}' ya fue confirmado — no se puede rollback"])

        # Normalizar rutas para comparación
        target_paths = set(str(Path(f).resolve()) for f in files)

        errors = []
        restored = 0

        for abs_path, entry in snapshot.entries.items():
            if abs_path not in target_paths:
                continue  # Solo restaurar los archivos solicitados

            try:
                if entry.was_new:
                    if os.path.exists(abs_path):
                        os.remove(abs_path)
                        logger.info(f"Rollback selectivo: eliminado archivo nuevo {abs_path}")
                    restored += 1
                else:
                    if entry.original_content is not None:
                        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
                        with open(abs_path, 'w', encoding=entry.encoding) as f:
                            f.write(entry.original_content)
                        logger.info(f"Rollback selectivo: restaurado {abs_path}")
                        restored += 1
                    else:
                        errors.append(f"No se pudo restaurar {abs_path}: contenido original no disponible")
            except IOError as e:
                errors.append(f"Error restaurando {abs_path}: {e}")

        success = len(errors) == 0
        if success:
            logger.info(f"Rollback selectivo exitoso: {snapshot_id} — {restored} archivos restaurados")
        else:
            logger.warning(f"Rollback selectivo con errores: {snapshot_id} — {restored} restaurados, {len(errors)} errores")

        return (success, errors)

    def rollback_last(self) -> Tuple[bool, List[str]]:
        """Restaura el snapshot más reciente que no ha sido confirmado.

        Convenience method para el caso más común.

        Returns:
            (success, errors): resultado del rollback.
        """
        uncommitted = [s for s in self._snapshots.values() if not s.committed]
        if not uncommitted:
            return (False, ["No hay snapshots sin confirmar para rollback"])

        # Ordenar por ID descendente (el ID incluye contador secuencial único)
        uncommitted.sort(key=lambda s: s.snapshot_id, reverse=True)
        last = uncommitted[0]
        return self.rollback(last.snapshot_id)

    # --- Commit ---

    def commit(self, snapshot_id: str) -> bool:
        """Marca un snapshot como confirmado (refactorización exitosa).

        Después del commit, no se puede hacer rollback de este snapshot.
        Los snapshots confirmados se pueden limpiar con prune().

        Args:
            snapshot_id: ID del snapshot a confirmar.

        Returns:
            True si se confirmó correctamente.
        """
        snapshot = self._snapshots.get(snapshot_id)
        if not snapshot:
            logger.error(f"Snapshot '{snapshot_id}' no encontrado")
            return False

        snapshot.committed = True
        self._update_disk(snapshot)
        logger.info(f"Snapshot confirmado: {snapshot_id} — '{snapshot.description}'")
        return True

    # --- Consultas ---

    def list_snapshots(self, include_committed: bool = False) -> List[Dict[str, Any]]:
        """Retorna información de los snapshots.

        Args:
            include_committed: Si True, incluye snapshots ya confirmados.

        Returns:
            Lista de dicts con info de cada snapshot.
        """
        result = []
        for snap in self._snapshots.values():
            if snap.committed and not include_committed:
                continue
            result.append({
                "snapshot_id": snap.snapshot_id,
                "created_at": snap.created_at,
                "description": snap.description,
                "committed": snap.committed,
                "file_count": len(snap.entries),
                "files": list(snap.entries.keys()),
                "parent_id": snap.parent_id,
            })
        result.sort(key=lambda x: x["snapshot_id"], reverse=True)
        return result

    def get_snapshot(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        """Retorna información detallada de un snapshot."""
        snap = self._snapshots.get(snapshot_id)
        if not snap:
            return None
        return {
            "snapshot_id": snap.snapshot_id,
            "created_at": snap.created_at,
            "description": snap.description,
            "committed": snap.committed,
            "file_count": len(snap.entries),
            "files": [
                {
                    "path": entry.filepath,
                    "was_new": entry.was_new,
                    "has_content": entry.original_content is not None,
                    "hash": entry.original_hash,
                }
                for entry in snap.entries.values()
            ],
            "parent_id": snap.parent_id,
        }

    def has_uncommitted(self) -> bool:
        """Retorna True si hay snapshots sin confirmar (activos)."""
        return any(not s.committed for s in self._snapshots.values())

    # --- Limpieza ---

    def prune(self, keep_last_n: int = 5) -> int:
        """Elimina snapshots confirmados, manteniendo los últimos N.

        Args:
            keep_last_n: Número de snapshots confirmados a conservar.

        Returns:
            Número de snapshots eliminados.
        """
        committed = [s for s in self._snapshots.values() if s.committed]
        committed.sort(key=lambda s: s.snapshot_id, reverse=True)

        to_remove = committed[keep_last_n:]
        removed = 0
        for snap in to_remove:
            self._remove_from_disk(snap)
            del self._snapshots[snap.snapshot_id]
            removed += 1

        if removed > 0:
            logger.info(f"Prune: eliminados {removed} snapshots confirmados antiguos")
        return removed

    def clear_all(self) -> int:
        """Elimina TODOS los snapshots (memoria + disco).

        Returns:
            Número de snapshots eliminados.
        """
        count = len(self._snapshots)
        self._snapshots.clear()

        if self._snapshots_dir.exists():
            try:
                shutil.rmtree(str(self._snapshots_dir))
            except IOError as e:
                logger.warning(f"Error eliminando directorio de snapshots: {e}")

        logger.info(f"Todos los snapshots eliminados: {count}")
        return count

    # --- Persistencia ---

    def _save_to_disk(self, snapshot: Snapshot) -> None:
        """Guarda un snapshot a disco en formato JSON."""
        try:
            self._snapshots_dir.mkdir(parents=True, exist_ok=True)
            snap_file = self._snapshots_dir / f"{snapshot.snapshot_id}.json"

            data = {
                "snapshot_id": snapshot.snapshot_id,
                "created_at": snapshot.created_at,
                "description": snapshot.description,
                "committed": snapshot.committed,
                "parent_id": snapshot.parent_id,
                "entries": {
                    path: {
                        "filepath": entry.filepath,
                        "original_content": entry.original_content,
                        "original_hash": entry.original_hash,
                        "was_new": entry.was_new,
                        "encoding": entry.encoding,
                    }
                    for path, entry in snapshot.entries.items()
                }
            }

            tmp_file = snap_file.with_suffix('.tmp')
            with open(tmp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(str(tmp_file), str(snap_file))

        except IOError as e:
            logger.warning(f"Error guardando snapshot a disco: {e}")

    def _update_disk(self, snapshot: Snapshot) -> None:
        """Actualiza un snapshot existente en disco (ej: después de commit)."""
        self._save_to_disk(snapshot)

    def _remove_from_disk(self, snapshot: Snapshot) -> None:
        """Elimina un snapshot del disco."""
        snap_file = self._snapshots_dir / f"{snapshot.snapshot_id}.json"
        if snap_file.exists():
            try:
                snap_file.unlink()
            except IOError as e:
                logger.warning(f"Error eliminando snapshot del disco: {e}")

    def _load_from_disk(self) -> None:
        """Carga snapshots existentes desde disco al iniciar."""
        if not self._snapshots_dir.exists():
            return

        loaded = 0
        for snap_file in self._snapshots_dir.glob("snap_*.json"):
            try:
                with open(snap_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                snapshot = Snapshot(
                    snapshot_id=data["snapshot_id"],
                    created_at=data["created_at"],
                    description=data.get("description", ""),
                    committed=data.get("committed", False),
                    parent_id=data.get("parent_id"),
                )

                for path, entry_data in data.get("entries", {}).items():
                    snapshot.entries[path] = SnapshotEntry(
                        filepath=entry_data["filepath"],
                        original_content=entry_data.get("original_content"),
                        original_hash=entry_data.get("original_hash"),
                        was_new=entry_data.get("was_new", False),
                        encoding=entry_data.get("encoding", "utf-8"),
                    )

                self._snapshots[snapshot.snapshot_id] = snapshot

                # Actualizar contador para IDs únicos
                parts = snapshot.snapshot_id.split('_')
                if len(parts) >= 4:
                    try:
                        counter = int(parts[-1])
                        self._snapshot_counter = max(self._snapshot_counter, counter)
                    except ValueError:
                        pass

                loaded += 1

            except (json.JSONDecodeError, KeyError, IOError) as e:
                logger.warning(f"Error cargando snapshot {snap_file.name}: {e}")

        if loaded > 0:
            logger.info(f"Cargados {loaded} snapshots desde disco")

    # --- Utilidades ---

    @staticmethod
    def _hash_content(content: str) -> str:
        """Retorna hash MD5 del contenido para verificación de integridad."""
        import hashlib
        return hashlib.md5(content.encode('utf-8')).hexdigest()[:12]

    def verify_integrity(self, snapshot_id: str) -> Tuple[bool, List[str]]:
        """Verifica que los archivos actuales coincidan con el estado post-snapshot.

        Útil para diagnosticar si un archivo fue modificado fuera del
        control del SnapshotManager.

        Returns:
            (intact, modified_files): intact=True si ningún archivo fue
            modificado desde el snapshot, modified_files lista los cambiados.
        """
        snapshot = self._snapshots.get(snapshot_id)
        if not snapshot:
            return (False, [f"Snapshot '{snapshot_id}' no encontrado"])

        modified = []
        for abs_path, entry in snapshot.entries.items():
            if entry.was_new:
                # Archivo nuevo — debería existir ahora
                if not os.path.exists(abs_path):
                    modified.append(f"{abs_path}: archivo nuevo fue eliminado")
            else:
                # Archivo existente — verificar contenido
                if os.path.exists(abs_path):
                    try:
                        with open(abs_path, 'r', encoding='utf-8') as f:
                            current = f.read()
                        current_hash = self._hash_content(current)
                        if current_hash != entry.original_hash:
                            modified.append(f"{abs_path}: contenido modificado")
                    except IOError:
                        modified.append(f"{abs_path}: no se pudo leer")
                else:
                    modified.append(f"{abs_path}: archivo eliminado")

        return (len(modified) == 0, modified)


# ============================================================================
# VALIDACIÓN AUTOCONTENIDA
# ============================================================================
def _run_validation() -> None:
    """Validacion autocontenida — 10 tests para RF3."""
    import sys
    import tempfile

    test_results = []

    # --- Fixture: directorio temporal para tests ---
    test_dir = tempfile.mkdtemp(prefix="apa_snap_test_")

    try:
        # Crear archivos de prueba
        file_a = os.path.join(test_dir, "modulo_a.py")
        file_b = os.path.join(test_dir, "modulo_b.py")
        file_c = os.path.join(test_dir, "modulo_c.py")

        original_a = "# Modulo A v1\ndef funcion_a():\n    return 'original'\n"
        original_b = "# Modulo B v1\ndef funcion_b():\n    return 'original'\n"
        original_c = "# Modulo C v1\ndef funcion_c():\n    return 'original'\n"

        # --- Test 1: Crear snapshot de archivos existentes ---
        try:
            with open(file_a, 'w') as f: f.write(original_a)
            with open(file_b, 'w') as f: f.write(original_b)
            with open(file_c, 'w') as f: f.write(original_c)

            mgr = SnapshotManager(test_dir)
            mgr.clear_all()  # Limpiar snapshots previos

            snap_id = mgr.create_snapshot(
                "refactor_test",
                [file_a, file_b, file_c]
            )
            assert snap_id.startswith("snap_"), f"ID deberia empezar con snap_: {snap_id}"
            info = mgr.get_snapshot(snap_id)
            assert info is not None, "Snapshot deberia existir"
            assert info["file_count"] == 3, f"Deberia tener 3 archivos: {info['file_count']}"
            assert info["committed"] is False, "No deberia estar confirmado"
            test_results.append(("Crear snapshot de 3 archivos", True))
        except AssertionError:
            test_results.append(("Crear snapshot de 3 archivos", False))

        # --- Test 2: Rollback restaura archivos modificados ---
        try:
            with open(file_a, 'w') as f: f.write(original_a)
            with open(file_b, 'w') as f: f.write(original_b)
            with open(file_c, 'w') as f: f.write(original_c)

            mgr = SnapshotManager(test_dir)
            mgr.clear_all()

            snap_id = mgr.create_snapshot("rollback_test", [file_a, file_b, file_c])

            # Modificar los 3 archivos
            with open(file_a, 'w') as f: f.write("# MODIFICADO A\n")
            with open(file_b, 'w') as f: f.write("# MODIFICADO B\n")
            with open(file_c, 'w') as f: f.write("# MODIFICADO C\n")

            # Verificar que están modificados
            with open(file_a, 'r') as f: assert "MODIFICADO" in f.read()
            with open(file_b, 'r') as f: assert "MODIFICADO" in f.read()
            with open(file_c, 'r') as f: assert "MODIFICADO" in f.read()

            # Rollback
            success, errors = mgr.rollback(snap_id)
            assert success, f"Rollback deberia exitoso: {errors}"

            # Verificar restauración
            with open(file_a, 'r') as f: content_a = f.read()
            with open(file_b, 'r') as f: content_b = f.read()
            with open(file_c, 'r') as f: content_c = f.read()
            assert content_a == original_a, f"archivo A no restaurado correctamente"
            assert content_b == original_b, f"archivo B no restaurado correctamente"
            assert content_c == original_c, f"archivo C no restaurado correctamente"
            test_results.append(("Rollback restaura 3 archivos modificados", True))
        except AssertionError:
            test_results.append(("Rollback restaura 3 archivos modificados", False))

        # --- Test 3: CRITERIO RF3 — 3 archivos, 3ro falla, rollback total ---
        try:
            with open(file_a, 'w') as f: f.write(original_a)
            with open(file_b, 'w') as f: f.write(original_b)
            with open(file_c, 'w') as f: f.write(original_c)

            mgr = SnapshotManager(test_dir)
            mgr.clear_all()

            snap_id = mgr.create_snapshot("criterio_rf3", [file_a, file_b, file_c])

            # Modificar archivo 1 — exitoso
            with open(file_a, 'w') as f: f.write("# Refactor exitoso A\n")

            # Modificar archivo 2 — exitoso
            with open(file_b, 'w') as f: f.write("# Refactor exitoso B\n")

            # Modificar archivo 3 — SIMULACIÓN DE FALLO
            # (en la realidad, el 3ro fallaría al escribir o validar)
            with open(file_c, 'w') as f: f.write("# Refactor FALLIDO C\n")

            # Detectamos el fallo y hacemos rollback
            success, errors = mgr.rollback(snap_id)
            assert success, f"Rollback deberia ser exitoso: {errors}"

            # TODOS los archivos deberían estar restaurados al original
            with open(file_a, 'r') as f: assert f.read() == original_a
            with open(file_b, 'r') as f: assert f.read() == original_b
            with open(file_c, 'r') as f: assert f.read() == original_c

            test_results.append(("CRITERIO RF3: 3 archivos modificados, rollback total OK", True))
        except AssertionError:
            test_results.append(("CRITERIO RF3: 3 archivos modificados, rollback total OK", False))

        # --- Test 4: Rollback elimina archivos nuevos ---
        try:
            with open(file_a, 'w') as f: f.write(original_a)

            mgr = SnapshotManager(test_dir)
            mgr.clear_all()

            new_file = os.path.join(test_dir, "nuevo_modulo.py")
            # Asegurar que no existe
            if os.path.exists(new_file):
                os.remove(new_file)

            snap_id = mgr.create_snapshot("new_file_test", [file_a, new_file])

            # Crear el archivo nuevo (simula refactor que crea archivo)
            with open(new_file, 'w') as f: f.write("# Archivo nuevo\n")

            assert os.path.exists(new_file), "Archivo nuevo deberia existir"

            # Rollback
            success, errors = mgr.rollback(snap_id)
            assert success, f"Rollback deberia ser exitoso: {errors}"

            # Archivo nuevo deberia ser eliminado
            assert not os.path.exists(new_file), "Archivo nuevo deberia eliminarse en rollback"

            # Archivo existente deberia restaurarse
            with open(file_a, 'r') as f: assert f.read() == original_a

            test_results.append(("Rollback elimina archivos nuevos (was_new)", True))
        except AssertionError:
            test_results.append(("Rollback elimina archivos nuevos (was_new)", False))

        # --- Test 5: Commit marca snapshot como confirmado ---
        try:
            with open(file_a, 'w') as f: f.write(original_a)

            mgr = SnapshotManager(test_dir)
            mgr.clear_all()

            snap_id = mgr.create_snapshot("commit_test", [file_a])

            # Modificar archivo
            with open(file_a, 'w') as f: f.write("# Modificacion permanente\n")

            # Commit
            result = mgr.commit(snap_id)
            assert result, "Commit deberia ser exitoso"

            info = mgr.get_snapshot(snap_id)
            assert info["committed"] is True, "Snapshot deberia estar confirmado"

            # Rollback de snapshot confirmado deberia fallar
            success, errors = mgr.rollback(snap_id)
            assert not success, "No deberia poder rollback de snapshot confirmado"

            # Archivo deberia quedar modificado (no restaurado)
            with open(file_a, 'r') as f: assert "permanente" in f.read()

            test_results.append(("Commit impide rollback de snapshot confirmado", True))
        except AssertionError:
            test_results.append(("Commit impide rollback de snapshot confirmado", False))

        # --- Test 6: rollback_last restaura el más reciente ---
        try:
            with open(file_a, 'w') as f: f.write(original_a)
            with open(file_b, 'w') as f: f.write(original_b)

            mgr = SnapshotManager(test_dir)
            mgr.clear_all()

            snap1 = mgr.create_snapshot("primero", [file_a])
            snap2 = mgr.create_snapshot("segundo", [file_b])

            # Modificar ambos
            with open(file_a, 'w') as f: f.write("# Mod A\n")
            with open(file_b, 'w') as f: f.write("# Mod B\n")

            # rollback_last deberia restaurar el segundo (más reciente)
            success, errors = mgr.rollback_last()
            assert success, f"rollback_last deberia ser exitoso: {errors}"

            # file_b restaurado, file_a sigue modificado
            with open(file_b, 'r') as f: assert f.read() == original_b
            with open(file_a, 'r') as f: assert "Mod A" in f.read()

            test_results.append(("rollback_last restaura el mas reciente", True))
        except AssertionError:
            test_results.append(("rollback_last restaura el mas reciente", False))

        # --- Test 7: Snapshots anidados ---
        try:
            with open(file_a, 'w') as f: f.write(original_a)
            with open(file_b, 'w') as f: f.write(original_b)

            mgr = SnapshotManager(test_dir)
            mgr.clear_all()

            parent_snap = mgr.create_snapshot("padre", [file_a])

            # Modificar A
            with open(file_a, 'w') as f: f.write("# Mod A nivel 1\n")

            # Crear snapshot hijo
            child_snap = mgr.create_snapshot("hijo", [file_b], parent_id=parent_snap)

            # Modificar B
            with open(file_b, 'w') as f: f.write("# Mod B nivel 2\n")

            # Rollback del hijo
            success, _ = mgr.rollback(child_snap)
            assert success, "Rollback hijo deberia ser exitoso"
            with open(file_b, 'r') as f: assert f.read() == original_b

            # A sigue modificado (no afectado por rollback del hijo)
            with open(file_a, 'r') as f: assert "nivel 1" in f.read()

            test_results.append(("Snapshots anidados (parent/child)", True))
        except AssertionError:
            test_results.append(("Snapshots anidados (parent/child)", False))

        # --- Test 8: Persistencia en disco ---
        try:
            with open(file_a, 'w') as f: f.write(original_a)

            mgr1 = SnapshotManager(test_dir)
            mgr1.clear_all()

            snap_id = mgr1.create_snapshot("persist_test", [file_a])

            # Crear nueva instancia — deberia cargar el snapshot desde disco
            mgr2 = SnapshotManager(test_dir)
            info = mgr2.get_snapshot(snap_id)
            assert info is not None, "Snapshot deberia cargarse desde disco"
            assert info["file_count"] == 1, f"Deberia tener 1 archivo: {info['file_count']}"
            assert info["description"] == "persist_test", "Descripcion deberia persistir"

            mgr2.clear_all()
            test_results.append(("Persistencia en disco (reload)", True))
        except AssertionError:
            test_results.append(("Persistencia en disco (reload)", False))

        # --- Test 9: verify_integrity detecta cambios ---
        try:
            with open(file_a, 'w') as f: f.write(original_a)

            mgr = SnapshotManager(test_dir)
            mgr.clear_all()

            snap_id = mgr.create_snapshot("integrity_test", [file_a])

            # Sin modificar — integridad OK
            intact, modified = mgr.verify_integrity(snap_id)
            assert intact, f"Deberia estar intacto: {modified}"

            # Modificar archivo
            with open(file_a, 'w') as f: f.write("# MODIFICADO\n")

            intact, modified = mgr.verify_integrity(snap_id)
            assert not intact, "Deberia detectar modificacion"
            assert len(modified) > 0, "Deberia reportar archivos modificados"

            mgr.clear_all()
            test_results.append(("verify_integrity detecta cambios externos", True))
        except AssertionError:
            test_results.append(("verify_integrity detecta cambios externos", False))

        # --- Test 10: list_snapshots y prune ---
        try:
            mgr = SnapshotManager(test_dir)
            mgr.clear_all()

            with open(file_a, 'w') as f: f.write(original_a)

            # Crear varios snapshots
            ids = []
            for i in range(5):
                sid = mgr.create_snapshot(f"snap_{i}", [file_a])
                mgr.commit(sid)
                ids.append(sid)

            # Crear uno sin confirmar
            uncommitted_id = mgr.create_snapshot("sin_confirmar", [file_a])

            # list_snapshots sin confirmados
            listed = mgr.list_snapshots(include_committed=False)
            assert len(listed) == 1, f"Deberia listar 1 sin confirmar: {len(listed)}"
            assert listed[0]["snapshot_id"] == uncommitted_id

            # list_snapshots con confirmados
            all_listed = mgr.list_snapshots(include_committed=True)
            assert len(all_listed) == 6, f"Deberia listar 6 total: {len(all_listed)}"

            # Prune: mantener solo 2 confirmados
            pruned = mgr.prune(keep_last_n=2)
            assert pruned == 3, f"Deberia eliminar 3: {pruned}"

            mgr.clear_all()
            test_results.append(("list_snapshots y prune funcionan correctamente", True))
        except AssertionError:
            test_results.append(("list_snapshots y prune funcionan correctamente", False))

    finally:
        # Limpieza del directorio temporal
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir, ignore_errors=True)

    # --- Reporte ---
    passed = sum(1 for _, ok in test_results if ok)
    failed = len(test_results) - passed
    print(f"\n{'='*60}")
    print(f"snapshot_manager.py v1.0 — RF3 Validation")
    print(f"{'='*60}")
    for name, ok in test_results:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}")
    print(f"\nResultado: {passed}/{len(test_results)} PASS, {failed} FAIL")
    print(f"{'='*60}")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    _run_validation()
