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
    
    This class provides a clean service-oriented interface via the service_registry
    that allows tools to access platform services (messaging, social, media) in a
    decoupled manner.
    """

    def __init__(
        self,
        service_registry=None,
        world_state_manager=None,
        context_manager=None,
        arweave_client=None,
        arweave_service=None,
        base_nft_service=None,
        eligibility_service=None,
        processing_hub=None,
        current_channel_id=None,
    ):
        # Service-oriented approach
        self.service_registry = service_registry
        
        # Shared resources
        self.world_state_manager = world_state_manager
        self.context_manager = context_manager
        self.arweave_client = arweave_client
        self.arweave_service = arweave_service
        self.base_nft_service = base_nft_service
        self.eligibility_service = eligibility_service
        self.processing_hub = processing_hub
        
        # Current channel context for tool execution
        self.current_channel_id = current_channel_id
        
        # Initialize dual storage manager
        self.dual_storage_manager = None
        try:
            from ..integrations.dual_storage_manager import DualStorageManager
            self.dual_storage_manager = DualStorageManager(arweave_service=arweave_service)
        except Exception as e:
            logger.warning(f"Failed to initialize dual storage manager: {e}")
    
    def update_current_channel(self, channel_id: str):
        """Update the current channel ID for tool execution context."""
        self.current_channel_id = channel_id
    
    def get_current_channel_id(self) -> Optional[str]:
        """Get the current channel ID, with fallback to world state if available."""
        if self.current_channel_id:
            return self.current_channel_id
        
        # Fallback: try to get from world state
        if self.world_state_manager:
            try:
                world_state_data = self.world_state_manager.get_world_state_data()
                # Check if there's a primary processing channel in current state
                return getattr(world_state_data, 'current_processing_channel_id', None)
            except Exception as e:
                logger.debug(f"Could not get current channel from world state: {e}")
        
        return None
    
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
