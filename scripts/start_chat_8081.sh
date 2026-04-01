#!/usr/bin/env bash
# gemma-3-4b-it Q6_K_XL – fast chat model
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../.env"
# shellcheck source=../.env
[[ -f "$ENV_FILE" ]] && set -a && source "$ENV_FILE" && set +a

MODEL_PATH="${MODEL_DIR:-/home/ra/models}/${CHAT_MODEL:-Qwen3-1.7B-Q8_0.gguf}"
MMPROJ_PATH="${MODEL_DIR:-/home/ra/models}/${CHAT_MMPROJ:-}"
LLAMA_SERVER_BIN="${LLAMA_SERVER_BIN:-/home/ra/qwen3vl-rocm-reference/llama.cpp/build/bin/llama-server}"
LOG_FILE="${LOG_FILE:-/tmp/llama-chat-8081.log}"

if [[ ! -x "$LLAMA_SERVER_BIN" ]]; then
  echo "llama-server not found or not executable: $LLAMA_SERVER_BIN" >&2
  exit 1
fi

if [[ ! -f "$MODEL_PATH" ]]; then
  echo "model file not found: $MODEL_PATH" >&2
  exit 1
fi

# Kill any existing instance on port 8081
EXISTING_PID=$(ss -tlnp 2>/dev/null | awk '/8081/ {match($0,/pid=([0-9]+)/,a); print a[1]}' || true)
if [[ -n "${EXISTING_PID:-}" ]]; then
  echo "Killing existing process on port 8081 (PID $EXISTING_PID)"
  kill "$EXISTING_PID" 2>/dev/null || true
  sleep 1
fi

echo "Starting gemma-3-4b-it chat model on port 8081..."
echo "Non-thinking mode | temp=0.7 top_p=0.8 | ctx=32768"
echo "Log: $LOG_FILE"

# Build mmproj argument if configured
MMPROJ_ARGS=()
if [[ -n "${CHAT_MMPROJ:-}" && -f "$MMPROJ_PATH" ]]; then
  MMPROJ_ARGS=(--mmproj "$MMPROJ_PATH")
  echo "Vision enabled: $CHAT_MMPROJ"
fi

nohup "$LLAMA_SERVER_BIN" \
  -m "$MODEL_PATH" \
  "${MMPROJ_ARGS[@]:-}" \
  --gpu-layers 99 --flash-attn on \
  --ctx-size 32768 \
  --cache-type-k q8_0 --cache-type-v q8_0 \
  --host 0.0.0.0 --port 8081 \
  --threads 6 --threads-batch 6 --threads-http 2 \
  --parallel 2 --cont-batching \
  --batch-size 2048 --ubatch-size 512 \
  --temp 0.7 --top-p 0.8 --top-k 20 --min-p 0.0 \
  --n-predict 32768 \
  --reasoning-format none \
  --metrics --no-webui \
  >"$LOG_FILE" 2>&1 &

echo "PID: $!"
echo "Waiting for server to be ready..."
for i in $(seq 1 30); do
  if curl -s http://localhost:8081/health >/dev/null 2>&1; then
    echo "Chat model ready on port 8081"
    exit 0
  fi
  sleep 1
done
echo "Warning: server not responding after 30s, check $LOG_FILE"
