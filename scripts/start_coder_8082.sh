#!/usr/bin/env bash
# Qwen3-Coder-30B-A3B-Instruct Q5_K_M – coding model
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../.env"
# shellcheck source=../.env
[[ -f "$ENV_FILE" ]] && set -a && source "$ENV_FILE" && set +a

MODEL_PATH="${MODEL_DIR:-/home/ra/models}/${CODER_MODEL:-Qwen2.5-Coder-14B-Instruct-Q8_0.gguf}"
LLAMA_SERVER_BIN="${LLAMA_SERVER_BIN:-/home/ra/qwen3vl-rocm-reference/llama.cpp/build/bin/llama-server}"
LOG_FILE="${LOG_FILE:-/tmp/llama-coder-8082.log}"

if [[ ! -x "$LLAMA_SERVER_BIN" ]]; then
  echo "llama-server not found or not executable: $LLAMA_SERVER_BIN" >&2
  exit 1
fi

if [[ ! -f "$MODEL_PATH" ]]; then
  echo "model file not found: $MODEL_PATH" >&2
  exit 1
fi

# Kill any existing instance on port 8082
EXISTING_PID=$(ss -tlnp 2>/dev/null | awk '/8082/ {match($0,/pid=([0-9]+)/,a); print a[1]}' || true)
if [[ -n "${EXISTING_PID:-}" ]]; then
  echo "Killing existing process on port 8082 (PID $EXISTING_PID)"
  kill "$EXISTING_PID" 2>/dev/null || true
  sleep 1
fi

echo "Starting Qwen3-Coder-30B-A3B on port 8082..."
echo "temp=0.7 top_p=0.8 | ctx=65536"
echo "Log: $LOG_FILE"

nohup "$LLAMA_SERVER_BIN" \
  -m "$MODEL_PATH" \
  --gpu-layers 99 --flash-attn on \
  --ctx-size 65536 \
  --cache-type-k q8_0 --cache-type-v q8_0 \
  --host 0.0.0.0 --port 8082 \
  --threads 6 --threads-batch 6 --threads-http 2 \
  --parallel 1 --cont-batching \
  --batch-size 4096 --ubatch-size 1024 \
  --temp 0.7 --top-p 0.8 --top-k 20 --min-p 0.0 --repeat-penalty 1.05 \
  --n-predict 65536 \
  --metrics --no-webui --jinja \
  >"$LOG_FILE" 2>&1 &

echo "PID: $!"
echo "Waiting for server to be ready..."
for i in $(seq 1 60); do
  if curl -s http://localhost:8082/health >/dev/null 2>&1; then
    echo "Coder model ready on port 8082"
    exit 0
  fi
  sleep 1
done
echo "Warning: server not responding after 60s, check $LOG_FILE"
