"""
Service-Oriented Farcaster Tools

Farcaster tools that use the service registry instead of direct observer access.
These tools demonstrate the new service-oriented architecture.
"""

import logging
import time
from typing import Any, Dict

from .base import ActionContext, ToolInterface

logger = logging.getLogger(__name__)


class ServiceOrientedSendFarcasterPostTool(ToolInterface):
    """
    Service-oriented tool for creating Farcaster casts.
    Uses the service registry instead of direct observer access.
    """

    @property
    def name(self) -> str:
        return "send_farcaster_post_v2"

    @property
    def description(self) -> str:
        return ("Service-oriented post tool for Farcaster. Uses clean service interfaces. "
                "Create a new Farcaster cast (post). Supports text content and optional embeds.")

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "content": "string - The text content of the cast",
            "embed_urls": "array (optional) - List of URLs to embed in the cast",
            "parent_url": "string (optional) - URL of the parent cast if this is a reply",
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """
        Execute the Farcaster post action using service-oriented approach.
        """
        logger.info(f"Executing service-oriented tool '{self.name}' with params: {params}")

        # Get Farcaster service from service registry
        farcaster_service = context.get_social_service("farcaster")
        if not farcaster_service:
            error_msg = "Farcaster social service not available"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Check if service is available
        if not await farcaster_service.is_available():
            error_msg = "Farcaster service is not currently available"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Extract and validate parameters
        content = params.get("content")
        embed_urls = params.get("embed_urls", [])
        parent_url = params.get("parent_url")

        if not content:
            error_msg = "Missing required parameter: content"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Create post using service
        result = await farcaster_service.create_post(
            content=content,
            embed_urls=embed_urls,
            parent_url=parent_url
        )

        return result


class ServiceOrientedLikeFarcasterPostTool(ToolInterface):
    """
    Service-oriented tool for liking Farcaster casts.
    Uses the service registry instead of direct observer access.
    """

    @property
    def name(self) -> str:
        return "like_farcaster_post_v2"

    @property
    def description(self) -> str:
        return ("Service-oriented like tool for Farcaster. Uses clean service interfaces. "
                "Like a Farcaster cast to show appreciation or agreement. "
                "Use this for acknowledgment, showing support, or expressing positive sentiment.")

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "cast_hash": "string - The hash of the cast to like",
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """
        Execute the Farcaster like action using service-oriented approach.
        """
        logger.info(f"Executing service-oriented tool '{self.name}' with params: {params}")

        # Get Farcaster service from service registry
        farcaster_service = context.get_social_service("farcaster")
        if not farcaster_service:
            error_msg = "Farcaster social service not available"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Check if service is available
        if not await farcaster_service.is_available():
            error_msg = "Farcaster service is not currently available"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Extract and validate parameters
        cast_hash = params.get("cast_hash")

        if not cast_hash:
            error_msg = "Missing required parameter: cast_hash"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Like post using service
        result = await farcaster_service.like_post(cast_hash)

        return result
