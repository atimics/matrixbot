"""
Service Registry - Abstraction Layer for Platform Services

This module provides a centralized registry for platform services, enabling
clean separation between tools and platform-specific implementations.

Tools should interact with services through this registry rather than directly
accessing observers or clients, promoting loose coupling and testability.
"""

import logging
import os
from typing import Any, Dict, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class MessagingService(Protocol):
    """Protocol for messaging services across platforms."""
    
    async def send_message(self, channel_id: str, content: str, **kwargs) -> Dict[str, Any]:
        """Send a message to a channel."""
        ...
    
    async def send_reply(self, channel_id: str, content: str, reply_to_id: str, **kwargs) -> Dict[str, Any]:
        """Send a reply to a specific message."""
        ...
    
    async def send_image(self, channel_id: str, image_url: str, **kwargs) -> Dict[str, Any]:
        """Send an image to a channel."""
        ...


@runtime_checkable
class StorageService(Protocol):
    """Protocol for storage services."""
    
    async def store(self, key: str, data: Any, **kwargs) -> Dict[str, Any]:
        """Store data with a key."""
        ...
    
    async def retrieve(self, key: str, **kwargs) -> Dict[str, Any]:
        """Retrieve data by key."""
        ...


class PrimaryStorageService:
    """
    Unified storage service that abstracts away the choice between S3 and Arweave.
    
    This service automatically selects the appropriate backend based on configuration,
    allowing tools to use a single storage interface without needing to know about
    the underlying implementation.
    """
    
    def __init__(self, arweave_service=None, s3_service=None):
        self.arweave_service = arweave_service
        self.s3_service = s3_service
        
        # Determine primary backend from environment
        self.primary_backend = os.getenv("PRIMARY_STORAGE_BACKEND", "arweave").lower()
        
        logger.info(f"PrimaryStorageService initialized with backend: {self.primary_backend}")
    
    async def store(self, key: str, data: Any, **kwargs) -> Dict[str, Any]:
        """Store data using the configured primary backend."""
        storage_type = kwargs.get("storage_type", self.primary_backend)
        
        if storage_type == "arweave" and self.arweave_service:
            return await self._store_arweave(key, data, **kwargs)
        elif storage_type == "s3" and self.s3_service:
            return await self._store_s3(key, data, **kwargs)
        else:
            # Fallback to available service
            if self.arweave_service:
                return await self._store_arweave(key, data, **kwargs)
            elif self.s3_service:
                return await self._store_s3(key, data, **kwargs)
            else:
                return {
                    "status": "error",
                    "error": "No storage backend available"
                }
    
    async def retrieve(self, key: str, **kwargs) -> Dict[str, Any]:
        """Retrieve data using the configured primary backend."""
        storage_type = kwargs.get("storage_type", self.primary_backend)
        
        if storage_type == "arweave" and self.arweave_service:
            return await self._retrieve_arweave(key, **kwargs)
        elif storage_type == "s3" and self.s3_service:
            return await self._retrieve_s3(key, **kwargs)
        else:
            # Try both backends
            if self.arweave_service:
                result = await self._retrieve_arweave(key, **kwargs)
                if result.get("status") == "success":
                    return result
            
            if self.s3_service:
                return await self._retrieve_s3(key, **kwargs)
            
            return {
                "status": "error",
                "error": "No storage backend available"
            }
    
    async def _store_arweave(self, key: str, data: Any, **kwargs) -> Dict[str, Any]:
        """Store data via Arweave service."""
        try:
            if hasattr(data, 'read'):  # File-like object
                return await self.arweave_service.upload_file(data, key, **kwargs)
            else:  # String or other data
                return await self.arweave_service.upload_data(str(data), key, **kwargs)
        except Exception as e:
            logger.error(f"Arweave storage error: {e}")
            return {
                "status": "error",
                "error": f"Arweave storage failed: {str(e)}"
            }
    
    async def _store_s3(self, key: str, data: Any, **kwargs) -> Dict[str, Any]:
        """Store data via S3 service."""
        try:
            if hasattr(data, 'read'):  # File-like object
                return await self.s3_service.upload_file(data, key, **kwargs)
            else:  # String or other data
                return await self.s3_service.upload_data(str(data), key, **kwargs)
        except Exception as e:
            logger.error(f"S3 storage error: {e}")
            return {
                "status": "error",
                "error": f"S3 storage failed: {str(e)}"
            }
    
    async def _retrieve_arweave(self, key: str, **kwargs) -> Dict[str, Any]:
        """Retrieve data via Arweave service."""
        try:
            return await self.arweave_service.get_data(key, **kwargs)
        except Exception as e:
            logger.error(f"Arweave retrieval error: {e}")
            return {
                "status": "error",
                "error": f"Arweave retrieval failed: {str(e)}"
            }
    
    async def _retrieve_s3(self, key: str, **kwargs) -> Dict[str, Any]:
        """Retrieve data via S3 service."""
        try:
            return await self.s3_service.get_data(key, **kwargs)
        except Exception as e:
            logger.error(f"S3 retrieval error: {e}")
            return {
                "status": "error",
                "error": f"S3 retrieval failed: {str(e)}"
            }


