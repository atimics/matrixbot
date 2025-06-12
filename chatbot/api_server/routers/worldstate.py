"""
World state management router for the chatbot API.

This module handles all world state-related endpoints including:
- Getting current world state information
- Managing channel information
- Accessing AI world state payloads
- Executing node-based actions
"""

from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from datetime import datetime
import logging

from chatbot.core.orchestration import MainOrchestrator
from ..dependencies import get_orchestrator
from ..schemas import StatusResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/worldstate", tags=["worldstate"])


class NodeAction(BaseModel):
    """Model for node actions."""
    node_id: str
    action: str  # expand, collapse, pin, unpin, refresh_summary
    force: bool = False


@router.get("")
async def get_world_state(orchestrator: MainOrchestrator = Depends(get_orchestrator)):
    """Get current world state information."""
    try:
        # Get traditional world state
        state_dict = orchestrator.world_state.to_dict()
        
        # Add node-based information if available
        node_info = {}
        if hasattr(orchestrator.processing_hub, 'node_manager') and orchestrator.processing_hub.node_manager:
            node_manager = orchestrator.processing_hub.node_manager
            node_info = {
                "expanded_nodes": list(node_manager.expanded_nodes.keys()),
                "collapsed_summaries": list(node_manager.collapsed_node_summaries.keys()),
                "pinned_nodes": list(node_manager.pinned_nodes),
                "system_events": node_manager.get_system_events()[-10:],  # Last 10 events
                "expansion_status": node_manager.get_expansion_status_summary()
            }
        
        return {
            "traditional_state": state_dict,
            "node_state": node_info,
            "processing_mode": "node_based" if orchestrator.config.processing_config.enable_node_based_processing else "traditional",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting world state: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/channels")
async def get_channels(orchestrator: MainOrchestrator = Depends(get_orchestrator)):
    """Get detailed channel information."""
    try:
        channels = {}
        # Handle nested structure: channels[platform][channel_id]
        for platform, platform_channels in orchestrator.world_state.state.channels.items():
            if isinstance(platform_channels, dict):
                for channel_id, channel in platform_channels.items():
                    channels[channel_id] = {
                        "id": channel.id,
                        "name": channel.name,
                        "platform": channel.type,
                        "message_count": len(channel.recent_messages),
                        "recent_messages": [
                            {
                                "id": msg.id,
                                "content": msg.content[:100] + "..." if len(msg.content) > 100 else msg.content,
                                "author": msg.sender,
                                "timestamp": msg.timestamp,
                                "platform": msg.channel_type
                            }
                            for msg in channel.recent_messages[-5:]  # Last 5 messages
                        ]
                    }
        
        return {
            "channels": channels,
            "total_channels": len(channels),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting channels: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ai-payload")
async def get_ai_world_state_payload(orchestrator: MainOrchestrator = Depends(get_orchestrator)):
    """Get the actual world state payload as used by the AI system."""
    try:
        # Get the payload builder from the orchestrator
        payload_builder = orchestrator.payload_builder
        world_state_data = orchestrator.world_state.state
        
        # Get the current primary channel (if any)
        primary_channel_id = getattr(orchestrator, 'current_primary_channel_id', None)
        
        # Build the actual AI payload
        ai_payload = payload_builder.build_full_payload(
            world_state_data=world_state_data,
            primary_channel_id=primary_channel_id,
            config={
                "optimize_for_size": False,  # Get full detail for API
                "include_detailed_user_info": True,
                "max_messages_per_channel": 10,
                "max_action_history": 10,
                "max_thread_messages": 10,
                "max_other_channels": 10
            }
        )
        
        return {
            "ai_world_state": ai_payload,
            "metadata": {
                "primary_channel_id": primary_channel_id,
                "payload_type": "full",
                "optimization_enabled": False,
                "timestamp": datetime.now().isoformat()
            }
        }
    except Exception as e:
        logger.error(f"Error getting AI world state payload: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/node/action")
async def execute_node_action(
    action: NodeAction,
    orchestrator: MainOrchestrator = Depends(get_orchestrator)
):
    """Execute an action on a node (expand, collapse, pin, unpin, refresh)."""
    try:
        if not hasattr(orchestrator.processing_hub, 'node_manager') or not orchestrator.processing_hub.node_manager:
            raise HTTPException(status_code=400, detail="Node-based processing not available")
        
        node_manager = orchestrator.processing_hub.node_manager
        
        if action.action == "expand":
            await node_manager.expand_node(action.node_id, force=action.force)
        elif action.action == "collapse":
            await node_manager.collapse_node(action.node_id)
        elif action.action == "pin":
            node_manager.pin_node(action.node_id)
        elif action.action == "unpin":
            node_manager.unpin_node(action.node_id)
        elif action.action == "refresh_summary":
            # This would trigger the NodeSummaryService to refresh the summary
            if hasattr(orchestrator.processing_hub, 'node_summary_service'):
                await orchestrator.processing_hub.node_summary_service.refresh_summary(action.node_id)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown action: {action.action}")
        
        return {
            "success": True,
            "action": action.action,
            "node_id": action.node_id,
            "message": f"Action '{action.action}' executed on node '{action.node_id}'"
        }
    except Exception as e:
        logger.error(f"Error executing node action: {e}")
        raise HTTPException(status_code=500, detail=str(e))
