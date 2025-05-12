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
from dotenv import load_dotenv
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
        self.user_id = os.getenv("MATRIX_USER_ID")
        self.password = os.getenv("MATRIX_PASSWORD")
        # --- Store access token if using password login ---
        self.access_token: Optional[str] = os.getenv("MATRIX_ACCESS_TOKEN") # Allow direct token too
        self.device_name = os.getenv("DEVICE_NAME", "NioChatBotSOA_Gateway_v2")
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
                    status_message=command.status_message,
                    timeout=command.timeout
                )
                print(f"Gateway: Presence set to {command.presence} with message '{command.status_message}'")
            except LocalProtocolError as e:
                print(f"Gateway: Failed to set presence (Nio Error): {e}")
            except Exception as e:
                print(f"Gateway: Failed to set presence (Error): {e}")
        else:
            print("Gateway: Cannot set presence, client not ready or not logged in.")


    async def run(self):
        print("MatrixGatewayService: Starting...")
        if not self.homeserver or not self.user_id:
             print("Gateway: MATRIX_HOMESERVER and MATRIX_USER_ID must be set. Exiting.")
             return
        if not self.password and not self.access_token:
            print("Gateway: Either MATRIX_PASSWORD or MATRIX_ACCESS_TOKEN must be set. Exiting.")
            return


        # Initialize client using access token if provided, otherwise prepare for password login
        if self.access_token:
             print(f"Gateway: Initializing client with User ID {self.user_id} and Access Token.")
             self.client = AsyncClient(
                 self.homeserver,
                 self.user_id,
                 device_id=self.device_name, # device_id is good practice with token login
                 token=self.access_token,
                 store_path=None # Consider adding store_path for encryption/state persistence if needed
             )
        else:
             print(f"Gateway: Initializing client with User ID {self.user_id} for password login.")
             self.client = AsyncClient(
                 self.homeserver,
                 self.user_id,
                 device_id=self.device_name,
                 store_path=None # Consider adding store_path
             )


        self.client.add_event_callback(self._matrix_message_callback, RoomMessageText)
        # Subscribe to commands
        self.bus.subscribe(SendMatrixMessageCommand.model_fields['event_type'].default, self._handle_send_message_command)
        self.bus.subscribe(SetTypingIndicatorCommand.model_fields['event_type'].default, self._handle_set_typing_command) 

        login_success = False
        try:
            if not self.client.access_token: # Only login if we don't already have a token
                print(f"Gateway: Attempting password login as {self.user_id}...")
                login_response = await self.client.login(self.password, device_name=self.device_name)

                if isinstance(login_response, LoginResponse):
                    login_success = True
                    self.access_token = self.client.access_token # <--- Store the token after login!
                    self.user_id = self.client.user_id # Ensure user ID is canonicalized
                    print(f"Gateway: Logged in successfully as {self.client.user_id}")
                    # Optional: Persist self.access_token and self.client.device_id for future runs
                    # Optional: Provide the token to RoomLogicService if needed for presence setting
                    # You could store it in an env var file, or pass via bus/shared state (carefully)
                    # Example: os.environ['MATRIX_ACCESS_TOKEN'] = self.access_token # Not ideal for runtime changes
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