class ServiceRegistry:
    """Registry for managing platform services with clean abstractions."""
    
    def __init__(self):
        self._services: Dict[str, Any] = {}
        logger.debug("ServiceRegistry initialized")
    
    def register_service(self, name: str, service: Any) -> None:
        """Register a service with the registry."""
        self._services[name] = service
        logger.debug(f"Registered service: {name}")
    
    def get_service(self, name: str) -> Optional[Any]:
        """Get a service by name."""
        return self._services.get(name)
    
    def get_messaging_service(self, platform: str) -> Optional[MessagingService]:
        """Get a messaging service for a specific platform."""
        service_name = f"{platform}_messaging"
        service = self.get_service(service_name)
        
        # For now, we'll wrap the observer in an adapter
        if not service and platform == "matrix":
            matrix_observer = self.get_service("matrix_observer")
            if matrix_observer:
                service = MatrixMessagingServiceAdapter(matrix_observer)
                self.register_service(service_name, service)
        elif not service and platform == "farcaster":
            farcaster_observer = self.get_service("farcaster_observer")
            if farcaster_observer:
                service = FarcasterMessagingServiceAdapter(farcaster_observer)
                self.register_service(service_name, service)
        
        return service
    
    def get_storage_service(self, storage_type: str = "primary") -> Optional[StorageService]:
        """Get a storage service by type."""
        if storage_type == "primary":
            # Return the unified primary storage service
            service = self.get_service("primary_storage")
            if not service:
                # Create primary storage service if not exists
                arweave_service = self.get_service("arweave_storage")
                s3_service = self.get_service("s3_storage")
                if arweave_service or s3_service:
                    service = PrimaryStorageService(arweave_service, s3_service)
                    self.register_service("primary_storage", service)
            return service
        else:
            # Return specific storage service
            service_name = f"{storage_type}_storage"
            return self.get_service(service_name)
    
    def list_services(self) -> Dict[str, str]:
        """List all registered services."""
        return {name: type(service).__name__ for name, service in self._services.items()}


class MatrixMessagingServiceAdapter:
    """Adapter to make MatrixObserver conform to MessagingService protocol."""
    
    def __init__(self, matrix_observer):
        self.matrix_observer = matrix_observer
    
    async def send_message(self, channel_id: str, content: str, **kwargs) -> Dict[str, Any]:
        """Send a message via Matrix observer."""
        format_as_markdown = kwargs.get("format_as_markdown", True)
        
        if format_as_markdown:
            from ...utils.markdown_utils import format_for_matrix
            formatted = format_for_matrix(content)
            result = await self.matrix_observer.send_formatted_message(
                channel_id, formatted["plain"], formatted["html"]
            )
        else:
            result = await self.matrix_observer.send_message(channel_id, content)
        
        return result
    
    async def send_reply(self, channel_id: str, content: str, reply_to_id: str, **kwargs) -> Dict[str, Any]:
        """Send a reply via Matrix observer."""
        format_as_markdown = kwargs.get("format_as_markdown", True)
        
        if format_as_markdown:
            from ...utils.markdown_utils import format_for_matrix
            formatted = format_for_matrix(content)
            result = await self.matrix_observer.send_formatted_reply(
                channel_id, formatted["plain"], formatted["html"], reply_to_id
            )
        else:
            result = await self.matrix_observer.send_reply(channel_id, content, reply_to_id)
        
        return result
    
    async def send_image(self, channel_id: str, image_url: str, **kwargs) -> Dict[str, Any]:
        """Send an image via Matrix observer."""
        caption = kwargs.get("caption")
        filename = kwargs.get("filename")
        return await self.matrix_observer.send_image(channel_id, image_url, caption, filename)


class FarcasterMessagingServiceAdapter:
    """Adapter to make FarcasterObserver conform to MessagingService protocol."""
    
    def __init__(self, farcaster_observer):
        self.farcaster_observer = farcaster_observer
    
    async def send_message(self, channel_id: str, content: str, **kwargs) -> Dict[str, Any]:
        """Send a message via Farcaster observer."""
        # For Farcaster, regular messages are posts
        return await self.farcaster_observer.send_cast(content)
    
    async def send_reply(self, channel_id: str, content: str, reply_to_id: str, **kwargs) -> Dict[str, Any]:
        """Send a reply via Farcaster observer."""
        return await self.farcaster_observer.send_reply(reply_to_id, content)
    
    async def send_image(self, channel_id: str, image_url: str, **kwargs) -> Dict[str, Any]:
        """Send an image via Farcaster observer."""
        # Farcaster handles images as part of casts
        caption = kwargs.get("caption", "")
        full_content = f"{caption}\n\n{image_url}".strip()
        return await self.farcaster_observer.send_cast(full_content)
