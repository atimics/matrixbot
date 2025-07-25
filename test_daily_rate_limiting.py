#!/usr/bin/env python3
"""
Test script to verify daily rate limiting functionality for Farcaster replies.
"""

import time
from chatbot.core.orchestration.rate_limiter import RateLimiter, RateLimitConfig


def test_daily_rate_limiting():
    """Test that daily rate limiting works correctly."""
    
    # Create config with daily limit
    config = RateLimitConfig()
    config.daily_limits = {"SendFarcasterReplyTool": 3}
    
    # Create rate limiter
    rate_limiter = RateLimiter(config)
    
    current_time = time.time()
    action_name = "SendFarcasterReplyTool"
    
    print("Testing daily rate limiting for SendFarcasterReplyTool...")
    print(f"Daily limit: {config.daily_limits[action_name]} replies per day")
    
    # Test normal replies (should be rate limited)
    for i in range(5):
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
    
    # Test mention replies (should bypass daily limit)
    print(f"\n" + "="*50)
    print("Testing mention bypass...")
    
    for i in range(3):
        can_execute, reason = rate_limiter.can_execute_action(
            action_name, current_time, is_mention=True
        )
        
        print(f"\nMention attempt {i+1}:")
        print(f"  Can execute: {can_execute}")
        if not can_execute:
            print(f"  Reason: {reason}")
        else:
            print(f"  Mention bypassed daily limit successfully!")
    
    # Show current status
    print(f"\n" + "="*50)
    print("Current rate limit status:")
    status = rate_limiter.get_rate_limit_status(current_time)
    
    if "daily_action_limits" in status and action_name in status["daily_action_limits"]:
        daily_status = status["daily_action_limits"][action_name]
        print(f"Daily usage: {daily_status['used']}/{daily_status['limit']}")
        print(f"Remaining: {daily_status['remaining']}")
    
    hourly_status = status["action_limits"][action_name]
    print(f"Hourly usage: {hourly_status['used']}/{hourly_status['limit']}")


if __name__ == "__main__":
    test_daily_rate_limiting()
