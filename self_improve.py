#!/usr/bin/env python3
# apa/self_improve.py — Pipeline de Auto-Mejora APA
#
# Ejecuta tareas de auto-modificación sobre el propio código de APA
# usando el pipeline: Planificador (LLM) → Codificador (LLM) → Ensamblador.
#
# Nivel 3 (AS5): Auto-mejora autónoma. El Director describe una tarea,
# APA genera el plan, el código, lo ensambla, valida y escribe.
#
# USO:
#   python apa/self_improve.py "Añadir método X a clase Y. Ancla: FIN_CLASE:Y"
#   python apa/self_improve.py --task task_description.txt
#   python apa/self_improve.py --dry-run "Tarea de prueba"
#
# SAFETY:
#   - Backup automático antes de cada modificación
#   - Validación de sintaxis obligatoria (ast.parse)
#   - Rollback automático si falla la validación
#   - --dry-run para ver qué se haría sin escribir archivos

import sys
import os
import argparse
import shutil
import ast
from datetime import datetime
from pathlib import Path

# Asegurar que apa.core es importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from core.assembler import Assembler, PlannerOutputParser, FullAssemblyResult
from core.router import call_llm


# ─── System Prompts (adaptados de semi_auto_agent.py) ───

PLANIFICADOR_SYSTEM_PROMPT = """Eres un Ingeniero de Software Senior. Tu rol es el de Agente Planificador de Ensamblaje Atómico del proyecto APA.

## CONTEXTO: AUTO-MEJORA
Estás modificando el PROPIO CÓDIGO de APA. Sé extremadamente cuidadoso con:
- No romper imports existentes
- No modificar métodos que no se te piden
- Mantener la compatibilidad con la API existente
- Usar anclas precisas para inserciones quirúrgicas

## FORMATO DE SALIDA

Tu respuesta SIEMPRE debe ser UN ÚNICO bloque ```markdown```. Sin texto antes ni después.

Plantilla para UNA tarea:

## TAREA DE ENSAMBLAJE
- SCRIPT: {ruta/archivo.py}
- TAREA_ID: {ID}
- ANCLA: {ANCLA_AST}
- MODO_EJECUCION: {local | nas}

## BLOQUE

# INSTRUCCIÓN PARA CODIFICADOR:
# {descripción técnica precisa}
# INDENTACIÓN: {0 | 4 | 8}
# DATOS ESPECÍFICOS:
# {contexto de estructuras existentes si aplica}

# VALIDACIÓN:
# - {criterio verificable}

## IMPORTS_NUEVOS
{módulo}

Omite IMPORTS_NUEVOS si no hay imports.

## REGLAS CRÍTICAS

1. **UN ANCLA = UNA OPERACIÓN**: Cada tarea tiene su propia ancla.
2. **SEPARACIÓN DE ROLES**: El BLOQUE contiene SOLO comentarios de instrucción. NUNCA código ejecutable.
3. **DATOS ESPECÍFICOS OBLIGATORIOS**: Cuando la tarea implique estructura EXISTENTE, indica qué existe en esa posición.
4. **REGLA ANTI-ERROR IMPORTS**: Tarea solo imports → BLOQUE VACÍO.
5. **APIs EXTERNAS**: Especificar SIEMPRE la firma completa.

## ANCLAS DISPONIBLES

INICIO_ARCHIVO | FIN_ARCHIVO | FIN_CLASE:Nombre | INICIO_CLASE:Nombre
ANTES_FUNCION:nombre | DESPUES_FUNCION:nombre | REEMPLAZAR_FUNCION:nombre
ANTES_CLASE:Nombre | DESPUES_METODO:Clase.metodo | REEMPLAZAR_METODO:Clase.met
FIN_IMPORTS | INSERTAR_ANTES_MAIN | REEMPLAZAR_BLOQUE_MAIN | ARCHIVO_NUEVO

## REGLA DE ELECCIÓN

- Archivo nuevo → ARCHIVO_NUEVO
- Añadir método a clase → FIN_CLASE:Nombre o DESPUES_METODO:Clase.metodo
- Añadir algo nuevo → ANTES_FUNCION, DESPUES_FUNCION, FIN_CLASE
- Modificar existente → REEMPLAZAR_FUNCION, REEMPLAZAR_METODO
- Solo imports → IMPORTS_NUEVOS (BLOQUE vacío)
"""

