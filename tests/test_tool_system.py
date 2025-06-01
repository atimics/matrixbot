"""
Test suite for the new tool-based architecture.
"""

import pytest
from unittest.mock import Mock, AsyncMock
import time

from chatbot.tools.base import ToolInterface, ActionContext
from chatbot.tools.registry import ToolRegistry
from chatbot.tools.core_tools import WaitTool
from chatbot.tools.matrix_tools import SendMatrixReplyTool, SendMatrixMessageTool
from chatbot.tools.farcaster_tools import SendFarcasterPostTool, SendFarcasterReplyTool


class TestToolRegistry:
    """Test the tool registry system."""
    
    def test_initialization(self):
        """Test tool registry initialization."""
        registry = ToolRegistry()
        assert len(registry.get_all_tools()) == 0
        assert registry.get_tool_names() == []
    
    def test_register_tool(self):
        """Test tool registration."""
        registry = ToolRegistry()
        wait_tool = WaitTool()
        
        registry.register_tool(wait_tool)
        assert len(registry.get_all_tools()) == 1
        assert "wait" in registry.get_tool_names()
        assert registry.get_tool("wait") is wait_tool
    
    def test_get_nonexistent_tool(self):
        """Test getting a tool that doesn't exist."""
        registry = ToolRegistry()
        assert registry.get_tool("nonexistent") is None
    
    def test_generate_tool_descriptions(self):
        """Test generating tool descriptions for AI."""
        registry = ToolRegistry()
        wait_tool = WaitTool()
        registry.register_tool(wait_tool)
        
        descriptions = registry.get_tool_descriptions_for_ai()
        assert "wait" in descriptions
        assert "observe" in descriptions.lower() or "wait" in descriptions.lower()


class TestActionContext:
    """Test the action context dependency injection."""
    
    def test_initialization(self):
        """Test action context initialization."""
        mock_matrix = Mock()
        mock_farcaster = Mock()
        
        context = ActionContext(
            matrix_observer=mock_matrix,
            farcaster_observer=mock_farcaster
        )
        
        assert context.matrix_observer is mock_matrix
        assert context.farcaster_observer is mock_farcaster


class TestCoreTools:
    """Test the core tool implementations."""
    
    @pytest.mark.asyncio
    async def test_wait_tool(self):
        """Test the wait tool functionality."""
        wait_tool = WaitTool()
        
        # Test properties
        assert wait_tool.name == "wait"
        assert "wait" in wait_tool.description.lower() or "observe" in wait_tool.description.lower()
        assert "duration" in wait_tool.parameters_schema
        
        # Test execution
        context = ActionContext()
        result = await wait_tool.execute({}, context)
        assert result["status"] == "success"
        assert "waited" in result["message"].lower()
        
        # Test with duration
        result = await wait_tool.execute({"duration": 1}, context)
        assert result["status"] == "success"


class TestMatrixTools:
    """Test Matrix platform tools."""
    
    @pytest.mark.asyncio
    async def test_send_matrix_reply_tool(self):
        """Test Matrix reply tool."""
        tool = SendMatrixReplyTool()
        
        # Test properties
        assert tool.name == "send_matrix_reply"
        assert "reply" in tool.description.lower()
        assert "channel_id" in tool.parameters_schema
        assert "content" in tool.parameters_schema
        assert "reply_to_id" in tool.parameters_schema
        
        # Test execution with mock observer
        mock_observer = AsyncMock()
        mock_observer.send_reply.return_value = {
            "success": True,
            "event_id": "test_event_123",
            "sent_content": "Test reply"
        }
        
        context = ActionContext(matrix_observer=mock_observer)
        params = {
            "channel_id": "!test:example.com",
            "content": "Test reply",
            "reply_to_id": "original_event",
            "format_as_markdown": False
        }
        
        result = await tool.execute(params, context)
        assert result["status"] == "success"
        assert result["event_id"] == "test_event_123"
        mock_observer.send_reply.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_send_matrix_message_tool(self):
        """Test Matrix message tool."""
        tool = SendMatrixMessageTool()
        
        # Test properties
        assert tool.name == "send_matrix_message"
        assert "message" in tool.description.lower()
        assert "channel_id" in tool.parameters_schema
        assert "content" in tool.parameters_schema
        
        # Test execution with mock observer
        mock_observer = AsyncMock()
        mock_observer.send_message.return_value = {
            "success": True,
            "event_id": "test_event_456",
            "sent_content": "Test message"
        }
        
        context = ActionContext(matrix_observer=mock_observer)
        params = {
            "channel_id": "!test:example.com",
            "content": "Test message",
            "format_as_markdown": False
        }
        
        result = await tool.execute(params, context)
        assert result["status"] == "success"
        assert result["event_id"] == "test_event_456"
        mock_observer.send_message.assert_called_once()


class TestFarcasterTools:
    """Test Farcaster platform tools."""
    
    @pytest.mark.asyncio
    async def test_send_farcaster_post_tool(self):
        """Test Farcaster post tool."""
        tool = SendFarcasterPostTool()
        
        # Test properties
        assert tool.name == "send_farcaster_post"
        assert "farcaster" in tool.description.lower()
        assert "content" in tool.parameters_schema
        
        # Test execution with mock observer
        mock_observer = AsyncMock()
        mock_observer.post_cast.return_value = {
            "success": True,
            "cast_hash": "test_hash_123",
            "sent_content": "Test post"
        }
        
        context = ActionContext(farcaster_observer=mock_observer)
        params = {"content": "Test post"}
        
        result = await tool.execute(params, context)
        assert result["status"] == "success"
        assert result["cast_hash"] == "test_hash_123"
        mock_observer.post_cast.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_send_farcaster_reply_tool(self):
        """Test Farcaster reply tool."""
        tool = SendFarcasterReplyTool()
        
        # Test properties
        assert tool.name == "send_farcaster_reply"
        assert "reply" in tool.description.lower()
        assert "content" in tool.parameters_schema
        assert "reply_to_hash" in tool.parameters_schema
        
        # Test execution with mock observer
        mock_observer = AsyncMock()
        mock_observer.reply_to_cast.return_value = {
            "success": True,
            "cast_hash": "test_reply_hash",
            "sent_content": "Test reply"
        }
        
        context = ActionContext(farcaster_observer=mock_observer)
        params = {
            "content": "Test reply",
            "reply_to_hash": "original_hash"
        }
        
        result = await tool.execute(params, context)
        assert result["status"] == "success"
        assert result["cast_hash"] == "test_reply_hash"
        mock_observer.reply_to_cast.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
