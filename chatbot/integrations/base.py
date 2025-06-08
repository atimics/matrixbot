"""
Base Integration Interface

Defines the common interface that all integrations must implement.
This provides a unified way to manage different service integrations.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class Integration(ABC):
    """Base class for all service integrations"""
    
    def __init__(self, integration_id: str, display_name: str, config: Dict[str, Any]):
        self.integration_id = integration_id
        self.display_name = display_name
        self.config = config
        self.is_connected = False
        self.last_error: Optional[str] = None
        
    @abstractmethod
    async def connect(self) -> bool:
        """
        Connects the integration to its service.
        
        Returns:
            bool: True on successful connection, False otherwise
        """
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnects the integration from its service"""
        pass

    @abstractmethod
    async def get_status(self) -> Dict[str, Any]:
        """
        Returns the current status of the integration.
        
        Returns:
            Dict containing status information including:
            - is_connected: bool
            - last_error: Optional[str]
            - service_specific_metrics: Dict[str, Any]
        """
        pass

    @property
    @abstractmethod
    def integration_type(self) -> str:
        """
        A unique identifier for the integration type.
        
        Returns:
            str: Integration type (e.g., 'farcaster', 'matrix', 'github')
        """
        pass
        
    @abstractmethod
    async def test_connection(self) -> Dict[str, Any]:
        """
        Test the connection without fully connecting.
        Used for validation during setup.
        
        Returns:
            Dict with 'success': bool and optional 'error': str
        """
        pass
        
    async def set_credentials(self, credentials: Dict[str, str]) -> None:
        """
        Set encrypted credentials for this integration.
        Override in subclasses if special handling is needed.
        
        Args:
            credentials: Dictionary of credential key-value pairs
        """
        # Store credentials securely - implementation will vary by integration
        self._credentials = credentials
        
    def get_basic_status(self) -> Dict[str, Any]:
        """
        Get basic status information common to all integrations.
        
        Returns:
            Dict with basic status information
        """
        return {
            "integration_id": self.integration_id,
            "integration_type": self.integration_type,
            "display_name": self.display_name,
            "is_connected": self.is_connected,
            "last_error": self.last_error,
        }


class IntegrationError(Exception):
    """Base exception for integration-related errors"""
    pass


class IntegrationConnectionError(IntegrationError):
    """Raised when an integration fails to connect"""
    pass


class IntegrationConfigurationError(IntegrationError):
    """Raised when integration configuration is invalid"""
    pass


class CredentialsError(IntegrationError):
    """Raised when credentials are invalid or missing"""
    pass
