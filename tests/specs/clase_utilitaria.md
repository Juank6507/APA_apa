<!-- apa/tests/specs/clase_utilitaria.md -->
# Clase de validación

Objetivo: Crear una clase Validadores con métodos estáticos:
- es_email_valido(email) -> bool
- es_telefono_valido(telefono) -> bool

Inputs:
- email: string
- telefono: string (formato español: 9 dígitos, puede empezar por 6,7,8,9)

Output esperado: Boolean indicando si el formato es válido.

Criterio de éxito: El bloque __main__ ejecuta asserts con casos válidos e inválidos e imprime "CRITERIO OK" si todos pasan.