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
    separate arweave-service microservice.
    """
    
    def __init__(self, wallet_path: Optional[str] = None, gateway_url: str = "https://arweave.net"):
        self.wallet_path = wallet_path or self._get_default_wallet_path()
        self.gateway_url = gateway_url
        self.wallet = None
        self._initialized = False
        
        if not ARWEAVE_AVAILABLE:
            logger.warning("Arweave dependencies not installed. Service will be unavailable.")
    
    async def initialize(self) -> bool:
        """Initialize the Arweave service and load the wallet."""
        if not ARWEAVE_AVAILABLE:
            logger.error("Cannot initialize: Arweave dependencies not installed")
            return False
            
        try:
            if not os.path.exists(self.wallet_path):
                logger.error(f"Arweave wallet not found at {self.wallet_path}")
                return False
                
            logger.info(f"Loading Arweave wallet from {self.wallet_path}")
            # Only import and use Wallet if dependencies are available
            if ARWEAVE_AVAILABLE:
                self.wallet = Wallet(self.wallet_path)
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
        env_path = os.getenv("ARWEAVE_WALLET_PATH")
        if env_path:
            return env_path
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
        if self.wallet and hasattr(self.wallet, 'address'):
            return self.wallet.address
        return None
    
    def is_ready(self) -> bool:
        """Check if the service is ready for operations."""
        return self._initialized and self.wallet is not None and ARWEAVE_AVAILABLE
    
    async def upload_data(self, data: bytes, content_type: str = "application/octet-stream", 
                         tags: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Upload raw data to Arweave."""
        if not self.is_ready():
            raise RuntimeError("Arweave service not ready")
        
        if not ARWEAVE_AVAILABLE:
            raise RuntimeError("Arweave dependencies not available")
        
        try:
            # Create and configure transaction
            transaction = Transaction(self.wallet, data=data)
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
        """Upload a file to Arweave."""
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


def create_arweave_service(config: Optional[Dict[str, Any]] = None) -> ArweaveStorageService:
    """Factory function to create an Arweave storage service."""
    config = config or {}
    wallet_path = config.get("wallet_path")
    gateway_url = config.get("gateway_url", "https://arweave.net")
    return ArweaveStorageService(wallet_path=wallet_path, gateway_url=gateway_url)
