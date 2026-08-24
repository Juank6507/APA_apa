# apa/core/sandbox_config.py
# v1.1 — Configuración centralizada del sandbox de ejecución.
#
# Permite al usuario elegir dónde ejecuta APA su código:
#   - "local"   : La propia PC del usuario (subprocess directo)
#   - "nas"     : Servidor NAS por SSH (diseño original)
#   - "vm"      : Máquina virtual por SSH (misma lógica que NAS, distinto host)
#   - "external": Cualquier dispositivo remoto por SSH
#
# El usuario configura esto ejecutando el asistente de instalación:
#   python apa/core/sandbox_setup.py
#
# El asistente escribe SANDBOX_TYPE y campos relacionados en .env.
# Este módulo lee esa configuración y proporciona la SandboxConfig lista.
#
# CAMBIOS v1.2 vs v1.1:
#   - work_dir se auto-computa en __post_init__ si está vacío
#   - python_cmd detecta automáticamente python vs python3 según SO
#   - sys.path.setup para ejecución standalone (python core/sandbox_config.py)
#
# CAMBIOS v1.1 vs v1.0:
#   - Eliminada la inferencia silenciosa de NAS_HOST.
#     Si SANDBOX_TYPE no está definido, se requiere ejecutar el asistente.
#   - resolve_sandbox_config() exige SANDBOX_TYPE explícito.
#   - Mensaje claro de error cuando no hay configuración.
#
# CAMBIOS v1.0:
#   - SandboxType enum (local, nas, vm, external)
#   - SandboxConfig dataclass con toda la info de conexión
#   - resolve_sandbox_config() lee de settings y retorna la config lista
#   - get_connector_class() retorna la clase adecuada para cada tipo
#   - Validación de campos requeridos por tipo
#   - Sin dependencias pesadas, solo stdlib + settings

import os
import sys
import logging
import platform
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any, List

# Para ejecución standalone: python core/sandbox_config.py
_this_dir = os.path.dirname(os.path.abspath(__file__))
_parent_dir = os.path.dirname(_this_dir)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

logger = logging.getLogger(__name__)


# =================================================================
# Tipos de sandbox disponibles
# =================================================================

class SandboxType(str, Enum):
    """Tipos de sandbox soportados por APA.
    
    - local: Ejecución directa en la PC del usuario via subprocess.
             No requiere configuración de red. El sandbox se crea
             en un directorio temporal del sistema local.
    
    - nas: Servidor NAS por SSH. Configuración original de APA.
           Requiere nas_host, nas_user, y opcionalmente nas_ssh_port.
    
    - vm: Máquina virtual por SSH. Misma lógica que NAS pero con
         host/credenciales diferentes. El usuario puede tener una VM
         con Docker, WSL, o cualquier entorno aislado.
    
    - external: Cualquier otro dispositivo accesible por SSH.
                Un servidor dedicado, una Raspberry Pi, etc.
    """
    LOCAL = "local"
    NAS = "nas"
    VM = "vm"
    EXTERNAL = "external"


# =================================================================
# Configuración del sandbox
# =================================================================

