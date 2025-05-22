import asyncio
import logging
import json
from typing import Dict, Any, Optional

from message_bus import MessageBus
from tool_manager import ToolRegistry
from tool_base import ToolResult # Assuming ToolResult is in tool_base
from event_definitions import ExecuteToolRequest, ToolExecutionResponse, BaseEvent, OpenRouterInferenceResponseEvent, MatrixRoomInfoResponseEvent
from available_tools.delegate_to_openrouter_tool import DELEGATED_OPENROUTER_RESPONSE_EVENT_TYPE # Import the constant

logger = logging.getLogger(__name__)

class ToolExecutionService:
    def __init__(self, message_bus: MessageBus, tool_registry: ToolRegistry, db_path: str = "matrix_bot_soa.db"):
        self.bus = message_bus
        self.tool_registry = tool_registry
        self.db_path = db_path
        self._stop_event = asyncio.Event()

    async def _handle_execute_tool_request(self, event: ExecuteToolRequest):
        # The event.tool_call object (ToolCall Pydantic model) contains the id and function details.
        # event.tool_call.id
        # event.tool_call.function.name
        # event.tool_call.function.arguments (this is a string, needs parsing)

        tool_name = event.tool_call.function.name # Correctly access tool name
        tool_call_id = event.tool_call.id
        arguments_input = event.tool_call.function.arguments
        if isinstance(arguments_input, str):
            try:
                parsed_args = json.loads(arguments_input)
            except Exception:
                parsed_args = {}
        elif isinstance(arguments_input, dict):
            parsed_args = arguments_input
        else:
            parsed_args = {}

        logger.info(f"TES: Received ExecuteToolRequest for tool: {tool_name}, Tool Call ID: {tool_call_id}, Event ID: {event.event_id}. Args: {arguments_str}") # MODIFIED

        tool = self.tool_registry.get_tool(tool_name)

        if not tool:
            logger.error(f"ToolExecSvc: Tool '{tool_name}' not found in registry.")
            tool_response = ToolExecutionResponse(
                original_tool_call_id=tool_call_id,
                tool_name=tool_name,
                status="failure",
                result_for_llm_history=f"[Error: Tool '{tool_name}' not found]",
                error_message=f"Tool '{tool_name}' not found",
                original_request_payload=event.original_request_payload
            )
            await self.bus.publish(tool_response)
            return

        try:
            tool_result: ToolResult = await tool.execute(
                room_id=event.room_id,
                db_path=self.db_path,
                arguments=parsed_args,
                tool_call_id=tool_call_id,
                llm_provider_info={
                    **event.llm_provider_info,
                    # Pass the original_request_payload from the ExecuteToolRequest itself
                    # so that tools like DelegateToOpenRouterTool can forward it if they delegate work.
                    "original_execute_tool_request_payload": event.original_request_payload
                },
                conversation_history_snapshot=event.conversation_history_snapshot,
                last_user_event_id=event.last_user_event_id
            )

            if tool_result.commands_to_publish:
                for command_to_publish in tool_result.commands_to_publish: # MODIFIED variable name for clarity
                    if isinstance(command_to_publish, BaseEvent):
                        logger.info(f"TES: Publishing command from tool {tool_name}: {command_to_publish.event_type} (Event ID: {command_to_publish.event_id}) for Tool Call ID: {tool_call_id}") # ADDED
                        await self.bus.publish(command_to_publish)
                    else:
                        logger.warning(f"ToolExecSvc: Tool '{tool_name}' (Tool Call ID: {tool_call_id}) tried to publish non-event: {command_to_publish}") # MODIFIED
            
            # If the tool requires a followup (like DelegateToOpenRouterTool), 
            # we don't publish a ToolExecutionResponse immediately.
            # It will be published by the handler for the delegated task's response.
            if tool_result.status != "requires_llm_followup":
                tool_response = ToolExecutionResponse(
                    original_tool_call_id=tool_call_id,
                    tool_name=tool_name, # Populate tool_name
                    status=tool_result.status,
                    result_for_llm_history=tool_result.result_for_llm_history,
                    error_message=tool_result.error_message,
                    data_from_tool_for_followup_llm=tool_result.data_for_followup_llm,
                    original_request_payload=event.original_request_payload
                )
                await self.bus.publish(tool_response)
                logger.info(f"ToolExecSvc: Finished executing tool '{tool_name}' (Call ID: {tool_call_id}). Status: {tool_result.status}")
            else:
                logger.info(f"ToolExecSvc: Tool '{tool_name}' (Call ID: {tool_call_id}) requires followup. Awaiting delegated task response.")

        except Exception as e:
            logger.error(f"ToolExecSvc: Exception during execution of tool '{tool_name}': {e}", exc_info=True)
            error_response = ToolExecutionResponse(
                original_tool_call_id=tool_call_id,
                tool_name=tool_name, # Populate tool_name
                status="failure",
                result_for_llm_history=f"[Error executing tool '{tool_name}': {e}]",
                error_message=str(e),
                original_request_payload=event.original_request_payload
            )
            await self.bus.publish(error_response)

    async def _handle_delegated_openrouter_response(self, or_response_event: OpenRouterInferenceResponseEvent) -> None:
        """Handles responses from OpenRouter that were initiated by DelegateToOpenRouterTool."""
        
        # Extract the context saved by DelegateToOpenRouterTool
        delegation_context = or_response_event.original_request_payload
        original_tool_call_id = delegation_context.get("original_tool_call_id")
        original_room_id = delegation_context.get("original_room_id")

        if not original_tool_call_id or not original_room_id:
            logger.error(f"ToolExecSvc: Received OpenRouter response for delegated call, but missing original_tool_call_id or original_room_id. OR Req ID: {or_response_event.request_id}")
            return

        logger.info(f"ToolExecSvc: Received OpenRouter response for original tool call ID '{original_tool_call_id}' in room '{original_room_id}'. Success: {or_response_event.success}")

        final_status: str
        result_for_llm: str
        error_msg: Optional[str] = None
        data_for_llm_followup: Optional[Dict[str, Any]] = None

        if or_response_event.success:
            final_status = "success" # The delegated call itself was successful
            # The result for the primary LLM is the text response from OpenRouter
            result_for_llm = or_response_event.text_response or "[OpenRouter returned no text content]"
            
            # If OpenRouter itself made tool calls, that's a more complex scenario.
            # For now, we assume the primary LLM wants the text response from OpenRouter.
            # The `data_for_followup_llm` will carry this text response back.
            data_for_llm_followup = {
                "text_response_from_openrouter": or_response_event.text_response,
                "tool_calls_from_openrouter": [
                    tc.model_dump(mode='json') if hasattr(tc, 'model_dump') else tc 
                    for tc in or_response_event.tool_calls
                ] if or_response_event.tool_calls else None
            }
            if or_response_event.tool_calls:
                logger.warning(f"ToolExecSvc: OpenRouter (delegated call for {original_tool_call_id}) itself returned tool_calls: {or_response_event.tool_calls}. These are passed in data_for_followup_llm but not directly executed by ToolExecutionService at this step.")

        else: # OpenRouter call failed
            final_status = "failure"
            error_msg = or_response_event.error_message or "OpenRouter call failed with no specific error message."
            result_for_llm = f"[Tool call_openrouter_llm failed: OpenRouter error: {error_msg}]"

        # For now, we'll use what we have, which is `delegation_context`.
        # This means RoomLogicService needs to be aware of this structure.

        # Correction: The `original_request_payload` in ToolExecutionResponse should be the one from the *initial* ExecuteToolRequest.
        # This was stored in `delegation_context` as `original_execute_tool_request_payload` (needs to be added).
        # Let's assume it is available as `delegation_context.get("original_execute_tool_request_payload")`

        # The `payload_for_openrouter_response_handler` (which is `delegation_context` here)
        # now contains `original_execute_tool_request_payload` which itself contains `original_payload_from_ai_response`.
        # This `original_payload_from_ai_response` is what RoomLogicService expects in ToolExecutionResponse.original_request_payload.
        execute_tool_request_context = delegation_context.get("original_execute_tool_request_payload", {})
        final_original_request_payload_for_rls = execute_tool_request_context.get("original_payload_from_ai_response")

        if not final_original_request_payload_for_rls:
            logger.error(f"ToolExecSvc: Critical - Missing 'original_payload_from_ai_response' in original_execute_tool_request_payload within delegation_context for tool call {original_tool_call_id}. Cannot form proper ToolExecutionResponse for RoomLogicService.")
            # Fallback, but this will likely cause issues in RoomLogicService
            final_original_request_payload_for_rls = {"room_id": original_room_id} 

        final_tool_response = ToolExecutionResponse(
            original_tool_call_id=original_tool_call_id,
            tool_name="call_openrouter_llm", # Populate tool_name (specific for delegated calls)
            status=final_status,
            result_for_llm_history=result_for_llm,
            error_message=error_msg,
            data_from_tool_for_followup_llm=data_for_llm_followup,
            original_request_payload=final_original_request_payload_for_rls
        )
        await self.bus.publish(final_tool_response)
        logger.info(f"ToolExecSvc: Published final ToolExecutionResponse for delegated call_openrouter_llm (Original Call ID: {original_tool_call_id}). Status: {final_status}")

    async def _handle_room_info_response(self, event: MatrixRoomInfoResponseEvent) -> None:
        tool_response = ToolExecutionResponse(
            original_tool_call_id=event.original_tool_call_id,
            tool_name="get_room_info",
            status="success" if event.success else "failure",
            result_for_llm_history=str(event.info) if event.success else f"[Failed to fetch room info: {event.error_message}]",
            error_message=event.error_message,
            original_request_payload={"room_id": event.room_id}
        )
        await self.bus.publish(tool_response)

    async def run(self) -> None:
        logger.info("ToolExecutionService: Starting...")
        self.bus.subscribe(ExecuteToolRequest.model_fields['event_type'].default, self._handle_execute_tool_request)
        # Subscribe to the specific event type that OpenRouterInferenceService will publish to
        # when a response for a DelegateToOpenRouterTool call is ready.
        self.bus.subscribe(DELEGATED_OPENROUTER_RESPONSE_EVENT_TYPE, self._handle_delegated_openrouter_response)
        self.bus.subscribe(MatrixRoomInfoResponseEvent.model_fields['event_type'].default, self._handle_room_info_response)
        await self._stop_event.wait()
        logger.info("ToolExecutionService: Stopped.")

    async def stop(self) -> None:
        logger.info("ToolExecutionService: Stop requested.")
        self._stop_event.set()
