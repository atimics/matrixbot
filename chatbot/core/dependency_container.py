"""
Dependency Injection Container for RatiChat

This module provides a centralized dependency injection container to manage
component lifecycle and dependencies, reducing coupling and improving testability.
"""

import logging
from typing import Optional, Dict, Any

from ..config import settings
from ..core.ai_engine import AIDecisionEngine
from ..core.context import ContextManager
from ..core.integration_manager import IntegrationManager
from ..core.world_state.manager import WorldStateManager
from ..core.world_state.payload_builder import PayloadBuilder
from ..core.orchestration.processing_hub import ProcessingHub, ProcessingConfig
from ..core.orchestration.rate_limiter import RateLimiter, RateLimitConfig
from ..core.proactive import ProactiveConversationEngine
from ..tools.registry import ToolRegistry
from ..integrations.arweave_uploader_client import ArweaveUploaderClient

logger = logging.getLogger(__name__)


class DependencyContainer:
    """
    Centralized dependency injection container.
    
    This container manages the lifecycle of all major system components
    and their dependencies, providing a clean separation of concerns.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self._components: Dict[str, Any] = {}
        self._initialized = False
        
    async def initialize(self):
        """Initialize all components in the correct order."""
        if self._initialized:
            logger.warning("DependencyContainer already initialized")
            return
            
        logger.info("Initializing dependency container...")
        
        try:
            # Core components (no dependencies)
            await self._initialize_core_components()
            
            # Components with dependencies
            await self._initialize_dependent_components()
            
            # External service components
            await self._initialize_external_services()
            
            self._initialized = True
            logger.info("Dependency container initialization complete")
            
        except Exception as e:
            logger.error(f"Failed to initialize dependency container: {e}")
            await self.cleanup()
            raise
    
    async def _initialize_core_components(self):
        """Initialize core components with no dependencies."""
        
        # World State Manager
        self._components["world_state_manager"] = WorldStateManager()
        
        # Payload Builder
        self._components["payload_builder"] = PayloadBuilder(
            world_state_manager=self._components["world_state_manager"]
        )
        
        # Rate Limiter
        rate_limit_config = RateLimitConfig()
        # Apply any custom configuration
        if "rate_limiting" in self.config:
            for key, value in self.config["rate_limiting"].items():
                if hasattr(rate_limit_config, key):
                    setattr(rate_limit_config, key, value)
        
        self._components["rate_limiter"] = RateLimiter(rate_limit_config)
        
        # Tool Registry
        self._components["tool_registry"] = ToolRegistry()
        
        # AI Engine
        api_key = settings.OPENROUTER_API_KEY
        if not api_key:
            logger.warning("OPENROUTER_API_KEY not set, AI engine may not function properly")
            api_key = "dummy_key"  # Prevent initialization failure
        
        self._components["ai_engine"] = AIDecisionEngine(
            api_key=api_key,
            model=getattr(settings, 'AI_MODEL', 'openai/gpt-4o-mini')
        )
        
    async def _initialize_dependent_components(self):
        """Initialize components that depend on core components."""
        
        # Context Manager
        db_path = self.config.get("db_path", getattr(settings, 'CHATBOT_DB_PATH', 'data/chatbot.db'))
        self._components["context_manager"] = ContextManager(
            self._components["world_state_manager"],
            db_path
        )
        # Note: ContextManager may not have an initialize method in this codebase
        
        # Integration Manager
        encryption_key = getattr(settings, 'RATICHAT_ENCRYPTION_KEY', None)
        self._components["integration_manager"] = IntegrationManager(
            db_path=db_path,
            encryption_key=encryption_key,
            world_state_manager=self._components["world_state_manager"]
        )
        # Note: IntegrationManager may not have an initialize method in this codebase
        
        # Processing Hub
        processing_config = ProcessingConfig()
        # Apply any custom configuration
        if "processing" in self.config:
            for key, value in self.config["processing"].items():
                if hasattr(processing_config, key):
                    setattr(processing_config, key, value)
        
        self._components["processing_hub"] = ProcessingHub(
            world_state_manager=self._components["world_state_manager"],
            payload_builder=self._components["payload_builder"],
            rate_limiter=self._components["rate_limiter"],
            config=processing_config
        )
        
        # Proactive Conversation Engine
        self._components["proactive_engine"] = ProactiveConversationEngine(
            world_state_manager=self._components["world_state_manager"],
            context_manager=self._components["context_manager"]
        )
        
        # Connect proactive engine to world state for easy access
        self._components["world_state_manager"].proactive_engine = self._components["proactive_engine"]
        
    async def _initialize_external_services(self):
        """Initialize external service clients."""
        
        # Arweave Client (optional)
        arweave_url = getattr(settings, 'ARWEAVE_INTERNAL_UPLOADER_SERVICE_URL', None)
        if arweave_url:
            self._components["arweave_client"] = ArweaveUploaderClient(
                uploader_service_url=arweave_url,
                api_key=getattr(settings, 'ARWEAVE_UPLOADER_API_KEY', None)
            )
        else:
            self._components["arweave_client"] = None
            
    def get_component(self, name: str) -> Any:
        """Get a component by name."""
        if not self._initialized:
            raise RuntimeError("Container not initialized. Call initialize() first.")
        
        if name not in self._components:
            raise KeyError(f"Component '{name}' not found")
        
        return self._components[name]
    
    def get_world_state_manager(self) -> WorldStateManager:
        """Get the world state manager."""
        return self.get_component("world_state_manager")
    
    def get_context_manager(self) -> ContextManager:
        """Get the context manager."""
        return self.get_component("context_manager")
    
    def get_integration_manager(self) -> IntegrationManager:
        """Get the integration manager."""
        return self.get_component("integration_manager")
    
    def get_ai_engine(self) -> AIDecisionEngine:
        """Get the AI engine."""
        return self.get_component("ai_engine")
    
    def get_payload_builder(self) -> PayloadBuilder:
        """Get the payload builder."""
        return self.get_component("payload_builder")
    
    def get_processing_hub(self) -> ProcessingHub:
        """Get the processing hub."""
        return self.get_component("processing_hub")
    
    def get_rate_limiter(self) -> RateLimiter:
        """Get the rate limiter."""
        return self.get_component("rate_limiter")
    
    def get_proactive_engine(self) -> ProactiveConversationEngine:
        """Get the proactive conversation engine."""
        return self.get_component("proactive_engine")
    
    def get_tool_registry(self) -> ToolRegistry:
        """Get the tool registry."""
        return self.get_component("tool_registry")
    
    def get_arweave_client(self) -> Optional[ArweaveUploaderClient]:
        """Get the Arweave client (may be None)."""
        return self.get_component("arweave_client")
    
    def get_all_components(self) -> Dict[str, Any]:
        """Get all components as a dictionary."""
        if not self._initialized:
            raise RuntimeError("Container not initialized")
        return self._components.copy()
    
    async def cleanup(self):
        """Clean up all components."""
        logger.info("Cleaning up dependency container...")
        
        # Cleanup in reverse order of initialization
        cleanup_order = [
            "arweave_client",
            "proactive_engine", 
            "processing_hub",
            "integration_manager",
            "context_manager",
            "ai_engine",
            "tool_registry",
            "rate_limiter",
            "payload_builder",
            "world_state_manager"
        ]
        
        for component_name in cleanup_order:
            if component_name in self._components:
                component = self._components[component_name]
                try:
                    # Try to call cleanup method if it exists
                    if hasattr(component, 'cleanup'):
                        if hasattr(component.cleanup, '__call__'):
                            await component.cleanup()
                    elif hasattr(component, 'close'):
                        if hasattr(component.close, '__call__'):
                            await component.close()
                except Exception as e:
                    logger.error(f"Error cleaning up {component_name}: {e}")
        
        self._components.clear()
        self._initialized = False
        logger.info("Dependency container cleanup complete")
    
    def is_initialized(self) -> bool:
        """Check if the container is initialized."""
        return self._initialized


class SubsystemManager:
    """
    Base class for subsystem managers that handle specific aspects of the system.
    
    This allows us to break down the monolithic orchestrator into focused managers.
    """
    
    def __init__(self, name: str, container: DependencyContainer):
        self.name = name
        self.container = container
        self.logger = logging.getLogger(f"{__name__}.{name}")
        self.running = False
    
    async def start(self):
        """Start the subsystem."""
        if self.running:
            self.logger.warning(f"{self.name} is already running")
            return
        
        self.logger.info(f"Starting {self.name}...")
        await self._start_implementation()
        self.running = True
        self.logger.info(f"{self.name} started successfully")
    
    async def stop(self):
        """Stop the subsystem."""
        if not self.running:
            self.logger.warning(f"{self.name} is not running")
            return
        
        self.logger.info(f"Stopping {self.name}...")
        await self._stop_implementation()
        self.running = False
        self.logger.info(f"{self.name} stopped successfully")
    
    async def _start_implementation(self):
        """Override this method to implement subsystem-specific start logic."""
        pass
    
    async def _stop_implementation(self):
        """Override this method to implement subsystem-specific stop logic."""
        pass
    
    def get_status(self) -> Dict[str, Any]:
        """Get the current status of the subsystem."""
        return {
            "name": self.name,
            "running": self.running,
            "status": "running" if self.running else "stopped"
        }


class ObserverManager(SubsystemManager):
    """Manages external observers (Matrix, Farcaster, etc.)."""
    
    def __init__(self, container: DependencyContainer):
        super().__init__("ObserverManager", container)
        self.observers = {}
    
    async def _start_implementation(self):
        """Start all configured observers."""
        integration_manager = self.container.get_integration_manager()
        
        # Get enabled integrations
        integrations = await integration_manager.list_integrations()
        
        for integration in integrations:
            if integration.get("enabled", False):
                await self._start_observer(integration)
    
    async def _stop_implementation(self):
        """Stop all observers."""
        for observer_name, observer in list(self.observers.items()):
            try:
                await self._stop_observer(observer_name)
            except Exception as e:
                self.logger.error(f"Error stopping observer {observer_name}: {e}")
    
    async def _start_observer(self, integration: Dict[str, Any]):
        """Start a specific observer."""
        integration_type = integration.get("type")
        
        if integration_type == "matrix":
            await self._start_matrix_observer(integration)
        elif integration_type == "farcaster":
            await self._start_farcaster_observer(integration)
        else:
            self.logger.warning(f"Unknown integration type: {integration_type}")
    
    async def _stop_observer(self, observer_name: str):
        """Stop a specific observer."""
        if observer_name in self.observers:
            observer = self.observers[observer_name]
            if hasattr(observer, 'stop'):
                await observer.stop()
            del self.observers[observer_name]
            self.logger.info(f"Stopped observer: {observer_name}")
    
    async def _start_matrix_observer(self, integration: Dict[str, Any]):
        """Start Matrix observer."""
        # Import here to avoid circular imports
        from ..integrations.matrix.observer import MatrixObserver
        
        try:
            observer = MatrixObserver(world_state_manager=world_state)
            if hasattr(observer, 'initialize'):
                await observer.initialize(integration.get("config", {}))
            await observer.start()
            self.observers["matrix"] = observer
            self.logger.info("Matrix observer started")
        except Exception as e:
            self.logger.error(f"Failed to start Matrix observer: {e}")
    
    async def _start_farcaster_observer(self, integration: Dict[str, Any]):
        """Start Farcaster observer."""
        # Import here to avoid circular imports
        from ..integrations.farcaster import FarcasterObserver
        
        try:
            world_state = self.container.get_world_state_manager()
            observer = FarcasterObserver(world_state_manager=world_state)
            await observer.initialize(integration.get("config", {}))
            await observer.start()
            self.observers["farcaster"] = observer
            self.logger.info("Farcaster observer started")
        except Exception as e:
            self.logger.error(f"Failed to start Farcaster observer: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get observer status."""
        status = super().get_status()
        status["observers"] = {}
        
        for name, observer in self.observers.items():
            observer_status = {"name": name, "running": False}
            if hasattr(observer, 'running'):
                observer_status["running"] = observer.running
            if hasattr(observer, 'get_status'):
                observer_status.update(observer.get_status())
            status["observers"][name] = observer_status
        
        return status


