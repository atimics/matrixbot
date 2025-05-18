import asyncio
import logging
import uuid
import json # For argument parsing if needed
from typing import Dict, Any, List, Optional

from tool_base import AbstractTool, ToolResult
from event_definitions import OpenRouterInferenceRequestEvent, BaseEvent

logger = logging.getLogger(__name__)

# Unique event type for this tool to listen for OpenRouter's response
DELEGATED_OPENROUTER_RESPONSE_EVENT_TYPE = "delegated_openrouter_response_for_tool"

class DelegateToOpenRouterTool(AbstractTool):
    """Delegates a query to a powerful cloud-based LLM via OpenRouter."""

    def __init__(self):
        super().__init__()
        # This tool will need access to the message bus to publish the OpenRouterInferenceRequestEvent
        # and to potentially listen for a response. This is a complex part.
        # For Option B (ToolExecutionService manages), this tool might not need the bus directly.
        # Let's assume Option B for now, where ToolExecutionService handles the async flow.
        self.openrouter_chat_model_default = "openai/gpt-4o-mini" # A sensible default

    def get_definition(self) -> Dict[str, Any]:
        # This is the schema currently in RoomLogicService._openrouter_tool_definition
        return {
            "type": "function",
            "function": {
                "name": "call_openrouter_llm",
                "description": "Delegates a complex query or a query requiring specific capabilities to a powerful cloud-based LLM (OpenRouter). Use this for tasks that local models might struggle with or for accessing specific proprietary models.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "model_name": {
                            "type": "string",
                            "description": "The specific OpenRouter model to use (e.g., 'openai/gpt-4o', 'anthropic/claude-3-opus'). If unsure, a default powerful model will be selected."
                        },
                        "messages_payload": {
                            "type": "array",
                            "description": "The conversation history and prompt to send to the OpenRouter LLM, in OpenAI message format.",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "role": {"type": "string", "enum": ["system", "user", "assistant"]},
                                    "content": {"type": "string"}
                                },
                                "required": ["role", "content"]
                            }
                        },
                        "prompt_text": {
                            "type": "string",
                            "description": "Alternatively, provide a single prompt text. If 'messages_payload' is given, this is ignored."
                        }
                    },
                    "required": [] # Flexible: either messages_payload or prompt_text
                }
            }
        }

    async def execute(
        self,
        room_id: str,
        arguments: Dict[str, Any],
        tool_call_id: Optional[str],
        llm_provider_info: Dict[str, Any],
        conversation_history_snapshot: List[Dict[str, Any]],
        last_user_event_id: Optional[str],
        db_path: Optional[str] = None # Added to accept db_path
    ) -> ToolResult:
        logger.info(f"DelegateToOpenRouterTool: Executing for room {room_id}, call_id {tool_call_id}")

        model_name = arguments.get("model_name") or self.openrouter_chat_model_default
        messages_payload = arguments.get("messages_payload")
        prompt_text = arguments.get("prompt_text")

        if not messages_payload and prompt_text:
            # Construct a simple user message if only prompt_text is provided
            # Consider if a system prompt should be prepended from conversation_history_snapshot or a default one.
            # For now, just use the prompt_text as user content.
            messages_payload = [{"role": "user", "content": prompt_text}]
        elif not messages_payload and not prompt_text:
            return ToolResult(
                status="failure",
                result_for_llm_history="[Tool call_openrouter_llm failed: Missing 'messages_payload' or 'prompt_text'.]",
                error_message="call_openrouter_llm tool requires either 'messages_payload' or 'prompt_text' argument."
            )
        
        # The tool needs to pass along information so that when OpenRouter responds,
        # the ToolExecutionService (or RoomLogicService) can correlate it back to this specific tool call
        # and the original LLM that requested it.
        delegated_request_id = str(uuid.uuid4())

        # This payload will be part of the OpenRouterInferenceRequestEvent's original_request_payload.
        # It helps the service that handles the OpenRouterInferenceResponseEvent to know the context.
        payload_for_openrouter_response_handler = {
            "original_calling_llm_provider": llm_provider_info, # e.g., {"name": "ollama", "model": "llama3"}
            "original_tool_call_id": tool_call_id, # The ID of *this* tool call from the primary LLM
            "original_room_id": room_id,
            # Pass the original ExecuteToolRequest's payload through, so ToolExecutionService can construct the final ToolExecutionResponse correctly.
            "original_execute_tool_request_payload": {
                # We need to reconstruct or pass through the original ExecuteToolRequest's payload.
                # This is crucial. The ExecuteToolRequest object itself isn't available here.
                # We have its components: room_id, tool_name (is "call_openrouter_llm"), tool_call_id, arguments, original_request_payload (from AIInferenceResponseEvent),
                # llm_provider_info, conversation_history_snapshot, last_user_event_id.
                # The most important part to pass through is `original_request_payload` of the ExecuteToolRequest,
                # which is the `original_request_payload` from the AIInferenceResponseEvent that triggered the tool call.
                # Let's assume the `ExecuteToolRequest` that led to this `DelegateToOpenRouterTool.execute()` call
                # had an `original_request_payload` field. We need to ensure that this field (which came from the AI response)
                # is correctly passed to the final ToolExecutionResponse.
                # The `request_event.original_request_payload` in `ToolExecutionService._handle_execute_tool_request`
                # is what we need to preserve.
                # So, `DelegateToOpenRouterTool` needs to receive it and pass it here.

                # Let's refine: `payload_for_openrouter_response_handler` needs to store the `original_request_payload`
                # that `ExecuteToolRequest` itself had. This is `request_event.original_request_payload` in the calling context.
                # We need to add a parameter to `execute()` or ensure this is passed via `llm_provider_info` or another field if it contains it.
                # The `ExecuteToolRequest` has `original_request_payload: Dict[str, Any]`. This is what needs to be preserved.
                # Let's assume `ExecuteToolRequest.original_request_payload` is passed to this tool, perhaps as `initial_execute_request_payload`
                "room_id": room_id, # This is `request_event.room_id`
                "tool_name": "call_openrouter_llm", # This is `request_event.tool_name`
                "tool_call_id": tool_call_id, # This is `request_event.tool_call_id`
                "arguments": arguments, # This is `request_event.arguments`
                # THIS IS THE KEY: The `original_request_payload` of the ExecuteToolRequest that initiated this tool.
                # This field must be added to the `execute` method's signature or passed via a dict.
                # For now, we assume it's passed as `initial_execute_request_payload` argument to this method.
                # This will be populated from `request_event.original_request_payload` in `ToolExecutionService`
                "original_payload_from_ai_response": llm_provider_info.get("original_execute_tool_request_payload")
            },
            "primary_llm_conversation_snapshot_before_delegation": conversation_history_snapshot,
            "last_user_event_id_at_delegation": last_user_event_id
        }

        openrouter_request = OpenRouterInferenceRequestEvent(
            request_id=delegated_request_id,
            # This is the critical part for Option B:
            # The reply_to_service_event tells the AIInferenceService (specifically OpenRouter part)
            # to publish an event that the ToolExecutionService can pick up to complete this tool's execution.
            # Let's define a new event type for this, e.g., "delegated_openrouter_response_for_tool"
            # Or, the ToolExecutionService itself could subscribe to OpenRouterInferenceResponseEvent
            # and filter based on a unique marker in original_request_payload.
            # For now, let's assume ToolExecutionService will handle OpenRouterInferenceResponseEvent
            # and use the payload_for_openrouter_response_handler to identify it.
            reply_to_service_event=DELEGATED_OPENROUTER_RESPONSE_EVENT_TYPE, # Custom event type
            original_request_payload=payload_for_openrouter_response_handler,
            model_name=model_name,
            messages_payload=messages_payload,
            # This tool could also define what tools OpenRouter itself can use, if any.
            # For now, let's assume OpenRouter won't call further tools that need to come back to *this* system.
            tools=None, # Or pass a restricted set of tools if OpenRouter should be able to use some.
            tool_choice=None
        )

        logger.info(f"DelegateToOpenRouterTool: Publishing OpenRouterInferenceRequestEvent (Req ID: {delegated_request_id}) for tool call {tool_call_id}")

        # According to Option B, the ToolExecutionService will manage the flow.
        # This tool's job is to prepare and return the request for OpenRouter.
        # The ToolExecutionService will then need to listen for the response.
        return ToolResult(
            status="requires_llm_followup", # This status indicates that the tool's work isn't done in one step.
                                          # It has initiated an async operation.
            result_for_llm_history=f"[Tool call_openrouter_llm: Request sent to OpenRouter model '{model_name}'. Awaiting response.]",
            commands_to_publish=[openrouter_request], # The command to send the request to OpenRouter
            # data_for_followup_llm is NOT used here yet. It will be populated by ToolExecutionService
            # when the OpenRouterInferenceResponseEvent comes back.
            data_for_followup_llm=None 
        )
