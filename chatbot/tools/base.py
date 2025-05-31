"""
Base classes and interfaces for the dynamic tool system.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class ActionContext:
    """
    Provides context to tools during execution, including access to observers,
    world state manager, and other shared resources.
    """
    def __init__(
        self, 
        matrix_observer=None, 
        farcaster_observer=None, 
        world_state_manager=None,
        context_manager=None
    ):
        self.matrix_observer = matrix_observer
        self.farcaster_observer = farcaster_observer
        self.world_state_manager = world_state_manager
        self.context_manager = context_manager


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
    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
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
