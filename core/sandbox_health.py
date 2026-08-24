# apa/core/sandbox_health.py
"""
sandbox_health.py — Detección de lenguajes instalados en el sandbox local.

Eje 4 (propuesta 4A) del DPCA aprobado por el Director:
- Detecta qué lenguajes APA puede ejecutar localmente.
- No instala nada automáticamente.
- Informa al usuario SÓLO cuando una tarea requiere un lenguaje no disponible.

Uso:
    from core.sandbox_health import detect_available_languages, is_language_available

    # Detectar al arranque (una sola vez, cacheado)
    available = detect_available_languages()

    # Verificar antes de ejecutar una tarea
    if not is_language_available("dart"):
        # Informar al usuario: "Esta tarea requiere Dart, que no está instalado.
        # Opciones: (1) instálalo, (2) usa el NAS cuando esté disponible,
        # (3) omite esta tarea."
"""
from __future__ import annotations

import os
import sys
import shutil
import subprocess
import platform
import logging
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# ── Comandos a probar para cada lenguaje ───────────────────────────────────
# Cada lenguaje tiene uno o más comandos posibles. Si ALGUNO responde a
# `<cmd> --version` con código 0, el lenguaje se considera disponible.
_LANGUAGE_COMMANDS: Dict[str, List[List[str]]] = {
    "python": [
        ["python", "--version"],
        ["python3", "--version"],
    ],
    "javascript": [
        ["node", "--version"],
    ],
    "typescript": [
        # TypeScript requiere Node + tsc
        ["tsc", "--version"],
        ["npx", "tsc", "--version"],
    ],
    "bash": [
        ["bash", "--version"],
        # En Windows, Git Bash suele estar en una ruta fija
        ["C:\\Program Files\\Git\\bin\\bash.exe", "--version"],
    ],
    "sql": [
        ["sqlite3", "--version"],
    ],
    "cpp": [
        ["g++", "--version"],
        ["cl", "/?"],  # MSVC en Windows
        ["clang++", "--version"],
    ],
    "dart": [
        ["dart", "--version"],
    ],
    "react-native": [
        # react-native CLI requiere Node + npx
        ["npx", "react-native", "--version"],
    ],
}

# ── Mensajes amigables para el usuario ─────────────────────────────────────
_LANGUAGE_INSTALL_HINTS: Dict[str, str] = {
    "python": "Python: viene con APA, no debería faltar.",
    "javascript": "JavaScript: instala Node.js desde https://nodejs.org/",
    "typescript": "TypeScript: instala Node.js y luego ejecuta 'npm install -g typescript'.",
    "bash": "Bash: en Windows, instala Git Bash desde https://git-scm.com/",
    "sql": "SQL: instala SQLite desde https://sqlite.org/download.html",
    "cpp": "C++: instala MinGW (g++) o Visual Studio Build Tools (cl).",
    "dart": "Dart: instala el SDK desde https://dart.dev/get-dart",
    "react-native": "React Native: instala Node.js y luego 'npm install -g react-native-cli'.",
}


# ── Cache a nivel de módulo ────────────────────────────────────────────────
_CACHED_LANGUAGES: Optional[Set[str]] = None
_DETECTION_DONE: bool = False


