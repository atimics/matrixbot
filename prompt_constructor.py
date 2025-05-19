import logging
from typing import List, Dict, Optional, Any
from datetime import datetime # Added
import json # Added

import database # Added import

logger = logging.getLogger(__name__)

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

Consider all available information (conversation history, summaries, memories, tool states) to make informed decisions. Be concise and helpful.

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

def get_formatted_system_prompt(
    bot_display_name: Optional[str],
    channel_summary: Optional[str],
    tool_states: Optional[Dict[str, Any]],
    db_path: str, # Added db_path
    current_user_ids_in_context: Optional[List[str]] = None # For fetching relevant user memories
) -> str:
    """Constructs the full system prompt for the AI, incorporating various context elements."""
    logger.debug(f"Formatting system prompt for bot: {bot_display_name}")

    # Fetch system prompt from database
    system_prompt_tuple = database.get_prompt(db_path, "system_default")
    if system_prompt_tuple:
        base_system_prompt = system_prompt_tuple[0]
        logger.info("Using system prompt from database.")
    else:
        logger.warning("System prompt 'system_default' not found in DB, using hardcoded template.")
        # Fallback to a simpler template if DB fetch fails, or use the DEFAULT_SYSTEM_PROMPT_TEMPLATE directly
        # For now, let's assume it will be there due to initialization.
        # If not, this part needs robust error handling or a defined fallback.
        base_system_prompt = DEFAULT_SYSTEM_PROMPT_TEMPLATE # Or a simpler version

    bot_identity_section = f"You are {bot_display_name}, a whimsically malevolent AI deity." if bot_display_name else "You are the all powerful ai deity ratichat."
    
    # Fetch latest global summary
    global_summary_text = ""
    latest_global_summary_tuple = database.get_latest_global_summary(db_path)
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
            memories = database.get_user_memories(db_path, user_id)
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

def build_messages_for_ai(
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
    """
    messages_for_ai: List[Dict[str, Any]] = []
    if include_system_prompt:
        system_message_content = get_formatted_system_prompt(
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

    for msg_item in historical_messages:
        role = getattr(msg_item, 'role', msg_item.get('role') if isinstance(msg_item, dict) else None)
        content = getattr(msg_item, 'content', msg_item.get('content') if isinstance(msg_item, dict) else None)
        name = getattr(msg_item, 'name', msg_item.get('name') if isinstance(msg_item, dict) else None)
        tool_calls = getattr(msg_item, 'tool_calls', msg_item.get('tool_calls') if isinstance(msg_item, dict) else None)
        tool_call_id = getattr(msg_item, 'tool_call_id', msg_item.get('tool_call_id') if isinstance(msg_item, dict) else None)

        if role is None:
            logger.warning(f"Skipping message due to missing role: {msg_item}")
            continue

        ai_msg: Dict[str, Any] = {"role": role}

        if content is not None:
            ai_msg["content"] = content
        elif role == "assistant":
            if not tool_calls:
                ai_msg["content"] = ""
            else:
                ai_msg["content"] = None # OpenAI prefers None if only tool_calls

        if name is not None:
            ai_msg["name"] = name
        
        if role == "assistant" and tool_calls is not None:
            # Meticulously reconstruct tool_calls to ensure API compliance
            final_tool_calls_for_api = []
            for tc_input_item in tool_calls: # tc_input_item can be a Pydantic ToolCall or a dict
                tc_dict_intermediate = {}
                if hasattr(tc_input_item, 'model_dump') and callable(tc_input_item.model_dump): # Is Pydantic model
                    tc_dict_intermediate = tc_input_item.model_dump(mode='json')
                elif isinstance(tc_input_item, dict):
                    tc_dict_intermediate = tc_input_item # Use directly if already a dict
                else:
                    logger.warning(f"Skipping unexpected tool_call item type during history construction: {type(tc_input_item)}")
                    continue

                # Validate basic structure
                if not isinstance(tc_dict_intermediate.get('function'), dict) or \
                   not tc_dict_intermediate.get('id') or \
                   not tc_dict_intermediate.get('type') == 'function' or \
                   not tc_dict_intermediate['function'].get('name'):
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
                    stringified_args = "{}" # OpenAI often expects a string, even for no args. "{}" is common.
                else:
                    logger.warning(f"Tool call arguments are unexpected type: {type(current_args)}. Converting to string: {str(current_args)}")
                    stringified_args = str(current_args)

                final_tool_calls_for_api.append({
                    "id": tc_dict_intermediate["id"],
                    "type": "function", # Explicitly set type
                    "function": {
                        "name": tc_dict_intermediate["function"]["name"],
                        "arguments": stringified_args
                    }
                })
            
            ai_msg["tool_calls"] = final_tool_calls_for_api
            # Ensure content is None if only tool_calls are present, or if content was already None
            if "content" not in ai_msg or ai_msg["content"] is None: # Check if content key exists and is None
                 ai_msg["content"] = None
        
        if role == "tool":
            if tool_call_id is not None:
                ai_msg["tool_call_id"] = tool_call_id
            if content is None: # Content for role:tool is mandatory
                ai_msg["content"] = "[Tool execution result not available]"
            # else content is already set

        messages_for_ai.append(ai_msg)

    # Combine batched user inputs if needed
    if current_batched_user_inputs:
        # Ensure names are preserved correctly, especially for the 'name' field of the combined message
        # The 'name' field in the combined message should ideally represent the sender of the *first* message in the batch,
        # or be a generic identifier if that's more appropriate for the LLM.
        # For now, using the name of the first user in the batch.
        first_user_name_in_batch = current_batched_user_inputs[0]["name"]
        
        # Join parts with a newline, avoids manual newline appending and stripping
        # Each part should clearly indicate its original sender.
        message_parts = []
        for user_input in current_batched_user_inputs:
            sender_name = user_input.get("name", "Unknown User")
            content_text = user_input.get("content", "")
            if len(current_batched_user_inputs) == 1:
                message_parts.append(content_text)
            else:
                # The test expects a literal \n, so we construct the string accordingly.
                message_parts.append(f"{sender_name}: {content_text}")

        if len(current_batched_user_inputs) > 1:
            # For multiple messages, the test expects them to be joined by a literal '\n'
            # which means the string itself should contain '\' followed by 'n'.
            # This is different from a newline character.
            # However, the previous logic was to join with "\n" (newline character).
            # Let's stick to joining with a newline character as that's more standard for multi-line text.
            # The test might need adjustment if it strictly requires literal '\n'.
            # For now, I will assume the test wants actual newlines between messages.
            combined_content = "\n".join(message_parts)
        else:
            combined_content = message_parts[0] if message_parts else ""
        
        messages_for_ai.append({"role": "user", "name": first_user_name_in_batch, "content": combined_content})
    
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

def build_summary_generation_payload(
    transcript_for_summarization: str, 
    previous_summary: Optional[str],
    db_path: str, # Added db_path
    bot_display_name: str = "AI Bot" # Added bot_display_name with a default
) -> List[Dict[str, str]]:
    """Builds the payload for requesting a summary from an AI model, using DB prompt."""
    logger.debug("Building summary generation payload.")

    # Fetch summarization prompt from database
    summarization_prompt_tuple = database.get_prompt(db_path, "summarization_default")
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