import asyncio
import json
import http.client
import os
import time
from dotenv import load_dotenv
from typing import Optional, Dict, Any

from nio import (
    AsyncClient,
    MatrixRoom,
    RoomMessageText,
    LoginResponse,
    RoomSendResponse,
    ProfileGetResponse,
)

# --- Configuration ---
load_dotenv()

# Matrix Configuration
MATRIX_HOMESERVER = os.getenv("MATRIX_HOMESERVER")
MATRIX_USER_ID = os.getenv("MATRIX_USER_ID")
MATRIX_PASSWORD = os.getenv("MATRIX_PASSWORD")
MATRIX_ROOM_ID = os.getenv("MATRIX_ROOM_ID")  # Optional: specific room to join on startup
DEVICE_NAME = os.getenv("DEVICE_NAME", "NioChatBotPolling")

# OpenRouter Configuration
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
# These are recommended by OpenRouter for request routing and identification.
YOUR_SITE_URL = os.getenv("YOUR_SITE_URL", "https://your-matrix-bot.example.com")
YOUR_SITE_NAME = os.getenv("YOUR_SITE_NAME", "MyMatrixBot")

# Active Listening / Decay Configuration
# This system doesn't "poll" for messages in the traditional sense of repeatedly fetching.
# Instead, it relies on `client.sync_forever()` to receive all messages.
# The "polling" or "decay" mechanism here refers to how long the bot remains in an
# "active listening" state (responding to non-mention messages) in a room after being addressed.
POLLING_INITIAL_INTERVAL = int(os.getenv("POLLING_INITIAL_INTERVAL", "10"))  # seconds to wait before first check for inactivity
POLLING_MAX_INTERVAL = int(os.getenv("POLLING_MAX_INTERVAL", "120"))      # max seconds to wait between inactivity checks
POLLING_INACTIVITY_DECAY_CYCLES = int(
    os.getenv("POLLING_INACTIVITY_DECAY_CYCLES", "3")
)  # Num cycles at max_interval with no activity before deactivating listening

# --- Global State ---
BOT_DISPLAY_NAME: Optional[str] = None

# room_activity_config stores state for rooms where the bot is actively listening or decaying.
# Structure:
# {
#   room_id: {
#     'is_active_listening': bool,  # True if bot should respond to non-mentions in this room
#     'current_interval': int,      # Current interval for the decay task's sleep/check cycle
#     'last_message_timestamp': float, # Timestamp of the last relevant message (mention or during active listening)
#     'decay_task': asyncio.Task,   # The asyncio.Task managing the activity decay for this room
#     'max_interval_no_activity_cycles': int # Counter for consecutive checks at max_interval with no activity
#   }
# }
room_activity_config: Dict[str, Dict[str, Any]] = {}


# --- Utility Functions ---
async def send_matrix_message(
    client: AsyncClient, room_id: str, text: str
) -> Optional[RoomSendResponse]:
    """Helper function to send a text message to a Matrix room."""
    if not text:
        print(f"[{room_id}] Attempted to send an empty message. Skipping.")
        return None
    try:
        print(f"[{room_id}] Sending message: \"{text[:70]}...\"")
        return await client.room_send(
            room_id=room_id,
            message_type="m.room.message",
            content={"msgtype": "m.text", "body": text},
        )
    except Exception as e:
        print(f"Error sending message to {room_id}: {e}")
        return None


# --- OpenRouter API Call ---
def get_openrouter_response(prompt_text: str) -> str:
    """
    Gets a response from the OpenRouter API for the given prompt.
    """
    if not OPENROUTER_API_KEY or "YOUR_OPENROUTER_API_KEY" in OPENROUTER_API_KEY:
        print("OpenRouter API key not configured. Skipping API call.")
        return "Sorry, my AI connection is not configured."

    conn = http.client.HTTPSConnection("openrouter.ai")
    payload = json.dumps(
        {"model": OPENROUTER_MODEL, "messages": [{"role": "user", "content": prompt_text}]}
    )
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": YOUR_SITE_URL,
        "X-Title": YOUR_SITE_NAME,
    }
    try:
        conn.request("POST", "/api/v1/chat/completions", payload, headers)
        res = conn.getresponse()
        data = res.read()
        response_json = json.loads(data.decode("utf-8"))

        if res.status == 200 and response_json.get("choices"):
            return response_json["choices"][0]["message"]["content"]
        else:
            error_message = response_json.get("error", {}).get(
                "message", "Unknown error"
            )
            print(
                f"Error from OpenRouter: {res.status} - {error_message} - Response: {response_json}"
            )
            return "Sorry, I couldn't get a response from the AI."
    except Exception as e:
        print(f"Error connecting to OpenRouter: {e}")
        return "Sorry, there was an issue connecting to the AI service."
    finally:
        conn.close()


