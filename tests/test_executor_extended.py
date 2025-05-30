"""
Tests for action executor functionality.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from chatbot.tools.executor import ActionExecutor


class TestActionExecutorExtended:
    """Extended tests for the action executor functionality."""
    
    @pytest.mark.asyncio
    async def test_wait_action(self):
        """Test the wait action."""
        executor = ActionExecutor()
        
        import time
        start_time = time.time()
        
        result = await executor.execute_action("wait", {"seconds": 0.1})
        
        end_time = time.time()
        elapsed = end_time - start_time
        
        # Should have waited approximately 0.1 seconds
        assert elapsed >= 0.1
        assert "Waited for 0.1 seconds" in result
    
    @pytest.mark.asyncio
    async def test_send_matrix_reply_missing_parameters(self):
        """Test Matrix reply with missing parameters."""
        executor = ActionExecutor()
        
        # Mock Matrix observer
        mock_observer = AsyncMock()
        executor.set_matrix_observer(mock_observer)
        
        # Test with missing content
        params = {
            "channel_id": "test_channel",
            "reply_to_event_id": "event_123"
            # Missing content
        }
        
        result = await executor.execute_action("send_matrix_reply", params)
        
        assert result["status"] == "failure"
        assert "Missing required parameters" in result["error"]
        assert "content" in result["error"]
    
    @pytest.mark.asyncio
    async def test_send_matrix_reply_observer_failure(self):
        """Test Matrix reply when observer returns failure."""
        executor = ActionExecutor()
        
        # Mock Matrix observer that returns failure
        mock_observer = AsyncMock()
        mock_observer.send_reply.return_value = {"success": False, "error": "Room not found"}
        executor.set_matrix_observer(mock_observer)
        
        params = {
            "channel_id": "nonexistent_room",
            "content": "Hello world",
            "reply_to_event_id": "event_123"
        }
        
        result = await executor.execute_action("send_matrix_reply", params)
        
        assert result["status"] == "failure"
        assert "Room not found" in result["error"]
    
    @pytest.mark.asyncio
    async def test_send_farcaster_post_no_observer(self):
        """Test Farcaster post without observer configured."""
        executor = ActionExecutor()
        
        params = {"content": "Hello Farcaster"}
        
        result = await executor.execute_action("send_farcaster_post", params)
        
        assert "Farcaster observer not configured" in result
    
    @pytest.mark.asyncio
    async def test_send_farcaster_post_missing_content(self):
        """Test Farcaster post with missing content."""
        executor = ActionExecutor()
        
        # Mock Farcaster observer
        mock_observer = AsyncMock()
        executor.set_farcaster_observer(mock_observer)
        
        params = {}  # Missing content
        
        result = await executor.execute_action("send_farcaster_post", params)
        
        assert "Missing content" in result
    
    @pytest.mark.asyncio
    async def test_send_farcaster_post_with_channel(self):
        """Test Farcaster post with specific channel."""
        executor = ActionExecutor()
        
        # Mock Farcaster observer
        mock_observer = AsyncMock()
        mock_observer.post_cast.return_value = {"success": True, "cast_hash": "0xabc123"}
        executor.set_farcaster_observer(mock_observer)
        
        params = {
            "content": "Hello specific channel",
            "channel": "crypto"
        }
        
        result = await executor.execute_action("send_farcaster_post", params)
        
        assert "Posted to Farcaster" in result
        mock_observer.post_cast.assert_called_once_with("Hello specific channel", "crypto")
    
    @pytest.mark.asyncio
    async def test_send_farcaster_post_observer_failure(self):
        """Test Farcaster post when observer returns failure."""
        executor = ActionExecutor()
        
        # Mock Farcaster observer that returns failure
        mock_observer = AsyncMock()
        mock_observer.post_cast.return_value = {"success": False, "error": "Rate limit exceeded"}
        executor.set_farcaster_observer(mock_observer)
        
        params = {"content": "Too many posts"}
        
        result = await executor.execute_action("send_farcaster_post", params)
        
        assert "Failed to post to Farcaster" in result
        assert "Rate limit exceeded" in result
    
    @pytest.mark.asyncio
    async def test_send_farcaster_reply_functionality(self):
        """Test Farcaster reply functionality."""
        executor = ActionExecutor()
        
        # Mock Farcaster observer
        mock_observer = AsyncMock()
        mock_observer.reply_to_cast.return_value = {"success": True, "cast_hash": "0xreply123"}
        executor.set_farcaster_observer(mock_observer)
        
        params = {
            "content": "This is a reply",
            "parent_cast_hash": "0xoriginal123"
        }
        
        result = await executor.execute_action("send_farcaster_reply", params)
        
        assert "Replied to Farcaster cast" in result
        mock_observer.reply_to_cast.assert_called_once_with("This is a reply", "0xoriginal123")
    
    @pytest.mark.asyncio
    async def test_send_farcaster_reply_missing_parent(self):
        """Test Farcaster reply with missing parent cast hash."""
        executor = ActionExecutor()
        
        # Mock Farcaster observer
        mock_observer = AsyncMock()
        executor.set_farcaster_observer(mock_observer)
        
        params = {
            "content": "This is a reply"
            # Missing parent_cast_hash
        }
        
        result = await executor.execute_action("send_farcaster_reply", params)
        
        assert "Missing parent_cast_hash" in result
    
    @pytest.mark.asyncio
    async def test_observer_state_management(self):
        """Test observer setting and state management."""
        executor = ActionExecutor()
        
        # Initially no observers
        assert executor.matrix_observer is None
        assert executor.farcaster_observer is None
        
        # Set observers
        matrix_obs = AsyncMock()
        farcaster_obs = AsyncMock()
        
        executor.set_matrix_observer(matrix_obs)
        executor.set_farcaster_observer(farcaster_obs)
        
        assert executor.matrix_observer is matrix_obs
        assert executor.farcaster_observer is farcaster_obs
        
        # Set observers using the combined method
        executor.set_observers(matrix_obs, farcaster_obs)
        
        assert executor.matrix_observer is matrix_obs
        assert executor.farcaster_observer is farcaster_obs
    
    @pytest.mark.asyncio
    async def test_action_parameter_handling(self):
        """Test various parameter handling scenarios."""
        executor = ActionExecutor()
        
        # Test room_id vs channel_id parameter naming
        mock_observer = AsyncMock()
        mock_observer.send_reply.return_value = {"success": True, "event_id": "event_456"}
        executor.set_matrix_observer(mock_observer)
        
        # Test with room_id parameter
        params1 = {
            "room_id": "test_room",
            "content": "Hello with room_id",
            "reply_to_event_id": "event_123"
        }
        
        result1 = await executor.execute_action("send_matrix_reply", params1)
        assert result1["status"] == "success"
        
        # Test with channel_id parameter
        params2 = {
            "channel_id": "test_room",
            "content": "Hello with channel_id", 
            "reply_to_event_id": "event_123"
        }
        
        result2 = await executor.execute_action("send_matrix_reply", params2)
        assert result2["status"] == "success"
        
        # Verify both calls were made correctly
        assert mock_observer.send_reply.call_count == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
