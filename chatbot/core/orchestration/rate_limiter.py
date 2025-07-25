"""
Rate Limiting System

Provides advanced rate limiting capabilities with adaptive behavior,
action-specific limits, and channel-based throttling.
"""

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class RateLimitConfig:
    """Enhanced rate limiting configuration."""

    # Global rate limits
    max_cycles_per_hour: int = 300  # Restored from overly conservative 60 to proper 300
    min_cycle_interval: float = 12.0  # Restored from 60.0 to proper 12.0 (Minimum seconds between cycles)

    # Adaptive rate limiting
    enable_adaptive_limits: bool = True
    burst_window_seconds: int = 300  # 5 minutes
    max_burst_cycles: int = 20  # Restored from overly conservative 5 to proper 20 (cycles in burst window)
    cooldown_multiplier: float = 1.5  # How much to slow down after burst

    # Action-specific limits (per hour)
    action_limits: Dict[str, int] = field(
        default_factory=lambda: {
            "SendMatrixMessageTool": 100,
            "SendMatrixReplyTool": 150,
            "SendFarcasterPostTool": 50,
            "SendFarcasterReplyTool": 100,
            "SendFarcasterDMTool": 30,
            "LikeFarcasterPostTool": 200,
            "FollowFarcasterUserTool": 20,
            "UnfollowFarcasterUserTool": 20,
            "QuoteFarcasterPostTool": 30,
            "DeleteFarcasterPostTool": 10,  # Conservative limit for deletions
            "DeleteFarcasterReactionTool": 50,  # Higher limit for reaction deletions
            "ReactToMatrixMessageTool": 100,
            # Discovery tools - higher limits as they're read-only
            "GetUserTimelineTool": 150,
            "SearchCastsTool": 100,
            "GetTrendingCastsTool": 80,
            "GetCastByUrlTool": 200,
        }
    )

    # Daily limits for specific actions (per 24 hours)
    daily_limits: Dict[str, int] = field(
        default_factory=lambda: {
            "SendFarcasterReplyTool": 3,  # Only 3 replies per day for general conversations
        }
    )

    # Channel-specific limits (messages per hour)
    channel_limits: Dict[str, int] = field(
        default_factory=lambda: {
            "matrix": 50,  # Per Matrix room per hour
            "farcaster": 30,  # Per Farcaster channel per hour
        }
    )


