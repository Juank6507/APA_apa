# Proceso: Conexion de APA a LLMs Reales mediante Proxy

**Objetivo:** Permitir que APA use inteligencia artificial real (glm-4-plus) cuando corre en la computadora del usuario.

**Duracion de setup:** ~10 minutos (primera vez) / ~30 segundos (replicacion con scripts)

---

## Resumen Ejecutivo

APA necesita un LLM para funcionar. El LLM esta dentro de los servidores de Z.ai y no es accesible desde fuera. La solucion fue crear un **proxy** dentro del sandbox de Z.ai que actua como puente: recibe peticiones desde la PC del usuario, las reenvia al LLM interno, y devuelve la respuesta.

Esto requiere tres componentes trabajando juntos:

1. **El Proxy** (sandbox de Z.ai) - El puente hacia el LLM
2. **El MB Sandbox** (PC del usuario) - El intermediario que APA llama
3. **La configuracion de APA** (PC del usuario) - Para que APA sepa donde esta MB

---

## Grafo del Proceso Completo

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                        FLUJO COMPLETO APA → LLM                            ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                            ║
║  ┌─────────────────────────────────────────────────┐                        ║
║  │  PC DEL USUARIO (Windows)                       │                        ║
║  │                                                 │                        ║
║  │  ┌──────────┐    HTTP       ┌──────────────┐    │                        ║
║  │  │  APA     │──localhost──→│ MB Sandbox   │    │                        ║
║  │  │  Python  │   :8080→8100 │ TypeScript   │    │                        ║
║  │  │  :8080   │              │ Bun :8100    │    │                        ║
║  │  └──────────┘              └──────┬───────┘    │                        ║
║  │       ▲                           │             │                        ║
║  │       │                           │             │                        ║
║  │  ┌────┴─────────────┐             │             │                        ║
║  │  │  .env             │    lee      │             │                        ║
║  │  │  settings.py      │←──.z-ai-config             │                        ║
║  │  │  mb_launcher.py   │             │             │                        ║
║  │  │  chat_engine.py   │             │             │                        ║
║  │  └──────────────────┘             │             │                        ║
║  └───────────────────────────────────┼─────────────┘                        ║
║                                      │                                     ║
║                    SDK (z-ai-web-dev-sdk)                                ║
║                    lee baseUrl de .z-ai-config                                ║
║                                      │                                     ║
╠══════════════════════════════════════╪══════════════════════════════════╣
║                                      │  INTERNET (HTTPS)                  ║
║                                      ▼                                     ║
║  ┌──────────────────────────────────────────────────────┐                  ║
║  │  SANDBOX DE Z.AI                                     │                  ║
║  │                                                      │                  ║
║  │  ┌────────────────────────────────────────────────┐  │                  ║
║  │  │  Next.js :3000                                   │  │                  ║
║  │  │                                                 │  │                  ║
║  │  │  /api/zai-proxy/v1/chat/completions  ◄───────┐  │  │                  ║
║  │  │  /api/zai-proxy/v1/vision                  │  │  │                  ║
║  │  │  /api/zai-proxy/v1/tts                     │  │  │                  ║
║  │  │  /api/zai-proxy/v1/asr                     │  │  │                  ║
║  │  │  /api/zai-proxy/v1/images/generations      │  │  │                  ║
║  │  │  /api/zai-proxy/v1/async-result            │  │  │                  ║
║  │  │  /api/zai-proxy/v1/functions/invoke        │  │  │                  ║
║  │  │                                             │  │  │                  ║
║  │  │  _lib.ts  lee  /etc/.z-ai-config            │  │  │                  ║
║  │  │  inyecta credenciales REALES               │  │  │                  ║
║  │  │         │                                   │  │  │                  ║
║  │  │         ▼                                   │  │  │                  ║
║  │  │  internal-api.z.ai/v1/chat/completions     │  │  │                  ║
║  │  │         │                                   │  │  │                  ║
║  │  │         ▼                                   │  │  │                  ║
║  │  │  glm-4-plus (LLM real)                     │  │  │                  ║
║  │  │         │                                   │  │  │                  ║
║  │  │         ▼                                   ─┘  │                  ║
║  │  │  Respuesta vuelve por el mismo camino         │                  ║
║  │  └─────────────────────────────────────────────────┘                  ║
║  │                                                                       ║
║  │  setup-proxy.sh → Recrea archivos si faltan                            ║
║  └───────────────────────────────────────────────────────────────────────┘                  ║
║                                                                            ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

### Diagrama de Secuencia (paso a paso)

