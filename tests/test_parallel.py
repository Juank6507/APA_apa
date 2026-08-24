# apa/tests/test_parallel.py
import sys
import os
from pathlib import Path

# --- SOLUCIÓN ROBUSTA DE IMPORTACIÓN ---
# Añadimos la carpeta 'apa' al sys.path para que los módulos internos
# puedan importarse directamente sin el prefijo 'apa.'
apa_dir = Path(__file__).parents[1]  # Esto apunta a la carpeta 'apa'
sys.path.insert(0, str(apa_dir))

# Ahora importamos los módulos directamente (sin 'apa.')
import time
import logging
from core.orchestrator import Orchestrator

# --- Resto del script sin cambios ---
logging.basicConfig(level=logging.WARNING)

def on_progress(event: dict) -> None:
    event_type = event.get("type", "")
    task_id = event.get("task_id", "")
    message = event.get("message", "")
    
    if event_type == "health_check":
        providers = event.get("providers", [])
        print(f"[health_check] proveedores: {providers}")
    elif event_type == "spec_parsed":
        print(f"[spec_parsed] objetivo: {event.get('objetivo', '')}")
    elif event_type == "plan_generated":
        print(f"[plan_generated] tareas: {event.get('tasks_count', 0)}")
    elif event_type == "task_started":
        print(f"[task_started] {task_id}: {event.get('task_name', '')}")
    elif event_type == "task_completed":
        print(f"[task_completed] {task_id} passed={event.get('criterion_passed', False)} attempts={event.get('attempts_used', 0)}")
    elif event_type == "task_failed":
        print(f"[task_failed] {task_id}: {event.get('diagnosis', '')}")
    elif event_type == "documentation_started":
        print(f"[documentation_started] {message}")
    elif event_type == "documentation_completed":
        print(f"[documentation_completed] {message}")
    elif event_type == "checkpoint_restored":
        print(f"[checkpoint_restored] proyecto {event.get('project_id', '')} reanudado con {event.get('tasks_completed', 0)} tareas completadas")
    else:
        print(f"[{event_type}] {task_id} {message}".strip())

def main():
    # Ruta a la spec de prueba (se encuentra en apa/specs/parallel_test.md)
    spec_path = apa_dir / "specs" / "parallel_test.md"
    print(f"=== INICIANDO PRUEBA DE PARALELISMO ===")
    print(f"Spec: {spec_path}\n")
    
    orchestrator = Orchestrator()
    start_time = time.time()
    result = orchestrator.run(str(spec_path), on_progress=on_progress)
    elapsed = time.time() - start_time
    
    print("\n--- RESULTADO FINAL ---")
    if result.get("success"):
        print("ÉXITO: proyecto completado")
    else:
        print(f"FALLO: {result.get('error', 'Error desconocido')}")
    
    print(f"Project ID: {result.get('project_id', 'N/A')}")
    print(f"Completadas: {result.get('completed', 0)}")
    print(f"Fallidas: {result.get('failed', 0)}")
    print(f"Tiempo total: {elapsed:.2f} segundos")
    
    tasks_summary = result.get("tasks_summary", [])
    if tasks_summary:
        print("\nResumen de tareas:")
        for t in tasks_summary:
            print(f"  [{t['status']}] {t['id']}: {t['name']}")
            print(f"    criterion_passed={t['criterion_passed']} attempts={t['attempts_used']}")
            if t.get('filename'):
                print(f"    archivo: {t['filename']}")
    
    if result.get("completed", 0) >= 3:
        print("\n✅ T6: Al menos 3 tareas independientes completadas exitosamente.")
        print(f"   Tiempo total: {elapsed:.2f}s (debe ser significativamente menor que la suma de tiempos individuales)")
    else:
        print("\n❌ T6: No se completaron 3 tareas independientes. Revisar salida.")

if __name__ == "__main__":
    main()