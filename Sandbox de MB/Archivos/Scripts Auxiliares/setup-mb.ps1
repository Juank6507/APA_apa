# setup-mb.ps1 — Configura MB Sandbox para APA
# FIX v5: URL SIEMPRE se construye desde ChatId con preview-chat-
#        chatId en config SIEMPRE lleva prefijo chat-
# Uso: .\setup-mb.ps1 [-ChatId "tu-chat-id"]

param(
    [string]$ChatId = ""
)

$ErrorActionPreference = "Stop"

# ── Rutas ───────────────────────────────────────────────────────────
$ProjectRoot = $PSScriptRoot
$SandboxDir = Join-Path $ProjectRoot "mb-sandbox"
$ApaDir = Join-Path $ProjectRoot "apa"
$EnvFile = Join-Path $ApaDir ".env"

Write-Host ""
Write-Host "=== Configuracion de MB Sandbox ===" -ForegroundColor Cyan
Write-Host ""

# ── Paso 0: MATAR BUN ANTES DE ESCRIBIR ARCHIVOS ──────────────────
Write-Host "[...] Deteniendo procesos bun existentes..." -ForegroundColor Yellow
$bunProcesses = Get-Process -Name "bun" -ErrorAction SilentlyContinue
if ($bunProcesses) {
    Stop-Process -Name "bun" -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
    Write-Host "[OK] Procesos bun terminados" -ForegroundColor Green
} else {
    Write-Host "[OK] No hay procesos bun corriendo" -ForegroundColor Green
}

# ── Paso 1: Crear carpeta ──────────────────────────────────────────
if (-not (Test-Path $SandboxDir)) {
    New-Item -ItemType Directory -Path $SandboxDir -Force | Out-Null
    Write-Host "[OK] Creada: $SandboxDir" -ForegroundColor Green
} else {
    Write-Host "[OK] Carpeta ya existe: $SandboxDir" -ForegroundColor Green
}

# ── Paso 2: Crear package.json (SIN BOM) ──────────────────────────
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

# ── Paso 3: Crear index.ts (SIN BOM, SIN respuestas simuladas) ───
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

# ── Paso 4: Construir .z-ai-config (SIN BOM) ──────────────────────
# CRITICAL: El SDK z-ai-web-dev-sdk espera EXACTAMENTE estos campos:
#   baseUrl (NO proxy_url), apiKey (NO api_key), chatId (NO chat_id)
#
# La URL SIEMPRE se construye desde el ChatId con el formato:
#   https://preview-chat-{uuid}.space-z.ai/api/zai-proxy/v1
# donde {uuid} es el chatId SIN el prefijo "chat-" (si lo tiene).
#
# El chatId en el config SIEMPRE lleva el prefijo "chat-" para que
# el SDK lo envie correctamente en la cabecera X-Chat-Id.

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

# ── Extraer UUID limpio (sin prefijo "chat-") ──
$uuid = $ChatIdVal
if ($uuid -match '^chat-') { $uuid = $uuid.Substring(6) }

# ── Construir SIEMPRE la URL con preview-chat- ──
$BaseUrl = "https://preview-chat-$uuid.space-z.ai/api/zai-proxy/v1"

# ── Asegurar que chatId lleve el prefijo "chat-" ──
$ChatIdForConfig = $ChatIdVal
if ($ChatIdForConfig -notmatch '^chat-') { $ChatIdForConfig = "chat-$ChatIdForConfig" }

# Si no hay API key, usar el default del proxy Z.ai
if (-not $ApiKeyVal) {
    $ApiKeyVal = "Z.ai"
    Write-Host "[INFO] ZAI_API_KEY no encontrado en .env, usando default: Z.ai" -ForegroundColor Yellow
}

# ── Mostrar lo que se va a generar (para debug) ──
Write-Host ""
Write-Host "  ChatId recibido : $ChatIdVal" -ForegroundColor Gray
Write-Host "  UUID extraido   : $uuid" -ForegroundColor Gray
Write-Host "  URL del proxy   : $BaseUrl" -ForegroundColor Gray
Write-Host "  chatId en config: $ChatIdForConfig" -ForegroundColor Gray
Write-Host "  apiKey          : $ApiKeyVal" -ForegroundColor Gray
Write-Host ""

# ── Validar formato de URL antes de escribir ──
if ($BaseUrl -notmatch '^https://preview-chat-[a-f0-9-]+') {
    Write-Host "[ERROR] URL generada no tiene el formato correcto: $BaseUrl" -ForegroundColor Red
    exit 1
}

# Construir JSON manual para asegurar nombres EXACTOS que el SDK espera
# SDK requiere: baseUrl y apiKey (camelCase, NO snake_case)
$ConfigParts = @()
$ConfigParts += "`"baseUrl`":`"$BaseUrl`""
$ConfigParts += "`"apiKey`":`"$ApiKeyVal`""
$ConfigParts += "`"chatId`":`"$ChatIdForConfig`""
$ConfigContent = "{" + ($ConfigParts -join ",") + "}"
[System.IO.File]::WriteAllText($ZaiConfig, $ConfigContent, [System.Text.UTF8Encoding]::new($false))
Write-Host "[OK] Creado: .z-ai-config" -ForegroundColor Green
Write-Host "       Contenido: $ConfigContent" -ForegroundColor Gray

# ── Paso 5: Instalar dependencias ───────────────────────────────────
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

# ── Paso 6: Verificar que NO hay BOM ────────────────────────────────
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
