const DEFAULT_CONFIG = {
  provider: "openai",
  baseUrl: "http://localhost:8081",
  model: "Qwen/Qwen3-VL-8B-Instruct",
  temperature: 0.3,
  maxTokens: 4096,
  systemPrompt: "",
};

export function readConfig() {
  const cfg = window.__LLM_UI_CONFIG__ || {};
  return {
    provider: "openai",
    baseUrl: String(cfg.baseUrl || DEFAULT_CONFIG.baseUrl).trim() || DEFAULT_CONFIG.baseUrl,
    model: String(cfg.model || DEFAULT_CONFIG.model).trim() || DEFAULT_CONFIG.model,
    temperature: Number.isFinite(Number(cfg.temperature))
      ? Number(cfg.temperature)
      : DEFAULT_CONFIG.temperature,
    maxTokens: Number.isFinite(Number(cfg.maxTokens))
      ? Number(cfg.maxTokens)
      : DEFAULT_CONFIG.maxTokens,
    systemPrompt: typeof cfg.systemPrompt === "string" ? cfg.systemPrompt : DEFAULT_CONFIG.systemPrompt,
  };
}

export function normalizeBaseUrl(baseUrl) {
  return String(baseUrl || "").trim().replace(/\/$/, "");
}
