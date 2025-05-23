import pytest
from unittest.mock import patch, AsyncMock
from prompt_constructor import (
    build_status_prompt,
    get_formatted_system_prompt,
    build_messages_for_ai,
    build_summary_generation_payload
)
from event_definitions import (
    HistoricalMessage,
    BatchedUserMessage,
    ToolCall,
    ToolRoleMessage,
    ToolFunction
)

# Tests for build_status_prompt
def test_build_status_prompt():
    bot_name = "TestBot"
    prompt_messages = build_status_prompt(bot_name)
    assert len(prompt_messages) == 1
    assert prompt_messages[0]["role"] == "system"
    assert f"You are an AI assistant named {bot_name}." in prompt_messages[0]["content"]
    assert "Generate a short, friendly status message" in prompt_messages[0]["content"]

# Tests for get_formatted_system_prompt
@patch('prompt_constructor.database')
@pytest.mark.asyncio
async def test_get_formatted_system_prompt_all_parts(mock_db):
    mock_db.get_prompt = AsyncMock(return_value=("Test system prompt template with {bot_identity_section}, {global_summary_section}, {user_memories_section}, and {tool_states_section}.", None))
    mock_db.get_latest_global_summary = AsyncMock(return_value=("Test global summary", None))
    mock_db.get_user_memories = AsyncMock(return_value=[
        (1, "user1", "Memory 1 for user1", 1678886400),
        (2, "user1", "Memory 2 for user1", 1678886500),
    ])
    tool_states = {"tool_a": {"state": "active"}, "tool_b": {"count": 5}}
    
    prompt = await get_formatted_system_prompt(
        bot_display_name="TestBot",
        channel_summary="Test channel summary",
        tool_states=tool_states,
        db_path="dummy_db.sqlite",
        current_user_ids_in_context=["user1"]
    )
    assert "Test global summary" in prompt
    assert "Memories for user user1" in prompt
    assert "Memory 1 for user1" in prompt
    assert "Current Tool States for this room:" in prompt
    assert "  - tool_a: {\"state\": \"active\"}" in prompt 
    assert "  - tool_b: {\"count\": 5}" in prompt
    assert "Test channel summary" in prompt # Ensure channel summary is appended

@patch('prompt_constructor.database')
@pytest.mark.asyncio
async def test_get_formatted_system_prompt_no_channel_summary(mock_db):
    mock_db.get_prompt = AsyncMock(return_value=("System prompt: {bot_identity_section}, {global_summary_section}, {user_memories_section}, {tool_states_section}", None))
    mock_db.get_latest_global_summary = AsyncMock(return_value=("Global summary", None))
    mock_db.get_user_memories = AsyncMock(return_value=[])
    prompt = await get_formatted_system_prompt("TestBot", None, None, "dummy_db.sqlite", [])
    assert "TestBot" in prompt
    assert "Global summary" in prompt
    assert "Context for user-specific memories not available." in prompt
    assert "No specific tool states available" in prompt
    assert "Channel Specific Summary:" not in prompt

@patch('prompt_constructor.database')
@pytest.mark.asyncio
async def test_get_formatted_system_prompt_no_global_summary(mock_db):
    mock_db.get_prompt = AsyncMock(return_value=("System prompt: {bot_identity_section}, {global_summary_section}, {user_memories_section}, {tool_states_section}", None))
    mock_db.get_latest_global_summary = AsyncMock(return_value=None)
    mock_db.get_user_memories = AsyncMock(return_value=[])
    prompt = await get_formatted_system_prompt("TestBot", "Channel summary", None, "dummy_db.sqlite", [])
    assert "TestBot" in prompt
    assert "No global summary available currently." in prompt
    assert "Channel Specific Summary:" in prompt 
    assert "Channel summary" in prompt
    # More specific check if needed, ensuring it's at the end after stripping potential trailing whitespace
    assert prompt.strip().endswith("Channel Specific Summary:\nChannel summary")

