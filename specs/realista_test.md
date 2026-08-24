# Proyecto: Servicio de Gestión de Tareas (Task Manager API)

Este proyecto implementa una API REST básica para gestionar tareas, con persistencia en memoria y validaciones.

## Archivo: models/task.py
Define la clase `Task` con los siguientes atributos:
- `id`: entero único.
- `title`: string no vacío.
- `completed`: booleano (por defecto False).

La clase debe tener un método `to_dict()` que retorna un diccionario con los atributos.

Además, define una clase `TaskManager` que gestione una lista de tareas con métodos:
- `add_task(title: str) -> Task`: crea una tarea con id autoincremental y la añade a la lista.
- `get_task(task_id: int) -> Optional[Task]`: retorna la tarea por id o None.
- `list_tasks(completed_only: bool = False) -> List[Task]`: retorna todas las tareas o solo las completadas.
- `mark_completed(task_id: int) -> bool`: marca la tarea como completada. Retorna True si existía, False en caso contrario.

## Archivo: utils/validators.py
Define funciones de validación:
- `validate_title(title: str) -> None`: lanza `ValueError` si el título está vacío o solo contiene espacios.
- `validate_id(task_id: int) -> None`: lanza `ValueError` si el id es negativo.

## Archivo: api.py
Implementa una API FastAPI con los siguientes endpoints:
- `POST /tasks` → recibe JSON `{"title": str}` y retorna la tarea creada (JSON de Task) con código 201.
- `GET /tasks` → retorna lista de todas las tareas (opcional query param `completed_only`).
- `GET /tasks/{task_id}` → retorna una tarea por id o 404 si no existe.
- `PUT /tasks/{task_id}/complete` → marca la tarea como completada, retorna la tarea actualizada o 404.

Utiliza las clases de `models/task.py` y las validaciones de `utils/validators.py`.
La aplicación debe ejecutarse con `uvicorn` si se llama directamente.

## Archivo: tests/test_integration.py
Pruebas con pytest que verifican:
- Crear una tarea válida y recuperarla.
- Intentar crear tarea con título inválido retorna error 400.
- Listar tareas filtradas por completadas.
- Marcar tarea como completada y verificar cambio.

No es necesario implementar todas las pruebas, pero sí al menos tres tests que cubran los casos anteriores.

## Criterios de aceptación globales
- La API debe arrancar sin errores.
- Los tests deben pasar ejecutando `pytest tests/test_integration.py -v`.
- El código debe estar correctamente organizado en los archivos especificados.