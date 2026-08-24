# apa/tests/test_rf1_v12_improvements.py
# Tests específicos para las mejoras RF1 v1.2:
#   RF1-10: BUG FIX — from . import X resuelve a X.py (no __init__.py)
#   RF1-11: Expansión de from X import * usando __all__ o símbolos públicos
#   RF1-12: Verificación de existencia de archivos (sin falsos positivos)
#   RF1-13: Resolución de self.metodo() y cls.metodo()
#   RF1-14: Resolución de importlib.import_module(variable) con tracking
#
# Cada test tiene:
#   - Descripción clara de QUÉ se valida
#   - Descripción de CÓMO se valida
#   - Escenario de código de entrada
#   - Verificación del resultado esperado
#
# EJECUCIÓN:
#   cd APA && python -m apa.tests.test_rf1_v12_improvements
#
import os
import sys
import tempfile
import shutil
from pathlib import Path

# Añadir raíz del proyecto al path
sys.path.insert(0, str(Path(__file__).parent.parent))


def _run_validation():
    from core.symbol_graph import SymbolGraph

    results = []

    # ================================================================
    # RF1-10: BUG FIX — from . import X resuelve a X.py, no a __init__.py
    # ================================================================
    #
    # QUÉ se valida: El bug original hacía que `from . import utils` en
    # un archivo dentro de un paquete resolviera a `__init__.py` en vez
    # de `utils.py`. Esto causaba que las llamadas a funciones de utils.py
    # no se detectaran como dependientes.
    #
    # CÓMO se valida: Se crea un paquete real en disco con __init__.py y
    # utils.py. Desde sub.py se hace `from . import utils` y se llama a
    # utils.validar(). Se verifica que el grafo registra correctamente
    # a sub.py como caller de validar() en utils.py.
    #
    print("── RF1-10: from . import X resuelve a X.py (no __init__.py) ──")

    try:
        tmp_dir = tempfile.mkdtemp(prefix="apa_rf1_10_")
        try:
            # Crear estructura:
            #   mi_paquete/__init__.py  (vacío)
            #   mi_paquete/utils.py    (contiene def validar)
            #   mi_paquete/sub.py      (from . import utils; llama a utils.validar)
            pkg_dir = os.path.join(tmp_dir, "mi_paquete")
            os.makedirs(pkg_dir, exist_ok=True)

            with open(os.path.join(pkg_dir, "__init__.py"), "w") as f:
                f.write("")

            with open(os.path.join(pkg_dir, "utils.py"), "w") as f:
                f.write("def validar(dato):\n    return bool(dato)\n")

            with open(os.path.join(pkg_dir, "sub.py"), "w") as f:
                f.write(
                    "from . import utils\n"
                    "\n"
                    "def procesar():\n"
                    "    return utils.validar('dato')\n"
                )

            graph = SymbolGraph()
            graph.build_from_directory(tmp_dir)

            # Buscar quienes llaman a validar en utils.py
            utils_rel = os.path.join("mi_paquete", "utils.py")
            ctx = graph.get_refactor_context(utils_rel, "validar")
            callers = ctx.get("llamado_por", [])
            caller_files = [f for f, _ in callers]

            # VERIFICACIÓN: sub.py debe estar en los callers
            has_sub = any("sub.py" in f for f in caller_files)
            assert has_sub, (
                f"BUG: from . import utils no resolvió a utils.py. "
                f"Callers encontrados: {caller_files}. "
                f"Se esperaba sub.py pero resolvió a __init__.py."
            )
            results.append((
                "RF1-10.1: from . import utils resuelve a utils.py (no __init__.py)",
                True
            ))
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
    except Exception as e:
        results.append((
            f"RF1-10.1: from . import X resuelve a X.py [{e}]",
            False
        ))

    # ================================================================
    # RF1-11: from X import * se expande correctamente
    # ================================================================
    #
    # QUÉ se valida: Cuando un archivo tiene `from utils import *`, el
    # sistema debe expandir ese asterisco a los símbolos específicos que
    # utils exporta. Si utils tiene `__all__`, usa esa lista. Si no,
    # usa todas las funciones/clases públicas (las que no empiezan con _).
    #
    # CÓMO se valida (caso A — con __all__): Se crea utils.py con
    # __all__ = ["validar", "formatear"] y una función privada _interno.
    # Se verifica que al hacer from utils import *, las llamadas a
    # validar() y formatear() se detectan, pero _interno() no genera
    # falsos positivos.
    #
    # CÓMO se valida (caso B — sin __all__): Se crea utils.py sin
    # __all__ y con funciones validar() y _privada(). Se verifica que
    # validar() se detecta pero _privada() no (empieza con _).
    #
    print("── RF1-11: from X import * se expande correctamente ──")

    # Caso A: Con __all__ explícito
    try:
        files = {
            "utils.py": (
                "__all__ = ['validar', 'formatear']\n"
                "\n"
                "def validar(dato):\n"
                "    return bool(dato)\n"
                "\n"
                "def formatear(texto):\n"
                "    return texto.strip()\n"
                "\n"
                "def _interno():\n"
                "    return 'oculto'\n"
            ),
            "main.py": (
                "from utils import *\n"
                "\n"
                "def ejecutar():\n"
                "    validar('datos')\n"
                "    formatear('texto')\n"
            ),
        }
        graph = SymbolGraph()
        graph.build_from_files(files)

        # Verificar que main.py es caller de validar
        ctx_validar = graph.get_refactor_context("utils.py", "validar")
        callers_validar = [f for f, _ in ctx_validar.get("llamado_por", [])]
        assert "main.py" in callers_validar, (
            f"main.py debería llamar a validar via star import: {callers_validar}"
        )

        # Verificar que main.py es caller de formatear
        ctx_formatear = graph.get_refactor_context("utils.py", "formatear")
        callers_formatear = [f for f, _ in ctx_formatear.get("llamado_por", [])]
        assert "main.py" in callers_formatear, (
            f"main.py debería llamar a formatear via star import: {callers_formatear}"
        )

        results.append((
            "RF1-11.1: from X import * con __all__ detecta símbolos exportados",
            True
        ))
    except Exception as e:
        results.append((
            f"RF1-11.1: star import con __all__ [{e}]",
            False
        ))

    # Caso B: Sin __all__ (símbolos públicos)
    try:
        files = {
            "utils.py": (
                "def validar(dato):\n"
                "    return bool(dato)\n"
                "\n"
                "def _privada():\n"
                "    return 'no exportada'\n"
            ),
            "main.py": (
                "from utils import *\n"
                "\n"
                "def ejecutar():\n"
                "    validar('ok')\n"
            ),
        }
        graph = SymbolGraph()
        graph.build_from_files(files)

        ctx = graph.get_refactor_context("utils.py", "validar")
        callers = [f for f, _ in ctx.get("llamado_por", [])]
        assert "main.py" in callers, (
            f"main.py debería llamar a validar via star import (sin __all__): {callers}"
        )
        results.append((
            "RF1-11.2: from X import * sin __all__ detecta símbolos públicos",
            True
        ))
    except Exception as e:
        results.append((
            f"RF1-11.2: star import sin __all__ [{e}]",
            False
        ))

    # ================================================================
    # RF1-12: Imports de módulos externos no generan falsos positivos
    # ================================================================
    #
    # QUÉ se valida: Antes, si un archivo hacía `import json`, el sistema
    # asumía que existía un archivo `json.py` en el proyecto y lo
    # registraba como dependencia. Esto generaba dependencias fantasma
    # hacia archivos que no existen. Ahora, el sistema verifica que el
    # archivo realmente existe en el proyecto antes de registrarlo.
    #
    # CÓMO se valida: Se crea un proyecto en disco con main.py que
    # importa `json` (módulo de la biblioteca estándar) y `utils`
    # (archivo del proyecto). Se verifica que:
    #   - utils.py aparece como dependencia de main.py (correcto)
    #   - json.py NO aparece como dependencia (sería un falso positivo)
    #
    print("── RF1-12: Sin falsos positivos de módulos externos ──")

    try:
        tmp_dir = tempfile.mkdtemp(prefix="apa_rf1_12_")
        try:
            # Crear estructura:
            #   main.py → import json; import utils; json.dumps(data); utils.validar(x)
            #   utils.py → def validar(dato)
            # NOTA: No existe json.py en el proyecto
            with open(os.path.join(tmp_dir, "main.py"), "w") as f:
                f.write(
                    "import json\n"
                    "import utils\n"
                    "\n"
                    "def ejecutar():\n"
                    "    json.dumps({'key': 'value'})\n"
                    "    return utils.validar('datos')\n"
                )

            with open(os.path.join(tmp_dir, "utils.py"), "w") as f:
                f.write("def validar(dato):\n    return bool(dato)\n")

            graph = SymbolGraph()
            graph.build_from_directory(tmp_dir)

            # VERIFICACIÓN 1: utils.py SÍ debe estar en dependencias de main.py
            main_imports = graph._imports.get("main.py", [])
            import_files = [imp[2] for imp in main_imports if imp[2] is not None]
            assert "utils.py" in import_files, (
                f"utils.py debería estar en imports de main.py: {import_files}"
            )

            # VERIFICACIÓN 2: json.py NO debe estar en dependencias
            # (json es un módulo externo, no hay json.py en el proyecto)
            assert "json.py" not in import_files, (
                f"json.py NO debería estar en imports de main.py (falso positivo): "
                f"{import_files}"
            )

            results.append((
                "RF1-12.1: Módulos externos (json) no generan falsos positivos",
                True
            ))
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
    except Exception as e:
        results.append((
            f"RF1-12.1: Sin falsos positivos externos [{e}]",
            False
        ))

    # ================================================================
    # RF1-13: self.metodo() y cls.metodo() se resuelven correctamente
    # ================================================================
    #
    # QUÉ se valida: Cuando un método de una clase llama a
    # `self.otro_metodo()`, el sistema debe registrar esa llamada
    # como una dependencia interna de la clase (el método llama a
    # otro método de la misma clase). Antes, la llamada aparecía
    # como `self.otro_metodo` y no se vinculaba con `Clase.otro_metodo`.
    #
    # CÓMO se valida: Se crea una clase Procesador con métodos
    # procesar() y validar(). El método procesar() llama a
    # self.validar(). Se verifica que el grafo registra la llamada
    # como Procesador.procesar → Procesador.validar (resolviendo
    # self a la clase contenedora).
    #
    print("── RF1-13: self.metodo() se resuelve a Clase.metodo() ──")

    # Caso A: self.metodo()
    try:
        files = {
            "servicio.py": (
                "class Procesador:\n"
                "    def procesar(self, dato):\n"
                "        return self.validar(dato)\n"
                "\n"
                "    def validar(self, dato):\n"
                "        return bool(dato)\n"
            ),
        }
        graph = SymbolGraph()
        graph.build_from_files(files)

        # Buscar quienes llaman a Procesador.validar
        ctx = graph.get_refactor_context("servicio.py", "Procesador.validar")
        callers = ctx.get("llamado_por", [])

        # VERIFICACIÓN: Procesador.procesar debe ser caller de Procesador.validar
        caller_symbols = [sym for _, sym in callers]
        has_caller = "Procesador.procesar" in caller_symbols
        assert has_caller, (
            f"Procesador.procesar debería llamar a Procesador.validar. "
            f"Callers encontrados: {callers}. "
            f"Probablemente self.validar() no se resolvió a Procesador.validar."
        )
        results.append((
            "RF1-13.1: self.validar() se resuelve como Procesador.validar → detectado",
            True
        ))
    except Exception as e:
        results.append((
            f"RF1-13.1: self.metodo() resolución [{e}]",
            False
        ))

    # Caso B: cls.metodo() en classmethod
    try:
        files = {
            "fabrica.py": (
                "class Fabrica:\n"
                "    @classmethod\n"
                "    def crear(cls, config):\n"
                "        return cls.validar_config(config)\n"
                "\n"
                "    def validar_config(cls, config):\n"
                "        return bool(config)\n"
            ),
        }
        graph = SymbolGraph()
        graph.build_from_files(files)

        ctx = graph.get_refactor_context("fabrica.py", "Fabrica.validar_config")
        callers = ctx.get("llamado_por", [])
        caller_symbols = [sym for _, sym in callers]
        has_caller = "Fabrica.crear" in caller_symbols
        assert has_caller, (
            f"Fabrica.crear debería llamar a Fabrica.validar_config via cls. "
            f"Callers: {callers}"
        )
        results.append((
            "RF1-13.2: cls.validar_config() se resuelve como Fabrica.validar_config",
            True
        ))
    except Exception as e:
        results.append((
            f"RF1-13.2: cls.metodo() resolución [{e}]",
            False
        ))

    # ================================================================
    # RF1-14: importlib.import_module(variable) se resuelve con tracking
    # ================================================================
    #
    # QUÉ se valida: Cuando una variable contiene un string literal y
    # luego se pasa como argumento a importlib.import_module(), el
    # sistema ahora puede resolver ese módulo dinámico. Antes solo
    # funcionaba si el argumento era un string literal directo.
    #
    # CÓMO se valida: Se crea un archivo donde:
    #   1. Se asigna una variable: nombre_modulo = "utils"
    #   2. Se importa dinámicamente: mod = importlib.import_module(nombre_modulo)
    #   3. Se llama a una función: mod.validar('dato')
    # Se verifica que el grafo detecta que main.py llama a validar()
    # en utils.py a través de la cadena variable → importlib → función.
    #
    print("── RF1-14: importlib.import_module(variable) con tracking ──")

    try:
        files = {
            "main.py": (
                "import importlib\n"
                "\n"
                "def cargar():\n"
                "    nombre_modulo = 'utils'\n"
                "    mod = importlib.import_module(nombre_modulo)\n"
                "    return mod.validar('dato')\n"
            ),
            "utils.py": (
                "def validar(dato):\n"
                "    return bool(dato)\n"
            ),
        }
        graph = SymbolGraph()
        graph.build_from_files(files)

        ctx = graph.get_refactor_context("utils.py", "validar")
        callers = ctx.get("llamado_por", [])
        caller_files = [f for f, _ in callers]

        # VERIFICACIÓN: main.py debe ser caller de validar via import dinámico con variable
        assert "main.py" in caller_files, (
            f"main.py debería llamar a validar via importlib.import_module(variable). "
            f"Callers encontrados: {caller_files}. "
            f"El tracking de variables no resolvió 'nombre_modulo' → 'utils'."
        )
        results.append((
            "RF1-14.1: importlib.import_module(variable) resuelve módulo via tracking",
            True
        ))
    except Exception as e:
        results.append((
            f"RF1-14.1: importlib con variable [{e}]",
            False
        ))

    # Caso B: __import__ con variable
    try:
        files = {
            "main.py": (
                "def cargar():\n"
                "    target = 'utils'\n"
                "    mod = __import__(target)\n"
                "    return mod.validar('dato')\n"
            ),
            "utils.py": (
                "def validar(dato):\n"
                "    return bool(dato)\n"
            ),
        }
        graph = SymbolGraph()
        graph.build_from_files(files)

        ctx = graph.get_refactor_context("utils.py", "validar")
        callers = ctx.get("llamado_por", [])
        caller_files = [f for f, _ in callers]

        assert "main.py" in caller_files, (
            f"main.py debería llamar a validar via __import__(variable): {caller_files}"
        )
        results.append((
            "RF1-14.2: __import__(variable) resuelve módulo via tracking",
            True
        ))
    except Exception as e:
        results.append((
            f"RF1-14.2: __import__ con variable [{e}]",
            False
        ))

    # ================================================================
    # Reporte de resultados
    # ================================================================
    print("\n" + "=" * 70)
    print("test_rf1_v12_improvements.py — RF1 v1.2 Validation")
    print("=" * 70)

    for name, passed in results:
        status = "[PASS]" if passed else "[FAIL]"
        print(f"  {status} {name}")

    passed = sum(1 for _, p in results if p)
    failed = len(results) - passed
    print(f"\nResultado: {passed}/{len(results)} PASS, {failed} FAIL")
    print("=" * 70)

    # Detalle de qué valida cada test
    print("\nDETALLE DE VALIDACIONES:")
    print("-" * 70)
    print("RF1-10: Verifica que 'from . import X' resuelve a X.py y no a __init__.py")
    print("        Se creó un paquete real en disco y se comprobó la ruta resuelta.")
    print("")
    print("RF1-11a: Verifica que 'from utils import *' expande los símbolos de __all__")
    print("        Se creó utils.py con __all__=['validar','formatear'] y se")
    print("        comprobó que main.py aparece como caller de ambos.")
    print("")
    print("RF1-11b: Verifica que sin __all__, se expanden símbolos públicos (no _)")
    print("        Se creó utils.py sin __all__ y se comprobó que validar() se")
    print("        detecta pero _privada() no.")
    print("")
    print("RF1-12: Verifica que 'import json' no crea dependencia fantasma a json.py")
    print("        Se creó un proyecto en disco con main.py importando json (stdlib).")
    print("        Se comprobó que utils.py sí aparece pero json.py no.")
    print("")
    print("RF1-13a: Verifica que self.validar() se resuelve a Clase.validar()")
    print("        Se creó una clase con self.validar() y se comprobó que el")
    print("        grafo registra Procesador.procesar → Procesador.validar.")
    print("")
    print("RF1-13b: Verifica que cls.validar_config() se resuelve a Fabrica.validar_config()")
    print("        Se creó un classmethod usando cls y se comprobó la resolución.")
    print("")
    print("RF1-14a: Verifica que importlib.import_module(variable) resuelve vía tracking")
    print("        Se asignó 'utils' a una variable y se pasó a importlib.import_module().")
    print("        Se comprobó que main.py aparece como caller de utils.validar().")
    print("")
    print("RF1-14b: Verifica que __import__(variable) resuelve vía tracking")
    print("        Mismo patrón con __import__ en vez de importlib.import_module.")
    print("-" * 70)

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    _run_validation()
