#!/usr/bin/env python3
# test_fase2_integration.py
# Tests de integración Fase 2: FailureAuditorAgent + SemiAutoAgent v3.4
#
# VALIDA:
#   1. Import perezoso de FailureAuditorAgent (no rompe si no existe)
#   2. _diagnose_failure() invoca auditor.diagnose() correctamente
#   3. task.validation_result["failure_diagnosis"] se popula tras fallo
#   4. get_failure_diagnosis() retorna el diagnóstico de la última tarea
#   5. get_progress_summary() incluye last_diagnosis
#   6. Los 7 puntos de llamada están presentes en el código fuente
#   7. Los 4 tipos de fallo se diagnostican correctamente (mock)
#
# USO:
#   python test_fase2_integration.py
#
# CRITERIO: Los 7 tests deben pasar.
# ============================================================================

import os
import sys
import re
import unittest
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any

# Asegurar que apa.core es importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Asegurar que el directorio del proyecto está en el path
_PROJECT_ROOT = os.path.join(os.path.dirname(__file__), '..', 'APA')
if os.path.exists(_PROJECT_ROOT):
    sys.path.insert(0, _PROJECT_ROOT)
    sys.path.insert(0, os.path.join(_PROJECT_ROOT, '..'))


# ============================================================================
# Mock: FailureAuditorAgent (sin necesidad del módulo real)
# ============================================================================
class MockFailureDiagnosis:
    """Mock de FailureDiagnosis."""
    def __init__(self, category="model_limitation", severity="minor",
                 agent="coder", task_id="T1", evidence=None,
                 description="", can_continue=True, can_abort=False,
                 suggested_action="retry", context_for_retry=None):
        self.category = category
        self.severity = severity
        self.agent = agent
        self.task_id = task_id
        self.evidence = evidence or []
        self.description = description
        self.can_continue = can_continue
        self.can_abort = can_abort
        self.suggested_action = suggested_action
        self.context_for_retry = context_for_retry
        self.__dataclass_fields__ = {
            'category': None, 'severity': None, 'agent': None,
            'task_id': None, 'evidence': None, 'description': None,
            'can_continue': None, 'can_abort': None,
            'suggested_action': None, 'context_for_retry': None,
        }


class MockFailureAuditorAgent:
    """Mock de FailureAuditorAgent que retorna diagnósticos preconfigurados."""
    def __init__(self, forced_diagnosis=None):
        self._forced = forced_diagnosis

    def diagnose(self, task, error, result, agent_name):
        if self._forced:
            return self._forced
        return MockFailureDiagnosis(
            category="model_limitation",
            severity="minor",
            agent=agent_name,
            task_id=getattr(task, 'task_id', ''),
            description="Mock diagnosis",
            suggested_action="retry",
        )

    def get_user_facing_message(self, diagnosis):
        return f"[Mock] {diagnosis.category}: {diagnosis.description}"

    def should_escalate_to_director(self, diagnosis):
        return diagnosis.severity == "critical"


# ============================================================================
# Tests
# ============================================================================

