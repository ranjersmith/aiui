#!/bin/bash

# Run tests
cd /workspace

echo "Installing test requirements..."
pip install pytest pytest-cov

echo "Running tests..."
pytest tests/ --maxfail=1 -v --tb=short