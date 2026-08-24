# apa/tests/test_fase4_agent_dashboard.py
# Fase 4 — Dashboard de agentes (UX2)
#
# Tests que validan:
#   1. EVT_AGENT_* constantes existen y tienen valores correctos
#   2. _emit_agent_event() emite eventos con datos correctos
#   3. notification_ui_bridge maneja eventos agent:* correctamente
#   4. app.py contiene la seccion de agentes con tarjetas
#   5. CSS contiene @keyframes agent-pulse y estilos de tarjetas
#   6. JS consume eventos SSE y actualiza tarjetas
#   7. Integration: flujo completo de eventos en SemiAutoAgent
#
# USO:
#   cd C:\Python\Proyectos\APA
#   python -m apa.tests.test_fase4_agent_dashboard
#
# ARCHIVO: test_fase4_agent_dashboard.py
# DESTINO: apa/tests/test_fase4_agent_dashboard.py

import sys
import os
import unittest
import time
import threading

# ============================================================================
# PATH SETUP — funciona desde apa/tests/ y desde raiz del proyecto
# ============================================================================
_here = os.path.dirname(os.path.abspath(__file__))
_apa_dir = os.path.dirname(_here)         # apa/
_project_dir = os.path.dirname(_apa_dir) # APA/ (o raiz del proyecto)
for _p in (_here, _apa_dir, _project_dir):
    if _p not in sys.path:
        sys.path.insert(0, _p)


class TestNotificationsConstants(unittest.TestCase):
    """Test 1: EVT_AGENT_* constantes en notifications.py."""

    def test_01_evt_agent_started_value(self):
        from core.notifications import EVT_AGENT_STARTED
        self.assertEqual(EVT_AGENT_STARTED, "agent:started")

    def test_02_evt_agent_progress_value(self):
        from core.notifications import EVT_AGENT_PROGRESS
        self.assertEqual(EVT_AGENT_PROGRESS, "agent:progress")

    def test_03_evt_agent_done_value(self):
        from core.notifications import EVT_AGENT_DONE
        self.assertEqual(EVT_AGENT_DONE, "agent:done")

    def test_04_evt_agent_failed_value(self):
        from core.notifications import EVT_AGENT_FAILED
        self.assertEqual(EVT_AGENT_FAILED, "agent:failed")

    def test_05_all_in_important_events(self):
        from core.notifications import (
            EVT_AGENT_STARTED, EVT_AGENT_PROGRESS,
            EVT_AGENT_DONE, EVT_AGENT_FAILED,
        )
        # Verify they're in the important_events set of _default_log_callback
        # by checking that notify() dispatches them
        collected = []
        def cb(evt_type, msg, data):
            collected.append(evt_type)
        from core.notifications import register_callback, unregister_callback, clear_callbacks
        clear_callbacks()
        register_callback(cb)
        from core.notifications import notify
        for evt in [EVT_AGENT_STARTED, EVT_AGENT_PROGRESS, EVT_AGENT_DONE, EVT_AGENT_FAILED]:
            notify(evt, "test", {})
        self.assertEqual(len(collected), 4)
        unregister_callback(cb)


