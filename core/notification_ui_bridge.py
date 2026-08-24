# apa/core/notification_ui_bridge.py
# v3.1 — MOTOR UNICO DE RENDERIZADO DE NOTIFICACIONES
#
# v3.1: Eliminadas 16 constantes EVT_* muertas (health/arena/pool).
#       Refs a pool/arena/providers eliminadas de:
#         - EVENT_SPECIFIC_COLOR_MAP
#         - EVENT_TYPES_LIST
#         - SUMMARY_LABELS_CONFIG
#         - NOTIF_SECTION_HTML (panel resumen simplificado)
#         - NOTIF_JS renderNotifSummary (solo modelos + agentes)
#         - get_summary_display_data (solo modelos + agentes)
#         - __main__ tests
#       Agregado EVT_EMERGENCY_MODE al color map.
#
# Este modulo es el UNICO lugar donde se define como se ven las notificaciones.
# Tanto app.py (FastAPI/web) como ensamblador_gui.py (tkinter) consumen
# este mismo codigo. Cero logica de render duplicada.
#
# Lo que contiene este motor:
#   1) Datos: format_event(), get_full_summary(), get_event_color(), etc.
#   2) Web:   NOTIF_CSS, NOTIF_SECTION_HTML, NOTIF_JS — todo el HTML/CSS/JS
#   3) Tkinter: render_events_to_text(), configure_tkinter_tags(),
#              get_summary_display_data()
#
# Si cambias un color, un layout o un formato AQUI, ambas interfaces
# se actualizan automaticamente.
#
# USO (app.py):
#   from core.notification_ui_bridge import (
#       NOTIF_CSS, NOTIF_TAB_BUTTON, NOTIF_SECTION_HTML, NOTIF_JS,
#       format_event, get_full_summary, get_event_summary,
#       create_bridge_callback, EVENT_TYPES_LIST,
#   )
#
# USO (ensamblador_gui.py):
#   from core.notification_ui_bridge import (
#       configure_tkinter_tags, render_events_to_text,
#       get_summary_display_data, SUMMARY_LABELS_CONFIG,
#       format_event, get_full_summary, get_event_summary,
#       create_bridge_callback, EVENT_TYPES_LIST,
#       EVENT_LABEL_MAP, EVENT_PREFIX_COLOR_MAP, EVENT_SPECIFIC_COLOR_MAP,
#   )
#
# ARCHIVO: notification_ui_bridge.py
# DESTINO: apa/core/notification_ui_bridge.py

import sys
import os
import time
from datetime import datetime
from typing import Dict, Any, List, Callable

# Tkinter: lazy import para no romper en entornos sin GUI (servidor, tests)
def _tk():
    import tkinter as _tk_mod
    return _tk_mod

# Import seguro: funciona en 3 escenarios:
#   1) Directo:  python apa/core/notification_ui_bridge.py
#   2) Modulo:   from core.notification_ui_bridge import ...  (sys.path apunta a apa/)
#   3) Absoluto: from apa.core.notification_ui_bridge import ...
_here = os.path.dirname(os.path.abspath(__file__))
_parent = os.path.dirname(_here)       # apa/
_grandparent = os.path.dirname(_parent) # APA/
for _p in (_parent, _grandparent):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# CRITICAL: Deduplication of module references.
if 'apa.core.notifications' in sys.modules and 'core.notifications' not in sys.modules:
    sys.modules['core.notifications'] = sys.modules['apa.core.notifications']
elif 'core.notifications' in sys.modules and 'apa.core.notifications' not in sys.modules:
    sys.modules['apa.core.notifications'] = sys.modules['core.notifications']
elif ('apa.core.notifications' in sys.modules and 'core.notifications' in sys.modules
      and sys.modules['apa.core.notifications'] is not sys.modules['core.notifications']):
    sys.modules['core.notifications'] = sys.modules['apa.core.notifications']

# v3.1: Solo importar EVT vivos. Los 16 EVT_HEALTH_*/EVT_ARENA_*/EVT_POOL_*
# fueron eliminados en notifications.py v2.0.
from core.notifications import (
    register_callback, unregister_callback,
    get_recent_events, get_events_by_type,
    EVT_EMERGENCY_MODE,
    EVT_SYSTEM_SHUTDOWN, EVT_SYSTEM_ERROR, EVT_SYSTEM_STARTUP,
    EVT_AGENT_STARTED, EVT_AGENT_PROGRESS, EVT_AGENT_DONE, EVT_AGENT_FAILED,
)


# ============================================================================
# CONSTANTES COMPARTIDAS — colores, etiquetas, configuracion del resumen
# ============================================================================

EVENT_PREFIX_COLOR_MAP = {
    'system': '#ef4444',    # Rojo
    'agent':  '#06b6d4',    # Cyan (Fase 4: Dashboard de agentes)
}

# v3.1: Solo EVT vivos. Eliminados todos los EVT_HEALTH_*, EVT_ARENA_*.
EVENT_SPECIFIC_COLOR_MAP = {
    EVT_EMERGENCY_MODE:      '#dc2626',   # Rojo oscuro
    EVT_SYSTEM_ERROR:        '#ef4444',
    EVT_SYSTEM_SHUTDOWN:     '#f59e0b',
    EVT_SYSTEM_STARTUP:      '#64748b',
    EVT_AGENT_STARTED:       '#06b6d4',   # Cyan
    EVT_AGENT_PROGRESS:      '#8b5cf6',   # Purpura
    EVT_AGENT_DONE:          '#22c55e',   # Verde
    EVT_AGENT_FAILED:        '#ef4444',   # Rojo
}

EVENT_LABEL_MAP = {
    'system': 'Sistema',
    'agent':  'Agente',
}

# v3.1: Solo EVT vivos (9 tipos, eliminados 16 muertos)
EVENT_TYPES_LIST = [
    EVT_EMERGENCY_MODE,
    EVT_SYSTEM_SHUTDOWN, EVT_SYSTEM_ERROR, EVT_SYSTEM_STARTUP,
    EVT_AGENT_STARTED, EVT_AGENT_PROGRESS, EVT_AGENT_DONE, EVT_AGENT_FAILED,
]

