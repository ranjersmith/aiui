#!/bin/sh
set -eu

js_escape() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
}

provider="${LLM_UI_PROVIDER:-openai}"
default_base_url=""
if [ "$provider" = "openai" ]; then
  default_base_url="http://localhost:8081"
fi

provider_escaped="$(js_escape "$provider")"
base_url_escaped="$(js_escape "${LLM_UI_BASE_URL:-$default_base_url}")"
model_escaped="$(js_escape "${LLM_UI_MODEL:-Qwen/Qwen3-VL-8B-Instruct}")"
system_prompt_escaped="$(js_escape "${LLM_UI_SYSTEM_PROMPT:-}")"

cat > /app/static/runtime-config.js <<EOF
window.__LLM_UI_CONFIG__ = {
  provider: "${provider_escaped}",
  baseUrl: "${base_url_escaped}",
  model: "${model_escaped}",
  temperature: ${LLM_UI_TEMPERATURE:-0.3},
  maxTokens: ${LLM_UI_MAX_TOKENS:-4096},
  systemPrompt: "${system_prompt_escaped}"
};
EOF

exec node /app/static-server.mjs
