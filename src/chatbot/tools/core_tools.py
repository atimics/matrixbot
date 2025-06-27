"""
Core tools that don't depend on specific platforms.
"""
import logging
import time
import uuid
from typing import Any, Dict

from .base import ActionContext, ToolInterface
from ..core.world_state.structures import Mission

logger = logging.getLogger(__name__)


class WaitTool(ToolInterface):
    """
    Tool for waiting/observing without taking action.
    Basic tool available to all agents.
    """

    @property
    def name(self) -> str:
        return "wait"

    @property
    def description(self) -> str:
        return "Do nothing and wait until the next world update or observation cycle. Use this when no immediate action is needed or to see if new information becomes available."

    @property
    def access_level(self) -> str:
        return 'core'  # Available to all agents

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        # Include optional duration parameter for waiting in seconds
        schema = {
            "type": "object",
            "properties": {
                "duration": {
                    "type": "number",
                    "description": "Duration to wait in seconds",
                    "default": 0
                }
            }
        }
        # Expose duration as top-level key for test compatibility
        schema["duration"] = schema["properties"]["duration"]
        return schema

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """
        Execute the wait action by doing nothing, allowing the main processing
        loop to continue to its next natural cycle.
        """
        message = "Waited for the next observation cycle."
        logger.info(message)

        return {
            "status": "success",
            "message": message,
            "timestamp": time.time(),
            "duration": 0,
        }


class SetMissionGoalTool(ToolInterface):
    """
    P1 FEATURE: Tool for setting high-level goals/missions for multi-cycle task completion.
    
    This enables the AI to set persistent objectives that guide decision-making
    across multiple processing cycles, enabling complex task completion.
    Strategic tool available only to Commander AI.
    """

    @property
    def name(self) -> str:
        return "set_mission_goal"

    @property
    def description(self) -> str:
        return "Set a high-level mission or goal that will guide your actions across multiple cycles. Use this to establish persistent objectives for complex tasks that require sustained effort."

    @property
    def access_level(self) -> str:
        return 'strategic'  # Only available to Commander AI

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "objective": {
                    "type": "string",
                    "description": "Clear description of what needs to be accomplished"
                },
                "key_results": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of specific outcomes or milestones to achieve",
                    "default": []
                },
                "priority": {
                    "type": "integer", 
                    "description": "Priority level (1-10, higher = more important)",
                    "minimum": 1,
                    "maximum": 10,
                    "default": 5
                },
                "context": {
                    "type": "object",
                    "description": "Additional context data for the mission",
                    "default": {}
                }
            },
            "required": ["objective"]
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """Set a new mission goal in the world state."""
        try:
            if not context.world_state_manager:
                return {
                    "status": "error",
                    "message": "World state manager not available"
                }
            
            objective = params.get("objective", "")
            key_results = params.get("key_results", [])
            priority = params.get("priority", 5)
            mission_context = params.get("context", {})
            
            if not objective:
                return {
                    "status": "error",
                    "message": "Mission objective is required"
                }
            
            # Create new mission
            mission = Mission(
                id=str(uuid.uuid4()),
                objective=objective,
                key_results=key_results,
                priority=priority,
                context=mission_context
            )
            
            # Get world state data and set the mission
            world_state_data = context.world_state_manager.get_world_state_data()
            world_state_data.current_mission = mission
            
            logger.info(f"Set new mission goal: {objective}")
            
            return {
                "status": "success",
                "message": f"Mission goal set: {objective}",
                "mission_id": mission.id,
                "objective": objective,
                "key_results": key_results,
                "priority": priority
            }
            
        except Exception as e:
            logger.error(f"Error setting mission goal: {e}")
            return {
                "status": "error",
                "message": f"Failed to set mission goal: {str(e)}"
            }


