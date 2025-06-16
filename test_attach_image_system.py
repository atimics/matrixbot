#!/usr/bin/env python3
"""
Test script to demonstrate the new attach_image parameter functionality.
"""

def test_attach_image_examples():
    """Demonstrate how the new attach_image parameter works."""
    
    print("🔗 New attach_image Parameter Examples")
    print("=" * 60)
    print()
    
    examples = [
        {
            "scenario": "Using existing image from library",
            "tool": "send_matrix_message", 
            "params": {
                "channel_id": "!room123:matrix.org",
                "content": "Here's that sunset I generated earlier!",
                "attach_image": "media_img_1703123456"  # Existing media_id
            },
            "behavior": "Retrieves image URL from library using media_id"
        },
        {
            "scenario": "Generating new image on-the-fly",
            "tool": "send_farcaster_post",
            "params": {
                "content": "Check out this amazing view!",
                "attach_image": "mountain landscape at golden hour"  # Description
            },
            "behavior": "Generates new image, stores in library, attaches to post"
        },
        {
            "scenario": "Traditional explicit workflow (still works)",
            "tool": "generate_image",
            "params": {
                "prompt": "abstract digital art with neon colors"
            },
            "behavior": "Generates image, returns media_id for later use"
        },
        {
            "scenario": "Using generated media_id in next message",
            "tool": "send_matrix_message",
            "params": {
                "channel_id": "!room123:matrix.org", 
                "content": "My latest digital creation!",
                "attach_image": "media_img_1703123999"  # From previous generation
            },
            "behavior": "Attaches previously generated image"
        },
        {
            "scenario": "No attach_image parameter",
            "tool": "send_farcaster_post",
            "params": {
                "content": "Just a text post, no images"
            },
            "behavior": "Checks for recent media (5min), auto-attaches if found"
        }
    ]
    
    for i, example in enumerate(examples, 1):
        print(f"Example {i}: {example['scenario']}")
        print(f"Tool: {example['tool']}")
        print("Parameters:")
        for key, value in example['params'].items():
            print(f"  {key}: {repr(value)}")
        print(f"Behavior: {example['behavior']}")
        print()
    
    print("=" * 60)
    print()

def test_ai_workflow_scenarios():
    """Show different AI workflow scenarios."""
    
    print("🤖 AI Workflow Scenarios")
    print("=" * 60)
    print()
    
    scenarios = [
        {
            "name": "Quick Image + Message",
            "description": "AI wants to send a message with a new image",
            "steps": [
                "AI calls: send_matrix_message(channel, 'Beautiful morning!', attach_image='sunrise over city')",
                "System generates image from description",
                "System posts image to gallery AND current channel", 
                "System sends message with image attached",
                "User sees message + image in their channel immediately"
            ]
        },
        {
            "name": "Reuse Previous Image",
            "description": "AI wants to reference a previously generated image",
            "steps": [
                "AI checks generated_media_library for relevant images",
                "AI finds suitable image: media_img_1703123456",
                "AI calls: send_farcaster_post('Throwback to this sunset!', attach_image='media_img_1703123456')",
                "System retrieves image URL from library",
                "System posts to Farcaster with image attached"
            ]
        },
        {
            "name": "Build Library + Use Later",
            "description": "AI wants to generate content for later use",
            "steps": [
                "AI calls: generate_image('futuristic cityscape')",
                "System generates image, stores in library, returns media_id",
                "AI stores media_id for future reference",
                "Later: AI calls send_matrix_message('Future vision!', attach_image='media_img_xxx')",
                "System uses stored image for message"
            ]
        },
        {
            "name": "Auto-attachment Fallback",
            "description": "AI sends message without specifying image",
            "steps": [
                "AI recently generated an image (within 5 minutes)",
                "AI calls: send_matrix_message('Check this out!')",
                "System detects recent media in library",
                "System automatically attaches recent image",
                "Message sent with auto-attached image"
            ]
        }
    ]
    
    for i, scenario in enumerate(scenarios, 1):
        print(f"Scenario {i}: {scenario['name']}")
        print(f"Description: {scenario['description']}")
        print("Steps:")
        for j, step in enumerate(scenario['steps'], 1):
            print(f"  {j}. {step}")
        print()
    
    print("=" * 60)

def main():
    """Run all demonstrations."""
    print("🎨 Enhanced AI Image Attachment System")
    print("=" * 60)
    print()
    
    test_attach_image_examples()
    test_ai_workflow_scenarios()
    
    print("✨ Key Benefits:")
    print("- ✅ Flexible: AI can use existing images OR generate new ones")
    print("- ✅ Efficient: One tool call for message + image")
    print("- ✅ Smart: Auto-attachment fallback for recent media")
    print("- ✅ Library: All generated images stored for reuse")
    print("- ✅ Choice: AI can choose between quick generation or deliberate workflow")
    print()
    print("🔧 AI Tool Parameters:")
    print("- attach_image: 'media_img_123' (use existing) OR 'description' (generate new)")
    print("- generate_image: Still available for explicit image creation")
    print("- send_matrix_message/send_farcaster_post: Enhanced with attach_image support")

if __name__ == "__main__":
    main()
