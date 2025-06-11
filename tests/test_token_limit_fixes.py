"""
Tests for token limit fixes and AI payload optimization.

These tests verify that the strategic and tactical fixes for HTTP 402 token limit errors
work correctly, including token estimation, processing mode switching, and payload optimization.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
import time
import json

from chatbot.utils.token_utils import estimate_token_count, should_use_node_based_payload
from chatbot.core.orchestration.processing_hub import ProcessingHub, ProcessingConfig
from chatbot.core.world_state.payload_builder import PayloadBuilder
from chatbot.core.world_state.structures import WorldStateData, Channel, Message
from chatbot.config import settings


class TestTokenUtils:
    """Test token estimation utilities."""
    
    def test_estimate_token_count_small_payload(self):
        """Test token estimation for small payloads."""
        small_payload = {
            "message": "Hello world",
            "user": "test_user"
        }
        
        estimated_tokens = estimate_token_count(small_payload)
        
        # Should be a reasonable estimate (not 0, not huge)
        assert 5 < estimated_tokens < 50
        
    def test_estimate_token_count_large_payload(self):
        """Test token estimation for large payloads."""
        # Create a large payload
        large_payload = {
            "channels": {
                f"channel_{i}": {
                    "messages": [
                        {
                            "content": f"This is a long message number {j} in channel {i} " * 20,
                            "user": f"user_{j}",
                            "timestamp": time.time()
                        }
                        for j in range(50)  # 50 messages per channel
                    ]
                }
                for i in range(20)  # 20 channels
            },
            "system_status": {"running": True, "cycles": 100},
            "user_data": [{"user_id": i, "profile": "x" * 1000} for i in range(100)]
        }
        
        estimated_tokens = estimate_token_count(large_payload)
        
        # Should estimate a large number of tokens
        assert estimated_tokens > 10000
        
    def test_should_use_node_based_payload_threshold(self):
        """Test the decision logic for switching to node-based payloads."""
        threshold = 12000
        
        # Below threshold - should use traditional
        assert not should_use_node_based_payload(8000, threshold)
        
        # Above threshold - should use node-based
        assert should_use_node_based_payload(15000, threshold)
        
        # At threshold - should use node-based (safer)
        assert should_use_node_based_payload(12000, threshold)


class TestProcessingHubTokenSwitching:
    """Test the processing hub's token-based mode switching."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.world_state_manager = Mock()
        self.payload_builder = Mock(spec=PayloadBuilder)
        self.rate_limiter = Mock()
        self.config = ProcessingConfig()
        
        self.processing_hub = ProcessingHub(
            world_state_manager=self.world_state_manager,
            payload_builder=self.payload_builder,
            rate_limiter=self.rate_limiter,
            config=self.config
        )
        
        # Mock processors
        self.processing_hub.traditional_processor = Mock()
        self.processing_hub.node_processor = Mock()
        
    def test_determine_processing_mode_small_payload(self):
        """Test that small payloads use traditional processing."""
        # Mock a small payload
        small_payload = {"test": "small data"}
        self.payload_builder.build_full_payload.return_value = small_payload
        
        # Mock world state
        self.world_state_manager.get_state_data.return_value = Mock()
        
        # Mock the entire method call chain to avoid import issues
        with patch.object(self.processing_hub, '_get_primary_channel', return_value="test_channel"), \
             patch('chatbot.utils.token_utils.estimate_token_count', return_value=5000):
            mode = self.processing_hub._determine_processing_mode(["test_channel"])
            
        assert mode == "traditional"
        
    def test_determine_processing_mode_large_payload(self):
        """Test that large payloads switch to node-based processing."""
        # Mock a large payload
        large_payload = {"test": "x" * 50000}  # Large payload
        self.payload_builder.build_full_payload.return_value = large_payload
        
        # Mock world state
        self.world_state_manager.get_state_data.return_value = Mock()
        
        # Mock the entire method call chain to avoid import issues
        with patch.object(self.processing_hub, '_get_primary_channel', return_value="test_channel"), \
             patch('chatbot.utils.token_utils.estimate_token_count', return_value=18000):
            mode = self.processing_hub._determine_processing_mode(["test_channel"])
            
        assert mode == "node_based"
        
    def test_determine_processing_mode_no_node_processor(self):
        """Test fallback to traditional when node processor unavailable."""
        # Remove node processor
        self.processing_hub.node_processor = None
        
        # Mock a large payload that would normally trigger node-based
        large_payload = {"test": "x" * 50000}
        self.payload_builder.build_full_payload.return_value = large_payload
        
        self.world_state_manager.get_state_data.return_value = Mock()
        
        # Mock the entire method call chain to avoid import issues
        with patch.object(self.processing_hub, '_get_primary_channel', return_value="test_channel"), \
             patch('chatbot.utils.token_utils.estimate_token_count', return_value=18000):
            mode = self.processing_hub._determine_processing_mode(["test_channel"])
            
        # Should fall back to traditional even with large payload
        assert mode == "traditional"
        
    def test_determine_processing_mode_error_handling(self):
        """Test error handling in processing mode determination."""
        # Mock an error in payload building
        self.payload_builder.build_full_payload.side_effect = Exception("Build error")
        self.world_state_manager.get_state_data.return_value = Mock()
        
        mode = self.processing_hub._determine_processing_mode(["test_channel"])
        
        # Should fall back to traditional on error
        assert mode == "traditional"


