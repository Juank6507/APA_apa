# apa/skills/express_api.py
"""
Skill: Express.js API REST
Lenguaje: JavaScript
Keywords: api, rest, express, route, endpoint, controller, middleware
"""

SKILL_NAME = "express_api"
SKILL_LANGUAGE = "javascript"
SKILL_KEYWORDS = ["api", "rest", "express", "route", "endpoint", "controller", "middleware", "get", "post", "put", "delete"]

SKILL_TEMPLATE = """
// Express.js API REST Pattern
// ============================

const express = require('express');
const app = express();

// Middleware
app.use(express.json());

// Routes
app.get('/api/items', async (req, res) => {
    try {
        const items = await getItems();
        res.json({ success: true, data: items });
    } catch (error) {
        res.status(500).json({ success: false, error: error.message });
    }
});

app.post('/api/items', async (req, res) => {
    try {
        const newItem = await createItem(req.body);
        res.status(201).json({ success: true, data: newItem });
    } catch (error) {
        res.status(400).json({ success: false, error: error.message });
    }
});

app.put('/api/items/:id', async (req, res) => {
    try {
        const updated = await updateItem(req.params.id, req.body);
        if (!updated) {
            return res.status(404).json({ success: false, error: 'Item not found' });
        }
        res.json({ success: true, data: updated });
    } catch (error) {
        res.status(500).json({ success: false, error: error.message });
    }
});

app.delete('/api/items/:id', async (req, res) => {
    try {
        const deleted = await deleteItem(req.params.id);
        if (!deleted) {
            return res.status(404).json({ success: false, error: 'Item not found' });
        }
        res.json({ success: true, message: 'Item deleted' });
    } catch (error) {
        res.status(500).json({ success: false, error: error.message });
    }
});

// Error handler middleware
app.use((err, req, res, next) => {
    console.error(err.stack);
    res.status(500).json({ success: false, error: 'Internal server error' });
});

// Start server
const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
    console.log(`Server running on port ${PORT}`);
});

module.exports = app;
"""

SKILL_PATTERNS = {
    "route_get": """app.get('/api/{resource}', async (req, res) => {
    try {
        const data = await get{Resource}();
        res.json({ success: true, data: data });
    } catch (error) {
        res.status(500).json({ success: false, error: error.message });
    }
});""",

    "route_post": """app.post('/api/{resource}', async (req, res) => {
    try {
        const newItem = await create{Resource}(req.body);
        res.status(201).json({ success: true, data: newItem });
    } catch (error) {
        res.status(400).json({ success: false, error: error.message });
    }
});""",

    "route_put": """app.put('/api/{resource}/:id', async (req, res) => {
    try {
        const updated = await update{Resource}(req.params.id, req.body);
        if (!updated) {
            return res.status(404).json({ success: false, error: '{Resource} not found' });
        }
        res.json({ success: true, data: updated });
    } catch (error) {
        res.status(500).json({ success: false, error: error.message });
    }
});""",

    "route_delete": """app.delete('/api/{resource}/:id', async (req, res) => {
    try {
        const deleted = await delete{Resource}(req.params.id);
        if (!deleted) {
            return res.status(404).json({ success: false, error: '{Resource} not found' });
        }
        res.json({ success: true, message: '{Resource} deleted' });
    } catch (error) {
        res.status(500).json({ success: false, error: error.message });
    }
});""",

    "middleware_error": """app.use((err, req, res, next) => {
    console.error(err.stack);
    res.status(500).json({ success: false, error: 'Internal server error' });
});""",

    "middleware_json": """app.use(express.json());""",

    "response_success": """res.json({ success: true, data: data });""",

    "response_error": """res.status(code).json({ success: false, error: error.message });""",

    "server_start": """const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
    console.log(`Server running on port ${PORT}`);
});"""
}

SKILL_BEST_PRACTICES = [
    "Always use try/catch in async route handlers",
    "Return consistent JSON responses: { success: true/false, data/error: ... }",
    "Use proper HTTP status codes: 200, 201, 400, 404, 500",
    "Validate request body before processing",
    "Use middleware for common functionality (auth, logging, error handling)",
    "Use meaningful route names: /api/resource",
    "Handle 404 cases explicitly",
    "Use async/await instead of callbacks"
]


def get_skill():
    """Retorna la información del skill para el SkillsManager."""
    return {
        "name": SKILL_NAME,
        "language": SKILL_LANGUAGE,
        "keywords": SKILL_KEYWORDS,
        "template": SKILL_TEMPLATE,
        "patterns": SKILL_PATTERNS,
        "best_practices": SKILL_BEST_PRACTICES
    }


if __name__ == "__main__":
    # Validación automática del skill
    skill = get_skill()
    
    # Verificar campos obligatorios
    assert skill["name"], "El campo 'name' está vacío"
    assert skill["language"], "El campo 'language' está vacío"
    assert len(skill["keywords"]) > 0, "El campo 'keywords' está vacío"
    assert skill["template"], "El campo 'template' está vacío"
    assert len(skill["patterns"]) > 0, "El campo 'patterns' está vacío"
    assert len(skill["best_practices"]) > 0, "El campo 'best_practices' está vacío"
    
    print(f"Skill: {skill['name']}")
    print(f"Lenguaje: {skill['language']}")
    print(f"Keywords: {skill['keywords']}")
    print(f"Patrones: {len(skill['patterns'])}")
    print(f"Best practices: {len(skill['best_practices'])}")
    print("CRITERIO OK")