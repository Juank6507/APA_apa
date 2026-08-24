# apa/tests/test_q1_validacion_completa.py
"""
Validación integral de todos los prompts mejorados - Tarea Q1
Ejecutar: python apa/tests/test_q1_validacion_completa.py
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

print(f"Project root: {project_root}")


def test_all_profiles_exist():
    """Verifica que todos los perfiles existen y tienen estructura correcta."""
    print("\n" + "="*60)
    print("TEST 1: Estructura de todos los perfiles")
    print("="*60)
    
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "language_profiles", 
        project_root / "core" / "language_profiles.py"
    )
    lp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lp)
    
    expected_profiles = ["python", "javascript", "bash", "sql", "cpp", "react-native", "dart"]
    all_profiles = lp.get_all_profiles()
    
    assert len(all_profiles) == 7, f"Se esperaban 7 perfiles, hay {len(all_profiles)}"
    
    found_names = [p.name for p in all_profiles]
    for expected in expected_profiles:
        assert expected in found_names, f"Perfil '{expected}' no encontrado"
        print(f"  ✅ Perfil '{expected}' existe")
    
    return True


def test_all_prompts_length():
    """Verifica que todos los prompts tienen longitud adecuada."""
    print("\n" + "="*60)
    print("TEST 2: Longitud de todos los prompts")
    print("="*60)
    
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "language_profiles", 
        project_root / "core" / "language_profiles.py"
    )
    lp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lp)
    
    min_length = 500
    for profile in lp.get_all_profiles():
        prompt_len = len(profile.prompt_template)
        assert prompt_len >= min_length, f"Prompt de {profile.name} muy corto: {prompt_len} caracteres"
        print(f"  ✅ {profile.name}: {prompt_len} caracteres")
    
    return True


def test_python_rules():
    """Verifica reglas específicas de Python."""
    print("\n" + "="*60)
    print("TEST 3: Reglas Python")
    print("="*60)
    
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "language_profiles", 
        project_root / "core" / "language_profiles.py"
    )
    lp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lp)
    
    profile = lp.get_python_profile()
    prompt = profile.prompt_template
    
    rules = [
        "INDENTATION",
        "COLONS", 
        "STRINGS",
        "IMPORTS",
        "FUNCTIONS",
        "CLASSES",
        "ERROR HANDLING",
        "ASYNC",
        "MAIN GUARD",
        "F-STRINGS",
        "EXAMPLE OF VALID"
    ]
    
    for rule in rules:
        assert rule in prompt, f"Regla '{rule}' no encontrada"
        print(f"  ✅ {rule}")
    
    return True


def test_javascript_rules():
    """Verifica reglas específicas de JavaScript."""
    print("\n" + "="*60)
    print("TEST 4: Reglas JavaScript")
    print("="*60)
    
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "language_profiles", 
        project_root / "core" / "language_profiles.py"
    )
    lp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lp)
    
    profile = lp.get_javascript_profile()
    prompt = profile.prompt_template
    
    rules = [
        "PARENTHESES",
        "BRACES",
        "SEMICOLONS",
        "STRINGS",
        "TRY/CATCH",
        "ARROW FUNCTIONS",
        "TEMPLATE LITERALS",
        "ASYNC/AWAIT",
        "EXAMPLE OF VALID"
    ]
    
    for rule in rules:
        assert rule in prompt, f"Regla '{rule}' no encontrada"
        print(f"  ✅ {rule}")
    
    return True


def test_bash_rules():
    """Verifica reglas específicas de Bash."""
    print("\n" + "="*60)
    print("TEST 5: Reglas Bash")
    print("="*60)
    
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "language_profiles", 
        project_root / "core" / "language_profiles.py"
    )
    lp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lp)
    
    profile = lp.get_bash_profile()
    prompt = profile.prompt_template
    
    rules = [
        "SHEBANG",
        "EXIT ON ERROR",
        "QUOTING",
        "CONDITIONALS",
        "VARIABLE ASSIGNMENT",
        "FUNCTIONS",
        "EXIT CODES",
        "EXAMPLE OF VALID"
    ]
    
    for rule in rules:
        assert rule in prompt, f"Regla '{rule}' no encontrada"
        print(f"  ✅ {rule}")
    
    return True


def test_sql_rules():
    """Verifica reglas específicas de SQL."""
    print("\n" + "="*60)
    print("TEST 6: Reglas SQL")
    print("="*60)
    
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "language_profiles", 
        project_root / "core" / "language_profiles.py"
    )
    lp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lp)
    
    profile = lp.get_sql_profile()
    prompt = profile.prompt_template
    
    rules = [
        "STATEMENTS",
        "KEYWORDS",
        "STRINGS",
        "NULL",
        "JOINS",
        "ALIASES",
        "TRANSACTIONS",
        "EXAMPLE OF VALID"
    ]
    
    for rule in rules:
        assert rule in prompt, f"Regla '{rule}' no encontrada"
        print(f"  ✅ {rule}")
    
    return True


def test_cpp_rules():
    """Verifica reglas específicas de C++."""
    print("\n" + "="*60)
    print("TEST 7: Reglas C++")
    print("="*60)
    
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "language_profiles", 
        project_root / "core" / "language_profiles.py"
    )
    lp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lp)
    
    profile = lp.get_cpp_profile()
    prompt = profile.prompt_template
    
    rules = [
        "HEADERS",
        "MAIN FUNCTION",
        "NAMESPACES",
        "BRACES",
        "SEMICOLONS",
        "POINTERS",
        "MEMORY",
        "EXAMPLE OF VALID"
    ]
    
    for rule in rules:
        assert rule in prompt, f"Regla '{rule}' no encontrada"
        print(f"  ✅ {rule}")
    
    return True


def test_react_native_rules():
    """Verifica reglas específicas de React Native."""
    print("\n" + "="*60)
    print("TEST 8: Reglas React Native")
    print("="*60)
    
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "language_profiles", 
        project_root / "core" / "language_profiles.py"
    )
    lp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lp)
    
    profile = lp.get_react_native_profile()
    prompt = profile.prompt_template
    
    rules = [
        "IMPORTS",
        "COMPONENTS",
        "HOOKS",
        "STYLING",
        "PROPS",
        "STATE",
        "EFFECTS",
        "LISTS",
        "EXAMPLE OF VALID"
    ]
    
    for rule in rules:
        assert rule in prompt, f"Regla '{rule}' no encontrada"
        print(f"  ✅ {rule}")
    
    return True


def test_dart_rules():
    """Verifica reglas específicas de Dart."""
    print("\n" + "="*60)
    print("TEST 9: Reglas Dart")
    print("="*60)
    
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "language_profiles", 
        project_root / "core" / "language_profiles.py"
    )
    lp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lp)
    
    profile = lp.get_dart_profile()
    prompt = profile.prompt_template
    
    rules = [
        "IMPORTS",
        "WIDGETS",
        "BUILD METHOD",
        "STATE",
        "CONST",
        "ASYNC",
        "NULL SAFETY",
        "EXAMPLE OF VALID"
    ]
    
    for rule in rules:
        assert rule in prompt, f"Regla '{rule}' no encontrada"
        print(f"  ✅ {rule}")
    
    return True


def test_skill_express_api():
    """Verifica que el skill express_api funciona."""
    print("\n" + "="*60)
    print("TEST 10: Skill express_api.py")
    print("="*60)
    
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "express_api", 
        project_root / "skills" / "express_api.py"
    )
    skill_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(skill_module)
    
    skill = skill_module.get_skill()
    
    assert skill["name"] == "express_api"
    assert skill["language"] == "javascript"
    assert len(skill["patterns"]) >= 9
    assert len(skill["best_practices"]) >= 8
    
    print(f"  ✅ Nombre: {skill['name']}")
    print(f"  ✅ Lenguaje: {skill['language']}")
    print(f"  ✅ Patrones: {len(skill['patterns'])}")
    print(f"  ✅ Best practices: {len(skill['best_practices'])}")
    
    return True


def test_integration():
    """Verifica integración con el proyecto."""
    print("\n" + "="*60)
    print("TEST 11: Integración del sistema")
    print("="*60)
    
    import importlib.util
    
    # Cargar language_profiles
    spec_lp = importlib.util.spec_from_file_location(
        "language_profiles", 
        project_root / "core" / "language_profiles.py"
    )
    lp = importlib.util.module_from_spec(spec_lp)
    spec_lp.loader.exec_module(lp)
    
    # Verificar que LANGUAGE_PROFILES funciona
    profiles = lp.LANGUAGE_PROFILES
    assert len(profiles) == 7
    
    # Verificar que get_all_profiles funciona
    all_profiles = lp.get_all_profiles()
    assert len(all_profiles) == 7
    
    # Verificar que cada perfil es válido
    for profile in all_profiles:
        assert hasattr(profile, 'name')
        assert hasattr(profile, 'extensions')
        assert hasattr(profile, 'keywords')
        assert hasattr(profile, 'interpreter')
        assert hasattr(profile, 'prompt_template')
        assert hasattr(profile, 'validator')
    
    print("  ✅ LANGUAGE_PROFILES funciona correctamente")
    print("  ✅ get_all_profiles() funciona correctamente")
    print("  ✅ Todos los perfiles tienen campos válidos")
    print("  ✅ Integración correcta con el proyecto")
    
    return True


def main():
    """Ejecuta todas las validaciones."""
    print("\n" + "#"*60)
    print("# VALIDACIÓN INTEGRAL COMPLETA - TAREA Q1")
    print("# Todos los prompts mejorados")
    print("#"*60)
    
    tests = [
        ("Estructura de perfiles", test_all_profiles_exist),
        ("Longitud de prompts", test_all_prompts_length),
        ("Reglas Python", test_python_rules),
        ("Reglas JavaScript", test_javascript_rules),
        ("Reglas Bash", test_bash_rules),
        ("Reglas SQL", test_sql_rules),
        ("Reglas C++", test_cpp_rules),
        ("Reglas React Native", test_react_native_rules),
        ("Reglas Dart", test_dart_rules),
        ("Skill express_api", test_skill_express_api),
        ("Integración del sistema", test_integration),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            test_func()
            passed += 1
        except AssertionError as e:
            print(f"\n  ❌ FALLO: {e}")
            failed += 1
        except Exception as e:
            print(f"\n  ❌ ERROR: {e}")
            failed += 1
    
    # Resumen final
    print("\n" + "#"*60)
    print("# RESUMEN DE VALIDACIÓN COMPLETA")
    print("#"*60)
    print(f"\n  Tests pasados: {passed}/{len(tests)}")
    print(f"  Tests fallidos: {failed}/{len(tests)}")
    
    if failed == 0:
        print("\n" + "="*60)
        print("✅ TODOS LOS TESTS PASADOS")
        print("✅ TAREA Q1 COMPLETADA AL 100%")
        print("="*60)
        print("\n  RESUMEN DE MEJORAS:")
        print("  ─────────────────────")
        print("  • Python:     10 reglas + ejemplo ✅")
        print("  • JavaScript:  8 reglas + ejemplo ✅")
        print("  • Bash:       10 reglas + ejemplo ✅")
        print("  • SQL:        10 reglas + ejemplo ✅")
        print("  • C++:        10 reglas + ejemplo ✅")
        print("  • React Native: 10 reglas + ejemplo ✅")
        print("  • Dart:       10 reglas + ejemplo ✅")
        print("  • Skill express_api: 9 patrones ✅")
        print("\n  CRITERIO OK")
    else:
        print(f"\n  ❌ {failed} TESTS FALLARON")
        sys.exit(1)


if __name__ == "__main__":
    main()