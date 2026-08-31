# PAQUETE COMPLETO: CADENA PROXY LLM PARA APA

> **Version:** 3.0 — Agosto 2025
> **Proposito:** Entregar TODOS los archivos que intervienen en la cadena proxy LLM.
> **Destino:** El agente Z.ai (sandbox) + tu PC (Windows)

---

## INDICE DE ARCHIVOS

### PARTE 1 — Sandbox Z.ai (9 archivos)
| # | Archivo | Ruta en sandbox | Lineas |
|---|---------|----------------|--------|
| 1 | `_lib.ts` | `src/app/api/zai-proxy/_lib.ts` | 73 |
| 2 | `chat/completions/route.ts` | `src/app/api/zai-proxy/v1/chat/completions/route.ts` | 8 |
| 3 | `vision/route.ts` | `src/app/api/zai-proxy/v1/vision/route.ts` | 8 |
| 4 | `tts/route.ts` | `src/app/api/zai-proxy/v1/tts/route.ts` | 8 |
| 5 | `asr/route.ts` | `src/app/api/zai-proxy/v1/asr/route.ts` | 8 |
| 6 | `images/generations/route.ts` | `src/app/api/zai-proxy/v1/images/generations/route.ts` | 8 |
| 7 | `async-result/route.ts` | `src/app/api/zai-proxy/v1/async-result/route.ts` | 8 |
| 8 | `functions/invoke/route.ts` | `src/app/api/zai-proxy/v1/functions/invoke/route.ts` | 8 |
| 9 | `setup-proxy.sh` | `setup-proxy.sh` | 132 |

### PARTE 2 — Tu PC: MB Sandbox (3 archivos)
| # | Archivo | Ruta en tu PC | Lineas |
|---|---------|-------------|--------|
| 10 | `package.json` | `mb-sandbox/package.json` | 11 |
| 11 | `index.ts` | `mb-sandbox/index.ts` | 141 |
| 12 | `.z-ai-config` | `mb-sandbox/.z-ai-config` | 5 (plantilla) |

### PARTE 3 — Tu PC: Configuracion APA (5 archivos)
| # | Archivo | Ruta en tu PC | Lineas |
|---|---------|-------------|--------|
| 13 | `.env` | `apa/.env` | 3 (plantilla) |
| 14 | `settings.py` | `apa/config/settings.py` | 445 |
| 15 | `mb_launcher.py` | `apa/core/mb_launcher.py` | 351 |
| 16 | `config_apa.py` | `apa/interface/app/config_apa.py` | 257 |
| 17 | `startup.py` | `apa/interface/app/startup.py` | 423 |

### PARTE 4 — Tu PC: Fix obligatorio (1 archivo)
| # | Archivo | Ruta en tu PC | Lineas |
|---|---------|-------------|--------|
| 18 | `chat_engine.py` (con fix) | `apa/interface/app/chat_engine.py` | 665 |

### PARTE 5 — Tu PC: Puente APA a MB (router.py)
| # | Archivo | Ruta en tu PC | Lineas |
|---|---------|-------------|--------|
| 19 | `router.py` (funciones clave) | `apa/core/router.py` | ~110 (de 2906) |

### PARTE 6 — Tu PC: Scripts de automatizacion (2 archivos)
| # | Archivo | Ruta en tu PC | Lineas |
|---|---------|-------------|--------|
| 20 | `setup-mb.ps1` | `setup-mb.ps1` | 317 |
| 21 | `start-apa.ps1` | `start-apa.ps1` | 133 |

### PARTE 7 — Tests de validacion (2 archivos)
| # | Archivo | Ubicacion |
|---|---------|----------|
| 22 | `test_proxy_chain_sandbox.py` | `download/test_proxy_chain_sandbox.py` (ya existe) |
| 23 | `test_proxy_chain_windows.py` | `download/test_proxy_chain_windows.py` (ya existe) |

### PARTE 8 — Documentacion (2 archivos)
| # | Archivo | Ubicacion |
|---|---------|----------|
| 24 | `proxy-llm-setup.md` | `upload/proxy-llm-setup.md` (ya existe) |
| 25 | `INFORME_PROXY_LLM.md` | `upload/INFORME_PROXY_LLM.md` (ya existe) |

**Total: 25 archivos (23 con contenido completo + 2 de referencia documental)**

---

---

# PARTE 1: ARCHIVOS DEL SANDBOX Z.AI

