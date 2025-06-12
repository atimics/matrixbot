"""
Tests for world state management functionality.
"""
import pytest
import time
from chatbot.core.world_state import WorldStateManager, Message, Channel, ActionHistory


class TestWorldStateExtended:
    """Extended tests for the world state management functionality."""
    
    def test_add_multiple_channels(self):
        """Test adding multiple channels of different types."""
        world_state = WorldStateManager()
        
        # Add Matrix channel
        world_state.add_channel("matrix_room_1", "matrix", "General Discussion")
        
        # Add Farcaster channel  
        world_state.add_channel("farcaster_ch_1", "farcaster", "Crypto Talk")
        
        state_dict = world_state.to_dict()
        
        # Check nested structure: channels[platform][channel_id]
        assert "matrix" in state_dict["channels"]
        assert "farcaster" in state_dict["channels"]
        assert "matrix_room_1" in state_dict["channels"]["matrix"]
        assert "farcaster_ch_1" in state_dict["channels"]["farcaster"]
        assert state_dict["channels"]["matrix"]["matrix_room_1"]["type"] == "matrix"
        assert state_dict["channels"]["farcaster"]["farcaster_ch_1"]["type"] == "farcaster"
    
    def test_message_ordering_and_limits(self):
        """Test that messages are ordered by timestamp and limited."""
        world_state = WorldStateManager()
        channel_id = "test_channel"
        world_state.add_channel(channel_id, "matrix", "Test Channel")
        
        # Add many messages
        for i in range(60):  # More than the 50 message limit
            message = Message(
                id=f"msg_{i}",
                content=f"Message {i}",
                sender=f"@user{i}:example.com",
                timestamp=time.time() + i,  # Incrementing timestamps
                channel_id=channel_id,
                channel_type="matrix"
            )
            world_state.add_message(channel_id, message)
        
        state_dict = world_state.to_dict()
        messages = state_dict["channels"][channel_id]["recent_messages"]
        
        # Should be limited to 50 messages
        assert len(messages) == 50
        
        # Should contain the most recent messages (50-59)
        assert messages[-1]["content"] == "Message 59"
        assert messages[0]["content"] == "Message 10"  # First kept message
    
    def test_action_history_tracking(self):
        """Test action history tracking and limits."""
        world_state = WorldStateManager()
        
        # Add many actions
        for i in range(120):  # More than the 100 action limit
            world_state.add_action_result(
                action_type="test_action",
                parameters={"test_param": f"value_{i}"},
                result=f"Result {i}"
            )
        
        state_dict = world_state.to_dict()
        actions = state_dict["action_history"]
        
        # Should be limited to 100 actions
        assert len(actions) == 100
        
        # Should contain the most recent actions
        assert actions[-1]["result"] == "Result 119"
        assert actions[0]["result"] == "Result 20"  # First kept action
    
    def test_system_status_updates(self):
        """Test system status tracking."""
        world_state = WorldStateManager()
        
        # Update various system status items
        world_state.update_system_status({
            "matrix_connected": True,
            "farcaster_connected": False,
            "last_decision_time": time.time(),
            "error_count": 0
        })
        
        state_dict = world_state.to_dict()
        
        assert state_dict["system_status"]["matrix_connected"] is True
        assert state_dict["system_status"]["farcaster_connected"] is False
        assert "last_decision_time" in state_dict["system_status"]
        assert state_dict["system_status"]["error_count"] == 0
    
    def test_get_observation_data(self):
        """Test getting observation data for AI."""
        world_state = WorldStateManager()
        
        # Add some channels and messages
        world_state.add_channel("ch1", "matrix", "Channel 1")
        
        message = Message(
            id="msg_1",
            content="Recent message",
            sender="@user:example.com",
            timestamp=time.time(),
            channel_id="ch1",
            channel_type="matrix"
        )
        world_state.add_message("ch1", message)
        
        # Add an action
        world_state.add_action_result(
            action_type="send_reply",
            parameters={"content": "Hello"},
            result="Success"
        )
        
        # Get observation
        observation = world_state.get_observation_data(lookback_seconds=600)
        
        assert "recent_messages" in observation
        assert "recent_actions" in observation
        assert "system_status" in observation
        assert len(observation["recent_messages"]) >= 1
        assert len(observation["recent_actions"]) >= 1
    
    def test_get_all_messages(self):
        """Test getting all messages across channels."""
        world_state = WorldStateManager()
        
        # Add multiple channels with messages
        for channel_num in range(3):
            channel_id = f"channel_{channel_num}"
            world_state.add_channel(channel_id, "matrix", f"Channel {channel_num}")
            
            for msg_num in range(5):
                message = Message(
                    id=f"msg_{channel_num}_{msg_num}",
                    content=f"Message {msg_num} in channel {channel_num}",
                    sender=f"@user{msg_num}:example.com",
                    timestamp=time.time() + msg_num,
                    channel_id=channel_id,
                    channel_type="matrix"
                )
                world_state.add_message(channel_id, message)
        
        all_messages = world_state.get_all_messages()
        
        # Should have 15 total messages (3 channels × 5 messages)
        assert len(all_messages) == 15
        
        # Check that messages from all channels are included
        channel_ids = {msg.channel_id for msg in all_messages}
        assert channel_ids == {"channel_0", "channel_1", "channel_2"}
    
    def test_world_state_json_serialization(self):
        """Test JSON serialization of world state."""
        world_state = WorldStateManager()
        
        # Add some data
        world_state.add_channel("test_ch", "matrix", "Test Channel")
        message = Message(
            id="msg_1",
            content="Test message",
            sender="@user:example.com",
            timestamp=time.time(),
            channel_id="test_ch",
            channel_type="matrix"
        )
        world_state.add_message("test_ch", message)
        
        # Test JSON serialization
        json_str = world_state.to_json()
        
        assert isinstance(json_str, str)
        assert "test_ch" in json_str
        assert "Test message" in json_str
        
        # Test that it's valid JSON
        import json
        parsed = json.loads(json_str)
        assert "channels" in parsed
        assert "test_ch" in parsed["channels"]
    
    def test_auto_channel_creation(self):
        """Test automatic channel creation when adding messages."""
        world_state = WorldStateManager()
        
        # Add message to non-existent channel
        message = Message(
            id="msg_1",
            content="Message in auto-created channel",
            sender="@user:example.com",
            timestamp=time.time(),
            channel_id="auto_channel",
            channel_type="matrix"
        )
        
        world_state.add_message("auto_channel", message)
        
        state_dict = world_state.to_dict()
        
        # Channel should be auto-created
        assert "auto_channel" in state_dict["channels"]
        assert state_dict["channels"]["auto_channel"]["type"] == "matrix"
        assert len(state_dict["channels"]["auto_channel"]["recent_messages"]) == 1
    
    def test_timestamp_updates(self):
        """Test that last_update timestamp is maintained."""
        world_state = WorldStateManager()
        
        initial_time = world_state.to_dict()["last_update"]
        
        # Wait a small amount
        import time
        time.sleep(0.01)
        
        # Add something to update timestamp
        world_state.update_system_status({"test": "value"})
        
        updated_time = world_state.to_dict()["last_update"]
        
        assert updated_time > initial_time


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
