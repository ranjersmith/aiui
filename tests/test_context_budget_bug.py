#!/usr/bin/env python3
"""
Test script to reproduce the context budgeting bug
"""
from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as app_module


def test_context_budget_bug():
    """Test the apply_context_budget function to identify potential bugs."""

    # Test case from the existing tests
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "a" * 500},
        {"role": "assistant", "content": "b" * 500},
        {"role": "user", "content": "latest"},
    ]

    print("=== Test Case 1 ===")
    print("Original messages:", len(messages))
    print("Messages content lengths:", [len(msg["content"]) for msg in messages])
    
    # Apply budget with a small limit
    trimmed = app_module.apply_context_budget(messages, budget_tokens=20, reserve_tokens=0)

    print("Trimmed messages:", len(trimmed))

    # Check what should be kept
    print("First message role:", messages[0]["role"])
    print("Last message role:", messages[-1]["role"])
    print("Trimmed first role:", trimmed[0]["role"] if trimmed else "None")
    print("Trimmed last role:", trimmed[-1]["role"] if trimmed else "None")
    
    # Check actual content
    if trimmed:
        print("Trimmed content:", [msg["content"][:50] + "..." if msg["content"] else "empty" for msg in trimmed])

    # Test with a more complex case
    print("\n=== Test Case 2 ===")
    complex_messages = [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "user message 1"},
        {"role": "assistant", "content": "assistant message 1"},
        {"role": "user", "content": "user message 2"},
        {"role": "assistant", "content": "assistant message 2"},
        {"role": "user", "content": "latest user message"},
    ]

    print("Complex case - original:", len(complex_messages))
    print("Messages content lengths:", [len(msg["content"]) for msg in complex_messages])
    
    complex_trimmed = app_module.apply_context_budget(complex_messages, budget_tokens=30, reserve_tokens=0)
    print("Complex case - trimmed:", len(complex_trimmed))

    # Print the results
    for i, msg in enumerate(complex_trimmed):
        print(f"  {i}: {msg['role']} - {msg['content'][:30]}...")


def debug_context_budget():
    """More detailed debugging of the context budget function."""
    print("\n=== Detailed Debugging ===")
    
    # Test with messages that have very few tokens each
    simple_messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "user msg"},
        {"role": "assistant", "content": "assistant msg"},
        {"role": "user", "content": "latest"},
    ]
    
    print("Simple case:")
    print("Messages:", len(simple_messages))
    for i, msg in enumerate(simple_messages):
        print(f"  {i}: {msg['role']} - '{msg['content']}' (tokens: {app_module.estimate_content_tokens(msg['content'])})")
    
    # Test with tight budget
    trimmed = app_module.apply_context_budget(simple_messages, budget_tokens=10, reserve_tokens=0)
    print("Trimmed to 10 tokens:", len(trimmed))
    for i, msg in enumerate(trimmed):
        print(f"  {i}: {msg['role']} - '{msg['content']}'")


if __name__ == "__main__":
    test_context_budget_bug()
    debug_context_budget()