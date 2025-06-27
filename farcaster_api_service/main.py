"""
In-House Farcaster API Service

This service provides a REST API wrapper around a Snapchain node,
offering a clean HTTP interface for Farcaster operations.
Integrates with the signer service for secure message signing.
"""

import logging
import asyncio
import aiohttp
import base64
from contextlib import asynccontextmanager
from typing import Dict, Any, List, Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException, Query, Path
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import os

from snapchain_client import SnapchainClient

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SignerServiceClient:
    """Client for communicating with the signer service."""
    
    def __init__(self, signer_url: str):
        self.signer_url = signer_url.rstrip('/')
        self.session = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def _make_request(self, method: str, endpoint: str, data: Optional[dict] = None) -> dict:
        """Make a request to the signer service."""
        if not self.session:
            self.session = aiohttp.ClientSession()
        
        url = f"{self.signer_url}{endpoint}"
        
        try:
            async with self.session.request(method, url, json=data) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    raise HTTPException(
                        status_code=response.status,
                        detail=f"Signer service error: {error_text}"
                    )
        except aiohttp.ClientError as e:
            raise HTTPException(
                status_code=503,
                detail=f"Cannot connect to signer service: {str(e)}"
            )
    
    async def get_status(self) -> dict:
        """Get signer service status."""
        return await self._make_request("GET", "/v1/status")
    
    async def sign_cast(self, cast_data: dict) -> dict:
        """Sign a cast message."""
        return await self._make_request("POST", "/v1/sign-cast", cast_data)
    
    async def sign_reaction(self, reaction_data: dict) -> dict:
        """Sign a reaction message."""
        return await self._make_request("POST", "/v1/sign-reaction", reaction_data)

# Global clients
snapchain_client = None
signer_client = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage the lifecycle of the snapchain and signer client connections."""
    global snapchain_client, signer_client
    
    # Startup
    snapchain_host = os.getenv("SNAPCHAIN_GRPC_HOST", "snapchain")
    snapchain_port = int(os.getenv("SNAPCHAIN_GRPC_PORT", "3383"))
    signer_url = os.getenv("SIGNER_SERVICE_URL", "http://signer_service:8000")
    
    snapchain_client = SnapchainClient(host=snapchain_host, port=snapchain_port)
    signer_client = SignerServiceClient(signer_url)
    
    try:
        await snapchain_client.connect()
        logger.info("Snapchain client connected successfully")
    except Exception as e:
        logger.error(f"Failed to connect to Snapchain: {e}")
        # Don't fail startup - we'll handle connection errors per request
    
    try:
        # Test signer service connection
        async with signer_client:
            status = await signer_client.get_status()
            logger.info(f"Signer service status: {status}")
    except Exception as e:
        logger.error(f"Failed to connect to signer service: {e}")
        # Don't fail startup - we'll handle connection errors per request
    
    yield
    
    # Shutdown
    if snapchain_client:
        await snapchain_client.disconnect()
    if signer_client and signer_client.session:
        await signer_client.session.close()

# Create FastAPI app
app = FastAPI(
    title="RatiChat Farcaster API",
    description="In-house REST API for Farcaster interactions via Snapchain",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models for request/response validation
class CastResponse(BaseModel):
    """Response model for cast data."""
    hash: Optional[str] = None
    thread_hash: Optional[str] = None
    parent_hash: Optional[str] = None
    parent_author: Optional[Dict[str, Any]] = None
    author: Dict[str, Any]
    text: str
    timestamp: str
    embeds: List[Dict[str, str]] = []
    mentions: List[int] = []
    mentions_positions: List[int] = []
    replies: Dict[str, int] = Field(default_factory=lambda: {"count": 0})
    reactions: Dict[str, int] = Field(default_factory=lambda: {"likes_count": 0, "recasts_count": 0})

class UserResponse(BaseModel):
    """Response model for user data."""
    fid: int
    username: Optional[str] = None
    display_name: Optional[str] = None
    bio: Optional[str] = None
    pfp_url: Optional[str] = None

class NodeInfoResponse(BaseModel):
    """Response model for node information."""
    version: str
    is_syncing: bool
    nickname: Optional[str] = None
    root_hash: Optional[str] = None
    db_stats: Optional[Dict[str, int]] = None

class SubmitMessageRequest(BaseModel):
    """Request model for submitting messages."""
    message_data: str = Field(..., description="Base64 encoded message bytes")

class SubmitMessageResponse(BaseModel):
    """Response model for message submission."""
    success: bool
    hash: Optional[str] = None
    message: str
    error: Optional[str] = None
    code: Optional[str] = None

# New models for cast posting
class PostCastRequest(BaseModel):
    """Request model for posting a cast."""
    text: str = Field(..., max_length=320, description="Cast text content")
    parent_cast_hash: Optional[str] = Field(None, description="Hash of parent cast for replies")
    parent_cast_fid: Optional[int] = Field(None, description="FID of parent cast author for replies")
    parent_url: Optional[str] = Field(None, description="Parent URL for URL replies")
    embeds: Optional[List[Dict[str, Any]]] = Field(None, description="List of embeds")
    mentions: Optional[List[int]] = Field(None, description="List of mentioned FIDs")
    mentions_positions: Optional[List[int]] = Field(None, description="Positions of mentions in text")

class PostCastResponse(BaseModel):
    """Response model for cast posting."""
    success: bool
    hash: Optional[str] = None
    message: str
    error: Optional[str] = None

class PostReactionRequest(BaseModel):
    """Request model for posting a reaction."""
    target_cast_hash: str = Field(..., description="Hash of the target cast")
    target_cast_fid: int = Field(..., description="FID of the target cast author")
    reaction_type: int = Field(1, description="Reaction type (1=like, 2=recast)")

class PostReactionResponse(BaseModel):
    """Response model for reaction posting."""
    success: bool
    hash: Optional[str] = None
    message: str
    error: Optional[str] = None

class SignerStatusResponse(BaseModel):
    """Response model for signer status."""
    is_ready: bool
    fid: Optional[int] = None
    public_key_hex: Optional[str] = None
    key_loaded: bool = False

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    try:
        if snapchain_client:
            info = await snapchain_client.get_info()
            return {
                "status": "healthy",
                "timestamp": datetime.utcnow().isoformat(),
                "snapchain_connected": True,
                "snapchain_syncing": info.get("is_syncing", True)
            }
        else:
            return {
                "status": "degraded",
                "timestamp": datetime.utcnow().isoformat(),
                "snapchain_connected": False
            }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(e)
        }

# Node information endpoint
@app.get("/v1/info", response_model=NodeInfoResponse)
async def get_node_info():
    """Get information about the Snapchain node."""
    if not snapchain_client:
        raise HTTPException(status_code=503, detail="Snapchain client not available")
    
    try:
        info = await snapchain_client.get_info()
        return NodeInfoResponse(**info)
    except Exception as e:
        logger.error(f"Error getting node info: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get node info: {str(e)}")

# Cast endpoints
@app.get("/v1/cast/{cast_hash}", response_model=CastResponse)
async def get_cast(
    cast_hash: str = Path(..., description="The cast hash (with or without 0x prefix)")
):
    """Get a cast by its hash."""
    if not snapchain_client:
        raise HTTPException(status_code=503, detail="Snapchain client not available")
    
    try:
        cast_data = await snapchain_client.get_cast_by_hash(cast_hash)
        if not cast_data:
            raise HTTPException(status_code=404, detail="Cast not found")
        
        return CastResponse(**cast_data)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching cast {cast_hash}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch cast: {str(e)}")

@app.get("/v1/casts", response_model=List[CastResponse])
async def get_casts_by_fid(
    fid: int = Query(..., description="The Farcaster ID"),
    limit: int = Query(25, description="Maximum number of casts to return", le=100),
    reverse: bool = Query(True, description="Whether to return newest first")
):
    """Get casts by a user's FID."""
    if not snapchain_client:
        raise HTTPException(status_code=503, detail="Snapchain client not available")
    
    try:
        casts = await snapchain_client.get_casts_by_fid(fid, limit, reverse)
        return [CastResponse(**cast) for cast in casts]
    except Exception as e:
        logger.error(f"Error fetching casts for FID {fid}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch casts: {str(e)}")

