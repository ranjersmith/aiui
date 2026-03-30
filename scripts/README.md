# Scripts Overview

This directory contains operational, test, and diagnostic scripts for the aiui stack.

## Canonical Production Scripts

- `verify_all.sh`: primary verification script for CI, lint, and tests.
- `stack.sh`: Docker compose orchestration for frontend services.
- `build_frontend.mjs`: frontend build pipeline.
- `run_tests.sh`: primary pytest runner.

## Legacy or Experimental Scripts

Prefer canonical equivalents when possible.

- `run_test.sh`: single-test runner, replaced by `run_tests.sh`.
- `test_run.sh`: legacy test runner variant.
- `test_script.sh`: experimental or debug runner.
- `simple_test.sh`: legacy basic test runner.
- `try_run.sh`: experimental runner with unclear purpose.
- `direct_run.py`: direct execution helper, prefer canonical scripts.

## Analysis and Debug Scripts

- `bench_llm.py`: LLM performance benchmarking.
- `eval_ab.py`: A/B evaluation helper.
- `eval_frontdoor.py`: FrontDoor evaluation script.
- `monitor_math_output.mjs`: math output monitoring.
- `debug_budget_analysis.py`: budget analysis.
- `debug_tests.sh`: test debugging helper.
- `demo_type_error.py`: type error demonstration script.
- `detailed_bug_report.py`: bug report utility.
- `coding_chat.py`: coding chat utility.
- `run_budget_test.py`: budget testing helper.

## Environment Setup Scripts

- `venv_check.sh`: check Python virtual environment state.
- `setup_test_env.sh`: initialize the local test environment.
