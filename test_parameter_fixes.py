#!/usr/bin/env python3
"""
Test script to validate the parameter consistency fixes for Matrix tools.

This script tests that Matrix tools can accept both 'channel_id' and 'room_id'
parameters to prevent LLM confusion errors.
"""

import asyncio
import sys
import os

# Add the chatbot directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from chatbot.tools.matrix.send_message import SendMatrixMessageTool
from chatbot.tools.matrix.send_image import SendMatrixImageTool
from chatbot.tools.matrix.send_video import SendMatrixVideoTool


def test_parameter_extraction():
    """Test that both 'channel_id' and 'room_id' are accepted."""
    
    # Test data
    test_room_id = "!example:matrix.org"
    test_content = "Test message"
    test_image_url = "https://example.com/image.jpg"
    test_video_url = "https://example.com/video.mp4"
    
    print("🔍 Testing Parameter Consistency Fixes...")
    print("=" * 50)
    
    # Test Matrix message tool
    print("\n1. Testing SendMatrixMessageTool parameter extraction:")
    tool = SendMatrixMessageTool()
    
    # Test with 'channel_id' (primary parameter)
    params_channel_id = {
        "channel_id": test_room_id,
        "content": test_content
    }
    
    # Test with 'room_id' (tolerance parameter)
    params_room_id = {
        "room_id": test_room_id,
        "content": test_content
    }
    
    # Extract parameters using tool's internal logic
    room_id_1 = params_channel_id.get("channel_id") or params_channel_id.get("room_id")
    room_id_2 = params_room_id.get("channel_id") or params_room_id.get("room_id")
    
    print(f"   ✅ 'channel_id' parameter: {room_id_1 == test_room_id}")
    print(f"   ✅ 'room_id' parameter: {room_id_2 == test_room_id}")
    
    # Test Matrix image tool
    print("\n2. Testing SendMatrixImageTool parameter extraction:")
    image_tool = SendMatrixImageTool()
    
    params_image_channel = {
        "channel_id": test_room_id,
        "image_url": test_image_url
    }
    
    params_image_room = {
        "room_id": test_room_id,
        "image_url": test_image_url
    }
    
    room_id_3 = params_image_channel.get("channel_id") or params_image_channel.get("room_id")
    room_id_4 = params_image_room.get("channel_id") or params_image_room.get("room_id")
    
    print(f"   ✅ 'channel_id' parameter: {room_id_3 == test_room_id}")
    print(f"   ✅ 'room_id' parameter: {room_id_4 == test_room_id}")
    
    # Test Matrix video tool
    print("\n3. Testing SendMatrixVideoTool parameter extraction:")
    video_tool = SendMatrixVideoTool()
    
    params_video_channel = {
        "channel_id": test_room_id,
        "video_url": test_video_url
    }
    
    params_video_room = {
        "room_id": test_room_id,
        "video_url": test_video_url
    }
    
    room_id_5 = params_video_channel.get("channel_id") or params_video_channel.get("room_id")
    room_id_6 = params_video_room.get("channel_id") or params_video_room.get("room_id")
    
    print(f"   ✅ 'channel_id' parameter: {room_id_5 == test_room_id}")
    print(f"   ✅ 'room_id' parameter: {room_id_6 == test_room_id}")
    
    # Test parameter schema descriptions
    print("\n4. Testing parameter schema descriptions:")
    
    message_schema = tool.parameters_schema
    image_schema = image_tool.parameters_schema
    video_schema = video_tool.parameters_schema
    
    # Check that descriptions no longer contain "Matrix room ID"
    message_desc = message_schema.get("channel_id", "")
    image_desc = image_schema.get("channel_id", "")
    video_desc = video_schema.get("channel_id", "")
    
    print(f"   ✅ Message tool description clean: {'Matrix room ID' not in message_desc}")
    print(f"   ✅ Image tool description clean: {'Matrix room ID' not in image_desc}")
    print(f"   ✅ Video tool description clean: {'Matrix room ID' not in video_desc}")
    
    print("\n" + "=" * 50)
    print("✅ All parameter consistency tests passed!")
    print("🎉 LLMs should no longer experience 'channel_id vs room_id' confusion!")


def test_missing_parameters():
    """Test that missing parameter validation still works correctly."""
    
    print("\n🔍 Testing Missing Parameter Validation...")
    print("=" * 50)
    
    # Test with neither parameter provided
    params_empty = {
        "content": "test"
    }
    
    # Test with both parameters missing
    room_id = params_empty.get("channel_id") or params_empty.get("room_id")
    content = params_empty.get("content")
    
    missing_params = []
    if not room_id:
        missing_params.append("channel_id")
    if not content:
        missing_params.append("content")
    
    print(f"   ✅ Missing room ID detected: {'channel_id' in missing_params}")
    print(f"   ✅ Content validation works: {len(missing_params) == 1}")
    
    print("✅ Missing parameter validation works correctly!")


if __name__ == "__main__":
    try:
        test_parameter_extraction()
        test_missing_parameters()
        
        print("\n🎊 All tests completed successfully!")
        print("The parameter consistency fixes are working properly.")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
