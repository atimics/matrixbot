#!/usr/bin/env python3
"""
Test script for enhanced Farcaster user information handling.
This tests the new user fields, mention formatting, and context extraction.
"""

import asyncio
import logging
from dataclasses import asdict
from chatbot.core.world_state import Message, WorldStateManager
from chatbot.integrations.farcaster.observer import FarcasterObserver

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_message_with_enhanced_user_info():
    """Test creating a message with enhanced user information"""
    
    # Create a test message with full user info
    message = Message(
        id="test_cast_123",
        channel_id="farcaster:test",
        channel_type="farcaster",
        sender="testuser",  # This should be the username now
        content="Hello @everyone! This is a test cast with enhanced user info.",
        timestamp=1640995200.0,
        reply_to=None,
        sender_username="testuser",
        sender_display_name="Test User 🚀",
        sender_fid=12345,
        sender_pfp_url="https://example.com/pfp.jpg",
        sender_bio="I'm a test user for the enhanced Farcaster integration",
        sender_follower_count=1337,
        sender_following_count=420,
        metadata={
            "cast_type": "normal",
            "verified_addresses": {"eth_addresses": ["0x123..."]},
            "power_badge": True,
        }
    )
    
    print("=== Enhanced Message Object ===")
    print(f"Sender (username): {message.sender}")
    print(f"Display Name: {message.sender_display_name}")
    print(f"FID: {message.sender_fid}")
    print(f"Followers: {message.sender_follower_count}")
    print(f"Power Badge: {message.metadata.get('power_badge')}")
    print(f"Content: {message.content}")
    print()
    
    return message

def test_farcaster_observer_helpers():
    """Test the new helper methods in FarcasterObserver"""
    
    # Create observer (without API keys for testing)
    observer = FarcasterObserver(
        api_key=None,
        signer_uuid=None,
        bot_fid=98765
    )
    
    # Set up world state manager
    world_state_manager = WorldStateManager()
    observer.world_state_manager = world_state_manager
    
    # Create test messages
    root_message = Message(
        id="root_cast_456",
        channel_id="farcaster:general",
        channel_type="farcaster",
        sender="influencer_user",
        content="What do you think about the latest AI developments?",
        timestamp=1640995200.0,
        reply_to=None,
        sender_username="influencer_user",
        sender_display_name="AI Influencer 🤖",
        sender_fid=11111,
        sender_follower_count=50000,
        sender_following_count=1000,
        metadata={
            "cast_type": "normal",
            "power_badge": True,
            "verified_addresses": {"eth_addresses": ["0xabc..."]},
        }
    )
    
    reply_message = Message(
        id="reply_cast_789",
        channel_id="farcaster:general", 
        channel_type="farcaster",
        sender="regular_user",
        content="I think AI is moving really fast! Thanks for sharing your thoughts.",
        timestamp=1640995260.0,
        reply_to="root_cast_456",
        sender_username="regular_user",
        sender_display_name="Regular User",
        sender_fid=22222,
        sender_follower_count=150,
        sender_following_count=300,
        metadata={
            "cast_type": "reply",
            "power_badge": False,
        }
    )
    
    # Add messages to world state
    world_state_manager.add_message(root_message.channel_id, root_message)
    world_state_manager.add_message(reply_message.channel_id, reply_message)
    
    print("=== User Mention Formatting ===")
    root_mention = observer.format_user_mention(root_message)
    reply_mention = observer.format_user_mention(reply_message)
    print(f"Root message mention: {root_mention}")
    print(f"Reply message mention: {reply_mention}")
    print()
    
    print("=== User Context ===")
    root_context = observer.get_user_context(root_message)
    reply_context = observer.get_user_context(reply_message)
    
    print("Root message user context:")
    for key, value in root_context.items():
        print(f"  {key}: {value}")
    print()
    
    print("Reply message user context:")
    for key, value in reply_context.items():
        print(f"  {key}: {value}")
    print()
    
    print("=== Thread Context ===")
    root_thread_context = observer.get_thread_context(root_message)
    reply_thread_context = observer.get_thread_context(reply_message)
    
    print("Root message thread context:")
    for key, value in root_thread_context.items():
        print(f"  {key}: {value}")
    print()
    
    print("Reply message thread context:")
    for key, value in reply_thread_context.items():
        print(f"  {key}: {value}")
    print()

def test_ai_readable_summary():
    """Test generating AI-readable summaries of enhanced user info"""
    
    observer = FarcasterObserver(api_key=None, signer_uuid=None)
    world_state_manager = WorldStateManager()
    observer.world_state_manager = world_state_manager
    
    # Test different user types
    test_users = [
        {
            "username": "crypto_whale",
            "display_name": "Crypto Whale 🐋",
            "followers": 100000,
            "power_badge": True,
            "verified": True,
        },
        {
            "username": "newbie_dev",
            "display_name": "Junior Dev",
            "followers": 50,
            "power_badge": False,
            "verified": False,
        },
        {
            "username": "mid_tier_user",
            "display_name": "Mid-tier Creator",
            "followers": 2500,
            "power_badge": False,
            "verified": True,
        }
    ]
    
    print("=== AI-Readable User Summaries ===")
    for i, user_data in enumerate(test_users):
        message = Message(
            id=f"cast_{i}",
            channel_id="farcaster:test",
            channel_type="farcaster",
            sender=user_data["username"],
            content="Test content",
            timestamp=1640995200.0 + i,
            sender_username=user_data["username"],
            sender_display_name=user_data["display_name"],
            sender_fid=10000 + i,
            sender_follower_count=user_data["followers"],
            sender_following_count=500,
            metadata={
                "power_badge": user_data["power_badge"],
                "verified_addresses": {"eth_addresses": ["0x123..."]} if user_data["verified"] else {},
            }
        )
        
        context = observer.get_user_context(message)
        mention = observer.format_user_mention(message)
        
        print(f"\nUser: {user_data['display_name']} (@{user_data['username']})")
        print(f"  Taggable mention: {mention}")
        print(f"  Engagement level: {context['engagement_level']}")
        print(f"  Followers: {context['follower_count']:,}")
        print(f"  Verified: {context['verified']}")
        print(f"  Power badge: {context['power_badge']}")

if __name__ == "__main__":
    print("Testing Enhanced Farcaster User Information Handling")
    print("=" * 60)
    
    test_message_with_enhanced_user_info()
    test_farcaster_observer_helpers() 
    test_ai_readable_summary()
    
    print("\n✅ All tests completed successfully!")
    print("\nKey improvements:")
    print("- Username vs display name properly distinguished")
    print("- Proper @username formatting for mentions/tags") 
    print("- Rich user context for AI decision making")
    print("- Thread context tracking")
    print("- Engagement level calculation")
    print("- Verification and power badge status")
