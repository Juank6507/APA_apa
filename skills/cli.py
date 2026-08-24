# apa/skills/cli.py

SKILL = {
    "name": "cli",
    "keywords": ["cli", "command line", "argparse", "argument", "flag", "script", "terminal"],
    "prompt_fragment": """
**Command-Line Interface (argparse) Best Practices:**
- Use `argparse.ArgumentParser` with a clear description.
- Define arguments with `add_argument`, specifying `type`, `help`, and `required` as needed.
- Use `args = parser.parse_args()` to access values.
- Include a `if __name__ == "__main__":` block to run the main function.
- Provide meaningful error messages and exit codes.
""",
    "example_code": """
import argparse

def main():
    parser = argparse.ArgumentParser(description="Process some files.")
    parser.add_argument("--input", type=str, required=True, help="Input file path")
    parser.add_argument("--output", type=str, default="output.txt", help="Output file path")
    parser.add_argument("--verbose", action="store_true", help="Increase output verbosity")
    args = parser.parse_args()
    
    if args.verbose:
        print(f"Processing {args.input} -> {args.output}")
    # Your logic here

if __name__ == "__main__":
    main()
"""
}

if __name__ == "__main__":
    # Validación atómica del skill cli
    assert "SKILL" in globals(), "Variable SKILL no encontrada"
    skill = SKILL
    required_keys = ["name", "keywords", "prompt_fragment"]
    for key in required_keys:
        assert key in skill, f"Falta clave obligatoria: {key}"
    assert isinstance(skill["name"], str), "name debe ser string"
    assert isinstance(skill["keywords"], list), "keywords debe ser lista"
    assert isinstance(skill["prompt_fragment"], str), "prompt_fragment debe ser string"
    assert skill["name"] == "cli", "El nombre del skill debe ser 'cli'"
    print("✅ cli skill validado correctamente")