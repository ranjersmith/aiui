#!/usr/bin/env python3
"""
Script to run the test for safe_add_ints function fix.
"""
import subprocess
import sys

# Try to run with python3 first, then fallback to python
try:
    result = subprocess.run([sys.executable, "test_safe_add_ints.py"], 
                          capture_output=True, text=True, check=True)
    print("STDOUT:", result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)
    print("Test completed successfully!")
except subprocess.CalledProcessError as e:
    print("Error running test:", e)
    print("STDOUT:", e.stdout)
    print("STDERR:", e.stderr)
    sys.exit(1)