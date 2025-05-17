import os
import importlib.util
import inspect
import logging
from typing import Dict, Any, List, Optional, Type

from tool_base import AbstractTool

logger = logging.getLogger(__name__)

class ToolLoader:
    """Loads tools from a specified directory."""

    def __init__(self, tools_directory: str = "available_tools"):
        self.tools_directory = tools_directory
        if not os.path.exists(self.tools_directory):
            os.makedirs(self.tools_directory)
            logger.info(f"Created tools directory: {self.tools_directory}")

    def load_tools(self) -> List[AbstractTool]:
        """Scans the tools directory, imports modules, and instantiates tool classes."""
        loaded_tools: List[AbstractTool] = []
        if not os.path.isdir(self.tools_directory):
            logger.warning(f"Tools directory '{self.tools_directory}' not found or is not a directory.")
            return loaded_tools

        for filename in os.listdir(self.tools_directory):
            if filename.endswith(".py") and not filename.startswith("__"):
                module_name = filename[:-3]
                file_path = os.path.join(self.tools_directory, filename)
                try:
                    spec = importlib.util.spec_from_file_location(module_name, file_path)
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        for name, obj in inspect.getmembers(module, inspect.isclass):
                            if issubclass(obj, AbstractTool) and obj is not AbstractTool:
                                try:
                                    tool_instance = obj() # Assumes tools have a no-arg constructor
                                    loaded_tools.append(tool_instance)
                                    logger.info(f"Successfully loaded tool: {name} from {filename}")
                                except Exception as e:
                                    logger.error(f"Error instantiating tool {name} from {filename}: {e}")
                    else:
                        logger.warning(f"Could not create spec for module {module_name} at {file_path}")
                except Exception as e:
                    logger.error(f"Error loading module {module_name} from {file_path}: {e}")
        return loaded_tools

class ToolRegistry:
    """Holds instances of loaded tools and provides access to them."""

    def __init__(self, tools: List[AbstractTool]):
        self._tools: Dict[str, AbstractTool] = {}
        for tool in tools:
            definition = tool.get_definition()
            tool_name = definition.get("function", {}).get("name")
            if tool_name:
                if tool_name in self._tools:
                    logger.warning(f"Duplicate tool name '{tool_name}' found. Overwriting.")
                self._tools[tool_name] = tool
            else:
                logger.warning(f"Tool {tool.__class__.__name__} has no name in its definition. Skipping.")

    def get_all_tool_definitions(self) -> List[Dict[str, Any]]:
        """Returns the LLM schema definitions for all registered tools."""
        return [tool.get_definition() for tool in self._tools.values()]

    def get_tool(self, name: str) -> Optional[AbstractTool]:
        """Retrieves a tool instance by its name."""
        return self._tools.get(name)
