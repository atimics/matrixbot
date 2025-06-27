"""
Tests for the unified tool execution pipeline.

This test suite verifies that the refactoring successfully eliminates the
fragmented execution paths and creates a single, unified pipeline for all tools.
"""

import pytest
from unittest.mock import Mock, AsyncMock

from chatbot.tools.registry import ToolRegistry
from chatbot.tools.base import ActionContext
from chatbot.tools.node_tools import (
    ExpandNodeTool, CollapseNodeTool, PinNodeTool, 
    UnpinNodeTool, RefreshSummaryTool, GetExpansionStatusTool
)
from chatbot.tools.matrix_tools import SendMatrixMessageTool
from chatbot.core.node_system.node_processor import NodeProcessor
from chatbot.core.services import ServiceRegistry


class TestUnifiedToolExecutionPipeline:
    """Test the unified tool execution pipeline."""
    
    @pytest.fixture
    def mock_world_state_manager(self):
        """Create a mock world state manager with node manager."""
        world_state_manager = Mock()
        node_manager = Mock()
        
        # Mock node manager methods
        node_manager.expand_node.return_value = (True, None, "Node expanded successfully")
        node_manager.collapse_node.return_value = (True, "Node collapsed successfully")
        node_manager.pin_node.return_value = (True, "Node pinned successfully") 
        node_manager.unpin_node.return_value = (True, "Node unpinned successfully")
        node_manager.get_node_metadata.return_value = Mock()
        node_manager.get_expansion_status_summary.return_value = {"expanded": 2, "pinned": 1}
        
        world_state_manager.node_manager = node_manager
        return world_state_manager
    
    @pytest.fixture
    def action_context(self, mock_world_state_manager):
        """Create an action context for testing."""
        service_registry = ServiceRegistry()
        return ActionContext(
            world_state_manager=mock_world_state_manager,
            service_registry=service_registry
        )
    
    @pytest.fixture
    def tool_registry(self):
        """Create a tool registry with unified node tools."""
        registry = ToolRegistry()
        
        # Register the new unified node tools
        registry.register_tool(ExpandNodeTool())
        registry.register_tool(CollapseNodeTool())
        registry.register_tool(PinNodeTool())
        registry.register_tool(UnpinNodeTool())
        registry.register_tool(RefreshSummaryTool())
        registry.register_tool(GetExpansionStatusTool())
        
        # Register a sample external tool
        registry.register_tool(SendMatrixMessageTool())
        
        return registry
    
    def test_node_tools_registered_in_tool_registry(self, tool_registry):
        """Test that all node tools are properly registered in the main tool registry."""
        expected_node_tools = [
            "expand_node", "collapse_node", "pin_node", 
            "unpin_node", "refresh_summary", "get_expansion_status"
        ]
        
        registered_tools = tool_registry.get_tool_names()
        
        for tool_name in expected_node_tools:
            assert tool_name in registered_tools, f"Node tool {tool_name} not registered in main tool registry"
    
    async def test_expand_node_tool_execution(self, tool_registry, action_context):
        """Test expand_node tool execution through unified pipeline."""
        tool = tool_registry.get_tool("expand_node")
        assert tool is not None, "expand_node tool not found in registry"
        
        params = {"node_path": "test.node.path"}
        result = await tool.execute(params, action_context)
        
        assert result["status"] == "success"
        assert result["action"] == "expand"
        assert result["node_path"] == "test.node.path"
        
        # Verify node manager was called
        action_context.world_state_manager.node_manager.expand_node.assert_called_once_with("test.node.path")
    
    async def test_collapse_node_tool_execution(self, tool_registry, action_context):
        """Test collapse_node tool execution through unified pipeline."""
        tool = tool_registry.get_tool("collapse_node")
        assert tool is not None
        
        params = {"node_path": "test.node.path"}
        result = await tool.execute(params, action_context)
        
        assert result["status"] == "success"
        assert result["action"] == "collapse"
        
        action_context.world_state_manager.node_manager.collapse_node.assert_called_once_with("test.node.path")
    
    async def test_pin_node_tool_execution(self, tool_registry, action_context):
        """Test pin_node tool execution through unified pipeline.""" 
        tool = tool_registry.get_tool("pin_node")
        assert tool is not None
        
        params = {"node_path": "test.node.path"}
        result = await tool.execute(params, action_context)
        
        assert result["status"] == "success"
        assert result["action"] == "pin"
        
        action_context.world_state_manager.node_manager.pin_node.assert_called_once_with("test.node.path")
    
    async def test_get_expansion_status_tool_execution(self, tool_registry, action_context):
        """Test get_expansion_status tool execution through unified pipeline."""
        tool = tool_registry.get_tool("get_expansion_status")
        assert tool is not None
        
        params = {}
        result = await tool.execute(params, action_context)
        
        assert result["status"] == "success"
        assert result["action"] == "get_expansion_status"
        assert "expansion_status" in result
        
        action_context.world_state_manager.node_manager.get_expansion_status_summary.assert_called_once()
    
    async def test_error_handling_missing_world_state(self, tool_registry):
        """Test error handling when world state manager is missing."""
        # Create action context without world state manager
        action_context = ActionContext()
        
        tool = tool_registry.get_tool("expand_node")
        params = {"node_path": "test.node.path"}
        result = await tool.execute(params, action_context)
        
        assert result["status"] == "failure"
        assert "World state manager not available" in result["error"]
    
    async def test_error_handling_missing_node_manager(self, tool_registry):
        """Test error handling when node manager is missing."""
        # Create world state manager without node_manager attribute
        world_state_manager = Mock()
        del world_state_manager.node_manager  # Remove the attribute
        
        action_context = ActionContext(world_state_manager=world_state_manager)
        
        tool = tool_registry.get_tool("expand_node")
        params = {"node_path": "test.node.path"}
        result = await tool.execute(params, action_context)
        
        assert result["status"] == "failure"
        assert "Node manager not available" in result["error"]
    
    async def test_error_handling_missing_parameters(self, tool_registry, action_context):
        """Test error handling for missing required parameters."""
        tool = tool_registry.get_tool("expand_node")
        params = {}  # Missing node_path
        result = await tool.execute(params, action_context)
        
        assert result["status"] == "failure"
        assert "Missing required parameter: node_path" in result["error"]
    
    def test_tool_registry_provides_unified_descriptions(self, tool_registry):
        """Test that tool registry provides unified descriptions for AI."""
        descriptions = tool_registry.get_tool_descriptions_for_ai()
        
        # Should contain both node tools and external tools
        assert "expand_node" in descriptions
        assert "send_matrix_message" in descriptions
        
        # Should be a unified format
        assert isinstance(descriptions, str)
        assert len(descriptions) > 0


