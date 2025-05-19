import asyncio
import pytest
from room_logic_service import RoomLogicService
from message_bus import MessageBus
from tool_manager import ToolRegistry
from event_definitions import (
    MatrixMessageReceivedEvent, ActivateListeningEvent, ProcessMessageBatchCommand,
    AIInferenceResponseEvent, BotDisplayNameReadyEvent, ToolExecutionResponse
)

@pytest.mark.asyncio
async def test_room_logic_service_creation_and_run_stop():
    bus = MessageBus()
    tool_registry = ToolRegistry([]) # Empty registry for basic test
    db_path = ":memory:" # In-memory DB for test
    service = RoomLogicService(bus, tool_registry, db_path, bot_display_name="TestBot")

    # Ensure all subscriptions can be made (i.e., methods exist)
    # This also implicitly tests that the handler methods are defined.
    bus.subscribe(MatrixMessageReceivedEvent, service._handle_matrix_message)
    bus.subscribe(ActivateListeningEvent, service._handle_activate_listening)
    bus.subscribe(ProcessMessageBatchCommand, service._handle_process_message_batch)
    bus.subscribe(AIInferenceResponseEvent, service._handle_ai_chat_response)
    bus.subscribe(AIInferenceResponseEvent, service._handle_ai_summary_response)
    bus.subscribe(BotDisplayNameReadyEvent, service._handle_bot_display_name_ready)
    bus.subscribe(ToolExecutionResponse, service._handle_tool_execution_response)
    await bus.shutdown() # Replaced unsubscribe_all with shutdown

    # Test that run can be called and stop can be called
    run_task = asyncio.create_task(service.run())
    
    # Give it a moment to start and subscribe
    await asyncio.sleep(0.01) 
    assert not service._stop_event.is_set(), "Stop event should not be set initially"
    assert not run_task.done(), "Run task should be waiting on stop event"
    
    # Call stop
    await service.stop()
    
    # Wait for the run_task to complete, with a timeout
    try:
        await asyncio.wait_for(run_task, timeout=1.0)
    except asyncio.TimeoutError:
        pytest.fail("service.run() did not complete after stop() was called.")
    
    assert run_task.done(), "Run task should have completed after stop"
    assert service._stop_event.is_set(), "Stop event should be set after stop()"

    # Verify it unsubscribed (conceptual, MessageBus mock would be better)
    # For a real test, you might mock the bus to check unsubscribe calls.
    # Here, we just ensure no error occurs if we try to publish after stop.
    try:
        await bus.publish(MatrixMessageReceivedEvent(
            room_id="test", 
            event_id_matrix="test_event", 
            sender_display_name="test_user", 
            sender_id="@test_user:matrix.org",  # Added sender_id
            room_display_name="Test Room",  # Added room_display_name
            body="test message", 
            timestamp=asyncio.get_event_loop().time()
        ))
    except Exception as e:
        pytest.fail(f"Publishing after stop should not error if unsubscribed, but got: {e}")
