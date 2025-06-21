"""
Node Interaction Tools for JSON Observer and Interactive Executor Pattern

This module provides AI tools for expanding, collapsing, pinning, and unpinning nodes
in the WorldState with automatic LRU management and payload size control.
"""

from typing import Any, Dict

from chatbot.config import settings
from .node_manager import NodeManager


class NodeInteractionTools:
    """Tools for AI to interact with expandable/collapsible nodes."""
    
    def __init__(self, node_manager: NodeManager):
        self.node_manager = node_manager
    
    def get_tool_definitions(self) -> Dict[str, Dict[str, Any]]:
        """Get all node interaction tool definitions for the AI."""
        return {
            "expand_node": {
                "type": "function",
                "function": {
                    "name": "expand_node",
                    "description": (
                        f"Expands a collapsed node in the world state to view its full details. "
                        f"Maximum {settings.node_system.max_expanded_nodes} nodes can be expanded simultaneously. "
                        f"If the limit is reached, the oldest unpinned expanded node will be "
                        f"automatically collapsed to make room. "
                        f"CRITICAL: You MUST use the full, exact node_path from the "
                        f"collapsed_node_summaries keys. DO NOT use channel names or abbreviated paths. "
                        f"Example: 'channels.matrix.!zBaUOGAwGyzOEGWJFd:chat.ratimics.com'"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "node_path": {
                                "type": "string",
                                "description": (
                                    "The EXACT path identifier from collapsed_node_summaries keys. "
                                    "Copy the full path exactly as shown, including all prefixes. "
                                    "Valid examples: 'channels.matrix.!room123:server.com', "
                                    "'channels.farcaster.home', 'users.farcaster.12345'. "
                                    "INVALID: channel names like 'Robot Laboratory' or bare room IDs."
                                )
                            }
                        },
                        "required": ["node_path"]
                    }
                }
            },
            "collapse_node": {
                "type": "function",
                "function": {
                    "name": "collapse_node",
                    "description": (
                        "Collapses an expanded node in the world state to hide its details "
                        "and rely on its summary. Use this when you're done examining a node "
                        "in detail to free up expansion slots for other nodes."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "node_path": {
                                "type": "string",
                                "description": "The path identifier of the currently expanded node to collapse"
                            }
                        },
                        "required": ["node_path"]
                    }
                }
            },
            "pin_node": {
                "type": "function",
                "function": {
                    "name": "pin_node",
                    "description": (
                        "Marks a node as important, preventing it from being auto-collapsed "
                        "when the expansion limit is reached. Use for nodes you want to keep "
                        "in detailed view for an extended period across multiple decision cycles."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "node_path": {
                                "type": "string",
                                "description": "The path identifier of the node to pin"
                            }
                        },
                        "required": ["node_path"]
                    }
                }
            },
            "unpin_node": {
                "type": "function",
                "function": {
                    "name": "unpin_node",
                    "description": (
                        "Removes the 'pinned' status from a node, allowing it to be "
                        "auto-collapsed if it becomes the oldest unpinned node when "
                        "the expansion limit is reached. Use when you no longer need "
                        "to keep a node permanently accessible."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "node_path": {
                                "type": "string",
                                "description": "The path identifier of the node to unpin"
                            }
                        },
                        "required": ["node_path"]
                    }
                }
            },
            "refresh_summary": {
                "type": "function",
                "function": {
                    "name": "refresh_summary",
                    "description": (
                        "Requests a new AI-generated summary for a specific node, "
                        "usually if its content has changed significantly or the current "
                        "summary is insufficient for understanding the node's relevance."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "node_path": {
                                "type": "string",
                                "description": "The path identifier of the node needing a summary refresh"
                            }
                        },
                        "required": ["node_path"]
                    }
                }
            },
            "get_expansion_status": {
                "type": "function",
                "function": {
                    "name": "get_expansion_status",
                    "description": (
                        "Get a summary of current node expansion status, including "
                        "which nodes are expanded, pinned, and how close to the "
                        "expansion limit you are. Useful for understanding context management."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            }
        }
    
    def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a node interaction tool.
        
        Returns:
            Dictionary with success status, message, and any relevant data
        """
        try:
            if tool_name == "expand_node":
                return self._expand_node(arguments["node_path"])
            elif tool_name == "collapse_node":
                return self._collapse_node(arguments["node_path"])
            elif tool_name == "pin_node":
                return self._pin_node(arguments["node_path"])
            elif tool_name == "unpin_node":
                return self._unpin_node(arguments["node_path"])
            elif tool_name == "refresh_summary":
                return self._refresh_summary(arguments["node_path"])
            elif tool_name == "get_expansion_status":
                return self._get_expansion_status()
            else:
                return {
                    "success": False,
                    "message": f"Unknown node tool: {tool_name}",
                    "error": "UNKNOWN_TOOL"
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error executing {tool_name}: {str(e)}",
                "error": "EXECUTION_ERROR"
            }
    
    def _expand_node(self, node_path: str) -> Dict[str, Any]:
        """Execute expand_node tool."""
        success, auto_collapsed, message = self.node_manager.expand_node(node_path)
        
        result = {
            "success": success,
            "message": message,
            "node_path": node_path,
            "action": "expand"
        }
        
        if auto_collapsed:
            result["auto_collapsed_node"] = auto_collapsed
            result["auto_collapse_reason"] = "expansion_limit_reached"
        
        return result
    
    def _collapse_node(self, node_path: str) -> Dict[str, Any]:
        """Execute collapse_node tool."""
        success, message = self.node_manager.collapse_node(node_path)
        
        return {
            "success": success,
            "message": message,
            "node_path": node_path,
            "action": "collapse"
        }
    
    def _pin_node(self, node_path: str) -> Dict[str, Any]:
        """Execute pin_node tool."""
        success, message = self.node_manager.pin_node(node_path)
        
        return {
            "success": success,
            "message": message,
            "node_path": node_path,
            "action": "pin"
        }
    
    def _unpin_node(self, node_path: str) -> Dict[str, Any]:
        """Execute unpin_node tool."""
        success, message = self.node_manager.unpin_node(node_path)
        
        return {
            "success": success,
            "message": message,
            "node_path": node_path,
            "action": "unpin"
        }
    
    def _refresh_summary(self, node_path: str) -> Dict[str, Any]:
        """Execute refresh_summary tool."""
        # This marks the node as needing a summary refresh
        # The actual summary generation happens in the orchestrator
        metadata = self.node_manager.get_node_metadata(node_path)
        metadata.ai_summary = None  # Clear existing summary to force regeneration
        metadata.last_summary_update_ts = None
        
        return {
            "success": True,
            "message": f"Marked {node_path} for summary refresh",
            "node_path": node_path,
            "action": "refresh_summary"
        }
    
    def _get_expansion_status(self) -> Dict[str, Any]:
        """Execute get_expansion_status tool."""
        status = self.node_manager.get_expansion_status_summary()
        
        return {
            "success": True,
            "message": "Current expansion status retrieved",
            "action": "get_expansion_status",
            "status": status
        }
