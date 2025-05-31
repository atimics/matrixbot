"""
Matrix platform-specific tools.
"""
import logging
import time
from typing import Any, Dict

from .base import ActionContext, ToolInterface

logger = logging.getLogger(__name__)


class SendMatrixReplyTool(ToolInterface):
    """
    Tool for sending replies to specific messages in Matrix channels.
    """
    
    @property
    def name(self) -> str:
        return "send_matrix_reply"
        
    @property
    def description(self) -> str:
        return "Reply to a specific message in a Matrix channel. Use this when you want to respond directly to someone's message."
        
    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "channel_id": "string (Matrix room ID) - The room where the reply should be sent",
            "content": "string - The message content to send as a reply",
            "reply_to_id": "string - The event ID of the message to reply to"
        }
        
    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        """
        Execute the Matrix reply action.
        """
        logger.info(f"Executing tool '{self.name}' with params: {params}")
        
        # Check if Matrix integration is available
        if not context.matrix_observer:
            error_msg = "Matrix integration (observer) not configured."
            logger.error(error_msg)
            return {
                "status": "failure",
                "error": error_msg,
                "timestamp": time.time()
            }
            
        # Extract and validate parameters
        room_id = params.get("channel_id")
        content = params.get("content")
        reply_to_event_id = params.get("reply_to_id")
        
        missing_params = []
        if not room_id:
            missing_params.append("channel_id")
        if not content:
            missing_params.append("content")
        if not reply_to_event_id:
            missing_params.append("reply_to_id")
            
        if missing_params:
            error_msg = f"Missing required parameters for Matrix reply: {', '.join(missing_params)}"
            logger.error(error_msg)
            return {
                "status": "failure",
                "error": error_msg,
                "timestamp": time.time()
            }
            
        try:
            # Use the observer's send_reply method for low-level interaction
            result = await context.matrix_observer.send_reply(room_id, content, reply_to_event_id)
            logger.info(f"Matrix observer send_reply returned: {result}")
            
            if result.get("success"):
                event_id = result.get("event_id", "unknown")
                success_msg = f"Sent Matrix reply to {room_id} (event: {event_id})"
                logger.info(success_msg)
                
                return {
                    "status": "success",
                    "message": success_msg,
                    "event_id": event_id,
                    "room_id": room_id,
                    "reply_to_event_id": reply_to_event_id,
                    "sent_content": content,  # For AI Blindness Fix
                    "timestamp": time.time()
                }
            else:
                error_msg = f"Failed to send Matrix reply via observer: {result.get('error', 'unknown error')}"
                logger.error(error_msg)
                return {
                    "status": "failure",
                    "error": error_msg,
                    "timestamp": time.time()
                }
                
        except Exception as e:
            error_msg = f"Error executing {self.name}: {str(e)}"
            logger.exception(error_msg)
            return {
                "status": "failure",
                "error": error_msg,
                "timestamp": time.time()
            }


class SendMatrixMessageTool(ToolInterface):
    """
    Tool for sending new messages to Matrix channels.
    """
    
    @property
    def name(self) -> str:
        return "send_matrix_message"
        
    @property
    def description(self) -> str:
        return "Send a new message to a Matrix channel. Use this when you want to start a new conversation or make an announcement."
        
    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "channel_id": "string (Matrix room ID) - The room where the message should be sent",
            "content": "string - The message content to send"
        }
        
    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        """
        Execute the Matrix message action.
        """
        logger.info(f"Executing tool '{self.name}' with params: {params}")
        
        # Check if Matrix integration is available
        if not context.matrix_observer:
            error_msg = "Matrix integration (observer) not configured."
            logger.error(error_msg)
            return {
                "status": "failure",
                "error": error_msg,
                "timestamp": time.time()
            }
            
        # Extract and validate parameters
        room_id = params.get("channel_id")
        content = params.get("content")
        
        missing_params = []
        if not room_id:
            missing_params.append("channel_id")
        if not content:
            missing_params.append("content")
            
        if missing_params:
            error_msg = f"Missing required parameters for Matrix message: {', '.join(missing_params)}"
            logger.error(error_msg)
            return {
                "status": "failure",
                "error": error_msg,
                "timestamp": time.time()
            }
            
        try:
            # Use the observer's send_message method for low-level interaction
            result = await context.matrix_observer.send_message(room_id, content)
            logger.info(f"Matrix observer send_message returned: {result}")
            
            if result.get("success"):
                event_id = result.get("event_id", "unknown")
                success_msg = f"Sent Matrix message to {room_id} (event: {event_id})"
                logger.info(success_msg)
                
                return {
                    "status": "success",
                    "message": success_msg,
                    "event_id": event_id,
                    "room_id": room_id,
                    "sent_content": content,  # For AI Blindness Fix
                    "timestamp": time.time()
                }
            else:
                error_msg = f"Failed to send Matrix message via observer: {result.get('error', 'unknown error')}"
                logger.error(error_msg)
                return {
                    "status": "failure",
                    "error": error_msg,
                    "timestamp": time.time()
                }
                
        except Exception as e:
            error_msg = f"Error executing {self.name}: {str(e)}"
            logger.exception(error_msg)
            return {
                "status": "failure",
                "error": error_msg,
                "timestamp": time.time()
            }
