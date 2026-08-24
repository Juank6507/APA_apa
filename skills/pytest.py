# apa/skills/pytest.py

SKILL = {
    "name": "pytest",
    "keywords": ["test", "pytest", "unit test", "assert", "fixture", "mock", "parametrize"],
    "prompt_fragment": """
**Pytest Best Practices:**
- Use `assert` statements directly; no need for `self.assertEqual`.
- Organize tests in files named `test_*.py` and functions named `test_*`.
- Use fixtures (`@pytest.fixture`) to set up common test data.
- Use `@pytest.mark.parametrize` for testing multiple inputs.
- To mock dependencies, use `pytest-mock` or `unittest.mock`.
""",
    "example_code": """
import pytest

def add(a, b):
    return a + b

@pytest.mark.parametrize("a,b,expected", [
    (1, 2, 3),
    (0, 0, 0),
    (-1, 1, 0),
])
def test_add(a, b, expected):
    assert add(a, b) == expected

def test_add_fixture(mocker):
    mocker.patch("module.external_api", return_value=42)
    # test logic
"""
}

if __name__ == "__main__":
    # Validación atómica del skill pytest
    assert "SKILL" in globals(), "Variable SKILL no encontrada"
    skill = SKILL
    required_keys = ["name", "keywords", "prompt_fragment"]
    for key in required_keys:
        assert key in skill, f"Falta clave obligatoria: {key}"
    assert isinstance(skill["name"], str), "name debe ser string"
    assert isinstance(skill["keywords"], list), "keywords debe ser lista"
    assert isinstance(skill["prompt_fragment"], str), "prompt_fragment debe ser string"
    assert skill["name"] == "pytest", "El nombre del skill debe ser 'pytest'"
    print("✅ pytest skill validado correctamente")