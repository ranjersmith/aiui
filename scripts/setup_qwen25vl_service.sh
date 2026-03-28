#!/usr/bin/env bash
set -euo pipefail

echo "setup_qwen25vl_service.sh is deprecated; using Qwen3-VL 4B for 8082 instead." >&2
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/setup_qwen3vl_service.sh"
