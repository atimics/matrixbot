import asyncio
import os
from typing import Optional
from nio import (
    AsyncClient,
    MatrixRoom,
    RoomMessageText,
    LoginResponse,
    ProfileGetResponse
)
from nio.exceptions import LocalProtocolError # Import specific known nio exceptions
from dotenv import load_dotenv, set_key, find_dotenv # Modified import
import markdown

from message_bus import MessageBus
from event_definitions import (
    MatrixMessageReceivedEvent,
    SendMatrixMessageCommand,
    BotDisplayNameReadyEvent,
    SetTypingIndicatorCommand,
    SetPresenceCommand
)

load_dotenv() # To get MATRIX_ configs

class MatrixGatewayService:
    def __init__(self, message_bus: MessageBus):
        self.bus = message_bus
        self.homeserver = os.getenv("MATRIX_HOMESERVER")
        self.user_id = os.getenv("MATRIX_USER_ID") # Will be updated by .env or after login
        self.password = os.getenv("MATRIX_PASSWORD")
        self.access_token: Optional[str] = os.getenv("MATRIX_ACCESS_TOKEN")
        # User's preferred device name for new logins, or if no MATRIX_DEVICE_ID is stored
        self.device_name_config = os.getenv("DEVICE_NAME", "NioChatBotSOA_Gateway_v2")
        # Device ID from a previous successful login, associated with the access_token
        self.persisted_device_id: Optional[str] = os.getenv("MATRIX_DEVICE_ID")
        self.client: Optional[AsyncClient] = None
        self.bot_display_name: Optional[str] = "ChatBot" # Default
        self._stop_event = asyncio.Event()

    async def _matrix_message_callback(self, room: MatrixRoom, event: RoomMessageText):
        if not self.client or event.sender == self.client.user_id:
            return

        sender_display_name = room.user_name(event.sender) or event.sender

        msg_event = MatrixMessageReceivedEvent(
            room_id=room.room_id,
            event_id=event.event_id,
            sender_id=event.sender,
            sender_display_name=sender_display_name,
            body=event.body.strip(),
            room_display_name=room.display_name
        )
        await self.bus.publish(msg_event)

    async def _handle_send_message_command(self, command: SendMatrixMessageCommand):
        if self.client:
            plain_text_body = command.text

            try:
                html_body = markdown.markdown(plain_text_body, extensions=['nl2br', 'fenced_code', 'codehilite'])
                content = {
                    "msgtype": "m.text",
                    "body": plain_text_body,
                    "format": "org.matrix.custom.html",
                    "formatted_body": html_body
                }
            except Exception as e:
                print(f"Gateway: Markdown conversion failed, sending plain text. Error: {e}")
                content = {
                    "msgtype": "m.text",
                    "body": plain_text_body
                }

            try:
                await self.client.room_send(
                    room_id=command.room_id,
                    message_type="m.room.message",
                    content=content
                )
            except (LocalProtocolError) as e:
                print(f"Gateway: Specific nio error sending message to {command.room_id}: {type(e).__name__} - {e}")
            except Exception as e:
                print(f"Gateway: General error sending message to {command.room_id}: {type(e).__name__} - {e}")
        else:
            print("Gateway: Cannot send message, client not initialized.")

    async def _handle_set_typing_command(self, command: SetTypingIndicatorCommand):
        if self.client and self.client.logged_in:
            try:
                # Use nio's built-in method
                await self.client.room_typing(
                    room_id=command.room_id,
                    typing_state=command.typing,
                    timeout=command.timeout # Pass timeout from command
                )
                # print(f"Gateway: Typing indicator set to {command.typing} in {command.room_id}")
            except LocalProtocolError as e:
                print(f"Gateway: Failed to set typing indicator in {command.room_id} (Nio Error): {e}")
            except Exception as e:
                print(f"Gateway: Failed to set typing indicator in {command.room_id} (Error): {e}")
        else:
            print(f"Gateway: Cannot set typing indicator in {command.room_id}, client not ready or not logged in.")

    async def _handle_set_presence_command(self, command: SetPresenceCommand):
        if self.client and self.client.logged_in:
            try:
                await self.client.set_presence(
                    presence=command.presence,
                    status_msg=command.status_msg,
                    # timeout=command.timeout # This was the original line, nio uses status_msg not status_message
                )
                print(f"Gateway: Presence set to {command.presence} with message '{command.status_msg}'")
            except LocalProtocolError as e:
                print(f"Gateway: Failed to set presence (Nio Error): {e}")
            except Exception as e:
                print(f"Gateway: Failed to set presence (Error): {e}")
        else:
            print("Gateway: Cannot set presence, client not ready or not logged in.")


    async def run(self):
        print("MatrixGatewayService: Starting...")
        if not self.homeserver or not self.user_id: # self.user_id here is from initial .env or None
             print("Gateway: MATRIX_HOMESERVER and MATRIX_USER_ID must be set. Exiting.")
             return
        if not self.password and not self.access_token: # self.access_token here is from initial .env or None
            print("Gateway: Either MATRIX_PASSWORD or MATRIX_ACCESS_TOKEN must be set. Exiting.")
            return

        # Determine the device_id to use for AsyncClient constructor
        # This device_id is primarily for when a token is provided.
        client_constructor_device_id = self.persisted_device_id or self.device_name_config

        if self.access_token:
             # If using token, user_id and device_id should ideally be the ones from the session that generated the token
             # self.user_id is already loaded from MATRIX_USER_ID (potentially canonicalized and saved from previous run)
             # client_constructor_device_id uses self.persisted_device_id (saved from previous run)
             print(f"Gateway: Initializing client with User ID {self.user_id}, Access Token, and Device ID {client_constructor_device_id}.")
             self.client = AsyncClient(
                 self.homeserver,
                 self.user_id,
                 device_id=client_constructor_device_id,
                 # token=self.access_token, # Removed: token is not a valid constructor argument
                 store_path=None
             )
             self.client.access_token = self.access_token # Set token after initialization
        else:
             print(f"Gateway: Initializing client with User ID {self.user_id} for password login.")
             # For password login, device_id in constructor is a default.
             # The actual device_id will be set by the server after login.
             # The device_name for the login call itself is self.device_name_config.
             self.client = AsyncClient(
                 self.homeserver,
                 self.user_id, # Initial user_id from env
                 device_id=self.device_name_config, # Provide configured name as default for client object
                 store_path=None
             )

        self.client.add_event_callback(self._matrix_message_callback, RoomMessageText)
        # Subscribe to commands
        self.bus.subscribe(SendMatrixMessageCommand.model_fields['event_type'].default, self._handle_send_message_command)
        self.bus.subscribe(SetTypingIndicatorCommand.model_fields['event_type'].default, self._handle_set_typing_command)
        self.bus.subscribe(SetPresenceCommand.model_fields['event_type'].default, self._handle_set_presence_command)

        login_success = False
        try:
            if not self.client.access_token: # Only login if we don't already have a token (i.e. self.access_token was None)
                print(f"Gateway: Attempting password login as {self.user_id}...")
                # Use self.device_name_config for the login attempt
                login_response = await self.client.login(self.password, device_name=self.device_name_config)

                if isinstance(login_response, LoginResponse):
                    login_success = True
                    # IMPORTANT: Update with values from the server
                    self.access_token = self.client.access_token
                    self.user_id = self.client.user_id # Canonicalized user ID from server
                    actual_device_id = self.client.device_id # Actual device ID from server

                    print(f"Gateway: Logged in successfully as {self.user_id} with device ID {actual_device_id}")
                    print(f"Gateway: Saving access token, user ID, and device ID to .env file...")
                    try:
                        dotenv_path_found = find_dotenv(usecwd=True, raise_error_if_not_found=False)
                        env_file_to_write = dotenv_path_found
                        if not env_file_to_write: # If .env doesn't exist or not found in CWD/parents
                            env_file_to_write = os.path.join(os.getcwd(), ".env")
                            # Create .env if it doesn't exist, so set_key can write to it
                            if not os.path.exists(env_file_to_write):
                                with open(env_file_to_write, "w") as f:
                                    pass # Create empty .env
                                print(f"Gateway: Created .env file at {env_file_to_write}")
                        
                        set_key(env_file_to_write, "MATRIX_ACCESS_TOKEN", self.access_token)
                        set_key(env_file_to_write, "MATRIX_USER_ID", self.user_id)
                        set_key(env_file_to_write, "MATRIX_DEVICE_ID", actual_device_id)
                        print(f"Gateway: Credentials saved to {env_file_to_write}.")

                        # Update current environment variables for this running instance
                        # and internal state, so it doesn't rely on a restart to use them.
                        os.environ['MATRIX_ACCESS_TOKEN'] = self.access_token
                        os.environ['MATRIX_USER_ID'] = self.user_id
                        os.environ['MATRIX_DEVICE_ID'] = actual_device_id
                        self.persisted_device_id = actual_device_id # Update internal state

                    except Exception as e:
                        print(f"Gateway: Failed to save credentials to .env file. Error: {type(e).__name__} - {e}")
                else:
                    print(f"Gateway: Login failed. Response: {login_response}")
                    await self.client.close()
                    return
            else:
                print("Gateway: Using provided access token. Verifying token...")
                # Optionally verify token with a simple API call like /account/whoami
                try:
                   whoami_response = await self.client.whoami()
                   if whoami_response.user_id == self.user_id:
                       print("Gateway: Access token is valid.")
                       login_success = True # Treat as successful login
                   else:
                       print(f"Gateway: Access token seems invalid or for wrong user ({whoami_response.user_id} != {self.user_id}).")
                       await self.client.close()
                       return
                except Exception as e:
                    print(f"Gateway: Failed to verify access token. Error: {e}")
                    await self.client.close()
                    return


            # --- Fetch display name (remains the same) ---
            try:
                profile: ProfileGetResponse = await self.client.get_profile(self.client.user_id)
                fetched_displayname = profile.displayname
                if fetched_displayname: self.bot_display_name = fetched_displayname
                else:
                    localpart = self.client.user_id.split(':')[0]
                    self.bot_display_name = localpart[1:] if localpart.startswith("@") else localpart
                print(f"Gateway: Bot display name set to '{self.bot_display_name}'")
                await self.bus.publish(BotDisplayNameReadyEvent(display_name=self.bot_display_name))
            except Exception as e:
                print(f"Gateway: Could not fetch bot's display name, using default '{self.bot_display_name}'. Error: {type(e).__name__} - {e}")
                await self.bus.publish(BotDisplayNameReadyEvent(display_name=self.bot_display_name)) # Publish default


            # --- Join room (remains the same) ---
            matrix_room_id_env = os.getenv("MATRIX_ROOM_ID")
            if matrix_room_id_env and "YOUR_MATRIX_ROOM_ID" not in matrix_room_id_env:
                print(f"Gateway: Attempting to join predefined room: {matrix_room_id_env}...")
                try:
                    join_response = await self.client.join(matrix_room_id_env)
                    if hasattr(join_response, 'room_id'):
                         print(f"Gateway: Successfully joined room: {join_response.room_id}")
                    else:
                         print(f"Gateway: Failed to join room {matrix_room_id_env}. Response: {join_response}")
                except (LocalProtocolError) as e:
                    # Handle 'already joined' specifically if needed
                    if "already in room" in str(e).lower():
                         print(f"Gateway: Already in room {matrix_room_id_env}.")
                    else:
                         print(f"Gateway: Specific nio error joining room {matrix_room_id_env}: {type(e).__name__} - {e}")
                except Exception as e:
                    print(f"Gateway: General error joining room {matrix_room_id_env}: {type(e).__name__} - {e}")


            try:
                # Set an initial presence, e.g., online or unavailable
                initial_presence = "unavailable" # Or "unavailable" if you want it to start idle
                initial_status_msg = "Initializing..." # Optional
                await self.client.set_presence(presence=initial_presence, status_msg=initial_status_msg)
                print(f"Gateway: Initial presence set to {initial_presence}")
            except Exception as e:
                print(f"Gateway: Failed to set initial presence: {e}")

            # --- Sync loop (remains the same) ---
            print("Gateway: Starting sync loop...")
            sync_task = asyncio.create_task(self.client.sync_forever(timeout=30000, full_state=True))
            stop_event_task = asyncio.create_task(self._stop_event.wait())

            done, pending = await asyncio.wait([sync_task, stop_event_task], return_when=asyncio.FIRST_COMPLETED)

            if stop_event_task in done:
                print("Gateway: Stop event received, cancelling sync task.")
                if not sync_task.done(): sync_task.cancel()
            elif sync_task in done:
                print("Gateway: Sync task finished unexpectedly.")
                try: sync_task.result()
                except asyncio.CancelledError: print("Gateway: Sync task was cancelled.")
                except (LocalProtocolError) as e: print(f"Gateway: Sync task failed (Matrix Sync error): {type(e).__name__} - {e}")
                except Exception as e: print(f"Gateway: Sync task failed (general error): {type(e).__name__} - {e}")

            if sync_task.cancelled() or (pending and sync_task in pending and not sync_task.done()):
                try: await sync_task
                except asyncio.CancelledError: print("Gateway: Sync task successfully processed cancellation.")
                except Exception as e: print(f"Gateway: Exception awaiting cancelled sync_task: {type(e).__name__} - {e}")


        except (LocalProtocolError) as e:
            print(f"Gateway: Matrix Sync error during initial setup: {type(e).__name__} - {e}")
        except ConnectionError as e:
            print(f"Gateway: ConnectionError during initial setup: {type(e).__name__} - {e}")
        except Exception as e:
            print(f"Gateway: Unexpected error in MatrixGatewayService run (setup): {type(e).__name__} - {e}")
        finally:
            if self.client:
                if login_success and not self.client.logged_in and not self._stop_event.is_set():
                     print("Gateway: Client is no longer logged in.")
                print("Gateway: Closing Matrix client...")
                await self.client.close()
            print("MatrixGatewayService: Stopped.")

    async def stop(self):
        print("MatrixGatewayService: Stop requested.")
        self._stop_event.set()