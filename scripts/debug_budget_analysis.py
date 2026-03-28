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

# Test case from the bug report
def analyze_bug_case():
    print("=== Bug Case Analysis ===")
    
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "a" * 500},
        {"role": "assistant", "content": "b" * 500},
        {"role": "user", "content": "latest"},
    ]

    print("Original messages:", len(messages))
    for i, msg in enumerate(messages):
        print(f"  {i}: {msg['role']} - {len(msg['content'])} chars")
        
    # Show token estimates
    for i, msg in enumerate(messages):
        tokens = estimate_content_tokens(msg['content'])
        print(f"  {i} tokens: {tokens}")
    
    # Simulate the budgeting process manually
    budget_tokens = 20
    reserve_tokens = 0
    
    usable_budget = max(128, budget_tokens - max(0, reserve_tokens))
    print("\nBudget parameters:")
    print(f"  budget_tokens: {budget_tokens}")
    print(f"  reserve_tokens: {reserve_tokens}")
    print(f"  usable_budget: {usable_budget}")
    
    selected_indices = set()
    
    # Step 1: Always keep the latest message (current user input).
    last_index = len(messages) - 1
    last_message_tokens = estimate_content_tokens(messages[last_index].get("content", ""))
    selected_indices.add(last_index)
    used_tokens = last_message_tokens
    
    print("\nStep 1 - Keep latest message:")
    print(f"  index {last_index} ({messages[last_index]['role']}): {last_message_tokens} tokens")
    print(f"  Total used tokens: {used_tokens}")
    
    # Step 2: Keep the latest non-system history first.
    print("\nStep 2 - Keep latest non-system messages:")
    for idx in range(last_index - 1, -1, -1):
        role = messages[idx].get("role")
        if role == "system":
            print(f"  Skip system message at index {idx}")
            continue
            
        token_cost = estimate_content_tokens(messages[idx].get("content", ""))
        print(f"  Index {idx} ({role}): {token_cost} tokens")
        print(f"    Would use {used_tokens} + {token_cost} = {used_tokens + token_cost} tokens")
        
        if token_cost <= 0:
            print("    Skip - token_cost <= 0")
            continue
            
        if used_tokens + token_cost > usable_budget:
            print(f"    Skip - Would exceed budget of {usable_budget}")
            continue
            
        selected_indices.add(idx)
        used_tokens += token_cost
        print(f"    Added - New used tokens: {used_tokens}")
    
    # Step 3: Keep the first system prompt if present, even if budget is tight.
    print("\nStep 3 - System prompt handling:")
    system_indices = [idx for idx, msg in enumerate(messages) if msg.get("role") == "system"]
    print(f"  System indices found: {system_indices}")
    
    if system_indices:
        first_system = system_indices[0]
        system_token_cost = estimate_content_tokens(messages[first_system].get("content", ""))
        print(f"  First system prompt at index {first_system}: {system_token_cost} tokens")
        print(f"  Would use {used_tokens} + {system_token_cost} = {used_tokens + system_token_cost} tokens")
        
        if used_tokens + system_token_cost <= usable_budget:
            selected_indices.add(first_system)
            print(f"  Added system prompt - New used tokens: {used_tokens + system_token_cost}")
        else:
            print("  Skipped system prompt - Would exceed budget")
    
    print(f"\nFinal selected indices: {sorted(selected_indices)}")
    
    # Apply the function
    result = app_module.apply_context_budget(messages, budget_tokens=20, reserve_tokens=0)
    print(f"Actual function result length: {len(result)}")
    for i, msg in enumerate(result):
        print(f"  {i}: {msg['role']} - {msg['content'][:20]}...")
        
    return result

# Test with another scenario that shows more clear bugs
def analyze_edge_case():
    print("\n=== Edge Case Analysis ===")
    
    # Very tight budget case
    messages = [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "user msg"},
        {"role": "assistant", "content": "assistant msg"},
        {"role": "user", "content": "latest"},
    ]
    
    print("Messages:", len(messages))
    for i, msg in enumerate(messages):
        tokens = estimate_content_tokens(msg['content'])
        print(f"  {i}: {msg['role']} - {len(msg['content'])} chars (~{tokens} tokens)")
        
    # Test with tight budget
    result = app_module.apply_context_budget(messages, budget_tokens=10, reserve_tokens=0)
    print(f"\nResult with tight budget (10 tokens): {len(result)} messages")
    for i, msg in enumerate(result):
        print(f"  {i}: {msg['role']} - {msg['content'][:20]}...")

if __name__ == "__main__":
    analyze_bug_case()
    analyze_edge_case()
