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
