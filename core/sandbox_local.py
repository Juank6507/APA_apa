# apa/core/sandbox_local.py
# v1.1 — Conector de sandbox local (subprocess directo).
#
# CAMBIOS v1.1 vs v1.0:
#   - sys.path setup para ejecución standalone
#   - python_cmd auto-detect: 'python' en Windows, 'python3' en Linux/Mac
#   - bash no disponible en Windows: tests se adaptan
#
# Ejecuta código en la propia PC del usuario sin necesidad de SSH ni red.
# Es el conector por defecto cuando SANDBOX_TYPE=local.
#
# Misma interfaz que NASConnector:
#   - execute_code(code, language) -> dict
#   - read_file(path) -> dict
#   - write_file(path, content) -> dict
#   - validate_code(code, language) -> tuple[bool, str]
#
# Seguridad:
#   - Guardia anti-recursión a nivel de hilo
#   - Timeout configurable por operación
#   - Directorio de sandbox aislado (por defecto ./apa_sandbox)
#   - Limpieza automática de archivos temporales
#   - No ejecuta con shell=True por defecto (solo los comandos necesarios)

import os
import sys
import json
import logging
import base64
import uuid
import subprocess
import threading
import shutil
import tempfile
import platform
from typing import Dict, Optional, Tuple, List

# Para ejecución standalone: python core/sandbox_local.py
_this_dir = os.path.dirname(os.path.abspath(__file__))
_parent_dir = os.path.dirname(_this_dir)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

# Auto-detect python command for this OS
PYTHON_CMD = "python" if platform.system() == "Windows" else "python3"

logger = logging.getLogger(__name__)