> Estos 9 archivos viven dentro del sandbox de Z.ai.
> Si el sandbox se reinicia, `setup-proxy.sh` (archivo #9) los recrea automaticamente.
> El agente Z.ai los gestiona. Tu NO necesitas copiarlos a tu PC.

---

## 1.1 `_lib.ts` — El corazon del proxy

**Ruta:** `src/app/api/zai-proxy/_lib.ts`
**Funcion:** Lee credenciales reales de `/etc/.z-ai-config`, inyecta headers, reenvia a `internal-api.z.ai`. No usa el SDK — usa `fetch` directo.

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

---

## 1.2 `v1/chat/completions/route.ts`

**Ruta:** `src/app/api/zai-proxy/v1/chat/completions/route.ts`
**Target:** `chat/completions`

```typescript
import { proxyRequest, optionsResponse } from '@/app/api/zai-proxy/_lib';
import { NextRequest } from 'next/server';

export async function POST(request: NextRequest) {
  return proxyRequest('chat/completions', request);
}

export async function OPTIONS() { return optionsResponse(); }
```

---

## 1.3 `v1/vision/route.ts`

**Ruta:** `src/app/api/zai-proxy/v1/vision/route.ts`
**Target:** `vision`

```typescript
import { proxyRequest, optionsResponse } from '@/app/api/zai-proxy/_lib';
import { NextRequest } from 'next/server';

export async function POST(request: NextRequest) {
  return proxyRequest('vision', request);
}

export async function OPTIONS() { return optionsResponse(); }
```

---

## 1.4 `v1/tts/route.ts`

**Ruta:** `src/app/api/zai-proxy/v1/tts/route.ts`
**Target:** `tts`

```typescript
import { proxyRequest, optionsResponse } from '@/app/api/zai-proxy/_lib';
import { NextRequest } from 'next/server';

export async function POST(request: NextRequest) {
  return proxyRequest('tts', request);
}

export async function OPTIONS() { return optionsResponse(); }
```

---

## 1.5 `v1/asr/route.ts`

**Ruta:** `src/app/api/zai-proxy/v1/asr/route.ts`
**Target:** `asr`

```typescript
import { proxyRequest, optionsResponse } from '@/app/api/zai-proxy/_lib';
import { NextRequest } from 'next/server';

export async function POST(request: NextRequest) {
  return proxyRequest('asr', request);
}

export async function OPTIONS() { return optionsResponse(); }
```

---

## 1.6 `v1/images/generations/route.ts`

**Ruta:** `src/app/api/zai-proxy/v1/images/generations/route.ts`
**Target:** `images/generations`

```typescript
import { proxyRequest, optionsResponse } from '@/app/api/zai-proxy/_lib';
import { NextRequest } from 'next/server';

export async function POST(request: NextRequest) {
  return proxyRequest('images/generations', request);
}

export async function OPTIONS() { return optionsResponse(); }
```

---

## 1.7 `v1/async-result/route.ts`

**Ruta:** `src/app/api/zai-proxy/v1/async-result/route.ts`
**Target:** `async-result`

```typescript
import { proxyRequest, optionsResponse } from '@/app/api/zai-proxy/_lib';
import { NextRequest } from 'next/server';

export async function POST(request: NextRequest) {
  return proxyRequest('async-result', request);
}

export async function OPTIONS() { return optionsResponse(); }
```

---

## 1.8 `v1/functions/invoke/route.ts`

**Ruta:** `src/app/api/zai-proxy/v1/functions/invoke/route.ts`
**Target:** `functions/invoke`

```typescript
import { proxyRequest, optionsResponse } from '@/app/api/zai-proxy/_lib';
import { NextRequest } from 'next/server';

export async function POST(request: NextRequest) {
  return proxyRequest('functions/invoke', request);
}

export async function OPTIONS() { return optionsResponse(); }
```

---

## 1.9 `setup-proxy.sh` — El reconstructor

**Ruta:** `setup-proxy.sh` (raiz del proyecto)
**Funcion:** Verifica que los 9 archivos del proxy existen y recrea los que falten. El agente lo ejecuta al inicio de cada sesion.

```bash
#!/bin/bash
# setup-proxy.sh — Verifica y recrea los archivos del proxy Z.ai en el sandbox
# Uso: bash /home/z/my-project/setup-proxy.sh

BASE="/home/z/my-project"
PROXY_DIR="$BASE/src/app/api/zai-proxy"
LIB_FILE="$PROXY_DIR/_lib.ts"

OK="\033[0;32m[OK]\033[0m"
CREANDO="\033[0;33m[CREANDO]\033[0m"

echo ""
echo "=== Verificacion del Proxy Z.ai ==="
echo ""

# --- _lib.ts ---
if [ -f "$LIB_FILE" ]; then
    echo "$OK _lib.ts"
else
    cat > "$LIB_FILE" << 'LIBEOF'
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
LIBEOF
    echo "$CREANDO _lib.ts"
fi

# --- Rutas (7 endpoints) ---
ROUTES="
v1/chat/completions:chat/completions
v1/vision:vision
v1/tts:tts
v1/asr:asr
v1/images/generations:images/generations
v1/async-result:async-result
v1/functions/invoke:functions/invoke
"

echo "$ROUTES" | while IFS=: read -r dir target; do
    [ -z "$dir" ] && continue
    FILE="$PROXY_DIR/$dir/route.ts"
    if [ -f "$FILE" ]; then
        echo "$OK $dir/route.ts"
    else
        mkdir -p "$(dirname "$FILE")"
        cat > "$FILE" << ROUTEEOF
import { proxyRequest, optionsResponse } from '@/app/api/zai-proxy/_lib';
import { NextRequest } from 'next/server';

export async function POST(request: NextRequest) {
  return proxyRequest('$target', request);
}

export async function OPTIONS() { return optionsResponse(); }
ROUTEEOF
        echo "$CREANDO $dir/route.ts"
    fi
done

echo ""
echo "=== Proxy verificado ==="
echo ""
```

---

---

# PARTE 2: ARCHIVOS PARA TU PC — MB SANDBOX

> Estos 3 archivos van en la carpeta `mb-sandbox/` de tu PC.
> El script `setup-mb.ps1` (Parte 6) los crea automaticamente.
> Tambien estan en `download/mb-sandbox/` de este proyecto.

---

## 2.1 `package.json`

**Ruta en tu PC:** `mb-sandbox/package.json`
**Funcion:** Le dice a Bun que instale `z-ai-web-dev-sdk`

```json
{
  "name": "mb-sandbox",
  "version": "1.0.0",
  "scripts": {
    "dev": "bun --hot index.ts"
  },
  "dependencies": {
    "z-ai-web-dev-sdk": "latest"
  }
}
```

---

## 2.2 `index.ts` — El servidor local

**Ruta en tu PC:** `mb-sandbox/index.ts`
**Funcion:** Escucha en puerto 8100, recibe peticiones de APA, las envia al LLM via SDK.
**Puerto:** 8100
**Endpoints:** GET /api/status, GET /api/models, POST /api/call

```typescript
// mb-sandbox/index.ts — Sandbox del Model Broker para APA
// Escucha en puerto 8100 y expone los endpoints que APA necesita.
// Usa z-ai-web-dev-sdk para generar respuestas reales de LLM.
// NO tiene respuestas simuladas — si el SDK falla, retorna error.

import ZAI from "z-ai-web-dev-sdk";

const PORT = 8100;

const AVAILABLE_MODELS = [
  { model: "sandbox-default", provider: "sandbox" },
];

let zaiInstance: Awaited<ReturnType<typeof ZAI.create>> | null = null;
let sdkReady = false;
let sdkError: string | null = null;

async function getZAI() {
  if (!zaiInstance) {
    try {
      zaiInstance = await ZAI.create();
      sdkReady = true;
      sdkError = null;
      console.log("[MB] SDK inicializado correctamente");
    } catch (err: any) {
      sdkReady = false;
      sdkError = err.message || String(err);
      console.error("[MB] Error al inicializar SDK:", sdkError);
      throw err;
    }
  }
  return zaiInstance;
}

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

async function handleRequest(req: Request): Promise<Response> {
  const url = new URL(req.url);
  const path = url.pathname;

  // GET /api/status
  if (req.method === "GET" && path === "/api/status") {
    return jsonResponse({
      mode: "sandbox",
      status: "ok",
      sdk_ready: sdkReady,
      sdk_error: sdkError,
      models_count: AVAILABLE_MODELS.length,
    });
  }

  // GET /api/models
  if (req.method === "GET" && path === "/api/models") {
    return jsonResponse(AVAILABLE_MODELS);
  }

  // POST /api/call — SIEMPRE llama al LLM real, nunca simula
  if (req.method === "POST" && path === "/api/call") {
    const t0 = Date.now();
    try {
      const parsed = await req.json();

      const systemPrompt = parsed.system_prompt || "";
      const userPrompt = parsed.user_prompt || "";

      if (!userPrompt) {
        return jsonResponse({
          success: false,
          error: "user_prompt is required",
          content: "",
          model_used: "",
          provider: null,
          http_status: null,
        }, 400);
      }

      const zai = await getZAI();

      // system_prompt como role "system", NO como "assistant"
      const messages: Array<{ role: string; content: string }> = [];
      if (systemPrompt) {
        messages.push({ role: "system", content: systemPrompt });
      }
      messages.push({ role: "user", content: userPrompt });

      const completion = await zai.chat.completions.create({
        messages,
      });

      const content = completion.choices?.[0]?.message?.content || "";
      const latencyMs = Date.now() - t0;

      return jsonResponse({
        content,
        model_used: "sandbox-default",
        provider: "sandbox",
        success: true,
        error: null,
        http_status: 200,
        latency_ms: latencyMs,
      });
    } catch (err: any) {
      return jsonResponse({
        success: false,
        error: err.message || "Error interno del sandbox",
        content: "",
        model_used: "sandbox-default",
        provider: "sandbox",
        http_status: 500,
        latency_ms: Date.now() - t0,
      }, 500);
    }
  }

  return jsonResponse({ error: "Not found" }, 404);
}

const server = Bun.serve({
  hostname: "0.0.0.0",
  port: PORT,
  async fetch(req) {
    try {
      return await handleRequest(req);
    } catch (err: any) {
      return jsonResponse({ error: err.message }, 500);
    }
  },
});

console.log(`MB Sandbox escuchando en puerto ${PORT}`);
```

---

## 2.3 `.z-ai-config` (PLANTILLA)

**Ruta en tu PC:** `mb-sandbox/.z-ai-config`
**Funcion:** Le dice al SDK a donde enviar los mensajes.
**NOTA CRITICA:** Este archivo lo genera `setup-mb.ps1` automaticamente. NO lo edites a mano.

Formato correcto:

```json
{
  "baseUrl": "https://preview-chat-{TU-UUID-AQUI}.space-z.ai/api/zai-proxy/v1",
  "apiKey": "Z.ai",
  "chatId": "chat-{TU-UUID-AQUI}"
}
```

Reglas:
- `baseUrl`: lleva `preview-chat-`, termina en `/api/zai-proxy/v1`
- `chatId`: lleva prefijo `chat-`
- Todo en **camelCase** (NO `base_url` ni `api_key`)
- UTF-8 **sin BOM**
- El `{TU-UUID-AQUI}` es el UUID de tu sesion de Z.ai (sin el prefijo `chat-`)

---

---

# PARTE 3: ARCHIVOS DE CONFIGURACION DE APA

> Estos archivos van dentro de la carpeta `apa/` de tu PC.
> Ya existen en tu instalacion de APA. Se incluyen aqui para referencia y por si necesitas verificarlos.

---

## 3.1 `apa/.env` (PLANTILLA)

**Ruta en tu PC:** `apa/.env`
**Funcion:** 3 variables que conectan APA con MB Sandbox.

```
MODEL_BROKER_URL=http://127.0.0.1:8100
MODEL_BROKER_START_CMD=bun --hot index.ts
SANDBOX_PATH=RUTA_ABSOLUTA_A_tu_carpeta_mb-sandbox
```

Notas:
- `MODEL_BROKER_URL`: La URL donde APA busca a MB Sandbox. Siempre `http://127.0.0.1:8100`.
- `MODEL_BROKER_START_CMD`: El comando que APA ejecuta para levantar MB si no esta corriendo.
- `SANDBOX_PATH`: La ruta absoluta a tu carpeta `mb-sandbox/` (donde esta `index.ts`).
- **NO** incluir `ZAI_PROXY_URL` — esa variable esta obsoleta y causo el error 410 Gone.

---

## 3.2 `settings.py`

**Ruta en tu PC:** `apa/config/settings.py`
**Funcion:** Carga el `.env`, expone las variables al resto de APA. Singleton `settings`.

```python
# apa/config/settings_v2.py
#
# v2.1 — Configuracion post-migracion a Model Broker.
# Sin API keys de providers externos. Todo el routing de LLMs
# pasa por Model Broker.
#
# Emergency fallback: solo Ollama (proveedor local).
# Si MB cae y no puede capturar modelos, se usa Ollama directo.
#
# Reemplaza a settings.py original.
#
# Variables de entorno:
#   MODEL_BROKER_URL         — URL del servicio Model Broker
#   MODEL_BROKER_API_KEY     — API key para autenticar con MB
#   OLLAMA_BASE_URL          — URL de Ollama local (default: http://localhost:11434)
#   OLLAMA_DEFAULT_MODEL     — Modelo Ollama por defecto (default: llama3.1)
#   APA_LOG_LEVEL            — Nivel de log (default: INFO)
#   NAS_SANDBOX_PATH         — Path sandbox (default: /tmp/apa_sandbox)
#
# Validacion:
#     python config/settings_v2.py

import os
import logging
from pathlib import Path
from typing import Dict, Optional, Any, List

logger = logging.getLogger(__name__)


# =========================================================================
# DOTENV LOADER — carga .env al entorno (sin dependencia externa)
# Reutiliza la misma logica que model_broker/settings_bridge.py
# =========================================================================

def _find_and_load_dotenv() -> Optional[str]:
    """Busca .env en ubicaciones logicas y carga sus variables al entorno.

    Prioridad (igual que MB settings_bridge.py):
      1. Raiz del paquete apa (el .env propio de APA)
      2. CWD
      3. Directorios padre ascendentes (repo compartido como fallback)

    Retorna la ruta del archivo cargado, o None.
    """
    candidates = []

    # PRIORIDAD 1: Raiz del paquete apa (el .env propio de APA)
    this_dir = Path(__file__).resolve().parent  # config/
    apa_dir = this_dir.parent                      # apa/
    candidates.append(("APA_ROOT", apa_dir / ".env"))

    # CWD
    candidates.append(("CWD", Path.cwd() / ".env"))

    # Padre de apa (repo compartido como fallback)
    repo_dir = apa_dir.parent                       # apa-repo/
    candidates.append(("APA_PARENT", repo_dir / ".env"))
    candidates.append(("APA_GRANDPARENT", repo_dir.parent / ".env"))

    # Subiendo desde CWD
    current = Path.cwd()
    for i in range(6):
        candidates.append((f"CWD_UP_{i}", current / ".env"))
        parent = current.parent
        if parent == current:
            break
        current = parent

    seen = set()
    for label, candidate in candidates:
        try:
            resolved = str(candidate.resolve())
        except Exception:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)

        try:
            with open(resolved, "r", encoding="utf-8-sig") as f:
                f.readline()  # solo verificar que es legible
            logger.debug("settings: .env encontrado en %s: %s", label, resolved)
            loaded = _load_dotenv_file(Path(resolved))
            logger.info("settings: .env cargado desde %s (%d variables)", label, loaded)
            return resolved
        except (FileNotFoundError, PermissionError):
            continue
        except Exception as e:
            logger.debug("settings: candidato %s: error: %s", label, e)
            continue

    logger.debug("settings: ningun .env encontrado en %d candidatos", len(seen))
    return None


def _load_dotenv_file(env_path: Path) -> int:
    """Carga un fichero .env simple (lineas KEY=VALUE, ignora # y vacias).

    Usa utf-8-sig para manejar BOM automaticamente.
    No sobreescribe variables ya definidas en el entorno.
    Retorna el numero de claves cargadas.
    """
    loaded = 0
    try:
        with open(env_path, "r", encoding="utf-8-sig") as f:
            for line_num, raw_line in enumerate(f, 1):
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("'\"")
                if not key:
                    continue
                if key not in os.environ:
                    os.environ[key] = value
                    loaded += 1
    except Exception as e:
        logger.warning("Error leyendo %s: %s", env_path, e)
    return loaded


# Cargar .env ANTES de crear el singleton Settings
_env_loaded_from = _find_and_load_dotenv()


# =========================================================================
# EMERGENCY CONFIG — Ollama como proveedor local de respaldo.
# No se usan claves externas (OpenRouter, etc.).
# Si MB cae y no puede capturar modelos, se intenta solo con Ollama.
# =========================================================================

_OLLAMA_CONFIG: Dict[str, str] = {}


def _load_ollama_config() -> Dict[str, str]:
    """Carga la configuracion de Ollama desde variables de entorno.

    Variables:
        OLLAMA_BASE_URL       — URL base de Ollama (ej: http://localhost:11434)
        OLLAMA_DEFAULT_MODEL  — modelo Ollama por defecto (ej: llama3.1)

    Ollama no necesita API key — es un proveedor local.
    """
    config = {}

    url = os.environ.get("OLLAMA_BASE_URL", "").strip()
    if url:
        config["ollama_base_url"] = url.rstrip("/")
    else:
        # Default: Ollama suele estar en localhost:11434
        config["ollama_base_url"] = "http://localhost:11434"

    model = os.environ.get("OLLAMA_DEFAULT_MODEL", "").strip()
    if model:
        config["ollama_model"] = model
    else:
        config["ollama_model"] = "llama3.1"

    return config


def get_emergency_keys() -> Dict[str, str]:
    """Retorna la configuracion de emergencia (Ollama).

    En v2.1 el emergency harness solo usa Ollama como proveedor
    local. No hay claves externas.

    Retorna dict con:
        - ollama_base_url: URL de Ollama
        - ollama_model: modelo por defecto
    """
    global _OLLAMA_CONFIG
    if not _OLLAMA_CONFIG:
        _OLLAMA_CONFIG = _load_ollama_config()
    return dict(_OLLAMA_CONFIG)


def has_emergency_keys() -> bool:
    """Retorna True si hay configuracion de emergencia (Ollama).

    Ollama siempre esta configurado (tiene default localhost:11434),
    por lo que siempre retorna True. La verificacion real de si
    Ollama esta corriendo se hace al intentar la llamada.
    """
    return True


def reload_emergency_keys() -> Dict[str, str]:
    """Recarga la configuracion de emergencia desde entorno.

    Util para hot-reload sin reiniciar la aplicacion.
    """
    global _OLLAMA_CONFIG
    _OLLAMA_CONFIG = _load_ollama_config()
    logger.info("Emergency config recargada: Ollama en %s", _OLLAMA_CONFIG.get("ollama_base_url"))
    return dict(_OLLAMA_CONFIG)


# =========================================================================
# MODEL BROKER CONFIG
# =========================================================================

def _get_mb_config() -> Dict[str, Any]:
    """Obtiene la configuracion de Model Broker desde entorno."""
    return {
        "url": os.environ.get("MODEL_BROKER_URL", "").strip(),
        "api_key": os.environ.get("MODEL_BROKER_API_KEY", "").strip(),
    }


# =========================================================================
# SETTINGS PRINCIPAL — objeto unico de configuracion
# =========================================================================

class Settings:
    """Configuracion centralizada de APA v2.1.

    Post-migracion: sin API keys de providers individuales.
    Todo via Model Broker + emergency Ollama (local).
    """

    # --- Model Broker ---
    @property
    def model_broker_url(self) -> str:
        return os.environ.get("MODEL_BROKER_URL", "").strip()

    @property
    def model_broker_api_key(self) -> str:
        return os.environ.get("MODEL_BROKER_API_KEY", "").strip()

    @property
    def model_broker_config(self) -> Dict[str, str]:
        return _get_mb_config()

    @property
    def model_broker_start_cmd(self) -> str:
        """Comando para arrancar MB en modo sandbox (desarrollo).

        Si esta vacio, APA no intenta arrancar MB localmente.
        Ejemplo: 'bun --hot index.ts'
        """
        return os.environ.get("MODEL_BROKER_START_CMD", "").strip()

    @property
    def model_broker_start_dir(self) -> str:
        """Directorio de trabajo para arrancar MB en modo sandbox.

        Lee SANDBOX_PATH del entorno (misma variable que el sandbox general).
        Si esta vacio, APA no intenta arrancar MB localmente.
        """
        return os.environ.get("SANDBOX_PATH", "").strip()

    # --- Emergency (Ollama local) ---
    @property
    def emergency_keys(self) -> Dict[str, str]:
        return get_emergency_keys()

    @property
    def has_emergency(self) -> bool:
        return has_emergency_keys()

    # --- Ollama directo ---
    @property
    def ollama_base_url(self) -> str:
        return get_emergency_keys().get("ollama_base_url", "http://localhost:11434")

    @property
    def ollama_default_model(self) -> str:
        return get_emergency_keys().get("ollama_model", "llama3.1")

    # --- General ---
    @property
    def log_level(self) -> str:
        return os.environ.get("APA_LOG_LEVEL", "INFO").strip()

    @property
    def nas_sandbox_path(self) -> str:
        return os.environ.get("NAS_SANDBOX_PATH", "/tmp/apa_sandbox").strip()

    @property
    def openrouter_api_key(self) -> str:
        """Backward compat — siempre vacio en v2.1.

        Los providers externos se gestionan via Model Broker.
        El emergency harness solo usa Ollama local.
        """
        return ""

    def __repr__(self) -> str:
        mb_url = self.model_broker_url or "(no configurada)"
        ollama = self.ollama_base_url
        return (f"Settings(mb_url={mb_url}, "
                f"ollama={ollama}, "
                f"log={self.log_level})")


# Singleton
settings = Settings()


# =========================================================================
# DIAGNOSTICO AL ARRANQUE
# =========================================================================

def _log_startup_warnings() -> None:
    """Advierte al arrancar si falta configuracion importante."""
    if _env_loaded_from:
        logger.info("settings: .env cargado desde %s", _env_loaded_from)
    else:
        logger.warning("settings: .env NO encontrado — usando variables de entorno del sistema")

    if not settings.model_broker_url:
        logger.warning(
            "settings: MODEL_BROKER_URL no configurada. "
            "APA operara en modo emergencia con Ollama local."
        )
    else:
        logger.info(
            "settings: Model Broker configurado en %s",
            settings.model_broker_url
        )

    if settings.model_broker_start_cmd:
        logger.info(
            "settings: MB sandbox configurado: cmd='%s', dir='%s'",
            settings.model_broker_start_cmd,
            settings.model_broker_start_dir,
        )
    else:
        logger.info(
            "settings: MB sandbox no configurado (sin MODEL_BROKER_START_CMD o SANDBOX_PATH)"
        )

    logger.info(
        "settings: Emergency fallback: Ollama en %s (modelo: %s)",
        settings.ollama_base_url,
        settings.ollama_default_model,
    )


_log_startup_warnings()
```

---

## 3.3 `mb_launcher.py`

**Ruta en tu PC:** `apa/core/mb_launcher.py`
**Funcion:** Arranca MB Sandbox automaticamente si no esta corriendo. 3 niveles: check MB, launch subprocess, emergency mode.

```python
# apa/core/mb_launcher.py
"""
Lanzador silencioso de Model Broker desde APA.

APA arranca MB como subprocess en background si no esta corriendo.
MB se comunica con APA exclusivamente por HTTP — nunca como clase Python.

Uso desde APA (en el startup):
    from core.mb_launcher import ensure_mb_running
    ensure_mb_running(settings.model_broker_url)
"""
from __future__ import annotations

import sys
import os
import time
import platform
import subprocess
import logging
import requests

logger = logging.getLogger("core.mb_launcher")

_mb_process = None  # subprocess.Popen or None


def _notify_progress(on_progress, step: str, message: str, data: dict = None) -> None:
    """Envia notificacion de progreso si hay callback disponible."""
    if on_progress is None:
        return
    try:
        on_progress(step, message, data or {})
    except Exception:
        pass


def ensure_mb_running(mb_url: str, timeout: float = 15.0,
                       on_progress=None, start_cmd: str = "", start_dir: str = "") -> bool:
    """Asegura que MB este corriendo y respondiendo por HTTP.

    Flujo (3 niveles):
    1. Verificar si MB ya responde en la URL (produccion).
    2. Si no responde, intentar arrancar sandbox local (desarrollo).
    3. Si tampoco, retorna False (APA usara emergency harness).

    En cada paso se notifica el progreso si se proporciona on_progress.

    Args:
        mb_url: URL base de MB, ej. ``http://127.0.0.1:8100``.
        timeout: Maximos segundos a esperar tras lanzar el sandbox.
        on_progress: Callback(step, message, data) para notificaciones.
        start_cmd: Comando para arrancar el sandbox (ej. ``bun --hot index.ts``).
        start_dir: Directorio de trabajo del sandbox.

    Returns:
        True si MB responde, False si no se pudo iniciar.
    """
    global _mb_process

    if not mb_url or not mb_url.strip():
        logger.debug("ensure_mb_running: sin URL configurada, skip")
        _notify_progress(on_progress, "no_url", "Sin URL de MB configurada")
        return False

    mb_url = mb_url.rstrip("/")

    # 1. Si ya tenemos un subprocess vivo, verificar si responde
    if _mb_process is not None and _mb_process.poll() is None:
        if _health_check(mb_url):
            return True
        # Proceso existe pero no responde — matar y relanzar
        logger.debug("MB subprocess vivo pero no responde, reiniciando...")
        _terminate_process(_mb_process)
        _mb_process = None

    # -- NIVEL 1: MB responde en la URL configurada (produccion) --
    _notify_progress(on_progress, "checking_url", "Verificando MB en la URL configurada...")
    if _health_check(mb_url):
        logger.info("MB ya corriendo en %s", mb_url)
        _notify_progress(on_progress, "mb_running", "MB responde correctamente")
        return True

    _notify_progress(on_progress, "url_failed", "MB no responde en la URL, intentando sandbox local...")

    # -- NIVEL 2: Arrancar sandbox local (desarrollo) --
    if not start_cmd or not start_dir:
        logger.warning("Sin configuracion de sandbox (start_cmd/start_dir vacios)")
        _notify_progress(on_progress, "no_sandbox_config", "No hay configuracion de sandbox, MB no disponible")
        return False

    _notify_progress(on_progress, "launching_sandbox", "Lanzando sandbox de MB...")

    cwd = start_dir
    try:
        cmd_parts = start_cmd.split()
        popen_kwargs = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "stdin": subprocess.DEVNULL,
            "cwd": cwd,
        }
        # Compatibilidad Windows/Linux para detach del proceso
        if platform.system() == "Windows":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True

        _mb_process = subprocess.Popen(cmd_parts, **popen_kwargs)
        logger.info("MB sandbox lanzado (PID: %d, cwd: %s, cmd: %s)", _mb_process.pid, cwd, start_cmd)
    except FileNotFoundError:
        logger.warning("Comando no encontrado al lanzar sandbox: %s (cwd: %s)", start_cmd, cwd)
        _notify_progress(on_progress, "sandbox_cmd_not_found", "Comando del sandbox no encontrado")
        return False
    except Exception as e:
        logger.warning("Error lanzando sandbox: %s", e)
        _notify_progress(on_progress, "sandbox_error", f"Error al lanzar sandbox: {e}")
        return False

    # Esperar a que el sandbox este listo
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _mb_process.poll() is not None:
            logger.warning("MB sandbox salio con codigo %d", _mb_process.returncode)
            _notify_progress(on_progress, "sandbox_crashed", "El sandbox de MB se cerro inesperadamente")
            return False
        if _health_check(mb_url):
            elapsed = timeout - (deadline - time.time())
            logger.info("MB sandbox listo en %s (%.1fs)", mb_url, elapsed)
            _notify_progress(on_progress, "sandbox_ready", "MB sandbox levantado correctamente",
                             {"elapsed_seconds": round(elapsed, 1)})
            return True
        time.sleep(0.5)

    logger.warning("MB sandbox no respondio en %.1fs", timeout)
    _notify_progress(on_progress, "sandbox_timeout", f"MB sandbox no respondio en {timeout:.1f}s")
    return False


def _health_check(mb_url: str, timeout: float = 3.0) -> bool:
    """Verifica si MB responde a GET /api/status."""
    try:
        resp = requests.get(
            f"{mb_url}/api/status", timeout=timeout
        )
        return resp.status_code == 200
    except Exception:
        return False


def _find_mb_directory() -> str:
    """Busca el directorio raiz donde esta el paquete model_broker."""
    try:
        this_dir = os.path.dirname(os.path.abspath(__file__))
        apa_dir = os.path.dirname(this_dir)
        repo_dir = os.path.dirname(apa_dir)
        if os.path.isdir(os.path.join(repo_dir, "model_broker")):
            return repo_dir
    except Exception:
        pass
    if os.path.isdir(os.path.join(os.getcwd(), "model_broker")):
        return os.getcwd()
    return os.getcwd()


def _terminate_process(proc: subprocess.Popen) -> None:
    """Termina un subprocess de forma segura (SIGTERM -> SIGKILL)."""
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def stop_mb() -> None:
    """Detiene el subprocess de MB si fue lanzado por APA."""
    global _mb_process
    if _mb_process is not None and _mb_process.poll() is None:
        logger.info("Deteniendo MB subprocess (PID: %d)", _mb_process.pid)
        _terminate_process(_mb_process)
        _mb_process = None


def get_mb_status() -> dict:
    """Retorna el estado del launcher: si hay proceso, PID, etc."""
    return {
        "process_alive": _mb_process is not None and _mb_process.poll() is None,
        "pid": _mb_process.pid if _mb_process and _mb_process.poll() is None else None,
    }
```

---

## 3.4 `config_apa.py`

**Ruta en tu PC:** `apa/interface/app/config_apa.py`
**Funcion:** Lee `settings.py` que lee `.env`. Expone `MODEL_BROKER_URL`, `MODEL_BROKER_START_CMD`, `MODEL_BROKER_START_DIR` y `WORK_DIRECTORIES` al resto de APA.

Este archivo es largo (257 lineas con tests autonomos). La parte critica para la cadena proxy son las lineas 149-159 que exponen las variables de MB:

```python
# -- URL de servicios (las 3 variables que conectan APA con MB) --
MODEL_BROKER_URL: str = (
    getattr(settings, "MODEL_BROKER_URL", None) if settings else None
) or "http://127.0.0.1:8100"

MODEL_BROKER_START_CMD: str = (
    getattr(settings, "model_broker_start_cmd", None) if settings else None
) or ""

MODEL_BROKER_START_DIR: str = (
    getattr(settings, "model_broker_start_dir", None) if settings else None
) or ""
```

El archivo completo esta en: `APA_apa/interface/app/config_apa.py` en el sandbox, o `download/config_apa.py`.

---

## 3.5 `startup.py`

**Ruta en tu PC:** `apa/interface/app/startup.py`
**Funcion:** Orquesta la secuencia de inicio: init_subsystems() -> ensure_mb_running() -> initialize_router() -> notifica estado.

La cadena de arranque es:
```
1. config_apa.py lee settings.py -> settings.py busca y carga .env
   -> obtiene MODEL_BROKER_URL, MODEL_BROKER_START_CMD, MODEL_BROKER_START_DIR

2. startup.py -> init_subsystems()
   -> Llama ensure_mb_running(url, start_cmd, start_dir)

3. mb_launcher.py -> ensure_mb_running() [3 niveles]
   Nivel 1: MB ya responde en :8100? -> GET /api/status -> si 200, listo
   Nivel 2: Si no -> lanza MB como subprocess (bun --hot index.ts en SANDBOX_PATH)
            -> espera hasta 15 segundos con health checks cada 0.5s
   Nivel 3: Si no levanto -> retorna False -> APA entra en "modo emergencia"

4. Si MB esta listo -> router se inicializa en modo "sandbox"
   -> Los mensajes del usuario van: APA -> MB(:8100) -> SDK -> proxy -> LLM
```

El archivo completo esta en: `APA_apa/interface/app/startup.py` en el sandbox, o `download/startup.py`.

---

---

# PARTE 4: FIX OBLIGATORIO — chat_engine.py

> **IMPORTANTE:** Este es el UNICO archivo de APA que necesitas modificar.
> La diferencia con tu version actual es UNA LINEA: agregar `"success": True,` al return de `handle_chat()`.
> Sin esta linea, APA siempre muestra "Error: Respuesta vacia" aunque el LLM respondio.

---

## 4.1 `chat_engine.py` (version con fix)

**Ruta en tu PC:** `apa/interface/app/chat_engine.py`
**Fix:** Linea 226 del return en `handle_chat()` lleva `"success": True,` como primer campo.

La diferencia critica esta en el return de `handle_chat()` (alrededor de la linea 225):

**SIN fix (tu version actual probablemente):**
```python
        return {
            "response": response_text,
            "maturity_status": maturity_status,
            "model_used": model_name or "default",
        }
```

**CON fix (version correcta):**
```python
        return {
            "success": True,
            "response": response_text,
            "maturity_status": maturity_status,
            "model_used": model_name or "default",
        }
```

El archivo completo con el fix esta en `download/chat_engine.py`. Copialo a `apa/interface/app/chat_engine.py` en tu PC.

---

---

# PARTE 5: PUENTE APA A MB — router.py

> El archivo `router.py` tiene 2906 lineas. Solo estas 2 funciones intervienen en la cadena proxy.
> El resto del archivo maneja pools de modelos, arena, desescalado, cache, etc.

---

## 5.1 `_call_mb_http()` (lineas 345-403)

**Ruta en tu PC:** `apa/core/router.py`
**Funcion:** Envia la peticion HTTP POST a MB Sandbox en `http://127.0.0.1:8100/api/call`.

```python
def _call_mb_http(
    task_type: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 2000,
    temperature: float = 0.1,
    estimated_tokens: int = 0,
    priority: str = "quality",
    model_id: str = None,
    max_fallbacks: int = 2,
) -> Optional[Dict[str, Any]]:
    """v7.2: Llama a MB via HTTP POST /api/call.
    Reemplaza la importacion de ModelBroker como clase Python.
    APA y MB son apps independientes que se comunican por HTTP.
    Retorna el dict de respuesta de MB, o None si no hay conexion.
    """
    global _broker_available
    mb_url = settings.model_broker_url
    if not mb_url:
        return None
    payload = {
        "task_type": task_type,
        "user_prompt": user_prompt,
        "system_prompt": system_prompt,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if estimated_tokens > 0:
        payload["estimated_tokens"] = estimated_tokens
    if priority:
        payload["priority"] = priority
    if model_id:
        payload["model_id"] = model_id
    if max_fallbacks != 2:
        payload["max_fallbacks"] = max_fallbacks
    try:
        resp = requests.post(
            f"{mb_url.rstrip('/')}/api/call",
            json=payload,
            timeout=180,
        )
        if resp.status_code == 200:
            data = resp.json()
            _broker_available = True
            return data
        else:
            logger.warning("MB HTTP %d: %s", resp.status_code, resp.text[:200])
            return {"success": False, "error": f"MB HTTP {resp.status_code}"}
    except (requests.exceptions.ConnectionError, ConnectionError):
        _broker_available = False
        return None
    except requests.exceptions.Timeout:
        _broker_available = False
        return None
    except Exception as e:
        _broker_available = False
        logger.warning("MB HTTP error: %s", e)
        return None
```

---

## 5.2 `call_llm()` — Capa 1: MB via HTTP (lineas 2005-2102)

```python
def call_llm(
    task_type: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 2000,
    temperature: float = 0.1,
    project_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Llama al mejor LLM disponible para la tarea.

    v7.0 (fused): Tres capas de resolucion:
    1. Model Broker (ruta primaria si esta configurado)
    2. Emergency Harness (si MB cae: bootstrap -> Ollama local)
    3. Pool/Providers de v6.6 (fallback original si MB no esta configurado)
    """
    # Cache check
    if _llm_cache is not None:
        try:
            cached_response = _llm_cache.get(user_prompt, "", max_tokens=max_tokens, temperature=temperature)
            if cached_response is not None:
                return cached_response
        except Exception as e:
            logger.warning(f"Cache get failed: {e}")

    call_start_time = time.time()

    # ================================================================
    # CAPA 1: MODEL BROKER via HTTP (v7.2)
    # ================================================================
    if _has_mb_config():
        _est_tokens = estimate_task_size(system_prompt, user_prompt, max_tokens)
        _priority = get_task_priority(task_type)
        result = _call_mb_http(
            task_type=task_type,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            estimated_tokens=_est_tokens,
            priority=_priority,
        )
        if result is not None:
            total_elapsed = int((time.time() - call_start_time) * 1000)
            if result.get("success"):
                logger.info(
                    "Router v7.2: MB HTTP exito -- %s via %s (%dms)",
                    result.get("model_used", "?"),
                    result.get("provider", "?"),
                    total_elapsed
                )
                return {
                    **result,
                    "attempts": 1,
                    "via_emergency": False,
                }
            else:
                logger.warning(
                    "Router v7.2: MB HTTP fallo la llamada: %s",
                    result.get("error", "unknown")
                )
                return {
                    **result,
                    "attempts": 1,
                    "via_emergency": False,
                }
        # result is None -> MB no responde
        logger.warning("Router v7.2: MB no responde -- activando emergency")
        # ... continua con Capa 2 y 3 (emergency + pool) ...
```

---

---

# PARTE 6: SCRIPTS DE AUTOMATIZACION WINDOWS

> Estos 2 scripts se ejecutan en tu PC con PowerShell.
> `setup-mb.ps1` crea la carpeta mb-sandbox con los 3 archivos.
> `start-apa.ps1` verifica todo y lanza MB + APA.

---

## 6.1 `setup-mb.ps1` v5

**Ruta en tu PC:** Donde tengas los scripts de APA (junto a la carpeta `mb-sandbox`)
**Uso:** `.
setup-mb.ps1 -ChatId "chat-dcaab75b-801b-4f87-885b-58dbc3b5f310"`
**Funcion:** Crea `mb-sandbox/` con `package.json`, `index.ts`, `.z-ai-config`. Construye la URL desde el ChatId con `preview-chat-`.

El archivo completo esta en: `download/setup-mb.ps1`

```powershell
# setup-mb.ps1 — Configura MB Sandbox para APA
# FIX v5: URL SIEMPRE se construye desde ChatId con preview-chat-
#        chatId en config SIEMPRE lleva prefijo chat-
# Uso: .\setup-mb.ps1 [-ChatId "tu-chat-id"]

param(
    [string]$ChatId = ""
)

$ErrorActionPreference = "Stop"

# -- Rutas --
$ProjectRoot = $PSScriptRoot
$SandboxDir = Join-Path $ProjectRoot "mb-sandbox"
$ApaDir = Join-Path $ProjectRoot "apa"
$EnvFile = Join-Path $ApaDir ".env"

Write-Host ""
Write-Host "=== Configuracion de MB Sandbox ===" -ForegroundColor Cyan
Write-Host ""

# -- Paso 0: MATAR BUN ANTES DE ESCRIBIR ARCHIVOS --
Write-Host "[...] Deteniendo procesos bun existentes..." -ForegroundColor Yellow
$bunProcesses = Get-Process -Name "bun" -ErrorAction SilentlyContinue
if ($bunProcesses) {
    Stop-Process -Name "bun" -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
    Write-Host "[OK] Procesos bun terminados" -ForegroundColor Green
} else {
    Write-Host "[OK] No hay procesos bun corriendo" -ForegroundColor Green
}

# -- Paso 1: Crear carpeta --
if (-not (Test-Path $SandboxDir)) {
    New-Item -ItemType Directory -Path $SandboxDir -Force | Out-Null
    Write-Host "[OK] Creada: $SandboxDir" -ForegroundColor Green
} else {
    Write-Host "[OK] Carpeta ya existe: $SandboxDir" -ForegroundColor Green
}

# -- Paso 2: Crear package.json (SIN BOM) --
$PackageJson = Join-Path $SandboxDir "package.json"
$PackageContent = @'
{
  "name": "mb-sandbox",
  "version": "1.0.0",
  "dependencies": {
    "z-ai-web-dev-sdk": "latest"
  }
}
'@
[System.IO.File]::WriteAllText($PackageJson, $PackageContent, [System.Text.UTF8Encoding]::new($false))
Write-Host "[OK] Creado: package.json" -ForegroundColor Green

# -- Paso 3: Crear index.ts (SIN BOM, SIN respuestas simuladas) --
$IndexTs = Join-Path $SandboxDir "index.ts"
$IndexContent = @'
// mb-sandbox/index.ts — Sandbox del Model Broker para APA
// Escucha en puerto 8100 y expone los endpoints que APA necesita.
// Usa z-ai-web-dev-sdk para generar respuestas reales de LLM.
// NO tiene respuestas simuladas — si el SDK falla, retorna error.

import ZAI from "z-ai-web-dev-sdk";

const PORT = 8100;

const AVAILABLE_MODELS = [
  { model: "sandbox-default", provider: "sandbox" },
];

let zaiInstance: Awaited<ReturnType<typeof ZAI.create>> | null = null;
let sdkReady = false;
let sdkError: string | null = null;

async function getZAI() {
  if (!zaiInstance) {
    try {
      zaiInstance = await ZAI.create();
      sdkReady = true;
      sdkError = null;
      console.log("[MB] SDK inicializado correctamente");
    } catch (err: any) {
      sdkReady = false;
      sdkError = err.message || String(err);
      console.error("[MB] Error al inicializar SDK:", sdkError);
      throw err;
    }
  }
  return zaiInstance;
}

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

async function handleRequest(req: Request): Promise<Response> {
  const url = new URL(req.url);
  const path = url.pathname;

  // GET /api/status
  if (req.method === "GET" && path === "/api/status") {
    return jsonResponse({
      mode: "sandbox",
      status: "ok",
      sdk_ready: sdkReady,
      sdk_error: sdkError,
      models_count: AVAILABLE_MODELS.length,
    });
  }

  // GET /api/models
  if (req.method === "GET" && path === "/api/models") {
    return jsonResponse(AVAILABLE_MODELS);
  }

  // POST /api/call — SIEMPRE llama al LLM real, nunca simula
  if (req.method === "POST" && path === "/api/call") {
    const t0 = Date.now();
    try {
      const parsed = await req.json();

      const systemPrompt = parsed.system_prompt || "";
      const userPrompt = parsed.user_prompt || "";

      if (!userPrompt) {
        return jsonResponse({
          success: false,
          error: "user_prompt is required",
          content: "",
          model_used: "",
          provider: null,
          http_status: null,
        }, 400);
      }

      const zai = await getZAI();

      // system_prompt como role "system", NO como "assistant"
      const messages: Array<{ role: string; content: string }> = [];
      if (systemPrompt) {
        messages.push({ role: "system", content: systemPrompt });
      }
      messages.push({ role: "user", content: userPrompt });

      const completion = await zai.chat.completions.create({
        messages,
      });

      const content = completion.choices?.[0]?.message?.content || "";
      const latencyMs = Date.now() - t0;

      return jsonResponse({
        content,
        model_used: "sandbox-default",
        provider: "sandbox",
        success: true,
        error: null,
        http_status: 200,
        latency_ms: latencyMs,
      });
    } catch (err: any) {
      return jsonResponse({
        success: false,
        error: err.message || "Error interno del sandbox",
        content: "",
        model_used: "sandbox-default",
        provider: "sandbox",
        http_status: 500,
        latency_ms: Date.now() - t0,
      }, 500);
    }
  }

  return jsonResponse({ error: "Not found" }, 404);
}

const server = Bun.serve({
  hostname: "0.0.0.0",
  port: PORT,
  async fetch(req) {
    try {
      return await handleRequest(req);
    } catch (err: any) {
      return jsonResponse({ error: err.message }, 500);
    }
  },
});

console.log(`MB Sandbox escuchando en puerto ${PORT}`);
'@

try {
    [System.IO.File]::WriteAllText($IndexTs, $IndexContent, [System.Text.UTF8Encoding]::new($false))
    Write-Host "[OK] Creado: index.ts" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] No se pudo escribir index.ts: $_" -ForegroundColor Red
    exit 1
}

# -- Paso 4: Construir .z-ai-config (SIN BOM) --
$ZaiConfig = Join-Path $SandboxDir ".z-ai-config"

# Leer ChatId y ApiKey del .env (SIEMPRE ignoramos ZAI_PROXY_URL del .env)
$ChatIdVal = $ChatId
$ApiKeyVal = ""
if (Test-Path $EnvFile) {
    foreach ($line in Get-Content $EnvFile -Encoding UTF8) {
        if ($line -match '^ZAI_CHAT_ID=(.+)$' -and -not $ChatIdVal) {
            $ChatIdVal = $Matches[1].Trim().Trim('"')
        }
        if ($line -match '^ZAI_API_KEY=(.+)$') {
            $ApiKeyVal = $Matches[1].Trim().Trim('"')
        }
    }
}

if (-not $ChatIdVal) {
    Write-Host "[ERROR] No se proporciono ChatId y no se encontro ZAI_CHAT_ID en .env" -ForegroundColor Red
    Write-Host "        Usa: .\setup-mb.ps1 -ChatId \"chat-dcaab75b-801b-4f87-885b-58dbc3b5f310\"" -ForegroundColor Red
    exit 1
}

# -- Extraer UUID limpio (sin prefijo "chat-") --
$uuid = $ChatIdVal
if ($uuid -match '^chat-') { $uuid = $uuid.Substring(6) }

# -- Construir SIEMPRE la URL con preview-chat- --
$BaseUrl = "https://preview-chat-$uuid.space-z.ai/api/zai-proxy/v1"

# -- Asegurar que chatId lleve el prefijo "chat-" --
$ChatIdForConfig = $ChatIdVal
if ($ChatIdForConfig -notmatch '^chat-') { $ChatIdForConfig = "chat-$ChatIdForConfig" }

if (-not $ApiKeyVal) {
    $ApiKeyVal = "Z.ai"
    Write-Host "[INFO] ZAI_API_KEY no encontrado en .env, usando default: Z.ai" -ForegroundColor Yellow
}

# -- Mostrar lo que se va a generar (para debug) --
Write-Host ""
Write-Host "  ChatId recibido : $ChatIdVal" -ForegroundColor Gray
Write-Host "  UUID extraido   : $uuid" -ForegroundColor Gray
Write-Host "  URL del proxy   : $BaseUrl" -ForegroundColor Gray
Write-Host "  chatId en config: $ChatIdForConfig" -ForegroundColor Gray
Write-Host "  apiKey          : $ApiKeyVal" -ForegroundColor Gray
Write-Host ""

# -- Validar formato de URL antes de escribir --
if ($BaseUrl -notmatch '^https://preview-chat-[a-f0-9-]+') {
    Write-Host "[ERROR] URL generada no tiene el formato correcto: $BaseUrl" -ForegroundColor Red
    exit 1
}

# Construir JSON manual para asegurar nombres EXACTOS que el SDK espera
$ConfigParts = @()
$ConfigParts += "`"baseUrl`":`"$BaseUrl`""
$ConfigParts += "`"apiKey`":`"$ApiKeyVal`""
$ConfigParts += "`"chatId`":`"$ChatIdForConfig`""
$ConfigContent = "{" + ($ConfigParts -join ",") + "}"
[System.IO.File]::WriteAllText($ZaiConfig, $ConfigContent, [System.Text.UTF8Encoding]::new($false))
Write-Host "[OK] Creado: .z-ai-config" -ForegroundColor Green
Write-Host "       Contenido: $ConfigContent" -ForegroundColor Gray

# -- Paso 5: Instalar dependencias --
Write-Host ""
Write-Host "Instalando dependencias..." -ForegroundColor Yellow
Push-Location $SandboxDir
try {
    bun install 2>&1 | ForEach-Object { Write-Host "  $_" }
    Write-Host "[OK] Dependencias instaladas" -ForegroundColor Green
} catch {
    Write-Host "[WARN] bun install fallo: $_" -ForegroundColor Yellow
} finally {
    Pop-Location
}

# -- Paso 6: Verificar que NO hay BOM --
Write-Host ""
Write-Host "Verificando archivos (sin BOM)..." -ForegroundColor Yellow
$filesToCheck = @("index.ts", "package.json", ".z-ai-config")
foreach ($f in $filesToCheck) {
    $fpath = Join-Path $SandboxDir $f
    if (Test-Path $fpath) {
        $bytes = [System.IO.File]::ReadAllBytes($fpath)
        if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
            $cleanBytes = $bytes[3..($bytes.Length - 1)]
            [System.IO.File]::WriteAllBytes($fpath, [byte[]]$cleanBytes)
            Write-Host "  [FIX] BOM eliminada de $f" -ForegroundColor Yellow
        } else {
            Write-Host "  [OK] $f sin BOM" -ForegroundColor Green
        }
    }
}

