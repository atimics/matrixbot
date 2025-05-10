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
)

# Import from our new module
import prompt_constructor

# --- Configuration ---
load_dotenv()

# Matrix Configuration
MATRIX_HOMESERVER = os.getenv("MATRIX_HOMESERVER")
MATRIX_USER_ID = os.getenv("MATRIX_USER_ID")
MATRIX_PASSWORD = os.getenv("MATRIX_PASSWORD")
MATRIX_ROOM_ID = os.getenv("MATRIX_ROOM_ID")
DEVICE_NAME = os.getenv("DEVICE_NAME", "NioChatBotPollingMem")

# OpenRouter Configuration
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
YOUR_SITE_URL = os.getenv("YOUR_SITE_URL", "https://your-matrix-bot.example.com")
YOUR_SITE_NAME = os.getenv("YOUR_SITE_NAME", "MyMatrixBotWithMemory")

# Active Listening / Decay Configuration
POLLING_INITIAL_INTERVAL = int(os.getenv("POLLING_INITIAL_INTERVAL", "10"))
POLLING_MAX_INTERVAL = int(os.getenv("POLLING_MAX_INTERVAL", "120"))
POLLING_INACTIVITY_DECAY_CYCLES = int(os.getenv("POLLING_INACTIVITY_DECAY_CYCLES", "3"))

# Memory Configuration
MAX_MESSAGES_PER_ROOM_MEMORY = int(os.getenv("MAX_MESSAGES_PER_ROOM_MEMORY", "20"))

# --- Global State ---
BOT_DISPLAY_NAME: Optional[str] = "ChatBot"
room_activity_config: Dict[str, Dict[str, Any]] = {}


# --- Utility Functions ---
async def send_matrix_message(
    client: AsyncClient, room_id: str, text: str
) -> Optional[RoomSendResponse]:
    if not text:
        print(f"[{room_id}] Attempted to send an empty message. Skipping.")
        return None
    try:
        print(f"[{room_id}] Sending message: \"{text[:70].replace(os.linesep, ' ')}{'...' if len(text) > 70 else ''}\"")
        return await client.room_send(
            room_id=room_id,
            message_type="m.room.message",
            content={"msgtype": "m.text", "body": text},
        )
    except Exception as e:
        print(f"Error sending message to {room_id}: {e}")
        return None


# --- OpenRouter API Call ---
def get_openrouter_response(messages_payload: List[Dict[str, str]]) -> str:
    global BOT_DISPLAY_NAME
    if not OPENROUTER_API_KEY or "YOUR_OPENROUTER_API_KEY" in OPENROUTER_API_KEY:
        print("OpenRouter API key not configured. Skipping API call.")
        return f"Sorry, my AI connection is not configured. (Bot: {BOT_DISPLAY_NAME})"

    if not messages_payload:
        print("Error: Empty messages_payload passed to get_openrouter_response.")
        return "Sorry, I received an empty request."

    conn = http.client.HTTPSConnection("openrouter.ai")
    payload_data = {
        "model": OPENROUTER_MODEL,
        "messages": messages_payload,
    }
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": YOUR_SITE_URL,
        "X-Title": YOUR_SITE_NAME,
    }
    try:
        print(f"Sending to OpenRouter with model {OPENROUTER_MODEL}. Payload messages count: {len(messages_payload)}")
        conn.request("POST", "/api/v1/chat/completions", json.dumps(payload_data), headers)
        res = conn.getresponse()
        data = res.read()
        response_json = json.loads(data.decode("utf-8"))

        if res.status == 200 and response_json.get("choices"):
            return response_json["choices"][0]["message"]["content"]
        else:
            error_message = response_json.get("error", {}).get("message", "Unknown error")
            print(f"Error from OpenRouter: {res.status} - {error_message} - Response: {response_json}")
            return f"Sorry, I couldn't get a response from the AI. (Error: {res.status})"
    except Exception as e:
        print(f"Error connecting to OpenRouter: {e}")
        return "Sorry, there was an issue connecting to the AI service."
    finally:
        conn.close()


