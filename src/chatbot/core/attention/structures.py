"""
Attention Engine Structures - Core Data Structures for Thread-Centric Processing

This module defines the fundamental data structures for the new attention-driven architecture:
- ContextualThread: The new fundamental unit of work containing rich context
- ThreadPriority: Enum for thread priority levels
- AttentionMetrics: Tracking and optimization data for the attention system
"""

import time
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Union
from enum import IntEnum

from ..world_state.structures import Message, Channel, FarcasterUserDetails, MatrixUserDetails


class ThreadPriority(IntEnum):
    """Priority levels for contextual threads."""
    LOWEST = 1
    LOW = 3  
    NORMAL = 5
    HIGH = 7
    URGENT = 9
    CRITICAL = 10


@dataclass
class ContextualThread:
    """
    The fundamental unit of work in the new attention-driven architecture.
    
    A ContextualThread represents a self-contained bundle of context that gives the AI
    everything it needs to make an intelligent decision about a triggering message.
    This eliminates the need for raw message processing and ensures no message is 
    ever seen in isolation.
    
    Attributes:
        thread_id: Unique identifier for this thread context
        triggering_message: The new message that caught the engine's attention
        conversation_history: Direct reply-chain leading up to the triggering message
        author_context: Rich profile of the message's author
        channel_context: Metadata about the channel where conversation is happening
        priority: ThreadPriority level for processing order
        reason: Human-readable explanation of why this thread warranted attention
        attention_timestamp: When this thread was created by the AttentionEngine
        processing_deadline: Optional deadline for processing this thread
        context_metadata: Additional context information and analysis
    """
    thread_id: str
    triggering_message: Message
    conversation_history: List[Message] = field(default_factory=list)
    author_context: Optional[Union[FarcasterUserDetails, MatrixUserDetails]] = None
    channel_context: Optional[Channel] = None
    priority: ThreadPriority = ThreadPriority.NORMAL
    reason: str = "New user message"
    attention_timestamp: float = field(default_factory=time.time)
    processing_deadline: Optional[float] = None
    context_metadata: Dict[str, Any] = field(default_factory=dict)
    
    def calculate_context_score(self) -> float:
        """
        Calculate a numerical score representing the richness of context available.
        
        This helps optimize processing by identifying threads with more complete context.
        Higher scores indicate more comprehensive context for better AI decision-making.
        
        Returns:
            Float score from 0.0 to 1.0 indicating context completeness
        """
        score = 0.0
        max_score = 6.0  # Total possible points
        
        # Points for conversation history depth
        if len(self.conversation_history) > 0:
            score += min(len(self.conversation_history) / 5.0, 1.0)  # Up to 1 point
        
        # Points for author context availability
        if self.author_context:
            score += 1.0
            # Bonus points for rich author data (Farcaster-specific)
            if isinstance(self.author_context, FarcasterUserDetails):
                if self.author_context.bio:
                    score += 0.5
                if self.author_context.follower_count:
                    score += 0.5
        
        # Points for channel context
        if self.channel_context:
            score += 1.0
            # Bonus for channel activity data
            if len(self.channel_context.recent_messages) > 5:
                score += 0.5
        
        # Points for message complexity/richness
        content_length = len(self.triggering_message.content)
        if content_length > 50:
            score += min(content_length / 200.0, 1.0)  # Up to 1 point
        
        # Points for multimedia content
        if self.triggering_message.image_urls:
            score += 0.5
        
        return min(score / max_score, 1.0)
    
    def is_expired(self) -> bool:
        """Check if this thread has exceeded its processing deadline."""
        if not self.processing_deadline:
            return False
        return time.time() > self.processing_deadline
    
    def get_age_minutes(self) -> float:
        """Get the age of this thread in minutes."""
        return (time.time() - self.attention_timestamp) / 60.0
    
    def to_summary_dict(self) -> Dict[str, Any]:
        """
        Convert to a summary dictionary for logging and monitoring.
        
        Returns:
            Dictionary with key metrics and identifiers for this thread
        """
        return {
            "thread_id": self.thread_id,
            "priority": self.priority.name,
            "reason": self.reason,
            "message_id": self.triggering_message.id,
            "channel_id": self.triggering_message.channel_id,
            "channel_type": self.triggering_message.channel_type,
            "author": self.triggering_message.sender_username or self.triggering_message.sender,
            "context_score": self.calculate_context_score(),
            "conversation_depth": len(self.conversation_history),
            "age_minutes": self.get_age_minutes(),
            "has_author_context": self.author_context is not None,
            "has_channel_context": self.channel_context is not None,
            "content_preview": self.triggering_message.content[:100] + "..." if len(self.triggering_message.content) > 100 else self.triggering_message.content
        }