class TestUIBridgeAgentEvents(unittest.TestCase):
    """Test 2: notification_ui_bridge maneja eventos agent:* correctamente."""

    def test_10_agent_prefix_color(self):
        from core.notification_ui_bridge import EVENT_PREFIX_COLOR_MAP, get_event_color
        self.assertIn('agent', EVENT_PREFIX_COLOR_MAP)
        self.assertEqual(EVENT_PREFIX_COLOR_MAP['agent'], '#06b6d4')
        # get_event_color should use specific map first
        from core.notifications import EVT_AGENT_STARTED, EVT_AGENT_DONE, EVT_AGENT_FAILED
        self.assertEqual(get_event_color(EVT_AGENT_STARTED), '#06b6d4')
        self.assertEqual(get_event_color(EVT_AGENT_DONE), '#22c55e')
        self.assertEqual(get_event_color(EVT_AGENT_FAILED), '#ef4444')

    def test_11_agent_prefix_label(self):
        from core.notification_ui_bridge import EVENT_LABEL_MAP, get_event_label
        self.assertIn('agent', EVENT_LABEL_MAP)
        self.assertEqual(EVENT_LABEL_MAP['agent'], 'Agente')
        from core.notifications import EVT_AGENT_STARTED
        self.assertEqual(get_event_label(EVT_AGENT_STARTED), 'Agente')

    def test_12_agent_in_event_types_list(self):
        from core.notification_ui_bridge import EVENT_TYPES_LIST
        from core.notifications import (
            EVT_AGENT_STARTED, EVT_AGENT_PROGRESS,
            EVT_AGENT_DONE, EVT_AGENT_FAILED,
        )
        self.assertIn(EVT_AGENT_STARTED, EVENT_TYPES_LIST)
        self.assertIn(EVT_AGENT_PROGRESS, EVENT_TYPES_LIST)
        self.assertIn(EVT_AGENT_DONE, EVENT_TYPES_LIST)
        self.assertIn(EVT_AGENT_FAILED, EVENT_TYPES_LIST)
        # Total should be 25 (21 original + 4 agent)
        self.assertEqual(len(EVENT_TYPES_LIST), 25)

    def test_13_format_event_agent_started(self):
        from core.notification_ui_bridge import format_event
        from core.notifications import EVT_AGENT_STARTED
        evt = {
            'type': EVT_AGENT_STARTED,
            'message': 'Planificador iniciado (T1)',
            'data': {'agent': 'planner', 'task': 'T1', 'model': 'claude-3'},
            'timestamp': time.time(),
        }
        fmt = format_event(evt)
        self.assertEqual(fmt['color'], '#06b6d4')
        self.assertEqual(fmt['category'], 'Agente')
        self.assertEqual(fmt['prefix'], 'agent')
        self.assertIn('time_str', fmt)
        self.assertIsNotNone(fmt['time_str'])

    def test_14_format_event_agent_failed(self):
        from core.notification_ui_bridge import format_event
        from core.notifications import EVT_AGENT_FAILED
        evt = {
            'type': EVT_AGENT_FAILED,
            'message': 'Codificador fallido (T2)',
            'data': {'agent': 'coder', 'task': 'T2', 'error': 'Timeout'},
            'timestamp': time.time(),
        }
        fmt = format_event(evt)
        self.assertEqual(fmt['color'], '#ef4444')
        self.assertEqual(fmt['category'], 'Agente')

    def test_15_specific_color_overrides_prefix(self):
        from core.notification_ui_bridge import EVENT_SPECIFIC_COLOR_MAP
        from core.notifications import EVT_AGENT_STARTED, EVT_AGENT_DONE, EVT_AGENT_FAILED, EVT_AGENT_PROGRESS
        # Each agent event has a specific color
        self.assertEqual(EVENT_SPECIFIC_COLOR_MAP[EVT_AGENT_STARTED], '#06b6d4')
        self.assertEqual(EVENT_SPECIFIC_COLOR_MAP[EVT_AGENT_DONE], '#22c55e')
        self.assertEqual(EVENT_SPECIFIC_COLOR_MAP[EVT_AGENT_FAILED], '#ef4444')
        self.assertEqual(EVENT_SPECIFIC_COLOR_MAP[EVT_AGENT_PROGRESS], '#8b5cf6')


