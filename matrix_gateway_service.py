import asyncio
import os
import logging
import json # ADDED
from typing import Optional
from nio import (
    AsyncClient,
    MatrixRoom,
    RoomMessageText,
    RoomMessageImage,
    LoginResponse,
    ProfileGetResponse,
    RoomGetEventResponse, # Added for fetching original event
    RoomGetEventError, # Import RoomGetEventError
    WhoamiResponse, # Added
    WhoamiError # Added
)
from nio.exceptions import LocalProtocolError # Import specific known nio exceptions
from dotenv import load_dotenv, set_key, find_dotenv # Modified import
import markdown

from message_bus import MessageBus
from event_definitions import (
    MatrixMessageReceivedEvent,
    MatrixImageReceivedEvent,
    SendMatrixMessageCommand,
    BotDisplayNameReadyEvent,
    SetTypingIndicatorCommand,
    SetPresenceCommand,
    ReactToMessageCommand,
    SendReplyCommand # Added new commands
)

logger = logging.getLogger(__name__)

load_dotenv() # To get MATRIX_ configs

class MatrixGatewayService:
    def __init__(self, message_bus: MessageBus):
        """Service for handling Matrix gateway operations."""
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
        self._command_queue = asyncio.Queue()
        self._rate_limit_until = 0.0  # Timestamp until which we must wait due to 429
        self._command_worker_task = None

    async def _rate_limited_matrix_call(self, coro_func, *args, **kwargs):
        # Wait if we are currently rate limited
        now = asyncio.get_event_loop().time()
        if self._rate_limit_until > now:
            sleep_duration = self._rate_limit_until - now
            logger.info(f"Gateway: Rate limit active. Sleeping for {sleep_duration:.3f}s until {self._rate_limit_until:.3f}.")
            await asyncio.sleep(sleep_duration)
            # logger.info(f"Gateway: Finished rate limit sleep. Proceeding with Matrix call for {coro_func.__name__}.") # Redundant log
        
        default_retry_sec = 10.0 # Define a default retry period

        try:
            return await coro_func(*args, **kwargs)
        except Exception as e:
            retry_after_seconds = default_retry_sec
            is_rate_limit_error = False

            # Prefer specific status code check if available
            if hasattr(e, 'status_code') and e.status_code == 429:
                is_rate_limit_error = True
                # nio might provide retry_after_ms in the exception object for M_LIMIT_EXCEEDED errors
                # This attribute name comes from nio.responses.ErrorResponse.retry_after_ms
                retry_after_ms = getattr(e, 'retry_after_ms', None)
                if retry_after_ms is not None:
                    retry_after_seconds = retry_after_ms / 1000.0
                    logger.warning(f"Gateway: Got 429 response (rate limited). Parsed Retry-After: {retry_after_seconds:.3f}s from exception attribute.")
                else:
                    # If retry_after_ms is not on the exception, check if the raw response might have it (nio specific)
                    # This part is speculative as nio might not expose raw response headers easily on all exceptions.
                    # For now, we'll rely on retry_after_ms or the default.
                    logger.warning(f"Gateway: Got 429 response (rate limited). No explicit Retry-After in exception. Using default {default_retry_sec}s.")
            elif '429' in str(e) or (hasattr(e, 'message') and isinstance(e.message, str) and 'M_LIMIT_EXCEEDED' in e.message):
                # Fallback if status_code attribute isn't present but error message indicates rate limiting
                is_rate_limit_error = True
                logger.warning(f"Gateway: Got 429-like response (rate limited by string match). Using default {default_retry_sec}s. Error: {e}")

            if is_rate_limit_error:
                self._rate_limit_until = asyncio.get_event_loop().time() + retry_after_seconds
                logger.info(f"Gateway: Rate limit triggered. Will wait for {retry_after_seconds:.3f}s. Next attempt after {self._rate_limit_until:.3f}.")
                await asyncio.sleep(retry_after_seconds)
                logger.info(f"Gateway: Finished rate limit sleep. Retrying Matrix call for {coro_func.__name__}...")
                # Retry the call once after waiting
                return await coro_func(*args, **kwargs) # This could raise again if still rate limited or another error occurs
            else:
                logger.error(f"Gateway: Matrix call error (not a 429 rate limit): {type(e).__name__} - {e}")
                raise # Re-raise non-429 errors

    async def _command_worker(self):
        while not self._stop_event.is_set():
            item_retrieved = False
            try:
                func, args, kwargs = await self._command_queue.get()
                item_retrieved = True # Mark that an item was successfully retrieved
                await func(*args, **kwargs)
            except asyncio.CancelledError:
                logger.info("Gateway: Command worker task cancelled during get().")
                # If cancelled during get(), item_retrieved remains False
                break # Exit loop if worker is cancelled
            except Exception as e:
                logger.error(f"Gateway: Error in command worker: {e}")
                # If an error occurs after get() but during func execution, item_retrieved is True
            finally:
                if item_retrieved: # Only call task_done if an item was processed or attempted
                    self._command_queue.task_done()

    async def _enqueue_command(self, func, *args, **kwargs):
        await self._command_queue.put((func, args, kwargs))

    async def _matrix_message_callback(self, room: MatrixRoom, event: RoomMessageText):
        # If client is not initialized or if the sender is the bot itself, ignore.
        if not self.client or event.sender == self.client.user_id: # Ensure self.client.user_id is the correct bot user ID
            if self.client and event.sender == self.client.user_id:
                logger.info(f"Gateway: Ignoring own message from {event.sender} in room {room.room_id}")
            return

        sender_display_name = room.user_name(event.sender) or event.sender

        msg_event = MatrixMessageReceivedEvent(
            room_id=room.room_id,
            event_id_matrix=event.event_id, # Corrected field name
            sender_id=event.sender,
            sender_display_name=sender_display_name,
            body=event.body.strip(),
            room_display_name=room.display_name
        )
        await self.bus.publish(msg_event)

    async def _matrix_image_callback(self, room: MatrixRoom, event: RoomMessageImage):
        if not self.client or event.sender == self.client.user_id:
            return
        sender_display_name = room.user_name(event.sender) or event.sender
        img_event = MatrixImageReceivedEvent(
            room_id=room.room_id,
            event_id_matrix=event.event_id,
            sender_id=event.sender,
            sender_display_name=sender_display_name,
            image_url=event.url,
            body=event.body,
            room_display_name=room.display_name,
        )
        await self.bus.publish(img_event)

    async def _handle_send_message_command(self, command: SendMatrixMessageCommand):
        await self._enqueue_command(self._send_message_impl, command)

    async def _send_message_impl(self, command: SendMatrixMessageCommand):
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
                logger.error(f"Gateway: Markdown conversion failed, sending plain text. Error: {e}")
                content = {
                    "msgtype": "m.text",
                    "body": plain_text_body
                }

            try:
                await self._rate_limited_matrix_call(
                    self.client.room_send,
                    room_id=command.room_id,
                    message_type="m.room.message",
                    content=content
                )
            except (LocalProtocolError) as e:
                logger.error(f"Gateway: Specific nio error sending message to {command.room_id}: {type(e).__name__} - {e}")
            except Exception as e:
                logger.error(f"Gateway: General error sending message to {command.room_id}: {type(e).__name__} - {e}")
        else:
            logger.error("Gateway: Cannot send message, client not initialized.")

    async def _handle_react_to_message_command(self, command: ReactToMessageCommand):
        await self._enqueue_command(self._react_to_message_impl, command)

    async def _react_to_message_impl(self, command: ReactToMessageCommand):
        if not self.client or not self.client.logged_in:
            logger.error("Gateway: Client not ready, cannot send reaction.")
            return
        try:
            content = {
                "m.relates_to": {
                    "rel_type": "m.annotation",
                    "event_id": command.event_id_to_react_to, # Changed from command.target_event_id
                    "key": command.reaction_key
                }
            }
            await self._rate_limited_matrix_call(
                self.client.room_send,
                room_id=command.room_id,
                message_type="m.reaction",
                content=content
            )
        except Exception as e:
            logger.error(f"Gateway: Error sending reaction to {command.room_id}: {e}")

    async def _handle_send_reply_command(self, command: SendReplyCommand):
        await self._enqueue_command(self._send_reply_impl, command)

    async def _send_reply_impl(self, command: SendReplyCommand):
        logger.info(f"Gateway: Attempting to send reply for command: {command.event_id}, Room: {command.room_id}, ReplyTo: {command.reply_to_event_id}, Text: '{command.text[:75]}...'") # MODIFIED for more text and info
        if not self.client or not self.client.logged_in:
            logger.error(f"Gateway: Client not ready for SendReplyCommand {command.event_id}, cannot send reply.") # ADDED command event_id
            return

        new_message_plain_text = command.text
        final_body_for_send = new_message_plain_text
        original_event_text_for_fallback_html = "" # ADDED for clarity

        try:
            logger.debug(f"Gateway [ReplyCmd:{command.event_id}]: Fetching original event {command.reply_to_event_id} for reply context in room {command.room_id}.") # ADDED command event_id and room
            try:
                original_event_response = await self.client.room_get_event(
                    command.room_id, command.reply_to_event_id
                )
                if isinstance(original_event_response, RoomGetEventResponse) and original_event_response.event:
                    original_event = original_event_response.event
                    original_sender = original_event.sender
                    original_body = getattr(original_event, 'body', None)
                    logger.debug(f"Gateway [ReplyCmd:{command.event_id}]: Original event fetched. Sender: {original_sender}, Body is present: {original_body is not None}") # ADDED command event_id

                    if original_sender and original_body:
                        original_body_str = str(original_body)
                        original_body_lines = original_body_str.splitlines()
                        quoted_original_body = "\n".join([f"> {line}" for line in original_body_lines])
                        final_body_for_send = f"{quoted_original_body}\n\n{new_message_plain_text}"
                        original_event_html = markdown.markdown(original_body_str, extensions=['nl2br'])
                        original_event_text_for_fallback_html = f"<mx-reply><blockquote><a href=\"https://matrix.to/#/{command.room_id}/{command.reply_to_event_id}\">In reply to</a> <a href=\"https://matrix.to/#/{original_event.sender}\">{original_event.sender}</a>:<br>{original_event_html}</blockquote></mx-reply>"
                        logger.debug(f"Gateway [ReplyCmd:{command.event_id}]: Prepared quoted body and HTML fallback for reply.") # ADDED command event_id
                    else:
                        logger.warning(f"Gateway [ReplyCmd:{command.event_id}]: Original event {command.reply_to_event_id} fetched but lacks sender or body for fallback quote.")
                elif isinstance(original_event_response, RoomGetEventError):
                    logger.warning(f"Gateway [ReplyCmd:{command.event_id}]: Failed to fetch original event {command.reply_to_event_id} (RoomGetEventError). Error: {original_event_response.message}, Status: {original_event_response.status_code}")
                else:
                    logger.warning(f"Gateway [ReplyCmd:{command.event_id}]: Failed to fetch details of original event {command.reply_to_event_id} for fallback reply. Response: {original_event_response}")
            except Exception as e:
                logger.error(f"Gateway [ReplyCmd:{command.event_id}]: Unexpected error fetching event {command.reply_to_event_id} for reply: {type(e).__name__} - {e}", exc_info=True)

            html_body_content = markdown.markdown(new_message_plain_text, extensions=['nl2br', 'fenced_code', 'codehilite'])

            content = {
                "msgtype": "m.text",
                "body": final_body_for_send,
                "format": "org.matrix.custom.html",
                "formatted_body": f"{original_event_text_for_fallback_html}{html_body_content}",
                "m.relates_to": {
                    "m.in_reply_to": {
                        "event_id": command.reply_to_event_id
                    }
                }
            }
            logger.debug(f"Gateway [ReplyCmd:{command.event_id}]: Prepared content for room_send: {json.dumps(content)}") # ADDED json.dumps for better readability

            await self._rate_limited_matrix_call(
                self.client.room_send,
                room_id=command.room_id,
                message_type="m.room.message",
                content=content
            )
            logger.info(f"Gateway [ReplyCmd:{command.event_id}]: Reply successfully sent to room {command.room_id} in reply to {command.reply_to_event_id}. Text: '{command.text[:75]}...'")
        except Exception as e:
            logger.error(f"Gateway [ReplyCmd:{command.event_id}]: Error sending reply to {command.room_id} (ReplyTo: {command.reply_to_event_id}): {type(e).__name__} - {e}", exc_info=True)

    async def _handle_set_typing_command(self, command: SetTypingIndicatorCommand):
        await self._enqueue_command(self._set_typing_impl, command)

    async def _set_typing_impl(self, command: SetTypingIndicatorCommand):
        if self.client and self.client.logged_in:
            try:
                await self._rate_limited_matrix_call(
                    self.client.room_typing,
                    room_id=command.room_id,
                    typing_state=command.typing,
                    timeout=command.timeout # Pass timeout from command
                )
                # logger.info(f"Gateway: Typing indicator set to {command.typing} in {command.room_id}")
            except LocalProtocolError as e:
                logger.error(f"Gateway: Failed to set typing indicator in {command.room_id} (Nio Error): {e}")
            except Exception as e:
                logger.error(f"Gateway: Failed to set typing indicator in {command.room_id} (Error): {e}")
        else:
            logger.error(f"Gateway: Cannot set typing indicator in {command.room_id}, client not ready or not logged in.")

    async def _handle_set_presence_command(self, command: SetPresenceCommand):
        await self._enqueue_command(self._set_presence_impl, command)

    async def _set_presence_impl(self, command: SetPresenceCommand):
        if self.client and self.client.logged_in:
            try:
                await self._rate_limited_matrix_call(
                    self.client.set_presence,
                    presence=command.presence,
                    status_msg=command.status_msg
                )
                logger.info(f"Gateway: Presence set to {command.presence} with message '{command.status_msg}'")
            except LocalProtocolError as e:
                logger.error(f"Gateway: Failed to set presence (Nio Error): {e}")
            except Exception as e:
                logger.error(f"Gateway: Failed to set presence (Error): {e}")
        else:
            logger.error("Gateway: Cannot set presence, client not ready or not logged in.")


    async def run(self) -> None:
        logger.info("MatrixGatewayService: Starting...")
        if not self.homeserver or not self.user_id: # self.user_id here is from initial .env or None
             logger.error("Gateway: MATRIX_HOMESERVER and MATRIX_USER_ID must be set. Exiting.")
             return
        if not self.password and not self.access_token: # self.access_token here is from initial .env or None
            logger.error("Gateway: Either MATRIX_PASSWORD or MATRIX_ACCESS_TOKEN must be set. Exiting.")
            return

        # Determine the device_id to use for AsyncClient constructor
        # This device_id is primarily for when a token is provided.
        client_constructor_device_id = self.persisted_device_id or self.device_name_config

        if self.access_token:
             # If using token, user_id and device_id should ideally be the ones from the session that generated the token
             # self.user_id is already loaded from MATRIX_USER_ID (potentially canonicalized and saved from previous run)
             # client_constructor_device_id uses self.persisted_device_id (saved from previous run)
             logger.info(f"Gateway: Initializing client with User ID {self.user_id}, Access Token, and Device ID {client_constructor_device_id}.")
             self.client = AsyncClient(
                 self.homeserver,
                 self.user_id,
                 device_id=client_constructor_device_id,
                 # token=self.access_token, # Removed: token is not a valid constructor argument
                 store_path=None
             )
             self.client.access_token = self.access_token # Set token after initialization
        else:
             logger.info(f"Gateway: Initializing client with User ID {self.user_id} for password login.")
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
        self.client.add_event_callback(self._matrix_image_callback, RoomMessageImage)
        # Subscribe to commands
        self.bus.subscribe(SendMatrixMessageCommand.model_fields['event_type'].default, self._handle_send_message_command)
        self.bus.subscribe(ReactToMessageCommand.model_fields['event_type'].default, self._handle_react_to_message_command)
        self.bus.subscribe(SendReplyCommand.model_fields['event_type'].default, self._handle_send_reply_command)
        self.bus.subscribe(SetTypingIndicatorCommand.model_fields['event_type'].default, self._handle_set_typing_command)
        self.bus.subscribe(SetPresenceCommand.model_fields['event_type'].default, self._handle_set_presence_command)

        self._command_worker_task = asyncio.create_task(self._command_worker())

        login_success = False
        try:
            if not self.client.access_token: # Only login if we don't already have a token (i.e. self.access_token was None)
                logger.info(f"Gateway: Attempting password login as {self.user_id}...")
                # Use self.device_name_config for the login attempt
                login_response = await self.client.login(self.password, device_name=self.device_name_config)

                if isinstance(login_response, LoginResponse):
                    login_success = True
                    # IMPORTANT: Update with values from the server
                    self.access_token = self.client.access_token
                    self.user_id = self.client.user_id # Canonicalized user ID from server
                    actual_device_id = self.client.device_id # Actual device ID from server

                    logger.info(f"Gateway: Logged in successfully as {self.user_id} with device ID {actual_device_id}")
                    logger.info(f"Gateway: Saving access token, user ID, and device ID to .env file...")
                    try:
                        dotenv_path_found = find_dotenv(usecwd=True, raise_error_if_not_found=False)
                        env_file_to_write = dotenv_path_found
                        if not env_file_to_write: # If .env doesn't exist or not found in CWD/parents
                            env_file_to_write = os.path.join(os.getcwd(), ".env")
                            # Create .env if it doesn't exist, so set_key can write to it
                            if not os.path.exists(env_file_to_write):
                                with open(env_file_to_write, "w") as f:
                                    pass # Create empty .env
                                logger.info(f"Gateway: Created .env file at {env_file_to_write}")
                        
                        set_key(env_file_to_write, "MATRIX_ACCESS_TOKEN", self.access_token)
                        set_key(env_file_to_write, "MATRIX_USER_ID", self.user_id)
                        set_key(env_file_to_write, "MATRIX_DEVICE_ID", actual_device_id)
                        logger.info(f"Gateway: Credentials saved to {env_file_to_write}.")

                        # Update current environment variables for this running instance
                        # and internal state, so it doesn't rely on a restart to use them.
                        os.environ['MATRIX_ACCESS_TOKEN'] = self.access_token
                        os.environ['MATRIX_USER_ID'] = self.user_id
                        os.environ['MATRIX_DEVICE_ID'] = actual_device_id
                        self.persisted_device_id = actual_device_id # Update internal state

                    except Exception as e:
                        logger.error(f"Gateway: Failed to save credentials to .env file. Error: {type(e).__name__} - {e}")
                else:
                    logger.error(f"Gateway: Login failed. Response: {login_response}")
                    await self.client.close()
                    return
            else:
                logger.info("Gateway: Using provided access token. Verifying token...")
                # Optionally verify token with a simple API call like /account/whoami
                try:
                   whoami_response = await self.client.whoami() # Returns WhoamiResponse or WhoamiError
                   if isinstance(whoami_response, WhoamiResponse):
                       if whoami_response.user_id == self.user_id:
                           logger.info("Gateway: Access token is valid.")
                           login_success = True # Treat as successful login
                       else:
                           logger.error(f"Gateway: Access token seems invalid or for wrong user (response: {whoami_response.user_id}, expected: {self.user_id}).")
                           return # Exit run method, finally block will handle cleanup
                   elif isinstance(whoami_response, WhoamiError):
                       logger.error(f"Gateway: Failed to verify access token. Whoami check failed with WhoamiError: {getattr(whoami_response, 'message', 'Unknown WhoamiError')}")
                       return # Exit run method, finally block will handle cleanup
                   else:
                       logger.error(f"Gateway: Failed to verify access token. Unexpected whoami response type: {type(whoami_response)}. Response: {whoami_response}")
                       return # Exit run method, finally block will handle cleanup
                except Exception as e:
                    logger.error(f"Gateway: Exception during access token verification: {type(e).__name__} - {e}")
                    return # Exit run method, finally block will handle cleanup


            # --- Fetch display name (remains the same) ---
            try:
                profile: ProfileGetResponse = await self.client.get_profile(self.client.user_id)
                fetched_displayname = profile.displayname
                if fetched_displayname: self.bot_display_name = fetched_displayname
                else:
                    localpart = self.client.user_id.split(':')[0]
                    self.bot_display_name = localpart[1:] if localpart.startswith("@") else localpart
                logger.info(f"Gateway: Bot display name set to '{self.bot_display_name}'")
                await self.bus.publish(BotDisplayNameReadyEvent(display_name=self.bot_display_name))
            except Exception as e:
                logger.warning(f"Gateway: Could not fetch bot's display name, using default '{self.bot_display_name}'. Error: {type(e).__name__} - {e}")
                await self.bus.publish(BotDisplayNameReadyEvent(display_name=self.bot_display_name)) # Publish default


            # --- Join room (remains the same) ---
            matrix_room_id_env = os.getenv("MATRIX_ROOM_ID")
            if matrix_room_id_env and "YOUR_MATRIX_ROOM_ID" not in matrix_room_id_env:
                logger.info(f"Gateway: Attempting to join predefined room: {matrix_room_id_env}...")
                try:
                    join_response = await self.client.join(matrix_room_id_env)
                    if hasattr(join_response, 'room_id'):
                         logger.info(f"Gateway: Successfully joined room: {join_response.room_id}")
                    else:
                         logger.warning(f"Gateway: Failed to join room {matrix_room_id_env}. Response: {join_response}")
                except (LocalProtocolError) as e:
                    # Handle 'already joined' specifically if needed
                    if "already in room" in str(e).lower():
                         logger.info(f"Gateway: Already in room {matrix_room_id_env}.")
                    else:
                         logger.error(f"Gateway: Specific nio error joining room {matrix_room_id_env}: {type(e).__name__} - {e}")
                except Exception as e:
                    logger.error(f"Gateway: General error joining room {matrix_room_id_env}: {type(e).__name__} - {e}")


            try:
                # Set an initial presence, e.g., online or unavailable
                initial_presence = "unavailable" # Or "unavailable" if you want it to start idle
                initial_status_msg = "Initializing..." # Optional
                await self.client.set_presence(presence=initial_presence, status_msg=initial_status_msg)
                logger.info(f"Gateway: Initial presence set to {initial_presence}")
            except Exception as e:
                logger.warning(f"Gateway: Failed to set initial presence: {e}")

            # --- Sync loop (remains the same) ---
            logger.info("Gateway: Starting sync loop...")
            sync_task = asyncio.create_task(self.client.sync_forever(timeout=30000, full_state=True))
            stop_event_task = asyncio.create_task(self._stop_event.wait())

            done, pending = await asyncio.wait([sync_task, stop_event_task], return_when=asyncio.FIRST_COMPLETED)

            if stop_event_task in done:
                logger.info("Gateway: Stop event received, cancelling sync task.")
                if not sync_task.done(): sync_task.cancel()
            elif sync_task in done:
                logger.warning("Gateway: Sync task finished unexpectedly.")
                try: sync_task.result()
                except asyncio.CancelledError: logger.info("Gateway: Sync task was cancelled.")
                except (LocalProtocolError) as e: logger.error(f"Gateway: Sync task failed (Matrix Sync error): {type(e).__name__} - {e}")
                except Exception as e: logger.error(f"Gateway: Sync task failed (general error): {type(e).__name__} - {e}")

            if sync_task.cancelled() or (pending and sync_task in pending and not sync_task.done()):
                try: await sync_task
                except asyncio.CancelledError: logger.info("Gateway: Sync task successfully processed cancellation.")
                except Exception as e: logger.error(f"Gateway: Exception awaiting cancelled sync_task: {type(e).__name__} - {e}")


        except (LocalProtocolError) as e:
            logger.error(f"Gateway: Matrix Sync error during initial setup: {type(e).__name__} - {e}")
        except ConnectionError as e:
            logger.error(f"Gateway: ConnectionError during initial setup: {type(e).__name__} - {e}")
        except Exception as e:
            logger.error(f"Gateway: Unexpected error in MatrixGatewayService run (setup): {type(e).__name__} - {e}")
        finally:
            if self.client:
                if login_success and not self.client.logged_in and not self._stop_event.is_set():
                     logger.warning("Gateway: Client is no longer logged in.")
                logger.info("Gateway: Closing Matrix client session...")
                # nio.AsyncClient does not have a .close() method.
                # Stopping the sync loop (via _stop_event) and optionally logging out is the way.
                if self.client.logged_in:
                    try:
                        await self.client.logout()
                        logger.info("Gateway: Client logged out.")
                    except Exception as e:
                        logger.error(f"Gateway: Error during client logout: {e}")
            if self._command_worker_task:
                self._command_worker_task.cancel()
                try:
                    await self._command_worker_task
                except Exception:
                    pass
            logger.info("MatrixGatewayService: Stopped.")

    async def stop(self) -> None:
        logger.info("MatrixGatewayService: Stop requested.")
        self._stop_event.set()