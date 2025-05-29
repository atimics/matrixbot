#!/usr/bin/env python3
"""Test script to help reproduce the race condition with overlapping turn processing."""

import asyncio
import time
import logging
from json_centric_room_logic_service import JsonCentricRoomLogicService
from message_bus import MessageBus
from event_definitions import RoomMessageTextEvent, ActivateListeningEvent
from action_registry_service import ActionRegistryService

# Set up logging to see what's happening
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def test_race_condition():
    """Test the race condition scenario."""
    
    # Create services
    bus = MessageBus()
    action_registry = ActionRegistryService(bus)
    room_logic = JsonCentricRoomLogicService(
        bus=bus,
        action_registry=action_registry,
        thinker_model="test-model",
        planner_model="test-model"
    )
    
    # Mock room
    room_id = "!test:example.com"
    
    # Activate listening
    await bus.publish(ActivateListeningEvent(room_id=room_id))
    
    print("Step 1: Sending first message...")
    # Send first message
    await bus.publish(RoomMessageTextEvent(
        room_id=room_id,
        event_id="$event1",
        sender_user_id="@user:example.com",
        sender_display_name="TestUser",
        content="Hello, first message",
        timestamp=int(time.time() * 1000)
    ))
    
    # Wait a bit to let first processing start
    await asyncio.sleep(1)
    
    print("Step 2: Sending second message quickly...")
    # Send second message quickly to trigger race condition
    await bus.publish(RoomMessageTextEvent(
        room_id=room_id,
        event_id="$event2", 
        sender_user_id="@user:example.com",
        sender_display_name="TestUser",
        content="Hello, second message",
        timestamp=int(time.time() * 1000)
    ))
    
    # Wait to see what happens
    print("Waiting to observe behavior...")
    await asyncio.sleep(10)
    
    print("Test completed")

if __name__ == "__main__":
    asyncio.run(test_race_condition())
