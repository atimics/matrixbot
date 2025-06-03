#!/usr/bin/env python3
"""
Test script to verify payload size optimizations are working correctly.
"""

import json
import time
from chatbot.core.world_state.structures import WorldStateData, Message, Channel
from chatbot.core.world_state.payload_builder import PayloadBuilder

def create_sample_world_state():
    """Create a sample world state with various data types for testing."""
    world_state = WorldStateData()
    
    # Add sample channels with messages
    for i in range(3):
        channel = Channel(
            id=f"channel_{i}",
            type="farcaster" if i % 2 == 0 else "matrix",
            name=f"Test Channel {i} with a very long name that should be truncated",
            recent_messages=[],
            last_checked=time.time()
        )
        
        # Add sample messages
        for j in range(15):  # More than the default limit
            msg = Message(
                id=f"msg_{i}_{j}",
                channel_id=f"channel_{i}",
                channel_type=channel.type,
                sender=f"user_{j}",
                content=f"This is a test message with some content that might be quite long and should be truncated in the optimized version. Message {j} in channel {i}.",
                timestamp=time.time() - (j * 60),  # Messages from different times
                sender_username=f"user_{j}",
                sender_fid=j if channel.type == "farcaster" else None,
                sender_bio=f"This is a very long bio for user {j} that contains lots of information about the user and should be truncated for optimization purposes."
            )
            channel.recent_messages.append(msg)
        
        world_state.channels[channel.id] = channel
    
    # Add some action history
    from chatbot.core.world_state.structures import ActionHistory
    for i in range(10):
        action = ActionHistory(
            action_type=f"test_action_{i}",
            parameters={"param1": f"value_{i}", "long_param": "very long parameter value that should be truncated"},
            result="success",
            timestamp=time.time() - (i * 120)
        )
        world_state.action_history.append(action)
    
    # Add some tool cache data
    world_state.tool_cache = {
        f"get_user_timeline:user_{i}": {
            "timestamp": time.time(),
            "result_type": "timeline",
            "data": {"casts": [f"cast_{j}" for j in range(20)]}  # Large data
        }
        for i in range(5)
    }
    
    # Add some user data
    from chatbot.core.world_state.structures import FarcasterUserDetails
    for i in range(3):
        user = FarcasterUserDetails(
            fid=str(i),
            username=f"user_{i}",
            display_name=f"User {i} Display Name",
            bio=f"This is a very long bio for user {i} that contains lots of information and should be truncated.",
            follower_count=1000 + i * 100,
            power_badge=i % 2 == 0
        )
        world_state.farcaster_users[str(i)] = user
    
    return world_state

def test_payload_sizes():
    """Test payload sizes with different optimization settings."""
    print("Testing Payload Size Optimizations")
    print("=" * 50)
    
    world_state = create_sample_world_state()
    builder = PayloadBuilder()
    
    # Test without optimization
    print("\n1. Building payload WITHOUT optimization...")
    config_full = {
        "optimize_for_size": False,
        "include_detailed_user_info": True,
        "max_messages_per_channel": 10,
        "max_action_history": 5,
        "bot_fid": "123",
        "bot_username": "testbot"
    }
    
    payload_full = builder.build_full_payload(
        world_state, 
        primary_channel_id="channel_0", 
        config=config_full
    )
    
    payload_full_json = json.dumps(payload_full, default=str)
    full_size = len(payload_full_json.encode('utf-8'))
    
    print(f"Full payload size: {full_size:,} bytes ({full_size/1024:.2f} KB)")
    
    # Test with optimization
    print("\n2. Building payload WITH optimization...")
    config_optimized = {
        "optimize_for_size": True,
        "include_detailed_user_info": False,
        "max_messages_per_channel": 8,
        "max_action_history": 4,
        "bot_fid": "123",
        "bot_username": "testbot"
    }
    
    payload_optimized = builder.build_full_payload(
        world_state, 
        primary_channel_id="channel_0", 
        config=config_optimized
    )
    
    payload_optimized_json = json.dumps(payload_optimized, default=str)
    optimized_size = len(payload_optimized_json.encode('utf-8'))
    
    print(f"Optimized payload size: {optimized_size:,} bytes ({optimized_size/1024:.2f} KB)")
    
    # Calculate savings
    savings = full_size - optimized_size
    savings_percent = (savings / full_size) * 100
    
    print(f"\nOptimization Results:")
    print(f"Size reduction: {savings:,} bytes ({savings/1024:.2f} KB)")
    print(f"Percentage saved: {savings_percent:.1f}%")
    
    # Compare structure differences
    print(f"\n3. Structure comparison:")
    print(f"Full payload channels: {len(payload_full.get('channels', {}))}")
    print(f"Optimized payload channels: {len(payload_optimized.get('channels', {}))}")
    
    full_messages = sum(len(ch.get('recent_messages', [])) for ch in payload_full.get('channels', {}).values())
    opt_messages = sum(len(ch.get('recent_messages', [])) for ch in payload_optimized.get('channels', {}).values())
    
    print(f"Full payload messages: {full_messages}")
    print(f"Optimized payload messages: {opt_messages}")
    
    print(f"Full payload actions: {len(payload_full.get('action_history', []))}")
    print(f"Optimized payload actions: {len(payload_optimized.get('actions', []))}")
    
    # Test size estimation
    print(f"\n4. Testing size estimation...")
    estimated_size = builder.estimate_payload_size(world_state)
    print(f"Estimated size: {estimated_size:,} bytes ({estimated_size/1024:.2f} KB)")
    print(f"Actual full size: {full_size:,} bytes ({full_size/1024:.2f} KB)")
    print(f"Estimation accuracy: {((estimated_size/full_size)*100):.1f}% of actual")
    
    return {
        "full_size": full_size,
        "optimized_size": optimized_size,
        "savings_percent": savings_percent,
        "estimated_size": estimated_size
    }

if __name__ == "__main__":
    results = test_payload_sizes()
    
    print(f"\n" + "="*50)
    print("SUMMARY")
    print(f"Full payload: {results['full_size']/1024:.2f} KB")
    print(f"Optimized payload: {results['optimized_size']/1024:.2f} KB")
    print(f"Savings: {results['savings_percent']:.1f}%")
    print(f"Size estimation accuracy: {((results['estimated_size']/results['full_size'])*100):.1f}%")
