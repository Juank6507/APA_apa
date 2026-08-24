# shared_tabs.py — HTML/CSS/JS generator for APA Assembler pywebview GUI
# Version: 6.2.0 — Fix: pool/arena notifs from parent, click-filter, tab badge
# Generates a complete HTML page with 7 tabs for embedded browser.
# All text in Spanish. No external dependencies. Self-validating.
#
# Usage:
#   from shared_tabs import build_full_page
#   html = build_full_page('ensamblador')  # or 'app'

from __future__ import annotations

import html as _html_module
import json
import re
import sys
import time
from typing import Dict, List, Optional, Tuple


# ─────────────────────────────────────────────────────────────────────────────
# CSS: Theme variables and base styles
# ─────────────────────────────────────────────────────────────────────────────

_CSS_THEME = """
:root {
    --bg-body: #1b2838;
    --bg-surface: #243447;
    --bg-elevated: #2d4059;
    --bg-input: #1e2d3d;
    --bg-hover: #374f6b;
    --border-default: #4a6278;
    --border-muted: #364d63;
    --border-accent: #e8a838;
    --text-primary: #f5e6c8;
    --text-secondary: #d4c4a0;
    --text-muted: #baae87;
    --accent: #e8a838;
    --accent-hover: #f0bc50;
    --green: #3fb950;
    --red: #f85149;
    --amber: #d29922;
    --purple: #bc8cff;
    --blue: #3b82f6;
    --teal: #14b8a6;
    --cyan: #06b6d4;
    --slate: #94a3b8;
    --font-sans: 'Segoe UI', system-ui, sans-serif;
    --font-mono: 'Consolas', 'Courier New', monospace;
    --radius-sm: 6px;
    --radius-md: 8px;
}
"""

_CSS_BASE = """
* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

html, body {
    width: 100%;
    height: 100%;
    overflow: hidden;
    font-family: var(--font-sans);
    font-size: 14px;
    color: var(--text-primary);
    background: var(--bg-body);
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
}

::-webkit-scrollbar {
    width: 8px;
    height: 8px;
}

::-webkit-scrollbar-track {
    background: var(--bg-body);
    border-radius: 4px;
}

::-webkit-scrollbar-thumb {
    background: var(--border-default);
    border-radius: 4px;
}

::-webkit-scrollbar-thumb:hover {
    background: var(--accent);
}

::selection {
    background: var(--accent);
    color: var(--bg-body);
}

input, textarea, select, button {
    font-family: var(--font-sans);
    font-size: 13px;
    outline: none;
}

button {
    cursor: pointer;
    border: none;
    border-radius: var(--radius-sm);
    padding: 8px 16px;
    font-weight: 600;
    transition: all 0.2s ease;
}

button:active {
    transform: scale(0.97);
}

textarea {
    resize: none;
}

a {
    color: var(--accent);
    text-decoration: none;
}

a:hover {
    text-decoration: underline;
}
"""

# ─────────────────────────────────────────────────────────────────────────────
# CSS: Tab bar
# ─────────────────────────────────────────────────────────────────────────────

_CSS_TABBAR = """
.tab-bar {
    display: flex;
    align-items: center;
    height: 44px;
    background: var(--bg-surface);
    border-bottom: 2px solid var(--border-muted);
    padding: 0 8px;
    gap: 2px;
    overflow-x: auto;
    overflow-y: hidden;
    flex-shrink: 0;
    -webkit-user-select: none;
    user-select: none;
}

.tab-btn {
    display: flex;
    align-items: center;
    gap: 6px;
    height: 36px;
    padding: 0 16px;
    background: transparent;
    color: var(--text-secondary);
    border: none;
    border-radius: var(--radius-sm) var(--radius-sm) 0 0;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s ease;
    white-space: nowrap;
    position: relative;
}

.tab-btn:hover {
    background: var(--bg-hover);
    color: var(--text-primary);
}

.tab-btn.active {
    background: var(--bg-elevated);
    color: var(--accent);
}

.tab-btn.active::after {
    content: '';
    position: absolute;
    bottom: -2px;
    left: 0;
    right: 0;
    height: 2px;
    background: var(--accent);
    border-radius: 2px 2px 0 0;
}

.tab-btn .tab-icon {
    font-size: 14px;
    opacity: 0.7;
}

.tab-btn.active .tab-icon {
    opacity: 1.0;
}

.tab-spacer {
    flex: 1;
}

.tab-btn-close {
    color: var(--red);
    font-size: 18px;
    padding: 0 12px;
    margin-left: auto;
    background: transparent;
    border: none;
    line-height: 1;
    font-weight: 400;
}

.tab-btn-close:hover {
    background: rgba(248, 81, 73, 0.2);
    color: var(--red);
}

.tab-badge {
    background: var(--red);
    color: #fff;
    font-size: 10px;
    min-width: 18px;
    height: 18px;
    line-height: 18px;
    padding: 0 5px;
    border-radius: 9px;
    font-weight: 700;
    margin-left: 4px;
    text-align: center;
    display: inline-flex;
    align-items: center;
    justify-content: center;
}
"""

# ─────────────────────────────────────────────────────────────────────────────
# CSS: Panel & layout
# ─────────────────────────────────────────────────────────────────────────────

_CSS_LAYOUT = """
.app-container {
    display: flex;
    flex-direction: column;
    height: 100vh;
    width: 100vw;
}

.app-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: 36px;
    padding: 0 16px;
    background: var(--bg-surface);
    border-bottom: 1px solid var(--border-muted);
    flex-shrink: 0;
}

.app-header .app-title {
    font-size: 13px;
    font-weight: 700;
    color: var(--accent);
    letter-spacing: 0.5px;
}

.app-header .header-right {
    display: flex;
    align-items: center;
    gap: 8px;
}

.app-header .header-right span {
    font-size: 11px;
    color: var(--text-muted);
}

.tab-panel {
    display: none;
    flex: 1;
    overflow: hidden;
    padding: 16px;
    background: var(--bg-body);
}

.tab-panel.active {
    display: flex;
    flex-direction: column;
}

.panel-section {
    margin-bottom: 12px;
}

.panel-section:last-child {
    margin-bottom: 0;
}

.section-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;
    font-size: 12px;
    font-weight: 700;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.8px;
}

.section-header .section-icon {
    color: var(--accent);
    font-size: 13px;
}

.row {
    display: flex;
    gap: 10px;
    align-items: stretch;
}

.row-stretch {
    display: flex;
    gap: 10px;
    align-items: stretch;
    flex: 1;
}

.col {
    display: flex;
    flex-direction: column;
}

.col-1 { flex: 1; min-width: 0; }
.col-2 { flex: 2; min-width: 0; }
.col-3 { flex: 3; min-width: 0; }
.col-auto { flex: 0 0 auto; }
.col-fixed-300 { flex: 0 0 300px; }
.col-fixed-350 { flex: 0 0 350px; }
.col-fixed-400 { flex: 0 0 400px; }

.gap-xs { gap: 4px; }
.gap-sm { gap: 6px; }
.gap-md { gap: 10px; }
.gap-lg { gap: 16px; }

.flex-1 { flex: 1; min-width: 0; }
.flex-auto { flex: 0 0 auto; }
.flex-wrap { flex-wrap: wrap; }

.align-start { align-items: flex-start; }
.align-center { align-items: center; }
.align-end { align-items: flex-end; }

.justify-between { justify-content: space-between; }
.justify-end { justify-content: flex-end; }

.mb-sm { margin-bottom: 6px; }
.mb-md { margin-bottom: 10px; }
.mb-lg { margin-bottom: 16px; }

.mt-sm { margin-top: 6px; }
.mt-md { margin-top: 10px; }

.overflow-hidden { overflow: hidden; }
.overflow-auto { overflow: auto; }

.text-mono { font-family: var(--font-mono); }
.text-sm { font-size: 12px; }
.text-xs { font-size: 11px; }
.text-lg { font-size: 16px; }
.text-muted { color: var(--text-muted); }
.text-secondary { color: var(--text-secondary); }
.text-accent { color: var(--accent); }
.text-green { color: var(--green); }
.text-red { color: var(--red); }
.text-amber { color: var(--amber); }
.text-purple { color: var(--purple); }
.text-blue { color: var(--blue); }
.text-teal { color: var(--teal); }
.text-cyan { color: var(--cyan); }
.text-slate { color: var(--slate); }
.fw-bold { font-weight: 700; }
.fw-semi { font-weight: 600; }
.text-center { text-align: center; }
.text-right { text-align: right; }
.text-ellipsis {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
"""

# ─────────────────────────────────────────────────────────────────────────────
# CSS: Form elements
# ─────────────────────────────────────────────────────────────────────────────

_CSS_FORMS = """
.form-group {
    display: flex;
    flex-direction: column;
    gap: 4px;
    margin-bottom: 8px;
}

.form-group:last-child {
    margin-bottom: 0;
}

.form-label {
    font-size: 12px;
    font-weight: 600;
    color: var(--text-secondary);
}

.form-row {
    display: flex;
    align-items: center;
    gap: 8px;
}

.form-input,
.form-select {
    width: 100%;
    height: 34px;
    padding: 0 10px;
    background: var(--bg-input);
    color: var(--text-primary);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-sm);
    font-size: 13px;
    transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.form-input:focus,
.form-select:focus {
    border-color: var(--accent);
    box-shadow: 0 0 0 2px rgba(232, 168, 56, 0.15);
}

.form-input::placeholder {
    color: var(--text-muted);
    opacity: 0.6;
}

.form-select {
    cursor: pointer;
    appearance: none;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath d='M2 4l4 4 4-4' fill='none' stroke='%23baae87' stroke-width='1.5'/%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: right 10px center;
    padding-right: 28px;
}

.form-textarea {
    width: 100%;
    padding: 10px;
    background: var(--bg-input);
    color: var(--text-primary);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-sm);
    font-family: var(--font-mono);
    font-size: 13px;
    line-height: 1.5;
    transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.form-textarea:focus {
    border-color: var(--accent);
    box-shadow: 0 0 0 2px rgba(232, 168, 56, 0.15);
}

.form-textarea::placeholder {
    color: var(--text-muted);
    opacity: 0.6;
}

.form-checkbox {
    display: flex;
    align-items: center;
    gap: 6px;
    cursor: pointer;
    font-size: 13px;
    color: var(--text-primary);
}

.form-checkbox input[type="checkbox"] {
    width: 16px;
    height: 16px;
    accent-color: var(--accent);
    cursor: pointer;
}

.form-radio-group {
    display: flex;
    gap: 12px;
}

.form-radio {
    display: flex;
    align-items: center;
    gap: 6px;
    cursor: pointer;
    font-size: 13px;
    color: var(--text-primary);
}

.form-radio input[type="radio"] {
    width: 14px;
    height: 14px;
    accent-color: var(--accent);
    cursor: pointer;
}

.form-hint {
    font-size: 11px;
    color: var(--text-muted);
    margin-top: 2px;
}
"""

# ─────────────────────────────────────────────────────────────────────────────
# CSS: Buttons
# ─────────────────────────────────────────────────────────────────────────────

_CSS_BUTTONS = """
.btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    height: 34px;
    padding: 0 14px;
    border: none;
    border-radius: var(--radius-sm);
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s ease;
    white-space: nowrap;
}

.btn:active {
    transform: scale(0.97);
}

.btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
    transform: none;
}

.btn-primary {
    background: var(--accent);
    color: var(--bg-body);
}

.btn-primary:hover:not(:disabled) {
    background: var(--accent-hover);
    box-shadow: 0 2px 8px rgba(232, 168, 56, 0.3);
}

.btn-secondary {
    background: var(--bg-elevated);
    color: var(--text-primary);
    border: 1px solid var(--border-default);
}

.btn-secondary:hover:not(:disabled) {
    background: var(--bg-hover);
    border-color: var(--text-muted);
}

.btn-success {
    background: var(--green);
    color: var(--bg-body);
}

.btn-success:hover:not(:disabled) {
    background: #4cc963;
    box-shadow: 0 2px 8px rgba(63, 185, 80, 0.3);
}

.btn-danger {
    background: var(--red);
    color: #fff;
}

.btn-danger:hover:not(:disabled) {
    background: #ff6b63;
    box-shadow: 0 2px 8px rgba(248, 81, 73, 0.3);
}

.btn-ghost {
    background: transparent;
    color: var(--text-secondary);
    border: 1px solid var(--border-muted);
}

.btn-ghost:hover:not(:disabled) {
    background: var(--bg-hover);
    color: var(--text-primary);
    border-color: var(--border-default);
}

.btn-sm {
    height: 28px;
    padding: 0 10px;
    font-size: 12px;
}

.btn-lg {
    height: 40px;
    padding: 0 20px;
    font-size: 14px;
    font-weight: 700;
}

.btn-icon {
    width: 34px;
    height: 34px;
    padding: 0;
    font-size: 15px;
}

.btn-icon-sm {
    width: 28px;
    height: 28px;
    padding: 0;
    font-size: 13px;
}

.btn-group {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
}

.btn-pipeline {
    background: var(--blue);
    color: #fff;
}

.btn-pipeline:hover:not(:disabled) {
    background: #60a5fa;
    box-shadow: 0 2px 8px rgba(59, 130, 246, 0.3);
}

.btn-pipeline.active-step {
    animation: pulse-blue 1.5s ease-in-out infinite;
}

.btn-pipeline.done-step {
    background: var(--green);
}

.btn-warn {
    background: var(--amber);
    color: var(--bg-body);
}

.btn-warn:hover:not(:disabled) {
    background: #e5a730;
}
"""

# ─────────────────────────────────────────────────────────────────────────────
# CSS: Cards
# ─────────────────────────────────────────────────────────────────────────────

_CSS_CARDS = """
.card {
    background: var(--bg-surface);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md);
    padding: 14px;
    transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.card:hover {
    border-color: var(--accent);
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.2);
}

.card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 10px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--border-muted);
}

.card-header .card-title {
    font-size: 13px;
    font-weight: 700;
    color: var(--text-primary);
    display: flex;
    align-items: center;
    gap: 6px;
}

.card-header .card-subtitle {
    font-size: 11px;
    color: var(--text-muted);
}

.card-body {
    font-size: 13px;
    color: var(--text-secondary);
    line-height: 1.5;
}

.card-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-top: 10px;
    padding-top: 8px;
    border-top: 1px solid var(--border-muted);
}

.card-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 12px;
}

.card-grid-2 {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 12px;
}

.card-grid-4 {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 12px;
}
"""

# ─────────────────────────────────────────────────────────────────────────────
# CSS: Agent cards
# ─────────────────────────────────────────────────────────────────────────────

_CSS_AGENTS = """
.agent-card {
    background: var(--bg-surface);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md);
    padding: 14px;
    transition: all 0.3s ease;
    position: relative;
    overflow: hidden;
}

.agent-card::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 3px;
    background: var(--border-muted);
    transition: background 0.3s ease;
}

.agent-card.idle {
    opacity: 0.5;
}

.agent-card.idle::before {
    background: var(--slate);
}

.agent-card.active {
    opacity: 1.0;
    border-color: var(--cyan);
    box-shadow: 0 0 16px rgba(6, 182, 212, 0.15);
}

.agent-card.active::before {
    background: var(--cyan);
    animation: pulse-bar 1.5s ease-in-out infinite;
}

.agent-card.done {
    opacity: 1.0;
    border-color: var(--green);
}

.agent-card.done::before {
    background: var(--green);
}

.agent-card.failed {
    opacity: 1.0;
    border-color: var(--red);
}

.agent-card.failed::before {
    background: var(--red);
}

.agent-card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 10px;
}

.agent-card-name {
    font-size: 14px;
    font-weight: 700;
    color: var(--text-primary);
}

.agent-card-model {
    font-size: 11px;
    color: var(--text-muted);
    font-family: var(--font-mono);
}

.agent-card-status {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 3px 10px;
    border-radius: 12px;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

.agent-card-status.status-idle {
    background: rgba(148, 163, 184, 0.15);
    color: var(--slate);
    border: 1px solid rgba(148, 163, 184, 0.3);
}

.agent-card-status.status-active {
    background: rgba(6, 182, 212, 0.15);
    color: var(--cyan);
    border: 1px solid rgba(6, 182, 212, 0.3);
    animation: badge-pulse 2s ease-in-out infinite;
}

.agent-card-status.status-done {
    background: rgba(63, 185, 80, 0.15);
    color: var(--green);
    border: 1px solid rgba(63, 185, 80, 0.3);
}

.agent-card-status.status-failed {
    background: rgba(248, 81, 73, 0.15);
    color: var(--red);
    border: 1px solid rgba(248, 81, 73, 0.3);
}

.agent-card-stats {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 6px;
    margin-bottom: 10px;
}

.agent-stat {
    display: flex;
    flex-direction: column;
    gap: 2px;
}

.agent-stat-label {
    font-size: 10px;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

.agent-stat-value {
    font-size: 13px;
    font-weight: 600;
    color: var(--text-primary);
    font-family: var(--font-mono);
}

.agent-progress {
    height: 4px;
    background: var(--bg-input);
    border-radius: 2px;
    overflow: hidden;
    margin-top: 8px;
}

.agent-progress-fill {
    height: 100%;
    background: var(--cyan);
    border-radius: 2px;
    transition: width 0.5s ease;
    width: 0%;
}

.agent-card.done .agent-progress-fill {
    background: var(--green);
}

.agent-card.failed .agent-progress-fill {
    background: var(--red);
}
"""

