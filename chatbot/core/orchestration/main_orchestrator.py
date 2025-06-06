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
from ...integrations.arweave_uploader_client import ArweaveUploaderClient
from ...integrations.farcaster import FarcasterObserver
from ...integrations.matrix.observer import MatrixObserver
from ...integrations.base_nft_service import BaseNFTService
from ...integrations.eligibility_service import UserEligibilityService
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
        
        # Initialize Arweave client
        self.arweave_client = None
        if settings.ARWEAVE_UPLOADER_API_ENDPOINT and settings.ARWEAVE_UPLOADER_API_KEY:
            self.arweave_client = ArweaveUploaderClient(
                api_endpoint=settings.ARWEAVE_UPLOADER_API_ENDPOINT,
                api_key=settings.ARWEAVE_UPLOADER_API_KEY,
                gateway_url=settings.ARWEAVE_GATEWAY_URL,
            )
            logger.info("Arweave client initialized.")
        
        # Create action context for tool execution
        from ...tools.base import ActionContext
        from ...tools.arweave_service import ArweaveService
        
        # Initialize arweave service with our client
        arweave_service_instance = ArweaveService(arweave_client=self.arweave_client)
        
        self.action_context = ActionContext(
            world_state_manager=self.world_state,
            context_manager=self.context_manager,
            arweave_client=self.arweave_client,
            arweave_service=arweave_service_instance
        )
        
        # External observers
        self.matrix_observer: Optional[MatrixObserver] = None
        self.farcaster_observer: Optional[FarcasterObserver] = None
        
        # NFT and eligibility services
        self.base_nft_service: Optional[BaseNFTService] = None
        self.eligibility_service: Optional[UserEligibilityService] = None
        
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
            GetUserTimelineTool,
            LikeFarcasterPostTool,
            QuoteFarcasterPostTool,
            SendFarcasterDMTool,
            SendFarcasterPostTool,
            SendFarcasterReplyTool,
            UnfollowFarcasterUserTool,
            DeleteFarcasterPostTool,
            DeleteFarcasterReactionTool,
            CollectWorldStateTool,
            GetTrendingCastsTool,
            SearchCastsTool,
            GetCastByUrlTool,
        )
        from ...tools.frame_tools import (
            CreateTransactionFrameTool,
            CreatePollFrameTool,
            CreateCustomFrameTool,
            SearchFramesTool,
            GetFrameCatalogTool,
            CreateMintFrameTool,
            CreateAirdropClaimFrameTool,
        )
        from ...tools.matrix_tools import (
            AcceptMatrixInviteTool,
            IgnoreMatrixInviteTool,
            JoinMatrixRoomTool,
            LeaveMatrixRoomTool,
            ReactToMatrixMessageTool,
            SendMatrixImageTool,
            SendMatrixMessageTool,
            SendMatrixReplyTool,
            SendMatrixVideoTool,
        )
        from ...tools.media_generation_tools import GenerateImageTool, GenerateVideoTool
        from ...tools.permaweb_tools import StorePermanentMemoryTool
        from ...tools.web_tools import WebSearchTool
        from ...tools.research_tools import UpdateResearchTool, QueryResearchTool
        from ...tools.developer_tools import (
            GetCodebaseStructureTool, UpdateProjectPlanTool, SummarizeChannelTool,
            SetupDevelopmentWorkspaceTool, ExploreCodebaseTool,
            AnalyzeAndProposeChangeTool, ImplementCodeChangesTool,
            CreatePullRequestTool, ACEOrchestratorTool
        )
        
        # Core tools
        self.tool_registry.register_tool(WaitTool())
        self.tool_registry.register_tool(DescribeImageTool())
        
        # Web search and research tools
        self.tool_registry.register_tool(WebSearchTool())
        self.tool_registry.register_tool(UpdateResearchTool())
        self.tool_registry.register_tool(QueryResearchTool())
        
        # Matrix tools
        self.tool_registry.register_tool(SendMatrixMessageTool())
        self.tool_registry.register_tool(SendMatrixReplyTool())
        self.tool_registry.register_tool(SendMatrixImageTool())
        self.tool_registry.register_tool(SendMatrixVideoTool())
        self.tool_registry.register_tool(ReactToMatrixMessageTool())
        self.tool_registry.register_tool(JoinMatrixRoomTool())
        self.tool_registry.register_tool(LeaveMatrixRoomTool())
        self.tool_registry.register_tool(AcceptMatrixInviteTool())
        self.tool_registry.register_tool(IgnoreMatrixInviteTool())
        
        # Farcaster tools
        self.tool_registry.register_tool(SendFarcasterPostTool())
        self.tool_registry.register_tool(SendFarcasterReplyTool())
        self.tool_registry.register_tool(SendFarcasterDMTool())
        self.tool_registry.register_tool(LikeFarcasterPostTool())
        self.tool_registry.register_tool(QuoteFarcasterPostTool())
        self.tool_registry.register_tool(FollowFarcasterUserTool())
        self.tool_registry.register_tool(UnfollowFarcasterUserTool())
        self.tool_registry.register_tool(DeleteFarcasterPostTool())
        self.tool_registry.register_tool(DeleteFarcasterReactionTool())
        self.tool_registry.register_tool(GetUserTimelineTool())
        self.tool_registry.register_tool(SearchCastsTool())
        self.tool_registry.register_tool(GetTrendingCastsTool())
        self.tool_registry.register_tool(GetCastByUrlTool())
        self.tool_registry.register_tool(CollectWorldStateTool())
        
        # Farcaster Frame tools
        self.tool_registry.register_tool(CreateTransactionFrameTool())
        self.tool_registry.register_tool(CreatePollFrameTool())
        self.tool_registry.register_tool(CreateCustomFrameTool())
        self.tool_registry.register_tool(SearchFramesTool())
        self.tool_registry.register_tool(GetFrameCatalogTool())
        
        # NFT Frame tools
        self.tool_registry.register_tool(CreateMintFrameTool())
        self.tool_registry.register_tool(CreateAirdropClaimFrameTool())
        
        # Media generation tools
        self.tool_registry.register_tool(GenerateImageTool())
        self.tool_registry.register_tool(GenerateVideoTool())
        
        # Permaweb tools
        self.tool_registry.register_tool(StorePermanentMemoryTool())
        # Developer tools (ACE Phase 1, 2 & 3)
        self.tool_registry.register_tool(GetCodebaseStructureTool())
        self.tool_registry.register_tool(SetupDevelopmentWorkspaceTool())
        self.tool_registry.register_tool(ExploreCodebaseTool())
        self.tool_registry.register_tool(AnalyzeAndProposeChangeTool())
        self.tool_registry.register_tool(ImplementCodeChangesTool())
        self.tool_registry.register_tool(CreatePullRequestTool())
        self.tool_registry.register_tool(ACEOrchestratorTool())
        self.tool_registry.register_tool(UpdateProjectPlanTool())
        self.tool_registry.register_tool(SummarizeChannelTool())

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
            
            # Initialize NFT and blockchain services
            await self._initialize_nft_services()
            
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
        
        # Stop NFT and eligibility services
        if self.eligibility_service:
            await self.eligibility_service.stop()
        
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

    async def _initialize_nft_services(self) -> None:
        """Initialize NFT and blockchain services if credentials are available."""
        try:
            # Initialize Base NFT service
            if (settings.BASE_RPC_URL and 
                settings.NFT_DEV_WALLET_PRIVATE_KEY and 
                settings.NFT_COLLECTION_ADDRESS_BASE):
                
                self.base_nft_service = BaseNFTService()
                
                # Initialize the service
                if await self.base_nft_service.initialize():
                    logger.info("Base NFT service initialized successfully")
                    
                    # Initialize eligibility service if we have Farcaster observer
                    if (settings.ECOSYSTEM_TOKEN_CONTRACT_ADDRESS and 
                        hasattr(self, 'farcaster_observer') and 
                        self.farcaster_observer and 
                        hasattr(self.farcaster_observer, 'neynar_api_client')):
                        
                        self.eligibility_service = UserEligibilityService(
                            neynar_api_client=self.farcaster_observer.neynar_api_client,
                            base_nft_service=self.base_nft_service,
                            world_state_manager=self.world_state
                        )
                        await self.eligibility_service.start()
                        logger.info("User eligibility service started")
                        
                        # Update action context with NFT services
                        self.action_context.base_nft_service = self.base_nft_service
                        self.action_context.eligibility_service = self.eligibility_service
                    else:
                        logger.info("Eligibility service not started - missing dependencies")
                        
                else:
                    logger.warning("Failed to initialize Base NFT service")
                    self.base_nft_service = None
                
            else:
                logger.info("NFT service configuration incomplete - NFT features disabled")
                
        except Exception as e:
            logger.error(f"Failed to initialize NFT services: {e}")
            logger.info("Continuing without NFT integration")

    async def _initialize_observers(self) -> None:
        """Initialize available observers based on environment configuration."""
        # Initialize Matrix observer if credentials available
        if settings.MATRIX_USER_ID and settings.MATRIX_PASSWORD:
            try:
                self.matrix_observer = MatrixObserver(self.world_state, self.arweave_client)
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
        
        # Configure critical node pinning based on active integrations
        self._configure_critical_node_pinning()

    def _configure_critical_node_pinning(self):
        """Configure critical node paths for pinning based on active integrations."""
        critical_pins = []
        
        # Add Matrix room if available
        if self.matrix_observer and settings.MATRIX_ROOM_ID:
            critical_pins.append(f"channels.matrix.{settings.MATRIX_ROOM_ID}")
            logger.info(f"Added Matrix room to critical pins: channels.matrix.{settings.MATRIX_ROOM_ID}")
        
        # Add Farcaster feeds if available
        if self.farcaster_observer:
            critical_pins.extend([
                "farcaster.feeds.home",
                "farcaster.feeds.notifications"
            ])
            logger.info("Added Farcaster feeds to critical pins: home, notifications")
        
        # Update PayloadBuilder's NodeManager with critical pins if it exists
        if hasattr(self.payload_builder, 'node_manager') and self.payload_builder.node_manager:
            for pin_path in critical_pins:
                self.payload_builder.node_manager.get_node_metadata(pin_path).is_pinned = True
                self.payload_builder.node_manager._log_system_event(
                    "integration_pin",
                    f"Node '{pin_path}' pinned as critical integration point.",
                    [pin_path]
                )
            logger.info(f"Configured {len(critical_pins)} critical node pins in PayloadBuilder")
        else:
            logger.warning("PayloadBuilder NodeManager not available for critical pinning")

    def trigger_state_change(self):
        """Trigger immediate processing when world state changes."""
        self.processing_hub.trigger_state_change()

    async def get_system_status(self) -> Dict[str, Any]:
        """
        Get comprehensive system status for the management UI.
        
        Returns:
            Dictionary containing system status information
        """
        try:
            # Get processing hub status
            processing_status = await self.processing_hub.get_processing_status()
            
            # Get world state metrics
            world_state_metrics = {
                "channels_count": len(self.world_state.state.channels),
                "total_messages": sum(len(ch.messages) for ch in self.world_state.state.channels.values()),
                "action_history_count": len(self.world_state.state.action_history.actions),
                "pending_invites": len(self.world_state.get_pending_matrix_invites()),
                "generated_media_count": len(self.world_state.state.generated_media_library),
                "research_entries": len(self.world_state.state.research_database.entries)
            }
            
            # Get tool stats
            tool_stats = self.tool_registry.get_tool_stats()
            
            # Get rate limiter status
            rate_limit_status = self.rate_limiter.get_status()
            
            # Get integration status
            integrations = {
                "matrix": {
                    "connected": self.matrix_observer is not None and getattr(self.matrix_observer.client, 'logged_in', False) if self.matrix_observer else False,
                    "monitored_rooms": getattr(self.matrix_observer, 'channels_to_monitor', []) if self.matrix_observer else [],
                    "pending_invites": len(self.world_state.get_pending_matrix_invites())
                },
                "farcaster": {
                    "connected": self.farcaster_observer is not None,
                    "bot_fid": settings.FARCASTER_BOT_FID,
                    "post_queue_size": getattr(self.farcaster_observer.scheduler.post_queue, 'qsize', lambda: 0)() if self.farcaster_observer and hasattr(self.farcaster_observer, 'scheduler') else 0,
                    "reply_queue_size": getattr(self.farcaster_observer.scheduler.reply_queue, 'qsize', lambda: 0)() if self.farcaster_observer and hasattr(self.farcaster_observer, 'scheduler') else 0
                }
            }
            
            return {
                "system_running": self.running,
                "cycle_count": self.cycle_count,
                "processing": processing_status,
                "world_state": world_state_metrics,
                "tools": tool_stats,
                "rate_limits": rate_limit_status,
                "integrations": integrations,
                "config": {
                    "ai_model": self.config.ai_model,
                    "processing_mode": "node_based" if self.config.processing_config.enable_node_based_processing else "traditional",
                    "observation_interval": self.config.processing_config.observation_interval,
                    "max_cycles_per_hour": self.config.processing_config.max_cycles_per_hour
                }
            }
        except Exception as e:
            logger.error(f"Error getting system status: {e}")
            return {
                "system_running": self.running,
                "error": str(e)
            }

    def force_processing_mode(self, enable_node_based: bool) -> None:
        """
        Force the processing mode to a specific type.
        
        Args:
            enable_node_based: True to force node-based processing, False for traditional
        """
        self.processing_hub.force_processing_mode(enable_node_based)
        self.config.processing_config.enable_node_based_processing = enable_node_based
        logger.info(f"Processing mode forced to {'node-based' if enable_node_based else 'traditional'}")

    def reset_processing_mode(self) -> None:
        """Reset processing mode to automatic determination."""
        self.processing_hub.reset_processing_mode()
        logger.info("Processing mode reset to automatic determination")

    def get_tool_registry(self) -> ToolRegistry:
        """Get the tool registry instance."""
        return self.tool_registry

    def get_ai_engine(self) -> AIDecisionEngine:
        """Get the AI engine instance."""
        return self.ai_engine

    def get_world_state_manager(self) -> WorldStateManager:
        """Get the world state manager instance."""
        return self.world_state

    def get_processing_hub(self) -> ProcessingHub:
        """Get the processing hub instance.""" 
        return self.processing_hub

    def increment_cycle_count(self) -> None:
        """Increment the processing cycle counter."""
        self.cycle_count += 1

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
            logger.warning("No traditional processor available, executing action directly")
            # For test compatibility, execute matrix actions directly
            if action.action_type in ["send_matrix_reply", "send_matrix_message"]:
                await self._execute_matrix_action_directly(action)
            else:
                logger.warning(f"Cannot execute action type {action.action_type} without traditional processor")
    
    async def _execute_matrix_action_directly(self, action) -> None:
        """Execute matrix actions directly for test compatibility."""
        try:
            from ...tools.matrix_tools import SendMatrixReplyTool, SendMatrixMessageTool
            
            # Update action context with required components
            self.action_context.matrix_observer = self.matrix_observer
            self.action_context.world_state_manager = self.world_state
            self.action_context.context_manager = self.context_manager
            
            if action.action_type == "send_matrix_reply":
                tool = SendMatrixReplyTool()
            elif action.action_type == "send_matrix_message":
                tool = SendMatrixMessageTool()
            else:
                logger.error(f"Unknown matrix action type: {action.action_type}")
                return
                
            result = await tool.execute(action.parameters, self.action_context)
            logger.info(f"Direct matrix action execution result: {result}")
            
        except Exception as e:
            logger.error(f"Error executing matrix action directly: {str(e)}")
            logger.exception(e)

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
        
        # Check for media generation + posting coordination opportunities
        coordinated_actions = await self._coordinate_media_actions(actions)
        
        for action in coordinated_actions:
            try:
                # Standardized to always handle ActionPlan objects
                action_name = action.action_type
                action_params = action.parameters
                
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
                    
                    # Fix describe_image parameters if using invalid URL
                    if action_name == "describe_image":
                        action_params = await self._fix_describe_image_params(action_params)
                    
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

    async def _fix_describe_image_params(self, action_params: dict) -> dict:
        """
        Fix describe_image parameters to ensure proper image URL is used.
        
        If the image_url parameter appears to be a filename (e.g., 'image.png'), 
        attempt to find the actual URL from recent messages with image_urls.
        """
        image_url = action_params.get("image_url", "")
        
        # Check if the image_url looks like a filename rather than a URL
        if image_url and not image_url.startswith(("http://", "https://", "mxc://")):
            logger.info(f"describe_image received filename '{image_url}' instead of URL, attempting to fix")
            
            # Search recent messages for actual image URLs
            # Get the channel_id if available for more targeted search
            channel_id = action_params.get("channel_id")
            
            # Look through recent messages in the world state
            if hasattr(self, 'action_context') and hasattr(self.action_context, 'world_state_manager'):
                world_state = self.action_context.world_state_manager
                
                # Search through channels for recent messages with image URLs
                channels_to_search = [channel_id] if channel_id else list(world_state.state.channels.keys())
                
                for ch_id in channels_to_search:
                    if ch_id in world_state.state.channels:
                        channel = world_state.state.channels[ch_id]
                        # Look at recent messages (last 10)
                        recent_messages = (channel.recent_messages[-10:] \
                                           if len(channel.recent_messages) > 10 \
                                           else channel.recent_messages)
                        
                        for message in reversed(recent_messages):  # Start with most recent
                            if message.image_urls:
                                # Check if this message's content matches the filename
                                if message.content and image_url in message.content:
                                    # Use the first image URL from this message
                                    corrected_url = message.image_urls[0]
                                    logger.info(f"Fixed describe_image URL: '{image_url}' -> '{corrected_url}'")
                                    
                                    # Create corrected parameters
                                    corrected_params = action_params.copy()
                                    corrected_params["image_url"] = corrected_url
                                    return corrected_params
                                
                                # Also check if the filename appears to match (basic heuristic)
                                if any(ext in image_url.lower() for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']):
                                    # If we have a recent image and the URL is clearly a filename, use the most recent image
                                    corrected_url = message.image_urls[0]
                                    logger.info(f"Used most recent image URL for describe_image: '{image_url}' -> '{corrected_url}'")
                                    
                                    corrected_params = action_params.copy()
                                    corrected_params["image_url"] = corrected_url
                                    return corrected_params
                
                logger.warning(f"Could not find matching image URL for filename '{image_url}' in recent messages")
        
        # Return original parameters if no fix was needed or possible
        return action_params

    async def _coordinate_media_actions(self, actions: list) -> list:
        """
        Coordinate media generation (image/video) with posting actions to enable auto-embedding.
        
        If both media generation and posting actions are present in the same batch,
        execute media generation first and automatically include the media URL in posts.
        """
        # Extract action names and find coordination opportunities
        action_names = []
        action_map = {}
        
        for i, action in enumerate(actions):
            if hasattr(action, 'action_type'):
                action_name = action.action_type
                action_names.append(action_name)
                action_map[action_name] = i
        
        # Check for image generation + posting coordination
        if "generate_image" in action_names and "send_farcaster_post" in action_names:
            logger.info("Detected image generation + Farcaster post coordination opportunity")
            return await self._coordinate_image_with_farcaster(actions, action_map)
        
        if "generate_image" in action_names and "send_matrix_message" in action_names:
            logger.info("Detected image generation + Matrix message coordination opportunity")
            return await self._coordinate_image_with_matrix(actions, action_map)
        
        # Check for video generation + posting coordination
        if "generate_video" in action_names and "send_farcaster_post" in action_names:
            logger.info("Detected video generation + Farcaster post coordination opportunity")
            return await self._coordinate_video_with_farcaster(actions, action_map)
        
        if "generate_video" in action_names and "send_matrix_message" in action_names:
            logger.info("Detected video generation + Matrix message coordination opportunity")
            return await self._coordinate_video_with_matrix(actions, action_map)
        
        # No coordination needed, return actions as-is
        return actions

    async def _coordinate_image_with_farcaster(self, actions: list, action_map: dict) -> list:
        """Coordinate image generation with Farcaster posting."""
        current_time = time.time()
        coordinated_actions = []
        generated_embed_url = None
        
        # First, execute image generation
        image_action_idx = action_map["generate_image"]
        image_action = actions[image_action_idx]
        
        try:
            action_params = image_action.parameters
            
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
                    
                    # Extract embed URL from result
                    if isinstance(result, dict) and result.get("status") == "success" and result.get("embed_page_url"):
                        generated_embed_url = result["embed_page_url"]
                        logger.info(f"Generated image embed page URL for coordination: {generated_embed_url}")
                    
                    # Record in context
                    if self.context_manager:
                        channel_id = action_params.get('channel_id', 'default')
                        result_dict = result if isinstance(result, dict) else {'result': str(result)}
                        await self.context_manager.add_tool_result(channel_id, "generate_image", result_dict)
            else:
                logger.warning(f"Cannot execute image generation for coordination: {reason}")
        
        except Exception as e:
            logger.error(f"Error in coordinated image generation: {e}")
        
        # Now process other actions, modifying Farcaster post if we have an embed URL
        for i, action in enumerate(actions):
            if i == image_action_idx:
                # Skip the image action since we already executed it
                continue
            
            # Check if this is the Farcaster post action
            action_name = action.action_type
            action_params = action.parameters.copy()  # Make a copy to avoid modifying original

            if action_name == "send_farcaster_post" and generated_embed_url:
                # Add the generated embed URL to the Farcaster post
                action_params["embed_url"] = generated_embed_url
                logger.info(f"Enhanced Farcaster post with generated image embed page: {generated_embed_url}")
                
                # Create modified action
                from ..ai_engine import ActionPlan
                modified_action = ActionPlan(
                    action_type=action.action_type,
                    parameters=action_params,
                    reasoning=action.reasoning,
                    priority=action.priority
                )
                
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
            action_params = image_action.parameters
            
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
            action_name = action.action_type
            action_params = action.parameters.copy()

            if action_name == "send_matrix_message" and generated_image_url:
                # Convert to send_matrix_image action for better embedding
                action_params["image_url"] = generated_image_url
                # Keep the original message as caption/description
                if "message" in action_params:
                    action_params["caption"] = action_params.pop("message")
                
                logger.info(f"Converting Matrix message to Matrix image with URL: {generated_image_url}")
                
                # Create modified action
                from ..ai_engine import ActionPlan
                modified_action = ActionPlan(
                    action_type="send_matrix_image",
                    parameters=action_params,
                    reasoning=f"Converted to image post with generated image: {action.reasoning}",
                    priority=action.priority
                )
                
                coordinated_actions.append(modified_action)
            else:
                # Add action as-is
                coordinated_actions.append(action)
        
        return coordinated_actions

    async def _coordinate_video_with_farcaster(self, actions: list, action_map: dict) -> list:
        """Coordinate video generation with Farcaster posting."""
        current_time = time.time()
        coordinated_actions = []
        generated_embed_url = None
        
        video_action_idx = action_map["generate_video"]
        video_action = actions[video_action_idx]
        
        try:
            action_params = video_action.parameters
            
            can_execute, reason = self.rate_limiter.can_execute_action("generate_video", current_time)
            
            if can_execute:
                tool = self.tool_registry.get_tool("generate_video")
                if tool:
                    self.rate_limiter.record_action("generate_video", current_time)
                    result = await tool.execute(action_params, self.action_context)
                    logger.info(f"Executed coordinated video generation: {result}")
                    
                    if isinstance(result, dict) and result.get("status") == "success" and result.get("embed_page_url"):
                        generated_embed_url = result["embed_page_url"]
                        logger.info(f"Generated video embed page URL for coordination: {generated_embed_url}")

                    if self.context_manager:
                        channel_id = action_params.get('channel_id', 'default')
                        result_dict = result if isinstance(result, dict) else {'result': str(result)}
                        await self.context_manager.add_tool_result(channel_id, "generate_video", result_dict)
            else:
                logger.warning(f"Cannot execute video generation for coordination: {reason}")
        
        except Exception as e:
            logger.error(f"Error in coordinated video generation: {e}")
        
        for i, action in enumerate(actions):
            if i == video_action_idx:
                continue
            
            action_name = action.action_type
            action_params = action.parameters.copy()

            if action_name == "send_farcaster_post" and generated_embed_url:
                action_params["embed_url"] = generated_embed_url
                logger.info(f"Enhanced Farcaster post with generated video embed page: {generated_embed_url}")
                
                from ..ai_engine import ActionPlan
                modified_action = ActionPlan(
                    action_type=action.action_type,
                    parameters=action_params,
                    reasoning=action.reasoning,
                    priority=action.priority
                )
                
                coordinated_actions.append(modified_action)
            else:
                coordinated_actions.append(action)
        
        return coordinated_actions

    async def _coordinate_video_with_matrix(self, actions: list, action_map: dict) -> list:
        """Coordinate video generation with Matrix messaging."""
        current_time = time.time()
        coordinated_actions = []
        generated_video_url = None
        
        video_action_idx = action_map["generate_video"]
        video_action = actions[video_action_idx]
        
        try:
            action_params = video_action.parameters
            
            can_execute, reason = self.rate_limiter.can_execute_action("generate_video", current_time)
            
            if can_execute:
                tool = self.tool_registry.get_tool("generate_video")
                if tool:
                    self.rate_limiter.record_action("generate_video", current_time)
                    result = await tool.execute(action_params, self.action_context)
                    logger.info(f"Executed coordinated video generation: {result}")
                    
                    if isinstance(result, dict) and result.get("status") == "success" and result.get("s3_video_url"):
                        generated_video_url = result["s3_video_url"]
                        logger.info(f"Generated video URL for Matrix coordination: {generated_video_url}")

                    if self.context_manager:
                        channel_id = action_params.get('channel_id', 'default')
                        result_dict = result if isinstance(result, dict) else {'result': str(result)}
                        await self.context_manager.add_tool_result(channel_id, "generate_video", result_dict)
            else:
                logger.warning(f"Cannot execute video generation for coordination: {reason}")
        
        except Exception as e:
            logger.error(f"Error in coordinated video generation: {e}")
            
        for i, action in enumerate(actions):
            if i == video_action_idx:
                continue
                
            action_name = action.action_type
            action_params = action.parameters.copy()

            if action_name == "send_matrix_message" and generated_video_url:
                action_params["video_url"] = generated_video_url
                if "message" in action_params:
                    action_params["caption"] = action_params.pop("message")
                
                logger.info(f"Converting Matrix message to Matrix video with URL: {generated_video_url}")
                
                from ..ai_engine import ActionPlan
                modified_action = ActionPlan(
                    action_type="send_matrix_video",
                    parameters=action_params,
                    reasoning=f"Converted to video post with generated video: {action.reasoning}",
                    priority=action.priority
                )
                
                coordinated_actions.append(modified_action)
            else:
                coordinated_actions.append(action)
        
        return coordinated_actions
