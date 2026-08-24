# apa/core/sdd_guide.py
"""
CV2: Árbol adaptativo de preguntas guía.

Genera preguntas naturales basadas en la madurez del SDD evaluada por CV1.
El sistema guía al usuario para cubrir los aspectos faltantes de forma conversacional,
sin que el usuario note que está respondiendo un cuestionario.

Integrado con el endpoint /chat para funcionar como capa invisible
entre la conversación y la respuesta del LLM.
"""

import logging
import sys
import os
import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

# Añadir el directorio padre al path para permitir imports relativos al ejecutar directamente
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from core.sdd_maturity import (
    SDDMaturityEvaluator,
    MaturityResult,
    AspectStatus,
    AspectPriority,
    CoverageLevel,
)

logger = logging.getLogger(__name__)


@dataclass
class GuideHint:
    """Instrucción invisible para el LLM sobre cómo debe enfocar su respuesta.

    No se muestra al usuario. Se inyecta en el system prompt del chat
    para guiar la conversación de forma natural.
    """
    focus_aspect: str       # Key del aspecto a cubrir (ej: "problem")
    focus_label: str        # Nombre descriptivo del aspecto
    natural_instruction: str  # Instrucción en lenguaje natural para el LLM
    priority: str           # "imprescindible" | "necesaria"


@dataclass
class GuideState:
    """Estado del arnés de guía para una conversación activa."""
    is_active: bool = False                    # True cuando se detectó proyecto
    last_hint: Optional[GuideHint] = None       # Última instrucción dada al LLM
    asked_aspects: List[str] = field(default_factory=list)  # Aspectos que ya se intentó cubrir
    ask_count: int = 0                         # Cuántas veces se ha intentado cubrir aspectos
    max_consecutive_asks: int = 3               # Máximo de preguntas seguidas antes de descansar
    consecutive_asks: int = 0                  # Preguntas consecutivas sin tema nuevo del usuario
    user_message_count_since_last_ask: int = 0 # Mensajes del usuario desde la última guía


