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
        
        logger.info("NodeProcessor initialized with Kanban-style action backlog system")
    
    async def process_cycle(
        self,
        cycle_id: str,
        primary_channel_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Process using Kanban-style continuous execution.
        
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
        context = context or {}
        cycle_start_time = time.time()
        actions_executed_count = 0
        planning_cycles = 0

        logger.info(f"Starting Kanban-style processing cycle {cycle_id}")

        # Ensure primary_channel_id is in context for priority interrupt handling
        if primary_channel_id:
            context["primary_channel_id"] = primary_channel_id

        # Update ActionContext with current channel information
        if self.action_context and primary_channel_id:
            self.action_context.update_current_channel(primary_channel_id)
            logger.debug(f"Updated ActionContext with primary channel: {primary_channel_id}")

        try:
            # CRITICAL FIX: Always ensure core channels are expanded for context
            await self._ensure_core_channels_expanded(primary_channel_id, context)
            
            # Also expand active channels for additional context
            await self._auto_expand_active_channels()

            # Main Kanban execution loop with extended timeout for continuous processing
            execution_timeout = self._max_execution_timeout  # Extended timeout for continuous processing
            while (time.time() - cycle_start_time) < execution_timeout and not self._shutdown_requested:
                
                # 1. Handle high-priority interrupts first
                await self._handle_priority_interrupts(context, cycle_id)
                
                # 2. Planning phase: Add new actions to backlog if needed
                if self._should_plan_new_actions():
                    planning_cycles += 1
                    await self._planning_phase(cycle_id, primary_channel_id, context)
                    self._last_planning_time = time.time()
                
                # 3. Execution phase: Execute actions from backlog
                executed_this_iteration = await self._execution_phase(cycle_id)
                actions_executed_count += executed_this_iteration
                
                # 4. If no actions executed and backlog is empty, break
                if executed_this_iteration == 0 and self._is_backlog_empty():
                    logger.info(f"No actions in backlog and none executed, ending cycle {cycle_id}")
                    break
                
                # 5. Brief pause to prevent tight loops
                if executed_this_iteration == 0:
                    await asyncio.sleep(0.1)

            # Finalize cycle
            return await self._finalize_cycle(
                cycle_id, cycle_start_time, actions_executed_count, planning_cycles
            )

        except Exception as e:
            logger.error(f"Error in Kanban processing cycle {cycle_id}: {e}", exc_info=True)
            return {
                "cycle_id": cycle_id,
                "success": False,
                "error": str(e),
                "actions_executed": actions_executed_count,
                "planning_cycles": planning_cycles
            }
    
    async def _finalize_cycle(self, cycle_id: str, cycle_start_time: float, 
                             actions_executed_count: int, planning_cycles: int = 0) -> Dict[str, Any]:
        """Helper method to finalize a processing cycle."""
        await self._update_node_summaries()
        self._log_node_system_events()

        cycle_duration = time.time() - cycle_start_time
        backlog_status = self.action_backlog.get_status_summary()
        
        logger.info(
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
    
    async def _handle_priority_interrupts(self, context: Dict[str, Any], cycle_id: str):
        """Handle high-priority interrupts like mentions and DMs"""
        trigger_type = context.get("trigger_type", "")
        primary_channel_id = context.get("primary_channel_id")
        
        if trigger_type in ["mention", "dm", "direct_reply"]:
            # Escalate priority of any queued communication actions
            await self._escalate_communication_actions()
            
            # If this is a critical trigger, add immediate response actions
            if trigger_type == "mention":
                logger.info(f"🔔 MENTION TRIGGER: AI being instructed to respond to mention in channel {primary_channel_id}")
                # Note: Core channel expansion is handled by _ensure_core_channels_expanded()
                logger.info(f"High-priority mention detected in cycle {cycle_id}, escalating response")
    
    async def _escalate_communication_actions(self):
        """Escalate priority of pending communication actions"""
        # Move any communication actions to high priority
        for priority_queue in self.action_backlog.queued_actions.values():
            for action in list(priority_queue):
                if action.action_type in ["send_matrix_reply", "send_farcaster_reply"]:
                    priority_queue.remove(action)
                    action.priority = ActionPriority.CRITICAL
                    self.action_backlog.queued_actions[ActionPriority.CRITICAL].appendleft(action)
                    logger.debug(f"Escalated {action.action_id} to CRITICAL priority")
    
    def _should_plan_new_actions(self) -> bool:
        """Determine if we should run AI planning to add new actions to backlog"""
        # Plan if backlog is low (increased threshold for more aggressive planning)
        total_queued = sum(len(queue) for queue in self.action_backlog.queued_actions.values())
        if total_queued < self._min_backlog_threshold:  # Increased from 3 to 5
            return True
            
        # Plan more frequently if enough time has passed since last planning
        if time.time() - self._last_planning_time > self._planning_interval:  # Reduced from 5s to 2s
            return True
            
        return False
    
    async def _planning_phase(self, cycle_id: str, primary_channel_id: Optional[str], 
                             context: Dict[str, Any]):
        """AI planning phase - analyze world state and add actions to backlog"""
        try:
            # Build planning payload
            planning_context = {
                **context,
                "phase": "planning",
                "backlog_status": self.action_backlog.get_status_summary(),
                "cycle_id": cycle_id
            }
            
            payload = await self._build_planning_payload(primary_channel_id, planning_context)
            if not payload:
                logger.warning("Failed to build planning payload")
                return
            
            # Get AI decisions for new actions
            ai_actions = await self._get_planned_actions(payload, cycle_id)
            if ai_actions:
                # Add actions to backlog
                action_ids = self.action_backlog.add_actions_batch(
                    ai_actions, 
                    cycle_context=planning_context
                )
                logger.info(f"Planning phase added {len(action_ids)} actions to backlog")
            else:
                logger.debug("Planning phase: AI suggested no new actions")
                
        except Exception as e:
            logger.error(f"Error in planning phase: {e}", exc_info=True)
    
    async def _execution_phase(self, cycle_id: str) -> int:
        """Execution phase - execute actions from backlog under rate limits"""
        actions_executed = 0
        
        try:
            # Execute actions while respecting rate limits and WIP constraints
            # Removed arbitrary max_iterations limit for more continuous execution
            iteration = 0
            
            while iteration < 50:  # Increased from 10 to 50 for more continuous execution
                iteration += 1
                
                # Get next executable action
                next_action = self.action_backlog.get_next_executable_action()
                if not next_action:
                    break  # No executable actions available
                
                # Start the action (acquire service resources)
                if not self.action_backlog.start_action(next_action):
                    logger.warning(f"Failed to start action {next_action.action_id}")
                    continue
                
                # Execute the action
                logger.info(f"Executing backlog action: {next_action.action_type} (priority: {next_action.priority.name})")
                execution_result = await self._execute_backlog_action(next_action, cycle_id)
                
                # Handle the action result
                result_status = execution_result.get("status")
                if result_status == "rate_limited":
                    # For rate limited actions, put them back in the queue with a delay
                    retry_after = execution_result.get("retry_after", 30)
                    logger.info(f"Action {next_action.action_id} rate limited, will retry after {retry_after} seconds")
                    
                    # Mark the action as queued again for retry, but don't increment attempts
                    # since this is a temporary condition
                    self.action_backlog.schedule_delayed_retry(next_action.action_id, retry_after)
                else:
                    # Complete the action normally
                    success = result_status == "success"
                    error = execution_result.get("error") if not success else None
                    self.action_backlog.complete_action(next_action.action_id, success, error)
                
                actions_executed += 1
                
                # Brief pause between actions
                await asyncio.sleep(0.05)
                
            return actions_executed
            
        except Exception as e:
            logger.error(f"Error in execution phase: {e}", exc_info=True)
            return actions_executed
    
    def _is_backlog_empty(self) -> bool:
        """Check if the action backlog is empty"""
        total_queued = sum(len(queue) for queue in self.action_backlog.queued_actions.values())
        total_in_progress = len(self.action_backlog.in_progress)
        return total_queued == 0 and total_in_progress == 0
    
    async def _build_current_payload(self, primary_channel_id: Optional[str], context: Dict[str, Any]) -> Dict[str, Any]:
        """Build a single, unified payload for the current state of the world."""
        try:
            world_state_data = self.world_state.get_world_state_data()
            
            payload = self.payload_builder.build_node_based_payload(
                world_state_data=world_state_data,
                node_manager=self.node_manager,
                primary_channel_id=primary_channel_id or ""
            )
            
            # Store reference to world_state_data for AI engine template substitution
            payload["_world_state_data_ref"] = world_state_data

            # Add all available tools to the payload
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
            
            # Add processing context with enhanced self-state awareness
            payload["processing_context"] = {
                "mode": "iterative_action",
                "primary_channel": primary_channel_id,
                "cycle_context": context,
                "node_stats": self.node_manager.get_expansion_status_summary(),
                "instruction": "Based on the current world state, select one or more actions to take in sequence. You can choose multiple non-conflicting actions that logically follow each other (e.g., generate_image followed by send_farcaster_post). Choose 'wait' if no action is needed."
            }
            
            # Add self-state awareness to prevent repetitive actions
            if "cycle_actions" in context:
                payload["self_state"] = {
                    "current_cycle_actions": context["cycle_actions"],
                    "actions_executed_this_cycle": context.get("actions_executed_this_cycle", 0),
                    "cycle_id": context.get("cycle_id"),
                    "guidance": self._generate_self_state_guidance(context["cycle_actions"])
                }
            
            # Log summary of the complete payload being sent to AI (for debugging)
            payload_summary = {
                "primary_channel": primary_channel_id,
                "payload_keys": list(payload.keys()) if payload else [],
                "tools_count": len(payload.get("tools", [])),
                "processing_mode": payload.get("processing_context", {}).get("mode"),
                "has_self_state": "self_state" in payload,
                "payload_size_kb": len(str(payload)) / 1024 if payload else 0
            }
            logger.info(f"Built AI Payload Summary: {payload_summary}")
            
            return payload
        except Exception as e:
            logger.error(f"Error building current payload: {e}", exc_info=True)
            return {}

    async def _get_next_actions(self, payload_data: Dict[str, Any], cycle_id: str, step: int):
        """Get the next action(s) from the AI."""
        try:
            # Log a summary of the AI payload being sent (for debugging)
            payload_summary = {
                "cycle_id": cycle_id,
                "step": step,
                "payload_keys": list(payload_data.keys()) if payload_data else [],
                "tools_count": len(payload_data.get("tools", [])),
                "processing_mode": payload_data.get("processing_context", {}).get("mode"),
                "primary_channel": payload_data.get("processing_context", {}).get("primary_channel"),
                "payload_size_kb": len(str(payload_data)) / 1024 if payload_data else 0
            }
            logger.info(f"AI Payload Summary: {payload_summary}")
            
            decision_result = await self.ai_engine.decide_actions(
                world_state=payload_data
            )
            # Log the AI's reasoning for this step
            if decision_result.get('reasoning'):
                logger.info(f"AI Reasoning for step {step}: {decision_result['reasoning']}")
            return decision_result.get('selected_actions', [])
        except Exception as e:
            logger.error(f"Error in AI action selection for cycle {cycle_id}, step {step}: {e}", exc_info=True)
            return []

    async def _execute_action(self, action, cycle_id: str) -> Dict[str, Any]:
        """Executes a single action and updates the world state."""
        tool_name = action["action_type"]
        tool_args = action["parameters"]

        # --- BEGIN TOOL DISAMBIGUATION ---
        # If the AI uses a generic tool name, attempt to map it to a specific one.
        original_tool_name = tool_name
        platform = None # Initialize platform to None
        if tool_name in ["send_message", "send_reply", "react_to_message"]:
            # Determine platform from channel_id/room_id
            channel_id = tool_args.get("channel_id") or tool_args.get("room_id")
            
            if isinstance(channel_id, str) and channel_id.startswith("!"):
                platform = "matrix"
                if tool_name == "send_message":
                    tool_name = "send_matrix_message"
                    tool_args = {
                        "room_id": channel_id,
                        "message": tool_args.get("text") or tool_args.get("message", ""),
                        "attach_image": tool_args.get("attach_image")
                    }
                elif tool_name == "send_reply":
                    tool_name = "send_matrix_reply"
                    tool_args = {
                        "room_id": channel_id,
                        "event_id": tool_args.get("event_id"),
                        "message": tool_args.get("text") or tool_args.get("message", ""),
                        "attach_image": tool_args.get("attach_image")
                    }
                elif tool_name == "react_to_message":
                    tool_name = "react_to_matrix_message"
                    tool_args = {
                        "room_id": channel_id,
                        "event_id": tool_args.get("event_id"),
                        "reaction": tool_args.get("reaction") or tool_args.get("emoji")
                    }
            # TODO: Add disambiguation for other platforms like Farcaster if needed
            
            if tool_name != original_tool_name:
                logger.warning(
                    f"AI used generic tool '{original_tool_name}'. Disambiguated to "
                    f"'{tool_name}' for platform '{platform}' based on channel_id."
                )
                # Update action details for execution
                action["action_type"] = tool_name
                action["parameters"] = tool_args

        # --- END TOOL DISAMBIGUATION ---
        
        # Log AI reasoning for selecting this action
        logger.info(f"AI reasoning: {action.get('reasoning', 'No reasoning provided')}")
        
        # *** VERBOSE LOGGING FOR BUG DIAGNOSIS ***
        logger.info(f"Executing action '{tool_name}' with args: {tool_args}")

        try:
            # Dispatch to the correct tool executor
            if tool_name in ["select_nodes_to_expand", "expand_node", "collapse_node", "pin_node", "unpin_node", "get_expansion_status"]:
                result = await self._execute_node_tool(tool_name, tool_args)
                logger.info(f"Node tool '{tool_name}' result: {result}")
                # Node tools return success/fail, let's normalize to status
                return {"status": "success" if result.get("success") else "failure", "result": result}
            elif tool_name == "refresh_summary":
                refresh_result = await self._execute_summary_refresh(tool_args)
                status = "success" if refresh_result.get("success") else "failure"
                return {"status": status, "result": refresh_result}
            else:
                result = await self._execute_platform_tool(tool_name, tool_args, cycle_id)
                
                # The result from the tool itself is in result['tool_result'].
                # That's what contains the 'status' field ('success', 'failure', 'error', 'rate_limited').
                # We need to propagate this status up to the process_cycle loop.
                tool_result = result.get("tool_result", {})
                
                # Determine the overall status. Default to success if not specified.
                status = tool_result.get("status", "success")
                
                # Handle rate limiting specially
                if status == "rate_limited":
                    retry_after = tool_result.get("retry_after", 30)
                    next_attempt_time = tool_result.get("next_attempt_time", time.time() + retry_after)
                    logger.info(f"Action rate limited, will retry after {retry_after} seconds")
                    return {
                        "status": "rate_limited", 
                        "result": result,
                        "retry_after": retry_after,
                        "next_attempt_time": next_attempt_time
                    }
                
                # If the outer tool execution failed, that should take precedence.
                if not result.get("success", True):
                    status = "failure"
                    
                return {"status": status, "result": result}
        except Exception as e:
            logger.error(f"Error executing action '{tool_name}': {e}", exc_info=True)
            return {"status": "failure", "error": str(e)}
    
    # Old methods removed - now using two-step approach with:
    # _build_node_selection_payload, _ai_select_nodes_to_expand
    # _build_action_selection_payload, _ai_select_actions
    
    async def _execute_node_tool(
        self, 
        tool_name: str, 
        tool_args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a node interaction tool."""
        try:
            # The tool 'select_nodes_to_expand' is now handled here.
            # It's essentially multiple 'expand_node' calls.
            if tool_name == "select_nodes_to_expand":
                node_paths = tool_args.get("node_paths", [])
                logger.info(f"AI selected {len(node_paths)} nodes for expansion: {node_paths}")
                for node_path in node_paths:
                    success, auto_collapsed, message = self.node_manager.expand_node(node_path)
                    logger.info(f"Expansion of '{node_path}': {message}")
                return {"success": True, "message": f"Expanded {len(node_paths)} nodes."}

            node_path = tool_args.get("node_path", "")
            
            # Some tools don't require a node_path
            if tool_name not in ["get_expansion_status"] and not node_path:
                return {"success": False, "error": "Missing node_path"}
            
            # *** INPUT SANITIZATION FOR NODE PATH MISMATCH BUG ***
            # Attempt to correct incomplete node paths (skip for tools that don't need paths)
            if tool_name not in ["get_expansion_status"]:
                original_node_path = node_path
                if node_path not in self.node_manager.node_metadata:
                    corrected_path = self._find_full_path(node_path)
                    if corrected_path:
                        logger.warning(f"Corrected ambiguous node_path '{node_path}' to '{corrected_path}'")
                        node_path = corrected_path
                        tool_args["node_path"] = corrected_path  # Update args for consistency
                    else:
                        # If no correction is found, fail gracefully
                        all_known_paths = self.node_manager.get_all_node_paths()
                        return {
                            "success": False, 
                            "error": f"Node path '{original_node_path}' not found or is ambiguous. Available paths: {all_known_paths[:5]}..."  # Limit output
                        }
            # *** END OF INPUT SANITIZATION ***
            
            if tool_name == "expand_node":
                success, auto_collapsed, message = self.node_manager.expand_node(node_path)
                return {
                    "success": success,
                    "message": message,
                    "auto_collapsed": auto_collapsed
                }
            
            elif tool_name == "collapse_node":
                success, message = self.node_manager.collapse_node(node_path)
                return {"success": success, "message": message}
            
            elif tool_name == "pin_node":
                success, message = self.node_manager.pin_node(node_path)
                return {"success": success, "message": message}
            
            elif tool_name == "unpin_node":
                success, message = self.node_manager.unpin_node(node_path)
                return {"success": success, "message": message}
            
            elif tool_name == "get_expansion_status":
                # This tool doesn't need a node_path, get status from interaction_tools
                status = self.interaction_tools.execute_tool(tool_name, {})
                return status
            
            else:
                return {"success": False, "error": f"Unknown node tool: {tool_name}"}
                
        except Exception as e:
            logger.error(f"Error executing node tool {tool_name}: {e}")
            return {"success": False, "error": str(e)}
    
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
            return f"WARNING: You attempted to expand node '{last_expand['parameters'].get('node_path')}' in step {last_expand['step']}. If it didn't work, the node path may be incorrect or the node is already expanded. Consider a different action."
        
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
            logger.info(f"Executing platform tool: {tool_name} with args {tool_args}")
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
                logger.info(f"Node system event: {event['event_type']} - {event['message']}")
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
                        logger.info(f"🔧 CORE EXPANSION: {channel_type} -> {node_path} (trigger: {trigger_type})")
                        if auto_collapsed:
                            logger.info(f"   ↳ Auto-collapsed {auto_collapsed} to make room")
                    else:
                        logger.debug(f"Core expansion skipped {channel_type} -> {node_path}: {message}")
                except Exception as e:
                    logger.warning(f"Error expanding core channel {channel_type} ({node_path}): {e}")
            
            if expanded_count > 0:
                logger.info(f"🎯 CORE CHANNELS: Ensured {expanded_count} essential channels are expanded for AI context")
                
                # DEBUG: Verify the expansion state immediately after expansion
                for channel_type, node_path in channels_to_expand:
                    metadata = self.node_manager.get_node_metadata(node_path)
                    logger.info(f"🔍 VERIFY EXPANSION: {node_path} -> is_expanded={metadata.is_expanded}, is_pinned={metadata.is_pinned}")
            else:
                logger.info("🎯 CORE CHANNELS: All essential channels were already expanded")
                
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
                    logger.info(f"Auto-expanded {len(auto_expanded)} active channels: {auto_expanded}")
                    
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
                payload["processing_context"] = {
                    "mode": "action_selection",
                    "primary_channel": primary_channel_id,
                    "cycle_context": context,
                    "node_stats": self.node_manager.get_expansion_status_summary(),
                    "instruction": "Now take appropriate actions based on the expanded node content. Prioritize platform communication tools over node management."
                }
            
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
            logger.info(f"AI Node Selection Payload Summary: {payload_summary}")

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
            logger.info(f"AI Action Selection Payload Summary: {payload_summary}")

            # Send to AI engine for action selection
            decision_result = await self.ai_engine.decide_actions(
                world_state=payload_data
            )
            
            # Convert dict result to format expected by execution methods
            ai_response = {
                "reasoning": decision_result.get('reasoning', ''),
                "observations": decision_result.get('reasoning', ''),  # Map reasoning to observations for compatibility
                "selected_actions": decision_result.get('selected_actions', []),
                "tool_calls": []  # Convert action dict objects to tool_calls format
            }
            
            # Convert action dict objects to tool_calls format for execution
            for action_plan in decision_result.get('selected_actions', []):
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
            
            logger.info(f"AI selected {len(node_paths)} nodes for expansion: {node_paths}")
            logger.info(f"AI reasoning: {reasoning}")
            
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
            logger.info("No triggers to process")
            return {"triggers_processed": 0, "cycles_executed": 0}
        
        logger.info(f"Processing {len(trigger_data)} triggers")
        
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
            
            logger.info(f"Trigger processing completed for cycle {cycle_id}")
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
            
            # Log execution result
            if result.get("status") == "success":
                logger.debug(f"Successfully executed backlog action {action.action_id}: {action.action_type}")
            else:
                logger.warning(f"Failed to execute backlog action {action.action_id}: {result.get('error', 'Unknown error')}")
            
            return result
            
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
            
            # Customize instruction based on trigger type
            if primary_trigger_type == "mention":
                instruction = f"{base_instruction} **IMPORTANT: You have been mentioned in a channel. This requires immediate attention and response. Check the recent messages in the primary channel ({primary_channel_id}) for the mention and respond appropriately.** Also consider other proactive engagement opportunities, but prioritize responding to the mention first."
                logger.info(f"🔔 MENTION TRIGGER: AI being instructed to respond to mention in channel {primary_channel_id}")
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
                "instruction": instruction
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
            logger.info(f"AI Planning Payload Summary: {payload_summary}")
            
            # Use AI engine to get planning decisions
            decision_result = await self.ai_engine.decide_actions(
                world_state=payload
            )
            
            # Log AI reasoning for planning
            if decision_result.get('reasoning'):
                logger.info(f"AI Planning Reasoning: {decision_result['reasoning']}")
            
            # Extract actions from the result
            planned_actions = decision_result.get('selected_actions', [])
            
            # Filter out 'wait' actions since we're building a backlog
            actionable_plans = [
                action for action in planned_actions 
                if action.get('action_type') != 'wait'
            ]
            
            if actionable_plans:
                logger.info(f"AI planned {len(actionable_plans)} new actions for backlog")
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
                logger.info(f"Adaptive planning triggered after {actions_executed_count} actions with low backlog")
                await self._planning_phase(cycle_id, primary_channel_id, context)
                self._last_planning_time = time.time()
