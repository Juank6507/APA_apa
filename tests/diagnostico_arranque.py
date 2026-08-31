# tests/diagnostico_arranque.py
# ═══════════════════════════════════════════════════════════════════════
#
# Diagnóstico paso a paso del arranque de APA y levantamiento de MB.
# Verifica cada eslabón de la cadena en orden y dice exactamente
# dónde falla y qué hay que arreglar.
#
# USO (desde la raíz del proyecto APA):
#   python tests/diagnostico_arranque.py
#
# O desde cualquier sitio apuntando al proyecto:
#   python tests/diagnostico_arranque.py C:\Python\Proyectos\APA
#

import os
import sys
import time
import json
import shutil
import subprocess
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError

# ── Configuración del test ──────────────────────────────────────────

# Buscar la raíz del proyecto APA
if len(sys.argv) > 1:
    APA_ROOT = Path(sys.argv[1]).resolve()
else:
    # Intentar detectar automáticamente
    _this = Path(__file__).resolve()
    # tests/diagnostico_arranque.py → tests/ → APA_root/
    APA_ROOT = _this.parent.parent.resolve()

# Asegurar que core/ y config/ son importables
if str(APA_ROOT) not in sys.path:
    sys.path.insert(0, str(APA_ROOT))
if str(APA_ROOT / "interface") not in sys.path:
    sys.path.insert(0, str(APA_ROOT / "interface"))


# ── Utilidades de presentación ──────────────────────────────────────

PASADOS = 0
FALLIDOS = 0
ADVERTENCIAS = 0


def paso(numero, titulo):
    print(f"\n{'='*65}")
    print(f"  PASO {numero}: {titulo}")
    print(f"{'='*65}")


def ok(mensaje):
    global PASADOS
    PASADOS += 1
    print(f"  ✅  {mensaje}")


def fallo(mensaje, consejo=""):
    global FALLIDOS
    FALLIDOS += 1
    print(f"  ❌  {mensaje}")
    if consejo:
        print(f"      💡 {consejo}")


def aviso(mensaje, consejo=""):
    global ADVERTENCIAS
    ADVERTENCIAS += 1
    print(f"  ⚠️  {mensaje}")
    if consejo:
        print(f"      💡 {consejo}")


def info(mensaje):
    print(f"  ℹ️  {mensaje}")


def cabecera():
    print()
    print("╔" + "═"*63 + "╗")
    print("║   DIAGNÓSTICO DE ARRANQUE APA + MODEL BROKER              ║")
    print("╚" + "═"*63 + "╝")
    print(f"  Raíz del proyecto: {APA_ROOT}")
    print(f"  Python: {sys.version}")
    print(f"  SO: {os.name} / {sys.platform}")
    print(f"  Hora: {time.strftime('%Y-%m-%d %H:%M:%S')}")


def resumen():
    total = PASADOS + FALLIDOS + ADVERTENCIAS
    print(f"\n{'='*65}")
    print(f"  RESUMEN")
    print(f"{'='*65}")
    print(f"  ✅ Pasados:   {PASADOS}")
    print(f"  ❌ Fallos:    {FALLIDOS}")
    print(f"  ⚠️  Avisos:    {ADVERTENCIAS}")
    print(f"{'='*65}")
    if FALLIDOS == 0 and ADVERTENCIAS == 0:
        print("  🎉 Todo correcto. APA debería arrancar y conectar con MB sin problemas.")
    elif FALLIDOS == 0:
        print("  ⚡ Hay avisos pero no fallos bloqueantes. APA debería funcionar.")
    else:
        print("  🔧 Hay fallos que impedirán el funcionamiento correcto.")
        print("     Revisa los 💡 arriba para saber cómo arreglar cada uno.")
    print()


# ════════════════════════════════════════════════════════════════════
#  TESTS
# ════════════════════════════════════════════════════════════════════

