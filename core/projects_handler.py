"""
projects_handler.py — Listar proyectos, detalle de proyecto, analizar.

Funcionalidad extraida de app.py.
Endpoints: /projects, /api/project/{id}, /analyze
"""
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


def list_projects(projects: dict, specs_dir: Path) -> dict:
    """Lista todos los proyectos con resumen de estado."""
    result = []
    for project_id, project in projects.items():
        plan_path = specs_dir / project_id / "plan.json"
        plan = None
        if plan_path.exists():
            try:
                plan = json.loads(plan_path.read_text(encoding='utf-8'))
            except Exception:
                pass

        result.append({
            "project_id": project_id,
            "status": project.get("status", "unknown"),
            "created_at": project.get("created_at"),
            "spec_summary": plan.get("spec_summary") if plan else None,
            "tasks_total": len(plan.get("tasks", [])) if plan else 0,
            "tasks_completed": sum(
                1 for t in plan.get("tasks", [])
                if t.get("status") == "completed"
            ) if plan else 0
        })

    result.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return {"projects": result, "total": len(result)}


def get_project_detail(project_id: str, projects: dict, specs_dir: Path) -> dict:
    """Retorna los detalles completos de un proyecto: spec, plan y archivos.

    Retorna dict con datos o dict con "_status" para errores.
    """
    project_data = projects.get(project_id)
    if not project_data:
        return {"error": f"Proyecto {project_id} no encontrado", "_status": 404}

    # Leer spec
    spec_content = ""
    spec_files = [
        specs_dir / f"{project_id}_spec.md",
        specs_dir / project_id / "spec.md",
        specs_dir / project_id / "spec.json",
    ]
    for sf in spec_files:
        if sf.exists():
            try:
                spec_content = sf.read_text(encoding='utf-8')
                break
            except Exception:
                pass

    # Leer plan
    plan_path = specs_dir / project_id / "plan.json"
    plan_tasks = []
    if plan_path.exists():
        try:
            plan = json.loads(plan_path.read_text(encoding='utf-8'))
            plan_tasks = plan.get("tasks", [])
        except Exception:
            pass

    # Listar archivos del proyecto
    files = []
    project_dir = specs_dir / project_id
    if project_dir.exists():
        try:
            for entry in sorted(project_dir.rglob("*")):
                rel_path = entry.relative_to(project_dir)
                if entry.is_file():
                    try:
                        size = entry.stat().st_size
                        if size < 1024:
                            size_str = str(size) + " B"
                        elif size < 1048576:
                            size_str = str(round(size / 1024, 1)) + " KB"
                        else:
                            size_str = str(round(size / 1048576, 1)) + " MB"
                    except OSError:
                        size_str = ""
                    files.append({
                        "name": str(rel_path),
                        "type": "file",
                        "size": size_str,
                    })
                elif entry.is_dir() and entry.name != "__pycache__":
                    files.append({
                        "name": str(rel_path) + "/",
                        "type": "directory",
                        "size": "",
                    })
        except Exception:
            pass

    # Tambien listar el spec file raiz si existe
    spec_file = specs_dir / f"{project_id}_spec.md"
    if spec_file.exists():
        already = any(f["name"] == f"{project_id}_spec.md" for f in files)
        if not already:
            try:
                size = spec_file.stat().st_size
                size_str = str(round(size / 1024, 1)) + " KB" if size > 1024 else str(size) + " B"
            except OSError:
                size_str = ""
            files.insert(0, {
                "name": f"{project_id}_spec.md",
                "type": "file",
                "size": size_str,
            })

    return {
        "project_id": project_id,
        "status": project_data.get("status", "unknown"),
        "created_at": project_data.get("created_at"),
        "spec_content": spec_content,
        "plan_tasks": plan_tasks,
        "tasks_total": len(plan_tasks),
        "tasks_completed": sum(1 for t in plan_tasks if t.get("status") == "completed"),
        "files": files,
    }


def format_size(size_bytes: int) -> str:
    """Formatea un tamano en bytes a cadena legible."""
    if size_bytes < 1024:
        return str(size_bytes) + " B"
    elif size_bytes < 1048576:
        return str(round(size_bytes / 1024, 1)) + " KB"
    else:
        return str(round(size_bytes / 1048576, 1)) + " MB"


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
    print("TESTS AUTONOMOS: projects_handler.py")
    print("=" * 60)

    # Test 1: list_projects vacio
    result = list_projects({}, Path("/tmp/fake_specs"))
    _check("list_projects vacio", result["total"] == 0)
    _check("list_projects lista vacia", len(result["projects"]) == 0)

    # Test 2: list_projects con datos
    projects = {
        "proj_1": {"status": "completed", "created_at": "2025-01-02"},
        "proj_2": {"status": "running", "created_at": "2025-01-03"},
    }
    result = list_projects(projects, Path("/tmp/fake_specs"))
    _check("list_projects 2 proyectos", result["total"] == 2)
    _check("list_projects ordenado por fecha", result["projects"][0]["project_id"] == "proj_2")

    # Test 3: list_projects con plan en disco
    tmp = Path(tempfile.mkdtemp())
    specs = tmp / "specs"
    specs.mkdir()
    proj_dir = specs / "proj_plan"
    proj_dir.mkdir(parents=True, exist_ok=True)
    (proj_dir / "plan.json").write_text(json.dumps({
        "spec_summary": "Resumen del spec",
        "tasks": [
            {"id": "T1", "status": "completed"},
            {"id": "T2", "status": "pending"},
        ]
    }), encoding="utf-8")

    projects2 = {"proj_plan": {"status": "completed", "created_at": "2025-01-01"}}
    result = list_projects(projects2, specs)
    _check("list_projects lee plan", result["projects"][0]["spec_summary"] == "Resumen del spec")
    _check("list_projects cuenta tareas", result["projects"][0]["tasks_total"] == 2)
    _check("list_projects cuenta completadas", result["projects"][0]["tasks_completed"] == 1)

    # Test 4: get_project_detail
    (proj_dir / "spec.md").write_text("# Spec de prueba", encoding="utf-8")
    result = get_project_detail("proj_plan", projects2, specs)
    _check("detail tiene spec_content", result.get("spec_content") == "# Spec de prueba")
    _check("detail tiene plan_tasks", len(result.get("plan_tasks", [])) == 2)

    # Test 5: get_project_detail no existe
    result = get_project_detail("no_existe", {}, specs)
    _check("detail 404 si no existe", result.get("_status") == 404)

    # Test 6: format_size
    _check("format_size bytes", format_size(500) == "500 B")
    _check("format_size KB", format_size(2048) == "2.0 KB")
    _check("format_size MB", format_size(1572864) == "1.5 MB")

    shutil.rmtree(tmp, ignore_errors=True)

    print("-" * 60)
    total = passed + failed
    print(f"Resultado: {passed}/{total} pasaron")
    print("=" * 60)
    sys.exit(0 if failed == 0 else 1)
