
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from ai_inference_service import AIInferenceService
from message_bus import MessageBus
from event_definitions import (
    OpenRouterInferenceRequestEvent,
    OpenRouterInferenceResponseEvent,
    ToolCall
)

@pytest.fixture
def mock_message_bus():
    bus = AsyncMock(spec=MessageBus)
    bus.publish = AsyncMock() # Ensure publish is an AsyncMock
    return bus

@pytest.fixture
def ai_service(mock_message_bus):
    # Mock os.getenv for OPENROUTER_API_KEY
    with patch('os.getenv', return_value='fake_api_key'):
        service = AIInferenceService(message_bus=mock_message_bus)
    return service

@pytest.fixture
def mock_httpx_client_post():
    with patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:
        yield mock_post

# --- Tests for OpenRouterInferenceRequestEvent Handling ---

@pytest.mark.asyncio
async def test_handle_openrouter_inference_request_success_text_response(
    ai_service: AIInferenceService, 
    mock_message_bus: MagicMock, 
    mock_httpx_client_post: AsyncMock
):
    request_event = OpenRouterInferenceRequestEvent(
        room_id="!room:host",
        ai_payload=[{"role": "user", "content": "Hello"}],
        original_request_payload_event_id="orig_payload_id",
        original_request_event_id="orig_req_id",
        event_type_to_respond_to="test_response_type",
        model_name="openrouter/test-model"
    )

    # Mock successful API response (text only)
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "id": "chatcmpl-123",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "AI response text"
                }
            }
        ]
    }
    mock_httpx_client_post.return_value = mock_response

    await ai_service._handle_open_router_inference_request(request_event)

    mock_httpx_client_post.assert_called_once()
    call_args = mock_httpx_client_post.call_args
    assert call_args[0][0] == "https://openrouter.ai/api/v1/chat/completions"
    assert call_args[1]["json"]["model"] == "openrouter/test-model"
    assert call_args[1]["json"]["messages"] == request_event.ai_payload

    mock_message_bus.publish.assert_called_once()
    response_event = mock_message_bus.publish.call_args[0][0]
    assert isinstance(response_event, OpenRouterInferenceResponseEvent)
    assert response_event.success is True
    assert response_event.text_response == "AI response text"
    assert response_event.tool_calls is None
    assert response_event.original_request_event_id == request_event.original_request_event_id
    assert response_event.original_request_payload_event_id == request_event.original_request_payload_event_id
    assert response_event.event_type_to_respond_to == request_event.event_type_to_respond_to

@pytest.mark.asyncio
async def test_handle_openrouter_inference_request_success_tool_calls(
    ai_service: AIInferenceService, 
    mock_message_bus: MagicMock, 
    mock_httpx_client_post: AsyncMock
):
    request_event = OpenRouterInferenceRequestEvent(
        room_id="!room:host",
        ai_payload=[{"role": "user", "content": "Call a tool"}],
        original_request_payload_event_id="orig_payload_id_tool",
        original_request_event_id="orig_req_id_tool",
        event_type_to_respond_to="test_tool_response_type",
        model_name="openrouter/tool-model",
        tools=[{"type": "function", "function": {"name": "get_weather"}}]
    )

    # Mock successful API response (tool calls)
    mock_api_tool_call = {
        "id": "call_abc",
        "type": "function",
        "function": {"name": "get_weather", "arguments": "{\"location\": \"Paris\"}"}
    }
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "id": "chatcmpl-456",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None, # No direct text content when tool_calls are present
                    "tool_calls": [mock_api_tool_call]
                }
            }
        ]
    }
    mock_httpx_client_post.return_value = mock_response

    await ai_service._handle_open_router_inference_request(request_event)

    mock_httpx_client_post.assert_called_once()
    mock_message_bus.publish.assert_called_once()
    response_event = mock_message_bus.publish.call_args[0][0]
    assert isinstance(response_event, OpenRouterInferenceResponseEvent)
    assert response_event.success is True
    assert response_event.text_response is None
    assert len(response_event.tool_calls) == 1
    tool_call = response_event.tool_calls[0]
    assert isinstance(tool_call, ToolCall)
    assert tool_call.id == "call_abc"
    assert tool_call.function_name == "get_weather"
    assert tool_call.function_args == "{\"location\": \"Paris\"}"

@pytest.mark.asyncio
async def test_handle_openrouter_inference_request_api_error(
    ai_service: AIInferenceService, 
    mock_message_bus: MagicMock, 
    mock_httpx_client_post: AsyncMock
):
    request_event = OpenRouterInferenceRequestEvent(
        room_id="!room:host",
        ai_payload=[{"role": "user", "content": "Trigger error"}],
        original_request_payload_event_id="orig_payload_id_err",
        original_request_event_id="orig_req_id_err",
        event_type_to_respond_to="test_error_response_type"
    )

    # Mock API error
    mock_httpx_client_post.side_effect = httpx.HTTPStatusError(
        message="Internal Server Error", request=MagicMock(), response=MagicMock(status_code=500)
    )

    await ai_service._handle_open_router_inference_request(request_event)

    mock_httpx_client_post.assert_called_once()
    mock_message_bus.publish.assert_called_once()
    response_event = mock_message_bus.publish.call_args[0][0]
    assert isinstance(response_event, OpenRouterInferenceResponseEvent)
    assert response_event.success is False
    assert response_event.text_response is None
    assert response_event.tool_calls is None
    assert "HTTPStatusError: Internal Server Error" in response_event.error_message