# User endpoints
@app.get("/v1/user/{fid}", response_model=UserResponse)
async def get_user_by_fid(
    fid: int = Path(..., description="The Farcaster ID")
):
    """Get user information by FID."""
    if not snapchain_client:
        raise HTTPException(status_code=503, detail="Snapchain client not available")
    
    try:
        user_data = await snapchain_client.get_user_by_fid(fid)
        if not user_data:
            raise HTTPException(status_code=404, detail="User not found")
        
        return UserResponse(**user_data)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching user {fid}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch user: {str(e)}")

# Message submission endpoint
@app.post("/v1/submit-message", response_model=SubmitMessageResponse)
async def submit_message(request: SubmitMessageRequest):
    """Submit a message to the Farcaster network."""
    if not snapchain_client:
        raise HTTPException(status_code=503, detail="Snapchain client not available")
    
    try:
        import base64
        message_bytes = base64.b64decode(request.message_data)
        result = await snapchain_client.submit_message(message_bytes)
        return SubmitMessageResponse(**result)
    except Exception as e:
        logger.error(f"Error submitting message: {e}")
        result = {
            "success": False,
            "message": "Failed to submit message",
            "error": str(e)
        }
        return SubmitMessageResponse(**result)

# Compatibility endpoints that match Neynar-style API
@app.get("/v2/farcaster/cast")
async def get_cast_neynar_style(
    hash: str = Query(..., description="The cast hash"),
    type: str = Query("hash", description="The identifier type")
):
    """Get cast information (Neynar-compatible endpoint)."""
    if type != "hash":
        raise HTTPException(status_code=400, detail="Only hash type is supported")
    
    # Redirect to our internal endpoint
    cast_data = await get_cast(hash)
    
    # Wrap in Neynar-style response
    return {
        "cast": cast_data.dict()
    }

