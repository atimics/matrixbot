"""
Arweave Service - Secure, lean microservice for Arweave uploads
This service expects a pre-provisioned wallet file and does NOT generate wallets.
"""
import asyncio
import json
import logging
import os
from typing import Dict, List, Optional, Annotated

import uvicorn
from arweave import Wallet, Transaction
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Depends, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

class ArweaveWalletManager:
    """Manages the Arweave wallet for the service"""
    
    def __init__(self, wallet_file_path: str, gateway_url: str = "https://arweave.net"):
        self.wallet_file_path = wallet_file_path
        self.gateway_url = gateway_url
        self.wallet: Optional[Wallet] = None
        
    async def initialize(self):
        """Initialize the wallet by loading it from the specified path."""
        try:
            if not os.path.exists(self.wallet_file_path):
                logger.critical(f"FATAL: Wallet file not found at {self.wallet_file_path}. "
                               f"The service cannot start without a wallet. "
                               f"Please mount the wallet file correctly.")
                self.wallet = None
                return
                
            logger.debug(f"Loading wallet from {self.wallet_file_path}")
            self.wallet = Wallet(self.wallet_file_path)
            logger.debug(f"Wallet loaded successfully. Address: {self.wallet.address}")
            
            # Log wallet balance for operational visibility
            try:
                balance = await self.get_balance()
                logger.debug(f"Wallet balance: {balance} AR")
            except Exception as e:
                logger.warning(f"Could not fetch wallet balance: {e}")
                
        except Exception as e:
            logger.error(f"Failed to initialize ArweaveWalletManager: {e}", exc_info=True)
            self.wallet = None
            
    async def get_balance(self) -> float:
        """Get the wallet's AR balance"""
        if not self.wallet:
            raise HTTPException(status_code=503, detail="Wallet not initialized")
        
        try:
            # Use run_in_executor for the synchronous wallet.balance property
            loop = asyncio.get_event_loop()
            balance_winston = await loop.run_in_executor(None, lambda: self.wallet.balance)
            # Convert winston to AR (1 AR = 1e12 winston)
            return float(balance_winston) / 1e12
        except Exception as e:
            logger.error(f"Failed to get wallet balance: {e}")
            raise HTTPException(status_code=503, detail="Could not fetch wallet balance")
            
    def get_wallet_address(self) -> Optional[str]:
        """Get the wallet's public address"""
        return self.wallet.address if self.wallet else None
        
    def is_ready(self) -> bool:
        """Check if the wallet is ready for operations"""
        return self.wallet is not None

# Pydantic models for API requests/responses
class UploadResponse(BaseModel):
    transaction_id: str
    wallet_address: str
    data_size: int
    content_type: str
    upload_status: str
    arweave_url: str

class WalletInfo(BaseModel):
    address: str
    balance_ar: float
    status: str

class HealthResponse(BaseModel):
    status: str
    wallet_ready: bool
    wallet_address: Optional[str] = None

# Initialize the wallet manager
def get_wallet():
    """Factory function to get the wallet manager"""
    wallet_path = os.getenv("ARWEAVE_WALLET_PATH", "/data/arweave_wallet.json")
    return ArweaveWalletManager(wallet_path)

# Initialize FastAPI app
app = FastAPI(
    title="Arweave Service",
    description="Secure, lean microservice for Arweave uploads",
    version="1.0.0"
)

# Global wallet manager instance
wallet_manager = get_wallet()

# API Key for basic authentication
API_KEY = os.getenv("ARWEAVE_SERVICE_API_KEY")

def validate_api_key(x_api_key: Optional[str] = None):
    """Validate API key if one is configured"""
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")

@app.on_event("startup")
async def startup_event():
    """Initialize the wallet on startup"""
    await wallet_manager.initialize()
    if wallet_manager.is_ready():
        logger.info("Arweave service started successfully")
    else:
        logger.error("Arweave service started but wallet is not ready - service will be unhealthy")

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    wallet_ready = wallet_manager.is_ready()
    wallet_address = wallet_manager.get_wallet_address()
    
    return HealthResponse(
        status="healthy" if wallet_ready else "unhealthy",
        wallet_ready=wallet_ready,
        wallet_address=wallet_address
    )

@app.get("/wallet", response_model=WalletInfo)
async def get_wallet_info():
    """Get wallet information"""
    if not wallet_manager.is_ready():
        raise HTTPException(status_code=503, detail="Wallet not initialized")
    
    try:
        balance = await wallet_manager.get_balance()
        return WalletInfo(
            address=wallet_manager.get_wallet_address(),
            balance_ar=balance,
            status="ready"
        )
    except Exception as e:
        logger.error(f"Failed to get wallet info: {e}")
        raise HTTPException(status_code=503, detail="Could not fetch wallet information")

