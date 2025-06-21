"""
AI engine management router for the chatbot API.

This module handles all AI-related endpoints including:
- Getting and managing AI system prompts
- Monitoring AI models and configurations
- Managing AI engine status
- Analyzing prompt payload sizes
"""

from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime
import logging
import json

from chatbot.core.orchestration import MainOrchestrator
from chatbot.config import settings
from ..dependencies import get_orchestrator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai"])




@router.get("/prompt")
async def get_ai_prompt(orchestrator: MainOrchestrator = Depends(get_orchestrator)):
    """Get the current AI system prompt."""
    try:
        return {
            "system_prompt": orchestrator.ai_engine.base_system_prompt,
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
                "main": settings.ai_model,
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


@router.get("/prompt/analysis")
async def analyze_prompt_payload(orchestrator: MainOrchestrator = Depends(get_orchestrator)):
    """Analyze current AI prompt payload sizes and provide optimization insights."""
    try:
        # Get the base system prompt
        base_system_prompt = orchestrator.ai_engine.base_system_prompt
        
        # Create a sample world state for analysis
        sample_world_state = {
            "current_processing_channel_id": "sample_channel",
            "available_tools": "Sample tool descriptions...",
            "active_channels": ["channel1", "channel2"],
            "recent_messages": ["message1", "message2", "message3"],
            "user_context": {"sample": "data"}
        }
        
        # Build sample user prompt
        user_prompt = f"""Current World State:
{json.dumps(sample_world_state, indent=2)}

Based on this world state, what actions (if any) should you take?"""

        # Calculate sizes
        system_prompt_size = len(base_system_prompt.encode('utf-8'))
        user_prompt_size = len(user_prompt.encode('utf-8'))
        
        # Simulate payload structure
        sample_payload = {
            "model": orchestrator.ai_engine.model,
            "messages": [
                {"role": "system", "content": base_system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 3500
        }
        
        payload_size_bytes = len(json.dumps(sample_payload).encode('utf-8'))
        payload_size_kb = payload_size_bytes / 1024
        
        # Analyze configuration
        config_analysis = {
            "ai_conversation_history_length": settings.AI_CONVERSATION_HISTORY_LENGTH,
            "ai_action_history_length": settings.AI_ACTION_HISTORY_LENGTH,
            "ai_thread_history_length": settings.AI_THREAD_HISTORY_LENGTH,
            "ai_context_token_threshold": settings.AI_CONTEXT_TOKEN_THRESHOLD,
            "ai_enable_prompt_logging": settings.AI_ENABLE_PROMPT_LOGGING,
            "ai_log_full_prompts": settings.AI_LOG_FULL_PROMPTS,
            "ai_log_token_usage": settings.AI_LOG_TOKEN_USAGE
        }
        
        # Provide recommendations
        recommendations = []
        if payload_size_kb > 200:
            recommendations.append("Payload is large (>200KB). Consider reducing AI_CONVERSATION_HISTORY_LENGTH.")
        if payload_size_kb > 300:
            recommendations.append("Payload is very large (>300KB). Consider reducing AI_ACTION_HISTORY_LENGTH and AI_THREAD_HISTORY_LENGTH.")
        if system_prompt_size > 50000:  # 50KB
            recommendations.append("System prompt is large. Consider optimizing prompt sections.")
        if not settings.AI_ENABLE_PROMPT_LOGGING:
            recommendations.append("Enable AI_ENABLE_PROMPT_LOGGING for better debugging.")
        
        return {
            "analysis": {
                "total_payload_size_kb": round(payload_size_kb, 2),
                "total_payload_size_bytes": payload_size_bytes,
                "system_prompt_size_kb": round(system_prompt_size / 1024, 2),
                "user_prompt_size_kb": round(user_prompt_size / 1024, 2),
                "model": orchestrator.ai_engine.model
            },
            "configuration": config_analysis,
            "recommendations": recommendations,
            "payload_thresholds": {
                "warning_kb": 200,
                "critical_kb": 300,
                "openrouter_limit_estimate_kb": 512
            },
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error analyzing prompt payload: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/logging/config")
async def get_logging_config():
    """Get current AI logging configuration."""
    try:
        return {
            "config": {
                "ai_enable_prompt_logging": settings.AI_ENABLE_PROMPT_LOGGING,
                "ai_log_full_prompts": settings.AI_LOG_FULL_PROMPTS,
                "ai_log_token_usage": settings.AI_LOG_TOKEN_USAGE,
                "ai_log_prompt_preview_length": settings.AI_LOG_PROMPT_PREVIEW_LENGTH,
                "log_level": settings.log_level
            },
            "description": {
                "ai_enable_prompt_logging": "Enable detailed prompt size and breakdown logging",
                "ai_log_full_prompts": "Log complete prompts and responses (very verbose)",
                "ai_log_token_usage": "Log token usage and cost estimation",
                "ai_log_prompt_preview_length": "Length of prompt previews when full logging is disabled"
            },
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting logging config: {e}")
        raise HTTPException(status_code=500, detail=str(e))