# v3.1: Simplificado — solo keys que existen en get_full_summary() via MB
SUMMARY_LABELS_CONFIG = [
    ('total',     'Total',       '#d4d4d4'),
    ('available', 'Disponibles', '#22c55e'),
]


# ============================================================================
# FUNCIONES CORE — formato, resumen, callback puente
# ============================================================================

def get_event_color(event_type: str) -> str:
    """Retorna el color hex para un tipo de evento."""
    specific = EVENT_SPECIFIC_COLOR_MAP.get(event_type)
    if specific:
        return specific
    prefix = event_type.split(':')[0] if ':' in event_type else 'system'
    return EVENT_PREFIX_COLOR_MAP.get(prefix, '#9ca3af')


def get_event_label(event_type: str) -> str:
    """Retorna la etiqueta legible para un tipo de evento."""
    prefix = event_type.split(':')[0] if ':' in event_type else 'system'
    return EVENT_LABEL_MAP.get(prefix, prefix.capitalize())


_MAX_MSG_LENGTH = 130


def _compact_list(items: list, max_show: int = 5) -> str:
    """Compacta una lista larga de strings."""
    if not items:
        return ''
    if len(items) <= max_show:
        return ', '.join(items)
    shown = ', '.join(str(x) for x in items[:max_show])
    return f"{shown} +{len(items) - max_show} mas"


def _truncate_message(msg: str, max_len: int = _MAX_MSG_LENGTH) -> str:
    """Trunca un mensaje si excede max_len caracteres."""
    if len(msg) <= max_len:
        return msg
    for delim in (')', ']', '}'):
        idx = msg.rfind(delim, 0, max_len)
        if idx > max_len * 0.5:
            return msg[:idx + 1] + '...'
    idx = msg.rfind(',', 0, max_len)
    if idx > max_len * 0.5:
        return msg[:idx] + '...'
    idx = msg.rfind('.', 0, max_len)
    if idx > max_len * 0.5:
        return msg[:idx + 1] + '..'
    idx = msg.rfind(' ', 0, max_len)
    if idx > max_len * 0.4:
        return msg[:idx] + '...'
    return msg[:max_len - 3] + '...'


def format_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """Formatea un evento crudo del event bus para presentacion UI."""
    evt_type = event.get('type', '')
    ts = event.get('timestamp', time.time())
    raw_msg = event.get('message', '')
    data = event.get('data', {})

    try:
        time_str = datetime.fromtimestamp(ts).strftime('%H:%M:%S')
    except (ValueError, OSError):
        time_str = '--:--:--'

    prefix = evt_type.split(':')[0] if ':' in evt_type else 'system'

    if 'categories' in data and isinstance(data['categories'], (list, dict)):
        cats = list(data['categories'].keys()) if isinstance(data['categories'], dict) else data['categories']
        compacted = _compact_list(sorted(cats), max_show=5)
        import re as _re
        raw_msg = _re.sub(r'\([^)]{20,}\)$', f'({compacted})', raw_msg)

    msg = _truncate_message(raw_msg)

    return {
        'type':      evt_type,
        'message':   msg,
        'data':      data,
        'timestamp': ts,
        'time_str':  time_str,
        'color':     get_event_color(evt_type),
        'category':  get_event_label(evt_type),
        'prefix':    prefix,
    }


def get_event_summary() -> Dict[str, Any]:
    """Retorna estadisticas de los eventos en el buffer."""
    events = get_recent_events(50)
    summary: Dict[str, Any] = {'total': len(events), 'by_prefix': {}}
    for e in events:
        p = e.get('type', '').split(':')[0] if ':' in e.get('type', '') else 'system'
        summary['by_prefix'][p] = summary['by_prefix'].get(p, 0) + 1
    return summary


def _dedup_module(short_name: str) -> None:
    s1 = f'core.{short_name}'
    s2 = f'apa.core.{short_name}'
    if s1 in sys.modules and s2 in sys.modules and sys.modules[s1] is not sys.modules[s2]:
        sys.modules[s1] = sys.modules[s2]
    elif s1 in sys.modules and s2 not in sys.modules:
        sys.modules[s2] = sys.modules[s1]
    elif s2 in sys.modules and s1 not in sys.modules:
        sys.modules[s1] = sys.modules[s2]


def get_full_summary() -> Dict[str, Any]:
    """Resumen de modelos disponibles via Model Broker y estado de agentes.

    v7.0: pool, providers, model_health y arena_fetcher eliminados.
    La info de modelos viene de MB. Los datos de agentes vienen de
    las notificaciones EVT_AGENT_*.
    """
    result = {
        'models': {},
        'agents': {},
    }

    # Modelos via Model Broker
    try:
        from model_broker.broker import ModelBroker
        _broker = ModelBroker()
        _models = _broker.get_models()
        result['models'] = {
            'total': len(_models),
            'available': len(_models),
        }
        if _models:
            result['models']['top_5'] = [
                {'id': m.get('id', ''), 'score': m.get('score', 0)}
                for m in _models[:5]
            ]
    except Exception:
        result['models'] = {'total': 0, 'available': 0}

    # Datos de agentes desde el buffer de notificaciones
    from core.notifications import get_events_by_type
    agent_events = {
        'started': get_events_by_type(EVT_AGENT_STARTED),
        'progress': get_events_by_type(EVT_AGENT_PROGRESS),
        'done': get_events_by_type(EVT_AGENT_DONE),
        'failed': get_events_by_type(EVT_AGENT_FAILED),
    }
    result['agents'] = {
        'started': len(agent_events['started']),
        'done': len(agent_events['done']),
        'failed': len(agent_events['failed']),
        'in_progress': len(agent_events['progress']),
    }

    return result


def create_bridge_callback(
    on_formatted_event: Callable[[Dict[str, Any]], None]
) -> Callable:
    """Crea y registra un callback puente."""
    _dedup_module('notifications')

    def _bridge_cb(event_type, message, data):
        formatted = format_event({
            'type': event_type,
            'message': message,
            'data': data or {},
            'timestamp': time.time(),
        })
        try:
            on_formatted_event(formatted)
        except Exception:
            pass

    register_callback(_bridge_cb)
    return _bridge_cb


