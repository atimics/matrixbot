"""
Centralized dependency injection for the API server.

This module provides shared dependencies that can be injected into router endpoints,
following FastAPI's dependency injection pattern for better consistency and maintainability.
"""

from fastapi import HTTPException

from chatbot.core.orchestration import MainOrchestrator
from chatbot.api_server.services.setup_manager import SetupManager


def get_orchestrator() -> MainOrchestrator:
    """
    Dependency injection for orchestrator - will be overridden by main server setup.
    
    This placeholder function will be replaced via app.dependency_overrides
    in the main API server initialization.
    """
    raise HTTPException(status_code=500, detail="Orchestrator not configured")


def get_setup_manager() -> SetupManager:
    """
    Dependency injection for setup manager - will be overridden by main server setup.
    
    This placeholder function will be replaced via app.dependency_overrides
    in the main API server initialization.
    """
    raise HTTPException(status_code=500, detail="Setup manager not configured")
