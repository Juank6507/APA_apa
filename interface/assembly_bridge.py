"""
Python↔JS bridge for the Ensamblador WebView.

Exposes Python assembly functions to JavaScript via pywebview's ``js_api``
mechanism.  Every public method prefixed with ``asm_`` is callable from the
WebView as ``pywebview.api.asm_xxx()``.

The bridge does **not** contain business logic — it delegates to a
*controller* (the ``EnsambladorGUI`` instance) that is injected at runtime
via :meth:`set_controller`.

Threading notes
---------------
* Tkinter dialogs (``asm_browse``) must run on the Tk main thread.  We use
  ``controller.root.after_idle()`` to schedule them and a
  ``threading.Event`` to synchronise the calling (pywebview) thread.
* Long-running operations (``asm_run_full_auto``) are dispatched via
  ``root.after_idle()`` so the Tk event-loop stays responsive; the bridge
  returns immediately and the WebView can poll ``asm_get_status()`` for
  progress.

JS usage example::

    const path   = await pywebview.api.asm_browse();
    await pywebview.api.asm_set_project_root(path);
    await pywebview.api.asm_set_inputs(plannerText, coderText);
    await pywebview.api.asm_run_full_auto();
    // … poll status …
    const status = await pywebview.api.asm_get_status();
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class AssemblyBridge:
    """Thin proxy that mirrors EnsambladorGUI state for the WebView.

    Attributes
    ----------
    _controller : EnsambladorGUI | None
        Set at runtime by :meth:`set_controller`.  All ``asm_*`` methods
        delegate to this object.
    """

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def __init__(self) -> None:
        self._controller: Any = None  # EnsambladorGUI, set later

    def set_controller(self, controller: Any) -> None:
        """Bind a controller (EnsambladorGUI instance) that owns the real logic."""
        self._controller = controller
        logger.info("AssemblyBridge: controller bound (%s)", type(controller).__name__)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _schedule_main(self, fn, *args, **kwargs) -> None:
        """Schedule *fn* on the Tk main thread via ``root.after_idle``."""
        if self._controller and hasattr(self._controller, "root"):
            self._controller.root.after_idle(lambda: fn(*args, **kwargs))
        else:
            fn(*args, **kwargs)

    def _run_on_main_thread_sync(self, fn, *args, timeout: float = 30.0) -> Any:
        """Run *fn* on the Tk main thread and block until it completes.

        Uses ``threading.Event`` for synchronisation.  Returns whatever
        *fn* returns, or ``None`` on timeout / error.
        """
        result_holder: list = [None]
        error_holder: list = [None]
        event = threading.Event()

        def _wrapper():
            try:
                result_holder[0] = fn(*args)
            except Exception as exc:
                error_holder[0] = exc
            finally:
                event.set()

        self._schedule_main(_wrapper)
        ok = event.wait(timeout=timeout)
        if not ok:
            logger.warning("AssemblyBridge: main-thread call timed out after %.1fs", timeout)
        if error_holder[0] is not None:
            raise error_holder[0]
        return result_holder[0]

    # ------------------------------------------------------------------
    # 1. Project root
    # ------------------------------------------------------------------

    def asm_get_project_root(self) -> str:
        """Return the current project root path string."""
        if self._controller is None:
            return ""
        return getattr(self._controller, "project_root", type("", (), {"get": lambda self: ""})()).get()

    def asm_browse(self) -> str:
        """Open a native directory-picker dialog (Tk ``filedialog``).

        Blocks the calling thread until the user closes the dialog.
        Returns the selected path or an empty string on cancel.
        """
        if self._controller is None:
            return ""

        def _pick() -> str:
            from tkinter import filedialog
            from pathlib import Path

            curr = self._controller.project_root.get()
            initial = curr if curr and Path(curr).exists() else str(Path.cwd())
            path = filedialog.askdirectory(
                initialdir=initial,
                title="Seleccionar raíz del proyecto",
            )
            return path  # empty string on cancel

        try:
            result = self._run_on_main_thread_sync(_pick)
            # Mirror the controller's own behaviour: set the path if non-empty
            if result:
                self._schedule_main(self._controller.project_root.set, result)
            return result or ""
        except Exception as exc:
            logger.error("asm_browse error: %s", exc)
            return ""

    def asm_set_project_root(self, path: str) -> bool:
        """Set the project root to *path*.

        Returns ``True`` on success, ``False`` if the controller is not bound.
        """
        if self._controller is None:
            return False
        self._schedule_main(self._controller.project_root.set, path)
        return True

    # ------------------------------------------------------------------
    # 2. Full auto assembly
    # ------------------------------------------------------------------

    def asm_run_full_auto(self) -> Dict[str, str]:
        """Trigger full assembly + execution on the Tk main thread.

        Returns immediately with ``{"status": "started"}``.  The WebView
        should subsequently poll :meth:`asm_get_status` for progress.
        """
        if self._controller is None:
            return {"status": "error", "message": "No controller bound"}
        self._schedule_main(self._controller._asm_run_full_auto)
        return {"status": "started"}

    # ------------------------------------------------------------------
    # 3. Undo / Redo
    # ------------------------------------------------------------------

    def asm_undo(self) -> Dict[str, Any]:
        """Undo the last assembly change.

        Returns a status dict; on success the undo stack is popped and
        the previous content is restored in the controller's text widgets.
        """
        if self._controller is None:
            return {"status": "error", "message": "No controller bound"}

        has_undo = bool(self._controller.asm_undo_stack)
        if not has_undo:
            return {"status": "noop", "message": "Nothing to undo"}

        self._schedule_main(self._controller._asm_undo)
        return {"status": "undone"}

    def asm_redo(self) -> Dict[str, Any]:
        """Redo the last undone assembly change.

        Returns a status dict; on success the redo stack is popped and
        the next state is restored.
        """
        if self._controller is None:
            return {"status": "error", "message": "No controller bound"}

        has_redo = bool(self._controller.asm_redo_stack)
        if not has_redo:
            return {"status": "noop", "message": "Nothing to redo"}

        self._schedule_main(self._controller._asm_redo)
        return {"status": "redone"}

    # ------------------------------------------------------------------
    # 4. Save / Copy / Clear
    # ------------------------------------------------------------------

    def asm_save(self) -> Dict[str, Any]:
        """Save the assembled script to disk (approve & write).

        Mirrors ``_asm_approve`` logic: creates backup, writes assembled
        content, marks task complete.

        Returns ``{"status": "saved", "path": ..., "task_id": ...}`` or
        ``{"status": "error", "message": ...}``.
        """
        if self._controller is None:
            return {"status": "error", "message": "No controller bound"}
        self._schedule_main(self._controller._asm_approve)
        return {"status": "started"}

    def asm_copy_code(self) -> Dict[str, Any]:
        """Copy the assembled code to the system clipboard.

        Returns ``{"status": "copied", "length": <char count>}`` or
        ``{"status": "error", "message": ...}``.
        """
        if self._controller is None:
            return {"status": "error", "message": "No controller bound"}

        def _copy() -> Dict[str, Any]:
            code = self._controller.asm_view.get("1.0", "end-1c")
            if code.strip():
                self._controller.root.clipboard_clear()
                self._controller.root.clipboard_append(code)
                self._controller.root.update()
                return {"status": "copied", "length": len(code)}
            return {"status": "empty", "message": "No code to copy"}

        try:
            return self._run_on_main_thread_sync(_copy)
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    def asm_clear(self) -> Dict[str, str]:
        """Clear planner/coder inputs and reset status.

        Delegates to ``_asm_clear_inputs`` on the controller.

        Returns ``{"status": "cleared"}``.
        """
        if self._controller is None:
            return {"status": "error", "message": "No controller bound"}
        self._schedule_main(self._controller._asm_clear_inputs)
        return {"status": "cleared"}

    # ------------------------------------------------------------------
    # 5. Status / Inputs (read & write)
    # ------------------------------------------------------------------

    def asm_get_status(self) -> Dict[str, Any]:
        """Return a snapshot of the current assembly status.

        Keys:
        * ``status``     – text from the status label
        * ``parsed_info`` – text from the parsed-info label
        * ``syntax``     – syntax-validation label text
        * ``line_count`` – number of lines in the assembled view
        * ``file_path``  – target script path
        * ``task_id``    – current task id
        * ``undo_depth`` – items in the undo stack
        * ``redo_depth`` – items in the redo stack
        * ``has_result`` – whether an assembled result exists
        """
        if self._controller is None:
            return {"status": "error", "message": "No controller bound"}

        def _collect() -> Dict[str, Any]:
            ctrl = self._controller

            status_text = ""
            parsed_text = ""
            syntax_text = ""

            if hasattr(ctrl, "asm_status_lbl"):
                status_text = ctrl.asm_status_lbl.cget("text")
            if hasattr(ctrl, "asm_parsed_lbl"):
                parsed_text = ctrl.asm_parsed_lbl.cget("text")
            if hasattr(ctrl, "asm_syntax_lbl"):
                syntax_text = ctrl.asm_syntax_lbl.cget("text")

            assembled = ""
            if hasattr(ctrl, "asm_view"):
                assembled = ctrl.asm_view.get("1.0", "end-1c")

            return {
                "status": status_text,
                "parsed_info": parsed_text,
                "syntax": syntax_text,
                "line_count": assembled.count("\n") + 1 if assembled.strip() else 0,
                "file_path": ctrl.asm_file_path.get() if hasattr(ctrl, "asm_file_path") else "",
                "task_id": ctrl.asm_task_id.get() if hasattr(ctrl, "asm_task_id") else "",
                "undo_depth": len(ctrl.asm_undo_stack) if hasattr(ctrl, "asm_undo_stack") else 0,
                "redo_depth": len(ctrl.asm_redo_stack) if hasattr(ctrl, "asm_redo_stack") else 0,
                "has_result": bool(assembled.strip()),
            }

        try:
            return self._run_on_main_thread_sync(_collect)
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    def asm_get_inputs(self) -> Dict[str, str]:
        """Return the current planner and coder text content.

        Returns ``{"planner": "...", "coder": "..."}``.
        """
        if self._controller is None:
            return {"planner": "", "coder": ""}

        def _read() -> Dict[str, str]:
            ctrl = self._controller
            planner = ""
            coder = ""
            if hasattr(ctrl, "asm_input"):
                planner = ctrl.asm_input.get("1.0", "end-1c")
            if hasattr(ctrl, "asm_coder_input"):
                coder = ctrl.asm_coder_input.get("1.0", "end-1c")
            return {"planner": planner, "coder": coder}

        try:
            return self._run_on_main_thread_sync(_read)
        except Exception as exc:
            logger.error("asm_get_inputs error: %s", exc)
            return {"planner": "", "coder": ""}

    def asm_set_inputs(self, planner_text: str, coder_text: str) -> Dict[str, str]:
        """Set the planner and coder text content in the controller's widgets.

        Returns ``{"status": "set"}`` on success.
        """
        if self._controller is None:
            return {"status": "error", "message": "No controller bound"}

        def _write() -> Dict[str, str]:
            ctrl = self._controller
            if hasattr(ctrl, "asm_input"):
                ctrl.asm_input.delete("1.0", "end-1c")
                ctrl.asm_input.insert("1.0", planner_text)
            if hasattr(ctrl, "asm_coder_input"):
                ctrl.asm_coder_input.delete("1.0", "end-1c")
                ctrl.asm_coder_input.insert("1.0", coder_text)
            return {"status": "set"}

        self._schedule_main(_write)
        return {"status": "set"}

    # ------------------------------------------------------------------
    # 6. Approve / Reject
    # ------------------------------------------------------------------

    def asm_approve(self) -> Dict[str, Any]:
        """Approve the assembled result and write to disk.

        Mirrors ``_asm_approve``: creates backup, writes content, marks
        task complete, clears inputs.

        Returns ``{"status": "approved"}`` or ``{"status": "error", ...}``.
        """
        if self._controller is None:
            return {"status": "error", "message": "No controller bound"}
        self._schedule_main(self._controller._asm_approve)
        return {"status": "started"}

    def asm_reject(self) -> Dict[str, Any]:
        """Reject the assembled result and restore from backup.

        Mirrors ``_asm_reject``: restores original file from backup,
        deletes backup, clears undo/redo stacks.

        Returns ``{"status": "rejected"}`` or ``{"status": "error", ...}``.
        """
        if self._controller is None:
            return {"status": "error", "message": "No controller bound"}
        self._schedule_main(self._controller._asm_reject)
        return {"status": "started"}

    # ------------------------------------------------------------------
    # 7. Push updates TO the WebView (Fase 4 placeholder)
    # ------------------------------------------------------------------

    def push_update(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
        """Push an update event to the WebView JavaScript layer.

        This will be implemented in Fase 4 once we hold a reference to the
        pywebview window object and can call ``window.evaluate_js()``.

        Parameters
        ----------
        event_type:
            Semantic event name (e.g. ``"status_change"``, ``"assembly_complete"``).
        data:
            Optional payload dict forwarded to the JS handler.
        """
        # Fase 4: self._webview_window.evaluate_js(
        #     f"window.__onBridgeEvent && window.__onBridgeEvent({json.dumps(event_type)}, {json.dumps(data or {})})"
        # )
        logger.debug("push_update (stub): event=%s  data=%s", event_type, data)


# ------------------------------------------------------------------
# Self-test
# ------------------------------------------------------------------

if __name__ == "__main__":
    bridge = AssemblyBridge()
    exposed = [m for m in dir(bridge) if m.startswith("asm_")]
    print(f"AssemblyBridge — {len(exposed)} methods exposed to WebView:")
    for name in sorted(exposed):
        doc = getattr(bridge, name).__doc__
        first_line = (doc or "").split("\n")[0].strip() if doc else "(no docstring)"
        print(f"  • {name:30s}  {first_line}")
