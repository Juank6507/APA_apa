# apa/skills/tkinter_gui.py
SKILL = {
    "name": "tkinter_gui",
    "language": "python",
    "keywords": [
        "tkinter", "gui", "form", "window", "textbox", "combobox", "checkbox",
        "desktop", "entry", "button", "buttons", "frame", "label", "labels", "text",
        "listbox", "radiobutton", "spinbox", "scale", "slider", "menu", "dialog",
        "mainwindow", "toplevel", "application", "widget", "widgets",
        "interfaz grafica", "ventana", "formulario", "cuadro de texto", "lista",
        "selector fecha", "selector hora", "cargar fichero", "deslizante",
        "option group", "page", "pestana",
        "formulario framework", "agregar_textbox", "agregar_combobox", "agregar_checkbox",
        "agregar_optiongroup", "agregar_listbox", "agregar_page", "agregar_selectorfecha",
        "agregar_selectorhora", "agregar_cargarfichero", "agregar_deslizante",
        "mascara", "input masking", "autocomplete", "buscador cadena",
        "enviar_datos", "flujo formulario", "posicionar_objeto",
        "headless", "xvfb"
    ],
    "prompt_fragment": """
## TKINTER GUI BEST PRACTICES

### Approach Selection: Formulario Framework vs Raw Tkinter

**IMPORTANT:** For any form with 3 or more input controls, PREFER the Formulario framework.
Use raw tkinter only for simple dialogs (1-2 fields), custom drawing, or non-form UI.

| Scenario | Recommended Approach |
|---|---|
| Simple dialog (1-2 fields) | Raw `tk.Tk` / `ttk` |
| Multi-field form (3+ controls) | **Formulario framework** |
| Form with validation/masking | **Formulario framework** |
| Tabbed/multi-page forms | **Formulario framework** |
| Custom canvas drawing | Raw tkinter |
| Non-standard widgets | Raw tkinter |

---

## FORMULARIO FRAMEWORK (RECOMMENDED for forms)

### Module Location & Import
```python
# Formulario is a sibling directory of apa/ inside the project root.
# Detect it automatically so it works on any machine (Linux, Windows, Mac).
import sys, os
_FORMULARIO_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'Formulario')
if _FORMULARIO_DIR not in sys.path:
    sys.path.insert(0, os.path.abspath(_FORMULARIO_DIR))
from Formulario import Formulario
```

### Headless Environments
Tkinter requires a display server. In headless/server environments, wrap execution with:
```bash
xvfb-run python tu_script.py
```

### Core Concepts

The `Formulario` class wraps `tk.Tk()` and provides a factory-method API:
- **Constructor:** `Formulario(titulo, iconimagen, cerrar_al_salir=True)`
  - Creates the root `tk.Tk()` window automatically
  - Sets up `WM_DELETE_WINDOW` protocol and auto-focus flow
  - `iconimagen`: filename of .ico in the `Formulario/Imagenes/` directory (fallback: `img_vacia_xsk_icon.ico`)
- **Main window:** accessed as `formulario.ventana`
- **Controls registry:** all input controls are auto-registered in `formulario.controles`

### Lifecycle Methods
```python
formulario = Formulario("Mi Formulario", "img_vacia_xsk_icon.ico")
# ... create controls ...
formulario.mostrar()       # calls ventana.deiconify() + ventana.mainloop()
formulario.enviar_datos()  # validates all controls, disables on success
formulario.salir()         # destroys or withdraws the window
formulario.on_closing()    # handles WM_DELETE_WINDOW
```

### Layout Methods
```python
formulario.posicionar_objeto(widget, 'grid', row=0, column=0, padx=10, pady=5, sticky="w")
formulario.posicionar_objeto(widget, 'pack', side=tk.LEFT, padx=5)
formulario.posicionar_objeto(widget, 'place', x=100, y=50)
formulario.posicionar_centrado()  # center window on screen
formulario.ventana.geometry("800x600")  # set window size
formulario.ventana.grid_rowconfigure(0, weight=1)  # allow expansion
formulario.ventana.grid_columnconfigure(0, weight=1)
```

### Container Methods
```python
marco = formulario.agregar_marco(contenedor, bd=2, relief="groove")
seccion = formulario.agregar_etiqueta_marco(contenedor, descripcion="SECCION")
etiqueta = formulario.agregar_etiqueta(contenedor, descripcion="Texto:")
```

### Widget Factory Methods (agregar_*) Reference

All `agregar_*` methods return a control object. Pass `contenedor` (or `False` for root window).
Arguments can be positional or keyword.

#### agregar_textbox(contenedor, ...) -> Textbox
Multi-purpose text input with masking, validation, and autocomplete.
```python
ctrl = formulario.agregar_textbox(
    contenedor,
    titulo_control="Nombre:",          # label text
    tipo_validacion="str",            # "str", "int", "float", "fecha", "hora", "email"
    restricciones={},                 # {"min": 0, "max": 100} or {"length": 50}
    mascara="",                       # e.g. "DD/MM/AAAA", "HH:MM", "########-#"
    caracteres_fijos="",              # e.g. "/", ":", "-"
    ancho=20,                         # field width in characters
    fuente_datos=None,                # dict {id: valor} for autocomplete
    modo_busqueda="inicio",           # "inicio", "contenido"
    permite_agregar=False,            # allow adding new values to autocomplete
    altura=1                          # text area height (>1 for multiline)
)
```
- **Mask tokens:** `D`=day, `M`=month, `A`=year digit, `H`=hour, `MM`=minute, `#`=any digit
- **Get value:** `ctrl.obtener_valor()` (raw), `ctrl.get()` (formatted string)
- **Set value:** `ctrl.establecer_valor("value")`, `ctrl.set("value")`
- **Clear:** `ctrl.limpiar()`
- **Disable:** `ctrl.set_estado("disabled")` or `ctrl.habilitar(False)`

#### agregar_combobox(contenedor, ...) -> Combobox
Dropdown selection with optional autocomplete from data source.
```python
ctrl = formulario.agregar_combobox(
    contenedor,
    titulo_control="Profesion:",
    ancho=20,
    valores=["Opcion1", "Opcion2"],   # dropdown items
    estado="readonly",                # "readonly" or "normal"
    fuente_datos=None,                # dict {id: valor} for autocomplete
    modo_busqueda="inicio"
)
```
- **Get:** `ctrl.get()` returns selected string
- **Set:** `ctrl.set("valor")`

#### agregar_optiongroup(contenedor, ...) -> OptionGroup
Radio button group for selecting one option from a list.
```python
ctrl = formulario.agregar_optiongroup(
    contenedor,
    titulo_control="Estado civil:",
    opciones=[("S", "Soltero/a"), ("C", "Casado/a"), ("D", "Divorciado/a")],
    valor_inicial="S",
    orientacion="vertical",           # "vertical" or "horizontal"
    comando=None                      # callback(control.get())
)
```
- **Get:** `ctrl.get()` returns the value key (e.g. "S")

#### agregar_listbox(contenedor, ...) -> Listbox
Searchable list with autocomplete filter textbox.
```python
ctrl = formulario.agregar_listbox(
    contenedor,
    titulo_control="Departamento:",
    fuente_datos={"RRHH": "Recursos Humanos", "VENT": "Ventas"},
    altura=5,
    ancho=25,
    modo_busqueda="contenido"         # "inicio" or "contenido"
)
```
- **Get filter text:** `ctrl.textbox_filtro.get()`
- **Clear:** `ctrl.limpiar()`

#### agregar_page(contenedor, ...) -> Page
Tabbed page container (notebook tab) for multi-page forms.
```python
page = formulario.agregar_page(
    contenedor,
    titulo="Datos Personales",
    ancho=600, alto=400,
    padding=20,
    color_fondo="#f0f0f0"
)
# Then add controls to page instead of the main container
formulario.agregar_textbox(page, titulo_control="Nombre:")
```

#### agregar_checkbox(contenedor, ...) -> Checkbox
Single checkbox (boolean).
```python
ctrl = formulario.agregar_checkbox(
    contenedor,
    titulo="Acepto los terminos",
    valor_inicial=False,
    comando=None                      # callback(ctrl.get())
)
```
- **Get:** `ctrl.get()` returns `True`/`False`
- **Set:** `ctrl.set(True)`
- **Toggle:** `ctrl.toggle()`

#### agregar_selectorfecha(contenedor, ...) -> SelectorFecha
Date picker (requires `tkcalendar` package, falls back to text entry).
```python
ctrl = formulario.agregar_selectorfecha(
    contenedor,
    titulo="Fecha nacimiento:",
    valor_inicial=datetime.date(1990, 1, 1),
    formato="%d/%m/%Y",
    min_fecha=None,                   # optional datetime.date
    max_fecha=None
)
```
- **Get:** `ctrl.get()` returns `datetime.date`, `ctrl.get_str()` returns formatted string
- **Set:** `ctrl.set(datetime.date(2025, 1, 1))` or `ctrl.set("01/01/2025")`

#### agregar_selectorhora(contenedor, ...) -> SelectorHora
Time picker with spinboxes.
```python
ctrl = formulario.agregar_selectorhora(
    contenedor,
    titulo="Hora entrada:",
    valor_inicial=datetime.time(8, 0),
    formato="%H:%M",
    intervalo_minutos=5,
    mostrar_segundos=False
)
```
- **Get:** `ctrl.get()` returns `datetime.time`, `ctrl.get_str()` returns formatted string
- **Set:** `ctrl.set(datetime.time(14, 30))`

#### agregar_cargarfichero(contenedor, ...) -> CargarFichero
File picker with path display.
```python
ctrl = formulario.agregar_cargarfichero(
    contenedor,
    titulo="Archivo:",
    tipos_archivo=[("Documentos", "*.pdf *.doc *.docx"), ("Todos", "*.*")],
    directorio_inicial=os.path.expanduser("~"),
    modo="abrir"                      # "abrir" or "guardar"
)
```
- **Get:** `ctrl.get()` returns file path string or `None`

#### agregar_deslizante(contenedor, ...) -> Deslizante
Slider for selecting a numeric value in a range.
```python
ctrl = formulario.agregar_deslizante(
    contenedor,
    titulo="Porcentaje:",
    valor_inicial=50,
    valor_minimo=0,
    valor_maximo=100,
    orientacion="horizontal",
    incremento=5,
    mostrar_valor=True
)
```
- **Get:** `ctrl.get()` returns float/int
- **Set:** `ctrl.set(75)`

#### agregar_boton(contenedor, caption, comando, ancho) -> ttk.Button
```python
btn = formulario.agregar_boton(contenedor, "Enviar", mi_funcion, 12)
```

### Form Flow & Validation
- Controls auto-chain focus on `<<SiguienteWidget>>` event (Tab key or Enter)
- `formulario.flujo_formulario()` validates current control, moves focus to next
- `formulario.enviar_datos()` validates ALL controls, shows errors, disables on success
- `formulario.deshabilitar_todos_los_controles()` locks all inputs after submission

### Complete Formulario Example Pattern
```python
import sys, os, datetime
# Auto-detect Formulario directory (works on any OS)
_FORMULARIO_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'Formulario')
sys.path.insert(0, os.path.abspath(_FORMULARIO_DIR))
from Formulario import Formulario

class MiFormulario:
    def __init__(self):
        self.form = Formulario("Registro", "img_vacia_xsk_icon.ico")
        self.form.ventana.geometry("500x400")

        marco = self.form.agregar_marco(self.form.ventana, bd=2, relief="groove")
        self.form.posicionar_objeto(marco, 'grid', row=0, column=0, padx=10, pady=10)

        self.nombre = self.form.agregar_textbox(marco, "Nombre:", tipo_validacion="str", ancho=30)
        self.form.posicionar_objeto(self.nombre, 'grid', row=0, column=0, pady=5)

        self.fecha = self.form.agregar_selectorfecha(marco, "Fecha:", formato="%d/%m/%Y")
        self.form.posicionar_objeto(self.fecha, 'grid', row=1, column=0, pady=5)

        self.acepto = self.form.agregar_checkbox(marco, "Acepto terminos")
        self.form.posicionar_objeto(self.acepto, 'grid', row=2, column=0, pady=5)

        btn = self.form.agregar_boton(marco, "Enviar", self._enviar, 12)
        self.form.posicionar_objeto(btn, 'grid', row=3, column=0, pady=10)
        self.form.boton_validar = btn  # enable auto-focus to button after last field

        self.form.posicionar_centrado()

    def _enviar(self):
        try:
            self.form.enviar_datos()
            nombre = self.nombre.obtener_valor()
            fecha = self.fecha.get_str()
            print(f"Datos: {nombre}, {fecha}")
        except Exception as e:
            print(f"Error: {e}")

    def ejecutar(self):
        self.form.mostrar()

if __name__ == "__main__":
    MiFormulario().ejecutar()
```

---

## RAW TKINTER BEST PRACTICES (for simple dialogs)

### Architecture
- Create a main application class that inherits from `tk.Tk` or uses a `Formulario` class.
- Each section of the UI should be a `tk.Frame` or `ttk.Frame` (separation of concerns).
- Keep the UI code separate from business logic. The UI should only handle display and user input.
- Register all input controls in a list for centralized validation and management.

### Variables and Data Binding
- ALWAYS use `tk.StringVar`, `tk.IntVar`, `tk.DoubleVar`, or `tk.BooleanVar` to bind data to widgets.
- Never read widget values directly with `.get("1.0", tk.END)` for input tracking; use the variable instead.
- Set initial values via the variable, not the widget: `var.set("default")`.

### Event Handling
- Every callback bound to a button or event MUST have a `try/except` block. Uncaught exceptions in Tkinter callbacks crash silently.
- Use `widget.bind("<FocusOut>", callback)` to validate when the user leaves a field.
- Use `<<SiguienteWidget>>` or `Tab` binding to move focus between fields in order.
- NEVER call `time.sleep()` or long operations inside a callback. Use `threading.Thread(daemon=True)` + `widget.after()`.

### Layout
- Choose ONE layout manager per container: `grid` for forms, `pack` for simple stacking, `place` only for absolute positioning.
- Mix managers only across DIFFERENT containers (e.g., `grid` in the main frame, `pack` inside a sub-frame).
- Always call `grid_rowconfigure()` / `grid_columnconfigure()` with `weight=1` for resizable areas.

### Input Validation
- Validate user input on `<FocusOut>` or when a "Submit" button is pressed, NOT on every keystroke.
- Use Python's `re` module for pattern validation (emails, phone numbers, postal codes).
- For masked inputs (dates, times), store the raw user input separately from the formatted display.
- Display validation errors using `messagebox.showwarning()` or inline labels, never crash.

### Threading Rules
- Tkinter is NOT thread-safe. Only modify widgets from the main thread.
- For long tasks: start a `threading.Thread`, do the work, then use `root.after(0, callback)` to update the UI.
- Use `queue.Queue` to pass results from the worker thread to the main thread.

### Window Management
- Always center the window on screen after creation: calculate x = (screen_width - window_width) // 2.
- Set `resizable(False, False)` on dialog windows that should not be resized.
- Handle the window close button: `root.protocol("WM_DELETE_WINDOW", on_closing)`.

### Common Pitfalls to AVOID
- NEVER block the mainloop with `while True` or `time.sleep()`.
- NEVER forget `root.mainloop()` at the end of the script.
- NEVER mix `import tkinter as tk` and `from tkinter import *` in the same file.
- NEVER create widgets before `tk.Tk()` is instantiated.
- NEVER use `global` variables for widget references; store them as instance attributes.
""",
    "example_code": """
# === EXAMPLE 1: Formulario Framework (RECOMMENDED for 3+ fields) ===
import sys
import os
import datetime
# Auto-detect Formulario directory (works on any OS)
_FORMULARIO_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'Formulario')
sys.path.insert(0, os.path.abspath(_FORMULARIO_DIR))
from Formulario import Formulario


class RegistroFormulario:
    '''Complete form using the Formulario framework with masked inputs,
    date picker, autocomplete, and automatic validation.'''

    def __init__(self):
        self.formulario = Formulario(
            titulo="Registro de Empleado",
            iconimagen="img_vacia_xsk_icon.ico",
            cerrar_al_salir=True
        )
        self.formulario.ventana.geometry("700x550")

        # Data sources for autocomplete
        self.ciudades = {
            "001": "Madrid", "002": "Barcelona", "003": "Valencia",
            "004": "Sevilla", "005": "Malaga"
        }
        self.departamentos = {
            "RRHH": "Recursos Humanos", "CONT": "Contabilidad",
            "VENT": "Ventas", "PROD": "Produccion", "SIST": "Sistemas"
        }
        self._crear_interfaz()
        self.formulario.posicionar_centrado()

    def _crear_interfaz(self):
        marco = self.formulario.agregar_marco(
            self.formulario.ventana, bd=2, relief="groove"
        )
        self.formulario.posicionar_objeto(
            marco, 'grid', row=0, column=0, padx=10, pady=10, sticky="nsew"
        )
        self.formulario.ventana.grid_rowconfigure(0, weight=1)
        self.formulario.ventana.grid_columnconfigure(0, weight=1)

        # Section: Personal data
        seccion1 = self.formulario.agregar_etiqueta_marco(
            marco, descripcion="DATOS PERSONALES"
        )
        self.formulario.posicionar_objeto(
            seccion1, 'grid', row=0, column=0, columnspan=2,
            padx=10, pady=10, sticky="ew"
        )

        self.nombre = self.formulario.agregar_textbox(
            seccion1, titulo_control="Nombre completo:",
            tipo_validacion="str", ancho=35
        )
        self.formulario.posicionar_objeto(
            self.nombre, 'grid', row=0, column=0, padx=5, pady=5, sticky="w"
        )

        self.cedula = self.formulario.agregar_textbox(
            seccion1, titulo_control="Cedula:",
            mascara="########-#", caracteres_fijos="-",
            tipo_validacion="str", ancho=15
        )
        self.formulario.posicionar_objeto(
            self.cedula, 'grid', row=1, column=0, padx=5, pady=5, sticky="w"
        )

        self.email = self.formulario.agregar_textbox(
            seccion1, titulo_control="Email:",
            tipo_validacion="email", ancho=35
        )
        self.formulario.posicionar_objeto(
            self.email, 'grid', row=2, column=0, padx=5, pady=5, sticky="w"
        )

        # Section: Dates, selection, files
        seccion2 = self.formulario.agregar_etiqueta_marco(
            marco, descripcion="FECHAS, SELECCION Y ARCHIVOS"
        )
        self.formulario.posicionar_objeto(
            seccion2, 'grid', row=1, column=0, columnspan=2,
            padx=10, pady=10, sticky="ew"
        )

        self.fecha = self.formulario.agregar_selectorfecha(
            seccion2, titulo="Fecha nacimiento:",
            valor_inicial=datetime.date(1990, 1, 1), formato="%d/%m/%Y"
        )
        self.formulario.posicionar_objeto(
            self.fecha, 'grid', row=0, column=0, padx=5, pady=5, sticky="w"
        )

        self.ciudad = self.formulario.agregar_textbox(
            seccion2, titulo_control="Ciudad:",
            tipo_validacion="str", fuente_datos=self.ciudades,
            modo_busqueda="inicio", ancho=25
        )
        self.formulario.posicionar_objeto(
            self.ciudad, 'grid', row=0, column=1, padx=5, pady=5, sticky="w"
        )

        self.departamento = self.formulario.agregar_listbox(
            seccion2, titulo_control="Departamento:",
            fuente_datos=self.departamentos, altura=4, ancho=25
        )
        self.formulario.posicionar_objeto(
            self.departamento, 'grid', row=1, column=0, padx=5, pady=5, sticky="w"
        )

        self.archivo = self.formulario.agregar_cargarfichero(
            seccion2, titulo="Curriculum:",
            tipos_archivo=[("Documentos", "*.pdf *.docx"), ("Todos", "*.*")]
        )
        self.formulario.posicionar_objeto(
            self.archivo, 'grid', row=1, column=1, padx=5, pady=5, sticky="w"
        )

        # Section: Preferences
        self.acepto = self.formulario.agregar_checkbox(
            seccion2, titulo="Acepto los terminos y condiciones",
            valor_inicial=False
        )
        self.formulario.posicionar_objeto(
            self.acepto, 'grid', row=2, column=0, columnspan=2,
            padx=5, pady=5, sticky="w"
        )

        # Buttons
        frame_btn = tk.Frame(marco)
        self.formulario.posicionar_objeto(
            frame_btn, 'grid', row=2, column=0, columnspan=2, pady=15
        )
        btn_enviar = self.formulario.agregar_boton(
            frame_btn, "Enviar", self._enviar, 12
        )
        self.formulario.posicionar_objeto(btn_enviar, 'pack', side=tk.LEFT, padx=5)
        self.formulario.boton_validar = btn_enviar

        btn_mostrar = self.formulario.agregar_boton(
            frame_btn, "Ver Datos", self._mostrar_datos, 12
        )
        self.formulario.posicionar_objeto(btn_mostrar, 'pack', side=tk.LEFT, padx=5)

        btn_limpiar = self.formulario.agregar_boton(
            frame_btn, "Limpiar", self._limpiar, 12
        )
        self.formulario.posicionar_objeto(btn_limpiar, 'pack', side=tk.LEFT, padx=5)

    def _enviar(self):
        try:
            self.formulario.enviar_datos()
            nombre = self.nombre.obtener_valor()
            cedula = self.cedula.obtener_valor()
            email = self.email.obtener_valor()
            fecha = self.fecha.get_str()
            print(f"Registro exitoso: {nombre} ({cedula}), {email}, nacido {fecha}")
        except Exception as e:
            print(f"Error al enviar: {e}")

    def _mostrar_datos(self):
        try:
            datos = (
                f"Nombre: {self.nombre.obtener_valor()}\\n"
                f"Cedula: {self.cedula.obtener_valor()}\\n"
                f"Email: {self.email.obtener_valor()}\\n"
                f"Fecha: {self.fecha.get_str()}\\n"
                f"Ciudad: {self.ciudad.obtener_valor()}\\n"
                f"Archivo: {self.archivo.get() or 'No seleccionado'}\\n"
                f"Acepta: {self.acepto.get()}"
            )
            print(datos)
        except Exception as e:
            print(f"Error: {e}")

    def _limpiar(self):
        try:
            self.nombre.establecer_valor("")
            self.cedula.establecer_valor("")
            self.email.establecer_valor("")
            self.ciudad.establecer_valor("")
            self.departamento.limpiar()
            self.fecha.set(datetime.date.today())
            self.acepto.set(False)
        except Exception as e:
            print(f"Error al limpiar: {e}")

    def ejecutar(self):
        self.formulario.mostrar()


if __name__ == "__main__":
    RegistroFormulario().ejecutar()


# === EXAMPLE 2: Raw Tkinter (for simple 1-2 field dialogs) ===
import tkinter as tk
from tkinter import ttk, messagebox


class AppFormulario(tk.Tk):
    \"\"\"Simple form using raw tkinter. Use only for 1-2 field dialogs.\"\"\"

    def __init__(self):
        super().__init__()
        self.title("Dialogo Simple")
        self.geometry("500x400")
        self.resizable(False, False)
        self.controles = []
        self._crear_interfaz()
        self._centrar_ventana()

    def _crear_interfaz(self):
        marco = ttk.Frame(self, padding=20)
        marco.pack(fill="both", expand=True)

        # --- Nombre ---
        ttk.Label(marco, text="Nombre:").grid(row=0, column=0, sticky="w", pady=5)
        self.nombre_var = tk.StringVar()
        entrada_nombre = ttk.Entry(marco, textvariable=self.nombre_var, width=30)
        entrada_nombre.grid(row=0, column=1, pady=5)
        self.controles.append(entrada_nombre)

        # --- Email ---
        ttk.Label(marco, text="Email:").grid(row=1, column=0, sticky="w", pady=5)
        self.email_var = tk.StringVar()
        entrada_email = ttk.Entry(marco, textvariable=self.email_var, width=30)
        entrada_email.grid(row=1, column=1, pady=5)
        self.controles.append(entrada_email)

        # --- Edad ---
        ttk.Label(marco, text="Edad:").grid(row=2, column=0, sticky="w", pady=5)
        self.edad_var = tk.IntVar(value=18)
        spin_edad = ttk.Spinbox(marco, from_=1, to=120, textvariable=self.edad_var, width=28)
        spin_edad.grid(row=2, column=1, pady=5)
        self.controles.append(spin_edad)

        # --- Aceptar terminos ---
        self.acepta_var = tk.BooleanVar()
        chk = ttk.Checkbutton(marco, text="Acepto los terminos", variable=self.acepta_var)
        chk.grid(row=3, column=0, columnspan=2, sticky="w", pady=10)

        # --- Botones ---
        marco_botones = ttk.Frame(marco)
        marco_botones.grid(row=4, column=0, columnspan=2, pady=15)
        ttk.Button(marco_botones, text="Enviar", command=self._enviar, width=12).pack(side="left", padx=5)
        ttk.Button(marco_botones, text="Limpiar", command=self._limpiar, width=12).pack(side="left", padx=5)

    def _centrar_ventana(self):
        self.update_idletasks()
        ancho = self.winfo_width()
        alto = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (ancho // 2)
        y = (self.winfo_screenheight() // 2) - (alto // 2)
        self.geometry(f"+{x}+{y}")

    def _validar_email(self, email: str) -> bool:
        import re
        patron = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$"
        return bool(re.match(patron, email))

    def _enviar(self):
        try:
            nombre = self.nombre_var.get().strip()
            email = self.email_var.get().strip()
            edad = self.edad_var.get()

            if not nombre:
                messagebox.showwarning("Validacion", "El nombre es obligatorio.")
                return
            if not self._validar_email(email):
                messagebox.showwarning("Validacion", "El email no es valido.")
                return
            if not self.acepta_var.get():
                messagebox.showwarning("Validacion", "Debe aceptar los terminos.")
                return

            messagebox.showinfo("Exito", f"Registro exitoso para {nombre} ({email}), edad {edad}.")
        except Exception as e:
            messagebox.showerror("Error", f"Error inesperado: {e}")

    def _limpiar(self):
        try:
            self.nombre_var.set("")
            self.email_var.set("")
            self.edad_var.set(18)
            self.acepta_var.set(False)
        except Exception as e:
            messagebox.showerror("Error", f"Error al limpiar: {e}")


if __name__ == "__main__":
    # For raw tkinter dialog:
    # app = AppFormulario()
    # app.mainloop()

    # For Formulario framework (headless safe):
    import subprocess
    subprocess.run(["xvfb-run", "-a", "python", __file__, "--formulario"])
"""
}