# --- Matrix Bot Logic: Active Listening and Decay Management ---

async def manage_room_activity_decay(room_id: str, client: AsyncClient):
    """
    Manages the "active listening" state for a room.
    This task runs periodically for a room after the bot has been addressed.
    It checks for inactivity and gradually increases its check interval.
    If the room remains inactive for too long, it deactivates "active listening".
    """
    # Initial current_interval is set when this task is created.
    initial_interval = room_activity_config.get(room_id, {}).get('current_interval', POLLING_INITIAL_INTERVAL)
    print(f"[{room_id}] Starting activity decay manager. Initial check interval: {initial_interval}s")
    try:
        while True:
            # Critical: Check if we should still be running *before* sleeping.
            # The config might have been removed or listening deactivated by message_callback.
            current_config = room_activity_config.get(room_id)
            if not current_config or not current_config.get('is_active_listening', False):
                print(f"[{room_id}] Decay manager: No longer active listening or config removed. Exiting task.")
                break

            sleep_duration = current_config['current_interval']
            print(f"[{room_id}] Decay manager: Sleeping for {sleep_duration}s. (Last activity: {time.ctime(current_config['last_message_timestamp'])})")
            await asyncio.sleep(sleep_duration)

            # Re-fetch config after sleep, as message_callback might have updated it.
            # This is crucial to react to new activity that happened during our sleep.
            current_config = room_activity_config.get(room_id)
            if not current_config or not current_config.get('is_active_listening', False):
                print(f"[{room_id}] Decay manager: No longer active listening or config removed after sleep. Exiting task.")
                break

            now = time.time()
            time_since_last_activity = now - current_config['last_message_timestamp']

            # If (time since last activity) is greater than or equal to the interval we just slept for,
            # it implies no relevant messages (that would reset last_message_timestamp) arrived during our sleep.
            if time_since_last_activity >= current_config['current_interval']:
                # No activity during the last interval. Increase the interval for the next check.
                new_interval = min(current_config['current_interval'] * 2, POLLING_MAX_INTERVAL)
                print(f"[{room_id}] Decay: No detected activity for >= {current_config['current_interval']}s. New check interval: {new_interval}s.")
                current_config['current_interval'] = new_interval

                if current_config['current_interval'] == POLLING_MAX_INTERVAL:
                    current_config['max_interval_no_activity_cycles'] += 1
                else:
                    # Reset counter if interval is not max, or if it just became max.
                    current_config['max_interval_no_activity_cycles'] = 0

                if current_config['max_interval_no_activity_cycles'] >= POLLING_INACTIVITY_DECAY_CYCLES:
                    current_config['is_active_listening'] = False
                    print(f"[{room_id}] Decay: Deactivating listening due to prolonged inactivity "
                          f"({POLLING_MAX_INTERVAL}s x {POLLING_INACTIVITY_DECAY_CYCLES} cycles).")
                    await send_matrix_message(
                        client,
                        room_id,
                        f"Stopping active listening in this room due to inactivity. "
                        f"Mention me (@{BOT_DISPLAY_NAME}) or use !bot to re-activate."
                    )
                    # Loop will break at the start of the next iteration due to 'is_active_listening' becoming False.
            else:
                # Activity occurred (last_message_timestamp was updated by message_callback),
                # or the interval was reset to initial by message_callback.
                # The current_config['current_interval'] should reflect POLLING_INITIAL_INTERVAL
                # if message_callback reset it.
                print(f"[{room_id}] Decay: Activity detected or interval recently reset by new message. "
                      f"Continuing with current check interval: {current_config['current_interval']}s.")
                current_config['max_interval_no_activity_cycles'] = 0  # Reset counter due to activity

    except asyncio.CancelledError:
        print(f"[{room_id}] Activity decay manager task was cancelled.")
    except Exception as e:
        print(f"[{room_id}] Error in activity decay manager: {e}")
    finally:
        print(f"[{room_id}] Activity decay manager task finished.")
        # Note: If the task exits due to deactivation or cancellation,
        # message_callback is responsible for potentially restarting it if a new mention occurs.


