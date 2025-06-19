#!/usr/bin/env python3
"""
NFT Data Structures

Defines NFT-related data structures for metadata and mint records.
"""

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class NFTMetadata:
    """
    NFT metadata structure following OpenSea/ERC-721 standards.
    
    Attributes:
        name: The name of the NFT
        description: Description of the NFT
        image: URL to the image (S3 or Arweave)
        image_data: Optional base64 encoded image data
        external_url: Optional external URL for more info
        animation_url: Optional URL to multimedia content
        background_color: Optional background color
        youtube_url: Optional YouTube URL
        attributes: List of traits/attributes
        created_by: Creator information
        created_at: Creation timestamp
        metadata_uri: URI where this metadata is stored (Arweave/IPFS)
    """
    name: str
    description: str
    image: str
    image_data: Optional[str] = None
    external_url: Optional[str] = None
    animation_url: Optional[str] = None
    background_color: Optional[str] = None
    youtube_url: Optional[str] = None
    attributes: List[Dict[str, Any]] = field(default_factory=list)
    created_by: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    metadata_uri: Optional[str] = None


@dataclass
class NFTMintRecord:
    """
    Record of an NFT mint/claim event.
    
    Attributes:
        nft_id: Unique identifier for the NFT
        token_id: On-chain token ID
        contract_address: NFT contract address
        recipient_fid: Farcaster ID of the recipient
        recipient_address: Wallet address of the recipient
        metadata: NFT metadata
        mint_type: Type of mint ('airdrop', 'claim', 'purchase')
        transaction_hash: Blockchain transaction hash
        block_number: Block number of the mint
        gas_used: Gas used for the transaction
        mint_timestamp: When the mint occurred
        frame_url: Frame URL used for the mint (if applicable)
        eligibility_criteria_met: Dict of criteria that were satisfied
    """
    nft_id: str
    token_id: Optional[int] = None
    contract_address: Optional[str] = None
    recipient_fid: str = ""
    recipient_address: str = ""
    metadata: Optional[NFTMetadata] = None
    mint_type: str = "claim"  # 'airdrop', 'claim', 'purchase'
    transaction_hash: Optional[str] = None
    block_number: Optional[int] = None
    gas_used: Optional[int] = None
    mint_timestamp: float = field(default_factory=time.time)
    frame_url: Optional[str] = None
    eligibility_criteria_met: Dict[str, bool] = field(default_factory=dict)
