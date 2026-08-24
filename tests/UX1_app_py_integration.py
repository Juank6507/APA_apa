#!/usr/bin/env python3
"""
================================================================================
  UX1 — Failure Pattern Auditor :: app.py Integration Patch
================================================================================

  Proposito:
    Instrucciones y codigo listo para integrar el modulo UX1 Failure Auditor
    en la interfaz web de APA (apa/interface/app.py).

  Destinatario:
    Director de integracion / Desarrollador encargado del merge.

  Precondiciones:
    - El archivo apa/core/failure_auditor.py (v2.0+) ya existe.
    - apa/interface/app.py utiliza FastAPI y sirve HTML inline.
    - El sistema de pestañas (tabs) usa clases .tab / .tab-content.

  Estructura de este archivo:
    SECCION 1 — Instrucciones paso a paso (en espanol)
    SECCION 2 — Bloques de codigo a insertar
    SECCION 3 — Orden de integracion

================================================================================
"""


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                    SECCION 1: INSTRUCCIONES PASO A PASO                   ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

INSTRUCTIONS = """
===============================================================================
  SECCION 1 — Instrucciones de integracion en apa/interface/app.py
===============================================================================

PASO 0 — Preparacion
---------------------
a) Copia el archivo failure_auditor.py a la ubicacion correcta:
   cp download/failure_auditor.py  apa/core/failure_auditor.py
b) Verifica que el modulo se importa correctamente:
   python -c "from core.failure_auditor import FailurePatternAnalyzer; print('OK')"

PASO 1 — Agregar el import
---------------------------
a) Abre el archivo apa/interface/app.py.
b) Busca la zona de imports (cerca de la linea 20, despues de los imports
   core como 'from core.xxx import ...').
c) Inserta la siguiente linea:
       from core.failure_auditor import FailurePatternAnalyzer
d) Asegurate de que no rompa otros imports; debe quedar junto a los
   demas imports de modulos core.

PASO 2 — Agregar el endpoint /api/auditor
------------------------------------------
a) En app.py, busca la seccion donde se definen los @app.post(...) /
   @app.get(...) existentes.
b) Identifica el ultimo endpoint ANTES de que empiece el HTML response
   (la ruta raiz "/" o el bloque de HTMLResponse).
c) Inserta el endpoint completo que se proporciona en la SECCION 2.2.
d) Verifica que 'logger' esta disponible en el ambito (se usa en el
   except). Si no existe, reemplaza logger.error(...) por print(...).

PASO 3 — Agregar el boton de pestana "Auditor"
-----------------------------------------------
a) En el bloque HTML de app.py, busca los botones de pestana existentes.
   Tienen la forma: <button class="tab" onclick="switchTab('xxx')" ...>
b) Busca el boton de la pestana "Agentes" (o la ultima pestana existente).
c) Inmediatamente DESPUES de ese boton, inserta:
       <button class="tab" onclick="switchTab('auditor')" id="tab-auditor">Auditor</button>

PASO 4 — Agregar la seccion de contenido de la pestana
-------------------------------------------------------
a) En el HTML de app.py, busca el ultimo <div> con clase "tab-content".
b) Inmediatamente DESPUES del cierre de ese div (</div>), inserta todo
   el bloque HTML de la SECCION 2.4.
c) Este bloque contiene: titulo, descripcion, campo de entrada para
   project_id, boton "Analizar Fallos", y los contenedores de resultados.

PASO 5 — Agregar la funcion JavaScript
---------------------------------------
a) En app.py, busca la etiqueta <script> que contiene el JavaScript
   de la interfaz.
b) Ve al FINAL de ese bloque, justo antes de la etiqueta de cierre
   </script>.
c) Inserta la funcion JavaScript completa de la SECCION 2.5.
d) Esta funcion (runAuditor) hace fetch POST a /api/auditor, procesa
   la respuesta y renderiza metricas, patrones, archivos y sugerencias.

PASO 6 — Verificacion
----------------------
a) Reinicia el servidor APA.
b) Abre la interfaz web en el navegador.
c) Verifica que la pestana "Auditor" aparece junto a las demas.
d) Haz clic en "Analizar Fallos" sin project_id para testear el analisis
   global.
e) Introduce un project_id especifico y verifica el analisis individual.
f) Comprueba que las tarjetas de metricas, patrones, archivos y
   sugerencias se renderizan correctamente.
"""


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                    SECCION 2: BLOQUES DE CODIGO A INSERTAR                ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