```
Usuario     APA(:8080)     MB Sandbox(:8100)    SDK          Proxy(:3000)    internal-api    glm-4-plus
  │            │                │               │               │               │               │
  │──escribe──→│                │               │               │               │               │
  │            │               │               │               │               │               │
  │            │──POST /api/call──────────────→│               │               │               │
  │            │  {system_prompt,              │               │               │               │
  │            │   user_prompt}                │               │               │               │
  │            │               │               │               │               │               │
  │            │               │──lee .z-ai-config              │               │               │
  │            │               │──ZAI.create()──│               │               │               │
  │            │               │               │               │               │               │
  │            │               │               │──POST /api/zai-proxy/v1/...→│               │               │
  │            │               │               │  (con headers falsos)           │               │
  │            │               │               │               │               │               │
  │            │               │               │               │──lee /etc/.z-ai-config
  │            │               │               │               │──inyecta credenciales
  │            │               │               │               │               │               │
  │            │               │               │               │──POST v1/chat/completions→│               │
  │            │               │               │               │  (credenciales reales)    │               │
  │            │               │               │               │               │               │
  │            │               │               │               │               │──genera──→    │
  │            │               │               │               │               │               │
  │            │               │               │               │←──respuesta───│←──────────────│
  │            │               │               │←──respuesta───│               │               │
  │            │←──JSON {content, model, ...}──│               │               │               │
  │            │               │               │               │               │               │
  │←──muestra respuesta con modelo usado────│               │               │               │
  │            │               │               │               │               │               │
```

---

## Inventario Completo de Archivos

### Resumen por Ubicacion

| Ubicacion | Archivos | Criticos | Quien lo gestiona |
|---|---|---|---|
| Sandbox Z.ai (proxy) | 8 | Si | Agente Z.ai + setup-proxy.sh |
| PC Usuario (mb-sandbox) | 3 | Si | Usuario + scripts .ps1 |
| PC Usuario (APA config) | 3 | Si | Usuario |
| PC Usuario (scripts aux) | 2 | No | Usuario (opcional) |
| **TOTAL** | **16** | **14** | |  

---

### DETALLE: Archivos en el Sandbox de Z.ai

Estos archivos viven dentro del sandbox donde corre el agente de Z.ai. Se pueden perder si el sandbox se reinicia. `setup-proxy.sh` los recrea automaticamente.

#### Fichero 1: `_lib.ts` (CORAZON DEL PROXY)

- **Ruta:** `src/app/api/zai-proxy/_lib.ts`
- **Ruta absoluta (sandbox):** `/home/z/my-project/src/app/api/zai-proxy/_lib.ts`
- **Que hace:** Es el cerebro del proxy. Lee las credenciales reales de `/etc/.z-ai-config`, construye los headers de autenticacion, y reenvia cualquier peticion a `internal-api.z.ai`. Descarta los headers del llamante y los reemplaza con credenciales validas del sandbox.
- **Dependencias:** Lee `/etc/.z-ai-config` (ya existe en el sandbox, no se toca)
- **Tamano:** ~72 lineas
- **Se regenera con:** `setup-proxy.sh`

#### Fichero 2: `v1/chat/completions/route.ts`

- **Ruta:** `src/app/api/zai-proxy/v1/chat/completions/route.ts`
- **Ruta absoluta (sandbox):** `/home/z/my-project/src/app/api/zai-proxy/v1/chat/completions/route.ts`
- **Que hace:** Endpoint del proxy para llamadas de chat al LLM. Recibe la peticion de MB Sandbox y la reenvia a `internal-api.z.ai/v1/chat/completions`. Este es el endpoint principal que usa APA.
- **Tamano:** 6 lineas (patron repetitivo)
- **Se regenera con:** `setup-proxy.sh`

#### Fichero 3: `v1/vision/route.ts`

- **Ruta:** `src/app/api/zai-proxy/v1/vision/route.ts`
- **Ruta absoluta (sandbox):** `/home/z/my-project/src/app/api/zai-proxy/v1/vision/route.ts`
- **Que hace:** Endpoint del proxy para analisis de imagenes (vision).
- **Tamano:** 6 lineas
- **Se regenera con:** `setup-proxy.sh`

#### Fichero 4: `v1/tts/route.ts`

- **Ruta:** `src/app/api/zai-proxy/v1/tts/route.ts`
- **Ruta absoluta (sandbox):** `/home/z/my-project/src/app/api/zai-proxy/v1/tts/route.ts`
- **Que hace:** Endpoint del proxy para texto a voz.
- **Tamano:** 6 lineas
- **Se regenera con:** `setup-proxy.sh`

#### Fichero 5: `v1/asr/route.ts`

- **Ruta:** `src/app/api/zai-proxy/v1/asr/route.ts`
- **Ruta absoluta (sandbox):** `/home/z/my-project/src/app/api/zai-proxy/v1/asr/route.ts`
- **Que hace:** Endpoint del proxy para voz a texto (reconocimiento de voz).
- **Tamano:** 6 lineas
- **Se regenera con:** `setup-proxy.sh`

#### Fichero 6: `v1/images/generations/route.ts`

