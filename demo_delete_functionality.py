#!/usr/bin/env python3
"""
Demo script showing the new Farcaster delete functionality.

This demonstrates how the bot can now delete its own posts and reactions.
"""

import asyncio
import logging
from unittest.mock import AsyncMock

from chatbot.tools.farcaster_tools import (
    SendFarcasterPostTool, 
    LikeFarcasterPostTool,
    DeleteFarcasterPostTool, 
    DeleteFarcasterReactionTool
)
from chatbot.tools.base import ActionContext
from chatbot.core.world_state import WorldStateManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def demo_delete_functionality():
    """Demonstrate the new delete functionality."""
    print("🎯 Farcaster Delete Functionality Demo")
    print("=" * 50)
    
    # Set up mock observer and world state
    mock_observer = AsyncMock()
    world_state_manager = WorldStateManager()
    
    context = ActionContext(
        farcaster_observer=mock_observer,
        world_state_manager=world_state_manager
    )
    
    # Mock successful responses
    mock_observer.post_cast.return_value = {
        "success": True,
        "cast": {"hash": "0xdemo123"},
        "sent_content": "Demo post content"
    }
    
    mock_observer.like_cast.return_value = {
        "success": True,
        "message": "Cast liked successfully"
    }
    
    mock_observer.delete_cast.return_value = {
        "success": True,
        "message": "Cast deleted successfully"
    }
    
    mock_observer.delete_reaction.return_value = {
        "success": True,
        "message": "Reaction deleted successfully"
    }
    
    # Demo 1: Post and then delete a cast
    print("\n📝 Demo 1: Post and Delete a Cast")
    print("-" * 30)
    
    post_tool = SendFarcasterPostTool()
    delete_post_tool = DeleteFarcasterPostTool()
    
    # Create a post
    post_result = await post_tool.execute(
        {"content": "This is a demo post that we'll delete!"}, 
        context
    )
    print(f"✅ Posted: {post_result['status']}")
    
    # Delete the post
    delete_result = await delete_post_tool.execute(
        {"cast_hash": "0xdemo123"}, 
        context
    )
    print(f"🗑️ Deleted post: {delete_result['status']}")
    print(f"   Message: {delete_result['message']}")
    
    # Demo 2: Like and then unlike a cast
    print("\n❤️ Demo 2: Like and Unlike a Cast")
    print("-" * 30)
    
    like_tool = LikeFarcasterPostTool()
    delete_reaction_tool = DeleteFarcasterReactionTool()
    
    # Like a cast
    like_result = await like_tool.execute(
        {"cast_hash": "0xsomecast456"}, 
        context
    )
    print(f"👍 Liked cast: {like_result['status']}")
    
    # Unlike the cast (delete reaction)
    unlike_result = await delete_reaction_tool.execute(
        {"cast_hash": "0xsomecast456"}, 
        context
    )
    print(f"👎 Unliked cast: {unlike_result['status']}")
    print(f"   Message: {unlike_result['message']}")
    
    # Demo 3: Error handling
    print("\n❌ Demo 3: Error Handling")
    print("-" * 30)
    
    # Mock a failure response
    mock_observer.delete_cast.return_value = {
        "success": False,
        "error": "Cast not found or not authorized to delete"
    }
    
    # Try to delete a non-existent cast
    error_result = await delete_post_tool.execute(
        {"cast_hash": "0xnotfound"}, 
        context
    )
    print(f"🚫 Delete failed: {error_result['status']}")
    print(f"   Error: {error_result['error']}")
    
    # Check world state updates
    print("\n📊 World State Summary")
    print("-" * 30)
    print(f"Total actions recorded: {len(world_state_manager.state.action_history)}")
    
    for i, action in enumerate(world_state_manager.state.action_history, 1):
        status = "✅" if action.result == "success" else "❌"
        print(f"{status} {i}. {action.action_type}: {action.result}")
    
    print("\n🎉 Demo completed!")
    print("\nKey Features Demonstrated:")
    print("• Delete your own Farcaster posts")
    print("• Remove reactions (likes/recasts)")
    print("• Proper error handling")
    print("• World state integration")
    print("• API response validation")

if __name__ == "__main__":
    asyncio.run(demo_delete_functionality())
