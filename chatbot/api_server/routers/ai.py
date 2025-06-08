"""
AI engine management router for the chatbot API.

This module handles all AI-related endpoints including:
- Getting and managing AI system prompts
- Monitoring AI models and configurations
- Managing AI engine status
"""

from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime
import logging

from chatbot.core.orchestration import MainOrchestrator
from chatbot.config import settings
from ..dependencies import get_orchestrator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["ai"])




@router.get("/prompt")
async def get_ai_prompt(orchestrator: MainOrchestrator = Depends(get_orchestrator)):
    """Get the current AI system prompt."""
    try:
        return {
            "system_prompt": orchestrator.ai_engine.system_prompt,
            "model": orchestrator.ai_engine.model,
            "enabled_tools_count": len(orchestrator.tool_registry.get_enabled_tools()),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting AI prompt: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models")
async def get_ai_models():
    """Get available AI models and current selections."""
    try:
        return {
            "current": {
                "main": settings.AI_MODEL,
                "web_search": settings.WEB_SEARCH_MODEL,
                "summary": settings.AI_SUMMARY_MODEL,
                "multimodal": settings.AI_MULTIMODAL_MODEL
            },
            "available": [
                "openai/gpt-4o-mini",
                "openai/gpt-4o",
                "anthropic/claude-3-sonnet",
                "anthropic/claude-3-haiku",
                "google/gemini-pro",
                "meta-llama/llama-3.1-70b-instruct"
            ],
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting AI models: {e}")
        raise HTTPException(status_code=500, detail=str(e))
