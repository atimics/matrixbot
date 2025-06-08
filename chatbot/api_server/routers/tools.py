"""
Tools management router - handles tool configuration and status.
"""

import logging
from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, Depends

from ..schemas import ToolStatusUpdate, StatusResponse
from chatbot.core.orchestration import MainOrchestrator
from ..dependencies import get_orchestrator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tools", tags=["tools"])


@router.get("")
async def get_tools(orchestrator: MainOrchestrator = Depends(get_orchestrator)):
    """Get all available tools and their current status."""
    try:
        tools_info = []
        
        for tool_name in orchestrator.tool_registry.get_tool_names():
            tool = orchestrator.tool_registry.get_tool(tool_name)
            if tool:
                tool_info = {
                    "name": tool_name,
                    "enabled": orchestrator.tool_registry.is_tool_enabled(tool_name),
                    "description": tool.get_description(),
                    "parameters": tool.get_parameters_schema() if hasattr(tool, 'get_parameters_schema') else {},
                    "category": getattr(tool, 'category', 'general'),
                    "last_used": None,  # Could be enhanced to track usage
                    "success_rate": None  # Could be enhanced to track success rates
                }
                tools_info.append(tool_info)
        
        return {
            "tools": tools_info,
            "total_count": len(tools_info),
            "enabled_count": sum(1 for tool in tools_info if tool["enabled"]),
            "stats": orchestrator.tool_registry.get_tool_stats()
        }
        
    except Exception as e:
        logger.error(f"Error getting tools: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get tools: {str(e)}")


@router.put("/{tool_name}/status", response_model=StatusResponse)
async def update_tool_status(
    tool_name: str,
    status_update: ToolStatusUpdate,
    orchestrator: MainOrchestrator = Depends(get_orchestrator)
):
    """Enable or disable a specific tool."""
    try:
        # Check if tool exists
        if not orchestrator.tool_registry.has_tool(tool_name):
            raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")
        
        # Update tool status
        if status_update.enabled:
            orchestrator.tool_registry.enable_tool(tool_name)
            message = f"Tool '{tool_name}' enabled successfully"
        else:
            orchestrator.tool_registry.disable_tool(tool_name)
            message = f"Tool '{tool_name}' disabled successfully"
        
        logger.info(f"Tool status updated: {tool_name} -> enabled={status_update.enabled}")
        
        return StatusResponse(
            status="success",
            message=message,
            data={"tool_name": tool_name, "enabled": status_update.enabled},
            timestamp=datetime.now().isoformat()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating tool status for {tool_name}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update tool status: {str(e)}")


@router.get("/{tool_name}")
async def get_tool_details(
    tool_name: str,
    orchestrator: MainOrchestrator = Depends(get_orchestrator)
):
    """Get detailed information about a specific tool."""
    try:
        # Check if tool exists
        if not orchestrator.tool_registry.has_tool(tool_name):
            raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")
        
        tool = orchestrator.tool_registry.get_tool(tool_name)
        if not tool:
            raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")
        
        # Get tool details
        tool_details = {
            "name": tool_name,
            "enabled": orchestrator.tool_registry.is_tool_enabled(tool_name),
            "description": tool.get_description(),
            "parameters_schema": tool.get_parameters_schema() if hasattr(tool, 'get_parameters_schema') else {},
            "category": getattr(tool, 'category', 'general'),
            "cooldown": getattr(tool, 'cooldown_seconds', None),
            "rate_limits": getattr(tool, 'rate_limits', None),
            "dependencies": getattr(tool, 'dependencies', []),
            "examples": getattr(tool, 'examples', [])
        }
        
        # Get usage statistics if available
        tool_stats = orchestrator.tool_registry.get_tool_stats()
        if tool_name in tool_stats:
            tool_details["usage_stats"] = tool_stats[tool_name]
        
        return tool_details
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting tool details for {tool_name}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get tool details: {str(e)}")
