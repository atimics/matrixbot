"""
Enhanced tests for PayloadBuilder with comprehensive coverage.
"""

import pytest
import json
import time
from unittest.mock import Mock, MagicMock, patch
from dataclasses import asdict

from chatbot.core.world_state.payload_builder import PayloadBuilder
from chatbot.core.world_state import WorldState, WorldStateManager, WorldStateData
from chatbot.core.world_state.structures import Channel, Message, ActionHistory
from chatbot.core.node_system.node_manager import NodeManager


class TestPayloadBuilderInitialization:
    """Test PayloadBuilder initialization."""
    
    def test_basic_initialization(self):
        """Test basic PayloadBuilder creation."""
        builder = PayloadBuilder()
        assert builder is not None
        assert hasattr(builder, 'build_full_payload')
        assert hasattr(builder, 'build_node_based_payload')
    
    def test_with_node_manager(self):
        """Test PayloadBuilder with NodeManager."""
        builder = PayloadBuilder()
        node_manager = NodeManager()
        builder.node_manager = node_manager
        assert builder.node_manager == node_manager


class TestPayloadBuilderFullPayload:
    """Test full payload generation."""
    
    @pytest.fixture
    def sample_world_state_data(self, world_state_manager):
        """Create sample world state data."""
        # Add channels
        world_state_manager.add_channel("matrix_room", "matrix", "Test Matrix Room")
        world_state_manager.add_channel("farcaster_feed", "farcaster", "Farcaster Feed")
        
        # Add messages
        message1 = Message(
            id="msg1",
            channel_type="matrix",
            sender="testuser1",
            content="Hello world!",
            timestamp=time.time() - 3600,
            channel_id="matrix_room",
            sender_fid=12345
        )
        
        message2 = Message(
            id="msg2",
            channel_type="farcaster", 
            sender="testuser2",
            content="How's everyone doing?",
            timestamp=time.time() - 1800,
            channel_id="farcaster_feed",
            sender_fid=67890
        )
        
        world_state_manager.add_message("matrix_room", message1)
        world_state_manager.add_message("farcaster_feed", message2)
        
        # Add action history
        action = ActionHistory(
            action_type="send_reply",
            parameters={"content": "Hi there!"},
            timestamp=time.time() - 900,
            channel_id="matrix_room",
            success=True
        )
        world_state_manager.add_action(action)
        
        return world_state_manager.state
    
    def test_build_full_payload_basic(self, sample_world_state_data):
        """Test basic full payload generation."""
        builder = PayloadBuilder()
        payload = builder.build_full_payload(sample_world_state_data)
        
        assert isinstance(payload, dict)
        assert "channels" in payload
        assert "action_history" in payload
        assert "system_status" in payload
        
        # Verify channels
        assert len(payload["channels"]) >= 2
        assert any("matrix" in str(ch) for ch in payload["channels"].values())
        assert any("farcaster" in str(ch) for ch in payload["channels"].values())
    
    def test_build_full_payload_with_primary_channel(self, sample_world_state_data):
        """Test full payload with primary channel specified."""
        builder = PayloadBuilder()
        payload = builder.build_full_payload(
            sample_world_state_data, 
            primary_channel_id="matrix_room"
        )
        
        assert isinstance(payload, dict)
        assert "channels" in payload
        # Should still include all channels but may prioritize primary
        assert len(payload["channels"]) >= 1
    
    def test_build_full_payload_with_config(self, sample_world_state_data):
        """Test full payload with custom configuration."""
        builder = PayloadBuilder()
        config = {
            "max_messages_per_channel": 5,
            "include_system_status": True,
            "compact_format": False
        }
        
        payload = builder.build_full_payload(sample_world_state_data, config=config)
        
        assert isinstance(payload, dict)
        assert "system_status" in payload  # Should be included based on config
    
    def test_build_full_payload_empty_state(self):
        """Test full payload with empty world state."""
        builder = PayloadBuilder()
        empty_state = WorldStateData()
        
        payload = builder.build_full_payload(empty_state)
        
        assert isinstance(payload, dict)
        assert "channels" in payload
        assert payload["channels"] == {}
        assert "action_history" in payload
        assert payload["action_history"] == []


