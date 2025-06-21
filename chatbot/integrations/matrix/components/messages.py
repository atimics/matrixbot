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

from ....utils.markdown_utils import format_for_matrix

logger = logging.getLogger(__name__)


class MatrixMessageOperations:
    """Handles Matrix message sending operations."""
    
    def __init__(self, client: AsyncClient, user_id: str):
        self.client = client
        self.user_id = user_id
    
    async def send_message(self, room_id: str, content: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Send a plain text or formatted message to a room."""
        if not self.client:
            return {"success": False, "error": "Matrix client not available"}
        
        # Standardize content processing
        if isinstance(content, dict):
            # Handle cases where pre-formatted content is passed
            plain_content = content.get('plain', content.get('html', str(content)))
        else:
            plain_content = str(content)
        
        # Always convert markdown to the required format
        formatted_parts = format_for_matrix(plain_content)
        
        message_content = {
            "msgtype": "m.text",
            "body": formatted_parts["plain"],
            "format": "org.matrix.custom.html",
            "formatted_body": formatted_parts["html"]
        }
        
        logger.debug(f"MatrixMessageOps: Sending formatted message to {room_id}")
        
        try:
            response = await self.client.room_send(
                room_id=room_id,
                message_type="m.room.message",
                content=message_content
            )
            
            if isinstance(response, RoomSendResponse):
                logger.debug(f"MatrixMessageOps: Message sent to {room_id}: {formatted_parts['plain'][:100]}...")
                return {
                    "success": True,
                    "event_id": response.event_id,
                    "room_id": room_id
                }
            else:
                error_msg = f"Failed to send message: {response}"
                logger.error(f"MatrixMessageOps: {error_msg}")
                
                # Check if the error is due to not being in the room
                if hasattr(response, 'message') and 'No such room' in str(response.message):
                    logger.info(f"MatrixMessageOps: Not in room {room_id}, attempting to join...")
                    
                    # Attempt to join the room
                    join_response = await self.client.join(room_id)
                    if hasattr(join_response, 'room_id'):
                        logger.info(f"MatrixMessageOps: Successfully joined room {room_id}, retrying message send...")
                        
                        # Retry sending the message
                        retry_response = await self.client.room_send(
                            room_id=room_id,
                            message_type="m.room.message",
                            content=message_content
                        )
                        
                        if isinstance(retry_response, RoomSendResponse):
                            logger.info(f"MatrixMessageOps: Message sent after joining room {room_id}")
                            return {
                                "success": True,
                                "event_id": retry_response.event_id,
                                "room_id": room_id,
                                "joined_room": True
                            }
                        else:
                            return {"success": False, "error": f"Failed to send message after joining room: {retry_response}"}
                    else:
                        return {"success": False, "error": f"Failed to join room {room_id}: {join_response}"}
                
                return {"success": False, "error": error_msg}
                
        except Exception as e:
            error_msg = f"Error sending message to {room_id}: {e}"
            logger.error(f"MatrixMessageOps: {error_msg}")
            
            # Check if the error is due to not being in the room
            if 'No such room' in str(e):
                logger.info(f"MatrixMessageOps: Not in room {room_id} (exception), attempting to join...")
                
                try:
                    # Attempt to join the room
                    join_response = await self.client.join(room_id)
                    if hasattr(join_response, 'room_id'):
                        logger.info(f"MatrixMessageOps: Successfully joined room {room_id}, retrying message send...")
                        
                        # Retry sending the message with the same content
                        retry_response = await self.client.room_send(
                            room_id=room_id,
                            message_type="m.room.message",
                            content=message_content
                        )
                        
                        if isinstance(retry_response, RoomSendResponse):
                            logger.info(f"MatrixMessageOps: Message sent after joining room {room_id}")
                            return {
                                "success": True,
                                "event_id": retry_response.event_id,
                                "room_id": room_id,
                                "joined_room": True
                            }
                        else:
                            return {"success": False, "error": f"Failed to send message after joining room: {retry_response}"}
                    else:
                        return {"success": False, "error": f"Failed to join room {room_id}: {join_response}"}
                except Exception as join_error:
                    logger.error(f"MatrixMessageOps: Error joining room {room_id}: {join_error}")
                    return {"success": False, "error": f"Failed to join room and send message: {join_error}"}
            
            return {"success": False, "error": error_msg}
    
    async def send_reply(
        self,
        room_id: str,
        reply_to_event_id: str,
        content: Union[str, Dict[str, Any]],
        original_sender: Optional[str] = None,
        original_content: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send a reply to a specific message."""
        if not self.client:
            return {"success": False, "error": "Matrix client not available"}
        
        # Standardize content processing for replies
        if isinstance(content, dict):
            plain_content = content.get('plain', content.get('html', str(content)))
        else:
            plain_content = str(content)
        
        formatted_parts = format_for_matrix(plain_content)
        
        # Construct reply content with fallback body
        fallback_body = f"> <{original_sender or 'unknown'}> {original_content or 'message'}\n\n{formatted_parts['plain']}"
        
        # Construct formatted body with HTML reply fallback
        formatted_fallback = (
            f"<mx-reply><blockquote><a href=\"https://matrix.to/#/{room_id}/{reply_to_event_id}\">In reply to</a> "
            f"<a href=\"https://matrix.to/#/{original_sender or 'unknown'}\">{original_sender or 'unknown'}</a>"
            f"<br>{original_content or 'message'}</blockquote></mx-reply>"
            f"{formatted_parts['html']}"
        )
        
        reply_content = {
            "msgtype": "m.text",
            "body": fallback_body,
            "format": "org.matrix.custom.html",
            "formatted_body": formatted_fallback,
            "m.relates_to": {
                "m.in_reply_to": {
                    "event_id": reply_to_event_id
                }
            }
        }
        
        try:
                body_content = str(content)
                msg_type = "m.text"
                logger.debug(f"MatrixMessageOps: Reply - Stringified content: {body_content}")
            
            # Construct reply content with fallback body
            fallback_body = f"> <{original_sender or 'unknown'}> {original_content or 'message'}\n\n{body_content}"
            
            reply_content = {
                "msgtype": msg_type,
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
                
                # Check if the error is due to not being in the room
                if hasattr(response, 'message') and 'No such room' in str(response.message):
                    logger.info(f"MatrixMessageOps: Not in room {room_id}, attempting to join...")
                    
                    # Attempt to join the room
                    join_response = await self.client.join(room_id)
                    if hasattr(join_response, 'room_id'):
                        logger.info(f"MatrixMessageOps: Successfully joined room {room_id}, retrying reply send...")
                        
                        # Retry sending the reply
                        retry_response = await self.client.room_send(
                            room_id=room_id,
                            message_type="m.room.message",
                            content=reply_content
                        )
                        
                        if isinstance(retry_response, RoomSendResponse):
                            logger.info(f"MatrixMessageOps: Reply sent after joining room {room_id}")
                            return {
                                "success": True,
                                "event_id": retry_response.event_id,
                                "room_id": room_id,
                                "reply_to": reply_to_event_id,
                                "joined_room": True
                            }
                        else:
                            return {"success": False, "error": f"Failed to send reply after joining room: {retry_response}"}
                    else:
                        return {"success": False, "error": f"Failed to join room {room_id}: {join_response}"}
                
                return {"success": False, "error": error_msg}
                
        except Exception as e:
            error_msg = f"Error sending reply to {room_id}: {e}"
            logger.error(f"MatrixMessageOps: {error_msg}")
            
            # Check if the error is due to not being in the room
            if 'No such room' in str(e):
                logger.info(f"MatrixMessageOps: Not in room {room_id} (exception), attempting to join...")
                
                try:
                    # Attempt to join the room
                    join_response = await self.client.join(room_id)
                    if hasattr(join_response, 'room_id'):
                        logger.info(f"MatrixMessageOps: Successfully joined room {room_id}, retrying reply send...")
                        
                        # Reconstruct reply content for retry
                        fallback_body = f"> <{original_sender or 'unknown'}> {original_content or 'message'}\n\n{body_content}"
                        reply_content = {
                            "msgtype": msg_type,
                            "body": fallback_body,
                            "m.relates_to": {
                                "m.in_reply_to": {
                                    "event_id": reply_to_event_id
                                }
                            }
                        }
                        
                        # Retry sending the reply
                        retry_response = await self.client.room_send(
                            room_id=room_id,
                            message_type="m.room.message",
                            content=reply_content
                        )
                        
                        if isinstance(retry_response, RoomSendResponse):
                            logger.info(f"MatrixMessageOps: Reply sent after joining room {room_id}")
                            return {
                                "success": True,
                                "event_id": retry_response.event_id,
                                "room_id": room_id,
                                "reply_to": reply_to_event_id,
                                "joined_room": True
                            }
                        else:
                            return {"success": False, "error": f"Failed to send reply after joining room: {retry_response}"}
                    else:
                        return {"success": False, "error": f"Failed to join room {room_id}: {join_response}"}
                except Exception as join_error:
                    logger.error(f"MatrixMessageOps: Error joining room {room_id}: {join_error}")
                    return {"success": False, "error": f"Failed to join room and send reply: {join_error}"}
            
            return {"success": False, "error": error_msg}
    
    async def send_formatted_message(
        self,
        room_id: str,
        content: Union[str, Dict[str, Any]],
        formatted_content: Optional[str] = None,
        format_type: str = "org.matrix.custom.html"
    ) -> Dict[str, Any]:
        """Send a formatted message with HTML or other formatting."""
        try:
            if not self.client:
                return {"success": False, "error": "Matrix client not available"}
            
            # Extract content from the content object
            if isinstance(content, dict):
                plain_content = content.get('plain', str(content))
                html_content = content.get('html', plain_content)
            else:
                plain_content = content
                html_content = content
            
            message_content = {
                "msgtype": "m.text",
                "body": plain_content
            }
            
            # Use the HTML content from the object, or fallback to formatted_content parameter
            if html_content and html_content != plain_content:
                message_content["format"] = format_type
                message_content["formatted_body"] = html_content
            elif formatted_content:
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
        content: Union[str, Dict[str, Any]],
        formatted_content: Optional[str] = None,
        original_sender: Optional[str] = None,
        original_content: Optional[str] = None,
        format_type: str = "org.matrix.custom.html"
    ) -> Dict[str, Any]:
        """Send a formatted reply to a specific message."""
        try:
            if not self.client:
                return {"success": False, "error": "Matrix client not available"}
            
            # Extract content from the content object
            if isinstance(content, dict):
                plain_content = content.get('plain', str(content))
                html_content = content.get('html', plain_content)
            else:
                plain_content = content
                html_content = content
            
            # Construct fallback body for clients that don't support formatting
            fallback_body = f"> <{original_sender or 'unknown'}> {original_content or 'message'}\n\n{plain_content}"
            
            reply_content = {
                "msgtype": "m.text",
                "body": fallback_body,
                "m.relates_to": {
                    "m.in_reply_to": {
                        "event_id": reply_to_event_id
                    }
                }
            }
            
            # Use the HTML content from the object, or fallback to formatted_content parameter
            if html_content and html_content != plain_content:
                reply_content["format"] = format_type
                # For formatted replies, include the quoted original in HTML
                formatted_fallback = (
                    f"<mx-reply><blockquote><a href=\"https://matrix.to/#/{room_id}/{reply_to_event_id}\">In reply to</a> "
                    f"<a href=\"https://matrix.to/#/{original_sender or 'unknown'}\">{original_sender or 'unknown'}</a>"
                    f"<br>{original_content or 'message'}</blockquote></mx-reply>"
                    f"{html_content}"
                )
                reply_content["formatted_body"] = formatted_fallback
            elif formatted_content:
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
