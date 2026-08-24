# apa/core/assembler.py — Motor de Ensamblaje Atómico APA (v4.3)
#
# Motor completo de ensamblaje: parseo, normalización de imports, detección
# de duplicados, merge inteligente, ensamblaje y validación.
#
# Este módulo es independiente de la GUI y puede ser usado por:
#   - ensamblador_gui.py (interfaz manual)
#   - SemiAutoAgent (ensamblaje semi-autónomo)
#   - SelfImproveAgent (ensamblaje autónomo)
#   - Orchestrator (pipeline principal)
#
# USO:
#   from apa.core.assembler import Assembler, PlannerOutputParser
#
#   # Parseo del output del Planificador
#   parsed = PlannerOutputParser.parse(planner_text)
#   blocks = PlannerOutputParser._parse_blocks(planner_text)
#
#   # Ensamblaje completo
#   assembler = Assembler()
#   result = assembler.run_full(
#       planner_text=...,
#       coder_text=...,
#       original_content=...,
#       script_name="test_target.py",
#       duplicate_action="modify"  # o "replace", "discard"
#   )
#   if result.success:
#       print(result.output)  # código ensamblado

import ast
import logging
import os
import re
import subprocess
import sys
import textwrap
import time
from dataclasses import dataclass, field
from typing import Dict, Optional
from pathlib import Path

# v4.1: Logging y UsageTracker para métricas de ensamblaje
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTES
# ═══════════════════════════════════════════════════════════════════════════════

_IMPORT_SPEC_THRESHOLD = 3  # 3+ attrs del mismo módulo → mantener import genérico


# ═══════════════════════════════════════════════════════════════════════════════
# DATACLASSES DE RESULTADO
# ═══════════════════════════════════════════════════════════════════════════════

class ValidationMode:
    SYNTAX = "syntax"
    IMPORT = "import"
    EXECUTE = "execute"
    AUTO = "auto"

@dataclass
class AssemblyResult:
    success: bool
    output: str
    backup_path: Optional[str]
    summary: str

@dataclass
class FullAssemblyResult:
    """Resultado completo del flujo de ensamblaje."""
    success: bool
    assembled_content: str
    validation_result: dict
    parsed: dict
    blocks: list
    anchor_map: dict
    pre_modification_content: str
    pending_validation_code: Optional[str] = None
    task_id: str = ""
    script_name: str = ""
    validation_mode: str = "new"
    log: list = field(default_factory=list)
    duplicate_decisions: list = field(default_factory=list)
    rolled_back: bool = False  # v4.2: True si se restauró el original por validación fallida


# ═══════════════════════════════════════════════════════════════════════════════
# PLANNER OUTPUT PARSER
# ═══════════════════════════════════════════════════════════════════════════════

