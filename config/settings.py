# apa/config/settings_v2.py
#
# v2.1 — Configuracion post-migracion a Model Broker.
# Sin API keys de providers externos. Todo el routing de LLMs
# pasa por Model Broker.
#
# Emergency fallback: solo Ollama (proveedor local).
# Si MB cae y no puede capturar modelos, se usa Ollama directo.
#
# Reemplaza a settings.py original.
#
# Variables de entorno:
#   MODEL_BROKER_URL         — URL del servicio Model Broker
#   MODEL_BROKER_API_KEY     — API key para autenticar con MB
#   OLLAMA_BASE_URL          — URL de Ollama local (default: http://localhost:11434)
#   OLLAMA_DEFAULT_MODEL     — Modelo Ollama por defecto (default: llama3.1)
#   APA_LOG_LEVEL            — Nivel de log (default: INFO)
#   NAS_SANDBOX_PATH         — Path sandbox (default: /tmp/apa_sandbox)
#
# Validacion:
#     python config/settings_v2.py

import os
import logging
from pathlib import Path
from typing import Dict, Optional, Any, List

logger = logging.getLogger(__name__)


# =========================================================================
# DOTENV LOADER — carga .env al entorno (sin dependencia externa)
# Reutiliza la misma lógica que model_broker/settings_bridge.py
# =========================================================================

def _find_and_load_dotenv() -> Optional[str]:
    """Busca .env en ubicaciones lógicas y carga sus variables al entorno.

    Prioridad (igual que MB settings_bridge.py):
      1. Raiz del paquete apa (el .env propio de APA)
      2. CWD
      3. Directorios padre ascendentes (repo compartido como fallback)

    Retorna la ruta del archivo cargado, o None.
    """
    candidates = []

    # PRIORIDAD 1: Raiz del paquete apa (el .env propio de APA)
    this_dir = Path(__file__).resolve().parent  # config/
    apa_dir = this_dir.parent                      # apa/
    candidates.append(("APA_ROOT", apa_dir / ".env"))

    # CWD
    candidates.append(("CWD", Path.cwd() / ".env"))

    # Padre de apa (repo compartido como fallback)
    repo_dir = apa_dir.parent                       # apa-repo/
    candidates.append(("APA_PARENT", repo_dir / ".env"))
    candidates.append(("APA_GRANDPARENT", repo_dir.parent / ".env"))

    # Subiendo desde CWD
    current = Path.cwd()
    for i in range(6):
        candidates.append((f"CWD_UP_{i}", current / ".env"))
        parent = current.parent
        if parent == current:
            break
        current = parent

    seen = set()
    for label, candidate in candidates:
        try:
            resolved = str(candidate.resolve())
        except Exception:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)

        try:
            with open(resolved, "r", encoding="utf-8-sig") as f:
                f.readline()  # solo verificar que es legible
            logger.debug("settings: .env encontrado en %s: %s", label, resolved)
            loaded = _load_dotenv_file(Path(resolved))
            logger.info("settings: .env cargado desde %s (%d variables)", label, loaded)
            return resolved
        except (FileNotFoundError, PermissionError):
            continue
        except Exception as e:
            logger.debug("settings: candidato %s: error: %s", label, e)
            continue

    logger.debug("settings: ningun .env encontrado en %d candidatos", len(seen))
    return None


def _load_dotenv_file(env_path: Path) -> int:
    """Carga un fichero .env simple (lineas KEY=VALUE, ignora # y vacias).

    Usa utf-8-sig para manejar BOM automaticamente.
    No sobreescribe variables ya definidas en el entorno.
    Retorna el numero de claves cargadas.
    """
    loaded = 0
    try:
        with open(env_path, "r", encoding="utf-8-sig") as f:
            for line_num, raw_line in enumerate(f, 1):
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("'\"")
                if not key:
                    continue
                if key not in os.environ:
                    os.environ[key] = value
                    loaded += 1
    except Exception as e:
        logger.warning("Error leyendo %s: %s", env_path, e)
    return loaded


# Cargar .env ANTES de crear el singleton Settings
_env_loaded_from = _find_and_load_dotenv()


# =========================================================================
# EMERGENCY CONFIG — Ollama como proveedor local de respaldo.
# No se usan claves externas (OpenRouter, etc.).
# Si MB cae y no puede capturar modelos, se intenta solo con Ollama.
# =========================================================================

_OLLAMA_CONFIG: Dict[str, str] = {}


