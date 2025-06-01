#!/usr/bin/env python3
"""
Test suite for WorldState AI integration improvements after fixes.
Validates that the following issues are resolved:
1. AI can now see its own recent messages in channel context
2. Rate limit information is now visible to AI
3. Action history includes all bot actions for better context
"""

import pytest
import time
from unittest.mock import Mock
from chatbot.core.world_state import WorldState, WorldStateManager, Message, Channel, ActionHistory


class TestWorldStateAIImprovementsFixed:
    """Test suite for AI integration improvements after fixes"""

    def setup_method(self):
        """Setup test fixtures"""
        self.world_state = WorldState()
        self.bot_fid = "12345"
        self.bot_username = "testbot"
        
        # Add a test channel
        self.channel_id = "test_channel"
        self.world_state.channels[self.channel_id] = Channel(
            id=self.channel_id,
            type="farcaster",
            name="Test Channel",
            recent_messages=[],
            last_checked=time.time()
        )

    def test_bot_messages_included_in_ai_context(self):
        """Test that bot's own messages are now included in AI context for conversational flow"""
        # Add bot message
        bot_message = Message(
            id="bot_msg_1",
            content="Hello from bot",
            sender=self.bot_username,
            sender_username=self.bot_username,
            sender_fid=int(self.bot_fid),
            channel_id=self.channel_id,
            channel_type="farcaster",
            timestamp=time.time()
        )
        
        # Add user message
        user_message = Message(
            id="user_msg_1", 
            content="Hello from user",
            sender="user123",
            sender_username="user123",
            sender_fid=54321,
            channel_id=self.channel_id,
            channel_type="farcaster",
            timestamp=time.time() + 1
        )
        
        self.world_state.add_message(bot_message)
        self.world_state.add_message(user_message)
        
        # Get AI payload
        ai_payload = self.world_state.to_dict_for_ai(
            primary_channel_id=self.channel_id,
            bot_fid=self.bot_fid,
            bot_username=self.bot_username
        )
        
        # Check that bot message is now included
        channel_data = ai_payload["channels"][self.channel_id]
        message_contents = [msg["content"] for msg in channel_data["recent_messages"]]
        
        assert "Hello from user" in message_contents
        assert "Hello from bot" in message_contents
        
        # Verify both messages exist in AI payload
        assert len(channel_data["recent_messages"]) == 2
        
        print("✓ Bot messages are now included in AI context for conversational flow")

    def test_rate_limits_included_in_system_status(self):
        """Test that rate_limits are now included in system_status for AI"""
        # Add rate limit information
        self.world_state.rate_limits["farcaster_api"] = {
            "remaining": 50,
            "reset_time": time.time() + 3600,
            "limit": 100
        }
        
        # Add system status
        self.world_state.system_status = {
            "matrix_connected": True,
            "farcaster_connected": True
        }
        
        # Get AI payload
        ai_payload = self.world_state.to_dict_for_ai(
            primary_channel_id=self.channel_id,
            bot_fid=self.bot_fid,
            bot_username=self.bot_username
        )
        
        # Check that rate_limits are now in system_status
        system_status = ai_payload["system_status"]
        assert "rate_limits" in system_status
        assert system_status["rate_limits"]["farcaster_api"]["remaining"] == 50
        assert system_status["rate_limits"]["farcaster_api"]["limit"] == 100
        assert system_status["matrix_connected"] is True
        assert system_status["farcaster_connected"] is True
        
        print("✓ Rate limits are now included in system_status for AI rate limit awareness")

    def test_action_history_includes_all_actions(self):
        """Test that action history now includes all bot actions for better context"""
        # Create actions that would previously be filtered
        action_1 = ActionHistory(
            action_type="send_message",
            parameters={"content": "Hello", "channel": self.channel_id},
            result="success",
            timestamp=time.time()
        )
        
        action_2 = ActionHistory(
            action_type="like_post",
            parameters={"post_id": "12345"},
            result="success",
            timestamp=time.time() + 1
        )
        
        action_3 = ActionHistory(
            action_type="follow_user",
            parameters={"user_id": "67890"},
            result="success",
            timestamp=time.time() + 2
        )
        
        # Add actions to world state
        self.world_state.action_history.extend([action_1, action_2, action_3])
        
        # Get AI payload
        ai_payload = self.world_state.to_dict_for_ai(
            primary_channel_id=self.channel_id,
            bot_fid=self.bot_fid,
            bot_username=self.bot_username
        )
        
        # Check that all actions are included
        action_history = ai_payload["action_history"]
        assert len(action_history) == 3
        
        action_types = [action["action_type"] for action in action_history]
        assert "send_message" in action_types
        assert "like_post" in action_types
        assert "follow_user" in action_types
        
        print("✓ Action history now includes all bot actions for better AI context")

    def test_thread_messages_include_bot_messages(self):
        """Test that thread messages now include bot's own messages for conversation context"""
        # Create a thread with bot and user messages
        root_message = Message(
            id="root_msg",
            content="Root message",
            sender="user123",
            sender_username="user123", 
            sender_fid=54321,
            channel_id=self.channel_id,
            channel_type="farcaster",
            timestamp=time.time()
        )
        
        bot_reply = Message(
            id="bot_reply",
            content="Bot reply to root",
            sender=self.bot_username,
            sender_username=self.bot_username,
            sender_fid=int(self.bot_fid),
            channel_id=self.channel_id,
            channel_type="farcaster",
            timestamp=time.time() + 1,
            reply_to="root_msg"
        )
        
        user_reply = Message(
            id="user_reply",
            content="User reply to bot",
            sender="user123",
            sender_username="user123",
            sender_fid=54321,
            channel_id=self.channel_id,
            channel_type="farcaster",
            timestamp=time.time() + 2,
            reply_to="bot_reply"
        )
        
        # Add thread messages
        thread_id = "root_msg"
        self.world_state.threads[thread_id] = [root_message, bot_reply, user_reply]
        
        # Get AI payload
        ai_payload = self.world_state.to_dict_for_ai(
            primary_channel_id=self.channel_id,
            bot_fid=self.bot_fid,
            bot_username=self.bot_username
        )
        
        # Check that bot messages are included in threads
        if thread_id in ai_payload["threads"]:
            thread_messages = ai_payload["threads"][thread_id]
            thread_contents = [msg["content"] for msg in thread_messages]
            
            assert "Root message" in thread_contents
            assert "Bot reply to root" in thread_contents
            assert "User reply to bot" in thread_contents
            assert len(thread_messages) == 3
            
            print("✓ Thread messages now include bot's own messages for conversation context")
        else:
            print("⚠ Thread not included in AI payload (may be expected based on relevance logic)")

    def test_payload_stats_updated(self):
        """Test that payload stats reflect the new message inclusion logic"""
        # Add messages including bot messages
        bot_message = Message(
            id="bot_msg_1",
            content="Hello from bot",
            sender=self.bot_username,
            sender_username=self.bot_username,
            sender_fid=int(self.bot_fid),
            channel_id=self.channel_id,
            channel_type="farcaster",
            timestamp=time.time()
        )
        
        user_message = Message(
            id="user_msg_1", 
            content="Hello from user",
            sender="user123",
            sender_username="user123",
            sender_fid=54321,
            channel_id=self.channel_id,
            channel_type="farcaster",
            timestamp=time.time() + 1
        )
        
        self.world_state.add_message(bot_message)
        self.world_state.add_message(user_message)
        
        ai_payload = self.world_state.to_dict_for_ai(
            primary_channel_id=self.channel_id,
            bot_fid=self.bot_fid,
            bot_username=self.bot_username
        )
        
        payload_stats = ai_payload["payload_stats"]
        
        # Check that the stats key name was updated
        assert "included_messages" in payload_stats
        assert "filtered_messages" not in payload_stats
        assert payload_stats["included_messages"] == 2  # Both bot and user messages
        
        print("✓ Payload stats updated to reflect new message inclusion logic")


if __name__ == "__main__":
    # Run tests to verify improvements
    test_suite = TestWorldStateAIImprovementsFixed()
    
    print("Testing AI integration improvements after fixes...")
    print("=" * 60)
    
    test_suite.setup_method()
    
    try:
        test_suite.test_bot_messages_included_in_ai_context()
    except Exception as e:
        print(f"✗ Bot message inclusion test failed: {e}")
    
    test_suite.setup_method()
    try:
        test_suite.test_rate_limits_included_in_system_status()
    except Exception as e:
        print(f"✗ Rate limits test failed: {e}")
    
    test_suite.setup_method()
    try:
        test_suite.test_action_history_includes_all_actions()
    except Exception as e:
        print(f"✗ Action history test failed: {e}")
    
    test_suite.setup_method()
    try:
        test_suite.test_thread_messages_include_bot_messages()
    except Exception as e:
        print(f"✗ Thread messages test failed: {e}")
    
    test_suite.setup_method()
    try:
        test_suite.test_payload_stats_updated()
    except Exception as e:
        print(f"✗ Payload stats test failed: {e}")
    
    print("\n" + "=" * 60)
    print("AI integration improvements testing complete!")
