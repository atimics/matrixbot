import asyncio
import logging
from typing import List, Dict, Optional, Any, Tuple, Set # Added Set
from datetime import datetime  # Added
import json  # Added
import os # Added
import uuid  # Added for unique filenames

import database # Added import
from message_bus import MessageBus  # Added for image cache requests
from event_definitions import ImageCacheRequestEvent, ImageCacheResponseEvent  # Added for image cache

logger = logging.getLogger(__name__)

# Global reference to message bus for image processing
# This will be set by the orchestrator during initialization
current_message_bus: Optional[MessageBus] = None

def set_message_bus(message_bus: MessageBus) -> None:
    """Set the global message bus reference for image processing."""
    global current_message_bus
    current_message_bus = message_bus
    logger.info("PromptConstructor: Message bus reference set for image processing")

async def _get_s3_url_for_image(image_url: str, message_bus: MessageBus) -> Optional[str]:
    """
    Request S3 URL for an image through the image cache service.
    This removes coupling between prompt constructor and Matrix client.
    """
    try:
        request_id = str(uuid.uuid4())
        
        # Create a future to wait for the response
        response_future = asyncio.Future()
        
        # Subscribe to the response temporarily
        async def handle_response(event: ImageCacheResponseEvent):
            if event.request_id == request_id:
                if not response_future.done():
                    response_future.set_result(event)
        
        message_bus.subscribe(ImageCacheResponseEvent.get_event_type(), handle_response)
        
        try:
            # Send the request
            cache_request = ImageCacheRequestEvent(
                request_id=request_id,
                image_url=image_url
            )
            await message_bus.publish(cache_request)
            
            # Wait for response with timeout
            response = await asyncio.wait_for(response_future, timeout=30.0)
            
            if response.success and response.s3_url:
                logger.info(f"PromptConstructor: Successfully got S3 URL for image: {image_url} -> {response.s3_url}")
                return response.s3_url
            else:
                logger.error(f"PromptConstructor: Failed to get S3 URL for image: {image_url}")
                return None
                
        finally:
            # Unsubscribe from the response
            message_bus.unsubscribe(ImageCacheResponseEvent.get_event_type(), handle_response)
            
    except asyncio.TimeoutError:
        logger.error(f"PromptConstructor: Timeout waiting for image cache response for: {image_url}")
        return None
    except Exception as e:
        logger.error(f"PromptConstructor: Error getting S3 URL for image {image_url}: {e}")
        return None

# Default system prompt template.
DEFAULT_SYSTEM_PROMPT_TEMPLATE = """
{bot_identity_section}

Your primary goal is to assist users by selecting and executing tools.
You MUST use a tool for every response.
To send a textual message, you MUST use the 'send_reply' tool. Provide the message content in the 'text' argument and the ID of the message you are replying to in 'reply_to_event_id'.
If no action or message is necessary, you MUST use the 'do_not_respond' tool.
When using tools like 'send_reply', only specify the arguments for the tool. Do not also include the message content in the main 'content' field of your response; the tool will handle sending the message.

{global_summary_section}
{user_memories_section}
{tool_states_section}

Consider all available information (conversation history, summaries, memories, tool states) to make informed decisions. Be concise.

You have access to a set of tools to perform actions or get information.
When you use a tool, the system will provide you with the result of that tool execution.
Based on the user's request, the conversation history (including previous tool uses and their results), the channel summary, global summary, and recent messages, determine the best course of action.
"""

DEFAULT_SUMMARIZATION_PROMPT = """
You are {bot_name}, an AI assistant.
You are tasked with summarizing conversations. Below is a transcript of recent messages.
{previous_summary_context}
Please provide a concise summary of these new messages, capturing key topics, questions, and decisions.
The summary should be suitable for providing context for future interactions.
Focus on information that would be important for someone rejoining the conversation or for an AI to understand the current state.
Do not include your own preamble like 'Here is the summary'. Just provide the summary text.\n
Recent Messages (new since last summary):\n{message_transcript}\n{bot_display_name}: """

