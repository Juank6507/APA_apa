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
