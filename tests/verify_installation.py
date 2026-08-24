#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_installation.py — Script de verificación autónoma de la instalación de APA.

Ejecuta 6 comprobaciones para confirmar que APA está correctamente instalado
y listo para ejecutarse. Imprime un informe detallado en la consola y lo guarda
en installation_report.txt.

Uso:
    python verify_installation.py
"""

import os
import sys
import json
import platform
import traceback
from datetime import datetime
from pathlib import Path

# =============================================================================
# Configuración de rutas (detección automática)
# =============================================================================
# Detectar la raíz del proyecto APA subiendo desde la ubicación de este script.
# Buscamos la carpeta que contiene 'apa/' como subdirectorio.
_THIS_DIR = Path(__file__).resolve().parent
_CANDIDATE = _THIS_DIR
for _UP in range(6):  # subir hasta 6 niveles como máximo
    if (_CANDIDATE / "apa" / "core" / "orchestrator.py").is_file():
        break
    _CANDIDATE = _CANDIDATE.parent
else:
    _CANDIDATE = _THIS_DIR.parent  # fallback: asume tests/ está dentro de apa/

APA_ROOT = _CANDIDATE
APA_PKG_DIR = APA_ROOT / "apa"          # Paquete principal (contiene config/, core/, agents/, mcp/)
PROVIDERS_DIR = APA_PKG_DIR / "core" / "data" / "providers"
# El informe se guarda junto al script, en la misma ubicación.
REPORT_PATH = _THIS_DIR / "installation_report.txt"

# Asegurar que el paquete 'apa' esté en sys.path
if str(APA_PKG_DIR) not in sys.path:
    sys.path.insert(0, str(APA_PKG_DIR))

# =============================================================================
# Utilidades de informe
# =============================================================================
report_lines = []


def log(text: str):
    """Imprime y acumula una línea en el informe."""
    print(text)
    report_lines.append(text)


def separator(char: str = "=", width: int = 72):
    log(char * width)


# =============================================================================
# Verificación 1: Versión de Python
# =============================================================================
def check_python_version() -> bool:
    """Verifica que Python 3.8+ esté disponible."""
    log("\n[1/6] Verificación de versión de Python")
    log("-" * 50)

    version = sys.version_info
    version_str = f"{version.major}.{version.minor}.{version.micro}"
    log(f"  Versión detectada: Python {version_str}")
    log(f"  Plataforma: {platform.system()} {platform.release()}")
    log(f"  Arquitectura: {platform.machine()}")
    log(f"  Ruta del intérprete: {sys.executable}")

    if version.major == 3 and version.minor >= 8:
        log("  ✅ PASADO — Python 3.8+ disponible")
        return True
    else:
        log(f"  ❌ FALLADO — Se requiere Python >= 3.8, se encontró {version.major}.{version.minor}")
        return False


# =============================================================================
# Verificación 2: Módulos core importables
# =============================================================================
def check_core_modules() -> bool:
    """Verifica que todos los módulos esenciales de APA puedan importarse."""
    log("\n[2/6] Verificación de módulos core")
    log("-" * 50)

    all_passed = True

    # ---- Dependencias externas ----
    log("  --- Dependencias externas ---")
    external_modules = {
        "fastapi": "FastAPI",
        "uvicorn": "Uvicorn",
        "pydantic": "Pydantic",
        "pydantic_settings": "Pydantic Settings",
        "requests": "Requests",
    }
    for module_name, display_name in external_modules.items():
        try:
            __import__(module_name)
            ver = getattr(sys.modules[module_name], "__version__", "desconocida")
            log(f"  ✅ {display_name} ({module_name}) — v{ver}")
        except ImportError as e:
            log(f"  ❌ {display_name} ({module_name}) — ImportError: {e}")
            all_passed = False

    # ---- Módulos de configuración APA ----
    log("  --- Módulos de configuración ---")
    config_modules = [
        ("config.settings", "config/settings.py"),
    ]
    for mod_name, file_ref in config_modules:
        try:
            __import__(mod_name)
            log(f"  ✅ {mod_name} ({file_ref})")
        except ImportError as e:
            log(f"  ❌ {mod_name} ({file_ref}) — {e}")
            all_passed = False
        except Exception as e:
            log(f"  ⚠️  {mod_name} ({file_ref}) — Error inesperado: {type(e).__name__}: {e}")
            all_passed = False

    # ---- Módulos core APA ----
    log("  --- Módulos core APA ---")
    core_modules = [
        ("core.orchestrator", "Orquestador"),
        ("core.assembler", "Ensamblador"),
        ("core.planner", "Planificador"),
        ("core.router", "Router LLM"),
        ("core.providers", "Proveedores LLM"),
        ("core.error_handler", "Gestor de errores"),
        ("core.snapshot_manager", "Gestor de snapshots"),
        ("core.refactor_guard", "Guardia de refactorización"),
        ("core.symbol_graph", "Grafo de símbolos"),
        ("core.spec_builder", "Constructor de especificaciones"),
    ]
    for mod_name, display in core_modules:
        try:
            __import__(mod_name)
            log(f"  ✅ {display} ({mod_name})")
        except ImportError as e:
            log(f"  ❌ {display} ({mod_name}) — ImportError: {e}")
            all_passed = False
        except Exception as e:
            log(f"  ⚠️  {display} ({mod_name}) — Error inesperado: {type(e).__name__}: {e}")
            all_passed = False

    # ---- Agentes APA ----
    log("  --- Agentes APA ---")
    agent_modules = [
        ("agents.generator", "Generador"),
        ("agents.corrector", "Corrector"),
        ("agents.documenter", "Documentador"),
    ]
    for mod_name, display in agent_modules:
        try:
            __import__(mod_name)
            log(f"  ✅ {display} ({mod_name})")
        except ImportError as e:
            log(f"  ❌ {display} ({mod_name}) — ImportError: {e}")
            all_passed = False
        except Exception as e:
            log(f"  ⚠️  {display} ({mod_name}) — Error inesperado: {type(e).__name__}: {e}")
            all_passed = False

    # ---- MCP ----
    log("  --- MCP (Model Context Protocol) ---")
    mcp_modules = [
        ("mcp.server", "Servidor MCP (NASConnector)"),
    ]
    for mod_name, display in mcp_modules:
        try:
            __import__(mod_name)
            log(f"  ✅ {display} ({mod_name})")
        except ImportError as e:
            log(f"  ❌ {display} ({mod_name}) — ImportError: {e}")
            all_passed = False
        except Exception as e:
            log(f"  ⚠️  {display} ({mod_name}) — Error inesperado: {type(e).__name__}: {e}")
            all_passed = False

    if all_passed:
        log("  ✅ PASADO — Todos los módulos core importados correctamente")
    else:
        log("  ❌ FALLADO — Uno o más módulos no pudieron importarse")
    return all_passed


# =============================================================================
# Verificación 3: Configuración (settings)
# =============================================================================
def check_configuration() -> bool:
    """Verifica que la configuración pueda cargarse y que las rutas clave existan."""
    log("\n[3/6] Verificación de configuración (settings)")
    log("-" * 50)

    passed = True

    # Intentar cargar settings
    try:
        from config.settings import settings
        log(f"  ✅ Settings cargados correctamente")
    except ValueError as e:
        # Settings lanza ValueError cuando no hay ningún proveedor configurado
        log(f"  ❌ Settings — Error de validación: {e}")
        log("  ⚠️  No se detectó ninguna API key configurada. Configure al menos un proveedor en .env")
        return False
    except Exception as e:
        log(f"  ❌ Settings — Error al cargar: {type(e).__name__}: {e}")
        return False

    # Verificar campos de configuración clave
    log("  --- Campos de configuración ---")
    key_attrs = [
        "openrouter_api_key", "anthropic_api_key", "openai_api_key",
        "groq_api_key", "github_token", "together_api_key",
        "cerebras_api_key", "siliconflow_api_key", "google_api_key",
        "deepseek_api_key", "mistral_api_key", "ollama_base_url",
        "sandbox_type", "sandbox_path", "log_level", "usage_db_path",
        "provider_priority",
    ]
    for attr in key_attrs:
        val = getattr(settings, attr, "<no definido>")
        if isinstance(val, str) and len(val) > 40:
            display_val = val[:37] + "..."
        else:
            display_val = val
        log(f"    {attr} = {display_val}")

    # Verificar rutas clave
    log("  --- Rutas clave ---")
    paths_to_check = {
        "Directorio raíz APA": APA_ROOT,
        "Paquete apa/": APA_PKG_DIR,
        "Directorio core/": APA_PKG_DIR / "core",
        "Directorio agents/": APA_PKG_DIR / "agents",
        "Directorio config/": APA_PKG_DIR / "config",
        "Directorio mcp/": APA_PKG_DIR / "mcp",
        "Directorio interface/": APA_PKG_DIR / "interface",
        "Directorio specs/": APA_PKG_DIR / "specs",
        "Directorio cache/": APA_PKG_DIR / "cache",
    }
    for label, path in paths_to_check.items():
        if path.is_dir():
            log(f"  ✅ {label}: {path}")
        else:
            log(f"  ❌ {label}: {path} — NO EXISTE")
            passed = False

    # Verificar archivos clave
    log("  --- Archivos clave ---")
    files_to_check = {
        "config/settings.py": APA_PKG_DIR / "config" / "settings.py",
        "core/orchestrator.py": APA_PKG_DIR / "core" / "orchestrator.py",
        "core/providers.py": APA_PKG_DIR / "core" / "providers.py",
        "core/sandbox_config.py": APA_PKG_DIR / "core" / "sandbox_config.py",
        "interface/app.py": APA_PKG_DIR / "interface" / "app.py",
        "requirements.txt": APA_PKG_DIR / "requirements.txt",
    }
    for label, fpath in files_to_check.items():
        if fpath.is_file():
            log(f"  ✅ {label}")
        else:
            log(f"  ❌ {label} — NO EXISTE en {fpath}")
            passed = False

    # Contar proveedores configurados (API keys no vacías)
    api_key_fields = [
        "openrouter_api_key", "anthropic_api_key", "openai_api_key",
        "groq_api_key", "github_token", "together_api_key",
        "fireworks_api_key", "cerebras_api_key", "siliconflow_api_key",
        "sambanova_api_key", "google_api_key", "deepseek_api_key",
        "mistral_api_key", "novita_api_key", "cloudflare_api_token",
        "cohere_api_key",
    ]
    configured = [k for k in api_key_fields if getattr(settings, k, "").strip()]
    ollama_url = getattr(settings, "ollama_base_url", "").strip()
    log(f"  --- Proveedores configurados ---")
    log(f"  Proveedores con API key: {len(configured)}")
    if configured:
        for k in configured:
            log(f"    ✅ {k}")
    if ollama_url:
        log(f"    ✅ Ollama (URL: {ollama_url})")
    if not configured and not ollama_url:
        log(f"    ⚠️  No se detectó ningún proveedor configurado")

    if passed:
        log("  ✅ PASADO — Configuración cargada correctamente")
    else:
        log("  ❌ FALLADO — Problemas en la configuración o rutas")
    return passed


# =============================================================================
# Verificación 4: Configuración de sandbox
# =============================================================================
def check_sandbox() -> bool:
    """Verifica la configuración del sandbox (sandbox_config.py)."""
    log("\n[4/6] Verificación de sandbox (sandbox_config.py)")
    log("-" * 50)

    passed = True

    # Verificar que el módulo sandbox_config.py existe
    sandbox_config_path = APA_PKG_DIR / "core" / "sandbox_config.py"
    if not sandbox_config_path.is_file():
        log(f"  ❌ core/sandbox_config.py NO EXISTE en {sandbox_config_path}")
        return False

    log(f"  ✅ core/sandbox_config.py encontrado")

    # Intentar importar las clases principales sin instanciar
    try:
        from core.sandbox_config import SandboxType, SandboxConfig
        log(f"  ✅ SandboxType importado correctamente")
        log(f"  ✅ SandboxConfig importado correctamente")

        # Verificar tipos soportados
        types_list = [st.value for st in SandboxType]
        log(f"  Tipos de sandbox soportados: {', '.join(types_list)}")
    except ImportError as e:
        log(f"  ❌ Error al importar sandbox_config: {e}")
        return False
    except Exception as e:
        log(f"  ❌ Error inesperado al importar sandbox_config: {type(e).__name__}: {e}")
        return False

    # Verificar el sandbox local existe
    sandbox_local_path = APA_PKG_DIR / "core" / "sandbox_local.py"
    if sandbox_local_path.is_file():
        log(f"  ✅ core/sandbox_local.py encontrado (conector local)")
    else:
        log(f"  ⚠️  core/sandbox_local.py NO ENCONTRADO — el modo local puede no funcionar")
        passed = False

    # Intentar cargar settings para comprobar SANDBOX_TYPE
    try:
        from config.settings import settings
        sandbox_type = getattr(settings, "sandbox_type", "").strip()
        sandbox_path = getattr(settings, "sandbox_path", "").strip()

        if sandbox_type:
            log(f"  Tipo de sandbox configurado: {sandbox_type}")
            log(f"  Ruta del sandbox: {sandbox_path or '(por defecto)'}")

            # Validar tipo
            try:
                st = SandboxType(sandbox_type.lower())
                log(f"  ✅ Tipo de sandbox válido: {st.value}")
            except ValueError:
                log(f"  ❌ Tipo de sandbox '{sandbox_type}' no es válido. Opciones: {', '.join(types_list)}")
                passed = False

            # Validar campo requerido
            if not sandbox_path and sandbox_type.lower() != "local":
                log(f"  ⚠️  SANDBOX_PATH no está definido para tipo '{sandbox_type}'")
                passed = False
            elif sandbox_path:
                if Path(sandbox_path).is_dir():
                    log(f"  ✅ Ruta del sandbox existe: {sandbox_path}")
                else:
                    log(f"  ⚠️  Ruta del sandbox NO existe (se creará al ejecutar): {sandbox_path}")
        else:
            log(f"  ⚠️  SANDBOX_TYPE no está definido en la configuración")
            log(f"  Ejecute 'python apa/core/sandbox_setup.py' para configurar el sandbox")
            passed = False

    except ValueError:
        # No se pudieron cargar los settings (sin API keys) — usar info por defecto
        log(f"  ⚠️  No se pudo cargar settings para verificar sandbox_type")
        log(f"  (Esto puede deberse a que no hay proveedores API configurados)")
        passed = False
    except Exception as e:
        log(f"  ❌ Error al verificar sandbox desde settings: {type(e).__name__}: {e}")
        passed = False

    if passed:
        log("  ✅ PASADO — Configuración de sandbox correcta")
    else:
        log("  ❌ FALLADO — Problemas en la configuración del sandbox")
    return passed


# =============================================================================
# Verificación 5: Proveedores LLM (providers.json / caché)
# =============================================================================
def check_providers() -> bool:
    """Verifica que al menos un proveedor LLM esté configurado (API key o caché de modelos)."""
    log("\n[5/6] Verificación de proveedores LLM")
    log("-" * 50)

    passed = False

    # --- Comprobar API keys configuradas ---
    try:
        from config.settings import settings
    except ValueError:
        log("  ⚠️  No se pudieron cargar settings — no hay proveedores API configurados")
        log("  ⚠️  Configure al menos una API key en el archivo .env")
        # Aún así comprobar cachés existentes
    except Exception as e:
        log(f"  ❌ Error al cargar settings: {type(e).__name__}: {e}")
        return False

    # Contar proveedores con API key
    api_key_map = {
        "openrouter_api_key": "OpenRouter",
        "anthropic_api_key": "Anthropic",
        "openai_api_key": "OpenAI",
        "groq_api_key": "Groq",
        "github_token": "GitHub Models",
        "together_api_key": "Together AI",
        "fireworks_api_key": "Fireworks AI",
        "cerebras_api_key": "Cerebras",
        "siliconflow_api_key": "SiliconFlow",
        "sambanova_api_key": "SambaNova",
        "google_api_key": "Google Gemini",
        "deepseek_api_key": "DeepSeek",
        "mistral_api_key": "Mistral AI",
        "novita_api_key": "Novita AI",
        "cloudflare_api_token": "Cloudflare Workers AI",
        "cohere_api_key": "Cohere",
    }

    configured_providers = []
    for attr, name in api_key_map.items():
        val = getattr(settings, attr, "").strip()
        if val:
            # Ocultar la mayor parte de la key por seguridad
            masked = val[:8] + "..." + val[-4:] if len(val) > 12 else "***"
            configured_providers.append(name)
            log(f"  ✅ {name}: {masked}")

    ollama_url = getattr(settings, "ollama_base_url", "").strip()
    if ollama_url:
        configured_providers.append("Ollama (local)")
        log(f"  ✅ Ollama (local): {ollama_url}")

    if not configured_providers:
        log(f"  ⚠️  No se detectó ningún proveedor con API key configurada")
    else:
        log(f"  Total de proveedores configurados: {len(configured_providers)}")

    # --- Comprobar archivos de caché de proveedores ---
    log("  --- Archivos de caché de modelos ---")
    if PROVIDERS_DIR.is_dir():
        provider_files = sorted(PROVIDERS_DIR.glob("*.json"))
        log(f"  Directorio de proveedores: {PROVIDERS_DIR}")
        log(f"  Archivos de caché encontrados: {len(provider_files)}")
        for pf in provider_files:
            try:
                data = json.loads(pf.read_text(encoding="utf-8"))
                model_count = len(data.get("models", []))
                ts = data.get("timestamp", 0)
                ts_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else "desconocido"
                log(f"    ✅ {pf.name} — {model_count} modelos (cache: {ts_str})")
            except Exception as e:
                log(f"    ⚠️  {pf.name} — Error al leer: {e}")
        if provider_files:
            passed = True
    else:
        log(f"  ⚠️  Directorio de caché de proveedores no existe: {PROVIDERS_DIR}")

    # Verificar provider_priority
    priority = getattr(settings, "provider_priority", "")
    if priority:
        providers_in_priority = [p.strip() for p in priority.split(",") if p.strip()]
        log(f"  Orden de prioridad de proveedores: {len(providers_in_priority)} proveedores")
        log(f"    {', '.join(providers_in_priority[:8])}{'...' if len(providers_in_priority) > 8 else ''}")

    if passed:
        log("  ✅ PASADO — Al menos un proveedor LLM disponible")
    else:
        log("  ❌ FALLADO — No se detectaron proveedores LLM configurados ni cachés de modelos")
    return passed


# =============================================================================
# Verificación 6: Arranque de FastAPI
# =============================================================================
def check_fastapi_startup() -> bool:
    """Verifica que la aplicación FastAPI pueda importarse e inicializarse."""
    log("\n[6/6] Verificación de arranque de FastAPI")
    log("-" * 50)

    passed = True

    # Intentar importar la app FastAPI directamente
    # NOTA: interface/app.py importa muchos módulos en cascada, por lo que
    # es un buen indicador de que toda la cadena de dependencias funciona.
    log("  Intentando importar la aplicación FastAPI (interface.app)...")

    try:
        # Primero verificar que FastAPI se puede instanciar
        from fastapi import FastAPI
        test_app = FastAPI(title="Test APA")
        log(f"  ✅ FastAPI se puede instanciar correctamente")
    except Exception as e:
        log(f"  ❌ Error al instanciar FastAPI: {type(e).__name__}: {e}")
        passed = False
        if passed:
            log("  ✅ PASADO — FastAPI inicializado correctamente")
        else:
            log("  ❌ FALLADO — Error al inicializar FastAPI")
        return passed

    # Intentar importar el módulo de la app de APA
    log("  Importando interface/app.py (aplicación completa de APA)...")
    try:
        import interface.app as apa_app_module
        app = getattr(apa_app_module, "app", None)
        if app is not None:
            log(f"  ✅ Aplicación APA importada correctamente")
            log(f"    Título: {getattr(app, 'title', 'N/A')}")
            log(f"    Versión: {getattr(app, 'version', 'N/A')}")

            # Verificar que tiene rutas registradas
            routes_count = len(app.routes) if hasattr(app, "routes") else 0
            log(f"    Rutas registradas: {routes_count}")

            # Listar algunas rutas clave
            key_paths = ["/", "/api/run", "/api/status", "/api/chat"]
            for path in key_paths:
                found = any(
                    getattr(r, "path", None) == path
                    for r in app.routes
                ) if hasattr(app, "routes") else False
                if found:
                    log(f"    ✅ Ruta {path} registrada")
                else:
                    log(f"    ⚠️  Ruta {path} no encontrada")
        else:
            log(f"  ❌ No se encontró el objeto 'app' en interface/app.py")
            passed = False
    except ValueError as e:
        # ValueError típicamente proviene de Settings (sin API keys)
        log(f"  ❌ Error de validación al importar APA: {e}")
        log(f"  ⚠️  Configure al menos un proveedor LLM en .env para importar la app completa")
        passed = False
    except ImportError as e:
        log(f"  ❌ Error de importación al cargar interface/app.py: {e}")
        # Proporcionar detalle sobre qué falta
        missing_mod = str(e).strip().split(" ")[-1] if str(e) else "desconocido"
        log(f"  ⚠️  Módulo faltante: {missing_mod}")
        passed = False
    except Exception as e:
        log(f"  ❌ Error inesperado al importar APA: {type(e).__name__}: {e}")
        log(f"  Detalle: {traceback.format_exc()[-500:]}")
        passed = False

    if passed:
        log("  ✅ PASADO — Aplicación FastAPI lista para ejecutarse")
    else:
        log("  ❌ FALLADO — Problemas al inicializar la aplicación FastAPI")
    return passed


# =============================================================================
# Función principal
# =============================================================================
def main():
    """Ejecuta todas las verificaciones y genera el informe."""
    separator()
    log("  INFORME DE VERIFICACIÓN DE INSTALACIÓN — APA")
    log(f"  Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"  Directorio APA: {APA_ROOT}")
    log(f"  Paquete: {APA_PKG_DIR}")
    separator()

    results = {}

    # Ejecutar las 6 verificaciones
    results["Python >= 3.8"] = check_python_version()
    results["Módulos core"] = check_core_modules()
    results["Configuración (settings)"] = check_configuration()
    results["Sandbox"] = check_sandbox()
    results["Proveedores LLM"] = check_providers()
    results["FastAPI startup"] = check_fastapi_startup()

    # Resumen final
    separator()
    log("\n  RESUMEN FINAL")
    log("=" * 50)

    passed_count = sum(1 for v in results.values() if v)
    failed_count = sum(1 for v in results.values() if not v)

    for name, passed in results.items():
        status = "✅ PASADO" if passed else "❌ FALLADO"
        log(f"  {status} — {name}")

    separator()
    log(f"\n  Resultado: {passed_count}/6 comprobaciones PASADAS, {failed_count} FALLARON")
    separator()

    if failed_count == 0:
        log("\n  🎉 APA está correctamente instalado y listo para ejecutarse.\n")
        log("  Para iniciar el servidor:")
        log(f"    cd {APA_ROOT}")
        log("    python -m uvicorn apa.interface.app:app --host 0.0.0.0 --port 8000 --reload")
    else:
        log(f"\n  ⚠️  {failed_count} comprobación(es) fallaron. Revise los errores arriba.")
        log("  Pasos sugeridos:")
        log("    1. Asegúrese de tener Python 3.8+ instalado")
        log("    2. Instale dependencias: pip install -r apa/requirements.txt")
        log("    3. Configure al menos un proveedor LLM en el archivo .env")
        log("    4. Configure el sandbox: python apa/core/sandbox_setup.py")

    separator()
    log("")

    # Escribir el informe a archivo
    try:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(REPORT_PATH, "w", encoding="utf-8") as f:
            f.write("\n".join(report_lines))
        print(f"Informe guardado en: {REPORT_PATH}")
    except Exception as e:
        print(f"⚠️  Error al guardar el informe: {e}")

    # Código de salida: 0 si todo pasó, 1 si algo falló
    return 0 if failed_count == 0 else 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
