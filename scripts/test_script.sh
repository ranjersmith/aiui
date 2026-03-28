#!/bin/bash

# Run all tests with coverage
cd /workspace
source .venv/bin/activate
pytest --cov=app --cov-report=term-missing