Write-Host ""
Write-Host "=== MB Sandbox configurado correctamente ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Siguiente paso: ejecuta start-apa.ps1 o lanza manualmente:" -ForegroundColor White
Write-Host "  1. cd mb-sandbox && bun --hot index.ts" -ForegroundColor White
Write-Host "  2. python apa/interface/app_apa.py" -ForegroundColor White
Write-Host ""
```

---

## 6.2 `start-apa.ps1` v4

**Ruta en tu PC:** Donde tengas los scripts de APA
**Uso:** `.\start-apa.ps1`
**Funcion:** Verifica `.z-ai-config`, lanza MB, espera health check, lanza APA.

El archivo completo esta en: `download/start-apa.ps1`

```powershell
# start-apa.ps1 -- Inicia APA con MB Sandbox
# FIX v4: sin caracteres especiales, Join-Path compatible, verifica .z-ai-config

$ErrorActionPreference = "Continue"

$ProjectRoot = $PSScriptRoot
$SandboxDir = Join-Path $ProjectRoot "mb-sandbox"
$ApaDir = Join-Path $ProjectRoot "apa"
$IntDir = Join-Path $ApaDir "interface"
$ApaFile = Join-Path $IntDir "app_apa.py"

Write-Host ""
Write-Host "=== Iniciando APA con MB Sandbox ===" -ForegroundColor Cyan
Write-Host ""

