"""
Arweave Storage Integration

Consolidated Arweave service that replaces the separate arweave-service microservice.
This integration provides secure upload and retrieval capabilities for permanent storage.
"""

import asyncio
import logging
import os
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)

# Handle optional arweave dependency
try:
    from arweave import Wallet, Transaction
    ARWEAVE_AVAILABLE = True
except ImportError:
    ARWEAVE_AVAILABLE = False
    logger.warning("Arweave dependencies not available. Install with: pip install arweave-python-client")


class ArweaveStorageService:
    """
    Unified Arweave storage service for permanent data archival.
    
    This service consolidates the functionality previously provided by the
    separate arweave-service microservice, providing:
    - File and data uploads to Arweave
    - Wallet management and balance tracking
    - Transaction status monitoring
    - Integration with the main chatbot's ServiceRegistry
    """
    
    def __init__(self, wallet_path: Optional[str] = None, gateway_url: str = "https://arweave.net"):
        self.wallet_path = wallet_path or self._get_default_wallet_path()
        self.gateway_url = gateway_url
        self.wallet = None
        self._initialized = False
        
        if not ARWEAVE_AVAILABLE:
            logger.warning("Arweave dependencies not installed. Arweave storage will be unavailable.")
    
    async def initialize(self) -> bool:
        """Initialize the Arweave service and load the wallet."""
        if not ARWEAVE_AVAILABLE:
            logger.error("Cannot initialize Arweave service: dependencies not installed")
            return False
            
        try:
            if not os.path.exists(self.wallet_path):
                logger.error(f"Arweave wallet not found at {self.wallet_path}")
                return False
                
            logger.info(f"Loading Arweave wallet from {self.wallet_path}")
            self.wallet = Wallet(self.wallet_path)
            
            # Verify wallet is functional
            address = self.wallet.address
            logger.info(f"Arweave wallet loaded successfully. Address: {address}")
            
            # Log balance for operational visibility
            try:
                balance = await self.get_balance()
                logger.info(f"Arweave wallet balance: {balance} AR")
            except Exception as e:
                logger.warning(f"Could not fetch wallet balance: {e}")
                
            self._initialized = True
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize Arweave service: {e}")
            return False
    
    def _get_default_wallet_path(self) -> str:
        """Get the default wallet path from environment or standard location."""
        # Check environment variable first
        env_path = os.getenv("ARWEAVE_WALLET_PATH")
        if env_path:
            return env_path
            
        # Fall back to standard data directory
        return "data/arweave_wallet.json"
    
    async def get_balance(self) -> float:
        """Get the wallet's AR balance."""
        if not self.is_ready():
            raise RuntimeError("Arweave wallet not initialized")
        
        try:
            # Use run_in_executor for the synchronous wallet.balance property
            loop = asyncio.get_event_loop()
            balance_winston = await loop.run_in_executor(None, lambda: self.wallet.balance)
            # Convert winston to AR (1 AR = 1e12 winston)
            return float(balance_winston) / 1e12
        except Exception as e:
            logger.error(f"Failed to get wallet balance: {e}")
            raise
    
    def get_wallet_address(self) -> Optional[str]:
        """Get the wallet's public address."""
        return self.wallet.address if self.wallet else None
    
    def is_ready(self) -> bool:
        """Check if the service is ready for operations."""
        return self._initialized and self.wallet is not None and ARWEAVE_AVAILABLE
    
    async def upload_data(self, data: bytes, content_type: str = "application/octet-stream", 
                         tags: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Upload raw data to Arweave.
        
        Args:
            data: Raw bytes to upload
            content_type: MIME type of the data
            tags: Optional metadata tags for the transaction
            
        Returns:
            Dictionary with upload result information
        """
        if not self.is_ready():
            raise RuntimeError("Arweave service not ready")
        
        try:
            # Create transaction
            transaction = Transaction(self.wallet, data=data)
            
            # Add content type tag
            transaction.add_tag('Content-Type', content_type)
            
            # Add custom tags if provided
            if tags:
                for key, value in tags.items():
                    transaction.add_tag(key, value)
            
            # Sign and send transaction
            transaction.sign()
            transaction.send()
            
            result = {
                "transaction_id": transaction.id,
                "wallet_address": self.wallet.address,
                "data_size": len(data),
                "content_type": content_type,
                "upload_status": "pending",
                "arweave_url": f"{self.gateway_url}/{transaction.id}",
                "tags": tags or {}
            }
            
            logger.info(f"Uploaded {len(data)} bytes to Arweave: {transaction.id}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to upload data to Arweave: {e}")
            raise
    
    async def upload_file(self, file_path: str, content_type: Optional[str] = None,
                         tags: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Upload a file to Arweave.
        
        Args:
            file_path: Path to the file to upload
            content_type: MIME type (auto-detected if not provided)
            tags: Optional metadata tags
            
        Returns:
            Dictionary with upload result information
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        # Auto-detect content type if not provided
        if not content_type:
            import mimetypes
            content_type, _ = mimetypes.guess_type(file_path)
            content_type = content_type or "application/octet-stream"
        
        # Read file data
        with open(file_path, 'rb') as f:
            data = f.read()
        
        # Add filename tag
        if not tags:
            tags = {}
        tags['Filename'] = os.path.basename(file_path)
        
        return await self.upload_data(data, content_type, tags)
    
    async def get_transaction_status(self, transaction_id: str) -> Dict[str, Any]:
        """
        Get the status of an Arweave transaction.
        
        Args:
            transaction_id: The transaction ID to check
            
        Returns:
            Dictionary with transaction status information
        """
        try:
            import aiohttp
            
            async with aiohttp.ClientSession() as session:
                # Check transaction status
                status_url = f"{self.gateway_url}/tx/{transaction_id}/status"
                async with session.get(status_url) as response:
                    if response.status == 200:
                        status_data = await response.json()
                        return {
                            "transaction_id": transaction_id,
                            "status": "confirmed",
                            "block_height": status_data.get("block_height"),
                            "block_indep_hash": status_data.get("block_indep_hash"),
                            "number_of_confirmations": status_data.get("number_of_confirmations")
                        }
                    elif response.status == 202:
                        return {
                            "transaction_id": transaction_id,
                            "status": "pending"
                        }
                    else:
                        return {
                            "transaction_id": transaction_id,
                            "status": "not_found"
                        }
                        
        except Exception as e:
            logger.error(f"Failed to get transaction status: {e}")
            return {
                "transaction_id": transaction_id,
                "status": "error",
                "error": str(e)
            }
    
    async def get_service_status(self) -> Dict[str, Any]:
        """Get comprehensive service status."""
        status = {
            "service": "arweave_storage",
            "available": ARWEAVE_AVAILABLE,
            "initialized": self._initialized,
            "wallet_ready": self.is_ready(),
            "wallet_address": self.get_wallet_address(),
            "gateway_url": self.gateway_url
        }
        
        if self.is_ready():
            try:
                status["balance_ar"] = await self.get_balance()
            except Exception as e:
                status["balance_error"] = str(e)
        
        return status


# Factory function for service registration
def create_arweave_service(config: Optional[Dict[str, Any]] = None) -> ArweaveStorageService:
    """
    Factory function to create an Arweave storage service.
    
    Args:
        config: Optional configuration dictionary
        
    Returns:
        Configured ArweaveStorageService instance
    """
    config = config or {}
    
    wallet_path = config.get("wallet_path")
    gateway_url = config.get("gateway_url", "https://arweave.net")
    
    return ArweaveStorageService(wallet_path=wallet_path, gateway_url=gateway_url)
