#!/bin/bash

echo "Testing the aiui project..."

# Set up environment
echo "Setting up virtual environment..."
python3 -m venv .venv
source .venv/bin/activate

echo "Installing dependencies..."
pip install -r requirements.txt -r requirements-dev.txt

echo "Running basic test checks..."

# Run just one test file to verify the setup works
echo "Running health and root tests..."
python -m pytest tests/test_health_and_root.py -v

echo "Running context budget tests..."
python -m pytest tests/test_context_budget.py -v

echo "Running non-stream chat tests..."
python -m pytest tests/test_chat_non_stream.py -v

echo "Running stream chat tests..."
python -m pytest tests/test_chat_stream.py -v

echo "All tests completed."