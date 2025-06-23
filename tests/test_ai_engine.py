"""
Tests for AI decision engine functionality.
"""
import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock, Mock
from chatbot.core.ai_engine import AIDecisionEngine, DecisionResult, ActionPlan


class TestAIDecisionEngine:
    """Test the AI decision engine with various scenarios."""
    
    def test_initialization_with_config(self):
        """Test initialization with custom config."""
        engine = AIDecisionEngine(api_key="test_key", model="claude-3-haiku")
        
        assert engine.api_key == "test_key"
        assert engine.model == "claude-3-haiku"
        assert engine.base_url is not None
    
    def test_initialization_without_api_key(self):
        """Test initialization fails without API key."""
        with pytest.raises(TypeError):
            # Should fail because api_key is required parameter
            AIDecisionEngine()
    
    @pytest.mark.asyncio
    async def test_make_decision_successful_response(self):
        """Test successful decision making with mocked response."""
        engine = AIDecisionEngine(api_key="test_key")
        
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
        engine = AIDecisionEngine(api_key="test_key")
        
        # Mock response for initial request (invalid JSON)
        mock_invalid_response_data = {
            "choices": [{
                "message": {
                    "content": "Invalid JSON response"
                }
            }]
        }
        
        # Mock response for recovery request (valid JSON)
        mock_recovery_response_data = {
            "choices": [{
                "message": {
                    "content": '{"reasoning": "Error recovery response", "selected_actions": [{"action_type": "wait", "details": {}}]}'
                }
            }]
        }
        
        mock_invalid_response = Mock()
        mock_invalid_response.status_code = 200
        mock_invalid_response.json.return_value = mock_invalid_response_data
        mock_invalid_response.raise_for_status = Mock()
        
        mock_recovery_response = Mock()
        mock_recovery_response.status_code = 200
        mock_recovery_response.json.return_value = mock_recovery_response_data
        mock_recovery_response.raise_for_status = Mock()
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            # First call returns invalid JSON, second call (recovery) returns valid JSON
            mock_client.post = AsyncMock(side_effect=[mock_invalid_response, mock_recovery_response])
            
            # Set up the async context manager properly
            mock_client_class.return_value = mock_client
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            
            result = await engine.make_decision({"test": "state"}, "test_cycle")
            
            # Should handle invalid JSON gracefully via error recovery
            assert result.cycle_id == "test_cycle"
            assert result.reasoning == "Error recovery response"
            assert len(result.selected_actions) == 1
            assert result.selected_actions[0].action_type == "wait"
            
            # Verify that two HTTP requests were made (original + recovery)
            assert mock_client.post.call_count == 2
    
    @pytest.mark.asyncio
    async def test_make_decision_http_error(self):
        """Test handling of HTTP errors."""
        engine = AIDecisionEngine(api_key="test_key")
        
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.raise_for_status = Mock()
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            
            # Set up the async context manager properly
            mock_client_class.return_value = mock_client
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            
            result = await engine.make_decision({"test": "state"}, "test_cycle")
            
            assert result.cycle_id == "test_cycle"
            assert len(result.selected_actions) == 0
            assert "API Error" in result.reasoning
    
    @pytest.mark.asyncio
    async def test_make_decision_network_exception(self):
        """Test handling of network exceptions."""
        engine = AIDecisionEngine(api_key="test_key")
        
        # Mock the error recovery system to prevent recursive calls
        with patch.object(engine.error_recovery, 'handle_ai_failure') as mock_recovery:
            mock_recovery.return_value = None  # Make recovery fail quickly
            
            with patch('httpx.AsyncClient') as mock_client_class:
                mock_client = AsyncMock()
                mock_client.post = AsyncMock(side_effect=Exception("Network timeout"))
                
                # Set up the async context manager properly
                mock_client_class.return_value = mock_client
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                
                result = await engine.make_decision({"test": "state"}, "test_cycle")
                
                assert result.cycle_id == "test_cycle"
                assert len(result.selected_actions) == 0
                assert "error" in result.reasoning.lower()
                
                # Verify that error recovery was attempted
                mock_recovery.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_make_decision_no_choices_in_response(self):
        """Test handling of response with no choices."""
        engine = AIDecisionEngine(api_key="test_key")
        
        mock_response_data = {
            "choices": []
        }
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status = Mock()
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            
            # Set up the async context manager properly
            mock_client_class.return_value = mock_client
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            
            result = await engine.make_decision({"test": "state"}, "test_cycle")
            
            assert result.cycle_id == "test_cycle"
            assert len(result.selected_actions) == 0
    
    def test_cleanup(self):
        """Test cleanup method (if it exists)."""
        engine = AIDecisionEngine(api_key="test_key")
        # Current implementation doesn't have cleanup method, so just verify it doesn't crash
        # If cleanup method is added later, this test should be updated
        assert engine.api_key == "test_key"
