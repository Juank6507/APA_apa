# apa/skills/cpp.py
SKILL = {
    "name": "cpp",
    "language": "cpp",
    "keywords": [
        "c++", "cpp", "g++", "clang", "compilar", "clase", "template", "std",
        "vector", "puntero", "referencia", "herencia", "polimorfismo", "raii",
        "smart pointer", "stl", "makefile", "cmake"
    ],
    "prompt_fragment": """**C++ Best Practices:**
- Include necessary headers: `#include <iostream>`.
- Use `int main() { ... return 0; }`.
- Compile with `g++ -std=c++17`.
- Example:
  ```cpp
  #include <iostream>
  int main() {
      std::cout << "OK" << std::endl;
      return 0;
  }
  ```""",
    "example_code": """#include <iostream>
#include <vector>

int main() {
    // Use std::vector instead of raw arrays
    std::vector<int> numeros = {1, 2, 3, 4, 5};

    // Range-based for loop for clean iteration
    for (const int& n : numeros) {
        std::cout << n << ' ';
    }
    std::cout << std::endl;

    // Smart pointer for automatic memory management
    auto ptr = std::make_unique<std::string>("Hello, C++!");
    std::cout << *ptr << std::endl;

    return 0;
}
"""
}


if __name__ == "__main__":
    import sys

    required_keys = {"name", "language", "keywords", "prompt_fragment"}

    if "SKILL" not in globals():
        print("CRITERIO FALLO: Variable SKILL no definida")
        sys.exit(1)

    skill = SKILL

    missing = required_keys - set(skill.keys())
    if missing:
        print(f"CRITERIO FALLO: Claves faltantes: {missing}")
        sys.exit(1)

    if not isinstance(skill["name"], str) or not skill["name"].strip():
        print("CRITERIO FALLO: 'name' debe ser un string no vacío")
        sys.exit(1)

    if skill.get("language") != "cpp":
        print(f"CRITERIO FALLO: 'language' debe ser 'cpp', obtenido: {skill.get('language')}")
        sys.exit(1)

    if not isinstance(skill["keywords"], list) or len(skill["keywords"]) == 0:
        print("CRITERIO FALLO: 'keywords' debe ser una lista no vacía")
        sys.exit(1)

    if not isinstance(skill["prompt_fragment"], str) or not skill["prompt_fragment"].strip():
        print("CRITERIO FALLO: 'prompt_fragment' debe ser un string no vacío")
        sys.exit(1)

    print("CRITERIO OK")