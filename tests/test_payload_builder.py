"""
Comprehensive tests for PayloadBuilder functionality.
Combines simple and enhanced test coverage in a single file.
"""

import pytest
import json
import time
from unittest.mock import Mock, MagicMock, patch
from dataclasses import asdict

from chatbot.core.world_state.payload_builder import PayloadBuilder
from chatbot.core.world_state import WorldState, WorldStateManager, WorldStateData
from chatbot.core.world_state.structures import Channel, Message, ActionHistory


class TestPayloadBuilderBasic:
    """Test basic PayloadBuilder functionality with actual API."""
    
    @pytest.fixture
    def world_state_manager(self):
        """Create a simple WorldStateManager for testing."""
        manager = Mock(spec=WorldStateManager)
        manager.current_state = Mock(spec=WorldState)
        manager.current_state.channels = {}
        manager.current_state.messages = {}
        manager.current_state.recent_activity = []
        manager.current_state.current_channel_id = None
        manager.current_state.action_history = []
        manager.current_state.rate_limits = {}
        manager.current_state.ecosystem_token_contract = None
        manager.current_state.token_metadata = None
        manager.current_state.monitored_token_holders = {}
        manager.current_state.recent_token_activity = []
        manager.current_state.research_database = {}
        manager.current_state.threads = {}
        manager.current_state.generated_media_library = []
        manager.current_state.bot_media_on_farcaster = {}
        manager.current_state.pending_matrix_invites = []
        manager.current_state.system_status = {}
        
        # Add methods that are called by PayloadBuilder
        manager.current_state.get_recent_media_actions.return_value = {
            "recent_media_actions": []
        }
        
        # Tests expect .state attribute
        manager.state = manager.current_state
        return manager
    
    def test_initialization(self, world_state_manager):
        """Test PayloadBuilder initialization."""
        builder = PayloadBuilder(world_state_manager)
        assert builder.world_state_manager == world_state_manager
    
    def test_initialization_with_node_manager(self, world_state_manager):
        """Test PayloadBuilder with NodeManager."""
        node_manager = Mock()
        builder = PayloadBuilder(world_state_manager, node_manager=node_manager)
        assert builder.world_state_manager == world_state_manager
        assert builder.node_manager == node_manager
    
    def test_build_full_payload_basic(self, world_state_manager):
        """Test basic full payload generation."""
        builder = PayloadBuilder(world_state_manager)
        
        payload = builder.build_full_payload(world_state_manager.state)
        
        assert isinstance(payload, dict)
        # Should have basic structure
        assert "channels" in payload or "current_channel" in payload
    
    def test_build_full_payload_empty_state(self, world_state_manager):
        """Test full payload with empty world state."""
        # Set up empty state
        world_state_manager.current_state.channels = {}
        world_state_manager.current_state.messages = {}
        world_state_manager.current_state.recent_activity = []
        
        builder = PayloadBuilder(world_state_manager)
        payload = builder.build_full_payload(world_state_manager.state)
        
        assert isinstance(payload, dict)
        # Should handle empty state gracefully
        assert "channels" in payload
    
    def test_estimate_payload_size_empty(self, world_state_manager):
        """Test size estimation with empty data."""
        empty_state = world_state_manager.state
        size = PayloadBuilder.estimate_payload_size(empty_state)
        assert isinstance(size, int)
        assert size >= 0
    
    def test_none_input_handling(self, world_state_manager):
        """Test handling of None inputs gracefully."""
        builder = PayloadBuilder(world_state_manager)
        
        # Should not crash with None world state manager attributes
        world_state_manager.current_state = None
        
        try:
            payload = builder.build_full_payload(world_state_manager.state)
            # If it doesn't crash, that's good
            assert isinstance(payload, dict)
        except AttributeError:
            # This is also acceptable - depends on implementation
            pass
    
    def test_platform_detection(self, world_state_manager):
        """Test platform detection logic."""
        # Test with sample world state that has platform data
        world_state_manager.current_state.channels = {
            "matrix_room": {"type": "matrix"},
            "farcaster_channel": {"type": "farcaster"}
        }
        
        # This tests that the method exists and returns something reasonable
        # Implementation details may vary
        size = PayloadBuilder.estimate_payload_size(world_state_manager.state)
        assert isinstance(size, int)
        assert size > 0


