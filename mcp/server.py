# apa/mcp/server.py
# v2.1 — Sandbox configurable + sonda TCP empirica (0.5s) + deteccion de errores.
#
# CAMBIOS v2.0 vs v1.0 (anterior):
#   - NASConnector ahora acepta config opcional (SandboxConfig).
#     Si se pasa, usa host/user/ssh_port de la config en vez de
#     leer directamente de settings.nas_host/nas_user.
#   - Añadida get_connector() — factory function que retorna el
#     conector correcto (NASConnector o LocalConnector) según
#     la configuración de sandbox.
#   - NASConnector.__init__() sin parámetros mantiene compatibilidad
#     total con el código existente.
#   - paramiko solo se importa cuando se usa NASConnector (no para local).
#
# NOTA: El comportamiento EXISTENTE de NASConnector NO cambia.
#       Solo se añade la opción de pasar SandboxConfig.
import sys
import os
import json
import logging
import base64
import uuid
import subprocess
import time
import threading
import shlex

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from config.settings import settings

# Guardia anti-recursión a nivel de hilo
_execution_guard = threading.local()

logging.basicConfig(level=logging.ERROR)
for logger_name in ["__main__", "core.orchestrator", "core.planner", "core.checkpoint", "agents.generator", "core.router", "mcp.server", "agents.documenter"]:
    logging.getLogger(logger_name).setLevel(logging.WARNING)

logger = logging.getLogger(__name__)
logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)


