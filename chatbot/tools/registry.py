"""
Tool registry for dynamic tool management and AI prompt generation.
"""
import json
import logging
from typing import Any, Dict, List, Optional

from .base import ToolInterface

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    Registry for managing available tools and generating AI prompts.
    """

    def __init__(self):
        self._tools: Dict[str, ToolInterface] = {}
        self._tool_enabled_status: Dict[str, bool] = {}  # Track enabled/disabled status

    def register_tool(self, tool: ToolInterface, enabled: bool = True) -> None:
        """
        Register a tool in the registry.

        Args:
            tool: Tool instance implementing ToolInterface
            enabled: Whether the tool should be enabled by default
        """
        if tool.name in self._tools:
            logger.warning(f"Tool '{tool.name}' is already registered. Overwriting.")

        self._tools[tool.name] = tool
        self._tool_enabled_status[tool.name] = enabled
        logger.info(f"Tool '{tool.name}' registered successfully (enabled: {enabled}).")

    def get_tool(self, name: str) -> Optional[ToolInterface]:
        """
        Retrieve a tool by name.

        Args:
            name: Tool name

        Returns:
            Tool instance or None if not found
        """
        return self._tools.get(name)

    def get_all_tools(self) -> List[ToolInterface]:
        """
        Get all registered tools.

        Returns:
            List of all tool instances
        """
        return list(self._tools.values())

    def get_tool_names(self) -> List[str]:
        """
        Get names of all registered tools.

        Returns:
            List of tool names
        """
        return list(self._tools.keys())

    def get_tool_descriptions_for_ai(self) -> str:
        """
        Generate a formatted string describing all enabled tools for AI prompts.

        Returns:
            Formatted string with tool descriptions and parameters
        """
        if not self._tools:
            return "No tools currently available."

        descriptions = []
        for tool in self._tools.values():
            # Only include enabled tools
            if not self.is_tool_enabled(tool.name):
                continue
                
            desc = f"- {tool.name}:\n"
            desc += f"  Description: {tool.description}\n"

            # Format parameters schema nicely
            if tool.parameters_schema:
                desc += "  Parameters:\n"
                for param_name, param_desc in tool.parameters_schema.items():
                    desc += f"    - {param_name}: {param_desc}\n"
            else:
                desc += "  Parameters: None\n"

            descriptions.append(desc)

        if not descriptions:
            return "No enabled tools currently available."

        return "\nAvailable tools:\n" + "\n".join(descriptions)

    def validate_tool_call(
        self, tool_name: str, params: Dict[str, any]
    ) -> Dict[str, any]:
        """
        Validate a tool call before execution.

        Args:
            tool_name: Name of the tool to validate
            params: Parameters for the tool

        Returns:
            Dict with validation result:
            - valid: bool
            - error: str (if not valid)
            - missing_params: List[str] (if applicable)
        """
        tool = self.get_tool(tool_name)
        if not tool:
            return {
                "valid": False,
                "error": f"Tool '{tool_name}' not found in registry",
            }

        # Basic parameter validation could be enhanced here
        # For now, just check if tool exists
        return {"valid": True}

    def set_tool_enabled(self, tool_name: str, enabled: bool) -> bool:
        """
        Enable or disable a tool.

        Args:
            tool_name: Name of the tool to enable/disable
            enabled: True to enable, False to disable

        Returns:
            True if successful, False if tool not found
        """
        if tool_name not in self._tools:
            logger.warning(f"Cannot set status for unknown tool: {tool_name}")
            return False
        
        self._tool_enabled_status[tool_name] = enabled
        logger.info(f"Tool '{tool_name}' enabled status set to: {enabled}")
        return True

    def is_tool_enabled(self, tool_name: str) -> bool:
        """
        Check if a tool is enabled.

        Args:
            tool_name: Name of the tool to check

        Returns:
            True if enabled, False if disabled or not found
        """
        return self._tool_enabled_status.get(tool_name, True)  # Default to enabled

    def get_all_tools_with_status(self) -> List[Dict[str, Any]]:
        """
        Get all tools with their enabled status and metadata.

        Returns:
            List of dictionaries containing tool information
        """
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters_schema": tool.parameters_schema,
                "enabled": self.is_tool_enabled(tool.name)
            }
            for tool in self._tools.values()
        ]

    def get_enabled_tools(self) -> List[ToolInterface]:
        """
        Get all enabled tools.

        Returns:
            List of enabled tool instances
        """
        return [
            tool for tool in self._tools.values()
            if self.is_tool_enabled(tool.name)
        ]

    def get_tool_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the tool registry.

        Returns:
            Dictionary with tool statistics
        """
        total_tools = len(self._tools)
        enabled_tools = sum(1 for name in self._tools.keys() if self.is_tool_enabled(name))
        
        return {
            "total_tools": total_tools,
            "enabled_tools": enabled_tools,
            "disabled_tools": total_tools - enabled_tools,
            "tool_names": list(self._tools.keys())
        }