# --- Matrix Bot Logic: Active Listening and Decay Management ---
async def manage_room_activity_decay(room_id: str, client: AsyncClient):
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

            current_config = room_activity_config.get(room_id)
            if not current_config or not current_config.get('is_active_listening', False):
                print(f"[{room_id}] Decay manager: No longer active listening or config removed after sleep. Exiting task.")
                break

            now = time.time()
            time_since_last_activity = now - current_config['last_message_timestamp']

            if time_since_last_activity >= current_config['current_interval']:
                new_interval = min(current_config['current_interval'] * 2, POLLING_MAX_INTERVAL)
                print(f"[{room_id}] Decay: No detected activity for >= {current_config['current_interval']}s. New check interval: {new_interval}s.")
                current_config['current_interval'] = new_interval

                if current_config['current_interval'] == POLLING_MAX_INTERVAL:
                    current_config['max_interval_no_activity_cycles'] += 1
                else:
                    current_config['max_interval_no_activity_cycles'] = 0

                if current_config['max_interval_no_activity_cycles'] >= POLLING_INACTIVITY_DECAY_CYCLES:
                    current_config['is_active_listening'] = False
                    print(f"[{room_id}] Decay: Deactivating listening due to prolonged inactivity. Memory preserved.")
                    await send_matrix_message(
                        client,
                        room_id,
                        f"Stopping active listening in this room due to inactivity. "
                        f"Mention me (@{BOT_DISPLAY_NAME}) to re-activate."
                    )
            else:
                current_config['max_interval_no_activity_cycles'] = 0
    except asyncio.CancelledError:
        print(f"[{room_id}] Activity decay manager task was cancelled.")
    except Exception as e:
        print(f"[{room_id}] Error in activity decay manager: {e}")
    finally:
        print(f"[{room_id}] Activity decay manager task finished.")


async def message_callback(room: MatrixRoom, event: RoomMessageText, client: AsyncClient) -> None:
    global room_activity_config, BOT_DISPLAY_NAME

    if event.sender == client.user_id:
        return

    now = time.time()
    room_id = room.room_id
    message_body = event.body.strip()
    
    # Get sender's display name for AI context and memory
    # room.user_name(event.sender) will return the display name if known in the room,
    # otherwise it returns the Matrix User ID (MXID).
    sender_display_name = room.user_name(event.sender) 
    # Fallback to raw sender ID if display name is somehow None or empty, though room.user_name should prevent this.
    if not sender_display_name:
        sender_display_name = event.sender
        print(f"[{room_id}] Warning: Could not get display name for {event.sender} from room state, using MXID.")


    print(f"Message received in room '{room.display_name}' ({room_id}) from '{sender_display_name}' ({event.sender}): \"{message_body[:100].replace(os.linesep, ' ')}{'...' if len(message_body) > 100 else ''}\"")

    current_room_config = room_activity_config.get(room_id)

    bot_name_lower = BOT_DISPLAY_NAME.lower() if BOT_DISPLAY_NAME else ""
    is_mention = bool(BOT_DISPLAY_NAME and bot_name_lower in message_body.lower())

    text_for_ai_processing: Optional[str] = None

    if is_mention:
        existing_memory: List[Dict[str, str]] = []
        if current_room_config and 'memory' in current_room_config:
            existing_memory = current_room_config['memory']
        
        if current_room_config and current_room_config.get('decay_task'):
            old_task = current_room_config['decay_task']
            if not old_task.done():
                old_task.cancel()
                try: await asyncio.wait_for(old_task, timeout=2.0)
                except (asyncio.CancelledError, asyncio.TimeoutError): pass
                except Exception as e: print(f"[{room_id}] Error awaiting old cancelled task: {e}")
        
        room_activity_config[room_id] = {
            'is_active_listening': True, 'current_interval': POLLING_INITIAL_INTERVAL,
            'last_message_timestamp': now, 'max_interval_no_activity_cycles': 0,
            'decay_task': asyncio.create_task(manage_room_activity_decay(room_id, client)),
            'memory': existing_memory
        }
        current_room_config = room_activity_config[room_id]
        print(f"[{room_id}] Activated/Reset active listening. Interval: {POLLING_INITIAL_INTERVAL}s. Memory size: {len(existing_memory)}")

        # AI call will happen below if perform_ai_call and text_for_ai_processing are set

    if current_room_config and current_room_config.get('is_active_listening'):
        if not message_body: return
        text_for_ai_processing = message_body
        current_room_config['last_message_timestamp'] = now
        current_room_config['current_interval'] = POLLING_INITIAL_INTERVAL
        current_room_config['max_interval_no_activity_cycles'] = 0
        print(f"[{room_id}] Active listening: Activity processed. Interval reset to {POLLING_INITIAL_INTERVAL}s.")
    else:
        return

    if text_for_ai_processing:
        if not current_room_config:
             print(f"[{room_id}] Error: current_room_config not found before AI call. This shouldn't happen.")
             return

        room_memory_store: List[Dict[str, str]] = current_room_config['memory']
        
        # sender_display_name is already fetched at the beginning of the callback
        # This is the name used in the AI prompt for the current user.
        user_name_for_ai_input = sender_display_name

        messages_payload = prompt_constructor.build_messages_for_ai(
            historical_messages=list(room_memory_store),
            current_user_input=text_for_ai_processing,
            user_name_for_input=user_name_for_ai_input, # Use the fetched display name
            bot_display_name=BOT_DISPLAY_NAME
        )
        
        print(f"[{room_id}] Preparing to call AI. History length: {len(room_memory_store)}, Current input by '{user_name_for_ai_input}': '{text_for_ai_processing[:50]}...'")

        ai_response_text = get_openrouter_response(messages_payload)
        await send_matrix_message(client, room_id, ai_response_text)

        user_message_to_store = {
            "role": "user",
            "name": user_name_for_ai_input, # Store with display name
            "content": text_for_ai_processing
        }
        room_memory_store.append(user_message_to_store)
        
        is_error_response = "Sorry, I couldn't" in ai_response_text or \
                            "not configured" in ai_response_text or \
                            "issue connecting" in ai_response_text
        if ai_response_text and not is_error_response:
            ai_response_to_store = {
                "role": "assistant",
                "name": BOT_DISPLAY_NAME, 
                "content": ai_response_text
            }
            room_memory_store.append(ai_response_to_store)
        
        while len(room_memory_store) > MAX_MESSAGES_PER_ROOM_MEMORY:
            room_memory_store.pop(0)
        print(f"[{room_id}] Updated memory. New size: {len(room_memory_store)}")