async def message_callback(room: MatrixRoom, event: RoomMessageText, client: AsyncClient) -> None:
    global room_activity_config, BOT_DISPLAY_NAME # BOT_DISPLAY_NAME is read-only here after init

    if event.sender == client.user_id:
        return  # Ignore messages from the bot itself

    now = time.time()
    room_id = room.room_id
    message_body = event.body.strip()

    print(f"Message received in room '{room.display_name}' ({room_id}) from {event.sender}: \"{message_body[:100]}{'...' if len(message_body) > 100 else ''}\"")

    # Fetch current configuration for this room, if any
    current_room_config = room_activity_config.get(room_id)

    # Determine if the bot was mentioned or a command was used
    is_command = message_body.lower().startswith("!bot")
    bot_name_lower = BOT_DISPLAY_NAME.lower() if BOT_DISPLAY_NAME else "" # Ensure BOT_DISPLAY_NAME is available
    is_mention = bool(BOT_DISPLAY_NAME and bot_name_lower in message_body.lower())


    if is_command or is_mention:
        ai_prompt_text = ""
        perform_ai_call = True  # Flag to determine if we should call OpenRouter

        if is_command:
            ai_prompt_text = message_body[len("!bot"):].strip()
            if not ai_prompt_text:
                await send_matrix_message(client, room_id, "You used !bot without a question. How can I assist?")
                perform_ai_call = False
        elif is_mention:  # This implies not a command (checked first)
            ai_prompt_text = message_body # Use the whole message body for mentions for LLM context
            # Check if the message is effectively just the bot's name (with potential punctuation/whitespace)
            # This helps provide a more specific response to a bare mention.
            temp_prompt = message_body.lower().replace(f"@{bot_name_lower}", "").replace(bot_name_lower, "").strip("@!.,? ")
            if not temp_prompt: # If nothing substantial is left after removing bot name
                await send_matrix_message(client, room_id, f"Hi {event.sender}! You mentioned me. How can I help? (Use !bot <your question> or just ask directly after mentioning me).")
                perform_ai_call = False

        if perform_ai_call and ai_prompt_text:
            print(f"[{room_id}] Mention/Command processing, sending to AI: '{ai_prompt_text}'")
            response_text = get_openrouter_response(ai_prompt_text)
            await send_matrix_message(client, room_id, response_text)

        # --- Activate/Reset Active Listening Logic ---
        was_previously_inactive_or_no_config = not current_room_config or not current_room_config.get('is_active_listening', False)

        # If there's an existing decay task for this room, cancel it before starting a new one.
        if current_room_config and current_room_config.get('decay_task'):
            old_task = current_room_config['decay_task']
            if not old_task.done():
                print(f"[{room_id}] Cancelling existing decay task due to new mention/command.")
                old_task.cancel()
                try:
                    # Give the old task a moment to process cancellation and clean up.
                    await asyncio.wait_for(old_task, timeout=2.0)
                except asyncio.CancelledError:
                    print(f"[{room_id}] Old decay task successfully cancelled.")
                except asyncio.TimeoutError:
                    print(f"[{room_id}] Timeout waiting for old decay task to self-cancel. It might already be finishing.")
                except Exception as e: # Catch other potential errors during await
                    print(f"[{room_id}] Error encountered while awaiting old cancelled task: {e}")

        # Create/update the room's activity configuration and start a new decay manager task.
        room_activity_config[room_id] = {
            'is_active_listening': True,
            'current_interval': POLLING_INITIAL_INTERVAL, # Reset interval to initial
            'last_message_timestamp': now,               # Update last activity time to this message
            'max_interval_no_activity_cycles': 0,        # Reset decay cycles counter
            'decay_task': asyncio.create_task(manage_room_activity_decay(room_id, client))
        }
        print(f"[{room_id}] Activated/Reset active listening. New check interval: {POLLING_INITIAL_INTERVAL}s.")

        # Notify user if listening was just activated, but only if we didn't already send a "bare mention" response
        if was_previously_inactive_or_no_config:
            if perform_ai_call and ai_prompt_text: # i.e. an actual question was asked and AI responded
                 await send_matrix_message(client, room_id, "Okay, I'm now paying closer attention to this room and will respond to messages for a while.")
            # If not perform_ai_call (e.g. bare mention), a specific message was already sent, so no need for this generic one.

    elif current_room_config and current_room_config.get('is_active_listening'):
        # Bot is in "active listening" mode for this room, and this message is not a direct command/mention.
        if not message_body:  # Ignore empty messages if any slip through
            return

        print(f"[{room_id}] Active listening: processing non-mention message '{message_body}' from {event.sender}")
        response_text = get_openrouter_response(message_body)
        await send_matrix_message(client, room_id, response_text)

        # Update activity state for this room as it's still active
        current_room_config['last_message_timestamp'] = now
        current_room_config['current_interval'] = POLLING_INITIAL_INTERVAL # Reset check interval due to activity
        current_room_config['max_interval_no_activity_cycles'] = 0      # Reset decay cycles counter
        print(f"[{room_id}] Active listening: Activity processed. Check interval reset to {POLLING_INITIAL_INTERVAL}s.")
    else:
        # General room message, bot not mentioned and not actively listening in this room. Ignore.
        print(f"[{room_id}] Ignoring message from {event.sender} as bot is not mentioned and not actively listening in this room.")
        pass # Explicitly do nothing


