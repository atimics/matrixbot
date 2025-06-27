"""
Tool for liking Farcaster posts.
"""
import logging
import time
from typing import Any, Dict

from ..base import ActionContext, ToolInterface
from .utils import get_farcaster_observer, create_error_response, create_success_response

logger = logging.getLogger(__name__)


class LikeFarcasterPostTool(ToolInterface):
    """
    Tool for liking (reacting to) posts on Farcaster.
    """

    @property
    def name(self) -> str:
        return "like_farcaster_post"

    @property
    def description(self) -> str:
        return "Like (react to) a specific cast on Farcaster. Use this to show appreciation for content you find valuable or interesting."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "cast_hash": {
                    "type": "string",
                    "description": "The hash of the cast to like"
                }
            },
            "required": ["cast_hash"]
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """
        Execute the Farcaster like action.
        """
        logger.info(f"Executing tool '{self.name}' with params: {params}")

        # Get Farcaster observer through ServiceRegistry
        farcaster_observer = get_farcaster_observer(context)
        if not farcaster_observer:
            return create_error_response("Farcaster integration (observer) not configured.")

        # Extract and validate parameters
        cast_hash = params.get("cast_hash")

        if not cast_hash:
            return create_error_response("Missing required parameter for Farcaster like: cast_hash")

        # Check if we've already liked this cast
        if context.world_state_manager and context.world_state_manager.has_liked_cast(
            cast_hash
        ):
            error_msg = (
                f"Already liked cast {cast_hash}. Cannot like the same cast twice."
            )
            logger.warning(error_msg)
            return create_error_response(error_msg)

        try:
            # Use the observer's like_cast method
            result = await farcaster_observer.like_cast(cast_hash)
            logger.info(f"Farcaster observer like_cast returned: {result}")

            # Record this action in world state
            if context.world_state_manager:
                if result.get("success"):
                    context.world_state_manager.add_action_result(
                        action_type=self.name,
                        parameters={"cast_hash": cast_hash},
                        result="success",
                    )
                else:
                    context.world_state_manager.add_action_result(
                        action_type=self.name,
                        parameters={"cast_hash": cast_hash},
                        result=f"failure: {result.get('error', 'unknown')}",
                    )

            if result.get("success"):
                success_msg = f"Successfully liked Farcaster cast: {cast_hash}"
                logger.info(success_msg)

                return create_success_response(
                    success_msg,
                    cast_hash=cast_hash
                )
            else:
                error_msg = f"Failed to like Farcaster cast via observer: {result.get('error', 'unknown error')}"
                logger.error(error_msg)
                return create_error_response(error_msg)

        except Exception as e:
            error_msg = f"Error executing {self.name}: {str(e)}"
            logger.exception(error_msg)

            # Record this action failure in world state
            if context.world_state_manager:
                context.world_state_manager.add_action_result(
                    action_type=self.name,
                    parameters={"cast_hash": cast_hash},
                    result=f"failure: {str(e)}",
                )

            return create_error_response(error_msg)
