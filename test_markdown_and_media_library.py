#!/usr/bin/env python3
"""
Test script to verify markdown stripping and media library functionality work end-to-end.
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

from chatbot.tools.farcaster_tools import SendFarcasterPostTool, SendFarcasterReplyTool
from chatbot.tools.media_generation_tools import GenerateImageTool
from chatbot.core.world_state import WorldStateManager
from chatbot.utils.markdown_utils import strip_markdown


async def test_markdown_stripping():
    """Test that markdown gets stripped from Farcaster tools."""
    print("=== Testing Markdown Stripping ===")
    
    # Test the strip_markdown function directly
    test_content = """# This is a header

**Bold text** and *italic text*

- List item 1
- List item 2

[Link text](https://example.com)

`code snippet`

> Block quote
    """
    
    stripped = strip_markdown(test_content)
    print("Original content:")
    print(repr(test_content))
    print("\nStripped content:")
    print(repr(stripped))
    
    # Verify it's properly stripped
    assert "**" not in stripped
    assert "*" not in stripped
    assert "[" not in stripped
    assert "]" not in stripped
    assert "#" not in stripped.split('\n')[0]  # First line shouldn't have header marker
    assert "`" not in stripped
    # Check that block quotes are stripped (line doesn't start with >)
    for line in stripped.split('\n'):
        assert not line.strip().startswith('>')
    
    print("✅ Markdown stripping works correctly!")
    return True


async def test_farcaster_tools_markdown_stripping():
    """Test that Farcaster tools strip markdown from content."""
    print("\n=== Testing Farcaster Tools Markdown Stripping ===")
    
    # Mock context
    context = MagicMock()
    context.farcaster_observer = AsyncMock()
    # Mock should return a dict, not a string
    context.farcaster_observer.post_cast = AsyncMock(return_value={"success": True, "hash": "mock_hash"})
    context.farcaster_observer.reply_to_cast = AsyncMock(return_value={"success": True, "hash": "mock_hash"})
    context.world_state_manager = MagicMock()
    context.world_state_manager.add_action_result = MagicMock()
    # Mock the duplicate detection to return False (not a duplicate)
    context.world_state_manager.has_sent_farcaster_post = MagicMock(return_value=False)
    context.world_state_manager.has_replied_to_cast = MagicMock(return_value=False)
    
    # Test SendFarcasterPostTool with unique content
    post_tool = SendFarcasterPostTool()
    import time
    unique_suffix = str(int(time.time() * 1000))  # Add unique timestamp
    markdown_content = f"**Bold** and *italic* text with [link](https://example.com) - {unique_suffix}"
    
    result = await post_tool.execute({
        "content": markdown_content
    }, context)
    
    print(f"Post tool result: {result}")
    
    # Check that the call was made with stripped content
    call_args = context.farcaster_observer.post_cast.call_args
    if call_args is None:
        print("❌ No call was made to post_cast")
        return False
    
    # Get content from keyword arguments
    posted_content = call_args[1]["content"]  # From kwargs
    
    print(f"Content sent to Farcaster: {repr(posted_content)}")
    
    # Verify markdown was stripped
    assert "**" not in posted_content
    assert "*" not in posted_content
    assert "[" not in posted_content
    assert "]" not in posted_content
    
    print("✅ Farcaster post tool strips markdown correctly!")
    
    # Test SendFarcasterReplyTool  
    reply_tool = SendFarcasterReplyTool()
    reply_markdown = f"**Reply** with *formatting* and [links](https://test.com) - {unique_suffix}"
    
    reply_result = await reply_tool.execute({
        "content": reply_markdown,
        "reply_to_hash": "test_hash"
    }, context)
    
    print(f"Reply tool result: {reply_result}")
    
    # Check that the reply call was made with stripped content
    reply_call_args = context.farcaster_observer.reply_to_cast.call_args
    if reply_call_args is None:
        print("❌ No call was made to reply_to_cast")
        return False
        
    print(f"Reply call args: {reply_call_args}")
    print(f"Reply call kwargs: {reply_call_args[1]}")
    
    # The reply tool uses positional arguments: reply_to_cast(content, reply_to_hash)
    reply_content = reply_call_args[0][0]  # First positional argument is content
    
    print(f"Reply content sent to Farcaster: {repr(reply_content)}")
    
    # Verify markdown was stripped in reply too
    assert "**" not in reply_content
    assert "*" not in reply_content
    assert "[" not in reply_content
    assert "]" not in reply_content
    
    print("✅ Farcaster reply tool strips markdown correctly!")
    return True


async def test_media_library_functionality():
    """Test that the media library functionality works."""
    print("\n=== Testing Media Library Functionality ===")
    
    # Create world state manager
    wsm = WorldStateManager()
    
    # Test recording generated media
    wsm.record_generated_media(
        media_url="https://s3.example.com/image1.png",
        media_type="image",
        prompt="A beautiful sunset over mountains",
        service_used="google_gemini",
        aspect_ratio="16:9",
        metadata={"generation_time": 3.5}
    )
    
    wsm.record_generated_media(
        media_url="https://s3.example.com/video1.mp4", 
        media_type="video",
        prompt="Birds flying in formation",
        service_used="google_veo",
        aspect_ratio="16:9",
        metadata={"input_image": "https://s3.example.com/image1.png"}
    )
    
    print(f"Generated media library now contains {len(wsm.state.generated_media_library)} items")
    
    # Test AI payload includes media library
    ai_payload = wsm.get_ai_optimized_payload()
    
    assert "generated_media_library" in ai_payload
    media_library = ai_payload["generated_media_library"]
    
    print(f"AI payload includes {len(media_library)} media items")
    
    # Verify content
    assert len(media_library) == 2
    
    first_media = media_library[0]
    assert first_media["type"] == "image"
    assert first_media["prompt"] == "A beautiful sunset over mountains"
    assert first_media["service_used"] == "google_gemini"
    assert first_media["url"] == "https://s3.example.com/image1.png"
    
    second_media = media_library[1]
    assert second_media["type"] == "video"
    assert second_media["prompt"] == "Birds flying in formation"
    assert second_media["service_used"] == "google_veo"
    assert second_media["url"] == "https://s3.example.com/video1.mp4"
    
    print("✅ Media library functionality works correctly!")
    
    # Test the library includes correct fields
    for media in media_library:
        required_fields = ["url", "type", "prompt", "service_used", "timestamp", "aspect_ratio", "metadata"]
        for field in required_fields:
            assert field in media, f"Missing field: {field}"
    
    print("✅ All required media library fields present!")
    return True


async def test_generate_image_tool_integration():
    """Test that GenerateImageTool records media in the library."""
    print("\n=== Testing GenerateImageTool Integration ===")
    
    # Mock context
    context = MagicMock()
    context.s3_service = AsyncMock()
    context.s3_service.upload_image_data = AsyncMock(return_value="https://s3.example.com/generated_123.png")
    context.world_state_manager = WorldStateManager()
    
    # Mock Google AI client 
    with MockGoogleAI():
        tool = GenerateImageTool()
        
        result = await tool.execute({
            "prompt": "A futuristic robot in a laboratory",
            "aspect_ratio": "1:1"
        }, context)
        
        print(f"Generate image result: {result}")
        
        # Check that media was recorded
        media_library = context.world_state_manager.state.generated_media_library
        assert len(media_library) == 1
        
        recorded_media = media_library[0]
        assert recorded_media["type"] == "image"
        assert recorded_media["prompt"] == "A futuristic robot in a laboratory"
        assert recorded_media["aspect_ratio"] == "1:1"
        assert "https://s3.example.com/" in recorded_media["url"]
        
        print("✅ GenerateImageTool records media in library correctly!")
        return True


class MockGoogleAI:
    """Context manager to mock Google AI calls."""
    
    def __enter__(self):
        # Mock the Google AI client
        import chatbot.tools.media_generation_tools
        self.original_google_client = getattr(chatbot.tools.media_generation_tools, 'GoogleAIMediaClient', None)
        
        mock_client = MagicMock()
        mock_instance = AsyncMock()
        mock_instance.generate_image_gemini = AsyncMock(return_value=b"fake_image_data")
        mock_client.return_value = mock_instance
        
        chatbot.tools.media_generation_tools.GoogleAIMediaClient = mock_client
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        # Restore original
        if self.original_google_client:
            import chatbot.tools.media_generation_tools
            chatbot.tools.media_generation_tools.GoogleAIMediaClient = self.original_google_client


async def main():
    """Run all tests."""
    print("Testing Markdown Stripping and Media Library Implementation")
    print("=" * 60)
    
    try:
        await test_markdown_stripping()
        await test_farcaster_tools_markdown_stripping()
        await test_media_library_functionality()
        await test_generate_image_tool_integration()
        
        print("\n" + "=" * 60)
        print("🎉 All tests passed! Implementation is working correctly.")
        print("\nSummary:")
        print("✅ Markdown stripping utility function works")
        print("✅ Farcaster tools strip markdown from content") 
        print("✅ Media library records generated media")
        print("✅ AI payload includes media library")
        print("✅ GenerateImageTool integration works")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


if __name__ == "__main__":
    asyncio.run(main())
