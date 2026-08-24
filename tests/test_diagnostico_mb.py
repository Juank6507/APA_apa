# apa/tests/test_diagnostico_mb.py
"""Test diagnóstico paso a paso del levantamiento de Model Broker.

Este test NO es un test unitario clásico. Es un DIAGNÓSTICO que ejecuta
los 15 puntos críticos del flujo APA→MB delimitando la respuesta de
cada uno para identificar exactamente DÓNDE falla la cadena.

Ejecución desde la raíz del proyecto APA:
    python -m tests.test_diagnostico_mb
    o:
    python apa/tests/test_diagnostico_mb.py

Cada paso muestra:
  [PASS] — El paso funcionó correctamente
  [FAIL] — El paso falló (con detalle del error)
  [WARN] — El paso tiene un problema no crítico
  [SKIP] — El paso no se pudo ejecutar (dependencia previa rota)

Grupos:
  A: Configuración en APA (pasos 1-3)
  B: Descubrimiento de MB en disco (pasos 4-5)
  C: Dependencias de MB (pasos 6-7)
  D: Arranque de MB (pasos 8-9)
  E: Endpoints de MB (pasos 10-11)
  F: Simulación ensure_mb_running (paso 12)
  G: Validación de app.py (pasos 13-15)
"""

import sys
import os
import time
import socket
import subprocess
import importlib
import traceback
from pathlib import Path
from typing import Optional, List, Tuple, Dict

# ============================================================================
# INFRAESTRUCTURA DEL DIAGNÓSTICO
# ============================================================================

class DiagnosticResult:
    """Almacena el resultado de cada paso del diagnóstico."""

    def __init__(self):
        self.steps: List[Dict] = []
        self.warnings: List[str] = []
        self.start_time = time.time()

    def pass_(self, step_num: int, name: str, detail: str = ""):
        tag = f"Paso {step_num:02d}"
        msg = f"  [PASS] {tag}: {name}"
        if detail:
            msg += f" — {detail}"
        print(msg)
        self.steps.append({"num": step_num, "name": name, "status": "PASS", "detail": detail})

    def fail(self, step_num: int, name: str, detail: str = ""):
        tag = f"Paso {step_num:02d}"
        msg = f"  [FAIL] {tag}: {name}"
        if detail:
            msg += f"\n         └── {detail}"
        print(msg)
        self.steps.append({"num": step_num, "name": name, "status": "FAIL", "detail": detail})

    def warn(self, step_num: int, name: str, detail: str = ""):
        tag = f"Paso {step_num:02d}"
        msg = f"  [WARN] {tag}: {name}"
        if detail:
            msg += f" — {detail}"
        print(msg)
        self.steps.append({"num": step_num, "name": name, "status": "WARN", "detail": detail})
        self.warnings.append(f"{tag}: {name} — {detail}")

    def skip(self, step_num: int, name: str, reason: str = ""):
        tag = f"Paso {step_num:02d}"
        msg = f"  [SKIP] {tag}: {name}"
        if reason:
            msg += f" — {reason}"
        print(msg)
        self.steps.append({"num": step_num, "name": name, "status": "SKIP", "detail": reason})

    def is_critical_fail(self, step_num: int) -> bool:
        """Pasos críticos cuyo fallo impide continuar el diagnóstico."""
        # Pasos que no bloquean a los siguientes:
        non_blocking = {6, 7, 8, 9, 10, 11, 12}
        for s in self.steps:
            if s["num"] == step_num and s["status"] == "FAIL":
                return step_num not in non_blocking
        return False

    def summary(self):
        elapsed = time.time() - self.start_time
        passed = sum(1 for s in self.steps if s["status"] == "PASS")
        failed = sum(1 for s in self.steps if s["status"] == "FAIL")
        warned = sum(1 for s in self.steps if s["status"] == "WARN")
        skipped = sum(1 for s in self.steps if s["status"] == "SKIP")
        total = len(self.steps)

        print("\n" + "=" * 72)
        print(f"RESUMEN: {passed} OK, {failed} FALLOS, {warned} AVISOS, {skipped} OMITIDOS ({total} pasos, {elapsed:.1f}s)")

        if failed > 0:
            print("\n  FALLOS DETECTADOS (en orden):")
            for s in self.steps:
                if s["status"] == "FAIL":
                    print(f"    • Paso {s['num']:02d}: {s['name']}")
                    if s["detail"]:
                        for line in s["detail"].split("\n"):
                            print(f"      {line}")

        if self.warnings:
            print("\n  AVISOS:")
            for w in self.warnings:
                print(f"    • {w}")

        if failed == 0 and warned == 0:
            print("\n  ✓ Todos los pasos pasaron. El flujo APA→MB debería funcionar.")
        elif failed == 0:
            print("\n  ✓ No hay fallos críticos. Revisar avisos.")
        else:
            print("\n  ✗ Hay fallos que impiden el levantamiento de MB.")
            print("    Revisa cada FAIL arriba para identificar la causa raíz.")

        print("=" * 72)

        # Retornar código de salida
        return 0 if failed == 0 else 1


