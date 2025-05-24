"""Comprehensive tests for the MatrixGatewayService."""

import pytest
import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from datetime import datetime, timezone

from matrix_gateway_service import MatrixGatewayService
from tests.test_utils import ServiceTestBase, MockMessageBus
from tests.factories import (
    SendMatrixMessageCommandFactory,
    SendReplyCommandFactory,
    ReactToMessageCommandFactory,
    SetTypingIndicatorCommandFactory,
    SetPresenceCommandFactory,
    RequestMatrixRoomInfoCommandFactory
)
from event_definitions import (
    SendMatrixMessageCommand,
    SendReplyCommand,
    ReactToMessageCommand,
    SetTypingIndicatorCommand,
    SetPresenceCommand,
    RequestMatrixRoomInfoCommand,
    MatrixRoomInfoResponseEvent,
    BotDisplayNameReadyEvent,
    MatrixMessageReceivedEvent,
    MatrixImageReceivedEvent
)


@pytest.mark.unit
class TestMatrixGatewayService(ServiceTestBase):
    """Test the MatrixGatewayService functionality."""

    @pytest.fixture
    def mock_matrix_client(self):
        """Create a mock Matrix client."""
        client = AsyncMock()
        client.user_id = "@bot:matrix.example.com"
        client.device_id = "test_device"
        client.access_token = "test_token"
        client.logged_in = True
        return client

    @pytest.fixture
    def gateway_service(self, mock_matrix_client):
        """Create a MatrixGatewayService instance for testing."""
        with patch.dict(os.environ, {
            'MATRIX_HOMESERVER': 'https://matrix.example.com',
            'MATRIX_USER_ID': '@bot:matrix.example.com',
            'MATRIX_PASSWORD': 'test_password',
            'MATRIX_ROOM_ID': '!test:matrix.example.com'
        }):
            service = MatrixGatewayService(message_bus=self.mock_bus)
            service.client = mock_matrix_client
            return service

    @pytest.mark.asyncio
    async def test_initialization(self, gateway_service):
        """Test service initialization."""
        assert gateway_service.homeserver == 'https://matrix.example.com'
        assert gateway_service.user_id == '@bot:matrix.example.com'
        assert gateway_service.password == 'test_password'
        assert gateway_service.bot_display_name == "ChatBot"

    @pytest.mark.asyncio
    async def test_rate_limited_matrix_call_success(self, gateway_service):
        """Test successful rate limited matrix call."""
        mock_func = AsyncMock(return_value="success")
        
        result = await gateway_service._rate_limited_matrix_call(mock_func, "arg1", kwarg1="kwarg1")
        
        assert result == "success"
        mock_func.assert_called_once_with("arg1", kwarg1="kwarg1")

    @pytest.mark.asyncio
    async def test_rate_limited_matrix_call_429_with_retry_after(self, gateway_service):
        """Test rate limited call with 429 status and retry after."""
        mock_func = AsyncMock()
        
        # First call raises 429, second succeeds
        rate_limit_error = Exception("Rate limited")
        rate_limit_error.status_code = 429
        rate_limit_error.retry_after_ms = 100  # 0.1 seconds
        
        mock_func.side_effect = [rate_limit_error, "success"]
        
        with patch('asyncio.sleep') as mock_sleep:
            result = await gateway_service._rate_limited_matrix_call(mock_func)
        
        assert result == "success"
        assert mock_func.call_count == 2
        mock_sleep.assert_called_once_with(0.1)

    @pytest.mark.asyncio
    async def test_rate_limited_matrix_call_429_string_match(self, gateway_service):
        """Test rate limited call with 429 in error message."""
        mock_func = AsyncMock()
        
        # First call raises error with 429 in message, second succeeds
        rate_limit_error = Exception("429 Too Many Requests")
        mock_func.side_effect = [rate_limit_error, "success"]
        
        with patch('asyncio.sleep') as mock_sleep:
            result = await gateway_service._rate_limited_matrix_call(mock_func)
        
        assert result == "success"
        assert mock_func.call_count == 2
        mock_sleep.assert_called_once_with(10.0)  # Default retry

    @pytest.mark.asyncio
    async def test_rate_limited_matrix_call_non_429_error(self, gateway_service):
        """Test rate limited call with non-429 error."""
        mock_func = AsyncMock()
        mock_func.side_effect = Exception("Some other error")
        
        with pytest.raises(Exception, match="Some other error"):
            await gateway_service._rate_limited_matrix_call(mock_func)

    @pytest.mark.asyncio
    async def test_command_worker(self, gateway_service):
        """Test the command worker processes commands."""
        # Start the worker
        worker_task = asyncio.create_task(gateway_service._command_worker())
        
        # Add a command
        mock_func = AsyncMock()
        await gateway_service._enqueue_command(mock_func, "arg1", kwarg1="kwarg1")
        
        # Give time to process
        await asyncio.sleep(0.1)
        
        # Stop the worker
        gateway_service._stop_event.set()
        await worker_task
        
        mock_func.assert_called_once_with("arg1", kwarg1="kwarg1")

    @pytest.mark.asyncio
    async def test_command_worker_error_handling(self, gateway_service):
        """Test command worker handles errors gracefully."""
        # Start the worker
        worker_task = asyncio.create_task(gateway_service._command_worker())
        
        # Add a command that raises an error
        mock_func = AsyncMock(side_effect=Exception("Test error"))
        await gateway_service._enqueue_command(mock_func)
        
        # Give time to process
        await asyncio.sleep(0.1)
        
        # Stop the worker
        gateway_service._stop_event.set()
        await worker_task
        
        # Worker should have handled the error and continued

    @pytest.mark.asyncio
    async def test_matrix_message_callback_own_message(self, gateway_service, mock_matrix_client):
        """Test that bot ignores its own messages."""
        room = MagicMock()
        room.room_id = "!test:matrix.example.com"
        
        event = MagicMock()
        event.sender = "@bot:matrix.example.com"
        event.body = "Test message"
        
        await gateway_service._matrix_message_callback(room, event)
        
        # Should not publish any events
        self.assert_no_events_published()

    @pytest.mark.asyncio
    async def test_matrix_message_callback_other_user(self, gateway_service, mock_matrix_client):
        """Test handling message from other user."""
        room = MagicMock()
        room.room_id = "!test:matrix.example.com"
        room.display_name = "Test Room"
        room.user_name = MagicMock(return_value="User Display")
        
        event = MagicMock()
        event.sender = "@user:matrix.example.com"
        event.body = "  Test message  "
        event.event_id = "$event:matrix.example.com"
        
        await gateway_service._matrix_message_callback(room, event)
        
        # Should publish MatrixMessageReceivedEvent
        events = self.mock_bus.get_published_events_of_type(MatrixMessageReceivedEvent)
        assert len(events) == 1
        assert events[0].body == "Test message"  # Stripped
        assert events[0].sender_display_name == "User Display"

    @pytest.mark.asyncio
    async def test_matrix_image_callback(self, gateway_service, mock_matrix_client):
        """Test handling image message."""
        room = MagicMock()
        room.room_id = "!test:matrix.example.com"
        room.display_name = "Test Room"
        room.user_name = MagicMock(return_value="User Display")
        
        event = MagicMock()
        event.sender = "@user:matrix.example.com"
        event.event_id = "$event:matrix.example.com"
        event.url = "mxc://matrix.example.com/image123"
        event.body = "Image description"
        event.server_timestamp = 1234567890
        event.content = {
            "info": {
                "mimetype": "image/jpeg",
                "size": 12345,
                "w": 800,
                "h": 600
            },
            "filename": "test.jpg"
        }
        
        await gateway_service._matrix_image_callback(room, event)
        
        # Should publish MatrixImageReceivedEvent
        events = self.mock_bus.get_published_events_of_type(MatrixImageReceivedEvent)
        assert len(events) == 1
        assert events[0].image_url == "mxc://matrix.example.com/image123"
        assert events[0].image_info["mimetype"] == "image/jpeg"

    @pytest.mark.asyncio
    async def test_handle_send_message_command(self, gateway_service):
        """Test handling send message command."""
        command = SendMatrixMessageCommandFactory(
            room_id="!test:matrix.example.com",
            text="Test message"
        )
        
        await gateway_service._handle_send_message_command(command)
        
        # Command should be queued
        assert not gateway_service._command_queue.empty()

    @pytest.mark.asyncio
    async def test_send_message_impl_plain_text(self, gateway_service, mock_matrix_client):
        """Test sending plain text message."""
        command = SendMatrixMessageCommandFactory(
            room_id="!test:matrix.example.com",
            text="Simple message"
        )
        
        await gateway_service._send_message_impl(command)
        
        mock_matrix_client.room_send.assert_called_once()
        call_args = mock_matrix_client.room_send.call_args
        assert call_args[1]["room_id"] == "!test:matrix.example.com"
        assert call_args[1]["content"]["body"] == "Simple message"

    @pytest.mark.asyncio
    async def test_send_message_impl_markdown(self, gateway_service, mock_matrix_client):
        """Test sending markdown message."""
        command = SendMatrixMessageCommandFactory(
            room_id="!test:matrix.example.com",
            text="**Bold** text"
        )
        
        await gateway_service._send_message_impl(command)
        
        mock_matrix_client.room_send.assert_called_once()
        call_args = mock_matrix_client.room_send.call_args
        content = call_args[1]["content"]
        assert content["body"] == "**Bold** text"
        assert "formatted_body" in content
        assert content["format"] == "org.matrix.custom.html"

    @pytest.mark.asyncio
    async def test_send_message_impl_markdown_error(self, gateway_service, mock_matrix_client):
        """Test handling markdown conversion error."""
        command = SendMatrixMessageCommandFactory(
            room_id="!test:matrix.example.com",
            text="Test message"
        )
        
        with patch('markdown.markdown', side_effect=Exception("Markdown error")):
            await gateway_service._send_message_impl(command)
        
        # Should fall back to plain text
        mock_matrix_client.room_send.assert_called_once()
        call_args = mock_matrix_client.room_send.call_args
        content = call_args[1]["content"]
        assert "formatted_body" not in content

    @pytest.mark.asyncio
    async def test_send_message_impl_no_client(self, gateway_service):
        """Test sending message with no client."""
        gateway_service.client = None
        
        command = SendMatrixMessageCommandFactory()
        await gateway_service._send_message_impl(command)
        
        # Should log error but not crash

    @pytest.mark.asyncio
    async def test_react_to_message_impl(self, gateway_service, mock_matrix_client):
        """Test reacting to message."""
        command = ReactToMessageCommandFactory(
            room_id="!test:matrix.example.com",
            event_id_to_react_to="$event:matrix.example.com",
            reaction_key="👍"
        )
        
        await gateway_service._react_to_message_impl(command)
        
        mock_matrix_client.room_send.assert_called_once()
        call_args = mock_matrix_client.room_send.call_args
        content = call_args[1]["content"]
        assert content["m.relates_to"]["event_id"] == "$event:matrix.example.com"
        assert content["m.relates_to"]["key"] == "👍"

    @pytest.mark.asyncio
    async def test_send_reply_impl_with_original_event(self, gateway_service, mock_matrix_client):
        """Test sending reply with original event fetched."""
        command = SendReplyCommandFactory(
            room_id="!test:matrix.example.com",
            reply_to_event_id="$original:matrix.example.com",
            text="Reply text",
            event_id="$reply:matrix.example.com"
        )
        
        # Mock the original event response
        original_event = MagicMock()
        original_event.sender = "@user:matrix.example.com"
        original_event.body = "Original message"
        
        event_response = MagicMock()
        event_response.event = original_event
        
        from nio import RoomGetEventResponse
        mock_matrix_client.room_get_event.return_value = event_response
        type(event_response).__class__ = RoomGetEventResponse
        
        await gateway_service._send_reply_impl(command)
        
        mock_matrix_client.room_send.assert_called_once()
        call_args = mock_matrix_client.room_send.call_args
        content = call_args[1]["content"]
        assert "m.relates_to" in content
        assert content["m.relates_to"]["m.in_reply_to"]["event_id"] == "$original:matrix.example.com"

    @pytest.mark.asyncio
    async def test_send_reply_impl_event_fetch_error(self, gateway_service, mock_matrix_client):
        """Test sending reply when original event fetch fails."""
        command = SendReplyCommandFactory(
            room_id="!test:matrix.example.com",
            reply_to_event_id="$original:matrix.example.com",
            text="Reply text"
        )
        
        from nio import RoomGetEventError
        error_response = RoomGetEventError("Event not found", 404)
        mock_matrix_client.room_get_event.return_value = error_response
        
        await gateway_service._send_reply_impl(command)
        
        mock_matrix_client.room_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_request_room_info_success(self, gateway_service, mock_matrix_client):
        """Test successful room info request."""
        command = RequestMatrixRoomInfoCommandFactory(
            room_id="!test:matrix.example.com",
            aspects=["name", "topic", "members"],
            event_id="$request:matrix.example.com",
            original_tool_call_id="call_123",
            turn_request_id="turn_456"
        )
        
        # Mock state event responses
        name_response = MagicMock()
        name_response.name = "Test Room"
        
        topic_response = MagicMock()
        topic_response.topic = "Test topic"
        
        members_response = MagicMock()
        members_response.members = {"@user1:example.com": {}, "@user2:example.com": {}}
        
        mock_matrix_client.room_get_state_event.side_effect = [name_response, topic_response]
        mock_matrix_client.joined_members.return_value = members_response
        
        await gateway_service._handle_request_room_info(command)
        
        # Should publish response event
        events = self.mock_bus.get_published_events_of_type(MatrixRoomInfoResponseEvent)
        assert len(events) == 1
        assert events[0].success is True
        assert events[0].info["name"] == "Test Room"
        assert events[0].info["topic"] == "Test topic"
        assert len(events[0].info["members"]) == 2

    @pytest.mark.asyncio
    async def test_handle_request_room_info_no_client(self, gateway_service):
        """Test room info request with no client."""
        gateway_service.client = None
        
        command = RequestMatrixRoomInfoCommandFactory()
        
        await gateway_service._handle_request_room_info(command)
        
        events = self.mock_bus.get_published_events_of_type(MatrixRoomInfoResponseEvent)
        assert len(events) == 1
        assert events[0].success is False
        assert "not ready" in events[0].error_message

    @pytest.mark.asyncio
    async def test_set_typing_impl(self, gateway_service, mock_matrix_client):
        """Test setting typing indicator."""
        command = SetTypingIndicatorCommandFactory(
            room_id="!test:matrix.example.com",
            typing=True,
            timeout=30000
        )
        
        await gateway_service._set_typing_impl(command)
        
        mock_matrix_client.room_typing.assert_called_once_with(
            room_id="!test:matrix.example.com",
            typing_state=True,
            timeout=30000
        )

    @pytest.mark.asyncio
    async def test_set_presence_impl(self, gateway_service, mock_matrix_client):
        """Test setting presence."""
        command = SetPresenceCommandFactory(
            presence="online",
            status_msg="Available"
        )
        
        await gateway_service._set_presence_impl(command)
        
        mock_matrix_client.set_presence.assert_called_once_with(
            presence="online",
            status_msg="Available"
        )

    @pytest.mark.asyncio
    async def test_run_missing_credentials(self):
        """Test run with missing credentials."""
        with patch.dict(os.environ, {}, clear=True):
            service = MatrixGatewayService(message_bus=MockMessageBus())
            await service.run()
            # Should exit early due to missing credentials

    @pytest.mark.asyncio
    async def test_run_password_login_success(self):
        """Test successful password login."""
        with patch.dict(os.environ, {
            'MATRIX_HOMESERVER': 'https://matrix.example.com',
            'MATRIX_USER_ID': '@bot:matrix.example.com',
            'MATRIX_PASSWORD': 'test_password'
        }):
            service = MatrixGatewayService(message_bus=MockMessageBus())
            
            mock_client = AsyncMock()
            mock_client.user_id = "@bot:matrix.example.com"
            mock_client.device_id = "test_device"
            mock_client.access_token = "test_token"
            mock_client.logged_in = True
            
            # Mock login response
            from nio import LoginResponse
            login_response = LoginResponse()
            mock_client.login.return_value = login_response
            
            # Mock profile response
            from nio import ProfileGetResponse
            profile_response = ProfileGetResponse()
            profile_response.displayname = "Test Bot"
            mock_client.get_profile.return_value = profile_response
            
            with patch('matrix_gateway_service.AsyncClient', return_value=mock_client):
                # Start service
                run_task = asyncio.create_task(service.run())
                
                # Give time to initialize
                await asyncio.sleep(0.1)
                
                # Stop service
                await service.stop()
                
                # Wait for completion
                try:
                    await asyncio.wait_for(run_task, timeout=1.0)
                except asyncio.TimeoutError:
                    run_task.cancel()

    @pytest.mark.asyncio
    async def test_run_token_auth_success(self):
        """Test successful token authentication."""
        with patch.dict(os.environ, {
            'MATRIX_HOMESERVER': 'https://matrix.example.com',
            'MATRIX_USER_ID': '@bot:matrix.example.com',
            'MATRIX_ACCESS_TOKEN': 'test_token',
            'MATRIX_DEVICE_ID': 'test_device'
        }):
            service = MatrixGatewayService(message_bus=MockMessageBus())
            
            mock_client = AsyncMock()
            mock_client.user_id = "@bot:matrix.example.com"
            mock_client.logged_in = True
            
            # Mock whoami response
            from nio import WhoamiResponse
            whoami_response = WhoamiResponse()
            whoami_response.user_id = "@bot:matrix.example.com"
            whoami_response.device_id = "test_device"
            mock_client.whoami.return_value = whoami_response
            
            with patch('matrix_gateway_service.AsyncClient', return_value=mock_client):
                # Start service
                run_task = asyncio.create_task(service.run())
                
                # Give time to initialize
                await asyncio.sleep(0.1)
                
                # Stop service
                await service.stop()
                
                try:
                    await asyncio.wait_for(run_task, timeout=1.0)
                except asyncio.TimeoutError:
                    run_task.cancel()

    @pytest.mark.asyncio
    async def test_get_client(self, gateway_service, mock_matrix_client):
        """Test getting the matrix client."""
        assert gateway_service.get_client() == mock_matrix_client