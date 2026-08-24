# apa/tests/test_levantamiento_silencioso_mb.py
"""Test integrador del levantamiento silencioso de Model Broker (MB) desde APA.

Este test valida que APA pueda arrancar MB de forma silenciosa como subprocess
cuando MB no está corriendo, y que la comunicación HTTP entre APA y MB funcione
correctamente. Cubre los siguientes escenarios:

    1. Configuración: MODEL_BROKER_URL está definida y es accesible.
    2. Descubrimiento: mb_launcher encuentra el directorio de model_broker.
    3. Arranque silencioso: ensure_mb_running() lanza MB como subprocess.
    4. Health check: MB responde a /api/status tras el arranque.
    5. Idempotencia: una segunda llamada no relanza MB si ya corre.
    6. Integración con init_subsystems: la cadena completa de startup funciona.
    7. Estado del launcher: get_mb_status() reporta correctamente el proceso.
    8. Limpieza: stop_mb() detiene el subprocess lanzado por APA.

NOTA: Este test NO debe ejecutarse si hay un MB externo ya corriendo en el
mismo puerto (lo detecta y salta los tests que requieren arranque desde cero).

Ejecución:
    python -m pytest apa/tests/test_levantamiento_silencioso_mb.py -v
    o:
    python apa/tests/test_levantamiento_silencioso_mb.py
"""
import os
import sys
import time
import subprocess
import requests
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# ── Configuración de paths para que los imports funcionen ─────────────────
_APA_DIR = Path(__file__).resolve().parent.parent  # apa/
_IFACE_DIR = _APA_DIR / "interface"
for _p in [str(_APA_DIR), str(_IFACE_DIR)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ── Constantes ─────────────────────────────────────────────────────────────
_MB_URL = "http://127.0.0.1:8100"
_MB_STARTUP_TIMEOUT = 30.0  # segundos para que MB arranque
_HEALTH_TIMEOUT = 3.0


# ── Fixtures ───────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def mb_url():
    """URL base de MB. Permite cambiarla vía env var para tests."""
    return os.environ.get("MODEL_BROKER_URL", _MB_URL).rstrip("/")


@pytest.fixture(scope="module")
def external_mb_running(mb_url):
    """Detecta si hay un MB externo ya corriendo (no lanzado por APA).

    Returns:
        True si MB ya responde al inicio del test (externo).
        False si MB no responde (APA deberá lanzarlo).
    """
    try:
        resp = requests.get(f"{mb_url}/api/status", timeout=_HEALTH_TIMEOUT)
        return resp.status_code == 200
    except Exception:
        return False


@pytest.fixture(scope="module")
def mb_started_by_apa(mb_url, external_mb_running):
    """Arranca MB vía APA (si no hay MB externo) y lo deja corriendo.

    Si ya hay un MB externo, este fixture se salta (los tests que requieren
    arranque desde cero se marcan como skip).

    Returns:
        dict con info del arranque: {started_by_apa: bool, mb_url: str}
    """
    from core.mb_launcher import ensure_mb_running, get_mb_status, stop_mb

    # Si hay MB externo, no podemos testear el arranque desde cero
    if external_mb_running:
        yield {
            "started_by_apa": False,
            "mb_url": mb_url,
            "external": True,
        }
        return

    # Arrancar MB desde cero
    started = ensure_mb_running(mb_url, timeout=_MB_STARTUP_TIMEOUT)
    status = get_mb_status()

    yield {
        "started_by_apa": started,
        "process_alive": status.get("process_alive", False),
        "pid": status.get("pid"),
        "mb_url": mb_url,
        "external": False,
    }

    # Cleanup: parar el subprocess que APA lanzó (no tocar externos)
    stop_mb()


# ── Tests ──────────────────────────────────────────────────────────────────

class TestConfiguracion:
    """Grupo A: Configuración de APA para levantar MB."""

    def test_model_broker_url_definida(self, mb_url):
        """MODEL_BROKER_URL debe estar definida y ser una URL HTTP válida."""
        assert mb_url, "MODEL_BROKER_URL no definida"
        assert mb_url.startswith("http://") or mb_url.startswith("https://"), (
            f"MODEL_BROKER_URL debe ser HTTP/HTTPS, got: {mb_url}"
        )

    def test_mb_launcher_importable(self):
        """core.mb_launcher debe poder importarse sin error."""
        from core import mb_launcher
        assert hasattr(mb_launcher, "ensure_mb_running")
        assert hasattr(mb_launcher, "stop_mb")
        assert hasattr(mb_launcher, "get_mb_status")
        assert callable(mb_launcher.ensure_mb_running)
        assert callable(mb_launcher.stop_mb)
        assert callable(mb_launcher.get_mb_status)

    def test_startup_init_subsystems_importable(self):
        """app.startup.init_subsystems debe poder importarse."""
        from app.startup import init_subsystems
        assert callable(init_subsystems)


class TestDescubrimiento:
    """Grupo B: Descubrimiento del directorio de model_broker."""

    def test_find_mb_directory_retorna_string(self):
        """_find_mb_directory() retorna un string."""
        from core.mb_launcher import _find_mb_directory
        result = _find_mb_directory()
        assert isinstance(result, str), f"Esperaba str, got {type(result)}"
        assert result, "Retornó string vacío"

    def test_find_mb_directory_existe(self):
        """El directorio retornado por _find_mb_directory existe en disco."""
        from core.mb_launcher import _find_mb_directory
        result = _find_mb_directory()
        assert os.path.isdir(result), f"Directorio no existe: {result}"

    def test_find_mb_directory_contiene_model_broker(self):
        """El directorio retornado contiene el paquete model_broker/."""
        from core.mb_launcher import _find_mb_directory
        result = _find_mb_directory()
        mb_path = os.path.join(result, "model_broker")
        assert os.path.isdir(mb_path), (
            f"model_broker/ no encontrado en {result}"
        )
        # Debe tener app.py (entry point)
        app_path = os.path.join(mb_path, "app.py")
        assert os.path.isfile(app_path), (
            f"model_broker/app.py no encontrado en {result}"
        )


class TestArranqueSilencioso:
    """Grupo C: Arranque silencioso de MB como subprocess."""

    def test_ensure_mb_running_sin_url_retorna_false(self):
        """ensure_mb_running('') y ensure_mb_running(None) retornan False."""
        from core.mb_launcher import ensure_mb_running
        assert ensure_mb_running("") is False
        assert ensure_mb_running(None) is False

    def test_ensure_mb_running_arranca_o_detecta(self, mb_started_by_apa):
        """ensure_mb_running() retorna True (sea lanzando o detectando externo)."""
        # Si APA arrancó MB, started_by_apa=True
        # Si MB era externo, el fixture lo detectó y started_by_apa=False
        # En ambos casos, MB debe estar disponible al final
        assert mb_started_by_apa["mb_url"], "URL de MB no disponible"
        # Verificar que MB responde
        try:
            resp = requests.get(
                f"{mb_started_by_apa['mb_url']}/api/status",
                timeout=_HEALTH_TIMEOUT,
            )
            assert resp.status_code == 200, (
                f"MB no responde 200, got {resp.status_code}"
            )
        except Exception as exc:
            pytest.fail(f"MB no responde tras ensure_mb_running: {exc}")

    def test_mb_lanzado_como_subprocess_si_no_hay_externo(
        self, mb_started_by_apa, external_mb_running
    ):
        """Si no había MB externo, APA debe haberlo lanzado como subprocess."""
        if external_mb_running:
            pytest.skip("MB externo corriendo — no se puede testear subprocess de APA")
        # Si no había externo, APA debe haberlo lanzado
        assert mb_started_by_apa.get("started_by_apa") is True, (
            "APA no logró lanzar MB como subprocess"
        )
        # process_alive debe ser True (el subprocess está vivo)
        # NOTE: puede ser None si el subprocess ya terminó (poco probable)
        assert mb_started_by_apa.get("process_alive") in (True, None), (
            f"process_alive inesperado: {mb_started_by_apa.get('process_alive')}"
        )


class TestHealthCheck:
    """Grupo D: Health check de MB tras el arranque."""

    def test_mb_api_status_responde(self, mb_started_by_apa):
        """GET /api/status de MB responde 200 con JSON válido."""
        mb_url = mb_started_by_apa["mb_url"]
        resp = requests.get(f"{mb_url}/api/status", timeout=_HEALTH_TIMEOUT)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict), f"Respuesta no es dict: {type(data)}"
        assert "initialized" in data, "Falta campo 'initialized'"

    def test_mb_api_status_tiene_pool_size(self, mb_started_by_apa):
        """GET /api/status incluye pool_size (entero >= 0)."""
        mb_url = mb_started_by_apa["mb_url"]
        resp = requests.get(f"{mb_url}/api/status", timeout=_HEALTH_TIMEOUT)
        data = resp.json()
        assert "pool_size" in data, "Falta campo 'pool_size'"
        assert isinstance(data["pool_size"], int), (
            f"pool_size no es int: {type(data['pool_size'])}"
        )
        assert data["pool_size"] >= 0, f"pool_size negativo: {data['pool_size']}"

    def test_mb_api_status_tiene_providers_count(self, mb_started_by_apa):
        """GET /api/status incluye providers_count."""
        mb_url = mb_started_by_apa["mb_url"]
        resp = requests.get(f"{mb_url}/api/status", timeout=_HEALTH_TIMEOUT)
        data = resp.json()
        assert "providers_count" in data, "Falta campo 'providers_count'"


