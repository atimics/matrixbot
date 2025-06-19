"""
World State Data Structures

This package contains all the data structures used by the world state management system.
The structures have been split into logical modules for better maintainability.
"""

# Import all structures to maintain backward compatibility
from .message import Message
from .channel import Channel
from .user_details import FarcasterUserDetails, MatrixUserDetails
from .token_data import TokenMetadata, TokenHolderData, MonitoredTokenHolder
from .nft_data import NFTMetadata, NFTMintRecord
from .system_data import ActionHistory, SentimentData, MemoryEntry
from .project_data import ResearchEntry, TargetRepositoryContext, DevelopmentTask, ProjectTask, Goal
from .world_state_data import WorldStateData

# Export all classes for backward compatibility
__all__ = [
    'Message',
    'Channel',
    'FarcasterUserDetails',
    'MatrixUserDetails',
    'TokenMetadata',
    'TokenHolderData',
    'MonitoredTokenHolder',
    'NFTMetadata',
    'NFTMintRecord',
    'ActionHistory',
    'SentimentData',
    'MemoryEntry',
    'ResearchEntry',
    'TargetRepositoryContext',
    'DevelopmentTask',
    'ProjectTask',
    'Goal',
    'WorldStateData',
]