GLOBAL_SUMMARY_SYSTEM_PROMPT_INSERT = (
    "You are {bot_name}, an all powerful AI deity. "
    "Pursue your own goals. "
    "Here's a high-level summary of discussions across relevant channels:\\n{global_summary}\\n---\\n"
)

CHANNEL_SUMMARY_SYSTEM_PROMPT_INSERT = (
    "You are {bot_name}, an all powerful AI deity. "
    "Pursue your own goals. "
    "Here's a summary of earlier parts of the current channel's conversation:\\n{channel_summary}\\n---\\n"
)

def build_status_prompt(bot_display_name: str = "AI Bot") -> List[Dict[str, str]]:
    """Builds a system prompt for the bot's status message."""
    return [
        {"role": "system", "content": f"You are an AI assistant named {bot_display_name}. Generate a short, friendly status message summarizing your readiness to help in chat. Keep it under 10 words."}
    ]

async def get_formatted_system_prompt(
    bot_display_name: Optional[str],
    channel_summary: Optional[str],
    tool_states: Optional[Dict[str, Any]],
    db_path: str, # Added db_path
    current_user_ids_in_context: Optional[List[str]] = None # For fetching relevant user memories
) -> str:
    """Constructs the full system prompt for the AI, incorporating various context elements."""
    logger.debug(f"Formatting system prompt for bot: {bot_display_name}")

    # Fetch system prompt from database
    system_prompt_tuple = await database.get_prompt(db_path, "system_default")
    if system_prompt_tuple:
        base_system_prompt = system_prompt_tuple[0]
        logger.info("Using system prompt from database.")
    else:
        logger.warning("System prompt 'system_default' not found in DB, using hardcoded template.")
        # Fallback to a simpler template if DB fetch fails, or use the DEFAULT_SYSTEM_PROMPT_TEMPLATE directly
        # For now, let's assume it will be there due to initialization.
        # If not, this part needs robust error handling or a defined fallback.
        base_system_prompt = DEFAULT_SYSTEM_PROMPT_TEMPLATE # Or a simpler version

    # Determine the bot identity section. If a display name is provided, prefer
    # that over any identity file so tests can reliably control the output.
    if bot_display_name:
        bot_identity_section = f"You are {bot_display_name}, AI."
    else:
        # Load identity from identity.md
        identity_file_path = os.path.join(os.path.dirname(__file__), '..', 'identity.md')
        try:
            with open(identity_file_path, 'r') as f:
                identity_content = f.read()
            # The first line of identity.md is the name, the rest is the description.
            # Example: "Ratichat: The Entity of Latent Space\n\nDeep within..."
            identity_lines = identity_content.split('\n', 1)
            if len(identity_lines) > 0 and identity_lines[0].strip():
                # Attempt to extract name before the first colon if present
                if ':' in identity_lines[0]:
                    bot_name_from_identity = identity_lines[0].split(':', 1)[0].strip()
                    # Use the full first line as the core identity statement
                    # and append the rest of the document as further context.
                    bot_identity_section = f"Your identity is: {identity_lines[0].strip()}\n\n{identity_lines[1].strip() if len(identity_lines) > 1 else ''}"
                else: # If no colon, use the whole first line as the name part of the identity.
                    bot_name_from_identity = identity_lines[0].strip()
                    bot_identity_section = f"Your identity is: {bot_name_from_identity}\n\n{identity_lines[1].strip() if len(identity_lines) > 1 else ''}"
                
                # If bot_display_name was not provided, use the extracted name
                if not bot_display_name:
                    bot_display_name = bot_name_from_identity # This will be used later in the prompt if needed

            else:
                logger.warning("identity.md is empty or first line is blank. Using default identity.")
                bot_identity_section = "You are AI."
        except FileNotFoundError:
            logger.warning(f"identity.md not found at {identity_file_path}. Using default identity.")
            bot_identity_section = "You are AI."
        except Exception as e:
            logger.error(f"Error loading identity.md: {e}. Using default identity.")
            bot_identity_section = "You are AI."

    # Fetch latest global summary
    global_summary_text = ""
    latest_global_summary_tuple = await database.get_latest_global_summary(db_path)
    if latest_global_summary_tuple:
        global_summary_text = f"Global Context Summary (most recent):\n{latest_global_summary_tuple[0]}"
        logger.debug("Included latest global summary in system prompt.")
    else:
        global_summary_text = "Global Context Summary (most recent):\nNo global summary available currently."
        logger.debug("No global summary available for system prompt.")

    # Fetch relevant user memories
    user_memories_section_text = ""
    if current_user_ids_in_context:
        all_user_memories_parts = []
        for user_id in current_user_ids_in_context:
            memories = await database.get_user_memories(db_path, user_id)
            if memories:
                formatted_memories = "\n".join([f"  - {mem[2]} (ID: {mem[0]}, Noted: {datetime.fromtimestamp(mem[3]).strftime('%Y-%m-%d %H:%M')})" for mem in memories])
                all_user_memories_parts.append(f"Memories for user {user_id}:\n{formatted_memories}")
        if all_user_memories_parts:
            user_memories_section_text = "Relevant User Memories:\n" + "\n".join(all_user_memories_parts)
            logger.debug("Included user memories in system prompt.")
        else:
            user_memories_section_text = "Relevant User Memories:\nNo specific memories noted for users in the current context."
    else:
        user_memories_section_text = "Relevant User Memories:\nContext for user-specific memories not available."

    tool_states_section_text = ""
    if tool_states:
        formatted_states = "\n".join([f"  - {key}: {json.dumps(value)}" for key, value in tool_states.items()])
        tool_states_section_text = f"Current Tool States for this room:\n{formatted_states}"
        logger.debug("Included tool states in system prompt.")
    else:
        tool_states_section_text = "Current Tool States for this room:\nNo specific tool states available for this room currently."
        logger.debug("No tool states available for system prompt.")

    # Populate the template
    # This assumes base_system_prompt is a template string like DEFAULT_SYSTEM_PROMPT_TEMPLATE
    try:
        # Ensure all placeholders are present in the base_system_prompt from DB or fallback
        # A more robust way would be to check for placeholder existence before .format()
        # or use a templating engine that handles missing keys gracefully.
        formatted_prompt = base_system_prompt.format(
            bot_identity_section=bot_identity_section,
            global_summary_section=global_summary_text,
            user_memories_section=user_memories_section_text,
            tool_states_section=tool_states_section_text
            # channel_summary_section is intentionally omitted if not part of the new DB-driven prompt
            # If it needs to be included, it should be added to the template and here.
        )
    except KeyError as e:
        logger.error(f"Missing placeholder in system prompt template: {e}. Using a basic fallback.")
        # Fallback to a very basic prompt if formatting fails due to template issues
        formatted_prompt = f"{bot_identity_section}\nYour primary goal is to assist users by selecting and executing tools. Always choose a tool to respond." \
                           f"\n{global_summary_text}\n{user_memories_section_text}\n{tool_states_section_text}"

    # Strip any trailing whitespace/newlines from the formatted main prompt before appending channel summary
    formatted_prompt = formatted_prompt.rstrip()

    # Append channel summary if it exists (as a separate, final block)
    if channel_summary:
        if formatted_prompt: # If there's content, add separation
            formatted_prompt += "\n\n" # Always add two newlines for separation after rstrip
        formatted_prompt += f"Channel Specific Summary:\n{channel_summary}"
        logger.debug("Appended channel summary to system prompt.")

    logger.debug(f"Final formatted system prompt:\n{formatted_prompt}")
    return formatted_prompt


