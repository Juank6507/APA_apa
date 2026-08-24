# apa/core/language_profiles.py
from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class LanguageProfile:
    name: str
    extensions: List[str]
    keywords: List[str]
    interpreter: str
    prompt_template: Optional[str] = None
    validator: Optional[str] = None


def get_python_profile() -> LanguageProfile:
    return LanguageProfile(
        name="python",
        extensions=[".py", ".pyw"],
        keywords=["python", "fastapi", "django", "flask", "pytest", "dataclass", "asyncio", "pydantic", "tkinter", "gui", "desktop"],
        interpreter="python3",
        prompt_template="""You are generating Python code. STRICT SYNTAX RULES:

1. INDENTATION: Use 4 spaces per level. NEVER mix tabs and spaces.
2. COLONS: Every block statement ends with colon (:): if, else, elif, for, while, def, class, try, except.
3. STRINGS: Use double quotes for strings. Use triple quotes for docstrings.
4. IMPORTS: Group imports at the top. Order: standard library, third-party, local.
5. FUNCTIONS: Always include type hints for parameters and return values.
6. CLASSES: Use PascalCase for class names. Include __init__ with type hints.
7. ERROR HANDLING: Use specific exceptions, not bare except.
8. ASYNC: Use async/await for asynchronous operations.
9. MAIN GUARD: Use if __name__ == "__main__": for executable scripts.
10. F-STRINGS: Prefer f-strings for string formatting.

OUTPUT FORMAT:
- PEP 8 compliant
- Proper indentation (4 spaces)
- Blank lines between functions/classes (2 lines)
- End file with newline

TKINTER GUI RULES (apply when generating GUI code):
- Use `import tkinter as tk` and `from tkinter import ttk, messagebox`. NEVER `from tkinter import *`.
- Create a main application class inheriting from `tk.Tk`. Call `self.mainloop()` only inside `if __name__ == "__main__":`.
- Use `tk.StringVar()`, `tk.IntVar()`, `tk.DoubleVar()`, `tk.BooleanVar()` to bind data to widgets.
- Every callback MUST have try/except. Uncaught exceptions in callbacks crash silently.
- NEVER call `time.sleep()` or blocking operations inside a callback. Use `threading.Thread(daemon=True)` + `widget.after()`.
- Choose ONE layout manager per container: `grid` for forms, `pack` for simple stacking.
- Center the window: calculate x = (screen_width - window_width) // 2 after `update_idletasks()`.
- Handle window close: `self.protocol("WM_DELETE_WINDOW", self.on_closing)`.
- Validate inputs on `<FocusOut>` or on submit, NOT on every keystroke.
- Use `re.match()` for pattern validation (email, phone, postal code).

EXAMPLE OF VALID CODE:
import os
from typing import List, Optional


class DataProcessor:
    def __init__(self, config: dict) -> None:
        self.config = config
    
    def process(self, items: List[str]) -> dict:
        result = {"processed": 0, "errors": []}
        for item in items:
            try:
                self._validate(item)
                result["processed"] += 1
            except ValueError as e:
                result["errors"].append(str(e))
        return result
    
    def _validate(self, item: str) -> None:
        if not item:
            raise ValueError("Empty item")


if __name__ == "__main__":
    processor = DataProcessor({"strict": True})
    data = ["item1", "item2", ""]
    print(processor.process(data))
""",
        validator="ast"
    )