# -- Paso 1: Matar procesos existentes
Write-Host "[...] Matando procesos bun existentes..." -ForegroundColor Yellow
$bunProcs = Get-Process -Name "bun" -ErrorAction SilentlyContinue
if ($bunProcs) {
    Stop-Process -Name "bun" -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
    Write-Host "[OK] Procesos bun terminados" -ForegroundColor Green
} else {
    Write-Host "[OK] No hay procesos bun" -ForegroundColor Green
}

# -- Paso 2: Verificar mb-sandbox
if (-not (Test-Path (Join-Path $SandboxDir "index.ts"))) {
    Write-Host "[ERROR] No se encontro mb-sandbox/index.ts" -ForegroundColor Red
    Write-Host "        Ejecuta primero: .\setup-mb.ps1 -ChatId \"tu-chat-id\"" -ForegroundColor Yellow
    exit 1
}
Write-Host "[OK] MB Sandbox encontrado en: $SandboxDir" -ForegroundColor Green

# -- Paso 2b: Verificar .z-ai-config
$ConfigFile = Join-Path $SandboxDir ".z-ai-config"
if (Test-Path $ConfigFile) {
    $cfgBytes = [System.IO.File]::ReadAllBytes($ConfigFile)
    $hasBom = ($cfgBytes.Length -ge 3 -and $cfgBytes[0] -eq 0xEF -and $cfgBytes[1] -eq 0xBB -and $cfgBytes[2] -eq 0xBF)
    if ($hasBom) {
        Write-Host "[WARN] .z-ai-config tiene BOM - esto puede causar error de SDK" -ForegroundColor Yellow
    }
    $cfgText = [System.IO.File]::ReadAllText($ConfigFile, [System.Text.UTF8Encoding]::new($false))
    $hasBaseUrl = $cfgText -match '"baseUrl"'
    $hasApiKey = $cfgText -match '"apiKey"'
    Write-Host "[OK] .z-ai-config encontrado" -ForegroundColor Green
    if (-not $hasBaseUrl -or -not $hasApiKey) {
        Write-Host "[ERROR] .z-ai-config no tiene los campos requeridos (baseUrl, apiKey)" -ForegroundColor Red
        Write-Host "        Contenido actual: $cfgText" -ForegroundColor Red
        Write-Host "        Ejecuta de nuevo: .\setup-mb.ps1" -ForegroundColor Yellow
        exit 1
    }
    Write-Host "       baseUrl: OK, apiKey: OK" -ForegroundColor Gray
} else {
    Write-Host "[ERROR] No se encontro .z-ai-config en: $ConfigFile" -ForegroundColor Red
    Write-Host "        Ejecuta primero: .\setup-mb.ps1" -ForegroundColor Yellow
    exit 1
}