# ─────────────────────────────────────────────────────────────────────────────
# CSS: Notifications
# ─────────────────────────────────────────────────────────────────────────────

_CSS_NOTIFICATIONS = """
.notif-summary {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
    gap: 10px;
    margin-bottom: 14px;
}

.notif-stat {
    background: var(--bg-surface);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-sm);
    padding: 10px 12px;
    text-align: center;
    transition: border-color 0.2s ease, box-shadow 0.2s ease;
    cursor: pointer;
}

.notif-stat:hover {
    border-color: var(--accent);
    box-shadow: 0 2px 8px rgba(232, 168, 56, 0.15);
}

.notif-stat.stat-active {
    border-color: var(--accent);
    box-shadow: 0 0 8px rgba(232, 168, 56, 0.25);
}

.notif-stat-value {
    font-size: 22px;
    font-weight: 700;
    font-family: var(--font-mono);
}

.notif-stat-label {
    font-size: 11px;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-top: 2px;
}

.notif-stat.stat-total .notif-stat-value { color: var(--accent); }
.notif-stat.stat-health .notif-stat-value { color: var(--green); }
.notif-stat.stat-arena .notif-stat-value { color: var(--purple); }
.notif-stat.stat-pool .notif-stat-value { color: var(--blue); }
.notif-stat.stat-system .notif-stat-value { color: var(--teal); }

.notif-toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 10px;
}

.notif-toolbar-left {
    display: flex;
    align-items: center;
    gap: 8px;
}

.notif-filter {
    width: 160px;
    height: 32px;
    padding: 0 10px;
    background: var(--bg-input);
    color: var(--text-primary);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-sm);
    font-size: 12px;
    cursor: pointer;
    appearance: none;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath d='M2 4l4 4 4-4' fill='none' stroke='%23baae87' stroke-width='1.5'/%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: right 8px center;
    padding-right: 26px;
}

.notif-list {
    flex: 1;
    overflow-y: auto;
    border: 1px solid var(--border-default);
    border-radius: var(--radius-sm);
    background: var(--bg-surface);
}

.notif-event {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    padding: 10px 12px;
    border-bottom: 1px solid var(--border-muted);
    transition: background 0.15s ease;
}

.notif-event:last-child {
    border-bottom: none;
}

.notif-event:hover {
    background: var(--bg-hover);
}

.notif-event-time {
    font-size: 11px;
    color: var(--text-muted);
    font-family: var(--font-mono);
    white-space: nowrap;
    min-width: 65px;
}

.notif-event-badge {
    display: inline-flex;
    align-items: center;
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.3px;
    white-space: nowrap;
    flex-shrink: 0;
}

.notif-badge-health {
    background: rgba(63, 185, 80, 0.15);
    color: var(--green);
    border: 1px solid rgba(63, 185, 80, 0.3);
}

.notif-badge-arena {
    background: rgba(188, 140, 255, 0.15);
    color: var(--purple);
    border: 1px solid rgba(188, 140, 255, 0.3);
}

.notif-badge-pool {
    background: rgba(59, 130, 246, 0.15);
    color: var(--blue);
    border: 1px solid rgba(59, 130, 246, 0.3);
}

.notif-badge-system {
    background: rgba(20, 184, 166, 0.15);
    color: var(--teal);
    border: 1px solid rgba(20, 184, 166, 0.3);
}

.notif-badge-error {
    background: rgba(248, 81, 73, 0.15);
    color: var(--red);
    border: 1px solid rgba(248, 81, 73, 0.3);
}

.notif-event-msg {
    flex: 1;
    font-size: 13px;
    color: var(--text-secondary);
    line-height: 1.4;
    min-width: 0;
    word-break: break-word;
}

.notif-event-detail {
    font-size: 11px;
    color: var(--text-muted);
    margin-top: 3px;
    font-family: var(--font-mono);
}
"""

# ─────────────────────────────────────────────────────────────────────────────
# CSS: Progress bar, tables, output
# ─────────────────────────────────────────────────────────────────────────────

_CSS_PROGRESS_TABLE = """
.progress-bar-container {
    width: 100%;
    height: 22px;
    background: var(--bg-input);
    border-radius: 11px;
    overflow: hidden;
    position: relative;
    border: 1px solid var(--border-muted);
}

.progress-bar-fill {
    height: 100%;
    background: linear-gradient(90deg, var(--accent), var(--accent-hover));
    border-radius: 11px;
    transition: width 0.5s ease;
    position: relative;
}

.progress-bar-fill::after {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: linear-gradient(
        90deg,
        transparent 0%,
        rgba(255, 255, 255, 0.1) 50%,
        transparent 100%
    );
    animation: shimmer 2s ease-in-out infinite;
}

.progress-bar-text {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    font-size: 11px;
    font-weight: 700;
    color: var(--text-primary);
    text-shadow: 0 1px 3px rgba(0, 0, 0, 0.4);
    z-index: 1;
}

.data-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
}

.data-table thead th {
    position: sticky;
    top: 0;
    background: var(--bg-elevated);
    color: var(--text-secondary);
    font-weight: 700;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    text-align: left;
    padding: 10px 12px;
    border-bottom: 2px solid var(--border-default);
}

.data-table tbody td {
    padding: 8px 12px;
    border-bottom: 1px solid var(--border-muted);
    color: var(--text-secondary);
    vertical-align: middle;
}

.data-table tbody tr {
    transition: background 0.15s ease;
}

.data-table tbody tr:hover {
    background: var(--bg-hover);
}

.data-table tbody tr:last-child td {
    border-bottom: none;
}

.output-box {
    flex: 1;
    min-height: 100px;
    padding: 10px;
    background: var(--bg-input);
    color: var(--text-primary);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-sm);
    font-family: var(--font-mono);
    font-size: 12px;
    line-height: 1.5;
    overflow-y: auto;
    white-space: pre-wrap;
    word-break: break-word;
}

.output-box:empty::before {
    content: attr(data-placeholder);
    color: var(--text-muted);
    opacity: 0.5;
    font-style: italic;
}

.output-box.error {
    border-color: var(--red);
    background: rgba(248, 81, 73, 0.05);
    color: var(--red);
}

.output-box.success {
    border-color: var(--green);
    background: rgba(63, 185, 80, 0.05);
    color: var(--green);
}

.status-badge {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 3px 10px;
    border-radius: 12px;
    font-size: 11px;
    font-weight: 600;
}

.status-badge.badge-idle {
    background: rgba(148, 163, 184, 0.15);
    color: var(--slate);
}

.status-badge.badge-running {
    background: rgba(6, 182, 212, 0.15);
    color: var(--cyan);
    animation: badge-pulse 2s ease-in-out infinite;
}

.status-badge.badge-done {
    background: rgba(63, 185, 80, 0.15);
    color: var(--green);
}

.status-badge.badge-error {
    background: rgba(248, 81, 73, 0.15);
    color: var(--red);
}

.status-badge.badge-pending {
    background: rgba(210, 153, 34, 0.15);
    color: var(--amber);
}

.mini-progress {
    width: 60px;
    height: 6px;
    background: var(--bg-input);
    border-radius: 3px;
    overflow: hidden;
    display: inline-block;
    vertical-align: middle;
}

.mini-progress-fill {
    height: 100%;
    background: var(--green);
    border-radius: 3px;
    transition: width 0.4s ease;
}

.status-line {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 10px;
    background: var(--bg-surface);
    border: 1px solid var(--border-muted);
    border-radius: var(--radius-sm);
    font-size: 12px;
}

.status-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--text-muted);
    flex-shrink: 0;
}

.status-dot.ready { background: var(--green); box-shadow: 0 0 6px rgba(63, 185, 80, 0.4); }
.status-dot.busy { background: var(--amber); animation: dot-blink 1s ease-in-out infinite; }
.status-dot.error { background: var(--red); }
"""

# ─────────────────────────────────────────────────────────────────────────────
# CSS: Animations
# ─────────────────────────────────────────────────────────────────────────────

_CSS_ANIMATIONS = """
@keyframes pulse-bar {
    0%, 100% { opacity: 0.5; }
    50% { opacity: 1.0; }
}

@keyframes pulse-blue {
    0%, 100% { box-shadow: 0 0 0 0 rgba(59, 130, 246, 0.3); }
    50% { box-shadow: 0 0 12px 2px rgba(59, 130, 246, 0.3); }
}

@keyframes badge-pulse {
    0%, 100% { opacity: 1.0; }
    50% { opacity: 0.6; }
}

@keyframes shimmer {
    0% { transform: translateX(-100%); }
    100% { transform: translateX(100%); }
}

@keyframes dot-blink {
    0%, 100% { opacity: 1.0; }
    50% { opacity: 0.3; }
}

@keyframes fade-in {
    from { opacity: 0; transform: translateY(8px); }
    to { opacity: 1; transform: translateY(0); }
}

@keyframes slide-in {
    from { opacity: 0; transform: translateX(-12px); }
    to { opacity: 1; transform: translateX(0); }
}

.fade-in {
    animation: fade-in 0.3s ease-out;
}

.slide-in {
    animation: slide-in 0.3s ease-out;
}

.events-log {
    flex: 1;
    min-height: 120px;
    max-height: 260px;
    overflow-y: auto;
    border: 1px solid var(--border-default);
    border-radius: var(--radius-sm);
    background: var(--bg-input);
    padding: 8px;
    font-family: var(--font-mono);
    font-size: 12px;
    line-height: 1.6;
    color: var(--text-secondary);
}

.events-log:empty::before {
    content: 'Sin eventos registrados...';
    color: var(--text-muted);
    opacity: 0.5;
    font-style: italic;
}

.event-line {
    padding: 2px 0;
    border-bottom: 1px solid var(--border-muted);
    animation: slide-in 0.2s ease-out;
}

.event-line:last-child {
    border-bottom: none;
}

.event-timestamp {
    color: var(--text-muted);
    margin-right: 6px;
}

.event-tag {
    display: inline-block;
    padding: 0 6px;
    border-radius: 3px;
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    margin-right: 6px;
}

.event-tag.tag-planificador { background: rgba(59, 130, 246, 0.2); color: var(--blue); }
.event-tag.tag-codificador { background: rgba(188, 140, 255, 0.2); color: var(--purple); }
.event-tag.tag-integrador { background: rgba(20, 184, 166, 0.2); color: var(--teal); }
.event-tag.tag-validador { background: rgba(232, 168, 56, 0.2); color: var(--accent); }

.empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 40px;
    color: var(--text-muted);
    text-align: center;
    gap: 12px;
}

.empty-state .empty-icon {
    font-size: 36px;
    opacity: 0.4;
}

.empty-state .empty-text {
    font-size: 14px;
    font-weight: 600;
}

.empty-state .empty-hint {
    font-size: 12px;
    opacity: 0.7;
}
"""

# ─────────────────────────────────────────────────────────────────────────────
# CSS: Extra components (manual 3-col, diff highlighting, task tree, summary)
# ─────────────────────────────────────────────────────────────────────────────

_CSS_EXTRAS = """
.planner-panel,
.coder-panel {
    display: flex;
    flex-direction: column;
    min-width: 280px;
    flex: 1;
    min-height: 0;
}

.asm-viewer {
    display: flex;
    flex-direction: column;
    min-width: 300px;
    flex: 1.2;
    min-height: 0;
    overflow: hidden;
}

.changed-line {
    background: rgba(232, 168, 56, 0.12);
    border-left: 3px solid var(--accent);
    padding-left: 6px;
    margin-left: -9px;
}

.asm-parsed-info {
    font-size: 11px;
    padding: 4px 8px;
    background: var(--bg-surface);
    border: 1px solid var(--border-muted);
    border-radius: var(--radius-sm);
    color: var(--text-muted);
    font-family: var(--font-mono);
}

.asm-parsed-info.info-ok {
    color: var(--green);
    border-color: rgba(63, 185, 80, 0.3);
}

.asm-parsed-info.info-warn {
    color: var(--amber);
    border-color: rgba(210, 153, 34, 0.3);
}

.asm-parsed-info.info-error {
    color: var(--red);
    border-color: rgba(248, 81, 73, 0.3);
}

.task-tree-container {
    flex: 1;
    overflow: auto;
    min-height: 120px;
    border: 1px solid var(--border-default);
    border-radius: var(--radius-sm);
    background: var(--bg-surface);
}

.task-tree-container table {
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
}

.task-tree-container thead th {
    position: sticky;
    top: 0;
    background: var(--bg-elevated);
    color: var(--text-secondary);
    font-weight: 700;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    text-align: left;
    padding: 8px 10px;
    border-bottom: 2px solid var(--border-default);
}

.task-tree-container tbody td {
    padding: 6px 10px;
    border-bottom: 1px solid var(--border-muted);
    color: var(--text-secondary);
    vertical-align: middle;
}

.task-tree-container tbody tr:hover {
    background: var(--bg-hover);
}

.task-tree-container tbody tr:last-child td {
    border-bottom: none;
}

.task-tree-container tbody tr.row-selected {
    background: rgba(232, 168, 56, 0.1);
    border-left: 3px solid var(--accent);
}

.semi-log {
    flex: 1;
    min-height: 80px;
    max-height: 180px;
    overflow-y: auto;
    border: 1px solid var(--border-default);
    border-radius: var(--radius-sm);
    background: var(--bg-input);
    padding: 6px 8px;
    font-family: var(--font-mono);
    font-size: 12px;
    line-height: 1.6;
    color: var(--text-secondary);
}

.semi-log:empty::before {
    content: 'Sin actividad...';
    color: var(--text-muted);
    opacity: 0.5;
    font-style: italic;
}

.semi-log .log-line {
    padding: 1px 0;
}

.semi-log .log-line.log-ok { color: var(--green); }
.semi-log .log-line.log-warn { color: var(--amber); }
.semi-log .log-line.log-err { color: var(--red); }
.semi-log .log-line.log-info { color: var(--blue); }

.summary-labels {
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
}

.summary-label {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 6px 12px;
    background: var(--bg-surface);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-sm);
    font-size: 12px;
}

.summary-label .sl-value {
    font-weight: 700;
    font-family: var(--font-mono);
    font-size: 14px;
}

.summary-label .sl-value.val-green { color: var(--green); }
.summary-label .sl-value.val-red { color: var(--red); }
.summary-label .sl-value.val-accent { color: var(--accent); }

.aud-error-input {
    width: 100%;
    min-height: 60px;
    padding: 8px 10px;
    background: rgba(248, 81, 73, 0.06);
    color: var(--red);
    border: 1px solid rgba(248, 81, 73, 0.3);
    border-radius: var(--radius-sm);
    font-family: var(--font-mono);
    font-size: 12px;
    line-height: 1.5;
    resize: vertical;
}

.aud-error-input:focus {
    border-color: var(--red);
    box-shadow: 0 0 0 2px rgba(248, 81, 73, 0.15);
}

.aud-error-input::placeholder {
    color: var(--red);
    opacity: 0.4;
}
"""


# ─────────────────────────────────────────────────────────────────────────────
# CSS: Responsive
# ─────────────────────────────────────────────────────────────────────────────