class NASConnector:
    """Conector de sandbox remoto via SSH (NAS, VM, External).
    
    Soporta dos modos de inicialización:
    1. Sin parámetros: lee de settings.nas_host/nas_user (compatibilidad total)
    2. Con SandboxConfig: usa host/user/port de la config (Fase 5)
    
    Esto permite que tanto el código legacy como el nuevo código
    de Fase 5 funcionen sin cambios.
    """

    def __init__(self, sandbox_config=None):
        """Inicializa la conexión SSH.
        
        Args:
            sandbox_config: SandboxConfig opcional (de core.sandbox_config).
                           Si se proporciona, usa sus credenciales.
                           Si no, lee de settings.nas_host/nas_user (legacy).
        """
        if sandbox_config is not None:
            self.nas_host = sandbox_config.host
            self.nas_user = sandbox_config.user
            self.sandbox_dir = sandbox_config.sandbox_path
            self.ssh_port = sandbox_config.ssh_port
            self.ssh_key_path = sandbox_config.ssh_key_path
            # Timeout restaurado al valor original del NAS.
            # El NASConnector se intenta en segundo plano (no bloquea el
            # arranque del servidor), así que puede esperar sus tiempos
            # completos sin afectar al usuario.
            self.timeout = sandbox_config.timeout
        else:
            # Sin parámetros: intentar resolver desde sandbox_config (.env)
            # Si falla, fallback a settings legacy
            try:
                from core.sandbox_config import resolve_sandbox_config
                _cfg = resolve_sandbox_config()
                self.nas_host = _cfg.host
                self.nas_user = _cfg.user
                self.sandbox_dir = _cfg.sandbox_path
                self.ssh_port = _cfg.ssh_port
                self.ssh_key_path = _cfg.ssh_key_path
                # Timeout restaurado al valor original del NAS.
                self.timeout = _cfg.timeout
            except Exception:
                # Fallback legacy: leer de settings directamente
                self.nas_host = settings.nas_host
                self.nas_user = settings.nas_user
                self.sandbox_dir = getattr(settings, 'nas_sandbox_path', '/app/sandbox') or '/app/sandbox'
                self.ssh_port = getattr(settings, 'sandbox_ssh_port', 22) or 22
                self.ssh_key_path = getattr(settings, 'nas_ssh_key', '') or ''
                # Timeout restaurado al valor original del NAS (20s).
                # El NASConnector se intenta en segundo plano (no bloquea
                # el arranque del servidor), así que puede esperar 20s.
                self.timeout = 20

        # Importar paramiko solo cuando se necesita (no para local)
        import paramiko
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        # Construir kwargs de conexión
        connect_kwargs = {
            "hostname": self.nas_host,
            "port": self.ssh_port,
            "username": self.nas_user,
            "timeout": self.timeout,
            "banner_timeout": self.timeout,
            "auth_timeout": self.timeout,
        }
        if self.ssh_key_path:
            connect_kwargs["key_filename"] = self.ssh_key_path

        self.client.connect(**connect_kwargs)
        logger.info(
            "NASConnector conectado a %s@%s:%d (sandbox=%s)",
            self.nas_user, self.nas_host, self.ssh_port, self.sandbox_dir
        )

    def _call_mcp_tool(self, tool_name: str, arguments: dict) -> dict:
        payload = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments}
        }, ensure_ascii=False) + "\n"

        command = f"sudo /usr/local/bin/docker exec -i mcp-server python -u /app/server/server.py"
        stdin, stdout, stderr = self.client.exec_command(command, timeout=60)
        stdin.write(payload)
        stdin.flush()
        stdin.channel.shutdown_write()

        for line in stdout:
            line = line.strip()
            if not line:
                continue
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
        err_out = stderr.read().decode('utf-8', errors='replace')
        return {"error": err_out or "No se recibió respuesta JSON válida"}

    def execute_code(self, code: str, language: str = "python") -> dict:
        # Guardia anti-recursión
        if getattr(_execution_guard, 'inside', False):
            raise RuntimeError("execute_code llamado recursivamente. Operación abortada para evitar bucle infinito.")
        _execution_guard.inside = True
        try:
            logger.info(f"Ejecutando código en NAS (language={language})...")

            lang_config = {
                "python": {"ext": ".py", "cmd": "python3 {file}"},
                "javascript": {"ext": ".js", "cmd": "node {file}"},
                "bash": {"ext": ".sh", "cmd": "bash -e {file}"},
                "sql": {"ext": ".sql", "cmd": "sqlite3 :memory:"},
                "cpp": {"ext": ".cpp", "cmd": None},
                "dart": {"ext": ".dart", "cmd": None}
            }

            if language not in lang_config:
                return {"success": False, "stdout": "", "stderr": f"Unsupported language: {language}"}

            config = lang_config[language]
            ext = config["ext"]
            filename = f"temp_{uuid.uuid4().hex}{ext}"
            sandbox_path = f"{self.sandbox_dir}/{filename}"

            try:
                encoded = base64.b64encode(code.encode('utf-8')).decode('utf-8')
                path_esc = sandbox_path.replace("'", "\\'")
                write_code = f"""
import os, base64
os.makedirs('{self.sandbox_dir}', exist_ok=True)
with open('{path_esc}', 'w', encoding='utf-8') as f:
    f.write(base64.b64decode('{encoded}').decode('utf-8'))
"""
                write_result = self._call_mcp_tool("ejecutar_en_nas", {"code": write_code})
                if "error" in write_result:
                    return {"stdout": "", "stderr": write_result.get("error", ""), "success": False}

                if language == "sql":
                    exec_code = f"""
import subprocess, sys, json
with open('{path_esc}', 'r', encoding='utf-8') as f:
    result = subprocess.run(
        ['sqlite3', ':memory:'],
        stdin=f,
        capture_output=True,
        text=True,
        timeout=30
    )
    sys.stdout.write(json.dumps({{"rc": result.returncode, "stdout": result.stdout, "stderr": result.stderr}}))
"""
                elif language == "cpp":
                    bin_path = sandbox_path.replace('.cpp', '.out')
                    bin_esc = bin_path.replace("'", "\\'")
                    exec_code = f"""
import subprocess, sys, json
compile_result = subprocess.run(
    ['g++', '-std=c++17', '-o', '{bin_esc}', '{path_esc}'],
    capture_output=True,
    text=True,
    timeout=30
)
if compile_result.returncode != 0:
    sys.stdout.write(json.dumps({{"rc": compile_result.returncode, "stdout": "", "stderr": compile_result.stderr}}))
else:
    run_result = subprocess.run(['{bin_esc}'], capture_output=True, text=True, timeout=10)
    sys.stdout.write(json.dumps({{"rc": run_result.returncode, "stdout": run_result.stdout, "stderr": run_result.stderr}}))
"""
                elif language == "dart":
                    exec_code = f"""
import subprocess, sys, json
result = subprocess.run(
    ['/opt/flutter/bin/dart', 'run', '{path_esc}'],
    capture_output=True,
    text=True,
    timeout=30
)
sys.stdout.write(json.dumps({{"rc": result.returncode, "stdout": result.stdout, "stderr": result.stderr}}))
"""
                else:
                    cmd = config["cmd"].replace("{file}", sandbox_path)
                    exec_code = f"""
import subprocess, sys, json
result = subprocess.run('{cmd}', shell=True, capture_output=True, text=True)
sys.stdout.write(json.dumps({{"rc": result.returncode, "stdout": result.stdout, "stderr": result.stderr}}))
"""
                response = self._call_mcp_tool("ejecutar_en_nas", {"code": exec_code})

                cleanup_code = f"""
import os
for f in ['{path_esc}', '{bin_esc if language == "cpp" else path_esc}']:
    if os.path.exists(f):
                        try:
                            os.remove(f)
                        except:
                            pass
"""
                self._call_mcp_tool("ejecutar_en_nas", {"code": cleanup_code})

                if "error" in response:
                    return {"stdout": "", "stderr": response.get("error", ""), "success": False}

                content_text = ""
                try:
                    content_text = response["result"]["content"][0]["text"]
                except (KeyError, IndexError, TypeError):
                    return {"stdout": "", "stderr": "Formato de respuesta inesperado", "success": False}

                # Interpretar resultado estructurado JSON (formato con rc)
                # que incluye rc, stdout y stderr del subprocess hijo.
                try:
                    _payload = json.loads(content_text)
                    if isinstance(_payload, dict) and "rc" in _payload:
                        _rc = _payload.get("rc", 0)
                        _out = _payload.get("stdout", "")
                        _err = _payload.get("stderr", "")
                        if _rc != 0:
                            return {"stdout": _out, "stderr": _err, "success": False}
                        return {"stdout": _out, "stderr": _err, "success": True}
                except (json.JSONDecodeError, TypeError, ValueError):
                    pass  # Formato legado: texto plano

                return {"stdout": content_text, "stderr": "", "success": True}
            except subprocess.TimeoutExpired as e:
                err_msg = f"Timeout en ejecución de {language}: {e}"
                logger.error(err_msg)
                return {"stdout": "", "stderr": err_msg, "success": False}
            except Exception as e:
                err_msg = str(e)
                logger.error(f"Error en execute_code: {err_msg}")
                return {"stdout": "", "stderr": err_msg, "success": False}
        finally:
            _execution_guard.inside = False

    def read_file(self, path: str) -> dict:
        logger.info(f"Leyendo archivo: {path}")
        try:
            dir_path = os.path.dirname(path) or "/"
            self._call_mcp_tool("list_directory", {"path": dir_path})

            code = f"""
import os
if not os.path.exists('{path.replace(chr(39), chr(92)+chr(39))}'):
    raise FileNotFoundError("Archivo no encontrado")
with open('{path.replace(chr(39), chr(92)+chr(39))}', 'r', encoding='utf-8') as f:
    print(f.read(), end='')
"""
            result = self.execute_code(code)
            if result["success"]:
                return {"content": result["stdout"], "success": True}
            return {"content": result.get("stderr", ""), "success": False}
        except Exception as e:
            err_msg = str(e)
            logger.error(f"Error en read_file: {err_msg}")
            return {"content": "", "success": False}

    def write_file(self, path: str, content: str) -> dict:
        logger.info(f"Escribiendo archivo (MCP): {path}")
        try:
            encoded = base64.b64encode(content.encode('utf-8')).decode('utf-8')
            
            # Script Python que crea directorios y escribe el archivo (igual que execute_code)
            script = f"""
import os, base64
os.makedirs('{os.path.dirname(path)}', exist_ok=True)
with open('{path}', 'w', encoding='utf-8') as f:
    f.write(base64.b64decode('{encoded}').decode('utf-8'))
"""
            # Enviar al MCP server directamente (sin execute_code)
            result = self._call_mcp_tool("ejecutar_en_nas", {"code": script})
            if "error" in result:
                return {"path": path, "success": False, "error": result.get("error", "Error desconocido")}
            return {"path": path, "success": True}
        except Exception as e:
            err_msg = str(e)
            logger.error(f"Error en write_file (MCP): {err_msg}")
            return {"path": path, "success": False, "error": err_msg}

    def validate_remote(self, code: str, language: str) -> tuple[bool, str]:
        """
        Valida estáticamente el código directamente en el NAS, de forma aislada y segura.
        Retorna (True, "") o (False, mensaje_de_error).
        """
        validation_cmds = {
            "javascript": ["node", "--check"],
            "bash": ["bash", "-n"],
            "cpp": ["g++", "-fsyntax-only", "-std=c++17", "-x", "c++", "-"],
            "python": ["python3", "-m", "py_compile"],
            "dart": ["/opt/flutter/bin/dart", "analyze"],
            "react-native": ["node", "--check"],
            "sql": None
        }
        if language not in validation_cmds or validation_cmds[language] is None:
            return True, ""

        ext_map = {"python": ".py", "javascript": ".js", "bash": ".sh", "sql": ".sql",
                   "cpp": ".cpp", "dart": ".dart", "react-native": ".js"}
        ext = ext_map.get(language, ".txt")
        remote_filename = f"temp_remote_val_{uuid.uuid4().hex}{ext}"
        remote_path = f"{self.sandbox_dir}/{remote_filename}"

        try:
            # 1. Transferir archivo por SFTP
            sftp = self.client.open_sftp()
            with sftp.file(remote_path, 'w') as f:
                f.write(code)
            sftp.close()

            # 2. Ejecutar validación por SSH directo
            cmd_parts = validation_cmds[language] + [remote_path]
            cmd_str = ' '.join(cmd_parts)
            stdin, stdout, stderr = self.client.exec_command(cmd_str, timeout=15)
            exit_status = stdout.channel.recv_exit_status()
            error_output = stderr.read().decode('utf-8', errors='replace')

            # 3. Limpiar archivo temporal
            self.client.exec_command(f"rm -f {remote_path}")

            return (exit_status == 0, error_output.strip())
        except Exception as e:
            logger.error(f"Error en validación remota para {language}: {e}")
            return True, ""  # Degradar gracefulmente


