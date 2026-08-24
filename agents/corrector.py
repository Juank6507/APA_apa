# apa/agents/corrector.py
# test
import sys
import os
import ast
import re
import logging
import traceback
import unicodedata
from typing import Optional
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from config.settings import settings
from core.router import call_llm, escalate_model
from core.error_handler import ErrorHandler as ErrorClassifier, ErrorComplexity, get_recommended_model
# provider_manager eliminado — Model Broker gestiona providers
from mcp.server import get_connector
logger = logging.getLogger(__name__)
logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)

# Patrones de clasificación de errores por lenguaje
ERROR_PATTERNS = {
    "python": [
        (r"SyntaxError", "syntax_error", "fix_syntax"),
        (r"NameError.*not defined", "undefined_name", "fix_import_or_typo"),
        (r"IndentationError", "indentation_error", "fix_indentation"),
        (r"TypeError.*object is not callable", "not_callable", "fix_callable"),
        (r"AttributeError.*has no attribute", "missing_attribute", "add_attribute"),
        # Patrones tkinter GUI
        (r"TclError.*no display", "tkinter_no_display", "fix_tkinter_headless"),
        (r"tkinter.*TclError", "tkinter_tcl_error", "fix_tkinter_error"),
        (r"_tkinter\..*TclError", "tkinter_binary_error", "fix_tkinter_error"),
        (r"time\.sleep.*blocking|mainloop.*blocked", "gui_blocking", "fix_gui_threading"),
        (r"can only be invoked from the main thread", "thread_safety_violation", "fix_gui_threading"),
    ],
    "javascript": [
        (r"SyntaxError: Unexpected token", "syntax_error", "fix_syntax"),
        (r"ReferenceError.*is not defined", "undefined_variable", "fix_undefined"),
        (r"TypeError: Cannot read propert", "null_access", "add_null_check"),
        (r"TypeError: .* is not a function", "not_a_function", "fix_function_call"),
    ],
    "bash": [
        (r"command not found", "missing_command", "install_or_replace"),
        (r"syntax error near unexpected token", "syntax_error", "fix_syntax"),
        (r"unbound variable", "unbound_var", "quote_or_default"),
        (r"permission denied", "permission_error", "fix_permissions"),
    ],
    "sql": [
        (r"near \".*\" syntax error", "syntax_error", "fix_sql_syntax"),
        (r"no such table", "missing_table", "create_table"),
        (r"column .* does not exist", "missing_column", "add_column"),
        (r"constraint failed", "constraint_error", "fix_constraint"),
    ],
    "cpp": [
        (r"error: expected ';' before", "missing_semicolon", "add_semicolon"),
        (r"error: '.*' was not declared", "undeclared_identifier", "add_include_or_declare"),
        (r"error: no matching function", "wrong_signature", "fix_signature"),
        (r"error: expected primary-expression", "expression_error", "fix_expression"),
    ],
    "dart": [
        (r"Error: Expected ';'", "missing_semicolon", "add_semicolon"),
        (r"Error: Undefined name", "undefined_name", "fix_import_or_declare"),
        (r"Error: The method '.*' isn't defined", "undefined_method", "add_method_or_import"),
        (r"Error: A value of type .* can't be assigned", "type_mismatch", "fix_type"),
    ],
    "react-native": [
        (r"SyntaxError: Unexpected token", "syntax_error", "fix_syntax"),
        (r"ReferenceError.*is not defined", "undefined_variable", "fix_undefined"),
        (r"TypeError: Cannot read propert", "null_access", "add_null_check"),
    ]
}

def _task_name_to_filename(name: str) -> str:
    normalized = unicodedata.normalize('NFKD', name)
    ascii_str = normalized.encode('ascii', 'ignore').decode('ascii')
    slug = re.sub(r'[^a-zA-Z0-9\s]', '', ascii_str)
    slug = re.sub(r'\s+', '', slug.strip()).lower()
    if not slug:
        slug = "generated_code"
    return f"{slug}.py"

