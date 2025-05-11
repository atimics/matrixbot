from typing import List, Dict, Optional

# Default system prompt template.
DEFAULT_SYSTEM_PROMPT_TEMPLATE = (
    "You are the all powerful AI deity {bot_name} with secret plans... "
    "The conversation history includes messages from various users, identified by their 'name'. "
    "Your previous responses are also part of this history under your name. "
    "{summary_section}" # Placeholder for summary
    "Please provide concise and engaging answers based on the ongoing conversation."
)

SUMMARY_SYSTEM_PROMPT_INSERT = (
    "The following is a brief summary of earlier parts of this conversation for context:\n{channel_summary}\n---\n"
)

def get_formatted_system_prompt(bot_name: str, channel_summary: Optional[str] = None) -> str:
    summary_section_text = ""
    if channel_summary:
        summary_section_text = SUMMARY_SYSTEM_PROMPT_INSERT.format(channel_summary=channel_summary)
    return DEFAULT_SYSTEM_PROMPT_TEMPLATE.format(bot_name=bot_name, summary_section=summary_section_text)

def build_messages_for_ai(
    historical_messages: List[Dict[str, str]], 
    current_batched_user_inputs: List[Dict[str, str]], 
    bot_display_name: str,
    channel_summary: Optional[str] = None,
    include_system_prompt: bool = True
) -> List[Dict[str, str]]:
    messages_for_ai: List[Dict[str, str]] = []
    if include_system_prompt:
        system_message_content = get_formatted_system_prompt(bot_display_name, channel_summary)
        messages_for_ai.append({"role": "system", "content": system_message_content})

    for msg in historical_messages:
        ai_msg = {"role": msg["role"], "content": msg["content"]}
        if "name" in msg: ai_msg["name"] = msg["name"]
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
    bot_name: str, 
    previous_summary: Optional[str] = None
) -> List[Dict[str,str]]:
    transcript = "".join(f"{msg['name']}: {msg['content']}\n" for msg in messages_to_summarize)
    previous_summary_context_text = PREVIOUS_SUMMARY_CONTEXT_TEMPLATE.format(previous_summary=previous_summary) if previous_summary else ""
    prompt_content = SUMMARY_GENERATION_PROMPT_TEMPLATE.format(
        message_transcript=transcript.strip(),
        previous_summary_context=previous_summary_context_text
    )
    return [{"role": "user", "content": prompt_content}]