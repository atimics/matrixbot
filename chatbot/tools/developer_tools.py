"""
Autonomous Code Evolution (ACE) Developer Tools

This module implements the core toolset for the ACE system, enabling the AI to:
- Set up development workspaces for target repositories
- Explore and analyze codebases 
- Propose and implement code changes
- Manage the complete development lifecycle from proposal to PR

Phase 1: Workspace setup, exploration, and basic code interaction
Phase 2: AI-driven proposal generation and implementation
Phase 3: Full ACE lifecycle orchestration with learning
"""
import asyncio
import os
import json
from typing import Any, Dict, List, Optional
from pathlib import Path
import logging

from ..integrations.github_service import GitHubService
from ..config import settings
from ..utils.git_utils import LocalGitRepository
from .base import ToolInterface, ActionContext

logger = logging.getLogger(__name__)

# Security configuration for developer tools
class DeveloperToolsSecurity:
    """Security controls for developer tools."""
    
    def __init__(self):
        self.enabled = os.getenv("DEVELOPER_TOOLS_ENABLED", "false").lower() == "true"
        self.sandbox_path = Path(os.getenv("DEVELOPER_TOOLS_SANDBOX", "/app/workspace"))
        self.admin_key = os.getenv("DEVELOPER_TOOLS_ADMIN_KEY")
        self.allowed_repos = self._get_allowed_repos()
    
    def _get_allowed_repos(self) -> List[str]:
        """Get list of allowed repositories from environment."""
        repos_env = os.getenv("DEVELOPER_TOOLS_ALLOWED_REPOS", "")
        if repos_env:
            return [repo.strip() for repo in repos_env.split(",")]
        return []
    
    def is_enabled(self) -> bool:
        """Check if developer tools are enabled."""
        return self.enabled
    
    def validate_admin_access(self, context: ActionContext) -> bool:
        """Validate admin access for dangerous operations."""
        if not self.admin_key:
            logger.warning("DEVELOPER_TOOLS_ADMIN_KEY not configured - blocking admin operations")
            return False
        
        # In a real implementation, this would check the request context
        # for the admin key or validate user permissions
        return True
    
    def validate_repo_access(self, repo_name: str) -> bool:
        """Validate access to a specific repository."""
        if not self.allowed_repos:
            # If no restrictions configured, allow all
            return True
        return repo_name in self.allowed_repos
    
    def sanitize_path(self, path: str) -> Path:
        """Sanitize and validate file paths to prevent path traversal."""
        # Convert to Path object and resolve
        requested_path = Path(path).resolve()
        
        # Ensure path is within sandbox
        try:
            requested_path.relative_to(self.sandbox_path.resolve())
        except ValueError:
            raise ValueError(f"Path {requested_path} is outside allowed sandbox {self.sandbox_path}")
        
        return requested_path
    
    def setup_sandbox(self):
        """Set up the sandbox directory."""
        self.sandbox_path.mkdir(parents=True, exist_ok=True)
        
        # Create .gitignore to prevent accidental commits
        gitignore = self.sandbox_path / ".gitignore"
        if not gitignore.exists():
            with open(gitignore, "w") as f:
                f.write("# Developer tools sandbox - do not commit\n*\n")

# Global security instance
_security = DeveloperToolsSecurity()

