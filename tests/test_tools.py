"""
Test suite for the chatbot tools and actions.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
import time

from chatbot.tools.executor import ActionExecutor


class TestActionExecutor:
    """Test the action execution system."""
    
    def test_initialization(self):
        """Test action executor initialization."""
        executor = ActionExecutor()
        assert executor.matrix_observer is None
        assert executor.farcaster_observer is None
    
    def test_set_observers(self):
        """Test setting observers."""
        executor = ActionExecutor()
        
        # Mock observers
        matrix_observer = Mock()
        farcaster_observer = Mock()
        
        executor.set_matrix_observer(matrix_observer)
        executor.set_farcaster_observer(farcaster_observer)
        
        assert executor.matrix_observer == matrix_observer
        assert executor.farcaster_observer == farcaster_observer
    
    @pytest.mark.asyncio
    async def test_send_matrix_reply_success(self):
        """Test sending a Matrix reply successfully."""
        executor = ActionExecutor()
        
        # Mock Matrix observer
        mock_observer = AsyncMock()
        mock_observer.send_reply.return_value = {"success": True, "event_id": "event_456"}
        executor.set_matrix_observer(mock_observer)
        
        # Test parameters with required fields
        params = {
            "channel_id": "test_channel",
            "content": "Hello world",
            "reply_to_event_id": "event_123"  # Required parameter
        }
        
        result = await executor.execute_action("send_matrix_reply", params)
        
        assert result["status"] == "success"
        assert "message" in result
        mock_observer.send_reply.assert_called_once_with("test_channel", "Hello world", "event_123")
    
    @pytest.mark.asyncio
    async def test_send_matrix_reply_no_observer(self):
        """Test sending Matrix reply without observer."""
        executor = ActionExecutor()
        
        params = {
            "channel_id": "test_channel", 
            "content": "Hello world"
        }
        
        result = await executor.execute_action("send_matrix_reply", params)
        
        assert result["status"] == "failure"  # Updated to match actual implementation
        assert "Matrix observer not configured" in result["error"]
    
    @pytest.mark.asyncio
    async def test_send_farcaster_cast_success(self):
        """Test sending a Farcaster cast successfully."""
        executor = ActionExecutor()
        
        # Mock Farcaster observer
        mock_observer = AsyncMock()
        mock_observer.post_cast.return_value = {"success": True, "cast_hash": "0x123"}
        executor.set_farcaster_observer(mock_observer)
        
        params = {
            "content": "Hello Farcaster"
        }
        
        # Use the correct action name that exists in the executor
        result = await executor.execute_action("send_farcaster_post", params)
        
        # The executor returns a dict with message field
        assert result["status"] == "success"
        assert "Posted to Farcaster" in result["message"]
        mock_observer.post_cast.assert_called_once_with("Hello Farcaster", None)
    
    @pytest.mark.asyncio
    async def test_unknown_action(self):
        """Test executing an unknown action."""
        executor = ActionExecutor()
        
        result = await executor.execute_action("unknown_action", {})
        
        assert result["status"] == "failure"  # Updated to match actual implementation
        assert "Unknown action" in result["error"]
    
    @pytest.mark.asyncio
    async def test_action_with_exception(self):
        """Test action execution with exception."""
        executor = ActionExecutor()
        
        # Mock Matrix observer that raises an exception
        mock_observer = AsyncMock()
        mock_observer.send_reply.side_effect = Exception("Network error")
        executor.set_matrix_observer(mock_observer)
        
        params = {
            "channel_id": "test_channel",
            "content": "Hello world",
            "reply_to_event_id": "event_123"  # Required parameter
        }
        
        result = await executor.execute_action("send_matrix_reply", params)
        
        assert result["status"] == "failure"  # Updated to match actual implementation
        assert "Network error" in result["error"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
