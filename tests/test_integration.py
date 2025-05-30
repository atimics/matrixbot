"""
Integration tests for the chatbot system.
"""

import pytest
import asyncio
import time
from unittest.mock import patch, AsyncMock

from chatbot.core.world_state import WorldStateManager
from chatbot.core.context import ContextManager
from chatbot.core.orchestrator import ContextAwareOrchestrator, OrchestratorConfig


class TestIntegration:
    """Integration tests for the chatbot system."""
    
    @pytest.mark.asyncio
    async def test_basic_workflow(self):
        """Test a basic chatbot workflow without external services."""
        # Create orchestrator with in-memory database
        config = OrchestratorConfig(
            db_path=":memory:",
            observation_interval=0.1,
            max_cycles_per_hour=3600,
            ai_model="test_model"
        )
        
        orchestrator = ContextAwareOrchestrator(config)
        
        # Test basic initialization
        assert not orchestrator.running
        assert orchestrator.world_state is not None
        assert orchestrator.context_manager is not None
        
        # Add a test message
        test_message = {
            "content": "Hello, chatbot!",
            "sender": "@user:test.com",
            "timestamp": time.time(),
            "channel_id": "test_channel"
        }
        
        await orchestrator.add_user_message("test_channel", test_message)
        
        # Get context summary
        summary = await orchestrator.get_context_summary("test_channel")
        assert isinstance(summary, dict)
    
    @pytest.mark.asyncio
    async def test_world_state_updates(self):
        """Test world state management."""
        world_state = WorldStateManager()
        
        # Test adding a channel
        world_state.add_channel("matrix", "test_room", "Test Room")
        
        state_dict = world_state.to_dict()
        assert "matrix" in state_dict["channels"]
        assert state_dict["channels"]["matrix"]["name"] == "Test Room"
        
        # Test updating system status
        world_state.update_system_status({"test_status": True})
        
        updated_state = world_state.to_dict()
        assert updated_state["system_status"]["test_status"] is True
    
    @pytest.mark.asyncio
    async def test_context_management(self):
        """Test context management functionality."""
        world_state = WorldStateManager()
        context_manager = ContextManager(world_state, ":memory:")
        
        # Add a user message
        test_message = {
            "content": "Test message",
            "sender": "@user:test.com",
            "timestamp": time.time(),
            "channel_id": "test_channel"
        }
        
        await context_manager.add_user_message("test_channel", test_message)
        
        # Get conversation messages
        messages = await context_manager.get_conversation_messages("test_channel")
        assert len(messages) >= 1
        
        # Get context summary
        summary = await context_manager.get_context_summary("test_channel")
        assert "channel_id" in summary
        assert summary["channel_id"] == "test_channel"
    
    @pytest.mark.asyncio 
    async def test_orchestrator_without_observers(self):
        """Test orchestrator functionality without external observers."""
        config = OrchestratorConfig(db_path=":memory:")
        orchestrator = ContextAwareOrchestrator(config)
        
        # Mock the observers initialization and main loop
        with patch.object(orchestrator, '_initialize_observers', new_callable=AsyncMock):
            with patch.object(orchestrator, '_main_event_loop', new_callable=AsyncMock) as mock_loop:
                # Mock the event loop to run briefly then stop
                async def mock_event_loop():
                    await asyncio.sleep(0.01)
                    orchestrator.running = False
                
                mock_loop.side_effect = mock_event_loop
                
                # Start and test
                await orchestrator.start()
                
                # Should have completed without errors
                assert not orchestrator.running
    
    @pytest.mark.asyncio
    async def test_state_change_detection(self):
        """Test state change detection."""
        orchestrator = ContextAwareOrchestrator(OrchestratorConfig(db_path=":memory:"))
        
        # Get initial state hash
        initial_state = orchestrator.world_state.to_dict()
        initial_hash = orchestrator._hash_state(initial_state)
        
        # Make a change to the world state
        orchestrator.world_state.add_channel("matrix", "new_channel", "New Channel")
        
        # Get new state hash
        new_state = orchestrator.world_state.to_dict()
        new_hash = orchestrator._hash_state(new_state)
        
        # Hashes should be different
        assert initial_hash != new_hash
    
    @pytest.mark.asyncio
    async def test_training_data_export(self):
        """Test exporting training data."""
        world_state = WorldStateManager()
        context_manager = ContextManager(world_state, ":memory:")
        
        # Add some test data
        test_message = {
            "content": "Training message",
            "sender": "@user:test.com", 
            "timestamp": time.time(),
            "channel_id": "training_channel"
        }
        
        await context_manager.add_user_message("training_channel", test_message)
        
        # Test exporting (this creates a file but we won't verify file contents in unit test)
        output_path = "/tmp/test_training_export.jsonl"
        result = await context_manager.export_state_changes_for_training(output_path)
        
        # Should return a status message
        assert isinstance(result, str)
        assert "export" in result.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
