"""
Farcaster management tools (delete posts, etc.).
"""
import logging
import time
from typing import Any, Dict

from ..base import ActionContext, ToolInterface

logger = logging.getLogger(__name__)


class DeleteFarcasterPostTool(ToolInterface):
    """
    Tool for deleting a Farcaster post (cast) by hash.
    """

    @property
    def name(self) -> str:
        return "delete_farcaster_post"

    @property
    def description(self) -> str:
        return "Delete a Farcaster cast by its hash. Use this to remove a post you previously made."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "cast_hash": {
                    "type": "string",
                    "description": "The hash of the cast to delete"
                }
            },
            "required": ["cast_hash"]
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """
        Execute the Farcaster delete cast action using service-oriented approach.
        """
        logger.debug(f"Executing tool '{self.name}' with params: {params}")

        # Get Farcaster service from service registry
        social_service = context.get_social_service("farcaster")
        if not social_service or not await social_service.is_available():
            error_msg = "Farcaster service is not available."
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Extract and validate parameters
        cast_hash = params.get("cast_hash")

        if not cast_hash:
            error_msg = "Missing required parameter 'cast_hash' for Farcaster delete"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        try:
            # Use the service's delete_post method
            result = await social_service.delete_post(cast_hash)
            logger.debug(f"Farcaster service delete_post returned: {result}")

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
                success_msg = f"Successfully deleted Farcaster cast: {cast_hash}"
                logger.debug(success_msg)
                return {
                    "status": "success",
                    "message": success_msg,
                    "cast_hash": cast_hash,
                    "timestamp": time.time(),
                }
            else:
                error_msg = f"Failed to delete Farcaster cast: {result.get('error', 'unknown error')}"
                logger.error(error_msg)
                return {
                    "status": "failure",
                    "error": error_msg,
                    "cast_hash": cast_hash,
                    "timestamp": time.time(),
                }

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

            return {"status": "failure", "error": error_msg, "timestamp": time.time()}
