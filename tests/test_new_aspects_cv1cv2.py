# apa/tests/test_new_aspects_cv1cv2.py
"""
Test dedicado para validar los 3 nuevos aspectos NECESARIAS:
  - states (Estados o etapas del proceso)
  - invariants (Reglas que siempre se cumplen)
  - edge_cases (Que podria salir mal)

Tambien valida las enriquecidas: constraints (volumen/escala) y success_criteria (rechazo).

Ejecutar:
    cd /home/z/APA
    python -m apa.tests.test_new_aspects_cv1cv2
"""

import sys
import os
import time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from apa.core.sdd_maturity import (
    SDDMaturityEvaluator,
    AspectPriority,
    CoverageLevel,
)
from apa.core.sdd_guide import SDDGuide, GuideState

PASS = 0
FAIL = 0
RESULTS = []


def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        RESULTS.append((name, True, ""))
        print(f"  \u2713 {name}")
    else:
        FAIL += 1
        RESULTS.append((name, False, detail))
        print(f"  \u2717 {name} — {detail}")


# =============================================================================
# CONVERSACIONES DE PRUEBA
# =============================================================================

# Sin los nuevos aspectos — solo imprescindibles (misma conversacion que test_bloque_cv_integration.py)
CONV_SOLO_IMPRESCINDIBLES = [
    {"role": "user", "content": "Quiero crear una aplicación para que los vecinos de mi comunidad puedan reservar zonas comunes como la piscina o el salón de eventos."},
    {"role": "assistant", "content": "Interesante, ¿cuál es el problema actual con las reservas?"},
    {"role": "user", "content": "Ahora todo se gestiona en un cuaderno en la portería y siempre hay conflictos porque nadie sabe quién reservó qué. Es un caos total."},
    {"role": "assistant", "content": "¿Qué funciones necesitas exactamente?"},
    {"role": "user", "content": "Principalmente que los vecinos puedan ver el calendario de disponibilidad, reservar un espacio seleccionando fecha y hora, y que el administrador reciba una notificación de cada reserva. No necesita pagos ni facturas, solo la gestión de reservas."},
    {"role": "assistant", "content": "¿Cómo imaginas que alguien lo usaría?"},
    {"role": "user", "content": "El vecino entra en la app, selecciona el espacio que quiere reservar, elige la fecha y hora disponibles, y confirma. El administrador ve todas las reservas en un panel y puede cancelarlas si hace falta."},
]

# Con los 3 nuevos aspectos cubiertos (imprescindibles tambien cubiertas)
CONV_CON_NUEVOS_ASPECTOS = [
    {"role": "user", "content": "Quiero crear una aplicación para que los vecinos de mi comunidad puedan reservar zonas comunes como la piscina o el salón de eventos."},
    {"role": "assistant", "content": "¿Cuál es el problema actual?"},
    {"role": "user", "content": "Ahora todo se gestiona en un cuaderno en la portería y siempre hay conflictos. Es un caos total."},
    {"role": "assistant", "content": "¿Qué funciones necesitas?"},
    {"role": "user", "content": "Los vecinos pueden ver calendario, reservar espacio. No necesita pagos ni facturas. El vecino entra, selecciona, confirma."},
    {"role": "assistant", "content": "¿Cómo pasan por estados las reservas?"},
    {"role": "user", "content": "Primero queda como pendiente, luego el admin la aprueba o rechaza, y si está aprobada el vecino recibe confirmación. Si se cancela, vuelve a disponible."},
    {"role": "assistant", "content": "¿Hay reglas que siempre se cumplan?"},
    {"role": "user", "content": "Sí, un mismo espacio no puede tener dos reservas a la misma hora, y un vecino no puede reservar más de 3 veces por semana."},
    {"role": "assistant", "content": "¿Qué podría salir mal?"},
    {"role": "user", "content": "Que dos vecinos intenten reservar el mismo hueco a la vez, o que alguien reserve y no vaya, dejando el espacio vacío."},
]

# Con volumen/escala (imprescindibles cubiertas)
CONV_CON_VOLUMEN = [
    {"role": "user", "content": "Quiero crear una aplicación de reservas para mi comunidad. El problema es que se gestionan en papel y hay confusiones. Necesito que puedan ver calendario y reservar. No incluye pagos. El vecino entra, selecciona y confirma."},
    {"role": "assistant", "content": "¿Cuántos vecinos son aproximadamente?"},
    {"role": "user", "content": "Somos unos 200 vecinos, y esperamos unas 50 reservas al mes."},
]