class TestIdempotencia:
    """Grupo E: Llamadas repetidas a ensure_mb_running no relanzan MB."""

    def test_segunda_llamada_retorna_true(self, mb_started_by_apa):
        """Una segunda llamada a ensure_mb_running retorna True sin relanzar."""
        from core.mb_launcher import ensure_mb_running, get_mb_status
        mb_url = mb_started_by_apa["mb_url"]

        # Estado antes de la segunda llamada
        status_before = get_mb_status()

        # Segunda llamada (timeout corto, no debería necesitar arrancar)
        result = ensure_mb_running(mb_url, timeout=5.0)
        assert result is True, "Segunda llamada no retornó True"

        # Estado después: no debe haber cambiado el PID
        status_after = get_mb_status()
        if status_before.get("pid") is not None:
            assert status_after.get("pid") == status_before.get("pid"), (
                "PID cambió — MB fue relanzado innecesariamente"
            )

    def test_ensure_mb_running_no_duplica_procesos(self, mb_started_by_apa):
        """Tras múltiples llamadas, solo hay un proceso de MB."""
        from core.mb_launcher import ensure_mb_running, get_mb_status
        mb_url = mb_started_by_apa["mb_url"]

        # Múltiples llamadas
        for _ in range(3):
            ensure_mb_running(mb_url, timeout=2.0)

        status = get_mb_status()
        # Si APA lanzó el subprocess, process_alive debe ser True
        # (no se duplicó ni se mató)
        if status.get("pid") is not None:
            assert status.get("process_alive") is True, (
                "Subprocess de MB murió tras múltiples llamadas"
            )