# ============================================================================
# MOTOR DE RENDERIZADO WEB — HTML/CSS/JS
# ============================================================================
# Toda la visual de notificaciones de app.py esta aqui.
# app.py solo inyecta estas constantes en su HTML template.
# ============================================================================

NOTIF_CSS = """
/* P5: Notificaciones — motor unico notification_ui_bridge.py v3.1 */
.notif-item {
    display: flex; align-items: flex-start; gap: 10px;
    padding: 8px 12px; border-left: 3px solid #555;
    margin-bottom: 4px; border-radius: 0 4px 4px 0;
    background: var(--bg-elevated, #2d4059); transition: background 0.2s;
}
.notif-item:hover { background: var(--bg-hover, #374f6b); }
.notif-time { color: var(--text-secondary, #d4c4a0); font-family: monospace; white-space: nowrap; min-width: 65px; }
.notif-badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; color: #fff; white-space: nowrap; }
.notif-msg { color: var(--text-primary, #f5e6c8); flex: 1; word-break: break-word; }
#notif-list { background: var(--bg-input, #1e2d3d); border: 1px solid var(--border-default, #4a6278); border-radius: 4px; max-height: 500px; overflow-y: auto; padding: 8px; font-size: 13px; }
#notif-tab-badge { background: #ef4444; color: white; font-size: 11px; padding: 1px 6px; border-radius: 10px; margin-left: 6px; font-weight: 600; }
"""

NOTIF_TAB_BUTTON = """<button class="tab" id="notif-tab" data-tab="notifications">Notificaciones<span id="notif-tab-badge" style="display:none;"></span></button>"""

# v3.1: Panel resumen simplificado — solo MODELOS y AGENTES.
# Eliminados: INFRAESTRUCTURA (arena), PROVEEDORES, TOP PLANIFICACION, TOP CODIGO
NOTIF_SECTION_HTML = """
        <!-- SECCION NOTIFICACIONES — motor: notification_ui_bridge.py v3.1 -->
        <div id="notifications-section" class="tab-content">
            <h2>&#x1F4E2; Notificaciones en Tiempo Real</h2>

            <!-- Panel resumen: solo modelos + agentes -->
            <div id="notif-summary" style="background:var(--bg-elevated,#2d4059);border:1px solid var(--border-default,#4a6278);border-radius:6px;padding:12px;margin-bottom:12px;font-size:13px;">
                <div style="margin-bottom:8px;">
                    <span style="color:var(--text-muted,#baae87);font-size:12px;">MODELOS</span>
                    <span id="sm-total" style="margin-left:12px;color:var(--text-primary,#f5e6c8);font-weight:600;">Total: --</span>
                    <span id="sm-avail" style="margin-left:12px;color:#22c55e;">Disponibles: --</span>
                </div>
                <div style="margin-bottom:8px;">
                    <span style="color:var(--text-muted,#baae87);font-size:12px;">AGENTES</span>
                    <span id="sm-agent-active" style="margin-left:12px;color:#06b6d4;">Activos: --</span>
                    <span id="sm-agent-done" style="margin-left:12px;color:#22c55e;">Completados: --</span>
                    <span id="sm-agent-failed" style="margin-left:12px;color:#ef4444;">Fallidos: --</span>
                </div>
                <div>
                    <span style="color:var(--text-muted,#baae87);font-size:12px;">TOP 5 MODELOS</span>
                    <span id="sm-top5" style="margin-left:12px;color:#3b82f6;">--</span>
                </div>
            </div>

            <div style="margin-bottom:12px;display:flex;gap:10px;align-items:center;flex-wrap:wrap;">
                <label style="margin:0;color:var(--text-secondary,#d4c4a0);">Filtrar:</label>
                <select id="notif-filter" onchange="setNotifFilter(this.value)" style="padding:6px 12px;border:1px solid var(--border-default,#4a6278);border-radius:4px;background:var(--bg-input,#1e2d3d);color:var(--text-primary,#f5e6c8);font-size:14px;">
                    <option value="all">Todos</option>
                    <option value="system">Sistema</option>
                    <option value="agent">Agente</option>
                </select>
                <span id="notif-count" style="color:var(--text-secondary,#d4c4a0);font-size:14px;">0 eventos</span>
                <button class="secondary" onclick="clearNotifDisplay()" style="margin-left:auto;padding:6px 16px;font-size:13px;">Limpiar</button>
            </div>
            <div id="notif-list"></div>
        </div>
"""

