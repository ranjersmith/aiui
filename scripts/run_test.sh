#!/bin/bash
# [LEGACY] Deprecated wrapper — redirects to canonical run_tests.sh
# This script is maintained for backward compatibility and will be removed in a future release.

echo "[WARN] run_test.sh is deprecated. Use ./scripts/run_tests.sh instead." >&2
exec "$(dirname "$0")/run_tests.sh" "$@"
