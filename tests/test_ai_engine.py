"""
Tests for AI decision engine functionality.
"""
import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from chatbot.core.ai_engine import AIDecisionEngine
from chatbot.config import AppConfig


class TestAIDecisionEngine:
    """Test the AI decision engine with various scenarios."""
    
    def test_initialization_with_config(self):
        """Test initialization with custom config."""
        config = AppConfig()
        config.OPENROUTER_API_KEY = "test_key"
        config.AI_MODEL = "claude-3-haiku"
        
        engine = AIDecisionEngine(config)
        
        assert engine.api_key == "test_key"
        assert engine.model == "claude-3-haiku"
        assert engine.session is not None
    
    def test_initialization_without_api_key(self):
        """Test initialization fails without API key."""
        config = AppConfig()
        config.OPENROUTER_API_KEY = None
        
        with pytest.raises(ValueError, match="OPENROUTER_API_KEY is required"):
            AIDecisionEngine(config)
    
    @pytest.mark.asyncio
    async def test_make_decision_successful_response(self):
        """Test successful AI decision making."""
        config = AppConfig()
        config.OPENROUTER_API_KEY = "test_key"
        engine = AIDecisionEngine(config)
        
        # Mock the HTTP session
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "should_act": True,
                        "action_type": "send_matrix_reply",
                        "parameters": {"content": "Hello world"},
                        "reasoning": "User asked a question"
                    })
                }
            }]
        })
        
        engine.session.post = AsyncMock(return_value=mock_response)
        
        world_state = {"channels": {}, "recent_actions": []}
        decision = await engine.make_decision(world_state)
        
        assert decision["should_act"] is True
        assert decision["action_type"] == "send_matrix_reply"
        assert decision["parameters"]["content"] == "Hello world"
        assert "reasoning" in decision
    
    @pytest.mark.asyncio
    async def test_make_decision_invalid_json_response(self):
        """Test handling of invalid JSON response."""
        config = AppConfig()
        config.OPENROUTER_API_KEY = "test_key"
        engine = AIDecisionEngine(config)
        
        # Mock the HTTP session with invalid JSON
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "choices": [{
                "message": {
                    "content": "invalid json {{"
                }
            }]
        })
        
        engine.session.post = AsyncMock(return_value=mock_response)
        
        world_state = {"channels": {}, "recent_actions": []}
        decision = await engine.make_decision(world_state)
        
        assert decision["should_act"] is False
        assert "error" in decision
        assert "JSON decode error" in decision["error"]
    
    @pytest.mark.asyncio
    async def test_make_decision_http_error(self):
        """Test handling of HTTP errors."""
        config = AppConfig()
        config.OPENROUTER_API_KEY = "test_key"
        engine = AIDecisionEngine(config)
        
        # Mock HTTP error
        mock_response = MagicMock()
        mock_response.status = 500
        mock_response.text = AsyncMock(return_value="Internal Server Error")
        
        engine.session.post = AsyncMock(return_value=mock_response)
        
        world_state = {"channels": {}, "recent_actions": []}
        decision = await engine.make_decision(world_state)
        
        assert decision["should_act"] is False
        assert "error" in decision
        assert "HTTP 500" in decision["error"]
    
    @pytest.mark.asyncio
    async def test_make_decision_network_exception(self):
        """Test handling of network exceptions."""
        config = AppConfig()
        config.OPENROUTER_API_KEY = "test_key"
        engine = AIDecisionEngine(config)
        
        # Mock network exception
        engine.session.post = AsyncMock(side_effect=Exception("Network timeout"))
        
        world_state = {"channels": {}, "recent_actions": []}
        decision = await engine.make_decision(world_state)
        
        assert decision["should_act"] is False
        assert "error" in decision
        assert "Network timeout" in decision["error"]
    
    @pytest.mark.asyncio
    async def test_make_decision_no_choices_in_response(self):
        """Test handling of response without choices."""
        config = AppConfig()
        config.OPENROUTER_API_KEY = "test_key"
        engine = AIDecisionEngine(config)
        
        # Mock response without choices
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"choices": []})
        
        engine.session.post = AsyncMock(return_value=mock_response)
        
        world_state = {"channels": {}, "recent_actions": []}
        decision = await engine.make_decision(world_state)
        
        assert decision["should_act"] is False
        assert "error" in decision
        assert "No choices in response" in decision["error"]
    
    @pytest.mark.asyncio
    async def test_cleanup(self):
        """Test cleanup closes session."""
        config = AppConfig()
        config.OPENROUTER_API_KEY = "test_key"
        engine = AIDecisionEngine(config)
        
        # Mock session close
        engine.session.close = AsyncMock()
        
        await engine.cleanup()
        
        engine.session.close.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
