"""
World State Management Package

This package handles all aspects of world state management:
- Data structures (Message, Channel, ActionHistory, WorldStateData)
- Core state management operations
- AI payload generation for different contexts
"""

from .structures import Message, Channel, ActionHistory, WorldStateData
from .structures import WorldStateData as WorldState  # Alias for backward compatibility
from .manager import WorldStateManager
from .payload_builder import PayloadBuilder

__all__ = [
    "Message",
    "Channel", 
    "ActionHistory",
    "WorldStateData",
    "WorldState",  # Backward compatibility
    "WorldStateManager",
    "PayloadBuilder"
]
