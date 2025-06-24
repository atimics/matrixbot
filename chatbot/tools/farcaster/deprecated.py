"""
Deprecated Farcaster tools.

These tools are kept for backward compatibility but are no longer functional.
"""
import logging
import time
from typing import Any, Dict

from ..base import ActionContext, ToolInterface
from .utils import create_error_response

logger = logging.getLogger(__name__)


class SendFarcasterDMTool(ToolInterface):
    """
    Tool for sending a direct message (DM) to a Farcaster user - DEPRECATED.
    """

    @property
    def name(self) -> str:
        return "send_farcaster_dm"

    @property
    def description(self) -> str:
        return "DEPRECATED: Send a direct message to a Farcaster user by FID. DM functionality is not supported by the Farcaster API."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "fid": {
                    "type": "integer",
                    "description": "The Farcaster ID of the recipient"
                },
                "content": {
                    "type": "string",
                    "description": "The DM content"
                }
            },
            "required": ["fid", "content"]
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        logger.info(f"Executing deprecated tool '{self.name}' with params: {params}")
        return create_error_response("Farcaster DM functionality is not supported by the API")
