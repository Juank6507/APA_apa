# apa/skills/gui_integration.py
SKILL = {
    "name": "gui_integration",
    "language": "python",
    "keywords": [
        "gui integration", "threading", "background task", "module",
        "orchestrate", "desktop app", "long running", "worker thread",
        "progress bar", "after", "queue", "background process",
        "integrate module", "desktop application", "async gui",
        "task worker", "ui update", "callback thread"
    ],
    "prompt_fragment": """
## GUI INTEGRATION BEST PRACTICES

### Architecture Pattern
- Use an orchestrator class (main application) that creates and manages all UI controls.
- Keep business logic modules completely INDEPENDENT from tkinter. They should work as plain Python classes/functions.
- The orchestrator registers controls for centralized management (validation, enable/disable, data collection).
- Structure: `logic_module.py` (no tkinter) + `main_app.py` (tkinter GUI that imports logic_module).

### Threading for Long Operations
- When a module performs a long operation (file parsing, network request, data processing), it MUST run in a separate thread.
- Pattern: `threading.Thread(target=self._worker, daemon=True).start()`
- The worker thread puts results into a `queue.Queue`.
- The main thread polls the queue using `self.after(100, self._check_queue)` every 100ms.
- NEVER update widgets directly from a worker thread. Always go through `after()` + queue.

### Updating UI from Background Tasks
- Use `widget.after(milliseconds, callback_function)` to schedule UI updates from the main thread.
- For progress reporting: worker thread puts progress % into queue, main thread updates a `ttk.Progressbar`.
- For results: worker thread puts final data into queue, main thread displays it in the UI.
- Always handle the case where the user closes the window while a thread is running (check a `self.running` flag).

### Error Handling in Multi-Module Apps
- Each module should raise its own specific exceptions, not generic ones.
- The orchestrator catches exceptions in threads and displays them via `messagebox.showerror()` on the main thread.
- Use `logging` module for diagnostic messages, not `print()`.

### Data Flow Pattern
1. User fills form -> clicks "Process" button
2. Button callback validates input (on main thread)
3. Button callback starts worker thread with validated parameters
4. Button callback disables "Process" button and shows progress bar
5. Worker thread does the work, puts result in queue
6. Main thread polls queue via `after()`, receives result
7. Main thread updates UI with result, re-enables button

### Module Communication
- Use composition, not inheritance, to connect modules to the GUI.
- Pass data through method calls: `module.process(data)` -> returns result.
- For real-time updates, use callbacks: `module.on_progress = lambda p: queue.put(("progress", p))`.
- Keep module interfaces simple: one entry point, one result, optional progress callback.
""",
    "example_code": """
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import queue
import time


class DataProcessor:
    \"\"\"Modulo de logica de negocio SIN dependencias de tkinter.\"\"\"

    def __init__(self):
        self.on_progress = None  # Callback de progreso opcional

    def process(self, data: str, items: int) -> dict:
        \"\"\"Procesamiento largo simulado. Retorna resultado.\"\"\"
        result = {"processed": 0, "errors": []}
        for i in range(items):
            # Simular trabajo
            time.sleep(0.1)
            try:
                if len(data) < 2:
                    raise ValueError(f"Item {i}: dato demasiado corto")
                result["processed"] += 1
            except ValueError as e:
                result["errors"].append(str(e))
            # Reportar progreso si hay callback
            if self.on_progress:
                self.on_progress((i + 1) / items)
        return result


class AppPrincipal(tk.Tk):
    \"\"\"Aplicacion principal que integra el modulo DataProcessor con GUI.\"\"\"

    def __init__(self):
        super().__init__()
        self.title("Procesador de Datos")
        self.geometry("450x300")
        self.resizable(False, False)

        # Cola para comunicacion thread -> mainloop
        self.cola_resultados = queue.Queue()
        self.procesando = False

        # Modulo de logica (sin tkinter)
        self.procesador = DataProcessor()
        self.procesador.on_progress = self._reportar_progreso

        self._crear_interfaz()
        self._centrar_ventana()

    def _crear_interfaz(self):
        marco = ttk.Frame(self, padding=20)
        marco.pack(fill="both", expand=True)

        ttk.Label(marco, text="Datos:").grid(row=0, column=0, sticky="w", pady=5)
        self.entrada = ttk.Entry(marco, width=30)
        self.entrada.grid(row=0, column=1, pady=5)
        self.entrada.insert(0, "dato de ejemplo")

        ttk.Label(marco, text="Items:").grid(row=1, column=0, sticky="w", pady=5)
        self.items_var = tk.IntVar(value=10)
        ttk.Spinbox(marco, from_=1, to=100, textvariable=self.items_var, width=28).grid(row=1, column=1, pady=5)

        # Barra de progreso
        self.barra = ttk.Progressbar(marco, maximum=100, mode="determinate")
        self.barra.grid(row=2, column=0, columnspan=2, sticky="ew", pady=10)

        self.etiqueta_estado = ttk.Label(marco, text="Listo")
        self.etiqueta_estado.grid(row=3, column=0, columnspan=2)

        # Botones
        marco_botones = ttk.Frame(marco)
        marco_botones.grid(row=4, column=0, columnspan=2, pady=10)
        self.btn_procesar = ttk.Button(marco_botones, text="Procesar", command=self._iniciar_procesamiento, width=12)
        self.btn_procesar.pack(side="left", padx=5)
        ttk.Button(marco_botones, text="Salir", command=self._salir, width=12).pack(side="left", padx=5)

        # Protocolo de cierre
        self.protocol("WM_DELETE_WINDOW", self._salir)

    def _centrar_ventana(self):
        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    def _iniciar_procesamiento(self):
        try:
            data = self.entrada.get().strip()
            items = self.items_var.get()
            if not data:
                messagebox.showwarning("Validacion", "Ingrese datos.")
                return
            self.procesando = True
            self.btn_procesar.config(state="disabled")
            self.barra["value"] = 0
            self.etiqueta_estado.config(text="Procesando...")
            # Iniciar worker thread
            threading.Thread(target=self._worker, args=(data, items), daemon=True).start()
            # Iniciar polling de la cola
            self.after(100, _check_queue)
        except Exception as e:
            messagebox.showerror("Error", f"Error al iniciar: {e}")
            self._resetear_ui()

    def _worker(self, data: str, items: int):
        \"\"\"Worker thread: ejecuta logica pesada y pone resultado en cola.\"\"\"
        try:
            resultado = self.procesador.process(data, items)
            self.cola_resultados.put(("resultado", resultado))
        except Exception as e:
            self.cola_resultados.put(("error", str(e)))

    def _check_queue(self):
        \"\"\"Polling: revisa la cola desde el main thread.\"\"\"
        try:
            while True:
                tipo, valor = self.cola_resultados.get_nowait()
                if tipo == "progress":
                    self.barra["value"] = valor * 100
                    self.etiqueta_estado.config(text=f"Procesando... {int(valor * 100)}%")
                elif tipo == "resultado":
                    self._mostrar_resultado(valor)
                    return
                elif tipo == "error":
                    messagebox.showerror("Error", f"Error en procesamiento: {valor}")
                    self._resetear_ui()
                    return
        except queue.Empty:
            pass
        if self.procesando:
            self.after(100, _check_queue)

    def _reportar_progreso(self, fraccion: float):
        \"\"\"Callback desde el worker (se ejecuta EN el worker thread).\"\"\"
        self.cola_resultados.put(("progress", fraccion))

    def _mostrar_resultado(self, resultado: dict):
        self.procesando = False
        self.etiqueta_estado.config(text=f"Completado: {resultado['processed']} procesados")
        messagebox.showinfo("Resultado", f"Procesados: {resultado['processed']}\\nErrores: {len(resultado['errors'])}")
        self._resetear_ui()

    def _resetear_ui(self):
        self.procesando = False
        self.btn_procesar.config(state="normal")
        self.barra["value"] = 0
        self.etiqueta_estado.config(text="Listo")

    def _salir(self):
        self.procesando = False
        self.destroy()


# Funcion de polling como closure para evitar problemas con self
def _check_queue():
    app = AppPrincipal._instancia if hasattr(AppPrincipal, "_instancia") else None
    if app:
        app._check_queue()


if __name__ == "__main__":
    app = AppPrincipal()
    AppPrincipal._instancia = app  # Para acceso desde polling
    # Sobrescribir el metodo de cola para usar self directamente
    app.after(100, app._check_queue)
    app.mainloop()
"""
}

if __name__ == "__main__":
    assert "SKILL" in globals(), "Variable SKILL no encontrada"
    skill = SKILL
    required_keys = ["name", "language", "keywords", "prompt_fragment", "example_code"]
    for key in required_keys:
        assert key in skill, f"Falta clave obligatoria: {key}"
    assert skill["language"] == "python", "El lenguaje debe ser 'python'"
    assert skill["name"] == "gui_integration", "El nombre debe ser 'gui_integration'"
    assert len(skill["keywords"]) >= 10, "Debe tener al menos 10 keywords"
    assert len(skill["prompt_fragment"]) > 500, "El prompt_fragment es demasiado corto"
    assert "threading" in skill["prompt_fragment"].lower(), "Debe mencionar threading"
    assert "queue" in skill["prompt_fragment"].lower(), "Debe mencionar queue"
    assert "after" in skill["prompt_fragment"].lower(), "Debe mencionar after()"
    assert "threading" in skill["example_code"], "El ejemplo debe usar threading"
    assert "mainloop" in skill["example_code"], "El ejemplo debe llamar a mainloop"
    print("✅ gui_integration skill validado correctamente")