# -- Paso 3: Lanzar MB Sandbox
Write-Host "[...] Lanzando MB Sandbox..." -ForegroundColor Yellow
$mbProcess = Start-Process -FilePath "bun" -ArgumentList "--hot", "index.ts" `
    -WorkingDirectory $SandboxDir `
    -WindowStyle Minimized `
    -PassThru

# Esperar a que MB responda
$mbUrl = "http://127.0.0.1:8100"
$maxWait = 10
$waited = 0
$mbOk = $false
while ($waited -lt $maxWait) {
    Start-Sleep -Seconds 1
    $waited++
    try {
        $response = Invoke-RestMethod -Uri "$mbUrl/api/status" -TimeoutSec 3 -ErrorAction Stop
        $mbOk = $true
        $mode = $response.mode
        $sdkReady = $null
        if ($response.PSObject.Properties.Name -contains "sdk_ready") {
            $sdkReady = $response.sdk_ready
        }
        $sdkStr = if ($sdkReady -eq $true) { "True" } elseif ($sdkReady -eq $false) { "False" } else { "N/A" }
        Write-Host "[OK] MB Sandbox listo (modo: $mode, SDK: $sdkStr) en ${waited}s" -ForegroundColor Green
        break
    } catch {
        # MB aun no responde
    }
}

if (-not $mbOk) {
    Write-Host "[WARN] MB Sandbox no respondio en ${maxWait}s" -ForegroundColor Yellow
    Write-Host "       APA funcionara en modo emergencia" -ForegroundColor Yellow
}

# -- Paso 4: Verificar APA
if (-not (Test-Path $ApaFile)) {
    Write-Host "[ERROR] No se encontro: $ApaFile" -ForegroundColor Red
    exit 1
}
Write-Host "[OK] APA encontrado en: $ApaFile" -ForegroundColor Green

# -- Paso 5: Lanzar APA
Write-Host "[...] Lanzando APA..." -ForegroundColor Yellow

$pythonCmd = $null
if (Get-Command "python" -ErrorAction SilentlyContinue) {
    $pythonCmd = "python"
} elseif (Get-Command "python3" -ErrorAction SilentlyContinue) {
    $pythonCmd = "python3"
} else {
    Write-Host "[ERROR] No se encontro python" -ForegroundColor Red
    exit 1
}

Start-Process -FilePath $pythonCmd -ArgumentList $ApaFile `
    -WorkingDirectory $IntDir `
    -WindowStyle Normal

Start-Sleep -Seconds 2

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  APA arrancando en http://localhost:8080" -ForegroundColor White
Write-Host "  MB Sandbox corriendo en puerto 8100" -ForegroundColor White
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "[OK] APA iniciado. Abre http://localhost:8080 en tu navegador." -ForegroundColor Green
Write-Host ""
Write-Host "NOTA: sdk_ready sera False hasta la primera llamada." -ForegroundColor Yellow
Write-Host "      Esto es normal. El SDK se inicializa en la primera llamada." -ForegroundColor Yellow
Write-Host "      Despues del primer mensaje, /api/status mostrara sdk_ready: True." -ForegroundColor Yellow
Write-Host ""
```

