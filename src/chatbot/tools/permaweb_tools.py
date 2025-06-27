"""
Permanent Storage Tools

This module provides tools for storing memories and media permanently on S3.
"""

import json
import logging
import time
from typing import Any, Dict

from chatbot.config import settings
from chatbot.integrations.s3_client import S3Client
from chatbot.tools.base import ToolInterface

logger = logging.getLogger(__name__)


class StorePermanentMemoryTool(ToolInterface):
    """Tool for storing textual memories or media references permanently on S3."""

    @property
    def name(self) -> str:
        return "store_permanent_memory"

    @property
    def description(self) -> str:
        return (
            "Stores a textual memory or a reference to generated media (image/video S3 URL) "
            "permanently on S3. Returns the S3 URL."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "memory_text": {
                    "type": "string",
                    "description": "The textual content of the memory (optional).",
                },
                "media_s3_url": {
                    "type": "string",
                    "description": "The S3 URL of an image or video to archive (optional).",
                },
                "media_content_type": {
                    "type": "string",
                    "description": "Required if media_s3_url is provided (e.g., 'image/png', 'video/mp4').",
                },
                "tags": {
                    "type": "object",
                    "description": "Key-value string pairs for Arweave tags (e.g., {'type': 'ai_observation', 'source_cast': '0x...'}) (optional).",
                    "additionalProperties": {"type": "string"},
                },
            },
            "anyOf": [
                {"required": ["memory_text"]},
                {"required": ["media_arweave_url", "media_content_type"]},
            ],
        }

    async def execute(self, params: Dict[str, Any], context) -> Dict[str, Any]:
        """Execute the permanent memory storage tool."""
        memory_text = params.get("memory_text")
        media_s3_url = params.get("media_s3_url")
        media_content_type = params.get("media_content_type")
        custom_tags = params.get("tags", {})

        # Validate inputs
        if not memory_text and not media_s3_url:
            return {
                "status": "error",
                "message": "Either memory_text or media_s3_url must be provided",
            }

        if media_s3_url and not media_content_type:
            return {
                "status": "error",
                "message": "media_content_type is required when media_s3_url is provided",
            }

        # Check cooldowns and rate limits
        cooldown_check = self._check_cooldowns_and_limits(context)
        if cooldown_check["status"] == "error":
            return cooldown_check

        # Check if S3 service is configured
        if not all([settings.s3_api_endpoint, settings.s3_api_key, settings.cloudfront_domain]):
            return {
                "status": "error",
                "message": "S3 service not configured",
            }

        try:
            s3_client = S3Client(
                s3_api_endpoint=settings.s3_api_endpoint,
                s3_api_key=settings.s3_api_key,
                cloudfront_domain=settings.cloudfront_domain,
            )

            # Prepare data for upload
            data = None
            content_type = None

            if media_s3_url and not memory_text:
                # Upload media only
                if hasattr(context, "s3_service"):
                    try:
                        data = await context.s3_service.download_file_data(media_s3_url)
                        content_type = media_content_type
                        logger.info(
                            f"Downloaded media from S3 for re-upload: {media_s3_url}"
                        )
                    except Exception as e:
                        return {
                            "status": "error",
                            "message": f"Failed to download media from S3: {str(e)}",
                        }
                else:
                    return {
                        "status": "error",
                        "message": "S3 service not available for media download",
                    }

            elif memory_text and not media_s3_url:
                # Upload text only
                data = memory_text.encode("utf-8")
                content_type = "text/plain"

            else:
                # Upload both text and media reference as JSON
                memory_data = {
                    "text": memory_text,
                    "media_s3_url": media_s3_url,
                    "media_content_type": media_content_type,
                    "timestamp": time.time(),
                }
                data = json.dumps(memory_data).encode("utf-8")
                content_type = "application/json"

            # Prepare S3 tags (kept for compatibility, though S3 API might not use them)
            tags = {
                "App-Name": "RatiChat-v0.0.3",
                "Content-Type": content_type,
                "Timestamp": str(int(time.time())),
                "Version": "v0.0.3",
                **custom_tags
            }

            # Upload to S3
            s3_url = await s3_client.upload_data(data, content_type, tags)

            if s3_url:
                logger.info(f"Successfully stored memory on S3: {s3_url}")

                return {
                    "status": "success",
                    "s3_url": s3_url,
                    "message": "Memory stored permanently on S3",
                    "content_type": content_type,
                    "tags": tags,
                }
            else:
                return {"status": "error", "message": "Failed to upload to S3"}

        except Exception as e:
            logger.error(f"Permanent memory storage tool error: {e}")
            return {"status": "error", "message": f"Failed to store memory: {str(e)}"}

    def _check_cooldowns_and_limits(self, context) -> Dict[str, Any]:
        """Check cooldowns and rate limits for the tool."""
        # This will be implemented when we enhance the rate limiter
        # For now, return success
        return {"status": "success"}
