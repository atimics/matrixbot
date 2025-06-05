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

    async def _run_command(self, *args, check=True):
        """Helper to run a git command."""
        cmd = ['git', '-C', str(self.repo_path)] + list(args)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if check and proc.returncode != 0:
            raise RuntimeError(f"Git command failed: {' '.join(cmd)}\nStderr: {stderr.decode()}")
        return stdout.decode()

    async def clone_or_pull(self, branch: str = "develop") -> bool:
        """
        Clone the repo at the given branch if it doesn't exist locally.
        Otherwise, fetch and reset to origin/<branch>.
        Returns True on success.
        """
        os.makedirs(self.local_base_path, exist_ok=True)
        if not self.repo_path.exists():
            try:
                await self._run_command('clone', '--branch', branch, self.repo_url, '.', check=True)
            except RuntimeError:
                # Fallback to cloning default and then checking out
                await self._run_command('clone', self.repo_url, '.', check=True)
                try:
                    await self._run_command('checkout', branch, check=True)
                except RuntimeError:
                    pass # Continue on default branch if checkout fails
        else:
            await self._run_command('fetch', 'origin', branch, check=True)
            await self._run_command('checkout', branch, check=True)
            await self._run_command('reset', '--hard', f'origin/{branch}', check=True)
        return True

    async def get_current_branch(self) -> Optional[str]:
        """
        Return the name of the current branch in the local repo, or None on failure.
        """
        if not self.repo_path.exists():
            return None
        try:
            return (await self._run_command('rev-parse', '--abbrev-ref', 'HEAD')).strip()
        except RuntimeError:
            return None

    async def create_branch(self, branch_name: str, base_branch: str):
        """Creates and checks out a new branch."""
        await self._run_command('checkout', '-b', branch_name, base_branch)
        return True

    async def add_remote(self, name: str, url: str):
        """Adds or updates a remote."""
        try:
            await self._run_command('remote', 'add', name, url)
        except RuntimeError:
            await self._run_command('remote', 'set-url', name, url)
        return True

    async def push(self, remote: str, branch: str):
        """Pushes a branch to a remote, setting upstream tracking."""
        await self._run_command('push', '-u', remote, branch)
        return True

    async def add_and_commit(self, message: str):
        """Stages all changes and creates a commit."""
        await self._run_command('add', '.')
        await self._run_command('commit', '-m', message)
        return True
