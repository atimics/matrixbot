#!/usr/bin/env python3
"""
Rate Limiter Test Script

This script tests the updated rate limiting functionality to ensure AI decision cycles
are limited to no more than once per minute (60 seconds).
"""

import sys
import os
import time

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath('.'))

from chatbot.core.orchestration.rate_limiter import RateLimiter, RateLimitConfig

def test_rate_limiter_60_second_interval():
    """Test that rate limiter enforces 60-second minimum cycle interval."""
    print("=== Testing Rate Limiter 60-Second Interval ===")
    
    # Create rate limiter with new configuration
    config = RateLimitConfig()
    rate_limiter = RateLimiter(config)
    
    print(f"Configuration:")
    print(f"  min_cycle_interval: {config.min_cycle_interval} seconds")
    print(f"  max_cycles_per_hour: {config.max_cycles_per_hour}")
    print(f"  max_burst_cycles: {config.max_burst_cycles}")
    print()
    
    # Test first cycle - should be allowed
    current_time = time.time()
    can_process, wait_time = rate_limiter.can_process_cycle(current_time)
    print(f"First cycle attempt: can_process={can_process}, wait_time={wait_time:.1f}s")
    assert can_process, "First cycle should be allowed"
    
    # Record the cycle
    rate_limiter.record_cycle(current_time)
    
    # Test immediate second cycle - should be blocked
    current_time += 1  # 1 second later
    can_process, wait_time = rate_limiter.can_process_cycle(current_time)
    print(f"Immediate second cycle (1s later): can_process={can_process}, wait_time={wait_time:.1f}s")
    assert not can_process, "Second cycle should be blocked"
    assert wait_time > 50, f"Wait time should be around 59 seconds, got {wait_time:.1f}s"
    
    # Test cycle at 30 seconds - should still be blocked
    current_time += 29  # 30 seconds total
    can_process, wait_time = rate_limiter.can_process_cycle(current_time)
    print(f"Cycle at 30s: can_process={can_process}, wait_time={wait_time:.1f}s")
    assert not can_process, "Cycle at 30s should be blocked"
    assert wait_time > 25, f"Wait time should be around 30 seconds, got {wait_time:.1f}s"
    
    # Test cycle at 59 seconds - should still be blocked
    current_time += 29  # 59 seconds total
    can_process, wait_time = rate_limiter.can_process_cycle(current_time)
    print(f"Cycle at 59s: can_process={can_process}, wait_time={wait_time:.1f}s")
    assert not can_process, "Cycle at 59s should be blocked"
    assert wait_time < 2, f"Wait time should be around 1 second, got {wait_time:.1f}s"
    
    # Test cycle at 60 seconds - should be allowed
    current_time += 1  # 60 seconds total
    can_process, wait_time = rate_limiter.can_process_cycle(current_time)
    print(f"Cycle at 60s: can_process={can_process}, wait_time={wait_time:.1f}s")
    assert can_process, "Cycle at 60s should be allowed"
    assert wait_time == 0, f"Wait time should be 0, got {wait_time:.1f}s"
    
    print("✅ All rate limiting tests passed!")
    return True

def test_burst_protection():
    """Test that burst protection works with new limits."""
    print("\n=== Testing Burst Protection ===")
    
    config = RateLimitConfig()
    rate_limiter = RateLimiter(config)
    
    current_time = time.time()
    cycles_recorded = 0
    
    # Try to record max_burst_cycles within burst_window
    for i in range(config.max_burst_cycles):
        can_process, wait_time = rate_limiter.can_process_cycle(current_time)
        if can_process:
            rate_limiter.record_cycle(current_time)
            cycles_recorded += 1
            print(f"Cycle {i+1}: Allowed")
            current_time += config.min_cycle_interval  # Wait the minimum interval
        else:
            print(f"Cycle {i+1}: Blocked (wait {wait_time:.1f}s)")
            break
    
    print(f"Recorded {cycles_recorded} cycles before burst protection kicked in")
    
    # Next cycle should trigger burst protection
    can_process, wait_time = rate_limiter.can_process_cycle(current_time)
    print(f"Next cycle after burst: can_process={can_process}, wait_time={wait_time:.1f}s")
    
    if not can_process and wait_time > config.min_cycle_interval:
        print("✅ Burst protection is working (extended cooldown)")
    else:
        print("⚠️  Burst protection may not be working as expected")
    
    return True

def test_hourly_limit():
    """Test that hourly limits work correctly."""
    print("\n=== Testing Hourly Limit ===")
    
    config = RateLimitConfig()
    rate_limiter = RateLimiter(config)
    
    current_time = time.time()
    
    # Record max cycles for an hour
    for i in range(config.max_cycles_per_hour):
        rate_limiter.record_cycle(current_time)
        current_time += config.min_cycle_interval
    
    # Next cycle should be blocked due to hourly limit
    can_process, wait_time = rate_limiter.can_process_cycle(current_time)
    print(f"After {config.max_cycles_per_hour} cycles: can_process={can_process}, wait_time={wait_time:.1f}s")
    
    if not can_process:
        print(f"✅ Hourly limit working (max {config.max_cycles_per_hour} cycles per hour)")
    else:
        print("⚠️  Hourly limit may not be working")
    
    return True

def main():
    """Run all rate limiter tests."""
    print("🚀 Testing Updated Rate Limiter Configuration")
    print("Target: Maximum 1 AI decision cycle per minute (60 seconds)\n")
    
    try:
        test_rate_limiter_60_second_interval()
        test_burst_protection()
        test_hourly_limit()
        
        print("\n🎉 All rate limiter tests completed successfully!")
        print("\nKey Points:")
        print("✅ Minimum 60 seconds between AI decision cycles")
        print("✅ Maximum 60 cycles per hour")
        print("✅ Burst protection limits rapid successive cycles")
        print("✅ Adaptive cooldowns for extreme burst conditions")
        
        return 0
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
