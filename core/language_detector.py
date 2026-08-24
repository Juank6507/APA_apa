# apa/core/language_detector.py
import re
import logging
from pathlib import Path
from typing import List, Optional
import sys
import os

# Asegurar que el directorio padre (apa/) esté en el path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.language_profiles import LanguageProfile, LANGUAGE_PROFILES

logger = logging.getLogger(__name__)


class LanguageDetector:
    """Detector de lenguaje basado en perfiles y heurística."""

    def __init__(self, profiles: Optional[List[LanguageProfile]] = None):
        if profiles is None:
            self.profiles = LANGUAGE_PROFILES
        else:
            self.profiles = profiles

        # Buscar perfil python como default
        self.default_profile = self.get_profile_by_name("python")
        if self.default_profile is None and self.profiles:
            self.default_profile = self.profiles[0]

    def detect(self, task_description: str, file_path: Optional[str] = None) -> LanguageProfile:
        # Primero intentar por extensión de archivo
        if file_path is not None:
            ext = Path(file_path).suffix.lower()
            for profile in self.profiles:
                if ext in profile.extensions:
                    logger.debug(f"Detected language by extension '{ext}': {profile.name}")
                    return profile

        # Tokenizar descripción: minúsculas y palabras alfanuméricas
        text = task_description.lower()
        tokens = set(re.findall(r'\b\w+\b', text))

        best_profile: Optional[LanguageProfile] = None
        max_matches = 0

        for profile in self.profiles:
            keywords = [kw.lower() for kw in profile.keywords]
            matches = sum(1 for kw in keywords if kw in tokens)

            if matches > max_matches:
                max_matches = matches
                best_profile = profile

        # Lógica de desempate: si hay empate, priorizar por nombre en la descripción
        if max_matches > 0 and best_profile is not None:
            # Encontrar todos los perfiles con el mismo número de coincidencias
            tied_profiles = []
            for profile in self.profiles:
                keywords = [kw.lower() for kw in profile.keywords]
                matches = sum(1 for kw in keywords if kw in tokens)
                if matches == max_matches:
                    tied_profiles.append(profile)
            
            # Si hay empate, verificar si algún nombre de perfil aparece como token
            if len(tied_profiles) > 1:
                name_matches = [p for p in tied_profiles if p.name.lower() in tokens]
                if len(name_matches) == 1:
                    logger.debug(f"Tie-break by name: {name_matches[0].name} found in description")
                    return name_matches[0]
            
            logger.debug(f"Detected language by keywords: {best_profile.name} ({max_matches} matches)")
            return best_profile

        logger.debug(f"No keyword match found, using default: {self.default_profile.name}")
        return self.default_profile

    def get_profile_by_name(self, name: str) -> Optional[LanguageProfile]:
        """Busca un perfil por nombre (insensible a mayúsculas)."""
        name_lower = name.lower()
        for profile in self.profiles:
            if profile.name.lower() == name_lower:
                return profile
        return None

    def list_profiles(self) -> List[str]:
        """Retorna lista de nombres de perfiles disponibles."""
        return [profile.name for profile in self.profiles]


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    detector = LanguageDetector()

    # Pruebas de detección
    tests = [
        ("Crear una API REST con FastAPI", None, "python"),
        ("Endpoint en Express.js para manejar items", None, "javascript"),
        ("Script de migración de base de datos", None, "sql"),
        ("Script de automatización en Bash", None, "bash"),
        ("Tarea ambigua", "app.js", "javascript"),
    ]

    all_passed = True
    for desc, path, expected in tests:
        result = detector.detect(desc, path)
        if result.name == expected:
            print(f"✓ '{desc}' -> {result.name}")
        else:
            print(f"✗ '{desc}' -> {result.name} (esperado: {expected})")
            all_passed = False

    # Prueba adicional: list_profiles
    profiles = detector.list_profiles()
    if "python" in profiles and "javascript" in profiles:
        print(f"✓ list_profiles: {profiles}")
    else:
        print(f"✗ list_profiles failed: {profiles}")
        all_passed = False

    # Prueba adicional: get_profile_by_name
    py_profile = detector.get_profile_by_name("Python")
    if py_profile is not None and py_profile.name == "python":
        print("✓ get_profile_by_name: case-insensitive lookup works")
    else:
        print("✗ get_profile_by_name failed")
        all_passed = False

    if all_passed:
        print("\nCRITERIO OK")
    else:
        print("\nCRITERIO FALLO")