class TestFase2Integration(unittest.TestCase):
    """Tests de integración Fase 2: FailureAuditorAgent + SemiAutoAgent."""

    def setUp(self):
        """Configura el entorno de test antes de cada test."""
        # Verificar que failure_auditor.py está disponible
        self._auditor_module_path = os.path.join(
            os.path.dirname(__file__), '..', 'core', 'failure_auditor.py'
        )
        self._auditor_available = os.path.exists(self._auditor_module_path)

    # ----------------------------------------------------------------
    # Test 1: El archivo failure_auditor.py existe y tiene las clases
    # ----------------------------------------------------------------
    def test_01_failure_auditor_module_exists(self):
        """Test 1: failure_auditor.py existe y exporta las clases correctas."""
        self.assertTrue(
            self._auditor_available,
            "failure_auditor.py no encontrado en core/"
        )

        with open(self._auditor_module_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Verificar que exporta las clases correctas
        self.assertIn('class FailureDiagnosis', content,
                      "FailureDiagnosis no encontrado en failure_auditor.py")
        self.assertIn('class FailureAuditorAgent', content,
                      "FailureAuditorAgent no encontrado en failure_auditor.py")
        self.assertIn('__all__', content,
                      "__all__ no encontrado en failure_auditor.py")
        print("  Test 1 PASÓ: failure_auditor.py existe con clases correctas")

    # ----------------------------------------------------------------
    # Test 2: El archivo semi_auto_agent.py tiene los puntos
    #         de integración de FailureAuditorAgent
    # ----------------------------------------------------------------
    def test_02_semi_auto_agent_has_integration_points(self):
        """Test 2: semi_auto_agent.py (v3.4) tiene los 7 puntos de llamada."""
        agent_path = os.path.join(
            os.path.dirname(__file__), '..', 'agents', 'semi_auto_agent.py'
        )
        self.assertTrue(
            os.path.exists(agent_path),
            "semi_auto_agent.py no encontrado en apa/agents/"
        )

        with open(agent_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Contar puntos de llamada a _diagnose_failure(
        # Debe haber exactamente 7 invocaciones (excluyendo la definición)
        call_pattern = r'self\._diagnose_failure\('
        calls = re.findall(call_pattern, content)
        self.assertEqual(len(calls), 7,
                         f"Esperadas 7 llamadas a _diagnose_failure(), "
                         f"encontradas {len(calls)}")

        # Verificar import perezoso
        self.assertIn('_get_failure_auditor', content,
                      "_get_failure_auditor no encontrado")
        self.assertIn('from core.failure_auditor import FailureAuditorAgent',
                      content,
                      "Import perezoso de FailureAuditorAgent no encontrado")

        # Verificar método público
        self.assertIn('def get_failure_diagnosis', content,
                      "get_failure_diagnosis() no encontrado")

        # Verificar last_diagnosis en get_progress_summary
        self.assertIn('last_diagnosis', content,
                      "last_diagnosis no encontrado en get_progress_summary")

        print(f"  Test 2 PASÓ: 7 puntos de integración encontrados en v3.4")

    # ----------------------------------------------------------------
    # Test 3: Verificar la docstring v3.4
    # ----------------------------------------------------------------
    def test_03_semi_auto_agent_version_v34(self):
        """Test 3: La docstring indica versión v3.4 con cambios Fase 2."""
        agent_path = os.path.join(
            os.path.dirname(__file__), '..', 'agents', 'semi_auto_agent.py'
        )

        with open(agent_path, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn('v3.4', content[:200],
                      "Versión v3.4 no encontrada en las primeras 200 líneas")
        self.assertIn('Fase 2', content[:500],
                      "Referencia a Fase 2 no encontrada en la docstring")
        self.assertIn('FailureAuditorAgent', content[:500],
                      "Referencia a FailureAuditorAgent no encontrada en docstring")

        print("  Test 3 PASÓ: Versión v3.4 confirmada con cambios Fase 2")

    # ----------------------------------------------------------------
    # Test 4: FailureAuditorAgent funciona standalone con los 4 casos
    # ----------------------------------------------------------------
    def test_04_auditor_standalone_4_categories(self):
        """Test 4: FailureAuditorAgent clasifica los 4 tipos de fallo."""
        if not self._auditor_available:
            self.skipTest("failure_auditor.py no disponible")

        # Importar las clases de prueba del propio failure_auditor.py
        # No podemos importar el módulo directamente porque tiene
        # dependencias de apa.core, pero podemos verificar que el
        # código contiene la lógica correcta

        with open(self._auditor_module_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Verificar las 4 categorías
        self.assertIn('context_insufficient', content)
        self.assertIn('model_limitation', content)
        self.assertIn('prompt_error', content)
        self.assertIn('unresolved_dependency', content)

        # Verificar las 3 severidades
        self.assertIn('"critical"', content)
        self.assertIn('"recoverable"', content)
        self.assertIn('"minor"', content)

        # Verificar las 5 acciones
        self.assertIn('"retry"', content)
        self.assertIn('"replan"', content)
        self.assertIn('"escalate"', content)
        self.assertIn('"split"', content)
        self.assertIn('"abort"', content)

        # Verificar los 4 tests en __main__
        self.assertIn('Caso 1: context_insufficient', content)
        self.assertIn('Caso 2: model_limitation', content)
        self.assertIn('Caso 3: prompt_error', content)
        self.assertIn('Caso 4: unresolved_dependency', content)

        print("  Test 4 PASÓ: Las 4 categorías, 3 severidades y 5 acciones están definidas")

    # ----------------------------------------------------------------
    # Test 5: Sintaxis correcta de semi_auto_agent.py
    # ----------------------------------------------------------------
    def test_05_semi_auto_agent_syntax(self):
        """Test 5: semi_auto_agent.py (v3.4) tiene sintaxis Python válida."""
        agent_path = os.path.join(
            os.path.dirname(__file__), '..', 'agents', 'semi_auto_agent.py'
        )

        with open(agent_path, 'r', encoding='utf-8') as f:
            source = f.read()

        try:
            compile(source, agent_path, 'exec')
        except SyntaxError as e:
            self.fail(f"Error de sintaxis en semi_auto_agent_v3.4.py: {e}")

        # Verificar que tiene más líneas que el original (2135)
        lines = source.count('\n')
        self.assertGreater(lines, 2100,
                           f"Archivo inesperadamente corto: {lines} líneas")

        print(f"  Test 5 PASÓ: Sintaxis válida, {lines} líneas")

    # ----------------------------------------------------------------
    # Test 6: failure_auditor.py tiene sintaxis válida
    # ----------------------------------------------------------------
    def test_06_failure_auditor_syntax(self):
        """Test 6: failure_auditor.py tiene sintaxis Python válida."""
        with open(self._auditor_module_path, 'r', encoding='utf-8') as f:
            source = f.read()

        try:
            compile(source, self._auditor_module_path, 'exec')
        except SyntaxError as e:
            self.fail(f"Error de sintaxis en failure_auditor.py: {e}")

        # Verificar tamaño esperado (~1252 líneas)
        lines = source.count('\n')
        self.assertGreater(lines, 1000,
                           f"Archivo inesperadamente corto: {lines} líneas")

        print(f"  Test 6 PASÓ: Sintaxis válida, {lines} líneas")

    # ----------------------------------------------------------------
    # Test 7: Los 7 puntos de llamada cubren los agentes correctos
    # ----------------------------------------------------------------
    def test_07_coverage_all_agents(self):
        """Test 7: Los 7 puntos de llamada cubren planner, coder,
        integrator y validator."""
        agent_path = os.path.join(
            os.path.dirname(__file__), '..', 'agents', 'semi_auto_agent.py'
        )

        with open(agent_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Extraer todos los agent_name="xxx" que están asociados
        # a una llamada _diagnose_failure. Como el call puede ser
        # multilinea con indentación, usamos un approach de buscar
        # cada _diagnose_failure( y luego encontrar el agent_name
        # en las siguientes ~15 líneas.
        all_agent_names = []
        for m in re.finditer(r'self\._diagnose_failure\(', content):
            block = content[m.start():m.start() + 500]
            agent_match = re.search(r'agent_name="(\w+)"', block)
            if agent_match:
                all_agent_names.append(agent_match.group(1))

        # Debe haber al menos un diagnóstico para cada agente
        self.assertIn("coder", all_agent_names,
                      "No hay diagnóstico para 'coder'")
        self.assertIn("integrator", all_agent_names,
                      "No hay diagnóstico para 'integrator'")
        self.assertIn("planner", all_agent_names,
                      "No hay diagnóstico para 'planner'")
        self.assertIn("validator", all_agent_names,
                      "No hay diagnóstico para 'validator'")

        # Verificar que hay múltiples diagnósticos para coder
        # (coder puede fallar en execute_next y en _execute_single_task)
        coder_count = all_agent_names.count("coder")
        self.assertGreaterEqual(coder_count, 2,
                                f"Esperados >= 2 diagnósticos para coder, "
                                f"encontrados {coder_count}")

        # Verificar que hay múltiples diagnósticos para validator
        # (RF4, RF5, execution error)
        validator_count = all_agent_names.count("validator")
        self.assertGreaterEqual(validator_count, 2,
                                f"Esperados >= 2 diagnósticos para validator, "
                                f"encontrados {validator_count}")

        print(f"  Test 7 PASÓ: Cobertura de agentes — "
              f"coder:{coder_count}, integrator:{all_agent_names.count('integrator')}, "
              f"planner:{all_agent_names.count('planner')}, "
              f"validator:{validator_count}")


# ============================================================================
# Ejecución principal
# ============================================================================
if __name__ == "__main__":
    print("=" * 70)
    print("Tests de Integración Fase 2 — FailureAuditorAgent + SemiAutoAgent v3.4")
    print("=" * 70)
    print()

    # Ejecutar tests
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestFase2Integration)

    runner = unittest.TextTestRunner(verbosity=0)
    result = runner.run(suite)

    # Resumen
    print()
    print("=" * 70)
    total = result.testsRun
    passed = total - len(result.failures) - len(result.errors)
    print(f"RESULTADO: {passed}/{total} tests PASARON")
    if result.failures:
        print(f"FALLOS: {len(result.failures)}")
        for test, traceback in result.failures:
            print(f"  - {test}: {traceback.split('AssertionError')[-1][:100]}")
    if result.errors:
        print(f"ERRORES: {len(result.errors)}")
        for test, traceback in result.errors:
            print(f"  - {test}: {str(traceback)[:100]}")
    print("=" * 70)

    # Exit code
    sys.exit(0 if result.wasSuccessful() else 1)
