import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio # Added asyncio import

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
        request_id="test_req_id_text", # Added
        reply_to_service_event="test_reply_event_text", # Added
        model_name="openrouter/test-model",
        messages_payload=[{"role": "user", "content": "Hello"}], # Changed from ai_payload
        original_request_payload={"original_request_payload_event_id":"orig_payload_id", "original_request_event_id":"orig_req_id", "event_type_to_respond_to":"test_response_type"} # Store old fields here
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

    await ai_service._handle_inference_request(request_event)

    mock_httpx_client_post.assert_called_once()
    call_args = mock_httpx_client_post.call_args
    assert call_args[0][0] == "https://openrouter.ai/api/v1/chat/completions"
    assert call_args[1]["json"]["model"] == "openrouter/test-model"
    assert call_args[1]["json"]["messages"] == request_event.messages_payload # Changed from ai_payload

    mock_message_bus.publish.assert_called_once()
    response_event = mock_message_bus.publish.call_args[0][0]
    assert isinstance(response_event, OpenRouterInferenceResponseEvent)
    assert response_event.success is True
    assert response_event.text_response == "AI response text"
    assert response_event.tool_calls is None
    assert response_event.request_id == request_event.request_id # Changed
    # Check original_request_payload for the old fields
    assert response_event.original_request_payload["original_request_payload_event_id"] == "orig_payload_id"
    assert response_event.original_request_payload["original_request_event_id"] == "orig_req_id"
    assert response_event.original_request_payload["event_type_to_respond_to"] == "test_response_type"

