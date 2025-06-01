"""
Main Orchestrator

Lean coordinator that manages observers, components, and overall system lifecycle.
Acts as the primary entry point and coordinates between different subsystems.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from ...config import settings
from ...core.ai_engine import AIDecisionEngine
from ...core.context import ContextManager
from ...integrations.farcaster import FarcasterObserver
from ...integrations.matrix.observer import MatrixObserver
from ...tools.registry import ToolRegistry
from ..world_state.manager import WorldStateManager
from ..world_state.payload_builder import PayloadBuilder
from .processing_hub import ProcessingHub, ProcessingConfig
from .rate_limiter import RateLimiter, RateLimitConfig

logger = logging.getLogger(__name__)


@dataclass
class OrchestratorConfig:
    """Configuration for the main orchestrator."""

    # Database and storage
    db_path: str = "chatbot.db"
    
    # Processing configuration
    processing_config: ProcessingConfig = field(default_factory=ProcessingConfig)
    rate_limit_config: RateLimitConfig = field(default_factory=RateLimitConfig)
    
    # AI Model settings
    ai_model: str = "openai/gpt-4o-mini"


class MainOrchestrator:
    """
    Main orchestrator that coordinates all chatbot components.
    
    This is the primary entry point that:
    1. Manages system lifecycle (start/stop)
    2. Initializes and coordinates all components
    3. Manages external observers (Matrix, Farcaster)
    4. Provides unified system status and control
    """
    
    def __init__(self, config: Optional[OrchestratorConfig] = None):
        self.config = config or OrchestratorConfig()
        
        # Core components
        self.world_state = WorldStateManager()
        self.payload_builder = PayloadBuilder()
        self.rate_limiter = RateLimiter(self.config.rate_limit_config)
        self.context_manager = ContextManager(self.world_state, self.config.db_path)
        
        # Processing hub
        self.processing_hub = ProcessingHub(
            world_state_manager=self.world_state,
            payload_builder=self.payload_builder,
            rate_limiter=self.rate_limiter,
            config=self.config.processing_config
        )
        
        # Tool Registry and AI Engine
        self.tool_registry = ToolRegistry()
        self.ai_engine = AIDecisionEngine(
            api_key=settings.OPENROUTER_API_KEY,
            model=self.config.ai_model
        )
        
        # Create action context for tool execution
        from ...tools.base import ActionContext
        self.action_context = ActionContext(
            world_state_manager=self.world_state,
            context_manager=self.context_manager
        )
        
        # External observers
        self.matrix_observer: Optional[MatrixObserver] = None
        self.farcaster_observer: Optional[FarcasterObserver] = None
        
        # System state
        self.running = False
        
        # Initialize tool registry and register tools
        self._register_all_tools()

    def _register_all_tools(self):
        """Register all available tools with the tool registry."""
        from ...tools.core_tools import WaitTool
        from ...tools.describe_image_tool import DescribeImageTool
        from ...tools.farcaster_tools import (
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
        from ...tools.matrix_tools import (
            AcceptMatrixInviteTool,
            GetMatrixInvitesTool,
            JoinMatrixRoomTool,
            LeaveMatrixRoomTool,
            ReactToMatrixMessageTool,
            SendMatrixImageTool,
            SendMatrixMessageTool,
            SendMatrixReplyTool,
        )
        from ...tools.media_generation_tools import GenerateImageTool, GenerateVideoTool
        from ...tools.permaweb_tools import StorePermanentMemoryTool
        
        # Core tools
        self.tool_registry.register_tool(WaitTool())
        self.tool_registry.register_tool(DescribeImageTool())
        
        # Matrix tools
        self.tool_registry.register_tool(SendMatrixMessageTool())
        self.tool_registry.register_tool(SendMatrixReplyTool())
        self.tool_registry.register_tool(SendMatrixImageTool())
        self.tool_registry.register_tool(ReactToMatrixMessageTool())
        self.tool_registry.register_tool(JoinMatrixRoomTool())
        self.tool_registry.register_tool(LeaveMatrixRoomTool())
        self.tool_registry.register_tool(AcceptMatrixInviteTool())
        self.tool_registry.register_tool(GetMatrixInvitesTool())
        
        # Farcaster tools
        self.tool_registry.register_tool(SendFarcasterPostTool())
        self.tool_registry.register_tool(SendFarcasterReplyTool())
        self.tool_registry.register_tool(SendFarcasterDMTool())
        self.tool_registry.register_tool(LikeFarcasterPostTool())
        self.tool_registry.register_tool(QuoteFarcasterPostTool())
        self.tool_registry.register_tool(FollowFarcasterUserTool())
        self.tool_registry.register_tool(UnfollowFarcasterUserTool())
        self.tool_registry.register_tool(GetUserTimelineTool())
        self.tool_registry.register_tool(SearchCastsTool())
        self.tool_registry.register_tool(GetTrendingCastsTool())
        self.tool_registry.register_tool(GetCastByUrlTool())
        
        # Media generation tools
        self.tool_registry.register_tool(GenerateImageTool())
        self.tool_registry.register_tool(GenerateVideoTool())
        
        # Permaweb tools
        self.tool_registry.register_tool(StorePermanentMemoryTool())

    async def start(self) -> None:
        """Start the entire orchestrator system."""
        if self.running:
            logger.warning("Main orchestrator already running")
            return

        logger.info("Starting main orchestrator system...")
        self.running = True

        try:
            # Initialize external observers
            await self._initialize_observers()
            
            # Set up processing hub with traditional processor
            self._setup_processing_components()
            
            # Start the processing loop
            await self.processing_hub.start_processing_loop()
            
        except Exception as e:
            logger.error(f"Error starting main orchestrator: {e}")
            raise
        finally:
            await self.stop()

    async def stop(self) -> None:
        """Stop the entire orchestrator system."""
        if not self.running:
            return

        logger.info("Stopping main orchestrator system...")
        self.running = False

        # Stop processing hub
        self.processing_hub.stop_processing_loop()
        
        # Stop external observers
        if self.matrix_observer:
            await self.matrix_observer.stop()

        if self.farcaster_observer:
            await self.farcaster_observer.stop()

        logger.info("Main orchestrator system stopped")

    def _setup_processing_components(self):
        """Set up processing components for the processing hub."""
        # Create traditional processor wrapper
        traditional_processor = TraditionalProcessor(
            ai_engine=self.ai_engine,
            tool_registry=self.tool_registry,
            rate_limiter=self.rate_limiter,
            context_manager=self.context_manager,
            action_context=self.action_context
        )
        
        self.processing_hub.set_traditional_processor(traditional_processor)
        
        # Note: Node processor would be set up here when implementing
        # the JSON Observer integration

    async def _initialize_observers(self) -> None:
        """Initialize available observers based on environment configuration."""
        # Initialize Matrix observer if credentials available
        if settings.MATRIX_USER_ID and settings.MATRIX_PASSWORD:
            try:
                self.matrix_observer = MatrixObserver(self.world_state)
                room_id = settings.MATRIX_ROOM_ID
                self.matrix_observer.add_channel(room_id, "Robot Laboratory")
                await self.matrix_observer.start()
                
                # Connect state change notifications
                self.matrix_observer.on_state_change = self.processing_hub.trigger_state_change
                
                logger.info("Matrix observer initialized and started")
            except Exception as e:
                logger.error(f"Failed to initialize Matrix observer: {e}")
                logger.info("Continuing without Matrix integration")

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
                
                # Connect state change notifications
                self.farcaster_observer.on_state_change = self.processing_hub.trigger_state_change
                
                self.world_state.update_system_status({"farcaster_connected": True})
                logger.info("Farcaster observer initialized and started")
            except Exception as e:
                logger.error(f"Failed to initialize Farcaster observer: {e}")
                logger.info("Continuing without Farcaster integration")
        
        # Update action context with initialized observers
        self.action_context.matrix_observer = self.matrix_observer
        self.action_context.farcaster_observer = self.farcaster_observer

    def trigger_state_change(self):
        """Trigger immediate processing when world state changes."""
        self.processing_hub.trigger_state_change()

    def get_system_status(self) -> Dict[str, Any]:
        """Get comprehensive system status."""
        return {
            "running": self.running,
            "processing_hub": self.processing_hub.get_processing_status(),
            "rate_limits": self.processing_hub.get_rate_limit_status(),
            "world_state_metrics": self.world_state.get_state_metrics(),
            "observers": {
                "matrix_connected": self.matrix_observer is not None,
                "farcaster_connected": self.farcaster_observer is not None,
            },
            "tools_registered": len(self.tool_registry.get_all_tools()),
        }

    async def force_processing_mode(self, mode: str) -> bool:
        """Force a specific processing mode."""
        return await self.processing_hub.force_processing_mode(mode)

    def reset_processing_mode(self):
        """Reset to automatic processing mode selection."""
        self.processing_hub.reset_processing_mode()


class TraditionalProcessor:
    """Wrapper for traditional AI processing approach."""
    
    def __init__(self, ai_engine, tool_registry, rate_limiter, context_manager, action_context=None):
        self.ai_engine = ai_engine
        self.tool_registry = tool_registry
        self.rate_limiter = rate_limiter
        self.context_manager = context_manager
        self.action_context = action_context

    async def process_payload(self, payload: Dict[str, Any], active_channels: list) -> None:
        """Process a traditional full payload."""
        try:
            # Update AI engine with current tool registry
            self.ai_engine.update_system_prompt_with_tools(self.tool_registry)
            
            # Make AI decision
            decision = await self.ai_engine.make_decision(
                world_state=payload,
                cycle_id="traditional_cycle"
            )
            
            # Execute actions from decision
            if decision and decision.selected_actions:
                await self._execute_actions(decision.selected_actions)
                
        except Exception as e:
            logger.error(f"Error in traditional processing: {e}")
            raise

    async def _execute_actions(self, actions: list) -> None:
        """Execute a list of actions with rate limiting."""
        current_time = time.time()
        
        for action in actions:
            try:
                # Handle both ActionPlan objects and dict formats
                if hasattr(action, 'action_type'):
                    # ActionPlan object
                    action_name = action.action_type
                    action_params = action.parameters
                else:
                    # Dict format (legacy support)
                    action_name = action.get("tool") or action.get("action_type")
                    action_params = action.get("parameters", {})
                
                if not action_name:
                    continue
                
                # Check rate limits
                can_execute, reason = self.rate_limiter.can_execute_action(
                    action_name, current_time
                )
                
                if not can_execute:
                    logger.warning(f"Skipping action {action_name}: {reason}")
                    continue
                
                # Get tool and execute
                tool = self.tool_registry.get_tool(action_name)
                if tool:
                    # Record action for rate limiting
                    self.rate_limiter.record_action(action_name, current_time)
                    
                    # Execute action with context
                    if self.action_context:
                        result = await tool.execute(action_params, self.action_context)
                    else:
                        # Fallback for tools that don't need context
                        result = await tool.execute(action_params)
                    logger.info(f"Executed action {action_name}: {result}")
                    
                    # Record in context
                    if self.context_manager:
                        self.context_manager.record_action(action_name, action, result)
                
            except Exception as e:
                logger.error(f"Error executing action {action_name}: {e}")
                continue
