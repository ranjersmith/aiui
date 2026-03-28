#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

TEXT_INSTANCE="8081"
VISION_INSTANCE="8082"
TEXT_SERVICE="llama@${TEXT_INSTANCE}.service"
VISION_SERVICE="llama@${VISION_INSTANCE}.service"
TEXT_ENV="/etc/llama/${TEXT_INSTANCE}.env"
TEXT_ENV_BAK="/etc/llama/${TEXT_INSTANCE}.env.bak.$(date +%Y%m%d_%H%M%S)"

TEXT_MODEL="/home/ra/models/Qwen3-Coder-30B-A3B-Instruct-UD-Q6_K_XL.gguf"
VISION_MODEL="/home/ra/models/Qwen3-VL-4B-Instruct-UD-Q6_K_XL.gguf"
VISION_MMPROJ="/home/ra/models/mmproj-Qwen3-VL-4B-F16.gguf"

if [[ ! -f "$TEXT_MODEL" ]]; then
  echo "Missing text/coder model: $TEXT_MODEL" >&2
  exit 1
fi

if [[ ! -f "$VISION_MODEL" ]]; then
  echo "Missing vision model: $VISION_MODEL" >&2
  exit 1
fi

if [[ ! -f "$VISION_MMPROJ" ]]; then
  echo "Missing vision mmproj: $VISION_MMPROJ" >&2
  exit 1
fi

echo "Requesting sudo once..."
sudo -v

echo "Backing up current env: $TEXT_ENV -> $TEXT_ENV_BAK"
sudo cp "$TEXT_ENV" "$TEXT_ENV_BAK"

echo "Writing $TEXT_ENV for Qwen3-Coder on port 8081"
sudo tee "$TEXT_ENV" >/dev/null <<'EOT'
SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
CURL_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
LLAMA_ARGS="-m /home/ra/models/Qwen3-Coder-30B-A3B-Instruct-UD-Q6_K_XL.gguf \
--ctx-size 131072 \
--host 0.0.0.0 --port 8081 \
--threads 5 --threads-batch 5 --threads-http 2 \
--parallel 1 --cont-batching \
--temp 1.0 --top-p 0.95 --top-k 20 --min-p 0.0 \
--reasoning-format none \
--chat-template-kwargs {\"enable_thinking\":false} \
--metrics --no-webui"
EOT

echo "Ensuring vision service config exists (8082)"
"$ROOT_DIR/scripts/setup_qwen3vl_service.sh" >/tmp/setup_qwen3vl_service.log 2>&1 || {
  cat /tmp/setup_qwen3vl_service.log >&2
  exit 1
}

echo "Reloading and restarting llama services"
sudo systemctl daemon-reload
sudo systemctl enable "$TEXT_SERVICE"
sudo systemctl restart "$TEXT_SERVICE"
sudo systemctl enable "$VISION_SERVICE"
sudo systemctl restart "$VISION_SERVICE"

echo "Waiting for ports 8081 + 8082"
for p in 8081 8082; do
  for _ in {1..60}; do
    if curl -fsS "http://127.0.0.1:${p}/v1/models" >/dev/null 2>&1; then
      echo "  port ${p}: ready"
      break
    fi
    sleep 1
  done
done

echo "Restarting AIUI orchestrator stack"
"$ROOT_DIR/scripts/stack.sh" up

echo
echo "Service checks:"
systemctl is-active "$TEXT_SERVICE"
systemctl is-active "$VISION_SERVICE"
curl -sS http://127.0.0.1:8081/v1/models | jq -r '.data[0].id'
curl -sS http://127.0.0.1:8082/v1/models | jq -r '.data[0].id'
curl -fsS http://127.0.0.1:${AIUI_ORCH_UI_PORT:-3311}/health
echo
echo "Done."
