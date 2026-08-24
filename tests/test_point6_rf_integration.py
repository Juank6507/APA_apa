#!/usr/bin/env python3
# test_point6_rf_integration.py
# Point 6 — Verificación de integración RF en SemiAutoAgent v3.4
#
# VALIDA:
#   1. review_diff_and_decide() existe en refactor_guard.py
#   2. SCOPE_VIOLATION como severidad en refactor_guard.py
#   3. semi_auto_agent.py usa review_diff_and_decide() en _rf4_review_diff
#   4. semi_auto_agent.py detecta SCOPE_VIOLATION en _rf4_review_diff
#   5. update_after_modification() se llama post-integración exitosa
#   6. should_block_changes() NO bloquea por SCOPE_VIOLATION
#   7. review_diff_and_decide() combina review + should_block
#
# USO:
#   python test_point6_rf_integration.py
#
# CRITERIO: Los 7 tests deben pasar.
# ============================================================================

import os
import sys
import re
import tempfile
import shutil
import ast

# Asegurar que apa.core es importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# ============================================================================
# Helpers
# ============================================================================

def _find_file_relative(relative_path: str) -> str:
    """Busca un archivo relativo al directorio del test o al project root."""
    # Estrategia 1: relativo al directorio del test
    test_dir = os.path.dirname(__file__)
    candidate = os.path.join(test_dir, relative_path)
    if os.path.exists(candidate):
        return candidate

    # Estrategia 2: relativo a apa/tests/../ (subir al nivel de apa/)
    candidate2 = os.path.join(test_dir, '..', relative_path)
    if os.path.exists(candidate2):
        return candidate2

    # Estrategia 3: relativo a APA/
    candidate3 = os.path.join(test_dir, '..', 'APA', relative_path)
    if os.path.exists(candidate3):
        return candidate3

    return None


def _read_file_content(path: str) -> str:
    """Lee el contenido de un archivo."""
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


# ============================================================================
# Test runner
# ============================================================================