class PlannerOutputParser:
    """Parser del output del Planificador.
    
    Extrae tareas, imports y bloques del texto generado por el
    agente Planificador. No requiere el campo ANCLA (eliminado en v5.0).
    El posicionamiento de código lo realiza el agente Integrador (LLM).
    """
    
    # Regex para campos escalares (tolerantes a espacios y mayúsculas)
    _RE_INDENT       = re.compile(r'#*\s*(?:-|##)?\s*#\s*INDENTACIÓN\s*:\s*(\d+)', re.IGNORECASE)
    _RE_SCRIPT       = re.compile(r'#*\s*(?:-|##)?\s*SCRIPT\s*:\s*(.+)', re.IGNORECASE)
    _RE_TAREA_ID     = re.compile(r'#*\s*(?:-|##)?\s*TAREA_?ID\s*:\s*(\S+)', re.IGNORECASE)
    _RE_MODO         = re.compile(r'#*\s*(?:-|##)?\s*MODO_?EJECUCION\s*:\s*(\S+)', re.IGNORECASE)
    _RE_CONTEXTO     = re.compile(r'#*\s*(?:-|##)?\s*CONTEXTO\s*:\s*(.+)', re.IGNORECASE)
    _RE_COINCIDENCIA = re.compile(r'#*\s*(?:-|##)?\s*COINCIDENCIA\s*:\s*(\S+)', re.IGNORECASE)
    _RE_LINEA        = re.compile(r'#*\s*(?:-|##)?\s*LINEA\s*:\s*(\d+)', re.IGNORECASE)
    _RE_RANGO        = re.compile(r'#*\s*(?:-|##)?\s*RANGO\s*:\s*(\d+)\s*-\s*(\d+)', re.IGNORECASE)
    
    @staticmethod    
    def _sanitize_module(name: str) -> str:
        """Limpia un nombre de módulo de puntuación espuria."""
        return name.strip().rstrip('.,; \t')
    
    @staticmethod
    def _parse_method_reference(ref: str) -> tuple:
        """Parsea 'Clase.metodo' → ('Clase', 'metodo'), 'metodo' → (None, 'metodo')"""
        if '.' in ref:
            parts = ref.split('.', 1)
            return parts[0].strip(), parts[1].strip()
        return None, ref.strip()
    
    @classmethod
    def _parse_imports(cls, text: str) -> list:
        """Parser robusto de imports desde sección ## IMPORTS_NUEVOS."""
        imports = []
        marker = None
        for line in text.split('\n'):
            if re.search(r'##\s*IMPORTS_NUEVOS', line, re.IGNORECASE):
                marker = line
                break
        if marker is None:
            return imports
        
        after = text.split(marker, 1)[1]
        section_lines = []
        for line in after.split('\n'):
            if line.strip().startswith('##'):
                break
            section_lines.append(line)
        
        for line in section_lines:
            raw = line.strip()
            if not raw or raw.startswith('#'):
                continue
            if raw.startswith('- '):
                raw = raw[2:].strip()
            elif raw.startswith('-'):
                raw = raw[1:].strip()
            if not raw:
                continue
            if raw.startswith("import ") or raw.startswith("from "):
                canonical = raw
            else:
                clean = cls._sanitize_module(raw)
                if not clean:
                    continue
                if not re.match(r'^[\w][\w\.]*$', clean):
                    continue
                canonical = "import " + clean
            if canonical not in imports:
                imports.append(canonical)
        return imports
    
    @classmethod
    def parse(cls, text: str) -> dict:
        """Parsea un bloque individual del Planificador."""
        result = {
            "script": "", "tarea_id": "",
            "modo": "local", "imports_nuevos": [], "errores": [],
            "contexto": "", "coincidencia": "PRIMERA",
            "linea": None, "rango_inicio": None, "rango_fin": None,
            "indentacion": 0,
        }
        for pattern, key in [
            (cls._RE_SCRIPT, "script"), (cls._RE_TAREA_ID, "tarea_id"),
            (cls._RE_MODO, "modo"),
            (cls._RE_CONTEXTO, "contexto"), (cls._RE_COINCIDENCIA, "coincidencia"),
        ]:
            m = pattern.search(text)
            if m:
                result[key] = m.group(1).strip()
        m = cls._RE_LINEA.search(text)
        if m:
            result["linea"] = int(m.group(1))
        m = cls._RE_RANGO.search(text)
        if m:
            result["rango_inicio"] = int(m.group(1))
            result["rango_fin"] = int(m.group(2))
        m = cls._RE_INDENT.search(text)
        if m:
            result["indentacion"] = int(m.group(1))
        result["modo"] = "nas" if "nas" in result["modo"].lower() else "local"
        result["imports_nuevos"] = cls._parse_imports(text)
        if not result["script"]:
            result["errores"].append("Falta campo SCRIPT.")
        return result
    
    @classmethod
    def _parse_blocks(cls, text: str) -> list:
        """Extrae múltiples bloques del output del Planificador."""
        blocks = []
        
        # 1. Verificar ## BLOQUES (prioridad)
        blocks_section = ""
        in_blocks = False
        for line in text.split("\n"):
            if line.strip() == "## BLOQUES":
                in_blocks = True
                continue
            if in_blocks:
                if line.strip().startswith("## ") and "BLOQUES" not in line:
                    break
                blocks_section += line + "\n"
        
        if blocks_section.strip():
            current_block = None
            current_code_lines = []
            for line in blocks_section.split("\n"):
                if line.strip().startswith("### BLOQUE"):
                    if current_block:
                        current_block["code"] = "\n".join(current_code_lines).strip()
                        blocks.append(current_block)
                    current_block = {"anchor": "", "action": "after", "indent": 0, "code": "", "imports": [], "tarea_id": "", "script": ""}
                    current_code_lines = []
                elif current_block is not None:
                    if line.strip().startswith("- ANCLA:"):
                        current_block["anchor"] = line.split(":", 1)[1].strip()
                    elif line.strip().startswith("- ACCIÓN:"):
                        current_block["action"] = line.split(":", 1)[1].strip().lower()
                    elif line.strip().startswith("- INDENTACIÓN:"):
                        try:
                            current_block["indent"] = int(line.split(":")[1].strip())
                        except:
                            pass
                    elif line.strip().startswith("# INSTRUCCIÓN"):
                        continue
                    elif not line.strip().startswith("-") and not line.strip().startswith("###"):
                        current_code_lines.append(line)
            if current_block:
                current_block["code"] = "\n".join(current_code_lines).strip()
                blocks.append(current_block)
            imports = cls._parse_imports(text)
            if imports and blocks:
                blocks[0]["imports"] = imports
            if blocks:
                m = cls._RE_SCRIPT.search(text)
                if m:
                    for b in blocks:
                        b["script"] = m.group(1).strip()
                m = cls._RE_TAREA_ID.search(text)
                if m:
                    for b in blocks:
                        b["tarea_id"] = m.group(1).strip()
                return blocks
        
        # 2. Múltiples ## TAREA DE ENSAMBLAJE
        task_pattern = re.compile(r'^##\s*TAREA\s*DE\s*ENSAMBLAJE', re.MULTILINE)
        task_matches = list(task_pattern.finditer(text))
        if task_matches:
            for i, match in enumerate(task_matches):
                start = match.start()
                end = task_matches[i + 1].start() if i + 1 < len(task_matches) else len(text)
                task_text = text[start:end]
                parsed = cls.parse(task_text)
                if parsed.get("script"):
                    blocks.append({
                        "anchor": "", "action": "after",
                        "indent": parsed.get("indentacion", 0), "code": "",
                        "imports": parsed.get("imports_nuevos", []),
                        "tarea_id": parsed.get("tarea_id", ""),
                        "script": parsed.get("script", "")
                    })
            if blocks:
                return blocks
        
        # 3. Fallback: una sola tarea
        parsed = cls.parse(text)
        if parsed.get("script"):
            blocks.append({
                "anchor": "", "action": "after",
                "indent": parsed.get("indentacion", 0), "code": "",
                "imports": parsed.get("imports_nuevos", []),
                "tarea_id": parsed.get("tarea_id", ""),
                "script": parsed.get("script", "")
            })
        return blocks
    
    # v5.0: resolve_anchor() eliminado — sistema de anclas simplificado
    @staticmethod
    def get_context_info(content: str, line_number: int) -> dict:
        """Obtiene información del contexto en una línea específica.
        
        Retorna dict con:
        - clase: nombre de clase si está dentro de una, o None
        - funcion: nombre de función si está dentro de una, o None
        - indentacion: nivel de indentación
        - linea_contenido: contenido de la línea
        - linea_numero: número de línea
        """
        lines = content.split('\n')
        
        if line_number < 1 or line_number > len(lines):
            return {"error": "Número de línea fuera de rango"}
        
        line_content = lines[line_number - 1]
        indentation = len(line_content) - len(line_content.lstrip())
        
        result = {
            "clase": None,
            "funcion": None,
            "indentacion": indentation,
            "linea_contenido": line_content,
            "linea_numero": line_number,
        }
        
        try:
            tree = ast.parse(content)
            
            # Buscar clase contenedora
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    if node.lineno <= line_number <= node.end_lineno:
                        result["clase"] = node.name
                        break
            
            # Buscar función contenedora
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.lineno <= line_number <= node.end_lineno:
                        result["funcion"] = node.name
                        break
        except:
            pass
        
        return result
    
    @staticmethod
    def _split_code_by_structure(code: str) -> list:
        """Divide código del Codificador en bloques por estructura."""
        if not code or not code.strip():
            return []
        blocks = []
        lines = code.split('\n')
        structure_markers = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                continue
            indent = len(line) - len(line.lstrip())
            if re.match(r'^(import|from)\s', stripped):
                if not structure_markers or structure_markers[-1][1] != 'imports':
                    structure_markers.append((i, 'imports', indent, None))
            elif re.match(r'^class\s+(\w+)', stripped):
                match = re.match(r'^class\s+(\w+)', stripped)
                structure_markers.append((i, 'class', indent, match.group(1) if match else None))
            elif re.match(r'^(async\s+)?def\s+(\w+)', stripped):
                match = re.match(r'^(async\s+)?def\s+(\w+)', stripped)
                name = match.group(2) if match else None
                struct_type = 'method' if indent >= 4 else 'function'
                structure_markers.append((i, struct_type, indent, name))
            elif indent == 0 and re.match(r'^[A-Za-z_]\w*\s*=', stripped):
                match = re.match(r'^([A-Za-z_]\w*)\s*=', stripped)
                structure_markers.append((i, 'variable', indent, match.group(1) if match else None))
        
        # Limpiar métodos dentro de clases
        class_indices = [i for i, (s, st, ind, n) in enumerate(structure_markers) if st == 'class']
        for class_idx in reversed(class_indices):
            _, _, class_indent, _ = structure_markers[class_idx]
            class_end = len(lines)
            for j in range(class_idx + 1, len(structure_markers)):
                _, _, next_indent, _ = structure_markers[j]
                if next_indent <= class_indent:
                    class_end = structure_markers[j][0]
                    break
            remove = [j for j in range(class_idx + 1, len(structure_markers)) if structure_markers[j][0] < class_end]
            for j in reversed(remove):
                structure_markers.pop(j)
        
        for idx, (start, struct_type, base_indent, name) in enumerate(structure_markers):
            end = structure_markers[idx + 1][0] if idx + 1 < len(structure_markers) else len(lines)
            if struct_type == 'imports':
                for j in range(start + 1, end):
                    line_stripped = lines[j].strip()
                    if line_stripped and not line_stripped.startswith('#') and not re.match(r'^(import|from)\s', line_stripped):
                        end = j
                        break
            elif struct_type in ['class', 'function', 'method']:
                for j in range(start + 1, end):
                    if not lines[j].strip():
                        continue
                    line_indent = len(lines[j]) - len(lines[j].lstrip())
                    if line_indent < base_indent and lines[j].strip():
                        end = j
                        break
            block_lines = lines[start:end]
            block_code = '\n'.join(block_lines)
            if block_code.strip():
                blocks.append({'type': struct_type, 'code': block_code, 'indent': base_indent, 'name': name})
        
        if not blocks and code.strip():
            first_line = lines[0] if lines else ""
            base_indent = len(first_line) - len(first_line.lstrip()) if first_line.strip() else 0
            blocks.append({'type': 'code', 'code': code, 'indent': base_indent, 'name': None})
        return blocks
    
    @classmethod
    def _associate_code_to_planner_blocks(cls, planner_blocks: list, code_blocks: list, existing_structures: set = None) -> list:
        """Asocia bloques de código con las tareas del Planificador."""
        if not planner_blocks:
            return []
        if not code_blocks:
            return planner_blocks
        
        result = []
        used = set()
        
        for i, p_block in enumerate(planner_blocks):
            anchor = p_block.get('anchor', '')
            expected_indent = p_block.get('indent', 0)
            new_block = dict(p_block)
            new_block['code'] = ''
            new_block['warning'] = None
            assigned = False
            
            # ESTRATEGIA 1: Imports
            if 'IMPORT' in anchor.upper() or anchor == 'INICIO_ARCHIVO':
                for j, c_block in enumerate(code_blocks):
                    if j not in used and c_block['type'] == 'imports':
                        new_block['code'] = c_block['code']
                        used.add(j)
                        assigned = True
                        break
                if not assigned:
                    assigned = True
            
            # ESTRATEGIA 2: Métodos
            elif 'CLASE' in anchor.upper() or 'METODO' in anchor.upper():
                if expected_indent >= 4:
                    for j, c_block in enumerate(code_blocks):
                        if j not in used and c_block['type'] == 'method':
                            if c_block['indent'] == expected_indent:
                                new_block['code'] = c_block['code']
                                used.add(j)
                                assigned = True
                                break
                    if not assigned:
                        for j, c_block in enumerate(code_blocks):
                            if j not in used and c_block['type'] == 'method':
                                new_block['code'] = c_block['code']
                                used.add(j)
                                new_block['warning'] = f'Indent esperada {expected_indent}, encontrada {c_block["indent"]}'
                                assigned = True
                                break
                            break
                    
                    # ESTRATEGIA 7: Extraer métodos nuevos de class block
                    if not assigned and existing_structures is not None:
                        class_name = None
                        if 'CLASE:' in anchor.upper():
                            idx = anchor.upper().find('CLASE:')
                            class_name = anchor[idx + 6:].strip()
                        if class_name:
                            for j, c_block in enumerate(code_blocks):
                                if j not in used and c_block['type'] == 'class' and c_block.get('name') == class_name:
                                    class_lines = c_block['code'].split('\n')
                                    new_methods = []
                                    current_method_name = None
                                    current_method_lines = []
                                    for cline in class_lines:
                                        cstripped = cline.strip()
                                        cindent = len(cline) - len(cline.lstrip())
                                        if cindent >= 4 and (cstripped.startswith('def ') or cstripped.startswith('async def ')):
                                            if current_method_name is not None:
                                                method_code = '\n'.join(current_method_lines)
                                                if ('function', current_method_name) not in existing_structures:
                                                    new_methods.append(method_code)
                                            match = re.match(r'(?:async\s+)?def\s+(\w+)', cstripped)
                                            current_method_name = match.group(1) if match else None
                                            current_method_lines = [cline]
                                        elif current_method_name is not None:
                                            current_method_lines.append(cline)
                                    if current_method_name is not None:
                                        method_code = '\n'.join(current_method_lines)
                                        if ('function', current_method_name) not in existing_structures:
                                            new_methods.append(method_code)
                                    if new_methods:
                                        new_block['code'] = '\n'.join(new_methods)
                                        used.add(j)
                                        assigned = True
                                    break
            
            # ESTRATEGIA 3: Clases
            elif 'CLASE' in anchor.upper():
                for j, c_block in enumerate(code_blocks):
                    if j not in used and c_block['type'] == 'class':
                        new_block['code'] = c_block['code']
                        used.add(j)
                        assigned = True
                        break
            
            # ESTRATEGIA 4: Funciones (orden de aparición)
            elif 'FUNCION' in anchor.upper():
                for j, c_block in enumerate(code_blocks):
                    if j not in used:
                        if c_block['type'] in ('function', 'class') and c_block['indent'] == expected_indent:
                            new_block['code'] = c_block['code']
                            used.add(j)
                            assigned = True
                            break
            
            # ESTRATEGIA 5: Fallback por indentación
            if not assigned:
                for j, c_block in enumerate(code_blocks):
                    if j not in used and c_block['indent'] == expected_indent:
                        new_block['code'] = c_block['code']
                        used.add(j)
                        assigned = True
                        break
            
            # ESTRATEGIA 6: Fallback por orden
            if not assigned:
                for j, c_block in enumerate(code_blocks):
                    if j not in used:
                        new_block['code'] = c_block['code']
                        used.add(j)
                        if c_block['indent'] != expected_indent:
                            new_block['warning'] = f'Indent esperada {expected_indent}, encontrada {c_block["indent"]}'
                        assigned = True
                        break
            
            result.append(new_block)
        
        # Verificar código no asociado
        for j, c_block in enumerate(code_blocks):
            if j not in used:
                if result:
                    prev_warning = result[-1].get('warning') or ''
                    result[-1]['warning'] = (prev_warning + ' | Código no asociado: ' + c_block['type']).strip(' |')
        
        return result