class UpdateMissionStatusTool(ToolInterface):
    """
    Tool for updating mission status and progress.
    
    This allows Sub-Agents to report progress, mark missions as complete,
    or request assistance from the Commander AI.
    """

    @property
    def name(self) -> str:
        return "update_mission_status"

    @property
    def description(self) -> str:
        return "Update the status or progress of your current mission. Use this to mark a mission as complete, report progress, or request assistance from the Commander AI."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mission_id": {
                    "type": "string",
                    "description": "The ID of the mission to update"
                },
                "status": {
                    "type": "string",
                    "description": "New mission status: 'active', 'completed', 'failed', 'paused'",
                    "enum": ["active", "completed", "failed", "paused"]
                },
                "progress_note": {
                    "type": "string",
                    "description": "Optional note about progress or completion"
                },
                "request_assistance": {
                    "type": "boolean",
                    "description": "Set to true to request assistance from the Commander AI",
                    "default": False
                }
            },
            "required": ["mission_id", "status"]
        }

    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        """
        Update mission status and optionally request assistance.
        
        Args:
            params: Update parameters including mission_id, status, etc.
            context: Action context containing world state manager
            
        Returns:
            Result of mission update
        """
        try:
            mission_id = params["mission_id"]
            new_status = params["status"]
            progress_note = params.get("progress_note", "")
            request_assistance = params.get("request_assistance", False)

            if not context.world_state_manager:
                return {
                    "status": "error",
                    "error": "No world state manager available"
                }

            # Get current world state
            world_state_data = context.world_state_manager.get_world_state_data()

            # Find the mission
            mission = world_state_data.missions.get(mission_id)
            if not mission:
                return {
                    "status": "error",
                    "error": f"Mission {mission_id} not found"
                }

            # Update mission status
            old_status = mission.status
            mission.update_status(new_status)

            # Add progress note if provided
            if progress_note:
                mission.context["progress_notes"] = mission.context.get("progress_notes", [])
                mission.context["progress_notes"].append({
                    "timestamp": time.time(),
                    "note": progress_note
                })

            # Handle assistance request
            if request_assistance:
                mission.context["assistance_requested"] = True
                mission.context["assistance_request_time"] = time.time()

            # If mission is completed or failed, clear it from the channel
            if new_status in ["completed", "failed"]:
                if mission.channel_id:
                    channel = world_state_data.channels.get(mission.channel_id)
                    if channel and channel.current_mission_id == mission_id:
                        channel.current_mission_id = None

            logger.info(f"UpdateMissionStatusTool: Mission {mission_id} status changed from {old_status} to {new_status}")

            result = {
                "status": "success",
                "message": f"Mission {mission_id} status updated to {new_status}",
                "old_status": old_status,
                "new_status": new_status
            }

            if progress_note:
                result["progress_note"] = progress_note

            if request_assistance:
                result["assistance_requested"] = True
                result["message"] += ". Assistance requested from Commander AI."

            return result

        except Exception as e:
            logger.error(f"UpdateMissionStatusTool: Error updating mission: {e}")
            return {
                "status": "error",
                "error": f"Failed to update mission: {str(e)}"
            }


class AssignMissionTool(ToolInterface):
    """
    Tool for assigning missions to channels for Sub-Agent processing.
    
    This allows the Commander AI to delegate simple, conversational tasks
    to lightweight Sub-Agents while focusing on complex analysis.
    """

    @property
    def name(self) -> str:
        return "assign_mission_to_channel"

    @property
    def description(self) -> str:
        return "Assign a simple, conversational task to a dedicated Sub-Agent for a specific channel. Use this for tasks like answering questions on a topic, guiding a user, or managing a simple workflow. The Sub-Agent will handle all interactions in that channel until the mission is complete."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "channel_id": {
                    "type": "string",
                    "description": "The channel to assign the mission to"
                },
                "objective": {
                    "type": "string", 
                    "description": "A clear, concise instruction for the Sub-Agent (e.g., 'Answer user questions about the new pricing model')"
                },
                "tool_scope": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of tool names the Sub-Agent is allowed to use (e.g., ['send_matrix_message', 'react_to_message'])",
                    "default": ["send_matrix_message", "react_to_message", "wait"]
                },
                "mission_duration_hours": {
                    "type": "integer",
                    "description": "How long the mission should be active (default: 1 hour)",
                    "default": 1
                },
                "priority": {
                    "type": "integer",
                    "description": "Mission priority from 1-10 (default: 5)",
                    "default": 5
                }
            },
            "required": ["channel_id", "objective"]
        }

    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        """
        Create and assign a mission to a channel.
        
        Args:
            params: Mission parameters including channel_id, objective, etc.
            context: Action context containing world state manager
            
        Returns:
            Result of mission assignment
        """
        try:
            channel_id = params["channel_id"]
            objective = params["objective"]
            tool_scope = params.get("tool_scope", ["send_matrix_message", "react_to_message", "wait"])
            duration_hours = params.get("mission_duration_hours", 1)
            priority = params.get("priority", 5)

            if not context.world_state_manager:
                return {
                    "status": "error",
                    "error": "No world state manager available"
                }

            # Get current world state
            world_state_data = context.world_state_manager.get_world_state_data()

            # Check if channel exists
            if channel_id not in world_state_data.channels:
                return {
                    "status": "error",
                    "error": f"Channel {channel_id} not found in world state"
                }

            channel = world_state_data.channels[channel_id]

            # Check if channel already has an active mission
            if channel.current_mission_id:
                existing_mission = world_state_data.missions.get(channel.current_mission_id)
                if existing_mission and existing_mission.status == "active":
                    return {
                        "status": "error",
                        "error": f"Channel {channel_id} already has an active mission: {existing_mission.objective}"
                    }

            # Create the mission
            mission = Mission(
                id=str(uuid.uuid4()),
                objective=objective,
                channel_id=channel_id,
                priority=priority,
                tool_scope=tool_scope,
                context={
                    "duration_hours": duration_hours,
                    "created_by": "commander_ai",
                    "channel_name": channel.name
                }
            )

            # Add mission to world state
            world_state_data.missions[mission.id] = mission

            # Assign mission to channel
            channel.current_mission_id = mission.id

            logger.info(f"AssignMissionTool: Created mission {mission.id} for channel {channel_id}: {objective}")

            return {
                "status": "success",
                "message": f"Mission '{objective}' assigned to channel {channel_id}",
                "mission_id": mission.id,
                "duration_hours": duration_hours
            }

        except Exception as e:
            logger.error(f"AssignMissionTool: Error assigning mission: {e}")
            return {
                "status": "error",
                "error": f"Failed to assign mission: {str(e)}"
            }
