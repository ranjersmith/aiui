import { normalizeBaseUrl } from "../core/config.mjs";
import { parseSseBuffer, buildErrorMessage } from "../core/sse.mjs";
import type { Attachment, StreamProvider } from "../core/types";

type ContentPart =
  | { type: "text"; text: string }
  | { type: "image_url"; image_url: { url: string } };

/** Build OpenAI-compatible content from text + attachments for the current turn. */
function buildUserContent(userText: string, attachments: Attachment[]): string | ContentPart[] {
  const images = attachments.filter((a) => a.type === "image" && a.dataUrl);
  const texts = attachments.filter((a) => a.type === "text" && a.textContent);

  if (images.length === 0 && texts.length === 0) {
    return userText;
  }

  const parts: ContentPart[] = [];

  // Inject text-file attachments as XML-fenced blocks before the user's prompt.
  let textBlock = "";
  for (const a of texts) {
    textBlock += `<file name="${a.name}">\n${a.textContent}\n</file>\n\n`;
  }
  const fullText = textBlock ? `${textBlock}${userText}`.trimEnd() : userText;
  if (fullText) {
    parts.push({ type: "text", text: fullText });
  }

  for (const img of images) {
    parts.push({ type: "image_url", image_url: { url: img.dataUrl! } });
  }

  return parts;
}

/** Build content for a history message (images are omitted to keep payload small). */
function buildHistoryContent(
  content: string,
  attachments: Attachment[] | undefined
): string | ContentPart[] {
  const texts = (attachments || []).filter((a) => a.type === "text" && a.textContent);
  if (texts.length === 0) return content;

  let textBlock = "";
  for (const a of texts) {
    textBlock += `<file name="${a.name}">\n${a.textContent}\n</file>\n\n`;
  }
  return `${textBlock}${content}`.trimEnd();
}

export const streamOpenAiCompatible: StreamProvider = async ({
  config,
  userText,
  history,
  attachments,
  signal,
  handlers,
}) => {
  const baseUrl = normalizeBaseUrl(config.baseUrl);
  if (!baseUrl) {
    throw new Error("baseUrl is required for openai provider");
  }

  const systemPrompt = String(config.systemPrompt || "").trim();
  const messages = [
    ...history.map((msg) => ({
      role: msg.role,
      content: buildHistoryContent(msg.content, msg.attachments),
    })),
    { role: "user", content: buildUserContent(userText, attachments) },
  ];
  if (systemPrompt) {
    messages.unshift({ role: "system", content: systemPrompt });
  }

  const response = await fetch(`${baseUrl}/v1/chat/completions`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
    },
    body: JSON.stringify({
      model: config.model,
      messages,
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
  let doneEmitted = false;
  let sawAnyEvent = false;
  let emittedAnyToken = false;

  const emitText = (raw: unknown) => {
    if (typeof raw === "string") {
      if (raw) {
        emittedAnyToken = true;
        handlers.onToken(raw);
      }
      return;
    }
    if (Array.isArray(raw)) {
      for (const part of raw) {
        if (!part || typeof part !== "object") continue;
        const textPart = (part as Record<string, unknown>).text;
        if (typeof textPart === "string" && textPart) {
          emittedAnyToken = true;
          handlers.onToken(textPart);
        }
      }
    }
  };

  const consumeEvent = (event: Record<string, unknown>) => {
    const eventType = String(event.type || "").trim().toLowerCase();
    if (eventType === "status") {
      const text = typeof event.text === "string" ? event.text : "";
      if (text) handlers.onStatus(text);
      return;
    }
    if (eventType === "tool_call") {
      const toolName = typeof event.name === "string" ? event.name : "tool";
      handlers.onStatus(`tool call: ${toolName}`);
      return;
    }
    if (eventType === "tool_result") {
      const toolName = typeof event.name === "string" ? event.name : "tool";
      handlers.onStatus(`tool result: ${toolName}`);
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
    if (!first) return;

    const delta = (first.delta || {}) as Record<string, unknown>;
    emitText(delta.content);
    emitText(delta.reasoning_content);

    const message = (first.message || {}) as Record<string, unknown>;
    emitText(message.content);
    emitText(message.reasoning_content);

    const text = first.text;
    emitText(text);
  };

  const emitDone = () => {
    if (doneEmitted) return;
    doneEmitted = true;
    const completionTokens = Number(usage.completion_tokens || 0);
    if (completionTokens > 0) {
      handlers.onDone(`${completionTokens} tok`);
    } else {
      handlers.onDone("done");
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    sseBuffer += decoder.decode(value, { stream: true });
    sseBuffer = parseSseBuffer(sseBuffer, (payloadText) => {
      sawAnyEvent = true;
      const payload = String(payloadText || "").trim();
      if (!payload) return;
      if (payload === "[DONE]") {
        emitDone();
        return;
      }

      let event: Record<string, unknown>;
      try {
        event = JSON.parse(payload);
      } catch {
        return;
      }

      consumeEvent(event);
    });
  }

  // Some backends close the stream without emitting [DONE], and some ignore
  // stream=true and return one JSON payload. Handle both so UI never hangs.
  if (!doneEmitted) {
    const tail = sseBuffer.trim();
    if (tail) {
      if (tail === "[DONE]") {
        emitDone();
      } else {
        try {
          const event = JSON.parse(tail) as Record<string, unknown>;
          consumeEvent(event);
        } catch {
          // Ignore non-JSON tail fragment.
        }
      }
    }

    // If we received events but no content and no DONE marker, avoid hanging in
    // streaming state while still showing a clear completion summary.
    if (!emittedAnyToken && sawAnyEvent) {
      handlers.onStatus("completed with empty delta stream");
    }
    emitDone();
  }
};
