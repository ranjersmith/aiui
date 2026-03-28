#!/bin/bash

# Check if venv exists
if [ -d ".venv" ]; then
    echo "Virtual environment already exists"
else
    echo "Virtual environment needs to be created"
fi

# List installed packages if venv exists
if [ -d ".venv" ]; then
    echo "Listing installed packages:"
    .venv/bin/pip list
fi