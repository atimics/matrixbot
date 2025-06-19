"""
Tests for AI decision engine functionality.
"""
import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock, Mock
from chatbot.core.ai_engine_v2 import AIEngine, AIResponse, ToolCall


class TestAIEngine:
    """Test the unified AI engine with various scenarios."""
    
    def test_initialization_with_config(self):
        """Test initialization with custom config."""
        engine = AIEngine(api_key="test_key", model="claude-3-haiku")
        
        assert engine.api_key == "test_key"
        assert engine.model == "claude-3-haiku"
        assert hasattr(engine, 'config')
    
    def test_initialization_without_api_key(self):
        """Test initialization fails without API key."""
        with pytest.raises(TypeError):
            # Should fail because api_key is required parameter
            AIEngine()
    
    @pytest.mark.asyncio
    async def test_make_decision_successful_response(self):
        """Test successful decision making with mocked response."""
        engine = AIEngine(api_key="test_key")
        
        # Mock response data that matches current JSON structure
        mock_response_data = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "observations": "Test observation",
                        "potential_actions": [],
                        "selected_actions": [{
                            "action_type": "wait",
                            "parameters": {},
                            "reasoning": "No action needed",
                            "priority": 1
                        }],
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
            
            result = await engine.make_decision({"test": "state"}, "test_cycle")
            
            assert result.cycle_id == "test_cycle"
            assert result.observations == "Test observation"
            assert len(result.selected_actions) == 1
            assert result.selected_actions[0].action_type == "wait"
    
    @pytest.mark.asyncio
    async def test_make_decision_invalid_json_response(self):
        """Test handling of invalid JSON response."""
        engine = AIEngine(api_key="test_key")
        
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
            
            result = await engine.make_decision({"test": "state"}, "test_cycle")
            
            # Should handle invalid JSON gracefully
            assert result.cycle_id == "test_cycle"
            assert "error" in result.reasoning.lower() or "failed" in result.reasoning.lower()
    
    @pytest.mark.asyncio
    async def test_make_decision_http_error(self):
        """Test handling of HTTP errors."""
        engine = AIEngine(api_key="test_key")
        
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.raise_for_status.return_value = None
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_context = AsyncMock()
            mock_context.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_context
            
            result = await engine.make_decision({"test": "state"}, "test_cycle")
            
            assert result.cycle_id == "test_cycle"
            assert len(result.selected_actions) == 1  # Should have fallback wait action
            assert result.selected_actions[0].action_type == "wait"
            assert "api error" in result.reasoning.lower()
    
    @pytest.mark.asyncio
    async def test_make_decision_network_exception(self):
        """Test handling of network exceptions."""
        engine = AIEngine(api_key="test_key")
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_context = AsyncMock()
            mock_context.__aenter__.return_value.post = AsyncMock(side_effect=Exception("Network timeout"))
            mock_client.return_value = mock_context
            
            result = await engine.make_decision({"test": "state"}, "test_cycle")
            
            assert result.cycle_id == "test_cycle"
            assert len(result.selected_actions) == 1  # Should have fallback wait action
            assert result.selected_actions[0].action_type == "wait"
            assert "error" in result.reasoning.lower()
    
    @pytest.mark.asyncio
    async def test_make_decision_no_choices_in_response(self):
        """Test handling of response with no choices."""
        engine = AIEngine(api_key="test_key")
        
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
            
            result = await engine.make_decision({"test": "state"}, "test_cycle")
            
            assert result.cycle_id == "test_cycle"
            assert len(result.selected_actions) == 1  # Should have fallback wait action
            assert result.selected_actions[0].action_type == "wait"
            assert "error" in result.reasoning.lower()
    
    def test_cleanup(self):
        """Test cleanup method (if it exists)."""
        engine = AIEngine(api_key="test_key")
        # Current implementation doesn't have cleanup method, so just verify it doesn't crash
        # If cleanup method is added later, this test should be updated
        assert engine.api_key == "test_key"
