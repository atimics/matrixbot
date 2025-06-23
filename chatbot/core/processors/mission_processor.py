"""
Mission Processor - Lightweight Sub-Agent for Goal-Oriented Tasks

This module implements the "Sub-Agent" pattern where lightweight processors
handle specific, focused missions in individual channels while the main
Commander AI focuses on complex, system-wide analysis.

The MissionProcessor operates with:
- Minimal context (just the mission and recent channel messages)
- Lightweight AI model for fast, cheap responses
- Goal-oriented prompts focused on mission completion
- Simple conversational interactions
"""

import logging
from typing import Dict, List, Optional, Any

from .base import Processor
from ..ai_engine import ActionPlan
from ..lightweight_ai_engine import LightweightAIEngine
from ..world_state.structures import Mission, WorldStateData
from ...tools.registry import ToolRegistry
from ...tools.base import ActionContext

logger = logging.getLogger(__name__)


class MissionProcessor(Processor):
    """
    A lightweight processor dedicated to fulfilling a single mission in a single channel.
    
    This represents the "Sub-Agent" in the Commander/Sub-Agent architecture.
    It's designed to handle simple, conversational tasks efficiently while the
    main Commander AI handles complex reasoning and system-wide analysis.
    """
    
    def __init__(
        self,
        mission: Mission,
        lightweight_ai_engine: LightweightAIEngine,
        world_state_data: WorldStateData,
        tool_registry: ToolRegistry,
        action_context: Optional[ActionContext] = None
    ):
        """
        Initialize the Mission Processor.
        
        Args:
            mission: The mission this processor is responsible for
            lightweight_ai_engine: Fast, cheap AI engine for conversations
            world_state_data: Snapshot of world state (not the full manager)
            tool_registry: Access to available tools
            action_context: Context for executing actions
        """
        self.mission = mission
        self.ai_engine = lightweight_ai_engine
        self.world_state = world_state_data
        self.tool_registry = tool_registry
        self.action_context = action_context
        
        logger.info(f"MissionProcessor initialized for mission: {mission.id} in channel: {mission.channel_id}")
    
    async def process_cycle(
        self,
        cycle_id: str,
        primary_channel_id: Optional[str],
        context: Optional[Dict[str, Any]] = None
    ) -> List[ActionPlan]:
        """
        Execute one cycle focused solely on the mission objective.
        
        Args:
            cycle_id: Unique identifier for this processing cycle
            primary_channel_id: Should be the channel this mission is assigned to
            context: Additional context (typically unused by Sub-Agents)
            
        Returns:
            List of ActionPlan objects representing the Sub-Agent's decisions
        """
        logger.debug(f"MissionProcessor: Processing cycle {cycle_id} for mission {self.mission.id}")
        
        # Verify mission is still active
        if self.mission.status != 'active':
            logger.info(f"Mission '{self.mission.id}' is not active (status: {self.mission.status}). Skipping.")
            return []
        
        # Verify we're processing the correct channel
        if primary_channel_id != self.mission.channel_id:
            logger.warning(f"MissionProcessor: Channel mismatch. Expected {self.mission.channel_id}, got {primary_channel_id}")
            return []
        
        try:
            # 1. Build focused payload for the lightweight AI
            if primary_channel_id is None:
                logger.warning(f"MissionProcessor: No channel ID provided for mission {self.mission.id}")
                return []
            
            payload = self._build_mission_payload(primary_channel_id)
            
            # 2. Get decision from the lightweight AI
            actions = await self.ai_engine.decide_mission_actions(payload, cycle_id)
            
            # 3. Execute actions through unified tool registry
            executed_actions = []
            for action in actions:
                try:
                    success = await self._execute_action(action, cycle_id)
                    if success:
                        executed_actions.append(action)
                        logger.debug(f"MissionProcessor: Action {action.action_type} executed successfully")
                    else:
                        logger.warning(f"MissionProcessor: Action {action.action_type} failed")
                except Exception as e:
                    logger.error(f"MissionProcessor: Error executing action {action.action_type}: {e}")
            
            logger.info(f"MissionProcessor: Completed cycle {cycle_id}, executed {len(executed_actions)}/{len(actions)} actions")
            return executed_actions
            
        except Exception as e:
            logger.error(f"MissionProcessor: Error in cycle {cycle_id}: {e}")
            return []
    
    def _build_mission_payload(self, channel_id: str) -> Dict[str, Any]:
        """
        Build a minimal, focused payload with only mission context and recent messages.
        
        This is much smaller than the full world state payload used by the Commander AI.
        """
        # Get channel data
        channel_data = self.world_state.channels.get(channel_id)
        if not channel_data:
            logger.warning(f"MissionProcessor: Channel {channel_id} not found in world state")
            return {
                "mission": self._mission_to_dict(),
                "messages": [],
                "channel_id": channel_id,
                "error": "Channel not found"
            }
        
        # Get only the most recent, relevant messages
        recent_messages = channel_data.recent_messages[-10:]  # Last 10 messages
        
        # Convert messages to AI-friendly format
        message_summaries = []
        for msg in recent_messages:
            message_summaries.append({
                "id": msg.id,
                "timestamp": msg.timestamp,
                "author": msg.sender,
                "content": msg.content,
                "reply_to": msg.reply_to,
                "is_from_bot": msg.is_from_bot()
            })
        
        return {
            "mission": self._mission_to_dict(),
            "messages": message_summaries,
            "channel_id": channel_id,
            "channel_name": channel_data.name,
            "cycle_timestamp": self.world_state.last_update
        }
    
    def _mission_to_dict(self) -> Dict[str, Any]:
        """Convert mission to dictionary for AI consumption."""
        return {
            "id": self.mission.id,
            "objective": self.mission.objective,
            "status": self.mission.status,
            "key_results": self.mission.key_results,
            "created_at": self.mission.created_at,
            "updated_at": self.mission.updated_at,
            "priority": self.mission.priority,
            "context": self.mission.context,
            "channel_id": self.mission.channel_id
        }
    
    async def _execute_action(self, action: ActionPlan, cycle_id: str) -> bool:
        """
        Execute an individual action through the unified tool registry.
        
        Args:
            action: The action to execute
            cycle_id: Current cycle identifier for logging
            
        Returns:
            True if action executed successfully, False otherwise
        """
        try:
            # Get tool from registry
            tool = self.tool_registry.get_tool(action.action_type)
            if not tool:
                logger.warning(f"MissionProcessor: Unknown tool {action.action_type}")
                return False
            
            # Execute through unified tool registry
            if not self.action_context:
                logger.warning(f"MissionProcessor: No ActionContext available for {action.action_type}")
                return False
            
            result = await tool.execute(action.parameters, self.action_context)
            success = result.get("status") == "success"
            
            if success:
                logger.debug(f"MissionProcessor: Action {action.action_type} succeeded: {result.get('message', 'No message')}")
            else:
                logger.warning(f"MissionProcessor: Action {action.action_type} failed: {result.get('error', 'Unknown error')}")
            
            return success
            
        except Exception as e:
            logger.error(f"MissionProcessor: Error executing action {action.action_type}: {e}")
            return False
    
    def get_status(self) -> Dict[str, Any]:
        """Get current processor status."""
        return {
            "processor_type": "mission_based",
            "mission_id": self.mission.id,
            "mission_objective": self.mission.objective,
            "mission_status": self.mission.status,
            "assigned_channel": self.mission.channel_id,
            "priority": self.mission.priority,
            "components": {
                "ai_engine_available": self.ai_engine is not None,
                "world_state_available": self.world_state is not None,
                "tool_registry_available": self.tool_registry is not None,
                "action_context_available": self.action_context is not None
            }
        }
