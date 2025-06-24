"""
Base classes and interfaces for the dynamic tool system.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.node_system.node_manager import NodeManager


class ActionContext:
    """
    Provides context to tools during execution, including access to observers,
    world state manager, and other shared resources.
    
    NEW: ServiceRegistry provides clean abstraction layer for platform services.
    Tools should prefer service_registry.get_messaging_service() over direct observer access.
    """

    def __init__(
        self,
        world_state_manager=None,
        context_manager=None,
        service_registry=None,
        # Legacy direct access - deprecated, use service_registry instead
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
        
        # Legacy direct access (deprecated - use service_registry instead)
        self.matrix_observer = matrix_observer
        self.farcaster_observer = farcaster_observer
        self.arweave_client = arweave_client
        self.arweave_service = arweave_service
        self.s3_service = s3_service
        self.base_nft_service = base_nft_service
        self.eligibility_service = eligibility_service
        
        # Auto-populate service registry if not provided
        if not self.service_registry:
            from ..core.services import ServiceRegistry
            self.service_registry = ServiceRegistry()
            
            # Register legacy services for compatibility
            if matrix_observer:
                self.service_registry.register_service("matrix_observer", matrix_observer)
            if farcaster_observer:
                self.service_registry.register_service("farcaster_observer", farcaster_observer)
            if arweave_service:
                self.service_registry.register_service("arweave_storage", arweave_service)
            if s3_service:
                self.service_registry.register_service("s3_storage", s3_service)


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
        Example: {"channel_id": "string (Matrix room ID)", "content": "string"}
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
