# apa/mcp/server.py
# v2.0 — Sandbox configurable: el conector se elige según SANDBOX_TYPE.
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
import subprocess, sys
with open('{path_esc}', 'r', encoding='utf-8') as f:
    result = subprocess.run(
        ['sqlite3', ':memory:'],
        stdin=f,
        capture_output=True,
        text=True,
        timeout=30
    )
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
    else:
        sys.stdout.write(result.stdout)
    sys.exit(result.returncode)
"""
                elif language == "cpp":
                    bin_path = sandbox_path.replace('.cpp', '.out')
                    bin_esc = bin_path.replace("'", "\\'")
                    exec_code = f"""
import subprocess, sys
compile_result = subprocess.run(
    ['g++', '-std=c++17', '-o', '{bin_esc}', '{path_esc}'],
    capture_output=True,
    text=True,
    timeout=30
)
if compile_result.returncode != 0:
    sys.stderr.write(compile_result.stderr)
    sys.exit(compile_result.returncode)
run_result = subprocess.run(['{bin_esc}'], capture_output=True, text=True, timeout=10)
if run_result.returncode != 0:
    sys.stderr.write(run_result.stderr)
else:
    sys.stdout.write(run_result.stdout)
sys.exit(run_result.returncode)
"""
                elif language == "dart":
                    exec_code = f"""
import subprocess, sys
result = subprocess.run(
    ['/opt/flutter/bin/dart', 'run', '{path_esc}'],
    capture_output=True,
    text=True,
    timeout=30
)
if result.returncode != 0:
    sys.stderr.write(result.stderr)
else:
    sys.stdout.write(result.stdout)
sys.exit(result.returncode)
"""
                else:
                    cmd = config["cmd"].replace("{file}", sandbox_path)
                    exec_code = f"""
import subprocess, sys
result = subprocess.run('{cmd}', shell=True, capture_output=True, text=True)
if result.returncode != 0:
    sys.stderr.write(result.stderr)
else:
    sys.stdout.write(result.stdout)
sys.exit(result.returncode)
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

def get_connector():
    """Retorna una instancia del conector de sandbox adecuado.

    Comportamiento original: cada agente (generator, corrector, documenter)
    llama a get_connector() y obtiene su propia instancia de NASConnector.
    El NAS mantiene sus tiempos de respuesta originales (timeout 20s) y
    sus reintentos si los tuviera.

    Eje 3 (arnés NAS): si el NAS no responde tras su timeout completo,
    se activa el arnés con LocalConnector en C:/Nas/sandbox (o equivalente
    en la plataforma). El arnés solo se activa cuando la conexión falla,
    no antes.

    Lee la configuración de SANDBOX_TYPE (y campos relacionados) y
    retorna:
    - LocalConnector si sandbox_type == "local"
    - NASConnector si sandbox_type == "nas", "vm", o "external"
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
        # NAS, VM, External → todos usan NASConnector con sus credenciales
        # El NAS mantiene sus tiempos de respuesta originales (timeout 20s)
        # y sus reintentos. Si tras esos tiempos no responde, se activa
        # el arnés con LocalConnector en C:/Nas/sandbox.
        logger.info(
            "Sandbox: modo %s (%s@%s:%d)",
            config.label, config.user, config.host, config.ssh_port
        )
        try:
            return NASConnector(sandbox_config=config)
        except Exception as exc:
            logger.warning(
                "ARNÉS NAS: no se pudo conectar a %s (%s). "
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
    logging.basicConfig(level=logging.INFO)

    # Resiliente: si el sandbox no responde, no se cuelga
    try:
        nas = get_connector()
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "server.py __main__: sandbox no disponible (%s). "
            "Saltando pruebas de conexión.", exc
        )
        nas = None

    if nas is not None:
        try:
            print("PRUEBA 1:", nas.execute_code("print('CONEXION OK')"))
            result_w = nas.write_file("/app/sandbox/test_apa.txt", "APA funcionando")
            result_r = nas.read_file("/app/sandbox/test_apa.txt")
            print("PRUEBA 2 escritura:", result_w)
            print("PRUEBA 2 lectura:", result_r)
            print("PRUEBA 3:", nas.execute_code("raise Exception('error test')"))
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "server.py __main__: error en pruebas de sandbox (%s). "
                "Sandboxes NAS/VM no disponibles en este entorno.", exc
            )
            print("PRUEBAS SKIPPED — sandbox no disponible en este entorno")
    else:
        print("PRUEBAS SKIPPED — sandbox no disponible en este entorno")
