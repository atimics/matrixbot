import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from summarization_service import SummarizationService
from message_bus import MessageBus
from event_definitions import (
    AIInferenceResponseEvent,
    SummaryGeneratedEvent,
    RequestAISummaryCommand,
    HistoricalMessage,
    OpenRouterInferenceRequestEvent,
    OllamaInferenceRequestEvent,
)


@pytest.mark.asyncio
@patch('summarization_service.database.initialize_database', new_callable=AsyncMock)
@patch('summarization_service.database.update_summary', new_callable=AsyncMock)
async def test_handle_ai_summary_response_success(mock_update, mock_init_db):
    bus = AsyncMock(spec=MessageBus)
    bus.publish = AsyncMock()
    service = SummarizationService(bus)

    event = AIInferenceResponseEvent(
        request_id="req",
        original_request_payload={
            "room_id": "room1",
            "event_id_of_last_message_in_summary_batch": "e1",
        },
        success=True,
        text_response="summary text",
        tool_calls=None,
        response_topic="ai_summary_response_received",
    )

    await service._handle_ai_summary_response(event)

    mock_update.assert_called_once_with(service.db_path, "room1", "summary text", "e1")
    bus.publish.assert_called_once()
    published = bus.publish.call_args[0][0]
    assert isinstance(published, SummaryGeneratedEvent)
    assert published.room_id == "room1"
    assert published.summary_text == "summary text"
    assert published.last_event_id_summarized == "e1"


@pytest.mark.asyncio
@patch('summarization_service.database.initialize_database', new_callable=AsyncMock)
@patch('summarization_service.database.update_summary', new_callable=AsyncMock)
async def test_handle_ai_summary_response_missing_info(mock_update, mock_init_db):
    bus = AsyncMock(spec=MessageBus)
    bus.publish = AsyncMock()
    service = SummarizationService(bus)

    event = AIInferenceResponseEvent(
        request_id="req",
        original_request_payload={"room_id": "room1"},
        success=True,
        text_response="summary",
        tool_calls=None,
        response_topic="ai_summary_response_received",
    )

    await service._handle_ai_summary_response(event)

    mock_update.assert_not_called()
    bus.publish.assert_not_called()


@pytest.mark.asyncio
@patch('summarization_service.database.initialize_database', new_callable=AsyncMock)
@patch('summarization_service.database.get_summary', new_callable=AsyncMock, return_value=(None, None))
@patch('summarization_service.prompt_constructor.build_summary_generation_payload', new_callable=AsyncMock, return_value=[{"role": "user", "content": "payload"}])
@patch('summarization_service.uuid.uuid4', return_value="uuid123")
async def test_handle_request_ai_summary_command_openrouter(mock_uuid, mock_build, mock_get_summary, mock_init_db):
    bus = AsyncMock(spec=MessageBus)
    bus.publish = AsyncMock()
    service = SummarizationService(bus, bot_display_name="Bot")

    msg = HistoricalMessage(role="user", content="Hi", event_id="evt1")
    cmd = RequestAISummaryCommand(room_id="room1", messages_to_summarize=[msg])

    await service._handle_request_ai_summary_command(cmd)

    mock_build.assert_called_once()
    assert mock_build.call_args.kwargs["transcript_for_summarization"] == "Unknown User: Hi"
    assert mock_build.call_args.kwargs["previous_summary"] is None
    assert mock_build.call_args.kwargs["db_path"] == service.db_path
    assert mock_build.call_args.kwargs["bot_display_name"] == "Bot"

    bus.publish.assert_called_once()
    sent_event = bus.publish.call_args[0][0]
    assert isinstance(sent_event, OpenRouterInferenceRequestEvent)
    assert sent_event.request_id == "uuid123"
    assert sent_event.original_request_payload["room_id"] == "room1"
    assert sent_event.original_request_payload["event_id_of_last_message_in_summary_batch"] == "evt1"
    assert sent_event.messages_payload == [{"role": "user", "content": "payload"}]


@pytest.mark.asyncio
@patch('summarization_service.database.initialize_database', new_callable=AsyncMock)
@patch('summarization_service.database.get_summary', new_callable=AsyncMock, return_value=(None, None))
@patch('summarization_service.prompt_constructor.build_summary_generation_payload', new_callable=AsyncMock, return_value=[{"role": "user", "content": "payload"}])
@patch('summarization_service.uuid.uuid4', return_value="uuid456")
async def test_handle_request_ai_summary_command_ollama(mock_uuid, mock_build, mock_get_summary, mock_init_db):
    bus = AsyncMock(spec=MessageBus)
    bus.publish = AsyncMock()
    with patch.dict('os.environ', {"PRIMARY_LLM_PROVIDER": "ollama"}):
        service = SummarizationService(bus)

    msg = HistoricalMessage(role="user", content="Hello", event_id="ev1")
    cmd = RequestAISummaryCommand(room_id="room1", messages_to_summarize=[msg])

    await service._handle_request_ai_summary_command(cmd)

    bus.publish.assert_called_once()
    sent_event = bus.publish.call_args[0][0]
    assert isinstance(sent_event, OllamaInferenceRequestEvent)
    assert sent_event.request_id == "uuid456"
    assert sent_event.original_request_payload["room_id"] == "room1"
    assert sent_event.original_request_payload["event_id_of_last_message_in_summary_batch"] == "ev1"
    assert sent_event.messages_payload == [{"role": "user", "content": "payload"}]