# ─── 2.1: Import (insertar cerca de la linea 20, junto a otros imports core) ───

IMPORT_BLOCK = '''\
from core.failure_auditor import FailurePatternAnalyzer\
'''

# ─── 2.2: Endpoint API (insertar despues de los endpoints existentes, antes del HTML root) ───

ENDPOINT_BLOCK = '''\
@app.post("/api/auditor")
async def api_auditor(body: dict):
    """UX1: Analiza patrones de fallo recurrentes en proyectos APA."""
    try:
        project_id = body.get("project_id", "")
        analyzer = FailurePatternAnalyzer()

        if project_id:
            report = analyzer.analyze_project(project_id)
        else:
            report = analyzer.analyze_all_projects()

        return analyzer.to_dict(report)
    except Exception as e:
        logger.error(f"Error en /api/auditor: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)
\
'''

# ─── 2.3: Boton de pestana HTML (insertar despues del boton "Agentes") ───

TAB_BUTTON_BLOCK = '''\
<button class="tab" onclick="switchTab('auditor')" id="tab-auditor">Auditor</button>\
'''

# ─── 2.4: Seccion de contenido HTML (insertar despues del ultimo tab-content div) ───

TAB_CONTENT_BLOCK = '''\
<div id="tab-auditor" class="tab-content">
    <div class="section-title">Auditor de Fallos</div>
    <div class="section-desc">Analiza patrones recurrentes de fallo en los proyectos ejecutados por APA e identifica oportunidades de mejora.</div>

    <div class="field-row mb-2">
        <div class="field" style="flex:2">
            <label for="auditor-project-id">ID del Proyecto (opcional)</label>
            <input type="text" id="auditor-project-id" placeholder="Dejar vacio para analizar todos los proyectos">
        </div>
    </div>

    <button class="primary" onclick="runAuditor()" id="btn-auditor-run">
        Analizar Fallos
    </button>

    <div id="auditor-results" class="mt-6" style="display:none;">
        <div class="metrics-grid" id="auditor-metrics"></div>
        <div class="detail-section" id="auditor-patterns-section" style="display:none;">
            <h3>Patrones Detectados</h3>
            <div id="auditor-patterns-list"></div>
        </div>
        <div class="detail-section" id="auditor-files-section" style="display:none;">
            <h3>Archivos Mas Problematicos</h3>
            <div id="auditor-files-list"></div>
        </div>
        <div class="detail-section" id="auditor-suggestions-section" style="display:none;">
            <h3>Sugerencias</h3>
            <div id="auditor-suggestions-list"></div>
        </div>
    </div>
</div>\
'''

# ─── 2.5: Funcion JavaScript (insertar al final del bloque <script>, antes de </script>) ───

