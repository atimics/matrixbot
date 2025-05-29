import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from faker import Faker

from action_execution_service import ActionExecutionService
from action_registry_service import ActionRegistryService
from message_bus import MessageBus
from event_definitions import (
    AIAction, ChannelResponse, AIResponsePlan,
    ActionExecutionRequestEvent, ActionExecutionResponseEvent,
    SendMatrixMessageCommand, SendReplyCommand, ReactToMessageCommand
)

fake = Faker()

@pytest.fixture
def mock_message_bus():
    """Provide a mock message bus for testing."""
    mock_bus = MagicMock(spec=MessageBus)
    mock_bus.publish = AsyncMock()
    mock_bus.subscribe = AsyncMock()
    return mock_bus

@pytest.fixture
def mock_action_registry():
    """Provide a mock action registry."""
    mock_registry = MagicMock(spec=ActionRegistryService)
    # Mock some basic action definitions
    mock_registry.get_action_definition.return_value = {
        "name": "test_action",
        "description": "Test action",
        "parameters": {}
    }
    return mock_registry

@pytest.fixture
def mock_farcaster_service():
    """Provide a mock farcaster service."""
    mock_service = MagicMock()
    mock_service.post_cast = AsyncMock(return_value={"success": True, "cast_hash": "0x123"})
    mock_service.get_home_feed = AsyncMock(return_value={"success": True, "count": 5})
    mock_service.like_cast = AsyncMock(return_value={"success": True})
    mock_service.reply_to_cast = AsyncMock(return_value={"success": True, "reply_hash": "0x456"})
    mock_service.get_notifications = AsyncMock(return_value={"success": True, "count": 3, "mentions_summary": "2 mentions"})
    return mock_service

@pytest.fixture
def action_execution_service(mock_message_bus, mock_action_registry, tmp_path):
    """Create an ActionExecutionService instance for testing."""
    db_path = str(tmp_path / "test.db")
    service = ActionExecutionService(mock_message_bus, mock_action_registry, db_path)
    return service

