#!/usr/bin/env python3
"""
System Data Structures

Defines system-level data structures for tracking actions, sentiment, and memory.
"""

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ActionHistory:
    """
    Represents a completed or scheduled action with comprehensive tracking.

    This class maintains a complete audit trail of bot actions, enabling deduplication,
    performance monitoring, and intelligent decision-making about future actions.

    Attributes:
        action_type: Type of action performed (e.g., 'send_farcaster_reply', 'like_farcaster_post')
        parameters: Dictionary of parameters used for the action execution
        result: Result or status of the action ('success', 'failure', 'scheduled', etc.)
        timestamp: Unix timestamp when the action was completed or updated
        action_id: Unique identifier for tracking and updating scheduled actions

    Usage:
        - Deduplication: Prevents duplicate likes, follows, and replies
        - Performance Monitoring: Tracks success rates and execution times
        - State Consistency: Ensures actions are properly recorded and updated
        - AI Context: Provides historical context for future decision-making
    """

    action_type: str
    parameters: Dict[str, Any]
    result: str
    timestamp: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    action_id: Optional[str] = None  # Unique ID for tracking/updating scheduled actions


@dataclass
class SentimentData:
    """
    Tracks user sentiment based on their interactions.
    
    Attributes:
        score: Sentiment score from -1.0 (very negative) to 1.0 (very positive)
        label: Human-readable sentiment label (positive, negative, neutral)
        last_updated: Unix timestamp of last sentiment update
        confidence: Optional confidence score for the sentiment analysis
        history: List of recent sentiment scores for trending analysis
    """
    score: float  # -1.0 to 1.0
    label: str    # "positive", "negative", "neutral"
    last_updated: float
    confidence: Optional[float] = None
    history: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class MemoryEntry:
    """
    Represents a specific memory or observation about a user.
    
    Attributes:
        user_platform_id: Platform-specific user identifier (e.g., "matrix:@user:server.com", "farcaster:fid:123")
        timestamp: Unix timestamp when this memory was created
        content: The core text content of the memory
        memory_id: Unique identifier for this memory entry
        source_message_id: Optional ID of the message this memory relates to
        source_cast_hash: Optional Farcaster cast hash this memory relates to
        related_entities: List of related users, topics, or entities
        memory_type: Type of memory (observation, preference, fact, etc.)
        importance: Importance score from 0.0 to 1.0
        ai_summary: Optional AI-generated summary of this memory
    """
    user_platform_id: str
    timestamp: float
    content: str
    memory_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source_message_id: Optional[str] = None
    source_cast_hash: Optional[str] = None
    related_entities: List[str] = field(default_factory=list)
    memory_type: str = "observation"  # observation, preference, fact, important_interaction
    importance: float = 0.5  # 0.0 to 1.0
    ai_summary: Optional[str] = None