class ToolManager(SubsystemManager):
    """Manages tool registration and lifecycle."""
    
    def __init__(self, container: DependencyContainer):
        super().__init__("ToolManager", container)
    
    async def _start_implementation(self):
        """Register all tools."""
        tool_registry = self.container.get_tool_registry()
        world_state = self.container.get_world_state_manager()
        context_manager = self.container.get_context_manager()
        
        # Create action context for tools
        from ..tools.base import ActionContext
        action_context = ActionContext(
            world_state_manager=world_state,
            context_manager=context_manager
        )
        
        # Register all tools
        await self._register_all_tools(tool_registry, action_context)
    
    async def _register_all_tools(self, tool_registry: ToolRegistry, action_context):
        """Register all available tools."""
        # Import and register core tools that exist
        try:
            from ..tools.matrix_tools import SendMatrixMessageTool, ReactToMatrixMessageTool
            from ..tools.farcaster_tools import SendFarcasterPostTool, LikeFarcasterPostTool
            
            # Register tools that exist in the codebase
            tool_classes = [
                SendMatrixMessageTool,
                ReactToMatrixMessageTool,
                SendFarcasterPostTool,
                LikeFarcasterPostTool,
            ]
            
            # Register each tool class
            registered_count = 0
            for tool_class in tool_classes:
                try:
                    # Most tools in this codebase are instantiated without parameters
                    tool_instance = tool_class()
                    tool_registry.register_tool(tool_instance)
                    registered_count += 1
                    self.logger.debug(f"Registered tool: {tool_class.__name__}")
                except Exception as e:
                    self.logger.warning(f"Failed to register tool {tool_class.__name__}: {e}")
            
            self.logger.info(f"Registered {registered_count} tools")
            
        except ImportError as e:
            self.logger.warning(f"Some tools could not be imported: {e}")
            self.logger.info("Tool registration completed with limited tool set")
    
    def get_status(self) -> Dict[str, Any]:
        """Get tool manager status."""
        status = super().get_status()
        
        if self.running:
            tool_registry = self.container.get_tool_registry()
            # Try to get tool count safely
            try:
                if hasattr(tool_registry, 'tools'):
                    status["registered_tools"] = len(tool_registry.tools)
                    status["tool_names"] = list(tool_registry.tools.keys())
                elif hasattr(tool_registry, 'get_all_tools'):
                    tools = tool_registry.get_all_tools()
                    status["registered_tools"] = len(tools)
                    status["tool_names"] = [tool.name for tool in tools]
                else:
                    status["registered_tools"] = "unknown"
                    status["tool_names"] = []
            except Exception as e:
                self.logger.warning(f"Could not get tool registry status: {e}")
                status["registered_tools"] = "error"
                status["tool_names"] = []
        
        return status
