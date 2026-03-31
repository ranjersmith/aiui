const DEFAULT_CONFIG = {
  provider: "openai",
  baseUrl: "/llm",
  model: "Qwen3.5-9B-BF16.gguf",
  temperature: 0.7,
  maxTokens: 81920,
  systemPrompt: "",
  toolProfile: "safe",
  toolStrategy: "nous",
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
    toolProfile:
      typeof cfg.toolProfile === "string" && ["safe", "minimal", "trusted", "all"].includes(cfg.toolProfile)
        ? cfg.toolProfile
        : DEFAULT_CONFIG.toolProfile,
    toolStrategy:
      typeof cfg.toolStrategy === "string" && ["nous", "qwen_native", "deepseek"].includes(cfg.toolStrategy)
        ? cfg.toolStrategy
        : DEFAULT_CONFIG.toolStrategy,
  };
}

export function normalizeBaseUrl(baseUrl) {
  return String(baseUrl || "").trim().replace(/\/$/, "");
}