_CSS_RESPONSIVE = """
@media (max-width: 1200px) {
    .card-grid-4 {
        grid-template-columns: repeat(2, 1fr);
    }
}

@media (max-width: 900px) {
    .card-grid-4,
    .card-grid-2 {
        grid-template-columns: 1fr;
    }

    .row {
        flex-direction: column;
    }

    .notif-summary {
        grid-template-columns: repeat(3, 1fr);
    }
}

@media (max-width: 600px) {
    .tab-btn {
        padding: 0 10px;
        font-size: 12px;
    }

    .notif-summary {
        grid-template-columns: repeat(2, 1fr);
    }

    .panel-section {
        padding: 8px;
    }
}
"""


# ─────────────────────────────────────────────────────────────────────────────
# HTML: Tab bar
# ─────────────────────────────────────────────────────────────────────────────

def _html_tab_bar() -> str:
    return """
    <div class="tab-bar" id="tabBar">
        <button class="tab-btn active" data-tab="tab-manual" onclick="switchTab('tab-manual')">
            <span class="tab-icon">&#9881;</span> Manual
        </button>
        <button class="tab-btn" data-tab="tab-semiauto" onclick="switchTab('tab-semiauto')">
            <span class="tab-icon">&#9889;</span> Semiautom&aacute;tico
        </button>
        <button class="tab-btn" data-tab="tab-plan" onclick="switchTab('tab-plan')">
            <span class="tab-icon">&#128196;</span> Plan
        </button>
        <button class="tab-btn" data-tab="tab-progress" onclick="switchTab('tab-progress')">
            <span class="tab-icon">&#128200;</span> Progreso
        </button>
        <button class="tab-btn" data-tab="tab-agents" onclick="switchTab('tab-agents')">
            <span class="tab-icon">&#129302;</span> Agentes
        </button>
        <button class="tab-btn" data-tab="tab-notif" onclick="switchTab('tab-notif')">
            <span class="tab-icon">&#128276;</span> Notificaciones
            <span id="notifTabBadge" class="tab-badge" style="display:none;">0</span>
        </button>
        <button class="tab-btn" data-tab="tab-auditor" onclick="switchTab('tab-auditor')">
            <span class="tab-icon">&#128269;</span> Auditor
        </button>
        <div class="tab-spacer"></div>
        <button class="tab-btn tab-btn-close" onclick="app_close()" title="Cerrar aplicaci&oacute;n">
            &times;
        </button>
    </div>
"""


# ─────────────────────────────────────────────────────────────────────────────
# HTML: Tab 1 — Ensamblaje Manual
# ─────────────────────────────────────────────────────────────────────────────

def _html_tab_manual() -> str:
    return """
    <div class="tab-panel active" id="tab-manual">
        <!-- Project Root -->
        <div class="row align-center gap-md mb-md">
            <span class="section-header" style="margin-bottom:0">
                <span class="section-icon">&#9881;</span> Ensamblaje Manual
            </span>
            <div class="status-line">
                <span class="status-dot ready" id="manualStatusDot"></span>
                <span id="manualStatusText">Listo</span>
            </div>
        </div>
        <div class="row align-center gap-sm mb-sm">
            <label class="form-label" style="margin:0; white-space:nowrap">&#128193; Ra&iacute;z del proyecto:</label>
            <input type="text" class="form-input" id="asmProjectRoot" style="flex:1" placeholder="C:/proyectos/mi-proyecto">
            <button class="btn btn-secondary btn-sm" onclick="asm_browse_folder()" title="Examinar carpeta">
                &#128194; Examinar
            </button>
        </div>

        <!-- Options row -->
        <div class="row align-center gap-md mb-md flex-wrap">
            <div class="form-row">
                <label class="form-label" style="margin:0; white-space:nowrap">ID Tarea:</label>
                <input type="text" class="form-input" id="asmTaskId" style="width:120px" placeholder="tarea-001">
            </div>
            <div class="form-row">
                <label class="form-label" style="margin:0; white-space:nowrap">Modo ejecuci&oacute;n:</label>
                <select class="form-select" id="asmExecMode" style="width:120px">
                    <option value="local">Local</option>
                    <option value="remote">Remoto</option>
                </select>
            </div>
            <label class="form-checkbox">
                <input type="checkbox" id="asmEditMode" onchange="asm_toggle_edit()">
                Modo edici&oacute;n
            </label>
            <div class="flex-1"></div>
            <span class="asm-parsed-info" id="asmSyntaxLabel">Sintaxis: --</span>
            <span class="asm-parsed-info" id="asmParsedInfo">Info: --</span>
        </div>

        <!-- Toolbar buttons -->
        <div class="row justify-between mb-md">
            <div class="btn-group">
                <button class="btn btn-primary" onclick="asm_run()" title="Ejecutar ensamblaje">
                    &#9654; Ejecutar
                </button>
                <button class="btn btn-success" onclick="asm_save()" title="Guardar resultado">
                    &#128190; Guardar
                </button>
                <button class="btn btn-secondary" onclick="asm_copy()" title="Copiar resultado al portapapeles">
                    &#128203; Copiar
                </button>
                <button class="btn btn-ghost" onclick="asm_undo()" title="Deshacer cambios">
                    &#8630; Deshacer
                </button>
                <button class="btn btn-ghost" onclick="asm_redo()" title="Rehacer cambios">
                    &#8631; Rehacer
                </button>
                <button class="btn btn-danger btn-sm" onclick="asm_clear()" title="Limpiar todo">
                    &#128465; Limpiar
                </button>
            </div>
            <div class="btn-group">
                <button class="btn btn-success btn-sm" id="btnApprove" onclick="asm_approve()" title="APROBAR cambios">
                    &#10003; APROBAR
                </button>
                <button class="btn btn-danger btn-sm" id="btnReject" onclick="asm_reject()" title="RECHAZAR cambios">
                    &#10007; RECHAZAR
                </button>
                <button class="btn btn-warn btn-sm" onclick="asm_reset()" title="Resetear ensamblador">
                    &#128260; Resetear
                </button>
            </div>
        </div>

        <!-- Stats bar -->
        <div class="row gap-md mb-md">
            <div class="col-auto">
                <div class="card" style="padding:8px 14px">
                    <div class="row align-center gap-sm">
                        <span class="text-xs text-muted fw-bold">L&iacute;neas:</span>
                        <span class="text-sm fw-bold text-accent" id="manualLineCount">0</span>
                    </div>
                </div>
            </div>
            <div class="col-auto">
                <div class="card" style="padding:8px 14px">
                    <div class="row align-center gap-sm">
                        <span class="text-xs text-muted fw-bold">Errores:</span>
                        <span class="text-sm fw-bold text-green" id="manualSyntaxErrors">0</span>
                    </div>
                </div>
            </div>
            <div class="col-auto">
                <div class="card" style="padding:8px 14px">
                    <div class="row align-center gap-sm">
                        <span class="text-xs text-muted fw-bold">Bloques:</span>
                        <span class="text-sm fw-bold text-teal" id="manualBlockCount">0</span>
                    </div>
                </div>
            </div>
            <div class="flex-1"></div>
            <div class="col-auto">
                <span class="text-xs text-muted" id="manualTimestamp"></span>
            </div>
        </div>

        <!-- 3-column editor: Planner | Coder | Assembled View -->
        <div class="row gap-md flex-1 overflow-hidden" style="min-height:0">
            <!-- Planner Input -->
            <div class="col planner-panel">
                <div class="section-header">
                    <span class="section-icon">&#128188;</span> Entrada Planificador
                </div>
                <textarea class="form-textarea flex-1"
                    id="asmPlannerInput"
                    placeholder="Escribe la instrucci&oacute;n del planificador...&#10;&#10;Ejemplo:&#10;Analizar el archivo src/main.py&#10;y generar un plan de refactorizaci&oacute;n."
                    spellcheck="false"
                    oninput="asm_analyze()"></textarea>
            </div>

            <!-- Coder Input -->
            <div class="col coder-panel">
                <div class="section-header">
                    <span class="section-icon">&#128187;</span> Entrada Codificador
                </div>
                <textarea class="form-textarea flex-1"
                    id="asmCoderInput"
                    placeholder="Escribe tu c&oacute;digo de ensamblaje aqu&iacute;...&#10;&#10;Ejemplo:&#10;FILE: src/main.py&#10;```python&#10;def hello():&#10;    print('Hola mundo')&#10;```"
                    spellcheck="false"
                    oninput="asm_analyze()"></textarea>
            </div>

            <!-- Assembled Output -->
            <div class="col asm-viewer">
                <div class="section-header justify-between">
                    <span class="row align-center gap-sm">
                        <span class="section-icon">&#128196;</span> Vista ensamblada
                    </span>
                    <span class="text-xs text-muted" id="outputStats"></span>
                </div>
                <div class="output-box flex-1"
                    id="asmOutput"
                    data-placeholder="El resultado del ensamblaje aparecer&aacute; aqu&iacute;..."></div>
            </div>
        </div>
    </div>
"""


# ─────────────────────────────────────────────────────────────────────────────
# HTML: Tab 2 — Semiautomático
# ─────────────────────────────────────────────────────────────────────────────

def _html_tab_semiauto() -> str:
    return """
    <div class="tab-panel" id="tab-semiauto">
        <div class="row justify-between mb-md">
            <div class="section-header" style="margin-bottom:0">
                <span class="section-icon">&#9889;</span> Ensamblaje Semiautom&aacute;tico
            </div>
            <div class="row align-center gap-sm">
                <span class="status-line">
                    <span class="status-dot" id="semiStatusDot"></span>
                    <span id="semiStatusText">Esperando...</span>
                </span>
            </div>
        </div>

        <div class="row gap-md flex-1 overflow-hidden" style="min-height:0">
            <!-- Left column: controls -->
            <div class="col" style="min-width:280px; max-width:380px">
                <!-- Task table -->
                <div class="section-header">
                    <span class="section-icon">&#128203;</span> Lista de tareas
                </div>
                <div class="task-tree-container mb-md" id="semiTaskContainer" style="max-height:220px">
                    <table>
                        <thead>
                            <tr>
                                <th style="width:55px">ID</th>
                                <th>Script</th>
                                <th style="width:65px">Modo</th>
                                <th style="width:75px">Estado</th>
                                <th style="width:55px">Intento</th>
                            </tr>
                        </thead>
                        <tbody id="semiTaskBody">
                            <tr>
                                <td colspan="5" class="text-center text-muted text-xs" style="padding:20px">
                                    Sin tareas cargadas
                                </td>
                            </tr>
                        </tbody>
                    </table>
                </div>

                <!-- Action buttons -->
                <div class="btn-group mb-md">
                    <button class="btn btn-primary" id="semiBtnExecNext" onclick="semi_exec_next()" disabled>
                        &#9654; Ejecutar siguiente
                    </button>
                    <button class="btn btn-ghost" id="semiBtnSkip" onclick="semi_skip()" disabled>
                        &#9193; Saltar
                    </button>
                    <button class="btn btn-secondary" id="semiBtnSendAsm" onclick="semi_send_to_asm()" disabled>
                        &#9881; Enviar a ensamblador
                    </button>
                </div>

                <!-- Approve / Reject / Cancel -->
                <div class="btn-group mb-md">
                    <button class="btn btn-success btn-sm" id="semiBtnApprove" onclick="semi_approve()" disabled>
                        &#10003; Aprobar
                    </button>
                    <button class="btn btn-danger btn-sm" id="semiBtnReject" onclick="semi_reject()" disabled>
                        &#10007; Rechazar
                    </button>
                    <button class="btn btn-ghost btn-sm" id="semiBtnCancel" onclick="semi_cancel()">
                        &#128473; Cancelar
                    </button>
                </div>

                <!-- Feedback textarea -->
                <div class="form-group">
                    <label class="form-label">&#128172; Instrucciones de correcci&oacute;n (rechazo)</label>
                    <textarea class="form-textarea" id="semiFeedback" rows="4"
                        placeholder="Escribe las instrucciones para corregir la tarea rechazada..."></textarea>
                </div>

                <!-- Model selectors -->
                <div class="form-group mt-sm">
                    <label class="form-label">&#129302; Modelo planificador</label>
                    <select class="form-select" id="semiModelPlanner">
                        <option value="gpt-4o-mini">gpt-4o-mini</option>
                        <option value="claude-4-haiku">claude-4-haiku</option>
                        <option value="gpt-4o">gpt-4o</option>
                        <option value="claude-4-sonnet">claude-4-sonnet</option>
                        <option value="gemini-2.0-flash">gemini-2.0-flash</option>
                    </select>
                </div>

                <div class="form-group">
                    <label class="form-label">&#128187; Modelo codificador</label>
                    <select class="form-select" id="semiModelCoder">
                        <option value="gpt-4o-mini">gpt-4o-mini</option>
                        <option value="claude-4-haiku">claude-4-haiku</option>
                        <option value="gpt-4o">gpt-4o</option>
                        <option value="claude-4-sonnet">claude-4-sonnet</option>
                        <option value="gemini-2.0-flash">gemini-2.0-flash</option>
                    </select>
                </div>

                <!-- Pipeline buttons -->
                <div class="col gap-sm mt-sm">
                    <button class="btn btn-pipeline btn-lg" id="semiBtnPlan"
                        onclick="semi_plan()">
                        &#128204; 1. Planificar
                    </button>
                    <button class="btn btn-pipeline btn-lg" id="semiBtnCode"
                        onclick="semi_code()" disabled>
                        &#128187; 2. Codificar
                    </button>
                    <button class="btn btn-pipeline btn-lg" id="semiBtnAssemble"
                        onclick="semi_assemble()" disabled>
                        &#9881; 3. Ensamblar
                    </button>
                </div>
            </div>

            <!-- Right column: log + output -->
            <div class="col flex-1 overflow-hidden" style="min-height:0">
                <div class="section-header justify-between">
                    <span class="row align-center gap-sm">
                        <span class="section-icon">&#128196;</span> Salida del pipeline
                    </span>
                    <span class="text-xs text-muted" id="semiOutputStats"></span>
                </div>
                <div class="semi-log mb-md" id="semiLog"></div>
                <div class="output-box flex-1"
                    id="semiOutput"
                    data-placeholder="La salida del pipeline semiautom&aacute;tico aparecer&aacute; aqu&iacute;...&#10;&#10;1. Haz clic en 'Planificar' para iniciar&#10;2. Revisa la lista de tareas&#10;3. Ejecuta, aprueba o rechaza"></div>
            </div>
        </div>
    </div>
"""


# ─────────────────────────────────────────────────────────────────────────────
# HTML: Tab 3 — Plan
# ─────────────────────────────────────────────────────────────────────────────

def _html_tab_plan() -> str:
    return """
    <div class="tab-panel" id="tab-plan">
        <div class="row justify-between mb-md">
            <div class="section-header" style="margin-bottom:0">
                <span class="section-icon">&#128196;</span> Plan de Mejoras
            </div>
            <div class="row align-center gap-sm">
                <span class="text-xs text-muted" id="planFileName">Sin archivo de plan</span>
                <button class="btn btn-ghost btn-sm" onclick="plan_refresh()" title="Actualizar vista del plan">
                    &#128260; Recargar
                </button>
            </div>
        </div>

        <!-- Add Task / Complete Task controls -->
        <div class="row gap-md mb-md">
            <div class="col flex-1">
                <div class="section-header">
                    <span class="section-icon">&#10133;</span> Agregar tarea
                </div>
                <div class="row gap-sm">
                    <textarea class="form-textarea" id="planNewTask" rows="2" style="flex:1"
                        placeholder="Descripci&oacute;n de la nueva tarea..."></textarea>
                    <button class="btn btn-primary btn-sm flex-auto" onclick="plan_add_task()" style="align-self:flex-end">
                        &#10133; Agregar
                    </button>
                </div>
            </div>
            <div class="col-auto" style="min-width:200px">
                <div class="section-header">
                    <span class="section-icon">&#10003;</span> Completar tarea
                </div>
                <div class="row gap-sm">
                    <input type="text" class="form-input" id="planCompleteId" placeholder="ID tarea"
                        style="width:100px">
                    <button class="btn btn-success btn-sm" onclick="plan_complete_task()">
                        &#10003; Completar
                    </button>
                </div>
            </div>
        </div>

        <div class="output-box flex-1"
            id="planContent"
            data-placeholder="Contenido del archivo PLAN_*.md aparecer&aacute; aqu&iacute;...&#10;&#10;Aseg&uacute;rate de que el proyecto tenga un archivo PLAN_*.md en su ra&iacute;z."
            style="font-size:13px; line-height:1.7;"></div>
    </div>
"""


