"""
Attention Package - Thread-Centric Processing Architecture

This package implements the core components of the new attention-driven architecture:

- structures: Data structures for ContextualThread and related objects
- engine: AttentionEngine for intelligent message filtering and context aggregation

The attention system transforms raw message events into rich, context-aware threads
that serve as the fundamental unit of work for the AI agent.
"""

from .structures import ContextualThread, ThreadPriority, AttentionMetrics
from .engine import AttentionEngine

__all__ = [
    'ContextualThread',
    'ThreadPriority', 
    'AttentionMetrics',
    'AttentionEngine'
]
