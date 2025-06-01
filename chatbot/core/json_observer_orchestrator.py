"""
Enhanced JSON Orchestrator with Node Management

This orchestrator integrates the JSON Observer and Interactive Executor pattern
with the existing chatbot system, providing expandable/collapsible nodes,
LRU auto-collapse, and AI-driven exploration.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from chatbot.config import settings
from chatbot.core.ai_engine import AIDecisionEngine
from chatbot.core.enhanced_world_state_manager import EnhancedWorldStateManager
from chatbot.core.node_interaction_tools import NodeInteractionTools
from chatbot.core.node_summary_service import NodeSummaryService

logger = logging.getLogger(__name__)


class JsonObserverOrchestrator:
    """
    Enhanced orchestrator that implements the JSON Observer and Interactive Executor pattern.
    
    This orchestrator:
    1. Manages expandable/collapsible nodes in the world state
    2. Provides AI tools for node interaction (expand, collapse, pin, unpin)
    3. Generates AI summaries for collapsed nodes
    4. Implements LRU auto-collapse with pinning support
    5. Optionally supports two-phase AI processing (exploration + action)
    """
    
    def __init__(
        self,
        world_state_manager: EnhancedWorldStateManager,
        ai_engine: AIDecisionEngine,
        api_key: str
    ):
        self.world_state_manager = world_state_manager
        self.ai_engine = ai_engine
        
        # Initialize node summary service
        self.summary_service = NodeSummaryService(
            api_key=api_key,
            model=settings.AI_SUMMARY_MODEL
        )
        self.world_state_manager.set_summary_service(self.summary_service)
        
        # Initialize node interaction tools
        self.node_tools = NodeInteractionTools(world_state_manager.node_manager)
        
        # Add node tools to AI engine
        self._register_node_tools()
        
        # Track recent node actions for logging
        self.recent_node_actions: List[Dict[str, Any]] = []
        
        # Configuration for two-phase processing
        self.enable_two_phase = settings.ENABLE_TWO_PHASE_AI_PROCESS
        self.max_exploration_rounds = settings.MAX_EXPLORATION_ROUNDS
        
        logger.info("JsonObserverOrchestrator initialized successfully")
        self.max_exploration_rounds = settings.MAX_EXPLORATION_ROUNDS
    
    def _register_node_tools(self):
        """Register node interaction tools with the AI engine."""
        node_tool_definitions = self.node_tools.get_tool_definitions()
        
        # Update the AI engine's system prompt to include node tools
        node_tools_description = self._generate_node_tools_description()
        
        # Add to the AI engine's dynamic tool prompt
        current_prompt = getattr(self.ai_engine, 'dynamic_tool_prompt_part', '')
        
        if "NODE INTERACTION TOOLS" not in current_prompt:
            self.ai_engine.dynamic_tool_prompt_part = current_prompt + "\n\n" + node_tools_description
            self.ai_engine._build_full_system_prompt()
        
        logger.info("Registered node interaction tools with AI engine")
    
    def _generate_node_tools_description(self) -> str:
        """Generate description of node tools for AI system prompt."""
        return f"""
NODE INTERACTION TOOLS:

You can now interact with the world state through an advanced node expansion system that helps manage context size and focus your attention on relevant information.

The world state is organized into nodes that can be:
- EXPANDED: View full details (limited to {settings.MAX_EXPANDED_NODES} simultaneously)
- COLLAPSED: View AI-generated summaries only
- PINNED: Prevent auto-collapse when expansion limit reached
- UNPINNED: Allow auto-collapse when needed

