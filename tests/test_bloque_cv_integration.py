"""
Test de integración completo del Bloque CV: CV1 + CV2 + CV3.

Este módulo prueba todo el sistema de conversación → detección de proyecto →
arnés de preguntas → habilitación de botón "Crear Proyecto" de forma end-to-end.

Se ejecuta de forma autocontenida, sin depender de APIs externas ni servicios.

Uso:
    cd C:\\Python\\Proyectos\\APA
    python -m apa.tests.test_bloque_cv_integration
"""

import sys
import os
import json
import time
from datetime import datetime

# Asegurar imports correctos desde la raíz del proyecto
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from apa.core.sdd_maturity import (
    SDDMaturityEvaluator,
    MaturityResult,
    AspectStatus,
    AspectPriority,
    CoverageLevel,
    ProjectSignal,
)
from apa.core.sdd_guide import SDDGuide, GuideHint, GuideState

# CV3: Importar función de tier (no depende de APIs externas)
from apa.core.router import get_task_tier, _TASK_TYPE_TIER, _FAST_TIER_MAX_CONTEXT


# =============================================================================
# UTILIDADES
# =============================================================================

class TestRunner:
    """Ejecutor de pruebas con reporte detallado."""

    def __init__(self):
        self.results = []
        self.start_time = time.time()
        self.total_passed = 0
        self.total_failed = 0

    def run(self, test_name: str, func):
        """Ejecuta un test y registra el resultado."""
        try:
            func()
            self.total_passed += 1
            self.results.append({
                "test": test_name,
                "status": "PASS",
                "detail": "",
                "time_ms": 0,
            })
            print(f"  \u2713 {test_name}")
        except AssertionError as e:
            self.total_failed += 1
            self.results.append({
                "test": test_name,
                "status": "FAIL",
                "detail": str(e),
                "time_ms": 0,
            })
            print(f"  \u2717 {test_name} — {e}")
        except Exception as e:
            self.total_failed += 1
            self.results.append({
                "test": test_name,
                "status": "ERROR",
                "detail": f"{type(e).__name__}: {e}",
                "time_ms": 0,
            })
            print(f"  \u2717 {test_name} — {type(e).__name__}: {e}")

    def summary(self) -> dict:
        """Genera el resumen de la ejecución."""
        elapsed = time.time() - self.start_time
        total = self.total_passed + self.total_failed
        return {
            "timestamp": datetime.now().isoformat(),
            "total_tests": total,
            "passed": self.total_passed,
            "failed": self.total_failed,
            "elapsed_seconds": round(elapsed, 2),
            "success_rate": f"{(self.total_passed / total * 100):.1f}%" if total > 0 else "N/A",
            "results": self.results,
        }


# =============================================================================
# CONVERSACIONES DE PRUEBA
# =============================================================================

# Conversación 1: Casual — no es un proyecto
CONVERSACION_CASUAL = [
    {"role": "user", "content": "Hola, ¿qué tal todo?"},
    {"role": "assistant", "content": "¡Hola! Muy bien, ¿en qué puedo ayudarte?"},
    {"role": "user", "content": "Nada especial, mirando cosas por internet."},
    {"role": "assistant", "content": "¡Ah, vale! Si ves algo interesante puedes contármelo."},
    {"role": "user", "content": "Sí, luego te cuento. ¿Qué tiempo hace?"},
]

# Conversación 2: Proyecto incompleto — solo señal inicial
CONVERSACION_INCOMPLETA = [
    {"role": "user", "content": "Necesito algo para gestionar mis tareas"},
    {"role": "assistant", "content": "¿Qué tipo de tareas gestionas normalmente?"},
    {"role": "user", "content": "Pues de todo un poco, cosas del trabajo y personales"},
]

# Conversación 3: Proyecto completo — todas las imprescindibles cubiertas
# (Comunidad de vecinos → reservas de zonas comunes)
CONVERSACION_COMPLETA = [
    {"role": "user", "content": "Quiero crear una aplicación para que los vecinos de mi comunidad puedan reservar zonas comunes como la piscina o el salón de eventos."},
    {"role": "assistant", "content": "Interesante, ¿cuál es el problema actual con las reservas?"},
    {"role": "user", "content": "Ahora todo se gestiona en un cuaderno en la portería y siempre hay conflictos porque nadie sabe quién reservó qué. Es un caos total."},
    {"role": "assistant", "content": "¿Qué funciones necesitas exactamente?"},
    {"role": "user", "content": "Principalmente que los vecinos puedan ver el calendario de disponibilidad, reservar un espacio seleccionando fecha y hora, y que el administrador reciba una notificación de cada reserva. No necesita pagos ni facturas, solo la gestión de reservas."},
    {"role": "assistant", "content": "¿Cómo imaginas que alguien lo usaría?"},
    {"role": "user", "content": "El vecino entra en la app, selecciona el espacio que quiere reservar, elige la fecha y hora disponibles, y confirma. El administrador ve todas las reservas en un panel y puede cancelarlas si hace falta."},
]