def get_javascript_profile() -> LanguageProfile:
    return LanguageProfile(
        name="javascript",
        extensions=[".js", ".mjs", ".cjs"],
        keywords=["javascript", "js", "node", "express", "react", "vue", "angular", "npm", "yarn", "es6", "commonjs", "module"],
        interpreter="node",
        prompt_template="""You are generating JavaScript code for Node.js. STRICT SYNTAX RULES:

1. PARENTHESES: Every ( must have a matching ). Count them before outputting.
2. BRACES: Every { must have a matching }. Indent properly. Count them.
3. SEMICOLONS: Every statement MUST end with a semicolon (;). No exceptions.
4. STRINGS: Use single quotes consistently. Never leave unclosed quotes.
5. TRY/CATCH: Always include the error parameter:
   try { ... } catch (error) { ... }  // CORRECT
   try { ... } catch { ... }          // WRONG
6. ARROW FUNCTIONS: For multi-line, use explicit return:
   const func = (x) => { return x + 1; };  // CORRECT
   const func = (x) => { x + 1; };         // WRONG
7. TEMPLATE LITERALS: Use backticks for interpolation: `Value: ${x}`
8. ASYNC/AWAIT: async function requires await inside for promises.

OUTPUT FORMAT:
- One statement per line when possible
- Proper indentation (2 or 4 spaces, consistent)
- No trailing whitespace
- End file with newline

EXAMPLE OF VALID CODE:
const fs = require('fs');

async function readFile(path) {
    try {
        const data = await fs.promises.readFile(path, 'utf8');
        return data;
    } catch (error) {
        console.error('Error:', error.message);
        return null;
    }
}

module.exports = { readFile };""",
        validator="none"
    )


def get_bash_profile() -> LanguageProfile:
    return LanguageProfile(
        name="bash",
        extensions=[".sh", ".bash"],
        keywords=["bash", "shell", "linux", "unix", "command", "terminal", "cron"],
        interpreter="bash",
        prompt_template="""You are generating Bash script. STRICT SYNTAX RULES:

1. SHEBANG: Always start with #!/bin/bash as the first line.
2. EXIT ON ERROR: Use set -e at the beginning to exit on any error.
3. QUOTING: ALWAYS quote variables with double quotes: "$var" (never $var alone).
4. CONDITIONALS: Use [[ ]] instead of [ ] for tests:
   if [[ "$var" == "value" ]]; then  // CORRECT
   if [ "$var" == "value" ]; then    // AVOID
5. VARIABLE ASSIGNMENT: No spaces around = :
   name="value"   // CORRECT
   name = "value" // WRONG
6. FUNCTIONS: Define functions with function keyword or () :
   function my_func() { ... }  // CORRECT
   my_func() { ... }           // CORRECT
7. ECHO: Use echo for output. For complex output, use printf.
8. EXIT CODES: End script with exit 0 for success, exit 1 for error.
9. COMMENTS: Use # for comments. Document complex logic.
10. ARITHMETIC: Use $(( )) for arithmetic: result=$((a + b))

OUTPUT FORMAT:
- Shebang on first line
- set -e after shebang
- Variables in UPPERCASE for constants
- Functions before main logic
- exit 0 at the end

EXAMPLE OF VALID SCRIPT:
#!/bin/bash
set -e

# Configuration
INPUT_DIR="/path/to/input"
OUTPUT_DIR="/path/to/output"

# Functions
process_file() {
    local file="$1"
    if [[ -f "$file" ]]; then
        echo "Processing: $file"
        cp "$file" "$OUTPUT_DIR/"
    fi
}

# Main logic
for file in "$INPUT_DIR"/*; do
    process_file "$file"
done

echo "Done!"
exit 0
""",
        validator="none"
    )


