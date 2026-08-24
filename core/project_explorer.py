# project_explorer.py - Navegacion y exploracion de proyectos.
#
# Funcionalidad extraida de app.py (CHAT-R.7).
# Contiene logica de browse_directory y explore_project sin dependencia de FastAPI.
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# Extensiones de codigo analizables por LLM
CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs", ".rb",
    ".php", ".c", ".cpp", ".h", ".cs", ".swift", ".kt", ".sh", ".sql",
    ".vue", ".svelte", ".html", ".css", ".scss",
    ".prg", ".fxp", ".dbf", ".dbc", ".mnt", ".mnu", ".pjx", ".pjt",
    ".txt", ".ini", ".cfg", ".json", ".xml", ".yaml", ".yml", ".toml",
    ".md", ".rst", ".bat", ".cmd",
}

# Extensiones de datos/entorno que siempre se leen
KEY_DATA_EXTENSIONS = {
    ".txt", ".ini", ".cfg", ".env", ".json", ".xml", ".yaml", ".yml",
    ".dbf", ".dbc", ".md",
}


def browse_directory(dir_path_str: str) -> dict:
    """Lista el contenido de un directorio para navegacion.

    Retorna dict con:
        - success: bool
        - path: str
        - entries: list (o error)
    """
    if not dir_path_str:
        dir_path_str = str(Path.cwd())

    path_obj = Path(dir_path_str)

    if not path_obj.is_dir():
        return {
            "success": False,
            "error": f"La ruta no es un directorio: {dir_path_str}",
            "path": dir_path_str,
            "entries": []
        }

    try:
        entries = []
        for entry in sorted(path_obj.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
            entry_info = {
                "name": entry.name,
                "path": str(entry),
                "is_dir": entry.is_dir(),
            }
            if entry.is_dir():
                try:
                    child_count = len(list(entry.iterdir()))
                    entry_info["child_count"] = child_count
                except Exception:
                    entry_info["child_count"] = 0
            else:
                try:
                    entry_info["size"] = entry.stat().st_size
                except Exception:
                    entry_info["size"] = 0
            entries.append(entry_info)

        # Permitir navegar al directorio padre
        parent = path_obj.parent
        if parent != path_obj:
            entries.insert(0, {
                "name": "..",
                "path": str(parent),
                "is_dir": True,
                "is_parent": True,
            })

        return {
            "success": True,
            "path": str(path_obj),
            "entries": entries,
        }
    except Exception as e:
        logger.error("Error navegando directorio: %s", e)
        return {"success": False, "error": str(e), "path": dir_path_str, "entries": []}


def detect_project_type(file_tree: list, key_files: dict, all_extensions: set) -> str:
    """Detecta el tipo de proyecto basado en archivos clave y extensiones."""
    if any(k in key_files for k in ("requirements", "config")):
        return "python"
    elif "package_json" in key_files:
        return "javascript/node"
    elif ".prg" in all_extensions or ".pjx" in all_extensions or ".pjt" in all_extensions:
        return "visual_foxpro"
    elif ".dbf" in all_extensions or ".dbc" in all_extensions:
        return "foxpro/database"
    elif key_files.get("config") and file_tree and "cargo" in file_tree[0].get("path", ""):
        return "rust"
    return "desconocido"


def scan_project_structure(path_obj: Path) -> dict:
    """Escanea la estructura de un proyecto.

    Retorna dict con:
        - file_tree: lista de archivos/directorios
        - script_files: lista de Path a scripts analizables (max 30)
        - key_files: dict de archivos clave encontrados
        - project_type: str tipo detectado
        - all_extensions: set de extensiones encontradas
    """
    file_tree = []
    script_files = []
    key_files = {}
    all_extensions = set()

    for entry in sorted(path_obj.rglob("*")):
        rel = entry.relative_to(path_obj)
        depth = len(rel.parts)
        if depth > 3:
            continue

        if entry.is_file():
            rel_str = str(rel).replace("\\", "/")
            size = entry.stat().st_size
            file_tree.append({"path": rel_str, "size": size, "is_dir": False})

            ext = entry.suffix.lower()
            if ext:
                all_extensions.add(ext)

            name_lower = entry.name.lower()
            if name_lower in ("readme.md", "readme", "readme.txt"):
                key_files["readme"] = rel_str
            elif name_lower == "package.json":
                key_files["package_json"] = rel_str
            elif name_lower == "requirements.txt":
                key_files["requirements"] = rel_str
            elif name_lower in ("setup.py", "pyproject.toml", "cargo.toml", "go.mod", "pom.xml"):
                key_files["config"] = rel_str

            if ext in CODE_EXTENSIONS and size < 50000 and len(script_files) < 30:
                script_files.append(entry)
            if ext in KEY_DATA_EXTENSIONS and name_lower not in key_files.values():
                key_files[f"data_{name_lower}"] = rel_str

        elif entry.is_dir():
            if depth <= 2:
                file_tree.append({"path": str(rel).replace("\\", "/") + "/", "size": 0, "is_dir": True})

    file_tree = file_tree[:100]
    project_type = detect_project_type(file_tree, key_files, all_extensions)

    return {
        "file_tree": file_tree,
        "script_files": script_files,
        "key_files": key_files,
        "project_type": project_type,
        "all_extensions": all_extensions,
    }


def read_key_file_contents(path_obj: Path, key_files: dict) -> dict:
    """Lee el contenido de archivos clave del proyecto.

    Retorna dict {key_name: {path, content, size, truncated}}
    """
    key_file_contents = {}
    for key_name, rel_path in key_files.items():
        if key_name.startswith("data_") or key_name in ("readme",):
            try:
                full_path = path_obj / rel_path
                if full_path.exists() and full_path.is_file():
                    raw = full_path.read_text(encoding='utf-8', errors='replace')
                    limit = 4000 if key_name.startswith("data_") else 2000
                    key_file_contents[key_name] = {
                        "path": rel_path,
                        "content": raw[:limit],
                        "size": full_path.stat().st_size,
                        "truncated": len(raw) > limit,
                    }
            except Exception as e:
                key_file_contents[key_name] = {"path": rel_path, "content": f"(Error leyendo: {str(e)[:100]})", "size": 0}
    return key_file_contents


# =====================================================================
# TESTS AUTONOMOS
# =====================================================================
if __name__ == "__main__":
    import sys, tempfile, shutil
    passed = 0
    failed = 0

    def _check(name, condition):
        global passed, failed
        if condition:
            print(f"  [PASS] {name}")
            passed += 1
        else:
            print(f"  [FAIL] {name}")
            failed += 1

    print("=" * 60)
    print("TESTS AUTONOMOS: project_explorer.py")
    print("=" * 60)

    # Test 1: browse_directory
    tmp = Path(tempfile.mkdtemp())
    try:
        (tmp / "archivo.txt").write_text("hola", encoding="utf-8")
        (tmp / "subdir").mkdir()
        (tmp / "subdir" / "otro.py").write_text("print(1)", encoding="utf-8")

        result = browse_directory(str(tmp))
        _check("browse success", result["success"] is True)
        _check("browse tiene entries", len(result["entries"]) >= 2)
        _check("browse tiene ..", result["entries"][0]["name"] == "..")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # Test 2: browse_directory ruta invalida
    result = browse_directory("/tmp/no_existe_xyz")
    _check("browse ruta inexistente", result["success"] is False)

    # Test 3: browse_directory no es directorio
    tmp3 = Path(tempfile.mkdtemp())
    archivo = tmp3 / "fichero.txt"
    archivo.write_text("no soy dir", encoding="utf-8")
    result = browse_directory(str(archivo))
    _check("browse no es dir", result["success"] is False)
    shutil.rmtree(tmp3, ignore_errors=True)

    # Test 4: detect_project_type
    _check("detect python (requirements)", detect_project_type([], {"requirements": "r.txt"}, set()) == "python")
    _check("detect js (package_json)", detect_project_type([], {"package_json": "p.json"}, set()) == "javascript/node")
    _check("detect desconocido", detect_project_type([], {}, set()) == "desconocido")

    # Test 5: scan_project_structure
    tmp5 = Path(tempfile.mkdtemp())
    try:
        (tmp5 / "main.py").write_text("print('hola')", encoding="utf-8")
        (tmp5 / "utils.py").write_text("def foo(): pass", encoding="utf-8")
        (tmp5 / "requirements.txt").write_text("fastapi\nuvicorn", encoding="utf-8")
        sub = tmp5 / "src"
        sub.mkdir()
        (sub / "mod.js").write_text("console.log(1)", encoding="utf-8")

        result = scan_project_structure(tmp5)
        _check("scan project_type python", result["project_type"] == "python")
        _check("scan tiene requirements", "requirements" in result["key_files"])
        _check("scan script_files", len(result["script_files"]) >= 3)
        _check("scan file_tree tiene archivos", any(not f["is_dir"] for f in result["file_tree"]))
    finally:
        shutil.rmtree(tmp5, ignore_errors=True)

    # Test 6: read_key_file_contents
    tmp6 = Path(tempfile.mkdtemp())
    try:
        (tmp6 / "README.md").write_text("A" * 5000, encoding="utf-8")
        (tmp6 / "config.json").write_text('{"key": "val"}', encoding="utf-8")
        key_files = {
            "readme": "README.md",
            "data_config.json": "config.json",
        }
        result = read_key_file_contents(tmp6, key_files)
        _check("read_key tiene readme", "readme" in result)
        _check("read_key readme truncado", result["readme"]["truncated"] is True)
        _check("read_key tiene data", "data_config.json" in result)
        _check("read_key data no truncado", result["data_config.json"]["truncated"] is False)
    finally:
        shutil.rmtree(tmp6, ignore_errors=True)

    # Test 7: browse con directorio vacio
    tmp7 = Path(tempfile.mkdtemp())
    try:
        result = browse_directory(str(tmp7))
        _check("browse vacio tiene solo ..", len(result["entries"]) == 1)
    finally:
        shutil.rmtree(tmp7, ignore_errors=True)

    print("-" * 60)
    total = passed + failed
    print(f"Resultado: {passed}/{total} pasaron")
    print("=" * 60)
    sys.exit(0 if failed == 0 else 1)
