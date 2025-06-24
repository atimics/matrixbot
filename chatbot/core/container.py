"""
Dependency Injection Container

This module provides centralized dependency management for the entire application.
It replaces manual component initialization throughout the codebase with a clean,
testable dependency injection pattern.
"""

import logging
from typing import Optional, Dict, Any, TYPE_CHECKING
from pathlib import Path

if TYPE_CHECKING:
    from .orchestration.main_orchestrator import OrchestratorConfig

from ..config import settings
from ..utils.logging_utils import get_colored_logger
from .persistence import DatabaseManager
from .ai_engine import AIDecisionEngine
from .context import ContextManager
from .integration_manager import IntegrationManager
from .world_state.manager import WorldStateManager
from .world_state.payload_builder import PayloadBuilder
from .orchestration.processing_hub import ProcessingHub, ProcessingConfig
from .orchestration.rate_limiter import RateLimiter, RateLimitConfig
from .proactive import ProactiveConversationEngine
from ..tools.registry import ToolRegistry
from ..tools.base import ActionContext
from ..tools.arweave_service import ArweaveService
from ..tools.s3_service import S3Service
from ..integrations.arweave_uploader_client import ArweaveUploaderClient

logger = get_colored_logger(__name__)


class DependencyContainer:
    """
    Centralized dependency injection container.
    
    This container is responsible for:
    1. Creating and configuring all core system components
    2. Managing component lifecycle (initialization/cleanup)
    3. Providing dependency injection for the orchestrator and other components
    4. Ensuring components are properly connected and configured
    """
    
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or settings.chatbot_db_path
        
        # Core infrastructure
        self._database_manager: Optional[DatabaseManager] = None
        self._world_state_manager: Optional[WorldStateManager] = None
        self._context_manager: Optional[ContextManager] = None
        self._integration_manager: Optional[IntegrationManager] = None
        
        # AI and processing
        self._ai_engine: Optional[AIDecisionEngine] = None
        self._payload_builder: Optional[PayloadBuilder] = None
        self._processing_hub: Optional[ProcessingHub] = None
        self._rate_limiter: Optional[RateLimiter] = None
        self._proactive_engine: Optional[ProactiveConversationEngine] = None
        
        # Tools and services
        self._tool_registry: Optional[ToolRegistry] = None
        self._action_context: Optional[ActionContext] = None
        self._arweave_client: Optional[ArweaveUploaderClient] = None
        
        # Initialization state
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize all dependencies in the correct order."""
        if self._initialized:
            logger.warning("DependencyContainer already initialized")
            return
        
        try:
            logger.info("Initializing DependencyContainer...")
            
            # 1. Initialize core infrastructure first
            await self._init_database_manager()
            self._init_world_state_manager()
            self._init_context_manager()
            self._init_integration_manager()
            
            # 2. Initialize tool system first (needed by processing components)
            self._init_arweave_client()
            self._init_action_context()
            self._init_tool_registry()
            
            # 3. Initialize AI and processing components
            self._init_ai_engine()
            self._init_payload_builder()
            self._init_rate_limiter()
            self._init_processing_hub()
            self._init_proactive_engine()
            
            # 4. Validate startup requirements
            await self._validate_startup_requirements()
            
            self._initialized = True
            logger.info("DependencyContainer initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize DependencyContainer: {e}")
            await self.cleanup()
            raise
    
    async def cleanup(self) -> None:
        """Clean up all managed dependencies."""
        logger.info("Cleaning up DependencyContainer...")
        
        # Cleanup in reverse order of initialization
        if self._integration_manager:
            await self._integration_manager.cleanup()
        
        if self._database_manager:
            await self._database_manager.close()
        
        # Reset all references
        self._database_manager = None
        self._world_state_manager = None
        self._context_manager = None
        self._integration_manager = None
        self._ai_engine = None
        self._payload_builder = None
        self._processing_hub = None
        self._rate_limiter = None
        self._proactive_engine = None
        self._tool_registry = None
        self._action_context = None
        self._arweave_client = None
        
        self._initialized = False
        logger.info("DependencyContainer cleanup complete")
    
    # Core Infrastructure Getters
    @property
    def database_manager(self) -> DatabaseManager:
        """Get the database manager instance."""
        if not self._database_manager:
            raise RuntimeError("DatabaseManager not initialized")
        return self._database_manager
    
    @property
    def world_state_manager(self) -> WorldStateManager:
        """Get the world state manager instance."""
        if not self._world_state_manager:
            raise RuntimeError("WorldStateManager not initialized")
        return self._world_state_manager
    
    @property
    def context_manager(self) -> ContextManager:
        """Get the context manager instance."""
        if not self._context_manager:
            raise RuntimeError("ContextManager not initialized")
        return self._context_manager
    
    @property
    def integration_manager(self) -> IntegrationManager:
        """Get the integration manager instance."""
        if not self._integration_manager:
            raise RuntimeError("IntegrationManager not initialized")
        return self._integration_manager
    
    # AI and Processing Getters
    @property
    def ai_engine(self) -> AIDecisionEngine:
        """Get the AI engine instance."""
        if not self._ai_engine:
            raise RuntimeError("AIDecisionEngine not initialized")
        return self._ai_engine
    
    @property
    def payload_builder(self) -> PayloadBuilder:
        """Get the payload builder instance."""
        if not self._payload_builder:
            raise RuntimeError("PayloadBuilder not initialized")
        return self._payload_builder
    
    @property
    def processing_hub(self) -> ProcessingHub:
        """Get the processing hub instance."""
        if not self._processing_hub:
            raise RuntimeError("ProcessingHub not initialized")
        return self._processing_hub
    
    @property
    def rate_limiter(self) -> RateLimiter:
        """Get the rate limiter instance."""
        if not self._rate_limiter:
            raise RuntimeError("RateLimiter not initialized")
        return self._rate_limiter
    
    @property
    def proactive_engine(self) -> ProactiveConversationEngine:
        """Get the proactive conversation engine instance."""
        if not self._proactive_engine:
            raise RuntimeError("ProactiveConversationEngine not initialized")
        return self._proactive_engine
    
    # Tools and Services Getters
    @property
    def tool_registry(self) -> ToolRegistry:
        """Get the tool registry instance."""
        if not self._tool_registry:
            raise RuntimeError("ToolRegistry not initialized")
        return self._tool_registry
    
    @property
    def action_context(self) -> ActionContext:
        """Get the action context instance."""
        if not self._action_context:
            raise RuntimeError("ActionContext not initialized")
        return self._action_context
    
    # Private initialization methods
    async def _init_database_manager(self) -> None:
        """Initialize the database manager."""
        self._database_manager = DatabaseManager(self.db_path)
        await self._database_manager.initialize()
        logger.debug("DatabaseManager initialized")
    
    def _init_world_state_manager(self) -> None:
        """Initialize the world state manager."""
        self._world_state_manager = WorldStateManager()
        logger.debug("WorldStateManager initialized")
    
    def _init_context_manager(self) -> None:
        """Initialize the context manager."""
        assert self._world_state_manager is not None, "WorldStateManager must be initialized first"
        self._context_manager = ContextManager(
            world_state_manager=self._world_state_manager,
            db_path=self.db_path
        )
        logger.debug("ContextManager initialized")
    
    def _init_integration_manager(self) -> None:
        """Initialize the integration manager."""
        self._integration_manager = IntegrationManager(
            db_path=self.db_path,
            encryption_key=settings.security.ratichat_encryption_key,
            world_state_manager=self._world_state_manager
        )
        logger.debug("IntegrationManager initialized")
    
    def _init_ai_engine(self) -> None:
        """Initialize the AI engine."""
        if not settings.processing.openrouter_api_key:
            logger.warning("OPENROUTER_API_KEY not set - AI engine may not function properly")
            raise ValueError("OPENROUTER_API_KEY is required for AI engine initialization")
        
        self._ai_engine = AIDecisionEngine(
            api_key=settings.processing.openrouter_api_key,
            model=settings.processing.ai_model
        )
        logger.debug("AIDecisionEngine initialized")
    
    def _init_payload_builder(self) -> None:
        """Initialize the payload builder."""
        self._payload_builder = PayloadBuilder()
        logger.debug("PayloadBuilder initialized")
    
    def _init_rate_limiter(self) -> None:
        """Initialize the rate limiter."""
        rate_limit_config = RateLimitConfig(
            max_cycles_per_hour=settings.processing.max_cycles_per_hour
        )
        self._rate_limiter = RateLimiter(rate_limit_config)
        logger.debug("RateLimiter initialized")
    
    def _init_processing_hub(self) -> None:
        """Initialize the processing hub."""
        processing_config = ProcessingConfig(
            observation_interval=settings.processing.observation_interval,
            max_cycles_per_hour=settings.processing.max_cycles_per_hour,
            enable_sub_agent_processing=True  # Enable advanced processing by default
        )
        
        assert self._world_state_manager is not None, "WorldStateManager must be initialized first"
        assert self._payload_builder is not None, "PayloadBuilder must be initialized first"
        assert self._rate_limiter is not None, "RateLimiter must be initialized first"
        assert self._action_context is not None, "ActionContext must be initialized first"
        
        self._processing_hub = ProcessingHub(
            world_state_manager=self._world_state_manager,
            payload_builder=self._payload_builder,
            rate_limiter=self._rate_limiter,
            config=processing_config,
            tool_registry=self._tool_registry,
            action_context=self._action_context
        )
        
        # Configure Commander/Sub-Agent architecture
        self._configure_commander_sub_agent_architecture()
        
        logger.debug("ProcessingHub initialized")
    
    def _configure_commander_sub_agent_architecture(self) -> None:
        """Configure the Commander AI and Sub-Agent components."""
        try:
            # Ensure all required components are available
            assert self._processing_hub is not None, "ProcessingHub must be initialized first"
            assert self._ai_engine is not None, "AIDecisionEngine must be initialized first"
            assert self._world_state_manager is not None, "WorldStateManager must be initialized first"
            assert self._payload_builder is not None, "PayloadBuilder must be initialized first"
            assert self._tool_registry is not None, "ToolRegistry must be initialized first"
            assert self._action_context is not None, "ActionContext must be initialized first"
            
            # Check for required API key
            if not settings.processing.openrouter_api_key:
                raise ValueError("OPENROUTER_API_KEY is required for Commander/Sub-Agent architecture")
            
            # Initialize Lightweight AI Engine for Sub-Agents
            from .lightweight_ai_engine import LightweightAIEngine
            lightweight_ai = LightweightAIEngine(api_key=settings.processing.openrouter_api_key)
            self._processing_hub.set_lightweight_ai_engine(lightweight_ai)
            
            # Initialize Commander AI (AdaptiveProcessor)
            from .processors.adaptive_processor import AdaptiveProcessor
            from .node_system.node_manager import NodeManager
            from .node_system.summary_service import NodeSummaryService
            
            # Create node system components for Commander AI
            node_manager = NodeManager()
            summary_service = NodeSummaryService(
                api_key=settings.processing.openrouter_api_key,
                model=settings.processing.ai_summary_model
            )
            
            commander_ai = AdaptiveProcessor(
                node_manager=node_manager,
                summary_service=summary_service,
                ai_engine=self._ai_engine,
                world_state_manager=self._world_state_manager,
                payload_builder=self._payload_builder,
                tool_registry=self._tool_registry,
                action_context=self._action_context
            )
            self._processing_hub.set_commander_processor(commander_ai)
            
            logger.info("Commander/Sub-Agent architecture configured successfully")
            
        except Exception as e:
            logger.error(f"Failed to configure Commander/Sub-Agent architecture: {e}")
            # Continue with basic hub functionality
            logger.warning("ProcessingHub will operate without Commander/Sub-Agent features")
    
    def _init_proactive_engine(self) -> None:
        """Initialize the proactive conversation engine."""
        assert self._world_state_manager is not None, "WorldStateManager must be initialized first"
        assert self._context_manager is not None, "ContextManager must be initialized first"
        
        self._proactive_engine = ProactiveConversationEngine(
            world_state_manager=self._world_state_manager,
            context_manager=self._context_manager
        )
        
        # Connect proactive engine to world state manager for easy access
        # Note: This may be a dynamic attribute added by the orchestrator for legacy compatibility
        if hasattr(self._world_state_manager, 'proactive_engine'):
            self._world_state_manager.proactive_engine = self._proactive_engine  # type: ignore
        else:
            # Set it anyway for backwards compatibility
            setattr(self._world_state_manager, 'proactive_engine', self._proactive_engine)
        logger.debug("ProactiveConversationEngine initialized")
    
    def _init_arweave_client(self) -> None:
        """Initialize the Arweave client if configured."""
        if settings.storage.arweave_internal_uploader_service_url:
            self._arweave_client = ArweaveUploaderClient(
                uploader_service_url=settings.storage.arweave_internal_uploader_service_url,
                gateway_url=settings.storage.arweave_gateway_url,
            )
            logger.debug("ArweaveUploaderClient initialized")
        else:
            logger.debug("Arweave uploader service URL not configured, skipping ArweaveUploaderClient")
    
    def _init_action_context(self) -> None:
        """Initialize the action context for tool execution."""
        # Initialize service instances
        arweave_service = ArweaveService(arweave_client=self._arweave_client)
        s3_service = S3Service()
        
        # Initialize service registry
        from .services import ServiceRegistry
        service_registry = ServiceRegistry()
        
        # Register basic services
        service_registry.register_service("arweave_storage", arweave_service)
        service_registry.register_service("s3_storage", s3_service)
        
        self._action_context = ActionContext(
            world_state_manager=self._world_state_manager,
            context_manager=self._context_manager,
            service_registry=service_registry,
            # Legacy compatibility
            arweave_client=self._arweave_client,
            arweave_service=arweave_service,
            s3_service=s3_service
        )
        logger.debug("ActionContext initialized with ServiceRegistry")
    
    def _init_tool_registry(self) -> None:
        """Initialize the tool registry and register all tools."""
        self._tool_registry = ToolRegistry()
        self._register_all_tools()
        logger.debug("ToolRegistry initialized and tools registered")
    
    def _register_all_tools(self) -> None:
        """Register all available tools with the tool registry."""
        # Import tools here to avoid circular imports
        from ..tools.core_tools import WaitTool, AssignMissionTool, UpdateMissionStatusTool
        from ..tools.describe_image_tool import DescribeImageTool
        from ..tools.farcaster_tools import (
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
        from ..tools.matrix_tools import (
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
        from ..tools.media_generation_tools import GenerateImageTool, GenerateVideoTool
        from ..tools.permaweb_tools import StorePermanentMemoryTool
        from ..tools.web_tools import WebSearchTool
        from ..tools.research_tools import UpdateResearchTool, QueryResearchTool
        from ..tools.user_profiling_tools import (
            SentimentAnalysisTool,
            StoreUserMemoryTool,
            GetUserProfileTool
        )
        # Node management tools (unified execution pipeline)
        from ..tools.node_tools import (
            ExpandNodeTool,
            CollapseNodeTool,
            PinNodeTool,
            UnpinNodeTool,
            RefreshSummaryTool,
            GetExpansionStatusTool
        )
        
        # Ensure tool registry is initialized
        assert self._tool_registry is not None, "Tool registry must be initialized before registering tools"
        
        # Core tools
        self._tool_registry.register_tool(WaitTool())
        self._tool_registry.register_tool(DescribeImageTool())
        self._tool_registry.register_tool(AssignMissionTool())
        self._tool_registry.register_tool(UpdateMissionStatusTool())
        
        # Node management tools (register early for priority in node-based processing)
        self._tool_registry.register_tool(ExpandNodeTool())
        self._tool_registry.register_tool(CollapseNodeTool())
        self._tool_registry.register_tool(PinNodeTool())
        self._tool_registry.register_tool(UnpinNodeTool())
        self._tool_registry.register_tool(RefreshSummaryTool())
        self._tool_registry.register_tool(GetExpansionStatusTool())
        
        # Web search and research tools
        self._tool_registry.register_tool(WebSearchTool())
        self._tool_registry.register_tool(UpdateResearchTool())
        self._tool_registry.register_tool(QueryResearchTool())
        
        # Matrix tools (consolidated - SendMatrixMessageTool now handles both messages and replies)
        self._tool_registry.register_tool(SendMatrixMessageTool())
        # NOTE: SendMatrixReplyTool deprecated - use send_matrix_message with reply_to_id parameter
        # self._tool_registry.register_tool(SendMatrixReplyTool())  # DEPRECATED - functionality consolidated into SendMatrixMessageTool
        self._tool_registry.register_tool(SendMatrixImageTool())
        self._tool_registry.register_tool(SendMatrixVideoTool())
        self._tool_registry.register_tool(ReactToMatrixMessageTool())
        self._tool_registry.register_tool(JoinMatrixRoomTool())
        self._tool_registry.register_tool(LeaveMatrixRoomTool())
        self._tool_registry.register_tool(AcceptMatrixInviteTool())
        self._tool_registry.register_tool(IgnoreMatrixInviteTool())
        
        # Farcaster tools (consolidated - SendFarcasterPostTool now handles both posts and replies)
        self._tool_registry.register_tool(SendFarcasterPostTool())
        # NOTE: SendFarcasterReplyTool deprecated - use send_farcaster_post with reply_to_hash parameter
        # self._tool_registry.register_tool(SendFarcasterReplyTool())  # DEPRECATED - functionality consolidated into SendFarcasterPostTool
        self._tool_registry.register_tool(SendFarcasterDMTool())
        self._tool_registry.register_tool(LikeFarcasterPostTool())
        self._tool_registry.register_tool(QuoteFarcasterPostTool())
        self._tool_registry.register_tool(FollowFarcasterUserTool())
        self._tool_registry.register_tool(UnfollowFarcasterUserTool())
        self._tool_registry.register_tool(DeleteFarcasterPostTool())
        self._tool_registry.register_tool(DeleteFarcasterReactionTool())
        self._tool_registry.register_tool(GetUserTimelineTool())
        self._tool_registry.register_tool(SearchCastsTool())
        self._tool_registry.register_tool(GetTrendingCastsTool())
        self._tool_registry.register_tool(GetCastByUrlTool())
        self._tool_registry.register_tool(CollectWorldStateTool())
        
        # Media generation tools
        self._tool_registry.register_tool(GenerateImageTool())
        self._tool_registry.register_tool(GenerateVideoTool())
        
        # Permaweb tools
        self._tool_registry.register_tool(StorePermanentMemoryTool())
        
        # User Profiling tools
        self._tool_registry.register_tool(SentimentAnalysisTool())
        self._tool_registry.register_tool(StoreUserMemoryTool())
        self._tool_registry.register_tool(GetUserProfileTool())
        
        tool_stats = self._tool_registry.get_tool_stats()
        logger.info(f"Registered {tool_stats['total_tools']} tools ({tool_stats['enabled_tools']} enabled)")
    
    # Convenience methods for creating configured components
    def create_main_orchestrator(self, config: Optional['OrchestratorConfig'] = None):
        """Create a MainOrchestrator with all dependencies injected."""
        if not self._initialized:
            raise RuntimeError("DependencyContainer must be initialized before creating components")
        
        # Import here to avoid circular imports
        from .orchestration.main_orchestrator import MainOrchestrator, OrchestratorConfig
        
        # Use provided config or create a default one
        orchestrator_config = config or OrchestratorConfig(db_path=self.db_path)
        
        # Ensure all required dependencies are initialized
        assert self._world_state_manager is not None, "WorldStateManager not initialized"
        assert self._context_manager is not None, "ContextManager not initialized"
        assert self._integration_manager is not None, "IntegrationManager not initialized"
        assert self._ai_engine is not None, "AIDecisionEngine not initialized"
        assert self._payload_builder is not None, "PayloadBuilder not initialized"
        assert self._processing_hub is not None, "ProcessingHub not initialized"
        assert self._rate_limiter is not None, "RateLimiter not initialized"
        assert self._proactive_engine is not None, "ProactiveConversationEngine not initialized"
        assert self._tool_registry is not None, "ToolRegistry not initialized"
        assert self._action_context is not None, "ActionContext not initialized"
        
        # Create orchestrator with dependency injection
        orchestrator = MainOrchestrator(
            config=orchestrator_config,
            world_state_manager=self._world_state_manager,
            context_manager=self._context_manager,
            integration_manager=self._integration_manager,
            ai_engine=self._ai_engine,
            payload_builder=self._payload_builder,
            processing_hub=self._processing_hub,
            rate_limiter=self._rate_limiter,
            proactive_engine=self._proactive_engine,
            tool_registry=self._tool_registry,
            action_context=self._action_context,
            arweave_client=self._arweave_client,
        )
        
        logger.info("Created MainOrchestrator with injected dependencies")
        return orchestrator
    
    # Private validation methods
    async def _validate_startup_requirements(self) -> None:
        """Validate that all required services are properly initialized and registered."""
        logger.info("Validating startup requirements...")
        
        # Check critical configuration
        if not settings.processing.openrouter_api_key:
            raise ValueError("OPENROUTER_API_KEY is required for system operation")
        
        # Ensure ActionContext has a ServiceRegistry
        if not self._action_context or not self._action_context.service_registry:
            raise RuntimeError("ActionContext must have a ServiceRegistry for proper service abstraction")
        
        # Validate that we can retrieve essential services
        service_registry = self._action_context.service_registry
        available_services = service_registry.list_services()
        logger.info(f"Available services: {available_services}")
        
        # Check for at least one messaging service
        has_messaging_service = any(
            service_name.endswith('_messaging') or service_name.endswith('_observer')
            for service_name in available_services.keys()
        )
        
        if not has_messaging_service:
            logger.warning("No messaging services registered - tools may not function properly")
        
        logger.info("✓ Startup validation completed successfully")
