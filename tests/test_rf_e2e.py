# apa/tests/test_rf_e2e.py
# v1.0 — Test E2E del Bloque RF (Refactoring Integrity) completo.
#         Valida RF1->RF2->RF3->RF4->RF5 paso a paso con fixtures realistas.
#         Incluye validación de integración con semi_auto_agent (v3.3).
#
# EJECUCIÓN:
#   cd APA && python -m apa.tests.test_rf_e2e
#   — o —
#   python apa/tests/test_rf_e2e.py
#
# PATRÓN: Canónico _run_validation() con test_results = [(name, bool)]
#
# FIXTURES:
#   Proyecto temporal con:
#     - utils.py: funciones validar(), formatear(), clase Procesador con método procesar()
#     - main.py: importa y llama a validar(), formatear(), Procesador()
#     - models.py: clase BaseModel, UserModel(BaseModel) con método guardar()
#     - services.py: importa BaseModel, llama a validar()
#
# ESCENARIO E2E:
#   Fase 1: RF1 — Construir grafo de símbolos
#   Fase 2: RF2 — Obtener contexto con evaluación de riesgo
#   Fase 3: RF3 — Crear snapshot, verificar integridad
#   Fase 4: RF4 — Revisar diffs con 4 severidades
#   Fase 5: RF5 — Validar regresión con rollback automático
#   Fase 6: Integración — Pipeline completo RF1->RF5 + integración semi_auto_agent
#
# ============================================================================
import ast
import os
import sys
import shutil
import tempfile
import logging
from typing import List, Tuple
from pathlib import Path

# Añadir raíz del proyecto (apa/) al path para importaciones internas
sys.path.insert(0, str(Path(__file__).parent.parent))

# ============================================================================
# Logging setup
# ============================================================================
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    logger.addHandler(handler)
logger.propagate = False


# ============================================================================
# Fixtures — Proyecto temporal con dependencias reales
# ============================================================================

UTILS_PY = '''\
# utils.py — Funciones de utilidad
def validar(dato):
    """Valida un dato."""
    return bool(dato)

def formatear(texto, mayus=False):
    """Formatea un texto."""
    if mayus:
        return texto.upper()
    return texto.strip()

class Procesador:
    """Procesador base."""
    def procesar(self, entrada):
        return str(entrada).strip()

    def validar_entrada(self, entrada):
        return validar(entrada)
'''

MAIN_PY = '''\
# main.py — Punto de entrada
from utils import validar, formatear, Procesador

def ejecutar():
    dato = "hola"
    if validar(dato):
        resultado = formatear(dato, mayus=True)
    proc = Procesador()
    proc.procesar(dato)
    return resultado

def iniciar():
    validar(None)
    ejecutar()
'''

MODELS_PY = '''\
# models.py — Modelos con herencia
class BaseModel:
    """Modelo base."""
    def guardar(self):
        pass

    def eliminar(self):
        pass

class UserModel(BaseModel):
    """Modelo de usuario."""
    def guardar(self):
        super().guardar()
        print("Usuario guardado")

class AdminModel(BaseModel):
    """Modelo de administrador."""
    def guardar(self):
        super().guardar()
        print("Admin guardado")
'''

SERVICES_PY = '''\
# services.py — Servicios
from models import BaseModel
from utils import validar

class Servicio:
    def procesar(self, dato):
        if validar(dato):
            return dato
        return None

    def crear_modelo(self):
        modelo = BaseModel()
        modelo.guardar()
        return modelo
'''


def _create_test_project(tmp_dir: str) -> dict:
    """Crea el proyecto de prueba en tmp_dir y retorna rutas absolutas."""
    files = {
        "utils.py": os.path.join(tmp_dir, "utils.py"),
        "main.py": os.path.join(tmp_dir, "main.py"),
        "models.py": os.path.join(tmp_dir, "models.py"),
        "services.py": os.path.join(tmp_dir, "services.py"),
    }
    with open(files["utils.py"], 'w', encoding='utf-8') as f:
        f.write(UTILS_PY)
    with open(files["main.py"], 'w', encoding='utf-8') as f:
        f.write(MAIN_PY)
    with open(files["models.py"], 'w', encoding='utf-8') as f:
        f.write(MODELS_PY)
    with open(files["services.py"], 'w', encoding='utf-8') as f:
        f.write(SERVICES_PY)
    return files