@patch('prompt_constructor.database')
@pytest.mark.asyncio
async def test_get_formatted_system_prompt_no_summaries_no_bot_name(mock_db):
    mock_db.get_prompt = AsyncMock(return_value=("System prompt: {bot_identity_section}, {global_summary_section}, {user_memories_section}, {tool_states_section}", None))
    mock_db.get_latest_global_summary = AsyncMock(return_value=None)
    mock_db.get_user_memories = AsyncMock(return_value=[])
    prompt = await get_formatted_system_prompt(None, None, None, "dummy_db.sqlite", [])
    assert "You are AI." in prompt # Default identity
    assert "No global summary available currently." in prompt
    assert "Channel Specific Summary:" not in prompt
    assert "Context for user-specific memories not available." in prompt # No user IDs provided

@patch('prompt_constructor.database')
@pytest.mark.asyncio
async def test_get_formatted_system_prompt_only_bot_name(mock_db):
    mock_db.get_prompt = AsyncMock(return_value=("System prompt: {bot_identity_section}, {global_summary_section}, {user_memories_section}, {tool_states_section}", None))
    mock_db.get_latest_global_summary = AsyncMock(return_value=None)
    mock_db.get_user_memories = AsyncMock(return_value=[])
    prompt = await get_formatted_system_prompt("NamedBot", None, None, "dummy_db.sqlite", [])
    assert "You are NamedBot, AI." in prompt
    assert "No global summary available currently." in prompt
    assert "No specific tool states available" in prompt

# Tests for build_messages_for_ai
@patch('prompt_constructor.get_formatted_system_prompt', new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_build_messages_for_ai_empty_inputs(mock_get_formatted_system_prompt):
    mock_get_formatted_system_prompt.return_value = "Mocked System Prompt"
    messages = await build_messages_for_ai([], [], bot_display_name="TestBot", db_path="dummy.db")
    assert len(messages) == 1 # System prompt only
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == "Mocked System Prompt"

@patch('prompt_constructor.get_formatted_system_prompt', new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_build_messages_for_ai_only_historical(mock_get_formatted_system_prompt):
    mock_get_formatted_system_prompt.return_value = "Mocked System Prompt"
    historical = [HistoricalMessage(role="user", content="Hello")]
    messages = await build_messages_for_ai(historical, [], bot_display_name="TestBot", db_path="dummy.db")
    assert len(messages) == 2
    assert messages[1]["content"] == "Hello"

@patch('prompt_constructor.get_formatted_system_prompt', new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_build_messages_for_ai_only_current_single(mock_get_formatted_system_prompt):
    mock_get_formatted_system_prompt.return_value = "Mocked System Prompt"
    current = [{"name": "@user:host", "content": "Hi there", "event_id": "$event1"}]
    messages = await build_messages_for_ai([], current, bot_display_name="TestBot", db_path="dummy.db")
    assert len(messages) == 2
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "Hi there"
    assert messages[1]["name"] == "@user:host"

@patch('prompt_constructor.get_formatted_system_prompt', new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_build_messages_for_ai_only_current_multiple(mock_get_formatted_system_prompt):
    mock_get_formatted_system_prompt.return_value = "Mocked System Prompt"
    current = [
        {"name": "@user1:host", "content": "First", "event_id": "$event1"},
        {"name": "@user2:host", "content": "Second", "event_id": "$event2"}
    ]
    messages = await build_messages_for_ai([], current, bot_display_name="TestBot", db_path="dummy.db")
    assert len(messages) == 2
    assert messages[1]["role"] == "user"
    expected_content = "@user1:host: First\n@user2:host: Second"
    assert messages[1]["content"] == expected_content
    assert messages[1]["name"] == "@user1:host" # name of the first user in batch is used

@patch('prompt_constructor.get_formatted_system_prompt', new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_build_messages_for_ai_inserts_stub_for_orphan_tool(mock_get):
    mock_get.return_value = "System"
    hist = [
        HistoricalMessage(
            role="assistant",
            content=None,
            tool_calls=[ToolCall(id="t1", function=ToolFunction(name="foo", arguments="{}"))]
        ),
        ToolRoleMessage(tool_call_id="t1", content="ok"),
        ToolRoleMessage(tool_call_id="t2", content="late")
    ]
    msgs = await build_messages_for_ai(hist, [], bot_display_name="Bot", db_path="db")
    stub_idx = next(i for i,m in enumerate(msgs) if m.get("tool_calls") and m["tool_calls"][0]["id"]=="t2")
    assert msgs[stub_idx]["role"] == "assistant"
    assert msgs[stub_idx+1]["role"] == "tool"
    assert msgs[stub_idx+1]["tool_call_id"] == "t2"
