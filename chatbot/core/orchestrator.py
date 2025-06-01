"""
Context-Aware Orchestrator

The main orchestrator that coordinates all chatbot components with context management.
"""

import asyncio
import json
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..config import settings
from ..core.ai_engine import AIDecisionEngine
from ..core.context import ContextManager
from ..core.world_state import WorldStateManager
from ..integrations.farcaster import FarcasterObserver
from ..integrations.matrix.observer import MatrixObserver
from ..tools.base import ActionContext
from ..tools.core_tools import WaitTool
from ..tools.describe_image_tool import DescribeImageTool
from ..tools.farcaster_tools import (
    FollowFarcasterUserTool,
    GetCastByUrlTool,
    GetTrendingCastsTool,
    GetUserTimelineTool,
    LikeFarcasterPostTool,
    QuoteFarcasterPostTool,
    SearchCastsTool,
    SendFarcasterDMTool,
    SendFarcasterPostTool,
    SendFarcasterReplyTool,
    UnfollowFarcasterUserTool,
)
from ..tools.matrix_tools import (
    AcceptMatrixInviteTool,
    GetMatrixInvitesTool,
    JoinMatrixRoomTool,
    LeaveMatrixRoomTool,
    ReactToMatrixMessageTool,
    SendMatrixMessageTool,
    SendMatrixReplyTool,
)
from ..tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Enhanced rate limiting configuration."""

    # Global rate limits
    max_cycles_per_hour: int = 300
    min_cycle_interval: float = 12.0  # Minimum seconds between cycles

    # Adaptive rate limiting
    enable_adaptive_limits: bool = True
    burst_window_seconds: int = 300  # 5 minutes
    max_burst_cycles: int = 20
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
            "ReactToMatrixMessageTool": 100,
            # Discovery tools - higher limits as they're read-only
            "GetUserTimelineTool": 150,
            "SearchCastsTool": 100,
            "GetTrendingCastsTool": 80,
            "GetCastByUrlTool": 200,
        }
    )

    # Channel-specific limits (messages per hour)
    channel_limits: Dict[str, int] = field(
        default_factory=lambda: {
            "matrix": 50,  # Per Matrix room per hour
            "farcaster": 30,  # Per Farcaster channel per hour
        }
    )


@dataclass
class OrchestratorConfig:
    """Configuration for the orchestrator."""

    db_path: str = "chatbot.db"
    observation_interval: float = 2.0  # More responsive default
    max_cycles_per_hour: int = 300  # Default value, can be overridden by settings
    ai_model: str = "openai/gpt-4o-mini"  # More reliable default model
    rate_limit_config: RateLimitConfig = field(default_factory=RateLimitConfig)


class EnhancedRateLimiter:
    """Enhanced rate limiting with adaptive behavior and action-specific limits."""

    def __init__(self, config: RateLimitConfig):
        self.config = config

        # Time-based tracking for different rate limit types
        self.cycle_history = deque()  # For tracking processing cycles
        self.action_history: Dict[str, deque] = defaultdict(lambda: deque())
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

        # Check basic rate limit
        base_interval = self.config.min_cycle_interval * self.adaptive_multiplier
        cycles_per_hour = len(self.cycle_history)

        if cycles_per_hour >= self.config.max_cycles_per_hour:
            # Hit hourly limit
            oldest_cycle = self.cycle_history[0] if self.cycle_history else current_time
            wait_time = 3600 - (current_time - oldest_cycle) + 1
            return False, max(wait_time, base_interval)

        # Check for burst conditions
        if self.config.enable_adaptive_limits:
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
        self, action_name: str, current_time: float
    ) -> tuple[bool, str]:
        """
        Check if an action can be executed based on rate limits.
        Returns (can_execute, reason_if_not)
        """
        if action_name not in self.config.action_limits:
            return True, ""

        # Clean old action history
        action_deque = self.action_history[action_name]
        self._clean_deque(action_deque, current_time, 3600)

        limit = self.config.action_limits[action_name]
        if len(action_deque) >= limit:
            oldest_action = action_deque[0] if action_deque else current_time
            wait_time = 3600 - (current_time - oldest_action)
            return (
                False,
                f"Action rate limit exceeded: {len(action_deque)}/{limit} per hour. Wait {wait_time:.0f}s",
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

        return {
            "cycles_per_hour": len(self.cycle_history),
            "max_cycles_per_hour": self.config.max_cycles_per_hour,
            "adaptive_multiplier": self.adaptive_multiplier,
            "in_cooldown": current_time < self.cooldown_until,
            "cooldown_remaining": max(0, self.cooldown_until - current_time),
            "burst_detected": self.burst_detected,
            "action_limits": action_status,
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


class ContextAwareOrchestrator:
    """Main orchestrator for the context-aware chatbot system."""

    def __init__(self, config: Optional[OrchestratorConfig] = None):
        self.config = config or OrchestratorConfig()

        # Initialize core components
        self.world_state = WorldStateManager()
        self.context_manager = ContextManager(self.world_state, self.config.db_path)

        # Tool Registry Initialization
        self.tool_registry = ToolRegistry()

        # AI Engine with dynamic tool support
        self.ai_engine = AIDecisionEngine(
            api_key=settings.OPENROUTER_API_KEY, model=self.config.ai_model
        )

        # Observers (initialized when credentials available)
        self.matrix_observer: Optional[MatrixObserver] = None
        self.farcaster_observer: Optional[FarcasterObserver] = None

        # State tracking
        self.running = False
        self.cycle_count = 0
        self.last_cycle_time = 0
        self.min_cycle_interval = 3600 / self.config.max_cycles_per_hour

        # Enhanced Rate Limiting State
        self.rate_limiter = EnhancedRateLimiter(self.config.rate_limit_config)

        # Action execution tracking (for rate limiting)
        self.action_timestamps: Dict[str, deque] = defaultdict(lambda: deque())
        self.channel_message_timestamps: Dict[str, deque] = defaultdict(lambda: deque())

        # Burst detection and adaptive behavior
        self.cycle_timestamps = deque()
        self.is_in_cooldown = False
        self.cooldown_until = 0.0

        # Event-driven processing
        self.state_changed_event = asyncio.Event()

        # Initialize tools after all components are set up
        self._initialize_tools()

        logger.info("Context-aware orchestrator initialized")

    async def start(self) -> None:
        """Start the orchestrator system."""
        if self.running:
            logger.warning("Orchestrator already running")
            return

        logger.info("Starting context-aware orchestrator...")
        self.running = True

        try:
            await self._initialize_observers()
            await self._main_event_loop()
        except Exception as e:
            logger.error(f"Error in orchestrator: {e}")
            raise
        finally:
            await self.stop()

    async def stop(self) -> None:
        """Stop the orchestrator system."""
        if not self.running:
            return

        logger.info("Stopping context-aware orchestrator...")
        self.running = False

        if self.matrix_observer:
            await self.matrix_observer.stop()

        if self.farcaster_observer:
            await self.farcaster_observer.stop()

        logger.info("Context-aware orchestrator stopped")

    async def _initialize_observers(self) -> None:
        """Initialize available observers based on environment configuration."""
        # Initialize Matrix observer if credentials available
        if settings.MATRIX_USER_ID and settings.MATRIX_PASSWORD:
            try:
                self.matrix_observer = MatrixObserver(self.world_state)
                room_id = settings.MATRIX_ROOM_ID
                self.matrix_observer.add_channel(room_id, "Robot Laboratory")
                await self.matrix_observer.start()
                logger.info("Matrix observer initialized and started")
                logger.info("Matrix observer available for tools.")
            except Exception as e:
                logger.error(f"Failed to initialize Matrix observer: {e}")
                logger.error(
                    f"Matrix configuration - User: {settings.MATRIX_USER_ID}, Server: {getattr(settings, 'MATRIX_SERVER', 'not configured')}"
                )
                logger.info(
                    "Continuing without Matrix integration. Check Matrix credentials and server configuration."
                )

        # Initialize Farcaster observer if credentials available
        if settings.NEYNAR_API_KEY:
            try:
                self.farcaster_observer = FarcasterObserver(
                    settings.NEYNAR_API_KEY,
                    settings.FARCASTER_BOT_SIGNER_UUID,
                    settings.FARCASTER_BOT_FID,
                    world_state_manager=self.world_state,
                )
                await self.farcaster_observer.start()
                self.world_state.update_system_status({"farcaster_connected": True})
                logger.info("Farcaster observer initialized and started")
                logger.info("Farcaster observer available for tools.")
            except Exception as e:
                logger.error(f"Failed to initialize Farcaster observer: {e}")
                logger.error(
                    f"Farcaster configuration - API Key present: {bool(settings.NEYNAR_API_KEY)}, Signer UUID present: {bool(settings.FARCASTER_BOT_SIGNER_UUID)}"
                )
                logger.info(
                    "Continuing without Farcaster integration. Check Neynar API key configuration."
                )

    async def _main_event_loop(self) -> None:
        """Main event loop for processing world state changes."""
        logger.info("Starting main event loop...")
        last_state_hash = None

        while self.running:
            try:
                # Wait for state change event or timeout
                try:
                    await asyncio.wait_for(
                        self.state_changed_event.wait(),
                        timeout=self.config.observation_interval,
                    )
                    self.state_changed_event.clear()
                    logger.info("State change event triggered")
                except asyncio.TimeoutError:
                    # Periodic check even if no events
                    pass

                cycle_start = time.time()

                # Enhanced Rate Limiting
                can_process, wait_time = self.rate_limiter.can_process_cycle(
                    cycle_start
                )

                if not can_process:
                    if wait_time > 0:
                        logger.debug(
                            f"Enhanced rate limiting: waiting {wait_time:.2f}s before next cycle"
                        )
                        await asyncio.sleep(
                            min(wait_time, self.config.observation_interval)
                        )
                    continue

                # Record the cycle for rate limiting
                self.rate_limiter.record_cycle(cycle_start)

                # Get current world state
                current_state = self.world_state.to_dict()
                current_hash = self._hash_state(current_state)

                # Check if state has changed
                if current_hash != last_state_hash:
                    logger.info(
                        f"World state changed, processing cycle {self.cycle_count}"
                    )

                    # Observe external feeds for new content
                    await self._observe_external_feeds()

                    # Get active channels to determine primary focus
                    active_channels = self._get_active_channels(current_state)

                    # Process all channels in a single AI decision cycle
                    # This is more efficient than running AI for each channel separately
                    await self._process_world_state(active_channels)

                    # Update tracking
                    last_state_hash = current_hash
                    self.cycle_count += 1
                    self.last_cycle_time = cycle_start

                    cycle_duration = time.time() - cycle_start
                    logger.info(
                        f"Cycle {self.cycle_count} completed in {cycle_duration:.2f}s"
                    )

                    # Log rate limiting status every 10 cycles for monitoring
                    if self.cycle_count % 10 == 0:
                        self.log_rate_limit_status()

            except Exception as e:
                logger.error(f"Error in event loop cycle {self.cycle_count}: {e}")
                await asyncio.sleep(5)

    def trigger_state_change(self):
        """Trigger immediate processing when world state changes"""
        if self.state_changed_event and not self.state_changed_event.is_set():
            self.state_changed_event.set()
            logger.debug("State change event triggered by external caller")

    async def _process_world_state(self, active_channels: List[str]) -> None:
        """Process the entire world state in a single AI decision cycle."""
        try:
            # Determine primary channel (most recently active)
            primary_channel_id = None
            if active_channels:
                # Sort by recent activity to get most active channel as primary
                channel_activity = []
                for channel_id in active_channels:
                    channel_data = self.world_state.get_channel(channel_id)
                    if channel_data and channel_data.recent_messages:
                        last_msg_time = channel_data.recent_messages[-1].timestamp
                        channel_activity.append((channel_id, last_msg_time))

                if channel_activity:
                    # Primary channel is the one with most recent activity
                    channel_activity.sort(key=lambda x: x[1], reverse=True)
                    primary_channel_id = channel_activity[0][0]

            # Get optimized world state for AI decision making
            world_state_for_ai = self.world_state.get_ai_optimized_payload(
                primary_channel_id=primary_channel_id
            )

            # Log payload size for monitoring
            payload_stats = world_state_for_ai.get("payload_stats", {})
            logger.info(
                f"AI payload stats for cycle {self.cycle_count}: {payload_stats}"
            )

            cycle_id = f"cycle_{self.cycle_count}_unified"

            # Make comprehensive AI decision for entire world state
            decision = await self.ai_engine.make_decision(world_state_for_ai, cycle_id)

            if decision and decision.selected_actions:
                logger.info(
                    f"AI Decision for cycle {self.cycle_count}: {len(decision.selected_actions)} actions selected"
                )

                # Execute all selected actions
                for action in decision.selected_actions:
                    try:
                        await self._execute_action(action)
                    except Exception as e:
                        logger.error(f"Error executing action {action.tool_name}: {e}")
                        # Continue with other actions
            else:
                logger.debug(
                    f"AI Decision for cycle {self.cycle_count}: No actions selected"
                )

        except Exception as e:
            logger.error(
                f"Error in unified world state processing for cycle {self.cycle_count}: {e}"
            )

    async def _process_channel(self, channel_id: str) -> None:
        """
        DEPRECATED: Process a single channel for AI decision making.

        This method is now deprecated in favor of _process_world_state which
        handles all channels in a single comprehensive AI decision cycle.
        Keeping for backward compatibility if needed.
        """
        logger.warning(
            f"_process_channel called for {channel_id} - this method is deprecated, use _process_world_state instead"
        )
        # For backward compatibility, delegate to unified processing
        await self._process_world_state([channel_id])

    async def _execute_action(self, action: Any) -> None:
        """Execute a single action using the ToolRegistry with enhanced rate limiting."""
        tool_name = action.action_type
        params = action.parameters
        current_time = time.time()

        # Enhanced Rate Limiting Check - Action-specific limits
        can_execute, rate_limit_reason = self.rate_limiter.can_execute_action(
            tool_name, current_time
        )
        if not can_execute:
            logger.warning(
                f"Rate limit prevents execution of {tool_name}: {rate_limit_reason}"
            )
            # Record this as a rate-limited action
            channel_id = params.get("channel_id", "unknown")
            await self.context_manager.add_tool_result(
                channel_id,
                tool_name,
                {
                    "action_type": tool_name,
                    "parameters": params,
                    "error": f"Rate limited: {rate_limit_reason}",
                    "status": "rate_limited",
                    "timestamp": current_time,
                },
            )
            return

        # Channel-specific rate limiting for messaging tools
        if tool_name in [
            "send_matrix_message",
            "send_matrix_reply",
            "send_farcaster_post",
            "send_farcaster_reply",
            "send_farcaster_dm",
        ]:
            channel_id = params.get("channel_id", "unknown")
            channel_type = "matrix" if "matrix" in tool_name else "farcaster"

            can_send, channel_limit_reason = self.rate_limiter.can_send_to_channel(
                channel_id, channel_type, current_time
            )

            if not can_send:
                logger.warning(
                    f"Channel rate limit prevents {tool_name} to {channel_id}: {channel_limit_reason}"
                )
                await self.context_manager.add_tool_result(
                    channel_id,
                    tool_name,
                    {
                        "action_type": tool_name,
                        "parameters": params,
                        "error": f"Channel rate limited: {channel_limit_reason}",
                        "status": "channel_rate_limited",
                        "timestamp": current_time,
                    },
                )
                return

        # Record action execution for rate limiting
        self.rate_limiter.record_action(tool_name, current_time)

        # If it's a channel message, record that too
        if tool_name in [
            "send_matrix_message",
            "send_matrix_reply",
            "send_farcaster_post",
            "send_farcaster_reply",
            "send_farcaster_dm",
        ]:
            channel_id = params.get("channel_id", "unknown")
            self.rate_limiter.record_channel_message(channel_id, current_time)

        tool = self.tool_registry.get_tool(tool_name)
        if not tool:
            logger.error(f"Attempted to execute unknown tool: {tool_name}")
            # Extract channel_id from parameters if available for context logging
            channel_id = params.get("channel_id", "unknown")
            # Record this as a failed tool execution in context manager
            await self.context_manager.add_tool_result(
                channel_id,
                tool_name,
                {
                    "action_type": tool_name,
                    "parameters": params,
                    "error": f"Unknown tool: {tool_name}",
                    "status": "failed",
                    "timestamp": current_time,
                },
            )
            return

        logger.info(f"Executing tool '{tool_name}' with parameters: {params}")

        # Create ActionContext to pass to the tool
        action_context = ActionContext(
            matrix_observer=self.matrix_observer,
            farcaster_observer=self.farcaster_observer,
            world_state_manager=self.world_state,
            context_manager=self.context_manager,
        )

        try:
            result = await tool.execute(params, action_context)
        except Exception as e:
            logger.error(
                f"Exception during execution of tool {tool_name}: {e}", exc_info=True
            )
            result = {"status": "failure", "error": str(e)}

        # Ensure result always has a timestamp and status for consistency
        result.setdefault("timestamp", current_time)
        if "status" not in result:
            if "error" in result:
                result["status"] = "failure"
            else:
                result["status"] = "success"

        # Extract channel_id from parameters or result for context logging
        channel_id = params.get("channel_id") or result.get("channel_id", "unknown")

        # Record tool result
        tool_result_payload = {
            "action_type": tool_name,
            "parameters": params,
            "status": result["status"],
            "timestamp": result["timestamp"],
        }

        if result["status"] in ["success", "scheduled"]:
            tool_result_payload["result"] = result.get("message", str(result))
            logger.info(
                f"Tool {tool_name} executed successfully: {tool_result_payload['result']}"
            )

            # Handle AI Blindness Fix - only for successful sends, not scheduled
            if (
                result["status"] == "success"
                and tool_name
                in [
                    "send_matrix_message",
                    "send_matrix_reply",
                    "send_farcaster_post",
                    "send_farcaster_reply",
                ]
                and "sent_content" in result
            ):
                await self._record_bot_sent_message(channel_id, tool_name, result)
        else:
            tool_result_payload["error"] = result.get(
                "error", "Unknown tool execution error"
            )
            logger.error(f"Tool {tool_name} failed: {tool_result_payload['error']}")

        await self.context_manager.add_tool_result(
            channel_id, tool_name, tool_result_payload
        )

    async def _record_bot_sent_message(
        self, channel_id: str, action_type: str, result: Dict[str, Any]
    ) -> None:
        """Record the bot's sent message in both WorldState and ContextManager for AI visibility."""
        try:
            sent_content = result["sent_content"]
            event_id = result.get("event_id") or result.get(
                "cast_hash", f"bot_msg_{time.time()}"
            )
            timestamp = time.time()

            # Determine channel details based on action type
            if action_type in ["send_matrix_message", "send_matrix_reply"]:
                room_id_for_msg = result.get("room_id") or channel_id
                channel_type = "matrix"
                reply_to_id = (
                    result.get("reply_to_event_id")
                    if action_type == "send_matrix_reply"
                    else None
                )
            elif action_type in ["send_farcaster_post", "send_farcaster_reply"]:
                room_id_for_msg = (
                    result.get("channel") or channel_id or "farcaster:home"
                )
                channel_type = "farcaster"
                reply_to_id = (
                    result.get("reply_to")
                    if action_type == "send_farcaster_reply"
                    else None
                )
            else:
                logger.warning(
                    f"Unknown action type for bot message recording: {action_type}"
                )
                return

            # Ensure we always have a valid room_id_for_msg
            if not room_id_for_msg:
                room_id_for_msg = f"{channel_type}:unknown"
                logger.warning(
                    f"No channel ID found for {action_type}, using fallback: {room_id_for_msg}"
                )

            # 1. Add to WorldStateManager
            from chatbot.core.world_state import Message as WorldStateMessage

            bot_world_message = WorldStateMessage(
                id=event_id,
                channel_id=room_id_for_msg,
                channel_type=channel_type,
                sender=settings.MATRIX_USER_ID,  # Bot's user ID
                content=sent_content,
                timestamp=timestamp,
                reply_to=reply_to_id,
            )
            self.world_state.add_message(room_id_for_msg, bot_world_message)
            logger.info(
                f"Added bot's own sent message to WorldState for channel {room_id_for_msg}"
            )

            # 2. Add to ContextManager's assistant messages for AI visibility
            assistant_message_payload = {
                "content": sent_content,
                "event_id": event_id,
                "sender": settings.MATRIX_USER_ID,
                "timestamp": timestamp,
                # type will be implicitly 'assistant' by add_assistant_message
            }
            await self.context_manager.add_assistant_message(
                channel_id, assistant_message_payload
            )
            logger.info(
                f"Added bot's own sent message to ContextManager for channel {channel_id}"
            )

        except Exception as e:
            logger.error(f"Error recording bot sent message: {e}")
            # Don't re-raise - this is supplementary functionality

    async def _observe_external_feeds(self) -> None:
        """
        Observe external feeds (Farcaster) for new content.

        This includes:
        - Popular channel feeds (dev, warpcast, base)
        - Notifications (replies to AI's casts, reactions, etc.)
        - Mentions and replies to the AI bot
        """
        if self.farcaster_observer:
            try:
                # Observe popular Farcaster channels, home feed, and notifications
                new_messages = await self.farcaster_observer.observe_feeds(
                    channels=["dev", "warpcast", "base"],  # Popular channels
                    include_notifications=True,  # Include replies and mentions to AI
                    include_home_feed=True,  # Also include the global (home) feed
                )

                # Add new messages to world state
                for message in new_messages:
                    self.world_state.add_message(message.channel_id, message)

                # Trigger state change if we got new messages
                if new_messages:
                    self.trigger_state_change()
                    logger.info(
                        f"Observed {len(new_messages)} new Farcaster messages (including notifications)"
                    )

            except Exception as e:
                logger.error(f"Error observing Farcaster feeds: {e}")

    def _get_active_channels(self, world_state: Dict[str, Any]) -> List[str]:
        """Get list of channels with recent activity."""
        active_channels = []
        channels = world_state.get("channels", {})
        current_time = time.time()

        for channel_id, channel_data in channels.items():
            # Check for recent activity (last 10 minutes)
            last_activity = channel_data.get("last_checked", 0)
            if current_time - last_activity < 600:
                active_channels.append(channel_id)

        # If no recent activity, include all monitored channels
        if not active_channels and channels:
            active_channels = list(channels.keys())

        return active_channels

    def _hash_state(self, state: Dict[str, Any]) -> str:
        """Generate hash of current state for change detection."""
        import hashlib
        import json

        state_str = json.dumps(state, sort_keys=True, default=str)
        return hashlib.sha256(state_str.encode()).hexdigest()

    def _initialize_tools(self):
        """Register all available tools in the tool registry."""
        # Register core tools
        self.tool_registry.register_tool(WaitTool())
        self.tool_registry.register_tool(DescribeImageTool())

        # Register Matrix tools
        self.tool_registry.register_tool(SendMatrixReplyTool())
        self.tool_registry.register_tool(SendMatrixMessageTool())
        self.tool_registry.register_tool(JoinMatrixRoomTool())
        self.tool_registry.register_tool(LeaveMatrixRoomTool())
        self.tool_registry.register_tool(AcceptMatrixInviteTool())
        self.tool_registry.register_tool(GetMatrixInvitesTool())
        self.tool_registry.register_tool(ReactToMatrixMessageTool())

        # Register Farcaster tools
        self.tool_registry.register_tool(SendFarcasterPostTool())
        self.tool_registry.register_tool(SendFarcasterReplyTool())
        self.tool_registry.register_tool(LikeFarcasterPostTool())
        self.tool_registry.register_tool(QuoteFarcasterPostTool())
        # Follow/unfollow and direct message tools
        self.tool_registry.register_tool(FollowFarcasterUserTool())
        self.tool_registry.register_tool(UnfollowFarcasterUserTool())
        self.tool_registry.register_tool(SendFarcasterDMTool())
        # Content discovery tools
        self.tool_registry.register_tool(GetUserTimelineTool())
        self.tool_registry.register_tool(SearchCastsTool())
        self.tool_registry.register_tool(GetTrendingCastsTool())
        self.tool_registry.register_tool(GetCastByUrlTool())

        # Update AI engine with tool descriptions
        self.ai_engine.update_system_prompt_with_tools(self.tool_registry)

        logger.info(
            f"Initialized {len(self.tool_registry.get_all_tools())} tools: {', '.join(self.tool_registry.get_tool_names())}"
        )

    # Public API methods
    async def add_user_message(self, channel_id: str, message: Dict[str, Any]) -> None:
        """Add a user message to the context."""
        await self.context_manager.add_user_message(channel_id, message)

    async def get_context_summary(self, channel_id: str) -> Dict[str, Any]:
        """Get context summary for a channel."""
        return await self.context_manager.get_context_summary(channel_id)

    async def clear_context(self, channel_id: str) -> None:
        """Clear context for a channel."""
        await self.context_manager.clear_context(channel_id)

    async def export_training_data(self, output_path: str) -> str:
        """Export state changes for training."""
        return await self.context_manager.export_state_changes_for_training(output_path)

    def get_rate_limit_status(self) -> Dict[str, Any]:
        """Get comprehensive rate limiting status for monitoring."""
        return self.rate_limiter.get_rate_limit_status(time.time())

    def log_rate_limit_status(self):
        """Log current rate limiting status for debugging."""
        status = self.get_rate_limit_status()
        logger.info(
            f"Rate Limit Status: Cycles {status['cycles_per_hour']}/{status['max_cycles_per_hour']}, "
            f"Adaptive multiplier: {status['adaptive_multiplier']:.2f}, "
            f"In cooldown: {status['in_cooldown']}"
        )

        # Log action limits that are near capacity
        for action_name, action_status in status["action_limits"].items():
            usage_percent = (action_status["used"] / action_status["limit"]) * 100
            if usage_percent > 70:  # Log if over 70% capacity
                logger.warning(
                    f"Action {action_name} near limit: {action_status['used']}/{action_status['limit']} ({usage_percent:.1f}%)"
                )