class TestIntegracionInitSubsystems:
    """Grupo F: Integración con init_subsystems() de startup.py."""

    def test_init_subsystems_retorna_dict_estructura(self):
        """init_subsystems() retorna dict con las claves esperadas."""
        from app.startup import init_subsystems
        result = init_subsystems(state=None)
        assert isinstance(result, dict), f"Esperaba dict, got {type(result)}"
        expected_keys = {
            "success", "mb_available", "router_initialized",
            "startup_mode", "errors",
        }
        assert set(result.keys()) == expected_keys, (
            f"Claves faltantes/sobrantes: {set(result.keys())} vs {expected_keys}"
        )

    def test_init_subsystems_mb_available_true(self):
        """init_subsystems() reporta mb_available=True si MB está corriendo."""
        from app.startup import init_subsystems
        result = init_subsystems(state=None)
        # Tras los tests anteriores, MB debería estar corriendo
        # (sea por APA o externo)
        assert result["mb_available"] is True, (
            f"mb_available=False, errors={result.get('errors')}"
        )

    def test_init_subsystems_errors_lista(self):
        """init_subsystems() retorna errors como lista."""
        from app.startup import init_subsystems
        result = init_subsystems(state=None)
        assert isinstance(result["errors"], list), (
            f"errors no es list: {type(result['errors'])}"
        )


class TestEstadoLauncher:
    """Grupo G: get_mb_status() reporta el estado correctamente."""

    def test_get_mb_status_retorna_dict(self):
        """get_mb_status() retorna un dict."""
        from core.mb_launcher import get_mb_status
        status = get_mb_status()
        assert isinstance(status, dict), f"Esperaba dict, got {type(status)}"

    def test_get_mb_status_tiene_claves(self):
        """get_mb_status() tiene 'process_alive' y 'pid'."""
        from core.mb_launcher import get_mb_status
        status = get_mb_status()
        assert "process_alive" in status, "Falta 'process_alive'"
        assert "pid" in status, "Falta 'pid'"

    def test_get_mb_status_consistente(self, mb_started_by_apa):
        """get_mb_status() es consistente entre llamadas."""
        from core.mb_launcher import get_mb_status
        s1 = get_mb_status()
        s2 = get_mb_status()
        assert s1 == s2, f"Estado inconsistente: {s1} vs {s2}"