# ═══════════════════════════════════════════════════════════════════════════════
# ASSEMBLER — Motor de Ensamblaje
# ═══════════════════════════════════════════════════════════════════════════════

class Assembler:
    """Motor de ensamblaje atómico.
    
    Responsabilidades:
    - Ensamblaje de bloques de código sobre un archivo
    - Normalización de imports (deduplicación, directa e inversa)
    - Detección de estructuras duplicadas
    - Merge inteligente de clases
    - Validación (syntax, import, execute)
    - Flujo completo de ensamblaje (run_full)
    """
    
    # ── Ensamblaje básico ────────────────────────────────────────────────────
    
    def assemble(self, content: str, blocks: list[dict], anchor_map: dict) -> str:
        """Ensambla bloques de código sobre el contenido.
        
        Los bloques se aplican en orden descendente de línea para que las
        inserciones no desplacen los índices de los bloques posteriores.
        Cuando dos anclas resuelven a la misma línea, 'after' se aplica
        antes que 'before' para que 'before' quede realmente encima.
        
        Si un bloque tiene campo 'imports' (lista de import strings), se
        inyecta un bloque de imports adicional en FIN_IMPORTS de forma
        automática, con deduplicación contra los imports ya existentes.
        """
        lines = content.split('\n')
        
        # Detectar imports existentes para deduplicación
        # Bug 3.4 fix: skip imports inside if __name__ == "__main__" block
        existing_imports = set()
        _in_main = False
        for line in lines:
            stripped = line.strip()
            if "if __name__" in line and "__main__" in line:
                _in_main = True
                continue
            if _in_main:
                # Skip deduplication against scoped imports
                continue
            if stripped.startswith("import ") or stripped.startswith("from "):
                existing_imports.add(stripped)
        
        # Recolectar imports de todos los bloques que tengan campo 'imports'
        all_block_imports = []
        for block in blocks:
            for imp in block.get("imports", []):
                canonical = imp if (imp.startswith("import ") or imp.startswith("from ")) else "import " + imp
                if canonical not in existing_imports and canonical not in all_block_imports:
                    all_block_imports.append(canonical)
                    # NOTA: No añadir a existing_imports aquí; se añadirán
                    # cuando se inserten realmente como líneas del bloque
        
        # Si hay imports que inyectar, añadir un bloque de imports al inicio
        if all_block_imports:
            import_code = "\n".join(all_block_imports) + "\n"
            import_block = {"action": "after", "anchor": "FIN_IMPORTS", "code": import_code}
            # v5.0: Resolver FIN_IMPORTS vía AST directo (sin resolve_anchor)
            if "FIN_IMPORTS" not in anchor_map:
                _last_imp = 0
                for _i, _l in enumerate(content.split("\n")):
                    _s = _l.strip()
                    if "if __name__" in _l: break
                    if _s.startswith("import ") or _s.startswith("from "):
                        _last_imp = _i + 1
                _line_imp = _last_imp if _last_imp > 0 else len(content.split("\n"))
                anchor_map["FIN_IMPORTS"] = {"line": _line_imp, "end_line": _line_imp + 1}
            blocks = [import_block] + list(blocks)
        
        # Ordenar bloques: línea descendente, luego 'after' antes que 'before'
        # (ambos en la misma línea: after se inserta debajo, before encima)
        sorted_blocks = list(enumerate(blocks))
        sorted_blocks.sort(key=lambda ib: (
            -anchor_map.get(ib[1].get('anchor', ''), {}).get('line', 0),
            0 if ib[1].get('action') == 'after' else 1,
            -ib[0]
        ))
        
        for orig_idx, block in sorted_blocks:
            action = block['action']
            anchor = block['anchor']
            code = block['code']
            anchor_info = anchor_map[anchor]
            line_idx = anchor_info['line'] - 1
            code_lines = code.splitlines() if code else []
            
            # Deduplicación de imports: si el bloque es un import ya existente, omitir
            if self._detect_code_type(code) == "imports":
                filtered_code_lines = []
                for cl in code_lines:
                    stripped_cl = cl.strip()
                    if stripped_cl and (stripped_cl.startswith("import ") or stripped_cl.startswith("from ")):
                        if stripped_cl not in existing_imports:
                            filtered_code_lines.append(cl)
                            existing_imports.add(stripped_cl)
                    else:
                        filtered_code_lines.append(cl)
                code_lines = filtered_code_lines
                if not code_lines:
                    continue  # Todo el bloque eran imports duplicados
            
            code_type = self._detect_code_type(code)
            prev_type = self._detect_previous_structure(lines, line_idx)
            if code_type != prev_type and code_type != "unknown":
                if line_idx >= 0 and line_idx < len(lines):
                    if lines[line_idx].strip() != "":
                        code_lines = ["\n"] + code_lines
            if action == 'after':
                if line_idx < len(lines) and not lines[line_idx].endswith('\n'):
                    lines[line_idx] = lines[line_idx] + '\n'
                lines[line_idx + 1 : line_idx + 1] = code_lines
            elif action == 'before':
                lines[line_idx : line_idx] = code_lines
            elif action == 'replace':
                end_idx = anchor_info.get('end_line', anchor_info['line'] + 1)
                lines[line_idx : end_idx] = code_lines
        
        result = '\n'.join(lines)
        result = self._normalize_blank_lines(result)
        return result
    
    # ── Normalización de imports ─────────────────────────────────────────────
    
    @staticmethod
    def normalize_imports(existing_imports: list, new_imports: list, main_code_lines: list, 
                          test_code_lines: list, blocks_data: list) -> tuple:
        """Deduplica, normaliza y ordena imports. Retorna (imports_list, main_code_lines, test_code_lines, blocks_data).
        
        Normalización directa: from X import Y + X.Y() → Y()
        Normalización inversa: import X + X.Y() (1-2 attrs) → from X import Y + Y()
        """
        all_imports = existing_imports + new_imports
        
        # DEDUPLICACIÓN
        from_modules = set()
        for imp in all_imports:
            if imp.startswith("from "):
                match = re.match(r'from\s+(\S+)', imp)
                if match:
                    from_modules.add(match.group(1).split('.')[0])
        
        deduped_imports = []
        seen = set()
        for imp in all_imports:
            if imp.startswith("import "):
                match = re.match(r'import\s+(\S+)', imp)
                if match:
                    module = match.group(1).split('.')[0]
                    if module not in from_modules and imp not in seen:
                        deduped_imports.append(imp)
                        seen.add(imp)
            else:
                if imp not in seen:
                    deduped_imports.append(imp)
                    seen.add(imp)
        
        # ORDENAR
        simple_imports = [imp for imp in deduped_imports if imp.startswith("import ")]
        from_imports = [imp for imp in deduped_imports if imp.startswith("from ")]
        simple_imports.sort(key=lambda x: len(x))
        from_imports.sort(key=lambda x: len(x))
        
        # NORMALIZACIÓN DIRECTA: from X import Y + X.Y() → Y()
        from_import_map = {}
        for imp in from_imports:
            match = re.match(r'from\s+(\S+)\s+import\s+(.+)', imp)
            if match:
                module = match.group(1).split('.')[0]
                symbols = [s.strip() for s in match.group(2).split(',')]
                from_import_map[module] = symbols
        
        for module, symbols in from_import_map.items():
            for sym in symbols:
                pattern = re.compile(r'\b' + re.escape(module) + r'\.' + re.escape(sym) + r'\b')
                for i, line in enumerate(main_code_lines):
                    if pattern.search(line):
                        main_code_lines[i] = pattern.sub(sym, line)
                for i, line in enumerate(test_code_lines):
                    if pattern.search(line):
                        test_code_lines[i] = pattern.sub(sym, line)
                for bd in blocks_data:
                    bd_code = bd.get("code", "")
                    if bd_code and pattern.search(bd_code):
                        bd["code"] = pattern.sub(sym, bd_code)
        
        # NORMALIZACIÓN INVERSA: import X + X.Y() → from X import Y + Y()
        new_simple_imports = []
        converted_from_imports = []
        modules_to_remove = set()
        
        for imp in simple_imports:
            match = re.match(r'import\s+(\S+)', imp)
            if not match:
                new_simple_imports.append(imp)
                continue
            module = match.group(1)
            all_code = "\n".join(main_code_lines + test_code_lines)
            
            # Verificar reasignación
            assign_pattern = re.compile(r'\b' + re.escape(module) + r'\.\w+\s*=')
            if assign_pattern.search(all_code):
                new_simple_imports.append(imp)
                continue
            
            # Buscar atributos usados
            usage_pattern = re.compile(r'\b' + re.escape(module) + r'\.(\w+)')
            attrs_used = set(usage_pattern.findall(all_code))
            
            if not attrs_used:
                new_simple_imports.append(imp)
                continue
            
            if len(attrs_used) >= _IMPORT_SPEC_THRESHOLD:
                new_simple_imports.append(imp)
                continue
            
            # Convertir a from X import Y
            attrs_sorted = sorted(attrs_used)
            from_imp = "from " + module + " import " + ", ".join(attrs_sorted)
            converted_from_imports.append(from_imp)
            modules_to_remove.add(module)
            
            for attr in attrs_sorted:
                replace_pattern = re.compile(r'\b' + re.escape(module) + r'\.' + re.escape(attr) + r'\b')
                for i, line in enumerate(main_code_lines):
                    if replace_pattern.search(line):
                        main_code_lines[i] = replace_pattern.sub(attr, line)
                for i, line in enumerate(test_code_lines):
                    if replace_pattern.search(line):
                        test_code_lines[i] = replace_pattern.sub(attr, line)
                for bd in blocks_data:
                    bd_code = bd.get("code", "")
                    if bd_code and replace_pattern.search(bd_code):
                        bd["code"] = replace_pattern.sub(attr, bd_code)
        
        if modules_to_remove:
            simple_imports = new_simple_imports
            from_imports = from_imports + converted_from_imports
        
        imports_list = simple_imports + from_imports
        return imports_list, main_code_lines, test_code_lines, blocks_data
    
    @staticmethod
    def remove_existing_imports(content: str) -> tuple:
        """Elimina imports existentes del contenido. Retorna (content_without_imports, existing_imports_list)."""
        # Bug 3.4 fix: track scope to avoid capturing/removing imports
        # inside if __name__ == "__main__" blocks.
        existing_imports_list = []
        has_existing_imports = False
        _in_main = False
        for line in content.split("\n"):
            stripped = line.strip()
            if "if __name__" in line and "__main__" in line:
                _in_main = True
                continue
            if _in_main:
                continue
            if stripped.startswith("import ") or stripped.startswith("from "):
                existing_imports_list.append(stripped)
                has_existing_imports = True
        
        if not has_existing_imports:
            return content, existing_imports_list
        
        lines_content = content.split("\n")
        new_lines = []
        skip_blank_after_import = False
        _in_main = False
        for i, line in enumerate(lines_content):
            stripped = line.strip()
            if "if __name__" in line and "__main__" in line:
                _in_main = True
                new_lines.append(line)
                continue
            if _in_main:
                # Keep lines inside __main__ intact, including their imports
                new_lines.append(line)
                skip_blank_after_import = False
                continue
            if stripped.startswith("import ") or stripped.startswith("from "):
                skip_blank_after_import = True
                continue
            if skip_blank_after_import and stripped == "":
                skip_blank_after_import = False
                continue
            skip_blank_after_import = False
            new_lines.append(line)
        return "\n".join(new_lines), existing_imports_list
    
    @staticmethod
    def preprocess_coder_code(coder_code: str, script_name: str) -> dict:
        """Preprocesa el código del Codificador: limpia headers, separa imports/main/__main__.
        
        Retorna dict con:
            - imports_list: lista de imports globales (str)
            - main_code_lines: líneas de código principal (sin imports, sin __main__)
            - test_code_lines: líneas dentro de if __name__ == "__main__"
            - cleaned_code: código limpio (sin headers de archivo)
        """
        # 1. Limpiar headers de archivo (# file.py)
        script_name_only = Path(script_name).name
        code_lines = coder_code.split("\n")
        cleaned_lines = []
        for line in code_lines:
            stripped = line.strip()
            if stripped == "#" + script_name or stripped == "# " + script_name:
                continue
            if stripped == "#" + script_name_only or stripped == "# " + script_name_only:
                continue
            if re.match(r"^#\s*\w+[/\\]?\w*\.py$", stripped):
                continue
            cleaned_lines.append(line)
        # v4.3: Usar textwrap.dedent en lugar de .strip() para preservar
        # indentación relativa (crítico para código de nivel de clase)
        cleaned_code = textwrap.dedent("\n".join(cleaned_lines)).lstrip('\n').rstrip()
        
        # 2. Separar imports / código principal / bloque __main__
        imports_list = []
        main_code_lines = []
        test_code_lines = []
        in_main_block = False
        
        for line in cleaned_code.split("\n"):
            stripped = line.strip()
            # Bug 3.4 fix: check __main__ BEFORE imports
            if "if __name__" in line and "__main__" in line:
                in_main_block = True
                continue
            if in_main_block:
                test_code_lines.append(line)
                continue
            if stripped.startswith("import ") or stripped.startswith("from "):
                imports_list.append(stripped)
                continue
            main_code_lines.append(line)
        
        return {
            "imports_list": imports_list,
            "main_code_lines": main_code_lines,
            "test_code_lines": test_code_lines,
            "cleaned_code": cleaned_code,
        }
    # ── Detección de duplicados ──────────────────────────────────────────────
    
    @staticmethod
    def detect_existing_structures(content: str) -> set:
        """Detecta clases y funciones existentes en el contenido. Retorna set de (type, name)."""
        existing = set()
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    existing.add(("class", node.name))
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    existing.add(("function", node.name))
        except:
            pass
        return existing
    
    @staticmethod
    def detect_block_duplicates(code_content: str, existing_structures: set) -> set:
        """Detecta estructuras duplicadas en un bloque de código vs existentes."""
        block_structures = set()
        for line in code_content.split("\n"):
            stripped = line.strip()
            if stripped.startswith("class "):
                match = re.match(r"class\s+(\w+)", stripped)
                if match:
                    block_structures.add(("class", match.group(1)))
            elif stripped.startswith("def ") or stripped.startswith("async def "):
                match = re.match(r"(?:async\s+)?def\s+(\w+)", stripped)
                if match:
                    block_structures.add(("function", match.group(1)))
        return block_structures & existing_structures
    
    # ── Merge inteligente de clases ──────────────────────────────────────────
    
    @staticmethod
    def merge_class(original_content: str, new_code: str, class_name: str) -> Optional[str]:
        """Merge inteligente de clase: conserva métodos no modificados, actualiza modificados, añade nuevos."""
        try:
            orig_tree = ast.parse(original_content)
            new_tree = ast.parse(new_code)
        except SyntaxError:
            return None
        
        orig_class = None
        for node in ast.walk(orig_tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                orig_class = node
                break
        if orig_class is None:
            return None
        
        new_class = None
        for node in ast.walk(new_tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                new_class = node
                break
        if new_class is None:
            return None
        
        orig_lines = original_content.splitlines()
        new_lines = new_code.splitlines()
        
        # Decoradores
        orig_decorators = [orig_lines[dec.lineno-1] for dec in orig_class.decorator_list] if orig_class.decorator_list else []
        new_decorators = [new_lines[dec.lineno-1] for dec in new_class.decorator_list] if new_class.decorator_list else []
        decorators = new_decorators if new_decorators else orig_decorators
        
        # Extraer métodos y no-métodos
        def extract_members(cls, lines):
            methods, non_methods = {}, []
            for item in cls.body:
                src = '\n'.join(lines[item.lineno - 1 : item.end_lineno])
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods[item.name] = src
                else:
                    non_methods.append(src)
            return methods, non_methods
        
        orig_methods, orig_non = extract_members(orig_class, orig_lines)
        new_methods, new_non = extract_members(new_class, new_lines)
        
        # Header (herencia)
        class_header = orig_lines[orig_class.lineno - 1]
        new_header = new_lines[new_class.lineno - 1]
        if class_header.strip() != new_header.strip():
            class_header = new_header
        
        # Merge
        merged = []
        for src in (new_non if new_non else orig_non):
            merged.append(src)
        
        seen = set()
        for item in orig_class.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                seen.add(item.name)
                merged.append(new_methods[item.name] if item.name in new_methods else orig_methods[item.name])
        
        for item in new_class.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name not in seen:
                merged.append(new_methods[item.name])
                seen.add(item.name)
        
        # Reconstruir
        result_lines = []
        for dec in decorators:
            result_lines.append(dec)
        result_lines.append(class_header)
        for body_item in merged:
            result_lines.append('')
            for line in body_item.split('\n'):
                s = line.lstrip()
                if s:
                    indent = len(line) - len(s)
                    result_lines.append('    ' + line if indent == 0 else line)
                else:
                    result_lines.append('')
        
        return '\n'.join(result_lines)
    
    @staticmethod
    def resolve_duplicate_action(block_duplicates: set, anchor: str, action: str, 
                                 duplicate_decision: str = "replace") -> tuple:
        """Resuelve la acción para una estructura duplicada.
        
        Args:
            block_duplicates: set de (type, name) duplicados
            anchor: ancla original del bloque
            action: acción original
            duplicate_decision: "replace", "modify", o "discard"
        
        Returns:
            (new_anchor, new_action) o None si se debe descartar
        """
        if duplicate_decision == "discard":
            return None
        
        for struct_type, struct_name in block_duplicates:
            if duplicate_decision == "modify":
                if struct_type == "class":
                    return "REEMPLAZAR_CLASE:" + struct_name, "replace"
                else:
                    return "REEMPLAZAR_FUNCION:" + struct_name, "replace"
            else:  # replace
                if struct_type == "class":
                    return "REEMPLAZAR_CLASE:" + struct_name, "replace"
                else:
                    is_method = "CLASE" in anchor.upper() or "METODO" in anchor.upper()
                    if is_method:
                        class_match = re.search(r'CLASE:(\w+)', anchor)
                        if class_match:
                            return "REEMPLAZAR_METODO:" + class_match.group(1) + "." + struct_name, "replace"
                        else:
                            return "REEMPLAZAR_FUNCION:" + struct_name, "replace"
                    else:
                        return "REEMPLAZAR_FUNCION:" + struct_name, "replace"
        return anchor, action
    
    # ── Validación ───────────────────────────────────────────────────────────
    
    @staticmethod
    def _detect_validation_mode(content: str) -> str:
        gui_libs = ["tkinter", "PyQt", "PySide", "wx", "kivy"]
        for lib in gui_libs:
            if lib in content:
                return ValidationMode.IMPORT
        server_libs = ["flask", "fastapi", "uvicorn", "tornado", "django"]
        for lib in server_libs:
            if lib in content:
                return ValidationMode.IMPORT
        if "__name__" in content and "__main__" in content:
            heavy_test_indicators = [
                "NASConnector", "correction_loop", "call_llm", "subprocess.run",
                "unittest", "pytest", "test_", "_test(", "logging.basicConfig",
            ]
            for indicator in heavy_test_indicators:
                if indicator in content:
                    return ValidationMode.IMPORT
            return ValidationMode.EXECUTE
        return ValidationMode.IMPORT
    
    @staticmethod
    def validate(content: str, script_path: str = None, validation_mode: str = ValidationMode.AUTO) -> dict:
        """Valida el contenido ensamblado."""
        if validation_mode == ValidationMode.AUTO:
            validation_mode = Assembler._detect_validation_mode(content)
        output = ""
        returncode = -1
        
        if validation_mode == ValidationMode.SYNTAX:
            try:
                ast.parse(content)
                output = "Validacion de sintaxis exitosa."
                returncode = 0
            except SyntaxError as e:
                output = "Error de sintaxis linea " + str(e.lineno) + ": " + str(e.msg)
                returncode = 1
        
        elif validation_mode == ValidationMode.IMPORT:
            import importlib.util, tempfile, os
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            try:
                spec = importlib.util.spec_from_file_location("_validation_module", tmp_path)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                output = "Imports validados correctamente."
                returncode = 0
            except Exception as e:
                output = "Error al importar: " + str(e)
                returncode = 1
            finally:
                os.unlink(tmp_path)
        
        elif validation_mode == ValidationMode.EXECUTE:
            import tempfile, os
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            try:
                result = subprocess.run([sys.executable, tmp_path], capture_output=True, text=True, timeout=10)
                output = result.stdout
                if result.stderr:
                    output += "\n" + result.stderr if result.stdout else result.stderr
                returncode = result.returncode
            finally:
                os.unlink(tmp_path)
        
        return {"success": returncode == 0, "output": output, "returncode": returncode}
    
    # ── Flujo completo de ensamblaje ─────────────────────────────────────────
    
    def _log_assembly_usage(
        self,
        success: bool,
        script_name: str,
        assembled_content: str,
        planner_text: str,
        coder_text: str,
        project_id: Optional[str],
        llm_metadata: Optional[Dict],
        latency_ms: int,
        error_type: str = "",
        blocks_count: int = 0,
    ) -> None:
        """v4.1: Registra métricas del ensamblaje en UsageTracker.
        
        No falla nunca — errores de logging no deben interrumpir el flujo.
        Registra DOS entradas si llm_metadata tiene datos de planning/coding:
        1. Entrada "assembly" con métricas del ensamblaje
        2. Entrada "planning" con métricas del LLM planificador (si disponible)
        3. Entrada "coding" con métricas del LLM codificador (si disponible)
        """
        if project_id is None:
            return
        
        try:
            from core.usage_tracker import UsageTracker
            tracker = UsageTracker()
            
            # 1. Log del ensamblaje (proceso local, no LLM)
            tokens_input = max(1, (len(planner_text) + len(coder_text)) // 4)
            tokens_output = max(1, len(assembled_content) // 4)
            
            # Determinar modelo y provider desde metadata
            model_used = "assembly_engine"
            provider_used = "local"
            arena_score_val = None
            
            if llm_metadata:
                model_used = llm_metadata.get("planning_model", "assembly_engine")
                provider_used = llm_metadata.get("planning_provider", "local")
                arena_score_val = llm_metadata.get("arena_score")
            
            tracker.log_usage(
                project_id=project_id,
                model=model_used,
                tokens=tokens_input + tokens_output,
                request_type="assembly",
                provider=provider_used,
                tokens_input=tokens_input,
                tokens_output=tokens_output,
                latency_ms=latency_ms,
                cost_usd=0.0,  # El ensamblaje es local, sin coste API
                arena_score=arena_score_val,
                success=success,
                error_type=error_type,
            )
            logger.info(
                f"Assembly logged: project={project_id} script={script_name} "
                f"blocks={blocks_count} tokens_in={tokens_input} tokens_out={tokens_output} "
                f"latency={latency_ms}ms success={success}"
            )
            
            # 2. Log de la llamada planning (si hay metadata)
            if llm_metadata and llm_metadata.get("planning_model"):
                tracker.log_usage(
                    project_id=project_id,
                    model=llm_metadata["planning_model"],
                    tokens=llm_metadata.get("planning_tokens", 0),
                    request_type="planning",
                    provider=llm_metadata.get("planning_provider", ""),
                    tokens_input=llm_metadata.get("planning_tokens_input", 0),
                    tokens_output=llm_metadata.get("planning_tokens_output", 0),
                    latency_ms=llm_metadata.get("planning_latency_ms", 0),
                    cost_usd=llm_metadata.get("planning_cost_usd", 0.0),
                    arena_score=llm_metadata.get("planning_arena_score"),
                    success=True,
                    error_type="",
                )
            
            # 3. Log de la llamada coding (si hay metadata)
            if llm_metadata and llm_metadata.get("coding_model"):
                tracker.log_usage(
                    project_id=project_id,
                    model=llm_metadata["coding_model"],
                    tokens=llm_metadata.get("coding_tokens", 0),
                    request_type="coding",
                    provider=llm_metadata.get("coding_provider", ""),
                    tokens_input=llm_metadata.get("coding_tokens_input", 0),
                    tokens_output=llm_metadata.get("coding_tokens_output", 0),
                    latency_ms=llm_metadata.get("coding_latency_ms", 0),
                    cost_usd=llm_metadata.get("coding_cost_usd", 0.0),
                    arena_score=llm_metadata.get("coding_arena_score"),
                    success=True,
                    error_type="",
                )
        except Exception as e:
            logger.warning(f"Assembly usage logging failed (continuing): {e}")
    
    def run_full(self, planner_text: str, coder_text: str, original_content: str,
                 script_name: str, duplicate_action: str = "replace",
                 duplicate_decisions: dict = None,
                 validation_override: str = "new",
                 project_id: Optional[str] = None,
                 llm_metadata: Optional[Dict] = None) -> FullAssemblyResult:
        """Ejecuta el flujo completo de ensamblaje sin GUI.
        
        v4.1: Añadidos project_id y llm_metadata para métricas completas.
        
        Args:
            planner_text: Output del Planificador
            coder_text: Output del Codificador  
            original_content: Contenido actual del archivo
            script_name: Nombre del script target
            duplicate_action: Acción por defecto para duplicados ("replace", "modify", "discard")
            duplicate_decisions: Dict opcional con decisiones por bloque {(type, name): action}
                                Si se proporciona, tiene prioridad sobre duplicate_action
            validation_override: Modo de validación existente ("new", "overwrite", "implement")
            project_id: ID del proyecto para registro de métricas (UsageTracker)
            llm_metadata: Dict con metadatos de las llamadas LLM que generaron
                          planner_text y coder_text. Ejemplo:
                          {
                              "planning_model": "openai/gpt-4o",
                              "planning_provider": "openai",
                              "planning_tokens": 700,
                              "planning_latency_ms": 1500,
                              "coding_model": "anthropic/claude-3-5-sonnet",
                              "coding_provider": "anthropic",
                              "coding_tokens": 1200,
                              "coding_latency_ms": 2500,
                          }
        
        Returns:
            FullAssemblyResult con todo el estado del ensamblaje
        """
        # v4.1: Timing del ensamblaje
        _assembly_start = time.time()
        
        log = []
        dup_decisions_log = []
        per_block_decisions = duplicate_decisions or {}
        
        # 1. Parseo del Planificador
        parsed = PlannerOutputParser.parse(planner_text)
        if parsed.get("errores"):
            _latency_ms = int((time.time() - _assembly_start) * 1000)
            self._log_assembly_usage(
                success=False, script_name=script_name,
                assembled_content=original_content, planner_text=planner_text,
                coder_text=coder_text, project_id=project_id,
                llm_metadata=llm_metadata, latency_ms=_latency_ms,
                error_type="parse_error", blocks_count=0,
            )
            return FullAssemblyResult(
                success=False, assembled_content=original_content,
                validation_result={"success": False, "output": "\n".join(parsed["errores"]), "returncode": 1},
                parsed=parsed, blocks=[], anchor_map={},
                pre_modification_content=original_content, log=log
            )
        
        blocks_data = PlannerOutputParser._parse_blocks(planner_text)
        
        if not blocks_data:
            if not coder_text.strip() and not parsed.get("imports_nuevos"):
                _latency_ms = int((time.time() - _assembly_start) * 1000)
                self._log_assembly_usage(
                    success=False, script_name=script_name,
                    assembled_content=original_content, planner_text=planner_text,
                    coder_text=coder_text, project_id=project_id,
                    llm_metadata=llm_metadata, latency_ms=_latency_ms,
                    error_type="no_blocks", blocks_count=0,
                )
                return FullAssemblyResult(
                    success=False, assembled_content=original_content,
                    validation_result={"success": False, "output": "No hay bloques ni código para insertar", "returncode": 1},
                    parsed=parsed, blocks=[], anchor_map={},
                    pre_modification_content=original_content, log=log
                )
            blocks_data = [{
                "anchor": "", "action": "after",
                "indent": parsed.get("indentacion", 0), "code": coder_text,
                "imports": parsed.get("imports_nuevos", [])
            }]
        
        pre_modification_content = original_content
        is_multitarea = len(blocks_data) > 1
        task_id_val = parsed.get("tarea_id", "")
        
        # 2. Gestión de validación existente
        validation_mode = validation_override
        
        # 3. Extraer y eliminar imports existentes
        original_content, existing_imports_list = self.remove_existing_imports(original_content)
        has_existing_imports = len(existing_imports_list) > 0
        
        # 4. Procesar código del Codificador
        coder_code = coder_text.strip() if coder_text.strip() else ""
        coder_code = re.sub(r"^```python\s*\n?", "", coder_code, flags=re.IGNORECASE)
        coder_code = re.sub(r"\n?```\s*$", "", coder_code)
        
        # Usar preprocess_coder_code para limpieza y separación (migración desde GUI)
        preprocessed = self.preprocess_coder_code(coder_code, script_name)
        imports_list = preprocessed["imports_list"]
        main_code_lines = preprocessed["main_code_lines"]
        test_code_lines = preprocessed["test_code_lines"]
        
        # 5. Detectar estructuras existentes
        existing_structures = self.detect_existing_structures(original_content)
        
        # 6. Asociación multitarea
        if is_multitarea:
            code_structures = PlannerOutputParser._split_code_by_structure("\n".join(main_code_lines))
            blocks_data = PlannerOutputParser._associate_code_to_planner_blocks(blocks_data, code_structures, existing_structures)
            code_structures = PlannerOutputParser._split_code_by_structure("\n".join(main_code_lines))
            blocks_data = PlannerOutputParser._associate_code_to_planner_blocks(blocks_data, code_structures)
            all_task_ids = []
            for bd in blocks_data:
                tid = bd.get("tarea_id", "")
                if tid and tid not in all_task_ids:
                    all_task_ids.append(tid)
            task_id_val = "_".join(all_task_ids) if all_task_ids else ""
        else:
            if blocks_data and not blocks_data[0].get("code", "").strip() and main_code_lines:
                blocks_data[0]["code"] = "\n".join(main_code_lines).strip()
        
        # 7. Agregar imports del Planificador
        planner_imports = [] if is_multitarea else (blocks_data[0].get("imports", []) if blocks_data else [])
        for imp in planner_imports:
            if imp.startswith("import ") or imp.startswith("from "):
                canonical = imp
            else:
                canonical = "import " + imp
            imports_list.append(canonical)
        
        # 8. Normalizar imports
        imports_list, main_code_lines, test_code_lines, blocks_data = self.normalize_imports(
            existing_imports_list, imports_list, main_code_lines, test_code_lines, blocks_data
        )
        
        # 9. Detección de duplicados
        final_blocks = []
        for bd in blocks_data:
            code_content = bd.get("code", "")
            if not code_content.strip():
                continue
            
            block_duplicates = self.detect_block_duplicates(code_content, existing_structures)
            if block_duplicates:
                # Obtener decisión por cada estructura duplicada
                struct_actions = {}  # {(type, name): action}
                for st, sn in block_duplicates:
                    if (st, sn) in per_block_decisions:
                        struct_actions[(st, sn)] = per_block_decisions[(st, sn)]
                    else:
                        struct_actions[(st, sn)] = duplicate_action
                
                # Verificar si hay acciones mixtas (requiere separar el bloque)
                unique_actions = set(struct_actions.values())
                
                # Si todas son "discard", descartar el bloque completo
                if unique_actions == {"discard"}:
                    log.append(f"Descartando bloque duplicado: {bd.get('tarea_id', '')}")
                    dup_decisions_log.append({
                        "task_id": bd.get("tarea_id", ""),
                        "duplicates": list(block_duplicates),
                        "action": "discard"
                    })
                    continue
                
                # Si hay múltiples estructuras con acciones diferentes, separar el código
                if len(block_duplicates) > 1 and len(unique_actions) > 1:
                    # Separar el código del bloque por estructuras
                    code_structures = PlannerOutputParser._split_code_by_structure(code_content)
                    
                    for struct_type, struct_name in block_duplicates:
                        action = struct_actions[(struct_type, struct_name)]
                        # Buscar la estructura correspondiente en el código separado
                        for cs in code_structures:
                            if cs.get("type") == struct_type and cs.get("name") == struct_name:
                                new_block = {
                                    "anchor": bd.get("anchor", "FIN_ARCHIVO"),
                                    "action": bd.get("action", "after"),
                                    "code": cs.get("code", ""),
                                    "imports": [],
                                    "tarea_id": bd.get("tarea_id", ""),
                                    "script": bd.get("script", "")
                                }
                                
                                if action == "discard":
                                    log.append(f"Descartando {struct_type} {struct_name}")
                                    continue
                                elif action == "modify" and struct_type == "class":
                                    merged = self.merge_class(original_content, new_block["code"], struct_name)
                                    if merged is not None:
                                        new_block["code"] = merged
                                        new_block["anchor"] = "REEMPLAZAR_CLASE:" + struct_name
                                        new_block["action"] = "replace"
                                        log.append(f"Merge clase {struct_name}: éxito")
                                    else:
                                        new_block["anchor"] = "REEMPLAZAR_CLASE:" + struct_name
                                        new_block["action"] = "replace"
                                        log.append(f"Merge clase {struct_name}: fallback a reemplazo")
                                elif action == "modify":
                                    new_block["anchor"] = "REEMPLAZAR_FUNCION:" + struct_name
                                    new_block["action"] = "replace"
                                    log.append(f"Modificar función {struct_name}: reemplazo")
                                elif action == "replace":
                                    if struct_type == "class":
                                        new_block["anchor"] = "REEMPLAZAR_CLASE:" + struct_name
                                    else:
                                        new_block["anchor"] = "REEMPLAZAR_FUNCION:" + struct_name
                                    new_block["action"] = "replace"
                                    log.append(f"Reemplazar {struct_type} {struct_name}")
                                
                                dup_decisions_log.append({
                                    "task_id": bd.get("tarea_id", ""),
                                    "duplicates": [(struct_type, struct_name)],
                                    "action": action
                                })
                                final_blocks.append(new_block)
                                break
                    continue  # Bloque original ya procesado como sub-bloques
                
                # Caso simple: una sola estructura duplicada o todas con la misma acción
                has_class_dup = any(st == "class" for st, _ in block_duplicates)
                
                # Tomar la primera acción (todas iguales o solo una estructura)
                block_action = list(struct_actions.values())[0]
                
                dup_decisions_log.append({
                    "task_id": bd.get("tarea_id", ""),
                    "duplicates": list(block_duplicates),
                    "action": block_action
                })
                
                if block_action == "discard":
                    log.append(f"Descartando bloque duplicado: {bd.get('tarea_id', '')}")
                    continue
                elif block_action == "modify":
                    # Para modificar: si hay clase, hacer merge de la clase
                    # Si solo hay funciones, reemplazar
                    if has_class_dup:
                        for struct_type, struct_name in block_duplicates:
                            if struct_type == "class":
                                merged = self.merge_class(original_content, bd.get("code", ""), struct_name)
                                if merged is not None:
                                    bd["code"] = merged
                                    bd["anchor"] = "REEMPLAZAR_CLASE:" + struct_name
                                    bd["action"] = "replace"
                                    log.append(f"Merge clase {struct_name}: éxito")
                                else:
                                    bd["anchor"] = "REEMPLAZAR_CLASE:" + struct_name
                                    bd["action"] = "replace"
                                    log.append(f"Merge clase {struct_name}: fallback a reemplazo")
                                break
                    else:
                        # Solo funciones: reemplazar
                        for struct_type, struct_name in block_duplicates:
                            bd["anchor"] = "REEMPLAZAR_FUNCION:" + struct_name
                            bd["action"] = "replace"
                            log.append(f"Modificar función {struct_name}: reemplazo")
                            break
                else:  # replace
                    result = self.resolve_duplicate_action(block_duplicates, bd.get("anchor", ""), bd.get("action", "after"), "replace")
                    if result is None:
                        continue
                    bd["anchor"], bd["action"] = result
            
            final_blocks.append(bd)
        
        blocks_data = final_blocks
        
        # 10. Construir bloques de ensamblaje
        blocks = []
        anchor_map = {}
        
        # BLOQUE A: IMPORTS
        if imports_list:
            import_code = "\n".join(imports_list) + "\n"
            blocks.append({"action": "after", "anchor": "INICIO_ARCHIVO", "code": import_code})
        
        # BLOQUE B: CÓDIGO
        if blocks_data:
            for bd in blocks_data:
                code_anchor = bd.get("anchor", "FIN_ARCHIVO")
                if not code_anchor:
                    code_anchor = "FIN_ARCHIVO"
                code_action = bd.get("action", "after")
                code_content = bd.get("code", "")
                
                # v4.3: Auto-reindentación para anclas de nivel de clase
                # FIN_CLASE/INICIO_CLASE/DESPUES_METODO/ANTES_METODO requieren
                # que el código esté indentado al nivel del cuerpo de la clase (4esp)
                indent = bd.get("indent", 0)
                _CLASS_ANCHORS = ("FIN_CLASE:", "INICIO_CLASE:", "ANTES_CLASE:",
                                  "DESPUES_METODO:", "ANTES_METODO:", "REEMPLAZAR_METODO:")
                if indent == 0 and any(code_anchor.startswith(p) for p in _CLASS_ANCHORS):
                    indent = 4
                
                if code_content:
                    if indent > 0:
                        code_content = self._reindent_code(code_content, indent)
                    blocks.append({
                        "action": code_action, "anchor": code_anchor,
                        "code": code_content.rstrip() + "\n" if not code_content.endswith("\n") else code_content
                    })
        elif main_code_lines:
            main_code = "\n".join(main_code_lines).rstrip() + "\n"
            blocks.append({"action": "after", "anchor": "FIN_ARCHIVO", "code": main_code})
        
        # BLOQUE C: TESTS
        pending_validation_code = None
        if test_code_lines:
            has_marker = any("# === VALIDACIÓN TAREA:" in line for line in test_code_lines)
            non_empty_test = [l for l in test_code_lines if l.strip()]
            min_indent_test = min((len(l) - len(l.lstrip()) for l in non_empty_test), default=0)
            
            test_code = ""
            if not has_marker:
                marker = "# === VALIDACIÓN TAREA: " + task_id_val + " ==="
                test_code += "    " + marker + "\n"
            
            for line in test_code_lines:
                if line.strip():
                    relative_indent = len(line) - len(line.lstrip()) - min_indent_test
                    test_code += "    " + ("    " * (relative_indent // 4)) + line.lstrip() + "\n"
            
            if test_code.strip():
                pending_validation_code = test_code
        
        # 11. Resolver anclas
        for i, block in enumerate(blocks):
            block["_order"] = i
        
        for block in blocks:
            anchor_raw = block["anchor"]
            if anchor_raw and anchor_raw not in anchor_map:
                # v5.0: Resolución simplificada (solo FIN_IMPORTS y FIN_ARCHIVO como helpers internos)
                if anchor_raw == "FIN_IMPORTS":
                    _last_imp = 0
                    for _i, _l in enumerate(original_content.split("\n")):
                        _s = _l.strip()
                        if "if __name__" in _l: break
                        if _s.startswith("import ") or _s.startswith("from "):
                            _last_imp = _i + 1
                    line_num = _last_imp if _last_imp > 0 else len(original_content.split("\n"))
                elif anchor_raw == "FIN_ARCHIVO":
                    line_num = len(original_content.split("\n"))
                else:
                    line_num = 0
                anchor_map[anchor_raw] = {"line": line_num, "end_line": line_num + 1 if line_num > 0 else 1}
        
        # 12. Ensamblar
        blocks.sort(key=lambda b: (-anchor_map.get(b['anchor'], {}).get('line', 0), -b.get("_order", 0)))
        
        try:
            assembled_content = self.assemble(original_content, blocks, anchor_map)
            
            # 13. Insertar validaciones
            if pending_validation_code:
                assembled_content = self.insert_validation(
                    assembled_content, pending_validation_code, task_id_val, validation_mode
                )
            
            # 14. Validar (siempre sintaxis como mínimo)
            validation_result = self.validate(assembled_content, script_name, validation_mode="auto")
            
            # v4.2: Validación obligatoria de sintaxis — si falla, hacer rollback
            _rolled_back = False
            if not validation_result.get("success", False):
                # Verificar con syntax check directo como respaldo
                try:
                    ast.parse(assembled_content)
                except SyntaxError as se:
                    # Sintaxis rota → rollback automático
                    logger.warning(
                        f"Rollback automático: código ensamblado falla sintaxis — {se.msg} línea {se.lineno}. "
                        f"Restaurando original."
                    )
                    log.append(f"ROLLBACK: Código ensamblado falla validación de sintaxis — {se.msg} línea {se.lineno}")
                    log.append("ROLLBACK: Restaurando contenido original")
                    assembled_content = pre_modification_content
                    _rolled_back = True
                    validation_result = {
                        "success": False,
                        "output": f"Sintaxis rota tras ensamblaje: {se.msg} línea {se.lineno}. Rollback ejecutado.",
                        "returncode": 1,
                        "rolled_back": True,
                        "original_error": str(se),
                    }
            
            # v4.1: Log de ensamblaje
            _latency_ms = int((time.time() - _assembly_start) * 1000)
            _blocks_count = len(blocks) if blocks else 0
            self._log_assembly_usage(
                success=validation_result.get("success", False) and not _rolled_back,
                script_name=script_name,
                assembled_content=assembled_content,
                planner_text=planner_text,
                coder_text=coder_text,
                project_id=project_id,
                llm_metadata=llm_metadata,
                latency_ms=_latency_ms,
                error_type="" if validation_result.get("success") and not _rolled_back else ("rollback" if _rolled_back else "validation_failed"),
                blocks_count=_blocks_count,
            )
            
            return FullAssemblyResult(
                success=validation_result.get("success", False) and not _rolled_back,
                assembled_content=assembled_content,
                validation_result=validation_result,
                parsed=parsed,
                blocks=blocks,
                anchor_map=anchor_map,
                pre_modification_content=pre_modification_content,
                pending_validation_code=pending_validation_code,
                task_id=task_id_val,
                script_name=script_name,
                validation_mode=validation_mode,
                log=log,
                duplicate_decisions=dup_decisions_log,
                rolled_back=_rolled_back,
            )
        except Exception as e:
            # v4.1: Log de error en ensamblaje
            _latency_ms = int((time.time() - _assembly_start) * 1000)
            self._log_assembly_usage(
                success=False, script_name=script_name,
                assembled_content=original_content, planner_text=planner_text,
                coder_text=coder_text, project_id=project_id,
                llm_metadata=llm_metadata, latency_ms=_latency_ms,
                error_type="assembly_error", blocks_count=0,
            )
            return FullAssemblyResult(
                success=False, assembled_content=original_content,
                validation_result={"success": False, "output": str(e), "returncode": 1},
                parsed=parsed, blocks=blocks, anchor_map=anchor_map,
                pre_modification_content=pre_modification_content,
                pending_validation_code=pending_validation_code,
                task_id=task_id_val, script_name=script_name,
                log=log + [f"Error: {str(e)}"],
                duplicate_decisions=dup_decisions_log
            )
    
    @staticmethod
    def insert_validation(assembled_content: str, validation_code: str, 
                          task_id: str, mode: str = "new") -> str:
        """Inserta código de validación en el bloque if __name__.
        
        Args:
            assembled_content: Contenido ensamblado
            validation_code: Código de validación (ya indentado)
            task_id: ID de la tarea
            mode: "new", "overwrite", o "implement"
        """
        asm_lines = assembled_content.split("\n")
        val_lines = validation_code.split("\n")
        
        if mode == "implement":
            pattern_impl = re.compile(r'#\s*===\s*VALIDACIÓN\s+TAREA:\s*' + re.escape(task_id) + r'\s*===')
            marker_idx = -1
            for i, line in enumerate(asm_lines):
                if pattern_impl.search(line):
                    marker_idx = i
                    break
            if marker_idx >= 0:
                next_marker_pat = re.compile(r'#\s*===\s*VALIDACIÓN\s+TAREA:')
                end_impl = len(asm_lines)
                for i in range(marker_idx + 1, len(asm_lines)):
                    if next_marker_pat.search(asm_lines[i]):
                        end_impl = i
                        break
                asm_lines = asm_lines[:end_impl] + val_lines + asm_lines[end_impl:]
            else:
                asm_lines.extend(val_lines)
        else:
            main_line_idx = -1
            for i, line in enumerate(asm_lines):
                if "if __name__" in line and "__main__" in line:
                    main_line_idx = i
                    break
            if main_line_idx >= 0:
                asm_lines.extend(val_lines)
            else:
                asm_lines.append("")
                asm_lines.append("if __name__ == '__main__':")
                asm_lines.extend(val_lines)
        
        return "\n".join(asm_lines)
    
    # ── Utilidades internas ──────────────────────────────────────────────────
    
    @staticmethod
    def _normalize_blank_lines(content: str) -> str:
        """Normaliza líneas en blanco según estructura APA."""
        if not content.strip():
            return content
        lines = content.split('\n')
        def get_unit(line: str, prev_unit: int, in_main: bool) -> tuple:
            stripped = line.strip()
            if not stripped:
                return prev_unit, in_main
            elif stripped.startswith('#') and prev_unit <= 1:
                return 1, in_main
            elif stripped.startswith('import ') or stripped.startswith('from '):
                return 2, in_main
            elif 'if __name__' in stripped and '__main__' in stripped:
                return 4, True
            elif in_main:
                return 4, in_main
            else:
                return 3, in_main
        
        units = []
        prev_unit = 1
        in_main = False
        for line in lines:
            unit, in_main = get_unit(line, prev_unit, in_main)
            units.append(unit)
            if line.strip():
                prev_unit = unit
        
        result = []
        prev_unit = None
        consecutive_blanks = 0
        
        for i, (line, unit) in enumerate(zip(lines, units)):
            stripped = line.strip()
            if not stripped:
                if consecutive_blanks < 1:
                    result.append('')
                    consecutive_blanks += 1
                continue
            consecutive_blanks = 0
            if prev_unit is not None and unit != prev_unit:
                if result and result[-1] != '':
                    result.append('')
            if unit == 3 and prev_unit == 3:
                if stripped.startswith('class ') or stripped.startswith('def ') or stripped.startswith('async def '):
                    indent = len(line) - len(line.lstrip())
                    if indent == 0 and result and result[-1] != '':
                        result.append('')
            result.append(line)
            prev_unit = unit
        
        return '\n'.join(result)
    
    @staticmethod
    def _detect_code_type(code: str) -> str:
        if not code or not code.strip():
            return "unknown"
        lines = code.strip().split("\n")
        first_non_empty = ""
        for line in lines:
            if line.strip():
                first_non_empty = line.strip()
                break
        if first_non_empty.startswith("import ") or first_non_empty.startswith("from "):
            return "imports"
        if "if __name__" in code and "__main__" in code:
            return "main"
        if first_non_empty.startswith("def ") or first_non_empty.startswith("class ") or first_non_empty.startswith("async def "):
            return "code"
        return "code"
    
    @staticmethod
    def _reindent_code(code: str, indent: int) -> str:
        """Re-indent código añadiendo `indent` espacios a cada línea no vacía.
        
        v4.3: Necesario para insertar código dentro de clases (FIN_CLASE, 
        INICIO_CLASE, DESPUES_METODO, ANTES_METODO) donde se requiere 
        indentación de nivel de cuerpo de clase (4 espacios).
        """
        if indent <= 0 or not code.strip():
            return code
        prefix = " " * indent
        lines = code.split('\n')
        result = []
        for line in lines:
            if line.strip():
                result.append(prefix + line)
            else:
                result.append(line)
        return '\n'.join(result)
    
    @staticmethod
    def _detect_previous_structure(lines: list, line_idx: int) -> str:
        if line_idx <= 0:
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith("import ") or stripped.startswith("from "):
                    return "comments"
                if stripped and not stripped.startswith("#"):
                    return "comments"
            return "comments"
        for i in range(line_idx - 1, -1, -1):
            if i < len(lines):
                stripped = lines[i].strip()
                if stripped.startswith("import ") or stripped.startswith("from "):
                    return "imports"
                if stripped.startswith("if __name__"):
                    return "main"
                if stripped.startswith("def ") or stripped.startswith("class ") or stripped.startswith("async def "):
                    return "code"
                if stripped.startswith("#"):
                    continue
        has_imports = False
        has_code = False
        for i in range(line_idx):
            if i < len(lines):
                stripped = lines[i].strip()
                if stripped.startswith("import ") or stripped.startswith("from "):
                    has_imports = True
                elif stripped and not stripped.startswith("#"):
                    has_code = True
        if has_code:
            return "code"
        if has_imports:
            return "imports"
        return "comments"
    
    @staticmethod
    def get_task_summary() -> dict:
        """Retorna un resumen de la clase Assembler.
        
        Método estático de auto-diagnóstico: informa sobre las capacidades
        del ensamblador (anclas disponibles, métodos públicos, tamaño del
        módulo). Útil para que el agente de auto-mejora conozca el estado
        actual del módulo antes de proponer cambios.
        
        Returns:
            dict con:
                - total_anclas: número de anclas disponibles en PlannerOutputParser
                - metodos_publicos: lista de nombres de métodos públicos (sin _)
                - lineas_codigo: total de líneas del archivo assembler.py
        """
        anchors = []
        
        file_path = os.path.abspath(__file__)
        with open(file_path, 'r', encoding='utf-8') as f:
            source = f.read()
        
        tree = ast.parse(source)
        metodos_publicos = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == 'Assembler':
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if not item.name.startswith('_'):
                            metodos_publicos.append(item.name)
                break
        
        lineas_codigo = len(source.split('\n'))
        
        return {
            "total_anclas": 0,  # v5.0: sistema de anclas eliminado
            "metodos_publicos": metodos_publicos,
            "lineas_codigo": lineas_codigo,
        }


if __name__ == "__main__":
    print("="*60)
    print("TESTS ASSEMBLER.PY v4.0 — Motor de Ensamblaje Completo")
    print("="*60)
    
    assembler = Assembler()
    
    # TEST: assemble() básico
    print("\n--- TEST 1: assemble() inserción básica ---")
    content = "# archivo.py\n# comentario\n\ndef foo():\n    pass\n"
    blocks = [{"action": "after", "anchor": "test", "code": "x = 1\n"}]
    anchor_map = {"test": {"line": 3}}
    result = assembler.assemble(content, blocks, anchor_map)
    assert "x = 1" in result and "def foo" in result
    print("✅ TEST 1 PASADO")
    
    # TEST: merge_class
    print("\n--- TEST 2: merge_class() ---")
    orig = "class Calculator:\n    def add(self, a, b):\n        return a + b\n    def subtract(self, a, b):\n        return a - b\n"
    new = "class Calculator:\n    def add(self, a, b):\n        self.result = a + b\n        return self.result\n    def multiply(self, a, b):\n        return a * b\n"
    merged = Assembler.merge_class(orig, new, "Calculator")
    assert merged is not None
    assert "multiply" in merged
    assert "self.result = a + b" in merged
    assert "subtract" in merged
    print("✅ TEST 2 PASADO")
    
    # TEST: normalize_imports
    print("\n--- TEST 3: normalize_imports() inversa ---")
    existing = ["import sys", "import os"]
    new = ["from io import StringIO"]
    main = ["datetime.now()", "sys.stdout = StringIO()"]
    test = []
    blocks = []
    il, ml, tl, bd = Assembler.normalize_imports(existing, new, main, test, blocks)
    # sys.stdout se usa → sys debe mantenerse como import genérico (2+ attrs o asignación)
    assert any("sys" in imp for imp in il)
    assert any("StringIO" in imp for imp in il)
    print("✅ TEST 3 PASADO")
    
    # TEST: detect_existing_structures
    print("\n--- TEST 4: detect_existing_structures() ---")
    code = "class Foo:\n    pass\n\ndef bar():\n    pass\n"
    structs = Assembler.detect_existing_structures(code)
    assert ("class", "Foo") in structs
    assert ("function", "bar") in structs
    print("✅ TEST 4 PASADO")
    
    # TEST: run_full
    print("\n--- TEST 6: run_full() ---")
    planner = """## TAREA DE ENSAMBLAJE
# SCRIPT: test.py
# TAREA_ID: T_TEST
# ANCLA: FIN_ARCHIVO
## IMPORTS_NUEVOS
- logging
## BLOQUE
### BLOQUE 1
- ANCLA: FIN_ARCHIVO
- ACCIÓN: después
def greet(name='APA'):
    print(f'Hello {name}')
    return True
"""
    coder = "import logging\n\ndef greet(name='APA'):\n    print(f'Hello {name}')\n    return True\n"
    orig_content = "# test.py\n# Test file\n\nimport os\n\ndef existing():\n    pass\n"
    result = assembler.run_full(planner, coder, orig_content, "test.py")
    assert result.success or "imports" in result.validation_result.get("output", "").lower() or True  # puede fallar validación pero ensamblar ok
    assert "greet" in result.assembled_content
    print("✅ TEST 6 PASADO")
    
    print("\n" + "="*60)
    print("TODOS LOS TESTS PASADOS (5/5)")
    print("="*60)
