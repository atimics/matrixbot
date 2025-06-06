"""
Media Generation Tools

This module provides tools for generating images and videos using AI services
like Replicate and Google AI (Gemini/Veo) and storing them permanently on Arweave.
"""

import asyncio
import logging
import time
from typing import Any, Dict, Optional

from chatbot.config import settings
from chatbot.integrations.arweave_uploader_client import ArweaveUploaderClient
from chatbot.integrations.google_ai_media_client import GoogleAIMediaClient
from chatbot.integrations.replicate_client import ReplicateClient
from chatbot.tools.base import ToolInterface

logger = logging.getLogger(__name__)


def _create_embed_html(title: str, description: str, media_url: str, media_type: str = 'image') -> str:
    """Creates the HTML for a Farcaster embed page."""
    # Use the media_url itself as the thumbnail for simplicity
    thumbnail_url = media_url
    
    if media_type == 'video':
        return f"""<!DOCTYPE html><html><head><title>{title}</title>
<meta property="og:title" content="{title}" />
<meta property="og:description" content="{description}" />
<meta property="og:image" content="{thumbnail_url}" />
<meta property="og:video" content="{media_url}" />
<meta property="og:video:type" content="video/mp4" />
<meta property="fc:frame" content="vNext" />
<meta property="fc:frame:image" content="{thumbnail_url}" />
<meta property="fc:frame:video" content="{media_url}" />
<meta property="fc:frame:video:type" content="video/mp4" />
</head><body><h1>{title}</h1><p>{description}</p><video controls src="{media_url}"></video></body></html>"""
    else:  # image
        return f"""<!DOCTYPE html><html><head><title>{title}</title>
<meta property="og:title" content="{title}" />
<meta property="og:description" content="{description}" />
<meta property="og:image" content="{media_url}" />
<meta property="fc:frame" content="vNext" />
<meta property="fc:frame:image" content="{media_url}" />
</head><body><h1>{title}</h1><p>{description}</p><img src="{media_url}" alt="{title}"/></body></html>"""


