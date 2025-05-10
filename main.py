import asyncio
import json
import http.client
import os
import time
from dotenv import load_dotenv
from typing import Optional, Dict, Any, List

from nio import (
    AsyncClient,
    MatrixRoom,
    RoomMessageText,
    LoginResponse,
    RoomSendResponse,
    ProfileGetResponse,
    SyncError, # For more specific error handling
    LocalProtocolError, # For more specific error handling
)

import prompt_constructor
import database # Our new database module

# --- Configuration ---
load_dotenv()

# Matrix Configuration
MATRIX_HOMESERVER = os.getenv("MATRIX_HOMESERVER")
MATRIX_USER_ID = os.getenv("MATRIX_USER_ID")
MATRIX_PASSWORD = os.getenv("MATRIX_PASSWORD")
MATRIX_ROOM_ID = os.getenv("MATRIX_ROOM_ID") # Optional startup room
DEVICE_NAME = os.getenv("DEVICE_NAME", "NioChatBotSummarizer")

# OpenRouter Configuration
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
OPENROUTER_SUMMARY_MODEL = os.getenv("OPENROUTER_SUMMARY_MODEL", "openai/gpt-3.5-turbo") # Cheaper model for summaries
YOUR_SITE_URL = os.getenv("YOUR_SITE_URL", "https://your-matrix-bot.example.com")
YOUR_SITE_NAME = os.getenv("YOUR_SITE_NAME", "MyMatrixBotSummarizer")

# Active Listening / Decay / Batching Configuration
POLLING_INITIAL_INTERVAL = int(os.getenv("POLLING_INITIAL_INTERVAL", "10")) # Interval for decay checks
POLLING_MAX_INTERVAL = int(os.getenv("POLLING_MAX_INTERVAL", "120"))
POLLING_INACTIVITY_DECAY_CYCLES = int(os.getenv("POLLING_INACTIVITY_DECAY_CYCLES", "3"))
MESSAGE_BATCH_DELAY = float(os.getenv("MESSAGE_BATCH_DELAY", "3.0")) # Seconds to wait for more messages before responding

# Memory and Summary Configuration
MAX_MESSAGES_PER_ROOM_MEMORY = int(os.getenv("MAX_MESSAGES_PER_ROOM_MEMORY", "10")) # Short-term memory (user+AI turns)
SUMMARY_UPDATE_MESSAGE_COUNT = int(os.getenv("SUMMARY_UPDATE_MESSAGE_COUNT", "15")) # Update summary after this many new messages (user+AI)

# --- Global State ---
BOT_DISPLAY_NAME: Optional[str] = "ChatBot"
# room_activity_config stores state for rooms. New fields:
# 'pending_messages_for_batch': List of raw incoming messages for current batch
# 'batch_response_task': asyncio.Task for debounced AI response
# 'messages_since_last_summary': Counter for triggering summary updates
room_activity_config: Dict[str, Dict[str, Any]] = {}


# --- Utility Functions ---
async def send_matrix_message(
    client: AsyncClient, room_id: str, text: str
) -> Optional[RoomSendResponse]:
    if not text:
        print(f"[{room_id}] Attempted to send an empty message. Skipping.")
        return None
    try:
        # Limit log length and replace newlines for cleaner logging
        log_text = text[:70].replace('\n', ' ').replace('\r', '')
        print(f"[{room_id}] Sending message: \"{log_text}{'...' if len(text) > 70 else ''}\"")
        return await client.room_send(
            room_id=room_id,
            message_type="m.room.message",
            content={"msgtype": "m.text", "body": text},
        )
    except Exception as e:
        print(f"Error sending message to {room_id}: {e}")
        return None


