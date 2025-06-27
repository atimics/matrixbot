"""
Node Management Tools - Unified Tool Interface for Node Interactions

This module implements node management capabilities as first-class ToolInterface tools,
eliminating the separate execution path and unifying all tool execution through the 
main ToolRegistry and ActionExecutor pipeline.

These tools replace the manual if/elif dispatch in NodeInteractionTools.execute_tool
with proper ToolInterface implementations that can be registered in the main tool registry.
"""

import logging
import time
from typing import Any, Dict

from .base import ToolInterface, ActionContext
from ..config import settings

logger = logging.getLogger(__name__)


class ExpandNodeTool(ToolInterface):
    """Expands a collapsed node to view its full details."""

    @property
    def name(self) -> str:
        return "expand_node"

    @property
    def description(self) -> str:
        return (
            f"Expands a collapsed node in the world state to view its full details. "
            f"Maximum {settings.processing.max_expanded_nodes} nodes can be expanded simultaneously. "
            f"If the limit is reached, the oldest unpinned expanded node will be "
            f"automatically collapsed to make room. For channel nodes, expansion provides "
            f"enhanced context including {settings.expanded_channel_recent_messages} recent messages "
            f"(vs {settings.collapsed_channel_recent_messages} for collapsed), full message content, "
            f"user context, thread relationships, and activity metrics. "
            f"Provide the node_path from the summary view."
        )

    @property
    def access_level(self) -> str:
        return 'strategic'

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "node_path": (
                "string - The path identifier of the node to expand (e.g., "
                "'channels.matrix.!room_id', 'users.farcaster.123', "
                "'threads.farcaster.0xhash')"
            )
        }

    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        """Execute the expand node action."""
        logger.info(f"Executing tool '{self.name}' with params: {params}")

        node_path = params.get("node_path")
        if not node_path:
            error_msg = "Missing required parameter: node_path"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Get node manager from action context
        node_manager = getattr(context, 'node_manager', None)
        if not node_manager:
            # CRITICAL FIX: Try alternative paths for accessing node_manager
            if hasattr(context, 'world_state_manager') and hasattr(context.world_state_manager, 'node_manager'):
                node_manager = context.world_state_manager.node_manager
            else:
                error_msg = "Node manager not available in action context"
                logger.error(error_msg)
                return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        try:
            success, auto_collapsed, message = node_manager.expand_node(node_path)
            
            result = {
                "status": "success" if success else "failure",
                "message": message,
                "node_path": node_path,
                "action": "expand",
                "timestamp": time.time()
            }
            
            if auto_collapsed:
                result["auto_collapsed_node"] = auto_collapsed
                result["auto_collapse_reason"] = "expansion_limit_reached"
            
            # Add enhanced context information for channel expansions
            if success and node_path.startswith("channels."):
                from ..config import settings
                result["enhanced_context"] = {
                    "recent_messages_count": settings.expanded_channel_recent_messages,
                    "message_detail_level": settings.expanded_channel_message_detail_level,
                    "includes_user_context": settings.expanded_channel_include_user_context,
                    "includes_thread_context": settings.expanded_channel_include_thread_context,
                    "includes_activity_metrics": settings.expanded_channel_include_activity_metrics,
                    "includes_sentiment": settings.expanded_channel_include_sentiment,
                    "lookback_hours": settings.expanded_channel_lookback_hours
                }
                result["message"] += f" - Enhanced context now available with {settings.expanded_channel_recent_messages} recent messages and enriched metadata."
            
            if success:
                logger.info(f"Successfully expanded node: {node_path}")
            else:
                logger.warning(f"Failed to expand node {node_path}: {message}")
            
            return result

        except Exception as e:
            error_msg = f"Error expanding node {node_path}: {str(e)}"
            logger.exception(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}