# ─────────────────────────────────────────────────────────────────────────────
# HTML: Tab 4 — Progreso
# ─────────────────────────────────────────────────────────────────────────────

def _html_tab_progress() -> str:
    return """
    <div class="tab-panel" id="tab-progress">
        <div class="row justify-between mb-md">
            <div class="section-header" style="margin-bottom:0">
                <span class="section-icon">&#128200;</span> Progreso del Proyecto
            </div>
            <div class="row align-center gap-sm">
                <label class="form-label" style="margin:0; white-space:nowrap">ID Proyecto:</label>
                <input type="text" class="form-input" id="progressProjectId"
                    style="width:180px" placeholder="proyecto-001">
                <button class="btn btn-primary btn-sm" onclick="progress_load()">
                    &#128269; Cargar
                </button>
                <button class="btn btn-ghost btn-sm" onclick="progress_connect()" title="Conectar al proyecto">
                    &#128279; Conectar
                </button>
                <span class="status-dot" id="progressConnDot"></span>
                <span class="text-xs text-muted" id="progressConnLabel">Desconectado</span>
            </div>
        </div>

        <!-- Summary labels -->
        <div class="row align-center gap-md mb-md">
            <div class="summary-labels">
                <div class="summary-label">
                    <span class="text-xs text-muted">Completadas:</span>
                    <span class="sl-value val-green" id="progressCompleted">0</span>
                </div>
                <div class="summary-label">
                    <span class="text-xs text-muted">Fallidas:</span>
                    <span class="sl-value val-red" id="progressFailed">0</span>
                </div>
                <div class="summary-label">
                    <span class="text-xs text-muted">Total:</span>
                    <span class="sl-value val-accent" id="progressTotal">0</span>
                </div>
            </div>
            <div class="flex-1"></div>
            <label class="form-checkbox">
                <input type="checkbox" id="progressAutoRefresh" checked>
                Auto-refresh
            </label>
            <button class="btn btn-ghost btn-sm" onclick="progress_refresh()" title="Refrescar manualmente">
                &#128260; Refrescar
            </button>
        </div>

        <!-- Progress bar -->
        <div class="panel-section mb-lg">
            <div class="row justify-between align-center mb-sm">
                <span class="text-sm fw-bold text-secondary">Progreso general</span>
                <span class="text-sm fw-bold text-accent" id="progressPercent">0%</span>
            </div>
            <div class="progress-bar-container">
                <div class="progress-bar-fill" id="progressBarFill" style="width: 0%"></div>
                <span class="progress-bar-text" id="progressBarText">0 / 0 tareas</span>
            </div>
        </div>

        <!-- Task table -->
        <div class="flex-1 overflow-auto" style="min-height:0">
            <table class="data-table" id="progressTable">
                <thead>
                    <tr>
                        <th style="width:60px">ID</th>
                        <th>Tarea</th>
                        <th style="width:120px">Estado</th>
                        <th style="width:100px">Progreso</th>
                        <th style="width:80px">Inicio</th>
                        <th style="width:80px">Fin</th>
                    </tr>
                </thead>
                <tbody id="progressTableBody">
                    <tr>
                        <td colspan="6" class="text-center text-muted" style="padding:30px">
                            Carga un proyecto para ver las tareas
                        </td>
                    </tr>
                </tbody>
            </table>
        </div>
    </div>
"""


# ─────────────────────────────────────────────────────────────────────────────
# HTML: Tab 5 — Agentes
# ─────────────────────────────────────────────────────────────────────────────

def _html_tab_agents() -> str:
    return """
    <div class="tab-panel" id="tab-agents">
        <div class="row justify-between mb-md">
            <div class="section-header" style="margin-bottom:0">
                <span class="section-icon">&#129302;</span> Agentes del Pipeline
            </div>
            <div class="row align-center gap-sm">
                <span class="text-xs text-muted" id="agentsSessionInfo">Sesi&oacute;n activa</span>
            </div>
        </div>

        <!-- Agent cards -->
        <div class="card-grid-4 mb-lg" id="agentCardsContainer">
            <!-- Planificador -->
            <div class="agent-card idle" id="agentCard-planner">
                <div class="agent-card-header">
                    <div>
                        <div class="agent-card-name">&#128188; Planificador</div>
                        <div class="agent-card-model" id="agentModel-planner">gpt-4o-mini</div>
                    </div>
                    <span class="agent-card-status status-idle" id="agentStatus-planner">
                        <span class="status-dot" style="width:6px;height:6px"></span> Idle
                    </span>
                </div>
                <div class="agent-card-stats">
                    <div class="agent-stat">
                        <span class="agent-stat-label">Tokens</span>
                        <span class="agent-stat-value" id="agentTokens-planner">0</span>
                    </div>
                    <div class="agent-stat">
                        <span class="agent-stat-label">Latencia</span>
                        <span class="agent-stat-value" id="agentLatency-planner">--</span>
                    </div>
                </div>
                <div class="agent-progress">
                    <div class="agent-progress-fill" id="agentProgress-planner" style="width:0%"></div>
                </div>
            </div>

            <!-- Codificador -->
            <div class="agent-card idle" id="agentCard-coder">
                <div class="agent-card-header">
                    <div>
                        <div class="agent-card-name">&#128187; Codificador</div>
                        <div class="agent-card-model" id="agentModel-coder">claude-4-haiku</div>
                    </div>
                    <span class="agent-card-status status-idle" id="agentStatus-coder">
                        <span class="status-dot" style="width:6px;height:6px"></span> Idle
                    </span>
                </div>
                <div class="agent-card-stats">
                    <div class="agent-stat">
                        <span class="agent-stat-label">Tokens</span>
                        <span class="agent-stat-value" id="agentTokens-coder">0</span>
                    </div>
                    <div class="agent-stat">
                        <span class="agent-stat-label">Latencia</span>
                        <span class="agent-stat-value" id="agentLatency-coder">--</span>
                    </div>
                </div>
                <div class="agent-progress">
                    <div class="agent-progress-fill" id="agentProgress-coder" style="width:0%"></div>
                </div>
            </div>

            <!-- Integrador -->
            <div class="agent-card idle" id="agentCard-integrator">
                <div class="agent-card-header">
                    <div>
                        <div class="agent-card-name">&#9881; Integrador</div>
                        <div class="agent-card-model" id="agentModel-integrator">gpt-4o-mini</div>
                    </div>
                    <span class="agent-card-status status-idle" id="agentStatus-integrator">
                        <span class="status-dot" style="width:6px;height:6px"></span> Idle
                    </span>
                </div>
                <div class="agent-card-stats">
                    <div class="agent-stat">
                        <span class="agent-stat-label">Tokens</span>
                        <span class="agent-stat-value" id="agentTokens-integrator">0</span>
                    </div>
                    <div class="agent-stat">
                        <span class="agent-stat-label">Latencia</span>
                        <span class="agent-stat-value" id="agentLatency-integrator">--</span>
                    </div>
                </div>
                <div class="agent-progress">
                    <div class="agent-progress-fill" id="agentProgress-integrator" style="width:0%"></div>
                </div>
            </div>

            <!-- Validador -->
            <div class="agent-card idle" id="agentCard-validator">
                <div class="agent-card-header">
                    <div>
                        <div class="agent-card-name">&#9989; Validador</div>
                        <div class="agent-card-model" id="agentModel-validator">claude-4-haiku</div>
                    </div>
                    <span class="agent-card-status status-idle" id="agentStatus-validator">
                        <span class="status-dot" style="width:6px;height:6px"></span> Idle
                    </span>
                </div>
                <div class="agent-card-stats">
                    <div class="agent-stat">
                        <span class="agent-stat-label">Tokens</span>
                        <span class="agent-stat-value" id="agentTokens-validator">0</span>
                    </div>
                    <div class="agent-stat">
                        <span class="agent-stat-label">Latencia</span>
                        <span class="agent-stat-value" id="agentLatency-validator">--</span>
                    </div>
                </div>
                <div class="agent-progress">
                    <div class="agent-progress-fill" id="agentProgress-validator" style="width:0%"></div>
                </div>
            </div>
        </div>

        <!-- Events log -->
        <div class="section-header">
            <span class="section-icon">&#128227;</span> Registro de eventos de agentes
        </div>
        <div class="events-log" id="agentsEventsLog"></div>
    </div>
"""


# ─────────────────────────────────────────────────────────────────────────────
# HTML: Tab 6 — Notificaciones
# ─────────────────────────────────────────────────────────────────────────────

def _html_tab_notif() -> str:
    return """
    <div class="tab-panel" id="tab-notif">
        <div class="section-header mb-md">
            <span class="section-icon">&#128276;</span> Centro de Notificaciones
        </div>

        <!-- Notif counters (updated by notif_set_events / notif_render_summary) -->
        <!-- Each box is clickable to filter by that type -->
        <div class="notif-summary" id="notifSummary">
            <div class="notif-stat stat-total" onclick="notif_filter_by('all')" title="Mostrar todas">
                <div class="notif-stat-value" id="notifCountTotal">0</div>
                <div class="notif-stat-label">Notificaciones</div>
            </div>
            <div class="notif-stat stat-health" onclick="notif_filter_by('health')" title="Filtrar Health">
                <div class="notif-stat-value" id="notifCountHealth">0</div>
                <div class="notif-stat-label">Health</div>
            </div>
            <div class="notif-stat stat-arena" onclick="notif_filter_by('arena')" title="Filtrar Arena">
                <div class="notif-stat-value" id="notifCountArena">0</div>
                <div class="notif-stat-label">Arena</div>
            </div>
            <div class="notif-stat stat-pool" onclick="notif_filter_by('pool')" title="Filtrar Pool">
                <div class="notif-stat-value" id="notifCountPool">0</div>
                <div class="notif-stat-label">Pool</div>
            </div>
            <div class="notif-stat stat-system" onclick="notif_filter_by('system')" title="Filtrar System">
                <div class="notif-stat-value" id="notifCountSystem">0</div>
                <div class="notif-stat-label">System</div>
            </div>
        </div>

        <!-- Pool status (updated by notif_update_summary — system data, not notif counts) -->
        <div style="display:flex;gap:12px;align-items:center;margin-bottom:12px;padding:8px 12px;background:rgba(255,255,255,0.04);border-radius:8px;">
            <span class="text-xs text-muted">Pool:</span>
            <span class="text-xs" id="poolTotal">--</span>
            <span class="text-xs text-muted">disp:</span>
            <span class="text-xs" id="poolAvailable">--</span>
            <span class="text-xs text-muted">arena:</span>
            <span class="text-xs" id="poolArena">--</span>
            <span class="text-xs text-muted">libres:</span>
            <span class="text-xs" id="poolFree">--</span>
            <span class="text-xs text-muted" id="poolStatusText" style="margin-left:auto;">--</span>
        </div>

        <!-- Toolbar -->
        <div class="notif-toolbar">
            <div class="notif-toolbar-left">
                <select class="notif-filter" id="notifFilter" onchange="notif_filter_changed()">
                    <option value="all">Todas</option>
                    <option value="health">Health</option>
                    <option value="arena">Arena</option>
                    <option value="pool">Pool</option>
                    <option value="system">System</option>
                </select>
                <span class="text-xs text-muted" id="notifFilterCount">Mostrando: 0 eventos</span>
            </div>
            <button class="btn btn-ghost btn-sm" onclick="notif_clear()">
                &#128465; Limpiar todo
            </button>
        </div>

        <!-- Event list -->
        <div class="notif-list" id="notifEventList">
            <div class="empty-state" id="notifEmptyState">
                <div class="empty-icon">&#128276;</div>
                <div class="empty-text">Sin notificaciones</div>
                <div class="empty-hint">Los eventos del sistema aparecer&aacute;n aqu&iacute;</div>
            </div>
        </div>
    </div>
"""


# ─────────────────────────────────────────────────────────────────────────────
# HTML: Tab 7 — Auditor
# ─────────────────────────────────────────────────────────────────────────────

def _html_tab_auditor() -> str:
    return """
    <div class="tab-panel" id="tab-auditor">
        <div class="section-header mb-md">
            <span class="section-icon">&#128269;</span> Auditor de Fallos
        </div>

        <!-- Controls row -->
        <div class="row gap-md mb-md">
            <!-- Mode selector -->
            <div class="form-group" style="min-width:130px">
                <label class="form-label">Modo</label>
                <div class="form-radio-group">
                    <label class="form-radio">
                        <input type="radio" name="auditorMode" value="local" checked
                            onchange="auditor_mode_changed()">
                        Local
                    </label>
                    <label class="form-radio">
                        <input type="radio" name="auditorMode" value="remoto"
                            onchange="auditor_mode_changed()">
                        Remoto
                    </label>
                </div>
            </div>

            <!-- Task ID -->
            <div class="form-group" style="min-width:180px">
                <label class="form-label">ID Tarea</label>
                <input type="text" class="form-input" id="auditorTaskId"
                    placeholder="tarea-001">
            </div>

            <!-- Agent selector -->
            <div class="form-group" style="min-width:170px">
                <label class="form-label">Agente</label>
                <select class="form-select" id="auditorAgent">
                    <option value="planificador">Planificador</option>
                    <option value="codificador">Codificador</option>
                    <option value="integrador">Integrador</option>
                    <option value="validador">Validador</option>
                </select>
            </div>

            <!-- Attempt number -->
            <div class="form-group" style="min-width:100px">
                <label class="form-label">Intento</label>
                <input type="number" class="form-input" id="auditorAttempt"
                    value="1" min="1" max="99">
            </div>

            <!-- Run button -->
            <div class="form-group" style="justify-content:flex-end">
                <button class="btn btn-primary btn-lg" onclick="auditor_run()">
                    &#9654; Ejecutar auditor&iacute;a
                </button>
            </div>
        </div>

        <!-- Script input -->
        <div class="panel-section mb-md">
            <div class="section-header">
                <span class="section-icon">&#128221;</span> Script de auditor&iacute;a
            </div>
            <textarea class="form-textarea" id="auditorScript" rows="6"
                placeholder="Escribe el script de auditor&iacute;a aqu&iacute;...&#10;&#10;Se ejecutar&aacute; en el contexto del agente seleccionado&#10;para diagnosticar y reparar fallos."></textarea>
        </div>

        <!-- Error input textarea -->
        <div class="panel-section mb-md">
            <div class="section-header">
                <span class="section-icon">&#9888;</span> Error reportado
            </div>
            <textarea class="aud-error-input" id="auditorErrorInput"
                placeholder="Pega aqu&iacute; el mensaje de error o traceback reportado..."></textarea>
        </div>

        <!-- Results -->
        <div class="row gap-md flex-1 overflow-hidden" style="min-height:0">
            <!-- Error output -->
            <div class="col col-1 flex-1" style="min-width:300px">
                <div class="section-header">
                    <span class="section-icon">&#9888;</span> Errores
                </div>
                <div class="output-box error flex-1" id="auditorErrors"
                    data-placeholder="Los errores del script aparecer&aacute;n aqu&iacute;..."></div>
            </div>

            <!-- Result output -->
            <div class="col col-1 flex-1" style="min-width:300px">
                <div class="section-header">
                    <span class="section-icon">&#10003;</span> Resultados
                </div>
                <div class="output-box success flex-1" id="auditorResults"
                    data-placeholder="Los resultados de la auditor&iacute;a aparecer&aacute;n aqu&iacute;..."></div>
            </div>
        </div>
    </div>
"""


# ─────────────────────────────────────────────────────────────────────────────
# JavaScript: Core
# ─────────────────────────────────────────────────────────────────────────────

