#!/usr/bin/env python3
"""
Test to verify that the orchestrator correctly handles 'scheduled' status from Farcaster tools.
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

from chatbot.tools.farcaster_tools import SendFarcasterReplyTool
from chatbot.tools.base import ActionContext


async def test_scheduled_status_handling():
    """Test that the reply tool returns 'scheduled' status when scheduling is available."""
    
    # Mock Farcaster observer with scheduling support
    farcaster_observer = MagicMock()
    farcaster_observer.schedule_reply = MagicMock()
    farcaster_observer.reply_queue = asyncio.Queue()  # Make it look like scheduling is supported
    
    # Mock world state manager
    world_state_manager = MagicMock()
    world_state_manager.has_replied_to_cast = MagicMock(return_value=False)
    world_state_manager.add_action_result = MagicMock()
    
    # Create action context
    context = ActionContext(
        matrix_observer=None,
        farcaster_observer=farcaster_observer,
        world_state_manager=world_state_manager,
        context_manager=None
    )
    
    # Create a reply tool
    reply_tool = SendFarcasterReplyTool()
    
    # Execute the tool
    params = {
        "content": "Test reply",
        "reply_to_hash": "0x123abc"
    }
    
    result = await reply_tool.execute(params, context)
    
    # Verify that the result has 'scheduled' status
    assert result["status"] == "scheduled", f"Expected 'scheduled' status, got {result['status']}"
    assert "Scheduled Farcaster reply" in result["message"]
    
    # Verify that schedule_reply was called
    farcaster_observer.schedule_reply.assert_called_once_with("Test reply", "0x123abc")
    
    print("✅ Test passed: Farcaster reply tool correctly returns 'scheduled' status")
    print(f"✅ Result: {result}")


if __name__ == "__main__":
    asyncio.run(test_scheduled_status_handling())
