import { normalizeBaseUrl } from "../core/config.mjs";
import { parseSseBuffer, buildErrorMessage } from "../core/sse.mjs";
import type { StreamProvider } from "../core/types";

export const streamAiuiProxy: StreamProvider = async ({
  config,
  userText,
  history,
  signal,
  handlers,
}) => {
  const normalizedBaseUrl = normalizeBaseUrl(config.baseUrl);
  const endpoint = !normalizedBaseUrl
    ? "/chat"
    : normalizedBaseUrl.endsWith("/chat")
      ? normalizedBaseUrl
      : `${normalizedBaseUrl}/chat`;

  const response = await fetch(endpoint, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      message: userText,
      history: history.map((msg) => ({ role: msg.role, content: msg.content })),
      model: config.model,
      stream: true,
      temperature: config.temperature,
      max_tokens: config.maxTokens,
    }),
    signal,
  });

  if (!response.ok) {
    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      // Ignore parse errors.
    }
    throw new Error(buildErrorMessage(response.status, body));
  }

  if (!response.body) {
    throw new Error("No response stream body");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let sseBuffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    sseBuffer += decoder.decode(value, { stream: true });
    sseBuffer = parseSseBuffer(sseBuffer, (payloadText) => {
      if (payloadText === "[DONE]") return;

      let event: Record<string, unknown>;
      try {
        event = JSON.parse(payloadText);
      } catch {
        return;
      }

      const type = String(event.type || "");
      if (type === "meta") {
        const model = String(event.model || "").trim();
        if (model) handlers.onMeta(model);
        return;
      }
      if (type === "status") {
        handlers.onStatus(String(event.text || ""));
        return;
      }
      if (type === "token") {
        const delta = String(event.delta || "");
        if (delta) handlers.onToken(delta);
        return;
      }
      if (type === "error") {
        handlers.onError(String(event.error || "stream error"));
        return;
      }
      if (type === "done") {
        const metrics = (event.metrics || {}) as Record<string, unknown>;
        const tokens = Number(metrics.tokens || 0);
        const tps = Number(metrics.tokens_per_second || 0);
        const elapsed = Number(metrics.elapsed_seconds || 0);
        if (tokens > 0 && tps > 0 && elapsed > 0) {
          handlers.onDone(`${tokens} tok | ${tps.toFixed(2)} tok/s | ${elapsed.toFixed(2)}s`);
        } else {
          handlers.onDone("done");
        }
      }
    });
  }
};
