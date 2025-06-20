"""
Tests for AI decision engine functionality.
"""
import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock, Mock
from chatbot.core.ai_engine import AIEngine, AIEngineConfig, AIResponse, ToolCall


class TestAIEngine:
    """Test the unified AI engine with various scenarios."""
    
    def test_initialization_with_config(self):
        """Test initialization with custom config."""
        config = AIEngineConfig(api_key="test_key", model="claude-3-haiku")
        engine = AIEngine(config)
        
        assert engine.config.api_key == "test_key"
        assert engine.config.model == "claude-3-haiku"
        assert hasattr(engine, 'config')
    
    def test_initialization_without_api_key(self):
        """Test initialization fails without API key."""
        with pytest.raises(ValueError):
            # Should fail because api_key is required parameter
            config = AIEngineConfig(api_key="")
            AIEngine(config)
    
    @pytest.mark.asyncio
    async def test_decide_actions_successful_response(self):
        """Test successful decision making with mocked response."""
        engine = AIEngine(AIEngineConfig(api_key="test_key"))
        
        # Mock response data that matches current JSON structure
        mock_response_data = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "tool_calls": [{
                            "name": "wait",
                            "parameters": {},
                            "reasoning": "No action needed"
                        }],
                        "message": "I'm waiting for more input",
                        "reasoning": "Test reasoning"
                    })
                }
            }]
        }
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status = MagicMock()
        
        # Mock httpx.AsyncClient properly
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            
            # Set up the async context manager
            mock_client_class.return_value = mock_client
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            
            result = await engine.decide_actions({"test": "state"})
            
            assert "reasoning" in result
            assert "selected_actions" in result
            assert len(result["selected_actions"]) == 1
            assert result["selected_actions"][0]["action_type"] == "wait"
    
    @pytest.mark.asyncio
    async def test_decide_actions_invalid_json_response(self):
        """Test handling of invalid JSON response."""
        config = AIEngineConfig(api_key="test_key")
        engine = AIEngine(config)
        
        mock_response_data = {
            "choices": [{
                "message": {
                    "content": "Invalid JSON response"
                }
            }]
        }
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status.return_value = None
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_context = AsyncMock()
            mock_context.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_context
            
            result = await engine.decide_actions({"test": "state"})
            
            # Should handle invalid JSON gracefully
            assert "reasoning" in result
            assert "error" in result["reasoning"].lower() or "failed" in result["reasoning"].lower()
    
    @pytest.mark.asyncio
    async def test_decide_actions_http_error(self):
        """Test handling of HTTP errors."""
        config = AIEngineConfig(api_key="test_key")
        engine = AIEngine(config)
        
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.raise_for_status.return_value = None
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_context = AsyncMock()
            mock_context.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_context
            
            result = await engine.decide_actions({"test": "state"})
            
            assert "reasoning" in result
            assert len(result["selected_actions"]) == 0  # Should have no actions on error
            assert "error" in result["reasoning"].lower()
    
    @pytest.mark.asyncio
    async def test_decide_actions_network_exception(self):
        """Test handling of network exceptions."""
        config = AIEngineConfig(api_key="test_key")
        engine = AIEngine(config)
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_context = AsyncMock()
            mock_context.__aenter__.return_value.post = AsyncMock(side_effect=Exception("Network timeout"))
            mock_client.return_value = mock_context
            
            result = await engine.decide_actions({"test": "state"})
            
            assert "reasoning" in result
            assert len(result["selected_actions"]) == 0  # Should have no actions on error
            assert "error" in result["reasoning"].lower()
    
    @pytest.mark.asyncio
    async def test_decide_actions_no_choices_in_response(self):
        """Test handling of response with no choices."""
        config = AIEngineConfig(api_key="test_key")
        engine = AIEngine(config)
        
        mock_response_data = {
            "choices": []
        }
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status.return_value = None
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_context = AsyncMock()
            mock_context.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_context
            
            result = await engine.decide_actions({"test": "state"})
            
            assert "reasoning" in result
            assert len(result["selected_actions"]) == 0  # Should have no actions on error
            assert "error" in result["reasoning"].lower()
    
    def test_cleanup(self):
        """Test cleanup method (if it exists)."""
        config = AIEngineConfig(api_key="test_key")
        engine = AIEngine(config)
        # Current implementation doesn't have cleanup method, so just verify it doesn't crash
        # If cleanup method is added later, this test should be updated
        assert engine.config.api_key == "test_key"
