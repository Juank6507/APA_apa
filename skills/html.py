# apa/skills/html.py
SKILL = {
    "name": "html",
    "language": "html",
    "keywords": [
        "html", "html5", "estructura", "web", "frontend", "template",
        "form", "input", "div", "span", "semantico", "accesibilidad", "doctype"
    ],
    "prompt_fragment": """
**HTML Best Practices:**
- Always start with `<!DOCTYPE html>` declaration for HTML5 compliance.
- Use the basic structure: `<html lang="es">`, `<head>`, `<body>`.
- Employ semantic tags: `<header>`, `<nav>`, `<main>`, `<section>`, `<article>`, `<footer>` for better accessibility and SEO.
- Include `alt` attributes on all `<img>` tags for screen readers and accessibility.
- Close all tags properly; use self-closing syntax for void elements (`<br/>`, `<img/>`).
- Use consistent indentation (2 or 4 spaces) for readability.
- Place `<meta charset="UTF-8">` in the `<head>` for proper character encoding.
- Use lowercase for tag and attribute names for consistency.
- Avoid inline styles; prefer external CSS or `<style>` blocks.
- Validate your HTML with W3C validator to catch errors early.
""",
    "example_code": """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Ejemplo de Página HTML</title>
</head>
<body>
    <header>
        <h1>Bienvenido</h1>
        <nav>
            <ul>
                <li><a href="#inicio">Inicio</a></li>
                <li><a href="#contacto">Contacto</a></li>
            </ul>
        </nav>
    </header>
    <main>
        <section>
            <h2>Contenido Principal</h2>
            <p>Este es un párrafo de ejemplo.</p>
            <form action="/submit" method="post">
                <label for="nombre">Nombre:</label>
                <input type="text" id="nombre" name="nombre" required>
                <button type="submit">Enviar</button>
            </form>
        </section>
    </main>
    <footer>
        <p>&copy; 2024 Mi Sitio Web</p>
    </footer>
</body>
</html>
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

    if skill.get("language") != "html":
        print(f"CRITERIO FALLO: 'language' debe ser 'html', obtenido: {skill.get('language')}")
        sys.exit(1)

    if not isinstance(skill["keywords"], list) or len(skill["keywords"]) == 0:
        print("CRITERIO FALLO: 'keywords' debe ser una lista no vacía")
        sys.exit(1)

    if not isinstance(skill["prompt_fragment"], str) or not skill["prompt_fragment"].strip():
        print("CRITERIO FALLO: 'prompt_fragment' debe ser un string no vacío")
        sys.exit(1)

    print("CRITERIO OK")