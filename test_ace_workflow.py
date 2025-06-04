#!/usr/bin/env python3
"""
Test script for full ACE Phase 1 workflow
"""
import asyncio
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from chatbot.tools.developer_tools import SetupDevelopmentWorkspaceTool, ExploreCodebaseTool
from chatbot.tools.base import ActionContext
from chatbot.core.world_state.structures import WorldStateData


class MockWorldStateManager:
    def __init__(self):
        self.state = WorldStateData()
    
    async def get_state(self):
        return self.state
    
    async def update_state(self, new_state):
        self.state = new_state
        print(f"World state updated: {len(self.state.target_repositories)} target repos")


async def test_full_ace_workflow():
    """Test the complete ACE Phase 1 workflow"""
    print("🚀 Testing complete ACE Phase 1 workflow...")
    
    # Shared context
    context = ActionContext(
        world_state_manager=MockWorldStateManager()
    )
    context.world_state = WorldStateData()
    
    # Step 1: Setup Development Workspace
    print("\n📁 Step 1: Setting up development workspace...")
    setup_tool = SetupDevelopmentWorkspaceTool()
    setup_params = {
        "target_repo_url": "https://github.com/octocat/Hello-World",
        "task_id": "ace-test-001", 
        "task_description": "Test ACE workflow",
        "base_branch": "master",
        "workspace_base_path": "/tmp/ace_workflow_test"
    }
    
    setup_result = await setup_tool.execute(setup_params, context)
    print(f"Setup result: {setup_result}")
    
    if setup_result.get("status") != "success":
        print("❌ Setup failed, aborting workflow test")
        return False
    
    # Step 2: Explore Codebase Structure
    print("\n🔍 Step 2: Exploring codebase structure...")
    explore_tool = ExploreCodebaseTool()
    
    # Test structure exploration
    structure_params = {
        "target_repo_url": "https://github.com/octocat/Hello-World",
        "exploration_type": "structure",
        "max_depth": 3
    }
    
    structure_result = await explore_tool.execute(structure_params, context)
    print(f"Structure exploration result: {structure_result}")
    
    # Test file content exploration
    print("\n📄 Step 3: Reading file content...")
    content_params = {
        "target_repo_url": "https://github.com/octocat/Hello-World",
        "exploration_type": "file_content",
        "target_path": "README"
    }
    
    content_result = await explore_tool.execute(content_params, context)
    print(f"File content result: {content_result}")
    
    # Test overview generation
    print("\n📊 Step 4: Generating codebase overview...")
    overview_params = {
        "target_repo_url": "https://github.com/octocat/Hello-World",
        "exploration_type": "overview"
    }
    
    overview_result = await explore_tool.execute(overview_params, context)
    print(f"Overview result: {overview_result}")
    
    # Check all results
    all_success = all([
        setup_result.get("status") == "success",
        structure_result.get("status") == "success",
        content_result.get("status") == "success",
        overview_result.get("status") == "success"
    ])
    
    return all_success


if __name__ == "__main__":
    # Clean up any previous test
    import shutil
    test_dir = Path("/tmp/ace_workflow_test")
    if test_dir.exists():
        shutil.rmtree(test_dir)
    
    result = asyncio.run(test_full_ace_workflow())
    if result:
        print("\n🎉 Complete ACE Phase 1 workflow test PASSED!")
    else:
        print("\n💥 ACE Phase 1 workflow test FAILED!")