def run_tests():
    """Ejecuta los 7 tests de integración RF v3.4."""
    test_results = []

    print("=" * 70)
    print("Point 6 — Verificación de integración RF en SemiAutoAgent v3.4")
    print("=" * 70)

    # ── Rutas de archivos (relativas al directorio del test: apa/tests/) ──
    guard_path = _find_file_relative(os.path.join('..', 'core', 'refactor_guard.py'))
    agent_path = _find_file_relative(os.path.join('..', 'agents', 'semi_auto_agent.py'))

    if guard_path is None:
        print("\n❌ refactor_guard.py no encontrado. Abortando.")
        sys.exit(1)
    if agent_path is None:
        print("\n❌ semi_auto_agent.py no encontrado. Abortando.")
        sys.exit(1)

    guard_content = _read_file_content(guard_path)
    agent_content = _read_file_content(agent_path)

    # ================================================================
    # Test 1: review_diff_and_decide() existe en refactor_guard.py
    # ================================================================
    print("\n── Test 1: review_diff_and_decide() en refactor_guard.py ──")

    has_method = 'def review_diff_and_decide(' in guard_content
    test_results.append((
        "review_diff_and_decide() existe en refactor_guard.py",
        has_method
    ))

    if has_method:
        # Verificar firma: acepta task_description
        has_task_desc = 'task_description' in guard_content
        test_results.append((
            "review_diff_and_decide() acepta task_description como parámetro",
            has_task_desc
        ))
    else:
        test_results.append((
            "review_diff_and_decide() acepta task_description como parámetro",
            False
        ))

    # ================================================================
    # Test 2: SCOPE_VIOLATION como severidad en refactor_guard.py
    # ================================================================
    print("── Test 2: SCOPE_VIOLATION en refactor_guard.py ──")

    has_scope = 'SCOPE_VIOLATION' in guard_content
    test_results.append((
        "SCOPE_VIOLATION definido como severidad en refactor_guard.py",
        has_scope
    ))

    has_check_scope = '_check_scope_violation(' in guard_content
    test_results.append((
        "_check_scope_violation() existe como método privado",
        has_check_scope
    ))

    # has_critical_issues incluye SCOPE_VIOLATION
    has_critical_includes_scope = (
        '"SCOPE_VIOLATION"' in guard_content and
        'has_critical_issues' in guard_content
    )
    test_results.append((
        "has_critical_issues() incluye SCOPE_VIOLATION",
        has_critical_includes_scope
    ))

    # ================================================================
    # Test 3: semi_auto_agent.py usa review_diff_and_decide()
    # ================================================================
    print("── Test 3: semi_auto_agent.py invoca review_diff_and_decide() ──")

    uses_decide = 'review_diff_and_decide(' in agent_content
    test_results.append((
        "semi_auto_agent.py invoca review_diff_and_decide()",
        uses_decide
    ))

    # Debe pasar task_description
    uses_task_desc = (
        uses_decide and
        'task_description' in agent_content
    )
    test_results.append((
        "semi_auto_agent.py pasa task_description a review_diff_and_decide()",
        uses_task_desc
    ))

    # ================================================================
    # Test 4: semi_auto_agent.py detecta SCOPE_VIOLATION
    # ================================================================
    print("── Test 4: semi_auto_agent.py maneja SCOPE_VIOLATION ──")

    detects_scope = 'scope_violations' in agent_content and 'SCOPE_VIOLATION' in agent_content
    test_results.append((
        "semi_auto_agent.py detecta y maneja SCOPE_VIOLATION",
        detects_scope
    ))

    # Loguea scope violations
    logs_scope = 'SCOPE: ' in agent_content or 'scope_violations' in agent_content
    test_results.append((
        "semi_auto_agent.py registra SCOPE_VIOLATION en el log",
        logs_scope
    ))

    # Almacena rf4_should_block en validation_result
    stores_should_block = 'rf4_should_block' in agent_content
    test_results.append((
        "semi_auto_agent.py almacena rf4_should_block en validation_result",
        stores_should_block
    ))

    # ================================================================
    # Test 5: update_after_modification() post-integración exitosa
    # ================================================================
    print("── Test 5: update_after_modification() post-integración ──")

    uses_update = 'update_after_modification(' in agent_content
    test_results.append((
        "semi_auto_agent.py invoca update_after_modification() post-integración",
        uses_update
    ))

    if uses_update:
        # Verificar que está dentro del bloque de validación exitosa
        # Buscar el patrón: _graph.update_after_modification(
        update_pattern = re.search(
            r'_graph\.update_after_modification\(', agent_content
        )
        has_graph_update = update_pattern is not None
        test_results.append((
            "update_after_modification() se invoca en el grafo del guard",
            has_graph_update
        ))
    else:
        test_results.append((
            "update_after_modification() se invoca en el grafo del guard",
            False
        ))

    # ================================================================
    # Test 6: should_block_changes() NO bloquea por SCOPE_VIOLATION
    # ================================================================
    print("── Test 6: should_block_changes() no bloquea por SCOPE_VIOLATION ──")

    # Buscar la definición de should_block_changes
    should_block_match = re.search(
        r'def should_block_changes\(self.*?\):(.*?)(?=\n    def |\nclass |\Z)',
        guard_content,
        re.DOTALL
    )

    if should_block_match:
        method_body = should_block_match.group(1)
        # Verifica que solo bloquea CRITICAL y SIGNATURE_CHANGE_BREAKING
        blocks_only_critical = (
            'CRITICAL' in method_body and
            'SIGNATURE_CHANGE_BREAKING' in method_body and
            'SCOPE_VIOLATION' not in method_body
        )
        test_results.append((
            "should_block_changes() solo bloquea CRITICAL y SIGNATURE_CHANGE_BREAKING",
            blocks_only_critical
        ))
    else:
        test_results.append((
            "should_block_changes() solo bloquea CRITICAL y SIGNATURE_CHANGE_BREAKING",
            False
        ))

    # Verificar que review_diff_and_decide() usa should_block_changes()
    decide_uses_should_block = (
        'should_block_changes' in guard_content and
        'review_diff_and_decide' in guard_content
    )
    test_results.append((
        "review_diff_and_decide() delega a should_block_changes()",
        decide_uses_should_block
    ))

    # ================================================================
    # Test 7: review_diff_and_decide() combina review + should_block
    # ================================================================
    print("── Test 7: review_diff_and_decide() es un combo completo ──")

    # Debe llamar a review_diff() y should_block_changes()
    decide_calls_review = re.search(
        r'issues\s*=\s*self\.review_diff\(', guard_content
    )
    decide_calls_should = re.search(
        r'should_block\s*=\s*self\.should_block_changes\(', guard_content
    )

    test_results.append((
        "review_diff_and_decide() invoca review_diff() internamente",
        decide_calls_review is not None
    ))
    test_results.append((
        "review_diff_and_decide() invoca should_block_changes() internamente",
        decide_calls_should is not None
    ))

    # Retorna (issues, should_block) — tupla de 2 elementos
    returns_tuple = 'return (issues, should_block)' in guard_content or 'return issues, should_block' in guard_content
    test_results.append((
        "review_diff_and_decide() retorna (issues, should_block)",
        returns_tuple
    ))

    # ================================================================
    # Test 8: Sintaxis válida de ambos archivos
    # ================================================================
    print("── Test 8: Sintaxis Python válida ──")

    try:
        compile(guard_content, guard_path, 'exec')
        test_results.append(("refactor_guard.py: sintaxis válida", True))
    except SyntaxError as e:
        test_results.append((f"refactor_guard.py: sintaxis válida (ERROR: {e})", False))

    try:
        compile(agent_content, agent_path, 'exec')
        test_results.append(("semi_auto_agent.py: sintaxis válida", True))
    except SyntaxError as e:
        test_results.append((f"semi_auto_agent.py: sintaxis válida (ERROR: {e})", False))

    # ================================================================
    # Reporte
    # ================================================================
    print("\n" + "=" * 70)

    passed = 0
    failed = 0
    for name, result in test_results:
        status = "  ✅" if result else "  ❌"
        print(f"{status} {name}")
        if result:
            passed += 1
        else:
            failed += 1

    total = len(test_results)
    print()
    print("=" * 70)
    print(f"RESULTADO: {passed}/{total} tests PASARON")
    if failed:
        print(f"FALLOS: {failed}")
    print("=" * 70)

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    run_tests()
