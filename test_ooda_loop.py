#!/usr/bin/env python3
"""
Test script for the OODA (Observe, Orient, Decide, Act) loop implementation.

This script validates that the new OODA loop architecture works correctly
by testing the structured two-phase AI decision-making process.
"""

import asyncio
import logging
import sys
from typing import Dict, Any
from unittest.mock import AsyncMock, MagicMock

# Add the project root to the path
sys.path.insert(0, '/Users/ratimics/develop/matrixbot')

from chatbot.core.node_system.node_processor import NodeProcessor
from chatbot.core.world_state.structures import WorldStateData

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class MockWorldStateManager:
    """Mock WorldStateManager for testing."""
    
    def __init__(self):
        self.state = WorldStateData()
        self.state.channels = {}
        self.state.farcaster = {
            "feeds": {
                "home": {"recent_casts": []},
                "trending": {"recent_casts": []}
            }
        }
    
    def get_world_state_data(self) -> WorldStateData:
        """Return the mock world state data."""
        return self.state


class MockPayloadBuilder:
    """Mock PayloadBuilder for testing."""
    
    def __init__(self):
        self.last_action_result = None
    
    def build_node_based_payload(self, world_state_data, node_manager, primary_channel_id, config=None):
        """Build a mock payload for testing."""
        cfg = config or {}
        phase = cfg.get("phase", "decide")
        
        mock_payload = {
            "current_processing_channel_id": primary_channel_id,
            "system_status": {"timestamp": "2025-06-21T10:00:00Z"},
            "ooda_phase": phase,
            "cycle_context": {},
            "collapsed_node_summaries": {
                "channels.matrix.test_room": {
                    "summary": "Test room with some activity",
                    "node_path_for_tools": "channels.matrix.test_room"
                }
            },
            "payload_stats": {
                "phase": phase,
                "expanded_nodes_count": 0 if phase == "orient" else 1,
                "collapsed_nodes_count": 1
            }
        }
        
        if phase != "orient":
            mock_payload["expanded_nodes"] = {
                "channels.matrix.test_room": {
                    "recent_messages": [
                        {"content": "Hello world", "sender": "user123", "timestamp": "2025-06-21T10:00:00Z"}
                    ]
                }
            }
        
        return mock_payload
    
    def set_last_action_result(self, result):
        """Set the last action result."""
        self.last_action_result = result


