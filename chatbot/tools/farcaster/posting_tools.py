"""
Farcaster posting and messaging tools.
"""
import logging
import time
from typing import Any, Dict

from ..base import ActionContext, ToolInterface
from ...utils.markdown_utils import strip_markdown

logger = logging.getLogger(__name__)


class SendFarcasterPostTool(ToolInterface):
    """
    Tool for sending new posts to Farcaster.
    """

    @property
    def name(self) -> str:
        return "send_farcaster_post"

    @property
    def description(self) -> str:
        return ("Send a new post (cast) to Farcaster. "
                "Use the 'attach_image' parameter to include an image - either provide a description to generate a new image, or reference an existing media_id from your library. "
                "Use the 'embed_url' parameter to attach media or frames. "
                "If no attach_image or embed_url is provided, recently generated media (within 5 minutes) will be automatically attached.")

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The text content of the cast to post"
                },
                "channel": {
                    "type": "string",
                    "description": "The channel to post in (if not provided, posts to user's timeline)"
                },
                "embed_url": {
                    "type": "string",
                    "description": "A URL to embed in the cast, such as an Arweave URL for an image/video page or a frame URL."
                },
                "attach_image": {
                    "type": "string",
                    "description": "Either a media_id from your library (e.g., 'media_img_1234567890') or a description to generate a new image (e.g., 'sunset over mountains')"
                },
                "media_id": {
                    "type": "string",
                    "description": "ID of previously generated media to attach (takes precedence over embed_url and attach_image)"
                }
            },
            "required": ["content"]
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """
        Execute the Farcaster post action using service-oriented approach.
        """
        logger.info(f"Executing tool '{self.name}' with params: {params}")

        # Enhanced service availability check with diagnostics
        social_service = context.get_social_service("farcaster")
        if not social_service:
            # Detailed diagnostic logging
            available_services = list(context.service_registry.keys()) if hasattr(context, 'service_registry') else []
            logger.error(f"Farcaster service not found in registry. Available services: {available_services}")
            return {
                "status": "failure", 
                "error": "Farcaster service not found in service registry",
                "diagnostic_info": {
                    "available_services": available_services,
                    "registry_status": "empty" if not available_services else "populated"
                },
                "timestamp": time.time()
            }
        
        # Test service availability with detailed error reporting
        try:
            is_available = await social_service.is_available()
            if not is_available:
                # Get detailed service status
                service_status = getattr(social_service, 'get_status', lambda: {})()
                logger.error(f"Farcaster service unavailable. Status: {service_status}")
                return {
                    "status": "failure", 
                    "error": "Farcaster service is not available",
                    "service_status": service_status,
                    "timestamp": time.time()
                }
        except Exception as availability_error:
            logger.error(f"Error checking Farcaster service availability: {availability_error}", exc_info=True)
            return {
                "status": "failure",
                "error": f"Farcaster service availability check failed: {str(availability_error)}",
                "timestamp": time.time()
            }

        # Extract and validate parameters
        content = params.get("content", "")
        channel = params.get("channel")  # Optional
        embed_url = params.get("embed_url")  # Optional
        attach_image = params.get("attach_image")  # New: either media_id or description
        media_id = params.get("media_id")  # Optional - takes precedence over all

        # Handle attach_image parameter: could be media_id or description
        generated_image_info = None
        if attach_image and not media_id:  # Only if media_id not explicitly provided
            # Check if it's a media_id (starts with "media_")
            if attach_image.startswith("media_"):
                # It's a media_id, treat it as such
                media_id = attach_image
                logger.info(f"Using attach_image as media_id: {media_id}")
            else:
                # It's a description, generate new image
                from ..message_enhancement import generate_image_from_description
                generated_image_info = await generate_image_from_description(attach_image, context)
                if generated_image_info:
                    embed_url = generated_image_info["image_url"]
                    logger.info(f"Generated new image from description: '{attach_image}' -> {embed_url}")
                else:
                    logger.warning(f"Failed to generate image from description: {attach_image}")

        # Handle explicit media_id (takes precedence over embed_url)
        if media_id and context.world_state_manager:
            # Retrieve media URL from world state using media_id
            media_url = context.world_state_manager.get_media_url_by_id(media_id)
            if media_url:
                embed_url = media_url
                logger.info(f"Using media_id {media_id} resolved to URL: {media_url}")
            else:
                logger.warning(f"Media ID {media_id} not found in world state")

        # Allow empty content only if we have embed to attach
        if not content and not embed_url:
            error_msg = "Missing required parameter 'content' for Farcaster post (content required when no embed is attached)"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}
        
        # Generate minimal content for embed-only posts
        if not content and embed_url:
            content = "📎"  # Simple emoji for embed posts

        # Strip markdown formatting for Farcaster
        content = strip_markdown(content)

        # Truncate content if too long for Farcaster
        MAX_FARCASTER_CONTENT_LENGTH = 320
        if len(content) > MAX_FARCASTER_CONTENT_LENGTH:
            content = content[:MAX_FARCASTER_CONTENT_LENGTH - 3] + "..."
            logger.warning(f"Farcaster content truncated to {MAX_FARCASTER_CONTENT_LENGTH} chars.")

        # Auto-attachment: Check for recently generated media if no embed_url provided
        if not embed_url and context.world_state_manager:
            recent_media_url = context.world_state_manager.get_last_generated_media_url()
            if recent_media_url:
                # Check if the media was generated recently (within last 5 minutes)
                if hasattr(context.world_state_manager.state, 'generated_media_library'):
                    media_library = context.world_state_manager.state.generated_media_library
                    if media_library:
                        last_media = media_library[-1]
                        media_age = time.time() - last_media.get('timestamp', 0)
                        if media_age <= 300:  # 5 minutes
                            embed_url = recent_media_url
                            logger.info(f"Auto-attaching recently generated media to Farcaster post: {embed_url}")

        # Create post using service
        try:
            result = await social_service.create_post(
                content=content,
                embed_urls=[embed_url] if embed_url else [],
                parent_url=None  # TODO: Add reply support to schema
            )

            # Enhanced success response formatting for better AI understanding
            if result.get("status") == "success":
                cast_hash = result.get("cast_hash", "unknown")
                success_msg = f"✅ Successfully posted to Farcaster! Cast hash: {cast_hash}"
                
                if embed_url:
                    success_msg += f" (with media: {embed_url})"
                
                logger.info(success_msg)
                
                # Record this action in world state if successful
                if context.world_state_manager:
                    context.world_state_manager.add_action_result(
                        action_type=self.name,
                        parameters={
                            "content": content,
                            "channel": channel,
                            "embed_url": embed_url,
                        },
                        result="success",
                    )
                
                return {
                    "status": "success",
                    "message": success_msg,
                    "cast_hash": cast_hash,
                    "content_posted": content,
                    "media_attached": embed_url if embed_url else None,
                    "farcaster_url": f"https://warpcast.com/{settings.FARCASTER_BOT_USERNAME or 'unknown'}/{cast_hash}" if cast_hash != "unknown" else None,
                    "timestamp": time.time()
                }
            else:
                # Enhanced failure response
                error_detail = result.get("error", "Unknown error occurred")
                failure_msg = f"❌ Farcaster post failed: {error_detail}"
                logger.error(failure_msg)
                
                # Record this action in world state if failed
                if context.world_state_manager:
                    context.world_state_manager.add_action_result(
                        action_type=self.name,
                        parameters={
                            "content": content,
                            "channel": channel,
                            "embed_url": embed_url,
                        },
                        result=f"failure: {error_detail}",
                    )
                
                return {
                    "status": "failure", 
                    "error": failure_msg,
                    "details": result,
                    "timestamp": time.time()
                }

        except Exception as e:
            error_msg = f"Error creating Farcaster post: {e}"
            logger.exception(error_msg)
            
            # Record this error in world state
            if context.world_state_manager:
                context.world_state_manager.add_action_result(
                    action_type=self.name,
                    parameters={
                        "content": content,
                        "channel": channel,
                        "embed_url": embed_url,
                    },
                    result=f"failure: {error_msg}",
                )
            
            return {
                "status": "failure",
                "error": error_msg,
                "timestamp": time.time(),
            }


