#!/usr/bin/env python3
"""
Test script to validate World State persistence implementation.

This script demonstrates the fix for the critical issue identified in the engineering
report: the bot's ephemeral memory causing "amnesia" on restart.
"""

import asyncio
import tempfile
import time
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import our world state components
from chatbot.core.world_state import WorldStateManager, Message

async def test_world_state_persistence():
    """Test that world state is properly persisted and restored."""
    logger.info("Testing World State Persistence...")
    
    # Create a temporary file for testing
    with tempfile.NamedTemporaryFile(suffix='.pkl', delete=False) as temp_file:
        test_state_file = temp_file.name
    
    try:
        # Test 1: Create world state and add some data
        logger.info("Step 1: Creating initial world state with test data")
        world_state_1 = WorldStateManager(state_file_path=test_state_file)
        
        # Add some test data
        world_state_1.add_channel("test_channel_1", "matrix", "Test Matrix Room")
        world_state_1.add_channel("test_channel_2", "farcaster", "Test Farcaster Channel")
        
        # Add some test messages
        test_message_1 = Message(
            id="msg_1",
            sender="@alice:matrix.org",
            content="Hello from Alice!",
            timestamp=time.time(),
            channel_type="matrix"
        )
        
        test_message_2 = Message(
            id="msg_2", 
            sender="bob_fid_123",
            content="Hello from Bob on Farcaster!",
            timestamp=time.time() + 1,
            channel_type="farcaster"
        )
        
        world_state_1.add_message("test_channel_1", test_message_1)
        world_state_1.add_message("test_channel_2", test_message_2)
        
        # Add some action history
        world_state_1.add_action_history({
            "action_type": "send_message",
            "timestamp": time.time(),
            "parameters": {"content": "Test action"},
            "result": "success"
        })
        
        # Save the state
        logger.info("Step 2: Saving world state to persistent storage")
        world_state_1.save_state()
        
        # Get summary of saved data
        state_dict_1 = world_state_1.to_dict()
        logger.info(f"Saved state contains:")
        logger.info(f"  - Channels: {len(state_dict_1['channels'])}")
        logger.info(f"  - Action history entries: {len(state_dict_1['action_history'])}")
        logger.info(f"  - Last update: {state_dict_1['last_update']}")
        
        # Test 2: Create a new world state manager and load the data
        logger.info("Step 3: Creating new world state manager (simulating restart)")
        world_state_2 = WorldStateManager(state_file_path=test_state_file)
        
        # Before loading - should be empty
        state_dict_2_before = world_state_2.to_dict()
        logger.info(f"Before loading - channels: {len(state_dict_2_before['channels'])}")
        
        # Load the state
        logger.info("Step 4: Loading world state from persistent storage")
        world_state_2.load_state()
        
        # After loading - should match the saved data
        state_dict_2_after = world_state_2.to_dict()
        logger.info(f"After loading - channels: {len(state_dict_2_after['channels'])}")
        logger.info(f"After loading - action history: {len(state_dict_2_after['action_history'])}")
        
        # Test 3: Validate data integrity
        logger.info("Step 5: Validating data integrity")
        
        # Check channels
        assert len(state_dict_2_after['channels']) == 2, "Channel count mismatch"
        assert "test_channel_1" in state_dict_2_after['channels'], "Matrix channel missing"
        assert "test_channel_2" in state_dict_2_after['channels'], "Farcaster channel missing"
        
        # Check channel details
        matrix_channel = state_dict_2_after['channels']['test_channel_1']
        farcaster_channel = state_dict_2_after['channels']['test_channel_2']
        
        assert matrix_channel['name'] == "Test Matrix Room", "Matrix channel name mismatch"
        assert matrix_channel['type'] == "matrix", "Matrix channel type mismatch"
        assert farcaster_channel['name'] == "Test Farcaster Channel", "Farcaster channel name mismatch"
        assert farcaster_channel['type'] == "farcaster", "Farcaster channel type mismatch"
        
        # Check messages
        matrix_messages = matrix_channel['recent_messages']
        farcaster_messages = farcaster_channel['recent_messages']
        
        assert len(matrix_messages) == 1, "Matrix message count mismatch"
        assert len(farcaster_messages) == 1, "Farcaster message count mismatch"
        
        assert matrix_messages[0]['sender'] == "@alice:matrix.org", "Matrix message sender mismatch"
        assert farcaster_messages[0]['sender'] == "bob_fid_123", "Farcaster message sender mismatch"
        
        # Check action history
        assert len(state_dict_2_after['action_history']) >= 1, "Action history missing"
        
        logger.info("✅ All persistence tests passed!")
        
        # Test 4: Demonstrate the fix working with an orchestrator-like pattern
        logger.info("Step 6: Testing orchestrator integration pattern")
        
        # Simulate what happens in MainOrchestrator.start()
        world_state_3 = WorldStateManager(state_file_path=test_state_file)
        world_state_3.load_state()  # This is the critical fix we implemented
        
        # Add new data (simulating runtime operation)
        world_state_3.add_channel("runtime_channel", "matrix", "Runtime Added Channel")
        
        # Simulate what happens in MainOrchestrator.stop()
        world_state_3.save_state()  # This is the critical fix we implemented
        
        # Verify the runtime data persists
        world_state_4 = WorldStateManager(state_file_path=test_state_file)
        world_state_4.load_state()
        final_state = world_state_4.to_dict()
        
        assert len(final_state['channels']) == 3, "Runtime channel not persisted"
        assert "runtime_channel" in final_state['channels'], "Runtime channel missing"
        
        logger.info("✅ Orchestrator integration pattern test passed!")
        logger.info("🎉 World State Persistence implementation is working correctly!")
        
        # Summary
        logger.info("\n" + "="*60)
        logger.info("WORLD STATE PERSISTENCE TEST SUMMARY")
        logger.info("="*60)
        logger.info(f"✅ Initial save: {len(state_dict_1['channels'])} channels, {len(state_dict_1['action_history'])} actions")
        logger.info(f"✅ Successful reload: All data preserved")
        logger.info(f"✅ Runtime persistence: New data correctly saved and restored")
        logger.info(f"✅ File location: {test_state_file}")
        logger.info("✅ The bot will now remember its state across restarts!")
        logger.info("="*60)
        
    finally:
        # Clean up
        if Path(test_state_file).exists():
            Path(test_state_file).unlink()
            logger.info(f"Cleaned up test file: {test_state_file}")

if __name__ == "__main__":
    asyncio.run(test_world_state_persistence())