def test_paso_1_estructura():
    """Verifica que la estructura de carpetas del proyecto existe."""
    paso(1, "Estructura de carpetas del proyecto")

    carpetas = [
        ("Raíz APA", APA_ROOT),
        ("config/", APA_ROOT / "config"),
        ("core/", APA_ROOT / "core"),
        ("interface/", APA_ROOT / "interface"),
        ("interface/app/", APA_ROOT / "interface" / "app"),
    ]
    for nombre, ruta in carpetas:
        if ruta.is_dir():
            ok(f"{nombre} existe → {ruta}")
        else:
            fallo(f"{nombre} NO existe → {ruta}",
                  f"Crea la carpeta o verifica que APA_ROOT es correcto.")

    # Verificar archivos clave
    archivos = [
        ("config/settings.py", APA_ROOT / "config" / "settings.py"),
        ("core/mb_launcher.py", APA_ROOT / "core" / "mb_launcher.py"),
        ("core/router.py", APA_ROOT / "core" / "router.py"),
        ("core/notifications.py", APA_ROOT / "core" / "notifications.py"),
        ("interface/app_apa.py", APA_ROOT / "interface" / "app_apa.py"),
        ("interface/app/startup.py", APA_ROOT / "interface" / "app" / "startup.py"),
        ("interface/app/config_apa.py", APA_ROOT / "interface" / "app" / "config_apa.py"),
        ("interface/app/sse_manager.py", APA_ROOT / "interface" / "app" / "sse_manager.py"),
        ("interface/app/chat_engine.py", APA_ROOT / "interface" / "app" / "chat_engine.py"),
    ]
    for nombre, ruta in archivos:
        if ruta.is_file():
            ok(f"{nombre} existe ({ruta.stat().st_size} bytes)")
        else:
            fallo(f"{nombre} NO existe → {ruta}")


def test_paso_2_dotenv():
    """Verifica que el archivo .env existe, es legible y tiene las variables necesarias."""
    paso(2, "Archivo .env")

    env_path = APA_ROOT / ".env"
    if not env_path.is_file():
        fallo(f"No existe {env_path}",
              f"Crea el archivo .env en {APA_ROOT} con al menos MODEL_BROKER_URL")
        return None

    ok(f".env existe → {env_path} ({env_path.stat().st_size} bytes)")

    # Leer el contenido
    try:
        contenido = env_path.read_text(encoding="utf-8-sig")
        ok(f".env es legible ({len(contenido)} chars)")
    except Exception as e:
        fallo(f"No se puede leer .env: {e}")
        return None

    # Buscar las variables clave
    variables_necesarias = {
        "MODEL_BROKER_URL": "URL del Model Broker (ej: http://127.0.0.1:8100)",
        "MODEL_BROKER_START_CMD": "Comando para arrancar MB (ej: bun --hot index.ts)",
        "MODEL_BROKER_SANDBOX_PATH": "Ruta al directorio del sandbox MB",
    }

    variables_opcionales = {
        "MODEL_BROKER_API_KEY": "API key para autenticar con MB",
        "LOG_LEVEL": "Nivel de log (INFO, DEBUG, etc.)",
        "OLLAMA_BASE_URL": "URL de Ollama local",
        "OLLAMA_DEFAULT_MODEL": "Modelo Ollama por defecto",
    }

    env_values = {}
    for var, descripcion in variables_necesarias.items():
        for linea in contenido.splitlines():
            linea_limpia = linea.strip()
            if linea_limpia.startswith("#") or not linea_limpia:
                continue
            if "=" in linea_limpia:
                key, _, value = linea_limpia.partition("=")
                if key.strip() == var:
                    value = value.strip().strip('"\'')
                    env_values[var] = value
                    ok(f"{var} = {value}")
                    # Validaciones específicas
                    if var == "MODEL_BROKER_URL":
                        if value.startswith("http"):
                            ok(f"  → URL parece correcta")
                        else:
                            fallo(f"  → URL no empieza por http: '{value}'",
                                  "Debe ser algo como http://127.0.0.1:8100")
                    break
        else:
            fallo(f"{var} NO está definida en .env",
                  f"Añade: {var}=tu_valor  ({descripcion})")

    for var, descripcion in variables_opcionales.items():
        for linea in contenido.splitlines():
            linea_limpia = linea.strip()
            if linea_limpia.startswith("#") or not linea_limpia:
                continue
            if "=" in linea_limpia:
                key, _, value = linea_limpia.partition("=")
                if key.strip() == var:
                    value = value.strip().strip('"\'')
                    info(f"{var} = {value} (opcional, configurada)")
                    break
        else:
            info(f"{var} no configurada (usará valor por defecto)")

    return env_values