async def main_matrix():
    global BOT_DISPLAY_NAME, room_activity_config # Allow modification of globals

    # --- Client Setup ---
    if not all([MATRIX_HOMESERVER, MATRIX_USER_ID, MATRIX_PASSWORD]):
        print("Error: MATRIX_HOMESERVER, MATRIX_USER_ID, or MATRIX_PASSWORD not set. Exiting.")
        return
    
    client = AsyncClient(MATRIX_HOMESERVER, MATRIX_USER_ID)
    client.add_event_callback(
        # Use a lambda to pass the client instance to the callback
        lambda room, event: message_callback(room, event, client),
        RoomMessageText
    )

    # --- Login ---
    print(f"Attempting to log in as {MATRIX_USER_ID} on {MATRIX_HOMESERVER}...")
    try:
        login_response = await client.login(MATRIX_PASSWORD, device_name=DEVICE_NAME)
        if not isinstance(login_response, LoginResponse):
            print(f"Failed to log in: {login_response}")
            return
    except Exception as e:
        print(f"Login failed with exception: {e}")
        return
    print(f"Logged in successfully as {client.user_id} (device ID: {client.device_id})")

    # --- Fetch Bot's Display Name ---
    # This is important for reliable mention detection.
    try:
        profile: ProfileGetResponse = await client.get_profile(client.user_id)
        BOT_DISPLAY_NAME = profile.displayname
        if not BOT_DISPLAY_NAME: # If display name is not set
            # Fallback to user ID's localpart (e.g., 'mybot' from '@mybot:matrix.org')
            localpart = client.user_id.split(':')[0]
            if localpart.startswith("@"):
                BOT_DISPLAY_NAME = localpart[1:]
            else: # Should not happen for valid Matrix user IDs but defensive
                BOT_DISPLAY_NAME = localpart 
        print(f"Bot's display name set to: '{BOT_DISPLAY_NAME}'")
        if not BOT_DISPLAY_NAME: # If still no name (e.g., localpart was empty or just "@")
            print("Warning: Bot display name could not be reliably determined. Mention detection might be impaired. Falling back to full user ID.")
            BOT_DISPLAY_NAME = client.user_id # Last resort
    except Exception as e:
        print(f"Could not fetch bot's display name. Mention detection will use a fallback. Error: {e}")
        # Simplified fallback if get_profile fails entirely
        localpart = client.user_id.split(':')[0][1:] if client.user_id.startswith('@') and ':' in client.user_id else client.user_id
        BOT_DISPLAY_NAME = localpart if localpart else client.user_id


    # --- Join Predefined Room (Optional) ---
    if MATRIX_ROOM_ID and "YOUR_MATRIX_ROOM_ID" not in MATRIX_ROOM_ID: # Check if it's a real ID
        print(f"Attempting to join predefined room: {MATRIX_ROOM_ID}...")
        try:
            join_response = await client.join(MATRIX_ROOM_ID)
            if hasattr(join_response, 'room_id') and join_response.room_id:
                print(f"Successfully joined room: {MATRIX_ROOM_ID}")
            else:
                print(f"Failed to join room {MATRIX_ROOM_ID}: {join_response}")
        except Exception as e:
            print(f"Error joining room {MATRIX_ROOM_ID}: {e}")
            # Bot will continue running and can be invited to rooms manually.

    # --- Main Event Loop ---
    print("Bot is running. Listening for messages and invitations...")
    try:
        # full_state=True ensures the bot gets current room state on initial sync.
        # timeout specifies how long to wait for an event before cycling (useful for graceful shutdown checks too)
        await client.sync_forever(timeout=30000, full_state=True)
    except Exception as e:
        print(f"Error during sync_forever: {e}")
    finally:
        print("Shutting down. Cancelling active room decay tasks...")
        active_decay_tasks = []
        for r_id, cfg in list(room_activity_config.items()): # Iterate over a copy of items for safe modification
            if cfg.get('decay_task') and not cfg['decay_task'].done():
                print(f"[{r_id}] Requesting cancellation of decay task for shutdown.")
                cfg['decay_task'].cancel()
                active_decay_tasks.append(cfg['decay_task'])
        
        if active_decay_tasks:
            # Wait for tasks to actually cancel, with a timeout
            done, pending = await asyncio.wait(active_decay_tasks, timeout=5.0, return_when=asyncio.ALL_COMPLETED)
            for task in pending:
                # This should ideally not happen if tasks handle CancelledError promptly.
                print(f"Warning: Task {task.get_name()} did not complete cancellation in time during shutdown.")
            for task in done:
                if task.cancelled():
                    print(f"Task {task.get_name()} successfully cancelled for shutdown.")
                elif task.exception():
                    print(f"Task {task.get_name()} raised an exception during shutdown/cancellation: {task.exception()}")
        
        print("Closing Matrix client...")
        await client.close()
        print("Matrix client closed. Bot shutdown complete.")


