# apa/skills/dataclasses.py

SKILL = {
    "name": "dataclasses",
    "keywords": ["dataclass", "dataclasses", "field", "frozen", "post_init", "model", "struct"],
    "prompt_fragment": """
**Dataclasses Best Practices:**
- Use `@dataclass` decorator to automatically generate `__init__`, `__repr__`, etc.
- Specify types for all fields; use `field()` for defaults or metadata.
- Use `frozen=True` to make instances immutable (hashable).
- Use `__post_init__` for custom validation.
- For nested data structures, combine with `List`, `Dict` from `typing`.
""",
    "example_code": """
from dataclasses import dataclass, field
from typing import List

@dataclass
class Person:
    name: str
    age: int
    email: str = field(default="unknown@example.com")
    
    def __post_init__(self):
        if self.age < 0:
            raise ValueError("Age cannot be negative")

@dataclass(frozen=True)
class Point:
    x: float
    y: float
"""
}

if __name__ == "__main__":
    # Validación atómica del skill dataclasses
    assert "SKILL" in globals(), "Variable SKILL no encontrada"
    skill = SKILL
    required_keys = ["name", "keywords", "prompt_fragment"]
    for key in required_keys:
        assert key in skill, f"Falta clave obligatoria: {key}"
    assert isinstance(skill["name"], str), "name debe ser string"
    assert isinstance(skill["keywords"], list), "keywords debe ser lista"
    assert isinstance(skill["prompt_fragment"], str), "prompt_fragment debe ser string"
    assert skill["name"] == "dataclasses", "El nombre del skill debe ser 'dataclasses'"
    print("✅ dataclasses skill validado correctamente")