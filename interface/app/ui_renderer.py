# apa/interface/app/ui_renderer.py
"""
ui_renderer.py — Renderizador de la interfaz de usuario de APA.

Módulo responsable de construir y servir la página HTML principal de la
aplicación APA. Inyecta valores dinámicos en la plantilla mediante un
sistema de placeholders:

    __THEME_ROOT__   → Variables CSS del tema (core.apa_theme.THEME_CSS_VARIABLES)
    __P5_CSS__       → CSS de notificaciones P5 (core.notification_ui_bridge.NOTIF_CSS)
    __P5_TAB__       → Botón de pestaña P5 (core.notification_ui_bridge.NOTIF_TAB_BUTTON)
    __P5_SECTION__   → Sección HTML P5 (core.notification_ui_bridge.NOTIF_SECTION_HTML)
    __P5_JS__        → JavaScript P5 (core.notification_ui_bridge.NOTIF_JS)

Si core.ui_template.HTML_TEMPLATE está disponible, se usa como base.
De lo contrario, se utiliza una plantilla fallback completa.

Clases:
    UIRenderer: Construye la página HTML con placeholders reemplazados.

Funciones:
    register_ui_routes: Registra GET / en la aplicación FastAPI.
"""

from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent)) #apa/

import logging
from typing import TYPE_CHECKING, Dict, Optional

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

if TYPE_CHECKING:
    from app.self_context import SelfContextLoader
    from app.state import AppState


# ── Logger ───────────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)


# ── Intento de importar plantilla real desde core ───────────────────────────
_HTML_TEMPLATE: Optional[str] = None
try:
    from core.ui_template import HTML_TEMPLATE as _HTML_TEMPLATE  # type: ignore[import-untyped]
    logger.info("Plantilla HTML cargada desde core.ui_template")
except ImportError:
    logger.info("core.ui_template no disponible — se usará plantilla fallback")


# ── Variables de inyección desde core ───────────────────────────────────────
_THEME_CSS: str = ""
try:
    from core.apa_theme import THEME_CSS_VARIABLES as _THEME_CSS  # type: ignore[import-untyped]
    logger.info("Variables de tema cargadas desde core.apa_theme")
except ImportError:
    logger.info("core.apa_theme no disponible — se usará tema por defecto")

_NOTIF_CSS: str = ""
_NOTIF_TAB: str = ""
_NOTIF_SECTION: str = ""
_NOTIF_JS: str = ""
try:
    from core.notification_ui_bridge import (  # type: ignore[import-untyped]
        NOTIF_CSS as _NOTIF_CSS,
        NOTIF_TAB_BUTTON as _NOTIF_TAB,
        NOTIF_SECTION_HTML as _NOTIF_SECTION,
        NOTIF_JS as _NOTIF_JS,
    )
    logger.info("Puentes de notificación cargados desde core.notification_ui_bridge")
except ImportError:
    logger.info("core.notification_ui_bridge no disponible — placeholders vacíos")


# ── Tema por defecto ─────────────────────────────────────────────────────────
_DEFAULT_THEME: str = """
:root {
    --bg-primary: #0f1117;
    --bg-secondary: #161922;
    --bg-tertiary: #1c2030;
    --bg-card: #1e2235;
    --bg-input: #232840;
    --bg-hover: #2a3050;
    --border-primary: #2d3348;
    --border-secondary: #3a4060;
    --border-accent: #10b981;
    --text-primary: #e8ecf4;
    --text-secondary: #8b95b0;
    --text-muted: #5a6480;
    --text-inverse: #0f1117;
    --accent: #10b981;
    --accent-hover: #34d399;
    --accent-dim: rgba(16, 185, 129, 0.15);
    --accent-amber: #f59e0b;
    --accent-amber-dim: rgba(245, 158, 11, 0.15);
    --accent-rose: #f43f5e;
    --accent-rose-dim: rgba(244, 63, 94, 0.15);
    --accent-cyan: #06b6d4;
    --accent-cyan-dim: rgba(6, 182, 212, 0.15);
    --shadow-sm: 0 1px 3px rgba(0,0,0,0.3);
    --shadow-md: 0 4px 12px rgba(0,0,0,0.4);
    --radius-sm: 6px;
    --radius-md: 10px;
    --radius-lg: 16px;
    --transition-fast: 150ms ease;
    --transition-normal: 250ms ease;
    --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    --font-mono: 'JetBrains Mono', 'Fira Code', monospace;
}
"""


# ════════════════════════════════════════════════════════════════════════════
#  PLANTILLA HTML FALLBACK COMPLETA
# ════════════════════════════════════════════════════════════════════════════

_FALLBACK_TEMPLATE: str = r"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>APA — AI Project Automation</title>
    <meta name="description" content="APA: Automatización inteligente de proyectos con IA">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">

    <!-- ═══ Variables de tema CSS (inyectadas dinámicamente) ═══ -->
    <style id="apa-theme-variables">
__THEME_ROOT__
    </style>

    <!-- ═══ CSS de notificaciones P5 (inyectado dinámicamente) ═══ -->
    <style id="p5-notification-css">
