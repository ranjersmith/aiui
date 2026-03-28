#!/usr/bin/env python3
"""
Test script to verify the context budgeting fix
"""
from __future__ import annotations

import sys
import os
# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as app_module


def test_context_budget_fix():
    """Test that the fix for apply_context_budget works correctly."""

    # Test the specific bug case from existing tests
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "a" * 500},
        {"role": "assistant", "content": "b" * 500},
        {"role": "user", "content": "latest"},
    ]

    # Apply budget with a small limit (this should not cause issues)
    trimmed = app_module.apply_context_budget(messages, budget_tokens=20, reserve_tokens=0)

    print("Original messages:", len(messages))
    print("Trimmed messages:", len(trimmed))

    # Should preserve the latest message
    assert trimmed[-1]["content"] == "latest"
    print("✓ Latest message preserved")

    # Should preserve system message if space allows
    if len(trimmed) > 1:
        assert trimmed[0]["role"] == "system"
        print("✓ System message preserved")

    # Test with very tight budget to make sure it doesn't crash
    try:
        tight_trimmed = app_module.apply_context_budget(messages, budget_tokens=10, reserve_tokens=0)
        print("✓ Tight budget handled without crash")
        print("  Tight budget result length:", len(tight_trimmed))
    except Exception as e:
        print("✗ Tight budget caused error:", e)
        raise

    # Test with zero budget
    try:
        zero_trimmed = app_module.apply_context_budget(messages, budget_tokens=0, reserve_tokens=0)
        print("✓ Zero budget handled without crash")
        print("  Zero budget result length:", len(zero_trimmed))
    except Exception as e:
        print("✗ Zero budget caused error:", e)
        raise

    # Test with very small but positive budget
    small_trimmed = app_module.apply_context_budget(messages, budget_tokens=5, reserve_tokens=0)
    print("✓ Very small budget handled")
    print("  Small budget result length:", len(small_trimmed))

    # Test case for the specific bug that was reported
    # This would have caused a KeyError in the original implementation
    messages_with_empty_content = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": ""},
        {"role": "assistant", "content": "response"},
        {"role": "user", "content": "latest"},
    ]
    
    try:
        result = app_module.apply_context_budget(messages_with_empty_content, budget_tokens=20, reserve_tokens=0)
        print("✓ Empty content handling works correctly")
        print("  Empty content test result length:", len(result))
    except Exception as e:
        print("✗ Empty content caused error:", e)
        raise

    print("\nAll tests passed! The fix successfully addresses the context budgeting issue.")


if __name__ == "__main__":
    test_context_budget_fix()