# v3.1: JS simplificado — renderNotifSummary solo muestra modelos + agentes.
# Eliminados: arena, providers, top_planning, top_coding del summary render.
NOTIF_JS = """
// --- P5: Notificaciones en tiempo real (SSE) — motor: notification_ui_bridge.py v3.1 ---
let notifEvents = [];
let notifFilter = 'all';
let notifUnseen = 0;

function initNotifications() {
    fetch('/notifications/recent')
        .then(r => r.json())
        .then(data => {
            notifEvents = (data.events || []).reverse();
            renderNotifSummary(data.summary || {});
            renderNotifications();
        })
        .catch(() => {});

    const es = new EventSource('/notifications/stream');
    es.onmessage = function(e) {
        try {
            const evt = JSON.parse(e.data);
            notifEvents.unshift(evt);
            if (notifEvents.length > 100) notifEvents.pop();
            notifUnseen++;
            updateNotifBadge();
            if (document.getElementById('notificaciones-section') && document.getElementById('notificaciones-section').classList.contains('active')) {
                renderNotifications();
            }
        } catch(err) {}
    };
    es.onerror = function() { setTimeout(function() { es.close(); }, 5000); };

    setInterval(refreshNotifSummary, 15000);
}

function refreshNotifSummary() {
    fetch('/notifications/summary')
        .then(r => r.json())
        .then(data => {
            if (data) renderNotifSummary(data);
        })
        .catch(() => {});
}

function renderNotifSummary(s) {
    if (!s) return;
    const m = s.models || {};
    const a = s.agents || {};
    const el = (id) => document.getElementById(id);

    // Modelos
    if (el('sm-total')) el('sm-total').textContent = 'Total: ' + (m.total || 0);
    if (el('sm-avail')) el('sm-avail').textContent = 'Disponibles: ' + (m.available || 0);

    // Agentes
    if (el('sm-agent-active')) el('sm-agent-active').textContent = 'Activos: ' + ((a.in_progress || 0) + (a.started || 0));
    if (el('sm-agent-done')) el('sm-agent-done').textContent = 'Completados: ' + (a.done || 0);
    if (el('sm-agent-failed')) el('sm-agent-failed').textContent = 'Fallidos: ' + (a.failed || 0);

    // Top 5 modelos
    const top5 = (m.top_5 || []);
    if (el('sm-top5')) {
        el('sm-top5').textContent = top5.length
            ? top5.map((t, i) => '#' + (i+1) + ' ' + t.id + ' (' + t.score + ')').join('  |  ')
            : '--';
    }
}

function renderNotifications() {
    const container = document.getElementById('notif-list');
    if (!container) return;
    const filtered = notifFilter === 'all'
        ? notifEvents
        : notifEvents.filter(e => e.prefix === notifFilter);
    container.innerHTML = '';
    if (filtered.length === 0) {
        container.innerHTML = '<div style="color:#666;padding:20px;text-align:center;">Sin eventos' +
            (notifFilter !== 'all' ? ' en esta categoria' : '') + '</div>';
    }
    for (const e of filtered) {
        const div = document.createElement('div');
        div.className = 'notif-item';
        div.style.borderLeftColor = e.color;
        div.innerHTML =
            '<span class="notif-time">' + e.time_str + '</span>' +
            '<span class="notif-badge" style="background:' + e.color + '">' + e.category + '</span>' +
            '<span class="notif-msg">' + e.message + '</span>';
        container.appendChild(div);
    }
    document.getElementById('notif-count').textContent = filtered.length + ' eventos';
}

function updateNotifBadge() {
    const badge = document.getElementById('notif-tab-badge');
    if (badge && notifUnseen > 0) {
        badge.textContent = notifUnseen > 99 ? '99+' : notifUnseen;
        badge.style.display = 'inline';
    } else if (badge) {
        badge.style.display = 'none';
    }
}

function setNotifFilter(val) {
    notifFilter = val;
    notifUnseen = 0;
    updateNotifBadge();
    renderNotifications();
}

function clearNotifDisplay() {
    notifEvents = [];
    notifUnseen = 0;
    updateNotifBadge();
    const container = document.getElementById('notif-list');
    if (container) container.innerHTML = '';
    document.getElementById('notif-count').textContent = '0 eventos';
}
"""


# ============================================================================
# MOTOR DE RENDERIZADO TKINTER — usado por ensamblador_gui.py
# ============================================================================
# Estas funciones renderizan eventos en un tk.Text widget usando los
# mismos colores, mismos formatos y misma logica que la web.
# el ensamblador NO tiene codigo de render propio: solo llama al bridge.
# ============================================================================

def _get_badge_tag(event_type: str) -> str:
    """Retorna el tag de badge para un tipo de evento."""
    if event_type in EVENT_SPECIFIC_COLOR_MAP:
        return "badge_" + event_type.replace(":", "_")
    prefix = event_type.split(":")[0] if ":" in event_type else "system"
    return "badge_" + prefix


def _get_msg_tag(event_type: str) -> str:
    """Retorna el tag de mensaje para un tipo de evento."""
    prefix = event_type.split(":")[0] if ":" in event_type else "system"
    return "msg_" + prefix


def configure_tkinter_tags(text_widget) -> None:
    """Configura los tags de color en un tk.Text widget.

    Debe llamarse UNA VEZ al crear el widget.
    Usa los mismos colores que EVENT_PREFIX_COLOR_MAP y EVENT_SPECIFIC_COLOR_MAP.
    """
    text_widget.tag_configure("time_tag",
        foreground="#888", font=("Consolas", 10))
    # Tags por prefijo
    for prefix, color in EVENT_PREFIX_COLOR_MAP.items():
        text_widget.tag_configure("badge_" + prefix,
            foreground=color, font=("Segoe UI", 10, "bold"))
        text_widget.tag_configure("msg_" + prefix,
            foreground="#d4d4d4", font=("Segoe UI", 10))
    # Tags especificos por tipo de evento (sobreescriben prefijo)
    for evt_type, color in EVENT_SPECIFIC_COLOR_MAP.items():
        tag_name = "badge_" + evt_type.replace(":", "_")
        text_widget.tag_configure(tag_name,
            foreground=color, font=("Segoe UI", 10, "bold"))
    # Separador sutil entre eventos
    text_widget.tag_configure("separator",
        foreground="#1a1a1a", font=("Segoe UI", 2))


def render_events_to_text(text_widget, formatted_events: List[Dict[str, Any]],
                          filter_prefix: str = None) -> int:
    """Renderiza eventos formateados en un tk.Text widget.

    Esta es la misma funcion que usa la web (renderNotifications en JS)
    pero para tkinter. Misma logica, mismo formato, mismos colores.

    Args:
        text_widget: tk.Text ya configurado con configure_tkinter_tags()
        formatted_events: lista de dicts de format_event()
        filter_prefix: si no es None, solo muestra eventos de ese prefijo

    Returns:
        Numero de eventos mostrados.
    """
    text_widget.config(state="normal")
    text_widget.delete("1.0", "end")

    shown = 0
    for evt in formatted_events:
        if filter_prefix and evt.get("prefix") != filter_prefix:
            continue
        _render_single_event(text_widget, evt)
        shown += 1

    if filter_prefix and shown == 0:
        text_widget.insert("end",
            f"  -- Sin eventos en categoria '{filter_prefix}' --\n",
            "time_tag")

    text_widget.config(state="disabled")
    text_widget.see("1.0")
    return shown