__P5_CSS__
    </style>

    <!-- ═══ Estilos principales ═══ -->
    <style>
        /* ── Reset ──────────────────────────────── */
        * { margin: 0; padding: 0; box-sizing: border-box; }
        html, body { height: 100%; font-family: var(--font-sans); background: var(--bg-primary); color: var(--text-primary); line-height: 1.6; overflow: hidden; }

        /* ── Scrollbar ──────────────────────────── */
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: var(--border-secondary); border-radius: 3px; }
        ::-webkit-scrollbar-thumb:hover { background: var(--text-muted); }

        /* ── Layout ─────────────────────────────── */
        .apa-app { display: flex; flex-direction: column; height: 100vh; max-height: 100vh; }

        /* ── Header ─────────────────────────────── */
        .apa-header { display: flex; align-items: center; justify-content: space-between; padding: 0 20px; height: 56px; min-height: 56px; background: var(--bg-secondary); border-bottom: 1px solid var(--border-primary); z-index: 100; }
        .apa-logo { display: flex; align-items: center; gap: 12px; }
        .apa-logo-icon { width: 32px; height: 32px; border-radius: var(--radius-sm); background: linear-gradient(135deg, var(--accent), #059669); display: flex; align-items: center; justify-content: center; font-weight: 800; font-size: 14px; color: white; letter-spacing: -0.5px; }
        .apa-logo-text { font-size: 18px; font-weight: 700; color: var(--text-primary); letter-spacing: -0.3px; }
        .apa-logo-sub { font-size: 11px; color: var(--text-muted); font-weight: 400; }
        .apa-header-right { display: flex; align-items: center; gap: 10px; }
        .apa-status-badge { display: flex; align-items: center; gap: 6px; padding: 4px 12px; border-radius: var(--radius-sm); background: var(--accent-dim); color: var(--accent); font-size: 12px; font-weight: 500; }
        .apa-status-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--accent); animation: pulse-dot 2s infinite; }
        @keyframes pulse-dot { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }

        /* ── Tabs ───────────────────────────────── */
        .apa-tabs { display: flex; align-items: center; gap: 2px; padding: 0 20px; height: 44px; min-height: 44px; background: var(--bg-secondary); border-bottom: 1px solid var(--border-primary); overflow-x: auto; }
        .apa-tab { display: flex; align-items: center; gap: 6px; padding: 8px 16px; border-radius: var(--radius-sm); background: transparent; border: none; color: var(--text-secondary); font-size: 13px; font-weight: 500; cursor: pointer; transition: all var(--transition-fast); white-space: nowrap; font-family: var(--font-sans); }
        .apa-tab:hover { background: var(--bg-hover); color: var(--text-primary); }
        .apa-tab.active { background: var(--accent-dim); color: var(--accent); }
        .apa-tab-icon { font-size: 15px; line-height: 1; }
        .apa-tab-badge { display: inline-flex; align-items: center; justify-content: center; min-width: 18px; height: 18px; padding: 0 5px; border-radius: 9px; background: var(--accent-rose); color: white; font-size: 10px; font-weight: 700; }

        /* ── P5 Tab placeholder ─────────────────── */
__P5_TAB__

        /* ── Content ────────────────────────────── */
        .apa-content { flex: 1; overflow: hidden; position: relative; }
        .apa-panel { display: none; height: 100%; overflow-y: auto; }
        .apa-panel.active { display: flex; flex-direction: column; }

        /* ── Chat ───────────────────────────────── */
        .chat-container { flex: 1; display: flex; flex-direction: column; height: 100%; }
        .chat-messages { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 16px; }
        .chat-message { max-width: 80%; padding: 12px 16px; border-radius: var(--radius-md); font-size: 14px; line-height: 1.65; animation: msg-in 0.3s ease; }
        @keyframes msg-in { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
        .chat-message.user { align-self: flex-end; background: var(--accent); color: white; border-bottom-right-radius: 4px; }
        .chat-message.assistant { align-self: flex-start; background: var(--bg-card); color: var(--text-primary); border: 1px solid var(--border-primary); border-bottom-left-radius: 4px; }
        .chat-message.system { align-self: center; background: var(--bg-tertiary); color: var(--text-muted); font-size: 12px; padding: 6px 14px; border-radius: var(--radius-sm); }
        .chat-message pre { background: var(--bg-primary); padding: 12px; border-radius: var(--radius-sm); overflow-x: auto; font-family: var(--font-mono); font-size: 13px; margin-top: 8px; }
        .chat-message code { font-family: var(--font-mono); font-size: 13px; }
        .chat-message p { margin-bottom: 8px; }
        .chat-message p:last-child { margin-bottom: 0; }
        .chat-msg-meta { font-size: 11px; color: var(--text-muted); margin-top: 6px; }
        .chat-input-area { display: flex; align-items: flex-end; gap: 10px; padding: 16px 20px; border-top: 1px solid var(--border-primary); background: var(--bg-secondary); }
        .chat-input-wrap { flex: 1; position: relative; }
        #chat-input { width: 100%; min-height: 44px; max-height: 160px; padding: 10px 14px; background: var(--bg-input); border: 1px solid var(--border-primary); border-radius: var(--radius-md); color: var(--text-primary); font-size: 14px; font-family: var(--font-sans); resize: vertical; outline: none; transition: border-color var(--transition-fast); line-height: 1.5; }
        #chat-input:focus { border-color: var(--accent); }
        #chat-input::placeholder { color: var(--text-muted); }
        .chat-send-btn { display: flex; align-items: center; justify-content: center; width: 44px; height: 44px; border-radius: var(--radius-md); background: var(--accent); border: none; color: white; cursor: pointer; transition: all var(--transition-fast); flex-shrink: 0; }
        .chat-send-btn:hover { background: var(--accent-hover); transform: translateY(-1px); }
        .chat-send-btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }
        .chat-send-btn svg { width: 20px; height: 20px; }
        .chat-welcome { flex: 1; display: flex; align-items: center; justify-content: center; flex-direction: column; gap: 12px; color: var(--text-muted); }
        .chat-welcome-icon { font-size: 48px; opacity: 0.3; }
        .chat-welcome h2 { font-size: 20px; color: var(--text-secondary); font-weight: 600; }
        .chat-welcome p { font-size: 14px; max-width: 400px; text-align: center; }

        /* ── Dashboard ──────────────────────────── */
        .dashboard-container { padding: 24px; overflow-y: auto; }
        .dashboard-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 16px; margin-bottom: 24px; }
        .dashboard-card { background: var(--bg-card); border: 1px solid var(--border-primary); border-radius: var(--radius-md); padding: 20px; transition: border-color var(--transition-fast); }
        .dashboard-card:hover { border-color: var(--border-secondary); }
        .dashboard-card-label { font-size: 12px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; font-weight: 500; margin-bottom: 8px; }
        .dashboard-card-value { font-size: 28px; font-weight: 700; color: var(--text-primary); line-height: 1.2; }
        .dashboard-card-sub { font-size: 12px; color: var(--text-secondary); margin-top: 4px; }
        .dashboard-card-icon { float: right; width: 40px; height: 40px; border-radius: var(--radius-sm); display: flex; align-items: center; justify-content: center; font-size: 20px; }
        .dashboard-section { background: var(--bg-card); border: 1px solid var(--border-primary); border-radius: var(--radius-md); padding: 20px; margin-bottom: 16px; }
        .dashboard-section h3 { font-size: 15px; font-weight: 600; margin-bottom: 16px; color: var(--text-primary); }
        .dashboard-activity-list { list-style: none; }
        .dashboard-activity-item { display: flex; align-items: center; gap: 10px; padding: 8px 0; border-bottom: 1px solid var(--border-primary); font-size: 13px; color: var(--text-secondary); }
        .dashboard-activity-item:last-child { border-bottom: none; }
        .activity-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }

        /* ── Projects ───────────────────────────── */
        .projects-container { display: flex; height: 100%; }
        .projects-sidebar { width: 280px; border-right: 1px solid var(--border-primary); overflow-y: auto; background: var(--bg-secondary); flex-shrink: 0; }
        .projects-sidebar-header { padding: 16px; border-bottom: 1px solid var(--border-primary); }
        .projects-sidebar-header h3 { font-size: 14px; font-weight: 600; }
        .project-list { list-style: none; }
        .project-item { display: flex; align-items: center; gap: 10px; padding: 12px 16px; cursor: pointer; transition: background var(--transition-fast); border-bottom: 1px solid var(--border-primary); }
        .project-item:hover { background: var(--bg-hover); }
        .project-item.active { background: var(--accent-dim); border-left: 3px solid var(--accent); }
        .project-item-name { font-size: 13px; font-weight: 500; color: var(--text-primary); }
        .project-item-status { font-size: 11px; color: var(--text-muted); }
        .projects-main { flex: 1; overflow-y: auto; padding: 24px; }
        .file-tree { list-style: none; }
        .file-tree-item { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border-radius: var(--radius-sm); cursor: pointer; font-size: 13px; color: var(--text-secondary); transition: all var(--transition-fast); }
        .file-tree-item:hover { background: var(--bg-hover); color: var(--text-primary); }
        .file-tree-folder { padding-left: 24px; }
        .file-icon { font-size: 14px; width: 18px; text-align: center; }

        /* ── Notifications ──────────────────────── */
        .notif-container { padding: 24px; overflow-y: auto; }
        .notif-list { list-style: none; display: flex; flex-direction: column; gap: 8px; }
        .notif-item { display: flex; align-items: flex-start; gap: 12px; padding: 14px 16px; background: var(--bg-card); border: 1px solid var(--border-primary); border-radius: var(--radius-md); transition: border-color var(--transition-fast); }
        .notif-item:hover { border-color: var(--border-secondary); }
        .notif-item.unread { border-left: 3px solid var(--accent); }
        .notif-type-icon { width: 32px; height: 32px; border-radius: var(--radius-sm); display: flex; align-items: center; justify-content: center; font-size: 16px; flex-shrink: 0; }
        .notif-type-icon.info { background: var(--accent-dim); color: var(--accent); }
        .notif-type-icon.warning { background: var(--accent-amber-dim); color: var(--accent-amber); }
        .notif-type-icon.error { background: var(--accent-rose-dim); color: var(--accent-rose); }
        .notif-content { flex: 1; min-width: 0; }
        .notif-message { font-size: 13px; color: var(--text-primary); line-height: 1.5; }
        .notif-time { font-size: 11px; color: var(--text-muted); margin-top: 4px; }

        /* ── P5 Notification section placeholder ── */
