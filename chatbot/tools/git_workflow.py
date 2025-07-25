"""
Git workflow utilities for the developer tools system.

This module provides improved git operations with deterministic naming
and better branch management for the ACE system.
"""
import hashlib
import re
import subprocess
import logging
from typing import Optional, List, Dict, Any
from pathlib import Path
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class GitContext:
    """Context information for git operations."""
    workspace_path: Path
    repo_url: str
    current_branch: str
    is_clean: bool
    last_commit_sha: str
    remote_branches: List[str]


class GitWorkflowManager:
    """
    Enhanced git workflow manager with deterministic naming and better error handling.
    
    Provides utilities for:
    - Deterministic branch naming
    - Safe branch creation and switching
    - Commit message validation
    - Remote synchronization
    """
    
    def __init__(self, workspace_path: Path):
        self.workspace_path = workspace_path
        self.git_dir = workspace_path / ".git"
    
    def is_git_repository(self) -> bool:
        """Check if the workspace is a git repository."""
        return self.git_dir.exists() and self.git_dir.is_dir()
    
    async def get_context(self) -> Optional[GitContext]:
        """Get current git context information."""
        if not self.is_git_repository():
            return None
        
        try:
            # Get current branch
            current_branch = await self._run_git_command(["branch", "--show-current"])
            current_branch = current_branch.strip()
            
            # Check if working directory is clean
            status_output = await self._run_git_command(["status", "--porcelain"])
            is_clean = len(status_output.strip()) == 0
            
            # Get last commit SHA
            last_commit = await self._run_git_command(["rev-parse", "HEAD"])
            last_commit_sha = last_commit.strip()
            
            # Get remote branches
            remote_branches_output = await self._run_git_command(["branch", "-r"])
            remote_branches = [
                line.strip().replace("origin/", "") 
                for line in remote_branches_output.split('\n') 
                if line.strip() and not line.strip().startswith("origin/HEAD")
            ]
            
            # Try to get remote URL
            try:
                repo_url = await self._run_git_command(["config", "--get", "remote.origin.url"])
                repo_url = repo_url.strip()
            except subprocess.CalledProcessError:
                repo_url = "unknown"
            
            return GitContext(
                workspace_path=self.workspace_path,
                repo_url=repo_url,
                current_branch=current_branch,
                is_clean=is_clean,
                last_commit_sha=last_commit_sha,
                remote_branches=remote_branches
            )
            
        except Exception as e:
            logger.exception(f"Error getting git context: {e}")
            return None
    
    def generate_deterministic_branch_name(
        self, 
        task_id: str, 
        description: str = "",
        prefix: str = "ace"
    ) -> str:
        """
        Generate a deterministic branch name based on task ID and content.
        
        Format: {prefix}/{task_id}/{short_sha}
        Where short_sha is derived from task_id + description for determinism.
        """
        # Clean task_id for use in branch name
        clean_task_id = re.sub(r'[^a-zA-Z0-9\-_]', '-', task_id)
        clean_task_id = re.sub(r'-+', '-', clean_task_id).strip('-')
        
        # Generate deterministic hash from task_id and description
        content = f"{task_id}{description}".encode('utf-8')
        content_hash = hashlib.sha256(content).hexdigest()[:8]
        
        # Ensure branch name is valid (max 250 chars, valid characters)
        branch_name = f"{prefix}/{clean_task_id}/{content_hash}"
        
        # Truncate if too long, keeping the hash at the end
        if len(branch_name) > 240:
            available_length = 240 - len(f"{prefix}//") - len(content_hash)
            truncated_task_id = clean_task_id[:available_length]
            branch_name = f"{prefix}/{truncated_task_id}/{content_hash}"
        
        return branch_name
    
    async def create_feature_branch(
        self, 
        branch_name: str, 
        base_branch: str = "main",
        force: bool = False
    ) -> Dict[str, Any]:
        """
        Create a new feature branch from the specified base branch.
        
        Returns:
            Dictionary with success status and details
        """
        try:
            context = await self.get_context()
            if not context:
                return {"success": False, "error": "Not a git repository"}
            
            # Check if branch already exists
            existing_branches = await self._run_git_command(["branch", "--list", branch_name])
            if existing_branches.strip() and not force:
                return {
                    "success": False, 
                    "error": f"Branch {branch_name} already exists",
                    "suggestion": "Use force=True to recreate the branch"
                }
            
            # Ensure we're on the base branch and it's up to date
            await self._run_git_command(["checkout", base_branch])
            
            try:
                await self._run_git_command(["pull", "origin", base_branch])
            except subprocess.CalledProcessError:
                logger.warning(f"Could not pull latest {base_branch}, continuing with local version")
            
            # Create and checkout the new branch
            if force and existing_branches.strip():
                await self._run_git_command(["branch", "-D", branch_name])
            
            await self._run_git_command(["checkout", "-b", branch_name])
            
            return {
                "success": True,
                "branch_name": branch_name,
                "base_branch": base_branch,
                "message": f"Created and switched to branch {branch_name}"
            }
            
        except subprocess.CalledProcessError as e:
            return {
                "success": False,
                "error": f"Git command failed: {e}",
                "suggestion": "Check git repository state and permissions"
            }
        except Exception as e:
            logger.exception(f"Error creating feature branch: {e}")
            return {"success": False, "error": str(e)}
    
    async def commit_changes(
        self, 
        message: str, 
        files: Optional[List[str]] = None,
        validate_message: bool = True
    ) -> Dict[str, Any]:
        """
        Commit changes with optional message validation.
        
        Args:
            message: Commit message
            files: Specific files to commit (None = all changes)
            validate_message: Whether to validate commit message format
            
        Returns:
            Dictionary with commit result
        """
        try:
            if validate_message:
                validation_result = self.validate_commit_message(message)
                if not validation_result["valid"]:
                    return {
                        "success": False,
                        "error": f"Invalid commit message: {validation_result['error']}",
                        "suggestion": validation_result.get("suggestion", "")
                    }
            
            # Stage files
            if files:
                for file_path in files:
                    await self._run_git_command(["add", file_path])
            else:
                await self._run_git_command(["add", "."])
            
            # Check if there are changes to commit
            status_output = await self._run_git_command(["status", "--porcelain", "--cached"])
            if not status_output.strip():
                return {
                    "success": False,
                    "error": "No changes staged for commit",
                    "suggestion": "Make some changes before committing"
                }
            
            # Commit changes
            await self._run_git_command(["commit", "-m", message])
            
            # Get the new commit SHA
            commit_sha = await self._run_git_command(["rev-parse", "HEAD"])
            commit_sha = commit_sha.strip()
            
            return {
                "success": True,
                "commit_sha": commit_sha,
                "message": message,
                "files_committed": len(status_output.strip().split('\n')) if status_output.strip() else 0
            }
            
        except subprocess.CalledProcessError as e:
            return {
                "success": False,
                "error": f"Git commit failed: {e}",
                "suggestion": "Check staged changes and commit message"
            }
        except Exception as e:
            logger.exception(f"Error committing changes: {e}")
            return {"success": False, "error": str(e)}
    
    def validate_commit_message(self, message: str) -> Dict[str, Any]:
        """
        Validate commit message according to conventional commit format.
        
        Expected format: type(scope): description
        Where type is one of: feat, fix, docs, style, refactor, test, chore
        """
        if not message or len(message.strip()) == 0:
            return {
                "valid": False,
                "error": "Commit message cannot be empty",
                "suggestion": "Provide a descriptive commit message"
            }
        
        lines = message.strip().split('\n')
        subject = lines[0]
        
        # Check length
        if len(subject) > 72:
            return {
                "valid": False,
                "error": "Subject line too long (max 72 characters)",
                "suggestion": "Shorten the subject line"
            }
        
        # Check conventional commit format (optional but recommended)
        conventional_pattern = re.compile(
            r'^(feat|fix|docs|style|refactor|perf|test|chore|ci|build)(\(.+\))?: .+$'
        )
        
        if not conventional_pattern.match(subject):
            # This is a warning, not an error - allow non-conventional commits
            return {
                "valid": True,
                "warning": "Consider using conventional commit format: type(scope): description",
                "suggestion": "Example: feat(api): add user authentication endpoint"
            }
        
        return {"valid": True}
    
    async def push_branch(
        self, 
        branch_name: str, 
        remote: str = "origin",
        force: bool = False
    ) -> Dict[str, Any]:
        """
        Push branch to remote repository.
        
        Args:
            branch_name: Name of branch to push
            remote: Remote name (default: origin)
            force: Whether to force push
            
        Returns:
            Dictionary with push result
        """
        try:
            context = await self.get_context()
            if not context:
                return {"success": False, "error": "Not a git repository"}
            
            # Build push command
            push_args = ["push", remote, branch_name]
            if force:
                push_args.insert(1, "--force-with-lease")  # Safer than --force
            
            await self._run_git_command(push_args)
            
            return {
                "success": True,
                "branch_name": branch_name,
                "remote": remote,
                "message": f"Successfully pushed {branch_name} to {remote}"
            }
            
        except subprocess.CalledProcessError as e:
            error_message = str(e)
            
            # Provide helpful error messages
            if "rejected" in error_message.lower():
                suggestion = "Try pulling latest changes or use force push if necessary"
            elif "permission denied" in error_message.lower():
                suggestion = "Check authentication credentials and repository permissions"
            else:
                suggestion = "Check network connection and remote repository URL"
            
            return {
                "success": False,
                "error": f"Push failed: {e}",
                "suggestion": suggestion
            }
        except Exception as e:
            logger.exception(f"Error pushing branch: {e}")
            return {"success": False, "error": str(e)}
    
    async def _run_git_command(self, args: List[str]) -> str:
        """
        Run a git command and return the output.
        
        Args:
            args: Git command arguments
            
        Returns:
            Command output as string
            
        Raises:
            subprocess.CalledProcessError: If command fails
        """
        cmd = ["git"] + args
        
        logger.debug(f"Running git command: {' '.join(cmd)}")
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=self.workspace_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            error_msg = stderr.decode('utf-8').strip()
            logger.error(f"Git command failed: {' '.join(cmd)}, error: {error_msg}")
            raise subprocess.CalledProcessError(
                process.returncode or -1, 
                cmd, 
                output=stdout, 
                stderr=stderr
            )
        
        return stdout.decode('utf-8')
    
    async def get_changed_files(self, base_branch: str = "main") -> List[str]:
        """
        Get list of files changed compared to base branch.
        
        Args:
            base_branch: Branch to compare against
            
        Returns:
            List of changed file paths
        """
        try:
            # Get files changed compared to base branch
            output = await self._run_git_command([
                "diff", "--name-only", f"{base_branch}...HEAD"
            ])
            
            changed_files = [
                line.strip() for line in output.split('\n') 
                if line.strip()
            ]
            
            return changed_files
            
        except subprocess.CalledProcessError:
            logger.warning(f"Could not get changed files compared to {base_branch}")
            return []
    
    async def get_commit_stats(self, commit_sha: Optional[str] = None) -> Dict[str, Any]:
        """
        Get statistics for a commit.
        
        Args:
            commit_sha: Commit to analyze (None = HEAD)
            
        Returns:
            Dictionary with commit statistics
        """
        try:
            sha = commit_sha or "HEAD"
            
            # Get commit info
            commit_info = await self._run_git_command([
                "show", "--stat", "--format=%H|%an|%ae|%ad|%s", sha
            ])
            
            lines = commit_info.strip().split('\n')
            if not lines:
                return {}
            
            # Parse commit header
            header_parts = lines[0].split('|')
            if len(header_parts) >= 5:
                commit_data = {
                    "sha": header_parts[0],
                    "author_name": header_parts[1],
                    "author_email": header_parts[2],
                    "date": header_parts[3],
                    "subject": header_parts[4],
                    "files_changed": [],
                    "insertions": 0,
                    "deletions": 0
                }
                
                # Parse file changes
                for line in lines[1:]:
                    if ' | ' in line and ('++' in line or '--' in line):
                        parts = line.split(' | ')
                        if len(parts) >= 2:
                            file_path = parts[0].strip()
                            commit_data["files_changed"].append(file_path)
                    elif 'insertion' in line or 'deletion' in line:
                        # Parse summary line
                        import re
                        insertions_match = re.search(r'(\d+) insertion', line)
                        deletions_match = re.search(r'(\d+) deletion', line)
                        
                        if insertions_match:
                            commit_data["insertions"] = int(insertions_match.group(1))
                        if deletions_match:
                            commit_data["deletions"] = int(deletions_match.group(1))
                
                return commit_data
            
            return {}
            
        except subprocess.CalledProcessError as e:
            logger.warning(f"Could not get commit stats for {commit_sha}: {e}")
            return {}


# Import subprocess and asyncio here to avoid import issues
import subprocess
import asyncio
