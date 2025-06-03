#!/usr/bin/env python3
"""
Test the Matrix image URL handling fix
"""
import asyncio
import logging
from unittest.mock import AsyncMock, Mock

from chatbot.tools.describe_image_tool import ensure_publicly_accessible_image_url
from chatbot.tools.base import ActionContext

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_matrix_image_url_conversion():
    """Test that Matrix URLs are properly converted to S3 URLs"""
    
    # Mock the Matrix client response
    mock_download_response = Mock()
    mock_download_response.body = b"fake_image_data"
    
    # Mock the Matrix client
    mock_matrix_client = AsyncMock()
    mock_matrix_client.download.return_value = mock_download_response
    
    # Mock the Matrix observer
    mock_matrix_observer = Mock()
    mock_matrix_observer.client = mock_matrix_client
    
    # Mock the S3 service
    mock_s3_service = AsyncMock()
    mock_s3_service.upload_image_data.return_value = "https://cdn.example.com/matrix_media_test123.jpg"
    
    # Create ActionContext
    context = ActionContext(
        matrix_observer=mock_matrix_observer,
        s3_service=mock_s3_service
    )
    
    # Test Matrix URL
    matrix_url = "https://chat.ratimics.com/_matrix/media/r0/download/chat.ratimics.com/test123"
    
    result = await ensure_publicly_accessible_image_url(matrix_url, context)
    
    print(f"Input URL: {matrix_url}")
    print(f"Output URL: {result}")
    
    # Verify the client was called with correct parameters
    mock_matrix_client.download.assert_called_once_with("mxc://chat.ratimics.com/test123")
    
    # Verify S3 upload was called
    mock_s3_service.upload_image_data.assert_called_once_with(
        b"fake_image_data",
        "matrix_media_test123.jpg"
    )
    
    # Verify we got the S3 URL back
    assert result == "https://cdn.example.com/matrix_media_test123.jpg"
    
    print("✅ Matrix URL conversion test passed!")


async def test_non_matrix_url_passthrough():
    """Test that non-Matrix URLs are passed through unchanged"""
    
    context = ActionContext()
    
    regular_url = "https://example.com/image.jpg"
    result = await ensure_publicly_accessible_image_url(regular_url, context)
    
    assert result == regular_url
    print("✅ Non-Matrix URL passthrough test passed!")


async def test_matrix_url_with_missing_context():
    """Test graceful fallback when Matrix client is not available"""
    
    context = ActionContext()  # No matrix_observer
    
    matrix_url = "https://chat.ratimics.com/_matrix/media/r0/download/chat.ratimics.com/test123"
    result = await ensure_publicly_accessible_image_url(matrix_url, context)
    
    # Should return original URL as fallback
    assert result == matrix_url
    print("✅ Missing context fallback test passed!")


async def main():
    """Run all tests"""
    print("Testing Matrix image URL handling fix...")
    
    await test_matrix_image_url_conversion()
    await test_non_matrix_url_passthrough()
    await test_matrix_url_with_missing_context()
    
    print("\n🎉 All tests passed! The Matrix image URL fix is working correctly.")


if __name__ == "__main__":
    asyncio.run(main())
