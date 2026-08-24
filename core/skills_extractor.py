# apa/core/skills_extractor.py
import sys
import os
import logging
import json
import ast
import re
from typing import Optional, Dict, Any
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from core.router import call_llm

logger = logging.getLogger(__name__)


def _clean_llm_response(text: str) -> str:
    """Elimina bloques markdown y aísla el diccionario Python/JSON."""
    cleaned = text.strip()
    cleaned = re.sub(r'^```(?:python|json)?\s*', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s*```$', '', cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip()
    first_brace = cleaned.find('{')
    last_brace = cleaned.rfind('}')
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        cleaned = cleaned[first_brace:last_brace + 1]
    return cleaned


def extract_skill(task_description: str, code: str, project_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Llama a un LLM para generar un diccionario SKILL basado en la tarea y el código.
    Retorna el diccionario si el LLM responde con un formato válido, o None en caso de error.
    """
    system_prompt = (
        "Eres un extractor de patrones de código experto. Tu única función es analizar "
        "una tarea y su código de solución exitoso para producir un diccionario SKILL "
        "en formato Python válido. "
        "El diccionario debe tener EXACTAMENTE estas claves:\n"
        "- 'name': str, identificador corto en minúsculas sin espacios (ej: 'requests_api')\n"
        "- 'keywords': list[str], 5-10 términos relevantes del código o descripción\n"
        "- 'prompt_fragment': str, resumen conciso (máx. 200 palabras) de mejores prácticas observadas\n"
        "- 'example_code': str, fragmento representativo (máx. 20 líneas) como ejemplo canónico\n"
        "Responde ÚNICAMENTE con el diccionario Python válido. Sin explicaciones, sin markdown, "
        "sin texto adicional antes o después del diccionario."
    )

    user_prompt = (
        f"Descripción de la tarea:\n{task_description}\n\n"
        f"Código exitoso:\n{code}"
    )

    try:
        llm_result = call_llm(
            task_type="skill_extraction",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.3,
            max_tokens=1000,
            project_id=project_id
        )

        if not llm_result.get("success"):
            logger.error(f"LLM call failed: {llm_result.get('error')}")
            return None

        cleaned = _clean_llm_response(llm_result.get("content", ""))
        
        try:
            skill_dict = ast.literal_eval(cleaned)
        except (ValueError, SyntaxError):
            try:
                skill_dict = json.loads(cleaned)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse LLM response: {e}")
                return None

        if not isinstance(skill_dict, dict):
            logger.warning("Parsed result is not a dictionary")
            return None

        required_keys = {"name", "keywords", "prompt_fragment"}
        if not required_keys.issubset(skill_dict.keys()):
            logger.warning(f"Skill dict missing required keys: {required_keys - set(skill_dict.keys())}")
            return None

        logger.info(f"Successfully extracted skill: {skill_dict.get('name')}")
        return skill_dict

    except Exception as e:
        logger.error(f"Error in extract_skill: {e}")
        return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    def mock_call_llm(**kwargs):
        return {
            "success": True,
            "content": '''{
    "name": "test_skill",
    "keywords": ["test", "example", "sample", "demo", "mock"],
    "prompt_fragment": "Este es un fragmento de prueba que demuestra las mejores prácticas para skills de ejemplo.",
    "example_code": "def example():\\n    return 'hello'"
}'''
        }

    import core.router
    original_call_llm = core.router.call_llm
    core.router.call_llm = mock_call_llm

    try:
        result = extract_skill(
            task_description="Crear una función de prueba simple",
            code="def test():\n    return True",
            project_id="test-project-123"
        )

        if result and isinstance(result, dict) and "name" in result:
            print(f"✓ Skill extraído: {result['name']}")
            print(f"✓ Keywords: {result.get('keywords', [])}")
            print("CRITERIO OK")
        else:
            print(f"CRITERIO FALLO: resultado inválido {result}")
    finally:
        core.router.call_llm = original_call_llm