if __name__ == "__main__":
    # Validacion atomica del skill tkinter_gui
    assert "SKILL" in globals(), "Variable SKILL no encontrada"
    skill = SKILL
    required_keys = ["name", "language", "keywords", "prompt_fragment", "example_code"]
    for key in required_keys:
        assert key in skill, f"Falta clave obligatoria: {key}"
    assert isinstance(skill["name"], str), "name debe ser string"
    assert isinstance(skill["language"], str), "language debe ser string"
    assert isinstance(skill["keywords"], list), "keywords debe ser lista"
    assert isinstance(skill["prompt_fragment"], str), "prompt_fragment debe ser string"
    assert isinstance(skill["example_code"], str), "example_code debe ser string"
    assert skill["language"] == "python", "El lenguaje debe ser 'python'"
    assert skill["name"] == "tkinter_gui", "El nombre del skill debe ser 'tkinter_gui'"
    assert len(skill["keywords"]) >= 10, "Debe tener al menos 10 keywords"
    assert len(skill["prompt_fragment"]) > 500, "El prompt_fragment es demasiado corto"
    assert "threading" in skill["prompt_fragment"].lower(), "Debe mencionar threading"
    assert "mainloop" in skill["prompt_fragment"].lower(), "Debe mencionar mainloop"
    assert "try" in skill["example_code"], "El ejemplo debe manejar excepciones"
    assert "mainloop" in skill["example_code"], "El ejemplo debe llamar a mainloop"
    # Additional Formulario framework assertions
    assert "Formulario" in skill["prompt_fragment"], "Debe mencionar Formulario framework"
    assert "agregar_textbox" in skill["prompt_fragment"], "Debe documentar agregar_textbox"
    assert "enviar_datos" in skill["prompt_fragment"], "Debe documentar enviar_datos"
    assert "xvfb" in skill["prompt_fragment"], "Debe mencionar xvfb para headless"
    print("✅ tkinter_gui skill validado correctamente")
