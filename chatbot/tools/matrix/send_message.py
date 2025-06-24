"""
Send Matrix Message Tool - Unified Messaging for Matrix

This tool consolidates the functionality of both regular messages and replies,
eliminating the need for separate tools and simplifying the AI's decision space.
Uses ServiceRegistry abstraction for clean platform integration.

Parameter Consistency Note:
- Uses 'channel_id' as the primary parameter name for specifying target rooms
- Accepts both 'channel_id' and 'room_id' for LLM tolerance (common confusion source)
- Parameter description avoids "Matrix room ID" phrase to prevent LLM confusion
- This follows the project-wide standard of using 'channel_id' for platform-agnostic channel targeting
"""

import logging
import time
from typing import Any, Dict

from ...config import settings
from ...utils.markdown_utils import format_for_matrix
from ..base import ActionContext, ToolInterface

logger = logging.getLogger(__name__)


class SendMatrixMessageTool(ToolInterface):
    """
    Unified tool for sending messages and replies to Matrix channels.
    
    This tool consolidates the functionality of both regular messages and replies,
    eliminating the need for separate tools and simplifying the AI's decision space.
    Uses ServiceRegistry for clean platform abstraction.
    """

    @property
    def name(self) -> str:
        return "send_matrix_message"

    @property
    def description(self) -> str:
        return ("Send a message to a Matrix channel using turn-based conversation logic. "
                "CRITICAL: For replies, the bot can only respond when it's the bot's turn in the conversation. "
                "The system automatically tracks whose turn it is to prevent feedback loops and maintain natural conversation flow. "
                "If reply_to_id is provided, the system validates that it's the bot's turn before allowing the reply. "
                "Recently generated media (within 5 minutes) will be automatically attached as a separate image message if no explicit image_url is provided.")

    @property
    def access_level(self) -> str:
        return 'conversational'

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "channel_id": "string - The unique identifier of the Matrix room where the message should be sent",
            "content": "string - The message content to send (supports markdown formatting)",
            "reply_to_id": "string (optional) - The event ID of the message to reply to. If provided, sends as a reply",
            "format_as_markdown": "boolean (optional, default: true) - Whether to format the content as markdown",
            "image_url": "string (optional) - URL of an image to attach. If not provided, recently generated media will be auto-attached",
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """
        Execute the Matrix message action using ServiceRegistry.
        """
        logger.info(f"Executing tool '{self.name}' with params: {params}")

        # Get Matrix messaging service from registry
        matrix_service = context.service_registry.get_messaging_service("matrix")
        if not matrix_service:
            error_msg = "Matrix messaging service not available in ServiceRegistry."
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Extract and validate parameters
        # Accept both 'channel_id' and 'room_id' for better LLM tolerance
        # This prevents errors when LLMs use 'room_id' based on the Matrix context
        room_id = params.get("channel_id") or params.get("room_id")
        content = params.get("content")
        reply_to_event_id = params.get("reply_to_id")
        format_as_markdown = params.get("format_as_markdown", True)
        image_url = params.get("image_url")

        missing_params = []
        if not room_id:
            missing_params.append("channel_id")
        if not content:
            missing_params.append("content")

        if missing_params:
            error_msg = f"Missing required parameters for Matrix message: {', '.join(missing_params)}"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Type assertions for safety
        content = str(content)
        room_id = str(room_id)

        # Deduplication check for replies: prevent replying outside of turn-based conversations
        if reply_to_event_id and context.world_state_manager:
            # Check if it's the bot's turn in this conversation thread
            thread_id = reply_to_event_id  # For Matrix, the reply target becomes the thread ID
            
            if not context.world_state_manager.is_bot_turn_in_thread(thread_id):
                warning_msg = f"Matrix reply blocked: Not the bot's turn in thread {thread_id}. Maintaining natural conversation flow."
                logger.warning(warning_msg)
                return {
                    "status": "blocked",
                    "message": warning_msg,
                    "event_id": reply_to_event_id,
                    "room_id": room_id,
                    "reason": "not_bot_turn",
                    "timestamp": time.time(),
                }
            
            logger.info(f"Matrix thread turn validation PASSED: Bot's turn to speak in thread {thread_id}")

        # Auto-attachment: Check for recently generated media if no image_url provided
        if not image_url and context.world_state_manager:
            recent_media_url = context.world_state_manager.get_last_generated_media_url()
            if recent_media_url:
                # Check if the media was generated recently (within last 5 minutes)
                if hasattr(context.world_state_manager.state, 'generated_media_library'):
                    media_library = context.world_state_manager.state.generated_media_library
                    if media_library:
                        last_media = media_library[-1]
                        media_age = time.time() - last_media.get('timestamp', 0)
                        if media_age <= 300:  # 5 minutes
                            image_url = recent_media_url
                            logger.info(f"Auto-attaching recently generated media to Matrix message: {image_url}")

        try:
            # Handle reply vs regular message using ServiceRegistry
            if reply_to_event_id:
                # This is a reply
                result = await matrix_service.send_reply(
                    room_id, content, reply_to_event_id, 
                    format_as_markdown=format_as_markdown
                )
            else:
                # This is a regular message
                result = await matrix_service.send_message(
                    room_id, content, 
                    format_as_markdown=format_as_markdown
                )

            logger.info(f"Matrix service returned: {result}")

            if result.get("success"):
                event_id = result.get("event_id", "unknown")
                action_type = "reply" if reply_to_event_id else "message"
                success_msg = f"Sent Matrix {action_type} to {room_id} (event: {event_id})"
                logger.info(success_msg)

                # Record the sent message in world state for AI blindness fix
                if context.world_state_manager:
                    from ...core.world_state.structures import Message
                    bot_message = Message(
                        id=event_id,
                        channel_id=room_id,
                        channel_type="matrix",
                        sender=settings.matrix.user_id or "unknown",
                        content=content,
                        timestamp=time.time(),
                        reply_to=reply_to_event_id  # Set if this is a reply
                    )
                    context.world_state_manager.add_message(room_id, bot_message)
                    logger.debug(f"Recorded sent Matrix {action_type} in world state: {event_id}")

                # Record the sent message in context manager for AI blindness fix
                if context.context_manager:
                    assistant_message = {
                        "content": content,
                        "sender": settings.matrix.user_id or "unknown",
                        "timestamp": time.time(),
                        "event_id": event_id,
                        "channel_type": "matrix",
                        "type": "assistant"
                    }
                    try:
                        await context.context_manager.add_assistant_message(room_id, assistant_message)
                        logger.debug(f"Recorded sent Matrix {action_type} in context manager: {event_id}")
                    except Exception as e:
                        logger.warning(f"Failed to record message in context manager: {e}")

                # Send auto-attached image if available
                image_event_id = None
                if image_url:
                    try:
                        image_result = await matrix_service.send_image(
                            room_id, image_url, caption=None, filename=None
                        )
                        if image_result.get("success"):
                            image_event_id = image_result.get("event_id", "unknown")
                            logger.info(f"Auto-attached image to Matrix {action_type}: {image_event_id}")
                        else:
                            logger.warning(f"Failed to auto-attach image: {image_result.get('error', 'unknown error')}")
                    except Exception as e:
                        logger.warning(f"Error auto-attaching image: {e}")

                return {
                    "status": "success",
                    "message": success_msg,
                    "event_id": event_id,
                    "room_id": room_id,
                    "reply_to_event_id": reply_to_event_id,
                    "sent_content": content,  # For AI Blindness Fix
                    "auto_attached_image": image_url if image_url else None,
                    "image_event_id": image_event_id,
                    "timestamp": time.time(),
                }
            else:
                action_type = "reply" if reply_to_event_id else "message"
                error_msg = f"Failed to send Matrix {action_type} via service: {result.get('error', 'unknown error')}"
                logger.error(error_msg)
                return {
                    "status": "failure",
                    "error": error_msg,
                    "timestamp": time.time(),
                }

        except Exception as e:
            error_msg = f"Error executing {self.name}: {str(e)}"
            logger.exception(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}
