"""
Context-Aware Orchestrator

The main orchestrator that coordinates all chatbot components with context management.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..config import settings
from ..core.ai_engine import AIDecisionEngine
from ..core.context import ContextManager
from ..core.world_state import WorldStateManager
from ..integrations.farcaster.observer import FarcasterObserver
from ..integrations.matrix.observer import MatrixObserver
from ..tools.base import ActionContext
from ..tools.core_tools import WaitTool
from ..tools.farcaster_tools import SendFarcasterPostTool, SendFarcasterReplyTool
from ..tools.matrix_tools import SendMatrixMessageTool, SendMatrixReplyTool
from ..tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


@dataclass
class OrchestratorConfig:
    """Configuration for the orchestrator."""

    db_path: str = "chatbot.db"
    observation_interval: float = 2.0  # More responsive default
    max_cycles_per_hour: int = 300  # Allow up to 5 responses per minute
    ai_model: str = "openai/gpt-4o-mini"  # More reliable default model


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
                    settings.NEYNAR_API_KEY, settings.FARCASTER_BOT_SIGNER_UUID
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

                # Rate limiting
                if cycle_start - self.last_cycle_time < self.min_cycle_interval:
                    logger.debug(
                        f"Rate limiting: {cycle_start - self.last_cycle_time:.2f}s < {self.min_cycle_interval:.2f}s"
                    )
                    remaining_time = self.min_cycle_interval - (
                        cycle_start - self.last_cycle_time
                    )
                    if remaining_time > 0:
                        await asyncio.sleep(remaining_time)
                    continue

                # Get current world state
                current_state = self.world_state.to_dict()
                current_hash = self._hash_state(current_state)

                # Check if state has changed
                if current_hash != last_state_hash:
                    logger.info(
                        f"World state changed, processing cycle {self.cycle_count}"
                    )

                    # Get active channels
                    active_channels = self._get_active_channels(current_state)

                    # Process each active channel
                    for channel_id in active_channels:
                        await self._process_channel(channel_id)

                    # Update tracking
                    last_state_hash = current_hash
                    self.cycle_count += 1
                    self.last_cycle_time = cycle_start

                    cycle_duration = time.time() - cycle_start
                    logger.info(
                        f"Cycle {self.cycle_count} completed in {cycle_duration:.2f}s"
                    )

            except Exception as e:
                logger.error(f"Error in event loop cycle {self.cycle_count}: {e}")
                await asyncio.sleep(5)

    def trigger_state_change(self):
        """Trigger immediate processing when world state changes"""
        if self.state_changed_event and not self.state_changed_event.is_set():
            self.state_changed_event.set()
            logger.debug("State change event triggered by external caller")

    async def _process_channel(self, channel_id: str) -> None:
        """Process a single channel for AI decision making."""
        try:
            # Get conversation messages with world state in system prompt
            messages = await self.context_manager.get_conversation_messages(channel_id)

            # Get current world state for AI decision making
            world_state = self.world_state.to_dict()
            cycle_id = f"cycle_{self.cycle_count}_{channel_id}"

            # Make AI decision
            decision = await self.ai_engine.make_decision(world_state, cycle_id)

            if decision and decision.selected_actions:
                # Record AI response in context
                ai_response = {
                    "content": f"Decision: {decision.reasoning}",
                    "timestamp": time.time(),
                    "channel_id": channel_id,
                }
                await self.context_manager.add_assistant_message(
                    channel_id, ai_response
                )

                # Execute selected actions
                for action in decision.selected_actions:
                    await self._execute_action(channel_id, action)

        except Exception as e:
            logger.error(f"Error processing channel {channel_id}: {e}")

    async def _execute_action(self, channel_id: str, action: Any) -> None:
        """Execute a single action using the ToolRegistry."""
        tool_name = action.action_type
        params = action.parameters

        tool = self.tool_registry.get_tool(tool_name)
        if not tool:
            logger.error(f"Attempted to execute unknown tool: {tool_name}")
            # Record this as a failed tool execution in context manager
            await self.context_manager.add_tool_result(
                channel_id,
                tool_name,
                {
                    "action_type": tool_name,
                    "parameters": params,
                    "error": f"Unknown tool: {tool_name}",
                    "status": "failed",
                    "timestamp": time.time(),
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
        result.setdefault("timestamp", time.time())
        result.setdefault("status", "failure" if "error" in result else "success")

        # Record tool result
        tool_result_payload = {
            "action_type": tool_name,
            "parameters": params,
            "status": result["status"],
            "timestamp": result["timestamp"],
        }

        if result["status"] == "success":
            tool_result_payload["result"] = result.get("message", str(result))
            logger.info(
                f"Tool {tool_name} executed successfully: {tool_result_payload['result']}"
            )

            # Handle AI Blindness Fix
            if (
                tool_name
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
                room_id_for_msg = result.get("room_id", channel_id)
                channel_type = "matrix"
                reply_to_id = (
                    result.get("reply_to_event_id")
                    if action_type == "send_matrix_reply"
                    else None
                )
            elif action_type in ["send_farcaster_post", "send_farcaster_reply"]:
                room_id_for_msg = result.get("channel", channel_id)
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

        # Register Matrix tools
        self.tool_registry.register_tool(SendMatrixReplyTool())
        self.tool_registry.register_tool(SendMatrixMessageTool())

        # Register Farcaster tools
        self.tool_registry.register_tool(SendFarcasterPostTool())
        self.tool_registry.register_tool(SendFarcasterReplyTool())

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