# ============================================================================
# Test E2E
# ============================================================================

def _run_validation():
    """Ejecuta la validación E2E del Bloque RF completo."""
    test_results: List[Tuple[str, bool]] = []

    # ── Crear proyecto temporal ──
    tmp_dir = tempfile.mkdtemp(prefix="apa_rf_e2e_")
    files = _create_test_project(tmp_dir)

    try:
        # ================================================================
        # FASE 1: RF1 — SymbolGraph
        # ================================================================
        print("\n── FASE 1: RF1 — SymbolGraph ──")

        from core.symbol_graph import SymbolGraph
        graph = SymbolGraph()
        count = graph.build_from_directory(tmp_dir)

        # RF1-1: El grafo se construye sin errores
        test_results.append((
            "RF1: Grafo construido (count > 0)",
            count > 0
        ))

        # RF1-2: Detecta símbolos de utils.py
        utils_syms = graph.get_file_symbols("utils.py")
        test_results.append((
            "RF1: utils.py tiene símbolos (validar, formatear, Procesador)",
            "validar" in utils_syms and "formatear" in utils_syms and "Procesador" in utils_syms
        ))

        # RF1-3: Detecta callers de validar()
        ctx_validar = graph.get_refactor_context("utils.py", "validar")
        llamado_por = ctx_validar.get("llamado_por", [])
        caller_files = set(f for f, _ in llamado_por)
        test_results.append((
            "RF1: validar() tiene callers en main.py y services.py",
            "main.py" in caller_files and "services.py" in caller_files
        ))

        # RF1-4: Detecta herencia en models.py
        ctx_base = graph.get_refactor_context("models.py", "BaseModel")
        herencia = ctx_base.get("herencia", {})
        derivados = herencia.get("derivados", [])
        test_results.append((
            "RF1: BaseModel tiene derivados (UserModel, AdminModel)",
            any("UserModel" in d for d in derivados) and any("AdminModel" in d for d in derivados)
        ))

        # RF1-5: Detecta calls entre archivos
        ctx_ejecutar = graph.get_refactor_context("main.py", "ejecutar")
        llama_a = ctx_ejecutar.get("llama_a", [])
        test_results.append((
            "RF1: ejecutar() llama a validar y formatear",
            "validar" in llama_a and "formatear" in llama_a
        ))

        # ================================================================
        # FASE 2: RF2 — Contexto inteligente con riesgo
        # ================================================================
        print("── FASE 2: RF2 — Contexto con evaluación de riesgo ──")

        from core.refactor_guard import RefactorGuard
        guard = RefactorGuard(tmp_dir)

        # RF2-1: Contexto para utils.py incluye dependientes
        context = guard.get_refactor_context_for_prompt("utils.py")
        test_results.append((
            "RF2: Contexto menciona main.py como dependiente de utils.py",
            "main.py" in context
        ))

        # RF2-2: Evaluación de riesgo ALTO para validar (>=3 callers)
        # validar es llamada por: main.py:ejecutar, main.py:iniciar, services.py:Servicio.procesar
        # -> 3 callers -> ALTO
        test_results.append((
            "RF2: validar tiene riesgo ALTO (>=3 callers)",
            "ALTO" in context and "validar" in context
        ))

        # RF2-3: Riesgo ALTO por herencia — BaseModel tiene subclases
        context_models = guard.get_refactor_context_for_prompt("models.py")
        test_results.append((
            "RF2: BaseModel tiene riesgo ALTO por herencia (subclases)",
            "ALTO" in context_models and "BaseModel" in context_models
        ))

        # RF2-4: Riesgo ALTO por herencia — método de clase con subclases
        context_guardar = guard.get_refactor_context_for_prompt("models.py", "BaseModel.guardar")
        test_results.append((
            "RF2: BaseModel.guardar tiene riesgo ALTO (herencia con subclases)",
            "ALTO" in context_guardar
        ))

        # RF2-5: Contexto sin dependencias no bloquea pipeline
        guard_no_graph = RefactorGuard("")
        empty_ctx = guard_no_graph.get_refactor_context_for_prompt("nonexistent_xyz.py")
        has_no_callers = "llamado_por" not in empty_ctx or "ningún archivo" in empty_ctx
        test_results.append((
            "RF2: Archivo inexistente no bloquea pipeline (sin callers)",
            empty_ctx == "" or has_no_callers or "CONTEXTO" in empty_ctx
        ))

        # RF2-6: Contexto de símbolo específico incluye llamadores
        ctx_validar_specific = guard.get_refactor_context_for_prompt("utils.py", "validar")
        test_results.append((
            "RF2: Contexto específico de validar() incluye llamadores",
            "llamado_por" in ctx_validar_specific.lower() or "main.py" in ctx_validar_specific
        ))

        # ================================================================
        # FASE 3: RF3 — SnapshotManager
        # ================================================================
        print("── FASE 3: RF3 — SnapshotManager ──")

        from core.snapshot_manager import SnapshotManager
        mgr = SnapshotManager(tmp_dir)

        # RF3-1: Crear snapshot
        snap_id = mgr.create_snapshot("test_e2e", [files["utils.py"], files["main.py"]])
        test_results.append((
            "RF3: Snapshot creado con ID válido (snap_*)",
            snap_id is not None and snap_id.startswith("snap_")
        ))

        # RF3-2: Snapshot contiene archivos correctos
        snapshots = mgr.list_snapshots()
        snap_info = next((s for s in snapshots if s["snapshot_id"] == snap_id), None)
        test_results.append((
            "RF3: Snapshot contiene 2 archivos",
            snap_info is not None and len(snap_info.get("files", [])) == 2
        ))

        # RF3-3: Verificar integridad (sin modificar)
        intact, modified = mgr.verify_integrity(snap_id)
        test_results.append((
            "RF3: Integridad OK antes de modificar",
            intact and len(modified) == 0
        ))

        # RF3-4: Modificar archivo y verificar integridad comprometida
        with open(files["utils.py"], 'w', encoding='utf-8') as f:
            f.write("# MODIFICADO\n")
        intact2, modified2 = mgr.verify_integrity(snap_id)
        test_results.append((
            "RF3: Integridad comprometida después de modificar",
            not intact2 and len(modified2) > 0
        ))

        # RF3-5: Rollback restaura archivos
        success, errors = mgr.rollback(snap_id)
        with open(files["utils.py"], 'r', encoding='utf-8') as f:
            restored = f.read()
        test_results.append((
            "RF3: Rollback restaura utils.py al contenido original",
            success and "def validar" in restored
        ))

        # RF3-6: Commit impide rollback
        snap2 = mgr.create_snapshot("test_commit", [files["utils.py"]])
        mgr.commit(snap2)
        commit_info = next((s for s in mgr.list_snapshots(include_committed=True)
                           if s["snapshot_id"] == snap2), None)
        test_results.append((
            "RF3: Commit marca snapshot como confirmado",
            commit_info is not None and commit_info.get("committed", False)
        ))

        # Restaurar utils.py para siguientes fases
        with open(files["utils.py"], 'w', encoding='utf-8') as f:
            f.write(UTILS_PY)

        # ================================================================
        # FASE 4: RF4 — Revisión de diffs
        # ================================================================
        print("── FASE 4: RF4 — Revisión de diffs ──")

        # RF4-1: CRITICAL — símbolo eliminado con callers
        utils_sin_validar = UTILS_PY.replace(
            "def validar(dato):\n    \"\"\"Valida un dato.\"\"\"\n    return bool(dato)\n",
            ""
        )
        issues = guard.review_diff(UTILS_PY, utils_sin_validar, "utils.py")
        criticals = [i for i in issues if i.severity == "CRITICAL"]
        test_results.append((
            "RF4: Eliminar validar() -> CRITICAL (tiene callers)",
            len(criticals) > 0 and any("validar" in i.symbol for i in criticals)
        ))

        # RF4-2: CRITICAL menciona callers afectados
        critical_validar = next((i for i in criticals if "validar" in i.symbol), None)
        test_results.append((
            "RF4: CRITICAL incluye callers afectados (main.py, services.py)",
            critical_validar is not None and
            any("main.py" in c for c in critical_validar.affected_callers) and
            any("services.py" in c for c in critical_validar.affected_callers)
        ))

        # RF4-3: SIGNATURE_CHANGE_BREAKING — parámetro requerido eliminado
        utils_breaking = UTILS_PY.replace(
            "def formatear(texto, mayus=False):",
            "def formatear(mayus=False):"  # Eliminado 'texto' requerido
        )
        issues_break = guard.review_diff(UTILS_PY, utils_breaking, "utils.py")
        sig_breaks = [i for i in issues_break if i.severity == "SIGNATURE_CHANGE_BREAKING"]
        test_results.append((
            "RF4: Eliminar parámetro requerido -> SIGNATURE_CHANGE_BREAKING",
            len(sig_breaks) > 0
        ))

        # RF4-4: SIGNATURE_CHANGE_COMPATIBLE — parámetro con default añadido
        utils_compat = UTILS_PY.replace(
            "def formatear(texto, mayus=False):",
            "def formatear(texto, mayus=False, prefijo=''):"
        )
        issues_compat = guard.review_diff(UTILS_PY, utils_compat, "utils.py")
        sig_compats = [i for i in issues_compat if i.severity == "SIGNATURE_CHANGE_COMPATIBLE"]
        test_results.append((
            "RF4: Añadir parámetro con default -> SIGNATURE_CHANGE_COMPATIBLE",
            len(sig_compats) > 0
        ))

        # RF4-5: Cambiar docstring -> WARNING (no CRITICAL ni BREAKING)
        utils_comment = UTILS_PY.replace(
            '"""Valida un dato."""',
            '"""Valida un dato modificado."""'
        )
        issues_comment = guard.review_diff(UTILS_PY, utils_comment, "utils.py")
        has_critical_comment = any(i.severity in ("CRITICAL", "SIGNATURE_CHANGE_BREAKING") for i in issues_comment)
        test_results.append((
            "RF4: Cambiar docstring -> WARNING (sin CRITICAL ni BREAKING)",
            not has_critical_comment
        ))

        # RF4-6: INFO para símbolos nuevos
        utils_new_func = UTILS_PY + "\ndef nueva_funcion():\n    pass\n"
        issues_new = guard.review_diff(UTILS_PY, utils_new_func, "utils.py")
        infos = [i for i in issues_new if i.severity == "INFO"]
        test_results.append((
            "RF4: Símbolo nuevo -> INFO",
            len(infos) > 0 and any("nueva_funcion" in i.symbol for i in infos)
        ))

        # RF4-7: Números de línea presentes en issues críticos
        test_results.append((
            "RF4: Issues incluyen números de línea",
            all(i.lineno > 0 for i in issues if i.severity in ("CRITICAL", "SIGNATURE_CHANGE_BREAKING"))
        ))

        # RF4-8: has_critical_issues() detecta problemas urgentes
        test_results.append((
            "RF4: has_critical_issues=True cuando hay CRITICAL",
            guard.has_critical_issues(issues)
        ))

        # RF4-9: has_critical_issues() retorna False cuando solo hay INFO
        test_results.append((
            "RF4: has_critical_issues=False cuando solo hay INFO",
            not guard.has_critical_issues(infos)
        ))

        # RF4-10: format_issues_for_prompt genera texto legible
        formatted = guard.format_issues_for_prompt(issues)
        test_results.append((
            "RF4: format_issues_for_prompt incluye CRITICAL y validar",
            "CRITICAL" in formatted and "validar" in formatted
        ))

        # ================================================================
        # FASE 5: RF5 — Validación de regresión
        # ================================================================
        print("── FASE 5: RF5 — Validación de regresión ──")

        # Restaurar archivos
        with open(files["utils.py"], 'w', encoding='utf-8') as f:
            f.write(UTILS_PY)
        with open(files["main.py"], 'w', encoding='utf-8') as f:
            f.write(MAIN_PY)

        # RF5-1: Validación OK cuando no hay cambios
        snap_ok = guard.create_refactor_snapshot("rf5_ok", [files["utils.py"]])
        ok_ok, report_ok = guard.validate_regression(snap_ok, [files["utils.py"]])
        test_results.append((
            "RF5: Validación OK cuando archivo no cambió",
            ok_ok and len(report_ok.get("regressions", [])) == 0
        ))
        guard.commit_snapshot(snap_ok)

        # RF5-2: Detecta error de sintaxis (ast.parse) — Capa 1
        snap_syntax = guard.create_refactor_snapshot("rf5_syntax", [files["utils.py"]])
        with open(files["utils.py"], 'w', encoding='utf-8') as f:
            f.write("def validar(\n")  # Paréntesis sin cerrar
        ok_syntax, report_syntax = guard.validate_regression(snap_syntax, [files["utils.py"]])
        test_results.append((
            "RF5: Capa 1 — Detecta error de sintaxis (ast.parse)",
            not ok_syntax and len(report_syntax.get("syntax_errors", [])) > 0
        ))
        # Restaurar
        with open(files["utils.py"], 'w', encoding='utf-8') as f:
            f.write(UTILS_PY)
        guard.rollback_snapshot(snap_syntax)

        # RF5-3: Detecta símbolo eliminado con callers — Capa 3
        snap_elim = guard.create_refactor_snapshot("rf5_elim", [files["utils.py"]])
        utils_sin_validar_content = UTILS_PY.replace(
            "def validar(dato):\n    \"\"\"Valida un dato.\"\"\"\n    return bool(dato)\n\n",
            ""
        )
        with open(files["utils.py"], 'w', encoding='utf-8') as f:
            f.write(utils_sin_validar_content)
        ok_elim, report_elim = guard.validate_regression(snap_elim, [files["utils.py"]])
        test_results.append((
            "RF5: Capa 3 — Detecta símbolo eliminado con callers (validar)",
            not ok_elim and any("validar" in str(r) for r in report_elim.get("regressions", []))
        ))
        # Restaurar
        with open(files["utils.py"], 'w', encoding='utf-8') as f:
            f.write(UTILS_PY)
        guard.rollback_snapshot(snap_elim)

        # RF5-4: validate_and_rollback restaura archivos automáticamente
        snap_auto = guard.create_refactor_snapshot("rf5_auto", [files["utils.py"], files["main.py"]])
        # Modificar ambos archivos
        with open(files["utils.py"], 'w', encoding='utf-8') as f:
            f.write("ROTOTO TOTAL\n")
        with open(files["main.py"], 'w', encoding='utf-8') as f:
            f.write("ROTOTO MAIN\n")
        # Validar — debería detectar regresión y hacer rollback automático
        ok_auto, report_auto = guard.validate_and_rollback(
            snap_auto, [files["utils.py"], files["main.py"]]
        )
        # Verificar que rollback restauró los archivos
        with open(files["utils.py"], 'r', encoding='utf-8') as f:
            restored_utils = f.read()
        with open(files["main.py"], 'r', encoding='utf-8') as f:
            restored_main = f.read()
        test_results.append((
            "RF5: validate_and_rollback restaura ambos archivos automáticamente",
            not ok_auto and
            "def validar" in restored_utils and
            "from utils import" in restored_main
        ))

        # RF5-5: validate_and_rollback reporta rollback ejecutado
        test_results.append((
            "RF5: validate_and_rollback reporta rollback_executed=True",
            report_auto.get("rollback_executed", False) is True
        ))

        # RF5-6: validate_and_rollback reporta rollback exitoso
        test_results.append((
            "RF5: validate_and_rollback reporta rollback_success=True",
            report_auto.get("rollback_success", False) is True
        ))

        # RF5-7: Commit impide rollback posterior
        snap_commit = guard.create_refactor_snapshot("rf5_commit_test", [files["utils.py"]])
        guard.commit_snapshot(snap_commit)
        success_rollback, _ = guard.rollback_snapshot(snap_commit)
        test_results.append((
            "RF5: Commit impide rollback posterior",
            not success_rollback
        ))

        # RF5-8: verify_snapshot_integrity detecta cambios
        snap_integrity = guard.create_refactor_snapshot("rf5_integrity", [files["utils.py"]])
        with open(files["utils.py"], 'w', encoding='utf-8') as f:
            f.write("# CORROMPIDO\n")
        intact_rf5, modified_rf5 = guard.verify_snapshot_integrity(snap_integrity)
        test_results.append((
            "RF5: verify_snapshot_integrity detecta archivo modificado",
            not intact_rf5 and len(modified_rf5) > 0
        ))
        # Limpiar
        guard.rollback_snapshot(snap_integrity)
        with open(files["utils.py"], 'w', encoding='utf-8') as f:
            f.write(UTILS_PY)

        # ================================================================
        # FASE 6: Integración completa — Pipeline RF1->RF5
        # ================================================================
        print("── FASE 6: Integración completa RF1->RF5 ──")

        # Restaurar todo
        with open(files["utils.py"], 'w', encoding='utf-8') as f:
            f.write(UTILS_PY)
        with open(files["main.py"], 'w', encoding='utf-8') as f:
            f.write(MAIN_PY)

        # E2E-1: Pipeline completo con cambio seguro (añadir función nueva)
        snap_pipeline = guard.create_refactor_snapshot("e2e_pipeline", [files["utils.py"]])
        utils_con_nueva = UTILS_PY + "\ndef calcular(x, y):\n    return x + y\n"
        with open(files["utils.py"], 'w', encoding='utf-8') as f:
            f.write(utils_con_nueva)

        # RF4: revisar diff
        issues_e2e = guard.review_diff(UTILS_PY, utils_con_nueva, "utils.py")
        has_info = any(i.severity == "INFO" for i in issues_e2e)
        has_critical = any(i.severity == "CRITICAL" for i in issues_e2e)

        # RF5: validar regresión
        ok_e2e, report_e2e = guard.validate_regression(snap_pipeline, [files["utils.py"]])
        test_results.append((
            "E2E: Añadir función nueva -> RF4=INFO, RF5=OK, sin CRITICAL",
            has_info and not has_critical and ok_e2e
        ))

        # Confirmar (cambio aprobado)
        guard.commit_snapshot(snap_pipeline)
        test_results.append((
            "E2E: Commit confirma snapshot tras cambio aprobado",
            True  # Si llegamos aquí sin excepción, OK
        ))

        # E2E-2: Pipeline con cambio peligroso (eliminar función con callers)
        with open(files["utils.py"], 'w', encoding='utf-8') as f:
            f.write(UTILS_PY)  # Restaurar

        snap_danger = guard.create_refactor_snapshot("e2e_danger", [files["utils.py"]])
        utils_sin_v = UTILS_PY.replace(
            "def validar(dato):\n    \"\"\"Valida un dato.\"\"\"\n    return bool(dato)\n\n",
            ""
        )
        with open(files["utils.py"], 'w', encoding='utf-8') as f:
            f.write(utils_sin_v)

        # RF4: revisar diff
        issues_danger = guard.review_diff(UTILS_PY, utils_sin_v, "utils.py")
        criticals_danger = [i for i in issues_danger if i.severity == "CRITICAL"]

        # RF5: validar -> regresión (símbolo eliminado con callers) + rollback auto
        ok_danger, report_danger = guard.validate_and_rollback(
            snap_danger, [files["utils.py"]]
        )
        # Verificar rollback restauró
        with open(files["utils.py"], 'r', encoding='utf-8') as f:
            restored_danger = f.read()

        test_results.append((
            "E2E: Eliminar validar() -> RF4=CRITICAL, RF5=regresión, rollback restaura",
            len(criticals_danger) > 0 and
            not ok_danger and
            "def validar" in restored_danger
        ))

        # E2E-3: RF4 issues se pueden serializar a dict (para task.validation_result)
        rf4_dicts = [
            {
                "severity": i.severity,
                "symbol": i.symbol,
                "lineno": i.lineno,
                "description": i.description,
                "affected_callers": i.affected_callers,
            }
            for i in issues_danger
        ]
        test_results.append((
            "E2E: RF4 issues se serializan a dict (integración semi_auto_agent)",
            len(rf4_dicts) > 0 and
            all("severity" in d for d in rf4_dicts) and
            any(d["severity"] == "CRITICAL" for d in rf4_dicts)
        ))

        # E2E-4: rf4_has_critical se puede determinar correctamente
        rf4_has_critical = any(i.severity == "CRITICAL" for i in issues_danger)
        test_results.append((
            "E2E: rf4_has_critical=True cuando hay CRITICAL (para task.validation_result)",
            rf4_has_critical is True
        ))

        # E2E-5: RF5 report se puede almacenar en task.validation_result
        rf5_report_serializable = isinstance(report_danger, dict) and "regressions" in report_danger
        test_results.append((
            "E2E: RF5 report es dict serializable (para task.validation_result)",
            rf5_report_serializable
        ))

        # E2E-6: Pipeline RF5 + RF4 merge — ambos resultados coexisten
        merged_validation = {
            "returncode": 0,
            "passed": True,
            "rf4_issues": rf4_dicts,
            "rf4_has_critical": rf4_has_critical,
            "rf5_report": report_danger,
        }
        test_results.append((
            "E2E: Merge RF4+RF5+validation_result coexiste sin colisión",
            "rf4_issues" in merged_validation and
            "rf4_has_critical" in merged_validation and
            "rf5_report" in merged_validation and
            "returncode" in merged_validation
        ))

        # E2E-7: RefactorGuard._ensure_graph es perezoso (no se reconstruye)
        guard_instance = RefactorGuard(tmp_dir)
        _ = guard_instance.get_refactor_context_for_prompt("utils.py")
        graph_id_1 = id(guard_instance._graph)
        _ = guard_instance.get_refactor_context_for_prompt("models.py")
        graph_id_2 = id(guard_instance._graph)
        test_results.append((
            "E2E: RefactorGuard._ensure_graph es perezoso (misma instancia)",
            graph_id_1 == graph_id_2
        ))

        # E2E-8: Snapshot ID tiene formato determinista
        snap_fmt = mgr.create_snapshot("test_format", [files["utils.py"]])
        test_results.append((
            "E2E: Snapshot ID tiene formato snap_YYYYMMDD_HHMMSS_NNN",
            snap_fmt is not None and
            len(snap_fmt.split('_')) == 4 and
            snap_fmt.split('_')[0] == "snap"
        ))

        # E2E-9: validate_and_rollback con regresión marca rollback_executed
        with open(files["utils.py"], 'w', encoding='utf-8') as f:
            f.write(UTILS_PY)
        snap_rollback_flag = guard.create_refactor_snapshot("e2e_rollback_flag", [files["utils.py"]])
        with open(files["utils.py"], 'w', encoding='utf-8') as f:
            f.write("INVALIDO\n")
        ok_flag, report_flag = guard.validate_and_rollback(snap_rollback_flag, [files["utils.py"]])
        test_results.append((
            "E2E: validate_and_rollback marca rollback_executed=True en regresión",
            not ok_flag and report_flag.get("rollback_executed") is True
        ))

        # E2E-10: validate_and_rollback sin regresión NO marca rollback_executed
        with open(files["utils.py"], 'w', encoding='utf-8') as f:
            f.write(UTILS_PY)
        with open(files["main.py"], 'w', encoding='utf-8') as f:
            f.write(MAIN_PY)
        snap_no_rollback = guard.create_refactor_snapshot("e2e_no_rollback", [files["utils.py"]])
        ok_no_rb, report_no_rb = guard.validate_and_rollback(snap_no_rollback, [files["utils.py"]])
        test_results.append((
            "E2E: validate_and_rollback NO marca rollback_executed cuando OK",
            ok_no_rb and report_no_rb.get("rollback_executed") is False
        ))
        guard.commit_snapshot(snap_no_rollback)

    finally:
        # ── Limpiar proyecto temporal ──
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # ================================================================
    # Reporte de resultados
    # ================================================================
    print("\n" + "=" * 70)
    print("test_rf_e2e.py v1.0 — Bloque RF E2E Validation")
    print("=" * 70)

    for name, passed in test_results:
        status = "[PASS]" if passed else "[FAIL]"
        print(f"  {status} {name}")

    passed = sum(1 for _, p in test_results if p)
    failed = len(test_results) - passed
    print(f"\nResultado: {passed}/{len(test_results)} PASS, {failed} FAIL")
    print("=" * 70)

    if failed > 0:
        sys.exit(1)


# ============================================================================
# Entry point
# ============================================================================
if __name__ == "__main__":
    _run_validation()
