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
from ...tools.s3_service import s3_service
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
            context_manager=self.context_manager,
            s3_service=s3_service
        )
        
        # External observers
        self.matrix_observer: Optional[MatrixObserver] = None
        self.farcaster_observer: Optional[FarcasterObserver] = None
        
        # System state
        self.running = False
        self.cycle_count = 0  # Track processing cycles
        
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

    # Additional API methods for test compatibility and external usage
    async def process_payload(self, payload: Dict[str, Any], active_channels: list) -> None:
        """Process a payload directly using the traditional processor."""
        if hasattr(self.processing_hub, 'traditional_processor') and self.processing_hub.traditional_processor:
            await self.processing_hub.traditional_processor.process_payload(payload, active_channels)
        else:
            logger.warning("No traditional processor available")

    async def _execute_action(self, action) -> None:
        """Execute a single action - wrapper for test compatibility."""
        if hasattr(self.processing_hub, 'traditional_processor') and self.processing_hub.traditional_processor:
            await self.processing_hub.traditional_processor._execute_actions([action])
        else:
            logger.warning("No traditional processor available")

    async def _process_channel(self, channel_id: str) -> None:
        """Process a specific channel - simplified implementation for tests."""
        try:
            # Get conversation messages
            messages = await self.context_manager.get_conversation_messages(channel_id)
            
            # Build world state payload
            payload = self.world_state.to_dict()
            payload['messages'] = messages
            
            # Process using traditional processor
            await self.process_payload(payload, [channel_id])
            
        except Exception as e:
            logger.error(f"Error processing channel {channel_id}: {e}")

    async def add_user_message(self, channel_id: str, message_data: Dict[str, Any]) -> None:
        """Add a user message to the context."""
        await self.context_manager.add_user_message(channel_id, message_data)

    async def get_context_summary(self, channel_id: str) -> Optional[Dict[str, Any]]:
        """Get context summary for a channel."""
        return await self.context_manager.get_context_summary(channel_id)

    async def clear_context(self, channel_id: str) -> None:
        """Clear context for a channel."""
        await self.context_manager.clear_context(channel_id)


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
        """Execute a list of actions with rate limiting and coordination."""
        current_time = time.time()
        
        # Check for image generation + posting coordination opportunities
        coordinated_actions = await self._coordinate_image_actions(actions)
        
        for action in coordinated_actions:
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
                        channel_id = action_params.get('channel_id', 'default')
                        result_dict = result if isinstance(result, dict) else {'result': str(result)}
                        await self.context_manager.add_tool_result(channel_id, action_name, result_dict)
                
            except Exception as e:
                logger.error(f"Error executing action {action_name}: {e}")
                continue

    async def _coordinate_image_actions(self, actions: list) -> list:
        """
        Coordinate image generation with posting actions to enable auto-embedding.
        
        If both image generation and posting actions are present in the same batch,
        execute image generation first and automatically include the image URL in posts.
        """
        # Extract action names and find coordination opportunities
        action_names = []
        action_map = {}
        
        for i, action in enumerate(actions):
            if hasattr(action, 'action_type'):
                action_name = action.action_type
            else:
                action_name = action.get("tool") or action.get("action_type")
            
            if action_name:
                action_names.append(action_name)
                action_map[action_name] = i
        
        # Check for image generation + Farcaster posting coordination
        if "generate_image" in action_names and "send_farcaster_post" in action_names:
            logger.info("Detected image generation + Farcaster post coordination opportunity")
            return await self._coordinate_image_with_farcaster(actions, action_map)
        
        # Check for image generation + Matrix posting coordination
        if "generate_image" in action_names and "send_matrix_message" in action_names:
            logger.info("Detected image generation + Matrix message coordination opportunity")
            return await self._coordinate_image_with_matrix(actions, action_map)
        
        # No coordination needed, return actions as-is
        return actions

    async def _coordinate_image_with_farcaster(self, actions: list, action_map: dict) -> list:
        """Coordinate image generation with Farcaster posting."""
        current_time = time.time()
        coordinated_actions = []
        generated_image_url = None
        
        # First, execute image generation
        image_action_idx = action_map["generate_image"]
        image_action = actions[image_action_idx]
        
        try:
            # Get action parameters
            if hasattr(image_action, 'action_type'):
                action_params = image_action.parameters
            else:
                action_params = image_action.get("parameters", {})
            
            # Check rate limits for image generation
            can_execute, reason = self.rate_limiter.can_execute_action("generate_image", current_time)
            
            if can_execute:
                # Execute image generation
                tool = self.tool_registry.get_tool("generate_image")
                if tool:
                    self.rate_limiter.record_action("generate_image", current_time)
                    
                    if self.action_context:
                        result = await tool.execute(action_params, self.action_context)
                    else:
                        result = await tool.execute(action_params)
                    
                    logger.info(f"Executed coordinated image generation: {result}")
                    
                    # Extract image URL from result
                    if isinstance(result, dict) and result.get("success") and result.get("image_url"):
                        generated_image_url = result["image_url"]
                        logger.info(f"Generated image URL for coordination: {generated_image_url}")
                    
                    # Record in context
                    if self.context_manager:
                        channel_id = action_params.get('channel_id', 'default')
                        result_dict = result if isinstance(result, dict) else {'result': str(result)}
                        await self.context_manager.add_tool_result(channel_id, "generate_image", result_dict)
            else:
                logger.warning(f"Cannot execute image generation for coordination: {reason}")
        
        except Exception as e:
            logger.error(f"Error in coordinated image generation: {e}")
        
        # Now process other actions, modifying Farcaster post if we have an image URL
        for i, action in enumerate(actions):
            if i == image_action_idx:
                # Skip the image action since we already executed it
                continue
            
            # Check if this is the Farcaster post action
            if hasattr(action, 'action_type'):
                action_name = action.action_type
                action_params = action.parameters.copy()  # Make a copy to avoid modifying original
            else:
                action_name = action.get("tool") or action.get("action_type")
                action_params = action.get("parameters", {}).copy()
            
            if action_name == "send_farcaster_post" and generated_image_url:
                # Add the generated image URL to the Farcaster post
                action_params["image_s3_url"] = generated_image_url
                logger.info(f"Enhanced Farcaster post with generated image: {generated_image_url}")
                
                # Create modified action
                if hasattr(action, 'action_type'):
                    # Create new ActionPlan with modified parameters
                    from ..ai_engine import ActionPlan
                    modified_action = ActionPlan(
                        action_type=action.action_type,
                        parameters=action_params,
                        reasoning=action.reasoning,
                        priority=action.priority
                    )
                else:
                    # Create modified dict
                    modified_action = action.copy()
                    modified_action["parameters"] = action_params
                
                coordinated_actions.append(modified_action)
            else:
                # Add action as-is
                coordinated_actions.append(action)
        
        return coordinated_actions

    async def _coordinate_image_with_matrix(self, actions: list, action_map: dict) -> list:
        """
        Coordinate image generation with Matrix messaging.
        
        If both are present, execute image generation first and suggest using
        send_matrix_image instead of send_matrix_message for better embedding.
        """
        current_time = time.time()
        coordinated_actions = []
        generated_image_url = None
        
        # First, execute image generation
        image_action_idx = action_map["generate_image"]
        image_action = actions[image_action_idx]
        
        try:
            # Get action parameters
            if hasattr(image_action, 'action_type'):
                action_params = image_action.parameters
            else:
                action_params = image_action.get("parameters", {})
            
            # Check rate limits for image generation
            can_execute, reason = self.rate_limiter.can_execute_action("generate_image", current_time)
            
            if can_execute:
                # Execute image generation
                tool = self.tool_registry.get_tool("generate_image")
                if tool:
                    self.rate_limiter.record_action("generate_image", current_time)
                    
                    if self.action_context:
                        result = await tool.execute(action_params, self.action_context)
                    else:
                        result = await tool.execute(action_params)
                    
                    logger.info(f"Executed coordinated image generation: {result}")
                    
                    # Extract image URL from result
                    if isinstance(result, dict) and result.get("success") and result.get("image_url"):
                        generated_image_url = result["image_url"]
                        logger.info(f"Generated image URL for Matrix coordination: {generated_image_url}")
                    
                    # Record in context
                    if self.context_manager:
                        channel_id = action_params.get('channel_id', 'default')
                        result_dict = result if isinstance(result, dict) else {'result': str(result)}
                        await self.context_manager.add_tool_result(channel_id, "generate_image", result_dict)
            else:
                logger.warning(f"Cannot execute image generation for coordination: {reason}")
        
        except Exception as e:
            logger.error(f"Error in coordinated image generation: {e}")
        
        # Process other actions, potentially converting Matrix message to Matrix image
        for i, action in enumerate(actions):
            if i == image_action_idx:
                # Skip the image action since we already executed it
                continue
            
            # Check if this is the Matrix message action and we have an image
            if hasattr(action, 'action_type'):
                action_name = action.action_type
                action_params = action.parameters.copy()
            else:
                action_name = action.get("tool") or action.get("action_type")
                action_params = action.get("parameters", {}).copy()
            
            if action_name == "send_matrix_message" and generated_image_url:
                # Convert to send_matrix_image action for better embedding
                action_params["image_url"] = generated_image_url
                # Keep the original message as caption/description
                if "message" in action_params:
                    action_params["caption"] = action_params.pop("message")
                
                logger.info(f"Converting Matrix message to Matrix image with URL: {generated_image_url}")
                
                # Create modified action
                if hasattr(action, 'action_type'):
                    from ..ai_engine import ActionPlan
                    modified_action = ActionPlan(
                        action_type="send_matrix_image",
                        parameters=action_params,
                        reasoning=f"Converted to image post with generated image: {action.reasoning}",
                        priority=action.priority
                    )
                else:
                    modified_action = action.copy()
                    modified_action["tool"] = "send_matrix_image"
                    modified_action["action_type"] = "send_matrix_image"
                    modified_action["parameters"] = action_params
                
                coordinated_actions.append(modified_action)
            else:
                # Add action as-is
                coordinated_actions.append(action)
        
        return coordinated_actions
