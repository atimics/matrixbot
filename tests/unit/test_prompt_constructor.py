\
import pytest
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
    ToolRoleMessage
)

# Tests for build_status_prompt
def test_build_status_prompt():
    prompt = build_status_prompt()
    assert "Current Status:" in prompt
    assert "Overall Summary:" in prompt
    assert "Active Rooms:" in prompt

# Tests for get_formatted_system_prompt
def test_get_formatted_system_prompt_all_parts():
    prompt = get_formatted_system_prompt(
        "TestBot", "This is a channel summary.", "This is a global summary."
    )
    assert "You are TestBot, a helpful AI assistant." in prompt
    assert "CHANNEL_SUMMARY:\nThis is a channel summary." in prompt
    assert "GLOBAL_SUMMARY:\nThis is a global summary." in prompt

def test_get_formatted_system_prompt_no_channel_summary():
    prompt = get_formatted_system_prompt(
        "TestBot", None, "This is a global summary."
    )
    assert "You are TestBot, a helpful AI assistant." in prompt
    assert "CHANNEL_SUMMARY:" not in prompt
    assert "GLOBAL_SUMMARY:\nThis is a global summary." in prompt

def test_get_formatted_system_prompt_no_global_summary():
    prompt = get_formatted_system_prompt(
        "TestBot", "This is a channel summary.", None
    )
    assert "You are TestBot, a helpful AI assistant." in prompt
    assert "CHANNEL_SUMMARY:\nThis is a channel summary." in prompt
    assert "GLOBAL_SUMMARY:" not in prompt

def test_get_formatted_system_prompt_no_summaries_no_bot_name():
    prompt = get_formatted_system_prompt(None, None, None)
    assert "You are a helpful AI assistant." in prompt
    assert "CHANNEL_SUMMARY:" not in prompt
    assert "GLOBAL_SUMMARY:" not in prompt

def test_get_formatted_system_prompt_only_bot_name():
    prompt = get_formatted_system_prompt("TestBot", None, None)
    assert "You are TestBot, a helpful AI assistant." in prompt
    assert "CHANNEL_SUMMARY:" not in prompt
    assert "GLOBAL_SUMMARY:" not in prompt

# Tests for build_messages_for_ai
def test_build_messages_for_ai_empty_inputs():
    messages = build_messages_for_ai([], [])
    assert messages == []

def test_build_messages_for_ai_only_historical():
    historical = [HistoricalMessage(role="user", content="Hello")]
    messages = build_messages_for_ai(historical, [])
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Hello"

def test_build_messages_for_ai_only_current_single():
    current = [BatchedUserMessage(user_id="@user:host", content="Hi there", event_id="$event1")]
    messages = build_messages_for_ai([], current)
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Hi there"

def test_build_messages_for_ai_only_current_multiple():
    current = [
        BatchedUserMessage(user_id="@user1:host", content="First", event_id="$event1"),
        BatchedUserMessage(user_id="@user2:host", content="Second", event_id="$event2")
    ]
    messages = build_messages_for_ai([], current)
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "@user1:host said: First\n@user2:host said: Second"

def test_build_messages_for_ai_combination():
    historical = [HistoricalMessage(role="user", content="Past message")]
    current = [BatchedUserMessage(user_id="@user:host", content="Current message", event_id="$event1")]
    messages = build_messages_for_ai(historical, current)
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Past message"
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "Current message"

def test_build_messages_for_ai_with_summaries_and_event_id():
    historical = [HistoricalMessage(role="assistant", content="Previous assistant message")]
    current = [BatchedUserMessage(user_id="@user:host", content="User asks something", event_id="$currEvent")]
    channel_summary = "Channel is active."
    global_summary = "Bot is running."
    last_user_event_id = "$lastUserEvent"

    messages = build_messages_for_ai(
        historical_messages=historical,
        current_batched_user_inputs=current,
        channel_summary=channel_summary,
        global_summary=global_summary,
        last_user_event_id_for_context=last_user_event_id
    )
    # Expected: system prompt, historical, current
    assert len(messages) == 3
    assert messages[0]["role"] == "system"
    assert "CHANNEL_SUMMARY:\nChannel is active." in messages[0]["content"]
    assert "GLOBAL_SUMMARY:\nBot is running." in messages[0]["content"]
    assert f"The user's last message event_id was {last_user_event_id}" in messages[0]["content"]
    assert messages[1]["role"] == "assistant"
    assert messages[2]["role"] == "user"

def test_build_messages_for_ai_assistant_message_tool_calls_no_content():
    historical = [
        HistoricalMessage(
            role="assistant",
            content=None, # No text content
            tool_calls=[ToolCall(id="call1", function_name="send_reply", function_args='{"text":"Hi"}')]
        )
    ]
    messages = build_messages_for_ai(historical, [])
    assert len(messages) == 1
    assert messages[0]["role"] == "assistant"
    assert messages[0]["content"] is None
    assert len(messages[0]["tool_calls"]) == 1
    assert messages[0]["tool_calls"][0]["id"] == "call1"
    assert messages[0]["tool_calls"][0]["type"] == "function"
    assert messages[0]["tool_calls"][0]["function"]["name"] == "send_reply"
    assert messages[0]["tool_calls"][0]["function"]["arguments"] == '{"text":"Hi"}'


def test_build_messages_for_ai_tool_role_message():
    historical = [
        ToolRoleMessage(
            tool_call_id="call1",
            content="Tool execution result text"
        )
    ]
    messages = build_messages_for_ai(historical, [])
    assert len(messages) == 1
    assert messages[0]["role"] == "tool"
    assert messages[0]["tool_call_id"] == "call1"
    assert messages[0]["content"] == "Tool execution result text"

# Tests for build_summary_generation_payload
def test_build_summary_generation_payload_no_previous_summary():
    transcript = "User: Hello\nBot: Hi there"
    payload = build_summary_generation_payload(transcript, None)
    assert len(payload) == 2 # System prompt + user message with transcript
    assert payload[0]["role"] == "system"
    assert "CONSOLIDATED_SUMMARY_SO_FAR: None" in payload[0]["content"]
    assert payload[1]["role"] == "user"
    assert transcript in payload[1]["content"]

def test_build_summary_generation_payload_with_previous_summary():
    transcript = "User: How are you?\nBot: I am fine."
    previous_summary = "Initial conversation started."
    payload = build_summary_generation_payload(transcript, previous_summary)
    assert len(payload) == 2
    assert payload[0]["role"] == "system"
    assert f"CONSOLIDATED_SUMMARY_SO_FAR:\n{previous_summary}" in payload[0]["content"]
    assert payload[1]["role"] == "user"
    assert transcript in payload[1]["content"]

def test_build_summary_generation_payload_empty_transcript():
    transcript = ""
    previous_summary = "Summary exists."
    payload = build_summary_generation_payload(transcript, previous_summary)
    assert len(payload) == 2
    assert payload[0]["role"] == "system"
    assert f"CONSOLIDATED_SUMMARY_SO_FAR:\n{Summary exists.}" in payload[0]["content"]
    assert payload[1]["role"] == "user"
    assert "The transcript is empty or contains no meaningful conversation." in payload[1]["content"]

