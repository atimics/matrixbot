import asyncio
import os
import httpx  # Added for asynchronous HTTP calls
import json
import logging
from typing import Dict, List, Optional, Tuple, Any
from dotenv import load_dotenv

from message_bus import MessageBus
from event_definitions import OpenRouterInferenceRequestEvent, AIInferenceResponseEvent, ToolCall, ToolFunction, OpenRouterInferenceResponseEvent

logger = logging.getLogger(__name__)

load_dotenv()

class AIInferenceService:
    def __init__(self, message_bus: MessageBus):
        """Service for handling AI inference requests via OpenRouter."""
        self.bus = message_bus
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        self.site_url = os.getenv("YOUR_SITE_URL", "https://your-matrix-bot.example.com/soa")
        self.site_name = os.getenv("YOUR_SITE_NAME", "MyMatrixBotSOA_AI")
        self._stop_event = asyncio.Event()

    def _validate_and_clean_tool_sequences(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Validate and clean tool call sequences, removing orphaned tool results."""
        if not messages:
            return messages
        
        cleaned_messages = []
        openai_tool_calls_awaiting = set()  # For tool_call_id tracking
        anthropic_tool_calls_awaiting = set()  # For tool_use_id tracking
        
        for i, msg in enumerate(messages):
            role = msg.get("role")
            msg_copy = msg.copy()
            
            if role == "assistant":
                # Track tool calls made by assistant (OpenAI format)
                tool_calls = msg.get("tool_calls", [])
                if tool_calls:
                    for tc in tool_calls:
                        tc_id = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
                        if tc_id:
                            openai_tool_calls_awaiting.add(tc_id)
                
                # Also check for Anthropic-style tool_use blocks in content
                content = msg.get("content")
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_use":
                            tool_use_id = block.get("id")
                            if tool_use_id:
                                anthropic_tool_calls_awaiting.add(tool_use_id)
                
                cleaned_messages.append(msg_copy)
                
            elif role == "tool":
                # Validate OpenAI-style tool responses
                tool_call_id = msg.get("tool_call_id")
                if not tool_call_id:
                    logger.warning(f"Skipping tool message at index {i}: missing tool_call_id")
                    continue
                
                if tool_call_id not in openai_tool_calls_awaiting:
                    logger.warning(f"Skipping orphaned tool result at index {i}: tool_call_id {tool_call_id} has no corresponding tool call")
                    continue
                
                openai_tool_calls_awaiting.remove(tool_call_id)
                cleaned_messages.append(msg_copy)
                
            elif role == "user":
                # Handle content that might contain tool_result blocks (Anthropic format)
                content = msg.get("content")
                if isinstance(content, list):
                    # Filter out orphaned tool_result blocks
                    filtered_content = []
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_result":
                            tool_use_id = block.get("tool_use_id")
                            # Check if this tool_result has a corresponding tool_use
                            if tool_use_id and tool_use_id in anthropic_tool_calls_awaiting:
                                anthropic_tool_calls_awaiting.remove(tool_use_id)
                                filtered_content.append(block)
                            else:
                                logger.warning(f"Skipping orphaned tool_result block with tool_use_id {tool_use_id} in user message at index {i}")
                        elif isinstance(block, dict) and block.get("type") == "tool_use":
                            # Track tool_use blocks
                            tool_use_id = block.get("id")
                            if tool_use_id:
                                anthropic_tool_calls_awaiting.add(tool_use_id)
                            filtered_content.append(block)
                        else:
                            # Keep all other content blocks (text, image, etc.)
                            filtered_content.append(block)
                    
                    if filtered_content:
                        msg_copy["content"] = filtered_content
                        cleaned_messages.append(msg_copy)
                    else:
                        logger.warning(f"Skipping user message at index {i}: all content blocks were filtered out")
                elif isinstance(content, str) and content.strip():
                    # Regular text content
                    cleaned_messages.append(msg_copy)
                
            else:
                # Other roles (system, etc.)
                cleaned_messages.append(msg_copy)
        
        return cleaned_messages

    def _validate_message_sequence(self, messages: List[Dict[str, Any]]) -> Tuple[bool, Optional[str]]:
        """Validate message sequence according to OpenRouter/OpenAI standards."""
        if not messages:
            return False, "Empty message list"
        
        # Check for alternating user/assistant pattern (flexible)
        has_user_message = any(msg.get("role") == "user" for msg in messages)
        if not has_user_message:
            return False, "No user messages found in conversation"
        
        # Validate tool call/response pairs with separate tracking for different formats
        openai_tool_calls_awaiting = set()  # For tool_call_id tracking
        anthropic_tool_calls_awaiting = set()  # For tool_use_id tracking
        
        for i, msg in enumerate(messages):
            role = msg.get("role")
            
            if role == "assistant":
                # Track OpenAI-style tool calls
                if msg.get("tool_calls"):
                    for tc in msg["tool_calls"]:
                        tc_id = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
                        if tc_id:
                            openai_tool_calls_awaiting.add(tc_id)
                
                # Track Anthropic-style tool_use blocks in content
                content = msg.get("content")
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_use":
                            tool_use_id = block.get("id")
                            if tool_use_id:
                                anthropic_tool_calls_awaiting.add(tool_use_id)
            
            elif role == "tool":
                # Validate OpenAI-style tool responses
                tool_call_id = msg.get("tool_call_id")
                if not tool_call_id:
                    return False, f"Tool message at index {i} missing tool_call_id"
                if tool_call_id not in openai_tool_calls_awaiting:
                    return False, f"Tool response {tool_call_id} has no corresponding tool call"
                openai_tool_calls_awaiting.remove(tool_call_id)
            
            elif role == "user":
                # Check for Anthropic-style tool_result blocks
                content = msg.get("content")
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_result":
                            tool_use_id = block.get("tool_use_id")
                            if tool_use_id:
                                if tool_use_id not in anthropic_tool_calls_awaiting:
                                    return False, f"Tool result block with tool_use_id {tool_use_id} has no corresponding tool call"
                                anthropic_tool_calls_awaiting.remove(tool_use_id)
        
        return True, None

    def _clean_and_prepare_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Clean and prepare messages for OpenRouter API."""
        # First, validate and clean tool sequences
        messages = self._validate_and_clean_tool_sequences(messages)
        
        cleaned_messages = []
        system_messages = []
        
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content")
            
            # Handle system messages separately - consolidate them
            if role == "system":
                if content and isinstance(content, str) and content.strip():
                    system_messages.append(content.strip())
                continue
            
            # Skip messages with empty content (except those with tool_calls)
            if not content or (isinstance(content, str) and not content.strip()):
                if role == "assistant" and msg.get("tool_calls"):
                    # Assistant message with tool calls but no content - keep it but ensure content is None
                    msg_copy = msg.copy()
                    msg_copy["content"] = None
                    cleaned_messages.append(msg_copy)
                continue
            
            # Handle list content - filter out empty blocks
            if isinstance(content, list):
                filtered_content = [block for block in content if block]
                if filtered_content:
                    msg_copy = msg.copy()
                    msg_copy["content"] = filtered_content
                    cleaned_messages.append(msg_copy)
                continue
            
            # For regular messages, ensure content is properly formatted
            msg_copy = msg.copy()
            if isinstance(content, str):
                msg_copy["content"] = content.strip()
            cleaned_messages.append(msg_copy)
        
        # Add consolidated system message at the beginning if any exist
        final_messages = []
        if system_messages:
            consolidated_system = "\n\n".join(system_messages)
            final_messages.append({"role": "system", "content": consolidated_system})
        
        final_messages.extend(cleaned_messages)
        return final_messages

    def _prepare_tool_calls_for_api(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Ensure tool calls are properly formatted for the OpenRouter API."""
        processed_messages = []
        
        for message in messages:
            msg_copy = message.copy()
            
            if msg_copy.get("role") == "assistant" and "tool_calls" in msg_copy and msg_copy["tool_calls"]:
                processed_tool_calls = []
                
                for tc in msg_copy["tool_calls"]:
                    # Convert Pydantic models to dict if needed
                    tc_dict = tc if isinstance(tc, dict) else tc.model_dump(mode='json')
                    
                    function_data = tc_dict.get("function", {})
                    arguments_data = function_data.get("arguments")
                    
                    # Ensure arguments are JSON string for OpenRouter
                    if isinstance(arguments_data, (dict, list)):
                        stringified_arguments = json.dumps(arguments_data)
                    elif arguments_data is None:
                        stringified_arguments = json.dumps({})
                    else:
                        stringified_arguments = str(arguments_data)
                    
                    processed_tool_calls.append({
                        "id": tc_dict.get("id"),
                        "type": tc_dict.get("type", "function"),
                        "function": {
                            "name": function_data.get("name"),
                            "arguments": stringified_arguments
                        }
                    })
                
                msg_copy["tool_calls"] = processed_tool_calls
            
            processed_messages.append(msg_copy)
        
        return processed_messages

    async def _get_openrouter_response_async(
        self,
        model_name: str,
        messages_payload: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = "auto"
    ) -> Tuple[bool, Optional[str], Optional[List[Dict[str, Any]]], Optional[str]]:
        """Sends a request to OpenRouter asynchronously and returns the result."""
        if not self.api_key:
            return False, None, None, "OpenRouter API key not configured."
        if not messages_payload:
            return False, None, None, "Empty messages_payload."

        try:
            # Step 1: Validate message sequence
            is_valid, validation_error = self._validate_message_sequence(messages_payload)
            if not is_valid:
                logger.error(f"Message validation failed: {validation_error}")
                return False, None, None, f"Message validation failed: {validation_error}"

            # Step 2: Prepare tool calls
            processed_messages = self._prepare_tool_calls_for_api(messages_payload)

            # Step 3: Clean and prepare messages
            final_messages = self._clean_and_prepare_messages(processed_messages)

            # Step 4: Final validation
            if not final_messages:
                return False, None, None, "All messages were filtered out due to empty content"

            # Check for empty content in final messages
            for i, msg in enumerate(final_messages):
                content = msg.get("content")
                role = msg.get("role")
                
                # Allow assistant messages with tool_calls to have None/empty content
                if role == "assistant" and msg.get("tool_calls"):
                    continue
                
                # For Anthropic format, content can be a list of blocks
                if isinstance(content, list) and content:
                    continue
                    
                # Check for truly empty content
                if content is None or (isinstance(content, str) and not content.strip()):
                    logger.error(f"Message {i} has empty content: {msg}")
                    return False, None, None, f"Message {i} has empty content"

            logger.debug(f"Sending {len(final_messages)} messages to OpenRouter model {model_name}")

            # Prepare request payload
            payload_data = {
                "model": model_name,
                "messages": final_messages
            }
            
            if tools:
                payload_data["tools"] = tools
                payload_data["tool_choice"] = tool_choice

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": self.site_url,
                "X-Title": self.site_name,
            }

            # Make the API request
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    json=payload_data,
                    headers=headers
                )
                response.raise_for_status()

                response_json = response.json()
                logger.debug(f"OpenRouter response for model {model_name}: {response_json}")

                # Check for errors in successful HTTP responses
                if response_json.get("error"):
                    error_details = response_json.get("error", {})
                    error_message = error_details.get("message", "Unknown error in response")
                    error_code = error_details.get("code")
                    error_type = error_details.get("type")
                    
                    logger.error(f"OpenRouter API error for {model_name}: {error_message} (code: {error_code}, type: {error_type}). Full response: {response_json}")
                    return False, None, None, error_message

                if response_json.get("choices"):
                    message = response_json["choices"][0]["message"]
                    text_content = message.get("content")
                    tool_calls = message.get("tool_calls")
                    return True, text_content, tool_calls, None
                else:
                    # Log the full response for debugging when there are no choices
                    logger.error(f"OpenRouter response for {model_name} has no choices. Full response: {response_json}")
                    error_details = response_json.get("error", {})
                    error_message = error_details.get("message", "No choices in response")
                    return False, None, None, error_message

        except httpx.HTTPStatusError as e:
            try:
                error_json = e.response.json()
                error_details = error_json.get("error", {})
                error_message = error_details.get("message", str(e))
                error_code = error_details.get("code")
                
                # Ensure error_message is a string and handle mock objects
                if not isinstance(error_message, str):
                    # If we get a mock object or other non-string, fall back to basic error
                    error_message = f"HTTP error: {e.response.status_code}"
                
                # Provide more specific error messages for common issues
                if e.response.status_code == 404:
                    logger.error(f"OpenRouter model not found: {model_name}. Check if the model name is correct. Response: {e.response.text}")
                    error_message = f"Model '{model_name}' not found. Please check the model name is correct."
                elif e.response.status_code == 401:
                    logger.error(f"OpenRouter authentication failed. Check your API key. Response: {e.response.text}")
                    error_message = "Authentication failed. Please check your OpenRouter API key."
                elif e.response.status_code == 429:
                    logger.error(f"OpenRouter rate limit exceeded for model {model_name}. Response: {e.response.text}")
                    error_message = "Rate limit exceeded. Please try again later."
                elif "invalid model" in str(error_message).lower() or "model not found" in str(error_message).lower():
                    logger.error(f"OpenRouter invalid model: {model_name}. Error: {error_message}. Response: {e.response.text}")
                    error_message = f"Invalid model '{model_name}': {error_message}"
                else:
                    # For 500 errors, include the response text
                    if e.response.status_code == 500:
                        response_text = str(e.response.text) if hasattr(e.response, 'text') else ""
                        error_message = f"HTTP error: {e.response.status_code} - {response_text}"
                    logger.error(f"OpenRouter HTTP {e.response.status_code} error for {model_name}: {error_message}. Response: {e.response.text}")
                    
            except (json.JSONDecodeError, AttributeError):
                # Ensure error_message is always a string
                response_text = str(e.response.text) if hasattr(e.response, 'text') else str(e)
                error_message = f"HTTP error: {e.response.status_code} - {response_text}"
                logger.error(f"OpenRouter HTTP error for {model_name}: {error_message}")
            
            return False, None, None, str(error_message)

        except httpx.RequestError as e:
            logger.error(f"Request error for {model_name}: {e}")
            return False, None, None, f"Network error: {str(e)}"

        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error for {model_name}: {e}")
            return False, None, None, f"Invalid JSON response: {str(e)}"

        except Exception as e:
            logger.error(f"Unexpected error for {model_name}: {e}")
            return False, None, None, f"Unexpected error: {str(e)}"

    async def _handle_inference_request(self, request_event: OpenRouterInferenceRequestEvent) -> None:
        """Handles incoming AI inference requests and publishes the response event."""
        tools_payload = request_event.tools
        tool_choice_payload = request_event.tool_choice if request_event.tool_choice else "auto"
        
        success, text_response, tool_calls_data, error_message = await self._get_openrouter_response_async(
            request_event.model_name,
            request_event.messages_payload,
            tools_payload,
            tool_choice_payload
        )
        
        # Parse tool calls into Pydantic models
        parsed_tool_calls: Optional[List[ToolCall]] = None
        if tool_calls_data:
            parsed_tool_calls = []
            for tc_data in tool_calls_data:
                try:
                    function_data = tc_data.get("function", {})
                    arguments_data = function_data.get("arguments")
                    
                    # Parse arguments if they're a JSON string
                    if isinstance(arguments_data, str):
                        try:
                            parsed_arguments = json.loads(arguments_data)
                        except json.JSONDecodeError as e:
                            logger.warning(f"Failed to parse tool call arguments as JSON: {arguments_data}")
                            parsed_arguments = arguments_data
                    else:
                        parsed_arguments = arguments_data

                    parsed_tool_calls.append(
                        ToolCall(
                            id=tc_data.get("id"),
                            type=tc_data.get("type", "function"),
                            function=ToolFunction(
                                name=function_data.get("name"),
                                arguments=parsed_arguments
                            )
                        )
                    )
                except Exception as e:
                    logger.error(f"Error parsing tool call {tc_data}: {e}")
                    continue

        # Determine response event type
        ResponseEventClass = AIInferenceResponseEvent
        if isinstance(request_event, OpenRouterInferenceRequestEvent):
            ResponseEventClass = OpenRouterInferenceResponseEvent

        response_event = ResponseEventClass(
            request_id=request_event.request_id,
            original_request_payload=request_event.original_request_payload,
            success=success,
            text_response=text_response,
            tool_calls=parsed_tool_calls,
            error_message=error_message,
            response_topic=request_event.reply_to_service_event
        )
        
        # Don't modify the frozen event_type field - use response_topic for custom routing instead
        
        logger.info(f"Publishing {ResponseEventClass.__name__} for request {request_event.request_id}. Success: {success}")
        await self.bus.publish(response_event)

    async def run(self) -> None:
        logger.info("AIInferenceService: Starting...")
        self.bus.subscribe(OpenRouterInferenceRequestEvent.get_event_type(), self._handle_inference_request)
        await self._stop_event.wait()
        logger.info("AIInferenceService: Stopped.")

    async def stop(self) -> None:
        logger.info("AIInferenceService: Stop requested.")
        self._stop_event.set()