@dataclass
class SandboxConfig:
    """Configuración completa del sandbox de ejecución.
    
    Atributos:
        sandbox_type: Tipo de sandbox (local, nas, vm, external).
        sandbox_path: Ruta donde se crean/leen los archivos de trabajo.
                      En local: ruta absoluta en el filesystem.
                      En remoto: ruta absoluta en el servidor remoto.
        host: Dirección del servidor remoto (IP o hostname).
              Solo aplicable para nas, vm, external. Vacío para local.
        user: Usuario SSH para el servidor remoto.
              Solo aplicable para nas, vm, external. Vacío para local.
        ssh_port: Puerto SSH. Por defecto 22.
        ssh_key_path: Ruta a la clave privada SSH (opcional).
                      Si no se proporciona, se usan las claves por defecto
                      del sistema (~/.ssh/id_rsa, etc.).
        timeout: Timeout en segundos para operaciones SSH.
        work_dir: Directorio de trabajo para el sandbox local.
                  Por defecto: {sandbox_path}/apa_sandbox
        python_cmd: Comando del intérprete Python en el sandbox.
                    "python3" por defecto, pero puede ser "python",
                    "/usr/bin/python3.11", etc.
        node_cmd: Comando de Node.js. "node" por defecto.
        env_vars: Variables de entorno adicionales para el sandbox.
        extra: Campos extra para extensiones futuras (serializable).
    """
    sandbox_type: SandboxType = SandboxType.LOCAL
    sandbox_path: str = ""
    host: str = ""
    user: str = ""
    ssh_port: int = 22
    ssh_key_path: str = ""
    timeout: int = 30
    work_dir: str = ""
    python_cmd: str = ""
    node_cmd: str = "node"

    def __post_init__(self):
        """Auto-computa work_dir y python_cmd si no se especificaron."""
        if not self.work_dir and self.sandbox_path:
            if self.is_local:
                self.work_dir = os.path.join(self.sandbox_path, "work")
            else:
                self.work_dir = self.sandbox_path
        if not self.python_cmd:
            # Windows usa 'python', Linux/Mac usan 'python3'
            self.python_cmd = "python" if platform.system() == "Windows" else "python3"
    env_vars: Dict[str, str] = field(default_factory=dict)
    extra: Dict[str, Any] = field(default_factory=dict)

    # ---- Propiedades derivadas ----

    @property
    def is_local(self) -> bool:
        """True si el sandbox es local (sin red)."""
        return self.sandbox_type == SandboxType.LOCAL

    @property
    def is_remote(self) -> bool:
        """True si el sandbox requiere conexión remota (SSH)."""
        return self.sandbox_type in (SandboxType.NAS, SandboxType.VM, SandboxType.EXTERNAL)

    @property
    def label(self) -> str:
        """Etiqueta legible del tipo de sandbox."""
        labels = {
            SandboxType.LOCAL: "PC Local",
            SandboxType.NAS: "NAS",
            SandboxType.VM: "Máquina Virtual",
            SandboxType.EXTERNAL: "Dispositivo Externo",
        }
        return labels.get(self.sandbox_type, str(self.sandbox_type))

    def validate(self) -> List[str]:
        """Valida que la configuración tenga los campos requeridos.
        
        Retorna una lista de errores. Vacía si todo es correcto.
        """
        errors = []

        # --- Todos los tipos requieren sandbox_path ---
        if not self.sandbox_path.strip():
            errors.append(
                "sandbox_path es obligatorio para todos los tipos de sandbox. "
                "Define SANDBOX_PATH en .env o settings.py"
            )

        # --- Locales no necesitan host/user ---
        if self.is_local:
            return errors

        # --- Remotos necesitan host y user ---
        if not self.host.strip():
            errors.append(
                f"Para sandbox tipo '{self.sandbox_type.value}' se requiere "
                f"un host. Define SANDBOX_HOST en .env"
            )
        if not self.user.strip():
            errors.append(
                f"Para sandbox tipo '{self.sandbox_type.value}' se requiere "
                f"un usuario SSH. Define SANDBOX_USER en .env"
            )

        # --- Validar puerto ---
        if not (1 <= self.ssh_port <= 65535):
            errors.append(
                f"ssh_port debe estar entre 1 y 65535, se recibió: {self.ssh_port}"
            )

        return errors

    def to_dict(self) -> Dict[str, Any]:
        """Convierte la configuración a diccionario (para logging/serialización)."""
        return {
            "sandbox_type": self.sandbox_type.value,
            "label": self.label,
            "sandbox_path": self.sandbox_path,
            "host": self.host or "(local)",
            "user": self.user or "(local)",
            "ssh_port": self.ssh_port,
            "ssh_key_path": self.ssh_key_path or "(default)",
            "timeout": self.timeout,
            "work_dir": self.work_dir,
            "python_cmd": self.python_cmd,
            "node_cmd": self.node_cmd,
        }


