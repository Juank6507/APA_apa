# apa/core/apa_theme.py
# TOKENS VISUALES UNIFICADOS — Fuente de verdad para todas las interfaces.
#
# La app web (app.py) es la fuente visual de verdad. Este modulo exporta
# los mismos tokens como constantes Python para que el ensamblador (tkinter)
# y cualquier otra interfaz puedan consumirlos.
#
# REGLA: Si cambias un color AQUI, actualizar tambien splash_screen.py
# para que el splash siga siendo consistente.

# ============================================================================
# COLORES — Fondo
# ============================================================================
THEME_BG_BODY = "#1b2838"       # --bg-body: fondo principal
THEME_BG_SURFACE = "#243447"    # --bg-surface: paneles/cards
THEME_BG_ELEVATED = "#2d4059"   # --bg-elevated: elementos elevados
THEME_BG_INPUT = "#1e2d3d"     # --bg-input: campos de entrada
THEME_BG_HOVER = "#374f6b"     # --bg-hover: hover sobre filas/botones

# ============================================================================
# COLORES — Bordes
# ============================================================================
THEME_BORDER_DEFAULT = "#4a6278"  # --border-default
THEME_BORDER_MUTED = "#364d63"    # --border-muted
THEME_BORDER_ACCENT = "#e8a838"   # --border-accent

# ============================================================================
# COLORES — Texto
# ============================================================================
THEME_TEXT_PRIMARY = "#f5e6c8"   # --text-primary (calido, alto contraste)
THEME_TEXT_SECONDARY = "#d4c4a0" # --text-secondary
THEME_TEXT_MUTED = "#baae87"     # --text-muted (labels, timestamps)

# ============================================================================
# COLORES — Acentos y semánticos
# ============================================================================
THEME_ACCENT = "#e8a838"         # --accent: primario (amber/gold)
THEME_ACCENT_HOVER = "#f0bc50"   # --accent-hover
THEME_GREEN = "#3fb950"          # --green: exito/OK
THEME_RED = "#f85149"            # --red: error/fallo
THEME_AMBER = "#d29922"          # --amber: advertencia
THEME_PURPLE = "#bc8cff"         # --purple: info/resuming

# ============================================================================
# COLORES — Agentes (tarjetas, usados por app y ensamblador)
# ============================================================================
THEME_AGENT_ACTIVE = "#06b6d4"   # cyan: agente trabajando
THEME_AGENT_DONE = "#22c55e"     # verde: agente completado
THEME_AGENT_FAILED = "#ef4444"   # rojo: agente fallido

# ============================================================================
# COLORES — Plan (usados por app y ensamblador)
# ============================================================================
THEME_PLAN_BG = "#0f172a"        # fondo del plan (mas oscuro)
THEME_PLAN_TEXT = "#94a3b8"      # texto normal del plan
THEME_PLAN_HEADING = "#f1f5f9"  # cabeceras de seccion
THEME_PLAN_BORDER = "#1e3a5f"   # separadores de seccion
THEME_PLAN_STRIKE = "#4b5563"   # texto tachado (completado)
THEME_PLAN_ACTIVE = "#60a5fa"   # tarea activa/resaltada

# ============================================================================
# COLORES — Paneles (notificaciones, resumen, agentes — compartidos)
# ============================================================================
THEME_PANEL_BG = "#111111"       # fondo de sub-paneles
THEME_PANEL_BORDER = "#333333"   # bordes de paneles
THEME_SCROLLBAR_BG = "#1a1a1a"   # fondo de scrollbar

# ============================================================================
# COLORES — Estado operacional (usados por notificaciones y progress)
# ============================================================================
THEME_BLUE = "#3b82f6"           # azul: info, planificacion
THEME_TEAL = "#14b8a6"           # teal: arena ranking
THEME_CYAN = "#06b6d4"           # cyan: pool con arena
THEME_SLATE = "#94a3b8"          # slate: valor secundario

