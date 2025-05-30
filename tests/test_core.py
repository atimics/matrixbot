"""
Test suite for the chatbot core functionality.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
import time

from chatbot.core.world_state import WorldStateManager
from chatbot.core.context import ContextManager
from chatbot.core.orchestrator import ContextAwareOrchestrator, OrchestratorConfig
from chatbot.core.ai_engine import AIDecisionEngine


class TestWorldState:
    """Test the world state management."""
    
    def test_initialization(self):
        """Test world state manager initialization."""
        world_state = WorldStateManager()
        state_dict = world_state.to_dict()
        
        # Check that required keys exist
        assert "channels" in state_dict
        assert "action_history" in state_dict
        assert "system_status" in state_dict
        assert "last_update" in state_dict
        
        # Check initial values
        assert state_dict["channels"] == {}
        assert state_dict["action_history"] == []
        assert isinstance(state_dict["system_status"], dict)
    
    def test_add_channel(self):
        """Test adding a channel to world state."""
        world_state = WorldStateManager()
        world_state.add_channel("matrix", "test_channel", "Test Channel")
        
        state_dict = world_state.to_dict()
        assert "matrix" in state_dict["channels"]
        assert state_dict["channels"]["matrix"]["name"] == "Test Channel"
        assert state_dict["channels"]["matrix"]["id"] == "matrix"
    
    def test_add_message(self):
        """Test adding a message to a channel."""
        world_state = WorldStateManager()
        world_state.add_channel("test_channel", "matrix", "Test Channel")
        
        # Create a proper message object with required attributes
        from chatbot.core.world_state import Message
        message = Message(
            id="msg_123",
            content="Hello world",
            sender="@user:example.com",
            timestamp=time.time(),
            channel_id="test_channel",
            channel_type="matrix"
        )
        
        world_state.add_message("test_channel", message)
        
        state_dict = world_state.to_dict()
        # Check the actual structure - channels are keyed by channel_id
        assert "test_channel" in state_dict["channels"]
        channel = state_dict["channels"]["test_channel"]
        assert len(channel["recent_messages"]) == 1
        assert channel["recent_messages"][0]["content"] == "Hello world"


class TestContextManager:
    """Test the context management functionality."""
    
    @pytest.fixture
    def world_state(self):
        """Create a world state manager for testing."""
        return WorldStateManager()
    
    @pytest.fixture
    def context_manager(self, world_state):
        """Create a context manager for testing."""
        return ContextManager(world_state, ":memory:")  # Use in-memory SQLite
    
    @pytest.mark.asyncio
    async def test_initialization(self, context_manager):
        """Test context manager initialization."""
        assert context_manager.db_path == ":memory:"
        assert context_manager.world_state is not None
    
    @pytest.mark.asyncio
    async def test_add_user_message(self, context_manager):
        """Test adding a user message."""
        channel_id = "test_channel"
        message = {
            "content": "Hello",
            "sender": "@user:example.com",
            "timestamp": time.time()
        }
        
        await context_manager.add_user_message(channel_id, message)
        
        # Verify the message was stored
        messages = await context_manager.get_conversation_messages(channel_id)
        assert len(messages) >= 1
        # Check that user message is in the conversation
        user_messages = [msg for msg in messages if msg.get("role") == "user"]
        assert len(user_messages) >= 1


class TestAIEngine:
    """Test the AI decision engine."""
    
    def test_initialization(self):
        """Test AI engine initialization."""
        engine = AIDecisionEngine("fake_api_key", "fake_model")
        assert engine.api_key == "fake_api_key"
        assert engine.model == "fake_model"
    
    @pytest.mark.asyncio
    async def test_make_decision_with_mock(self):
        """Test AI decision making with mocked response."""
        engine = AIDecisionEngine("fake_api_key", "fake_model")
        
        # Mock the HTTP client response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": '{"reasoning": "Test decision", "selected_actions": []}'
                }
            }]
        }
        
        with patch('httpx.AsyncClient.post', return_value=mock_response):
            world_state = {"channels": {}, "system": {}}
            decision = await engine.make_decision(world_state, "test_cycle")
            
            assert decision is not None
            assert decision.reasoning == "Test decision"
            assert decision.selected_actions == []


class TestOrchestrator:
    """Test the main orchestrator."""
    
    def test_initialization(self):
        """Test orchestrator initialization."""
        config = OrchestratorConfig(db_path=":memory:")
        orchestrator = ContextAwareOrchestrator(config)
        
        assert orchestrator.config.db_path == ":memory:"
        assert orchestrator.world_state is not None
        assert orchestrator.context_manager is not None
        assert orchestrator.ai_engine is not None
        assert orchestrator.action_executor is not None
        assert not orchestrator.running
    
    def test_config_defaults(self):
        """Test default configuration values."""
        config = OrchestratorConfig()
        
        assert config.db_path == "chatbot.db"
        assert config.observation_interval == 2.0
        assert config.max_cycles_per_hour == 300
        assert config.ai_model == "openai/gpt-4o-mini"
    
    @pytest.mark.asyncio
    async def test_start_stop_without_observers(self):
        """Test starting and stopping orchestrator without external services."""
        config = OrchestratorConfig(db_path=":memory:")
        orchestrator = ContextAwareOrchestrator(config)
        
        # Mock the observers initialization to avoid actual network calls
        with patch.object(orchestrator, '_initialize_observers', new_callable=AsyncMock):
            with patch.object(orchestrator, '_main_event_loop', new_callable=AsyncMock) as mock_loop:
                mock_loop.side_effect = KeyboardInterrupt()  # Simulate Ctrl+C
                
                try:
                    await orchestrator.start()
                except KeyboardInterrupt:
                    pass
                
                assert not orchestrator.running


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
