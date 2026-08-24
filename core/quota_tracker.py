#!/usr/bin/env python3
# apa/core/quota_tracker.py
# T4 — QuotaTracker: seguimiento de cuotas por proveedor.
#
# v1.0.1 — FIX: validación usa tempfile.gettempdir() en vez de /tmp/
#           para compatibilidad Windows/Linux.
#
# Funcionalidades:
#   - Límite de gasto diario por proveedor (configurable en settings.py)
#   - Límite de gasto global diario
#   - Pre-flight check: verificar si una llamada está permitida antes de hacerla
#   - Auto-block: bloquea proveedores que agotaron su cuota
#   - Historial de gastos por ventana temporal
#   - Persistencia en usage.db (tabla 'quotas' + 'provider_spending')
#
# Integración:
#   - router.py: check_quota() antes de cada call_llm()
#   - settings.py: budget_*_daily, quota settings
#   - app.py: /quota/status endpoint
#
# Patrón: lazy instantiation, auto-migration, never crash.

import sqlite3
import logging
import time
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ============================================================================
# Configuración por defecto
# ============================================================================

# Umbrales por defecto (0 = sin límite)
_DEFAULT_DAILY_BUDGET_USD = 0.0  # $0 = sin límite global
_DEFAULT_ALERT_THRESHOLD_PCT = 80.0  # Alertar al 80%
_DEFAULT_HARD_STOP = False  # False = solo advertir, True = bloquear


def _get_db_path() -> str:
    """Obtiene la ruta a usage.db desde settings."""
    try:
        from config.settings import settings
        return settings.usage_db_path
    except Exception:
        return "apa/data/usage.db"


