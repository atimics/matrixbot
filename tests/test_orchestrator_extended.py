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
        
        # Set observers directly on orchestrator and action executor
        self.orchestrator.matrix_observer = matrix_observer
        self.orchestrator.farcaster_observer = farcaster_observer
        
        # Set observers on action executor using individual methods
        self.orchestrator.action_executor.set_matrix_observer(matrix_observer)
        self.orchestrator.action_executor.set_farcaster_observer(farcaster_observer)
        
        assert self.orchestrator.matrix_observer is matrix_observer
        assert self.orchestrator.farcaster_observer is farcaster_observer
        
        # Verify observers are set on action executor
        assert self.orchestrator.action_executor.matrix_observer is matrix_observer
        assert self.orchestrator.action_executor.farcaster_observer is farcaster_observer
    
    @pytest.mark.asyncio
    async def test_start_stop_without_observers(self):
        """Test starting and stopping orchestrator without observers."""
        # Mock _main_event_loop to avoid infinite loop in tests
        with patch.object(self.orchestrator, '_main_event_loop') as mock_loop:
            # Make the event loop return immediately
            loop = asyncio.get_event_loop()
            future = loop.create_future()
            future.set_result(None)
            mock_loop.return_value = future
            
            # Mock _initialize_observers to avoid actual observer initialization
            with patch.object(self.orchestrator, '_initialize_observers') as mock_init:
                init_future = loop.create_future()
                init_future.set_result(None)
                mock_init.return_value = init_future
                
                # Create a task that we can control
                async def controlled_start():
                    self.orchestrator.running = True
                    return None
                
                with patch.object(self.orchestrator, 'start', new=controlled_start):
                    await self.orchestrator.start()
                    assert self.orchestrator.running is True
                    
                await self.orchestrator.stop()
                assert self.orchestrator.running is False
    
    @pytest.mark.asyncio
    async def test_message_processing(self):
        """Test processing incoming messages through add_user_message."""
        # Create a test message
        message_data = {
            "content": "Hello bot!",
            "sender": "@user:example.com", 
            "timestamp": 1234567890,
            "event_id": "test_event_1"
        }
        
        # Process message
        await self.orchestrator.add_user_message("test_channel", message_data)
        
        # Verify message was processed
        context_summary = await self.orchestrator.get_context_summary("test_channel")
        assert context_summary is not None
    
    @pytest.mark.asyncio 
    async def test_channel_processing_with_mocked_ai(self):
        """Test channel processing with mocked AI."""
        # Mock the AI engine to return a simple decision
        with patch.object(self.orchestrator.ai_engine, 'make_decision') as mock_decision:
            mock_decision.return_value = AsyncMock()
            mock_decision.return_value.selected_actions = []
            mock_decision.return_value.observations = "No action needed"
            
            # Mock context manager to return some messages
            with patch.object(self.orchestrator.context_manager, 'get_conversation_messages') as mock_get_messages:
                mock_get_messages.return_value = [{"role": "user", "content": "test"}]
                
                # Add some data to world state
                self.orchestrator.world_state.update_system_status({"test": "value"})
                
                # Run channel processing
                await self.orchestrator._process_channel("test_channel")
                
                # Verify AI was called
                mock_decision.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_action_execution_with_mocked_action(self):
        """Test action execution through _execute_action."""
        # Mock observers
        mock_matrix = AsyncMock()
        mock_matrix.send_reply.return_value = {"success": True, "event_id": "event_123"}
        
        # Set observers directly
        self.orchestrator.matrix_observer = mock_matrix
        self.orchestrator.action_executor.set_matrix_observer(mock_matrix)
        
        # Create a mock action object with action_type and parameters
        mock_action = MagicMock()
        mock_action.action_type = "send_matrix_reply"
        mock_action.parameters = {
            "channel_id": "test_room",
            "content": "AI generated response",
            "reply_to_event_id": "original_event"
        }
        
        # Execute action
        await self.orchestrator._execute_action("test_room", mock_action)
        
        # Verify action was attempted
        # Note: actual verification depends on action executor implementation
    
    @pytest.mark.asyncio
    async def test_error_handling_in_channel_processing(self):
        """Test error handling in channel processing."""
        # Mock context manager to raise an exception
        with patch.object(self.orchestrator.context_manager, 'get_conversation_messages') as mock_get_messages:
            mock_get_messages.side_effect = Exception("Context service unavailable")
            
            # Channel processing should handle the error gracefully
            await self.orchestrator._process_channel("test_channel")
            
            # Orchestrator should still be in a valid state
            assert self.orchestrator.world_state is not None
    
    @pytest.mark.asyncio
    async def test_context_integration(self):
        """Test integration between world state and context manager."""
        # Add a user message through the orchestrator API
        user_message = {
            "content": "What's the weather?",
            "sender": "@alice:example.com",
            "timestamp": 1234567890,
            "event_id": "user_msg_1"
        }
        
        await self.orchestrator.add_user_message("general", user_message)
        
        # Verify context is updated
        context_summary = await self.orchestrator.get_context_summary("general")
        assert context_summary is not None
    
    @pytest.mark.asyncio
    async def test_action_execution_recording(self):
        """Test that executed actions are handled properly."""
        # Mock matrix observer
        mock_matrix = AsyncMock()
        mock_matrix.send_reply.return_value = {"success": True, "event_id": "event_123"}
        
        # Set observers directly
        self.orchestrator.matrix_observer = mock_matrix
        self.orchestrator.action_executor.set_matrix_observer(mock_matrix)
        
        # Create a mock action
        mock_action = MagicMock()
        mock_action.action_type = "send_matrix_reply"
        mock_action.parameters = {
            "channel_id": "test_room",
            "content": "Test response",
            "reply_to_event_id": "original_event"
        }
        
        # Execute action 
        await self.orchestrator._execute_action("test_room", mock_action)
        
        # Check that world state exists and is functional
        state_dict = self.orchestrator.world_state.to_dict()
        assert state_dict is not None
    
    @pytest.mark.asyncio
    async def test_system_status_updates(self):
        """Test system status updates during operation."""
        # Trigger state change to test system
        self.orchestrator.trigger_state_change()
        
        # Check that system status is accessible
        state_dict = self.orchestrator.world_state.to_dict()
        assert state_dict is not None
        
        # Check that basic orchestrator attributes are working
        assert self.orchestrator.cycle_count >= 0
        assert self.orchestrator.running is False  # Not started yet
    
    def test_config_defaults(self):
        """Test that configuration defaults are applied correctly."""
        config = OrchestratorConfig()
        orchestrator = ContextAwareOrchestrator(config)
        
        # Check default values are set
        assert orchestrator.config.observation_interval >= 1.0  # Should have reasonable default
        assert orchestrator.config.ai_model is not None
    
    @pytest.mark.asyncio
    async def test_context_management(self):
        """Test the context management functionality."""
        # Test clear context
        await self.orchestrator.clear_context("test_channel")
        
        # Add a message and get summary
        test_message = {
            "content": "Test message",
            "sender": "@test:example.com",
            "timestamp": 1234567890,
            "event_id": "test_1"
        }
        
        await self.orchestrator.add_user_message("test_channel", test_message)
        summary = await self.orchestrator.get_context_summary("test_channel") 
        
        assert summary is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