class MockAIEngine:
    """Mock AIEngine for testing OODA phases."""
    
    async def decide_actions(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Mock AI decision based on payload content."""
        
        # Check for OODA phase instructions
        ai_instruction = payload.get("ai_instruction", {})
        phase = ai_instruction.get("phase")
        
        if phase == "orientation":
            # In orientation phase, AI should expand nodes
            return {
                "reasoning": "I need to expand the test room to see recent messages",
                "selected_actions": [
                    {
                        "action_type": "expand_node",
                        "arguments": {"node_path": "channels.matrix.test_room"},
                        "reasoning": "Expanding to see recent activity"
                    }
                ]
            }
        elif phase == "decision":
            # In decision phase, AI should take external actions
            return {
                "reasoning": "I see a message in the test room, I should respond",
                "selected_actions": [
                    {
                        "action_type": "send_matrix_message",
                        "arguments": {
                            "room_id": "test_room",
                            "content": "Hello! I'm responding to your message."
                        },
                        "reasoning": "Sending a friendly response"
                    }
                ]
            }
        else:
            # Default phase
            return {
                "reasoning": "No specific phase detected",
                "selected_actions": []
            }


class MockNodeManager:
    """Mock NodeManager for testing."""
    
    def __init__(self):
        self.nodes = {}
    
    def get_node_metadata(self, node_path):
        """Return mock node metadata."""
        mock_metadata = MagicMock()
        mock_metadata.is_expanded = False
        mock_metadata.is_pinned = False
        mock_metadata.ai_summary = f"Summary for {node_path}"
        return mock_metadata
    
    def get_expansion_status_summary(self):
        """Return mock expansion status."""
        return {
            "expanded_count": 0,
            "max_expanded": 10,
            "pinned_count": 0
        }
    
    def get_system_events(self):
        """Return mock system events."""
        return []


class MockInteractionTools:
    """Mock NodeInteractionTools for testing."""
    
    def __init__(self):
        self.executed_tools = []
    
    def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Mock tool execution."""
        self.executed_tools.append((tool_name, arguments))
        return {
            "success": True,
            "message": f"Successfully executed {tool_name}",
            "node_path": arguments.get("node_path"),
            "action": tool_name
        }


class MockActionExecutor:
    """Mock ActionExecutor for testing."""
    
    def __init__(self):
        self.executed_actions = []
    
    async def execute_action(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Mock action execution."""
        self.executed_actions.append(action)
        return {
            "success": True,
            "action_type": action.get("action_type"),
            "message": f"Successfully executed {action.get('action_type')}"
        }


async def test_ooda_loop():
    """Test the OODA loop implementation."""
    
    logger.info("🧪 Starting OODA Loop Test")
    
    # Create mock components
    world_state_manager = MockWorldStateManager()
    payload_builder = MockPayloadBuilder()
    ai_engine = MockAIEngine()
    node_manager = MockNodeManager()
    interaction_tools = MockInteractionTools()
    action_executor = MockActionExecutor()
    
    # Create NodeProcessor with mocks
    processor = NodeProcessor(
        world_state_manager=world_state_manager,
        payload_builder=payload_builder,
        ai_engine=ai_engine,
        node_manager=node_manager,
        summary_service=None,  # Not needed for this test
        interaction_tools=interaction_tools,
        action_executor=action_executor
    )
    
    # Test OODA loop execution
    logger.info("🎯 Testing OODA Loop execution")
    
    result = await processor.ooda_loop(
        cycle_id="test_001",
        primary_channel_id="test_room",
        context={
            "trigger_type": "mention",
            "primary_channel_id": "test_room"
        }
    )
    
    # Validate results
    logger.info("✅ Validating OODA Loop results")
    
    assert result["success"] is True, f"OODA loop failed: {result}"
    assert "ooda_loop_duration" in result, "Missing OODA loop duration"
    assert "node_actions_executed" in result, "Missing node actions count"
    assert "external_actions_executed" in result, "Missing external actions count"
    
    # Check that node tools were executed in Orient phase
    assert len(interaction_tools.executed_tools) > 0, "No node tools executed in Orient phase"
    tool_name, tool_args = interaction_tools.executed_tools[0]
    assert tool_name == "expand_node", f"Expected expand_node, got {tool_name}"
    assert tool_args["node_path"] == "channels.matrix.test_room", f"Wrong node path: {tool_args}"
    
    # Check that external actions were executed in Act phase
    assert len(action_executor.executed_actions) > 0, "No external actions executed in Act phase"
    external_action = action_executor.executed_actions[0]
    assert external_action["action_type"] == "send_matrix_message", f"Wrong action type: {external_action}"
    
    logger.info("🎉 OODA Loop test completed successfully!")
    logger.info(f"📊 Results: {result}")
    logger.info(f"🔧 Node tools executed: {interaction_tools.executed_tools}")
    logger.info(f"🚀 External actions executed: {[a['action_type'] for a in action_executor.executed_actions]}")


async def test_ooda_phases():
    """Test that OODA phases work correctly in isolation."""
    
    logger.info("🧪 Testing OODA Phases individually")
    
    # Test Orient phase payload
    world_state_manager = MockWorldStateManager()
    payload_builder = MockPayloadBuilder()
    node_manager = MockNodeManager()
    
    # Create a minimal processor for payload testing
    processor = NodeProcessor(
        world_state_manager=world_state_manager,
        payload_builder=payload_builder,
        ai_engine=None,
        node_manager=node_manager,
        summary_service=None,
        interaction_tools=None
    )
    
    # Test Orient payload
    logger.info("🎯 Testing Orient payload generation")
    context = {"cycle_id": "test_orient", "primary_channel_id": "test_room"}
    orient_payload = await processor._build_orientation_payload(context)
    
    assert orient_payload is not None, "Orient payload is None"
    assert orient_payload["ooda_phase"] == "orient", f"Wrong phase: {orient_payload['ooda_phase']}"
    assert "collapsed_node_summaries" in orient_payload, "Missing collapsed_node_summaries"
    assert "expanded_nodes" not in orient_payload, "Orient payload should not have expanded_nodes"
    
    logger.info("✅ Orient payload test passed")
    
    # Test Decide payload
    logger.info("🎯 Testing Decide payload generation")
    decide_payload = await processor._build_decision_payload(context)
    
    assert decide_payload is not None, "Decide payload is None"
    assert decide_payload["ooda_phase"] == "decide", f"Wrong phase: {decide_payload['ooda_phase']}"
    assert "collapsed_node_summaries" in decide_payload, "Missing collapsed_node_summaries"
    assert "expanded_nodes" in decide_payload, "Decide payload should have expanded_nodes"
    
    logger.info("✅ Decide payload test passed")
    logger.info("🎉 OODA Phases test completed successfully!")


if __name__ == "__main__":
    async def main():
        """Run all OODA loop tests."""
        try:
            await test_ooda_phases()
            await test_ooda_loop()
            logger.info("🎉 All OODA loop tests passed!")
        except Exception as e:
            logger.error(f"❌ OODA loop test failed: {e}", exc_info=True)
            sys.exit(1)
    
    asyncio.run(main())
