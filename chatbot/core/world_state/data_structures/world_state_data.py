#!/usr/bin/env python3
"""
World State Data Structure

The main WorldStateData class that serves as the central knowledge base.
"""

import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from .channel import Channel
from .message import Message
from .system_data import ActionHistory
from .user_details import FarcasterUserDetails, MatrixUserDetails
from .system_data import MemoryEntry
from .token_data import TokenMetadata, MonitoredTokenHolder
from .project_data import Goal, TargetRepositoryContext, DevelopmentTask

logger = logging.getLogger(__name__)


@dataclass
class WorldStateData:
    """
    The complete observable state of the world with advanced management capabilities.

    This class serves as the central knowledge base for the AI system, maintaining
    comprehensive awareness of all platform activities, conversations, and bot interactions.
    It provides intelligent organization, deduplication, and optimization features for
    efficient AI decision-making.

    Core Components:
        - channels: Dictionary mapping channel IDs to Channel objects
        - action_history: Chronological list of completed actions
        - system_status: Current system health and connection status
        - threads: Conversation thread tracking for platforms supporting threading
        - seen_messages: Set for cross-platform message deduplication
        - rate_limits: API rate limiting information and enforcement data
        - pending_matrix_invites: Matrix room invitations awaiting response

    Key Features:
        - Automatic message deduplication across all platforms
        - Intelligent conversation thread management
        - AI payload optimization for efficient token usage
        - Comprehensive action tracking with deduplication
        - Real-time activity monitoring and analytics
        - Memory management with automatic cleanup

    Performance Optimizations:
        - Message rotation to prevent memory bloat (50 messages per channel)
        - Action history limits (100 actions maximum)
        - Smart filtering for AI payloads
        - Efficient data structures for fast access
    """

    def __init__(self):
        """
        Initialize empty world state with optimized data structures.

        Sets up all necessary containers and tracking mechanisms for efficient
        operation across multiple platforms and conversation contexts.
        """
        self.channels: Dict[str, Dict[str, Channel]] = {}  # Nested: {platform: {channel_id: Channel}}
        self.action_history: List[ActionHistory] = []
        self.system_status: Dict[str, Any] = {}
        self.threads: Dict[
            str, List[Message]
        ] = {}  # Map root cast id to thread messages
        self.thread_roots: Dict[str, Message] = {}  # Root message for each thread
        self.seen_messages: set[str] = set()  # Deduplication of message IDs

        # Rate limiting and API management
        self.rate_limits: Dict[str, Any] = {}  # API rate limiting information

        # Matrix room management
        self.pending_matrix_invites: List[
            Dict[str, Any]
        ] = []  # Pending Matrix invitations

        # v0.0.3: Bot media tracking for Farcaster engagement-based archival
        self.bot_media_on_farcaster: Dict[
            str, Dict[str, Any]
        ] = {}  # cast_hash -> media_info
        # Aliases
        self.pending_invites = self.pending_matrix_invites
        # action_history already exists
        # Pending invites alias
        # pending_matrix_invites: List[Dict] already defined

        # Image library: Track AI-generated media for reuse and reference
        self.generated_media_library: List[Dict[str, Any]] = []

        # Ecosystem token tracking
        self.ecosystem_token_contract: Optional[str] = None
        # Enhanced token metadata tracking
        self.token_metadata: Optional[TokenMetadata] = None
        # Stores FIDs of top holders and their details + recent activity
        self.monitored_token_holders: Dict[str, MonitoredTokenHolder] = {}

        # Initialize timestamp tracking
        self.last_update = time.time()
        
        # Enhanced user tracking with sentiment and memory
        self.farcaster_users: Dict[str, FarcasterUserDetails] = {}  # fid -> user details
        self.matrix_users: Dict[str, MatrixUserDetails] = {}  # user_id -> user details
        self.user_memory_bank: Dict[str, List[MemoryEntry]] = {}  # user_platform_id -> memories
        
        # Tool result caching
        self.tool_cache: Dict[str, Dict[str, Any]] = {}  # cache_key -> cached result
        self.search_cache: Dict[str, Dict[str, Any]] = {}  # query_hash -> search results
        
        # Research knowledge base - persistent AI learning and knowledge accumulation
        self.research_database: Dict[str, Dict[str, Any]] = {}  # topic -> research_entry
        
        # Autonomous Code Evolution (ACE) capabilities
        self.target_repositories: Dict[str, TargetRepositoryContext] = {}  # repo_url -> context
        self.development_tasks: Dict[str, DevelopmentTask] = {}  # task_id -> task
        self.evolutionary_knowledge_base: Dict[str, Dict[str, Any]] = {}  # patterns and learnings
        
        # Compatibility (Phase 1 backward compatibility)
        self.codebase_structure: Optional[Dict[str, Any]] = None
        self.project_plan: Dict[str, DevelopmentTask] = {}  # task_id -> DevelopmentTask  
        self.github_repository_state: Optional[TargetRepositoryContext] = None
        
        # Goal Management System - Long-term strategic objectives
        self.active_goals: List[Goal] = []
        
        # Backward compatibility placeholders
        self.user_details: Dict[str, Any] = {}
        self.bot_media: Dict[str, Any] = {}  # alias for bot_media_on_farcaster

    def get_recent_messages(self, channel_id: str, limit: int = 50) -> List[Message]:
        """
        Retrieve recent messages from a specific channel.
        
        Args:
            channel_id: The channel identifier to get messages from
            limit: Maximum number of messages to return
            
        Returns:
            List of Message objects from the specified channel
        """
        messages = []
        
        # Search through all platforms for the channel
        for platform_channels in self.channels.values():
            if channel_id in platform_channels:
                channel = platform_channels[channel_id]
                messages = channel.recent_messages[-limit:] if channel.recent_messages else []
                break
        
        return messages

    def add_action_history(self, action_data: dict):
        """Compatibility method for tests that call add_action_history on WorldStateData."""
        action = ActionHistory(
            action_type=action_data.get("action_type", "unknown"),
            parameters=action_data.get("parameters", {}),
            result=action_data.get("result", ""),
            timestamp=action_data.get("timestamp", time.time()),
        )
        self.action_history.append(action)
        if len(self.action_history) > 100:
            self.action_history = self.action_history[-100:]

    def get_state_metrics(self) -> Dict[str, Any]:
        """
        Get metrics about the current state for payload size estimation.
        
        Returns:
            Dictionary with metrics about channels, messages, actions, etc.
        """
        # Handle nested channel structure: channels[platform][channel_id]
        total_messages = sum(
            len(ch.recent_messages) 
            for platform_channels in self.channels.values() 
            for ch in platform_channels.values()
        )
        
        # Count total channels across all platforms
        total_channels = sum(len(platform_channels) for platform_channels in self.channels.values())
        
        return {
            "channel_count": total_channels,
            "total_messages": total_messages,
            "action_history_count": len(self.action_history),
            "thread_count": len(self.threads),
            "pending_invites": len(self.pending_matrix_invites),
            "media_library_size": len(self.generated_media_library),
            "development_task_count": len(self.development_tasks),
            "target_repository_count": len(self.target_repositories),
            "active_tasks": len([t for t in self.development_tasks.values() if t.status in ["approved", "implementation_in_progress"]]),
            "codebase_structure_available": self.codebase_structure is not None,
            "active_goals_count": len(self.active_goals),
            "last_update": self.last_update
        }

    # Goal Management System Methods
    def add_goal(self, goal: Goal):
        """Add a new goal to active goals."""
        self.active_goals.append(goal)
        logger.debug(f"Added new goal: {goal.title} (ID: {goal.id})")
        
    def update_goal_progress(self, goal_id: str, update: str, metrics: Optional[Dict[str, Any]] = None):
        """Update progress on a specific goal."""
        for goal in self.active_goals:
            if goal.id == goal_id:
                goal.add_progress_update(update, metrics)
                logger.debug(f"Updated goal {goal.title}: {update}")
                return True
        return False
        
    def get_active_goals_summary(self) -> List[Dict[str, Any]]:
        """Get summary of all active goals for AI context."""
        return [goal.get_progress_summary() for goal in self.active_goals if goal.status == "active"]
        
    def complete_goal(self, goal_id: str, completion_note: str = ""):
        """Mark a goal as completed."""
        for goal in self.active_goals:
            if goal.id == goal_id:
                goal.mark_completed(completion_note)
                logger.debug(f"Completed goal: {goal.title}")
                return True
        return False
        
    def get_goal_by_id(self, goal_id: str) -> Optional[Goal]:
        """Get a specific goal by ID."""
        for goal in self.active_goals:
            if goal.id == goal_id:
                return goal
        return None
    
    def remove_goal(self, goal_id: str) -> bool:
        """Remove a goal from active goals."""
        for i, goal in enumerate(self.active_goals):
            if goal.id == goal_id:
                removed_goal = self.active_goals.pop(i)
                logger.debug(f"Removed goal: {removed_goal.title} (ID: {goal_id})")
                return True
        return False

    def has_replied_to_cast(self, cast_hash: str) -> bool:
        """
        Check if the AI has already replied to a specific cast.
        This now checks for successful or scheduled actions.
        """
        for action in self.action_history:
            if action.action_type == "send_farcaster_reply":
                reply_to_hash = action.parameters.get("reply_to_hash")
                if reply_to_hash == cast_hash:
                    # Consider it replied if the action was successful OR is still scheduled.
                    # This prevents re-queueing a reply while one is already pending.
                    if action.result != "failure":
                        return True
        return False

    def set_rate_limits(self, key: str, limits: Dict[str, Any]):
        """Set rate limit info for a service."""
        self.rate_limits[key] = limits

    def get_rate_limits(self, key: str) -> Optional[Dict[str, Any]]:
        """Get rate limit info for a service."""
        return self.rate_limits.get(key)

    def add_pending_invite(self, invite_info: Dict[str, Any]):
        """Add a pending Matrix invite."""
        # Use pending_matrix_invites list
        room = invite_info.get("room_id")
        if room:
            self.pending_matrix_invites.append(invite_info)
            self.last_update = time.time()

    def remove_pending_invite(self, room_id: str) -> bool:
        """Remove a pending Matrix invite by room_id."""
        original = len(self.pending_matrix_invites)
        self.pending_matrix_invites = [inv for inv in self.pending_matrix_invites if inv.get("room_id") != room_id]
        removed = len(self.pending_matrix_invites) < original
        if removed:
            self.last_update = time.time()
        return removed

    def track_bot_media(self, cast_hash: str, media_info: Dict[str, Any]):
        """Record tracking info for bot media engagement."""
        self.bot_media_on_farcaster[cast_hash] = media_info
        # Maintain alias
        self.bot_media = self.bot_media_on_farcaster
        self.last_update = time.time()

    def add_action(self, action: ActionHistory):
        """Add an action to history with a default limit of 10 entries."""
        self.action_history.append(action)
        # Keep only last 10
        if len(self.action_history) > 10:
            self.action_history = self.action_history[-10:]
        self.last_update = time.time()

    def get_all_messages(self) -> List[Message]:
        """Get all messages from all channels"""
        all_messages = []
        for platform_channels in self.channels.values():
            for channel in platform_channels.values():
                all_messages.extend(channel.recent_messages)
        return sorted(all_messages, key=lambda x: x.timestamp or 0)

    def to_json(self) -> str:
        """Convert world state to JSON for AI consumption"""
        import json

        return json.dumps(self.to_dict(), indent=2, default=str)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "channels": {
                platform: {
                    channel_id: {
                        "id": ch.id,
                        "type": ch.type,
                        "name": ch.name,
                        "recent_messages": [asdict(msg) for msg in ch.recent_messages],
                        "last_checked": ch.last_checked,
                    }
                    for channel_id, ch in platform_channels.items()
                } if isinstance(platform_channels, dict) else {
                    platform_channels.id: {
                        "id": platform_channels.id,
                        "type": platform_channels.type,
                        "name": platform_channels.name,
                        "recent_messages": [asdict(msg) for msg in platform_channels.recent_messages],
                        "last_checked": platform_channels.last_checked,
                    }
                }
                for platform, platform_channels in self.channels.items()
            },
            "action_history": [asdict(action) for action in self.action_history],
            "system_status": self.system_status,
            "last_update": self.last_update,
            "threads": {
                thread_id: [asdict(msg) for msg in msgs]
                for thread_id, msgs in self.threads.items()
            },
            "rate_limits": self.rate_limits,
            "pending_invites": self.pending_matrix_invites,
            "recent_activity": self.get_recent_activity(),
            # Autonomous Code Evolution (ACE) fields
            "target_repositories": {url: asdict(ctx) for url, ctx in self.target_repositories.items()},
            "development_tasks": {task_id: asdict(task) for task_id, task in self.development_tasks.items()},
            "evolutionary_knowledge_base": self.evolutionary_knowledge_base,
            # Compatibility
            "codebase_structure": self.codebase_structure,
            "project_plan": {task_id: asdict(task) for task_id, task in self.project_plan.items()},
            "github_repository_state": asdict(self.github_repository_state) if self.github_repository_state else None,
        }

    def get_recent_activity(self, lookback_seconds: int = 300) -> Dict[str, Any]:
        """Get recent activity summary for the AI"""
        cutoff_time = time.time() - lookback_seconds

        recent_messages = []
        for platform_channels in self.channels.values():
            for channel in platform_channels.values():
                for msg in channel.recent_messages:
                    if msg.timestamp > cutoff_time:
                        recent_messages.append(msg)

        recent_actions = [
            action for action in self.action_history if action.timestamp > cutoff_time
        ]

        # Sort by timestamp
        recent_messages.sort(key=lambda x: x.timestamp or 0)
        recent_actions.sort(key=lambda x: x.timestamp or 0)

        return {
            "recent_messages": [asdict(msg) for msg in recent_messages],
            "recent_actions": [asdict(action) for action in recent_actions],
            "channels": {
                platform: {
                    channel_id: {
                        "name": ch.name,
                        "type": ch.type,
                        "message_count": len(ch.recent_messages),
                        "recent_messages": [asdict(msg) for msg in ch.recent_messages],
                    }
                    for channel_id, ch in platform_channels.items()
                }
                for platform, platform_channels in self.channels.items()
            },
            "system_status": self.system_status,
            "current_time": time.time(),
            "lookback_seconds": lookback_seconds,
        }

    def get_recent_media_actions(self, lookback_seconds: int = 300) -> Dict[str, Any]:
        """Get recent media-related actions to help avoid repetitive operations."""
        cutoff_time = time.time() - lookback_seconds

        recent_media_actions = []
        image_urls_recently_described = set()
        recent_generations = []

        for action in reversed(self.action_history):
            if action.timestamp < cutoff_time:
                break

            if action.action_type == "describe_image":
                # Only consider successful image descriptions to avoid retry loops
                is_successful = hasattr(action, "result") and not (
                    "failure" in str(action.result).lower() or
                    "not accessible" in str(action.result).lower() or
                    "error" in str(action.result).lower()
                )
                
                if is_successful:
                    if hasattr(action, "metadata") and action.metadata:
                        image_url = action.metadata.get("image_url")
                        if image_url:
                            image_urls_recently_described.add(image_url)
                    elif hasattr(action, "parameters") and action.parameters:
                        image_url = action.parameters.get("image_url")
                        if image_url:
                            image_urls_recently_described.add(image_url)
                
                # Include all describe_image actions in recent_media_actions for context
                recent_media_actions.append(
                    {
                        "action": "describe_image",
                        "timestamp": action.timestamp,
                        "image_url": action.parameters.get("image_url")
                        if hasattr(action, "parameters")
                        else None,
                        "status": "success" if is_successful else "failed",
                        "result": str(action.result) if hasattr(action, "result") else None,
                    }
                )

            elif action.action_type == "generate_image":
                recent_generations.append(
                    {
                        "action": "generate_image",
                        "timestamp": action.timestamp,
                        "prompt": action.parameters.get("prompt")
                        if hasattr(action, "parameters")
                        else None,
                        "result_url": action.result if hasattr(action, "result") else None,
                    }
                )
                recent_media_actions.append(recent_generations[-1])

        return {
            "recent_media_actions": recent_media_actions[-10:],  # Last 10 media actions
            "images_recently_described": list(image_urls_recently_described),
            "recent_generations": recent_generations[-5:],  # Last 5 generations
            "summary": {
                "total_recent_media_actions": len(recent_media_actions),
                "unique_images_described": len(image_urls_recently_described),
                "recent_generation_count": len(recent_generations),
            },
        }

    def update_codebase_structure(self, structure: Dict[str, Any]):
        """Update the codebase structure from GitHub or local analysis."""
        self.codebase_structure = structure
        self.last_update = time.time()

    def add_project_task(self, task: DevelopmentTask):
        """Add a new development task to the plan (compatibility method)."""
        self.project_plan[task.task_id] = task
        self.development_tasks[task.task_id] = task  # Also add to new structure
        self.last_update = time.time()

    def update_project_task(self, task_id: str, **kwargs):
        """Update an existing development task."""
        if task_id in self.development_tasks:
            task = self.development_tasks[task_id]
            for key, value in kwargs.items():
                if hasattr(task, key):
                    setattr(task, key, value)
            task.updated_at = time.time()
            self.last_update = time.time()
            # Keep structure in sync
            if task_id in self.project_plan:
                self.project_plan[task_id] = task

    def get_project_tasks_by_status(self, status: str) -> List[DevelopmentTask]:
        """Get all development tasks with a specific status."""
        return [task for task in self.development_tasks.values() if task.status == status]

    def add_target_repository(self, repo_url: str, context: TargetRepositoryContext):
        """Add or update target repository context for ACE operations."""
        self.target_repositories[repo_url] = context
        self.last_update = time.time()

    def get_target_repository(self, repo_url: str) -> Optional[TargetRepositoryContext]:
        """Get target repository context by URL."""
        return self.target_repositories.get(repo_url)

    def update_github_repo_state(self, **kwargs):
        """Update GitHub repository state fields (compatibility method)."""
        if self.github_repository_state is None:
            self.github_repository_state = TargetRepositoryContext()
        for key, value in kwargs.items():
            if hasattr(self.github_repository_state, key):
                setattr(self.github_repository_state, key, value)
        self.last_update = time.time()
