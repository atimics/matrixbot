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
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ...tools.base import ActionContext

from ...config import settings
from ...core.ai_engine import AIDecisionEngine, ActionPlan
from ...core.history_recorder import HistoryRecorder
from ...core.integration_manager import IntegrationManager
from ...integrations.arweave_uploader_client import ArweaveUploaderClient
from ...integrations.farcaster import FarcasterObserver
from ..node_system.node_manager import NodeManager
from ..node_system.summary_service import NodeSummaryService
from ..node_system.interaction_tools import NodeInteractionTools
from ..processors.adaptive_processor import AdaptiveProcessor
from ...integrations.matrix.observer import MatrixObserver
from ...integrations.base_nft_service import BaseNFTService
from ...integrations.eligibility_service import UserEligibilityService
from ...tools.registry import ToolRegistry
from ..world_state.manager import WorldStateManager
from ..world_state.payload_builder import PayloadBuilder
from .processing_hub import ProcessingHub, ProcessingConfig
from .rate_limiter import RateLimiter, RateLimitConfig
from ..proactive import ProactiveConversationEngine
from ...integrations.matrix.health_monitor import MatrixHealthMonitor

logger = logging.getLogger(__name__)


class TraditionalProcessor:
    """
    Traditional AI processing wrapper that processes full payloads.
    
    This class acts as a bridge between the processing hub and the AI engine,
    handling the traditional full-payload processing approach.
    """
    
    def __init__(self, ai_engine, tool_registry, rate_limiter, history_recorder, action_context):
        self.ai_engine = ai_engine
        self.tool_registry = tool_registry
        self.rate_limiter = rate_limiter
        self.history_recorder = history_recorder
        self.action_context = action_context
        
    async def process_payload(self, payload: Dict[str, Any], active_channels: list) -> None:
        """
        Process a payload using the traditional approach.
        
        Args:
            payload: The world state payload to process
            active_channels: List of active channel IDs
        """
        try:
            # Add available tools to the payload
            payload["available_tools"] = self.tool_registry.get_tool_descriptions_for_ai()
            
            # Generate a cycle ID for this decision
            cycle_id = payload.get("cycle_id", f"cycle_{int(time.time() * 1000)}")
            
            # Get AI decision
            decision_result = await self.ai_engine.make_decision(payload, cycle_id)
            
            if not decision_result.selected_actions:
                logger.debug("No actions selected by AI")
                return
                
            # Execute selected actions
            for action in decision_result.selected_actions:
                try:
                    await self._execute_action(action)
                except Exception as e:
                    logger.error(f"Error executing action {action.action_type}: {e}")
                    
        except Exception as e:
            logger.error(f"Error in traditional processing: {e}")
            raise
            
    async def _execute_action(self, action: ActionPlan) -> None:
        """Execute a single action."""
        try:
            # Get the tool from registry
            tool = self.tool_registry.get_tool(action.action_type)
            if not tool:
                logger.error(f"Tool not found: {action.action_type}")
                return
                
            # Execute the tool with parameters and context
            result = await tool.execute(action.parameters, self.action_context)
            
            # Log the action result using HistoryRecorder directly
            from ...core.history_recorder import StateChangeBlock
            await self.history_recorder.record_state_change(StateChangeBlock(
                timestamp=time.time(),
                change_type="tool_result",
                source="tool",
                channel_id="system",
                observations=None,
                potential_actions=None,
                selected_actions=[{"tool": action.action_type, "result": str(result)[:1000]}],
                reasoning=f"Tool {action.action_type} executed: {action.reasoning}",
                raw_content={"tool": action.action_type, "result": result, "parameters": action.parameters},
            ))
            
        except Exception as e:
            logger.error(f"Error executing action {action.action_type}: {e}")
            # Log the failed action using HistoryRecorder directly
            from ...core.history_recorder import StateChangeBlock
            await self.history_recorder.record_state_change(StateChangeBlock(
                timestamp=time.time(),
                change_type="tool_result",
                source="tool",
                channel_id="system",
                observations=None,
                potential_actions=None,
                selected_actions=[{"tool": action.action_type, "error": str(e)[:1000]}],
                reasoning=f"Tool {action.action_type} failed: {action.reasoning}",
                raw_content={"tool": action.action_type, "error": str(e), "parameters": action.parameters},
            ))

    async def _execute_actions(self, actions: list) -> None:
        """
        Execute a list of actions with coordination logic.
        
        This method handles special coordination cases like injecting generated
        image URLs into posting actions.
        """
        # Track results from executed actions for coordination
        execution_results = {}
        
        # Sort actions by priority (higher priority first)
        sorted_actions = sorted(actions, key=lambda a: getattr(a, 'priority', 0), reverse=True)
        
        for action in sorted_actions:
            try:
                # Check for coordination opportunities
                if action.action_type in ["send_farcaster_post", "send_matrix_message"]:
                    # Check if we have a generated image to coordinate with
                    if "generate_image" in execution_results:
                        image_result = execution_results["generate_image"]
                        if image_result.get("status") == "success" and "embed_page_url" in image_result:
                            # Inject the embed URL into the posting action
                            action.parameters["embed_url"] = image_result["embed_page_url"]
                
                # Execute the action
                result = await self._execute_action_and_return_result(action)
                execution_results[action.action_type] = result
                
            except Exception as e:
                logger.error(f"Error executing action {action.action_type}: {e}")
                execution_results[action.action_type] = {"status": "error", "error": str(e)}
    
    async def _execute_action_and_return_result(self, action: ActionPlan) -> dict:
        """Execute a single action and return the result for coordination."""
        try:
            # Get the tool from registry
            tool = self.tool_registry.get_tool(action.action_type)
            if not tool:
                logger.error(f"Tool not found: {action.action_type}")
                return {"status": "error", "error": f"Tool not found: {action.action_type}"}
                
            # Execute the tool with parameters and context
            result = await tool.execute(action.parameters, self.action_context)
            
            # Log the action result using HistoryRecorder directly
            from ...core.history_recorder import StateChangeBlock
            await self.history_recorder.record_state_change(StateChangeBlock(
                timestamp=time.time(),
                change_type="tool_result",
                source="tool",
                channel_id="system",
                observations=None,
                potential_actions=None,
                selected_actions=[{"tool": action.action_type, "result": str(result)[:1000]}],
                reasoning=f"Tool {action.action_type} executed and returned: {action.reasoning}",
                raw_content={"tool": action.action_type, "result": result, "parameters": action.parameters},
            ))
            
            return result
            
        except Exception as e:
            logger.error(f"Error executing action {action.action_type}: {e}")
            # Log the failed action using HistoryRecorder directly
            from ...core.history_recorder import StateChangeBlock
            await self.history_recorder.record_state_change(StateChangeBlock(
                timestamp=time.time(),
                change_type="tool_result",
                source="tool",
                channel_id="system",
                observations=None,
                potential_actions=None,
                selected_actions=[{"tool": action.action_type, "error": str(e)[:1000]}],
                reasoning=f"Tool {action.action_type} failed and returned error: {action.reasoning}",
                raw_content={"tool": action.action_type, "error": str(e), "parameters": action.parameters},
            ))
            return {"status": "error", "error": str(e)}

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
    2. Coordinates between different subsystems
    3. Manages external observers (Matrix, Farcaster)
    4. Provides unified system status and control
    
    Dependencies are injected via constructor to enable clean testing and DI.
    """
    
    def __init__(
        self,
        config: Optional[OrchestratorConfig] = None,
        # Core dependencies (injected by DI container)
        world_state_manager: Optional[WorldStateManager] = None,
        history_recorder: Optional[HistoryRecorder] = None,
        integration_manager: Optional[IntegrationManager] = None,
        ai_engine: Optional[AIDecisionEngine] = None,
        payload_builder: Optional[PayloadBuilder] = None,
        processing_hub: Optional[ProcessingHub] = None,
        rate_limiter: Optional[RateLimiter] = None,
        proactive_engine: Optional[ProactiveConversationEngine] = None,
        tool_registry: Optional[ToolRegistry] = None,
        action_context: Optional['ActionContext'] = None,
        arweave_client: Optional[ArweaveUploaderClient] = None,
    ):
        self.config = config or OrchestratorConfig()
        
        
        # DI mode - use all injected dependencies
        if not all([world_state_manager, history_recorder, integration_manager, 
                    ai_engine, payload_builder, processing_hub, rate_limiter, 
                    proactive_engine, tool_registry, action_context]):
            raise ValueError("In DI mode, all core dependencies must be provided")
        
        self.world_state = world_state_manager
        self.history_recorder = history_recorder
        self.integration_manager = integration_manager
        self.ai_engine = ai_engine
        self.payload_builder = payload_builder
        self.processing_hub = processing_hub
        self.rate_limiter = rate_limiter
        self.proactive_engine = proactive_engine
        self.tool_registry = tool_registry
        self.action_context = action_context
        self.arweave_client = arweave_client
        
        logger.info("MainOrchestrator initialized with dependency injection")
        logger.info("Commander/Sub-Agent architecture will be used")
        
        # NFT and eligibility services
        self.base_nft_service: Optional[BaseNFTService] = None
        self.eligibility_service: Optional[UserEligibilityService] = None
        
        # System state
        self.running = False
        self.cycle_count = 0  # Track processing cycles
        
            
        # Initialize node-based processing system (depends on core components being set)
        self._initialize_node_system()
    

    def _register_all_tools(self):
        """Register all available tools with the tool registry."""
        if not self.tool_registry:
            logger.warning("Tool registry not available - skipping tool registration")
            return
        from ...tools.core_tools import WaitTool, SetMissionGoalTool, UpdateMissionStatusTool
        from ...tools.describe_image_tool import DescribeImageTool
        from ...tools.farcaster import (
            FollowFarcasterUserTool,
            GetUserTimelineTool,
            LikeFarcasterPostTool,
            SendFarcasterPostTool,
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
        from ...tools.matrix import (
            AcceptMatrixInviteTool,
            IgnoreMatrixInviteTool,
            JoinMatrixRoomTool,
            LeaveMatrixRoomTool,
            ReactToMatrixMessageTool,
            SendMatrixImageTool,
            SendMatrixMessageTool,
            SendMatrixVideoTool,
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
        from ...tools.proactive_conversation_tools import (
            InitiateProactiveConversationTool,
            DetectConversationOpportunitiesTool,
            ScheduleProactiveEngagementTool,
            GetProactiveEngagementStatusTool
        )
        # Node management tools (unified execution pipeline)
        from ...tools.node_tools import (
            ExpandNodeTool,
            CollapseNodeTool,
            PinNodeTool,
            UnpinNodeTool,
            RefreshSummaryTool,
            GetExpansionStatusTool
        )
        
        # Core tools
        self.tool_registry.register_tool(WaitTool())
        self.tool_registry.register_tool(DescribeImageTool())
        
        # P1 FEATURE: Mission/Goal management tools
        self.tool_registry.register_tool(SetMissionGoalTool())
        self.tool_registry.register_tool(UpdateMissionStatusTool())
        
        # Node management tools (register early for priority in node-based processing)
        self.tool_registry.register_tool(ExpandNodeTool())
        self.tool_registry.register_tool(CollapseNodeTool())
        self.tool_registry.register_tool(PinNodeTool())
        self.tool_registry.register_tool(UnpinNodeTool())
        self.tool_registry.register_tool(RefreshSummaryTool())
        self.tool_registry.register_tool(GetExpansionStatusTool())
        
        # Web search and research tools
        self.tool_registry.register_tool(WebSearchTool())
        self.tool_registry.register_tool(UpdateResearchTool())
        self.tool_registry.register_tool(QueryResearchTool())
        
        # Matrix tools (consolidated - SendMatrixMessageTool now handles both messages and replies)
        self.tool_registry.register_tool(SendMatrixMessageTool())
        # NOTE: SendMatrixReplyTool deprecated - use send_matrix_message with reply_to_id parameter
        # self.tool_registry.register_tool(SendMatrixReplyTool())  # DEPRECATED - functionality consolidated into SendMatrixMessageTool
        self.tool_registry.register_tool(SendMatrixImageTool())
        self.tool_registry.register_tool(SendMatrixVideoTool())
        self.tool_registry.register_tool(ReactToMatrixMessageTool())
        self.tool_registry.register_tool(JoinMatrixRoomTool())
        self.tool_registry.register_tool(LeaveMatrixRoomTool())
        self.tool_registry.register_tool(AcceptMatrixInviteTool())
        self.tool_registry.register_tool(IgnoreMatrixInviteTool())
        
        # Farcaster tools (consolidated - SendFarcasterPostTool now handles both posts and replies)
        self.tool_registry.register_tool(SendFarcasterPostTool())
        # NOTE: SendFarcasterReplyTool deprecated - use send_farcaster_post with reply_to_hash parameter
        # self.tool_registry.register_tool(SendFarcasterReplyTool())  # DEPRECATED - functionality consolidated into SendFarcasterPostTool
        # NOTE: SendFarcasterDMTool deprecated - functionality not currently available
        self.tool_registry.register_tool(LikeFarcasterPostTool())
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
            # Initialize database manager (for centralized database operations)
            if hasattr(self, 'database_manager'):
                await self.database_manager.initialize()
                logger.info("DatabaseManager initialized for persistent cache operations")
            
            # Initialize integration manager
            await self.integration_manager.initialize()
            
            # Register integrations from environment variables
            await self._register_integrations_from_env()
            
            # Connect all active integrations from database
            await self.integration_manager.connect_all()
            
            # Update action context with properly connected integrations
            await self._update_action_context_integrations()
            
            # NEW: Perform authoritative state sync for Farcaster replies
            await self._perform_startup_state_sync()
            
            # Ensure the media gallery channel exists or create it
            await self._ensure_media_gallery_exists()
            
            # Initialize NFT and blockchain services
            await self._initialize_nft_services()
            
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
        
        # Disconnect all integrations
        await self.integration_manager.disconnect_all()
        
        # Clean up integration manager resources
        await self.integration_manager.cleanup()

        logger.info("Main orchestrator system stopped")

    async def _initialize_nft_services(self) -> None:
        """Initialize NFT and blockchain services if credentials are available."""
        try:
            # Initialize Base NFT service
            if (settings.base_rpc_url and 
                settings.nft_dev_wallet_private_key and 
                settings.nft_collection_address_base):
                
                self.base_nft_service = BaseNFTService()
                
                # Initialize the service
                if await self.base_nft_service.initialize():
                    logger.info("Base NFT service initialized successfully")
                    
                    # Initialize eligibility service if we have Farcaster integration
                    if (settings.ecosystem_token_contract_address and 
                        self.integration_manager):
                        
                        # Get active integrations to find Farcaster
                        active_integrations = self.integration_manager.get_active_integrations()
                        farcaster_integration = None
                        for integration_id, integration in active_integrations.items():
                            if hasattr(integration, 'integration_type') and integration.integration_type == 'farcaster':
                                farcaster_integration = integration
                                break
                        
                        if farcaster_integration and hasattr(farcaster_integration, 'neynar_api_client'):
                            self.eligibility_service = UserEligibilityService(
                                neynar_api_client=farcaster_integration.neynar_api_client,
                                base_nft_service=self.base_nft_service,
                                world_state_manager=self.world_state
                            )
                            await self.eligibility_service.start()
                            logger.info("User eligibility service started")
                            
                            # Update action context with NFT services
                            if hasattr(self.action_context, 'base_nft_service'):
                                self.action_context.base_nft_service = self.base_nft_service
                            if hasattr(self.action_context, 'eligibility_service'):
                                self.action_context.eligibility_service = self.eligibility_service
                        else:
                            logger.info("Eligibility service not started - Farcaster integration not available")
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



    async def _update_action_context_integrations(self) -> None:
        """Update action context with properly connected integrations from IntegrationManager."""
        # Update action context with initialized integrations
        active_integrations = self.integration_manager.get_active_integrations()
        
        # Find Matrix and Farcaster integrations
        matrix_integration = None
        farcaster_integration = None
        
        for integration_id, integration in active_integrations.items():
            if hasattr(integration, 'integration_type') and integration.integration_type == 'matrix':
                matrix_integration = integration
            elif hasattr(integration, 'integration_type') and integration.integration_type == 'farcaster':
                farcaster_integration = integration
        
        # CRITICAL: Register integrations with ServiceRegistry for service abstraction
        if matrix_integration and self.action_context and self.action_context.service_registry:
            self.action_context.service_registry.register_service("matrix_observer", matrix_integration)
            logger.info(f"✓ Matrix integration registered with ServiceRegistry")
        
        if farcaster_integration and self.action_context and self.action_context.service_registry:
            self.action_context.service_registry.register_service("farcaster_observer", farcaster_integration)
            logger.info(f"✓ Farcaster integration registered with ServiceRegistry")
        
        # Also register storage services if available
        if (self.action_context and self.action_context.service_registry and 
            hasattr(self.action_context, 'arweave_service') and self.action_context.arweave_service):
            self.action_context.service_registry.register_service("arweave_storage", self.action_context.arweave_service)
            logger.debug("Arweave service registered with ServiceRegistry")
        
        if (self.action_context and self.action_context.service_registry and
            hasattr(self.action_context, 's3_service') and self.action_context.s3_service):
            self.action_context.service_registry.register_service("s3_storage", self.action_context.s3_service)
            logger.debug("S3 service registered with ServiceRegistry")
        
        # Debug logging to track which integration is being used
        if farcaster_integration:
            logger.info(f"✓ Using Farcaster integration from IntegrationManager (ID: {farcaster_integration.integration_id})")
            if hasattr(farcaster_integration, 'api_client'):
                logger.info(f"  API client initialized: {farcaster_integration.api_client is not None}")
        else:
            logger.info("ℹ No Farcaster integration available")

    def _configure_critical_node_pinning(self):
        """Configure critical node paths for pinning based on active integrations."""
        critical_pins = []
        
        # Get active integrations to determine which pins to configure
        if self.integration_manager:
            active_integrations = self.integration_manager.get_active_integrations()
            
            # Add Matrix room if available
            matrix_integration = None
            for integration_id, integration in active_integrations.items():
                if hasattr(integration, 'integration_type') and integration.integration_type == 'matrix':
                    matrix_integration = integration
                    break
                    
            if matrix_integration and settings.matrix.room_id:
                critical_pins.append(f"channels.matrix.{settings.matrix.room_id}")
                logger.info(f"Added Matrix room to critical pins: channels.matrix.{settings.matrix.room_id}")
            
            # Add Farcaster feeds if available
            farcaster_integration = None
            for integration_id, integration in active_integrations.items():
                if hasattr(integration, 'integration_type') and integration.integration_type == 'farcaster':
                    farcaster_integration = integration
                    break
                    
            if farcaster_integration:
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
        # Next, check if ProcessingHub's commander_processor has a node_manager
        elif (self.processing_hub and self.processing_hub.commander_processor and 
              hasattr(self.processing_hub.commander_processor, 'node_manager') and 
              self.processing_hub.commander_processor.node_manager):
            node_manager = self.processing_hub.commander_processor.node_manager
            logger.debug("Using ProcessingHub's commander_processor NodeManager for critical pinning")
        
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
            # Get integration status from IntegrationManager
            matrix_integration = None
            farcaster_integration = None
            
            if self.integration_manager:
                active_integrations = self.integration_manager.get_active_integrations()
                for integration_id, integration in active_integrations.items():
                    if hasattr(integration, 'integration_type') and integration.integration_type == 'matrix':
                        matrix_integration = integration
                    elif hasattr(integration, 'integration_type') and integration.integration_type == 'farcaster':
                        farcaster_integration = integration
            
            integrations = {
                "matrix": {
                    "connected": matrix_integration is not None and getattr(matrix_integration, 'connected', False),
                    "monitored_rooms": getattr(matrix_integration, 'channels_to_monitor', []) if matrix_integration else [],
                    "pending_invites": len(self.world_state.get_pending_matrix_invites()) if self.world_state else 0
                },
                "farcaster": {
                    "connected": farcaster_integration is not None,
                    "bot_fid": settings.farcaster.bot_fid,
                    "post_queue_size": getattr(farcaster_integration, 'post_queue_size', 0) if farcaster_integration else 0,
                    "reply_queue_size": getattr(farcaster_integration, 'reply_queue_size', 0) if farcaster_integration else 0
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
                    "processing_mode": "sub_agent" if self.config.processing_config.enable_sub_agent_processing else "traditional",
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
            await self.processing_hub.traditional_processor._execute_action(action)
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
            from ...tools.matrix import SendMatrixMessageTool
            
            # Get matrix integration from integration manager
            matrix_integration = None
            if self.integration_manager:
                active_integrations = self.integration_manager.get_active_integrations()
                for integration_id, integration in active_integrations.items():
                    if hasattr(integration, 'integration_type') and integration.integration_type == 'matrix':
                        matrix_integration = integration
                        break
            
            if not matrix_integration:
                logger.error("No Matrix integration available for direct action execution")
                return
            
            # Update action context with required components
            if self.action_context:
                if hasattr(self.action_context, 'matrix_observer'):
                    self.action_context.matrix_observer = matrix_integration
                if hasattr(self.action_context, 'world_state_manager'):
                    self.action_context.world_state_manager = self.world_state
                # Note: ActionContext.context_manager is deprecated, leaving as None
                
                # Use unified SendMatrixMessageTool for both messages and replies
                if action.action_type in ["send_matrix_reply", "send_matrix_message"]:
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
            # Get world state data
            world_state_data = self.world_state.get_state_data()
            
            # Use PayloadBuilder to construct context instead of deprecated ContextManager
            from chatbot.config import settings
            config = {
                "optimize_for_size": True,
                "include_detailed_user_info": settings.ai_include_detailed_user_info,
                "max_messages_per_channel": settings.ai_conversation_history_length,
                "max_action_history": settings.ai_action_history_length,
                "bot_fid": settings.farcaster.bot_fid,
                "bot_username": settings.farcaster.bot_username,
            }
            
            # Build payload using PayloadBuilder
            payload_builder = self.world_state.payload_builder
            payload = payload_builder.build_full_payload(
                world_state_data=world_state_data,
                primary_channel_id=channel_id,
                config=config
            )
            
            # Process using traditional processor
            await self.process_payload(payload, [channel_id])
            
        except Exception as e:
            logger.error(f"Error processing channel {channel_id}: {e}")

    async def add_user_message(self, channel_id: str, message_data: Dict[str, Any]) -> None:
        """Add a user message to the context using HistoryRecorder."""
        # Store the message directly using HistoryRecorder
        from ...core.history_recorder import StateChangeBlock
        import time
        
        await self.history_recorder.record_state_change(StateChangeBlock(
            timestamp=time.time(),
            change_type="user_message",
            source="user",
            channel_id=channel_id,
            observations=None,
            potential_actions=None,
            selected_actions=None,
            reasoning=None,
            raw_content=message_data,
        ))

    async def get_context_summary(self, channel_id: str) -> Optional[Dict[str, Any]]:
        """Get context summary for a channel using HistoryRecorder directly."""
        try:
            # Access HistoryRecorder directly instead of through deprecated ContextManager methods
            recent_changes = await self.history_recorder.get_recent_state_changes(
                channel_id=channel_id, 
                limit=50
            )
            
            return {
                "channel_id": channel_id,
                "recent_state_changes": len(recent_changes),
                "message": "Context summary based on HistoryRecorder data. Use PayloadBuilder for AI context construction."
            }
        except Exception as e:
            logger.error(f"Error getting context summary for {channel_id}: {e}")
            return None

    async def clear_context(self, channel_id: str) -> None:
        """Clear context for a channel - deprecated since ContextManager no longer stores contexts."""
        logger.warning(f"clear_context called for {channel_id} - this is deprecated since ContextManager is stateless now")
        # No-op since ContextManager no longer stores contexts in memory

    async def _ensure_media_gallery_exists(self) -> None:
        """Check for, create, and configure the media gallery room."""
        if settings.matrix.media_gallery_room_id:
            logger.info(f"Matrix media gallery is configured: {settings.matrix.media_gallery_room_id}")
            return

        config_path = Path("data/config.json")
        if config_path.exists():
            try:
                with open(config_path, 'r') as f:
                    config_data = json.load(f)
                    gallery_id = config_data.get("MATRIX_MEDIA_GALLERY_ROOM_ID")
                    if gallery_id:
                        # Note: Can't directly set nested config, would need to update config.json
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
                # Note: Can't directly set nested config, updating config.json instead

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
        
        # Debug log the Farcaster settings
        logger.info(f"Farcaster settings check:")
        logger.info(f"  neynar_api_key: {'SET' if settings.farcaster.neynar_api_key else 'NOT SET'}")
        logger.info(f"  bot_fid: {'SET' if settings.farcaster.bot_fid else 'NOT SET'}")
        logger.info(f"  bot_signer_uuid: {'SET' if settings.farcaster.bot_signer_uuid else 'NOT SET'}")
        
        # Check for Farcaster integration
        if (settings.farcaster.neynar_api_key and 
            settings.farcaster.bot_fid and 
            settings.farcaster.bot_signer_uuid):
            
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
                            'username': settings.farcaster.bot_username or 'farcaster_bot'
                        },
                        credentials={
                            'api_key': settings.farcaster.neynar_api_key,
                            'bot_fid': settings.farcaster.bot_fid,
                            'signer_uuid': settings.farcaster.bot_signer_uuid
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
                                'api_key': settings.farcaster.neynar_api_key,
                                'bot_fid': settings.farcaster.bot_fid,
                                'signer_uuid': settings.farcaster.bot_signer_uuid
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
        if (settings.matrix.homeserver and 
            settings.matrix.user_id and 
            settings.matrix.password):
            
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
                            'room_id': settings.matrix.room_id,
                            'device_name': settings.matrix.device_name
                        },
                        credentials={
                            'homeserver': settings.matrix.homeserver,
                            'user_id': settings.matrix.user_id,
                            'password': settings.matrix.password
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
                                'homeserver': settings.matrix.homeserver,
                                'user_id': settings.matrix.user_id,
                                'password': settings.matrix.password
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
    
    def _initialize_node_system(self):
        """Initialize the Commander/Sub-Agent processing system with node-based context management."""
        logger.info("Initializing Commander/Sub-Agent processing system...")
        
        # Ensure required dependencies are available
        if not self.ai_engine:
            raise RuntimeError("AI engine is required for node system initialization")
        if not self.world_state:
            raise RuntimeError("World state manager is required for node system initialization")  
        if not self.payload_builder:
            raise RuntimeError("Payload builder is required for node system initialization")
        if not self.tool_registry:
            raise RuntimeError("Tool registry is required for node system initialization")
        if not self.processing_hub:
            raise RuntimeError("Processing hub is required for node system initialization")
        
        # Initialize NodeManager with LRU and metadata management
        self.node_manager = NodeManager(
            max_expanded_nodes=settings.processing.max_expanded_nodes,
            default_pinned_nodes=settings.processing.default_pinned_nodes
        )
        
        # Initialize NodeSummaryService for AI summarization
        api_key = settings.processing.openrouter_api_key
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY is required for node summary service")
        
        self.node_summary_service = NodeSummaryService(
            api_key=api_key,
            model=settings.processing.ai_summary_model
        )
        
        # Initialize NodeInteractionTools for AI node operations
        self.node_interaction_tools = NodeInteractionTools(self.node_manager)
        
        # Initialize AdaptiveProcessor (Commander AI) with strategic decision making
        self.commander_processor = AdaptiveProcessor(
            node_manager=self.node_manager,
            summary_service=self.node_summary_service,
            ai_engine=self.ai_engine,
            world_state_manager=self.world_state,
            payload_builder=self.payload_builder,
            tool_registry=self.tool_registry,
            action_context=self.action_context
        )
        
        # Connect AdaptiveProcessor (Commander AI) to ProcessingHub
        self.processing_hub.set_commander_processor(self.commander_processor)
        
        # CRITICAL FIX: Connect NodeManager to WorldStateManager so tools can access it
        self.world_state.node_manager = self.node_manager
        logger.info("NodeManager connected to WorldStateManager for tool access")
        
        # Update ActionContext with the node_manager after initialization
        self._update_action_context_with_node_manager()
        
        logger.info("Commander/Sub-Agent processing system initialized successfully")

    def _update_action_context_with_node_manager(self):
        """Update ActionContext to include the node_manager for node tools."""
        if self.action_context and self.node_manager:
            # Add node_manager to the ActionContext
            self.action_context.node_manager = self.node_manager
            logger.info("ActionContext updated with node_manager")
        else:
            logger.warning("Could not update ActionContext with node_manager - missing dependencies")
    
    async def _perform_startup_state_sync(self) -> None:
        """
        Perform authoritative state sync with external platforms on startup.
        
        This ensures the bot's persistent state is consistent with the actual
        state on the platforms, preventing duplicate actions after restarts.
        """
        logger.info("Performing startup state synchronization...")
        
        # Sync Farcaster reply history
        if self.farcaster_observer and self.action_context and self.action_context.database_manager:
            try:
                synced_count = await self.farcaster_observer.sync_reply_history(self.action_context.database_manager)
                logger.info(f"Farcaster state sync completed: {synced_count} replies synced")
            except Exception as e:
                logger.error(f"Failed to sync Farcaster reply history: {e}", exc_info=True)
        else:
            logger.debug("Skipping Farcaster state sync: observer or database manager not available")
        
        # Future: Add Matrix state sync here if needed
        # if self.matrix_observer and self.action_context and self.action_context.database_manager:
        #     await self.matrix_observer.sync_message_history(self.action_context.database_manager)
        
        logger.info("Startup state synchronization completed")


