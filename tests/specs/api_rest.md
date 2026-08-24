<!-- apa/tests/specs/api_rest.md -->
# API REST Simple con FastAPI

Objetivo: Crear una API REST con un endpoint GET /saludo/{nombre} que retorne un JSON {"mensaje": "Hola, <nombre>"}.

Inputs:
- nombre: string (parte de la URL)

Output esperado: Respuesta JSON con campo "mensaje".

Criterio de éxito: El servidor se levanta en http://127.0.0.1:8000 y una petición HTTP al endpoint verifica la respuesta esperada.