# ============================================================================
# COLORES — Splash (derivados del tema, usados por splash_screen.py)
# ============================================================================
THEME_SPLASH_BG = "#0f172a"      # Mas oscuro que bg-body para impacto
THEME_SPLASH_TITLE = "#60a5fa"   # Azul brillante para el titulo
THEME_SPLASH_SUBTITLE = "#475569"
THEME_SPLASH_STATUS = "#94a3b8"
THEME_SPLASH_READY = "#22c55e"

# ============================================================================
# FUENTES
# ============================================================================
THEME_FONT_SANS = "Segoe UI"
THEME_FONT_MONO = "Consolas"

# ============================================================================
# RADIO Y SOMBRA
# ============================================================================
THEME_RADIUS_SM = 6
THEME_RADIUS_MD = 8
THEME_RADIUS_LG = 12

# ============================================================================
# CSS VARIABLES — Para inyectar en app.py (:root)
# ============================================================================
THEME_CSS_VARIABLES = f"""
    :root {{
        --bg-body: {THEME_BG_BODY};
        --bg-surface: {THEME_BG_SURFACE};
        --bg-elevated: {THEME_BG_ELEVATED};
        --bg-input: {THEME_BG_INPUT};
        --bg-hover: {THEME_BG_HOVER};
        --border-default: {THEME_BORDER_DEFAULT};
        --border-muted: {THEME_BORDER_MUTED};
        --border-accent: {THEME_BORDER_ACCENT};
        --text-primary: {THEME_TEXT_PRIMARY};
        --text-secondary: {THEME_TEXT_SECONDARY};
        --text-muted: {THEME_TEXT_MUTED};
        --accent: {THEME_ACCENT};
        --accent-hover: {THEME_ACCENT_HOVER};
        --accent-bg: rgba(232,168,56,0.15);
        --green: {THEME_GREEN};
        --green-bg: rgba(63,185,80,0.15);
        --red: {THEME_RED};
        --red-bg: rgba(248,81,73,0.15);
        --amber: {THEME_AMBER};
        --amber-bg: rgba(210,153,34,0.15);
        --purple: {THEME_PURPLE};
        --purple-bg: rgba(188,140,255,0.15);
        --agent-active: {THEME_AGENT_ACTIVE};
        --agent-done: {THEME_AGENT_DONE};
        --agent-failed: {THEME_AGENT_FAILED};
        --plan-bg: {THEME_PLAN_BG};
        --plan-text: {THEME_PLAN_TEXT};
        --plan-heading: {THEME_PLAN_HEADING};
        --plan-border: {THEME_PLAN_BORDER};
        --plan-strike: {THEME_PLAN_STRIKE};
        --plan-active: {THEME_PLAN_ACTIVE};
        --panel-bg: {THEME_PANEL_BG};
        --panel-border: {THEME_PANEL_BORDER};
        --blue: {THEME_BLUE};
        --teal: {THEME_TEAL};
        --cyan: {THEME_CYAN};
        --radius-sm: {THEME_RADIUS_SM}px;
        --radius-md: {THEME_RADIUS_MD}px;
        --radius-lg: {THEME_RADIUS_LG}px;
        --font-sans: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
        --font-mono: 'SF Mono', 'Cascadia Code', 'Fira Code', Consolas, monospace;
    }}
"""

# ============================================================================
# VALIDACION
# ============================================================================

if __name__ == "__main__":
    print("=== apa_theme.py — Validacion ===")
    # Recoger todos los tokens THEME_*
    tokens = sorted(
        [k for k in globals() if k.startswith("THEME_") and k.isupper()]
    )
    for t in tokens:
        val = globals()[t]
        print(f"  {t} = {val}")
    print(f"\nTotal: {len(tokens)} tokens")
    assert len(THEME_CSS_VARIABLES) > 300, "CSS variables deben ser completas"
    assert THEME_ACCENT in THEME_CSS_VARIABLES
    assert THEME_BG_BODY in THEME_CSS_VARIABLES
    assert THEME_AGENT_ACTIVE in THEME_CSS_VARIABLES
    assert THEME_PLAN_BG in THEME_CSS_VARIABLES
    assert THEME_PANEL_BG in THEME_CSS_VARIABLES
    print("Validacion OK")
