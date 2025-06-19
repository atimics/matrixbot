#!/usr/bin/env python3
"""
Project and Development Data Structures

Defines structures for research, development tasks, and project management.
"""

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ResearchEntry:
    """
    Represents a research entry in the persistent knowledge base.
    
    This stores information gathered through web searches and user interactions
    to build an evolving knowledge base that improves the AI's reliability over time.
    
    Attributes:
        topic: Key topic or subject (normalized to lowercase for deduplication)
        summary: Concise summary of current knowledge about the topic
        key_facts: List of important facts or data points
        sources: List of sources where information was gathered
        confidence_level: Confidence in the information accuracy (1-10 scale)
        last_updated: Timestamp when this entry was last updated
        last_verified: Timestamp when information was last verified
        tags: List of tags for categorization and cross-referencing
        related_topics: List of related topic keys for knowledge graph connections
        verification_notes: Notes about information verification or concerns
    """
    topic: str
    summary: str
    key_facts: List[str] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)
    confidence_level: int = 5  # 1-10 scale, 5 is neutral
    last_updated: float = field(default_factory=time.time)
    last_verified: Optional[float] = None
    tags: List[str] = field(default_factory=list)
    related_topics: List[str] = field(default_factory=list)
    verification_notes: Optional[str] = None


@dataclass
class TargetRepositoryContext:
    """
    Comprehensive context for a target repository in the ACE system.
    
    This structure maintains all necessary information for the AI to work on
    improving a specific codebase, whether external or its own.
    """
    url: str = ""  # Main repository URL (e.g., "https://github.com/owner/repo")
    fork_url: Optional[str] = None  # AI's fork URL
    local_clone_path: Optional[str] = None  # Local workspace path
    current_branch: Optional[str] = None  # Current working branch
    active_task_id: Optional[str] = None  # Currently active development task
    open_issues_summary: List[Dict[str, Any]] = field(default_factory=list)  # GitHub issues
    open_prs_summary: List[Dict[str, Any]] = field(default_factory=list)  # GitHub PRs
    codebase_structure: Optional[Dict[str, Any]] = None  # File tree and analysis
    last_synced_with_upstream: Optional[float] = None
    setup_complete: bool = False  # Whether workspace is ready for development


@dataclass
class DevelopmentTask:
    """
    Represents a development task in the ACE system lifecycle.
    
    Tracks the complete evolution from identification through implementation
    and feedback, enabling the AI to learn from outcomes.
    """
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    description: str = ""  # Detailed task description from AI or human
    target_repository: str = ""  # Repository URL this task applies to
    target_files: List[str] = field(default_factory=list)  # Files to modify
    status: str = "proposed"  # proposed, feedback_pending, approved, implementation_in_progress, pr_submitted, merged, closed
    priority: int = 5  # 1-10
    
    # ACE Lifecycle tracking
    initial_proposal: Optional[str] = None  # AI's initial proposal text
    feedback_summary: Optional[str] = None  # Human feedback from Matrix/PR
    implementation_plan: Optional[str] = None  # Detailed plan for code changes
    associated_pr_url: Optional[str] = None  # GitHub PR URL
    pr_status: Optional[str] = None  # open, merged, closed
    
    # Learning and evaluation
    validation_results: Optional[str] = None  # Test results, error logs, etc.
    key_learnings: Optional[str] = None  # What the AI learned from this task
    performance_impact: Optional[str] = None  # Measurable impact if available
    
    # Metadata
    source_reference: Optional[str] = None  # Matrix room, log entry, etc. that triggered this
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None


@dataclass
class ProjectTask:
    """
    Represents a project task for legacy compatibility with UpdateProjectPlan tool.
    
    This is a simpler variant of DevelopmentTask focused on project planning
    rather than the full ACE lifecycle.
    """
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    description: str = ""
    status: str = "todo"  # todo, in_progress, completed, blocked
    priority: int = 5  # 1-10, higher number = higher priority
    estimated_complexity: Optional[int] = None  # 1-10 complexity estimate
    related_code_files: List[str] = field(default_factory=list)  # Files this task affects
    source_references: List[str] = field(default_factory=list)  # Source docs, issues, etc.
    
    # Metadata
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None


@dataclass
class Goal:
    """
    Represents a long-term goal or task for the AI system.
    
    Goals provide strategic direction beyond reactive behavior, allowing the AI
    to work towards specific objectives over time.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    description: str = ""
    status: str = "active"  # active, completed, paused, cancelled
    priority: int = 5  # 1-10, higher is more important
    created_timestamp: float = field(default_factory=time.time)
    target_completion: Optional[float] = None  # Optional deadline
    completion_criteria: List[str] = field(default_factory=list)
    sub_tasks: List[str] = field(default_factory=list)  # List of task descriptions
    progress_metrics: Dict[str, Any] = field(default_factory=dict)
    category: str = "general"  # e.g., "community_growth", "content_creation", "engagement"
    related_channels: List[str] = field(default_factory=list)  # Channels relevant to this goal
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_progress_update(self, update: str, metrics: Optional[Dict[str, Any]] = None):
        """Add a progress update to the goal."""
        if "progress_updates" not in self.metadata:
            self.metadata["progress_updates"] = []
        
        self.metadata["progress_updates"].append({
            "timestamp": time.time(),
            "update": update,
            "metrics": metrics or {}
        })
    
    def mark_completed(self, completion_note: str = ""):
        """Mark the goal as completed."""
        self.status = "completed"
        self.metadata["completed_timestamp"] = time.time()
        if completion_note:
            self.metadata["completion_note"] = completion_note
    
    def get_progress_summary(self) -> Dict[str, Any]:
        """Get a summary of goal progress."""
        updates = self.metadata.get("progress_updates", [])
        return {
            "goal_id": self.id,
            "title": self.title,
            "status": self.status,
            "priority": self.priority,
            "created_days_ago": (time.time() - self.created_timestamp) / 86400,
            "total_updates": len(updates),
            "latest_update": updates[-1] if updates else None,
            "completion_criteria_count": len(self.completion_criteria),
            "sub_tasks_count": len(self.sub_tasks)
        }