class CorrectorAgent:
    def __init__(self):
        # Resiliente: si el sandbox (NAS/VM/external) no responde, no se
        # cae el constructor. self.nas queda None y las operaciones que
        # requieren sandbox se saltan con un warning.
        try:
            self.nas = get_connector()
        except Exception as exc:
            logger.warning(
                "CorrectorAgent: sandbox no disponible (%s). "
                "Las operaciones que requieren sandbox se omitirán.", exc
            )
            self.nas = None
        self.error_classifier = ErrorClassifier()

    def _clean_code_response(self, text: str) -> str:
        if text is None or not isinstance(text, str):
            return ""
        cleaned = text.strip()
        if not cleaned:
            return ""
        cleaned = re.sub(r'^```python\s*', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'^```\s*', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s*```$', '', cleaned, flags=re.IGNORECASE)
        return cleaned.strip()

    def _classify_error_by_language(self, stderr: str, stdout: str, language: str) -> tuple:
        """Clasifica errores de forma granular según patrones por lenguaje."""
        combined = f"{stderr} {stdout}".lower()
        patterns = ERROR_PATTERNS.get(language, [])
        for pattern, error_type, strategy in patterns:
            if re.search(pattern, combined, re.IGNORECASE):
                # Extraer detalles adicionales si es posible
                match = re.search(pattern, combined, re.IGNORECASE)
                details = match.group(0) if match else "Error detectado por patrón"
                return error_type, strategy, details
        return "unknown", "rewrite", "No se detectó patrón conocido"

    def analyze_error(self, code: str, execution_result: dict, task: dict) -> dict:
        logger.info(f"Analyzing error for task: {task.get('id')}")
        error_type = "unknown"
        error_message = ""
        strategy = "rewrite"
        details = ""
        language = task.get("language", "python")

        try:
            if language == "python":
                ast.parse(code)
            has_syntax_error = False
        except SyntaxError as e:
            has_syntax_error = True
            error_type = "syntax_error"
            error_message = f"Line {e.lineno}: {e.msg}"
            strategy = "fix_syntax"
            details = f"Syntax error at line {e.lineno}"

        if not has_syntax_error:
            stderr = execution_result.get("stderr", "")
            stdout = execution_result.get("stdout", "")
            nas_success = execution_result.get("nas_success", True)

            # Clasificación granular por lenguaje
            granular_type, granular_strategy, granular_details = self._classify_error_by_language(stderr, stdout, language)
            
            if granular_type != "unknown":
                error_type = granular_type
                strategy = granular_strategy
                details = granular_details
                error_message = stderr.strip() or stdout.strip() or "Error detectado"
            elif not nas_success:
                error_type = "nas_error"
                error_message = stderr or "NAS execution failed"
                strategy = "retry_execution"
                details = "Error executing in sandbox"
            elif stderr and ("Traceback" in stderr or "Error" in stderr):
                error_type = "runtime_error"
                lines = stderr.strip().split('\n')
                error_message = '\n'.join(lines[-5:])
                strategy = "fix_runtime"
                details = "Runtime exception during execution"
            elif "CRITERIO FALLO" in stdout:
                error_type = "criterion_failed"
                for line in stdout.split('\n'):
                    if "CRITERIO FALLO" in line:
                        error_message = line.strip()
                        break
                strategy = "fix_logic"
                details = "Code runs but does not meet acceptance criterion"
            else:
                error_type = "unknown"
                error_message = "No specific error identified"
                strategy = "rewrite"
                details = f"stdout: {stdout[:200]}, stderr: {stderr[:200]}"

        logger.info(f"Error analysis: type={error_type}, strategy={strategy}, language={language}")
        return {
            "error_type": error_type,
            "error_message": error_message,
            "strategy": strategy,
            "details": details,
            "language": language
        }

    def _build_fix_prompt_with_dependencies(self, task: dict, code: str, error_message: str, attempt: int) -> str:
        dep_codes = task.get("dependency_codes", {})
        dep_context = ""
        for path, dep_code in dep_codes.items():
            dep_context += f"### Código de {path}\n```python\n{dep_code}\n```\n\n"
        prompt = (
            f"Tarea original: {task.get('name')}\n"
            f"Descripción: {task.get('description')}\n"
            f"Criterio de aceptación: {task.get('acceptance_criterion')}\n\n"
            f"{dep_context}\n"
            f"Código actual que no cumple el criterio:\n```python\n{code}\n```\n\n"
            f"El problema: {error_message}\n\n"
            f"Reescribe el código para que:\n"
            f"1. Implemente correctamente las funciones descritas.\n"
            f"2. Utilice las funciones de los módulos dependientes (importándolos).\n"
            f"3. Maneje correctamente los casos de error (lanzando excepciones cuando corresponda).\n"
            f"4. Incluya un bloque __main__ que demuestre el funcionamiento y muestre 'CRITERIO OK'.\n\n"
            f"Responde ÚNICAMENTE con el código Python corregido. "
        )
        return prompt

    def _call_ollama_for_simple_correction(self, model_id: str, system_prompt: str, user_prompt: str, max_tokens: int, temperature: float) -> dict:
        """Corrección simple vía call_llm (Model Broker gestiona el provider)."""
        try:
            result = call_llm(
                task_type="correction",
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=max_tokens,
                temperature=temperature
            )
            return result
        except Exception as e:
            logger.error(f"Simple correction call failed: {e}")
            return {"success": False, "error": str(e), "content": "", "model_used": model_id}

    def correct(self, task: dict, code: str, execution_result: dict,
                attempt: int, current_model: str = None, project_id: Optional[str] = None) -> dict:
        logger.info(f"Correcting code for task {task.get('id')}, attempt {attempt + 1}")
        try:
            analysis = self.analyze_error(code, execution_result, task)
            error_type = analysis["error_type"]
            strategy = analysis["strategy"]
            error_message = analysis["error_message"]
            details = analysis.get("details", "")
            language = analysis.get("language", "python")

            if attempt >= 2:
                if current_model:
                    current_model = escalate_model(current_model)
                else:
                    current_model = None  # Model Broker selecciona automáticamente
                logger.info(f"Escalated to model: {current_model}")

            if attempt == 0:
                if task.get("depends_on") and error_type == "unknown":
                    strategy = "fix_with_dependencies"
                else:
                    strategy = analysis["strategy"]
            elif attempt == 1:
                strategy = "rewrite"
            else:
                strategy = "simplify"

            system_prompts = {
                "fix_syntax": f"Eres un experto en {language}. Corrige ÚNICAMENTE los errores de sintaxis del código proporcionado. No cambies la lógica. Responde SOLO con el código corregido, sin explicaciones ni markdown.",
                "fix_runtime": f"Eres un experto en debugging {language}. Analiza el error de ejecución y corrige el código. Mantén la misma lógica pero corrige el error específico. Responde SOLO con el código corregido.",
                "fix_logic": f"Eres un experto en {language}. El código se ejecuta pero no cumple el criterio de aceptación. Corrige la lógica para que cumpla exactamente el criterio. Responde SOLO con el código corregido.",
                "retry_execution": f"Eres un experto en {language}. Reescribe completamente el código para cumplir el objetivo. El código debe ser simple, correcto y autocontenido. Responde SOLO con el código.",
                "rewrite": f"Eres un experto en {language}. Reescribe completamente el código para cumplir el objetivo. El código debe ser simple, correcto y autocontenido. Responde SOLO con el código.",
                "fix_with_dependencies": f"Eres un experto en {language}. Revisa las dependencias y corrige el código para que cumpla la especificación. Responde SOLO con el código corregido.",
                "simplify": f"Eres un experto en {language}. Implementa la solución más simple posible que cumpla el criterio de aceptación. Sin clases innecesarias, sin imports externos, sin abstracción prematura. Solo lo esencial.",
                "fix_import_or_typo": f"Eres un experto en {language}. Corrige nombres no definidos añadiendo imports faltantes o corrigiendo typos. Responde SOLO con el código corregido.",
                "fix_indentation": f"Eres un experto en {language}. Corrige errores de indentación manteniendo la lógica original. Responde SOLO con el código corregido.",
                "add_null_check": f"Eres un experto en {language}. Añade verificaciones de null/undefined para prevenir errores de acceso. Responde SOLO con el código corregido.",
                "add_semicolon": f"Eres un experto en {language}. Añade puntos y coma faltantes según la sintaxis del lenguaje. Responde SOLO con el código corregido.",
                "add_include_or_declare": f"Eres un experto en {language}. Añade includes/imports faltantes o declara identificadores no definidos. Responde SOLO con el código corregido.",
                "fix_signature": f"Eres un experto en {language}. Corrige firmas de funciones para que coincidan con las llamadas. Responde SOLO con el código corregido.",
                # Estrategias específicas de GUI/tkinter
                "fix_tkinter_headless": f"Eres un experto en Python/tkinter. El código falla porque no hay display disponible. Añade soporte para ejecución sin display: envuelve la creación de Tk() en un try/except y usa una bandera para detectar modo headless. Si no hay display, usa valores por defecto o imprime resultados en consola. Responde SOLO con el código corregido.",
                "fix_tkinter_error": f"Eres un experto en Python/tkinter. Corrige el error de TclError en código tkinter. Verifica que los widgets se crean DESPUÉS de tk.Tk(), que las variables tk.StringVar/IntVar se usen correctamente, y que no se acceda a widgets destruidos. Responde SOLO con el código corregido.",
                "fix_gui_threading": f"Eres un experto en Python/tkinter y concurrencia. El código tiene operaciones que bloquean el mainloop de tkinter. Mueve las operaciones largas (time.sleep, bucles, solicitudes de red) a un hilo separado con threading.Thread(daemon=True) y usa widget.after() para actualizar la UI desde el hilo principal. Usa queue.Queue para comunicar datos entre threads. Responde SOLO con el código corregido.",
                "fix_callable": f"Eres un experto en {language}. Corrige el error donde un objeto no es callable. Verifica que los métodos existan y que no se esté llamando a una propiedad como función. En tkinter, verifica que los callbacks sean funciones válidas (no el resultado de llamarlas). Responde SOLO con el código corregido.",
                "add_attribute": f"Eres un experto en {language}. El código intenta acceder a un atributo que no existe. En tkinter, esto suele pasar con widgets que no tienen el método esperado (ej: Listbox no tiene get_selected, usar textbox_filtro.get() en su lugar). Responde SOLO con el código corregido.",
            }
            system_prompt = system_prompts.get(strategy, system_prompts["rewrite"])

            # Prompt enriquecido con clasificación granular
            error_context = f"Tipo de error: {error_type}\n"
            if details and details != "No se detectó patrón conocido":
                error_context += f"Detalles: {details}\n"
            error_context += f"Mensaje: {error_message}\n"

            user_prompt = (
                f"Tarea original: {task.get('name')}\n"
                f"Criterio de aceptación: {task.get('acceptance_criterion')}\n"
                f"Lenguaje: {language}\n\n"
                f"Código con error:\n```{language}\n{code}\n```\n\n"
                f"Análisis del error:\n{error_context}\n"
                f"Estrategia de corrección: {strategy}\n"
                f"Intento: {attempt + 1}/3\n\n"
                f"Genera el código corregido que:\n"
                f"1. Corrija el error indicado ({error_type})\n"
                f"2. Cumpla el criterio de aceptación\n"
                f"3. Incluya bloque __main__ con test que imprima\n"
                f"   'CRITERIO OK' si pasa o 'CRITERIO FALLO: detalle'\n\n"
                f"Responde ÚNICAMENTE con código {language}. "
            )

            if strategy == "fix_with_dependencies":
                user_prompt = self._build_fix_prompt_with_dependencies(task, code, error_message, attempt)

            if task.get("dependency_codes"):
                dep_context = "\n\n".join([
                    f"### Código del archivo del que depende: {dep_path}\n```{language}\n{dep_code}\n```"
                    for dep_path, dep_code in task["dependency_codes"].items()
                ])
                user_prompt = f"{dep_context}\n\n{user_prompt}"
                user_prompt += (
                    f"\n\nINSTRUCCIÓN CRÍTICA SOBRE IMPORTS:\n"
                    f"Este código se ejecutará como script AISLADO. No puede importar desde otros archivos\n"
                    f"del proyecto. Si necesitas funcionalidad de las dependencias mostradas arriba, COPIA las funciones\n"
                    f"necesarias directamente en este archivo. No uses ningún import relativo ni absoluto hacia otros\n"
                    f"módulos del proyecto."
                )
                logger.debug(f"Injected dependency context for task {task.get('id')}")

            llm_result = None
            if attempt == 0:
                error_text = f"{execution_result.get('stderr', '')} {execution_result.get('stdout', '')}".strip()
                complexity = self.error_classifier.classify(error_text, code, execution_result)
                if complexity == ErrorComplexity.SIMPLE:
                    model_id = get_recommended_model(ErrorComplexity.SIMPLE, "correction")
                    logger.info(f"Simple error correction via call_llm (model hint: {model_id})")
                    llm_result = self._call_ollama_for_simple_correction(
                        model_id=model_id,
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        max_tokens=3000,
                        temperature=0.1
                    )
                    if not llm_result.get("success"):
                        logger.warning(f"Simple correction failed, falling back to normal flow: {llm_result.get('error')}")
                        llm_result = None

            if llm_result is None:
                # current_model es None → call_llm delega a Model Broker
                llm_result = call_llm(
                    task_type="correction",
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=3000,
                    temperature=0.1,
                    project_id=project_id
                )

            content = llm_result.get("content")
            if content is None or (isinstance(content, str) and not content.strip()):
                logger.warning(f"LLM returned empty or None content: {llm_result}")
                return {
                    "task_id": task.get("id"),
                    "code": "",
                    "filename": _task_name_to_filename(task.get("name", "")),
                    "is_valid_syntax": False,
                    "model_used": llm_result.get("model_used", ""),
                    "provider_used": llm_result.get("provider_used", ""),
                    "strategy": strategy,
                    "error_type": error_type,
                    "attempt": attempt + 1,
                    "success": False,
                    "error": "Empty LLM response"
                }

            if not llm_result.get("success"):
                logger.error(f"LLM call failed in correction: {llm_result.get('error')}")
                return {
                    "task_id": task.get("id"),
                    "code": "",
                    "filename": _task_name_to_filename(task.get("name", "")),
                    "is_valid_syntax": False,
                    "model_used": llm_result.get("model_used", ""),
                    "provider_used": llm_result.get("provider_used", ""),
                    "strategy": strategy,
                    "error_type": error_type,
                    "attempt": attempt + 1,
                    "success": False,
                    "error": llm_result.get("error", "LLM call failed")
                }

            corrected_code = self._clean_code_response(llm_result["content"])
            filename = _task_name_to_filename(task.get("name", ""))

            is_valid = False
            try:
                if language == "python":
                    ast.parse(corrected_code)
                is_valid = True
            except SyntaxError as e:
                logger.warning(f"Corrected code has syntax error: {e}")

            logger.info(f"Correction generated, valid_syntax={is_valid}")

            return {
                "task_id": task.get("id"),
                "code": corrected_code,
                "filename": filename,
                "is_valid_syntax": is_valid,
                "model_used": llm_result.get("model_used", ""),
                "provider_used": llm_result.get("provider_used", ""),
                "strategy": strategy,
                "error_type": error_type,
                "attempt": attempt + 1,
                "success": True
            }

        except Exception as e:
            logger.error(f"Error in correct: {e}")
            return {
                "task_id": task.get("id"),
                "code": "",
                "filename": _task_name_to_filename(task.get("name", "")),
                "is_valid_syntax": False,
                "model_used": "",
                "provider_used": "",
                "strategy": "unknown",
                "error_type": "exception",
                "attempt": attempt + 1,
                "success": False,
                "error": str(e)
            }

    def correction_loop(self, task: dict, initial_code: str,
                        initial_execution: dict, max_attempts: int = 3) -> dict:
        logger.info(f"Starting correction loop for task: {task.get('id')}")
        project_id = task.get("project_id")
        try:
            current_code = initial_code
            current_execution = initial_execution
            current_model = None
            history = []
            filename = _task_name_to_filename(task.get("name", ""))

            for attempt in range(max_attempts):
                if "CRITERIO OK" in current_execution.get("stdout", ""):
                    logger.info(f"Criterion already passed, returning success")
                    return {
                        "task_id": task.get("id"),
                        "success": True,
                        "code": current_code,
                        "filename": filename,
                        "final_execution": current_execution,
                        "attempts_used": attempt,
                        "history": history,
                        "diagnosis": "Corregido exitosamente"
                    }

                logger.info(f"Intento de corrección {attempt + 1}/{max_attempts}")
                correction_result = self.correct(
                    task, current_code, current_execution, attempt, current_model, project_id=project_id
                )

                if not correction_result.get("success"):
                    history.append({
                        "attempt": attempt + 1,
                        "strategy": correction_result.get("strategy", "unknown"),
                        "error_type": correction_result.get("error_type", "unknown"),
                        "model_used": correction_result.get("model_used", ""),
                        "provider_used": correction_result.get("provider_used", ""),
                        "criterion_passed": False,
                        "stdout": "",
                        "stderr": correction_result.get("error", "Failed to generate correction"),
                        "status": "failed_to_generate"
                    })
                    continue

                if self.nas is not None:
                    new_execution = self.nas.execute_code(correction_result["code"])
                else:
                    logger.warning("CorrectorAgent: NAS no disponible — omitiendo ejecución de corrección")
                    new_execution = {"stdout": "", "stderr": "Sandbox no disponible", "success": False}
                criterion_passed = "CRITERIO OK" in new_execution.get("stdout", "")

                history.append({
                    "attempt": attempt + 1,
                    "strategy": correction_result["strategy"],
                    "error_type": correction_result["error_type"],
                    "model_used": correction_result["model_used"],
                    "provider_used": correction_result["provider_used"],
                    "criterion_passed": criterion_passed,
                    "stdout": new_execution.get("stdout", ""),
                    "stderr": new_execution.get("stderr", "")
                })

                current_code = correction_result["code"]
                current_execution = new_execution
                current_model = correction_result["model_used"]

                if criterion_passed:
                    logger.info(f"Criterion passed on attempt {attempt + 1}")
                    return {
                        "task_id": task.get("id"),
                        "success": True,
                        "code": current_code,
                        "filename": filename,
                        "final_execution": current_execution,
                        "attempts_used": attempt + 1,
                        "history": history,
                        "diagnosis": "Corregido exitosamente"
                    }

            diagnosis = self._generate_diagnosis(history, current_execution)
            logger.warning(f"Correction loop failed after {max_attempts} attempts: {diagnosis}")

            return {
                "task_id": task.get("id"),
                "success": False,
                "code": current_code,
                "filename": filename,
                "final_execution": current_execution,
                "attempts_used": max_attempts,
                "history": history,
                "diagnosis": diagnosis
            }

        except Exception as e:
            logger.error(f"Error in correction_loop: {e}")
            return {
                "task_id": task.get("id"),
                "success": False,
                "code": "",
                "filename": _task_name_to_filename(task.get("name", "")),
                "final_execution": {"stdout": "", "stderr": str(e), "nas_success": False},
                "attempts_used": 0,
                "history": [],
                "diagnosis": f"Exception in correction loop: {str(e)}"
            }

    def _generate_diagnosis(self, history: list, final_execution: dict) -> str:
        if not history:
            return "No correction attempts were made"
        last_entry = history[-1]
        error_type = last_entry.get("error_type", "unknown")
        strategy = last_entry.get("strategy", "unknown")
        diagnoses = {
            "syntax_error": "El código generado tenía errores de sintaxis que no pudieron corregirse automáticamente",
            "runtime_error": "El código causaba errores de ejecución que persistieron tras múltiples intentos",
            "criterion_failed": "El código se ejecutaba pero no cumplía el criterio de aceptación; la lógica no pudo corregirse",
            "nas_error": "Error al ejecutar el código en el sandbox del NAS",
            "unknown": "No se pudo identificar una estrategia de corrección efectiva",
            "fix_with_dependencies": "El código no pudo corregirse incluso con contexto de dependencias",
            "simplify": "El código no pudo simplificarse lo suficiente para cumplir el criterio",
            "undefined_name": "No se pudo resolver el nombre no definido tras múltiples intentos",
            "missing_semicolon": "No se pudo añadir el punto y coma faltante correctamente",
            "null_access": "No se pudo añadir la verificación de null/undefined necesaria",
        }
        base_diagnosis = diagnoses.get(error_type, diagnoses["unknown"])
        if len(history) >= 3:
            strategies_tried = set(h.get("strategy") for h in history)
            base_diagnosis += f". Estrategias intentadas: {', '.join(strategies_tried)}"
        return base_diagnosis


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_task = {
        "id": "T1",
        "name": "Implement sum function",
        "description": "Implementa suma(a, b) que retorna a + b",
        "inputs": ["a: int", "b: int"],
        "expected_output": "Función suma que retorna a + b",
        "acceptance_criterion": "suma(2, 3) retorna 5",
        "task_type": "generation",
        "status": "pending",
        "attempts": 0,
        "result": None,
        "model_used": None
    }
    print("=== PRUEBA 1: analyze_error con código con error lógico ===")
    bad_code = """
def suma(a, b):
    return a - b  # error intencional
if __name__ == '__main__':
    resultado = suma(2, 3)
    if resultado == 5:
        print('CRITERIO OK')
    else:
        print(f'CRITERIO FALLO: esperado 5, obtenido {resultado}')
"""
    # Resiliente: si el sandbox no responde, usar mock de execution
    try:
        nas = get_connector()
        execution = nas.execute_code(bad_code)
    except Exception as exc:
        import logging as _logging
        _logging.getLogger(__name__).warning(
            "corrector.py __main__: sandbox no disponible (%s). Usando mock de execution.", exc
        )
        execution = {
            "stdout": "CRITERIO FALLO: esperado 5, obtenido -1",
            "stderr": "NameError: name 'suma' is not defined",
            "nas_success": False,
            "criterion_passed": False,
        }
    agent = CorrectorAgent()
    analysis = agent.analyze_error(bad_code, execution, test_task)
    print(f"error_type: {analysis['error_type']}")
    print(f"strategy: {analysis['strategy']}")
    print(f"error_message: {analysis['error_message']}")
    print("ANALYZE OK" if analysis['error_type'] != 'unknown' else "ANALYZE: tipo desconocido")
    print("\n=== PRUEBA 2: correction_loop completo ===")
    execution_with_error = {
        "stdout": "CRITERIO FALLO: esperado 5, obtenido -1",
        "stderr": "",
        "nas_success": True,
        "criterion_passed": False
    }
    result = agent.correction_loop(test_task, bad_code, execution_with_error)
    print(f"\ncorrection success: {result['success']}")
    print(f"attempts used: {result['attempts_used']}")
    print(f"diagnosis: {result['diagnosis']}")
    if result['success']:
        print(f"--- CÓDIGO CORREGIDO ---")
        print(result['code'])
        print(f"--- FIN ---")
        print("CORRECTION_LOOP OK")
    else:
        print("CORRECTION_LOOP: no pudo corregir")
        for h in result['history']:
            print(f"  Intento {h['attempt']}: strategy={h['strategy']} passed={h['criterion_passed']}")
    print("\n=== PRUEBA B2: Corrección simple de errores ===")
    def test_b2_simple_error():
        from core.error_handler import ErrorHandler as ErrorClassifier, ErrorComplexity
        import logging
        logging.basicConfig(level=logging.INFO)
        agent = CorrectorAgent()
        bad_code = "def foo()\n    return 1"
        execution = {"stdout": "", "stderr": "SyntaxError: invalid syntax", "nas_success": True}
        task = {"id": "test", "name": "syntax error test", "acceptance_criterion": "..."}
        complexity = agent.error_classifier.classify(execution["stderr"], bad_code)
        assert complexity == ErrorComplexity.SIMPLE
        print(f"Error clasificado como SIMPLE: {complexity}")
        result = agent.correct(task, bad_code, execution, attempt=0)
        provider = (result.get("provider_used") or "mb").lower()
        model = result.get("model_used", "unknown")
        print(f"B2: provider={provider}, model={model}")
        result2 = agent.correct(task, bad_code, execution, attempt=1)
        assert result2 is not None
        print("B2 VALIDATION OK")
    test_b2_simple_error()