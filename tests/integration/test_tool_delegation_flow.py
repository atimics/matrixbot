import pytest
import asyncio
import json
import os
from unittest.mock import AsyncMock, patch

from message_bus import MessageBus
from room_logic_service import RoomLogicService
from tool_execution_service import ToolExecutionService
from tool_manager import ToolRegistry, ToolLoader
from ollama_inference_service import OllamaInferenceService
from ai_inference_service import AIInferenceService
from event_definitions import (
    MatrixMessageReceivedEvent,
    OllamaInferenceRequestEvent,
    OllamaInferenceResponseEvent,
    OpenRouterInferenceRequestEvent,
    OpenRouterInferenceResponseEvent,
    SendReplyCommand,
    ToolCall,
    ToolFunction,
    BotDisplayNameReadyEvent,
)
from available_tools.delegate_to_openrouter_tool import DELEGATED_OPENROUTER_RESPONSE_EVENT_TYPE
import database


import pytest_asyncio


@pytest_asyncio.fixture
async def initialized_bus():
    bus = MessageBus()
    yield bus
    await bus.shutdown()


@pytest_asyncio.fixture
async def test_db_path_integration(tmp_path):
    db_file = tmp_path / "test_integration_matrix_bot.db"
    await database.initialize_database(str(db_file))
    # Ensure default prompts exist
    if not await database.get_prompt(str(db_file), "system_default"):
        await database.update_prompt(str(db_file), "system_default", database.DEFAULT_SYSTEM_PROMPT)
    if not await database.get_prompt(str(db_file), "summarization_default"):
        await database.update_prompt(str(db_file), "summarization_default", database.DEFAULT_SUMMARIZATION_PROMPT)
    return str(db_file)


@pytest.fixture
def tool_registry_with_delegate():
    loader = ToolLoader()
    tools = loader.load_tools()
    assert any(tool.get_definition()["function"]["name"] == "call_openrouter_llm" for tool in tools)
    return ToolRegistry(tools)


@pytest.mark.asyncio
@pytest.mark.xfail(reason="Delegation flow integration not fully implemented")
@patch("room_logic_service.asyncio.sleep", new_callable=AsyncMock)
async def test_ollama_delegates_to_openrouter_and_responds(
    mock_sleep,
    initialized_bus: MessageBus,
    tool_registry_with_delegate: ToolRegistry,
    test_db_path_integration: str,
):
    bus = initialized_bus
    db_path = test_db_path_integration

    # ----------------- Mock Primary LLM (Ollama) -----------------
    async def mock_ollama_handle_request(request: OllamaInferenceRequestEvent):
        if "Original user query" in request.messages_payload[-1]["content"]:
            tool_call_id_ollama = "ollama_tool_call_delegate_123"
            response = OllamaInferenceResponseEvent(
                request_id=request.request_id,
                original_request_payload=request.original_request_payload,
                success=True,
                text_response=None,
                tool_calls=[
                    ToolCall(
                        id=tool_call_id_ollama,
                        type="function",
                        function=ToolFunction(
                            name="call_openrouter_llm",
                            arguments=json.dumps(
                                {
                                    "prompt_text": "Please process this complex query via OpenRouter.",
                                    "model_name": "mock_openrouter_model/gpt-x",
                                }
                            ),
                        ),
                    ).model_dump(mode="json")
                ],
            )
            response.event_type = request.reply_to_service_event
            await bus.publish(response)
        elif any(
            msg.get("role") == "tool" and msg.get("tool_call_id") == "ollama_tool_call_delegate_123"
            for msg in request.messages_payload
        ):
            assert any(
                "OpenRouter says: Processed!" in msg.get("content", "")
                for msg in request.messages_payload
                if msg.get("role") == "tool"
            )
            response = OllamaInferenceResponseEvent(
                request_id=request.request_id,
                original_request_payload=request.original_request_payload,
                success=True,
                text_response="Okay, after consulting OpenRouter: Processed!",
                tool_calls=None,
            )
            response.event_type = request.reply_to_service_event
            await bus.publish(response)
        else:
            pytest.fail(f"Unexpected Ollama request: {request.messages_payload}")

    bus.subscribe(OllamaInferenceRequestEvent.get_event_type(), mock_ollama_handle_request)

    # ----------------- Mock Delegated LLM (OpenRouter) -----------------
    async def mock_openrouter_handle_request(request: OpenRouterInferenceRequestEvent):
        assert request.model_name == "mock_openrouter_model/gpt-x"
        assert "Please process this complex query via OpenRouter." in request.messages_payload[-1]["content"]

        response = OpenRouterInferenceResponseEvent(
            request_id=request.request_id,
            original_request_payload=request.original_request_payload,
            success=True,
            text_response="OpenRouter says: Processed!",
            tool_calls=None,
        )
        response.event_type = DELEGATED_OPENROUTER_RESPONSE_EVENT_TYPE
        await bus.publish(response)

    bus.subscribe(OpenRouterInferenceRequestEvent.get_event_type(), mock_openrouter_handle_request)

    # ----------------- Services Under Test -----------------
    tes = ToolExecutionService(bus, tool_registry_with_delegate, db_path)
    tes_task = asyncio.create_task(tes.run())

    with patch.dict(os.environ, {"PRIMARY_LLM_PROVIDER": "ollama", "OLLAMA_DEFAULT_CHAT_MODEL": "mock_ollama_model"}):
        rls = RoomLogicService(bus, tool_registry_with_delegate, db_path, bot_display_name="TestBot")
    rls_task = asyncio.create_task(rls.run())

    await bus.publish(BotDisplayNameReadyEvent(display_name="TestBot", user_id="@bot:server"))

    room_id = "!testroom:matrix.org"
    user_message = MatrixMessageReceivedEvent(
        room_id=room_id,
        event_id_matrix="$event1",
        sender_display_name="UserA",
        sender_id="@usera:matrix.org",
        room_display_name="Test Room",
        body="Original user query to Ollama",
        timestamp=asyncio.get_event_loop().time(),
    )

    rls.room_activity_config[room_id] = {
        "last_message_ts": asyncio.get_event_loop().time(),
        "active_until_ts": asyncio.get_event_loop().time() + 3600,
        "pending_batch_for_memory": [],
        "short_term_memory": [],
        "consecutive_tool_calls": 0,
        "last_event_id": None,
        "processing_lock": asyncio.Lock(),
        "user_ids_in_room_context": set(),
        "pending_tool_calls": {},
    }

    final_reply_command = None

    original_bus_publish = bus.publish

    async def bus_publish_capture(event):
        nonlocal final_reply_command
        if isinstance(event, SendReplyCommand):
            final_reply_command = event
        await original_bus_publish(event)

    bus.publish = bus_publish_capture

    await bus.publish(user_message)


    for _ in range(50):
        if final_reply_command is not None:
            break
        await asyncio.sleep(0.1)

    await rls.stop()
    await tes.stop()
    await rls_task
    await tes_task
    bus.publish = original_bus_publish

    assert final_reply_command is not None
    assert final_reply_command.text == "Okay, after consulting OpenRouter: Processed!"
    assert final_reply_command.room_id == room_id
    assert final_reply_command.reply_to_event_id == "$event1"