# --- OpenRouter API Call (modified to allow different models) ---
def get_openrouter_response(messages_payload: List[Dict[str, str]], model_name: str = OPENROUTER_MODEL) -> str:
    global BOT_DISPLAY_NAME
    if not OPENROUTER_API_KEY or "YOUR_OPENROUTER_API_KEY" in OPENROUTER_API_KEY:
        print(f"OpenRouter API key not configured. Skipping API call for model {model_name}.")
        return f"Sorry, my AI connection is not configured."

    if not messages_payload:
        print(f"Error: Empty messages_payload passed to get_openrouter_response for model {model_name}.")
        return "Sorry, I received an empty request."

    conn = http.client.HTTPSConnection("openrouter.ai")
    payload_data = {
        "model": model_name,
        "messages": messages_payload,
    }
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": YOUR_SITE_URL,
        "X-Title": YOUR_SITE_NAME,
    }
    try:
        print(f"Sending to OpenRouter with model {model_name}. Payload messages count: {len(messages_payload)}")
        conn.request("POST", "/api/v1/chat/completions", json.dumps(payload_data), headers)
        res = conn.getresponse()
        data = res.read()
        response_json = json.loads(data.decode("utf-8"))

        if res.status == 200 and response_json.get("choices"):
            return response_json["choices"][0]["message"]["content"]
        else:
            error_message = response_json.get("error", {}).get("message", "Unknown error")
            print(f"Error from OpenRouter ({model_name}): {res.status} - {error_message} - Response: {response_json}")
            return f"Sorry, I couldn't get a response from the AI ({model_name}). (Error: {res.status})"
    except Exception as e:
        print(f"Error connecting to OpenRouter ({model_name}): {e}")
        return f"Sorry, there was an issue connecting to the AI service ({model_name})."
    finally:
        conn.close()

# --- Summary Management ---
async def update_channel_summary_if_needed(room_id: str, client: AsyncClient, force_update: bool = False):
    config = room_activity_config.get(room_id)
    if not config: return

    # Check if enough messages have accumulated or if forced
    # We will use short-term memory for summarization.
    short_term_memory: List[Dict[str,str]] = config.get('memory', [])
    
    # This logic needs refinement: what *exactly* do we summarize?
    # For now, let's assume we summarize the entire current short_term_memory if a threshold is met.
    # A more advanced approach would be to get messages since last_event_id_summarized from DB.
    
    messages_in_short_term_mem = len(short_term_memory) # Counts user + AI turns

    if force_update or (messages_in_short_term_mem > 0 and config.get('messages_since_last_summary', 0) >= SUMMARY_UPDATE_MESSAGE_COUNT) :
        print(f"[{room_id}] Triggering summary update. Force: {force_update}, Msgs since last: {config.get('messages_since_last_summary',0)}")
        
        previous_summary_data = database.get_summary(room_id)
        previous_summary_text = previous_summary_data[0] if previous_summary_data else None
        # last_event_id_summarized = previous_summary_data[1] if previous_summary_data else None
        
        # We need a list of {"name": ..., "content": ...} from short_term_memory
        # The short_term_memory already has this structure, but 'role' needs to be handled.
        # For summarization, the 'role' (user/assistant) is less important than the content and speaker name.
        messages_for_summary_prompt: List[Dict[str,str]] = []
        for mem_item in short_term_memory:
            messages_for_summary_prompt.append({"name": mem_item.get("name", "Unknown"), "content": mem_item["content"]})

        if not messages_for_summary_prompt:
            print(f"[{room_id}] No messages in short-term memory to summarize.")
            config['messages_since_last_summary'] = 0 # Reset counter
            return

        summary_payload = prompt_constructor.build_summary_generation_payload(
            messages_to_summarize=messages_for_summary_prompt,
            bot_name=BOT_DISPLAY_NAME,
            previous_summary=previous_summary_text
        )
        
        new_summary = get_openrouter_response(summary_payload, model_name=OPENROUTER_SUMMARY_MODEL)

        if "Sorry, I couldn't" not in new_summary and "not configured" not in new_summary:
            # TODO: Determine the 'last_event_id_summarized'. This is tricky with batched inputs.
            # For now, we're not precisely tracking it for summarization.
            # A robust way would be to store event IDs with messages in short-term memory.
            database.update_summary(room_id, new_summary, last_event_id_summarized=None) 
            print(f"[{room_id}] New summary generated and stored. Length: {len(new_summary)}")
            config['messages_since_last_summary'] = 0 # Reset counter
            
            # Optional: Clear short_term_memory after summarization to prevent it growing too large
            # if it's only used for summarization. If it's also for immediate context,
            # then keep it and rely on MAX_MESSAGES_PER_ROOM_MEMORY truncation.
            # config['memory'] = [] # Example: Clearing memory after summarization
        else:
            print(f"[{room_id}] Failed to generate a valid summary.")