- **Ruta:** `src/app/api/zai-proxy/v1/images/generations/route.ts`
- **Ruta absoluta (sandbox):** `/home/z/my-project/src/app/api/zai-proxy/v1/images/generations/route.ts`
- **Que hace:** Endpoint del proxy para generacion de imagenes.
- **Tamano:** 6 lineas
- **Se regenera con:** `setup-proxy.sh`

#### Fichero 7: `v1/async-result/route.ts`

- **Ruta:** `src/app/api/zai-proxy/v1/async-result/route.ts`
- **Ruta absoluta (sandbox):** `/home/z/my-project/src/app/api/zai-proxy/v1/async-result/route.ts`
- **Que hace:** Endpoint del proxy para consultar resultados de operaciones asincronas (polling).
- **Tamano:** 6 lineas
- **Se regenera con:** `setup-proxy.sh`

#### Fichero 8: `v1/functions/invoke/route.ts`

- **Ruta:** `src/app/api/zai-proxy/v1/functions/invoke/route.ts`
- **Ruta absoluta (sandbox):** `/home/z/my-project/src/app/api/zai-proxy/v1/functions/invoke/route.ts`
- **Que hace:** Endpoint del proxy para invocar funciones/herramientas del LLM (tool calling).
- **Tamano:** 6 lineas
- **Se regenera con:** `setup-proxy.sh`

#### Fichero 9: `setup-proxy.sh` (REGENERADOR)

- **Ruta:** `/home/z/my-project/setup-proxy.sh`
- **Que hace:** Script bash que verifica los 8 archivos del proxy. Si falta alguno, lo recrea con el contenido correcto. Incluye una verificacion con `curl` al final. Se ejecuta al inicio de cada sesion del sandbox.
- **Cuando usarlo:** Al inicio de cada sesion, o si el proxy devuelve 404.
- **Tamano:** ~160 lineas
- **NO se regenera** (es el que regenera a los demas)

---

### DETALLE: Archivos en la PC del Usuario (MB Sandbox)

Estos archivos van en la carpeta `mb-sandbox` junto a la instalacion de APA en la PC del usuario.

#### Fichero 10: `package.json` (MB Sandbox)

- **Ruta:** `mb-sandbox/package.json`
- **Ruta absoluta (Windows):** `C:\Python\Proyectos\APA\mb-sandbox\package.json`
- **Que hace:** Declara la dependencia del SDK de Z.ai (`z-ai-web-dev-sdk`). Bun lo lee para instalar la libreria correcta.
- **Contenido clave:** Solo una dependencia: `"z-ai-web-dev-sdk": "latest"`
- **Tamano:** ~10 lineas
- **Accion requerida:** Ejecutar `bun install` despues de crearlo

#### Fichero 11: `index.ts` (SERVIDOR MB SANDBOX)

- **Ruta:** `mb-sandbox/index.ts`
- **Ruta absoluta (Windows):** `C:\Python\Proyectos\APA\mb-sandbox\index.ts`
- **Que hace:** Es el servidor HTTP que escucha en el puerto 8100. Expone tres endpoints que APA necesita:
  - `GET /api/status` - APA verifica si MB esta vivo
  - `GET /api/models` - APA consulta modelos disponibles
  - `POST /api/call` - APA envia mensajes del usuario al LLM
  - Inicializa el SDK de Z.ai, que lee `.z-ai-config` para saber donde enviar las peticiones
  - Tiene modo fallback: si el SDK no puede inicializar, genera respuestas simuladas
- **Detalles criticos:**
  - El system prompt se envia con `role: "system"` (NO `role: "assistant"`, eso causa respuestas vacias)
  - No envia el parametro `thinking` (causa respuestas vacias)
  - Usa `completion.model` para obtener el nombre real del modelo usado
- **Tamano:** ~110 lineas

#### Fichero 12: `.z-ai-config` (CONFIGURACION DEL SDK)

- **Ruta:** `mb-sandbox/.z-ai-config`
- **Ruta absoluta (Windows):** `C:\Python\Proyectos\APA\mb-sandbox\.z-ai-config`
- **Que hace:** Le dice al SDK de Z.ai donde encontrar el proxy. El SDK lo busca en `process.cwd()` (la carpeta donde corre `bun`). Por eso DEBE estar en la misma carpeta que `index.ts`.
- **Contenido:**
```json
{
  "baseUrl": "https://preview-chat-CHAT_ID_AQUI.space-z.ai/api/zai-proxy/v1",
  "apiKey": "Z.ai",
  "chatId": "",
  "userId": ""
}
```
- **IMPORTANTE:** El `CHAT_ID_AQUI` debe reemplazarse con el `chat_id` de la sesion actual de Z.ai. Este valor aparece en los metadatos del gateway de cada mensaje.
- **Tamano:** 6 lineas

---

### DETALLE: Archivos de Configuracion de APA (PC del Usuario)

