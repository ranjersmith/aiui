#!/usr/bin/env bash
set -euo pipefail

INSTANCE="8082"
ENV_FILE="/etc/llama/${INSTANCE}.env"
SERVICE="llama@${INSTANCE}.service"
MODEL="/home/ra/models/Qwen3-VL-4B-Instruct-UD-Q6_K_XL.gguf"
MMPROJ="/home/ra/models/mmproj-Qwen3-VL-4B-F16.gguf"
PORT="8082"

if [[ ! -f "$MODEL" ]]; then
  echo "Missing model: $MODEL" >&2
  exit 1
fi
if [[ ! -f "$MMPROJ" ]]; then
  echo "Missing mmproj: $MMPROJ" >&2
  exit 1
fi

# Optional: clear a non-systemd process already bound to 8082 to avoid restart conflicts.
if ss -ltnp "( sport = :${PORT} )" | tail -n +2 | grep -q .; then
  echo "Port ${PORT} is currently in use."
  ss -ltnp "( sport = :${PORT} )" || true
  echo "Attempting to stop existing ${SERVICE} first..."
fi

sudo mkdir -p /etc/llama
sudo tee "$ENV_FILE" >/dev/null <<EOT
SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
CURL_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
LLAMA_ARGS="-m ${MODEL} \\
--mmproj ${MMPROJ} \\
--ctx-size 8192 \\
--image-min-tokens 1024 \\
--host 0.0.0.0 --port ${PORT} \\
--threads 4 --threads-batch 4 --threads-http 2 \\
--parallel 1 --cont-batching \\
--temp 0.1 --top-p 0.9 --top-k 20 --min-p 0.0 \\
--reasoning-format none \\
--chat-template-kwargs {\\"enable_thinking\\":false} \\
--metrics --webui"
EOT

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE"
sudo systemctl restart "$SERVICE"

echo
echo "Service status:"
sudo systemctl status "$SERVICE" --no-pager -n 30

echo
echo "Health check:"
curl -sS "http://127.0.0.1:${PORT}/health" || true

echo
echo "Root response headers (should be HTML for new Web UI):"
curl -sS -I "http://127.0.0.1:${PORT}/" | sed -n '1,12p' || true

echo
echo "Recent projector/model lines:"
sudo journalctl -u "$SERVICE" -n 120 --no-pager -l | rg -n 'loaded model|loaded multimodal model|projector|server is listening' || true

echo
echo "Done. Open: http://192.168.50.6:${PORT}/"
