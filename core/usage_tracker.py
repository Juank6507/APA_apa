# apa/core/usage_tracker.py
# v2.0 — Métricas completas de uso LLM:
#         + provider, tokens_input, tokens_output, latency_ms,
#           cost_usd, arena_score, success, error_type
#         Migración automática de v1 → v2 (ALTER TABLE)
#         Backward compatible: log_usage() acepta kwargs opcionales
#
# CAMBIOS v2.0 vs v1:
#   - 8 columnas nuevas para métricas completas por llamada LLM
#   - Migración automática: si la tabla existe sin las columnas nuevas,
#     se añaden con ALTER TABLE (no pierde datos existentes)
#   - log_usage() acepta kwargs opcionales (backward compatible)
#   - get_aggregated_usage() retorna dict enriquecido con costes
#   - get_usage_details() nuevo método con todas las columnas
#   - get_usage_summary() resumen por modelo con avg latency, coste, éxito
#
# v1.0 — Sprint 1: Registro básico de tokens por llamada

import sqlite3
import os
import logging
from pathlib import Path
from typing import List, Dict, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)

# Columnas v2.0 — para migración automática
_V2_COLUMNS = {
    "provider": "TEXT DEFAULT ''",
    "tokens_input": "INTEGER DEFAULT 0",
    "tokens_output": "INTEGER DEFAULT 0",
    "latency_ms": "INTEGER DEFAULT 0",
    "cost_usd": "REAL DEFAULT 0.0",
    "arena_score": "REAL DEFAULT NULL",
    "success": "INTEGER DEFAULT 1",
    "error_type": "TEXT DEFAULT ''",
}


