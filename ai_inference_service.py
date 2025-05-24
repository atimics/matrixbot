import asyncio
import os
import httpx  # Added for asynchronous HTTP calls
import json
import logging
from typing import Dict, List, Optional, Tuple, Any
from dotenv import load_dotenv

from message_bus import MessageBus
from event_definitions import (
    OpenRouterInferenceRequestEvent,
    OpenRouterInferenceResponseEvent,
    ToolCall,
    ToolFunction
)

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

    def _prepare_messages_for_api(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Clean and prepare messages for the OpenRouter API, relying on OpenRouter's normalization."""
        prepared = []
        system_content = []
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content")

            if role == "system" and isinstance(content, str) and content.strip():
                system_content.append(content.strip())
                continue

            # Skip empty text messages
            if role != "assistant" and (not content or (isinstance(content, str) and not content.strip())):
                continue

            # Normalize content
            msg_copy = {"role": role}
            if isinstance(content, list):
                msg_copy["content"] = [block for block in content if block]
            else:
                msg_copy["content"] = content.strip() if isinstance(content, str) else content

            # Preserve tool_calls on assistant messages
            if role == "assistant" and msg.get("tool_calls"):
                msg_copy["tool_calls"] = msg["tool_calls"]

            # Preserve tool_call_id on tool messages
            if role == "tool" and msg.get("tool_call_id"):
                msg_copy["tool_call_id"] = msg["tool_call_id"]

            prepared.append(msg_copy)

        if system_content:
            prepared.insert(0, {"role": "system", "content": "\n\n".join(system_content)})
        return prepared

    def _prepare_tool_calls_for_api(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Ensure tool calls are properly formatted for the OpenRouter API."""
        processed = []
        for msg in messages:
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                formatted_calls = []
                for tc in msg["tool_calls"]:
                    tc_dict = tc if isinstance(tc, dict) else tc.model_dump(mode='json')
                    func = tc_dict.get("function", {})
                    args = func.get("arguments")
                    formatted_calls.append({
                        "id": tc_dict.get("id"),
                        "type": tc_dict.get("type", "function"),
                        "function": {
                            "name": func.get("name"),
                            "arguments": json.dumps(args) if isinstance(args, (dict, list)) else str(args or "{}")
                        }
                    })
                msg = msg.copy()
                msg["tool_calls"] = formatted_calls
            processed.append(msg)
        return processed

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

        # Clean and prepare messages
        prepared = self._prepare_messages_for_api(messages_payload)
        # Format any tool calls
        final_msgs = self._prepare_tool_calls_for_api(prepared)

        payload = {"model": model_name, "messages": final_msgs}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.site_url,
            "X-Title": self.site_name,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    json=payload,
                    headers=headers
                )
                response.raise_for_status()
                result = response.json()

                if error := result.get("error"):
                    msg = error.get("message", "Unknown error in response")
                    logger.error(f"OpenRouter API error for {model_name}: {msg}. Full response: {result}")
                    return False, None, None, msg

                choices = result.get("choices", [])
                if not choices:
                    logger.error(f"OpenRouter response for {model_name} has no choices. Full response: {result}")
                    return False, None, None, "No choices in response"

                choice = choices[0]
                message = choice.get("message", {})
                content = message.get("content")
                tool_calls = message.get("tool_calls")
                
                logger.debug(f"OpenRouter response for model {model_name}: success")
                return True, content, tool_calls, None

        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            detail = ""
            try:
                error_json = e.response.json()
                error_detail = error_json.get("error", {}).get("message", "")
                if error_detail and isinstance(error_detail, str):
                    detail = error_detail
                else:
                    # Fallback to response text if no valid error message in JSON
                    detail = e.response.text
            except Exception:
                detail = e.response.text
            
            if status == 401:
                logger.error(f"OpenRouter authentication failed. Check your API key. Response: {e.response.text}")
                return False, None, None, "Authentication failed. Check your OpenRouter API key."
            elif status == 404:
                logger.error(f"OpenRouter model not found: {model_name}. Response: {e.response.text}")
                return False, None, None, f"Model '{model_name}' not found. Please check the model name is correct."
            elif status == 429:
                logger.error(f"OpenRouter rate limit exceeded for model {model_name}. Response: {e.response.text}")
                return False, None, None, "Rate limit exceeded. Please try again later."
            else:
                logger.error(f"OpenRouter HTTP {status} error for {model_name}: {detail}. Response: {e.response.text}")
                return False, None, None, f"HTTP error: {status} - {detail}"
                
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
        success, text, tool_calls, error = await self._get_openrouter_response_async(
            request_event.model_name,
            request_event.messages_payload,
            request_event.tools,
            request_event.tool_choice or "auto"
        )

        parsed_calls = None
        if tool_calls:
            parsed_calls = []
            for tc in tool_calls:
                try:
                    func = tc.get("function", {})
                    args = func.get("arguments")
                    try:
                        parsed_args = json.loads(args) if isinstance(args, str) else args
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse tool call arguments as JSON: {args}")
                        parsed_args = args
                    
                    parsed_calls.append(
                        ToolCall(
                            id=tc.get("id"),
                            type=tc.get("type", "function"),
                            function=ToolFunction(name=func.get("name"), arguments=parsed_args)
                        )
                    )
                except Exception as e:
                    logger.error(f"Error parsing tool call {tc}: {e}")
                    continue

        response_event = OpenRouterInferenceResponseEvent(
            request_id=request_event.request_id,
            original_request_payload=request_event.original_request_payload,
            success=success,
            text_response=text,
            tool_calls=parsed_calls,
            error_message=error,
            response_topic=request_event.reply_to_service_event
        )

        logger.info(f"Publishing OpenRouterInferenceResponseEvent for {request_event.request_id}, success={success}")
        await self.bus.publish(response_event)

    async def run(self) -> None:
        logger.info("AIInferenceService: Starting...")
        self.bus.subscribe(
            OpenRouterInferenceRequestEvent.get_event_type(),
            self._handle_inference_request
        )
        await self._stop_event.wait()
        logger.info("AIInferenceService: Stopped.")

    async def stop(self) -> None:
        logger.info("AIInferenceService: Stop requested.")
        self._stop_event.set()