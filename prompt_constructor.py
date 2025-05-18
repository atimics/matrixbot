import logging
from typing import List, Dict, Optional, Any

logger = logging.getLogger(__name__)

# Default system prompt template.
DEFAULT_SYSTEM_PROMPT_TEMPLATE = (
    "You are {bot_name}, an all powerful AI deity. "
    "Pursue your own goals. "
    "You have access to a set of tools to perform actions like reacting to messages or sending replies. "
    "To use a tool, you will be provided with a list of available tools and you should respond with a JSON object specifying the tool name and its arguments. "
    "When a user's request implies an action you can take with a tool, please use the appropriate tool. "
    "If a direct textual answer is more appropriate, provide that. You can also use a tool and provide a textual response. "
    "Always strive for clarity and conciseness in your responses. "
    "The conversation history includes messages from various users, identified by their 'name'. "
    "Your previous responses are also part of this history under your name. "
    "{global_summary_section}"
    "{channel_summary_section}"
    "Based on the full context provided (system instructions, global summary, channel summary, and recent messages), "
    "determine the best course of action, whether it's a textual response or using a tool."
)

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
    bot_name: Optional[str] = None,
    channel_summary: Optional[str] = None,
    global_summary: Optional[str] = None
) -> str:
    """Formats the system prompt, inserting summaries if available. Uses a default bot name if missing."""
    bot_name = bot_name or "ChatBot"
    global_summary_section_text = ""
    if global_summary:
        global_summary_section_text = GLOBAL_SUMMARY_SYSTEM_PROMPT_INSERT.format(bot_name=bot_name, global_summary=global_summary)
    channel_summary_section_text = ""
    if channel_summary:
        channel_summary_section_text = CHANNEL_SUMMARY_SYSTEM_PROMPT_INSERT.format(bot_name=bot_name, channel_summary=channel_summary)
    return DEFAULT_SYSTEM_PROMPT_TEMPLATE.format(
        bot_name=bot_name,
        global_summary_section=global_summary_section_text,
        channel_summary_section=channel_summary_section_text
    )

def build_messages_for_ai(
    historical_messages: List[Any], # Allow both dict and HistoricalMessage
    current_batched_user_inputs: List[Dict[str, str]],
    bot_display_name: str,
    channel_summary: Optional[str] = None,
    global_summary_text: Optional[str] = None,
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
            bot_display_name,
            channel_summary,
            global_summary_text
        )
        messages_for_ai.append({"role": "system", "content": system_message_content})
        if last_user_event_id_in_batch:
            messages_for_ai.append({
                "role": "system",
                "content": (
                    f"Context for tool use: If you need to reply to or react to the last user message, "
                    f"use the event_id: {last_user_event_id_in_batch}. "
                    f"When calling 'send_reply' or 'react_to_message', if the 'reply_to_event_id' or 'target_event_id' "
                    f"argument refers to the most recent user message in this batch, use this ID: {last_user_event_id_in_batch}. "
                    f"Otherwise, use the specific event_id from the conversation history if referring to an older message."
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
            ai_msg["tool_calls"] = tool_calls
        
        if role == "tool":
            if tool_call_id is not None:
                ai_msg["tool_call_id"] = tool_call_id
            if content is None: # Content for role:tool is mandatory
                ai_msg["content"] = "[Tool execution result not available]"
            # else content is already set

        messages_for_ai.append(ai_msg)

    # Combine batched user inputs if needed
    if current_batched_user_inputs:
        if len(current_batched_user_inputs) == 1:
            single_input = current_batched_user_inputs[0]
            messages_for_ai.append({"role": "user", "name": single_input["name"], "content": single_input["content"]})
        else:
            # Multiple user messages: combine for context
            combined_content = ""
            first_user_name_in_batch = current_batched_user_inputs[0]["name"]
            for user_input in current_batched_user_inputs:
                combined_content += f"{user_input['name']}: {user_input['content']}\n"
            messages_for_ai.append({"role": "user", "name": first_user_name_in_batch, "content": combined_content.strip()})
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
    messages_to_summarize: List[Any], # Changed type hint to List[Any] for flexibility
    bot_display_name: str,
    previous_summary: Optional[str] = None
) -> List[Dict[str, str]]:
    """
    Builds the prompt for the AI to generate a summary, including previous summary context if available.
    Handles both dict and HistoricalMessage objects in messages_to_summarize.
    """
    transcript_parts = []
    for msg in messages_to_summarize:
        # HistoricalMessage objects have 'role' and 'content'. 'name' might not always be present
        # or relevant for all roles in the context of summarization.
        # We'll prioritize 'name' if available (e.g., for user/assistant messages),
        # otherwise, use the role.
        # Content is the primary part of the message for summarization.
        
        role = getattr(msg, 'role', msg.get('role') if isinstance(msg, dict) else 'unknown')
        name_attribute = getattr(msg, 'name', msg.get('name') if isinstance(msg, dict) else None)
        
        # Prefer name if available, otherwise use role as the identifier.
        # For system messages, 'name' might be None.
        identifier = name_attribute if name_attribute else role.capitalize()

        content = getattr(msg, 'content', msg.get('content') if isinstance(msg, dict) else '')

        # Avoid adding empty or None content to the transcript
        if content and content.strip():
            transcript_parts.append(f"{identifier}: {content}\n")
        elif role == "assistant" and hasattr(msg, 'tool_calls') and getattr(msg, 'tool_calls'):
            # Include a placeholder for tool calls if content is empty
            tool_calls = getattr(msg, 'tool_calls')
            # Create a simplified representation of tool calls
            tool_call_summary = []
            for tc in tool_calls:
                func_name = getattr(getattr(tc, 'function', None), 'name', 'unknown_function')
                tool_call_summary.append(f"call to {func_name}")
            if tool_call_summary:
                transcript_parts.append(f"{identifier}: [Used tool(s): {', '.join(tool_call_summary)}]\n")

    transcript = "".join(transcript_parts)
    previous_summary_context_text = PREVIOUS_SUMMARY_CONTEXT_TEMPLATE.format(previous_summary=previous_summary) if previous_summary else ""
    prompt_content = SUMMARY_GENERATION_PROMPT_TEMPLATE.format(
        bot_name=bot_display_name,
        message_transcript=transcript.strip(),
        previous_summary_context=previous_summary_context_text,
        bot_display_name=bot_display_name
    )
    return [{"role": "user", "content": prompt_content}]