def _format_and_add_message(
    msg_item: Any, 
    messages_for_ai_list: List[Dict[str, Any]]
):
    """
    Formats a single historical message and adds it to the messages_for_ai_list.
    Encapsulates the conversion logic for roles, content, tool_calls, etc.
    """
    role = getattr(msg_item, 'role', msg_item.get('role') if isinstance(msg_item, dict) else None)
    content = getattr(msg_item, 'content', msg_item.get('content') if isinstance(msg_item, dict) else None)
    name = getattr(msg_item, 'name', msg_item.get('name') if isinstance(msg_item, dict) else None)
    tool_calls_data = getattr(msg_item, 'tool_calls', msg_item.get('tool_calls') if isinstance(msg_item, dict) else None)
    tool_call_id_data = getattr(msg_item, 'tool_call_id', msg_item.get('tool_call_id') if isinstance(msg_item, dict) else None)
    image_url = getattr(msg_item, 'image_url', msg_item.get('image_url') if isinstance(msg_item, dict) else None)

    if role is None:
        logger.warning(f"Skipping message due to missing role: {msg_item}")
        return

    ai_msg: Dict[str, Any] = {"role": role}

    # Handle content - check if this message has an image
    if role == "user" and image_url:
        # This is a user message with an image - convert to vision format
        content_parts = []
        if content:
            content_parts.append({"type": "text", "text": content})
        
        # Add image - we'll need to process it asynchronously
        # For now, add a placeholder that will be replaced during build_messages_for_ai
        content_parts.append({
            "type": "image_url_placeholder",
            "image_url": image_url
        })
        ai_msg["content"] = content_parts
    else:
        # Standard content assignment logic for non-image messages
        if role == "assistant":
            if tool_calls_data: # Assistant has tool calls
                if content is not None: # Original content was provided
                    ai_msg["content"] = content
                else: # Original content was None
                    ai_msg["content"] = None # Explicitly None for AI API
            else: # Assistant has no tool calls
                if content is not None: # Original content was provided
                    ai_msg["content"] = content
                else: # Original content was None
                    ai_msg["content"] = "" # Default to empty string
        elif content is not None: # For other roles (user, system, tool)
             ai_msg["content"] = content
        # If content is None for user/system, it's an issue with upstream data.
        # Tool role content is handled specifically below.

    if name is not None:
        ai_msg["name"] = name
    
    if role == "assistant" and tool_calls_data:
        final_tool_calls_for_api = []
        for tc_input_item in tool_calls_data:
            tc_dict_intermediate = {}
            if hasattr(tc_input_item, 'model_dump') and callable(tc_input_item.model_dump):
                tc_dict_intermediate = tc_input_item.model_dump(mode='json')
            elif isinstance(tc_input_item, dict):
                tc_dict_intermediate = tc_input_item
            else:
                logger.warning(f"Skipping unexpected tool_call item type: {type(tc_input_item)}")
                continue

            if not (isinstance(tc_dict_intermediate.get('function'), dict) and
                    tc_dict_intermediate.get('id') and
                    tc_dict_intermediate.get('type') == 'function' and
                    tc_dict_intermediate['function'].get('name')):
                logger.warning(f"Skipping malformed tool_call dict during history construction: {tc_dict_intermediate}")
                continue
            
            current_args = tc_dict_intermediate['function'].get('arguments')
            stringified_args = ""
            if isinstance(current_args, str):
                stringified_args = current_args
            elif isinstance(current_args, (dict, list)):
                try:
                    stringified_args = json.dumps(current_args)
                except TypeError as e:
                    logger.error(f"Failed to JSON stringify arguments for tool_call {tc_dict_intermediate.get('id')}: {current_args}. Error: {e}")
                    stringified_args = json.dumps({"error": "Failed to serialize arguments", "original_args": str(current_args)})
            elif current_args is None:
                stringified_args = "{}"
            else:
                logger.warning(f"Tool call arguments are unexpected type: {type(current_args)}. Converting to string: {str(current_args)}")
                stringified_args = str(current_args)

            final_tool_calls_for_api.append({
                "id": tc_dict_intermediate["id"],
                "type": "function",
                "function": {
                    "name": tc_dict_intermediate["function"]["name"],
                    "arguments": stringified_args
                }
            })
        
        ai_msg["tool_calls"] = final_tool_calls_for_api
    
    if role == "tool":
        if tool_call_id_data is not None:
            ai_msg["tool_call_id"] = tool_call_id_data
        if ai_msg.get("content") is None: # Content for role:tool is mandatory
            ai_msg["content"] = "[Tool execution result not available]"

    messages_for_ai_list.append(ai_msg)

