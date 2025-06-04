#!/usr/bin/env python3
"""
Deep debug script for git clone issue
"""
import asyncio
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from chatbot.utils.git_utils import LocalGitRepository


async def deep_debug_clone():
    """Deep debug the git clone issue"""
    print("🔧 Deep debugging git clone...")
    
    # Test the exact same setup as the tool
    target_repo_url = "https://github.com/octocat/Hello-World"
    workspace_base = "/tmp/test_ace_workspace"
    base_branch = "master"
    
    # Replicate tool logic exactly
    if target_repo_url.endswith('.git'):
        target_repo_url = target_repo_url[:-4]
    repo_parts = target_repo_url.replace('https://github.com/', '').split('/')
    repo_owner, repo_name = repo_parts
    main_repo = f"{repo_owner}/{repo_name}"
    
    workspace_path = Path(workspace_base) / repo_name
    workspace_path.mkdir(parents=True, exist_ok=True)
    
    clone_url = f"https://github.com/{main_repo}.git"
    lg = LocalGitRepository(clone_url, str(workspace_path.parent))
    
    print(f"Repository: {main_repo}")
    print(f"Clone URL: {clone_url}")
    print(f"Workspace path: {workspace_path}")
    print(f"Local base path: {lg.local_base_path}")
    print(f"Repo path: {lg.repo_path}")
    print(f"Base branch: {base_branch}")
    
    # Check if directories exist
    print(f"workspace_path.parent exists: {workspace_path.parent.exists()}")
    print(f"workspace_path exists: {workspace_path.exists()}")
    print(f"lg.repo_path exists: {lg.repo_path.exists()}")
    
    # If repo_path already exists, let's see what's in it
    if lg.repo_path.exists():
        print(f"Contents of {lg.repo_path}: {list(lg.repo_path.iterdir())}")
        
        # Check if it's a git repo
        git_dir = lg.repo_path / ".git"
        print(f"Is git repo (has .git): {git_dir.exists()}")
    
    print("\n🔄 Attempting clone...")
    
    try:
        result = await lg.clone_or_pull(branch=base_branch)
        print(f"Clone result: {result}")
        
        if result:
            current_branch = await lg.get_current_branch()
            print(f"Current branch: {current_branch}")
        else:
            print("❌ Clone failed, let's try manual git command...")
            # Try manual git clone
            import subprocess
            cmd = ['git', 'clone', clone_url, str(lg.repo_path)]
            print(f"Running: {' '.join(cmd)}")
            result = subprocess.run(cmd, cwd=str(lg.local_base_path), capture_output=True, text=True)
            print(f"Return code: {result.returncode}")
            print(f"Stdout: {result.stdout}")
            print(f"Stderr: {result.stderr}")
            
    except Exception as e:
        print(f"❌ Exception: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(deep_debug_clone())