def _check_port_in_use(port: int) -> Tuple[bool, Optional[str]]:
    """Verifica si un puerto está en uso. Retorna (in_use, info)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            result = s.connect_ex(('127.0.0.1', port))
            if result == 0:
                return True, "puerto ocupado (algo escucha)"
            return False, f"puerto libre (connect_ex={result})"
    except OSError as e:
        return False, f"error de socket: {e}"


def _load_env_file(env_path: str) -> Dict[str, str]:
    """Lee un archivo .env y retorna un dict con las variables.
    Soporta líneas tipo KEY=VALUE, ignora comentarios y vacías.
    No usa python-dotenv — parsing manual para máxima portabilidad.
    """
    vars_found = {}
    if not os.path.isfile(env_path):
        return vars_found
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if "=" not in stripped:
                    continue
                key, _, value = stripped.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key:
                    vars_found[key] = value
    except Exception:
        pass
    return vars_found


def _get_mb_url() -> Tuple[Optional[str], str]:
    """Obtiene la URL de MB desde las fuentes posibles.
    Retorna (url, source_description).
    """
    sources_checked = []

    # 1. Variable de entorno (ya cargada en Python)
    from_env = os.environ.get("MODEL_BROKER_URL", "").strip()
    sources_checked.append(f"os.environ: {'✓ ' + from_env if from_env else 'vacía'}")
    if from_env:
        return from_env, "os.environ"

    # 2. Intentar cargar .env y leer directamente
    # Buscar .env en ubicaciones probables
    env_candidates = []
    this_file = os.path.abspath(__file__)
    tests_dir = os.path.dirname(this_file)        # .../apa/tests
    apa_dir = os.path.dirname(tests_dir)           # .../apa
    repo_dir = os.path.dirname(apa_dir)            # .../repo
    cwd = os.getcwd()

    for d in [tests_dir, apa_dir, repo_dir, cwd]:
        env_candidates.append(os.path.join(d, ".env"))
    # También hermanos comunes
    if os.path.basename(cwd).lower() == 'apa':
        env_candidates.append(os.path.join(os.path.dirname(cwd), ".env"))

    for env_path in env_candidates:
        if not os.path.isfile(env_path):
            continue
        env_vars = _load_env_file(env_path)
        url = env_vars.get("MODEL_BROKER_URL", "").strip()
        rel_path = os.path.relpath(env_path, cwd)
        sources_checked.append(f"{rel_path}: {'✓ ' + url if url else 'existe pero sin MODEL_BROKER_URL'}")
        if url:
            # Inyectar en os.environ para que el resto del diagnóstico la use
            os.environ["MODEL_BROKER_URL"] = url
            return url, f"{rel_path} (inyectada a os.environ)"

    # 3. Intentar core.settings
    try:
        for candidate in [cwd, os.path.dirname(cwd)]:
            core_path = os.path.join(candidate, "apa")
            if os.path.isdir(core_path) and core_path not in sys.path:
                sys.path.insert(0, core_path)

        from core import settings as _core_settings
        url = getattr(_core_settings, "model_broker_url", "").strip()
        sources_checked.append(f"core.settings: {'✓ ' + url if url else 'vacía'}")
        if url:
            return url, "core.settings"
    except Exception as e:
        sources_checked.append(f"core.settings: error ({e})")

    return None, " | ".join(sources_checked)


def _find_mb_dir_from_launcher() -> Tuple[Optional[str], str, bool]:
    """Ejecuta la lógica de _find_mb_directory del launcher.
    Retorna (dir_encontrado, detalle, es_real).
    es_real=False indica que es un fallback (no se encontró model_broker/).
    """
    # 1. Hermano de apa/ → raíz del repo
    try:
        # Simular: este archivo está en apa/tests/
        this_file = os.path.abspath(__file__)
        tests_dir = os.path.dirname(this_file)       # .../apa/tests
        apa_dir = os.path.dirname(tests_dir)          # .../apa
        repo_dir = os.path.dirname(apa_dir)           # .../repo
        candidate = os.path.join(repo_dir, "model_broker")
        if os.path.isdir(candidate):
            return repo_dir, f"encontrado como hermano de apa/ → {candidate}", True
    except Exception as e:
        pass

    # 2. CWD
    cwd = os.getcwd()
    if os.path.isdir(os.path.join(cwd, "model_broker")):
        return cwd, f"encontrado en CWD → {os.path.join(cwd, 'model_broker')}", True

    # 3. Buscar también en parent del CWD (por si estamos dentro de apa/)
    parent = os.path.dirname(cwd)
    if parent != cwd:
        # Probar hermano de 'apa' desde CWD
        if os.path.basename(cwd).lower() == 'apa':
            candidate = os.path.join(parent, "model_broker")
            if os.path.isdir(candidate):
                return parent, f"encontrado como hermano de CWD(=apa/) → {candidate}", True
        # Probar dentro de CWD (por si es la raíz del repo)
        candidate = os.path.join(cwd, "model_broker")
        if os.path.isdir(candidate):
            return cwd, f"encontrado en CWD → {candidate}", True

    # No encontrado
    return None, "model_broker/ no encontrado en ninguna ubicación", False


def _check_module_exists(module_name: str) -> Tuple[bool, str]:
    """Verifica si un módulo Python puede importarse."""
    try:
        importlib.import_module(module_name)
        return True, "importable"
    except ImportError as e:
        return False, f"ImportError: {e}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def _check_file_exists(path: str) -> Tuple[bool, str]:
    """Verifica si un archivo existe."""
    if os.path.isfile(path):
        return True, f"existe ({os.path.getsize(path)} bytes)"
    return False, "no existe"


def _check_dir_exists(path: str) -> Tuple[bool, str]:
    """Verifica si un directorio existe."""
    if os.path.isdir(path):
        contents = os.listdir(path)
        return True, f"existe ({len(contents)} items)"
    return False, "no existe"


def _check_subprocess_launch(
    mb_dir: str, timeout: float = 10.0,
) -> Tuple[bool, str, Optional[subprocess.Popen]]:
    """Intenta lanzar MB como subprocess y esperar su respuesta.
    Retorna (success, detail, process).
    """
    proc = None
    try:
        cmd = [sys.executable, "-m", "model_broker.app"]
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            cwd=mb_dir,
        )

        # Esperar un poco y verificar si el proceso sigue vivo
        time.sleep(2)

        if proc.poll() is not None:
            # Proceso ya salió
            stderr_output = proc.stderr.read().decode("utf-8", errors="replace")
            stdout_output = proc.stdout.read().decode("utf-8", errors="replace")
            detail = f"proceso salió con código {proc.returncode}"
            if stderr_output.strip():
                # Últimas 5 líneas del stderr
                lines = stderr_output.strip().split("\n")[-5:]
                detail += f"\n         stderr (últimas 5 líneas):"
                for line in lines:
                    detail += f"\n         | {line}"
            if stdout_output.strip():
                lines = stdout_output.strip().split("\n")[-3:]
                detail += f"\n         stdout (últimas 3 líneas):"
                for line in lines:
                    detail += f"\n         | {line}"
            return False, detail, proc

        return True, f"proceso vivo (PID {proc.pid})", proc

    except FileNotFoundError as e:
        return False, f"FileNotFoundError: {e}", None
    except Exception as e:
        return False, f"{type(e).__name__}: {e}", None


def _http_get(url: str, timeout: float = 5.0) -> Tuple[int, str, Optional[dict]]:
    """Hace GET y retorna (status_code, error_msg, json_body)."""
    try:
        import requests
        resp = requests.get(url, timeout=timeout)
        try:
            body = resp.json()
        except Exception:
            body = None
        return resp.status_code, "", body
    except Exception as e:
        return 0, str(e), None


def _http_post_json(url: str, payload: dict, timeout: float = 30.0) -> Tuple[int, str, Optional[dict]]:
    """Hace POST con JSON y retorna (status_code, error_msg, json_body)."""
    try:
        import requests
        resp = requests.post(url, json=payload, timeout=timeout)
        try:
            body = resp.json()
        except Exception:
            body = None
        return resp.status_code, "", body
    except Exception as e:
        return 0, str(e), None


def _kill_process(proc: subprocess.Popen) -> None:
    """Termina un subprocess de forma segura."""
    if proc is None:
        return
    try:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
    except Exception:
        pass


# ============================================================================
# DIAGNÓSTICO COMPLETO
# ============================================================================

def run_diagnostic() -> int:
    """Ejecuta los 15 pasos del diagnóstico. Retorna código de salida."""

    print("\n" + "=" * 72)
    print("DIAGNÓSTICO APA → MODEL BROKER — 15 PASOS")
    print("=" * 72)
    print(f"  Python:    {sys.version.split()[0]}")
    print(f"  CWD:       {os.getcwd()}")
    print(f"  Executable: {sys.executable}")
    print(f"  sys.path[0]: {sys.path[0]}")
    print(f"  Timestamp:  {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 72)

    r = DiagnosticResult()
    mb_url = None
    mb_dir = None
    mb_dir_is_real = False  # True solo si se encontró model_broker/ realmente
    launched_proc = None  # Para limpiar al final
    mb_already_running = False

    # =========================================================================
    # GRUPO A: CONFIGURACIÓN EN APA (pasos 1-3)
    # =========================================================================
    print("\n── GRUPO A: CONFIGURACIÓN EN APA ──\n")

    # --- PASO 1: URL de MB configurada ---
    mb_url, url_source = _get_mb_url()
    if mb_url:
        r.pass_(1, "URL de MB configurada", f"{mb_url} — fuente: {url_source}")
    else:
        # Ya tenemos el detalle de qué fuentes se revisaron
        r.fail(1, "URL de MB NO configurada",
               f"Fuentes revisadas: {url_source}")
        # No podemos continuar sin URL
        print()
        return r.summary()

    # --- PASO 2: Puerto de MB accesible (sin MB corriendo aún) ---
    port = 8100
    try:
        from urllib.parse import urlparse
        parsed = urlparse(mb_url)
        if parsed.port:
            port = parsed.port
    except Exception:
        pass

    in_use, port_info = _check_port_in_use(port)
    if in_use:
        mb_already_running = True
        r.warn(2, f"Puerto {port} ya está en uso", port_info)
    else:
        r.pass_(2, f"Puerto {port} está libre", port_info)

    # --- PASO 3: módulo mb_launcher importable ---
    # Intentar agregar apa/ al path si estamos en el repo root
    _path_fixed = False
    try:
        from core import mb_launcher
        r.pass_(3, "mb_launcher importable desde core.mb_launcher",
                f"{mb_launcher.__file__}")
    except ImportError:
        # Si falla, intentar agregar directorios al path
        _candidate_dirs = [
            os.path.dirname(os.path.abspath(__file__)),  # tests/
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),  # apa/
            os.getcwd(),  # CWD
        ]
        for d in _candidate_dirs:
            parent = os.path.dirname(d)
            for candidate in [d, parent]:
                core_candidate = os.path.join(candidate, "core")
                if os.path.isdir(core_candidate) and candidate not in sys.path:
                    sys.path.insert(0, candidate)
                    _path_fixed = True
                    break
            if _path_fixed:
                break

        # Reintentar
        try:
            from core import mb_launcher
            r.pass_(3, "mb_launcher importable desde core.mb_launcher (path corregido)",
                    f"{mb_launcher.__file__}")
        except ImportError as e:
            # Último intento: import directo
            try:
                import mb_launcher as _ml
                r.warn(3, "mb_launcher importable solo como mb_launcher (no core.mb_launcher)",
                       str(e))
            except ImportError as e2:
                r.fail(3, "mb_launcher NO se puede importar",
                       f"core.mb_launcher: {e} | mb_launcher: {e2}")
        # No error genérico aquí porque el path fix ya intentó
    except Exception as e:
        r.fail(3, "Error inesperado importando mb_launcher", str(e))

    # =========================================================================
    # GRUPO B: DESCUBRIMIENTO DE MB EN DISCO (pasos 4-5)
    # =========================================================================
    print("\n── GRUPO B: DESCUBRIMIENTO DE MB EN DISCO ──\n")

    # --- PASO 4: Directorio de MB encontrado ---
    mb_dir, dir_detail, mb_dir_is_real = _find_mb_dir_from_launcher()
    if mb_dir_is_real:
        mb_path = os.path.join(mb_dir, "model_broker")
        exists, exist_detail = _check_dir_exists(mb_path)
        if exists:
            r.pass_(4, "Directorio de MB encontrado", f"{mb_path} — {exist_detail}")
        else:
            r.fail(4, "model_broker/ NO existe en el directorio esperado",
                   f"Buscado en: {mb_path} — {exist_detail}")
    else:
        r.fail(4, "Directorio de MB NO encontrado", dir_detail)

    # --- PASO 5: Entry point de MB (model_broker.app) ---
    if mb_dir_is_real:
        app_path = os.path.join(mb_dir, "model_broker", "app.py")
        exists, detail = _check_file_exists(app_path)
        if exists:
            r.pass_(5, "Entry point model_broker/app.py encontrado", detail)
        else:
            # Buscar alternativas
            alternatives = []
            for name in ["main.py", "__main__.py", "server.py", "index.py"]:
                alt_path = os.path.join(mb_dir, "model_broker", name)
                if os.path.isfile(alt_path):
                    alternatives.append(name)
            alt_msg = f"Alternativas encontradas: {alternatives}" if alternatives else "No hay archivos de entry point"
            r.fail(5, "model_broker/app.py NO encontrado",
                   f"Buscado en: {app_path}. {alt_msg}")

        # 5b: Listar contenido de model_broker/ para diagnóstico
        mb_pkg = os.path.join(mb_dir, "model_broker")
        try:
            items = sorted(os.listdir(mb_pkg))
            py_files = [i for i in items if i.endswith('.py')]
            print(f"         Contenido de model_broker/: {items}")
            print(f"         Archivos .py: {py_files}")
        except Exception:
            pass
    else:
        r.skip(5, "No se puede verificar entry point", "Paso 4 falló")

    # =========================================================================
    # GRUPO C: DEPENDENCIAS DE MB (pasos 6-7)
    # =========================================================================
    print("\n── GRUPO C: DEPENDENCIAS DE MB ──\n")

    # --- PASO 6: Dependencias Python de MB ---
    mb_deps = ["flask", "fastapi", "uvicorn", "requests", "httpx"]
    found_deps = []
    missing_deps = []
    for dep in mb_deps:
        exists, detail = _check_module_exists(dep)
        if exists:
            found_deps.append(dep)
        else:
            missing_deps.append(dep)

    if missing_deps:
        r.warn(6, f"Dependencias faltantes: {missing_deps}",
               f"Instaladas: {found_deps}. Faltan: {missing_deps}")
    else:
        r.pass_(6, "Todas las dependencias comunes instaladas",
               f"{found_deps}")

    # --- PASO 7: .env de MB existe ---
    if mb_dir_is_real:
        mb_env_paths = [
            os.path.join(mb_dir, "model_broker", ".env"),
            os.path.join(mb_dir, "model_broker", ".env.example"),
        ]
        env_found = False
        for env_path in mb_env_paths:
            if os.path.isfile(env_path):
                r.pass_(7, ".env de MB encontrado", f"{env_path}")
                env_found = True
                break
        if not env_found:
            r.warn(7, ".env de MB NO encontrado",
                   f"Buscado en: {mb_env_paths}")
    else:
        r.skip(7, "No se puede verificar .env de MB", "Paso 4 falló (directorio no encontrado)")

    # =========================================================================
    # GRUPO D: ARRANQUE DE MB (pasos 8-9)
    # =========================================================================
    print("\n── GRUPO D: ARRANQUE DE MB ──\n")

    # --- PASO 8: Lanzamiento de subprocess ---
    if mb_dir_is_real and not mb_already_running:
        success, detail, launched_proc = _check_subprocess_launch(mb_dir)
        if success:
            r.pass_(8, "MB subprocess lanzado correctamente", detail)
        else:
            r.fail(8, "MB subprocess falló al arrancar", detail)
    elif mb_already_running:
        r.skip(8, "MB ya estaba corriendo", "Puerto ocupado detectado en paso 2")
    else:
        r.skip(8, "No se puede lanzar MB", "Directorio no encontrado")

    # --- PASO 9: MB responde a health check ---
    status_url = f"{mb_url.rstrip('/')}/api/status"

    if mb_already_running or (launched_proc and launched_proc.poll() is None):
        # Esperar con retries
        max_retries = 10
        retry_interval = 1.5
        last_status = 0
        last_error = ""
        last_body = None

        for attempt in range(1, max_retries + 1):
            last_status, last_error, last_body = _http_get(status_url, timeout=3.0)
            if last_status == 200:
                break
            print(f"         ... intento {attempt}/{max_retries} — HTTP {last_status} ({last_error[:60] if last_error else 'OK'})" if last_status else f"         ... intento {attempt}/{max_retries} — {last_error[:60]}")
            time.sleep(retry_interval)

        if last_status == 200:
            r.pass_(9, "MB responde a GET /api/status",
                   f"HTTP 200 — body: {str(last_body)[:100]}")
        else:
            r.fail(9, "MB NO responde a GET /api/status",
                   f"Último intento: HTTP {last_status} — {last_error}")

            # Si tenemos el proceso lanzado por nosotros, mostrar su stderr
            if launched_proc and launched_proc.poll() is not None:
                r.warn(9, "MB subprocess ya terminó",
                       f"Exit code: {launched_proc.returncode}")
                try:
                    stderr_out = launched_proc.stderr.read().decode("utf-8", errors="replace")
                    if stderr_out.strip():
                        lines = stderr_out.strip().split("\n")[-8:]
                        print("         stderr del proceso:")
                        for line in lines:
                            print(f"         | {line}")
                except Exception:
                    pass
    else:
        r.skip(9, "No se puede verificar health check", "MB no está corriendo")

    # =========================================================================
    # GRUPO E: ENDPOINTS DE MB (pasos 10-12)
    # =========================================================================
    print("\n── GRUPO E: ENDPOINTS DE MB ──\n")

    # Determinar si MB está accesible para los siguientes pasos
    mb_accessible = False
    if mb_already_running:
        # Verificar que realmente responde
        st, _, _ = _http_get(status_url, timeout=3.0)
        mb_accessible = (st == 200)
    elif launched_proc and launched_proc.poll() is None:
        st, _, _ = _http_get(status_url, timeout=3.0)
        mb_accessible = (st == 200)

    # --- PASO 10: GET /api/models ---
    models_url = f"{mb_url.rstrip('/')}/api/models"
    if mb_accessible:
        status, error, body = _http_get(models_url, timeout=5.0)
        if status == 200:
            model_count = 0
            if isinstance(body, list):
                model_count = len(body)
            elif isinstance(body, dict) and "models" in body:
                model_count = len(body["models"])
            if model_count > 0:
                r.pass_(10, "GET /api/models funciona", f"HTTP 200 — {model_count} modelos")
            else:
                r.warn(10, "GET /api/models responde pero sin modelos",
                       f"HTTP 200 — body: {str(body)[:120]}")
        else:
            r.fail(10, "GET /api/models falló",
                   f"HTTP {status} — {error}")
    else:
        r.skip(10, "GET /api/models no verificado", "MB no está accesible")

    # --- PASO 11: POST /api/call (test mínimo) ---
    call_url = f"{mb_url.rstrip('/')}/api/call"
    if mb_accessible:
        test_payload = {
            "task_type": "chat",
            "user_prompt": "health check",
            "system_prompt": "Reply OK",
            "max_tokens": 10,
            "temperature": 0.0,
        }
        status, error, body = _http_post_json(call_url, test_payload, timeout=60.0)
        if status == 200 and body is not None:
            success = body.get("success", False)
            model_used = body.get("model_used", "?")
            provider = body.get("provider", "?")
            if success:
                r.pass_(11, "POST /api/call funciona",
                       f"HTTP 200 — modelo: {model_used} via {provider}")
            else:
                err_msg = body.get("error", "sin detalle")
                r.warn(11, "POST /api/call respondió pero falló la llamada",
                       f"error: {err_msg}")
        elif status == 0:
            r.fail(11, "POST /api/call — sin conexión", error)
        else:
            r.fail(11, "POST /api/call — error HTTP",
                   f"HTTP {status} — {error} — body: {str(body)[:120]}")
    else:
        r.skip(11, "POST /api/call no verificado", "MB no está accesible")

    # --- PASO 12: Simulación de ensure_mb_running() ---
    print("\n── GRUPO F: SIMULACIÓN COMPLETA ──\n")

    if mb_dir_is_real:
        # Simular lo que haría ensure_mb_running
        try:
            from core import mb_launcher as _ml

            # Reset estado interno del launcher
            _ml._mb_process = None

            # Si MB ya está corriendo (lo lanzamos nosotros), el launcher
            # debería detectarlo vía health check
            if mb_accessible:
                start = time.time()
                result = _ml.ensure_mb_running(mb_url, timeout=5.0)
                elapsed = time.time() - start
                if result:
                    r.pass_(12, "ensure_mb_running() retorna True",
                           f"MB ya estaba corriendo, detectado en {elapsed:.1f}s")
                else:
                    r.fail(12, "ensure_mb_running() retornó False",
                           "MB está accesible pero el launcher no lo detectó")
            else:
                # MB no está accesible — el launcher debería intentar lanzarlo
                # Pero como ya sabemos que falla (paso 8/9), solo verificamos
                # que la función no explota
                start = time.time()
                try:
                    result = _ml.ensure_mb_running(mb_url, timeout=3.0)
                    elapsed = time.time() - start
                    if result:
                        r.pass_(12, "ensure_mb_running() lanzó MB con éxito",
                               f"Lanzado y detectado en {elapsed:.1f}s")
                    else:
                        r.warn(12, "ensure_mb_running() retornó False (esperado)",
                               f"MB no accesible, intento completado en {elapsed:.1f}s")
                except Exception as e:
                    r.fail(12, "ensure_mb_running() lanzó excepción", str(e))
        except Exception as e:
            r.fail(12, "No se pudo importar mb_launcher para simulación", str(e))
    else:
        r.skip(12, "No se puede simular ensure_mb_running", "Directorio no encontrado")

    # =========================================================================
    # GRUPO G: VALIDACIÓN DE APP.PY (pasos 13-15)
    # =========================================================================
    print("\n── GRUPO G: VALIDACIÓN DE APP.PY ──\n")

    # Buscar app.py
    app_py_path = None
    for candidate_dir in [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'interface'),
        os.path.join(os.getcwd(), 'apa', 'interface'),
    ]:
        c = os.path.join(candidate_dir, 'app.py')
        if os.path.isfile(c):
            app_py_path = c
            break

    # --- PASO 13: app.py contiene la integración MB ---
    if app_py_path:
        rel_path = os.path.relpath(app_py_path, os.getcwd())
        try:
            with open(app_py_path, 'r', encoding='utf-8') as f:
                app_content = f.read()

            checks = {
                'initialize_router importado': 'from core.router import' in app_content and 'initialize_router' in app_content,
                'ensure_mb_running en startup': 'ensure_mb_running' in app_content,
                'model_broker.broker ELIMINADO': 'from model_broker.broker import ModelBroker' not in app_content,
                'initialize_router() llamado': 'initialize_router()' in app_content,
            }
            all_ok = True
            for check_name, check_result in checks.items():
                if not check_result:
                    all_ok = False
                    r.fail(13, f"app.py: {check_name}", f"No encontrado en {rel_path}")

            if all_ok:
                r.pass_(13, "app.py integración MB v7.2 correcta",
                       f"{rel_path} — 4/4 checks")
            else:
                r.fail(13, "app.py tiene código antiguo de MB",
                       f"Revisar {rel_path} — algunos checks fallaron")

        except Exception as e:
            r.fail(13, "Error leyendo app.py", str(e))
    else:
        r.skip(13, "No se encontró app.py", "No está en interface/app.py ni apa/interface/app.py")

    # --- PASO 14: app.py llama ensure_mb_running ANTES de initialize_router ---
    if app_py_path:
        try:
            with open(app_py_path, 'r', encoding='utf-8') as f:
                app_content = f.read()

            pos_ensure = app_content.find('ensure_mb_running')
            pos_init_router = app_content.find('initialize_router()')

            if pos_ensure > 0 and pos_init_router > 0:
                if pos_ensure < pos_init_router:
                    r.pass_(14, "Orden correcto: ensure_mb_running antes de initialize_router",
                           f"ensure_mb_running en pos {pos_ensure}, initialize_router() en pos {pos_init_router}")
                else:
                    r.fail(14, "Orden incorrecto: initialize_router ANTES de ensure_mb_running",
                           "MB podría no estar listo cuando el router intente conectar")
            else:
                r.skip(14, "No se puede verificar orden", "Alguna función no encontrada en app.py")
        except Exception as e:
            r.fail(14, "Error verificando orden", str(e))
    else:
        r.skip(14, "No se puede verificar orden", "app.py no encontrado")

    # --- PASO 15: Simulación del flujo completo (launcher + router) ---
    if mb_dir_is_real and mb_accessible:
        try:
            from core.router import initialize_router as _init_router
            report = _init_router()
            mode = report.get('startup_mode', '?')
            mb_avail = report.get('mb_available', False)
            ollama = report.get('ollama_ready', False)
            cached = report.get('cached_task_types', 0)

            if mb_avail:
                r.pass_(15, "initialize_router() completo — MB disponible",
                       f"modo={mode}, cache={cached} tareas, ollama={'OK' if ollama else 'N/A'}")
            else:
                r.warn(15, "initialize_router() completó pero MB no disponible",
                       f"modo={mode}, mb_available=False — verificar URL y puerto")
        except Exception as e:
            r.fail(15, "initialize_router() falló", str(e))
    else:
        r.skip(15, "No se puede simular initialize_router", "MB no está accesible")

    # =========================================================================
    # LIMPIEZA
    # =========================================================================
    if launched_proc and launched_proc.poll() is None:
        print("\n  Deteniendo MB subprocess lanzado por el diagnóstico...")
        _kill_process(launched_proc)
        print("  Proceso detenido.")

    # =========================================================================
    # RESUMEN
    # =========================================================================
    print()
    return r.summary()


# ============================================================================
# VALIDACIÓN AUTÓNOMA
# ============================================================================
if __name__ == "__main__":
    exit_code = run_diagnostic()
    sys.exit(exit_code)
