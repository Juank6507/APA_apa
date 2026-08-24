# Spec: Interfaz web del APA

Objetivo: crear una aplicación web local con FastAPI que permita
al usuario pegar una spec en markdown, lanzar el orquestador APA
y ver el progreso de cada tarea en tiempo real.

Inputs disponibles:
- apa/core/orchestrator.py con clase Orchestrator
- El método run(spec_path, on_progress) recibe la ruta a un
  archivo .md y un callback que recibe eventos dict con campo
  "type" que puede ser: health_check, parsing_spec, spec_parsed,
  generating_plan, plan_generated, task_started, task_completed,
  task_failed
- FastAPI y uvicorn disponibles para instalar

Output esperado:
- Servidor web en localhost:8080
- GET / → página HTML con textarea para pegar spec y botón lanzar
- POST /run → recibe spec como texto, la guarda en archivo
  temporal, lanza orquestador en background, retorna project_id
- GET /status/{project_id} → retorna plan.json actual como JSON
- GET /stream/{project_id} → SSE stream con eventos en tiempo real
- La página muestra lista de tareas con estado actualizado
- Al finalizar muestra botón para descargar cada archivo generado

Criterio de éxito:
- python interface/app.py arranca servidor en localhost:8080
- Se abre en navegador sin errores
- Al pegar la spec de ejemplo y lanzar aparecen las tareas
- El estado de cada tarea se actualiza sin recargar la página
- Los archivos generados se pueden descargar