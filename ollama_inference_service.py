# ollama_inference_service.py
import asyncio
import os
import logging
import ollama
import uuid # Added import for uuid
from typing import Dict, List, Optional, Tuple, Any

from message_bus import MessageBus
from event_definitions import OllamaInferenceRequestEvent, OllamaInferenceResponseEvent

logger = logging.getLogger(__name__)

class OllamaInferenceService:
    def __init__(self, message_bus: MessageBus):
        self.bus = message_bus
        self.api_url = os.getenv("OLLAMA_API_URL", "http://localhost:11434")
        # OLLAMA_KEEP_ALIVE is handled by the ollama library itself if passed during chat/generate
        # self.keep_alive = os.getenv("OLLAMA_KEEP_ALIVE", "5m")
        self._client = ollama.AsyncClient(host=self.api_url) # This is an httpx.AsyncClient
        self._stop_event = asyncio.Event()
        logger.info(f"OllamaInferenceService initialized with API URL: {self.api_url}")

    async def _get_ollama_response(
        self,
        model_name: str,
        messages_payload: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        # tool_choice: Optional[str] = "auto" # Ollama's tool choice might differ or be implicit
        keep_alive: str = "5m" # Default keep_alive for Ollama
    ) -> Tuple[bool, Optional[str], Optional[List[Dict[str, Any]]], Optional[str]]:
        try:
            options = {"keep_alive": keep_alive}
            # The 'ollama' library's chat function takes tools directly.
            # It seems to manage tool_choice implicitly based on the presence of tools.
            response = await self._client.chat(
                model=model_name,
                messages=messages_payload,
                tools=tools if tools else None, # Pass tools if provided
                # options=options # keep_alive can be passed here if needed per call
                keep_alive=keep_alive
            )

            # logger.debug(f"Ollama response: {response}")

            # The response structure for ollama.chat:
            # response['message']['content']
            # response['message']['tool_calls'] (if any)
            message = response.get('message', {})
            text_content = message.get('content')
            ollama_tool_calls = message.get('tool_calls') # This is List[ollama.types.ToolCall]

            # Ensure tool_calls are in the expected format if present
            formatted_tool_calls_list = None
            if ollama_tool_calls:
                formatted_tool_calls_list = []
                for tc_obj in ollama_tool_calls:
                    # tc_obj is an ollama.types.ToolCall object.
                    # We need to convert it to a dictionary structure that
                    # OllamaInferenceResponseEvent and RoomLogicService expect.
                    # Expected structure per RoomLogicService: {'id': '...', 'type': 'function', 'function': {'name': '...', 'arguments': {...}}}
                    if tc_obj and hasattr(tc_obj, 'function') and \
                       hasattr(tc_obj.function, 'name') and \
                       hasattr(tc_obj.function, 'arguments'):
                        # The tc_obj from Ollama library might not have an 'id' or 'type' field directly.
                        # We need to construct a ToolCall Pydantic model or a dict matching its structure.
                        # For simplicity, creating a dict that matches event_definitions.ToolCall structure.
                        # A random ID can be generated if not provided by Ollama's tc_obj.
                        tool_call_id = f"ollama_tool_{uuid.uuid4()}" # Generate an ID
                        formatted_tool_calls_list.append({
                            "id": tool_call_id, # Added ID
                            "type": "function", # Assuming type is always function
                            "function": {
                                "name": tc_obj.function.name,
                                "arguments": tc_obj.function.arguments # This should be a dict
                            }
                        })


            if not text_content and not formatted_tool_calls_list:
                logger.warning(f"Ollama model {model_name} returned no content and no tool calls.")
                # This might be acceptable if the model deliberately chooses to do nothing.

            return True, text_content, formatted_tool_calls_list, None

        except ollama.ResponseError as e:
            logger.error(f"Ollama API ResponseError for model {model_name}: {e.status_code} - {e.error}")
            return False, None, None, f"Ollama API Error: {e.error}"
        except Exception as e:
            logger.error(f"Exception connecting to Ollama ({model_name}): {type(e).__name__} - {e}")
            return False, None, None, str(e)

    async def _handle_inference_request(self, request_event: OllamaInferenceRequestEvent):
        # logger.debug(f"OllamaInfer: Received inference request {request_event.request_id} for model {request_event.model_name}")
        # logger.debug(f"OllamaInfer: Payload: {request_event.messages_payload}")
        # logger.debug(f"OllamaInfer: Tools: {request_event.tools}")

        success, text_response, tool_calls, error_message = await self._get_ollama_response(
            model_name=request_event.model_name, # Model name comes from the request
            messages_payload=request_event.messages_payload,
            tools=request_event.tools
            # keep_alive can be configured globally or per call
        )

        response_event = OllamaInferenceResponseEvent(
            request_id=request_event.request_id,
            original_request_payload=request_event.original_request_payload,
            success=success,
            text_response=text_response,
            tool_calls=tool_calls, # Pass Ollama's tool_calls structure
            error_message=error_message
        )
        response_event.event_type = request_event.reply_to_service_event
        await self.bus.publish(response_event)
        # logger.debug(f"OllamaInfer: Published AIInferenceResponseEvent (as {response_event.event_type}) for request {request_event.request_id}. Success: {success}")


    async def run(self):
        logger.info("OllamaInferenceService: Starting...")
        self.bus.subscribe(OllamaInferenceRequestEvent.get_event_type(), self._handle_inference_request)
        
        try:
            await self._stop_event.wait()
        finally:
            logger.info("OllamaInferenceService: Stop event received, cleaning up...")
            if self._client: # self._client is an ollama.AsyncClient
                try:
                    await self._client.aclose() # Use the httpx.AsyncClient's aclose() method
                    logger.info("OllamaInferenceService: Ollama client session closed.")
                except Exception as e:
                    logger.error(f"OllamaInferenceService: Error closing Ollama client session: {e}")
        logger.info("OllamaInferenceService: Stopped.")

    async def stop(self):
        logger.info("OllamaInferenceService: Stop requested.")
        self._stop_event.set()
        # The run method's finally block will now handle client closing.