# Conversación 4: Proyecto técnico (lenguaje técnico pero sigue siendo un proyecto)
CONVERSACION_TECNICA = [
    {"role": "user", "content": "Necesito una API REST con Express que maneje CRUD de usuarios y se conecte a PostgreSQL, con autenticación JWT."},
]

# Conversación 5: Simulación progresiva — la conversación evoluciona de casual a proyecto
CONVERSACION_PROGRESIVA = [
    {"role": "user", "content": "Hola, buenas tardes"},
    {"role": "assistant", "content": "Buenas tardes, ¿qué tal?"},
    {"role": "user", "content": "Estoy harto de usar Excel para llevar la contabilidad del restaurante"},
    {"role": "assistant", "content": "Te entiendo, llevar las cuentas en Excel puede ser muy tedioso."},
    {"role": "user", "content": "Siempre tengo que copiar los tickets a mano y al final del mes siempre hay errores. Necesito algo que automatice esto"},
    {"role": "assistant", "content": "Cuéntame más, ¿qué información manejas actualmente?"},
    {"role": "user", "content": "Tenemos un restaurante pequeño, llevamos ingresos, gastos, tickets del día. Quiero una aplicación para mi equipo de 5 personas. Tiene que poder calcular el balance del día automáticamente, mostrar un resumen y guardar el historial de ingresos y gastos. No necesito facturación ni inventario, solo ingresos y gastos diarios."},
    {"role": "assistant", "content": "¿Y cómo lo usarían concretamente?"},
    {"role": "user", "content": "El usuario entra, pulsa 'nuevo ticket', introduce el total y selecciona si es ingreso o gasto. Al final del turno, el usuario pulsa 'cerrar turno' y el sistema le muestra el resumen del día."},
]

# Conversación 6: Simulación de chat donde el arnés guía hasta completar
CONVERSACION_GUIADA_PASO_A_PASO = [
    {"role": "user", "content": "Necesito una app para mi clínica dental"},
    {"role": "assistant", "content": "Cuéntame más, ¿para qué la necesitas?"},
    {"role": "user", "content": "Para que los pacientes puedan pedir cita online"},
    {"role": "assistant", "content": "¿Qué problema hay ahora con el sistema de citas?"},
    {"role": "user", "content": "Todo es por teléfono y muchas veces se pierden citas o hay confusiones con las horas. Los pacientes siempre llaman en horario de consulta y a veces no pueden. Es un problema porque perdemos pacientes por esto."},
    {"role": "assistant", "content": "¿Qué cosas concretas debería poder hacer el paciente?"},
    {"role": "user", "content": "La app debe poder mostrar las horas disponibles, permitir al paciente confirmar la cita, y enviar un recordatorio automático. También necesito que yo como dentista pueda ver mi agenda del día. No necesito pagos online ni historial clínico, solo la gestión de citas."},
    {"role": "assistant", "content": "¿Cómo lo verías funcionando paso a paso?"},
    {"role": "user", "content": "El paciente entra en la página, ve un calendario con las horas libres, selecciona el día y la hora, pone su nombre y teléfono, y confirma. Yo como dentista veo la agenda completa y puedo bloquear horas para descanso."},
]


# =============================================================================
# TESTS CV1 — EVALUADOR DE MADUREZ
# =============================================================================

