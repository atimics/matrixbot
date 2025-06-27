"""
Tool for deleting Farcaster reactions.
"""
import logging
from typing import Any, Dict

from ..base import ActionContext, ToolInterface
from .utils import get_farcaster_observer, create_error_response, create_success_response

logger = logging.getLogger(__name__)


class DeleteFarcasterReactionTool(ToolInterface):
    """
    Tool for deleting a reaction (like/recast) from a Farcaster post.
    """

    @property
    def name(self) -> str:
        return "delete_farcaster_reaction"

    @property
    def description(self) -> str:
        return "Delete a reaction (like or recast) from a Farcaster cast. Use this to remove a like or recast you previously made."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "cast_hash": {
                    "type": "string",
                    "description": "The hash of the cast to remove reaction from"
                }
            },
            "required": ["cast_hash"]
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """
        Execute the Farcaster delete reaction action.
        """
        logger.info(f"Executing tool '{self.name}' with params: {params}")

        # Get Farcaster observer through ServiceRegistry
        farcaster_observer = get_farcaster_observer(context)
        if not farcaster_observer:
            return create_error_response("Farcaster integration (observer) not configured.")

        # Extract and validate parameters
        cast_hash = params.get("cast_hash")

        if not cast_hash:
            return create_error_response("Missing required parameter 'cast_hash' for Farcaster reaction delete")

        try:
            # Use the observer's delete_reaction method
            result = await farcaster_observer.delete_reaction(cast_hash)
            logger.info(f"Farcaster observer delete_reaction returned: {result}")

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
                success_msg = f"Successfully deleted reaction from Farcaster cast: {cast_hash}"
                logger.info(success_msg)
                return create_success_response(success_msg, cast_hash=cast_hash)
            else:
                error_msg = f"Failed to delete reaction from Farcaster cast: {result.get('error', 'unknown error')}"
                logger.error(error_msg)
                return create_error_response(error_msg, cast_hash=cast_hash)

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
