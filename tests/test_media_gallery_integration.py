#!/usr/bin/env python3
"""
Test script for the Centralized Media Gallery functionality

This script tests the new media gallery integration to ensure
generated media is automatically posted to the dedicated gallery channel.
"""

import asyncio
import json
import logging
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from chatbot.config import settings
from chatbot.core.orchestration.main_orchestrator import MainOrchestrator
from chatbot.tools.media_generation_tools import GenerateImageTool, GenerateVideoTool, _auto_post_to_gallery
from chatbot.tools.base import ActionContext

logger = logging.getLogger(__name__)


class TestMediaGalleryIntegration:
    """Test cases for the centralized media gallery system."""

    @pytest.fixture
    def mock_action_context(self):
        """Create a mock ActionContext for testing."""
        context = MagicMock(spec=ActionContext)
        
        # Mock arweave service
        context.arweave_service = MagicMock()  # Use MagicMock for the service itself
        context.arweave_service.is_configured = MagicMock(return_value=True)  # Sync method
        context.arweave_service.upload_image_data = AsyncMock(return_value="https://arweave.net/test-media-id")  # Async method
        
        # Mock world state manager
        context.world_state_manager = MagicMock()
        context.world_state_manager.record_generated_media = MagicMock()
        
        # Mock matrix observer
        context.matrix_observer = AsyncMock()
        context.matrix_observer.client = AsyncMock()
        
        return context

    @pytest.mark.asyncio
    async def test_gallery_auto_post_success(self, mock_action_context):
        """Test successful auto-posting to media gallery."""
        # Setup
        original_gallery_id = settings.matrix_media_gallery_room_id
        settings.matrix_media_gallery_room_id = "!test-gallery:example.com"
        
        try:
            with patch('chatbot.tools.media_generation_tools.SendMatrixImageTool') as mock_tool_class:
                mock_tool_instance = AsyncMock()
                mock_tool_instance.execute.return_value = {"status": "success"}
                mock_tool_class.return_value = mock_tool_instance
                
                # Execute
                await _auto_post_to_gallery(
                    mock_action_context,
                    "image",
                    "https://arweave.net/test-image",
                    "A beautiful sunset",
                    "google_gemini"
                )
                
                # Verify
                mock_tool_instance.execute.assert_called_once()
                call_args = mock_tool_instance.execute.call_args[0]
                params = call_args[0]
                
                assert params["channel_id"] == "!test-gallery:example.com"
                assert params["image_url"] == "https://arweave.net/test-image"
                assert "🎨 **New Image Generated**" in params["caption"]
                assert "A beautiful sunset" in params["caption"]
                assert "google_gemini" in params["caption"]
                
        finally:
            settings.matrix_media_gallery_room_id = original_gallery_id

    @pytest.mark.asyncio
    async def test_gallery_auto_post_no_gallery_configured(self, mock_action_context, caplog):
        """Test auto-posting when no gallery is configured."""
        # Setup
        original_gallery_id = settings.matrix_media_gallery_room_id
        settings.matrix_media_gallery_room_id = None
        
        try:
            with caplog.at_level(logging.DEBUG):
                await _auto_post_to_gallery(
                    mock_action_context,
                    "image",
                    "https://arweave.net/test-image",
                    "A beautiful sunset",
                    "google_gemini"
                )
                
                # Verify debug message was logged
                assert "MATRIX_MEDIA_GALLERY_ROOM_ID not set" in caplog.text
                
        finally:
            settings.matrix_media_gallery_room_id = original_gallery_id

    @pytest.mark.asyncio 
    async def test_gallery_auto_post_failure_non_blocking(self, mock_action_context, caplog):
        """Test that gallery auto-post failures don't block media generation."""
        # Setup
        original_gallery_id = settings.matrix_media_gallery_room_id
        settings.matrix_media_gallery_room_id = "!test-gallery:example.com"
        
        try:
            with patch('chatbot.tools.media_generation_tools.SendMatrixImageTool') as mock_tool_class:
                mock_tool_instance = AsyncMock()
                mock_tool_instance.execute.return_value = {"status": "error", "error": "Failed to send"}
                mock_tool_class.return_value = mock_tool_instance
                
                with caplog.at_level(logging.WARNING):
                    # This should not raise an exception
                    await _auto_post_to_gallery(
                        mock_action_context,
                        "image", 
                        "https://arweave.net/test-image",
                        "A beautiful sunset",
                        "google_gemini"
                    )
                    
                    # Verify warning was logged
                    assert "Failed to auto-post generated image to gallery" in caplog.text
                    
        finally:
            settings.matrix_media_gallery_room_id = original_gallery_id

    @pytest.mark.asyncio
    async def test_generate_image_tool_integration(self, mock_action_context):
        """Test that GenerateImageTool properly calls gallery auto-post."""
        # Setup
        original_gallery_id = settings.matrix_media_gallery_room_id
        settings.matrix_media_gallery_room_id = "!test-gallery:example.com"
        
        try:
            with patch('chatbot.tools.media_generation_tools._auto_post_to_gallery') as mock_auto_post:
                mock_auto_post.return_value = None
                
                with patch('chatbot.tools.media_generation_tools.GoogleAIMediaClient') as mock_client_class:
                    mock_client = AsyncMock()
                    mock_client.generate_image_gemini.return_value = b"fake_image_data"
                    mock_client_class.return_value = mock_client
                    
                    # Configure settings for Google AI
                    original_google_key = settings.GOOGLE_API_KEY
                    settings.GOOGLE_API_KEY = "test-key"
                    
                    try:
                        # Execute
                        tool = GenerateImageTool()
                        result = await tool.execute(
                            {"prompt": "A beautiful sunset", "aspect_ratio": "16:9"},
                            mock_action_context
                        )
                        
                        # Verify
                        assert result["status"] == "success"
                        assert "arweave_image_url" in result
                        
                        # Verify auto-post was called
                        mock_auto_post.assert_called_once_with(
                            mock_action_context,
                            "image",
                            "https://arweave.net/test-media-id",
                            "A beautiful sunset",
                            "google_gemini"
                        )
                        
                    finally:
                        settings.GOOGLE_API_KEY = original_google_key
                        
        finally:
            settings.matrix_media_gallery_room_id = original_gallery_id

    @pytest.mark.asyncio
    async def test_orchestrator_gallery_room_creation(self):
        """Test that the orchestrator can create a gallery room when none exists."""
        # Setup
        original_gallery_id = settings.matrix_media_gallery_room_id
        settings.matrix_media_gallery_room_id = None
        
        try:
            orchestrator = MainOrchestrator()
            
            # Mock matrix observer and client
            mock_matrix_observer = AsyncMock()
            mock_client = AsyncMock()
            mock_matrix_observer.client = mock_client
            
            # Create action context manually since orchestrator hasn't started
            from chatbot.tools.base import ActionContext
            mock_action_context = ActionContext(
                world_state_manager=MagicMock(),
                arweave_service=None,
                matrix_observer=mock_matrix_observer,
                farcaster_observer=None
            )
            orchestrator.action_context = mock_action_context
            
            # Mock room creation response
            from nio import RoomCreateResponse
            mock_response = RoomCreateResponse(room_id="!new-gallery:example.com")
            mock_client.room_create.return_value = mock_response
            
            # Mock the file operations for config persistence
            with patch('builtins.open'), patch('json.load'), patch('json.dump'):
                with patch('pathlib.Path.exists', return_value=False):
                    with patch('pathlib.Path.mkdir'):
                        await orchestrator._ensure_media_gallery_exists()
                
                # Verify room creation was attempted
                mock_client.room_create.assert_called_once()
                
                # Verify the settings were updated
                assert settings.matrix_media_gallery_room_id == "!new-gallery:example.com"
                
        finally:
            settings.matrix_media_gallery_room_id = original_gallery_id

    def test_media_gallery_room_id_configuration(self):
        """Test that the MATRIX_MEDIA_GALLERY_ROOM_ID configuration exists."""
        # Verify the configuration attribute exists
        assert hasattr(settings, 'MATRIX_MEDIA_GALLERY_ROOM_ID')
        
        # It should be Optional[str] and default to None
        assert settings.matrix_media_gallery_room_id is None or isinstance(settings.matrix_media_gallery_room_id, str)


def main():
    """Run the media gallery integration tests."""
    print("🧪 Media Gallery Integration Test Suite")
    print("Testing the centralized media gallery implementation")
    print("=" * 60)
    
    # Run the tests
    test_result = pytest.main([
        __file__, 
        "-v",
        "--tb=short"
    ])
    
    if test_result == 0:
        print("\n✅ All media gallery integration tests passed!")
        print("\n📋 Architecture Summary:")
        print("   • Media generation tools are decoupled from posting logic")
        print("   • Generated media auto-posts to dedicated gallery channel")
        print("   • Gallery channel is auto-created if not configured")
        print("   • Failed gallery posts don't block media generation")
        print("   • Agent must explicitly share media to other channels")
        return 0
    else:
        print("\n❌ Some media gallery integration tests failed")
        return 1


if __name__ == "__main__":
    exit(main())
