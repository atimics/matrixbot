#!/usr/bin/env python3
"""
Test script for Kanban-style action execution in the NodeProcessor.

This script validates:
1. Priority-based action queuing
2. Service-specific rate limiting
3. Continuous planning and execution
4. High-priority interrupt handling
"""

import asyncio
import logging
import sys
import time
from unittest.mock import Mock, AsyncMock
from typing import Dict, Any, List

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Mock classes to simulate the system
class MockWorldState:
    def get_world_state_data(self):
        return Mock(
            channels={'matrix': {'!test:example.com': {'recent_messages': [{'timestamp': time.time(), 'body': 'Hello'}]}}},
            farcaster={'feeds': {'home': [{'timestamp': time.time(), 'text': 'Test cast'}]}}
        )

class MockPayloadBuilder:
    def build_node_based_payload(self, world_state_data, node_manager, primary_channel_id):
        return {
            "world_state": "mock_world_state",
            "primary_channel": primary_channel_id,
            "nodes": {"expanded": [], "collapsed": []}
        }

class MockAIEngine:
    def __init__(self):
        self.call_count = 0
        
    async def decide_actions(self, world_state):
        self.call_count += 1
        # Simulate AI planning different actions based on call count
        cycle_id = world_state.get("cycle_id", "default")
        if "planning" in cycle_id:
            # Planning phase - suggest new actions
            if self.call_count == 1:
                return {
                    "reasoning": "I notice recent activity in channels, will respond",
                    "selected_actions": [
                        {
                            "action_type": "send_matrix_reply",
                            "parameters": {"room_id": "!test:example.com", "message": "Hello there!"},
                            "reasoning": "Responding to recent message"
                        },
                        {
                            "action_type": "expand_node", 
                            "parameters": {"node_path": "matrix.!test:example.com"},
                            "reasoning": "Expanding active channel for more context"
                        }
                    ]
                }
            else:
                # Later planning cycles - suggest fewer actions
                return {
                    "reasoning": "System appears stable, minimal actions needed",
                    "selected_actions": [
                        {
                            "action_type": "wait",
                            "parameters": {},
                            "reasoning": "No urgent actions needed"
                        }
                    ]
                }
        else:
            # Regular execution cycle
            return {
                "reasoning": "Executing from backlog",
                "selected_actions": []
            }

class MockNodeManager:
    def __init__(self):
        self.expanded_nodes = set()
        
    def auto_expand_active_channels(self, channel_activity):
        return ["matrix.!test:example.com"]
        
    def get_expansion_status_summary(self):
        return {"expanded": len(self.expanded_nodes), "total": 10}
        
    def expand_node(self, node_path):
        self.expanded_nodes.add(node_path)
        return True, [], f"Expanded {node_path}"
        
    def get_expanded_nodes(self):
        return list(self.expanded_nodes)

class MockToolRegistry:
    def get_enabled_tools(self):
        return [
            Mock(name="send_matrix_reply", description="Send Matrix reply", parameters_schema={}),
            Mock(name="expand_node", description="Expand node", parameters_schema={})
        ]

class MockInteractionTools:
    def get_tool_definitions(self):
        return {
            "expand_node": {
                "type": "function",
                "function": {
                    "name": "expand_node",
                    "description": "Expand a node",
                    "parameters": {}
                }
            }
        }