def get_sql_profile() -> LanguageProfile:
    return LanguageProfile(
        name="sql",
        extensions=[".sql"],
        keywords=["sql", "query", "postgres", "mysql", "sqlite", "migration", "migracion", "database", "datos", "bd", "consulta", "tabla", "table", "select", "insert", "update", "delete"],
        interpreter="sqlite3",
        prompt_template="""You are generating SQL code. STRICT SYNTAX RULES:

1. STATEMENTS: Every statement MUST end with a semicolon (;).
2. KEYWORDS: Use UPPERCASE for SQL keywords: SELECT, FROM, WHERE, INSERT, UPDATE, DELETE.
3. STRINGS: Use single quotes for string literals: 'value'.
4. IDENTIFIERS: Use double quotes for identifiers if needed: "column name".
5. NULL: Use IS NULL or IS NOT NULL, never = NULL.
6. JOINS: Always specify JOIN type: INNER JOIN, LEFT JOIN, RIGHT JOIN.
7. ALIASES: Use AS for aliases: SELECT col AS alias FROM table.
8. SUBQUERIES: Enclose subqueries in parentheses.
9. TRANSACTIONS: Use BEGIN, COMMIT, ROLLBACK for data modifications.
10. COMMENTS: Use -- for single-line comments, /* */ for multi-line.

OUTPUT FORMAT:
- One clause per line for complex queries
- Indent subqueries
- Consistent capitalization
- End each statement with semicolon

EXAMPLE OF VALID SQL:
-- Create users table
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Insert a new user
INSERT INTO users (name, email)
VALUES ('John Doe', 'john@example.com');

-- Query users
SELECT 
    u.id,
    u.name,
    u.email
FROM users AS u
WHERE u.created_at IS NOT NULL
ORDER BY u.name ASC;

COMMIT;
""",
        validator="none"
    )


def get_cpp_profile() -> LanguageProfile:
    return LanguageProfile(
        name="cpp",
        extensions=[".cpp", ".cc", ".cxx", ".h", ".hpp"],
        keywords=["c++", "cpp", "g++", "clang", "compilar", "clase", "template", "std", "vector", "puntero", "herencia", "polimorfismo", "makefile", "cmake"],
        interpreter="g++",
        prompt_template="""You are generating C++ code. STRICT SYNTAX RULES:

1. HEADERS: Include necessary headers at the top: #include <iostream>, #include <string>, etc.
2. MAIN FUNCTION: Every executable needs int main() { ... return 0; }.
3. NAMESPACES: Prefer explicit std:: over using namespace std.
4. BRACES: Every { must have a matching }. Consistent style (K&R or Allman).
5. SEMICOLONS: Every statement MUST end with a semicolon (;).
6. POINTERS: Initialize pointers to nullptr. Check for nullptr before dereferencing.
7. MEMORY: Use smart pointers (std::unique_ptr, std::shared_ptr) over raw pointers.
8. STRINGS: Use std::string instead of char arrays.
9. VECTORS: Use std::vector instead of raw arrays.
10. RETURN: Return 0 from main() for success, non-zero for error.

OUTPUT FORMAT:
- Headers first
- Using declarations (if any)
- Classes/structs
- Functions
- main() function last
- Proper indentation (4 spaces)
- End file with newline

EXAMPLE OF VALID C++:
#include <iostream>
#include <string>
#include <vector>

class Calculator {
public:
    int add(int a, int b) {
        return a + b;
    }
    
    int multiply(int a, int b) {
        return a * b;
    }
};

int main() {
    Calculator calc;
    
    std::vector<int> numbers = {1, 2, 3, 4, 5};
    int sum = 0;
    
    for (int num : numbers) {
        sum = calc.add(sum, num);
    }
    
    std::cout << "Sum: " << sum << std::endl;
    std::cout << "Product: " << calc.multiply(3, 4) << std::endl;
    
    return 0;
}
""",
        validator="none"
    )


