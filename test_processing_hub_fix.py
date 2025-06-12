#!/usr/bin/env python3
"""
Test script to verify the processing hub fix for the 'Channel' object has no attribute 'items' error.
"""

import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from chatbot.core.orchestration.processing_hub import ProcessingHub
from chatbot.core.world_state.manager import WorldStateManager
from chatbot.core.world_state.payload_builder import PayloadBuilder
from chatbot.core.orchestration.rate_limiter import RateLimiter

def test_processing_hub_active_channels():
    """Test that the processing hub can handle the nested channel structure."""
    
    # Create a mock world state with the new nested structure
    world_state_manager = WorldStateManager()
    
    # Add a matrix channel
    world_state_manager.add_channel("test_room", "matrix", "Test Room")
    
    # Add a farcaster channel
    world_state_manager.add_channel("home", "farcaster", "Home Feed")
    
    # Add some messages to make channels active
    from chatbot.core.world_state.structures import Message
    import time
    
    matrix_msg = Message(
        id="msg1",
        sender="@user:example.com",
        content="Hello Matrix!",
        timestamp=time.time(),
        channel_type="matrix",
        channel_id="test_room"
    )
    world_state_manager.add_message("test_room", matrix_msg)
    
    farcaster_msg = Message(
        id="cast1",
        sender="testuser",
        content="Hello Farcaster!",
        timestamp=time.time(),
        channel_type="farcaster", 
        channel_id="home"
    )
    world_state_manager.add_message("home", farcaster_msg)
    
    # Create processing hub components
    payload_builder = PayloadBuilder()
    rate_limiter = RateLimiter()
    
    # Create processing hub
    processing_hub = ProcessingHub(
        world_state_manager=world_state_manager,
        payload_builder=payload_builder,
        rate_limiter=rate_limiter
    )
    
    # Test the _get_active_channels method that was causing the error
    world_state_dict = world_state_manager.to_dict()
    active_channels = processing_hub._get_active_channels(world_state_dict)
    
    print(f"World state structure: {list(world_state_dict.get('channels', {}).keys())}")
    print(f"Active channels found: {active_channels}")
    
    # Should find both channels as active
    assert len(active_channels) == 2
    assert "test_room" in active_channels
    assert "home" in active_channels
    
    print("✅ Processing hub fix verified successfully!")
    print("✅ No more 'Channel' object has no attribute 'items' errors!")

if __name__ == "__main__":
    test_processing_hub_active_channels()