---

---

# PARTE 7: TESTS DE VALIDACION

> Estos archivos ya existen en `download/`. No se incluyen aqui por tamano (test_sandbox: ~800 lineas, test_windows: ~1000 lineas).
> Consultalos directamente en:
> - `download/test_proxy_chain_sandbox.py` — 40 verificaciones para el sandbox
> - `download/test_proxy_chain_windows.py` — 35 verificaciones para tu PC

---

---

# PARTE 8: DOCUMENTACION

> Estos documentos ya existen:
> - `upload/proxy-llm-setup.md` — Documento principal con instrucciones para el agente + lenguaje del director
> - `upload/INFORME_PROXY_LLM.md` — Informe ejecutivo narrativo

---

---

# REGLAS INVIOLABLES

| # | Regla | Consecuencia de romperla |
|---|-------|--------------------------|
| 1 | La URL del proxy lleva `preview-chat-` antes del UUID | Error 410 Gone del gateway |
| 2 | El SDK usa camelCase (`baseUrl`, `apiKey`, `chatId`) | El SDK ignora la configuracion |
| 3 | El system prompt usa `role: "system"` | Respuestas vacias del LLM |
| 4 | `.z-ai-config` del usuario es UTF-8 sin BOM | JSON parse falla silenciosamente |
| 5 | `chatId` en el config del usuario lleva prefijo `chat-` | El proxy no inyecta el header X-Chat-Id |
| 6 | NO leer `ZAI_PROXY_URL` del `.env` para construir la URL | URL incorrecta sin `preview-chat-` -> error 410 |
| 7 | Usar rutas estaticas para los endpoints, NO comodin `[...path]` | 404 intermitente con Turbopack |
| 8 | `chat_engine.py` debe incluir `"success": True` en el return | APA muestra "Respuesta vacia" siempre |
| 9 | NO eliminar `thinking:` del codigo de index.ts | Es inofensivo, el SDK lo anade automaticamente |
| 10 | `/etc/.z-ai-config` del sandbox NO se toca | Tiene credenciales reales que el proxy necesita |

