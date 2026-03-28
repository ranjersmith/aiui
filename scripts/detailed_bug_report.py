#!/usr/bin/env python3

# Detailed analysis of the apply_context_budget function

import math
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import app as app_module

def estimate_text_tokens(text):
    clean = str(text or "").strip()
    if not clean:
        return 0
    # Lightweight estimate: roughly 1 token per ~4 characters.
    return max(1, math.ceil(len(clean) / 4))

def estimate_content_tokens(content):
    if isinstance(content, str):
        return estimate_text_tokens(content)

    if isinstance(content, list):
        total = 0
        for part in content:
            if not isinstance(part, dict):
                continue
            part_type = str(part.get("type") or "")
            if part_type == "text":
                total += estimate_text_tokens(str(part.get("text") or ""))
            elif part_type == "image_url":
                total += max(1, 768)  # IMAGE_PART_TOKEN_ESTIMATE
        return total

    if isinstance(content, dict):
        maybe_text = content.get("text")
        if isinstance(maybe_text, str):
            return estimate_text_tokens(maybe_text)

    return estimate_text_tokens(str(content or ""))

# Test case that's likely to expose the bug
def analyze_specific_bug_case():
    print("=== Specific Bug Case Analysis ===")
    
    # This case with a small budget might expose edge case behavior
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "a" * 500},
        {"role": "assistant", "content": "b" * 500},
        {"role": "user", "content": "latest"},
    ]

    print("Original messages details:")
    for i, msg in enumerate(messages):
        tokens = estimate_content_tokens(msg['content'])
        print(f"  {i}: {msg['role']} - {len(msg['content'])} chars (~{tokens} tokens)")
        
    print("\nBudget: 20 tokens, reserve: 0 tokens")
    
    # Calculate how it would work
    budget_tokens = 20
    reserve_tokens = 0
    usable_budget = max(128, budget_tokens - max(0, reserve_tokens))
    print(f"usable_budget (due to max(128, ...)): {usable_budget}")
    
    # Test with actual function
    result = app_module.apply_context_budget(messages, budget_tokens=20, reserve_tokens=0)
    print(f"\nActual result from function: {len(result)} messages")
    for i, msg in enumerate(result):
        tokens = estimate_content_tokens(msg['content'])
        print(f"  {i}: {msg['role']} - {len(msg['content'])} chars (~{tokens} tokens) - {msg['content'][:30]}...")
        
    # Check the key constraints that should always hold
    print("\nChecking constraints:")
    print(f"  Should keep system message: {any(msg['role'] == 'system' for msg in result)}")
    print(f"  Should keep latest message: {result[-1]['content'] == 'latest'}")
    print(f"  Should have fewer messages than original: {len(result) < len(messages)}")

# Check how existing tests expect the behavior
def verify_existing_test():
    print("\n=== Verify Existing Test ===")
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "a" * 500},
        {"role": "assistant", "content": "b" * 500},
        {"role": "user", "content": "latest"},
    ]
    
    result = app_module.apply_context_budget(messages, budget_tokens=20, reserve_tokens=0)
    
    print("Expected test result (from existing test):")
    print("  - First message should be system")
    print("  - Last message should be 'latest'")
    print("  - Should be fewer messages than original")
    
    print("\nActual result:")
    print(f"  First message role: {result[0]['role'] if result else 'None'}")
    print(f"  Last message content: {result[-1]['content'] if result else 'None'}")
    print(f"  Message count: {len(result)} (original: {len(messages)})")

if __name__ == "__main__":
    analyze_specific_bug_case()
    verify_existing_test()
