# ui_template.py - Template HTML/CSS/JS de la interfaz APA.
#
# Extraido de app.py para separar la logica de la presentacion.
# Contiene la pagina completa con pestañas, estilos y JavaScript.

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>APA — Agente de Programacion Autonoma</title>
    <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🤖</text></svg>">
    <link rel="stylesheet" href="/static/apa_theme.css">
    <style>
        /* ===== DESIGN TOKENS — injected from apa_theme.py ===== */
        __THEME_ROOT__
        :root {
            --shadow-sm: 0 1px 3px rgba(0,0,0,0.4);
            --shadow-md: 0 4px 12px rgba(0,0,0,0.5);
            --transition: 0.15s ease;
        }

        /* ===== RESET & BASE ===== */
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: var(--font-sans);
            background: var(--bg-body);
            color: var(--text-primary);
            min-height: 100vh;
            line-height: 1.5;
            -webkit-font-smoothing: antialiased;
        }

        /* ===== SCROLLBAR ===== */
        ::-webkit-scrollbar { width: 8px; height: 8px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: var(--border-default); border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: var(--text-muted); }

        /* ===== LAYOUT ===== */
        .container {
            max-width: 1100px;
            margin: 0 auto;
            padding: 24px 28px 40px;
        }
        @media (max-width: 768px) {
            .container { padding: 16px 12px 32px; }
        }

        /* ===== HEADER ===== */
        .header {
            display: flex;
            align-items: baseline;
            gap: 12px;
            margin-bottom: 28px;
            padding-bottom: 20px;
            border-bottom: 1px solid var(--border-muted);
        }
        .header h1 {
            font-size: 1.6rem;
            font-weight: 700;
            color: var(--text-primary);
            letter-spacing: -0.02em;
        }
        .header .subtitle {
            font-size: 0.85rem;
            color: var(--text-muted);
            font-weight: 400;
        }

        /* ===== TABS ===== */
        .tabs {
            display: flex;
            gap: 2px;
            margin-bottom: 0;
            border-bottom: 1px solid var(--border-default);
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
        }
        .tab {
            position: relative;
            padding: 10px 20px;
            cursor: pointer;
            border: none;
            background: transparent;
            font-family: var(--font-sans);
            font-size: 0.85rem;
            font-weight: 500;
            color: var(--text-muted);
            transition: color var(--transition);
            white-space: nowrap;
            border-bottom: 2px solid transparent;
            margin-bottom: -1px;
        }
        .tab:hover { color: var(--text-secondary); }
        .tab.active {
            color: var(--accent);
            border-bottom-color: var(--accent);
        }

        /* ===== SECTIONS ===== */
        .tab-content { display: none !important; padding-top: 24px; }
        .tab-content.active { display: block !important; }

        /* ===== FORM CONTROLS ===== */
        label {
            display: block;
            font-size: 0.82rem;
            font-weight: 600;
            color: var(--text-secondary);
            margin-bottom: 6px;
            letter-spacing: 0.02em;
        }
        input[type="text"], select, textarea {
            width: 100%;
            padding: 9px 12px;
            border: 1px solid var(--border-default);
            border-radius: var(--radius-sm);
            font-family: var(--font-mono);
            font-size: 0.85rem;
            background: var(--bg-input);
            color: var(--text-primary);
            transition: border-color var(--transition), box-shadow var(--transition);
            box-sizing: border-box;
        }
        input[type="text"]:focus, select:focus, textarea:focus {
            outline: none;
            border-color: var(--accent);
            box-shadow: 0 0 0 3px var(--accent-bg);
        }
        textarea { min-height: 160px; resize: vertical; line-height: 1.6; }
        select { cursor: pointer; appearance: auto; }
        .field { margin-bottom: 16px; }
        .field-row { display: flex; gap: 12px; }
        .field-row .field { flex: 1; }
        @media (max-width: 600px) { .field-row { flex-direction: column; gap: 0; } }

        /* ===== BUTTONS ===== */
        button {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
            padding: 9px 20px;
            border: 1px solid var(--border-default);
            border-radius: var(--radius-sm);
            background: var(--bg-elevated);
            color: var(--text-primary);
            font-family: var(--font-sans);
            font-size: 0.85rem;
            font-weight: 500;
            cursor: pointer;
            transition: background var(--transition), border-color var(--transition), transform 0.1s;
            line-height: 1.4;
        }
        button:hover { background: var(--bg-hover); border-color: var(--text-muted); }
        button:active { transform: scale(0.98); }
        button:disabled { opacity: 0.5; cursor: not-allowed; }
        button.primary {
            background: var(--accent-bg);
            color: var(--accent);
            border-color: rgba(232,168,56,0.4);
        }
        button.primary:hover { background: rgba(232,168,56,0.25); border-color: var(--accent); }
        button.danger {
            background: var(--red-bg);
            color: var(--red);
            border-color: rgba(248,81,73,0.4);
        }
        .btn-row { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }

        /* ===== STATUS / BADGES ===== */
        .badge {
            display: inline-flex;
            align-items: center;
            padding: 3px 10px;
            border-radius: 20px;
            font-size: 0.75rem;
            font-weight: 600;
            letter-spacing: 0.02em;
        }
        .badge.pending { background: var(--amber-bg); color: var(--amber); }
        .badge.running { background: var(--accent-bg); color: var(--accent); }
        .badge.completed { background: var(--green-bg); color: var(--green); }
        .badge.failed { background: var(--red-bg); color: var(--red); }
        .badge.resuming { background: var(--purple-bg); color: var(--purple); }

        @keyframes pulse-dot {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.4; }
        }
        .badge.running::before {
            content: '';
            display: inline-block;
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: var(--accent);
            margin-right: 6px;
            animation: pulse-dot 1.4s ease-in-out infinite;
        }

        /* ===== PROGRESS BAR ===== */
        .progress-bar {
            height: 6px;
            background: var(--bg-input);
            border-radius: 3px;
            overflow: hidden;
            margin: 8px 0;
        }
        .progress-fill {
            height: 100%;
            background: var(--accent);
            border-radius: 3px;
            transition: width 0.4s ease;
        }
        .progress-fill.green { background: var(--green); }
        .progress-fill.red { background: var(--red); }

        /* ===== CHAT ===== */
        .chat-layout {
            display: flex;
            flex-direction: column;
            height: calc(100vh - 260px);
            min-height: 300px;
            border: 1px solid var(--border-default);
            border-radius: var(--radius-md);
            overflow: hidden;
        }
        @media (max-width: 768px) {
            .chat-layout { height: calc(100vh - 230px); }
        }
        .chat-messages {
            flex: 1;
            overflow-y: auto;
            padding: 16px;
            background: var(--bg-surface);
            display: flex;
            flex-direction: column;
            gap: 12px;
        }
        .chat-empty {
            flex: 1;
            display: flex;
            align-items: center;
            justify-content: center;
            color: var(--text-muted);
            font-size: 0.9rem;
        }
        .chat-message { display: flex; max-width: 85%; }
        .chat-message.user { align-self: flex-end; }
        .chat-message.assistant { align-self: flex-start; }
        .chat-bubble {
            padding: 10px 14px;
            border-radius: var(--radius-lg);
            word-wrap: break-word;
            line-height: 1.55;
            font-size: 0.9rem;
        }
        .user .chat-bubble {
            background: var(--accent);
            color: #fff;
            border-bottom-right-radius: 4px;
        }
        .assistant .chat-bubble {
            background: var(--bg-elevated);
            color: var(--text-primary);
            border: 1px solid var(--border-default);
            border-bottom-left-radius: 4px;
        }
        .chat-bubble code {
            background: rgba(110,118,129,0.2);
            padding: 1px 5px;
            border-radius: 3px;
            font-family: var(--font-mono);
            font-size: 0.82rem;
        }
        .chat-bubble pre {
            background: var(--bg-input);
            border: 1px solid var(--border-default);
            border-radius: var(--radius-sm);
            padding: 10px 12px;
            margin: 8px 0 4px;
            overflow-x: auto;
            font-family: var(--font-mono);
            font-size: 0.82rem;
            line-height: 1.5;
        }
        .chat-input-area {
            display: flex;
            gap: 8px;
            padding: 12px;
            border-top: 1px solid var(--border-default);
            background: var(--bg-elevated);
        }
        .chat-input-area textarea {
            min-height: 44px;
            max-height: 120px;
            resize: none;
            font-family: var(--font-sans);
            font-size: 0.9rem;
            border-radius: var(--radius-sm);
            flex: 1;
        }
        .chat-input-area button { flex-shrink: 0; padding: 10px 16px; }
        .chat-meta {
            font-size: 0.72rem;
            color: var(--text-muted);
            margin-top: 2px;
        }

        /* ===== TABLES ===== */
        .data-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 16px;
        }
        .data-table th, .data-table td {
            padding: 10px 14px;
            text-align: left;
            border-bottom: 1px solid var(--border-muted);
            font-size: 0.85rem;
        }
        .data-table th {
            background: var(--bg-elevated);
            font-weight: 600;
            color: var(--text-secondary);
            font-size: 0.78rem;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            position: sticky;
            top: 0;
        }
        .data-table tr:hover td { background: var(--bg-hover); }
        .data-table .id-cell {
            font-family: var(--font-mono);
            font-size: 0.78rem;
            color: var(--text-muted);
        }

        /* ===== DASHBOARD CARDS ===== */
        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 12px;
            margin-top: 16px;
        }
        .metric-card {
            background: var(--bg-surface);
            border: 1px solid var(--border-default);
            border-radius: var(--radius-md);
            padding: 16px;
            transition: border-color var(--transition);
        }
        .metric-card:hover { border-color: var(--text-muted); }
        .metric-card .metric-label {
            font-size: 0.75rem;
            font-weight: 600;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 6px;
        }
        .metric-card .metric-value {
            font-size: 1.4rem;
            font-weight: 700;
            color: var(--text-primary);
        }
        .metric-card .metric-detail {
            font-size: 0.78rem;
            color: var(--text-muted);
            margin-top: 4px;
        }
        .detail-section {
            margin-top: 20px;
            padding-top: 16px;
            border-top: 1px solid var(--border-muted);
        }
        .detail-section h3 {
            font-size: 0.85rem;
            font-weight: 600;
            color: var(--text-secondary);
            margin-bottom: 12px;
        }

        /* ===== ANALYZE RESULT ===== */
        #analyze-result {
            display: none;
            margin-top: 20px;
            padding: 16px;
            background: var(--bg-surface);
            border: 1px solid var(--border-default);
            border-radius: var(--radius-md);
        }
        #analyze-stats { font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 12px; line-height: 1.7; }
        #generated-spec { min-height: 250px; }

        /* ===== NOTIFICATION / ALERT BOX ===== */
        .alert {
            padding: 12px 16px;
            border-radius: var(--radius-sm);
            margin: 12px 0;
            font-size: 0.85rem;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .alert.info { background: var(--accent-bg); color: var(--accent); border: 1px solid rgba(232,168,56,0.3); }
        .alert.success { background: var(--green-bg); color: var(--green); border: 1px solid rgba(63,185,80,0.3); }
        .alert.error { background: var(--red-bg); color: var(--red); border: 1px solid rgba(248,81,73,0.3); }
        .alert.warning { background: var(--amber-bg); color: var(--amber); border: 1px solid rgba(210,153,34,0.3); }

        /* ===== SECTION TITLES ===== */
        .section-title {
            font-size: 1.05rem;
            font-weight: 600;
            color: var(--text-primary);
            margin-bottom: 6px;
        }
        .section-desc {
            font-size: 0.85rem;
            color: var(--text-muted);
            margin-bottom: 20px;
            line-height: 1.5;
        }

        /* ===== COST INDICATORS ===== */
        .cost-estimated { color: var(--amber); }
        .cost-estimated::after { content: "~"; margin-left: 2px; }
        .cost-real { color: var(--green); }

        /* ===== UTILITIES ===== */
        .mt-4 { margin-top: 16px; }
        .mt-6 { margin-top: 24px; }
        .mb-2 { margin-bottom: 8px; }
        .text-muted { color: var(--text-muted); }
        .text-sm { font-size: 0.82rem; }
        .hidden { display: none !important; }

        /* ===== TOOLTIP ===== */
        .tooltip {
            position: relative;
            cursor: help;
        }
        .tooltip .tooltip-text {
            visibility: hidden;
            background: var(--bg-elevated);
            color: var(--text-primary);
            text-align: center;
            border: 1px solid var(--border-default);
            border-radius: var(--radius-sm);
            padding: 8px 12px;
            position: absolute;
            z-index: 10;
            bottom: calc(100% + 6px);
            left: 50%;
            transform: translateX(-50%);
            opacity: 0;
            transition: opacity 0.2s;
            font-size: 0.75rem;
            white-space: nowrap;
            pointer-events: none;
        }
        .tooltip:hover .tooltip-text { visibility: visible; opacity: 1; }

        /* ===== LINKS ===== */
        a { color: var(--accent); text-decoration: none; }
        a:hover { text-decoration: underline; }
        code { background: var(--bg-elevated); padding: 2px 6px; border-radius: 3px; font-family: var(--font-mono); font-size: 0.85rem; color: var(--text-primary); border: 1px solid var(--border-muted); }

        /* ===== FASE 4: AGENT CARDS (UX2) ===== */
        @keyframes agent-pulse {
            0%, 100% { box-shadow: 0 0 0 0 rgba(6,182,212,0.4); }
            50% { box-shadow: 0 0 0 8px rgba(6,182,212,0); }
        }
        @keyframes agent-dot-blink {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.3; }
        }
        #agent-cards-container {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 16px;
            margin-top: 16px;
        }
        .agent-card {
            background: var(--bg-surface);
            border: 2px solid var(--border-default);
            border-radius: var(--radius-md);
            overflow: hidden;
            transition: border-color 0.3s, box-shadow 0.3s;
        }
        .agent-card.active {
            border-color: var(--agent-active);
            animation: agent-pulse 2s ease-in-out infinite;
        }
        .agent-card.done {
            border-color: var(--agent-done);
            opacity: 0.7;
        }
        .agent-card.failed {
            border-color: var(--agent-failed);
            background: var(--red-bg);
        }
        .agent-card.idle {
            border-color: var(--border-muted);
            opacity: 0.5;
        }
        .agent-card-header {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 14px 16px;
        }
        .agent-icon {
            width: 38px;
            height: 38px;
            border-radius: 50%;
            background: var(--bg-elevated);
            border: 2px solid var(--border-default);
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-size: 0.9rem;
            color: var(--text-muted);
            transition: all 0.3s;
            flex-shrink: 0;
        }
        .agent-card.active .agent-icon {
            border-color: var(--agent-active);
            color: var(--agent-active);
            animation: agent-dot-blink 1.4s ease-in-out infinite;
        }
        .agent-card.done .agent-icon {
            border-color: var(--agent-done);
            color: var(--agent-done);
            background: var(--green-bg);
        }
        .agent-card.failed .agent-icon {
            border-color: var(--agent-failed);
            color: var(--agent-failed);
            background: var(--red-bg);
        }
        .agent-card-info {
            flex: 1;
            min-width: 0;
        }
        .agent-card-name {
            font-weight: 600;
            font-size: 0.9rem;
            color: var(--text-primary);
        }
        .agent-card-model {
            font-family: var(--font-mono);
            font-size: 0.72rem;
            color: var(--text-muted);
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .agent-card-status {
            font-size: 0.7rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            padding: 3px 8px;
            border-radius: 10px;
            background: var(--bg-input);
            color: var(--text-muted);
        }
        .agent-card.active .agent-card-status {
            background: rgba(6,182,212,0.2);
            color: var(--agent-active);
        }
        .agent-card.done .agent-card-status {
            background: var(--green-bg);
            color: var(--green);
        }
        .agent-card.failed .agent-card-status {
            background: var(--red-bg);
            color: var(--red);
        }
        .agent-card-body {
            padding: 0 16px 14px;
            font-size: 0.8rem;
        }
        .agent-card-detail {
            display: flex;
            justify-content: space-between;
            padding: 3px 0;
            color: var(--text-secondary);
        }
        .agent-detail-label {
            color: var(--text-muted);
        }
        .agent-card-progress {
            margin-top: 8px;
        }
        /* ===== FASE 4 UX2+: Task description & context metrics ===== */
        .agent-card-task {
            margin-top: 6px;
            padding: 6px 8px;
            background: var(--bg-input);
            border-radius: 6px;
            font-size: 0.75rem;
            color: var(--text-secondary);
            line-height: 1.4;
            max-height: 3em;
            overflow: hidden;
            text-overflow: ellipsis;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            white-space: normal;
        }
        .agent-card-context {
            display: flex;
            align-items: center;
            gap: 6px;
            margin-top: 6px;
        }
        .agent-card-context-label {
            font-size: 0.7rem;
            color: var(--text-muted);
            white-space: nowrap;
        }
        .agent-context-bar {
            flex: 1;
            height: 4px;
            background: var(--bg-input);
            border-radius: 2px;
            overflow: hidden;
        }
        .agent-context-fill {
            height: 100%;
            border-radius: 2px;
            background: var(--accent);
            transition: width 0.5s ease;
        }
        .agent-context-fill.warn { background: #f59e0b; }
        .agent-context-fill.danger { background: var(--agent-failed); }
        .agent-context-pct {
            font-size: 0.68rem;
            font-family: var(--font-mono);
            color: var(--text-muted);
            min-width: 36px;
            text-align: right;
        }
        /* Hidden cards when no agent is active */
        .agent-card.agent-card-hidden {
            display: none;
        }

        /* ===== P5: Notificaciones — motor unico notification_ui_bridge.py v3.0 ===== */
        <!-- __P5_CSS__ -->

        /* ===== H5: TRANSICIONES ENTRE PESTANAS ===== */
        .tab-content.active { opacity: 1; transform: translateY(0); transition: opacity 0.2s ease, transform 0.2s ease; }
        .tab-content.fade-out { opacity: 0; transform: translateY(6px); }

        /* ===== H5: SPINNER DE CARGA ===== */
        .spinner { display: inline-block; width: 16px; height: 16px; border: 2px solid var(--border-default); border-top-color: var(--accent); border-radius: 50%; animation: spin 0.6s linear infinite; }
        @keyframes spin { to { transform: rotate(360deg); } }
        .spinner-lg { width: 32px; height: 32px; border-width: 3px; }

        /* ===== H5: TOAST NOTIFICATIONS ===== */
        .toast-container { position: fixed; top: 20px; right: 20px; z-index: 9999; display: flex; flex-direction: column; gap: 8px; pointer-events: none; }
        .toast { pointer-events: auto; padding: 12px 18px; border-radius: var(--radius-sm); font-size: 0.85rem; font-family: var(--font-sans); color: var(--text-primary); background: var(--bg-elevated); border: 1px solid var(--border-default); box-shadow: var(--shadow-md); opacity: 0; transform: translateX(40px); transition: opacity 0.3s ease, transform 0.3s ease; max-width: 360px; }
        .toast.show { opacity: 1; transform: translateX(0); }
        .toast.success { border-left: 3px solid var(--green); }
        .toast.error { border-left: 3px solid var(--red); }
        .toast.warning { border-left: 3px solid var(--amber); }
        .toast.info { border-left: 3px solid var(--accent); }

        /* ===== H5: MODAL DE REVISION DE PLAN ===== */
        .modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.6); backdrop-filter: blur(4px); z-index: 1000; display: flex; align-items: center; justify-content: center; opacity: 0; pointer-events: none; transition: opacity 0.25s ease; }
        .modal-overlay.active { opacity: 1; pointer-events: auto; }
        .modal { background: var(--bg-surface); border: 1px solid var(--border-default); border-radius: var(--radius-lg); box-shadow: var(--shadow-md); width: 90%; max-width: 720px; max-height: 80vh; display: flex; flex-direction: column; transform: scale(0.95) translateY(10px); transition: transform 0.25s ease; }
        .modal-overlay.active .modal { transform: scale(1) translateY(0); }
        .modal-header { padding: 20px 24px 16px; border-bottom: 1px solid var(--border-muted); display: flex; align-items: center; justify-content: space-between; }
        .modal-header h2 { font-size: 1.1rem; font-weight: 600; }
        .modal-close { background: none; border: none; color: var(--text-muted); font-size: 1.4rem; cursor: pointer; padding: 4px 8px; line-height: 1; border-radius: var(--radius-sm); }
        .modal-close:hover { background: var(--bg-hover); color: var(--text-primary); }
        .modal-body { padding: 20px 24px; overflow-y: auto; flex: 1; }
        .modal-footer { padding: 16px 24px 20px; border-top: 1px solid var(--border-muted); display: flex; gap: 8px; justify-content: flex-end; }

        /* ===== H5: PLAN TASK LIST (dentro del modal) ===== */
        .plan-task { display: flex; align-items: flex-start; gap: 12px; padding: 12px 0; border-bottom: 1px solid var(--border-muted); }
        .plan-task:last-child { border-bottom: none; }
        .plan-task-num { flex-shrink: 0; width: 28px; height: 28px; border-radius: 50%; background: var(--bg-elevated); border: 1px solid var(--border-default); display: flex; align-items: center; justify-content: center; font-size: 0.75rem; font-weight: 600; color: var(--text-muted); font-family: var(--font-mono); }
        .plan-task-content { flex: 1; min-width: 0; }
        .plan-task-title { font-size: 0.88rem; font-weight: 500; color: var(--text-primary); margin-bottom: 4px; word-break: break-word; }
        .plan-task-meta { font-size: 0.75rem; color: var(--text-muted); }
        .plan-task-deps { font-size: 0.72rem; color: var(--text-muted); font-family: var(--font-mono); margin-top: 4px; }

        /* ===== H5: PROGRESS SECTION ===== */
        .progress-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; flex-wrap: wrap; gap: 8px; }
        .progress-summary { display: flex; gap: 16px; align-items: center; }
        .progress-summary-item { display: flex; align-items: center; gap: 6px; font-size: 0.82rem; color: var(--text-secondary); }
        .progress-summary-item .count { font-weight: 700; font-family: var(--font-mono); }
        .progress-tasks-list { display: flex; flex-direction: column; gap: 2px; }
        .progress-task-row { display: grid; grid-template-columns: 36px 1fr 100px 100px 80px 90px; align-items: center; gap: 8px; padding: 10px 14px; border-radius: var(--radius-sm); transition: background var(--transition); font-size: 0.82rem; }
        .progress-task-row:hover { background: var(--bg-hover); }
        .progress-task-row.header { background: var(--bg-elevated); font-weight: 600; font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.04em; }
        .progress-task-num { font-family: var(--font-mono); color: var(--text-muted); font-size: 0.78rem; text-align: center; }
        .progress-task-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .progress-task-model { font-family: var(--font-mono); font-size: 0.75rem; color: var(--text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .progress-task-time { font-family: var(--font-mono); font-size: 0.78rem; color: var(--text-secondary); text-align: center; }
        @keyframes task-flash { 0% { background: var(--accent-bg); } 100% { background: transparent; } }
        .progress-task-row.just-updated { animation: task-flash 1.5s ease; }
        @media (max-width: 768px) {
            .progress-task-row { grid-template-columns: 28px 1fr 70px; }
            .progress-task-model, .progress-task-time { display: none; }
        }

        /* ===== H5: SELECTION AND ACCESSIBILITY ===== */
        ::selection { background: var(--accent-bg); color: var(--accent); }
        *:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 2px; }

        /* ===== H5: BUTTON LOADING STATE ===== */
        button.loading { position: relative; color: transparent; pointer-events: none; }
        button.loading::after { content: ''; position: absolute; width: 14px; height: 14px; border: 2px solid transparent; border-top-color: var(--accent); border-radius: 50%; animation: spin 0.6s linear infinite; }

        /* ===== H5: EMPTY STATE ===== */
        .empty-state { text-align: center; padding: 48px 24px; }
        .empty-state-icon { font-size: 2.5rem; margin-bottom: 12px; opacity: 0.5; }
        .empty-state-title { font-size: 1rem; font-weight: 600; color: var(--text-secondary); margin-bottom: 6px; }
        .empty-state-desc { font-size: 0.85rem; color: var(--text-muted); max-width: 400px; margin: 0 auto; line-height: 1.5; }

        /* ===== H5: FADE IN ANIMATION ===== */
        @keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
        .fade-in { animation: fadeIn 0.3s ease forwards; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>APA</h1>
            <span class="subtitle">Agente de Programacion Autonoma</span>
        </div>

        <!-- TABS -->
        <div class="tabs" id="tab-bar">
            <button class="tab active" data-tab="chat">Chat</button>
            <button class="tab" data-tab="sdd">SDD</button>
            <button class="tab" data-tab="proyectos">Proyectos</button>
            <button class="tab" data-tab="plan">Plan</button>
            <button class="tab" data-tab="progreso">Progreso</button>
            <button class="tab" data-tab="agentes">Agentes</button>
            <button class="tab" data-tab="notificaciones">Notificaciones</button>
            <button class="tab" data-tab="auditor">Auditor</button>
            <button class="tab" data-tab="dashboard">Dashboard</button>
        </div>

        <!-- ===== CHAT ===== -->
        <div id="chat-section" class="tab-content active">
            <!-- CHAT-R.2: Ubicacion del proyecto + botón buscar + badge de variante -->
            <div style="display:flex; gap:12px; margin-bottom:12px; align-items:center; flex-wrap:wrap;">
                <div style="flex:1; min-width:200px;">
                    <label style="font-size:0.78rem; font-weight:600; color:var(--text-secondary); margin-bottom:4px; display:block;">Ubicacion del proyecto:</label>
                    <div style="display:flex; gap:6px; align-items:center;">
                        <input type="text" id="chat-project-path" value="" placeholder="Ubicacion del proyecto (ej: C:\\Users\\MiProyecto)" style="flex:1; padding:7px 10px; border:1px solid var(--border-default); border-radius:var(--radius-sm); font-family:var(--font-mono); font-size:0.82rem; background:var(--bg-input); color:var(--text-primary);">
                        <button onclick="browseProjectLocation()" style="padding:6px 10px; border:1px solid var(--border-default); border-radius:var(--radius-sm); background:var(--bg-elevated); color:var(--text-secondary); font-size:0.78rem; cursor:pointer; white-space:nowrap;" title="Explorar ubicacion en el sistema de archivos">📂 Buscar</button>
                    </div>
                </div>
                <span id="chat-variant-badge" style="font-size:0.7rem; padding:3px 10px; border-radius:10px; background:var(--border-muted); color:var(--text-muted); white-space:nowrap; display:none;"></span>
            </div>
            <!-- CHAT-R.3: Resumen de la especificación del proyecto (SIEMPRE visible, auto-actualizable por CV1/CV2) -->
            <div id="chat-objective-bar" style="margin-bottom:12px; padding:10px 14px; background:var(--bg-elevated); border:1px solid var(--border-default); border-radius:var(--radius-md);">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                    <span style="font-size:0.75rem; font-weight:600; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.04em;">Resumen de la especificación del proyecto</span>
                    <span id="chat-objective-pct" style="font-size:0.72rem; color:var(--amber);">0%</span>
                </div>
                <div id="chat-objective-text" style="font-size:0.85rem; color:var(--text-secondary); line-height:1.5; min-height:20px; cursor:text; opacity:0.55;" contenteditable="true">A medida que describas tu proyecto, aquí aparecerá un resumen de la especificación del proyecto...</div>
            </div>
            <!-- 3a: Visualizacion de los 18 aspectos de madurez agrupados por tipo -->
            <div id="chat-aspects-section" style="display:none; margin-bottom:12px; padding:10px 14px; background:var(--bg-elevated); border:1px solid var(--border-default); border-radius:var(--radius-md);">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px; cursor:pointer;" onclick="toggleAspects()">
                    <span style="font-size:0.75rem; font-weight:600; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.04em;">Aspectos de la especificacion</span>
                    <span id="chat-aspects-toggle-icon" style="font-size:0.7rem; color:var(--text-muted);">&#9660;</span>
                </div>
                <div id="chat-aspects-list" style="font-size:0.78rem; display:none; max-height:280px; overflow-y:auto;"></div>
            </div>
            <!-- Chat principal -->
            <div class="chat-layout">
                <div style="display:flex; align-items:center; gap:8px; padding:4px 8px; border-bottom:1px solid var(--border-muted);">
                    <span style="font-size:0.75rem; color:var(--text-muted);">Chat con APA</span>
                    <span id="chat-llm-badge" style="font-size:0.68rem; padding:1px 7px; border-radius:10px; background:var(--green); color:#fff; font-family:var(--font-mono); display:none;"></span>
                    <div style="flex:1;"></div>
                    <button onclick="toggleChatHistory()" style="font-size:0.72rem; padding:3px 8px; border:1px solid var(--border-default); border-radius:var(--radius-sm); background:var(--bg-elevated); color:var(--text-secondary); cursor:pointer; white-space:nowrap;" title="Historial de conversaciones guardadas">Historial</button>
                    <button onclick="newChat()" style="font-size:0.72rem; padding:3px 8px; border:1px solid var(--border-default); border-radius:var(--radius-sm); background:var(--bg-elevated); color:var(--text-secondary); cursor:pointer; white-space:nowrap;" title="Nueva conversacion">+ Nueva</button>
                </div>
                <!-- Punto 5: Panel de historial de conversaciones -->
                <div id="chat-history-panel" style="display:none; border-bottom:1px solid var(--border-muted); background:var(--bg-elevated); max-height:240px; overflow-y:auto;">
                    <div style="padding:6px 12px; font-size:0.72rem; font-weight:600; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.04em; border-bottom:1px solid var(--border-muted);">Conversaciones guardadas</div>
                    <div id="chat-history-list"></div>
                </div>
                <div class="chat-messages" id="chat-history">
                    <div class="chat-empty" id="chat-placeholder">Describe tu proyecto en lenguaje natural. Te ayudare a definir claramente que quieres construir.</div>
                </div>
                <div class="chat-input-area">
                    <textarea id="chat-input" placeholder="Escribe tu mensaje... (Enter para enviar, Shift+Enter para salto de linea)" rows="1"></textarea>
                    <button class="primary" id="chat-send-btn" onclick="sendChat()">Enviar</button>
                    <button class="primary" id="create-project-btn" onclick="createFromChat()" style="display:none; margin-left:4px; white-space:nowrap;">Generar la SDD</button>
                </div>
                <!-- CV1: Indicador de madurez SDD -->
                <div id="sdd-indicator" style="display:none; padding:8px 12px; font-size:0.78rem; color:var(--text-muted); border-top:1px solid var(--border-muted); background:var(--bg-elevated);">
                    <span id="sdd-indicator-text"></span>
                </div>
            </div>
            <!-- CHAT-R.1: Panel de spec generada (aparece tras generar SDD) -->
            <div id="chat-spec-panel" style="display:none; margin-top:16px;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                    <h3 style="font-size:0.9rem;font-weight:600;color:var(--text-secondary);">SDD generada (puedes editarla)</h3>
                    <span id="chat-spec-path" style="font-size:0.72rem; color:var(--text-muted); font-family:var(--font-mono);"></span>
                </div>
                <textarea id="chat-generated-spec" style="width:100%; min-height:200px; font-family:var(--font-mono); font-size:0.82rem; padding:12px; border:1px solid var(--border-default); border-radius:var(--radius-md); background:var(--bg-input); color:var(--text-primary); resize:vertical; line-height:1.6;"></textarea>
                <div class="btn-row" style="margin-top:10px;">
                    <button class="primary" id="chat-launch-apa-btn" onclick="launchAPAFromChat()">Lanzar APA</button>
                    <button onclick="closeSpecPanel()" style="color:var(--text-muted);">Cerrar</button>
                </div>
            </div>
        </div>

        <!-- ===== SDD (Spec + Analyze) ===== -->
        <div id="sdd-section" class="tab-content">
            <h2 class="section-title">Especificacion del proyecto (SDD)</h2>
            <p class="section-desc">Escribe la especificacion de tu proyecto en formato Markdown o analiza un proyecto existente. APA generara un plan de tareas y lo ejecutara automaticamente.</p>

            <h3 style="font-size:0.9rem;font-weight:600;color:var(--text-secondary);margin-bottom:8px;">Nueva especificacion</h3>
            <div class="field">
                <label>Especificacion (Markdown):</label>
                <textarea id="spec-input" placeholder="Objetivo: Crear una API REST con..."></textarea>
            </div>
            <div class="btn-row">
                <button class="primary" onclick="runAPA()">Generar Plan</button>
            </div>
            <div id="run-status" class="hidden mt-4"></div>

            <div style="margin-top:24px;padding-top:20px;border-top:1px solid var(--border-muted);">
                <h3 style="font-size:0.9rem;font-weight:600;color:var(--text-secondary);margin-bottom:8px;">Analizar proyecto existente</h3>
                <div class="field-row">
                    <div class="field">
                        <label>Problemas identificados (uno por linea):</label>
                        <textarea id="analyze-problemas" style="min-height:80px" placeholder="Funcion X demasiado larga&#10;Falta manejo de errores"></textarea>
                    </div>
                    <div class="field">
                        <label>Criterios de aceptacion (uno por linea):</label>
                        <textarea id="analyze-criterios" style="min-height:80px" placeholder="Todos los tests pasan&#10;Codigo lint limpio"></textarea>
                    </div>
                </div>
                <div class="btn-row">
                    <button class="primary" onclick="analyzeProject()" id="analyze-btn">Analizar y generar spec</button>
                </div>
                <div id="analyze-result">
                    <div id="analyze-stats"></div>
                    <div class="field mt-4">
                        <label>Spec generada (editable):</label>
                        <textarea id="generated-spec"></textarea>
                    </div>
                    <div class="btn-row">
                        <button class="primary" onclick="runAPAWithSpec()">Generar Plan con esta spec</button>
                    </div>
                </div>
            </div>
        </div>

        <!-- ===== PROYECTOS (Refactorizacion) ===== -->
        <div id="proyectos-section" class="tab-content">
            <h2 class="section-title">Proyectos</h2>
            <p class="section-desc">Explora los proyectos, sus elementos generados (scripts, ficheros de configuracion, carpetas, imagenes) y gestiona su refactorizacion.</p>

            <div class="field-row" style="margin-bottom:16px;">
                <div class="field">
                    <label>Proyecto:</label>
                    <select id="proyectos-select" onchange="loadProjectDetail(this.value)">
                        <option value="">-- Selecciona un proyecto --</option>
                    </select>
                </div>
                <div class="field" style="display:flex;align-items:flex-end;gap:8px;">
                    <button class="primary" onclick="refreshProjectsList()" id="proyectos-refresh-btn">Actualizar lista</button>
                </div>
            </div>

            <div id="proyectos-detail" style="display:none;">
                <div class="detail-section">
                    <h3 style="font-size:0.92rem;font-weight:600;color:var(--text-secondary);margin-bottom:8px;">Informacion del Proyecto</h3>
                    <div id="proyectos-info" style="background:var(--bg-elevated);border:1px solid var(--border-muted);border-radius:var(--radius-sm);padding:12px;font-size:0.85rem;"></div>
                </div>

                <div class="detail-section mt-4">
                    <h3 style="font-size:0.92rem;font-weight:600;color:var(--text-secondary);margin-bottom:8px;">Spec del Proyecto</h3>
                    <div id="proyectos-spec" style="background:var(--bg-elevated);border:1px solid var(--border-muted);border-radius:var(--radius-sm);padding:12px;font-size:0.82rem;font-family:var(--font-mono);max-height:250px;overflow-y:auto;white-space:pre-wrap;color:var(--text-secondary);">
                        <span class="text-muted">Sin spec disponible.</span>
                    </div>
                </div>

                <div class="detail-section mt-4">
                    <h3 style="font-size:0.92rem;font-weight:600;color:var(--text-secondary);margin-bottom:8px;">Plan de Tareas</h3>
                    <div id="proyectos-plan" style="font-size:0.85rem;">
                        <span class="text-muted text-sm">Sin plan disponible.</span>
                    </div>
                </div>

                <div class="detail-section mt-4">
                    <h3 style="font-size:0.92rem;font-weight:600;color:var(--text-secondary);margin-bottom:8px;">Elementos del Proyecto</h3>
                    <div id="proyectos-files" style="background:var(--bg-elevated);border:1px solid var(--border-muted);border-radius:var(--radius-sm);padding:12px;font-size:0.82rem;font-family:var(--font-mono);max-height:400px;overflow-y:auto;">
                        <span class="text-muted">Selecciona un proyecto para ver sus elementos.</span>
                    </div>
                </div>

                <div class="detail-section mt-4">
                    <h3 style="font-size:0.92rem;font-weight:600;color:var(--text-secondary);margin-bottom:8px;">Acciones</h3>
                    <div style="display:flex;gap:8px;flex-wrap:wrap;">
                        <button class="secondary" onclick="goRefactorProject()">Refactorizar proyecto</button>
                        <button class="secondary" onclick="goProjectProgress()">Ver progreso</button>
                        <button class="secondary" onclick="goProjectDashboard()">Ver metricas</button>
                    </div>
                </div>
            </div>

            <div id="proyectos-no-selection">
                <div class="empty-state">
                    <div class="empty-state-icon">&#128193;</div>
                    <div class="empty-state-title">Sin proyecto seleccionado</div>
                    <div class="empty-state-desc">Selecciona un proyecto del desplegable para ver sus elementos, spec, plan y ficheros generados.</div>
                </div>
            </div>
        </div>

        <!-- ===== DASHBOARD ===== -->
        <div id="dashboard-section" class="tab-content">
            <h2 class="section-title">Dashboard de Monitoreo</h2>
            <p class="section-desc">Selecciona un proyecto para ver sus metricas de ejecucion, costes y modelos utilizados.</p>
            <div class="field-row">
                <div class="field">
                    <label>Proyecto:</label>
                    <select id="project-select"><option value="">-- Selecciona un proyecto --</option></select>
                </div>
                <div class="field" style="display:flex;align-items:flex-end;">
                    <button class="primary" onclick="loadDashboard()" id="dashboard-btn" disabled>Cargar metricas</button>
                </div>
            </div>
            <div id="dashboard-content">
                <p class="text-muted text-sm">Selecciona un proyecto y pulsa "Cargar metricas" para ver los datos.</p>
            </div>
        </div>

        <!-- ===== PROGRESO EN TIEMPO REAL (H2) ===== -->
        <div id="progreso-section" class="tab-content">
            <h2 class="section-title">Progreso de ejecucion</h2>
            <p class="section-desc">Seguimiento en tiempo real de las tareas del proyecto activo.</p>
            <div id="progress-no-project">
                <div class="empty-state">
                    <div class="empty-state-icon">📋</div>
                    <div class="empty-state-title">Sin proyecto activo</div>
                    <div class="empty-state-desc">Lanza un proyecto desde la pestana "Nueva spec" para ver su progreso aqui.</div>
                </div>
            </div>
            <div id="progress-content" class="hidden">
                <div class="progress-header">
                    <div class="progress-summary">
                        <div class="progress-summary-item">Proyecto: <span class="count" id="progress-project-id">-</span></div>
                        <div class="progress-summary-item">Completadas: <span class="count" id="progress-completed" style="color:var(--green)">0</span></div>
                        <div class="progress-summary-item">Fallidas: <span class="count" id="progress-failed" style="color:var(--red)">0</span></div>
                    </div>
                    <button onclick="refreshProgress()" id="refresh-progress-btn">Actualizar</button>
                </div>
                <div class="progress-bar" style="height:8px;margin-bottom:16px">
                    <div class="progress-fill green" id="progress-bar-fill" style="width:0%"></div>
                </div>
                <div class="progress-tasks-list">
                    <div class="progress-task-row header">
                        <div style="text-align:center">#</div>
                        <div>Tarea</div>
                        <div>Estado</div>
                        <div>Modelo</div>
                        <div style="text-align:center">Tiempo</div>
                        <div style="text-align:center">Intento</div>
                    </div>
                    <div id="progress-tasks-body"></div>
                </div>
            </div>
        </div>

        <!-- ===== PLAN ===== -->
        <div id="plan-section" class="tab-content">
            <h2 class="section-title">Plan de Mejoras</h2>
            <p class="section-desc">Plan maestro de desarrollo del proyecto activo.</p>
            <div style="background:var(--bg-surface);border:1px solid var(--border-default);border-radius:var(--radius-md);padding:16px;margin-top:16px;font-family:var(--font-mono);font-size:0.85rem;color:var(--plan-text);max-height:70vh;overflow-y:auto;line-height:1.7;" id="plan-content">
                <p style="color:var(--text-muted);">Cargando plan del proyecto...</p>
            </div>
        </div>

        <!-- ===== NOTIFICACIONES ===== -->
        <div id="notificaciones-section" class="tab-content">
            <h2 class="section-title">Notificaciones</h2>
            <p class="section-desc">Eventos del sistema en tiempo real via SSE.</p>
            <div id="notif-list" style="margin-top:16px;">
                <div class="empty-state">
                    <div class="empty-state-icon">🔔</div>
                    <div class="empty-state-title">Sin notificaciones</div>
                    <div class="empty-state-desc">Las notificaciones apareceran aqui durante la ejecucion.</div>
                </div>
            </div>
        </div>

        <!-- ===== AGENTES EN TIEMPO REAL (Fase 4: UX2) ===== -->
        <div id="agentes-section" class="tab-content">
            <h2 class="section-title">Agentes en tiempo real</h2>
            <p class="section-desc">Estado de los agentes del pipeline durante la ejecución. Actualización automática vía SSE.</p>
            <div id="agent-cards-container">
                <div class="agent-card agent-card-hidden" id="card-planner" data-agent="planner">
                    <div class="agent-card-header">
                        <div class="agent-icon" id="icon-planner">P</div>
                        <div class="agent-card-info">
                            <div class="agent-card-name">Planificador</div>
                            <div class="agent-card-model" id="model-planner">--</div>
                        </div>
                        <div class="agent-card-status" id="status-planner">idle</div>
                    </div>
                    <div class="agent-card-body">
                        <div class="agent-card-task" id="task-planner"></div>
                        <div class="agent-card-detail"><span class="agent-detail-label">Tokens:</span> <span id="tokens-planner">0</span></div>
                        <div class="agent-card-context" id="ctx-row-planner" style="display:none">
                            <span class="agent-card-context-label">Contexto:</span>
                            <div class="agent-context-bar"><div class="agent-context-fill" id="ctx-fill-planner" style="width:0%"></div></div>
                            <span class="agent-context-pct" id="ctx-pct-planner">--</span>
                        </div>
                        <div class="agent-card-detail"><span class="agent-detail-label">Latencia:</span> <span id="latency-planner">--</span></div>
                        <div class="agent-card-progress"><div class="progress-bar"><div class="progress-fill" id="pbar-planner" style="width:0%"></div></div></div>
                    </div>
                </div>
                <div class="agent-card agent-card-hidden" id="card-coder" data-agent="coder">
                    <div class="agent-card-header">
                        <div class="agent-icon" id="icon-coder">C</div>
                        <div class="agent-card-info">
                            <div class="agent-card-name">Codificador</div>
                            <div class="agent-card-model" id="model-coder">--</div>
                        </div>
                        <div class="agent-card-status" id="status-coder">idle</div>
                    </div>
                    <div class="agent-card-body">
                        <div class="agent-card-task" id="task-coder"></div>
                        <div class="agent-card-detail"><span class="agent-detail-label">Tokens:</span> <span id="tokens-coder">0</span></div>
                        <div class="agent-card-context" id="ctx-row-coder" style="display:none">
                            <span class="agent-card-context-label">Contexto:</span>
                            <div class="agent-context-bar"><div class="agent-context-fill" id="ctx-fill-coder" style="width:0%"></div></div>
                            <span class="agent-context-pct" id="ctx-pct-coder">--</span>
                        </div>
                        <div class="agent-card-detail"><span class="agent-detail-label">Latencia:</span> <span id="latency-coder">--</span></div>
                        <div class="agent-card-progress"><div class="progress-bar"><div class="progress-fill" id="pbar-coder" style="width:0%"></div></div></div>
                    </div>
                </div>
                <div class="agent-card agent-card-hidden" id="card-integrator" data-agent="integrator">
                    <div class="agent-card-header">
                        <div class="agent-icon" id="icon-integrator">I</div>
                        <div class="agent-card-info">
                            <div class="agent-card-name">Integrador</div>
                            <div class="agent-card-model" id="model-integrator">--</div>
                        </div>
                        <div class="agent-card-status" id="status-integrator">idle</div>
                    </div>
                    <div class="agent-card-body">
                        <div class="agent-card-task" id="task-integrator"></div>
                        <div class="agent-card-detail"><span class="agent-detail-label">Tokens:</span> <span id="tokens-integrator">0</span></div>
                        <div class="agent-card-context" id="ctx-row-integrator" style="display:none">
                            <span class="agent-card-context-label">Contexto:</span>
                            <div class="agent-context-bar"><div class="agent-context-fill" id="ctx-fill-integrator" style="width:0%"></div></div>
                            <span class="agent-context-pct" id="ctx-pct-integrator">--</span>
                        </div>
                        <div class="agent-card-detail"><span class="agent-detail-label">Latencia:</span> <span id="latency-integrator">--</span></div>
                        <div class="agent-card-progress"><div class="progress-bar"><div class="progress-fill" id="pbar-integrator" style="width:0%"></div></div></div>
                    </div>
                </div>
                <div class="agent-card agent-card-hidden" id="card-validator" data-agent="validator">
                    <div class="agent-card-header">
                        <div class="agent-icon" id="icon-validator">V</div>
                        <div class="agent-card-info">
                            <div class="agent-card-name">Validador</div>
                            <div class="agent-card-model" id="model-validator">--</div>
                        </div>
                        <div class="agent-card-status" id="status-validator">idle</div>
                    </div>
                    <div class="agent-card-body">
                        <div class="agent-card-task" id="task-validator"></div>
                        <div class="agent-card-detail"><span class="agent-detail-label">Resultado:</span> <span id="tokens-validator">--</span></div>
                        <div class="agent-card-progress"><div class="progress-bar"><div class="progress-fill" id="pbar-validator" style="width:0%"></div></div></div>
                    </div>
                </div>

                <!-- Eventos de agentes -->
                <div style="margin-top:12px;">
                    <h3 class="text-sm" style="color:var(--text-muted);text-transform:uppercase;letter-spacing:0.04em;margin-bottom:6px;">Eventos</h3>
                    <div id="agents-events" style="background:var(--bg-elevated);border:1px solid var(--border-muted);border-radius:var(--radius-sm);padding:8px 10px;max-height:120px;overflow-y:auto;font-family:var(--font-mono);font-size:0.78rem;color:var(--text-secondary);line-height:1.6;">
                        <span style="color:var(--text-muted);">Esperando eventos...</span>
                    </div>
                </div>
            </div>
        </div>

        <!-- ===== MODAL DE REVISION DE PLAN (H1) ===== -->
        <div class="modal-overlay" id="plan-review-modal">
            <div class="modal">
                <div class="modal-header">
                    <h2>Revision del plan de tareas</h2>
                    <button class="modal-close" onclick="closePlanReview()">&times;</button>
                </div>
                <div class="modal-body" id="plan-review-body">
                    <p class="text-muted text-sm">Cargando plan...</p>
                </div>
                <div class="modal-footer">
                    <button onclick="closePlanReview()">Cancelar</button>
                    <button class="primary" onclick="approvePlan()">Aprobar y ejecutar</button>
                </div>
            </div>
        </div>

        <!-- ===== TOAST CONTAINER (H5) ===== -->
        <div class="toast-container" id="toast-container"></div>

        <!-- ===== UX1: AUDITOR DE FALLOS ===== -->
        <div id="auditor-section" class="tab-content">
            <h2 class="section-title">Auditor de Fallos</h2>
            <p class="section-desc">Diagnostica fallos del pipeline APA clasificandolos en 4 categorias y genera recomendaciones de correccion accionables.</p>

            <div class="field-row">
                <div class="field">
                    <label>Tarea ID:</label>
                    <input type="text" id="fa-task-id" placeholder="Ej: T1, T2...">
                </div>
                <div class="field">
                    <label>Script objetivo:</label>
                    <input type="text" id="fa-script" placeholder="Ej: modulo.py">
                </div>
            </div>
            <div class="field-row">
                <div class="field">
                    <label>Agente donde fallo:</label>
                    <select id="fa-agent">
                        <option value="coder">Codificador</option>
                        <option value="planner">Planificador</option>
                        <option value="integrator">Integrador</option>
                        <option value="validator">Validador</option>
                    </select>
                </div>
                <div class="field">
                    <label>Intento / Max intentos:</label>
                    <div style="display:flex;gap:8px;align-items:center;">
                        <input type="number" id="fa-attempt" value="1" min="1" max="10" style="width:70px;">
                        <span style="color:var(--text-muted)">/</span>
                        <input type="number" id="fa-max-attempts" value="3" min="1" max="10" style="width:70px;">
                    </div>
                </div>
            </div>
            <div class="field">
                <label>Error reportado:</label>
                <textarea id="fa-error" style="min-height:100px" placeholder="Pega aqui el error: [CONTEXT_EXCEEDED], JSONDecodeError, Falta campo SCRIPT, etc."></textarea>
            </div>
            <div class="field">
                <label>Salida del codificador (opcional):</label>
                <textarea id="fa-coder-output" style="min-height:60px" placeholder="Salida del LLM o codificador (opcional)"></textarea>
            </div>
            <div class="btn-row">
                <button class="primary" onclick="runFailureAuditor()">Diagnosticar fallo</button>
                <button onclick="loadSampleError()">Cargar ejemplo</button>
            </div>

            <div id="fa-result" class="hidden mt-6" style="padding:16px;background:var(--bg-surface);border:1px solid var(--border-default);border-radius:var(--radius-md);">
                <h3 style="font-size:0.95rem;font-weight:600;margin-bottom:12px;">Resultado del diagnostico</h3>
                <div id="fa-result-content"></div>
            </div>

            <!-- Historial de diagnosticos -->
            <div class="detail-section mt-6" id="fa-history-section" style="display:none;">
                <h3>Historial de diagnosticos (esta sesion)</h3>
                <table class="data-table">
                    <thead><tr><th>Hora</th><th>Tarea</th><th>Categoria</th><th>Severidad</th><th>Accion</th></tr></thead>
                    <tbody id="fa-history-body"></tbody>
                </table>
            </div>
        </div>

        <!-- SECCION NOTIFICACIONES — integrada en pestana Notificaciones (UI3) -->

        <!-- ===== PROJECTS TABLE ===== -->
        <div class="detail-section" id="history-section">
            <h3>Proyectos Recientes</h3>
            <table class="data-table">
                <thead><tr><th>ID</th><th>Estado</th><th>Progreso</th><th>Fecha</th><th>Acciones</th></tr></thead>
                <tbody id="projects-table">
                    <tr><td colspan="5" class="text-muted text-sm" style="text-align:center;padding:24px;">No hay proyectos registrados en esta sesion.</td></tr>
                </tbody>
            </table>
        </div>
    </div>

    <script>
    /* ===== STATE ===== */
    const chatMessages = [];
    let activeProjectId = null;
    let eventSource = null;

    /* ===== PUNTO 5: Estado de sesión y caché ===== */
    let currentChatId = null;
    let cachedProjectName = '';
    let cachedMaturitySummary = '';
    let cachedSddStatus = null;
    let isEscalated = false;  /* Rama B/C: flag de escalación confirmada */

    /* ===== DOM REFS ===== */
    const $ = (sel) => document.querySelector(sel);
    const chatHistoryEl = $('#chat-history');
    const chatInput = $('#chat-input');
    const chatPlaceholder = $('#chat-placeholder');

    /* ===== TABS ===== */
    function switchTab(tabName) {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(s => s.classList.remove('active'));
        const tabBtn = document.querySelector('.tab[data-tab="' + tabName + '"]');
        const section = document.getElementById(tabName + '-section');
        if (tabBtn) tabBtn.classList.add('active');
        if (section) section.classList.add('active');
        if (tabName === 'notificaciones') { try { notifUnseen = 0; updateNotifBadge(); } catch(e){} }

        // UI4: Load plan when Plan tab is activated
        if (tabName === 'plan') {
            fetch('/api/plan')
                .then(r => r.json())
                .then(data => {
                    const el = document.getElementById('plan-content');
                    if (data.content) {
                        // Apply plan visual spec: format markdown-like content
                        let html = data.content
                            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
                            .replace(/^### (.+)$/gm, '<div style="color:var(--plan-heading);font-weight:bold;margin-top:16px;font-size:0.95rem;">$1</div>')
                            .replace(/^## (.+)$/gm, '<div style="color:var(--plan-heading);font-weight:bold;margin-top:20px;font-size:1.05rem;border-bottom:1px solid var(--plan-border);padding-bottom:6px;">$1</div>')
                            .replace(/^- \[x\] (.+)$/gm, '<div style="color:var(--plan-strike);text-decoration:line-through;">$1</div>')
                            .replace(/^- \[ \] (.+)$/gm, '<div style="color:var(--plan-text);">$1</div>')
                            .replace(/^---$/gm, '<hr style="border-color:var(--plan-border);margin:12px 0;">')
                            .replace(/\\n/g, '<br>');
                        el.innerHTML = html;
                    }
                }).catch(function(e) { console.warn('Error cargando plan:', e); });
        }
    }
    document.querySelectorAll('.tab[data-tab]').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            switchTab(btn.dataset.tab);
        });
    });

    /* ===== CHAT ===== */
    function addMessage(role, text, model) {
        if (chatPlaceholder) chatPlaceholder.remove();
        chatMessages.push({ role, text });
        const msgDiv = document.createElement('div');
        msgDiv.className = 'chat-message ' + role;
        const bubble = document.createElement('div');
        bubble.className = 'chat-bubble';
        bubble.innerHTML = renderInlineMarkdown(text);
        if (model && role === 'assistant') {
            const modelLabel = document.createElement('div');
            modelLabel.style.cssText = 'font-size:0.68rem;color:var(--text-muted);margin-top:5px;opacity:0.7;display:flex;align-items:center;gap:4px;';
            modelLabel.textContent = 'Modelo: ' + model;
            bubble.appendChild(modelLabel);
        }
        msgDiv.appendChild(bubble);
        chatHistoryEl.appendChild(msgDiv);
        chatHistoryEl.scrollTop = chatHistoryEl.scrollHeight;
    }

    function renderInlineMarkdown(text) {
        let s = text
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/```(\\w*)\\n?([\\s\\S]*?)```/g, '<pre><code>$2</code></pre>')
            .replace(/`([^`]+)`/g, '<code>$1</code>')
            .replace(/\\*\\*([^*]+)\\*\\*/g, '<strong>$1</strong>')
            .replace(/\\*([^*]+)\\*/g, '<em>$1</em>');
        return s;
    }

    async function sendChat() {
        const message = chatInput.value.trim();
        if (!message) return;
        addMessage('user', message);
        chatInput.value = '';
        chatInput.style.height = 'auto';
        $('#chat-send-btn').disabled = true;

        const typingDiv = document.createElement('div');
        typingDiv.className = 'chat-message assistant';
        typingDiv.id = 'typing-indicator';
        typingDiv.innerHTML = '<div class="chat-bubble"><span class="text-muted">Escribiendo...</span></div>';
        chatHistoryEl.appendChild(typingDiv);
        chatHistoryEl.scrollTop = chatHistoryEl.scrollHeight;

        try {
            const historyPayload = chatMessages.map(m => ({ role: m.role, content: m.text }));
            const currentPath = ($('#chat-project-path') || {}).value || '';
            const response = await fetch('/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: message, history: historyPayload, project_path: currentPath, is_escalated: isEscalated })
            });
            const data = await response.json();
            typingDiv.remove();
            if (data.success && data.response) {
                addMessage('assistant', data.response, data.model_used);
            } else {
                addMessage('assistant', 'Error: ' + (data.error || 'Respuesta vacia'));
            }
            // CHAT-R.5: Mostrar que LLM respondio (badge junto a 'Chat con APA')
            const chatBadge = $('#chat-llm-badge');
            if (chatBadge) {
                if (data.model_used) {
                    const shortModel = data.model_used.split('/').pop();
                    chatBadge.textContent = shortModel;
                    chatBadge.title = 'Modelo: ' + data.model_used;
                    chatBadge.style.display = 'inline-block';
                    chatBadge.style.background = 'var(--green)';
                    chatBadge.style.color = '#fff';
                } else if (data.success) {
                    chatBadge.textContent = 'LLM';
                    chatBadge.title = 'Modelo no reportado';
                    chatBadge.style.display = 'inline-block';
                    chatBadge.style.background = 'var(--amber)';
                    chatBadge.style.color = '#fff';
                }
            }
            // CV1: Actualizar boton Crear Proyecto segun madurez SDD
            if (data.sdd_status) {
                updateSDDButton(data.sdd_status);
                updateAspectsDisplay(data.sdd_status);
            }
            // Rama B/C: Si el backend confirma la escalación, activar flag para futuros mensajes
            if (data.escalation_confirmed) {
                isEscalated = true;
            }
            // CHAT-R.3: Actualizar resumen del objetivo dinámico
            if (data.objective_summary !== undefined) {
                updateObjectiveSummary(data.objective_summary, data.sdd_status);
            }
            // CHAT-R.7: Detección de variante y auto-set de ubicación
            if (data.project_variant) {
                handleVariantDetection(data.project_variant, data.project_name, data.project_path);
            }
            // Punto 5: Cachear datos cuando madurez llega a 5/5
            if (data.sdd_status && data.sdd_status.can_generate) {
                if (!currentChatId) { currentChatId = 'sess_' + Date.now().toString(36); }
                if (data.project_name) cachedProjectName = data.project_name;
                if (data.maturity_summary) cachedMaturitySummary = data.maturity_summary;
                cachedSddStatus = data.sdd_status;
                // Fire-and-forget: enviar al backend (no bloquea la UI)
                fetch('/api/chat-cache', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        chat_id: currentChatId,
                        messages: chatMessages.map(m => ({ role: m.role, content: m.text })),
                        project_name: cachedProjectName,
                        project_path: (($('#chat-project-path') || {}).value) || '',
                        project_variant: data.project_variant || '',
                        sdd_status: cachedSddStatus,
                        objective_summary: data.objective_summary || '',
                        maturity_summary: cachedMaturitySummary,
                    })
                }).catch(() => {});
            }
        } catch (error) {
            typingDiv.remove();
            addMessage('assistant', 'Error de conexion: ' + error.message);
        }
        $('#chat-send-btn').disabled = false;
        chatInput.focus();
    }

    /* ===== CV1: Boton dinamico Generar la SDD (invisible hasta 5/5 imprescindibles) ===== */
    function updateSDDButton(sdd) {
        const btn = $('#create-project-btn');
        const indicator = $('#sdd-indicator');
        const indicatorText = $('#sdd-indicator-text');
        if (!btn || !sdd) return;

        if (sdd.can_generate) {
            /* 5/5 imprescindibles — mostrar y habilitar el boton */
            btn.style.display = 'inline-flex';
            btn.disabled = false;
            btn.title = 'Madurez: ' + sdd.maturity + ' — ' + sdd.covered_count + '/' + sdd.total_essentials + ' aspectos cubiertos';
            indicator.style.display = 'block';
            indicatorText.innerHTML = '<span style="color:var(--green);">&#10003;</span> Listo para generar SDD <span style="margin-left:8px;">' + sdd.covered_count + '/' + sdd.total_essentials + ' aspectos esenciales</span>';
        } else if (sdd.is_project) {
            /* Proyecto detectado pero no 5/5 — boton invisible */
            btn.style.display = 'none';
            indicator.style.display = 'block';
            const pct = sdd.total_essentials > 0 ? Math.round((sdd.covered_count / sdd.total_essentials) * 100) : 0;
            indicatorText.innerHTML = '<span style="color:var(--amber);">&#9679;</span> Definiendo proyecto... <span style="margin-left:8px;">' + sdd.covered_count + '/' + sdd.total_essentials + ' aspectos (' + pct + '%)</span>';
        } else {
            /* Sin proyecto — ocultar todo */
            btn.style.display = 'none';
            indicator.style.display = 'none';
        }
    }

    /* CHAT-R.3: Actualiza el resumen del objetivo dinámico (SIEMPRE visible) */
    function updateObjectiveSummary(summary, sdd) {
        const bar = $('#chat-objective-bar');
        const textEl = $('#chat-objective-text');
        const pctEl = $('#chat-objective-pct');
        if (!bar || !textEl || !pctEl) return;

        if (summary && summary.length > 5) {
            /* Solo actualizar si el usuario no está editando manualmente */
            if (document.activeElement !== textEl) {
                textEl.innerText = summary;
                textEl.style.color = 'var(--text-primary)';
                textEl.style.opacity = '1';
            }
        } else {
            /* Sin resumen — mostrar placeholder con opacidad baja */
            if (document.activeElement !== textEl) {
                textEl.innerText = 'A medida que describas tu proyecto, aqui aparecera un resumen de tu objetivo...';
                textEl.style.color = 'var(--text-secondary)';
                textEl.style.opacity = '0.55';
            }
        }

        /* Porcentaje basado en aspectos cubiertos */
        if (sdd && sdd.total_essentials > 0) {
            const pct = Math.round((sdd.covered_count / sdd.total_essentials) * 100);
            pctEl.textContent = pct + '%';
            pctEl.style.color = pct >= 100 ? 'var(--green)' : 'var(--amber)';
        } else {
            pctEl.textContent = '0%';
        }
    }

    /* 3a: Visualiza los 18 aspectos de madurez agrupados por tipo */
    function updateAspectsDisplay(sdd) {
        const section = $('#chat-aspects-section');
        const list = $('#chat-aspects-list');
        if (!section || !list || !sdd || !sdd.aspects_detail) return;
        section.style.display = 'block';
        let html = '';
        const groups = [
            { key: 'imprescindibles', label: 'Imprescindibles', color: 'var(--red)' },
            { key: 'necesarias', label: 'Necesarias', color: 'var(--amber)' },
            { key: 'prescindibles', label: 'Prescindibles', color: 'var(--text-muted)' }
        ];
        for (const g of groups) {
            const items = sdd.aspects_detail[g.key] || [];
            if (items.length === 0) continue;
            html += '<div style="margin-bottom:8px;">';
            html += '<span style="font-size:0.72rem; font-weight:600; color:' + g.color + ';">' + g.label + ' (' + items.length + ')</span>';
            html += '<div style="margin-top:2px;">';
            for (const a of items) {
                const icon = a.status === 'COVERED' ? '&#10003;' : (a.status === 'PARTIAL' ? '&#9673;' : '&#10007;');
                const ic = a.status === 'COVERED' ? 'var(--green)' : (a.status === 'PARTIAL' ? 'var(--amber)' : 'var(--text-muted)');
                html += '<div style="display:flex; align-items:baseline; gap:5px; padding:1px 0;">';
                html += '<span style="color:' + ic + '; font-size:0.75rem; min-width:14px;">' + icon + '</span>';
                html += '<span style="color:var(--text-secondary); font-size:0.74rem;">' + a.label + '</span>';
                html += '</div>';
            }
            html += '</div></div>';
        }
        list.innerHTML = html;
    }

    function toggleAspects() {
        const list = $('#chat-aspects-list');
        const icon = $('#chat-aspects-toggle-icon');
        if (!list) return;
        const isOpen = list.style.display !== 'none';
        list.style.display = isOpen ? 'none' : 'block';
        if (icon) icon.innerHTML = isOpen ? '&#9660;' : '&#9650;';
    }

    /* ===== PUNTO 5: Persistencia de conversaciones ===== */

    /* Commit: salva el caché a disco (fire-and-forget con sendBeacon para beforeunload) */
    function commitChat(specGenerated) {
        if (!currentChatId) return;
        const payload = JSON.stringify({ chat_id: currentChatId, spec_generated: !!specGenerated });
        if (navigator.sendBeacon) {
            navigator.sendBeacon('/api/chat-commit', payload);
        } else {
            fetch('/api/chat-commit', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: payload }).catch(() => {});
        }
    }

    /* beforeunload: salva caché a disco si hay datos */
    window.addEventListener('beforeunload', function() { commitChat(false); });

    /* Nueva conversación: salva la anterior y limpia estado */
    async function newChat() {
        commitChat(false);
        /* C1: Resetear guía CV2 para no arrastrar estado entre conversaciones */
        try { await fetch('/api/chat-reset-guide', { method: 'POST' }); } catch(e) {}
        chatMessages.length = 0;
        currentChatId = null;
        cachedProjectName = '';
        cachedMaturitySummary = '';
        cachedSddStatus = null;
        isEscalated = false;  /* Resetear escalación al iniciar nueva conversación */
        /* Limpiar UI */
        chatHistoryEl.innerHTML = '<div class="chat-empty" id="chat-placeholder">Describe tu proyecto en lenguaje natural. Te ayudare a definir claramente que quieres construir.</div>';
        const objText = $('#chat-objective-text');
        if (objText) { objText.innerText = 'A medida que describas tu proyecto, aqui aparecera un resumen de la especificacion del proyecto...'; objText.style.opacity = '0.55'; objText.style.color = 'var(--text-secondary)'; }
        const pctEl = $('#chat-objective-pct');
        if (pctEl) { pctEl.textContent = '0%'; }
        const aspSection = $('#chat-aspects-section');
        if (aspSection) aspSection.style.display = 'none';
        const sddInd = $('#sdd-indicator');
        if (sddInd) sddInd.style.display = 'none';
        const crtBtn = $('#create-project-btn');
        if (crtBtn) crtBtn.style.display = 'none';
        const specPanel = $('#chat-spec-panel');
        if (specPanel) specPanel.style.display = 'none';
        const pathInput = $('#chat-project-path');
        if (pathInput) pathInput.value = '';
        const badge = $('#chat-variant-badge');
        if (badge) badge.style.display = 'none';
        /* Cerrar panel de historial si abierto */
        const histPanel = $('#chat-history-panel');
        if (histPanel) histPanel.style.display = 'none';
        chatInput.focus();
    }

    /* Toggle panel de historial */
    function toggleChatHistory() {
        const panel = $('#chat-history-panel');
        if (!panel) return;
        if (panel.style.display === 'none' || !panel.style.display) {
            panel.style.display = 'block';
            loadChatList();
        } else {
            panel.style.display = 'none';
        }
    }

    /* Cargar lista de conversaciones guardadas */
    async function loadChatList() {
        const listEl = $('#chat-history-list');
        if (!listEl) return;
        listEl.innerHTML = '<div style="padding:12px; color:var(--text-muted); font-size:0.8rem;">Cargando...</div>';
        try {
            const res = await fetch('/api/chat-list');
            const data = await res.json();
            if (!data.success || !data.chats || data.chats.length === 0) {
                listEl.innerHTML = '<div style="padding:12px; color:var(--text-muted); font-size:0.8rem;">No hay conversaciones guardadas.</div>';
                return;
            }
            let html = '';
            for (const c of data.chats) {
                const specBadge = c.has_spec ? ' <span style="font-size:0.65rem; background:var(--green); color:#fff; padding:1px 5px; border-radius:8px;">SDD</span>' : '';
                const dateStr = c.date ? c.date.substring(0, 16).replace('T', ' ') : '';
                html += '<div onclick="loadChatSession(\\'' + c.chat_id + '\\')" style="display:flex; justify-content:space-between; align-items:center; padding:8px 12px; border-bottom:1px solid var(--border-muted); cursor:pointer; transition:background 0.15s;" onmouseover="this.style.background=\\'var(--bg-input)\\'" onmouseout="this.style.background=\\'transparent\\'">';
                html += '<div>';
                html += '<div style="font-size:0.82rem; color:var(--text-primary); font-weight:500;">' + c.name + specBadge + '</div>';
                html += '<div style="font-size:0.7rem; color:var(--text-muted); margin-top:2px;">' + c.messages + ' msgs &middot; ' + dateStr + '</div>';
                html += '</div>';
                html += '<span style="font-size:0.7rem; color:var(--text-muted); font-family:var(--font-mono);">#' + c.n + '</span>';
                html += '</div>';
            }
            listEl.innerHTML = html;
        } catch (e) {
            listEl.innerHTML = '<div style="padding:12px; color:var(--agent-failed); font-size:0.8rem;">Error cargando historial.</div>';
        }
    }

    /* Cargar una sesión guardada desde disco */
    async function loadChatSession(filename) {
        try {
            const res = await fetch('/api/chat-load/' + encodeURIComponent(filename));
            const data = await res.json();
            if (!data.success || !data.chat) { return; }
            const chat = data.chat;
            /* Commit any current session first */
            commitChat(false);
            /* Restore state */
            chatMessages.length = 0;
            currentChatId = null;
            cachedProjectName = chat.project_name || '';
            cachedMaturitySummary = chat.maturity_summary || '';
            cachedSddStatus = chat.sdd_status || null;
            /* Render messages */
            if (chat.messages && chat.messages.length > 0) {
                for (const msg of chat.messages) {
                    chatMessages.push({ role: msg.role, text: msg.content });
                }
                chatHistoryEl.innerHTML = '';
                for (const msg of chatMessages) {
                    addMessage(msg.role, msg.text);
                }
            }
            /* Restore objective summary */
            if (chat.objective_summary) {
                updateObjectiveSummary(chat.objective_summary, chat.sdd_status);
            }
            /* Restore sdd_status */
            if (chat.sdd_status) {
                updateSDDButton(chat.sdd_status);
                updateAspectsDisplay(chat.sdd_status);
            }
            /* Restore variant */
            if (chat.project_variant) {
                handleVariantDetection(chat.project_variant, chat.project_name, chat.project_path);
            }
            /* Restore path */
            if (chat.project_path) {
                const pathInput = $('#chat-project-path');
                if (pathInput) pathInput.value = chat.project_path;
            }
            /* Close history panel */
            const histPanel = $('#chat-history-panel');
            if (histPanel) histPanel.style.display = 'none';
            chatInput.focus();
        } catch (e) {
            console.error('Error loading chat session:', e);
        }
    }

    /* CHAT-R.1: Genera spec desde la conversacion. NO lanza APA. Muestra la SDD para revision del usuario. */
    async function createFromChat() {
        const btn = $('#create-project-btn');
        btn.disabled = true;
        btn.textContent = 'Generando SDD...';

        try {
            /* Punto 5: Commit al disco antes de generar SDD */
            commitChat(true);

            /* slice(-20) + resumen de madurez para SpecBuilder */
            const historyPayload = chatMessages.slice(-20).map(m => ({ role: m.role, content: m.text }));
            const buildBody = { conversation_history: historyPayload };
            if (cachedMaturitySummary) {
                buildBody.maturity_summary = cachedMaturitySummary;
            }

            /* Generar spec estructurada via SpecBuilder */
            const buildRes = await fetch('/api/build-spec', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(buildBody)
            });
            const buildData = await buildRes.json();
            if (!buildData.success) {
                addInlineAlert('run-status', 'error', 'Error generando especificacion: ' + (buildData.error || 'Desconocido'));
                btn.disabled = false;
                btn.textContent = 'Generar la SDD';
                return;
            }
            const spec = buildData.spec;
            const specPath = buildData.spec_path || '';

            /* Mostrar la spec en el panel para revision del usuario */
            $('#chat-generated-spec').value = spec;
            $('#chat-spec-path').textContent = specPath ? specPath.split('/').pop() : '';
            $('#chat-spec-panel').style.display = 'block';

            /* Mensaje en el chat */
            addMessage('assistant', 'SDD generada. Revisa la especificacion de abajo y pulsa "Lanzar APA" cuando estes conforme. Puedes editarla directamente.');

        } catch (error) {
            addInlineAlert('run-status', 'error', 'Error: ' + error.message);
        }
        btn.disabled = false;
        btn.textContent = 'Generar la SDD';
    }

    /* CHAT-R.1: Lanza APA con la spec editada por el usuario */
    async function launchAPAFromChat() {
        const spec = $('#chat-generated-spec').value.trim();
        if (!spec) { addInlineAlert('run-status', 'warning', 'La especificacion esta vacia.'); return; }
        const btn = $('#chat-launch-apa-btn');
        btn.disabled = true;
        btn.textContent = 'Lanzando APA...';

        try {
            const res = await fetch('/run', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ spec: spec })
            });
            const data = await res.json();
            if (data.project_id) {
                activeProjectId = data.project_id;
                addInlineAlert('run-status', 'info', 'Proyecto ' + data.project_id + ' iniciado desde conversacion.');
                refreshProjects();
                startProgressStream(data.project_id);
                switchTab('proyectos');
            } else {
                addInlineAlert('run-status', 'error', 'Error al iniciar: ' + JSON.stringify(data));
            }
        } catch (error) {
            addInlineAlert('run-status', 'error', 'Error: ' + error.message);
        }
        btn.disabled = false;
        btn.textContent = 'Generar Plan';
    }

    /* CHAT-R.1: Cierra el panel de spec generada */
    function closeSpecPanel() {
        $('#chat-spec-panel').style.display = 'none';
    }

    /* ===== CHAT-R.7: Deteccion de variante y auto-set de ubicacion (3 variantes) ===== */
    async function handleVariantDetection(variant, projectName, projectPath) {
        const badge = $('#chat-variant-badge');
        const pathInput = $('#chat-project-path');
        if (!badge) return;

        if (variant === 'A') {
            /* 2c1: Nuevo proyecto — ubicacion por defecto apa/APA Proyectos */
            badge.textContent = 'Nuevo proyecto';
            badge.style.display = 'inline';
            badge.style.background = 'var(--green)';
            badge.style.color = '#fff';
            badge.title = 'Se detecto que quieres crear un proyecto nuevo';

            /* Si se detecto el nombre del proyecto, auto-set la ubicacion */
            if (projectName && pathInput && !pathInput.value.trim()) {
                pathInput.value = 'apa/APA Proyectos/' + projectName.replace(/\s+/g, '-');
            }
            /* Si no hay nombre pero tampoco hay valor, asegurar el default */
            if (pathInput && !pathInput.value.trim()) {
                pathInput.value = 'apa/APA Proyectos';
            }
        } else if (variant === 'B') {
            /* 2c2: Proyecto existente por ubicacion directa del usuario */
            badge.textContent = 'Proyecto existente';
            badge.style.display = 'inline';
            badge.style.background = 'var(--amber)';
            badge.style.color = '#fff';
            badge.title = 'Se detecto que quieres trabajar sobre un proyecto existente';

            /* Si se detecto la ruta, auto-set y explorar scripts uno por uno */
            if (projectPath && pathInput) {
                pathInput.value = projectPath;
                await analyzeExistingProject(projectPath);
            }
        } else if (variant === 'C') {
            /* 2c3: Ubicacion inducida por la conversacion con el modelo */
            badge.textContent = 'Proyecto detectado por chat';
            badge.style.display = 'inline';
            badge.style.background = '#6366f1';
            badge.style.color = '#fff';
            badge.title = 'El modelo detecto la ubicacion del proyecto en la conversacion';

            /* Si se detecto la ruta, auto-set y explorar scripts uno por uno */
            if (projectPath && pathInput) {
                pathInput.value = projectPath;
                await analyzeExistingProject(projectPath);
            }
        }
    }

    /* CHAT-R.7: Analizar proyecto existente — scripts uno por uno con explicacion (2c2/2c3) */
    async function analyzeExistingProject(projectPath) {
        addMessage('assistant', 'Explorando proyecto en ' + projectPath + '. Analizando scripts uno por uno...');
        try {
            const res = await fetch('/api/explore-project', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: projectPath })
            });
            const data = await res.json();
            if (data.success) {
                /* Resumen general del proyecto */
                let msg = '';
                if (data.project_summary) {
                    msg += '** ' + data.project_name + ' (' + data.project_type + ') **\\n';
                    msg += data.project_summary + '\\n\\n';
                }
                /* Detalle de cada script */
                if (data.script_summaries && data.script_summaries.length > 0) {
                    msg += '--- Scripts analizados (' + data.stats.scripts_analyzed + ') ---\\n';
                    for (const s of data.script_summaries) {
                        msg += '\\n**' + s.file + '** (' + formatBytes(s.size) + '):\\n' + s.summary + '\\n';
                    }
                }
                /* Mostrar contenido de archivos clave detectados */
                if (data.key_file_contents) {
                    const keyEntries = Object.entries(data.key_file_contents);
                    if (keyEntries.length > 0) {
                        msg += '\\n--- Archivos clave leidos ---\\n';
                        for (const [kname, kdata] of keyEntries) {
                            if (kdata.content && !kdata.content.startsWith('(Error')) {
                                const trunc = kdata.truncated ? ' (truncado)' : '';
                                msg += '\\n**' + kdata.path + '**' + trunc + ':\\n';
                                /* Truncar contenido muy largo en el display */
                                const maxDisplay = 1500;
                                const displayContent = kdata.content.length > maxDisplay
                                    ? kdata.content.substring(0, maxDisplay) + '\\n... (contenido truncado en display, disponible completo para el chat)'
                                    : kdata.content;
                                msg += '```\\n' + displayContent + '\\n```\\n';
                            }
                        }
                    }
                }
                msg += '\\n' + data.stats.total_files + ' archivos en ' + data.stats.total_dirs + ' directorios.';
                addMessage('assistant', msg);
            } else {
                addMessage('assistant', 'Error explorando: ' + (data.error || 'desconocido'));
            }
        } catch (error) {
            addMessage('assistant', 'Error de conexion al explorar proyecto: ' + error.message);
        }
    }

    /* Formatea bytes a KB/MB */
    function formatBytes(bytes) {
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    }

    /* CHAT-R.7: Browser de ubicacion de proyecto */
    async function browseProjectLocation() {
        try {
            const res = await fetch('/api/browse-directory', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: '' })
            });
            const data = await res.json();
            if (!data.success) {
                addMessage('assistant', 'No se pudo navegar: ' + (data.error || 'desconocido'));
                return;
            }
            showBrowseDialog(data.path, buildNavHtml(data));
        } catch (error) {
            addMessage('assistant', 'Error de conexion al navegar: ' + error.message);
        }
    }

    /* Construye HTML de navegacion (usa data-path para evitar escaping) */
    function buildNavHtml(data) {
        const dirs = data.entries.filter(e => e.is_dir);
        const files = data.entries.filter(e => !e.is_dir);
        let html = '<div style="max-height:300px; overflow-y:auto;">';
        html += '<div style="font-size:0.78rem; color:var(--text-muted); margin-bottom:8px;">Ruta: <code style="font-family:var(--font-mono);">' + escHtml(data.path) + '</code></div>';
        if (dirs.length > 0) {
            html += '<div style="font-size:0.75rem; color:var(--text-muted); margin-bottom:4px;">Directorios:</div>';
            for (const d of dirs) {
                const label = d.is_parent ? '.. (volver)' : escHtml(d.name) + (d.child_count ? ' (' + d.child_count + ')' : '');
                html += '<div class="browse-dir" data-path="' + escAttr(d.path) + '" style="padding:4px 8px; margin:2px 0; cursor:pointer; border-radius:4px; background:var(--bg-elevated); font-size:0.82rem; color:var(--text-primary);">&#128193; ' + label + '</div>';
            }
        }
        if (files.length > 0) {
            html += '<div style="font-size:0.75rem; color:var(--text-muted); margin:6px 0 4px;">Archivos:</div>';
            for (const f of files) {
                html += '<div class="browse-file" data-path="' + escAttr(f.path) + '" style="padding:4px 8px; margin:2px 0; cursor:pointer; border-radius:4px; background:var(--bg-elevated); font-size:0.82rem; color:var(--text-primary);">&#128196; ' + escHtml(f.name) + ' <span style="color:var(--text-muted); font-size:0.72rem;">' + formatBytes(f.size || 0) + '</span></div>';
            }
        }
        html += '</div>';
        return html;
    }

    /* Escape HTML entities */
    function escHtml(s) {
        return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    /* Escape para atributos HTML (data-path) */
    function escAttr(s) {
        return String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    /* Navega a un subdirectorio en el browser */
    async function browseTo(path) {
        try {
            const res = await fetch('/api/browse-directory', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: path })
            });
            const data = await res.json();
            if (!data.success) return;
            const dialogContent = $('#browse-dialog-content');
            if (dialogContent) dialogContent.innerHTML = buildNavHtml(data);
            const pathLabel = $('#browse-dialog-path');
            if (pathLabel) pathLabel.textContent = data.path;
        } catch (error) {
            addMessage('assistant', 'Error al navegar: ' + error.message);
        }
    }

    /* Selecciona una ruta como ubicacion del proyecto */
    function selectProjectPath(path) {
        const pathInput = $('#chat-project-path');
        if (pathInput) {
            pathInput.value = path;
        }
        closeBrowseDialog();
        /* Si es un directorio, explorar el proyecto automaticamente */
        if (!path.includes('.')) {
            analyzeExistingProject(path);
        }
    }

    /* Muestra dialogo de navegador */
    function showBrowseDialog(currentPath, contentHtml) {
        let dialog = $('#browse-dialog');
        if (!dialog) {
            dialog = document.createElement('div');
            dialog.id = 'browse-dialog';
            dialog.style.cssText = 'position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);z-index:9999;background:var(--bg-surface);border:1px solid var(--border-default);border-radius:var(--radius-lg);padding:16px;min-width:450px;max-width:90vw;max-height:80vh;overflow-y:auto;box-shadow:0 8px 32px rgba(0,0,0,0.5);';
            document.body.appendChild(dialog);
            /* Event delegation: un solo listener para dirs y files */
            dialog.addEventListener('click', function(e) {
                const dirEl = e.target.closest('.browse-dir');
                if (dirEl) {
                    browseTo(dirEl.dataset.path);
                    return;
                }
                const fileEl = e.target.closest('.browse-file');
                if (fileEl) {
                    selectProjectPath(fileEl.dataset.path);
                }
            });
        }
        dialog.innerHTML =
            '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">' +
                '<h3 id="browse-dialog-path" style="font-size:0.9rem;font-weight:600;color:var(--text-primary);">Buscar proyecto</h3>' +
                '<button onclick="closeBrowseDialog()" style="background:none;border:none;color:var(--text-muted);cursor:pointer;font-size:1.1rem;">&times;</button>' +
            '</div>' +
            '<div id="browse-dialog-content" style="font-family:var(--font-mono);">' + contentHtml + '</div>' +
            '<div style="margin-top:10px;display:flex;gap:8px;justify-content:flex-end;">' +
                '<button id="browse-select-btn" style="padding:6px 14px;border:1px solid var(--border-default);border-radius:var(--radius-sm);background:var(--bg-elevated);color:var(--text-primary);cursor:pointer;font-size:0.82rem;">Usar esta carpeta</button>' +
            '</div>';
        /* Boton "Usar esta carpeta" usa la ruta actual del dialog */
        var selectBtn = dialog.querySelector('#browse-select-btn');
        if (selectBtn) {
            selectBtn.addEventListener('click', function() {
                var pathEl = dialog.querySelector('#browse-dialog-path');
                selectProjectPath(pathEl ? pathEl.textContent : currentPath);
            });
        }
        dialog.style.display = 'block';
    }

    /* Cierra dialogo de navegador */
    function closeBrowseDialog() {
        const dialog = $('#browse-dialog');
        if (dialog) dialog.style.display = 'none';
    }

    /* CHAT-R.7: Explorar proyecto existente (legacy, ahora usa analyzeExistingProject) */
    async function exploreProjectFromChat(projectPath) {
        await analyzeExistingProject(projectPath);
    }

    /* ===== RUN APA ===== */
    async function runAPA() {
        const spec = $('#spec-input').value.trim();
        if (!spec) { addInlineAlert('run-status', 'warning', 'Escribe una especificacion antes de generar el plan.'); return; }
        const runBtn = document.querySelector('#sdd-section .primary');
        runBtn.disabled = true;
        runBtn.textContent = 'Lanzando...';

        try {
            const res = await fetch('/run', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ spec: spec })
            });
            const data = await res.json();
            if (data.project_id) {
                activeProjectId = data.project_id;
                addInlineAlert('run-status', 'info', 'Proyecto ' + data.project_id + ' iniciado. Se ha abierto la pestana de proyectos.');
                refreshProjects();
                startProgressStream(data.project_id);
            } else {
                addInlineAlert('run-status', 'error', 'Error al iniciar: ' + JSON.stringify(data));
            }
        } catch (error) {
            addInlineAlert('run-status', 'error', 'Error de conexion: ' + error.message);
        }
        runBtn.disabled = false;
        runBtn.textContent = 'Lanzar APA';
    }

    /* ===== ANALYZE PROJECT ===== */
    async function analyzeProject() {
        /* CHAT-R.4: usar campo de ubicacion del Chat */
        const projectPath = ($('#chat-project-path') || {}).value ? $('#chat-project-path').value.trim() : '';
        if (!projectPath) { addInlineAlert('analyze-result', 'warning', 'Introduce la ruta del proyecto en el campo de ubicacion del Chat.', true); return; }
        const btn = $('#analyze-btn');
        btn.disabled = true;
        btn.textContent = 'Analizando...';

        try {
            const problemas = $('#analyze-problemas').value.trim().split('\\n').filter(s => s.trim());
            const criterios = $('#analyze-criterios').value.trim().split('\\n').filter(s => s.trim());
            const res = await fetch('/analyze', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    project_path: projectPath,
                    objetivo: ($('#chat-objective-text') || {}).innerText ? $('#chat-objective-text').innerText.trim() : 'Mejorar la calidad del codigo',
                    problemas: problemas,
                    criterios: criterios
                })
            });
            const data = await res.json();
            if (data.spec) {
                $('#analyze-stats').textContent = data.stats || 'Spec generada correctamente.';
                $('#generated-spec').value = data.spec;
                $('#analyze-result').style.display = 'block';
            } else {
                addInlineAlert('analyze-result', 'error', 'Error: ' + (data.error || JSON.stringify(data)), true);
            }
        } catch (error) {
            addInlineAlert('analyze-result', 'error', 'Error: ' + error.message, true);
        }
        btn.disabled = false;
        btn.textContent = 'Analizar y generar spec';
    }

    /* ===== RUN APA WITH SPEC ===== */
    async function runAPAWithSpec() {
        const spec = $('#generated-spec').value.trim();
        if (!spec) { alert('No hay spec generada para lanzar.'); return; }
        const specInput = $('#spec-input');
        specInput.value = spec;
        switchTab('sdd');
        await runAPA();
    }

    /* ===== LOAD DASHBOARD ===== */
    async function loadDashboard() {
        const projectId = $('#project-select').value;
        if (!projectId) return;
        const btn = $('#dashboard-btn');
        btn.disabled = true;
        btn.textContent = 'Cargando...';
        const container = $('#dashboard-content');
        container.innerHTML = '<p class="text-muted text-sm">Cargando metricas...</p>';

        try {
            const res = await fetch('/dashboard/' + projectId);
            const data = await res.json();
            renderDashboard(data, container);
        } catch (error) {
            container.innerHTML = '<p class="text-sm" style="color:var(--red)">Error al cargar metricas: ' + error.message + '</p>';
        }
        btn.disabled = false;
        btn.textContent = 'Cargar metricas';
    }

    function renderDashboard(data, container) {
        const successRate = data.task_success_rate || 0;
        const rateColor = successRate >= 80 ? 'green' : successRate >= 50 ? 'amber' : 'red';
        const modelsHtml = Object.entries(data.models_used || {}).map(([m, c]) =>
            '<div class="text-sm" style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid var(--border-muted)">' +
            '<span style="color:var(--text-secondary);font-family:var(--font-mono);font-size:0.78rem;overflow:hidden;text-overflow:ellipsis;max-width:70%;">' + m + '</span>' +
            '<span class="badge running">' + c + '</span></div>'
        ).join('') || '<span class="text-muted text-sm">Sin datos</span>';

        const costReal = data.real_cost_usd || 0;
        const costDisplay = costReal < 0.0001 ? '<0.01' : costReal.toFixed(4);

        // H6: Tiempo medio por lenguaje
        const latencyData = data.latency_by_language || [];
        const latencyHtml = latencyData.length > 0
            ? latencyData.map(function(item) {
                const latencySec = (item.avg_latency_ms / 1000).toFixed(1);
                const barWidth = Math.min(100, Math.max(5, item.avg_latency_ms / 50));
                return '<div class="text-sm" style="display:flex;align-items:center;gap:10px;padding:6px 0;border-bottom:1px solid var(--border-muted)">' +
                    '<span style="color:var(--accent);font-weight:600;min-width:100px;font-family:var(--font-mono);font-size:0.82rem;">' + item.language + '</span>' +
                    '<div style="flex:1;background:var(--bg-input);border-radius:3px;height:8px;overflow:hidden;">' +
                        '<div style="width:' + barWidth + '%;height:100%;background:var(--accent);border-radius:3px;transition:width 0.4s ease;"></div>' +
                    '</div>' +
                    '<span style="color:var(--text-primary);font-weight:600;font-family:var(--font-mono);font-size:0.85rem;min-width:60px;text-align:right;">' + latencySec + 's</span>' +
                    '<span style="color:var(--text-muted);font-size:0.75rem;min-width:50px;text-align:right;">' + item.total_calls + ' calls</span>' +
                    '<span style="color:var(--text-muted);font-size:0.72rem;min-width:30px;text-align:right;">' + item.projects_count + ' proj</span>' +
                '</div>';
            }).join('')
            : '<span class="text-muted text-sm">Sin datos de latencia por lenguaje</span>';

        container.innerHTML =
            '<div class="metrics-grid">' +
                '<div class="metric-card"><div class="metric-label">Tasa de exito</div><div class="metric-value" style="color:var(--' + rateColor + ')">' + successRate.toFixed(0) + '%</div></div>' +
                '<div class="metric-card"><div class="metric-label">Coste total</div><div class="metric-value">$' + costDisplay + '</div><div class="metric-detail">con factor de infraestructura 12%</div></div>' +
                '<div class="metric-card"><div class="metric-label">Cache hits</div><div class="metric-value">' + (data.cache_entries || 0) + '</div></div>' +
                '<div class="metric-card"><div class="metric-label">Llamadas LLM</div><div class="metric-value">' + Object.values(data.models_used || {}).reduce((a,b) => a+b, 0) + '</div></div>' +
            '</div>' +
            '<div class="detail-section"><h3>Modelos utilizados</h3>' + modelsHtml + '</div>' +
            '<div class="detail-section"><h3>Tiempo medio por lenguaje</h3><p class="section-desc" style="margin-bottom:12px;">Latencia media de respuesta LLM agrupada por lenguaje de programacion (ultimos 10 proyectos)</p>' + latencyHtml + '</div>';
    }

    /* ===== PROJECTS TABLE ===== */
    async function refreshProjects() {
        try {
            const res = await fetch('/projects');
            const data = await res.json();
            const list = Array.isArray(data) ? data : (data.projects || []);
            const tbody = $('#projects-table');
            if (list.length === 0) {
                tbody.innerHTML = '<tr><td colspan="5" class="text-muted text-sm" style="text-align:center;padding:24px;">No hay proyectos en esta sesion.</td></tr>';
                return;
            }
            tbody.innerHTML = list.map(p => {
                const badge = '<span class="badge ' + p.status + '">' + statusLabel(p.status) + '</span>';
                const progress = p.progress ? p.progress.completed + '/' + p.progress.total : '-';
                const progressHtml = p.progress ? '<div class="progress-bar"><div class="progress-fill' + (p.progress.failed > 0 ? ' red' : (p.progress.completed === p.progress.total ? ' green' : '')) + '" style="width:' + (p.progress.total > 0 ? (p.progress.completed / p.progress.total * 100) : 0) + '%"></div></div>' : '';
                const fecha = p.created_at ? new Date(p.created_at).toLocaleString('es-ES', { day:'2-digit', month:'short', hour:'2-digit', minute:'2-digit' }) : '-';
                return '<tr><td class="id-cell">' + (p.id || '') + '</td><td>' + badge + '</td><td style="min-width:120px">' + progressHtml + '</td><td class="text-sm text-muted">' + fecha + '</td><td><a href="/dashboard/' + (p.id || '') + '" onclick="event.preventDefault();selectProjectAndLoad(&apos;' + (p.id || '') + '&apos;)">Metricas</a></td></tr>';
            }).join('');
            populateProjectSelect(list);
        } catch (e) {
            console.error('Error cargando proyectos:', e);
        }
    }

    function populateProjectSelect(list) {
        const sel = $('#project-select');
        const current = sel.value;
        sel.innerHTML = '<option value="">-- Selecciona un proyecto --</option>';
        (list || []).forEach(p => {
            const opt = document.createElement('option');
            opt.value = p.id;
            opt.textContent = p.id + ' — ' + statusLabel(p.status);
            sel.appendChild(opt);
        });
        if (current) sel.value = current;
        $('#dashboard-btn').disabled = !sel.value;
    }

    function selectProjectAndLoad(projectId) {
        const sel = $('#project-select');
        sel.value = projectId;
        switchTab('dashboard');
        loadDashboard();
    }

    $('#project-select').addEventListener('change', () => {
        $('#dashboard-btn').disabled = !$('#project-select').value;
    });


    /* ===== PROYECTOS TAB (Refactorizacion) ===== */
    async function refreshProjectsList() {
        try {
            const res = await fetch('/projects');
            const data = await res.json();
            const list = Array.isArray(data) ? data : (data.projects || []);
            const sel = $('#proyectos-select');
            const current = sel ? sel.value : '';
            if (sel) {
                sel.innerHTML = '<option value="">-- Selecciona un proyecto --</option>';
                list.forEach(function(p) {
                    const opt = document.createElement('option');
                    opt.value = p.project_id || p.id || '';
                    const statusText = statusLabel ? statusLabel(p.status) : (p.status || '--');
                    opt.textContent = (p.project_id || p.id || '') + ' - ' + statusText;
                    sel.appendChild(opt);
                });
                if (current) sel.value = current;
            }
        } catch(e) {
            console.warn('Error cargando lista de proyectos:', e);
        }
    }

    async function loadProjectDetail(projectId) {
        const detailEl = $('#proyectos-detail');
        const noSelEl = $('#proyectos-no-selection');
        if (!projectId) {
            if (detailEl) detailEl.style.display = 'none';
            if (noSelEl) noSelEl.style.display = 'block';
            return;
        }
        if (detailEl) detailEl.style.display = 'block';
        if (noSelEl) noSelEl.style.display = 'none';

        try {
            const res = await fetch('/api/project/' + encodeURIComponent(projectId));
            const data = await res.json();
            renderProjectDetail(data);
        } catch(e) {
            console.error('Error cargando detalle del proyecto:', e);
            const infoEl = $('#proyectos-info');
            if (infoEl) infoEl.innerHTML = '<span style="color:var(--red)">Error al cargar detalles del proyecto.</span>';
        }
    }

    function renderProjectDetail(data) {
        var infoEl = $('#proyectos-info');
        if (infoEl) {
            var statusBadge = '<span class="badge ' + (data.status || 'unknown') + '">' + (data.status || 'unknown') + '</span>';
            var created = data.created_at ? new Date(data.created_at).toLocaleString('es-ES') : '--';
            infoEl.innerHTML =
                '<div style="display:flex;gap:16px;flex-wrap:wrap;">' +
                '<div><strong>ID:</strong> ' + (data.project_id || '--') + '</div>' +
                '<div><strong>Estado:</strong> ' + statusBadge + '</div>' +
                '<div><strong>Creado:</strong> ' + created + '</div>' +
                '<div><strong>Tareas:</strong> ' + (data.tasks_completed || 0) + '/' + (data.tasks_total || 0) + '</div>' +
                '</div>';
        }

        var specEl = $('#proyectos-spec');
        if (specEl) {
            if (data.spec_content) {
                specEl.textContent = data.spec_content;
            } else {
                specEl.innerHTML = '<span class="text-muted">Sin spec disponible.</span>';
            }
        }

        var planEl = $('#proyectos-plan');
        if (planEl) {
            if (data.plan_tasks && data.plan_tasks.length > 0) {
                var html = '<table class="data-table" style="width:100%;"><thead><tr><th>#</th><th>Tarea</th><th>Estado</th><th>Agente</th></tr></thead><tbody>';
                data.plan_tasks.forEach(function(t, i) {
                    var st = t.status || 'pending';
                    var stLabel = statusLabel ? statusLabel(st) : st;
                    html += '<tr><td style="color:var(--text-muted);font-family:var(--font-mono);font-size:0.78rem;">' + (i+1) + '</td><td>' + (t.name || t.description || '--') + '</td><td><span class="badge ' + st + '">' + stLabel + '</span></td><td style="color:var(--text-muted);font-size:0.8rem;">' + (t.agent || '--') + '</td></tr>';
                });
                html += '</tbody></table>';
                planEl.innerHTML = html;
            } else {
                planEl.innerHTML = '<span class="text-muted text-sm">Sin plan disponible.</span>';
            }
        }

        var filesEl = $('#proyectos-files');
        if (filesEl) {
            var files = data.files || [];
            if (files.length > 0) {
                var html = '';
                var categories = {scripts: [], configs: [], folders: [], images: [], other: []};
                files.forEach(function(f) {
                    var ext = (f.name || '').split('.').pop().toLowerCase();
                    var scriptExts = ['py', 'js', 'ts', 'sh', 'bash', 'rb', 'go', 'rs', 'java', 'cpp', 'c', 'h', 'cs', 'php', 'sql', 'r'];
                    var configExts = ['json', 'yaml', 'yml', 'toml', 'ini', 'cfg', 'conf', 'env', 'txt', 'md', 'csv'];
                    var imageExts = ['png', 'jpg', 'jpeg', 'gif', 'svg', 'ico', 'webp', 'bmp'];

                    if (scriptExts.indexOf(ext) >= 0) {
                        categories.scripts.push(f);
                    } else if (configExts.indexOf(ext) >= 0) {
                        categories.configs.push(f);
                    } else if (imageExts.indexOf(ext) >= 0) {
                        categories.images.push(f);
                    } else if (f.type === 'directory' || f.type === 'folder') {
                        categories.folders.push(f);
                    } else {
                        categories.other.push(f);
                    }
                });

                function renderCat(label, icon, items) {
                    if (items.length === 0) return '';
                    var h = '<div style="margin-bottom:12px;">';
                    h += '<div style="color:var(--text-secondary);font-weight:600;font-size:0.82rem;margin-bottom:6px;font-family:var(--font-mono);">' + icon + ' ' + label + ' (' + items.length + ')</div>';
                    items.forEach(function(f) {
                        var size = f.size ? ' (' + f.size + ')' : '';
                        h += '<div style="padding:3px 0;color:var(--text-primary);font-size:0.8rem;">';
                        h += '<span style="color:var(--text-muted);margin-right:6px;">' + (f.type === 'directory' ? '[DIR]' : '[FILE]') + '</span>';
                        h += f.name + size;
                        h += '</div>';
                    });
                    h += '</div>';
                    return h;
                }

                html += renderCat('Scripts', 'SCR', categories.scripts);
                html += renderCat('Configuracion', 'CFG', categories.configs);
                html += renderCat('Carpetas', 'DIR', categories.folders);
                html += renderCat('Imagenes', 'IMG', categories.images);
                if (categories.other.length > 0) {
                    html += renderCat('Otros', 'OTH', categories.other);
                }

                filesEl.innerHTML = html || '<span class="text-muted">Sin elementos.</span>';
            } else {
                filesEl.innerHTML = '<span class="text-muted">Sin elementos en este proyecto.</span>';
            }
        }
    }

    function goRefactorProject() {
        var projectId = $('#proyectos-select').value;
        if (!projectId) return;
        switchTab('sdd');
        /* CHAT-R.4: ruta de proyecto ahora vive en el campo del Chat */
        var pathInput = $('#chat-project-path');
        if (pathInput) {
            var specDir = '/specs/' + projectId;
            pathInput.value = specDir;
        }
    }

    function goProjectProgress() {
        var projectId = $('#proyectos-select').value;
        if (!projectId) return;
        activeProjectId = projectId;
        switchTab('progreso');
        refreshProgress();
    }

    function goProjectDashboard() {
        var projectId = $('#proyectos-select').value;
        if (!projectId) return;
        var sel = $('#project-select');
        if (sel) sel.value = projectId;
        switchTab('dashboard');
        loadDashboard();
    }

    /* ===== TOAST NOTIFICATIONS (H5) ===== */
    function showToast(message, type, duration) {
        type = type || 'info';
        duration = duration || 4000;
        const container = $('#toast-container');
        const toast = document.createElement('div');
        toast.className = 'toast ' + type;
        toast.textContent = message;
        container.appendChild(toast);
        requestAnimationFrame(() => { toast.classList.add('show'); });
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 300);
        }, duration);
    }

    /* ===== PLAN REVIEW MODAL (H1) ===== */
    let pendingPlanSpec = null;

    function showPlanReview(projectId, planData) {
        pendingPlanSpec = null;
        const modal = $('#plan-review-modal');
        const body = $('#plan-review-body');
        const tasks = planData.tasks || [];

        let html = '<div style="margin-bottom:16px"><p class="text-sm" style="color:var(--text-secondary)">El plan contiene <strong>' + tasks.length + '</strong> tareas. Revisa y aprueba para iniciar la ejecucion.</p></div>';

        tasks.forEach((t, i) => {
            const deps = t.dependencies || t.deps || [];
            const depsStr = deps.length > 0 ? 'Depende de: ' + deps.join(', ') : 'Sin dependencias';
            const critStr = t.acceptance_criterion ? '<br>' + t.acceptance_criterion.substring(0, 120) + (t.acceptance_criterion.length > 120 ? '...' : '') : '';
            html += '<div class="plan-task">' +
                '<div class="plan-task-num">' + (i + 1) + '</div>' +
                '<div class="plan-task-content">' +
                    '<div class="plan-task-title">' + (t.title || t.description || 'Tarea ' + (i + 1)) + '</div>' +
                    '<div class="plan-task-meta">' + depsStr + critStr + '</div>' +
                '</div></div>';
        });

        body.innerHTML = html;
        modal.classList.add('active');
    }

    function closePlanReview() {
        $('#plan-review-modal').classList.remove('active');
        pendingPlanSpec = null;
    }

    function approvePlan() {
        if (!pendingPlanSpec) { showToast('No hay plan pendiente', 'warning'); return; }
        closePlanReview();
        showToast('Plan aprobado. Iniciando ejecucion...', 'success');
        executeApprovedPlan(pendingPlanSpec);
    }

    async function executeApprovedPlan(spec) {
        try {
            const res = await fetch('/run', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ spec: spec })
            });
            const data = await res.json();
            if (data.project_id) {
                activeProjectId = data.project_id;
                showToast('Proyecto ' + data.project_id + ' iniciado', 'success');
                refreshProjects();
                startProgressStream(data.project_id);
                switchTab('progreso');
            } else {
                showToast('Error al iniciar: ' + JSON.stringify(data), 'error');
            }
        } catch (error) {
            showToast('Error de conexion: ' + error.message, 'error');
        }
    }

    /* ===== PROGRESS SECTION (H2) ===== */
    async function refreshProgress() {
        if (!activeProjectId) {
            showToast('No hay proyecto activo', 'warning');
            return;
        }
        const btn = $('#refresh-progress-btn');
        if (btn) btn.classList.add('loading');

        try {
            const res = await fetch('/status/' + activeProjectId);
            const data = await res.json();
            renderProgress(data);
        } catch (e) {
            console.error('Error cargando progreso:', e);
        }
        if (btn) btn.classList.remove('loading');
    }

    function renderProgress(data) {
        const noProject = $('#progress-no-project');
        const content = $('#progress-content');
        if (!data || !data.id) { noProject.classList.remove('hidden'); content.classList.add('hidden'); return; }
        noProject.classList.add('hidden'); content.classList.remove('hidden');

        $('#progress-project-id').textContent = data.id;

        fetch('/status/' + data.id).then(r => r.json()).then(status => {
            const prog = status.progress || { total: 0, completed: 0, failed: 0 };
            $('#progress-completed').textContent = prog.completed;
            $('#progress-failed').textContent = prog.failed;
            const pct = prog.total > 0 ? (prog.completed / prog.total * 100) : 0;
            $('#progress-bar-fill').style.width = pct + '%';
            if (prog.failed > 0) $('#progress-bar-fill').className = 'progress-fill red';
            else if (pct === 100) $('#progress-bar-fill').className = 'progress-fill green';
            else $('#progress-bar-fill').className = 'progress-fill';
        }).catch(() => {});

        // Fetch pipeline status for detailed task info
        fetch('/pipeline/' + data.id + '/status').then(r => r.json()).then(pipeline => {
            const tbody = $('#progress-tasks-body');
            if (!pipeline.tasks || pipeline.tasks.length === 0) {
                tbody.innerHTML = '<div class="text-muted text-sm" style="text-align:center;padding:16px">El plan aun no se ha generado o no hay tareas.</div>';
                return;
            }
            tbody.innerHTML = pipeline.tasks.map((t, i) => {
                const st = statusLabel(t.status);
                const badgeClass = t.status === 'completed' ? 'completed' : t.status === 'failed' ? 'failed' : t.status === 'executing' ? 'running' : 'pending';
                return '<div class="progress-task-row">' +
                    '<div class="progress-task-num">' + (i + 1) + '</div>' +
                    '<div class="progress-task-name" title="' + (t.script || '') + '">' + (t.script || 'Tarea ' + (i + 1)) + '</div>' +
                    '<div><span class="badge ' + badgeClass + '">' + st + '</span></div>' +
                    '<div class="progress-task-model">' + (pipeline.model_used_planner || '-') + '</div>' +
                    '<div class="progress-task-time">-</div>' +
                    '<div class="progress-task-time">' + (t.attempt || '-') + '</div>' +
                '</div>';
            }).join('');
        }).catch(() => {
            $('#progress-tasks-body').innerHTML = '<div class="text-muted text-sm" style="text-align:center;padding:16px">Cargando tareas...</div>';
        });
    }

    const SPECS_DIR_VAL = '/specs';

    /* ===== SSE PROGRESS ===== */
    function startProgressStream(projectId) {
        if (eventSource) { eventSource.close(); }
        activeProjectId = projectId;
        switchTab('progreso');
        eventSource = new EventSource('/stream/' + projectId);
        eventSource.onmessage = (e) => {
            try {
                const event = JSON.parse(e.data);
                if (event.type === 'done') {
                    eventSource.close();
                    refreshProjects();
                    refreshProgress();
                    const status = event.status;
                    if (status === 'completed') showToast('Proyecto completado con exito', 'success', 6000);
                    else showToast('Proyecto finalizado con errores', 'error', 6000);
                    return;
                }
                // Auto-refresh progress on every event
                refreshProgress();
                refreshProjects();
            } catch (err) { console.warn('SSE parse error:', err); }
        };
        eventSource.onerror = () => {
            setTimeout(() => { try { eventSource.close(); } catch(e){} refreshProjects(); refreshProgress(); }, 3000);
        };
    }

    /* ===== ALERTS ===== */
    function addInlineAlert(parentId, type, message, isParent) {
        const parent = isParent ? $('#' + parentId) : $('#' + parentId).parentElement || $('#' + parentId);
        if (!parent) return;
        const existing = parent.querySelector('.alert');
        if (existing) existing.remove();
        const alert = document.createElement('div');
        alert.className = 'alert ' + type;
        alert.textContent = message;
        parent.insertBefore(alert, parent.firstChild);
    }

    function statusLabel(s) {
        const map = { pending: 'Pendiente', running: 'Ejecutando', completed: 'Completado', failed: 'Fallido', resuming: 'Reanudando' };
        return map[s] || s;
    }

    /* ===== FASE 4: AGENT DASHBOARD (UX2+) ===== */
    const AGENT_NAMES = ['planner', 'coder', 'integrator', 'validator'];
    const AGENT_STATUS_LABELS = { idle: 'idle', started: 'activo', progress: 'activo', done: 'completado', failed: 'fallido' };

    // Track which agents have been seen (for dynamic show/hide)
    const _agentSeen = {};

    function resetAgentCards() {
        AGENT_NAMES.forEach(name => {
            const card = document.getElementById('card-' + name);
            if (card) { card.className = 'agent-card agent-card-hidden'; }
            const status = document.getElementById('status-' + name);
            if (status) { status.textContent = 'idle'; }
            // Clear task description
            const taskEl = document.getElementById('task-' + name);
            if (taskEl) { taskEl.textContent = ''; }
            // Hide context row
            const ctxRow = document.getElementById('ctx-row-' + name);
            if (ctxRow) { ctxRow.style.display = 'none'; }
        });
        // Reset seen tracker
        for (var k in _agentSeen) { delete _agentSeen[k]; }
    }

    function handleAgentEvent(evt) {
        if (!evt || !evt.type) return;
        const agent = evt.data && evt.data.agent;
        if (!agent) return;

        // Filter to known agents only
        if (!AGENT_NAMES.includes(agent)) return;

        const card = document.getElementById('card-' + agent);
        const statusEl = document.getElementById('status-' + agent);
        const modelEl = document.getElementById('model-' + agent);
        const tokensEl = document.getElementById('tokens-' + agent);
        const latencyEl = document.getElementById('latency-' + agent);
        const pbarEl = document.getElementById('pbar-' + agent);
        const taskEl = document.getElementById('task-' + agent);

        if (!card) return;

        // Determine state from event type
        let state = 'idle';
        if (evt.type === 'agent:started') state = 'started';
        else if (evt.type === 'agent:progress') state = 'progress';
        else if (evt.type === 'agent:done') state = 'done';
        else if (evt.type === 'agent:failed') state = 'failed';

        // --- Dynamic visibility: show card when agent becomes active ---
        if (state === 'started' || state === 'progress') {
            _agentSeen[agent] = true;
            card.classList.remove('agent-card-hidden');
        }
        // Update card class (keep data-agent)
        card.className = 'agent-card ' + state;

        // Update status badge
        if (statusEl) statusEl.textContent = AGENT_STATUS_LABELS[state] || state;

        // Update model
        if (modelEl && evt.data.model) {
            const shortModel = evt.data.model.split('/').pop();
            modelEl.textContent = shortModel || '--';
            modelEl.title = evt.data.model;
        }

        // Update tokens
        if (tokensEl && evt.data.tokens_used != null) {
            tokensEl.textContent = evt.data.tokens_used.toLocaleString();
        }

        // Update latency
        if (latencyEl && evt.data.latency_ms != null) {
            latencyEl.textContent = (evt.data.latency_ms / 1000).toFixed(1) + 's';
        }

        // Update progress bar
        if (pbarEl && evt.data.pct != null) {
            const pct = Math.min(100, Math.max(0, evt.data.pct));
            pbarEl.style.width = pct + '%';
            if (state === 'failed') pbarEl.className = 'progress-fill red';
            else if (state === 'done') pbarEl.className = 'progress-fill green';
            else pbarEl.className = 'progress-fill';
        }

        // --- NEW: Update task description ---
        if (taskEl) {
            const desc = evt.data.task_description || '';
            if (desc) {
                taskEl.textContent = desc;
                taskEl.title = desc;
            }
        }

        // --- NEW: Update context metrics ---
        const ctxRow = document.getElementById('ctx-row-' + agent);
        const ctxFill = document.getElementById('ctx-fill-' + agent);
        const ctxPct = document.getElementById('ctx-pct-' + agent);
        if (ctxRow && evt.data.context_pct != null) {
            const cpct = Math.min(100, Math.max(0, evt.data.context_pct));
            ctxRow.style.display = 'flex';
            if (ctxFill) {
                ctxFill.style.width = cpct + '%';
                ctxFill.className = 'agent-context-fill' +
                    (cpct > 85 ? ' danger' : cpct > 60 ? ' warn' : '');
            }
            if (ctxPct) {
                const ctxUsed = evt.data.context_used || '?';
                const ctxMax = evt.data.context_max || '?';
                ctxPct.textContent = cpct.toFixed(0) + '%';
                ctxPct.title = 'Contexto: ' + ctxUsed + ' / ' + ctxMax + ' tokens';
            }
        }
    }

    // Hook into existing SSE notification stream to filter agent events
    const _origInitNotifs = typeof initNotifications === 'function' ? initNotifications : null;
    function initNotificationsWithAgents() {
        // Reset agent cards on init
        resetAgentCards();
        // Call original notification init if it exists
        if (_origInitNotifs) _origInitNotifs();

        // Also listen on the main notification SSE for agent events
        const agentEs = new EventSource('/notifications/stream');
        agentEs.onmessage = function(e) {
            try {
                const evt = JSON.parse(e.data);
                if (evt.type && evt.type.startsWith('agent:')) {
                    handleAgentEvent(evt);
                }
                /* C2: Mostrar notificaciones de chat como toast */
                if (evt.type === 'chat_escalate') {
                    showToast('Escalando a mejor modelo disponible (planning)...', 'info', 3000);
                } else if (evt.type === 'chat_model_selected') {
                    showToast('Modelo: ' + (evt.data && evt.data.model ? evt.data.model : '?'), 'info', 3000);
                }
            } catch(err) {}
        };
        agentEs.onerror = function() {
            setTimeout(function() { try { agentEs.close(); } catch(e){} }, 5000);
        };
    }
    // Override
    initNotifications = initNotificationsWithAgents;

    /* ===== P5: NOTIFICATION JS (inject from bridge) ===== */
    <!-- __P5_JS__ -->

    /* ===== UX1: FAILURE AUDITOR JS ===== */
    const _faAuditor = new (function() {
        this.history = [];
    })();

    async function runFailureAuditor() {
        const taskId = $('#fa-task-id').value.trim() || 'unknown';
        const script = $('#fa-script').value.trim();
        const agent = $('#fa-agent').value;
        const attempt = parseInt($('#fa-attempt').value) || 1;
        const maxAttempts = parseInt($('#fa-max-attempts').value) || 3;
        const error = $('#fa-error').value.trim();
        const coderOutput = $('#fa-coder-output').value.trim();

        if (!error) {
            $('#fa-result-content').innerHTML = '<div class="alert warning">Introduce un error para diagnosticar.</div>';
            $('#fa-result').classList.remove('hidden');
            return;
        }

        $('#fa-result-content').innerHTML = '<p class="text-muted">Diagnosticando...</p>';
        $('#fa-result').classList.remove('hidden');

        try {
            const resp = await fetch('/api/failure-auditor/diagnose', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    task_id: taskId,
                    script: script,
                    agent: agent,
                    attempt: attempt,
                    max_attempts: maxAttempts,
                    error: error,
                    coder_output: coderOutput,
                })
            });
            const data = await resp.json();

            if (data.error) {
                $('#fa-result-content').innerHTML = '<div class="alert error">Error: ' + data.error + '</div>';
                return;
            }

            const d = data.diagnosis;
            const sevIcons = { critical: '🔴', recoverable: '🟡', minor: '🟢' };
            const sevLabels = { critical: 'Critico', recoverable: 'Recuperable', minor: 'Menor' };
            const catLabels = {
                context_insufficient: 'Contexto insuficiente',
                model_limitation: 'Limitacion del modelo',
                prompt_error: 'Error en la planificacion',
                unresolved_dependency: 'Dependencia sin resolver'
            };
            const actLabels = {
                retry: 'Reintentar', replan: 'Replanificar',
                escalate: 'Escalar al Director', split: 'Dividir tarea', abort: 'Abortar'
            };
            const sevBadge = d.severity === 'critical' ? 'failed' : d.severity === 'recoverable' ? 'pending' : 'completed';

            let html = '<div style="display:flex;gap:12px;align-items:center;margin-bottom:12px;">';
            html += '<span style="font-size:1.5rem">' + (sevIcons[d.severity] || '⚪') + '</span>';
            html += '<div><strong>' + (catLabels[d.category] || d.category) + '</strong>';
            html += ' <span class="badge ' + sevBadge + '">' + (sevLabels[d.severity] || d.severity) + '</span>';
            html += '</div></div>';
            html += '<p style="margin-bottom:10px;color:var(--text-secondary);font-size:0.88rem;line-height:1.5;">' + (d.description || '') + '</p>';

            if (d.evidence && d.evidence.length > 0) {
                html += '<div style="margin-bottom:10px;"><strong style="font-size:0.82rem;color:var(--text-secondary);">Evidencia:</strong>';
                html += '<ul style="margin-top:4px;padding-left:20px;color:var(--text-muted);font-size:0.82rem;">';
                d.evidence.slice(0, 5).forEach(function(ev) { html += '<li>' + ev + '</li>'; });
                html += '</ul></div>';
            }

            html += '<div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:10px;font-size:0.82rem;">';
            html += '<span><strong>Accion sugerida:</strong> ' + (actLabels[d.suggested_action] || d.suggested_action) + '</span>';
            html += '<span><strong>Continuar:</strong> ' + (d.can_continue ? 'Si' : 'No') + '</span>';
            html += '<span><strong>Abortar:</strong> ' + (d.can_abort ? 'Si' : 'No') + '</span>';
            html += '<span><strong>Escalar:</strong> ' + (d.should_escalate ? 'Si' : 'No') + '</span>';
            html += '</div>';

            if (d.context_for_retry) {
                html += '<div style="padding:10px;background:var(--bg-input);border-radius:6px;border:1px solid var(--border-muted);">';
                html += '<strong style="font-size:0.78rem;color:var(--text-secondary);">Contexto para reintento:</strong>';
                html += '<pre style="margin-top:6px;white-space:pre-wrap;font-size:0.8rem;color:var(--text-primary);">' + d.context_for_retry + '</pre></div>';
            }

            $('#fa-result-content').innerHTML = html;

            // Agregar al historial
            _faAuditor.history.unshift({
                time: new Date().toLocaleTimeString(),
                task_id: taskId,
                category: d.category,
                severity: d.severity,
                action: d.suggested_action,
            });
            if (_faAuditor.history.length > 20) _faAuditor.history.pop();
            _renderFaHistory();

        } catch (err) {
            $('#fa-result-content').innerHTML = '<div class="alert error">Error de conexion: ' + err.message + '</div>';
        }
    }

    function _renderFaHistory() {
        if (_faAuditor.history.length === 0) {
            $('#fa-history-section').style.display = 'none';
            return;
        }
        $('#fa-history-section').style.display = 'block';
        const catLabels = {
            context_insufficient: 'CtxInsuf', model_limitation: 'ModelLimit',
            prompt_error: 'PromptErr', unresolved_dependency: 'DepSinResolver'
        };
        const sevLabels = { critical: '🔴 Critico', recoverable: '🟡 Recup', minor: '🟢 Menor' };
        const actLabels = {
            retry: 'Reintentar', replan: 'Replanif.',
            escalate: 'Escalar', split: 'Dividir', abort: 'Abortar'
        };
        let rows = '';
        _faAuditor.history.forEach(function(h) {
            rows += '<tr>';
            rows += '<td class="id-cell">' + h.time + '</td>';
            rows += '<td>' + h.task_id + '</td>';
            rows += '<td>' + (catLabels[h.category] || h.category) + '</td>';
            rows += '<td>' + (sevLabels[h.severity] || h.severity) + '</td>';
            rows += '<td>' + (actLabels[h.action] || h.action) + '</td>';
            rows += '</tr>';
        });
        $('#fa-history-body').innerHTML = rows;
    }

    function loadSampleError() {
        const samples = [
            {
                task_id: 'T1', script: 'modulo_grande.py', agent: 'coder',
                attempt: 1, max_attempts: 3,
                error: '[CONTEXT_EXCEEDED] El contexto del modelo excedio el limite maximo permitido.',
                coder_output: ''
            },
            {
                task_id: 'T3', script: 'api.py', agent: 'planner',
                attempt: 1, max_attempts: 3,
                error: 'V3PlanParser: Falta campo SCRIPT. No se encontraron bloques validos en la salida del planificador.',
                coder_output: ''
            },
            {
                task_id: 'T2', script: 'servicio.py', agent: 'coder',
                attempt: 2, max_attempts: 3,
                error: 'JSONDecodeError: Expecting value: line 1 column 1 (char 0)',
                coder_output: 'El modelo no genero codigo valido.'
            },
            {
                task_id: 'T4', script: 'utils.py', agent: 'validator',
                attempt: 2, max_attempts: 3,
                error: 'RF4: cambios bloqueados — RF5: regresion detectada',
                coder_output: '# codigo integrado'
            }
        ];
        const s = samples[Math.floor(Math.random() * samples.length)];
        $('#fa-task-id').value = s.task_id;
        $('#fa-script').value = s.script;
        $('#fa-agent').value = s.agent;
        $('#fa-attempt').value = s.attempt;
        $('#fa-max-attempts').value = s.max_attempts;
        $('#fa-error').value = s.error;
        $('#fa-coder-output').value = s.coder_output;
    }

    /* ===== INIT ===== */
    document.addEventListener('DOMContentLoaded', () => {
        chatInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendChat();
            }
        });
        chatInput.addEventListener('input', () => {
            chatInput.style.height = 'auto';
            chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + 'px';
        });
        try { refreshProjects(); refreshProjectsList(); } catch(e) { console.warn('Error cargando proyectos:', e); }
        try { initNotifications(); } catch(e) { console.warn('Notifications not initialized:', e); }

        // H5: Poll progreso si hay proyecto activo
        setInterval(() => { if (activeProjectId) refreshProgress(); }, 5000);
    });
    </script>
</body>
</html>
"""


def get_html() -> str:
    """Retorna el template HTML como string."""
    return HTML_TEMPLATE


if __name__ == "__main__":
    import sys
    html = get_html()
    print(f"Template HTML: {len(html)} caracteres, {html.count(chr(10))} lineas")
    assert len(html) > 10000, "Template demasiado pequeno"
    assert "<!DOCTYPE html>" in html, "Falta DOCTYPE"
    assert "</html>" in html, "Falta cierre html"
    assert "__P5_CSS__" in html, "Falta placeholder __P5_CSS__"
    assert "__P5_JS__" in html, "Falta placeholder __P5_JS__"
    assert "__THEME_ROOT__" in html, "Falta placeholder __THEME_ROOT__"
    print("[PASS] Template valido")
    sys.exit(0)
