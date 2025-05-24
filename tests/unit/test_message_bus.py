"""Comprehensive tests for the MessageBus system."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from typing import List

from message_bus import MessageBus
from event_definitions import MatrixMessageReceivedEvent, SendMatrixMessageCommand
from tests.test_utils import wait_for_condition


@pytest.mark.unit
class TestMessageBus:
    """Test the MessageBus event system."""

    @pytest.fixture
    def message_bus(self):
        """Provide a fresh MessageBus instance."""
        return MessageBus()

    @pytest.mark.asyncio
    async def test_publish_without_subscribers(self, message_bus):
        """Test publishing events when no subscribers exist."""
        event = MatrixMessageReceivedEvent(
            room_id="!test:matrix.example.com",
            event_id_matrix="$test:matrix.example.com",
            sender_id="@user:matrix.example.com",
            sender_display_name="Test User",
            body="Hello",
            room_display_name="Test Room"
        )
        
        # Should not raise any exceptions
        await message_bus.publish(event)

    @pytest.mark.asyncio
    async def test_subscribe_and_publish(self, message_bus):
        """Test basic subscription and publishing."""
        received_events = []
        
        async def handler(event):
            received_events.append(event)
        
        # Subscribe to events
        message_bus.subscribe(MatrixMessageReceivedEvent.get_event_type(), handler)
        
        # Publish an event
        event = MatrixMessageReceivedEvent(
            room_id="!test:matrix.example.com",
            event_id_matrix="$test:matrix.example.com",
            sender_id="@user:matrix.example.com",
            sender_display_name="Test User",
            body="Hello",
            room_display_name="Test Room"
        )
        
        await message_bus.publish(event)
        
        # Wait for async processing
        await wait_for_condition(lambda: len(received_events) > 0)
        
        assert len(received_events) == 1
        assert received_events[0] == event

    @pytest.mark.asyncio
    async def test_multiple_subscribers(self, message_bus):
        """Test multiple subscribers receiving the same event."""
        received_events_1 = []
        received_events_2 = []
        
        async def handler1(event):
            received_events_1.append(event)
        
        async def handler2(event):
            received_events_2.append(event)
        
        # Subscribe multiple handlers
        event_type = MatrixMessageReceivedEvent.get_event_type()
        message_bus.subscribe(event_type, handler1)
        message_bus.subscribe(event_type, handler2)
        
        # Publish an event
        event = MatrixMessageReceivedEvent(
            room_id="!test:matrix.example.com",
            event_id_matrix="$test:matrix.example.com",
            sender_id="@user:matrix.example.com",
            sender_display_name="Test User",
            body="Hello",
            room_display_name="Test Room"
        )
        
        await message_bus.publish(event)
        
        # Wait for async processing
        await wait_for_condition(lambda: len(received_events_1) > 0 and len(received_events_2) > 0)
        
        assert len(received_events_1) == 1
        assert len(received_events_2) == 1
        assert received_events_1[0] == event
        assert received_events_2[0] == event

    @pytest.mark.asyncio
    async def test_handler_exception_isolation(self, message_bus):
        """Test that exceptions in one handler don't affect others."""
        received_events = []
        
        async def failing_handler(event):
            raise ValueError("Handler failed")
        
        async def working_handler(event):
            received_events.append(event)
        
        # Subscribe both handlers
        event_type = MatrixMessageReceivedEvent.get_event_type()
        message_bus.subscribe(event_type, failing_handler)
        message_bus.subscribe(event_type, working_handler)
        
        # Publish an event
        event = MatrixMessageReceivedEvent(
            room_id="!test:matrix.example.com",
            event_id_matrix="$test:matrix.example.com",
            sender_id="@user:matrix.example.com",
            sender_display_name="Test User",
            body="Hello",
            room_display_name="Test Room"
        )
        
        await message_bus.publish(event)
        
        # Wait for async processing
        await wait_for_condition(lambda: len(received_events) > 0)
        
        # Working handler should still receive the event
        assert len(received_events) == 1
        assert received_events[0] == event

    @pytest.mark.asyncio
    async def test_different_event_types(self, message_bus):
        """Test that handlers only receive events they're subscribed to."""
        matrix_events = []
        command_events = []
        
        async def matrix_handler(event):
            matrix_events.append(event)
        
        async def command_handler(event):
            command_events.append(event)
        
        # Subscribe to different event types
        message_bus.subscribe(MatrixMessageReceivedEvent.get_event_type(), matrix_handler)
        message_bus.subscribe(SendMatrixMessageCommand.get_event_type(), command_handler)
        
        # Publish different events
        matrix_event = MatrixMessageReceivedEvent(
            room_id="!test:matrix.example.com",
            event_id_matrix="$test:matrix.example.com",
            sender_id="@user:matrix.example.com",
            sender_display_name="Test User",
            body="Hello",
            room_display_name="Test Room"
        )
        
        command_event = SendMatrixMessageCommand(
            room_id="!test:matrix.example.com",
            text="Response"
        )
        
        await message_bus.publish(matrix_event)
        await message_bus.publish(command_event)
        
        # Wait for async processing
        await wait_for_condition(lambda: len(matrix_events) > 0 and len(command_events) > 0)
        
        # Each handler should only receive its subscribed event type
        assert len(matrix_events) == 1
        assert len(command_events) == 1
        assert matrix_events[0] == matrix_event
        assert command_events[0] == command_event

    @pytest.mark.asyncio
    async def test_shutdown(self, message_bus):
        """Test message bus shutdown functionality."""
        handler_called = False
        
        async def handler(event):
            nonlocal handler_called
            handler_called = True
        
        message_bus.subscribe(MatrixMessageReceivedEvent.get_event_type(), handler)
        
        # Shutdown the bus
        await message_bus.shutdown()
        
        # Publishing after shutdown should not call handlers
        event = MatrixMessageReceivedEvent(
            room_id="!test:matrix.example.com",
            event_id_matrix="$test:matrix.example.com",
            sender_id="@user:matrix.example.com",
            sender_display_name="Test User",
            body="Hello",
            room_display_name="Test Room"
        )
        
        await message_bus.publish(event)
        
        # Give some time for potential handler execution
        await asyncio.sleep(0.1)
        
        assert not handler_called

    @pytest.mark.asyncio
    async def test_concurrent_publishing(self, message_bus):
        """Test publishing events concurrently."""
        received_events = []
        
        async def handler(event):
            # Simulate some processing time
            await asyncio.sleep(0.01)
            received_events.append(event)
        
        message_bus.subscribe(MatrixMessageReceivedEvent.get_event_type(), handler)
        
        # Publish multiple events concurrently
        events = []
        tasks = []
        
        for i in range(10):
            event = MatrixMessageReceivedEvent(
                room_id=f"!room{i}:matrix.example.com",
                event_id_matrix=f"$event{i}:matrix.example.com",
                sender_id="@user:matrix.example.com",
                sender_display_name="Test User",
                body=f"Message {i}",
                room_display_name="Test Room"
            )
            events.append(event)
            tasks.append(message_bus.publish(event))
        
        # Wait for all publishing to complete
        await asyncio.gather(*tasks)
        
        # Wait for all handlers to complete
        await wait_for_condition(lambda: len(received_events) == 10, timeout=2.0)
        
        assert len(received_events) == 10
        # All events should be received (order may vary due to concurrency)
        assert set(received_events) == set(events)