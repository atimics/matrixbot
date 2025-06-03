"""
Comprehensive tests for world state functionality to increase coverage.
"""
import pytest
import json
import time
from unittest.mock import Mock, patch, MagicMock
from chatbot.core.world_state import (
    WorldState, 
    WorldStateManager, 
    WorldStateData,
    Message,
    Channel,
    ActionHistory
)


class TestWorldStateComprehensive:
    """Comprehensive tests to increase world state coverage"""

    def test_world_state_deduplication(self):
        """Test message deduplication functionality"""
        world_state = WorldState()
        
        # Add a message
        message1 = Message(
            id="msg1",
            sender="user1",
            content="Hello",
            timestamp=time.time(),
            channel_type="matrix"
        )
        
        # First add should succeed
        world_state.add_message(message1)
        assert "msg1" in world_state.seen_messages
        assert len(world_state.channels) == 1
        
        # Duplicate message should be deduplicated
        message2 = Message(
            id="msg1",
            sender="user1", 
            content="Hello duplicate",
            timestamp=time.time(),
            channel_type="matrix"
        )
        
        world_state.add_message(message2)
        # Should still only have one message since it's a duplicate
        assert len(world_state.seen_messages) == 1

    def test_world_state_thread_management(self):
        """Test conversation thread management"""
        world_state = WorldState()
        
        # Root message
        root_msg = Message(
            id="root1",
            sender="user1",
            content="Root message",
            timestamp=time.time(),
            channel_type="farcaster"
        )
        world_state.add_message(root_msg)
        
        # Reply message
        reply_msg = Message(
            id="reply1",
            sender="user2",
            content="Reply to root",
            timestamp=time.time(),
            channel_type="farcaster",
            reply_to="root1"
        )
        world_state.add_message(reply_msg)
        
        # Check thread tracking
        assert "root1" in world_state.threads
        assert len(world_state.threads["root1"]) == 2
        assert reply_msg in world_state.threads["root1"]

    def test_world_state_rate_limits(self):
        """Test rate limiting functionality"""
        world_state = WorldState()
        
        # Set rate limits
        world_state.set_rate_limits("api_service", {
            "requests_per_minute": 60,
            "last_request": time.time(),
            "remaining": 59
        })
        
        assert "api_service" in world_state.rate_limits
        
        # Get rate limits
        limits = world_state.get_rate_limits("api_service")
        assert limits["requests_per_minute"] == 60

    def test_world_state_pending_invites(self):
        """Test pending invites management"""
        world_state = WorldState()
        
        invite = {
            "room_id": "!room:example.com",
            "sender": "@user:example.com",
            "timestamp": time.time()
        }
        
        world_state.add_pending_invite(invite)
        assert len(world_state.pending_matrix_invites) == 1
        
        # Remove invite
        world_state.remove_pending_invite("!room:example.com")
        assert len(world_state.pending_matrix_invites) == 0

    def test_world_state_bot_media_tracking(self):
        """Test bot media tracking for Farcaster"""
        world_state = WorldState()
        
        media_info = {
            "url": "https://example.com/image.jpg",
            "engagement_count": 5,
            "timestamp": time.time()
        }
        
        world_state.track_bot_media("cast123", media_info)
        assert "cast123" in world_state.bot_media_on_farcaster
        assert world_state.bot_media_on_farcaster["cast123"]["engagement_count"] == 5

    def test_world_state_cleanup_old_messages(self):
        """Test cleanup of old messages"""
        world_state = WorldStateData()
        world_state.add_channel("test_channel", "matrix", "Test Channel")
        
        # Add more than 50 messages to trigger cleanup
        for i in range(55):
            msg = Message(
                id=f"msg{i}",
                sender="user1",
                content=f"Message {i}",
                timestamp=time.time() - (55 - i),  # Older messages have lower timestamps
                channel_type="matrix",
                channel_id="test_channel"  # Ensure channel_id is set
            )
            world_state.add_message(msg)
        
        # Should keep only last 50 messages
        channel = world_state.channels["test_channel"]
        assert len(channel.recent_messages) == 50
        # Should have the most recent messages (msg5 to msg54)
        assert channel.recent_messages[0].id == "msg5"
        assert channel.recent_messages[-1].id == "msg54"

    def test_world_state_action_history_limits(self):
        """Test action history cleanup"""
        world_state = WorldState()
        
        # Add more than 100 actions
        for i in range(105):
            action_data = {
                "action_type": f"action_{i}",
                "parameters": {"param": i},
                "result": f"result_{i}",
                "timestamp": time.time()
            }
            world_state.add_action_history(action_data)
        
        # Should keep only last 100 actions
        assert len(world_state.action_history) == 100
        assert world_state.action_history[0].action_type == "action_5"
        assert world_state.action_history[-1].action_type == "action_104"

    def test_world_state_get_recent_activity(self):
        """Test recent activity retrieval"""
        world_state = WorldState()
        world_state.add_channel("test_channel", "matrix", "Test Channel")
        
        # Add recent message
        recent_msg = Message(
            id="recent",
            sender="user1",
            content="Recent message",
            timestamp=time.time(),
            channel_type="matrix"
        )
        world_state.add_message(recent_msg)
        
        # Add old message
        old_msg = Message(
            id="old",
            sender="user1", 
            content="Old message",
            timestamp=time.time() - 400,  # 400 seconds ago
            channel_type="matrix"
        )
        world_state.add_message(old_msg)
        
        # Get recent activity (last 300 seconds)
        activity = world_state.get_recent_activity(300)
        assert len(activity["recent_messages"]) == 1
        assert activity["recent_messages"][0]["id"] == "recent"

    def test_world_state_to_json(self):
        """Test JSON serialization"""
        world_state = WorldState()
        world_state.add_channel("test", "matrix", "Test")
        
        msg = Message(
            id="test_msg",
            sender="user1",
            content="Test message",
            timestamp=time.time(),
            channel_type="matrix"
        )
        world_state.add_message(msg)
        
        json_str = world_state.to_json()
        assert isinstance(json_str, str)
        
        # Should be valid JSON
        data = json.loads(json_str)
        assert "channels" in data
        assert "recent_activity" in data

    def test_world_state_to_dict_for_ai_with_filters(self):
        """Test AI-optimized dictionary conversion with filters"""
        world_state = WorldState()
        world_state.add_channel("test", "matrix", "Test")
        
        # Add message
        msg = Message(
            id="test_msg",
            sender="user1",
            content="Test message",
            timestamp=time.time(),
            channel_type="matrix"
        )
        world_state.add_message(msg)
        
        # Add action
        action_data = {
            "action_type": "test_action",
            "parameters": {"test": "value"},
            "result": "success",
            "timestamp": time.time()
        }
        world_state.add_action_history(action_data)
        
        # Test with filters
        ai_dict = world_state.to_dict_for_ai(
            include_channels=["test"],
            max_messages_per_channel=5,
            max_actions=10
        )
        
        assert "channels" in ai_dict
        assert "test" in ai_dict["channels"]
        assert len(ai_dict["action_history"]) <= 10


