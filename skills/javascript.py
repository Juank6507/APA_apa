# apa/skills/javascript.py
SKILL = {
    "name": "javascript",
    "language": "javascript",
    "keywords": [
        "javascript", "js", "node", "express", "api", "rest", "async", "await",
        "promise", "callback", "es6", "npm", "commonjs", "module", "require", "export"
    ],
    "prompt_fragment": """**JavaScript/Node.js Best Practices:**
- Use `const` and `let` instead of `var`.
- Always end statements with semicolons.
- In `try/catch`, the `catch` block must include an error parameter: `catch (error) { ... }`.
- Use consistent quotes (single or double).
- Example: `console.log("OK");`""",
    "example_code": """const express = require('express');
const app = express();
const PORT = process.env.PORT || 3000;

app.use(express.json());

app.get('/', (req, res) => {
    res.json({ status: 'OK', message: 'Server running' });
});

app.post('/api/items', async (req, res) => {
    try {
        const { name, value } = req.body;
        if (!name) {
            return res.status(400).json({ error: 'Name is required' });
        }
        res.status(201).json({ id: Date.now(), name, value });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

app.listen(PORT, () => console.log(`Server running on port ${PORT}`));
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

    if skill.get("language") != "javascript":
        print(f"CRITERIO FALLO: 'language' debe ser 'javascript', obtenido: {skill.get('language')}")
        sys.exit(1)

    if not isinstance(skill["keywords"], list) or len(skill["keywords"]) == 0:
        print("CRITERIO FALLO: 'keywords' debe ser una lista no vacía")
        sys.exit(1)

    if not isinstance(skill["prompt_fragment"], str) or not skill["prompt_fragment"].strip():
        print("CRITERIO FALLO: 'prompt_fragment' debe ser un string no vacío")
        sys.exit(1)

    print("CRITERIO OK")