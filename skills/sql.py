# apa/skills/sql.py
SKILL = {
    "name": "sql",
    "language": "sql",
    "keywords": [
        "sql", "query", "select", "insert", "update", "delete", "table",
        "database", "postgres", "mysql", "sqlite", "migration", "index", "join"
    ],
    "prompt_fragment": """**SQL Best Practices:**
- Terminate every statement with a semicolon `;`.
- Use single quotes for string literals.
- For SQLite compatibility, use `AUTOINCREMENT` instead of `AUTO_INCREMENT`.
- Example: `SELECT 'OK';`""",
    "example_code": """-- Crear tabla de usuarios con buenas prácticas
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insertar datos con parámetros (ejemplo conceptual)
INSERT INTO usuarios (nombre, email) VALUES ('Juan', 'juan@example.com');

-- Consulta con JOIN explícito y filtro
SELECT u.nombre, p.titulo
FROM usuarios u
INNER JOIN pedidos p ON u.id = p.usuario_id
WHERE u.nombre LIKE 'J%';

-- Índice para optimizar búsquedas por email
CREATE INDEX IF NOT EXISTS idx_usuarios_email ON usuarios(email);
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

    if skill.get("language") != "sql":
        print(f"CRITERIO FALLO: 'language' debe ser 'sql', obtenido: {skill.get('language')}")
        sys.exit(1)

    if not isinstance(skill["keywords"], list) or len(skill["keywords"]) == 0:
        print("CRITERIO FALLO: 'keywords' debe ser una lista no vacía")
        sys.exit(1)

    if not isinstance(skill["prompt_fragment"], str) or not skill["prompt_fragment"].strip():
        print("CRITERIO FALLO: 'prompt_fragment' debe ser un string no vacío")
        sys.exit(1)

    print("CRITERIO OK")