_JS_CORE = r"""
// ── Tab switching ────────────────────────────────────────────────────────────
function switchTab(tabId) {
    // Deactivate all
    document.querySelectorAll('.tab-btn').forEach(function(btn) {
        btn.classList.remove('active');
    });
    document.querySelectorAll('.tab-panel').forEach(function(panel) {
        panel.classList.remove('active');
    });

    // Activate target
    var tabBtn = document.querySelector('.tab-btn[data-tab="' + tabId + '"]');
    var tabPanel = document.getElementById(tabId);
    if (tabBtn) tabBtn.classList.add('active');
    if (tabPanel) tabPanel.classList.add('active');

    // Resetear badge al entrar en pestaña de notificaciones
    if (tabId === 'tab-notif') {
        _notifUnseen = 0;
        updateTabBadge();
    }

    // Resize textareas to fill available space
    window.dispatchEvent(new Event('resize'));
}

// ── pywebview API bridge ────────────────────────────────────────────────────
// All calls go through pywebview.api.asm_* for Python interop
function callApi(methodName, args) {
    args = args || [];
    try {
        if (window.pywebview && window.pywebview.api && window.pywebview.api[methodName]) {
            var fn = window.pywebview.api[methodName];
            return fn.apply(window.pywebview.api, args);
        }
    } catch (err) {
        console.error('pywebview API error [' + methodName + ']:', err);
    }
    // Graceful fallback — return null (Python side not connected)
    return null;
}

// ── Utility ──────────────────────────────────────────────────────────────────
function escapeHtml(str) {
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
}

function formatTimestamp(date) {
    if (!date) date = new Date();
    var h = String(date.getHours()).padStart(2, '0');
    var m = String(date.getMinutes()).padStart(2, '0');
    var s = String(date.getSeconds()).padStart(2, '0');
    return h + ':' + m + ':' + s;
}

function formatNumber(n) {
    if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
    if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
    return String(n);
}

// ── Notification data store ──────────────────────────────────────────────────
var _notifEvents = [];
var _notifCounts = { total: 0, health: 0, arena: 0, pool: 0, system: 0 };
"""

# ─────────────────────────────────────────────────────────────────────────────
# JavaScript: Tab 1 — Manual Assembly
# ─────────────────────────────────────────────────────────────────────────────

_JS_TAB_MANUAL = r"""
// ── Tab 1: Ensamblaje Manual ─────────────────────────────────────────────────
var _editMode = false;

function asm_analyze() {
    var plannerInput = document.getElementById('asmPlannerInput');
    var coderInput = document.getElementById('asmCoderInput');
    var plannerText = plannerInput ? plannerInput.value : '';
    var coderText = coderInput ? coderInput.value : '';
    var text = coderText || plannerText;
    var lines = text ? text.split('\n') : [];
    var lineCount = lines.length;
    var blockCount = 0;
    var syntaxErrors = 0;

    for (var i = 0; i < lines.length; i++) {
        var line = lines[i].trim();
        if (line.indexOf('FILE:') === 0 || line.indexOf('```') === 0) {
            blockCount++;
        }
        if (line.length > 0 && line.length < 3 && line.indexOf('```') === -1) {
            syntaxErrors++;
        }
    }

    var elLines = document.getElementById('manualLineCount');
    var elErrors = document.getElementById('manualSyntaxErrors');
    var elBlocks = document.getElementById('manualBlockCount');
    if (elLines) elLines.textContent = lineCount;
    if (elErrors) elErrors.textContent = syntaxErrors;
    if (elBlocks) elBlocks.textContent = blockCount;

    var ts = document.getElementById('manualTimestamp');
    if (ts) ts.textContent = 'Actualizado: ' + formatTimestamp();
}

function asm_run() {
    var plannerInput = document.getElementById('asmPlannerInput');
    var coderInput = document.getElementById('asmCoderInput');
    var plannerCode = plannerInput ? plannerInput.value : '';
    var coderCode = coderInput ? coderInput.value : '';
    var taskId = document.getElementById('asmTaskId');
    var taskIdVal = taskId ? taskId.value.trim() : '';
    var execMode = document.getElementById('asmExecMode');
    var execModeVal = execMode ? execMode.value : 'local';

    // Update status
    var dot = document.getElementById('manualStatusDot');
    var status = document.getElementById('manualStatusText');
    if (dot) { dot.className = 'status-dot busy'; }
    if (status) { status.textContent = 'Ensamblando...'; }

    var output = document.getElementById('asmOutput');
    var totalLines = (plannerCode ? plannerCode.split('\n').length : 0) +
                     (coderCode ? coderCode.split('\n').length : 0);
    if (output) {
        output.textContent = 'Ensamblando...\n\nProcesando ' + totalLines + ' l\u00edneas...';
        output.className = 'output-box flex-1';
    }

    var result = callApi('asm_run', [plannerCode, coderCode, taskIdVal, execModeVal]);
    if (result) {
        if (result && typeof result.then === 'function') {
            result.then(function(data) {
                asm_display_result(data);
            }).catch(function(err) {
                asm_display_error('Error en ensamblaje: ' + err);
            });
        } else {
            asm_display_result(result);
        }
    } else {
        setTimeout(function() {
            asm_display_result({
                output: '[Demo] Ensamblaje completado con \u00e9xito.\n\n' +
                        totalLines + ' l\u00edneas procesadas.\n' +
                        '0 errores de sintaxis detectados.',
                success: true
            });
        }, 800);
    }
}

function asm_display_result(data) {
    var output = document.getElementById('asmOutput');
    var dot = document.getElementById('manualStatusDot');
    var status = document.getElementById('manualStatusText');
    var stats = document.getElementById('outputStats');

    if (!output) return;

    if (typeof data === 'string') {
        output.textContent = data;
        output.className = 'output-box flex-1';
    } else if (data && data.output) {
        output.textContent = data.output;
        output.className = data.success !== false ? 'output-box flex-1 success' : 'output-box flex-1 error';
    } else if (data && data.error) {
        output.textContent = 'Error: ' + data.error;
        output.className = 'output-box flex-1 error';
    }

    if (dot) { dot.className = 'status-dot ready'; }
    if (status) { status.textContent = 'Completado'; }
    if (stats) {
        var lines = output.textContent.split('\n').length;
        stats.textContent = lines + ' l\u00edneas de salida';
    }
}

function asm_display_error(msg) {
    var output = document.getElementById('asmOutput');
    var dot = document.getElementById('manualStatusDot');
    var status = document.getElementById('manualStatusText');
    if (output) {
        output.textContent = 'Error: ' + msg;
        output.className = 'output-box flex-1 error';
    }
    if (dot) { dot.className = 'status-dot error'; }
    if (status) { status.textContent = 'Error'; }
}

// ── Python-pushable functions for Tab 1 ────────────────────────────────────────

function asm_set_view_content(content, changedLines, lineCount) {
    var output = document.getElementById('asmOutput');
    if (!output) return;
    if (changedLines && changedLines.length > 0) {
        var lines = (content || '').split('\n');
        var html = '';
        for (var i = 0; i < lines.length; i++) {
            var isChanged = changedLines.indexOf(i + 1) !== -1;
            html += '<div' + (isChanged ? ' class="changed-line"' : '') + '>' +
                    escapeHtml(lines[i]) + '</div>';
        }
        output.innerHTML = html;
    } else {
        output.textContent = content || '';
    }
    var stats = document.getElementById('outputStats');
    if (stats && lineCount) stats.textContent = lineCount + ' l\u00edneas de salida';
}

function asm_clear_output() {
    var output = document.getElementById('asmOutput');
    if (output) { output.textContent = ''; output.className = 'output-box flex-1'; }
}

function asm_append_output(text) {
    var output = document.getElementById('asmOutput');
    if (output) output.textContent += (output.textContent ? '\n' : '') + (text || '');
}

function setAsmStatus(text) {
    var status = document.getElementById('manualStatusText');
    var dot = document.getElementById('manualStatusDot');
    if (status) status.textContent = text || 'Listo';
    if (dot) {
        var t = (text || '').toLowerCase();
        if (t.indexOf('error') !== -1 || t.indexOf('fal') !== -1) dot.className = 'status-dot error';
        else if (t.indexOf('ensambl') !== -1 || t.indexOf('proces') !== -1) dot.className = 'status-dot busy';
        else dot.className = 'status-dot ready';
    }
}

function setAsmParsedInfo(text, color) {
    var el = document.getElementById('asmParsedInfo');
    if (!el) return;
    el.textContent = 'Info: ' + (text || '--');
    el.className = 'asm-parsed-info' +
        (color === 'ok' ? ' info-ok' : color === 'warn' ? ' info-warn' : color === 'error' ? ' info-error' : '');
}

function setProjectRoot(path) {
    var el = document.getElementById('asmProjectRoot');
    if (el) el.value = path || '';
}

function asm_browse_folder() {
    try {
        if (window.pywebview && window.pywebview.api && window.pywebview.api.asm_browse_folder) {
            window.pywebview.api.asm_browse_folder().then(function(path) {
                if (path) setProjectRoot(path);
            });
        }
    } catch (e) {
        console.warn('asm_browse_folder not available');
    }
}

function asm_save() {
    var output = document.getElementById('asmOutput');
    var text = output ? output.textContent : '';
    var result = callApi('asm_save', [text]);
    if (result && typeof result.then === 'function') {
        result.then(function() { alert('Guardado con \u00e9xito'); });
    }
}

function asm_copy() {
    var output = document.getElementById('asmOutput');
    if (!output) return;
    var text = output.textContent || '';
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(function() {
            var title = document.title;
            document.title = '\u2713 Copiado';
            setTimeout(function() { document.title = title; }, 1500);
        });
    }
}

function asm_undo() {
    callApi('asm_undo');
}

function asm_redo() {
    callApi('asm_redo');
}

function asm_clear() {
    var plannerInput = document.getElementById('asmPlannerInput');
    var coderInput = document.getElementById('asmCoderInput');
    var output = document.getElementById('asmOutput');
    if (plannerInput) plannerInput.value = '';
    if (coderInput) coderInput.value = '';
    if (output) { output.textContent = ''; output.className = 'output-box flex-1'; }
    asm_analyze();
}

function asm_toggle_edit() {
    var cb = document.getElementById('asmEditMode');
    _editMode = cb ? cb.checked : !_editMode;
    callApi('asm_toggle_edit', [_editMode]);
}

function asm_approve() {
    callApi('asm_approve');
    setAsmStatus('Aprobado');
}

function asm_reject() {
    callApi('asm_reject');
    setAsmStatus('Rechazado');
}

function asm_reset() {
    callApi('asm_reset');
    asm_clear();
    setAsmStatus('Listo');
}

// ── Python-pushable: Tab Manual bridge functions ────────────────────────────

function setAsmSyntax(text, color) {
    var el = document.getElementById('manualSyntaxErrors');
    if (el) {
        el.textContent = text || '';
        el.style.color = color || '#888';
    }
}

function asm_restore_inputs(planner_code, coder_code) {
    var p = document.getElementById('asmPlannerInput');
    var c = document.getElementById('asmCoderInput');
    if (p) p.value = planner_code || '';
    if (c) c.value = coder_code || '';
    asm_analyze();
}

function asm_clear_inputs() {
    var p = document.getElementById('asmPlannerInput');
    var c = document.getElementById('asmCoderInput');
    var out = document.getElementById('asmOutput');
    var tid = document.getElementById('asmTaskId');
    var parsed = document.getElementById('asmParsedInfo');
    var syn = document.getElementById('manualSyntaxErrors');
    var lc = document.getElementById('manualLineCount');
    var bc = document.getElementById('manualBlockCount');
    var stats = document.getElementById('outputStats');
    if (p) p.value = '';
    if (c) c.value = '';
    if (out) out.textContent = '';
    if (tid) tid.value = '';
    if (parsed) { parsed.textContent = ''; parsed.className = 'asm-parsed-info'; }
    if (syn) { syn.textContent = ''; syn.style.color = '#888'; }
    if (lc) lc.textContent = '0';
    if (bc) bc.textContent = '0';
    if (stats) stats.textContent = '';
}

function asm_toggle_edit_mode(enable) {
    var cb = document.getElementById('asmEditMode');
    if (cb) cb.checked = !!enable;
    _editMode = !!enable;
}

function asm_reset_hard() {
    var p = document.getElementById('asmPlannerInput');
    var c = document.getElementById('asmCoderInput');
    var out = document.getElementById('asmOutput');
    var tid = document.getElementById('asmTaskId');
    var parsed = document.getElementById('asmParsedInfo');
    var syn = document.getElementById('manualSyntaxErrors');
    var lc = document.getElementById('manualLineCount');
    var bc = document.getElementById('manualBlockCount');
    var stats = document.getElementById('outputStats');
    if (p) p.value = '';
    if (c) c.value = '';
    if (out) out.textContent = '';
    if (tid) tid.value = '';
    if (parsed) { parsed.textContent = ''; parsed.className = 'asm-parsed-info'; }
    if (syn) { syn.textContent = ''; syn.style.color = '#888'; }
    if (lc) lc.textContent = '0';
    if (bc) bc.textContent = '0';
    if (stats) stats.textContent = '';
    setAsmStatus('Limpio — listo para ensamblar');
    setAsmSyntax('', '#888');
    setAsmParsedInfo('', '#888');
}
"""

# ─────────────────────────────────────────────────────────────────────────────
# JavaScript: Tab 2 — Semiautomático
# ─────────────────────────────────────────────────────────────────────────────

