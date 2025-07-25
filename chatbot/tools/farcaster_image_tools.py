"""
Farcaster image posting tool - dedicated tool for image posts.
"""
from typing import Any, Dict
from .base import ActionContext, ToolInterface
from .farcaster_tools import SendFarcasterPostTool


class SendFarcasterImagePostTool(ToolInterface):
    """
    Tool for sending image posts to Farcaster.
    This is a specialized wrapper around SendFarcasterPostTool for image content.
    """

    def __init__(self):
        self._post_tool = SendFarcasterPostTool()

    @property
    def name(self) -> str:
        return "send_farcaster_image_post"

    @property
    def description(self) -> str:
        return ("Send an image post to Farcaster. This tool is optimized for image content "
                "and will automatically handle media formatting and attachment.")

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Optional text content to accompany the image"
                },
                "image_url": {
                    "type": "string",
                    "description": "URL of the image to post"
                },
                "alt_text": {
                    "type": "string",
                    "description": "Alternative text for accessibility"
                },
                "channel": {
                    "type": "string",
                    "description": "The channel to post in (if not provided, posts to user's timeline)"
                }
            },
            "required": ["image_url"]
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """
        Execute the image post by delegating to SendFarcasterPostTool with proper media formatting.
        """
        # Extract image-specific parameters
        image_url = params.get("image_url")
        alt_text = params.get("alt_text", "")
        content = params.get("content", "")
        channel = params.get("channel")

        # Prepare media array for the base tool
        media = [
            {
                "url": image_url,
                "type": "image",
                "alt_text": alt_text
            }
        ]

        # Delegate to the base SendFarcasterPostTool with media
        base_params = {
            "content": content,
            "channel": channel,
            "media": media
        }

        return await self._post_tool.execute(base_params, context)
