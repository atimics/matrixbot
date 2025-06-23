"""
Core tools that don't depend on specific platforms.
"""
import asyncio
import logging
import time
import uuid
from typing import Any, Dict

from .base import ActionContext, ToolInterface

logger = logging.getLogger(__name__)


class WaitTool(ToolInterface):
    """
    Tool for waiting/observing without taking action.
    """

    @property
    def name(self) -> str:
        return "wait"

    @property
    def description(self) -> str:
        return "Do nothing and wait until the next world update or observation cycle. Use this when no immediate action is needed or to see if new information becomes available."

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
    """

    @property
    def name(self) -> str:
        return "set_mission_goal"

    @property
    def description(self) -> str:
        return "Set a high-level mission or goal that will guide your actions across multiple cycles. Use this to establish persistent objectives for complex tasks that require sustained effort."

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
            from ..core.world_state.structures import Mission
            
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
            world_state_data = await context.world_state_manager.get_world_state_data()
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
    P1 FEATURE: Tool for updating the status of the current mission.
    
    Allows the AI to mark missions as completed, failed, or update progress.
    """

    @property
    def name(self) -> str:
        return "update_mission_status"

    @property
    def description(self) -> str:
        return "Update the status of the current mission. Use this to mark missions as completed, failed, or to add progress updates."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["active", "completed", "failed", "paused"],
                    "description": "New status for the mission"
                },
                "add_key_result": {
                    "type": "string",
                    "description": "Add a new key result to the mission",
                    "default": ""
                }
            },
            "required": ["status"]
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """Update the current mission status."""
        try:
            status = params.get("status", "")
            add_key_result = params.get("add_key_result", "")
            
            # Get world state data
            world_state_data = context.world_state_manager.get_state_data()
            
            if not world_state_data.current_mission:
                return {
                    "status": "error", 
                    "message": "No active mission to update"
                }
            
            # Update mission status
            world_state_data.current_mission.update_status(status)
            
            # Add key result if provided
            if add_key_result:
                world_state_data.current_mission.add_key_result(add_key_result)
            
            logger.info(f"Updated mission status to: {status}")
            
            return {
                "status": "success",
                "message": f"Mission status updated to: {status}",
                "mission_id": world_state_data.current_mission.id,
                "new_status": status,
                "key_result_added": add_key_result if add_key_result else None
            }
            
        except Exception as e:
            logger.error(f"Error updating mission status: {e}")
            return {
                "status": "error",
                "message": f"Failed to update mission status: {str(e)}"
            }
