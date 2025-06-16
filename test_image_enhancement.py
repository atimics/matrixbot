#!/usr/bin/env python3
"""
Test script to demonstrate the new image description enhancement in messages.
"""

import asyncio
from chatbot.tools.message_enhancement import extract_image_description, enhance_message_with_image

def test_image_description_extraction():
    """Test the image description extraction function."""
    
    test_cases = [
        # Valid cases
        ('"image_description": "a cat sitting on a windowsill" This is a beautiful scene!', 
         "a cat sitting on a windowsill", "This is a beautiful scene!"),
        
        ('"image": "sunset over mountains" What a peaceful evening.', 
         "sunset over mountains", "What a peaceful evening."),
         
        ('"img": "abstract digital art" Creative inspiration strikes!', 
         "abstract digital art", "Creative inspiration strikes!"),
         
        ('image_description: "robot in a garden" No quotes around key', 
         "robot in a garden", "No quotes around key"),
         
        # Invalid cases (should return None, original_content)
        ("Just a regular message with no image description", 
         None, "Just a regular message with no image description"),
         
        ("image_description is mentioned but not at start", 
         None, "image_description is mentioned but not at start"),
         
        ("", None, ""),
    ]
    
    print("Testing image description extraction:")
    print("=" * 60)
    
    for i, (input_text, expected_desc, expected_content) in enumerate(test_cases, 1):
        actual_desc, actual_content = extract_image_description(input_text)
        
        success = (actual_desc == expected_desc and actual_content == expected_content)
        status = "✅ PASS" if success else "❌ FAIL"
        
        print(f"Test {i}: {status}")
        print(f"  Input: '{input_text}'")
        print(f"  Expected: desc='{expected_desc}', content='{expected_content}'")
        print(f"  Actual:   desc='{actual_desc}', content='{actual_content}'")
        print()
    
    print("=" * 60)

async def test_message_enhancement_demo():
    """Demonstrate how the message enhancement would work (without actual generation)."""
    
    print("Message Enhancement Demo:")
    print("=" * 60)
    
    # Mock ActionContext for demo
    class MockActionContext:
        def __init__(self):
            self.arweave_service = None
            self.world_state_manager = None
    
    mock_context = MockActionContext()
    
    test_messages = [
        '"image_description": "a cozy coffee shop interior" Good morning! Starting the day with some creativity.',
        '"img": "futuristic city skyline" Imagining what our world could look like in 2050.',
        "Regular message without any image generation.",
        '"image": "mountain landscape at dawn" Nature is the best artist.',
    ]
    
    for i, message in enumerate(test_messages, 1):
        print(f"Message {i}:")
        print(f"  Original: '{message}'")
        
        # Extract description (this part actually works)
        desc, remaining = extract_image_description(message)
        
        if desc:
            print(f"  → Would generate image: '{desc}'")
            print(f"  → Enhanced message: '🎨 Generated image: {desc}\\n\\n{remaining}'")
            print(f"  → Image would be auto-posted to gallery and current channel")
        else:
            print(f"  → No image generation needed")
            print(f"  → Message unchanged: '{message}'")
        
        print()
    
    print("=" * 60)

def main():
    """Run all tests."""
    print("🎨 Image Description Enhancement Testing")
    print("=" * 60)
    print()
    
    # Test extraction function
    test_image_description_extraction()
    print()
    
    # Demo enhancement workflow
    asyncio.run(test_message_enhancement_demo())
    
    print("✨ All tests completed!")
    print()
    print("Usage Examples:")
    print('- "image_description": "sunset over ocean" Beautiful evening!')
    print('- "img": "robot and human shaking hands" AI-human collaboration!')
    print('- "image": "abstract patterns" Expressing creativity through code.')

if __name__ == "__main__":
    main()