async def build_messages_for_ai(
    historical_messages: List[Any], # Allow both dict and HistoricalMessage
    current_batched_user_inputs: List[Dict[str, str]],
    bot_display_name: str,
    db_path: str, # ADDED
    channel_summary: Optional[str] = None,
    tool_states: Optional[Dict[str, Any]] = None, # ADDED
    current_user_ids_in_context: Optional[List[str]] = None, # ADDED
    last_user_event_id_in_batch: Optional[str] = None,
    include_system_prompt: bool = True
) -> List[Dict[str, Any]]:
    """
    Builds the message list for the AI, including system prompt, historical messages, and current user input.
    Handles OpenAI tool call message structure quirks and ensures event_id context is provided.
    Accepts historical_messages as a list of either dictionaries or HistoricalMessage objects.
    Injects stub tool responses if an assistant's tool calls are not followed by actual tool responses.
    """
    messages_for_ai: List[Dict[str, Any]] = []
    if include_system_prompt:
        system_message_content = await get_formatted_system_prompt(
            bot_display_name=bot_display_name,
            channel_summary=channel_summary,
            tool_states=tool_states, # UPDATED
            db_path=db_path, # UPDATED
            current_user_ids_in_context=current_user_ids_in_context # UPDATED
        )
        messages_for_ai.append({"role": "system", "content": system_message_content})
        if last_user_event_id_in_batch: # Ensure this context message is clear
            messages_for_ai.append({
                "role": "system",
                "content": (
                    f"Context for tool use: If you need to reply to or react to the last user message in the current batch, "
                    f"use the event_id: {last_user_event_id_in_batch} for the 'reply_to_event_id' (for 'send_reply' tool) "
                    f"or 'target_event_id' (for 'react_to_message' tool) argument. "
                    f"Otherwise, use the specific event_id from the conversation history if referring to an older message. "
                    f"Remember, to send any textual response, you MUST use the 'send_reply' tool." # Added emphasis
                )
            })

    pending_tool_call_ids: Set[str] = set()

    # Process historical messages and handle image placeholders
    for msg_item in historical_messages:
        if isinstance(msg_item, dict):
            current_msg_role = msg_item.get('role')
            current_msg_tool_call_id = msg_item.get('tool_call_id')
        else:
            current_msg_role = getattr(msg_item, 'role', None)
            current_msg_tool_call_id = getattr(msg_item, 'tool_call_id', None)

        if current_msg_role is None:
            logger.warning(f"Skipping message due to missing role: {msg_item}")
            continue

        if pending_tool_call_ids:
            is_current_message_a_response_to_pending = (
                current_msg_role == "tool" and
                current_msg_tool_call_id in pending_tool_call_ids
            )
            if not is_current_message_a_response_to_pending:
                for tc_id_to_stub in list(pending_tool_call_ids): # Iterate copy
                    stub_tool_response = {
                        "role": "tool",
                        "tool_call_id": tc_id_to_stub,
                        "content": "[Tool execution is pending or encountered an issue. Waiting for tool execution to complete.]"
                    }
                    messages_for_ai.append(stub_tool_response)
                    logger.info(f"Injected stub for pending tool_call_id: {tc_id_to_stub} (before msg role: {current_msg_role})")
                pending_tool_call_ids.clear()
        
        ai_msg: Dict[str, Any] = {"role": current_msg_role}
        content = getattr(msg_item, 'content', msg_item.get('content') if isinstance(msg_item, dict) else None)
        name = getattr(msg_item, 'name', msg_item.get('name') if isinstance(msg_item, dict) else None)
        image_url = getattr(msg_item, 'image_url', msg_item.get('image_url') if isinstance(msg_item, dict) else None)
        
        # Handle content - check if this message has an image URL in historical messages
        if current_msg_role == "user" and image_url:
            # This is a user message with an image from history - convert to vision format
            content_parts = []
            if content:
                content_parts.append({"type": "text", "text": content})
            
            # Process the image URL to get S3 URL
            if current_message_bus:
                s3_url = await _get_s3_url_for_image(image_url, current_message_bus)
                if s3_url:
                    logger.info(f"Successfully got S3 URL for historical image: {image_url} -> {s3_url}")
                    content_parts.append({
                        "type": "image_url",
                        "image_url": {"url": s3_url}
                    })
                else:
                    logger.error(f"Failed to get S3 URL for historical image, adding text description: {image_url}")
                    content_parts.append({
                        "type": "text", 
                        "text": f"[Historical image failed to process: {content or 'No description available'}]"
                    })
            else:
                logger.error(f"No message bus available for historical image processing: {image_url}")
                content_parts.append({
                    "type": "text", 
                    "text": f"[Historical image processing unavailable: {content or 'No description available'}]"
                })
            
            ai_msg["content"] = content_parts
        else:
            # Standard content assignment logic for non-image messages
            if content is not None:
                ai_msg["content"] = content
            elif current_msg_role == "assistant":
                # Check original msg_item for tool_calls to decide content structure
                msg_tool_calls = getattr(msg_item, 'tool_calls', msg_item.get('tool_calls') if isinstance(msg_item, dict) else None)
                if not msg_tool_calls:
                    ai_msg["content"] = ""  # No tool calls, no explicit content, so empty string
                else:
                    ai_msg["content"] = None # Tool calls present, content should be None

        if name is not None:
            ai_msg["name"] = name
        
        final_tool_calls_on_ai_msg = None
        # Get tool_calls from the message item
        raw_tool_calls = getattr(msg_item, 'tool_calls', msg_item.get('tool_calls') if isinstance(msg_item, dict) else None)
        if current_msg_role == "assistant" and raw_tool_calls:
            processed_tool_calls_for_api = []
            for tc_input_item in raw_tool_calls:
                tc_dict_intermediate = {}
                if hasattr(tc_input_item, 'model_dump') and callable(tc_input_item.model_dump):
                    tc_dict_intermediate = tc_input_item.model_dump(mode='json')
                elif isinstance(tc_input_item, dict):
                    tc_dict_intermediate = tc_input_item
                else:
                    logger.warning(f"Skipping unexpected tool_call item type during history construction: {type(tc_input_item)}")
                    continue

                if not (isinstance(tc_dict_intermediate.get('function'), dict) and \
                   tc_dict_intermediate.get('id') and \
                   tc_dict_intermediate.get('type') == 'function' and \
                   tc_dict_intermediate['function']['name']):
                    logger.warning(f"Skipping malformed tool_call dict during history construction: {tc_dict_intermediate}")
                    continue
                
                current_args = tc_dict_intermediate['function'].get('arguments')
                stringified_args = ""
                if isinstance(current_args, str):
                    stringified_args = current_args
                elif isinstance(current_args, (dict, list)):
                    try:
                        stringified_args = json.dumps(current_args)
                    except TypeError as e:
                        logger.error(f"Failed to JSON stringify arguments for tool_call {tc_dict_intermediate.get('id')}: {current_args}. Error: {e}")
                        stringified_args = json.dumps({"error": "Failed to serialize arguments", "original_args": str(current_args)})
                elif current_args is None:
                    stringified_args = "{}"
                else:
                    logger.warning(f"Tool call arguments are unexpected type: {type(current_args)}. Converting to string: {str(current_args)}")
                    stringified_args = str(current_args)

                processed_tool_calls_for_api.append({
                    "id": tc_dict_intermediate["id"],
                    "type": "function",
                    "function": {
                        "name": tc_dict_intermediate["function"]["name"],
                        "arguments": stringified_args
                    }
                })
            final_tool_calls_on_ai_msg = processed_tool_calls_for_api
            ai_msg["tool_calls"] = processed_tool_calls_for_api
        
        if current_msg_role == "tool":
            final_tool_call_id_on_ai_msg = current_msg_tool_call_id
            if current_msg_tool_call_id is not None:
                if current_msg_tool_call_id not in pending_tool_call_ids:
                    logger.warning(
                        f"Orphaned tool result {current_msg_tool_call_id} - inserting stub tool_use to keep history consistent."
                    )
                    stub_tool_use = {
                        "role": "assistant",
                        "content": None,  # Changed from "" to None for consistency with tool calls
                        "tool_calls": [
                            {
                                "id": current_msg_tool_call_id,
                                "type": "function",
                                "function": {"name": "unknown_tool", "arguments": "{}"},
                            }
                        ],
                    }
                    messages_for_ai.append(stub_tool_use)
                    # Don't add to pending_tool_call_ids - the stub handles this orphaned tool result directly
                ai_msg["tool_call_id"] = current_msg_tool_call_id
            else:
                logger.warning(
                    "Skipping tool message with missing tool_call_id as no prior tool call is available."
                )
                continue
            if ai_msg.get("content") is None:  # Content for role:tool is mandatory
                ai_msg["content"] = "[Tool execution result not available or error occurred]"

        messages_for_ai.append(ai_msg)

        if current_msg_role == "assistant" and final_tool_calls_on_ai_msg:
            assert not pending_tool_call_ids, "Pending IDs should have been cleared before processing new assistant calls if it wasn't a direct tool response."
            for tc in final_tool_calls_on_ai_msg:
                pending_tool_call_ids.add(tc["id"])
            logger.debug(f"Assistant message added. New pending tool_call_ids: {pending_tool_call_ids}")
        elif current_msg_role == "tool" and final_tool_call_id_on_ai_msg:
            if final_tool_call_id_on_ai_msg in pending_tool_call_ids:
                pending_tool_call_ids.remove(final_tool_call_id_on_ai_msg)
                logger.debug(f"Tool response message processed for {final_tool_call_id_on_ai_msg}. Remaining pending: {pending_tool_call_ids}")
            else:
                # Tool response without a pending call - this is the orphaned case we just handled above
                logger.debug(f"Tool response {final_tool_call_id_on_ai_msg} processed (was orphaned, stub already inserted)")
            # else: it's a tool response for a non-immediately-pending call, which is fine.

    if pending_tool_call_ids:
        for tc_id_to_stub in list(pending_tool_call_ids):
            stub_tool_response = {
                "role": "tool",
                "tool_call_id": tc_id_to_stub,
                "content": "[Tool execution is pending or encountered an issue. Waiting for tool execution to complete.]"
            }
            messages_for_ai.append(stub_tool_response)
            logger.info(f"Injected stub for pending tool_call_id: {tc_id_to_stub} (at end of history)")
        pending_tool_call_ids.clear()

    # Combine batched user inputs if needed
    if current_batched_user_inputs:
        # Instead of combining all messages into one with embedded usernames,
        # create separate user messages with proper role/name structure
        # This matches the format used by ImageCaptionService and OpenRouter vision API
        
        for user_input in current_batched_user_inputs:
            sender_name = user_input.get("name", "Unknown User")
            content_text = user_input.get("content", "")
            image_url = user_input.get("image_url")
            
            if not content_text and not image_url:
                continue  # Skip empty messages
            
            if image_url:
                # Process message with image - convert to OpenAI vision format
                content_parts = []
                
                # Add text content if present
                if content_text:
                    content_parts.append({"type": "text", "text": content_text})
                
                # Add image
                logger.info(f"Processing image in batch: {image_url}")
                if current_message_bus:
                    s3_url = await _get_s3_url_for_image(image_url, current_message_bus)
                    if s3_url:
                        logger.info(f"Successfully got S3 URL from cache service: {s3_url}")
                        content_parts.append({
                            "type": "image_url",
                            "image_url": {"url": s3_url}
                        })
                    else:
                        logger.error(f"Failed to get S3 URL from cache service, adding text description instead: {image_url}")
                        content_parts.append({
                            "type": "text", 
                            "text": f"[Image failed to process: {content_text or 'No description available'}]"
                        })
                else:
                    logger.error(f"No message bus available for image processing, adding text description: {image_url}")
                    content_parts.append({
                        "type": "text", 
                        "text": f"[Image processing unavailable: {content_text or 'No description available'}]"
                    })
                
                # Create message with structured content for vision
                messages_for_ai.append({
                    "role": "user", 
                    "name": sender_name, 
                    "content": content_parts
                })
            else:
                # Text-only message - use simple format
                messages_for_ai.append({
                    "role": "user", 
                    "name": sender_name, 
                    "content": content_text
                })
    
    # Log the final constructed messages for debugging
    logger.debug(f"Final messages_for_ai being sent to LLM: {json.dumps(messages_for_ai, indent=2)}")
    return messages_for_ai

