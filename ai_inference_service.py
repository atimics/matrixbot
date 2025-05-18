import asyncio
import os
import httpx  # Added for asynchronous HTTP calls
import json
import logging
from typing import Dict, List, Optional, Tuple, Any
from dotenv import load_dotenv

from message_bus import MessageBus
from event_definitions import OpenRouterInferenceRequestEvent, OpenRouterInferenceResponseEvent, ToolCall, ToolFunction  # Added ToolCall, ToolFunction

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

        payload_data = {"model": model_name, "messages": messages_payload}
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
        
        # No longer need loop.run_in_executor as _get_openrouter_response_async is now async
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
                parsed_tool_calls.append(
                    ToolCall(
                        id=tc_data.get("id"),
                        type=tc_data.get("type"),
                        function=ToolFunction(
                            name=function_data.get("name"),
                            arguments=function_data.get("arguments")
                        )
                    )
                )

        response_event = OpenRouterInferenceResponseEvent(
            request_id=request_event.request_id,
            original_request_payload=request_event.original_request_payload,
            success=success,
            text_response=text_response,
            tool_calls=parsed_tool_calls,  # Use parsed Pydantic models
            error_message=error_message,
            event_type=request_event.reply_to_service_event  # Pass event_type here
        )
        await self.bus.publish(response_event)

    async def run(self) -> None:
        logger.info("AIInferenceService: Starting...")
        # Access default from model_fields for subscription
        self.bus.subscribe(OpenRouterInferenceRequestEvent.model_fields['event_type'].default, self._handle_inference_request)  # Removed await
        await self._stop_event.wait()
        logger.info("AIInferenceService: Stopped.")

    async def stop(self) -> None:
        logger.info("AIInferenceService: Stop requested.")
        self._stop_event.set()