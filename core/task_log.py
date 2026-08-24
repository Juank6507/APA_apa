# apa/core/task_log.py
"""
========================================================================
Módulo: core/task_log.py — Bitácora de Ejecución de Tareas (Task Log)
========================================================================

Sistema de registro de ejecución de tareas para APA (AI Project Automation).

Cuando se genera un plan a partir de un SDD, este contiene tareas que son
ejecutadas por diferentes agentes. La bitácora registra el CONTEXTO COMPLETO
de cada ejecución para que:

    1. Los modelos de planificación puedan reprogramar tareas fallidas.
    2. Los modelos de fiscalización (auditoría) puedan auditar el trabajo
       realizado y tomar decisiones informadas.

Formato de almacenamiento: JSONL (JSON Lines) — un registro JSON por línea,
lo que permite lecturas progresivas y escrituras concurrentes controladas.

Estructura de directorios:
    specs/{project_id}/task_log.jsonl

Dependencias:
    - pathlib (estándar, multiplataforma)
    - threading (estándar, seguridad entre hilos)
    - logging (estándar, registros del sistema)
    - json (estándar, serialización)
    - datetime (estándar, marcas temporales)

Autor: APA Core Team
Versión: 1.0.0
========================================================================
"""

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


logger = logging.getLogger("apa.task_log")