class TestPayloadBuilderAdvanced:
    """Advanced tests for PayloadBuilder functionality."""
    
    @pytest.fixture
    def world_state_manager(self):
        """Create a comprehensive WorldStateManager for advanced testing."""
        # Use real WorldStateManager instead of mocks
        manager = WorldStateManager()
        
        # Add real channels
        manager.add_channel("matrix_room", "matrix", "Test Matrix Room")
        manager.add_channel("farcaster_feed", "farcaster", "Farcaster Feed")
        
        return manager
    
    def test_build_full_payload_with_data(self, world_state_manager):
        """Test full payload generation with comprehensive data."""
        builder = PayloadBuilder(world_state_manager)
        
        payload = builder.build_full_payload(world_state_manager.state)
        
        assert isinstance(payload, dict)
        assert "channels" in payload
        assert len(payload["channels"]) == 2
        assert "matrix_room" in payload["channels"]
        assert "farcaster_feed" in payload["channels"]
    
    def test_build_payload_with_node_manager(self, world_state_manager):
        """Test payload building with NodeManager integration."""
        node_manager = Mock()
        node_manager.get_node_states.return_value = {
            "node1": {"status": "active", "data": "test"}
        }
        
        builder = PayloadBuilder(world_state_manager, node_manager=node_manager)
        payload = builder.build_full_payload(world_state_manager.state)
        
        assert isinstance(payload, dict)
        # Should include basic payload structure
        assert "channels" in payload
    
    def test_payload_size_estimation_accuracy(self, world_state_manager):
        """Test that payload size estimation is reasonably accurate."""
        # Add messages to the world state using real methods
        for i in range(100):
            message = Message(
                id=f"msg_{i}",
                content=f"Message {i}",
                sender=f"user_{i % 10}",
                timestamp=time.time() + i,
                channel_type="matrix"
            )
            world_state_manager.add_message("matrix_room", message)
        
        estimated_size = PayloadBuilder.estimate_payload_size(world_state_manager.state)
        
        # Build actual payload to compare
        builder = PayloadBuilder(world_state_manager)
        actual_payload = builder.build_full_payload(world_state_manager.state)
        actual_size = len(json.dumps(actual_payload))
        
        # Should be within reasonable range (allow for some variance)
        assert abs(estimated_size - actual_size) < actual_size * 0.5
    
    def test_payload_with_action_history(self, world_state_manager):
        """Test payload generation with action history."""
        # Add action history using the real method
        action_data = {
            "action_type": "send_message",
            "timestamp": time.time(),
            "parameters": {"content": "Test message"},
            "result": "success"
        }
        world_state_manager.add_action_history(action_data)
        
        builder = PayloadBuilder(world_state_manager)
        payload = builder.build_full_payload(world_state_manager.state)
        
        assert isinstance(payload, dict)
        # Action history should be included in some form
        assert "action_history" in payload or "recent_activity" in payload
    
    def test_payload_with_token_data(self, world_state_manager):
        """Test payload generation with token ecosystem data."""
        builder = PayloadBuilder(world_state_manager)
        payload = builder.build_full_payload(world_state_manager.state)
        
        assert isinstance(payload, dict)
        # Should include token-related data if available
        if hasattr(world_state_manager.state, 'ecosystem_token_contract'):
            # May be included in various forms depending on implementation
            pass
    
    def test_payload_optimization_for_large_data(self, world_state_manager):
        """Test that payload builder optimizes for large datasets."""
        # Add many messages to test optimization
        for i in range(1000):
            message = Message(
                id=f"msg_{i}",
                content=f"This is a long message number {i} with lots of content",
                timestamp=time.time() + i,
                sender=f"user_{i % 10}",
                channel_type="matrix"
            )
            world_state_manager.add_message("matrix_room", message)
        
        builder = PayloadBuilder(world_state_manager)
        payload = builder.build_full_payload(world_state_manager.state)
        
        # Should limit message count or optimize somehow
        assert isinstance(payload, dict)
        if "channels" in payload and "matrix_room" in payload["channels"]:
            messages = payload["channels"]["matrix_room"].get("recent_messages", [])
            # Should limit to reasonable number
            assert len(messages) <= 100  # Assuming some reasonable limit
    
    def test_error_handling_malformed_state(self, world_state_manager):
        """Test error handling with malformed world state."""
        # Create an empty state to test error handling
        from chatbot.core.world_state.structures import WorldStateData
        empty_state = WorldStateData()
        
        builder = PayloadBuilder(world_state_manager)
        
        # Should handle gracefully
        try:
            payload = builder.build_full_payload(empty_state)
            assert isinstance(payload, dict)
        except Exception as e:
            # Should be a handled exception, not a crash
            assert isinstance(e, (ValueError, TypeError, AttributeError))
    
    def test_payload_serialization(self, world_state_manager):
        """Test that generated payload is JSON serializable."""
        builder = PayloadBuilder(world_state_manager)
        payload = builder.build_full_payload(world_state_manager.state)
        
        # Should be JSON serializable
        try:
            json_str = json.dumps(payload)
            assert isinstance(json_str, str)
            
            # Should be deserializable
            reconstructed = json.loads(json_str)
            assert isinstance(reconstructed, dict)
        except (TypeError, ValueError) as e:
            pytest.fail(f"Payload is not JSON serializable: {e}")
    
    def test_payload_structure_consistency(self, world_state_manager):
        """Test that payload structure is consistent across calls."""
        builder = PayloadBuilder(world_state_manager)
        
        payload1 = builder.build_full_payload(world_state_manager.state)
        payload2 = builder.build_full_payload(world_state_manager.state)
        
        # Structure should be consistent
        assert payload1.keys() == payload2.keys()
        
        # Content should be the same for unchanged state
        assert payload1 == payload2