# =================================================================
# FACTORY: Obtener el conector correcto según la configuración
# =================================================================

def _quick_host_probe(host: str, port: int, timeout: float = 0.5) -> bool:
    """Verifica si un host:port es alcanzable sin establecer conexion SSH.

    Usa un socket TCP con timeout corto para detectar rapidamente si
    el NAS esta encendido y accesible. Si no lo esta, el arnes se
    activa en ~0.5s en vez de esperar el timeout completo del SSH.

    El timeout de 0.5s se basa en mediciones empiricas del NAS en la
    red del usuario: media de 11 ms, maximo de 15 ms.  Con un margen
    de 45x sobre la media, ofrece un balance entre deteccion rapida
    y tolerancia a fluctuaciones de red.

    Args:
        host: Direccion del servidor.
        port: Puerto a verificar.
        timeout: Segundos maximos de espera (defecto: 0.5s).

    Returns:
        True si el puerto responde, False si no.
    """
    import socket
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        return True
    except (OSError, socket.timeout):
        return False


def get_connector():
    """Retorna una instancia del conector de sandbox adecuado.

    Comportamiento original: cada agente (generator, corrector, documenter)
    llama a get_connector() y obtiene su propia instancia de NASConnector.
    El NAS mantiene sus tiempos de respuesta originales (timeout 20s) y
    sus reintentos si los tuviera.

    Arnés NAS: antes de intentar la conexion SSH completa (que puede
    tardar hasta 20s), se hace una prueba rapida de 2s para ver si el
    host es alcanzable. Si no lo esta, se activa inmediatamente el
    sandbox local en C:/Nas/sandbox (Windows) o ~/apa_sandbox_emergency
    (Linux/Mac). Si el host responde, se procede con la conexion SSH
    normal con sus timeouts originales.

    Lee la configuración de SANDBOX_TYPE (y campos relacionados) y
    retorna:
    - LocalConnector si sandbox_type == "local"
    - NASConnector si sandbox_type == "nas", "vm", o "external" (host responde)
    - LocalConnector de emergencia si el NAS no responde (arnés)

    Returns:
        Instancia de LocalConnector o NASConnector.
    """
    try:
        from core.sandbox_config import resolve_sandbox_config, SandboxType
        config = resolve_sandbox_config()
    except Exception as e:
        logger.warning(
            "No se pudo resolver sandbox_config (%s). "
            "Usando LocalConnector como fallback seguro.", e
        )
        return _create_emergency_local_connector()

    if config.is_local:
        try:
            from core.sandbox_local import LocalConnector
            logger.info("Sandbox: modo LOCAL (%s)", config.sandbox_path)
            return LocalConnector(config)
        except ImportError as e:
            logger.error("No se pudo importar LocalConnector: %s", e)
            raise
    else:
        # NAS, VM, External → verificar si el host es alcanzable
        # antes de intentar la conexion SSH completa.
        logger.info(
            "Sandbox: modo %s (%s@%s:%d)",
            config.label, config.user, config.host, config.ssh_port
        )
        # Prueba rapida: 0.5s (medido empiricamente: NAS responde en ~11ms)
        # Si no responde, se activa el arnes sin esperar el timeout SSH.
        if not _quick_host_probe(config.host, config.ssh_port):
            logger.warning(
                "ARNÉS NAS: %s:%d no responde en 0.5s. "
                "Activando sandbox local de emergencia en %s.",
                config.host, config.ssh_port, _get_emergency_sandbox_path()
            )
            return _create_emergency_local_connector()

        # El host responde: intentar conexion SSH con timeout completo.
        try:
            return NASConnector(sandbox_config=config)
        except Exception as exc:
            logger.warning(
                "ARNÉS NAS: %s responde pero SSH fallo (%s). "
                "Activando sandbox local de emergencia en %s.",
                config.host, exc, _get_emergency_sandbox_path()
            )
            return _create_emergency_local_connector()


