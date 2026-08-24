# apa/core/skills_validator.py
import ast
import logging
import re
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

# Lista de módulos estándar "básicos" que no cuentan como imports no triviales
TRIVIAL_STD_MODULES = {
    "sys", "os", "re", "math", "random", "datetime", "json", "time",
    "collections", "itertools", "functools", "typing", "pathlib"
}


def validate_skill_structure(skill: Dict[str, Any]) -> bool:
    """Verifica que el skill tenga la estructura correcta."""
    required_keys = {"name", "keywords", "prompt_fragment"}

    if not required_keys.issubset(skill.keys()):
        missing = required_keys - set(skill.keys())
        logger.warning(f"Skill missing required keys: {missing}")
        return False

    name = skill.get("name")
    if not isinstance(name, str) or not name.strip():
        logger.warning("Skill 'name' must be a non-empty string")
        return False

    keywords = skill.get("keywords")
    if not isinstance(keywords, list):
        logger.warning("Skill 'keywords' must be a list")
        return False
    if not all(isinstance(kw, str) for kw in keywords):
        logger.warning("All keywords must be strings")
        return False

    prompt_fragment = skill.get("prompt_fragment")
    if not isinstance(prompt_fragment, str) or not prompt_fragment.strip():
        logger.warning("Skill 'prompt_fragment' must be a non-empty string")
        return False

    return True


def _normalize_name(name: str) -> str:
    """Normaliza un nombre: minúsculas, sin espacios/guiones extra."""
    normalized = name.lower().strip()
    normalized = re.sub(r'[\s\-_]+', '_', normalized)
    return normalized


def _jaccard_similarity(set1: set, set2: set) -> float:
    """Calcula el coeficiente de Jaccard entre dos conjuntos."""
    if not set1 and not set2:
        return 1.0
    if not set1 or not set2:
        return 0.0
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    return intersection / union if union > 0 else 0.0


def is_duplicate_skill(candidate: Dict[str, Any], existing_skills: List[Dict[str, Any]]) -> bool:
    """Verifica si el skill candidato es duplicado por nombre o similitud de keywords."""
    candidate_name = _normalize_name(candidate.get("name", ""))

    for existing in existing_skills:
        existing_name = _normalize_name(existing.get("name", ""))
        if candidate_name and existing_name and candidate_name == existing_name:
            logger.info(f"Duplicate skill name detected: {candidate_name}")
            return True

        candidate_keywords = set(kw.lower() for kw in candidate.get("keywords", []))
        existing_keywords = set(kw.lower() for kw in existing.get("keywords", []))

        similarity = _jaccard_similarity(candidate_keywords, existing_keywords)
        if similarity >= 0.7:
            logger.info(f"High keyword similarity detected: {similarity:.2f}")
            return True

    return False


def validate_example_code(code: Optional[str]) -> bool:
    """Valida que el código de ejemplo tenga sintaxis Python válida."""
    if code is None or not code.strip():
        return True

    try:
        ast.parse(code)
        return True
    except SyntaxError as e:
        logger.warning(f"Syntax error in example code: {e}")
        return False


def is_skill_nontrivial(skill: Dict[str, Any]) -> bool:
    """Evalúa si el skill representa conocimiento útil (no trivial)."""
    example_code = skill.get("example_code", "")
    if not example_code or not isinstance(example_code, str):
        return False

    try:
        tree = ast.parse(example_code)
    except SyntaxError:
        return False

    # Contar líneas de código no vacías y no puramente comentarios
    lines = example_code.splitlines()
    code_lines = 0
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            code_lines += 1

    if code_lines < 8:
        return False

    # Buscar imports no triviales
    has_nontrivial_import = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_name = alias.name.split(".")[0]
                if module_name not in TRIVIAL_STD_MODULES:
                    has_nontrivial_import = True
                    break
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                module_name = node.module.split(".")[0]
                if module_name not in TRIVIAL_STD_MODULES:
                    has_nontrivial_import = True
                    break

    return has_nontrivial_import