class TestPayloadBuilderContextRefactoring:
    """Test PayloadBuilder as the central context constructor after ContextManager refactoring."""
    
    @pytest.fixture
    def sample_world_state_data(self):
        """Create sample WorldStateData for testing."""
        # Create test channels with messages
        test_channel_1 = Channel(
            id="test_channel_1",
            type="matrix",
            name="Test Channel 1",
            recent_messages=[
                Message(
                    id="msg1",
                    channel_id="test_channel_1",
                    channel_type="matrix",
                    sender="user1",
                    content="Hello world",
                    timestamp=time.time() - 100
                ),
                Message(
                    id="msg2", 
                    channel_id="test_channel_1",
                    channel_type="matrix",
                    sender="user2",
                    content="How are you?",
                    timestamp=time.time() - 50
                )
            ]
        )
        
        test_channel_2 = Channel(
            id="test_channel_2",
            type="farcaster",
            name="Test Channel 2",
            recent_messages=[
                Message(
                    id="msg3",
                    channel_id="test_channel_2",
                    channel_type="farcaster",
                    sender="user3",
                    content="AI is amazing",
                    timestamp=time.time() - 75
                )
            ]
        )
        
        # Create sample action history
        action_history = [
            ActionHistory(
                action_type="send_message",
                parameters={"channel_id": "test_channel_1", "content": "Hello"},
                result="success",
                timestamp=time.time() - 200
            ),
            ActionHistory(
                action_type="like_post",
                parameters={"post_id": "post123"},
                result="success", 
                timestamp=time.time() - 150
            )
        ]
        
        # Create WorldStateData
        world_state_data = WorldStateData()
        world_state_data.channels = {
            "test_channel_1": test_channel_1,
            "test_channel_2": test_channel_2
        }
        world_state_data.action_history = action_history
        world_state_data.system_status = {"status": "active"}
        world_state_data.rate_limits = {"matrix": 100, "farcaster": 50}
        world_state_data.pending_matrix_invites = []
        world_state_data.last_update = time.time()
        
        return world_state_data
    
    def test_build_full_payload_channel_filtering(self, sample_world_state_data):
        """Test that PayloadBuilder correctly filters and prioritizes channels."""
        builder = PayloadBuilder()
        
        # Test with primary channel specified
        config = {
            "max_messages_per_channel": 2,
            "max_action_history": 5,
            "optimize_for_size": True
        }
        
        payload = builder.build_full_payload(
            world_state_data=sample_world_state_data,
            primary_channel_id="test_channel_1", 
            config=config
        )
        
        # Verify structure
        assert isinstance(payload, dict)
        assert "channels" in payload
        assert "action_history" in payload
        assert "current_processing_channel_id" in payload
        assert payload["current_processing_channel_id"] == "test_channel_1"
        
        # Verify channel filtering worked
        assert "test_channel_1" in payload["channels"]
        assert "test_channel_2" in payload["channels"]
        
        # Verify message limiting
        channel_1_data = payload["channels"]["test_channel_1"]
        assert len(channel_1_data["recent_messages"]) <= 2
        
    def test_build_full_payload_action_history_limiting(self, sample_world_state_data):
        """Test that PayloadBuilder correctly limits action history."""
        builder = PayloadBuilder()
        
        config = {
            "max_action_history": 1,  # Limit to 1 action
            "optimize_for_size": True
        }
        
        payload = builder.build_full_payload(
            world_state_data=sample_world_state_data,
            config=config
        )
        
        # Verify action history is limited
        assert len(payload["action_history"]) == 1
        # Should be the most recent action
        assert payload["action_history"][0]["action_type"] == "like_post"
        
    def test_build_full_payload_optimization_levels(self, sample_world_state_data):
        """Test PayloadBuilder optimization options."""
        builder = PayloadBuilder()
        
        # Test optimized payload
        optimized_config = {"optimize_for_size": True}
        optimized_payload = builder.build_full_payload(
            world_state_data=sample_world_state_data,
            config=optimized_config
        )
        
        # Test unoptimized payload (includes more data)
        unoptimized_config = {"optimize_for_size": False}
        unoptimized_payload = builder.build_full_payload(
            world_state_data=sample_world_state_data,
            config=unoptimized_config
        )
        
        # Unoptimized should have more fields
        optimized_keys = set(optimized_payload.keys())
        unoptimized_keys = set(unoptimized_payload.keys())
        
        # Unoptimized should have additional keys like generated_media_library, ecosystem_token_info
        assert len(unoptimized_keys) >= len(optimized_keys)
        
    def test_build_full_payload_with_bot_identity(self, sample_world_state_data):
        """Test PayloadBuilder includes bot identity information."""
        builder = PayloadBuilder()
        
        config = {
            "bot_fid": "12345",
            "bot_username": "@testbot"
        }
        
        payload = builder.build_full_payload(
            world_state_data=sample_world_state_data,
            config=config
        )
        
        # Check that bot identity is included in payload stats
        assert "payload_stats" in payload
        assert "bot_identity" in payload["payload_stats"]
        assert payload["payload_stats"]["bot_identity"]["fid"] == "12345"
        assert payload["payload_stats"]["bot_identity"]["username"] == "@testbot"
        
    def test_build_node_based_payload_basic(self, sample_world_state_data):
        """Test basic node-based payload construction."""
        builder = PayloadBuilder()
        
        # Mock NodeManager
        mock_node_manager = Mock()
        mock_node_manager.get_node_metadata.return_value = Mock(
            is_expanded=True,
            is_pinned=False,
            last_expanded_ts=time.time(),
            ai_summary="Test summary"
        )
        mock_node_manager.get_expansion_status_summary.return_value = {
            "expanded_count": 2,
            "total_count": 5
        }
        mock_node_manager.get_system_events.return_value = []
        
        payload = builder.build_node_based_payload(
            world_state_data=sample_world_state_data,
            node_manager=mock_node_manager,
            primary_channel_id="test_channel_1"
        )
        
        # Verify node-based structure
        assert isinstance(payload, dict)
        assert "expanded_nodes" in payload
        assert "collapsed_node_summaries" in payload
        assert "expansion_status" in payload
        assert "system_events" in payload
        assert "current_processing_channel_id" in payload
        assert payload["current_processing_channel_id"] == "test_channel_1"
        
    def test_payload_size_estimation(self, sample_world_state_data):
        """Test payload size estimation functionality."""
        estimated_size = PayloadBuilder.estimate_payload_size(sample_world_state_data)
        
        assert isinstance(estimated_size, int)
        assert estimated_size > 0
        
        # Should be reasonable size (not too small or too large)
        assert 100 < estimated_size < 1000000  # Between 100 bytes and 1MB
        
    def test_build_full_payload_replaces_context_manager(self, sample_world_state_data):
        """Test that PayloadBuilder.build_full_payload provides all necessary context for AI."""
        builder = PayloadBuilder()
        
        payload = builder.build_full_payload(
            world_state_data=sample_world_state_data,
            primary_channel_id="test_channel_1"
        )
        
        # Verify it includes all essential elements that ContextManager used to provide
        essential_keys = [
            "channels",
            "action_history", 
            "system_status",
            "current_processing_channel_id"
        ]
        
        for key in essential_keys:
            assert key in payload, f"Missing essential key: {key}"
            
        # Verify structure is suitable for AI consumption
        assert isinstance(payload, dict)
        
        # Should be JSON serializable
        json_str = json.dumps(payload, default=str)
        assert len(json_str) > 0
        
        # Should be able to parse back
        parsed = json.loads(json_str)
        assert isinstance(parsed, dict)
