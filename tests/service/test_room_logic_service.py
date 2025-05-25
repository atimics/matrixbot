"""Comprehensive tests for the RoomLogicService."""

import pytest
import pytest_asyncio
import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from room_logic_service import RoomLogicService
from tests.test_utils import ServiceTestBase, MockMessageBus, create_mock_tool_registry, create_sample_conversation_history
from tests.factories import (
    MatrixMessageReceivedEventFactory,
    AIInferenceResponseEventFactory,
    ActivateListeningEventFactory,
    BotDisplayNameReadyEventFactory
)
from event_definitions import (
    MatrixMessageReceivedEvent,
    AIInferenceResponseEvent,
    ActivateListeningEvent,
    BotDisplayNameReadyEvent,
    ProcessMessageBatchCommand,
    SendMatrixMessageCommand,
    SendReplyCommand,
    SetTypingIndicatorCommand,
    OpenRouterInferenceRequestEvent,
    OllamaInferenceRequestEvent
)


@pytest.mark.unit
class TestRoomLogicService(ServiceTestBase):
    """Test the RoomLogicService functionality."""

    @pytest_asyncio.fixture
    async def room_logic_service(self):
        """Create a RoomLogicService instance for testing."""
        # Create database asynchronously for fixture
        import tempfile
        import os
        from database import initialize_database
        
        # Create temporary database
        db_fd, db_path = tempfile.mkstemp(suffix='.db')
        os.close(db_fd)
        await initialize_database(db_path)
        
        tool_registry = create_mock_tool_registry()
        
        service = RoomLogicService(
            message_bus=self.mock_bus,
            tool_registry=tool_registry,
            db_path=db_path,
            bot_display_name="TestBot",
            matrix_client=self.mock_client
        )
        
        # Clean up database after test
        yield service
        
        try:
            os.unlink(db_path)
        except OSError:
            pass

    @pytest.mark.asyncio
    async def test_initialization(self, room_logic_service):
        """Test service initialization."""
        service = room_logic_service
        
        assert service.bus == self.mock_bus
        assert service.bot_display_name == "TestBot"
        assert service.matrix_client == self.mock_client
        assert service.room_activity_config == {}
        assert service.pending_tool_calls_for_ai_turn == {}

    @pytest.mark.asyncio
    async def test_bot_display_name_ready_event(self, room_logic_service):
        """Test handling of BotDisplayNameReadyEvent."""
        service = room_logic_service
        
        event = BotDisplayNameReadyEventFactory(
            display_name="UpdatedBot",
            user_id="@bot:matrix.example.com"
        )
        
        await service._handle_bot_display_name_ready(event)
        
        assert service.bot_display_name == "UpdatedBot"

    @pytest.mark.asyncio
    async def test_matrix_message_mention_detection(self, room_logic_service):
        """Test that mentions of the bot are detected and activate listening."""
        service = room_logic_service
        
        # Message with bot mention
        event = MatrixMessageReceivedEventFactory(
            body="Hello TestBot, how are you?",
            room_id=self.test_room_id
        )
        
        await service._handle_matrix_message(event)
        
        # Should publish ActivateListeningEvent
        activate_events = self.mock_bus.get_published_events_of_type(ActivateListeningEvent)
        assert len(activate_events) == 1
        assert activate_events[0].room_id == self.test_room_id

    @pytest.mark.asyncio
    async def test_matrix_message_without_mention(self, room_logic_service):
        """Test that messages without bot mention don't activate listening when not active."""
        service = room_logic_service
        
        # Message without bot mention
        event = MatrixMessageReceivedEventFactory(
            body="Hello everyone!",
            room_id=self.test_room_id
        )
        
        await service._handle_matrix_message(event)
        
        # Should not publish any events
        self.assert_no_events_published()

    @pytest.mark.asyncio
    async def test_activate_listening_event(self, room_logic_service):
        """Test handling of ActivateListeningEvent."""
        service = room_logic_service
        
        event = ActivateListeningEventFactory(room_id=self.test_room_id)
        
        await service._handle_activate_listening(event)
        
        # Should create room config and set active listening
        assert self.test_room_id in service.room_activity_config
        config = service.room_activity_config[self.test_room_id]
        assert config['is_active_listening'] is True
        assert len(config['pending_messages_for_batch']) == 1

    @pytest.mark.asyncio
    async def test_message_batching_when_active(self, room_logic_service):
        """Test that messages are batched when room is actively listening."""
        service = room_logic_service
        
        # First activate listening
        activate_event = ActivateListeningEventFactory(room_id=self.test_room_id)
        await service._handle_activate_listening(activate_event)
        
        # Send a message
        message_event = MatrixMessageReceivedEventFactory(
            body="This is a test message",
            room_id=self.test_room_id
        )
        
        await service._handle_matrix_message(message_event)
        
        # Should be added to batch
        config = service.room_activity_config[self.test_room_id]
        assert len(config['pending_messages_for_batch']) == 2  # Activation message + new message

    @patch('room_logic_service.prompt_constructor.build_messages_for_ai')
    @pytest.mark.asyncio
    async def test_ai_response_handling_text_response(self, mock_build_messages, room_logic_service):
        """Test handling of AI response with text content."""
        service = room_logic_service
        
        # Setup room config
        service.room_activity_config[self.test_room_id] = {
            'is_active_listening': True,
            'memory': [],
            'pending_messages_for_batch': [],
            'new_turns_since_last_summary': 0
        }
        
        response_event = AIInferenceResponseEventFactory(
            success=True,
            text_response="This is the AI response",
            tool_calls=None,
            original_request_payload={
                'room_id': self.test_room_id,
                'last_user_event_id_in_batch': '$user_event:matrix.example.com',
                'pending_batch_for_memory': []
            }
        )
        
        await service._handle_ai_chat_response(response_event)
        
        # Should publish SendReplyCommand
        reply_commands = self.mock_bus.get_published_events_of_type(SendReplyCommand)
        assert len(reply_commands) == 1
        assert reply_commands[0].text == "This is the AI response"
        assert reply_commands[0].room_id == self.test_room_id

    @patch('room_logic_service.prompt_constructor.build_messages_for_ai')  
    @pytest.mark.asyncio
    async def test_ai_response_handling_tool_calls(self, mock_build_messages, room_logic_service):
        """Test handling of AI response with tool calls."""
        service = room_logic_service
        
        # Setup room config
        service.room_activity_config[self.test_room_id] = {
            'is_active_listening': True,
            'memory': [],
            'pending_messages_for_batch': [],
            'pending_tool_calls': {},
            'new_turns_since_last_summary': 0
        }
        
        # Create mock tool call
        from event_definitions import ToolCall, ToolFunction
        tool_call = ToolCall(
            id="call_123",
            type="function",
            function=ToolFunction(name="send_reply", arguments='{"text": "Tool response"}')
        )
        
        response_event = AIInferenceResponseEventFactory(
            success=True,
            text_response=None,
            tool_calls=[tool_call],
            original_request_payload={
                'room_id': self.test_room_id,
                'pending_batch_for_memory': []
            }
        )
        
        await service._handle_ai_chat_response(response_event)
        
        # Should track pending tool calls
        config = service.room_activity_config[self.test_room_id]
        assert "call_123" in config['pending_tool_calls']

    @patch('room_logic_service.prompt_constructor.build_messages_for_ai')
    @pytest.mark.asyncio
    async def test_process_message_batch_openrouter(self, mock_build_messages, room_logic_service):
        """Test processing message batch with OpenRouter provider."""
        service = room_logic_service
        service.primary_llm_provider = "openrouter"
        
        # Setup room config with active listening - THIS WAS MISSING
        service.room_activity_config[self.test_room_id] = {
            'is_active_listening': True,
            'memory': [],
            'pending_messages_for_batch': [],
            'new_turns_since_last_summary': 0
        }
        
        command = ProcessMessageBatchCommand(
            room_id=self.test_room_id,
            messages_in_batch=[{
                'user_id': '@test:matrix.example.com',
                'content': 'Hello bot',
                'event_id': '$test:matrix.example.com'
            }]
        )
        
        mock_build_messages.return_value = [{"role": "user", "content": "Test prompt"}]
        
        await service._handle_process_message_batch(command)
        
        # Should publish OpenRouterInferenceRequestEvent
        inference_requests = self.mock_bus.get_published_events_of_type(OpenRouterInferenceRequestEvent)
        assert len(inference_requests) == 1
        assert inference_requests[0].original_request_payload["room_id"] == self.test_room_id

    @patch('room_logic_service.prompt_constructor.build_messages_for_ai')
    @pytest.mark.asyncio
    async def test_process_message_batch_ollama(self, mock_build_messages, room_logic_service):
        """Test processing message batch with Ollama provider."""
        service = room_logic_service
        service.primary_llm_provider = "ollama"
        
        # Setup room config with active listening - THIS WAS MISSING
        service.room_activity_config[self.test_room_id] = {
            'is_active_listening': True,
            'memory': [],
            'pending_messages_for_batch': [],
            'new_turns_since_last_summary': 0
        }
        
        command = ProcessMessageBatchCommand(
            room_id=self.test_room_id,
            messages_in_batch=[{
                'user_id': '@test:matrix.example.com',
                'content': 'Hello bot',
                'event_id': '$test:matrix.example.com'
            }]
        )
        
        mock_build_messages.return_value = [{"role": "user", "content": "Test prompt"}]
        
        await service._handle_process_message_batch(command)
        
        # Should publish OllamaInferenceRequestEvent
        inference_requests = self.mock_bus.get_published_events_of_type(OllamaInferenceRequestEvent)
        assert len(inference_requests) == 1

    @pytest.mark.asyncio
    async def test_typing_indicator_management(self, room_logic_service):
        """Test that typing indicators are properly managed."""
        service = room_logic_service
        
        # Setup room config
        service.room_activity_config[self.test_room_id] = {
            'is_active_listening': True,
            'memory': [],
            'pending_messages_for_batch': [],
            'new_turns_since_last_summary': 0
        }
        
        # Process a batch (should turn on typing)
        command = ProcessMessageBatchCommand(
            room_id=self.test_room_id,
            messages_in_batch=[{
                'user_id': '@test:matrix.example.com',
                'content': 'Hello',
                'event_id': '$test:matrix.example.com'
            }]
        )
        
        with patch('room_logic_service.prompt_constructor.build_messages_for_ai') as mock_build:
            mock_build.return_value = [{"role": "user", "content": "Test"}]
            
            await service._handle_process_message_batch(command)
        
        # Should set typing indicator on
        typing_commands = self.mock_bus.get_published_events_of_type(SetTypingIndicatorCommand)
        typing_on_commands = [cmd for cmd in typing_commands if cmd.typing is True]
        assert len(typing_on_commands) >= 1

    @patch('room_logic_service.prompt_constructor.build_summary_generation_payload')
    @pytest.mark.asyncio
    async def test_memory_management(self, mock_build_summary, room_logic_service):
        """Test that conversation memory is properly managed."""
        service = room_logic_service
        service.short_term_memory_items = 3  # Small limit for testing
        
        # Mock the summary generation to avoid bot_display_name KeyError
        mock_build_summary.return_value = [{"role": "user", "content": "Test summary prompt"}]
        
        # Setup room with NO existing memory to test trimming properly
        service.room_activity_config[self.test_room_id] = {
            'is_active_listening': True,
            'memory': [],  # Start with empty memory
            'pending_messages_for_batch': [],
            'new_turns_since_last_summary': 0
        }
        
        # Add several messages to exceed the limit
        for i in range(5):  # Add 5 messages, limit is 3
            response_event = AIInferenceResponseEventFactory(
                success=True,
                text_response=f"Response {i}",
                original_request_payload={
                    'room_id': self.test_room_id,
                    'pending_batch_for_memory': [{
                        'name': f'User{i}',
                        'content': f'Message {i}',
                        'event_id': f'$msg{i}:matrix.example.com'
                    }]
                }
            )
            
            await service._handle_ai_chat_response(response_event)
        
        # Memory should be trimmed to limit
        config = service.room_activity_config[self.test_room_id]
        assert len(config['memory']) <= service.short_term_memory_items

    @pytest.mark.asyncio
    async def test_historical_message_filtering(self, room_logic_service):
        """Test that historical messages are filtered out."""
        service = room_logic_service
        
        # Create an old message (before service start time)
        old_timestamp = service._service_start_time.timestamp() - 3600  # 1 hour ago
        
        old_event = MatrixMessageReceivedEventFactory(
            body="Old message",
            room_id=self.test_room_id,
            timestamp=old_timestamp
        )
        
        await service._handle_matrix_message(old_event)
        
        # Should not process old messages
        self.assert_no_events_published()

    @pytest.mark.asyncio
    async def test_error_handling_in_ai_response(self, room_logic_service):
        """Test error handling when AI response fails."""
        service = room_logic_service
        
        # Setup room config
        service.room_activity_config[self.test_room_id] = {
            'is_active_listening': True,
            'memory': [],
            'pending_messages_for_batch': [],
            'new_turns_since_last_summary': 0
        }
        
        # Failed AI response
        response_event = AIInferenceResponseEventFactory(
            success=False,
            text_response=None,
            error_message="AI service failed",
            original_request_payload={'room_id': self.test_room_id}
        )
        
        await service._handle_ai_chat_response(response_event)
        
        # Should still turn off typing indicator
        typing_commands = self.mock_bus.get_published_events_of_type(SetTypingIndicatorCommand)
        typing_off_commands = [cmd for cmd in typing_commands if cmd.typing is False]
        assert len(typing_off_commands) >= 1

    @pytest.mark.asyncio
    async def test_service_run_and_stop(self, room_logic_service):
        """Test service run loop and stopping."""
        service = room_logic_service
        
        # Start service in background
        run_task = asyncio.create_task(service.run())
        
        # Give it time to set up subscriptions
        await asyncio.sleep(0.1)
        
        # Stop the service
        await service.stop()
        
        # Wait for run task to complete
        try:
            await asyncio.wait_for(run_task, timeout=1.0)
        except asyncio.TimeoutError:
            run_task.cancel()
            pytest.fail("Service did not stop within timeout")


