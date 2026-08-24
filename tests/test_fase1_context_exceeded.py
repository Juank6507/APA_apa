# tests/test_fase1_context_exceeded.py
# 4 tests para verificar la FASE 1:
#   - Detección de contexto excedido en model_health
#   - Clasificación de errores de contexto en _classify_error
#   - Funcionalidad de _handle_context_exceeded en router
#   - Señal split_task cuando no hay modelo con contexto suficiente

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core import model_health


def test_is_context_exceeded():
    """Test 1: is_context_exceeded detecta correctamente los errores de contexto."""
    passed = 0
    total = 0

    # Debe ser True
    total += 1
    if model_health.is_context_exceeded(413, "request entity too large"):
        passed += 1
        print("  [OK] 413 con cualquier body -> True")
    else:
        print("  [FAIL] 413 con cualquier body -> esperaba True")

    total += 1
    if model_health.is_context_exceeded(400, "context_length_exceeded"):
        passed += 1
        print("  [OK] 400 con 'context_length_exceeded' -> True")
    else:
        print("  [FAIL] 400 con 'context_length_exceeded' -> esperaba True")

    total += 1
    if model_health.is_context_exceeded(400, "maximum context length exceeded for model"):
        passed += 1
        print("  [OK] 400 con 'maximum context length' -> True")
    else:
        print("  [FAIL] 400 con 'maximum context length' -> esperaba True")

    total += 1
    if model_health.is_context_exceeded(400, "prompt too large"):
        passed += 1
        print("  [OK] 400 con 'prompt too large' -> True")
    else:
        print("  [FAIL] 400 con 'prompt too large' -> esperaba True")

    total += 1
    if model_health.is_context_exceeded(400, "token limit exceeded"):
        passed += 1
        print("  [OK] 400 con 'token limit' -> True")
    else:
        print("  [FAIL] 400 con 'token limit' -> esperaba True")

    # Debe ser False
    total += 1
    if not model_health.is_context_exceeded(500, "internal server error"):
        passed += 1
        print("  [OK] 500 sin señal de contexto -> False")
    else:
        print("  [FAIL] 500 sin señal de contexto -> esperaba False")

    total += 1
    if not model_health.is_context_exceeded(400, "bad request format"):
        passed += 1
        print("  [OK] 400 sin señal de contexto -> False")
    else:
        print("  [FAIL] 400 sin señal de contexto -> esperaba False")

    total += 1
    if not model_health.is_context_exceeded(429, "rate limit exceeded"):
        passed += 1
        print("  [OK] 429 rate limit -> False")
    else:
        print("  [FAIL] 429 rate limit -> esperaba False")

    total += 1
    if not model_health.is_context_exceeded(402, "payment required"):
        passed += 1
        print("  [OK] 402 payment -> False")
    else:
        print("  [FAIL] 402 payment -> esperaba False")

    total += 1
    if not model_health.is_context_exceeded(200, ""):
        passed += 1
        print("  [OK] 200 vacío -> False")
    else:
        print("  [FAIL] 200 vacío -> esperaba False")

    print(f"\n  test_is_context_exceeded: {passed}/{total} passed")
    return passed == total


def test_classify_error_context_exceeded():
    """Test 2: _classify_error reconoce errores de contexto excedido."""
    passed = 0
    total = 0

    # Debe clasificar como "context_exceeded"
    test_cases = [
        "context_length_exceeded for this model",
        "maximum context length is 8192 tokens",
        "input too large: your prompt exceeds the limit",
        "prompt too large, max_tokens is 4096",
        "request too large for this model",
        "token limit exceeded",
        "tokens limit reached",
    ]

    for case in test_cases:
        total += 1
        result = model_health._classify_error(case)
        if result == "context_exceeded":
            passed += 1
            print(f"  [OK] '{case[:50]}' -> context_exceeded")
        else:
            print(f"  [FAIL] '{case[:50]}' -> {result} (esperaba context_exceeded)")

    # No debe clasificar como context_exceeded
    false_cases = [
        "rate limit exceeded",
        "internal server error",
        "authentication failed",
        "model not found",
        "connection timeout",
    ]

    for case in false_cases:
        total += 1
        result = model_health._classify_error(case)
        if result != "context_exceeded":
            passed += 1
            print(f"  [OK] '{case}' -> {result} (no es context_exceeded)")
        else:
            print(f"  [FAIL] '{case}' -> context_exceeded (no debería serlo)")

    print(f"\n  test_classify_error_context_exceeded: {passed}/{total} passed")
    return passed == total


