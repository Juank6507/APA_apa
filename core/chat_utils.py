"""
chat_utils.py — Gestión de conversaciones: caché, commit, listado, carga.

Funcionalidad extraida de app.py (Punto 5: guardar/recuperar conversaciones).
Cada funcion es pura (recibe dependencias por parametro) y testeable sin FastAPI.
"""
import json
import re
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


def reset_guide(sdd_guide) -> dict:
    """Resetea el estado de la guia CV2 entre conversaciones."""
    try:
        sdd_guide.reset()
        return {"success": True}
    except Exception as e:
        logger.warning("Error reseteando guia CV2: %s", e)
        return {"error": str(e), "_status": 500}


def cache_chat(chat_id: str, body: dict, cache: dict) -> dict:
    """Guarda estado de conversacion madura en cache (memoria).

    El frontend envia datos completos despues de cada interaccion cuando
    la madurez llega a 5/5 imprescindibles.
    """
    if not chat_id:
        return {"error": "chat_id requerido", "_status": 400}

    cache[chat_id] = {
        "chat_id": chat_id,
        "updated_at": datetime.now().isoformat(),
        "messages": body.get("messages", []),
        "project_name": body.get("project_name", ""),
        "project_path": body.get("project_path", ""),
        "project_variant": body.get("project_variant", ""),
        "sdd_status": body.get("sdd_status"),
        "objective_summary": body.get("objective_summary", ""),
        "maturity_summary": body.get("maturity_summary", ""),
    }
    logger.info("Chat %s cacheado (%d msgs)", chat_id, len(body.get('messages', [])))
    return {"success": True, "cached": True}


