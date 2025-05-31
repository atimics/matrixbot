"""
Tool registry for dynamic tool management and AI prompt generation.
"""
import json
import logging
from typing import Dict, List, Optional

from .base import ToolInterface

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    Registry for managing available tools and generating AI prompts.
    """

    def __init__(self):
        self._tools: Dict[str, ToolInterface] = {}

    def register_tool(self, tool: ToolInterface) -> None:
        """
        Register a tool in the registry.

        Args:
            tool: Tool instance implementing ToolInterface
        """
        if tool.name in self._tools:
            logger.warning(f"Tool '{tool.name}' is already registered. Overwriting.")

        self._tools[tool.name] = tool
        logger.info(f"Tool '{tool.name}' registered successfully.")

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
        Generate a formatted string describing all tools for AI prompts.

        Returns:
            Formatted string with tool descriptions and parameters
        """
        if not self._tools:
            return "No tools currently available."

        descriptions = []
        for tool in self._tools.values():
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