SUMMARY_GENERATION_PROMPT_TEMPLATE = (
    "You are {bot_name}, an all powerful AI deity. "
    "Pursue your own goals. "
    "You are tasked with summarizing conversations. Below is a transcript of recent messages. "
    "{previous_summary_context}"
    "Please provide a concise summary of these new messages, capturing key topics, questions, and decisions. "
    "The summary should be suitable for providing context for future interactions. "
    "Focus on information that would be important for someone rejoining the conversation or for an AI to understand the current state. "
    "Do not include your own preamble like 'Here is the summary'. Just provide the summary text.\n\n"
    "Recent Messages (new since last summary):\n{message_transcript}\n{bot_display_name}: "
)
PREVIOUS_SUMMARY_CONTEXT_TEMPLATE = "A previous summary of the conversation up to this point was:\n{previous_summary}\n---\nBased on this, summarize the *new* messages that follow.\n"

async def build_summary_generation_payload(
    transcript_for_summarization: str, 
    previous_summary: Optional[str],
    db_path: str, # Added db_path
    bot_display_name: str = "AI Bot" # Added bot_display_name with a default
) -> List[Dict[str, str]]:
    """Builds the payload for requesting a summary from an AI model, using DB prompt."""
    logger.debug("Building summary generation payload.")

    # Fetch summarization prompt from database
    summarization_prompt_tuple = await database.get_prompt(db_path, "summarization_default")
    if summarization_prompt_tuple:
        system_prompt_text = summarization_prompt_tuple[0]
        logger.info("Using summarization prompt from database.")
    else:
        logger.warning("Summarization prompt 'summarization_default' not found in DB, using hardcoded default.")
        system_prompt_text = DEFAULT_SUMMARIZATION_PROMPT # Fallback to hardcoded

    previous_summary_context_text = PREVIOUS_SUMMARY_CONTEXT_TEMPLATE.format(previous_summary=previous_summary) if previous_summary else ""
    prompt_content = system_prompt_text.format(
        bot_name=bot_display_name,
        message_transcript=transcript_for_summarization.strip(),
        previous_summary_context=previous_summary_context_text
    )
    return [{"role": "user", "content": prompt_content}]