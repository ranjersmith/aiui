# Scripts Overview

This directory contains operational, evaluation, and diagnostic scripts for the aiui stack.

## Canonical Production Scripts

- `verify_all.sh`: primary verification script for CI, lint, and tests.
- `stack.sh`: Docker compose orchestration for frontend services.
- `build_frontend.mjs`: frontend build pipeline.
- `run_tests.sh`: primary pytest runner.

## Evaluation & Analysis Scripts

- `bench_llm.py`: LLM performance benchmarking.
- `eval_ab.py`: A/B evaluation helper.
- `eval_frontdoor.py`: FrontDoor evaluation script.
- `ab_eval_auto.sh`: automated A/B evaluation runner.
- `monitor_math_output.mjs`: math output monitoring.
- `coding_chat.py`: coding chat utility.

## Environment Setup Scripts

- `setup_test_env.sh`: initialize the local test environment.
