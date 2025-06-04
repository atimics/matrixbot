"""
GitHub API client for repository inspection and PR status (read-only).
"""
import os
import httpx
from typing import Any, Dict, List, Optional


class GitHubService:
    """
    Client for interacting with the GitHub API (read-only operations).
    """

    def __init__(
        self,
        token: Optional[str] = None,
        main_repo: str = "",
        fork_owner: Optional[str] = None,
    ):
        """
        Initialize a GitHubService instance.

        Args:
            token: GitHub Personal Access Token (env GITHUB_TOKEN if None)
            main_repo: Repository full name (e.g., "owner/repo")
            fork_owner: Username that owns the fork (unused for read-only)
        """
        self.token = token or os.getenv("GITHUB_TOKEN")
        self.main_repo = main_repo
        self.fork_owner = fork_owner
        self._client = httpx.AsyncClient(
            base_url="https://api.github.com/",
            headers={"Authorization": f"token {self.token}"} if self.token else {},
        )

    async def get_repository_tree(
        self, branch: str = "develop", path: str = ""
    ) -> List[Dict[str, Any]]:
        """
        Retrieve the file tree of the repository for a given branch and path.

        Returns a list of objects with keys: path, mode, type, sha, size, url.
        """
        url = f"repos/{self.main_repo}/git/trees/{branch}?recursive=1"
        response = await self._client.get(url)
        response.raise_for_status()
        data = response.json()
        tree = data.get("tree", [])
        if path:
            tree = [item for item in tree if item.get("path", "").startswith(path)]
        return tree

    async def get_file_content(
        self, file_path: str, branch: str = "develop"
    ) -> Optional[str]:
        """
        Get the content of a file at a given path and branch.
        """
        url = f"repos/{self.main_repo}/contents/{file_path}?ref={branch}"
        response = await self._client.get(url)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        data = response.json()
        content = data.get("content")
        encoding = data.get("encoding")
        if content and encoding == "base64":
            import base64

            return base64.b64decode(content).decode("utf-8")
        return None

    async def get_pull_request_status(
        self, pr_number: int
    ) -> Dict[str, Any]:
        """
        Fetch status of a pull request (CI status, mergeable, reviews).
        """
        url = f"repos/{self.main_repo}/pulls/{pr_number}"
        response = await self._client.get(url)
        response.raise_for_status()
        pr = response.json()
        # Simplified status representation
        return {
            "number": pr.get("number"),
            "state": pr.get("state"),
            "mergeable": pr.get("mergeable"),
            "merged": pr.get("merged"),
            "title": pr.get("title"),
            "url": pr.get("html_url"),
        }