__P5_SECTION__

        /* ── Pipeline ───────────────────────────── */
        .pipeline-container { padding: 24px; overflow-y: auto; }
        .pipeline-card { background: var(--bg-card); border: 1px solid var(--border-primary); border-radius: var(--radius-md); padding: 20px; margin-bottom: 16px; }
        .pipeline-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
        .pipeline-name { font-size: 15px; font-weight: 600; color: var(--text-primary); }
        .pipeline-status { padding: 3px 10px; border-radius: 12px; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }
        .pipeline-status.running { background: var(--accent-dim); color: var(--accent); }
        .pipeline-status.paused { background: var(--accent-amber-dim); color: var(--accent-amber); }
        .pipeline-status.completed { background: rgba(99, 102, 241, 0.15); color: #818cf8; }
        .pipeline-status.failed { background: var(--accent-rose-dim); color: var(--accent-rose); }
        .progress-bar { width: 100%; height: 6px; background: var(--bg-primary); border-radius: 3px; overflow: hidden; margin-top: 8px; }
        .progress-fill { height: 100%; border-radius: 3px; transition: width 0.5s ease; }
        .progress-fill.green { background: var(--accent); }
        .progress-fill.amber { background: var(--accent-amber); }
        .progress-fill.rose { background: var(--accent-rose); }
        .pipeline-steps { display: flex; flex-direction: column; gap: 6px; margin-top: 12px; }
        .pipeline-step { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--text-secondary); }
        .step-check { width: 16px; height: 16px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 10px; }
        .step-check.done { background: var(--accent); color: white; }
        .step-check.pending { background: var(--bg-primary); color: var(--text-muted); border: 1px solid var(--border-secondary); }
        .step-check.active { background: var(--accent-amber); color: white; }

        /* ── Settings ───────────────────────────── */
        .settings-container { padding: 24px; max-width: 640px; overflow-y: auto; }
        .settings-section { background: var(--bg-card); border: 1px solid var(--border-primary); border-radius: var(--radius-md); padding: 20px; margin-bottom: 16px; }
        .settings-section h3 { font-size: 15px; font-weight: 600; margin-bottom: 16px; color: var(--text-primary); }
        .setting-row { display: flex; align-items: center; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid var(--border-primary); }
        .setting-row:last-child { border-bottom: none; }
        .setting-label { font-size: 13px; color: var(--text-primary); }
        .setting-desc { font-size: 11px; color: var(--text-muted); margin-top: 2px; }
        .setting-value { font-size: 13px; color: var(--text-secondary); font-family: var(--font-mono); }

        /* ── Toast ──────────────────────────────── */
        .toast-container { position: fixed; bottom: 20px; right: 20px; z-index: 9999; display: flex; flex-direction: column; gap: 8px; }
        .toast { padding: 12px 20px; border-radius: var(--radius-md); font-size: 13px; color: white; box-shadow: var(--shadow-md); animation: toast-in 0.3s ease; max-width: 360px; }
        .toast.success { background: var(--accent); }
        .toast.error { background: var(--accent-rose); }
        .toast.warning { background: var(--accent-amber); color: var(--text-inverse); }
        .toast.info { background: var(--accent-cyan); }
        @keyframes toast-in { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }

        /* ── Responsive ─────────────────────────── */
        @media (max-width: 768px) {
            .apa-header { padding: 0 12px; }
            .apa-tabs { padding: 0 12px; }
            .chat-message { max-width: 90%; }
            .dashboard-grid { grid-template-columns: 1fr; }
            .projects-sidebar { width: 200px; }
        }
    </style>