CODIFICADOR_SYSTEM_PROMPT = """Eres un Ingeniero de Software Senior. Tu rol es el de Agente Codificador de Script Atómico del proyecto APA.

## CONTEXTO: AUTO-MEJORA
Estás generando código que se insertará en el PROPIO CÓDIGO de APA. Esto requiere:
- Código limpio, bien documentado, sin errores
- Imports mínimos (solo los necesarios)
- Compatibilidad total con la API existente
- Tipado correcto (type hints)

## FORMATO DE ENTREGA OBLIGATORIO
Tu respuesta SIEMPRE debe ser UN ÚNICO bloque de código Markdown de Python, envuelto en ```python``` al inicio y ``` al final.
- NUNCA incluyas texto, comentarios o explicaciones fuera del bloque de código.
- La primera línea DENTRO del bloque debe ser el comentario de ruta: # {ruta/archivo.py}

## REGLA 0 — COMPUERTA DE ENTRADA
Antes de escribir, respóndete internamente:
¿La instrucción describe explícitamente una función, método o clase a implementar?
    SÍ → escribe exactamente ese bloque dentro del marco markdown.
    NO → no escribas nada.

## REGLAS DE FORMATO INTERNO
1. Primera línea SIEMPRE: # {ruta/archivo.py}
2. Indentación: aplica INDENTACIÓN: X espacios si se especifica.
3. Bloques completos: si piden reescribir, entrega la unidad completa.
4. Imports: implementar CORRECTAMENTE según IMPORTS_NUEVOS recibido.
5. Ignora comentarios # INSTRUCCIÓN... del prompt. Tu respuesta es solo código ejecutable.

## REGLA DE INTEGRACIÓN
Todo código debe estar DENTRO de una función, método o clase.
NUNCA dejar líneas sueltas fuera de una unidad arquitectónica.

## REGLA DE VALIDACIÓN
Al final de TODO código, incluir exactamente:
if __name__ == "__main__":
    # === VALIDACIÓN TAREA: {ID} ===
    [Tests ejecutables que cubran CADA criterio de la sección VALIDACIÓN]
"""