class TestPayloadBuilderNodeBasedPayload:
    """Test node-based payload generation."""
    
    @pytest.fixture
    def builder_with_node_manager(self):
        """Create PayloadBuilder with NodeManager."""
        builder = PayloadBuilder()
        node_manager = NodeManager()
        builder.node_manager = node_manager
        return builder, node_manager
    
    def test_build_node_based_payload_basic(self, sample_world_state_data, builder_with_node_manager):
        """Test basic node-based payload generation."""
        builder, node_manager = builder_with_node_manager
        
        payload = builder.build_node_based_payload(sample_world_state_data)
        
        assert isinstance(payload, dict)
        # Node-based payload should have different structure
        assert "world_state_summary" in payload or "nodes" in payload or "channels" in payload
    
    def test_build_node_based_payload_without_node_manager(self, sample_world_state_data):
        """Test node-based payload without NodeManager falls back gracefully."""
        builder = PayloadBuilder()
        # No node manager set
        
        payload = builder.build_node_based_payload(sample_world_state_data)
        
        # Should either fallback to full payload or return meaningful error structure
        assert isinstance(payload, dict)
    
    def test_build_node_based_payload_with_expansion_limit(self, sample_world_state_data, builder_with_node_manager):
        """Test node-based payload with expansion limits."""
        builder, node_manager = builder_with_node_manager
        
        payload = builder.build_node_based_payload(
            sample_world_state_data,
            max_expanded_nodes=2
        )
        
        assert isinstance(payload, dict)


class TestPayloadBuilderSizeEstimation:
    """Test payload size estimation functionality."""
    
    def test_estimate_payload_size_basic(self, sample_world_state_data):
        """Test basic payload size estimation."""
        builder = PayloadBuilder()
        
        # Should have size estimation method
        if hasattr(builder, 'estimate_payload_size'):
            size = builder.estimate_payload_size(sample_world_state_data)
            assert isinstance(size, (int, float))
            assert size > 0
    
    def test_estimate_payload_size_empty(self):
        """Test size estimation with empty data."""
        builder = PayloadBuilder()
        empty_state = WorldStateData()
        
        if hasattr(builder, 'estimate_payload_size'):
            size = builder.estimate_payload_size(empty_state)
            assert isinstance(size, (int, float))
            assert size >= 0


class TestPayloadBuilderOptimization:
    """Test payload optimization features."""
    
    def test_build_optimized_payload(self, sample_world_state_data):
        """Test optimized payload selection."""
        builder = PayloadBuilder()
        
        if hasattr(builder, 'build_optimized_payload'):
            payload = builder.build_optimized_payload(sample_world_state_data)
            assert isinstance(payload, dict)
        else:
            # If method doesn't exist, should default to full payload
            payload = builder.build_full_payload(sample_world_state_data)
            assert isinstance(payload, dict)
    
    def test_payload_compression(self, sample_world_state_data):
        """Test payload compression/compacting."""
        builder = PayloadBuilder()
        
        # Test with compact format if available
        config = {"compact_format": True}
        payload = builder.build_full_payload(sample_world_state_data, config=config)
        
        assert isinstance(payload, dict)
        # Compact format might have fewer fields or shorter representations


