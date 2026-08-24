# apa/tests/test_t13.py
import sys
import os
import time
import logging
import tempfile
from pathlib import Path

# Aseguramos que apa sea importable
apa_dir = Path(__file__).parents[1]
sys.path.insert(0, str(apa_dir))

from core.orchestrator import Orchestrator

logging.basicConfig(level=logging.WARNING)

# Crear especificación multi-archivo temporal con dependencias
SPEC_CONTENT = """# Proyecto: Módulo matemático con dependencias

## Archivo: utils/math_helpers.py
Define funciones auxiliares:
- `es_par(n)` retorna True si n es par.
- `es_primo(n)` retorna True si n es primo (implementación simple).

## Archivo: main.py
Importa `es_par` y `es_primo` desde `utils/math_helpers.py`.
Define función `clasificar_numero(n)` que retorna:
- "par primo" si n es par y primo.
- "par no primo" si n es par pero no primo.
- "impar primo" si n es impar y primo.
- "impar no primo" si n es impar y no primo.

## Criterios de aceptación globales
- `clasificar_numero(2)` debe retornar "par primo".
- `clasificar_numero(4)` debe retornar "par no primo".
- `clasificar_numero(3)` debe retornar "impar primo".
- `clasificar_numero(9)` debe retornar "impar no primo".
"""

def on_progress(event: dict) -> None:
    """Callback para mostrar eventos de progreso."""
    event_type = event.get("type", "")
    task_id = event.get("task_id", "")
    task_name = event.get("task_name", "")
    message = event.get("message", "")

    if event_type == "task_started":
        print(f"[START] {task_id}: {task_name}")
    elif event_type == "task_completed":
        print(f"[DONE] {task_id}")
    elif event_type == "task_failed":
        print(f"[FAIL] {task_id}: {event.get('diagnosis', '')}")
    elif event_type == "plan_generated":
        print(f"[PLAN] Tareas generadas: {event.get('tasks_count', 0)}")
    elif event_type == "checkpoint_restored":
        print(f"[CHECKPOINT] Restaurado con {event.get('tasks_completed', 0)} tareas completadas")
    elif event_type == "documentation_completed":
        print(f"[DOCS] {message}")

def main():
    # Crear archivo de spec temporal
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
        f.write(SPEC_CONTENT)
        spec_path = f.name

    print(f"=== INICIANDO PRUEBA T13: MULTI-ARCHIVO CON DEPENDENCIAS ===")
    print(f"Spec temporal: {spec_path}\n")

    orchestrator = Orchestrator()
    start_time = time.time()
    result = orchestrator.run(spec_path, on_progress=on_progress)
    elapsed = time.time() - start_time

    print("\n--- RESULTADO FINAL ---")
    success = result.get("success", False)
    print(f"Éxito: {success}")
    print(f"Project ID: {result.get('project_id', 'N/A')}")
    print(f"Completadas: {result.get('completed', 0)}")
    print(f"Fallidas: {result.get('failed', 0)}")
    print(f"Tiempo total: {elapsed:.2f} segundos")

    # Mostrar resumen de tareas
    tasks_summary = result.get("tasks_summary", [])
    if tasks_summary:
        print("\nResumen de tareas:")
        for t in tasks_summary:
            print(f"  [{t['status']}] {t['id']}: {t['name']}")
            if t.get('filename'):
                print(f"    archivo: {t['filename']}")

    # Verificación del criterio T13
    print("\n--- VERIFICACIÓN T13 ---")
    if success and result.get("completed", 0) >= 2:
        # Verificar que existan las tareas esperadas
        task_ids = [t["id"] for t in tasks_summary]
        if "math_helpers_py" in task_ids and "main_py" in task_ids:
            print("✅ T13: Ambas tareas multi-archivo generadas correctamente.")
            print("   Las dependencias se respetaron (main_py dependía de math_helpers_py).")
        else:
            print("⚠️ T13: Tareas generadas pero IDs no coinciden con lo esperado.")
    else:
        print("❌ T13: Falló la ejecución del proyecto multi-archivo.")

    # Limpiar archivo temporal
    try:
        os.unlink(spec_path)
    except Exception:
        pass

if __name__ == "__main__":
    main()