"""
SendFarcasterImagePostTool: Dedicated tool for posting images to Farcaster
"""
from .base import ActionContext, ToolInterface
from .farcaster_utils import FarcasterCastUtils
from typing import Any, Dict

class SendFarcasterImagePostTool(ToolInterface):
    """Tool for posting images to Farcaster with captions."""
    @property
    def name(self) -> str:
        return "send_farcaster_image_post"

    @property
    def description(self) -> str:
        return "Post an image to Farcaster with optional caption and alt text."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Caption/text for the image post"},
                "image_url": {"type": "string", "description": "URL of the image to post"},
                "alt_text": {"type": "string", "description": "Alternative text for accessibility"},
                "channel": {"type": "string", "description": "Channel to post in"}
            },
            "required": ["image_url"]
        }

    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        content = params.get("content", "")
        image_url = params["image_url"]
        alt_text = params.get("alt_text", "")
        channel = params.get("channel")
        # Validate and prepare media
        media = [{"url": image_url, "type": "image", "alt_text": alt_text}]
        content = FarcasterCastUtils.validate_content(content)
        # Use observer's post_cast with media
        result = await context.farcaster_observer.post_cast(
            content=content,
            channel=channel,
            embed_urls=[image_url],
            media=media
        )
        return {"status": "success" if result.get("success") else "failure", **result}
