#!/usr/bin/env python3
"""
Simple test for daily rate limiting data structures without full imports.
"""

import time
from collections import deque


class DailyRateLimit:
    """
    Tracks daily rate limiting for specific actions with persistence.
    """
    def __init__(self, action_name: str, daily_limit: int = 3):
        self.action_name = action_name
        self.timestamps = []
        self.daily_limit = daily_limit
        self.last_reset = time.time()
    
    def clean_old_entries(self, current_time: float):
        """Remove entries older than 24 hours."""
        cutoff_time = current_time - 86400  # 24 hours
        self.timestamps = [ts for ts in self.timestamps if ts >= cutoff_time]
        
    def can_execute(self, current_time: float, is_mention: bool = False) -> tuple[bool, str]:
        """Check if action can be executed within daily limits."""
        # Mentions bypass daily limits
        if is_mention:
            return True, ""
            
        self.clean_old_entries(current_time)
        
        if len(self.timestamps) >= self.daily_limit:
            oldest_timestamp = min(self.timestamps) if self.timestamps else current_time
            wait_time = 86400 - (current_time - oldest_timestamp)
            return False, f"Daily limit exceeded: {len(self.timestamps)}/{self.daily_limit} per day. Wait {wait_time:.0f}s"
            
        return True, ""
        
    def record_execution(self, current_time: float):
        """Record a new execution."""
        self.clean_old_entries(current_time)
        self.timestamps.append(current_time)


def test_daily_rate_limiting():
    """Test the daily rate limiting functionality."""
    
    print("Testing Daily Rate Limiting with Mention Bypass")
    print("=" * 50)
    
    # Create daily rate limiter
    limiter = DailyRateLimit("SendFarcasterReplyTool", daily_limit=3)
    current_time = time.time()
    
    # Test normal execution up to limit
    print("Testing normal replies (up to daily limit):")
    for i in range(4):  # Try 4, should block the 4th
        can_execute, reason = limiter.can_execute(current_time, is_mention=False)
        print(f"  Attempt {i+1}: {'✅ ALLOWED' if can_execute else '❌ BLOCKED'}")
        if reason:
            print(f"    Reason: {reason}")
        
        if can_execute:
            limiter.record_execution(current_time)
    
    print(f"\nCurrent usage: {len(limiter.timestamps)}/{limiter.daily_limit}")
    
    # Test mention bypass
    print("\nTesting mention bypass:")
    for i in range(3):
        can_execute, reason = limiter.can_execute(current_time, is_mention=True)
        print(f"  Mention {i+1}: {'✅ ALLOWED' if can_execute else '❌ BLOCKED'}")
        if reason:
            print(f"    Reason: {reason}")
    
    # Test cleanup
    print("\nTesting cleanup of old entries:")
    old_time = current_time - 90000  # More than 24 hours ago
    limiter.timestamps.extend([old_time, old_time + 100])
    print(f"  Before cleanup: {len(limiter.timestamps)} timestamps")
    limiter.clean_old_entries(current_time)
    print(f"  After cleanup: {len(limiter.timestamps)} timestamps")
    
    print("\n✅ All tests completed!")


if __name__ == "__main__":
    test_daily_rate_limiting()
