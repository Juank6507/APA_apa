# apa/skills/fastapi.py
SKILL = {
    "name": "fastapi",
    "keywords": ["api", "rest", "fastapi", "endpoint", "http", "web"],
    "prompt_fragment": """
**FastAPI Best Practices:**
- Use type hints for request and response models (Pydantic).
- Define routes with @app.get, @app.post, etc.
- Include a `if __name__ == "__main__": import uvicorn; uvicorn.run(app)` block for local testing.
- Return JSON responses automatically when returning dicts or Pydantic models.
- Use HTTPException for error handling.
""",
    "example_code": """
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

class Item(BaseModel):
    name: str
    price: float

@app.post("/items/")
async def create_item(item: Item):
    return {"item": item}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
"""
}

if __name__ == "__main__":
    # Prueba atómica de validación del skill fastapi
    assert "SKILL" in globals(), "Variable SKILL no encontrada"
    skill = SKILL
    required_keys = ["name", "keywords", "prompt_fragment"]
    for key in required_keys:
        assert key in skill, f"Falta clave obligatoria: {key}"
    assert isinstance(skill["name"], str), "name debe ser string"
    assert isinstance(skill["keywords"], list), "keywords debe ser lista"
    assert isinstance(skill["prompt_fragment"], str), "prompt_fragment debe ser string"
    assert skill["name"] == "fastapi", "El nombre del skill debe ser 'fastapi'"
    print("✅ fastapi skill validado correctamente")