JAVASCRIPT_BLOCK = r'''
// === UX1: Auditor de Fallos ===
async function runAuditor() {
    const projectId = document.getElementById('auditor-project-id').value.trim();
    const btn = document.getElementById('btn-auditor-run');
    const resultsDiv = document.getElementById('auditor-results');

    btn.disabled = true;
    btn.textContent = 'Analizando...';
    resultsDiv.style.display = 'block';

    try {
        const response = await fetch('/api/auditor', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({project_id: projectId})
        });
        const data = await response.json();

        if (data.error) {
            resultsDiv.innerHTML = '<div class="alert error">' + data.error + '</div>';
            return;
        }

        // Metrics cards
        const metricsHtml = `
            <div class="metric-card">
                <div class="metric-label">Tareas Totales</div>
                <div class="metric-value">${data.total_tasks || 0}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Fallos Detectados</div>
                <div class="metric-value" style="color:var(--red)">${data.total_failures || 0}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Patrones</div>
                <div class="metric-value" style="color:var(--amber)">${(data.patterns || []).length}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Sugerencias</div>
                <div class="metric-value" style="color:var(--green)">${(data.suggestions || []).length}</div>
            </div>
        `;
        document.getElementById('auditor-metrics').innerHTML = metricsHtml;

        // Patterns
        const patterns = data.patterns || [];
        if (patterns.length > 0) {
            document.getElementById('auditor-patterns-section').style.display = 'block';
            const severityBadge = {critical: 'failed', recoverable: 'pending', minor: 'completed'};
            const severityLabel = {critical: 'Critico', recoverable: 'Recuperable', minor: 'Menor'};
            let patternsHtml = '';
            patterns.forEach(p => {
                const badgeClass = severityBadge[p.severity] || 'pending';
                const sevLabel = severityLabel[p.severity] || p.severity;
                patternsHtml += `
                    <div class="alert warning" style="margin-bottom:12px;">
                        <div style="flex:1;">
                            <strong>${p.pattern_type}</strong>
                            <span class="badge ${badgeClass}" style="margin-left:8px;">${sevLabel}</span>
                            <span style="color:var(--text-muted);font-size:0.8rem;margin-left:8px;">x${p.count}</span>
                            <div style="margin-top:6px;font-size:0.85rem;color:var(--text-secondary);">
                                ${p.suggestion || p.details || ''}
                            </div>
                            ${p.affected_files && p.affected_files.length > 0 ?
                                '<div style="margin-top:4px;font-size:0.78rem;color:var(--text-muted);">Archivos: ' + p.affected_files.join(', ') + '</div>' : ''}
                        </div>
                    </div>
                `;
            });
            document.getElementById('auditor-patterns-list').innerHTML = patternsHtml;
        }

        // Top failing files
        const topFiles = data.top_failing_files || [];
        if (topFiles.length > 0) {
            document.getElementById('auditor-files-section').style.display = 'block';
            let filesHtml = '<div class="data-table"><table><thead><tr><th>Archivo</th><th>Fallos</th></tr></thead><tbody>';
            topFiles.forEach(f => {
                filesHtml += `<tr><td><code>${f.file || f.script || '?'}</code></td><td>${f.count}</td></tr>`;
            });
            filesHtml += '</tbody></table></div>';
            document.getElementById('auditor-files-list').innerHTML = filesHtml;
        }

        // Suggestions
        const suggestions = data.suggestions || [];
        if (suggestions.length > 0) {
            document.getElementById('auditor-suggestions-section').style.display = 'block';
            let sugHtml = '';
            suggestions.forEach((s, i) => {
                sugHtml += `<div class="alert info" style="margin-bottom:8px;">
                    <span style="margin-right:8px;font-weight:700;">${i + 1}.</span> ${s}
                </div>`;
            });
            document.getElementById('auditor-suggestions-list').innerHTML = sugHtml;
        }

        if (data.total_failures === 0) {
            resultsDiv.innerHTML = '<div class="alert success" style="margin-top:16px;">No se detectaron fallos en los proyectos analizados.</div>';
        }

    } catch (err) {
        resultsDiv.innerHTML = '<div class="alert error">Error de conexion: ' + err.message + '</div>';
    } finally {
        btn.disabled = false;
        btn.textContent = 'Analizar Fallos';
    }
}\
'''


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                      SECCION 3: ORDEN DE INTEGRACION                       ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

INTEGRATION_ORDER = """
===============================================================================
  SECCION 3 — Orden de integracion (checklist)
===============================================================================

  [  ] 1. Copiar failure_auditor.py
         cp download/failure_auditor.py -> apa/core/failure_auditor.py
         (Esto reemplaza la version v1.0 si existia)

  [  ] 2. Agregar el import de FailurePatternAnalyzer
         Ubicacion: cerca de la linea 20, zona de imports core.
         Codigo: ver variable IMPORT_BLOCK

  [  ] 3. Agregar el endpoint /api/auditor
         Ubicacion: despues de los endpoints existentes, antes del HTML root.
         Codigo: ver variable ENDPOINT_BLOCK

  [  ] 4. Agregar el boton de pestana "Auditor"
         Ubicacion: despues del boton de la pestana "Agentes".
         Codigo: ver variable TAB_BUTTON_BLOCK

  [  ] 5. Agregar la seccion de contenido de la pestana
         Ubicacion: despues del ultimo <div class="tab-content"> existente.
         Codigo: ver variable TAB_CONTENT_BLOCK

  [  ] 6. Agregar la funcion JavaScript runAuditor()
         Ubicacion: al final del bloque <script>, antes de </script>.
         Codigo: ver variable JAVASCRIPT_BLOCK

  [  ] 7. Probar la integracion
         - Reiniciar el servidor APA
         - Verificar la pestana "Auditor" en la UI
         - Ejecutar analisis global (sin project_id)
         - Ejecutar analisis por proyecto (con project_id)
         - Confirmar renderizado de metricas, patrones, archivos y sugerencias

===============================================================================
"""


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                          UTILIDAD: AUTO-APLICAR PATCH                     ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def print_instructions():
    """Imprime las instrucciones completas en la terminal."""
    print(INSTRUCTIONS)


