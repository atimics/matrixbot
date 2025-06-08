"""
Tests to increase coverage for the world_state module.
Focused on testing actual functionality that exists.
"""
import pytest
import json
import time
from unittest.mock import Mock, patch, MagicMock
from chatbot.core.world_state import (
    WorldState, 
    WorldStateManager, 
    Message, 
    Channel, 
    ActionHistory
)


class TestWorldStateCoverage:
    """Tests to increase world state coverage"""

    def test_world_state_initialization(self):
        """Test WorldState initialization"""
        ws = WorldState()
        assert ws.channels == {}
        assert ws.seen_messages == set()
        assert ws.action_history == []
        assert ws.last_update is not None
        assert ws.rate_limits == {}
        assert ws.pending_invites == []
        assert ws.user_details == {}
        assert ws.bot_media == {}

    def test_world_state_add_message_basic(self):
        """Test basic message addition"""
        ws = WorldState()
        
        message = Message(
            id="test_msg",
            channel_id="test_channel",
            channel_type="matrix",
            sender="test_user",
            content="Test message",
            timestamp=time.time()
        )
        
        ws.add_message(message)
        assert "test_msg" in ws.seen_messages
        assert "test_channel" in ws.channels

    def test_world_state_get_recent_messages(self):
        """Test getting recent messages"""
        ws = WorldState()
        
        # Add channel first
        channel = Channel(
            id="test_channel",
            type="matrix", 
            name="Test Channel",
            recent_messages=[],
            last_checked=time.time()
        )
        ws.channels["test_channel"] = channel
        
        # Add message
        message = Message(
            id="msg1",
            channel_id="test_channel",
            channel_type="matrix",
            sender="user1",
            content="Hello",
            timestamp=time.time()
        )
        
        ws.add_message(message)
        messages = ws.get_recent_messages("test_channel", limit=5)
        assert len(messages) == 1
        assert messages[0].content == "Hello"

    def test_world_state_has_replied_logic(self):
        """Test has_replied_to_cast logic"""
        ws = WorldState()
        
        # Test non-existent cast
        assert not ws.has_replied_to_cast("nonexistent")
        
        # Add action history
        action = ActionHistory(
            action_type="send_farcaster_reply",
            parameters={"reply_to_hash": "test_cast"},
            result="success",
            timestamp=time.time()
        )
        ws.action_history.append(action)
        
        # Now should return True
        assert ws.has_replied_to_cast("test_cast")

    def test_world_state_to_dict(self):
        """Test to_dict functionality"""
        ws = WorldState()
        
        # Add some data
        channel = Channel(
            id="test_ch",
            type="matrix",
            name="Test",
            recent_messages=[],
            last_checked=time.time()
        )
        ws.channels["test_ch"] = channel
        
        result = ws.to_dict()
        assert "channels" in result
        assert "action_history" in result
        assert "last_update" in result
        assert "rate_limits" in result
        assert "pending_invites" in result

    def test_world_state_to_dict_for_ai(self):
        """Test to_dict_for_ai functionality"""
        ws = WorldState()
        
        # Add data
        message = Message(
            id="msg1",
            channel_id="test_channel",
            channel_type="matrix",
            sender="user1", 
            content="Hello",
            timestamp=time.time()
        )
        ws.add_message(message)
        
        result = ws.to_dict_for_ai()
        assert "channels" in result
        assert isinstance(result, dict)

    def test_world_state_to_dict_for_ai_with_limit(self):
        """Test to_dict_for_ai with message limit"""
        ws = WorldState()
        
        # Add channel
        channel = Channel(
            id="test_channel",
            type="matrix",
            name="Test",
            recent_messages=[],
            last_checked=time.time()
        )
        ws.channels["test_channel"] = channel
        
        # Add multiple messages
        for i in range(5):
            message = Message(
                id=f"msg{i}",
                channel_id="test_channel",
                channel_type="matrix",
                sender=f"user{i}",
                content=f"Message {i}",
                timestamp=time.time() + i
            )
            ws.add_message(message)
        
        result = ws.to_dict_for_ai(message_limit_per_channel=2)
        channel_data = result["channels"]["test_channel"]
        assert len(channel_data["recent_messages"]) <= 2

    def test_world_state_add_action(self):
        """Test action history addition"""
        ws = WorldState()
        
        action = ActionHistory(
            action_type="test_action",
            parameters={"key": "value"},
            result="success",
            timestamp=time.time()
        )
        
        ws.add_action(action)
        assert len(ws.action_history) == 1
        assert ws.action_history[0].action_type == "test_action"

    def test_world_state_add_action_with_limit(self):
        """Test action history with limit"""
        ws = WorldState()
        
        # Add many actions to test limit
        for i in range(15):  # More than default limit of 10
            action = ActionHistory(
                action_type=f"action_{i}",
                parameters={},
                result="success",
                timestamp=time.time() + i
            )
            ws.add_action(action)
        
        # Should be limited to 10
        assert len(ws.action_history) == 10
        # Should keep the most recent ones
        assert ws.action_history[-1].action_type == "action_14"

    def test_world_state_get_all_messages(self):
        """Test get_all_messages functionality"""
        ws = WorldState()
        
        # Add messages to multiple channels
        for ch in ["ch1", "ch2"]:
            channel = Channel(
                id=ch,
                type="matrix",
                name=f"Channel {ch}",
                recent_messages=[],
                last_checked=time.time()
            )
            ws.channels[ch] = channel
            
            message = Message(
                id=f"msg_{ch}",
                channel_id=ch,
                channel_type="matrix",
                sender="user",
                content=f"Message in {ch}",
                timestamp=time.time()
            )
            ws.add_message(message)
        
        all_messages = ws.get_all_messages()
        assert len(all_messages) == 2
        channel_ids = [msg.channel_id for msg in all_messages]
        assert "ch1" in channel_ids
        assert "ch2" in channel_ids

    def test_world_state_get_observation_data(self):
        """Test get_observation_data functionality"""
        ws = WorldState()
        
        # Add some data
        message = Message(
            id="obs_msg",
            channel_id="obs_ch",
            channel_type="matrix",
            sender="observer",
            content="Observation test",
            timestamp=time.time()
        )
        ws.add_message(message)
        
        obs_data = ws.get_observation_data()
        assert "channels" in obs_data
        assert "action_history" in obs_data

    def test_world_state_manager_initialization(self):
        """Test WorldStateManager initialization"""
        manager = WorldStateManager()
        assert manager.world_state is not None
        assert isinstance(manager.world_state, WorldState)

    def test_world_state_manager_add_channel(self):
        """Test WorldStateManager add_channel"""
        manager = WorldStateManager()
        
        channel = Channel(
            id="mgr_channel",
            type="farcaster",
            name="Manager Channel",
            recent_messages=[],
            last_checked=time.time()
        )
        
        manager.add_channel(channel)
        assert "mgr_channel" in manager.world_state.channels
        assert manager.world_state.channels["mgr_channel"].type == "farcaster"

    def test_world_state_manager_add_message(self):
        """Test WorldStateManager add_message"""
        manager = WorldStateManager()
        
        # Add channel first
        channel = Channel(
            id="mgr_ch",
            type="matrix",
            name="Manager Channel",
            recent_messages=[],
            last_checked=time.time()
        )
        manager.add_channel(channel)
        
        # Create message data
        message_data = {
            "id": "mgr_msg",
            "channel_id": "mgr_ch",
            "channel_type": "matrix",
            "sender": "manager",
            "content": "Manager message",
            "timestamp": time.time()
        }
        
        message = Message(**message_data)
        manager.add_message(message_data, message)
        
        assert "mgr_msg" in manager.world_state.seen_messages

    def test_message_dataclass_creation(self):
        """Test Message dataclass creation and methods"""
        msg = Message(
            id="test_id",
            channel_id="test_channel",
            channel_type="matrix",
            sender="test_sender",
            content="Test content",
            timestamp=time.time()
        )
        
        assert msg.id == "test_id"
        assert msg.channel_id == "test_channel"
        assert msg.channel_type == "matrix"
        assert msg.sender == "test_sender"
        assert msg.content == "Test content"

    def test_message_with_images(self):
        """Test Message with image URLs"""
        msg = Message(
            id="img_msg",
            channel_id="img_channel",
            channel_type="matrix",
            sender="img_sender",
            content="Image message",
            timestamp=time.time(),
            image_urls=["http://example.com/image.jpg"]
        )
        
        assert len(msg.image_urls) == 1
        assert "http://example.com/image.jpg" in msg.image_urls

    def test_message_with_metadata(self):
        """Test Message with metadata"""
        msg = Message(
            id="meta_msg",
            channel_id="meta_channel", 
            channel_type="farcaster",
            sender="meta_sender",
            content="Meta message",
            timestamp=time.time(),
            metadata={"power_badge": True, "verified": True}
        )
        
        assert msg.metadata["power_badge"] is True
        assert msg.metadata["verified"] is True

    def test_message_reply_functionality(self):
        """Test Message reply functionality"""
        msg = Message(
            id="reply_msg",
            channel_id="reply_channel",
            channel_type="matrix",
            sender="replier",
            content="This is a reply",
            timestamp=time.time(),
            reply_to="original_msg"
        )
        
        assert msg.reply_to == "original_msg"

    def test_channel_dataclass_creation(self):
        """Test Channel dataclass creation"""
        channel = Channel(
            id="test_channel_id",
            type="matrix",
            name="Test Channel Name",
            recent_messages=[],
            last_checked=time.time()
        )
        
        assert channel.id == "test_channel_id"
        assert channel.type == "matrix"
        assert channel.name == "Test Channel Name"
        assert channel.recent_messages == []

    def test_channel_with_matrix_metadata(self):
        """Test Channel with Matrix-specific metadata"""
        channel = Channel(
            id="matrix_room",
            type="matrix",
            name="Matrix Room",
            recent_messages=[],
            last_checked=time.time(),
            canonical_alias="#test:example.com",
            topic="Test room topic",
            encrypted=True,
            public=False
        )
        
        assert channel.canonical_alias == "#test:example.com"
        assert channel.topic == "Test room topic"
        assert channel.encrypted is True
        assert channel.public is False

    def test_action_history_dataclass(self):
        """Test ActionHistory dataclass"""
        action = ActionHistory(
            action_type="test_action",
            parameters={"param1": "value1"},
            result="success",
            timestamp=time.time()
        )
        
        assert action.action_type == "test_action"
        assert action.parameters["param1"] == "value1"
        assert action.result == "success"
        assert isinstance(action.timestamp, float)

    def test_world_state_json_serialization(self):
        """Test JSON serialization of WorldState"""
        ws = WorldState()
        
        # Add some data
        message = Message(
            id="json_msg",
            channel_id="json_channel",
            channel_type="matrix",
            sender="json_user",
            content="JSON test",
            timestamp=time.time()
        )
        ws.add_message(message)
        
        # Test to_json method
        json_str = ws.to_json()
        assert isinstance(json_str, str)
        
        # Verify it's valid JSON
        data = json.loads(json_str)
        assert "channels" in data
        assert "action_history" in data

    def test_world_state_manager_serialization(self):
        """Test WorldStateManager serialization methods"""
        manager = WorldStateManager()
        
        # Add some data
        channel = Channel(
            id="ser_channel",
            type="matrix",
            name="Serialization Channel",
            recent_messages=[],
            last_checked=time.time()
        )
        manager.add_channel(channel)
        
        # Test to_json
        json_str = manager.to_json()
        assert isinstance(json_str, str)
        
        # Test to_dict
        dict_data = manager.to_dict()
        assert isinstance(dict_data, dict)
        assert "channels" in dict_data
