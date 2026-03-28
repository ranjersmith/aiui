#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

SERVICE_INSTANCE="8081"
ENV_FILE="/etc/llama/${SERVICE_INSTANCE}.env"
SERVICE_UNIT="llama@${SERVICE_INSTANCE}.service"
MODELS_DIR="/home/ra/models"
URL="http://127.0.0.1:8081/v1/chat/completions"
PROMPTS_FILE="$ROOT_DIR/eval/prompts_qwen35b_ab.jsonl"
Q5_MODEL="Qwen3.5-35B-A3B-UD-Q5_K_XL.gguf"
Q6_MODEL="Qwen3.5-35B-A3B-UD-Q6_K_S.gguf"
WARMUP_RUNS=1
MEASURED_RUNS=10
TEMPERATURE="0.0"
WAIT_TIMEOUT=300
RESTORE_ORIGINAL="false"
RUN_ROOT=""
STAMP="$(date -u +%Y%m%d_%H%M%S)"
ENV_BACKUP=""
ORIGINAL_MODEL=""

usage() {
  cat <<'USAGE'
Usage:
  ./scripts/ab_eval_auto.sh [options]

Runs a full automated A/B capture:
1) switch service to Q5 quant
2) capture prompts (warmup + measured runs)
3) switch service to Q6 quant
4) capture prompts
5) build blind pack

Options:
  --service-instance NAME   systemd instance name (default: 8081)
  --env-file PATH           llama env file (default: /etc/llama/<instance>.env)
  --models-dir PATH         models directory (default: /home/ra/models)
  --url URL                 chat completions endpoint (default: http://127.0.0.1:8081/v1/chat/completions)
  --prompts-file PATH       prompt JSONL file (default: ./eval/prompts_qwen35b_ab.jsonl)
  --q5-model FILE           Q5 model filename
  --q6-model FILE           Q6 model filename
  --warmup-runs N           warmup runs per prompt (default: 1)
  --measured-runs N         measured runs per prompt (default: 10)
  --temperature FLOAT       sampling temperature (default: 0.0)
  --wait-timeout SEC        model load wait timeout seconds (default: 300)
  --output-root PATH        output root (default: ./eval_runs/ab_auto_<timestamp>)
  --restore-original        restore original model after completion
  -h, --help                show this message

Example:
  ./scripts/ab_eval_auto.sh --measured-runs 8
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --service-instance)
      SERVICE_INSTANCE="${2:?missing value for --service-instance}"
      SERVICE_UNIT="llama@${SERVICE_INSTANCE}.service"
      ENV_FILE="/etc/llama/${SERVICE_INSTANCE}.env"
      shift 2
      ;;
    --env-file)
      ENV_FILE="${2:?missing value for --env-file}"
      shift 2
      ;;
    --models-dir)
      MODELS_DIR="${2:?missing value for --models-dir}"
      shift 2
      ;;
    --url)
      URL="${2:?missing value for --url}"
      shift 2
      ;;
    --prompts-file)
      PROMPTS_FILE="${2:?missing value for --prompts-file}"
      shift 2
      ;;
    --q5-model)
      Q5_MODEL="${2:?missing value for --q5-model}"
      shift 2
      ;;
    --q6-model)
      Q6_MODEL="${2:?missing value for --q6-model}"
      shift 2
      ;;
    --warmup-runs)
      WARMUP_RUNS="${2:?missing value for --warmup-runs}"
      shift 2
      ;;
    --measured-runs)
      MEASURED_RUNS="${2:?missing value for --measured-runs}"
      shift 2
      ;;
    --temperature)
      TEMPERATURE="${2:?missing value for --temperature}"
      shift 2
      ;;
    --wait-timeout)
      WAIT_TIMEOUT="${2:?missing value for --wait-timeout}"
      shift 2
      ;;
    --output-root)
      RUN_ROOT="${2:?missing value for --output-root}"
      shift 2
      ;;
    --restore-original)
      RESTORE_ORIGINAL="true"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ -z "$RUN_ROOT" ]]; then
  RUN_ROOT="$ROOT_DIR/eval_runs/ab_auto_${STAMP}"
