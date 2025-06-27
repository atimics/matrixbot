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
from ..security import require_api_key, validate_admin_access

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai"])

@router.get("/prompt")
async def get_ai_prompt(orchestrator: MainOrchestrator = Depends(get_orchestrator)):
    """Get the current AI system prompt."""
    try:
        if not hasattr(orchestrator, 'ai_engine') or not orchestrator.ai_engine:
            raise HTTPException(status_code=503, detail="AI engine not available")
            
        if not hasattr(orchestrator, 'tool_registry') or not orchestrator.tool_registry:
            tools_count = 0
        else:
            tools_count = len(getattr(orchestrator.tool_registry, 'get_enabled_tools', lambda: [])())
            
        return {
            "system_prompt": getattr(orchestrator.ai_engine, 'system_prompt', 'Not available'),
            "model": getattr(orchestrator.ai_engine, 'model', 'unknown'),
            "enabled_tools_count": tools_count,
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
                "main": settings.processing.ai_model,
                "web_search": settings.web_search_model,
                "summary": settings.ai_summary_model,
                "multimodal": settings.ai_multimodal_model,
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


@router.get("/performance")
async def get_ai_performance(orchestrator: MainOrchestrator = Depends(get_orchestrator)):
    """Get AI engine performance metrics and health status."""
    try:
        from chatbot.core.performance_monitor import performance_monitor
        
        # Get comprehensive performance data
        performance_data = performance_monitor.export_metrics_for_api()
        
        # Add AI engine specific information if available
        if hasattr(orchestrator, 'ai_engine') and orchestrator.ai_engine:
            performance_data["ai_engine"] = {
                "model": getattr(orchestrator.ai_engine, 'model', 'unknown'),
                "max_actions_per_cycle": getattr(orchestrator.ai_engine, 'max_actions_per_cycle', 3),
                "validation_enabled": hasattr(orchestrator.ai_engine, 'validator'),
                "recovery_enabled": hasattr(orchestrator.ai_engine, 'error_recovery'),
                "dynamic_prompts_enabled": hasattr(orchestrator.ai_engine, 'dynamic_prompt_builder')
            }
        else:
            performance_data["ai_engine"] = {"status": "not_available"}
        
        return performance_data
    except Exception as e:
        logger.error(f"Error getting AI performance metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def get_ai_health():
    """Get AI engine health status for monitoring systems."""
    try:
        from chatbot.core.performance_monitor import performance_monitor
        
        health_status = performance_monitor.get_health_status()
        return health_status
    except Exception as e:
        logger.error(f"Error getting AI health status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/performance/reset")
async def reset_ai_performance_metrics(authenticated: bool = Depends(validate_admin_access)):
    """Reset AI performance metrics (admin endpoint)."""
    try:
        from chatbot.core.performance_monitor import performance_monitor
        
        performance_monitor.reset_metrics()
        return {
            "status": "success",
            "message": "AI performance metrics have been reset",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error resetting AI performance metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))
