# apa/core/spec_builder.py
import sys
import os
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Any

# Añadir el directorio padre al path para permitir imports relativos al ejecutar directamente
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from core.router import call_llm

# TDM (Tech Domain Map) — Decisiones 1+2 del Director:
# la recomendación de stack tecnológico se muestra SIEMPRE al usuario
# (nunca se aplica de forma silenciosa) y aparece en el SDD generado,
# para que el usuario pueda revisarla ANTES de ejecutar nada.
try:
    from core.tech_domain_map import recommend_language as _tdm_recommend_language
except Exception:  # pragma: no cover — fallback defensivo
    logging.getLogger(__name__).warning(
        "spec_builder: tech_domain_map no disponible", exc_info=True
    )
    def _tdm_recommend_language(_text: str) -> dict:  # type: ignore[no-redef]
        return {"language": "", "framework": "", "notes": "", "confidence": "low"}

logger = logging.getLogger(__name__)


class SpecBuilder:
    """
    Clase responsable de convertir una conversación de chat en una especificación
    de proyecto en formato Markdown compatible con APA.
    """

    def __init__(self):
        """Inicializa el SpecBuilder con el system prompt para generación de specs."""
        self.system_prompt = """
Eres un asistente especializado en extraer especificaciones de proyectos software a partir de conversaciones.
Analiza la conversación proporcionada y genera una especificación en formato Markdown con las siguientes secciones:
Título del proyecto (inventa uno descriptivo)
Objetivo: (qué debe hacer el proyecto)
Inputs: (lista de entradas, tipos, formatos)
Output esperado: (qué produce el sistema)
Criterio de éxito: (cómo verificar que funciona correctamente)
Si se mencionan múltiples archivos, añade una sección "Archivos:" con una lista de rutas y descripciones breves.
Responde ÚNICAMENTE con el contenido Markdown de la especificación, sin explicaciones adicionales.
"""

    def build_spec(self, conversation_history: List[Dict[str, str]], maturity_summary: str = "") -> str:
        """
        A partir del historial de chat, genera una especificación en formato Markdown.
        
        Args:
            conversation_history: Lista de dicts con keys "role" y "content".
            maturity_summary: Resumen textual de los 18 aspectos de madurez (opcional).
            
        Returns:
            str: Contenido Markdown de la especificación generada.
            
        Raises:
            ValueError: Si conversation_history está vacío.
            RuntimeError: Si el LLM falla o retorna contenido vacío.
        """
        if not conversation_history:
            raise ValueError("conversation_history no puede estar vacío")
        
        # 1. Formatear la conversación como texto legible
        conversation_text = ""
        for msg in conversation_history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "user":
                conversation_text += f"Usuario: {content}\n"
            elif role == "assistant":
                conversation_text += f"Asistente: {content}\n"
        
        # 2. Construir prompt: conversación + resumen de madurez si existe
        user_prompt_parts = [f"Conversación:\n{conversation_text}"]
        if maturity_summary:
            user_prompt_parts.append(f"\n\n{maturity_summary}")

        # ── Decisiones 1+2 del Director (TDM) ──────────────────────────
        # Mostrar el stack recomendado ANTES de generar el SDD para que el
        # usuario lo vea, y siempre explicando el porqué (persuasivo). La
        # recomendación se computa aquí (no se aplica en silencio) y se
        # incluye en el prompt del LLM para que forme parte de la spec
        # generada como una sección visible para el usuario.
        try:
            tdm_rec = _tdm_recommend_language(conversation_text)
            tdm_lang = tdm_rec.get("language", "")
            tdm_fw = tdm_rec.get("framework", "")
            tdm_notes = tdm_rec.get("notes", "")
            tdm_conf = tdm_rec.get("confidence", "")
        except Exception as exc:
            logger.debug(f"TDM recommend_language falló en build_spec: {exc}")
            tdm_lang = tdm_fw = tdm_notes = tdm_conf = ""

        if tdm_lang:
            stack_block_lines = [
                "",
                "── RECOMENDACIÓN DE STACK TECNOLÓGICO (APA · TDM) ──",
                f"  Lenguaje recomendado : {tdm_lang}",
            ]
            if tdm_fw:
                stack_block_lines.append(f"  Framework recomendado: {tdm_fw}")
            if tdm_notes:
                stack_block_lines.append(f"  Razones              : {tdm_notes}")
            stack_block_lines.append(
                "  Confianza            : " + (tdm_conf or "desconocida")
            )
            stack_block_lines.append(
                "APA recomienda este stack porque encaja con el tipo de proyecto "
                "descrito en la conversación. Si prefieres otra tecnología, "
                "indícalo en tu respuesta y APA te explicará las ventajas y "
                "desventajas de tu elección antes de continuar."
            )
            stack_block_lines.append(
                "Incluye SIEMPRE esta recomendación como una sección "
                "'## Stack Tecnológico Recomendado' al inicio de la spec "
                "generada, para que el usuario la vea ANTES de cualquier "
                "tarea de implementación."
            )
            stack_block_lines.append("── FIN RECOMENDACIÓN ──")
            user_prompt_parts.append("\n".join(stack_block_lines))

        full_prompt = "\n".join(user_prompt_parts)

        # 3. Llamar al LLM
        result = call_llm(
            task_type="spec_generation",
            system_prompt=self.system_prompt,
            user_prompt=full_prompt,
            max_tokens=1500,
            temperature=0.3
        )
        
        if not result.get("success"):
            raise RuntimeError(f"LLM failed to generate spec: {result.get('error')}")
        
        content = result.get("content", "").strip()
        if not content:
            raise RuntimeError("LLM returned empty content for spec generation")
        
        return content

    def save_spec(self, spec_content: str, output_path: Optional[Path] = None) -> Path:
        """
        Guarda la especificación en disco.
        
        Args:
            spec_content: Contenido Markdown de la especificación.
            output_path: Ruta opcional donde guardar. Si es None, se usa apa/specs/ con timestamp.
            
        Returns:
            Path: Ruta donde se guardó el archivo.
        """
        if output_path is None:
            specs_dir = Path(__file__).parent.parent / "specs"
            specs_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = specs_dir / f"spec_chat_{timestamp}.md"
        
        output_path.write_text(spec_content, encoding="utf-8")
        logger.info(f"Spec saved to {output_path}")
        return output_path

    def is_ready(self, conversation_history: List[Dict[str, str]]) -> bool:
        """
        Evalúa si la conversación contiene suficiente información 
        para generar una spec válida (D4).
        
        Args:
            conversation_history: Lista de mensajes del chat.
            
        Returns:
            bool: True si se detectan objetivo, inputs, output y criterio de éxito.
        """
        # Extraer solo mensajes del usuario
        user_text = " ".join(
            msg.get("content", "") for msg in conversation_history 
            if msg.get("role") == "user"
        ).lower()
        
        if not user_text.strip():
            return False
        
        # Palabras clave por categoría
        objetivo_kw = ["quiero", "necesito", "objetivo", "crear", "implementar", "desarrollar", "hacer", "construir"]
        inputs_kw = ["input", "recibe", "entrada", "parámetro", "argumento", "archivo", "csv", "json"]
        output_kw = ["output", "retorna", "retorne", "devuelve", "salida", "imprime", "genera", "respuesta"]
        criterio_kw = ["criterio", "éxito", "exito", "debe", "tiene que", "esperado", "assert", "prueba"]
        
        tiene_objetivo = any(kw in user_text for kw in objetivo_kw)
        tiene_inputs = any(kw in user_text for kw in inputs_kw)
        tiene_output = any(kw in user_text for kw in output_kw)
        tiene_criterio = any(kw in user_text for kw in criterio_kw)
        
        return all([tiene_objetivo, tiene_inputs, tiene_output, tiene_criterio])


