"""
Shared models for the developer tools system.

This module defines the data structures used throughout the ACE (Autonomous Code Evolution)
system for representing code changes, analysis results, and related metadata.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union
from enum import Enum
import uuid
from pathlib import Path


class ChangeType(Enum):
    """Types of code changes that can be proposed and implemented."""
    CREATE = "create"
    MODIFY = "modify"
    DELETE = "delete"
    RENAME = "rename"
    MOVE = "move"


class Priority(Enum):
    """Priority levels for proposed changes."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AnalysisFocus(Enum):
    """Areas of focus for code analysis."""
    CODE_QUALITY = "code_quality"
    PERFORMANCE = "performance"
    SECURITY = "security"
    DOCUMENTATION = "documentation"
    ARCHITECTURE = "architecture"
    TESTING = "testing"


@dataclass
class DiffHunk:
    """Represents a specific diff hunk with line-level precision."""
    file_path: str
    start_line: int
    end_line: int
    old_content: str
    new_content: str
    context_lines_before: List[str] = field(default_factory=list)
    context_lines_after: List[str] = field(default_factory=list)
    
    def to_unified_diff(self) -> str:
        """Convert to unified diff format."""
        lines = []
        lines.extend(f" {line}" for line in self.context_lines_before)
        
        if self.old_content.strip():
            for line in self.old_content.split('\n'):
                if line.strip():
                    lines.append(f"-{line}")
        
        if self.new_content.strip():
            for line in self.new_content.split('\n'):
                if line.strip():
                    lines.append(f"+{line}")
        
        lines.extend(f" {line}" for line in self.context_lines_after)
        return '\n'.join(lines)


@dataclass
class ChangeSpec:
    """
    Specification for a code change with all necessary details for implementation.
    
    This is the shared model that bridges analysis and implementation phases.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    description: str = ""
    change_type: ChangeType = ChangeType.MODIFY
    priority: Priority = Priority.MEDIUM
    
    # File-level information
    file_path: str = ""
    target_file_path: Optional[str] = None  # For rename/move operations
    
    # Change details
    diff_hunks: List[DiffHunk] = field(default_factory=list)
    full_file_content: Optional[str] = None  # For create operations
    
    # Metadata
    rationale: str = ""
    estimated_effort: str = "medium"  # low, medium, high
    affected_files: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)  # Other ChangeSpec IDs
    tags: List[str] = field(default_factory=list)
    
    # Implementation tracking
    implemented: bool = False
    implementation_notes: str = ""
    validation_status: Optional[str] = None  # passed, failed, pending
    
    def add_diff_hunk(
        self, 
        start_line: int, 
        end_line: int, 
        old_content: str, 
        new_content: str,
        context_before: Optional[List[str]] = None,
        context_after: Optional[List[str]] = None
    ) -> None:
        """Add a diff hunk to this change specification."""
        hunk = DiffHunk(
            file_path=self.file_path,
            start_line=start_line,
            end_line=end_line,
            old_content=old_content,
            new_content=new_content,
            context_lines_before=context_before or [],
            context_lines_after=context_after or []
        )
        self.diff_hunks.append(hunk)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "change_type": self.change_type.value,
            "priority": self.priority.value,
            "file_path": self.file_path,
            "target_file_path": self.target_file_path,
            "diff_hunks": [
                {
                    "file_path": hunk.file_path,
                    "start_line": hunk.start_line,
                    "end_line": hunk.end_line,
                    "old_content": hunk.old_content,
                    "new_content": hunk.new_content,
                    "context_lines_before": hunk.context_lines_before,
                    "context_lines_after": hunk.context_lines_after
                }
                for hunk in self.diff_hunks
            ],
            "full_file_content": self.full_file_content,
            "rationale": self.rationale,
            "estimated_effort": self.estimated_effort,
            "affected_files": self.affected_files,
            "dependencies": self.dependencies,
            "tags": self.tags,
            "implemented": self.implemented,
            "implementation_notes": self.implementation_notes,
            "validation_status": self.validation_status
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ChangeSpec':
        """Create from dictionary (deserialization)."""
        change_spec = cls(
            id=data.get("id", str(uuid.uuid4())),
            title=data.get("title", ""),
            description=data.get("description", ""),
            change_type=ChangeType(data.get("change_type", "modify")),
            priority=Priority(data.get("priority", "medium")),
            file_path=data.get("file_path", ""),
            target_file_path=data.get("target_file_path"),
            full_file_content=data.get("full_file_content"),
            rationale=data.get("rationale", ""),
            estimated_effort=data.get("estimated_effort", "medium"),
            affected_files=data.get("affected_files", []),
            dependencies=data.get("dependencies", []),
            tags=data.get("tags", []),
            implemented=data.get("implemented", False),
            implementation_notes=data.get("implementation_notes", ""),
            validation_status=data.get("validation_status")
        )
        
        # Reconstruct diff hunks
        for hunk_data in data.get("diff_hunks", []):
            hunk = DiffHunk(
                file_path=hunk_data["file_path"],
                start_line=hunk_data["start_line"],
                end_line=hunk_data["end_line"],
                old_content=hunk_data["old_content"],
                new_content=hunk_data["new_content"],
                context_lines_before=hunk_data.get("context_lines_before", []),
                context_lines_after=hunk_data.get("context_lines_after", [])
            )
            change_spec.diff_hunks.append(hunk)
        
        return change_spec


@dataclass
class AnalysisResult:
    """Results from codebase analysis."""
    focus: AnalysisFocus
    workspace_path: str
    files_analyzed: List[str] = field(default_factory=list)
    issues_found: List[Dict[str, Any]] = field(default_factory=list)
    opportunities: List[Dict[str, Any]] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    proposed_changes: List[ChangeSpec] = field(default_factory=list)
    analysis_time: float = 0.0
    
    def add_issue(self, file_path: str, line: int, severity: str, message: str, rule_id: str = "") -> None:
        """Add an issue to the analysis results."""
        self.issues_found.append({
            "file_path": file_path,
            "line": line,
            "severity": severity,
            "message": message,
            "rule_id": rule_id,
            "type": "issue"
        })
    
    def add_opportunity(self, file_path: str, message: str, impact: str = "medium") -> None:
        """Add an improvement opportunity to the analysis results."""
        self.opportunities.append({
            "file_path": file_path,
            "message": message,
            "impact": impact,
            "type": "opportunity"
        })
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of the analysis results."""
        return {
            "focus": self.focus.value,
            "files_analyzed_count": len(self.files_analyzed),
            "issues_count": len(self.issues_found),
            "opportunities_count": len(self.opportunities),
            "proposed_changes_count": len(self.proposed_changes),
            "analysis_time": self.analysis_time,
            "metrics": self.metrics
        }


@dataclass 
class RuleMatch:
    """Represents a match from a code analysis rule."""
    rule_id: str
    file_path: str
    line_number: int
    column: Optional[int] = None
    message: str = ""
    severity: str = "info"  # info, warning, error, critical
    suggested_fix: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    
    def to_change_spec(self, change_title: Optional[str] = None) -> Optional[ChangeSpec]:
        """Convert this rule match to a ChangeSpec if it has a suggested fix."""
        if not self.suggested_fix:
            return None
        
        title = change_title or f"Fix {self.rule_id} in {Path(self.file_path).name}"
        
        return ChangeSpec(
            title=title,
            description=self.message,
            change_type=ChangeType.MODIFY,
            priority=Priority.MEDIUM if self.severity == "warning" else Priority.HIGH,
            file_path=self.file_path,
            rationale=f"Rule {self.rule_id}: {self.message}",
            tags=[self.rule_id, self.severity]
        )
