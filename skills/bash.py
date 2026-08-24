# apa/skills/bash.py
SKILL = {
    "name": "bash",
    "language": "bash",
    "keywords": [
        "bash", "shell", "script", "linux", "unix", "command",
        "terminal", "cron", "sh", "#!/bin/bash"
    ],
    "prompt_fragment": """**Bash Script Best Practices:**
- Start with shebang: `#!/bin/bash`.
- Use `set -euo pipefail` to exit on errors and undefined variables.
- Always quote variables: `"$var"`.
- Use `[[ ]]` for conditional tests.
- End script with `exit 0`.
- Example:
  ```bash
  #!/bin/bash
  set -euo pipefail
  echo "Hello, world!"
  exit 0
  ```""",
    "example_code": """#!/bin/bash
set -euo pipefail

echo "Iniciando script..."

# Verificar si un archivo existe
if [[ -f "archivo.txt" ]]; then
    echo "El archivo existe"
    content="$(cat archivo.txt)"
    printf "Contenido: %s\\n" "$content"
else
    echo "Archivo no encontrado" >&2
    exit 1
fi

# Función con variable local
procesar_datos() {
    local input="$1"
    echo "Procesando: $input"
}

procesar_datos "ejemplo"

echo "Script completado exitosamente"
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

    if skill.get("language") != "bash":
        print(f"CRITERIO FALLO: 'language' debe ser 'bash', obtenido: {skill.get('language')}")
        sys.exit(1)

    if not isinstance(skill["keywords"], list) or len(skill["keywords"]) == 0:
        print("CRITERIO FALLO: 'keywords' debe ser una lista no vacía")
        sys.exit(1)

    if not isinstance(skill["prompt_fragment"], str) or not skill["prompt_fragment"].strip():
        print("CRITERIO FALLO: 'prompt_fragment' debe ser un string no vacío")
        sys.exit(1)

    print("CRITERIO OK")