class QuotaTracker:
    """T4: Seguimiento de cuotas de gasto por proveedor.

    Usa la misma base de datos que UsageTracker (usage.db) pero
    con tablas propias para no interferir con el tracking existente.

    Uso:
        qt = QuotaTracker()
        check = qt.check_quota("openrouter", estimated_cost=0.001)
        if not check["allowed"]:
            # Usar otro proveedor
            ...
    """

    _TABLE_VERSION = 1
    _instance_cache: Dict[str, 'QuotaTracker'] = {}
    _instance_lock = threading.Lock()

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path or _get_db_path()
        self._lock = threading.Lock()
        self._initialized = False
        self._init_db()

    @classmethod
    def get_instance(cls, db_path: Optional[str] = None) -> 'QuotaTracker':
        """Retorna un singleton por db_path."""
        key = db_path or _get_db_path()
        with cls._instance_lock:
            if key not in cls._instance_cache:
                cls._instance_cache[key] = cls(db_path)
            return cls._instance_cache[key]

    def _get_conn(self) -> sqlite3.Connection:
        """Obtiene una conexión a la base de datos."""
        conn = sqlite3.connect(self._db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        """Crea las tablas necesarias si no existen (auto-migración)."""
        if self._initialized:
            return
        try:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()

                # Tabla de configuración de cuotas por proveedor
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS quota_config (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        provider TEXT NOT NULL UNIQUE,
                        daily_budget_usd REAL NOT NULL DEFAULT 0,
                        alert_threshold_pct REAL NOT NULL DEFAULT 80,
                        is_active INTEGER NOT NULL DEFAULT 1,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                """)

                # Tabla de registro de gastos por proveedor y día
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS provider_daily_spending (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        provider TEXT NOT NULL,
                        date TEXT NOT NULL,
                        total_cost_usd REAL NOT NULL DEFAULT 0,
                        call_count INTEGER NOT NULL DEFAULT 0,
                        tokens_total INTEGER NOT NULL DEFAULT 0,
                        UNIQUE(provider, date)
                    )
                """)

                # Tabla de registro de eventos de cuota (bloqueos, alertas)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS quota_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        provider TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        daily_spent_usd REAL NOT NULL DEFAULT 0,
                        daily_budget_usd REAL NOT NULL DEFAULT 0,
                        message TEXT NOT NULL,
                        timestamp TEXT NOT NULL
                    )
                """)

                # Metadata de versión
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS quota_meta (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    )
                """)

                # Verificar/setear versión
                cursor.execute("SELECT value FROM quota_meta WHERE key='table_version'")
                row = cursor.fetchone()
                if not row:
                    cursor.execute(
                        "INSERT INTO quota_meta (key, value) VALUES (?, ?)",
                        ("table_version", str(self._TABLE_VERSION))
                    )

                conn.commit()
                self._initialized = True
                logger.debug("QuotaTracker: tablas inicializadas en %s", self._db_path)

            finally:
                conn.close()

        except Exception as e:
            logger.warning(f"QuotaTracker: error inicializando DB: {e}")
            # No crash — el sistema funciona sin cuotas

    # =========================================================================
    # Configuración de cuotas
    # =========================================================================

    def set_provider_quota(
        self,
        provider: str,
        daily_budget_usd: float,
        alert_threshold_pct: float = _DEFAULT_ALERT_THRESHOLD_PCT,
    ) -> None:
        """Establece la cuota diaria para un proveedor.

        Args:
            provider: Nombre del proveedor (ej: 'openrouter', 'anthropic')
            daily_budget_usd: Presupuesto diario en USD (0 = sin límite)
            alert_threshold_pct: Porcentaje al cual alertar (default 80%)
        """
        if not provider:
            return
        now = datetime.utcnow().isoformat()
        try:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO quota_config (provider, daily_budget_usd, alert_threshold_pct,
                                             is_active, created_at, updated_at)
                    VALUES (?, ?, ?, 1, ?, ?)
                    ON CONFLICT(provider) DO UPDATE SET
                        daily_budget_usd = excluded.daily_budget_usd,
                        alert_threshold_pct = excluded.alert_threshold_pct,
                        is_active = 1,
                        updated_at = excluded.updated_at
                """, (provider, daily_budget_usd, alert_threshold_pct, now, now))
                conn.commit()
                logger.info(f"QuotaTracker: cuota para {provider} = ${daily_budget_usd:.4f}/día")
            finally:
                conn.close()
        except Exception as e:
            logger.warning(f"QuotaTracker: error set_provider_quota({provider}): {e}")

    def remove_provider_quota(self, provider: str) -> None:
        """Elimina la cuota de un proveedor (sin límite)."""
        if not provider:
            return
        try:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM quota_config WHERE provider = ?", (provider,))
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            logger.warning(f"QuotaTracker: error remove_provider_quota({provider}): {e}")

    def get_provider_quota(self, provider: str) -> Optional[Dict[str, Any]]:
        """Retorna la configuración de cuota de un proveedor."""
        if not provider:
            return None
        try:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM quota_config WHERE provider = ? AND is_active = 1",
                    (provider,)
                )
                row = cursor.fetchone()
                if row:
                    return dict(row)
                return None
            finally:
                conn.close()
        except Exception:
            return None

    def get_all_quotas(self) -> List[Dict[str, Any]]:
        """Retorna todas las cuotas configuradas."""
        try:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM quota_config WHERE is_active = 1")
                return [dict(row) for row in cursor.fetchall()]
            finally:
                conn.close()
        except Exception:
            return []

    # =========================================================================
    # Registro de gastos
    # =========================================================================

    def record_spending(
        self,
        provider: str,
        cost_usd: float,
        tokens: int = 0,
    ) -> None:
        """Registra un gasto para el proveedor en el día actual.

        Se llama DESPUÉS de una llamada LLM exitosa para actualizar
        el contador de gastos diarios.
        """
        if not provider or cost_usd <= 0:
            return
        today = datetime.utcnow().strftime("%Y-%m-%d")
        try:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO provider_daily_spending (provider, date, total_cost_usd, call_count, tokens_total)
                    VALUES (?, ?, ?, 1, ?)
                    ON CONFLICT(provider, date) DO UPDATE SET
                        total_cost_usd = total_cost_usd + excluded.total_cost_usd,
                        call_count = call_count + 1,
                        tokens_total = tokens_total + excluded.tokens_total
                """, (provider, today, cost_usd, tokens))
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            logger.debug(f"QuotaTracker: error record_spending({provider}): {e}")

    # =========================================================================
    # Verificación de cuotas (pre-flight check)
    # =========================================================================

    def get_daily_spending(self, provider: str) -> float:
        """Retorna el gasto acumulado hoy para un proveedor."""
        if not provider:
            return 0.0
        today = datetime.utcnow().strftime("%Y-%m-%d")
        try:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT total_cost_usd FROM provider_daily_spending "
                    "WHERE provider = ? AND date = ?",
                    (provider, today)
                )
                row = cursor.fetchone()
                return row["total_cost_usd"] if row else 0.0
            finally:
                conn.close()
        except Exception:
            return 0.0

    def check_quota(
        self,
        provider: str,
        estimated_cost: float = 0.0,
    ) -> Dict[str, Any]:
        """Verifica si una llamada está dentro de la cuota del proveedor.

        Retorna dict con:
          - allowed: bool — True si la llamada puede proceder
          - blocked: bool — True si la cuota está agotada
          - warning: bool — True si está cerca del límite
          - provider: str
          - daily_spent: float — gasto acumulado hoy
          - daily_budget: float — presupuesto diario (0 = sin límite)
          - pct_used: float — porcentaje usado
          - message: str — descripción legible

        Si no hay cuota configurada para el proveedor, siempre retorna allowed=True.
        """
        result = {
            "allowed": True,
            "blocked": False,
            "warning": False,
            "provider": provider,
            "daily_spent": 0.0,
            "daily_budget": 0.0,
            "pct_used": 0.0,
            "message": "Sin límite de cuota configurado",
        }

        if not provider:
            return result

        # Obtener configuración de cuota
        quota = self.get_provider_quota(provider)
        if not quota:
            return result

        budget = quota["daily_budget_usd"]
        if budget <= 0:
            return result  # Sin límite

        threshold = quota.get("alert_threshold_pct", _DEFAULT_ALERT_THRESHOLD_PCT)

        # Obtener gasto actual
        spent = self.get_daily_spending(provider)
        pct = (spent / budget * 100) if budget > 0 else 0

        result["daily_spent"] = round(spent, 6)
        result["daily_budget"] = budget
        result["pct_used"] = round(pct, 1)

        if pct >= 100:
            result["allowed"] = False
            result["blocked"] = True
            result["message"] = f"CUOTA AGOTADA: {provider} gastó ${spent:.4f} de ${budget:.4f} (100%)"
            self._log_quota_event(provider, "blocked", spent, budget, result["message"])
        elif pct >= threshold:
            result["warning"] = True
            result["message"] = f"CUOTA ALTA: {provider} gastó ${spent:.4f} de ${budget:.4f} ({pct:.0f}%)"
            self._log_quota_event(provider, "warning", spent, budget, result["message"])
        else:
            result["message"] = f"OK: {provider} gastó ${spent:.4f} de ${budget:.4f} ({pct:.0f}%)"

        return result

    def is_provider_blocked(self, provider: str) -> bool:
        """Verificación rápida: retorna True si el proveedor agotó su cuota."""
        return self.check_quota(provider)["blocked"]

    # =========================================================================
    # Estado general
    # =========================================================================

    def get_all_spending_today(self) -> Dict[str, Dict[str, Any]]:
        """Retorna el gasto de hoy para todos los proveedores con cuota."""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        quotas = {q["provider"]: q for q in self.get_all_quotas()}

        result = {}
        for provider, quota in quotas.items():
            budget = quota["daily_budget_usd"]
            threshold = quota.get("alert_threshold_pct", _DEFAULT_ALERT_THRESHOLD_PCT)

            spent = self.get_daily_spending(provider)
            pct = (spent / budget * 100) if budget > 0 else 0

            result[provider] = {
                "daily_budget_usd": budget,
                "daily_spent_usd": round(spent, 6),
                "pct_used": round(pct, 1),
                "call_count": self._get_call_count(provider, today),
                "status": "blocked" if pct >= 100 else (
                    "warning" if pct >= threshold else "ok"
                ),
            }

        return result

    def get_quota_summary(self) -> Dict[str, Any]:
        """Resumen general para el dashboard /quota/status."""
        spending = self.get_all_spending_today()

        total_budget = sum(s["daily_budget_usd"] for s in spending.values())
        total_spent = sum(s["daily_spent_usd"] for s in spending.values())
        total_pct = (total_spent / total_budget * 100) if total_budget > 0 else 0

        blocked = [p for p, s in spending.items() if s["status"] == "blocked"]
        warning = [p for p, s in spending.items() if s["status"] == "warning"]

        return {
            "total_daily_budget_usd": round(total_budget, 4),
            "total_daily_spent_usd": round(total_spent, 6),
            "total_pct_used": round(total_pct, 1),
            "providers_with_quota": len(spending),
            "blocked_providers": blocked,
            "warning_providers": warning,
            "overall_status": "blocked" if blocked else (
                "warning" if warning else "healthy"
            ),
            "providers": spending,
        }

    def _get_call_count(self, provider: str, date: str) -> int:
        """Retorna el número de llamadas hoy para un proveedor."""
        try:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT call_count FROM provider_daily_spending WHERE provider = ? AND date = ?",
                    (provider, date)
                )
                row = cursor.fetchone()
                return row["call_count"] if row else 0
            finally:
                conn.close()
        except Exception:
            return 0

    def _log_quota_event(self, provider: str, event_type: str,
                         spent: float, budget: float, message: str) -> None:
        """Registra un evento de cuota (bloqueo o alerta)."""
        now = datetime.utcnow().isoformat()
        try:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO quota_events (provider, event_type, daily_spent_usd,
                                              daily_budget_usd, message, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (provider, event_type, round(spent, 6), budget, message, now))
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            logger.debug(f"QuotaTracker: error logging event: {e}")

    def get_recent_events(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Retorna los eventos de cuota más recientes."""
        try:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM quota_events ORDER BY id DESC LIMIT ?", (limit,)
                )
                return [dict(row) for row in cursor.fetchall()]
            finally:
                conn.close()
        except Exception:
            return []

    def get_spending_history(self, days: int = 7) -> Dict[str, List[Dict[str, Any]]]:
        """Retorna el historial de gastos por proveedor en los últimos N días."""
        since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        result: Dict[str, List[Dict[str, Any]]] = {}

        try:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT provider, date, total_cost_usd, call_count, tokens_total
                    FROM provider_daily_spending
                    WHERE date >= ?
                    ORDER BY date DESC, provider ASC
                """, (since,))

                for row in cursor.fetchall():
                    d = dict(row)
                    prov = d["provider"]
                    if prov not in result:
                        result[prov] = []
                    result[prov].append(d)

            finally:
                conn.close()
        except Exception:
            pass

        return result


