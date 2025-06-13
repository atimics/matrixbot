"""
Service Registry

Central registry for managing integration services in a service-oriented architecture.
This provides clean abstraction between the MainOrchestrator and underlying observers.
"""

import logging
from typing import Any, Dict, Optional, Type, List
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class ServiceInterface(ABC):
    """Base interface for all integration services"""
    
    @property
    @abstractmethod
    def service_id(self) -> str:
        """Unique identifier for this service"""
        pass
    
    @property
    @abstractmethod
    def service_type(self) -> str:
        """Type of service (matrix, farcaster, etc.)"""
        pass
    
    @abstractmethod
    async def is_available(self) -> bool:
        """Check if the service is available and operational"""
        pass


class MessagingServiceInterface(ServiceInterface):
    """Interface for services that support messaging operations"""
    
    @abstractmethod
    async def send_message(self, channel_id: str, content: str, **kwargs) -> Dict[str, Any]:
        """Send a message to a channel"""
        pass
    
    @abstractmethod
    async def send_reply(self, channel_id: str, content: str, reply_to_id: str, **kwargs) -> Dict[str, Any]:
        """Send a reply to a specific message"""
        pass
    
    @abstractmethod
    async def react_to_message(self, channel_id: str, event_id: str, reaction: str) -> Dict[str, Any]:
        """React to a message with an emoji or reaction"""
        pass


class MediaServiceInterface(ServiceInterface):
    """Interface for services that support media operations"""
    
    @abstractmethod
    async def send_image(self, channel_id: str, image_url: str, caption: str = None, **kwargs) -> Dict[str, Any]:
        """Send an image to a channel"""
        pass
    
    @abstractmethod
    async def send_video(self, channel_id: str, video_url: str, caption: str = None, **kwargs) -> Dict[str, Any]:
        """Send a video to a channel"""
        pass


class SocialServiceInterface(ServiceInterface):
    """Interface for services that support social media operations"""
    
    @abstractmethod
    async def create_post(self, content: str, **kwargs) -> Dict[str, Any]:
        """Create a new post/cast"""
        pass
    
    @abstractmethod
    async def like_post(self, post_id: str) -> Dict[str, Any]:
        """Like/heart a post"""
        pass


class ServiceRegistry:
    """Central registry for managing integration services"""
    
    def __init__(self):
        self._services: Dict[str, ServiceInterface] = {}
        self._service_types: Dict[str, List[str]] = {}
        
    def register_service(self, service: ServiceInterface) -> None:
        """Register a service in the registry"""
        service_id = service.service_id
        service_type = service.service_type
        
        if service_id in self._services:
            logger.warning(f"Service {service_id} is already registered, replacing")
            
        self._services[service_id] = service
        
        # Track services by type
        if service_type not in self._service_types:
            self._service_types[service_type] = []
        if service_id not in self._service_types[service_type]:
            self._service_types[service_type].append(service_id)
            
        logger.info(f"Registered service: {service_id} (type: {service_type})")
    
    def unregister_service(self, service_id: str) -> None:
        """Unregister a service from the registry"""
        if service_id not in self._services:
            logger.warning(f"Attempted to unregister unknown service: {service_id}")
            return
            
        service = self._services[service_id]
        service_type = service.service_type
        
        del self._services[service_id]
        
        # Remove from type tracking
        if service_type in self._service_types:
            self._service_types[service_type] = [
                sid for sid in self._service_types[service_type] if sid != service_id
            ]
            if not self._service_types[service_type]:
                del self._service_types[service_type]
                
        logger.info(f"Unregistered service: {service_id}")
    
    def get_service(self, service_id: str) -> Optional[ServiceInterface]:
        """Get a service by ID"""
        return self._services.get(service_id)
    
    def get_services_by_type(self, service_type: str) -> List[ServiceInterface]:
        """Get all services of a specific type"""
        service_ids = self._service_types.get(service_type, [])
        return [self._services[service_id] for service_id in service_ids if service_id in self._services]
    
    def get_messaging_service(self, service_id: str) -> Optional[MessagingServiceInterface]:
        """Get a messaging service by ID"""
        service = self.get_service(service_id)
        if isinstance(service, MessagingServiceInterface):
            return service
        return None
    
    def get_media_service(self, service_id: str) -> Optional[MediaServiceInterface]:
        """Get a media service by ID"""
        service = self.get_service(service_id)
        if isinstance(service, MediaServiceInterface):
            return service
        return None
    
    def get_social_service(self, service_id: str) -> Optional[SocialServiceInterface]:
        """Get a social service by ID"""
        service = self.get_service(service_id)
        if isinstance(service, SocialServiceInterface):
            return service
        return None
    
    def list_available_services(self) -> Dict[str, Dict[str, Any]]:
        """List all available services with their status"""
        services = {}
        for service_id, service in self._services.items():
            services[service_id] = {
                'service_type': service.service_type,
                'interfaces': self._get_service_interfaces(service)
            }
        return services
    
    def _get_service_interfaces(self, service: ServiceInterface) -> List[str]:
        """Get the interfaces implemented by a service"""
        interfaces = ['ServiceInterface']
        if isinstance(service, MessagingServiceInterface):
            interfaces.append('MessagingServiceInterface')
        if isinstance(service, MediaServiceInterface):
            interfaces.append('MediaServiceInterface')
        if isinstance(service, SocialServiceInterface):
            interfaces.append('SocialServiceInterface')
        return interfaces
    
    async def get_available_services(self) -> Dict[str, ServiceInterface]:
        """Get all currently available services (connected and operational)"""
        available = {}
        for service_id, service in self._services.items():
            try:
                if await service.is_available():
                    available[service_id] = service
            except Exception as e:
                logger.warning(f"Error checking availability of service {service_id}: {e}")
        return available
