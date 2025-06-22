"""
Node Processor with OODA Loop Implementation

This module implements the two-phase OODA (Observe, Orient, Decide, Act) loop that 
significantly reduces context explosion and guides AI reasoning.

Phase 1: Orient - AI receives only collapsed node summaries and uses expand_node tool
Phase 2: Decide/Act - AI receives expanded nodes and can use external action tools

This pattern ensures the AI first explores and understands the context before taking actions.
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional

from chatbot.config import settings
from .node_manager import NodeManager
from .summary_service import NodeSummaryService  
from .interaction_tools import NodeInteractionTools
from ..ai_engine import AIDecisionEngine, DecisionResult
from ..world_state.manager import WorldStateManager
from ..world_state.payload_builder import PayloadBuilder
from ...tools.registry import ToolRegistry
from ...tools.base import ActionContext

logger = logging.getLogger(__name__)


class NodeProcessor:
    """
    Node-based processor implementing two-phase OODA loop for context compression.
    
    This processor dramatically reduces AI context size by implementing:
    1. Orient Phase: AI sees only collapsed summaries, must use expand_node to explore
    2. Decide/Act Phase: AI sees expanded nodes and can use full action toolset
    
    This approach reduces context explosion and guides systematic AI reasoning.
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
        self.node_manager = node_manager
        self.summary_service = summary_service
        self.ai_engine = ai_engine
        self.world_state_manager = world_state_manager
        self.payload_builder = payload_builder
        self.tool_registry = tool_registry
        self.action_context = action_context
        
        # Create node interaction tools (legacy compatibility - now deprecated)
        self.node_tools = NodeInteractionTools(node_manager)
        
        # Phase control
        self.enable_two_phase = settings.ENABLE_TWO_PHASE_AI_PROCESS
        self.max_exploration_rounds = settings.MAX_EXPLORATION_ROUNDS
        
        logger.info(f"NodeProcessor initialized (two-phase: {self.enable_two_phase})")
        logger.info("Note: Node tools are now executed through unified ToolRegistry pipeline")
    
    async def process_cycle(
        self, 
        cycle_id: str, 
        primary_channel_id: Optional[str],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Process a cycle using the node-based OODA loop approach.
        
        Args:
            cycle_id: Unique identifier for this processing cycle
            primary_channel_id: Primary channel to focus on
            context: Additional context from ProcessingHub
            
        Returns:
            Processing result with action count and status
        """
        logger.info(f"NodeProcessor: Starting cycle {cycle_id} (two-phase: {self.enable_two_phase})")
        
        try:
            if self.enable_two_phase:
                return await self._process_two_phase_cycle(cycle_id, primary_channel_id, context)
            else:
                return await self._process_single_phase_cycle(cycle_id, primary_channel_id, context)
                
        except Exception as e:
            logger.error(f"NodeProcessor: Error in cycle {cycle_id}: {e}")
            return {
                "cycle_id": cycle_id,
                "success": False,
                "error": str(e),
                "actions_executed": 0,
                "phases_completed": 0
            }
    
    async def _process_two_phase_cycle(
        self, 
        cycle_id: str, 
        primary_channel_id: Optional[str],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute the two-phase OODA loop: Orient then Decide/Act.
        
        Phase 1 (Orient): AI sees only collapsed summaries, uses expand_node to explore
        Phase 2 (Decide/Act): AI sees expanded nodes, uses full action toolset
        """
        total_actions = 0
        phases_completed = 0
        
        # Refresh node summaries for collapsed nodes
        await self._refresh_stale_summaries()
        
        # Phase 1: Orient - Exploration with summaries only
        logger.info(f"NodeProcessor: Phase 1 (Orient) - cycle {cycle_id}")
        
        orient_result = await self._execute_orient_phase(cycle_id, primary_channel_id)
        total_actions += orient_result.get("expansion_actions", 0)
        phases_completed = 1
        
        if orient_result.get("success", False):
            # Phase 2: Decide/Act - Full decision making with expanded context
            logger.info(f"NodeProcessor: Phase 2 (Decide/Act) - cycle {cycle_id}")
            
            decide_result = await self._execute_decide_act_phase(cycle_id, primary_channel_id)
            total_actions += decide_result.get("external_actions", 0)
            phases_completed = 2
            
            return {
                "cycle_id": cycle_id,
                "success": True,
                "actions_executed": total_actions,
                "phases_completed": phases_completed,
                "orient_phase": orient_result,
                "decide_phase": decide_result,
                "mode": "two_phase"
            }
        else:
            logger.warning(f"NodeProcessor: Orient phase failed for cycle {cycle_id}")
            return {
                "cycle_id": cycle_id,
                "success": False,
                "actions_executed": total_actions,
                "phases_completed": phases_completed,
                "error": "Orient phase failed",
                "mode": "two_phase"
            }
    
    async def _process_single_phase_cycle(
        self, 
        cycle_id: str, 
        primary_channel_id: Optional[str],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute single-phase processing (traditional node-based without OODA separation).
        
        This is a fallback mode where AI gets both node tools and external tools simultaneously.
        """
        logger.info(f"NodeProcessor: Single-phase cycle {cycle_id}")
        
        # Build payload with current node state
        world_state_data = self.world_state_manager.get_world_state_data()
        payload = self.payload_builder.build_node_based_payload(
            world_state_data=world_state_data,
            node_manager=self.node_manager,
            primary_channel_id=primary_channel_id or "unknown",
            config={
                "bot_fid": settings.FARCASTER_BOT_FID,
                "bot_username": settings.FARCASTER_BOT_USERNAME
            }
        )
        
        # Add all available tools through unified ToolRegistry
        payload["available_tools"] = self.tool_registry.get_tool_descriptions_for_ai()
        
        # Get AI decision
        decision_result = await self.ai_engine.make_decision(payload, cycle_id)
        
        if not decision_result.selected_actions:
            logger.debug(f"NodeProcessor: No actions selected in cycle {cycle_id}")
            return {
                "cycle_id": cycle_id,
                "success": True,
                "actions_executed": 0,
                "phases_completed": 1,
                "mode": "single_phase"
            }
        
        # Execute selected actions through unified pipeline
        actions_executed = 0
        for action in decision_result.selected_actions:
            try:
                success = await self._execute_action(action, cycle_id)
                if success:
                    actions_executed += 1
            except Exception as e:
                logger.error(f"NodeProcessor: Error executing action {action.action_type}: {e}")
        
        return {
            "cycle_id": cycle_id,
            "success": True,
            "actions_executed": actions_executed,
            "phases_completed": 1,
            "mode": "single_phase"
        }
    
    async def _execute_orient_phase(
        self, 
        cycle_id: str, 
        primary_channel_id: Optional[str]
    ) -> Dict[str, Any]:
        """
        Execute Phase 1: Orient - AI explores using only collapsed summaries.
        
        In this phase, the AI:
        1. Sees only collapsed node summaries
        2. Can only use node interaction tools (expand_node, collapse_node, etc.)
        3. Must decide what context to expand for decision making
        
        Returns:
            Dict with success status and expansion actions taken
        """
        world_state_data = self.world_state_manager.get_world_state_data()
        
        # Build minimal payload with collapsed summaries only
        payload = {
            "current_processing_channel_id": primary_channel_id or "unknown",
            "system_status": {
                "timestamp": world_state_data.last_update,
                "rate_limits": world_state_data.rate_limits
            },
            "expansion_status": self.node_manager.get_expansion_status_summary(),
            "system_events": self.node_manager.get_system_events(),
            "phase": "orient",
            "instructions": (
                "ORIENT PHASE: You are in exploration mode. Examine the collapsed_node_summaries "
                "and use expand_node to explore nodes that seem relevant for understanding the "
                "current situation. You cannot take external actions in this phase - only node "
                "exploration. Focus on expanding nodes that will help you understand what's "
                "happening and what actions might be needed."
            )
        }
        
        # Get all node paths and build collapsed summaries
        all_node_paths = self.payload_builder._get_node_paths_from_world_state(world_state_data)
        collapsed_node_summaries = {}
        
        for node_path in all_node_paths:
            metadata = self.node_manager.get_node_metadata(node_path)
            node_data = self.payload_builder._get_node_data_by_path(world_state_data, node_path)
            
            if node_data is None:
                continue
            
            if not metadata.is_expanded:
                # Include summary for collapsed nodes
                summary = metadata.ai_summary or f"Node {node_path} (no summary available)"
                data_changed = self.node_manager.is_data_changed(node_path, node_data)
                
                collapsed_node_summaries[node_path] = {
                    "summary": summary,
                    "data_changed": data_changed,
                    "last_summary_update": metadata.last_summary_update_ts
                }
        
        payload["collapsed_node_summaries"] = collapsed_node_summaries
        
        # Show currently expanded nodes (if any) but without full data
        expanded_nodes = {}
        for node_path in all_node_paths:
            metadata = self.node_manager.get_node_metadata(node_path)
            if metadata.is_expanded:
                expanded_nodes[node_path] = {
                    "status": "expanded",
                    "is_pinned": metadata.is_pinned,
                    "last_expanded": metadata.last_expanded_ts
                }
        payload["expanded_nodes"] = expanded_nodes
        
        # Only provide node interaction tools in orient phase (get descriptions from ToolRegistry)
        node_tool_names = ["expand_node", "collapse_node", "pin_node", "unpin_node", "refresh_summary", "get_expansion_status"]
        node_tools_descriptions = []
        for tool_name in node_tool_names:
            tool = self.tool_registry.get_tool(tool_name)
            if tool:
                node_tools_descriptions.append(f"{tool.name}: {tool.description}")
        payload["available_tools"] = "\n".join(node_tools_descriptions)
        
        # Execute orient decision
        orient_cycle_id = f"{cycle_id}_orient"
        decision_result = await self.ai_engine.make_decision(payload, orient_cycle_id)
        
        expansion_actions = 0
        if decision_result.selected_actions:
            for action in decision_result.selected_actions:
                try:
                    # Only execute node interaction tools in orient phase, use unified pipeline
                    if action.action_type in ["expand_node", "collapse_node", "pin_node", "unpin_node", "refresh_summary"]:
                        success = await self._execute_action(action, cycle_id)
                        if success:
                            expansion_actions += 1
                            logger.debug(f"NodeProcessor: Orient action {action.action_type} succeeded")
                        else:
                            logger.warning(f"NodeProcessor: Orient action {action.action_type} failed")
                    else:
                        logger.warning(f"NodeProcessor: Ignoring non-node action {action.action_type} in orient phase")
                except Exception as e:
                    logger.error(f"NodeProcessor: Error executing orient action {action.action_type}: {e}")
        
        return {
            "success": True,
            "expansion_actions": expansion_actions,
            "reasoning": decision_result.reasoning,
            "observations": decision_result.observations
        }
    
    async def _execute_decide_act_phase(
        self, 
        cycle_id: str, 
        primary_channel_id: Optional[str]
    ) -> Dict[str, Any]:
        """
        Execute Phase 2: Decide/Act - AI makes decisions with expanded context.
        
        In this phase, the AI:
        1. Sees full data for expanded nodes
        2. Can use all available tools (node tools + external action tools)
        3. Makes final decisions and takes external actions
        
        Returns:
            Dict with success status and external actions taken
        """
        world_state_data = self.world_state_manager.get_world_state_data()
        
        # Build full payload with expanded node data
        payload = self.payload_builder.build_node_based_payload(
            world_state_data=world_state_data,
            node_manager=self.node_manager,
            primary_channel_id=primary_channel_id or "unknown",
            config={
                "bot_fid": settings.FARCASTER_BOT_FID,
                "bot_username": settings.FARCASTER_BOT_USERNAME
            }
        )
        
        # Add phase-specific context
        payload["phase"] = "decide_act"
        payload["instructions"] = (
            "DECIDE/ACT PHASE: You now have full context from expanded nodes. "
            "Analyze the information and take appropriate external actions. You can "
            "still use node tools if needed, but focus on external actions that "
            "respond to the situation you've discovered."
        )
        
        # Provide all available tools through unified ToolRegistry
        payload["available_tools"] = self.tool_registry.get_tool_descriptions_for_ai()
        
        # Execute decide/act decision
        decide_cycle_id = f"{cycle_id}_decide_act"
        decision_result = await self.ai_engine.make_decision(payload, decide_cycle_id)
        
        external_actions = 0
        if decision_result.selected_actions:
            for action in decision_result.selected_actions:
                try:
                    success = await self._execute_action(action, decide_cycle_id)
                    if success:
                        external_actions += 1
                except Exception as e:
                    logger.error(f"NodeProcessor: Error executing decide/act action {action.action_type}: {e}")
        
        return {
            "success": True,
            "external_actions": external_actions,
            "reasoning": decision_result.reasoning,
            "observations": decision_result.observations
        }
    
    async def _execute_action(self, action, cycle_id: str) -> bool:
        """
        Execute an individual action through the unified tool registry pipeline.
        
        This method now routes ALL actions (node and external) through the main
        ToolRegistry, eliminating the forked execution pattern.
        
        Returns:
            True if action executed successfully, False otherwise
        """
        try:
            # All actions now go through the unified ToolRegistry
            tool = self.tool_registry.get_tool(action.action_type)
            if not tool:
                logger.warning(f"NodeProcessor: Unknown tool {action.action_type}")
                return False
            
            # For external tools, we need an ActionContext
            if action.action_type not in ["expand_node", "collapse_node", "pin_node", "unpin_node", "refresh_summary", "get_expansion_status"]:
                if not self.action_context:
                    logger.info(f"NodeProcessor: External action {action.action_type} requires ActionContext - skipping in node-only mode")
                    return True  # Consider successful for node-only processing
                
                # Execute external tool with full ActionContext
                result = await tool.execute(action.parameters, self.action_context)
                success = result.get("status") == "success"
                if success:
                    logger.info(f"NodeProcessor: External action {action.action_type} succeeded")
                else:
                    logger.warning(f"NodeProcessor: External action {action.action_type} failed: {result.get('error', 'Unknown error')}")
                return success
            else:
                # Execute node management tool with minimal ActionContext
                minimal_context = ActionContext(world_state_manager=self.world_state_manager)
                result = await tool.execute(action.parameters, minimal_context)
                success = result.get("status") == "success"
                if success:
                    logger.debug(f"NodeProcessor: Node action {action.action_type} succeeded")
                else:
                    logger.warning(f"NodeProcessor: Node action {action.action_type} failed: {result.get('error', 'Unknown error')}")
                return success
                
        except Exception as e:
            logger.error(f"NodeProcessor: Error executing action {action.action_type}: {e}")
            return False
    
    async def _refresh_stale_summaries(self):
        """
        Refresh summaries for nodes that have stale or missing summaries.
        
        This ensures the Orient phase has accurate summaries to work with.
        """
        try:
            world_state_data = self.world_state_manager.get_world_state_data()
            all_node_paths = self.payload_builder._get_node_paths_from_world_state(world_state_data)
            
            # Find nodes needing summary updates
            nodes_needing_summary = []
            for node_path in all_node_paths:
                metadata = self.node_manager.get_node_metadata(node_path)
                node_data = self.payload_builder._get_node_data_by_path(world_state_data, node_path)
                
                if node_data is None or metadata.is_expanded:
                    continue
                
                # Check if summary is missing or data has changed
                if (metadata.ai_summary is None or 
                    metadata.last_summary_update_ts is None or
                    self.node_manager.is_data_changed(node_path, node_data)):
                    
                    nodes_needing_summary.append({
                        "node_path": node_path,
                        "node_data": node_data,
                        "node_type": self._infer_node_type(node_path)
                    })
            
            if nodes_needing_summary:
                logger.info(f"NodeProcessor: Refreshing {len(nodes_needing_summary)} stale summaries")
                
                # Generate summaries efficiently
                summaries = await self.summary_service.generate_multiple_summaries(nodes_needing_summary)
                
                # Update node metadata with new summaries
                for node_request in nodes_needing_summary:
                    node_path = node_request["node_path"]
                    if node_path in summaries:
                        self.node_manager.update_node_summary(node_path, summaries[node_path])
                        logger.debug(f"NodeProcessor: Updated summary for {node_path}")
            
        except Exception as e:
            logger.error(f"NodeProcessor: Error refreshing summaries: {e}")
    
    def _infer_node_type(self, node_path: str) -> str:
        """Infer the type of a node from its path."""
        if node_path.startswith("channels."):
            return "channel"
        elif node_path.startswith("users."):
            return "user"
        elif node_path.startswith("threads."):
            return "thread"
        elif node_path.startswith("farcaster.feeds."):
            return "feed"
        elif node_path.startswith("system."):
            return "system"
        else:
            return "unknown"
    
    def get_status(self) -> Dict[str, Any]:
        """Get current processor status."""
        return {
            "processor_type": "node_based",
            "two_phase_enabled": self.enable_two_phase,
            "max_exploration_rounds": self.max_exploration_rounds,
            "node_manager_status": self.node_manager.get_expansion_status_summary(),
            "recent_system_events": len(self.node_manager.system_events)
        }