# --- Batched Response Processing ---
async def process_batched_messages(room_id: str, client: AsyncClient):
    config = room_activity_config.get(room_id)
    if not config or not config.get('is_active_listening', False):
        print(f"[{room_id}] process_batched_messages: Not active or no config. Aborting.")
        return

    pending_batch: List[Dict[str, str]] = list(config.get('pending_messages_for_batch', [])) # copy
    config['pending_messages_for_batch'] = [] # Clear immediately

    if not pending_batch:
        print(f"[{room_id}] process_batched_messages: No messages in batch. Aborting.")
        return

    print(f"[{room_id}] Processing batch of {len(pending_batch)} message(s).")

    short_term_memory: List[Dict[str, str]] = config.get('memory', [])
    summary_data = database.get_summary(room_id)
    channel_summary_text = summary_data[0] if summary_data else None

    # Construct payload for AI using prompt_constructor
    messages_payload_for_ai = prompt_constructor.build_messages_for_ai(
        historical_messages=list(short_term_memory), # pass a copy
        current_batched_user_inputs=pending_batch, # these are {"name": ..., "content": ...}
        bot_display_name=BOT_DISPLAY_NAME,
        channel_summary=channel_summary_text
    )

    ai_response_text = get_openrouter_response(messages_payload_for_ai, model_name=OPENROUTER_MODEL)
    await send_matrix_message(client, room_id, ai_response_text)

    # Update short-term memory
    # 1. Add the combined batched user input as a single "user" turn
    # This representation is simplified; more complex scenarios might store individual messages.
    if pending_batch:
        combined_user_content = ""
        first_user_name = pending_batch[0]["name"]
        for msg_data in pending_batch:
            combined_user_content += f"{msg_data['name']}: {msg_data['content']}\n"
        
        short_term_memory.append({
            "role": "user", 
            "name": first_user_name, # Or a generic "Multiple Users"
            "content": combined_user_content.strip()
        })
        config['messages_since_last_summary'] = config.get('messages_since_last_summary', 0) + 1


    # 2. Add AI's response
    is_error_response = "Sorry, I couldn't" in ai_response_text or \
                        "not configured" in ai_response_text or \
                        "issue connecting" in ai_response_text
    if ai_response_text and not is_error_response:
        short_term_memory.append({
            "role": "assistant", 
            "name": BOT_DISPLAY_NAME, 
            "content": ai_response_text
        })
        config['messages_since_last_summary'] = config.get('messages_since_last_summary', 0) + 1


    # 3. Truncate short-term memory
    while len(short_term_memory) > MAX_MESSAGES_PER_ROOM_MEMORY:
        short_term_memory.pop(0)
    
    config['memory'] = short_term_memory # Ensure the main config is updated
    print(f"[{room_id}] Short-term memory updated. Size: {len(short_term_memory)}. Msgs since summary: {config.get('messages_since_last_summary',0)}")

    # Trigger summary update if needed
    await update_channel_summary_if_needed(room_id, client)


# --- Matrix Bot Logic: Active Listening and Decay Management ---
async def manage_room_activity_decay(room_id: str, client: AsyncClient):
    # (Largely same, but calls force summary update on deactivation)
    initial_interval = room_activity_config.get(room_id, {}).get('current_interval', POLLING_INITIAL_INTERVAL)
    print(f"[{room_id}] Starting activity decay manager. Initial check interval: {initial_interval}s")
    try:
        while True:
            current_config = room_activity_config.get(room_id)
            if not current_config or not current_config.get('is_active_listening', False):
                print(f"[{room_id}] Decay manager: No longer active listening or config removed. Exiting task.")
                break
            sleep_duration = current_config['current_interval']
            await asyncio.sleep(sleep_duration)
            current_config = room_activity_config.get(room_id) # Re-fetch
            if not current_config or not current_config.get('is_active_listening', False):
                print(f"[{room_id}] Decay manager: No longer active listening or config removed after sleep. Exiting task.")
                break
            now = time.time()
            if (now - current_config['last_message_timestamp']) >= current_config['current_interval']:
                new_interval = min(current_config['current_interval'] * 2, POLLING_MAX_INTERVAL)
                print(f"[{room_id}] Decay: No detected activity for >= {current_config['current_interval']}s. New interval: {new_interval}s.")
                current_config['current_interval'] = new_interval
                if new_interval == POLLING_MAX_INTERVAL:
                    current_config['max_interval_no_activity_cycles'] += 1
                else:
                    current_config['max_interval_no_activity_cycles'] = 0
                if current_config['max_interval_no_activity_cycles'] >= POLLING_INACTIVITY_DECAY_CYCLES:
                    current_config['is_active_listening'] = False
                    print(f"[{room_id}] Decay: Deactivating listening. Forcing summary update.")
                    await update_channel_summary_if_needed(room_id, client, force_update=True) # Force summary
                    await send_matrix_message(client, room_id, f"Stopping active listening due to inactivity. Mention me (@{BOT_DISPLAY_NAME}) to re-activate.")
            else:
                current_config['max_interval_no_activity_cycles'] = 0
    except asyncio.CancelledError:
        print(f"[{room_id}] Activity decay manager task was cancelled.")
        # If cancelled, it might be due to reactivation. Summary update might happen elsewhere or be pending.
    except Exception as e:
        print(f"[{room_id}] Error in activity decay manager: {e}")
    finally:
        print(f"[{room_id}] Activity decay manager task finished.")