class SDDGuide:
    """
    CV2: Arnés de preguntas guía adaptativas.

    Funciona como una capa invisible entre la conversación del usuario
    y el LLM. En cada turno:
    1. Recibe el mensaje del usuario
    2. Evalúa la madurez actual del SDD (via CV1)
    3. Determina qué aspecto es más prioritario cubrir
    4. Genera una instrucción invisible para el LLM
    5. El LLM responde naturalmente, guiado por esa instrucción
    """

    def __init__(self):
        """Inicializa el arnés con el evaluador de madurez."""
        self._evaluator = SDDMaturityEvaluator()
        self._state = GuideState()

        # Frases de transición para introducir preguntas de forma natural
        self._transition_phrases = {
            "problem": [
                "dime más sobre qué te lleva a buscar esto",
                "¿qué te gustaría que cambiara?",
                "entiendo, ¿y cuál es la situación que quieres mejorar?",
            ],
            "what_is": [
                "para entenderte mejor",
                "para tener claro el enfoque",
                "cuéntame un poco más",
            ],
            "features": [
                "¿qué cosas te gustaría que pudieras hacer?",
                "imagina que ya está listo, ¿qué harías con él?",
            ],
            "limits": [
                "y para empezar, ¿qué sería lo básico?",
                "¿hay algo que sepas que no necesitas?",
            ],
            "usage": [
                "cuéntame cómo lo verías funcionar",
                "ponte en el lugar de quien lo va a usar",
            ],
            "similar_existing": [
                "¿conoces algo que haga algo parecido?",
                "¿has visto alguna aplicación que haga algo similar?",
            ],
            "constraints": [
                "¿alguna limitación que tenga en cuenta?",
                "¿tiene que funcionar en algún dispositivo en particular?",
            ],
            "success_criteria": [
                "imagina que ya está terminado",
                "¿cómo sabrías que funciona bien?",
            ],
            "integrations": [
                "¿necesita conectarse con algo que ya tengas?",
                "¿usa algún sistema externo, base de datos, o servicio?",
            ],
            "states": [
                "ese proceso que me cuentas, ¿pasa por etapas?",
                "¿hay algún punto donde algo cambie de estado?",
            ],
            "invariants": [
                "¿hay reglas que nunca se pueden romper en tu negocio?",
                "¿algo que siempre deba ser cierto, pase lo que pase?",
            ],
            "edge_cases": [
                "pensando en lo que me contaste, ¿qué podría salir mal?",
                "¿qué escenario te daría miedo que ocurriera?",
            ],
        }

    def process_message(
        self,
        user_message: str,
        conversation_history: List[Dict[str, str]],
    ) -> Optional[GuideHint]:
        """
        Procesa un mensaje del usuario y retorna una instrucción de guía
        si es necesario.

        Args:
            user_message: El último mensaje del usuario.
            conversation_history: Historial completo de la conversación.

        Returns:
            GuideHint si hay un aspecto que cubrir, None si no es necesario guiar.
        """
        # Añadir el mensaje a la cuenta
        self._state.user_message_count_since_last_ask += 1

        # Evaluar madurez completa
        maturity = self._evaluator.evaluate(conversation_history)

        # Si no es conversación de proyecto, desactivar
        if not maturity.is_project_conversation:
            if self._state.is_active:
                logger.info("CV2: Conversación ya no parece un proyecto, desactivando guía")
                self._state.is_active = False
            return None

        # Activar guía si se detecta proyecto
        if not self._state.is_active and maturity.is_project_conversation:
            logger.info(f"CV2: Proyecto detectado (confianza: {maturity.project_confidence:.2f}), activando guía")
            self._state.is_active = True

        # Si ya puede generar proyecto, no guiar más (pero mantener activo)
        if maturity.can_generate_project:
            logger.info("CV2: Todas las imprescindibles cubiertas, sin guía necesaria")
            self._state.last_hint = None
            return None

        # Resetear contador consecutivo si el usuario aporta contenido nuevo
        if self._state.user_message_count_since_last_ask >= 2:
            self._state.consecutive_asks = 0

        # Evitar demasiadas preguntas seguidas: si llevamos max_consecutive_asks,
        # dejar que la conversación fluya libre
        if self._state.consecutive_asks >= self._state.max_consecutive_asks:
            if self._state.user_message_count_since_last_ask < 2:
                return None  # Aún no ha hablado lo suficiente desde la última guía
            self._state.consecutive_asks = 0

        # Determinar el aspecto más prioritario faltante
        hint = self._select_next_aspect(maturity)

        if hint:
            self._state.last_hint = hint
            self._state.asked_aspects.append(hint.focus_aspect)
            self._state.ask_count += 1
            self._state.consecutive_asks += 1
            self._state.user_message_count_since_last_ask = 0
            logger.info(f"CV2: Guía activa → enfocar en '{hint.focus_label}' ({hint.priority})")

        return hint

    def get_system_prompt_addition(self, hint: GuideHint) -> str:
        """
        Genera el fragmento de texto que se añade al system prompt del chat
        para guiar la respuesta del LLM.

        Este texto es invisible para el usuario pero dirige al LLM para que
        cubra el aspecto faltante de forma natural.
        """
        if not hint:
            return ""

        # Seleccionar frase de transición aleatoria
        phrases = self._transition_phrases.get(hint.focus_aspect, [])
        transition = phrases[self._state.ask_count % len(phrases)] if phrases else ""

        return (
            f"\n\n--- [INSTRUCCIÓN INTERNA - NO MOSTRAR AL USUARIO] ---\n"
            f"La conversación actual parece describir un proyecto de software. "
            f"Para que la conversación sea productiva, enfoca tu próxima respuesta "
            f"en cubrir este aspecto que aún falta:\n"
            f"- Aspecto: {hint.focus_label}\n"
            f"- Prioridad: {hint.priority}\n"
            f"- Qué hacer: {hint.natural_instruction}\n"
            f"- Estilo: No preguntes directamente '{hint.focus_label}'. En lugar de eso, "
            f"conecta con lo que el usuario acaba de decir y {transition}. "
            f"Sé natural, como si estuvieras teniendo una conversación interesada.\n"
            f"- Si el usuario ya proporcionó información sobre este aspecto en su último "
            f"mensaje, NO preguntes sobre ello. Simplemente reconócelo y avanza.\n"
            f"--- [FIN INSTRUCCIÓN INTERNA] ---\n"
        )

    def get_project_ready_status(self, conversation_history: List[Dict[str, str]]) -> Dict:
        """
        Retorna el estado de preparación del proyecto para la interfaz.

        Útil para decidir si habilitar el botón "Crear Proyecto" en el frontend.

        Args:
            conversation_history: Historial completo de la conversación.

        Returns:
            Dict con claves: is_project, can_generate, maturity, coverage_summary
        """
        maturity = self._evaluator.evaluate(conversation_history)

        return {
            "is_project_conversation": maturity.is_project_conversation,
            "can_generate_project": maturity.can_generate_project,
            "maturity_label": maturity.maturity_label,
            "project_confidence": maturity.project_confidence,
            "imprescindibles": {
                "covered": maturity.imprescindibles_covered,
                "total": maturity.imprescindibles_total,
            },
            "necesarias": {
                "covered": maturity.necesarias_covered,
                "total": maturity.necesarias_total,
            },
        }

    def reset(self):
        """Reinicia el estado del arnés para una nueva conversación."""
        self._state = GuideState()
        logger.info("CV2: Estado reiniciado")

    # --- Métodos privados ---

    def _select_next_aspect(self, maturity: MaturityResult) -> Optional[GuideHint]:
        """
        Selecciona el siguiente aspecto a cubrir.

        Prioridad:
        1. Imprescindibles no cubiertas (orden de definición)
        2. Si todas las imprescindibles parciales ya se preguntaron, pausar
        3. Necesarias no cubiertas (solo si imprescindibles están cubiertas o parciales)
        """
        # Primero: imprescindibles no cubiertas
        missing_impressionsibles = self._evaluator.get_missing_impressionsibles(maturity)

        # Filtrar las que ya se preguntaron recientemente (evitar insistencia)
        not_recently_asked = [
            a for a in missing_impressionsibles
            if a.key not in self._state.asked_aspects[-2:]  # Excluir las 2 últimas
        ]

        # Si todas las imprescindibles se preguntaron recientemente, pausar
        if missing_impressionsibles and not not_recently_asked:
            # Pero si hay algunas que nunca se preguntaron, insistir
            never_asked = [
                a for a in missing_impressionsibles
                if a.key not in self._state.asked_aspects
            ]
            if not never_asked:
                return None  # Ya se intentó con todas, pausar guía

        target = not_recently_asked[0] if not_recently_asked else (
            missing_impressionsibles[0] if missing_impressionsibles else None
        )

        if target:
            return GuideHint(
                focus_aspect=target.key,
                focus_label=target.label,
                natural_instruction=self._build_instruction(target),
                priority="imprescindible",
            )

        # Si todas las imprescindibles están cubiertas, verificar necesarias
        if maturity.imprescindibles_covered >= maturity.imprescindibles_total:
            missing_necesarias = self._evaluator.get_missing_necesarias(maturity)
            not_recently_nec = [
                a for a in missing_necesarias
                if a.key not in self._state.asked_aspects[-2:]
            ]

            if not_recently_nec:
                target = not_recently_nec[0]
                return GuideHint(
                    focus_aspect=target.key,
                    focus_label=target.label,
                    natural_instruction=self._build_instruction(target),
                    priority="necesaria",
                )

        return None

    def _build_instruction(self, aspect: AspectStatus) -> str:
        """Construye la instrucción natural para el LLM."""
        instructions = {
            "what_is": (
                "Averigua qué tipo de aplicación o sistema es lo que el usuario "
                "quiere crear y quiénes lo usarían. Usa el contexto de lo que "
                "ya dijo para formular la pregunta de forma natural."
            ),
            "problem": (
                "Descubre el problema, necesidad o dolor que motiva al usuario. "
                "Conecta con lo que ya contó para que fluya como una conversación, "
                "no como un interrogatorio."
            ),
            "features": (
                "Haz que el usuario describa las funcionalidades principales que "
                "necesita, ordenadas por importancia. Ayúdalo a pensar en el "
                "tangible: qué botones pulsaría, qué pantallas vería."
            ),
            "limits": (
                "Aclara los límites del proyecto: qué no incluye, qué se deja "
                "para después, o qué es explícitamente fuera de alcance."
            ),
            "usage": (
                "Guía al usuario para que describa paso a paso cómo usaría la "
                "aplicación, desde que entra hasta que termina lo que vino a hacer."
            ),
            "similar_existing": (
                "Pregunta si conoce aplicaciones o herramientas que hagan algo "
                "parecido. Si menciona alguna, aprovecha para entender qué le "
                "gusta y qué le falta de lo que existe."
            ),
            "stakeholders": (
                "Descubre si hay otras personas que necesitan aprobar, revisar "
                "o usar el resultado."
            ),
            "constraints": (
                "Identifica limitaciones importantes: plataformas (móvil, PC), "
                "plazos, datos sensibles, normativas. También pregunta por el "
                "volumen esperado: ¿cuántos usuarios? ¿cuántos registros o datos? "
                "¿cuánta concurrencia?"
            ),
            "success_criteria": (
                "Ayuda al usuario a definir qué significa 'quedar bien' y qué "
                "significa 'mal'. Pide que imagine que ya está terminado y que "
                "diga qué probaría primero. Luego explora qué debería ocurrir "
                "cuando algo sale mal: ¿cómo debe rechazarse un dato incorrecto? "
                "¿qué debería pasar si alguien intenta una acción prohibida?"
            ),
            "integrations": (
                "Averigua si necesita conectarse con sistemas externos, "
                "bases de datos, servicios de pago, APIs, etc."
            ),
            "states": (
                "Descubre si el proceso que describe el usuario pasa por "
                "etapas o estados (ej: 'borrador', 'pendiente', 'aprobado', "
                "'entregado'). Si los hay, identifica cuáles son y cómo "
                "transiciona entre ellos."
            ),
            "invariants": (
                "Identifica reglas de negocio que siempre se cumplen, como "
                "'un mismo email no puede registrarse dos veces', 'el saldo "
                "nunca puede ser negativo', o 'nadie puede reservar algo "
                "ya ocupado'. Pregunta de forma natural y con ejemplos."
            ),
            "edge_cases": (
                "Explora qué podría salir mal en el flujo que el usuario "
                "describió: errores, conflictos, datos inválidos, acciones "
                "simultáneas, etc. Pide 2 o 3 ejemplos concretos de "
                "escenarios que le preocuparían."
            ),
            "alternatives": (
                "Explora si el usuario ha considerado otras opciones o enfoques "
                "y por qué eligió este."
            ),
            "timeline": (
                "Pregunta si hay plazos, fechas clave o fases definidas."
            ),
            "cross_team_impact": (
                "Identifica si otros equipos o áreas se verán afectados."
            ),
            "testing_approach": (
                "Explora cómo se probará que funciona correctamente."
            ),
            "open_questions": (
                "Identifica dudas o decisiones pendientes que podrían "
                "afectar el proyecto."
            ),
        }
        return instructions.get(
            aspect.key,
            f"Intenta descubrir más sobre '{aspect.label}' de forma natural.",
        )


