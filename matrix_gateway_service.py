import asyncio
import os
from typing import Optional
from nio import (
    AsyncClient,
    MatrixRoom,
    RoomMessageText,
    LoginResponse,
    ProfileGetResponse,
    # NioError, # NioError does not exist, use specific exceptions or general Exception
)
from nio.exceptions import LocalProtocolError # Import specific known nio exceptions
from dotenv import load_dotenv
import markdown # <--- Import the markdown library

from message_bus import MessageBus
from event_definitions import MatrixMessageReceivedEvent, SendMatrixMessageCommand, BotDisplayNameReadyEvent

load_dotenv() # To get MATRIX_ configs

class MatrixGatewayService:
    def __init__(self, message_bus: MessageBus):
        self.bus = message_bus
        self.homeserver = os.getenv("MATRIX_HOMESERVER")
        self.user_id = os.getenv("MATRIX_USER_ID")
        self.password = os.getenv("MATRIX_PASSWORD")
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
            
            # Assume text from AI might be Markdown and try to convert it
            # A more sophisticated approach might involve the AI explicitly stating
            # the format, or the SendMatrixMessageCommand having a format field.
            # For now, we convert and send both.
            try:
                # Convert Markdown to HTML.
                # `extensions=['nl2br']` converts newlines to <br> which is common for chat.
                # `extensions=['fenced_code']` for code blocks.
                html_body = markdown.markdown(plain_text_body, extensions=['nl2br', 'fenced_code', 'codehilite'])
                
                content = {
                    "msgtype": "m.text",
                    "body": plain_text_body, # Plain text fallback
                    "format": "org.matrix.custom.html",
                    "formatted_body": html_body     # HTML version
                }
                # print(f"Gateway: Sending formatted message to {command.room_id}")
            except Exception as e:
                # If markdown conversion fails, or for any other reason, send as plain text
                print(f"Gateway: Markdown conversion failed (or other error), sending plain text. Error: {e}")
                content = {
                    "msgtype": "m.text",
                    "body": plain_text_body
                }

            try:
                await self.client.room_send(
                    room_id=command.room_id,
                    message_type="m.room.message", # This is the event type, content has msgtype
                    content=content
                )
            except (LocalProtocolError) as e: # Catch specific nio operational errors
                print(f"Gateway: Specific nio error sending message to {command.room_id}: {type(e).__name__} - {e}")
            except Exception as e:
                print(f"Gateway: General error sending message to {command.room_id}: {type(e).__name__} - {e}")
        else:
            print("Gateway: Cannot send message, client not initialized.")

    async def run(self):
        print("MatrixGatewayService: Starting...")
        if not all([self.homeserver, self.user_id, self.password]):
            print("Gateway: Matrix credentials not fully set. Exiting.")
            return

        self.client = AsyncClient(self.homeserver, self.user_id)
        self.client.add_event_callback(self._matrix_message_callback, RoomMessageText)
        self.bus.subscribe(SendMatrixMessageCommand.model_fields['event_type'].default, self._handle_send_message_command)

        login_success = False
        try:
            print(f"Gateway: Attempting login as {self.user_id}...")
            login_response = await self.client.login(self.password, device_name=self.device_name)
            
            if isinstance(login_response, LoginResponse):
                login_success = True
                print(f"Gateway: Logged in successfully as {self.client.user_id}")
            else: 
                print(f"Gateway: Login failed. Response: {login_response}")
                return 

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
                await self.bus.publish(BotDisplayNameReadyEvent(display_name=self.bot_display_name))

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
                    print(f"Gateway: Specific nio error joining room {matrix_room_id_env}: {type(e).__name__} - {e}")
                except Exception as e:
                    print(f"Gateway: General error joining room {matrix_room_id_env}: {type(e).__name__} - {e}")
            
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
                if login_success and not self.client.logged_in:
                     print("Gateway: Client is no longer logged in.")
                print("Gateway: Closing Matrix client...")
                await self.client.close()
            print("MatrixGatewayService: Stopped.")

    async def stop(self):
        print("MatrixGatewayService: Stop requested.")
        self._stop_event.set()