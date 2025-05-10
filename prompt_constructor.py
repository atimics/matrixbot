from typing import List, Dict, Optional

# Default system prompt template.
DEFAULT_SYSTEM_PROMPT_TEMPLATE = (
    "You are a helpful AI assistant named {bot_name} participating in a group chat. "
    "The conversation history includes messages from various users, identified by their 'name'. "
    "Your previous responses are also part of this history under your name. "
    "{summary_section}" # Placeholder for summary
    "Please provide concise and relevant answers based on the ongoing conversation."
)

SUMMARY_SYSTEM_PROMPT_INSERT = (
    "The following is a brief summary of earlier parts of this conversation for context:\n{channel_summary}\n---\n"
)

def get_formatted_system_prompt(bot_name: str, channel_summary: Optional[str] = None) -> str:
    """Formats the system prompt with the bot's name and an optional channel summary."""
    summary_section_text = ""
    if channel_summary:
        summary_section_text = SUMMARY_SYSTEM_PROMPT_INSERT.format(channel_summary=channel_summary)
    
    return DEFAULT_SYSTEM_PROMPT_TEMPLATE.format(bot_name=bot_name, summary_section=summary_section_text)

def build_messages_for_ai(
    historical_messages: List[Dict[str, str]], # Short-term memory
    current_batched_user_inputs: List[Dict[str, str]], # Messages in the current batch
    bot_display_name: str,
    channel_summary: Optional[str] = None,
    include_system_prompt: bool = True
) -> List[Dict[str, str]]:
    """
    Constructs the 'messages' payload for the AI API.

    Args:
        historical_messages: Short-term recent conversation history.
        current_batched_user_inputs: List of user messages in the current processing batch.
                                     Each dict: {"name": "sender_name", "content": "message_text"}
        bot_display_name: The display name of the bot.
        channel_summary: Optional long-term summary of the channel.
        include_system_prompt: Whether to prepend the formatted system prompt.

    Returns:
        A list of message dictionaries ready to be sent to the AI.
    """
    messages_for_ai: List[Dict[str, str]] = []

    if include_system_prompt:
        system_message_content = get_formatted_system_prompt(bot_display_name, channel_summary)
        messages_for_ai.append({"role": "system", "content": system_message_content})

    # Add the short-term historical messages
    messages_for_ai.extend(historical_messages)

    # Add the current batch of user messages.
    # These could be combined into one "user" message or kept separate.
    # For now, let's combine them if there are multiple, to represent a single "turn" of user input.
    if current_batched_user_inputs:
        if len(current_batched_user_inputs) == 1:
            # If only one message in batch, add it directly
            single_input = current_batched_user_inputs[0]
            messages_for_ai.append({
                "role": "user",
                "name": single_input["name"],
                "content": single_input["content"]
            })
        else:
            # If multiple, combine them. The "name" could be a generic like "Multiple Users"
            # or the name of the first user in the batch. Or, list names.
            # For simplicity, let's just concatenate and attribute to the first user for now,
            # but prefix with actual sender names.
            combined_content = ""
            first_user_name = current_batched_user_inputs[0]["name"]
            for user_input in current_batched_user_inputs:
                combined_content += f"{user_input['name']}: {user_input['content']}\n"
            
            messages_for_ai.append({
                "role": "user",
                "name": first_user_name, # Or a generic name like "GroupInput"
                "content": combined_content.strip()
            })
            
    return messages_for_ai


SUMMARY_GENERATION_PROMPT_TEMPLATE = (
    "You are an AI tasked with summarizing conversations. "
    "Below is a transcript of recent messages. "
    "{previous_summary_context}"
    "Please provide a concise summary of these new messages, capturing key topics, questions, and decisions. "
    "The summary should be suitable for providing context for future interactions. "
    "Focus on information that would be important for someone rejoining the conversation or for an AI to understand the current state. "
    "Do not include your own preamble like 'Here is the summary'. Just provide the summary text.\n\n"
    "Recent Messages:\n"
    "{message_transcript}"
)

PREVIOUS_SUMMARY_CONTEXT_TEMPLATE = "A previous summary of the conversation up to this point was:\n{previous_summary}\n---\nBased on this, summarize the *new* messages that follow.\n"

def build_summary_generation_payload(
    messages_to_summarize: List[Dict[str, str]], # list of {"name": ..., "content": ...}
    bot_name: str, # The bot's own name
    previous_summary: Optional[str] = None
) -> List[Dict[str,str]]:
    """Builds the payload for asking the AI to summarize messages."""
    
    transcript = ""
    for msg in messages_to_summarize:
        transcript += f"{msg['name']}: {msg['content']}\n"
    
    previous_summary_context_text = ""
    if previous_summary:
        previous_summary_context_text = PREVIOUS_SUMMARY_CONTEXT_TEMPLATE.format(previous_summary=previous_summary)

    prompt_content = SUMMARY_GENERATION_PROMPT_TEMPLATE.format(
        message_transcript=transcript.strip(),
        previous_summary_context=previous_summary_context_text
    )
    
    # The summarization task is a direct instruction to the AI.
    # We can frame this as a user request to a specialized summarizer model/role.
    return [
        {"role": "user", "content": prompt_content}
    ]