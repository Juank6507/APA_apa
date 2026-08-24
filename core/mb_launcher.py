# apa/core/mb_launcher.py
"""
Lanzador silencioso de Model Broker desde APA.

APA arranca MB como subprocess en background si no está corriendo.
MB se comunica con APA exclusivamente por HTTP — nunca como clase Python.

Uso desde APA (en el startup):
    from core.mb_launcher import ensure_mb_running
    ensure_mb_running(settings.model_broker_url)
"""
from __future__ import annotations

import sys
import os
import time
import subprocess
import logging
import requests

logger = logging.getLogger("core.mb_launcher")

_mb_process = None  # subprocess.Popen or None


def ensure_mb_running(mb_url: str, timeout: float = 15.0) -> bool:
    """Asegura que MB esté corriendo y respondiendo por HTTP.

    Flujo:
    1. Si MB ya responde (arrancado externamente o por APA) → retorna True.
    2. Si MB no responde → lanza MB como subprocess silencioso.
    3. Espera hasta ``timeout`` segundos a que MB esté listo.
    4. Si no levanta en tiempo → retorna False (APA usará emergency harness).

    Args:
        mb_url: URL base de MB, ej. ``http://127.0.0.1:8100``.
        timeout: Máximos segundos a esperar tras lanzar el subprocess.

    Returns:
        True si MB responde, False si no se pudo iniciar.
    """
    global _mb_process

    if not mb_url or not mb_url.strip():
        logger.debug("ensure_mb_running: sin URL configurada, skip")
        return False

    mb_url = mb_url.rstrip("/")

    # 1. Si ya tenemos un subprocess vivo, verificar si responde
    if _mb_process is not None and _mb_process.poll() is None:
        if _health_check(mb_url):
            return True
        # Proceso existe pero no responde — matar y relanzar
        logger.debug("MB subprocess vivo pero no responde, reiniciando...")
        _terminate_process(_mb_process)
        _mb_process = None

    # 2. Health check — MB puede haber sido arrancado externamente
    if _health_check(mb_url):
        logger.info("MB ya corriendo en %s", mb_url)
        return True

    # 3. Lanzar MB como subprocess silencioso
    cwd = _find_mb_directory()
    try:
        _mb_process = subprocess.Popen(
            [sys.executable, "-m", "model_broker.app"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,  # detach del process group de APA
            cwd=cwd,
        )
        logger.info("MB lanzado como subprocess (PID: %d, cwd: %s)", _mb_process.pid, cwd)
    except FileNotFoundError:
        logger.warning("No se encontró el módulo model_broker.app (cwd: %s)", cwd)
        return False
    except Exception as e:
        logger.warning("Error lanzando MB: %s", e)
        return False

    # 4. Esperar a que MB esté listo
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _mb_process.poll() is not None:
            logger.warning(
                "MB proceso salió con código %d", _mb_process.returncode
            )
            return False
        if _health_check(mb_url):
            elapsed = timeout - (deadline - time.time())
            logger.info("MB listo en %s (%.1fs)", mb_url, elapsed)
            return True
        time.sleep(0.5)

    logger.warning("MB no respondió en %.1fs", timeout)
    return False


def _health_check(mb_url: str, timeout: float = 3.0) -> bool:
    """Verifica si MB responde a GET /api/status."""
    try:
        resp = requests.get(
            f"{mb_url}/api/status", timeout=timeout
        )
        return resp.status_code == 200
    except Exception:
        return False


def _find_mb_directory() -> str:
    """Busca el directorio raíz donde está el paquete model_broker.

    Busca en orden:
    1. Hermano de ``apa/`` en el repo (``repo/model_broker/``).
    2. Directorio actual de trabajo.
    3. Fallback al directorio de este script.
    """
    # 1. Hermano de apa/ → raíz del repo
    try:
        this_dir = os.path.dirname(os.path.abspath(__file__))
        # this_dir = .../apa/core
        apa_dir = os.path.dirname(this_dir)          # .../apa
        repo_dir = os.path.dirname(apa_dir)           # .../repo
        if os.path.isdir(os.path.join(repo_dir, "model_broker")):
            return repo_dir
    except Exception:
        pass

    # 2. Directorio actual de trabajo
    if os.path.isdir(os.path.join(os.getcwd(), "model_broker")):
        return os.getcwd()

    # 3. Fallback
    return os.getcwd()


def _terminate_process(proc: subprocess.Popen) -> None:
    """Termina un subprocess de forma segura (SIGTERM → SIGKILL)."""
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def stop_mb() -> None:
    """Detiene el subprocess de MB si fue lanzado por APA.

    Se puede llamar en el shutdown de APA para limpieza.
    """
    global _mb_process
    if _mb_process is not None and _mb_process.poll() is None:
        logger.info("Deteniendo MB subprocess (PID: %d)", _mb_process.pid)
        _terminate_process(_mb_process)
        _mb_process = None


def get_mb_status() -> dict:
    """Retorna el estado del launcher: si hay proceso, PID, etc."""
    return {
        "process_alive": _mb_process is not None and _mb_process.poll() is None,
        "pid": _mb_process.pid if _mb_process and _mb_process.poll() is None else None,
    }


# =========================================================================
# VALIDACIÓN AUTÓNOMA
# =========================================================================
if __name__ == "__main__":
    passed = 0
    failed = 0

    def _check(name, condition):
        global passed, failed
        if condition:
            print(f"  [PASS] {name}")
            passed += 1
        else:
            print(f"  [FAIL] {name}")
            failed += 1

    import unittest.mock as mock

    print("\n" + "=" * 70)
    print("VALIDACIÓN AUTÓNOMA: core/mb_launcher.py")
    print("=" * 70)

    # --- 1. Funciones exportadas ---
    print("\n--- 1. Funciones exportadas ---")
    _check("ensure_mb_running", callable(ensure_mb_running))
    _check("stop_mb", callable(stop_mb))
    _check("get_mb_status", callable(get_mb_status))
    _check("_health_check", callable(_health_check))
    _check("_find_mb_directory", callable(_find_mb_directory))

    # --- 2. _find_mb_directory retorna string ---
    print("\n--- 2. _find_mb_directory ---")
    result = _find_mb_directory()
    _check("Retorna string", isinstance(result, str))
    _check("Directorio existe", os.path.isdir(result))

    # --- 3. ensure_mb_running sin URL retorna False ---
    print("\n--- 3. ensure_mb_running sin URL ---")
    _check("URL vacía → False", ensure_mb_running("") is False)
    _check("URL None → False", ensure_mb_running(None) is False)

    # --- 4. ensure_mb_running con URL que no responde ---
    print("\n--- 4. ensure_mb_running URL inalcanzable ---")
    # Mock subprocess.Popen para que no lance nada real
    _orig_health = _health_check
    _health_check = lambda *a, **kw: False
    try:
        with mock.patch("subprocess.Popen") as mock_popen:
            mock_proc = mock.MagicMock()
            mock_proc.poll.return_value = 42  # simulamos que el proceso sale
            mock_popen.return_value = mock_proc
            result = ensure_mb_running("http://127.0.0.1:19999", timeout=1.0)
        _check("Inalcanzable → False", result is False)
    finally:
        # Restaurar (a nivel de modulo)
        import types as _types
        _mod = _types.ModuleType("temp_fix")
        globals()['_health_check'] = _orig_health

    # --- 5. ensure_mb_running con health check OK (sin lanzar) ---
    print("\n--- 5. MB ya corriendo (sin lanzar) ---")
    _saved_hc = globals()['_health_check']
    globals()['_health_check'] = lambda *a, **kw: True
    try:
        result = ensure_mb_running("http://127.0.0.1:8100", timeout=1.0)
        _check("Ya corre → True", result is True)
    finally:
        globals()['_health_check'] = _saved_hc

    # --- 6. get_mb_status ---
    print("\n--- 6. get_mb_status ---")
    status = get_mb_status()
    _check("Retorna dict", isinstance(status, dict))
    _check("Tiene process_alive", "process_alive" in status)
    _check("Tiene pid", "pid" in status)

    # --- 7. stop_mb no explota sin proceso ---
    print("\n--- 7. stop_mb sin proceso ---")
    _mb_process = None
    try:
        stop_mb()
        _check("No explota", True)
    except Exception:
        _check("No explota", False)

    # --- 8. _health_check con URL inválida ---
    print("\n--- 8. _health_check ---")
    _check("URL inválida → False", _health_check("http://0.0.0.0:1", timeout=0.5) is False)

    # --- RESULTADO ---
    print("\n" + "-" * 70)
    total = passed + failed
    print(f"Resultado: {passed}/{total} tests pasaron")
    if failed > 0:
        print(f"FALLARON: {failed}")
    print("=" * 70)
    sys.exit(0 if failed == 0 else 1)
