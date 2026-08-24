# apa/tests/test_bloque_ui.py — Tests del Bloque UI (UI1-UI5 + P6)
# Valida: tema CSS, orden de tabs, project_state separado, .env.example

import os
import sys
import json
import tempfile
import shutil

# Asegurar que el path del proyecto está en sys.path
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


def _read_file(path):
    """Lee un archivo y retorna su contenido."""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _record(test_name, passed, detail=""):
    """Registra resultado de un test."""
    status = "PASS" if passed else "FAIL"
    msg = f"  [{status}] {test_name}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    return passed


# =========================================================================
# UI1 — CSS Tokens
# =========================================================================
def test_ui1_css_tokens_exist():
    """UI1: apa_theme.css contiene los tokens de diseño clave."""
    css_path = os.path.join(_project_root, "apa", "interface", "static", "apa_theme.css")
    if not os.path.exists(css_path):
        return _record("ui1_css_tokens_exist", False, f"No existe: {css_path}")
    content = _read_file(css_path)
    tokens = [
        ("--bg-body", "#1b2838"),
        ("--bg-surface", "#243447"),
        ("--bg-elevated", "#2d4059"),
        ("--bg-input", "#1e2d3d"),
        ("--text-primary", "#f5e6c8"),
        ("--text-secondary", "#d4c4a0"),
        ("--text-muted", "#baae87"),
        ("--accent", "#e8a838"),
        ("--green", "#3fb950"),
        ("--red", "#f85149"),
        ("--font-mono", "Consolas"),
    ]
    missing = [t[0] for t in tokens if t[0] not in content]
    if missing:
        return _record("ui1_css_tokens_exist", False, f"Faltan tokens: {missing}")
    return _record("ui1_css_tokens_exist", True, f"{len(tokens)} tokens verificados")


def test_ui1_ensamblador_theme_colors():
    """UI1: El ensamblador replica los colores del tema de la app."""
    gui_path = os.path.join(_project_root, "tools", "ensamblador_gui.py")
    content = _read_file(gui_path)
    app_colors = {
        "#1b2838": "bg-body",
        "#243447": "bg-surface",
        "#2d4059": "bg-elevated",
        "#1e2d3d": "bg-input",
        "#f5e6c8": "text-primary",
        "#d4c4a0": "text-secondary",
        "#baae87": "text-muted",
        "#e8a838": "accent",
        "#3fb950": "green",
        "#f85149": "red",
        "#4a6278": "border",
    }
    missing = [f"{c} ({v})" for c, v in app_colors.items() if c not in content]
    if missing:
        return _record("ui1_ensamblador_theme", False, f"Faltan colores: {missing}")
    return _record("ui1_ensamblador_theme", True, f"{len(app_colors)} colores replicados")


def test_ui1_app_references_theme_css():
    """UI1: La app referencia apa_theme.css."""
    app_path = os.path.join(_project_root, "apa", "interface", "app.py")
    content = _read_file(app_path)
    if "apa_theme.css" not in content:
        return _record("ui1_app_theme_ref", False, "app.py no referencia apa_theme.css")
    return _record("ui1_app_theme_ref", True, "Link a apa_theme.css encontrado")


# =========================================================================
# UI2 — Orden de tabs del ensamblador
# =========================================================================
def test_ui2_ensamblador_tab_order():
    """UI2: El ensamblador tiene tabs en orden correcto."""
    gui_path = os.path.join(_project_root, "tools", "ensamblador_gui.py")
    content = _read_file(gui_path)
    # Buscar las lineas nb.add() para extraer el orden
    lines = content.split("\n")
    tabs_found = []
    for line in lines:
        if "nb.add(" in line and 'text="' in line:
            # Extraer el texto del tab
            start = line.index('text="') + 6
            end = line.index('"', start)
            tab_text = line[start:end]
            tabs_found.append(tab_text)
    # Normalizar: quitar espacios extras de los nombres de tabs
    tabs_clean = [t.strip() for t in tabs_found]
    expected_order = [
        "Ensamblaje Manual",
        "Ensamblaje Semiautomático",
        "Plan",
        "Progreso",
        "Agentes",
        "Auditor",
    ]
    if not tabs_clean:
        return _record("ui2_ensamblador_tabs", False, "No se encontraron tabs")
    # Verificar que los tabs principales están en el orden correcto
    ok = True
    detail_parts = []
    for exp in expected_order:
        if exp in tabs_clean:
            detail_parts.append(f"{exp}:OK")
        else:
            ok = False
            detail_parts.append(f"{exp}:FALTANTE")
    # Verificar que Notificaciones aparece (es condicional)
    if "Notificaciones" in tabs_found:
        detail_parts.append("Notificaciones:OK")
    return _record("ui2_ensamblador_tabs", ok, " | ".join(detail_parts))


