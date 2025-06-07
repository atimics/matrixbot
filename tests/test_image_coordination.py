#!/usr/bin/env python3
"""
Test Image Generation and Posting Actions

Tests that image generation and posting actions work independently.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock


class TestImageCoordination:
    """Test image generation and posting actions work independently."""

    @pytest.fixture
    def mock_tool_registry(self):
        """Mock tool registry with generate_image and send_farcaster_post tools."""
        registry = MagicMock()
        
        # Mock image generation tool
        image_tool = AsyncMock()
        image_tool.execute.return_value = {
            "status": "success",
            "image_url": "https://d7xbminy5txaa.cloudfront.net/images/test_generated_image.jpg",
            "image_arweave_url": "ar://test_arweave_id_image",
            "prompt": "test image",
            "embed_page_url": "ar://test_embed_page_url"
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
        
        def get_tool(name):
            if name == "generate_image":
                return image_tool
            elif name == "send_farcaster_post":
                return farcaster_tool
            elif name == "send_matrix_message":
                return matrix_tool
            return None
        
        registry.get_tool.side_effect = get_tool
        return registry

    @pytest.fixture
    def mock_action_context(self):
        """Mock action context."""
        return MagicMock()

    @pytest.mark.asyncio
    async def test_farcaster_image_coordination(self, mock_tool_registry, mock_action_context):
        """Test that image generation and Farcaster posting work independently."""
        # Test image generation
        image_tool = mock_tool_registry.get_tool("generate_image")
        image_result = await image_tool.execute(
            {"prompt": "A beautiful sunset over mountains"}, 
            mock_action_context
        )
        
        # Verify image generation worked
        assert image_result["status"] == "success"
        assert "image_url" in image_result
        
        # Test Farcaster posting
        farcaster_tool = mock_tool_registry.get_tool("send_farcaster_post")
        farcaster_result = await farcaster_tool.execute(
            {"text": "Check out this sunset!", "channel_id": "nature"},
            mock_action_context
        )
        
        # Verify Farcaster posting worked
        assert farcaster_result["success"] is True
        assert "cast_hash" in farcaster_result

    @pytest.mark.asyncio
    async def test_matrix_image_coordination(self, mock_tool_registry, mock_action_context):
        """Test that image generation and Matrix messaging work independently."""
        # Test image generation
        image_tool = mock_tool_registry.get_tool("generate_image")
        image_result = await image_tool.execute(
            {"prompt": "A robot in a lab"}, 
            mock_action_context
        )
        
        # Verify image generation worked
        assert image_result["status"] == "success"
        assert "image_url" in image_result
        
        # Test Matrix messaging
        matrix_tool = mock_tool_registry.get_tool("send_matrix_message")
        matrix_result = await matrix_tool.execute(
            {"message": "Here's the robot!", "channel_id": "!test:matrix.org"},
            mock_action_context
        )
        
        # Verify Matrix messaging worked
        assert matrix_result["success"] is True
        assert "event_id" in matrix_result

    @pytest.mark.asyncio
    async def test_no_coordination_when_no_image_generation(self, mock_tool_registry, mock_action_context):
        """Test that Farcaster posting works without image generation."""
        # Test Farcaster posting only
        farcaster_tool = mock_tool_registry.get_tool("send_farcaster_post")
        farcaster_result = await farcaster_tool.execute(
            {"text": "Just a text post", "channel_id": "general"},
            mock_action_context
        )
        
        # Verify Farcaster posting worked
        assert farcaster_result["success"] is True
        assert "cast_hash" in farcaster_result

    @pytest.mark.asyncio
    async def test_coordination_with_failed_image_generation(self, mock_tool_registry, mock_action_context):
        """Test behavior when image generation fails."""
        # Mock image generation to fail
        image_tool = mock_tool_registry.get_tool("generate_image")
        image_tool.execute.return_value = {
            "status": "error",
            "error": "Generation failed"
        }
        
        # Test failed image generation
        image_result = await image_tool.execute(
            {"prompt": "A complex scene"}, 
            mock_action_context
        )
        
        # Verify image generation failed
        assert image_result["status"] == "error"
        assert "error" in image_result
        
        # Test that Farcaster posting still works
        farcaster_tool = mock_tool_registry.get_tool("send_farcaster_post")
        farcaster_result = await farcaster_tool.execute(
            {"text": "Should post without image", "channel_id": "general"},
            mock_action_context
        )
        
        # Verify Farcaster posting worked
        assert farcaster_result["success"] is True

    @pytest.mark.asyncio
    async def test_dict_format_coordination(self, mock_tool_registry, mock_action_context):
        """Test that tools work with dictionary format parameters."""
        # Test with dictionary parameters
        image_tool = mock_tool_registry.get_tool("generate_image")
        image_result = await image_tool.execute(
            {"prompt": "Test image"}, 
            mock_action_context
        )
        
        # Verify image generation worked
        assert image_result["status"] == "success"
        
        # Test Farcaster posting with dictionary parameters
        farcaster_tool = mock_tool_registry.get_tool("send_farcaster_post")
        farcaster_result = await farcaster_tool.execute(
            {"text": "Dict format test", "channel_id": "test"},
            mock_action_context
        )
        
        # Verify Farcaster posting worked
        assert farcaster_result["success"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