class CollapseNodeTool(ToolInterface):
    """Collapses an expanded node to hide its details."""

    @property
    def name(self) -> str:
        return "collapse_node"

    @property
    def description(self) -> str:
        return (
            "Collapses an expanded node in the world state to hide its details "
            "and rely on its summary. Use this when you're done examining a node "
            "in detail to free up expansion slots for other nodes."
        )

    @property
    def access_level(self) -> str:
        return 'strategic'

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "node_path": "string - The path identifier of the currently expanded node to collapse"
        }

    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        """Execute the collapse node action."""
        logger.info(f"Executing tool '{self.name}' with params: {params}")

        node_path = params.get("node_path")
        if not node_path:
            error_msg = "Missing required parameter: node_path"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Get node manager from action context
        node_manager = getattr(context, 'node_manager', None)
        if not node_manager:
            error_msg = "Node manager not available in action context"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        try:
            success, message = node_manager.collapse_node(node_path)
            
            result = {
                "status": "success" if success else "failure",
                "message": message,
                "node_path": node_path,
                "action": "collapse",
                "timestamp": time.time()
            }
            
            if success:
                logger.info(f"Successfully collapsed node: {node_path}")
            else:
                logger.warning(f"Failed to collapse node {node_path}: {message}")
            
            return result

        except Exception as e:
            error_msg = f"Error collapsing node {node_path}: {str(e)}"
            logger.exception(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}


class PinNodeTool(ToolInterface):
    """Marks a node as important, preventing auto-collapse."""

    @property
    def name(self) -> str:
        return "pin_node"

    @property
    def description(self) -> str:
        return (
            "Marks a node as important, preventing it from being auto-collapsed "
            "when the expansion limit is reached. Use for nodes you want to keep "
            "in detailed view for an extended period across multiple decision cycles."
        )

    @property
    def access_level(self) -> str:
        return 'strategic'

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "node_path": "string - The path identifier of the node to pin"
        }

    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        """Execute the pin node action."""
        logger.info(f"Executing tool '{self.name}' with params: {params}")

        node_path = params.get("node_path")
        if not node_path:
            error_msg = "Missing required parameter: node_path"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Get node manager from action context
        node_manager = getattr(context, 'node_manager', None)
        if not node_manager:
            error_msg = "Node manager not available in action context"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        try:
            success, message = node_manager.pin_node(node_path)
            
            result = {
                "status": "success" if success else "failure",
                "message": message,
                "node_path": node_path,
                "action": "pin",
                "timestamp": time.time()
            }
            
            if success:
                logger.info(f"Successfully pinned node: {node_path}")
            else:
                logger.warning(f"Failed to pin node {node_path}: {message}")
            
            return result

        except Exception as e:
            error_msg = f"Error pinning node {node_path}: {str(e)}"
            logger.exception(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}


class UnpinNodeTool(ToolInterface):
    """Removes the pinned status from a node."""

    @property
    def name(self) -> str:
        return "unpin_node"

    @property
    def description(self) -> str:
        return (
            "Removes the 'pinned' status from a node, allowing it to be "
            "auto-collapsed if it becomes the oldest unpinned node when "
            "the expansion limit is reached. Use when you no longer need "
            "to keep a node permanently accessible."
        )

    @property
    def access_level(self) -> str:
        return 'strategic'

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "node_path": "string - The path identifier of the node to unpin"
        }

    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        """Execute the unpin node action."""
        logger.info(f"Executing tool '{self.name}' with params: {params}")

        node_path = params.get("node_path")
        if not node_path:
            error_msg = "Missing required parameter: node_path"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Get node manager from action context
        node_manager = getattr(context, 'node_manager', None)
        if not node_manager:
            error_msg = "Node manager not available in action context"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        try:
            success, message = node_manager.unpin_node(node_path)
            
            result = {
                "status": "success" if success else "failure",
                "message": message,
                "node_path": node_path,
                "action": "unpin",
                "timestamp": time.time()
            }
            
            if success:
                logger.info(f"Successfully unpinned node: {node_path}")
            else:
                logger.warning(f"Failed to unpin node {node_path}: {message}")
            
            return result

        except Exception as e:
            error_msg = f"Error unpinning node {node_path}: {str(e)}"
            logger.exception(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}


