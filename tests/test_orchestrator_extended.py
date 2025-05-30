"""
Tests for orchestrator functionality and integration.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from chatbot.core.orchestrator import ContextAwareOrchestrator, OrchestratorConfig


class TestOrchestratorExtended:
    """Extended tests for the orchestrator functionality."""
    
    def setup_method(self):
        """Set up test environment."""
        self.config = OrchestratorConfig()
        self.config.db_path = ":memory:"  # Use in-memory database for tests
        self.orchestrator = ContextAwareOrchestrator(self.config)
    
    def teardown_method(self):
        """Clean up test environment."""
        if hasattr(self, 'orchestrator'):
            # Don't call cleanup() as it's async - just clean up manually
            pass
    
    def test_initialization_with_config(self):
        """Test orchestrator initialization with custom config."""
        assert self.orchestrator.config is self.config
        assert self.orchestrator.world_state is not None
        assert self.orchestrator.context_manager is not None
        assert self.orchestrator.ai_engine is not None
        assert self.orchestrator.action_executor is not None
        assert self.orchestrator.running is False
    
    def test_observer_management(self):
        """Test setting and managing observers."""
        # Create mock observers
        matrix_observer = AsyncMock()
        farcaster_observer = AsyncMock()
        
        # Set observers
        self.orchestrator.set_observers(matrix_observer, farcaster_observer)
        
        assert self.orchestrator.matrix_observer is matrix_observer
        assert self.orchestrator.farcaster_observer is farcaster_observer
        
        # Verify observers are set on action executor
        assert self.orchestrator.action_executor.matrix_observer is matrix_observer
        assert self.orchestrator.action_executor.farcaster_observer is farcaster_observer
    
    @pytest.mark.asyncio
    async def test_start_stop_without_observers(self):
        """Test starting and stopping orchestrator without observers."""
        # Start orchestrator
        await self.orchestrator.start()
        
        assert self.orchestrator.running is True
        assert self.orchestrator.decision_task is not None
        
        # Stop orchestrator
        await self.orchestrator.stop()
        
        assert self.orchestrator.running is False
        assert self.orchestrator.decision_task is None
    
    @pytest.mark.asyncio
    async def test_message_processing(self):
        """Test processing incoming messages."""
        # Create a test message
        from chatbot.core.world_state import Message
        import time
        
        message = Message(
            id="test_msg_1",
            content="Hello bot!",
            sender="@user:example.com",
            timestamp=time.time(),
            channel_id="test_channel",
            channel_type="matrix"
        )
        
        # Process message
        await self.orchestrator.process_message(message)
        
        # Verify message was added to world state
        all_messages = self.orchestrator.world_state.get_all_messages()
        assert len(all_messages) == 1
        assert all_messages[0].content == "Hello bot!"
        assert all_messages[0].sender == "@user:example.com"
    
    @pytest.mark.asyncio 
    async def test_decision_cycle_with_mocked_ai(self):
        """Test a single decision cycle with mocked AI."""
        # Mock the AI engine to return a simple decision
        self.orchestrator.ai_engine.make_decision = AsyncMock(return_value={
            "should_act": False,
            "reasoning": "No action needed"
        })
        
        # Add some data to world state
        self.orchestrator.world_state.update_system_status({"test": "value"})
        
        # Run one decision cycle
        await self.orchestrator._decision_cycle()
        
        # Verify AI was called
        self.orchestrator.ai_engine.make_decision.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_decision_cycle_with_action(self):
        """Test decision cycle that results in an action."""
        # Mock observers
        mock_matrix = AsyncMock()
        mock_matrix.send_reply.return_value = {"success": True, "event_id": "event_123"}
        self.orchestrator.set_observers(mock_matrix, None)
        
        # Mock AI to decide on an action
        self.orchestrator.ai_engine.make_decision = AsyncMock(return_value={
            "should_act": True,
            "action_type": "send_matrix_reply",
            "parameters": {
                "channel_id": "test_room",
                "content": "AI generated response",
                "reply_to_event_id": "original_event"
            },
            "reasoning": "User asked a question"
        })
        
        # Run decision cycle
        await self.orchestrator._decision_cycle()
        
        # Verify action was executed
        mock_matrix.send_reply.assert_called_once_with(
            "test_room", 
            "AI generated response", 
            "original_event"
        )
    
    @pytest.mark.asyncio
    async def test_decision_cycle_error_handling(self):
        """Test error handling in decision cycle."""
        # Mock AI to raise an exception
        self.orchestrator.ai_engine.make_decision = AsyncMock(
            side_effect=Exception("AI service unavailable")
        )
        
        # Decision cycle should handle the error gracefully
        await self.orchestrator._decision_cycle()
        
        # Orchestrator should still be in a valid state
        assert self.orchestrator.world_state is not None
    
    @pytest.mark.asyncio
    async def test_context_integration(self):
        """Test integration between world state and context manager."""
        # Process a user message
        from chatbot.core.world_state import Message
        import time
        
        user_message = Message(
            id="user_msg_1",
            content="What's the weather?",
            sender="@alice:example.com",
            timestamp=time.time(),
            channel_id="general",
            channel_type="matrix"
        )
        
        await self.orchestrator.process_message(user_message)
        
        # Verify message is in world state
        all_messages = self.orchestrator.world_state.get_all_messages()
        assert len(all_messages) == 1
        
        # Verify context is updated
        context = self.orchestrator.context_manager.get_context_for_user(
            "@alice:example.com", "general"
        )
        assert len(context["messages"]) == 1
        assert context["messages"][0]["content"] == "What's the weather?"
    
    @pytest.mark.asyncio
    async def test_action_execution_and_history(self):
        """Test that executed actions are recorded in history."""
        # Mock matrix observer
        mock_matrix = AsyncMock()
        mock_matrix.send_reply.return_value = {"success": True, "event_id": "event_123"}
        self.orchestrator.set_observers(mock_matrix, None)
        
        # Execute an action directly
        action_params = {
            "channel_id": "test_room",
            "content": "Test response",
            "reply_to_event_id": "original_event"
        }
        
        await self.orchestrator._execute_action("send_matrix_reply", action_params)
        
        # Verify action is in world state history
        state_dict = self.orchestrator.world_state.to_dict()
        assert len(state_dict["action_history"]) == 1
        assert state_dict["action_history"][0]["action_type"] == "send_matrix_reply"
    
    @pytest.mark.asyncio
    async def test_system_status_updates(self):
        """Test system status updates during operation."""
        # Start orchestrator briefly
        await self.orchestrator.start()
        
        # Check that system status is being updated
        state_dict = self.orchestrator.world_state.to_dict()
        
        assert "total_cycles" in state_dict["system_status"]
        assert "last_observation_cycle" in state_dict["system_status"]
        assert state_dict["system_status"]["total_cycles"] >= 0
        
        await self.orchestrator.stop()
    
    def test_config_defaults(self):
        """Test that configuration defaults are applied correctly."""
        config = OrchestratorConfig()
        orchestrator = ContextAwareOrchestrator(config)
        
        # Check default values are set
        assert orchestrator.decision_interval >= 1.0  # Should have reasonable default
        assert orchestrator.config.ai_model is not None
    
    @pytest.mark.asyncio
    async def test_cleanup_process(self):
        """Test the cleanup process."""
        # Mock cleanup methods
        self.orchestrator.ai_engine.cleanup = AsyncMock()
        self.orchestrator.context_manager.cleanup = MagicMock()
        
        await self.orchestrator.cleanup()
        
        # Verify cleanup was called on components
        self.orchestrator.ai_engine.cleanup.assert_called_once()
        self.orchestrator.context_manager.cleanup.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
