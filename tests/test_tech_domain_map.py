# apa/tests/test_tech_domain_map.py
# =========================================================================
# TDM — Tech Domain Map: tests formales (pytest).
#
# Decisión 7 (Opción A) del Director: migrar los 10 tests internos que
# vivían en el bloque `if __name__ == "__main__"` de core/tech_domain_map.py
# a un archivo pytest formal para que formen parte de la suite CI.
#
# Cobertura:
#   - 10 casos de recommend_language() (los mismos del bloque __main__).
#   - 1 test de get_domain_knowledge_prompt() (no vacío).
#   - Tests adicionales sobre la estructura del módulo y la coexistencia
#     con LanguageDetector (Decisión 4).
# =========================================================================

import os
import sys
from pathlib import Path

import pytest

# ── Path setup para que `core.tech_domain_map` sea importable al ejecutar
#    pytest desde cualquier directorio (incluido sin instalar APA) ──
_THIS_DIR = Path(__file__).resolve()
_APA_ROOT = _THIS_DIR.parent.parent  # apa/
if str(_APA_ROOT) not in sys.path:
    sys.path.insert(0, str(_APA_ROOT))

from core.tech_domain_map import (
    DOMAIN_MAP,
    SKILL_MAP,
    FRAMEWORK_MAP,
    TechRecommendation,
    detect_domain,
    detect_skills,
    detect_framework,
    recommend_language,
    get_domain_knowledge_prompt,
)


# ── Casos migrados del bloque `if __name__ == "__main__"` ────────────────
# Cada caso conserva el texto original y el lenguaje esperado. Se
# mantienen los nombres descriptivos para que el output de pytest sea
# legible y útil para diagnóstico.

@pytest.mark.parametrize(
    "text, expected_language",
    [
        ("Crea un expert advisor para MetaTrader 5", "cpp"),
        ("App movil para gestionar inventario", "dart"),
        ("Bot de Telegram para alertas de precio", "python"),
        ("API REST con FastAPI para gestionar usuarios", "python"),
        ("Indicador técnico para TradingView", "javascript"),
        ("Script de bash para backup automático", "bash"),
        ("Dashboard de visualización de datos", "python"),
        ("Aplicación de escritorio con GUI", "python"),
        ("Componente React Native para lista de productos", "react-native"),
        ("Página web con Next.js", "javascript"),
    ],
    ids=[
        "metatrader_ea",
        "mobile_inventory",
        "telegram_bot",
        "fastapi_users",
        "tradingview_indicator",
        "bash_backup",
        "dashboard",
        "desktop_gui",
        "react_native_list",
        "nextjs_web",
    ],
)
def test_recommend_language_internal_cases(text, expected_language):
    """Los 10 casos internos migrados a pytest (Decisión 7).

    Cada caso verifica que recommend_language() retorne el lenguaje
    esperado para una descripción de proyecto típica.
    """
    result = recommend_language(text)
    assert isinstance(result, dict), f"recommend_language debe retornar dict, no {type(result)}"
    assert "language" in result, "result debe tener key 'language'"
    assert result["language"] == expected_language, (
        f"Texto: '{text}'\n"
        f"  Esperado: {expected_language}\n"
        f"  Recibido: {result['language']}\n"
        f"  Framework: {result.get('framework', '')}\n"
        f"  Detalles: {result.get('details', [])}"
    )


# ── Tests individuales (más fáciles de leer en el output de pytest) ─────

def test_recommend_language_metatrader():
    """Test 1: Expert advisor para MetaTrader 5 → cpp."""
    result = recommend_language("Crea un expert advisor para MetaTrader 5")
    assert result["language"] == "cpp"


def test_recommend_language_mobile_app():
    """Test 2: App móvil para inventario → dart."""
    result = recommend_language("App movil para gestionar inventario")
    assert result["language"] == "dart"


def test_recommend_language_telegram_bot():
    """Test 3: Bot de Telegram para alertas → python."""
    result = recommend_language("Bot de Telegram para alertas de precio")
    assert result["language"] == "python"


def test_recommend_language_fastapi_api():
    """Test 4: API REST con FastAPI → python."""
    result = recommend_language("API REST con FastAPI para gestionar usuarios")
    assert result["language"] == "python"


def test_recommend_language_tradingview_indicator():
    """Test 5: Indicador técnico para TradingView → javascript."""
    result = recommend_language("Indicador técnico para TradingView")
    assert result["language"] == "javascript"


def test_recommend_language_bash_script():
    """Test 6: Script de bash → bash."""
    result = recommend_language("Script de bash para backup automático")
    assert result["language"] == "bash"


def test_recommend_language_dashboard():
    """Test 7: Dashboard de visualización → python."""
    result = recommend_language("Dashboard de visualización de datos")
    assert result["language"] == "python"


def test_recommend_language_desktop_gui():
    """Test 8: Aplicación de escritorio con GUI → python."""
    result = recommend_language("Aplicación de escritorio con GUI")
    assert result["language"] == "python"


def test_recommend_language_react_native():
    """Test 9: Componente React Native → react-native."""
    result = recommend_language("Componente React Native para lista de productos")
    assert result["language"] == "react-native"


