#!/usr/bin/env python3
"""
Simple Demo of Context-Aware System

This demonstrates the working context management system with the existing architecture.
"""

import asyncio
import logging
import tempfile
import json
import time
from pathlib import Path

# Setup path
import sys
sys.path.append(str(Path(__file__).parent))

from context_manager import ContextManager
from world_state import WorldStateManager

async def demo_context_system():
    """Demonstrate the context-aware system with realistic flow"""
    
    print("🚀 Starting Context-Aware System Demo")
    print("=" * 50)
    
    # Create temp database
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as temp_db:
        db_path = temp_db.name
    
    try:
        # Initialize components
        world_state = WorldStateManager()
        context_manager = ContextManager(world_state, db_path)
        
        # Simulate a Matrix room
        channel_id = "!demo:matrix.example.com"
        
        print(f"📝 Channel: {channel_id}")
        print()
        
        # ===== SCENARIO 1: User asks a question =====
        print("👤 User: Hello, what's the weather like?")
        
        user_message = {
            "content": "Hello, what's the weather like?", 
            "sender": "@alice:matrix.example.com",
            "event_id": "$event1",
            "timestamp": time.time()
        }
        await context_manager.add_user_message(channel_id, user_message)
        
        # ===== AI RESPONDS with structured format =====
        print("🤖 AI analyzes and responds...")
        
        ai_structured_response = {
            "observations": "User is asking about weather. I don't have weather data access, so I should explain my limitations.",
            "potential_actions": [
                {
                    "action_type": "send_matrix_reply",
                    "parameters": {
                        "channel_id": channel_id,
                        "reply_to_id": "$event1", 
                        "content": "I don't have access to weather data, but I can help with other questions!"
                    },
                    "reasoning": "Honest response about limitations while offering help",
                    "priority": 8
                },
                {
                    "action_type": "add_context",
                    "parameters": {
                        "context_type": "user_preference",
                        "data": {"user": "@alice:matrix.example.com", "interested_in": "weather"}
                    },
                    "reasoning": "Remember user's interest in weather data",
                    "priority": 5
                }
            ],
            "selected_actions": [
                {
                    "action_type": "send_matrix_reply", 
                    "parameters": {
                        "channel_id": channel_id,
                        "reply_to_id": "$event1",
                        "content": "I don't have access to weather data, but I can help with other questions!"
                    }
                }
            ],
            "reasoning": "Direct helpful response while being honest about limitations"
        }
        
        assistant_message = {
            "content": json.dumps(ai_structured_response),
            "event_id": "$event2",
            "timestamp": time.time()
        }
        await context_manager.add_assistant_message(channel_id, assistant_message)
        
        # ===== TOOL EXECUTION =====
        print("⚙️  Executing selected action: send_matrix_reply")
        
        tool_result = {
            "observations": "Successfully sent reply explaining weather data limitations",
            "status": "success", 
            "message_sent": True,
            "reasoning": "Message delivered successfully to Matrix room"
        }
        await context_manager.add_tool_result(channel_id, "send_matrix_reply", tool_result)
        
        print()
        
        # ===== SCENARIO 2: User follows up =====
        print("👤 User: Okay, can you help me write a Python function?")
        
        user_message2 = {
            "content": "Okay, can you help me write a Python function?",
            "sender": "@alice:matrix.example.com", 
            "event_id": "$event3",
            "timestamp": time.time()
        }
        await context_manager.add_user_message(channel_id, user_message2)
        
        # ===== AI RESPONDS AGAIN =====
        print("🤖 AI provides helpful programming assistance...")
        
        ai_response2 = {
            "observations": "User is now asking for programming help with Python. This is something I can definitely help with.",
            "potential_actions": [
                {
                    "action_type": "send_matrix_reply",
                    "parameters": {
                        "channel_id": channel_id,
                        "reply_to_id": "$event3",
                        "content": "Absolutely! I'd be happy to help you write a Python function. What should the function do?"
                    },
                    "reasoning": "Enthusiastic offer to help with programming",
                    "priority": 9
                }
            ],
            "selected_actions": [
                {
                    "action_type": "send_matrix_reply",
                    "parameters": {
                        "channel_id": channel_id, 
                        "reply_to_id": "$event3",
                        "content": "Absolutely! I'd be happy to help you write a Python function. What should the function do?"
                    }
                }
            ],
            "reasoning": "Programming help is definitely within my capabilities"
        }
        
        assistant_message2 = {
            "content": json.dumps(ai_response2),
            "event_id": "$event4", 
            "timestamp": time.time()
        }
        await context_manager.add_assistant_message(channel_id, assistant_message2)
        
        print()
        
        # ===== SHOW RESULTS =====
        print("📊 SYSTEM STATUS")
        print("=" * 50)
        
        # Get context summary
        summary = await context_manager.get_context_summary(channel_id)
        print(f"💬 Messages: {summary['user_message_count']} user, {summary['assistant_message_count']} assistant")
        
        # Get state changes
        state_changes = await context_manager.get_state_changes(channel_id=channel_id)
        print(f"📋 State changes: {len(state_changes)} total")
        
        # Show state change types
        change_types = {}
        for change in state_changes:
            change_types[change.change_type] = change_types.get(change.change_type, 0) + 1
        
        for change_type, count in change_types.items():
            print(f"   - {change_type}: {count}")
        
        print()
        
        # Get conversation messages (what would be sent to AI)
        messages = await context_manager.get_conversation_messages(channel_id)
        print(f"🔄 Conversation messages for AI: {len(messages)}")
        
        # Show system prompt preview
        system_msg = next((msg for msg in messages if msg['role'] == 'system'), None)
        if system_msg:
            preview = system_msg['content'][:200] + "..."
            print(f"📋 System prompt preview: {preview}")
        
        print()
        
        # Export training data
        export_path = "demo_training_data.jsonl"
        exported = await context_manager.export_state_changes_for_training(export_path)
        print(f"💾 Exported training data to: {exported}")
        
        # Show sample state change
        if state_changes:
            print("\n📄 Sample State Change:")
            sample = state_changes[0]
            print(f"   Type: {sample.change_type}")
            print(f"   Source: {sample.source}")
            if sample.observations:
                print(f"   Observations: {sample.observations[:100]}...")
            if sample.selected_actions:
                print(f"   Selected Actions: {len(sample.selected_actions)}")
        
        print("\n✅ Demo completed successfully!")
        print("\nKey Features Demonstrated:")
        print("- ✓ Evolving world state in system prompt")
        print("- ✓ Structured AI responses with observations/actions/reasoning")
        print("- ✓ Permanent storage of all state changes")
        print("- ✓ Context management separating conversation from world state") 
        print("- ✓ Training data export for future ML")
        print("- ✓ Tool execution tracking")
        
    except Exception as e:
        print(f"❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Cleanup
        import os
        try:
            os.unlink(db_path)
            if Path(export_path).exists():
                os.unlink(export_path)
        except:
            pass

if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(level=logging.INFO)
    
    asyncio.run(demo_context_system())
