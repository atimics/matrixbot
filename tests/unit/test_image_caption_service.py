"""Tests for ImageCaptionService."""

import pytest
import asyncio
import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from image_caption_service import ImageCaptionService
from event_definitions import (
    MatrixImageReceivedEvent, 
    AIInferenceResponseEvent,
    ImageCacheRequestEvent,
    ImageCacheResponseEvent,
    SendReplyCommand,
    OpenRouterInferenceRequestEvent
)
from tests.test_utils import MockMessageBus


@pytest.mark.unit
class TestImageCaptionService:
    """Test ImageCaptionService functionality."""

    @pytest.fixture
    def mock_bus(self):
        """Create a mock message bus."""
        return MockMessageBus()

    @pytest.fixture
    def image_caption_service(self, mock_bus):
        """Create ImageCaptionService instance."""
        with patch.dict(os.environ, {"OPENROUTER_VISION_MODEL": "openai/gpt-4o"}):
            return ImageCaptionService(mock_bus)

    @pytest.mark.asyncio
    async def test_initialization(self, image_caption_service, mock_bus):
        """Test service initialization."""
        assert image_caption_service.bus == mock_bus
        assert image_caption_service.openrouter_vision_model == "openai/gpt-4o"
        assert hasattr(image_caption_service, '_stop_event')
        assert hasattr(image_caption_service, '_pending_requests')

    @pytest.mark.asyncio
    async def test_handle_image_message(self, image_caption_service, mock_bus):
        """Test handling of image received event."""
        image_event = MatrixImageReceivedEvent(
            room_id="!test:matrix.org",
            event_id_matrix="$event123",
            sender_display_name="TestUser",
            sender_id="@test:matrix.org",
            room_display_name="Test Room",
            image_url="mxc://matrix.org/image123",
            body="Check out this image!",
            timestamp=1234567890,
            image_info={"mimetype": "image/jpeg", "size": 1024}
        )

        await image_caption_service._handle_image_message(image_event)

        # Should publish ImageCacheRequestEvent
        cache_requests = mock_bus.get_published_events_of_type(ImageCacheRequestEvent)
        assert len(cache_requests) == 1
        
        cache_request = cache_requests[0]
        assert cache_request.image_url == "mxc://matrix.org/image123"
        assert cache_request.request_id in image_caption_service._pending_requests
        
        # Check pending request context
        pending_context = image_caption_service._pending_requests[cache_request.request_id]
        assert pending_context["room_id"] == "!test:matrix.org"
        assert pending_context["reply_to_event_id"] == "$event123"
        assert pending_context["original_image_url"] == "mxc://matrix.org/image123"
        assert pending_context["body"] == "Check out this image!"

    @pytest.mark.asyncio
    async def test_handle_image_cache_response_success(self, image_caption_service, mock_bus):
        """Test handling successful image cache response."""
        # Set up a pending request
        request_id = str(uuid.uuid4())
        image_caption_service._pending_requests[request_id] = {
            "room_id": "!test:matrix.org",
            "reply_to_event_id": "$event123",
            "original_image_url": "mxc://matrix.org/image123",
            "body": "Look at this image"
        }

        cache_response = ImageCacheResponseEvent(
            request_id=request_id,
            original_url="mxc://matrix.org/image123",
            success=True,
            s3_url="https://s3.amazonaws.com/bucket/cached_image.jpg",
            error_message=None
        )

        await image_caption_service._handle_image_cache_response(cache_response)

        # Should publish OpenRouterInferenceRequestEvent
        inference_requests = mock_bus.get_published_events_of_type(OpenRouterInferenceRequestEvent)
        assert len(inference_requests) == 1
        
        inference_request = inference_requests[0]
        assert inference_request.reply_to_service_event == "image_caption_response"
        assert inference_request.model_name == "openai/gpt-4o"
        assert inference_request.original_request_payload["room_id"] == "!test:matrix.org"
        assert inference_request.original_request_payload["reply_to_event_id"] == "$event123"
        
        # Check message payload contains S3 URL
        messages = inference_request.messages_payload
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        content = messages[0]["content"]
        assert any(item["type"] == "image_url" and 
                  item["image_url"]["url"] == "https://s3.amazonaws.com/bucket/cached_image.jpg" 
                  for item in content)

        # Pending request should be removed
        assert request_id not in image_caption_service._pending_requests

    @pytest.mark.asyncio
    async def test_handle_image_cache_response_failure(self, image_caption_service, mock_bus):
        """Test handling failed image cache response."""
        request_id = str(uuid.uuid4())
        image_caption_service._pending_requests[request_id] = {
            "room_id": "!test:matrix.org",
            "reply_to_event_id": "$event123",
            "original_image_url": "mxc://matrix.org/image123",
            "body": ""
        }

        cache_response = ImageCacheResponseEvent(
            request_id=request_id,
            original_url="mxc://matrix.org/image123",
            success=False,
            s3_url=None,
            error_message="Failed to cache image"
        )

        await image_caption_service._handle_image_cache_response(cache_response)

        # Should not publish any inference requests
        inference_requests = mock_bus.get_published_events_of_type(OpenRouterInferenceRequestEvent)
        assert len(inference_requests) == 0

        # Pending request should be removed
        assert request_id not in image_caption_service._pending_requests

    @pytest.mark.asyncio
    async def test_handle_image_cache_response_no_pending_request(self, image_caption_service, mock_bus):
        """Test handling cache response with no matching pending request."""
        cache_response = ImageCacheResponseEvent(
            request_id="unknown-request-id",
            original_url="mxc://matrix.org/image123",
            success=True,
            s3_url="https://s3.amazonaws.com/bucket/image.jpg",
            error_message=None
        )

        await image_caption_service._handle_image_cache_response(cache_response)

        # Should not publish any inference requests
        inference_requests = mock_bus.get_published_events_of_type(OpenRouterInferenceRequestEvent)
        assert len(inference_requests) == 0

    @pytest.mark.asyncio
    async def test_handle_caption_response_success(self, image_caption_service, mock_bus):
        """Test handling successful caption response."""
        response = AIInferenceResponseEvent(
            request_id="test-123",
            success=True,
            text_response="This image shows a beautiful sunset over mountains.",
            tool_calls=None,
            error_message=None,
            response_topic="image_caption_response",
            original_request_payload={
                "room_id": "!test:matrix.org",
                "reply_to_event_id": "$event123"
            }
        )

        await image_caption_service._handle_caption_response(response)

        # Should publish SendReplyCommand
        reply_commands = mock_bus.get_published_events_of_type(SendReplyCommand)
        assert len(reply_commands) == 1
        
        reply_command = reply_commands[0]
        assert reply_command.room_id == "!test:matrix.org"
        assert reply_command.reply_to_event_id == "$event123"
        assert reply_command.text == "This image shows a beautiful sunset over mountains."

    @pytest.mark.asyncio
    async def test_handle_caption_response_failure(self, image_caption_service, mock_bus):
        """Test handling failed caption response."""
        response = AIInferenceResponseEvent(
            request_id="test-456",
            success=False,
            text_response=None,
            tool_calls=None,
            error_message="Caption generation failed",
            response_topic="image_caption_response",
            original_request_payload={
                "room_id": "!test:matrix.org",
                "reply_to_event_id": "$event456"
            }
        )

        await image_caption_service._handle_caption_response(response)

        # Should publish SendReplyCommand with error message
        reply_commands = mock_bus.get_published_events_of_type(SendReplyCommand)
        assert len(reply_commands) == 1
        
        reply_command = reply_commands[0]
        assert reply_command.text == "[Image could not be interpreted]"

    @pytest.mark.asyncio
    async def test_handle_caption_response_wrong_topic(self, image_caption_service, mock_bus):
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
                "reply_to_event_id": "$event789"
            }
        )

        await image_caption_service._handle_caption_response(response)

        # Should not publish any replies
        reply_commands = mock_bus.get_published_events_of_type(SendReplyCommand)
        assert len(reply_commands) == 0

    @pytest.mark.asyncio
    async def test_handle_caption_response_missing_payload_data(self, image_caption_service, mock_bus):
        """Test handling response with missing room_id or event_id."""
        response = AIInferenceResponseEvent(
            request_id="test-missing",
            success=True,
            text_response="Caption text",
            tool_calls=None,
            error_message=None,
            response_topic="image_caption_response",
            original_request_payload={
                # Missing room_id and reply_to_event_id
            }
        )

        await image_caption_service._handle_caption_response(response)

        # Should not publish any replies
        reply_commands = mock_bus.get_published_events_of_type(SendReplyCommand)
        assert len(reply_commands) == 0

    @pytest.mark.asyncio
    async def test_service_run_and_stop(self, image_caption_service, mock_bus):
        """Test service run loop and stopping."""
        # Start service in background
        run_task = asyncio.create_task(image_caption_service.run())
        
        # Give it time to set up subscriptions
        await asyncio.sleep(0.1)
        
        # Stop the service
        await image_caption_service.stop()
        
        # Wait for run task to complete
        try:
            await asyncio.wait_for(run_task, timeout=1.0)
        except asyncio.TimeoutError:
            run_task.cancel()
            pytest.fail("Service did not stop within timeout")

    @pytest.mark.asyncio
    async def test_image_message_with_user_text(self, image_caption_service, mock_bus):
        """Test image message that includes user text with the image."""
        # Set up a pending request first
        request_id = str(uuid.uuid4())
        image_caption_service._pending_requests[request_id] = {
            "room_id": "!test:matrix.org",
            "reply_to_event_id": "$event123",
            "original_image_url": "mxc://matrix.org/image123",
            "body": "What do you think of this sunset?"
        }

        cache_response = ImageCacheResponseEvent(
            request_id=request_id,
            original_url="mxc://matrix.org/image123",
            success=True,
            s3_url="https://s3.amazonaws.com/bucket/sunset.jpg",
            error_message=None
        )

        await image_caption_service._handle_image_cache_response(cache_response)

        # Should include user text in the inference request
        inference_requests = mock_bus.get_published_events_of_type(OpenRouterInferenceRequestEvent)
        assert len(inference_requests) == 1
        
        # Check that user text is incorporated into the prompt
        # This would depend on the actual implementation details

    @pytest.mark.asyncio 
    async def test_default_vision_model_configuration(self, mock_bus):
        """Test default vision model when environment variable is not set."""
        with patch.dict(os.environ, {}, clear=True):
            service = ImageCaptionService(mock_bus)
            assert service.openrouter_vision_model == "openai/gpt-4o"