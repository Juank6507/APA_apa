<!-- apa/tests/specs/modulo_config.md -->
# Módulo de configuración con variables de entorno

Objetivo: Crear una clase Settings que cargue HOST, PORT y DEBUG desde variables de entorno o .env.

Inputs:
- Variables de entorno: HOST, PORT, DEBUG

Output esperado: Una instancia de Settings con atributos host, port, debug.

Criterio de éxito: Establecer variables de entorno temporalmente, instanciar Settings y verificar que los valores coinciden.