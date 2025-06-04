#!/usr/bin/env python3
"""
Test suite for Matrix feedback loop prevention.

This test verifies that the bot does not repeatedly reply to the same message
when its own reply triggers a new processing cycle.
"""

import asyncio
import json
import time
from unittest.mock import Mock, AsyncMock, patch

import pytest

from chatbot.core.world_state.manager import WorldStateManager
from chatbot.core.world_state.structures import Message, ActionHistory
from chatbot.tools.matrix_tools import SendMatrixReplyTool
from chatbot.tools.base import ActionContext


class TestFeedbackLoopPrevention:
    """Test suite for Matrix feedback loop prevention"""

    def setup_method(self):
        """Set up test fixtures"""
        self.world_state_manager = WorldStateManager()
        self.world_state_manager.add_channel("!test:example.com", "matrix", "Test Room")
        
        # Mock Matrix observer
        self.mock_matrix_observer = Mock()
        self.mock_matrix_observer.send_reply = AsyncMock(return_value={
            "success": True,
            "event_id": "$bot_reply_123",
        })
        
        # Create action context
        self.action_context = ActionContext(
            world_state_manager=self.world_state_manager,
            matrix_observer=self.mock_matrix_observer,
            context_manager=None,
            farcaster_observer=None,
        )
        
        # Create the tool
        self.reply_tool = SendMatrixReplyTool()

    @pytest.mark.asyncio
    async def test_first_reply_succeeds(self):
        """Test that the first reply to a message succeeds"""
        # Original user message
        user_message = Message(
            id="$user_msg_123",
            channel_id="!test:example.com",
            channel_type="matrix",
            sender="@user:example.com",
            content="Hello bot!",
            timestamp=time.time(),
        )
        self.world_state_manager.add_message("!test:example.com", user_message)
        
        # Execute reply
        with patch('chatbot.config.settings') as mock_settings:
            mock_settings.MATRIX_USER_ID = "@bot:example.com"
            
            result = await self.reply_tool.execute({
                "channel_id": "!test:example.com",
                "content": "Hello user!",
                "reply_to_id": "$user_msg_123",
            }, self.action_context)
        
        # Verify the reply succeeded
        assert result["status"] == "success"
        assert "event_id" in result
        self.mock_matrix_observer.send_reply.assert_called_once()

    @pytest.mark.asyncio
    async def test_duplicate_reply_prevented_by_action_history(self):
        """Test that duplicate replies are prevented when action history shows a reply"""
        # Add action history showing we already replied
        action_history = ActionHistory(
            action_type="send_matrix_reply",
            parameters={"reply_to_id": "$user_msg_123"},
            result="success",
            timestamp=time.time(),
        )
        self.world_state_manager.state.action_history.append(action_history)
        
        # Try to reply again
        with patch('chatbot.config.settings') as mock_settings:
            mock_settings.MATRIX_USER_ID = "@bot:example.com"
            
            result = await self.reply_tool.execute({
                "channel_id": "!test:example.com",
                "content": "Hello again!",
                "reply_to_id": "$user_msg_123",
            }, self.action_context)
        
        # Verify the reply was skipped
        assert result["status"] == "skipped"
        assert "already_replied" in result["reason"]
        self.mock_matrix_observer.send_reply.assert_not_called()

    @pytest.mark.asyncio
    async def test_duplicate_reply_prevented_by_message_history(self):
        """Test that duplicate replies are prevented when message history shows a bot reply"""
        # Original user message
        user_message = Message(
            id="$user_msg_123",
            channel_id="!test:example.com",
            channel_type="matrix",
            sender="@user:example.com",
            content="Hello bot!",
            timestamp=time.time(),
        )
        self.world_state_manager.add_message("!test:example.com", user_message)
        
        # Bot's previous reply
        with patch('chatbot.config.settings') as mock_settings:
            mock_settings.MATRIX_USER_ID = "@bot:example.com"
            
            bot_reply = Message(
                id="$bot_reply_123",
                channel_id="!test:example.com",
                channel_type="matrix",
                sender="@bot:example.com",
                content="Hello user!",
                timestamp=time.time(),
                reply_to="$user_msg_123",
            )
            self.world_state_manager.add_message("!test:example.com", bot_reply)
            
            # Try to reply again
            result = await self.reply_tool.execute({
                "channel_id": "!test:example.com",
                "content": "Hello again!",
                "reply_to_id": "$user_msg_123",
            }, self.action_context)
        
        # Verify the reply was skipped
        assert result["status"] == "skipped"
        assert "already_replied" in result["reason"]
        self.mock_matrix_observer.send_reply.assert_not_called()

    @pytest.mark.asyncio
    async def test_new_message_allows_reply(self):
        """Test that replies to different messages are allowed"""
        # Bot replied to first message
        action_history = ActionHistory(
            action_type="send_matrix_reply",
            parameters={"reply_to_id": "$user_msg_123"},
            result="success",
            timestamp=time.time(),
        )
        self.world_state_manager.state.action_history.append(action_history)
        
        # Try to reply to a different message
        with patch('chatbot.config.settings') as mock_settings:
            mock_settings.MATRIX_USER_ID = "@bot:example.com"
            
            result = await self.reply_tool.execute({
                "channel_id": "!test:example.com",
                "content": "Reply to new message",
                "reply_to_id": "$user_msg_456",  # Different message ID
            }, self.action_context)
        
        # Verify the reply succeeded
        assert result["status"] == "success"
        self.mock_matrix_observer.send_reply.assert_called_once()

    @pytest.mark.asyncio
    async def test_failed_reply_allows_retry(self):
        """Test that failed replies allow retries"""
        # Add action history showing a failed reply
        action_history = ActionHistory(
            action_type="send_matrix_reply",
            parameters={"reply_to_id": "$user_msg_123"},
            result="failure",
            timestamp=time.time(),
        )
        self.world_state_manager.state.action_history.append(action_history)
        
        # Try to reply again
        with patch('chatbot.config.settings') as mock_settings:
            mock_settings.MATRIX_USER_ID = "@bot:example.com"
            
            result = await self.reply_tool.execute({
                "channel_id": "!test:example.com",
                "content": "Retry reply",
                "reply_to_id": "$user_msg_123",
            }, self.action_context)
        
        # Verify the reply succeeded (retry allowed for failed attempts)
        assert result["status"] == "success"
        self.mock_matrix_observer.send_reply.assert_called_once()

    def test_has_bot_replied_to_matrix_event_method(self):
        """Test the has_bot_replied_to_matrix_event method directly"""
        with patch('chatbot.config.settings') as mock_settings:
            mock_settings.MATRIX_USER_ID = "@bot:example.com"
            
            # Initially no reply exists
            assert not self.world_state_manager.has_bot_replied_to_matrix_event("$user_msg_123")
            
            # Add action history
            action_history = ActionHistory(
                action_type="send_matrix_reply",
                parameters={"reply_to_id": "$user_msg_123"},
                result="success",
                timestamp=time.time(),
            )
            self.world_state_manager.state.action_history.append(action_history)
            
            # Now should return True
            assert self.world_state_manager.has_bot_replied_to_matrix_event("$user_msg_123")
            
            # Different message should still return False
            assert not self.world_state_manager.has_bot_replied_to_matrix_event("$user_msg_456")

    def test_has_bot_replied_checks_message_history(self):
        """Test that has_bot_replied_to_matrix_event checks message history"""
        with patch('chatbot.config.settings') as mock_settings:
            mock_settings.MATRIX_USER_ID = "@bot:example.com"
            
            # Add bot reply message
            bot_reply = Message(
                id="$bot_reply_123",
                channel_id="!test:example.com",
                channel_type="matrix",
                sender="@bot:example.com",
                content="Bot reply",
                timestamp=time.time(),
                reply_to="$user_msg_123",
            )
            self.world_state_manager.add_message("!test:example.com", bot_reply)
            
            # Should detect the reply
            assert self.world_state_manager.has_bot_replied_to_matrix_event("$user_msg_123")
            
            # Different message should return False
            assert not self.world_state_manager.has_bot_replied_to_matrix_event("$user_msg_456")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
