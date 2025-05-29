#!/usr/bin/env python3
"""
Event-Driven AI Bot Demo

This script demonstrates the event-driven AI bot system with a simple scenario.
It simulates messages arriving and shows how the system responds.
"""

import asyncio
import logging
import time
from typing import Dict, Any

from world_state import WorldState, Message
from ai_engine import AIDecisionEngine
from action_executor import ActionExecutor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class MockAIEngine:
    """Mock AI engine that makes simple decisions"""
    
    def __init__(self):
        self.max_actions_per_cycle = 3
        logger.info("Mock AI engine initialized")
    
    async def make_decision(self, world_state_dict: Dict[str, Any], cycle_id: str):
        """Make mock decisions based on simple rules"""
        from ai_engine import DecisionResult, ActionPlan
        
        logger.info(f"Mock AI making decision for cycle {cycle_id}")
        
        # Simple decision logic
        messages = world_state_dict.get("channels", {})
        total_messages = sum(len(ch.get("recent_messages", [])) for ch in messages.values())
        
        selected_actions = []
        
        if total_messages > 0:
            # If there are messages, respond to them
            selected_actions.append(ActionPlan(
                action_type="send_matrix_message",
                parameters={
                    "room_id": "!demo:example.com",
                    "content": f"I see {total_messages} messages in the channels. How can I help?"
                },
                reasoning="Responding to activity in the channels",
                priority=8
            ))
        else:
            # If no messages, just wait
            selected_actions.append(ActionPlan(
                action_type="wait",
                parameters={"duration": 1},
                reasoning="No new activity detected, waiting for messages",
                priority=3
            ))
        
        return DecisionResult(
            selected_actions=selected_actions,
            reasoning=f"Analyzed {total_messages} messages and selected {len(selected_actions)} actions",
            observations="Demo environment with mock messages",
            cycle_id=cycle_id
        )

async def demo_event_cycle():
    """Demonstrate a complete event cycle"""
    logger.info("🚀 Starting event-driven AI bot demo...")
    
    # Initialize components
    world_state = WorldState()
    ai_engine = MockAIEngine()
    action_executor = ActionExecutor()
    
    # Simulate some initial state
    logger.info("📝 Setting up initial world state...")
    
    # Add a simulated channel
    world_state.update_system_status({
        "demo_mode": True,
        "matrix_connected": False,
        "farcaster_connected": False
    })
    
    # Simulate new message arriving
    logger.info("📨 Simulating new message arrival...")
    
    message = Message(
        id="msg_demo_1",
        channel_id="!demo:example.com",
        channel_type="matrix",
        sender="alice",
        content="Hello! Is anyone there?",
        timestamp=time.time()
    )
    
    world_state.add_message(message)
    
    # Show world state
    logger.info("🌍 Current world state:")
    logger.info(f"   Messages: {len(world_state.get_all_messages())}")
    logger.info(f"   Channels: {len(world_state.channels)}")
    
    # Trigger AI decision
    logger.info("🤖 Triggering AI decision cycle...")
    
    world_state_dict = world_state.to_dict()
    decision_result = await ai_engine.make_decision(world_state_dict, "demo_cycle_1")
    
    logger.info(f"🎯 AI Decision Result:")
    logger.info(f"   Reasoning: {decision_result.reasoning}")
    logger.info(f"   Selected actions: {len(decision_result.selected_actions)}")
    
    # Execute actions
    logger.info("⚡ Executing selected actions...")
    
    for i, action in enumerate(decision_result.selected_actions):
        logger.info(f"   Action {i+1}: {action.action_type}")
        logger.info(f"   Reasoning: {action.reasoning}")
        
        # Execute the action
        result = await action_executor.execute_action(action.action_type, action.parameters)
        logger.info(f"   Result: {result}")
        
        # Record action in world state
        world_state.add_action_history({
            "action_type": action.action_type,
            "parameters": action.parameters,
            "result": result,
            "timestamp": time.time()
        })
    
    # Show final state
    logger.info("📊 Final world state:")
    logger.info(f"   Messages: {len(world_state.get_all_messages())}")
    logger.info(f"   Action history: {len(world_state.action_history)}")
    
    # Demonstrate state change detection
    logger.info("🔍 Demonstrating state change detection...")
    
    # Calculate state hash before and after changes
    def calculate_simple_hash(ws):
        return str(hash(str({
            "messages": len(ws.get_all_messages()),
            "actions": len(ws.action_history),
            "last_update": ws.last_update
        })))
    
    hash1 = calculate_simple_hash(world_state)
    logger.info(f"   State hash: {hash1[:8]}...")
    
    # Add another message
    message2 = Message(
        id="msg_demo_2",
        channel_id="!demo:example.com",
        channel_type="matrix",
        sender="bob",
        content="Thanks for responding!",
        timestamp=time.time()
    )
    
    world_state.add_message(message2)
    hash2 = calculate_simple_hash(world_state)
    logger.info(f"   New hash: {hash2[:8]}...")
    logger.info(f"   State changed: {hash1 != hash2}")
    
    logger.info("✅ Demo completed successfully!")
    logger.info("")
    logger.info("🏗️  This demonstrates the core event-driven architecture:")
    logger.info("   1. World state changes (new messages)")
    logger.info("   2. AI analyzes state and selects actions")
    logger.info("   3. Actions are executed")
    logger.info("   4. Results update world state")
    logger.info("   5. Cycle repeats when new changes occur")

if __name__ == "__main__":
    asyncio.run(demo_event_cycle())