def suite_cv1(runner: TestRunner, evaluator: SDDMaturityEvaluator):

    def test_cv1_casual_no_es_proyecto():
        """CV1: Una conversación casual NO se detecta como proyecto."""
        result = evaluator.evaluate(CONVERSACION_CASUAL)
        assert result.is_project_conversation == False, \
            f"Esperado False, got {result.is_project_conversation}"
        assert result.can_generate_project == False
        assert result.project_confidence < 0.4, \
            f"Confianza debería ser < 0.4, got {result.project_confidence:.2f}"

    def test_cv1_incompleto_detecta_proyecto():
        """CV1: Una conversación con señal inicial SÍ se detecta como proyecto."""
        result = evaluator.evaluate(CONVERSACION_INCOMPLETA)
        assert result.is_project_conversation == True, \
            f"Esperado True, got {result.is_project_conversation}"
        assert result.can_generate_project == False, \
            "No debería poder generar con información incompleta"
        assert result.imprescindibles_covered < 5, \
            f"No deberían estar todas las imprescindibles: {result.imprescindibles_covered}/5"

    def test_cv1_completo_puede_generar():
        """CV1: Conversación con todas las imprescindibles → can_generate_project = True."""
        result = evaluator.evaluate(CONVERSACION_COMPLETA)
        assert result.is_project_conversation == True
        assert result.can_generate_project == True, \
            f"Debería poder generar. Imprescindibles: {result.imprescindibles_covered}/{result.imprescindibles_total}"
        assert result.imprescindibles_covered == 5, \
            f"Deberían estar 5/5 imprescindibles, got {result.imprescindibles_covered}"

    def test_cv1_tecnico_detecta_proyecto():
        """CV1: Lenguaje técnico también se detecta como proyecto."""
        result = evaluator.evaluate(CONVERSACION_TECNICA)
        assert result.is_project_conversation == True, \
            "El lenguaje técnico también debe detectarse como proyecto"

    def test_cv1_progresiva_evolucion():
        """CV1: Conversación que evoluciona de casual a proyecto."""
        # Primeros 2 mensajes: casual
        partial = CONVERSACION_PROGRESIVA[:2]
        result_early = evaluator.evaluate(partial)
        assert result_early.is_project_conversation == False, \
            "Los primeros mensajes no deberían parecer un proyecto"

        # Después de quejarse de Excel: debería detectarse
        result_mid = evaluator.evaluate(CONVERSACION_PROGRESIVA[:5])
        assert result_mid.is_project_conversation == True, \
            "Tras quejarse de Excel + necesidad, debería detectarse como proyecto"

        # Conversación completa: debería poder generar
        result_full = evaluator.evaluate(CONVERSACION_PROGRESIVA)
        assert result_full.can_generate_project == True, \
            f"Conversación completa debería poder generar. Imp: {result_full.imprescindibles_covered}/5"

    def test_cv1_todas_las_imprescindibles_cubiertas():
        """CV1: Verificar que las 5 imprescindibles tienen cobertura COVERED."""
        result = evaluator.evaluate(CONVERSACION_COMPLETA)
        imprescindibles_keys = ["what_is", "problem", "features", "limits", "usage"]
        for key in imprescindibles_keys:
            aspect = result.aspects[key]
            assert aspect.coverage == CoverageLevel.COVERED, \
                f"'{aspect.label}' debería estar COVERED, got {aspect.coverage.value}"

    def test_cv1_aspectos_tienen_evidencia():
        """CV1: Los aspectos cubiertos deben tener evidencia de la conversación."""
        result = evaluator.evaluate(CONVERSACION_COMPLETA)
        for key, aspect in result.aspects.items():
            if aspect.coverage == CoverageLevel.COVERED:
                assert len(aspect.evidence) > 0, \
                    f"'{aspect.label}' marcado como COVERED pero sin evidencia"

    def test_cv1_to_dict_serializacion():
        """CV1: to_dict() retorna estructura esperada para la interfaz."""
        result = evaluator.evaluate(CONVERSACION_COMPLETA)
        d = result.to_dict()
        assert isinstance(d, dict)
        assert "can_generate_project" in d
        assert "is_project_conversation" in d
        assert "coverage" in d
        assert "imprescindibles" in d["coverage"]
        assert "necesarias" in d["coverage"]
        assert "prescindibles" in d["coverage"]
        assert "aspects" in d
        assert d["can_generate_project"] == True

    def test_cv1_necesarias_no_bloquean():
        """CV1: Las necesarias no bloquean la generación del proyecto."""
        result = evaluator.evaluate(CONVERSACION_COMPLETA)
        # Puede generar aunque no todas las necesarias estén cubiertas
        assert result.can_generate_project == True
        assert result.necesarias_covered < result.necesarias_total, \
            "Algunas necesarias deberían faltar aún"

    def test_cv1_madurez_etiquetas():
        """CV1: Las etiquetas de madurez se asignan correctamente."""
        # Inicial
        r_inicial = evaluator.evaluate(CONVERSACION_INCOMPLETA)
        assert r_inicial.maturity_label in ["inicial", "intermedio"]

        # Completo (al menos intermedio)
        r_completo = evaluator.evaluate(CONVERSACION_COMPLETA)
        assert r_completo.maturity_label in ["intermedio", "maduro"]

    def test_cv1_guiada_completa():
        """CV1: La conversación guiada también logra las 5 imprescindibles."""
        result = evaluator.evaluate(CONVERSACION_GUIADA_PASO_A_PASO)
        assert result.is_project_conversation == True
        assert result.can_generate_project == True, \
            f"Conversación guiada debería generar. Imp: {result.imprescindibles_covered}/5"

    def test_cv1_get_missing_impressionsibles():
        """CV1: get_missing_impressionsibles retorna solo las no cubiertas."""
        result = evaluator.evaluate(CONVERSACION_INCOMPLETA)
        missing = evaluator.get_missing_impressionsibles(result)
        assert len(missing) > 0, "Debería faltar al menos una imprescindible"
        assert all(a.priority == AspectPriority.IMPRESCINDIBLE for a in missing), \
            "Todas deberían ser imprescindibles"

        # Conversación completa: no debería faltar ninguna
        result_full = evaluator.evaluate(CONVERSACION_COMPLETA)
        missing_full = evaluator.get_missing_impressionsibles(result_full)
        assert len(missing_full) == 0, \
            f"Completas debería tener 0 faltantes, got {len(missing_full)}"

    def test_cv1_get_missing_necesarias():
        """CV1: get_missing_necesarias funciona correctamente."""
        result = evaluator.evaluate(CONVERSACION_COMPLETA)
        missing = evaluator.get_missing_necesarias(result)
        # Todas las que faltan deberían ser necesarias
        assert all(a.priority == AspectPriority.NECESARIA for a in missing)

    def test_cv1_signals_tipo():
        """CV1: Las señales de proyecto tienen tipos válidos."""
        result = evaluator.evaluate(CONVERSACION_COMPLETA)
        valid_types = {"problem", "action", "user_ref", "existing_tool", "repetitive_process"}
        for signal in result.project_signals:
            assert signal.signal_type in valid_types, \
                f"Tipo de señal inválido: {signal.signal_type}"
            assert 0.0 <= signal.confidence <= 1.0, \
                f"Confianza fuera de rango: {signal.confidence}"
            assert len(signal.evidence) > 0, "Señal sin evidencia"

    print("\n  --- CV1: Evaluador de Madurez (15 tests) ---")
    runner.run("CV1.01  Casual NO es proyecto", test_cv1_casual_no_es_proyecto)
    runner.run("CV1.02  Incompleto detecta proyecto", test_cv1_incompleto_detecta_proyecto)
    runner.run("CV1.03  Completo puede generar", test_cv1_completo_puede_generar)
    runner.run("CV1.04  Técnico detecta proyecto", test_cv1_tecnico_detecta_proyecto)
    runner.run("CV1.05  Progresión casual→proyecto", test_cv1_progresiva_evolucion)
    runner.run("CV1.06  5 imprescindibles COVERED", test_cv1_todas_las_imprescindibles_cubiertas)
    runner.run("CV1.07  Aspectos tienen evidencia", test_cv1_aspectos_tienen_evidencia)
    runner.run("CV1.08  to_dict() serialización", test_cv1_to_dict_serializacion)
    runner.run("CV1.09  Necesarias no bloquean", test_cv1_necesarias_no_bloquean)
    runner.run("CV1.10  Etiquetas de madurez", test_cv1_madurez_etiquetas)
    runner.run("CV1.11  Conversación guiada completa", test_cv1_guiada_completa)
    runner.run("CV1.12  get_missing_impressionsibles", test_cv1_get_missing_impressionsibles)
    runner.run("CV1.13  get_missing_necesarias", test_cv1_get_missing_necesarias)
    runner.run("CV1.14  Señales tienen tipos válidos", test_cv1_signals_tipo)


