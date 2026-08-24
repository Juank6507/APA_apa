# apa/core/tech_domain_map.py
# TDM — Tech Domain Map: Mapeo de dominios, plataformas y funcionalidades
#       a lenguajes, frameworks y herramientas óptimos.
#
# Este módulo es la base de conocimiento que permite a APA decidir
# qué tecnología usar cuando el usuario no lo especifica en el SDD.
#
# Tres capas de mapeo:
#   1. DOMAIN_MAP: tipo de proyecto / plataforma -> lenguaje principal
#   2. SKILL_MAP: funcionalidad requerida -> lenguaje con mejor ecosistema
#   3. FRAMEWORK_MAP: proyecto complejo -> framework recomendado
#
# El planificador consulta estas tablas antes de generar el plan
# para asegurar que cada tarea use la tecnología más adecuada.
# =========================================================================

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass(frozen=True)
class TechRecommendation:
    """Recomendación tecnológica para un dominio o funcionalidad."""
    language: str              # Lenguaje principal (debe existir en language_profiles.py)
    framework: str = ""        # Framework o librería principal
    alternatives: tuple = ()   # Lenguajes alternativos
    keywords: tuple = ()       # Palabras clave para detectar este dominio
    notes: str = ""            # Notas para el planificador


# =========================================================================
# CAPA 1: DOMAIN_MAP
# Relaciona tipos de proyecto y plataformas con el lenguaje óptimo.
# Cuando el usuario dice "quiero un expert advisor" o "necesito una app
# móvil", APA busca aquí qué lenguaje y framework usar.
# =========================================================================