# Con criterios de rechazo (imprescindibles cubiertas)
CONV_CON_RECHAZO = [
    {"role": "user", "content": "Quiero crear una aplicación de reservas para vecinos. El problema es que se gestiona en papel y hay errores. Necesito ver calendario y reservar. No incluye pagos. El vecino entra, selecciona y confirma."},
    {"role": "assistant", "content": "¿Qué pasaría si algo sale mal?"},
    {"role": "user", "content": "El sistema no debería permitir reservar un espacio que ya está ocupado. Si alguien intenta reservar fuera de horario, debe mostrar error y rechazar la operación."},
]


# =============================================================================
# TESTS
# =============================================================================

def test_estructura_aspectos():
    """Validar recuentos de aspectos tras los cambios."""
    print("\n  --- Estructura de aspectos ---")
    evaluator = SDDMaturityEvaluator()

    imp = [a for a in evaluator._aspects.values() if a.priority == AspectPriority.IMPRESCINDIBLE]
    nec = [a for a in evaluator._aspects.values() if a.priority == AspectPriority.NECESARIA]
    pre = [a for a in evaluator._aspects.values() if a.priority == AspectPriority.PRESCINDIBLE]

    check("5.09  Imprescindibles = 5", len(imp) == 5, f"got {len(imp)}")
    check("5.10  Necesarias = 8", len(nec) == 8, f"got {len(nec)}")
    check("5.11  Total aspectos = 18", len(evaluator._aspects) == 18, f"got {len(evaluator._aspects)}")

    # 5.1: Los 3 nuevos aspectos existen
    check("5.01  'states' existe", "states" in evaluator._aspects)
    check("5.01  'invariants' existe", "invariants" in evaluator._aspects)
    check("5.01  'edge_cases' existe", "edge_cases" in evaluator._aspects)

    # Son NECESARIAS
    check("5.01  states priority = NECESARIA", evaluator._aspects["states"].priority == AspectPriority.NECESARIA)
    check("5.01  invariants priority = NECESARIA", evaluator._aspects["invariants"].priority == AspectPriority.NECESARIA)
    check("5.01  edge_cases priority = NECESARIA", evaluator._aspects["edge_cases"].priority == AspectPriority.NECESARIA)

    # Los 5 imprescindibles originales siguen intactos (orden alfabetico)
    expected_imp_keys = sorted(["what_is", "problem", "features", "limits", "usage"])
    actual_imp_keys = sorted([a.key for a in imp])
    check("Imprescindibles sin cambios", actual_imp_keys == expected_imp_keys,
          f"got {actual_imp_keys}")

    # Las 8 necesarias son las esperadas
    expected_nec_keys = sorted(["similar_existing", "stakeholders", "constraints",
                                "success_criteria", "integrations", "states",
                                "invariants", "edge_cases"])
    actual_nec_keys = sorted([a.key for a in nec])
    check("Necesarias correctas", actual_nec_keys == expected_nec_keys,
          f"got {actual_nec_keys}")


def test_deteccion_nuevos_aspectos():
    """Validar que los 3 nuevos aspectos se detectan correctamente."""
    print("\n  --- Deteccion de nuevos aspectos ---")
    evaluator = SDDMaturityEvaluator()

    # 5.5: Sin mencionar — NOT_COVERED
    r_sin = evaluator.evaluate(CONV_SOLO_IMPRESCINDIBLES)
    check("5.05  states = NOT_COVERED sin mencion",
          r_sin.aspects["states"].coverage == CoverageLevel.NOT_COVERED,
          f"got {r_sin.aspects['states'].coverage.value}")
    check("5.05  invariants = NOT_COVERED sin mencion",
          r_sin.aspects["invariants"].coverage == CoverageLevel.NOT_COVERED,
          f"got {r_sin.aspects['invariants'].coverage.value}")
    check("5.05  edge_cases = NOT_COVERED sin mencion",
          r_sin.aspects["edge_cases"].coverage == CoverageLevel.NOT_COVERED,
          f"got {r_sin.aspects['edge_cases'].coverage.value}")

    # 5.2-5.4: Con mención — COVERED
    r_con = evaluator.evaluate(CONV_CON_NUEVOS_ASPECTOS)
    check("5.02  states = COVERED con estados",
          r_con.aspects["states"].coverage == CoverageLevel.COVERED,
          f"got {r_con.aspects['states'].coverage.value}")
    check("5.03  invariants = COVERED con reglas",
          r_con.aspects["invariants"].coverage == CoverageLevel.COVERED,
          f"got {r_con.aspects['invariants'].coverage.value}")
    check("5.04  edge_cases = COVERED con errores",
          r_con.aspects["edge_cases"].coverage == CoverageLevel.COVERED,
          f"got {r_con.aspects['edge_cases'].coverage.value}")