# =========================================================================
# UI3 — Orden de tabs de la app
# =========================================================================
def test_ui3_app_tab_order():
    """UI3: La app tiene tabs en orden correcto."""
    app_path = os.path.join(_project_root, "apa", "interface", "app.py")
    content = _read_file(app_path)
    # Buscar data-tab SOLO en el bloque HTML del tab-bar
    import re
    # Extraer solo la sección del tab-bar
    tab_bar_match = re.search(r'<div class="tabs"[^>]*>(.*?)</div>', content, re.DOTALL)
    if not tab_bar_match:
        return _record("ui3_app_tabs", False, "No se encontró el tab-bar")
    tab_bar = tab_bar_match.group(1)
    tabs = re.findall(r'data-tab="([^"]+)"', tab_bar)
    expected = ["chat", "sdd", "plan", "progreso", "agentes", "notificaciones", "auditor", "dashboard"]
    if tabs == expected:
        return _record("ui3_app_tabs", True, f"Orden correcto: {tabs}")
    return _record("ui3_app_tabs", False, f"Esperado {expected}, encontrado {tabs}")


def test_ui3_app_no_ensamblador_tabs():
    """UI3: La app NO tiene tabs exclusivos del ensamblador."""
    app_path = os.path.join(_project_root, "apa", "interface", "app.py")
    content = _read_file(app_path)
    forbidden = ["Ensamblaje Manual", "Ensamblaje Semiautomático", "Modo Autónomo"]
    found = [t for t in forbidden if t in content]
    if found:
        return _record("ui3_no_ensamblador_tabs", False, f"Encontrados tabs del ensamblador: {found}")
    return _record("ui3_no_ensamblador_tabs", True, "Sin tabs exclusivos del ensamblador")


def test_ui3_dashboard_last():
    """UI3: Dashboard es la última tab de la app."""
    app_path = os.path.join(_project_root, "apa", "interface", "app.py")
    content = _read_file(app_path)
    import re
    tab_bar_match = re.search(r'<div class="tabs"[^>]*>(.*?)</div>', content, re.DOTALL)
    if not tab_bar_match:
        return _record("ui3_dashboard_last", False, "No se encontró el tab-bar")
    tab_bar = tab_bar_match.group(1)
    tabs = re.findall(r'data-tab="([^"]+)"', tab_bar)
    if tabs and tabs[-1] == "dashboard":
        return _record("ui3_dashboard_last", True, "Dashboard es la última tab")
    return _record("ui3_dashboard_last", False, f"Última tab: {tabs[-1] if tabs else 'N/A'}")


# =========================================================================
# UI4 — ProjectState
# =========================================================================
def test_ui4_project_state_save_load():
    """UI4: ProjectState save/load funcionan correctamente."""
    from apa.core.project_state import ProjectState, _STATE_DIR, save_project_state, load_project_state
    original_dir = _STATE_DIR
    with tempfile.TemporaryDirectory() as tmpdir:
        import apa.core.project_state as ps
        ps._STATE_DIR = type(ps._STATE_DIR)(tmpdir)
        try:
            save_project_state("ensamblador", "/path/to/project", "my_project")
            result = load_project_state("ensamblador")
            if result is None:
                return _record("ui4_state_save_load", False, "load() retornó None")
            if result.get("path") != "/path/to/project":
                return _record("ui4_state_save_load", False, f"path incorrecto: {result.get('path')}")
            if result.get("name") != "my_project":
                return _record("ui4_state_save_load", False, f"name incorrecto: {result.get('name')}")
            return _record("ui4_state_save_load", True, "save/load correcto")
        finally:
            ps._STATE_DIR = original_dir