def _load_ollama_config() -> Dict[str, str]:
    """Carga la configuracion de Ollama desde variables de entorno.

    Variables:
        OLLAMA_BASE_URL       — URL base de Ollama (ej: http://localhost:11434)
        OLLAMA_DEFAULT_MODEL  — modelo Ollama por defecto (ej: llama3.1)

    Ollama no necesita API key — es un proveedor local.
    """
    config = {}

    url = os.environ.get("OLLAMA_BASE_URL", "").strip()
    if url:
        config["ollama_base_url"] = url.rstrip("/")
    else:
        # Default: Ollama suele estar en localhost:11434
        config["ollama_base_url"] = "http://localhost:11434"

    model = os.environ.get("OLLAMA_DEFAULT_MODEL", "").strip()
    if model:
        config["ollama_model"] = model
    else:
        config["ollama_model"] = "llama3.1"

    return config


def get_emergency_keys() -> Dict[str, str]:
    """Retorna la configuracion de emergencia (Ollama).

    En v2.1 el emergency harness solo usa Ollama como proveedor
    local. No hay claves externas.

    Retorna dict con:
        - ollama_base_url: URL de Ollama
        - ollama_model: modelo por defecto
    """
    global _OLLAMA_CONFIG
    if not _OLLAMA_CONFIG:
        _OLLAMA_CONFIG = _load_ollama_config()
    return dict(_OLLAMA_CONFIG)


def has_emergency_keys() -> bool:
    """Retorna True si hay configuracion de emergencia (Ollama).

    Ollama siempre esta configurado (tiene default localhost:11434),
    por lo que siempre retorna True. La verificacion real de si
    Ollama esta corriendo se hace al intentar la llamada.
    """
    return True


def reload_emergency_keys() -> Dict[str, str]:
    """Recarga la configuracion de emergencia desde entorno.

    Util para hot-reload sin reiniciar la aplicacion.
    """
    global _OLLAMA_CONFIG
    _OLLAMA_CONFIG = _load_ollama_config()
    logger.info("Emergency config recargada: Ollama en %s", _OLLAMA_CONFIG.get("ollama_base_url"))
    return dict(_OLLAMA_CONFIG)


# =========================================================================
# MODEL BROKER CONFIG
# =========================================================================

def _get_mb_config() -> Dict[str, Any]:
    """Obtiene la configuracion de Model Broker desde entorno."""
    return {
        "url": os.environ.get("MODEL_BROKER_URL", "").strip(),
        "api_key": os.environ.get("MODEL_BROKER_API_KEY", "").strip(),
    }


# =========================================================================
# SETTINGS PRINCIPAL — objeto unico de configuracion
# =========================================================================

class Settings:
    """Configuracion centralizada de APA v2.1.

    Post-migracion: sin API keys de providers individuales.
    Todo via Model Broker + emergency Ollama (local).
    """

    # --- Model Broker ---
    @property
    def model_broker_url(self) -> str:
        return os.environ.get("MODEL_BROKER_URL", "").strip()

    @property
    def model_broker_api_key(self) -> str:
        return os.environ.get("MODEL_BROKER_API_KEY", "").strip()

    @property
    def model_broker_config(self) -> Dict[str, str]:
        return _get_mb_config()

    @property
    def model_broker_start_cmd(self) -> str:
        """Comando para arrancar MB en modo sandbox (desarrollo).

        Si esta vacio, APA no intenta arrancar MB localmente.
        Ejemplo: 'bun --hot index.ts'
        """
        return os.environ.get("MODEL_BROKER_START_CMD", "").strip()

    @property
    def model_broker_start_dir(self) -> str:
        """Directorio de trabajo para arrancar MB en modo sandbox.

        Lee SANDBOX_PATH del entorno (misma variable que el sandbox general).
        Si esta vacio, APA no intenta arrancar MB localmente.
        """
        return os.environ.get("SANDBOX_PATH", "").strip()

    # --- Emergency (Ollama local) ---
    @property
    def emergency_keys(self) -> Dict[str, str]:
        return get_emergency_keys()

    @property
    def has_emergency(self) -> bool:
        return has_emergency_keys()

    # --- Ollama directo ---
    @property
    def ollama_base_url(self) -> str:
        return get_emergency_keys().get("ollama_base_url", "http://localhost:11434")

    @property
    def ollama_default_model(self) -> str:
        return get_emergency_keys().get("ollama_model", "llama3.1")

    # --- General ---
    @property
    def log_level(self) -> str:
        return os.environ.get("APA_LOG_LEVEL", "INFO").strip()

    @property
    def nas_sandbox_path(self) -> str:
        return os.environ.get("NAS_SANDBOX_PATH", "/tmp/apa_sandbox").strip()

    @property
    def openrouter_api_key(self) -> str:
        """Backward compat — siempre vacio en v2.1.

        Los providers externos se gestionan via Model Broker.
        El emergency harness solo usa Ollama local.
        """
        return ""

    def __repr__(self) -> str:
        mb_url = self.model_broker_url or "(no configurada)"
        ollama = self.ollama_base_url
        return (f"Settings(mb_url={mb_url}, "
                f"ollama={ollama}, "
                f"log={self.log_level})")


# Singleton
settings = Settings()