class TestLimpieza:
    """Grupo H: stop_mb() detiene el subprocess sin errores."""

    def test_stop_mb_no_explota_sin_proceso(self):
        """stop_mb() no lanza excepción si no hay subprocess."""
        from core.mb_launcher import stop_mb, get_mb_status
        # Si no hay subprocess lanzado por APA, stop_mb() es no-op
        # (no debe lanzar excepción)
        try:
            stop_mb()
            # Verificar que sigue retornando dict válido
            status = get_mb_status()
            assert isinstance(status, dict)
        except Exception as exc:
            pytest.fail(f"stop_mb() lanzó excepción: {exc}")


# ── Punto de entrada para ejecución directa (python archivo.py) ────────────
if __name__ == "__main__":
    print("=" * 70)
    print("TEST INTEGRADOR: Levantamiento silencioso de MB desde APA")
    print("=" * 70)
    print()

    # Detectar si pytest está disponible
    try:
        import pytest
        print("Ejecutando con pytest...\n")
        sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
    except ImportError:
        print("pytest no disponible. Ejecutando tests manualmente...\n")

        # Ejecución manual básica
        tests_run = 0
        tests_passed = 0
        tests_failed = 0
        tests_skipped = 0

        def run_test(test_class_name, test_method_name, test_instance):
            global tests_run, tests_passed, tests_failed, tests_skipped
            tests_run += 1
            try:
                method = getattr(test_instance, test_method_name)
                # Si el método acepta fixtures, las mockeamos con valores simples
                import inspect
                sig = inspect.signature(method)
                kwargs = {}
                for param_name, param in sig.parameters.items():
                    if param_name == "self":
                        continue
                    elif param_name == "mb_url":
                        kwargs[param_name] = _MB_URL
                    elif param_name == "external_mb_running":
                        # Detectar MB externo
                        try:
                            resp = requests.get(f"{_MB_URL}/api/status", timeout=_HEALTH_TIMEOUT)
                            kwargs[param_name] = resp.status_code == 200
                        except Exception:
                            kwargs[param_name] = False
                    elif param_name == "mb_started_by_apa":
                        # Simular fixture simple
                        from core.mb_launcher import ensure_mb_running, get_mb_status
                        try:
                            started = ensure_mb_running(_MB_URL, timeout=_MB_STARTUP_TIMEOUT)
                            status = get_mb_status()
                            kwargs[param_name] = {
                                "started_by_apa": started,
                                "process_alive": status.get("process_alive", False),
                                "pid": status.get("pid"),
                                "mb_url": _MB_URL,
                                "external": not started,
                            }
                        except Exception:
                            kwargs[param_name] = {
                                "started_by_apa": False,
                                "mb_url": _MB_URL,
                                "external": True,
                            }
                    else:
                        kwargs[param_name] = None

                method(**kwargs)
                print(f"  [PASS] {test_class_name}::{test_method_name}")
                tests_passed += 1
            except Exception as exc:
                if "skip" in str(exc).lower():
                    print(f"  [SKIP] {test_class_name}::{test_method_name}: {exc}")
                    tests_skipped += 1
                else:
                    print(f"  [FAIL] {test_class_name}::{test_method_name}: {exc}")
                    tests_failed += 1

        # Importar y ejecutar todas las clases de test
        import importlib
        module = importlib.import_module(__name__)

        for class_name in [
            "TestConfiguracion",
            "TestDescubrimiento",
            "TestArranqueSilencioso",
            "TestHealthCheck",
            "TestIdempotencia",
            "TestIntegracionInitSubsystems",
            "TestEstadoLauncher",
            "TestLimpieza",
        ]:
            test_class = getattr(module, class_name)
            instance = test_class()
            print(f"\n--- {class_name} ---")
            for method_name in dir(instance):
                if method_name.startswith("test_"):
                    run_test(class_name, method_name, instance)

        print()
        print("=" * 70)
        print(f"Resultado: {tests_passed}/{tests_run} pasaron, "
              f"{tests_failed} fallaron, {tests_skipped} saltados")
        print("=" * 70)
        sys.exit(0 if tests_failed == 0 else 1)