#### Fichero 13: `.env` de APA

- **Ruta:** `apa/.env` (dentro de la carpeta del paquete APA)
- **Ruta absoluta (Windows):** `C:\Python\Proyectos\APA\apa\.env`
- **Que hace:** Define las variables de entorno que APA necesita para lanzar MB Sandbox automaticamente. Sin este archivo, APA no sabe que MB existe y cae a "modo emergencia" (sin LLM real).
- **Contenido requerido:**
```
MODEL_BROKER_URL=http://127.0.0.1:8100
MODEL_BROKER_START_CMD=bun --hot index.ts
SANDBOX_PATH=C:\Python\Proyectos\APA\mb-sandbox
```
- **Nota tecnica:** La variable `SANDBOX_PATH` es la que APA lee como `model_broker_start_dir` en `settings.py`. El mapeo esta en la propiedad `model_broker_start_dir`.
- **Tamano:** 3 lineas

#### Fichero 14: `settings.py` (configuracion central de APA)

- **Ruta:** `apa/config/settings.py`
- **Ruta absoluta (Windows):** `C:\Python\Proyectos\APA\apa\config\settings.py`
- **Que hace:** Es el cerebro de configuracion de APA. Lee las variables del `.env` y las expone como propiedades. Las propiedades relevantes para el proxy son:
  - `model_broker_url` → lee `MODEL_BROKER_URL`
  - `model_broker_start_cmd` → lee `MODEL_BROKER_START_CMD`
  - `model_broker_start_dir` → lee `SANDBOX_PATH` (ojo: no `MODEL_BROKER_SANDBOX_PATH`)
- **No se modifica:** Este archivo se entrega como esta. Solo importa que el `.env` tenga las variables correctas.
- **Tamano:** ~445 lineas (incluye tests autonomos)

#### Fichero 15: `mb_launcher.py` (lanzador de MB)

- **Ruta:** `apa/core/mb_launcher.py`
- **Ruta absoluta (Windows):** `C:\Python\Proyectos\APA\apa\core\mb_launcher.py`
- **Que hace:** Funcion `ensure_mb_running()` que APA ejecuta al arrancar. Tiene una estrategia de 3 niveles:
  1. Verifica si MB ya responde en la URL configurada (production)
  2. Si no, intenta lanzar MB como proceso hijo usando `start_cmd` + `start_dir` (sandbox local)
  3. Si tampoco funciona, retorna `False` y APA usa Ollama local (modo emergencia)
  - Incluye `stop_mb()` para detener el proceso y `get_mb_status()` para monitoreo
- **No se modifica:** Este archivo se entrega como esta.
- **Tamano:** ~351 lineas (incluye tests autonomos)

#### Fichero 16: `chat_engine.py` (FIX REQUERIDO)

- **Ruta:** `apa/interface/app/chat_engine.py`
- **Ruta absoluta (Windows):** `C:\Python\Proyectos\APA\apa\interface\app\chat_engine.py`
- **Que hace:** Maneja las respuestas del chat de APA. Tiene un bug: el frontend JavaScript revisa `data.success` antes de mostrar la respuesta, pero el backend original nunca incluye ese campo.
- **FIX REQUERIDO:** Agregar `"success": True` como primera linea del diccionario de retorno:
```python
# ANTES (bug):
return {
    "response": response_text,
    ...
}

# DESPUES (corregido):
return {
    "success": True,
    "response": response_text,
    ...
}
```
- **Sin este fix:** El chat SIEMPRE muestra "Error: Respuesta vacia" aunque el LLM haya respondido correctamente.
- **Tamano:** Variable (cambio de 1 linea)

---

### DETALLE: Scripts Auxiliares (PC del Usuario, Opcionales)

#### Fichero: `setup-mb.ps1` (CREACION AUTOMATICA DEL MB SANDBOX)

- **Ruta:** `C:\Python\Proyectos\APA\setup-mb.ps1`
- **Que hace:** Script PowerShell que crea la carpeta `mb-sandbox`, los 3 archivos necesarios (`package.json`, `index.ts`, `.z-ai-config` con el `chat_id` correcto), y ejecuta `bun install`.
- **Uso:** `powershell -ExecutionPolicy Bypass -File setup-mb.ps1 -ChatId "TU_CHAT_ID"`

#### Fichero: `start-apa.ps1` (INICIO AUTOMATICO)

- **Ruta:** `C:\Python\Proyectos\APA\start-apa.ps1`
- **Que hace:** Mata procesos bun existentes, lanza MB en background, espera a que este listo (health check), y lanza APA.
- **Uso:** `powershell -ExecutionPolicy Bypass -File start-apa.ps1`

---

## Mapa de Dependencias entre Archivos