class UsageTracker:
    """
    Gestiona el registro de uso de tokens consumidos por llamadas a LLM.
    Almacena en SQLite: apa/data/usage.db

    v2.0: Métricas completas — provider, tokens in/out, latencia,
    coste estimado, Arena score, éxito/error por cada llamada.
    """

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            db_path = Path(__file__).parent.parent / "data" / "usage.db"
        self.db_path = Path(db_path)
        self._ensure_db_exists()

    def _ensure_db_exists(self) -> None:
        """Crea la base de datos y la tabla si no existen.
        Migra automáticamente de v1 a v2 añadiendo columnas faltantes."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        # Crear tabla si no existe (schema v2 completo)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                model TEXT NOT NULL,
                tokens INTEGER NOT NULL DEFAULT 0,
                request_type TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                provider TEXT DEFAULT '',
                tokens_input INTEGER DEFAULT 0,
                tokens_output INTEGER DEFAULT 0,
                latency_ms INTEGER DEFAULT 0,
                cost_usd REAL DEFAULT 0.0,
                arena_score REAL DEFAULT NULL,
                success INTEGER DEFAULT 1,
                error_type TEXT DEFAULT ''
            )
        """)

        # Migración v1 → v2: añadir columnas faltantes
        cursor.execute("PRAGMA table_info(usage)")
        existing_columns = {row[1] for row in cursor.fetchall()}

        for col_name, col_def in _V2_COLUMNS.items():
            if col_name not in existing_columns:
                try:
                    cursor.execute(
                        f"ALTER TABLE usage ADD COLUMN {col_name} {col_def}"
                    )
                    logger.info(f"Migration: columna '{col_name}' añadida a usage")
                except sqlite3.OperationalError as e:
                    logger.debug(f"Migration: columna '{col_name}' ya existe o error: {e}")

        conn.commit()
        conn.close()

    def log_usage(
        self,
        project_id: str,
        model: str,
        tokens: int,
        request_type: str,
        timestamp: Optional[datetime] = None,
        *,
        provider: str = "",
        tokens_input: int = 0,
        tokens_output: int = 0,
        latency_ms: int = 0,
        cost_usd: float = 0.0,
        arena_score: Optional[float] = None,
        success: bool = True,
        error_type: str = "",
    ) -> None:
        """Registra un uso de tokens para un proyecto.

        v2.0: Acepta métricas completas como kwargs opcionales.
        Backward compatible: los parámetros v1 (project_id, model, tokens,
        request_type) siguen funcionando igual.

        Args:
            project_id: ID del proyecto
            model: Modelo LLM usado
            tokens: Total de tokens (input + output)
            request_type: Tipo de request (planning, coding, assembly, etc.)
            timestamp: Momento de la llamada (default: ahora)
            provider: Proveedor usado (openrouter, anthropic, openai, etc.)
            tokens_input: Tokens de entrada (prompt)
            tokens_output: Tokens de salida (respuesta)
            latency_ms: Tiempo de respuesta en milisegundos
            cost_usd: Coste estimado en dólares
            arena_score: Score Arena del modelo al momento de la llamada
            success: Si la llamada tuvo éxito
            error_type: Tipo de error si falló (rate_limit, timeout, etc.)
        """
        if timestamp is None:
            timestamp = datetime.utcnow()
        ts_str = timestamp.isoformat()

        # Si tokens_input + tokens_output están disponibles, recalcular total
        if tokens == 0 and (tokens_input > 0 or tokens_output > 0):
            tokens = tokens_input + tokens_output

        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO usage (
                project_id, model, tokens, request_type, timestamp,
                provider, tokens_input, tokens_output, latency_ms,
                cost_usd, arena_score, success, error_type
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id, model, tokens, request_type, ts_str,
                provider, tokens_input, tokens_output, latency_ms,
                cost_usd, arena_score, 1 if success else 0, error_type,
            )
        )
        conn.commit()
        conn.close()

    def get_usage_by_project(self, project_id: str) -> List[Dict[str, Any]]:
        """Obtiene todos los registros de uso para un proyecto."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM usage WHERE project_id = ? ORDER BY timestamp DESC",
            (project_id,)
        )
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def get_aggregated_usage(self, project_id: str) -> Dict[str, int]:
        """Obtiene el uso agregado por modelo para un proyecto.
        Returns: {model: total_tokens}
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT model, SUM(tokens) as total_tokens
            FROM usage
            WHERE project_id = ?
            GROUP BY model
            """,
            (project_id,)
        )
        rows = cursor.fetchall()
        conn.close()
        return {row[0]: row[1] for row in rows}

    def get_usage_details(self, project_id: str) -> List[Dict[str, Any]]:
        """Obtiene registros detallados con todas las métricas v2.0.

        Returns: Lista de dicts con todas las columnas including
        provider, tokens_input, tokens_output, latency_ms, cost_usd,
        arena_score, success, error_type.
        """
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM usage
            WHERE project_id = ?
            ORDER BY timestamp DESC
            """,
            (project_id,)
        )
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def get_usage_summary(self, project_id: str) -> List[Dict[str, Any]]:
        """Resumen de uso por modelo con métricas agregadas.

        Returns: Lista de dicts con:
            model, provider, total_calls, total_tokens,
            total_tokens_input, total_tokens_output,
            avg_latency_ms, total_cost_usd, avg_arena_score, success_rate
        """
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                model,
                provider,
                COUNT(*) as total_calls,
                SUM(tokens) as total_tokens,
                SUM(tokens_input) as total_tokens_input,
                SUM(tokens_output) as total_tokens_output,
                AVG(latency_ms) as avg_latency_ms,
                SUM(cost_usd) as total_cost_usd,
                AVG(arena_score) as avg_arena_score,
                CAST(SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*) as success_rate
            FROM usage
            WHERE project_id = ?
            GROUP BY model, provider
            ORDER BY total_tokens DESC
            """,
            (project_id,)
        )
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def get_error_summary(self, project_id: str) -> List[Dict[str, Any]]:
        """Resumen de errores por tipo y modelo.

        Returns: Lista de dicts con:
            model, provider, error_type, count, last_error_timestamp
        """
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                model, provider, error_type,
                COUNT(*) as count,
                MAX(timestamp) as last_error_timestamp
            FROM usage
            WHERE project_id = ? AND success = 0
            GROUP BY model, provider, error_type
            ORDER BY count DESC
            """,
            (project_id,)
        )
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def get_avg_latency_by_language(self, limit_projects: int = 10) -> List[Dict[str, Any]]:
        """Tiempo medio de ejecución (latencia LLM) agrupado por lenguaje.

        Cruza datos de usage.db (latency_ms por project_id) con los plan.json
        de cada proyecto para obtener el lenguaje. Solo considera los últimos
        `limit_projects` proyectos con datos de uso.

        Returns: Lista de dicts con:
            language, avg_latency_ms, total_calls, projects_count
        """
        import json as _json

        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Obtener project_ids distintos con latency > 0, ordenados por fecha
        cursor.execute(
            """
            SELECT project_id, AVG(latency_ms) as avg_latency, COUNT(*) as calls
            FROM usage
            WHERE latency_ms > 0
            GROUP BY project_id
            ORDER BY MAX(timestamp) DESC
            LIMIT ?
            """,
            (limit_projects,)
        )
        project_latencies = {}
        for row in cursor.fetchall():
            d = dict(row)
            project_latencies[d["project_id"]] = {
                "avg_latency": d["avg_latency"],
                "calls": d["calls"],
            }
        conn.close()

        if not project_latencies:
            return []

        # Buscar el lenguaje de cada proyecto en su plan.json
        specs_dir = Path(self.db_path).parent.parent / "specs"
        language_data: Dict[str, Dict[str, Any]] = {}

        for project_id, latency_info in project_latencies.items():
            language = None

            # Intentar leer plan.json para obtener el lenguaje
            plan_path = specs_dir / project_id / "plan.json"
            if plan_path.exists():
                try:
                    plan = _json.loads(plan_path.read_text(encoding="utf-8"))
                    # Recoger lenguajes de las tareas
                    langs_found = set()
                    for task in plan.get("tasks", []):
                        lang = task.get("language")
                        if lang:
                            langs_found.add(lang)
                    # Si todas las tareas tienen el mismo lenguaje, usar ese
                    # Si hay varios o ninguno, inferir desde spec_summary
                    if len(langs_found) == 1:
                        language = langs_found.pop()
                    elif len(langs_found) > 1:
                        language = ", ".join(sorted(langs_found))
                except Exception:
                    pass

            # Fallback: inferir lenguaje desde el spec markdown
            if not language:
                for suffix in ("_spec.md", ".md"):
                    spec_path = specs_dir / f"{project_id}{suffix}"
                    if spec_path.exists():
                        try:
                            spec_content = spec_path.read_text(encoding="utf-8").lower()
                            # Heurística simple basada en patrones comunes
                            lang_patterns = {
                                "python": [".py", "python", "pip", "django", "flask"],
                                "javascript": [".js", "javascript", "node", "npm", "react"],
                                "bash": [".sh", "bash", "shell"],
                                "sql": [".sql", "sqlite", "postgresql"],
                                "cpp": [".cpp", "c++", "g++", "cmake"],
                                "dart": [".dart", "flutter"],
                                "react-native": ["react native", "react-native", "jsx"],
                            }
                            best_lang = None
                            best_score = 0
                            for lang, patterns in lang_patterns.items():
                                score = sum(1 for p in patterns if p in spec_content)
                                if score > best_score:
                                    best_score = score
                                    best_lang = lang
                            if best_lang and best_score >= 1:
                                language = best_lang
                        except Exception:
                            pass
                        break

            if not language:
                language = "otro"

            # Agregar datos por lenguaje
            if language not in language_data:
                language_data[language] = {
                    "language": language,
                    "total_latency_ms": 0.0,
                    "total_calls": 0,
                    "projects_count": 0,
                }
            language_data[language]["total_latency_ms"] += (
                latency_info["avg_latency"] * latency_info["calls"]
            )
            language_data[language]["total_calls"] += latency_info["calls"]
            language_data[language]["projects_count"] += 1

        # Calcular promedios
        result = []
        for lang, data in language_data.items():
            avg = (
                data["total_latency_ms"] / data["total_calls"]
                if data["total_calls"] > 0
                else 0
            )
            result.append({
                "language": lang,
                "avg_latency_ms": round(avg, 1),
                "total_calls": data["total_calls"],
                "projects_count": data["projects_count"],
            })

        # Ordenar por avg_latency_ms descendente
        result.sort(key=lambda x: x["avg_latency_ms"], reverse=True)
        return result

    def get_column_names(self) -> List[str]:
        """Retorna los nombres de las columnas de la tabla usage."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(usage)")
        columns = [row[1] for row in cursor.fetchall()]
        conn.close()
        return columns


if __name__ == "__main__":
    import tempfile
    import shutil

    temp_dir = tempfile.mkdtemp()
    test_db = Path(temp_dir) / "test_usage.db"

    try:
        tracker = UsageTracker(db_path=test_db)

        # --- Test 1: Columnas v2.0 ---
        columns = tracker.get_column_names()
        print(f"Columnas: {columns}")
        required = {"provider", "tokens_input", "tokens_output", "latency_ms",
                     "cost_usd", "arena_score", "success", "error_type"}
        missing = required - set(columns)
        assert not missing, f"Faltan columnas: {missing}"
        print("[OK] Test 1: Columnas v2.0 completas")

        # --- Test 2: log_usage con métricas completas ---
        # Usar timestamps explícitos para garantizar orden determinista
        ts1 = datetime(2026, 1, 1, 10, 0, 0)
        ts2 = datetime(2026, 1, 1, 10, 0, 1)
        ts3 = datetime(2026, 1, 1, 10, 0, 2)

        tracker.log_usage(
            "test_proj", "anthropic/claude-3-5-sonnet", 500, "planning",
            timestamp=ts1,
            provider="anthropic",
            tokens_input=300, tokens_output=200,
            latency_ms=1500, cost_usd=0.012,
            arena_score=85.3, success=True, error_type=""
        )
        tracker.log_usage(
            "test_proj", "openai/gpt-4o", 800, "coding",
            timestamp=ts2,
            provider="openai",
            tokens_input=500, tokens_output=300,
            latency_ms=2000, cost_usd=0.025,
            arena_score=71.4, success=True, error_type=""
        )
        tracker.log_usage(
            "test_proj", "openai/gpt-4o", 0, "correction",
            timestamp=ts3,
            provider="openai",
            tokens_input=100, tokens_output=50,
            latency_ms=800, cost_usd=0.005,
            arena_score=71.4, success=False, error_type="rate_limit"
        )
        details = tracker.get_usage_details("test_proj")
        assert len(details) == 3, f"Esperados 3 registros, obtenidos {len(details)}"
        # Verificar que tokens se recalcula cuando es 0
        # details ordenado por timestamp DESC → details[0] = ts3 (tokens=0→150)
        recalculated = details[0]
        assert recalculated["tokens"] == 150, f"Tokens recalculado: esperado 150, obtenido {recalculated['tokens']}"
        print("[OK] Test 2: log_usage con métricas completas")

        # --- Test 3: Backward compatibility (sin kwargs) ---
        tracker.log_usage("test_proj", "qwen/qwen2.5-coder", 150, "generation")
        details = tracker.get_usage_details("test_proj")
        last = details[0]  # Más reciente primero
        assert last["provider"] == "", f"Provider default vacío: {last['provider']}"
        assert last["success"] == 1, f"Success default: {last['success']}"
        print("[OK] Test 3: Backward compatible")

        # --- Test 4: Agregación v1 sigue funcionando ---
        aggregated = tracker.get_aggregated_usage("test_proj")
        assert aggregated.get("openai/gpt-4o") == 950, f"Tokens gpt-4o: {aggregated.get('openai/gpt-4o')}"
        print("[OK] Test 4: get_aggregated_usage compatible")

        # --- Test 5: Usage summary ---
        summary = tracker.get_usage_summary("test_proj")
        gpt4o = [s for s in summary if s["model"] == "openai/gpt-4o"][0]
        assert gpt4o["total_calls"] == 2, f"Calls gpt-4o: {gpt4o['total_calls']}"
        assert gpt4o["success_rate"] == 0.5, f"Success rate: {gpt4o['success_rate']}"
        print("[OK] Test 5: get_usage_summary")

        # --- Test 6: Error summary ---
        errors = tracker.get_error_summary("test_proj")
        assert len(errors) == 1, f"Errors: {len(errors)}"
        assert errors[0]["error_type"] == "rate_limit"
        print("[OK] Test 6: get_error_summary")

        # --- Test 7: Migración v1 → v2 ---
        # Crear DB con schema v1 y verificar migración
        test_db_v1 = Path(temp_dir) / "test_v1.db"
        conn = sqlite3.connect(str(test_db_v1))
        conn.execute("""
            CREATE TABLE usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                model TEXT NOT NULL,
                tokens INTEGER NOT NULL,
                request_type TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
        """)
        conn.execute(
            "INSERT INTO usage (project_id, model, tokens, request_type, timestamp) "
            "VALUES ('old_proj', 'old_model', 100, 'planning', '2024-01-01T00:00:00')"
        )
        conn.commit()
        conn.close()

        # Abrir con UsageTracker → debe migrar
        tracker_v2 = UsageTracker(db_path=test_db_v1)
        cols = tracker_v2.get_column_names()
        assert "provider" in cols, f"Migración falló: columnas = {cols}"
        # Verificar que datos antiguos se preservan
        old_data = tracker_v2.get_aggregated_usage("old_proj")
        assert old_data.get("old_model") == 100, f"Datos v1 perdidos: {old_data}"
        print("[OK] Test 7: Migración v1 → v2 (datos preservados)")

        print("\nUsageTracker v2.0 — Todos los tests pasados.")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
