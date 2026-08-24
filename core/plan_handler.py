# plan_handler.py - Endpoint para obtener el plan del proyecto activo.
#
# Funcionalidad extraida de app.py (UI4: PLAN ENDPOINT).
import json
import os
import glob as glob_mod
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def get_plan(load_project_state_fn=None, project_root: str = None) -> dict:
    """Retorna el contenido del plan del proyecto activo.

    Args:
        load_project_state_fn: funcion que recibe un nombre y retorna dict.
        project_root: ruta raiz del proyecto (opcional, para tests).
    """
    if load_project_state_fn is None:
        return {"content": "No hay proyecto activo.", "project": ""}

    last = load_project_state_fn("app")
    project_path = last.get("path", "") if last else ""
    if not project_path:
        return {"content": "No hay proyecto activo.", "project": ""}

    # Buscar PLAN_*.md files
    plan_files = glob_mod.glob(os.path.join(project_path, "**", "PLAN_*.md"), recursive=True)
    plan_files += glob_mod.glob(os.path.join(project_path, "**", "docs", "PLAN_*.md"), recursive=True)
    if not plan_files:
        plan_files = glob_mod.glob(os.path.join(project_path, "docs", "PLAN_*.md"))

    if plan_files:
        plan_files = [Path(p) for p in plan_files]
        plan_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        try:
            with open(plan_files[0], "r", encoding="utf-8") as f:
                return {"content": f.read(), "project": os.path.basename(project_path)}
        except Exception:
            pass

    return {"content": "Plan no encontrado.", "project": os.path.basename(project_path)}


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
    print("TESTS AUTONOMOS: plan_handler.py")
    print("=" * 60)

    # Test 1: sin load_project_state_fn
    result = get_plan()
    _check("sin state fn: no proyecto", result["content"] == "No hay proyecto activo.")

    # Test 2: con proyecto sin plan
    result = get_plan(lambda name: {"path": "/tmp/no_existe_dir_xxx"})
    _check("proyecto sin path: plan no encontrado", "no encontrado" in result["content"])

    # Test 3: con proyecto y plan en disco
    tmp = Path(tempfile.mkdtemp())
    try:
        docs = tmp / "docs"
        docs.mkdir()
        plan_file = docs / "PLAN_mejoras_v2.md"
        plan_file.write_text("# Plan de Mejoras\n\nEste es el plan de pruebas.", encoding="utf-8")

        result = get_plan(lambda name: {"path": str(tmp)})
        _check("plan encontrado", "Plan de Mejoras" in result["content"])
        _check("project name", result["project"] == tmp.name)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # Test 4: estado vacio
    result = get_plan(lambda name: None)
    _check("estado None: no proyecto", result["content"] == "No hay proyecto activo.")

    # Test 5: path vacio
    result = get_plan(lambda name: {"path": ""})
    _check("path vacio: no proyecto", result["content"] == "No hay proyecto activo.")

    print("-" * 60)
    total = passed + failed
    print(f"Resultado: {passed}/{total} pasaron")
    print("=" * 60)
    sys.exit(0 if failed == 0 else 1)