def test_deteccion_enriquecidas():
    """Validar que constraints y success_criteria enriquecidas detectan."""
    print("\n  --- Deteccion de enriquecidas ---")
    evaluator = SDDMaturityEvaluator()

    # 5.12: constraints detecta volumen/escala
    r_vol = evaluator.evaluate(CONV_CON_VOLUMEN)
    check("5.12  constraints detecta volumen/escala",
          r_vol.aspects["constraints"].coverage == CoverageLevel.COVERED,
          f"got {r_vol.aspects['constraints'].coverage.value}")

    # 5.13: success_criteria detecta criterios de rechazo
    r_rech = evaluator.evaluate(CONV_CON_RECHAZO)
    check("5.13  success_criteria detecta rechazo",
          r_rech.aspects["success_criteria"].coverage == CoverageLevel.COVERED,
          f"got {r_rech.aspects['success_criteria'].coverage.value}")


def test_guiado_cv2_nuevos_aspectos():
    """Validar que CV2 genera hints para los nuevos aspectos."""
    print("\n  --- Guia CV2 para nuevos aspectos ---")
    guide = SDDGuide()

    # 5.6: CV2 puede guiar hacia los nuevos aspectos cuando imprescindibles cubiertas
    guide.reset()
    maturity = guide._evaluator.evaluate(CONV_SOLO_IMPRESCINDIBLES)
    # Cuando imprescindibles estan cubiertas, las nuevas necesarias son candidatas
    check("5.06  Imprescindibles cubiertas para test de guia",
          maturity.can_generate_project == True)
    missing_nec = guide._evaluator.get_missing_necesarias(maturity)
    missing_keys = [a.key for a in missing_nec]
    # Los 3 nuevos aspectos deben estar entre las faltantes (no cubiertos en esta conv)
    new_in_missing = [k for k in ["states", "invariants", "edge_cases"] if k in missing_keys]
    check("5.06  Nuevos aspectos son candidatos para guiar",
          len(new_in_missing) == 3,
          f"solo {new_in_missing} de 3 en faltantes")

    # 5.7-5.8: Verificar que los nuevos aspectos tienen frases de transicion
    # y que _build_instruction no retorna vacio para ellos
    for key in ["states", "invariants", "edge_cases"]:
        has_transition = key in guide._transition_phrases
        check(f"5.07  '{key}' tiene frases de transicion", has_transition)

    for key in ["states", "invariants", "edge_cases"]:
        aspect = type('A', (), {'key': key, 'label': key})()
        instruction = guide._build_instruction(aspect)
        check(f"5.08  '{key}' tiene instruccion LLM", len(instruction) > 30,
              f"got {len(instruction)} chars")


def test_no_rompe_imprescindibles():
    """Validar que los cambios no afectan a las imprescindibles."""
    print("\n  --- Regresion: imprescindibles intactas ---")
    evaluator = SDDMaturityEvaluator()

    r = evaluator.evaluate(CONV_SOLO_IMPRESCINDIBLES)
    check("Imprescindibles_covered = 5",
          r.imprescindibles_covered == 5,
          f"got {r.imprescindibles_covered}")
    check("Imprescindibles_total = 5",
          r.imprescindibles_total == 5,
          f"got {r.imprescindibles_total}")
    check("can_generate_project = True",
          r.can_generate_project == True)
    check("Necesarias_covered < Necesarias_total",
          r.necesarias_covered < r.necesarias_total,
          f"got {r.necesarias_covered}/{r.necesarias_total}")


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("  TEST: 3 nuevos aspectos NECESARIAS + 2 enriquecidas")
    print("  states | invariants | edge_cases | constraints+ | success_criteria+")
    print("=" * 70)
    print(f"  Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    t0 = time.time()

    test_estructura_aspectos()
    test_deteccion_nuevos_aspectos()
    test_deteccion_enriquecidas()
    test_guiado_cv2_nuevos_aspectos()
    test_no_rompe_imprescindibles()

    elapsed = time.time() - t0

    print("\n" + "=" * 70)
    print(f"  RESULTADO: {PASS}/{PASS + FAIL} tests PASARON")
    if FAIL > 0:
        print(f"  {FAIL} tests FALLARON")
    print(f"  Tiempo: {elapsed:.2f}s")
    print("=" * 70)

    if FAIL > 0:
        print("\n  DETALLE DE FALLOS:")
        for name, ok, detail in RESULTS:
            if not ok:
                print(f"    - {name}: {detail}")
        sys.exit(1)
    else:
        print("\n  TODOS LOS TESTS PASARON")
        sys.exit(0)