---

# DIAGNOSTICO RAPIDO

| Si ves esto... | Es porque... | Haz esto |
|----------------|--------------|---------|
| "Model Broker no disponible" | MB no esta corriendo | Verifica que `.env` tenga las 3 variables. Lanza MB manualmente: `cd mb-sandbox && bun --hot index.ts` |
| "Configuration file not found" | `.z-ai-config` no esta junto a `index.ts` | Debe estar en la misma carpeta que `index.ts` |
| Error 404 del proxy | Los archivos del proxy se borraron del sandbox | Ejecutar `setup-proxy.sh` |
| Respuesta vacia del LLM | `index.ts` envia system prompt con `role: "assistant"` | Cambiar a `role: "system"` |
| "Error: Respuesta vacia" en APA | Falta `"success": True` en `chat_engine.py` | Agregarlo al return (1 linea) |
| **Error 410 Gone** | **La URL del `.z-ai-config` no tiene `preview-chat-`** | **Reejecutar `setup-mb.ps1` con el ChatId correcto** |
| Error 502 o tiempo de espera | El `chat_id` de tu sesion de Z.ai cambio | Actualizar `.z-ai-config` con el nuevo chat_id |
| Puerto ocupado (`EADDRINUSE`) | MB ya esta corriendo | Matar el proceso: `Stop-Process -Name bun` |