class TestPayloadBuilderOptimization:
    """Test the payload builder's tactical optimizations for newly joined channels."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.payload_builder = PayloadBuilder()
        
    def create_test_world_state(self, num_channels=5, messages_per_channel=10, recent_join=False):
        """Create a test world state with configurable channels and messages."""
        current_time = time.time()
        
        channels = {}
        for i in range(num_channels):
            channel_id = f"channel_{i}"
            
            # Create messages for this channel
            messages = []
            for j in range(messages_per_channel):
                # For recent join simulation, make first message very recent
                if recent_join and j == 0:
                    msg_time = current_time - 300  # 5 minutes ago
                else:
                    msg_time = current_time - (3600 * j)  # Spread over hours
                
                message = Message(
                    id=f"msg_{i}_{j}",
                    channel_type="farcaster",
                    sender=f"user_{j}",
                    content=f"Message {j} in channel {i}",
                    timestamp=msg_time,
                    channel_id=channel_id
                )
                messages.append(message)
            
            channel = Channel(
                id=channel_id,
                name=f"Channel {i}",
                type="farcaster",
                recent_messages=messages
            )
            channels[channel_id] = channel
        
        world_state = WorldStateData()
        world_state.channels = channels
        world_state.system_status = {"running": True}
        world_state.rate_limits = {}
        
        return world_state
    
    def test_build_full_payload_normal_channels(self):
        """Test payload building with normal channel activity."""
        world_state = self.create_test_world_state(num_channels=3, messages_per_channel=5)
        
        payload = self.payload_builder.build_full_payload(
            world_state_data=world_state,
            primary_channel_id="channel_0"
        )
        
        # Should include all channels
        assert len(payload["channels"]) == 3
        assert payload["payload_stats"]["data_spike_detected"] is False
        
    def test_build_full_payload_data_spike_detected(self):
        """Test payload building when data spike is detected."""
        # Create many channels with recent activity
        world_state = self.create_test_world_state(
            num_channels=15,  # More than the threshold (10)
            messages_per_channel=5,
            recent_join=True
        )
        
        payload = self.payload_builder.build_full_payload(
            world_state_data=world_state,
            primary_channel_id="channel_0"
        )
        
        # Should detect data spike and apply aggressive filtering
        assert payload["payload_stats"]["data_spike_detected"] is True
        assert payload["payload_stats"]["active_channels_count"] == 15
        
        # Should have fewer detailed channels due to aggressive filtering
        detailed_channels = payload["payload_stats"]["detailed_channels"]
        assert detailed_channels < 15  # Should be reduced
        
    def test_build_full_payload_newly_joined_channels_marked(self):
        """Test that newly joined channels are properly marked."""
        world_state = self.create_test_world_state(
            num_channels=5,
            messages_per_channel=3,
            recent_join=True
        )
        
        payload = self.payload_builder.build_full_payload(
            world_state_data=world_state,
            primary_channel_id="channel_0"
        )
        
        # Check that non-primary channels are marked as recently joined
        for channel_id, channel_data in payload["channels"].items():
            if channel_id != "channel_0":  # Not primary channel
                if "recent_messages" in channel_data:  # Detailed channel
                    assert channel_data.get("recently_joined") is True
                else:  # Summary channel
                    assert channel_data.get("recently_joined") is True


class TestHTTP402ScenarioIntegration:
    """Integration tests for the specific HTTP 402 scenario from the logs."""
    
    @pytest.mark.asyncio
    async def test_http_402_scenario_simulation(self):
        """Simulate the exact scenario that caused HTTP 402 errors."""
        # Simulate the bot joining many Matrix rooms simultaneously
        # This creates a large payload that exceeds token limits
        
        payload_builder = PayloadBuilder()
        
        # Create a scenario similar to the logs: many channels with messages
        current_time = time.time()
        channels = {}
        
        # Create 20 matrix channels (simulating joining many rooms)
        for i in range(20):
            channel_id = f"!room{i}:matrix.server"
            messages = []
            
            # Each channel has some recent messages
            for j in range(8):  # 8 messages per channel
                message = Message(
                    id=f"$event_{i}_{j}",
                    channel_type="matrix",
                    sender=f"@user{j}:matrix.server",
                    content=f"Welcome to room {i}! This is message {j}. " * 10,  # Longer messages
                    timestamp=current_time - (j * 300),  # 5 min intervals
                    channel_id=channel_id
                )
                messages.append(message)
            
            channel = Channel(
                id=channel_id,
                name=f"Matrix Room {i}",
                type="matrix",
                recent_messages=messages
            )
            channels[channel_id] = channel
        
        world_state = WorldStateData(
            channels=channels,
            system_status={"running": True, "total_cycles": 150},
            rate_limits={"matrix": {"remaining": 1000}},
            action_history=[]  # Add some action history too
        )
        
        # Build payload with default configuration
        payload = payload_builder.build_full_payload(
            world_state_data=world_state,
            primary_channel_id=list(channels.keys())[0]
        )
        
        # Estimate tokens
        estimated_tokens = estimate_token_count(payload)
        
        # Verify that our fixes would handle this scenario
        print(f"Estimated tokens: {estimated_tokens}")
        print(f"Token threshold: {settings.AI_CONTEXT_TOKEN_THRESHOLD}")
        print(f"Data spike detected: {payload['payload_stats']['data_spike_detected']}")
        
        # The payload should be optimized to prevent token limit issues
        if estimated_tokens > settings.AI_CONTEXT_TOKEN_THRESHOLD:
            # If still over threshold, the processing hub should switch to node-based
            assert should_use_node_based_payload(estimated_tokens, settings.AI_CONTEXT_TOKEN_THRESHOLD)
        
        # Verify that data spike detection worked
        assert payload["payload_stats"]["data_spike_detected"] is True
        assert payload["payload_stats"]["active_channels_count"] == 20
        
        # Verify that aggressive filtering was applied
        detailed_channels = payload["payload_stats"]["detailed_channels"]
        summary_channels = payload["payload_stats"]["summary_channels"]
        
        # Should have fewer detailed channels due to optimization
        assert detailed_channels < 20
        assert summary_channels > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
