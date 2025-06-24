"""
Tool for quote casting on Farcaster.
"""
import logging
import time
from typing import Any, Dict

from ..base import ActionContext, ToolInterface
from ...utils.markdown_utils import strip_markdown
from .utils import get_farcaster_observer, create_error_response, create_success_response

logger = logging.getLogger(__name__)


class QuoteFarcasterPostTool(ToolInterface):
    """
    Tool for quote casting (reposting with commentary) on Farcaster.
    """

    @property
    def name(self) -> str:
        return "quote_farcaster_post"

    @property
    def description(self) -> str:
        return "Quote cast (repost with your own commentary) a specific cast on Farcaster. Use this to share someone's cast while adding your own thoughts or context."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Your commentary/thoughts to add to the quoted cast"
                },
                "quoted_cast_hash": {
                    "type": "string",
                    "description": "The hash of the cast to quote"
                },
                "channel": {
                    "type": "string",
                    "description": "The channel to post in (if not provided, posts to user's timeline)"
                }
            },
            "required": ["content", "quoted_cast_hash"]
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """
        Execute the Farcaster quote cast action.
        """
        logger.info(f"Executing tool '{self.name}' with params: {params}")

        # Get Farcaster observer through ServiceRegistry
        farcaster_observer = get_farcaster_observer(context)
        if not farcaster_observer:
            return create_error_response("Farcaster integration (observer) not configured.")

        # Extract and validate parameters
        content = params.get("content")
        quoted_cast_hash = params.get("quoted_cast_hash")
        channel = params.get("channel")  # Optional

        missing_params = []
        if not content:
            missing_params.append("content")
        if not quoted_cast_hash:
            missing_params.append("quoted_cast_hash")

        if missing_params:
            return create_error_response(f"Missing required parameters for Farcaster quote cast: {', '.join(missing_params)}")

        # Strip markdown formatting for Farcaster
        content = strip_markdown(str(content))

        # Check if we've already quoted this cast
        if context.world_state_manager and context.world_state_manager.has_quoted_cast(
            quoted_cast_hash
        ):
            error_msg = f"Already quoted cast {quoted_cast_hash}. Cannot quote the same cast twice."
            logger.warning(error_msg)
            return create_error_response(error_msg)

        try:
            # First, get the details of the cast to be quoted to retrieve the author's FID
            cast_details_result = await farcaster_observer.get_cast_details(quoted_cast_hash)
            if not cast_details_result.get("cast"):
                error_msg = f"Could not retrieve details for cast to be quoted: {quoted_cast_hash}"
                logger.error(error_msg)
                return create_error_response(error_msg)

            quoted_cast_author_fid = cast_details_result["cast"]["author"]["fid"]
            if not quoted_cast_author_fid:
                error_msg = f"Could not find author FID for cast {quoted_cast_hash}"
                logger.error(error_msg)
                return create_error_response(error_msg)

            # Use the observer's quote_cast method
            result = await farcaster_observer.quote_cast(
                content, quoted_cast_hash, quoted_cast_author_fid, channel
            )
            logger.info(f"Farcaster observer quote_cast returned: {result}")

            # Record this action in world state
            if context.world_state_manager:
                if result.get("success"):
                    cast_hash = result.get("cast", {}).get(
                        "hash", result.get("cast_hash", "unknown")
                    )
                    context.world_state_manager.add_action_result(
                        action_type=self.name,
                        parameters={
                            "content": content,
                            "quoted_cast_hash": quoted_cast_hash,
                            "channel": channel,
                            "cast_hash": cast_hash,
                        },
                        result="success",
                    )
                else:
                    context.world_state_manager.add_action_result(
                        action_type=self.name,
                        parameters={
                            "content": content,
                            "quoted_cast_hash": quoted_cast_hash,
                            "channel": channel,
                        },
                        result=f"failure: {result.get('error', 'unknown')}",
                    )

            if result.get("success"):
                cast_hash = result.get("cast_hash", "unknown")
                quoted_cast = result.get("quoted_cast", quoted_cast_hash)
                success_msg = f"Successfully posted quote cast (hash: {cast_hash}) quoting {quoted_cast}"
                logger.info(success_msg)

                return create_success_response(
                    success_msg,
                    cast_hash=cast_hash,
                    quoted_cast_hash=quoted_cast,
                    channel=channel,
                    sent_content=content  # For AI Blindness Fix
                )
            else:
                error_msg = f"Failed to post quote cast via observer: {result.get('error', 'unknown error')}"
                logger.error(error_msg)
                return create_error_response(error_msg)

        except Exception as e:
            error_msg = f"Error executing {self.name}: {str(e)}"
            logger.exception(error_msg)

            # Record this action failure in world state
            if context.world_state_manager:
                context.world_state_manager.add_action_result(
                    action_type=self.name,
                    parameters={
                        "content": content,
                        "quoted_cast_hash": quoted_cast_hash,
                        "channel": channel,
                    },
                    result=f"failure: {str(e)}",
                )

            return create_error_response(error_msg)
