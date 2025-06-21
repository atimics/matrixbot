"""
Message Enhancement Tools

This module provides utilities for enhancing messages with automatically generated media
based on image descriptions found at the beginning of messages.
"""

import logging
import re
import time
from typing import Any, Dict, Optional, Tuple

from chatbot.config import settings
from chatbot.integrations.google_ai_media_client import GoogleAIMediaClient
from chatbot.integrations.replicate_client import ReplicateClient
from chatbot.tools.base import ActionContext
import httpx

logger = logging.getLogger(__name__)


def extract_image_description(content: str) -> Tuple[Optional[str], str]:
    """
    Extract image description from the beginning of message content.
    
    Supports formats like:
    - "image_description": "a cat sitting on a windowsill" The rest of the message...
    - "image": "sunset over mountains" Here's what I think about that...
    - "img": "abstract art" This is my response...
    
    Args:
        content: The message content to parse
        
    Returns:
        Tuple of (image_description, remaining_content)
        Returns (None, original_content) if no image description found
    """
    if not content or not isinstance(content, str):
        return None, content
    
    # Patterns to match image descriptions at the start of messages
    patterns = [
        r'^"image_description":\s*"([^"]+)"\s*(.*)$',
        r'^"image":\s*"([^"]+)"\s*(.*)$', 
        r'^"img":\s*"([^"]+)"\s*(.*)$',
        r'^image_description:\s*"([^"]+)"\s*(.*)$',
        r'^image:\s*"([^"]+)"\s*(.*)$',
        r'^img:\s*"([^"]+)"\s*(.*)$',
    ]
    
    for pattern in patterns:
        match = re.match(pattern, content.strip(), re.IGNORECASE | re.DOTALL)
        if match:
            image_desc = match.group(1).strip()
            remaining_content = match.group(2).strip()
            logger.info(f"Extracted image description: '{image_desc[:50]}...'")
            return image_desc, remaining_content
    
    return None, content


async def generate_image_from_description(
    image_description: str,
    context: ActionContext,
    aspect_ratio: str = "1:1"
) -> Optional[Dict[str, Any]]:
    """
    Generate an image from a text description using available AI services.
    
    Args:
        image_description: Text description of the image to generate
        context: ActionContext for accessing services
        aspect_ratio: Desired aspect ratio (default: "1:1")
        
    Returns:
        Dict with image info if successful, None if failed
        Dict contains: {
            "image_url": str,
            "media_id": str, 
            "service_used": str,
            "storage_service": str
        }
    """
    if not context.arweave_service or not context.arweave_service.is_configured():
        logger.warning("Cannot generate image: Arweave service not configured")
        return None
    
    try:
        image_data = None
        service_used = "unknown"

        # Try Google Gemini first
        if settings.GOOGLE_API_KEY:
            try:
                google_client = GoogleAIMediaClient(api_key=settings.GOOGLE_API_KEY)
                image_data = await google_client.generate_image_gemini(image_description, aspect_ratio)
                if image_data:
                    service_used = "google_gemini"
                    logger.info(f"Generated image using Google Gemini: {image_description[:50]}...")
            except Exception as e:
                if "Multi-modal output is not supported" in str(e):
                    logger.debug("Google Gemini multi-modal output not supported, falling back to Replicate")
                else:
                    logger.warning(f"Google Gemini image generation failed: {e}")

        # Fallback to Replicate if Gemini failed or was not used
        if not image_data and settings.REPLICATE_API_TOKEN:
            try:
                replicate_client = ReplicateClient(api_token=settings.REPLICATE_API_TOKEN)
                replicate_image_url = await replicate_client.generate_image(image_description, aspect_ratio=aspect_ratio)
                if replicate_image_url:
                    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
                        response = await client.get(replicate_image_url)
                        response.raise_for_status()
                        image_data = response.content
                    service_used = "replicate"
                    logger.info(f"Generated and downloaded image using Replicate: {image_description[:50]}...")
            except Exception as e:
                logger.warning(f"Replicate image generation failed: {e}")

        if not image_data:
            logger.error("Failed to generate image data from any available service")
            return None

        # Use dual storage: S3 for fast delivery, optionally Arweave for NFT potential
        if context.dual_storage_manager:
            image_url = await context.dual_storage_manager.upload_media(
                image_data, "generated_image.png", "image/png"
            )
            storage_service = "s3" if context.dual_storage_manager.is_s3_available() else "arweave"
        else:
            # Fallback to direct Arweave upload
            image_url = await context.arweave_service.upload_image_data(image_data, "generated_image.png", "image/png")
            storage_service = "arweave"
        
        if not image_url:
            logger.error("Failed to upload generated image to storage")
            return None

        # Generate unique media_id for explicit action chaining
        media_id = f"media_img_{int(time.time() * 1000)}"
        
        # Record in world state with media_id
        if context.world_state_manager:
            context.world_state_manager.record_generated_media(
                media_url=image_url, media_type="image", prompt=image_description,
                service_used=service_used, aspect_ratio=aspect_ratio,
                media_id=media_id
            )

        return {
            "image_url": image_url,
            "media_id": media_id,
            "service_used": service_used,
            "storage_service": storage_service,
            "prompt_used": image_description
        }

    except Exception as e:
        logger.error(f"Image generation failed: {e}", exc_info=True)
        return None


async def enhance_message_with_image(
    content: str,
    context: ActionContext,
    current_channel_id: Optional[str] = None
) -> Tuple[str, Optional[Dict[str, Any]]]:
    """
    Check if message content contains an image description and enhance it with generated image.
    
    Args:
        content: Original message content
        context: ActionContext for accessing services
        current_channel_id: Current channel ID for posting
        
    Returns:
        Tuple of (enhanced_content, image_info)
        - enhanced_content: Message content with image description removed
        - image_info: Dict with image details if generated, None otherwise
    """
    image_description, remaining_content = extract_image_description(content)
    
    if not image_description:
        return content, None
    
    # Generate the image
    image_info = await generate_image_from_description(image_description, context)
    
    if not image_info:
        # If image generation failed, return original content
        logger.warning(f"Failed to generate image for description: {image_description}")
        return content, None
    
    # Auto-post to gallery if configured
    if settings.matrix_media_gallery_room_id:
        try:
            from .matrix import SendMatrixImageTool
            gallery_tool = SendMatrixImageTool()
            gallery_caption = (
                f"🎨 **Auto-Generated Image**\n\n"
                f"**Description:** `{image_description}`\n\n"
                f"**Service:** `{image_info['service_used']}`\n\n"
                f"**[View on Storage]({image_info['image_url']})**"
            )
            
            await gallery_tool.execute({
                "channel_id": settings.matrix_media_gallery_room_id,
                "image_url": image_info["image_url"],
                "caption": gallery_caption
            }, context)
            
            logger.info("Auto-posted generated image to gallery")
            
        except Exception as e:
            logger.warning(f"Failed to auto-post to gallery: {e}")
    
    # Enhance the remaining content to reference the generated image
    if remaining_content:
        enhanced_content = f"🎨 Generated image: {image_description}\n\n{remaining_content}"
    else:
        enhanced_content = f"🎨 Generated image: {image_description}"
    
    return enhanced_content, image_info
