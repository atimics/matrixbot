"""
Base Integration Service

Service-oriented abstraction layer for platform integrations.
This provides a cleaner separation between integration observers and service functionality.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple
import logging
from dataclasses import dataclass

from ..core.world_state import Message

logger = logging.getLogger(__name__)


@dataclass
class ServiceStatus:
    """Status information for an integration service"""
    service_id: str
    service_type: str
    is_connected: bool
    is_enabled: bool
    last_error: Optional[str] = None
    connection_time: Optional[float] = None
    metrics: Dict[str, Any] = None

    def __post_init__(self):
        if self.metrics is None:
            self.metrics = {}


class BaseIntegrationService(ABC):
    """
    Abstract base class for integration services.
    
    This class provides a service-oriented abstraction layer that:
    1. Encapsulates platform-specific communication logic
    2. Provides standardized interfaces for messaging, feed observation, and user interaction
    3. Manages connection lifecycle and error handling
    4. Abstracts channel/feed visibility and management
    """
    
    def __init__(self, service_id: str, service_type: str, config: Dict[str, Any] = None):
        self.service_id = service_id
        self.service_type = service_type
        self.config = config or {}
        self.is_connected = False
        self.is_enabled = True
        self.last_error: Optional[str] = None
        self.connection_time: Optional[float] = None
        self._observer = None  # Reference to underlying observer/integration
        
    @abstractmethod
    async def connect(self) -> bool:
        """
        Connect to the service and initialize all necessary resources.
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        pass
        
    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the service and cleanup resources."""
        pass
        
    @abstractmethod
    async def test_connection(self) -> Dict[str, Any]:
        """
        Test service connectivity without full connection.
        
        Returns:
            Dict with 'success': bool and optional 'error': str
        """
        pass
        
    @property
    @abstractmethod
    def enabled(self) -> bool:
        """Check if service is enabled and properly configured."""
        pass
        
    # === MESSAGING INTERFACE ===
    
    @abstractmethod
    async def send_message(self, content: str, channel_id: str, **kwargs) -> Dict[str, Any]:
        """
        Send a message to a specific channel/room.
        
        Args:
            content: Message content
            channel_id: Target channel/room identifier
            **kwargs: Platform-specific options (reply_to, embeds, etc.)
            
        Returns:
            Dict with 'success': bool and optional message details
        """
        pass
        
    @abstractmethod
    async def reply_to_message(self, content: str, message_id: str, **kwargs) -> Dict[str, Any]:
        """
        Reply to a specific message.
        
        Args:
            content: Reply content
            message_id: ID of message to reply to
            **kwargs: Platform-specific options
            
        Returns:
            Dict with 'success': bool and optional reply details
        """
        pass
        
    # === FEED OBSERVATION INTERFACE ===
    
    @abstractmethod
    async def get_available_channels(self) -> List[Dict[str, Any]]:
        """
        Get list of all available channels/feeds the service can access.
        
        Returns:
            List of channel info dicts with keys: id, name, type, description
        """
        pass
        
    @abstractmethod
    async def observe_channel_messages(self, channel_id: str, limit: int = 50) -> List[Message]:
        """
        Observe recent messages from a specific channel.
        
        Args:
            channel_id: Channel identifier
            limit: Maximum number of messages to retrieve
            
        Returns:
            List of Message objects
        """
        pass
        
    @abstractmethod
    async def observe_all_feeds(self, feed_types: List[str] = None) -> Dict[str, List[Message]]:
        """
        Observe messages from multiple feed types.
        
        Args:
            feed_types: List of feed types to observe (platform-specific)
            
        Returns:
            Dict mapping feed_type -> List[Message]
        """
        pass
        
    # === USER INTERACTION INTERFACE ===
    
    @abstractmethod
    async def get_user_info(self, user_id: str) -> Dict[str, Any]:
        """
        Get information about a user.
        
        Args:
            user_id: User identifier
            
        Returns:
            Dict with user information
        """
        pass
        
    @abstractmethod
    async def get_user_context(self, message: Message) -> Dict[str, Any]:
        """
        Get contextual information about a user from a message.
        
        Args:
            message: Message object
            
        Returns:
            Dict with user context information
        """
        pass
        
    # === STATUS AND MANAGEMENT ===
    
    def get_status(self) -> ServiceStatus:
        """Get current service status."""
        return ServiceStatus(
            service_id=self.service_id,
            service_type=self.service_type,
            is_connected=self.is_connected,
            is_enabled=self.is_enabled,
            last_error=self.last_error,
            connection_time=self.connection_time,
            metrics=self._get_service_metrics()
        )
        
    @abstractmethod
    def _get_service_metrics(self) -> Dict[str, Any]:
        """
        Get service-specific metrics for monitoring.
        
        Returns:
            Dict with metrics like message_count, error_count, etc.
        """
        pass
        
    # === CONFIGURATION MANAGEMENT ===
    
    async def set_credentials(self, credentials: Dict[str, str]) -> None:
        """
        Set service credentials.
        
        Args:
            credentials: Dict of credential key-value pairs
        """
        if self._observer and hasattr(self._observer, 'set_credentials'):
            await self._observer.set_credentials(credentials)
        else:
            logger.warning(f"Service {self.service_id} does not support credential updates")
            
    def update_config(self, config: Dict[str, Any]) -> None:
        """Update service configuration."""
        self.config.update(config)
        
    # === WORLD STATE INTEGRATION ===
    
    async def collect_world_state_data(self, **kwargs) -> Dict[str, List[Message]]:
        """
        Collect comprehensive world state data for AI context.
        
        Returns:
            Dict mapping data_type -> List[Message]
        """
        try:
            return await self.observe_all_feeds(**kwargs)
        except Exception as e:
            logger.error(f"Error collecting world state data for {self.service_type}: {e}")
            return {}
            
    # === UTILITY METHODS ===
    
    def _set_observer(self, observer) -> None:
        """Set reference to underlying observer/integration."""
        self._observer = observer
        
    def _get_observer(self):
        """Get reference to underlying observer/integration."""
        return self._observer
        
    async def _handle_error(self, error: Exception, context: str = "") -> None:
        """Handle service errors consistently."""
        error_msg = f"{context}: {str(error)}" if context else str(error)
        self.last_error = error_msg
        logger.error(f"Service {self.service_id} error - {error_msg}", exc_info=True)
        
    def _log_operation(self, operation: str, details: str = "") -> None:
        """Log service operations for debugging."""
        log_msg = f"Service {self.service_id} ({self.service_type}): {operation}"
        if details:
            log_msg += f" - {details}"
        logger.debug(log_msg)
