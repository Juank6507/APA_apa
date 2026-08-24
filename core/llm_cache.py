# apa/core/llm_cache.py
import os
import sys
import json
import sqlite3
import hashlib
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
try:
    from config.settings import settings
except ImportError:
    class _DummySettings:
        LLM_CACHE_PATH = None
        LLM_CACHE_TTL_DAYS = 30
        log_level = 'INFO'
    settings = _DummySettings()

logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(getattr(logging, getattr(settings, 'log_level', 'DEBUG').upper(), logging.DEBUG))

class LLMCache:
    def __init__(self, cache_path: Optional[Path] = None, ttl_days: int = 30,
                 journal_mode: str = "WAL"):
        """Cache de respuestas LLM en SQLite.

        Usa una unica conexion persistente para evitar problemas de handles
        de archivo en Windows (Python 3.11+). La conexion se cierra
        explicitamente con close() o automaticamente via __del__.

        journal_mode controla como SQLite gestiona las escrituras:
          "WAL" (por defecto): mejor rendimiento en produccion con lecturas concurrentes
          "DELETE": modo simple, sin archivos auxiliares, compatible con Windows en tests
        """
        self._journal_mode = journal_mode

        # Resolver ruta: parámetro -> settings -> fallback por defecto
        if cache_path is None:
            cache_path = getattr(settings, 'LLM_CACHE_PATH', None)
        if cache_path is None:
            cache_path = Path(__file__).parents[1] / "cache" / "llm_cache.db"
        self.cache_path = Path(cache_path)
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)

        # Resolver TTL: parámetro -> settings
        self.ttl_days = ttl_days if ttl_days != 30 else getattr(settings, 'LLM_CACHE_TTL_DAYS', ttl_days)

        # Conexion persistente (una sola, reutilizada en todas las operaciones)
        self._conn = sqlite3.connect(str(self.cache_path))
        self._conn.execute(f"PRAGMA journal_mode={self._journal_mode}")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                prompt TEXT,
                model TEXT,
                response TEXT,
                created_at TEXT,
                expires_at TEXT
            )
        """)
        logger.debug(f"LLMCache inicializado en {self.cache_path}")

    def close(self) -> None:
        """Cierra la conexion a la base de datos."""
        try:
            if self._conn:
                self._conn.close()
                self._conn = None
        except Exception as e:
            logger.debug(f"Error cerrando LLMCache: {e}")

    def __del__(self):
        self.close()

    def _compute_key(self, prompt: str, model: str, **params) -> str:
        param_str = json.dumps(params, sort_keys=True, ensure_ascii=False)
        raw = f"{prompt}|{model}|{param_str}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, prompt: str, model: str, **params) -> Optional[Dict[str, Any]]:
        try:
            key = self._compute_key(prompt, model, **params)
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT response FROM cache WHERE key = ? AND expires_at > datetime('now')",
                (key,)
            )
            row = cursor.fetchone()
            if row:
                logger.debug(f"Cache HIT: {key[:8]}...")
                return json.loads(row[0])
            logger.debug(f"Cache MISS: {key[:8]}...")
            return None
        except Exception as e:
            logger.debug(f"Cache get falló: {e}")
            return None

    def set(self, prompt: str, model: str, response: Dict[str, Any], **params) -> None:
        try:
            key = self._compute_key(prompt, model, **params)
            now = datetime.utcnow()
            expires = (now + timedelta(days=self.ttl_days)).strftime('%Y-%m-%d %H:%M:%S')
            resp_json = json.dumps(response, ensure_ascii=False)
            self._conn.execute(
                "INSERT OR REPLACE INTO cache (key, prompt, model, response, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?)",
                (key, prompt, model, resp_json, now.isoformat(), expires)
            )
            self._conn.commit()
            logger.debug(f"Cache SET: {key[:8]}... (TTL: {self.ttl_days}d)")
        except Exception as e:
            logger.debug(f"Cache set falló: {e}")

    def clear_expired(self) -> int:
        try:
            cursor = self._conn.cursor()
            cursor.execute("DELETE FROM cache WHERE expires_at <= datetime('now')")
            deleted = cursor.rowcount
            self._conn.commit()
            if deleted > 0:
                logger.debug(f"Limpieza de caché: {deleted} entradas eliminadas")
            return deleted
        except Exception as e:
            logger.debug(f"Cache clear_expired falló: {e}")
            return 0


if __name__ == "__main__":
    import tempfile

    print("Iniciando pruebas de LLMCache...")

    # Se usa journal_mode="DELETE" en el test porque:
    # - WAL crea archivos -wal y -shm que Windows bloquea por memory-mapping
    # - DELETE no crea archivos auxiliares, asi que Windows puede liberar el .db
    #   inmediatamente al cerrar la conexion con close()
    # - La funcionalidad del cache es identica en ambos modos
    with tempfile.TemporaryDirectory() as tmpdir:
        test_db = Path(tmpdir) / "test_llm_cache_fix.db"
        cache = LLMCache(cache_path=test_db, ttl_days=30, journal_mode="DELETE")

        # Prueba 1: set/get correcto
        prompt = "Test prompt"
        model = "test-model"
        response = {"response": "Hola mundo", "model": "test-model", "tokens": 5}
        cache.set(prompt, model, response, temperature=0.7, max_tokens=100)
        cached = cache.get(prompt, model, temperature=0.7, max_tokens=100)
        assert cached == response, "Test 1 falló: set/get mismatch"
        print("✅ Prueba 1: set/get correcto")

        # Prueba 2: clave diferente retorna None
        cached_none = cache.get("Different prompt", model, temperature=0.7)
        assert cached_none is None, "Test 2 falló: debería retornar None"
        print("✅ Prueba 2: clave diferente retorna None")

        # Prueba 3: limpieza de expiradas
        old_expires = (datetime.utcnow() - timedelta(seconds=5)).strftime('%Y-%m-%d %H:%M:%S')
        old_key = cache._compute_key("Old prompt", "old-model", temperature=0.0)
        # Usar la conexion persistente de cache para insertar la fila expirada
        # (evita abrir una segunda conexion que lockearia el .db en Windows)
        cache._conn.execute(
            "INSERT OR REPLACE INTO cache (key, prompt, model, response, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?)",
            (old_key, "Old prompt", "old-model", "{}", old_expires, old_expires)
        )
        cache._conn.commit()
        deleted = cache.clear_expired()
        assert deleted >= 1, f"No se eliminaron entradas expiradas (deleted={deleted})"
        print("✅ Prueba 3: limpieza de expiradas")

        # Prueba 4: close() ejecuta sin error
        try:
            cache.close()
            print("✅ Prueba 4: close() ejecuta sin error")
        except Exception as e:
            print(f"❌ Prueba 4 falló: {e}")

    print("Todas las pruebas pasaron.")
