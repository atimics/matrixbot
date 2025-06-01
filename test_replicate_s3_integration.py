#!/usr/bin/env python3
"""
Test script to verify that Replicate service properly uploads generated images to S3.
"""

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

from chatbot.tools.media_generation_tools import GenerateImageTool

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_replicate_s3_integration():
    """Test that Replicate images are properly uploaded to S3 and return CloudFront URLs."""
    print("\n=== Testing Replicate S3 Integration ===")
    
    # Create mock context
    context = MagicMock()
    context.world_state_manager = MagicMock()
    context.world_state_manager.add_action_result = MagicMock()
    context.world_state_manager.record_generated_media = MagicMock()
    
    # Mock S3 service
    mock_s3_service = MagicMock()
    mock_s3_service.ensure_s3_url = AsyncMock(return_value="https://d123example.cloudfront.net/uuid123.jpg")
    context.s3_service = mock_s3_service
    
    tool = GenerateImageTool()
    
    # Mock Replicate client to return a non-S3 URL
    with patch('chatbot.tools.media_generation_tools.ReplicateClient') as mock_replicate_class:
        mock_replicate_instance = MagicMock()
        mock_replicate_instance.generate_image = AsyncMock(
            return_value="https://replicate.delivery/pbxt/abc123/generated-image.jpg"
        )
        mock_replicate_class.return_value = mock_replicate_instance
        
        # Mock settings to use Replicate
        with patch('chatbot.tools.media_generation_tools.settings') as mock_settings:
            mock_settings.GOOGLE_API_KEY = None  # Force use of Replicate
            mock_settings.REPLICATE_API_TOKEN = "test_token"
            mock_settings.REPLICATE_IMAGE_MODEL = "test/model"
            mock_settings.REPLICATE_LORA_WEIGHTS_URL = None
            mock_settings.REPLICATE_LORA_SCALE = None
            
            # Execute the tool
            result = await tool.execute({
                "prompt": "A beautiful sunset over mountains",
                "aspect_ratio": "16:9"
            }, context)
            
            print(f"Tool result: {result}")
            
            # Verify the result
            assert result["status"] == "success", f"Tool failed: {result}"
            assert result["s3_image_url"] == "https://d123example.cloudfront.net/uuid123.jpg", \
                f"Expected S3 URL, got: {result['s3_image_url']}"
            assert result["service_used"] == "replicate", \
                f"Expected 'replicate', got: {result['service_used']}"
            
            # Verify Replicate was called
            mock_replicate_instance.generate_image.assert_called_once_with(
                "A beautiful sunset over mountains", aspect_ratio="16:9"
            )
            
            # Verify S3 ensure_s3_url was called with the Replicate URL
            mock_s3_service.ensure_s3_url.assert_called_once_with(
                "https://replicate.delivery/pbxt/abc123/generated-image.jpg"
            )
            
            # Verify world state was updated
            context.world_state_manager.add_action_result.assert_called_once()
            context.world_state_manager.record_generated_media.assert_called_once()
            
            call_args = context.world_state_manager.record_generated_media.call_args[1]
            assert call_args["media_url"] == "https://d123example.cloudfront.net/uuid123.jpg"
            assert call_args["media_type"] == "image"
            assert call_args["service_used"] == "replicate"
            
            print("✅ Replicate image properly uploaded to S3 and returned CloudFront URL!")


async def test_google_gemini_s3_integration():
    """Test that Google Gemini images are properly uploaded to S3."""
    print("\n=== Testing Google Gemini S3 Integration ===")
    
    # Create mock context
    context = MagicMock()
    context.world_state_manager = MagicMock()
    context.world_state_manager.add_action_result = MagicMock()
    context.world_state_manager.record_generated_media = MagicMock()
    
    # Mock S3 service
    mock_s3_service = MagicMock()
    mock_s3_service.upload_image_data = AsyncMock(return_value="https://d123example.cloudfront.net/generated_image_123.png")
    context.s3_service = mock_s3_service
    
    tool = GenerateImageTool()
    
    # Mock Google client to return image data
    with patch('chatbot.tools.media_generation_tools.GoogleAIMediaClient') as mock_google_class:
        mock_google_instance = MagicMock()
        mock_google_instance.generate_image_gemini = AsyncMock(
            return_value=b"fake_png_image_data"
        )
        mock_google_class.return_value = mock_google_instance
        
        # Mock settings to use Google
        with patch('chatbot.tools.media_generation_tools.settings') as mock_settings:
            mock_settings.GOOGLE_API_KEY = "test_google_key"
            mock_settings.GOOGLE_GEMINI_IMAGE_MODEL = "gemini-2.0-flash-experimental"
            mock_settings.REPLICATE_API_TOKEN = "test_token"
            
            # Execute the tool
            result = await tool.execute({
                "prompt": "A futuristic cityscape",
                "aspect_ratio": "1:1"
            }, context)
            
            print(f"Tool result: {result}")
            
            # Verify the result
            assert result["status"] == "success", f"Tool failed: {result}"
            assert result["s3_image_url"] == "https://d123example.cloudfront.net/generated_image_123.png", \
                f"Expected S3 URL, got: {result['s3_image_url']}"
            assert result["service_used"] == "google_gemini", \
                f"Expected 'google_gemini', got: {result['service_used']}"
            
            # Verify Google was called
            mock_google_instance.generate_image_gemini.assert_called_once_with(
                "A futuristic cityscape", "1:1"
            )
            
            # Verify S3 upload_image_data was called with the image data
            mock_s3_service.upload_image_data.assert_called_once()
            call_args = mock_s3_service.upload_image_data.call_args[0]
            assert call_args[0] == b"fake_png_image_data"
            assert call_args[1].endswith('.png')
            
            # Verify world state was updated
            context.world_state_manager.add_action_result.assert_called_once()
            context.world_state_manager.record_generated_media.assert_called_once()
            
            print("✅ Google Gemini image properly uploaded to S3!")


async def main():
    """Run all tests."""
    print("Testing Media Generation Tools S3 Integration")
    print("=" * 50)
    
    await test_replicate_s3_integration()
    await test_google_gemini_s3_integration()
    
    print("\n🎉 All S3 integration tests passed!")


if __name__ == "__main__":
    asyncio.run(main())
