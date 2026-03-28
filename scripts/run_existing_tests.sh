#!/bin/bash

cd /workspace

# Activate venv if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Run just the context budget tests
echo "Running context budget tests..."
python -m pytest tests/test_context_budget.py -v
echo ""
echo "Running context budget edge case tests..."
python -m pytest tests/test_context_budget_edge_cases.py -v