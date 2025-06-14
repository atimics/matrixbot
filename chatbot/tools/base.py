"""
Base classes and interfaces for the dynamic tool system.
"""
import logging
import warnings
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class ActionContext:
    """
    Provides context to tools during execution, including access to services,
    world state manager, and other shared resources.
    
    This class provides both the new service-oriented interface (via service_registry)
    and maintains backward compatibility with direct observer access.
    """

    def __init__(
        self,
        service_registry=None,
        matrix_observer=None,
        farcaster_observer=None,
        world_state_manager=None,
        context_manager=None,
        arweave_client=None,
        arweave_service=None,
        base_nft_service=None,
        eligibility_service=None,
    ):
        # New service-oriented approach
        self.service_registry = service_registry
        
        # Legacy observer access for backward compatibility - stored privately
        self._matrix_observer = matrix_observer
        self._farcaster_observer = farcaster_observer
        
        # Shared resources
        self.world_state_manager = world_state_manager
        self.context_manager = context_manager
        self.arweave_client = arweave_client
        self.arweave_service = arweave_service
        self.base_nft_service = base_nft_service
        self.eligibility_service = eligibility_service
        
        # Initialize dual storage manager
        self.dual_storage_manager = None
        try:
            from ..integrations.dual_storage_manager import DualStorageManager
            self.dual_storage_manager = DualStorageManager(arweave_service=arweave_service)
        except Exception as e:
            logger.warning(f"Failed to initialize dual storage manager: {e}")
    
    @property
    def matrix_observer(self):
        """
        DEPRECATED: Direct access to matrix_observer is deprecated.
        Use get_messaging_service('matrix') instead.
        """
        warnings.warn(
            "Direct access to matrix_observer is deprecated. Use get_messaging_service('matrix') instead.",
            DeprecationWarning,
            stacklevel=2
        )
        return self._matrix_observer
    
    @property
    def farcaster_observer(self):
        """
        DEPRECATED: Direct access to farcaster_observer is deprecated.
        Use get_social_service('farcaster') instead.
        """
        warnings.warn(
            "Direct access to farcaster_observer is deprecated. Use get_social_service('farcaster') instead.",
            DeprecationWarning,
            stacklevel=2
        )
        return self._farcaster_observer
    
    def get_messaging_service(self, service_id: str):
        """Get a messaging service by ID"""
        if self.service_registry:
            return self.service_registry.get_messaging_service(service_id)
        return None
    
    def get_media_service(self, service_id: str):
        """Get a media service by ID"""
        if self.service_registry:
            return self.service_registry.get_media_service(service_id)
        return None
    
    def get_social_service(self, service_id: str):
        """Get a social service by ID"""
        if self.service_registry:
            return self.service_registry.get_social_service(service_id)
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
        Example: {"channel_id": "string (Matrix room ID)", "content": "string"}
        """
        pass

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
