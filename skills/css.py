# apa/skills/css.py
SKILL = {
    "name": "css",
    "language": "css",
    "keywords": [
        "css", "css3", "estilos", "diseño", "responsive", "flexbox",
        "grid", "animacion", "selector", "media query", "fuente",
        "color", "margen", "padding"
    ],
    "prompt_fragment": """
**CSS Best Practices:**
- Use descriptive class names; consider BEM methodology (`block__element--modifier`) for scalability.
- Organize CSS by components or sections to improve maintainability.
- Prefer `rem` or `em` units for font sizes to support user accessibility settings.
- Use `flexbox` or `grid` for modern, responsive layouts instead of floats or positioning hacks.
- Include media queries (`@media`) for responsive design across different screen sizes.
- Avoid excessive use of `!important`; rely on specificity and proper cascade order instead.
- Use CSS variables (`--custom-property`) for consistent theming and easier updates.
- Minimize selector nesting depth to keep styles predictable and performant.
- Comment complex sections with `/* comment */` for better code documentation.
- Validate CSS with tools like Stylelint to catch errors and enforce conventions.
""",
    "example_code": """/* Reset básico y configuración global */
* {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
}

body {
    font-family: system-ui, -apple-system, sans-serif;
    line-height: 1.6;
    color: #333;
    background-color: #fff;
}

/* Contenedor principal con Flexbox */
.contenedor {
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 100vh;
    padding: 1rem;
}

/* Tarjeta de ejemplo con sombras y bordes redondeados */
.tarjeta {
    max-width: 400px;
    padding: 2rem;
    border-radius: 8px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
    background: #f9f9f9;
}

/* Responsive: ajustar en pantallas pequeñas */
@media (max-width: 600px) {
    .contenedor {
        flex-direction: column;
        text-align: center;
    }
    .tarjeta {
        width: 100%;
    }
}

/* Animación suave para hover */
.tarjeta:hover {
    transform: translateY(-2px);
    transition: transform 0.2s ease-in-out;
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

    if skill.get("language") != "css":
        print(f"CRITERIO FALLO: 'language' debe ser 'css', obtenido: {skill.get('language')}")
        sys.exit(1)

    if not isinstance(skill["keywords"], list) or len(skill["keywords"]) == 0:
        print("CRITERIO FALLO: 'keywords' debe ser una lista no vacía")
        sys.exit(1)

    if not isinstance(skill["prompt_fragment"], str) or not skill["prompt_fragment"].strip():
        print("CRITERIO FALLO: 'prompt_fragment' debe ser un string no vacío")
        sys.exit(1)

    print("CRITERIO OK")
