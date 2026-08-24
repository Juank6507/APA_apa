# apa/skills/typescript.py
# Skill base para TypeScript — generado para F5/TS1
# Proporciona contexto de dominio para el generador cuando detecta tareas TypeScript
#
# UBICACIÓN EN REPO: C:\Python\Proyectos\APA\apa\skills\typescript.py

SKILL = {
    "name": "typescript",
    "language": "typescript",
    "keywords": [
        "typescript", "ts", "tsc", "ts-node",
        "interface", "type ", "enum ", "generic",
        "prisma", "nestjs", "deno", "angular",
        "type annotation", "type guard",
        ": string", ": number", ": boolean",
        "express con typescript", "api rest typescript",
        "clase typescript", "typescript class",
        "servidor typescript", "typescript server",
        "modulo typescript", "typescript module",
        "decorador", "decorator typescript",
        "dto", "entity typescript",
        "zod", "io-ts", "class-validator",
    ],
    "prompt_fragment": """## 📘 TYPESCRIPT - Directrices de Generación

### Reglas Obligatorias de Tipado:
1. **TODOS** los parámetros de función deben tener anotación de tipo explícita
2. **TODAS** las funciones deben tener tipo de retorno explícito (incluido `: void`)
3. Usa `interface` para definir formas de objetos, NO `type` (salvo uniones/intersecciones)
4. **PROHIBIDO** usar `any` — usa `unknown` si el tipo es desconocido
5. Usa `readonly` para propiedades inmutables en interfaces
6. Usa genéricos (`<T>`) cuando el tipo pueda parametrizarse

### Reglas de Sintaxis:
7. Toda statement termina con `;` (sin excepciones)
8. Usa comillas simples para strings, backticks para template literals
9. Usa `===` y `!==` (nunca `==` ni `!=`)
10. Usa optional chaining (`?.`) y nullish coalescing (`??`)
11. Usa `const` por defecto, `let` solo si la variable se reasigna, NUNCA `var`

### Reglas de Estructura:
12. Exporta interfaces, tipos y funciones con `export`
13. Usa `export default` solo para el componente/clase principal
14. Organiza el archivo: imports → interfaces/types → funciones/clases → export
15. Usa JSDoc (`/** */`) para documentar funciones y interfaces públicas
16. Si el script es ejecutable, incluye `console.log("CRITERIO OK")` al final

### Errores Comunes a Evitar:
- No mezcles `export default` con `export named` sin motivo
- No uses `Object.any` como tipo — define una interface
- No ignores el error de `strictNullChecks` — maneja los nulls
- No uses `as` para castear sin verificar antes con type guard
- No definas una interface y un type con el mismo nombre
""",
    "example_code": """// === EJEMPLO: Sistema de gestión de usuarios en TypeScript ===

// Interfaces
interface User {
    readonly id: number;
    name: string;
    email: string;
    role: UserRole;
    createdAt: Date;
    updatedAt?: Date;
}

type UserRole = "admin" | "editor" | "viewer";

interface CreateUserDTO {
    name: string;
    email: string;
    role: UserRole;
}

// Type guard
function isAdmin(user: User): boolean {
    return user.role === "admin";
}

// Función con tipado completo
function createUser(dto: CreateUserDTO): User {
    const id: number = Math.floor(Math.random() * 100000);
    const now: Date = new Date();

    return {
        id,
        name: dto.name,
        email: dto.email,
        role: dto.role,
        createdAt: now,
    };
}

// Función genérica
function findById<T extends { id: number }>(
    items: ReadonlyArray<T>,
    id: number
): T | undefined {
    return items.find((item: T): boolean => item.id === id);
}

// Validación con resultado tipado
function validateEmail(email: string): { valid: boolean; error?: string } {
    if (!email.includes("@")) {
        return { valid: false, error: "Email must contain @" };
    }
    if (!email.includes(".")) {
        return { valid: false, error: "Email must contain a domain" };
    }
    return { valid: true };
}

// Uso
const users: User[] = [
    createUser({ name: "Alice", email: "alice@example.com", role: "admin" }),
    createUser({ name: "Bob", email: "bob@example.com", role: "editor" }),
];

const found: User | undefined = findById(users, users[0].id);
if (found !== undefined) {
    console.log(`Found: ${found.name} (${found.role})`);
}

// Test
const validation = validateEmail("test@example.com");
if (validation.valid) {
    console.log("CRITERIO OK");
} else {
    console.log(`CRITERIO FALLO: ${validation.error}`);
}
""",
}


# === VALIDACIÓN AUTOMÁTICA ===
if __name__ == "__main__":
    # Verificar estructura del skill
    assert "name" in SKILL, "Falta campo 'name'"
    assert "language" in SKILL, "Falta campo 'language'"
    assert "keywords" in SKILL, "Falta campo 'keywords'"
    assert "prompt_fragment" in SKILL, "Falta campo 'prompt_fragment'"
    assert "example_code" in SKILL, "Falta campo 'example_code'"

    # Verificar contenido
    assert SKILL["name"] == "typescript", f"Name incorrecto: {SKILL['name']}"
    assert SKILL["language"] == "typescript", f"Language incorrecto: {SKILL['language']}"
    assert len(SKILL["keywords"]) >= 20, f"Keywords insuficientes: {len(SKILL['keywords'])}"
    assert len(SKILL["prompt_fragment"]) >= 500, f"Prompt fragment muy corto: {len(SKILL['prompt_fragment'])} chars"
    assert len(SKILL["example_code"]) >= 300, f"Example code muy corto: {len(SKILL['example_code'])} chars"

    # Verificar que el example_code contiene CRITERIO OK
    assert "CRITERIO OK" in SKILL["example_code"], "Example code no contiene 'CRITERIO OK'"

    # Verificar keywords clave
    critical_keywords = ["typescript", "interface", "type ", "nestjs", "prisma", "zod"]
    for kw in critical_keywords:
        assert any(kw in k for k in SKILL["keywords"]), f"Falta keyword clave: {kw}"

    # Verificar que prompt_fragment menciona reglas clave
    assert "any" in SKILL["prompt_fragment"], "Prompt no menciona prohibición de 'any'"
    assert "interface" in SKILL["prompt_fragment"], "Prompt no menciona interfaces"
    assert "generic" in SKILL["prompt_fragment"].lower() or "genérico" in SKILL["prompt_fragment"].lower(), "Prompt no menciona genéricos"

    print(f"Skill name: {SKILL['name']}")
    print(f"Language: {SKILL['language']}")
    print(f"Keywords: {len(SKILL['keywords'])}")
    print(f"Prompt fragment: {len(SKILL['prompt_fragment'])} caracteres")
    print(f"Example code: {len(SKILL['example_code'])} caracteres")
    print("CRITERIO OK")
