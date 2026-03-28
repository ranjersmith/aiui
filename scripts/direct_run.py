#!/usr/bin/env python3
"""
Script to run the test for safe_add_ints function fix.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Run the test directly
import test_safe_add_ints

if __name__ == "__main__":
    try:
        test_safe_add_ints.test_safe_add_ints()
        print("All tests passed successfully!")
    except Exception as e:
        print(f"Test failed with error: {e}")
        sys.exit(1)