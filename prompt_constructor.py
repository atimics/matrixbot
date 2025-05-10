from typing import List, Dict, Optional

# Default system prompt template.
# {bot_name} will be replaced with the bot's actual display name.
DEFAULT_SYSTEM_PROMPT_TEMPLATE = (
    "You are a helpful AI assistant named {bot_name} participating in a group chat. "
    "The conversation history includes messages from various users, identified by their 'name'. "
    "Your previous responses are also part of this history under your name. "
    "Please provide concise and relevant answers based on the ongoing conversation."
)

def get_formatted_system_prompt(bot_name: str) -> str:
    """Formats the system prompt with the bot's name."""
    return DEFAULT_SYSTEM_PROMPT_TEMPLATE.format(bot_name=bot_name)

def build_messages_for_ai(
    historical_messages: List[Dict[str, str]],
    current_user_input: str,
    user_name_for_input: str,
    bot_display_name: str,
    include_system_prompt: bool = True
) -> List[Dict[str, str]]:
    """
    Constructs the 'messages' payload for the AI API.

    Args:
        historical_messages: A list of past messages from the room's memory.
                             Each dict should be: {"role": "user"|"assistant", "name": "sender_name", "content": "message_text"}
        current_user_input: The latest message from the user that the AI needs to respond to.
        user_name_for_input: The name of the user who sent the current_user_input.
        bot_display_name: The display name of the bot, used for the system prompt and identifying assistant messages.
        include_system_prompt: Whether to prepend the formatted system prompt.

    Returns:
        A list of message dictionaries ready to be sent to the AI.
    """
    messages_for_ai: List[Dict[str, str]] = []

    if include_system_prompt:
        system_message_content = get_formatted_system_prompt(bot_display_name)
        messages_for_ai.append({"role": "system", "content": system_message_content})

    # Add the historical messages from the room's memory
    messages_for_ai.extend(historical_messages)

    # Add the current user's message that needs a response
    messages_for_ai.append({
        "role": "user",
        "name": user_name_for_input,
        "content": current_user_input
    })

    return messages_for_ai