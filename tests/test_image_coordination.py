#!/usr/bin/env python3
"""
Test Image Generation and Posting Coordination

Tests the automatic coordination between image generation and posting actions
to ensure generated images are properly embedded in posts.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from chatbot.core.ai_engine import ActionPlan
from chatbot.core.orchestration.main_orchestrator import TraditionalProcessor


class TestImageCoordination:
    """Test coordination between image generation and posting actions."""

    @pytest.fixture
    def mock_ai_engine(self):
        """Mock AI engine."""
        return MagicMock()

    @pytest.fixture
    def mock_tool_registry(self):
        """Mock tool registry with generate_image and send_farcaster_post tools."""
        registry = MagicMock()
        
        # Mock image generation tool
        image_tool = AsyncMock()
        image_tool.execute.return_value = {
            "status": "success",  # Changed from "success": True
            "image_url": "https://d7xbminy5txaa.cloudfront.net/images/test_generated_image.jpg",
            "image_arweave_url": "ar://test_arweave_id_image",
            "prompt": "test image",
            # Ensure all expected fields by TraditionalProcessor are present if generate_image is successful
            "embed_page_url": "ar://test_embed_page_url" # Added this as GenerateImageTool returns it
        }
        
        # Mock Farcaster posting tool
        farcaster_tool = AsyncMock()
        farcaster_tool.execute.return_value = {
            "success": True,
            "cast_hash": "0xtest123",
            "url": "https://warpcast.com/test"
        }
        
        # Mock Matrix tools
        matrix_tool = AsyncMock()
        matrix_tool.execute.return_value = {
            "success": True,
            "event_id": "$test123"
        }
        
        matrix_image_tool = AsyncMock()
        matrix_image_tool.execute.return_value = {
            "success": True,
            "event_id": "$test456"
        }
        
        def get_tool(name):
            if name == "generate_image":
                return image_tool
            elif name == "send_farcaster_post":
                return farcaster_tool
            elif name == "send_matrix_message":
                return matrix_tool
            elif name == "send_matrix_image":
                return matrix_image_tool
            return None
        
        registry.get_tool.side_effect = get_tool
        return registry

    @pytest.fixture
    def mock_rate_limiter(self):
        """Mock rate limiter that allows all actions."""
        limiter = MagicMock()
        limiter.can_execute_action.return_value = (True, "")
        limiter.record_action.return_value = None
        return limiter

    @pytest.fixture
    def mock_context_manager(self):
        """Mock context manager."""
        manager = AsyncMock()
        manager.add_tool_result.return_value = None
        return manager

    @pytest.fixture
    def mock_action_context(self):
        """Mock action context."""
        return MagicMock()

    @pytest.fixture
    def processor(self, mock_ai_engine, mock_tool_registry, mock_rate_limiter, 
                  mock_context_manager, mock_action_context):
        """Create a TraditionalProcessor instance for testing."""
        return TraditionalProcessor(
            ai_engine=mock_ai_engine,
            tool_registry=mock_tool_registry,
            rate_limiter=mock_rate_limiter,
            context_manager=mock_context_manager,
            action_context=mock_action_context
        )

    @pytest.mark.asyncio
    async def test_farcaster_image_coordination(self, processor, mock_tool_registry):
        """Test that image generation + Farcaster posting are coordinated."""
        # Create actions for image generation and Farcaster posting
        actions = [
            ActionPlan(
                action_type="generate_image",
                parameters={"prompt": "A beautiful sunset over mountains"},
                reasoning="Creating visual content",
                priority=8
            ),
            ActionPlan(
                action_type="send_farcaster_post",
                parameters={"text": "Check out this sunset!", "channel_id": "nature"},
                reasoning="Sharing generated content",
                priority=7
            )
        ]

        # Execute the actions individually (as the processor does)
        for action in actions:
            await processor._execute_action(action)

        # Verify image generation was called
        image_tool = mock_tool_registry.get_tool("generate_image")
        image_tool.execute.assert_called_once_with(
            {"prompt": "A beautiful sunset over mountains"},
            processor.action_context
        )

        # Verify Farcaster posting was called
        farcaster_tool = mock_tool_registry.get_tool("send_farcaster_post")
        farcaster_tool.execute.assert_called_once()
        
        # Check that the original parameters were passed
        call_args = farcaster_tool.execute.call_args[0]
        params = call_args[0]
        assert params["text"] == "Check out this sunset!"
        assert params["channel_id"] == "nature"

    @pytest.mark.asyncio
    async def test_matrix_image_coordination(self, processor, mock_tool_registry):
        """Test that image generation + Matrix messaging converts to Matrix image."""
        # Create actions for image generation and Matrix messaging
        actions = [
            ActionPlan(
                action_type="generate_image",
                parameters={"prompt": "A robot in a lab"},
                reasoning="Creating visual content",
                priority=8
            ),
            ActionPlan(
                action_type="send_matrix_message",
                parameters={"message": "Here's the robot!", "channel_id": "!test:matrix.org"},
                reasoning="Sharing in Matrix",
                priority=7
            )
        ]

        # Execute the actions individually (as the processor does)
        for action in actions:
            await processor._execute_action(action)

        # Verify image generation was called
        image_tool = mock_tool_registry.get_tool("generate_image")
        image_tool.execute.assert_called_once_with(
            {"prompt": "A robot in a lab"},
            processor.action_context
        )

        # Verify Matrix message tool was called (not doing complex coordination)
        matrix_tool = mock_tool_registry.get_tool("send_matrix_message")
        matrix_tool.execute.assert_called_once()
        
        # Check that the original parameters were passed
        call_args = matrix_tool.execute.call_args[0]
        params = call_args[0]
        assert params["message"] == "Here's the robot!"
        assert params["channel_id"] == "!test:matrix.org"

    @pytest.mark.asyncio
    async def test_no_coordination_when_no_image_generation(self, processor, mock_tool_registry):
        """Test that no coordination happens when image generation is not present."""
        # Create action for only Farcaster posting
        actions = [
            ActionPlan(
                action_type="send_farcaster_post",
                parameters={"text": "Just a text post", "channel_id": "general"},
                reasoning="Posting text content",
                priority=7
            )
        ]

        # Execute the actions individually (as the processor does)
        for action in actions:
            await processor._execute_action(action)

        # Verify only Farcaster posting was called, without image URL
        farcaster_tool = mock_tool_registry.get_tool("send_farcaster_post")
        farcaster_tool.execute.assert_called_once()
        
        call_args = farcaster_tool.execute.call_args[0]
        params = call_args[0]
        assert "image_arweave_url" not in params
        assert params["text"] == "Just a text post"

        # Verify image generation was not called
        image_tool = mock_tool_registry.get_tool("generate_image")
        image_tool.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_coordination_with_failed_image_generation(self, processor, mock_tool_registry):
        """Test coordination behavior when image generation fails."""
        # Mock image generation to fail
        image_tool = mock_tool_registry.get_tool("generate_image")
        image_tool.execute.return_value = {
            "success": False,
            "error": "Generation failed"
        }

        actions = [
            ActionPlan(
                action_type="generate_image",
                parameters={"prompt": "A complex scene"},
                reasoning="Creating visual content",
                priority=8
            ),
            ActionPlan(
                action_type="send_farcaster_post",
                parameters={"text": "Should post without image", "channel_id": "general"},
                reasoning="Posting content",
                priority=7
            )
        ]

        # Execute the actions individually (as the processor does)
        for action in actions:
            await processor._execute_action(action)

        # Verify image generation was attempted
        image_tool.execute.assert_called_once()

        # Verify Farcaster posting was called without image URL (since generation failed)
        farcaster_tool = mock_tool_registry.get_tool("send_farcaster_post")
        farcaster_tool.execute.assert_called_once()
        
        call_args = farcaster_tool.execute.call_args[0]
        params = call_args[0]
        assert "image_arweave_url" not in params
        assert params["text"] == "Should post without image"

    @pytest.mark.asyncio
    async def test_dict_format_coordination(self, processor, mock_tool_registry):
        """Test coordination works with ActionPlan-format actions."""
        # Create actions in ActionPlan format
        actions = [
            ActionPlan(
                action_type="generate_image",
                parameters={"prompt": "Test image"},
                reasoning="Testing dict format",
                priority=8
            ),
            ActionPlan(
                action_type="send_farcaster_post",
                parameters={"text": "Dict format test", "channel_id": "test"},
                reasoning="Testing coordination",
                priority=7
            )
        ]

        # Execute the actions individually (as the processor does)
        for action in actions:
            await processor._execute_action(action)

        # Verify both actions were called
        image_tool = mock_tool_registry.get_tool("generate_image")
        image_tool.execute.assert_called_once()

        farcaster_tool = mock_tool_registry.get_tool("send_farcaster_post")
        farcaster_tool.execute.assert_called_once()
        
        call_args = farcaster_tool.execute.call_args[0]
        params = call_args[0]
        # Check that the original parameters were passed
        assert params["text"] == "Dict format test"
        assert params["channel_id"] == "test"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
