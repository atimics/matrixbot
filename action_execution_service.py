import asyncio
import json
import logging
import uuid
from typing import Dict, Any, Optional

from message_bus import MessageBus
from action_registry_service import ActionRegistryService
from farcaster_service import FarcasterService
from event_definitions import (
    ActionExecutionRequestEvent, ActionExecutionResponseEvent,
    SendMatrixMessageCommand, SendReplyCommand, ReactToMessageCommand,
    AIAction, ChannelResponse, AIResponsePlan
)

logger = logging.getLogger(__name__)

class ActionExecutionService:
    """Service that executes individual actions from AI response plans."""
    
    def __init__(self, message_bus: MessageBus, action_registry: ActionRegistryService, 
                 db_path: str = "matrix_bot_soa.db"):
        self.bus = message_bus
        self.action_registry = action_registry
        self.db_path = db_path
        self.farcaster_service = FarcasterService(db_path)
        self._stop_event = asyncio.Event()
        # Add reference for unified channel integration
        self.unified_channel_manager = None
    
    async def run(self) -> None:
        """Main service loop."""
        logger.info("ActionExecutionService: Starting service...")
        
        # Subscribe to action execution requests
        await self.bus.subscribe("action_execution_request", self._handle_action_execution_request)
        
        # Subscribe to unified channel tool events
        await self.bus.subscribe("update_farcaster_channel", self._handle_update_farcaster_channel)
        await self.bus.subscribe("view_channel_context", self._handle_view_channel_context)
        
        # Wait for stop signal
        await self._stop_event.wait()
        logger.info("ActionExecutionService: Service stopped")
    
    async def stop(self) -> None:
        """Stop the service."""
        self._stop_event.set()
    
    async def execute_action_plan(self, action_plan: AIResponsePlan, 
                                request_id: str = None) -> Dict[str, Any]:
        """Execute all actions in an AI response plan."""
        if not request_id:
            request_id = str(uuid.uuid4())
        
        results = {
            "request_id": request_id,
            "channel_results": [],
            "overall_success": True
        }
        
        for channel_response in action_plan.channel_responses:
            channel_results = await self._execute_channel_response(channel_response, request_id)
            results["channel_results"].append(channel_results)
            
            if not channel_results["success"]:
                results["overall_success"] = False
        
        logger.info(f"ActionExecution: Completed action plan execution {request_id}")
        return results
    
    async def _execute_channel_response(self, channel_response: ChannelResponse, 
                                      request_id: str) -> Dict[str, Any]:
        """Execute all actions for a single channel."""
        channel_id = channel_response.channel_id
        results = {
            "channel_id": channel_id,
            "action_results": [],
            "success": True
        }
        
        for action in channel_response.actions:
            action_result = await self._execute_single_action(channel_id, action, request_id)
            results["action_results"].append(action_result)
            
            if not action_result["success"]:
                results["success"] = False
        
        return results
    
    async def _execute_single_action(self, channel_id: str, action: AIAction, 
                                   request_id: str) -> Dict[str, Any]:
        """Execute a single action."""
        action_name = action.action_name
        parameters = action.parameters
        
        logger.info(f"ActionExecution: Executing {action_name} for channel {channel_id}")
        
        # Validate action exists
        action_def = self.action_registry.get_action_definition(action_name)
        if not action_def:
            error_msg = f"Unknown action: {action_name}"
            logger.error(f"ActionExecution: {error_msg}")
            return {
                "action_name": action_name,
                "success": False,
                "error": error_msg
            }
        
        # Execute the action based on its type
        try:
            # Matrix actions
            if action_name == "send_reply_text":
                return await self._execute_send_reply_text(channel_id, parameters, request_id)
            elif action_name == "send_message_text":
                return await self._execute_send_message_text(channel_id, parameters, request_id)
            elif action_name == "react_to_message":
                return await self._execute_react_to_message(channel_id, parameters, request_id)
            elif action_name == "describe_image":
                return await self._execute_describe_image(channel_id, parameters, request_id)
            elif action_name == "manage_channel_summary":
                return await self._execute_manage_channel_summary(channel_id, parameters, request_id)
            elif action_name == "do_not_respond":
                return await self._execute_do_not_respond(channel_id, parameters, request_id)
            elif action_name == "get_room_info":
                return await self._execute_get_room_info(channel_id, parameters, request_id)
            elif action_name == "delegate_to_openrouter":
                return await self._execute_delegate_to_openrouter(channel_id, parameters, request_id)
            elif action_name == "manage_system_prompt":
                return await self._execute_manage_system_prompt(channel_id, parameters, request_id)
            # Farcaster actions
            elif action_name == "farcaster_post_cast":
                return await self._execute_farcaster_post_cast(channel_id, parameters, request_id)
            elif action_name == "farcaster_get_home_feed":
                return await self._execute_farcaster_get_home_feed(channel_id, parameters, request_id)
            elif action_name == "farcaster_like_cast":
                return await self._execute_farcaster_like_cast(channel_id, parameters, request_id)
            elif action_name == "farcaster_reply_to_cast":
                return await self._execute_farcaster_reply_to_cast(channel_id, parameters, request_id)
            elif action_name == "farcaster_get_notifications":
                return await self._execute_farcaster_get_notifications(channel_id, parameters, request_id)
            elif action_name == "farcaster_quote_cast":
                return await self._execute_farcaster_quote_cast(channel_id, parameters, request_id)
            else:
                error_msg = f"Action execution not implemented: {action_name}"
                logger.error(f"ActionExecution: {error_msg}")
                return {
                    "action_name": action_name,
                    "success": False,
                    "error": error_msg
                }
        
        except Exception as e:
            error_msg = f"Error executing action {action_name}: {str(e)}"
            logger.error(f"ActionExecution: {error_msg}")
            return {
                "action_name": action_name,
                "success": False,
                "error": error_msg
            }
    
    # Matrix action execution methods (existing)
    async def _execute_send_reply_text(self, channel_id: str, parameters: Dict[str, Any], 
                                     request_id: str) -> Dict[str, Any]:
        """Execute send_reply_text action."""
        text = parameters.get("text", "")
        reply_to_event_id = parameters.get("reply_to_event_id")
        
        if not text:
            return {
                "action_name": "send_reply_text",
                "success": False,
                "error": "Missing required parameter: text"
            }
        
        if reply_to_event_id:
            # Send as a reply
            command = SendReplyCommand(
                room_id=channel_id,
                text=text,
                reply_to_event_id=reply_to_event_id
            )
        else:
            # Send as regular message
            command = SendMatrixMessageCommand(
                room_id=channel_id,
                text=text
            )
        
        await self.bus.publish(command)
        
        return {
            "action_name": "send_reply_text",
            "success": True,
            "result": f"Sent reply: {text[:50]}..."
        }
    
    async def _execute_send_message_text(self, channel_id: str, parameters: Dict[str, Any], 
                                       request_id: str) -> Dict[str, Any]:
        """Execute send_message_text action."""
        text = parameters.get("text", "")
        
        if not text:
            return {
                "action_name": "send_message_text",
                "success": False,
                "error": "Missing required parameter: text"
            }
        
        command = SendMatrixMessageCommand(
            room_id=channel_id,
            text=text
        )
        
        await self.bus.publish(command)
        
        return {
            "action_name": "send_message_text",
            "success": True,
            "result": f"Sent message: {text[:50]}..."
        }
    
    async def _execute_react_to_message(self, channel_id: str, parameters: Dict[str, Any], 
                                      request_id: str) -> Dict[str, Any]:
        """Execute react_to_message action."""
        event_id = parameters.get("event_id", "")
        emoji = parameters.get("emoji", "")
        
        if not event_id or not emoji:
            return {
                "action_name": "react_to_message",
                "success": False,
                "error": "Missing required parameters: event_id and/or emoji"
            }
        
        command = ReactToMessageCommand(
            room_id=channel_id,
            event_id_to_react_to=event_id,
            reaction_key=emoji
        )
        
        await self.bus.publish(command)
        
        return {
            "action_name": "react_to_message",
            "success": True,
            "result": f"Reacted with {emoji} to message {event_id}"
        }
    
    async def _execute_describe_image(self, channel_id: str, parameters: Dict[str, Any], 
                                    request_id: str) -> Dict[str, Any]:
        """Execute describe_image action."""
        image_event_id = parameters.get("image_event_id", "")
        focus = parameters.get("focus", "general")
        
        if not image_event_id:
            return {
                "action_name": "describe_image",
                "success": False,
                "error": "Missing required parameter: image_event_id"
            }
        
        # This would typically trigger an image analysis service
        # For now, we'll create a placeholder response
        description = f"[Image description for {image_event_id} with focus: {focus}]"
        
        # Send the description as a reply
        command = SendReplyCommand(
            room_id=channel_id,
            text=description,
            reply_to_event_id=image_event_id
        )
        
        await self.bus.publish(command)
        
        return {
            "action_name": "describe_image",
            "success": True,
            "result": f"Generated image description for {image_event_id}"
        }
    
    async def _execute_manage_channel_summary(self, channel_id: str, parameters: Dict[str, Any], 
                                            request_id: str) -> Dict[str, Any]:
        """Execute manage_channel_summary action."""
        action = parameters.get("action", "")
        focus = parameters.get("focus")
        
        if not action:
            return {
                "action_name": "manage_channel_summary",
                "success": False,
                "error": "Missing required parameter: action"
            }
        
        # This would typically trigger a summarization service
        logger.info(f"ActionExecution: Managing channel summary - action: {action}, focus: {focus}")
        
        return {
            "action_name": "manage_channel_summary",
            "success": True,
            "result": f"Channel summary {action} requested"
        }
    
    async def _execute_do_not_respond(self, channel_id: str, parameters: Dict[str, Any], 
                                    request_id: str) -> Dict[str, Any]:
        """Execute do_not_respond action."""
        reason = parameters.get("reason", "No response needed")
        
        logger.info(f"ActionExecution: Choosing not to respond to {channel_id}. Reason: {reason}")
        
        return {
            "action_name": "do_not_respond",
            "success": True,
            "result": f"No response action: {reason}"
        }
    
    async def _execute_get_room_info(self, channel_id: str, parameters: Dict[str, Any], 
                                   request_id: str) -> Dict[str, Any]:
        """Execute get_room_info action."""
        info_type = parameters.get("info_type")
        
        if not info_type:
            return {
                "action_name": "get_room_info",
                "success": False,
                "error": "Missing required parameter: info_type"
            }
        
        # Map info_type to aspects for Matrix room info request
        info_type_to_aspects = {
            "basic": ["name", "topic"],
            "members": ["members"],
            "settings": ["name", "topic"],  # Could include more settings in the future
            "history_stats": ["name", "topic", "members"],  # Basic info for stats context
            "general": ["name", "topic", "members"]  # Handle the "general" case from AI
        }
        
        aspects = info_type_to_aspects.get(info_type, ["name", "topic", "members"])
        
        # This would typically query the Matrix client for room information
        logger.info(f"ActionExecution: Getting room info for {channel_id}, info_type: {info_type}, aspects: {aspects}")
        
        return {
            "action_name": "get_room_info",
            "success": True,
            "result": f"Room info requested for type '{info_type}' (aspects: {aspects})"
        }
    
    async def _execute_delegate_to_openrouter(self, channel_id: str, parameters: Dict[str, Any], 
                                            request_id: str) -> Dict[str, Any]:
        """Execute delegate_to_openrouter action."""
        query = parameters.get("query", "")
        model_preference = parameters.get("model_preference")
        context_needed = parameters.get("context_needed", True)
        
        if not query:
            return {
                "action_name": "delegate_to_openrouter",
                "success": False,
                "error": "Missing required parameter: query"
            }
        
        # This would typically create an AI inference request
        logger.info(f"ActionExecution: Delegating to OpenRouter - model: {model_preference}, query: {query[:100]}...")
        
        return {
            "action_name": "delegate_to_openrouter",
            "success": True,
            "result": f"Delegated query to OpenRouter: {query[:50]}..."
        }
    
    async def _execute_manage_system_prompt(self, channel_id: str, parameters: Dict[str, Any], 
                                          request_id: str) -> Dict[str, Any]:
        """Execute manage_system_prompt action."""
        import database
        
        # --- Parameter normalization for compatibility with AI-generated actions ---
        # Accept both legacy and new parameter names
        normalized = dict(parameters)
        op = normalized.get("operation")
        if op:
            if op in ["get", "get_current"]:
                normalized["action"] = "get_current"
            elif op in ["set", "update"]:
                normalized["action"] = "update"
        # Accept new_content as new_prompt_text
        if "new_content" in normalized:
            normalized["new_prompt_text"] = normalized["new_content"]
        # Optionally, handle prompt_section if you want to support sections in the future
        action = normalized.get("action", "")
        new_prompt_text = normalized.get("new_prompt_text")
        # ...existing code...
        if not action:
            return {
                "action_name": "manage_system_prompt",
                "success": False,
                "error": "Missing required parameter: action"
            }
        
        if action not in ["get_current", "update"]:
            return {
                "action_name": "manage_system_prompt",
                "success": False,
                "error": f"Invalid action '{action}'. Must be 'get_current' or 'update'"
            }
        
        try:
            if action == "get_current":
                prompt_name = "system_default"
                current_prompt_tuple = await database.get_prompt(self.db_path, prompt_name)
                
                if current_prompt_tuple and current_prompt_tuple[0] is not None:
                    current_prompt = current_prompt_tuple[0]
                    logger.info(f"ActionExecution: Retrieved system prompt '{prompt_name}'")
                    return {
                        "action_name": "manage_system_prompt",
                        "success": True,
                        "result": f"Current system prompt: '{current_prompt}'"
                    }
                else:
                    logger.warning(f"ActionExecution: System prompt '{prompt_name}' not found")
                    return {
                        "action_name": "manage_system_prompt",
                        "success": True,
                        "result": f"System prompt '{prompt_name}' not found"
                    }
            
            elif action == "update":
                if not new_prompt_text:
                    return {
                        "action_name": "manage_system_prompt",
                        "success": False,
                        "error": "Missing required parameter 'new_prompt_text' for action 'update'"
                    }
                
                prompt_name = "system_default"
                await database.update_prompt(self.db_path, prompt_name, new_prompt_text)
                logger.info(f"ActionExecution: Updated system prompt '{prompt_name}'")
                
                return {
                    "action_name": "manage_system_prompt",
                    "success": True,
                    "result": f"System prompt '{prompt_name}' updated successfully"
                }
                
        except Exception as e:
            error_msg = f"Error managing system prompt: {str(e)}"
            logger.error(f"ActionExecution: {error_msg}")
            return {
                "action_name": "manage_system_prompt",
                "success": False,
                "error": error_msg
            }
    
    # Farcaster action execution methods (new)
    async def _execute_farcaster_post_cast(self, channel_id: str, parameters: Dict[str, Any], 
                                          request_id: str) -> Dict[str, Any]:
        """Execute farcaster_post_cast action."""
        text = parameters.get("text", "")
        channel_id_fc = parameters.get("channel_id")
        embed_urls = parameters.get("embed_urls")
        
        if not text:
            return {
                "action_name": "farcaster_post_cast",
                "success": False,
                "error": "Missing required parameter: text"
            }
        
        result = await self.farcaster_service.post_cast(text, channel_id_fc, embed_urls)
        
        if result.get("success"):
            cast_hash = result.get("cast_hash", "unknown")
            return {
                "action_name": "farcaster_post_cast",
                "success": True,
                "result": f"Posted cast: {text[:50]}... (hash: {cast_hash})"
            }
        else:
            return {
                "action_name": "farcaster_post_cast",
                "success": False,
                "error": result.get("error", "Unknown error posting cast")
            }
    
    async def _execute_farcaster_get_home_feed(self, channel_id: str, parameters: Dict[str, Any], 
                                              request_id: str) -> Dict[str, Any]:
        """Execute farcaster_get_home_feed action."""
        limit = parameters.get("limit", 25)
        
        result = await self.farcaster_service.get_home_feed(limit)
        
        if result.get("success"):
            count = result.get("count", 0)
            return {
                "action_name": "farcaster_get_home_feed",
                "success": True,
                "result": f"Retrieved {count} casts from home feed"
            }
        else:
            return {
                "action_name": "farcaster_get_home_feed",
                "success": False,
                "error": result.get("error", "Unknown error getting home feed")
            }
    
    async def _execute_farcaster_like_cast(self, channel_id: str, parameters: Dict[str, Any], 
                                          request_id: str) -> Dict[str, Any]:
        """Execute farcaster_like_cast action."""
        target_cast_hash = parameters.get("target_cast_hash", "")
        
        if not target_cast_hash:
            return {
                "action_name": "farcaster_like_cast",
                "success": False,
                "error": "Missing required parameter: target_cast_hash"
            }
        
        result = await self.farcaster_service.like_cast(target_cast_hash)
        
        if result.get("success"):
            return {
                "action_name": "farcaster_like_cast",
                "success": True,
                "result": f"Liked cast {target_cast_hash}"
            }
        else:
            return {
                "action_name": "farcaster_like_cast",
                "success": False,
                "error": result.get("error", "Unknown error liking cast")
            }
    
    async def _execute_farcaster_reply_to_cast(self, channel_id: str, parameters: Dict[str, Any], 
                                              request_id: str) -> Dict[str, Any]:
        """Execute farcaster_reply_to_cast action."""
        text = parameters.get("text", "")
        parent_cast_hash = parameters.get("parent_cast_hash", "")
        channel_id_fc = parameters.get("channel_id")
        embed_urls = parameters.get("embed_urls")
        
        if not text:
            return {
                "action_name": "farcaster_reply_to_cast",
                "success": False,
                "error": "Missing required parameter: text"
            }
        
        if not parent_cast_hash:
            return {
                "action_name": "farcaster_reply_to_cast",
                "success": False,
                "error": "Missing required parameter: parent_cast_hash"
            }
        
        result = await self.farcaster_service.reply_to_cast(text, parent_cast_hash, channel_id_fc, embed_urls)
        
        if result.get("success"):
            reply_hash = result.get("reply_hash", "unknown")
            return {
                "action_name": "farcaster_reply_to_cast",
                "success": True,
                "result": f"Replied to cast {parent_cast_hash}: {text[:50]}... (reply hash: {reply_hash})"
            }
        else:
            return {
                "action_name": "farcaster_reply_to_cast",
                "success": False,
                "error": result.get("error", "Unknown error replying to cast")
            }
    
    async def _execute_farcaster_get_notifications(self, channel_id: str, parameters: Dict[str, Any], 
                                                  request_id: str) -> Dict[str, Any]:
        """Execute farcaster_get_notifications action."""
        limit = parameters.get("limit", 25)
        filter_types = parameters.get("filter_types")
        
        result = await self.farcaster_service.get_notifications(limit, filter_types)
        
        if result.get("success"):
            count = result.get("count", 0)
            mentions_summary = result.get("mentions_summary", "")
            return {
                "action_name": "farcaster_get_notifications",
                "success": True,
                "result": f"Retrieved {count} new notifications. {mentions_summary}"
            }
        else:
            return {
                "action_name": "farcaster_get_notifications",
                "success": False,
                "error": result.get("error", "Unknown error getting notifications")
            }
    
    async def _execute_farcaster_quote_cast(self, channel_id: str, parameters: Dict[str, Any], 
                                           request_id: str) -> Dict[str, Any]:
        """Execute farcaster_quote_cast action."""
        text = parameters.get("text", "")
        quoted_cast_hash = parameters.get("quoted_cast_hash", "")
        channel_id_fc = parameters.get("channel_id")
        embed_urls = parameters.get("embed_urls")
        
        if not text:
            return {
                "action_name": "farcaster_quote_cast",
                "success": False,
                "error": "Missing required parameter: text"
            }
        
        if not quoted_cast_hash:
            return {
                "action_name": "farcaster_quote_cast",
                "success": False,
                "error": "Missing required parameter: quoted_cast_hash"
            }
        
        result = await self.farcaster_service.quote_cast(text, quoted_cast_hash, channel_id_fc, embed_urls)
        
        if result.get("success"):
            quote_hash = result.get("quote_hash", "unknown")
            return {
                "action_name": "farcaster_quote_cast",
                "success": True,
                "result": f"Quoted cast {quoted_cast_hash}: {text[:50]}... (quote hash: {quote_hash})"
            }
        else:
            return {
                "action_name": "farcaster_quote_cast",
                "success": False,
                "error": result.get("error", "Unknown error quoting cast")
            }

    async def _handle_action_execution_request(self, request: ActionExecutionRequestEvent) -> None:
        """Handle individual action execution requests."""
        result = await self._execute_single_action(
            request.channel_id, 
            request.action, 
            request.event_id
        )
        
        response = ActionExecutionResponseEvent(
            channel_id=request.channel_id,
            action_name=request.action.action_name,
            success=result["success"],
            result=result.get("result"),
            error_message=result.get("error"),
            original_request_id=request.event_id
        )
        
        await self.bus.publish(response)
    
    async def _handle_update_farcaster_channel(self, event) -> None:
        """Handle Farcaster channel update requests."""
        try:
            channel_type = event.channel_type
            limit = event.limit
            
            if channel_type == "home":
                result = await self.farcaster_service.get_home_feed(limit)
                if result.get("success"):
                    logger.info(f"ActionExecution: Updated Farcaster home channel with {result.get('count', 0)} casts")
                else:
                    logger.error(f"ActionExecution: Failed to update Farcaster home channel: {result.get('error')}")
            
            elif channel_type == "notifications":
                result = await self.farcaster_service.get_notifications(limit)
                if result.get("success"):
                    logger.info(f"ActionExecution: Updated Farcaster notifications channel with {result.get('count', 0)} notifications")
                else:
                    logger.error(f"ActionExecution: Failed to update Farcaster notifications channel: {result.get('error')}")
            
            else:
                logger.error(f"ActionExecution: Invalid Farcaster channel type: {channel_type}")
                
        except Exception as e:
            logger.error(f"ActionExecution: Error handling Farcaster channel update: {e}")
    
    async def _handle_view_channel_context(self, event) -> None:
        """Handle channel context view requests."""
        try:
            channel_id = event.channel_id
            limit = event.limit
            
            if self.unified_channel_manager:
                context = await self.unified_channel_manager.get_channel_context(channel_id, limit)
                messages = context.get("messages", [])
                
                # Format the context for AI consumption
                context_text = self._format_channel_context(messages, channel_id)
                
                # Send the context as a message to be picked up by the AI
                # This will be integrated with the AI service to provide context
                logger.info(f"ActionExecution: Retrieved context for channel {channel_id}: {len(messages)} messages")
                
                # TODO: Send this context to the AI service for processing
                # For now, just log it
                logger.debug(f"Channel context for {channel_id}:\n{context_text}")
            else:
                logger.warning("ActionExecution: Unified channel manager not available for context retrieval")
                
        except Exception as e:
            logger.error(f"ActionExecution: Error handling channel context view: {e}")
    
    def _format_channel_context(self, messages: list, channel_id: str) -> str:
        """Format channel messages into readable context text."""
        if not messages:
            return f"No messages found in channel {channel_id}"
        
        context_lines = [f"=== Channel Context: {channel_id} ==="]
        
        for msg in messages:
            timestamp = msg.get("timestamp", 0)
            sender = msg.get("sender_display_name", "Unknown")
            content = msg.get("content", "")
            message_type = msg.get("message_type", "")
            ai_replied = msg.get("ai_has_replied", False)
            
            # Format timestamp
            import datetime
            dt = datetime.datetime.fromtimestamp(timestamp)
            time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
            
            # Add message type indicator
            type_indicator = ""
            if message_type == "farcaster_cast":
                type_indicator = "[FC]"
            elif message_type == "farcaster_notification":
                type_indicator = "[FC-NOTIF]"
            elif message_type == "matrix_message":
                type_indicator = "[MATRIX]"
            
            # Add AI reply indicator
            reply_indicator = " [AI-REPLIED]" if ai_replied else ""
            
            context_lines.append(f"{time_str} {type_indicator} {sender}: {content}{reply_indicator}")
        
        return "\n".join(context_lines)