if __name__ == "__main__":
    builder = SpecBuilder()

    # ========================================
    # Pruebas de is_ready() (D4)
    # ========================================
    print("🧪 Ejecutando pruebas de is_ready()...")

    # Caso 1: Conversación completa (debe retornar True)
    hist_completo = [
        {"role": "user", "content": "Quiero una API que sume dos números. Recibe a y b como enteros. Retorna la suma en JSON. Debe pasar un test con assert."}
    ]
    assert builder.is_ready(hist_completo) == True, "❌ Caso completo falló"
    print("  ✓ Caso completo: True")

    # Caso 2: Conversación incompleta (falta criterio de éxito) → False
    hist_incompleto = [
        {"role": "user", "content": "Quiero una función que sume dos números."}
    ]
    assert builder.is_ready(hist_incompleto) == False, "❌ Caso incompleto falló"
    print("  ✓ Caso incompleto: False")

    # Caso 3: Conversación vacía → False
    assert builder.is_ready([]) == False, "❌ Caso vacío falló"
    print("  ✓ Caso vacío: False")

    print("✅ Tests de is_ready() pasados.\n")

    # ========================================
    # Pruebas existentes (build_spec / save_spec)
    # ========================================
    test_history = [
        {"role": "user", "content": "Quiero una API que sume dos números"},
        {"role": "assistant", "content": "¿Qué inputs recibe? ¿Qué debe retornar?"},
        {"role": "user", "content": "Recibe a y b como enteros, retorna la suma en JSON"}
    ]

    try:
        spec = builder.build_spec(test_history)
        print("=== Spec generada ===")
        print(spec)
        assert "Objetivo" in spec, "Falta Objetivo"
        assert "Criterio de éxito" in spec, "Falta Criterio de éxito"
        print("\n✅ Spec generada correctamente")
        
        # Probar guardado
        saved_path = builder.save_spec(spec)
        print(f"✅ Spec guardada en {saved_path}")
        
        # Limpieza de archivo de prueba
        if saved_path.exists():
            saved_path.unlink()
            
    except Exception as e:
        print(f"⚠️ Prueba de LLM omitida o fallida (requiere conexión/keys): {e}")