fi

PROMPTS_FILE="$(realpath "$PROMPTS_FILE")"
RUN_ROOT="$(realpath -m "$RUN_ROOT")"
MODELS_DIR="$(realpath "$MODELS_DIR")"

CHAT_URL="${URL%/}"
if [[ "$CHAT_URL" == */v1/chat/completions ]]; then
  MODELS_URL="${CHAT_URL%/chat/completions}/models"
else
  echo "URL must end with /v1/chat/completions: $URL" >&2
  exit 1
fi

sanitize_name() {
  local raw="$1"
  local out
  out="$(echo "$raw" | sed -E 's/[^a-zA-Z0-9._-]+/_/g; s/^[._-]+//; s/[._-]+$//')"
  if [[ -z "$out" ]]; then
    out="capture"
  fi
  printf '%s\n' "$out"
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required command: $1" >&2
    exit 1
  }
}

current_configured_model() {
  local model_path
  model_path="$(grep -oE -- '-m [^[:space:]]+' "$ENV_FILE" | head -n1 | awk '{print $2}')"
  if [[ -z "$model_path" ]]; then
    return 1
  fi
  basename "$model_path"
}

wait_for_model() {
  local expected_model="$1"
  local start_ts
  start_ts="$(date +%s)"
  while true; do
    local now_ts
    now_ts="$(date +%s)"
    if (( now_ts - start_ts > WAIT_TIMEOUT )); then
      echo "Timed out waiting for model $expected_model at $MODELS_URL" >&2
      return 1
    fi
    local payload
    payload="$(curl -fsS "$MODELS_URL" 2>/dev/null || true)"
    if [[ -n "$payload" ]] && echo "$payload" | rg -Fq "\"id\":\"$expected_model\""; then
      return 0
    fi
    sleep 2
  done
}

switch_model() {
  local model_file="$1"
  local model_path="$MODELS_DIR/$model_file"
  [[ -f "$model_path" ]] || {
    echo "Model file not found: $model_path" >&2
    exit 1
  }

  echo
  echo "==> Switching to $model_file"
  sudo sed -E -i "s#-m [^[:space:]]+#-m ${model_path}#g" "$ENV_FILE"
  sudo systemctl restart "$SERVICE_UNIT"
  wait_for_model "$model_file"
  echo "    Ready: $model_file"
}

validate_capture_model_match() {
  local capture_file="$1"
  local expected_model="$2"
  "$PYTHON_BIN" - "$capture_file" "$expected_model" <<'PY'
import json
import sys
from pathlib import Path

capture_path = Path(sys.argv[1])
expected = sys.argv[2]
rows = [json.loads(line) for line in capture_path.read_text(encoding="utf-8").splitlines() if line.strip()]
reported = sorted({str(row.get("reported_model") or "").strip() for row in rows})
if reported != [expected]:
    print(f"Model mismatch in {capture_path}", file=sys.stderr)
    print(f"Expected reported_model: {expected}", file=sys.stderr)
    print(f"Actual reported_model(s): {reported}", file=sys.stderr)
    sys.exit(2)
print(f"    Model validation OK for {capture_path.name}: {expected}", file=sys.stderr)
PY
}

run_capture() {
  local model_file="$1"
  local out_dir="$2"
  mkdir -p "$out_dir"

  "$PYTHON_BIN" "$ROOT_DIR/scripts/eval_ab.py" capture \
    --url "$URL" \
    --model "$model_file" \
    --prompts-file "$PROMPTS_FILE" \
    --warmup-runs "$WARMUP_RUNS" \
    --measured-runs "$MEASURED_RUNS" \
    --temperature "$TEMPERATURE" \
    --output-dir "$out_dir" >&2

  local capture_name capture_file
  capture_name="$(sanitize_name "$model_file")"
  capture_file="$out_dir/capture_${capture_name}.jsonl"
  [[ -f "$capture_file" ]] || {
    echo "Expected capture file missing: $capture_file" >&2
    exit 1
  }
  validate_capture_model_match "$capture_file" "$model_file" >&2
  printf '%s\n' "$capture_file"
}

