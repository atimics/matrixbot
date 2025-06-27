"""
Logs and history management router for the chatbot API.

This module handles all logging and history-related endpoints including:
- Getting recent log entries
- Accessing action history
- WebSocket log streaming (handled in main.py)
"""

from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime
import logging

from chatbot.core.orchestration import MainOrchestrator
from ..dependencies import get_orchestrator
from ..schemas import StatusResponse

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api", tags=["logs-history"])


@router.get("/logs/recent")
async def get_recent_logs():
    """Get recent log entries."""
    try:
        # This is a simplified implementation
        # In a real system, you'd want to read from a log file or database
        return {
            "logs": [
                {
                    "timestamp": datetime.now().isoformat(),
                    "level": "INFO",
                    "logger": "chatbot.api",
                    "message": "Recent logs endpoint called",
                    "module": "api_server",
                    "function": "get_recent_logs",
                    "line": 0
                }
            ],
            "count": 1,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting recent logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/actions")
async def get_action_history(orchestrator: MainOrchestrator = Depends(get_orchestrator)):
    """Get recent action history."""
    try:
        actions = []
        for action in orchestrator.world_state.state.action_history.actions[-20:]:  # Last 20 actions
            actions.append({
                "id": action.id,
                "type": action.type,
                "description": action.description,
                "timestamp": action.timestamp.isoformat() if action.timestamp else None,
                "channel_id": action.channel_id,
                "status": action.status,
                "metadata": action.metadata
            })
        
        return {
            "actions": actions,
            "total_actions": len(orchestrator.world_state.state.action_history.actions),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting action history: {e}")
        raise HTTPException(status_code=500, detail=str(e))
