#!/usr/bin/env python3
"""
Test script for ExploreCodebaseTool
"""
import asyncio
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from chatbot.tools.developer_tools import ExploreCodebaseTool
from chatbot.tools.base import ActionContext
from chatbot.core.world_state.structures import WorldStateData


class MockWorldStateManager:
    def __init__(self):
        self.state = WorldStateData()
    
    async def get_state(self):
        return self.state
    
    async def update_state(self, new_state):
        self.state = new_state


async def test_explore_codebase():
    """Test the ExploreCodebaseTool"""
    print("🔧 Testing ExploreCodebaseTool...")
    
    # Create tool and mock context
    tool = ExploreCodebaseTool()
    
    context = ActionContext(
        world_state_manager=MockWorldStateManager()
    )
    context.world_state = WorldStateData()
    
    # Test parameters for structure exploration
    params = {
        "target_repo_url": "https://github.com/octocat/Hello-World",
        "exploration_type": "structure",
        "max_depth": 2
    }
    
    print(f"Testing structure exploration: {params}")
    
    try:
        result = await tool.execute(params, context)
        print(f"✅ Structure exploration result: {result}")
        
        # Test file content exploration
        params2 = {
            "target_repo_url": "https://github.com/octocat/Hello-World",
            "exploration_type": "file_content",
            "target_path": "README"
        }
        
        print(f"\nTesting file content exploration: {params2}")
        result2 = await tool.execute(params2, context)
        print(f"✅ File content result: {result2}")
        
        # Test overview exploration
        params3 = {
            "target_repo_url": "https://github.com/octocat/Hello-World",
            "exploration_type": "overview"
        }
        
        print(f"\nTesting overview exploration: {params3}")
        result3 = await tool.execute(params3, context)
        print(f"✅ Overview result: {result3}")
        
        return all([
            result.get("status") == "success",
            result2.get("status") == "success", 
            result3.get("status") == "success"
        ])
        
    except Exception as e:
        print(f"❌ Error executing tool: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    result = asyncio.run(test_explore_codebase())
    if result:
        print("🎉 ExploreCodebaseTool test passed!")
    else:
        print("💥 ExploreCodebaseTool test failed!")
