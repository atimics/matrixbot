#!/usr/bin/env python3
"""
Test script to verify the channel summary update functionality.
"""

import asyncio
import os
import tempfile
from pathlib import Path
import sys

# Add the current directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

from json_centric_orchestrator import JsonCentricOrchestrator
from event_definitions import BotDisplayNameReadyEvent
import database

async def test_channel_summary_update():
    """Test that channel summary updates work correctly."""
    print("Testing channel summary update functionality...")
    
    # Create a temporary database for testing
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp_db:
        test_db_path = tmp_db.name
    
    try:
        # Set database path for testing
        os.environ["DATABASE_PATH"] = test_db_path
        
        # Initialize the orchestrator
        orchestrator = JsonCentricOrchestrator()
        
        # Initialize the database
        await orchestrator.initialize_database()
        
        # Add a test channel to the database
        await database.ensure_channel_exists(
            test_db_path,
            channel_id="!test:example.com",
            channel_type="matrix",
            display_name="Test Channel"
        )
        
        # Add some test messages
        await database.add_channel_message(
            test_db_path,
            channel_id="!test:example.com",
            message_id="$msg1:example.com",
            message_type="text",
            sender_id="@user:example.com",
            sender_display_name="Test User",
            content="Hello, this is a test message",
            timestamp=1640995200000,  # 2022-01-01 00:00:00
            metadata={}
        )
        
        await database.add_channel_message(
            test_db_path,
            channel_id="!test:example.com",
            message_id="$msg2:example.com",
            message_type="text",
            sender_id="@user2:example.com", 
            sender_display_name="Test User 2",
            content="This is another test message for summary",
            timestamp=1640995260000,  # 2022-01-01 00:01:00
            metadata={}
        )
        
        print("✓ Test database and channel created")
        
        # Create a bot ready event
        bot_ready_event = BotDisplayNameReadyEvent(
            display_name="Test Bot",
            user_id="@bot:example.com"
        )
        
        # Track published events
        published_events = []
        original_publish = orchestrator.message_bus.publish
        
        async def mock_publish(event):
            published_events.append(event)
            print(f"📤 Event published: {event.event_type}")
            if hasattr(event, 'room_id'):
                print(f"   Room ID: {event.room_id}")
            if hasattr(event, 'force_update'):
                print(f"   Force update: {event.force_update}")
            # Call the original publish method
            await original_publish(event)
        
        orchestrator.message_bus.publish = mock_publish
        
        # Trigger the channel summary update
        try:
            await orchestrator._handle_bot_ready_for_summary_update(bot_ready_event)
        except Exception as e:
            print(f"Error during summary update: {e}")
            import traceback
            traceback.print_exc()
            raise
        
        print("✓ Channel summary update triggered")
        
        # Verify that a RequestAISummaryCommand was published
        summary_commands = [event for event in published_events 
                          if event.event_type == "request_ai_summary_command"]
        
        if summary_commands:
            print(f"✓ {len(summary_commands)} summary command(s) published")
            for cmd in summary_commands:
                print(f"   - Room: {cmd.room_id}, Force: {cmd.force_update}, Messages: {len(cmd.messages_to_summarize or [])}")
        else:
            print("❌ No summary commands published")
            return False
        
        print("✅ Test completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        # Clean up temporary database
        try:
            os.unlink(test_db_path)
        except:
            pass

async def main():
    """Main test runner."""
    success = await test_channel_summary_update()
    if success:
        print("\n🎉 All tests passed!")
        sys.exit(0)
    else:
        print("\n💥 Tests failed!")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
