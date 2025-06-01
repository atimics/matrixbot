"""
Comprehensive tests for enhanced rate limiting functionality in the orchestrator.
"""
import asyncio
import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch

from chatbot.core.orchestrator import (
    ContextAwareOrchestrator,
    EnhancedRateLimiter,
    OrchestratorConfig,
    RateLimitConfig,
)
from chatbot.core.world_state import ActionHistory, Message


class TestEnhancedRateLimiting:
    """Test suite for enhanced rate limiting functionality."""

    def test_rate_limit_config_defaults(self):
        """Test that rate limit configuration has sensible defaults."""
        config = RateLimitConfig()
        
        assert config.max_cycles_per_hour == 300
        assert config.min_cycle_interval == 12.0
        assert config.enable_adaptive_limits is True
        assert config.burst_window_seconds == 300
        assert config.max_burst_cycles == 20
        assert config.cooldown_multiplier == 1.5
        
        # Check action-specific limits
        assert 'SendMatrixMessageTool' in config.action_limits
        assert 'SendFarcasterPostTool' in config.action_limits
        assert config.action_limits['SendMatrixMessageTool'] == 100
        assert config.action_limits['SendFarcasterPostTool'] == 50
        
        # Check channel-specific limits
        assert 'matrix' in config.channel_limits
        assert 'farcaster' in config.channel_limits
        assert config.channel_limits['matrix'] == 50
        assert config.channel_limits['farcaster'] == 30

    def test_enhanced_rate_limiter_basic_functionality(self):
        """Test basic rate limiter functionality."""
        config = RateLimitConfig()
        limiter = EnhancedRateLimiter(config)
        current_time = time.time()
        
        # Should allow first cycle
        can_process, wait_time = limiter.can_process_cycle(current_time)
        assert can_process is True
        assert wait_time == 0.0
        
        # Record the cycle
        limiter.record_cycle(current_time)
        
        # Should allow action within limits
        can_execute, reason = limiter.can_execute_action('SendMatrixMessageTool', current_time)
        assert can_execute is True
        assert reason == ""
        
        # Record action
        limiter.record_action('SendMatrixMessageTool', current_time)

    def test_action_rate_limiting(self):
        """Test action-specific rate limiting."""
        config = RateLimitConfig()
        config.action_limits['TestTool'] = 2  # Low limit for testing
        limiter = EnhancedRateLimiter(config)
        current_time = time.time()
        
        # Should allow first two actions
        for i in range(2):
            can_execute, reason = limiter.can_execute_action('TestTool', current_time + i)
            assert can_execute is True
            limiter.record_action('TestTool', current_time + i)
        
        # Third action should be blocked
        can_execute, reason = limiter.can_execute_action('TestTool', current_time + 2)
        assert can_execute is False
        assert "Action rate limit exceeded" in reason
        assert "2/2 per hour" in reason

    def test_channel_rate_limiting(self):
        """Test channel-specific rate limiting."""
        config = RateLimitConfig()
        config.channel_limits['test_type'] = 2  # Low limit for testing
        limiter = EnhancedRateLimiter(config)
        current_time = time.time()
        
        # Should allow first two messages to channel
        for i in range(2):
            can_send, reason = limiter.can_send_to_channel('test_channel', 'test_type', current_time + i)
            assert can_send is True
            limiter.record_channel_message('test_channel', current_time + i)
        
        # Third message should be blocked
        can_send, reason = limiter.can_send_to_channel('test_channel', 'test_type', current_time + 2)
        assert can_send is False
        assert "Channel rate limit exceeded" in reason
        assert "2/2 per hour" in reason

    def test_burst_detection_and_cooldown(self):
        """Test burst detection and adaptive cooldown."""
        config = RateLimitConfig()
        config.max_burst_cycles = 3  # Low threshold for testing
        config.burst_window_seconds = 60  # 1 minute window
        config.cooldown_multiplier = 2.0
        limiter = EnhancedRateLimiter(config)
        current_time = time.time()
        
        # Record cycles in quick succession to trigger burst
        for i in range(3):
            can_process, wait_time = limiter.can_process_cycle(current_time + i)
            assert can_process is True
            limiter.record_cycle(current_time + i)
        
        # Fourth cycle should trigger burst protection
        can_process, wait_time = limiter.can_process_cycle(current_time + 3)
        assert can_process is False
        assert wait_time > 0
        assert limiter.burst_detected is True

    def test_adaptive_multiplier_recovery(self):
        """Test that adaptive multiplier gradually recovers."""
        config = RateLimitConfig()
        limiter = EnhancedRateLimiter(config)
        current_time = time.time()
        
        # Manually set high adaptive multiplier
        limiter.adaptive_multiplier = 2.0
        limiter.burst_detected = False
        limiter.cooldown_until = current_time - 1  # Past cooldown
        
        # Record a cycle - should reduce multiplier
        limiter.record_cycle(current_time)
        assert limiter.adaptive_multiplier < 2.0

    def test_rate_limit_status_reporting(self):
        """Test comprehensive rate limit status reporting."""
        config = RateLimitConfig()
        config.action_limits['TestTool'] = 10
        limiter = EnhancedRateLimiter(config)
        current_time = time.time()
        
        # Record some actions
        for i in range(3):
            limiter.record_action('TestTool', current_time + i)
            limiter.record_cycle(current_time + i)
        
        status = limiter.get_rate_limit_status(current_time + 10)
        
        assert 'cycles_per_hour' in status
        assert 'max_cycles_per_hour' in status
        assert 'adaptive_multiplier' in status
        assert 'action_limits' in status
        assert 'TestTool' in status['action_limits']
        assert status['action_limits']['TestTool']['used'] == 3
        assert status['action_limits']['TestTool']['limit'] == 10
        assert status['action_limits']['TestTool']['remaining'] == 7

    def test_old_entries_cleanup(self):
        """Test that old entries are cleaned up properly."""
        config = RateLimitConfig()
        limiter = EnhancedRateLimiter(config)
        current_time = time.time()
        
        # Record old actions (more than 1 hour ago)
        old_time = current_time - 3700  # Over 1 hour ago
        for i in range(5):
            limiter.record_action('TestTool', old_time + i)
            
        # Record recent actions
        for i in range(3):
            limiter.record_action('TestTool', current_time + i)
        
        # Check that only recent actions count
        status = limiter.get_rate_limit_status(current_time + 10)
        if 'TestTool' in status['action_limits']:
            assert status['action_limits']['TestTool']['used'] == 3  # Only recent ones

    @pytest.mark.asyncio
    async def test_orchestrator_integration(self):
        """Test enhanced rate limiting integration with orchestrator."""
        # Create config with very low limits for testing
        rate_config = RateLimitConfig()
        rate_config.max_cycles_per_hour = 2
        rate_config.action_limits['WaitTool'] = 1
        
        config = OrchestratorConfig(rate_limit_config=rate_config)
        
        with patch('chatbot.config.settings') as mock_settings:
            mock_settings.OPENROUTER_API_KEY = "test_key"
            mock_settings.MATRIX_USER_ID = "test_user"
            
            orchestrator = ContextAwareOrchestrator(config)
            
            # Test rate limit status retrieval
            status = orchestrator.get_rate_limit_status()
            assert 'cycles_per_hour' in status
            assert 'max_cycles_per_hour' in status
            assert status['max_cycles_per_hour'] == 2

    @pytest.mark.asyncio 
    async def test_action_execution_rate_limiting(self):
        """Test that action execution respects rate limits."""
        rate_config = RateLimitConfig()
        rate_config.action_limits['TestActionTool'] = 1  # Very low limit
        
        config = OrchestratorConfig(rate_limit_config=rate_config)
        
        with patch('chatbot.config.settings') as mock_settings:
            mock_settings.OPENROUTER_API_KEY = "test_key"
            mock_settings.MATRIX_USER_ID = "test_user"
            
            orchestrator = ContextAwareOrchestrator(config)
            
            # Mock the context manager to avoid database operations
            orchestrator.context_manager = MagicMock()
            orchestrator.context_manager.add_tool_result = AsyncMock()
            
            # Create a mock action
            action = MagicMock()
            action.action_type = 'TestActionTool'
            action.parameters = {'channel_id': 'test_channel'}
            
            # First execution should work (no tool registered, but rate limiting should pass)
            await orchestrator._execute_action(action)
            
            # Second execution should be rate limited
            await orchestrator._execute_action(action)
            
            # Check that rate limiting was recorded
            assert orchestrator.context_manager.add_tool_result.call_count == 2
            # Second call should be rate limited
            second_call_args = orchestrator.context_manager.add_tool_result.call_args_list[1]
            result = second_call_args[0][2]  # Third argument is the result dict
            assert 'rate_limited' in result.get('status', '') or 'Rate limited' in result.get('error', '')

    def test_rate_limit_logging(self):
        """Test rate limit status logging."""
        rate_config = RateLimitConfig()
        config = OrchestratorConfig(rate_limit_config=rate_config)
        
        with patch('chatbot.config.settings') as mock_settings:
            mock_settings.OPENROUTER_API_KEY = "test_key"
            mock_settings.MATRIX_USER_ID = "test_user"
            
            orchestrator = ContextAwareOrchestrator(config)
            
            # Test that logging doesn't crash
            with patch('chatbot.core.orchestrator.logger') as mock_logger:
                orchestrator.log_rate_limit_status()
                assert mock_logger.info.called

    def test_messaging_tool_channel_rate_limiting(self):
        """Test that messaging tools trigger channel-specific rate limiting."""
        config = RateLimitConfig()
        config.channel_limits['matrix'] = 1  # Very low limit
        limiter = EnhancedRateLimiter(config)
        current_time = time.time()
        
        # First Matrix message should be allowed
        can_send, reason = limiter.can_send_to_channel('test_room', 'matrix', current_time)
        assert can_send is True
        limiter.record_channel_message('test_room', current_time)
        
        # Second Matrix message to same room should be blocked
        can_send, reason = limiter.can_send_to_channel('test_room', 'matrix', current_time + 1)
        assert can_send is False
        assert "Channel rate limit exceeded" in reason


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