def require_developer_tools_enabled(func):
    """Decorator to require developer tools to be enabled."""
    async def wrapper(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        if not _security.is_enabled():
            return {
                "status": "error",
                "message": "Developer tools are disabled. Set DEVELOPER_TOOLS_ENABLED=true to enable.",
                "security_notice": "These tools can modify code and should only be enabled in secure environments."
            }
        return await func(self, params, context)
    return wrapper

def require_admin_access(func):
    """Decorator to require admin access for dangerous operations."""
    async def wrapper(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        # First check if developer tools are enabled
        if not _security.is_enabled():
            return {
                "status": "error", 
                "message": "Developer tools are disabled",
                "security_notice": "Set DEVELOPER_TOOLS_ENABLED=true to enable developer tools"
            }
        
        # Check admin key in parameters
        admin_key = params.get("admin_key")
        if not admin_key:
            return {
                "status": "error",
                "message": "Admin key required for this operation",
                "security_notice": "Pass 'admin_key' parameter with valid admin key"
            }
        
        if admin_key != _security.admin_key:
            logger.warning(f"Invalid admin key attempt for {func.__name__}")
            return {
                "status": "error",
                "message": "Invalid admin key",
                "security_notice": "This incident has been logged"
            }
        
        # Remove admin key from params before processing
        filtered_params = {k: v for k, v in params.items() if k != "admin_key"}
        return await func(self, filtered_params, context)
    return wrapper

def validate_sandbox_path(func):
    """Decorator to validate and sanitize file paths."""
    async def wrapper(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        # Validate any path parameters
        path_params = ["path", "file_path", "workspace_path", "target_path"]
        
        for param_name in path_params:
            if param_name in params:
                try:
                    # Sanitize and validate the path
                    sanitized_path = _security.sanitize_path(params[param_name])
                    params[param_name] = str(sanitized_path)
                except ValueError as e:
                    logger.error(f"Path validation failed for {param_name}: {e}")
                    return {
                        "status": "error",
                        "message": f"Invalid path: {e}",
                        "security_notice": "Path must be within allowed sandbox directory"
                    }
        
        return await func(self, params, context)
    return wrapper

# ==============================================================================
# GitHub-Centric ACE Tools (Phase 2 - New Architecture)
# ==============================================================================

class GetGitHubIssuesTool(ToolInterface):
    """
    Fetch open issues from a GitHub repository with filtering capabilities.
    This is the primary entry point for AI to discover work.
    """
    @property
    def name(self) -> str:
        return "GetGitHubIssues"

    @property
    def description(self) -> str:
        return (
            "Fetch open issues from a GitHub repository. Use this to discover "
            "available work items, bugs to fix, or features to implement. "
            "Filter by labels to find specific types of work."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "repo_full_name": "string - Repository name in format 'owner/repo'",
            "labels": "array of strings (optional) - Filter by labels (e.g. ['bug', 'enhancement', 'good first issue'])",
            "state": "string (optional, default: 'open') - Issue state: 'open', 'closed', 'all'",
            "limit": "integer (optional, default: 20) - Maximum number of issues to return (max 100)"
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        repo_full_name = params.get("repo_full_name")
        if not repo_full_name:
            return {"status": "failure", "message": "repo_full_name is required"}
        
        labels = params.get("labels", [])
        state = params.get("state", "open")
        limit = params.get("limit", 20)
        
        try:
            gh = GitHubService(main_repo=repo_full_name)
            issues = await gh.get_issues(
                state=state,
                labels=labels,
                per_page=limit
            )
            
            # Format for AI consumption
            formatted_issues = []
            for issue in issues:
                # Skip pull requests (they appear in issues API)
                if issue.get("pull_request"):
                    continue
                    
                formatted_issues.append({
                    "number": issue["number"],
                    "title": issue["title"],
                    "state": issue["state"],
                    "labels": [label["name"] for label in issue["labels"]],
                    "created_at": issue["created_at"],
                    "updated_at": issue["updated_at"],
                    "url": issue["html_url"],
                    "author": issue["user"]["login"],
                    "assignees": [assignee["login"] for assignee in issue.get("assignees", [])],
                    "body_preview": (issue["body"][:200] + "..." if issue["body"] and len(issue["body"]) > 200 else issue["body"] or "")
                })
            
            await gh.close()
            
            return {
                "status": "success",
                "issues": formatted_issues,
                "total_count": len(formatted_issues),
                "repository": repo_full_name,
                "filters_applied": {
                    "state": state,
                    "labels": labels,
                    "limit": limit
                }
            }
            
        except Exception as e:
            return {
                "status": "failure", 
                "message": f"Failed to fetch issues from {repo_full_name}: {str(e)}"
            }


class GetGitHubIssueDetailsTool(ToolInterface):
    """
    Get comprehensive details of a specific GitHub issue including comments.
    Use this to understand the full context before proposing solutions.
    """
    @property
    def name(self) -> str:
        return "GetGitHubIssueDetails"

    @property
    def description(self) -> str:
        return (
            "Get full details of a specific GitHub issue including description, "
            "comments, and metadata. Use this to understand the complete context "
            "before analyzing or implementing solutions."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "repo_full_name": "string - Repository name in format 'owner/repo'",
            "issue_number": "integer - Issue number to retrieve"
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        repo_full_name = params.get("repo_full_name")
        issue_number = params.get("issue_number")
        
        if not repo_full_name or not issue_number:
            return {
                "status": "failure", 
                "message": "Both repo_full_name and issue_number are required"
            }
        
        try:
            gh = GitHubService(main_repo=repo_full_name)
            
            # Get issue details
            issue = await gh.get_issue(issue_number)
            
            # Skip if this is actually a pull request
            if issue.get("pull_request"):
                await gh.close()
                return {
                    "status": "failure",
                    "message": f"#{issue_number} is a pull request, not an issue"
                }
            
            # Get comments
            comments = await gh.get_issue_comments(issue_number)
            
            formatted_comments = []
            for comment in comments:
                formatted_comments.append({
                    "id": comment["id"],
                    "author": comment["user"]["login"],
                    "created_at": comment["created_at"],
                    "updated_at": comment["updated_at"],
                    "body": comment["body"],
                    "url": comment["html_url"]
                })
            
            await gh.close()
            
            return {
                "status": "success",
                "issue": {
                    "number": issue["number"],
                    "title": issue["title"],
                    "body": issue["body"] or "",
                    "state": issue["state"],
                    "labels": [label["name"] for label in issue["labels"]],
                    "assignees": [assignee["login"] for assignee in issue.get("assignees", [])],
                    "milestone": issue.get("milestone", {}).get("title") if issue.get("milestone") else None,
                    "created_at": issue["created_at"],
                    "updated_at": issue["updated_at"],
                    "closed_at": issue.get("closed_at"),
                    "url": issue["html_url"],
                    "author": issue["user"]["login"]
                },
                "comments": formatted_comments,
                "comment_count": len(formatted_comments),
                "repository": repo_full_name
            }
            
        except Exception as e:
            return {
                "status": "failure",
                "message": f"Failed to fetch details for issue #{issue_number} in {repo_full_name}: {str(e)}"
            }


class CommentOnGitHubIssueTool(ToolInterface):
    """
    Add a comment to a GitHub issue for communication and status updates.
    """
    @property
    def name(self) -> str:
        return "CommentOnGitHubIssue"

    @property
    def description(self) -> str:
        return (
            "Add a comment to a GitHub issue. Use this to ask clarifying questions, "
            "provide analysis results, give status updates, or propose solutions. "
            "Comments support Markdown formatting."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "repo_full_name": "string - Repository name in format 'owner/repo'",
            "issue_number": "integer - Issue number to comment on",
            "comment_body": "string - Comment text (supports Markdown formatting)"
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        repo_full_name = params.get("repo_full_name")
        issue_number = params.get("issue_number")
        comment_body = params.get("comment_body")
        
        # Validate required parameters
        if not repo_full_name or not issue_number or not comment_body:
            return {
                "status": "failure", 
                "message": "repo_full_name, issue_number, and comment_body are all required"
            }
        
        # Convert types safely
        try:
            repo_full_name = str(repo_full_name)
            issue_number = int(issue_number)
            comment_body = str(comment_body)
        except (ValueError, TypeError) as e:
            return {
                "status": "failure",
                "message": f"Invalid parameter types: {e}"
            }
        
        # Add AI signature to comments for transparency
        ai_signature = "\n\n---\n*Comment posted by AI Assistant*"
        full_comment = comment_body + ai_signature
        
        try:
            gh = GitHubService(main_repo=repo_full_name)
            
            comment = await gh.create_issue_comment(issue_number, full_comment)
            
            await gh.close()
            
            return {
                "status": "success",
                "comment": {
                    "id": comment["id"],
                    "url": comment["html_url"],
                    "created_at": comment["created_at"]
                },
                "issue_number": issue_number,
                "repository": repo_full_name,
                "message": f"Successfully posted comment on issue #{issue_number}"
            }
            
        except Exception as e:
            return {
                "status": "failure",
                "message": f"Failed to create comment on issue #{issue_number} in {repo_full_name}: {str(e)}"
            }


class CreateGitHubIssueTool(ToolInterface):
    """
    Create a new GitHub issue for tracking bugs, features, or analysis results.
    """
    @property
    def name(self) -> str:
        return "CreateGitHubIssue"

    @property
    def description(self) -> str:
        return (
            "Create a new GitHub issue. Use this when analysis reveals problems "
            "that need tracking, or when proposing new features or improvements. "
            "Issues support Markdown formatting and labels."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "repo_full_name": "string - Repository name in format 'owner/repo'",
            "title": "string - Issue title (clear and descriptive)",
            "body": "string - Issue description (supports Markdown)",
            "labels": "array of strings (optional) - Labels to apply (e.g. ['bug', 'enhancement'])",
            "assignees": "array of strings (optional) - GitHub usernames to assign"
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        repo_full_name = params.get("repo_full_name")
        title = params.get("title")
        body = params.get("body", "")
        labels = params.get("labels", [])
        assignees = params.get("assignees", [])
        
        if not repo_full_name or not title:
            return {
                "status": "failure",
                "message": "repo_full_name and title are required"
            }
        
        # Add AI signature to issue body for transparency
        ai_signature = "\n\n---\n*Issue created by AI Assistant*"
        full_body = body + ai_signature
        
        try:
            gh = GitHubService(main_repo=repo_full_name)
            
            issue = await gh.create_issue(
                title=title,
                body=full_body,
                labels=labels,
                assignees=assignees
            )
            
            await gh.close()
            
            return {
                "status": "success",
                "issue": {
                    "number": issue["number"],
                    "title": issue["title"],
                    "url": issue["html_url"],
                    "created_at": issue["created_at"]
                },
                "repository": repo_full_name,
                "message": f"Successfully created issue #{issue['number']}: {title}"
            }
            
        except Exception as e:
            return {
                "status": "failure",
                "message": f"Failed to create issue in {repo_full_name}: {str(e)}"
            }


class AnalyzeChannelForIssuesTool(ToolInterface):
    """
    Analyze channel discussions to identify potential GitHub issues.
    Replacement for the deprecated SummarizeChannelTool.
    """
    @property
    def name(self) -> str:
        return "AnalyzeChannelForIssues"

    @property
    def description(self) -> str:
        return (
            "Analyze recent channel messages to identify bugs, feature requests, "
            "or issues that should be tracked in GitHub. Can optionally create "
            "GitHub issues directly from the analysis."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "channel_id": "string - Channel ID to analyze",
            "message_limit": "integer (optional, default: 20) - Number of recent messages to analyze",
            "repo_full_name": "string (optional) - Repository to create issues in if found",
            "create_issues": "boolean (optional, default: false) - Whether to automatically create GitHub issues",
            "focus": "string (optional, default: 'all') - Focus on: 'bugs', 'features', 'improvements', 'all'"
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        channel_id = params.get("channel_id")
        if not channel_id:
            return {"status": "failure", "message": "channel_id is required"}
        
        message_limit = params.get("message_limit", 20)
        repo_full_name = params.get("repo_full_name")
        create_issues = params.get("create_issues", False)
        focus = params.get("focus", "all")
        
        if not context.world_state_manager:
            return {"status": "failure", "message": "World state manager not available"}
        
        messages = context.world_state_manager.state.get_recent_messages(channel_id, message_limit)
        if not messages:
            return {"status": "failure", "message": f"No messages found in channel {channel_id}"}
        
        # Analyze messages for potential issues
        potential_issues = []
        
        for msg in messages:
            if not msg.content:
                continue
                
            content_lower = msg.content.lower()
            
            # Bug indicators
            bug_keywords = ["error", "bug", "broken", "issue", "problem", "fail", "crash", "doesn't work", "not working"]
            feature_keywords = ["feature", "add", "new", "implement", "enhancement", "improve", "should", "could", "would be nice"]
            
            is_bug = any(keyword in content_lower for keyword in bug_keywords)
            is_feature = any(keyword in content_lower for keyword in feature_keywords)
            
            if (focus == "all" or 
                (focus == "bugs" and is_bug) or 
                (focus == "features" and is_feature) or
                (focus == "improvements" and (is_bug or is_feature))):
                
                issue_type = "bug" if is_bug else "enhancement" if is_feature else "discussion"
                
                potential_issues.append({
                    "type": issue_type,
                    "message_id": getattr(msg, 'id', 'unknown'),
                    "sender": msg.sender,
                    "content": msg.content,
                    "timestamp": msg.timestamp,
                    "suggested_title": self._generate_issue_title(msg.content, issue_type),
                    "priority": "high" if is_bug else "medium"
                })
        
        # Create GitHub issues if requested
        created_issues = []
        if create_issues and repo_full_name and potential_issues:
            create_tool = CreateGitHubIssueTool()
            
            for issue_data in potential_issues[:5]:  # Limit to 5 issues to avoid spam
                title = issue_data["suggested_title"]
                body = f"""## Issue identified from channel discussion

**Original message from:** {issue_data['sender']}
**Timestamp:** {issue_data['timestamp']}
**Type:** {issue_data['type']}

**Content:**
{issue_data['content']}

**Analysis:** This {issue_data['type']} was identified through automated analysis of channel discussions.
"""
                
                labels = [issue_data["type"]]
                if issue_data["priority"] == "high":
                    labels.append("priority-high")
                
                result = await create_tool.execute({
                    "repo_full_name": repo_full_name,
                    "title": title,
                    "body": body,
                    "labels": labels
                }, context)
                
                if result.get("status") == "success":
                    created_issues.append(result["issue"])
        
        return {
            "status": "success",
            "analysis": {
                "channel_id": channel_id,
                "messages_analyzed": len(messages),
                "potential_issues_found": len(potential_issues),
                "focus": focus
            },
            "potential_issues": potential_issues,
            "created_issues": created_issues,
            "summary": f"Analyzed {len(messages)} messages and found {len(potential_issues)} potential issues"
        }
    
    def _generate_issue_title(self, content: str, issue_type: str) -> str:
        """Generate a concise issue title from message content."""
        # Take first sentence or first 60 chars
        first_sentence = content.split('.')[0].split('!')[0].split('?')[0]
        title = first_sentence[:60].strip()
        
        if issue_type == "bug":
            return f"Bug: {title}"
        elif issue_type == "enhancement":
            return f"Feature: {title}"
        else:
            return f"Discussion: {title}"


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


class SetupDevelopmentWorkspaceTool(ToolInterface):
    """
    Sets up a complete development workspace for a target repository.
    
    This is the first step in any ACE workflow - it creates/updates the fork,
    clones locally, sets up the workspace, and updates the world state.
    """
    @property
    def name(self) -> str:
        return "SetupDevelopmentWorkspace"

    @property
    def description(self) -> str:
        return (
            "Set up a development workspace for a target GitHub repository. "
            "Creates fork if needed, clones locally, creates feature branch, "
            "and prepares the workspace for ACE operations."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "target_repo_url": "string - GitHub repository URL (e.g. 'https://github.com/owner/repo')",
            "task_id": "string - Unique task identifier for branch naming",
            "task_description": "string - Brief description for branch naming",
            "base_branch": "string (optional, default: 'develop') - Base branch to fork from",
            "workspace_base_path": "string (optional, default: './ace_workspace') - Base directory for workspaces"
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        target_repo_url = params.get("target_repo_url")
        task_id = params.get("task_id")
        task_description = params.get("task_description", "")
        base_branch = params.get("base_branch", "develop")
        workspace_base = params.get("workspace_base_path", "./ace_workspace")
        
        if not target_repo_url or not task_id:
            return {"status": "failure", "message": "target_repo_url and task_id are required"}

        if not settings.github.token or not settings.github.username:
            return {
                "status": "failure",
                "message": "GITHUB_TOKEN and GITHUB_USERNAME must be configured.",
            }

        try:
            # Extract repo owner/name from URL
            if target_repo_url.endswith('.git'):
                target_repo_url = target_repo_url[:-4]
            repo_parts = target_repo_url.replace('https://github.com/', '').split('/')
            if len(repo_parts) != 2:
                return {"status": "failure", "message": "Invalid GitHub repository URL format"}
            
            repo_owner, repo_name = repo_parts
            main_repo_full_name = f"{repo_owner}/{repo_name}"
            
            # Set up GitHub service
            gh = GitHubService(main_repo=main_repo_full_name)
            
            # 1. Check for/create a fork
            fork_clone_url = await gh.check_fork_exists()
            if not fork_clone_url:
                fork_info = await gh.create_fork()
                if not fork_info:
                    return {"status": "failure", "message": "Failed to create fork."}
                fork_clone_url = fork_info["clone_url"]

            # 2. Clone or pull the main repo locally
            workspace_path = Path(workspace_base)
            lg = LocalGitRepository(
                f"https://github.com/{main_repo_full_name}.git", str(workspace_path)
            )
            clone_success = await lg.clone_or_pull(branch=base_branch)
            if not clone_success:
                return {"status": "failure", "message": f"Failed to clone/pull repository {main_repo_full_name}"}

            # 3. Add fork as a remote with authentication
            fork_auth_url = fork_clone_url.replace('https://', f'https://{settings.github.username}:{settings.github.token}@')
            await lg.add_remote("fork", fork_auth_url)

            # 4. Create and checkout a feature branch
            feature_branch_name = f"ace-task-{task_id[:8]}-{task_description.lower().replace(' ', '-')[:20]}"
            await lg.create_branch(feature_branch_name, base_branch=f"origin/{base_branch}")
            
            # 5. Update world state
            from ..core.world_state.structures import TargetRepositoryContext
            repo_context = TargetRepositoryContext(
                url=target_repo_url,
                fork_url=fork_clone_url,
                local_clone_path=str(lg.repo_path),
                current_branch=feature_branch_name,
                active_task_id=task_id,
                setup_complete=True
            )
            
            if hasattr(context, 'world_state_manager') and context.world_state_manager:
                ws_data = context.world_state_manager.get_state_data()
                ws_data.add_target_repository(target_repo_url, repo_context)
            
            return {
                "status": "success",
                "message": f"Development workspace set up for {main_repo_full_name}",
                "workspace_path": str(lg.repo_path),
                "feature_branch": feature_branch_name,
                "base_branch": base_branch,
            }
            
        except Exception as e:
            return {"status": "failure", "message": f"Error setting up workspace: {str(e)}"}


class ExploreCodebaseTool(ToolInterface):
    """
    Explores and analyzes the structure and content of a target repository.
    
    Provides detailed information about files, directories, and code content
    to help the AI understand the codebase before making changes.
    """
    @property
    def name(self) -> str:
        return "ExploreCodebase"

    @property
    def description(self) -> str:
        return (
            "Explore the structure and content of a target repository workspace. "
            "Can analyze file trees, read specific files, or provide overviews "
            "of code organization and patterns."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "target_repo_url": "string - Repository URL to explore",
            "exploration_type": "string - 'structure' for file tree, 'file_content' for specific file, 'overview' for summary",
            "target_path": "string (optional) - Specific file or directory path to examine",
            "max_depth": "integer (optional, default: 3) - Maximum directory depth for structure exploration",
            "include_patterns": "list of strings (optional) - File patterns to include (e.g., ['*.py', '*.js'])"
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        target_repo_url = params.get("target_repo_url")
        exploration_type = params.get("exploration_type", "structure")
        target_path = params.get("target_path", "")
        max_depth = params.get("max_depth", 3)
        include_patterns = params.get("include_patterns", ["*.py", "*.js", "*.ts", "*.md", "*.yml", "*.yaml", "*.json"])
        
        if not target_repo_url:
            return {"status": "failure", "message": "target_repo_url is required"}
        
        try:
            # Get workspace path from world state
            workspace_path = None
            if hasattr(context, 'world_state_manager') and context.world_state_manager:
                ws_data = await context.world_state_manager.get_state()
                repo_context = ws_data.get_target_repository(target_repo_url)
                if repo_context and repo_context.local_clone_path:
                    workspace_path = Path(repo_context.local_clone_path)
            
            if not workspace_path or not workspace_path.exists():
                return {"status": "failure", "message": f"Workspace not found for {target_repo_url}. Run SetupDevelopmentWorkspace first."}
            
            if exploration_type == "structure":
                return await self._explore_structure(workspace_path, target_path, max_depth, include_patterns)
            elif exploration_type == "file_content":
                return await self._read_file_content(workspace_path, target_path)
            elif exploration_type == "overview":
                return await self._generate_overview(workspace_path, include_patterns)
            else:
                return {"status": "failure", "message": f"Unknown exploration_type: {exploration_type}"}
                
        except Exception as e:
            return {"status": "failure", "message": f"Error exploring codebase: {str(e)}"}

    async def _explore_structure(self, workspace_path: Path, target_path: str, max_depth: int, include_patterns: List[str]) -> Dict[str, Any]:
        """Explore directory structure."""
        import fnmatch
        
        start_path = workspace_path / target_path if target_path else workspace_path
        if not start_path.exists():
            return {"status": "failure", "message": f"Path does not exist: {target_path}"}
        
        structure = {}
        files = []
        
        def should_include(file_path: Path) -> bool:
            return any(fnmatch.fnmatch(file_path.name, pattern) for pattern in include_patterns)
        
        for root, dirs, filenames in os.walk(start_path):
            # Calculate current depth
            current_depth = len(Path(root).relative_to(start_path).parts)
            if current_depth >= max_depth:
                dirs.clear()  # Don't descend further
                continue
            
            # Filter out common directories to ignore
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['node_modules', '__pycache__', '.git']]
            
            for filename in filenames:
                file_path = Path(root) / filename
                if should_include(file_path):
                    rel_path = file_path.relative_to(workspace_path)
                    files.append({
                        "path": str(rel_path),
                        "size": file_path.stat().st_size,
                        "type": file_path.suffix[1:] if file_path.suffix else "file"
                    })
        
        return {
            "status": "success",
            "exploration_type": "structure",
            "workspace_path": str(workspace_path),
            "target_path": target_path,
            "file_count": len(files),
            "files": files[:100],  # Limit to first 100 files
            "summary": f"Found {len(files)} files matching patterns {include_patterns}"
        }

    async def _read_file_content(self, workspace_path: Path, target_path: str) -> Dict[str, Any]:
        """Read content of a specific file."""
        if not target_path:
            return {"status": "failure", "message": "target_path is required for file_content exploration"}
        
        file_path = workspace_path / target_path
        if not file_path.exists():
            return {"status": "failure", "message": f"File does not exist: {target_path}"}
        
        if not file_path.is_file():
            return {"status": "failure", "message": f"Path is not a file: {target_path}"}
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            return {
                "status": "success",
                "exploration_type": "file_content",
                "file_path": target_path,
                "content": content,
                "size": len(content),
                "lines": content.count('\n') + 1,
                "file_type": file_path.suffix[1:] if file_path.suffix else "text"
            }
        except UnicodeDecodeError:
            return {"status": "failure", "message": f"Cannot read file (binary or encoding issue): {target_path}"}

    async def _generate_overview(self, workspace_path: Path, include_patterns: List[str]) -> Dict[str, Any]:
        """Generate a high-level overview of the codebase."""
        import fnmatch
        from collections import defaultdict
        
        file_types = defaultdict(int)
        total_size = 0
        total_files = 0
        key_files = []
        
        # Look for important files
        important_files = ['README.md', 'package.json', 'requirements.txt', 'setup.py', 'Dockerfile', 'docker-compose.yml']
        
        for root, dirs, filenames in os.walk(workspace_path):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['node_modules', '__pycache__', '.git']]
            
            for filename in filenames:
                file_path = Path(root) / filename
                rel_path = file_path.relative_to(workspace_path)
                
                if any(fnmatch.fnmatch(filename, pattern) for pattern in include_patterns):
                    file_types[file_path.suffix or 'no_extension'] += 1
                    total_size += file_path.stat().st_size
                    total_files += 1
                
                if filename in important_files:
                    key_files.append(str(rel_path))
        
        return {
            "status": "success",
            "exploration_type": "overview",
            "workspace_path": str(workspace_path),
            "total_files": total_files,
            "total_size_bytes": total_size,
            "file_types": dict(file_types),
            "key_files_found": key_files,
            "summary": f"Codebase with {total_files} files across {len(file_types)} file types"
        }


class AnalyzeAndProposeChangeTool(ToolInterface):  # Phase 2 - GitHub-Centric
    """
    Analyze code and propose changes, posting results to GitHub Issues.
    
    This tool analyzes code based on GitHub Issues or general focus areas,
    then posts findings and proposals as GitHub Issue comments or creates new issues.
    """
    @property
    def name(self) -> str:
        return "AnalyzeAndProposeChange"

    @property
    def description(self) -> str:
        return (
            "Analyze a codebase and propose specific code changes. Can work with "
            "a specific GitHub issue or perform general analysis. Results are "
            "posted to GitHub issues for tracking and collaboration."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "repo_full_name": "string - Repository name in format 'owner/repo'",
            "issue_number": "integer (optional) - Specific GitHub issue to analyze",
            "analysis_focus": "string (optional) - Focus area if no issue: 'bug_fixes', 'performance', 'code_quality', 'features', 'security', 'documentation'",
            "specific_files": "list of strings (optional) - Specific files to focus analysis on",
            "context_description": "string (optional) - Additional context about what to analyze",
            "create_new_issue": "boolean (optional, default: true) - Create new issue if none specified",
            "proposal_scope": "string (optional, default: 'targeted') - 'minimal', 'targeted', or 'comprehensive'"
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        repo_full_name = params.get("repo_full_name")
        issue_number = params.get("issue_number")
        analysis_focus = params.get("analysis_focus", "code_quality")
        specific_files = params.get("specific_files", [])
        context_description = params.get("context_description", "")
        create_new_issue = params.get("create_new_issue", True)
        proposal_scope = params.get("proposal_scope", "targeted")
        
        if not repo_full_name:
            return {"status": "failure", "message": "repo_full_name is required"}
        
        try:
            # If issue_number provided, get issue context first
            issue_context = ""
            if issue_number:
                details_tool = GetGitHubIssueDetailsTool()
                issue_result = await details_tool.execute({
                    "repo_full_name": repo_full_name,
                    "issue_number": issue_number
                }, context)
                
                if issue_result.get("status") == "success":
                    issue_data = issue_result["issue"]
                    issue_context = f"GitHub Issue #{issue_number}: {issue_data['title']}\n{issue_data['body']}"
                    analysis_focus = "issue_specific"
                else:
                    return {"status": "failure", "message": f"Could not fetch issue #{issue_number}"}
            
            # Convert repo_full_name to URL format for workspace lookup
            target_repo_url = f"https://github.com/{repo_full_name}"
            
            # Find workspace path from world state
            workspace_path = await self._find_workspace_path(target_repo_url, context)
            if not workspace_path:
                return {"status": "failure", "message": f"Workspace not found for {repo_full_name}. Run SetupDevelopmentWorkspace first."}
            
            # Combine context
            full_context = f"{context_description}\n{issue_context}".strip()
            
            # Analyze codebase structure and content
            analysis_result = await self._analyze_codebase(
                workspace_path, analysis_focus, specific_files, full_context
            )
            
            # Generate AI-driven change proposals
            proposals = await self._generate_change_proposals(
                analysis_result, analysis_focus, proposal_scope, workspace_path
            )
            
            # Format analysis results for GitHub
            github_content = self._format_analysis_for_github(
                analysis_result, proposals, analysis_focus, specific_files
            )
            
            # Post to GitHub
            github_result = None
            if issue_number:
                # Comment on existing issue
                comment_tool = CommentOnGitHubIssueTool()
                github_result = await comment_tool.execute({
                    "repo_full_name": repo_full_name,
                    "issue_number": issue_number,
                    "comment_body": github_content
                }, context)
            elif create_new_issue:
                # Create new issue with analysis
                create_tool = CreateGitHubIssueTool()
                title = f"Code Analysis: {analysis_focus.replace('_', ' ').title()}"
                if specific_files:
                    title += f" ({', '.join(specific_files[:2])}{'...' if len(specific_files) > 2 else ''})"
                
                github_result = await create_tool.execute({
                    "repo_full_name": repo_full_name,
                    "title": title,
                    "body": github_content,
                    "labels": ["analysis", "enhancement"]
                }, context)
            
            # Prepare response
            result = {
                "status": "success",
                "analysis_focus": analysis_focus,
                "workspace_path": str(workspace_path),
                "proposals_count": len(proposals),
                "repository": repo_full_name
            }
            
            if github_result:
                if github_result.get("status") == "success":
                    if issue_number:
                        result["github_comment"] = github_result["comment"]
                        result["message"] = f"Posted analysis to issue #{issue_number}"
                    else:
                        result["github_issue"] = github_result["issue"]
                        result["message"] = f"Created issue #{github_result['issue']['number']} with analysis"
                else:
                    result["github_error"] = github_result.get("message")
                    result["message"] = "Analysis completed but failed to post to GitHub"
            else:
                result["message"] = "Analysis completed (no GitHub posting requested)"
            
            result["next_steps"] = "Use ImplementCodeChangesTool to apply proposed changes"
            
            return result
            
        except Exception as e:
            return {"status": "failure", "message": f"Error analyzing codebase: {str(e)}"}
    
    def _format_analysis_for_github(
        self, analysis_result: Dict[str, Any], proposals: List[Dict[str, Any]], 
        focus: str, files: List[str]
    ) -> str:
        """Format analysis results for GitHub issue/comment."""
        content = f"## Code Analysis Results\n\n"
        content += f"**Focus:** {focus.replace('_', ' ').title()}\n"
        
        if files:
            content += f"**Files Analyzed:** {', '.join(files)}\n"
        
        content += f"\n### Analysis Summary\n"
        
        if analysis_result.get("issues_found"):
            content += f"**Issues Found:** {len(analysis_result['issues_found'])}\n"
            for issue in analysis_result["issues_found"][:5]:  # Limit to 5
                content += f"- {issue.get('description', 'Issue identified')}\n"
        
        if analysis_result.get("metrics"):
            content += f"\n**Code Metrics:**\n"
            metrics = analysis_result["metrics"]
            for key, value in metrics.items():
                content += f"- {key.replace('_', ' ').title()}: {value}\n"
        
        if proposals:
            content += f"\n### Proposed Changes ({len(proposals)} total)\n"
            for i, proposal in enumerate(proposals[:3], 1):  # Show first 3
                content += f"\n#### Proposal {i}: {proposal.get('title', 'Code Change')}\n"
                content += f"**Priority:** {proposal.get('priority', 'Medium')}\n"
                content += f"**Files:** {', '.join(proposal.get('affected_files', []))}\n"
                content += f"**Description:** {proposal.get('description', 'No description')}\n"
                
                if proposal.get("implementation_plan"):
                    content += f"**Implementation:**\n{proposal['implementation_plan']}\n"
        
        content += f"\n### Next Steps\n"
        content += f"1. Review the proposed changes above\n"
        content += f"2. Use `ImplementCodeChangesTool` to apply selected changes\n"
        content += f"3. Test the implementation\n"
        content += f"4. Create a pull request with the changes\n"
        
        return content

    async def _find_workspace_path(self, target_repo_url: str, context: ActionContext) -> Optional[Path]:
        """Find the local workspace path for a target repository."""
        if hasattr(context, 'world_state_manager') and context.world_state_manager:
            ws_data = await context.world_state_manager.get_state()
            if target_repo_url in ws_data.target_repositories:
                repo_context = ws_data.target_repositories[target_repo_url]
                if repo_context.setup_complete:
                    return Path(repo_context.local_clone_path)
        return None

    async def _analyze_codebase(
        self, workspace_path: Path, focus: str, specific_files: List[str], context_desc: str
    ) -> Dict[str, Any]:
        """Analyze the codebase to identify areas for improvement."""
        analysis = {
            "focus": focus,
            "files_analyzed": [],
            "patterns_found": [],
            "issues_identified": [],
            "opportunities": []
        }
        
        # Determine files to analyze
        files_to_analyze = []
        if specific_files:
            files_to_analyze = [workspace_path / f for f in specific_files if (workspace_path / f).exists()]
        else:
            # Auto-discover relevant files based on focus
            extensions = self._get_relevant_extensions(focus)
            for ext in extensions:
                files_to_analyze.extend(workspace_path.glob(f"**/*{ext}"))
        
        # Analyze each file
        for file_path in files_to_analyze[:10]:  # Limit to avoid excessive analysis
            if file_path.is_file() and file_path.stat().st_size < 50000:  # Skip very large files
                file_analysis = await self._analyze_file(file_path, focus, context_desc)
                analysis["files_analyzed"].append(str(file_path.relative_to(workspace_path)))
                analysis["patterns_found"].extend(file_analysis.get("patterns", []))
                analysis["issues_identified"].extend(file_analysis.get("issues", []))
                analysis["opportunities"].extend(file_analysis.get("opportunities", []))
        
        return analysis

    def _get_relevant_extensions(self, focus: str) -> List[str]:
        """Get file extensions relevant to the analysis focus."""
        base_extensions = [".py", ".js", ".ts", ".java", ".cpp", ".c", ".go", ".rs"]
        
        if focus == "documentation":
            return [".md", ".txt", ".rst"] + base_extensions
        elif focus == "security":
            return base_extensions + [".yml", ".yaml", ".json", ".xml"]
        else:
            return base_extensions

    async def _analyze_file(self, file_path: Path, focus: str, context_desc: str) -> Dict[str, Any]:
        """Analyze a single file for issues and opportunities."""
        try:
            content = file_path.read_text(encoding='utf-8')
            lines = content.split('\n')
            
            analysis = {
                "patterns": [],
                "issues": [],
                "opportunities": []
            }
            
            # Basic pattern analysis based on focus
            if focus == "code_quality":
                analysis.update(self._analyze_code_quality(content, lines, file_path))
            elif focus == "performance":
                analysis.update(self._analyze_performance(content, lines, file_path))
            elif focus == "security":
                analysis.update(self._analyze_security(content, lines, file_path))
            elif focus == "documentation":
                analysis.update(self._analyze_documentation(content, lines, file_path))
            
            return analysis
            
        except Exception:
            return {"patterns": [], "issues": [], "opportunities": []}

    def _analyze_code_quality(self, content: str, lines: List[str], file_path: Path) -> Dict[str, Any]:
        """Analyze code quality issues."""
        issues = []
        opportunities = []
        patterns = []
        
        # Check for common code quality issues
        if len(lines) > 500:
            issues.append(f"Large file ({len(lines)} lines) in {file_path.name} - consider splitting")
        
        # Look for long functions (simple heuristic)
        function_lines = 0
        in_function = False
        for i, line in enumerate(lines):
            line = line.strip()
            if line.startswith('def ') or line.startswith('function ') or line.startswith('class '):
                if in_function and function_lines > 50:
                    issues.append(f"Long function/class at line {i-function_lines} in {file_path.name}")
                in_function = True
                function_lines = 0
            elif in_function:
                function_lines += 1
        
        # Look for code patterns
        if 'TODO' in content or 'FIXME' in content:
            patterns.append(f"TODO/FIXME comments found in {file_path.name}")
            opportunities.append(f"Address TODO/FIXME items in {file_path.name}")
        
        return {"patterns": patterns, "issues": issues, "opportunities": opportunities}

    def _analyze_performance(self, content: str, lines: List[str], file_path: Path) -> Dict[str, Any]:
        """Analyze performance-related issues."""
        issues = []
        opportunities = []
        patterns = []
        
        # Simple performance pattern detection
        if file_path.suffix == '.py':
            if 'for' in content and 'in range(' in content:
                patterns.append(f"Range loops found in {file_path.name}")
                opportunities.append(f"Consider optimizing range loops in {file_path.name}")
            
            if content.count('print(') > 10:
                issues.append(f"Many print statements in {file_path.name} - may impact performance")
        
        return {"patterns": patterns, "issues": issues, "opportunities": opportunities}

    def _analyze_security(self, content: str, lines: List[str], file_path: Path) -> Dict[str, Any]:
        """Analyze security-related issues."""
        issues = []
        opportunities = []
        patterns = []
        
        # Basic security pattern detection
        security_keywords = ['password', 'secret', 'api_key', 'token']
        for keyword in security_keywords:
            if keyword in content.lower():
                patterns.append(f"Security-sensitive keyword '{keyword}' found in {file_path.name}")
                opportunities.append(f"Review {keyword} handling in {file_path.name}")
        
        return {"patterns": patterns, "issues": issues, "opportunities": opportunities}

    def _analyze_documentation(self, content: str, lines: List[str], file_path: Path) -> Dict[str, Any]:
        """Analyze documentation-related issues."""
        issues = []
        opportunities = []
        patterns = []
        
        if file_path.suffix == '.py':
            # Check for missing docstrings
            function_count = content.count('def ')
            docstring_count = content.count('"""') + content.count("'''")
            
            if function_count > 0 and docstring_count < function_count:
                issues.append(f"Missing docstrings in {file_path.name}")
                opportunities.append(f"Add docstrings to functions in {file_path.name}")
        
        return {"patterns": patterns, "issues": issues, "opportunities": opportunities}

    async def _generate_change_proposals(
        self, analysis: Dict[str, Any], focus: str, scope: str, workspace_path: Path
    ) -> List[Dict[str, Any]]:
        """Generate concrete change proposals based on analysis."""
        proposals = []
        
        # Convert issues into actionable proposals
        for issue in analysis["issues_identified"][:5]:  # Limit proposals
            proposal = {
                "id": f"proposal-{len(proposals) + 1}",
                "title": f"Fix: {issue}",
                "description": f"Address the identified issue: {issue}",
                "type": "fix",
                "priority": "medium",
                "files_affected": [],
                "changes_summary": f"Implement fix for {issue}",
                "implementation_plan": [
                    "Identify affected code sections",
                    "Implement the fix",
                    "Test the changes",
                    "Update documentation if needed"
                ]
            }
            proposals.append(proposal)
        
        # Convert opportunities into enhancement proposals
        for opportunity in analysis["opportunities"][:3]:
            proposal = {
                "id": f"proposal-{len(proposals) + 1}",
                "title": f"Enhancement: {opportunity}",
                "description": f"Implement improvement: {opportunity}",
                "type": "enhancement",
                "priority": "low",
                "files_affected": [],
                "changes_summary": f"Enhance codebase by {opportunity}",
                "implementation_plan": [
                    "Analyze current implementation",
                    "Design improvement",
                    "Implement changes",
                    "Validate improvements"
                ]
            }
            proposals.append(proposal)
        
        return proposals

    async def _create_development_task(
        self, context: ActionContext, target_repo_url: str, task_id: str, 
        proposals: List[Dict[str, Any]], focus: str
    ):
        """Create a development task in the world state."""
        from ..core.world_state.structures import DevelopmentTask
        
        if not context.world_state_manager:
            logger.warning("World state manager not available for development task creation")
            return None
        
        ws_data = await context.world_state_manager.get_state()
        
        task = DevelopmentTask(
            task_id=task_id,
            title=f"AI-Proposed {focus.title()} Improvements",
            description=f"AI-generated proposals for {focus} improvements",
            target_repository=target_repo_url,
            status="proposal_ready",
            initial_proposal=json.dumps({
                "focus": focus,
                "proposals": proposals,
                "generated_at": asyncio.get_event_loop().time()
            }, indent=2)
        )
        
        ws_data.development_tasks[task_id] = task


class ImplementCodeChangesTool(ToolInterface):  # Phase 2
    """
    Implements specific code changes based on AI proposals or manual specifications.
    
    This tool takes change proposals and applies them to the codebase,
    creating commits and preparing for PR submission.
    """
    @property
    def name(self) -> str:
        return "ImplementCodeChanges"

    @property
    def description(self) -> str:
        return (
            "Implement specific code changes in a target repository workspace. "
            "Can apply AI-generated proposals or implement manually specified changes. "
            "Creates commits and prepares changes for review."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "target_repo_url": "string - Repository URL where changes will be implemented",
            "task_id": "string (optional) - Development task ID if implementing from proposals",
            "proposal_ids": "list of strings (optional) - Specific proposal IDs to implement",
            "manual_changes": "list of objects (optional) - Manual change specifications: [{'file': 'path', 'action': 'create/modify/delete', 'content': '...', 'description': '...'}]",
            "commit_message": "string (optional) - Custom commit message",
            "create_branch": "boolean (optional, default: true) - Whether to create a new branch for changes"
        }

    @require_developer_tools_enabled
    @require_admin_access
    @validate_sandbox_path
    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        target_repo_url = params.get("target_repo_url")
        task_id = params.get("task_id")
        proposal_ids = params.get("proposal_ids", [])
        manual_changes = params.get("manual_changes", [])
        commit_message = params.get("commit_message")
        create_branch = params.get("create_branch", True)
        
        if not target_repo_url:
            return {"status": "failure", "message": "target_repo_url is required"}
        
        if not task_id and not manual_changes:
            return {"status": "failure", "message": "Either task_id with proposals or manual_changes must be provided"}
        
        try:
            # Find workspace and git repository
            workspace_path = await self._find_workspace_path(target_repo_url, context)
            if not workspace_path:
                return {"status": "failure", "message": f"Workspace not found for {target_repo_url}. Run SetupDevelopmentWorkspace first."}
            
            # Set up git repository interface
            lg = LocalGitRepository(target_repo_url, str(workspace_path.parent))
            
            # Create feature branch if requested
            branch_name = None
            if create_branch:
                branch_name = f"ace-implementation-{task_id or 'manual'}-{asyncio.get_event_loop().time():.0f}"
                await self._create_branch(lg, branch_name)
            
            # Determine changes to implement
            changes_to_apply = []
            if task_id:
                changes_to_apply = await self._get_proposal_changes(context, task_id, proposal_ids)
            else:
                changes_to_apply = manual_changes
            
            # Apply changes
            applied_changes = []
            for change in changes_to_apply:
                result = await self._apply_change(workspace_path, change)
                if result["success"]:
                    applied_changes.append(result)
            
            # Commit changes if any were applied
            commit_success = False
            if applied_changes:
                commit_msg = commit_message or f"ACE: Implement {len(applied_changes)} changes for task {task_id or 'manual'}"
                commit_success = await lg.add_and_commit(commit_msg)
            
            # Update task status in world state
            if task_id and hasattr(context, 'world_state_manager'):
                await self._update_task_status(context, task_id, "implemented", applied_changes)
            
            return {
                "status": "success",
                "workspace_path": str(workspace_path),
                "branch_name": branch_name,
                "changes_applied": len(applied_changes),
                "changes_summary": [c['description'] for c in applied_changes],
                "commit_created": commit_success,
                "next_steps": "Review changes and create PR with CreatePullRequestTool"
            }
            
        except Exception as e:
            return {"status": "failure", "message": f"Error implementing changes: {str(e)}"}

    async def _find_workspace_path(self, target_repo_url: str, context: ActionContext) -> Optional[Path]:
        """Find the local workspace path for a target repository."""
        if hasattr(context, 'world_state_manager') and context.world_state_manager:
            ws_data = await context.world_state_manager.get_state()
            if target_repo_url in ws_data.target_repositories:
                repo_context = ws_data.target_repositories[target_repo_url]
                if repo_context.setup_complete:
                    return Path(repo_context.local_clone_path)
        return None

    async def _create_branch(self, lg: LocalGitRepository, branch_name: str) -> bool:
        """Create a new feature branch."""
        # Simple branch creation - in a real implementation, this would use git commands
        return True

    async def _get_proposal_changes(
        self, context: ActionContext, task_id: str, proposal_ids: List[str]
    ) -> List[Dict[str, Any]]:
        """Get changes from development task proposals."""
        if not hasattr(context, 'world_state_manager') or not context.world_state_manager:
            return []
        
        ws_data = await context.world_state_manager.get_state()
        if task_id not in ws_data.development_tasks:
            return []
        
        task = ws_data.development_tasks[task_id]
        proposals = task.initial_proposal.get("proposals", [])
        
        # Filter by proposal IDs if specified
        if proposal_ids:
            proposals = [p for p in proposals if p.get("id") in proposal_ids]
        
        # Convert proposals to change specifications
        changes = []
        for proposal in proposals:
            # This is a simplified conversion - real implementation would be more sophisticated
            change = {
                "file": "example.py",  # Would be determined from proposal
                "action": "modify",
                "content": f"# Implementation of: {proposal['title']}\n# {proposal['description']}\n",
                "description": proposal['title']
            }
            changes.append(change)
        
        return changes

    async def _apply_change(self, workspace_path: Path, change: Dict[str, Any]) -> Dict[str, Any]:
        """Apply a single change to the workspace."""
        try:
            file_path = workspace_path / change["file"]
            action = change["action"]
            content = change.get("content", "")
            
            if action == "create":
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(content, encoding='utf-8')
            elif action == "modify":
                if file_path.exists():
                    # In a real implementation, this would be more sophisticated
                    # (patch application, targeted modifications, etc.)
                    current_content = file_path.read_text(encoding='utf-8')
                    new_content = current_content + "\n" + content
                    file_path.write_text(new_content, encoding='utf-8')
                else:
                    file_path.write_text(content, encoding='utf-8')
            elif action == "delete":
                if file_path.exists():
                    file_path.unlink()
            
            return {
                "success": True,
                "file": change["file"],
                "action": action,
                "description": change.get("description", f"{action.title()} {change['file']}")
            }
            
        except Exception as e:
            return {
                "success": False,
                "file": change.get("file", "unknown"),
                "action": change.get("action", "unknown"),
                "error": str(e)
            }

    async def _commit_changes(
        self, lg: LocalGitRepository, commit_message: str, changes: List[Dict[str, Any]]
    ) -> bool:
        """Commit the applied changes."""
        # In a real implementation, this would use git commands to add and commit files
        # For now, return True to indicate success
        return True

    async def _update_task_status(
        self, context: ActionContext, task_id: str, status: str, changes: List[Dict[str, Any]]
    ):
        """Update the development task status in world state."""
        if not context.world_state_manager:
            logger.warning("World state manager not available for task status update")
            return
        
        ws_data = context.world_state_manager.world_state
        if task_id in ws_data.development_tasks:
            task = ws_data.development_tasks[task_id]
            task.status = status
            task.implementation_details = {
                "changes_applied": changes,
                "implemented_at": asyncio.get_event_loop().time()
            }


class CreatePullRequestTool(ToolInterface):  # Phase 3
    """
    Creates a pull request from the implemented changes.
    
    This tool pushes the local changes to a fork and creates a PR
    for human review, completing the ACE workflow cycle.
    """
    @property
    def name(self) -> str:
        return "CreatePullRequest"

    @property
    def description(self) -> str:
        return (
            "Create a pull request from implemented changes in a development workspace. "
            "Pushes changes to fork and opens PR for human review."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "target_repo_url": "string - Repository URL where changes were implemented",
            "pr_title": "string - Title for the pull request",
            "pr_description": "string (optional) - Description for the pull request",
            "target_branch": "string (optional, default: 'develop') - Target branch for the PR",
            "draft": "boolean (optional, default: true) - Create as draft PR for ACE changes"
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        target_repo_url = params.get("target_repo_url")
        pr_title = params.get("pr_title")
        pr_description = params.get("pr_description", "")
        target_branch = params.get("target_branch", "develop")
        draft = params.get("draft", True)
        
        if not target_repo_url or not pr_title:
            return {"status": "failure", "message": "target_repo_url and pr_title are required"}
        
        try:
            if not context.world_state_manager:
                return {"status": "failure", "message": "World state manager not available"}
            
            ws_data = context.world_state_manager.get_state_data()
            repo_context = ws_data.target_repositories.get(target_repo_url)
            if not repo_context or not repo_context.setup_complete:
                return {"status": "failure", "message": f"Workspace not set up for {target_repo_url}"}

            workspace_path = Path(repo_context.local_clone_path)
            feature_branch = repo_context.current_branch
            
            # 1. Push changes to fork
            lg = LocalGitRepository(target_repo_url, str(workspace_path.parent))
            await lg.push("fork", feature_branch)

            # 2. Create PR using GitHub service
            repo_parts = target_repo_url.replace('https://github.com/', '').split('/')
            main_repo_full_name = f"{repo_parts[0]}/{repo_parts[1]}"
            gh = GitHubService(main_repo=main_repo_full_name)
            
            pr_data = await gh.create_pull_request(
                title=pr_title,
                body=pr_description,
                head_branch=feature_branch,
                base_branch=target_branch,
                is_draft=draft,
            )
            
            if not pr_data:
                return {"status": "failure", "message": "Failed to create pull request"}
            
            pr_url = pr_data.get("html_url")
            
            # Update world state with PR information
            if repo_context.active_task_id:
                task = ws_data.development_tasks.get(repo_context.active_task_id)
                if task:
                    task.status = "pr_submitted"
                    task.associated_pr_url = pr_url
            
            return {
                "status": "success",
                "pr_url": pr_url,
                "message": f"Successfully created pull request: {pr_url}",
                "next_steps": "Monitor PR for feedback and iterate with ACE as needed"
            }
            
        except Exception as e:
            return {"status": "failure", "message": f"Error creating PR: {str(e)}"}

