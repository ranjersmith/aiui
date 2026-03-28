const DEFAULT_CONFIG = {
  provider: "aiui-proxy",
  baseUrl: "",
  model: "Qwen/Qwen3-VL-8B-Instruct",
  temperature: 0.7,
  maxTokens: 512,
};

export function readConfig() {
  const cfg = window.__LLM_UI_CONFIG__ || {};
  return {
    provider: cfg.provider === "openai" ? "openai" : "aiui-proxy",
    baseUrl: String(cfg.baseUrl || "").trim(),
    model: String(cfg.model || DEFAULT_CONFIG.model).trim() || DEFAULT_CONFIG.model,
    temperature: Number.isFinite(Number(cfg.temperature)) ? Number(cfg.temperature) : DEFAULT_CONFIG.temperature,
    maxTokens: Number.isFinite(Number(cfg.maxTokens)) ? Number(cfg.maxTokens) : DEFAULT_CONFIG.maxTokens,
  };
}

export function normalizeBaseUrl(baseUrl) {
  return String(baseUrl || "").trim().replace(/\/$/, "");
}