async def main_matrix():
    global BOT_DISPLAY_NAME, room_activity_config

    if not all([MATRIX_HOMESERVER, MATRIX_USER_ID, MATRIX_PASSWORD]):
        print("CRITICAL: MATRIX_HOMESERVER, MATRIX_USER_ID, or MATRIX_PASSWORD not set. Exiting.")
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
        print(f"Login failed with exception: {e}"); return
    print(f"Logged in successfully as {client.user_id} (device ID: {client.device_id})")

    try:
        profile: ProfileGetResponse = await client.get_profile(client.user_id)
        fetched_displayname = profile.displayname
        if fetched_displayname:
            BOT_DISPLAY_NAME = fetched_displayname
        else:
            localpart = client.user_id.split(':')[0]
            BOT_DISPLAY_NAME = localpart[1:] if localpart.startswith("@") else localpart
        print(f"Bot's display name set to: '{BOT_DISPLAY_NAME}'")
    except Exception as e:
        print(f"Could not fetch bot's display name, using fallback '{BOT_DISPLAY_NAME}'. Error: {e}")

    if MATRIX_ROOM_ID and "YOUR_MATRIX_ROOM_ID" not in MATRIX_ROOM_ID:
        print(f"Attempting to join predefined room: {MATRIX_ROOM_ID}...")
        try:
            join_response = await client.join(MATRIX_ROOM_ID)
            if hasattr(join_response, 'room_id') and join_response.room_id:
                print(f"Successfully joined room: {MATRIX_ROOM_ID}")
            else:
                print(f"Failed to join room {MATRIX_ROOM_ID}: {join_response}")
        except Exception as e:
            print(f"Error joining room {MATRIX_ROOM_ID}: {e}")

    print("Bot is running. Listening for messages and invitations...")
    try:
        await client.sync_forever(timeout=30000, full_state=True)
    except Exception as e: # Catch specific exceptions if needed, e.g. nio.exceptions.TransportError
        print(f"Error during sync_forever: {type(e).__name__} - {e}")
    finally:
        print("Shutting down. Cancelling active room decay tasks...")
        active_decay_tasks = [
            cfg['decay_task'] for cfg in room_activity_config.values()
            if cfg.get('decay_task') and not cfg['decay_task'].done()
        ]
        for task in active_decay_tasks: task.cancel()
        
        if active_decay_tasks:
            done, pending = await asyncio.wait(active_decay_tasks, timeout=5.0, return_when=asyncio.ALL_COMPLETED)
            for task in pending: print(f"Warning: Task {task.get_name()} did not complete cancellation in time.")
            for task in done:
                if task.cancelled(): print(f"Task {task.get_name()} successfully cancelled.")
                elif task.exception(): print(f"Task {task.get_name()} raised an exception during shutdown: {task.exception()}")
        
        print("Closing Matrix client..."); await client.close()
        print("Matrix client closed. Bot shutdown complete.")


if __name__ == "__main__":
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