@dataclass
class AttentionMetrics:
    """
    Metrics and performance tracking for the AttentionEngine.
    
    This data structure tracks the performance and behavior of the attention system
    to enable optimization and monitoring of the new architecture.
    """
    total_messages_processed: int = 0
    threads_created: int = 0
    threads_filtered_out: int = 0
    self_messages_ignored: int = 0
    cooldown_filtered: int = 0
    priority_distribution: Dict[str, int] = field(default_factory=dict)
    average_context_score: float = 0.0
    processing_times: List[float] = field(default_factory=list)
    last_reset: float = field(default_factory=time.time)
    
    def add_thread_created(self, thread: ContextualThread, processing_time: float) -> None:
        """Record that a new thread was created."""
        self.threads_created += 1
        self.total_messages_processed += 1
        
        # Update priority distribution
        priority_name = thread.priority.name
        if priority_name not in self.priority_distribution:
            self.priority_distribution[priority_name] = 0
        self.priority_distribution[priority_name] += 1
        
        # Update processing time tracking
        self.processing_times.append(processing_time)
        if len(self.processing_times) > 100:  # Keep last 100 measurements
            self.processing_times = self.processing_times[-100:]
        
        # Update average context score
        context_score = thread.calculate_context_score()
        current_total = self.average_context_score * (self.threads_created - 1)
        self.average_context_score = (current_total + context_score) / self.threads_created
    
    def add_message_filtered(self, reason: str) -> None:
        """Record that a message was filtered out."""
        self.total_messages_processed += 1
        self.threads_filtered_out += 1
        
        if reason == "self_message":
            self.self_messages_ignored += 1
        elif reason == "cooldown":
            self.cooldown_filtered += 1
    
    def get_average_processing_time(self) -> float:
        """Get the average processing time for thread creation."""
        if not self.processing_times:
            return 0.0
        return sum(self.processing_times) / len(self.processing_times)
    
    def get_attention_rate(self) -> float:
        """Get the percentage of messages that result in threads."""
        if self.total_messages_processed == 0:
            return 0.0
        return self.threads_created / self.total_messages_processed
    
    def reset_metrics(self) -> None:
        """Reset all metrics for a fresh measurement period."""
        self.total_messages_processed = 0
        self.threads_created = 0
        self.threads_filtered_out = 0
        self.self_messages_ignored = 0
        self.cooldown_filtered = 0
        self.priority_distribution.clear()
        self.average_context_score = 0.0
        self.processing_times.clear()
        self.last_reset = time.time()
    
    def to_summary_dict(self) -> Dict[str, Any]:
        """Convert metrics to a summary dictionary for monitoring."""
        return {
            "total_messages_processed": self.total_messages_processed,
            "threads_created": self.threads_created,
            "threads_filtered_out": self.threads_filtered_out,
            "self_messages_ignored": self.self_messages_ignored,
            "cooldown_filtered": self.cooldown_filtered,
            "attention_rate": self.get_attention_rate(),
            "average_context_score": self.average_context_score,
            "average_processing_time_ms": self.get_average_processing_time() * 1000,
            "priority_distribution": self.priority_distribution.copy(),
            "uptime_hours": (time.time() - self.last_reset) / 3600.0
        }
