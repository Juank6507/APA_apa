import sys
import os

# Asegurar que la carpeta 'apa' está en el path para los imports
# Asumiendo que ejecutas esto desde la raíz del proyecto: C:\Python\Proyectos\APA
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'apa'))

from mcp.server import NASConnector

def test_operations():
    nas = NASConnector()

    # Código corregido para utils/operations.py
    # Usa comillas simples internamente para evitar cualquier conflicto
    code = '''
def validate_number(valor):
    if not isinstance(valor, (int, float)):
        raise ValueError(f'No es un numero: {valor}')

def sumar(a, b):
    validate_number(a)
    validate_number(b)
    return a + b

def restar(a, b):
    validate_number(a)
    validate_number(b)
    return a - b

def multiplicar(a, b):
    validate_number(a)
    validate_number(b)
    return a * b

def dividir(a, b):
    validate_number(a)
    validate_number(b)
    if b == 0:
        raise ValueError('No se puede dividir por cero')
    return a / b

if __name__ == '__main__':
    assert sumar(3, 2) == 5
    assert restar(5, 3) == 2
    assert multiplicar(4, 3) == 12
    assert dividir(10, 2) == 5.0
    try:
        dividir(1, 0)
        assert False, "Debería lanzar ValueError"
    except ValueError:
        pass
    print('CRITERIO OK')
'''

    print(f"Ejecutando código en el NAS...")
    result = nas.execute_code(code)
    
    print('--- RESULTADO ---')
    print('stdout:', repr(result['stdout']))
    print('stderr:', repr(result['stderr']))
    print('success:', result['success'])
    
    # Verificación explícita
    if 'CRITERIO OK' in result.get('stdout', ''):
        print("✅ PRUEBA SUPERADA: El código cumple el criterio.")
    else:
        print("❌ PRUEBA FALLIDA: No se detectó 'CRITERIO OK' en la salida.")

if __name__ == "__main__":
    test_operations()
    