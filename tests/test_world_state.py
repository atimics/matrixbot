"""
Comprehensive tests for world state management functionality.
Combines comprehensive and extended test coverage in a single file.
"""
import time
from chatbot.core.world_state import WorldStateManager, Message


class TestWorldStateBasic:
    """Basic tests for world state functionality."""
    
    def test_add_multiple_channels(self):
        """Test adding multiple channels of different types."""
        world_state = WorldStateManager()
        
        # Add Matrix channel
        world_state.add_channel("matrix_room_1", "matrix", "General Discussion")
        
        # Add Farcaster channel  
        world_state.add_channel("farcaster_ch_1", "farcaster", "Crypto Talk")
        
        state_dict = world_state.to_dict()
        
        assert "matrix_room_1" in state_dict["channels"]
        assert "farcaster_ch_1" in state_dict["channels"]
        assert state_dict["channels"]["matrix_room_1"]["type"] == "matrix"
        assert state_dict["channels"]["farcaster_ch_1"]["type"] == "farcaster"
    
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
        assert len(messages) <= 50
        
        # Should be ordered by timestamp (the messages are stored in the order they were added)
        # Since we added them with incrementing timestamps, they should be in chronological order
        timestamps = [msg["timestamp"] for msg in messages]
        assert timestamps == sorted(timestamps)  # Should be in chronological order (oldest first)
    
    def test_channel_creation_and_retrieval(self):
        """Test channel creation and data retrieval."""
        world_state = WorldStateManager()
        
        world_state.add_channel("test_room", "matrix", "Test Room")
        
        state_dict = world_state.to_dict()
        channel = state_dict["channels"]["test_room"]
        
        assert channel["id"] == "test_room"
        assert channel["type"] == "matrix"
        assert channel["name"] == "Test Room"
        assert "recent_messages" in channel
    
    def test_message_deduplication_across_channels(self):
        """Test message deduplication works across different channels."""
        world_state = WorldStateManager()
        
        # Add two channels
        world_state.add_channel("channel1", "matrix", "Channel 1")
        world_state.add_channel("channel2", "matrix", "Channel 2")
        
        # Same message ID in different channels
        message1 = Message(
            id="same_id",
            content="Message in channel 1",
            sender="user1",
            timestamp=time.time(),
            channel_id="channel1",
            channel_type="matrix"
        )
        
        message2 = Message(
            id="same_id",  # Same ID
            content="Message in channel 2", 
            sender="user1",
            timestamp=time.time(),
            channel_id="channel2",
            channel_type="matrix"
        )
        
        world_state.add_message("channel1", message1)
        world_state.add_message("channel2", message2)
        
        state_dict = world_state.to_dict()
        
        # Should only have one of these messages due to deduplication
        total_messages = 0
        for channel in state_dict["channels"].values():
            total_messages += len(channel["recent_messages"])
        
        assert total_messages == 1


