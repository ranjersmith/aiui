#!/bin/bash
# [LEGACY] Legacy test runner variant
# ⚠️  Deprecated. Use verify_all.sh or run_tests.sh instead.

# Run tests
cd /workspace

echo "Installing test requirements..."
pip install pytest pytest-cov

echo "Running tests..."
pytest tests/ --maxfail=1 -v --tb=short