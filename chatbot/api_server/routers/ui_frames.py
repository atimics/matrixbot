"""
UI and Frames router for the chatbot API.

This module handles all UI serving and Farcaster frame endpoints including:
- Serving static UI files
- NFT minting frames
- Frame actions and responses
"""

from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
import os
from datetime import datetime
import logging

from chatbot.core.orchestration import MainOrchestrator
from ..dependencies import get_orchestrator
from chatbot.config import settings

logger = logging.getLogger(__name__)

# Create two routers - one for UI and one for frames
ui_router = APIRouter(tags=["ui"])
frames_router = APIRouter(prefix="/frames", tags=["frames"])


class FrameActionRequest(BaseModel):
    """Model for frame action requests."""
    untrustedData: Dict[str, Any]
    trustedData: Dict[str, Any]


# ===== UI ENDPOINTS =====

@ui_router.get("/")
async def serve_root():
    """Redirect root to UI."""
    ui_file = os.path.join(os.getcwd(), "ui", "index.html")
    if os.path.exists(ui_file):
        return FileResponse(ui_file)
    else:
        raise HTTPException(status_code=404, detail="UI not found. Please ensure ui/index.html exists.")


@ui_router.get("/ui/{file_path:path}")
async def serve_ui_files(file_path: str):
    """Serve UI static files."""
    ui_path = os.path.join(os.getcwd(), "ui", file_path)
    if os.path.exists(ui_path) and os.path.isfile(ui_path):
        return FileResponse(ui_path)
    else:
        # Fallback to index.html for SPA routing
        index_path = os.path.join(os.getcwd(), "ui", "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        else:
            raise HTTPException(status_code=404, detail="File not found")


# ===== FRAME ENDPOINTS =====

@frames_router.get("/mint/{frame_id}")
async def serve_mint_frame(
    frame_id: str,
    claim_type: str = "public",
    max_mints: int = 1,
    orchestrator: MainOrchestrator = Depends(get_orchestrator)
):
    """
    Serve the HTML for an NFT minting Farcaster Frame.
    
    Args:
        frame_id: Unique identifier for the frame
        claim_type: 'public' or 'gated' minting
        max_mints: Maximum number of mints allowed
        
    Returns:
        HTML response with Farcaster Frame meta tags
    """
    try:
        # Get frame metadata from world state
        world_state = orchestrator.world_state_manager.get_state()
        frame_metadata = getattr(world_state, 'nft_frames', {}).get(frame_id)
        
        if not frame_metadata:
            raise HTTPException(status_code=404, detail="Frame not found")
        
        # Build frame HTML with meta tags
        title = frame_metadata.get('title', 'AI Art NFT')
        description = frame_metadata.get('description', 'Mint this AI-generated artwork as an NFT')
        image_url = frame_metadata.get('image_url', '')
        button_text = "Check Eligibility" if claim_type == "gated" else "Mint NFT"
        
        # Construct action URL
        action_url = f"{settings.FRAMES_BASE_URL or 'https://yourbot.com'}/frames/action/mint/{frame_id}"
        
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{title}</title>
    
    <!-- Farcaster Frame Meta Tags -->
    <meta property="fc:frame" content="vNext" />
    <meta property="fc:frame:image" content="{image_url}" />
    <meta property="fc:frame:image:aspect_ratio" content="1:1" />
    <meta property="fc:frame:button:1" content="{button_text}" />
    <meta property="fc:frame:post_url" content="{action_url}" />
    
    <!-- Open Graph for social sharing -->
    <meta property="og:title" content="{title}" />
    <meta property="og:description" content="{description}" />
    <meta property="og:image" content="{image_url}" />
    
    <style>
        body {{
            font-family: Arial, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }}
        .frame-container {{
            text-align: center;
            background: white;
            padding: 2rem;
            border-radius: 10px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            max-width: 400px;
        }}
        .frame-image {{
            width: 100%;
            height: auto;
            border-radius: 10px;
            margin-bottom: 1rem;
        }}
        h1 {{ color: #333; }}
        p {{ color: #666; }}
        .mint-button {{
            background: #667eea;
            color: white;
            padding: 1rem 2rem;
            border: none;
            border-radius: 5px;
            font-size: 1.1rem;
            cursor: pointer;
            transition: background 0.3s;
        }}
        .mint-button:hover {{
            background: #5a6fd8;
        }}
    </style>
</head>
<body>
    <div class="frame-container">
        <img src="{image_url}" alt="{title}" class="frame-image" />
        <h1>{title}</h1>
        <p>{description}</p>
        <p><strong>Claim Type:</strong> {claim_type.title()}</p>
        <p><strong>Max Mints:</strong> {max_mints}</p>
        <button class="mint-button" onclick="alert('Use Farcaster to interact with this frame!')">{button_text}</button>
    </div>
</body>
</html>
"""
        
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        logger.error(f"Error serving mint frame: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@frames_router.post("/action/mint/{frame_id}")
async def handle_mint_action(
    frame_id: str,
    action_data: FrameActionRequest,
    orchestrator: MainOrchestrator = Depends(get_orchestrator)
):
    """
    Handle frame action for NFT minting.
    
    This endpoint processes the Farcaster frame button click and returns
    appropriate response based on user eligibility and minting logic.
    """
    try:
        # Extract user data from the frame action
        untrusted_data = action_data.untrustedData
        trusted_data = action_data.trustedData
        
        # Get user's FID (Farcaster ID)
        user_fid = untrusted_data.get('fid')
        button_index = untrusted_data.get('buttonIndex', 1)
        
        logger.info(f"Frame action for {frame_id} from user {user_fid}, button {button_index}")
        
        # Get frame metadata
        world_state = orchestrator.world_state_manager.get_state()
        frame_metadata = getattr(world_state, 'nft_frames', {}).get(frame_id)
        
        if not frame_metadata:
            return {
                "type": "frame",
                "frameData": {
                    "image": {"url": "https://via.placeholder.com/400x400?text=Frame+Not+Found"},
                    "buttons": [{"text": "Go Back"}],
                    "imageAspectRatio": "1:1"
                }
            }
        
        # Mock eligibility check - in reality, this would check user's wallet, 
        # previous actions, whitelist status, etc.
        is_eligible = True  # Simplified for demo
        
        if is_eligible:
            # Mock successful mint
            success_image = frame_metadata.get('success_image_url', 
                                             'https://via.placeholder.com/400x400?text=Mint+Successful!')
            
            return {
                "type": "frame",
                "frameData": {
                    "image": {"url": success_image},
                    "buttons": [
                        {"text": "View NFT", "action": "link", "target": f"https://opensea.io/assets/..."},
                        {"text": "Share", "action": "link", "target": f"https://warpcast.com/~/compose?text=Just+minted+{frame_metadata.get('title', 'NFT')}!"}
                    ],
                    "imageAspectRatio": "1:1"
                }
            }
        else:
            # Not eligible
            ineligible_image = frame_metadata.get('ineligible_image_url',
                                                'https://via.placeholder.com/400x400?text=Not+Eligible')
            
            return {
                "type": "frame", 
                "frameData": {
                    "image": {"url": ineligible_image},
                    "buttons": [{"text": "Learn More", "action": "link", "target": "https://yourbot.com/eligibility"}],
                    "imageAspectRatio": "1:1"
                }
            }
            
    except Exception as e:
        logger.error(f"Error handling mint action: {e}")
        # Return error frame
        return {
            "type": "frame",
            "frameData": {
                "image": {"url": "https://via.placeholder.com/400x400?text=Error+Occurred"},
                "buttons": [{"text": "Try Again"}],
                "imageAspectRatio": "1:1"
            }
        }


@frames_router.get("/ineligible")
async def serve_ineligible_frame():
    """Serve a frame for users who are not eligible for minting."""
    html_content = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Not Eligible</title>
    
    <!-- Farcaster Frame Meta Tags -->
    <meta property="fc:frame" content="vNext" />
    <meta property="fc:frame:image" content="https://via.placeholder.com/400x400?text=Not+Eligible" />
    <meta property="fc:frame:image:aspect_ratio" content="1:1" />
    <meta property="fc:frame:button:1" content="Learn More" />
    <meta property="fc:frame:button:1:action" content="link" />
    <meta property="fc:frame:button:1:target" content="https://yourbot.com/eligibility" />
    
    <style>
        body {
            font-family: Arial, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
            background: linear-gradient(135deg, #ff6b6b 0%, #ee5a24 100%);
        }
        .frame-container {
            text-align: center;
            background: white;
            padding: 2rem;
            border-radius: 10px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            max-width: 400px;
        }
        h1 { color: #e74c3c; }
        p { color: #666; }
    </style>
</head>
<body>
    <div class="frame-container">
        <h1>Not Eligible</h1>
        <p>Unfortunately, you don't meet the eligibility requirements for this NFT mint.</p>
        <p>Check the requirements or try again later!</p>
    </div>
</body>
</html>
"""
    
    return HTMLResponse(content=html_content)