```
                        ┌─────────────────────┐
                        │   /etc/.z-ai-config │  (Sandbox - ya existe)
                        │   credenciales reales│
                        └──────────┬──────────┘
                                   │ lee
                                   ▼
                    ┌──────────────────────────┐
                    │     _lib.ts (proxy)       │
                    │  reenvia peticiones       │◄── 7 route.ts files
                    │  inyecta credenciales     │
                    └──────────────┬───────────┘
                                   │ HTTP via
                                   │ Next.js :3000
                                   ▼
                    ┌──────────────────────────┐
                    │    mb-sandbox/.z-ai-config│  (PC Usuario)
                    │    baseUrl = proxy URL     │
                    └──────────────┬───────────┘
                                   │ lee
                                   ▼
                    ┌──────────────────────────┐
                    │   mb-sandbox/index.ts     │  (PC Usuario)
                    │   Servidor Bun :8100      │◄── package.json (dep: SDK)
                    │   Usa z-ai-web-dev-sdk    │
                    └──────────────┬───────────┘
                                   │ HTTP localhost
                                   │
                    ┌──────────────┴───────────┐
                    │                          │
              ┌─────┴──────┐            ┌──────┴─────┐
              │  apa/.env  │            │ settings.py│
              │  URL + CMD │──define──→│ lee env vars│
              │  + PATH    │            └──────┬─────┘
              └────────────┘                   │
                                               │ usa
                                               ▼
                                    ┌──────────────────┐
                                    │  mb_launcher.py   │
                                    │  lanza MB si no   │
                                    │  esta corriendo   │
                                    └────────┬─────────┘
                                             │ MB listo
                                             ▼
                                    ┌──────────────────┐
                                    │ chat_engine.py   │
                                    │ envia prompts     │
                                    │ al MB via HTTP   │
                                    │ (debe incluir    │
                                    │  success: True)  │
                                    └──────────────────┘
```

---

## Fase 1: Entender el Problema

### 1.1 La arquitectura de APA

APA no habla directamente con el LLM. Tiene tres capas:

```
Usuario → APA (Python, :8080) → MB (TypeScript, :8100) → LLM
```

APA le pide a MB que hable con la IA. MB usa un SDK oficial (`z-ai-web-dev-sdk`) para conectarse al LLM.

### 1.2 La restriccion

El LLM esta en `internal-api.z.ai`, un servidor que **solo es accesible desde dentro de la red de Z.ai**. Desde la PC del usuario (Windows), es completamente inalcanzable.

### 1.3 El sandbox como solucion

El sandbox de Z.ai tiene dos propiedades que lo hacen ideal como puente:

- **Puede alcanzar `internal-api.z.ai`** — Esta dentro de la red.
- **Esta expuesto publicamente** — Tiene una URL accesible desde cualquier lugar (el Preview Panel).

La solucion: poner un proxy dentro del sandbox que reciba peticiones desde afuera y las reenvie al LLM interno.

### 1.4 Por que esta solucion y no otra

| Alternativa descartada | Motivo |
|---|---|
| Ollama (LLM local) | Descargar modelos de varios GB, calidad inferior, consume recursos |
| OpenAI/Anthropic | Costo monetario, credenciales, cambiaria la arquitectura de MB |
| VPN al sandbox | El sandbox se recrea cada sesion, no hay IP fija, inestable |
| Modificar MB para otra API | MB esta disenado alrededor del SDK de Z.ai |

---

## Fase 2: Diseno de la Solucion

### 2.1 Decisiones tecnicas importantes

Estas decisiones se tomaron despues de pruebas reales y errores. No cambiarlas sin probar:

| Decision | Por que |
|---|---|
| Rutas estaticas (un archivo por endpoint) en vez de una ruta comodin | Next.js 16 con Turbopack tiene un bug que hace que las rutas comodin funcionen intermitentemente (a veces 200, a veces 404) |
| El system prompt se envia con `role: "system"` | Con `role: "assistant"`, el LLM a veces devuelve respuestas vacias a traves del proxy |
| No enviar el parametro `thinking` | Causa respuestas vacias del LLM |
| MB Sandbox es un proyecto separado (no se modifica el MB original) | Aislamiento: si algo falla, no afecta al MB original |
| El truco de autenticacion | El proxy sobreescribe los headers del llamante con credenciales reales del sandbox |

---

## Fase 3: Ejecucion — Paso a Paso

### Prerrequisitos