async def _parse_tags(tags: Optional[str]) -> Dict[str, str]:
    """Parse tags from JSON string format"""
    if not tags:
        return {}
    
    try:
        tag_dict = json.loads(tags)
        return {key: str(value) for key, value in tag_dict.items()}
    except json.JSONDecodeError:
        logger.warning(f"Invalid tags JSON provided: {tags}")
        return {}

async def _create_and_send_transaction(
    data: bytes, 
    content_type: str, 
    custom_tags: Dict[str, str],
    additional_tags: Optional[Dict[str, str]] = None
) -> Transaction:
    """
    Create, tag, sign and send an Arweave transaction
    
    Args:
        data: The data to upload
        content_type: Content type of the data
        custom_tags: Custom tags from user input
        additional_tags: Additional system tags (e.g., filename)
    
    Returns:
        The completed transaction
    """
    # Create transaction
    transaction = Transaction(wallet_manager.wallet, data=data)
    
    # Add content type tag
    transaction.add_tag('Content-Type', content_type)
    
    # Add additional system tags
    if additional_tags:
        for key, value in additional_tags.items():
            transaction.add_tag(key, value)
    
    # Add custom tags
    for key, value in custom_tags.items():
        transaction.add_tag(key, value)
    
    # Sign and send transaction
    transaction.sign()
    await asyncio.to_thread(transaction.send)
    
    return transaction

def _create_upload_response(
    transaction: Transaction, 
    data_size: int, 
    content_type: str
) -> UploadResponse:
    """Create a standardized upload response"""
    arweave_url = f"https://arweave.net/{transaction.id}"
    
    return UploadResponse(
        transaction_id=transaction.id,
        wallet_address=wallet_manager.get_wallet_address(),
        data_size=data_size,
        content_type=content_type,
        upload_status="submitted",
        arweave_url=arweave_url
    )

@app.post("/upload", response_model=UploadResponse)
async def upload_to_arweave(
    file: UploadFile = File(...),
    tags: Optional[str] = Form(None),
    x_api_key: Annotated[str | None, Header()] = None
):
    """
    Upload a file to Arweave
    
    Args:
        file: The file to upload
        tags: Optional JSON string of tags to add to the transaction
        x_api_key: Optional API key for authentication
    """
    # Validate API key if configured
    validate_api_key(x_api_key)
    
    if not wallet_manager.is_ready():
        raise HTTPException(status_code=503, detail="Wallet not initialized")
    
    try:
        # Read file content
        file_content = await file.read()
        if not file_content:
            raise HTTPException(status_code=400, detail="Empty file provided")
        
        logger.debug(f"Uploading file: {file.filename} ({len(file_content)} bytes)")
        
        # Parse custom tags
        custom_tags = await _parse_tags(tags)
        
        # Prepare additional system tags
        additional_tags = {}
        if file.filename:
            additional_tags['File-Name'] = file.filename
        
        # Create and send transaction
        transaction = await _create_and_send_transaction(
            data=file_content,
            content_type=file.content_type or "application/octet-stream",
            custom_tags=custom_tags,
            additional_tags=additional_tags
        )
        
        # Create response
        response = _create_upload_response(
            transaction=transaction,
            data_size=len(file_content),
            content_type=file.content_type or "application/octet-stream"
        )
        
        logger.debug(f"Upload successful: {transaction.id}")
        return response
        
    except Exception as e:
        logger.error(f"Upload failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@app.post("/upload/data", response_model=UploadResponse)
async def upload_data_to_arweave(
    data: str = Form(...),
    content_type: str = Form("text/plain"),
    tags: Optional[str] = Form(None),
    x_api_key: Annotated[str | None, Header()] = None
):
    """
    Upload raw data to Arweave
    
    Args:
        data: The data to upload as a string
        content_type: Content type of the data
        tags: Optional JSON string of tags to add to the transaction
        x_api_key: Optional API key for authentication
    """
    # Validate API key if configured
    validate_api_key(x_api_key)
    
    if not wallet_manager.is_ready():
        raise HTTPException(status_code=503, detail="Wallet not initialized")
    
    try:
        data_bytes = data.encode('utf-8')
        logger.debug(f"Uploading data ({len(data_bytes)} bytes)")
        
        # Parse custom tags
        custom_tags = await _parse_tags(tags)
        
        # Create and send transaction
        transaction = await _create_and_send_transaction(
            data=data_bytes,
            content_type=content_type,
            custom_tags=custom_tags
        )
        
        # Create response
        response = _create_upload_response(
            transaction=transaction,
            data_size=len(data_bytes),
            content_type=content_type
        )
        
        logger.debug(f"Data upload successful: {transaction.id}")
        return response
        
    except Exception as e:
        logger.error(f"Data upload failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Data upload failed: {str(e)}")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
