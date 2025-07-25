#!/usr/bin/env python3
"""
Test script to verify persistent daily rate limiting functionality for Farcaster replies.
"""

import time
import tempfile
import os
from pathlib import Path

from chatbot.core.orchestration.rate_limiter import RateLimiter, RateLimitConfig
from chatbot.core.world_state.manager import WorldStateManager
from chatbot.core.world_state.structures import DailyRateLimit


def test_persistent_daily_rate_limiting():
    """Test that daily rate limiting persists across restarts."""
    
    # Create a temporary directory for state persistence
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create world state manager with persistent storage
        world_state = WorldStateManager()
        
        # Create config with daily limit
        config = RateLimitConfig()
        config.daily_limits = {"SendFarcasterReplyTool": 3}
        
        # Create rate limiter with world state
        rate_limiter = RateLimiter(config, world_state_manager=world_state)
        
        current_time = time.time()
        action_name = "SendFarcasterReplyTool"
        
        print("Testing persistent daily rate limiting for SendFarcasterReplyTool...")
        print(f"Daily limit: {config.daily_limits[action_name]} replies per day")
        
        # Test normal replies up to the limit
        for i in range(3):
            can_execute, reason = rate_limiter.can_execute_action(
                action_name, current_time, is_mention=False
            )
            
            print(f"\nAttempt {i+1} (non-mention):")
            print(f"  Can execute: {can_execute}")
            if not can_execute:
                print(f"  Reason: {reason}")
            else:
                # Record the action
                rate_limiter.record_action(action_name, current_time)
                print(f"  Action recorded successfully")
        
        # Test that the 4th attempt is blocked
        can_execute, reason = rate_limiter.can_execute_action(
            action_name, current_time, is_mention=False
        )
        print(f"\nAttempt 4 (non-mention, should be blocked):")
        print(f"  Can execute: {can_execute}")
        print(f"  Reason: {reason}")
        
        # Test mention bypass
        can_execute, reason = rate_limiter.can_execute_action(
            action_name, current_time, is_mention=True
        )
        print(f"\nMention attempt (should bypass daily limit):")
        print(f"  Can execute: {can_execute}")
        if can_execute:
            print(f"  Mention bypassed daily limit successfully!")
        
        # Show current status
        print(f"\n" + "="*50)
        print("Current rate limit status:")
        status = rate_limiter.get_rate_limit_status(current_time)
        
        if "daily_action_limits" in status and action_name in status["daily_action_limits"]:
            daily_status = status["daily_action_limits"][action_name]
            print(f"Daily usage: {daily_status['used']}/{daily_status['limit']}")
            print(f"Remaining: {daily_status['remaining']}")
        
        # Simulate restart by creating a new rate limiter with the same world state
        print(f"\n" + "="*50)
        print("SIMULATING RESTART...")
        
        # Create new rate limiter instance (simulating restart)
        rate_limiter_after_restart = RateLimiter(config, world_state_manager=world_state)
        
        # Check if daily limits persist
        can_execute, reason = rate_limiter_after_restart.can_execute_action(
            action_name, current_time, is_mention=False
        )
        print(f"After restart - non-mention attempt:")
        print(f"  Can execute: {can_execute}")
        print(f"  Reason: {reason}")
        
        # Show status after restart
        status_after_restart = rate_limiter_after_restart.get_rate_limit_status(current_time)
        if "daily_action_limits" in status_after_restart and action_name in status_after_restart["daily_action_limits"]:
            daily_status = status_after_restart["daily_action_limits"][action_name]
            print(f"Daily usage after restart: {daily_status['used']}/{daily_status['limit']}")
            print(f"Remaining after restart: {daily_status['remaining']}")
            
            # Verify persistence
            if daily_status['used'] == 3:
                print("✅ SUCCESS: Daily rate limits are persistent across restarts!")
            else:
                print("❌ FAILURE: Daily rate limits were not preserved")
        
        # Test mention bypass still works after restart
        can_execute_mention, _ = rate_limiter_after_restart.can_execute_action(
            action_name, current_time, is_mention=True
        )
        if can_execute_mention:
            print("✅ SUCCESS: Mention bypass still works after restart!")
        else:
            print("❌ FAILURE: Mention bypass broken after restart")


def test_daily_rate_limit_cleanup():
    """Test that old daily rate limit entries are cleaned up."""
    
    print(f"\n" + "="*60)
    print("Testing daily rate limit cleanup...")
    
    # Create a DailyRateLimit instance
    daily_limiter = DailyRateLimit(action_name="TestAction", daily_limit=3)
    
    current_time = time.time()
    old_time = current_time - 86500  # More than 24 hours ago
    recent_time = current_time - 3600  # 1 hour ago
    
    # Add some old and recent timestamps
    daily_limiter.timestamps = [old_time, old_time + 100, recent_time, current_time - 10]
    
    print(f"Before cleanup: {len(daily_limiter.timestamps)} timestamps")
    daily_limiter.clean_old_entries(current_time)
    print(f"After cleanup: {len(daily_limiter.timestamps)} timestamps")
    
    # Should only have the recent ones
    if len(daily_limiter.timestamps) == 2:
        print("✅ SUCCESS: Old entries cleaned up correctly!")
    else:
        print("❌ FAILURE: Cleanup didn't work as expected")


if __name__ == "__main__":
    test_persistent_daily_rate_limiting()
    test_daily_rate_limit_cleanup()
