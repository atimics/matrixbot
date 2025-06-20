#!/usr/bin/env python3
"""
Test cases for robust JSON parsing in AI engine.
"""

import pytest
from chatbot.core.ai_engine import AIEngine


class TestRobustJSONParsing:
    """Test the robust JSON parsing capabilities."""

    def setup_method(self):
        """Set up test fixtures."""
        self.engine = AIEngine("dummy_key", "dummy_model")

    def test_pure_json_parsing(self):
        """Test parsing pure JSON response."""
        pure_json = '{"selected_actions": [{"action_type": "test", "parameters": {}, "reasoning": "test", "priority": 5}], "observations": "test"}'
        
        result = self.engine._extract_json_from_response(pure_json)
        assert "selected_actions" in result
        assert len(result["selected_actions"]) == 1
        assert result["observations"] == "test"

    def test_markdown_wrapped_json(self):
        """Test parsing JSON wrapped in markdown code blocks."""
        markdown_json = '''```json
{
  "selected_actions": [
    {
      "action_type": "send_matrix_reply",
      "parameters": {
        "channel_id": "test",
        "content": "test message"
      },
      "reasoning": "test reason",
      "priority": 8
    }
  ],
  "observations": "test observation"
}
```'''
        
        result = self.engine._extract_json_from_response(markdown_json)
        assert "selected_actions" in result
        assert len(result["selected_actions"]) == 1
        assert result["selected_actions"][0]["action_type"] == "send_matrix_reply"
        assert result["observations"] == "test observation"

    def test_json_with_explanatory_text(self):
        """Test parsing JSON embedded in explanatory text."""
        text_with_json = '''Looking at the current situation, here's my analysis:

## Observations
The user is testing the system.

## Actions
Based on this, I recommend:

```json
{
  "observations": "User is testing the robust JSON parser",
  "potential_actions": [
    {
      "action_type": "wait",
      "parameters": {"duration": 1},
      "reasoning": "Give time for processing",
      "priority": 5
    }
  ],
  "selected_actions": [
    {
      "action_type": "wait",
      "parameters": {"duration": 1},
      "reasoning": "Give time for processing",
      "priority": 5
    }
  ],
  "reasoning": "Simple wait action for testing"
}
```

That's my recommendation.'''
        
        result = self.engine._extract_json_from_response(text_with_json)
        assert "selected_actions" in result
        assert "observations" in result
        assert len(result["selected_actions"]) == 1
        assert result["selected_actions"][0]["action_type"] == "wait"

    def test_json_mixed_in_text_without_markdown(self):
        """Test parsing JSON mixed directly in text without markdown markers."""
        mixed_text = '''Here's my analysis:
        
        {"selected_actions": [{"action_type": "test_action", "parameters": {"param": "value"}, "reasoning": "test", "priority": 7}], "observations": "direct JSON test"}
        
        That's my decision.'''
        
        result = self.engine._extract_json_from_response(mixed_text)
        assert "selected_actions" in result
        assert len(result["selected_actions"]) == 1
        assert result["selected_actions"][0]["action_type"] == "test_action"

    def test_multiple_json_objects_picks_largest(self):
        """Test that when multiple JSON objects exist, it picks the largest/most complete one."""
        multiple_json = '''
        First small JSON: {"observations": "small"}
        
        Here's the main response:
        ```json
        {
          "observations": "This is a larger, more complete response",
          "potential_actions": [
            {
              "action_type": "comprehensive_action",
              "parameters": {
                "param1": "value1",
                "param2": "value2"
              },
              "reasoning": "This is more detailed",
              "priority": 9
            }
          ],
          "selected_actions": [
            {
              "action_type": "comprehensive_action",
              "parameters": {
                "param1": "value1",
                "param2": "value2"
              },
              "reasoning": "This is more detailed",
              "priority": 9
            }
          ],
          "reasoning": "This is the comprehensive decision"
        }
        ```
        
        And a small one at the end: {"test": "small"}
        '''
        
        result = self.engine._extract_json_from_response(multiple_json)
        assert "selected_actions" in result
        assert "potential_actions" in result
        assert result["observations"] == "This is a larger, more complete response"

    def test_invalid_json_raises_error(self):
        """Test that completely invalid responses raise appropriate errors."""
        invalid_response = "This is just plain text with no JSON whatsoever."
        
        with pytest.raises(Exception):  # Should raise JSONDecodeError or similar
            self.engine._extract_json_from_response(invalid_response)

    def test_malformed_json_in_text(self):
        """Test that completely broken JSON in text is handled gracefully."""
        # Use JSON that's so broken even our enhanced parser can't fix it
        # Remove any recognizable key patterns so last-resort reconstruction fails
        completely_broken = '''Here's some text with completely broken JSON:
        
        {broken: unterminated, invalid: syntax everywhere, no_quotes_no_braces
        
        More text.'''
        
        with pytest.raises(Exception):  # Should raise an error for completely broken JSON
            self.engine._extract_json_from_response(completely_broken)

    def test_missing_opening_brace_fix(self):
        """Test that JSON missing opening brace can be fixed by enhanced parser."""
        # This is the actual problematic response from the logs
        missing_opening_brace = '''observations": "The primary channel contains advice on Farcaster engagement.",
  "selected_actions": [
    {
      "action_type": "send_matrix_message",
      "parameters": {
        "channel_id": "!test:example.com",
        "content": "Understood!"
      },
      "reasoning": "Acknowledge the advice",
      "priority": 9
    }
  ],
  "reasoning": "Applying the guidance received."
}'''
        
        result = self.engine._extract_json_from_response(missing_opening_brace)
        
        # Should successfully parse and reconstruct
        assert isinstance(result, dict)
        assert "selected_actions" in result
        assert len(result["selected_actions"]) == 1
        assert result["selected_actions"][0]["action_type"] == "send_matrix_message"
