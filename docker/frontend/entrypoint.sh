#!/bin/sh
set -eu

js_escape() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
}

provider_escaped="$(js_escape "${LLM_UI_PROVIDER:-aiui-proxy}")"
base_url_escaped="$(js_escape "${LLM_UI_BASE_URL:-/llm}")"
model_escaped="$(js_escape "${LLM_UI_MODEL:-Qwen/Qwen3-VL-8B-Instruct}")"

cat > /usr/share/nginx/html/static/runtime-config.js <<EOF
window.__LLM_UI_CONFIG__ = {
  provider: "${provider_escaped}",
  baseUrl: "${base_url_escaped}",
  model: "${model_escaped}",
  temperature: ${LLM_UI_TEMPERATURE:-0.7},
  maxTokens: ${LLM_UI_MAX_TOKENS:-512}
};
EOF

envsubst '${NGINX_PORT} ${LLM_UI_PROXY_TARGET} ${LLM_UI_PROXY_AUTH_HEADER}' < /etc/nginx/templates/default.conf.template > /etc/nginx/conf.d/default.conf
exec nginx -g 'daemon off;'
