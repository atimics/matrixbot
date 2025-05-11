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
from dotenv import load_dotenv

from message_bus import MessageBus
from event_definitions import MatrixMessageReceivedEvent, SendMatrixMessageCommand, BotDisplayNameReadyEvent

load_dotenv() # To get MATRIX_ configs

class MatrixGatewayService:
    def __init__(self, message_bus: MessageBus):
        self.bus = message_bus
        self.homeserver = os.getenv("MATRIX_HOMESERVER")
        self.user_id = os.getenv("MATRIX_USER_ID")
        self.password = os.getenv("MATRIX_PASSWORD")
        self.device_name = os.getenv("DEVICE_NAME", "NioChatBotSOA_Gateway")
        self.client: Optional[AsyncClient] = None
        self.bot_display_name: Optional[str] = "ChatBot" # Default
        self._stop_event = asyncio.Event()

    async def _matrix_message_callback(self, room: MatrixRoom, event: RoomMessageText):
        if not self.client or event.sender == self.client.user_id:
            return

        sender_display_name = room.user_name(event.sender) or event.sender
        
        # print(f"Gateway: Received message in '{room.display_name}' from '{sender_display_name}'")
        
        msg_event = MatrixMessageReceivedEvent(
            room_id=room.room_id,
            event_id=event.event_id,
            sender_id=event.sender,
            sender_display_name=sender_display_name,
            body=event.body.strip(),
            room_display_name=room.display_name # Pass room name along
        )
        await self.bus.publish(msg_event)

    async def _handle_send_message_command(self, command: SendMatrixMessageCommand):
        if self.client:
            # print(f"Gateway: Received SendMatrixMessageCommand for room {command.room_id}")
            try:
                await self.client.room_send(
                    room_id=command.room_id,
                    message_type="m.room.message",
                    content={"msgtype": "m.text", "body": command.text}
                )
            except Exception as e:
                print(f"Gateway: Exception sending message to {command.room_id}: {e}")
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

        try:
            print(f"Gateway: Attempting login as {self.user_id}...")
            login_response = await self.client.login(self.password, device_name=self.device_name)
            if not isinstance(login_response, LoginResponse):
                print(f"Gateway: Login failed: {login_response}")
                return
            print(f"Gateway: Logged in successfully as {self.client.user_id}")

            # Fetch and publish bot display name
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
                print(f"Gateway: Could not fetch bot's display name, using default '{self.bot_display_name}'. Error: {e}")
                await self.bus.publish(BotDisplayNameReadyEvent(display_name=self.bot_display_name)) # Publish default

            # Join predefined room if specified
            matrix_room_id_env = os.getenv("MATRIX_ROOM_ID")
            if matrix_room_id_env and "YOUR_MATRIX_ROOM_ID" not in matrix_room_id_env:
                print(f"Gateway: Attempting to join predefined room: {matrix_room_id_env}...")
                try:
                    await self.client.join(matrix_room_id_env)
                    print(f"Gateway: Successfully joined room: {matrix_room_id_env}")
                except Exception as e:
                    print(f"Gateway: Failed to join room {matrix_room_id_env}: {e}")
            
            print("Gateway: Starting sync loop...")
            # Use sync with a stop condition
            sync_task = asyncio.create_task(self.client.sync_forever(timeout=30000, full_state=True))
            stop_event_task = asyncio.create_task(self._stop_event.wait())
            
            done, pending = await asyncio.wait([sync_task, stop_event_task], return_when=asyncio.FIRST_COMPLETED)
            
            if stop_event_task in done:
                print("Gateway: Stop event received, cancelling sync task.")
                sync_task.cancel()
                try:
                    await sync_task # Await cancellation
                except asyncio.CancelledError:
                    print("Gateway: Sync task successfully cancelled.")
            elif sync_task in done: # Sync task finished (possibly due to error)
                print(f"Gateway: Sync task finished unexpectedly. Result: {sync_task.result() if not sync_task.cancelled() else 'Cancelled'}")
        except Exception as e:
            print(f"Gateway: Unexpected error in run loop: {type(e).__name__} - {e}")
        finally:
            if self.client:
                print("Gateway: Closing Matrix client...")
                await self.client.close()
            print("MatrixGatewayService: Stopped.")

    async def stop(self):
        print("MatrixGatewayService: Stop requested.")
        self._stop_event.set()