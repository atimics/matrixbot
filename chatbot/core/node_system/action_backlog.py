"""
Action Backlog System for Kanban-style Continuous Processing

This module implements a prioritized action backlog that supports:
- Priority-based action queuing
- Service-specific rate limiting
- WIP (Work In Progress) limits
- Action deferral and retry logic
"""

import asyncio
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class ActionPriority(Enum):
    """Action priority levels"""
    CRITICAL = 1  # Immediate response required (direct mentions, DMs)
    HIGH = 2      # Important but can wait briefly (channel activity in monitored channels)
    MEDIUM = 3    # Background tasks (search, exploration)
    LOW = 4       # Housekeeping, optimization


class ActionStatus(Enum):
    """Action execution status"""
    QUEUED = "queued"
    IN_PROGRESS = "in_progress" 
    COMPLETED = "completed"
    FAILED = "failed"
    DEFERRED = "deferred"


@dataclass
class QueuedAction:
    """A single action in the backlog"""
    action_id: str
    action_type: str
    parameters: Dict[str, Any]
    priority: ActionPriority
    service: str  # e.g., "matrix", "farcaster", "node_system"
    reasoning: str = ""
    
    # Execution tracking
    status: ActionStatus = ActionStatus.QUEUED
    created_at: float = field(default_factory=time.time)
    attempts: int = 0
    max_attempts: int = 3
    last_attempt_at: Optional[float] = None
    retry_after: Optional[float] = None  # Time when action can be retried after rate limiting
    error: Optional[str] = None  # Error message if action failed
    
    # Dependencies and sequencing
    depends_on: List[str] = field(default_factory=list)
    blocks: List[str] = field(default_factory=list)
    
    # Context
    cycle_id: str = ""
    trigger_type: str = ""
    channel_id: str = ""


class ServiceRateLimiter:
    """Rate limiter for a specific service"""
    
    def __init__(self, service_name: str, max_concurrent: int = 2, min_interval: float = 0.5):
        self.service_name = service_name
        self.max_concurrent = max_concurrent
        self.min_interval = min_interval
        
        self.active_actions: Set[str] = set()
        self.last_execution_time = 0.0
        
    def can_execute(self) -> bool:
        """Check if we can execute another action for this service"""
        # Check concurrent limit
        if len(self.active_actions) >= self.max_concurrent:
            return False
            
        # Check minimum interval
        time_since_last = time.time() - self.last_execution_time
        if time_since_last < self.min_interval:
            return False
            
        return True
    
    def acquire(self, action_id: str) -> bool:
        """Acquire execution slot for an action"""
        if not self.can_execute():
            return False
            
        self.active_actions.add(action_id)
        self.last_execution_time = time.time()
        return True
    
    def release(self, action_id: str):
        """Release execution slot"""
        self.active_actions.discard(action_id)