class TestActionExecutionService:
    """Test suite for ActionExecutionService."""

    @pytest.mark.asyncio
    async def test_initialization(self, action_execution_service):
        """Test service initialization."""
        assert action_execution_service.bus is not None
        assert action_execution_service.action_registry is not None
        assert action_execution_service.db_path is not None
        assert not action_execution_service._stop_event.is_set()

    @pytest.mark.asyncio
    async def test_run_and_stop(self, action_execution_service):
        """Test service run and stop lifecycle."""
        # Start the service in the background
        run_task = asyncio.create_task(action_execution_service.run())
        
        # Allow some time for initialization
        await asyncio.sleep(0.1)
        
        # Verify subscriptions were made
        action_execution_service.bus.subscribe.assert_any_call(
            "action_execution_request", 
            action_execution_service._handle_action_execution_request
        )
        action_execution_service.bus.subscribe.assert_any_call(
            "update_farcaster_channel", 
            action_execution_service._handle_update_farcaster_channel
        )
        action_execution_service.bus.subscribe.assert_any_call(
            "view_channel_context", 
            action_execution_service._handle_view_channel_context
        )
        
        # Stop the service
        await action_execution_service.stop()
        await run_task

    @pytest.mark.asyncio
    async def test_execute_action_plan_success(self, action_execution_service):
        """Test successful execution of an action plan."""
        # Create test action plan
        action = AIAction(action_name="send_message_text", parameters={"text": "Test message"})
        channel_response = ChannelResponse(channel_id="!test:matrix.org", actions=[action])
        action_plan = AIResponsePlan(channel_responses=[channel_response])
        
        # Execute the plan
        results = await action_execution_service.execute_action_plan(action_plan)
        
        # Verify results
        assert results["overall_success"] is True
        assert len(results["channel_results"]) == 1
        assert results["channel_results"][0]["channel_id"] == "!test:matrix.org"
        assert len(results["channel_results"][0]["action_results"]) == 1
        
        # Verify message was published
        action_execution_service.bus.publish.assert_called()

    @pytest.mark.asyncio
    async def test_execute_unknown_action(self, action_execution_service):
        """Test execution of unknown action."""
        # Mock registry to return None for unknown action
        action_execution_service.action_registry.get_action_definition.return_value = None
        
        action = AIAction(action_name="unknown_action", parameters={})
        
        result = await action_execution_service._execute_single_action(
            "!test:matrix.org", action, "test_request_id"
        )
        
        assert result["success"] is False
        assert "Unknown action: unknown_action" in result["error"]

    # Matrix Action Tests
    @pytest.mark.asyncio
    async def test_execute_send_message_text_success(self, action_execution_service):
        """Test successful send_message_text action."""
        parameters = {"text": "Hello, world!"}
        
        result = await action_execution_service._execute_send_message_text(
            "!test:matrix.org", parameters, "test_request_id"
        )
        
        assert result["success"] is True
        assert "Sent message: Hello, world!" in result["result"]
        
        # Verify command was published
        action_execution_service.bus.publish.assert_called()
        call_args = action_execution_service.bus.publish.call_args[0][0]
        assert isinstance(call_args, SendMatrixMessageCommand)
        assert call_args.text == "Hello, world!"

    @pytest.mark.asyncio
    async def test_execute_send_message_text_missing_text(self, action_execution_service):
        """Test send_message_text action with missing text parameter."""
        parameters = {}
        
        result = await action_execution_service._execute_send_message_text(
            "!test:matrix.org", parameters, "test_request_id"
        )
        
        assert result["success"] is False
        assert "Missing required parameter: text" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_send_reply_text_success(self, action_execution_service):
        """Test successful send_reply_text action."""
        parameters = {"text": "Reply text", "reply_to_event_id": "$event123:matrix.org"}
        
        result = await action_execution_service._execute_send_reply_text(
            "!test:matrix.org", parameters, "test_request_id"
        )
        
        assert result["success"] is True
        assert "Sent reply: Reply text" in result["result"]
        
        # Verify reply command was published
        action_execution_service.bus.publish.assert_called()
        call_args = action_execution_service.bus.publish.call_args[0][0]
        assert isinstance(call_args, SendReplyCommand)
        assert call_args.text == "Reply text"
        assert call_args.reply_to_event_id == "$event123:matrix.org"

    @pytest.mark.asyncio
    async def test_execute_send_reply_text_without_reply_id(self, action_execution_service):
        """Test send_reply_text action without reply_to_event_id falls back to regular message."""
        parameters = {"text": "Regular message"}
        
        result = await action_execution_service._execute_send_reply_text(
            "!test:matrix.org", parameters, "test_request_id"
        )
        
        assert result["success"] is True
        
        # Verify regular message command was published
        call_args = action_execution_service.bus.publish.call_args[0][0]
        assert isinstance(call_args, SendMatrixMessageCommand)

    @pytest.mark.asyncio
    async def test_execute_react_to_message_success(self, action_execution_service):
        """Test successful react_to_message action."""
        parameters = {"event_id": "$event123:matrix.org", "emoji": "👍"}
        
        result = await action_execution_service._execute_react_to_message(
            "!test:matrix.org", parameters, "test_request_id"
        )
        
        assert result["success"] is True
        assert "Reacted with 👍 to message $event123:matrix.org" in result["result"]
        
        # Verify reaction command was published
        call_args = action_execution_service.bus.publish.call_args[0][0]
        assert isinstance(call_args, ReactToMessageCommand)
        assert call_args.reaction_key == "👍"

    @pytest.mark.asyncio
    async def test_execute_react_to_message_missing_parameters(self, action_execution_service):
        """Test react_to_message action with missing parameters."""
        parameters = {"event_id": "$event123:matrix.org"}  # Missing emoji
        
        result = await action_execution_service._execute_react_to_message(
            "!test:matrix.org", parameters, "test_request_id"
        )
        
        assert result["success"] is False
        assert "Missing required parameters: event_id and/or emoji" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_describe_image_success(self, action_execution_service):
        """Test successful describe_image action."""
        parameters = {"image_event_id": "$image123:matrix.org", "focus": "objects"}
        
        result = await action_execution_service._execute_describe_image(
            "!test:matrix.org", parameters, "test_request_id"
        )
        
        assert result["success"] is True
        assert "Generated image description for $image123:matrix.org" in result["result"]
        
        # Verify reply command was published with description
        call_args = action_execution_service.bus.publish.call_args[0][0]
        assert isinstance(call_args, SendReplyCommand)
        assert "$image123:matrix.org" in call_args.text
        assert "objects" in call_args.text

    @pytest.mark.asyncio
    async def test_execute_do_not_respond_success(self, action_execution_service):
        """Test successful do_not_respond action."""
        parameters = {"reason": "Message is spam"}
        
        result = await action_execution_service._execute_do_not_respond(
            "!test:matrix.org", parameters, "test_request_id"
        )
        
        assert result["success"] is True
        assert "No response action: Message is spam" in result["result"]

    @pytest.mark.asyncio
    async def test_execute_get_room_info_success(self, action_execution_service):
        """Test successful get_room_info action."""
        parameters = {"info_type": "basic"}
        
        result = await action_execution_service._execute_get_room_info(
            "!test:matrix.org", parameters, "test_request_id"
        )
        
        assert result["success"] is True
        assert "Room info requested for type 'basic'" in result["result"]

    @pytest.mark.asyncio
    async def test_execute_get_room_info_missing_type(self, action_execution_service):
        """Test get_room_info action with missing info_type."""
        parameters = {}
        
        result = await action_execution_service._execute_get_room_info(
            "!test:matrix.org", parameters, "test_request_id"
        )
        
        assert result["success"] is False
        assert "Missing required parameter: info_type" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_delegate_to_openrouter_success(self, action_execution_service):
        """Test successful delegate_to_openrouter action."""
        parameters = {"query": "What is the weather?", "model_preference": "gpt-4"}
        
        result = await action_execution_service._execute_delegate_to_openrouter(
            "!test:matrix.org", parameters, "test_request_id"
        )
        
        assert result["success"] is True
        assert "Delegated query to OpenRouter: What is the weather?" in result["result"]

    @pytest.mark.asyncio
    async def test_execute_manage_channel_summary_success(self, action_execution_service):
        """Test successful manage_channel_summary action."""
        parameters = {"action": "generate", "focus": "recent_activity"}
        
        result = await action_execution_service._execute_manage_channel_summary(
            "!test:matrix.org", parameters, "test_request_id"
        )
        
        assert result["success"] is True
        assert "Channel summary generate requested" in result["result"]

    @pytest.mark.asyncio
    async def test_execute_manage_system_prompt_get_current(self, action_execution_service):
        """Test get_current system prompt action."""
        with patch('database.get_prompt', new_callable=AsyncMock) as mock_get_prompt:
            mock_get_prompt.return_value = ("Current system prompt", None)
            
            parameters = {"action": "get_current"}
            
            result = await action_execution_service._execute_manage_system_prompt(
                "!test:matrix.org", parameters, "test_request_id"
            )
            
            assert result["success"] is True
            assert "Current system prompt: 'Current system prompt'" in result["result"]

    @pytest.mark.asyncio
    async def test_execute_manage_system_prompt_update(self, action_execution_service):
        """Test update system prompt action."""
        with patch('database.update_prompt', new_callable=AsyncMock) as mock_update_prompt:
            parameters = {"action": "update", "new_prompt_text": "New system prompt"}
            
            result = await action_execution_service._execute_manage_system_prompt(
                "!test:matrix.org", parameters, "test_request_id"
            )
            
            assert result["success"] is True
            assert "System prompt 'system_default' updated successfully" in result["result"]
            mock_update_prompt.assert_called_once()

    # Farcaster Action Tests
    @pytest.mark.asyncio
    async def test_execute_farcaster_post_cast_success(self, action_execution_service, mock_farcaster_service):
        """Test successful farcaster_post_cast action."""
        action_execution_service.farcaster_service = mock_farcaster_service
        
        parameters = {"text": "Hello Farcaster!", "channel_id": "dev"}
        
        result = await action_execution_service._execute_farcaster_post_cast(
            "!test:matrix.org", parameters, "test_request_id"
        )
        
        assert result["success"] is True
        assert "Posted cast: Hello Farcaster!" in result["result"]
        assert "0x123" in result["result"]

    @pytest.mark.asyncio
    async def test_execute_farcaster_post_cast_missing_text(self, action_execution_service):
        """Test farcaster_post_cast action with missing text."""
        parameters = {}
        
        result = await action_execution_service._execute_farcaster_post_cast(
            "!test:matrix.org", parameters, "test_request_id"
        )
        
        assert result["success"] is False
        assert "Missing required parameter: text" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_farcaster_get_home_feed_success(self, action_execution_service, mock_farcaster_service):
        """Test successful farcaster_get_home_feed action."""
        action_execution_service.farcaster_service = mock_farcaster_service
        
        parameters = {"limit": 10}
        
        result = await action_execution_service._execute_farcaster_get_home_feed(
            "!test:matrix.org", parameters, "test_request_id"
        )
        
        assert result["success"] is True
        assert "Retrieved 5 casts from home feed" in result["result"]

    @pytest.mark.asyncio
    async def test_execute_farcaster_like_cast_success(self, action_execution_service, mock_farcaster_service):
        """Test successful farcaster_like_cast action."""
        action_execution_service.farcaster_service = mock_farcaster_service
        
        parameters = {"target_cast_hash": "0xabc123"}
        
        result = await action_execution_service._execute_farcaster_like_cast(
            "!test:matrix.org", parameters, "test_request_id"
        )
        
        assert result["success"] is True
        assert "Liked cast 0xabc123" in result["result"]

    @pytest.mark.asyncio
    async def test_execute_farcaster_like_cast_missing_hash(self, action_execution_service):
        """Test farcaster_like_cast action with missing hash."""
        parameters = {}
        
        result = await action_execution_service._execute_farcaster_like_cast(
            "!test:matrix.org", parameters, "test_request_id"
        )
        
        assert result["success"] is False
        assert "Missing required parameter: target_cast_hash" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_farcaster_reply_to_cast_success(self, action_execution_service, mock_farcaster_service):
        """Test successful farcaster_reply_to_cast action."""
        action_execution_service.farcaster_service = mock_farcaster_service
        
        parameters = {"text": "Great point!", "parent_cast_hash": "0xdef456"}
        
        result = await action_execution_service._execute_farcaster_reply_to_cast(
            "!test:matrix.org", parameters, "test_request_id"
        )
        
        assert result["success"] is True
        assert "Replied to cast 0xdef456: Great point!" in result["result"]
        assert "0x456" in result["result"]

    @pytest.mark.asyncio
    async def test_execute_farcaster_reply_missing_params(self, action_execution_service):
        """Test farcaster_reply_to_cast action with missing parameters."""
        parameters = {"text": "Reply"}  # Missing parent_cast_hash
        
        result = await action_execution_service._execute_farcaster_reply_to_cast(
            "!test:matrix.org", parameters, "test_request_id"
        )
        
        assert result["success"] is False
        assert "Missing required parameter: parent_cast_hash" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_farcaster_get_notifications_success(self, action_execution_service, mock_farcaster_service):
        """Test successful farcaster_get_notifications action."""
        action_execution_service.farcaster_service = mock_farcaster_service
        
        parameters = {"limit": 20, "filter_types": ["mention"]}
        
        result = await action_execution_service._execute_farcaster_get_notifications(
            "!test:matrix.org", parameters, "test_request_id"
        )
        
        assert result["success"] is True
        assert "Retrieved 3 new notifications" in result["result"]
        assert "2 mentions" in result["result"]

    # Error Handling Tests
    @pytest.mark.asyncio
    async def test_action_execution_with_exception(self, action_execution_service):
        """Test action execution when an exception occurs."""
        # Mock the action registry to return None for unknown action
        action_execution_service.action_registry.get_action_definition.return_value = None
        
        action = AIAction(action_name="unknown_action", parameters={})
        
        result = await action_execution_service._execute_single_action(
            "!test:matrix.org", action, "test_request_id"
        )
        
        assert result["success"] is False
        assert "Unknown action: unknown_action" in result["error"]

    @pytest.mark.asyncio
    async def test_farcaster_service_failure(self, action_execution_service):
        """Test handling of Farcaster service failures."""
        # Mock Farcaster service to return failure
        mock_service = MagicMock()
        mock_service.post_cast = AsyncMock(return_value={"success": False, "error": "API error"})
        action_execution_service.farcaster_service = mock_service
        
        parameters = {"text": "Test cast"}
        
        result = await action_execution_service._execute_farcaster_post_cast(
            "!test:matrix.org", parameters, "test_request_id"
        )
        
        assert result["success"] is False
        assert "API error" in result["error"]

    # Event Handler Tests
    @pytest.mark.asyncio
    async def test_handle_action_execution_request(self, action_execution_service):
        """Test handling of action execution request events."""
        action = AIAction(action_name="send_message_text", parameters={"text": "Test"})
        request = ActionExecutionRequestEvent(
            channel_id="!test:matrix.org",
            action=action,
            event_id="request123"
        )
        
        await action_execution_service._handle_action_execution_request(request)
        
        # Verify response was published
        action_execution_service.bus.publish.assert_called()
        published_events = [call[0][0] for call in action_execution_service.bus.publish.call_args_list]
        response_events = [e for e in published_events if isinstance(e, ActionExecutionResponseEvent)]
        
        assert len(response_events) >= 1
        response = response_events[-1]  # Get the last response event
        assert response.channel_id == "!test:matrix.org"
        assert response.action_name == "send_message_text"

    @pytest.mark.asyncio
    async def test_handle_update_farcaster_channel_home(self, action_execution_service, mock_farcaster_service):
        """Test handling of Farcaster channel update for home feed."""
        action_execution_service.farcaster_service = mock_farcaster_service
        
        # Create mock event
        event = MagicMock()
        event.channel_type = "home"
        event.limit = 25
        
        await action_execution_service._handle_update_farcaster_channel(event)
        
        mock_farcaster_service.get_home_feed.assert_called_once_with(25)

    @pytest.mark.asyncio
    async def test_handle_update_farcaster_channel_notifications(self, action_execution_service, mock_farcaster_service):
        """Test handling of Farcaster channel update for notifications."""
        action_execution_service.farcaster_service = mock_farcaster_service
        
        # Create mock event
        event = MagicMock()
        event.channel_type = "notifications"
        event.limit = 20
        
        await action_execution_service._handle_update_farcaster_channel(event)
        
        mock_farcaster_service.get_notifications.assert_called_once_with(20)

    @pytest.mark.asyncio
    async def test_handle_view_channel_context(self, action_execution_service):
        """Test handling of channel context view requests."""
        # Mock unified channel manager
        mock_manager = MagicMock()
        mock_manager.get_channel_context = AsyncMock(return_value={
            "messages": [
                {
                    "timestamp": 1640995200,
                    "sender_display_name": "TestUser",
                    "content": "Hello world",
                    "message_type": "matrix_message",
                    "ai_has_replied": False
                }
            ]
        })
        action_execution_service.unified_channel_manager = mock_manager
        
        # Create mock event
        event = MagicMock()
        event.channel_id = "!test:matrix.org"
        event.limit = 50
        
        await action_execution_service._handle_view_channel_context(event)
        
        mock_manager.get_channel_context.assert_called_once_with("!test:matrix.org", 50)

    def test_format_channel_context_empty(self, action_execution_service):
        """Test formatting of empty channel context."""
        result = action_execution_service._format_channel_context([], "!test:matrix.org")
        
        assert "No messages found in channel !test:matrix.org" in result

    def test_format_channel_context_with_messages(self, action_execution_service):
        """Test formatting of channel context with messages."""
        messages = [
            {
                "timestamp": 1640995200,
                "sender_display_name": "TestUser",
                "content": "Hello world",
                "message_type": "matrix_message",
                "ai_has_replied": False
            },
            {
                "timestamp": 1640995260,
                "sender_display_name": "FCUser",
                "content": "Farcaster cast content",
                "message_type": "farcaster_cast",
                "ai_has_replied": True
            }
        ]
        
        result = action_execution_service._format_channel_context(messages, "!test:matrix.org")
        
        assert "=== Channel Context: !test:matrix.org ===" in result
        assert "[MATRIX] TestUser: Hello world" in result
        assert "[FC] FCUser: Farcaster cast content [AI-REPLIED]" in result

    @pytest.mark.asyncio
    async def test_system_prompt_parameter_normalization(self, action_execution_service):
        """Test parameter normalization for manage_system_prompt action."""
        with patch('database.get_prompt', new_callable=AsyncMock) as mock_get_prompt:
            mock_get_prompt.return_value = ("Test prompt", None)
            
            # Test legacy parameter names
            parameters = {"operation": "get"}
            
            result = await action_execution_service._execute_manage_system_prompt(
                "!test:matrix.org", parameters, "test_request_id"
            )
            
            assert result["success"] is True
            
        # Test new parameter names with new_content
        with patch('database.update_prompt', new_callable=AsyncMock) as mock_update_prompt:
            parameters = {"operation": "set", "new_content": "New prompt"}
            
            result = await action_execution_service._execute_manage_system_prompt(
                "!test:matrix.org", parameters, "test_request_id"
            )
            
            assert result["success"] is True
            mock_update_prompt.assert_called_once()