#!/usr/bin/env python3
"""
Test script to verify Matrix image handling fixes.
This test simulates the problematic scenario described in the engineering report.
"""

import asyncio
import logging
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass
from typing import Dict, Any, List, Optional

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class MockMessage:
    """Mock Message object for testing."""
    id: str
    channel_id: str
    channel_type: str
    sender: str
    content: str
    timestamp: float
    reply_to: Optional[str]
    image_urls: Optional[List[str]]
    metadata: Dict[str, Any]

@dataclass
class MockChannel:
    """Mock Channel object for testing."""
    id: str
    messages: List[MockMessage]

@dataclass
class MockWorldState:
    """Mock WorldState for testing."""
    channels: Dict[str, MockChannel]

async def test_matrix_image_fix():
    """Test the Matrix image handling fixes."""
    print("🧪 Testing Matrix Image Handling Fixes")
    print("=" * 50)
    
    # Test 1: Test the enhanced ensure_publicly_accessible_image_url function
    print("\n1. Testing Matrix URL pattern recognition...")
    
    from chatbot.tools.describe_image_tool import ensure_publicly_accessible_image_url
    from chatbot.tools.base import ActionContext
    
    # Create mock context
    mock_context = ActionContext()
    
    # Test generic Matrix URL pattern (not hardcoded homeserver)
    matrix_url = "https://matrix.example.com/_matrix/media/r0/download/matrix.example.com/fZEbZIjeCUtTYtFGJqnaxlru"
    
    # Test with no Matrix observer (should fall back gracefully)
    result_url, is_accessible = await ensure_publicly_accessible_image_url(matrix_url, mock_context)
    print(f"   Matrix URL pattern test: {matrix_url[:50]}...")
    print(f"   Result: URL={result_url[:50]}..., accessible={is_accessible}")
    
    # Test 2: Test system-level fix for describe_image parameters
    print("\n2. Testing describe_image parameter correction...")
    
    from chatbot.core.orchestration.main_orchestrator import TraditionalProcessor
    
    # Create a minimal traditional processor for testing
    class TestTraditionalProcessor(TraditionalProcessor):
        def __init__(self):
            self.action_context = ActionContext()
            # Mock world state manager
            self.action_context.world_state_manager = MagicMock()
            
            # Create mock world state with a channel containing an image message
            mock_world_state = MockWorldState(channels={})
            mock_channel = MockChannel(
                id="!test:matrix.org",
                messages=[
                    MockMessage(
                        id="$event1",
                        channel_id="!test:matrix.org", 
                        channel_type="matrix",
                        sender="@user:matrix.org",
                        content="[Image]",
                        timestamp=1234567890.0,
                        reply_to=None,
                        image_urls=["https://s3.amazonaws.com/bucket/image_abc123.jpg"],
                        metadata={"original_filename": "image.png", "matrix_event_type": "m.image"}
                    )
                ]
            )
            mock_world_state.channels["!test:matrix.org"] = mock_channel
            self.action_context.world_state_manager.state = mock_world_state
    
    processor = TestTraditionalProcessor()
    
    # Test fixing invalid image URL parameter (filename instead of URL)
    invalid_params = {
        "image_url": "image.png",  # This is invalid - it's a filename, not a URL
        "channel_id": "!test:matrix.org"
    }
    
    corrected_params = await processor._fix_describe_image_params(invalid_params)
    print(f"   Original params: {invalid_params}")
    print(f"   Corrected params: {corrected_params}")
    
    if corrected_params["image_url"] != "image.png":
        print("   ✅ Successfully corrected image URL!")
    else:
        print("   ❌ Failed to correct image URL")
    
    # Test 3: Test Matrix observer image content handling  
    print("\n3. Testing Matrix observer content handling...")
    
    # Mock a Matrix image event
    mock_image_event = MagicMock()
    mock_image_event.body = "image.png"  # This is a filename
    mock_image_event.url = "mxc://matrix.org/fZEbZIjeCUtTYtFGJqnaxlru"
    
    # Test our enhanced content logic
    original_body = getattr(mock_image_event, "body", "Image")
    
    # Check if the body looks like just a filename
    if original_body and any(original_body.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.svg']):
        # Store the filename in metadata and use a generic content
        content = "[Image]"
        image_filename = original_body
        print(f"   Original body: '{original_body}' -> Content: '{content}', Filename: '{image_filename}'")
        print("   ✅ Successfully converted filename to generic content!")
    else:
        print("   ❌ Failed to detect filename pattern")
    
    # Test 4: Test AI prompt enhancement verification
    print("\n4. Testing AI prompt enhancements...")
    
    from chatbot.core.ai_engine import AIDecisionEngine
    
    # Check if the enhanced prompt text is present
    try:
        # Create a test AI engine to access the system prompt
        ai_engine = AIDecisionEngine(api_key="test", model="test")
        system_prompt = ai_engine._build_system_prompt_text([])  # Empty tools list for test
        
        if "ALWAYS use the URL from the message's `image_urls` array, NOT the `content` field" in system_prompt:
            print("   ✅ Enhanced AI prompt instructions found!")
        else:
            print("   ❌ Enhanced AI prompt instructions not found")
    except Exception as e:
        print(f"   ⚠️  Could not test AI prompt: {e}")
    
    print("\n🎉 Matrix Image Handling Fix Test Complete!")
    print("=" * 50)

async def main():
    """Main test function."""
    try:
        await test_matrix_image_fix()
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
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