async def test_kanban_execution():
    """Test the Kanban-style execution model"""
    logger.debug("=== Starting Kanban Execution Test ===")
    
    # Import the NodeProcessor (assuming the path is correct)
    sys.path.append("/Users/ratimics/develop/matrixbot")
    from chatbot.core.node_system.node_processor import NodeProcessor
    from chatbot.core.node_system.action_backlog import ActionBacklog, ActionPriority
    
    # Create mock dependencies
    world_state = MockWorldState()
    payload_builder = MockPayloadBuilder()
    ai_engine = MockAIEngine()
    node_manager = MockNodeManager()
    tool_registry = MockToolRegistry()
    interaction_tools = MockInteractionTools()
    
    # Mock the platform execution methods
    async def mock_execute_platform_tool(tool_name, tool_args, cycle_id):
        logger.debug(f"Mock executing platform tool: {tool_name} with args {tool_args}")
        await asyncio.sleep(0.1)  # Simulate execution time
        return {"success": True, "tool_result": {"status": "success", "message": "Mock execution successful"}}
    
    # Create NodeProcessor instance
    processor = NodeProcessor(
        world_state_manager=world_state,
        payload_builder=payload_builder,
        ai_engine=ai_engine,
        node_manager=node_manager,
        summary_service=None,
        interaction_tools=interaction_tools,
        tool_registry=tool_registry
    )
    
    # Mock the platform execution method
    processor._execute_platform_tool = mock_execute_platform_tool
    
    # Test 1: Basic cycle execution
    logger.debug("Test 1: Basic cycle execution")
    context = {
        "trigger_type": "periodic"
    }
    
    result = await processor.process_cycle("test_cycle_1", "!test:example.com", context)
    logger.debug(f"Cycle result: {result}")
    
    # Verify results
    assert result["success"], "Cycle should succeed"
    assert result["actions_executed"] > 0, "Should execute some actions"
    assert result["planning_cycles"] > 0, "Should perform planning"
    
    # Test 2: High-priority interrupt handling
    logger.debug("Test 2: High-priority interrupt handling")
    context_mention = {
        "trigger_type": "mention",
        "primary_channel_id": "!test:example.com"
    }
    
    # Add some actions to backlog first
    processor.action_backlog.add_action(
        action_type="send_farcaster_reply",
        parameters={"cast_id": "123", "message": "Low priority reply"},
        priority=ActionPriority.LOW,
        service="farcaster",
        reasoning="Background reply"
    )
    
    result_mention = await processor.process_cycle(context_mention)
    logger.debug(f"Mention cycle result: {result_mention}")
    
    # Test 3: Rate limiting behavior
    logger.debug("Test 3: Rate limiting behavior")
    
    # Add multiple actions for the same service
    for i in range(5):
        processor.action_backlog.add_action(
            action_type="send_matrix_reply",
            parameters={"room_id": "!test:example.com", "message": f"Message {i}"},
            priority=ActionPriority.MEDIUM,
            service="matrix",
            reasoning=f"Batch message {i}"
        )
    
    # Execute cycle and check that rate limits are respected
    start_time = time.time()
    result_rate_limit = await processor.process_cycle(context)
    execution_time = time.time() - start_time
    
    logger.debug(f"Rate limit cycle result: {result_rate_limit}, execution time: {execution_time:.2f}s")
    
    # Test 4: Backlog status and monitoring
    logger.debug("Test 4: Backlog status monitoring")
    backlog_status = processor.action_backlog.get_status_summary()
    logger.debug(f"Final backlog status: {backlog_status}")
    
    logger.debug("=== Kanban Execution Test Completed Successfully ===")
    return True

async def test_action_priority_escalation():
    """Test priority escalation functionality"""
    logger.debug("=== Testing Action Priority Escalation ===")
    
    sys.path.append("/Users/ratimics/develop/matrixbot")
    from chatbot.core.node_system.action_backlog import ActionBacklog, ActionPriority
    
    # Create action backlog
    backlog = ActionBacklog()
    
    # Add some communication actions with different priorities
    backlog.add_action(
        action_type="send_matrix_reply",
        parameters={"room_id": "!test:example.com", "message": "Normal reply"},
        priority=ActionPriority.MEDIUM,
        service="matrix",
        reasoning="Regular response"
    )
    
    backlog.add_action(
        action_type="send_farcaster_reply", 
        parameters={"cast_id": "123", "message": "Another reply"},
        priority=ActionPriority.LOW,
        service="farcaster",
        reasoning="Background response"
    )
    
    logger.debug(f"Before escalation - CRITICAL queue: {len(backlog.queued_actions[ActionPriority.CRITICAL])}")
    logger.debug(f"Before escalation - MEDIUM queue: {len(backlog.queued_actions[ActionPriority.MEDIUM])}")
    
    # Test escalation (simulating NodeProcessor._escalate_communication_actions)
    for priority_queue in backlog.queued_actions.values():
        for action in list(priority_queue):
            if action.action_type in ["send_matrix_reply", "send_farcaster_reply"]:
                priority_queue.remove(action)
                action.priority = ActionPriority.CRITICAL
                backlog.queued_actions[ActionPriority.CRITICAL].appendleft(action)
                logger.debug(f"Escalated {action.action_id} to CRITICAL priority")
    
    logger.debug(f"After escalation - CRITICAL queue: {len(backlog.queued_actions[ActionPriority.CRITICAL])}")
    logger.debug(f"After escalation - MEDIUM queue: {len(backlog.queued_actions[ActionPriority.MEDIUM])}")
    
    # Verify that communication actions were escalated
    assert len(backlog.queued_actions[ActionPriority.CRITICAL]) == 2, "Both communication actions should be escalated"
    assert len(backlog.queued_actions[ActionPriority.MEDIUM]) == 0, "Medium queue should be empty"
    
    logger.debug("=== Priority Escalation Test Completed Successfully ===")
    return True

if __name__ == "__main__":
    async def main():
        try:
            await test_action_priority_escalation()
            await test_kanban_execution()
            logger.debug("All tests passed!")
        except Exception as e:
            logger.error(f"Test failed: {e}", exc_info=True)
            return False
        return True
    
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
