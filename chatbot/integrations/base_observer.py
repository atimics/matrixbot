#!/usr/bin/env python3
"""
Base Observer

Provides a minimal common interface for platform integration observers.
This class establishes common patterns for lifecycle management and health monitoring
while allowing platform-specific implementations to remain flexible.
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class ObserverStatus(Enum):
    """Observer connection status enumeration"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"
    RECONNECTING = "reconnecting"


class BaseObserver(ABC):
    """
    Base class for platform integration observers.
    
    Provides a minimal common interface for lifecycle management and health monitoring
    while allowing platform-specific implementations to remain flexible.
    """
    
    def __init__(self, integration_id: str, display_name: str):
        self.integration_id = integration_id
        self.display_name = display_name
        self._status = ObserverStatus.DISCONNECTED
        self._last_error: Optional[str] = None
        self._connection_attempts = 0
        self._enabled = True
        
    @property
    def status(self) -> ObserverStatus:
        """Get current observer status"""
        return self._status
    
    @property
    def last_error(self) -> Optional[str]:
        """Get the last error message"""
        return self._last_error
    
    @property
    def enabled(self) -> bool:
        """Check if observer is enabled"""
        return self._enabled
    
    @enabled.setter
    def enabled(self, value: bool) -> None:
        """Set observer enabled state"""
        self._enabled = value
        if not value:
            self._status = ObserverStatus.DISCONNECTED
    
    @abstractmethod
    async def connect(self, credentials: Optional[Dict[str, Any]] = None) -> bool:
        """
        Connect to the platform.
        
        Args:
            credentials: Optional platform-specific credentials
            
        Returns:
            True if connection successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the platform."""
        pass
    
    @abstractmethod
    async def is_healthy(self) -> bool:
        """
        Check if the observer is healthy and operational.
        
        Returns:
            True if healthy, False otherwise
        """
        pass
    
    def _set_status(self, status: ObserverStatus, error: Optional[str] = None) -> None:
        """
        Set observer status and error state.
        
        Args:
            status: New status
            error: Optional error message
        """
        old_status = self._status
        self._status = status
        self._last_error = error
        
        if status != old_status:
            logger.debug(f"{self.display_name}: Status changed from {old_status.value} to {status.value}")
            
        if error:
            logger.error(f"{self.display_name}: Error - {error}")
    
    def _increment_connection_attempts(self) -> None:
        """Increment connection attempt counter"""
        self._connection_attempts += 1
        
    def _reset_connection_attempts(self) -> None:
        """Reset connection attempt counter"""
        self._connection_attempts = 0
    
    def get_status_info(self) -> Dict[str, Any]:
        """
        Get comprehensive status information.
        
        Returns:
            Dict containing status, error, and connection attempt info
        """
        return {
            "integration_id": self.integration_id,
            "display_name": self.display_name,
            "status": self._status.value,
            "enabled": self._enabled,
            "last_error": self._last_error,
            "connection_attempts": self._connection_attempts,
        }
