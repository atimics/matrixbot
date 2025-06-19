#!/usr/bin/env python3
"""
World State Data Structures (Legacy Compatibility Module)

This module is now a compatibility layer that imports from the new modular structure.
The actual structures have been split into logical modules for better maintainability.

For new code, import directly from the data_structures package:
    from chatbot.core.world_state.data_structures import Message, Channel, etc.
"""

# Import all structures from the new modular layout for backward compatibility
from .data_structures import (
    Message,
    Channel,
    ActionHistory,
    SentimentData,
    MemoryEntry,
    FarcasterUserDetails,
    MatrixUserDetails,
    TokenMetadata,
    TokenHolderData,
    MonitoredTokenHolder,
    NFTMetadata,
    NFTMintRecord,
    ResearchEntry,
    TargetRepositoryContext,
    DevelopmentTask,
    ProjectTask,
    Goal,
    WorldStateData,
)

# Re-export all classes for backward compatibility
__all__ = [
    'Message',
    'Channel',
    'ActionHistory',
    'SentimentData',
    'MemoryEntry',
    'FarcasterUserDetails',
    'MatrixUserDetails',
    'TokenMetadata',
    'TokenHolderData',
    'MonitoredTokenHolder',
    'NFTMetadata',
    'NFTMintRecord',
    'ResearchEntry',
    'TargetRepositoryContext',
    'DevelopmentTask',
    'ProjectTask',
    'Goal',
    'WorldStateData',
]
