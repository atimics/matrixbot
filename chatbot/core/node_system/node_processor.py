"""
Node Processor for Interactive Node-Based Processing

This module implements the core node processor that handles AI decision-making
using the node-based JSON Observer and Interactive Executor pattern.
"""

import asyncio
import logging
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
        Process a single cycle using node-based interactive approach.
        
        Args:
            cycle_id: Unique identifier for this processing cycle
            primary_channel_id: The primary channel to focus on (optional)
            context: Additional context for processing
            
        Returns:
            Dict containing cycle results and metrics
        """
        context = context or {}
        cycle_start_time = asyncio.get_event_loop().time()
        
        logger.debug(f"Starting node-based processing cycle {cycle_id}")
        
        try:
            # Step 1: Build node-aware AI payload
            payload_data = await self._build_node_payload(primary_channel_id, context)
            
            # Step 2: Process with AI and get decisions
            ai_response = await self._process_with_ai(payload_data, cycle_id)
            
            # Step 3: Execute any actions the AI decided to take
            execution_results = await self._execute_ai_actions(ai_response, cycle_id)
            
            # Step 4: Update node summaries if needed
            await self._update_node_summaries()
            
            # Step 5: Log system events from node operations
            self._log_node_system_events()
            
            cycle_duration = asyncio.get_event_loop().time() - cycle_start_time
            
            result = {
                "cycle_id": cycle_id,
                "success": True,
                "actions_executed": execution_results.get("actions_executed", 0),
                "nodes_processed": execution_results.get("nodes_processed", 0),
                "cycle_duration": cycle_duration,
                "primary_channel": primary_channel_id,
                "ai_response_summary": self._summarize_ai_response(ai_response),
                "payload_info": {
                    "expanded_nodes": len(self.node_manager.get_expanded_nodes()),
                    "payload_size": len(str(payload_data)) if payload_data else 0
                }
            }
            
            logger.info(f"Completed node-based cycle {cycle_id} in {cycle_duration:.2f}s - "
                       f"{result['actions_executed']} actions executed")
            
            return result
            
        except Exception as e:
            logger.error(f"Error in node-based processing cycle {cycle_id}: {e}", exc_info=True)
            return {
                "cycle_id": cycle_id,
                "success": False,
                "error": str(e),
                "actions_executed": 0,
                "nodes_processed": 0
            }
    
    async def _build_node_payload(
        self, 
        primary_channel_id: Optional[str],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build a node-aware payload for AI processing."""
        try:
            # Get current world state
            world_state_data = self.world_state.get_world_state_data()
            
            # Build node-based payload with expanded/collapsed state
            payload = self.payload_builder.build_node_based_payload(
                world_state_data=world_state_data,
                node_manager=self.node_manager,
                primary_channel_id=primary_channel_id or "default"
            )
            
            # Add node interaction tools to the payload
            if payload and "tools" not in payload:
                payload["tools"] = []
            
            # Add node management tools
            node_tools = self.interaction_tools.get_tool_definitions()
            if payload:
                payload["tools"].extend(node_tools.values())
            
            # Add all platform tools from tool registry
            if hasattr(self, 'tool_registry') and self.tool_registry and payload:
                platform_tools = self.tool_registry.get_tool_definitions()
                payload["tools"].extend(platform_tools)
                logger.debug(f"Added {len(platform_tools)} platform tools to payload")
            
            # Add processing context
            if payload:
                payload["processing_context"] = {
                    "mode": "node_based",
                    "primary_channel": primary_channel_id,
                    "cycle_context": context,
                    "node_stats": self.node_manager.get_expansion_status_summary()
                }
            
            return payload
            
        except Exception as e:
            logger.error(f"Error building node payload: {e}", exc_info=True)
            return {}
    
    async def _process_with_ai(
        self, 
        payload_data: Dict[str, Any], 
        cycle_id: str
    ) -> Dict[str, Any]:
        """Process the payload with AI and get response."""
        try:
            if not payload_data:
                logger.warning(f"Empty payload for cycle {cycle_id}")
                return {}
            
            # Send to AI engine using make_decision
            decision_result = await self.ai_engine.make_decision(
                world_state=payload_data,
                cycle_id=cycle_id
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
            logger.error(f"Error in AI processing for cycle {cycle_id}: {e}", exc_info=True)
            return {}

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
