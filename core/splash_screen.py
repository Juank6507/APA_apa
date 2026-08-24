# apa/core/splash_screen.py
# MOTOR DE PANTALLA DE CARGA — Splash Screen (Tkinter)
#
# Este modulo define la pantalla de carga para el ensamblador GUI.
# Los tokens visuales se importan de apa_theme.py (fuente de verdad).
#
# USO (ensamblador_gui.py):
#   from apa.core.splash_screen import SplashScreen
#   splash = SplashScreen(root)
#   splash.update_status("Cargando...")
#   splash.close()

# ============================================================================
# TOKENS VISUALES — Importados del tema unificado (apa_theme.py)
# ============================================================================
try:
    from apa.core.apa_theme import (
        THEME_SPLASH_BG, THEME_SPLASH_TITLE,
        THEME_SPLASH_SUBTITLE, THEME_SPLASH_STATUS, THEME_SPLASH_READY,
        THEME_FONT_SANS,
    )
    SPLASH_BG_COLOR = THEME_SPLASH_BG
    SPLASH_TITLE_COLOR = THEME_SPLASH_TITLE
    SPLASH_SUBTITLE_COLOR = THEME_SPLASH_SUBTITLE
    SPLASH_STATUS_COLOR = THEME_SPLASH_STATUS
    SPLASH_STATUS_DONE_COLOR = THEME_SPLASH_READY
    SPLASH_FONT_FAMILY = THEME_FONT_SANS
except ImportError:
    # Fallback: si apa_theme no existe, usar valores hardcoded
    SPLASH_BG_COLOR = "#0f172a"
    SPLASH_TITLE_COLOR = "#60a5fa"
    SPLASH_SUBTITLE_COLOR = "#475569"
    SPLASH_STATUS_COLOR = "#94a3b8"
    SPLASH_STATUS_DONE_COLOR = "#22c55e"
    SPLASH_FONT_FAMILY = "Segoe UI"
SPLASH_WIDTH = 420
SPLASH_HEIGHT = 200

# ============================================================================
# MOTOR TKINTER — usado por ensamblador_gui.py
# ============================================================================

def _tk():
    """Lazy import de tkinter para no romper en entornos sin GUI."""
    import tkinter as _tk_mod
    return _tk_mod


class SplashScreen:
    """Ventana de carga ligera para el ensamblador.

    Se muestra inmediatamente al arrancar y se cierra cuando la UI
    principal esta lista para responder. Las operaciones pesadas
    (pool, probes) corren en hilos de fondo mientras el splash
    muestra mensajes de progreso al usuario.

    Uso en ensamblador_gui.py::

        splash = SplashScreen(root)
        splash.update_status("Listo")
        splash.close()

    Al cerrar:
        splash.close()  # Llamar desde el hilo principal
    """

    def __init__(self, root):
        self._tk = _tk()
        self.root = root
        self.splash = self._tk.Toplevel(root)
        # NO transient(root): interfere con overrideredirect en Windows
        # y causa problemas de foco al cerrar.
        self.splash.overrideredirect(True)
        self.splash.configure(bg=SPLASH_BG_COLOR)
        self.splash.attributes("-topmost", True)

        w = SPLASH_WIDTH
        h = SPLASH_HEIGHT
        x = (self.splash.winfo_screenwidth() - w) // 2
        y = (self.splash.winfo_screenheight() - h) // 2
        self.splash.geometry(f"{w}x{h}+{x}+{y}")

        self._tk.Label(
            self.splash,
            text="APA \u2014 Ensamblador",
            font=(SPLASH_FONT_FAMILY, 18, "bold"),
            bg=SPLASH_BG_COLOR,
            fg=SPLASH_TITLE_COLOR,
        ).pack(pady=(30, 5))

        self._tk.Label(
            self.splash,
            text="At\u00f3mico v4.0",
            font=(SPLASH_FONT_FAMILY, 10),
            bg=SPLASH_BG_COLOR,
            fg=SPLASH_SUBTITLE_COLOR,
        ).pack()

        self.status = self._tk.Label(
            self.splash,
            text="Iniciando...",
            font=(SPLASH_FONT_FAMILY, 10),
            bg=SPLASH_BG_COLOR,
            fg=SPLASH_STATUS_COLOR,
        )
        self.status.pack(pady=(15, 0))

        self.progress = self._tk.ttk.Progressbar(
            self.splash, mode="indeterminate", length=300
        )
        self.progress.pack(pady=15)
        self.progress.start(10)

    def update_status(self, message: str):
        """Actualiza el mensaje de estado (seguro desde cualquier hilo)."""
        try:
            self.status.config(text=message)
            self.splash.update_idletasks()
        except self._tk.TclError:
            pass  # Ventana ya cerrada

    def set_ready(self):
        """Marca como listo con color verde."""
        try:
            self.status.config(
                text="Listo",
                fg=SPLASH_STATUS_DONE_COLOR,
            )
            self.splash.update_idletasks()
        except self._tk.TclError:
            pass

    def close(self):
        """Cierra el splash y devuelve el foco a la ventana principal.

        Problema en Windows: destruir un Toplevel con overrideredirect
        + -topmost hace que Windows pierda la relacion de foco.

        Solucion: El truco "topmost toggle" en root.
        -topmost en Tkinter usa SetWindowPos(HWND_TOPMOST) que
        BYPASSEA la restriccion de SetForegroundWindow de Windows.

        Debe llamarse desde el hilo principal.
        """
        try:
            self.progress.stop()
        except self._tk.TclError:
            pass

        # Paso 1: Hacer root topmost ANTES de destruir el splash.
        try:
            self.root.attributes('-topmost', True)
            self.root.lift()
        except self._tk.TclError:
            pass

        # Paso 2: Destruir el splash (el foco va a root que ya es topmost)
        try:
            self.splash.destroy()
        except self._tk.TclError:
            pass

        # Paso 3: Quitar topmost de root + forzar foco
        try:
            self.root.after(100, self._restore_root_focus)
        except Exception:
            pass

    def _restore_root_focus(self):
        """Restaura estado normal de root y fuerza foco."""
        try:
            self.root.attributes('-topmost', False)
            self.root.focus_force()
        except self._tk.TclError:
            pass

        # Backup nuclear: ctypes SetForegroundWindow (solo Windows)
        try:
            import ctypes
            hwnd = int(self.root.winfo_id())
            ctypes.windll.user32.SetForegroundWindow(hwnd)
        except Exception:
            pass


# ============================================================================
# VALIDACION
# ============================================================================

if __name__ == "__main__":
    print("=== splash_screen.py — Validacion ===")
    print(f"Background: {SPLASH_BG_COLOR}")
    print(f"Title color: {SPLASH_TITLE_COLOR}")
    print(f"Status color: {SPLASH_STATUS_COLOR}")
    print(f"Ready color: {SPLASH_STATUS_DONE_COLOR}")
    print("Validacion OK")
