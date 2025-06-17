"""
Comprehensive Unit Tests for PayloadBuilder

Tests the AI payload construction logic with various scenarios,
focusing on edge cases and performance characteristics.
"""

import pytest
import time
from unittest.mock import Mock, patch
from typing import Dict, Any

from chatbot.core.world_state import WorldStateManager, WorldStateData, Message, Channel
from chatbot.core.world_state.payload_builder import PayloadBuilder
from chatbot.core.node_system.node_manager import NodeManager


@pytest.mark.unit
class TestPayloadBuilder:
    """Unit tests for PayloadBuilder class."""

    @pytest.fixture
    def world_state_manager(self):
        """Create a WorldStateManager for testing."""
        return WorldStateManager()

    @pytest.fixture
    def node_manager(self):
        """Create a NodeManager for testing."""
        return NodeManager()

    @pytest.fixture
    def payload_builder(self, node_manager):
        """Create a PayloadBuilder for testing."""
        builder = PayloadBuilder()
        builder.node_manager = node_manager
        return builder

    def test_build_ai_payload_empty_state(self, payload_builder, world_state_manager):
        """Test payload building with empty world state."""
        payload = payload_builder.build_ai_payload(
            world_state_manager.state,
            current_channel_id="test_channel"
        )
        
        assert isinstance(payload, dict)
        assert "current_channel_id" in payload
        assert payload["current_channel_id"] == "test_channel"
        assert "channels" in payload
        assert "action_history" in payload
        assert "system_status" in payload

    def test_build_ai_payload_with_messages(self, payload_builder, world_state_manager):
        """Test payload building with messages in channels."""
        # Add test messages to world state
        test_messages = [
            Message(
                content="Hello world",
                sender="@user1:matrix.org",
                timestamp=time.time() - 300,  # 5 minutes ago
                channel_id="test_channel",
                message_id="msg1",
                platform="matrix"
            ),
            Message(
                content="How are you?",
                sender="@user2:matrix.org", 
                timestamp=time.time() - 150,  # 2.5 minutes ago
                channel_id="test_channel",
                message_id="msg2",
                platform="matrix"
            )
        ]
        
        for msg in test_messages:
            world_state_manager.add_message(msg)
        
        payload = payload_builder.build_ai_payload(
            world_state_manager.state,
            current_channel_id="test_channel"
        )
        
        assert "test_channel" in payload["channels"]["matrix"]
        channel_data = payload["channels"]["matrix"]["test_channel"]
        assert len(channel_data["recent_messages"]) == 2
        assert channel_data["recent_messages"][0]["content"] == "Hello world"
        assert channel_data["recent_messages"][1]["content"] == "How are you?"

    def test_build_ai_payload_message_truncation(self, payload_builder, world_state_manager):
        """Test that messages are properly truncated to limits."""
        # Add many messages to exceed default limits
        for i in range(60):  # Exceed the typical 50 message limit
            msg = Message(
                content=f"Message {i}",
                sender="@user:matrix.org",
                timestamp=time.time() - (60 - i),  # Increasing timestamps
                channel_id="test_channel", 
                message_id=f"msg_{i}",
                platform="matrix"
            )
            world_state_manager.add_message(msg)
        
        payload = payload_builder.build_ai_payload(
            world_state_manager.state,
            current_channel_id="test_channel"
        )
        
        channel_data = payload["channels"]["matrix"]["test_channel"]
        # Should be limited to 50 messages (or whatever the configured limit is)
        assert len(channel_data["recent_messages"]) <= 50
        # Most recent messages should be kept
        assert "Message 59" in channel_data["recent_messages"][-1]["content"]

    def test_build_ai_payload_action_history_limit(self, payload_builder, world_state_manager):
        """Test that action history is properly limited."""
        # Add many actions to world state
        from chatbot.core.world_state.structures import ActionHistory
        
        for i in range(120):  # Exceed typical 100 action limit
            action = ActionHistory(
                action="test_action",
                timestamp=time.time() - (120 - i),
                result={"success": True, "data": f"Action {i}"},
                channel_id="test_channel"
            )
            world_state_manager.state.action_history.append(action)
        
        payload = payload_builder.build_ai_payload(
            world_state_manager.state,
            current_channel_id="test_channel"
        )
        
        # Should be limited to 100 actions (or configured limit)
        assert len(payload["action_history"]) <= 100
        # Most recent actions should be kept
        recent_action = payload["action_history"][-1]
        assert "Action 119" in str(recent_action["result"])

    def test_build_ai_payload_current_channel_priority(self, payload_builder, world_state_manager):
        """Test that current channel gets priority in payload."""
        # Add messages to multiple channels
        channels = ["channel1", "channel2", "current_channel"]
        
        for channel in channels:
            for i in range(10):
                msg = Message(
                    content=f"Message {i} in {channel}",
                    sender="@user:matrix.org",
                    timestamp=time.time() - i,
                    channel_id=channel,
                    message_id=f"msg_{channel}_{i}",
                    platform="matrix"
                )
                world_state_manager.add_message(msg)
        
        payload = payload_builder.build_ai_payload(
            world_state_manager.state,
            current_channel_id="current_channel"
        )
        
        # Current channel should be present and detailed
        assert "current_channel" in payload["channels"]["matrix"]
        current_channel_data = payload["channels"]["matrix"]["current_channel"]
        assert len(current_channel_data["recent_messages"]) == 10
        
        # Other channels should also be present but potentially summarized
        assert "channel1" in payload["channels"]["matrix"]
        assert "channel2" in payload["channels"]["matrix"]

    def test_build_ai_payload_cross_platform_data(self, payload_builder, world_state_manager):
        """Test payload building with multi-platform data."""
        # Add Matrix messages
        matrix_msg = Message(
            content="Matrix message",
            sender="@user:matrix.org",
            timestamp=time.time(),
            channel_id="matrix_room",
            message_id="matrix_msg",
            platform="matrix"
        )
        world_state_manager.add_message(matrix_msg)
        
        # Add Farcaster messages (simulate)
        farcaster_msg = Message(
            content="Farcaster cast",
            sender="user.eth",
            timestamp=time.time() - 60,
            channel_id="farcaster_channel",
            message_id="farcaster_msg",
            platform="farcaster"
        )
        world_state_manager.add_message(farcaster_msg)
        
        payload = payload_builder.build_ai_payload(
            world_state_manager.state,
            current_channel_id="matrix_room"
        )
        
        # Both platforms should be represented
        assert "matrix" in payload["channels"]
        assert "farcaster" in payload["channels"]
        assert "matrix_room" in payload["channels"]["matrix"]
        assert "farcaster_channel" in payload["channels"]["farcaster"]

    def test_build_ai_payload_node_system_integration(self, payload_builder, world_state_manager):
        """Test payload building with node system data."""
        # Mock node system data
        with patch.object(payload_builder.node_manager, 'get_active_nodes') as mock_nodes:
            mock_nodes.return_value = [
                {"id": "node1", "type": "message", "data": {"content": "test"}},
                {"id": "node2", "type": "action", "data": {"action": "wait"}}
            ]
            
            payload = payload_builder.build_ai_payload(
                world_state_manager.state,
                current_channel_id="test_channel"
            )
            
            # Node data should be included in some form
            assert "nodes" in payload or "processing_state" in payload

    def test_build_ai_payload_performance_large_state(self, payload_builder, world_state_manager):
        """Test payload building performance with large world state."""
        import time
        
        # Create a large world state
        for channel_idx in range(10):
            channel_id = f"channel_{channel_idx}"
            for msg_idx in range(100):
                msg = Message(
                    content=f"Message {msg_idx} in channel {channel_idx}",
                    sender=f"@user{msg_idx % 5}:matrix.org",
                    timestamp=time.time() - (msg_idx * 10),
                    channel_id=channel_id,
                    message_id=f"msg_{channel_idx}_{msg_idx}",
                    platform="matrix"
                )
                world_state_manager.add_message(msg)
        
        # Add many actions
        from chatbot.core.world_state.structures import ActionHistory
        for i in range(200):
            action = ActionHistory(
                action="test_action",
                timestamp=time.time() - i,
                result={"data": f"Action {i}"},
                channel_id="channel_0"
            )
            world_state_manager.state.action_history.append(action)
        
        # Measure payload building time
        start_time = time.time()
        payload = payload_builder.build_ai_payload(
            world_state_manager.state,
            current_channel_id="channel_0"
        )
        build_time = time.time() - start_time
        
        # Should complete within reasonable time (< 1 second for this size)
        assert build_time < 1.0
        assert isinstance(payload, dict)
        assert len(payload) > 0

    def test_build_ai_payload_token_optimization(self, payload_builder, world_state_manager):
        """Test that payload respects token limits and optimizes content."""
        # Add content that would exceed token limits
        large_content = "A" * 5000  # Very large message content
        
        msg = Message(
            content=large_content,
            sender="@user:matrix.org",
            timestamp=time.time(),
            channel_id="test_channel",
            message_id="large_msg",
            platform="matrix"
        )
        world_state_manager.add_message(msg)
        
        # Build payload with token limit
        payload = payload_builder.build_ai_payload(
            world_state_manager.state,
            current_channel_id="test_channel",
            token_limit=1000  # Small limit to force truncation
        )
        
        # Content should be truncated or optimized
        channel_data = payload["channels"]["matrix"]["test_channel"]
        message_content = channel_data["recent_messages"][0]["content"]
        
        # Should be shorter than original or marked as truncated
        assert len(message_content) < len(large_content) or "..." in message_content

    def test_build_ai_payload_error_handling(self, payload_builder):
        """Test error handling in payload building."""
        # Test with invalid/corrupted world state
        invalid_state = WorldStateData()
        invalid_state.channels = None  # Corrupt the channels data
        
        # Should handle gracefully and return valid payload
        payload = payload_builder.build_ai_payload(
            invalid_state,
            current_channel_id="test_channel"
        )
        
        assert isinstance(payload, dict)
        assert "error" in payload or payload is not None

    @pytest.mark.slow
    def test_build_ai_payload_memory_usage(self, payload_builder, world_state_manager):
        """Test memory usage during payload building."""
        import psutil
        import os
        
        # Get initial memory usage
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss
        
        # Create moderately large state
        for i in range(500):
            msg = Message(
                content=f"Test message {i} with some content to make it realistic",
                sender=f"@user{i % 10}:matrix.org",
                timestamp=time.time() - i,
                channel_id=f"channel_{i % 5}",
                message_id=f"msg_{i}",
                platform="matrix"
            )
            world_state_manager.add_message(msg)
        
        # Build payload
        payload = payload_builder.build_ai_payload(
            world_state_manager.state,
            current_channel_id="channel_0"
        )
        
        # Check memory usage hasn't grown excessively
        final_memory = process.memory_info().rss
        memory_growth = final_memory - initial_memory
        
        # Memory growth should be reasonable (< 100MB for this test)
        assert memory_growth < 100 * 1024 * 1024  # 100MB
        assert payload is not None