class TestWorldStateManager:
    """Test WorldStateManager functionality"""

    def test_world_state_manager_initialization(self):
        """Test WorldStateManager initialization"""
        manager = WorldStateManager()
        
        assert manager.state is not None
        assert isinstance(manager.state, WorldState)
        assert manager.state.system_status["matrix_connected"] is False
        assert manager.state.system_status["farcaster_connected"] is False

    def test_world_state_manager_add_channel(self):
        """Test adding channels through manager"""
        manager = WorldStateManager()
        
        manager.add_channel("test_channel", "matrix", "Test Channel", "active")
        
        assert "test_channel" in manager.state.channels
        channel = manager.state.channels["test_channel"]
        assert channel.name == "Test Channel"
        assert channel.channel_type == "matrix"
        assert channel.status == "active"

    def test_world_state_manager_add_message(self):
        """Test adding messages through manager"""
        manager = WorldStateManager()
        manager.add_channel("test_channel", "matrix", "Test Channel")
        
        message_data = {
            "id": "test_msg",
            "sender": "user1",
            "content": "Test message",
            "timestamp": time.time(),
            "channel_id": "test_channel",
            "channel_type": "matrix"
        }
        
        manager.add_message(message_data)
        
        channel = manager.state.channels["test_channel"]
        assert len(channel.recent_messages) == 1
        assert channel.recent_messages[0].content == "Test message"

    def test_world_state_manager_observation_data(self):
        """Test observation data generation"""
        manager = WorldStateManager()
        manager.add_channel("test", "matrix", "Test")
        
        message_data = {
            "id": "obs_msg",
            "sender": "user1",
            "content": "Observation message",
            "timestamp": time.time(),
            "channel_id": "test",
            "channel_type": "matrix"
        }
        manager.add_message(message_data)
        
        observation = manager.get_observation_data(["test"], 300)
        
        assert "channels" in observation
        assert "test" in observation["channels"]
        assert len(observation["channels"]["test"]["recent_messages"]) == 1

    def test_world_state_manager_has_replied_to_cast(self):
        """Test Farcaster reply tracking"""
        manager = WorldStateManager()
        
        # Should return False for unknown cast
        assert not manager.has_replied_to_cast("unknown_cast")
        
        # Add action history for a reply
        action_data = {
            "action_type": "send_farcaster_reply", 
            "parameters": {"cast_hash": "test_cast"},
            "result": "success",
            "timestamp": time.time()
        }
        manager.add_action_history(action_data)
        
        # Should now return True
        assert manager.has_replied_to_cast("test_cast")

    def test_world_state_manager_serialization(self):
        """Test manager serialization methods"""
        manager = WorldStateManager()
        manager.add_channel("test", "matrix", "Test")
        
        # Test to_json
        json_str = manager.to_json()
        assert isinstance(json_str, str)
        
        # Test to_dict
        dict_data = manager.to_dict()
        assert isinstance(dict_data, dict)
        assert "channels" in dict_data


