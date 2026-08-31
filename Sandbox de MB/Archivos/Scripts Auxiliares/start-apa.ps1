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