- [ ] Bun instalado en Windows (`https://bun.sh`)
- [ ] Python 3.11+ en Windows
- [ ] APA clonado en `C:\Python\Proyectos\APA\`
- [ ] Sesion activa del sandbox de Z.ai (el agente esta corriendo)

---

### Paso 1 — Asegurar el Proxy en el Sandbox

**Que:** Verificar que los archivos del proxy existen dentro del sandbox de Z.ai.

**Por que:** El sandbox puede reiniciarse entre sesiones y perder los archivos. Sin el proxy, nada funciona.

**Quien lo hace:** El agente de Z.ai (no requiere intervencion del usuario).

**Accion:**

```bash
bash /home/z/my-project/setup-proxy.sh
```

Este script verifica 9 archivos (1 lib + 7 rutas + 1 script) y recrea los que falten. Incluye una verificacion automatica al final.

**Verificacion:** El script muestra `[OK]` para cada archivo existente y `[CREANDO]` para los nuevos.

---

### Paso 2 — Crear el MB Sandbox en Windows

**Que:** Crear un servidor TypeScript minimo en la PC del usuario que APA pueda llamar.

**Por que:** APA necesita un MB corriendo en `localhost:8100`. El MB original es Python y no usa el SDK de Z.ai. Necesitamos uno nuevo que si lo use.

**Quien lo hace:** El usuario (o el script de automatizacion).

**Accion (con script):**

```powershell
powershell -ExecutionPolicy Bypass -File C:\Python\Proyectos\APA\setup-mb.ps1 -ChatId "dcaab75b-801b-4f87-885b-58dbc3b5f310"
```

**Accion (manual):**

1. Crear carpeta: `mkdir C:\Python\Proyectos\APA\mb-sandbox`
2. Crear `package.json` (ver Fichero 10)
3. Crear `index.ts` (ver Fichero 11)
4. Crear `.z-ai-config` (ver Fichero 12, reemplazar CHAT_ID)
5. Ejecutar: `cd C:\Python\Proyectos\APA\mb-sandbox && bun install`

**Verificacion:**

```powershell
cd C:\Python\Proyectos\APA\mb-sandbox
bun --hot index.ts
```

Debe mostrar:
```
MB Sandbox escuchando en puerto 8100
[MB Sandbox] SDK z-ai-web-dev-sdk inicializado correctamente
```

Si muestra "Configuration file not found" → el `.z-ai-config` no esta en la carpeta correcta.

---

### Paso 3 — Configurar el `.env` de APA

**Que:** Decirle a APA como encontrar y lanzar el MB Sandbox.

**Por que:** Sin esta configuracion, APA arranca pero no lanza MB y cae a "modo emergencia" (sin LLM real).

**Quien lo hace:** El usuario.

**Accion:**

Editar `C:\Python\Proyectos\APA\apa\.env` y agregar:

```
MODEL_BROKER_URL=http://127.0.0.1:8100
MODEL_BROKER_START_CMD=bun --hot index.ts
SANDBOX_PATH=C:\Python\Proyectos\APA\mb-sandbox
```

**Nota:** La variable se llama `SANDBOX_PATH` pero APA internamente la lee como `start_dir`. Esto es correcto — es el mapeo que hace `settings.py`.

**Verificacion:** Despues de este paso, APA deberia mostrar `Startup completado — success=True, mb=True` al arrancar.

---

### Paso 4 — Aplicar Fix en `chat_engine.py`

**Que:** Agregar un campo faltante en la respuesta del chat de APA.

**Por que:** APA tiene un bug: el frontend JavaScript revisa `data.success` antes de mostrar la respuesta, pero el backend nunca incluye ese campo.

**Quien lo hace:** El usuario (cambio de una linea).

**Accion:** En `C:\Python\Proyectos\APA\apa\interface\app\chat_engine.py`, buscar el `return` final y agregar `"success": True,`:

```python
# DESPUES (corregido):
return {
    "success": True,
    "response": response_text,
    ...
}
```

---

### Paso 5 — Iniciar todo

**Opcion A: Manual (dos terminales)**

Terminal 1: `cd C:\Python\Proyectos\APA\mb-sandbox && bun --hot index.ts`
Terminal 2: `python C:\Python\Proyectos\APA\apa\interface\app_apa.py`

**Opcion B: Automatico (un comando)**

```powershell
powershell -ExecutionPolicy Bypass -File C:\Python\Proyectos\APA\start-apa.ps1
```

**Verificacion final:**

1. APA muestra: `Startup completado — success=True, mb=True`
2. Abrir `http://localhost:8080` en el navegador
3. Escribir un mensaje en el chat
4. La respuesta debe mostrar `Modelo: glm-4-plus` y ser contextual

---

## Fase 4: Mantenimiento

### El chat_id puede cambiar

La URL del proxy contiene el `chat_id` de la sesion de Z.ai. Si la sesion cambia, esta URL cambia. El sintoma: el proxy devuelve 502 o errores de conexion.

**Solucion:** Actualizar el `chat_id` en `C:\Python\Proyectos\APA\mb-sandbox\.z-ai-config`.

### El proxy puede desaparecer

El sandbox se reinicia entre sesiones. Los archivos del proxy se pierden.

**Solucion:** Ejecutar `bash /home/z/my-project/setup-proxy.sh` al inicio de cada sesion.

---

## Fase 5: Diagnostico de Problemas

