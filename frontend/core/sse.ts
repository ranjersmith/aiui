export function parseSseBuffer(
  buffer: string,
  onPayload: (payload: string) => void,
): string {
  while (true) {
    const match = /\r?\n\r?\n/.exec(buffer);
    if (!match) break;

    const boundary = match.index;
    const delimiterLength = match[0].length;
    const rawEvent = buffer.slice(0, boundary);
    buffer = buffer.slice(boundary + delimiterLength);

    const payload = rawEvent
      .split(/\r?\n/)
      .filter((line: string) => line.startsWith("data:"))
      .map((line: string) => {
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

export function buildErrorMessage(
  status: number | string,
  responseBody: unknown,
): string {
  const fallback = String(status);
  if (!responseBody || typeof responseBody !== "object") return fallback;

  const body = responseBody as Record<string, unknown>;
  if (body.error && typeof body.error === "object") {
    const msg = (body.error as Record<string, unknown>).message;
    if (typeof msg === "string" && msg.trim()) return msg;
  }
  if (typeof body.detail === "string" && body.detail.trim()) return body.detail;
  return fallback;
}
