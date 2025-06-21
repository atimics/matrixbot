"""
Permaweb Storage Tools

This module provides tools for storing memories and media permanently on Arweave.
"""

import json
import logging
import time
from typing import Any, Dict, Optional

from chatbot.config import settings
from chatbot.integrations.arweave_uploader_client import ArweaveUploaderClient
from chatbot.tools.base import ToolInterface

logger = logging.getLogger(__name__)


class StorePermanentMemoryTool(ToolInterface):
    """Tool for storing textual memories or media references permanently on Arweave."""

    @property
    def name(self) -> str:
        return "store_permanent_memory"

    @property
    def description(self) -> str:
        return (
            "Stores a textual memory or a reference to generated media (image/video Arweave URL) "
            "permanently on Arweave. Returns the Arweave transaction ID."
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
                "media_arweave_url": {
                    "type": "string",
                    "description": "The Arweave URL of an image or video to archive (optional).",
                },
                "media_content_type": {
                    "type": "string",
                    "description": "Required if media_arweave_url is provided (e.g., 'image/png', 'video/mp4').",
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
        media_arweave_url = params.get("media_arweave_url")
        media_content_type = params.get("media_content_type")
        custom_tags = params.get("tags", {})

        # Validate inputs
        if not memory_text and not media_arweave_url:
            return {
                "status": "error",
                "message": "Either memory_text or media_arweave_url must be provided",
            }

        if media_arweave_url and not media_content_type:
            return {
                "status": "error",
                "message": "media_content_type is required when media_arweave_url is provided",
            }

        # Check cooldowns and rate limits
        cooldown_check = self._check_cooldowns_and_limits(context)
        if cooldown_check["status"] == "error":
            return cooldown_check

        # Check if Arweave uploader is configured
        if (
            not settings.storage.arweave_uploader_api_endpoint
            or not settings.storage.arweave_uploader_api_key
        ):
            return {
                "status": "error",
                "message": "Arweave uploader service not configured",
            }

        try:
            arweave_client = ArweaveUploaderClient(
                api_endpoint=settings.storage.arweave_uploader_api_endpoint,
                api_key=settings.storage.arweave_uploader_api_key,
                gateway_url=settings.storage.arweave_gateway_url,
            )

            # Prepare data for upload
            data = None
            content_type = None

            if media_arweave_url and not memory_text:
                # Upload media only
                if hasattr(context, "arweave_service"):
                    try:
                        data = await context.arweave_service.download_file_data(media_arweave_url)
                        content_type = media_content_type
                        logger.info(
                            f"Downloaded media from Arweave for re-upload: {media_arweave_url}"
                        )
                    except Exception as e:
                        return {
                            "status": "error",
                            "message": f"Failed to download media from Arweave: {str(e)}",
                        }
                else:
                    return {
                        "status": "error",
                        "message": "Arweave service not available for media download",
                    }

            elif memory_text and not media_arweave_url:
                # Upload text only
                data = memory_text.encode("utf-8")
                content_type = "text/plain"

            else:
                # Upload both text and media reference as JSON
                memory_data = {
                    "text": memory_text,
                    "media_arweave_url": media_arweave_url,
                    "media_content_type": media_content_type,
                    "timestamp": time.time(),
                }
                data = json.dumps(memory_data).encode("utf-8")
                content_type = "application/json"

            # Prepare Arweave tags
            tags = []

            # Add default tags
            default_tags = {
                "App-Name": "RatiChat-v0.0.3",
                "Content-Type": content_type,
                "Timestamp": str(int(time.time())),
                "Version": "v0.0.3",
            }

            # Add custom tags
            all_tags = {**default_tags, **custom_tags}

            # Upload to Arweave
            tx_id = await arweave_client.upload_data(data, content_type, all_tags)

            if tx_id:
                arweave_url = arweave_client.get_arweave_url(tx_id)

                logger.info(f"Successfully stored memory on Arweave: {tx_id}")

                return {
                    "status": "success",
                    "arweave_tx_id": tx_id,
                    "arweave_url": arweave_url,
                    "message": "Memory stored permanently on Arweave",
                    "content_type": content_type,
                    "tags": all_tags,
                }
            else:
                return {"status": "error", "message": "Failed to upload to Arweave"}

        except Exception as e:
            logger.error(f"Permanent memory storage tool error: {e}")
            return {"status": "error", "message": f"Failed to store memory: {str(e)}"}

    def _check_cooldowns_and_limits(self, context) -> Dict[str, Any]:
        """Check cooldowns and rate limits for the tool."""
        # This will be implemented when we enhance the rate limiter
        # For now, return success
        return {"status": "success"}
