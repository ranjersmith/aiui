#!/usr/bin/env bash
# [EXPERIMENTAL] Model/stack switcher for Qwen coder models
# ⚠️  Development utility for switching between LLM configurations. Not for production.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

TEXT_INSTANCE="8081"
VISION_INSTANCE="8082"
TEXT_SERVICE="llama@${TEXT_INSTANCE}.service"
VISION_SERVICE="llama@${VISION_INSTANCE}.service"
TEXT_ENV="/etc/llama/${TEXT_INSTANCE}.env"
TEXT_ENV_BAK="/etc/llama/${TEXT_INSTANCE}.env.bak.$(date +%Y%m%d_%H%M%S)"

TEXT_MODEL="/home/ra/models/Qwen3.5-9B-BF16.gguf"
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

echo "Writing $TEXT_ENV for Qwen3.5-9B-BF16 on port 8081"
sudo tee "$TEXT_ENV" >/dev/null <<'EOT'
SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
CURL_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
LLAMA_ARGS="-m /home/ra/models/Qwen3.5-9B-BF16.gguf \
--gpu-layers 99 \
--flash-attn on \
--ctx-size 32768 \
--cache-type-k q8_0 --cache-type-v q8_0 \
--host 0.0.0.0 --port 8081 \
--threads 6 --threads-batch 6 --threads-http 2 \
--parallel 1 --cont-batching \
--batch-size 4096 --ubatch-size 1024 \
--temp 0.7 --top-p 0.8 --top-k 20 --min-p 0.0 --presence-penalty 1.5 --repeat-penalty 1.0 \
--n-predict 32768 \
--reasoning off \
--reasoning-format none \
--tools all \
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
