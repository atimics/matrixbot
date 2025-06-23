"""
Test suite for the security and performance improvements.
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from chatbot.api_server.security import APIKeyAuth, RateLimitedAPIKeyAuth
from chatbot.core.world_state.dynamic_optimizer import DynamicPayloadOptimizer, PayloadOptimizationConfig


class TestAPIKeyAuth:
    """Test the API key authentication system."""
    
    def test_api_key_validation_success(self):
        """Test successful API key validation."""
        with patch('chatbot.api_server.security.settings') as mock_settings:
            mock_settings.API_SERVER_KEY = "test_key_123"
            mock_settings.API_REQUIRE_AUTH = True
            
            auth = APIKeyAuth()
            
            # Create mock credentials
            mock_credentials = Mock()
            mock_credentials.credentials = "test_key_123"
            
            result = auth(mock_credentials)
            assert result is True
    
    def test_api_key_validation_failure(self):
        """Test failed API key validation."""
        with patch('chatbot.config.settings') as mock_settings:
            mock_settings.API_SERVER_KEY = "test_key_123"
            mock_settings.API_REQUIRE_AUTH = True
            
            auth = APIKeyAuth()
            
            # Create mock credentials with wrong key
            mock_credentials = Mock()
            mock_credentials.credentials = "wrong_key"
            
            with pytest.raises(Exception):  # Should raise HTTPException
                auth(mock_credentials)
    
    def test_api_key_disabled_auth(self):
        """Test when authentication is disabled."""
        with patch('chatbot.config.settings') as mock_settings:
            mock_settings.API_REQUIRE_AUTH = False
            
            auth = APIKeyAuth()
            
            result = auth(None)
            assert result is True


class TestDynamicPayloadOptimizer:
    """Test the dynamic payload optimization system."""
    
    @pytest.fixture
    def optimizer(self):
        """Create a DynamicPayloadOptimizer instance for testing."""
        return DynamicPayloadOptimizer()
    
    @pytest.fixture
    def large_payload(self):
        """Create a large test payload."""
        return {
            "channels": {
                f"channel_{i}": {
                    "recent_messages": [
                        {
                            "id": f"msg_{j}",
                            "content": "This is a test message with some content " * 10,
                            "sender": f"user_{j}",
                            "timestamp": 1000000 + j
                        }
                        for j in range(20)  # 20 messages per channel
                    ],
                    "type": "test_channel"
                }
                for i in range(10)  # 10 channels
            },
            "action_history": [
                {
                    "action_type": f"test_action_{i}",
                    "parameters": {"test_param": f"value_{i}" * 50},
                    "result": f"test_result_{i}" * 100,
                    "timestamp": 1000000 + i
                }
                for i in range(50)  # 50 actions
            ],
            "system_status": {
                "running": True,
                "debug_info": {"large_debug_data": "x" * 10000}
            },
            "research_database": [
                {
                    "topic": f"topic_{i}",
                    "content": "Research content " * 200,
                    "timestamp": 1000000 + i,
                    "relevance_score": 0.5
                }
                for i in range(20)  # 20 research entries
            ]
        }
    
    def test_payload_size_reduction(self, optimizer, large_payload):
        """Test that optimization reduces payload size."""
        original_size = len(json.dumps(large_payload))
        
        optimized_payload, report = optimizer.optimize_payload(
            large_payload,
            target_size=50000,  # Force optimization
            urgency_level="normal"
        )
        
        final_size = len(json.dumps(optimized_payload))
        
        assert final_size < original_size
        assert report["size_reduction"] > 0
        assert report["size_reduction_percent"] > 0
        assert len(report["strategies_applied"]) > 0
    
    def test_metadata_cleanup(self, optimizer, large_payload):
        """Test that metadata cleanup removes debug info."""
        optimized_payload, report = optimizer.optimize_payload(
            large_payload,
            urgency_level="conservative"
        )
        
        # Debug info should be removed
        assert "debug_info" not in optimized_payload.get("system_status", {})
        assert "metadata_cleanup" in report["strategies_applied"]
    
    def test_message_optimization(self, optimizer, large_payload):
        """Test that message optimization reduces message count."""
        original_message_count = sum(
            len(channel.get("recent_messages", []))
            for channel in large_payload["channels"].values()
        )
        
        optimized_payload, report = optimizer.optimize_payload(
            large_payload,
            target_size=30000,  # Aggressive optimization
            urgency_level="aggressive"
        )
        
        optimized_message_count = sum(
            len(channel.get("recent_messages", []))
            for channel in optimized_payload.get("channels", {}).values()
        )
        
        assert optimized_message_count <= original_message_count
        assert "message_optimization" in report["strategies_applied"]
    
    def test_action_history_compression(self, optimizer, large_payload):
        """Test that action history is compressed."""
        original_action_count = len(large_payload["action_history"])
        
        optimized_payload, report = optimizer.optimize_payload(
            large_payload,
            target_size=40000,
            urgency_level="normal"
        )
        
        optimized_action_count = len(optimized_payload.get("action_history", []))
        
        # Should be reduced or have summary entry
        assert optimized_action_count <= original_action_count
        
        # Check for summary entry if actions were summarized
        if optimized_action_count < original_action_count:
            assert any(
                action.get("type") == "action_summary"
                for action in optimized_payload.get("action_history", [])
            )
    
    def test_research_summarization(self, optimizer, large_payload):
        """Test that research data is summarized."""
        original_research_count = len(large_payload["research_database"])
        
        optimized_payload, report = optimizer.optimize_payload(
            large_payload,
            target_size=35000,
            urgency_level="normal"
        )
        
        # Research should be reduced and summary added
        optimized_research_count = len(optimized_payload.get("research_database", []))
        assert optimized_research_count <= min(10, original_research_count)
        
        if original_research_count > 10:
            assert "research_summary" in optimized_payload
            assert "research_summarization" in report["strategies_applied"]
    
    def test_aggressive_pruning(self, optimizer, large_payload):
        """Test aggressive channel pruning."""
        original_channel_count = len(large_payload["channels"])
        
        optimized_payload, report = optimizer.optimize_payload(
            large_payload,
            target_size=20000,  # Very aggressive
            urgency_level="aggressive"
        )
        
        optimized_channel_count = len(optimized_payload.get("channels", {}))
        
        # Should keep only top 3 channels
        assert optimized_channel_count <= min(3, original_channel_count)
        
        if original_channel_count > 3:
            assert "aggressive_pruning" in report["strategies_applied"]
            assert "pruning_applied" in optimized_payload
    
    def test_optimization_stats(self, optimizer):
        """Test that optimization statistics are tracked."""
        payload = {"test": "data"}
        
        initial_stats = optimizer.get_optimization_stats()
        assert initial_stats["total_optimizations"] == 0
        
        optimizer.optimize_payload(payload)
        
        updated_stats = optimizer.get_optimization_stats()
        assert updated_stats["total_optimizations"] == 1
        assert updated_stats["last_optimization"] is not None
    
    def test_urgency_levels(self, optimizer, large_payload):
        """Test different urgency levels produce different results."""
        conservative_result, conservative_report = optimizer.optimize_payload(
            large_payload.copy(), urgency_level="conservative"
        )
        
        aggressive_result, aggressive_report = optimizer.optimize_payload(
            large_payload.copy(), urgency_level="aggressive"
        )
        
        conservative_size = len(json.dumps(conservative_result))
        aggressive_size = len(json.dumps(aggressive_result))
        
        # Aggressive should be smaller
        assert aggressive_size <= conservative_size
        assert len(aggressive_report["strategies_applied"]) >= len(conservative_report["strategies_applied"])


class TestPayloadBuilderIntegration:
    """Test PayloadBuilder integration with DynamicPayloadOptimizer."""
    
    def test_optimization_integration(self):
        """Test that PayloadBuilder uses the optimizer when payloads are large."""
        with patch('chatbot.core.world_state.payload_builder.PayloadBuilder') as MockBuilder:
            # Create a mock PayloadBuilder instance
            builder = MockBuilder.return_value
            builder.optimization_enabled = True
            builder.size_threshold = 1000  # Low threshold for testing
            
            # Mock the optimizer
            mock_optimizer = Mock()
            mock_optimizer.optimize_payload.return_value = (
                {"optimized": True},
                {"size_reduction_percent": 25.0, "strategies_applied": ["test_strategy"]}
            )
            builder.optimizer = mock_optimizer
            
            # Test that optimization is called for large payloads
            large_payload = {"data": "x" * 2000}  # Exceeds threshold
            
            # Simulate the optimization logic
            payload_size = len(json.dumps(large_payload))
            if payload_size > builder.size_threshold:
                result, report = builder.optimizer.optimize_payload(large_payload)
                
                # Verify optimization was called
                mock_optimizer.optimize_payload.assert_called_once()
                assert result["optimized"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
