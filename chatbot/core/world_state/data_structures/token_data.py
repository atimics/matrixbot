#!/usr/bin/env python3
"""
Token Data Structures

Defines token-related data structures for tracking token metadata and holders.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .message import Message


@dataclass
class TokenMetadata:
    """
    Comprehensive token metadata including market data and activity metrics.
    
    Attributes:
        contract_address: The token's contract address
        ticker: Token ticker symbol (e.g., 'ETH', 'USDC')
        name: Full token name
        description: Token description
        market_cap: Current market capitalization in USD
        price_usd: Current price in USD
        price_change_24h: 24-hour price change percentage
        volume_24h: 24-hour trading volume in USD
        total_supply: Total token supply
        circulating_supply: Circulating token supply
        holder_count: Total number of token holders
        top_holder_percentage: Percentage of supply held by top holder
        last_updated: Timestamp of last metadata update
        dex_info: DEX trading information (pools, liquidity, etc.)
        social_metrics: Social media activity metrics
    """
    contract_address: str
    ticker: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    market_cap: Optional[float] = None
    price_usd: Optional[float] = None
    price_change_24h: Optional[float] = None
    volume_24h: Optional[float] = None
    total_supply: Optional[float] = None
    circulating_supply: Optional[float] = None
    holder_count: Optional[int] = None
    top_holder_percentage: Optional[float] = None
    last_updated: Optional[float] = None
    dex_info: Dict[str, Any] = field(default_factory=dict)
    social_metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TokenHolderData:
    """
    Enhanced token holder information with balance and ranking data.
    
    Attributes:
        address: Wallet address of the holder
        balance: Token balance
        percentage_of_supply: Percentage of total supply held
        rank: Ranking among all holders (1 = largest holder)
        fid: Associated Farcaster ID (if available)
        last_transaction_timestamp: Timestamp of last token transaction
        is_whale: Whether this holder qualifies as a "whale"
        transaction_count: Number of token transactions
    """
    address: str
    balance: float
    percentage_of_supply: float
    rank: int
    fid: Optional[str] = None
    last_transaction_timestamp: Optional[float] = None
    is_whale: bool = False
    transaction_count: Optional[int] = None


@dataclass
class MonitoredTokenHolder:
    """
    Represents a monitored token holder with their Farcaster activity and token data.
    
    Attributes:
        fid: Farcaster ID of the holder
        username: Farcaster username
        display_name: Display name
        last_cast_seen_timestamp: Timestamp of the last cast seen from this holder
        recent_casts: List of recent messages from this holder
        token_holder_data: Enhanced token holding information
        social_influence_score: Calculated influence score based on followers/activity
        last_activity_timestamp: Timestamp of last Farcaster activity
    """
    fid: str
    username: Optional[str] = None
    display_name: Optional[str] = None
    last_cast_seen_timestamp: Optional[float] = None
    recent_casts: List[Message] = field(default_factory=list)
    token_holder_data: Optional[TokenHolderData] = None
    social_influence_score: Optional[float] = None
    last_activity_timestamp: Optional[float] = None