def test_paso_3_settings(env_values):
    """Verifica que config/settings.py carga correctamente y lee las variables."""
    paso(3, "config/settings.py — Carga de configuración")

    try:
        from config.settings import settings, _find_and_load_dotenv
        ok("config.settings importado correctamente")
    except Exception as e:
        fallo(f"No se pudo importar config.settings: {e}",
              "Verifica que config/settings.py existe y no tiene errores de sintaxis")
        return

    # Verificar que el .env se cargó
    env_loaded = _find_and_load_dotenv()
    if env_loaded:
        ok(f".env cargado desde: {env_loaded}")
    else:
        aviso(".env no se cargó automáticamente (puede ser que ya esté en os.environ)")

    # Verificar propiedades de settings
    checks = [
        ("model_broker_url", "URL del Model Broker"),
        ("model_broker_start_cmd", "Comando de arranque de MB"),
        ("model_broker_start_dir", "Directorio del sandbox"),
        ("log_level", "Nivel de log"),
    ]
    for attr, descripcion in checks:
        try:
            valor = getattr(settings, attr)
            ok(f"settings.{attr} = '{valor}' ({descripcion})")
        except Exception as e:
            fallo(f"settings.{attr} falló: {e}")

    # Verificar que los valores coinciden con lo esperado
    if env_values:
        url_esperada = env_values.get("MODEL_BROKER_URL", "")
        url_real = settings.model_broker_url
        if url_esperada == url_real:
            ok(f"MODEL_BROKER_URL coincide con .env: {url_real}")
        else:
            fallo(f"MODEL_BROKER_URL no coincide: .env='{url_esperada}' vs settings='{url_real}'",
                  "Puede haber otra variable de entorno o .env sobreescribiendo")

        cmd_esperado = env_values.get("MODEL_BROKER_START_CMD", "")
        cmd_real = settings.model_broker_start_cmd
        if cmd_esperado == cmd_real:
            ok(f"MODEL_BROKER_START_CMD coincide con .env: {cmd_real}")
        else:
            fallo(f"MODEL_BROKER_START_CMD no coincide: .env='{cmd_esperado}' vs settings='{cmd_real}'")

        dir_esperado = env_values.get("MODEL_BROKER_SANDBOX_PATH", "")
        dir_real = settings.model_broker_start_dir
        if dir_esperado == dir_real:
            ok(f"MODEL_BROKER_SANDBOX_PATH coincide con .env: {dir_real}")
        else:
            fallo(f"MODEL_BROKER_SANDBOX_PATH no coincide: .env='{dir_esperado}' vs settings='{dir_real}'")


def test_paso_4_config_apa():
    """Verifica que interface/app/config_apa.py lee los valores de settings."""
    paso(4, "interface/app/config_apa.py — Constantes de la app")

    try:
        from app.config_apa import (
            MODEL_BROKER_URL,
            MODEL_BROKER_START_CMD,
            MODEL_BROKER_START_DIR,
            DEFAULT_HOST,
            DEFAULT_PORT,
        )
        ok("app.config_apa importado correctamente")
    except Exception as e:
        fallo(f"No se pudo importar app.config_apa: {e}",
              "Verifica que interface/app/config_apa.py existe y no tiene errores")
        return

    ok(f"MODEL_BROKER_URL = '{MODEL_BROKER_URL}'")
    ok(f"MODEL_BROKER_START_CMD = '{MODEL_BROKER_START_CMD}'")
    ok(f"MODEL_BROKER_START_DIR = '{MODEL_BROKER_START_DIR}'")
    ok(f"DEFAULT_HOST = '{DEFAULT_HOST}'")
    ok(f"DEFAULT_PORT = {DEFAULT_PORT}")

    # Verificar que START_CMD y START_DIR no están vacíos
    if not MODEL_BROKER_START_CMD:
        aviso("MODEL_BROKER_START_CMD está vacío",
              "APA no podrá arrancar MB automáticamente. MB debe estar corriendo antes de arrancar APA.")
    else:
        ok("MODEL_BROKER_START_CMD está configurado → APA intentará arrancar MB")

    if not MODEL_BROKER_START_DIR:
        aviso("MODEL_BROKER_START_DIR está vacío",
              "APA no sabrá dónde está el sandbox. MB debe estar corriendo antes de arrancar APA.")
    else:
        ok("MODEL_BROKER_START_DIR está configurado → APA sabe dónde está el sandbox")