@app.get("/v2/farcaster/user/bulk")
async def get_users_bulk(
    fids: str = Query(..., description="Comma-separated list of FIDs")
):
    """Get multiple users by FIDs (Neynar-compatible endpoint)."""
    if not snapchain_client:
        raise HTTPException(status_code=503, detail="Snapchain client not available")
    
    try:
        fid_list = [int(fid.strip()) for fid in fids.split(",")]
        users = []
        
        for fid in fid_list:
            try:
                user_data = await snapchain_client.get_user_by_fid(fid)
                if user_data:
                    users.append(UserResponse(**user_data).dict())
            except Exception as e:
                logger.warning(f"Failed to fetch user {fid}: {e}")
                continue
        
        return {"users": users}
    except Exception as e:
        logger.error(f"Error fetching users bulk: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch users: {str(e)}")

# New endpoints for cast posting and reactions

@app.get("/v1/signer/status", response_model=SignerStatusResponse)
async def get_signer_status():
    """Get the status of the signer service."""
    if not signer_client:
        raise HTTPException(status_code=503, detail="Signer client not available")
    
    try:
        async with signer_client:
            status = await signer_client.get_status()
            return SignerStatusResponse(**status)
    except Exception as e:
        logger.error(f"Error getting signer status: {e}")
        raise HTTPException(status_code=503, detail=f"Signer service unavailable: {str(e)}")

@app.post("/v1/cast", response_model=PostCastResponse)
async def post_cast(request: PostCastRequest):
    """
    Post a cast to Farcaster.
    
    This endpoint:
    1. Sends the cast data to the signer service for signing
    2. Submits the signed message to the Snapchain node
    3. Returns the result
    """
    if not signer_client:
        raise HTTPException(status_code=503, detail="Signer client not available")
    
    if not snapchain_client:
        raise HTTPException(status_code=503, detail="Snapchain client not available")
    
    try:
        # Prepare signing request
        signing_request = {
            "text": request.text,
            "embeds": request.embeds,
            "mentions": request.mentions,
            "mentions_positions": request.mentions_positions
        }
        
        # Add parent information if this is a reply
        if request.parent_cast_hash and request.parent_cast_fid:
            signing_request["parent_cast_id"] = {
                "fid": request.parent_cast_fid,
                "hash": request.parent_cast_hash.replace("0x", "")
            }
        elif request.parent_url:
            signing_request["parent_url"] = request.parent_url
        
        # Step 1: Get signed message from signer service
        async with signer_client:
            signing_response = await signer_client.sign_cast(signing_request)
        
        if not signing_response.get("success"):
            return PostCastResponse(
                success=False,
                message="Failed to sign cast",
                error=signing_response.get("error", "Unknown signing error")
            )
        
        # Step 2: Submit signed message to Snapchain
        signed_message_bytes = bytes.fromhex(signing_response["signed_message_bytes"])
        submit_result = await snapchain_client.submit_message(signed_message_bytes)
        
        if submit_result.get("success"):
            return PostCastResponse(
                success=True,
                hash=signing_response.get("message_hash"),
                message="Cast posted successfully"
            )
        else:
            return PostCastResponse(
                success=False,
                message="Failed to submit cast to network",
                error=submit_result.get("error", "Unknown submission error")
            )
            
    except Exception as e:
        logger.error(f"Error posting cast: {e}")
        return PostCastResponse(
            success=False,
            message="Internal error while posting cast",
            error=str(e)
        )

@app.post("/v1/reaction", response_model=PostReactionResponse)
async def post_reaction(request: PostReactionRequest):
    """
    Post a reaction (like/recast) to a cast.
    
    This endpoint:
    1. Sends the reaction data to the signer service for signing
    2. Submits the signed message to the Snapchain node
    3. Returns the result
    """
    if not signer_client:
        raise HTTPException(status_code=503, detail="Signer client not available")
    
    if not snapchain_client:
        raise HTTPException(status_code=503, detail="Snapchain client not available")
    
    try:
        # Prepare signing request
        signing_request = {
            "target_cast_hash": request.target_cast_hash.replace("0x", ""),
            "target_cast_fid": request.target_cast_fid,
            "reaction_type": request.reaction_type
        }
        
        # Step 1: Get signed message from signer service
        async with signer_client:
            signing_response = await signer_client.sign_reaction(signing_request)
        
        if not signing_response.get("success"):
            return PostReactionResponse(
                success=False,
                message="Failed to sign reaction",
                error=signing_response.get("error", "Unknown signing error")
            )
        
        # Step 2: Submit signed message to Snapchain
        signed_message_bytes = bytes.fromhex(signing_response["signed_message_bytes"])
        submit_result = await snapchain_client.submit_message(signed_message_bytes)
        
        if submit_result.get("success"):
            return PostReactionResponse(
                success=True,
                hash=signing_response.get("message_hash"),
                message="Reaction posted successfully"
            )
        else:
            return PostReactionResponse(
                success=False,
                message="Failed to submit reaction to network",
                error=submit_result.get("error", "Unknown submission error")
            )
            
    except Exception as e:
        logger.error(f"Error posting reaction: {e}")
        return PostReactionResponse(
            success=False,
            message="Internal error while posting reaction",
            error=str(e)
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