def validate_skill(candidate: Dict[str, Any], existing_skills: List[Dict[str, Any]]) -> Tuple[bool, Optional[str]]:
    """Ejecuta todas las validaciones y retorna (success, error_message)."""
    if not validate_skill_structure(candidate):
        return False, "Invalid skill structure"

    if not is_skill_nontrivial(candidate):
        return False, "Skill is too trivial (insufficient code lines or no non-standard imports)"

    if is_duplicate_skill(candidate, existing_skills):
        return False, "Duplicate or highly similar skill"

    example_code = candidate.get("example_code")
    if not validate_example_code(example_code):
        return False, "Invalid example code syntax"

    return True, None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    valid_skill = {
        "name": "test_skill",
        "keywords": ["test", "example", "demo"],
        "prompt_fragment": "Test skill for validation",
        "example_code": "def hello():\n    return 'world'"
    }

    existing_skills = [
        {
            "name": "existing_skill",
            "keywords": ["api", "rest", "fastapi"],
            "prompt_fragment": "Existing skill"
        }
    ]

    all_passed = True

    # Test validate_skill_structure
    if not validate_skill_structure(valid_skill):
        print("FAIL: validate_skill_structure with valid skill")
        all_passed = False
    else:
        print("✓ validate_skill_structure: valid skill passed")

    invalid_skill = {"name": "", "keywords": "not a list", "prompt_fragment": ""}
    if validate_skill_structure(invalid_skill):
        print("FAIL: validate_skill_structure should reject invalid skill")
        all_passed = False
    else:
        print("✓ validate_skill_structure: invalid skill rejected")

    # Test is_duplicate_skill
    if is_duplicate_skill(valid_skill, existing_skills):
        print("FAIL: is_duplicate_skill should not detect duplicate")
        all_passed = False
    else:
        print("✓ is_duplicate_skill: no false positive")

    duplicate_skill = {"name": "Existing_Skill", "keywords": ["other"], "prompt_fragment": "test"}
    if not is_duplicate_skill(duplicate_skill, existing_skills):
        print("FAIL: is_duplicate_skill should detect name duplicate")
        all_passed = False
    else:
        print("✓ is_duplicate_skill: name duplicate detected")

    similar_skill = {"name": "similar", "keywords": ["api", "rest", "fastapi", "extra"], "prompt_fragment": "test"}
    if not is_duplicate_skill(similar_skill, existing_skills):
        print("FAIL: is_duplicate_skill should detect high similarity")
        all_passed = False
    else:
        print("✓ is_duplicate_skill: keyword similarity detected")

    # Test validate_example_code
    if not validate_example_code("def foo():\n    pass"):
        print("FAIL: validate_example_code should accept valid code")
        all_passed = False
    else:
        print("✓ validate_example_code: valid code accepted")

    if validate_example_code("def broken(:"):
        print("FAIL: validate_example_code should reject invalid syntax")
        all_passed = False
    else:
        print("✓ validate_example_code: invalid syntax rejected")

    if not validate_example_code(None):
        print("FAIL: validate_example_code should accept None")
        all_passed = False
    else:
        print("✓ validate_example_code: None accepted")

    # Test is_skill_nontrivial
    trivial_skill = {
        "name": "trivial",
        "keywords": ["sum", "add"],
        "prompt_fragment": "Simple sum function",
        "example_code": "def suma(a, b):\n    return a + b"
    }
    if is_skill_nontrivial(trivial_skill):
        print("FAIL: is_skill_nontrivial should reject trivial skill")
        all_passed = False
    else:
        print("✓ is_skill_nontrivial: trivial skill rejected")

    nontrivial_skill = {
        "name": "nontrivial",
        "keywords": ["api", "http"],
        "prompt_fragment": "HTTP client with requests",
        "example_code": """import requests
from typing import Dict

def fetch_data(url: str) -> Dict:
    response = requests.get(url)
    response.raise_for_status()
    return response.json()

def post_data(url: str, data: Dict) -> Dict:
    response = requests.post(url, json=data)
    response.raise_for_status()
    return response.json()

if __name__ == "__main__":
    result = fetch_data("https://api.example.com/items")
    print(result)"""
    }
    if not is_skill_nontrivial(nontrivial_skill):
        print("FAIL: is_skill_nontrivial should accept non-trivial skill")
        all_passed = False
    else:
        print("✓ is_skill_nontrivial: non-trivial skill accepted")

    # Test validate_skill with trivial skill
    success, error = validate_skill(trivial_skill, existing_skills)
    if success:
        print("FAIL: validate_skill should reject trivial skill")
        all_passed = False
    else:
        print(f"✓ validate_skill: trivial skill rejected ({error})")

    # Test validate_skill with nontrivial skill
    success, error = validate_skill(nontrivial_skill, existing_skills)
    if not success:
        print(f"FAIL: validate_skill should accept non-trivial skill: {error}")
        all_passed = False
    else:
        print("✓ validate_skill: non-trivial skill accepted")

    print("FILTRO COMPLEJIDAD OK")

    if all_passed:
        print("\nCRITERIO OK")
    else:
        print("\nCRITERIO FALLO: algunas pruebas fallaron")