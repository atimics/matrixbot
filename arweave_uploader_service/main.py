"""
Arweave Uploader Service - Microservice for handling direct Arweave uploads
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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

class ArweaveWalletManager:
    """Manages the Arweave wallet for the uploader service"""
    
    def __init__(self, wallet_file_path: str, gateway_url: str = "https://arweave.net"):
        self.wallet_file_path = wallet_file_path
        self.gateway_url = gateway_url
        self.wallet: Optional[Wallet] = None
        
    async def initialize(self):
        """Initialize the wallet by loading it from the guaranteed path."""
        try:
            # The entrypoint script guarantees this file exists.
            logger.info(f"Loading wallet from {self.wallet_file_path}")
            self.wallet = Wallet(self.wallet_file_path)
            logger.info(f"Wallet loaded successfully. Address: {self.wallet.address}")
        except FileNotFoundError:
            logger.error(f"CRITICAL: Wallet file not found at {self.wallet_file_path}. The entrypoint script should have created it.")
            # The service will fail health checks if the wallet is not initialized.
            self.wallet = None
        except Exception as e:
            logger.error(f"Failed to initialize ArweaveWalletManager: {e}", exc_info=True)
            self.wallet = None
            

            
    def get_wallet_address(self) -> Optional[str]:
        """Get the wallet's public address"""
        return self.wallet.address if self.wallet else None
        
    async def get_wallet_balance(self) -> Optional[str]:
        """Get the wallet's current balance in Winston"""
        if not self.wallet:
            return None
            
        try:
            loop = asyncio.get_event_loop()
            balance_winston = await loop.run_in_executor(None, lambda: self.wallet.balance)
            return str(balance_winston)
        except Exception as e:
            logger.error(f"Failed to get wallet balance: {e}")
            return None
            
    async def upload_data(
        self,
        data: bytes,
        content_type: str,
        tags: Optional[List[Dict[str, str]]] = None
    ) -> Optional[str]:
        """Upload data to Arweave and return transaction ID"""
        if not self.wallet:
            logger.error("Wallet not initialized")
            return None
            
        try:
            # Create transaction
            transaction = Transaction(
                wallet=self.wallet,
                data=data
            )
            
            # Add Content-Type tag
            transaction.add_tag('Content-Type', content_type)
            
            # Add custom tags
            if tags:
                for tag in tags:
                    transaction.add_tag(tag['name'], tag['value'])
                    
            # Sign transaction
            transaction.sign()
            
            # Send transaction (run in thread pool to avoid blocking)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, transaction.send)
            
            if transaction.id:
                logger.info(f"Data uploaded to Arweave. TX ID: {transaction.id}")
                return transaction.id
            else:
                logger.error("Transaction sent but no ID received")
                return None
                
        except Exception as e:
            logger.error(f"Failed to upload data to Arweave: {e}", exc_info=True)
            return None


# Initialize FastAPI app
app = FastAPI(
    title="Arweave Uploader Service",
    description="Microservice for uploading data to Arweave",
    version="1.0.0"
)

# Global wallet manager
wallet_manager: Optional[ArweaveWalletManager] = None

# Optional API key for internal service authentication
API_KEY = os.getenv("ARWEAVE_UPLOADER_API_KEY")


def verify_api_key(x_api_key: Annotated[str | None, Header()] = None):
    """Verify API key if configured."""
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key"
        )
    return True

@app.on_event("startup")
async def startup_event():
    """Initialize the wallet manager on startup"""
    global wallet_manager
    
    # Get configuration from environment variables
    wallet_file_path = os.getenv("ARWEAVE_WALLET_FILE_PATH", "/data/arweave_wallet.json")
    gateway_url = os.getenv("ARWEAVE_GATEWAY_URL", "https://arweave.net")
    
    logger.info(f"Starting Arweave Uploader Service")
    logger.info(f"Wallet file path: {wallet_file_path}")
    logger.info(f"Gateway URL: {gateway_url}")
    
    wallet_manager = ArweaveWalletManager(wallet_file_path, gateway_url)
    await wallet_manager.initialize()

@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    content_type: str = Form(...),
    tags: Optional[str] = Form(None),
    _: bool = Depends(verify_api_key)
):
    """Upload a file to Arweave"""
    if not wallet_manager or not wallet_manager.wallet:
        raise HTTPException(
            status_code=503, 
            detail="Arweave wallet not initialized. Check server logs."
        )
    
    try:
        # Read file data
        file_data = await file.read()
        
        # Parse tags if provided
        parsed_tags = None
        if tags:
            try:
                parsed_tags = json.loads(tags)
                if not isinstance(parsed_tags, list):
                    raise ValueError("Tags must be a list")
            except (json.JSONDecodeError, ValueError) as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid tags format. Expected JSON list: {str(e)}"
                )
        
        # Upload to Arweave
        tx_id = await wallet_manager.upload_data(file_data, content_type, parsed_tags)
        
        if tx_id:
            arweave_url = f"{wallet_manager.gateway_url}/{tx_id}"
            return JSONResponse({
                "status": "success",
                "tx_id": tx_id,
                "arweave_url": arweave_url
            })
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to upload to Arweave. Check server logs."
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload endpoint error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )

@app.get("/wallet-info")
async def get_wallet_info(_: bool = Depends(verify_api_key)):
    """Get wallet information"""
    if not wallet_manager:
        raise HTTPException(
            status_code=503,
            detail="Wallet manager not initialized"
        )
    
    address = wallet_manager.get_wallet_address()
    if not address:
        raise HTTPException(
            status_code=503,
            detail="Arweave wallet not properly initialized"
        )
    
    try:
        balance_winston = await wallet_manager.get_wallet_balance()
        balance_ar = "N/A"
        
        if balance_winston is not None:
            try:
                balance_ar_float = int(balance_winston) / (10**12)
                balance_ar = f"{balance_ar_float:.6f} AR"
            except ValueError:
                balance_ar = "Error parsing balance"
        
        return JSONResponse({
            "address": address,
            "balance_winston": balance_winston,
            "balance_ar": balance_ar,
            "gateway_url": wallet_manager.gateway_url,
            "funding_instructions": "Please send AR tokens to this address to enable data uploads to Arweave."
        })
        
    except Exception as e:
        logger.error(f"Error getting wallet info: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get wallet info: {str(e)}"
        )

@app.get("/status/{tx_id}")
async def get_transaction_status(tx_id: str, _: bool = Depends(verify_api_key)):
    """Get Arweave transaction status"""
    if not wallet_manager or not wallet_manager.wallet:
        raise HTTPException(
            status_code=503,
            detail="Arweave wallet not initialized"
        )
    
    try:
        # Use the Arweave Python library to check transaction status
        arweave = Arweave()
        
        loop = asyncio.get_event_loop()
        status = await loop.run_in_executor(
            None, 
            arweave.transactions.get_status, 
            tx_id
        )
        
        return JSONResponse({
            "tx_id": tx_id,
            "status_code": status.status_code,
            "confirmed": status.status_code == 200,
            "block_height": getattr(status, 'block_height', None),
            "block_indep_hash": getattr(status, 'block_indep_hash', None)
        })
        
    except Exception as e:
        logger.error(f"Error getting transaction status: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get transaction status: {str(e)}"
        )

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    wallet_initialized = wallet_manager is not None and wallet_manager.wallet is not None
    return JSONResponse({
        "status": "healthy" if wallet_initialized else "degraded",
        "wallet_initialized": wallet_initialized,
        "service": "arweave-uploader"
    })

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,
        log_level="info"
    )