_JS_TAB_SEMIAUTO = r"""
// ── Tab 2: Semiautomático ────────────────────────────────────────────────────
var _semiStep = 0; // 0=idle, 1=planning, 2=coding, 3=assembling
var _semiTasks = [];
var _semiSelectedTask = null;

function semi_update_buttons() {
    var btnPlan = document.getElementById('semiBtnPlan');
    var btnCode = document.getElementById('semiBtnCode');
    var btnAssemble = document.getElementById('semiBtnAssemble');
    var btnApprove = document.getElementById('semiBtnApprove');
    var btnReject = document.getElementById('semiBtnReject');
    var statusText = document.getElementById('semiStatusText');
    var dot = document.getElementById('semiStatusDot');

    if (btnPlan) {
        btnPlan.disabled = _semiStep !== 0;
        btnPlan.classList.toggle('active-step', _semiStep === 1);
        btnPlan.classList.toggle('done-step', _semiStep > 1);
    }
    if (btnCode) {
        btnCode.disabled = _semiStep !== 1;
        btnCode.classList.toggle('active-step', _semiStep === 2);
        btnCode.classList.toggle('done-step', _semiStep > 2);
    }
    if (btnAssemble) {
        btnAssemble.disabled = _semiStep !== 2;
        btnAssemble.classList.toggle('active-step', _semiStep === 3);
    }
    if (btnApprove) btnApprove.disabled = _semiStep < 3;
    if (btnReject) btnReject.disabled = _semiStep < 1;

    if (statusText) {
        var labels = ['Esperando...', 'Planificando...', 'Codificando...', 'Ensamblando...', 'Completado'];
        statusText.textContent = labels[Math.min(_semiStep, 4)];
    }
    if (dot) {
        dot.className = _semiStep > 0 && _semiStep < 4 ? 'status-dot busy' : 'status-dot ready';
    }
}

function semi_output(text) {
    var el = document.getElementById('semiOutput');
    if (el) el.textContent = text;
}

function semi_add_log(tag, message) {
    var log = document.getElementById('semiLog');
    if (!log) return;
    var line = document.createElement('div');
    var tagClass = 'log-info';
    if (tag === 'ok' || tag === 'success' || tag === 'approve') tagClass = 'log-ok';
    else if (tag === 'warn' || tag === 'warning') tagClass = 'log-warn';
    else if (tag === 'error' || tag === 'fail' || tag === 'reject') tagClass = 'log-err';
    line.className = 'log-line ' + tagClass;
    line.textContent = '[' + formatTimestamp() + '] ' + (tag ? '[' + tag.toUpperCase() + '] ' : '') + (message || '');
    log.appendChild(line);
    log.scrollTop = log.scrollHeight;
    while (log.children.length > 200) log.removeChild(log.firstChild);
}

function setSemiStatus(text, color) {
    var el = document.getElementById('semiStatusText');
    var dot = document.getElementById('semiStatusDot');
    if (el) el.textContent = text || 'Esperando...';
    if (dot) {
        var c = (color || '').toLowerCase();
        if (c === 'red' || c === 'error') dot.className = 'status-dot error';
        else if (c === 'green' || c === 'ok' || c === 'done') dot.className = 'status-dot ready';
        else dot.className = 'status-dot busy';
    }
}

// ── Python-pushable: task list management ─────────────────────────────────────

function semi_update_tasks(tasks) {
    _semiTasks = tasks || [];
    var tbody = document.getElementById('semiTaskBody');
    if (!tbody) return;

    if (_semiTasks.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted text-xs" style="padding:20px">Sin tareas cargadas</td></tr>';
        return;
    }

    var html = '';
    for (var i = 0; i < _semiTasks.length; i++) {
        var t = _semiTasks[i];
        var statusColor = 'text-muted';
        if (t.status === 'done') statusColor = 'text-green';
        else if (t.status === 'running') statusColor = 'text-amber';
        else if (t.status === 'error') statusColor = 'text-red';
        else if (t.status === 'pending') statusColor = 'text-blue';

        html += '<tr class="fade-in" style="cursor:pointer" onclick="semi_select_task(' + i + ')">' +
            '<td class="text-mono text-xs">' + escapeHtml(t.id || '') + '</td>' +
            '<td class="text-xs text-ellipsis">' + escapeHtml(t.script || t.name || '') + '</td>' +
            '<td class="text-xs">' + escapeHtml(t.mode || '') + '</td>' +
            '<td class="text-xs ' + statusColor + '">' + escapeHtml(t.status || '') + '</td>' +
            '<td class="text-xs text-center">' + (t.attempt || 1) + '</td>' +
            '</tr>';
    }
    tbody.innerHTML = html;
    semi_update_buttons();
}

function semi_select_task(index) {
    _semiSelectedTask = index;
    var rows = document.querySelectorAll('#semiTaskBody tr');
    for (var i = 0; i < rows.length; i++) {
        rows[i].classList.toggle('row-selected', i === index);
    }
    var btnExec = document.getElementById('semiBtnExecNext');
    var btnSkip = document.getElementById('semiBtnSkip');
    var btnSend = document.getElementById('semiBtnSendAsm');
    if (btnExec) btnExec.disabled = false;
    if (btnSkip) btnSkip.disabled = false;
    if (btnSend) btnSend.disabled = false;
}

// ── Python-pushable: button state management ──────────────────────────────────

function semi_update_buttons(enableExec, enableApprove, enableReject, enableSkip) {
    var btnExec = document.getElementById('semiBtnExecNext');
    var btnApprove = document.getElementById('semiBtnApprove');
    var btnReject = document.getElementById('semiBtnReject');
    var btnSkip = document.getElementById('semiBtnSkip');
    var btnSend = document.getElementById('semiBtnSendAsm');
    if (btnExec) btnExec.disabled = !enableExec;
    if (btnApprove) btnApprove.disabled = !enableApprove;
    if (btnReject) btnReject.disabled = !enableReject;
    if (btnSkip) btnSkip.disabled = !enableSkip;
    if (btnSend) btnSend.disabled = !enableExec;
}

function semi_exec_next() {
    semi_add_log('info', 'Ejecutando siguiente tarea...');
    setSemiStatus('Ejecutando...', 'amber');
    callApi('semi_execute_next');
}

function semi_skip() {
    semi_add_log('warn', 'Saltando tarea seleccionada');
    callApi('semi_skip');
}

function semi_send_to_asm() {
    semi_add_log('info', 'Enviando al ensamblador...');
    callApi('semi_send_to_assembler');
}

function semi_plan() {
    _semiStep = 1;
    semi_update_buttons();
    var model = document.getElementById('semiModelPlanner');
    var modelVal = model ? model.value : 'gpt-4o-mini';

    semi_add_log('info', 'Iniciando planificaci\u00f3n con modelo: ' + modelVal);

    var result = callApi('semi_plan', ['', '', modelVal]);
    if (result && typeof result.then === 'function') {
        result.then(function(data) {
            if (data && data.output) semi_output(data.output);
            semi_add_log('ok', 'Planificaci\u00f3n completada');
            _semiStep = 1;
            semi_update_buttons();
        }).catch(function(err) {
            semi_output('Error en planificaci\u00f3n: ' + err);
            semi_add_log('error', 'Error: ' + err);
            _semiStep = 0;
            semi_update_buttons();
        });
    } else {
        setTimeout(function() {
            semi_output('Planificaci\u00f3n completada.\n\n[Demo] Se gener\u00f3 un plan con 3 pasos:\n' +
                        '1. Analizar estructura actual\n' +
                        '2. Generar c\u00f3digo nuevo\n' +
                        '3. Integrar cambios\n\n' +
                        'Haz clic en "Codificar" para continuar.');
            semi_add_log('ok', '[Demo] Plan completado');
            _semiStep = 1;
            semi_update_buttons();
        }, 1200);
    }
}

function semi_code() {
    _semiStep = 2;
    semi_update_buttons();
    var model = document.getElementById('semiModelCoder');
    var modelVal = model ? model.value : 'claude-4-haiku';

    var currentOutput = document.getElementById('semiOutput');
    var prev = currentOutput ? currentOutput.textContent + '\n\n---\n\n' : '';

    semi_output(prev + 'Codificando con modelo: ' + modelVal + '...\n\nGenerando c\u00f3digo...');
    semi_add_log('info', 'Codificando con: ' + modelVal);

    var result = callApi('semi_code', [modelVal]);
    if (result && typeof result.then === 'function') {
        result.then(function(data) {
            if (data && data.output) semi_output(prev + data.output);
            semi_add_log('ok', 'Codificaci\u00f3n completada');
            _semiStep = 2;
            semi_update_buttons();
        }).catch(function(err) {
            semi_output(prev + 'Error en codificaci\u00f3n: ' + err);
            semi_add_log('error', 'Error: ' + err);
            _semiStep = 1;
            semi_update_buttons();
        });
    } else {
        setTimeout(function() {
            semi_output(prev + 'Codificaci\u00f3n completada.\n\n[Demo] C\u00f3digo generado exitosamente.\n\n' +
                        'Haz clic en "Ensamblar" para aplicar los cambios.');
            semi_add_log('ok', '[Demo] Codificaci\u00f3n completada');
            _semiStep = 2;
            semi_update_buttons();
        }, 1000);
    }
}

function semi_assemble() {
    _semiStep = 3;
    semi_update_buttons();

    var currentOutput = document.getElementById('semiOutput');
    var prev = currentOutput ? currentOutput.textContent + '\n\n---\n\n' : '';

    semi_output(prev + 'Ensamblando...\n\nAplicando cambios al proyecto...');
    semi_add_log('info', 'Ensamblando...');

    var result = callApi('semi_assemble');
    if (result && typeof result.then === 'function') {
        result.then(function(data) {
            if (data && data.output) semi_output(prev + data.output);
            semi_add_log('ok', 'Ensamblaje completado');
            _semiStep = 4;
            semi_update_buttons();
        }).catch(function(err) {
            semi_output(prev + 'Error en ensamblaje: ' + err);
            semi_add_log('error', 'Error: ' + err);
            _semiStep = 2;
            semi_update_buttons();
        });
    } else {
        setTimeout(function() {
            semi_output(prev + 'Ensamblaje completado con \u00e9xito.\n\n' +
                        '[Demo] 3 archivos modificados.\n' +
                        'Revisa los cambios y haz clic en "Aprobar" o "Rechazar".');
            semi_add_log('ok', '[Demo] Ensamblaje completado');
            _semiStep = 4;
            semi_update_buttons();
        }, 900);
    }
}

function semi_approve() {
    callApi('semi_approve');
    semi_add_log('ok', 'Cambios APROBADOS y aplicados');
    setSemiStatus('Completado', 'green');
    _semiStep = 0;
    semi_update_buttons();
}

function semi_reject() {
    var feedback = document.getElementById('semiFeedback');
    var feedbackVal = feedback ? feedback.value.trim() : '';
    callApi('semi_reject', [feedbackVal]);
    semi_add_log('error', 'Cambios RECHAZADOS.' + (feedbackVal ? ' Feedback: ' + feedbackVal : ''));
    _semiStep = 0;
    semi_update_buttons();
}

function semi_cancel() {
    callApi('semi_cancel');
    semi_add_log('warn', 'Operaci\u00f3n cancelada');
    setSemiStatus('Cancelado', 'red');
    _semiStep = 0;
    semi_update_buttons();
    semi_output('Operaci\u00f3n cancelada.');
}

// ── Python-pushable: Tab Semiauto bridge functions ──────────────────────────

function semi_update_state(data) {
    if (!data) return;
    // Update status
    if (data.status_text !== undefined) {
        var el = document.getElementById('semiStatusText');
        if (el) el.textContent = data.status_text || '';
    }
    if (data.status_color !== undefined) {
        var dot = document.getElementById('semiStatusDot');
        if (dot) {
            var c = (data.status_color || '').toLowerCase();
            if (c === 'red' || c === 'error' || c === '#f87171') dot.className = 'status-dot error';
            else if (c === 'green' || c === 'ok' || c === 'done' || c === '#4ade80') dot.className = 'status-dot ready';
            else dot.className = 'status-dot busy';
        }
    }
    // Update task table
    if (data.plan_data && Array.isArray(data.plan_data)) {
        semi_update_tasks(data.plan_data);
    }
    // Update log
    if (data.log_lines && Array.isArray(data.log_lines)) {
        var log = document.getElementById('semiLog');
        if (log) {
            log.innerHTML = '';
            for (var i = 0; i < data.log_lines.length; i++) {
                var line = data.log_lines[i];
                var tag = line.tag || 'info';
                var msg = line.message || '';
                semi_add_log(tag, msg);
            }
        }
    }
    // Update feedback
    if (data.feedback !== undefined) {
        var fb = document.getElementById('semiFeedback');
        if (fb) fb.value = data.feedback || '';
    }
    // Update buttons based on agent state
    if (data.agent_state) {
        var s = data.agent_state;
        var hasAgent = data.has_agent;
        var enableExec = hasAgent && (s === 'planned' || s === 'awaiting_approval');
        var enableApprove = hasAgent && s === 'awaiting_approval';
        var enableReject = hasAgent && s === 'awaiting_approval';
        var enableSkip = hasAgent && (s === 'planned' || s === 'awaiting_approval');
        semi_update_buttons(enableExec, enableApprove, enableReject, enableSkip);
    }
}

function semi_update_log(log_lines) {
    if (!log_lines || !Array.isArray(log_lines)) return;
    var log = document.getElementById('semiLog');
    if (!log) return;
    log.innerHTML = '';
    for (var i = 0; i < log_lines.length; i++) {
        var line = log_lines[i];
        var tag = line.tag || 'info';
        var msg = line.message || '';
        semi_add_log(tag, msg);
    }
}
"""

# ─────────────────────────────────────────────────────────────────────────────
# JavaScript: Tab 3 — Plan
# ─────────────────────────────────────────────────────────────────────────────

_JS_TAB_PLAN = r"""
// ── Tab 3: Plan ─────────────────────────────────────────────────────────────

function plan_refresh() {
    var result = callApi('plan_refresh');
    if (result && typeof result.then === 'function') {
        result.then(function(data) {
            if (data && data.content) {
                var el = document.getElementById('planContent');
                if (el) el.textContent = data.content;
                var fn = document.getElementById('planFileName');
                if (fn && data.filename) fn.textContent = data.filename;
            }
        });
    } else {
        var el = document.getElementById('planContent');
        if (el) {
            el.textContent = '[Demo] Contenido del plan de mejoras.\n\n' +
                '# PLAN Mejoras v1.0\n\n' +
                '## Objetivo\nMejorar la arquitectura del ensamblador at\u00f3mico.\n\n' +
                '## Tareas\n' +
                '- [ ] Refactorizar el parser de instrucciones\n' +
                '- [ ] Agregar soporte para bloques anidados\n' +
                '- [x] Implementar validaci\u00f3n de sintaxis\n' +
                '- [ ] Optimizar el sistema de snapshots\n' +
                '- [ ] Integrar health probing autom\u00e1tico\n\n' +
                '## Notas\n' +
                'Este plan se genera autom\u00e1ticamente al iniciar el proyecto.\n';
        }
    }
}

function plan_add_task() {
    var input = document.getElementById('planNewTask');
    var desc = input ? input.value.trim() : '';
    if (!desc) return;
    callApi('plan_add_task', [desc]);
    input.value = '';
    // Auto-refresh after adding
    setTimeout(plan_refresh, 500);
}

function plan_complete_task() {
    var input = document.getElementById('planCompleteId');
    var taskId = input ? input.value.trim() : '';
    if (!taskId) return;
    callApi('plan_complete_task', [taskId]);
    input.value = '';
    setTimeout(plan_refresh, 500);
}

// Python-pushable
function updatePlanContent(content, filename) {
    var el = document.getElementById('planContent');
    if (el) el.textContent = content || '';
    var fn = document.getElementById('planFileName');
    if (fn && filename) fn.textContent = filename;
}
"""

# ─────────────────────────────────────────────────────────────────────────────
# JavaScript: Tab 4 — Progreso
# ─────────────────────────────────────────────────────────────────────────────

_JS_TAB_PROGRESS = r"""
// ── Tab 4: Progreso ─────────────────────────────────────────────────────────
function progress_load() {
    var projectId = document.getElementById('progressProjectId');
    var id = projectId ? projectId.value.trim() : '';

    var result = callApi('progress_load', [id]);
    if (result && typeof result.then === 'function') {
        result.then(function(data) {
            progress_render(data);
        });
    } else {
        // Demo data
        progress_render({
            total: 8,
            completed: 3,
            failed: 1,
            tasks: [
                { id: 'T-001', name: 'Refactorizar parser', status: 'done', progress: 100, start: '10:30', end: '10:45' },
                { id: 'T-002', name: 'Validar sintaxis', status: 'done', progress: 100, start: '10:46', end: '10:52' },
                { id: 'T-003', name: 'Bloques anidados', status: 'done', progress: 100, start: '10:53', end: '11:20' },
                { id: 'T-004', name: 'Optimizar snapshots', status: 'error', progress: 45, start: '11:21', end: '11:35' },
                { id: 'T-005', name: 'Health probing', status: 'pending', progress: 0, start: '', end: '' },
                { id: 'T-006', name: 'UI notificaciones', status: 'pending', progress: 0, start: '', end: '' },
                { id: 'T-007', name: 'Integrador v2', status: 'pending', progress: 0, start: '', end: '' },
                { id: 'T-008', name: 'Tests E2E', status: 'pending', progress: 0, start: '', end: '' }
            ]
        });
    }
}

function progress_render(data) {
    if (!data) return;

    var completed = data.completed || 0;
    var failed = data.failed || 0;
    var total = data.total || 0;
    var percent = total > 0 ? Math.round((completed / total) * 100) : 0;

    var elPercent = document.getElementById('progressPercent');
    var elBar = document.getElementById('progressBarFill');
    var elText = document.getElementById('progressBarText');
    if (elPercent) elPercent.textContent = percent + '%';
    if (elBar) elBar.style.width = percent + '%';
    if (elText) elText.textContent = completed + ' / ' + total + ' tareas';

    // Summary labels
    var elComp = document.getElementById('progressCompleted');
    var elFail = document.getElementById('progressFailed');
    var elTotal = document.getElementById('progressTotal');
    if (elComp) elComp.textContent = completed;
    if (elFail) elFail.textContent = failed;
    if (elTotal) elTotal.textContent = total;

    progress_update_table(data.tasks || []);
}

function progress_update_table(tasks) {
    var tbody = document.getElementById('progressTableBody');
    if (!tbody) return;

    if (!tasks || tasks.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted" style="padding:30px">Sin tareas</td></tr>';
        return;
    }

    var html = '';
    for (var i = 0; i < tasks.length; i++) {
        var t = tasks[i];
        var statusHtml = progress_status_badge(t.status);
        html += '<tr class="fade-in">' +
            '<td class="text-mono text-xs">' + escapeHtml(t.id) + '</td>' +
            '<td>' + escapeHtml(t.name) + '</td>' +
            '<td>' + statusHtml + '</td>' +
            '<td><div class="mini-progress"><div class="mini-progress-fill" style="width:' + t.progress + '%"></div></div> <span class="text-xs text-muted">' + t.progress + '%</span></td>' +
            '<td class="text-xs text-muted">' + escapeHtml(t.start || '--:--') + '</td>' +
            '<td class="text-xs text-muted">' + escapeHtml(t.end || '--:--') + '</td>' +
            '</tr>';
    }
    tbody.innerHTML = html;
}

function progress_status_badge(status) {
    var map = {
        'done':    '<span class="status-badge badge-done">&#10003; Completado</span>',
        'running': '<span class="status-badge badge-running">&#9679; En progreso</span>',
        'pending': '<span class="status-badge badge-pending">&#9203; Pendiente</span>',
        'error':   '<span class="status-badge badge-error">&#10007; Error</span>'
    };
    return map[status] || '<span class="status-badge badge-pending">' + escapeHtml(status) + '</span>';
}

// ── New progress controls ──────────────────────────────────────────────────────

function progress_connect() {
    var projectId = document.getElementById('progressProjectId');
    var id = projectId ? projectId.value.trim() : '';
    var result = callApi('progress_connect', [id]);
    if (result && typeof result.then === 'function') {
        result.then(function(data) {
            progress_set_connected(data && data.connected ? 'Conectado' : 'Desconectado',
                                  data && data.connected ? 'green' : 'red');
            if (data && data.connected) progress_load();
        });
    } else {
        progress_set_connected('Conectado', 'green');
    }
}

function progress_refresh() {
    progress_load();
}

// Python-pushable
function progress_update_summary(completed, failed, total, pct) {
    var elComp = document.getElementById('progressCompleted');
    var elFail = document.getElementById('progressFailed');
    var elTotal = document.getElementById('progressTotal');
    var elPct = document.getElementById('progressPercent');
    var elBar = document.getElementById('progressBarFill');
    var elText = document.getElementById('progressBarText');
    if (elComp) elComp.textContent = completed;
    if (elFail) elFail.textContent = failed;
    if (elTotal) elTotal.textContent = total;
    if (elPct) elPct.textContent = (pct || 0) + '%';
    if (elBar) elBar.style.width = (pct || 0) + '%';
    if (elText) elText.textContent = completed + ' / ' + total + ' tareas';
}

function progress_set_connected(text, color) {
    var dot = document.getElementById('progressConnDot');
    var label = document.getElementById('progressConnLabel');
    if (label) label.textContent = text || 'Desconectado';
    if (dot) {
        var c = (color || '').toLowerCase();
        if (c === 'green' || c === 'ok') dot.className = 'status-dot ready';
        else dot.className = 'status-dot error';
    }
}

// ── Python-pushable: Tab Progress bridge functions ─────────────────────────

function progress_update(data) {
    if (!data) return;
    if (data.summary) {
        var s = data.summary;
        progress_update_summary(s.completed || 0, s.failed || 0, s.total || 0, s.pct || 0);
    }
    if (data.tasks && Array.isArray(data.tasks)) {
        progress_update_table(data.tasks);
    }
}
"""