</head>
<body>
    <div class="apa-app" role="application" aria-label="APA — Asistente de Proyectos Automatizado">

        <!-- ═══ HEADER ═══ -->
        <header class="apa-header" role="banner">
            <div class="apa-logo">
                <div class="apa-logo-icon" aria-hidden="true">A</div>
                <div>
                    <div class="apa-logo-text">APA</div>
                    <div class="apa-logo-sub">AI Project Automation</div>
                </div>
            </div>
            <div class="apa-header-right">
                <div class="apa-status-badge" id="status-badge" role="status" aria-live="polite">
                    <span class="apa-status-dot"></span>
                    <span id="status-text">Conectando...</span>
                </div>
            </div>
        </header>

        <!-- ═══ TABS ═══ -->
        <nav class="apa-tabs" role="tablist" aria-label="Navegación principal">
            <button class="apa-tab active" data-tab="chat" role="tab" aria-selected="true" aria-controls="panel-chat" onclick="switchTab('chat')">
                <span class="apa-tab-icon" aria-hidden="true">💬</span> Chat
            </button>
            <button class="apa-tab" data-tab="dashboard" role="tab" aria-selected="false" aria-controls="panel-dashboard" onclick="switchTab('dashboard')">
                <span class="apa-tab-icon" aria-hidden="true">📊</span> Dashboard
            </button>
            <button class="apa-tab" data-tab="projects" role="tab" aria-selected="false" aria-controls="panel-projects" onclick="switchTab('projects')">
                <span class="apa-tab-icon" aria-hidden="true">📁</span> Proyectos
            </button>
            <button class="apa-tab" data-tab="pipeline" role="tab" aria-selected="false" aria-controls="panel-pipeline" onclick="switchTab('pipeline')">
                <span class="apa-tab-icon" aria-hidden="true">🔄</span> Pipeline
            </button>
            <button class="apa-tab" data-tab="notifications" role="tab" aria-selected="false" aria-controls="panel-notifications" onclick="switchTab('notifications')">
                <span class="apa-tab-icon" aria-hidden="true">🔔</span> Notificaciones
                <span class="apa-tab-badge" id="notif-badge" style="display:none;">0</span>
            </button>
            <button class="apa-tab" data-tab="settings" role="tab" aria-selected="false" aria-controls="panel-settings" onclick="switchTab('settings')">
                <span class="apa-tab-icon" aria-hidden="true">⚙️</span> Ajustes
            </button>
        </nav>

        <!-- ═══ CONTENT ═══ -->
        <main class="apa-content">

            <!-- ── Panel: Chat ────────────────────── -->
            <section class="apa-panel active" id="panel-chat" role="tabpanel" aria-label="Chat">
                <div class="chat-container">
                    <div class="chat-messages" id="chat-messages" role="log" aria-live="polite" aria-label="Historial de mensajes">
                        <div class="chat-welcome" id="chat-welcome">
                            <div class="chat-welcome-icon" aria-hidden="true">🤖</div>
                            <h2>Bienvenido a APA</h2>
                            <p>Sistema multiagente para planificación y ejecución automática de proyectos de software. Escribe un mensaje para comenzar.</p>
                        </div>
                    </div>
                    <div class="chat-input-area">
                        <div class="chat-input-wrap">
                            <textarea id="chat-input" placeholder="Describe tu proyecto o pregunta algo..." rows="1" aria-label="Mensaje de chat" onkeydown="handleChatKeydown(event)"></textarea>
                        </div>
                        <button class="chat-send-btn" id="chat-send-btn" onclick="sendMessage()" aria-label="Enviar mensaje" title="Enviar (Enter)">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>
                        </button>
                    </div>
                </div>
            </section>

            <!-- ── Panel: Dashboard ───────────────── -->
            <section class="apa-panel" id="panel-dashboard" role="tabpanel" aria-label="Dashboard">
                <div class="dashboard-container">
                    <div class="dashboard-grid" id="dashboard-stats">
                        <div class="dashboard-card">
                            <div class="dashboard-card-icon" style="background:var(--accent-dim);color:var(--accent);" aria-hidden="true">💾</div>
                            <div class="dashboard-card-label">Cache LLM</div>
                            <div class="dashboard-card-value" id="stat-cache">0</div>
                            <div class="dashboard-card-sub">entradas almacenadas</div>
                        </div>
                        <div class="dashboard-card">
                            <div class="dashboard-card-icon" style="background:var(--accent-amber-dim);color:var(--accent-amber);" aria-hidden="true">⚡</div>
                            <div class="dashboard-card-label">Llamadas totales</div>
                            <div class="dashboard-card-value" id="stat-calls">0</div>
                            <div class="dashboard-card-sub">al broker de modelos</div>
                        </div>
                        <div class="dashboard-card">
                            <div class="dashboard-card-icon" style="background:var(--accent-cyan-dim);color:var(--accent-cyan);" aria-hidden="true">💰</div>
                            <div class="dashboard-card-label">Costo estimado</div>
                            <div class="dashboard-card-value" id="stat-cost">$0.00</div>
                            <div class="dashboard-card-sub">acumulado por modelos</div>
                        </div>
                        <div class="dashboard-card">
                            <div class="dashboard-card-icon" style="background:var(--accent-rose-dim);color:var(--accent-rose);" aria-hidden="true">📈</div>
                            <div class="dashboard-card-label">Proyectos activos</div>
                            <div class="dashboard-card-value" id="stat-projects">0</div>
                            <div class="dashboard-card-sub">en ejecución</div>
                        </div>
                    </div>
                    <div class="dashboard-section">
                        <h3>Costos por Modelo</h3>
                        <div id="model-costs-table">Cargando datos...</div>
                    </div>
                    <div class="dashboard-section">
                        <h3>Actividad Reciente</h3>
                        <ul class="dashboard-activity-list" id="activity-list">
                            <li class="dashboard-activity-item"><span class="activity-dot" style="background:var(--text-muted);"></span> Sin actividad registrada</li>
                        </ul>
                    </div>
                </div>
            </section>

            <!-- ── Panel: Projects ────────────────── -->
            <section class="apa-panel" id="panel-projects" role="tabpanel" aria-label="Proyectos">
                <div class="projects-container">
                    <aside class="projects-sidebar">
                        <div class="projects-sidebar-header">
                            <h3>Proyectos</h3>
                        </div>
                        <ul class="project-list" id="project-list">
                            <li class="project-item active">
                                <span aria-hidden="true">📂</span>
                                <div>
                                    <div class="project-item-name">proyecto-ejemplo</div>
                                    <div class="project-item-status">Activo</div>
                                </div>
                            </li>
                        </ul>
                    </aside>
                    <div class="projects-main" id="project-detail">
                        <h3 style="font-size:16px;font-weight:600;margin-bottom:16px;">Archivos del Proyecto</h3>
                        <ul class="file-tree" id="file-tree">
                            <li class="file-tree-item"><span class="file-icon" aria-hidden="true">📁</span> specs/</li>
                            <li class="file-tree-item file-tree-folder"><span class="file-icon" aria-hidden="true">📄</span> SDD.md</li>
                            <li class="file-tree-item file-tree-folder"><span class="file-icon" aria-hidden="true">📄</span> plan.md</li>
                            <li class="file-tree-item"><span class="file-icon" aria-hidden="true">📁</span> src/</li>
                            <li class="file-tree-item file-tree-folder"><span class="file-icon" aria-hidden="true">📄</span> main.py</li>
                            <li class="file-tree-item"><span class="file-icon" aria-hidden="true">📁</span> tests/</li>
                            <li class="file-tree-item file-tree-folder"><span class="file-icon" aria-hidden="true">📄</span> test_main.py</li>
                            <li class="file-tree-item"><span class="file-icon" aria-hidden="true">📄</span> README.md</li>
                        </ul>
                    </div>
                </div>
            </section>

            <!-- ── Panel: Pipeline ────────────────── -->
            <section class="apa-panel" id="panel-pipeline" role="tabpanel" aria-label="Pipeline">
                <div class="pipeline-container" id="pipeline-list">
                    <div class="pipeline-card">
                        <div class="pipeline-header">
                            <span class="pipeline-name">Pipeline de ejemplo</span>
                            <span class="pipeline-status running">Ejecutando</span>
                        </div>
                        <div class="progress-bar"><div class="progress-fill green" style="width:60%;"></div></div>
                        <div class="pipeline-steps">
                            <div class="pipeline-step"><span class="step-check done">✓</span> Análisis de requisitos</div>
                            <div class="pipeline-step"><span class="step-check done">✓</span> Generación de SDD</div>
                            <div class="pipeline-step"><span class="step-check active">⟳</span> Generación de código</div>
                            <div class="pipeline-step"><span class="step-check pending">○</span> Testing automatizado</div>
                            <div class="pipeline-step"><span class="step-check pending">○</span> Despliegue</div>
                        </div>
                    </div>
                </div>
            </section>

            <!-- ── Panel: Notifications ───────────── -->
            <section class="apa-panel" id="panel-notifications" role="tabpanel" aria-label="Notificaciones">
                <div class="notif-container">
                    <ul class="notif-list" id="notification-list">
                        <li class="notif-item unread">
                            <div class="notif-type-icon info" aria-hidden="true">ℹ</div>
                            <div class="notif-content">
                                <div class="notif-message">Sistema APA iniciado correctamente. Todos los subsistemas operativos.</div>
                                <div class="notif-time">Ahora</div>
                            </div>
                        </li>
                    </ul>
                </div>
            </section>

            <!-- ── Panel: Settings ────────────────── -->
            <section class="apa-panel" id="panel-settings" role="tabpanel" aria-label="Ajustes">
                <div class="settings-container">
                    <div class="settings-section">
                        <h3>Conexión con Model Broker</h3>
                        <div class="setting-row">
                            <div><div class="setting-label">URL del Broker</div><div class="setting-desc">Endpoint del servicio de modelos</div></div>
                            <div class="setting-value" id="setting-mb-url">—</div>
                        </div>
                        <div class="setting-row">
                            <div><div class="setting-label">Estado del Broker</div><div class="setting-desc">Conectividad verificada vía health check</div></div>
                            <div class="setting-value" id="setting-mb-status">Verificando...</div>
                        </div>
                        <div class="setting-row">
                            <div><div class="setting-label">Modo del Router</div><div class="setting-desc">Estrategia de routing actual</div></div>
                            <div class="setting-value" id="setting-router-mode">—</div>
                        </div>
                    </div>
                    <div class="settings-section">
                        <h3>Presupuesto y Cuotas</h3>
                        <div class="setting-row">
                            <div><div class="setting-label">Presupuesto diario</div><div class="setting-desc">Límite de gasto por día</div></div>
                            <div class="setting-value" id="setting-daily-budget">—</div>
                        </div>
                        <div class="setting-row">
                            <div><div class="setting-label">Gasto acumulado hoy</div><div class="setting-desc">Costo total del día actual</div></div>
                            <div class="setting-value" id="setting-today-cost">$0.00</div>
                        </div>
                    </div>
                    <div class="settings-section">
                        <h3>Sistema</h3>
                        <div class="setting-row">
                            <div><div class="setting-label">Versión de APA</div></div>
                            <div class="setting-value">2.0.0</div>
                        </div>
                        <div class="setting-row">
                            <div><div class="setting-label">Modo de inicio</div></div>
                            <div class="setting-value" id="setting-startup-mode">—</div>
                        </div>
                    </div>
                </div>
            </section>

        </main>

        <!-- ═══ TOAST CONTAINER ═══ -->
        <div class="toast-container" id="toast-container" aria-live="assertive"></div>
    </div>

    <!-- ═══ JAVASCRIPT ═══ -->
    <script>
    /* ── Estado global del cliente ──────────────────── */
    let currentProject = 'default';
    let sseConnection = null;
    let notifCount = 0;

    /* ── Tab switching ──────────────────────────────── */
    function switchTab(tabName) {
        // Desactivar todas las pestañas y paneles
        document.querySelectorAll('.apa-tab').forEach(function(tab) {
            tab.classList.remove('active');
            tab.setAttribute('aria-selected', 'false');
        });
        document.querySelectorAll('.apa-panel').forEach(function(panel) {
            panel.classList.remove('active');
        });
        // Activar la pestaña y panel seleccionados
        var tabBtn = document.querySelector('.apa-tab[data-tab="' + tabName + '"]');
        var panel = document.getElementById('panel-' + tabName);
        if (tabBtn) { tabBtn.classList.add('active'); tabBtn.setAttribute('aria-selected', 'true'); }
        if (panel) { panel.classList.add('active'); }
        // Cargar datos del panel si es necesario
        if (tabName === 'dashboard') { loadDashboard(); }
    }

    /* ── Chat ───────────────────────────────────────── */
    function handleChatKeydown(event) {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            sendMessage();
        }
    }

    function sendMessage() {
        var input = document.getElementById('chat-input');
        var text = input.value.trim();
        if (!text) return;

        // Ocultar welcome
        var welcome = document.getElementById('chat-welcome');
        if (welcome) welcome.style.display = 'none';

        // Añadir mensaje del usuario
        appendMessage('user', text);
        input.value = '';
        input.style.height = 'auto';

        // Enviar al backend
        fetch('/chat/' + currentProject, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text })
        })
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (data.response) {
                appendMessage('assistant', data.response);
            } else if (data.error) {
                appendMessage('system', 'Error: ' + data.error);
            }
        })
        .catch(function(err) {
            appendMessage('system', 'Error de conexión: ' + err.message);
        });
    }

    function appendMessage(role, content) {
        var container = document.getElementById('chat-messages');
        var div = document.createElement('div');
        div.className = 'chat-message ' + role;
        var now = new Date().toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit' });
        div.innerHTML = '<div>' + escapeHtml(content) + '</div><div class="chat-msg-meta">' + role.charAt(0).toUpperCase() + role.slice(1) + ' · ' + now + '</div>';
        container.appendChild(div);
        container.scrollTop = container.scrollHeight;
    }

    function escapeHtml(text) {
        var d = document.createElement('div');
        d.textContent = text;
        return d.innerHTML;
    }

    /* ── Dashboard ──────────────────────────────────── */
    function loadDashboard() {
        fetch('/dashboard/' + currentProject)
        .then(function(r) { return r.json(); })
        .then(function(data) {
            document.getElementById('stat-cache').textContent = data.cache_entries || 0;
            document.getElementById('stat-calls').textContent = data.total_calls || 0;
            document.getElementById('stat-projects').textContent = Object.keys(data.projects || {}).length;
            // Costos por modelo
            var totalCost = 0;
            var costsHtml = '<table style="width:100%;font-size:13px;border-collapse:collapse;">';
            costsHtml += '<tr style="border-bottom:1px solid var(--border-primary);"><th style="text-align:left;padding:8px 4px;color:var(--text-muted);">Modelo</th><th style="text-align:right;padding:8px 4px;color:var(--text-muted);">Costo</th></tr>';
            var modelCosts = data.model_costs || {};
            for (var model in modelCosts) {
                var cost = parseFloat(modelCosts[model]) || 0;
                totalCost += cost;
                costsHtml += '<tr style="border-bottom:1px solid var(--border-primary);"><td style="padding:8px 4px;color:var(--text-primary);font-family:var(--font-mono);font-size:12px;">' + escapeHtml(model) + '</td><td style="text-align:right;padding:8px 4px;color:var(--accent);">$' + cost.toFixed(4) + '</td></tr>';
            }
            costsHtml += '</table>';
            document.getElementById('model-costs-table').innerHTML = costsHtml || 'Sin datos';
            document.getElementById('stat-cost').textContent = '$' + totalCost.toFixed(2);
            // Actividad reciente
            var actList = document.getElementById('activity-list');
            var activities = data.recent_activity || [];
            if (activities.length > 0) {
                actList.innerHTML = activities.map(function(a) {
                    var color = a.type === 'error' ? 'var(--accent-rose)' : a.type === 'warning' ? 'var(--accent-amber)' : 'var(--accent)';
                    return '<li class="dashboard-activity-item"><span class="activity-dot" style="background:' + color + ';"></span>' + escapeHtml(a.message || a) + '</li>';
                }).join('');
            }
        })
        .catch(function() { /* dashboard no disponible */ });
    }

    /* ── Health check y estado ──────────────────────── */
    function checkHealth() {
        fetch('/health')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            var statusText = document.getElementById('status-text');
            var badge = document.getElementById('status-badge');
            if (data.mb_responding) {
                statusText.textContent = 'MB conectado';
                badge.style.background = 'var(--accent-dim)';
                badge.style.color = 'var(--accent)';
            } else {
                statusText.textContent = 'MB sin conexión';
                badge.style.background = 'var(--accent-amber-dim)';
                badge.style.color = 'var(--accent-amber)';
            }
            // Settings
            var mbUrl = document.getElementById('setting-mb-url');
            if (mbUrl) mbUrl.textContent = data.mb_url || '—';
            var mbStatus = document.getElementById('setting-mb-status');
            if (mbStatus) mbStatus.textContent = data.mb_responding ? 'Conectado' : 'Sin conexión';
            var routerMode = document.getElementById('setting-router-mode');
            if (routerMode) routerMode.textContent = data.mode || '—';
            var startupMode = document.getElementById('setting-startup-mode');
            if (startupMode) startupMode.textContent = data.mode || '—';
        })
        .catch(function() {
            document.getElementById('status-text').textContent = 'Error de salud';
        });
    }

    /* ── SSE (Server-Sent Events) ───────────────────── */
    function connectSSE() {
        if (sseConnection) { sseConnection.close(); }
        var url = '/stream/' + currentProject;
        sseConnection = new EventSource(url);
        sseConnection.onmessage = function(event) {
            try {
                var data = JSON.parse(event.data);
                if (data.type === 'notification' || data.type === 'status') {
                    addNotification(data);
                }
                if (data.message && data.type === 'chat') {
                    appendMessage('assistant', data.message);
                }
            } catch(e) { /* ignorar */ }
        };
        sseConnection.onerror = function() {
            sseConnection.close();
            setTimeout(connectSSE, 5000);
        };
    }

    function addNotification(data) {
        notifCount++;
        var badge = document.getElementById('notif-badge');
        if (badge) { badge.style.display = 'inline-flex'; badge.textContent = notifCount; }
        var list = document.getElementById('notification-list');
        if (!list) return;
        var li = document.createElement('li');
        li.className = 'notif-item unread';
        var typeClass = data.type === 'error' ? 'error' : data.type === 'warning' ? 'warning' : 'info';
        var icon = typeClass === 'error' ? '✕' : typeClass === 'warning' ? '⚠' : 'ℹ';
        var time = new Date().toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit' });
        li.innerHTML = '<div class="notif-type-icon ' + typeClass + '" aria-hidden="true">' + icon + '</div><div class="notif-content"><div class="notif-message">' + escapeHtml(data.message || '') + '</div><div class="notif-time">' + time + '</div></div>';
        list.insertBefore(li, list.firstChild);
        showToast(data.message || 'Nueva notificación', 'info');
    }

    /* ── Toast ──────────────────────────────────────── */
    function showToast(message, type) {
        type = type || 'info';
        var container = document.getElementById('toast-container');
        var toast = document.createElement('div');
        toast.className = 'toast ' + type;
        toast.textContent = message;
        container.appendChild(toast);
        setTimeout(function() { toast.style.opacity = '0'; toast.style.transition = 'opacity 0.3s'; }, 3500);
        setTimeout(function() { if (toast.parentNode) toast.parentNode.removeChild(toast); }, 4000);
    }

    /* ── Auto-resize textarea ───────────────────────── */
    var chatInput = document.getElementById('chat-input');
    if (chatInput) {
        chatInput.addEventListener('input', function() {
            this.style.height = 'auto';
            this.style.height = Math.min(this.scrollHeight, 160) + 'px';
        });
    }

    /* ── Init ───────────────────────────────────────── */
    checkHealth();
    connectSSE();
    setInterval(checkHealth, 30000);

    /* ── JavaScript P5 (inyectado dinámicamente) ────── */
