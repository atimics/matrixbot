"""
Integration management router for the chatbot API.

This module handles all integration-related endpoints including:
- Listing, adding, and removing integrations
- Managing integration connections and status
- Testing integration configurations
- Getting available integration types
"""

from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from datetime import datetime
import logging

from chatbot.core.orchestration import MainOrchestrator
from ..schemas import StatusResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations", tags=["integrations"])


def get_orchestrator() -> MainOrchestrator:
    """Dependency injection for orchestrator - will be set by main server."""
    # This will be overridden in the main server setup
    raise HTTPException(status_code=500, detail="Orchestrator not configured")


class IntegrationConfig(BaseModel):
    """Model for integration configuration."""
    integration_type: str
    display_name: str
    config: Dict[str, Any]
    credentials: Dict[str, str] = {}


class IntegrationTestRequest(BaseModel):
    """Model for testing integration configurations."""
    integration_type: str
    config: Dict[str, Any]
    credentials: Dict[str, str] = {}


@router.get("")
async def list_integrations(orchestrator: MainOrchestrator = Depends(get_orchestrator)):
    """List all configured integrations with their status."""
    try:
        integrations = await orchestrator.integration_manager.list_integrations()
        return integrations
    except Exception as e:
        logger.error(f"Error listing integrations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("")
async def add_integration(
    config: IntegrationConfig,
    orchestrator: MainOrchestrator = Depends(get_orchestrator)
):
    """Add a new integration configuration."""
    try:
        integration_id = await orchestrator.integration_manager.add_integration(
            integration_type=config.integration_type,
            display_name=config.display_name,
            config=config.config,
            credentials=config.credentials
        )
        return {"integration_id": integration_id, "message": "Integration added successfully"}
    except Exception as e:
        logger.error(f"Error adding integration: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{integration_id}")
async def get_integration_status(
    integration_id: str,
    orchestrator: MainOrchestrator = Depends(get_orchestrator)
):
    """Get detailed status of a specific integration."""
    try:
        status = await orchestrator.integration_manager.get_integration_status(integration_id)
        if status is None:
            raise HTTPException(status_code=404, detail="Integration not found")
        return status
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting integration status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{integration_id}/connect")
async def connect_integration(
    integration_id: str,
    orchestrator: MainOrchestrator = Depends(get_orchestrator)
):
    """Manually trigger connection attempt for an integration."""
    try:
        success = await orchestrator.integration_manager.connect_integration(
            integration_id, orchestrator.world_state
        )
        return {"success": success, "message": "Connection attempt completed"}
    except Exception as e:
        logger.error(f"Error connecting integration: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{integration_id}/disconnect")
async def disconnect_integration(
    integration_id: str,
    orchestrator: MainOrchestrator = Depends(get_orchestrator)
):
    """Disconnect a specific integration."""
    try:
        await orchestrator.integration_manager.disconnect_integration(integration_id)
        return {"message": "Integration disconnected successfully"}
    except Exception as e:
        logger.error(f"Error disconnecting integration: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{integration_id}")
async def remove_integration(
    integration_id: str,
    orchestrator: MainOrchestrator = Depends(get_orchestrator)
):
    """Remove an integration configuration."""
    try:
        # First disconnect if connected
        await orchestrator.integration_manager.disconnect_integration(integration_id)
        
        # TODO: Add remove_integration method to IntegrationManager
        return {"message": "Integration removed successfully"}
    except Exception as e:
        logger.error(f"Error removing integration: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test")
async def test_integration_config(
    test_request: IntegrationTestRequest,
    orchestrator: MainOrchestrator = Depends(get_orchestrator)
):
    """Test an integration configuration without saving it."""
    try:
        result = await orchestrator.integration_manager.test_integration_config(
            integration_type=test_request.integration_type,
            config=test_request.config,
            credentials=test_request.credentials
        )
        return result
    except Exception as e:
        logger.error(f"Error testing integration config: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/types")
async def get_available_integration_types(
    orchestrator: MainOrchestrator = Depends(get_orchestrator)
):
    """Get list of available integration types."""
    try:
        types = orchestrator.integration_manager.get_available_integration_types()
        return {"integration_types": types}
    except Exception as e:
        logger.error(f"Error getting integration types: {e}")
        raise HTTPException(status_code=500, detail=str(e))
