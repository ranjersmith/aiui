export function parseSseBuffer(buffer, onPayload) {
  while (true) {
    const match = /\r?\n\r?\n/.exec(buffer);
    if (!match) break;

    const boundary = match.index;
    const delimiterLength = match[0].length;
    const rawEvent = buffer.slice(0, boundary);
    buffer = buffer.slice(boundary + delimiterLength);

    const payload = rawEvent
      .split(/\r?\n/)
      .filter((line) => line.startsWith("data:"))
      .map((line) => {
        const value = line.slice(5);
        return value.startsWith(" ") ? value.slice(1) : value;
      })
      .join("\n")
      .trim();

    if (payload) {
      onPayload(payload);
    }
  }
  return buffer;
}

export function buildErrorMessage(status, responseBody) {
  const fallback = String(status);
  if (!responseBody || typeof responseBody !== "object") return fallback;

  const body = responseBody;
  if (body.error && typeof body.error === "object") {
    const msg = body.error.message;
    if (typeof msg === "string" && msg.trim()) return msg;
  }
  if (typeof body.detail === "string" && body.detail.trim()) return body.detail;
  return fallback;
}