def test_recommend_language_nextjs_web():
    """Test 10: Página web con Next.js → javascript."""
    result = recommend_language("Página web con Next.js")
    assert result["language"] == "javascript"


# ── Tests sobre get_domain_knowledge_prompt() ──────────────────────────

def test_get_domain_knowledge_prompt_returns_nonempty_string():
    """get_domain_knowledge_prompt() debe retornar un string no vacío.

    Esta función se usa para inyectar la base de conocimiento de TDM en
    el system prompt del LLM (Decisiones 1+3 del Director).
    """
    prompt = get_domain_knowledge_prompt()
    assert isinstance(prompt, str), f"Debe retornar str, no {type(prompt)}"
    assert len(prompt) > 0, "El prompt no debe estar vacío"
    # Debe contener la regla de inferencia de lenguaje
    assert "REGLA" in prompt, "El prompt debe contener la regla de inferencia"
    assert "language" in prompt.lower(), "El prompt debe mencionar 'language'"


# ── Tests estructurales (bonus) ─────────────────────────────────────────

def test_recommend_language_result_structure():
    """recommend_language() siempre retorna un dict con las keys esperadas."""
    result = recommend_language("Crea un expert advisor para MetaTrader 5")
    expected_keys = {"language", "framework", "confidence", "source", "details", "notes"}
    assert expected_keys.issubset(set(result.keys())), (
        f"Faltan keys. Esperadas: {expected_keys}. Recibidas: {set(result.keys())}"
    )


def test_recommend_language_confidence_values():
    """confidence solo puede ser 'high', 'medium' o 'low'."""
    valid_confidences = {"high", "medium", "low"}
    test_texts = [
        "Crea un expert advisor para MetaTrader 5",  # high
        "App movil para gestionar inventario",       # high
        "xqz random text without meaningful keywords",  # variable
        "asdf qwer zxcv",                            # low
    ]
    for text in test_texts:
        result = recommend_language(text)
        assert result["confidence"] in valid_confidences, (
            f"confidence={result['confidence']!r} no válido para texto: {text!r}"
        )


def test_recommend_language_empty_text():
    """recommend_language('') no debe romper; debe retornar confidence='low'."""
    result = recommend_language("")
    assert result["confidence"] == "low"
    assert result["language"] == ""


def test_domain_map_has_entries():
    """DOMAIN_MAP debe tener entradas (es la capa 1 de mapeo)."""
    assert len(DOMAIN_MAP) > 0, "DOMAIN_MAP no debe estar vacío"


def test_skill_map_has_entries():
    """SKILL_MAP debe tener entradas (es la capa 2 de mapeo)."""
    assert len(SKILL_MAP) > 0, "SKILL_MAP no debe estar vacío"


def test_framework_map_has_entries():
    """FRAMEWORK_MAP debe tener entradas (es la capa 3 de mapeo)."""
    assert len(FRAMEWORK_MAP) > 0, "FRAMEWORK_MAP no debe estar vacío"


def test_tech_recommendation_is_frozen_dataclass():
    """TechRecommendation es un dataclass frozen (inmutable)."""
    rec = TechRecommendation(
        language="python",
        framework="FastAPI",
        keywords=("api", "rest"),
        notes="Test",
    )
    assert rec.language == "python"
    # Frozen: no se puede modificar
    with pytest.raises((AttributeError, Exception)):
        rec.language = "javascript"


def test_detect_domain_returns_list():
    """detect_domain() retorna una lista de TechRecommendation."""
    results = detect_domain("Crea un expert advisor para MetaTrader 5")
    assert isinstance(results, list)
    assert len(results) >= 1
    for r in results:
        assert isinstance(r, TechRecommendation)


def test_coexistencia_con_language_detector_decision_4():
    """Decisión 4 (Opción A) del Director: TDM y LanguageDetector coexisten.

    Verifica que los lenguajes recomendados por TDM que TAMBIÉN están en
    LANGUAGE_PROFILES (los del LanguageDetector) funcionen como puente
    entre los dos sistemas.
    """
    try:
        from core.language_profiles import LANGUAGE_PROFILES
    except ImportError:
        pytest.skip("core.language_profiles no disponible en este entorno")

    profile_names = {p.name for p in LANGUAGE_PROFILES}
    # Los lenguajes que recomendamos en los tests internos deben existir
    # en LANGUAGE_PROFILES para que la coexistencia funcione.
    test_cases = [
        ("Crea un expert advisor para MetaTrader 5", "cpp"),
        ("App movil para gestionar inventario", "dart"),
        ("Bot de Telegram para alertas de precio", "python"),
        ("Indicador técnico para TradingView", "javascript"),
        ("Script de bash para backup automático", "bash"),
        ("Componente React Native para lista de productos", "react-native"),
    ]
    for text, expected in test_cases:
        result = recommend_language(text)
        assert result["language"] == expected
        assert expected in profile_names, (
            f"El lenguaje recomendado por TDM '{expected}' debe existir "
            f"en LANGUAGE_PROFILES para que LanguageDetector pueda usarlo"
        )
