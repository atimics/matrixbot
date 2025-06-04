"""
Local Git repository operations wrapper (Phase 1).
"""
import os
import asyncio
from pathlib import Path
from typing import Optional


class LocalGitRepository:
    """
    Wrapper around git command-line for basic operations: clone or pull, get current branch.
    """

    def __init__(self, repo_url: str, local_base_path: str):
        """
        Args:
            repo_url: Clone URL of the repository (HTTPS or SSH).
            local_base_path: Directory under which to clone/pull the repo.
        """
        self.repo_url = repo_url
        self.local_base_path = Path(local_base_path).resolve()
        # Derive directory name from URL
        name = Path(repo_url.rstrip('/').split('/')[-1])
        if name.suffix == '.git':
            name = name.with_suffix('')
        self.repo_path = self.local_base_path / name

    async def clone_or_pull(self, branch: str = 'develop') -> bool:
        """
        Clone the repo at the given branch if it doesn't exist locally.
        Otherwise, fetch and reset to origin/<branch>.
        Returns True on success.
        """
        os.makedirs(self.local_base_path, exist_ok=True)
        if not self.repo_path.exists():
            cmd = ['git', 'clone', '-b', branch, self.repo_url, str(self.repo_path)]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(self.local_base_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            _, _ = await proc.communicate()
            return proc.returncode == 0
        # Fetch and hard-reset
        fetch_cmd = ['git', '-C', str(self.repo_path), 'fetch', 'origin', branch]
        proc1 = await asyncio.create_subprocess_exec(
            *fetch_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc1.communicate()
        reset_cmd = ['git', '-C', str(self.repo_path), 'reset', '--hard', f'origin/{branch}']
        proc2 = await asyncio.create_subprocess_exec(
            *reset_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, _ = await proc2.communicate()
        return proc2.returncode == 0

    async def get_current_branch(self) -> Optional[str]:
        """
        Return the name of the current branch in the local repo, or None on failure.
        """
        if not self.repo_path.exists():
            return None
        cmd = ['git', '-C', str(self.repo_path), 'rev-parse', '--abbrev-ref', 'HEAD']
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        out, _ = await proc.communicate()
        if proc.returncode != 0:
            return None
        return out.decode('utf-8').strip()
