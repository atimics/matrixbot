"""Tests for orphaned tool calls that cause API errors with Claude/Anthropic."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import asyncio
from datetime import datetime

from room_logic_service import RoomLogicService
from tool_manager import ToolRegistry
from message_bus import MessageBus
from event_definitions import (
    AIInferenceResponseEvent, ToolExecutionResponse, ToolCall, ToolFunction,
    OpenRouterInferenceResponseEvent, ExecuteToolRequest, HistoricalMessage
)
import prompt_constructor
from prompt_constructor import build_messages_for_ai
import database


@pytest.mark.asyncio
class TestOrphanedToolCalls:
    """Test cases for orphaned tool calls that cause API errors."""

    @pytest.fixture
    async def test_db_path(self, tmp_path):
        """Set up test database."""
        db_path = str(tmp_path / "test_orphan.db")
        await database.initialize_database(db_path)
        
        # Set up default prompts
        await database.update_prompt(db_path, "system_default", 
            "You are a test bot. Always use tools to respond.")
        
        return db_path

    @pytest.fixture
    def message_bus(self):
        """Set up message bus."""
        return MessageBus()

    @pytest.fixture
    def tool_registry(self):
        """Set up tool registry."""
        return ToolRegistry([])  # Empty for this test

    @pytest.fixture
    def room_logic_service(self, message_bus, tool_registry, test_db_path):
        """Set up room logic service."""
        return RoomLogicService(
            message_bus=message_bus,
            tool_registry=tool_registry,
            db_path=test_db_path,
            bot_display_name="TestBot"
        )

    async def test_orphaned_tool_result_without_tool_use(self, test_db_path):
        """Test case: tool_result exists without corresponding tool_use in conversation history."""
        # Create a conversation history with an orphaned tool result
        # This simulates the case where a tool_result exists but its corresponding
        # tool_use (assistant message with tool_calls) is missing or malformed
        historical_messages = [
            HistoricalMessage(
                role="user",
                content="Hello, can you help me?",
                name="TestUser"
            ),
            # Missing assistant message with tool_calls here - this creates the orphan
            HistoricalMessage(
                role="tool",
                tool_call_id="toolu_016BgCk6Z7kSbX2LePAbSxpt",  # Same ID from error log
                content="Tool execution completed successfully"
            ),
            HistoricalMessage(
                role="user", 
                content="What was the result?",
                name="TestUser"
            )
        ]
        
        # Build messages for AI - this should detect and fix the orphaned tool result
        messages = await build_messages_for_ai(
            historical_messages=historical_messages,
            current_batched_user_inputs=[],
            bot_display_name="TestBot",
            db_path=test_db_path
        )
        
        # Verify that a stub tool_use was inserted before the orphaned tool result
        tool_result_index = None
        stub_assistant_index = None
        
        for i, msg in enumerate(messages):
            if msg.get("role") == "tool" and msg.get("tool_call_id") == "toolu_016BgCk6Z7kSbX2LePAbSxpt":
                tool_result_index = i
            elif (msg.get("role") == "assistant" and 
                  msg.get("tool_calls") and 
                  any(tc.get("id") == "toolu_016BgCk6Z7kSbX2LePAbSxpt" for tc in msg.get("tool_calls", []))):
                stub_assistant_index = i
        
        # Assert that both exist and the assistant message comes before the tool result
        assert stub_assistant_index is not None, "Stub assistant message with tool_calls should be inserted"
        assert tool_result_index is not None, "Tool result message should exist"
        assert stub_assistant_index < tool_result_index, "Stub assistant message should come before tool result"
        
        # Verify the stub has the correct structure
        stub_message = messages[stub_assistant_index]
        assert stub_message["role"] == "assistant"
        assert stub_message["content"] is None  # Should be None when tool_calls are present
        assert len(stub_message["tool_calls"]) == 1
        assert stub_message["tool_calls"][0]["id"] == "toolu_016BgCk6Z7kSbX2LePAbSxpt"
        assert stub_message["tool_calls"][0]["function"]["name"] == "unknown_tool"

    async def test_multiple_orphaned_tool_results(self, test_db_path):
        """Test case: multiple orphaned tool results in conversation history."""
        historical_messages = [
            HistoricalMessage(
                role="user",
                content="Start conversation",
                name="TestUser"
            ),
            # Multiple orphaned tool results
            HistoricalMessage(
                role="tool",
                tool_call_id="orphan_1",
                content="First orphaned result"
            ),
            HistoricalMessage(
                role="tool", 
                tool_call_id="orphan_2",
                content="Second orphaned result"
            ),
            HistoricalMessage(
                role="user",
                content="What happened?",
                name="TestUser"
            )
        ]
        
        messages = await build_messages_for_ai(
            historical_messages=historical_messages,
            current_batched_user_inputs=[],
            bot_display_name="TestBot",
            db_path=test_db_path
        )
        
        # Should have stubs for both orphaned tool results
        orphan_1_stub = None
        orphan_2_stub = None
        
        for msg in messages:
            if (msg.get("role") == "assistant" and msg.get("tool_calls")):
                for tc in msg.get("tool_calls", []):
                    if tc.get("id") == "orphan_1":
                        orphan_1_stub = msg
                    elif tc.get("id") == "orphan_2":
                        orphan_2_stub = msg
        
        assert orphan_1_stub is not None, "Stub for orphan_1 should be created"
        assert orphan_2_stub is not None, "Stub for orphan_2 should be created"

    async def test_tool_execution_response_creates_orphan(self, message_bus, tool_registry, test_db_path):
        """Test case: ToolExecutionResponse creates orphaned tool result in conversation flow."""
        rls = RoomLogicService(
            message_bus=message_bus,
            tool_registry=tool_registry,
            db_path=test_db_path,
            bot_display_name="TestBot"
        )
        
        # Set up room config
        room_id = "!test:matrix.org"
        rls.room_activity_config[room_id] = {
            'memory': [],
            'is_active_listening': True,
            'tool_states': {},
            'pending_tool_calls': {}
        }
        
        # Simulate a turn where tools were called but the assistant message gets corrupted/lost
        turn_request_id = "test_turn_123"
        
        # Set up pending tool call info without the assistant message
        # Use a tool that's NOT in SIMPLE_OUTPUT_TOOLS to ensure follow-up AI call
        rls.pending_tool_calls_for_ai_turn[turn_request_id] = {
            "room_id": room_id,
            "conversation_history_at_tool_call_time": [
                {"role": "user", "content": "Test message", "name": "TestUser"}
            ],
            "assistant_message_with_tool_calls": {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "test_tool_call_1",
                        "type": "function", 
                        "function": {"name": "get_room_info", "arguments": '{"info_type": "name"}'}
                    }
                ]
            },
            "expected_tool_call_ids": ["test_tool_call_1"],
            "received_tool_responses": [],
            "original_ai_response_payload": {
                "room_id": room_id,
                "turn_request_id": turn_request_id,
                "current_llm_provider": "openrouter"
            },
            "skip_follow_up_if_simple_output": False
        }
        
        # Create a tool execution response
        tool_response = ToolExecutionResponse(
            original_tool_call_id="test_tool_call_1",
            tool_name="get_room_info",
            status="success",
            result_for_llm_history="Room info retrieved successfully",
            original_request_payload={
                "room_id": room_id,
                "turn_request_id": turn_request_id
            }
        )
        
        # Mock the follow-up AI call to capture the payload
        with patch.object(message_bus, "publish") as mock_publish:
            await rls._handle_tool_execution_response(tool_response)
            
            # Verify that a follow-up AI request was published
            mock_publish.assert_called()
            
            # Find the AI request call
            ai_request_call = None
            for call in mock_publish.call_args_list:
                if hasattr(call[0][0], 'messages_payload'):
                    ai_request_call = call[0][0]
                    break
            
            assert ai_request_call is not None, "Follow-up AI request should be published"
            
            # Check that the messages payload has proper tool_use -> tool_result structure
            messages = ai_request_call.messages_payload
            
            # Find assistant and tool messages
            assistant_msg = None
            tool_msg = None
            
            for msg in messages:
                if msg.get("role") == "assistant" and msg.get("tool_calls"):
                    for tc in msg.get("tool_calls", []):
                        if tc.get("id") == "test_tool_call_1":
                            assistant_msg = msg
                            break
                elif (msg.get("role") == "tool" and 
                      msg.get("tool_call_id") == "test_tool_call_1"):
                    tool_msg = msg
            
            assert assistant_msg is not None, "Assistant message with tool_calls should exist"
            assert tool_msg is not None, "Tool result message should exist"
            
            # Verify proper ordering
            assistant_index = messages.index(assistant_msg)
            tool_index = messages.index(tool_msg)
            assert assistant_index < tool_index, "Assistant message should come before tool result"

    async def test_pending_tool_call_cleanup_prevents_orphans(self, test_db_path):
        """Test that proper cleanup of pending tool calls prevents orphaned results."""
        # Test the pending_tool_call_ids tracking in build_messages_for_ai
        historical_messages = [
            HistoricalMessage(
                role="user",
                content="Test request",
                name="TestUser"
            ),
            HistoricalMessage(
                role="assistant",
                content=None,
                tool_calls=[
                    ToolCall(
                        id="pending_call_1",
                        function=ToolFunction(name="test_tool", arguments="{}")
                    )
                ]
            ),
            # No tool result yet - this should be handled by pending tracking
            HistoricalMessage(
                role="user",
                content="Another message",
                name="TestUser"
            )
        ]
        
        messages = await build_messages_for_ai(
            historical_messages=historical_messages,
            current_batched_user_inputs=[],
            bot_display_name="TestBot",
            db_path=test_db_path
        )
        
        # Should inject a stub tool response for the pending call
        stub_tool_response = None
        for msg in messages:
            if (msg.get("role") == "tool" and 
                msg.get("tool_call_id") == "pending_call_1" and
                "pending" in msg.get("content", "").lower()):
                stub_tool_response = msg
                break
        
        assert stub_tool_response is not None, "Stub tool response should be injected for pending tool call"
        assert "pending" in stub_tool_response["content"].lower(), "Stub should indicate pending status"

    async def test_anthropic_api_error_reproduction(self, test_db_path):
        """Reproduce the exact error scenario from the logs."""
        # Create the exact scenario that causes the Anthropic API error
        # Based on error: "messages.0.content.0: unexpected `tool_use_id` found in `tool_result` blocks"
        
        # This creates a malformed conversation where the first message is a tool_result
        # without a preceding tool_use, which violates Anthropic's API requirements
        historical_messages = [
            # System prompt will be added by build_messages_for_ai
            # This tool result has no preceding tool_use - this should be caught and fixed
            HistoricalMessage(
                role="tool",
                tool_call_id="toolu_016BgCk6Z7kSbX2LePAbSxpt",  # Exact ID from error log
                content="Some tool result"
            )
        ]
        
        messages = await build_messages_for_ai(
            historical_messages=historical_messages,
            current_batched_user_inputs=[{"name": "User", "content": "Test message"}],
            bot_display_name="TestBot",
            db_path=test_db_path
        )
        
        # Verify the structure is valid for Anthropic API
        system_msg_count = sum(1 for msg in messages if msg.get("role") == "system")
        user_msg_count = sum(1 for msg in messages if msg.get("role") == "user")
        assistant_msg_count = sum(1 for msg in messages if msg.get("role") == "assistant")
        tool_msg_count = sum(1 for msg in messages if msg.get("role") == "tool")
        
        assert system_msg_count >= 1, "Should have system message"
        assert user_msg_count >= 1, "Should have user message"
        
        # If there are tool messages, there should be corresponding assistant messages with tool_calls
        if tool_msg_count > 0:
            assert assistant_msg_count > 0, "Tool messages require preceding assistant messages with tool_calls"
            
            # Verify each tool message has a corresponding tool_call in an assistant message
            tool_call_ids_in_assistant_msgs = set()
            tool_call_ids_in_tool_msgs = set()
            
            for msg in messages:
                if msg.get("role") == "assistant" and msg.get("tool_calls"):
                    for tc in msg.get("tool_calls", []):
                        tool_call_ids_in_assistant_msgs.add(tc.get("id"))
                elif msg.get("role") == "tool":
                    tool_call_ids_in_tool_msgs.add(msg.get("tool_call_id"))
            
            # Every tool_call_id in tool messages should have a corresponding entry in assistant messages
            orphaned_ids = tool_call_ids_in_tool_msgs - tool_call_ids_in_assistant_msgs
            assert len(orphaned_ids) == 0, f"Found orphaned tool_call_ids: {orphaned_ids}"

    async def test_conversation_order_validation(self, test_db_path):
        """Validate that conversation follows proper tool_use -> tool_result ordering."""
        # Test various edge cases that could lead to ordering issues
        test_cases = [
            {
                "name": "tool_result_before_tool_use",
                "messages": [
                    HistoricalMessage(role="user", content="Test", name="User"),
                    HistoricalMessage(role="tool", tool_call_id="test_1", content="Result"),
                    HistoricalMessage(role="assistant", content=None, 
                                    tool_calls=[ToolCall(id="test_1", function=ToolFunction(name="test", arguments="{}"))]),
                ]
            },
            {
                "name": "multiple_tool_results_mixed_order",
                "messages": [
                    HistoricalMessage(role="user", content="Test", name="User"),
                    HistoricalMessage(role="tool", tool_call_id="test_1", content="Result 1"),
                    HistoricalMessage(role="assistant", content=None,
                                    tool_calls=[ToolCall(id="test_2", function=ToolFunction(name="test", arguments="{}"))]),
                    HistoricalMessage(role="tool", tool_call_id="test_2", content="Result 2"),
                ]
            }
        ]
        
        for test_case in test_cases:
            messages = await build_messages_for_ai(
                historical_messages=test_case["messages"],
                current_batched_user_inputs=[],
                bot_display_name="TestBot", 
                db_path=test_db_path
            )
            
            # Validate ordering: every tool message should be preceded by an assistant message
            # with a tool_call that has the same ID
            for i, msg in enumerate(messages):
                if msg.get("role") == "tool":
                    tool_call_id = msg.get("tool_call_id")
                    
                    # Look backward to find the corresponding assistant message
                    found_assistant = False
                    for j in range(i-1, -1, -1):
                        prev_msg = messages[j]
                        if (prev_msg.get("role") == "assistant" and 
                            prev_msg.get("tool_calls")):
                            for tc in prev_msg.get("tool_calls", []):
                                if tc.get("id") == tool_call_id:
                                    found_assistant = True
                                    break
                            if found_assistant:
                                break
                    
                    assert found_assistant, (
                        f"Tool message with tool_call_id '{tool_call_id}' in test case "
                        f"'{test_case['name']}' has no preceding assistant message with matching tool_call"
                    )

if __name__ == "__main__":
    pytest.main([__file__])