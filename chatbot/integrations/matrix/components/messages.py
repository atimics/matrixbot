"""
Matrix Message Operations

Handles sending messages, replies, formatted content, and images to Matrix rooms.
"""

import asyncio
import logging
import mimetypes
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import httpx
from nio import AsyncClient, RoomSendError, RoomSendResponse

logger = logging.getLogger(__name__)


class MatrixMessageOperations:
    """Handles Matrix message sending operations."""
    
    def __init__(self, client: AsyncClient, user_id: str):
        self.client = client
        self.user_id = user_id
    
    async def send_message(self, room_id: str, content: str) -> Dict[str, Any]:
        """Send a plain text message to a room."""
        try:
            if not self.client:
                return {"success": False, "error": "Matrix client not available"}
            
            # Ensure content is always a string
            if not isinstance(content, str):
                content = str(content)
            
            response = await self.client.room_send(
                room_id=room_id,
                message_type="m.room.message",
                content={
                    "msgtype": "m.text",
                    "body": content
                }
            )
            
            if isinstance(response, RoomSendResponse):
                logger.debug(f"MatrixMessageOps: Message sent to {room_id}: {content[:100]}...")
                return {
                    "success": True,
                    "event_id": response.event_id,
                    "room_id": room_id
                }
            else:
                error_msg = f"Failed to send message: {response}"
                logger.error(f"MatrixMessageOps: {error_msg}")
                return {"success": False, "error": error_msg}
                
        except Exception as e:
            error_msg = f"Error sending message to {room_id}: {e}"
            logger.error(f"MatrixMessageOps: {error_msg}")
            return {"success": False, "error": error_msg}
    
    async def send_reply(
        self,
        room_id: str,
        reply_to_event_id: str,
        content: str,
        original_sender: Optional[str] = None,
        original_content: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send a reply to a specific message."""
        try:
            if not self.client:
                return {"success": False, "error": "Matrix client not available"}
            
            # Ensure content is always a string
            if not isinstance(content, str):
                content = str(content)
            
            # Construct reply content with fallback body
            fallback_body = f"> <{original_sender or 'unknown'}> {original_content or 'message'}\n\n{content}"
            
            reply_content = {
                "msgtype": "m.text",
                "body": fallback_body,
                "m.relates_to": {
                    "m.in_reply_to": {
                        "event_id": reply_to_event_id
                    }
                }
            }
            
            response = await self.client.room_send(
                room_id=room_id,
                message_type="m.room.message",
                content=reply_content
            )
            
            if isinstance(response, RoomSendResponse):
                logger.debug(f"MatrixMessageOps: Reply sent to {room_id}")
                return {
                    "success": True,
                    "event_id": response.event_id,
                    "room_id": room_id,
                    "reply_to": reply_to_event_id
                }
            else:
                error_msg = f"Failed to send reply: {response}"
                logger.error(f"MatrixMessageOps: {error_msg}")
                return {"success": False, "error": error_msg}
                
        except Exception as e:
            error_msg = f"Error sending reply to {room_id}: {e}"
            logger.error(f"MatrixMessageOps: {error_msg}")
            return {"success": False, "error": error_msg}
    
    async def send_formatted_message(
        self,
        room_id: str,
        content: str,
        formatted_content: Optional[str] = None,
        format_type: str = "org.matrix.custom.html"
    ) -> Dict[str, Any]:
        """Send a formatted message with HTML or other formatting."""
        try:
            if not self.client:
                return {"success": False, "error": "Matrix client not available"}
            
            message_content = {
                "msgtype": "m.text",
                "body": content
            }
            
            if formatted_content:
                message_content["format"] = format_type
                message_content["formatted_body"] = formatted_content
            
            response = await self.client.room_send(
                room_id=room_id,
                message_type="m.room.message",
                content=message_content
            )
            
            if isinstance(response, RoomSendResponse):
                logger.debug(f"MatrixMessageOps: Formatted message sent to {room_id}")
                return {
                    "success": True,
                    "event_id": response.event_id,
                    "room_id": room_id,
                    "formatted": bool(formatted_content)
                }
            else:
                error_msg = f"Failed to send formatted message: {response}"
                logger.error(f"MatrixMessageOps: {error_msg}")
                return {"success": False, "error": error_msg}
                
        except Exception as e:
            error_msg = f"Error sending formatted message to {room_id}: {e}"
            logger.error(f"MatrixMessageOps: {error_msg}")
            return {"success": False, "error": error_msg}
    
    async def send_formatted_reply(
        self,
        room_id: str,
        reply_to_event_id: str,
        content: str,
        formatted_content: Optional[str] = None,
        original_sender: Optional[str] = None,
        original_content: Optional[str] = None,
        format_type: str = "org.matrix.custom.html"
    ) -> Dict[str, Any]:
        """Send a formatted reply to a specific message."""
        try:
            if not self.client:
                return {"success": False, "error": "Matrix client not available"}
            
            # Construct fallback body for clients that don't support formatting
            fallback_body = f"> <{original_sender or 'unknown'}> {original_content or 'message'}\n\n{content}"
            
            reply_content = {
                "msgtype": "m.text",
                "body": fallback_body,
                "m.relates_to": {
                    "m.in_reply_to": {
                        "event_id": reply_to_event_id
                    }
                }
            }
            
            if formatted_content:
                reply_content["format"] = format_type
                # For formatted replies, include the quoted original in HTML
                formatted_fallback = (
                    f"<mx-reply><blockquote><a href=\"https://matrix.to/#/{room_id}/{reply_to_event_id}\">In reply to</a> "
                    f"<a href=\"https://matrix.to/#/{original_sender or 'unknown'}\">{original_sender or 'unknown'}</a>"
                    f"<br>{original_content or 'message'}</blockquote></mx-reply>"
                    f"{formatted_content}"
                )
                reply_content["formatted_body"] = formatted_fallback
            
            response = await self.client.room_send(
                room_id=room_id,
                message_type="m.room.message",
                content=reply_content
            )
            
            if isinstance(response, RoomSendResponse):
                logger.debug(f"MatrixMessageOps: Formatted reply sent to {room_id}")
                return {
                    "success": True,
                    "event_id": response.event_id,
                    "room_id": room_id,
                    "reply_to": reply_to_event_id,
                    "formatted": bool(formatted_content)
                }
            else:
                error_msg = f"Failed to send formatted reply: {response}"
                logger.error(f"MatrixMessageOps: {error_msg}")
                return {"success": False, "error": error_msg}
                
        except Exception as e:
            error_msg = f"Error sending formatted reply to {room_id}: {e}"
            logger.error(f"MatrixMessageOps: {error_msg}")
            return {"success": False, "error": error_msg}
    
    async def send_image(
        self,
        room_id: str,
        image_data: bytes,
        filename: str,
        content_type: Optional[str] = None,
        caption: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send an image to a room."""
        try:
            if not self.client:
                return {"success": False, "error": "Matrix client not available"}
            
            # Determine content type if not provided
            if not content_type:
                content_type, _ = mimetypes.guess_type(filename)
                if not content_type:
                    content_type = "application/octet-stream"
            
            # Upload the image to Matrix
            upload_response = await self.client.upload(
                data_provider=lambda: image_data,
                content_type=content_type,
                filename=filename
            )
            
            if hasattr(upload_response, 'content_uri'):
                # Send the image message
                image_content = {
                    "msgtype": "m.image",
                    "body": caption or filename,
                    "url": upload_response.content_uri,
                    "info": {
                        "mimetype": content_type,
                        "size": len(image_data)
                    }
                }
                
                response = await self.client.room_send(
                    room_id=room_id,
                    message_type="m.room.message",
                    content=image_content
                )
                
                if isinstance(response, RoomSendResponse):
                    logger.debug(f"MatrixMessageOps: Image sent to {room_id}: {filename}")
                    return {
                        "success": True,
                        "event_id": response.event_id,
                        "room_id": room_id,
                        "mxc_uri": upload_response.content_uri,
                        "filename": filename
                    }
                else:
                    error_msg = f"Failed to send image message: {response}"
                    logger.error(f"MatrixMessageOps: {error_msg}")
                    return {"success": False, "error": error_msg}
            else:
                error_msg = f"Failed to upload image: {upload_response}"
                logger.error(f"MatrixMessageOps: {error_msg}")
                return {"success": False, "error": error_msg}
                
        except Exception as e:
            error_msg = f"Error sending image to {room_id}: {e}"
            logger.error(f"MatrixMessageOps: {error_msg}")
            return {"success": False, "error": error_msg}
    
    async def react_to_message(
        self,
        room_id: str,
        event_id: str,
        reaction: str
    ) -> Dict[str, Any]:
        """Add a reaction to a message."""
        try:
            if not self.client:
                return {"success": False, "error": "Matrix client not available"}
            
            reaction_content = {
                "m.relates_to": {
                    "rel_type": "m.annotation",
                    "event_id": event_id,
                    "key": reaction
                }
            }
            
            response = await self.client.room_send(
                room_id=room_id,
                message_type="m.reaction",
                content=reaction_content
            )
            
            if isinstance(response, RoomSendResponse):
                logger.debug(f"MatrixMessageOps: Reaction '{reaction}' sent to message {event_id} in {room_id}")
                return {
                    "success": True,
                    "event_id": response.event_id,
                    "room_id": room_id,
                    "reacted_to": event_id,
                    "reaction": reaction
                }
            else:
                error_msg = f"Failed to send reaction: {response}"
                logger.error(f"MatrixMessageOps: {error_msg}")
                return {"success": False, "error": error_msg}
                
        except Exception as e:
            error_msg = f"Error sending reaction to {room_id}: {e}"
            logger.error(f"MatrixMessageOps: {error_msg}")
            return {"success": False, "error": error_msg}