def _check_command(cmd: List[str], timeout: float = 3.0) -> bool:
    """Ejecuta un comando y verifica si responde con código 0.

    Args:
        cmd: Lista con el comando y sus argumentos.
        timeout: Tiempo máximo de espera en segundos.

    Returns:
        True si el comando respondió con código 0, False en caso contrario.
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
            shell=(platform.system() == "Windows" and len(cmd) == 1),
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False
    except Exception:
        return False


def detect_available_languages(force: bool = False) -> Set[str]:
    """Detecta qué lenguajes APA puede ejecutar localmente.

    Procura cada comando de cada lenguaje con `<cmd> --version`.
    Si responde con código 0, el lenguaje se considera disponible.
    El resultado se cachea a nivel de módulo (la primera llamada tarda
    ~3-5s, las siguientes son instantáneas).

    Args:
        force: Si True, re-ejecuta la detección aunque ya esté cacheada.

    Returns:
        Set con los nombres de los lenguajes disponibles.
    """
    global _CACHED_LANGUAGES, _DETECTION_DONE

    if _DETECTION_DONE and not force:
        return _CACHED_LANGUAGES or set()

    _DETECTION_DONE = True
    available: Set[str] = set()

    logger.info("Detectando lenguajes instalados en el sandbox local...")
    for lang_name, commands in _LANGUAGE_COMMANDS.items():
        for cmd in commands:
            if _check_command(cmd):
                available.add(lang_name)
                logger.info("  ✓ %s disponible (%s)", lang_name, " ".join(cmd[:1]))
                break
        else:
            logger.info("  ✗ %s no disponible", lang_name)

    _CACHED_LANGUAGES = available
    total = len(_LANGUAGE_COMMANDS)
    logger.info(
        "Detección completa: %d/%d lenguajes disponibles (%s)",
        len(available), total, ", ".join(sorted(available)) if available else "ninguno"
    )
    return available


def is_language_available(language: str) -> bool:
    """Verifica si un lenguaje específico está disponible en el sandbox local.

    Args:
        language: Nombre del lenguaje (python, javascript, bash, sql, cpp,
                  dart, react-native, typescript).

    Returns:
        True si el lenguaje está disponible, False en caso contrario.
    """
    available = detect_available_languages()
    return language in available


def get_missing_languages(required: List[str]) -> List[str]:
    """Retorna los lenguajes requeridos que NO están disponibles.

    Útil para informar al usuario qué lenguajes faltan antes de
    ejecutar una tarea o un proyecto.

    Args:
        required: Lista de lenguajes que la tarea/proyecto necesita.

    Returns:
        Lista de lenguajes requeridos que no están instalados.
    """
    available = detect_available_languages()
    return [lang for lang in required if lang not in available]


def format_missing_languages_message(missing: List[str]) -> str:
    """Genera un mensaje amigable para el usuario cuando faltan lenguajes.

    Args:
        missing: Lista de lenguajes que faltan (de get_missing_languages).

    Returns:
        Mensaje en lenguaje natural con las opciones para el usuario.
    """
    if not missing:
        return ""

    lines = [
        "⚠️  Esta tarea requiere lenguajes que no están instalados en tu PC:",
        "",
    ]
    for lang in missing:
        hint = _LANGUAGE_INSTALL_HINTS.get(lang, f"{lang}: instala el intérprete correspondiente.")
        lines.append(f"  • {hint}")

    lines.extend([
        "",
        "Opciones:",
        "  1. Instala los lenguajes faltantes (arriba)",
        "  2. Usa el NAS cuando esté disponible (tiene todos los lenguajes)",
        "  3. Omite esta tarea (las demás seguirán ejecutándose)",
    ])
    return "\n".join(lines)


# ── Validación autónoma ────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 70)
    print("VALIDACIÓN AUTÓNOMA: core/sandbox_health.py")
    print("=" * 70)
    print()

    # 1. Detectar lenguajes
    print("--- 1. Detección de lenguajes ---")
    available = detect_available_languages(force=True)
    total = len(_LANGUAGE_COMMANDS)
    print(f"  Disponibles: {len(available)}/{total}")
    for lang in sorted(_LANGUAGE_COMMANDS.keys()):
        status = "✓" if lang in available else "✗"
        print(f"    {status} {lang}")
    print()

    # 2. is_language_available
    print("--- 2. is_language_available ---")
    assert is_language_available("python"), "Python debería estar disponible"
    print("  [OK] is_language_available('python') = True")
    # Verificar cacheo (debe ser instantáneo)
    import time
    start = time.time()
    is_language_available("javascript")
    elapsed = time.time() - start
    assert elapsed < 0.01, f"Cache no funcionó: {elapsed}s"
    print(f"  [OK] Cache funciona (2ª llamada: {elapsed:.4f}s)")
    print()

    # 3. get_missing_languages
    print("--- 3. get_missing_languages ---")
    missing = get_missing_languages(["python", "dart", "cpp"])
    print(f"  Lenguajes requeridos: python, dart, cpp")
    print(f"  Faltantes: {missing}")
    assert "python" not in missing, "Python no debería faltar"
    print("  [OK] get_missing_languages filtra correctamente")
    print()

    # 4. format_missing_languages_message
    print("--- 4. format_missing_languages_message ---")
    if missing:
        msg = format_missing_languages_message(missing)
        print(msg)
        assert "Opciones:" in msg, "Mensaje debe incluir opciones"
        print("  [OK] Mensaje generado correctamente")
    else:
        print("  [OK] No hay lenguajes faltantes, mensaje vacío")
    print()

    # 5. Estructura de datos
    print("--- 5. Estructura ---")
    assert isinstance(available, set), "detect_available_languages debe retornar set"
    assert all(isinstance(lang, str) for lang in available), "Elementos deben ser str"
    print("  [OK] detect_available_languages retorna Set[str]")
    print()

    print("=" * 70)
    print(f"Resultado: 5/5 tests pasaron")
    print("=" * 70)