DOMAIN_MAP: List[TechRecommendation] = [
    # --- Trading y Finanzas ---
    TechRecommendation(
        language="cpp",
        framework="MQL4/MQL5",
        keywords=(
            "metatrader", "meta trader", "mt4", "mt5", "expert advisor",
            "ea trading", "indicador tecnico", "custom indicator",
            "mql4", "mql5", "robot trading", "bot trading",
            "forex", "expert advisor", "asesor experto",
        ),
        notes="MetaTrader usa MQL que es derivado de C/C++. Generar código compatible con MQL.",
    ),
    TechRecommendation(
        language="python",
        framework="ccxt / pandas / yfinance",
        keywords=(
            "trading bot", "criptomoneda", "cryptocurrency", "bitcoin",
            "backtesting", "estrategia trading", "portfolio",
            "analisis financiero", "financial analysis", "quant",
            "yahoo finance", "bolsa", "stock market", "algo trading",
            "arbitraje", "crypto bot", "defi",
        ),
        notes="Python domina el ecosistema de trading algorítmico y análisis de datos financieros.",
    ),
    TechRecommendation(
        language="javascript",
        framework="TradingView Pine Script",
        keywords=(
            "tradingview", "pine script", "indicador tradingview",
            "script tradingview", "estrategia tradingview",
            "indicador trading view",
        ),
        notes="TradingView usa Pine Script propio. Generar código en Pine Script v5.",
    ),

    # --- Aplicaciones Móviles ---
    TechRecommendation(
        language="dart",
        framework="Flutter",
        keywords=(
            "app movil", "mobile app", "aplicacion movil", "multiplataforma",
            "cross-platform", "ios y android", "android e ios",
            "app nativa", "flutter",
        ),
        notes="Flutter es la opción óptima para apps multiplataforma nativas con un solo código.",
    ),
    TechRecommendation(
        language="react-native",
        framework="React Native / Expo",
        keywords=(
            "react native", "react-native", "expo", "app react",
            "componente movil", "componente mobile",
            "mobile react", "navigation", "flatlist", "stylesheet",
        ),
        alternatives=("dart",),
        notes="React Native cuando el equipo ya usa React o se prefiere ecosistema JavaScript.",
    ),

    # --- Desarrollo Web ---
    TechRecommendation(
        language="python",
        framework="FastAPI",
        keywords=(
            "api rest", "rest api", "fastapi", "endpoint",
            "servicio web", "web service", "microservicio",
            "backend", "web api",
        ),
        notes="FastAPI es rápido, moderno y con documentación automática. Ideal para APIs.",
    ),
    TechRecommendation(
        language="javascript",
        framework="Express.js / Node.js",
        keywords=(
            "express", "node.js", "nodejs", "servidor node",
            "middleware", "api express", "rest con node",
        ),
        notes="Node.js + Express para APIs cuando el proyecto ya usa JavaScript en frontend.",
    ),
    TechRecommendation(
        language="python",
        framework="Django",
        keywords=(
            "django", "aplicacion web completa", "web app",
            "admin panel", "panel administracion", "cms",
            "ecommerce", "tienda online", "e-commerce",
        ),
        notes="Django incluye ORM, admin, auth y es ideal para aplicaciones web completas.",
    ),
    TechRecommendation(
        language="javascript",
        framework="Next.js / React",
        keywords=(
            "next.js", "nextjs", "react", "frontend", "spa",
            "single page application", "componente web",
            "ssr", "server side rendering",
        ),
        notes="Next.js es el framework React más completo con SSR, routing y optimización.",
    ),

    # --- TypeScript ---
    TechRecommendation(
        language="typescript",
        framework="NestJS / Angular / Deno",
        keywords=(
            "nestjs", "nest js", "angular", "deno",
            "typescript", "typescript backend", "typescript api",
            "decorator", "decorators", "pipe", "pipes",
            "guard", "module nest", "controller nest",
            "typescript puro", "ts project",
        ),
        alternatives=("javascript",),
        notes="TypeScript para backends robustos (NestJS) o apps empresariales (Angular).",
    ),
    TechRecommendation(
        language="typescript",
        framework="Prisma / TypeORM",
        keywords=(
            "prisma", "prisma schema", "prisma client",
            "typeorm", "typeorm entity",
            "datasource prisma",
        ),
        alternatives=("javascript",),
        notes="Prisma y TypeORM son ORMs modernos que usan TypeScript como lenguaje principal.",
    ),
    TechRecommendation(
        language="typescript",
        framework="Next.js (TypeScript) / React con TS",
        keywords=(
            "typescript react", "react typescript", "react tsx",
            "tsx", "typescript frontend",
            "componente tsx", "next.js typescript", "nextjs ts",
        ),
        alternatives=("javascript",),
        notes="Next.js y React se usan con TypeScript en la mayoría de proyectos modernos.",
    ),

    # --- Automatización y Scripts ---
    TechRecommendation(
        language="bash",
        framework="Bash / Shell",
        keywords=(
            "bash", "script shell", "bash script",
            "automatizacion linux", "linux automation",
            "cron", "systemd", "backup automatico", "backup automático",
            "script sistema", "pipeline ci", "devops script",
            "automatizacion", "tarea automatica", "tarea automática",
        ),
        notes="Bash para scripts de sistema, automatización de tareas en Linux/Unix.",
    ),
    TechRecommendation(
        language="python",
        framework="Selenium / Playwright / BeautifulSoup",
        keywords=(
            "web scraping", "scraper", "extraccion web", "crawling",
            "bot web", "automatizacion navegador", "selenium",
            "playwright", "beautifulsoup", "parseo html",
            "scraping", "extraccion datos web",
        ),
        notes="Python domina el web scraping con Selenium, Playwright y BeautifulSoup.",
    ),
    TechRecommendation(
        language="python",
        framework="smtplib / schedule",
        keywords=(
            "bot telegram", "telegram bot", "automatizacion email",
            "email automation", "tarea programada", "scheduled task",
            "notificacion", "alerta automatica",
        ),
        notes="Python tiene librerías maduras para automatización de comunicaciones.",
    ),

    # --- Bases de Datos ---
    TechRecommendation(
        language="sql",
        framework="SQL (SQLite / PostgreSQL / MySQL)",
        keywords=(
            "consulta sql", "sql query", "migracion sql",
            "sql migration", "stored procedure", "trigger",
            "consulta compleja", "query optimization",
            "script sql", "ddl", "alter table", "create index",
            "funcion sql", "vista sql", "sql view",
            "base de datos", "database", "tabla", "table",
            "postgres", "mysql", "sqlite", "create table",
            "select", "insert into", "crud sql",
        ),
        notes="SQL directo para manipulación de datos, migraciones DDL, procedimientos almacenados y consultas complejas.",
    ),
    TechRecommendation(
        language="python",
        framework="SQLAlchemy / Django ORM",
        keywords=(
            "sqlalchemy", "django orm", "modelo de datos",
            "data model", "orm", "orm python",
            "migracion sqlalchemy", "alembic",
            "database model python", "clase modelo",
            "declarative base", "session sqlalchemy",
        ),
        notes="ORM en Python: se define la estructura de la base de datos usando clases Python, no SQL directo.",
    ),
    TechRecommendation(
        language="javascript",
        framework="Sequelize / Knex.js",
        keywords=(
            "sequelize", "knex", "orm node",
            "orm javascript", "modelo javascript",
            "migration sequelize",
        ),
        notes="ORM en JavaScript para proyectos Node.js. Se define modelos con clases/objetos JS.",
    ),

    # --- Ciencia de Datos y Machine Learning ---
    TechRecommendation(
        language="python",
        framework="pandas / scikit-learn / TensorFlow",
        keywords=(
            "machine learning", "ml", "deep learning",
            "inteligencia artificial", "ia", "ai",
            "modelo predictivo", "clasificacion", "regresion",
            "neural network", "red neuronal", "nlp",
            "procesamiento lenguaje natural", "computer vision",
            "vision artificial", "opencv", "pytorch", "tensorflow",
            "entrenamiento modelo", "dataset", "data science",
        ),
        notes="Python es el lenguaje dominante en ciencia de datos y machine learning.",
    ),
    TechRecommendation(
        language="python",
        framework="pandas / matplotlib / plotly",
        keywords=(
            "visualizacion datos", "data visualization", "grafico",
            "dashboard", "panel datos", "chart", "reporte datos",
            "analisis datos", "data analysis", "estadistica",
            "pipeline etl", "etl", "data pipeline", "flujo datos",
            "procesamiento datos", "extraccion transformacion carga",
        ),
        notes="Python con pandas y matplotlib es el estándar para análisis y visualización.",
    ),

    # --- Escritorio / GUI ---
    TechRecommendation(
        language="python",
        framework="Tkinter / PyQt",
        keywords=(
            "aplicacion escritorio", "desktop app", "gui",
            "interfaz grafica", "ventana", "tkinter", "pyqt",
            "widget", "formulario escritorio",
        ),
        notes="Python con Tkinter para GUIs simples o PyQt para aplicaciones más complejas.",
    ),

    # --- IoT y Embebidos ---
    TechRecommendation(
        language="cpp",
        framework="Arduino / ESP32 / PlatformIO",
        keywords=(
            "arduino", "esp32", "esp8266", "iot", "sensor",
            "embebido", "embedded", "microcontrolador",
            "raspberry", "gpio", "firmware", "hardware",
        ),
        notes="C/C++ es el estándar para programación de microcontroladores e IoT.",
    ),
    TechRecommendation(
        language="python",
        framework="MicroPython / Raspberry Pi",
        keywords=(
            "micropython", "raspberry pi", "raspberry", "gpio python",
        ),
        alternatives=("cpp",),
        notes="Python en Raspberry Pi o MicroPython para prototipado rápido en IoT.",
    ),

    # --- Videojuegos ---
    TechRecommendation(
        language="cpp",
        framework="Godot / Unreal",
        keywords=(
            "videojuego", "unreal engine",
            "motor grafico", "game engine", "godot",
            "shader", "renderizado", "physx", "juego 3d",
        ),
        notes="C++ para motores de juego de alto rendimiento (Unreal, Godot).",
    ),
    TechRecommendation(
        language="javascript",
        framework="Unity (C#) / Phaser.js",
        keywords=(
            "unity", "phaser", "juego web", "browser game",
            "2d game", "juego 2d", "juego navegador",
            "navegador", "canvas", "webgl",
        ),
        alternatives=("cpp",),
        notes="Unity con C# para juegos, Phaser.js para juegos web en browser.",
    ),

    # --- DevOps e Infraestructura ---
    TechRecommendation(
        language="bash",
        framework="Docker / Kubernetes / Terraform",
        keywords=(
            "docker", "dockerfile", "container", "contenedor",
            "kubernetes", "k8s", "terraform", "iac",
            "infraestructura como codigo", "ci cd", "deploy",
            "despliegue", "pipeline ci", "pipeline devops",
        ),
        notes="Scripts Bash para CI/CD, Dockerfiles y automatización de infraestructura.",
    ),

    # --- Plugins y Extensiones ---
    TechRecommendation(
        language="javascript",
        framework="VS Code Extension API",
        keywords=(
            "vscode extension", "extension vscode", "plugin vscode",
            "extension editor",
        ),
        notes="Extensiones de VS Code usan JavaScript/TypeScript con la Extension API.",
    ),
    TechRecommendation(
        language="javascript",
        framework="Shopify / WordPress",
        keywords=(
            "wordpress plugin", "plugin wordpress", "theme wordpress",
            "shopify app", "shopify plugin", "liquid",
        ),
        notes="Plugins de WordPress usan PHP, apps de Shopify usan Liquid + JavaScript.",
    ),

    # --- Procesamiento de Archivos ---
    TechRecommendation(
        language="python",
        framework="openpyxl / PyPDF2 / Pillow",
        keywords=(
            "procesar excel", "excel", "xlsx", "csv",
            "procesar pdf", "pdf", "extraer texto pdf",
            "procesar imagen", "imagen", "redimensionar",
            "manipulacion archivo", "file processing",
            "word", "docx", "documento",
        ),
        notes="Python tiene las mejores librerías para procesamiento de archivos de oficina.",
    ),

    # --- Audio y Multimedia ---
    TechRecommendation(
        language="python",
        framework="pydub / librosa / moviepy",
        keywords=(
            "audio", "musica", "sonido", "podcast",
            "transcripcion audio", "speech to text",
            "procesamiento audio", "editar video",
        ),
        notes="Python con pydub para audio, moviepy para video, Whisper para transcripción.",
    ),
]


