"""
Farcaster engagement tools (likes, follows, reactions).
"""
import logging
import time
from typing import Any, Dict

from ..base import ActionContext, ToolInterface

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
        Execute the Farcaster like action using service-oriented approach.
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
            error_msg = "Missing required parameter for Farcaster like: cast_hash"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Check if we've already liked this cast (local state check)
        if context.world_state_manager and context.world_state_manager.has_liked_cast(
            cast_hash
        ):
            warning_msg = f"Already liked cast {cast_hash}. Cannot like the same cast twice."
            logger.warning(warning_msg)
            return {
                "status": "skipped",
                "message": warning_msg,
                "cast_hash": cast_hash,
                "reason": "already_liked_local",
                "timestamp": time.time()
            }

        # Authoritative pre-condition check using Farcaster service
        social_service = context.get_social_service("farcaster")
        if social_service and await social_service.is_available():
            try:
                has_liked = await social_service.has_liked_post(cast_hash)
                if has_liked:
                    warning_msg = f"Authoritative check confirms we have already liked cast {cast_hash}"
                    logger.warning(warning_msg)
                    return {
                        "status": "skipped",
                        "message": warning_msg,
                        "cast_hash": cast_hash,
                        "reason": "already_liked_authoritative",
                        "timestamp": time.time()
                    }
            except Exception as e:
                logger.warning(f"Could not perform authoritative like check for cast {cast_hash}: {e}")

        try:
            # Use the service's react method
            result = await social_service.react_to_post(cast_hash, "like")
            logger.debug(f"Farcaster service react_to_post returned: {result}")

            # Record this action in world state
            if context.world_state_manager:
                if result.get("status") == "success":
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

            if result.get("status") == "success":
                success_msg = f"Successfully liked Farcaster cast: {cast_hash}"
                logger.debug(success_msg)

                return {
                    "status": "success",
                    "message": success_msg,
                    "cast_hash": cast_hash,
                    "timestamp": time.time(),
                }
            else:
                error_msg = f"Failed to like Farcaster cast: {result.get('error', 'unknown error')}"
                logger.error(error_msg)
                return {
                    "status": "failure",
                    "error": error_msg,
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
        logger.debug(f"Executing tool '{self.name}' with params: {params}")
        
        # Get Farcaster service from service registry
        social_service = context.get_social_service("farcaster")
        if not social_service or not await social_service.is_available():
            error_msg = "Farcaster service is not available."
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}
            
        fid = params.get("fid")
        if fid is None:
            err = "Missing required parameter: fid"
            logger.error(err)
            return {"status": "failure", "error": err, "timestamp": time.time()}
        
        # Enhanced idempotency check: verify if we're already following this user
        if context.world_state_manager and context.world_state_manager.is_following_user(fid):
            warning_msg = f"Already following user {fid}. Cannot follow the same user twice."
            logger.warning(warning_msg)
            return {
                "status": "skipped",
                "message": warning_msg,
                "fid": fid,
                "reason": "already_following",
                "timestamp": time.time()
            }
        
        # Authoritative pre-condition check using Farcaster service
        social_service = context.get_social_service("farcaster")
        if social_service and await social_service.is_available():
            try:
                is_following = await social_service.is_following_user(fid)
                if is_following:
                    warning_msg = f"Authoritative check confirms we are already following user {fid}"
                    logger.warning(warning_msg)
                    return {
                        "status": "skipped",
                        "message": warning_msg,
                        "fid": fid,
                        "reason": "already_following_authoritative",
                        "timestamp": time.time()
                    }
            except Exception as e:
                logger.warning(f"Could not perform authoritative follow check for user {fid}: {e}")
            
        # Use service method to follow user
        result = await social_service.follow_user(fid)
        
        # Record this action in world state
        if context.world_state_manager:
            if result.get("success"):
                context.world_state_manager.add_action_result(
                    action_type=self.name,
                    parameters={"fid": fid},
                    result="success",
                )
            else:
                context.world_state_manager.add_action_result(
                    action_type=self.name,
                    parameters={"fid": fid},
                    result=f"failure: {result.get('error', 'unknown')}",
                )
        
        if result.get("success"):
            success_msg = f"Successfully followed Farcaster user: {fid}"
            logger.debug(success_msg)
            return {
                "status": "success",
                "message": success_msg,
                "fid": fid,
                "timestamp": time.time()
            }
        
        error_msg = f"Failed to follow Farcaster user: {result.get('error', 'unknown error')}"
        logger.error(error_msg)
        return {
            "status": "failure",
            "error": error_msg,
            "fid": fid,
            "timestamp": time.time()
        }


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
        logger.debug(f"Executing tool '{self.name}' with params: {params}")
        
        # Get Farcaster service from service registry
        social_service = context.get_social_service("farcaster")
        if not social_service or not await social_service.is_available():
            error_msg = "Farcaster service is not available."
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}
            
        fid = params.get("fid")
        if fid is None:
            err = "Missing required parameter: fid"
            logger.error(err)
            return {"status": "failure", "error": err, "timestamp": time.time()}
            
        # Use service method to unfollow user
        result = await social_service.unfollow_user(fid)
        if result.get("success"):
            return {"status": "success", "fid": fid, "timestamp": time.time()}
        return {
            "status": "failure",
            "error": result.get("error"),
            "timestamp": time.time(),
        }


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
        Execute the Farcaster delete reaction action using service-oriented approach.
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
            error_msg = "Missing required parameter 'cast_hash' for Farcaster reaction delete"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        try:
            # Use the service's delete_reaction method
            result = await social_service.delete_reaction(cast_hash)
            logger.debug(f"Farcaster service delete_reaction returned: {result}")

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
                logger.debug(success_msg)
                return {
                    "status": "success",
                    "message": success_msg,
                    "cast_hash": cast_hash,
                    "timestamp": time.time(),
                }
            else:
                error_msg = f"Failed to delete reaction from Farcaster cast: {result.get('error', 'unknown error')}"
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
