// mb-sandbox/index.ts â€” Sandbox del Model Broker para APA
// Escucha en puerto 8100 y expone los endpoints que APA necesita.
// Usa z-ai-web-dev-sdk para generar respuestas reales de LLM.
// NO tiene respuestas simuladas â€” si el SDK falla, retorna error.

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

  // POST /api/call â€” SIEMPRE llama al LLM real, nunca simula
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