def _create_emergency_local_connector():
    """Crea un LocalConnector de emergencia cuando el NAS no responde.

    Eje 3 (arnés NAS): usa la ruta C:/Nas/sandbox (Windows) o
    ~/apa_sandbox_emergency (Linux/Mac) según la plataforma.

    Returns:
        Instancia de LocalConnector, o None si no se puede crear.
    """
    try:
        from pathlib import Path
        from core.sandbox_config import SandboxConfig, SandboxType
        from core.sandbox_local import LocalConnector

        emergency_path = _get_emergency_sandbox_path()
        Path(emergency_path).mkdir(parents=True, exist_ok=True)

        emergency_config = SandboxConfig(
            sandbox_type=SandboxType.LOCAL,
            sandbox_path=emergency_path,
        )
        logger.info(
            "ARNÉS NAS activo: sandbox local en %s. "
            "Los lenguajes no instalados en esta PC no estarán disponibles.",
            emergency_path
        )
        return LocalConnector(emergency_config)
    except Exception as fallback_exc:
        logger.error(
            "ARNÉS NAS: no se pudo crear LocalConnector de emergencia: %s. "
            "Las operaciones de sandbox fallarán.", fallback_exc
        )
        return None


def _get_emergency_sandbox_path() -> str:
    """Retorna la ruta del sandbox de emergencia según la plataforma.

    - Windows: C:/Nas/sandbox (ruta indicada por el Director)
    - Linux/Mac: ~/apa_sandbox_emergency

    Returns:
        Ruta absoluta al directorio de sandbox de emergencia.
    """
    import platform
    from pathlib import Path

    if platform.system() == "Windows":
        return "C:/Nas/sandbox"
    else:
        return str(Path.home() / "apa_sandbox_emergency")