def commit_chat(chat_id: str, body: dict, cache: dict, chats_dir: Path) -> dict:
    """Salva el cache a disco.

    Se invoca al pulsar 'Generar SDD', al cerrar la pestana (beforeunload),
    o al iniciar una nueva conversacion.
    Nombre del archivo: chat_{N}_{nombre_slug}.json
    """
    if not chat_id:
        return {"success": True, "committed": False, "reason": "no_chat_id"}

    cached = cache.get(chat_id)
    # C4: Si no hay cache en memoria (backend reiniciado), usar datos del frontend
    if not cached and body.get("messages"):
        cached = {
            "chat_id": chat_id,
            "updated_at": datetime.now().isoformat(),
            "messages": body.get("messages", []),
            "project_name": body.get("project_name", ""),
            "project_path": body.get("project_path", ""),
            "project_variant": body.get("project_variant", ""),
            "sdd_status": body.get("sdd_status"),
            "objective_summary": body.get("objective_summary", ""),
            "maturity_summary": body.get("maturity_summary", ""),
        }
        logger.info("C4: Commit con datos de respaldo del frontend para %s", chat_id)
    if not cached:
        return {"success": True, "committed": False, "reason": "no_cache"}

    project_name = cached.get("project_name", "proyecto").strip()
    if not project_name:
        project_name = "proyecto"

    # Slug: minusculas, espacios -> guiones bajos, solo alfanumericos y guiones
    slug = re.sub(r'[^a-z0-9aeioun_\-]', '', project_name.lower().replace(" ", "_"))
    slug = re.sub(r'_+', '_', slug).strip('_')
    if not slug:
        slug = "sin_nombre"

    # Numero secuencial: contar chat_*.json existentes
    existing = [f for f in chats_dir.iterdir() if f.suffix == '.json' and f.name.startswith('chat_')]
    n = len(existing) + 1

    filename = f"chat_{n}_{slug}.json"
    filepath = chats_dir / filename

    # Construir paquete completo para disco
    disk_data = {
        "chat_id": filename,
        "chat_n": n,
        "project_name": project_name,
        "created_at": cached.get("created_at", cached.get("updated_at", datetime.now().isoformat())),
        "updated_at": datetime.now().isoformat(),
        "messages": cached.get("messages", []),
        "project_path": cached.get("project_path", ""),
        "project_variant": cached.get("project_variant", ""),
        "sdd_status": cached.get("sdd_status"),
        "objective_summary": cached.get("objective_summary", ""),
        "maturity_summary": cached.get("maturity_summary", ""),
        "spec_generated": body.get("spec_generated", False),
    }

    filepath.write_text(json.dumps(disk_data, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Chat salvado a disco -> %s", filename)

    # Limpiar del cache en memoria
    if chat_id in cache:
        del cache[chat_id]

    return {"success": True, "committed": True, "filename": filename}


def list_chats(chats_dir: Path) -> dict:
    """Lista todas las conversaciones guardadas en disco.

    Retorna indice con: chat_id, name, n, date, messages, has_spec.
    """
    chats = []
    for fpath in sorted(chats_dir.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True):
        if fpath.suffix != '.json' or not fpath.name.startswith('chat_'):
            continue
        try:
            data = json.loads(fpath.read_text(encoding='utf-8'))
            chats.append({
                "chat_id": fpath.name,
                "name": data.get("project_name", "Sin nombre"),
                "n": data.get("chat_n", 0),
                "date": data.get("updated_at", ""),
                "messages": len(data.get("messages", [])),
                "has_spec": data.get("spec_generated", False),
            })
        except Exception:
            continue
    return {"success": True, "chats": chats}


def load_chat(filename: str, chats_dir: Path) -> dict:
    """Carga una conversacion guardada desde disco.

    Retorna el JSON completo de la sesion o un error.
    """
    # Sanitizar: solo permitir nombres que empiezan con chat_ y terminan con .json
    if not filename.startswith("chat_") or not filename.endswith(".json"):
        return {"error": "Nombre de archivo invalido", "_status": 400}
    # No permitir path traversal
    if "/" in filename or "\\" in filename or ".." in filename:
        return {"error": "Nombre de archivo invalido", "_status": 400}

    filepath = chats_dir / filename
    if not filepath.exists():
        return {"error": "Conversacion no encontrada", "_status": 404}

    try:
        data = json.loads(filepath.read_text(encoding='utf-8'))
        return {"success": True, "chat": data}
    except Exception as e:
        return {"error": str(e), "_status": 500}


# =====================================================================
# TESTS AUTONOMOS
# =====================================================================
if __name__ == "__main__":
    import sys, tempfile, shutil
    passed = 0
    failed = 0

    def _check(name, condition):
        global passed, failed
        if condition:
            print(f"  [PASS] {name}")
            passed += 1
        else:
            print(f"  [FAIL] {name}")
            failed += 1

    print("=" * 60)
    print("TESTS AUTONOMOS: chat_utils.py")
    print("=" * 60)

    # Test 1: cache_chat basico
    cache = {}
    result = cache_chat("c1", {"messages": [{"role": "user", "content": "hola"}], "project_name": "Test"}, cache)
    _check("cache_chat guarda en cache", result.get("success") is True)
    _check("cache_chat contiene mensajes", "c1" in cache and len(cache["c1"]["messages"]) == 1)

    # Test 2: cache_chat sin chat_id
    result = cache_chat("", {}, cache)
    _check("cache_chat sin chat_id retorna error", "_status" in result)

    # Test 3: commit_chat a disco
    tmp = Path(tempfile.mkdtemp())
    try:
        cache["c2"] = {
            "chat_id": "c2", "updated_at": "2025-01-01T00:00:00",
            "messages": [{"role": "user", "content": "test"}],
            "project_name": "Mi Proyecto", "project_path": "", "project_variant": "",
            "sdd_status": None, "objective_summary": "", "maturity_summary": "",
        }
        result = commit_chat("c2", {"spec_generated": True}, cache, tmp)
        _check("commit_chat exitoso", result.get("committed") is True)
        _check("commit_chat genera archivo", result.get("filename", "").startswith("chat_"))
        _check("commit_chat limpia cache", "c2" not in cache)

        # Verificar contenido del archivo
        filepath = tmp / result["filename"]
        data = json.loads(filepath.read_text(encoding='utf-8'))
        _check("commit_chat contenido correcto", data["project_name"] == "Mi Proyecto")
        _check("commit_chat spec_generated", data.get("spec_generated") is True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # Test 4: commit_chat sin cache y con datos frontend
    cache2 = {}
    tmp2 = Path(tempfile.mkdtemp())
    try:
        result = commit_chat("c3", {
            "messages": [{"role": "user", "content": "hola"}],
            "project_name": "Desde Frontend", "spec_generated": False,
        }, cache2, tmp2)
        _check("commit_chat fallback frontend", result.get("committed") is True)
    finally:
        shutil.rmtree(tmp2, ignore_errors=True)

    # Test 5: commit_chat sin chat_id
    result = commit_chat("", {}, {}, tmp if tmp.exists() else Path("/tmp"))
    _check("commit_chat sin id retorna no_chat_id", result.get("reason") == "no_chat_id")

    # Test 6: list_chats
    tmp3 = Path(tempfile.mkdtemp())
    try:
        (tmp3 / "chat_1_test.json").write_text(json.dumps({
            "project_name": "P1", "chat_n": 1, "updated_at": "2025-01-01",
            "messages": [{"r": "u", "c": "a"}, {"r": "u", "c": "b"}],
            "spec_generated": True,
        }), encoding="utf-8")
        (tmp3 / "chat_2_otro.json").write_text(json.dumps({
            "project_name": "P2", "chat_n": 2, "updated_at": "2025-01-02",
            "messages": [], "spec_generated": False,
        }), encoding="utf-8")
        (tmp3 / "otro_archivo.txt").write_text("no es chat")
        result = list_chats(tmp3)
        _check("list_chats retorna 2 chats", len(result.get("chats", [])) == 2)
        _check("list_chats success", result.get("success") is True)
    finally:
        shutil.rmtree(tmp3, ignore_errors=True)

    # Test 7: load_chat
    tmp4 = Path(tempfile.mkdtemp())
    try:
        (tmp4 / "chat_1_test.json").write_text(json.dumps({"chat_id": "ok", "data": 42}), encoding="utf-8")
        result = load_chat("chat_1_test.json", tmp4)
        _check("load_chat exitoso", result.get("success") is True and result["chat"]["data"] == 42)

        result = load_chat("mal_nombre.txt", tmp4)
        _check("load_chat rechaza nombre invalido", "_status" in result)

        result = load_chat("../etc/passwd", tmp4)
        _check("load_chat rechaza path traversal", "_status" in result)

        result = load_chat("chat_999_no_existe.json", tmp4)
        _check("load_chat 404 si no existe", result.get("_status") == 404)
    finally:
        shutil.rmtree(tmp4, ignore_errors=True)

    # Test 8: reset_guide
    mock_guide = type('MockGuide', (), {'reset': lambda self: None})()
    result = reset_guide(mock_guide)
    _check("reset_guide exitoso", result.get("success") is True)

    print("-" * 60)
    total = passed + failed
    print(f"Resultado: {passed}/{total} pasaron")
    print("=" * 60)
    sys.exit(0 if failed == 0 else 1)