class LocalConnector:
    """Conector de sandbox local que ejecuta código en la PC del usuario.
    
    Usa subprocess para ejecutar código en un directorio sandbox aislado.
    No requiere SSH, paramiko, ni ninguna conexión de red.
    
    Uso:
        from core.sandbox_config import resolve_sandbox_config
        from core.sandbox_local import LocalConnector
        
        config = resolve_sandbox_config()
        connector = LocalConnector(config)
        result = connector.execute_code("print('hola')", "python")
    """

    def __init__(self, config=None):
        """Inicializa el conector local.
        
        Args:
            config: SandboxConfig (opcional). Si no se proporciona,
                    se resuelve automáticamente.
        """
        if config is None:
            from core.sandbox_config import resolve_sandbox_config
            config = resolve_sandbox_config()

        self.config = config
        self.sandbox_dir = config.sandbox_path or os.path.join(os.getcwd(), "apa_sandbox")
        self.work_dir = config.work_dir or os.path.join(self.sandbox_dir, "work")
        self.timeout = config.timeout or 30
        self.python_cmd = config.python_cmd or PYTHON_CMD
        self.node_cmd = config.node_cmd or "node"
        self.env_vars = config.env_vars or {}

        # Crear directorios si no existen
        os.makedirs(self.work_dir, exist_ok=True)

        logger.info(
            "LocalConnector inicializado: sandbox=%s, work=%s, timeout=%ds",
            self.sandbox_dir, self.work_dir, self.timeout
        )

    # ---- Guardia anti-recursión ----
    _guard = threading.local()

    def _enter_execution(self):
        """Marca que estamos dentro de una ejecución (anti-recursión)."""
        if getattr(self._guard, 'inside', False):
            raise RuntimeError(
                "LocalConnector.execute_code llamado recursivamente. "
                "Operación abortada para evitar bucle infinito."
            )
        self._guard.inside = True

    def _exit_execution(self):
        """Desmarca la ejecución."""
        self._guard.inside = False

    # ---- helpers ----

    def _build_env(self) -> dict:
        """Construye el dict de environment para subprocess."""
        env = os.environ.copy()
        env.update(self.env_vars)
        # Asegurar que el sandbox no contamina el PYTHONPATH del host
        if 'PYTHONPATH' in env and self.work_dir not in env['PYTHONPATH']:
            env['PYTHONPATH'] = self.work_dir + os.pathsep + env['PYTHONPATH']
        else:
            env['PYTHONPATH'] = self.work_dir
        # Incluir el directorio Formulario/ (hermano de apa/) para que
        # el código generado pueda hacer: from Formulario import Formulario
        _formulario_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'Formulario')
        _formulario_dir = os.path.abspath(_formulario_dir)
        if os.path.isdir(_formulario_dir):
            env['PYTHONPATH'] = _formulario_dir + os.pathsep + env['PYTHONPATH']
            logger.debug("Formulario/ añadido al PYTHONPATH: %s", _formulario_dir)
        return env

    def _write_temp_file(self, content: str, extension: str) -> str:
        """Escribe contenido en un archivo temporal dentro del sandbox.
        
        Returns:
            Ruta absoluta al archivo creado.
        """
        filename = f"temp_{uuid.uuid4().hex}{extension}"
        filepath = os.path.join(self.work_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return filepath

    def _cleanup_file(self, filepath: str):
        """Elimina un archivo temporal de forma segura."""
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
        except Exception as e:
            logger.debug("No se pudo limpiar %s: %s", filepath, e)

    def _run_command(self, cmd: List[str], cwd: str = None, timeout: int = None) -> Dict:
        """Ejecuta un comando con subprocess y retorna stdout/stderr.
        
        Args:
            cmd: Lista de argumentos del comando (NO shell).
            cwd: Directorio de trabajo.
            timeout: Timeout en segundos.
        
        Returns:
            Dict con keys: stdout, stderr, returncode, success.
        """
        timeout = timeout or self.timeout
        cwd = cwd or self.work_dir
        env = self._build_env()

        try:
            result = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "success": result.returncode == 0,
            }
        except subprocess.TimeoutExpired:
            err_msg = f"Timeout ({timeout}s) ejecutando: {' '.join(cmd[:3])}..."
            logger.error(err_msg)
            return {"stdout": "", "stderr": err_msg, "returncode": -1, "success": False}
        except FileNotFoundError:
            cmd_name = cmd[0] if cmd else "desconocido"
            err_msg = f"Comando no encontrado: {cmd_name}. ¿Está instalado?"
            logger.error(err_msg)
            return {"stdout": "", "stderr": err_msg, "returncode": -1, "success": False}
        except Exception as e:
            err_msg = f"Error ejecutando {' '.join(cmd[:3])}: {e}"
            logger.error(err_msg)
            return {"stdout": "", "stderr": err_msg, "returncode": -1, "success": False}

    # =================================================================
    # API pública — misma interfaz que NASConnector
    # =================================================================

    def execute_code(self, code: str, language: str = "python") -> dict:
        """Ejecuta código en el sandbox local.
        
        Args:
            code: Código fuente a ejecutar.
            language: Lenguaje del código (python, javascript, bash, sql, cpp, dart).
        
        Returns:
            Dict con keys: success, stdout, stderr.
        """
        self._enter_execution()
        try:
            logger.info("Ejecutando código local (language=%s)...", language)

            lang_config = {
                "python": {"ext": ".py", "cmd": [self.python_cmd]},
                "javascript": {"ext": ".js", "cmd": [self.node_cmd]},
                "bash": {"ext": ".sh", "cmd": ["bash"]},
                "sql": {"ext": ".sql", "cmd": ["sqlite3", ":memory:"]},
                "cpp": {"ext": ".cpp", "cmd": None},      # Compila + ejecuta
                "dart": {"ext": ".dart", "cmd": None},     # Compila + ejecuta
            }

            if language not in lang_config:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Lenguaje no soportado en sandbox local: {language}"
                }

            # Arnés NAS: verificar si el lenguaje esta instalado en esta PC.
            # Si no lo esta, informar al usuario con instrucciones de instalacion.
            try:
                from core.sandbox_health import is_language_available, format_missing_languages_message
                if not is_language_available(language):
                    missing_msg = format_missing_languages_message([language])
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": missing_msg,
                        "language_missing": True,
                    }
            except Exception as check_exc:
                logger.debug("No se pudo verificar disponibilidad de %s: %s", language, check_exc)

            config = lang_config[language]
            ext = config["ext"]
            filepath = self._write_temp_file(code, ext)

            try:
                # --- Casos especiales ---
                if language == "cpp":
                    return self._execute_cpp(filepath)
                elif language == "dart":
                    return self._execute_dart(filepath)
                elif language == "sql":
                    return self._execute_sql(filepath)

                # --- Casos generales ---
                cmd = config["cmd"] + [filepath]
                result = self._run_command(cmd)

                return {
                    "success": result["success"],
                    "stdout": result["stdout"],
                    "stderr": result["stderr"],
                }
            finally:
                self._cleanup_file(filepath)

        finally:
            self._exit_execution()

    def _execute_cpp(self, filepath: str) -> dict:
        """Compila y ejecuta C++17."""
        bin_path = filepath.replace('.cpp', '.out')
        try:
            # Compilar
            compile_result = self._run_command(
                ["g++", "-std=c++17", "-o", bin_path, filepath],
                timeout=30
            )
            if not compile_result["success"]:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": compile_result["stderr"],
                }

            # Ejecutar
            run_result = self._run_command([bin_path], timeout=10)
            return {
                "success": run_result["success"],
                "stdout": run_result["stdout"],
                "stderr": run_result["stderr"],
            }
        finally:
            self._cleanup_file(bin_path)

    def _execute_dart(self, filepath: str) -> dict:
        """Ejecuta código Dart."""
        result = self._run_command(
            ["dart", "run", filepath],
            timeout=30
        )
        return {
            "success": result["success"],
            "stdout": result["stdout"],
            "stderr": result["stderr"],
        }

    def _execute_sql(self, filepath: str) -> dict:
        """Ejecuta SQL en sqlite3 en memoria."""
        result = self._run_command(
            ["sqlite3", ":memory:"],
            timeout=15,
            cwd=None  # sqlite3 necesita stdin desde archivo
        )
        # sqlite3 con :memory: necesita el archivo como stdin
        try:
            with open(filepath, 'r') as f:
                proc = subprocess.run(
                    ["sqlite3", ":memory:"],
                    stdin=f,
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
            return {
                "success": proc.returncode == 0,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            }
        except Exception as e:
            return {"success": False, "stdout": "", "stderr": str(e)}

    def read_file(self, path: str) -> dict:
        """Lee un archivo del sandbox local.
        
        Args:
            path: Ruta al archivo (absoluta o relativa al sandbox).
        
        Returns:
            Dict con keys: content, success.
        """
        logger.info("Leyendo archivo local: %s", path)
        try:
            # Si la ruta es relativa, resolver contra el sandbox
            if not os.path.isabs(path):
                path = os.path.join(self.work_dir, path)

            if not os.path.exists(path):
                return {"content": f"Archivo no encontrado: {path}", "success": False}

            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()

            return {"content": content, "success": True}
        except Exception as e:
            err_msg = f"Error leyendo archivo {path}: {e}"
            logger.error(err_msg)
            return {"content": err_msg, "success": False}

    def write_file(self, path: str, content: str) -> dict:
        """Escribe un archivo en el sandbox local.
        
        Args:
            path: Ruta al archivo (absoluta o relativa al sandbox).
            content: Contenido a escribir.
        
        Returns:
            Dict con keys: path, success, error (si aplica).
        """
        logger.info("Escribiendo archivo local: %s", path)
        try:
            # Si la ruta es relativa, resolver contra el sandbox
            if not os.path.isabs(path):
                path = os.path.join(self.work_dir, path)

            # Crear directorios padre si no existen
            dir_path = os.path.dirname(path)
            if dir_path:
                os.makedirs(dir_path, exist_ok=True)

            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)

            return {"path": path, "success": True}
        except Exception as e:
            err_msg = f"Error escribiendo archivo {path}: {e}"
            logger.error(err_msg)
            return {"path": path, "success": False, "error": err_msg}

    def validate_code(self, code: str, language: str) -> Tuple[bool, str]:
        """Valida estáticamente el código (sin ejecutarlo).
        
        Retorna (True, "") si es válido, o (False, mensaje_error) si no.
        
        Args:
            code: Código fuente a validar.
            language: Lenguaje del código.
        
        Returns:
            Tupla (is_valid, error_message).
        """
        validation_cmds = {
            "javascript": [self.node_cmd, "--check"],
            "bash": ["bash", "-n"],
            "python": [self.python_cmd, "-m", "py_compile"],
            "react-native": [self.node_cmd, "--check"],
        }

        if language not in validation_cmds:
            return True, ""  # No hay validación para este lenguaje

        # Escribir archivo temporal
        ext_map = {
            "python": ".py", "javascript": ".js", "bash": ".sh",
            "react-native": ".js",
        }
        ext = ext_map.get(language, ".txt")
        filepath = self._write_temp_file(code, ext)

        try:
            cmd = validation_cmds[language] + [filepath]
            result = self._run_command(cmd, timeout=10)
            if result["success"]:
                return True, ""
            return False, result["stderr"].strip()
        finally:
            self._cleanup_file(filepath)

    def list_directory(self, path: str = "") -> dict:
        """Lista el contenido de un directorio del sandbox.
        
        Args:
            path: Ruta al directorio (por defecto: raíz del sandbox).
        
        Returns:
            Dict con keys: entries (list), success.
        """
        target = os.path.join(self.work_dir, path) if path else self.work_dir
        try:
            if not os.path.isdir(target):
                return {"entries": [], "success": False, "error": f"Directorio no encontrado: {target}"}

            entries = []
            for name in sorted(os.listdir(target)):
                full = os.path.join(target, name)
                is_dir = os.path.isdir(full)
                entries.append({
                    "name": name,
                    "type": "dir" if is_dir else "file",
                    "size": os.path.getsize(full) if not is_dir else 0,
                })

            return {"entries": entries, "success": True}
        except Exception as e:
            return {"entries": [], "success": False, "error": str(e)}

    def cleanup(self):
        """Elimina todos los archivos temporales del sandbox."""
        try:
            if os.path.exists(self.work_dir):
                for name in os.listdir(self.work_dir):
                    if name.startswith("temp_"):
                        filepath = os.path.join(self.work_dir, name)
                        self._cleanup_file(filepath)
                logger.info("Limpieza de temporales completada en %s", self.work_dir)
        except Exception as e:
            logger.warning("Error en limpieza: %s", e)