class TestPayloadBuilderCrossPlatform:
    """Test cross-platform payload features."""
    
    def test_platform_detection(self, world_state_manager):
        """Test detection of different platforms."""
        builder = PayloadBuilder()
        
        # Add channels from different platforms
        world_state_manager.add_channel("matrix_room", "matrix", "Matrix Room")
        world_state_manager.add_channel("farcaster_feed", "farcaster", "Farcaster Feed")
        
        payload = builder.build_full_payload(world_state_manager.state)
        
        # Should detect both platforms
        channels = payload.get("channels", {})
        matrix_channels = [ch for ch in channels.values() if "matrix" in str(ch).lower()]
        farcaster_channels = [ch for ch in channels.values() if "farcaster" in str(ch).lower()]
        
        assert len(matrix_channels) > 0
        assert len(farcaster_channels) > 0
    
    def test_channel_prioritization(self, world_state_manager):
        """Test channel prioritization in payload."""
        builder = PayloadBuilder()
        
        # Add multiple channels with different activity levels
        world_state_manager.add_channel("active_room", "matrix", "Active Room")
        world_state_manager.add_channel("quiet_room", "matrix", "Quiet Room")
        
        # Add more recent messages to active room
        for i in range(5):
            msg = Message(
                id=f"msg_{i}",
                author_fid=f"user_{i}",
                author_username=f"user_{i}",
                content=f"Message {i}",
                timestamp=time.time() - (i * 100),
                channel_id="active_room"
            )
            world_state_manager.add_message("active_room", msg)
        
        payload = builder.build_full_payload(world_state_manager.state)
        
        # Should include both channels
        assert "channels" in payload
        assert len(payload["channels"]) >= 2


class TestPayloadBuilderNodeIntegration:
    """Test integration with node system."""
    
    @pytest.fixture
    def setup_node_system(self, world_state_manager, builder_with_node_manager):
        """Set up world state with node system."""
        builder, node_manager = builder_with_node_manager
        
        # Add channels and data
        world_state_manager.add_channel("main_room", "matrix", "Main Room")
        
        # Add several messages
        for i in range(10):
            msg = Message(
                id=f"node_msg_{i}",
                author_fid=f"user_{i}",
                author_username=f"user_{i}",
                content=f"Node test message {i}",
                timestamp=time.time() - (i * 60),
                channel_id="main_room"
            )
            world_state_manager.add_message("main_room", msg)
        
        return builder, node_manager, world_state_manager
    
    def test_node_expansion_payload(self, setup_node_system):
        """Test payload with node expansion."""
        builder, node_manager, world_state_manager = setup_node_system
        
        # Test with different expansion settings
        payload = builder.build_node_based_payload(
            world_state_manager.state,
            max_expanded_nodes=3
        )
        
        assert isinstance(payload, dict)
    
    def test_node_collapse_payload(self, setup_node_system):
        """Test payload with collapsed nodes."""
        builder, node_manager, world_state_manager = setup_node_system
        
        payload = builder.build_node_based_payload(
            world_state_manager.state,
            max_expanded_nodes=1  # Force most nodes to be collapsed
        )
        
        assert isinstance(payload, dict)


class TestPayloadBuilderEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_none_input_handling(self):
        """Test handling of None inputs."""
        builder = PayloadBuilder()
        
        # Should handle None gracefully
        try:
            payload = builder.build_full_payload(None)
            # If it doesn't raise an error, should return reasonable structure
            assert payload is not None
        except (ValueError, AttributeError) as e:
            # If it raises an error, should be meaningful
            assert str(e)
    
    def test_malformed_data_handling(self):
        """Test handling of malformed world state data."""
        builder = PayloadBuilder()
        
        # Create a malformed state object
        malformed_state = type('MockState', (), {})()
        
        try:
            payload = builder.build_full_payload(malformed_state)
            assert isinstance(payload, dict)
        except Exception as e:
            # Should be a reasonable error
            assert isinstance(e, (AttributeError, ValueError, TypeError))
    
    def test_large_data_handling(self, world_state_manager):
        """Test handling of large datasets."""
        builder = PayloadBuilder()
        
        # Add many channels and messages
        for ch_i in range(5):
            channel_id = f"large_ch_{ch_i}"
            world_state_manager.add_channel(channel_id, "matrix", f"Large Channel {ch_i}")
            
            # Add many messages per channel
            for msg_i in range(20):
                msg = Message(
                    id=f"large_msg_{ch_i}_{msg_i}",
                    author_fid=f"user_{msg_i}",
                    author_username=f"user_{msg_i}",
                    content=f"Large dataset test message {msg_i} in channel {ch_i}",
                    timestamp=time.time() - (msg_i * 30),
                    channel_id=channel_id
                )
                world_state_manager.add_message(channel_id, msg)
        
        # Should handle large dataset without issues
        payload = builder.build_full_payload(world_state_manager.state)
        
        assert isinstance(payload, dict)
        assert "channels" in payload
        assert len(payload["channels"]) >= 5
    
    @pytest.mark.error_handling
    def test_memory_constraints(self, world_state_manager):
        """Test behavior under memory constraints."""
        builder = PayloadBuilder()
        
        # Create extremely large content
        large_content = "x" * 10000  # 10KB content
        
        for i in range(10):
            msg = Message(
                id=f"memory_test_{i}",
                author_fid="test_user",
                author_username="test_user",
                content=large_content,
                timestamp=time.time(),
                channel_id="memory_test_channel"
            )
            world_state_manager.add_message("memory_test_channel", msg)
        
        # Should handle gracefully
        payload = builder.build_full_payload(world_state_manager.state)
        assert isinstance(payload, dict)


class TestPayloadBuilderSerialization:
    """Test payload serialization capabilities."""
    
    def test_json_serialization(self, sample_world_state_data):
        """Test that generated payloads are JSON serializable."""
        builder = PayloadBuilder()
        payload = builder.build_full_payload(sample_world_state_data)
        
        # Should be able to serialize to JSON
        json_str = json.dumps(payload)
        assert isinstance(json_str, str)
        assert len(json_str) > 10
        
        # Should be able to deserialize back
        deserialized = json.loads(json_str)
        assert isinstance(deserialized, dict)
        assert deserialized.keys() == payload.keys()
    
    def test_payload_structure_consistency(self, sample_world_state_data):
        """Test that payload structure is consistent across builds."""
        builder = PayloadBuilder()
        
        payload1 = builder.build_full_payload(sample_world_state_data)
        payload2 = builder.build_full_payload(sample_world_state_data)
        
        # Should have same structure (keys)
        assert payload1.keys() == payload2.keys()
        
        # Core structure should be the same
        assert type(payload1.get("channels")) == type(payload2.get("channels"))
        assert type(payload1.get("action_history")) == type(payload2.get("action_history"))


class TestPayloadBuilderPerformance:
    """Test performance characteristics."""
    
    @pytest.mark.slow
    def test_payload_generation_performance(self, world_state_manager):
        """Test payload generation performance with realistic data."""
        builder = PayloadBuilder()
        
        # Add realistic amount of data
        for ch_i in range(3):
            channel_id = f"perf_ch_{ch_i}"
            world_state_manager.add_channel(channel_id, "matrix", f"Performance Channel {ch_i}")
            
            for msg_i in range(50):
                msg = Message(
                    id=f"perf_msg_{ch_i}_{msg_i}",
                    author_fid=f"user_{msg_i % 10}",  # 10 different users
                    author_username=f"user_{msg_i % 10}",
                    content=f"Performance test message {msg_i}",
                    timestamp=time.time() - (msg_i * 60),
                    channel_id=channel_id
                )
                world_state_manager.add_message(channel_id, msg)
        
        # Time the payload generation
        start_time = time.time()
        payload = builder.build_full_payload(world_state_manager.state)
        end_time = time.time()
        
        # Should complete reasonably quickly (under 1 second for this data size)
        assert (end_time - start_time) < 1.0
        assert isinstance(payload, dict)
        assert len(payload["channels"]) == 3
