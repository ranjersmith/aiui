#!/bin/bash
# [LEGACY] Deprecated wrapper — redirects to canonical run_tests.sh or verify_all.sh
# This script is maintained for backward compatibility and will be removed in a future release.

echo "[WARN] test_run.sh is deprecated. Use ./scripts/run_tests.sh or ./scripts/verify_all.sh instead." >&2
exec "$(dirname "$0")/run_tests.sh" "$@"
