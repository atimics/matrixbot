"""
Node Processor for Interactive Node-Based Processing

This module implements the core node processor that handles AI decision-making
using the node-based JSON Observer and Interactive Executor pattern.
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..world_state.manager import WorldStateManager
    from ..world_state.payload_builder import PayloadBuilder
    from ..ai_engine import AIDecisionEngine
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
        ai_engine: "AIDecisionEngine",
        node_manager: "NodeManager",
        summary_service: "NodeSummaryService",
        interaction_tools: "NodeInteractionTools",
        tool_registry=None,
        action_context=None
    ):
        self.world_state = world_state_manager
        self.payload_builder = payload_builder
        self.ai_engine = ai_engine
        self.node_manager = node_manager
        self.summary_service = summary_service
        self.interaction_tools = interaction_tools
        self.tool_registry = tool_registry
        self.action_context = action_context
        
        logger.info("NodeProcessor initialized with node-based processing capabilities")
    
    async def process_cycle(
        self,
        cycle_id: str,
        primary_channel_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Process a single cycle using an iterative action loop.
        The loop continues until the AI chooses to 'wait' or a limit is reached.
        
        Args:
            cycle_id: Unique identifier for this processing cycle
            primary_channel_id: The primary channel to focus on (optional)
            context: Additional context for processing
            
        Returns:
            Dict containing cycle results and metrics
        """
        context = context or {}
        cycle_start_time = time.time()
        actions_executed_count = 0
        MAX_ACTIONS_PER_CYCLE = 3  # Safety break to prevent infinite loops

        logger.info(f"Starting iterative processing cycle {cycle_id}")

        try:
            # Initial auto-expansion of active channels
            await self._auto_expand_active_channels()

            while actions_executed_count < MAX_ACTIONS_PER_CYCLE:
                # 1. Build payload based on the current state of the world
                payload = await self._build_current_payload(primary_channel_id, context)
                if not payload:
                    logger.warning("Failed to build payload, ending cycle.")
                    break

                # 2. Get the single next action from the AI
                ai_actions = await self._get_next_actions(payload, cycle_id, actions_executed_count)
                if not ai_actions:
                    logger.info("AI returned no actions, ending cycle.")
                    break

                # The AI can return multiple actions, but we process them one by one.
                # We primarily focus on the highest priority action.
                action_to_execute = ai_actions[0]

                # 3. If the action is 'wait', the cycle is complete
                if action_to_execute.action_type == "wait":
                    logger.info(f"AI chose to 'wait'. Cycle {cycle_id} complete.")
                    await self._execute_platform_tool(action_to_execute.action_type, action_to_execute.parameters, cycle_id)
                    actions_executed_count += 1
                    break

                # 4. Execute the chosen action
                logger.info(f"Cycle {cycle_id}, Step {actions_executed_count + 1}: Executing action '{action_to_execute.action_type}'")
                await self._execute_action(action_to_execute, cycle_id)
                actions_executed_count += 1
                
                # After an action, the world state has changed. The loop will now
                # build a new payload reflecting this change for the next AI decision.

            # Finalize cycle
            await self._update_node_summaries()
            self._log_node_system_events()

            cycle_duration = time.time() - cycle_start_time
            logger.info(f"Completed iterative cycle {cycle_id} in {cycle_duration:.2f}s - {actions_executed_count} actions executed")
            
            return {
                "cycle_id": cycle_id,
                "success": True,
                "actions_executed": actions_executed_count,
                "cycle_duration": cycle_duration
            }

        except Exception as e:
            logger.error(f"Error in iterative processing cycle {cycle_id}: {e}", exc_info=True)
            return {
                "cycle_id": cycle_id,
                "success": False,
                "error": str(e),
                "actions_executed": actions_executed_count,
            }
    
    async def _build_current_payload(self, primary_channel_id: Optional[str], context: Dict[str, Any]) -> Dict[str, Any]:
        """Build a single, unified payload for the current state of the world."""
        try:
            world_state_data = self.world_state.get_world_state_data()
            
            payload = self.payload_builder.build_node_based_payload(
                world_state_data=world_state_data,
                node_manager=self.node_manager,
                primary_channel_id=primary_channel_id or ""
            )

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
            
            # Add processing context
            payload["processing_context"] = {
                "mode": "iterative_action",
                "primary_channel": primary_channel_id,
                "cycle_context": context,
                "node_stats": self.node_manager.get_expansion_status_summary(),
                "instruction": "Based on the current world state, select the single most important action to take now. Choose 'wait' if no action is needed."
            }
            
            return payload
        except Exception as e:
            logger.error(f"Error building current payload: {e}", exc_info=True)
            return {}

    async def _get_next_actions(self, payload_data: Dict[str, Any], cycle_id: str, step: int):
        """Get the next action(s) from the AI."""
        try:
            decision_result = await self.ai_engine.make_decision(
                world_state=payload_data,
                cycle_id=f"{cycle_id}_step_{step}"
            )
            # Log the AI's reasoning for this step
            if decision_result.reasoning:
                logger.info(f"AI Reasoning for step {step}: {decision_result.reasoning}")
            return decision_result.selected_actions
        except Exception as e:
            logger.error(f"Error in AI action selection for cycle {cycle_id}, step {step}: {e}", exc_info=True)
            return []

    async def _execute_action(self, action, cycle_id: str):
        """Executes a single action and updates the world state."""
        tool_name = action.action_type
        tool_args = action.parameters
        
        # Log AI reasoning for selecting this action
        logger.info(f"AI reasoning: {action.reasoning}")

        # Dispatch to the correct tool executor
        if tool_name in ["select_nodes_to_expand", "expand_node", "collapse_node", "pin_node", "unpin_node"]:
            await self._execute_node_tool(tool_name, tool_args)
        elif tool_name == "refresh_summary":
            await self._execute_summary_refresh(tool_args)
        else:
            await self._execute_platform_tool(tool_name, tool_args, cycle_id)
    
    # Old methods removed - now using two-step approach with:
    # _build_node_selection_payload, _ai_select_nodes_to_expand
    # _build_action_selection_payload, _ai_select_actions

    async def _execute_ai_actions(
        self, 
        ai_response: Dict[str, Any], 
        cycle_id: str
    ) -> Dict[str, Any]:
        """Execute actions from AI response."""
        actions_executed = 0
        nodes_processed = set()
        
        try:
            # Handle tool calls from AI response (converted from ActionPlan objects)
            tool_calls = ai_response.get("tool_calls", [])
            
            # Also handle ActionPlan objects directly
            selected_actions = ai_response.get("selected_actions", [])
            
            # Process tool calls first
            for tool_call in tool_calls:
                try:
                    tool_name = tool_call.get("function", {}).get("name", "")
                    tool_args = tool_call.get("function", {}).get("arguments", {})
                    
                    # Handle node interaction tools
                    if tool_name in ["expand_node", "collapse_node", "pin_node", "unpin_node"]:
                        result = await self._execute_node_tool(tool_name, tool_args)
                        if result.get("success"):
                            actions_executed += 1
                            if "node_path" in tool_args:
                                nodes_processed.add(tool_args["node_path"])
                    
                    # Handle summary refresh
                    elif tool_name == "refresh_summary":
                        result = await self._execute_summary_refresh(tool_args)
                        if result.get("success"):
                            actions_executed += 1
                            if "node_path" in tool_args:
                                nodes_processed.add(tool_args["node_path"])
                    
                    # Handle other platform-specific tools
                    else:
                        result = await self._execute_platform_tool(tool_name, tool_args, cycle_id)
                        if result.get("success"):
                            actions_executed += 1
                
                except Exception as e:
                    # Extract tool_name safely in case it wasn't defined
                    safe_tool_name = tool_call.get("function", {}).get("name", "unknown") if 'tool_call' in locals() else "unknown"
                    logger.error(f"Error executing tool {safe_tool_name}: {e}")
                    continue
            
            # Process ActionPlan objects directly
            for action_plan in selected_actions:
                try:
                    tool_name = action_plan.action_type
                    tool_args = action_plan.parameters
                    
                    # Handle node interaction tools
                    if tool_name in ["expand_node", "collapse_node", "pin_node", "unpin_node"]:
                        result = await self._execute_node_tool(tool_name, tool_args)
                        if result.get("success"):
                            actions_executed += 1
                            if "node_path" in tool_args:
                                nodes_processed.add(tool_args["node_path"])
                    
                    # Handle summary refresh
                    elif tool_name == "refresh_summary":
                        result = await self._execute_summary_refresh(tool_args)
                        if result.get("success"):
                            actions_executed += 1
                            if "node_path" in tool_args:
                                nodes_processed.add(tool_args["node_path"])
                    
                    # Handle other platform-specific tools
                    else:
                        result = await self._execute_platform_tool(tool_name, tool_args, cycle_id)
                        if result.get("success"):
                            actions_executed += 1
                
                except Exception as e:
                    # Extract tool_name safely in case it wasn't defined
                    safe_tool_name = getattr(action_plan, 'action_type', 'unknown') if 'action_plan' in locals() else "unknown"
                    logger.error(f"Error executing action {safe_tool_name}: {e}")
                    continue
            
            return {
                "actions_executed": actions_executed,
                "nodes_processed": len(nodes_processed),
                "processed_node_paths": list(nodes_processed)
            }
            
        except Exception as e:
            logger.error(f"Error executing AI actions for cycle {cycle_id}: {e}", exc_info=True)
            return {"actions_executed": 0, "nodes_processed": 0}
    
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
            if not node_path:
                return {"success": False, "error": "Missing node_path"}
            
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
            
            else:
                return {"success": False, "error": f"Unknown node tool: {tool_name}"}
                
        except Exception as e:
            logger.error(f"Error executing node tool {tool_name}: {e}")
            return {"success": False, "error": str(e)}
    
    async def _execute_summary_refresh(self, tool_args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a summary refresh request."""
        try:
            node_path = tool_args.get("node_path", "")
            if not node_path:
                return {"success": False, "error": "Missing node_path"}
            
            # Get current node data
            world_state_data = self.world_state.get_world_state_data()
            node_data = self.payload_builder._get_node_data_by_path(world_state_data, node_path)
            
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
        """Execute a platform-specific tool through the tool registry."""
        try:
            # Use the tool registry and action context if provided
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
            
            # Execute the tool
            logger.info(f"Executing platform tool: {tool_name} with args {tool_args}")
            result = await tool_instance.execute(tool_args, action_context)
            
            return {
                "success": True,
                "message": f"Tool {tool_name} executed successfully",
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
            
            # Find all node paths that exist in world state
            all_node_paths = self.payload_builder._get_node_paths_from_world_state(world_state_data)
            
            # Get nodes that need summary updates
            nodes_needing_summary = self.node_manager.get_nodes_needing_summary(all_node_paths)
            
            # Update summaries for these nodes
            for node_path in nodes_needing_summary[:5]:  # Limit to 5 per cycle to avoid overload
                try:
                    node_data = self.payload_builder._get_node_data_by_path(world_state_data, node_path)
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
                if isinstance(feed_data, dict) and 'casts' in feed_data:
                    feed_casts = feed_data['casts']
                    if feed_casts:
                        # Get timestamp of most recent cast
                        latest_timestamp = max(
                            cast.get('timestamp', 0) for cast in feed_casts
                            if isinstance(cast, dict)
                        )
                        channel_activity[f"farcaster.feeds.{feed_name}"] = latest_timestamp
            
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
        self, 
        payload_data: Dict[str, Any], 
        cycle_id: str
    ) -> Dict[str, Any]:
        """First AI decision - select which nodes to expand."""
        try:
            if not payload_data:
                logger.warning(f"Empty payload for node selection in cycle {cycle_id}")
                return {"node_paths": [], "reasoning": "No payload data"}
            
            # Send to AI engine for node selection
            decision_result = await self.ai_engine.make_decision(
                world_state=payload_data,
                cycle_id=f"{cycle_id}_node_selection"
            )
            
            # Extract node selection from AI response
            selected_actions = decision_result.selected_actions
            for action_plan in selected_actions:
                if action_plan.action_type == "select_nodes_to_expand":
                    return {
                        "node_paths": action_plan.parameters.get("node_paths", []),
                        "reasoning": action_plan.parameters.get("reasoning", "No reasoning provided"),
                        "ai_reasoning": action_plan.reasoning
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
            
            # Send to AI engine for action selection
            decision_result = await self.ai_engine.make_decision(
                world_state=payload_data,
                cycle_id=f"{cycle_id}_action_selection"
            )
            
            # Convert DecisionResult to dict format expected by execution methods
            ai_response = {
                "reasoning": decision_result.reasoning,
                "observations": decision_result.observations,
                "selected_actions": decision_result.selected_actions,
                "tool_calls": []  # Convert ActionPlan objects to tool_calls format
            }
            
            # Convert ActionPlan objects to tool_calls format for execution
            for action_plan in decision_result.selected_actions:
                tool_call = {
                    "function": {
                        "name": action_plan.action_type,
                        "arguments": action_plan.parameters
                    },
                    "reasoning": action_plan.reasoning,
                    "priority": action_plan.priority
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
