#!/usr/bin/env bash
# Script Organization and Classification for aiui/scripts/

# CANONICAL / PRODUCTION SCRIPTS:
# - verify_all.sh       : CANONICAL - Primary verification script for CI/lint/test
# - stack.sh            : CANONICAL - Docker compose orchestration (frontend)
# - build_frontend.mjs  : CANONICAL - Frontend build pipeline
# - run_tests.sh        : CANONICAL - Primary test runner with pytest coverage

# LEGACY / EXPERIMENTAL SCRIPTS (prefer canonical equivalents or verify_all.sh):
# - run_test.sh         : LEGACY - Single test runner, replaced by run_tests.sh
# - test_run.sh         : LEGACY - Test runner variant, prefer run_tests.sh or verify_all.sh
# - test_script.sh      : LEGACY - Experimental/debug script, use verify_all.sh
# - simple_test.sh      : LEGACY - Basic test runner, replaced by verify_all.sh
# - try_run.sh          : LEGACY - Experimental runner, unclear purpose
# - direct_run.py       : LEGACY - Direct execution script, use verify_all.sh or run_tests.sh

# ANALYSIS & DEBUG SCRIPTS:
# - bench_llm.py                : DEBUG - LLM performance benchmarking
# - eval_ab.py                  : DEBUG - A/B evaluation script
# - eval_frontdoor.py           : DEBUG - FrontDoor evaluation
# - monitor_math_output.mjs     : DEBUG - Math output monitoring
# - debug_budget_analysis.py    : DEBUG - Budget analysis
# - debug_tests.sh              : DEBUG - Test debugging
# - demo_type_error.py          : DEBUG - Type error demonstration
# - detailed_bug_report.py      : DEBUG - Bug reporting utility
# - coding_chat.py              : DEBUG - Coding chat utility
# - run_budget_test.py          : DEBUG - Budget testing

# ENVIRONMENT SETUP:
# - venv_check.sh       : UTILITY - Check Python venv state
# - setup_test_env.sh   : UTILITY - Initialize test environment

echo "Script classification complete. See above for organization."
