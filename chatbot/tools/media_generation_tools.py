"""
Media Generation Tools

This module provides tools for generating images and videos using AI services
like Replicate and Google AI (Gemini/Veo) and storing them permanently on Arweave.
"""

import httpx
import logging
import time
from typing import Any, Dict, Optional

from chatbot.config import settings
from chatbot.integrations.google_ai_media_client import GoogleAIMediaClient
from chatbot.integrations.replicate_client import ReplicateClient
from chatbot.tools.base import ActionContext, ToolInterface
from chatbot.tools.matrix_tools import SendMatrixImageTool, SendMatrixVideoTool, SendMatrixVideoLinkTool

logger = logging.getLogger(__name__)


async def _auto_post_to_gallery(
    context: ActionContext,
    media_type: str,
    media_url: str,
    prompt: str,
    service_used: str,
) -> None:
    """
    Best-effort attempt to auto-post generated media to the configured Matrix gallery.
    Failures are logged as warnings and do not fail the parent tool.
    """
    if not settings.MATRIX_MEDIA_GALLERY_ROOM_ID:
        logger.debug("MATRIX_MEDIA_GALLERY_ROOM_ID not set, skipping auto-post to gallery.")
        return

    try:
        caption = (
            f"🎨 **New {media_type.capitalize()} Generated**\n\n"
            f"**Prompt:** `{prompt}`\n\n"
            f"**Service:** `{service_used}`\n\n"
            f"**[View on Arweave]({media_url})**"
        )

        if media_type == "image":
            tool = SendMatrixImageTool()
            params = {"channel_id": settings.MATRIX_MEDIA_GALLERY_ROOM_ID, "image_url": media_url, "caption": caption}
        elif media_type == "video":
            # Use link-based approach to avoid Matrix upload tuple errors
            tool = SendMatrixVideoLinkTool()
            params = {
                "channel_id": settings.MATRIX_MEDIA_GALLERY_ROOM_ID, 
                "video_url": media_url, 
                "caption": caption,
                "title": f"{service_used.title()} Generated Video"
            }
        else:
            return

        result = await tool.execute(params, context)
        if result.get("status") == "success":
            logger.info(f"Successfully auto-posted generated {media_type} to Matrix gallery.")
        else:
            logger.warning(f"Failed to auto-post generated {media_type} to gallery: {result.get('error')}")

    except Exception as e:
        logger.warning(f"Exception during media gallery auto-post: {e}", exc_info=True)


class GenerateImageTool(ToolInterface):
    """Tool for generating images from text prompts and storing them on Arweave."""

    @property
    def name(self) -> str:
        return "generate_image"

    @property
    def description(self) -> str:
        return (
            "Generates an image from a text prompt and stores it on Arweave. "
            "The image is automatically posted to a dedicated gallery channel for reference. "
            "To share the image elsewhere, use the returned `arweave_image_url` with another tool like 'send_matrix_image' or 'send_farcaster_post'."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Detailed description for the image generation.",
                },
                "aspect_ratio": {
                    "type": "string",
                    "description": "Desired aspect ratio, e.g., '1:1', '16:9', '4:3'. Defaults to '1:1'.",
                    "default": "1:1",
                },
            },
            "required": ["prompt"],
        }

    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        """Execute the image generation tool."""
        prompt = params.get("prompt", "")
        aspect_ratio = params.get("aspect_ratio", "1:1")

        if not prompt.strip():
            return {"status": "error", "message": "Prompt cannot be empty"}

        if not context.arweave_service or not context.arweave_service.is_configured():
            return {"status": "error", "message": "Arweave service is not configured."}

        try:
            image_data = None
            service_used = "unknown"

            # Try Google Gemini first
            if settings.GOOGLE_API_KEY:
                try:
                    google_client = GoogleAIMediaClient(api_key=settings.GOOGLE_API_KEY)
                    image_data = await google_client.generate_image_gemini(prompt, aspect_ratio)
                    if image_data:
                        service_used = "google_gemini"
                        logger.info(f"Generated image using Google Gemini: {prompt[:50]}...")
                except Exception as e:
                    logger.warning(f"Google Gemini image generation failed: {e}")

            # Fallback to Replicate if Gemini failed or was not used
            if not image_data and settings.REPLICATE_API_TOKEN:
                try:
                    replicate_client = ReplicateClient(api_token=settings.REPLICATE_API_TOKEN)
                    replicate_image_url = await replicate_client.generate_image(prompt, aspect_ratio=aspect_ratio)
                    if replicate_image_url:
                        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
                            response = await client.get(replicate_image_url)
                            response.raise_for_status()
                            image_data = response.content
                        service_used = "replicate"
                        logger.info(f"Generated and downloaded image using Replicate: {prompt[:50]}...")
                except Exception as e:
                    logger.warning(f"Replicate image generation failed: {e}")

            if not image_data:
                return {"status": "error", "message": "Failed to generate image data from any available service."}

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
                return {"status": "error", "message": "Failed to upload generated image to storage."}

            # Generate unique media_id for explicit action chaining
            media_id = f"media_img_{int(time.time() * 1000)}"
            
            # Record in world state with media_id
            context.world_state_manager.record_generated_media(
                media_url=image_url, media_type="image", prompt=prompt,
                service_used=service_used, aspect_ratio=aspect_ratio,
                media_id=media_id  # Store the media_id for chaining
            )

            await _auto_post_to_gallery(context, "image", image_url, prompt, service_used)

            return {
                "status": "success",
                "message": f"Image generated using {service_used} and stored on {storage_service}.",
                "media_id": media_id,  # Explicit media_id for chaining
                "media_url": image_url,  # Also provide direct URL for backward compatibility
                "image_url": image_url,  # Legacy field name
                "arweave_image_url": image_url if storage_service == "arweave" else None,
                "prompt_used": prompt,
                "storage_service": storage_service,
                "next_actions_suggestion": f"To share this image, use 'send_farcaster_post' or 'send_matrix_image' with media_id: {media_id}"
            }

        except Exception as e:
            logger.error(f"Image generation failed: {e}", exc_info=True)
            return {"status": "error", "message": f"Image generation failed: {str(e)}"}


