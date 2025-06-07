"""
Configuration management router - handles system configuration.
"""

import logging
from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, Depends

from ..schemas import ConfigUpdate, StatusResponse
from chatbot.core.orchestration import MainOrchestrator
from chatbot.config import settings
from ..dependencies import get_orchestrator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/config", tags=["configuration"])





@router.get("")
async def get_configuration(orchestrator: MainOrchestrator = Depends(get_orchestrator)):
    """Get current system configuration."""
    try:
        # Get current configuration from settings
        config = {
            "ai": {
                "model": settings.OPENROUTER_MODEL,
                "max_actions_per_cycle": 3,
                "temperature": getattr(settings, 'AI_TEMPERATURE', 0.7)
            },
            "processing": {
                "node_based_enabled": orchestrator.processing_hub.get_processing_status().get("node_based_enabled", True),
                "max_expanded_nodes": getattr(settings, 'MAX_EXPANDED_NODES', 3),
                "auto_collapse_threshold": getattr(settings, 'AUTO_COLLAPSE_THRESHOLD', 10)
            },
            "rate_limits": {
                "max_cycles_per_hour": settings.MAX_CYCLES_PER_HOUR,
                "max_actions_per_hour": settings.MAX_ACTIONS_PER_HOUR,
                "image_generation_cooldown": settings.IMAGE_GENERATION_COOLDOWN_SECONDS,
                "video_generation_cooldown": settings.VIDEO_GENERATION_COOLDOWN_SECONDS,
                "farcaster_post_cooldown": settings.FARCASTER_POST_COOLDOWN_SECONDS
            },
            "integrations": {
                "matrix_enabled": bool(settings.MATRIX_USER_ID and settings.MATRIX_PASSWORD),
                "farcaster_enabled": bool(settings.NEYNAR_API_KEY),
                "arweave_enabled": bool(settings.ARWEAVE_WALLET_PATH),
                "replicate_enabled": bool(settings.REPLICATE_API_TOKEN),
                "google_ai_enabled": bool(settings.GOOGLE_API_KEY)
            },
            "storage": {
                "db_path": settings.DB_PATH,
                "context_storage_enabled": True,
                "history_retention_days": getattr(settings, 'HISTORY_RETENTION_DAYS', 30)
            },
            "logging": {
                "level": settings.LOG_LEVEL,
                "file_enabled": True
            }
        }
        
        return {
            "config": config,
            "last_updated": datetime.now().isoformat(),
            "editable_keys": [
                "ai.temperature",
                "processing.max_expanded_nodes",
                "processing.auto_collapse_threshold",
                "rate_limits.max_cycles_per_hour",
                "rate_limits.max_actions_per_hour",
                "storage.history_retention_days",
                "logging.level"
            ]
        }
        
    except Exception as e:
        logger.error(f"Error getting configuration: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get configuration: {str(e)}")


@router.put("", response_model=StatusResponse)
async def update_configuration(
    config_update: ConfigUpdate,
    orchestrator: MainOrchestrator = Depends(get_orchestrator)
):
    """Update a configuration value."""
    try:
        key = config_update.key
        value = config_update.value
        
        logger.info(f"Updating configuration: {key} = {value}")
        
        # Define allowed configuration updates
        # Note: In a production system, this would likely use a more sophisticated
        # configuration management system
        allowed_updates = {
            "ai.temperature": lambda v: setattr(settings, 'AI_TEMPERATURE', float(v)),
            "processing.max_expanded_nodes": lambda v: setattr(settings, 'MAX_EXPANDED_NODES', int(v)),
            "processing.auto_collapse_threshold": lambda v: setattr(settings, 'AUTO_COLLAPSE_THRESHOLD', int(v)),
            "rate_limits.max_cycles_per_hour": lambda v: setattr(settings, 'MAX_CYCLES_PER_HOUR', int(v)),
            "rate_limits.max_actions_per_hour": lambda v: setattr(settings, 'MAX_ACTIONS_PER_HOUR', int(v)),
            "storage.history_retention_days": lambda v: setattr(settings, 'HISTORY_RETENTION_DAYS', int(v)),
            "logging.level": lambda v: setattr(settings, 'LOG_LEVEL', str(v))
        }
        
        if key not in allowed_updates:
            raise HTTPException(
                status_code=400, 
                detail=f"Configuration key '{key}' is not allowed to be updated"
            )
        
        # Validate value based on key
        try:
            if key.startswith("rate_limits.") or key.startswith("processing.") or key.startswith("storage."):
                if not isinstance(value, (int, float)) or value < 0:
                    raise ValueError("Value must be a positive number")
            elif key == "ai.temperature":
                if not isinstance(value, (int, float)) or not (0 <= value <= 2):
                    raise ValueError("Temperature must be between 0 and 2")
            elif key == "logging.level":
                if value not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
                    raise ValueError("Log level must be one of: DEBUG, INFO, WARNING, ERROR, CRITICAL")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid value for {key}: {str(e)}")
        
        # Apply the update
        try:
            allowed_updates[key](value)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to apply update: {str(e)}")
        
        # For some updates, we might need to notify other components
        if key.startswith("processing."):
            # Notify the processing hub of configuration changes
            orchestrator.processing_hub.update_configuration()
        elif key.startswith("rate_limits."):
            # Update rate limiter configuration
            orchestrator.rate_limiter.update_configuration()
        
        return StatusResponse(
            status="success",
            message=f"Configuration updated: {key} = {value}",
            data={"key": key, "value": value},
            timestamp=datetime.now().isoformat()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating configuration: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update configuration: {str(e)}")