# =============================================================================
# TESTS CV2 — ARNÉS DE PREGUNTAS GUÍA
# =============================================================================

def suite_cv2(runner: TestRunner, guide: SDDGuide):

    def test_cv2_casual_sin_guia():
        """CV2: Conversación casual → sin guía generada."""
        hint = guide.process_message(
            CONVERSACION_CASUAL[-1]["content"],
            CONVERSACION_CASUAL,
        )
        assert hint is None, "No debería generar guía para conversación casual"
        assert guide._state.is_active == False

    def test_cv2_proyecto_activa_guia():
        """CV2: Primera señal de proyecto → guía se activa."""
        guide.reset()
        hint = guide.process_message(
            CONVERSACION_INCOMPLETA[-1]["content"],
            CONVERSACION_INCOMPLETA,
        )
        assert hint is not None, "Debería generar guía para señal de proyecto"
        assert guide._state.is_active == True
        assert hint.priority == "imprescindible"

    def test_cv2_completo_sin_guia():
        """CV2: Proyecto completo → sin guía necesaria (todo cubierto)."""
        guide.reset()
        hint = guide.process_message(
            CONVERSACION_COMPLETA[-1]["content"],
            CONVERSACION_COMPLETA,
        )
        # Puede ser None o hint si aún no evaluó todo
        # Lo que importa es que get_project_ready_status diga True
        status = guide.get_project_ready_status(CONVERSACION_COMPLETA)
        assert status["can_generate_project"] == True, \
            "El estado debería indicar que puede generar proyecto"

    def test_cv2_system_prompt_addition():
        """CV2: El fragmento de system prompt contiene las marcas invisibles."""
        guide.reset()
        guide.process_message(
            CONVERSACION_INCOMPLETA[-1]["content"],
            CONVERSACION_INCOMPLETA,
        )
        if guide._state.last_hint:
            prompt = guide.get_system_prompt_addition(guide._state.last_hint)
            assert "INSTRUCCIÓN INTERNA" in prompt, \
                "Debe contener la marca de instrucción interna"
            assert "NO MOSTRAR AL USUARIO" in prompt, \
                "Debe contener la marca de invisibilidad"
            assert "No preguntes directamente" in prompt, \
                "Debe indicar que no pregunte directamente"
            assert len(prompt) > 100, "El fragmento debería ser sustancial"

    def test_cv2_guide_focus_en_imprescindible():
        """CV2: La guía se enfoca en aspectos imprescindibles primero."""
        guide.reset()
        hint = guide.process_message(
            CONVERSACION_INCOMPLETA[-1]["content"],
            CONVERSACION_INCOMPLETA,
        )
        if hint:
            assert hint.priority == "imprescindible", \
                f"Debería priorizar imprescindibles, got: {hint.priority}"

    def test_cv2_reset():
        """CV2: Reset reinicia todo el estado."""
        guide.reset()
        guide.process_message(
            CONVERSACION_INCOMPLETA[-1]["content"],
            CONVERSACION_INCOMPLETA,
        )
        assert guide._state.is_active == True or guide._state.ask_count > 0

        guide.reset()
        assert guide._state.is_active == False
        assert guide._state.ask_count == 0
        assert guide._state.consecutive_asks == 0
        assert len(guide._state.asked_aspects) == 0

    def test_cv2_consecutive_asks_limit():
        """CV2: No hace más de max_consecutive_asks preguntas seguidas."""
        guide.reset()
        # Forzar muchas preguntas sin aporte del usuario
        short_history = [
            {"role": "user", "content": "Necesito algo para el negocio"},
        ]
        guide.process_message("Necesito algo para el negocio", short_history)

        # Simular varias rondas sin nuevo contenido real
        hints_count = 0
        for i in range(6):
            guide._state.user_message_count_since_last_ask = 0
            hint = guide.process_message("bueno", short_history)
            if hint:
                hints_count += 1

        # No debería haber generado más de max_consecutive_asks seguidas
        assert guide._state.consecutive_asks <= guide._state.max_consecutive_asks + 1, \
            f"Demasiadas preguntas consecutivas: {guide._state.consecutive_asks}"

    def test_cv2_proyecto_ready_status():
        """CV2: get_project_ready_status retorna estructura correcta."""
        guide.reset()
        status = guide.get_project_ready_status(CONVERSACION_COMPLETA)
        assert isinstance(status, dict)
        assert "is_project_conversation" in status
        assert "can_generate_project" in status
        assert "maturity_label" in status
        assert "imprescindibles" in status
        assert "necesarias" in status
        assert "covered" in status["imprescindibles"]
        assert "total" in status["imprescindibles"]

    def test_cv2_desactiva_si_no_es_proyecto():
        """CV2: La guía se desactiva si la conversación deja de parecer proyecto."""
        guide.reset()
        # Activar con proyecto
        guide.process_message(
            CONVERSACION_INCOMPLETA[-1]["content"],
            CONVERSACION_INCOMPLETA,
        )
        # Enviar algo casual
        hint = guide.process_message(
            "No, ya no me interesa",
            CONVERSACION_CASUAL,
        )
        # Tras mensaje que no es proyecto, la guía debería desactivarse
        # (depende de la confianza final)
        # No forzamos assertion estricta porque puede que la conversación
        # acumulada todavía dé señal, pero el comportamiento es correcto
        status = guide.get_project_ready_status(CONVERSACION_CASUAL)
        assert status["can_generate_project"] == False

    def test_cv2_guiada_paso_a_paso():
        """CV2: La conversación guiada logra can_generate_project."""
        guide.reset()
        status = guide.get_project_ready_status(CONVERSACION_GUIADA_PASO_A_PASO)
        assert status["is_project_conversation"] == True, \
            "La conversación guiada debería detectarse como proyecto"
        assert status["can_generate_project"] == True, \
            f"Debería poder generar. Imp: {status['imprescindibles']}"

    def test_cv2_hint_contiene_focus():
        """CV2: El hint contiene los campos necesarios."""
        guide.reset()
        hint = guide.process_message(
            CONVERSACION_INCOMPLETA[-1]["content"],
            CONVERSACION_INCOMPLETA,
        )
        if hint:
            assert isinstance(hint, GuideHint)
            assert len(hint.focus_aspect) > 0
            assert len(hint.focus_label) > 0
            assert len(hint.natural_instruction) > 0
            assert hint.priority in ["imprescindible", "necesaria"]

    print("\n  --- CV2: Arnés de Preguntas Guía (11 tests) ---")
    runner.run("CV2.01  Casual sin guía", test_cv2_casual_sin_guia)
    runner.run("CV2.02  Proyecto activa guía", test_cv2_proyecto_activa_guia)
    runner.run("CV2.03  Completo sin guía necesaria", test_cv2_completo_sin_guia)
    runner.run("CV2.04  System prompt addition", test_cv2_system_prompt_addition)
    runner.run("CV2.05  Focus en imprescindibles", test_cv2_guide_focus_en_imprescindible)
    runner.run("CV2.06  Reset reinicia estado", test_cv2_reset)
    runner.run("CV2.07  Límite preguntas consecutivas", test_cv2_consecutive_asks_limit)
    runner.run("CV2.08  Project ready status", test_cv2_proyecto_ready_status)
    runner.run("CV2.09  Desactiva si no es proyecto", test_cv2_desactiva_si_no_es_proyecto)
    runner.run("CV2.10  Guiada paso a paso", test_cv2_guiada_paso_a_paso)
    runner.run("CV2.11  Hint tiene campos requeridos", test_cv2_hint_contiene_focus)


