#!/bin/bash
# setup-proxy.sh — Recrea los archivos del Proxy LLM si faltan
# Uso: bash /home/z/my-project/setup-proxy.sh

set -e

PROXY_DIR="/home/z/my-project/src/app/api/zai-proxy"

LIB_FILE="$PROXY_DIR/_lib.ts"
ROUTES=(
  "v1/chat/completions:chat/completions"
  "v1/vision:vision"
  "v1/tts:tts"
  "v1/asr:asr"
  "v1/images/generations:images/generations"
  "v1/async-result:async-result"
  "v1/functions/invoke:functions/invoke"
)

CREATED=0
EXISTS=0

echo "=== setup-proxy.sh ==="
echo "Verificando archivos del proxy en $PROXY_DIR"
echo ""

# Crear directorios
for entry in "${ROUTES[@]}"; do
  route_dir="$PROXY_DIR/${entry%%:*}"
  mkdir -p "$route_dir"
done

# Verificar/crear _lib.ts
if [ ! -f "$LIB_FILE" ]; then
  echo "[CREANDO] _lib.ts"
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
    return new Response(JSON.stringify({ error: 'Proxy config not found' }), {
      status: 503,
      headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' },
    });
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
  CREATED=$((CREATED + 1))
else
  echo "[OK] _lib.ts"
  EXISTS=$((EXISTS + 1))
fi

# Verificar/crear cada route.ts
for entry in "${ROUTES[@]}"; do
  route_dir="$PROXY_DIR/${entry%%:*}"
  target_path="${entry##*:}"
  route_file="$route_dir/route.ts"

  if [ ! -f "$route_file" ]; then
    echo "[CREANDO] ${route_file#$PROXY_DIR/}"
    cat > "$route_file" << ROUTEEOF
import { proxyRequest, optionsResponse } from '@/app/api/zai-proxy/_lib';
import { NextRequest } from 'next/server';

export async function POST(request: NextRequest) {
  return proxyRequest('$target_path', request);
}

export async function OPTIONS() { return optionsResponse(); }
ROUTEEOF
    CREATED=$((CREATED + 1))
  else
    echo "[OK] ${route_file#$PROXY_DIR/}"
    EXISTS=$((EXISTS + 1))
  fi
done

echo ""
echo "=== Resultado ==="
echo "Existían: $EXISTS archivos"
echo "Creados:  $CREATED archivos"
echo ""

# Verificación rápida si curl está disponible
if command -v curl &> /dev/null; then
  echo "Verificando proxy..."
  STATUS=$(curl -s -o /dev/null -w '%{http_code}' -X POST http://localhost:3000/api/zai-proxy/v1/chat/completions \
    -H 'Content-Type: application/json' \
    -d '{"messages":[{"role":"user","content":"hi"}]}' 2>/dev/null || echo "000")
  if [ "$STATUS" = "200" ]; then
    echo "Proxy: ✅ OK (HTTP 200)"
  else
    echo "Proxy: ⚠️  HTTP $STATUS (puede necesitar que Next.js recompile)"
  fi
else
  echo "(curl no disponible para verificación)"
fi