class RefreshSummaryTool(ToolInterface):
    """Requests a new AI-generated summary for a specific node."""

    @property
    def name(self) -> str:
        return "refresh_summary"

    @property
    def description(self) -> str:
        return (
            "Requests a new AI-generated summary for a specific node, "
            "usually if its content has changed significantly or the current "
            "summary is insufficient for understanding the node's relevance."
        )

    @property
    def access_level(self) -> str:
        return 'strategic'

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "node_path": "string - The path identifier of the node needing a summary refresh"
        }

    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        """Execute the refresh summary action."""
        logger.info(f"Executing tool '{self.name}' with params: {params}")

        node_path = params.get("node_path")
        if not node_path:
            error_msg = "Missing required parameter: node_path"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Get node manager from action context
        node_manager = getattr(context, 'node_manager', None)
        if not node_manager:
            error_msg = "Node manager not available in action context"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        try:
            # Mark the node as needing a summary refresh
            # The actual summary generation happens in the orchestrator
            metadata = node_manager.get_node_metadata(node_path)
            metadata.ai_summary = None  # Clear existing summary to force regeneration
            metadata.last_summary_update_ts = None
            
            success_msg = f"Marked {node_path} for summary refresh"
            result = {
                "status": "success",
                "message": success_msg,
                "node_path": node_path,
                "action": "refresh_summary",
                "timestamp": time.time()
            }
            
            logger.info(success_msg)
            return result

        except Exception as e:
            error_msg = f"Error refreshing summary for node {node_path}: {str(e)}"
            logger.exception(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}


class GetExpansionStatusTool(ToolInterface):
    """Get a summary of current node expansion status."""

    @property
    def name(self) -> str:
        return "get_expansion_status"

    @property
    def description(self) -> str:
        return (
            "Get a summary of current node expansion status, including "
            "which nodes are expanded, pinned, and how close to the "
            "expansion limit you are. Useful for understanding context management."
        )

    @property
    def access_level(self) -> str:
        return 'strategic'

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {}  # No parameters required

    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        """Execute the get expansion status action."""
        logger.info(f"Executing tool '{self.name}' with params: {params}")

        # Get node manager from action context
        node_manager = getattr(context, 'node_manager', None)
        if not node_manager:
            error_msg = "Node manager not available in action context"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        try:
            status = node_manager.get_expansion_status_summary()
            
            # Add enhanced context configuration information
            from ..config import settings
            enhanced_context_info = {
                "expanded_channel_messages": settings.expanded_channel_recent_messages,
                "collapsed_channel_messages": settings.collapsed_channel_recent_messages,
                "message_detail_level": settings.expanded_channel_message_detail_level,
                "includes_user_context": settings.expanded_channel_include_user_context,
                "includes_thread_context": settings.expanded_channel_include_thread_context,
                "includes_activity_metrics": settings.expanded_channel_include_activity_metrics,
                "lookback_hours": settings.expanded_channel_lookback_hours
            }
            
            # Count expanded channel nodes
            expanded_channels = [node for node in status.get("pinned_nodes", []) + status.get("unpinned_nodes", []) 
                               if node.startswith("channels.")]
            
            result = {
                "status": "success",
                "message": "Current expansion status retrieved",
                "action": "get_expansion_status",
                "expansion_status": status,
                "enhanced_context_config": enhanced_context_info,
                "expanded_channels": expanded_channels,
                "expanded_channels_count": len(expanded_channels),
                "timestamp": time.time()
            }
            
            logger.info("Successfully retrieved expansion status")
            return result

        except Exception as e:
            error_msg = f"Error getting expansion status: {str(e)}"
            logger.exception(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}