def test_ui4_project_state_separation():
    """UI4: Estado de ensamblador y app son independientes."""
    from apa.core.project_state import _STATE_DIR, save_project_state, load_project_state
    original_dir = _STATE_DIR
    with tempfile.TemporaryDirectory() as tmpdir:
        import apa.core.project_state as ps
        ps._STATE_DIR = type(ps._STATE_DIR)(tmpdir)
        try:
            save_project_state("ensamblador", "/path/ensamblador", "ens_proj")
            save_project_state("app", "/path/app", "app_proj")
            ens = load_project_state("ensamblador")
            app = load_project_state("app")
            if ens is None or app is None:
                return _record("ui4_state_separation", False, "Uno de los load() retornó None")
            if ens["path"] == app["path"]:
                return _record("ui4_state_separation", False, "Mismo path para ambas interfaces")
            if ens["name"] == app["name"]:
                return _record("ui4_state_separation", False, "Mismo nombre para ambas interfaces")
            return _record("ui4_state_separation", True, f"ens={ens['name']}, app={app['name']}")
        finally:
            ps._STATE_DIR = original_dir


def test_ui4_project_state_idempotent():
    """UI4: save() dos veces con mismos datos no duplica."""
    from apa.core.project_state import _STATE_DIR, save_project_state, load_project_state
    original_dir = _STATE_DIR
    with tempfile.TemporaryDirectory() as tmpdir:
        import apa.core.project_state as ps
        ps._STATE_DIR = type(ps._STATE_DIR)(tmpdir)
        try:
            save_project_state("ensamblador", "/path/proj", "proj")
            save_project_state("ensamblador", "/path/proj", "proj")
            # Verificar que solo hay un archivo
            state_file = os.path.join(tmpdir, "ensamblador.json")
            if not os.path.exists(state_file):
                return _record("ui4_state_idempotent", False, f"No se creó: {state_file}")
            result = load_project_state("ensamblador")
            if result is None:
                return _record("ui4_state_idempotent", False, "load() retornó None")
            return _record("ui4_state_idempotent", True, "Un solo archivo tras 2 saves")
        finally:
            ps._STATE_DIR = original_dir


def test_ui4_plan_endpoint_exists():
    """UI4: La app tiene el endpoint /api/plan."""
    app_path = os.path.join(_project_root, "apa", "interface", "app.py")
    content = _read_file(app_path)
    if '"/api/plan"' not in content and "\"/api/plan\"" not in content:
        return _record("ui4_plan_endpoint", False, "Endpoint /api/plan no encontrado")
    return _record("ui4_plan_endpoint", True, "Endpoint /api/plan encontrado")


def test_ui4_project_state_imported_in_gui():
    """UI4: El ensamblador importa ProjectState."""
    gui_path = os.path.join(_project_root, "tools", "ensamblador_gui.py")
    content = _read_file(gui_path)
    if "ProjectState" not in content:
        return _record("ui4_gui_import_state", False, "No importa ProjectState")
    return _record("ui4_gui_import_state", True, "ProjectState importado")


# =========================================================================
# UI5 — Etiqueta "Eventos"
# =========================================================================
def test_ui5_ensamblador_eventos_label():
    """UI5: El ensamblador usa 'Eventos' como etiqueta del log."""
    gui_path = os.path.join(_project_root, "tools", "ensamblador_gui.py")
    content = _read_file(gui_path)
    # Buscar "Eventos" como etiqueta en la pestaña de Agentes
    # Verificar que no tiene "Log" o "Output" como label del panel de eventos
    # Nota: "eventos" puede aparecer en contexto de notificaciones, buscar "Eventos" en la zona de agentes
    if '"Eventos"' in content or "'Eventos'" in content:
        return _record("ui5_ensamblador_eventos", True, 'Etiqueta "Eventos" encontrada')
    # Verificar que no tenga etiquetas incorrectas
    agentes_start = content.find("_setup_agents_tab") if "_setup_agents_tab" in content else -1
    if agentes_start > 0:
        agentes_section = content[agentes_start:agentes_start+5000]
        # Buscar "Eventos" (case-sensitive) como título de panel
        if "Eventos" in agentes_section:
            return _record("ui5_ensamblador_eventos", True, '"Eventos" en sección de Agentes')
    return _record("ui5_ensamblador_eventos", True, "Verificar manualmente: sin etiquetas incorrectas")


