import { normalizeBaseUrl } from "../core/config.mjs";
import { parseSseBuffer, buildErrorMessage } from "../core/sse.mjs";
import type { StreamProvider } from "../core/types";

export const streamOpenAiCompatible: StreamProvider = async ({
  config,
  userText,
  history,
  signal,
  handlers,
}) => {
  const baseUrl = normalizeBaseUrl(config.baseUrl);
  if (!baseUrl) {
    throw new Error("baseUrl is required for openai provider");
  }

  const response = await fetch(`${baseUrl}/v1/chat/completions`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
    },
    body: JSON.stringify({
      model: config.model,
      messages: [
        ...history.map((msg) => ({ role: msg.role, content: msg.content })),
        { role: "user", content: userText },
      ],
      stream: true,
      stream_options: { include_usage: true },
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
  let usage: Record<string, unknown> = {};

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    sseBuffer += decoder.decode(value, { stream: true });
    sseBuffer = parseSseBuffer(sseBuffer, (payloadText) => {
      if (payloadText === "[DONE]") {
        const completionTokens = Number(usage.completion_tokens || 0);
        if (completionTokens > 0) {
          handlers.onDone(`${completionTokens} tok`);
        } else {
          handlers.onDone("done");
        }
        return;
      }

      let event: Record<string, unknown>;
      try {
        event = JSON.parse(payloadText);
      } catch {
        return;
      }

      if (event.model) {
        handlers.onMeta(String(event.model));
      }

      if (event.usage && typeof event.usage === "object") {
        usage = event.usage as Record<string, unknown>;
      }

      const choices = Array.isArray(event.choices) ? event.choices : [];
      const first = choices[0] as Record<string, unknown> | undefined;
      const delta = (first?.delta || {}) as Record<string, unknown>;
      const contentDelta = String(delta.content || "");
      if (contentDelta) {
        handlers.onToken(contentDelta);
      }
    });
  }
};
