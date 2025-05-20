import asyncio
import os
import httpx  # Added for asynchronous HTTP calls
import json
import logging
from typing import Dict, List, Optional, Tuple, Any
from dotenv import load_dotenv

from message_bus import MessageBus
from event_definitions import OpenRouterInferenceRequestEvent, AIInferenceResponseEvent, ToolCall, ToolFunction, OpenRouterInferenceResponseEvent  # MODIFIED import

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

    async def _get_openrouter_response_async(
        self,
        model_name: str,
        messages_payload: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = "auto"
    ) -> Tuple[bool, Optional[str], Optional[List[Dict[str, Any]]], Optional[str]]:
        """Sends a request to OpenRouter asynchronously and returns the result."""
        if not self.api_key:
            return False, None, None, "OpenRouter API key not configured."
        if not messages_payload:
            return False, None, None, "Empty messages_payload."

        # Preprocess messages_payload to ensure ToolCall objects are JSON serializable
        processed_messages_payload = []
        for message in messages_payload:
            new_message = message.copy() # Work on a copy
            if new_message.get("role") == "assistant" and "tool_calls" in new_message and new_message["tool_calls"] is not None:
                processed_tool_calls = []
                for tc in new_message["tool_calls"]:
                    # Ensure tc is a dictionary, as it might be a Pydantic model (ToolCall)
                    tc_dict = tc if isinstance(tc, dict) else tc.model_dump(mode='json')
                    
                    function_data = tc_dict.get("function", {})
                    arguments_data = function_data.get("arguments")

                    # Ensure arguments are a JSON string for OpenRouter
                    if isinstance(arguments_data, dict) or isinstance(arguments_data, list): # Added list
                        stringified_arguments = json.dumps(arguments_data)
                    elif arguments_data is None: 
                        stringified_arguments = json.dumps({}) 
                    else: 
                        stringified_arguments = str(arguments_data)

                    processed_tool_calls.append({
                        "id": tc_dict.get("id"),
                        "type": tc_dict.get("type"),
                        "function": {
                            "name": function_data.get("name"),
                            "arguments": stringified_arguments
                        }
                    })
                new_message["tool_calls"] = processed_tool_calls
                # Explicitly set content to None if only tool_calls are present and content is not already set (or is empty string)
                # This is a safeguard; primary logic for this should be upstream when message is created.
                if not new_message.get("content"): # If content is None or empty string
                    new_message["content"] = None
            
            processed_messages_payload.append(new_message)

        # --- BEGIN PRE-FLIGHT CHECK for tool call structure ---
        # This check ensures that assistant messages with tool_calls are correctly followed by tool responses.
        # It operates on processed_messages_payload, which should have arguments stringified.
        active_assistant_tool_calls_ids = set()
        for i, msg in enumerate(processed_messages_payload):
            role = msg.get("role")

            if active_assistant_tool_calls_ids: # We are expecting tool responses
                if role == "tool":
                    tc_id = msg.get("tool_call_id")
                    if tc_id in active_assistant_tool_calls_ids:
                        active_assistant_tool_calls_ids.remove(tc_id)
                    else:
                        error_msg = f"Pre-flight check failed: Encountered tool message with unexpected tool_call_id '{tc_id}' at index {i}. Expected one of {active_assistant_tool_calls_ids}."
                        logger.error(f"{error_msg} History: {json.dumps(processed_messages_payload, indent=2)}")
                        return False, None, None, error_msg
                else: # A non-tool message appeared before all expected tool responses were found
                    error_msg = f"Pre-flight check failed: Assistant message at an earlier index made tool calls (missing responses for {active_assistant_tool_calls_ids}), but message at index {i} has role '{role}' instead of 'tool'."
                    logger.error(f"{error_msg} History: {json.dumps(processed_messages_payload, indent=2)}")
                    return False, None, None, error_msg
            
            if role == "assistant":
                if active_assistant_tool_calls_ids: # Should have been cleared by tool responses or a non-tool message
                    # This implies an assistant message was followed by another assistant message, but tool responses were still pending.
                    error_msg = f"Pre-flight check failed: New assistant message at index {i} found, but previous assistant message's tool calls were not all addressed (missing responses for {active_assistant_tool_calls_ids})."
                    logger.error(f"{error_msg} History: {json.dumps(processed_messages_payload, indent=2)}")
                    return False, None, None, error_msg

                current_tool_calls = msg.get("tool_calls")
                if current_tool_calls and isinstance(current_tool_calls, list):
                    # This assistant message is making tool calls.
                    # Note: tool_calls here should already be processed dicts with stringified arguments.
                    for tc in current_tool_calls:
                        if isinstance(tc, dict) and tc.get("id") and tc.get("type") == "function":
                            active_assistant_tool_calls_ids.add(tc["id"])
                        else:
                            error_msg = f"Pre-flight check failed: Assistant message at index {i} has malformed tool_call entry: {tc}."
                            logger.error(f"{error_msg} History: {json.dumps(processed_messages_payload, indent=2)}")
                            return False, None, None, error_msg
                    
                    if not active_assistant_tool_calls_ids and current_tool_calls: # e.g. tool_calls was [{}] (list of empty dicts)
                        # This means tool_calls array was present but contained no valid tool calls with IDs.
                        # This is usually fine if the list is empty, but if not empty and no IDs, it's odd.
                        # For an empty list `[]`, active_assistant_tool_calls_ids would be empty, and this block is fine.
                        pass # No actual tool calls to track.
                    elif active_assistant_tool_calls_ids and (i == len(processed_messages_payload) - 1):
                        # Last message is an assistant making tool calls, but no tool responses can follow.
                        error_msg = f"Pre-flight check failed: Last message (index {i}) is an assistant message making tool calls (IDs: {active_assistant_tool_calls_ids}), but no tool responses follow."
                        logger.error(f"{error_msg} History: {json.dumps(processed_messages_payload, indent=2)}")
                        return False, None, None, error_msg
        
        # After iterating through all messages, if there are still active_assistant_tool_calls_ids, it means the history ended without satisfying them.
        if active_assistant_tool_calls_ids:
            error_msg = f"Pre-flight check failed: Message history ends but assistant tool calls are still pending responses for IDs: {active_assistant_tool_calls_ids}."
            logger.error(f"{error_msg} History: {json.dumps(processed_messages_payload, indent=2)}")
            return False, None, None, error_msg
        # --- END PRE-FLIGHT CHECK ---

        payload_data = {"model": model_name, "messages": processed_messages_payload}
        if tools:
            payload_data["tools"] = tools
            payload_data["tool_choice"] = tool_choice
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.site_url, 
            "X-Title": self.site_name,
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    json=payload_data,
                    headers=headers,
                    timeout=30.0  # Added a timeout
                )
                response.raise_for_status()  # Raises an HTTPStatusError for 4XX/5XX responses
                
                response_json = response.json()
                logger.info(f"AIS: OpenRouter raw response data: {response_json}") # ADDED
                
                if response_json.get("choices"):
                    message = response_json["choices"][0]["message"]
                    text_content = message.get("content")
                    tool_calls = message.get("tool_calls")
                    return True, text_content, tool_calls, None
                else:
                    # This case might be less likely if choices are always present on 200 OK
                    error_details = response_json.get("error", {})
                    error_message = error_details.get("message", "Unknown error (No choices in response)")
                    logger.error(f"OpenRouter error ({model_name}): No choices in response - Resp: {response_json}")
                    return False, None, None, error_message

            except httpx.HTTPStatusError as e:
                error_message = f"HTTP error: {e.response.status_code} - {e.response.text}"
                try:
                    # Attempt to parse more specific error from response body
                    error_json = e.response.json()
                    if error_json and "error" in error_json and "message" in error_json["error"]:
                        error_message = error_json["error"]["message"]
                except json.JSONDecodeError:
                    pass  # Stick with the text version if JSON parsing fails
                logger.error(f"OpenRouter HTTPStatusError ({model_name}): {e.response.status_code} - {error_message} - Full Response: {e.response.text}")
                return False, None, None, error_message
            except httpx.RequestError as e:  # Catches network errors, timeouts, etc.
                logger.error(f"Exception connecting to OpenRouter ({model_name}) with httpx: {type(e).__name__} - {e}")
                return False, None, None, f"RequestError: {str(e)}"
            except json.JSONDecodeError as e:  # If response is not valid JSON
                logger.error(f"Failed to decode JSON response from OpenRouter ({model_name}): {e}")
                return False, None, None, f"JSONDecodeError: {str(e)}"
            except Exception as e:  # Catch-all for other unexpected errors
                logger.error(f"Unexpected exception in _get_openrouter_response_async ({model_name}): {type(e).__name__} - {e}")
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
        
        parsed_tool_calls: Optional[List[ToolCall]] = None
        if tool_calls_data:
            parsed_tool_calls = []
            for tc_data in tool_calls_data:
                function_data = tc_data.get("function", {})
                arguments_data = function_data.get("arguments")
                parsed_arguments = None
                if isinstance(arguments_data, str):
                    try:
                        parsed_arguments = json.loads(arguments_data)
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse tool call arguments JSON: {arguments_data} - Error: {e}")
                        parsed_arguments = arguments_data 
                else:
                    parsed_arguments = arguments_data

                parsed_tool_calls.append(
                    ToolCall(
                        id=tc_data.get("id"),
                        type=tc_data.get("type"),
                        function=ToolFunction(
                            name=function_data.get("name"),
                            arguments=parsed_arguments
                        )
                    )
                )

        # Determine the correct response event type
        ResponseEventClass = AIInferenceResponseEvent # Default
        if isinstance(request_event, OpenRouterInferenceRequestEvent):
            ResponseEventClass = OpenRouterInferenceResponseEvent
        # Add other specific request types here if needed, e.g.:
        # elif isinstance(request_event, OllamaInferenceRequestEvent):
        #     ResponseEventClass = OllamaInferenceResponseEvent

        response_event = ResponseEventClass(
            request_id=request_event.request_id,
            original_request_payload=request_event.original_request_payload,
            success=success,
            text_response=text_response,
            tool_calls=parsed_tool_calls,
            error_message=error_message,
            response_topic=request_event.reply_to_service_event
        )
        logger.info(f"AIS: Publishing {ResponseEventClass.__name__} for request {request_event.request_id}. Success: {success}, EventTypeForBus: {response_event.event_type}, ResponseTopicForHandler: {response_event.response_topic}") # MODIFIED logging
        await self.bus.publish(response_event)

    async def run(self) -> None:
        logger.info("AIInferenceService: Starting...")
        # Access default from model_fields for subscription
        self.bus.subscribe(OpenRouterInferenceRequestEvent.model_fields['event_type'].default, self._handle_inference_request)
        await self._stop_event.wait()
        logger.info("AIInferenceService: Stopped.")

    async def stop(self) -> None:
        logger.info("AIInferenceService: Stop requested.")
        self._stop_event.set()