def test_paso_5_sandbox_dir():
    """Verifica que el directorio del sandbox existe y tiene los archivos correctos."""
    paso(5, "Directorio del sandbox MB")

    # Leer la ruta desde settings (ya cargado en paso 3)
    try:
        from config.settings import settings
        sandbox_dir = Path(settings.model_broker_start_dir)
    except Exception:
        try:
            from app.config_apa import MODEL_BROKER_START_DIR
            sandbox_dir = Path(MODEL_BROKER_START_DIR)
        except Exception:
            fallo("No se pudo obtener SANDBOX_PATH de ningún sitio")
            return

    info(f"SANDBOX_PATH = {sandbox_dir}")

    # Verificar que el directorio existe
    if not sandbox_dir.exists():
        fallo(f"El directorio NO existe: {sandbox_dir}",
              f"Crea la carpeta y pon ahí los archivos del MB sandbox.")
        return

    ok(f"El directorio existe: {sandbox_dir}")

    if not sandbox_dir.is_dir():
        fallo(f"Existe pero NO es un directorio: {sandbox_dir}")
        return

    # Verificar contenido
    archivos_esperados = {
        "index.ts": "Servidor principal del MB (TypeScript/Bun)",
        "package.json": "Configuración del proyecto Bun",
    }

    for archivo, descripcion in archivos_esperados.items():
        ruta = sandbox_dir / archivo
        if ruta.is_file():
            ok(f"{archivo} existe ({ruta.stat().st_size} bytes) — {descripcion}")
        else:
            fallo(f"{archivo} NO existe en {sandbox_dir}",
                  f"El equipo de MB debe proporcionar {archivo}. {descripcion}.")

    # Verificar package.json tiene las dependencias correctas
    pkg_path = sandbox_dir / "package.json"
    if pkg_path.is_file():
        try:
            pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
            deps = pkg.get("dependencies", {})
            if "z-ai-web-dev-sdk" in deps:
                ok("package.json tiene 'z-ai-web-dev-sdk' como dependencia")
            else:
                aviso("package.json NO tiene 'z-ai-web-dev-sdk'",
                      "El MB sandbox lo necesita para llamar a los LLMs")

            scripts = pkg.get("scripts", {})
            if "dev" in scripts:
                ok(f"package.json tiene script 'dev': {scripts['dev']}")
            else:
                aviso("package.json NO tiene script 'dev'")
        except json.JSONDecodeError as e:
            fallo(f"package.json tiene error de JSON: {e}")

    # Listar todo lo que hay en el directorio
    try:
        todos = list(sandbox_dir.iterdir())
        info(f"Contenido completo de {sandbox_dir}:")
        for f in sorted(todos):
            tam = "(dir)" if f.is_dir() else f"({f.stat().st_size} bytes)"
            print(f"      {f.name} {tam}")
    except Exception:
        pass