class TestConsolidatedMatrixTools:
    """Test the consolidated Matrix messaging tools."""
    
    @pytest.fixture
    def mock_matrix_observer(self):
        """Create a mock Matrix observer."""
        observer = AsyncMock()
        observer.send_message.return_value = {"success": True, "event_id": "test_event_123"}
        observer.send_reply.return_value = {"success": True, "event_id": "test_reply_456"}
        observer.send_formatted_message.return_value = {"success": True, "event_id": "test_formatted_789"}
        observer.send_formatted_reply.return_value = {"success": True, "event_id": "test_formatted_reply_101"}
        return observer
    
    @pytest.fixture
    def action_context_matrix(self, mock_matrix_observer):
        """Create action context with Matrix observer."""
        return ActionContext(matrix_observer=mock_matrix_observer)
    
    async def test_send_matrix_message_regular(self, action_context_matrix):
        """Test sending a regular Matrix message (no reply_to_id)."""
        tool = SendMatrixMessageTool()
        params = {
            "channel_id": "!test:matrix.org",
            "content": "Hello world!",
            "format_as_markdown": False
        }
        
        result = await tool.execute(params, action_context_matrix)
        
        assert result["status"] == "success"
        assert result["event_id"] == "test_event_123"
        assert result["reply_to_event_id"] is None
        
        # Should call send_message (not send_reply)
        action_context_matrix.matrix_observer.send_message.assert_called_once_with(
            "!test:matrix.org", "Hello world!"
        )
        action_context_matrix.matrix_observer.send_reply.assert_not_called()
    
    async def test_send_matrix_message_as_reply(self, action_context_matrix):
        """Test sending a Matrix reply using the unified tool."""
        tool = SendMatrixMessageTool()
        params = {
            "channel_id": "!test:matrix.org",
            "content": "This is a reply!",
            "reply_to_id": "$original_event_123",
            "format_as_markdown": False
        }
        
        result = await tool.execute(params, action_context_matrix)
        
        assert result["status"] == "success"
        assert result["event_id"] == "test_reply_456"
        assert result["reply_to_event_id"] == "$original_event_123"
        
        # Should call send_reply (not send_message)
        action_context_matrix.matrix_observer.send_reply.assert_called_once_with(
            "!test:matrix.org", "This is a reply!", "$original_event_123"
        )
        action_context_matrix.matrix_observer.send_message.assert_not_called()
    
    async def test_consolidated_tool_parameters(self):
        """Test that the consolidated tool has the right parameters."""
        tool = SendMatrixMessageTool()
        schema = tool.parameters_schema
        
        # Should support both regular messages and replies
        assert "channel_id" in schema
        assert "content" in schema
        assert "reply_to_id" in schema  # NEW: Optional reply support
        assert "format_as_markdown" in schema
        assert "image_url" in schema
        
        # reply_to_id should be optional (indicated in description)
        assert "optional" in schema["reply_to_id"]