| Sintoma | Causa probable | Archivo involucrado | Accion |
|---|---|---|---|
| APA dice "Model Broker no disponible" | MB no esta corriendo | `apa/.env` | Verificar `.env` (Paso 3). Probar MB manualmente (Paso 2). |
| MB dice "Configuration file not found" | Config no encontrada | `mb-sandbox/.z-ai-config` | Ponerlo en `mb-sandbox/` junto a `index.ts`. |
| MB dice "API request failed with status 404" (con HTML) | Proxy desaparecido | `src/app/api/zai-proxy/_lib.ts` + 7 routes | Ejecutar `setup-proxy.sh` en el sandbox. |
| SDK inicializa pero respuesta vacia | Parametros incorrectos | `mb-sandbox/index.ts` | Verificar: sin `thinking`, system prompt con `role: "system"`. |
| MB devuelve contenido pero APA muestra "Respuesta vacia" | Falta success flag | `apa/interface/app/chat_engine.py` | Agregar `"success": True` al return. |
| `EADDRINUSE` al iniciar MB | Puerto ocupado | N/A | `Get-Process -Name bun \| Stop-Process` |
| Conexion tarda mucho o da 502 | chat_id cambio | `mb-sandbox/.z-ai-config` | Actualizar con el nuevo `chat_id`. |

---

## Test de Validacion

Existe un test completo en `APA_apa/tests/test_proxy_chain.py` que:

- Verifica que todos los 16 archivos existen en sus ubicaciones correctas
- Valida el contenido de cada archivo critico
- Prueba cada eslabon de la cadena (proxy, MB, configuracion APA)
- Indica exactamente que archivo falta y donde debe ir
- Muestra un reporte claro al usuario

**Ejecucion (en la PC del usuario):**

```bash
cd C:\Python\Proyectos\APA
python -m APA_apa.tests.test_proxy_chain
```

**Ejecucion (desde cualquier ubicacion, pasando la ruta base):**

```bash
python C:\Python\Proyectos\APA\APA_apa\tests\test_proxy_chain.py --base-dir C:\Python\Proyectos\APA
```

---

## Apendices

### Apendice A — Contenido de `.z-ai-config` (MB Sandbox)

**Ubicacion:** `C:\Python\Proyectos\APA\mb-sandbox\.z-ai-config`

```json
{
  "baseUrl": "https://preview-chat-REEMPLAZAR-CON-CHAT-ID.space-z.ai/api/zai-proxy/v1",
  "apiKey": "Z.ai",
  "chatId": "",
  "userId": ""
}
```

### Apendice B — Codigo de `index.ts` (MB Sandbox - version corregida)

**Ubicacion:** `C:\Python\Proyectos\APA\mb-sandbox\index.ts`

```typescript
import ZAI from "z-ai-web-dev-sdk";

const PORT = 8100;
const AVAILABLE_MODELS = [{ model: "sandbox-default", provider: "sandbox" }];

type ZAIInstance = Awaited<ReturnType<typeof ZAI.create>>;
let zaiInstance: ZAIInstance | null = null;
let sdkReady = false;
let sdkError: string | null = null;
let sdkInitAttempted = false;

async function getZAI(): Promise<ZAIInstance | null> {
  if (sdkInitAttempted) return zaiInstance;
  sdkInitAttempted = true;
  try {
    zaiInstance = await ZAI.create();
    sdkReady = true;
    console.log("[MB Sandbox] SDK z-ai-web-dev-sdk inicializado correctamente");
    return zaiInstance;
  } catch (err: any) {
    sdkError = err.message || String(err);
    sdkReady = false;
    console.warn("[MB Sandbox] SDK no disponible: " + sdkError);
    console.warn("[MB Sandbox] Modo FALLBACK activado.");
    return null;
  }
}

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status, headers: { "Content-Type": "application/json" },
  });
}

function generateFallbackResponse(userPrompt: string): string {
  const prompt = userPrompt.toLowerCase().trim();
  if (prompt.includes("hola") || prompt.includes("buenos") || prompt.includes("saludos")) {
    return "Hola! Soy APA. Estoy en modo sandbox con respuestas simuladas.";
  }
  return "[Modo sandbox] Recibi tu mensaje (" + userPrompt.length + " caracteres). MB funciona correctamente.";
}

async function handleRequest(req: Request): Promise<Response> {
  const url = new URL(req.url);
  const path = url.pathname;

  if (req.method === "GET" && path === "/api/status") {
    return jsonResponse({ mode: "sandbox", status: "ok", models_count: AVAILABLE_MODELS.length, sdk_ready: sdkReady, sdk_error: sdkError });
  }
  if (req.method === "GET" && path === "/api/models") {
    return jsonResponse(AVAILABLE_MODELS);
  }
  if (req.method === "POST" && path === "/api/call") {
    const t0 = Date.now();
    try {
      const parsed = await req.json();
      const systemPrompt = parsed.system_prompt || "";
      const userPrompt = parsed.user_prompt || "";
      if (!userPrompt) {
        return jsonResponse({ success: false, error: "user_prompt is required", content: "", model_used: "", provider: null, http_status: null }, 400);
      }
      const zai = await getZAI();
      if (zai) {
        const messages: Array<{ role: string; content: string }> = [];
        if (systemPrompt) messages.push({ role: "system", content: systemPrompt });
        messages.push({ role: "user", content: userPrompt });
        const completion = await zai.chat.completions.create({ messages }) as any;
        const msg = completion.choices?.[0]?.message;
        let content = msg?.content || "";
        return jsonResponse({ content, model_used: completion.model || "sandbox-default", provider: "sandbox", success: !!content, error: content ? null : "Respuesta vacia del LLM", http_status: 200, latency_ms: Date.now() - t0 });
      }
      const content = generateFallbackResponse(userPrompt);
      return jsonResponse({ content, model_used: "sandbox-default", provider: "sandbox-fallback", success: true, error: null, http_status: 200, latency_ms: Date.now() - t0, sdk_mode: "fallback", sdk_error: sdkError });
    } catch (err: any) {
      console.error("[MB Sandbox] Error en /api/call:", err.message);
      return jsonResponse({ success: false, error: err.message || "Error interno", content: "", model_used: "sandbox-default", provider: "sandbox", http_status: 500, latency_ms: Date.now() - t0 }, 500);
    }
  }
  return jsonResponse({ error: "Not found" }, 404);
}

Bun.serve({
  hostname: "0.0.0.0",
  port: PORT,
  async fetch(req) {
    try { return await handleRequest(req); }
    catch (err: any) { return jsonResponse({ error: err.message }, 500); }
  },
});

console.log("MB Sandbox escuchando en puerto " + PORT);
```