def _render_single_event(text_widget, evt: Dict[str, Any]) -> None:
    """Renderiza un solo evento como tarjeta con borde izquierdo de color.

    Formato visual identico a la web:
      ┃ HH:MM:SS  [CATEGORIA]  mensaje
      ─────────────────────────────────
    """
    evt_type = evt.get("type", "")
    color = evt.get("color", "#9ca3af")

    # Tag dinamico para el borde (color del evento)
    border_tag = "border_" + evt_type.replace(":", "_")
    text_widget.tag_configure(border_tag,
        foreground=color, font=("Segoe UI", 12, "bold"))

    badge_tag = _get_badge_tag(evt_type)
    msg_tag = _get_msg_tag(evt_type)

    text_widget.insert("end", " \u2503 ", border_tag)             # ┃ borde izquierdo
    text_widget.insert("end", evt.get("time_str", "--:--:--") + "  ", "time_tag")
    text_widget.insert("end", evt.get("category", "") + "  ", badge_tag)
    text_widget.insert("end", evt.get("message", "") + "\n", msg_tag)
    text_widget.insert("end", " \u2500" * 60 + "\n", "separator")  # ─── separador


# v3.1: Simplificado — solo modelos (via MB) y agentes (via EVT_AGENT_*).
# Eliminados: arena, pool, providers.
def get_summary_display_data(summary_data: Dict[str, Any]) -> Dict[str, str]:
    """Retorna un dict clave->texto con los datos de resumen formateados.

    Consumido por ensamblador_gui.py para actualizar sus labels.
    Las claves coinciden con SUMMARY_LABELS_CONFIG + keys extra.

    Returns:
        {
            'total': '42', 'available': '38',
            'agent_active': '2', 'agent_done': '5', 'agent_failed': '0',
            'top_5': '#1 gpt-4o (95.3)  |  #2 claude-3 (92.1)',
            'status': 'Modelos: 38 disponibles de 42 totales | Agentes: 2 activos',
        }
    """
    m = summary_data.get('models', {})
    a = summary_data.get('agents', {})

    result = {}

    # Modelos via MB
    for key, label, color in SUMMARY_LABELS_CONFIG:
        result[key] = str(m.get(key, 0))

    # Agentes
    agent_active = (a.get('in_progress', 0) or 0) + (a.get('started', 0) or 0)
    result['agent_active'] = str(agent_active)
    result['agent_done'] = str(a.get('done', 0) or 0)
    result['agent_failed'] = str(a.get('failed', 0) or 0)

    # Top 5 modelos
    top5 = m.get('top_5', [])
    result['top_5'] = "  |  ".join(
        f"#{i+1} {t['id']} ({t['score']})" for i, t in enumerate(top5)
    ) if top5 else "--"

    # Barra de estado
    result['status'] = (
        f"Modelos: {m.get('available',0)} disponibles de "
        f"{m.get('total',0)} totales | "
        f"Agentes: {agent_active} activos"
    )

    return result


# ============================================================================
# MOTOR DE TARJETAS DE AGENTES PARA TKINTER (v1.0)
# ============================================================================
# Mismo patron que configure_tkinter_tags() + render_events_to_text():
#   - El bridge proporciona constantes, logica de estado y render.
#   - El ensamblador solo crea el frame contenedor y llama al manager.
# ============================================================================

AGENT_NAMES = ['planner', 'coder', 'integrator', 'validator']

AGENT_ICONS = {
    "planner":    ("P", "Planificador"),
    "coder":      ("C", "Codificador"),
    "integrator": ("I", "Integrador"),
    "validator":  ("V", "Validador"),
}

AGENT_COLORS = {
    "started":  "#3b82f6",
    "progress": "#f59e0b",
    "done":     "#22c55e",
    "failed":   "#ef4444",
    "inactive": "#555555",
}

AGENT_STATUS_LABELS = {
    "started":  "● activo",
    "progress": "● trabajando",
    "done":     "● completado",
    "failed":   "● fallido",
    "inactive": "○ inactivo",
}


