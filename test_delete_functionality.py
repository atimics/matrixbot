#!/usr/bin/env python3
"""
Test the new delete functionality for Farcaster posts and reactions.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock

from chatbot.tools.farcaster_tools import DeleteFarcasterPostTool, DeleteFarcasterReactionTool
from chatbot.tools.base import ActionContext
from chatbot.core.world_state import WorldStateManager


@pytest.mark.asyncio
async def test_delete_farcaster_post_tool():
    """Test the DeleteFarcasterPostTool functionality."""
    tool = DeleteFarcasterPostTool()
    
    # Test properties
    assert tool.name == "delete_farcaster_post"
    assert "delete" in tool.description.lower()
    assert "cast_hash" in tool.parameters_schema["properties"]
    
    # Test successful deletion
    mock_observer = AsyncMock()
    mock_observer.delete_cast.return_value = {
        "success": True,
        "message": "Cast deleted successfully"
    }
    
    world_state_manager = WorldStateManager()
    context = ActionContext(
        farcaster_observer=mock_observer,
        world_state_manager=world_state_manager
    )
    
    params = {"cast_hash": "0xabc123"}
    result = await tool.execute(params, context)
    
    assert result["status"] == "success"
    assert result["cast_hash"] == "0xabc123"
    mock_observer.delete_cast.assert_called_once_with("0xabc123")
    
    # Check world state was updated
    assert len(world_state_manager.state.action_history) == 1
    action = world_state_manager.state.action_history[0]
    assert action.action_type == "delete_farcaster_post"
    assert action.result == "success"


@pytest.mark.asyncio
async def test_delete_farcaster_post_tool_failure():
    """Test DeleteFarcasterPostTool failure handling."""
    tool = DeleteFarcasterPostTool()
    
    # Test failed deletion
    mock_observer = AsyncMock()
    mock_observer.delete_cast.return_value = {
        "success": False,
        "error": "Cast not found or not authorized"
    }
    
    world_state_manager = WorldStateManager()
    context = ActionContext(
        farcaster_observer=mock_observer,
        world_state_manager=world_state_manager
    )
    
    params = {"cast_hash": "0xnotfound"}
    result = await tool.execute(params, context)
    
    assert result["status"] == "failure"
    assert "not found or not authorized" in result["error"]


@pytest.mark.asyncio
async def test_delete_farcaster_reaction_tool():
    """Test the DeleteFarcasterReactionTool functionality."""
    tool = DeleteFarcasterReactionTool()
    
    # Test properties
    assert tool.name == "delete_farcaster_reaction"
    assert "reaction" in tool.description.lower()
    assert "cast_hash" in tool.parameters_schema["properties"]
    
    # Test successful reaction deletion
    mock_observer = AsyncMock()
    mock_observer.delete_reaction.return_value = {
        "success": True,
        "message": "Reaction deleted successfully"
    }
    
    world_state_manager = WorldStateManager()
    context = ActionContext(
        farcaster_observer=mock_observer,
        world_state_manager=world_state_manager
    )
    
    params = {"cast_hash": "0xdef456"}
    result = await tool.execute(params, context)
    
    assert result["status"] == "success"
    assert result["cast_hash"] == "0xdef456"
    mock_observer.delete_reaction.assert_called_once_with("0xdef456")


@pytest.mark.asyncio
async def test_delete_tools_missing_observer():
    """Test delete tools without Farcaster observer."""
    delete_post_tool = DeleteFarcasterPostTool()
    delete_reaction_tool = DeleteFarcasterReactionTool()
    
    context = ActionContext(farcaster_observer=None)
    params = {"cast_hash": "0xtest"}
    
    # Both tools should fail without observer
    result1 = await delete_post_tool.execute(params, context)
    result2 = await delete_reaction_tool.execute(params, context)
    
    assert result1["status"] == "failure"
    assert result2["status"] == "failure"
    assert "not configured" in result1["error"]
    assert "not configured" in result2["error"]


@pytest.mark.asyncio
async def test_delete_tools_missing_params():
    """Test delete tools with missing parameters."""
    delete_post_tool = DeleteFarcasterPostTool()
    delete_reaction_tool = DeleteFarcasterReactionTool()
    
    mock_observer = AsyncMock()
    context = ActionContext(farcaster_observer=mock_observer)
    
    # Missing cast_hash parameter
    params = {}
    
    result1 = await delete_post_tool.execute(params, context)
    result2 = await delete_reaction_tool.execute(params, context)
    
    assert result1["status"] == "failure"
    assert result2["status"] == "failure"
    assert "Missing required parameter" in result1["error"]
    assert "Missing required parameter" in result2["error"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
