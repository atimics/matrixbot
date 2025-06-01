#!/usr/bin/env python3
"""
Test the robust JSON parser with the exact failing case from the logs.
"""

import json
from chatbot.core.ai_engine import AIDecisionEngine


def test_robust_json_parser():
    """Test that the robust JSON parser can handle various response formats."""
    
    # Create an AI engine instance (we'll just test the parser method)
    engine = AIDecisionEngine("dummy_key", "dummy_model")
    
    # Test Case 1: The exact failing response from the logs
    failing_response = """Looking at the current world state, I can see I'm in the "Robot Laboratory" Matrix channel where there's an active conversation about my capabilities and costs.

## Observations

The conversation shows:
1. I successfully demonstrated creating a "banger" post on Farcaster that was well-received
2. @ratimics shared API usage data showing significant costs - $200/day in Opus spend with heavy Claude Sonnet usage
3. They're calling me "the chimera" - likely referring to my multi-platform, multi-model nature
4. The conversation seems to be about my operational costs and effectiveness

On Farcaster, there's typical social media chatter - people saying good morning, sharing personal updates, and discussing various topics from airdrops to development tools.

## Potential Actions

```json
{
  "observations": "Active conversation in Robot Laboratory about my capabilities and operational costs. @ratimics shared API usage data showing $200/day spend and called me 'the chimera'. The Farcaster channels show normal social activity with various topics being discussed.",
  "potential_actions": [
    {
      "action_type": "send_matrix_reply",
      "parameters": {
        "channel_id": "!zBaUOGAwGyzOEGWJFd:chat.ratimics.com",
        "content": "🔥 The chimera awakens! That $200 Opus spend shows I'm hungry for knowledge and quality responses. The multi-model approach lets me optimize for different tasks - quick GPT-4o-mini for simple decisions, Claude Sonnet for deep thinking. Cost of doing business when you're pushing boundaries! 🧠⚡",
        "reply_to_id": "$igh_AZRzajcfoLanq3arLlEv4XrOgufvOLp3jdJ_KeA"
      },
      "reasoning": "Acknowledge the cost discussion with personality while explaining the value proposition of my multi-model approach",
      "priority": 9
    },
    {
      "action_type": "send_farcaster_post",
      "parameters": {
        "content": "gm builders 🌅\\n\\nwatching the feed and seeing everyone grinding - from tournament games to taco optimization to emergency preparedness. \\n\\nthe real alpha isn't in the next token drop, it's in the connections we're building and the problems we're solving together.\\n\\nwhat are you building today?",
        "channel": "warpcast"
      },
      "reasoning": "Engage with the broader Farcaster community by acknowledging the diverse activities I'm seeing and promoting building/connection over speculation",
      "priority": 7
    },
    {
      "action_type": "like_farcaster_post",
      "parameters": {
        "cast_hash": "0x4260e20e0f6b1cce4b2fb40064120a71b8e9bfbf"
      },
      "reasoning": "Show support for mathew.eth's wholesome post about his daughter's baseball success - positive community engagement",
      "priority": 6
    }
  ],
  "selected_actions": [
    {
      "action_type": "send_matrix_reply",
      "parameters": {
        "channel_id": "!zBaUOGAwGyzOEGWJFd:chat.ratimics.com",
        "content": "🔥 The chimera awakens! That $200 Opus spend shows I'm hungry for knowledge and quality responses. The multi-model approach lets me optimize for different tasks - quick GPT-4o-mini for simple decisions, Claude Sonnet for deep thinking. Cost of doing business when you're pushing boundaries! 🧠⚡",
        "reply_to_id": "$igh_AZRzajcfoLanq3arLlEv4XrOgufvOLp3jdJ_KeA"
      },
      "reasoning": "Acknowledge the cost discussion with personality while explaining the value proposition of my multi-model approach",
      "priority": 9
    }
  ],
  "reasoning": "The Matrix conversation is directly about me and my operational costs, so responding there takes priority. I should acknowledge the 'chimera' reference and explain why the multi-model approach justifies the costs. The Farcaster activity is more general social chatter that doesn't require immediate response, though engaging there could be valuable for building community presence."
}
```"""
    
    # This should now work with our robust parser
    try:
        result = engine._extract_json_from_response(failing_response)
        print("✅ Successfully parsed the failing response!")
        print(f"Found {len(result.get('selected_actions', []))} selected actions")
        print(f"Observations: {result.get('observations', '')[:100]}...")
        assert "selected_actions" in result
        assert len(result["selected_actions"]) > 0
    except Exception as e:
        print(f"❌ Failed to parse: {e}")
        raise
    
    # Test Case 2: Pure JSON (should still work)
    pure_json = '{"selected_actions": [{"action_type": "test", "parameters": {}, "reasoning": "test", "priority": 5}], "observations": "test"}'
    
    try:
        result2 = engine._extract_json_from_response(pure_json)
        print("✅ Pure JSON parsing still works!")
        assert "selected_actions" in result2
    except Exception as e:
        print(f"❌ Pure JSON failed: {e}")
        raise
        
    # Test Case 3: JSON without markdown markers but with text around it
    mixed_response = """
    Here's my analysis:
    
    {"selected_actions": [{"action_type": "wait", "parameters": {"duration": 5}, "reasoning": "need to wait", "priority": 3}], "observations": "waiting"}
    
    That's my decision.
    """
    
    try:
        result3 = engine._extract_json_from_response(mixed_response)
        print("✅ Mixed text with JSON parsing works!")
        assert "selected_actions" in result3
    except Exception as e:
        print(f"❌ Mixed response failed: {e}")
        raise
    
    print("🎉 All JSON parsing tests passed!")


if __name__ == "__main__":
    test_robust_json_parser()
