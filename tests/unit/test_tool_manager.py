import pytest
import os
import sys
import tempfile
import shutil
import logging
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
            "function": {
                "name": self._name,
                "description": self._description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "arg1": {
                            "type": "string",
                            "description": "Arg one"
                        }
                    },
                    "required": []
                }
            }
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

@patch('tool_manager.os.path.exists', return_value=False)
@patch('tool_manager.os.makedirs')
def test_tool_loader_no_dir(mock_makedirs, mock_exists, caplog):
    # Test that the directory is created if it doesn't exist
    # Set the logging level for the logger used in ToolLoader to INFO for this test
    with caplog.at_level(logging.INFO, logger='tool_manager'):
        loader = ToolLoader(tools_directory="/path/to/non_existent_tools_dir")
        mock_exists.assert_called_once_with("/path/to/non_existent_tools_dir")
        mock_makedirs.assert_called_once_with("/path/to/non_existent_tools_dir")
        assert "Created tools directory: /path/to/non_existent_tools_dir" in caplog.text

    # Test loading when directory is still considered non-existent by listdir (mocked)
    # Ensure os.listdir raises FileNotFoundError when the directory doesn't exist after creation attempt (if makedirs failed silently or was mocked too simply)
    with patch('tool_manager.os.listdir', side_effect=FileNotFoundError("[Errno 2] No such file or directory: '/path/to/non_existent_tools_dir'")):
        # Also, ensure that os.path.isdir correctly reports the directory as non-existent.
        with patch('tool_manager.os.path.isdir', return_value=False):
            tools = loader.load_tools()
            assert not tools
            assert "Tools directory '/path/to/non_existent_tools_dir' not found or is not a directory." in caplog.text

@patch('tool_manager.logger') # Mock logger to check for error messages
def test_tool_loader_import_error(mock_logger, mock_tool_dir):
    loader = ToolLoader(tools_directory=mock_tool_dir)
    tools = loader.load_tools() # Should load MyValidTool, skip import_error_tool
    assert len(tools) == 1
    assert tools[0].get_definition()["name"] == "my_valid_tool"
    # Check if logger.error was called for the import error tool
    assert any("Error importing tool module" in call.args[0] and "import_error_tool.py" in call.args[0] for call in mock_logger.error.call_args_list)

@patch('tool_manager.importlib.util.spec_from_file_location')
def test_tool_loader_import_error_with_spec_mock(mock_spec_from_file_location, caplog, temp_tools_dir):
    # Create a dummy tool file that will cause an ImportError
    tool_file_path = temp_tools_dir / "error_tool.py"
    tool_file_path.write_text("import non_existent_module\n\nclass ErrorTool(AbstractTool): pass")

    # Mock spec_from_file_location to return a spec, but exec_module will fail
    mock_spec = MagicMock()
    mock_spec.loader.exec_module.side_effect = ImportError("Mocked import error")
    mock_spec_from_file_location.return_value = mock_spec
    
    loader = ToolLoader(tools_directory=str(temp_tools_dir))
    tools = loader.load_tools()
    
    assert not tools # No tools should be loaded
    assert "Error importing tool module error_tool" in caplog.text # Made assertion more general

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

@patch('tool_manager.importlib.util.spec_from_file_location')
def test_tool_loader_syntax_error_tool(mock_spec_from_file_location, caplog, temp_tools_dir):
    # Create a dummy tool file with a syntax error
    tool_file_path = temp_tools_dir / "syntax_error_tool.py"
    tool_file_path.write_text("class SyntaxErrorTool(AbstractTool):\n  pass\n  some_invalid_syntax = ")

    # Mock spec_from_file_location to return a spec, but exec_module will fail due to syntax error
    # The actual SyntaxError happens during exec_module
    mock_spec = MagicMock()
    mock_spec.loader.exec_module.side_effect = SyntaxError("Mocked syntax error")
    mock_spec_from_file_location.return_value = mock_spec

    loader = ToolLoader(tools_directory=str(temp_tools_dir))
    tools = loader.load_tools()

    assert not tools
    assert "Error loading module syntax_error_tool" in caplog.text
    assert "Mocked syntax error" in caplog.text

# --- ToolRegistry Tests ---

def test_tool_registry_register_and_get_definitions(sample_tool_list):
    registry = ToolRegistry(tools=sample_tool_list) # Pass tools via constructor
    definitions = registry.get_all_tool_definitions()
    assert len(definitions) == 2
    # Add assertions to check the content of the definitions if necessary
    assert definitions[0]["function"]["name"] == "SampleToolOne"
    assert definitions[1]["function"]["name"] == "SampleToolTwo"

def test_tool_registry_get_tool_exists(sample_tool_list):
    registry = ToolRegistry(tools=sample_tool_list) # Pass tools via constructor
    tool = registry.get_tool("SampleToolOne")
    assert tool is not None
    assert tool.get_definition()["function"]["name"] == "SampleToolOne"

def test_tool_registry_get_tool_not_exists(sample_tool_list):
    registry = ToolRegistry(tools=sample_tool_list) # Pass tools via constructor
    tool = registry.get_tool("NonExistentTool")
    assert tool is None

@patch('tool_manager.logger')
def test_tool_registry_duplicate_tool_name_warning(mock_logger):
    # The ToolRegistry now overwrites tools with duplicate names and logs a warning.
    tool1 = MockTool(name="duplicate_name")
    tool2 = MockTool(name="duplicate_name", description="A different mock tool")
    registry = ToolRegistry(tools=[tool1, tool2]) # Initialize with both tools

    # The second tool (tool2) should overwrite the first one (tool1).
    assert registry.get_tool("duplicate_name") is tool2
    mock_logger.warning.assert_called_once()
    assert "Duplicate tool name 'duplicate_name' found. Overwriting." in mock_logger.warning.call_args[0][0]

    # Check definitions - should only contain one tool with that name, the last one registered.
    definitions = registry.get_all_tool_definitions()
    assert len(definitions) == 1
    assert definitions[0]["function"]["name"] == "duplicate_name"
    assert definitions[0]["function"]["description"] == "A different mock tool"

# A fixture to provide a list of sample tools for registry tests
@pytest.fixture
def sample_tool_list():
    return [
        MockTool(name="SampleToolOne", description="First sample tool"),
        MockTool(name="SampleToolTwo", description="Second sample tool")
    ]

# Fixture for a temporary directory to store mock tool files
@pytest.fixture
def temp_tools_dir(tmp_path):
    dir_path = tmp_path / "temp_tools"
    dir_path.mkdir()
    return dir_path

