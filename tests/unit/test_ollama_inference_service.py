"""Tests for OllamaInferenceService."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from ollama_inference_service import OllamaInferenceService
from event_definitions import OllamaInferenceRequestEvent, OllamaInferenceResponseEvent
from tests.test_utils import MockMessageBus
import ollama


@pytest.mark.unit
class TestOllamaInferenceService:
    """Test OllamaInferenceService functionality."""

    @pytest.fixture
    def mock_bus(self):
        """Create a mock message bus."""
        return MockMessageBus()

    @pytest.fixture
    def ollama_service(self, mock_bus):
        """Create OllamaInferenceService instance."""
        with patch('ollama.AsyncClient'):
            return OllamaInferenceService(mock_bus)

    @pytest.mark.asyncio
    async def test_initialization(self, ollama_service, mock_bus):
        """Test service initialization."""
        assert ollama_service.bus == mock_bus
        assert ollama_service.api_url == "http://localhost:11434"
        assert hasattr(ollama_service, '_client')
        assert hasattr(ollama_service, '_stop_event')

    @pytest.mark.asyncio
    async def test_initialization_with_custom_url(self, mock_bus):
        """Test service initialization with custom API URL."""
        with patch.dict('os.environ', {'OLLAMA_API_URL': 'http://custom:8080'}):
            with patch('ollama.AsyncClient'):
                service = OllamaInferenceService(mock_bus)
                assert service.api_url == "http://custom:8080"

    @pytest.mark.asyncio
    async def test_get_ollama_response_success_text_only(self, ollama_service):
        """Test successful Ollama response with text content only."""
        mock_response = {
            'message': {
                'content': 'This is a test response from Ollama.',
                'tool_calls': None
            }
        }
        ollama_service._client.chat = AsyncMock(return_value=mock_response)

        success, text_response, tool_calls, error_message = await ollama_service._get_ollama_response(
            model_name="llama2",
            messages_payload=[{"role": "user", "content": "Hello"}],
            tools=None
        )

        assert success is True
        assert text_response == "This is a test response from Ollama."
        assert tool_calls is None
        assert error_message is None

    @pytest.mark.asyncio
    async def test_get_ollama_response_success_with_tools(self, ollama_service):
        """Test successful Ollama response with tool calls."""
        # Mock tool call object
        mock_tool_call = MagicMock()
        mock_tool_call.function.name = "send_message"
        mock_tool_call.function.arguments = {"text": "Hello from tool"}

        mock_response = {
            'message': {
                'content': None,
                'tool_calls': [mock_tool_call]
            }
        }
        ollama_service._client.chat = AsyncMock(return_value=mock_response)

        with patch('uuid.uuid4') as mock_uuid:
            mock_uuid.return_value.hex = "test-tool-id"
            mock_uuid.return_value.__str__ = lambda self: "test-tool-id"

            success, text_response, tool_calls, error_message = await ollama_service._get_ollama_response(
                model_name="llama2",
                messages_payload=[{"role": "user", "content": "Use a tool"}],
                tools=[{"type": "function", "function": {"name": "send_message"}}]
            )

        assert success is True
        assert text_response is None
        assert tool_calls is not None
        assert len(tool_calls) == 1
        assert tool_calls[0]["id"] == "ollama_tool_test-tool-id"
        assert tool_calls[0]["type"] == "function"
        assert tool_calls[0]["function"]["name"] == "send_message"
        assert tool_calls[0]["function"]["arguments"] == {"text": "Hello from tool"}
        assert error_message is None

    @pytest.mark.asyncio
    async def test_get_ollama_response_with_both_content_and_tools(self, ollama_service):
        """Test Ollama response with both text content and tool calls."""
        mock_tool_call = MagicMock()
        mock_tool_call.function.name = "get_weather"
        mock_tool_call.function.arguments = {"location": "Tokyo"}

        mock_response = {
            'message': {
                'content': 'I\'ll check the weather for you.',
                'tool_calls': [mock_tool_call]
            }
        }
        ollama_service._client.chat = AsyncMock(return_value=mock_response)

        success, text_response, tool_calls, error_message = await ollama_service._get_ollama_response(
            model_name="llama2",
            messages_payload=[{"role": "user", "content": "What's the weather in Tokyo?"}],
            tools=[{"type": "function", "function": {"name": "get_weather"}}]
        )

        assert success is True
        assert text_response == "I'll check the weather for you."
        assert tool_calls is not None
        assert len(tool_calls) == 1
        assert error_message is None

    @pytest.mark.asyncio
    async def test_get_ollama_response_empty_response(self, ollama_service):
        """Test Ollama response with no content or tools."""
        mock_response = {
            'message': {
                'content': None,
                'tool_calls': None
            }
        }
        ollama_service._client.chat = AsyncMock(return_value=mock_response)

        success, text_response, tool_calls, error_message = await ollama_service._get_ollama_response(
            model_name="llama2",
            messages_payload=[{"role": "user", "content": "Hello"}]
        )

        assert success is True
        assert text_response is None
        assert tool_calls is None
        assert error_message is None

    @pytest.mark.asyncio
    async def test_get_ollama_response_api_error(self, ollama_service):
        """Test Ollama API ResponseError handling."""
        error = ollama.ResponseError("Model not found", status_code=404)
        ollama_service._client.chat = AsyncMock(side_effect=error)

        success, text_response, tool_calls, error_message = await ollama_service._get_ollama_response(
            model_name="nonexistent",
            messages_payload=[{"role": "user", "content": "Hello"}]
        )

        assert success is False
        assert text_response is None
        assert tool_calls is None
        assert "Ollama API Error: Model not found" in error_message

    @pytest.mark.asyncio
    async def test_get_ollama_response_general_exception(self, ollama_service):
        """Test general exception handling in Ollama response."""
        ollama_service._client.chat = AsyncMock(side_effect=Exception("Connection timeout"))

        success, text_response, tool_calls, error_message = await ollama_service._get_ollama_response(
            model_name="llama2",
            messages_payload=[{"role": "user", "content": "Hello"}]
        )

        assert success is False
        assert text_response is None
        assert tool_calls is None
        assert error_message == "Connection timeout"

    @pytest.mark.asyncio
    async def test_handle_inference_request_success(self, ollama_service, mock_bus):
        """Test handling successful inference request."""
        # Mock successful Ollama response
        mock_response = {
            'message': {
                'content': 'Response from Ollama model',
                'tool_calls': None
            }
        }
        ollama_service._client.chat = AsyncMock(return_value=mock_response)

        request = OllamaInferenceRequestEvent(
            request_id="test-request-123",
            reply_to_service_event="chat_response",
            original_request_payload={"room_id": "!test:matrix.org"},
            model_name="llama2",
            messages_payload=[{"role": "user", "content": "Hello"}],
            tools=None
        )

        await ollama_service._handle_inference_request(request)

        # Check that response was published
        responses = mock_bus.get_published_events_of_type(OllamaInferenceResponseEvent)
        assert len(responses) == 1
        
        response = responses[0]
        assert response.request_id == "test-request-123"
        assert response.success is True
        assert response.text_response == "Response from Ollama model"
        assert response.tool_calls is None
        assert response.error_message is None
        assert response.response_topic == "chat_response"

    @pytest.mark.asyncio
    async def test_handle_inference_request_failure(self, ollama_service, mock_bus):
        """Test handling failed inference request."""
        # Mock Ollama API error
        error = ollama.ResponseError("Server unavailable", status_code=503)
        ollama_service._client.chat = AsyncMock(side_effect=error)

        request = OllamaInferenceRequestEvent(
            request_id="test-request-456",
            reply_to_service_event="chat_response",
            original_request_payload={"room_id": "!test:matrix.org"},
            model_name="llama2",
            messages_payload=[{"role": "user", "content": "Hello"}],
            tools=None
        )

        await ollama_service._handle_inference_request(request)

        # Check that error response was published
        responses = mock_bus.get_published_events_of_type(OllamaInferenceResponseEvent)
        assert len(responses) == 1
        
        response = responses[0]
        assert response.success is False
        assert response.text_response is None
        assert response.tool_calls is None
        assert "Ollama API Error: Server unavailable" in response.error_message

    @pytest.mark.asyncio
    async def test_handle_inference_request_with_tools(self, ollama_service, mock_bus):
        """Test handling inference request with tools."""
        # Mock tool call
        mock_tool_call = MagicMock()
        mock_tool_call.function.name = "search_web"
        mock_tool_call.function.arguments = {"query": "Python tutorials"}

        mock_response = {
            'message': {
                'content': 'I\'ll search for that.',
                'tool_calls': [mock_tool_call]
            }
        }
        ollama_service._client.chat = AsyncMock(return_value=mock_response)

        request = OllamaInferenceRequestEvent(
            request_id="test-request-789",
            reply_to_service_event="chat_response",
            original_request_payload={"room_id": "!test:matrix.org"},
            model_name="llama2",
            messages_payload=[{"role": "user", "content": "Search for Python tutorials"}],
            tools=[{"type": "function", "function": {"name": "search_web"}}]
        )

        await ollama_service._handle_inference_request(request)

        responses = mock_bus.get_published_events_of_type(OllamaInferenceResponseEvent)
        assert len(responses) == 1
        
        response = responses[0]
        assert response.success is True
        assert response.text_response == "I'll search for that."
        assert response.tool_calls is not None
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].function.name == "search_web"

    @pytest.mark.asyncio
    async def test_service_run_and_stop(self, ollama_service, mock_bus):
        """Test service run loop and stopping."""
        # Start service in background
        run_task = asyncio.create_task(ollama_service.run())
        
        # Give it time to set up subscriptions
        await asyncio.sleep(0.1)
        
        # Stop the service
        await ollama_service.stop()
        
        # Wait for run task to complete
        try:
            await asyncio.wait_for(run_task, timeout=1.0)
        except asyncio.TimeoutError:
            run_task.cancel()
            pytest.fail("Service did not stop within timeout")

    @pytest.mark.asyncio
    async def test_client_cleanup_on_stop(self, ollama_service):
        """Test that client is properly closed when service stops."""
        ollama_service._client.aclose = AsyncMock()
        
        # Start and immediately stop
        run_task = asyncio.create_task(ollama_service.run())
        await asyncio.sleep(0.1)
        await ollama_service.stop()
        
        await run_task
        
        # Verify client was closed
        ollama_service._client.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_client_cleanup_exception_handling(self, ollama_service):
        """Test exception handling during client cleanup."""
        ollama_service._client.aclose = AsyncMock(side_effect=Exception("Cleanup error"))
        
        # Start and stop - should not raise exception
        run_task = asyncio.create_task(ollama_service.run())
        await asyncio.sleep(0.1)
        await ollama_service.stop()
        
        await run_task  # Should complete without raising exception