class TestEmitAgentEvent(unittest.TestCase):
    """Test 3: _emit_agent_event() emite eventos con datos correctos."""

    def setUp(self):
        """Limpiar callbacks antes de cada test."""
        from core.notifications import clear_callbacks
        clear_callbacks()
        self.collected = []
        self._cb = lambda evt_type, msg, data: self.collected.append({
            'type': evt_type, 'message': msg, 'data': data
        })
        from core.notifications import register_callback
        register_callback(self._cb)

    def tearDown(self):
        from core.notifications import unregister_callback, register_callback
        if self._cb:
            try:
                unregister_callback(self._cb)
            except Exception:
                pass
        # Re-register default log callback
        try:
            from core.notifications import _default_log_callback
            register_callback(_default_log_callback)
        except Exception:
            pass

    def test_20_emit_started_planner(self):
        from agents.semi_auto_agent import _emit_agent_event
        _emit_agent_event("agent:started", "planner", "T1", "claude-3")
        agent_events = [e for e in self.collected if e['type'].startswith('agent:')]
        self.assertEqual(len(agent_events), 1)
        evt = agent_events[0]
        self.assertEqual(evt['type'], 'agent:started')
        self.assertEqual(evt['data']['agent'], 'planner')
        self.assertEqual(evt['data']['task'], 'T1')
        self.assertEqual(evt['data']['model'], 'claude-3')
        self.assertIn('Planificador', evt['message'])
        self.assertIn('iniciado', evt['message'])

    def test_21_emit_done_coder(self):
        from agents.semi_auto_agent import _emit_agent_event
        _emit_agent_event("agent:done", "coder", "T2", "gpt-4o",
                          extra={"tokens_used": 1500, "latency_ms": 3200})
        agent_events = [e for e in self.collected if e['type'].startswith('agent:')]
        self.assertEqual(len(agent_events), 1)
        evt = agent_events[0]
        self.assertEqual(evt['type'], 'agent:done')
        self.assertEqual(evt['data']['agent'], 'coder')
        self.assertEqual(evt['data']['tokens_used'], 1500)
        self.assertEqual(evt['data']['latency_ms'], 3200)
        self.assertIn('Codificador', evt['message'])
        self.assertIn('completado', evt['message'])

    def test_22_emit_failed_integrator(self):
        from agents.semi_auto_agent import _emit_agent_event
        _emit_agent_event("agent:failed", "integrator", "T3", "deepseek",
                          extra={"error": "Context exceeded"})
        agent_events = [e for e in self.collected if e['type'].startswith('agent:')]
        evt = agent_events[0]
        self.assertEqual(evt['type'], 'agent:failed')
        self.assertEqual(evt['data']['agent'], 'integrator')
        self.assertEqual(evt['data']['error'], "Context exceeded")
        self.assertIn('Integrador', evt['message'])
        self.assertIn('fallido', evt['message'])

    def test_23_emit_progress(self):
        from agents.semi_auto_agent import _emit_agent_event
        _emit_agent_event("agent:progress", "coder", "T1", "claude",
                          extra={"tokens_used": 800, "pct": 40})
        agent_events = [e for e in self.collected if e['type'].startswith('agent:')]
        evt = agent_events[0]
        self.assertEqual(evt['type'], 'agent:progress')
        self.assertEqual(evt['data']['pct'], 40)
        self.assertEqual(evt['data']['tokens_used'], 800)

    def test_24_emit_without_model(self):
        from agents.semi_auto_agent import _emit_agent_event
        _emit_agent_event("agent:started", "validator", "T5")
        agent_events = [e for e in self.collected if e['type'].startswith('agent:')]
        evt = agent_events[0]
        self.assertEqual(evt['data']['model'], '')
        self.assertIn('Validador', evt['message'])

    def test_25_emit_does_not_break_on_error(self):
        """_emit_agent_event nunca lanza excepcion."""
        from agents.semi_auto_agent import _emit_agent_event
        # Pasar datos problematicos
        _emit_agent_event("agent:started", None, None, None)
        # No deberia haber lanzado error
        self.assertTrue(True)

    def test_26_emit_thread_safety(self):
        """_emit_agent_event es thread-safe (usado desde hilos del pipeline)."""
        from agents.semi_auto_agent import _emit_agent_event
        errors = []

        def emit_many(agent_id):
            try:
                for i in range(10):
                    _emit_agent_event("agent:started", f"agent_{agent_id}", f"T{i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=emit_many, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(errors), 0, f"Thread safety errors: {errors}")
        self.assertEqual(len(self.collected), 50)


class TestAppPyAgentDashboard(unittest.TestCase):
    """Test 4: app.py contiene la seccion de agentes con tarjetas."""

    def test_30_agentes_tab_exists(self):
        """La pestana 'Agentes' existe en el HTML."""
        app_path = os.path.join(_apa_dir, 'interface', 'app.py')
        self.assertTrue(os.path.exists(app_path), f"No existe: {app_path}")
        with open(app_path, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertIn('data-tab="agentes"', content)

    def test_31_agentes_section_exists(self):
        """La seccion agentes-section existe en el HTML."""
        app_path = os.path.join(_apa_dir, 'interface', 'app.py')
        with open(app_path, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertIn('id="agentes-section"', content)

    def test_32_four_agent_cards_exist(self):
        """Existen 4 tarjetas de agente: planner, coder, integrator, validator."""
        app_path = os.path.join(_apa_dir, 'interface', 'app.py')
        with open(app_path, 'r', encoding='utf-8') as f:
            content = f.read()
        for agent in ('planner', 'coder', 'integrator', 'validator'):
            self.assertIn(f'id="card-{agent}"', content,
                          f"Falta tarjeta para agente: {agent}")
            self.assertIn(f'id="status-{agent}"', content)
            self.assertIn(f'id="model-{agent}"', content)

    def test_33_agent_js_functions_exist(self):
        """Las funciones JS del dashboard de agentes existen."""
        app_path = os.path.join(_apa_dir, 'interface', 'app.py')
        with open(app_path, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertIn('handleAgentEvent', content)
        self.assertIn('resetAgentCards', content)
        self.assertIn('initNotificationsWithAgents', content)
        self.assertIn('AGENT_NAMES', content)

    def test_34_agent_js_consumes_sse(self):
        """El JS consume eventos SSE agent:*."""
        app_path = os.path.join(_apa_dir, 'interface', 'app.py')
        with open(app_path, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertIn("evt.type.startsWith('agent:')", content)

    def test_35_agent_js_updates_progress_bar(self):
        """El JS actualiza la barra de progreso de las tarjetas."""
        app_path = os.path.join(_apa_dir, 'interface', 'app.py')
        with open(app_path, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertIn('pbarEl.style.width', content)


class TestCSSAgentCards(unittest.TestCase):
    """Test 5: CSS contiene @keyframes agent-pulse y estilos de tarjetas."""

    def test_40_agent_pulse_keyframe(self):
        """@keyframes agent-pulse existe en el CSS."""
        app_path = os.path.join(_apa_dir, 'interface', 'app.py')
        with open(app_path, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertIn('@keyframes agent-pulse', content)

    def test_41_agent_dot_blink_keyframe(self):
        """@keyframes agent-dot-blink existe para icono activo."""
        app_path = os.path.join(_apa_dir, 'interface', 'app.py')
        with open(app_path, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertIn('@keyframes agent-dot-blink', content)

    def test_42_agent_card_classes(self):
        """Existen clases CSS para estados de tarjeta: active, done, failed, idle."""
        app_path = os.path.join(_apa_dir, 'interface', 'app.py')
        with open(app_path, 'r', encoding='utf-8') as f:
            content = f.read()
        for state in ('active', 'done', 'failed', 'idle'):
            self.assertIn(f'.agent-card.{state}', content,
                          f"Falta clase CSS .agent-card.{state}")

    def test_43_agent_active_uses_cyan(self):
        """Tarjeta activa usa color cyan #06b6d4."""
        app_path = os.path.join(_apa_dir, 'interface', 'app.py')
        with open(app_path, 'r', encoding='utf-8') as f:
            content = f.read()
        # Cyan border for active state
        self.assertIn('border-color: #06b6d4', content)

    def test_44_agent_done_uses_green(self):
        """Tarjeta completada usa color verde."""
        app_path = os.path.join(_apa_dir, 'interface', 'app.py')
        with open(app_path, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertIn('.agent-card.done .agent-card-status', content)
        self.assertIn('--green', content)

    def test_45_agent_failed_uses_red(self):
        """Tarjeta fallida usa color rojo."""
        app_path = os.path.join(_apa_dir, 'interface', 'app.py')
        with open(app_path, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertIn('.agent-card.failed .agent-card-status', content)
        self.assertIn('--red', content)

    def test_46_agent_grid_layout(self):
        """Tarjetas usan grid responsive."""
        app_path = os.path.join(_apa_dir, 'interface', 'app.py')
        with open(app_path, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertIn('#agent-cards-container', content)
        self.assertIn('grid-template-columns', content)
        self.assertIn('auto-fit', content)


class TestIntegrationPipelineEvents(unittest.TestCase):
    """Test 6: Integration — flujo completo de eventos en SemiAutoAgent.

    Estos tests verifican que los eventos agent:* se emiten en secuencia
    correcta durante una ejecucion simulada del pipeline.
    """

    def setUp(self):
        from core.notifications import clear_callbacks
        clear_callbacks()
        self.collected = []
        self._cb = lambda evt_type, msg, data: self.collected.append({
            'type': evt_type, 'message': msg, 'data': data
        })
        from core.notifications import register_callback
        register_callback(self._cb)

    def tearDown(self):
        from core.notifications import unregister_callback, register_callback
        if self._cb:
            try:
                unregister_callback(self._cb)
            except Exception:
                pass
        try:
            from core.notifications import _default_log_callback
            register_callback(_default_log_callback)
        except Exception:
            pass

    def test_50_emit_sequence_for_coder_phase(self):
        """Secuencia de eventos para fase de codificacion: started -> done/failed."""
        from agents.semi_auto_agent import _emit_agent_event
        # Simular secuencia del pipeline
        _emit_agent_event("agent:started", "coder", "T1", "claude-3")
        _emit_agent_event("agent:done", "coder", "T1", "claude-3",
                          extra={"tokens_used": 1200, "latency_ms": 2500})

        agent_events = [e for e in self.collected if e['type'].startswith('agent:')]
        self.assertEqual(len(agent_events), 2)
        self.assertEqual(agent_events[0]['type'], 'agent:started')
        self.assertEqual(agent_events[0]['data']['agent'], 'coder')
        self.assertEqual(agent_events[1]['type'], 'agent:done')
        self.assertEqual(agent_events[1]['data']['agent'], 'coder')
        self.assertEqual(agent_events[1]['data']['tokens_used'], 1200)

    def test_51_full_pipeline_event_sequence(self):
        """Secuencia completa: planner -> coder -> integrator -> validator."""
        from agents.semi_auto_agent import _emit_agent_event
        phases = [
            ("agent:started", "planner", ""),
            ("agent:done", "planner", ""),
            ("agent:started", "coder", "T1"),
            ("agent:done", "coder", "T1"),
            ("agent:started", "integrator", "T1"),
            ("agent:done", "integrator", "T1"),
            ("agent:started", "validator", "T1"),
            ("agent:done", "validator", "T1"),
        ]
        for evt_type, agent, task in phases:
            _emit_agent_event(evt_type, agent, task)

        agent_events = [e for e in self.collected if e['type'].startswith('agent:')]
        self.assertEqual(len(agent_events), 8)

        # Verificar orden
        self.assertEqual(agent_events[0]['data']['agent'], 'planner')
        self.assertEqual(agent_events[0]['type'], 'agent:started')
        self.assertEqual(agent_events[1]['type'], 'agent:done')
        self.assertEqual(agent_events[2]['data']['agent'], 'coder')
        self.assertEqual(agent_events[4]['data']['agent'], 'integrator')
        self.assertEqual(agent_events[6]['data']['agent'], 'validator')
        self.assertEqual(agent_events[7]['type'], 'agent:done')

    def test_52_failure_in_coder_generates_failed_event(self):
        """Fallo en codificador genera agent:failed, no agent:done."""
        from agents.semi_auto_agent import _emit_agent_event
        _emit_agent_event("agent:started", "coder", "T3", "bad-model")
        _emit_agent_event("agent:failed", "coder", "T3", "bad-model",
                          extra={"error": "Rate limited"})

        agent_events = [e for e in self.collected if e['type'].startswith('agent:')]
        self.assertEqual(len(agent_events), 2)
        self.assertEqual(agent_events[0]['type'], 'agent:started')
        self.assertEqual(agent_events[1]['type'], 'agent:failed')
        self.assertEqual(agent_events[1]['data']['error'], 'Rate limited')
        # No debe haber agent:done
        done_events = [e for e in agent_events if e['type'] == 'agent:done']
        self.assertEqual(len(done_events), 0)

    def test_53_events_have_required_fields(self):
        """Cada evento agent:* tiene campos requeridos: agent, task, model."""
        from agents.semi_auto_agent import _emit_agent_event
        _emit_agent_event("agent:started", "integrator", "T5", "deepseek",
                          extra={"tokens_used": 3000, "pct": 60})

        agent_events = [e for e in self.collected if e['type'].startswith('agent:')]
        evt = agent_events[-1]
        self.assertIn('agent', evt['data'])
        self.assertIn('task', evt['data'])
        self.assertIn('model', evt['data'])
        self.assertEqual(evt['data']['agent'], 'integrator')
        self.assertEqual(evt['data']['task'], 'T5')
        self.assertEqual(evt['data']['model'], 'deepseek')

    def test_54_notify_buffer_stores_agent_events(self):
        """Los eventos agent:* se almacenan en el buffer de notifications."""
        from core.notifications import notify, get_recent_events
        # Recordar cuantos eventos agent hay antes del test
        from core.notifications import get_recent_events as _get_before
        before = [e for e in _get_before(300) if e['type'].startswith('agent:')]

        notify("agent:started", "Planificador iniciado",
               {"agent": "planner", "task": "", "model": "claude"})
        notify("agent:done", "Planificador completado",
               {"agent": "planner", "task": "", "model": "claude", "pct": 100})

        recent = get_recent_events(300)
        agent_events = [e for e in recent if e['type'].startswith('agent:')]
        # Debe haber al least 2 mas que antes
        new_agent_events = agent_events[len(before):]
        self.assertEqual(len(new_agent_events), 2)
        self.assertEqual(new_agent_events[0]['type'], 'agent:started')
        self.assertEqual(new_agent_events[1]['type'], 'agent:done')

    def test_55_multiple_agents_can_be_active_simultaneously(self):
        """Multiples agentes pueden emitir eventos concurrentemente."""
        from agents.semi_auto_agent import _emit_agent_event
        # Simular planner done + coder started (solapamiento en run())
        _emit_agent_event("agent:done", "planner", "")
        _emit_agent_event("agent:started", "coder", "T1")

        agent_events = [e for e in self.collected if e['type'].startswith('agent:')]
        self.assertEqual(len(agent_events), 2)
        self.assertEqual(agent_events[0]['data']['agent'], 'planner')
        self.assertEqual(agent_events[1]['data']['agent'], 'coder')

    def test_56_events_include_task_description(self):
        """Los eventos agent:* incluyen task_description cuando se proporciona."""
        from agents.semi_auto_agent import _emit_agent_event
        _emit_agent_event("agent:started", "coder", "T1", "claude-3",
                          extra={"task_description": "T1: Generando codigo (main.py)"})

        agent_events = [e for e in self.collected if e['type'].startswith('agent:')]
        evt = agent_events[-1]
        self.assertIn('task_description', evt['data'])
        self.assertEqual(evt['data']['task_description'], 'T1: Generando codigo (main.py)')

    def test_57_events_include_context_metrics(self):
        """Los eventos agent:* incluyen context_pct y context_used/context_max."""
        from agents.semi_auto_agent import _emit_agent_event
        _emit_agent_event("agent:done", "coder", "T1", "gpt-4o",
                          extra={"tokens_used": 2000,
                                 "latency_ms": 1500,
                                 "context_used": 3000,
                                 "context_max": 8000,
                                 "context_pct": 38})

        agent_events = [e for e in self.collected if e['type'].startswith('agent:')]
        evt = agent_events[-1]
        self.assertEqual(evt['data']['context_used'], 3000)
        self.assertEqual(evt['data']['context_max'], 8000)
        self.assertEqual(evt['data']['context_pct'], 38)

    def test_58_planner_events_have_task_description(self):
        """Los eventos del planificador incluyen task_description."""
        from agents.semi_auto_agent import _emit_agent_event
        _emit_agent_event("agent:started", "planner", "",
                          extra={"task_description": "Generando plan de tareas..."})

        agent_events = [e for e in self.collected if e['type'].startswith('agent:')]
        evt = agent_events[-1]
        self.assertEqual(evt['data']['task_description'], "Generando plan de tareas...")

    def test_59_validator_events_have_task_description(self):
        """Los eventos del validador incluyen task_description."""
        from agents.semi_auto_agent import _emit_agent_event
        _emit_agent_event("agent:done", "validator", "T1",
                          extra={"pct": 100,
                                 "task_description": "T1: Validacion OK"})

        agent_events = [e for e in self.collected if e['type'].startswith('agent:')]
        evt = agent_events[-1]
        self.assertEqual(evt['data']['task_description'], "T1: Validacion OK")
        self.assertEqual(evt['data']['pct'], 100)


class TestAppPyAgentDashboardUX2Plus(unittest.TestCase):
    """Test 7: UX2+ — task description, context metrics, dynamic visibility."""

    def test_60_task_description_field_exists(self):
        """Cada tarjeta de agente tiene un campo task-description."""
        app_path = os.path.join(_apa_dir, 'interface', 'app.py')
        with open(app_path, 'r', encoding='utf-8') as f:
            content = f.read()
        for agent in ('planner', 'coder', 'integrator', 'validator'):
            self.assertIn(f'id="task-{agent}"', content,
                          f"Falta campo task para agente: {agent}")

    def test_61_context_metrics_elements_exist(self):
        """Las tarjetas de planner/coder/integrator tienen fila de contexto."""
        app_path = os.path.join(_apa_dir, 'interface', 'app.py')
        with open(app_path, 'r', encoding='utf-8') as f:
            content = f.read()
        for agent in ('planner', 'coder', 'integrator'):
            self.assertIn(f'id="ctx-row-{agent}"', content,
                          f"Falta ctx-row para agente: {agent}")
            self.assertIn(f'id="ctx-fill-{agent}"', content,
                          f"Falta ctx-fill para agente: {agent}")
            self.assertIn(f'id="ctx-pct-{agent}"', content,
                          f"Falta ctx-pct para agente: {agent}")

    def test_62_css_task_description_style(self):
        """CSS tiene estilo .agent-card-task."""
        app_path = os.path.join(_apa_dir, 'interface', 'app.py')
        with open(app_path, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertIn('.agent-card-task', content)

    def test_63_css_context_bar_style(self):
        """CSS tiene estilos de barra de contexto (.agent-context-fill)."""
        app_path = os.path.join(_apa_dir, 'interface', 'app.py')
        with open(app_path, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertIn('.agent-context-bar', content)
        self.assertIn('.agent-context-fill', content)

    def test_64_css_context_warn_danger(self):
        """CSS tiene colores de advertencia y peligro para contexto alto."""
        app_path = os.path.join(_apa_dir, 'interface', 'app.py')
        with open(app_path, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertIn('.agent-context-fill.warn', content)
        self.assertIn('.agent-context-fill.danger', content)

    def test_65_css_hidden_card_class(self):
        """CSS tiene clase .agent-card-hidden para ocultar tarjetas inactivas."""
        app_path = os.path.join(_apa_dir, 'interface', 'app.py')
        with open(app_path, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertIn('.agent-card.agent-card-hidden', content)

    def test_66_cards_start_hidden(self):
        """Las tarjetas de agente inician con clase agent-card-hidden."""
        app_path = os.path.join(_apa_dir, 'interface', 'app.py')
        with open(app_path, 'r', encoding='utf-8') as f:
            content = f.read()
        for agent in ('planner', 'coder', 'integrator', 'validator'):
            # Verificar que la tarjeta tiene agent-card-hidden en su apertura
            self.assertIn(f'agent-card-hidden" id="card-{agent}"', content,
                          f"Tarjeta {agent} no inicia oculta")

    def test_67_js_updates_task_description(self):
        """JS handleAgentEvent actualiza el campo task_description."""
        app_path = os.path.join(_apa_dir, 'interface', 'app.py')
        with open(app_path, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertIn('task_description', content)
        self.assertIn('taskEl.textContent', content)

    def test_68_js_updates_context_metrics(self):
        """JS handleAgentEvent actualiza las metricas de contexto."""
        app_path = os.path.join(_apa_dir, 'interface', 'app.py')
        with open(app_path, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertIn('context_pct', content)
        self.assertIn('ctxFill.style.width', content)
        self.assertIn('ctxPct.textContent', content)

    def test_69_js_dynamic_card_visibility(self):
        """JS muestra tarjetas cuando el agente se activa (agent-card-hidden)."""
        app_path = os.path.join(_apa_dir, 'interface', 'app.py')
        with open(app_path, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertIn('agent-card-hidden', content)
        self.assertIn('classList.remove', content)
        self.assertIn('_agentSeen', content)

    def test_70_reset_clears_task_and_context(self):
        """resetAgentCards limpia task description y oculta contexto."""
        app_path = os.path.join(_apa_dir, 'interface', 'app.py')
        with open(app_path, 'r', encoding='utf-8') as f:
            content = f.read()
        # Verificar que resetAgentCards limpia los campos nuevos
        self.assertIn('taskEl.textContent', content)
        self.assertIn("ctxRow.style.display = 'none'", content)


# ============================================================================
# RUN TESTS
# ============================================================================
if __name__ == '__main__':
    print("\n" + "=" * 65)
    print("  FASE 4 — DASHBOARD DE AGENTES (UX2)")
    print("  Tests de validación completa")
    print("=" * 65)

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Cargar todos los test classes
    suite.addTests(loader.loadTestsFromTestCase(TestNotificationsConstants))
    suite.addTests(loader.loadTestsFromTestCase(TestUIBridgeAgentEvents))
    suite.addTests(loader.loadTestsFromTestCase(TestEmitAgentEvent))
    suite.addTests(loader.loadTestsFromTestCase(TestAppPyAgentDashboard))
    suite.addTests(loader.loadTestsFromTestCase(TestCSSAgentCards))
    suite.addTests(loader.loadTestsFromTestCase(TestIntegrationPipelineEvents))
    suite.addTests(loader.loadTestsFromTestCase(TestAppPyAgentDashboardUX2Plus))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    total = result.testsRun
    passed = total - len(result.failures) - len(result.errors)
    print("\n" + "=" * 65)
    print(f"  RESULTADO: {passed}/{total} tests PASADOS")
    if result.failures:
        print(f"  FALLIDOS: {len(result.failures)}")
        for test, tb in result.failures:
            print(f"    - {test}: {tb.splitlines()[-1]}")
    if result.errors:
        print(f"  ERRORES: {len(result.errors)}")
        for test, tb in result.errors:
            print(f"    - {test}: {tb.splitlines()[-1]}")
    print("=" * 65)

    sys.exit(0 if result.wasSuccessful() else 1)
