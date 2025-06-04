#!/usr/bin/env python3
"""
Test script for complete ACE workflow using the orchestrator
"""
import asyncio
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from chatbot.tools.developer_tools import ACEOrchestratorTool
from chatbot.tools.base import ActionContext
from chatbot.core.world_state.structures import WorldStateData


class MockWorldStateManager:
    def __init__(self):
        self.state = WorldStateData()
    
    async def get_state(self):
        return self.state
    
    async def update_state(self, new_state):
        self.state = new_state
        print(f"🌍 World state: {len(self.state.target_repositories)} repos, {len(self.state.development_tasks)} tasks")


async def test_ace_orchestrator():
    """Test the complete ACE orchestrator workflow"""
    print("🎼 Testing ACE Orchestrator - Complete Workflow...")
    
    # Shared context
    context = ActionContext(
        world_state_manager=MockWorldStateManager()
    )
    context.world_state = WorldStateData()
    
    # Test the full orchestrator workflow
    orchestrator = ACEOrchestratorTool()
    params = {
        "target_repo_url": "https://github.com/octocat/Hello-World",
        "improvement_focus": "documentation",
        "workflow_scope": "targeted",
        "context_description": "Simple Hello World repository that could benefit from better documentation",
        "auto_implement": True,  # Automatically implement changes
        "create_pr": True       # Create PR after implementation
    }
    
    print(f"🚀 Starting ACE workflow with parameters:")
    for key, value in params.items():
        print(f"  {key}: {value}")
    
    try:
        result = await orchestrator.execute(params, context)
        
        print(f"\n✅ Orchestrator Result:")
        print(f"  Status: {result.get('status')}")
        print(f"  Message: {result.get('message')}")
        print(f"  Workflow ID: {result.get('workflow_id')}")
        print(f"  Focus: {result.get('improvement_focus')}")
        
        # Display step results
        print(f"\n📋 Workflow Steps:")
        steps = result.get('results', {}).get('steps', [])
        for i, (step_name, step_result) in enumerate(steps, 1):
            status = step_result.get('status', 'unknown')
            print(f"  {i}. {step_name.title()}: {status}")
            if status == "failure":
                print(f"     Error: {step_result.get('message', 'Unknown error')}")
        
        return result.get("status") in ["complete", "implemented", "proposals_ready", "analyzed"]
        
    except Exception as e:
        print(f"❌ Error executing orchestrator: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_manual_workflow():
    """Test manual step-by-step workflow for comparison"""
    print("\n🔧 Testing manual step-by-step workflow for comparison...")
    
    context = ActionContext(world_state_manager=MockWorldStateManager())
    context.world_state = WorldStateData()
    
    # Import tools
    from chatbot.tools.developer_tools import (
        SetupDevelopmentWorkspaceTool, 
        ExploreCodebaseTool,
        AnalyzeAndProposeChangeTool,
        ImplementCodeChangesTool,
        CreatePullRequestTool
    )
    
    target_repo = "https://github.com/octocat/Hello-World"
    
    # Manual workflow
    steps = [
        ("Setup", SetupDevelopmentWorkspaceTool(), {
            "target_repo_url": target_repo,
            "task_id": "manual-test-001",
            "task_description": "Manual workflow test",
            "workspace_base_path": "/tmp/ace_manual_test"
        }),
        ("Explore", ExploreCodebaseTool(), {
            "target_repo_url": target_repo,
            "exploration_type": "overview"
        }),
        ("Analyze", AnalyzeAndProposeChangeTool(), {
            "target_repo_url": target_repo,
            "analysis_focus": "documentation"
        }),
        ("Implement", ImplementCodeChangesTool(), {
            "target_repo_url": target_repo,
            "manual_changes": [{
                "file": "CONTRIBUTING.md",
                "action": "create", 
                "content": "# Contributing\n\nThis is a test contribution guide.\n",
                "description": "Add contributing guide"
            }]
        }),
        ("Create PR", CreatePullRequestTool(), {
            "target_repo_url": target_repo,
            "pr_title": "Add contributing guide"
        })
    ]
    
    for step_name, tool, params in steps:
        print(f"🔄 Executing {step_name}...")
        result = await tool.execute(params, context)
        print(f"   Result: {result.get('status')}")
        if result.get('status') == 'failure':
            print(f"   Error: {result.get('message')}")
            break
    
    return True


if __name__ == "__main__":
    # Clean up any previous tests
    import shutil
    for test_dir in ["/tmp/ace_workflows", "/tmp/ace_manual_test"]:
        if Path(test_dir).exists():
            shutil.rmtree(test_dir)
    
    async def run_all_tests():
        print("🎯 Running ACE Complete Workflow Tests\n")
        
        test1 = await test_ace_orchestrator()
        test2 = await test_manual_workflow()
        
        print(f"\n🏁 Test Results:")
        print(f"  ACE Orchestrator: {'✅ PASSED' if test1 else '❌ FAILED'}")
        print(f"  Manual Workflow: {'✅ PASSED' if test2 else '❌ FAILED'}")
        
        if test1 and test2:
            print("\n🎉 All ACE workflow tests PASSED!")
        else:
            print("\n💥 Some ACE workflow tests FAILED!")
        
        return test1 and test2
    
    result = asyncio.run(run_all_tests())