class RateLimiter:
    """Enhanced rate limiting with adaptive behavior and action-specific limits."""

    def __init__(self, config: RateLimitConfig, world_state_manager=None):
        self.config = config
        self.world_state_manager = world_state_manager

        # Time-based tracking for different rate limit types
        self.cycle_history = deque()  # For tracking processing cycles
        self.action_history: Dict[str, deque] = defaultdict(lambda: deque())
        # Note: daily_action_history is now handled by world state for persistence
        self.channel_history: Dict[str, deque] = defaultdict(lambda: deque())

        # State for adaptive behavior
        self.burst_detected = False
        self.cooldown_until = 0.0
        self.adaptive_multiplier = 1.0

    def can_process_cycle(self, current_time: float) -> tuple[bool, float]:
        """
        Check if a new processing cycle can start.
        Returns (can_process, wait_time_seconds)
        """
        # Clean old cycle history
        self._clean_deque(self.cycle_history, current_time, 3600)  # 1 hour window

        # Check if in cooldown
        if current_time < self.cooldown_until:
            return False, self.cooldown_until - current_time

        # Check minimum cycle interval - CRITICAL: This enforces the 60-second minimum
        if self.cycle_history:
            last_cycle_time = self.cycle_history[-1]  # Most recent cycle
            time_since_last = current_time - last_cycle_time
            base_interval = self.config.min_cycle_interval * self.adaptive_multiplier
            
            if time_since_last < base_interval:
                wait_time = base_interval - time_since_last
                return False, wait_time

        # Check hourly rate limit
        cycles_per_hour = len(self.cycle_history)
        if cycles_per_hour >= self.config.max_cycles_per_hour:
            # Hit hourly limit
            oldest_cycle = self.cycle_history[0] if self.cycle_history else current_time
            wait_time = 3600 - (current_time - oldest_cycle) + 1
            return False, wait_time

        # Check for burst conditions
        if self.config.enable_adaptive_limits:
            base_interval = self.config.min_cycle_interval * self.adaptive_multiplier
            burst_cycles = len(
                [
                    t
                    for t in self.cycle_history
                    if current_time - t <= self.config.burst_window_seconds
                ]
            )

            if burst_cycles >= self.config.max_burst_cycles:
                # Entering burst cooldown
                self.burst_detected = True
                self.cooldown_until = current_time + (
                    base_interval * self.config.cooldown_multiplier
                )
                self.adaptive_multiplier = min(self.adaptive_multiplier * 1.2, 3.0)
                return False, self.cooldown_until - current_time

        return True, 0.0

    def can_execute_action(
        self, action_name: str, current_time: float, is_mention: bool = False
    ) -> tuple[bool, str]:
        """
        Check if an action can be executed based on rate limits.
        
        Args:
            action_name: Name of the action to check
            current_time: Current timestamp
            is_mention: If True, daily limits are bypassed for mentions
            
        Returns:
            (can_execute, reason_if_not)
        """
        if action_name not in self.config.action_limits:
            return True, ""

        # Clean old action history
        action_deque = self.action_history[action_name]
        self._clean_deque(action_deque, current_time, 3600)

        # Check hourly limit
        limit = self.config.action_limits[action_name]
        if len(action_deque) >= limit:
            oldest_action = action_deque[0] if action_deque else current_time
            wait_time = 3600 - (current_time - oldest_action)
            return (
                False,
                f"Action rate limit exceeded: {len(action_deque)}/{limit} per hour. Wait {wait_time:.0f}s",
            )

        # Check daily limit (only if not a mention and daily limit exists)
        if not is_mention and action_name in self.config.daily_limits:
            if self.world_state_manager and hasattr(self.world_state_manager, 'state'):
                # Use persistent world state for daily tracking
                if action_name not in self.world_state_manager.state.daily_rate_limits:
                    from ..world_state.structures import DailyRateLimit
                    self.world_state_manager.state.daily_rate_limits[action_name] = DailyRateLimit(
                        action_name=action_name,
                        daily_limit=self.config.daily_limits[action_name]
                    )
                
                daily_limiter = self.world_state_manager.state.daily_rate_limits[action_name]
                can_execute, reason = daily_limiter.can_execute(current_time, is_mention)
                if not can_execute:
                    return False, reason
            else:
                # Fallback: use basic daily limit check without persistence
                daily_limit = self.config.daily_limits[action_name]
                return (
                    False,
                    f"Daily limit not enforced: world state not available. Limit would be {daily_limit} per day.",
                )

        return True, ""

    def can_send_to_channel(
        self, channel_id: str, channel_type: str, current_time: float
    ) -> tuple[bool, str]:
        """
        Check if a message can be sent to a specific channel.
        Returns (can_send, reason_if_not)
        """
        if channel_type not in self.config.channel_limits:
            return True, ""

        # Clean old channel history
        channel_deque = self.channel_history[channel_id]
        self._clean_deque(channel_deque, current_time, 3600)

        limit = self.config.channel_limits[channel_type]
        if len(channel_deque) >= limit:
            oldest_message = channel_deque[0] if channel_deque else current_time
            wait_time = 3600 - (current_time - oldest_message)
            return (
                False,
                f"Channel rate limit exceeded: {len(channel_deque)}/{limit} per hour. Wait {wait_time:.0f}s",
            )

        return True, ""

    def record_cycle(self, current_time: float):
        """Record a processing cycle."""
        self.cycle_history.append(current_time)

        # Gradually reduce adaptive multiplier if no recent bursts
        if not self.burst_detected and current_time > self.cooldown_until:
            self.adaptive_multiplier = max(self.adaptive_multiplier * 0.95, 1.0)

    def record_action(self, action_name: str, current_time: float):
        """Record an action execution."""
        self.action_history[action_name].append(current_time)
        
        # Also record for daily tracking if action has daily limits and world state is available
        if action_name in self.config.daily_limits and self.world_state_manager and hasattr(self.world_state_manager, 'state'):
            if action_name not in self.world_state_manager.state.daily_rate_limits:
                from ..world_state.structures import DailyRateLimit
                self.world_state_manager.state.daily_rate_limits[action_name] = DailyRateLimit(
                    action_name=action_name,
                    daily_limit=self.config.daily_limits[action_name]
                )
            
            daily_limiter = self.world_state_manager.state.daily_rate_limits[action_name]
            daily_limiter.record_execution(current_time)

    def record_channel_message(self, channel_id: str, current_time: float):
        """Record a message sent to a channel."""
        self.channel_history[channel_id].append(current_time)

    def get_rate_limit_status(self, current_time: float) -> Dict[str, Any]:
        """Get current rate limiting status for monitoring."""
        # Clean all histories
        self._clean_deque(self.cycle_history, current_time, 3600)

        action_status = {}
        for action_name, limit in self.config.action_limits.items():
            action_deque = self.action_history[action_name]
            self._clean_deque(action_deque, current_time, 3600)
            action_status[action_name] = {
                "used": len(action_deque),
                "limit": limit,
                "remaining": max(0, limit - len(action_deque)),
            }

        # Add daily limits status
        daily_action_status = {}
        for action_name, daily_limit in self.config.daily_limits.items():
            if self.world_state_manager and hasattr(self.world_state_manager, 'state'):
                if action_name not in self.world_state_manager.state.daily_rate_limits:
                    from ..world_state.structures import DailyRateLimit
                    self.world_state_manager.state.daily_rate_limits[action_name] = DailyRateLimit(
                        action_name=action_name,
                        daily_limit=daily_limit
                    )
                
                daily_limiter = self.world_state_manager.state.daily_rate_limits[action_name]
                daily_limiter.clean_old_entries(current_time)
                used_count = len(daily_limiter.timestamps)
                daily_action_status[action_name] = {
                    "used": used_count,
                    "limit": daily_limit,
                    "remaining": max(0, daily_limit - used_count),
                }
            else:
                # World state not available
                daily_action_status[action_name] = {
                    "used": 0,
                    "limit": daily_limit,
                    "remaining": daily_limit,
                    "note": "World state not available - tracking not persistent"
                }

        return {
            "cycles_per_hour": len(self.cycle_history),
            "max_cycles_per_hour": self.config.max_cycles_per_hour,
            "adaptive_multiplier": self.adaptive_multiplier,
            "in_cooldown": current_time < self.cooldown_until,
            "cooldown_remaining": max(0, self.cooldown_until - current_time),
            "burst_detected": self.burst_detected,
            "action_limits": action_status,
            "daily_action_limits": daily_action_status,
            "channel_message_counts": {
                ch_id: len(self.channel_history[ch_id])
                for ch_id in self.channel_history
            },
        }

    def _clean_deque(self, deque_obj: deque, current_time: float, window_seconds: int):
        """Remove entries older than the specified window."""
        cutoff_time = current_time - window_seconds
        while deque_obj and deque_obj[0] < cutoff_time:
            deque_obj.popleft()