async def message_callback(room: MatrixRoom, event: RoomMessageText, client: AsyncClient) -> None:
    global room_activity_config, BOT_DISPLAY_NAME

    if event.sender == client.user_id: return

    now = time.time()
    room_id = room.room_id
    message_body = event.body.strip()
    sender_display_name = room.user_name(event.sender) or event.sender

    print(f"Msg in '{room.display_name}' ({room_id}) from '{sender_display_name}': \"{message_body[:50].replace(os.linesep,' ')}...\"")

    current_room_config = room_activity_config.get(room_id)
    bot_name_lower = BOT_DISPLAY_NAME.lower()
    is_mention = bool(bot_name_lower and bot_name_lower in message_body.lower())

    should_activate_or_reset_listening = is_mention

    if should_activate_or_reset_listening:
        # Cancel any existing batch task if we're re-triggering listening
        if current_room_config and current_room_config.get('batch_response_task'):
            task = current_room_config['batch_response_task']
            if not task.done(): task.cancel()
        
        # Cancel existing decay task
        if current_room_config and current_room_config.get('decay_task'):
            task = current_room_config['decay_task']
            if not task.done(): task.cancel()

        # Initialize or update room config
        if not current_room_config:
            current_room_config = {
                'memory': [], 
                'pending_messages_for_batch': [],
                'messages_since_last_summary': 0,
            }
        current_room_config.update({
            'is_active_listening': True, 'current_interval': POLLING_INITIAL_INTERVAL,
            'last_message_timestamp': now, 'max_interval_no_activity_cycles': 0,
            'decay_task': asyncio.create_task(manage_room_activity_decay(room_id, client)),
            'batch_response_task': None # Will be set below
        })
        room_activity_config[room_id] = current_room_config
        print(f"[{room_id}] Activated/Reset listening. Interval: {POLLING_INITIAL_INTERVAL}s. Mem size: {len(current_room_config['memory'])}")
        # If it was a bare mention (no actual question), we might not add to batch immediately or handle differently
        # For now, all mentions will make the bot listen and process this message in a batch.

    # If not actively listening now (even after potential activation by mention), ignore further processing.
    if not current_room_config or not current_room_config.get('is_active_listening', False):
        # print(f"[{room_id}] Not actively listening. Ignoring message.")
        return

    # Add current message to the pending batch for this room
    current_room_config['pending_messages_for_batch'].append({
        "name": sender_display_name,
        "content": message_body,
        "event_id": event.event_id # Store event_id for potential future use (e.g. precise summarization point)
    })
    print(f"[{room_id}] Added message to batch. Batch size: {len(current_room_config['pending_messages_for_batch'])}")

    # Update activity timestamp for decay manager
    current_room_config['last_message_timestamp'] = now
    current_room_config['current_interval'] = POLLING_INITIAL_INTERVAL # Reset decay interval
    current_room_config['max_interval_no_activity_cycles'] = 0

    # Debounce: If a batch response task is already scheduled, cancel it and reschedule.
    if current_room_config.get('batch_response_task'):
        task = current_room_config['batch_response_task']
        if not task.done():
            # print(f"[{room_id}] Cancelling existing batch task to reschedule.")
            task.cancel()

    # Schedule (or reschedule) the batched processing
    current_room_config['batch_response_task'] = asyncio.create_task(
        _delayed_batch_processing(room_id, client, MESSAGE_BATCH_DELAY)
    )
    # print(f"[{room_id}] Scheduled/Rescheduled batch processing task.")


