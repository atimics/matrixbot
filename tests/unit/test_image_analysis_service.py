"""Tests for ImageAnalysisService."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from image_analysis_service import ImageAnalysisService
from event_definitions import AIInferenceResponseEvent, ToolExecutionResponse
from tests.test_utils import MockMessageBus


@pytest.mark.unit
class TestImageAnalysisService:
    """Test ImageAnalysisService functionality."""

    @pytest.fixture
    def mock_bus(self):
        """Create a mock message bus."""
        return MockMessageBus()

    @pytest.fixture
    def image_analysis_service(self, mock_bus):
        """Create ImageAnalysisService instance."""
        return ImageAnalysisService(mock_bus)

    @pytest.mark.asyncio
    async def test_initialization(self, image_analysis_service, mock_bus):
        """Test service initialization."""
        assert image_analysis_service.bus == mock_bus
        assert hasattr(image_analysis_service, '_stop_event')

    @pytest.mark.asyncio
    async def test_handle_image_analysis_response_success(self, image_analysis_service, mock_bus):
        """Test handling successful image analysis response."""
        response = AIInferenceResponseEvent(
            request_id="test-123",
            success=True,
            text_response="This is a photo of a cat sitting on a windowsill.",
            tool_calls=None,
            error_message=None,
            response_topic="image_analysis_response",
            original_request_payload={
                "room_id": "!test:matrix.org",
                "tool_call_id": "call_456",
                "analysis_type": "general_description"
            }
        )

        await image_analysis_service._handle_image_analysis_response(response)

        # Check that ToolExecutionResponse was published
        tool_responses = mock_bus.get_published_events_of_type(ToolExecutionResponse)
        assert len(tool_responses) == 1
        
        tool_response = tool_responses[0]
        assert tool_response.original_tool_call_id == "call_456"
        assert tool_response.tool_name == "describe_image"
        assert tool_response.status == "success"
        assert "Image Analysis (general_description)" in tool_response.result_for_llm_history
        assert "cat sitting on a windowsill" in tool_response.result_for_llm_history
        assert tool_response.error_message is None

    @pytest.mark.asyncio
    async def test_handle_image_analysis_response_failure(self, image_analysis_service, mock_bus):
        """Test handling failed image analysis response."""
        response = AIInferenceResponseEvent(
            request_id="test-456",
            success=False,
            text_response=None,
            tool_calls=None,
            error_message="Image processing failed",
            response_topic="image_analysis_response",
            original_request_payload={
                "room_id": "!test:matrix.org",
                "tool_call_id": "call_789",
                "analysis_type": "detailed_analysis"
            }
        )

        await image_analysis_service._handle_image_analysis_response(response)

        tool_responses = mock_bus.get_published_events_of_type(ToolExecutionResponse)
        assert len(tool_responses) == 1
        
        tool_response = tool_responses[0]
        assert tool_response.status == "failure"
        assert "[Image analysis failed: Image processing failed]" in tool_response.result_for_llm_history
        assert tool_response.error_message == "Image processing failed"

    @pytest.mark.asyncio
    async def test_handle_image_analysis_response_wrong_topic(self, image_analysis_service, mock_bus):
        """Test ignoring responses with wrong topic."""
        response = AIInferenceResponseEvent(
            request_id="test-789",
            success=True,
            text_response="Some response",
            tool_calls=None,
            error_message=None,
            response_topic="chat_response",  # Wrong topic
            original_request_payload={
                "room_id": "!test:matrix.org",
                "tool_call_id": "call_123"
            }
        )

        await image_analysis_service._handle_image_analysis_response(response)

        # Should not publish any responses
        tool_responses = mock_bus.get_published_events_of_type(ToolExecutionResponse)
        assert len(tool_responses) == 0

    @pytest.mark.asyncio
    async def test_handle_image_analysis_response_missing_room_id(self, image_analysis_service, mock_bus):
        """Test handling response with missing room_id."""
        response = AIInferenceResponseEvent(
            request_id="test-missing-room",
            success=True,
            text_response="Analysis result",
            tool_calls=None,
            error_message=None,
            response_topic="image_analysis_response",
            original_request_payload={
                # Missing room_id
                "tool_call_id": "call_123"
            }
        )

        await image_analysis_service._handle_image_analysis_response(response)

        # Should not publish any responses due to missing room_id
        tool_responses = mock_bus.get_published_events_of_type(ToolExecutionResponse)
        assert len(tool_responses) == 0

    @pytest.mark.asyncio
    async def test_handle_image_analysis_response_missing_tool_call_id(self, image_analysis_service, mock_bus):
        """Test handling response with missing tool_call_id."""
        response = AIInferenceResponseEvent(
            request_id="test-missing-tool-call",
            success=True,
            text_response="Analysis result",
            tool_calls=None,
            error_message=None,
            response_topic="image_analysis_response",
            original_request_payload={
                "room_id": "!test:matrix.org"
                # Missing tool_call_id
            }
        )

        await image_analysis_service._handle_image_analysis_response(response)

        # Should not publish any responses due to missing tool_call_id
        tool_responses = mock_bus.get_published_events_of_type(ToolExecutionResponse)
        assert len(tool_responses) == 0

    @pytest.mark.asyncio
    async def test_handle_image_analysis_response_success_no_error_message(self, image_analysis_service, mock_bus):
        """Test successful response without explicit error message."""
        response = AIInferenceResponseEvent(
            request_id="test-no-error",
            success=False,
            text_response=None,
            tool_calls=None,
            error_message=None,  # No explicit error message
            response_topic="image_analysis_response",
            original_request_payload={
                "room_id": "!test:matrix.org",
                "tool_call_id": "call_999",
                "analysis_type": "object_detection"
            }
        )

        await image_analysis_service._handle_image_analysis_response(response)

        tool_responses = mock_bus.get_published_events_of_type(ToolExecutionResponse)
        assert len(tool_responses) == 1
        
        tool_response = tool_responses[0]
        assert tool_response.status == "failure"
        assert "[Image analysis failed: Unknown error]" in tool_response.result_for_llm_history

    @pytest.mark.asyncio
    async def test_service_run_and_stop(self, image_analysis_service, mock_bus):
        """Test service run loop and stopping."""
        # Start service in background
        run_task = asyncio.create_task(image_analysis_service.run())
        
        # Give it time to set up subscriptions
        await asyncio.sleep(0.1)
        
        # Stop the service
        await image_analysis_service.stop()
        
        # Wait for run task to complete
        try:
            await asyncio.wait_for(run_task, timeout=1.0)
        except asyncio.TimeoutError:
            run_task.cancel()
            pytest.fail("Service did not stop within timeout")

    @pytest.mark.asyncio
    async def test_service_subscription_setup(self, image_analysis_service, mock_bus):
        """Test that service properly subscribes to events."""
        # Start service briefly to set up subscriptions
        run_task = asyncio.create_task(image_analysis_service.run())
        await asyncio.sleep(0.1)
        await image_analysis_service.stop()
        await run_task
        
        # Verify subscription was made (check mock_bus internal state if needed)
        # This is more of an integration test to ensure the service starts properly