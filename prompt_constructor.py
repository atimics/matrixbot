from typing import List, Dict, Optional, Any # Added Any

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
    "{global_summary_section}" # Placeholder for global summary
    "{channel_summary_section}" # Placeholder for channel summary
    "Based on the full context provided (system instructions, global summary, channel summary, and recent messages), "
    "determine the best course of action, whether it's a textual response or using a tool."
)

GLOBAL_SUMMARY_SYSTEM_PROMPT_INSERT = (
    "Here's a high-level summary of discussions across relevant channels:\\n{global_summary}\\n---\\n"
)

CHANNEL_SUMMARY_SYSTEM_PROMPT_INSERT = ( # Renamed from SUMMARY_SYSTEM_PROMPT_INSERT
    "Here's a summary of earlier parts of the current channel's conversation:\\n{channel_summary}\\n---\\n"
)

def build_status_prompt(bot_display_name: str = "AI Bot"):
    # You can enhance this prompt with more personalized or context-driven content!
    return [
        {"role": "system", "content": f"You are an AI assistant named {bot_display_name}. Generate a short, friendly status message summarizing your readiness to help in chat. Keep it under 10 words."}
    ]

def get_formatted_system_prompt(
    bot_name: str, 
    channel_summary: Optional[str] = None,
    global_summary: Optional[str] = None # Added global_summary
) -> str:
    global_summary_section_text = ""
    if global_summary:
        global_summary_section_text = GLOBAL_SUMMARY_SYSTEM_PROMPT_INSERT.format(global_summary=global_summary)
    
    channel_summary_section_text = ""
    if channel_summary:
        channel_summary_section_text = CHANNEL_SUMMARY_SYSTEM_PROMPT_INSERT.format(channel_summary=channel_summary)
        
    return DEFAULT_SYSTEM_PROMPT_TEMPLATE.format(
        bot_name=bot_name, 
        global_summary_section=global_summary_section_text,
        channel_summary_section=channel_summary_section_text
    )

def build_messages_for_ai(
    historical_messages: List[Dict[str, Any]],  # Changed type hint for historical_messages
    current_batched_user_inputs: List[Dict[str, str]], 
    bot_display_name: str,
    channel_summary: Optional[str] = None,
    global_summary_text: Optional[str] = None, # Added global_summary_text
    last_user_event_id_in_batch: Optional[str] = None,
    include_system_prompt: bool = True
) -> List[Dict[str, Any]]: # Changed return type hint
    messages_for_ai: List[Dict[str, Any]] = [] # Changed type hint
    if include_system_prompt:
        system_message_content = get_formatted_system_prompt(
            bot_display_name, 
            channel_summary,
            global_summary_text # Pass global_summary_text
        )
        messages_for_ai.append({"role": "system", "content": system_message_content})
        # Add explicit tool guidance if event ID is available
        if last_user_event_id_in_batch:
            messages_for_ai.append({
                "role": "system",
                "content": (
                    f"When using a tool that requires an event_id (such as replying or reacting), "
                    f"always use this event_id: {last_user_event_id_in_batch}. Do not invent or use placeholder values. "
                    f"If you need to reply or react, use this event_id as the argument."
                )
            })

    for msg in historical_messages:
        ai_msg: Dict[str, Any] = {"role": msg["role"]} # Changed type hint
        
        # Content is usually present, but can be None for assistant messages with only tool_calls
        if "content" in msg and msg["content"] is not None:
            ai_msg["content"] = msg["content"]
        elif msg["role"] == "assistant" and not msg.get("tool_calls"): # Assistant message with no content and no tool_calls
             ai_msg["content"] = "" # Ensure content is at least an empty string if no tool_calls

        if "name" in msg: 
            ai_msg["name"] = msg["name"]
        
        # Add tool_calls for assistant messages if present
        if msg["role"] == "assistant" and "tool_calls" in msg and msg["tool_calls"] is not None:
            ai_msg["tool_calls"] = msg["tool_calls"]
            # If content was None and tool_calls are present, OpenAI expects content to be null or not present.
            # If content was previously set to "" but there are tool_calls, we can remove it or set to None.
            # For simplicity, if tool_calls are present, we ensure content is not an empty string unless it was explicitly that.
            if ai_msg.get("content") == "" and not ("content" in msg and msg["content"] == ""): # if we defaulted it to ""
                if "content" in msg and msg["content"] is None:
                    ai_msg["content"] = None # Explicitly null if original was null
                else:
                    ai_msg.pop("content", None) # Or remove if it was just a placeholder

        # Add tool_call_id for tool messages if present
        if msg["role"] == "tool" and "tool_call_id" in msg:
            ai_msg["tool_call_id"] = msg["tool_call_id"]
            # Content for role:tool is mandatory. It should have been set by RoomLogicService.
            # Ensure it's present, even if it's just a string indicating an error or success.
            if "content" not in msg or msg["content"] is None:
                 ai_msg["content"] = "[Missing tool content]" # Fallback, though this shouldn't happen

        messages_for_ai.append(ai_msg)

    if current_batched_user_inputs:
        if len(current_batched_user_inputs) == 1:
            single_input = current_batched_user_inputs[0]
            messages_for_ai.append({"role": "user", "name": single_input["name"], "content": single_input["content"]})
        else:
            combined_content = ""
            first_user_name_in_batch = current_batched_user_inputs[0]["name"]
            for user_input in current_batched_user_inputs:
                combined_content += f"{user_input['name']}: {user_input['content']}\n"
            messages_for_ai.append({"role": "user", "name": first_user_name_in_batch, "content": combined_content.strip()})
    return messages_for_ai

SUMMARY_GENERATION_PROMPT_TEMPLATE = (
    "You are an AI tasked with summarizing conversations. Below is a transcript of recent messages. "
    "{previous_summary_context}"
    "Please provide a concise summary of these new messages, capturing key topics, questions, and decisions. "
    "The summary should be suitable for providing context for future interactions. "
    "Focus on information that would be important for someone rejoining the conversation or for an AI to understand the current state. "
    "Do not include your own preamble like 'Here is the summary'. Just provide the summary text.\n\n"
    "Recent Messages (new since last summary):\n{message_transcript}\n{bot_display_name}: "
)
PREVIOUS_SUMMARY_CONTEXT_TEMPLATE = "A previous summary of the conversation up to this point was:\n{previous_summary}\n---\nBased on this, summarize the *new* messages that follow.\n"

def build_summary_generation_payload(
    messages_to_summarize: List[Dict[str, str]], 
    bot_display_name: str, # Changed from bot_name
    previous_summary: Optional[str] = None
) -> List[Dict[str,str]]:
    transcript = "".join(f"{msg['name']}: {msg['content']}\n" for msg in messages_to_summarize)
    previous_summary_context_text = PREVIOUS_SUMMARY_CONTEXT_TEMPLATE.format(previous_summary=previous_summary) if previous_summary else ""
    prompt_content = SUMMARY_GENERATION_PROMPT_TEMPLATE.format(
        message_transcript=transcript.strip(),
        previous_summary_context=previous_summary_context_text,
        bot_display_name=bot_display_name # Added this format argument
    )
    return [{"role": "user", "content": prompt_content}]