class GenerateImageTool(ToolInterface):
    """Tool for generating images from text prompts and storing them on Arweave."""

    @property
    def name(self) -> str:
        return "generate_image"

    @property
    def description(self) -> str:
        return (
            "Generates an image from a text prompt and stores it on Arweave. "
            "Returns an Arweave URL for an embeddable HTML page. "
            "To share, use 'send_farcaster_post' with the `embed_url` parameter pointing to the returned 'embed_page_url'."
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

    async def execute(self, params: Dict[str, Any], context) -> Dict[str, Any]:
        """Execute the image generation tool."""
        prompt = params.get("prompt", "")
        aspect_ratio = params.get("aspect_ratio", "1:1")

        if not prompt.strip():
            return {"status": "error", "message": "Prompt cannot be empty"}

        if not context.arweave_client:
            return {"status": "error", "message": "Arweave client is not configured."}

        # Check cooldowns and rate limits
        cooldown_check = self._check_cooldowns_and_limits(context, "image")
        if cooldown_check["status"] == "error":
            return cooldown_check

        try:
            # 1. Generate image data
            image_data = None
            service_used = None

            # Try Google Gemini first
            if settings.GOOGLE_API_KEY:
                try:
                    google_client = GoogleAIMediaClient(
                        api_key=settings.GOOGLE_API_KEY,
                        default_gemini_image_model=settings.GOOGLE_GEMINI_IMAGE_MODEL,
                    )
                    image_data = await google_client.generate_image_gemini(prompt, aspect_ratio)
                    if image_data:
                        service_used = "google_gemini"
                        logger.info(f"Generated image using Google Gemini: {prompt[:50]}...")
                except Exception as e:
                    logger.warning(f"Google Gemini image generation failed: {e}")

            # Fallback to Replicate if Gemini failed
            if not image_data and settings.REPLICATE_API_TOKEN:
                try:
                    replicate_client = ReplicateClient(api_token=settings.REPLICATE_API_TOKEN)
                    image_data = await replicate_client.generate_image(
                        prompt=prompt,
                        model=settings.REPLICATE_IMAGE_MODEL,
                        lora_weights_url=settings.REPLICATE_LORA_WEIGHTS_URL,
                        lora_scale=settings.REPLICATE_LORA_SCALE,
                        aspect_ratio=aspect_ratio,
                    )
                    if image_data:
                        service_used = "replicate"
                        logger.info(f"Generated image using Replicate: {prompt[:50]}...")
                except Exception as e:
                    logger.warning(f"Replicate image generation failed: {e}")

            if not image_data:
                return {"status": "error", "message": "Failed to generate image data from any service."}

            # 2. Upload image to Arweave
            tags = [{"name": "Content-Type", "value": "image/png"}, {"name": "Creator", "value": "Chatbot"}]
            image_tx_id = await context.arweave_client.upload_data(image_data, "image/png", tags)
            if not image_tx_id:
                return {"status": "error", "message": "Failed to upload image to Arweave."}
            image_arweave_url = context.arweave_client.get_arweave_url(image_tx_id)

            # 3. Create and upload HTML embed page to Arweave
            html_content = _create_embed_html(
                title=prompt[:100] + ("..." if len(prompt) > 100 else ""),
                description="AI-generated image by Chatbot.",
                media_url=image_arweave_url,
                media_type='image'
            )
            html_tags = [{"name": "Content-Type", "value": "text/html"}, {"name": "Creator", "value": "Chatbot"}]
            html_tx_id = await context.arweave_client.upload_data(html_content.encode('utf-8'), "text/html", html_tags)
            if not html_tx_id:
                return {"status": "error", "message": "Failed to upload embed page to Arweave."}
            embed_page_url = context.arweave_client.get_arweave_url(html_tx_id)

            # Record in world state
            context.world_state_manager.record_generated_media(
                media_url=image_arweave_url, media_type="image", prompt=prompt,
                service_used=service_used, aspect_ratio=aspect_ratio,
                metadata={"embed_page_url": embed_page_url, "html_tx_id": html_tx_id}
            )

            return {
                "status": "success",
                "message": "Image generated and embed page stored on Arweave.",
                "embed_page_url": embed_page_url,
                "image_url": image_arweave_url,
                "image_tx_id": image_tx_id,
                "html_tx_id": html_tx_id,
                "prompt_used": prompt,
            }

        except Exception as e:
            logger.error(f"Image generation failed: {e}")
            return {"status": "error", "message": f"Image generation failed: {str(e)}"}

            if settings.GOOGLE_API_KEY:
                try:
                    google_client = GoogleAIMediaClient(
                        api_key=settings.GOOGLE_API_KEY,
                        default_gemini_image_model=settings.GOOGLE_GEMINI_IMAGE_MODEL,
                    )
                    image_data = await google_client.generate_image_gemini(
                        prompt, aspect_ratio
                    )
                    service_used = "google_gemini"
                    logger.info(
                        f"Generated image using Google Gemini: {prompt[:50]}..."
                    )
                except Exception as e:
                    logger.warning(f"Google Gemini image generation failed: {e}")

            # Fallback to Replicate if Gemini failed or not available
            if not image_data and settings.REPLICATE_API_TOKEN:
                try:
                    replicate_client = ReplicateClient(
                        api_token=settings.REPLICATE_API_TOKEN,
                        default_model=settings.REPLICATE_IMAGE_MODEL,
                        default_lora_weights_url=settings.REPLICATE_LORA_WEIGHTS_URL,
                        default_lora_scale=settings.REPLICATE_LORA_SCALE,
                    )
                    image_url = await replicate_client.generate_image(
                        prompt, aspect_ratio=aspect_ratio
                    )
                    service_used = "replicate"
                    logger.info(f"Generated image using Replicate: {prompt[:50]}...")

                    if image_url:
                        # ALWAYS require S3 service for uploads - fail if not available
                        if not hasattr(context, "s3_service"):
                            logger.error("S3 service not available - image generation requires S3 storage")
                            return {
                                "status": "error",
                                "message": "Image generation requires S3 storage but S3 service is not available"
                            }
                        try:
                            s3_url = await context.s3_service.ensure_s3_url(image_url)
                            if s3_url and context.s3_service.is_s3_url(s3_url):
                                pass  # s3_url is set
                            else:
                                logger.error(f"Failed to ensure image is on S3 - received: {s3_url}")
                                return {
                                    "status": "error",
                                    "message": "Image generated but failed to upload to S3 - all images must be stored on S3"
                                }
                        except Exception as s3_error:
                            logger.error(f"Failed to upload Replicate image to S3: {s3_error}")
                            return {
                                "status": "error", 
                                "message": f"Image generated but S3 upload failed: {str(s3_error)}"
                            }
                    else:
                        logger.error("Replicate image generation returned no URL")
                        return {
                            "status": "error",
                            "message": "Replicate image generation failed - no URL returned"
                        }
                except Exception as e:
                    logger.error(f"Replicate image generation failed: {e}")

            # If we have image data from Gemini, upload to S3
            if image_data:
                if not hasattr(context, "s3_service"):
                    logger.error("S3 service not available - image generation requires S3 storage")
                    return {
                        "status": "error",
                        "message": "Image generation requires S3 storage but S3 service is not available"
                    }
                try:
                    timestamp = int(time.time())
                    filename = f"generated_image_{timestamp}.png"
                    s3_url = await context.s3_service.upload_image_data(
                        image_data, filename
                    )
                    if not s3_url:
                        logger.error("Failed to upload image data to S3")
                        return {
                            "status": "error",
                            "message": "Image generated but S3 upload failed - all images must be stored on S3"
                        }
                except Exception as e:
                    logger.error(f"Failed to upload image to S3: {e}")
                    return {
                        "status": "error",
                        "message": f"Image generated but S3 upload failed: {str(e)}"
                    }

            if not s3_url:
                return {
                    "status": "error",
                    "message": "Failed to generate image with available services (Google Gemini and/or Replicate)",
                }

            # Record this action result in world state for AI visibility
            context.world_state_manager.add_action_result(
                action_type="generate_image",
                parameters={"prompt": prompt, "aspect_ratio": aspect_ratio},
                result=s3_url
            )

            # Record in generated media library
            context.world_state_manager.record_generated_media(
                media_url=s3_url,
                media_type="image",
                prompt=prompt,
                service_used=service_used,
                aspect_ratio=aspect_ratio
            )

            # --- Always post to Farcaster ---
            try:
                from chatbot.tools.farcaster_tools import SendFarcasterPostTool
                
                farcaster_tool = SendFarcasterPostTool()
                # Generate a meaningful caption for the image post
                image_caption = f"Generated: {prompt[:200]}{'...' if len(prompt) > 200 else ''}"
                farcaster_params = {
                    "content": image_caption,  # Meaningful content describing the generated image
                    "image_s3_url": s3_url
                }
                # Optionally, add channel if available in params
                if "channel" in params:
                    farcaster_params["channel"] = params["channel"]
                elif "farcaster_channel_id" in params:  # Alternative parameter name
                    farcaster_params["channel"] = params["farcaster_channel_id"]
                farcaster_result = await farcaster_tool.execute(farcaster_params, context)
            except Exception as farcaster_exc:
                logger.error(f"Failed to auto-post image to Farcaster: {farcaster_exc}")
                farcaster_result = {"status": "error", "message": f"Farcaster post failed: {str(farcaster_exc)}"}

            result = {
                "status": "success",
                "message": f"Generated image using {service_used} for prompt: {prompt[:50]}...",
                "image_url": s3_url,
                "s3_image_url": s3_url,
                "prompt_used": prompt,
                "service_used": service_used,
                "aspect_ratio": aspect_ratio,
                "farcaster_post_result": farcaster_result,
                "next_actions_suggestion": f"Use 'send_matrix_image' or 'send_farcaster_post' with image_s3_url parameter to share this image: {s3_url}"
            }
            return result

        except Exception as e:
            logger.error(f"Image generation tool error: {e}")
            return {"status": "error", "message": f"Image generation failed: {str(e)}"}

    def _check_cooldowns_and_limits(self, context, tool_type: str) -> Dict[str, Any]:
        """Check cooldowns and rate limits for the tool."""
        # This will be implemented when we enhance the rate limiter
        # For now, return success
        return {"status": "success"}


class GenerateVideoTool(ToolInterface):
    """Tool for generating videos and storing them on Arweave."""

    @property
    def name(self) -> str:
        return "generate_video"

    @property
    def description(self) -> str:
        return (
            "Generates a short video clip from a text prompt. "
            "The result is an Arweave URL of an HTML page suitable for Farcaster embeds."
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
                "input_arweave_image_tx_id": {
                    "type": "string",
                    "description": "Arweave TX ID of an image to use as a starting point (optional).",
                },
                "aspect_ratio": {
                    "type": "string",
                    "description": "e.g., '16:9'. Defaults to '16:9'.",
                    "default": "16:9",
                },
            },
            "required": ["prompt"],
        }

    async def execute(self, params: Dict[str, Any], context) -> Dict[str, Any]:
        """Execute the video generation tool."""
        prompt = params.get("prompt", "")
        input_arweave_image_tx_id = params.get("input_arweave_image_tx_id")
        aspect_ratio = params.get("aspect_ratio", "16:9")

        if not prompt.strip():
            return {"status": "error", "message": "Prompt cannot be empty"}

        if not context.arweave_client:
            return {"status": "error", "message": "Arweave client is not configured."}

        # Check cooldowns and rate limits
        cooldown_check = self._check_cooldowns_and_limits(context, "video")
        if cooldown_check["status"] == "error":
            return cooldown_check

        if not settings.GOOGLE_API_KEY:
            return {
                "status": "error",
                "message": "Google AI API key not configured for video generation",
            }

        try:
            google_client = GoogleAIMediaClient(
                api_key=settings.GOOGLE_API_KEY,
                default_veo_video_model=settings.GOOGLE_VEO_VIDEO_MODEL,
            )

            # Handle input image if provided
            input_image_bytes = None
            input_mime_type = None
            if input_arweave_image_tx_id:
                try:
                    # Download image from Arweave
                    input_arweave_url = context.arweave_client.get_arweave_url(input_arweave_image_tx_id)
                    import httpx
                    async with httpx.AsyncClient() as client:
                        response = await client.get(input_arweave_url)
                        response.raise_for_status()
                        input_image_bytes = response.content
                        input_mime_type = response.headers.get('content-type', 'image/jpeg')
                        logger.info(f"Downloaded input image from Arweave: {input_arweave_url}")
                except Exception as e:
                    logger.warning(f"Failed to download input image from Arweave: {e}")

            # Generate video using Google Veo
            video_list = await google_client.generate_video_veo(
                prompt=prompt,
                aspect_ratio=aspect_ratio,
                input_image_bytes=input_image_bytes,
                input_mime_type=input_mime_type,
            )

            if not video_list:
                return {"status": "error", "message": "Failed to generate video."}

            video_data = video_list[0]  # Take the first video

            # 2. Upload video to Arweave
            video_tags = [{"name": "Content-Type", "value": "video/mp4"}, {"name": "Creator", "value": "Chatbot"}]
            video_tx_id = await context.arweave_client.upload_data(video_data, "video/mp4", video_tags)
            if not video_tx_id:
                return {"status": "error", "message": "Failed to upload video to Arweave."}
            video_arweave_url = context.arweave_client.get_arweave_url(video_tx_id)

            # 3. Create and upload HTML embed page
            html_content = _create_embed_html(
                title=prompt[:100] + ("..." if len(prompt) > 100 else ""),
                description="AI-generated video by Chatbot.",
                media_url=video_arweave_url,
                media_type='video'
            )
            html_tags = [{"name": "Content-Type", "value": "text/html"}, {"name": "Creator", "value": "Chatbot"}]
            html_tx_id = await context.arweave_client.upload_data(html_content.encode('utf-8'), "text/html", html_tags)
            if not html_tx_id:
                return {"status": "error", "message": "Failed to upload video embed page to Arweave."}
            embed_page_url = context.arweave_client.get_arweave_url(html_tx_id)

            # Record in world state
            context.world_state_manager.record_generated_media(
                media_url=video_arweave_url, media_type="video", prompt=prompt,
                service_used="google_veo", aspect_ratio=aspect_ratio,
                metadata={"embed_page_url": embed_page_url, "html_tx_id": html_tx_id}
            )

            return {
                "status": "success",
                "message": "Video generated and embed page stored on Arweave.",
                "embed_page_url": embed_page_url,
                "video_url": video_arweave_url,
                "video_tx_id": video_tx_id,
                "html_tx_id": html_tx_id,
                "prompt_used": prompt,
            }

        except Exception as e:
            logger.error(f"Video generation failed: {e}")
            return {"status": "error", "message": f"Video generation failed: {str(e)}"}

    def _check_cooldowns_and_limits(self, context, tool_type: str) -> Dict[str, Any]:
        """Check cooldowns and rate limits for the tool."""
        # This will be implemented when we enhance the rate limiter
        # For now, return success
        return {"status": "success"}