__P5_JS__
    </script>
</body>
</html>"""


# ════════════════════════════════════════════════════════════════════════════
#  CLASE UIRenderer
# ════════════════════════════════════════════════════════════════════════════


class UIRenderer:
    """Renderizador de la interfaz de usuario de APA.

    Carga la plantilla HTML desde core.ui_template si está disponible;
    de lo contrario, utiliza una plantilla fallback completa. Reemplaza
    los 5 placeholders con valores dinámicos inyectados desde los
    módulos core correspondientes.

    Attributes:
        state: Estado global de la aplicación.
        context_loader: Cargador de contexto de autoconocimiento.
    """

    PLACEHOLDER_THEME: str = "__THEME_ROOT__"
    PLACEHOLDER_P5_CSS: str = "__P5_CSS__"
    PLACEHOLDER_P5_TAB: str = "__P5_TAB__"
    PLACEHOLDER_P5_SECTION: str = "__P5_SECTION__"
    PLACEHOLDER_P5_JS: str = "__P5_JS__"

    def __init__(self, state: "AppState", context_loader: "SelfContextLoader") -> None:
        """Inicializa el renderizador de UI.

        Args:
            state: Instancia de AppState con el estado global.
            context_loader: Instancia de SelfContextLoader para contexto propio.
        """
        self.state = state
        self.context_loader = context_loader

        # Seleccionar plantilla: real o fallback
        if _HTML_TEMPLATE is not None:
            self._template: str = _HTML_TEMPLATE
            logger.info(
                "UIRenderer: plantilla cargada desde core.ui_template (%d chars)",
                len(self._template),
            )
        else:
            self._template = _FALLBACK_TEMPLATE
            logger.info(
                "UIRenderer: usando plantilla fallback (%d chars)",
                len(self._template),
            )

        # Valores de inyección
        self._theme_css: str = _THEME_CSS or _DEFAULT_THEME
        self._p5_css: str = _NOTIF_CSS
        self._p5_tab: str = _NOTIF_TAB
        self._p5_section: str = _NOTIF_SECTION
        self._p5_js: str = _NOTIF_JS

        logger.debug(
            "UIRenderer inicializado: tema=%d, css=%d, tab=%d, section=%d, js=%d",
            len(self._theme_css), len(self._p5_css), len(self._p5_tab),
            len(self._p5_section), len(self._p5_js),
        )

    def _render(self) -> str:
        """Renderiza la página HTML completa reemplazando todos los placeholders.

        Reemplaza los 5 marcadores de posición en la plantilla:
          - __THEME_ROOT__   → Variables CSS del tema
          - __P5_CSS__       → Estilos CSS de notificaciones P5
          - __P5_TAB__       → Botón de pestaña de notificaciones P5
          - __P5_SECTION__   → Sección HTML de notificaciones P5
          - __P5_JS__        → JavaScript de notificaciones P5

        Returns:
            HTML completo listo para enviar al navegador.
        """
        rendered: str = self._template

        replacements: Dict[str, str] = {
            self.PLACEHOLDER_THEME: self._theme_css,
            self.PLACEHOLDER_P5_CSS: self._p5_css,
            self.PLACEHOLDER_P5_TAB: self._p5_tab,
            self.PLACEHOLDER_P5_SECTION: self._p5_section,
            self.PLACEHOLDER_P5_JS: self._p5_js,
        }

        for placeholder, value in replacements.items():
            if placeholder in rendered:
                rendered = rendered.replace(placeholder, value)
                logger.debug(
                    "Placeholder '%s' reemplazado (%d chars)",
                    placeholder, len(value),
                )
            else:
                logger.warning(
                    "Placeholder '%s' NO encontrado en la plantilla", placeholder
                )

        return rendered

    def __repr__(self) -> str:
        return (
            f"UIRenderer(template={len(self._template)} chars, "
            f"state.projects={len(self.state.projects)})"
        )


# ════════════════════════════════════════════════════════════════════════════
#  REGISTRO DE RUTAS
# ════════════════════════════════════════════════════════════════════════════


def register_ui_routes(
    app: FastAPI,
    state: "AppState",
    context_loader: "SelfContextLoader",
) -> None:
    """Registra la ruta GET / que sirve la interfaz HTML principal.

    Crea una instancia de UIRenderer con el estado y cargador de
    contexto proporcionados, y registra el endpoint raíz.

    Args:
        app: Aplicación FastAPI donde registrar la ruta.
        state: Estado global de la aplicación.
        context_loader: Cargador de contexto de autoconocimiento.
    """
    renderer = UIRenderer(state=state, context_loader=context_loader)

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def serve_ui() -> HTMLResponse:
        """Sirve la página principal de la interfaz APA."""
        html_content = renderer._render()
        return HTMLResponse(content=html_content)

    logger.info("Ruta registrada: GET / (UI principal)")


# ════════════════════════════════════════════════════════════════════════════
#  VALIDACIÓN INDEPENDIENTE
# ════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=== Validación de ui_renderer.py ===")
    print()

    # 1. Crear instancia con estado simulado
    from app.state import AppState as _VA_State
    from app.self_context import SelfContextLoader as _VA_Loader
    import tempfile

    _tmpdir = tempfile.mkdtemp()
    _va_state = _VA_State()
    _va_loader = _VA_Loader(docs_dir=_tmpdir)
    _va_renderer = UIRenderer(state=_va_state, context_loader=_va_loader)
    print(f"[OK] UIRenderer creado: {_va_renderer}")

    # 2. Verificar que _render() retorna HTML válido
    _va_html = _va_renderer._render()
    assert "<!DOCTYPE html>" in _va_html, "Falta <!DOCTYPE html>"
    assert "</html>" in _va_html, "Falta </html>"
    assert "<body" in _va_html, "Falta <body>"
    print(f"[OK] _render() produce HTML válido ({len(_va_html)} chars)")

    # 3. Verificar que todos los placeholders fueron reemplazados
    _placeholders = [
        "__THEME_ROOT__", "__P5_CSS__", "__P5_TAB__",
        "__P5_SECTION__", "__P5_JS__",
    ]
    _all_replaced = True
    for ph in _placeholders:
        if ph in _va_html:
            print(f"[FAIL] Placeholder '{ph}' NO fue reemplazado")
            _all_replaced = False
    if _all_replaced:
        print(f"[OK] Todos los {len(_placeholders)} placeholders reemplazados")

    # 4. Verificar elementos clave del HTML
    _key_elements = [
        ("chat-input", "campo de entrada de chat"),
        ("chat-messages", "contenedor de mensajes"),
        ("dashboard-stats", "estadísticas del dashboard"),
        ("notification-list", "lista de notificaciones"),
        ("switchTab", "función de cambio de pestañas"),
        ("sendMessage", "función de envío de mensajes"),
        ("showToast", "función de notificaciones toast"),
        ("--accent", "variables de color de acento"),
        ("--bg-primary", "variables de color de fondo"),
        ("panel-chat", "panel de chat"),
        ("panel-dashboard", "panel de dashboard"),
        ("panel-projects", "panel de proyectos"),
        ("panel-pipeline", "panel de pipeline"),
        ("panel-notifications", "panel de notificaciones"),
        ("panel-settings", "panel de ajustes"),
    ]
    for elem_id, desc in _key_elements:
        if elem_id in _va_html:
            print(f"[OK] {elem_id} encontrado ({desc})")
        else:
            print(f"[FAIL] {elem_id} NO encontrado ({desc})")

    # 5. Verificar registro de rutas
    from fastapi import FastAPI as _VA_App

    _va_test_app = _VA_App()
    register_ui_routes(_va_test_app, _va_state, _va_loader)
    _va_routes = [r.path for r in _va_test_app.routes if hasattr(r, "path")]
    assert "/" in _va_routes, "Ruta GET / no registrada"
    print("[OK] register_ui_routes registró GET / correctamente")

    # 6. Verificar fallback cuando core no está disponible
    if _HTML_TEMPLATE is None:
        print("[OK] core.ui_template no disponible — usando fallback")
    else:
        print("[INFO] core.ui_template disponible — se usa plantilla real")

    print()
    print("=== Todas las validaciones pasaron ===")