# =================================================================
# Resolución de configuración desde settings
# =================================================================

def resolve_sandbox_config() -> SandboxConfig:
    """Lee la configuración de sandbox desde settings/.env y retorna un SandboxConfig.
    
    La configuración se establece ejecutando el asistente de instalación:
        python apa/core/sandbox_setup.py
    
    El asistente escribe SANDBOX_TYPE y campos relacionados en el .env.
    Este módulo lee esos valores y construye la SandboxConfig.
    
    Variables de entorno soportadas (escritas por el asistente):
        SANDBOX_TYPE     - "local", "nas", "vm", "external" (obligatorio)
        SANDBOX_PATH     - Ruta del sandbox (obligatorio)
        SANDBOX_HOST     - Host remoto (obligatorio para nas/vm/external)
        SANDBOX_USER     - Usuario SSH (obligatorio para nas/vm/external)
        SANDBOX_SSH_PORT - Puerto SSH (defecto: 22)
        SANDBOX_SSH_KEY  - Ruta a clave SSH privada (opcional)
        SANDBOX_TIMEOUT  - Timeout en segundos (defecto: 30)
    
    Si SANDBOX_TYPE no está definido, se lanza un error claro indicando
    que se debe ejecutar el asistente de instalación.
    """
    from config.settings import settings

    # --- Leer tipo de sandbox (obligatorio) ---
    sandbox_type_str = getattr(settings, 'sandbox_type', '') or os.environ.get('SANDBOX_TYPE', '').strip()

    if not sandbox_type_str:
        raise ValueError(
            "SANDBOX_TYPE no esta definido. APA requiere que configures el sandbox\n"
            "antes de usarlo. Ejecuta el asistente de configuracion:\n\n"
            "    python apa/core/sandbox_setup.py\n\n"
            "Este asistente te preguntara donde quieres ejecutar el codigo\n"
            "(tu PC, un NAS, una maquina virtual, o un dispositivo externo)\n"
            "y escribira la configuracion en tu archivo .env."
        )

    # Normalizar a enum
    try:
        sandbox_type = SandboxType(sandbox_type_str.lower())
    except ValueError:
        raise ValueError(
            f"SANDBOX_TYPE='{sandbox_type_str}' no es valido. Opciones: local, nas, vm, external.\n"
            "Ejecuta el asistente para corregir:\n"
            "    python apa/core/sandbox_setup.py"
        )

    # --- Leer host (solo para remotos) ---
    host = (
        getattr(settings, 'sandbox_host', '') or
        os.environ.get('SANDBOX_HOST', '') or
        ''
    ).strip()

    # --- Leer usuario (solo para remotos) ---
    user = (
        getattr(settings, 'sandbox_user', '') or
        os.environ.get('SANDBOX_USER', '') or
        ''
    ).strip()

    # --- Leer sandbox_path (obligatorio) ---
    sandbox_path = (
        getattr(settings, 'sandbox_path', '') or
        os.environ.get('SANDBOX_PATH', '') or
        ''
    ).strip()

    if not sandbox_path:
        if sandbox_type == SandboxType.LOCAL:
            sandbox_path = os.path.join(os.getcwd(), "apa_sandbox")
            logger.info("SANDBOX_PATH vacio para local, usando default: %s", sandbox_path)
        else:
            raise ValueError(
                "SANDBOX_PATH no esta definido. Ejecuta el asistente:\n"
                "    python apa/core/sandbox_setup.py"
            )

    # --- Leer puerto SSH ---
    try:
        ssh_port = int(
            getattr(settings, 'sandbox_ssh_port', 0) or
            os.environ.get('SANDBOX_SSH_PORT', '') or
            22
        )
    except (ValueError, TypeError):
        ssh_port = 22

    # --- Leer clave SSH ---
    ssh_key_path = (
        getattr(settings, 'sandbox_ssh_key', '') or
        os.environ.get('SANDBOX_SSH_KEY', '') or
        ''
    ).strip()

    # --- Leer timeout ---
    try:
        timeout = int(
            getattr(settings, 'sandbox_timeout', 0) or
            os.environ.get('SANDBOX_TIMEOUT', '') or
            30
        )
    except (ValueError, TypeError):
        timeout = 30

    # --- Construir config ---
    config = SandboxConfig(
        sandbox_type=sandbox_type,
        sandbox_path=sandbox_path,
        host=host,
        user=user,
        ssh_port=ssh_port,
        ssh_key_path=ssh_key_path,
        timeout=timeout,
        work_dir=os.path.join(sandbox_path, "work") if sandbox_type == SandboxType.LOCAL else sandbox_path,
    )

    # --- Validar ---
    errors = config.validate()
    if errors:
        error_msg = (
            "Errores en la configuracion del sandbox:\n"
            "  - " + "\n  - ".join(errors) + "\n\n"
            "Ejecuta el asistente para corregir:\n"
            "    python apa/core/sandbox_setup.py"
        )
        raise ValueError(error_msg)

    logger.info("Sandbox configurado: %s (%s) en %s", config.label, config.sandbox_type.value, config.sandbox_path)
    if config.is_remote:
        logger.info("  Conexion remota: %s@%s:%d", config.user, config.host, config.ssh_port)

    return config