def get_react_native_profile() -> LanguageProfile:
    return LanguageProfile(
        name="react-native",
        extensions=[".js", ".jsx", ".ts", ".tsx"],
        keywords=["react-native", "expo", "mobile", "ios", "android", "component", "navigation", "hook", "usestate", "useeffect", "flatlist", "stylesheet"],
        interpreter="node",
        prompt_template="""You are generating React Native code. STRICT SYNTAX RULES:

1. IMPORTS: Import React and React Native components at the top.
2. COMPONENTS: Use functional components with hooks (not class components).
3. HOOKS: Call hooks at the top level, never inside loops or conditions.
4. STYLING: Use StyleSheet.create() for styles, not inline styles.
5. PROPS: Destructure props in function parameters: ({ title, onPress }).
6. STATE: Use useState for local state: const [state, setState] = useState(initial).
7. EFFECTS: Use useEffect for side effects with proper dependencies array.
8. LISTS: Use FlatList for lists, not .map() in render.
9. HANDLERS: Define handlers inside component or use useCallback.
10. EXPORT: Export default component at the bottom.

OUTPUT FORMAT:
- Imports first
- Component function
- Styles (StyleSheet.create)
- Export at the bottom
- Proper indentation (2 or 4 spaces)
- End file with newline

EXAMPLE OF VALID COMPONENT:
import React, { useState, useEffect } from 'react';
import { View, Text, Button, FlatList, StyleSheet } from 'react-native';

const ItemList = ({ navigation }) => {
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        loadItems();
    }, []);

    const loadItems = async () => {
        try {
            const data = await fetchItems();
            setItems(data);
        } catch (error) {
            console.error('Error loading items:', error);
        } finally {
            setLoading(false);
        }
    };

    const renderItem = ({ item }) => (
        <View style={styles.item}>
            <Text style={styles.title}>{item.title}</Text>
        </View>
    );

    if (loading) {
        return (
            <View style={styles.center}>
                <Text>Loading...</Text>
            </View>
        );
    }

    return (
        <View style={styles.container}>
            <FlatList
                data={items}
                renderItem={renderItem}
                keyExtractor={(item) => item.id.toString()}
            />
            <Button title="Add Item" onPress={() => navigation.navigate('AddItem')} />
        </View>
    );
};

const styles = StyleSheet.create({
    container: {
        flex: 1,
        padding: 16,
    },
    center: {
        flex: 1,
        justifyContent: 'center',
        alignItems: 'center',
    },
    item: {
        padding: 16,
        borderBottomWidth: 1,
        borderBottomColor: '#ccc',
    },
    title: {
        fontSize: 16,
        fontWeight: 'bold',
    },
});

export default ItemList;
""",
        validator="none"
    )


def get_dart_profile() -> LanguageProfile:
    return LanguageProfile(
        name="dart",
        extensions=[".dart"],
        keywords=["flutter", "dart", "widget", "setstate", "material", "cupertino", "bloc", "provider", "riverpod", "async", "await", "future", "stream"],
        interpreter="/opt/flutter/bin/dart",
        prompt_template="""You are generating Dart code for Flutter. STRICT SYNTAX RULES:

1. IMPORTS: Import packages first, then relative imports.
2. WIDGETS: Extend StatelessWidget or StatefulWidget.
3. BUILD METHOD: Every widget must have a build() method returning a Widget.
4. STATE: Use setState() in State classes to trigger rebuilds.
5. CONST: Use const constructors where possible for performance.
6. ASYNC: Use async/await for asynchronous operations.
7. FUTURES: Return Future<void> for async methods that do not return a value.
8. NULL SAFETY: Handle null with ? or ! operators. Use late for late initialization.
9. PARAMETERS: Use required for required named parameters.
10. THEMING: Use Theme.of(context) for consistent styling.

OUTPUT FORMAT:
- Imports first
- Main/widget class
- State class (if StatefulWidget)
- Helper methods
- End file with newline

EXAMPLE OF VALID FLUTTER WIDGET:
import 'package:flutter/material.dart';

class CounterWidget extends StatefulWidget {
    const CounterWidget({Key? key, required this.title}) : super(key: key);

    final String title;

    @override
    State<CounterWidget> createState() => _CounterWidgetState();
}

class _CounterWidgetState extends State<CounterWidget> {
    int _counter = 0;

    void _incrementCounter() {
        setState(() {
            _counter++;
        });
    }

    void _resetCounter() {
        setState(() {
            _counter = 0;
        });
    }

    @override
    Widget build(BuildContext context) {
        return Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
                Text(
                    widget.title,
                    style: Theme.of(context).textTheme.headlineMedium,
                ),
                const SizedBox(height: 16),
                Text(
                    'Count: $_counter',
                    style: Theme.of(context).textTheme.headlineSmall,
                ),
                const SizedBox(height: 16),
                Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                        ElevatedButton(
                            onPressed: _incrementCounter,
                            child: const Text('Increment'),
                        ),
                        const SizedBox(width: 16),
                        ElevatedButton(
                            onPressed: _resetCounter,
                            child: const Text('Reset'),
                        ),
                    ],
                ),
            ],
        );
    }
}
""",
        validator="none"
    )


