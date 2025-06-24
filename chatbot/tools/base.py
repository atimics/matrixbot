"""
Base classes and interfaces for the dynamic tool system.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.node_system.node_manager import NodeManager


class ActionContext:
    """
    Provides context to tools during execution through the ServiceRegistry abstraction.
    
    This class enforces clean service abstraction by routing all platform interactions
    through the ServiceRegistry. Tools should use:
    - context.service_registry.get_messaging_service(platform) for messaging
    - context.service_registry.get_storage_service(type) for storage
    - context.service_registry.get_service(name) for other services
    
    Direct observer access has been removed to enforce proper abstraction.
    """

    def __init__(
        self,
        world_state_manager=None,
        context_manager=None,
        service_registry=None,
        # Legacy parameters for backward compatibility during migration
        matrix_observer=None,
        farcaster_observer=None,
        arweave_client=None,
        arweave_service=None,
        s3_service=None,
        base_nft_service=None,
        eligibility_service=None,
    ):
        # New unified service access
        self.service_registry = service_registry
        self.world_state_manager = world_state_manager
        self.context_manager = context_manager
        
        # Node system access
        self.node_manager: Optional["NodeManager"] = None  # Will be set after node system initialization
        
        # Auto-populate service registry if not provided
        if not self.service_registry:
            from ..core.services import ServiceRegistry
            self.service_registry = ServiceRegistry()
            
        # Register legacy services for compatibility during migration
        if matrix_observer:
            self.service_registry.register_service("matrix_observer", matrix_observer)
        if farcaster_observer:
            self.service_registry.register_service("farcaster_observer", farcaster_observer)
        if arweave_service:
            self.service_registry.register_service("arweave_storage", arweave_service)
        if s3_service:
            self.service_registry.register_service("s3_storage", s3_service)
        if base_nft_service:
            self.service_registry.register_service("base_nft_service", base_nft_service)
        if eligibility_service:
            self.service_registry.register_service("eligibility_service", eligibility_service)

    # Legacy property accessors for backward compatibility
    # These will raise deprecation warnings to encourage migration to service registry
    @property
    def matrix_observer(self):
        """DEPRECATED: Use service_registry.get_messaging_service('matrix') instead."""
        import warnings
        warnings.warn(
            "Direct access to matrix_observer is deprecated. Use context.service_registry.get_messaging_service('matrix') instead.",
            DeprecationWarning,
            stacklevel=2
        )
        if self.service_registry:
            return self.service_registry.get_service("matrix_observer")
        return None
    
    @property
    def farcaster_observer(self):
        """DEPRECATED: Use service_registry.get_messaging_service('farcaster') instead."""
        import warnings
        warnings.warn(
            "Direct access to farcaster_observer is deprecated. Use context.service_registry.get_messaging_service('farcaster') instead.",
            DeprecationWarning,
            stacklevel=2
        )
        if self.service_registry:
            return self.service_registry.get_service("farcaster_observer")
        return None
    
    @property
    def arweave_service(self):
        """DEPRECATED: Use service_registry.get_storage_service() instead."""
        import warnings
        warnings.warn(
            "Direct access to arweave_service is deprecated. Use context.service_registry.get_storage_service() instead.",
            DeprecationWarning,
            stacklevel=2
        )
        if self.service_registry:
            return self.service_registry.get_service("arweave_storage")
        return None
    
    @property
    def s3_service(self):
        """DEPRECATED: Use service_registry.get_storage_service() instead."""
        import warnings
        warnings.warn(
            "Direct access to s3_service is deprecated. Use context.service_registry.get_storage_service() instead.",
            DeprecationWarning,
            stacklevel=2
        )
        if self.service_registry:
            return self.service_registry.get_service("s3_storage")
        return None


class ToolInterface(ABC):
    """
    Abstract base class defining the interface for all tools in the system.
    Tools are self-contained units of capability that can be dynamically
    registered and executed by the orchestrator.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """The unique name of the tool, used by the AI for identification."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """
        A description of what the tool does, its parameters, and when to use it.
        This description is used in the AI prompt to help the model understand
        when and how to use this tool.
        """
        pass

    @property
    @abstractmethod
    def parameters_schema(self) -> Dict[str, Any]:
        """
        A schema describing the parameters the tool accepts.
        Format: {"parameter_name": "type and description"}
        Example: {"channel_id": "string - The unique identifier of the target channel", "content": "string - The message content"}
        """
        pass
    
    @property
    def access_level(self) -> str:
        """
        Access level for this tool, determining which agents can use it.
        
        Levels:
        - 'conversational': Basic tools for simple conversations (Sub-Agents)
        - 'strategic': Advanced tools for strategic planning (Commander AI)
        - 'system': System-level tools for administration
        - 'core': Core tools available to all agents
        
        Default is 'core' for backward compatibility.
        """
        return 'core'

    @abstractmethod
    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """
        Executes the tool with the given parameters and context.

        Args:
            params: Dictionary of parameters for the tool
            context: ActionContext providing access to observers and managers

        Returns:
            Dictionary with status and result/error information:
            - status: "success" or "failure"
            - message: Success message (for status="success")
            - error: Error message (for status="failure")
            - timestamp: Execution timestamp
            - Additional tool-specific data
        """
        pass