class TestActionHistory:
    """Test ActionHistory functionality"""

    def test_action_history_creation(self):
        """Test action history creation"""
        action = ActionHistory(
            action_type="send_message",
            parameters={"content": "Hello"},
            result="success",
            timestamp=time.time()
        )
        
        assert action.action_type == "send_message"
        assert action.parameters["content"] == "Hello"
        assert action.result == "success"
        assert isinstance(action.timestamp, float)

    def test_action_history_serialization(self):
        """Test action history serialization"""
        from dataclasses import asdict
        
        action = ActionHistory(
            action_type="test_action",
            parameters={"key": "value"},
            result="completed",
            timestamp=123456789.0
        )
        
        action_dict = asdict(action)
        
        assert action_dict["action_type"] == "test_action"
        assert action_dict["parameters"]["key"] == "value"
        assert action_dict["result"] == "completed"
        assert action_dict["timestamp"] == 123456789.0


class TestMessage:
    """Test Message functionality"""

    def test_message_creation(self):
        """Test message creation"""
        msg = Message(
            id="msg1",
            sender="user1",
            content="Hello world",
            timestamp=time.time(),
            channel_type="matrix"
        )
        
        assert msg.id == "msg1"
        assert msg.sender == "user1"
        assert msg.content == "Hello world"
        assert msg.channel_type == "matrix"
        assert msg.reply_to is None
        assert msg.image_urls == []

    def test_message_with_images(self):
        """Test message with image URLs"""
        msg = Message(
            id="img_msg",
            sender="user1",
            content="Check this out",
            timestamp=time.time(),
            channel_type="matrix",
            image_urls=["https://example.com/image.jpg"]
        )
        
        assert len(msg.image_urls) == 1
        assert msg.image_urls[0] == "https://example.com/image.jpg"

    def test_message_reply(self):
        """Test reply message"""
        msg = Message(
            id="reply1",
            sender="user2",
            content="Reply message",
            timestamp=time.time(),
            channel_type="farcaster",
            reply_to="original_msg"
        )
        
        assert msg.reply_to == "original_msg"

    def test_message_serialization(self):
        """Test message serialization"""
        from dataclasses import asdict
        
        msg = Message(
            id="ser_msg",
            sender="user1",
            content="Serialize this",
            timestamp=123456789.0,
            channel_type="matrix",
            image_urls=["https://example.com/test.jpg"]
        )
        
        msg_dict = asdict(msg)
        
        assert msg_dict["id"] == "ser_msg"
        assert msg_dict["sender"] == "user1"
        assert msg_dict["content"] == "Serialize this"
        assert msg_dict["timestamp"] == 123456789.0
        assert msg_dict["channel_type"] == "matrix"
        assert msg_dict["image_urls"] == ["https://example.com/test.jpg"]


class TestChannel:
    """Test Channel functionality"""

    def test_channel_creation(self):
        """Test channel creation"""
        channel = Channel(
            id="test_channel",
            name="Test Channel",
            channel_type="matrix",
            status="active"
        )
        
        assert channel.id == "test_channel"
        assert channel.name == "Test Channel"
        assert channel.channel_type == "matrix"
        assert channel.status == "active"
        assert len(channel.recent_messages) == 0
        assert channel.last_checked is None

    def test_channel_update_timestamp(self):
        """Test channel timestamp updates"""
        channel = Channel(
            id="test_channel",
            name="Test Channel",
            channel_type="matrix"
        )
        
        current_time = time.time()
        channel.update_last_checked(current_time)
        
        assert channel.last_checked == current_time

    def test_channel_serialization(self):
        """Test channel serialization"""
        from dataclasses import asdict
        
        channel = Channel(
            id="ser_channel",
            name="Serializable Channel",
            channel_type="farcaster",
            status="active"
        )
        
        channel.update_last_checked(123456789.0)
        
        channel_dict = asdict(channel)
        
        assert channel_dict["id"] == "ser_channel"
        assert channel_dict["name"] == "Serializable Channel"
        assert channel_dict["channel_type"] == "farcaster"
        assert channel_dict["status"] == "active"
        assert channel_dict["last_checked"] == 123456789.0
