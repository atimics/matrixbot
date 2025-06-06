#!/usr/bin/env python3
"""
Base NFT Service

This service handles all interactions with NFT contracts on the Base blockchain,
including minting, querying balances, and managing metadata uploads.
"""

import asyncio
import json
import logging
import time
from typing import Dict, Any, Optional, List

import aiohttp
from web3 import Web3
from web3.middleware import geth_poa_middleware
from eth_account import Account

from chatbot.config import settings
from chatbot.core.world_state.structures import NFTMetadata, NFTMintRecord

logger = logging.getLogger(__name__)


class BaseNFTService:
    """
    Service for managing NFT operations on the Base blockchain.
    
    This service handles:
    1. NFT contract interactions (minting, querying)
    2. Metadata upload to Arweave/IPFS
    3. Transaction signing and submission
    4. Balance and ownership queries
    """
    
    def __init__(self):
        self.rpc_url = settings.BASE_RPC_URL
        self.contract_address = settings.NFT_COLLECTION_ADDRESS_BASE
        self.dev_wallet_private_key = settings.NFT_DEV_WALLET_PRIVATE_KEY
        self.collection_name = settings.NFT_COLLECTION_NAME
        self.collection_symbol = settings.NFT_COLLECTION_SYMBOL
        
        # Web3 setup
        self.w3: Optional[Web3] = None
        self.contract = None
        self.dev_account = None
        
        # Standard ERC-721 ABI (simplified for minting and querying)
        self.contract_abi = [
            {
                "inputs": [
                    {"internalType": "address", "name": "to", "type": "address"},
                    {"internalType": "string", "name": "tokenURI", "type": "string"}
                ],
                "name": "mint",
                "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
                "stateMutability": "nonpayable",
                "type": "function"
            },
            {
                "inputs": [{"internalType": "address", "name": "owner", "type": "address"}],
                "name": "balanceOf",
                "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [],
                "name": "totalSupply",
                "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [{"internalType": "uint256", "name": "tokenId", "type": "uint256"}],
                "name": "tokenURI",
                "outputs": [{"internalType": "string", "name": "", "type": "string"}],
                "stateMutability": "view",
                "type": "function"
            }
        ]
        
    async def initialize(self) -> bool:
        """Initialize the Web3 connection and contract interface."""
        try:
            if not self.rpc_url:
                logger.warning("BASE_RPC_URL not configured, NFT service will be disabled")
                return False
                
            if not self.contract_address:
                logger.warning("NFT_COLLECTION_ADDRESS_BASE not configured, NFT service will be disabled")
                return False
                
            # Initialize Web3
            self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))
            
            # Add PoA middleware for Base (if needed)
            self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)
            
            # Check connection
            if not self.w3.is_connected():
                logger.error("Failed to connect to Base RPC")
                return False
                
            # Initialize contract
            self.contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(self.contract_address),
                abi=self.contract_abi
            )
            
            # Initialize dev account if private key is provided
            if self.dev_wallet_private_key:
                self.dev_account = Account.from_key(self.dev_wallet_private_key)
                logger.info(f"Initialized dev wallet: {self.dev_account.address}")
            
            logger.info("Base NFT Service initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize Base NFT Service: {e}")
            return False
    
    async def upload_metadata(self, image_url: str, title: str, description: str, 
                            attributes: Optional[List[Dict[str, Any]]] = None) -> Optional[str]:
        """
        Upload NFT metadata to Arweave and return the URI.
        
        Args:
            image_url: URL to the image (typically S3)
            title: NFT title
            description: NFT description
            attributes: Optional list of trait attributes
            
        Returns:
            Arweave URI string or None if failed
        """
        try:
            if not settings.ARWEAVE_UPLOADER_API_ENDPOINT or not settings.ARWEAVE_UPLOADER_API_KEY:
                logger.error("Arweave uploader not configured")
                return None
            
            # Create NFT metadata following OpenSea standard
            metadata = {
                "name": title,
                "description": description,
                "image": image_url,
                "attributes": attributes or [],
                "created_by": self.collection_name,
                "created_at": int(time.time()),
                "external_url": settings.FRAMES_BASE_URL or ""
            }
            
            # Upload to Arweave
            headers = {
                "Authorization": f"Bearer {settings.ARWEAVE_UPLOADER_API_KEY}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "data": json.dumps(metadata),
                "content_type": "application/json",
                "tags": [
                    {"name": "Content-Type", "value": "application/json"},
                    {"name": "App-Name", "value": self.collection_name},
                    {"name": "NFT-Collection", "value": self.collection_symbol},
                    {"name": "Type", "value": "NFT-Metadata"}
                ]
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    settings.ARWEAVE_UPLOADER_API_ENDPOINT,
                    headers=headers,
                    json=payload
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        tx_id = result.get("tx_id")
                        if tx_id:
                            metadata_uri = f"{settings.ARWEAVE_GATEWAY_URL}/{tx_id}"
                            logger.info(f"Uploaded NFT metadata to Arweave: {metadata_uri}")
                            return metadata_uri
                    else:
                        logger.error(f"Failed to upload metadata to Arweave: {response.status}")
                        
        except Exception as e:
            logger.error(f"Error uploading NFT metadata: {e}")
            
        return None
    
    async def mint_nft(self, to_address: str, metadata_uri: str) -> Optional[Dict[str, Any]]:
        """
        Mint an NFT to the specified address.
        
        Args:
            to_address: Recipient wallet address
            metadata_uri: URI pointing to the NFT metadata
            
        Returns:
            Dict with transaction details or None if failed
        """
        try:
            if not self.w3 or not self.contract or not self.dev_account:
                logger.error("Base NFT Service not properly initialized")
                return None
            
            # Ensure address is checksummed
            to_address = Web3.to_checksum_address(to_address)
            
            # Build transaction
            nonce = self.w3.eth.get_transaction_count(self.dev_account.address)
            
            transaction = self.contract.functions.mint(
                to_address,
                metadata_uri
            ).build_transaction({
                'from': self.dev_account.address,
                'nonce': nonce,
                'gas': 200000,  # Adjust based on your contract
                'gasPrice': self.w3.eth.gas_price,
            })
            
            # Sign transaction
            signed_txn = self.w3.eth.account.sign_transaction(transaction, self.dev_wallet_private_key)
            
            # Send transaction
            tx_hash = self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
            
            # Wait for confirmation
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
            
            if receipt.status == 1:
                # Extract token ID from logs (assumes standard ERC-721 Transfer event)
                token_id = None
                for log in receipt.logs:
                    if len(log.topics) == 4:  # Transfer event has 4 topics
                        token_id = int.from_bytes(log.topics[3], byteorder='big')
                        break
                
                result = {
                    "transaction_hash": tx_hash.hex(),
                    "block_number": receipt.blockNumber,
                    "gas_used": receipt.gasUsed,
                    "token_id": token_id,
                    "contract_address": self.contract_address,
                    "recipient": to_address,
                    "metadata_uri": metadata_uri
                }
                
                logger.info(f"Successfully minted NFT: {result}")
                return result
            else:
                logger.error(f"NFT mint transaction failed: {tx_hash.hex()}")
                
        except Exception as e:
            logger.error(f"Error minting NFT: {e}")
            
        return None
    
    async def get_nft_balance(self, wallet_address: str) -> int:
        """
        Get the number of NFTs owned by an address from this collection.
        
        Args:
            wallet_address: Wallet address to check
            
        Returns:
            Number of NFTs owned
        """
        try:
            if not self.w3 or not self.contract:
                logger.error("Base NFT Service not properly initialized")
                return 0
            
            address = Web3.to_checksum_address(wallet_address)
            balance = self.contract.functions.balanceOf(address).call()
            return int(balance)
            
        except Exception as e:
            logger.error(f"Error getting NFT balance for {wallet_address}: {e}")
            return 0
    
    async def get_total_supply(self) -> int:
        """Get the total supply of NFTs in the collection."""
        try:
            if not self.w3 or not self.contract:
                return 0
            
            supply = self.contract.functions.totalSupply().call()
            return int(supply)
            
        except Exception as e:
            logger.error(f"Error getting total supply: {e}")
            return 0
    
    async def get_token_metadata(self, token_id: int) -> Optional[Dict[str, Any]]:
        """
        Get metadata for a specific token ID.
        
        Args:
            token_id: Token ID to query
            
        Returns:
            Metadata dict or None if not found
        """
        try:
            if not self.w3 or not self.contract:
                return None
            
            uri = self.contract.functions.tokenURI(token_id).call()
            
            # Fetch metadata from URI
            async with aiohttp.ClientSession() as session:
                async with session.get(uri) as response:
                    if response.status == 200:
                        metadata = await response.json()
                        return metadata
                        
        except Exception as e:
            logger.error(f"Error getting token metadata for {token_id}: {e}")
            
        return None
    
    def is_configured(self) -> bool:
        """Check if the service is properly configured."""
        return bool(
            self.rpc_url and 
            self.contract_address and 
            settings.ARWEAVE_UPLOADER_API_ENDPOINT and 
            settings.ARWEAVE_UPLOADER_API_KEY
        )