restore_original_model() {
  if [[ "$RESTORE_ORIGINAL" != "true" ]]; then
    return 0
  fi
  if [[ -z "$ORIGINAL_MODEL" ]]; then
    return 0
  fi
  if [[ ! -f "$MODELS_DIR/$ORIGINAL_MODEL" ]]; then
    echo "Skipping restore: original model file missing ($MODELS_DIR/$ORIGINAL_MODEL)" >&2
    return 0
  fi

  echo
  echo "==> Restoring original model: $ORIGINAL_MODEL"
  sudo sed -E -i "s#-m [^[:space:]]+#-m ${MODELS_DIR}/${ORIGINAL_MODEL}#g" "$ENV_FILE"
  sudo systemctl restart "$SERVICE_UNIT"
  wait_for_model "$ORIGINAL_MODEL" || true
}

trap restore_original_model EXIT

require_cmd "$PYTHON_BIN"
require_cmd curl
require_cmd rg
require_cmd sudo
require_cmd systemctl

[[ -f "$ENV_FILE" ]] || { echo "Env file not found: $ENV_FILE" >&2; exit 1; }
[[ -f "$PROMPTS_FILE" ]] || { echo "Prompts file not found: $PROMPTS_FILE" >&2; exit 1; }
[[ -f "$ROOT_DIR/scripts/eval_ab.py" ]] || { echo "Missing script: $ROOT_DIR/scripts/eval_ab.py" >&2; exit 1; }

ORIGINAL_MODEL="$(current_configured_model || true)"
ENV_BACKUP="${ENV_FILE}.bak.ab_auto.${STAMP}"

echo "AB auto run root:  $RUN_ROOT"
echo "Service unit:      $SERVICE_UNIT"
echo "Env file:          $ENV_FILE"
echo "Prompts file:      $PROMPTS_FILE"
echo "Chat URL:          $URL"
echo "Models URL:        $MODELS_URL"
echo "Q5 model:          $Q5_MODEL"
echo "Q6 model:          $Q6_MODEL"
echo "Warmup runs:       $WARMUP_RUNS"
echo "Measured runs:     $MEASURED_RUNS"
echo "Temperature:       $TEMPERATURE"
if [[ -n "$ORIGINAL_MODEL" ]]; then
  echo "Original model:    $ORIGINAL_MODEL"
fi
echo

mkdir -p "$RUN_ROOT"

echo "Requesting sudo once (for env edit + service restart)..."
sudo -v

sudo cp "$ENV_FILE" "$ENV_BACKUP"
echo "Backed up env file: $ENV_BACKUP"

Q5_DIR="$RUN_ROOT/q5"
Q6_DIR="$RUN_ROOT/q6"
PACK_DIR="$RUN_ROOT/pack"

switch_model "$Q5_MODEL"
Q5_CAPTURE_FILE="$(run_capture "$Q5_MODEL" "$Q5_DIR")"

switch_model "$Q6_MODEL"
Q6_CAPTURE_FILE="$(run_capture "$Q6_MODEL" "$Q6_DIR")"

mkdir -p "$PACK_DIR"
"$PYTHON_BIN" "$ROOT_DIR/scripts/eval_ab.py" pack \
  --capture-a "$Q5_CAPTURE_FILE" \
  --capture-b "$Q6_CAPTURE_FILE" \
  --output-dir "$PACK_DIR"

echo
echo "Done."
echo "Q5 capture:   $Q5_CAPTURE_FILE"
echo "Q6 capture:   $Q6_CAPTURE_FILE"
echo "Blind pack:   $PACK_DIR/blind_packet.md"
echo "Blind key:    $PACK_DIR/blind_key.csv"
echo "Score sheet:  $PACK_DIR/score_by_output.csv"
echo "Pairwise:     $PACK_DIR/score_pairwise.csv"
