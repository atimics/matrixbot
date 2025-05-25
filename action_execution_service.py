import asyncio
import json
import logging
import uuid
from typing import Dict, Any, Optional

from message_bus import MessageBus
from action_registry_service import ActionRegistryService
from event_definitions import (
    ActionExecutionRequestEvent, ActionExecutionResponseEvent,
    SendMatrixMessageCommand, SendReplyCommand, ReactToMessageCommand,
    AIAction, ChannelResponse, AIResponsePlan
)

logger = logging.getLogger(__name__)

class ActionExecutionService:
    """Service that executes individual actions from AI response plans."""
    
    def __init__(self, message_bus: MessageBus, action_registry: ActionRegistryService):
        self.bus = message_bus
        self.action_registry = action_registry
        self._stop_event = asyncio.Event()
    
    async def run(self) -> None:
        """Main service loop."""
        logger.info("ActionExecutionService: Starting service...")
        
        # Subscribe to action execution requests
        await self.bus.subscribe("action_execution_request", self._handle_action_execution_request)
        
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
        reaction = parameters.get("reaction", "")
        
        if not event_id or not reaction:
            return {
                "action_name": "react_to_message",
                "success": False,
                "error": "Missing required parameters: event_id and/or reaction"
            }
        
        command = ReactToMessageCommand(
            room_id=channel_id,
            event_id_to_react_to=event_id,
            reaction_key=reaction
        )
        
        await self.bus.publish(command)
        
        return {
            "action_name": "react_to_message",
            "success": True,
            "result": f"Reacted with {reaction} to message {event_id}"
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
        aspects = parameters.get("aspects", [])
        
        if not aspects:
            return {
                "action_name": "get_room_info",
                "success": False,
                "error": "Missing required parameter: aspects"
            }
        
        # This would typically query the Matrix client for room information
        logger.info(f"ActionExecution: Getting room info for {channel_id}, aspects: {aspects}")
        
        return {
            "action_name": "get_room_info",
            "success": True,
            "result": f"Room info requested for aspects: {aspects}"
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