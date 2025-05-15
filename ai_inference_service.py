import asyncio
import os
import http.client # For OpenRouter
import json
from typing import Dict, List, Optional, Tuple, Any # Added Any
from dotenv import load_dotenv

from message_bus import MessageBus
from event_definitions import AIInferenceRequestEvent, AIInferenceResponseEvent

load_dotenv() # To get OPENROUTER_ configs

class AIInferenceService:
    def __init__(self, message_bus: MessageBus):
        self.bus = message_bus
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        self.site_url = os.getenv("YOUR_SITE_URL", "https://your-matrix-bot.example.com/soa")
        self.site_name = os.getenv("YOUR_SITE_NAME", "MyMatrixBotSOA_AI")
        self._stop_event = asyncio.Event()

    def _get_openrouter_response(self, 
                                 model_name: str, 
                                 messages_payload: List[Dict[str, str]],
                                 tools: Optional[List[Dict[str, Any]]] = None, # Added tools parameter
                                 tool_choice: Optional[str] = "auto" # Added tool_choice
                                 ) -> Tuple[bool, Optional[str], Optional[List[Dict[str, Any]]], Optional[str]]:
        if not self.api_key:
            return False, None, None, "OpenRouter API key not configured."

        if not messages_payload:
            return False, None, None, "Empty messages_payload."

        conn = http.client.HTTPSConnection("openrouter.ai")
        payload_data = {"model": model_name, "messages": messages_payload}
        if tools:
            payload_data["tools"] = tools
            payload_data["tool_choice"] = tool_choice # e.g., "auto", "none", or specific tool
            
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.site_url, "X-Title": self.site_name,
        }
        try:
            conn.request("POST", "/api/v1/chat/completions", json.dumps(payload_data), headers)
            res = conn.getresponse()
            data = res.read()
            response_json = json.loads(data.decode("utf-8"))

            if res.status == 200 and response_json.get("choices"):
                message = response_json["choices"][0]["message"]
                text_content = message.get("content")
                tool_calls = message.get("tool_calls")
                return True, text_content, tool_calls, None
            else:
                error_details = response_json.get("error", {})
                error_message = error_details.get("message", f"Unknown error (Status: {res.status})")
                print(f"AIInfer: Error from OpenRouter ({model_name}): {res.status} - {error_message} - Resp: {response_json}")
                return False, None, None, error_message
        except Exception as e:
            print(f"AIInfer: Exception connecting to OpenRouter ({model_name}): {e}")
            return False, None, None, str(e)
        finally:
            conn.close()

    async def _handle_inference_request(self, request_event: AIInferenceRequestEvent):
        # print(f"AIInfer: Received inference request {request_event.request_id} for model {request_event.model_name}")
        
        tools_payload = request_event.tools
        tool_choice_payload = request_event.tool_choice if request_event.tool_choice else "auto"

        loop = asyncio.get_event_loop()
        success, text_response, tool_calls, error_message = await loop.run_in_executor(
            None, 
            self._get_openrouter_response, 
            request_event.model_name, 
            request_event.messages_payload,
            tools_payload, # Pass tools to the API call
            tool_choice_payload # Pass tool_choice to the API call
        )
        
        response_event = AIInferenceResponseEvent(
            request_id=request_event.request_id,
            original_request_payload=request_event.original_request_payload,
            success=success,
            text_response=text_response,
            tool_calls=tool_calls, # Add tool_calls to the response event
            error_message=error_message
        )
        response_event.event_type = request_event.reply_to_service_event
        await self.bus.publish(response_event)
        # print(f"AIInfer: Published AIInferenceResponseEvent (as {response_event.event_type}) for request {request_event.request_id}. Success: {success}")


    async def run(self):
        print("AIInferenceService: Starting...")
        self.bus.subscribe(AIInferenceRequestEvent.model_fields['event_type'].default, self._handle_inference_request)
        await self._stop_event.wait() # Keep running until stop is called
        print("AIInferenceService: Stopped.")

    async def stop(self):
        print("AIInferenceService: Stop requested.")
        self._stop_event.set()