# =========================================================================
# CAPA 2: SKILL_MAP
# Relaciona funcionalidades específicas con el lenguaje que tiene
# el mejor ecosistema de librerías para esa funcionalidad.
# =========================================================================

SKILL_MAP: List[TechRecommendation] = [
    # --- Conectividad y Redes ---
    TechRecommendation(
        language="python",
        framework="requests / httpx / aiohttp",
        keywords=(
            "peticion http", "http request", "api call",
            "descargar", "download", "webhook",
            "rest client", "consumir api",
        ),
        notes="Python con requests es el estándar para peticiones HTTP.",
    ),
    TechRecommendation(
        language="javascript",
        framework="fetch / axios / socket.io",
        keywords=(
            "tiempo real", "real-time", "websocket", "socket",
            "chat en vivo", "live update", "streaming",
            "servidor websocket",
        ),
        notes="Node.js con socket.io domina la comunicación en tiempo real.",
    ),

    # --- Seguridad ---
    TechRecommendation(
        language="python",
        framework="cryptography / hashlib",
        keywords=(
            "encriptacion", "encryption", "hash", "cifrado",
            "seguridad", "security", "autenticacion",
            "jwt", "token", "oauth",
        ),
        notes="Python con cryptography para implementaciones de seguridad.",
    ),

    # --- Testing ---
    TechRecommendation(
        language="python",
        framework="pytest / unittest",
        keywords=(
            "test", "prueba unitaria", "unit test", "testing",
            "assert", "mock", "fixture", "coverage",
        ),
        notes="Python con pytest es el estándar para testing.",
    ),

    # --- Logging y Monitoreo ---
    TechRecommendation(
        language="python",
        framework="logging / prometheus_client",
        keywords=(
            "log", "logging", "monitoreo", "monitoring",
            "alerta", "metrica", "observabilidad",
        ),
        notes="Python tiene logging nativo robusto y librerías para monitoreo.",
    ),

    # --- Manejo de Fechas y Horarios ---
    TechRecommendation(
        language="python",
        framework="datetime / pendulum",
        keywords=(
            "fecha", "hora", "timezone", "zona horaria",
            "calendario", "scheduler", "cron",
            "periodo", "rango fechas",
        ),
        notes="Python con datetime/pendulum es ideal para lógica de fechas.",
    ),
]


