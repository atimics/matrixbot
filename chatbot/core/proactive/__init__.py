"""
Proactive Conversation Management Package

This package implements the core proactive conversation capabilities including:
- Conversation opportunity detection
- Engagement strategy selection  
- Proactive conversation initiation
- Context-aware proactive responses
"""

from .proactive_engine import ProactiveConversationEngine, ConversationOpportunity
from .engagement_strategies import EngagementStrategyRegistry, EngagementStrategy

__all__ = [
    "ProactiveConversationEngine",
    "ConversationOpportunity",
    "EngagementStrategyRegistry", 
    "EngagementStrategy"
]