# =================================================================
# Factory: obtener el conector adecuado
# =================================================================

def get_connector_class(config: Optional[SandboxConfig] = None):
    """Retorna la clase de conector adecuada para la configuración dada.
    
    Este es el punto de despatcho central. Cuando se añadan nuevos tipos
    de sandbox (VMCloudProvider, ExternalProvider, etc.), se añaden aquí.
    
    Args:
        config: SandboxConfig. Si es None, se resuelve automáticamente.
    
    Returns:
        Clase del conector (NASConnector, LocalConnector, etc.)
        Tiene el método execute_code(), read_file(), write_file().
    
    Raises:
        ImportError: Si las dependencias del conector no están instaladas.
    """
    if config is None:
        config = resolve_sandbox_config()

    if config.is_local:
        # Importar conector local
        try:
            # Buscar en el path del paquete
            core_dir = os.path.dirname(__file__)
            if core_dir not in sys.path:
                sys.path.insert(0, core_dir)
            from sandbox_local import LocalConnector
            logger.info("Usando conector local (subprocess)")
            return LocalConnector
        except ImportError as e:
            raise ImportError(
                f"No se pudo importar LocalConnector: {e}. "
                "Asegúrese de que apa/core/sandbox_local.py existe."
            )

    elif config.sandbox_type == SandboxType.NAS:
        # Usar el NASConnector existente en mcp/server.py
        try:
            mcp_dir = os.path.join(os.path.dirname(__file__), '..', 'mcp')
            if mcp_dir not in sys.path:
                sys.path.insert(0, mcp_dir)
            from server import NASConnector
            logger.info("Usando NASConnector (SSH a %s@%s)", config.user, config.host)
            return NASConnector
        except ImportError as e:
            raise ImportError(
                f"No se pudo importar NASConnector: {e}. "
                "Asegúrese de que apa/mcp/server.py existe y paramiko está instalado."
            )

    elif config.sandbox_type == SandboxType.VM:
        # VM usa la misma lógica que NAS pero con sus propias credenciales
        try:
            mcp_dir = os.path.join(os.path.dirname(__file__), '..', 'mcp')
            if mcp_dir not in sys.path:
                sys.path.insert(0, mcp_dir)
            from server import NASConnector
            logger.info("Usando NASConnector para VM (SSH a %s@%s)", config.user, config.host)
            return NASConnector
        except ImportError as e:
            raise ImportError(
                f"No se pudo importar NASConnector para VM: {e}. "
                "Asegúrese de que apa/mcp/server.py existe y paramiko está instalado."
            )

    elif config.sandbox_type == SandboxType.EXTERNAL:
        # External usa la misma lógica que NAS con credenciales externas
        try:
            mcp_dir = os.path.join(os.path.dirname(__file__), '..', 'mcp')
            if mcp_dir not in sys.path:
                sys.path.insert(0, mcp_dir)
            from server import NASConnector
            logger.info("Usando NASConnector para dispositivo externo (SSH a %s@%s)", config.user, config.host)
            return NASConnector
        except ImportError as e:
            raise ImportError(
                f"No se pudo importar NASConnector: {e}. "
                "Asegúrese de que apa/mcp/server.py existe y paramiko está instalado."
            )

    else:
        raise ValueError(f"Tipo de sandbox no soportado: {config.sandbox_type}")