def get_typescript_profile() -> LanguageProfile:
    return LanguageProfile(
        name="typescript",
        extensions=[".ts", ".tsx"],
        keywords=[
            "typescript", "ts", "tsc", "ts-node",
            "interface", "type ", "enum ", "generic",
            "prisma", "nestjs", "deno", "angular",
            "type annotation", "type guard",
            ": string", ": number", ": boolean",
        ],
        interpreter="npx ts-node",
        prompt_template="""You are generating TypeScript code. STRICT SYNTAX RULES:

1. TYPE ANNOTATIONS: Every function parameter MUST have a type. Every function MUST have a return type.
2. INTERFACES: Use interfaces to define object shapes. Prefer interfaces over type aliases for objects.
3. NO ANY: NEVER use 'any' type. Use 'unknown' if the type is truly unknown.
4. NULL SAFETY: Handle nullable types with ? or !. Use optional chaining (?.) and nullish coalescing (??).
5. SEMICOLONS: Every statement MUST end with a semicolon (;).
6. STRINGS: Use single quotes for strings. Use template literals (backticks) for interpolation.
7. BRACES: Every { must have a matching }. Indent with 2 or 4 spaces consistently.
8. PARENTHESES: Every ( must have a matching ). Count them before outputting.
9. ASYNC/AWAIT: async function requires await inside for promises. Type promises as Promise<T>.
10. EXPORTS: Use export for modules. Use export default for main exports.

OUTPUT FORMAT:
- One statement per line when possible
- Proper indentation (2 or 4 spaces, consistent)
- No trailing whitespace
- End file with newline

EXAMPLE OF VALID TYPESCRIPT:
interface User {
    id: number;
    name: string;
    email: string;
    createdAt?: Date;
}

function createUser(name: string, email: string): User {
    return {
        id: Math.floor(Math.random() * 1000),
        name,
        email,
        createdAt: new Date(),
    };
}

function formatUser(user: User): string {
    const dateStr = user.createdAt?.toISOString() ?? "unknown";
    return `${user.name} (${user.email}) - created: ${dateStr}`;
}

// Validation
const user: User = createUser("Alice", "alice@example.com");
console.log(formatUser(user));
console.log("CRITERIO OK");
""",
        validator="typescript"
    )


def get_all_profiles() -> List[LanguageProfile]:
    return [
        get_python_profile(),
        get_javascript_profile(),
        get_bash_profile(),
        get_sql_profile(),
        get_cpp_profile(),
        get_react_native_profile(),
        get_dart_profile(),
        get_typescript_profile()
    ]


LANGUAGE_PROFILES: List[LanguageProfile] = get_all_profiles()


if __name__ == "__main__":
    import sys

    # Verificar cantidad de perfiles
    assert len(LANGUAGE_PROFILES) == 8, f"Se esperaban 8 perfiles, se obtuvieron {len(LANGUAGE_PROFILES)}"

    # Comprobar campos obligatorios no vacíos
    for profile in LANGUAGE_PROFILES:
        assert profile.name, f"El campo 'name' está vacío en el perfil {profile}"
        assert len(profile.extensions) > 0, f"El campo 'extensions' está vacío en {profile.name}"
        assert len(profile.keywords) > 0, f"El campo 'keywords' está vacío en {profile.name}"
        assert profile.interpreter, f"El campo 'interpreter' está vacío en {profile.name}"
        assert len(profile.prompt_template) > 500, f"El prompt_template es muy corto en {profile.name}"

    print("Perfiles disponibles:", [p.name for p in LANGUAGE_PROFILES])
    print("\nLongitudes de prompts:")
    for profile in LANGUAGE_PROFILES:
        print(f"  {profile.name}: {len(profile.prompt_template)} caracteres")
    print("\nCRITERIO OK")