class TaskLog:
    """Bitácora de ejecución de tareas APA.

    Registra el contexto completo de cada ejecución de tarea en formato
    JSONL. Permite lectura, consulta y actualización de registros.

    Cada entrada en el JSONL contiene:
        - timestamp: momento de la ejecución (ISO 8601)
        - task_id: identificador de la tarea
        - agent: agente que ejecutó la tarea
        - model: modelo LLM detrás del agente
        - task_code: código de la tarea
        - llm_context: prompts enviados al LLM
        - output: lo que se generó
        - status: estado de la ejecución

    Attributes:
        specs_dir: Ruta al directorio de especificaciones.
        _lock: Lock para escrituras concurrentes.
    """

    def __init__(self, specs_dir: str) -> None:
        """Inicializa la bitácora con la ruta al directorio de specs.

        Args:
            specs_dir: Ruta absoluta o relativa al directorio specs/.
        """
        self.specs_dir = Path(specs_dir)
        self._lock = threading.Lock()
        logger.debug("TaskLog inicializado con specs_dir=%s", self.specs_dir)

    def _get_log_path(self, project_id: str) -> Path:
        """Retorna la ruta al archivo JSONL de un proyecto.

        Args:
            project_id: Identificador del proyecto.

        Returns:
            Path al archivo task_log.jsonl del proyecto.
        """
        return self.specs_dir / project_id / "task_log.jsonl"

    def _ensure_project_dir(self, project_id: str) -> Path:
        """Asegura que el directorio del proyecto exista.

        Args:
            project_id: Identificador del proyecto.

        Returns:
            Path al directorio del proyecto.
        """
        project_dir = self.specs_dir / project_id
        project_dir.mkdir(parents=True, exist_ok=True)
        return project_dir

    def log_task_execution(
        self,
        project_id: str,
        task_id: str,
        agent: str,
        model: str,
        task_code: str,
        llm_context: list,
        output: str,
        status: str,
    ) -> dict:
        """Registra una ejecución de tarea en la bitácora.

        Appends un nuevo registro JSON al archivo JSONL del proyecto.
        La escritura es thread-safe.

        Args:
            project_id: Identificador del proyecto.
            task_id: Identificador de la tarea.
            agent: Agente que ejecutó la tarea.
            model: Modelo LLM detrás del agente.
            task_code: Código o descripción técnica de la tarea.
            llm_context: Lista de prompts enviados al LLM.
            output: Lo que se generó como resultado.
            status: Estado de la ejecución (e.g. 'completed', 'failed').

        Returns:
            dict con la entrada registrada y su ubicación.
        """
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "task_id": task_id,
            "agent": agent,
            "model": model,
            "task_code": task_code,
            "llm_context": llm_context,
            "output": output,
            "status": status,
        }

        log_path = self._get_log_path(project_id)

        with self._lock:
            try:
                self._ensure_project_dir(project_id)
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                logger.info(
                    "Tarea registrada: project=%s task=%s status=%s",
                    project_id,
                    task_id,
                    status,
                )
                return {"success": True, "entry": entry, "path": str(log_path)}
            except OSError as exc:
                logger.error(
                    "Error escribiendo task_log para %s: %s", project_id, exc
                )
                return {"success": False, "error": str(exc)}
            except (TypeError, ValueError) as exc:
                logger.error(
                    "Error serializando entrada para %s/%s: %s",
                    project_id,
                    task_id,
                    exc,
                )
                return {"success": False, "error": str(exc)}

    def get_task_log(self, project_id: str) -> list[dict]:
        """Lee todas las entradas de la bitácora de un proyecto.

        Args:
            project_id: Identificador del proyecto.

        Returns:
            Lista de diccionarios con las entradas leídas.
            Lista vacía si el archivo no existe o hay errores.
        """
        log_path = self._get_log_path(project_id)

        if not log_path.exists():
            logger.debug(
                "No existe bitácora para proyecto %s", project_id
            )
            return []

        entries: list[dict] = []
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                for line_number, line in enumerate(f, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        entries.append(entry)
                    except json.JSONDecodeError as exc:
                        logger.warning(
                            "Línea %d inválida en %s: %s",
                            line_number,
                            log_path,
                            exc,
                        )
                        continue
            logger.debug(
                "Leídas %d entradas de %s", len(entries), project_id
            )
            return entries
        except OSError as exc:
            logger.error(
                "Error leyendo task_log de %s: %s", project_id, exc
            )
            return []

    def get_task_entry(
        self, project_id: str, task_id: str
    ) -> Optional[dict]:
        """Obtiene la última entrada de una tarea específica.

        Si una tarea tiene múltiples ejecuciones (reintentos),
        retorna la más reciente.

        Args:
            project_id: Identificador del proyecto.
            task_id: Identificador de la tarea.

        Returns:
            Diccionario con la entrada o None si no existe.
        """
        entries = self.get_task_log(project_id)
        matching = [
            e for e in entries if e.get("task_id") == task_id
        ]

        if not matching:
            logger.debug(
                "No se encontró entrada para tarea %s/%s",
                project_id,
                task_id,
            )
            return None

        latest = matching[-1]
        logger.debug(
            "Encontrada última entrada para %s/%s (status=%s)",
            project_id,
            task_id,
            latest.get("status"),
        )
        return latest

    def get_task_summary(self, project_id: str, task_id: str) -> str:
        """Genera un resumen formateado de una tarea para fiscalización.

        Produce un string legible que un modelo de fiscalización puede
        consumir para entender qué pasó en la ejecución: quién ejecutó,
        qué modelo usó, qué prompts se enviaron, y qué se generó.

        Args:
            project_id: Identificador del proyecto.
            task_id: Identificador de la tarea.

        Returns:
            String formateado con el resumen, o mensaje de error.
        """
        entry = self.get_task_entry(project_id, task_id)

        if entry is None:
            return (
                f"No se encontró registro para la tarea {task_id} "
                f"en el proyecto {project_id}."
            )

        lines: list[str] = []
        lines.append("=" * 70)
        lines.append(f"RESUMEN DE TAREA: {task_id}")
        lines.append("=" * 70)
        lines.append("")

        # Timestamp
        ts = entry.get("timestamp", "desconocido")
        lines.append(f"MARCA TEMPORAL: {ts}")
        lines.append("")

        # Estado
        status = entry.get("status", "desconocido")
        lines.append(f"ESTADO: {status}")
        lines.append("")

        # Descripción de la tarea
        task_code = entry.get("task_code", "(no especificado)")
        lines.append("DESCRIPCIÓN DE LA TAREA:")
        lines.append(f"  {task_code}")
        lines.append("")

        # Quién ejecutó
        agent = entry.get("agent", "desconocido")
        model = entry.get("model", "desconocido")
        lines.append("QUIÉN EJECUTÓ:")
        lines.append(f"  Agente:  {agent}")
        lines.append(f"  Modelo:  {model}")
        lines.append("")

        # Contexto LLM (prompts)
        llm_context = entry.get("llm_context", [])
        lines.append("PROMPTS ENVIADOS AL LLM:")
        if llm_context:
            for i, ctx_item in enumerate(llm_context, start=1):
                if isinstance(ctx_item, dict):
                    role = ctx_item.get("role", "unknown")
                    content = str(ctx_item.get("content", ""))
                    if len(content) > 500:
                        content = content[:500] + " ... [truncado]"
                    lines.append(f"  [{i}] role={role}:")
                    lines.append(f"      {content}")
                elif isinstance(ctx_item, str):
                    text = ctx_item[:500]
                    if len(ctx_item) > 500:
                        text += " ... [truncado]"
                    lines.append(f"  [{i}] {text}")
                else:
                    lines.append(f"  [{i}] {str(ctx_item)[:500]}")
        else:
            lines.append("  (sin contexto LLM registrado)")
        lines.append("")

        # Output generado
        output = entry.get("output", "")
        lines.append("LO QUE SE GENERÓ (output):")
        if output:
            if len(output) > 2000:
                output = output[:2000] + " ... [truncado]"
            lines.append(f"  {output}")
        else:
            lines.append("  (vacío)")
        lines.append("")

        lines.append("-" * 70)

        if status == "failed":
            lines.append(
                ">>> RECOMENDACIÓN: Esta tarea falló. Considerar "
                "reprogramación con diferente agente, modelo o enfoque."
            )
        elif status == "completed":
            lines.append("Tarea completada exitosamente.")
        else:
            lines.append(
                "Tarea en estado intermedio. Verificar si hay "
                "ejecución pendiente."
            )

        lines.append("=" * 70)
        return "\n".join(lines)

    def update_task_status(
        self, project_id: str, task_id: str, status: str
    ) -> bool:
        """Actualiza el estado de la última entrada de una tarea.

        Reescribe el archivo JSONL completo, reemplazando el estado
        de la última ocurrencia del task_id.

        Args:
            project_id: Identificador del proyecto.
            task_id: Identificador de la tarea.
            status: Nuevo estado (e.g. 'completed', 'failed', 'retry').

        Returns:
            True si se actualizó correctamente, False en caso contrario.
        """
        log_path = self._get_log_path(project_id)

        if not log_path.exists():
            logger.warning(
                "No existe bitácora para %s al actualizar estado",
                project_id,
            )
            return False

        with self._lock:
            try:
                entries: list[dict] = []
                updated = False
                last_index = -1

                with open(log_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                            entries.append(entry)
                            if entry.get("task_id") == task_id:
                                last_index = len(entries) - 1
                        except json.JSONDecodeError:
                            entries.append(line)
                            continue

                if last_index >= 0:
                    old_status = entries[last_index].get("status", "?")
                    entries[last_index]["status"] = status
                    entries[last_index][
                        "status_updated_at"
                    ] = datetime.now(timezone.utc).isoformat()
                    updated = True
                    logger.info(
                        "Estado actualizado: %s/%s %s → %s",
                        project_id,
                        task_id,
                        old_status,
                        status,
                    )

                if updated:
                    with open(log_path, "w", encoding="utf-8") as f:
                        for entry in entries:
                            if isinstance(entry, dict):
                                f.write(
                                    json.dumps(entry, ensure_ascii=False)
                                    + "\n"
                                )
                            else:
                                f.write(str(entry) + "\n")

                return updated

            except OSError as exc:
                logger.error(
                    "Error actualizando estado de %s/%s: %s",
                    project_id,
                    task_id,
                    exc,
                )
                return False

    def clear_log(self, project_id: str) -> bool:
        """Elimina toda la bitácora de un proyecto.

        Args:
            project_id: Identificador del proyecto.

        Returns:
            True si se eliminó correctamente, False en caso contrario.
        """
        log_path = self._get_log_path(project_id)

        with self._lock:
            try:
                if log_path.exists():
                    log_path.unlink()
                    logger.info(
                        "Bitácora eliminada para proyecto %s", project_id
                    )
                    return True
                logger.debug(
                    "Bitácora no existe para proyecto %s, nada que limpiar",
                    project_id,
                )
                return True
            except OSError as exc:
                logger.error(
                    "Error limpiando bitácora de %s: %s", project_id, exc
                )
                return False


if __name__ == "__main__":
    import tempfile
    import shutil

    print("=== Validación de core/task_log.py ===")
    print()

    # Crear directorio temporal
    temp_dir = tempfile.mkdtemp(prefix="task_log_test_")
    print(f"Directorio temporal: {temp_dir}")

    try:
        # 1. Instanciar TaskLog
        tl = TaskLog(temp_dir)
        print("[OK] TaskLog instanciado")

        # 2. Registrar 3 tareas
        result1 = tl.log_task_execution(
            project_id="proj_001",
            task_id="T001",
            agent="apa_agent",
            model="gpt-4o",
            task_code="Crear módulo de autenticación",
            llm_context=[
                {"role": "system", "content": "Eres un desarrollador experto"},
                {"role": "user", "content": "Crea un módulo de auth con JWT"},
            ],
            output="def authenticate(token): ...",
            status="completed",
        )
        assert result1["success"] is True
        print("[OK] Tarea T001 registrada")

        result2 = tl.log_task_execution(
            project_id="proj_001",
            task_id="T002",
            agent="apa_agent",
            model="claude-3-sonnet",
            task_code="Crear tests unitarios para auth",
            llm_context=[
                {"role": "user", "content": "Escribe tests para el módulo de auth"},
            ],
            output="def test_authenticate(): ...",
            status="completed",
        )
        assert result2["success"] is True
        print("[OK] Tarea T002 registrada")

        result3 = tl.log_task_execution(
            project_id="proj_001",
            task_id="T003",
            agent="apa_agent",
            model="gpt-4o",
            task_code="Configurar base de datos PostgreSQL",
            llm_context=[
                {"role": "user", "content": "Configura la conexión a PostgreSQL"},
            ],
            output="",
            status="failed",
        )
        assert result3["success"] is True
        print("[OK] Tarea T003 registrada (fallida)")

        # 3. Leer todas las entradas
        all_entries = tl.get_task_log("proj_001")
        assert len(all_entries) == 3, f"Esperaba 3, obtuve {len(all_entries)}"
        print(f"[OK] Leídas {len(all_entries)} entradas")

        # 4. Obtener entrada específica
        t002 = tl.get_task_entry("proj_001", "T002")
        assert t002 is not None
        assert t002["model"] == "claude-3-sonnet"
        print("[OK] get_task_entry retorna entrada correcta")

        # 5. Obtener entrada inexistente
        t999 = tl.get_task_entry("proj_001", "T999")
        assert t999 is None
        print("[OK] get_task_entry retorna None para inexistente")

        # 6. Obtener resumen de tarea
        summary = tl.get_task_summary("proj_001", "T001")
        assert "T001" in summary
        assert "gpt-4o" in summary
        assert "apa_agent" in summary
        assert "JWT" in summary
        print("[OK] get_task_summary genera resumen correcto")
        print()
        print("--- Resumen de T001 ---")
        print(summary)

        # 7. Resumen de tarea inexistente
        summary_none = tl.get_task_summary("proj_001", "T999")
        assert "No se encontró" in summary_none
        print("[OK] Resumen para tarea inexistente retorna mensaje")

        # 8. Actualizar estado
        updated = tl.update_task_status("proj_001", "T003", "retry")
        assert updated is True
        t003_updated = tl.get_task_entry("proj_001", "T003")
        assert t003_updated["status"] == "retry"
        print("[OK] Estado de T003 actualizado a 'retry'")

        # 9. Actualizar estado de tarea inexistente
        updated_false = tl.update_task_status("proj_001", "T999", "completed")
        assert updated_false is False
        print("[OK] Actualizar estado de tarea inexistente retorna False")

        # 10. Leer log de proyecto inexistente
        empty_entries = tl.get_task_log("proj_999")
        assert empty_entries == []
        print("[OK] get_task_log de proyecto inexistente retorna lista vacía")

        # 11. Limpiar log
        cleared = tl.clear_log("proj_001")
        assert cleared is True
        after_clear = tl.get_task_log("proj_001")
        assert after_clear == []
        print("[OK] clear_log elimina todas las entradas")

        # 12. Limpiar log ya limpio
        cleared_again = tl.clear_log("proj_001")
        assert cleared_again is True
        print("[OK] clear_log de proyecto sin log retorna True")

        # 13. Verificar estructura JSONL
        tl.log_task_execution(
            project_id="proj_002",
            task_id="T001",
            agent="system",
            model="none",
            task_code="tarea de prueba",
            llm_context=[],
            output="salida de prueba",
            status="completed",
        )
        log_path = Path(temp_dir) / "proj_002" / "task_log.jsonl"
        assert log_path.exists()
        with open(log_path, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert set(parsed.keys()) == {
            "timestamp", "task_id", "agent", "model",
            "task_code", "llm_context", "output", "status",
        }
        print("[OK] Estructura JSONL correcta con todos los campos")

        print()
        print("=== Todas las validaciones pasaron ===")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        print(f"\nDirectorio temporal limpiado: {temp_dir}")