class SendFarcasterReplyTool(ToolInterface):
    """
    Tool for replying to specific casts on Farcaster.
    """

    @property
    def name(self) -> str:
        return "send_farcaster_reply"

    @property
    def description(self) -> str:
        return "Reply to a specific cast on Farcaster. Use this when you want to respond directly to someone's cast."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The text content of the reply"
                },
                "reply_to_hash": {
                    "type": "string",
                    "description": "The hash of the cast to reply to"
                }
            },
            "required": ["content", "reply_to_hash"]
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """
        Execute the Farcaster reply action using service-oriented approach.
        """
        logger.info(f"Executing tool '{self.name}' with params: {params}")

        # Get Farcaster service from service registry
        social_service = context.get_social_service("farcaster")
        if not social_service or not await social_service.is_available():
            error_msg = "Farcaster service is not available."
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Extract and validate parameters
        content = params.get("content")
        reply_to_hash = params.get("reply_to_hash")

        missing_params = []
        if not content:
            missing_params.append("content")
        if not reply_to_hash:
            missing_params.append("reply_to_hash")

        if missing_params:
            error_msg = f"Missing required parameters for Farcaster reply: {', '.join(missing_params)}"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Strip markdown formatting for Farcaster
        content = strip_markdown(content)

        # Truncate content if too long for Farcaster
        MAX_FARCASTER_CONTENT_LENGTH = 320
        if len(content) > MAX_FARCASTER_CONTENT_LENGTH:
            content = content[:MAX_FARCASTER_CONTENT_LENGTH - 3] + "..."
            logger.warning(f"Farcaster reply content truncated to {MAX_FARCASTER_CONTENT_LENGTH} chars.")

        # Check if we've already replied to this cast
        if (
            context.world_state_manager
            and context.world_state_manager.has_replied_to_cast(reply_to_hash)
        ):
            error_msg = f"Already replied to cast {reply_to_hash}. Cannot reply to the same cast twice."
            logger.warning(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        try:
            # Use service's reply method
            result = await social_service.reply_to_post(content, reply_to_hash)
            logger.info(f"Farcaster service reply_to_post returned: {result}")

            # Enhanced success response formatting for better AI understanding
            if result.get("status") == "success":
                reply_hash = result.get("reply_hash", "unknown")
                success_msg = f"✅ Successfully replied to Farcaster cast {reply_to_hash}! Reply hash: {reply_hash}"
                logger.info(success_msg)
                
                # Record this action in world state for duplicate prevention
                if context.world_state_manager:
                    context.world_state_manager.add_action_result(
                        action_type=self.name,
                        parameters={
                            "content": content,
                            "reply_to_hash": reply_to_hash,
                            "reply_hash": reply_hash,
                        },
                        result="success",
                    )
                
                return {
                    "status": "success",
                    "message": success_msg,
                    "reply_hash": reply_hash,
                    "parent_hash": reply_to_hash,
                    "content_posted": content,
                    "farcaster_url": f"https://warpcast.com/{settings.FARCASTER_BOT_USERNAME or 'unknown'}/{reply_hash}" if reply_hash != "unknown" else None,
                    "timestamp": time.time()
                }
            else:
                # Enhanced failure response
                error_detail = result.get("error", "Unknown error occurred")
                failure_msg = f"❌ Failed to reply to Farcaster cast {reply_to_hash}: {error_detail}"
                logger.error(failure_msg)
                
                # Record this action in world state for duplicate prevention
                if context.world_state_manager:
                    context.world_state_manager.add_action_result(
                        action_type=self.name,
                        parameters={"content": content, "reply_to_hash": reply_to_hash},
                        result=f"failure: {error_detail}",
                    )
                
                return {
                    "status": "failure",
                    "error": failure_msg,
                    "details": result,
                    "timestamp": time.time(),
                }
        except Exception as e:
            error_msg = f"Error executing send_farcaster_reply: {e}"
            logger.exception(error_msg)

            # Record this action failure in world state
            if context.world_state_manager:
                context.world_state_manager.add_action_result(
                    action_type=self.name,
                    parameters={"content": content, "reply_to_hash": reply_to_hash},
                    result=f"failure: {str(e)}",
                )

            return {"status": "failure", "error": error_msg, "timestamp": time.time()}


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
        Execute the Farcaster quote cast action using service-oriented approach.
        """
        logger.info(f"Executing tool '{self.name}' with params: {params}")

        # Get Farcaster service from service registry
        social_service = context.get_social_service("farcaster")
        if not social_service or not await social_service.is_available():
            error_msg = "Farcaster service is not available."
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

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
            error_msg = f"Missing required parameters for Farcaster quote cast: {', '.join(missing_params)}"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Strip markdown formatting for Farcaster
        content = strip_markdown(content)

        # Check if we've already quoted this cast
        if context.world_state_manager and context.world_state_manager.has_quoted_cast(
            quoted_cast_hash
        ):
            error_msg = f"Already quoted cast {quoted_cast_hash}. Cannot quote the same cast twice."
            logger.warning(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        try:
            # For now, use create_post with parent_url as quote functionality
            # TODO: Implement proper quote functionality in service layer
            result = await social_service.create_post(
                content=f"{content}",  # Quote content
                embed_urls=[],
                parent_url=quoted_cast_hash  # This acts as a quote reference
            )
            logger.info(f"Farcaster service create_post (quote) returned: {result}")

            # Record this action in world state
            if context.world_state_manager:
                if result.get("status") == "success":
                    cast_hash = result.get("cast_hash", "unknown")
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

            if result.get("status") == "success":
                cast_hash = result.get("cast_hash", "unknown")
                success_msg = f"Successfully posted quote cast (hash: {cast_hash}) quoting {quoted_cast_hash}"
                logger.info(success_msg)

                return {
                    "status": "success",
                    "message": success_msg,
                    "cast_hash": cast_hash,
                    "quoted_cast_hash": quoted_cast_hash,
                    "channel": channel,
                    "sent_content": content,  # For AI Blindness Fix
                    "timestamp": time.time(),
                }
            else:
                error_msg = f"Failed to post quote cast via service: {result.get('error', 'unknown error')}"
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
                    parameters={
                        "content": content,
                        "quoted_cast_hash": quoted_cast_hash,
                        "channel": channel,
                    },
                    result=f"failure: {str(e)}",
                )

            return {"status": "failure", "error": error_msg, "timestamp": time.time()}


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
        
        # Get Farcaster service from service registry for consistency 
        social_service = context.get_social_service("farcaster")
        if not social_service or not await social_service.is_available():
            error_msg = "Farcaster service is not available."
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}
            
        return {
            "status": "failure", 
            "error": "Farcaster DM functionality is not supported by the API", 
            "timestamp": time.time()
        }