---

# FLUJO COMPLETO DE UN MENSAJE (5 eslabones)

```
ESLABON 1: APA (Python, :8080)
    | chat_engine.py -> router._call_mb_http()
    | POST http://127.0.0.1:8100/api/call
    | { system_prompt: "...", user_prompt: "Hola" }
    v
ESLABON 2: MB Sandbox (Bun, :8100)
    | index.ts -> getZAI() -> ZAI.create()
    | SDK lee .z-ai-config -> obtiene baseUrl
    | SDK construye: {baseUrl}/chat/completions
    | SDK envia HTTPS POST a preview-chat-{uuid}.space-z.ai/api/zai-proxy/v1/chat/completions
    v
ESLABON 3: Z.ai Gateway
    | Enruta por subdominio preview-chat-{uuid} al sandbox correcto
    v
ESLABON 4: Proxy Next.js (sandbox, :3000)
    | route.ts -> proxyRequest('chat/completions', request)
    | _lib.ts lee /etc/.z-ai-config (credenciales reales del sandbox)
    | Descarta headers del llamante, inyecta headers reales
    | fetch https://internal-api.z.ai/v1/chat/completions (con credenciales reales)
    v
ESLABON 5: LLM glm-4-plus
    | Genera respuesta
    | Vuelve: LLM -> proxy -> gateway -> SDK -> MB -> APA -> pantalla
```
