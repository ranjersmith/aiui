#!/usr/bin/env bash
set -euo pipefail

MODEL_PATH="${MODEL_PATH:-/home/ra/models/Qwen3.5-9B-BF16.gguf}"
LLAMA_SERVER_BIN="${LLAMA_SERVER_BIN:-/home/ra/qwen3vl-rocm-reference/llama.cpp/build/bin/llama-server}"
LOG_FILE="${LOG_FILE:-/tmp/llama-8081.log}"

if [[ ! -x "$LLAMA_SERVER_BIN" ]]; then
  echo "llama-server not found or not executable: $LLAMA_SERVER_BIN" >&2
  exit 1
fi

if [[ ! -f "$MODEL_PATH" ]]; then
  echo "model file not found: $MODEL_PATH" >&2
  exit 1
fi

# Keep a single instance for this model/port combo.
EXISTING_PID=$(ps -ef | awk '/llama-server/ && /Qwen3.5-9B-BF16.gguf/ && /--port 8081/ {print $2; exit}')
if [[ -n "${EXISTING_PID:-}" ]]; then
  kill "$EXISTING_PID"
  sleep 1
fi

nohup "$LLAMA_SERVER_BIN" \
  -m "$MODEL_PATH" \
  --gpu-layers 99 --flash-attn on \
  --ctx-size 131072 \
  --cache-type-k q8_0 --cache-type-v q8_0 \
  --host 0.0.0.0 --port 8081 \
  --threads 6 --threads-batch 6 --threads-http 2 \
  --parallel 1 --cont-batching \
  --batch-size 4096 --ubatch-size 1024 \
  --temp 0.7 --top-p 0.8 --top-k 20 --min-p 0.0 --presence-penalty 1.5 --repeat-penalty 1.0 \
  --n-predict 32768 \
  --reasoning off --reasoning-format none \
  --tools all \
  --metrics --no-webui \
  >"$LOG_FILE" 2>&1 &

echo "Started llama-server on 8081 with 128K context (PID $!)."
echo "Log: $LOG_FILE"