# ─────────────────────────────────────────────────────────────────────────────
# JavaScript: Tab 5 — Agentes
# ─────────────────────────────────────────────────────────────────────────────

_JS_TAB_AGENTS = r"""
// ── Tab 5: Agentes ──────────────────────────────────────────────────────────
var _agentIds = ['planner', 'coder', 'integrator', 'validator'];
var _agentNames = {
    planner: 'Planificador',
    coder: 'Codificador',
    integrator: 'Integrador',
    validator: 'Validador'
};

function agent_update_state(agentId, state, tokens, latency, progress, model) {
    var card = document.getElementById('agentCard-' + agentId);
    var status = document.getElementById('agentStatus-' + agentId);
    var tokensEl = document.getElementById('agentTokens-' + agentId);
    var latencyEl = document.getElementById('agentLatency-' + agentId);
    var progressEl = document.getElementById('agentProgress-' + agentId);
    var modelEl = document.getElementById('agentModel-' + agentId);

    if (!card) return;

    // Remove all state classes
    card.classList.remove('idle', 'active', 'done', 'failed');

    // Apply new state class
    if (state === 'idle') card.classList.add('idle');
    else if (state === 'active') card.classList.add('active');
    else if (state === 'done') card.classList.add('done');
    else if (state === 'failed') card.classList.add('failed');
    else card.classList.add('idle');

    // Update status badge
    if (status) {
        status.className = 'agent-card-status status-' + state;
        var label = state === 'idle' ? 'Idle' :
                    state === 'active' ? 'Activo' :
                    state === 'done' ? 'Completado' :
                    state === 'failed' ? 'Fallido' : state;
        status.innerHTML = '<span class="status-dot" style="width:6px;height:6px"></span> ' + label;
    }

    // Update stats
    if (tokensEl) tokensEl.textContent = formatNumber(tokens || 0);
    if (latencyEl) latencyEl.textContent = latency ? latency + 'ms' : '--';
    if (progressEl) progressEl.style.width = (progress || 0) + '%';
    if (modelEl && model) modelEl.textContent = model;
}

function agent_log_event(agentId, message) {
    var log = document.getElementById('agentsEventsLog');
    if (!log) return;

    var name = _agentNames[agentId] || agentId;
    var tagClass = 'tag-' + agentId;
    var line = document.createElement('div');
    line.className = 'event-line';
    line.innerHTML = '<span class="event-timestamp">' + formatTimestamp() + '</span>' +
                     '<span class="event-tag ' + tagClass + '">' + escapeHtml(name) + '</span>' +
                     '<span>' + escapeHtml(message) + '</span>';
    log.insertBefore(line, log.firstChild);

    // Limit to 100 events
    while (log.children.length > 100) {
        log.removeChild(log.lastChild);
    }
}

function agent_reset_all() {
    for (var i = 0; i < _agentIds.length; i++) {
        agent_update_state(_agentIds[i], 'idle', 0, null, 0, null);
    }
}

// Expose for Python bridge to call
function agents_update(data) {
    if (!data || !data.agents) return;
    for (var i = 0; i < data.agents.length; i++) {
        var a = data.agents[i];
        agent_update_state(a.id, a.state, a.tokens, a.latency, a.progress, a.model);
    }
    if (data.event) {
        agent_log_event(data.event.agent || 'system', data.event.message || '');
    }
}
"""

# ─────────────────────────────────────────────────────────────────────────────
# JavaScript: Tab 6 — Notificaciones
# ─────────────────────────────────────────────────────────────────────────────

_JS_TAB_NOTIF = r"""
// ── Tab 6: Notificaciones ──────────────────────────────────────────────────

function _notif_prefix(type) {
    // Extrae prefijo del tipo: 'health:model_verified' -> 'health'
    if (!type) return 'system';
    var idx = type.indexOf(':');
    return idx >= 0 ? type.substring(0, idx) : type;
}

var _notifUnseen = 0; // Contador de notificaciones no leídas (badge pestaña)

function notif_add_event(type, message, detail) {
    var event = {
        type: type,
        prefix: _notif_prefix(type),
        message: message,
        detail: detail || '',
        timestamp: formatTimestamp(),
        id: Date.now() + Math.random()
    };
    _notifEvents.unshift(event);

    // Update counts usando prefix
    var prefix = event.prefix;
    _notifCounts.total++;
    if (_notifCounts[prefix] !== undefined) {
        _notifCounts[prefix]++;
    }

    // Actualizar badge de pestaña
    _notifUnseen++;
    updateTabBadge();

    notif_render_summary();
    notif_render_list();
}

function notif_clear() {
    _notifEvents = [];
    _notifCounts = { total: 0, health: 0, arena: 0, pool: 0, system: 0 };
    _notifUnseen = 0;
    updateTabBadge();
    notif_render_summary();
    notif_render_list();
    callApi('notif_clear');
}

function notif_filter_changed() {
    notif_render_list();
}

// Filtrar por tipo al hacer click en recuadros de resumen
function notif_filter_by(type) {
    var filterEl = document.getElementById('notifFilter');
    if (filterEl) filterEl.value = type;

    // Actualizar indicador visual en recuadros
    var stats = document.querySelectorAll('.notif-stat');
    for (var i = 0; i < stats.length; i++) {
        stats[i].classList.remove('stat-active');
    }
    var classMap = { all: 'stat-total', health: 'stat-health', arena: 'stat-arena', pool: 'stat-pool', system: 'stat-system' };
    var targetClass = classMap[type] || 'stat-total';
    var target = document.querySelector('.notif-stat.' + targetClass);
    if (target) target.classList.add('stat-active');

    notif_render_list();
}

// Badge de pestaña: muestra número de notificaciones no leídas
function updateTabBadge() {
    var badge = document.getElementById('notifTabBadge');
    if (!badge) return;
    if (_notifUnseen > 0) {
        badge.textContent = _notifUnseen > 99 ? '99+' : _notifUnseen;
        badge.style.display = 'inline-flex';
    } else {
        badge.style.display = 'none';
    }
}

function notif_render_summary() {
    var map = {
        total: 'notifCountTotal',
        health: 'notifCountHealth',
        arena: 'notifCountArena',
        pool: 'notifCountPool',
        system: 'notifCountSystem'
    };
    for (var key in map) {
        var el = document.getElementById(map[key]);
        if (el) el.textContent = _notifCounts[key];
    }
}

function notif_render_list() {
    var filterEl = document.getElementById('notifFilter');
    var filter = filterEl ? filterEl.value : 'all';
    var container = document.getElementById('notifEventList');
    var emptyState = document.getElementById('notifEmptyState');
    var countLabel = document.getElementById('notifFilterCount');

    if (!container) return;

    var filtered = [];
    if (filter === 'all') {
        filtered = _notifEvents;
    } else {
        for (var i = 0; i < _notifEvents.length; i++) {
            var prefix = _notifEvents[i].prefix || _notif_prefix(_notifEvents[i].type);
            if (prefix === filter) {
                filtered.push(_notifEvents[i]);
            }
        }
    }

    if (countLabel) {
        countLabel.textContent = 'Mostrando: ' + filtered.length + ' evento' + (filtered.length !== 1 ? 's' : '');
    }

    if (filtered.length === 0) {
        container.innerHTML = '<div class="empty-state" id="notifEmptyState">' +
            '<div class="empty-icon">&#128276;</div>' +
            '<div class="empty-text">Sin notificaciones</div>' +
            '<div class="empty-hint">' + (filter === 'all' ?
                'Los eventos del sistema aparecer\u00e1n aqu\u00ed' :
                'No hay eventos de tipo "' + filter + '"') + '</div></div>';
        return;
    }

    var html = '';
    for (var i = 0; i < filtered.length; i++) {
        var ev = filtered[i];
        var badgeClass = notif_badge_class(ev.type);
        var badgeLabel = notif_badge_label(ev.type);
        html += '<div class="notif-event slide-in">' +
            '<span class="notif-event-time">' + escapeHtml(ev.timestamp) + '</span>' +
            '<span class="notif-event-badge ' + badgeClass + '">' + badgeLabel + '</span>' +
            '<div class="notif-event-msg">' + escapeHtml(ev.message) +
            (ev.detail ? '<div class="notif-event-detail">' + escapeHtml(ev.detail) + '</div>' : '') +
            '</div></div>';
    }
    container.innerHTML = html;
}

function notif_badge_class(type) {
    var prefix = _notif_prefix(type);
    var map = {
        health: 'notif-badge-health',
        arena: 'notif-badge-arena',
        pool: 'notif-badge-pool',
        system: 'notif-badge-system',
        error: 'notif-badge-error'
    };
    return map[prefix] || 'notif-badge-system';
}

function notif_badge_label(type) {
    var prefix = _notif_prefix(type);
    var map = {
        health: 'HEALTH',
        arena: 'ARENA',
        pool: 'POOL',
        system: 'SYSTEM',
        error: 'ERROR'
    };
    return map[prefix] || prefix.toUpperCase();
}

// Expose for Python bridge
function notif_update(events, counts) {
    if (counts) _notifCounts = counts;
    if (events) _notifEvents = events;
    notif_render_summary();
    notif_render_list();
}

// ── Python-pushable: Tab Notificaciones bridge functions ────────────────────

function notif_update_summary(data) {
    if (!data) return;
    // Update POOL STATUS bar (separate from notif counters)
    var mc = data.model_counts || {};
    var el;
    el = document.getElementById('poolTotal');
    if (el) el.textContent = mc.total || '--';
    el = document.getElementById('poolAvailable');
    if (el) el.textContent = mc.available || '--';
    el = document.getElementById('poolArena');
    if (el) el.textContent = mc.arena_scored || '--';
    el = document.getElementById('poolFree');
    if (el) el.textContent = mc.free || '--';
}

function notif_update_status(text) {
    var el = document.getElementById('notifStatusText');
    if (el) el.textContent = text || '';
}

function notif_set_events(events) {
    if (!Array.isArray(events)) return;
    // Calcular delta para badge (eventos nuevos no leídos)
    var newCount = events.length;
    if (newCount > _notifEvents.length) {
        _notifUnseen += (newCount - _notifEvents.length);
        updateTabBadge();
    }
    _notifEvents = events;
    // Recalculate counts usando prefix
    _notifCounts = {total: events.length, health: 0, arena: 0, pool: 0, system: 0};
    for (var i = 0; i < events.length; i++) {
        var prefix = events[i].prefix || _notif_prefix(events[i].type);
        if (_notifCounts[prefix] !== undefined) _notifCounts[prefix]++;
        else _notifCounts.system++;
    }
    notif_render_summary();
    notif_render_list();
}

function notif_update_count(count) {
    var el = document.getElementById('notifFilterCount');
    if (el) el.textContent = count + ' eventos';
}
"""

# ─────────────────────────────────────────────────────────────────────────────
# JavaScript: Tab 7 — Auditor
# ─────────────────────────────────────────────────────────────────────────────

_JS_TAB_AUDITOR = r"""
// ── Tab 7: Auditor ───────────────────────────────────────────────────────────

function auditor_mode_changed() {
    var radios = document.querySelectorAll('input[name="auditorMode"]');
    var mode = 'local';
    for (var i = 0; i < radios.length; i++) {
        if (radios[i].checked) { mode = radios[i].value; break; }
    }
    callApi('auditor_mode_changed', [mode]);
}

function auditor_run() {
    var taskId = document.getElementById('auditorTaskId');
    var script = document.getElementById('auditorScript');
    var agent = document.getElementById('auditorAgent');
    var attempt = document.getElementById('auditorAttempt');

    var taskIdVal = taskId ? taskId.value.trim() : '';
    var scriptVal = script ? script.value : '';
    var agentVal = agent ? agent.value : 'planificador';
    var attemptVal = attempt ? parseInt(attempt.value, 10) || 1 : 1;

    var mode = 'local';
    var radios = document.querySelectorAll('input[name="auditorMode"]');
    for (var i = 0; i < radios.length; i++) {
        if (radios[i].checked) { mode = radios[i].value; break; }
    }

    var errorsEl = document.getElementById('auditorErrors');
    var resultsEl = document.getElementById('auditorResults');
    if (errorsEl) {
        errorsEl.textContent = 'Ejecutando auditor\u00eda...\n\n' +
            'Modo: ' + mode + '\n' +
            'Tarea: ' + (taskIdVal || 'sin ID') + '\n' +
            'Agente: ' + agentVal + '\n' +
            'Intento: ' + attemptVal + '\n' +
            'Script: ' + (scriptVal ? scriptVal.split('\n').length + ' l\u00edneas' : 'vac\u00edo');
    }
    if (resultsEl) {
        resultsEl.textContent = 'Esperando resultados...';
    }

    var result = callApi('auditor_run', [mode, taskIdVal, scriptVal, agentVal, attemptVal]);
    if (result && typeof result.then === 'function') {
        result.then(function(data) {
            auditor_display(data);
        }).catch(function(err) {
            if (errorsEl) errorsEl.textContent = 'Error: ' + err;
        });
    } else {
        setTimeout(function() {
            if (errorsEl) {
                errorsEl.textContent = '[Demo] Auditor\u00eda completada.\n\nNo se detectaron errores cr\u00edticos.\nAdvertencias: 2\nNotas: La validaci\u00f3n de snapshots est\u00e1 pendiente.';
            }
            if (resultsEl) {
                resultsEl.textContent = '[Demo] Resultados de la auditor\u00eda:\n\n' +
                    '\u2713 Estado del agente: Activo\n' +
                    '\u2713 Pool: Conectado (48 modelos)\n' +
                    '\u2713 Arena: Datos actualizados\n' +
                    '\u26A0 RefactorGuard: Sin revisiones recientes\n\n' +
                    'Recomendaci\u00f3n: Ejecutar health probing manual.';
            }
        }, 1500);
    }
}

function auditor_display(data) {
    var errorsEl = document.getElementById('auditorErrors');
    var resultsEl = document.getElementById('auditorResults');
    if (data && data.errors && errorsEl) errorsEl.textContent = data.errors;
    if (data && data.results && resultsEl) resultsEl.textContent = data.results;
}

// ── Python-pushable: Tab Auditor bridge functions ───────────────────────────

function auditor_set_result(text) {
    var resultsEl = document.getElementById('auditorResults');
    if (resultsEl) resultsEl.textContent = text || '';
}
"""