def test_paso_6_comando_arranque():
    """Verifica que el comando de arranque de MB es ejecutable."""
    paso(6, "Comando de arranque de MB — ¿Se puede ejecutar?")

    try:
        from config.settings import settings
        start_cmd = settings.model_broker_start_cmd
        start_dir = settings.model_broker_start_dir
    except Exception:
        fallo("No se pudo leer la configuración de MB")
        return

    if not start_cmd:
        aviso("MODEL_BROKER_START_CMD está vacío",
              "MB debe estar arrancado manualmente antes de APA")
        return

    info(f"Comando: {start_cmd}")
    info(f"Directorio: {start_dir}")

    # Separar el comando en partes
    cmd_parts = start_cmd.split()
    ejecutable = cmd_parts[0]

    info(f"Ejecutable: {ejecutable}")
    info(f"Argumentos: {' '.join(cmd_parts[1:])}")

    # Buscar el ejecutable en el PATH
    ejecutable_path = shutil.which(ejecutable)
    if ejecutable_path:
        ok(f"'{ejecutable}' encontrado en PATH: {ejecutable_path}")
    else:
        fallo(f"'{ejecutable}' NO está en el PATH del sistema",
              f"Instala {ejecutable} o pon su ruta completa en MODEL_BROKER_START_CMD")

    # Verificar versión
    if ejecutable_path:
        try:
            resultado = subprocess.run(
                [ejecutable, "--version"],
                capture_output=True, text=True, timeout=10,
                cwd=start_dir if start_dir else None,
            )
            version = resultado.stdout.strip() or resultado.stderr.strip()
            if version:
                ok(f"Versión de {ejecutable}: {version[:80]}")
            else:
                aviso(f"{ejecutable} no reporta versión con --version")
        except subprocess.TimeoutExpired:
            aviso(f"{ejecutable} --version tardó demasiado (timeout)")
        except FileNotFoundError:
            fallo(f"{ejecutable} no se encuentra al ejecutar",
                  "Esto no debería pasar si shutil.which lo encontró. Verifica permisos.")
        except Exception as e:
            aviso(f"No se pudo obtener versión de {ejecutable}: {e}")

    # Verificar que el directorio de trabajo existe
    if start_dir:
        dir_path = Path(start_dir)
        if dir_path.is_dir():
            ok(f"Directorio de trabajo existe: {dir_path}")
        else:
            fallo(f"Directorio de trabajo NO existe: {dir_path}",
                  f"Crea la carpeta o corrige SANDBOX_PATH en .env")
    else:
        aviso("Directorio de trabajo vacío — subprocess usará el directorio actual de APA")