class ActionBacklog:
    """
    Prioritized action backlog with service rate limiting and WIP limits
    """
    
    def __init__(self, max_total_wip: int = 15):  # Increased from 10 to 15
        self.max_total_wip = max_total_wip
        
        # Main backlog storage
        self.queued_actions: Dict[ActionPriority, deque] = {
            priority: deque() for priority in ActionPriority
        }
        self.in_progress: Dict[str, QueuedAction] = {}
        self.completed: Dict[str, QueuedAction] = {}
        self.failed: Dict[str, QueuedAction] = {}
        
        # Service rate limiters with increased capacity for continuous processing
        self.rate_limiters: Dict[str, ServiceRateLimiter] = {
            "matrix": ServiceRateLimiter("matrix", max_concurrent=4, min_interval=0.2),  # Increased capacity
            "farcaster": ServiceRateLimiter("farcaster", max_concurrent=3, min_interval=0.8),  # Increased capacity
            "node_system": ServiceRateLimiter("node_system", max_concurrent=6, min_interval=0.05),  # Increased capacity
            "search": ServiceRateLimiter("search", max_concurrent=3, min_interval=0.3),  # Increased capacity
        }
        
        # Dependency tracking
        self.dependency_graph: Dict[str, Set[str]] = defaultdict(set)
        
        self._action_counter = 0
        
    def add_action(self, action_type: str, parameters: Dict[str, Any], 
                   priority: ActionPriority, service: str, **kwargs) -> str:
        """Add an action to the backlog"""
        self._action_counter += 1
        action_id = f"{action_type}_{self._action_counter}_{int(time.time())}"
        
        action = QueuedAction(
            action_id=action_id,
            action_type=action_type,
            parameters=parameters,
            priority=priority,
            service=service,
            **kwargs
        )
        
        # Add to appropriate priority queue
        self.queued_actions[priority].append(action)
        
        # Track dependencies
        for dep_id in action.depends_on:
            self.dependency_graph[dep_id].add(action_id)
            
        logger.debug(f"Added action {action_id} to backlog (priority: {priority.name}, service: {service})")
        return action_id
    
    def add_actions_batch(self, actions: List[Dict[str, Any]], 
                         default_priority: ActionPriority = ActionPriority.MEDIUM,
                         cycle_context: Optional[Dict[str, Any]] = None) -> List[str]:
        """Add multiple actions from AI planning phase"""
        action_ids = []
        
        for action_dict in actions:
            # Determine priority based on action type and context
            priority = self._determine_priority(action_dict, cycle_context)
            service = self._determine_service(action_dict["action_type"])
            
            action_id = self.add_action(
                action_type=action_dict["action_type"],
                parameters=action_dict["parameters"],
                priority=priority,
                service=service,
                reasoning=action_dict.get("reasoning", ""),
                cycle_id=cycle_context.get("cycle_id", "") if cycle_context else "",
                trigger_type=cycle_context.get("trigger_type", "") if cycle_context else "",
                channel_id=cycle_context.get("current_channel_id", "") if cycle_context else ""
            )
            action_ids.append(action_id)
            
        return action_ids
    
    def get_next_executable_action(self) -> Optional[QueuedAction]:
        """Get the next action that can be executed given current constraints"""
        # Check WIP limit
        if len(self.in_progress) >= self.max_total_wip:
            return None
            
        # Look through priority levels
        for priority in ActionPriority:
            queue = self.queued_actions[priority]
            
            # Look for executable actions in this priority level
            for i, action in enumerate(queue):
                # Check if action is waiting due to rate limiting
                if action.retry_after and time.time() < action.retry_after:
                    continue
                    
                # Check dependencies
                if not self._dependencies_satisfied(action):
                    continue
                    
                # Check service rate limits
                rate_limiter = self.rate_limiters.get(action.service)
                if rate_limiter and not rate_limiter.can_execute():
                    continue
                    
                # Found an executable action
                queue.remove(action)
                return action
                
        return None
    
    def start_action(self, action: QueuedAction) -> bool:
        """Mark action as in progress and acquire service resources"""
        rate_limiter = self.rate_limiters.get(action.service)
        if rate_limiter and not rate_limiter.acquire(action.action_id):
            return False
            
        action.status = ActionStatus.IN_PROGRESS
        action.last_attempt_at = time.time()
        action.attempts += 1
        
        self.in_progress[action.action_id] = action
        
        logger.debug(f"Started action {action.action_id} (service: {action.service})")
        return True
    
    def complete_action(self, action_id: str, success: bool = True, error: Optional[str] = None):
        """Mark action as completed or failed"""
        if action_id not in self.in_progress:
            logger.warning(f"Cannot complete action {action_id}: not in progress")
            return
            
        action = self.in_progress.pop(action_id)
        
        # Release service resources
        rate_limiter = self.rate_limiters.get(action.service)
        if rate_limiter:
            rate_limiter.release(action_id)
            
        if success:
            action.status = ActionStatus.COMPLETED
            self.completed[action_id] = action
            
            # Mark dependent actions as ready
            self._update_dependencies(action_id)
            
            logger.debug(f"Completed action {action_id}")
        else:
            action.status = ActionStatus.FAILED
            action.error = error  # Store the error message
            
            # Retry logic
            if action.attempts < action.max_attempts:
                action.status = ActionStatus.QUEUED
                self.queued_actions[action.priority].appendleft(action)  # High priority for retry
                logger.debug(f"Retrying action {action_id} (attempt {action.attempts}/{action.max_attempts})")
            else:
                self.failed[action_id] = action
                logger.warning(f"Action {action_id} failed permanently: {error}")
    
    def get_status_summary(self) -> Dict[str, Any]:
        """Get summary of backlog status"""
        total_queued = sum(len(queue) for queue in self.queued_actions.values())
        
        return {
            "total_queued": total_queued,
            "in_progress": len(self.in_progress),
            "completed_recent": len([a for a in self.completed.values() 
                                   if time.time() - a.created_at < 300]),  # Last 5 minutes
            "failed": len(self.failed),
            "wip_utilization": f"{len(self.in_progress)}/{self.max_total_wip}",
            "service_status": {
                service: {
                    "active": len(limiter.active_actions),
                    "max_concurrent": limiter.max_concurrent,
                    "can_execute": limiter.can_execute()
                }
                for service, limiter in self.rate_limiters.items()
            }
        }
    
    def _determine_priority(self, action_dict: Dict[str, Any], 
                          cycle_context: Optional[Dict[str, Any]]) -> ActionPriority:
        """Determine action priority based on type and context"""
        action_type = action_dict["action_type"]
        
        # High priority for communication actions
        if action_type in ["send_matrix_reply", "send_farcaster_reply"]:
            return ActionPriority.HIGH
            
        # Critical for mentions and DMs
        if cycle_context and cycle_context.get("trigger_type") == "mention":
            return ActionPriority.CRITICAL
            
        # Medium for exploration and search
        if action_type in ["expand_node", "search_casts", "get_trending_casts"]:
            return ActionPriority.MEDIUM
            
        # Low for housekeeping
        if action_type in ["collapse_node", "refresh_summary"]:
            return ActionPriority.LOW
            
        return ActionPriority.MEDIUM
    
    def _determine_service(self, action_type: str) -> str:
        """Determine which service handles this action type"""
        if action_type.startswith("send_matrix") or "matrix" in action_type:
            return "matrix"
        elif action_type.startswith("send_farcaster") or "farcaster" in action_type or "cast" in action_type:
            return "farcaster"
        elif action_type in ["expand_node", "collapse_node", "pin_node", "unpin_node"]:
            return "node_system"
        elif "search" in action_type or "trending" in action_type:
            return "search"
        else:
            return "node_system"  # Default
    
    def _dependencies_satisfied(self, action: QueuedAction) -> bool:
        """Check if all dependencies for an action are satisfied"""
        for dep_id in action.depends_on:
            if dep_id not in self.completed:
                return False
        return True
    
    def _update_dependencies(self, completed_action_id: str):
        """Update dependency tracking when an action completes"""
        # This is handled automatically by the dependency checking in get_next_executable_action
        pass

    def schedule_delayed_retry(self, action_id: str, delay_seconds: float):
        """Schedule an action for delayed retry due to rate limiting"""
        if action_id not in self.in_progress:
            logger.warning(f"Cannot schedule delayed retry for action {action_id}: not in progress")
            return
        
        action = self.in_progress[action_id]
        
        # Release service resources
        service = action.service or "default"
        if service in self.rate_limiters:
            self.rate_limiters[service].release(action_id)
        
        # Remove from in_progress
        del self.in_progress[action_id]
        
        # Set a retry time
        action.retry_after = time.time() + delay_seconds
        action.status = ActionStatus.QUEUED
        
        # Put back in queue with high priority since it was already being executed
        self.queued_actions[ActionPriority.HIGH].appendleft(action)
        
        logger.debug(f"Scheduled delayed retry for action {action_id} in {delay_seconds} seconds")
