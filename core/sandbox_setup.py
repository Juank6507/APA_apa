# apa/core/sandbox_setup.py
# v1.0 — Asistente de configuración del sandbox para la instalación de APA.
#
# Este script se ejecuta UNA VEZ durante la instalación de APA.
# Pregunta al usuario dónde quiere ejecutar su sandbox y escribe
# la configuración en el archivo .env.
#
# Ejecutar:
#   python apa/core/sandbox_setup.py
#
# El asistente NO adivina nada. Siempre pregunta explícitamente.
# Las opciones son:
#   1) PC Local        — subprocess directo, sin red
#   2) NAS             — servidor NAS por SSH
#   3) Máquina Virtual — VM por SSH (WSL, VirtualBox, etc.)
#   4) Dispositivo Externo — cualquier otro dispositivo por SSH
#
# También puede re-ejecutarse en cualquier momento para cambiar
# la configuración del sandbox.

import os
import sys
import platform

# Asegurar que podemos importar del paquete
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)


def _clear():
    """Limpia la terminal."""
    if platform.system() == "Windows":
        os.system('cls')
    else:
        os.system('clear')


def _banner():
    """Muestra el banner del asistente."""
    _clear()
    print()
    print("=" * 56)
    print("   APA — CONFIGURACION DEL SANDBOX")
    print("   Asistente de instalacion")
    print("=" * 56)
    print()
    print("  El sandbox es el lugar donde APA ejecuta y prueba")
    print("  el codigo que genera. Debes elegir donde se ubicara.")
    print()
    print("  OPCIONES DISPONIBLES:")
    print()
    print("    1) PC Local")
    print("       Ejecuta codigo directamente en tu PC.")
    print("       No necesita red ni configuracion extra.")
    print("       Recomendado para la mayoria de usuarios.")
    print()
    print("    2) NAS (Servidor de red)")
    print("       Un servidor NAS conectado por SSH.")
    print("       Es el diseño original de APA.")
    print()
    print("    3) Maquina Virtual (VM)")
    print("       WSL, VirtualBox, VMware, etc.")
    print("       Conectada por SSH desde tu PC.")
    print()
    print("    4) Dispositivo Externo")
    print("       Cualquier otro dispositivo con SSH:")
    print("       Raspberry Pi, servidor dedicado, etc.")
    print()
    print("  NOTA: Puedes cambiar esta configuracion en cualquier")
    print("  momento volviendo a ejecutar este asistente.")
    print()
    print("=" * 56)


def _ask(prompt, default="", required=True):
    """Pide input al usuario con valor por defecto."""
    if default:
        display = f"{prompt} [{default}]: "
    else:
        display = f"{prompt}: "
    value = input(display).strip()
    if not value and default:
        return default
    if not value and required:
        print(f"  Este campo es obligatorio.")
        return _ask(prompt, default, required)
    return value


def _ask_int(prompt, default, min_val=1, max_val=65535):
    """Pide un número entero al usuario."""
    while True:
        value = _ask(prompt, str(default))
        try:
            n = int(value)
            if min_val <= n <= max_val:
                return n
            print(f"  El valor debe estar entre {min_val} y {max_val}.")
        except ValueError:
            print(f"  Introduce un numero valido.")