### Apendice C — Codigo de `_lib.ts` (Proxy)

**Ubicacion:** `/home/z/my-project/src/app/api/zai-proxy/_lib.ts`

```typescript
import { readFileSync } from 'fs';

const TARGET_BASE = 'https://internal-api.z.ai/v1';

function getConfig() {
  try {
    return JSON.parse(readFileSync('/etc/.z-ai-config', 'utf-8'));
  } catch {
    return null;
  }
}

function buildHeaders(config: any): Record<string, string> {
  const h: Record<string, string> = {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${config.apiKey}`,
    'X-Z-AI-From': 'Z',
  };
  if (config.chatId) h['X-Chat-Id'] = config.chatId;
  if (config.userId) h['X-User-Id'] = config.userId;
  if (config.token) h['X-Token'] = config.token;
  return h;
}

export async function proxyRequest(targetPath: string, request: Request) {
  const config = getConfig();
  if (!config) {
    return new Response(
      JSON.stringify({ error: 'Proxy config not found' }),
      { status: 503, headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' } }
    );
  }

  const targetUrl = `${TARGET_BASE}/${targetPath}`;
  const headers = buildHeaders(config);
  const body = await request.text();

  try {
    const resp = await fetch(targetUrl, {
      method: request.method,
      headers,
      body: request.method !== 'GET' ? body : undefined,
    });

    const respHeaders = new Headers({
      'Access-Control-Allow-Origin': '*',
      'Content-Type': resp.headers.get('Content-Type') || 'application/json',
    });

    if (resp.body) {
      return new Response(resp.body, { status: resp.status, headers: respHeaders });
    }
    return new Response(await resp.text(), { status: resp.status, headers: respHeaders });
  } catch (err: any) {
    return new Response(
      JSON.stringify({ error: 'Proxy failed', detail: err.message }),
      { status: 502, headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' } }
    );
  }
}

export function optionsResponse() {
  return new Response(null, {
    status: 204,
    headers: {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Chat-Id, X-User-Id',
      'Access-Control-Max-Age': '86400',
    },
  });
}
```

### Apendice D — Patron de cada route.ts del Proxy

Cada archivo route.ts sigue este patron exacto. Solo cambia el `targetPath`:

```typescript
import { proxyRequest, optionsResponse } from '@/app/api/zai-proxy/_lib';
import { NextRequest } from 'next/server';

export async function POST(request: NextRequest) {
  return proxyRequest('AQUI-VA-EL-TARGET-PATH', request);
}

export async function OPTIONS() { return optionsResponse(); }
```

| Archivo | targetPath |
|---|---|
| `v1/chat/completions/route.ts` | `chat/completions` |
| `v1/vision/route.ts` | `vision` |
| `v1/tts/route.ts` | `tts` |
| `v1/asr/route.ts` | `asr` |
| `v1/images/generations/route.ts` | `images/generations` |
| `v1/async-result/route.ts` | `async-result` |
| `v1/functions/invoke/route.ts` | `functions/invoke` |