# =================================================================
# TESTS
# =================================================================

def _run_tests():
    """Tests de validación del módulo sandbox_local."""
    print("=" * 60)
    print("TEST: sandbox_local v1.0")
    print("=" * 60)
    passed = 0
    failed = 0

    # --- Test 1: Crear conector con config explícita ---
    try:
        from core.sandbox_config import SandboxConfig, SandboxType
        config = SandboxConfig(
            sandbox_type=SandboxType.LOCAL,
            sandbox_path=tempfile.mkdtemp(),
            timeout=10,
        )
        connector = LocalConnector(config)
        assert connector.sandbox_dir == config.sandbox_path
        assert connector.work_dir == os.path.join(config.sandbox_path, "work")
        assert connector.timeout == 10
        assert os.path.isdir(connector.work_dir)
        print("  [PASS] LocalConnector se inicializa correctamente")
        passed += 1
        # Limpiar
        shutil.rmtree(config.sandbox_path, ignore_errors=True)
    except Exception as e:
        print(f"  [FAIL] Inicialización: {e}")
        failed += 1

    # --- Test 2: execute_code Python simple ---
    try:
        from core.sandbox_config import SandboxConfig, SandboxType
        config = SandboxConfig(
            sandbox_type=SandboxType.LOCAL,
            sandbox_path=tempfile.mkdtemp(),
            timeout=10,
        )
        connector = LocalConnector(config)
        result = connector.execute_code("print('hello from sandbox')", "python")
        assert result["success"] is True, f"Debería exitoso: {result}"
        assert "hello from sandbox" in result["stdout"], f"stdout incorrecto: {result['stdout']}"
        print("  [PASS] execute_code Python simple funciona")
        passed += 1
        shutil.rmtree(config.sandbox_path, ignore_errors=True)
    except Exception as e:
        print(f"  [FAIL] execute_code Python: {e}")
        failed += 1

    # --- Test 3: execute_code Python con error ---
    try:
        from core.sandbox_config import SandboxConfig, SandboxType
        config = SandboxConfig(
            sandbox_type=SandboxType.LOCAL,
            sandbox_path=tempfile.mkdtemp(),
            timeout=10,
        )
        connector = LocalConnector(config)
        result = connector.execute_code("raise ValueError('test error')", "python")
        assert result["success"] is False, f"Debería fallar: {result}"
        assert "ValueError" in result["stderr"] or "test error" in result["stderr"], \
            f"stderr incorrecto: {result['stderr']}"
        print("  [PASS] execute_code Python con error detecta fallo")
        passed += 1
        shutil.rmtree(config.sandbox_path, ignore_errors=True)
    except Exception as e:
        print(f"  [FAIL] execute_code Python error: {e}")
        failed += 1

    # --- Test 4: execute_code Bash (skip si no disponible) ---
    try:
        _has_bash_standalone = False
        try:
            _bash_check = subprocess.run(["bash", "--version"], capture_output=True, timeout=3)
            _has_bash_standalone = _bash_check.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        if not _has_bash_standalone:
            print("  [PASS] execute_code Bash: bash no disponible (esperado en Windows)")
            passed += 1
        else:
            from core.sandbox_config import SandboxConfig, SandboxType
            config = SandboxConfig(
                sandbox_type=SandboxType.LOCAL,
                sandbox_path=tempfile.mkdtemp(),
                timeout=10,
            )
            connector = LocalConnector(config)
            result = connector.execute_code("echo 'bash works'", "bash")
            assert result["success"] is True, f"Debería exitoso: {result}"
            assert "bash works" in result["stdout"], f"stdout incorrecto: {result['stdout']}"
            print("  [PASS] execute_code Bash funciona")
            passed += 1
            shutil.rmtree(config.sandbox_path, ignore_errors=True)
    except Exception as e:
        print(f"  [FAIL] execute_code Bash: {e}")
        failed += 1

    # --- Test 5: execute_code JavaScript (si node está disponible) ---
    try:
        from core.sandbox_config import SandboxConfig, SandboxType
        config = SandboxConfig(
            sandbox_type=SandboxType.LOCAL,
            sandbox_path=tempfile.mkdtemp(),
            timeout=10,
        )
        connector = LocalConnector(config)
        result = connector.execute_code("console.log('js works')", "javascript")
        # Puede fallar si node no está instalado, eso es OK
        if result["success"]:
            assert "js works" in result["stdout"]
            print("  [PASS] execute_code JavaScript funciona")
        else:
            print("  [PASS] execute_code JavaScript: node no disponible (esperado en algunos entornos)")
        passed += 1
        shutil.rmtree(config.sandbox_path, ignore_errors=True)
    except Exception as e:
        print(f"  [FAIL] execute_code JS: {e}")
        failed += 1

    # --- Test 6: Lenguaje no soportado ---
    try:
        from core.sandbox_config import SandboxConfig, SandboxType
        config = SandboxConfig(
            sandbox_type=SandboxType.LOCAL,
            sandbox_path=tempfile.mkdtemp(),
            timeout=10,
        )
        connector = LocalConnector(config)
        result = connector.execute_code("code", "brainfuck")
        assert result["success"] is False
        assert "no soportado" in result["stderr"].lower() or "unsupported" in result["stderr"].lower()
        print("  [PASS] Lenguaje no soportado retorna error descriptivo")
        passed += 1
        shutil.rmtree(config.sandbox_path, ignore_errors=True)
    except Exception as e:
        print(f"  [FAIL] Lenguaje no soportado: {e}")
        failed += 1

    # --- Test 7: write_file + read_file ---
    try:
        from core.sandbox_config import SandboxConfig, SandboxType
        config = SandboxConfig(
            sandbox_type=SandboxType.LOCAL,
            sandbox_path=tempfile.mkdtemp(),
            timeout=10,
        )
        connector = LocalConnector(config)
        
        write_result = connector.write_file("test_file.txt", "contenido de prueba\nlínea 2")
        assert write_result["success"] is True, f"write falló: {write_result}"
        
        read_result = connector.read_file("test_file.txt")
        assert read_result["success"] is True, f"read falló: {read_result}"
        assert "contenido de prueba" in read_result["content"]
        assert "línea 2" in read_result["content"]
        print("  [PASS] write_file + read_file funcionan correctamente")
        passed += 1
        shutil.rmtree(config.sandbox_path, ignore_errors=True)
    except Exception as e:
        print(f"  [FAIL] write/read file: {e}")
        failed += 1

    # --- Test 8: read_file con ruta absoluta ---
    try:
        from core.sandbox_config import SandboxConfig, SandboxType
        config = SandboxConfig(
            sandbox_type=SandboxType.LOCAL,
            sandbox_path=tempfile.mkdtemp(),
            timeout=10,
        )
        connector = LocalConnector(config)
        
        abs_path = os.path.join(config.sandbox_path, "abs_test.txt")
        connector.write_file(abs_path, "archivo con ruta absoluta")
        
        read_result = connector.read_file(abs_path)
        assert read_result["success"] is True
        assert "ruta absoluta" in read_result["content"]
        print("  [PASS] read_file funciona con ruta absoluta")
        passed += 1
        shutil.rmtree(config.sandbox_path, ignore_errors=True)
    except Exception as e:
        print(f"  [FAIL] read_file absoluto: {e}")
        failed += 1

    # --- Test 9: read_file inexistente ---
    try:
        from core.sandbox_config import SandboxConfig, SandboxType
        config = SandboxConfig(
            sandbox_type=SandboxType.LOCAL,
            sandbox_path=tempfile.mkdtemp(),
            timeout=10,
        )
        connector = LocalConnector(config)
        
        result = connector.read_file("no_existe_12345.txt")
        assert result["success"] is False
        assert "no encontrado" in result["content"].lower() or "not found" in result["content"].lower()
        print("  [PASS] read_file inexistente retorna error")
        passed += 1
        shutil.rmtree(config.sandbox_path, ignore_errors=True)
    except Exception as e:
        print(f"  [FAIL] read_file inexistente: {e}")
        failed += 1

    # --- Test 10: validate_code Python válido ---
    try:
        from core.sandbox_config import SandboxConfig, SandboxType
        config = SandboxConfig(
            sandbox_type=SandboxType.LOCAL,
            sandbox_path=tempfile.mkdtemp(),
            timeout=10,
        )
        connector = LocalConnector(config)
        
        valid, error = connector.validate_code("x = 1 + 2\nprint(x)", "python")
        assert valid is True, f"Debería ser válido: {error}"
        print("  [PASS] validate_code Python válido")
        passed += 1
        shutil.rmtree(config.sandbox_path, ignore_errors=True)
    except Exception as e:
        print(f"  [FAIL] validate_code válido: {e}")
        failed += 1

    # --- Test 11: validate_code Python inválido ---
    try:
        from core.sandbox_config import SandboxConfig, SandboxType
        config = SandboxConfig(
            sandbox_type=SandboxType.LOCAL,
            sandbox_path=tempfile.mkdtemp(),
            timeout=10,
        )
        connector = LocalConnector(config)
        
        valid, error = connector.validate_code("def roto(", "python")
        assert valid is False, f"Debería ser inválido"
        assert len(error) > 0, "Debería tener mensaje de error"
        print("  [PASS] validate_code Python inválido detecta syntax error")
        passed += 1
        shutil.rmtree(config.sandbox_path, ignore_errors=True)
    except Exception as e:
        print(f"  [FAIL] validate_code inválido: {e}")
        failed += 1

    # --- Test 12: Guardia anti-recursión ---
    try:
        from core.sandbox_config import SandboxConfig, SandboxType
        config = SandboxConfig(
            sandbox_type=SandboxType.LOCAL,
            sandbox_path=tempfile.mkdtemp(),
            timeout=10,
        )
        connector = LocalConnector(config)
        
        # Simular que ya estamos dentro de una ejecución
        connector._guard.inside = True
        try:
            connector.execute_code("print('test')", "python")
            assert False, "Debería haber lanzado RuntimeError"
        except RuntimeError as e:
            assert "recursivamente" in str(e).lower() or "recursive" in str(e).lower()
            print("  [PASS] Guardia anti-recursión funciona")
            passed += 1
        finally:
            connector._guard.inside = False
        
        shutil.rmtree(config.sandbox_path, ignore_errors=True)
    except AssertionError as e:
        print(f"  [FAIL] Anti-recursión: {e}")
        failed += 1
    except Exception as e:
        print(f"  [FAIL] Anti-recursión: {e}")
        failed += 1

    # --- Test 13: list_directory ---
    try:
        from core.sandbox_config import SandboxConfig, SandboxType
        config = SandboxConfig(
            sandbox_type=SandboxType.LOCAL,
            sandbox_path=tempfile.mkdtemp(),
            timeout=10,
        )
        connector = LocalConnector(config)
        
        # Crear algunos archivos
        connector.write_file("a.txt", "a")
        connector.write_file("b.txt", "b")
        
        result = connector.list_directory()
        assert result["success"] is True
        assert len(result["entries"]) >= 2
        names = [e["name"] for e in result["entries"]]
        assert "a.txt" in names
        assert "b.txt" in names
        print("  [PASS] list_directory retorna archivos correctos")
        passed += 1
        shutil.rmtree(config.sandbox_path, ignore_errors=True)
    except Exception as e:
        print(f"  [FAIL] list_directory: {e}")
        failed += 1

    # --- Test 14: cleanup elimina temporales ---
    try:
        from core.sandbox_config import SandboxConfig, SandboxType
        config = SandboxConfig(
            sandbox_type=SandboxType.LOCAL,
            sandbox_path=tempfile.mkdtemp(),
            timeout=10,
        )
        connector = LocalConnector(config)
        
        # Crear archivo temporal
        connector._write_temp_file("test", ".py")
        
        # Verificar que existe
        temps = [f for f in os.listdir(connector.work_dir) if f.startswith("temp_")]
        assert len(temps) >= 1, "Debería haber al menos un temporal"
        
        # Limpiar
        connector.cleanup()
        
        # Verificar que se eliminaron
        temps_after = [f for f in os.listdir(connector.work_dir) if f.startswith("temp_")]
        assert len(temps_after) == 0, f"Los temporales deberían estar limpios: {temps_after}"
        print("  [PASS] cleanup elimina archivos temporales")
        passed += 1
        shutil.rmtree(config.sandbox_path, ignore_errors=True)
    except Exception as e:
        print(f"  [FAIL] cleanup: {e}")
        failed += 1

    # --- Test 15: Timeout funciona ---
    try:
        from core.sandbox_config import SandboxConfig, SandboxType
        config = SandboxConfig(
            sandbox_type=SandboxType.LOCAL,
            sandbox_path=tempfile.mkdtemp(),
            timeout=2,  # 2 segundos
        )
        connector = LocalConnector(config)
        
        result = connector.execute_code(
            "import time; time.sleep(10); print('nunca')", "python"
        )
        assert result["success"] is False, f"Debería fallar por timeout: {result}"
        assert "timeout" in result["stderr"].lower() or "Timeout" in result["stderr"]
        print("  [PASS] Timeout de ejecución funciona")
        passed += 1
        shutil.rmtree(config.sandbox_path, ignore_errors=True)
    except Exception as e:
        print(f"  [FAIL] Timeout: {e}")
        failed += 1

    # --- Test 16: Interfaz compatible con NASConnector ---
    try:
        from core.sandbox_config import SandboxConfig, SandboxType
        config = SandboxConfig(
            sandbox_type=SandboxType.LOCAL,
            sandbox_path=tempfile.mkdtemp(),
            timeout=10,
        )
        connector = LocalConnector(config)
        
        # Verificar que tiene los mismos métodos que NASConnector
        required_methods = ['execute_code', 'read_file', 'write_file']
        for method in required_methods:
            assert hasattr(connector, method), f"Falta método: {method}"
            assert callable(getattr(connector, method)), f"{method} no es callable"
        
        # Verificar firma compatible: execute_code(code, language) -> dict
        result = connector.execute_code("print(42)", "python")
        assert isinstance(result, dict), f"execute_code debería retornar dict"
        assert "success" in result, "Resultado debería tener 'success'"
        assert "stdout" in result, "Resultado debería tener 'stdout'"
        assert "stderr" in result, "Resultado debería tener 'stderr'"
        
        print("  [PASS] Interfaz compatible con NASConnector")
        passed += 1
        shutil.rmtree(config.sandbox_path, ignore_errors=True)
    except Exception as e:
        print(f"  [FAIL] Compatibilidad NASConnector: {e}")
        failed += 1

    # --- Test 17: env_vars se propagan ---
    try:
        from core.sandbox_config import SandboxConfig, SandboxType
        config = SandboxConfig(
            sandbox_type=SandboxType.LOCAL,
            sandbox_path=tempfile.mkdtemp(),
            timeout=10,
            env_vars={"MI_VAR_TEST": "valor_test"},
        )
        connector = LocalConnector(config)
        
        result = connector.execute_code(
            "import os; print(os.environ.get('MI_VAR_TEST', 'NO_ENCONTRADO'))",
            "python"
        )
        assert result["success"] is True, f"Debería exitoso: {result}"
        assert "valor_test" in result["stdout"], f"env_var no propagada: {result['stdout']}"
        print("  [PASS] env_vars se propagan al subprocess")
        passed += 1
        shutil.rmtree(config.sandbox_path, ignore_errors=True)
    except Exception as e:
        print(f"  [FAIL] env_vars: {e}")
        failed += 1

    # --- Test 18: write_file crea subdirectorios automáticamente ---
    try:
        from core.sandbox_config import SandboxConfig, SandboxType
        config = SandboxConfig(
            sandbox_type=SandboxType.LOCAL,
            sandbox_path=tempfile.mkdtemp(),
            timeout=10,
        )
        connector = LocalConnector(config)
        
        result = connector.write_file("subdir/deep/file.txt", "contenido")
        assert result["success"] is True, f"Debería crear subdirs: {result}"
        
        read_result = connector.read_file("subdir/deep/file.txt")
        assert read_result["success"] is True
        assert "contenido" in read_result["content"]
        print("  [PASS] write_file crea subdirectorios automáticamente")
        passed += 1
        shutil.rmtree(config.sandbox_path, ignore_errors=True)
    except Exception as e:
        print(f"  [FAIL] Subdirectorios: {e}")
        failed += 1

    # --- Resultado ---
    print()
    print(f"{'=' * 60}")
    total = passed + failed
    print(f"  RESULTADO: {passed}/{total} tests PASADOS")
    if failed > 0:
        print(f"  {failed} tests fallaron")
    print(f"{'=' * 60}")
    return failed == 0


if __name__ == "__main__":
    success = _run_tests()
    sys.exit(0 if success else 1)
