"""
Tools for following and unfollowing Farcaster users.
"""
import logging
import time
from typing import Any, Dict

from ..base import ActionContext, ToolInterface
from .utils import get_farcaster_observer, create_error_response, create_success_response

logger = logging.getLogger(__name__)


class FollowFarcasterUserTool(ToolInterface):
    """
    Tool for following a Farcaster user.
    """

    @property
    def name(self) -> str:
        return "follow_farcaster_user"

    @property
    def description(self) -> str:
        return "Follow a Farcaster user by FID."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "fid": {
                    "type": "integer",
                    "description": "The Farcaster ID of the user to follow"
                }
            },
            "required": ["fid"]
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        logger.info(f"Executing tool '{self.name}' with params: {params}")
        
        farcaster_observer = get_farcaster_observer(context)
        if not farcaster_observer:
            return create_error_response("Farcaster integration not configured.")
            
        fid = params.get("fid")
        if fid is None:
            return create_error_response("Missing required parameter: fid")
            
        result = await farcaster_observer.follow_user(fid)
        if result.get("success"):
            return create_success_response(f"Successfully followed user {fid}", fid=fid)
        return create_error_response(result.get("error", "Unknown error"))


class UnfollowFarcasterUserTool(ToolInterface):
    """
    Tool for unfollowing a Farcaster user.
    """

    @property
    def name(self) -> str:
        return "unfollow_farcaster_user"

    @property
    def description(self) -> str:
        return "Unfollow a Farcaster user by FID."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "fid": {
                    "type": "integer",
                    "description": "The Farcaster ID of the user to unfollow"
                }
            },
            "required": ["fid"]
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        logger.info(f"Executing tool '{self.name}' with params: {params}")
        
        farcaster_observer = get_farcaster_observer(context)
        if not farcaster_observer:
            return create_error_response("Farcaster integration not configured.")
            
        fid = params.get("fid")
        if fid is None:
            return create_error_response("Missing required parameter: fid")
            
        result = await farcaster_observer.unfollow_user(fid)
        if result.get("success"):
            return create_success_response(f"Successfully unfollowed user {fid}", fid=fid)
        return create_error_response(result.get("error", "Unknown error"))
