"""
Setup management router for the chatbot API.

This module handles all setup-related endpoints including:
- Starting and managing setup process
- Submitting setup steps
- Resetting setup process
"""

from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from datetime import datetime
import logging

from chatbot.core.orchestration import MainOrchestrator
from ..services import SetupManager
from ..schemas import StatusResponse
from ..dependencies import get_orchestrator, get_setup_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/setup", tags=["setup"])


class SetupSubmission(BaseModel):
    """Model for setup step submissions."""
    step_key: str
    value: Any


@router.get("/start")
async def start_setup(setup_manager: SetupManager = Depends(get_setup_manager)):
    """Start or get the current setup step."""
    try:
        if not setup_manager.is_setup_required():
            return {
                "message": "Setup is already complete!",
                "complete": True,
                "step": None
            }
        
        current_step = setup_manager.get_current_step()
        if current_step:
            return {
                "message": f"Welcome! Let me help you configure your chatbot. {current_step['question']}",
                "complete": False,
                "step": current_step
            }
        else:
            return {
                "message": "Setup is complete!",
                "complete": True,
                "step": None
            }
    except Exception:
        logger.exception("Error starting setup")
        raise HTTPException(status_code=500, detail="Unable to start setup")


@router.post("/submit")
async def submit_setup_step(
    submission: SetupSubmission,
    setup_manager: SetupManager = Depends(get_setup_manager)
):
    """Submit a step in the setup process."""
    try:
        result = setup_manager.submit_step(submission.step_key, submission.value)
        return result
    except Exception:
        logger.exception("Error submitting setup step")
        raise HTTPException(status_code=500, detail="Unable to submit setup step")


@router.post("/reset")
async def reset_setup(setup_manager: SetupManager = Depends(get_setup_manager)):
    """Reset the setup process."""
    try:
        setup_manager.reset_setup()
        return {"success": True, "message": "Setup process has been reset"}
    except Exception:
        logger.exception("Error resetting setup")
        raise HTTPException(status_code=500, detail="Unable to reset setup")


@router.get("/status")
async def get_setup_status(setup_manager: SetupManager = Depends(get_setup_manager)):
    """Get the current setup status."""
    try:
        return setup_manager.get_setup_status()
    except Exception:
        logger.exception("Error getting setup status")
        raise HTTPException(status_code=500, detail="Unable to get setup status")
