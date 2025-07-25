"""
Rate limiting service for Farcaster tools.
"""
import time
from typing import Dict, Tuple, Optional
from .farcaster_constants import (
    DEFAULT_DAILY_CAST_LIMIT,
    DEFAULT_DAILY_REPLY_LIMIT,
    DEFAULT_HOURLY_CAST_LIMIT
)


class FarcasterRateLimiter:
    """
    Rate limiter for Farcaster actions with mention exceptions.
    Addresses point 5: Rate-limiter coupling.
    """
    
    def __init__(self):
        self.action_history: Dict[str, list] = {}
        self.daily_limits = {
            "send_farcaster_post": DEFAULT_DAILY_CAST_LIMIT,
            "send_farcaster_reply": DEFAULT_DAILY_REPLY_LIMIT,
            "create_farcaster_thread": DEFAULT_DAILY_CAST_LIMIT // 5,  # Threads use more quota
        }
        self.hourly_limits = {
            "send_farcaster_post": DEFAULT_HOURLY_CAST_LIMIT,
            "send_farcaster_reply": DEFAULT_HOURLY_CAST_LIMIT * 2,  # Replies can be more frequent
        }
    
    def can_cast(self, action: str, current_time: float, is_mention: bool = False) -> Tuple[bool, str]:
        """
        Check if an action can be executed given rate limits.
        
        Args:
            action: The action type (e.g., "send_farcaster_post")
            current_time: Current timestamp
            is_mention: Whether this is in response to a mention (bypasses daily limits)
            
        Returns:
            Tuple of (can_execute: bool, reason: str)
        """
        if action not in self.action_history:
            self.action_history[action] = []
        
        # Clean old entries (older than 24 hours)
        day_ago = current_time - 86400  # 24 hours
        hour_ago = current_time - 3600  # 1 hour
        
        self.action_history[action] = [
            timestamp for timestamp in self.action_history[action] 
            if timestamp > day_ago
        ]
        
        # Check daily limits (bypassed for mentions)
        if not is_mention and action in self.daily_limits:
            daily_count = len(self.action_history[action])
            if daily_count >= self.daily_limits[action]:
                return False, f"Daily limit exceeded for {action}: {daily_count}/{self.daily_limits[action]}"
        
        # Check hourly limits (always enforced)
        if action in self.hourly_limits:
            hourly_count = len([
                timestamp for timestamp in self.action_history[action] 
                if timestamp > hour_ago
            ])
            if hourly_count >= self.hourly_limits[action]:
                return False, f"Hourly limit exceeded for {action}: {hourly_count}/{self.hourly_limits[action]}"
        
        return True, "Rate limit check passed"
    
    def can_execute_action(self, action: str, current_time: float, is_mention: bool = False) -> Tuple[bool, str]:
        """Alias for backward compatibility."""
        return self.can_cast(action, current_time, is_mention)
    
    def record_action(self, action: str, timestamp: float) -> None:
        """Record that an action was executed."""
        if action not in self.action_history:
            self.action_history[action] = []
        
        self.action_history[action].append(timestamp)
    
    def get_action_stats(self, action: str, current_time: float) -> Dict[str, int]:
        """Get current usage statistics for an action."""
        if action not in self.action_history:
            return {"daily_count": 0, "hourly_count": 0}
        
        day_ago = current_time - 86400
        hour_ago = current_time - 3600
        
        daily_count = len([
            timestamp for timestamp in self.action_history[action]
            if timestamp > day_ago
        ])
        
        hourly_count = len([
            timestamp for timestamp in self.action_history[action]
            if timestamp > hour_ago
        ])
        
        return {
            "daily_count": daily_count,
            "hourly_count": hourly_count,
            "daily_limit": self.daily_limits.get(action, 0),
            "hourly_limit": self.hourly_limits.get(action, 0)
        }
