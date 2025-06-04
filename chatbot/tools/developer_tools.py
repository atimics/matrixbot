"""
Developer-focused tools: codebase inspection and GitHub-local sync (Phase 1).
"""
import asyncio
import os
from typing import Any, Dict, List

from ..integrations.github_service import GitHubService
from ..utils.git_utils import LocalGitRepository
from .base import ToolInterface, ActionContext


class GetCodebaseStructureTool(ToolInterface):  # Phase 1
    """
    Retrieves the codebase file tree from GitHub (read-only) or local clone.
    """
    @property
    def name(self) -> str:
        return "GetCodebaseStructure"

    @property
    def description(self) -> str:
        return (
            "Fetch the file tree of the codebase from the specified GitHub repository and branch. "
            "Useful for understanding project structure."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "main_repo": "string - GitHub repository full name (e.g. 'owner/repo')",
            "branch": "string (optional, default: 'develop') - Branch to inspect",
            "local_base_path": "string (optional, default: '.') - Local directory for clone or pull"
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        main_repo = params.get("main_repo")
        if not main_repo:
            return {"status": "failure", "message": "Parameter 'main_repo' is required."}
        branch = params.get("branch", "develop")
        local_base = params.get("local_base_path", ".")
        # Attempt GitHub API fetch
        gh = GitHubService(main_repo=main_repo)
        try:
            tree = await gh.get_repository_tree(branch=branch)
            count = len(tree)
            return {
                "status": "success",
                "message": f"Fetched {count} items from {main_repo}@{branch}",
                "structure": tree,
            }
        except Exception:
            # Fallback to local clone
            try:
                repo_url = f"https://github.com/{main_repo}.git"
                lg = LocalGitRepository(repo_url, local_base)
                ok = await lg.clone_or_pull(branch=branch)
                if not ok:
                    raise RuntimeError("Local clone_or_pull failed")
                # Walk filesystem
                files: List[str] = []
                for root, _, filenames in os.walk(lg.repo_path):
                    for fn in filenames:
                        rel = os.path.relpath(os.path.join(root, fn), lg.repo_path)
                        files.append(rel)
                return {
                    "status": "success",
                    "message": f"Read {len(files)} files locally from {lg.repo_path}",
                    "structure": files,
                }
            except Exception as err:
                return {"status": "failure", "message": str(err)}