# =========================================================================
# CAPA 3: FRAMEWORK_MAP
# Relaciona proyectos complejos con el framework completo recomendado.
# Se usa cuando el proyecto requiere múltiples piezas integradas.
# =========================================================================

FRAMEWORK_MAP: Dict[str, Dict[str, str]] = {
    "api_rest_completa": {
        "language": "python",
        "framework": "FastAPI",
        "stack": "FastAPI + SQLAlchemy + Pydantic + Uvicorn",
        "description": "API REST con validación, ORM, documentación automática",
        "keywords": ("api rest completa", "restful api", "api con base de datos"),
    },
    "web_fullstack": {
        "language": "python",
        "framework": "Django",
        "stack": "Django + Django REST Framework + PostgreSQL + Celery",
        "description": "Aplicación web full-stack con admin, auth y API",
        "keywords": ("aplicacion web completa", "web app completa", "fullstack"),
    },
    "web_fullstack_js": {
        "language": "javascript",
        "framework": "Next.js",
        "stack": "Next.js + React + TailwindCSS + PostgreSQL",
        "description": "Aplicación web full-stack con React y SSR",
        "keywords": ("next.js app", "react web app", "frontend backend juntos"),
    },
    "web_fullstack_ts": {
        "language": "typescript",
        "framework": "Next.js + TypeScript",
        "stack": "Next.js + TypeScript + Prisma + PostgreSQL",
        "description": "Aplicación web full-stack moderna con TypeScript y Prisma ORM",
        "keywords": ("next.js typescript", "fullstack typescript", "app ts completa"),
    },
    "backend_nestjs": {
        "language": "typescript",
        "framework": "NestJS",
        "stack": "NestJS + TypeORM + PostgreSQL + Swagger",
        "description": "Backend robusto con TypeScript, decoradores y módulos",
        "keywords": ("backend nestjs", "api nestjs", "servicio nest"),
    },
    "mobile_app": {
        "language": "dart",
        "framework": "Flutter",
        "stack": "Flutter + Dart + Provider/Riverpod + Firebase",
        "description": "App móvil multiplataforma nativa",
        "keywords": ("app movil", "mobile app", "aplicacion movil"),
    },
    "data_pipeline": {
        "language": "python",
        "framework": "Apache Airflow / Luigi",
        "stack": "Python + pandas + SQLAlchemy + Airflow",
        "description": "Pipeline de procesamiento de datos automatizado",
        "keywords": ("pipeline datos", "etl", "data pipeline", "flujo datos"),
    },
    "ml_model": {
        "language": "python",
        "framework": "scikit-learn / TensorFlow",
        "stack": "Python + scikit-learn + pandas + joblib",
        "description": "Modelo de machine learning entrenado y deployado",
        "keywords": ("modelo machine learning", "ml model", "modelo predictivo"),
    },
    "chatbot": {
        "language": "python",
        "framework": "python-telegram-bot / discord.py",
        "stack": "Python + telegram-bot / discord.py + SQLite",
        "description": "Bot conversacional para Telegram o Discord",
        "keywords": ("chatbot", "bot telegram", "bot discord", "bot conversacional"),
    },
    "trading_system": {
        "language": "python",
        "framework": "ccxt + pandas + backtrader",
        "stack": "Python + ccxt + pandas + matplotlib",
        "description": "Sistema de trading algorítmico completo",
        "keywords": ("sistema trading", "trading system", "algo trading completo"),
    },
    "desktop_app": {
        "language": "python",
        "framework": "PyQt6 / CustomTkinter",
        "stack": "Python + PyQt6 + SQLite",
        "description": "Aplicación de escritorio con GUI profesional",
        "keywords": ("app escritorio", "desktop app", "aplicacion escritorio profesional"),
    },
}


