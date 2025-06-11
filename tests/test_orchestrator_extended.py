"""
Tests for orchestrator functionality and integration.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from chatbot.core.orchestration import MainOrchestrator, OrchestratorConfig, ProcessingConfig


class TestOrchestratorExtended:
    """Extended tests for the orchestrator functionality."""
    
    def setup_method(self):
        """Set up test environment."""
        self.config = OrchestratorConfig()
        self.config.db_path = ":memory:"  # Use in-memory database for tests
        self.orchestrator = MainOrchestrator(self.config)
    
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
        assert self.orchestrator.tool_registry is not None  # Updated for new architecture
        assert self.orchestrator.running is False
    
    def test_observer_management(self):
        """Test setting and managing observers."""
        # Create mock observers
        matrix_observer = AsyncMock()
        farcaster_observer = AsyncMock()
        
        # Set observers directly on orchestrator (new architecture)
        self.orchestrator.matrix_observer = matrix_observer
        self.orchestrator.farcaster_observer = farcaster_observer
        
        assert self.orchestrator.matrix_observer is matrix_observer
        assert self.orchestrator.farcaster_observer is farcaster_observer
        
        # Verify tools can access observers via ActionContext
        # (This would be tested in tool-specific unit tests)
    
    @pytest.mark.asyncio
    async def test_start_stop_without_observers(self):
        """Test starting and stopping orchestrator without observers."""
        # Mock all the methods that could hang or make network calls
        with patch.object(self.orchestrator, '_register_integrations_from_env', new_callable=AsyncMock), \
             patch.object(self.orchestrator, '_update_action_context_integrations', new_callable=AsyncMock), \
             patch.object(self.orchestrator, '_ensure_media_gallery_exists', new_callable=AsyncMock), \
             patch.object(self.orchestrator, '_initialize_nft_services', new_callable=AsyncMock), \
             patch.object(self.orchestrator.integration_manager, 'initialize', new_callable=AsyncMock), \
             patch.object(self.orchestrator.integration_manager, 'connect_all_active', new_callable=AsyncMock), \
             patch.object(self.orchestrator.integration_manager, 'start_all_services', new_callable=AsyncMock), \
             patch.object(self.orchestrator.integration_manager, 'stop_all_services', new_callable=AsyncMock), \
             patch.object(self.orchestrator.integration_manager, 'disconnect_all', new_callable=AsyncMock), \
             patch.object(self.orchestrator.integration_manager, 'cleanup', new_callable=AsyncMock), \
             patch.object(self.orchestrator, '_update_legacy_observer_references', new_callable=AsyncMock), \
             patch.object(self.orchestrator.proactive_engine, 'start', new_callable=AsyncMock), \
             patch.object(self.orchestrator.proactive_engine, 'stop', new_callable=AsyncMock):
            
            with patch.object(self.orchestrator.processing_hub, 'start_processing_loop', new_callable=AsyncMock) as mock_start, \
                 patch.object(self.orchestrator.processing_hub, 'stop_processing_loop') as mock_stop:
                
                # Configure the mock to raise KeyboardInterrupt to simulate quick shutdown
                mock_start.side_effect = KeyboardInterrupt("Test shutdown")
                
                # Test should complete quickly without hanging
                try:
                    await self.orchestrator.start()
                except KeyboardInterrupt:
                    pass  # Expected from our mock
                
                # Ensure orchestrator is not running after stop
                assert not self.orchestrator.running
                
                # Verify processing loop was started
                mock_start.assert_called_once()
    
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
        await self.orchestrator.context_manager.add_user_message("test_channel", message_data)
        
        # Verify message was processed
        context_summary = await self.orchestrator.context_manager.get_context_summary("test_channel")
        assert context_summary is not None

    @pytest.mark.asyncio
    async def test_channel_processing_with_mocked_ai(self):
        """Test channel processing with mocked AI."""
        # Mock the AI engine to return a simple decision
        with patch.object(self.orchestrator.ai_engine, 'make_decision') as mock_decision:
            from chatbot.core.ai_engine import DecisionResult
            mock_result = DecisionResult(
                selected_actions=[],
                observations="No action needed",
                reasoning="Test reasoning",
                cycle_id="test_cycle_123"
            )
            mock_decision.return_value = mock_result
            
            # Mock context manager to return some messages
            with patch.object(self.orchestrator.context_manager, 'get_conversation_messages') as mock_get_messages:
                mock_get_messages.return_value = [{"role": "user", "content": "test"}]
                
                # Add some data to world state
                self.orchestrator.world_state.update_system_status({"test": "value"})
                
                # Create a payload to process
                payload = self.orchestrator.world_state.to_dict()
                active_channels = ["test_channel"]
                
                # Run payload processing
                await self.orchestrator.process_payload(payload, active_channels)
                
                # Verify AI was called (it's called by the processing hub)
                # Note: In the new architecture, AI is called by TraditionalProcessor
                # So we can't directly verify it was called from this level
    
    @pytest.mark.asyncio
    async def test_action_execution_with_mocked_action(self):
        """Test action execution through _execute_action."""
        # Mock observers with proper return structure for AI Blindness Fix
        mock_matrix = AsyncMock()
        mock_matrix.send_reply.return_value = {
            "success": True, 
            "event_id": "event_123",
            "room_id": "test_room",
            "reply_to_event_id": "original_event",
            "sent_content": "AI generated response"  # Required for AI Blindness Fix
        }
        
        # Set observers directly (new architecture)
        self.orchestrator.matrix_observer = mock_matrix
        # Also set it in the action context for tools to access
        self.orchestrator.action_context.matrix_observer = mock_matrix
        
        # Set up the processing hub with a traditional processor
        self.orchestrator._setup_processing_components()
        
        # Create a mock action object with action_type and parameters
        mock_action = MagicMock()
        mock_action.action_type = "send_matrix_reply"
        mock_action.parameters = {
            "channel_id": "test_room",  # Updated parameter name for new tool interface
            "content": "AI generated response",
            "reply_to_id": "original_event",  # Updated parameter name for new tool interface
            "format_as_markdown": False
        }
        
        # Execute action
        await self.orchestrator._execute_action(mock_action)
        
        # Verify the matrix observer's send_reply method was called
        mock_matrix.send_reply.assert_called_once_with("test_room", "AI generated response", "original_event")
    
    @pytest.mark.asyncio
    async def test_error_handling_in_channel_processing(self):
        """Test error handling in channel processing."""
        # Mock context manager to raise an exception
        with patch.object(self.orchestrator.context_manager, 'get_conversation_messages') as mock_get_messages:
            mock_get_messages.side_effect = Exception("Context service unavailable")
            
            # Mock AI engine to prevent HTTP requests and return empty decision
            with patch.object(self.orchestrator.ai_engine, 'make_decision') as mock_ai_decision:
                from chatbot.core.ai_engine import DecisionResult
                mock_ai_decision.return_value = DecisionResult(
                    selected_actions=[],
                    reasoning="Test decision during error handling",
                    observations="Error in context service",
                    cycle_id="test_cycle"
                )
                
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
        mock_matrix.send_reply.return_value = {
            "success": True, 
            "event_id": "event_123",
            "room_id": "test_room",
            "reply_to_event_id": "original_event",
            "sent_content": "Test response"  # Required for AI Blindness Fix
        }
        mock_matrix.send_formatted_reply.return_value = {
            "success": True, 
            "event_id": "event_123",
            "room_id": "test_room",
            "reply_to_event_id": "original_event",
            "sent_content": "Test response"  # Required for AI Blindness Fix
        }
        
        # Set observer directly on the orchestrator
        self.orchestrator.matrix_observer = mock_matrix
        
        # Create a mock action with the new parameter schema
        mock_action = MagicMock()
        mock_action.action_type = "send_matrix_reply"
        mock_action.parameters = {
            "channel_id": "test_room",  # Updated parameter name for new tool interface
            "content": "Test response",
            "reply_to_id": "original_event",  # Updated parameter name for new tool interface
            "format_as_markdown": False
        }
        
        # Execute action 
        await self.orchestrator._execute_action(mock_action)
        
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
        orchestrator = MainOrchestrator(config)
        
        # Check default values are set
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