@pytest.mark.asyncio
async def test_handle_openrouter_inference_request_no_api_key(
    mock_message_bus: MagicMock
):
    # Create service without API key by patching getenv to return None for the key
    with patch('os.getenv', return_value=None) as mock_getenv:
        service_no_key = AIInferenceService(message_bus=mock_message_bus)
        mock_getenv.assert_any_call("OPENROUTER_API_KEY")
    
    request_event = OpenRouterInferenceRequestEvent(
        room_id="!room:host",
        ai_payload=[{"role": "user", "content": "Hello"}],
        original_request_payload_event_id="orig_payload_id_no_key",
        original_request_event_id="orig_req_id_no_key",
        event_type_to_respond_to="test_no_key_response_type"
    )

    # No httpx.AsyncClient.post should be called if API key is missing
    with patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post_no_key_call:
        await service_no_key._handle_open_router_inference_request(request_event)
        mock_post_no_key_call.assert_not_called()

    mock_message_bus.publish.assert_called_once()
    response_event = mock_message_bus.publish.call_args[0][0]
    assert isinstance(response_event, OpenRouterInferenceResponseEvent)
    assert response_event.success is False
    assert "OpenRouter API key is not configured." in response_event.error_message

@pytest.mark.asyncio
async def test_api_payload_construction_with_optional_params(
    ai_service: AIInferenceService, 
    mock_httpx_client_post: AsyncMock
):
    request_event = OpenRouterInferenceRequestEvent(
        room_id="!room:host",
        ai_payload=[{"role": "user", "content": "Hello"}],
        original_request_payload_event_id="orig_payload",
        original_request_event_id="orig_req",
        event_type_to_respond_to="test_response",
        model_name="openrouter/test-model",
        temperature=0.7,
        max_tokens=150,
        top_p=0.9,
        tool_choice="auto",
        tools=[{"type": "function", "function": {"name": "get_time"}}]
    )

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {"choices": [{"message": {"content": "OK"}}]}
    mock_httpx_client_post.return_value = mock_response

    await ai_service._handle_open_router_inference_request(request_event)

    mock_httpx_client_post.assert_called_once()
    api_payload = mock_httpx_client_post.call_args[1]["json"]
    
    assert api_payload["model"] == "openrouter/test-model"
    assert api_payload["messages"] == request_event.ai_payload
    assert api_payload["temperature"] == 0.7
    assert api_payload["max_tokens"] == 150
    assert api_payload["top_p"] == 0.9
    assert api_payload["tool_choice"] == "auto"
    assert api_payload["tools"] == request_event.tools

# Example of how to start testing the main run loop and subscription
# This is more of an integration test for the service's core behavior.
@pytest.mark.asyncio
async def test_service_subscribes_to_openrouter_requests_on_run(
    ai_service: AIInferenceService, 
    mock_message_bus: MagicMock
):
    # We need to patch the actual _handle_open_router_inference_request to prevent it from running
    # and making real HTTP calls or complex logic during this specific subscription test.
    with patch.object(ai_service, '_handle_open_router_inference_request', new_callable=AsyncMock) as mock_handler:
        
        # Simulate the service's run method being called, which should set up subscriptions.
        # The run method itself is a loop, so we don't call it directly in a test like this usually.
        # Instead, we test that the subscription happens as expected.
        # AIInferenceService's __init__ should call subscribe.
        # Let's verify that subscribe was called with the correct arguments.
        
        # Call init again, or check calls from fixture's init
        # The fixture `ai_service` already initializes the service.
        # So, `mock_message_bus.subscribe` should have been called during its creation.

        mock_message_bus.subscribe.assert_any_call(
            OpenRouterInferenceRequestEvent.event_type,
            ai_service._handle_open_router_inference_request
        )
        # If there are other subscriptions, add asserts for them too.

        # To test the handler being called, we can simulate a publish
        test_event = OpenRouterInferenceRequestEvent(
            room_id="!r:h", ai_payload=[], original_request_payload_event_id="p", 
            original_request_event_id="e", event_type_to_respond_to="t"
        )
        
        # This part requires the bus to actually call the handler.
        # The mock_message_bus is a MagicMock, so its subscribe doesn't store handlers in a way
        # that a bus.publish(test_event) on the mock bus would trigger the real handler.
        # Instead, we can directly call the handler as if the bus did it.
        await ai_service._handle_open_router_inference_request(test_event)
        mock_handler.assert_called_once_with(test_event)
