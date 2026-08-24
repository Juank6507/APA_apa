# diagnostic_5providers.py v1.0
# Script de diagnóstico para los 5 proveedores problemáticos:
#   SambaNova, SiliconFlow, Cloudflare, Cohere, Fireworks
#
# Este script NO hace llamadas a modelos. Solo prueba:
#   1. Si la API key está cargada en settings
#   2. Si la petición GET /models llega a la API
#   3. Qué status code devuelve
#   4. Qué estructura tiene la respuesta
#   5. Cuántos modelos se pueden extraer
#
# USO: python diagnostic_5providers.py
# ============================================================

import sys
import os
import json
import time
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from config.settings import settings

SEPARATOR = "=" * 70

def diagnose_provider(name, api_key, base_url, extra_checks=None):
    """Diagnostica un proveedor: key, petición, respuesta, modelos."""
    print(f"\n{SEPARATOR}")
    print(f"  PROVEEDOR: {name.upper()}")
    print(f"  URL base: {base_url}")
    print(f"{SEPARATOR}")

    # 1. Verificar API key
    issues = []
    if not api_key or not api_key.strip():
        print(f"  [FALLO] API key: VACIA — el proveedor no puede funcionar")
        print(f"  ACCION: Revisa que la variable de entorno en .env tenga valor")
        issues.append("API key vacia")
        return issues
    else:
        masked = api_key[:6] + "..." + api_key[-4:] if len(api_key) > 10 else "***"
        print(f"  [OK] API key cargada: {masked}")

    # Extra checks (ej: cf_account_id para Cloudflare)
    if extra_checks:
        for check_name, check_value in extra_checks.items():
            if not check_value or not check_value.strip():
                print(f"  [FALLO] {check_name}: VACIO — necesario para este proveedor")
                issues.append(f"{check_name} vacio")
            else:
                print(f"  [OK] {check_name}: {check_value[:8]}...{check_value[-4:] if len(check_value) > 12 else ''}")

    if issues:
        print(f"\n  RESULTADO: No se puede conectar — faltan datos obligatorios")
        return issues

    # 2. Hacer petición GET /models
    print(f"\n  --- Peticion GET /models ---")
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        t0 = time.time()
        resp = requests.get(f"{base_url}/models", headers=headers, timeout=10)
        elapsed = time.time() - t0
        print(f"  [OK] Respuesta en {elapsed:.2f}s — Status: {resp.status_code}")
    except requests.exceptions.ConnectionError as e:
        print(f"  [FALLO] ConnectionError: No se pudo conectar a {base_url}")
        print(f"  DETALLE: {str(e)[:200]}")
        issues.append("ConnectionError")
        return issues
    except requests.exceptions.Timeout:
        print(f"  [FALLO] Timeout: La API no respondio en 10s")
        issues.append("Timeout")
        return issues
    except Exception as e:
        print(f"  [FALLO] Error inesperado: {type(e).__name__}: {str(e)[:200]}")
        issues.append(f"Error: {type(e).__name__}")
        return issues

    # 3. Analizar respuesta
    if resp.status_code != 200:
        print(f"  [FALLO] Status != 200")
        try:
            body = resp.json()
            print(f"  Body: {json.dumps(body, indent=2)[:500]}")
        except Exception:
            print(f"  Body (texto): {resp.text[:300]}")
        issues.append(f"HTTP {resp.status_code}")
        return issues

    # 4. Parsear estructura
    print(f"\n  --- Analisis de estructura ---")
    try:
        body = resp.json()
    except json.JSONDecodeError:
        print(f"  [FALLO] La respuesta no es JSON valido")
        print(f"  Body: {resp.text[:300]}")
        issues.append("Respuesta no es JSON")
        return issues

    print(f"  Claves en respuesta: {list(body.keys()) if isinstance(body, dict) else type(body).__name__}")

    # Intentar extraer modelos de diferentes estructuras posibles
    models_found = []
    data_key = None

    if isinstance(body, dict):
        for key in ["data", "models", "items"]:
            if key in body and isinstance(body[key], list):
                data_key = key
                models_found = body[key]
                break
    elif isinstance(body, list):
        data_key = "(root)"
        models_found = body

    if not models_found:
        print(f"  [FALLO] No se encontró lista de modelos en la respuesta")
        print(f"  Estructura recibida: {json.dumps(body, indent=2)[:500]}")
        issues.append("Sin lista de modelos")
        return issues

    print(f"  [OK] Lista de modelos en clave: '{data_key}' ({len(models_found)} elementos)")

    # 5. Analizar primeros modelos
    if models_found:
        print(f"\n  --- Primeros 3 modelos ---")
        for i, m in enumerate(models_found[:3]):
            if isinstance(m, dict):
                mid = m.get("id") or m.get("name") or m.get("model") or "(sin id)"
                print(f"  [{i}] {mid} — claves: {list(m.keys())}")
            else:
                print(f"  [{i}] {m} (tipo: {type(m).__name__})")

    print(f"\n  RESULTADO: {len(models_found)} modelos en la respuesta")
    return issues  # Lista vacía = todo OK


if __name__ == "__main__":
    print(f"\n{SEPARATOR}")
    print(f"  APA — DIAGNOSTICO DE 5 PROVEEDORES PROBLEMATICOS")
    print(f"  Fecha: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{SEPARATOR}")

    all_issues = {}

    # 1. SambaNova
    issues = diagnose_provider(
        name="SambaNova",
        api_key=settings.sambanova_api_key,
        base_url="https://api.sambanova.ai/v1"
    )
    all_issues["SambaNova"] = issues

    # 2. SiliconFlow
    issues = diagnose_provider(
        name="SiliconFlow",
        api_key=settings.siliconflow_api_key,
        base_url="https://api.siliconflow.com/v1"
    )
    all_issues["SiliconFlow"] = issues

    # 3. Cloudflare (necesita 2 keys)
    issues = diagnose_provider(
        name="Cloudflare",
        api_key=settings.cloudflare_api_token,
        base_url=f"https://api.cloudflare.com/client/v4/accounts/{settings.cf_account_id}/ai/v1",
        extra_checks={"cf_account_id": settings.cf_account_id}
    )
    all_issues["Cloudflare"] = issues

    # 4. Cohere
    issues = diagnose_provider(
        name="Cohere",
        api_key=settings.cohere_api_key,
        base_url="https://api.cohere.com/v1"
    )
    all_issues["Cohere"] = issues

    # 5. Fireworks
    issues = diagnose_provider(
        name="Fireworks",
        api_key=settings.fireworks_api_key,
        base_url="https://api.fireworks.ai/inference/v1"
    )
    all_issues["Fireworks"] = issues

    # Resumen final
    print(f"\n{SEPARATOR}")
    print(f"  RESUMEN FINAL")
    print(f"{SEPARATOR}")
    for name, issues in all_issues.items():
        if not issues:
            print(f"  {name}: OK — sin problemas detectados")
        else:
            print(f"  {name}: ISSUES → {', '.join(issues)}")

    print(f"\n{SEPARATOR}")