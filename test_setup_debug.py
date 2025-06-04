#!/usr/bin/env python3
"""
Debug script for SetupDevelopmentWorkspaceTool
"""
import asyncio
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from chatbot.tools.developer_tools import SetupDevelopmentWorkspaceTool
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


async def test_setup_workspace():
    """Test the SetupDevelopmentWorkspaceTool"""
    print("🔧 Testing SetupDevelopmentWorkspaceTool...")
    
    # Create tool and mock context
    tool = SetupDevelopmentWorkspaceTool()
    
    # Create mock context with world state manager
    context = ActionContext(
        world_state_manager=MockWorldStateManager()
    )
    # Add world_state property for compatibility
    context.world_state = WorldStateData()
    
    # Test parameters
    params = {
        "target_repo_url": "https://github.com/octocat/Hello-World",
        "task_id": "test-task-001", 
        "task_description": "Test workspace setup",
        "base_branch": "master",  # octocat/Hello-World uses master branch
        "workspace_base_path": "/tmp/test_ace_workspace"
    }
    
    print(f"Parameters: {params}")
    
    try:
        result = await tool.execute(params, context)
        print(f"✅ Tool execution result: {result}")
        
        # Additional debugging if it failed
        if result.get("status") == "failure":
            print("\n🔍 Additional debugging...")
            target_repo_url = params["target_repo_url"]
            workspace_base = params["workspace_base_path"]
            
            # Replicate the tool's logic
            if target_repo_url.endswith('.git'):
                target_repo_url = target_repo_url[:-4]
            repo_parts = target_repo_url.replace('https://github.com/', '').split('/')
            repo_owner, repo_name = repo_parts
            main_repo = f"{repo_owner}/{repo_name}"
            
            workspace_path = Path(workspace_base) / repo_name
            print(f"workspace_path: {workspace_path}")
            print(f"workspace_path.parent: {workspace_path.parent}")
            
            clone_url = f"https://github.com/{main_repo}.git"
            print(f"clone_url: {clone_url}")
            
            # Test the exact LocalGitRepository call
            from chatbot.utils.git_utils import LocalGitRepository
            lg = LocalGitRepository(clone_url, str(workspace_path.parent))
            print(f"lg.repo_path: {lg.repo_path}")
            print(f"lg.local_base_path: {lg.local_base_path}")
            
            # Test clone directly
            print("Testing clone directly...")
            clone_result = await lg.clone_or_pull(branch=params["base_branch"])
            print(f"Direct clone result: {clone_result}")
        
        return result
        
    except Exception as e:
        print(f"❌ Error executing tool: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "failure", "error": str(e)}


if __name__ == "__main__":
    result = asyncio.run(test_setup_workspace())
    if result.get("status") == "success":
        print("🎉 Test passed!")
    else:
        print(f"💥 Test failed: {result}")
