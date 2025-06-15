"""
Main Orchestrator

Lean coordinator that manages observers, components, and overall system lifecycle.
Acts as the primary entry point and coordinates between different subsystems.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...config import settings
from ...core.context import ContextManager
from ...core.integration_manager import IntegrationManager
from ...integrations.arweave_uploader_client import ArweaveUploaderClient
from ...integrations.farcaster import FarcasterObserver
from ..node_system.node_manager import NodeManager
from ..node_system.node_processor import NodeProcessor
from ..node_system.summary_service import NodeSummaryService
from ..node_system.interaction_tools import NodeInteractionTools
from ...integrations.matrix.observer import MatrixObserver
from ...integrations.base_nft_service import BaseNFTService
from ...integrations.eligibility_service import UserEligibilityService
from ...tools.registry import ToolRegistry
from ..world_state.manager import WorldStateManager
from ..world_state.payload_builder import PayloadBuilder
from .processing_hub import ProcessingHub, ProcessingConfig
from .rate_limiter import RateLimiter, RateLimitConfig
from ..proactive import ProactiveConversationEngine
from ..history_recorder import HistoryRecorder

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
        
        # Initialize HistoryRecorder for persistent memory
        self.history_recorder = HistoryRecorder(self.config.db_path)
        
        # Connect HistoryRecorder to WorldStateManager for memory persistence
        self.world_state.set_history_recorder(self.history_recorder)
        
        # Integration management
        self.integration_manager = IntegrationManager(
            db_path=self.config.db_path,
            world_state_manager=self.world_state
        )
        
        # Processing hub
        self.processing_hub = ProcessingHub(
            world_state_manager=self.world_state,
            payload_builder=self.payload_builder,
            rate_limiter=self.rate_limiter,
            config=self.config.processing_config
        )
        
        # Proactive conversation engine (Initiative C)
        self.proactive_engine = ProactiveConversationEngine(
            world_state_manager=self.world_state,
            context_manager=self.context_manager
        )
        
        # Connect proactive engine to world state manager for easy access
        self.world_state.proactive_engine = self.proactive_engine
        
        # Tool Registry and AI Engine
        self.tool_registry = ToolRegistry()
        
        # Import the prompt builder
        from ...core.prompts import prompt_builder
        
        # Ensure we have an API key
        api_key = settings.OPENROUTER_API_KEY
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY is required but not set")
        
        # Choose AI engine based on configuration
        optimization_level = getattr(settings, 'AI_OPTIMIZATION_LEVEL', 'balanced')
        
        from ..ai_engine import AIDecisionEngine, OptimizationLevel
        
        # Validate optimization level
        valid_levels = [OptimizationLevel.ORIGINAL, OptimizationLevel.BALANCED, OptimizationLevel.AGGRESSIVE]
        if optimization_level not in valid_levels:
            logger.warning(f"Invalid optimization level '{optimization_level}', using 'balanced'")
            optimization_level = OptimizationLevel.BALANCED
        
        self.ai_engine = AIDecisionEngine(
            api_key=api_key,
            model=self.config.ai_model,
            optimization_level=optimization_level,
            prompt_builder_instance=prompt_builder,
            config=self.config
        )
        logger.info(f"MainOrchestrator: Using AIDecisionEngine with {optimization_level} optimization")
        
        # Initialize Arweave client for internal uploader service
        self.arweave_client = None
        if settings.ARWEAVE_INTERNAL_UPLOADER_SERVICE_URL:
            self.arweave_client = ArweaveUploaderClient(
                uploader_service_url=settings.ARWEAVE_INTERNAL_UPLOADER_SERVICE_URL,
                gateway_url=settings.ARWEAVE_GATEWAY_URL,
            )
            logger.info("Arweave client initialized for internal uploader service.")
        
        # Initialize service registry for service-oriented architecture
        from ..services import ServiceRegistry
        self.service_registry = ServiceRegistry()
        
        # Create action context for tool execution
        from ...tools.base import ActionContext
        from ...tools.arweave_service import ArweaveService
        
        # Initialize arweave service with our client
        arweave_service_instance = ArweaveService(arweave_client=self.arweave_client)
        
        self.action_context = ActionContext(
            service_registry=self.service_registry,
            world_state_manager=self.world_state,
            context_manager=self.context_manager,
            arweave_client=self.arweave_client,
            arweave_service=arweave_service_instance
        )
        
        # Legacy observer references for backward compatibility
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
        from ...tools.farcaster import (
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
            AddFarcasterFeedTool,
            ListFarcasterFeedsTool,
            RemoveFarcasterFeedTool,
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
        from ...tools.matrix import (
            AcceptMatrixInviteTool,
            IgnoreMatrixInviteTool,
            JoinMatrixRoomTool,
            LeaveMatrixRoomTool,
            ReactToMatrixMessageTool,
            SendMatrixImageTool,
            SendMatrixMessageTool,
            SendMatrixReplyTool,
            SendMatrixVideoTool,
            SendMatrixVideoLinkTool,
        )
        from ...tools.media_generation_tools import GenerateImageTool, GenerateVideoTool
        from ...tools.permaweb_tools import StorePermanentMemoryTool
        from ...tools.web_tools import WebSearchTool
        from ...tools.research_tools import UpdateResearchTool, QueryResearchTool
        from ...tools.developer_tools import (
            GetGitHubIssuesTool, GetGitHubIssueDetailsTool, CommentOnGitHubIssueTool,
            CreateGitHubIssueTool, AnalyzeChannelForIssuesTool,
            GetCodebaseStructureTool, SetupDevelopmentWorkspaceTool, ExploreCodebaseTool,
            AnalyzeAndProposeChangeTool, ImplementCodeChangesTool,
            CreatePullRequestTool
        )
        from ...tools.user_profiling_tools import (
            SentimentAnalysisTool,
            StoreUserMemoryTool,
            GetUserProfileTool
        )
        from ...tools.world_state_tools import (
            QueryChannelActivityTool,
            FindMessagesFromUserTool,
            CheckActionHistoryTool
        )
        from ...tools.proactive_conversation_tools import (
            InitiateProactiveConversationTool,
            DetectConversationOpportunitiesTool,
            ScheduleProactiveEngagementTool,
            GetProactiveEngagementStatusTool
        )
        
        # Core tools
        self.tool_registry.register_tool(WaitTool())
        self.tool_registry.register_tool(DescribeImageTool())
        
        # Web search and research tools
        self.tool_registry.register_tool(WebSearchTool())
        self.tool_registry.register_tool(UpdateResearchTool())
        self.tool_registry.register_tool(QueryResearchTool())
        
        # World state query tools
        self.tool_registry.register_tool(QueryChannelActivityTool())
        self.tool_registry.register_tool(FindMessagesFromUserTool())
        self.tool_registry.register_tool(CheckActionHistoryTool())
        
        # Matrix tools
        self.tool_registry.register_tool(SendMatrixMessageTool())
        self.tool_registry.register_tool(SendMatrixReplyTool())
        self.tool_registry.register_tool(SendMatrixImageTool())
        self.tool_registry.register_tool(SendMatrixVideoTool())
        self.tool_registry.register_tool(SendMatrixVideoLinkTool())
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
        
        # Farcaster feed management tools
        self.tool_registry.register_tool(AddFarcasterFeedTool())
        self.tool_registry.register_tool(ListFarcasterFeedsTool())
        self.tool_registry.register_tool(RemoveFarcasterFeedTool())
        
        # Farcaster Frame tools
        self.tool_registry.register_tool(CreateTransactionFrameTool())
        self.tool_registry.register_tool(CreatePollFrameTool())
        self.tool_registry.register_tool(CreateCustomFrameTool())
        self.tool_registry.register_tool(SearchFramesTool())
        self.tool_registry.register_tool(GetFrameCatalogTool())
        
        # NFT Frame tools
        self.tool_registry.register_tool(CreateMintFrameTool())
        self.tool_registry.register_tool(CreateAirdropClaimFrameTool())
        
        # Service-oriented tools (new architecture) - REMOVED
        # Legacy tools now use service-oriented architecture internally
        # No need for separate _v2 tools

        # Media generation tools
        self.tool_registry.register_tool(GenerateImageTool())
        self.tool_registry.register_tool(GenerateVideoTool())
        
        # Permaweb tools
        self.tool_registry.register_tool(StorePermanentMemoryTool())
        
        # GitHub-Centric Developer tools (ACE Phase 2 & 3)
        self.tool_registry.register_tool(GetGitHubIssuesTool())
        self.tool_registry.register_tool(GetGitHubIssueDetailsTool())
        self.tool_registry.register_tool(CommentOnGitHubIssueTool())
        self.tool_registry.register_tool(CreateGitHubIssueTool())
        self.tool_registry.register_tool(AnalyzeChannelForIssuesTool())
        
        # Core Developer tools (ACE Phase 1, 2 & 3)
        self.tool_registry.register_tool(GetCodebaseStructureTool())
        self.tool_registry.register_tool(SetupDevelopmentWorkspaceTool())
        self.tool_registry.register_tool(ExploreCodebaseTool())
        self.tool_registry.register_tool(AnalyzeAndProposeChangeTool())
        self.tool_registry.register_tool(ImplementCodeChangesTool())
        self.tool_registry.register_tool(CreatePullRequestTool())
        
        # User Profiling tools (Initiative B)
        self.tool_registry.register_tool(SentimentAnalysisTool())
        self.tool_registry.register_tool(StoreUserMemoryTool())
        self.tool_registry.register_tool(GetUserProfileTool())
        
        # Proactive Conversation tools (Initiative C)
        self.tool_registry.register_tool(InitiateProactiveConversationTool())
        self.tool_registry.register_tool(DetectConversationOpportunitiesTool())
        self.tool_registry.register_tool(ScheduleProactiveEngagementTool())
        self.tool_registry.register_tool(GetProactiveEngagementStatusTool())

    async def start(self) -> None:
        """Start the entire orchestrator system."""
        if self.running:
            logger.warning("Main orchestrator already running")
            return

        logger.info("Starting main orchestrator system...")
        self.running = True

        try:
            # Initialize integration manager
            await self.integration_manager.initialize()
            
            # Initialize HistoryRecorder for persistent memory
            await self.history_recorder.initialize()
            logger.info("HistoryRecorder initialized for persistent memory")
            
            # Restore persistent state from previous runs
            await self.world_state.restore_persistent_state()
            logger.info("Persistent state restored from previous runs")
            
            # Register integrations from environment variables
            await self._register_integrations_from_env()
            
            # Connect all active integrations and start their services
            await self.integration_manager.connect_all_active()
            await self.integration_manager.start_all_services()
            
            # Update legacy observer references for backward compatibility
            await self._update_legacy_observer_references()
            
            # Register integration services in the service registry
            await self._register_integration_services()
            
            # Update action context with properly connected integrations
            await self._update_action_context_integrations()
            
            # Ensure the media gallery channel exists or create it
            await self._ensure_media_gallery_exists()
            
            # Initialize NFT and blockchain services
            await self._initialize_nft_services()
            
            # Set up processing hub with traditional processor
            self._setup_processing_components()
            
            # Start the proactive conversation engine
            await self.proactive_engine.start()
            
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
        
        # Stop proactive conversation engine
        if self.proactive_engine:
            await self.proactive_engine.stop()
        
        # Stop NFT and eligibility services
        if self.eligibility_service:
            await self.eligibility_service.stop()
        
        # Stop all integration services and disconnect
        await self.integration_manager.stop_all_services()
        await self.integration_manager.disconnect_all()
        
        # Clean up integration manager resources
        await self.integration_manager.cleanup()
        
        # Clear legacy observer references
        self.matrix_observer = None
        self.farcaster_observer = None

        logger.info("Main orchestrator system stopped")

    def _setup_processing_components(self):
        """Set up processing components for the processing hub."""
        try:
            # Initialize node system components
            logger.info("Setting up node-based processing components...")
            
            # Create node manager with critical pinned nodes
            critical_pins = self._get_critical_node_pins()
            self.node_manager = NodeManager(
                max_expanded_nodes=8,
                default_pinned_nodes=critical_pins
            )
            logger.info(f"Node manager initialized with {len(critical_pins)} critical pins: {critical_pins}")
            
            # Create node summary service
            if settings.OPENROUTER_API_KEY:
                self.node_summary_service = NodeSummaryService(
                    api_key=settings.OPENROUTER_API_KEY,
                    model=settings.AI_SUMMARY_MODEL
                )
            else:
                logger.warning("No API key available for node summary service")
                self.node_summary_service = None
            
            # Create node interaction tools
            self.node_interaction_tools = NodeInteractionTools(self.node_manager)
            
            # Create node processor
            if (self.world_state and self.payload_builder and self.ai_engine and 
                self.node_manager and self.node_summary_service and self.node_interaction_tools):
                
                self.node_processor = NodeProcessor(
                    world_state_manager=self.world_state,
                    payload_builder=self.payload_builder,
                    ai_engine=self.ai_engine,
                    node_manager=self.node_manager,
                    summary_service=self.node_summary_service,
                    interaction_tools=self.node_interaction_tools,
                    tool_registry=self.tool_registry,
                    action_context=self.action_context
                )
                
                # Set the node processor in the processing hub
                self.processing_hub.node_processor = self.node_processor
                
                logger.info("Node processor successfully initialized and connected to processing hub")
            else:
                logger.error("Failed to initialize node processor - missing dependencies")
                self.node_processor = None
            
            logger.info("Processing components setup complete - node-based processing ready")
            
        except Exception as e:
            logger.error(f"Error setting up processing components: {e}", exc_info=True)
            self.node_processor = None

    def _get_critical_node_pins(self) -> List[str]:
        """Get critical node paths that should be pinned based on active integrations."""
        critical_pins = []
        
        # Add Matrix room if available
        if hasattr(self, 'matrix_observer') and self.matrix_observer and settings.MATRIX_ROOM_ID:
            critical_pins.append(f"channels.matrix.{settings.MATRIX_ROOM_ID}")
            logger.debug(f"Added Matrix room to critical pins: channels.matrix.{settings.MATRIX_ROOM_ID}")
        
        # Add Farcaster feeds if available  
        if hasattr(self, 'farcaster_observer') and self.farcaster_observer:
            critical_pins.extend([
                "farcaster.feeds.home",
                "farcaster.feeds.notifications"
            ])
            logger.debug("Added Farcaster feeds to critical pins: home, notifications")
        
        return critical_pins

    async def _update_legacy_observer_references(self) -> None:
        """Update legacy observer references for backward compatibility."""
        try:
            active_integrations = self.integration_manager.get_active_integrations()
            
            # Update legacy references
            for integration_id, integration in active_integrations.items():
                if hasattr(integration, 'integration_type'):
                    if integration.integration_type == 'matrix':
                        self.matrix_observer = integration
                        logger.debug(f"Updated legacy matrix_observer reference to integration {integration_id}")
                    elif integration.integration_type == 'farcaster':
                        self.farcaster_observer = integration
                        logger.debug(f"Updated legacy farcaster_observer reference to integration {integration_id}")
                        
        except Exception as e:
            logger.error(f"Error updating legacy observer references: {e}")

    async def _register_integration_services(self) -> None:
        """Register integration services in the service registry for service-oriented access."""
        try:
            active_integrations = self.integration_manager.get_active_integrations()
            
            # Register services based on active integrations
            for integration_id, integration in active_integrations.items():
                if hasattr(integration, 'integration_type'):
                    if integration.integration_type == 'matrix':
                        from ..services import MatrixService
                        matrix_service = MatrixService(
                            matrix_observer=integration,
                            world_state_manager=self.world_state,
                            context_manager=self.context_manager
                        )
                        self.service_registry.register_service(matrix_service)
                        logger.info(f"Registered Matrix service for integration {integration_id}")
                        
                    elif integration.integration_type == 'farcaster':
                        from ..services import FarcasterService
                        farcaster_service = FarcasterService(
                            farcaster_observer=integration,
                            world_state_manager=self.world_state,
                            context_manager=self.context_manager
                        )
                        self.service_registry.register_service(farcaster_service)
                        logger.info(f"Registered Farcaster service for integration {integration_id}")
                        
        except Exception as e:
            logger.error(f"Error registering integration services: {e}")

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
                
                # Connect processing hub for trigger generation
                self.matrix_observer.processing_hub = self.processing_hub
                
                # Connect legacy state change callback for backward compatibility
                self.matrix_observer.on_state_change = self._on_world_state_change
                
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
                
                # Connect processing hub for trigger generation
                self.farcaster_observer.processing_hub = self.processing_hub
                
                # Connect legacy state change callback for backward compatibility
                self.farcaster_observer.on_state_change = self._on_world_state_change
                
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

    async def _update_action_context_integrations(self) -> None:
        """Update action context with properly connected integrations from IntegrationManager."""
        # Update action context with initialized observers
        active_integrations = self.integration_manager.get_active_integrations()
        
        # Find Matrix and Farcaster integrations
        matrix_integration = None
        farcaster_integration = None
        
        for integration_id, integration in active_integrations.items():
            if hasattr(integration, 'integration_type') and integration.integration_type == 'matrix':
                matrix_integration = integration
            elif hasattr(integration, 'integration_type') and integration.integration_type == 'farcaster':
                farcaster_integration = integration
        
        # Update action context and maintain legacy properties
        self.action_context.matrix_observer = matrix_integration or self.matrix_observer
        self.action_context.farcaster_observer = farcaster_integration or self.farcaster_observer
        
        # Debug logging to track which observer is being used
        if farcaster_integration:
            logger.info(f"✓ Using Farcaster integration from IntegrationManager (ID: {farcaster_integration.integration_id})")
            logger.info(f"  API client initialized: {farcaster_integration.api_client is not None}")
        elif self.farcaster_observer:
            logger.info(f"⚠ Using legacy Farcaster observer (fallback)")
            logger.info(f"  API client initialized: {self.farcaster_observer.api_client is not None}")
        else:
            logger.info("ℹ No Farcaster observer available")

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
        
        # Try to apply critical pins to available node managers
        node_manager = None
        
        # First, check if PayloadBuilder has a node_manager
        if hasattr(self.payload_builder, 'node_manager') and self.payload_builder.node_manager:
            node_manager = self.payload_builder.node_manager
            logger.debug("Using PayloadBuilder's NodeManager for critical pinning")
        # Next, check if ProcessingHub's node_processor has a node_manager
        elif (self.processing_hub.node_processor and 
              hasattr(self.processing_hub.node_processor, 'node_manager') and 
              self.processing_hub.node_processor.node_manager):
            node_manager = self.processing_hub.node_processor.node_manager
            logger.debug("Using ProcessingHub's node_processor NodeManager for critical pinning")
        
        if node_manager:
            for pin_path in critical_pins:
                node_manager.get_node_metadata(pin_path).is_pinned = True
                node_manager._log_system_event(
                    "integration_pin",
                    f"Node '{pin_path}' pinned as critical integration point.",
                    [pin_path]
                )
            logger.info(f"Configured {len(critical_pins)} critical node pins")
        else:
            if critical_pins:  # Only warn if there are actually pins to configure
                logger.warning("NodeManager not available for critical pinning")
            else:
                logger.debug("No critical pins to configure")

    def trigger_state_change(self):
        """Trigger immediate processing when world state changes."""
        self.processing_hub.trigger_state_change()
    
    def _on_world_state_change(self):
        """Handle world state changes for both processing and proactive conversations."""
        # Trigger normal processing
        self.processing_hub.trigger_state_change()
        
        # Trigger proactive conversation opportunity detection
        if self.proactive_engine:
            asyncio.create_task(self.proactive_engine.on_world_state_change())

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
        Force the processing mode to a specific type - deprecated method.
        
        Args:
            enable_node_based: Ignored, system now uses node-based processing only
        """
        logger.warning("force_processing_mode is deprecated - system now uses node-based processing only")

    def reset_processing_mode(self) -> None:
        """Reset processing mode to automatic determination - deprecated method."""
        logger.warning("reset_processing_mode is deprecated - system now uses node-based processing only")

    def get_tool_registry(self) -> ToolRegistry:
        """Get the tool registry instance."""
        return self.tool_registry

    def get_ai_engine(self):
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
        """Process a payload directly - deprecated method for backward compatibility."""
        logger.warning("process_payload method is deprecated - system now uses node-based processing only")

    async def _execute_action(self, action) -> None:
        """Execute a single action - wrapper for test compatibility."""
        logger.warning("_execute_action method is deprecated - system now uses node-based processing only")
        # For test compatibility, execute matrix actions directly
        if action.action_type in ["send_matrix_reply", "send_matrix_message"]:
            await self._execute_matrix_action_directly(action)
        else:
            logger.warning(f"Cannot execute action type {action.action_type} without traditional processor")
    
    async def _execute_matrix_action_directly(self, action) -> None:
        """Execute matrix actions directly for test compatibility."""
        try:
            from ...tools.matrix import SendMatrixReplyTool, SendMatrixMessageTool
            
            # Get matrix observer from integration manager
            active_integrations = self.integration_manager.get_active_integrations()
            matrix_integration = None
            for integration_id, integration in active_integrations.items():
                if hasattr(integration, 'name') and integration.name == 'matrix':
                    matrix_integration = integration
                    break
            
            # Update action context with required components
            self.action_context.matrix_observer = matrix_integration or self.matrix_observer
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

    async def _ensure_media_gallery_exists(self) -> None:
        """Check for, create, and configure the media gallery room."""
        if settings.MATRIX_MEDIA_GALLERY_ROOM_ID:
            logger.info(f"Matrix media gallery is configured: {settings.MATRIX_MEDIA_GALLERY_ROOM_ID}")
            return

        config_path = Path("data/config.json")
        if config_path.exists():
            try:
                with open(config_path, 'r') as f:
                    config_data = json.load(f)
                    gallery_id = config_data.get("MATRIX_MEDIA_GALLERY_ROOM_ID")
                    if gallery_id:
                        settings.MATRIX_MEDIA_GALLERY_ROOM_ID = gallery_id
                        logger.info(f"Loaded Matrix media gallery from config.json: {gallery_id}")
                        return
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Could not read gallery ID from config.json: {e}")

        logger.info("MATRIX_MEDIA_GALLERY_ROOM_ID not found. Attempting to create a new gallery room...")
        if not self.action_context.matrix_observer:
            logger.error("Cannot create gallery room: Matrix observer is not available.")
            return

        try:
            from nio import RoomCreateResponse, RoomVisibility
            response = await self.action_context.matrix_observer.client.room_create(
                visibility=RoomVisibility.public,
                name="AI Media Gallery",
                topic="A collection of media generated by the AI agent.",
                initial_state=[{"type": "m.room.guest_access", "state_key": "", "content": {"guest_access": "can_join"}}],
            )
            if isinstance(response, RoomCreateResponse) and response.room_id:
                new_room_id = response.room_id
                logger.info(f"Successfully created new Matrix media gallery: {new_room_id}")
                settings.MATRIX_MEDIA_GALLERY_ROOM_ID = new_room_id

                # Persist the new room ID to config.json
                config_data = {}
                if config_path.exists():
                    with open(config_path, 'r') as f: 
                        config_data = json.load(f)
                config_data["MATRIX_MEDIA_GALLERY_ROOM_ID"] = new_room_id
                config_path.parent.mkdir(parents=True, exist_ok=True)
                with open(config_path, 'w') as f: 
                    json.dump(config_data, f, indent=2)
                logger.info(f"Saved new gallery room ID to {config_path}")
            else:
                logger.error(f"Failed to create gallery room. Response: {response}")
        except Exception as e:
            logger.error(f"Exception during gallery room creation: {e}", exc_info=True)

    async def _register_integrations_from_env(self) -> None:
        """Register integrations from environment variables if they don't exist."""
        logger.info("Checking for integrations to register from environment variables...")
        
        # Get existing integrations
        existing_integrations = await self.integration_manager.list_integrations()
        
        # Check for Farcaster integration
        if (settings.NEYNAR_API_KEY and 
            settings.FARCASTER_BOT_FID and 
            settings.FARCASTER_BOT_SIGNER_UUID):
            
            farcaster_exists = any(
                integration.get('integration_type') == 'farcaster' 
                for integration in existing_integrations
            )
            
            if not farcaster_exists:
                logger.info("Registering Farcaster integration from environment variables...")
                try:
                    await self.integration_manager.add_integration(
                        integration_type='farcaster',
                        display_name='Farcaster Bot',
                        config={
                            'username': settings.FARCASTER_BOT_USERNAME or 'farcaster_bot'
                        },
                        credentials={
                            'api_key': settings.NEYNAR_API_KEY,
                            'bot_fid': settings.FARCASTER_BOT_FID,
                            'signer_uuid': settings.FARCASTER_BOT_SIGNER_UUID
                        }
                    )
                    logger.info("✓ Farcaster integration registered successfully")
                except Exception as e:
                    logger.error(f"Failed to register Farcaster integration: {e}")
            else:
                logger.info("Farcaster integration already exists, updating credentials from environment...")
                # Update credentials for existing integration
                farcaster_integration = next(
                    (integration for integration in existing_integrations 
                     if integration.get('integration_type') == 'farcaster'), None
                )
                if farcaster_integration:
                    try:
                        # Clean up any invalid credentials first
                        await self.integration_manager.clean_invalid_credentials(farcaster_integration['integration_id'])
                        
                        # Update credentials from environment
                        await self.integration_manager.update_credentials(
                            farcaster_integration['integration_id'],
                            {
                                'api_key': settings.NEYNAR_API_KEY,
                                'bot_fid': settings.FARCASTER_BOT_FID,
                                'signer_uuid': settings.FARCASTER_BOT_SIGNER_UUID
                            }
                        )
                        logger.info("✓ Farcaster credentials updated from environment variables")
                    except Exception as e:
                        logger.error(f"Failed to update Farcaster credentials: {e}")
        else:
            logger.debug("Farcaster environment variables not fully configured, skipping auto-registration")
            # If environment variables aren't set but integration exists, remove it
            farcaster_integration = next(
                (integration for integration in existing_integrations 
                 if integration.get('integration_type') == 'farcaster'), None
            )
            if farcaster_integration:
                logger.info("Removing Farcaster integration since environment variables are not configured")
                try:
                    await self.integration_manager.remove_integration(farcaster_integration['integration_id'])
                    logger.info("✓ Farcaster integration removed successfully")
                except Exception as e:
                    logger.error(f"Failed to remove Farcaster integration: {e}")
        
        # Check for Matrix integration
        if (settings.MATRIX_HOMESERVER and 
            settings.MATRIX_USER_ID and 
            settings.MATRIX_PASSWORD):
            
            matrix_exists = any(
                integration.get('integration_type') == 'matrix' 
                for integration in existing_integrations
            )
            
            if not matrix_exists:
                logger.info("Registering Matrix integration from environment variables...")
                try:
                    await self.integration_manager.add_integration(
                        integration_type='matrix',
                        display_name='Matrix Bot',
                        config={
                            'room_id': settings.MATRIX_ROOM_ID,
                            'device_name': settings.DEVICE_NAME
                        },
                        credentials={
                            'homeserver': settings.MATRIX_HOMESERVER,
                            'user_id': settings.MATRIX_USER_ID,
                            'password': settings.MATRIX_PASSWORD
                        }
                    )
                    logger.info("✓ Matrix integration registered successfully")
                except Exception as e:
                    logger.error(f"Failed to register Matrix integration: {e}")
            else:
                logger.info("Matrix integration already exists, updating credentials from environment...")
                # Update credentials for existing integration
                matrix_integration = next(
                    (integration for integration in existing_integrations 
                     if integration.get('integration_type') == 'matrix'), None
                )
                if matrix_integration:
                    try:
                        # Clean up any invalid credentials first
                        await self.integration_manager.clean_invalid_credentials(matrix_integration['integration_id'])
                        
                        # Update credentials from environment
                        await self.integration_manager.update_credentials(
                            matrix_integration['integration_id'],
                            {
                                'homeserver': settings.MATRIX_HOMESERVER,
                                'user_id': settings.MATRIX_USER_ID,
                                'password': settings.MATRIX_PASSWORD
                            }
                        )
                        logger.info("✓ Matrix credentials updated from environment variables")
                    except Exception as e:
                        logger.error(f"Failed to update Matrix credentials: {e}")
        else:
            logger.debug("Matrix environment variables not fully configured, skipping auto-registration")
            # If environment variables aren't set but integration exists, remove it
            matrix_integration = next(
                (integration for integration in existing_integrations 
                 if integration.get('integration_type') == 'matrix'), None
            )
            if matrix_integration:
                logger.info("Removing Matrix integration since environment variables are not configured")
                try:
                    await self.integration_manager.remove_integration(matrix_integration['integration_id'])
                    logger.info("✓ Matrix integration removed successfully")
                except Exception as e:
                    logger.error(f"Failed to remove Matrix integration: {e}")
