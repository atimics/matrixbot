#!/usr/bin/env python3
"""
Quick test script to verify thread turn validation logic.
"""

import time
from chatbot.core.world_state.manager import WorldStateManager
from chatbot.core.world_state.structures import Message


def test_turn_validation():
    """Test that thread turn validation works correctly."""
    
    # Create a WorldStateManager
    wsm = WorldStateManager()
    
    # Create test messages
    user_message = Message(
        id="test_msg_1",
        sender="testuser",
        content="Hello bot!",
        timestamp=time.time(),
        channel_id="test_channel",
        channel_type="farcaster",
        channel_name="Test Channel"
    )
    
    bot_message = Message(
        id="test_msg_2",
        sender="ratichat",  # This should match the bot username in config
        content="Hello user!",
        timestamp=time.time() + 1,
        channel_id="test_channel", 
        channel_type="farcaster",
        channel_name="Test Channel",
        reply_to="test_msg_1"
    )
    
    user_message2 = Message(
        id="test_msg_3",
        sender="testuser",
        content="How are you?",
        timestamp=time.time() + 2,
        channel_id="test_channel",
        channel_type="farcaster", 
        channel_name="Test Channel",
        reply_to="test_msg_1"
    )
    
    # Test 1: Add user message - should be bot's turn
    print("=== Test 1: User speaks first ===")
    wsm.add_message("test_channel", user_message)
    
    thread_id = user_message.id  # First message creates the thread
    print(f"Thread ID: {thread_id}")
    
    # Check if it's bot's turn
    is_bot_turn = wsm.is_bot_turn_in_thread(thread_id)
    print(f"Is bot's turn after user message: {is_bot_turn}")
    
    # Test 2: Add bot message - should NOT be bot's turn
    print("\n=== Test 2: Bot responds ===")
    wsm.add_message("test_channel", bot_message)
    
    is_bot_turn = wsm.is_bot_turn_in_thread(thread_id)
    print(f"Is bot's turn after bot response: {is_bot_turn}")
    
    # Test 3: Add another user message - should be bot's turn again
    print("\n=== Test 3: User speaks again ===")
    wsm.add_message("test_channel", user_message2)
    
    is_bot_turn = wsm.is_bot_turn_in_thread(thread_id)
    print(f"Is bot's turn after user speaks again: {is_bot_turn}")
    
    # Print thread state for debugging
    thread = wsm.state.threads.get(thread_id)
    if thread:
        print(f"\nThread state:")
        print(f"  Last speaker: {thread.last_speaker_id}")
        print(f"  Participants: {thread.participants}")
        print(f"  Message count: {thread.message_count}")
        print(f"  Platform: {thread.platform}")


if __name__ == "__main__":
    test_turn_validation()