def print_integration_order():
    """Imprime el orden de integracion como checklist."""
    print(INTEGRATION_ORDER)


def print_block(name: str):
    """Imprime un bloque de codigo especifico por nombre.

    Args:
        name: Nombre del bloque. Valores validos:
              'import', 'endpoint', 'tab_button', 'tab_content', 'javascript'
    """
    blocks = {
        "import":       ("2.1 Import",             IMPORT_BLOCK),
        "endpoint":     ("2.2 API Endpoint",       ENDPOINT_BLOCK),
        "tab_button":   ("2.3 Tab Button HTML",    TAB_BUTTON_BLOCK),
        "tab_content":  ("2.4 Tab Content HTML",   TAB_CONTENT_BLOCK),
        "javascript":   ("2.5 JavaScript",         JAVASCRIPT_BLOCK),
    }

    if name not in blocks:
        print(f"[ERROR] Bloque '{name}' no encontrado. Bloques disponibles:")
        for key, (label, _) in blocks.items():
            print(f"  - {key} ({label})")
        return

    label, code = blocks[name]
    print(f"{'=' * 70}")
    print(f"  BLOQUE {label}")
    print(f"{'=' * 70}")
    print(code)
    print()


def print_all_blocks():
    """Imprime todos los bloques de codigo en orden."""
    for name in ["import", "endpoint", "tab_button", "tab_content", "javascript"]:
        print_block(name)


def get_blocks_dict() -> dict:
    """Retorna un diccionario con todos los bloques de codigo.

    Returns:
        dict con claves: import, endpoint, tab_button, tab_content, javascript
    """
    return {
        "import":       IMPORT_BLOCK,
        "endpoint":     ENDPOINT_BLOCK,
        "tab_button":   TAB_BUTTON_BLOCK,
        "tab_content":  TAB_CONTENT_BLOCK,
        "javascript":   JAVASCRIPT_BLOCK,
    }


# ─── Punto de entrada cuando se ejecuta como script ───

if __name__ == "__main__":
    import sys

    print("=" * 70)
    print("  UX1 — Failure Pattern Auditor :: app.py Integration Patch")
    print("=" * 70)
    print()

    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd == "--instructions" or cmd == "-i":
            print_instructions()
        elif cmd == "--order" or cmd == "-o":
            print_integration_order()
        elif cmd == "--blocks" or cmd == "-b":
            print_all_blocks()
        elif cmd == "--block":
            if len(sys.argv) > 2:
                print_block(sys.argv[2])
            else:
                print("[ERROR] Especifica el nombre del bloque.")
                print("  python UX1_app_py_integration.py --block import")
                print("  python UX1_app_py_integration.py --block endpoint")
                print("  python UX1_app_py_integration.py --block tab_button")
                print("  python UX1_app_py_integration.py --block tab_content")
                print("  python UX1_app_py_integration.py --block javascript")
        else:
            print("Uso:")
            print("  python UX1_app_py_integration.py              # Muestra todo")
            print("  python UX1_app_py_integration.py -i            # Instrucciones")
            print("  python UX1_app_py_integration.py -o            # Orden de integracion")
            print("  python UX1_app_py_integration.py -b            # Todos los bloques de codigo")
            print("  python UX1_app_py_integration.py --block <nombre>  # Un bloque especifico")
    else:
        # Sin argumentos: mostrar resumen completo
        print_instructions()
        print()
        print_all_blocks()
        print(INTEGRATION_ORDER)
