import asyncio
import os
import http.client # For OpenRouter
import json
from typing import Dict, List, Optional, Tuple # For OpenRouter
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

    def _get_openrouter_response(self, model_name: str, messages_payload: List[Dict[str, str]]) -> Tuple[bool, Optional[str], Optional[str]]:
        if not self.api_key:
            return False, None, "OpenRouter API key not configured."

        if not messages_payload:
            return False, None, "Empty messages_payload."

        conn = http.client.HTTPSConnection("openrouter.ai")
        payload_data = {"model": model_name, "messages": messages_payload}
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.site_url, "X-Title": self.site_name,
        }
        try:
            # print(f"AIInfer: Requesting from OpenRouter model {model_name}. Msgs: {len(messages_payload)}")
            conn.request("POST", "/api/v1/chat/completions", json.dumps(payload_data), headers)
            res = conn.getresponse()
            data = res.read()
            response_json = json.loads(data.decode("utf-8"))

            if res.status == 200 and response_json.get("choices"):
                return True, response_json["choices"][0]["message"]["content"], None
            else:
                error_details = response_json.get("error", {})
                error_message = error_details.get("message", f"Unknown error (Status: {res.status})")
                print(f"AIInfer: Error from OpenRouter ({model_name}): {res.status} - {error_message} - Resp: {response_json}")
                return False, None, error_message
        except Exception as e:
            print(f"AIInfer: Exception connecting to OpenRouter ({model_name}): {e}")
            return False, None, str(e)
        finally:
            conn.close()

    async def _handle_inference_request(self, request_event: AIInferenceRequestEvent):
        # print(f"AIInfer: Received inference request {request_event.request_id} for model {request_event.model_name}")
        
        # Run synchronous HTTP call in a separate thread to avoid blocking asyncio loop
        loop = asyncio.get_event_loop()
        success, text_response, error_message = await loop.run_in_executor(
            None, # Uses default ThreadPoolExecutor
            self._get_openrouter_response, 
            request_event.model_name, 
            request_event.messages_payload
        )
        
        response_event = AIInferenceResponseEvent(
            request_id=request_event.request_id,
            original_request_payload=request_event.original_request_payload, # Pass through
            success=success,
            text_response=text_response,
            error_message=error_message
        )
        # Publish to a general AI response topic, or a specific one if `reply_to_service_event` is used more directly
        # For now, let's assume services listen on a general AI response topic and filter by request_id
        # or by a field in original_request_payload.
        # A simpler way: the requester specified which event type it's waiting for as a response.
        # So, publish to that event type.
        response_event.event_type = request_event.reply_to_service_event # Crucial for routing back
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