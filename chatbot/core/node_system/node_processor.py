"""
Node Processor for Interactive Node-Based Processing

This module implements the core node processor that handles AI decision-making
using the node-based JSON Observer and Interactive Executor pattern.
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .action_backlog import ActionBacklog, QueuedAction, ActionPriority, ActionStatus

if TYPE_CHECKING:
    from ..world_state.manager import WorldStateManager
    from ..world_state.payload_builder import PayloadBuilder
    from ..ai_engine import AIEngine
    from .node_manager import NodeManager
    from .summary_service import NodeSummaryService
    from .interaction_tools import NodeInteractionTools

logger = logging.getLogger(__name__)


class NodeProcessor:
    """
    Node-based processor that implements the JSON Observer and Interactive Executor pattern.
    
    This processor:
    1. Builds node-aware payloads for the AI
    2. Manages node expansion/collapse operations
    3. Coordinates AI decision-making with node state
    4. Executes AI-selected actions through tools
    """
    
    def __init__(
        self,
        world_state_manager: "WorldStateManager",
        payload_builder: "PayloadBuilder",
        ai_engine: "AIEngine",
        node_manager: "NodeManager",
        summary_service: "NodeSummaryService",
        interaction_tools: "NodeInteractionTools",
        tool_registry=None,
        action_context=None,
        action_executor=None
    ):
        self.world_state = world_state_manager
        self.payload_builder = payload_builder
        self.ai_engine = ai_engine
        self.node_manager = node_manager
        self.summary_service = summary_service
        self.interaction_tools = interaction_tools
        self.tool_registry = tool_registry
        self.action_context = action_context
        self.action_executor = action_executor
        
        # Initialize Kanban-style action backlog system with optimized settings
        self.action_backlog = ActionBacklog(max_total_wip=12)  # Increased WIP capacity
        self._last_planning_time = 0
        self._planning_interval = 2.0  # More frequent planning (reduced from 5s to 2s)
        self._shutdown_requested = False
        
        # Enhanced continuous processing settings
        self._min_backlog_threshold = 5  # Increased from 3 to 5 for more aggressive planning
        self._max_execution_timeout = 120.0  # Increased from 30s to 2 minutes for more continuous processing
        
        logger.debug("NodeProcessor initialized with Kanban-style action backlog system")
    
    async def process_cycle(
        self,
        cycle_id: str,
        primary_channel_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        LEGACY METHOD: Maintained for backward compatibility.
        New implementations should use ooda_loop() for the structured decision-making process.
        
        This method:
        1. Checks for high-priority interrupts (mentions, DMs)
        2. Plans new actions if backlog is low
        3. Executes actions from the prioritized backlog
        4. Respects service-specific rate limits and WIP constraints
        
        Args:
            cycle_id: Unique identifier for this processing cycle
            primary_channel_id: The primary channel to focus on (optional)
            context: Additional context for processing (trigger_type, etc.)
            
        Returns:
            Dict containing cycle results and metrics
        """
        # For now, delegate to the new OODA loop implementation
        return await self.ooda_loop(cycle_id, primary_channel_id, context)

    async def ooda_loop(
        self,
        cycle_id: str,
        primary_channel_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute the Observe, Orient, Decide, Act (OODA) loop for structured AI decision-making.
        
        This method implements a formal two-stage AI process:
        1. OBSERVE: System gathers current world state
        2. ORIENT (AI Stage 1): AI decides what information needs deeper inspection
        3. DECIDE (AI Stage 2): AI chooses external actions based on expanded information
        4. ACT: System executes the chosen actions
        5. FEEDBACK: Results inform the next cycle
        
        Args:
            cycle_id: Unique identifier for this processing cycle
            primary_channel_id: The primary channel to focus on (optional)
            context: Additional context for processing (trigger_type, etc.)
            
        Returns:
            Dict containing cycle results and metrics
        """
        context = context or {}
        cycle_start_time = time.time()
        
        logger.info(f"[OODA/{cycle_id}] Starting OODA Loop. Trigger: {context.get('trigger_type', 'unknown')}")

        # Ensure primary_channel_id is in context
        if primary_channel_id:
            context["primary_channel_id"] = primary_channel_id
            context["cycle_id"] = cycle_id

        # Update ActionContext with current channel information
        if self.action_context and primary_channel_id:
            self.action_context.update_current_channel(primary_channel_id)
            logger.debug(f"[OODA/{cycle_id}] Updated ActionContext with primary channel: {primary_channel_id}")

        try:
            # OBSERVE: Gather current world state and ensure core channels are available
            logger.debug(f"[OODA/{cycle_id}] OBSERVE: Gathering world state")
            
            # Ensure core channels are expanded so AI has context to work with
            await self._ensure_core_channels_expanded(primary_channel_id, context)
            
            # ORIENT (AI Stage 1): AI decides what information to expand
            logger.info(f"[OODA/{cycle_id}] ORIENT: Building orientation payload")
            orientation_payload = await self._build_orientation_payload(context)
            
            if not orientation_payload:
                logger.warning(f"[OODA/{cycle_id}] Failed to build orientation payload")
                return await self._finalize_ooda_cycle(cycle_id, cycle_start_time, 0, 0)
            
            # Check if we have any meaningful data for the AI
            collapsed_summaries = orientation_payload.get("collapsed_node_summaries", {})
            if not collapsed_summaries or all(not summary for summary in collapsed_summaries.values()):
                logger.warning(f"[OODA/{cycle_id}] No meaningful node summaries - expanding basic nodes proactively")
                # Emergency expansion of basic nodes
                basic_nodes = [
                    "farcaster.feeds.home",
                    "farcaster.feeds.notifications", 
                    "farcaster.feeds.mentions"
                ]
                for node_path in basic_nodes:
                    try:
                        success, _, _ = self.node_manager.expand_node(node_path)
                        if success:
                            logger.debug(f"Emergency expanded: {node_path}")
                    except Exception as e:
                        logger.debug(f"Failed to emergency expand {node_path}: {e}")
                
                # Rebuild payload after emergency expansion
                orientation_payload = await self._build_orientation_payload(context)
                if not orientation_payload:
                    logger.error(f"[OODA/{cycle_id}] Still no orientation payload after emergency expansion")
                    return await self._finalize_ooda_cycle(cycle_id, cycle_start_time, 0, 0)
            
            logger.info(f"[OODA/{cycle_id}] ORIENT: Getting AI's node expansion decisions")
            node_actions = await self._get_orientation_decision(orientation_payload, cycle_id)
            
            if node_actions:
                logger.info(f"[OODA/{cycle_id}] ORIENT: Executing {len(node_actions)} node expansions")
                await self._execute_node_actions(node_actions, cycle_id)
            else:
                logger.debug(f"[OODA/{cycle_id}] ORIENT: AI requested no node expansions - using fallback expansion")
                # Fallback: expand some basic nodes to ensure AI has context
                await self._auto_expand_active_channels()
            
            # DECIDE (AI Stage 2): AI chooses external actions based on expanded information
            logger.info(f"[OODA/{cycle_id}] DECIDE: Building decision payload with expanded nodes")
            decision_payload = await self._build_decision_payload(context)
            
            if not decision_payload:
                logger.warning(f"[OODA/{cycle_id}] Failed to build decision payload")
                return await self._finalize_ooda_cycle(cycle_id, cycle_start_time, len(node_actions) if node_actions else 0, 0)
            
            logger.info(f"[OODA/{cycle_id}] DECIDE: Getting AI's external action decisions")
            external_actions = await self._get_decision(decision_payload, cycle_id)
            
            actions_executed_count = 0
            if external_actions:
                logger.info(f"[OODA/{cycle_id}] DECIDE: AI chose {len(external_actions)} external actions")
                
                # ACT: Execute the chosen actions
                logger.info(f"[OODA/{cycle_id}] ACT: Executing external actions")
                execution_results = await self._execute_external_actions(external_actions, cycle_id)
                actions_executed_count = len(execution_results) if execution_results else 0
                
                # FEEDBACK: Set last action result for next cycle
                if execution_results:
                    self.payload_builder.set_last_action_result(execution_results[-1])
                    logger.debug(f"[OODA/{cycle_id}] FEEDBACK: Set last action result for next cycle")
            else:
                logger.debug(f"[OODA/{cycle_id}] DECIDE: AI chose no external actions")
            
            logger.info(f"[OODA/{cycle_id}] OODA Loop completed successfully")
            return await self._finalize_ooda_cycle(cycle_id, cycle_start_time, 
                                                 len(node_actions) if node_actions else 0, 
                                                 actions_executed_count)

        except Exception as e:
            logger.error(f"[OODA/{cycle_id}] Error in OODA loop: {e}", exc_info=True)
            return {
                "cycle_id": cycle_id,
                "success": False,
                "error": str(e),
                "node_actions_executed": 0,
                "external_actions_executed": 0,
                "ooda_loop_duration": time.time() - cycle_start_time
            }
    
    async def _finalize_cycle(self, cycle_id: str, cycle_start_time: float, 
                             actions_executed_count: int, planning_cycles: int = 0) -> Dict[str, Any]:
        """Helper method to finalize a processing cycle."""
        await self._update_node_summaries()
        self._log_node_system_events()

        cycle_duration = time.time() - cycle_start_time
        backlog_status = self.action_backlog.get_status_summary()
        
        logger.debug(
            f"Completed Kanban cycle {cycle_id} in {cycle_duration:.2f}s - "
            f"{actions_executed_count} actions executed, {planning_cycles} planning cycles, "
            f"backlog: {backlog_status['total_queued']} queued, {backlog_status['in_progress']} in progress"
        )
        
        return {
            "cycle_id": cycle_id,
            "success": True,
            "actions_executed": actions_executed_count,
            "planning_cycles": planning_cycles,
            "cycle_duration": cycle_duration,
            "backlog_status": backlog_status
        }
    
    async def _finalize_ooda_cycle(self, cycle_id: str, cycle_start_time: float,
                                 node_actions_executed: int, external_actions_executed: int) -> Dict[str, Any]:
        """Helper method to finalize an OODA processing cycle."""
        await self._update_node_summaries()
        self._log_node_system_events()

        cycle_duration = time.time() - cycle_start_time
        
        logger.info(
            f"[OODA/{cycle_id}] Completed in {cycle_duration:.2f}s - "
            f"{node_actions_executed} node actions, {external_actions_executed} external actions"
        )
        
        return {
            "cycle_id": cycle_id,
            "success": True,
            "node_actions_executed": node_actions_executed,
            "external_actions_executed": external_actions_executed,
            "ooda_loop_duration": cycle_duration,
            "ooda_phases": {
                "observe": "system",
                "orient": "ai_stage_1",
                "decide": "ai_stage_2", 
                "act": "system"
            }
        }

    async def _build_orientation_payload(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Build payload for the ORIENT phase (AI Stage 1).
        
        This payload contains only collapsed node summaries and system status.
        The AI will use this to decide which nodes need expansion.
        
        Args:
            context: Processing context containing cycle information
            
        Returns:
            Orientation payload dictionary or None if building fails
        """
        try:
            # Get current world state (synchronous call)
            world_state_data = self.world_state.get_world_state_data()
            if not world_state_data:
                logger.warning("Failed to get world state data for orientation payload")
                return None
            
            primary_channel_id = context.get("primary_channel_id") or ""
            
            # Build node-based payload with phase='orient'
            payload = self.payload_builder.build_node_based_payload(
                world_state_data=world_state_data,
                node_manager=self.node_manager,
                primary_channel_id=primary_channel_id,
                config={"phase": "orient"}
            )
            
            # Add OODA-specific context
            payload["ooda_phase"] = "orient"
            payload["cycle_context"] = {
                "cycle_id": context.get("cycle_id"),
                "trigger_type": context.get("trigger_type"),
                "primary_channel_id": primary_channel_id
            }
            
            logger.debug(f"Built orientation payload with {len(payload.get('collapsed_node_summaries', {}))} collapsed nodes")
            return payload
            
        except Exception as e:
            logger.error(f"Error building orientation payload: {e}", exc_info=True)
            return None

    async def _get_orientation_decision(self, payload: Dict[str, Any], cycle_id: str) -> Optional[List[Dict[str, Any]]]:
        """
        Get AI's orientation decision - which nodes to expand.
        
        Args:
            payload: Orientation payload with collapsed summaries
            cycle_id: Current cycle ID for logging
            
        Returns:
            List of node action dictionaries or None if AI call fails
        """
        try:
            logger.debug(f"[OODA/{cycle_id}] Calling AI for orientation decision")
            
            # Add orientation-specific instruction message
            orientation_payload = {
                **payload,
                "instruction": {
                    "phase": "ORIENTATION",
                    "task": "Review the collapsed_node_summaries and system_events to determine what information needs deeper inspection. Use ONLY the expand_node, pin_node, or collapse_node tools to select nodes for expansion.",
                    "available_tools": ["expand_node", "pin_node", "collapse_node"],
                    "forbidden_tools": ["send_message", "send_farcaster_cast", "search_web"]
                }
            }
            
            # Add node management tools to the payload
            if "tools" not in orientation_payload:
                orientation_payload["tools"] = []
            
            # Add node management tools
            node_tools = self.interaction_tools.get_tool_definitions()
            orientation_payload["tools"].extend(node_tools.values())
            
            # Ensure the AI instruction is in the expected message format
            if "messages" not in orientation_payload:
                orientation_payload["messages"] = []
            
            # Add user message with orientation instruction
            orientation_message = (
                "ORIENTATION PHASE:\n"
                "Your goal is to determine what information needs deeper inspection.\n"
                "Review the collapsed_node_summaries and system_events.\n"
                "Use ONLY the expand_node, pin_node, or collapse_node tools to select nodes that need expansion for detailed analysis.\n"
                f"Available data: {len(orientation_payload.get('collapsed_node_summaries', {}))} collapsed nodes, "
                f"{len(orientation_payload.get('system_events', []))} system events"
            )
            
            orientation_payload["messages"].append({
                "role": "user",
                "content": orientation_message
            })
            
            # Debug: Log what data is actually in the payload
            debug_info = {
                "collapsed_node_summaries": len(orientation_payload.get("collapsed_node_summaries", {})),
                "system_events": len(orientation_payload.get("system_events", [])),
                "tools": len(orientation_payload.get("tools", [])),
                "payload_keys": list(orientation_payload.keys())
            }
            logger.debug(f"[OODA/{cycle_id}] ORIENT Debug - Payload contents: {debug_info}")
            
            # Log a sample of collapsed summaries for debugging
            collapsed_summaries = orientation_payload.get("collapsed_node_summaries", {})
            if collapsed_summaries:
                sample_keys = list(collapsed_summaries.keys())[:3]
                logger.debug(f"[OODA/{cycle_id}] ORIENT Sample summaries: {sample_keys}")
            else:
                logger.warning(f"[OODA/{cycle_id}] ORIENT WARNING: No collapsed_node_summaries in payload!")
            
            # Call AI with orientation payload
            ai_response = await self.ai_engine.decide_actions(orientation_payload)
            
            if not ai_response or not ai_response.get("selected_actions"):
                logger.debug(f"[OODA/{cycle_id}] AI provided no orientation actions")
                return None
            
            # Filter for node-related actions only
            node_actions = []
            for action in ai_response["selected_actions"]:
                action_type = action.get("action_type", "")
                if action_type in ["expand_node", "pin_node", "collapse_node"]:
                    node_actions.append(action)
                else:
                    logger.warning(f"[OODA/{cycle_id}] ORIENT: Ignoring non-node action {action_type}")
            
            logger.debug(f"[OODA/{cycle_id}] AI orientation decision: {len(node_actions)} node actions")
            return node_actions
            
        except Exception as e:
            logger.error(f"[OODA/{cycle_id}] Error getting orientation decision: {e}", exc_info=True)
            return None

    async def _execute_node_actions(self, node_actions: List[Dict[str, Any]], cycle_id: str) -> None:
        """
        Execute node expansion/collapse actions using NodeInteractionTools.
        
        Args:
            node_actions: List of node action dictionaries from AI
            cycle_id: Current cycle ID for logging
        """
        try:
            for action in node_actions:
                action_type = action.get("action_type")
                arguments = action.get("arguments", {})
                node_path = arguments.get("node_path")
                
                if not action_type:
                    logger.warning(f"[OODA/{cycle_id}] Node action missing action_type: {action}")
                    continue
                    
                if not node_path:
                    logger.warning(f"[OODA/{cycle_id}] Node action missing node_path: {action}")
                    continue
                
                logger.debug(f"[OODA/{cycle_id}] Executing {action_type} on {node_path}")
                
                # Execute through the interaction tools
                result = self.interaction_tools.execute_tool(action_type, arguments)
                
                if result.get("success"):
                    logger.debug(f"[OODA/{cycle_id}] {action_type} on {node_path} succeeded")
                else:
                    logger.warning(f"[OODA/{cycle_id}] {action_type} on {node_path} failed: {result.get('message')}")
                    
        except Exception as e:
            logger.error(f"[OODA/{cycle_id}] Error executing node actions: {e}", exc_info=True)

    async def _build_decision_payload(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Build payload for the DECIDE phase (AI Stage 2).
        
        This payload contains the full content of expanded nodes.
        The AI will use this to choose external actions.
        
        Args:
            context: Processing context containing cycle information
            
        Returns:
            Decision payload dictionary or None if building fails
        """
        try:
            # Get current world state (after node expansions) - synchronous call
            world_state_data = self.world_state.get_world_state_data()
            if not world_state_data:
                logger.warning("Failed to get world state data for decision payload")
                return None
            
            primary_channel_id = context.get("primary_channel_id") or ""
            
            # Build node-based payload with phase='decide'
            payload = self.payload_builder.build_node_based_payload(
                world_state_data=world_state_data,
                node_manager=self.node_manager,
                primary_channel_id=primary_channel_id,
                config={"phase": "decide"}
            )
            
            # Add OODA-specific context
            payload["ooda_phase"] = "decide"
            payload["cycle_context"] = {
                "cycle_id": context.get("cycle_id"),
                "trigger_type": context.get("trigger_type"),
                "primary_channel_id": primary_channel_id
            }
            
            expanded_count = len(payload.get("expanded_nodes", {}))
            logger.debug(f"Built decision payload with {expanded_count} expanded nodes")
            return payload
            
        except Exception as e:
            logger.error(f"Error building decision payload: {e}", exc_info=True)
            return None

    async def _get_decision(self, payload: Dict[str, Any], cycle_id: str) -> Optional[List[Dict[str, Any]]]:
        """
        Get AI's external action decision.
        
        Args:
            payload: Decision payload with expanded node content
            cycle_id: Current cycle ID for logging
            
        Returns:
            List of external action dictionaries or None if AI call fails
        """
        try:
            logger.debug(f"[OODA/{cycle_id}] Calling AI for external action decision")
            
            # Add decision-specific instruction message
            decision_payload = {
                **payload,
                "instruction": {
                    "phase": "DECISION",
                    "task": "Choose external actions based on expanded node content. You can use any available tools except node management tools.",
                    "forbidden_tools": ["expand_node", "pin_node", "collapse_node"]
                }
            }
            
            # Ensure the AI instruction is in the expected message format
            if "messages" not in decision_payload:
                decision_payload["messages"] = []
            
            # Add user message with decision instruction
            decision_message = (
                "DECISION PHASE:\n"
                "You have expanded the relevant nodes and can see their detailed content in expanded_nodes.\n"
                "Based on this full context, decide on the best external actions to take.\n"
                "You can use any available communication and interaction tools.\n"
                f"Available data: {len(decision_payload.get('expanded_nodes', {}))} expanded nodes"
            )
            
            decision_payload["messages"].append({
                "role": "user", 
                "content": decision_message
            })
            
            # Debug: Log what data is actually in the payload
            debug_info = {
                "expanded_nodes": len(decision_payload.get("expanded_nodes", {})),
                "collapsed_node_summaries": len(decision_payload.get("collapsed_node_summaries", {})),
                "tools": len(decision_payload.get("tools", [])),
                "payload_keys": list(decision_payload.keys())
            }
            logger.debug(f"[OODA/{cycle_id}] DECIDE Debug - Payload contents: {debug_info}")
            
            # Log a sample of expanded nodes for debugging
            expanded_nodes = decision_payload.get("expanded_nodes", {})
            if expanded_nodes:
                sample_keys = list(expanded_nodes.keys())[:3]
                logger.debug(f"[OODA/{cycle_id}] DECIDE Sample expanded nodes: {sample_keys}")
            else:
                logger.warning(f"[OODA/{cycle_id}] DECIDE WARNING: No expanded_nodes in payload!")
            
            # Call AI with decision payload
            ai_response = await self.ai_engine.decide_actions(decision_payload)
            
            if not ai_response or not ai_response.get("selected_actions"):
                logger.debug(f"[OODA/{cycle_id}] AI provided no external actions")
                return None
            
            # Filter for external actions only (exclude node actions)
            external_actions = []
            for action in ai_response["selected_actions"]:
                action_type = action.get("action_type", "")
                if action_type not in ["expand_node", "pin_node", "collapse_node"]:
                    external_actions.append(action)
                else:
                    logger.warning(f"[OODA/{cycle_id}] DECIDE: Ignoring node action {action_type} in decision phase")
            
            logger.debug(f"[OODA/{cycle_id}] AI decision: {len(external_actions)} external actions")
            return external_actions
            
        except Exception as e:
            logger.error(f"[OODA/{cycle_id}] Error getting decision: {e}", exc_info=True)
            return None

    async def _execute_external_actions(self, actions: List[Dict[str, Any]], cycle_id: str) -> Optional[List[Dict[str, Any]]]:
        """
        Execute external actions (send_message, search_web, etc.) via ActionExecutor.
        
        Args:
            actions: List of external action dictionaries from AI
            cycle_id: Current cycle ID for logging
            
        Returns:
            List of execution results for feedback loop
        """
        try:
            execution_results = []
            
            for action in actions:
                action_type = action.get("action_type")
                logger.debug(f"[OODA/{cycle_id}] Executing external action: {action_type}")
                
                if self.action_executor:
                    # Execute through the action executor
                    result = await self.action_executor.execute_action(action)
                    execution_results.append(result)
                    logger.debug(f"[OODA/{cycle_id}] Action {action_type} result: {result.get('success', False)}")
                else:
                    logger.warning(f"[OODA/{cycle_id}] No action executor available for {action_type}")
                    execution_results.append({
                        "action_type": action_type,
                        "success": False,
                        "error": "No action executor available"
                    })
            
            return execution_results
            
        except Exception as e:
            logger.error(f"[OODA/{cycle_id}] Error executing external actions: {e}", exc_info=True)
            return None

    # === Legacy Kanban Methods (Deprecated - Use OODA loop instead) ===
    
    def _is_backlog_empty(self) -> bool:
        """DEPRECATED: Legacy method for Kanban-style processing."""
        # For now, always return True to disable legacy Kanban processing
        return True
    
    async def _planning_phase(self, cycle_id: str, primary_channel_id: Optional[str], 
                             context: Dict[str, Any]) -> None:
        """DEPRECATED: Legacy planning phase - replaced by OODA Orient/Decide phases."""
        logger.warning(f"[{cycle_id}] Legacy planning phase called - should use OODA loop instead")
        # No-op - OODA loop handles planning
        pass
    
    async def _execute_action(self, action_dict: Dict[str, Any], cycle_id: str) -> Dict[str, Any]:
        """DEPRECATED: Legacy action execution - replaced by OODA Act phase."""
        logger.warning(f"[{cycle_id}] Legacy action execution called - should use OODA loop instead")
        return {
            "status": "skipped",
            "message": "Legacy action execution bypassed - use OODA loop",
            "action_type": action_dict.get("action_type", "unknown")
        }
    
    def _generate_self_state_guidance(self, cycle_actions: List[Dict[str, Any]]) -> str:
        """
        Generate guidance for the AI based on its actions within the current cycle.
        This helps prevent repetitive actions and provides self-awareness.
        """
        if not cycle_actions:
            return "No actions taken in this cycle yet. Choose your first action carefully."
        
        last_action = cycle_actions[-1]
        action_types = [action["action_type"] for action in cycle_actions]
        
        # Check for repetitive expand_node attempts
        expand_attempts = [action for action in cycle_actions if action["action_type"] == "expand_node"]
        if len(expand_attempts) > 1:
            last_expand = expand_attempts[-1]
            return f"WARNING: You attempted to expand node '{last_expand['parameters'].get('node_path')}' in step {last_expand['action_step']}. If it didn't work, the node path may be incorrect or the node is already expanded. Consider a different action."
        
        # Check for repeated actions of the same type
        if len(set(action_types)) < len(action_types):
            return f"WARNING: You have repeated the same action type ({last_action['action_type']}) multiple times in this cycle. Consider why the previous attempt didn't achieve your goal before retrying."
        
        # General guidance based on last action
        if last_action["action_type"] == "expand_node":
            return f"You just attempted to expand node '{last_action['parameters'].get('node_path')}'. The node should now be visible in expanded_nodes if successful."
        elif last_action["action_type"] in ["send_farcaster_post", "send_matrix_message"]:
            return f"You just attempted to {last_action['action_type']}. Check if the action was successful before attempting another post."
        else:
            return f"Previous action: {last_action['action_type']}. Consider the result before choosing your next action."

    def _find_full_path(self, partial_path: str) -> Optional[str]:
        """
        Find the full node path from a partial path, channel name, or room ID.
        This handles the alias/ID mismatch bug where AI uses human-readable names.
        
        Args:
            partial_path: The partial path, channel name, or room ID provided by AI
            
        Returns:
            The full node path if found, None otherwise
        """
        all_known_paths = self.node_manager.get_all_node_paths()
        
        # Strategy 1: Check if it's a suffix of a known path
        for path in all_known_paths:
            if path.endswith(partial_path):
                return path
        
        # Strategy 2: Check if it's a Matrix room ID (starts with !)
        if partial_path.startswith('!'):
            for path in all_known_paths:
                if f"channel.matrix.{partial_path}" == path:
                    return path
        
        # Strategy 3: Check if it's a channel name by looking at world state
        try:
            world_state_data = self.world_state.get_world_state_data()
            for platform, platform_channels in world_state_data.channels.items():
                if isinstance(platform_channels, dict):
                    for channel_id, channel in platform_channels.items():
                        if channel.name == partial_path:
                            # Found a channel with this name, construct the full path
                            full_path = f"channel.{platform}.{channel_id}"
                            if full_path in all_known_paths:
                                return full_path
        except Exception as e:
            logger.error(f"Error searching for channel name '{partial_path}': {e}")
        
        # Strategy 4: Check if it's a Farcaster channel ID or name
        if partial_path.startswith('farcaster:'):
            for path in all_known_paths:
                if f"channel.{partial_path}" == path:
                    return path
        
        logger.warning(f"Could not find full path for '{partial_path}'. Available paths: {all_known_paths}")
        return None
    
    async def _execute_summary_refresh(self, tool_args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a summary refresh request."""
        try:
            node_path = tool_args.get("node_path", "")
            if not node_path:
                return {"success": False, "error": "Missing node_path"}
            
            # Get current node data
            world_state_data = self.world_state.get_world_state_data()
            
            # Use NodeDataHandlers to get node data
            from ..world_state.node_data_handlers import NodeDataHandlers
            data_handler = NodeDataHandlers()
            node_data = data_handler.get_node_data_by_path(world_state_data, node_path)
            
            if node_data:
                # Generate new summary
                summary = await self.summary_service.generate_node_summary(node_path, node_data)
                
                # Update node metadata
                self.node_manager.update_node_summary(node_path, summary)
                
                return {
                    "success": True,
                    "message": f"Refreshed summary for {node_path}",
                    "summary": summary
                }
            else:
                return {"success": False, "error": f"No data found for node {node_path}"}
                
        except Exception as e:
            logger.error(f"Error refreshing summary: {e}")
            return {"success": False, "error": str(e)}
    
    async def _execute_platform_tool(
        self, 
        tool_name: str, 
        tool_args: Dict[str, Any], 
        cycle_id: str
    ) -> Dict[str, Any]:
        """Execute a platform-specific tool through the ActionExecutor."""
        try:
            # Use ActionExecutor if available for centralized execution
            if self.action_executor and self.action_context:
                from ..orchestration.action_executor import ActionPlan
                
                action_plan = ActionPlan(tool_name, tool_args)
                result = await self.action_executor.execute_action(action_plan, self.action_context)
                
                return {
                    "success": result.get("status") == "success",
                    "message": result.get("message", f"Tool {tool_name} executed"),
                    "tool_name": tool_name,
                    "cycle_id": cycle_id,
                    "tool_result": result
                }
            
            # Fallback to direct tool execution for backward compatibility
            if hasattr(self, 'tool_registry') and self.tool_registry:
                tool_registry = self.tool_registry
            else:
                logger.warning(f"No tool registry available for tool {tool_name}")
                return {"success": False, "error": "Tool registry not available"}
            
            if hasattr(self, 'action_context') and self.action_context:
                action_context = self.action_context
            else:
                logger.warning(f"No action context available for tool {tool_name}")
                return {"success": False, "error": "Action context not available"}
            
            # Get the tool instance
            tool_instance = tool_registry.get_tool(tool_name)
            if not tool_instance:
                logger.warning(f"Tool {tool_name} not found in registry")
                return {"success": False, "error": f"Tool {tool_name} not found"}
            
            # Execute the tool directly
            logger.debug(f"Executing platform tool: {tool_name} with args {tool_args}")
            result = await tool_instance.execute(tool_args, action_context)
            
            # Check if the tool execution was successful
            tool_success = result.get("status") == "success" if isinstance(result, dict) else True
            
            return {
                "success": tool_success,
                "message": f"Tool {tool_name} executed {'successfully' if tool_success else 'with errors'}",
                "tool_name": tool_name,
                "cycle_id": cycle_id,
                "tool_result": result
            }
            
        except Exception as e:
            logger.error(f"Error executing platform tool {tool_name}: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    async def _update_node_summaries(self):
        """Update summaries for nodes that need refreshing."""
        try:
            # Get world state data
            world_state_data = self.world_state.get_world_state_data()
            
            # Use NodePathGenerator to get all node paths
            from ..world_state.node_path_generator import NodePathGenerator
            path_generator = NodePathGenerator()
            all_node_paths = path_generator.get_node_paths_from_world_state(world_state_data)
            
            # Get nodes that need summary updates
            nodes_needing_summary = self.node_manager.get_nodes_needing_summary(all_node_paths)
            
            # Update summaries for these nodes
            for node_path in nodes_needing_summary[:5]:  # Limit to 5 per cycle to avoid overload
                try:
                    # Use NodeDataHandlers to get node data
                    from ..world_state.node_data_handlers import NodeDataHandlers
                    data_handler = NodeDataHandlers()
                    node_data = data_handler.get_node_data_by_path(world_state_data, node_path)
                    if node_data:
                        summary = await self.summary_service.generate_node_summary(node_path, node_data)
                        self.node_manager.update_node_summary(node_path, summary)
                        logger.debug(f"Updated summary for node {node_path}")
                except Exception as e:
                    logger.error(f"Error updating summary for {node_path}: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error updating node summaries: {e}")
    
    def _log_node_system_events(self):
        """Log system events from node operations."""
        try:
            events = self.node_manager.get_system_events()
            for event in events:
                logger.debug(f"Node system event: {event['event_type']} - {event['message']}")
        except Exception as e:
            logger.error(f"Error logging node system events: {e}")
    
    def _summarize_ai_response(self, ai_response: Dict[str, Any]) -> str:
        """Create a brief summary of the AI response."""
        try:
            if not ai_response:
                return "No AI response"
            
            tool_calls = ai_response.get("tool_calls", [])
            if tool_calls:
                tool_names = [call.get("function", {}).get("name", "unknown") for call in tool_calls]
                return f"AI requested {len(tool_calls)} tool calls: {', '.join(tool_names)}"
            
            response_text = ai_response.get("content", "")
            if response_text:
                return f"AI provided text response ({len(response_text)} chars)"
            
            return "AI response with no tools or text"
            
        except Exception as e:
            logger.error(f"Error summarizing AI response: {e}")
            return "Error summarizing response"
    
    def get_status(self) -> Dict[str, Any]:
        """Get current status of the node processor."""
        return {
            "processor_type": "node_based",
            "node_manager_available": self.node_manager is not None,
            "summary_service_available": self.summary_service is not None,
            "interaction_tools_available": self.interaction_tools is not None,
            "current_expanded_nodes": len(self.node_manager.get_expanded_nodes()) if self.node_manager else 0,
            "expansion_status": self.node_manager.get_expansion_status_summary() if self.node_manager else {}
        }
    
    async def _ensure_core_channels_expanded(
        self, 
        primary_channel_id: Optional[str], 
        context: Dict[str, Any]
    ):
        """
        Ensure core channels are always expanded so the AI never receives empty context.
        
        This method guarantees that the AI always has access to:
        1. The primary channel (Matrix/Farcaster)
        2. Farcaster home timeline (for social context)
        3. Any recently selected channels
        
        Unlike auto_expand_active_channels, this runs regardless of recent activity.
        """
        try:
            channels_to_expand = []
            trigger_type = context.get("trigger_type", "")
            
            # 1. Always expand the primary channel if specified
            if primary_channel_id:
                if primary_channel_id.startswith('!'):
                    # Matrix channel - use correct dot notation
                    primary_node_path = f"channel.matrix.{primary_channel_id}"
                    channels_to_expand.append(("primary_matrix", primary_node_path))
                elif primary_channel_id.startswith('farcaster:'):
                    # Farcaster channel - use correct dot notation
                    primary_node_path = f"channel.farcaster.{primary_channel_id}"
                    channels_to_expand.append(("primary_farcaster", primary_node_path))
                else:
                    # Unknown format - try both with correct paths
                    channels_to_expand.append(("primary_matrix_fallback", f"channel.matrix.{primary_channel_id}"))
                    channels_to_expand.append(("primary_farcaster_fallback", f"channel.farcaster.{primary_channel_id}"))
            
            # 2. Always expand Farcaster home timeline for social context
            channels_to_expand.append(("farcaster_home", "farcaster.feeds.home"))
            
            # 3. Always expand notifications/mentions feeds
            channels_to_expand.append(("farcaster_notifications", "farcaster.feeds.notifications"))
            channels_to_expand.append(("farcaster_mentions", "farcaster.feeds.mentions"))
            
            # 4. Get the most recently active Matrix channel as fallback
            try:
                world_state_data = self.world_state.get_world_state_data()
                matrix_channels = getattr(world_state_data, 'channels', {}).get('matrix', {})
                
                # Find the Matrix channel with the most recent activity
                most_recent_matrix = None
                latest_timestamp = 0
                
                for room_id, room_data in matrix_channels.items():
                    if isinstance(room_data, dict) and 'recent_messages' in room_data:
                        recent_messages = room_data['recent_messages']
                        if recent_messages:
                            room_latest = max(
                                msg.get('timestamp', 0) for msg in recent_messages
                                if isinstance(msg, dict)
                            )
                            if room_latest > latest_timestamp:
                                latest_timestamp = room_latest
                                most_recent_matrix = room_id
                
                if most_recent_matrix and most_recent_matrix != primary_channel_id:
                    channels_to_expand.append(("recent_matrix", f"channel.matrix.{most_recent_matrix}"))
                    
            except Exception as e:
                logger.debug(f"Error finding recent Matrix channel: {e}")
            
            # 5. Expand all identified channels
            expanded_count = 0
            for channel_type, node_path in channels_to_expand:
                try:
                    success, auto_collapsed, message = self.node_manager.expand_node(node_path)
                    if success:
                        expanded_count += 1
                        logger.debug(f"🔧 CORE EXPANSION: {channel_type} -> {node_path} (trigger: {trigger_type})")
                        if auto_collapsed:
                            logger.debug(f"   ↳ Auto-collapsed {auto_collapsed} to make room")
                    else:
                        logger.debug(f"Core expansion skipped {channel_type} -> {node_path}: {message}")
                except Exception as e:
                    logger.warning(f"Error expanding core channel {channel_type} ({node_path}): {e}")
            
            if expanded_count > 0:
                logger.debug(f"🎯 CORE CHANNELS: Ensured {expanded_count} essential channels are expanded for AI context")
                
                # DEBUG: Verify the expansion state immediately after expansion
                for channel_type, node_path in channels_to_expand:
                    metadata = self.node_manager.get_node_metadata(node_path)
                    logger.debug(f"🔍 VERIFY EXPANSION: {node_path} -> is_expanded={metadata.is_expanded}, is_pinned={metadata.is_pinned}")
            else:
                logger.debug("🎯 CORE CHANNELS: All essential channels were already expanded")
                
        except Exception as e:
            logger.error(f"Error ensuring core channels expanded: {e}", exc_info=True)

    async def _auto_expand_active_channels(self):
        """Auto-expand the most active channels based on world state activity."""
        try:
            # Get world state data
            world_state_data = self.world_state.get_world_state_data()
            
            # Extract channel activity data
            channel_activity = {}
            current_time = time.time()
            
            # Check Matrix channels
            matrix_channels = getattr(world_state_data, 'channels', {}).get('matrix', {})
            for room_id, room_data in matrix_channels.items():
                if isinstance(room_data, dict) and 'recent_messages' in room_data:
                    recent_messages = room_data['recent_messages']
                    if recent_messages:
                        # Get timestamp of most recent message
                        latest_timestamp = max(
                            msg.get('timestamp', 0) for msg in recent_messages
                            if isinstance(msg, dict)
                        )
                        channel_activity[f"matrix.{room_id}"] = latest_timestamp
            
            # Check Farcaster channels
            farcaster_channels = getattr(world_state_data, 'channels', {}).get('farcaster', {})
            for channel_id, channel_data in farcaster_channels.items():
                if isinstance(channel_data, dict) and 'recent_casts' in channel_data:
                    recent_casts = channel_data['recent_casts']
                    if recent_casts:
                        # Get timestamp of most recent cast
                        latest_timestamp = max(
                            cast.get('timestamp', 0) for cast in recent_casts
                            if isinstance(cast, dict)
                        )
                        channel_activity[f"farcaster.{channel_id}"] = latest_timestamp
            
            # Check Farcaster feeds for activity
            farcaster_data = getattr(world_state_data, 'farcaster', {})
            feeds = farcaster_data.get('feeds', {})
            for feed_name, feed_data in feeds.items():
                if isinstance(feed_data, dict):
                    # Handle different feed data structures
                    feed_messages = None
                    if 'casts' in feed_data:
                        feed_messages = feed_data['casts']
                    elif 'messages' in feed_data:
                        feed_messages = feed_data['messages']
                    elif isinstance(feed_data, list):
                        # Sometimes feed_data might be a direct list of messages
                        feed_messages = feed_data
                    
                    if feed_messages:
                        # Get timestamp of most recent message
                        latest_timestamp = max(
                            (cast.get('timestamp', 0) if isinstance(cast, dict) else 0) 
                            for cast in feed_messages
                        )
                        channel_activity[f"farcaster.feeds.{feed_name}"] = latest_timestamp
                        
                        # Special handling for high-priority feeds like notifications
                        if feed_name in ['notifications', 'mentions', 'home']:
                            # Always prioritize notifications and mentions for expansion
                            channel_activity[f"farcaster.feeds.{feed_name}"] = current_time
            
            # Auto-expand active channels if we found any activity
            if channel_activity:
                auto_expanded = self.node_manager.auto_expand_active_channels(channel_activity)
                if auto_expanded:
                    logger.debug(f"Auto-expanded {len(auto_expanded)} active channels: {auto_expanded}")
                    
        except Exception as e:
            logger.error(f"Error in auto-expanding active channels: {e}", exc_info=True)

    async def _build_node_selection_payload(
        self, 
        primary_channel_id: Optional[str],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build a payload for AI to select which nodes to expand - focuses on summaries."""
        try:
            # Get current world state
            world_state_data = self.world_state.get_world_state_data()
            
            # Build node-based payload with expanded/collapsed state
            payload = self.payload_builder.build_node_based_payload(
                world_state_data=world_state_data,
                node_manager=self.node_manager,
                primary_channel_id=primary_channel_id or "default"
            )
            
            # Add only node selection tools (no platform tools yet)
            if payload and "tools" not in payload:
                payload["tools"] = []
            
            # Add node selection tool
            node_selection_tool = {
                "type": "function",
                "function": {
                    "name": "select_nodes_to_expand",
                    "description": (
                        "Select which nodes you want to expand to get detailed information. "
                        "Based on the collapsed node summaries, choose the nodes that are most "
                        "relevant to the current situation and likely to contain actionable information."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "node_paths": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of node paths to expand for detailed examination"
                            },
                            "reasoning": {
                                "type": "string", 
                                "description": "Explain why you selected these specific nodes"
                            }
                        },
                        "required": ["node_paths", "reasoning"]
                    }
                }
            }
            payload["tools"].append(node_selection_tool)
            
            # Add processing context
            if payload:
                payload["processing_context"] = {
                    "mode": "node_selection",
                    "primary_channel": primary_channel_id,
                    "cycle_context": context,
                    "node_stats": self.node_manager.get_expansion_status_summary(),
                    "instruction": "Focus on selecting the most relevant nodes to expand based on their summaries. You will be able to take actions in the next step."
                }
            
            return payload
            
        except Exception as e:
            logger.error(f"Error building node selection payload: {e}", exc_info=True)
            return {}

    async def _build_action_selection_payload(
        self, 
        primary_channel_id: Optional[str],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build a payload for AI to select actions - includes all tools and expanded nodes."""
        try:
            # Get current world state
            world_state_data = self.world_state.get_world_state_data()
            
            # Build node-based payload with expanded/collapsed state
            payload = self.payload_builder.build_node_based_payload(
                world_state_data=world_state_data,
                node_manager=self.node_manager,
                primary_channel_id=primary_channel_id or "default"
            )
            
            # Add all tools for action selection
            if payload and "tools" not in payload:
                payload["tools"] = []
            
            # Add all platform tools from tool registry FIRST (higher priority)
            if hasattr(self, 'tool_registry') and self.tool_registry and payload:
                enabled_tools = self.tool_registry.get_enabled_tools()
                platform_tools = []
                
                for tool in enabled_tools:
                    # Convert ToolInterface to the format expected by AI
                    tool_def = {
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": self._convert_parameters_schema(tool.parameters_schema)
                        }
                    }
                    platform_tools.append(tool_def)
                
                # Insert platform tools at the beginning for higher priority
                payload["tools"] = platform_tools + payload["tools"]
                logger.debug(f"Added {len(platform_tools)} platform tools to action payload (high priority)")
            
            # Add node management tools at the end
            node_tools = self.interaction_tools.get_tool_definitions()
            if payload:
                payload["tools"].extend(node_tools.values())
                logger.debug(f"Added {len(node_tools)} node management tools to action payload")
            
            # Add processing context
            if payload:
                # Get recent action failures for AI learning
                recent_failures = self._get_recent_action_failures()
                
                payload["processing_context"] = {
                    "mode": "action_selection",
                    "primary_channel": primary_channel_id,
                    "cycle_context": context,
                    "node_stats": self.node_manager.get_expansion_status_summary(),
                    "recent_failures": recent_failures,
                    "instruction": "Now take appropriate actions based on the expanded node content. Prioritize platform communication tools over node management. Learn from recent failures to avoid repeating mistakes."
                }
                
                if recent_failures:
                    failure_summary = f"Recent action failures ({len(recent_failures)}): "
                    failure_summary += ", ".join([f"{f['action_type']}: {f['error']}" for f in recent_failures[:3]])
                    payload["processing_context"]["failure_summary"] = failure_summary
                
                # Check payload size and truncate if needed
                payload_size = len(str(payload))
                if payload_size > 100000:  # 100KB limit
                    logger.warning(f"Payload too large ({payload_size} chars), truncating")
                    # Remove less critical context to reduce size
                    if "recent_failures" in payload["processing_context"]:
                        payload["processing_context"]["recent_failures"] = recent_failures[:2]  # Keep only 2 failures
                    # Further truncation if still too large
                    payload_size = len(str(payload))
                    if payload_size > 100000:
                        payload["processing_context"]["node_stats"] = {"truncated": True}
            
            return payload
            
        except Exception as e:
            logger.error(f"Error building action selection payload: {e}", exc_info=True)
            return {}

    async def _ai_select_nodes_to_expand(
        self,        payload_data: Dict[str, Any], 
        cycle_id: str
    ) -> Dict[str, Any]:
        """First AI decision - select which nodes to expand."""
        try:
            if not payload_data:
                logger.warning(f"Empty payload for node selection in cycle {cycle_id}")
                return {"node_paths": [], "reasoning": "No payload data"}

            # Log a summary of the AI payload being sent for node selection (for debugging)
            payload_summary = {
                "cycle_id": cycle_id,
                "phase": "node_selection",
                "payload_keys": list(payload_data.keys()) if payload_data else [],
                "tools_count": len(payload_data.get("tools", [])),
                "payload_size_kb": len(str(payload_data)) / 1024 if payload_data else 0
            }
            logger.debug(f"AI Node Selection Payload Summary: {payload_summary}")

            # Send to AI engine for node selection
            decision_result = await self.ai_engine.decide_actions(
                world_state=payload_data
            )
            
            # Extract node selection from AI response
            selected_actions = decision_result.get('selected_actions', [])
            for action_plan in selected_actions:
                if action_plan.get('action_type') == "select_nodes_to_expand":
                    return {
                        "node_paths": action_plan.get('parameters', {}).get("node_paths", []),
                        "reasoning": action_plan.get('parameters', {}).get("reasoning", "No reasoning provided"),
                        "ai_reasoning": action_plan.get('reasoning', '')
                    }
            
            # If no explicit node selection, return empty selection
            logger.debug(f"No node selection found in AI response for cycle {cycle_id}")
            return {"node_paths": [], "reasoning": "AI did not select any nodes"}
            
        except Exception as e:
            logger.error(f"Error in AI node selection for cycle {cycle_id}: {e}", exc_info=True)
            return {"node_paths": [], "reasoning": f"Error: {str(e)}"}

    async def _ai_select_actions(
        self, 
        payload_data: Dict[str, Any], 
        cycle_id: str
    ) -> Dict[str, Any]:
        """Second AI decision - select actions based on expanded context."""
        try:
            if not payload_data:
                logger.warning(f"Empty payload for action selection in cycle {cycle_id}")
                return {}
            
            # Log a summary of the AI payload being sent for action selection (for debugging)
            payload_summary = {
                "cycle_id": cycle_id,
                "phase": "action_selection",
                "payload_keys": list(payload_data.keys()) if payload_data else [],
                "tools_count": len(payload_data.get("tools", [])),
                "payload_size_kb": len(str(payload_data)) / 1024 if payload_data else 0
            }
            logger.debug(f"AI Action Selection Payload Summary: {payload_summary}")

            # Send to AI engine for action selection
            decision_result = await self.ai_engine.decide_actions(
                world_state=payload_data
            )
            
            # Handle cases where the AI generates a direct message (inner monologue)
            selected_actions = decision_result.get('selected_actions', [])
            if not selected_actions and decision_result.get('message'):
                logger.info(f"🧠 AI Inner Monologue: {decision_result['message']}")
                # This is internal AI reasoning/thinking - don't convert to external actions
                # Just log it and let the cycle continue without executing external actions
            
            # Convert dict result to format expected by execution methods
            ai_response = {
                "reasoning": decision_result.get('reasoning', ''),
                "observations": decision_result.get('reasoning', ''),  # Map reasoning to observations for compatibility
                "selected_actions": selected_actions,
                "tool_calls": []  # Convert action dict objects to tool_calls format
            }
            
            # Convert action dict objects to tool_calls format for execution
            for action_plan in selected_actions:
                tool_call = {
                    "function": {
                        "name": action_plan.get('action_type', ''),
                        "arguments": action_plan.get('parameters', {})
                    },
                    "reasoning": action_plan.get('reasoning', ''),
                    "priority": action_plan.get('priority', 0)
                }
                ai_response["tool_calls"].append(tool_call)
            
            return ai_response
            
        except Exception as e:
            logger.error(f"Error in AI action selection for cycle {cycle_id}: {e}", exc_info=True)
            return {}

    async def _apply_node_expansions(self, node_selections: Dict[str, Any]) -> Dict[str, Any]:
        """Apply the AI's node expansion selections."""
        try:
            node_paths = node_selections.get("node_paths", [])
            reasoning = node_selections.get("reasoning", "")
            
            if not node_paths:
                logger.debug("No nodes selected for expansion")
                return {"nodes_expanded": 0, "expansion_results": []}
            
            logger.debug(f"AI selected {len(node_paths)} nodes for expansion: {node_paths}")
            logger.debug(f"AI reasoning: {reasoning}")
            
            expansion_results = []
            nodes_expanded = 0
            
            for node_path in node_paths:
                try:
                    success, auto_collapsed, message = self.node_manager.expand_node(node_path)
                    if success:
                        nodes_expanded += 1
                    
                    expansion_results.append({
                        "node_path": node_path,
                        "success": success,
                        "message": message,
                        "auto_collapsed": auto_collapsed
                    })
                    
                    logger.debug(f"Expansion result for {node_path}: {message}")
                    
                except Exception as e:
                    logger.error(f"Error expanding node {node_path}: {e}")
                    expansion_results.append({
                        "node_path": node_path,
                        "success": False,
                        "message": f"Error: {str(e)}",
                        "auto_collapsed": None
                    })
            
            return {
                "nodes_expanded": nodes_expanded,
                "expansion_results": expansion_results
            }
            
        except Exception as e:
            logger.error(f"Error applying node expansions: {e}", exc_info=True)
            return {"nodes_expanded": 0, "expansion_results": []}

    def _summarize_node_selections(self, node_selections: Dict[str, Any]) -> str:
        """Create a brief summary of the AI's node selections."""
        try:
            if not node_selections:
                return "No node selections"
            
            node_paths = node_selections.get("node_paths", [])
            reasoning = node_selections.get("reasoning", "")
            
            if not node_paths:
                return "AI selected no nodes for expansion"
            
            summary = f"AI selected {len(node_paths)} nodes: {', '.join(node_paths)}"
            if reasoning:
                summary += f" (Reason: {reasoning[:100]}{'...' if len(reasoning) > 100 else ''})"
            
            return summary
            
        except Exception as e:
            logger.error(f"Error summarizing node selections: {e}")
            return "Error summarizing selections"
    
    def _convert_parameters_schema(self, parameters_schema: Dict[str, Any]) -> Dict[str, Any]:
        """Convert tool parameters schema to the format expected by AI."""
        try:
            # If it's already in the proper OpenRouter function calling format, return as is
            if "type" in parameters_schema and "properties" in parameters_schema:
                return parameters_schema
            
            # Convert from simple description format to OpenRouter format
            properties = {}
            required = []
            
            for param_name, param_desc in parameters_schema.items():
                if isinstance(param_desc, str):
                    # Parse simple format like "string - description" or "integer (optional) - description"
                    desc_parts = param_desc.split(' - ', 1)
                    type_part = desc_parts[0].strip()
                    description = desc_parts[1] if len(desc_parts) > 1 else param_desc
                    
                    # Extract type and check if optional
                    is_optional = "(optional)" in type_part
                    type_part = type_part.replace("(optional)", "").strip()
                    
                    # Determine the parameter type
                    if type_part.startswith("string"):
                        param_type = "string"
                    elif type_part.startswith("integer"):
                        param_type = "integer"
                    elif type_part.startswith("number"):
                        param_type = "number"
                    elif type_part.startswith("boolean"):
                        param_type = "boolean"
                    elif type_part.startswith("array") or type_part.startswith("list"):
                        param_type = "array"
                        properties[param_name] = {
                            "type": "array",
                            "items": {"type": "string"},  # Default to string items
                            "description": description
                        }
                        continue
                    else:
                        param_type = "string"  # Default fallback
                    
                    properties[param_name] = {
                        "type": param_type,
                        "description": description
                    }
                    
                    if not is_optional:
                        required.append(param_name)
                        
                elif isinstance(param_desc, dict):
                    # Already in proper format
                    properties[param_name] = param_desc
                    if param_desc.get("required", True):
                        required.append(param_name)
            
            return {
                "type": "object",
                "properties": properties,
                "required": required
            }
            
        except Exception as e:
            logger.error(f"Error converting parameters schema: {e}")
            # Fallback to empty schema
            return {
                "type": "object",
                "properties": {},
                "required": []
            }
    
    async def process_triggers(self, trigger_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Process triggers by converting them into processing cycles.
        
        Args:
            trigger_data: List of trigger dictionaries with type, priority, data, and timestamp
            
        Returns:
            Dict containing processing results
        """
        if not trigger_data:
            logger.debug("No triggers to process")
            return {"triggers_processed": 0, "cycles_executed": 0}
        
        logger.debug(f"Processing {len(trigger_data)} triggers")
        
        # Sort triggers by priority (highest first)
        sorted_triggers = sorted(trigger_data, key=lambda t: t.get('priority', 0), reverse=True)
        
        # Generate a cycle ID based on the primary trigger
        primary_trigger = sorted_triggers[0]
        cycle_id = f"trigger-{primary_trigger['type']}-{int(time.time())}"
        
        # Extract context from triggers
        context = {
            "triggers": trigger_data,
            "primary_trigger_type": primary_trigger['type'],
            "trigger_count": len(trigger_data)
        }
        
        # Determine primary channel if any trigger specifies one
        primary_channel_id = None
        for trigger in trigger_data:
            if 'channel_id' in trigger.get('data', {}):
                primary_channel_id = trigger['data']['channel_id']
                break
        
        try:
            # Process the cycle
            cycle_result = await self.process_cycle(
                cycle_id=cycle_id,
                primary_channel_id=primary_channel_id,
                context=context
            )
            
            logger.debug(f"Trigger processing completed for cycle {cycle_id}")
            return {
                "triggers_processed": len(trigger_data),
                "cycles_executed": 1,
                "cycle_result": cycle_result
            }
            
        except Exception as e:
            logger.error(f"Error processing triggers in cycle {cycle_id}: {e}", exc_info=True)
            return {
                "triggers_processed": 0,
                "cycles_executed": 0,
                "error": str(e)
            }
    
    async def _execute_backlog_action(self, action: QueuedAction, cycle_id: str) -> Dict[str, Any]:
        """Execute a single action from the backlog"""
        try:
            # Convert backlog action to the format expected by _execute_action
            action_dict = {
                "action_type": action.action_type,
                "parameters": action.parameters,
                "reasoning": getattr(action, 'reasoning', f"Executing {action.action_type} from backlog")
            }
            
            # Execute using existing action execution infrastructure
            result = await self._execute_action(action_dict, cycle_id)
            
            # Log execution result with specific error message
            is_success = result.get("status") == "success"
            error_message = result.get("error") if not is_success else None

            if is_success:
                logger.debug(f"Successfully executed backlog action {action.action_id}: {action.action_type}")
            else:
                logger.warning(f"Failed to execute backlog action {action.action_id}: {error_message}")
            
            return {"status": result.get("status"), "result": result, "error": error_message}
            
        except Exception as e:
            logger.error(f"Error executing backlog action {action.action_id}: {e}", exc_info=True)
            return {"status": "failure", "error": str(e)}
    
    async def _build_planning_payload(self, primary_channel_id: Optional[str], 
                                     context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Build a payload for AI planning phase to decide on new actions"""
        try:
            # Get current world state
            world_state_data = self.world_state.get_world_state_data()
            
            # Build comprehensive payload for planning
            payload = self.payload_builder.build_node_based_payload(
                world_state_data=world_state_data,
                node_manager=self.node_manager,
                primary_channel_id=primary_channel_id or ""
            )
            
            # Store reference to world_state_data for template substitution
            payload["_world_state_data_ref"] = world_state_data
            
            # Add all available tools
            payload["tools"] = []
            if self.tool_registry:
                enabled_tools = self.tool_registry.get_enabled_tools()
                for tool in enabled_tools:
                    payload["tools"].append({
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": self._convert_parameters_schema(tool.parameters_schema)
                        }
                    })
            
            # Add node interaction tools
            node_interaction_tools = self.interaction_tools.get_tool_definitions()
            payload["tools"].extend(node_interaction_tools.values())
            
            # Add planning-specific context
            primary_trigger_type = context.get("primary_trigger_type")
            base_instruction = "Analyze the current world state and backlog status. Plan 3-8 high-value actions to add to the execution backlog based on current opportunities and context."
            
            # Get recent failures for AI feedback
            recent_failures = self._get_recent_action_failures()
            failure_summary = ""
            if recent_failures:
                failure_summary = f"Recent action failures ({len(recent_failures)}): " + ", ".join(
                    [f"'{f['action_type']}' failed with error: '{f['error'][:100]}...'" for f in recent_failures]
                )
            
            # Customize instruction based on trigger type
            if primary_trigger_type == "mention":
                instruction = f"{base_instruction} **IMPORTANT: You have been mentioned in a channel. This requires immediate attention and response. Check the recent messages in the primary channel ({primary_channel_id}) for the mention and respond appropriately.** Also consider other proactive engagement opportunities, but prioritize responding to the mention first."
                logger.debug(f"🔔 MENTION TRIGGER: AI being instructed to respond to mention in channel {primary_channel_id}")
            else:
                instruction = f"{base_instruction} Focus on responding to recent activity, mentions, or important updates, but also consider proactive engagement opportunities. Prioritize diverse actions across different channels and services when meaningful. Consider the current backlog to avoid redundant actions, but don't limit yourself unnecessarily - if there are genuine opportunities for valuable engagement, plan multiple complementary actions."
            
            payload["processing_context"] = {
                "mode": "kanban_planning",
                "primary_channel": primary_channel_id,
                "backlog_status": context.get("backlog_status", {}),
                "cycle_id": context.get("cycle_id"),
                "phase": "planning",
                "primary_trigger_type": primary_trigger_type,
                "triggers": context.get("triggers", []),
                "recent_failures": recent_failures,
                "failure_summary": failure_summary,
                "instruction": (
                    f"{instruction} "
                    "CRITICAL: Review 'recent_failures' to understand what did not work. Do not repeat failed actions. "
                    "Choose only valid tools from the provided list. If a tool call failed with 'Tool not found in registry', "
                    "that tool does not exist - use a different, valid tool instead."
                )
            }
            
            return payload
            
        except Exception as e:
            logger.error(f"Error building planning payload: {e}", exc_info=True)
            return None
    
    async def _get_planned_actions(self, payload: Dict[str, Any], cycle_id: str) -> List[Dict[str, Any]]:
        """Get planned actions from AI for the backlog"""
        try:
            # Log a summary of the AI payload being sent for planning (for debugging)
            payload_summary = {
                "cycle_id": cycle_id,
                "phase": "planning",
                "payload_keys": list(payload.keys()) if payload else [],
                "tools_count": len(payload.get("tools", [])),
                "payload_size_kb": len(str(payload)) / 1024 if payload else 0,
                "trigger_type": payload.get("processing_context", {}).get("primary_trigger_type")
            }
            logger.debug(f"AI Planning Payload Summary: {payload_summary}")
            
            # Use AI engine to get planning decisions
            decision_result = await self.ai_engine.decide_actions(
                world_state=payload
            )
            
            # Log AI reasoning for planning
            if decision_result.get('reasoning'):
                logger.debug(f"AI Planning Reasoning: {decision_result['reasoning']}")
            
            # Extract actions from the result
            planned_actions = decision_result.get('selected_actions', [])

            # --- START OF NO ACTION FAILURE DETECTION ---
            # Check if AI provided no tool calls and did not explicitly wait
            is_wait_action = any(action.get('action_type') == 'wait' for action in planned_actions)
            
            if not planned_actions and not is_wait_action:
                logger.warning("AI failed to select any action. This will be added to the failure context.")
                # Create a synthetic failure record for the feedback loop
                failure_record = {
                    "action_type": "no_action_selected",
                    "error": "The AI did not select any tool to execute.",
                    "reasoning": decision_result.get('reasoning'),
                    "message_generated": decision_result.get('message'),
                    "timestamp": time.time()
                }
                
                # Use the ActionBacklog to record this as a permanent failure for this cycle
                # This ensures it will be picked up by _get_recent_action_failures
                failed_action = QueuedAction(
                    action_id=f"no_action_{cycle_id}",
                    action_type="no_action_selected",
                    parameters={"reasoning": decision_result.get('reasoning')},
                    priority=ActionPriority.LOW,
                    service="system",
                    status=ActionStatus.FAILED,
                    error="AI did not select any tool to execute.",
                    last_attempt_at=time.time(),
                    attempts=1,
                    max_attempts=1
                )
                self.action_backlog.failed[failed_action.action_id] = failed_action
                
                # Return an empty list so the cycle ends and a new one can begin with failure context
                return []
            # --- END OF NO ACTION FAILURE DETECTION ---

            # Handle cases where the AI generates a direct message (inner monologue)
            if not planned_actions and decision_result.get('message'):
                logger.warning("AI generated a direct message instead of a tool call. Converting to internal monologue.")
                planned_actions.append({
                    "action_type": "log_internal_monologue",
                    "parameters": {"thought": decision_result['message']},
                    "reasoning": "AI generated a direct thought instead of an external action."
                })
            
            # Filter out 'wait' actions since we're building a backlog
            actionable_plans = [
                action for action in planned_actions 
                if action.get('action_type') != 'wait'
            ]
            
            if actionable_plans:
                logger.debug(f"AI planned {len(actionable_plans)} new actions for backlog")
                for action in actionable_plans:
                    logger.debug(f"Planned action: {action.get('action_type')} - {action.get('reasoning', 'No reasoning')}")
            
            return actionable_plans
            
        except Exception as e:
            logger.error(f"Error getting planned actions: {e}", exc_info=True)
            return []
    
    async def _should_trigger_immediate_planning(self, context: Dict[str, Any]) -> bool:
        """Check if we should trigger immediate planning based on world state changes"""
        trigger_type = context.get("trigger_type", "")
        
        # Immediate planning for high-priority triggers
        if trigger_type in ["mention", "dm", "direct_reply"]:
            return True
            
        # Immediate planning if backlog is completely empty
        if self._is_backlog_empty():
            return True
            
        # Check for significant world state changes that warrant immediate re-planning
        # (This could be extended with more sophisticated world state change detection)
        
        return False

    def _should_continue_cycle(self, actions_executed_count: int, cycle_start_time: float) -> bool:
        """Determine if the cycle should continue processing"""
        # Continue if we have actions in the backlog and haven't hit timeout
        if not self._is_backlog_empty():
            return True
            
        # Continue if we're still within a reasonable execution window and being productive
        cycle_duration = time.time() - cycle_start_time
        if cycle_duration < 60.0 and actions_executed_count > 0:
            return True
            
        return False

    async def _adaptive_planning_check(self, cycle_id: str, primary_channel_id: Optional[str], 
                                     context: Dict[str, Any], actions_executed_count: int):
        """Perform adaptive planning based on execution patterns and world state"""
        # If we've executed several actions, check if we need more
        if actions_executed_count > 0 and actions_executed_count % 5 == 0:
            total_queued = sum(len(queue) for queue in self.action_backlog.queued_actions.values())
            if total_queued < 3:  # Low backlog after execution - plan more
                logger.debug(f"Adaptive planning triggered after {actions_executed_count} actions with low backlog")
                await self._planning_phase(cycle_id, primary_channel_id, context)
                self._last_planning_time = time.time()

    def _get_recent_action_failures(self, max_failures: int = 3) -> List[Dict[str, Any]]:
        """Get recent action failures to provide feedback to AI."""
        try:
            if not self.action_backlog:
                return []
            
            # Get recent failures from the last 5 minutes
            cutoff_time = time.time() - 300
            recent_failures = []
            
            # The 'failed' dict holds permanently failed actions
            for action in list(self.action_backlog.failed.values()):
                if action.last_attempt_at and action.last_attempt_at >= cutoff_time:
                    failure_info = {
                        "action_type": action.action_type,
                        "error": (action.error or "Unknown error")[:200],  # Truncate error
                        "parameters": {k: str(v)[:50] for k, v in (action.parameters or {}).items()},
                        "attempts": action.attempts,
                        "timestamp": action.last_attempt_at
                    }
                    recent_failures.append(failure_info)
            
            # Sort by timestamp, most recent first
            recent_failures.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
            return recent_failures[:max_failures]
        except Exception as e:
            logger.error(f"Error getting recent action failures: {e}")
            return []
