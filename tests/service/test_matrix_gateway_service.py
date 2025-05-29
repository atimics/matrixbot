"""Tests for MatrixGatewayService."""

import pytest
import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch, call
from nio import (
    AsyncClient, MatrixRoom, RoomMessageText, RoomMessageImage,
    LoginResponse, LoginError, ProfileGetResponse, ProfileGetError,
    RoomGetEventResponse, RoomGetEventError, WhoamiResponse, WhoamiError,
    JoinResponse, JoinError, ErrorResponse
)
from matrix_gateway_service import MatrixGatewayService
from event_definitions import (
    MatrixMessageReceivedEvent, MatrixImageReceivedEvent,
    SendMatrixMessageCommand, BotDisplayNameReadyEvent,
    SetTypingIndicatorCommand, SetPresenceCommand,
    ReactToMessageCommand, SendReplyCommand,
    RequestMatrixRoomInfoCommand, MatrixRoomInfoResponseEvent
)
from tests.test_utils import MockMessageBus


@pytest.mark.unit
class TestMatrixGatewayService:
    """Test MatrixGatewayService functionality."""

    @pytest.fixture
    def mock_bus(self):
        """Create a mock message bus."""
        return MockMessageBus()

    @pytest.fixture
    def mock_client(self):
        """Create a mock Matrix AsyncClient."""
        client = AsyncMock(spec=AsyncClient)
        client.user_id = "@bot:matrix.example.com"
        client.device_id = "DEVICE123"
        client.access_token = "test_token"
        client.logged_in = True
        return client

    @pytest.fixture
    def gateway_service(self, mock_bus):
        """Create MatrixGatewayService instance."""
        with patch.dict(os.environ, {
            "MATRIX_HOMESERVER": "https://matrix.example.com",
            "MATRIX_USER_ID": "@bot:matrix.example.com",
            "MATRIX_PASSWORD": "test_password",
            "MATRIX_ROOM_ID": "!test:matrix.example.com"
        }):
            return MatrixGatewayService(mock_bus)

    @pytest.mark.asyncio
    async def test_initialization(self, gateway_service, mock_bus):
        """Test service initialization."""
        assert gateway_service.bus == mock_bus
        assert gateway_service.homeserver == "https://matrix.example.com"
        assert gateway_service.user_id == "@bot:matrix.example.com"
        assert gateway_service.password == "test_password"
        assert gateway_service.bot_display_name == "ChatBot"
        assert hasattr(gateway_service, '_stop_event')

    @pytest.mark.asyncio
    async def test_rate_limited_matrix_call_success(self, gateway_service):
        """Test successful matrix call without rate limiting."""
        mock_func = AsyncMock(return_value="success")
        
        result = await gateway_service._rate_limited_matrix_call(mock_func, "arg1", kwarg1="value1")
        
        assert result == "success"
        mock_func.assert_called_once_with("arg1", kwarg1="value1")

    @pytest.mark.asyncio
    async def test_rate_limited_matrix_call_429_with_retry_after(self, gateway_service):
        """Test matrix call with 429 rate limit and retry after."""
        mock_func = AsyncMock()
        # First call raises 429, second succeeds
        rate_limit_error = Exception("Rate limited")
        rate_limit_error.status_code = 429
        rate_limit_error.retry_after_ms = 100  # 0.1 seconds
        mock_func.side_effect = [rate_limit_error, "success"]
        
        with patch.object(gateway_service, '_animated_sleep_with_progress', new_callable=AsyncMock) as mock_sleep:
            result = await gateway_service._rate_limited_matrix_call(mock_func)
        
        assert result == "success"
        assert mock_func.call_count == 2
        mock_sleep.assert_called_once_with(0.1, "Rate limit triggered")

    @pytest.mark.asyncio
    async def test_rate_limited_matrix_call_429_no_retry_after(self, gateway_service):
        """Test matrix call with 429 rate limit but no retry after header."""
        mock_func = AsyncMock()
        rate_limit_error = Exception("Rate limited")
        rate_limit_error.status_code = 429
        # No retry_after_ms attribute
        mock_func.side_effect = [rate_limit_error, "success"]
        
        with patch.object(gateway_service, '_animated_sleep_with_progress', new_callable=AsyncMock) as mock_sleep:
            result = await gateway_service._rate_limited_matrix_call(mock_func)
        
        assert result == "success"
        mock_sleep.assert_called_once_with(10.0, "Rate limit triggered")  # Default retry

    @pytest.mark.asyncio
    async def test_rate_limited_matrix_call_string_429(self, gateway_service):
        """Test matrix call with 429 in error string."""
        mock_func = AsyncMock()
        rate_limit_error = Exception("Error 429: M_LIMIT_EXCEEDED")
        mock_func.side_effect = [rate_limit_error, "success"]
        
        with patch.object(gateway_service, '_animated_sleep_with_progress', new_callable=AsyncMock) as mock_sleep:
            result = await gateway_service._rate_limited_matrix_call(mock_func)
        
        assert result == "success"
        mock_sleep.assert_called_once_with(10.0, "Rate limit triggered")

    @pytest.mark.asyncio
    async def test_rate_limited_matrix_call_non_rate_limit_error(self, gateway_service):
        """Test matrix call with non-rate-limit error."""
        mock_func = AsyncMock()
        other_error = Exception("Some other error")
        mock_func.side_effect = other_error
        
        with pytest.raises(Exception) as exc_info:
            await gateway_service._rate_limited_matrix_call(mock_func)
        
        assert str(exc_info.value) == "Some other error"

    @pytest.mark.asyncio
    async def test_command_worker(self, gateway_service):
        """Test command worker processes commands."""
        # Initialize the event and queue for testing
        gateway_service._stop_event = asyncio.Event()
        gateway_service._command_queue = asyncio.Queue()
        
        # Start command worker
        worker_task = asyncio.create_task(gateway_service._command_worker())
        
        # Add a command
        test_func = AsyncMock()
        await gateway_service._enqueue_command(test_func, "arg1", kwarg1="value1")
        
        # Give worker time to process
        await asyncio.sleep(0.1)
        
        # Stop worker properly
        gateway_service._stop_event.set()
        
        try:
            await asyncio.wait_for(worker_task, timeout=1.0)
        except asyncio.TimeoutError:
            worker_task.cancel()
            await asyncio.gather(worker_task, return_exceptions=True)
        
        test_func.assert_called_once_with("arg1", kwarg1="value1")

    @pytest.mark.asyncio
    async def test_matrix_message_callback_own_message(self, gateway_service, mock_client):
        """Test ignoring own messages."""
        gateway_service.client = mock_client
        
        room = MagicMock(spec=MatrixRoom)
        room.room_id = "!test:matrix.example.com"
        
        event = MagicMock(spec=RoomMessageText)
        event.sender = "@bot:matrix.example.com"  # Same as client user_id
        event.body = "Test message"
        
        await gateway_service._matrix_message_callback(room, event)
        
        # Should not publish any events for own messages
        assert len(gateway_service.bus.published_events) == 0

    @pytest.mark.asyncio
    async def test_matrix_message_callback_other_user(self, gateway_service, mock_client, mock_bus):
        """Test processing messages from other users."""
        gateway_service.client = mock_client
        
        room = MagicMock(spec=MatrixRoom)
        room.room_id = "!test:matrix.example.com"
        room.display_name = "Test Room"
        room.user_name.return_value = "TestUser"
        
        event = MagicMock(spec=RoomMessageText)
        event.sender = "@user:matrix.example.com"
        event.body = "Hello bot!  "  # With trailing spaces
        event.event_id = "$event123:matrix.example.com"
        
        await gateway_service._matrix_message_callback(room, event)
        
        # Should publish MatrixMessageReceivedEvent
        published_events = mock_bus.get_published_events_of_type(MatrixMessageReceivedEvent)
        assert len(published_events) == 1
        
        msg_event = published_events[0]
        assert msg_event.room_id == "!test:matrix.example.com"
        assert msg_event.sender_id == "@user:matrix.example.com"
        assert msg_event.body == "Hello bot!"  # Stripped
        assert msg_event.sender_display_name == "TestUser"

    @pytest.mark.asyncio
    async def test_matrix_image_callback(self, gateway_service, mock_client, mock_bus):
        """Test processing image messages."""
        gateway_service.client = mock_client
        
        room = MagicMock(spec=MatrixRoom)
        room.room_id = "!test:matrix.example.com"
        room.display_name = "Test Room"
        room.user_name.return_value = "TestUser"
        
        event = MagicMock(spec=RoomMessageImage)
        event.sender = "@user:matrix.example.com"
        event.event_id = "$image123:matrix.example.com"
        event.url = "mxc://matrix.example.com/image123"
        event.body = "Check this out"
        event.server_timestamp = 1234567890
        event.content = {
            "info": {
                "mimetype": "image/jpeg",
                "size": 1024,
                "w": 800,
                "h": 600
            },
            "filename": "test.jpg"
        }
        
        await gateway_service._matrix_image_callback(room, event)
        
        # Should publish MatrixImageReceivedEvent
        published_events = mock_bus.get_published_events_of_type(MatrixImageReceivedEvent)
        assert len(published_events) == 1
        
        img_event = published_events[0]
        assert img_event.room_id == "!test:matrix.example.com"
        assert img_event.sender_id == "@user:matrix.example.com"
        assert img_event.image_url == "mxc://matrix.example.com/image123"
        assert img_event.image_info["mimetype"] == "image/jpeg"
        assert img_event.image_info["size"] == 1024

    @pytest.mark.asyncio
    async def test_matrix_image_callback_no_url(self, gateway_service, mock_client):
        """Test image callback with missing URL."""
        gateway_service.client = mock_client
        
        room = MagicMock(spec=MatrixRoom)
        event = MagicMock(spec=RoomMessageImage)
        event.sender = "@user:matrix.example.com"
        event.event_id = "$missing_url_event:matrix.example.com"  # Add event_id
        # No url attribute
        delattr(event, 'url') if hasattr(event, 'url') else None
        
        await gateway_service._matrix_image_callback(room, event)
        
        # Should not publish any events
        assert len(gateway_service.bus.published_events) == 0

    @pytest.mark.asyncio
    async def test_send_message_impl_success(self, gateway_service, mock_client):
        """Test successful message sending."""
        gateway_service.client = mock_client
        
        command = SendMatrixMessageCommand(
            room_id="!test:matrix.example.com",
            text="Hello **world**!"
        )
        
        await gateway_service._send_message_impl(command)
        
        # Should call room_send with formatted content
        mock_client.room_send.assert_called_once()
        call_args = mock_client.room_send.call_args
        
        assert call_args[1]["room_id"] == "!test:matrix.example.com"
        assert call_args[1]["message_type"] == "m.room.message"
        content = call_args[1]["content"]
        assert content["body"] == "Hello **world**!"
        assert "formatted_body" in content
        assert content["format"] == "org.matrix.custom.html"

    @pytest.mark.asyncio
    async def test_send_message_impl_markdown_error(self, gateway_service, mock_client):
        """Test message sending with markdown conversion error."""
        gateway_service.client = mock_client
        
        command = SendMatrixMessageCommand(
            room_id="!test:matrix.example.com",
            text="Test message"
        )
        
        with patch('markdown.markdown', side_effect=Exception("Markdown error")):
            await gateway_service._send_message_impl(command)
        
        # Should fallback to plain text
        mock_client.room_send.assert_called_once()
        content = mock_client.room_send.call_args[1]["content"]
        assert content["body"] == "Test message"
        assert "formatted_body" not in content

    @pytest.mark.asyncio
    async def test_send_message_impl_no_client(self, gateway_service):
        """Test message sending with no client."""
        gateway_service.client = None
        
        command = SendMatrixMessageCommand(
            room_id="!test:matrix.example.com",
            text="Test message"
        )
        
        await gateway_service._send_message_impl(command)
        
        # Should not raise error, just log

    @pytest.mark.asyncio
    async def test_react_to_message_impl(self, gateway_service, mock_client):
        """Test reaction sending."""
        gateway_service.client = mock_client
        
        command = ReactToMessageCommand(
            room_id="!test:matrix.example.com",
            event_id_to_react_to="$event123:matrix.example.com",
            reaction_key="👍"
        )
        
        await gateway_service._react_to_message_impl(command)
        
        # Should send reaction
        mock_client.room_send.assert_called_once()
        call_args = mock_client.room_send.call_args
        
        assert call_args[1]["message_type"] == "m.reaction"
        content = call_args[1]["content"]
        assert content["m.relates_to"]["event_id"] == "$event123:matrix.example.com"
        assert content["m.relates_to"]["key"] == "👍"

    @pytest.mark.asyncio
    async def test_send_reply_impl_with_original_event(self, gateway_service, mock_client):
        """Test reply sending with successful original event fetch."""
        gateway_service.client = mock_client
        
        # Mock original event response
        original_event = MagicMock()
        original_event.sender = "@user:matrix.example.com"
        original_event.body = "Original message"
        
        event_response = MagicMock(spec=RoomGetEventResponse)
        event_response.event = original_event
        
        mock_client.room_get_event.return_value = event_response
        
        command = SendReplyCommand(
            room_id="!test:matrix.example.com",
            reply_to_event_id="$original:matrix.example.com",
            text="This is my reply",
            event_id="$reply:matrix.example.com"
        )
        
        await gateway_service._send_reply_impl(command)
        
        # Should fetch original event and send reply
        mock_client.room_get_event.assert_called_once_with(
            "!test:matrix.example.com", 
            "$original:matrix.example.com"
        )
        
        mock_client.room_send.assert_called_once()
        content = mock_client.room_send.call_args[1]["content"]
        
        assert "m.relates_to" in content
        assert content["m.relates_to"]["m.in_reply_to"]["event_id"] == "$original:matrix.example.com"
        assert "> Original message" in content["body"]
        assert "This is my reply" in content["body"]

    @pytest.mark.asyncio
    async def test_send_reply_impl_failed_original_event(self, gateway_service, mock_client):
        """Test reply sending when original event fetch fails."""
        gateway_service.client = mock_client
        
        # Mock failed event response
        error_response = MagicMock(spec=RoomGetEventError)
        error_response.message = "Event not found"
        error_response.status_code = 404
        
        mock_client.room_get_event.return_value = error_response
        
        command = SendReplyCommand(
            room_id="!test:matrix.example.com",
            reply_to_event_id="$missing:matrix.example.com",
            text="This is my reply",
            event_id="$reply:matrix.example.com"
        )
        
        await gateway_service._send_reply_impl(command)
        
        # Should still send reply without quote
        mock_client.room_send.assert_called_once()
        content = mock_client.room_send.call_args[1]["content"]
        assert content["body"] == "This is my reply"

    @pytest.mark.asyncio
    async def test_handle_request_room_info_success(self, gateway_service, mock_client, mock_bus):
        """Test successful room info request."""
        gateway_service.client = mock_client
        
        # Mock room state responses
        name_response = MagicMock()
        name_response.name = "Test Room Name"
        
        topic_response = MagicMock()
        topic_response.topic = "Test room topic"
        
        members_response = MagicMock()
        members_response.members = {
            "@user1:matrix.example.com": {},
            "@user2:matrix.example.com": {}
        }
        
        mock_client.room_get_state_event.side_effect = [name_response, topic_response]
        mock_client.joined_members.return_value = members_response
        
        command = RequestMatrixRoomInfoCommand(
            room_id="!test:matrix.example.com",
            aspects=["name", "topic", "members"],
            response_event_topic="room_info_response_test",
            event_id="$request:matrix.example.com",
            original_tool_call_id="call_123",
            turn_request_id="turn_456"
        )
        
        await gateway_service._handle_request_room_info(command)
        
        # Should publish room info response
        responses = mock_bus.get_published_events_of_type(MatrixRoomInfoResponseEvent)
        assert len(responses) == 1
        
        response = responses[0]
        assert response.success is True
        assert response.info["name"] == "Test Room Name"
        assert response.info["topic"] == "Test room topic"
        assert len(response.info["members"]) == 2

    @pytest.mark.asyncio
    async def test_handle_request_room_info_no_client(self, gateway_service, mock_bus):
        """Test room info request with no client."""
        gateway_service.client = None
        
        command = RequestMatrixRoomInfoCommand(
            room_id="!test:matrix.example.com",
            aspects=["name"],
            response_event_topic="room_info_response_test",
            event_id="$request:matrix.example.com",
            original_tool_call_id="call_123",
            turn_request_id="turn_456"
        )
        
        await gateway_service._handle_request_room_info(command)
        
        # Should publish failed response
        responses = mock_bus.get_published_events_of_type(MatrixRoomInfoResponseEvent)
        assert len(responses) == 1
        assert responses[0].success is False
        assert "not ready" in responses[0].error_message

    @pytest.mark.asyncio
    async def test_set_typing_impl(self, gateway_service, mock_client):
        """Test typing indicator setting."""
        gateway_service.client = mock_client
        
        command = SetTypingIndicatorCommand(
            room_id="!test:matrix.example.com",
            typing=True,
            timeout=30000
        )
        
        await gateway_service._set_typing_impl(command)
        
        mock_client.room_typing.assert_called_once_with(
            room_id="!test:matrix.example.com",
            typing_state=True,
            timeout=30000
        )

    @pytest.mark.asyncio
    async def test_set_presence_impl(self, gateway_service, mock_client):
        """Test presence setting."""
        gateway_service.client = mock_client
        
        command = SetPresenceCommand(
            presence="online",
            status_msg="Ready to chat!"
        )
        
        await gateway_service._set_presence_impl(command)
        
        mock_client.set_presence.assert_called_once_with(
            presence="online",
            status_msg="Ready to chat!"
        )

    @pytest.mark.asyncio
    async def test_run_missing_credentials(self, mock_bus):
        """Test run with missing credentials."""
        # No environment variables set
        with patch.dict(os.environ, {}, clear=True):
            service = MatrixGatewayService(mock_bus)
            
            # Should exit early
            await service.run()
            
            # No events should be published
            assert len(mock_bus.published_events) == 0

    @pytest.mark.asyncio
    async def test_get_client(self, gateway_service, mock_client):
        """Test getting the Matrix client."""
        gateway_service.client = mock_client
        
        assert gateway_service.get_client() == mock_client

    @pytest.mark.asyncio
    async def test_stop(self, gateway_service):
        """Test service stop."""
        # Initialize the stop event for testing
        gateway_service._stop_event = asyncio.Event()
        
        assert not gateway_service._stop_event.is_set()
        
        await gateway_service.stop()
        
        assert gateway_service._stop_event.is_set()

    @pytest.mark.asyncio
    async def test_command_enqueue(self, gateway_service):
        """Test command enqueueing."""
        # Initialize the queue for testing
        gateway_service._command_queue = asyncio.Queue()
        
        test_func = AsyncMock()
        
        await gateway_service._enqueue_command(test_func, "arg1", kwarg1="value1")
        
        # Command should be in queue
        assert not gateway_service._command_queue.empty()
        
        # Process the command
        func, args, kwargs = await gateway_service._command_queue.get()
        assert func == test_func
        assert args == ("arg1",)
        assert kwargs == {"kwarg1": "value1"}

    @pytest.mark.asyncio
    async def test_command_worker_exception_handling(self, gateway_service):
        """Test command worker handles exceptions gracefully."""
        # Initialize the event and queue for testing
        gateway_service._stop_event = asyncio.Event()
        gateway_service._command_queue = asyncio.Queue()
        
        # Function that raises exception
        def failing_func():
            raise Exception("Command failed")
        
        # Start worker
        worker_task = asyncio.create_task(gateway_service._command_worker())
        
        # Add failing command
        await gateway_service._enqueue_command(failing_func)
        
        # Give time to process
        await asyncio.sleep(0.1)
        
        # Worker should still be running
        assert not worker_task.done()
        
        # Stop worker properly
        gateway_service._stop_event.set()
        
        try:
            await asyncio.wait_for(worker_task, timeout=1.0)
        except asyncio.TimeoutError:
            worker_task.cancel()
            await asyncio.gather(worker_task, return_exceptions=True)

    @pytest.mark.asyncio
    async def test_handle_commands_via_bus(self, gateway_service, mock_bus):
        """Test that commands are properly handled via message bus."""
        # This tests the subscription setup
        gateway_service.client = AsyncMock()
        gateway_service.client.logged_in = True
        
        # Initialize the event and queue for testing
        gateway_service._stop_event = asyncio.Event()
        gateway_service._command_queue = asyncio.Queue()
        
        # Start command worker
        gateway_service._command_worker_task = asyncio.create_task(gateway_service._command_worker())
        
        # Send message command
        send_cmd = SendMatrixMessageCommand(
            room_id="!test:matrix.example.com",
            text="Test message"
        )
        
        await gateway_service._handle_send_message_command(send_cmd)
        
        # Give time to process
        await asyncio.sleep(0.1)
        
        # Should be queued for processing
        # (Testing the enqueue mechanism)
        
        # Cleanup
        gateway_service._stop_event.set()
        gateway_service._command_worker_task.cancel()
        try:
            await gateway_service._command_worker_task
        except asyncio.CancelledError:
            pass