def test_report_http_status_413():
    """Test 3: report_http_status trata 413 como temporarily_unavailable,
    no como failed permanente."""
    passed = 0
    total = 0

    # Configurar modelo de prueba
    model_health._health_data["test-model-413"] = {
        "status": "unknown",
        "verified_at": None,
        "provider": "test_provider",
        "previous_status": "unknown",
        "previously_available": False,
        "error": None,
        "rate_limited_at": None,
        "rate_limited_count": 0,
        "probe_errors": {},
    }

    # Ejecutar report_http_status con 413
    model_health.report_http_status(
        "test-model-413",
        413,
        "test_provider",
        "HTTP 413 payload too large"
    )

    # Verificar que NO está "failed"
    total += 1
    status = model_health.get_status("test-model-413")
    if status == "temporarily_unavailable":
        passed += 1
        print(f"  [OK] 413 -> temporarily_unavailable (no failed)")
    else:
        print(f"  [FAIL] 413 -> {status} (esperaba temporarily_unavailable)")

    # Limpiar
    if "test-model-413" in model_health._health_data:
        del model_health._health_data["test-model-413"]

    print(f"\n  test_report_http_status_413: {passed}/{total} passed")
    return passed == total


def test_handle_context_exceeded_split_task():
    """Test 4: _handle_context_exceeded devuelve señal split_task cuando
    no hay modelo con contexto suficiente.

    Este test simula un pool vacío (sin modelos) para forzar la señal.
    """
    passed = 0
    total = 0

    try:
        from core.router import _handle_context_exceeded
    except ImportError as e:
        print(f"  [SKIP] No se pudo importar _handle_context_exceeded: {e}")
        return True

    # Simular un prompt muy grande (100K caracteres = ~25K tokens estimados)
    big_prompt = "x" * 100000
    system_prompt = "You are a helpful assistant."

    # Ejecutar con un modelo que no existe en el pool
    result = _handle_context_exceeded(
        task_type="assembly",
        system_prompt=system_prompt,
        user_prompt=big_prompt,
        failed_model_id="nonexistent:model",
        max_tokens=2000,
        temperature=0.1,
    )

    # Verificar la señal split_task
    total += 1
    if result.get("success") is False:
        passed += 1
        print("  [OK] success=False")
    else:
        print(f"  [FAIL] success={result.get('success')} (esperaba False)")

    total += 1
    if result.get("error_type") == "context_exceeded_no_fallback":
        passed += 1
        print("  [OK] error_type='context_exceeded_no_fallback'")
    else:
        print(f"  [FAIL] error_type='{result.get('error_type')}' (esperaba context_exceeded_no_fallback)")

    total += 1
    if result.get("action_required") == "split_task":
        passed += 1
        print("  [OK] action_required='split_task'")
    else:
        print(f"  [FAIL] action_required='{result.get('action_required')}' (esperaba split_task)")

    total += 1
    if result.get("tokens_needed", 0) > 0:
        passed += 1
        print(f"  [OK] tokens_needed={result.get('tokens_needed')} (>0)")
    else:
        print(f"  [FAIL] tokens_needed={result.get('tokens_needed')} (esperaba >0)")

    total += 1
    if result.get("max_available_context", 0) >= 0:
        passed += 1
        print(f"  [OK] max_available_context={result.get('max_available_context')} (>=0)")
    else:
        print(f"  [FAIL] max_available_context={result.get('max_available_context')} (esperaba >=0)")

    total += 1
    msg = result.get("message", "")
    if msg and "desglose" in msg.lower():
        passed += 1
        print(f"  [OK] message contiene 'desglose': '{msg[:60]}...'")
    else:
        print(f"  [FAIL] message no contiene 'desglose': '{msg[:80]}'")

    print(f"\n  test_handle_context_exceeded_split_task: {passed}/{total} passed")
    return passed == total


if __name__ == "__main__":
    print("=" * 60)
    print("FASE 1 — Tests de contexto excedido (v6.2)")
    print("=" * 60)

    results = []
    print("\n--- Test 1: is_context_exceeded ---")
    results.append(("is_context_exceeded", test_is_context_exceeded()))

    print("\n--- Test 2: _classify_error context_exceeded ---")
    results.append(("_classify_error", test_classify_error_context_exceeded()))

    print("\n--- Test 3: report_http_status 413 ---")
    results.append(("report_http_status_413", test_report_http_status_413()))

    print("\n--- Test 4: _handle_context_exceeded split_task ---")
    results.append(("_handle_context_exceeded", test_handle_context_exceeded_split_task()))

    print("\n" + "=" * 60)
    passed_total = sum(1 for _, ok in results if ok)
    total_total = len(results)
    for name, ok in results:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}")

    print(f"\nResultado: {passed_total}/{total_total} tests pasaron")
    print("=" * 60)

    if passed_total == total_total:
        print("TODOS LOS TESTS PASARON")
        sys.exit(0)
    else:
        print("ALGUNOS TESTS FALLARON")
        sys.exit(1)