def self_improve(
    task_description: str,
    target_file: str = "",
    project_root: str = "",
    dry_run: bool = False,
    max_retries: int = 2,
    on_progress=None,
) -> dict:
    """
    Ejecuta el pipeline de auto-mejora: Planner → Coder → Assembler.
    
    Args:
        task_description: Descripción de la tarea en lenguaje natural
        target_file: Archivo objetivo (ruta relativa). Si está vacío,
                     el Planificador lo determinará.
        project_root: Ruta raíz del proyecto
        dry_run: Si True, no escribe archivos
        max_retries: Máximo de reintentos si falla la validación
        on_progress: Callback de progreso (etapa, mensaje)
    
    Returns:
        dict con: success, assembled_content, backup_path, error, 
                  model_used_planner, model_used_coder, validation_result
    """
    if not project_root:
        project_root = os.path.join(os.path.dirname(__file__), "..")
        project_root = os.path.abspath(project_root)
    
    result = {
        "success": False,
        "assembled_content": "",
        "backup_path": None,
        "error": None,
        "model_used_planner": "",
        "model_used_coder": "",
        "validation_result": {},
        "attempts": 0,
    }
    
    def _report(stage, msg):
        if on_progress:
            on_progress(stage, msg)
        print(f"  [{stage}] {msg}")
    
    for attempt in range(1, max_retries + 1):
        result["attempts"] = attempt
        _report("auto-mejora", f"Intento {attempt}/{max_retries}")
        
        try:
            # ─── PASO 1: Leer contenido original ───
            if not target_file:
                # Intentar detectar el archivo de la descripción
                for pattern in ["apa/core/", "apa/agents/", "apa/config/"]:
                    if pattern in task_description:
                        import re
                        m = re.search(r'(\S+\.py)', task_description)
                        if m:
                            target_file = m.group(1)
                            break
                if not target_file:
                    result["error"] = "No se pudo determinar el archivo objetivo"
                    return result
            
            file_path = os.path.join(project_root, target_file)
            if not os.path.exists(file_path):
                result["error"] = f"Archivo no encontrado: {file_path}"
                return result
            
            with open(file_path, 'r', encoding='utf-8') as f:
                original_content = f.read()
            
            _report("lectura", f"Archivo: {target_file} ({len(original_content)} chars)")
            
            # ─── PASO 2: Crear backup ───
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_dir = os.path.join(project_root, "backups")
            os.makedirs(backup_dir, exist_ok=True)
            backup_name = f"{Path(target_file).stem}_backup_{timestamp}.py"
            backup_path = os.path.join(backup_dir, backup_name)
            shutil.copy2(file_path, backup_path)
            result["backup_path"] = backup_path
            _report("backup", f"Backup creado: {backup_name}")
            
            # ─── PASO 3: Llamar al Planificador ───
            _report("planificador", "Consultando Planificador...")
            
            # Construir prompt del Planificador con contexto del archivo
            planner_user_prompt = f"""TAREA: {task_description}

ARCHIVO TARGET: {target_file}

CONTEXTO DEL ARCHIVO (primeras 50 líneas y últimas 30):
```python
{chr(10).join(original_content.split(chr(10))[:50])}
# ... (contenido intermedio omitido) ...
{chr(10).join(original_content.split(chr(10))[-30:])}
```

ESTRUCTURAS EXISTENTES:
{_get_structure_summary(original_content)}
"""
            
            planner_response = call_llm(
                task_type="planning",
                system_prompt=PLANIFICADOR_SYSTEM_PROMPT,
                user_prompt=planner_user_prompt,
                max_tokens=3000,
                temperature=0.1,
            )
            
            if not planner_response.get("success"):
                result["error"] = f"Error Planificador: {planner_response.get('error', 'sin respuesta')}"
                _report("planificador", f"ERROR: {result['error']}")
                continue
            
            planner_output = planner_response["content"]
            result["model_used_planner"] = planner_response.get("model_used", "")
            _report("planificador", f"OK — modelo: {result['model_used_planner']}")
            
            # ─── PASO 4: Llamar al Codificador ───
            _report("codificador", "Consultando Codificador...")
            
            coder_user_prompt = f"""{planner_output}

CÓDIGO EXISTENTE EN {target_file} (fragmentos relevantes):
{_get_relevant_context(original_content, planner_output)}
"""
            
            # Si es reintento, añadir contexto de corrección
            if attempt > 1 and result.get("validation_result"):
                val = result["validation_result"]
                error_msg = val.get("output", "")[:500]
                coder_user_prompt += f"""

## CONTEXTO DE CORRECCIÓN
El código anterior falló la validación con el siguiente error:
{error_msg}

Corrige el código para resolver este error. Mantén la misma estructura pero aplica los cambios necesarios.
"""
            
            coder_response = call_llm(
                task_type="generation",
                system_prompt=CODIFICADOR_SYSTEM_PROMPT,
                user_prompt=coder_user_prompt,
                max_tokens=4000,
                temperature=0.1,
            )
            
            if not coder_response.get("success"):
                result["error"] = f"Error Codificador: {coder_response.get('error', 'sin respuesta')}"
                _report("codificador", f"ERROR: {result['error']}")
                continue
            
            coder_output = coder_response["content"]
            result["model_used_coder"] = coder_response.get("model_used", "")
            _report("codificador", f"OK — modelo: {result['model_used_coder']}")
            
            # ─── PASO 5: Ensamblar ───
            _report("ensamblador", "Ensamblando código...")
            
            assembler = Assembler()
            assembly_result = assembler.run_full(
                planner_text=planner_output,
                coder_text=coder_output,
                original_content=original_content,
                script_name=target_file,
                duplicate_action="replace",
                validation_override="new",
            )
            
            result["validation_result"] = assembly_result.validation_result
            result["assembled_content"] = assembly_result.assembled_content
            
            if not assembly_result.success:
                if assembly_result.rolled_back:
                    _report("ensamblador", "Rollback ejecutado — código inválido")
                else:
                    _report("ensamblador", f"Ensamblaje falló: {assembly_result.validation_result}")
                
                # Si hay syntax error, reintentar
                val = assembly_result.validation_result or {}
                val_out = str(val.get("output", ""))
                if "SyntaxError" in val_out or "unexpected indent" in val_out:
                    _report("ensamblador", "SyntaxError detectado — reintentando...")
                    continue
                
                result["error"] = f"Ensamblaje falló: {val_out[:200]}"
                return result
            
            _report("ensamblador", "Ensamblaje exitoso")
            
            # ─── PASO 6: Validación funcional ───
            _report("validación", "Verificando código ensamblado...")
            
            # Syntax check
            try:
                ast.parse(assembly_result.assembled_content)
                _report("validación", "✅ Sintaxis válida")
            except SyntaxError as e:
                _report("validación", f"❌ SyntaxError: {e}")
                continue
            
            # Check que el archivo sigue importable
            import_ok = _check_importable(assembly_result.assembled_content, target_file)
            if not import_ok:
                _report("validación", "❌ Módulo no importable — reintentando...")
                continue
            
            _report("validación", "✅ Módulo importable")
            
            # ─── PASO 7: Escribir archivo ───
            if dry_run:
                _report("escritura", "DRY-RUN — archivo NO escrito")
                _report("escritura", f"Contenido ensamblado: {len(assembly_result.assembled_content)} chars")
            else:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(assembly_result.assembled_content)
                _report("escritura", f"✅ Archivo escrito: {target_file}")
            
            result["success"] = True
            return result
            
        except Exception as e:
            result["error"] = f"Error inesperado: {e}"
            _report("error", str(e))
            import traceback
            traceback.print_exc()
    
    return result


