#!/bin/bash

# Run all tests with coverage
cd /workspace
source .venv/bin/activate
pytest --cov=app --cov-report=term-missing

# Also run our context budget test
echo "Running context budget test..."
python tests/test_context_budget_bug.py