# =========================================================================
# DIAGNOSTICO AL ARRANQUE
# =========================================================================

def _log_startup_warnings() -> None:
    """Advierte al arrancar si falta configuracion importante."""
    if _env_loaded_from:
        logger.info("settings: .env cargado desde %s", _env_loaded_from)
    else:
        logger.warning("settings: .env NO encontrado — usando variables de entorno del sistema")

    if not settings.model_broker_url:
        logger.warning(
            "settings: MODEL_BROKER_URL no configurada. "
            "APA operara en modo emergencia con Ollama local."
        )
    else:
        logger.info(
            "settings: Model Broker configurado en %s",
            settings.model_broker_url
        )

    if settings.model_broker_start_cmd:
        logger.info(
            "settings: MB sandbox configurado: cmd='%s', dir='%s'",
            settings.model_broker_start_cmd,
            settings.model_broker_start_dir,
        )
    else:
        logger.info(
            "settings: MB sandbox no configurado (sin MODEL_BROKER_START_CMD o SANDBOX_PATH)"
        )

    logger.info(
        "settings: Emergency fallback: Ollama en %s (modelo: %s)",
        settings.ollama_base_url,
        settings.ollama_default_model,
    )


_log_startup_warnings()


# =====================================================================
# TESTS AUTONOMOS
# =====================================================================
if __name__ == "__main__":
    import sys

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

    print("=" * 60)
    print("TESTS AUTONOMOS: settings_v2.py v2.1")
    print("=" * 60)

    # Test 1: get_emergency_keys retorna dict con ollama_base_url
    _OLLAMA_CONFIG = {}
    keys = get_emergency_keys()
    _check("get_emergency_keys retorna dict", isinstance(keys, dict))
    _check("get_emergency_keys tiene ollama_base_url", "ollama_base_url" in keys)
    _check("get_emergency_keys tiene ollama_model", "ollama_model" in keys)

    # Test 2: has_emergency_keys siempre True (Ollama tiene default)
    _OLLAMA_CONFIG = {}
    result = has_emergency_keys()
    _check("has_emergency_keys siempre True", result is True)

    # Test 3: get_emergency_keys retorna copia
    _OLLAMA_CONFIG = {}
    k1 = get_emergency_keys()
    k1["extra"] = "hack"
    k2 = get_emergency_keys()
    _check("get_emergency_keys retorna copia", "extra" not in k2)

    # Test 4: reload_emergency_keys
    _OLLAMA_CONFIG = {}
    reload_emergency_keys()
    _check("reload_emergency_keys no explota", True)

    # Test 5: Settings singleton existe
    _check("settings singleton existe", settings is not None)

    # Test 6: Settings.log_level
    _check("settings.log_level retorna str", isinstance(settings.log_level, str))

    # Test 7: Settings.nas_sandbox_path
    _check("settings.nas_sandbox_path retorna str", isinstance(settings.nas_sandbox_path, str))

    # Test 8: Settings.model_broker_config retorna dict
    config = settings.model_broker_config
    _check("settings.model_broker_config es dict", isinstance(config, dict))
    _check("model_broker_config tiene 'url'", "url" in config)
    _check("model_broker_config tiene 'api_key'", "api_key" in config)

    # Test 9: Settings.emergency_keys tiene campos Ollama
    _OLLAMA_CONFIG = {}
    ek = settings.emergency_keys
    _check("settings.emergency_keys retorna dict", isinstance(ek, dict))
    _check("emergency_keys tiene ollama_base_url", "ollama_base_url" in ek)
    _check("emergency_keys tiene ollama_model", "ollama_model" in ek)

    # Test 10: Settings.has_emergency
    _check("settings.has_emergency = True", settings.has_emergency is True)

    # Test 11: Settings.ollama_base_url
    _check("settings.ollama_base_url retorna str", isinstance(settings.ollama_base_url, str))
    _check("settings.ollama_base_url tiene localhost", "localhost" in settings.ollama_base_url)

    # Test 12: Settings.ollama_default_model
    _check("settings.ollama_default_model retorna str", isinstance(settings.ollama_default_model, str))

    # Test 13: openrouter_api_key siempre vacio
    _check("settings.openrouter_api_key vacio", settings.openrouter_api_key == "")

    # Test 14: Settings.repr no explota
    repr_str = repr(settings)
    _check("Settings.__repr__ funciona", isinstance(repr_str, str) and "Settings" in repr_str)

    # Test 15: No hay referencia a openrouter en emergency keys
    _OLLAMA_CONFIG = {}
    ek = get_emergency_keys()
    _check("emergency_keys NO tiene openrouter_api_key", "openrouter_api_key" not in ek)

    _OLLAMA_CONFIG = {}

    print("-" * 60)
    total = passed + failed
    print(f"Resultado: {passed}/{total} pasaron")
    print("=" * 60)
    sys.exit(0 if failed == 0 else 1)