Available Node Tools:
- expand_node(node_path): Expand a collapsed node to see full details
- collapse_node(node_path): Collapse an expanded node to save space
- pin_node(node_path): Mark a node as important (won't auto-collapse)
- unpin_node(node_path): Remove pin status (can auto-collapse)
- refresh_summary(node_path): Request new AI summary for a node
- get_expansion_status(): See current expansion state and limits

Auto-Collapse Behavior:
When you expand a node and the limit ({settings.MAX_EXPANDED_NODES}) is reached, the oldest unpinned expanded node will automatically collapse. Pin important nodes to keep them accessible across multiple decision cycles.

Node Path Examples:
- channels.matrix.!room_id (Matrix channel)
- channels.farcaster.channel_name (Farcaster channel)
- users.farcaster.123456 (Farcaster user profile)
- users.matrix.username (Matrix user)
- threads.farcaster.0xhash (Farcaster thread)
- system.notifications (System notifications)
- system.rate_limits (API rate limit status)

Usage Strategy:
1. Start by examining collapsed node summaries
2. Expand nodes that seem relevant to your current task
3. Pin nodes you'll need to reference multiple times
4. Collapse nodes when you're done with them
5. Use refresh_summary if a node's summary seems outdated

The payload you receive will show:
- expanded_nodes: Full data for currently expanded nodes
- collapsed_node_summaries: AI summaries for collapsed nodes
- expansion_status: Current expansion limits and usage
- system_events: Recent auto-collapses and other system actions
"""
    
    async def process_decision_cycle(
        self,
        primary_channel_id: str,
        bot_fid: Optional[int] = None,
        bot_username: Optional[str] = None,
        cycle_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Process a complete decision cycle with node management.
        
        This implements either single-phase or two-phase processing based on configuration.
        """
        cycle_id = cycle_id or f"cycle_{len(self.recent_node_actions)}"
        
        try:
            # Step 1: Update summaries for any changed collapsed nodes
            logger.info("Updating node summaries for changed data...")
            await self.world_state_manager.update_summaries_for_changed_nodes()
            
            # Step 2: Get AI-optimized payload with node system
            logger.info("Generating AI payload with node expansion system...")
            world_state_payload = self.world_state_manager.get_ai_optimized_payload_with_nodes(
                primary_channel_id=primary_channel_id,
                bot_fid=bot_fid,
                bot_username=bot_username
            )
            
            # Step 3: Process based on configuration
            if settings.ENABLE_TWO_PHASE_AI_PROCESS:
                return await self._process_two_phase_cycle(
                    world_state_payload, cycle_id, primary_channel_id, bot_fid, bot_username
                )
            else:
                return await self._process_single_phase_cycle(
                    world_state_payload, cycle_id
                )
                
        except Exception as e:
            logger.error(f"Error in decision cycle {cycle_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "cycle_id": cycle_id,
                "node_actions": [],
                "ai_actions": []
            }
    
    async def _process_single_phase_cycle(
        self,
        world_state_payload: Dict[str, Any],
        cycle_id: str
    ) -> Dict[str, Any]:
        """Process a single-phase decision cycle where node and action tools are available together."""
        
        logger.info(f"Processing single-phase cycle {cycle_id}")
        
        # Make AI decision with full tool access
        decision_result = await self.ai_engine.make_decision(world_state_payload, cycle_id)
        
        # Process any node actions first
        node_actions = []
        remaining_actions = []
        
        for action in decision_result.selected_actions:
            if action.action_type in ["expand_node", "collapse_node", "pin_node", "unpin_node", "refresh_summary", "get_expansion_status"]:
                # Execute node action
                result = self.node_tools.execute_tool(action.action_type, action.parameters)
                node_actions.append({
                    "action": action.action_type,
                    "parameters": action.parameters,
                    "result": result,
                    "reasoning": action.reasoning
                })
            else:
                remaining_actions.append(action)
        
        # Log node actions
        if node_actions:
            self.recent_node_actions.extend(node_actions)
            # Keep only recent actions
            self.recent_node_actions = self.recent_node_actions[-20:]
            
            logger.info(f"Executed {len(node_actions)} node actions in cycle {cycle_id}")
            for action in node_actions:
                logger.debug(f"  {action['action']}: {action['result'].get('message', 'No message')}")
        
        return {
            "success": True,
            "cycle_id": cycle_id,
            "decision_result": decision_result,
            "node_actions": node_actions,
            "remaining_ai_actions": remaining_actions,
            "expansion_status": self.world_state_manager.node_manager.get_expansion_status_summary()
        }
    
    async def _process_two_phase_cycle(
        self,
        world_state_payload: Dict[str, Any],
        cycle_id: str,
        primary_channel_id: str,
        bot_fid: Optional[int],
        bot_username: Optional[str]
    ) -> Dict[str, Any]:
        """Process a two-phase decision cycle (exploration phase + action phase)."""
        
        logger.info(f"Processing two-phase cycle {cycle_id}")
        
        # Phase A: Exploration Phase
        exploration_actions = []
        
        for round_num in range(settings.MAX_EXPLORATION_ROUNDS):
            logger.info(f"Exploration round {round_num + 1}/{settings.MAX_EXPLORATION_ROUNDS}")
            
            # Create exploration-focused prompt
            exploration_payload = world_state_payload.copy()
            exploration_payload["phase"] = "exploration"
            exploration_payload["round"] = round_num + 1
            exploration_payload["max_rounds"] = settings.MAX_EXPLORATION_ROUNDS
            exploration_payload["instruction"] = (
                "EXPLORATION PHASE: Use node tools (expand_node, collapse_node, pin_node, unpin_node, refresh_summary) "
                "to explore the world state and gather the information you need. "
                "Signal completion by including 'EXPLORATION_COMPLETE' in your reasoning when ready for actions."
            )
            
            # Make exploration decision
            exploration_decision = await self.ai_engine.make_decision(exploration_payload, f"{cycle_id}_explore_{round_num}")
            
            # Process only node actions in exploration phase
            round_node_actions = []
            exploration_complete = False
            
            for action in exploration_decision.selected_actions:
                if action.action_type in ["expand_node", "collapse_node", "pin_node", "unpin_node", "refresh_summary", "get_expansion_status"]:
                    result = self.node_tools.execute_tool(action.action_type, action.parameters)
                    round_node_actions.append({
                        "action": action.action_type,
                        "parameters": action.parameters,
                        "result": result,
                        "reasoning": action.reasoning
                    })
            
            exploration_actions.extend(round_node_actions)
            
            # Check if AI signaled completion
            if "EXPLORATION_COMPLETE" in exploration_decision.reasoning:
                logger.info(f"AI signaled exploration complete in round {round_num + 1}")
                exploration_complete = True
                break
            
            # If no node actions were taken, assume exploration is complete
            if not round_node_actions:
                logger.info(f"No node actions in round {round_num + 1}, ending exploration")
                exploration_complete = True
                break
            
            # Update world state payload for next round if continuing
            if round_num < settings.MAX_EXPLORATION_ROUNDS - 1:
                # Re-generate payload with updated node states
                await self.world_state_manager.update_summaries_for_changed_nodes()
                world_state_payload = self.world_state_manager.get_ai_optimized_payload_with_nodes(
                    primary_channel_id=primary_channel_id,
                    bot_fid=bot_fid,
                    bot_username=bot_username
                )
        
        # Phase B: Action Phase
        logger.info("Starting action phase with explored world state")
        
        # Generate final payload for action phase
        await self.world_state_manager.update_summaries_for_changed_nodes()
        action_payload = self.world_state_manager.get_ai_optimized_payload_with_nodes(
            primary_channel_id=primary_channel_id,
            bot_fid=bot_fid,
            bot_username=bot_username
        )
        
        action_payload["phase"] = "action"
        action_payload["instruction"] = (
            "ACTION PHASE: Based on your exploration, now take concrete actions. "
            "Focus on action tools (send_message, generate_image, etc.) rather than node tools."
        )
        
        # Make action decision
        action_decision = await self.ai_engine.make_decision(action_payload, f"{cycle_id}_action")
        
        # Filter out node tools from action phase
        ai_actions = [
            action for action in action_decision.selected_actions
            if action.action_type not in ["expand_node", "collapse_node", "pin_node", "unpin_node", "refresh_summary", "get_expansion_status"]
        ]
        
        # Log exploration actions
        if exploration_actions:
            self.recent_node_actions.extend(exploration_actions)
            self.recent_node_actions = self.recent_node_actions[-20:]
        
        return {
            "success": True,
            "cycle_id": cycle_id,
            "exploration_actions": exploration_actions,
            "action_decision": action_decision,
            "ai_actions": ai_actions,
            "exploration_rounds": round_num + 1,
            "expansion_status": self.world_state_manager.node_manager.get_expansion_status_summary()
        }
    
    def get_recent_node_activity_summary(self) -> Dict[str, Any]:
        """Get a summary of recent node management activity for debugging/monitoring."""
        return {
            "recent_actions": self.recent_node_actions[-10:],
            "expansion_status": self.world_state_manager.node_manager.get_expansion_status_summary(),
            "total_actions_processed": len(self.recent_node_actions)
        }
    
    def get_node_tools(self) -> List[Any]:
        """Get all node interaction tools for registration with the main tool registry."""
        return self.node_tools.get_all_tools()
    
    async def get_status(self) -> Dict[str, Any]:
        """Get comprehensive status of the JSON Observer orchestrator."""
        return {
            "summary_service_available": self.summary_service is not None,
            "node_tools_count": len(self.node_tools.get_all_tools()),
            "expansion_status": self.world_state_manager.node_manager.get_expansion_status_summary(),
            "recent_activity": self.get_recent_node_activity_summary(),
            "enable_two_phase": self.enable_two_phase,
            "max_exploration_rounds": self.max_exploration_rounds
        }
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get metrics about node management for monitoring."""
        return {
            "node_manager": self.world_state_manager.node_manager.get_expansion_status_summary(),
            "recent_actions": len(self.recent_node_actions),
            "summary_service": {
                "available": self.summary_service is not None,
                "model": settings.AI_SUMMARY_MODEL if self.summary_service else None
            }
        }
