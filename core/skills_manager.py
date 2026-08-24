# apa/core/skills_manager.py
import sys
import os
import re
import logging
import importlib.util
from pathlib import Path
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

# Contenido del skill por defecto para crear si el directorio está vacío
DEFAULT_SKILL_CONTENT = '''# apa/skills/fastapi.py
SKILL = {
    "name": "fastapi",
    "language": "python",
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
'''

class SkillsManager:
    """
    Gestor de skills reutilizables. Carga dinámicamente fragments de conocimiento
    desde el directorio apa/skills y permite buscarlos por descripción.
    """

    def __init__(self, skills_dir: Optional[Path] = None):
        # Determinar ruta del directorio de skills
        if skills_dir is None:
            # SkillsManager está en apa/core, así que subimos dos niveles a apa/
            skills_dir = Path(__file__).parent.parent / "skills"

        self.skills_dir = skills_dir
        self.skills_dir.mkdir(parents=True, exist_ok=True)

        self.loaded_skills: Dict[str, Dict[str, Any]] = {}
        self._load_all_skills()

    def _load_all_skills(self) -> None:
        """Carga todos los skills disponibles desde el directorio."""
        self.loaded_skills.clear()

        # Verificar si el directorio está vacío (sin archivos .py)
        py_files = list(self.skills_dir.glob("*.py"))
        if not py_files:
            logger.info(f"Skills directory empty at {self.skills_dir}. Creating default fastapi skill.")
            self._create_default_skill()
            # Re-escanear tras crear el archivo por defecto
            py_files = list(self.skills_dir.glob("*.py"))

        # Cargar todos los skills disponibles
        for path in py_files:
            if path.name == "__init__.py":
                continue
            try:
                self._load_skill(path)
            except Exception as e:
                logger.warning(f"Error loading skill from {path}: {e}")

    def _create_default_skill(self):
        """Crea el archivo fastapi.py con el contenido por defecto."""
        target_path = self.skills_dir / "fastapi.py"
        try:
            target_path.write_text(DEFAULT_SKILL_CONTENT, encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to create default skill: {e}")

    def _load_skill(self, path: Path):
        """Carga un módulo de skill desde una ruta de archivo."""
        module_name = path.stem
        spec = importlib.util.spec_from_file_location(module_name, str(path))
        if spec is None or spec.loader is None:
            return

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Buscar la variable SKILL en el módulo
        skill_data = getattr(module, "SKILL", None)
        if skill_data and isinstance(skill_data, dict):
            # Validar campo language obligatorio
            language = skill_data.get("language")
            if not language or not isinstance(language, str) or not language.strip():
                logger.warning(f"Skill in {path} missing or invalid 'language' field, skipping")
                return
            # Usamos el nombre definido en el skill o el nombre del archivo como fallback
            name = skill_data.get("name", module_name)
            self.loaded_skills[name] = skill_data
            logger.debug(f"Loaded skill: {name}")
        else:
            logger.warning(f"Module {module_name} does not export a valid SKILL dict.")

    def reload(self) -> None:
        """Recarga todos los skills desde el directorio."""
        self._load_all_skills()
        logger.info(f"Skills reloaded. Total skills: {len(self.loaded_skills)}")

    def find_skill(self, task_description: str, language: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Busca el skill más relevante basado en la descripción de la tarea.
        Tokeniza la descripción y cuenta coincidencias de palabras clave.
        Si language se proporciona, filtra solo skills de ese lenguaje.
        """
        # Tokenizar descripción: convertir a minúsculas y extraer palabras alfanuméricas
        text = task_description.lower()
        tokens = set(re.findall(r'\b\w+\b', text))

        # Filtrar por lenguaje si se especifica
        skills_to_search = self.loaded_skills
        if language is not None:
            lang_lower = language.lower()
            skills_to_search = {
                name: skill for name, skill in self.loaded_skills.items()
                if skill.get("language", "").lower() == lang_lower
            }

        best_skill: Optional[Dict[str, Any]] = None
        max_matches = 0

        for name, skill_data in skills_to_search.items():
            keywords = [kw.lower() for kw in skill_data.get("keywords", [])]
            matches = 0

            for kw in keywords:
                # Verificar si la keyword está presente como token exacto
                if kw in tokens:
                    matches += 1

            # Actualizar mejor coincidencia si supera el máximo actual
            if matches > max_matches:
                max_matches = matches
                best_skill = skill_data

        # Retornar solo si hay al menos 2 coincidencias
        if max_matches >= 2 and best_skill:
            return best_skill
        return None

    def get_skill_prompt(self, skill_name: str) -> Optional[str]:
        """Retorna el fragmento de prompt para un skill por nombre."""
        if skill_name in self.loaded_skills:
            return self.loaded_skills[skill_name].get("prompt_fragment")
        return None

    def list_skills(self) -> List[str]:
        """Retorna la lista de nombres de skills cargados."""
        return list(self.loaded_skills.keys())


if __name__ == "__main__":
    # Configuración básica de logging para pruebas
    logging.basicConfig(level=logging.INFO)

    print("🧪 Ejecutando pruebas de SkillsManager...")

    # Limpiar directorio de prueba para simular entorno limpio
    import shutil
    import time
    test_dir = Path(__file__).parent.parent / "skills_test"
    if test_dir.exists():
        shutil.rmtree(test_dir)

    try:
        # Inicializar con directorio de prueba
        manager = SkillsManager(skills_dir=test_dir)

        # 1. Listar skills (debe contener al menos 'fastapi' creado por defecto)
        skills = manager.list_skills()
        assert "fastapi" in skills, f"fastapi skill no encontrado. Skills: {skills}"
        print(f"✓ Skills disponibles: {skills}")

        # 2. Buscar skill relevante
        task_desc = "Crear una API REST con FastAPI que maneje items"
        skill = manager.find_skill(task_desc)
        assert skill is not None, "No se encontró skill para API REST"
        assert skill["name"] == "fastapi", f"Se esperaba fastapi, se obtuvo {skill['name']}"
        print(f"✓ Skill encontrado para '{task_desc}': {skill['name']}")

        # 3. Buscar descripción sin coincidencias suficientes
        no_match = manager.find_skill("Script de línea de comandos")
        assert no_match is None, "No debería encontrar skill para CLI (solo fastapi existe)"
        print("✓ Sin coincidencias para 'Script de línea de comandos'")

        # 4. Obtener prompt fragment
        prompt = manager.get_skill_prompt("fastapi")
        assert prompt is not None, "Prompt no encontrado"
        assert "FastAPI Best Practices" in prompt, "Contenido del prompt incorrecto"
        print("✓ Prompt fragment obtenido correctamente")

        # 5. Prueba de filtro por lenguaje
        # Fastapi es python, así que buscar con language="python" debe funcionar
        skill_py = manager.find_skill(task_desc, language="python")
        assert skill_py is not None and skill_py["name"] == "fastapi", "Filtro por language=python falló"
        print("✓ Filtro por language='python' funciona")

        # Buscar con language="javascript" no debe encontrar fastapi
        skill_js = manager.find_skill(task_desc, language="javascript")
        assert skill_js is None, "No debería encontrar skill de javascript para tarea de FastAPI"
        print("✓ Filtro por language='javascript' excluye skills de otros lenguajes")

        # 6. Prueba de skill sin campo language (debe ser ignorado)
        invalid_skill_content = '''# apa/skills/invalid_skill.py
SKILL = {
    "name": "invalid_skill",
    "keywords": ["test", "invalid"],
    "prompt_fragment": "Skill sin campo language"
}
'''
        invalid_skill_path = test_dir / "invalid_skill.py"
        invalid_skill_path.write_text(invalid_skill_content, encoding="utf-8")
        time.sleep(0.1)
        manager.reload()
        assert "invalid_skill" not in manager.list_skills(), "Skill sin language no debería cargarse"
        print("✓ Skill sin campo 'language' es ignorado correctamente")

        # 7. Prueba de reload con nuevo skill
        new_skill_content = '''# apa/skills/test_reload.py
SKILL = {
    "name": "test_reload",
    "language": "python",
    "keywords": ["test", "reload", "temporal"],
    "prompt_fragment": "Skill de prueba para verificar reload",
    "example_code": "print('hello')"
}
'''
        new_skill_path = test_dir / "test_reload.py"
        new_skill_path.write_text(new_skill_content, encoding="utf-8")
        time.sleep(0.1)  # Pequeña pausa para asegurar escritura

        # Verificar que el skill no está cargado aún
        assert "test_reload" not in manager.list_skills(), "Skill no debería estar cargado antes de reload"

        # Recargar y verificar
        manager.reload()
        assert "test_reload" in manager.list_skills(), "Skill no encontrado después de reload"
        print("✓ Reload funcionó correctamente")
        print("RELOAD OK")

        print("\n✅ Todos los tests de SkillsManager pasaron.")

    except Exception as e:
        print(f"❌ Error en pruebas: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Limpieza
        if test_dir.exists():
            shutil.rmtree(test_dir)