if __name__ == "__main__":
    # Basic credential and configuration check
    essential_configs = {
        "MATRIX_HOMESERVER": MATRIX_HOMESERVER,
        "MATRIX_USER_ID": MATRIX_USER_ID,
        "MATRIX_PASSWORD": MATRIX_PASSWORD,
    }
    missing_essentials = False
    for key, val in essential_configs.items():
        if not val or f"YOUR_{key}" in str(val) or "placeholder" in str(val).lower():
            print(f"CRITICAL: Missing or placeholder value for essential config: {key}. Please set it in your .env file or environment.")
            missing_essentials = True
    
    if missing_essentials:
        print("Exiting due to missing essential Matrix configurations.")
    else:
        if not OPENROUTER_API_KEY or "YOUR_OPENROUTER_API_KEY" in OPENROUTER_API_KEY:
            print("Warning: OPENROUTER_API_KEY is not set or is a placeholder. AI responses will be disabled (bot will state connection is not configured).")
        
        if "your-site-url.com" in YOUR_SITE_URL or "My Chatbot" in YOUR_SITE_NAME :
            print(f"Note: YOUR_SITE_URL ('{YOUR_SITE_URL}') and YOUR_SITE_NAME ('{YOUR_SITE_NAME}') are using default/placeholder values. "
                  "These are recommended by OpenRouter but not critical for basic operation.")

        try:
            asyncio.run(main_matrix())
        except KeyboardInterrupt:
            print("Bot stopped by user (KeyboardInterrupt).")
        except Exception as e:
            # This catches errors that might occur outside the main_matrix asyncio loop (e.g., during setup)
            print(f"An unexpected error occurred in the main execution block: {e}")