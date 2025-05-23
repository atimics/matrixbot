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

        # --- BEGIN PAYLOAD CORRECTION AND VALIDATION ---
        # This section ensures that assistant messages with tool_calls are correctly followed by tool responses.
        # If responses are missing, stubs are inserted.
        # If tool messages are malformed or unexpected, the request will fail.

        corrected_messages_payload = []
        # Stores IDs of tool calls made by the last assistant message, awaiting responses.
        pending_tool_ids_from_assistant = set()

        original_payload_for_logging = processed_messages_payload # Keep a reference for logging errors

        for i, current_message in enumerate(processed_messages_payload):
            current_role = current_message.get("role")

            # If the current message is not a tool message, it means any tool calls
            # expected from a *previous* assistant message that were not yet met must now be stubbed.
            if current_role != "tool":
                if pending_tool_ids_from_assistant:
                    for tool_id_to_stub in list(pending_tool_ids_from_assistant): # Iterate over a copy for modification
                        stub_content = json.dumps({
                            "status": "stubbed_by_preflight_check",
                            "reason": f"Expected tool response for call_id '{tool_id_to_stub}' was missing before a subsequent '{current_role}' message at index {i}."
                        })
                        stub_message = {"role": "tool", "tool_call_id": tool_id_to_stub, "content": stub_content}
                        corrected_messages_payload.append(stub_message)
                        logger.warning(f"AIS Pre-flight: Inserted stub for missing tool response (ID: {tool_id_to_stub}) before message index {i} ('{current_role}').")
                    pending_tool_ids_from_assistant.clear()

            # Now, process the current_message itself
            if current_role == "assistant":
                corrected_messages_payload.append(current_message)
                # This assistant message might make new tool calls.
                # Any previous pending_tool_ids should have been cleared and stubbed above.
                # So, pending_tool_ids_from_assistant should be empty here before repopulating.
                
                assistant_tool_calls = current_message.get("tool_calls")
                if assistant_tool_calls and isinstance(assistant_tool_calls, list):
                    for tc in assistant_tool_calls:
                        # Ensure tc is a dictionary, as it might be a Pydantic model (ToolCall)
                        # This should have been handled by the initial processing loop already,
                        # but double-check tc structure if issues persist.
                        # For this logic, we assume tc is a dict as per OpenRouter's expected format.
                        if isinstance(tc, dict) and tc.get("id") and tc.get("type") == "function":
                            pending_tool_ids_from_assistant.add(tc["id"])
                        else:
                            # This assistant message itself has a malformed tool_call. This is a fatal error.
                            error_msg = f"Pre-flight check failed: Assistant message at index {i} has malformed tool_call entry: {tc}."
                            logger.error(f"{error_msg} Original History Segment: {json.dumps(original_payload_for_logging, indent=2)}")
                            return False, None, None, error_msg
            
            elif current_role == "tool":
                tool_call_id = current_message.get("tool_call_id")
                if tool_call_id and tool_call_id in pending_tool_ids_from_assistant:
                    corrected_messages_payload.append(current_message)
                    pending_tool_ids_from_assistant.remove(tool_call_id)
                else:
                    # This tool message is unexpected (no matching pending call_id from an assistant)
                    # or malformed (e.g., missing tool_call_id). This is a fatal error for the request.
                    error_msg = (f"Pre-flight check failed: Encountered tool message at index {i} with "
                                 f"tool_call_id '{tool_call_id}' which was not pending or ID is missing. "
                                 f"Currently pending IDs from assistant: {pending_tool_ids_from_assistant}.")
                    logger.error(f"{error_msg} Original History Segment: {json.dumps(original_payload_for_logging, indent=2)}")
                    return False, None, None, error_msg
            
            else: # Handles "user", "system", or any other roles
                corrected_messages_payload.append(current_message)
                # If we reached here, pending_tool_ids_from_assistant should be empty due to the check
                # at the beginning of the loop for non-tool messages.

        # After iterating through all messages, if there are still pending_tool_ids,
        # it means the history ended with an assistant message making tool calls that were not responded to.
        # These must be stubbed.
        if pending_tool_ids_from_assistant:
            for tool_id_to_stub in list(pending_tool_ids_from_assistant): # Iterate over a copy
                stub_content = json.dumps({
                    "status": "stubbed_by_preflight_check",
                    "reason": f"Expected tool response for call_id '{tool_id_to_stub}' was missing at the end of the message history."
                })
                stub_message = {"role": "tool", "tool_call_id": tool_id_to_stub, "content": stub_content}
                corrected_messages_payload.append(stub_message)
                logger.warning(f"AIS Pre-flight: Inserted stub for missing tool response (ID: {tool_id_to_stub}) at end of history.")
            pending_tool_ids_from_assistant.clear()

        # Use the corrected payload for the API call
        processed_messages_payload = corrected_messages_payload 
        # --- END PAYLOAD CORRECTION AND VALIDATION ---

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
        self.bus.subscribe(OpenRouterInferenceRequestEvent.get_event_type(), self._handle_inference_request)
        await self._stop_event.wait()
        logger.info("AIInferenceService: Stopped.")

    async def stop(self) -> None:
        logger.info("AIInferenceService: Stop requested.")
        self._stop_event.set()