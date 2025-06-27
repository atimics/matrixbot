"""
GitHub API client for repository inspection and PR status (read-only).
"""
import os
import httpx
from typing import Any, Dict, List, Optional
import asyncio
import time

from ..config import settings


class GitHubService:
    """
    Client for interacting with the GitHub API (read-only operations).
    """

    def __init__(
        self,
        token: Optional[str] = None,
        main_repo: str = ""
    ):
        """
        Initialize a GitHubService instance.

        Args:
            main_repo: Repository full name (e.g., "owner/repo")
        """
        self.token = settings.github_token
        self.main_repo = main_repo
        self.fork_owner = settings.github_username
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

    async def check_fork_exists(self) -> Optional[str]:
        """Check if a fork of the main repo exists for the bot user."""
        if not self.fork_owner:
            return None
        fork_full_name = f"{self.fork_owner}/{self.main_repo.split('/')[1]}"
        try:
            response = await self._client.get(f"repos/{fork_full_name}")
            if response.status_code == 200:
                return response.json().get("clone_url")
            return None
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    async def create_fork(self) -> Optional[Dict[str, Any]]:
        """Create a fork of the main repo under the bot's account."""
        url = f"repos/{self.main_repo}/forks"
        response = await self._client.post(url)
        if response.status_code == 202:  # Accepted
            # Forking can take time, so we need to poll until it's ready
            fork_full_name = f"{self.fork_owner}/{self.main_repo.split('/')[1]}"
            for _ in range(10):  # Poll for 10 times with 3 seconds interval
                await asyncio.sleep(3)
                fork_url = await self.check_fork_exists()
                if fork_url:
                    return {"clone_url": fork_url, "full_name": fork_full_name}
            raise RuntimeError("Fork creation timed out.")
        response.raise_for_status()
        return response.json()

    async def create_pull_request(
        self, title: str, body: str, head_branch: str, base_branch: str, is_draft: bool = True
    ) -> Optional[Dict[str, Any]]:
        """Create a pull request."""
        if not self.fork_owner:
            raise ValueError(
                "GITHUB_USERNAME must be set to create a pull request from a fork."
            )
        head = f"{self.fork_owner}:{head_branch}"
        payload = {
            "title": title,
            "body": body,
            "head": head,
            "base": base_branch,
            "draft": is_draft,
        }
        url = f"repos/{self.main_repo}/pulls"
        response = await self._client.post(url, json=payload)
        response.raise_for_status()
        return response.json()

    async def get_issues(
        self, 
        state: str = "open", 
        labels: List[str] = None,
        per_page: int = 20,
        page: int = 1
    ) -> List[Dict[str, Any]]:
        """
        Get issues from the repository.
        
        Args:
            state: Issue state ('open', 'closed', 'all')
            labels: List of label names to filter by
            per_page: Number of issues per page (max 100)
            page: Page number for pagination
        """
        url = f"repos/{self.main_repo}/issues"
        params = {
            "state": state,
            "per_page": min(per_page, 100),
            "page": page
        }
        
        if labels:
            params["labels"] = ",".join(labels)
            
        response = await self._client.get(url, params=params)
        response.raise_for_status()
        return response.json()

    async def get_issue(self, issue_number: int) -> Dict[str, Any]:
        """Get a specific issue by number."""
        url = f"repos/{self.main_repo}/issues/{issue_number}"
        response = await self._client.get(url)
        response.raise_for_status()
        return response.json()

    async def get_issue_comments(self, issue_number: int) -> List[Dict[str, Any]]:
        """Get comments for a specific issue."""
        url = f"repos/{self.main_repo}/issues/{issue_number}/comments"
        response = await self._client.get(url)
        response.raise_for_status()
        return response.json()

    async def create_issue_comment(
        self, issue_number: int, body: str
    ) -> Dict[str, Any]:
        """Create a comment on an issue."""
        url = f"repos/{self.main_repo}/issues/{issue_number}/comments"
        payload = {"body": body}
        response = await self._client.post(url, json=payload)
        response.raise_for_status()
        return response.json()

    async def create_issue(
        self,
        title: str,
        body: str = "",
        labels: List[str] = None,
        assignees: List[str] = None
    ) -> Dict[str, Any]:
        """Create a new issue."""
        payload = {
            "title": title,
            "body": body
        }
        
        if labels:
            payload["labels"] = labels
        if assignees:
            payload["assignees"] = assignees
            
        url = f"repos/{self.main_repo}/issues"
        response = await self._client.post(url, json=payload)
        response.raise_for_status()
        return response.json()

    async def update_issue(
        self,
        issue_number: int,
        title: str = None,
        body: str = None,
        state: str = None,
        labels: List[str] = None
    ) -> Dict[str, Any]:
        """Update an existing issue."""
        payload = {}
        
        if title is not None:
            payload["title"] = title
        if body is not None:
            payload["body"] = body
        if state is not None:
            payload["state"] = state
        if labels is not None:
            payload["labels"] = labels
            
        url = f"repos/{self.main_repo}/issues/{issue_number}"
        response = await self._client.patch(url, json=payload)
        response.raise_for_status()
        return response.json()

    async def close(self):
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