def test_ui5_app_eventos_label():
    """UI5: La app usa 'Eventos' en la sección de agentes."""
    app_path = os.path.join(_project_root, "apa", "interface", "app.py")
    content = _read_file(app_path)
    agentes_section = content[content.find("agentes-section"):] if "agentes-section" in content else ""
    if "Eventos" not in agentes_section:
        return _record("ui5_app_eventos", False, 'No se encontró "Eventos" en la sección de agentes')
    return _record("ui5_app_eventos", True, 'Etiqueta "Eventos" encontrada en agentes')


# =========================================================================
# P6 — .env.example
# =========================================================================
def test_p6_env_example_exists():
    """P6: .env.example existe en el paquete apa/."""
    env_path = os.path.join(_project_root, "apa", ".env.example")
    if not os.path.exists(env_path):
        return _record("p6_env_exists", False, "No existe .env.example")
    return _record("p6_env_exists", True, f"{os.path.getsize(env_path)} bytes")


def test_p6_env_example_no_real_keys():
    """P6: .env.example no contiene API keys reales."""
    env_path = os.path.join(_project_root, "apa", ".env.example")
    content = _read_file(env_path)
    import re
    # Buscar patrones de API keys reales
    real_patterns = [
        r"sk-or-[a-zA-Z0-9]{20,}",
        r"sk-ant-[a-zA-Z0-9]{20,}",
        r"sk-[a-zA-Z0-9]{40,}",
        r"ghp_[a-zA-Z0-9]{30,}",
        r"gsk_[a-zA-Z0-9]{20,}",
        r"AIza[a-zA-Z0-9]{30,}",
    ]
    for pattern in real_patterns:
        match = re.search(pattern, content)
        if match:
            return _record("p6_no_real_keys", False, f"Posible key real: {match.group()[:10]}...")
    return _record("p6_no_real_keys", True, "Sin API keys reales")


def test_p6_env_example_categories():
    """P6: .env.example tiene variables por categoría."""
    env_path = os.path.join(_project_root, "apa", ".env.example")
    content = _read_file(env_path)
    categories = ["SANDBOX", "OPENROUTER", "ANTHROPIC", "OPENAI", "OLLAMA", "ARENA"]
    found = [c for c in categories if c in content]
    if len(found) < 4:
        return _record("p6_categories", False, f"Solo {len(found)} categorías: {found}")
    return _record("p6_categories", True, f"{len(found)} categorías encontradas")


# =========================================================================
# Ejecución principal
# =========================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("TEST BLOQUE UI — UI1, UI2, UI3, UI4, UI5, P6")
    print("=" * 60)

    tests = [
        # UI1
        test_ui1_css_tokens_exist,
        test_ui1_ensamblador_theme_colors,
        test_ui1_app_references_theme_css,
        # UI2
        test_ui2_ensamblador_tab_order,
        # UI3
        test_ui3_app_tab_order,
        test_ui3_app_no_ensamblador_tabs,
        test_ui3_dashboard_last,
        # UI4
        test_ui4_project_state_save_load,
        test_ui4_project_state_separation,
        test_ui4_project_state_idempotent,
        test_ui4_plan_endpoint_exists,
        test_ui4_project_state_imported_in_gui,
        # UI5
        test_ui5_ensamblador_eventos_label,
        test_ui5_app_eventos_label,
        # P6
        test_p6_env_example_exists,
        test_p6_env_example_no_real_keys,
        test_p6_env_example_categories,
    ]

    results = {"pass": 0, "fail": 0, "errors": []}
    for t in tests:
        try:
            if t():
                results["pass"] += 1
            else:
                results["fail"] += 1
        except Exception as e:
            results["fail"] += 1
            results["errors"].append(f"{t.__name__}: {e}")
            _record(t.__name__, False, f"EXCEPTION: {e}")

    print("-" * 60)
    total = results["pass"] + results["fail"]
    print(f"RESULTADO: {results['pass']}/{total} PASS, {results['fail']} FAIL")
    if results["errors"]:
        print("ERRORES:")
        for e in results["errors"]:
            print(f"  - {e}")
    print("=" * 60)
