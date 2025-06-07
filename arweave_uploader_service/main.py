"""
Arweave Uploader Service - Microservice for handling direct Arweave uploads
"""
import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

import uvicorn
from arweave import Wallet, Arweave, Transaction
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
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
        self.arweave: Optional[Arweave] = None
        
    async def initialize(self):
        """Initialize the wallet and Arweave client"""
        try:
            await self._load_or_generate_wallet()
            if self.wallet:
                self.arweave = Arweave(self.gateway_url)
                logger.info("ArweaveWalletManager initialized successfully")
            else:
                logger.error("Failed to initialize wallet")
        except Exception as e:
            logger.error(f"Failed to initialize ArweaveWalletManager: {e}", exc_info=True)
            
    async def _load_or_generate_wallet(self):
        """Load existing wallet or generate a new one"""
        wallet_path = Path(self.wallet_file_path)
        
        try:
            if wallet_path.exists():
                # Load existing wallet
                logger.info(f"Loading existing wallet from {wallet_path}")
                with open(wallet_path, 'r') as f:
                    jwk_data = json.load(f)
                self.wallet = Wallet(jwk_data)
                logger.info(f"Wallet loaded successfully. Address: {self.wallet.address}")
            else:
                # Generate new wallet
                logger.info("No existing wallet found. Generating new wallet...")
                self.wallet = Wallet()
                
                # Ensure directory exists
                wallet_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Save wallet
                with open(wallet_path, 'w') as f:
                    json.dump(self.wallet.jwk_data, f, indent=2)
                
                # Set restrictive permissions
                try:
                    os.chmod(wallet_path, 0o600)
                except OSError as e:
                    logger.warning(f"Could not set restrictive permissions on wallet file: {e}")
                
                logger.info(f"New wallet generated and saved. Address: {self.wallet.address}")
                logger.info("*** IMPORTANT: Please fund this wallet with AR tokens to enable uploads ***")
                
        except Exception as e:
            logger.error(f"Error loading/generating wallet: {e}", exc_info=True)
            self.wallet = None
            
    def get_wallet_address(self) -> Optional[str]:
        """Get the wallet's public address"""
        return self.wallet.address if self.wallet else None
        
    async def get_wallet_balance(self) -> Optional[str]:
        """Get the wallet's current balance in Winston"""
        if not self.wallet or not self.arweave:
            return None
            
        try:
            loop = asyncio.get_event_loop()
            balance_winston = await loop.run_in_executor(None, self.wallet.get_balance)
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
        if not self.wallet or not self.arweave:
            logger.error("Wallet or Arweave client not initialized")
            return None
            
        try:
            # Create transaction
            transaction = Transaction(
                arweave_instance=self.arweave,
                data=data
            )
            
            # Add Content-Type tag
            transaction.add_tag('Content-Type', content_type)
            
            # Add custom tags
            if tags:
                for tag in tags:
                    transaction.add_tag(tag['name'], tag['value'])
                    
            # Sign transaction
            transaction.sign(self.wallet)
            
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
    tags: Optional[str] = Form(None)
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
async def get_wallet_info():
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
async def get_transaction_status(tx_id: str):
    """Get Arweave transaction status"""
    if not wallet_manager or not wallet_manager.arweave:
        raise HTTPException(
            status_code=503,
            detail="Arweave client not initialized"
        )
    
    try:
        loop = asyncio.get_event_loop()
        status = await loop.run_in_executor(
            None, 
            wallet_manager.arweave.transactions.get_status, 
            tx_id
        )
        
        return JSONResponse({
            "tx_id": tx_id,
            "status_code": status.status_code,
            "confirmed": status.status_code == 200,
            "data": status.json() if hasattr(status, 'json') else {}
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
