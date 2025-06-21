"""
Enhanced centralized dependency injection for the API server.

This module implements a comprehensive dependency injection system that addresses
the repetitive boilerplate code issue identified in the engineering report.
"""

import logging
from typing import Optional, Dict, Any
from functools import lru_cache

from fastapi import HTTPException, Depends, Request
from pydantic import BaseModel

from chatbot.core.orchestration import MainOrchestrator
from chatbot.api_server.services.setup_manager import SetupManager
from chatbot.config import AppConfig
from chatbot.core.secrets import SecretManager

logger = logging.getLogger(__name__)


class DependencyContainer:
    """Container for managing application dependencies."""
    
    def __init__(self):
        self._orchestrator: Optional[MainOrchestrator] = None
        self._setup_manager: Optional[SetupManager] = None
        self._settings: Optional[AppConfig] = None
        self._secret_manager: Optional[SecretManager] = None
        self._initialized = False
    
    def initialize(
        self,
        orchestrator: MainOrchestrator,
        setup_manager: SetupManager,
        settings: AppConfig,
        secret_manager: SecretManager
    ):
        """Initialize the container with concrete instances."""
        self._orchestrator = orchestrator
        self._setup_manager = setup_manager
        self._settings = settings
        self._secret_manager = secret_manager
        self._initialized = True
        logger.info("Dependency container initialized")
    
    @property
    def orchestrator(self) -> MainOrchestrator:
        """Get orchestrator instance."""
        if not self._initialized or not self._orchestrator:
            raise HTTPException(status_code=500, detail="Orchestrator not configured")
        return self._orchestrator
    
    @property
    def setup_manager(self) -> SetupManager:
        """Get setup manager instance."""
        if not self._initialized or not self._setup_manager:
            raise HTTPException(status_code=500, detail="Setup manager not configured")
        return self._setup_manager
    
    @property
    def settings(self) -> AppConfig:
        """Get settings instance."""
        if not self._initialized or not self._settings:
            raise HTTPException(status_code=500, detail="Settings not configured")
        return self._settings
    
    @property
    def secret_manager(self) -> SecretManager:
        """Get secret manager instance."""
        if not self._initialized or not self._secret_manager:
            raise HTTPException(status_code=500, detail="Secret manager not configured")
        return self._secret_manager
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get health status of all dependencies."""
        return {
            "initialized": self._initialized,
            "orchestrator_ready": self._orchestrator is not None,
            "setup_manager_ready": self._setup_manager is not None,
            "settings_ready": self._settings is not None,
            "secret_manager_ready": self._secret_manager is not None
        }


# Global dependency container
_container = DependencyContainer()


def get_dependency_container() -> DependencyContainer:
    """Get the global dependency container."""
    return _container


class RequestMetadata(BaseModel):
    """Metadata extracted from request for dependency injection."""
    client_ip: str
    user_agent: str
    request_id: str
    path: str
    method: str


def get_request_metadata(request: Request) -> RequestMetadata:
    """Extract metadata from request for logging and tracking."""
    import uuid
    
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("User-Agent", "unknown")
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
    
    return RequestMetadata(
        client_ip=client_ip,
        user_agent=user_agent,
        request_id=request_id,
        path=str(request.url.path),
        method=request.method
    )


# Dependency injection functions
def get_orchestrator(
    container: DependencyContainer = Depends(get_dependency_container)
) -> MainOrchestrator:
    """Get orchestrator instance via dependency injection."""
    return container.orchestrator


def get_setup_manager(
    container: DependencyContainer = Depends(get_dependency_container)
) -> SetupManager:
    """Get setup manager instance via dependency injection."""
    return container.setup_manager


def get_settings(
    container: DependencyContainer = Depends(get_dependency_container)
) -> AppConfig:
    """Get settings instance via dependency injection."""
    return container.settings


def get_secret_manager(
    container: DependencyContainer = Depends(get_dependency_container)
) -> SecretManager:
    """Get secret manager instance via dependency injection."""
    return container.secret_manager


@lru_cache(maxsize=1)
def get_cached_settings() -> AppConfig:
    """Get cached settings for performance-critical paths."""
    try:
        return _container.settings
    except:
        # Fallback to creating new instance if container not initialized
        from chatbot.config import create_settings
        return create_settings()


class HealthChecker:
    """Dependency for health checking various services."""
    
    def __init__(self, container: DependencyContainer):
        self.container = container
    
    async def check_orchestrator_health(self) -> Dict[str, Any]:
        """Check orchestrator health."""
        try:
            orchestrator = self.container.orchestrator
            # Assuming orchestrator has a health check method
            if hasattr(orchestrator, 'get_health_status'):
                return await orchestrator.get_health_status()
            else:
                return {"status": "running", "message": "Orchestrator is active"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    async def check_setup_manager_health(self) -> Dict[str, Any]:
        """Check setup manager health."""
        try:
            setup_manager = self.container.setup_manager
            return {
                "status": "running",
                "setup_required": setup_manager.is_setup_required(),
                "current_step": setup_manager.current_step_index
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    async def get_full_health_status(self) -> Dict[str, Any]:
        """Get comprehensive health status."""
        container_status = self.container.get_health_status()
        
        health_status = {
            "container": container_status,
            "timestamp": logger.info.__globals__.get('datetime', {}).get('datetime', {}).now().isoformat() if hasattr(logging, 'datetime') else "unknown"
        }
        
        if container_status["orchestrator_ready"]:
            health_status["orchestrator"] = await self.check_orchestrator_health()
        
        if container_status["setup_manager_ready"]:
            health_status["setup_manager"] = await self.check_setup_manager_health()
        
        return health_status


def get_health_checker(
    container: DependencyContainer = Depends(get_dependency_container)
) -> HealthChecker:
    """Get health checker instance."""
    return HealthChecker(container)


# Utility functions for the enhanced dependency system
def initialize_dependencies(
    orchestrator: MainOrchestrator,
    setup_manager: SetupManager,
    settings: AppConfig,
    secret_manager: SecretManager
):
    """Initialize the global dependency container."""
    _container.initialize(orchestrator, setup_manager, settings, secret_manager)


def is_dependencies_initialized() -> bool:
    """Check if dependencies are initialized."""
    return _container._initialized