# =========================================================================
# Funciones de consulta
# =========================================================================

def detect_domain(text: str) -> List[TechRecommendation]:
    """Detecta qué dominios/plataformas coincide con el texto dado.

    Busca en el texto las palabras clave de cada entrada en DOMAIN_MAP
    y retorna las recomendaciones que coincidan, ordenadas por número
    de coincidencias (mayor primero).

    Args:
        text: Texto a analizar (objetivo del proyecto, descripción, etc.)

    Returns:
        Lista de TechRecommendation que coinciden con el texto,
        ordenadas por relevancia.
    """
    # Normalizar texto: minúsculas, sin tildes, sin guiones
    text_lower = text.lower()
    text_normalized = text_lower
    for orig, repl in [('á','a'),('é','e'),('í','i'),('ó','o'),('ú','u'),('ü','u'),('ñ','n')]:
        text_normalized = text_normalized.replace(orig, repl)
    tokens = set(text_lower.split())
    tokens_norm = set(text_normalized.split())

    scored = []
    for rec in DOMAIN_MAP:
        matches = 0
        platform_hit = False  # Coincidencia con nombre de plataforma (peso extra)
        for kw in rec.keywords:
            kw_lower = kw.lower()
            kw_norm = kw_lower
            for orig, repl in [('á','a'),('é','e'),('í','i'),('ó','o'),('ú','u'),('ü','u'),('ñ','n')]:
                kw_norm = kw_norm.replace(orig, repl)
            kw_norm_nospace = kw_norm.replace('-', ' ')

            # Nivel 1: Coincidencia exacta como token (máxima confianza)
            if kw_lower in tokens:
                matches += 1
                if len(kw_lower.split()) >= 2 or kw_lower in text_lower:
                    platform_hit = True
            # Nivel 2: Guion ↔ espacio SOLO si la keyword tiene guion real
            # (react-native ↔ react native), evita falsos positivos genéricos
            elif '-' in kw_lower:
                kw_nospace = kw_lower.replace('-', ' ')
                if kw_nospace in tokens_norm or kw_nospace in text_normalized:
                    matches += 1
                    platform_hit = True
            # Nivel 3: Coincidencia por normalización de tildes (media confianza,
            #          NO da bonus de plataforma para evitar falsos positivos)
            elif kw_norm in tokens_norm:
                matches += 1
            # Nivel 4: Substring normalizado (baja confianza)
            elif kw_norm in text_normalized:
                matches += 1
        if matches > 0:
            # Puntuación: matches + bonus por plataforma
            score = matches + (2 if platform_hit else 0)
            scored.append((score, rec))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [rec for _, rec in scored]


