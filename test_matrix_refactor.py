#!/usr/bin/env python3
"""
Test script to verify the Matrix observer refactoring is working correctly.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add the project root to the Python path
sys.path.insert(0, str(Path(__file__).parent))

from chatbot.integrations.matrix import MatrixObserver
from chatbot.core.world_state.manager import WorldStateManager
from chatbot.core.node_system.node_manager import NodeManager
from chatbot.core.node_system.interaction_tools import NodeInteractionTools

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_matrix_observer():
    """Test that the new Matrix observer can be instantiated and has the right methods."""
    
    logger.debug("Testing Matrix observer refactoring...")
    
    # Test 1: Import and instantiate
    try:
        world_state = WorldStateManager()
        observer = MatrixObserver(world_state)
        logger.debug("✓ Matrix observer instantiated successfully")
    except Exception as e:
        logger.error(f"✗ Failed to instantiate Matrix observer: {e}")
        return False
    
    # Test 2: Check essential methods exist
    essential_methods = [
        'connect', 'disconnect', 'is_healthy', 'get_status',
        'send_message', 'send_reply', 'join_room', 'leave_room',
        'add_channel'
    ]
    
    for method_name in essential_methods:
        if hasattr(observer, method_name):
            logger.debug(f"✓ Method {method_name} exists")
        else:
            logger.error(f"✗ Method {method_name} missing")
            return False
    
    # Test 3: Check components are initialized
    components = ['auth_handler', 'room_manager', 'event_handler', 'message_ops', 'room_ops', 'encryption_handler']
    
    for component_name in components:
        if hasattr(observer, component_name):
            logger.debug(f"✓ Component {component_name} initialized")
        else:
            logger.error(f"✗ Component {component_name} missing")
            return False
    
    logger.debug("✓ All Matrix observer tests passed!")
    return True

async def test_node_tools():
    """Test that the node interaction tools work correctly."""
    
    logger.debug("Testing node interaction tools...")
    
    try:
        # Test 1: Create node manager and tools
        node_manager = NodeManager()
        node_tools = NodeInteractionTools(node_manager)
        logger.debug("✓ Node tools instantiated successfully")
        
        # Test 2: Check get_expansion_status tool
        tools = node_tools.get_tool_definitions()
        if 'get_expansion_status' in tools:
            logger.debug("✓ get_expansion_status tool definition exists")
        else:
            logger.error("✗ get_expansion_status tool definition missing")
            return False
        
        # Test 3: Execute get_expansion_status
        result = node_tools.execute_tool('get_expansion_status', {})
        if result.get('success'):
            logger.debug("✓ get_expansion_status tool executed successfully")
        else:
            logger.error(f"✗ get_expansion_status tool failed: {result}")
            return False
        
        logger.debug("✓ All node tools tests passed!")
        return True
        
    except Exception as e:
        logger.error(f"✗ Node tools test failed: {e}")
        return False

async def main():
    """Run all tests."""
    
    logger.debug("Starting Matrix observer refactoring tests...")
    
    success = True
    
    # Test Matrix observer
    if not await test_matrix_observer():
        success = False
    
    # Test node tools
    if not await test_node_tools():
        success = False
    
    if success:
        logger.debug("🎉 All tests passed! Matrix observer refactoring is working correctly.")
        return 0
    else:
        logger.error("❌ Some tests failed. Please check the logs above.")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