@pytest.mark.integration
class TestRoomLogicServiceIntegration:
    """Integration tests for RoomLogicService with real components."""

    @pytest.mark.asyncio
    async def test_full_conversation_flow(self):
        """Test a complete conversation flow from message to AI response."""
        from tests.test_utils import DatabaseTestHelper
        
        # Create real components
        mock_bus = MockMessageBus()
        db_path = await DatabaseTestHelper.create_test_database()
        tool_registry = create_mock_tool_registry()
        
        service = RoomLogicService(
            message_bus=mock_bus,
            tool_registry=tool_registry,
            db_path=db_path,
            bot_display_name="TestBot"
        )
        
        room_id = "!test:matrix.example.com"
        
        # 1. Bot mention to activate listening
        mention_event = MatrixMessageReceivedEventFactory(
            body="Hello TestBot!",
            room_id=room_id
        )
        
        await service._handle_matrix_message(mention_event)
        
        # Should activate listening
        activate_events = mock_bus.get_published_events_of_type(ActivateListeningEvent)
        assert len(activate_events) == 1
        
        # 2. Handle the activation
        await service._handle_activate_listening(activate_events[0])
        
        # 3. Send follow-up message
        message_event = MatrixMessageReceivedEventFactory(
            body="How are you?",
            room_id=room_id
        )
        
        await service._handle_matrix_message(message_event)
        
        # 4. Process the batch (after delay simulation)
        config = service.room_activity_config[room_id]
        
        # Convert pending messages to BatchedUserMessage format
        messages_in_batch = []
        for msg in config['pending_messages_for_batch']:
            messages_in_batch.append({
                'user_id': msg.get('sender_id', '@test:matrix.example.com'),
                'content': msg.get('content', msg.get('body', '')),
                'event_id': msg.get('event_id', '$test:matrix.example.com')
            })
        
        command = ProcessMessageBatchCommand(
            room_id=room_id,
            messages_in_batch=messages_in_batch
        )
        
        with patch('room_logic_service.prompt_constructor.build_messages_for_ai') as mock_build:
            mock_build.return_value = [{"role": "user", "content": "Combined messages"}]
            
            await service._handle_process_message_batch(command)
        
        # Should publish AI inference request
        inference_requests = mock_bus.get_published_events_of_type(OpenRouterInferenceRequestEvent)
        assert len(inference_requests) == 1
        
        # 5. Simulate AI response
        ai_response = AIInferenceResponseEventFactory(
            success=True,
            text_response="I'm doing well, thank you!",
            original_request_payload=inference_requests[0].original_request_payload
        )
        
        await service._handle_ai_chat_response(ai_response)
        
        # Should publish reply command
        reply_commands = mock_bus.get_published_events_of_type(SendReplyCommand)
        assert len(reply_commands) == 1
        assert "I'm doing well" in reply_commands[0].text
        
        # Cleanup
        DatabaseTestHelper.cleanup_database(db_path)
