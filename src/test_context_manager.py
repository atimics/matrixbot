#!/usr/bin/env python3
"""
Test script for the ContextManager
"""

import asyncio
import sys
import os
import tempfile
import json
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent))

from context_manager import ContextManager, StateChangeBlock
from world_state import WorldStateManager

async def test_context_manager():
    """Test the ContextManager functionality"""
    
    # Create a temporary database for testing
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as temp_db:
        db_path = temp_db.name
    
    try:
        # Initialize world state manager
        world_state = WorldStateManager()
        
        # Initialize context manager
        context_manager = ContextManager(world_state, db_path)
        
        # Test channel ID
        channel_id = "!test:matrix.example.com"
        
        print("Testing ContextManager...")
        
        # Add a user message
        user_message = {
            "content": "Hello, what can you help me with today?",
            "sender": "@user:matrix.example.com",
            "event_id": "$event1"
        }
        await context_manager.add_user_message(channel_id, user_message)
        print("✓ Added user message")
        
        # Add an assistant message with structured response
        assistant_message = {
            "content": json.dumps({
                "observations": "User is greeting me and asking for help",
                "potential_actions": [
                    {
                        "action_type": "send_matrix_reply",
                        "parameters": {
                            "channel_id": channel_id,
                            "reply_to_id": "$event1",
                            "content": "Hello! I'm here to help you with various tasks. What would you like assistance with?"
                        },
                        "reasoning": "Responding politely to the user's greeting and offering help",
                        "priority": 9
                    }
                ],
                "selected_actions": [
                    {
                        "action_type": "send_matrix_reply",
                        "parameters": {
                            "channel_id": channel_id,
                            "reply_to_id": "$event1",
                            "content": "Hello! I'm here to help you with various tasks. What would you like assistance with?"
                        }
                    }
                ],
                "reasoning": "This is a simple greeting that requires a friendly response"
            }),
            "event_id": "$event2"
        }
        await context_manager.add_assistant_message(channel_id, assistant_message)
        print("✓ Added assistant message with structured response")
        
        # Add a tool result
        tool_result = {
            "observations": "Successfully sent reply to user",
            "status": "success",
            "reasoning": "Message was delivered successfully"
        }
        await context_manager.add_tool_result(channel_id, "send_matrix_reply", tool_result)
        print("✓ Added tool result")
        
        # Get conversation messages
        messages = await context_manager.get_conversation_messages(channel_id)
        print(f"✓ Retrieved {len(messages)} conversation messages")
        
        # Print system prompt preview
        context = await context_manager.get_context(channel_id)
        print(f"\nSystem prompt preview (first 200 chars):")
        print(context.system_prompt[:200] + "...")
        
        # Get state changes
        state_changes = await context_manager.get_state_changes(channel_id=channel_id)
        print(f"✓ Retrieved {len(state_changes)} state changes for channel")
        
        # Get context summary
        summary = await context_manager.get_context_summary(channel_id)
        print(f"✓ Context summary: {summary}")
        
        # Test export functionality
        export_path = "test_state_changes.jsonl"
        exported_file = await context_manager.export_state_changes_for_training(export_path)
        print(f"✓ Exported state changes to {exported_file}")
        
        print("\n✅ All tests passed!")
        
        # Show sample state change data
        if state_changes:
            print(f"\nSample state change (type: {state_changes[0].change_type}):")
            print(f"  Source: {state_changes[0].source}")
            print(f"  Observations: {state_changes[0].observations}")
            if state_changes[0].selected_actions:
                print(f"  Selected Actions: {len(state_changes[0].selected_actions)}")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Clean up
        try:
            os.unlink(db_path)
            if os.path.exists(export_path):
                os.unlink(export_path)
        except:
            pass

if __name__ == "__main__":
    asyncio.run(test_context_manager())