class TestNodeProcessorUnifiedExecution:
    """Test that NodeProcessor uses the unified execution pipeline."""
    
    @pytest.fixture
    def mock_dependencies(self):
        """Create mock dependencies for NodeProcessor."""
        node_manager = Mock()
        summary_service = Mock()
        ai_engine = Mock()
        world_state_manager = Mock()
        payload_builder = Mock()
        tool_registry = ToolRegistry()
        action_context = Mock()
        
        # Register a test tool in the registry
        test_tool = Mock()
        test_tool.execute = AsyncMock(return_value={"status": "success"})
        tool_registry.register_tool(test_tool, enabled=True)
        tool_registry._tools["test_action"] = test_tool
        
        return {
            "node_manager": node_manager,
            "summary_service": summary_service,
            "ai_engine": ai_engine,
            "world_state_manager": world_state_manager,
            "payload_builder": payload_builder,
            "tool_registry": tool_registry,
            "action_context": action_context
        }
    
    def test_node_processor_initialization_with_action_context(self, mock_dependencies):
        """Test NodeProcessor can be initialized with ActionContext."""
        processor = NodeProcessor(**mock_dependencies)
        
        assert processor.tool_registry is mock_dependencies["tool_registry"]
        assert processor.action_context is mock_dependencies["action_context"]
        assert hasattr(processor, "node_tools")  # Legacy compatibility maintained
    
    async def test_execute_action_uses_tool_registry(self, mock_dependencies):
        """Test that _execute_action routes through ToolRegistry instead of direct if/elif."""
        processor = NodeProcessor(**mock_dependencies)
        
        # Create a mock action
        mock_action = Mock()
        mock_action.action_type = "test_action"
        mock_action.parameters = {"param": "value"}
        
        # Execute the action
        result = await processor._execute_action(mock_action, "test_cycle")
        
        # Should have used tool registry
        assert result is True
        tool = mock_dependencies["tool_registry"].get_tool("test_action")
        tool.execute.assert_called_once()
    
    async def test_unknown_tool_handling(self, mock_dependencies):
        """Test handling of unknown tools."""
        processor = NodeProcessor(**mock_dependencies)
        
        mock_action = Mock()
        mock_action.action_type = "unknown_action"
        mock_action.parameters = {}
        
        result = await processor._execute_action(mock_action, "test_cycle")
        
        # Should return False for unknown tools
        assert result is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
