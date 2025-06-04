#!/usr/bin/env python3
"""
Debug script for git utilities
"""
import asyncio
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from chatbot.utils.git_utils import LocalGitRepository


async def test_git_clone():
    """Test the git clone functionality directly"""
    print("🔧 Testing git clone functionality...")
    
    # Test parameters
    repo_url = "https://github.com/octocat/Hello-World.git"
    local_path = "/tmp/test_git_direct"
    
    # Create directory
    Path(local_path).mkdir(parents=True, exist_ok=True)
    
    # Test git repository
    lg = LocalGitRepository(repo_url, local_path)
    
    print(f"Repository URL: {repo_url}")
    print(f"Local path: {local_path}")
    print(f"Repository path: {lg.repo_path}")
    
    try:
        # Test clone/pull
        print("🔄 Attempting clone/pull...")
        result = await lg.clone_or_pull(branch="master")
        print(f"Clone/pull result: {result}")
        
        if result:
            current_branch = await lg.get_current_branch()
            print(f"Current branch: {current_branch}")
            
            # List files in the repo
            if lg.repo_path.exists():
                files = list(lg.repo_path.iterdir())
                print(f"Files in repo: {[f.name for f in files]}")
        
        return result
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    result = asyncio.run(test_git_clone())
    if result:
        print("🎉 Git test passed!")
    else:
        print("💥 Git test failed!")