class TestWorldStateAdvanced:
    """Advanced tests for world state functionality."""
    
    def test_world_state_deduplication(self):
        """Test message deduplication functionality"""
        world_state_manager = WorldStateManager()
        
        # Add a message
        message1 = Message(
            id="msg1",
            sender="user1",
            content="Hello",
            timestamp=time.time(),
            channel_type="matrix"
        )
        
        # First add should succeed
        world_state_manager.add_message("test_channel", message1)
        state_dict = world_state_manager.to_dict()
        assert len(state_dict["channels"]) >= 1
        
        # Duplicate message should be deduplicated
        message2 = Message(
            id="msg1",
            sender="user1", 
            content="Hello duplicate",
            timestamp=time.time(),
            channel_type="matrix"
        )
        
        initial_message_count = sum(len(ch["recent_messages"]) for ch in state_dict["channels"].values())
        world_state_manager.add_message("test_channel", message2)
        
        new_state_dict = world_state_manager.to_dict()
        final_message_count = sum(len(ch["recent_messages"]) for ch in new_state_dict["channels"].values())
        
        # Should not have increased due to deduplication
        assert final_message_count == initial_message_count

    def test_world_state_action_history_tracking(self):
        """Test action history tracking"""
        world_state_manager = WorldStateManager()
        
        # Add action to history using the proper format
        action_data = {
            "action_type": "send_message",
            "timestamp": time.time(),
            "parameters": {"content": "Test message"},
            "result": "success"
        }
        
        world_state_manager.add_action_history(action_data)
        state_dict = world_state_manager.to_dict()
        
        assert "action_history" in state_dict
        assert len(state_dict["action_history"]) >= 1
        assert state_dict["action_history"][0]["action_type"] == "send_message"
    
    def test_world_state_serialization_comprehensive(self):
        """Test comprehensive serialization of world state"""
        world_state_manager = WorldStateManager()
        
        # Add various types of data
        message = Message(
            id="test_msg",
            sender="user1", 
            content="Test content",
            timestamp=time.time(),
            channel_type="matrix"
        )
        world_state_manager.add_message("test_channel", message)
        
        # Add action history using the proper format
        action_data = {
            "action_type": "test_action",
            "timestamp": time.time(),
            "parameters": {},
            "result": "completed"
        }
        world_state_manager.add_action_history(action_data)
        
        # Serialize to dict
        serialized = world_state_manager.to_dict()
        
        # Should contain all major components
        assert "channels" in serialized
        assert "action_history" in serialized
        
        # Should be JSON serializable
        import json
        json_str = json.dumps(serialized)
        assert isinstance(json_str, str)
    
    def test_world_state_concurrent_operations(self):
        """Test concurrent operations on world state"""
        world_state_manager = WorldStateManager()
        
        # Simulate concurrent message additions
        messages = []
        for i in range(10):
            message = Message(
                id=f"concurrent_msg_{i}",
                sender=f"user_{i}",
                content=f"Concurrent message {i}",
                timestamp=time.time() + i,
                channel_type="matrix"
            )
            messages.append(message)
        
        # Add all messages
        for message in messages:
            world_state_manager.add_message("concurrent_channel", message)
        
        state_dict = world_state_manager.to_dict()
        
        # Should have all unique messages
        total_messages = sum(len(ch["recent_messages"]) for ch in state_dict["channels"].values())
        assert total_messages == 10
        assert len(state_dict["channels"]) >= 1
    
    def test_world_state_memory_efficiency(self):
        """Test memory efficiency with large datasets"""
        world_state_manager = WorldStateManager()
        
        # Add many messages to test memory limits
        for i in range(200):  # More than typical limits
            message = Message(
                id=f"memory_test_msg_{i}",
                sender=f"user_{i % 20}",  # Cycle through users
                content=f"Memory test message {i}" * 10,  # Longer content
                timestamp=time.time() + i,
                channel_type="matrix"
            )
            world_state_manager.add_message("memory_test_channel", message)
        
        state_dict = world_state_manager.to_dict()
        
        # Should maintain reasonable limits
        total_messages = sum(len(ch["recent_messages"]) for ch in state_dict["channels"].values())
        assert total_messages <= 100  # Should limit total messages
        
        # Should maintain recent messages (by timestamp in chronological order)
        for channel in state_dict["channels"].values():
            if len(channel["recent_messages"]) > 1:
                timestamps = [msg["timestamp"] for msg in channel["recent_messages"]]
                assert timestamps == sorted(timestamps)  # Chronological order
    
    def test_world_state_different_platforms(self):
        """Test handling messages from different platforms"""
        world_state_manager = WorldStateManager()
        
        # Add Matrix message
        matrix_msg = Message(
            id="matrix_msg_1",
            sender="@user:matrix.org",
            content="Hello from Matrix",
            timestamp=time.time(),
            channel_type="matrix"
        )
        world_state_manager.add_message("matrix_channel", matrix_msg)
        
        # Add Farcaster message
        farcaster_msg = Message(
            id="farcaster_msg_1",
            sender="farcasteruser",
            content="Hello from Farcaster",
            timestamp=time.time(),
            channel_type="farcaster",
            sender_fid=12345
        )
        world_state_manager.add_message("farcaster_channel", farcaster_msg)
        
        state_dict = world_state_manager.to_dict()
        
        # Should have both channels
        assert len(state_dict["channels"]) == 2
        
        # Verify platform-specific data is preserved
        matrix_channel = None
        farcaster_channel = None
        
        for channel in state_dict["channels"].values():
            if channel["type"] == "matrix":
                matrix_channel = channel
            elif channel["type"] == "farcaster":
                farcaster_channel = channel
        
        assert matrix_channel is not None
        assert farcaster_channel is not None
        
        # Check Farcaster-specific data
        farcaster_message = farcaster_channel["recent_messages"][0]
        assert farcaster_message.get("sender_fid") == 12345