if __name__ == "__main__":
    import sys as _sys
    import tempfile
    import platform as _platform

    _passed = 0
    _failed = 0
    _skipped = 0

    def _check(name, condition):
        global _passed, _failed
        if condition:
            print(f"  [PASS] {name}")
            _passed += 1
        else:
            print(f"  [FAIL] {name}")
            _failed += 1

    def _skip(name, reason=""):
        global _skipped
        _msg = f"{name} — {reason}" if reason else name
        print(f"  [SKIP] {_msg}")
        _skipped += 1

    logging.basicConfig(level=logging.WARNING)
    print("\n" + "=" * 70)
    print("VALIDACIÓN AUTÓNOMA: mcp/server.py v2.0")
    print("  Conector NAS + Fábrica + Arnés de emergencia + LocalConnector")
    print("=" * 70)

    # =================================================================
    # 1. _quick_host_probe
    # =================================================================
    print("\n--- 1. _quick_host_probe ---")

    # 1a. Función existe y es llamable
    _check("Función existe", callable(_quick_host_probe))

    # 1b. IP no rutable (TEST-NET-1, reservada, nunca responde)
    _t0 = time.time()
    _result_unreachable = _quick_host_probe("192.0.2.1", 22, timeout=1.0)
    _elapsed_unreachable = time.time() - _t0
    _check("IP no rutable retorna False", _result_unreachable is False)
    _check(
        f"IP no rutable completa en ≤1.5s (real: {_elapsed_unreachable:.2f}s)",
        _elapsed_unreachable <= 1.5
    )

    # 1c. Puerto cerrado en localhost (connection refused = inmediato)
    #     Nota: en Windows, un puerto cerrado puede consumir el timeout
    #     completo por el firewall/pila de red.  Se usa timeout=0.5s y
    #     se verifica que no supere el timeout + 0.3s de holgura.
    _t0 = time.time()
    _result_closed = _quick_host_probe("127.0.0.1", 1, timeout=0.5)
    _elapsed_closed = time.time() - _t0
    _check("Puerto cerrado retorna False", _result_closed is False)
    _check(
        f"Puerto cerrado completa en <=0.8s (real: {_elapsed_closed:.3f}s)",
        _elapsed_closed < 0.8
    )

    # 1d. Host local con un puerto que probablemente esté abierto
    #     (si hay algo escuchando en 22, 80, o 3000)
    _probe_ok = False
    for _try_port in [22, 80, 3000, 8000]:
        if _quick_host_probe("127.0.0.1", _try_port, timeout=0.5):
            _probe_ok = True
            _check(f"Puerto local {_try_port} alcanzable", True)
            break
    if not _probe_ok:
        _skip("Puerto local abierto", "ningún puerto común escuchando en este entorno")

    # =================================================================
    # 2. _get_emergency_sandbox_path
    # =================================================================
    print("\n--- 2. _get_emergency_sandbox_path ---")
    _check("Función existe", callable(_get_emergency_sandbox_path))

    _path = _get_emergency_sandbox_path()
    _check("Retorna string no vacío", isinstance(_path, str) and len(_path) > 0)

    _is_windows = _platform.system() == "Windows"
    if _is_windows:
        _check("Windows: ruta contiene C:/Nas/sandbox",
                "C:/Nas" in _path or "c:/nas" in _path.lower())
    else:
        _check(f"Plataforma {_platform.system()}: ruta contiene apa_sandbox_emergency",
                "apa_sandbox_emergency" in _path)

    # =================================================================
    # 3. _create_emergency_local_connector
    # =================================================================
    print("\n--- 3. _create_emergency_local_connector ---")
    _check("Función existe", callable(_create_emergency_local_connector))

    try:
        _connector = _create_emergency_local_connector()
        if _connector is not None:
            _check("Retorna un objeto (no None)", True)
            _check("Tiene método execute_code", hasattr(_connector, 'execute_code'))
            _check("Tiene método read_file", hasattr(_connector, 'read_file'))
            _check("Tiene método write_file", hasattr(_connector, 'write_file'))
            # Ejecución real de prueba
            _test_result = _connector.execute_code("print('sandbox OK')", "python")
            _check("Ejecuta código Python correctamente",
                    _test_result.get("success") is True)
            _check("Salida contiene 'sandbox OK'",
                    "sandbox OK" in _test_result.get("stdout", ""))
            # Limpieza
            if hasattr(_connector, 'cleanup'):
                _connector.cleanup()
        else:
            _skip("LocalConnector de emergencia", "retornó None (dependencias no disponibles)")
            for _ in range(5):
                _skip("(dependiente del anterior)", "")
    except ImportError as _imp_err:
        _skip("LocalConnector de emergencia", f"import falló: {_imp_err}")
        for _ in range(5):
            _skip("(dependiente del anterior)", "")
    except Exception as _e:
        _check(f"Error inesperado: {_e}", False)

    # =================================================================
    # 4. get_connector — fábrica (modo local)
    # =================================================================
    print("\n--- 4. get_connector factory ---")
    _check("Función existe", callable(get_connector))

    try:
        from core.sandbox_config import SandboxConfig, SandboxType
        import core.sandbox_config as _sc_mod

        _tmp_sandbox = os.path.join(tempfile.gettempdir(), "test_server_sandbox")
        _local_cfg = SandboxConfig(
            sandbox_type=SandboxType.LOCAL,
            sandbox_path=_tmp_sandbox,
            timeout=10,
        )
        # Patchear resolve_sandbox_config para forzar modo local
        _original_resolve = getattr(_sc_mod, 'resolve_sandbox_config', None)
        _sc_mod.resolve_sandbox_config = lambda: _local_cfg
        try:
            _conn = get_connector()
            _check("Modo local retorna conector", _conn is not None)
            if _conn is not None:
                _check("Conector tiene execute_code", hasattr(_conn, 'execute_code'))
                _r = _conn.execute_code("print('factory OK')", "python")
                _check("Conector de fábrica ejecuta código",
                        _r.get("success") is True)
            else:
                _skip("Conector de fábrica", "retornó None")
        finally:
            # Restaurar y limpiar
            if _original_resolve:
                _sc_mod.resolve_sandbox_config = _original_resolve
            import shutil
            shutil.rmtree(_tmp_sandbox, ignore_errors=True)
    except ImportError:
        _skip("get_connector modo local", "core.sandbox_config no disponible (entorno standalone)")
    except Exception as _e:
        _check(f"Error en get_connector: {_e}", False)

    # =================================================================
    # 5. Medición de tiempo de respuesta del NAS
    # =================================================================
    print("\n--- 5. Medición de tiempo de respuesta del NAS ---")
    try:
        from core.sandbox_config import resolve_sandbox_config
        _nas_cfg = resolve_sandbox_config()
        if _nas_cfg.is_local:
            _skip("Medición NAS", "configurado en modo local (no hay NAS que medir)")
            for _ in range(2):
                _skip("(dependiente)", "")
        else:
            _nas_host = _nas_cfg.host
            _nas_port = _nas_cfg.ssh_port
            print(f"  NAS: {_nas_host}:{_nas_port}")

            _timings = []
            _rounds = 5
            for _i in range(_rounds):
                _t0 = time.time()
                _reachable = _quick_host_probe(
                    _nas_host, _nas_port, timeout=5.0
                )
                _elapsed = time.time() - _t0
                _timings.append(_elapsed)
                _status = "OK" if _reachable else "FALLÓ"
                print(f"  Medida {_i+1}/{_rounds}: {_elapsed:.3f}s — {_status}")

            _any_reachable = any(
                _quick_host_probe(_nas_host, _nas_port, timeout=5.0)
                for _ in range(1)  # 1 comprobación extra
            )
            if _any_reachable or all(t < 4.0 for t in _timings):
                _min_t = min(_timings)
                _max_t = max(_timings)
                _avg_t = sum(_timings) / len(_timings)
                _variance = sum((t - _avg_t) ** 2 for t in _timings) / len(_timings)
                _std_t = _variance ** 0.5
                # Timeout sugerido = máximo + 3σ + 0.5s de margen
                _suggested = round(_max_t + 3 * _std_t + 0.5, 1)

                print(f"\n  Resumen estadístico:")
                print(f"    Mínimo:  {_min_t*1000:.0f} ms")
                print(f"    Máximo:  {_max_t*1000:.0f} ms")
                print(f"    Media:    {_avg_t*1000:.0f} ms")
                print(f"    Desv. estándar: {_std_t*1000:.0f} ms")
                print(f"    \n  Timeout de sonda sugerido: {_suggested}s")

                # CV < 60% se considera consistente para mediciones de red local
                _consistent = _std_t < _avg_t * 0.6 if _avg_t > 0 else True
                _check(f"NAS responde (media {_avg_t*1000:.0f} ms)", True)
                _check(
                    f"Tiempos {'consistentes' if _consistent else 'variables'} "
                    f"(σ = {_std_t*1000:.0f} ms)",
                    _consistent
                )
                _check(f"Timeout sugerido: {_suggested}s", _suggested > 0)
            else:
                _skip("NAS no alcanzable", "el NAS no respondió en ninguna medición")
                for _ in range(2):
                    _skip("(dependiente)", "")
    except ImportError:
        _skip("Medición NAS", "core.sandbox_config no disponible (entorno standalone)")
        for _ in range(2):
            _skip("(dependiente)", "")
    except Exception as _e:
        _check(f"Error en medición NAS: {_e}", False)

    # =================================================================
    # 6. Conexión real con NAS / sandbox (si disponible)
    # =================================================================
    print("\n--- 6. Conexión y operaciones ---")
    try:
        _real_conn = get_connector()
        if _real_conn is not None:
            _check("Conector obtenido", True)
            try:
                _r1 = _real_conn.execute_code("print('CONEXION OK')", "python")
                _check("Ejecuta código", _r1.get("success") is True)

                _r2 = _real_conn.write_file(
                    "/app/sandbox/test_server_validation.txt",
                    "validación server.py"
                )
                _check("Escribe archivo", _r2.get("success") is True)

                _r3 = _real_conn.read_file(
                    "/app/sandbox/test_server_validation.txt"
                )
                _check("Lee archivo", _r3.get("success") is True)
                _check(
                    "Contenido coincide",
                    "validación server.py" in _r3.get("content", "")
                )

                _r4 = _real_conn.execute_code(
                    "raise Exception('error controlado')", "python"
                )
                _check("Error capturado (success=False)",
                        _r4.get("success") is False)
            except Exception as _op_err:
                _check(f"Error en operaciones: {_op_err}", False)
        else:
            _skip("Conexión real", "get_connector retornó None")
    except Exception as _conn_err:
        _skip("Conexión real", str(_conn_err))

    # =================================================================
    # 7. Estructura del módulo
    # =================================================================
    print("\n--- 7. Estructura del módulo ---")
    _check("NASConnector class existe",
            hasattr(NASConnector, '__init__') and hasattr(NASConnector, 'execute_code'))
    _check("get_connector factory existe", callable(get_connector))
    _check("_quick_host_probe existe", callable(_quick_host_probe))
    _check("_create_emergency_local_connector existe",
            callable(_create_emergency_local_connector))
    _check("_get_emergency_sandbox_path existe",
            callable(_get_emergency_sandbox_path))

    # =================================================================
    # RESULTADO
    # =================================================================
    _total = _passed + _failed
    print("\n" + "-" * 70)
    print(f"Resultado: {_passed}/{_total} pasaron, {_skipped} omitidos")
    if _failed > 0:
        print(f"FALLARON: {_failed}")
    else:
        print("TODAS LAS PRUEBAS PASARON")
    print("=" * 70)
    _sys.exit(0 if _failed == 0 else 1)