def detect_skills(text: str) -> List[TechRecommendation]:
    """Detecta qué funcionalidades requiere el texto dado.

    Busca en el texto las palabras clave de cada entrada en SKILL_MAP
    y retorna las recomendaciones que coincidan.

    Args:
        text: Texto a analizar.

    Returns:
        Lista de TechRecommendation que coinciden.
    """
    text_lower = text.lower()
    tokens = set(text_lower.split())

    scored = []
    for rec in SKILL_MAP:
        matches = sum(1 for kw in rec.keywords if kw.lower() in tokens or kw.lower() in text_lower)
        if matches > 0:
            scored.append((matches, rec))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [rec for _, rec in scored]


def detect_framework(text: str) -> Optional[Dict[str, str]]:
    """Detecta si el texto describe un proyecto complejo que necesita un framework.

    Args:
        text: Texto a analizar.

    Returns:
        Diccionario con datos del framework recomendado, o None si no coincide.
    """
    text_lower = text.lower()

    for fw_name, fw_data in FRAMEWORK_MAP.items():
        for kw in fw_data.get("keywords", ()):
            if kw.lower() in text_lower:
                return fw_data

    return None


def recommend_language(text: str) -> Dict[str, Any]:
    """Recomendación principal de lenguaje para un texto dado.

    Combina las tres capas de mapeo para dar una recomendación:
    1. Busca dominios/plataformas (prioridad alta)
    2. Busca funcionalidades (prioridad media)
    3. Busca frameworks completos (prioridad baja)

    Retorna un diccionario con:
        - language: lenguaje recomendado
        - framework: framework recomendado (si aplica)
        - confidence: "high" | "medium" | "low"
        - source: de dónde vino la recomendación
        - details: lista de coincidencias encontradas

    Args:
        text: Texto del objetivo o descripción del proyecto.

    Returns:
        Diccionario con la recomendación.
    """
    # Prioridad 1: Dominio/plataforma
    domains = detect_domain(text)
    if domains:
        # F5-mejora: desempate inteligente. Si hay múltiples dominios
        # empatados y el texto contiene indicadores de un lenguaje más
        # específico (ej: "typescript" > "javascript"), preferir el más
        # específico. Esto permite que "Componente React con TypeScript"
        # se detecte como typescript en vez de javascript.
        text_lower = text.lower()
        if len(domains) >= 2:
            top_lang = domains[0].language
            # Buscar un resultado typescript entre los empatados si el
            # texto menciona typescript explícitamente
            ts_indicators = ("typescript", ".ts", ".tsx", " ts ")
            has_ts = any(ind in text_lower for ind in ts_indicators)
            if has_ts and top_lang == "javascript":
                ts_result = next(
                    (r for r in domains if r.language == "typescript"), None
                )
                if ts_result:
                    best = ts_result
                    return {
                        "language": best.language,
                        "framework": best.framework,
                        "confidence": "high",
                        "source": "domain_map",
                        "details": [f"Coincidencia con: {best.keywords[:3]}"],
                        "notes": best.notes,
                    }

        best = domains[0]
        return {
            "language": best.language,
            "framework": best.framework,
            "confidence": "high",
            "source": "domain_map",
            "details": [f"Coincidencia con: {best.keywords[:3]}"],
            "notes": best.notes,
        }

    # Prioridad 2: Framework completo
    fw = detect_framework(text)
    if fw:
        return {
            "language": fw["language"],
            "framework": fw["framework"],
            "confidence": "high",
            "source": "framework_map",
            "details": [f"Proyecto tipo: {fw['description']}"],
            "notes": f"Stack recomendado: {fw.get('stack', '')}",
        }

    # Prioridad 3: Funcionalidades
    skills = detect_skills(text)
    if skills:
        best = skills[0]
        return {
            "language": best.language,
            "framework": best.framework,
            "confidence": "medium",
            "source": "skill_map",
            "details": [f"Funcionalidad detectada: {best.keywords[:3]}"],
            "notes": best.notes,
        }

    # Sin coincidencias
    return {
        "language": "",
        "framework": "",
        "confidence": "low",
        "source": "none",
        "details": [],
        "notes": "",
    }


