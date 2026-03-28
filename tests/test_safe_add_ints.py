#!/usr/bin/env python3
"""
Test script for the safe_add_ints function fix.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the module to test
import app

def test_safe_add_ints():
    print("Testing safe_add_ints function...")

    # Test normal integer inputs
    result = app.safe_add_ints(5, 3)
    print(f"safe_add_ints(5, 3) = {result}")
    assert result == 8

    # Test string inputs that should be convertible to int
    result = app.safe_add_ints("5", "3")
    print(f"safe_add_ints('5', '3') = {result}")
    assert result == 8

    # Test mixed int and string inputs
    result = app.safe_add_ints(5, "3")
    print(f"safe_add_ints(5, '3') = {result}")
    assert result == 8

    # Test None inputs
    result = app.safe_add_ints(None, 5)
    print(f"safe_add_ints(None, 5) = {result}")
    assert result == 5

    # Test string that can't be converted to int
    result = app.safe_add_ints("hello", 5)
    print(f"safe_add_ints('hello', 5) = {result}")
    assert result == 0  # Should return 0 for invalid conversion

    # Test with float values
    result = app.safe_add_ints(5.7, 3.2)
    print(f"safe_add_ints(5.7, 3.2) = {result}")
    assert result == 8  # Should truncate to integer

    # Test that we don't get TypeError with string and int addition
    try:
        # This should not cause TypeError anymore
        result = app.safe_add_ints(5, "3")
        print(f"No TypeError with int and string: {result}")
    except TypeError as e:
        print(f"TypeError still occurs: {e}")
        raise

    print("All tests passed!")

if __name__ == "__main__":
    test_safe_add_ints()