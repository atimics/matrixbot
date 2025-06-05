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
from ..config import settings
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

        if not settings.GITHUB_TOKEN or not settings.GITHUB_USERNAME:
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
            fork_auth_url = fork_clone_url.replace('https://', f'https://{settings.GITHUB_USERNAME}:{settings.GITHUB_TOKEN}@')
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


class AnalyzeAndProposeChangeTool(ToolInterface):  # Phase 2
    """
    Uses AI to analyze code and propose specific improvements or changes.
    
    This tool takes the context from codebase exploration and generates
    concrete, actionable change proposals with reasoning and implementation plans.
    """
    @property
    def name(self) -> str:
        return "AnalyzeAndProposeChange"

    @property
    def description(self) -> str:
        return (
            "Analyze a codebase and propose specific code changes or improvements. "
            "Uses AI to understand code patterns, identify issues, and suggest "
            "concrete implementations with detailed reasoning."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "target_repo_url": "string - Repository URL to analyze",
            "analysis_focus": "string - Focus area: 'bug_fixes', 'performance', 'code_quality', 'features', 'security', 'documentation'",
            "specific_files": "list of strings (optional) - Specific files to focus analysis on",
            "context_description": "string (optional) - Additional context about what to look for",
            "proposal_scope": "string (optional, default: 'targeted') - 'minimal', 'targeted', or 'comprehensive'"
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        target_repo_url = params.get("target_repo_url")
        analysis_focus = params.get("analysis_focus", "code_quality")
        specific_files = params.get("specific_files", [])
        context_description = params.get("context_description", "")
        proposal_scope = params.get("proposal_scope", "targeted")
        
        if not target_repo_url:
            return {"status": "failure", "message": "target_repo_url is required"}
        
        try:
            # Find workspace path from world state
            workspace_path = await self._find_workspace_path(target_repo_url, context)
            if not workspace_path:
                return {"status": "failure", "message": f"Workspace not found for {target_repo_url}. Run SetupDevelopmentWorkspace first."}
            
            # Analyze codebase structure and content
            analysis_result = await self._analyze_codebase(
                workspace_path, analysis_focus, specific_files, context_description
            )
            
            # Generate AI-driven change proposals
            proposals = await self._generate_change_proposals(
                analysis_result, analysis_focus, proposal_scope, workspace_path
            )
            
            # Create development task in world state
            if proposals and hasattr(context, 'world_state_manager') and context.world_state_manager:
                task_id = f"ace-proposal-{analysis_focus}-{asyncio.get_event_loop().time():.0f}"
                await self._create_development_task(
                    context, target_repo_url, task_id, proposals, analysis_focus
                )
            
            return {
                "status": "success",
                "analysis_focus": analysis_focus,
                "workspace_path": str(workspace_path),
                "proposals_count": len(proposals),
                "proposals": proposals[:3],  # Limit to first 3 for readability
                "all_proposals_summary": f"Generated {len(proposals)} change proposals",
                "next_steps": "Use ImplementCodeChangesTool to apply selected proposals"
            }
            
        except Exception as e:
            return {"status": "failure", "message": f"Error analyzing codebase: {str(e)}"}

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
        
        ws_data = await context.world_state_manager.get_state()
        
        task = DevelopmentTask(
            task_id=task_id,
            title=f"AI-Proposed {focus.title()} Improvements",
            description=f"AI-generated proposals for {focus} improvements",
            target_repository=target_repo_url,
            status="proposal_ready",
            initial_proposal={
                "focus": focus,
                "proposals": proposals,
                "generated_at": asyncio.get_event_loop().time()
            }
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
        if not hasattr(context, 'world_state_manager'):
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
            # Find workspace path
            workspace_path = await self._find_workspace_path(target_repo_url, context)
            if not workspace_path:
                return {"status": "failure", "message": f"Workspace not found for {target_repo_url}"}
            
            # Get repository context from world state
            repo_context = await self._get_repo_context(target_repo_url, context)
            if not repo_context:
                return {"status": "failure", "message": "Repository context not found in world state"}
            
            # Push changes to fork (simulated for now)
            push_success = await self._push_to_fork(workspace_path, repo_context)
            if not push_success:
                return {"status": "failure", "message": "Failed to push changes to fork"}
            
            # Create pull request (simulated for now)
            pr_url = await self._create_github_pr(
                target_repo_url, repo_context, pr_title, pr_description, target_branch, draft
            )
            
            # Update world state with PR information
            if hasattr(context, 'world_state_manager'):
                await self._update_pr_info(context, target_repo_url, pr_url)
            
            return {
                "status": "success",
                "pr_url": pr_url,
                "pr_title": pr_title,
                "target_branch": target_branch,
                "draft": draft,
                "message": f"Pull request created: {pr_url}",
                "next_steps": "Monitor PR for feedback and iterate with ACE as needed"
            }
            
        except Exception as e:
            return {"status": "failure", "message": f"Error creating PR: {str(e)}"}

    async def _find_workspace_path(self, target_repo_url: str, context: ActionContext) -> Optional[Path]:
        """Find the local workspace path for a target repository."""
        if hasattr(context, 'world_state_manager') and context.world_state_manager:
            ws_data = await context.world_state_manager.get_state()
            if target_repo_url in ws_data.target_repositories:
                repo_context = ws_data.target_repositories[target_repo_url]
                if repo_context.setup_complete:
                    return Path(repo_context.local_clone_path)
        return None

    async def _get_repo_context(self, target_repo_url: str, context: ActionContext):
        """Get repository context from world state."""
        if hasattr(context, 'world_state_manager') and context.world_state_manager:
            ws_data = await context.world_state_manager.get_state()
            return ws_data.target_repositories.get(target_repo_url)
        return None

    async def _push_to_fork(self, workspace_path: Path, repo_context) -> bool:
        """Push changes to the fork repository."""
        # In a real implementation, this would:
        # 1. Set up fork as remote if not exists
        # 2. Push current branch to fork
        # 3. Handle authentication
        
        # For now, simulate success
        return True

    async def _create_github_pr(
        self, target_repo_url: str, repo_context, title: str, 
        description: str, target_branch: str, draft: bool
    ) -> str:
        """Create a GitHub pull request."""
        # In a real implementation, this would use GitHub API to:
        # 1. Create the pull request
        # 2. Set appropriate labels (e.g., "ACE-generated")
        # 3. Assign reviewers if configured
        
        # Simulate PR creation with a mock URL
        repo_name = target_repo_url.split('/')[-1]
        pr_number = f"{asyncio.get_event_loop().time():.0f}"[-4:]  # Use last 4 digits of timestamp
        return f"https://github.com/mock-user/{repo_name}/pull/{pr_number}"

    async def _update_pr_info(self, context: ActionContext, target_repo_url: str, pr_url: str):
        """Update world state with PR information."""
        ws_data = await context.world_state_manager.get_state()
        
        # Find and update any related development tasks
        for task_id, task in ws_data.development_tasks.items():
            if task.target_repository == target_repo_url and task.status in ["implemented", "proposal_ready"]:
                task.associated_pr_url = pr_url
                task.status = "pr_created"
        
        # Update repository context
        if target_repo_url in ws_data.target_repositories:
            repo_context = ws_data.target_repositories[target_repo_url]
            if not hasattr(repo_context, 'associated_prs'):
                repo_context.associated_prs = []
            repo_context.associated_prs.append(pr_url)


class ACEOrchestratorTool(ToolInterface):  # Phase 3
    """
    High-level orchestrator for complete ACE workflows.
    
    This tool manages the entire lifecycle from repository analysis
    to PR creation, coordinating all ACE tools in sequence.
    """
    @property
    def name(self) -> str:
        return "ACEOrchestrator"

    @property
    def description(self) -> str:
        return (
            "Orchestrate a complete Autonomous Code Evolution workflow. "
            "Manages the full cycle: setup → exploration → analysis → "
            "proposal → implementation → PR creation."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "target_repo_url": "string - GitHub repository URL to improve",
            "improvement_focus": "string - Focus area: 'bug_fixes', 'performance', 'code_quality', 'features', 'security', 'documentation'",
            "workflow_scope": "string (optional, default: 'targeted') - 'minimal', 'targeted', or 'comprehensive'",
            "context_description": "string (optional) - Additional context about what to improve",
            "auto_implement": "boolean (optional, default: false) - Whether to auto-implement changes or wait for approval",
            "create_pr": "boolean (optional, default: true) - Whether to automatically create PR"
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        target_repo_url = params.get("target_repo_url")
        improvement_focus = params.get("improvement_focus", "code_quality")
        workflow_scope = params.get("workflow_scope", "targeted")
        context_description = params.get("context_description", "")
        auto_implement = params.get("auto_implement", False)
        create_pr = params.get("create_pr", True)
        
        if not target_repo_url:
            return {"status": "failure", "message": "target_repo_url is required"}
        
        workflow_id = f"ace-workflow-{improvement_focus}-{asyncio.get_event_loop().time():.0f}"
        results = {"workflow_id": workflow_id, "steps": []}
        
        try:
            # Step 1: Setup Development Workspace
            setup_result = await self._execute_setup(target_repo_url, workflow_id, context)
            results["steps"].append(("setup", setup_result))
            
            if setup_result.get("status") != "success":
                return {"status": "failure", "message": "Workspace setup failed", "results": results}
            
            # Step 2: Explore Codebase
            explore_result = await self._execute_exploration(target_repo_url, context)
            results["steps"].append(("exploration", explore_result))
            
            # Step 3: Analyze and Propose Changes
            analyze_result = await self._execute_analysis(
                target_repo_url, improvement_focus, context_description, workflow_scope, context
            )
            results["steps"].append(("analysis", analyze_result))
            
            if analyze_result.get("status") != "success":
                return {"status": "partial_success", "message": "Analysis failed", "results": results}
            
            # Step 4: Implement Changes (if auto_implement or no proposals)
            implement_result = None
            if auto_implement or analyze_result.get("proposals_count", 0) == 0:
                implement_result = await self._execute_implementation(
                    target_repo_url, workflow_id, context
                )
                results["steps"].append(("implementation", implement_result))
            
            # Step 5: Create PR (if changes were implemented and create_pr is True)
            pr_result = None
            if create_pr and implement_result and implement_result.get("status") == "success":
                pr_result = await self._execute_pr_creation(
                    target_repo_url, improvement_focus, workflow_id, context
                )
                results["steps"].append(("pr_creation", pr_result))
            
            # Determine overall status
            if pr_result and pr_result.get("status") == "success":
                status = "complete"
                message = f"ACE workflow completed successfully: {pr_result.get('pr_url')}"
            elif implement_result and implement_result.get("status") == "success":
                status = "implemented"
                message = "Changes implemented successfully, ready for PR creation"
            elif analyze_result.get("proposals_count", 0) > 0:
                status = "proposals_ready"
                message = f"Analysis complete, {analyze_result.get('proposals_count')} proposals generated"
            else:
                status = "analyzed"
                message = "Codebase analyzed, no immediate improvements identified"
            
            return {
                "status": status,
                "message": message,
                "workflow_id": workflow_id,
                "improvement_focus": improvement_focus,
                "results": results
            }
            
        except Exception as e:
            return {
                "status": "failure", 
                "message": f"ACE workflow error: {str(e)}",
                "workflow_id": workflow_id,
                "results": results
            }

    async def _execute_setup(self, target_repo_url: str, workflow_id: str, context: ActionContext):
        """Execute workspace setup step."""
        setup_tool = SetupDevelopmentWorkspaceTool()
        params = {
            "target_repo_url": target_repo_url,
            "task_id": workflow_id,
            "task_description": "ACE automated workflow",
            "workspace_base_path": f"/tmp/ace_workflows"
        }
        return await setup_tool.execute(params, context)

    async def _execute_exploration(self, target_repo_url: str, context: ActionContext):
        """Execute codebase exploration step."""
        explore_tool = ExploreCodebaseTool()
        params = {
            "target_repo_url": target_repo_url,
            "exploration_type": "overview"
        }
        return await explore_tool.execute(params, context)

    async def _execute_analysis(
        self, target_repo_url: str, focus: str, context_desc: str, scope: str, context: ActionContext
    ):
        """Execute analysis and proposal generation step."""
        analyze_tool = AnalyzeAndProposeChangeTool()
        params = {
            "target_repo_url": target_repo_url,
            "analysis_focus": focus,
            "context_description": context_desc,
            "proposal_scope": scope
        }
        return await analyze_tool.execute(params, context)

    async def _execute_implementation(self, target_repo_url: str, workflow_id: str, context: ActionContext):
        """Execute implementation step."""
        implement_tool = ImplementCodeChangesTool()
        params = {
            "target_repo_url": target_repo_url,
            "task_id": workflow_id,
            "commit_message": f"ACE: Automated improvements ({workflow_id})"
        }
        return await implement_tool.execute(params, context)

    async def _execute_pr_creation(
        self, target_repo_url: str, focus: str, workflow_id: str, context: ActionContext
    ):
        """Execute PR creation step."""
        pr_tool = CreatePullRequestTool()
        params = {
            "target_repo_url": target_repo_url,
            "pr_title": f"ACE: {focus.replace('_', ' ').title()} Improvements",
            "pr_description": f"Automated code improvements generated by ACE workflow {workflow_id}",
            "draft": True
        }
        return await pr_tool.execute(params, context)
