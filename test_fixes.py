#!/usr/bin/env python3
"""
Test script to validate the fixes for Farcaster integration issues
"""
import asyncio
import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.abspath('.'))

from chatbot.tools.farcaster_tools import SendFarcasterPostTool
from chatbot.tools.base import ActionContext
from chatbot.utils.markdown_utils import strip_markdown


class MockFarcasterObserver:
    """Mock Farcaster observer for testing"""
    
    def __init__(self):
        self.post_queue = None  # Simulate no scheduling queue for immediate execution
        
    async def post_cast(self, content, channel=None, embed_urls=None):
        """Mock post_cast method"""
        print(f"Mock post_cast called with:")
        print(f"  content: '{content}'")
        print(f"  channel: {channel}")
        print(f"  embed_urls: {embed_urls}")
        
        # Simulate success
        return {
            "success": True,
            "cast": {"hash": "0x123456"}
        }


class MockWorldStateManager:
    """Mock world state manager for testing"""
    
    def has_sent_farcaster_post(self, content):
        return False
        
    def add_action_result(self, action_type, parameters, result):
        print(f"Recording action: {action_type} -> {result}")
        return "action_123"


async def test_empty_content_validation():
    """Test that empty content is properly rejected"""
    print("=== Testing Empty Content Validation ===")
    
    tool = SendFarcasterPostTool()
    context = ActionContext()
    context.farcaster_observer = MockFarcasterObserver()
    context.world_state_manager = MockWorldStateManager()
    
    # Test with empty content
    params = {
        "content": "",
        "image_s3_url": "https://example.com/image.jpg"
    }
    
    result = await tool.execute(params, context)
    print(f"Result for empty content: {result}")
    
    assert result["status"] == "failure"
    assert "Missing required parameter 'content'" in result["error"]
    print("✓ Empty content properly rejected")


async def test_markdown_stripping():
    """Test that markdown is properly stripped"""
    print("\n=== Testing Markdown Stripping ===")
    
    markdown_text = "**Bold text** with *italic* and [link](http://example.com) and `code`"
    stripped = strip_markdown(markdown_text)
    print(f"Original: {markdown_text}")
    print(f"Stripped: {stripped}")
    
    # Should not contain markdown formatting
    assert "**" not in stripped
    assert "*" not in stripped
    assert "[" not in stripped
    assert "]" not in stripped
    assert "`" not in stripped
    print("✓ Markdown properly stripped")


async def test_content_with_image():
    """Test that content with image is properly handled"""
    print("\n=== Testing Content with Image ===")
    
    tool = SendFarcasterPostTool()
    context = ActionContext()
    context.farcaster_observer = MockFarcasterObserver()
    context.world_state_manager = MockWorldStateManager()
    
    # Test with valid content and image
    params = {
        "content": "Check out this **amazing** image!",
        "image_s3_url": "https://example.com/image.jpg"
    }
    
    result = await tool.execute(params, context)
    print(f"Result for content with image: {result}")
    
    assert result["status"] == "success"
    print("✓ Content with image properly handled")


async def test_rate_limit_info_structure():
    """Test that rate limit info has the correct structure"""
    print("\n=== Testing Rate Limit Info Structure ===")
    
    from chatbot.integrations.farcaster.neynar_api_client import NeynarAPIClient
    
    # Create client with dummy key
    client = NeynarAPIClient(api_key="test_key")
    
    # Check that rate_limit_info has the correct structure
    print(f"Rate limit info: {client.rate_limit_info}")
    
    required_keys = ["limit", "remaining", "reset", "last_updated_client"]
    for key in required_keys:
        assert key in client.rate_limit_info, f"Missing key: {key}"
    
    print("✓ Rate limit info structure is correct")


async def main():
    """Run all tests"""
    print("Running Farcaster integration fix tests...")
    
    try:
        await test_empty_content_validation()
        await test_markdown_stripping()
        await test_content_with_image()
        await test_rate_limit_info_structure()
        
        print("\n🎉 All tests passed! The fixes are working correctly.")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