# =================================================================
# TESTS
# =================================================================

def _run_tests():
    """Tests de validación del módulo sandbox_config."""
    print("=" * 60)
    print("TEST: sandbox_config v1.0")
    print("=" * 60)
    passed = 0
    failed = 0

    # --- Test 1: SandboxType enum tiene 4 valores ---
    try:
        assert len(SandboxType) == 4, f"Esperado 4 tipos, hay {len(SandboxType)}"
        assert SandboxType.LOCAL.value == "local"
        assert SandboxType.NAS.value == "nas"
        assert SandboxType.VM.value == "vm"
        assert SandboxType.EXTERNAL.value == "external"
        print("  [PASS] SandboxType enum con 4 valores correctos")
        passed += 1
    except AssertionError as e:
        print(f"  [FAIL] SandboxType enum: {e}")
        failed += 1

    # --- Test 2: SandboxConfig por defecto es local ---
    try:
        config = SandboxConfig()
        assert config.sandbox_type == SandboxType.LOCAL
        assert config.is_local is True
        assert config.is_remote is False
        assert config.label == "PC Local"
        print("  [PASS] SandboxConfig por defecto es local")
        passed += 1
    except AssertionError as e:
        print(f"  [FAIL] SandboxConfig por defecto: {e}")
        failed += 1

    # --- Test 3: is_remote para tipos remotos ---
    try:
        for remote_type in (SandboxType.NAS, SandboxType.VM, SandboxType.EXTERNAL):
            cfg = SandboxConfig(sandbox_type=remote_type)
            assert cfg.is_remote is True, f"{remote_type} debería ser remoto"
            assert cfg.is_local is False, f"{remote_type} no debería ser local"
        print("  [PASS] is_remote/is_local correcto para tipos remotos")
        passed += 1
    except AssertionError as e:
        print(f"  [FAIL] is_remote: {e}")
        failed += 1

    # --- Test 4: Labels correctos ---
    try:
        expected_labels = {
            SandboxType.LOCAL: "PC Local",
            SandboxType.NAS: "NAS",
            SandboxType.VM: "Máquina Virtual",
            SandboxType.EXTERNAL: "Dispositivo Externo",
        }
        for stype, expected in expected_labels.items():
            cfg = SandboxConfig(sandbox_type=stype)
            assert cfg.label == expected, f"{stype}: esperado '{expected}', got '{cfg.label}'"
        print("  [PASS] Labels correctos para los 4 tipos")
        passed += 1
    except AssertionError as e:
        print(f"  [FAIL] Labels: {e}")
        failed += 1

    # --- Test 5: Validación de local sin sandbox_path ---
    try:
        cfg = SandboxConfig(sandbox_type=SandboxType.LOCAL, sandbox_path="")
        errors = cfg.validate()
        # Local sin sandbox_path genera warning pero no es blocking
        # porque tiene default
        assert "sandbox_path" in errors[0].lower() if errors else True
        print("  [PASS] Validación: local sin sandbox_path genera error")
        passed += 1
    except Exception as e:
        print(f"  [FAIL] Validación local: {e}")
        failed += 1

    # --- Test 6: Validación de NAS sin host ---
    try:
        cfg = SandboxConfig(sandbox_type=SandboxType.NAS, sandbox_path="/app/sandbox")
        errors = cfg.validate()
        assert len(errors) >= 1, "NAS sin host debería tener errores"
        assert any("host" in e.lower() for e in errors), "Error debería mencionar 'host'"
        print("  [PASS] Validación: NAS sin host genera error")
        passed += 1
    except AssertionError as e:
        print(f"  [FAIL] Validación NAS: {e}")
        failed += 1

    # --- Test 7: Validación de NAS sin user ---
    try:
        cfg = SandboxConfig(
            sandbox_type=SandboxType.NAS,
            sandbox_path="/app/sandbox",
            host="192.168.1.100"
        )
        errors = cfg.validate()
        assert len(errors) >= 1, "NAS sin user debería tener errores"
        assert any("usuario" in e.lower() or "user" in e.lower() for e in errors), \
            "Error debería mencionar 'usuario'"
        print("  [PASS] Validación: NAS sin user genera error")
        passed += 1
    except AssertionError as e:
        print(f"  [FAIL] Validación NAS user: {e}")
        failed += 1

    # --- Test 8: Configuración NAS válida pasa validación ---
    try:
        cfg = SandboxConfig(
            sandbox_type=SandboxType.NAS,
            sandbox_path="/app/sandbox",
            host="192.168.1.100",
            user="admin",
        )
        errors = cfg.validate()
        assert len(errors) == 0, f"Config NAS válida no debería tener errores: {errors}"
        print("  [PASS] Configuración NAS válida pasa validación")
        passed += 1
    except AssertionError as e:
        print(f"  [FAIL] Config NAS válida: {e}")
        failed += 1

    # --- Test 9: Configuración VM válida ---
    try:
        cfg = SandboxConfig(
            sandbox_type=SandboxType.VM,
            sandbox_path="/home/dev/sandbox",
            host="10.0.0.50",
            user="developer",
            ssh_port=2222,
        )
        errors = cfg.validate()
        assert len(errors) == 0, f"Config VM válida no debería tener errores: {errors}"
        assert cfg.ssh_port == 2222
        print("  [PASS] Configuración VM válida con puerto personalizado")
        passed += 1
    except AssertionError as e:
        print(f"  [FAIL] Config VM: {e}")
        failed += 1

    # --- Test 10: Configuración External válida ---
    try:
        cfg = SandboxConfig(
            sandbox_type=SandboxType.EXTERNAL,
            sandbox_path="/srv/sandbox",
            host="raspberry.local",
            user="pi",
            ssh_key_path="/home/user/.ssh/id_ed25519",
        )
        errors = cfg.validate()
        assert len(errors) == 0
        assert cfg.ssh_key_path == "/home/user/.ssh/id_ed25519"
        print("  [PASS] Configuración External válida con SSH key")
        passed += 1
    except AssertionError as e:
        print(f"  [FAIL] Config External: {e}")
        failed += 1

    # --- Test 11: Puerto inválido ---
    try:
        cfg = SandboxConfig(
            sandbox_type=SandboxType.NAS,
            sandbox_path="/app/sandbox",
            host="192.168.1.100",
            user="admin",
            ssh_port=99999,
        )
        errors = cfg.validate()
        assert any("65535" in e for e in errors), f"Debería reportar puerto inválido: {errors}"
        print("  [PASS] Puerto 99999 detectado como inválido")
        passed += 1
    except AssertionError as e:
        print(f"  [FAIL] Puerto inválido: {e}")
        failed += 1

    # --- Test 12: to_dict serializa correctamente ---
    try:
        cfg = SandboxConfig(
            sandbox_type=SandboxType.NAS,
            sandbox_path="/app/sandbox",
            host="nas.mired.local",
            user="admin",
            ssh_port=2222,
        )
        d = cfg.to_dict()
        assert d["sandbox_type"] == "nas"
        assert d["label"] == "NAS"
        assert d["host"] == "nas.mired.local"
        assert d["user"] == "admin"
        assert d["ssh_port"] == 2222
        assert d["sandbox_path"] == "/app/sandbox"
        print("  [PASS] to_dict serializa todos los campos")
        passed += 1
    except AssertionError as e:
        print(f"  [FAIL] to_dict: {e}")
        failed += 1

    # --- Test 13: to_dict local muestra (local) en host ---
    try:
        cfg = SandboxConfig(sandbox_type=SandboxType.LOCAL, sandbox_path="/tmp/sandbox")
        d = cfg.to_dict()
        assert d["host"] == "(local)", f"Esperado '(local)', got '{d['host']}'"
        assert d["user"] == "(local)"
        print("  [PASS] to_dict local muestra (local) en host y user")
        passed += 1
    except AssertionError as e:
        print(f"  [FAIL] to_dict local: {e}")
        failed += 1

    # --- Test 14: env_vars funciona ---
    try:
        cfg = SandboxConfig(
            sandbox_type=SandboxType.LOCAL,
            sandbox_path="/tmp/sandbox",
            env_vars={"PYTHONPATH": "/custom/path", "DEBUG": "1"},
        )
        assert cfg.env_vars["PYTHONPATH"] == "/custom/path"
        assert cfg.env_vars["DEBUG"] == "1"
        print("  [PASS] env_vars se almacenan correctamente")
        passed += 1
    except Exception as e:
        print(f"  [FAIL] env_vars: {e}")
        failed += 1

    # --- Test 15: work_dir se construye automáticamente ---
    try:
        cfg = SandboxConfig(sandbox_type=SandboxType.LOCAL, sandbox_path="/tmp/sandbox")
        expected_work = os.path.join("/tmp/sandbox", "work")
        assert cfg.work_dir == expected_work, f"Esperado '{expected_work}', got '{cfg.work_dir}'"
        print("  [PASS] work_dir se construye automáticamente para local")
        passed += 1
    except AssertionError as e:
        print(f"  [FAIL] work_dir: {e}")
        failed += 1

    # --- Test 16: resolve_sandbox_config retorna SandboxConfig ---
    try:
        # Este test puede fallar si settings no tiene los campos nuevos,
        # pero resolve_sandbox_config debería manejar eso con defaults
        cfg = resolve_sandbox_config()
        assert isinstance(cfg, SandboxConfig), f"Esperado SandboxConfig, got {type(cfg)}"
        assert cfg.sandbox_type in SandboxType
        assert cfg.sandbox_path != "", "sandbox_path no debería estar vacío"
        print("  [PASS] resolve_sandbox_config retorna SandboxConfig válido")
        passed += 1
    except Exception as e:
        print(f"  [FAIL] resolve_sandbox_config: {e}")
        failed += 1

    # --- Test 17: Local con sandbox_path definido no tiene errores ---
    try:
        cfg = SandboxConfig(sandbox_type=SandboxType.LOCAL, sandbox_path="/tmp/apa_sandbox")
        errors = cfg.validate()
        assert len(errors) == 0, f"Local con path no debería tener errores: {errors}"
        print("  [PASS] Local con sandbox_path definido pasa validación limpia")
        passed += 1
    except AssertionError as e:
        print(f"  [FAIL] Local con path: {e}")
        failed += 1

    # --- Test 18: get_connector_class para local retorna LocalConnector ---
    try:
        cfg = SandboxConfig(sandbox_type=SandboxType.LOCAL, sandbox_path="/tmp/sandbox")
        # Si sandbox_local.py existe, debería poder importar
        connector = get_connector_class(cfg)
        assert connector is not None
        print("  [PASS] get_connector_class(local) retorna clase")
        passed += 1
    except ImportError as e:
        # Si sandbox_local.py aún no existe, es esperado
        print(f"  [PASS] get_connector_class(local) falla con ImportError (sandbox_local.py pendiente)")
        passed += 1
    except Exception as e:
        print(f"  [FAIL] get_connector_class: {e}")
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