class AgentCardManager:
    """Motor de tarjetas de agentes para tkinter.

    Gestiona estado, parseo de eventos del notification bus, render
    de tarjetas dinamicas en 4 cuadrantes, y cleanup automatico.

    Uso en ensamblador_gui.py::

        mgr = AgentCardManager(root, parent_frame)
        mgr.set_callback_ref(create_bridge_callback(mgr.on_event))
        # Al cerrar:
        mgr.destroy()
    """

    def __init__(self, root, parent_frame, status_label=None, log_widget=None):
        """
        Args:
            root: tk.Tk — ventana principal (para root.after)
            parent_frame: tk.Frame — frame donde se crean los 4 cuadrantes
            status_label: tk.Label (optional) — label para mostrar
                          "N agente(s) activo(s)" / "Esperando agentes..."
            log_widget: tk.Text (optional) — widget de log para mostrar
                        los ultimos eventos de agentes
        """
        self.root = root
        self._status_label = status_label
        self._log_widget = log_widget
        self._log_lines = []  # buffer de ultimas lineas
        self._MAX_LOG_LINES = 4
        self._state = {}          # {agent_key: {status, model, task, ...}}
        self._callback_ref = None
        self._cleanup_timer = None

        # Crear 4 cuadrantes
        tk = _tk()
        self._quadrants = {}
        for idx, agent_id in enumerate(AGENT_NAMES):
            q = tk.Frame(parent_frame, bg="#111", bd=0)
            q.grid(row=0, column=idx, padx=2, pady=2, sticky="nsew")
            parent_frame.columnconfigure(idx, weight=1)
            parent_frame.rowconfigure(0, weight=1)
            self._quadrants[agent_id] = q

        # Render inicial: placeholders vacíos
        self._render_quadrants()

    def set_callback_ref(self, callback_ref):
        """Guarda la referencia al callback del bridge (para destroy)."""
        self._callback_ref = callback_ref

    # --- Evento del notification bus ---

    def on_event(self, formatted):
        """Callback invocado por create_bridge_callback().

        Recibe eventos formateados del bus y actualiza el estado interno.
        Solo procesa eventos con prefix 'agent'.
        """
        evt_type = formatted.get("type", "")
        data = formatted.get("data", {})
        prefix = formatted.get("prefix", "")

        # Filtrar solo eventos de agente
        if not prefix.startswith("agent"):
            return

        agent_id = data.get("agent", "")
        if not agent_id:
            return

        # Determinar estado
        status = "inactive"
        if "started" in evt_type:
            status = "started"
        elif "progress" in evt_type:
            status = "progress"
        elif "done" in evt_type:
            status = "done"
        elif "failed" in evt_type:
            status = "failed"

        # Actualizar estado interno
        now = time.time()
        key = f"{agent_id}_{data.get('task', 'default')}"
        prev = self._state.get(key, {})
        self._state[key] = {
            "status": status,
            "model": data.get("model", prev.get("model", "--")),
            "task": data.get("task", prev.get("task", "")),
            "tokens": data.get("tokens_used", prev.get("tokens", 0)),
            "pct": data.get("pct", prev.get("pct", "")),
            "error": data.get("error", ""),
            "timestamp": now,
            "agent_id": agent_id,
        }

        # Actualizar tarjetas en el hilo de la GUI
        self.root.after(0, self._render_quadrants)

        # Actualizar log
        self._append_log(formatted)

    # --- Render ---

    def _render_quadrants(self):
        """Reconstruye las tarjetas visuales en los 4 cuadrantes."""
        # Agrupar por tipo de agente
        active_by_type = {}
        for key, state in self._state.items():
            aid = state.get("agent_id", "")
            if aid not in active_by_type:
                active_by_type[aid] = []
            active_by_type[aid].append(state)

        total_active = 0

        for agent_id, quadrant in self._quadrants.items():
            # Limpiar cuadrante
            for w in quadrant.winfo_children():
                w.destroy()

            agents = active_by_type.get(agent_id, [])
            icon_letter, name = AGENT_ICONS.get(agent_id, ("?", agent_id))

            if not agents:
                tk = _tk()
                # Placeholder con buen contraste
                tk.Label(quadrant, text=icon_letter, bg="#111", fg="#4a5568",
                         font=("Segoe UI", 18)).pack(pady=(15, 2))
                tk.Label(quadrant, text=name, bg="#111", fg="#718096",
                         font=("Segoe UI", 9, "bold")).pack()
                tk.Label(quadrant, text="sin actividad", bg="#111", fg="#4a5568",
                         font=("Segoe UI", 8)).pack(pady=(0, 10))
                continue

            # Mas reciente primero
            agents.sort(key=lambda a: a.get("timestamp", 0), reverse=True)

            for state in agents:
                self._render_card(quadrant, state, icon_letter)
                total_active += 1

        # Actualizar label de estado
        if self._status_label:
            if total_active > 0:
                self._status_label.config(
                    text=f"{total_active} agente(s) activo(s)", fg="#22c55e")
            else:
                self._status_label.config(
                    text="Esperando agentes...", fg="#666")

        # Cleanup de agentes terminados tras ~2.5s
        if self._cleanup_timer is not None:
            self.root.after_cancel(self._cleanup_timer)
        self._cleanup_timer = self.root.after(2500, self._cleanup_done)

    def _render_card(self, parent, state, icon_letter):
        """Renderiza una tarjeta de agente dentro de un cuadrante."""
        tk = _tk()
        status = state.get("status", "inactive")
        color = AGENT_COLORS.get(status, "#555")
        status_txt = AGENT_STATUS_LABELS.get(status, "○ inactivo")
        model = state.get("model", "--")
        task = state.get("task", "")
        tokens = state.get("tokens", 0)
        pct = state.get("pct", "")
        error = state.get("error", "")

        # Card
        card = tk.Frame(parent, bg="#1a1a1a", bd=1, relief="solid",
                        highlightbackground="#333", highlightthickness=1)
        card.pack(fill="both", expand=True, padx=3, pady=3)

        # Cabecera
        hdr = tk.Frame(card, bg="#1a1a1a")
        hdr.pack(fill="x", padx=6, pady=(4, 0))
        tk.Label(hdr, text=icon_letter, bg="#1a1a1a", fg=color,
                 font=("Segoe UI", 10)).pack(side="left")
        tk.Label(hdr, text=task, bg="#1a1a1a", fg="#d4d4d4",
                 font=("Consolas", 9, "bold")).pack(side="left", padx=4)
        if pct:
            tk.Label(hdr, text=f"{pct}%", bg="#1a1a1a", fg="#f59e0b",
                     font=("Segoe UI", 9, "bold")).pack(side="right")

        # Estado
        sf = tk.Frame(card, bg="#1a1a1a")
        sf.pack(fill="x", padx=6, pady=1)
        tk.Label(sf, text=status_txt, bg="#1a1a1a", fg=color,
                 font=("Segoe UI", 8)).pack(side="left")

        # Detalles
        detail = tk.Frame(card, bg="#1a1a1a")
        detail.pack(fill="x", padx=6, pady=(0, 4))
        tk.Label(detail, text=model, bg="#1a1a1a", fg="#888",
                 font=("Consolas", 8)).pack(side="left")
        if tokens:
            tk.Label(detail, text=f"│ {tokens} tok", bg="#1a1a1a", fg="#555",
                     font=("Consolas", 8)).pack(side="left", padx=6)

        # Barra de error si falló
        if error and status == "failed":
            err_frame = tk.Frame(card, bg="#2a1111")
            err_frame.pack(fill="x", padx=4, pady=(0, 4))
            tk.Label(err_frame, text=f"⚠ {error[:60]}", bg="#2a1111",
                     fg="#ef4444", font=("Consolas", 8), anchor="w",
                     wraplength=200, justify="left").pack(
                         fill="x", padx=4, pady=2)

    # --- Log ---

    def _append_log(self, formatted):
        """Agrega una linea al log widget (max 4 lineas)."""
        if not self._log_widget:
            return
        evt_type = formatted.get("type", "")
        data = formatted.get("data", {})
        msg = formatted.get("message", "")
        time_str = formatted.get("time_str", "--:--:--")
        agent = data.get("agent", "?")

        # Color por tipo
        color = AGENT_COLORS.get(evt_type.split(":")[-1] if ":" in evt_type else "inactive", "#888")
        tag = f"agent_{evt_type.split(':')[1]}" if ":" in evt_type else "agent_info"

        line = f"[{time_str}] {agent}: {msg}"
        self._log_lines.append((line, tag, color))
        if len(self._log_lines) > self._MAX_LOG_LINES:
            self._log_lines = self._log_lines[-self._MAX_LOG_LINES:]

        self.root.after(0, self._render_log)

    def _render_log(self):
        """Renderiza las ultimas lineas en el log widget."""
        if not self._log_widget:
            return
        tk = _tk()
        try:
            self._log_widget.config(state="normal")
            self._log_widget.delete("1.0", "end")
            for line, tag, color in self._log_lines:
                if not self._log_widget.tag_exists(tag):
                    self._log_widget.tag_configure(tag, foreground=color)
                self._log_widget.insert("end", line + "\n", tag)
            self._log_widget.config(state="disabled")
            self._log_widget.see("end")
        except Exception:
            pass

    # --- Cleanup ---

    def _cleanup_done(self):
        """Elimina agentes completados/fallidos del estado tras delay de observación."""
        self._cleanup_timer = None
        now = time.time()
        to_remove = [
            key for key, s in self._state.items()
            if s.get("status") in ("done", "failed") and (now - s.get("timestamp", 0)) > 2.5
        ]
        for key in to_remove:
            del self._state[key]
        if to_remove:
            self._render_quadrants()

    # --- Public API ---

    def clear(self):
        """Limpia todo el estado de agentes."""
        self._state.clear()
        self._render_quadrants()

    def destroy(self):
        """Limpia recursos: cancela timers y desregistra callback."""
        if self._cleanup_timer is not None:
            self.root.after_cancel(self._cleanup_timer)
            self._cleanup_timer = None
        if self._callback_ref is not None:
            try:
                unregister_callback(self._callback_ref)
            except Exception:
                pass
            self._callback_ref = None