def get_domain_knowledge_prompt() -> str:
    """Genera un resumen del mapeo para inyectar en el prompt del planificador.

    Retorna un texto compacto que el LLM puede usar como referencia
    para decidir qué lenguaje y framework usar en cada tarea.
    """
    lines = [
        "CONOCIMIENTO TECNOLÓGICO DE APA:",
        "Cuando el usuario no especifica un lenguaje, APA elige el más adecuado según el dominio:",
        "",
    ]

    # Agrupar por categoría
    categories = {}
    for rec in DOMAIN_MAP:
        lang = rec.language.upper()
        if lang not in categories:
            categories[lang] = []
        categories[lang].append(rec)

    for lang, recs in categories.items():
        lines.append(f"- {lang}:")
        for rec in recs:
            kws = ", ".join(rec.keywords[:5])
            fw_part = f" ({rec.framework})" if rec.framework else ""
            lines.append(f"  * {kws}{fw_part}")

    lines.append("")
    lines.append("REGLA: Si el usuario no especifica lenguaje, INFERIR el más adecuado")
    lines.append("usando esta tabla. Incluir el campo 'language' en cada tarea del plan.")

    return "\n".join(lines)


# =========================================================================
# Tests internos
# =========================================================================

if __name__ == "__main__":
    tests = [
        ("Crea un expert advisor para MetaTrader 5", "cpp"),
        ("App movil para gestionar inventario", "dart"),
        ("Bot de Telegram para alertas de precio", "python"),
        ("API REST con FastAPI para gestionar usuarios", "python"),
        ("Indicador técnico para TradingView", "javascript"),
        ("Script de bash para backup automático", "bash"),
        ("Dashboard de visualización de datos", "python"),
        ("Aplicación de escritorio con GUI", "python"),
        ("Componente React Native para lista de productos", "react-native"),
        ("Página web con Next.js", "javascript"),
    ]

    all_passed = True
    for text, expected in tests:
        result = recommend_language(text)
        lang = result["language"]
        status = "OK" if lang == expected else "FALLO"
        if status == "FALLO":
            all_passed = False
        print(f"[{status}] '{text}' -> {lang} (esperado: {expected})")
        if result["framework"]:
            print(f"       Framework: {result['framework']}")
        print()

    if all_passed:
        print("CRITERIO OK")
    else:
        print("CRITERIO FALLO - Revisar detectores")