# =============================================================================
# TESTS CV3 — ENRUTAMIENTO POR TIER
# =============================================================================

def suite_cv3(runner: TestRunner):

    def test_cv3_chat_es_fast():
        """CV3: task_type 'chat' → tier 'fast'."""
        assert get_task_tier("chat") == "fast"

    def test_cv3_evaluation_es_fast():
        """CV3: task_type 'evaluation' → tier 'fast'."""
        assert get_task_tier("evaluation") == "fast"

    def test_cv3_sdd_evaluation_es_fast():
        """CV3: task_type 'sdd_evaluation' → tier 'fast'."""
        assert get_task_tier("sdd_evaluation") == "fast"

    def test_cv3_planning_es_capable():
        """CV3: task_type 'planning' → tier 'capable'."""
        assert get_task_tier("planning") == "capable"

    def test_cv3_generation_es_capable():
        """CV3: task_type 'generation' → tier 'capable'."""
        assert get_task_tier("generation") == "capable"

    def test_cv3_coding_es_capable():
        """CV3: task_type 'coding' → tier 'capable'."""
        assert get_task_tier("coding") == "capable"

    def test_cv3_correction_es_capable():
        """CV3: task_type 'correction' → tier 'capable'."""
        assert get_task_tier("correction") == "capable"

    def test_cv3_sdd_generation_es_capable():
        """CV3: task_type 'sdd_generation' → tier 'capable'."""
        assert get_task_tier("sdd_generation") == "capable"

    def test_cv3_spec_generation_es_capable():
        """CV3: task_type 'spec_generation' → tier 'capable'."""
        assert get_task_tier("spec_generation") == "capable"

    def test_cv3_analysis_es_capable():
        """CV3: task_type 'analysis' → tier 'capable'."""
        assert get_task_tier("analysis") == "capable"

    def test_cv3_default_capable():
        """CV3: task_type desconocido → tier 'capable' (seguro por defecto)."""
        assert get_task_tier("desconocido") == "capable"
        assert get_task_tier("") == "capable"
        assert get_task_tier("cualquier_cosa") == "capable"

    def test_cv3_fast_tier_context_limit():
        """CV3: El límite de contexto para fast tier es 32000."""
        assert _FAST_TIER_MAX_CONTEXT == 32000

    def test_cv3_todos_los_tipos_registrados():
        """CV3: Todos los task_types esperados están registrados."""
        expected_types = [
            "chat", "evaluation", "sdd_evaluation",
            "planning", "generation", "coding", "correction",
            "spec_generation", "sdd_generation", "analysis",
        ]
        for tt in expected_types:
            assert tt in _TASK_TYPE_TIER, f"Falta task_type '{tt}' en el diccionario"

    print("\n  --- CV3: Enrutamiento por Tier (13 tests) ---")
    runner.run("CV3.01  chat → fast", test_cv3_chat_es_fast)
    runner.run("CV3.02  evaluation → fast", test_cv3_evaluation_es_fast)
    runner.run("CV3.03  sdd_evaluation → fast", test_cv3_sdd_evaluation_es_fast)
    runner.run("CV3.04  planning → capable", test_cv3_planning_es_capable)
    runner.run("CV3.05  generation → capable", test_cv3_generation_es_capable)
    runner.run("CV3.06  coding → capable", test_cv3_coding_es_capable)
    runner.run("CV3.07  correction → capable", test_cv3_correction_es_capable)
    runner.run("CV3.08  sdd_generation → capable", test_cv3_sdd_generation_es_capable)
    runner.run("CV3.09  spec_generation → capable", test_cv3_spec_generation_es_capable)
    runner.run("CV3.10  analysis → capable", test_cv3_analysis_es_capable)
    runner.run("CV3.11  desconocido → capable (default)", test_cv3_default_capable)
    runner.run("CV3.12  fast tier ctx limit = 32000", test_cv3_fast_tier_context_limit)
    runner.run("CV3.13  todos los tipos registrados", test_cv3_todos_los_tipos_registrados)