# ============================================================================
# Test standalone
# ============================================================================

if __name__ == "__main__":
    from core.notifications import notify

    print("\n" + "=" * 60)
    print("TEST: notification_ui_bridge v3.1")
    print("=" * 60)

    # --- Tests core ---
    c1 = get_event_color(EVT_SYSTEM_ERROR)
    assert c1 == '#ef4444', f"Esperaba #ef4444, obtuve {c1}"
    print("  [PASS] get_event_color() prefijo system -> rojo")

    c2 = get_event_color(EVT_EMERGENCY_MODE)
    assert c2 == '#dc2626', f"Esperaba #dc2626, obtuve {c2}"
    print("  [PASS] get_event_color() EVT_EMERGENCY_MODE -> rojo oscuro")

    c3 = get_event_color(EVT_AGENT_STARTED)
    assert c3 == '#06b6d4', f"Esperaba #06b6d4, obtuve {c3}"
    print("  [PASS] get_event_color() EVT_AGENT_STARTED -> cyan")

    l1 = get_event_label(EVT_SYSTEM_ERROR)
    assert l1 == 'Sistema', f"Esperaba Sistema, obtuve {l1}"
    l2 = get_event_label(EVT_AGENT_STARTED)
    assert l2 == 'Agente', f"Esperaba Agente, obtuve {l2}"
    print("  [PASS] get_event_label() retorna etiquetas correctas")

    test_evt = {
        'type': EVT_SYSTEM_ERROR,
        'message': 'Error critico del sistema',
        'data': {'code': 500},
        'timestamp': time.time(),
    }
    fmt = format_event(test_evt)
    assert fmt['color'] == '#ef4444'
    assert fmt['category'] == 'Sistema'
    assert fmt['prefix'] == 'system'
    assert fmt['time_str'] != '--:--:--'
    assert fmt['message'] == 'Error critico del sistema'
    print("  [PASS] format_event() campos correctos")

    fmt2 = format_event({
        'type': 'custom:algo_nuevo',
        'message': 'Test custom',
        'data': {},
    })
    assert fmt2['prefix'] == 'custom'
    assert fmt2['category'] == 'Custom'
    assert fmt2['color'] == '#9ca3af'
    print("  [PASS] format_event() tipo desconocido usa prefijo y gris")

    # --- Tests truncado ---
    long_msg = "Modelos disponibles: " + ", ".join([f"modelo_{i}" for i in range(30)])
    fmt_long = format_event({
        'type': 'system:startup',
        'message': long_msg,
        'data': {},
        'timestamp': time.time(),
    })
    assert len(fmt_long['message']) <= 140, f"Mensaje muy largo: {len(fmt_long['message'])}"
    print(f"  [PASS] Truncado: {len(long_msg)} -> {len(fmt_long['message'])} chars")

    summary = get_event_summary()
    assert 'total' in summary
    assert 'by_prefix' in summary
    print("  [PASS] get_event_summary() retorna estructura correcta")

    collected = []
    def on_fmt(evt):
        collected.append(evt)
    cb = create_bridge_callback(on_fmt)
    notify(EVT_SYSTEM_ERROR, 'Test error bridge', {'test': True})
    assert len(collected) >= 1
    assert collected[-1]['type'] == EVT_SYSTEM_ERROR
    assert collected[-1]['color'] == '#ef4444'
    assert collected[-1]['category'] == 'Sistema'
    assert 'time_str' in collected[-1]
    unregister_callback(cb)
    print("  [PASS] create_bridge_callback() emite y formatea")

    # v3.1: EVENT_TYPES_LIST tiene 8 tipos (eliminados 16 muertos)
    assert EVT_EMERGENCY_MODE in EVENT_TYPES_LIST
    assert EVT_SYSTEM_ERROR in EVENT_TYPES_LIST
    assert EVT_AGENT_STARTED in EVENT_TYPES_LIST
    assert len(EVENT_TYPES_LIST) == 8, f"Esperaba 8, obtuve {len(EVENT_TYPES_LIST)}"
    print("  [PASS] EVENT_TYPES_LIST tiene 8 tipos")

    assert set(EVENT_PREFIX_COLOR_MAP.keys()) == {'system', 'agent'}
    print("  [PASS] EVENT_PREFIX_COLOR_MAP tiene 2 categorias")

    # --- Tests Fase 4: Agent lifecycle events ---
    assert EVT_AGENT_STARTED == 'agent:started'
    assert EVT_AGENT_PROGRESS == 'agent:progress'
    assert EVT_AGENT_DONE == 'agent:done'
    assert EVT_AGENT_FAILED == 'agent:failed'
    print('  [PASS] EVT_AGENT_* constantes definidas correctamente')

    c_agent_started = get_event_color(EVT_AGENT_STARTED)
    assert c_agent_started == '#06b6d4', f'Esperaba #06b6d4, obtuve {c_agent_started}'
    c_agent_done = get_event_color(EVT_AGENT_DONE)
    assert c_agent_done == '#22c55e', f'Esperaba #22c55e, obtuve {c_agent_done}'
    c_agent_failed = get_event_color(EVT_AGENT_FAILED)
    assert c_agent_failed == '#ef4444', f'Esperaba #ef4444, obtuve {c_agent_failed}'
    print('  [PASS] Colores de EVT_AGENT_* correctos')

    l_agent = get_event_label(EVT_AGENT_STARTED)
    assert l_agent == 'Agente', f'Esperaba Agente, obtuve {l_agent}'
    print('  [PASS] get_event_label() retorna Agente para eventos agent:*')

    fmt_agent = format_event({
        'type': EVT_AGENT_STARTED,
        'message': 'Planificador iniciado',
        'data': {'agent': 'planner', 'task': 'T1', 'model': 'claude-3'},
        'timestamp': time.time(),
    })
    assert fmt_agent['color'] == '#06b6d4'
    assert fmt_agent['category'] == 'Agente'
    assert fmt_agent['prefix'] == 'agent'
    print('  [PASS] format_event() agent:started formateado correctamente')

    # --- Tests motor web ---
    assert 'notif-item' in NOTIF_CSS
    assert 'notif-badge' in NOTIF_CSS
    assert 'border-left' in NOTIF_CSS
    print("  [PASS] NOTIF_CSS contiene estilos de notificaciones")

    assert 'notifications-section' in NOTIF_SECTION_HTML
    assert 'sm-total' in NOTIF_SECTION_HTML
    assert 'sm-agent-active' in NOTIF_SECTION_HTML
    # v3.1: ya no existen estos spans
    assert 'sm-arena' not in NOTIF_SECTION_HTML
    assert 'sm-provactive' not in NOTIF_SECTION_HTML
    assert 'sm-topplan' not in NOTIF_SECTION_HTML
    print("  [PASS] NOTIF_SECTION_HTML: solo modelos + agentes, sin arena/providers")

    assert 'initNotifications' in NOTIF_JS
    assert 'renderNotifications' in NOTIF_JS
    assert 'renderNotifSummary' in NOTIF_JS
    assert 'setNotifFilter' in NOTIF_JS
    assert 'clearNotifDisplay' in NOTIF_JS
    # v3.1: JS ya no refiere arena/providers
    assert 'sm-arena' not in NOTIF_JS
    assert 'sm-provactive' not in NOTIF_JS
    assert 'sm-provlist' not in NOTIF_JS
    print("  [PASS] NOTIF_JS: funciones presentes, sin arena/providers")

    # --- Tests motor tkinter ---
    assert _get_badge_tag(EVT_SYSTEM_ERROR) == "badge_system_error"
    assert _get_badge_tag('custom:something') == "badge_custom"
    assert _get_msg_tag('system:error') == "msg_system"
    print("  [PASS] _get_badge_tag() y _get_msg_tag() retornan tags correctos")

    # v3.1: get_summary_display_data simplificado
    disp = get_summary_display_data({
        'models': {'total': 50, 'available': 40, 'top_5': [
            {'id': 'gpt-4o', 'score': 95.3},
            {'id': 'claude-3', 'score': 92.1},
        ]},
        'agents': {'started': 1, 'in_progress': 2, 'done': 5, 'failed': 0},
    })
    assert disp['total'] == '50'
    assert disp['available'] == '40'
    assert disp['agent_active'] == '3'
    assert disp['agent_done'] == '5'
    assert disp['agent_failed'] == '0'
    assert '#1 gpt-4o (95.3)' in disp['top_5']
    assert '#2 claude-3 (92.1)' in disp['top_5']
    assert 'Modelos: 40 disponibles' in disp['status']
    assert 'Agentes: 3 activos' in disp['status']
    # v3.1: ya no existen estas keys
    assert 'arena_ranked' not in disp
    assert 'pool_total' not in disp
    assert 'prov_active' not in disp
    print("  [PASS] get_summary_display_data() solo modelos + agentes")

    assert len(SUMMARY_LABELS_CONFIG) == 2, f"Esperaba 2, obtuve {len(SUMMARY_LABELS_CONFIG)}"
    print("  [PASS] SUMMARY_LABELS_CONFIG tiene 2 entradas")

    # --- Tests robustez ---
    collected2 = []
    broken_called = []
    def broken_ui(evt):
        broken_called.append(1)
        raise RuntimeError("Soy una UI rota")
    def good_ui(evt):
        collected2.append(evt)
    cb1 = create_bridge_callback(broken_ui)
    cb2 = create_bridge_callback(good_ui)
    notify(EVT_EMERGENCY_MODE, 'Test roto + bueno', {'reason': 'test'})
    assert len(broken_called) >= 1
    assert len(collected2) >= 1
    unregister_callback(cb1)
    unregister_callback(cb2)
    print("  [PASS] Callback roto no afecta a otros callbacks")

    print("\n" + "=" * 60)
    print("  TODOS LOS TESTS PASARON - notification_ui_bridge v3.1 OK")
    print("=" * 60)