"""
Media Generation Tools

This module provides tools for generating images and videos using AI services
like Replicate and Google AI (Gemini/Veo).
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


class GenerateImageTool(ToolInterface):
    """Tool for generating images from text prompts using AI services."""

    @property
    def name(self) -> str:
        return "generate_image"

    @property
    def description(self) -> str:
        return (
            "Generates an image from a text prompt. Specify aspect ratio if needed. "
            "The result is an S3 URL of the image, which can then be used in posts or stored as a memory."
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

        # Check cooldowns and rate limits
        cooldown_check = self._check_cooldowns_and_limits(context, "image")
        if cooldown_check["status"] == "error":
            return cooldown_check

        try:
            # Try Google Gemini first, fallback to Replicate
            image_data = None
            service_used = None

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
                        result = {
                            "status": "success",
                            "s3_image_url": image_url,  # Replicate returns direct URL
                            "prompt_used": prompt,
                            "service_used": service_used,
                            "aspect_ratio": aspect_ratio,
                        }

                        # Record this action result in world state for AI visibility
                        context.world_state_manager.add_action_result(
                            action_type="generate_image",
                            parameters={"prompt": prompt, "aspect_ratio": aspect_ratio},
                            result=f"Generated image using {service_used}: {image_url}"
                        )

                        # Record in generated media library
                        context.world_state_manager.record_generated_media(
                            media_url=image_url,
                            media_type="image",
                            prompt=prompt,
                            service_used=service_used,
                            aspect_ratio=aspect_ratio
                        )

                        return result
                except Exception as e:
                    logger.error(f"Replicate image generation failed: {e}")

            # If we have image data from Gemini, upload to S3
            if image_data and hasattr(context, "s3_service"):
                try:
                    # Generate a filename
                    timestamp = int(time.time())
                    filename = f"generated_image_{timestamp}.png"

                    # Upload to S3
                    s3_url = await context.s3_service.upload_image_data(
                        image_data, filename, content_type="image/png"
                    )

                    if s3_url:
                        result = {
                            "status": "success",
                            "s3_image_url": s3_url,
                            "prompt_used": prompt,
                            "service_used": service_used,
                            "aspect_ratio": aspect_ratio,
                        }

                        # Record this action result in world state for AI visibility
                        context.world_state_manager.add_action_result(
                            action_type="generate_image",
                            parameters={"prompt": prompt, "aspect_ratio": aspect_ratio},
                            result=f"Generated image using {service_used}, uploaded to S3: {result['s3_image_url']}"
                        )

                        # Record in generated media library
                        context.world_state_manager.record_generated_media(
                            media_url=s3_url,
                            media_type="image",
                            prompt=prompt,
                            service_used=service_used,
                            aspect_ratio=aspect_ratio
                        )

                        return result
                except Exception as e:
                    logger.error(f"Failed to upload image to S3: {e}")

            return {
                "status": "error",
                "message": "Failed to generate image with available services",
            }

        except Exception as e:
            logger.error(f"Image generation tool error: {e}")
            return {"status": "error", "message": f"Image generation failed: {str(e)}"}

    def _check_cooldowns_and_limits(self, context, tool_type: str) -> Dict[str, Any]:
        """Check cooldowns and rate limits for the tool."""
        # This will be implemented when we enhance the rate limiter
        # For now, return success
        return {"status": "success"}


class GenerateVideoTool(ToolInterface):
    """Tool for generating videos from text prompts using Google Veo."""

    @property
    def name(self) -> str:
        return "generate_video"

    @property
    def description(self) -> str:
        return (
            "Generates a short video clip from a text prompt, optionally using an input image as a reference. "
            "The result is an S3 URL of the video."
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
                "input_s3_image_url": {
                    "type": "string",
                    "description": "S3 URL of an image to use as a starting point/reference (optional).",
                },
                "aspect_ratio": {
                    "type": "string",
                    "description": "Desired aspect ratio, e.g., '16:9'. Defaults to '16:9'.",
                    "default": "16:9",
                },
            },
            "required": ["prompt"],
        }

    async def execute(self, params: Dict[str, Any], context) -> Dict[str, Any]:
        """Execute the video generation tool."""
        prompt = params.get("prompt", "")
        input_s3_image_url = params.get("input_s3_image_url")
        aspect_ratio = params.get("aspect_ratio", "16:9")

        if not prompt.strip():
            return {"status": "error", "message": "Prompt cannot be empty"}

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

            if input_s3_image_url and hasattr(context, "s3_service"):
                try:
                    # Download image from S3
                    input_image_bytes = await context.s3_service.download_file_data(
                        input_s3_image_url
                    )
                    input_mime_type = "image/png"  # Assume PNG for now
                    logger.info(f"Downloaded input image from S3: {input_s3_image_url}")
                except Exception as e:
                    logger.warning(f"Failed to download input image: {e}")

            # Generate video
            video_list = await google_client.generate_video_veo(
                prompt=prompt,
                input_image_bytes=input_image_bytes,
                input_mime_type=input_mime_type,
                aspect_ratio=aspect_ratio,
            )

            if video_list and len(video_list) > 0:
                video_data = video_list[0]  # Use first video

                # Upload to S3
                if hasattr(context, "s3_service"):
                    timestamp = int(time.time())
                    filename = f"generated_video_{timestamp}.mp4"

                    s3_url = await context.s3_service.upload_image_data(
                        video_data, filename, content_type="video/mp4"
                    )

                    if s3_url:
                        result = {
                            "status": "success",
                            "s3_video_url": s3_url,
                            "prompt_used": prompt,
                            "input_image_used": input_s3_image_url,
                            "aspect_ratio": aspect_ratio,
                        }

                        # Record this action result in world state for AI visibility
                        context.world_state_manager.add_action_result(
                            action_type="generate_video",
                            parameters={
                                "prompt": prompt, 
                                "aspect_ratio": aspect_ratio,
                                "input_s3_image_url": input_s3_image_url
                            },
                            result=f"Generated video using Google Veo, uploaded to S3: {s3_url}"
                        )

                        # Record in generated media library
                        context.world_state_manager.record_generated_media(
                            media_url=s3_url,
                            media_type="video",
                            prompt=prompt,
                            service_used="google_veo",
                            aspect_ratio=aspect_ratio,
                            metadata={
                                "input_image_url": input_s3_image_url,
                                "timestamp": timestamp
                            }
                        )

                        return result

            return {"status": "error", "message": "Failed to generate video"}

        except Exception as e:
            logger.error(f"Video generation tool error: {e}")
            return {"status": "error", "message": f"Video generation failed: {str(e)}"}

    def _check_cooldowns_and_limits(self, context, tool_type: str) -> Dict[str, Any]:
        """Check cooldowns and rate limits for the tool."""
        # This will be implemented when we enhance the rate limiter
        # For now, return success
        return {"status": "success"}
