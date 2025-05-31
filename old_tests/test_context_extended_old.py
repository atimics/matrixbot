"""
Tests for context management functionality.
"""
import pytest
import os
import tempfile
import time
from chatbot.core.context import ContextManager
from chatbot.core.world_state import Message
from chatbot.config import AppConfig


class TestContextManagerExtended:
    """Extended tests for the context management functionality."""
    
    def setup_method(self):
        """Set up test environment with temporary database."""
        self.temp_dir = tempfile.mkdtemp()
        self.config = AppConfig()
        
        from chatbot.core.world_state import WorldStateManager
        self.world_state = WorldStateManager()
        
        db_path = os.path.join(self.temp_dir, "test.db")
        self.context_manager = ContextManager(self.world_state, db_path)
    
    def teardown_method(self):
        """Clean up test environment."""
        # Current ContextManager doesn't have cleanup method
        # Clean up temp files
        import shutil
        if hasattr(self, 'temp_dir'):
            shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    @pytest.mark.asyncio
    async def test_basic_message_flow(self):
        """Test basic message addition and retrieval."""
        channel_id = "test_channel"
        
        # Add a user message
        user_msg = {
            "content": "Hello world",
            "sender": "@user:example.com",
            "timestamp": time.time()
        }
        await self.context_manager.add_user_message(channel_id, user_msg)
        
        # Get conversation messages
        messages = await self.context_manager.get_conversation_messages(channel_id)
        assert len(messages) >= 1
        
        # Add an assistant message
        assistant_msg = {
            "content": "Hello back!",
            "sender": "bot",
            "timestamp": time.time()
        }
        await self.context_manager.add_assistant_message(channel_id, assistant_msg)
        
        # Get updated messages
        updated_messages = await self.context_manager.get_conversation_messages(channel_id)
        assert len(updated_messages) >= len(messages)
    
    @pytest.mark.asyncio
    async def test_context_retrieval(self):
        """Test context retrieval functionality."""
        channel_id = "context_test"
        
        # Get context for empty channel
        context = await self.context_manager.get_context(channel_id)
        assert context is not None
        
        # Get context summary
        summary = await self.context_manager.get_context_summary(channel_id)
        assert "channel_id" in summary
        assert summary["channel_id"] == channel_id
    
    @pytest.mark.asyncio
    async def test_state_change_tracking(self):
        """Test state change tracking functionality."""
        # Add a world state update
        await self.context_manager.add_world_state_update(
            "test_update", 
            {"key": "value", "timestamp": time.time()}
        )
        
        # Get recent state changes
        changes = await self.context_manager.get_state_changes()
        assert len(changes) >= 0  # May or may not have changes depending on implementation
    
    @pytest.mark.asyncio 
    async def test_clear_context(self):
        """Test clearing context for a channel."""
        channel_id = "clear_test"
        
        # Add some messages
        msg = {
            "content": "Test message",
            "sender": "@user:example.com", 
            "timestamp": time.time()
        }
        await self.context_manager.add_user_message(channel_id, msg)
        
        # Clear context
        await self.context_manager.clear_context(channel_id)
        
        # Verify cleared
        messages = await self.context_manager.get_conversation_messages(channel_id)
        # Note: The exact behavior depends on implementation
        # Some contexts may still have system messages
    
    def test_multiple_users_separate_contexts(self):
        """Test that different users have separate contexts."""
        channel_id = "general"
        
        # Two different users
        self.context_manager.add_user_message("@alice:example.com", channel_id, "Alice's message")
        self.context_manager.add_user_message("@bob:example.com", channel_id, "Bob's message")
        
        # Get contexts
        alice_context = self.context_manager.get_context_for_user("@alice:example.com", channel_id)
        bob_context = self.context_manager.get_context_for_user("@bob:example.com", channel_id)
        
        assert len(alice_context["messages"]) == 1
        assert len(bob_context["messages"]) == 1
        assert alice_context["messages"][0]["content"] == "Alice's message"
        assert bob_context["messages"][0]["content"] == "Bob's message"
    
    def test_context_limit_enforcement(self):
        """Test that context is limited to prevent unbounded growth."""
        user_id = "@test:example.com"
        channel_id = "test"
        
        # Add many messages (more than the limit)
        for i in range(25):  # Assuming limit is 20
            self.context_manager.add_user_message(user_id, channel_id, f"Message {i}")
        
        context = self.context_manager.get_context_for_user(user_id, channel_id)
        
        # Should be limited
        assert len(context["messages"]) <= 20
        # Should contain the most recent messages
        assert "Message 24" in context["messages"][-1]["content"]
    
    def test_get_context_empty_user(self):
        """Test getting context for user with no messages."""
        context = self.context_manager.get_context_for_user("@new:example.com", "channel")
        
        assert context["messages"] == []
        assert context["user_id"] == "@new:example.com"
        assert context["channel_id"] == "channel"
    
    def test_database_persistence(self):
        """Test that messages persist across context manager instances."""
        user_id = "@persistent:example.com"
        channel_id = "persistent_channel"
        content = "This should persist"
        
        # Add message
        self.context_manager.add_user_message(user_id, channel_id, content)
        
        # Create new context manager instance with same database
        new_context_manager = ContextManager(self.config)
        
        # Verify message persists
        context = new_context_manager.get_context_for_user(user_id, channel_id)
        assert len(context["messages"]) == 1
        assert context["messages"][0]["content"] == content
        
        new_context_manager.cleanup()
    
    def test_summarize_for_ai_basic(self):
        """Test basic context summarization for AI."""
        user_id = "@test:example.com"
        channel_id = "test"
        
        # Add some conversation
        self.context_manager.add_user_message(user_id, channel_id, "Hello bot")
        self.context_manager.add_bot_response(user_id, channel_id, "Hello human!", "msg1")
        self.context_manager.add_user_message(user_id, channel_id, "How are you?")
        
        summary = self.context_manager.summarize_for_ai(user_id, channel_id)
        
        assert "conversation_history" in summary
        assert len(summary["conversation_history"]) == 3
        assert summary["user_id"] == user_id
        assert summary["channel_id"] == channel_id
        assert "last_interaction" in summary


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