# --- Módulo de pruebas ---

if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

    print("=== CV2: SDDGuide - Pruebas ===\n")
    guide = SDDGuide()

    # Caso 1: Conversación casual → sin guía
    print("Caso 1: Conversación casual")
    casual = [
        {"role": "user", "content": "Hola, ¿qué tal?"},
    ]
    hint1 = guide.process_message("Hola, ¿qué tal?", casual)
    assert hint1 is None, "No debería generar guía para conversación casual"
    print("  ✓ Sin guía (correcto)\n")

    # Caso 2: Primera señal de proyecto → guía activada
    print("Caso 2: Señal de proyecto detectada")
    project = [
        {"role": "user", "content": "Necesito algo para gestionar las reservas del restaurante"},
    ]
    hint2 = guide.process_message("Necesito algo para gestionar las reservas del restaurante", project)
    assert hint2 is not None, "Debería generar guía"
    assert guide._state.is_active == True, "Debería estar activo"
    print(f"  Guía: {hint2.focus_label} ({hint2.priority})")
    assert hint2.priority == "imprescindible", "Prioridad debe ser imprescindible"
    print("  ✓ PASS\n")

    # Caso 3: Conversación completa → sin guía necesaria
    print("Caso 3: Proyecto completo")
    guide.reset()
    complete = [
        {"role": "user", "content": "Quiero crear una app para que los vecinos reserven zonas comunes. Los vecinos son de una comunidad residencial. Ahora se gestiona con un cuaderno y hay conflictos. Necesito que puedan ver calendario y reservar. No incluye pagos. El vecino entra, selecciona espacio, elige fecha y confirma."},
    ]
    hint3 = guide.process_message("Quiero crear una app...", complete)
    maturity = guide._evaluator.evaluate(complete)
    print(f"  Madurez: {maturity.maturity_label}")
    print(f"  Imprescindibles: {maturity.imprescindibles_covered}/{maturity.imprescindibles_total}")
    print(f"  Puede generar: {maturity.can_generate_project}")
    if maturity.can_generate_project:
        assert hint3 is None, "No debería guiar si puede generar proyecto"
    print("  ✓ PASS\n")

    # Caso 4: Generación de fragmento de system prompt
    print("Caso 4: System prompt addition")
    guide.reset()
    guide.process_message("Necesito una app para reservas", [
        {"role": "user", "content": "Necesito una app para reservas"}
    ])
    if guide._state.last_hint:
        prompt_add = guide.get_system_prompt_addition(guide._state.last_hint)
        assert "INSTRUCCIÓN INTERNA" in prompt_add
        assert "NO MOSTRAR AL USUARIO" in prompt_add
        print(f"  Fragmento generado ({len(prompt_add)} chars)")
        print("  ✓ PASS\n")

    # Caso 5: get_project_ready_status
    print("Caso 5: Estado de preparación")
    status = guide.get_project_ready_status(complete)
    assert "can_generate_project" in status
    assert "imprescindibles" in status
    print(f"  Estado: {status['maturity_label']}, can_generate={status['can_generate_project']}")
    print(f"  Imprescindibles: {status['imprescindibles']}")
    print("  ✓ PASS\n")

    # Caso 6: Reset
    print("Caso 6: Reset")
    guide.reset()
    assert guide._state.is_active == False
    assert guide._state.ask_count == 0
    print("  ✓ Estado reiniciado\n")

    print("=== Todas las pruebas PASARON ===")
