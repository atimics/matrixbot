
import pytest
import os
import sys
import tempfile
import shutil
from unittest.mock import MagicMock, patch

from tool_manager import ToolLoader, ToolRegistry
from tool_base import AbstractTool, ToolResult, ToolParameter

# --- Fixtures and Mocks ---

@pytest.fixture
def mock_tool_dir(tmp_path):
    """Creates a temporary directory structure for mock tools."""
    tools_dir = tmp_path / "mock_tools"
    tools_dir.mkdir()

    # Valid tool
    with open(tools_dir / "valid_tool.py", "w") as f:
        f.write("""
from tool_base import AbstractTool, ToolResult, ToolParameter

class MyValidTool(AbstractTool):
    def get_definition(self):
        return {
            "name": "my_valid_tool",
            "description": "A valid tool.",
            "parameters": [
                ToolParameter(name="param1", type="string", description="A param", required=True)
            ]
        }
    async def execute(self, room_id, arguments, tool_call_id, llm_provider_info, conversation_history_snapshot, last_user_event_id):
        return ToolResult(status="success", commands_to_publish=[])
""")

    # Tool with import error
    with open(tools_dir / "import_error_tool.py", "w") as f:
        f.write("import non_existent_module\n")

    # Tool with instantiation error
    with open(tools_dir / "init_error_tool.py", "w") as f:
        f.write("""
from tool_base import AbstractTool

class InitErrorTool(AbstractTool):
    def __init__(self):
        raise ValueError(\"Init failed\")
    def get_definition(self):
        return {"name": "init_error_tool", "description": "..."}
    async def execute(self, **kwargs):
        pass
""")

    # File that is not a tool (doesn't inherit AbstractTool)
    with open(tools_dir / "not_a_tool.py", "w") as f:
        f.write("""
class NotATool:
    pass
""")

    # File with Python syntax error
    with open(tools_dir / "syntax_error_tool.py", "w") as f:
        f.write("def some_func(;\n") # Syntax error

    return str(tools_dir)

class MockTool(AbstractTool):
    def __init__(self, name="mock_tool", description="A mock tool"):
        self._name = name
        self._description = description

    def get_definition(self):
        return {
            "name": self._name,
            "description": self._description,
            "parameters": [
                ToolParameter(name="arg1", type="string", description="Arg one", required=False)
            ]
        }

    async def execute(self, room_id, arguments, tool_call_id, llm_provider_info, conversation_history_snapshot, last_user_event_id):
        return ToolResult(status="success")

# --- ToolLoader Tests ---

def test_tool_loader_load_tools_valid(mock_tool_dir):
    loader = ToolLoader(tools_directory=mock_tool_dir)
    tools = loader.load_tools()
    assert len(tools) == 1
    assert tools[0].get_definition()["name"] == "my_valid_tool"

def test_tool_loader_empty_dir(tmp_path):
    empty_dir = tmp_path / "empty_tools"
    empty_dir.mkdir()
    loader = ToolLoader(tools_directory=str(empty_dir))
    tools = loader.load_tools()
    assert len(tools) == 0

def test_tool_loader_no_dir():
    loader = ToolLoader(tools_directory="/path/to/non_existent_dir")
    tools = loader.load_tools()
    assert len(tools) == 0

@patch('tool_manager.logger') # Mock logger to check for error messages
def test_tool_loader_import_error(mock_logger, mock_tool_dir):
    loader = ToolLoader(tools_directory=mock_tool_dir)
    tools = loader.load_tools() # Should load MyValidTool, skip import_error_tool
    assert len(tools) == 1
    assert tools[0].get_definition()["name"] == "my_valid_tool"
    # Check if logger.error was called for the import error tool
    assert any("Error importing tool module" in call.args[0] and "import_error_tool.py" in call.args[0] for call in mock_logger.error.call_args_list)

@patch('tool_manager.logger')
def test_tool_loader_instantiation_error(mock_logger, mock_tool_dir):
    loader = ToolLoader(tools_directory=mock_tool_dir)
    tools = loader.load_tools()
    assert len(tools) == 1 # MyValidTool
    assert tools[0].get_definition()["name"] == "my_valid_tool"
    assert any("Error instantiating tool" in call.args[0] and "InitErrorTool" in call.args[0] for call in mock_logger.error.call_args_list)

@patch('tool_manager.logger')
def test_tool_loader_not_subclass(mock_logger, mock_tool_dir):
    loader = ToolLoader(tools_directory=mock_tool_dir)
    tools = loader.load_tools()
    assert len(tools) == 1 # MyValidTool
    assert tools[0].get_definition()["name"] == "my_valid_tool"
    # NotATool should be silently ignored, no specific error log for this case in the plan

@patch('tool_manager.logger')
def test_tool_loader_syntax_error_tool(mock_logger, mock_tool_dir):
    loader = ToolLoader(tools_directory=mock_tool_dir)
    tools = loader.load_tools()
    assert len(tools) == 1 # MyValidTool
    assert tools[0].get_definition()["name"] == "my_valid_tool"
    assert any("Error importing tool module" in call.args[0] and "syntax_error_tool.py" in call.args[0] for call in mock_logger.error.call_args_list)


# --- ToolRegistry Tests ---

def test_tool_registry_register_and_get_definitions():
    registry = ToolRegistry()
    tool1 = MockTool(name="tool1")
    tool2 = MockTool(name="tool2")
    registry.register_tool(tool1)
    registry.register_tool(tool2)

    definitions = registry.get_tool_definitions()
    assert len(definitions) == 2
    assert definitions[0]["name"] == "tool1"
    assert definitions[1]["name"] == "tool2"

def test_tool_registry_get_tool_exists():
    registry = ToolRegistry()
    tool = MockTool(name="find_me")
    registry.register_tool(tool)
    retrieved_tool = registry.get_tool("find_me")
    assert retrieved_tool is tool

def test_tool_registry_get_tool_not_exists():
    registry = ToolRegistry()
    retrieved_tool = registry.get_tool("non_existent_tool")
    assert retrieved_tool is None

@patch('tool_manager.logger')
def test_tool_registry_duplicate_tool_name_warning(mock_logger):
    registry = ToolRegistry()
    tool1 = MockTool(name="duplicate_name")
    tool2 = MockTool(name="duplicate_name") # Same name
    registry.register_tool(tool1)
    registry.register_tool(tool2) # Attempt to register another with the same name

    # The second tool should not overwrite the first one if names are unique identifiers.
    # The plan asks for a warning. Let's assume the first one registered wins.
    assert registry.get_tool("duplicate_name") is tool1
    mock_logger.warning.assert_called_once()
    assert "Tool with name 'duplicate_name' already exists in registry." in mock_logger.warning.call_args[0][0]

    # Check definitions - should only contain one tool with that name
    definitions = registry.get_tool_definitions()
    names = [d["name"] for d in definitions]
    assert names.count("duplicate_name") == 1