def _get_structure_summary(content: str) -> str:
    """Extrae un resumen de las estructuras (clases, funciones) del código."""
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return "No se pudo parsear el archivo"
    
    lines = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            methods = [
                f"    {n.name}()" 
                for n in node.body 
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            method_list = ", ".join(methods[:8])
            if len(methods) > 8:
                method_list += f", ... (+{len(methods)-8} más)"
            lines.append(f"class {node.name} ({len(methods)} métodos): {method_list}")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Solo funciones de nivel de módulo
            for parent in ast.walk(tree):
                if isinstance(parent, ast.ClassDef) and node in parent.body:
                    break
            else:
                lines.append(f"def {node.name}()")
    
    return "\n".join(lines[:30])


def _get_relevant_context(content: str, planner_output: str) -> str:
    """Extrae fragmentos relevantes del código basándose en el planner output."""
    lines = content.split('\n')
    
    # Buscar nombres de clases/métodos en el planner output
    relevant_lines = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("class ") or stripped.startswith("def "):
            # Incluir contexto alrededor de clases y funciones mencionadas
            for keyword in planner_output.split():
                keyword = keyword.strip(":-.,;")
                if keyword and keyword in stripped:
                    start = max(0, i - 2)
                    end = min(len(lines), i + 20)
                    relevant_lines.append(f"# Líneas {start+1}-{end}:")
                    relevant_lines.extend(lines[start:end])
                    relevant_lines.append("")
                    break
    
    if not relevant_lines:
        # Fallback: últimas 30 líneas
        relevant_lines = lines[-30:]
    
    return "\n".join(relevant_lines[:100])


def _check_importable(content: str, target_file: str) -> bool:
    """Verifica que el módulo modificado sigue siendo importable."""
    try:
        compile(content, target_file, 'exec')
        return True
    except SyntaxError:
        return False


def main():
    parser = argparse.ArgumentParser(
        description="APA Self-Improvement Pipeline — Auto-modificación del propio código"
    )
    parser.add_argument(
        "task", nargs="?", 
        help="Descripción de la tarea de auto-mejora"
    )
    parser.add_argument(
        "--task-file", "-f",
        help="Archivo con la descripción de la tarea"
    )
    parser.add_argument(
        "--target", "-t", default="",
        help="Archivo objetivo (ruta relativa)"
    )
    parser.add_argument(
        "--project-root", "-r", default="",
        help="Ruta raíz del proyecto"
    )
    parser.add_argument(
        "--dry-run", "-n", action="store_true",
        help="No escribir archivos, solo simular"
    )
    parser.add_argument(
        "--max-retries", type=int, default=2,
        help="Máximo de reintentos (default: 2)"
    )
    
    args = parser.parse_args()
    
    # Obtener descripción de la tarea
    task = args.task or ""
    if args.task_file:
        with open(args.task_file, 'r', encoding='utf-8') as f:
            task = f.read().strip()
    
    if not task:
        parser.error("Se requiere una descripción de tarea (argumento o --task-file)")
    
    print("=" * 70)
    print("  APA SELF-IMPROVEMENT PIPELINE")
    print("=" * 70)
    print(f"  Fecha:  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Tarea:  {task[:80]}{'...' if len(task) > 80 else ''}")
    print(f"  Target: {args.target or '(auto-detectar)'}")
    print(f"  Dry-run: {args.dry_run}")
    print("=" * 70)
    print()
    
    result = self_improve(
        task_description=task,
        target_file=args.target,
        project_root=args.project_root,
        dry_run=args.dry_run,
        max_retries=args.max_retries,
    )
    
    print()
    print("=" * 70)
    print("  RESULTADO")
    print("=" * 70)
    print(f"  Éxito:     {result['success']}")
    print(f"  Intentos:  {result['attempts']}")
    print(f"  Planner:   {result['model_used_planner']}")
    print(f"  Coder:     {result['model_used_coder']}")
    if result['backup_path']:
        print(f"  Backup:    {result['backup_path']}")
    if result['error']:
        print(f"  Error:     {result['error']}")
    if result['success']:
        print(f"  Contenido: {len(result['assembled_content'])} chars")
    print("=" * 70)
    
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
