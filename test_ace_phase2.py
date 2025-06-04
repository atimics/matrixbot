#!/usr/bin/env python3
"""
Test script for ACE Phase 2 tools
"""
import asyncio
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from chatbot.tools.developer_tools import (
    SetupDevelopmentWorkspaceTool, 
    AnalyzeAndProposeChangeTool,
    ImplementCodeChangesTool
)
from chatbot.tools.base import ActionContext
from chatbot.core.world_state.structures import WorldStateData


class MockWorldStateManager:
    def __init__(self):
        self.state = WorldStateData()
    
    async def get_state(self):
        return self.state
    
    async def update_state(self, new_state):
        self.state = new_state
        print(f"World state updated: {len(self.state.target_repositories)} repos, {len(self.state.development_tasks)} tasks")


async def test_phase2_workflow():
    """Test the ACE Phase 2 workflow"""
    print("🚀 Testing ACE Phase 2 workflow...")
    
    # Shared context
    context = ActionContext(
        world_state_manager=MockWorldStateManager()
    )
    context.world_state = WorldStateData()
    
    # Step 1: Setup workspace (prerequisite)
    print("\n📁 Step 1: Setting up development workspace...")
    setup_tool = SetupDevelopmentWorkspaceTool()
    setup_params = {
        "target_repo_url": "https://github.com/octocat/Hello-World",
        "task_id": "ace-phase2-test", 
        "task_description": "Test Phase 2 workflow",
        "base_branch": "master",
        "workspace_base_path": "/tmp/ace_phase2_test"
    }
    
    setup_result = await setup_tool.execute(setup_params, context)
    print(f"Setup result: {setup_result['status']}")
    
    if setup_result.get("status") != "success":
        print("❌ Setup failed, aborting test")
        return False
    
    # Step 2: Analyze and propose changes
    print("\n🔍 Step 2: Analyzing codebase and generating proposals...")
    analyze_tool = AnalyzeAndProposeChangeTool()
    analyze_params = {
        "target_repo_url": "https://github.com/octocat/Hello-World",
        "analysis_focus": "code_quality",
        "context_description": "Simple Hello World repository analysis"
    }
    
    analyze_result = await analyze_tool.execute(analyze_params, context)
    print(f"Analysis result: {analyze_result}")
    
    if analyze_result.get("status") != "success":
        print("❌ Analysis failed")
        return False
    
    # Step 3: Implement code changes
    print("\n⚡ Step 3: Implementing code changes...")
    implement_tool = ImplementCodeChangesTool()
    
    # Test with manual changes first
    implement_params = {
        "target_repo_url": "https://github.com/octocat/Hello-World",
        "manual_changes": [
            {
                "file": "ENHANCEMENT.md",
                "action": "create",
                "content": "# ACE Enhancement\n\nThis file was created by the Autonomous Code Evolution system.\n\n## Changes Applied\n- Added documentation\n- Improved code structure\n",
                "description": "Add ACE enhancement documentation"
            }
        ],
        "commit_message": "ACE: Add enhancement documentation"
    }
    
    implement_result = await implement_tool.execute(implement_params, context)
    print(f"Implementation result: {implement_result}")
    
    success = all([
        setup_result.get("status") == "success",
        analyze_result.get("status") == "success",
        implement_result.get("status") == "success"
    ])
    
    return success


if __name__ == "__main__":
    # Clean up any previous test
    import shutil
    test_dir = Path("/tmp/ace_phase2_test")
    if test_dir.exists():
        shutil.rmtree(test_dir)
    
    result = asyncio.run(test_phase2_workflow())
    if result:
        print("\n🎉 ACE Phase 2 workflow test PASSED!")
    else:
        print("\n💥 ACE Phase 2 workflow test FAILED!")