# ─────────────────────────────────────────────────────────────────────────────
# JavaScript: Init
# ─────────────────────────────────────────────────────────────────────────────

_JS_INIT = r"""
// ── Global: Close application ─────────────────────────────────────────────────
function app_close() {
    callApi('app_close');
}

// ── Initialization ──────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function() {
    // Initialize tabs
    switchTab('tab-manual');

    // Update manual timestamp
    var ts = document.getElementById('manualTimestamp');
    if (ts) ts.textContent = 'Listo — ' + formatTimestamp();

    // Esperar a que pywebview API esté disponible (inyecta DESPUÉS de DOMContentLoaded)
    function _waitForPyWebView(maxTries) {
        var tries = 0;
        var iv = setInterval(function() {
            tries++;
            if (window.pywebview && window.pywebview.api) {
                clearInterval(iv);
                try {
                    if (window.pywebview.api.ui_ready) {
                        window.pywebview.api.ui_ready();
                        console.log('[shared_tabs] ui_ready() enviado a Python');
                    }
                } catch (e) {
                    console.error('[shared_tabs] ui_ready error:', e);
                }
            } else if (tries >= (maxTries || 100)) {
                clearInterval(iv);
                console.warn('[shared_tabs] pywebview.api no disponible tras ' + tries + ' intentos');
            }
        }, 100);
    }
    _waitForPyWebView(100);

    // Start auto-refresh timer for notifications
    setInterval(function() {
        callApi('notif_refresh_summary');
    }, 15000);

    console.log('[shared_tabs] UI inicializada correctamente');
});

// Handle window resize — resize textareas
window.addEventListener('resize', function() {
    // Force textarea reflow
    var textareas = document.querySelectorAll('.form-textarea');
    for (var i = 0; i < textareas.length; i++) {
        textareas[i].style.height = 'auto';
    }
});
"""


# ─────────────────────────────────────────────────────────────────────────────
# Helper: Build complete HTML page
# ─────────────────────────────────────────────────────────────────────────────

def _build_title(mode: str) -> str:
    """Return the page title based on mode."""
    if mode == 'app':
        return "APA Chat"
    return "APA Ensamblador"


def _build_css() -> str:
    """Concatenate all CSS sections."""
    return (
        _CSS_THEME
        + _CSS_BASE
        + _CSS_TABBAR
        + _CSS_LAYOUT
        + _CSS_FORMS
        + _CSS_BUTTONS
        + _CSS_CARDS
        + _CSS_AGENTS
        + _CSS_NOTIFICATIONS
        + _CSS_PROGRESS_TABLE
        + _CSS_ANIMATIONS
        + _CSS_EXTRAS
        + _CSS_RESPONSIVE
    )


def _build_html_body(mode: str) -> str:
    """Build the complete HTML body with header, tab bar, and panels."""
    title = _build_title(mode)
    return f"""
<div class="app-container">
    <!-- Header -->
    <div class="app-header">
        <span class="app-title">&#9881; {title}</span>
        <div class="header-right">
            <span>v4.0</span>
        </div>
    </div>

    <!-- Tab bar -->
    {_html_tab_bar()}

    <!-- Tab panels -->
    <div style="flex:1; display:flex; flex-direction:column; overflow:hidden; min-height:0;">
        {_html_tab_manual()}
        {_html_tab_semiauto()}
        {_html_tab_plan()}
        {_html_tab_progress()}
        {_html_tab_agents()}
        {_html_tab_notif()}
        {_html_tab_auditor()}
    </div>
</div>
"""


def _build_javascript() -> str:
    """Concatenate all JavaScript sections."""
    return (
        _JS_CORE
        + _JS_TAB_MANUAL
        + _JS_TAB_SEMIAUTO
        + _JS_TAB_PLAN
        + _JS_TAB_PROGRESS
        + _JS_TAB_AGENTS
        + _JS_TAB_NOTIF
        + _JS_TAB_AUDITOR
        + _JS_INIT
    )


def _build_full_html(mode: str) -> str:
    """Assemble the complete HTML document."""
    title = _build_title(mode)
    css = _build_css()
    body_html = _build_html_body(mode)
    javascript = _build_javascript()

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
{css}
    </style>
</head>
<body>
{body_html}
    <script>
{javascript}
    </script>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def build_full_page(mode: str = "ensamblador") -> str:
    """Build a complete HTML page for the APA pywebview embedded browser.

    Args:
        mode: 'ensamblador' for the assembler title, 'app' for chat title.

    Returns:
        Complete HTML document as a string.

    Raises:
        ValueError: If mode is not 'ensamblador' or 'app'.
    """
    if mode not in ("ensamblador", "app"):
        raise ValueError(
            f"Invalid mode '{mode}'. Must be 'ensamblador' or 'app'."
        )

    return _build_full_html(mode)


def get_tab_names() -> List[str]:
    """Return the ordered list of tab names."""
    return [
        "tab-manual",
        "tab-semiauto",
        "tab-plan",
        "tab-progress",
        "tab-agents",
        "tab-notif",
        "tab-auditor",
    ]


def get_tab_labels() -> Dict[str, str]:
    """Return a mapping of tab IDs to their display labels (in Spanish)."""
    return {
        "tab-manual": "Ensamblaje Manual",
        "tab-semiauto": "Semiautomático",
        "tab-plan": "Plan",
        "tab-progress": "Progreso",
        "tab-agents": "Agentes",
        "tab-notif": "Notificaciones",
        "tab-auditor": "Auditor",
    }


def get_css_theme_vars() -> Dict[str, str]:
    """Return the CSS theme variables as a Python dictionary."""
    return {
        "bg-body": "#1b2838",
        "bg-surface": "#243447",
        "bg-elevated": "#2d4059",
        "bg-input": "#1e2d3d",
        "bg-hover": "#374f6b",
        "border-default": "#4a6278",
        "border-muted": "#364d63",
        "border-accent": "#e8a838",
        "text-primary": "#f5e6c8",
        "text-secondary": "#d4c4a0",
        "text-muted": "#baae87",
        "accent": "#e8a838",
        "accent-hover": "#f0bc50",
        "green": "#3fb950",
        "red": "#f85149",
        "amber": "#d29922",
        "purple": "#bc8cff",
        "blue": "#3b82f6",
        "teal": "#14b8a6",
        "cyan": "#06b6d4",
        "slate": "#94a3b8",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Self-validation
# ─────────────────────────────────────────────────────────────────────────────

def _validate_html(html: str) -> List[str]:
    """Validate the generated HTML for common issues.

    Returns:
        List of error strings (empty if valid).
    """
    errors: List[str] = []

    # Check for placeholders
    if "__NOTIF_SECTION_HTML__" in html:
        errors.append("Found placeholder __NOTIF_SECTION_HTML__ in output")

    # Check for other common placeholders
    placeholder_patterns = [
        r"__[A-Z_]+__",
    ]
    for pattern in placeholder_patterns:
        matches = re.findall(pattern, html)
        for m in matches:
            if m == "__NOTIF_SECTION_HTML__":
                continue  # Already caught
            errors.append(f"Found placeholder {m} in output")

    # Check for required elements
    required_elements = [
        "tab-manual",
        "tab-semiauto",
        "tab-plan",
        "tab-progress",
        "tab-agents",
        "tab-notif",
        "tab-auditor",
        "switchTab",
        "asm_run",
        "semi_plan",
        "plan_refresh",
        "progress_load",
        "agentCard-planner",
        "agentCard-coder",
        "agentCard-integrator",
        "agentCard-validator",
        "notif_add_event",
        "auditor_run",
    ]
    for elem in required_elements:
        if elem not in html:
            errors.append(f"Missing required element: {elem}")

    # Check for agent-card idle visibility (must have class "idle", NOT "agent-card-hidden")
    # Agent cards must be visible by default
    if 'class="agent-card idle"' not in html:
        errors.append("Agent cards must have class 'agent-card idle' for idle visibility")

    # Check for agent-card-hidden (should NOT exist)
    if "agent-card-hidden" in html:
        errors.append("Found forbidden class 'agent-card-hidden' — agents must be visible in idle state")

    # Check CSS variables
    css_vars = [
        "--bg-body", "--bg-surface", "--accent", "--text-primary"
    ]
    for var in css_vars:
        if var not in html:
            errors.append(f"Missing CSS variable: {var}")

    # Check Spanish text presence
    spanish_markers = [
        "Ensamblaje Manual",
        "Semiautom",
        "Plan",
        "Progreso",
        "Agentes",
        "Notificaciones",
        "Auditor",
        "Ejecutar",
        "Guardar",
        "Copiar",
        "Deshacer",
        "Rehacer",
        "Limpiar",
    ]
    for marker in spanish_markers:
        if marker not in html:
            errors.append(f"Missing Spanish text: {marker}")

    return errors


def _run_self_validation() -> bool:
    """Run self-validation tests.

    Returns:
        True if all tests pass, False otherwise.
    """
    print("=" * 60)
    print("shared_tabs.py — Auto-validaci\u00f3n")
    print("=" * 60)

    all_passed = True

    # Test 1: build_full_page('ensamblador')
    print("\n[1] Generando p\u00e1gina ensamblador...")
    try:
        html = build_full_page("ensamblador")
        assert isinstance(html, str), "Output must be a string"
        assert len(html) > 5000, f"Output too short: {len(html)} chars"
        assert "APA Ensamblador" in html, "Title missing"
        print(f"    \u2713 OK — {len(html)} caracteres generados")
    except Exception as e:
        print(f"    \u2717 FALLO: {e}")
        all_passed = False

    # Test 2: build_full_page('app')
    print("\n[2] Generando p\u00e1gina app...")
    try:
        html = build_full_page("app")
        assert isinstance(html, str), "Output must be a string"
        assert "APA Chat" in html, "Title missing"
        print(f"    \u2713 OK — {len(html)} caracteres generados")
    except Exception as e:
        print(f"    \u2717 FALLO: {e}")
        all_passed = False

    # Test 3: Invalid mode
    print("\n[3] Probando modo inv\u00e1lido...")
    try:
        build_full_page("invalid_mode")
        print("    \u2717 FALLO: Should have raised ValueError")
        all_passed = False
    except ValueError:
        print("    \u2713 OK — ValueError raised correctly")
    except Exception as e:
        print(f"    \u2717 FALLO inesperado: {e}")
        all_passed = False

    # Test 4: HTML validation
    print("\n[4] Validando HTML generado...")
    try:
        html = build_full_page("ensamblador")
        errors = _validate_html(html)
        if errors:
            for err in errors:
                print(f"    \u2717 {err}")
            all_passed = False
        else:
            print("    \u2713 OK — Todas las validaciones pasaron")
    except Exception as e:
        print(f"    \u2717 FALLO: {e}")
        all_passed = False

    # Test 5: Tab names
    print("\n[5] Verificando nombres de pesta\u00f1as...")
    try:
        names = get_tab_names()
        assert len(names) == 7, f"Expected 7 tabs, got {len(names)}"
        expected = ["tab-manual", "tab-semiauto", "tab-plan", "tab-progress",
                     "tab-agents", "tab-notif", "tab-auditor"]
        assert names == expected, f"Tab order mismatch: {names}"
        print(f"    \u2713 OK — 7 pesta\u00f1as en orden correcto")
    except Exception as e:
        print(f"    \u2717 FALLO: {e}")
        all_passed = False

    # Test 6: Tab labels
    print("\n[6] Verificando etiquetas de pesta\u00f1as...")
    try:
        labels = get_tab_labels()
        assert len(labels) == 7, f"Expected 7 labels, got {len(labels)}"
        assert labels["tab-manual"] == "Ensamblaje Manual"
        print(f"    \u2713 OK — Etiquetas correctas")
    except Exception as e:
        print(f"    \u2717 FALLO: {e}")
        all_passed = False

    # Test 7: CSS theme vars
    print("\n[7] Verificando variables CSS...")
    try:
        vars = get_css_theme_vars()
        assert len(vars) >= 20, f"Expected >= 20 vars, got {len(vars)}"
        assert vars["accent"] == "#e8a838"
        print(f"    \u2713 OK — {len(vars)} variables CSS")
    except Exception as e:
        print(f"    \u2717 FALLO: {e}")
        all_passed = False

    # Test 8: Check for pywebview API bridge calls
    print("\n[8] Verificando puente pywebview API...")
    try:
        html = build_full_page("ensamblador")
        bridge_calls = [
            "pywebview.api.asm_run",
            "pywebview.api.asm_save",
            "pywebview.api.asm_undo",
            "pywebview.api.asm_redo",
            "pywebview.api.semi_plan",
            "pywebview.api.semi_code",
            "pywebview.api.semi_assemble",
            "pywebview.api.plan_refresh",
            "pywebview.api.progress_load",
            "pywebview.api.auditor_run",
        ]
        missing = []
        for call in bridge_calls:
            # We check for the method name since the callApi wrapper is used
            method = call.split('.')[-1]
            if method not in html:
                missing.append(method)
        if missing:
            print(f"    \u2717 FALLO — Bridge calls faltantes: {missing}")
            all_passed = False
        else:
            print(f"    \u2713 OK — Todas las llamadas al bridge est\u00e1n presentes")
    except Exception as e:
        print(f"    \u2717 FALLO: {e}")
        all_passed = False

    # Test 9: No external dependencies
    print("\n[9] Verificando que no hay dependencias externas...")
    try:
        # Parse the file to check imports
        import ast
        with open(__file__, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)
        external = []
        stdlib = {'__future__', 'ast', 'html', 'json', 're', 'sys', 'time', 'typing'}
        for imp in imports:
            root = imp.split('.')[0]
            if root not in stdlib:
                external.append(imp)
        if external:
            print(f"    \u2717 FALLO — Dependencias externas encontradas: {external}")
            all_passed = False
        else:
            print(f"    \u2713 OK — Solo se usan m\u00f3dulos est\u00e1ndar")
    except Exception as e:
        print(f"    \u2717 FALLO: {e}")
        all_passed = False

    # Test 10: JavaScript functions exist
    print("\n[10] Verificando funciones JavaScript...")
    try:
        html = build_full_page("ensamblador")
        js_funcs = [
            "function switchTab",
            "function callApi",
            "function escapeHtml",
            "function formatTimestamp",
            "function asm_run",
            "function asm_save",
            "function asm_copy",
            "function asm_undo",
            "function asm_redo",
            "function asm_clear",
            "function asm_toggle_edit",
            "function semi_plan",
            "function semi_code",
            "function semi_assemble",
            "function semi_approve",
            "function semi_reject",
            "function semi_cancel",
            "function plan_refresh",
            "function progress_load",
            "function agent_update_state",
            "function agent_log_event",
            "function agents_update",
            "function notif_add_event",
            "function notif_clear",
            "function notif_filter_changed",
            "function notif_update",
            "function auditor_run",
            "function auditor_mode_changed",
        ]
        missing = []
        for func in js_funcs:
            if func not in html:
                missing.append(func)
        if missing:
            print(f"    \u2717 FALLO — Funciones JS faltantes ({len(missing)}):")
            for m in missing[:5]:
                print(f"        - {m}")
            if len(missing) > 5:
                print(f"        ... y {len(missing)-5} m\u00e1s")
            all_passed = False
        else:
            print(f"    \u2713 OK — {len(js_funcs)} funciones JS encontradas")
    except Exception as e:
        print(f"    \u2717 FALLO: {e}")
        all_passed = False

    # Summary
    print("\n" + "=" * 60)
    if all_passed:
        print("\u2713 TODAS LAS PRUEBAS PASARON")
    else:
        print("\u2717 ALGUNAS PRUEBAS FALLARON")
    print("=" * 60)

    return all_passed


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    success = _run_self_validation()
    sys.exit(0 if success else 1)