def test_paso_7_mb_responde():
    """Verifica si MB ya está corriendo y responde en la URL configurada."""
    paso(7, "¿Model Broker ya está corriendo?")

    try:
        from config.settings import settings
        mb_url = settings.model_broker_url
    except Exception:
        mb_url = "http://127.0.0.1:8100"

    if not mb_url:
        fallo("MODEL_BROKER_URL está vacía", "Configura MODEL_BROKER_URL en .env")
        return

    info(f"URL configurada: {mb_url}")

    # Test 1: GET /api/status
    status_url = f"{mb_url.rstrip('/')}/api/status"
    info(f"Probando: GET {status_url}")
    try:
        req = Request(status_url, method="GET")
        req.add_header("Accept", "application/json")
        with urlopen(req, timeout=5) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            ok(f"MB responde: {json.dumps(body, ensure_ascii=False)}")
    except URLError as e:
        if "ConnectionRefused" in str(e) or "timed out" in str(e).lower():
            aviso(f"MB NO está corriendo en {mb_url} (conexión rechazada o timeout)",
                  "APA intentará arrancarlo automáticamente (paso 8). Si no puede, usará modo emergencia.")
        else:
            aviso(f"Error conectando a MB: {e}")
        return
    except Exception as e:
        aviso(f"Error inesperado: {e}")
        return

    # Test 2: GET /api/models
    models_url = f"{mb_url.rstrip('/')}/api/models"
    info(f"Probando: GET {models_url}")
    try:
        req = Request(models_url, method="GET")
        req.add_header("Accept", "application/json")
        with urlopen(req, timeout=5) as resp:
            models = json.loads(resp.read().decode("utf-8"))
            if isinstance(models, list):
                ok(f"MB tiene {len(models)} modelo(s) disponible(s):")
                for m in models:
                    print(f"      • {m.get('model', '?')} (proveedor: {m.get('provider', '?')})")
            else:
                aviso(f"/api/models devolvió formato inesperado: {type(models).__name__}")
    except Exception as e:
        aviso(f"/api/models falló: {e}")

    # Test 3: POST /api/call (test rápido)
    call_url = f"{mb_url.rstrip('/')}/api/call"
    info(f"Probando: POST {call_url}")
    try:
        payload = json.dumps({
            "user_prompt": "Responde solo con la palabra OK",
        }).encode("utf-8")
        req = Request(call_url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
        t0 = time.time()
        with urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            elapsed = time.time() - t0
            if body.get("success"):
                content = body.get("content", "")
                model = body.get("model_used", "?")
                provider = body.get("provider", "?")
                ok(f"MB respondió en {elapsed:.1f}s — modelo: {model}, proveedor: {provider}")
                ok(f"Contenido: {content[:100]}{'...' if len(content) > 100 else ''}")
                sdk_mode = body.get("sdk_mode", "")
                if sdk_mode == "fallback":
                    info("ℹ MB en modo fallback — el SDK de IA no está configurado. "
                         "El chat funcionará con respuestas simuladas.")
                    info("ℹ Para respuestas reales, crea .z-ai-config en el "
                         "directorio del sandbox o en tu home.")
            else:
                fallo(f"MB respondió pero con error: {body.get('error', 'desconocido')}")
    except Exception as e:
        aviso(f"/api/call falló: {e}",
              "Si MB no está corriendo, APA lo intentará arrancar automáticamente.")
        info("💡 Si el sandbox indica 'sdk_mode: fallback', es normal: "
             "el SDK de IA no está configurado pero el sandbox funciona.")


def test_paso_8_mb_launcher():
    """Verifica que core/mb_launcher.py funciona correctamente."""
    paso(8, "core/mb_launcher.py — Lanzador de MB")

    try:
        from core.mb_launcher import ensure_mb_running, _health_check, stop_mb, get_mb_status
        ok("core.mb_launcher importado correctamente")
    except ImportError as e:
        fallo(f"No se pudo importar core.mb_launcher: {e}",
              "Verifica que core/mb_launcher.py existe y core/__init__.py permite la importación")
        return
    except Exception as e:
        fallo(f"Error importando core.mb_launcher: {e}")
        return

    # Verificar que las funciones exportadas son llamables
    funciones = [
        ("ensure_mb_running", ensure_mb_running),
        ("_health_check", _health_check),
        ("stop_mb", stop_mb),
        ("get_mb_status", get_mb_status),
    ]
    for nombre, func in funciones:
        if callable(func):
            ok(f"{nombre} es callable")
        else:
            fallo(f"{nombre} NO es callable")

    # Test: get_mb_status
    status = get_mb_status()
    ok(f"get_mb_status(): {status}")

    # Test: ensure_mb_running sin URL → debe retornar False
    resultado = ensure_mb_running("")
    if resultado is False:
        ok("ensure_mb_running('') retorna False (correcto)")
    else:
        fallo(f"ensure_mb_running('') debería retornar False, retornó {resultado}")

    # Test: _health_check con URL inválida → debe retornar False
    resultado = _health_check("http://0.0.0.0:1", timeout=1)
    if resultado is False:
        ok("_health_check(URL inválida) retorna False (correcto)")
    else:
        fallo(f"_health_check debería retornar False, retornó {resultado}")


def test_paso_9_startup():
    """Verifica que interface/app/startup.py importa correctamente."""
    paso(9, "interface/app/startup.py — Cadena de arranque")

    try:
        from app.startup import (
            init_subsystems,
            init_subsystems_threaded,
            get_mb_communication_status,
        )
        ok("app.startup importado correctamente")
    except Exception as e:
        fallo(f"No se pudo importar app.startup: {e}")
        return

    # Verificar que son llamables
    for nombre, func in [
        ("init_subsystems", init_subsystems),
        ("init_subsystems_threaded", init_subsystems_threaded),
        ("get_mb_communication_status", get_mb_communication_status),
    ]:
        if callable(func):
            ok(f"{nombre} es callable")
        else:
            fallo(f"{nombre} NO es callable")

    # Test: get_mb_communication_status
    mb_status = get_mb_communication_status()
    ok(f"get_mb_communication_status(): {json.dumps(mb_status, indent=2)}")
    if mb_status.get("mb_responding"):
        ok("MB está respondiendo ahora mismo")
    else:
        aviso(f"MB NO está respondiendo ahora mismo",
              "Cuando arrances APA, intentará levantar MB automáticamente")


def test_paso_10_notificaciones():
    """Verifica que el sistema de notificaciones funciona."""
    paso(10, "core/notifications.py — Sistema de notificaciones")

    try:
        from core.notifications import notify, register_callback, clear_callbacks
        ok("core.notifications importado correctamente")
    except Exception as e:
        fallo(f"No se pudo importar core.notifications: {e}")
        return

    # Test de notificación
    capturadas = []

    def capturar(event_type, message, data):
        capturadas.append((event_type, message, data))

    try:
        clear_callbacks()
        register_callback(capturar)
        notify("test:diagnostico", "Mensaje de prueba", {"clave": "valor"})
    except Exception as e:
        fallo(f"Error al registrar/emitir notificación: {e}")
        return

    if len(capturadas) == 1:
        ok("Notificación capturada correctamente")
        et, msg, dat = capturadas[0]
        if isinstance(msg, str):
            ok(f"Mensaje es string: '{msg}'")
        else:
            fallo(f"Mensaje es {type(msg).__name__}, debería ser string",
                  "Esto causaría '[object Object]' en la UI")
        if isinstance(dat, dict):
            ok(f"Data es dict: {dat}")
        else:
            fallo(f"Data es {type(dat).__name__}, debería ser dict")
    else:
        fallo(f"Se esperaba 1 notificación, se capturaron {len(capturadas)}")

    # Limpiar
    try:
        clear_callbacks()
    except Exception:
        pass


def test_paso_11_sse_manager():
    """Verifica que el gestor SSE puede recibir notificaciones con 3 parámetros."""
    paso(11, "interface/app/sse_manager.py — Callback SSE")

    try:
        from app.sse_manager import SSEManager
        ok("app.sse_manager importado correctamente")
    except Exception as e:
        fallo(f"No se pudo importar app.sse_manager: {e}")
        return

    # Verificar que _on_notification acepta 3 parámetros
    import inspect
    src = inspect.getsource(SSEManager)
    if "_on_notification" in src:
        ok("SSEManager tiene método _on_notification")

        # Extraer la firma
        for line in src.split("\n"):
            if "def _on_notification" in line:
                params = line.count(",") + 1  # +1 porque self no tiene coma antes
                if params >= 3:  # self + event_type + message + data = 4 mínimo, pero self puede no estar
                    ok(f"Firma del callback: {line.strip()}")
                    # Verificar que tiene event_type, message, data
                    if "event_type" in line and "message" in line and "data" in line:
                        ok("Callback tiene los 3 parámetros: event_type, message, data")
                    else:
                        fallo("Callback no tiene los 3 parámetros esperados",
                              "Debe ser: def _on_notification(self, event_type, message, data)")
                break
    else:
        fallo("SSEManager NO tiene método _on_notification")


def test_paso_12_router():
    """Verifica que core/router.py puede inicializarse."""
    paso(12, "core/router.py — Inicialización del router")

    try:
        from core.router import initialize_router, call_llm
        ok("core.router importado correctamente")
    except Exception as e:
        fallo(f"No se pudo importar core.router: {e}")
        return

    # Intentar inicializar
    info("Ejecutando initialize_router()...")
    try:
        report = initialize_router()
        ok(f"Router inicializado: modo={report.get('startup_mode', '?')}")
        ok(f"  MB disponible: {report.get('mb_available', False)}")
        ok(f"  MB modelos validados: {report.get('mb_validated_models', 0)}")
        ok(f"  Ollama listo: {report.get('ollama_ready', False)}")
        ok(f"  Caché cargado: {report.get('cache_loaded', False)}")
    except Exception as e:
        fallo(f"initialize_router() falló: {e}")


def test_paso_13_chat_engine():
    """Verifica que ChatEngine importa y tiene los métodos necesarios."""
    paso(13, "interface/app/chat_engine.py — Motor de chat")

    try:
        from app.chat_engine import ChatEngine
        ok("app.chat_engine importado correctamente")
    except Exception as e:
        fallo(f"No se pudo importar app.chat_engine: {e}")
        return

    # Verificar método handle_chat
    if hasattr(ChatEngine, "handle_chat"):
        ok("ChatEngine tiene método handle_chat")
    else:
        fallo("ChatEngine NO tiene método handle_chat")

    # Verificar método _call_llm_async
    if hasattr(ChatEngine, "_call_llm_async"):
        ok("ChatEngine tiene método _call_llm_async")
    else:
        aviso("ChatEngine NO tiene método _call_llm_async (puede tener otro nombre)")


def test_paso_14_planner():
    """Verifica que core/planner.py no tiene errores de sintaxis."""
    paso(14, "core/planner.py — Verificación de sintaxis")

    planner_path = APA_ROOT / "core" / "planner.py"
    if not planner_path.is_file():
        fallo(f"No existe: {planner_path}")
        return

    try:
        with open(planner_path, "r", encoding="utf-8") as f:
            compile(f.read(), str(planner_path), "exec")
        ok("planner.py no tiene errores de sintaxis")
    except SyntaxError as e:
        fallo(f"planner.py tiene SyntaxError en línea {e.lineno}: {e.msg}",
              f"Revisa la línea {e.lineno} de {planner_path}. Es probable un docstring mal cerrado.")


def test_paso_15_simulacion_arranque_completo():
    """Simula lo que hace APA al arrancar: llama a init_subsystems."""
    paso(15, "Simulación completa de arranque (init_subsystems)")

    try:
        from app.startup import init_subsystems
        from app.state import AppState
    except Exception as e:
        fallo(f"No se pudo importar: {e}")
        return

    info("Ejecutando init_subsystems() (puede tardar hasta 15 segundos)...")
    info("Esto es EXACTAMENTE lo que hace APA al arrancar.")

    state = AppState()
    t0 = time.time()

    try:
        result = init_subsystems(state=state)
        elapsed = time.time() - t0

        ok(f"init_subsystems completó en {elapsed:.1f}s")
        ok(f"  success: {result.get('success')}")
        ok(f"  mb_available: {result.get('mb_available')}")
        ok(f"  router_initialized: {result.get('router_initialized')}")
        ok(f"  startup_mode: {result.get('startup_mode')}")

        errores = result.get('errors', [])
        if errores:
            aviso(f"Hay {len(errores)} error(es) durante el arranque:")
            for err in errores:
                print(f"      ⚠ {err}")
        else:
            ok("Sin errores durante el arranque")

        if result.get('success'):
            ok("🎉 ¡El arranque completo fue EXITOSO!")
            ok("APA está listo para funcionar con MB.")
        else:
            fallo("El arranque no fue exitoso",
                  "Revisa los errores arriba. APA funcionará en modo degradado.")

    except Exception as e:
        elapsed = time.time() - t0
        fallo(f"init_subsystems() lanzó excepción tras {elapsed:.1f}s: {e}")


# ════════════════════════════════════════════════════════════════════
#  EJECUCIÓN
# ════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    cabecera()

    # Paso 1: Estructura
    test_paso_1_estructura()

    # Paso 2: .env
    env_values = test_paso_2_dotenv()

    # Paso 3: settings.py
    test_paso_3_settings(env_values)

    # Paso 4: config_apa.py
    test_paso_4_config_apa()

    # Paso 5: Directorio del sandbox
    test_paso_5_sandbox_dir()

    # Paso 6: Comando de arranque
    test_paso_6_comando_arranque()

    # Paso 7: ¿MB responde?
    test_paso_7_mb_responde()

    # Paso 8: mb_launcher
    test_paso_8_mb_launcher()

    # Paso 9: startup.py
    test_paso_9_startup()

    # Paso 10: notificaciones
    test_paso_10_notificaciones()

    # Paso 11: SSE manager
    test_paso_11_sse_manager()

    # Paso 12: router
    test_paso_12_router()

    # Paso 13: chat engine
    test_paso_13_chat_engine()

    # Paso 14: planner sintaxis
    test_paso_14_planner()

    # Paso 15: Simulación completa
    test_paso_15_simulacion_arranque_completo()

    resumen()
