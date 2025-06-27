"""
Adaptive Processor - The Commander AI for Strategic Decision Making

This module implements the "Commander AI" in the Commander/Sub-Agent architecture.
The AdaptiveProcessor focuses on high-level strategy, complex analysis, and delegation
while Sub-Agents handle simple conversational tasks.

The AdaptiveProcessor:
- Analyzes the full world state using node-based compression
- Processes rich ContextualThread objects from the AttentionEngine
- Identifies opportunities for mission delegation
- Handles complex multi-step tasks
- Maintains strategic awareness across all channels
- Delegates simple tasks to MissionProcessor Sub-Agents
"""

import logging
import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .base import Processor
from ..ai_engine import AIDecisionEngine, ActionPlan
from ..node_system.node_manager import NodeManager
from ..node_system.summary_service import NodeSummaryService
from ..world_state.manager import WorldStateManager
from ..world_state.payload_builder import PayloadBuilder
from ...tools.registry import ToolRegistry
from ...tools.base import ActionContext
from ...config import settings

if TYPE_CHECKING:
    from ..attention.structures import ContextualThread

logger = logging.getLogger(__name__)


class AdaptiveProcessor(Processor):
    """
    The Commander AI - handles strategic decisions and complex reasoning.
    
    This processor represents the evolution of the NodeProcessor into a true
    "Commander" that:
    1. Analyzes complex, system-wide state using node compression
    2. Identifies delegation opportunities for simple tasks
    3. Handles strategic planning and multi-step operations
    4. Maintains awareness of all active missions and Sub-Agents
    """
    
    def __init__(
        self,
        node_manager: NodeManager,
        summary_service: NodeSummaryService,
        ai_engine: AIDecisionEngine,
        world_state_manager: WorldStateManager,
        payload_builder: PayloadBuilder,
        tool_registry: ToolRegistry,
        action_context: Optional[ActionContext] = None
    ):
        """
        Initialize the Commander AI.
        
        Args:
            node_manager: Node system for context compression
            summary_service: Summary generation service
            ai_engine: Main AI decision engine (powerful model)
            world_state_manager: World state management
            payload_builder: Payload construction service
            tool_registry: Access to all available tools
            action_context: Context for executing actions
        """
        self.node_manager = node_manager
        self.summary_service = summary_service
        self.ai_engine = ai_engine
        self.world_state_manager = world_state_manager
        self.payload_builder = payload_builder
        self.tool_registry = tool_registry
        self.action_context = action_context
        
        # Strategic awareness settings
        self.enable_mission_delegation = settings.processing.enable_mission_delegation
        self.delegation_cooldown = 300  # 5 minutes between delegation checks
        self.last_delegation_check = 0
        
        # Commander-specific tracking
        self.active_missions_monitored: Dict[str, float] = {}  # mission_id -> last_check_time
        self.strategic_opportunities: List[Dict[str, Any]] = []
        
        logger.info(f"AdaptiveProcessor (Commander AI) initialized")
        logger.info(f"Mission delegation enabled: {self.enable_mission_delegation}")
    
    async def process_cycle(
        self,
        cycle_id: str,
        primary_channel_id: Optional[str],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Process a cycle as the Commander AI.
        
        The Commander focuses on:
        1. Strategic analysis of world state
        2. Identifying delegation opportunities
        3. Complex problem solving
        4. Monitoring Sub-Agent missions
        
        Args:
            cycle_id: Unique identifier for this processing cycle
            primary_channel_id: Primary channel to focus on (may be None for system-wide analysis)
            context: Additional context from ProcessingHub
            
        Returns:
            Processing result with action count and strategic insights
        """
        logger.info(f"AdaptiveProcessor (Commander): Starting strategic cycle {cycle_id}")
        
        try:
            # Phase 1: Strategic Awareness - Analyze world state for opportunities
            strategic_result = await self._analyze_strategic_state(cycle_id, primary_channel_id)
            
            # Phase 2: Delegation Assessment - Check for delegation opportunities
            delegation_result = await self._assess_delegation_opportunities(cycle_id)
            
            # Phase 3: Commander Decision - Make strategic decisions
            decision_result = await self._make_commander_decisions(cycle_id, primary_channel_id, strategic_result, delegation_result)
            
            total_actions = (
                strategic_result.get("actions_executed", 0) +
                delegation_result.get("delegations_created", 0) +
                decision_result.get("actions_executed", 0)
            )
            
            return {
                "cycle_id": cycle_id,
                "success": True,
                "mode": "commander",
                "actions_executed": total_actions,
                "strategic_phase": strategic_result,
                "delegation_phase": delegation_result,
                "decision_phase": decision_result,
                "missions_monitored": len(self.active_missions_monitored),
                "opportunities_identified": len(self.strategic_opportunities)
            }
            
        except Exception as e:
            logger.error(f"AdaptiveProcessor (Commander): Error in cycle {cycle_id}: {e}")
            return {
                "cycle_id": cycle_id,
                "success": False,
                "error": str(e),
                "actions_executed": 0,
                "mode": "commander"
            }
    
    async def _analyze_strategic_state(
        self,
        cycle_id: str,
        primary_channel_id: Optional[str]
    ) -> Dict[str, Any]:
        """
        Analyze the strategic state using node-based compression.
        
        This phase focuses on understanding the big picture:
        - Cross-channel patterns
        - User engagement trends
        - Emerging opportunities
        - System health and performance
        """
        logger.debug(f"AdaptiveProcessor: Strategic analysis phase - cycle {cycle_id}")
        
        try:
            # Get world state and build strategic payload
            world_state_data = self.world_state_manager.get_world_state_data()
            
            # Build a strategic analysis payload using node system
            payload = self.payload_builder.build_node_based_payload(
                world_state_data=world_state_data,
                node_manager=self.node_manager,
                primary_channel_id=primary_channel_id or "strategic_overview",
                config={
                    "bot_fid": settings.farcaster.bot_fid,
                    "bot_username": settings.farcaster.bot_username,
                    "mode": "strategic_analysis"
                }
            )
            
            # Add Commander-specific context
            payload["commander_context"] = {
                "role": "strategic_commander",
                "active_missions": len(world_state_data.missions),
                "channels_with_missions": len([ch for ch in world_state_data.channels.values() if ch.current_mission_id]),
                "last_delegation_check": self.last_delegation_check,
                "strategic_opportunities": self.strategic_opportunities
            }
            
            payload["instructions"] = (
                "STRATEGIC ANALYSIS PHASE: You are the Commander AI responsible for high-level "
                "strategic awareness. Analyze the world state for patterns, opportunities, and "
                "complex situations that require strategic thinking. Look for: 1) Cross-channel "
                "patterns, 2) User engagement trends, 3) Opportunities for value creation, "
                "4) Complex problems requiring multi-step solutions. This is strategic analysis - "
                "focus on understanding rather than immediate action."
            )
            
            # Provide strategic analysis tools
            strategic_tools = ["expand_node", "collapse_node", "pin_node", "refresh_summary", 
                             "assign_mission_to_channel", "web_search", "update_research"]
            strategic_tool_descriptions = []
            for tool_name in strategic_tools:
                tool = self.tool_registry.get_tool(tool_name)
                if tool:
                    strategic_tool_descriptions.append(f"{tool.name}: {tool.description}")
            payload["available_tools"] = "\n".join(strategic_tool_descriptions)
            
            # Get strategic decision
            strategic_cycle_id = f"{cycle_id}_strategic"
            decision_result = await self.ai_engine.make_decision(payload, strategic_cycle_id)
            
            # Execute strategic actions
            actions_executed = 0
            insights = []
            
            if decision_result.selected_actions:
                for action in decision_result.selected_actions:
                    try:
                        success = await self._execute_action(action, strategic_cycle_id)
                        if success:
                            actions_executed += 1
                            # Track delegation actions specifically
                            if action.action_type == "assign_mission_to_channel":
                                insights.append(f"Delegated mission: {action.parameters.get('objective', 'Unknown objective')}")
                    except Exception as e:
                        logger.error(f"AdaptiveProcessor: Error executing strategic action {action.action_type}: {e}")
            
            return {
                "success": True,
                "actions_executed": actions_executed,
                "insights": insights,
                "reasoning": decision_result.reasoning,
                "observations": decision_result.observations
            }
            
        except Exception as e:
            logger.error(f"AdaptiveProcessor: Error in strategic analysis: {e}")
            return {
                "success": False,
                "error": str(e),
                "actions_executed": 0
            }
    
    async def _assess_delegation_opportunities(self, cycle_id: str) -> Dict[str, Any]:
        """
        Assess opportunities for delegating tasks to Sub-Agents.
        
        This phase identifies channels with simple, repetitive, or conversational
        tasks that would be better handled by lightweight Sub-Agents.
        """
        logger.debug(f"AdaptiveProcessor: Delegation assessment phase - cycle {cycle_id}")
        
        try:
            current_time = time.time()
            
            # Check if enough time has passed since last delegation check
            if current_time - self.last_delegation_check < self.delegation_cooldown:
                return {
                    "success": True,
                    "delegations_created": 0,
                    "status": "cooldown",
                    "next_check_in": self.delegation_cooldown - (current_time - self.last_delegation_check)
                }
            
            self.last_delegation_check = current_time
            
            if not self.enable_mission_delegation:
                return {
                    "success": True,
                    "delegations_created": 0,
                    "status": "delegation_disabled"
                }
            
            world_state_data = self.world_state_manager.get_world_state_data()
            delegation_opportunities = []
            
            # Scan channels for delegation opportunities
            for channel_id, channel in world_state_data.channels.items():
                # Skip channels that already have missions
                if channel.current_mission_id:
                    continue
                
                # Look for channels with recent user activity but no bot responses
                if len(channel.recent_messages) >= 2:
                    # Get recent messages that are NOT from the bot
                    recent_user_messages = [
                        msg for msg in channel.recent_messages[-10:] 
                        if not msg.is_from_bot()
                    ]
                    
                    # Only proceed if there are actual user messages
                    if len(recent_user_messages) >= 1:
                        latest_user_msg = recent_user_messages[-1]
                        
                        # Check if this message is actually recent (not older than 10 minutes)
                        current_time = time.time()
                        message_age_minutes = (current_time - latest_user_msg.timestamp) / 60
                        
                        if message_age_minutes > 10:  # Skip old messages
                            continue
                        
                        # CRITICAL: Check if we've already responded to this specific message
                        # Check both action history and message history for replies to this specific message
                        already_responded = False
                        
                        # Check if we have a reply in our message history
                        bot_messages_after_user = [
                            msg for msg in channel.recent_messages
                            if (msg.is_from_bot() and 
                                msg.timestamp > latest_user_msg.timestamp and
                                (msg.reply_to == latest_user_msg.id or 
                                 msg.timestamp - latest_user_msg.timestamp < 300))  # 5 min window
                        ]
                        
                        if bot_messages_after_user:
                            already_responded = True
                            logger.debug(f"Already responded to message {latest_user_msg.id} in {channel_id}")
                         # Double-check using world state manager if available
                        if (not already_responded and 
                            self.world_state_manager and 
                            hasattr(self.world_state_manager, 'has_bot_replied_to_matrix_event')):
                            already_responded = self.world_state_manager.has_bot_replied_to_matrix_event(latest_user_msg.id)
                        
                        # Only create delegation opportunity if we haven't responded yet
                        if not already_responded:
                            # Simple heuristics for delegation
                            if (
                                "?" in latest_user_msg.content or  # Questions
                                any(word in latest_user_msg.content.lower() for word in ["help", "how", "what", "explain"]) or  # Help requests
                                len(latest_user_msg.content) < 200  # Short messages (likely conversational)
                            ):
                                delegation_opportunities.append({
                                    "channel_id": channel_id,
                                    "channel_name": channel.name,
                                    "user_messages": len(recent_user_messages),
                                    "latest_message": latest_user_msg.content[:100] + "..." if len(latest_user_msg.content) > 100 else latest_user_msg.content,
                                    "latest_message_id": latest_user_msg.id,
                                    "suggested_objective": f"Provide helpful responses and engage with users in {channel.name}",
                                    "message_age_minutes": message_age_minutes
                                })
                        else:
                            logger.debug(f"Skipping delegation for {channel_id} - already responded to latest message")
            
            logger.info(f"AdaptiveProcessor: Found {len(delegation_opportunities)} delegation opportunities")
            
            return {
                "success": True,
                "delegations_created": 0,  # Delegation happens in strategic phase
                "opportunities": delegation_opportunities,
                "status": "assessed"
            }
            
        except Exception as e:
            logger.error(f"AdaptiveProcessor: Error in delegation assessment: {e}")
            return {
                "success": False,
                "error": str(e),
                "delegations_created": 0
            }
    
    async def _make_commander_decisions(
        self,
        cycle_id: str,
        primary_channel_id: Optional[str],
        strategic_result: Dict[str, Any],
        delegation_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Make final Commander decisions based on strategic analysis and delegation assessment.
        
        This phase handles complex actions that require the full power of the Commander AI.
        """
        logger.debug(f"AdaptiveProcessor: Commander decision phase - cycle {cycle_id}")
        
        try:
            world_state_data = self.world_state_manager.get_world_state_data()
            
            # Build decision payload
            payload = {
                "commander_role": "final_decision_maker",
                "cycle_id": cycle_id,
                "strategic_insights": strategic_result,
                "delegation_opportunities": delegation_result,
                "system_status": {
                    "timestamp": world_state_data.last_update,
                    "active_missions": len(world_state_data.missions),
                    "total_channels": len(world_state_data.channels),
                    "channels_with_missions": len([ch for ch in world_state_data.channels.values() if ch.current_mission_id])
                },
                "instructions": (
                    "COMMANDER DECISION PHASE: Based on the strategic analysis and delegation "
                    "assessment, make final decisions for this cycle. You can: 1) Take complex "
                    "actions that require strategic thinking, 2) Engage in sophisticated "
                    "conversations, 3) Handle multi-step problems, 4) Coordinate across platforms. "
                    "Focus on actions that require the full power of the Commander AI rather than "
                    "simple conversational tasks that should be delegated."
                )
            }
            
            # Provide full tool access for Commander decisions
            payload["available_tools"] = self.tool_registry.get_tool_descriptions_for_ai()
            
            # Get Commander decision
            commander_cycle_id = f"{cycle_id}_commander"
            decision_result = await self.ai_engine.make_decision(payload, commander_cycle_id)
            
            # Execute Commander actions
            actions_executed = 0
            if decision_result.selected_actions:
                for action in decision_result.selected_actions:
                    try:
                        success = await self._execute_action(action, commander_cycle_id)
                        if success:
                            actions_executed += 1
                    except Exception as e:
                        logger.error(f"AdaptiveProcessor: Error executing commander action {action.action_type}: {e}")
            
            return {
                "success": True,
                "actions_executed": actions_executed,
                "reasoning": decision_result.reasoning,
                "observations": decision_result.observations
            }
            
        except Exception as e:
            logger.error(f"AdaptiveProcessor: Error in commander decisions: {e}")
            return {
                "success": False,
                "error": str(e),
                "actions_executed": 0
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
            tool = self.tool_registry.get_tool(action.action_type)
            if not tool:
                logger.warning(f"AdaptiveProcessor: Unknown tool {action.action_type}")
                return False
            
            if not self.action_context:
                logger.warning(f"AdaptiveProcessor: No ActionContext available for {action.action_type}")
                return False
            
            # Execute through unified tool registry
            result = await tool.execute(action.parameters, self.action_context)
            success = result.get("status") == "success"
            
            if success:
                logger.debug(f"AdaptiveProcessor: Action {action.action_type} succeeded")
                
                # Track mission assignments for monitoring
                if action.action_type == "assign_mission_to_channel":
                    mission_id = result.get("mission_id")
                    if mission_id:
                        self.active_missions_monitored[mission_id] = time.time()
            else:
                logger.warning(f"AdaptiveProcessor: Action {action.action_type} failed: {result.get('error', 'Unknown error')}")
            
            return success
            
        except Exception as e:
            logger.error(f"AdaptiveProcessor: Error executing action {action.action_type}: {e}")
            return False
    
    async def process_contextual_thread(
        self,
        thread: "ContextualThread",
        cycle_id: str
    ) -> Dict[str, Any]:
        """
        Process a ContextualThread with the Commander AI.
        
        This method focuses the Commander's full analytical power on a single
        rich thread context, making intelligent decisions based on the complete
        context provided by the AttentionEngine.
        
        Args:
            thread: ContextualThread containing rich context
            cycle_id: Unique identifier for this processing cycle
            
        Returns:
            Processing result with action count and insights
        """
        logger.info(f"AdaptiveProcessor (Commander): Processing ContextualThread {thread.thread_id}")
        
        try:
            # Build thread-centric payload for Commander AI
            payload = await self._build_thread_centric_payload(thread, cycle_id)
            
            # Get Commander decision focused on this specific thread
            decision_result = await self.ai_engine.make_decision(payload, cycle_id)
            
            # Execute Commander actions
            actions_executed = 0
            if decision_result.selected_actions:
                for action in decision_result.selected_actions:
                    try:
                        success = await self._execute_action(action, cycle_id)
                        if success:
                            actions_executed += 1
                    except Exception as e:
                        logger.error(f"AdaptiveProcessor: Error executing thread action {action.action_type}: {e}")
            
            return {
                "thread_id": thread.thread_id,
                "cycle_id": cycle_id,
                "success": True,
                "mode": "thread_centric_commander",
                "actions_executed": actions_executed,
                "context_score": thread.calculate_context_score(),
                "thread_priority": thread.priority.name,
                "reasoning": decision_result.reasoning,
                "observations": decision_result.observations
            }
            
        except Exception as e:
            logger.error(f"AdaptiveProcessor (Commander): Error processing thread {thread.thread_id}: {e}")
            return {
                "thread_id": thread.thread_id,
                "cycle_id": cycle_id,
                "success": False,
                "error": str(e),
                "actions_executed": 0,
                "mode": "thread_centric_commander"
            }
    
    async def _build_thread_centric_payload(
        self,
        thread: "ContextualThread",
        cycle_id: str
    ) -> Dict[str, Any]:
        """
        Build a focused payload for thread-centric Commander processing.
        
        This creates a highly focused context that gives the Commander AI
        everything it needs to make intelligent decisions about this specific
        conversation thread.
        
        Args:
            thread: The ContextualThread to build payload for
            cycle_id: Cycle identifier
            
        Returns:
            Payload dictionary optimized for thread-centric processing
        """
        try:
            # Get world state for additional context
            world_state_data = self.world_state_manager.get_world_state_data()
            
            # Build focused payload
            payload = {
                "processing_mode": "thread_centric_commander",
                "cycle_id": cycle_id,
                "thread_context": {
                    "thread_id": thread.thread_id,
                    "priority": thread.priority.name,
                    "reason": thread.reason,
                    "context_score": thread.calculate_context_score(),
                    "age_minutes": thread.get_age_minutes()
                },
                "triggering_message": thread.triggering_message.to_ai_summary_dict(),
                "conversation_history": [msg.to_ai_summary_dict() for msg in thread.conversation_history],
                "author_context": self._serialize_author_context(thread.author_context),
                "channel_context": self._serialize_channel_context(thread.channel_context),
                "system_context": {
                    "timestamp": world_state_data.last_update,
                    "active_missions": len(world_state_data.missions),
                    "total_channels": len(world_state_data.channels)
                },
                "instructions": (
                    "THREAD-CENTRIC COMMANDER MODE: You are processing a specific conversation thread "
                    "that has been identified as requiring your attention. The AttentionEngine has already "
                    "filtered out noise and provided you with rich context. Analyze this specific conversation "
                    "and determine the most appropriate response. You can: "
                    "1) Take direct action (reply, react, share media) "
                    "2) Delegate to a Sub-Agent using assign_mission_to_channel "
                    "3) Use strategic tools for complex analysis "
                    "4) Wait if no action is needed. "
                    "Focus on this specific thread - you have complete context."
                )
            }
            
            # Provide full tool access for Commander decisions
            payload["available_tools"] = self.tool_registry.get_tool_descriptions_for_ai()
            
            return payload
            
        except Exception as e:
            logger.error(f"Error building thread-centric payload: {e}")
            # Return minimal payload to prevent complete failure
            return {
                "processing_mode": "thread_centric_commander_error",
                "cycle_id": cycle_id,
                "error": str(e),
                "thread_id": thread.thread_id,
                "instructions": "Error building thread context. Please use wait tool.",
                "available_tools": [{"name": "wait", "description": "Wait and observe without taking action"}]
            }
    
    def _serialize_author_context(self, author_context) -> Optional[Dict[str, Any]]:
        """Serialize author context for AI consumption."""
        if not author_context:
            return None
        
        try:
            from ..world_state.structures import FarcasterUserDetails, MatrixUserDetails
            
            if isinstance(author_context, FarcasterUserDetails):
                return {
                    "platform": "farcaster",
                    "fid": author_context.fid,
                    "username": author_context.username,
                    "display_name": author_context.display_name,
                    "bio": author_context.bio,
                    "follower_count": author_context.follower_count,
                    "power_badge": author_context.power_badge
                }
            elif isinstance(author_context, MatrixUserDetails):
                return {
                    "platform": "matrix",
                    "user_id": author_context.user_id,
                    "display_name": author_context.display_name
                }
        except Exception as e:
            logger.warning(f"Error serializing author context: {e}")
        
        return None
    
    def _serialize_channel_context(self, channel_context) -> Optional[Dict[str, Any]]:
        """Serialize channel context for AI consumption."""
        if not channel_context:
            return None
        
        try:
            return {
                "id": channel_context.id,
                "name": channel_context.name,
                "type": channel_context.type,
                "recent_message_count": len(channel_context.recent_messages),
                "has_active_mission": bool(channel_context.current_mission_id),
                "member_count": getattr(channel_context, 'member_count', None)
            }
        except Exception as e:
            logger.warning(f"Error serializing channel context: {e}")
            return None

    def get_status(self) -> Dict[str, Any]:
        """Get current Commander AI status."""
        return {
            "processor_type": "adaptive_commander",
            "mission_delegation_enabled": self.enable_mission_delegation,
            "missions_monitored": len(self.active_missions_monitored),
            "strategic_opportunities": len(self.strategic_opportunities),
            "last_delegation_check": self.last_delegation_check,
            "delegation_cooldown": self.delegation_cooldown,
            "components": {
                "node_manager_available": self.node_manager is not None,
                "summary_service_available": self.summary_service is not None,
                "ai_engine_available": self.ai_engine is not None,
                "world_state_manager_available": self.world_state_manager is not None,
                "tool_registry_available": self.tool_registry is not None,
                "action_context_available": self.action_context is not None
            }
        }
