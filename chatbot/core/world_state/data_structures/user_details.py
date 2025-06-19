#!/usr/bin/env python3
"""
User Details Data Structures

Defines user detail structures for different platforms.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .system_data import SentimentData, MemoryEntry


@dataclass
class FarcasterUserDetails:
    """
    Enhanced Farcaster user information with caching capabilities.
    
    Attributes:
        fid: Farcaster ID number
        username: Farcaster username
        display_name: Display name
        bio: User biography
        follower_count: Number of followers
        following_count: Number of following
        pfp_url: Profile picture URL
        power_badge: Whether user has power badge
        timeline_cache: Cached recent casts from user's timeline
        last_timeline_fetch: Timestamp of last timeline fetch
        sentiment: Current sentiment analysis for this user
        memory_entries: List of memory entries for this user
        verified_addresses: Dictionary mapping blockchain networks to wallet addresses
        ecosystem_token_balance_sol: Current balance of ecosystem token on Solana
        ecosystem_nft_count_base: Number of NFTs held from the collection on Base
        is_eligible_for_airdrop: Whether user meets airdrop criteria
        last_eligibility_check: Timestamp of last eligibility verification
        nft_interaction_history: List of NFT mints/claims by this user
    """
    fid: str
    username: Optional[str] = None
    display_name: Optional[str] = None
    bio: Optional[str] = None
    follower_count: Optional[int] = None
    following_count: Optional[int] = None
    pfp_url: Optional[str] = None
    power_badge: bool = False
    timeline_cache: Optional[Dict[str, Any]] = None  # Contains casts and metadata
    last_timeline_fetch: Optional[float] = None
    sentiment: Optional[SentimentData] = None
    memory_entries: List[MemoryEntry] = field(default_factory=list)
    
    # NFT & Cross-chain data (v0.0.4)
    verified_addresses: Dict[str, List[str]] = field(default_factory=dict)  # e.g., {"solana": [...], "evm": [...]}
    ecosystem_token_balance_sol: float = 0.0
    ecosystem_nft_count_base: int = 0
    is_eligible_for_airdrop: bool = False
    last_eligibility_check: Optional[float] = None
    nft_interaction_history: List[Dict[str, Any]] = field(default_factory=list)  # Mint/claim history


@dataclass
class MatrixUserDetails:
    """
    Enhanced Matrix user information.
    
    Attributes:
        user_id: Matrix user ID (@user:server.com)
        display_name: Display name
        avatar_url: Avatar URL
        sentiment: Current sentiment analysis for this user
        memory_entries: List of memory entries for this user
    """
    user_id: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    sentiment: Optional[SentimentData] = None
    memory_entries: List[MemoryEntry] = field(default_factory=list)
