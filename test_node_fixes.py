#!/usr/bin/env python3
"""
Test script for P0 critical fixes to node-based processing.

This script tests:
1. NodeManager connection to ActionContext for node tools
2. NodeProcessor execution of both node and external tools
3. Structured summaries in node payloads
"""

import asyncio
import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from chatbot.core.node_system.node_manager import NodeManager
from chatbot.core.node_system.summary_service import NodeSummaryService
from chatbot.core.node_system.node_processor import NodeProcessor
from chatbot.core.ai_engine import AIDecisionEngine
from chatbot.core.world_state.manager import WorldStateManager
from chatbot.core.world_state.payload_builder import PayloadBuilder
from chatbot.tools.registry import ToolRegistry
from chatbot.tools.base import ActionContext
from chatbot.tools.node_tools import ExpandNodeTool
from chatbot.config import settings

async def test_node_tool_execution():
    """Test P0 Fix: Node tools can access NodeManager through ActionContext"""
    print("🧪 Testing P0 Fix: Node Tool Execution Context")
    
    # Create components
    world_state = WorldStateManager()
    node_manager = NodeManager(max_expanded_nodes=5)
    
    # P0 FIX: Connect node_manager to world_state 
    world_state.node_manager = node_manager
    
    # Create ActionContext with node_manager
    action_context = ActionContext(world_state_manager=world_state)
    action_context.node_manager = node_manager
    
    # Test ExpandNodeTool execution
    expand_tool = ExpandNodeTool()
    
    # Test parameters
    params = {"node_path": "channels.matrix.test_room"}
    
    # Execute the tool
    result = await expand_tool.execute(params, action_context)
    
    print(f"✅ ExpandNodeTool result: {result}")
    
    # Verify success
    if result.get("status") == "success":
        print("✅ P0 Fix verified: NodeManager accessible through ActionContext")
        return True
    else:
        print(f"❌ P0 Fix failed: {result.get('error', 'Unknown error')}")
        return False

async def test_structured_summaries():
    """Test P1 Enhancement: Structured node summaries"""
    print("\n🧪 Testing P1 Enhancement: Structured Node Summaries")
    
    # Create summary service
    if not settings.OPENROUTER_API_KEY:
        print("⚠️  OPENROUTER_API_KEY not set, using fallback summaries only")
    
    summary_service = NodeSummaryService(
        api_key=settings.OPENROUTER_API_KEY or "test_key",
        model="openai/gpt-4o-mini"
    )
    
    # Test data
    node_data = {
        "recent_messages": [
            {"sender": "alice", "content": "Hello world", "timestamp": 1672531200},
            {"sender": "bob", "content": "How are you?", "timestamp": 1672531300},
        ]
    }
    
    # Generate summary
    summary = await summary_service.generate_node_summary(
        "channels.matrix.test_room",
        node_data,
        "matrix"
    )
    
    print(f"✅ Structured summary: {summary}")
    
    # Verify structure
    if isinstance(summary, dict) and "summary" in summary:
        print("✅ P1 Enhancement verified: Summaries are now structured")
        if "message_count" in summary:
            print("✅ Enhanced metadata included in summary")
        return True
    else:
        print("❌ P1 Enhancement failed: Summary not structured")
        return False

async def test_node_processor_integration():
    """Test integration of all fixes in NodeProcessor"""
    print("\n🧪 Testing NodeProcessor Integration")
    
    # Create all components
    world_state = WorldStateManager()
    node_manager = NodeManager(max_expanded_nodes=5)
    world_state.node_manager = node_manager
    
    # Add some test data to world state
    world_state.add_channel("test_room", "matrix", "Test Room")
    
    # Create other components
    summary_service = NodeSummaryService(
        api_key=settings.OPENROUTER_API_KEY or "test_key"
    )
    
    # Create a minimal AI engine for testing
    class MockAIEngine:
        async def make_decision(self, payload, cycle_id):
            # Mock decision to expand a node
            from chatbot.core.ai_engine import DecisionResult, ActionPlan
            action = ActionPlan(
                action_type="expand_node",
                parameters={"node_path": "channels.matrix.test_room"},
                reasoning="Testing node expansion",
                priority=1
            )
            return DecisionResult(
                cycle_id=cycle_id,
                selected_actions=[action],
                reasoning="Mock decision for testing",
                observations="Testing mode"
            )
    
    ai_engine = MockAIEngine()  # type: ignore  # Mock for testing
    payload_builder = PayloadBuilder()
    tool_registry = ToolRegistry()
    
    # Register node tools
    from chatbot.tools.node_tools import ExpandNodeTool, CollapseNodeTool
    tool_registry.register_tool(ExpandNodeTool())
    tool_registry.register_tool(CollapseNodeTool())
    
    # Create ActionContext
    action_context = ActionContext(world_state_manager=world_state)
    action_context.node_manager = node_manager
    
    # Create NodeProcessor
    node_processor = NodeProcessor(
        node_manager=node_manager,
        summary_service=summary_service,
        ai_engine=ai_engine,
        world_state_manager=world_state,
        payload_builder=payload_builder,
        tool_registry=tool_registry,
        action_context=action_context
    )
    
    # Test a processing cycle
    result = await node_processor.process_cycle("test_cycle", "test_room")
    
    print(f"✅ NodeProcessor cycle result: {result}")
    
    if result.get("success"):
        print("✅ Integration test passed: NodeProcessor executing actions")
        return True
    else:
        print(f"❌ Integration test failed: {result.get('error', 'Unknown error')}")
        return False

async def main():
    """Run all tests"""
    print("🚀 Running Node Processing P0/P1 Fix Tests\n")
    
    tests = [
        test_node_tool_execution,
        test_structured_summaries,
        test_node_processor_integration
    ]
    
    results = []
    for test in tests:
        try:
            result = await test()
            results.append(result)
        except Exception as e:
            print(f"❌ Test failed with exception: {e}")
            results.append(False)
    
    # Summary
    passed = sum(results)
    total = len(results)
    
    print(f"\n📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All critical fixes verified!")
        return True
    else:
        print("⚠️  Some fixes need attention")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
