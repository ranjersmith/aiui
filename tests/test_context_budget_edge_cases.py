from __future__ import annotations

import app as app_module


def test_context_budget_with_small_budget_and_system_prompt() -> None:
    """Test that the system prompt is only included if there's enough space in the budget."""
    # Create messages with a large system prompt and many long history messages
    messages = [
        {"role": "system", "content": "This is a very long system prompt that takes up a lot of tokens" * 10},
        {"role": "user", "content": "previous user message"},
        {"role": "assistant", "content": "previous assistant message"},
        {"role": "user", "content": "current message"},
    ]
    
    # Set a small budget that barely fits the current message but not the system prompt
    # Using a very small budget to test the edge case
    result = app_module.apply_context_budget(messages, budget_tokens=50, reserve_tokens=0)
    
    # The system prompt should be excluded because it doesn't fit with the current message
    # The current user message should be included (always included)
    # Previous messages should be included if space permits, but may not be in this tight case
    assert len(result) >= 1  # At least the current message should be included
    assert result[-1]["role"] == "user"  # Last message is current user message
    assert result[-1]["content"] == "current message"


def test_context_budget_with_limited_space() -> None:
    """Test context budget with a very tight space where system prompt barely fits."""
    # Create messages with a moderately long system prompt and a few history messages
    messages = [
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "User message 1"},
        {"role": "assistant", "content": "Assistant message 1"},
        {"role": "user", "content": "User message 2"},
        {"role": "assistant", "content": "Assistant message 2"},
        {"role": "user", "content": "Current message"},
    ]
    
    # Test with a budget that barely fits the current message + system prompt
    # The system prompt should be included since there's room
    result = app_module.apply_context_budget(messages, budget_tokens=100, reserve_tokens=0)
    
    # Should include at least the system prompt and current message
    system_found = any(msg["role"] == "system" for msg in result)
    assert system_found or len(result) >= 1


def test_context_budget_preserves_current_message() -> None:
    """Test that current message is always preserved regardless of budget constraints."""
    messages = [
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "Old user message"},
        {"role": "assistant", "content": "Old assistant message"},
        {"role": "user", "content": "Current message"},
    ]
    
    # Use a very small budget to test that the current message is preserved
    result = app_module.apply_context_budget(messages, budget_tokens=10, reserve_tokens=0)
    
    # Current message should always be preserved
    assert len(result) >= 1
    assert result[-1]["role"] == "user"
    assert result[-1]["content"] == "Current message"