class GenerateVideoTool(ToolInterface):
    """Tool for generating videos and storing them on Arweave."""

    @property
    def name(self) -> str:
        return "generate_video"

    @property
    def description(self) -> str:
        return (
            "Generates a short video clip from a text prompt. "
            "The resulting video is stored on Arweave and automatically posted to a gallery channel. "
            "Use the returned `arweave_video_url` to share it elsewhere."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Detailed description for the video generation.",
                },
                "aspect_ratio": {
                    "type": "string",
                    "description": "e.g., '16:9'. Defaults to '16:9'.",
                    "default": "16:9",
                },
            },
            "required": ["prompt"],
        }

    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        """Execute the video generation tool."""
        prompt = params.get("prompt", "")
        aspect_ratio = params.get("aspect_ratio", "16:9")

        if not prompt.strip():
            return {"status": "error", "message": "Prompt cannot be empty"}
        if not context.arweave_service or not context.arweave_service.is_configured():
            return {"status": "error", "message": "Arweave service is not configured."}
        if not settings.GOOGLE_API_KEY:
            return {"status": "error", "message": "Google AI API key not configured for video generation."}

        # Check daily video generation limit (1 per day)
        if context.world_state_manager:
            today_video_count = context.world_state_manager.get_daily_video_generation_count()
            if today_video_count >= 1:
                return {
                    "status": "error", 
                    "message": "Daily video generation limit reached (1 video per day). Please try again tomorrow.",
                    "daily_limit": 1,
                    "videos_generated_today": today_video_count
                }

        try:
            google_client = GoogleAIMediaClient(api_key=settings.GOOGLE_API_KEY)
            video_list = await google_client.generate_video_veo(prompt=prompt, aspect_ratio=aspect_ratio)

            if not video_list:
                return {"status": "error", "message": "Failed to generate video from Google Veo."}

            video_data = video_list[0]
            
            # Use dual storage: S3 for fast delivery, optionally Arweave for NFT potential
            if context.dual_storage_manager:
                video_url = await context.dual_storage_manager.upload_media(
                    video_data, "generated_video.mp4", "video/mp4"
                )
                storage_service = "s3" if context.dual_storage_manager.is_s3_available() else "arweave"
            else:
                # Fallback to direct Arweave upload
                video_url = await context.arweave_service.upload_media_data(
                    video_data, "generated_video.mp4", "video/mp4"
                )
                storage_service = "arweave"
            
            if not video_url:
                return {"status": "error", "message": "Failed to upload generated video to storage."}

            # Generate unique media_id for explicit action chaining
            media_id = f"media_vid_{int(time.time() * 1000)}"

            context.world_state_manager.record_generated_media(
                media_url=video_url, media_type="video", prompt=prompt,
                service_used="google_veo", aspect_ratio=aspect_ratio,
                media_id=media_id  # Store the media_id for chaining
            )

            await _auto_post_to_gallery(context, "video", video_url, prompt, "google_veo")

            return {
                "status": "success",
                "message": f"Video generated and stored on {storage_service}.",
                "media_id": media_id,  # Explicit media_id for chaining
                "media_url": video_url,  # Also provide direct URL for backward compatibility
                "video_url": video_url,  # Legacy field name
                "arweave_video_url": video_url if storage_service == "arweave" else None,
                "prompt_used": prompt,
                "storage_service": storage_service,
                "next_actions_suggestion": f"To share this video, use 'send_farcaster_post' or 'send_matrix_video_link' with media_id: {media_id}"
            }

        except Exception as e:
            logger.error(f"Video generation failed: {e}", exc_info=True)
            return {"status": "error", "message": f"Video generation failed: {str(e)}"}