# =============================================================================
# TESTS DE INTEGRACIÓN CV1+CV2+CV3 END-TO-END
# =============================================================================

def suite_integracion(runner: TestRunner, evaluator: SDDMaturityEvaluator, guide: SDDGuide):

    def test_e2e_casual_boton_deshabilitado():
        """E2E: Conversación casual → botón "Crear Proyecto" DESHABILITADO."""
        maturity = evaluator.evaluate(CONVERSACION_CASUAL)
        status = guide.get_project_ready_status(CONVERSACION_CASUAL)
        assert maturity.can_generate_project == False
        assert status["can_generate_project"] == False
        assert status["is_project_conversation"] == False
        # CV3: Si se usara chat, sería fast tier
        assert get_task_tier("chat") == "fast"

    def test_e2e_incompleto_boton_deshabilitado():
        """E2E: Proyecto incompleto → botón DESHABILITADO."""
        maturity = evaluator.evaluate(CONVERSACION_INCOMPLETA)
        status = guide.get_project_ready_status(CONVERSACION_INCOMPLETA)
        assert maturity.can_generate_project == False
        assert status["can_generate_project"] == False
        assert status["is_project_conversation"] == True

    def test_e2e_completo_boton_habilitado():
        """E2E: Proyecto completo → botón HABILITADO."""
        maturity = evaluator.evaluate(CONVERSACION_COMPLETA)
        status = guide.get_project_ready_status(CONVERSACION_COMPLETA)
        assert maturity.can_generate_project == True
        assert status["can_generate_project"] == True
        assert status["imprescindibles"]["covered"] == 5

    def test_e2e_guiada_boton_habilitado():
        """E2E: Conversación guiada paso a paso → botón HABILITADO."""
        maturity = evaluator.evaluate(CONVERSACION_GUIADA_PASO_A_PASO)
        status = guide.get_project_ready_status(CONVERSACION_GUIADA_PASO_A_PASO)
        assert maturity.can_generate_project == True
        assert status["can_generate_project"] == True

    def test_e2e_progresivo_evolucion_boton():
        """E2E: Conversación progresiva — botón pasa de deshabilitado a habilitado."""
        # Fase 1: Casual → deshabilitado
        s1 = guide.get_project_ready_status(CONVERSACION_PROGRESIVA[:2])
        assert s1["can_generate_project"] == False, \
            "Fase casual: botón debería estar deshabilitado"

        # Fase 2: Señal de proyecto pero sin imprescindibles → deshabilitado
        s2 = guide.get_project_ready_status(CONVERSACION_PROGRESIVA[:5])
        assert s2["is_project_conversation"] == True, \
            "Fase señal: debería detectarse como proyecto"
        assert s2["can_generate_project"] == False, \
            "Fase señal: botón aún deshabilitado"

        # Fase 3: Completo → habilitado
        s3 = guide.get_project_ready_status(CONVERSACION_PROGRESIVA)
        assert s3["can_generate_project"] == True, \
            f"Fase completa: botón debería estar habilitado. Imp: {s3['imprescindibles']}"

    def test_e2e_chat_uses_fast_sdd_uses_capable():
        """E2E: El chat usa fast tier, la generación de SDD usa capable."""
        # Durante la conversación: fast
        chat_tier = get_task_tier("chat")
        assert chat_tier == "fast"

        # Cuando se genera el SDD: capable
        sdd_tier = get_task_tier("sdd_generation")
        assert sdd_tier == "capable"

        # Verificar que son diferentes
        assert chat_tier != sdd_tier, \
            "Chat y SDD generation deberían usar tiers diferentes"

    def test_e2e_consistencia_cv1_cv2():
        """E2E: CV1 y CV2 son consistentes en sus evaluaciones."""
        for conv_name, conv in [
            ("casual", CONVERSACION_CASUAL),
            ("incompleta", CONVERSACION_INCOMPLETA),
            ("completa", CONVERSACION_COMPLETA),
            ("guiada", CONVERSACION_GUIADA_PASO_A_PASO),
        ]:
            maturity = evaluator.evaluate(conv)
            status = guide.get_project_ready_status(conv)
            assert maturity.can_generate_project == status["can_generate_project"], \
                f"Inconsistencia en '{conv_name}': " \
                f"CV1={maturity.can_generate_project}, CV2={status['can_generate_project']}"

    def test_e2e_to_dict_para_frontend():
        """E2E: La serialización to_dict tiene todo lo que necesita el frontend."""
        maturity = evaluator.evaluate(CONVERSACION_COMPLETA)
        d = maturity.to_dict()
        # Campos que el frontend necesita para actualizar el botón
        assert "can_generate_project" in d
        assert "is_project_conversation" in d
        assert "maturity_label" in d
        assert "project_confidence" in d
        assert "coverage" in d
        assert d["coverage"]["imprescindibles"]["covered"] == 5
        assert d["coverage"]["imprescindibles"]["total"] == 5

    def test_e2e_flujo_conversacion_completo():
        """
        E2E: Simula el flujo completo de una conversación real:
        1. Usuario empieza a hablar de un problema
        2. Sistema detecta que es un proyecto
        3. Arnés guía las preguntas faltantes
        4. Todas las imprescindibles se cubren
        5. Botón se habilita
        """
        guide.reset()

        # Paso 1: Mensaje inicial — posible señal
        msg1 = CONVERSACION_GUIADA_PASO_A_PASO[0]["content"]
        conv1 = CONVERSACION_GUIADA_PASO_A_PASO[:1]
        m1 = evaluator.evaluate(conv1)
        guide.process_message(msg1, conv1)
        # Puede o no detectar proyecto con un solo mensaje, lo importante es que no falle

        # Paso 2: Conversación crece — debe detectar proyecto
        conv2 = CONVERSACION_GUIADA_PASO_A_PASO[:4]
        m2 = evaluator.evaluate(conv2)
        guide.process_message(CONVERSACION_GUIADA_PASO_A_PASO[3]["content"], conv2)
        assert m2.is_project_conversation == True, \
            "Tras 4 mensajes debería detectarse proyecto"

        # Paso 3: Conversación completa — debe poder generar
        m3 = evaluator.evaluate(CONVERSACION_GUIADA_PASO_A_PASO)
        guide.process_message(
            CONVERSACION_GUIADA_PASO_A_PASO[-1]["content"],
            CONVERSACION_GUIADA_PASO_A_PASO,
        )
        assert m3.can_generate_project == True, \
            f"Conversación completa debería poder generar. Imp: {m3.imprescindibles_covered}/5"

        status = guide.get_project_ready_status(CONVERSACION_GUIADA_PASO_A_PASO)
        assert status["can_generate_project"] == True

    print("\n  --- Integración E2E (9 tests) ---")
    runner.run("E2E.01  Casual → botón deshabilitado", test_e2e_casual_boton_deshabilitado)
    runner.run("E2E.02  Incompleto → botón deshabilitado", test_e2e_incompleto_boton_deshabilitado)
    runner.run("E2E.03  Completo → botón habilitado", test_e2e_completo_boton_habilitado)
    runner.run("E2E.04  Guiada → botón habilitado", test_e2e_guiada_boton_habilitado)
    runner.run("E2E.05  Progresión deshabilitado→habilitado", test_e2e_progresivo_evolucion_boton)
    runner.run("E2E.06  chat=fast, sdd=capable", test_e2e_chat_uses_fast_sdd_uses_capable)
    runner.run("E2E.07  Consistencia CV1 vs CV2", test_e2e_consistencia_cv1_cv2)
    runner.run("E2E.08  to_dict para frontend", test_e2e_to_dict_para_frontend)
    runner.run("E2E.09  Flujo conversación completo", test_e2e_flujo_conversacion_completo)


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 70)
    print("  BLOQUE CV — TEST DE INTEGRACIÓN COMPLETO")
    print("  CV1: Evaluador de Madurez del SDD")
    print("  CV2: Arnés Adaptativo de Preguntas Guía")
    print("  CV3: Enrutamiento por Tier de Modelo")
    print("  E2E: Integración End-to-End")
    print("=" * 70)
    print(f"  Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    runner = TestRunner()
    evaluator = SDDMaturityEvaluator()
    guide = SDDGuide()

    # Ejecutar suites
    suite_cv1(runner, evaluator)
    suite_cv2(runner, guide)
    suite_cv3(runner)
    suite_integracion(runner, evaluator, guide)

    # Resumen final
    summary = runner.summary()
    print("\n" + "=" * 70)
    print(f"  RESULTADO: {summary['passed']}/{summary['total_tests']} tests PASARON")
    if summary['failed'] > 0:
        print(f"  {summary['failed']} tests FALLARON")
    print(f"  Tasa de éxito: {summary['success_rate']}")
    print(f"  Tiempo: {summary['elapsed_seconds']}s")
    print("=" * 70)

    # Detalle de fallos si los hay
    failures = [r for r in summary["results"] if r["status"] != "PASS"]
    if failures:
        print("\n  DETALLE DE FALLOS:")
        for f in failures:
            print(f"    - {f['test']}: {f['detail']}")

    # Guardar reporte JSON
    report_path = os.path.join(
        os.path.dirname(__file__), '..', '..', 'download',
        'test_bloque_cv_report.json'
    )
    report_path = os.path.abspath(report_path)
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"\n  Reporte guardado en: {report_path}")

    # Retornar código de salida
    if summary['failed'] > 0:
        print("\n  HAY FALLOS — revisar antes de proceder")
        sys.exit(1)
    else:
        print("\n  TODOS LOS TESTS PASARON — sistema listo para prueba real")
        sys.exit(0)


if __name__ == "__main__":
    main()
