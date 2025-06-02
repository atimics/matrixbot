#!/usr/bin/env python3
"""
Test to verify that image generation always requires S3 and returns CloudFront URLs.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from chatbot.tools.media_generation_tools import GenerateImageTool


@pytest.mark.asyncio
async def test_generate_image_requires_s3_service():
    """Test that image generation fails when S3 service is not available."""
    print("\n=== Testing S3 Service Requirement ===")
    
    tool = GenerateImageTool()
    
    # Create context without S3 service
    context = MagicMock()
    context.world_state_manager = MagicMock()
    # No s3_service attribute
    
    # Mock Google Gemini to succeed
    with patch('chatbot.tools.media_generation_tools.settings') as mock_settings:
        mock_settings.GOOGLE_API_KEY = "test_key"
        mock_settings.REPLICATE_API_TOKEN = None  # Force Google path
        
        with patch('chatbot.tools.media_generation_tools.GoogleAIMediaClient') as mock_google_class:
            mock_google_client = AsyncMock()
            mock_google_client.generate_image_gemini = AsyncMock(return_value=b"fake_image_data")
            mock_google_class.return_value = mock_google_client
            
            result = await tool.execute({
                "prompt": "A test robot",
                "aspect_ratio": "1:1"
            }, context)
            
            print(f"Result without S3 service: {result}")
            
            # Should fail because S3 service is required
            assert result["status"] == "error"
            assert "S3 storage" in result["message"]
            assert "not available" in result["message"]


@pytest.mark.asyncio
async def test_generate_image_with_replicate_always_returns_s3_url():
    """Test that Replicate image generation always returns S3/CloudFront URL."""
    print("\n=== Testing Replicate S3 Requirement ===")
    
    tool = GenerateImageTool()
    
    # Create mock context with S3 service
    context = MagicMock()
    context.world_state_manager = MagicMock()
    context.world_state_manager.add_action_result = MagicMock()
    context.world_state_manager.record_generated_media = MagicMock()
    
    # Mock S3 service that succeeds
    mock_s3_service = MagicMock()
    mock_s3_service.ensure_s3_url = AsyncMock(return_value="https://d123example.cloudfront.net/uuid123.jpg")
    mock_s3_service.is_s3_url = MagicMock(return_value=True)
    context.s3_service = mock_s3_service
    
    # Mock Replicate to succeed
    with patch('chatbot.tools.media_generation_tools.settings') as mock_settings:
        mock_settings.GOOGLE_API_KEY = None  # Force Replicate path
        mock_settings.REPLICATE_API_TOKEN = "test_token"
        mock_settings.REPLICATE_IMAGE_MODEL = "test/model"
        mock_settings.REPLICATE_LORA_WEIGHTS_URL = None
        mock_settings.REPLICATE_LORA_SCALE = None
        
        with patch('chatbot.tools.media_generation_tools.ReplicateClient') as mock_replicate_class:
            mock_replicate_instance = MagicMock()
            mock_replicate_instance.generate_image = AsyncMock(
                return_value="https://replicate.delivery/pbxt/abc123/generated-image.jpg"
            )
            mock_replicate_class.return_value = mock_replicate_instance
            
            result = await tool.execute({
                "prompt": "A beautiful sunset over mountains",
                "aspect_ratio": "16:9"
            }, context)
            
            print(f"Result with Replicate: {result}")
            
            # Should succeed and return S3 URL
            assert result["status"] == "success"
            assert "image_url" in result
            assert result["image_url"] == "https://d123example.cloudfront.net/uuid123.jpg"
            assert "s3_image_url" in result
            assert result["s3_image_url"] == "https://d123example.cloudfront.net/uuid123.jpg"
            assert result["service_used"] == "replicate"
            
            # Verify S3 conversion was called
            mock_s3_service.ensure_s3_url.assert_called_once_with(
                "https://replicate.delivery/pbxt/abc123/generated-image.jpg"
            )


@pytest.mark.asyncio  
async def test_generate_image_replicate_s3_upload_fails():
    """Test that image generation fails when S3 upload fails."""
    print("\n=== Testing S3 Upload Failure ===")
    
    tool = GenerateImageTool()
    
    # Create mock context with S3 service that fails
    context = MagicMock()
    context.world_state_manager = MagicMock()
    
    # Mock S3 service that fails
    mock_s3_service = MagicMock()
    mock_s3_service.ensure_s3_url = AsyncMock(return_value=None)  # Upload fails
    context.s3_service = mock_s3_service
    
    # Mock Replicate to succeed
    with patch('chatbot.tools.media_generation_tools.settings') as mock_settings:
        mock_settings.GOOGLE_API_KEY = None  # Force Replicate path
        mock_settings.REPLICATE_API_TOKEN = "test_token"
        mock_settings.REPLICATE_IMAGE_MODEL = "test/model"
        mock_settings.REPLICATE_LORA_WEIGHTS_URL = None
        mock_settings.REPLICATE_LORA_SCALE = None
        
        with patch('chatbot.tools.media_generation_tools.ReplicateClient') as mock_replicate_class:
            mock_replicate_instance = MagicMock()
            mock_replicate_instance.generate_image = AsyncMock(
                return_value="https://replicate.delivery/pbxt/abc123/generated-image.jpg"
            )
            mock_replicate_class.return_value = mock_replicate_instance
            
            result = await tool.execute({
                "prompt": "A test image",
                "aspect_ratio": "1:1"
            }, context)
            
            print(f"Result with S3 failure: {result}")
            
            # Should fail because S3 upload failed
            assert result["status"] == "error"
            assert "S3" in result["message"]
            assert "failed" in result["message"].lower()


@pytest.mark.asyncio
async def test_generate_image_replicate_returns_non_s3_url():
    """Test that image generation fails when ensure_s3_url returns a non-S3 URL."""
    print("\n=== Testing Non-S3 URL Rejection ===")
    
    tool = GenerateImageTool()
    
    # Create mock context with S3 service
    context = MagicMock()
    context.world_state_manager = MagicMock()
    
    # Mock S3 service that returns the original URL (not uploaded)
    mock_s3_service = MagicMock()
    mock_s3_service.ensure_s3_url = AsyncMock(return_value="https://replicate.delivery/pbxt/abc123/generated-image.jpg")
    mock_s3_service.is_s3_url = MagicMock(return_value=False)  # Not an S3 URL
    context.s3_service = mock_s3_service
    
    # Mock Replicate to succeed
    with patch('chatbot.tools.media_generation_tools.settings') as mock_settings:
        mock_settings.GOOGLE_API_KEY = None  # Force Replicate path
        mock_settings.REPLICATE_API_TOKEN = "test_token"
        mock_settings.REPLICATE_IMAGE_MODEL = "test/model"
        mock_settings.REPLICATE_LORA_WEIGHTS_URL = None
        mock_settings.REPLICATE_LORA_SCALE = None
        
        with patch('chatbot.tools.media_generation_tools.ReplicateClient') as mock_replicate_class:
            mock_replicate_instance = MagicMock()
            mock_replicate_instance.generate_image = AsyncMock(
                return_value="https://replicate.delivery/pbxt/abc123/generated-image.jpg"
            )
            mock_replicate_class.return_value = mock_replicate_instance
            
            result = await tool.execute({
                "prompt": "A test image",
                "aspect_ratio": "1:1"
            }, context)
            
            print(f"Result with non-S3 URL: {result}")
            
            # Should fail because the returned URL is not an S3 URL
            assert result["status"] == "error"
            assert "S3" in result["message"]
            assert "failed" in result["message"].lower()


async def main():
    """Run all tests."""
    print("🧪 Testing S3 Requirement Enforcement for Image Generation")
    
    await test_generate_image_requires_s3_service()
    print("✅ S3 service requirement test passed")
    
    await test_generate_image_with_replicate_always_returns_s3_url()
    print("✅ Replicate S3 URL test passed")
    
    await test_generate_image_replicate_s3_upload_fails()
    print("✅ S3 upload failure test passed")
    
    await test_generate_image_replicate_returns_non_s3_url()
    print("✅ Non-S3 URL rejection test passed")
    
    print("\n🎉 All tests passed! Image generation now requires S3 and returns CloudFront URLs only.")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