def _find_env_file() -> str:
    """Busca el archivo .env y retorna su ruta absoluta."""
    candidates = [
        os.path.join(PROJECT_ROOT, ".env"),
        os.path.join(os.getcwd(), ".env"),
        os.path.join(BASE_DIR, "..", ".env"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return os.path.abspath(path)
    # Si no existe, crear en la raíz del proyecto
    default_env = os.path.join(PROJECT_ROOT, ".env")
    return default_env


def _read_existing_env(env_path: str) -> list:
    """Lee las líneas existentes del .env (sin comentarios de sandbox)."""
    lines = []
    if os.path.isfile(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    return lines


def _write_env(env_path: str, existing_lines: list, config_lines: list):
    """Escribe el .env eliminando config sandbox anterior y añadiendo la nueva."""
    # Filtrar líneas: eliminar secciones SANDBOX anteriores y campos NAS_HOST/USER
    sandbox_keys = [
        "SANDBOX_TYPE", "SANDBOX_PATH", "SANDBOX_HOST", "SANDBOX_USER",
        "SANDBOX_SSH_PORT", "SANDBOX_SSH_KEY", "SANDBOX_TIMEOUT",
        "SANDBOX_PYTHON_CMD", "SANDBOX_NODE_CMD",
    ]

    filtered = []
    skip_section = False
    for line in existing_lines:
        stripped = line.strip()

        # Detectar inicio de sección sandbox anterior
        if "SANDBOX CONFIGURABLE" in stripped or "SANDBOX — APA" in stripped:
            skip_section = True
            continue

        # Detectar fin de sección sandbox
        if skip_section and stripped.startswith("#") and "SANDBOX" not in stripped and stripped != "#":
            skip_section = False

        # Saltar líneas dentro de la sección sandbox
        if skip_section:
            continue

        # Eliminar campos sandbox individuales (pero NO otros campos)
        is_sandbox_key = False
        for key in sandbox_keys:
            if stripped.startswith(key + "=") or stripped.startswith(key + " "):
                is_sandbox_key = True
                break
        if is_sandbox_key:
            continue

        filtered.append(line)

    # Añadir nueva configuración sandbox al final
    filtered.append("\n")
    filtered.extend(config_lines)
    filtered.append("\n")

    with open(env_path, 'w', encoding='utf-8') as f:
        f.writelines(filtered)


def _generate_env_config(sandbox_type, config) -> list:
    """Genera las líneas de configuración para el .env."""
    lines = [
        "# ============================================================\n",
        "# SANDBOX CONFIGURABLE — APA\n",
        f"# Tipo: {config['label']}\n",
        f"# Configurado: {config['timestamp']}\n",
        "# Para cambiar, ejecuta: python apa/core/sandbox_setup.py\n",
        "# ============================================================\n",
        f"SANDBOX_TYPE={sandbox_type}\n",
        f"SANDBOX_PATH={config['sandbox_path']}\n",
    ]

    if sandbox_type != "local":
        lines.extend([
            f"SANDBOX_HOST={config['host']}\n",
            f"SANDBOX_USER={config['user']}\n",
            f"SANDBOX_SSH_PORT={config['ssh_port']}\n",
        ])
        if config.get('ssh_key'):
            lines.append(f"SANDBOX_SSH_KEY={config['ssh_key']}\n")

    lines.append(f"SANDBOX_TIMEOUT={config['timeout']}\n")

    if config.get('python_cmd') and config['python_cmd'] != "python3":
        lines.append(f"SANDBOX_PYTHON_CMD={config['python_cmd']}\n")

    if config.get('node_cmd') and config['node_cmd'] != "node":
        lines.append(f"SANDBOX_NODE_CMD={config['node_cmd']}\n")

    return lines


def _configure_local() -> dict:
    """Pide datos para sandbox local."""
    print()
    print("  --- SANDBOX LOCAL ---")
    print("  El sandbox se creara en tu PC.")
    print("  Todo el codigo se ejecutara con subprocess directo.")
    print()

    default_path = os.path.join(os.getcwd(), "apa_sandbox")
    sandbox_path = _ask("  Ruta del sandbox", default_path)
    timeout = _ask_int("  Timeout de ejecucion (segundos)", 30)

    # Detectar comandos disponibles
    python_cmd = _ask("  Comando de Python", "python3")
    node_cmd = _ask("  Comando de Node.js", "node")

    return {
        "label": "PC Local",
        "sandbox_path": sandbox_path,
        "timeout": timeout,
        "python_cmd": python_cmd,
        "node_cmd": node_cmd,
        "timestamp": _now(),
    }


def _configure_nas() -> dict:
    """Pide datos para sandbox NAS."""
    print()
    print("  --- SANDBOX NAS ---")
    print("  El sandbox estara en tu servidor NAS conectado por SSH.")
    print()

    host = _ask("  IP o nombre del NAS")
    user = _ask("  Usuario SSH", "admin")
    ssh_port = _ask_int("  Puerto SSH", 22)
    sandbox_path = _ask("  Ruta del sandbox en el NAS", "/app/sandbox")
    timeout = _ask_int("  Timeout de ejecucion (segundos)", 30)
    ssh_key = _ask("  Ruta a clave SSH privada (Enter para usar default)", "", required=False)

    return {
        "label": "NAS",
        "host": host,
        "user": user,
        "ssh_port": ssh_port,
        "sandbox_path": sandbox_path,
        "timeout": timeout,
        "ssh_key": ssh_key,
        "timestamp": _now(),
    }


def _configure_vm() -> dict:
    """Pide datos para sandbox en Máquina Virtual."""
    print()
    print("  --- SANDBOX: MAQUINA VIRTUAL ---")
    print("  El sandbox estara en una VM conectada por SSH.")
    print("  Ejemplos: WSL, VirtualBox, VMware, Proxmox, etc.")
    print()

    host = _ask("  IP o nombre de la VM")
    user = _ask("  Usuario SSH", "developer")
    ssh_port = _ask_int("  Puerto SSH", 22)
    sandbox_path = _ask("  Ruta del sandbox en la VM", "/home/dev/sandbox")
    timeout = _ask_int("  Timeout de ejecucion (segundos)", 30)
    ssh_key = _ask("  Ruta a clave SSH privada (Enter para usar default)", "", required=False)

    return {
        "label": "Maquina Virtual",
        "host": host,
        "user": user,
        "ssh_port": ssh_port,
        "sandbox_path": sandbox_path,
        "timeout": timeout,
        "ssh_key": ssh_key,
        "timestamp": _now(),
    }


def _configure_external() -> dict:
    """Pide datos para sandbox en dispositivo externo."""
    print()
    print("  --- SANDBOX: DISPOSITIVO EXTERNO ---")
    print("  El sandbox estara en un dispositivo remoto por SSH.")
    print("  Ejemplos: Raspberry Pi, servidor dedicado, etc.")
    print()

    host = _ask("  IP o nombre del dispositivo")
    user = _ask("  Usuario SSH", "pi")
    ssh_port = _ask_int("  Puerto SSH", 22)
    sandbox_path = _ask("  Ruta del sandbox en el dispositivo", "/home/pi/sandbox")
    timeout = _ask_int("  Timeout de ejecucion (segundos)", 30)
    ssh_key = _ask("  Ruta a clave SSH privada (Enter para usar default)", "", required=False)

    return {
        "label": "Dispositivo Externo",
        "host": host,
        "user": user,
        "ssh_port": ssh_port,
        "sandbox_path": sandbox_path,
        "timeout": timeout,
        "ssh_key": ssh_key,
        "timestamp": _now(),
    }


def _now():
    """Retorna timestamp actual como string."""
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def run_setup(env_path=None, non_interactive=False):
    """Ejecuta el asistente de configuración del sandbox.
    
    Args:
        env_path: Ruta al .env. Si es None, se busca automáticamente.
        non_interactive: Si True, solo retorna la config sin interactuar.
    
    Returns:
        dict con la configuración elegida, o None si se canceló.
    """
    if env_path is None:
        env_path = _find_env_file()

    _banner()

    # Preguntar opción
    while True:
        choice = _ask("  Elige una opcion (1-4)", "").strip()
        if choice == "1":
            sandbox_type = "local"
            config = _configure_local()
            break
        elif choice == "2":
            sandbox_type = "nas"
            config = _configure_nas()
            break
        elif choice == "3":
            sandbox_type = "vm"
            config = _configure_vm()
            break
        elif choice == "4":
            sandbox_type = "external"
            config = _configure_external()
            break
        elif choice.lower() in ("q", "quit", "salir", ""):
            print("\n  Configuracion cancelada.\n")
            return None
        else:
            print("  Opcion no valida. Elige 1, 2, 3 o 4.")

    # Confirmar
    print()
    print("  --- RESUMEN DE CONFIGURACION ---")
    print(f"  Tipo de sandbox:  {config['label']} ({sandbox_type})")
    print(f"  Ubicacion:        {config['sandbox_path']}")
    if sandbox_type != "local":
        print(f"  Host:              {config['host']}")
        print(f"  Usuario SSH:       {config['user']}")
        print(f"  Puerto SSH:        {config['ssh_port']}")
        if config.get('ssh_key'):
            print(f"  Clave SSH:         {config['ssh_key']}")
    print(f"  Timeout:           {config['timeout']}s")
    print()

    confirm = _ask("  Confirmar configuracion? (s/n)", "s").strip().lower()
    if confirm not in ("s", "si", "y", "yes"):
        print("\n  Configuracion cancelada.\n")
        return None

    # Escribir en .env
    existing_lines = _read_existing_env(env_path)
    config_lines = _generate_env_config(sandbox_type, config)
    _write_env(env_path, existing_lines, config_lines)

    # Si es local, crear el directorio
    if sandbox_type == "local":
        os.makedirs(config["sandbox_path"], exist_ok=True)
        work_dir = os.path.join(config["sandbox_path"], "work")
        os.makedirs(work_dir, exist_ok=True)

    print()
    print("  " + "=" * 56)
    print(f"  Configuracion escrita en: {env_path}")
    print(f"  Sandbox: {config['label']} en {config['sandbox_path']}")
    print()
    print("  Para cambiar en el futuro, ejecuta:")
    print("    python apa/core/sandbox_setup.py")
    print("  " + "=" * 56)
    print()

    return {"sandbox_type": sandbox_type, **config}


# =================================================================
# TESTS
# =================================================================

def _run_tests():
    """Tests del módulo sandbox_setup."""
    import tempfile
    import re

    print("=" * 60)
    print("TEST: sandbox_setup v1.0")
    print("=" * 60)
    passed = 0
    failed = 0

    # --- Test 1: _find_env_file retorna ruta ---
    try:
        path = _find_env_file()
        assert isinstance(path, str) and len(path) > 0
        assert path.endswith(".env")
        print("  [PASS] _find_env_file retorna ruta a .env")
        passed += 1
    except Exception as e:
        print(f"  [FAIL] _find_env_file: {e}")
        failed += 1

    # --- Test 2: _generate_env_config para local ---
    try:
        config = {
            "label": "PC Local",
            "sandbox_path": "./apa_sandbox",
            "timeout": 30,
            "python_cmd": "python3",
            "node_cmd": "node",
            "timestamp": "2026-01-01 00:00:00",
        }
        lines = _generate_env_config("local", config)
        text = "".join(lines)
        assert "SANDBOX_TYPE=local" in text
        assert "SANDBOX_PATH=./apa_sandbox" in text
        assert "SANDBOX_HOST" not in text  # Local no tiene host
        assert "SANDBOX_TIMEOUT=30" in text
        assert "SANDBOX CONFIGURABLE" in text
        print("  [PASS] _generate_env_config para local")
        passed += 1
    except Exception as e:
        print(f"  [FAIL] _generate_env_config local: {e}")
        failed += 1

    # --- Test 3: _generate_env_config para NAS ---
    try:
        config = {
            "label": "NAS",
            "sandbox_path": "/app/sandbox",
            "host": "192.168.1.100",
            "user": "admin",
            "ssh_port": 22,
            "ssh_key": "",
            "timeout": 30,
            "timestamp": "2026-01-01 00:00:00",
        }
        lines = _generate_env_config("nas", config)
        text = "".join(lines)
        assert "SANDBOX_TYPE=nas" in text
        assert "SANDBOX_HOST=192.168.1.100" in text
        assert "SANDBOX_USER=admin" in text
        assert "SANDBOX_SSH_PORT=22" in text
        assert "SANDBOX_PATH=/app/sandbox" in text
        print("  [PASS] _generate_env_config para NAS")
        passed += 1
    except Exception as e:
        print(f"  [FAIL] _generate_env_config NAS: {e}")
        failed += 1

    # --- Test 4: _generate_env_config para VM con SSH key ---
    try:
        config = {
            "label": "Maquina Virtual",
            "sandbox_path": "/home/dev/sandbox",
            "host": "10.0.0.50",
            "user": "developer",
            "ssh_port": 2222,
            "ssh_key": "/home/user/.ssh/id_rsa",
            "timeout": 60,
            "timestamp": "2026-01-01 00:00:00",
        }
        lines = _generate_env_config("vm", config)
        text = "".join(lines)
        assert "SANDBOX_TYPE=vm" in text
        assert "SANDBOX_SSH_KEY=/home/user/.ssh/id_rsa" in text
        assert "SANDBOX_SSH_PORT=2222" in text
        assert "SANDBOX_TIMEOUT=60" in text
        print("  [PASS] _generate_env_config para VM con SSH key")
        passed += 1
    except Exception as e:
        print(f"  [FAIL] _generate_env_config VM: {e}")
        failed += 1

    # --- Test 5: _generate_env_config para external ---
    try:
        config = {
            "label": "Dispositivo Externo",
            "sandbox_path": "/srv/sandbox",
            "host": "rpi.local",
            "user": "pi",
            "ssh_port": 22,
            "ssh_key": "",
            "timeout": 30,
            "timestamp": "2026-01-01 00:00:00",
        }
        lines = _generate_env_config("external", config)
        text = "".join(lines)
        assert "SANDBOX_TYPE=external" in text
        assert "SANDBOX_HOST=rpi.local" in text
        assert "SANDBOX_USER=pi" in text
        print("  [PASS] _generate_env_config para external")
        passed += 1
    except Exception as e:
        print(f"  [FAIL] _generate_env_config external: {e}")
        failed += 1

    # --- Test 6: _write_env escribe correctamente ---
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False, encoding='utf-8') as f:
            f.write("# Mi .env\n")
            f.write("OPENROUTER_API_KEY=sk-test\n")
            f.write("SANDBOX_TYPE=local\n")
            f.write("SANDBOX_PATH=/old/path\n")
            f.write("SANDBOX_HOST=old.host\n")
            temp_env = f.name

        new_config = [
            "# ============================================================\n",
            "# SANDBOX CONFIGURABLE — APA\n",
            "SANDBOX_TYPE=nas\n",
            "SANDBOX_HOST=192.168.1.100\n",
            "SANDBOX_USER=admin\n",
            "SANDBOX_PATH=/app/sandbox\n",
            "SANDBOX_SSH_PORT=22\n",
            "SANDBOX_TIMEOUT=30\n",
        ]
        _write_env(temp_env, _read_existing_env(temp_env), new_config)

        with open(temp_env, 'r', encoding='utf-8') as f:
            content = f.read()

        assert "OPENROUTER_API_KEY=sk-test" in content, "Otros campos deben mantenerse"
        assert "SANDBOX_TYPE=nas" in content, "Nuevo tipo debe estar"
        assert "SANDBOX_HOST=192.168.1.100" in content, "Nuevo host debe estar"
        assert "SANDBOX_USER=admin" in content
        assert "/old/path" not in content, "Viejo path debe eliminarse"
        assert "old.host" not in content, "Viejo host debe eliminarse"

        os.unlink(temp_env)
        print("  [PASS] _write_env reemplaza config sandbox sin tocar otros campos")
        passed += 1
    except Exception as e:
        print(f"  [FAIL] _write_env: {e}")
        failed += 1

    # --- Test 7: _write_env no duplica config ---
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False, encoding='utf-8') as f:
            f.write("OPENROUTER_API_KEY=sk-test\n")
            temp_env = f.name

        new_config = ["SANDBOX_TYPE=local\n", "SANDBOX_PATH=./sandbox\n"]
        _write_env(temp_env, _read_existing_env(temp_env), new_config)

        # Ejecutar de nuevo: no debe duplicar
        _write_env(temp_env, _read_existing_env(temp_env), new_config)

        with open(temp_env, 'r', encoding='utf-8') as f:
            content = f.read()

        count = content.count("SANDBOX_TYPE=local")
        assert count == 1, f"SANDBOX_TYPE aparece {count} veces, debe ser 1"

        os.unlink(temp_env)
        print("  [PASS] _write_env no duplica config al ejecutar varias veces")
        passed += 1
    except Exception as e:
        print(f"  [FAIL] No duplicar: {e}")
        failed += 1

    # --- Test 8: _configure functions existen ---
    try:
        assert callable(_configure_local)
        assert callable(_configure_nas)
        assert callable(_configure_vm)
        assert callable(_configure_external)
        print("  [PASS] Las 4 funciones de configuracion existen")
        passed += 1
    except Exception as e:
        print(f"  [FAIL] Funciones de configuracion: {e}")
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
    if "--test" in sys.argv:
        success = _run_tests()
        sys.exit(0 if success else 1)
    else:
        run_setup()