# ============================================================================
# VALIDACIÓN — if __name__ == "__main__"
# ============================================================================
if __name__ == "__main__":
    import sys
    import os
    import tempfile
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

    _record = {"pass": 0, "fail": 0, "tests": []}

    def _run(name: str, fn):
        try:
            fn()
            _record["pass"] += 1
            _record["tests"].append(f"  PASS: {name}")
        except Exception as e:
            _record["fail"] += 1
            _record["tests"].append(f"  FAIL: {name} — {e}")

    print("=" * 60)
    print("QuotaTracker v1.0 — Validación integrada")
    print("=" * 60)

    # T1: Crear instancia (usa DB temporal cross-platform)
    _db_tmp = os.path.join(tempfile.gettempdir(), "test_quota_tracker.db")
    qt = QuotaTracker(db_path=_db_tmp)

    def t1_init():
        assert qt._initialized, "DB no inicializada"
        assert qt._db_path == _db_tmp
    _run("T1: Inicialización DB", t1_init)

    # T2: Configurar cuota
    def t2_set_quota():
        qt.set_provider_quota("openrouter", 1.0, 80.0)
        q = qt.get_provider_quota("openrouter")
        assert q is not None, "Cuota no encontrada"
        assert q["daily_budget_usd"] == 1.0
        assert q["alert_threshold_pct"] == 80.0
    _run("T2: set_provider_quota + get_provider_quota", t2_set_quota)

    # T3: check_quota sin gasto (allowed)
    def t3_check_ok():
        r = qt.check_quota("openrouter")
        assert r["allowed"] is True
        assert r["blocked"] is False
        assert r["pct_used"] == 0.0
    _run("T3: check_quota sin gasto → allowed", t3_check_ok)

    # T4: Registrar gasto
    def t4_record():
        qt.record_spending("openrouter", 0.5, 1000)
        spent = qt.get_daily_spending("openrouter")
        assert spent == 0.5, f"Esperado 0.5, got {spent}"
    _run("T4: record_spending + get_daily_spending", t4_record)

    # T5: check_quota con gasto parcial (warning al 80%)
    def t5_warning():
        qt.record_spending("openrouter", 0.35, 700)  # Total: 0.85
        r = qt.check_quota("openrouter")
        assert r["allowed"] is True
        assert r["warning"] is True, f"Esperado warning, got status={r.get('pct_used')}%"
    _run("T5: check_quota con gasto 85% → warning", t5_warning)

    # T6: Bloqueo por cuota agotada
    def t6_blocked():
        qt.set_provider_quota("test_blocked", 0.01, 80.0)
        qt.record_spending("test_blocked", 0.02, 100)
        r = qt.check_quota("test_blocked")
        assert r["allowed"] is False
        assert r["blocked"] is True
    _run("T6: check_quota agotada → blocked", t6_blocked)

    # T7: is_provider_blocked
    def t7_blocked_fast():
        assert qt.is_provider_blocked("test_blocked") is True
        assert qt.is_provider_blocked("openrouter") is False
    _run("T7: is_provider_blocked", t7_blocked_fast)

    # T8: get_all_quotas
    def t8_all_quotas():
        all_q = qt.get_all_quotas()
        names = [q["provider"] for q in all_q]
        assert "openrouter" in names
        assert "test_blocked" in names
    _run("T8: get_all_quotas", t8_all_quotas)

    # T9: get_quota_summary
    def t9_summary():
        s = qt.get_quota_summary()
        assert "total_daily_budget_usd" in s
        assert "providers" in s
        assert s["overall_status"] in ("healthy", "warning", "blocked")
    _run("T9: get_quota_summary", t9_summary)

    # T10: get_spending_history
    def t10_history():
        h = qt.get_spending_history(days=7)
        assert isinstance(h, dict)
        assert "openrouter" in h
    _run("T10: get_spending_history", t10_history)

    # T11: remove_provider_quota
    def t11_remove():
        qt.remove_provider_quota("test_blocked")
        assert qt.get_provider_quota("test_blocked") is None
    _run("T11: remove_provider_quota", t11_remove)

    # T12: get_recent_events
    def t12_events():
        evts = qt.get_recent_events(limit=5)
        assert isinstance(evts, list)
    _run("T12: get_recent_events", t12_events)

    # T13: Singleton — get_instance debe retornar la misma instancia
    def t13_singleton():
        QuotaTracker._instance_cache.clear()  # Limpiar cache para test limpio
        qt_new = QuotaTracker.get_instance(db_path=_db_tmp)
        qt_same = QuotaTracker.get_instance(db_path=_db_tmp)
        assert qt_new is qt_same, "Singleton no funciona"
    _run("T13: get_instance singleton", t13_singleton)

    # T14: Proveedor sin cuota → siempre allowed
    def t14_no_quota():
        r = qt.check_quota("proveedor_sin_cuota")
        assert r["allowed"] is True
        assert r["message"] == "Sin límite de cuota configurado"
    _run("T14: Proveedor sin cuota → allowed", t14_no_quota)

    # Cleanup
    try:
        if os.path.exists(_db_tmp):
            os.remove(_db_tmp)
    except Exception:
        pass

    print()
    for t in _record["tests"]:
        print(t)
    print(f"\n{'=' * 60}")
    print(f"RESULTADO: {_record['pass']} PASS / {_record['fail']} FAIL")
    print(f"{'=' * 60}")
    sys.exit(0 if _record["fail"] == 0 else 1)