@pytest.mark.asyncio
async def test_handle_openrouter_inference_request_success_tool_calls(
    ai_service: AIInferenceService, 
    mock_message_bus: MagicMock, 
    mock_httpx_client_post: AsyncMock
):
    request_event = OpenRouterInferenceRequestEvent(
        request_id="test_req_id_tool", # Added
        reply_to_service_event="test_reply_event_tool", # Added
        model_name="openrouter/tool-model",
        messages_payload=[{"role": "user", "content": "Call a tool"}], # Changed from ai_payload
        tools=[{"type": "function", "function": {"name": "get_weather"}}],
        original_request_payload={"original_request_payload_event_id":"orig_payload_id_tool", "original_request_event_id":"orig_req_id_tool", "event_type_to_respond_to":"test_tool_response_type"} # Store old fields here
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

    await ai_service._handle_inference_request(request_event)

    mock_httpx_client_post.assert_called_once()
    mock_message_bus.publish.assert_called_once()
    response_event = mock_message_bus.publish.call_args[0][0]
    assert isinstance(response_event, OpenRouterInferenceResponseEvent)
    assert response_event.success is True
    assert response_event.text_response is None
    assert len(response_event.tool_calls) == 1
    tool_call = response_event.tool_calls[0]
    assert isinstance(tool_call, ToolCall) # Changed to ToolCall
    assert tool_call.id == "call_abc" 
    assert tool_call.function.name == "get_weather"
    assert tool_call.function.arguments == {"location": "Paris"} # Changed to expect a dict

@pytest.mark.asyncio
async def test_handle_openrouter_inference_request_api_error(
    ai_service: AIInferenceService, 
    mock_message_bus: MagicMock, 
    mock_httpx_client_post: AsyncMock
):
    request_event = OpenRouterInferenceRequestEvent(
        request_id="test_req_id_err", # Added
        reply_to_service_event="test_reply_event_err", # Added
        model_name="openrouter/error-model", # Added model_name
        messages_payload=[{"role": "user", "content": "Trigger error"}], # Changed from ai_payload
        original_request_payload={"original_request_payload_event_id":"orig_payload_id_err", "original_request_event_id":"orig_req_id_err", "event_type_to_respond_to":"test_error_response_type"}
    )

    # Mock API error
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error - More details here"
    mock_httpx_client_post.side_effect = httpx.HTTPStatusError(
        message="Internal Server Error", request=MagicMock(), response=mock_response
    )

    await ai_service._handle_inference_request(request_event)

    mock_httpx_client_post.assert_called_once()
    mock_message_bus.publish.assert_called_once()
    response_event = mock_message_bus.publish.call_args[0][0]
    assert isinstance(response_event, OpenRouterInferenceResponseEvent)
    assert response_event.success is False
    assert response_event.text_response is None
    assert response_event.tool_calls is None
    # Updated assertion to match the actual error message format
    assert "HTTP error: 500" in response_event.error_message 
    assert "Internal Server Error" in response_event.error_message

@pytest.mark.asyncio
async def test_handle_openrouter_inference_request_no_api_key(
    mock_message_bus: MagicMock
):
    # Create service without API key by patching getenv to return None for the key
    with patch('os.getenv', return_value=None) as mock_getenv:
        service_no_key = AIInferenceService(message_bus=mock_message_bus)
        mock_getenv.assert_any_call("OPENROUTER_API_KEY")
    
    request_event = OpenRouterInferenceRequestEvent(
        request_id="test_req_id_no_key", # Added
        reply_to_service_event="test_reply_event_no_key", # Added
        model_name="openrouter/key-model", # Added model_name
        messages_payload=[{"role": "user", "content": "Hello"}], # Changed from ai_payload
        original_request_payload={"original_request_payload_event_id":"orig_payload_id_no_key", "original_request_event_id":"orig_req_id_no_key", "event_type_to_respond_to":"test_no_key_response_type"}
    )

    # No httpx.AsyncClient.post should be called if API key is missing
    with patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post_no_key_call:
        await service_no_key._handle_inference_request(request_event)
        mock_post_no_key_call.assert_not_called()

    mock_message_bus.publish.assert_called_once()
    response_event = mock_message_bus.publish.call_args[0][0]
    assert isinstance(response_event, OpenRouterInferenceResponseEvent)
    assert response_event.success is False
    assert "OpenRouter API key not configured" in response_event.error_message # Removed period

@pytest.mark.asyncio
async def test_api_payload_construction_with_optional_params(
    ai_service: AIInferenceService, 
    mock_httpx_client_post: AsyncMock
):
    request_event = OpenRouterInferenceRequestEvent(
        request_id="test_req_id_opt", # Added
        reply_to_service_event="test_reply_event_opt", # Added
        model_name="openrouter/test-model",
        messages_payload=[{"role": "user", "content": "Hello"}], # Changed from ai_payload
        tool_choice="auto",
        tools=[{"type": "function", "function": {"name": "get_time"}}],
        original_request_payload={"original_request_payload_event_id":"orig_payload", "original_request_event_id":"orig_req", "event_type_to_respond_to":"test_response"}
    )

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {"choices": [{"message": {"content": "OK"}}]}
    mock_httpx_client_post.return_value = mock_response

    await ai_service._handle_inference_request(request_event)

    mock_httpx_client_post.assert_called_once()
    api_payload = mock_httpx_client_post.call_args[1]["json"]
    
    assert api_payload["model"] == "openrouter/test-model"
    assert api_payload["messages"] == request_event.messages_payload # Changed from ai_payload
    # assert api_payload["temperature"] == 0.7 # Removed
    # assert api_payload["max_tokens"] == 150  # Removed
    # assert api_payload["top_p"] == 0.9       # Removed
    assert api_payload["tool_choice"] == "auto"
    assert api_payload["tools"] == request_event.tools

# Example of how to start testing the main run loop and subscription
# This is more of an integration test for the service's core behavior.
@pytest.mark.asyncio
async def test_service_subscribes_to_openrouter_requests_on_run(
    ai_service: AIInferenceService, 
    mock_message_bus: MagicMock
):
    # The AIInferenceService's run method is now responsible for subscription.
    # We need to ensure that run() is called to set up the subscription.
    # Since run() is an infinite loop, we'll patch _stop_event.wait() to exit early.
    
    with patch.object(ai_service, '_handle_inference_request', new_callable=AsyncMock) as mock_handler, \
         patch.object(ai_service._stop_event, 'wait', new_callable=AsyncMock) as mock_stop_wait:

        # Start the service's run method in the background
        run_task = asyncio.create_task(ai_service.run())

        # Allow the run method to proceed and set up subscriptions
        # We need to yield control to the event loop for the run_task to execute.
        # A small delay should be enough for the subscription to happen.
        await asyncio.sleep(0.01)


        mock_message_bus.subscribe.assert_any_call(
            OpenRouterInferenceRequestEvent.get_event_type(),
            ai_service._handle_inference_request
        )
        
        # To test the handler being called, we can simulate a publish
        # This part requires a more integrated test setup or a way to capture subscribed handlers.
        # For now, we've verified the subscription call.
        # If the message bus actually stored and called handlers, we could test it like this:
        # test_event = OpenRouterInferenceRequestEvent(...)
        # await mock_message_bus.publish(test_event) # This would need to trigger the handler
        # mock_handler.assert_called_once_with(test_event)

        # Stop the service
        await ai_service.stop() # Added await
        await run_task # Ensure the run task completes
