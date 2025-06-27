"""
Secure Farcaster Signer Service

This service provides a secure, isolated environment for signing Farcaster messages.
It manages private keys securely and exposes a minimal REST API for signing operations.
"""

import os
import logging
from contextlib import asynccontextmanager
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from key_manager import SecureKeyManager
from farcaster_signer import FarcasterSigner

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global instances
key_manager: Optional[SecureKeyManager] = None
farcaster_signer: Optional[FarcasterSigner] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage the lifecycle of the signer service."""
    global key_manager, farcaster_signer
    
    # Startup
    logger.info("Starting Farcaster Signer Service...")
    
    try:
        # Initialize key manager
        storage_path = os.getenv("SECURE_STORAGE_PATH", "/secure_storage")
        key_id = os.getenv("SIGNER_KEY_ID", "default")
        
        key_manager = SecureKeyManager(
            storage_path=storage_path,
            key_id=key_id,
            use_cloud_hsm=os.getenv("USE_CLOUD_HSM", "false").lower() == "true"
        )
        
        # Try to load existing key
        existing_key = key_manager.load_existing_key()
        
        if not existing_key:
            # No existing key found - check if we should auto-generate
            auto_generate = os.getenv("AUTO_GENERATE_KEY", "false").lower() == "true"
            default_fid = os.getenv("DEFAULT_FID")
            
            if auto_generate and default_fid:
                logger.info(f"Auto-generating new signer key for FID {default_fid}")
                key_info = key_manager.generate_new_key(int(default_fid))
                logger.warning("=" * 80)
                logger.warning("NEW SIGNER KEY GENERATED!")
                logger.warning(f"Public Key: {key_info['public_key_hex']}")
                logger.warning("You MUST register this public key on-chain using your account's Owner Key")
                logger.warning("=" * 80)
            else:
                logger.warning("No existing signer key found and auto-generation disabled")
                logger.warning("Service will start but signing operations will fail")
        else:
            logger.info(f"Loaded existing signer key for FID {existing_key['fid']}")
        
        # Initialize Farcaster signer
        farcaster_signer = FarcasterSigner(key_manager)
        
        logger.info("Farcaster Signer Service started successfully")
        
    except Exception as e:
        logger.error(f"Failed to start Farcaster Signer Service: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down Farcaster Signer Service...")
    if key_manager:
        key_manager.clear_memory()
    logger.info("Shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="Farcaster Signer Service",
    description="Secure, isolated service for signing Farcaster messages",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware (restrict in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://farcaster_api_service:8001"],  # Only allow internal services
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# Pydantic models for request/response validation
class CastSigningRequest(BaseModel):
    """Request model for signing a cast."""
    text: str = Field(..., max_length=320, description="Cast text content")
    parent_cast_id: Optional[Dict[str, Any]] = Field(None, description="Parent cast for replies")
    parent_url: Optional[str] = Field(None, description="Parent URL for URL replies")
    embeds: Optional[List[Dict[str, Any]]] = Field(None, description="List of embeds")
    mentions: Optional[List[int]] = Field(None, description="List of mentioned FIDs")
    mentions_positions: Optional[List[int]] = Field(None, description="Positions of mentions in text")


class ReactionSigningRequest(BaseModel):
    """Request model for signing a reaction."""
    target_cast_hash: str = Field(..., description="Hash of the target cast")
    target_cast_fid: int = Field(..., description="FID of the target cast author")
    reaction_type: int = Field(1, description="Reaction type (1=like, 2=recast)")


class SigningResponse(BaseModel):
    """Response model for signing operations."""
    success: bool
    signed_message_bytes: Optional[str] = Field(None, description="Hex-encoded signed message bytes")
    message_hash: Optional[str] = Field(None, description="Hex-encoded message hash")
    error: Optional[str] = None


class KeyGenerationRequest(BaseModel):
    """Request model for generating a new key."""
    fid: int = Field(..., description="Farcaster ID to associate with the key")
    force: bool = Field(False, description="Force generation even if key exists")


class SignerStatusResponse(BaseModel):
    """Response model for signer status."""
    is_ready: bool
    fid: Optional[int] = None
    public_key_hex: Optional[str] = None
    key_loaded: bool = False
    protobuf_available: bool = False


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "farcaster-signer",
        "key_loaded": key_manager.is_key_loaded() if key_manager else False
    }


# Signer status endpoint
@app.get("/v1/status", response_model=SignerStatusResponse)
async def get_signer_status():
    """Get the current status of the signer."""
    if not key_manager or not farcaster_signer:
        return SignerStatusResponse(
            is_ready=False,
            key_loaded=False,
            protobuf_available=False
        )
    
    signer_info = farcaster_signer.get_signer_info()
    
    return SignerStatusResponse(
        is_ready=key_manager.is_key_loaded(),
        fid=signer_info["fid"],
        public_key_hex=signer_info["public_key_hex"],
        key_loaded=signer_info["is_key_loaded"],
        protobuf_available=signer_info["protobuf_available"]
    )


# Key generation endpoint (admin only)
@app.post("/v1/admin/generate-key")
async def generate_new_key(request: KeyGenerationRequest):
    """
    Generate a new signer key (admin endpoint).
    
    WARNING: This will overwrite existing keys if force=True.
    """
    if not key_manager:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Key manager not initialized"
        )
    
    # Check if key already exists
    if key_manager.is_key_loaded() and not request.force:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Signer key already exists. Use force=true to overwrite."
        )
    
    try:
        key_info = key_manager.generate_new_key(request.fid)
        
        # Reinitialize the signer with new key
        global farcaster_signer
        farcaster_signer = FarcasterSigner(key_manager)
        
        return {
            "success": True,
            "key_info": key_info,
            "warning": "You MUST register this public key on-chain using your account's Owner Key"
        }
        
    except Exception as e:
        logger.error(f"Failed to generate new key: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate new key: {str(e)}"
        )


# Cast signing endpoint
@app.post("/v1/sign-cast", response_model=SigningResponse)
async def sign_cast(request: CastSigningRequest):
    """
    Sign a cast message.
    
    This is the primary endpoint used by the farcaster-api-service
    to sign cast messages before submitting them to the Snapchain node.
    """
    if not key_manager or not farcaster_signer:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Signer service not initialized"
        )
    
    if not key_manager.is_key_loaded():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No signing key loaded"
        )
    
    try:
        # Convert parent_cast_id if provided
        parent_cast_id = None
        if request.parent_cast_id:
            parent_cast_id = {
                "fid": request.parent_cast_id.get("fid"),
                "hash": bytes.fromhex(request.parent_cast_id.get("hash", "").replace("0x", ""))
            }
        
        # Create and sign the message
        signed_message_bytes = farcaster_signer.create_cast_add_message(
            text=request.text,
            parent_cast_id=parent_cast_id,
            parent_url=request.parent_url,
            embeds=request.embeds,
            mentions=request.mentions,
            mentions_positions=request.mentions_positions
        )
        
        # Compute message hash for reference
        message_hash = farcaster_signer._compute_message_hash(signed_message_bytes)
        
        logger.info(f"Successfully signed cast message: {message_hash.hex()}")
        
        return SigningResponse(
            success=True,
            signed_message_bytes=signed_message_bytes.hex(),
            message_hash=message_hash.hex()
        )
        
    except Exception as e:
        logger.error(f"Failed to sign cast: {e}")
        return SigningResponse(
            success=False,
            error=str(e)
        )


# Reaction signing endpoint
@app.post("/v1/sign-reaction", response_model=SigningResponse)
async def sign_reaction(request: ReactionSigningRequest):
    """
    Sign a reaction message.
    """
    if not key_manager or not farcaster_signer:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Signer service not initialized"
        )
    
    if not key_manager.is_key_loaded():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No signing key loaded"
        )
    
    try:
        # Prepare target cast ID
        target_cast_id = {
            "fid": request.target_cast_fid,
            "hash": bytes.fromhex(request.target_cast_hash.replace("0x", ""))
        }
        
        # Create and sign the reaction
        signed_message_bytes = farcaster_signer.create_reaction_add_message(
            target_cast_id=target_cast_id,
            reaction_type=request.reaction_type
        )
        
        # Compute message hash for reference
        message_hash = farcaster_signer._compute_message_hash(signed_message_bytes)
        
        logger.info(f"Successfully signed reaction message: {message_hash.hex()}")
        
        return SigningResponse(
            success=True,
            signed_message_bytes=signed_message_bytes.hex(),
            message_hash=message_hash.hex()
        )
        
    except Exception as e:
        logger.error(f"Failed to sign reaction: {e}")
        return SigningResponse(
            success=False,
            error=str(e)
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
