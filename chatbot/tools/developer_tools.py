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


class UpdateProjectPlanTool(ToolInterface):  # Phase 2
    """
    Creates or updates project tasks in the world state project plan.
    """
    @property
    def name(self) -> str:
        return "UpdateProjectPlan"

    @property
    def description(self) -> str:
        return (
            "Create, update, or manage project tasks in the development plan. "
            "Use this to organize development work based on analysis of codebase structure, "
            "channel discussions, or identified issues."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "action": "string - 'create', 'update', or 'list'",
            "task_id": "string (optional) - Required for 'update' action",
            "title": "string (optional) - Task title for 'create' action",
            "description": "string (optional) - Detailed task description",
            "status": "string (optional) - 'todo', 'in_progress', 'needs_review', 'blocked', 'done'",
            "priority": "integer (optional) - 1-10 priority level",
            "complexity": "string (optional) - 'S', 'M', 'L' for size estimation",
            "related_files": "array of strings (optional) - Related code file paths",
            "source_refs": "array of strings (optional) - References to discussions or issues"
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        action = params.get("action", "list")
        
        # Import here to avoid circular imports
        from ..core.world_state.structures import ProjectTask
        
        if action == "list":
            tasks = context.world_state.project_plan
            task_summary = []
            for task_id, task in tasks.items():
                task_summary.append({
                    "task_id": task_id,
                    "title": task.title,
                    "status": task.status,
                    "priority": task.priority,
                    "complexity": task.estimated_complexity
                })
            return {
                "status": "success",
                "message": f"Retrieved {len(tasks)} project tasks",
                "tasks": task_summary
            }
        
        elif action == "create":
            title = params.get("title", "Untitled Task")
            description = params.get("description", "")
            task = ProjectTask(
                title=title,
                description=description,
                status=params.get("status", "todo"),
                priority=params.get("priority", 5),
                estimated_complexity=params.get("complexity"),
                related_code_files=params.get("related_files", []),
                source_references=params.get("source_refs", [])
            )
            context.world_state.add_project_task(task)
            return {
                "status": "success",
                "message": f"Created task '{title}' with ID {task.task_id}",
                "task_id": task.task_id
            }
        
        elif action == "update":
            task_id = params.get("task_id")
            if not task_id or task_id not in context.world_state.project_plan:
                return {"status": "failure", "message": "Invalid or missing task_id"}
            
            update_fields = {}
            for field in ["title", "description", "status", "priority", "complexity", "related_files", "source_refs"]:
                if field in params:
                    if field == "complexity":
                        update_fields["estimated_complexity"] = params[field]
                    elif field == "related_files":
                        update_fields["related_code_files"] = params[field]
                    elif field == "source_refs":
                        update_fields["source_references"] = params[field]
                    else:
                        update_fields[field] = params[field]
            
            context.world_state.update_project_task(task_id, **update_fields)
            return {
                "status": "success",
                "message": f"Updated task {task_id}",
                "updated_fields": list(update_fields.keys())
            }
        
        else:
            return {"status": "failure", "message": f"Unknown action: {action}"}


class SummarizeChannelTool(ToolInterface):  # Phase 2
    """
    Analyzes recent channel activity to generate insights for project planning.
    """
    @property
    def name(self) -> str:
        return "SummarizeChannel"

    @property
    def description(self) -> str:
        return (
            "Analyze recent messages in a channel to extract key topics, issues, "
            "feature requests, or development discussions that could inform project planning."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "channel_id": "string - Channel ID to analyze",
            "message_limit": "integer (optional, default: 20) - Number of recent messages to analyze",
            "focus": "string (optional) - 'issues', 'features', 'bugs', 'general' - What to focus analysis on"
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        channel_id = params.get("channel_id")
        if not channel_id:
            return {"status": "failure", "message": "channel_id is required"}
        
        message_limit = params.get("message_limit", 20)
        focus = params.get("focus", "general")
        
        messages = context.world_state.get_recent_messages(channel_id, message_limit)
        if not messages:
            return {"status": "failure", "message": f"No messages found in channel {channel_id}"}
        
        # Basic text analysis (could be enhanced with AI summarization)
        text_content = []
        for msg in messages:
            if msg.content:
                text_content.append(f"{msg.sender}: {msg.content}")
        
        combined_text = "\n".join(text_content)
        word_count = len(combined_text.split())
        
        # Simple keyword analysis based on focus
        keywords = []
        if focus == "issues":
            keywords = ["error", "bug", "broken", "issue", "problem", "fail", "crash"]
        elif focus == "features":
            keywords = ["feature", "add", "new", "implement", "enhancement", "improve"]
        elif focus == "bugs":
            keywords = ["bug", "fix", "broken", "error", "crash", "issue"]
        
        keyword_mentions = {}
        for keyword in keywords:
            count = combined_text.lower().count(keyword.lower())
            if count > 0:
                keyword_mentions[keyword] = count
        
        return {
            "status": "success",
            "message": f"Analyzed {len(messages)} messages from {channel_id}",
            "summary": {
                "message_count": len(messages),
                "word_count": word_count,
                "focus": focus,
                "keyword_mentions": keyword_mentions,
                "time_range": {
                    "earliest": messages[0].timestamp if messages else None,
                    "latest": messages[-1].timestamp if messages else None
                }
            },
            "sample_content": combined_text[:500] + "..." if len(combined_text) > 500 else combined_text
        }


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
        
        try:
            # Extract repo owner/name from URL
            if target_repo_url.endswith('.git'):
                target_repo_url = target_repo_url[:-4]
            repo_parts = target_repo_url.replace('https://github.com/', '').split('/')
            if len(repo_parts) != 2:
                return {"status": "failure", "message": "Invalid GitHub repository URL format"}
            
            repo_owner, repo_name = repo_parts
            main_repo = f"{repo_owner}/{repo_name}"
            
            # Set up GitHub service
            gh = GitHubService(main_repo=main_repo)
            
            # Create workspace directory
            workspace_path = Path(workspace_base) / repo_name
            workspace_path.mkdir(parents=True, exist_ok=True)
            
            # Set up local git repository
            clone_url = f"https://github.com/{main_repo}.git"
            lg = LocalGitRepository(clone_url, str(workspace_path.parent))
            
            # Clone or pull latest
            clone_success = await lg.clone_or_pull(branch=base_branch)
            if not clone_success:
                return {"status": "failure", "message": f"Failed to clone/pull repository {main_repo}"}
            
            # Create feature branch for this task
            feature_branch = f"ace-task-{task_id[:8]}-{task_description.lower().replace(' ', '-')[:20]}"
            current_branch = await lg.get_current_branch()
            
            # Update world state with target repository context
            from ..core.world_state.structures import TargetRepositoryContext
            repo_context = TargetRepositoryContext(
                url=target_repo_url,
                fork_url=None,  # Will be set when we implement forking
                local_clone_path=str(lg.repo_path),
                current_branch=current_branch,
                active_task_id=task_id,
                setup_complete=True
            )
            
            # Store in world state if manager is available
            if hasattr(context, 'world_state_manager') and context.world_state_manager:
                ws_data = await context.world_state_manager.get_state()
                ws_data.add_target_repository(target_repo_url, repo_context)
                await context.world_state_manager.update_state(ws_data)
            
            return {
                "status": "success",
                "message": f"Development workspace set up for {main_repo}",
                "workspace_path": str(lg.repo_path),
                "current_branch": current_branch,
                "feature_branch": feature_branch,
                "base_branch": base_branch,
                "target_repo": main_repo
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


# ...existing code...
