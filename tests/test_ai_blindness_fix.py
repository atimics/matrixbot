#!/usr/bin/env python3
"""
Test for AI Blindness Fix

This test verifies that the bot's messages are properly recorded
in both WorldStateManager and ContextManager so the AI can see its own messages.
"""

import asyncio
import pytest
import time
from unittest.mock import Mock, AsyncMock, patch

from chatbot.core.orchestrator import ContextAwareOrchestrator, OrchestratorConfig
from chatbot.core.ai_engine import ActionPlan
from chatbot.config import settings


class TestAIBlindnessFix:
    """Test the AI blindness fix implementation."""
    
    @pytest.fixture
    def orchestrator(self):
        """Create a test orchestrator."""
        config = OrchestratorConfig(db_path=":memory:")
        return ContextAwareOrchestrator(config)
    
    @pytest.fixture
    def mock_matrix_observer(self):
        """Create a mock matrix observer with flexible return values."""
        observer = Mock()
        
        # Create a function that returns appropriate content based on the call
        def make_reply_return(*args, **kwargs):
            content = kwargs.get("content", "default test content")
            reply_to = kwargs.get("reply_to_event_id", "default_reply_to")
            room_id = kwargs.get("room_id", "!test:example.com")
            return {
                "success": True,
                "event_id": "test_event_123",
                "room_id": room_id,
                "reply_to_event_id": reply_to,
                "sent_content": content,
                "error": None
            }
            
        def make_message_return(*args, **kwargs):
            content = kwargs.get("content", "default test content")
            room_id = kwargs.get("room_id", "!test:example.com")
            return {
                "success": True,
                "event_id": "test_event_456",
                "room_id": room_id,
                "sent_content": content,
                "error": None
            }
        
        observer.send_reply = AsyncMock(side_effect=make_reply_return)
        observer.send_formatted_reply = AsyncMock(side_effect=make_reply_return)
        observer.send_message = AsyncMock(side_effect=make_message_return)
        observer.send_formatted_message = AsyncMock(side_effect=make_message_return)
        return observer
    
    @pytest.mark.asyncio
    async def test_matrix_reply_recorded_in_world_state(self, orchestrator, mock_matrix_observer):
        """Test that bot's matrix reply is recorded in WorldStateManager."""
        # Setup - set the matrix observer directly on the orchestrator
        orchestrator.matrix_observer = mock_matrix_observer
        channel_id = "!test:example.com"
        test_content = "This is a test reply"
        
        # Create action
        action = ActionPlan(
            action_type="send_matrix_reply",
            parameters={
                "channel_id": channel_id,  # Updated parameter name for new tool interface
                "content": test_content,
                "reply_to_id": "original_event_123"  # Updated parameter name for new tool interface
            },
            reasoning="Test action",
            priority=5
        )
        
        # Execute action
        await orchestrator._execute_action(action)
        
        # Verify the message was added to world state
        world_state_data = orchestrator.world_state.to_dict()
        
        assert "channels" in world_state_data
        assert channel_id in world_state_data["channels"]
        
        channel_data = world_state_data["channels"][channel_id]
        messages = channel_data.get("recent_messages", [])
        
        # Find the bot's message
        bot_messages = [msg for msg in messages if msg.get("sender") == settings.MATRIX_USER_ID]
        assert len(bot_messages) == 1
        
        bot_message = bot_messages[0]
        assert bot_message["content"] == test_content
        assert bot_message["id"] == "test_event_123"
        assert bot_message["reply_to"] == "original_event_123"
        assert bot_message["channel_type"] == "matrix"
    
    @pytest.mark.asyncio
    async def test_matrix_reply_recorded_in_context(self, orchestrator, mock_matrix_observer):
        """Test that bot's matrix reply is recorded in ContextManager."""
        # Setup - set the matrix observer directly on the orchestrator
        orchestrator.matrix_observer = mock_matrix_observer
        channel_id = "!test:example.com"
        test_content = "This is a test reply for context"
        
        # Create action
        action = ActionPlan(
            action_type="send_matrix_reply",
            parameters={
                "channel_id": channel_id,  # Updated parameter name
                "content": test_content,
                "reply_to_id": "original_event_456"  # Updated parameter name
            },
            reasoning="Test action for context",
            priority=5
        )
        
        # Execute action
        await orchestrator._execute_action(action)
        
        # Get context and verify the assistant message was added
        context = await orchestrator.context_manager.get_context(channel_id)
        
        # Check that assistant messages include our sent message
        assistant_messages = context.assistant_messages
        assert len(assistant_messages) > 0
        
        # Find our message in assistant messages
        our_messages = [msg for msg in assistant_messages if msg.get("content") == test_content]
        assert len(our_messages) == 1
        
        our_message = our_messages[0]
        assert our_message["event_id"] == "test_event_123"
        assert our_message["sender"] == settings.MATRIX_USER_ID
        assert our_message["type"] == "assistant"
    
    @pytest.mark.asyncio
    async def test_matrix_message_recorded_in_both_stores(self, orchestrator, mock_matrix_observer):
        """Test that bot's matrix message is recorded in both WorldState and Context."""
        # Setup - set the matrix observer directly on the orchestrator
        orchestrator.matrix_observer = mock_matrix_observer
        channel_id = "!test:example.com"
        test_content = "This is a test message"
        
        # Create action
        action = ActionPlan(
            action_type="send_matrix_message",
            parameters={
                "channel_id": channel_id,  # Updated parameter name for new tool interface
                "content": test_content
            },
            reasoning="Test message action",
            priority=5
        )
        
        # Execute action
        await orchestrator._execute_action(action)
        
        # Verify WorldState
        world_state_data = orchestrator.world_state.to_dict()
        channel_data = world_state_data["channels"][channel_id]
        messages = channel_data.get("recent_messages", [])
        bot_messages = [msg for msg in messages if msg.get("sender") == settings.MATRIX_USER_ID]
        
        assert len(bot_messages) == 1
        assert bot_messages[0]["content"] == test_content
        assert bot_messages[0]["reply_to"] is None  # Not a reply
        
        # Verify ContextManager
        context = await orchestrator.context_manager.get_context(channel_id)
        assistant_messages = context.assistant_messages
        our_messages = [msg for msg in assistant_messages if msg.get("content") == test_content]
        
        assert len(our_messages) == 1
        assert our_messages[0]["sender"] == settings.MATRIX_USER_ID
    
    @pytest.mark.asyncio
    async def test_failed_action_not_recorded_as_bot_message(self, orchestrator, mock_matrix_observer):
        """Test that failed actions don't create phantom bot messages."""
        # Setup failed observer
        mock_matrix_observer.send_reply = AsyncMock(return_value={
            "success": False,
            "error": "Test failure"
        })
        mock_matrix_observer.send_formatted_reply = AsyncMock(return_value={
            "success": False,
            "error": "Test failure"
        })
        orchestrator.matrix_observer = mock_matrix_observer  # Updated for new architecture
        
        channel_id = "!test:example.com"
        test_content = "This message will fail"
        
        # Create action
        action = ActionPlan(
            action_type="send_matrix_reply",
            parameters={
                "channel_id": channel_id,  # Updated parameter name
                "content": test_content,
                "reply_to_id": "original_event_789"  # Updated parameter name
            },
            reasoning="Test failed action",
            priority=5
        )
        
        # Execute action
        await orchestrator._execute_action(action)
        
        # Verify no bot message was created in WorldState
        world_state_data = orchestrator.world_state.to_dict()
        
        # Should either have no channels or no messages for this channel
        if "channels" in world_state_data and channel_id in world_state_data["channels"]:
            channel_data = world_state_data["channels"][channel_id]
            messages = channel_data.get("recent_messages", [])
            bot_messages = [msg for msg in messages if msg.get("sender") == settings.MATRIX_USER_ID]
            assert len(bot_messages) == 0
        
        # Verify no assistant message was created in ContextManager for the failed send
        context = await orchestrator.context_manager.get_context(channel_id)
        assistant_messages = context.assistant_messages
        our_messages = [msg for msg in assistant_messages if msg.get("content") == test_content]
        assert len(our_messages) == 0


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v"])