async def _delayed_batch_processing(room_id: str, client: AsyncClient, delay: float):
    """Helper to introduce a delay before processing the batch."""
    await asyncio.sleep(delay)
    try:
        await process_batched_messages(room_id, client)
    except asyncio.CancelledError:
        print(f"[{room_id}] Delayed batch processing task was cancelled before execution.")
    except Exception as e:
        print(f"[{room_id}] Error in delayed_batch_processing: {e}")


async def main_matrix():
    global BOT_DISPLAY_NAME, room_activity_config

    database.initialize_database() # Initialize DB

    if not all([MATRIX_HOMESERVER, MATRIX_USER_ID, MATRIX_PASSWORD]):
        print("CRITICAL: Matrix credentials not set. Exiting.")
        return
    
    client = AsyncClient(MATRIX_HOMESERVER, MATRIX_USER_ID)
    client.add_event_callback(
        lambda room, event: message_callback(room, event, client), RoomMessageText
    )

    print(f"Attempting to log in as {MATRIX_USER_ID} on {MATRIX_HOMESERVER}...")
    try:
        login_response = await client.login(MATRIX_PASSWORD, device_name=DEVICE_NAME)
        if not isinstance(login_response, LoginResponse):
            print(f"Failed to log in: {login_response}"); return
    except Exception as e:
        print(f"Login failed: {e}"); return
    print(f"Logged in as {client.user_id} (device: {client.device_id})")

    try:
        profile: ProfileGetResponse = await client.get_profile(client.user_id)
        BOT_DISPLAY_NAME = profile.displayname or (client.user_id.split(':')[0][1:] if client.user_id.startswith("@") else client.user_id.split(':')[0])
        print(f"Bot display name: '{BOT_DISPLAY_NAME}'")
    except Exception as e:
        print(f"Could not fetch display name, using fallback. Error: {e}")

    if MATRIX_ROOM_ID and "YOUR_MATRIX_ROOM_ID" not in MATRIX_ROOM_ID:
        print(f"Joining predefined room: {MATRIX_ROOM_ID}...")
        try:
            await client.join(MATRIX_ROOM_ID)
            print(f"Joined {MATRIX_ROOM_ID}")
        except Exception as e:
            print(f"Failed to join {MATRIX_ROOM_ID}: {e}")

    print("Bot is running...")
    try:
        await client.sync_forever(timeout=30000, full_state=True)
    except (SyncError, LocalProtocolError) as e: # Catch common nio sync errors
        print(f"Matrix Sync Error: {type(e).__name__} - {e}. This might be a server or network issue.")
    except Exception as e:
        print(f"Unexpected error during sync: {type(e).__name__} - {e}")
    finally:
        print("Shutting down...")
        # Cancel all active tasks
        tasks_to_cancel = []
        for r_id, cfg in list(room_activity_config.items()):
            for task_key in ['decay_task', 'batch_response_task']:
                task = cfg.get(task_key)
                if task and not task.done():
                    task.cancel()
                    tasks_to_cancel.append(task)
        
        if tasks_to_cancel:
            print(f"Waiting for {len(tasks_to_cancel)} tasks to cancel...")
            await asyncio.gather(*tasks_to_cancel, return_exceptions=True)
            print("Active tasks cancelled.")
        
        await client.close()
        print("Matrix client closed. Bot shutdown complete.")


if __name__ == "__main__":
    # (Credential checks remain the same)
    essential_configs = {"MATRIX_HOMESERVER": MATRIX_HOMESERVER, "MATRIX_USER_ID": MATRIX_USER_ID, "MATRIX_PASSWORD": MATRIX_PASSWORD}
    if any(not val or f"YOUR_{key}" in str(val) or "placeholder" in str(val).lower() for key, val in essential_configs.items()):
        print("CRITICAL: Missing or placeholder essential Matrix configs. Please set them in .env or environment. Exiting.")
    else:
        if not OPENROUTER_API_KEY or "YOUR_OPENROUTER_API_KEY" in OPENROUTER_API_KEY:
            print("Warning: OPENROUTER_API_KEY is not set or is a placeholder. AI responses will be disabled.")
        try:
            asyncio.run(main_matrix())
        except KeyboardInterrupt:
            print("Bot stopped by user (KeyboardInterrupt).")
        except Exception as e:
            print(f"An unexpected error occurred in __main__: {type(e).__name__} - {e}")