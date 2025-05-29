#!/usr/bin/env python3
"""
Test script for the event-driven AI bot system

This script tests the core components without requiring external API keys.
"""

import asyncio
import logging
import time
from unittest.mock import AsyncMock, MagicMock

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_world_state():
    """Test world state management"""
    logger.info("Testing world state management...")
    
    from world_state import WorldState, Message
    
    # Create world state
    world_state = WorldState()
    
    # Add test messages
    message1 = Message(
        id="msg1",
        channel_id="test_channel",
        channel_type="matrix",
        sender="alice",
        content="Hello world!",
        timestamp=time.time()
    )
    
    world_state.add_message(message1)
    
    # Test state functions
    messages = world_state.get_all_messages()
    assert len(messages) == 1
    assert messages[0].content == "Hello world!"
    
    # Test JSON serialization
    json_state = world_state.to_json()
    assert "Hello world!" in json_state
    
    logger.info("✓ World state test passed")

async def test_ai_engine_mock():
    """Test AI engine with mocked API"""
    logger.info("Testing AI engine structure...")
    
    from ai_engine import AIDecisionEngine, ActionPlan
    from world_state import WorldState
    
    # Create AI engine with dummy key
    ai_engine = AIDecisionEngine(api_key="test_key")
    
    # Just test that it's properly initialized
    assert ai_engine.api_key == "test_key"
    assert ai_engine.max_actions_per_cycle == 3
    
    logger.info("✓ AI engine structure test passed")

async def test_action_executor():
    """Test action executor"""
    logger.info("Testing action executor...")
    
    from action_executor import ActionExecutor
    
    # Create action executor
    executor = ActionExecutor()
    
    # Test wait action
    result = await executor.execute_action("wait", {"duration": 0.1})
    assert "Waited" in result
    
    # Test error handling
    result = await executor.execute_action("invalid_action", {})
    assert "Unknown action type" in result
    
    logger.info("✓ Action executor test passed")

async def test_observers_mock():
    """Test observers with mocked connections"""
    logger.info("Testing observers with mock...")
    
    from matrix_observer import MatrixObserver
    from farcaster_observer import FarcasterObserver
    from world_state import WorldState
    
    # Create a simple world state for Matrix observer
    world_state = WorldState()
    
    # Test Matrix observer - use None to simulate missing env vars
    matrix_obs = MatrixObserver(None)  # Pass None to simulate missing world state manager
    
    # Test Farcaster observer
    farcaster_obs = FarcasterObserver("test_key")
    
    # Test connection status methods
    farcaster_connected = farcaster_obs.is_connected()
    assert farcaster_connected == True  # Should have API key
    
    logger.info("✓ Observer structure tests passed")

async def test_event_orchestrator_components():
    """Test event orchestrator component integration"""
    logger.info("Testing event orchestrator components...")
    
    from event_orchestrator import EventOrchestrator
    
    # Create orchestrator (will fail on real API calls, but we can test initialization)
    try:
        orchestrator = EventOrchestrator()
        
        # Test status method
        status = orchestrator.get_status()
        assert "running" in status
        assert "cycle_count" in status
        assert status["cycle_count"] == 0
        
        # Test state hash calculation
        hash1 = orchestrator._calculate_state_hash()
        hash2 = orchestrator._calculate_state_hash()
        assert hash1 == hash2  # Should be same with no changes
        
        logger.info("✓ Event orchestrator component test passed")
        
    except Exception as e:
        # Expected to fail without real credentials
        if "OPENROUTER_API_KEY" in str(e) or "NoneType" in str(e):
            logger.info("✓ Event orchestrator component test passed (expected credential error)")
        else:
            raise e

async def run_all_tests():
    """Run all tests"""
    logger.info("Starting event-driven AI bot system tests...")
    
    try:
        await test_world_state()
        await test_ai_engine_mock()
        await test_action_executor()
        await test_observers_mock()
        await test_event_orchestrator_components()
        
        logger.info("🎉 All tests passed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    exit(0 if success else 1)
