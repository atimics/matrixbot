#!/usr/bin/env python3
"""
Test suite for WorldState AI integration improvements.
Validates fixes for:
1. AI blindness to its own recent messages in channel context
2. Rate limit information visibility to AI
3. Action history filtering improvements
"""

import pytest
import time
from unittest.mock import Mock
from chatbot.core.world_state import WorldState, WorldStateManager, Message, Channel, ActionHistory


class TestWorldStateAIImprovements:
    """Test suite for AI integration improvements"""

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

    def test_bot_messages_filtered_from_ai_context(self):
        """Test that bot's own messages are currently filtered from AI context"""
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
        
        # Check that bot message is filtered out
        channel_data = ai_payload["channels"][self.channel_id]
        message_contents = [msg["content"] for msg in channel_data["recent_messages"]]
        
        assert "Hello from user" in message_contents
        assert "Hello from bot" not in message_contents
        
        # Verify bot message exists in world state but not in AI payload
        all_messages = self.world_state.channels[self.channel_id].recent_messages
        all_contents = [msg.content for msg in all_messages]
        assert "Hello from bot" in all_contents
        assert len(all_messages) == 2
        assert len(channel_data["recent_messages"]) == 1

    def test_rate_limits_not_in_system_status(self):
        """Test that rate_limits are currently not included in system_status for AI"""
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
        
        # Check that rate_limits are not in system_status
        system_status = ai_payload["system_status"]
        assert "rate_limits" not in system_status
        assert system_status["matrix_connected"] is True
        assert system_status["farcaster_connected"] is True

    def test_action_history_filtering_logic(self):
        """Test the current action history filtering behavior"""
        # Create actions with different sender configurations
        action_with_bot_sender = ActionHistory(
            action_type="test_action",
            parameters={"sender": self.bot_username, "message": "test"},
            result="success",
            timestamp=time.time()
        )
        
        action_with_matrix_sender = ActionHistory(
            action_type="test_action", 
            parameters={"sender": "matrix_user_id", "message": "test"},
            result="success",
            timestamp=time.time()
        )
        
        action_without_sender = ActionHistory(
            action_type="test_action",
            parameters={"message": "test"},
            result="success",
            timestamp=time.time()
        )
        
        # Add actions to world state
        self.world_state.action_history.extend([
            action_with_bot_sender,
            action_with_matrix_sender, 
            action_without_sender
        ])
        
        # Mock settings for matrix user ID
        import chatbot.core.world_state as ws_module
        original_settings = getattr(ws_module, 'settings', None)
        ws_module.settings = Mock()
        ws_module.settings.MATRIX_USER_ID = "matrix_user_id"
        
        try:
            # Get AI payload
            ai_payload = self.world_state.to_dict_for_ai(
                primary_channel_id=self.channel_id,
                bot_fid=self.bot_fid,
                bot_username=self.bot_username
            )
            
            # Check action history filtering
            action_history = ai_payload["action_history"]
            
            # Should only include action without sender
            assert len(action_history) == 1
            assert action_history[0]["parameters"]["message"] == "test"
            assert "sender" not in action_history[0]["parameters"]
            
        finally:
            # Restore original settings
            if original_settings:
                ws_module.settings = original_settings
            else:
                delattr(ws_module, 'settings')

    def test_bot_identity_in_payload_stats(self):
        """Test that bot identity is included in payload stats"""
        ai_payload = self.world_state.to_dict_for_ai(
            primary_channel_id=self.channel_id,
            bot_fid=self.bot_fid,
            bot_username=self.bot_username
        )
        
        payload_stats = ai_payload["payload_stats"]
        bot_identity = payload_stats["bot_identity"]
        
        assert bot_identity["fid"] == self.bot_fid
        assert bot_identity["username"] == self.bot_username


if __name__ == "__main__":
    # Run tests
    test_suite = TestWorldStateAIImprovements()
    test_suite.setup_method()
    
    print("Testing current behavior...")
    
    try:
        test_suite.test_bot_messages_filtered_from_ai_context()
        print("✓ Bot messages are filtered from AI context (current behavior)")
    except AssertionError as e:
        print(f"✗ Bot message filtering test failed: {e}")
    
    try:
        test_suite.test_rate_limits_not_in_system_status()
        print("✓ Rate limits are not in system_status for AI (current behavior)")
    except AssertionError as e:
        print(f"✗ Rate limits test failed: {e}")
    
    try:
        test_suite.test_action_history_filtering_logic()
        print("✓ Action history filtering works as expected (current behavior)")
    except AssertionError as e:
        print(f"✗ Action history filtering test failed: {e}")
    
    try:
        test_suite.test_bot_identity_in_payload_stats()
        print("✓ Bot identity is included in payload stats")
    except AssertionError as e:
        print(f"✗ Bot identity test failed: {e}")
    
    print("\nNow implementing improvements...")
