"""
Refactored Matrix Observer

A modular Matrix observer that uses separate components for different responsibilities.
This replaces the monolithic 2000-line observer with a clean, maintainable structure.
"""

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional, Callable

from nio import (
    AsyncClient,
    InviteMemberEvent,
    LoginResponse,
    MatrixRoom,
    RoomMemberEvent,
    RoomMessageImage,
    RoomMessageText,
    BadEventType,
    MegolmEvent,
)

from ...config import settings
from ...core.world_state import WorldStateManager
from ..base import Integration, IntegrationError, IntegrationConnectionError
from ..base_observer import BaseObserver, ObserverStatus

# Import our modular components
from .components.auth import MatrixAuthHandler
from .components.rooms import MatrixRoomManager
from .components.events import MatrixEventHandler
from .components.messages import MatrixMessageOperations
from .components.room_ops import MatrixRoomOperations
from .components.encryption import MatrixEncryptionHandler

logger = logging.getLogger(__name__)


class MatrixObserver(Integration, BaseObserver):
    """Modular Matrix observer that delegates to specialized components."""

    def __init__(
        self,
        integration_id: str = "matrix",
        display_name: str = "Matrix Integration",
        config: Dict[str, Any] = None,
        world_state_manager: WorldStateManager = None,
        arweave_client=None,
        db_manager=None,
        processing_hub=None
    ):
        # Support legacy positional usage: MatrixObserver(world_state, arweave_client)
        if not isinstance(integration_id, str):
            # Legacy call: first param is world_state, second is arweave_client
            ws_manager = integration_id
            arw_client = display_name
            integration_id = "matrix"
            display_name = "Matrix Integration"
            config = config or {}
            world_state_manager = ws_manager
            arweave_client = arw_client

        Integration.__init__(self, integration_id, display_name, config or {})
        BaseObserver.__init__(self, integration_id, display_name)

        # Core properties
        self.world_state = world_state_manager
        self.arweave_client = arweave_client
        self.db_manager = db_manager  # Store database manager for encryption handler
        self.homeserver = settings.matrix.homeserver
        self.user_id = settings.matrix.user_id
        self.password = settings.matrix.password
        self.client: Optional[AsyncClient] = None
        self.sync_task: Optional[asyncio.Task] = None
        self.channels_to_monitor = []
        self.processing_hub = processing_hub
        
        # State change callback for orchestrator notifications (matches FarcasterObserver pattern)
        self.on_state_change: Optional[Callable] = None
        
        # E2EE initialization lock to prevent race conditions
        self._e2ee_ready = asyncio.Event()
        self._login_complete = asyncio.Event()
        
        # Initial sync tracking to prevent spurious responses during startup
        self._initial_sync_complete = False

        # Create store directory
        self.store_path = Path("matrix_store")
        self.store_path.mkdir(parents=True, exist_ok=True)

        # Check configuration
        self._enabled = all([self.homeserver, self.user_id, self.password])
        if not self._enabled:
            error_msg = (
                "Matrix configuration incomplete. Check MATRIX_HOMESERVER, "
                "MATRIX_USER_ID, and MATRIX_PASSWORD environment variables."
            )
            self._set_status(ObserverStatus.ERROR, error_msg)
            return

        # Initialize components (will be properly set up when client is available)
        self.auth_handler: Optional[MatrixAuthHandler] = None
        self.room_manager: Optional[MatrixRoomManager] = None
        self.event_handler: Optional[MatrixEventHandler] = None
        self.message_ops: Optional[MatrixMessageOperations] = None
        self.room_ops: Optional[MatrixRoomOperations] = None
        self.encryption_handler: Optional[MatrixEncryptionHandler] = None

        self._set_status(ObserverStatus.DISCONNECTED)
        logger.debug(f"MatrixObserver: Initialized modular observer for {self.user_id}@{self.homeserver}")

    @property
    def enabled(self) -> bool:
        """Check if integration is enabled and properly configured."""
        return self._enabled

    @property
    def integration_type(self) -> str:
        """Return the integration type identifier."""
        return "matrix"

    async def start(self) -> bool:
        """Start the Matrix observer by connecting and beginning to observe."""
        logger.debug("MatrixObserver: Starting Matrix observer...")
        
        # Connect to Matrix
        success = await self.connect()
        
        if success:
            # Make sure the processing hub is properly set on the event handler after connect
            if self.processing_hub and hasattr(self, 'event_handler') and self.event_handler:
                self.event_handler.processing_hub = self.processing_hub
                logger.debug("MatrixObserver: Processing hub propagated to event handler after connection")
            else:
                logger.warning(f"MatrixObserver: Cannot propagate processing hub - hub_exists={self.processing_hub is not None}, handler_exists={hasattr(self, 'event_handler') and self.event_handler is not None}")
                
        return success

    def _initialize_components(self):
        """Initialize all components with the Matrix client."""
        if not self.client:
            logger.error("MatrixObserver: Cannot initialize components without Matrix client")
            return

        # Initialize components
        self.auth_handler = MatrixAuthHandler(
            self.homeserver, self.user_id, self.password, self.store_path
        )

        if self.world_state:
            self.room_manager = MatrixRoomManager(self.world_state)
        
            self.event_handler = MatrixEventHandler(
                self.world_state,
                self.room_manager,
                self.user_id,
                self.arweave_client,
                self.processing_hub,
                self.channels_to_monitor,
                observer=self  # Pass observer reference for state change callbacks
            )
        else:
            logger.warning("MatrixObserver: No world state manager provided")

        self.message_ops = MatrixMessageOperations(self.client, self.user_id)
        
        if self.world_state and self.room_manager:
            self.room_ops = MatrixRoomOperations(
                self.client, 
                self.user_id, 
                self.world_state,
                self.room_manager,
                self.channels_to_monitor
            )

        self.encryption_handler = MatrixEncryptionHandler(self.client, self.user_id, self.db_manager)

        # After all components are initialized, make sure processing hub is set
        if self.processing_hub and self.event_handler:
            self.event_handler.processing_hub = self.processing_hub
            logger.debug("MatrixObserver: Processing hub set on event handler during component initialization")

        logger.info("MatrixObserver: All components initialized")

    async def connect(self, credentials: Optional[Dict[str, Any]] = None) -> bool:
        """Connect to Matrix server and start observing."""
        if not self.enabled:
            self._set_status(ObserverStatus.ERROR, "Matrix observer is disabled due to missing configuration")
            return False

        try:
            self._set_status(ObserverStatus.CONNECTING)
            logger.debug("MatrixObserver: Starting Matrix client connection...")

            # Create Matrix client
            self.client = AsyncClient(self.homeserver, self.user_id, store_path=str(self.store_path))

            # Initialize components now that we have a client
            self._initialize_components()

            # Set up event callbacks
            self._setup_event_callbacks()

            # Authenticate
            if not await self._authenticate():
                self._set_status(ObserverStatus.ERROR, "Authentication failed")
                return False

            # Start sync
            await self._start_sync()

            self._set_status(ObserverStatus.CONNECTED)
            logger.info("MatrixObserver: Successfully connected and syncing")
            return True

        except Exception as e:
            error_msg = f"Failed to connect to Matrix: {e}"
            self._set_status(ObserverStatus.ERROR, error_msg)
            logger.error(f"MatrixObserver: {error_msg}")
            return False

    def _setup_event_callbacks(self):
        """Set up Matrix event callbacks."""
        if not self.client or not self.event_handler:
            return

        # Message events
        self.client.add_event_callback(self._on_message, RoomMessageText)
        self.client.add_event_callback(self._on_message, RoomMessageImage)

        # Room events
        self.client.add_event_callback(self._on_invite, InviteMemberEvent)
        self.client.add_event_callback(self._on_membership_change, RoomMemberEvent)

        # Encryption events
        self.client.add_event_callback(self._on_bad_event, BadEventType)
        
        # E2EE initialization callbacks
        self.client.add_response_callback(self._on_login_response, LoginResponse)
        
        # Import and add Megolm event callback for undecryptable messages
        try:
            from nio import MegolmEvent, SyncResponse
            self.client.add_event_callback(self._on_megolm_event, MegolmEvent)
            self.client.add_response_callback(self._on_sync_response, SyncResponse)
        except ImportError:
            logger.debug("MatrixObserver: MegolmEvent not available, skipping callback")

        logger.debug("MatrixObserver: Event callbacks configured")

    async def _authenticate(self) -> bool:
        """Handle authentication using the auth handler."""
        if not self.auth_handler:
            logger.error("MatrixObserver: Auth handler not initialized")
            return False

        # Try to load existing token
        access_token = await self.auth_handler.load_token()
        
        if access_token:
            self.client.access_token = access_token
            
            # Set user_id and device_id from token file before loading store
            try:
                with open(self.auth_handler.token_file, 'r') as f:
                    token_data = json.load(f)
                self.client.user_id = token_data.get('user_id', self.user_id)
                self.client.device_id = token_data.get('device_id')
                
                # Explicitly load the encryption store. This is the critical step.
                self.client.load_store()
                logger.debug("MatrixObserver: Successfully loaded encryption store from session.")
            except Exception as e:
                logger.error(f"MatrixObserver: Failed to load encryption store: {e}. Proceeding with re-login.")
                self.auth_handler.clear_token()
                # Fall through to login
                access_token = await self.auth_handler.login_with_retry(self.client)
                return access_token is not None
            
            # Verify token is still valid
            if await self.auth_handler.verify_token_with_backoff(self.client):
                logger.debug("MatrixObserver: Using existing valid token")
                return True
            else:
                logger.warning("MatrixObserver: Existing token invalid, re-authenticating")

        # Login with credentials
        access_token = await self.auth_handler.login_with_retry(self.client)
        return access_token is not None

    async def _start_sync(self):
        """Start the Matrix sync loop."""
        if not self.client:
            return

        # Start sync in background
        self.sync_task = asyncio.create_task(self._sync_forever())
        logger.debug("MatrixObserver: Sync task started")

    async def _sync_forever(self):
        """Main sync loop."""
        try:
            await self.client.sync_forever(timeout=30000)
        except Exception as e:
            logger.error(f"MatrixObserver: Sync loop error: {e}")
            self._set_status(ObserverStatus.ERROR, f"Sync error: {e}")

    # Event callback methods that delegate to components
    async def _on_message(self, room: MatrixRoom, event):
        """Handle message events."""
        if self.event_handler:
            await self.event_handler.handle_message(room, event, self.client)

    async def _on_invite(self, room, event):
        """Handle invite events."""
        if self.event_handler:
            await self.event_handler.handle_invite(room, event)

    async def _on_membership_change(self, room, event):
        """Handle membership change events."""
        if self.event_handler:
            await self.event_handler.handle_membership_change(room, event)

    async def _on_bad_event(self, room: MatrixRoom, event):
        """Handle encryption errors and bad events."""
        if self.encryption_handler and hasattr(event, 'event_id') and hasattr(event, 'sender'):
            # Only handle if this is a MegolmEvent or similar decryptable event
            if isinstance(event, MegolmEvent):
                await self.encryption_handler.handle_decryption_failure(room, event)
            else:
                # For other event types, create a minimal object with required attributes
                logger.debug(f"MatrixObserver: Non-Megolm bad event {getattr(event, 'event_id', 'unknown')} of type {type(event)}")
        
        # Also handle via event handler for logging
        if self.event_handler:
            await self.event_handler.handle_encryption_error(room, event)

    async def _on_megolm_event(self, room: MatrixRoom, event):
        """Handle undecryptable Megolm events."""
        logger.warning(
            f"MatrixObserver: Undecryptable Megolm event {getattr(event, 'event_id', 'unknown')} "
            f"in room {room.room_id} from {getattr(event, 'sender', 'unknown')}"
        )
        
        if self.encryption_handler:
            # Pass the full event object since it's already a MegolmEvent
            await self.encryption_handler.handle_decryption_failure(room, event)

    async def _on_login_response(self, response):
        """Handle login response for E2EE initialization."""
        logger.debug("MatrixObserver: Login response received for E2EE initialization")
        
        # Set the login complete event
        self._login_complete.set()
        logger.debug("MatrixObserver: Login response processed for E2EE")

    async def _on_sync_response(self, response):
        """Handle sync response for E2EE initialization and initial sync tracking."""
        logger.debug("MatrixObserver: Sync response received for E2EE initialization")
        
        # Set E2EE ready after first sync if not already set
        if not self._e2ee_ready.is_set():
            self._e2ee_ready.set()
            logger.debug("MatrixObserver: E2EE initialized after first sync")
        
        # Mark initial sync as complete after the first sync response
        if not self._initial_sync_complete:
            self._initial_sync_complete = True
            logger.info("MatrixObserver: Initial sync complete - bot will now respond to events")
            
            # Notify event handler about initial sync completion
            if self.event_handler:
                self.event_handler.initial_sync_complete = True
            
            # Mark state as stale after initial sync completion
            if self.processing_hub:
                self.processing_hub.mark_state_as_stale(
                    "matrix_initial_sync_complete",
                    {"initial_sync": True}
                )
        else:
            # For subsequent syncs, mark state as stale to trigger processing
            if self.processing_hub:
                self.processing_hub.mark_state_as_stale(
                    "matrix_sync_response",
                    {"sync_time": time.time()}
                )

    # Public API methods that delegate to components
    async def send_message(self, room_id: str, content: str) -> Dict[str, Any]:
        """Send a message to a room."""
        if self.message_ops:
            return await self.message_ops.send_message(room_id, content)
        return {"success": False, "error": "Message operations not initialized"}

    async def send_reply(
        self,
        room_id: str,
        content: str,
        reply_to_event_id: str,
    ) -> Dict[str, Any]:
        """Send a reply to a message."""
        if self.message_ops:
            return await self.message_ops.send_reply(room_id, content, reply_to_event_id)
        return {"success": False, "error": "Message operations not initialized"}

    async def join_room(self, room_identifier: str) -> Dict[str, Any]:
        """Join a Matrix room."""
        if self.room_ops:
            return await self.room_ops.join_room(room_identifier)
        return {"success": False, "error": "Room operations not initialized"}

    async def leave_room(self, room_id: str, reason: Optional[str] = None) -> Dict[str, Any]:
        """Leave a Matrix room."""
        if self.room_ops:
            return await self.room_ops.leave_room(room_id, reason)
        return {"success": False, "error": "Room operations not initialized"}

    def add_channel(self, channel_id: str, channel_name: Optional[str] = None, force_fetch: bool = False):
        """Add a channel to monitor - unified method."""
        if not self.enabled:
            logger.warning("Matrix observer is disabled - cannot add channel")
            return False
            
        # Add to monitoring list
        if channel_id not in self.channels_to_monitor:
            self.channels_to_monitor.append(channel_id)
        
        # If we have a simple channel name (legacy usage), just register with world state
        if channel_name and not force_fetch:
            if self.world_state:
                # Use the world state manager to add the channel
                from ...core.world_state.data_structures import Channel
                channel = Channel(
                    id=channel_id,
                    name=channel_name,
                    type="matrix"
                )
                self.world_state.add_channel(channel)
                
            logger.debug(f"MatrixObserver: Added channel {channel_name} ({channel_id}) to monitoring")
            return True
        
        # Otherwise try to fetch from client (async version)
        if hasattr(self, 'client') and self.client:
            try:
                logger.debug(f"MatrixObserver: Adding channel {channel_id} (force_fetch={force_fetch})")
                
                # Get the room object from the client
                if not hasattr(self.client, 'rooms'):
                    logger.error(f"MatrixObserver: Client not available for room {channel_id}")
                    return False
                
                if channel_id not in self.client.rooms:
                    logger.warning(f"MatrixObserver: Room {channel_id} not found in client rooms")
                    return False
                
                room = self.client.rooms[channel_id]
                
                # Use the room manager to extract details and register the room
                if self.room_manager:
                    room_details = self.room_manager.extract_room_details(room)
                    
                    if room_details:
                        # Use room manager's register_room method which includes message fetching
                        self.room_manager.register_room(channel_id, room_details, room)
                        logger.debug(f"MatrixObserver: Successfully added channel {channel_id}")
                        return True
                    else:
                        logger.warning(f"MatrixObserver: Failed to get details for channel {channel_id}")
                        return False
                else:
                    logger.error(f"MatrixObserver: Room manager not initialized")
                    return False
                    
            except Exception as e:
                logger.error(f"MatrixObserver: Error adding channel {channel_id}: {e}")
                return False
        
        logger.warning(f"MatrixObserver: Client not available for channel {channel_id}")
        return False

    async def disconnect(self) -> None:
        """Disconnect from Matrix."""
        try:
            if self.sync_task and not self.sync_task.done():
                self.sync_task.cancel()
                try:
                    await self.sync_task
                except asyncio.CancelledError:
                    pass

            if self.client:
                await self.client.close()
                self.client = None

            self._set_status(ObserverStatus.DISCONNECTED)
            logger.debug("MatrixObserver: Disconnected successfully")

        except Exception as e:
            logger.error(f"MatrixObserver: Error during disconnect: {e}")

    async def is_healthy(self) -> bool:
        """Check if the observer is healthy."""
        if not self.client:
            return False

        try:
            # Simple health check - verify we can make API calls
            if self.client.access_token:
                response = await self.client.whoami()
                return hasattr(response, 'user_id') and response.user_id == self.user_id
        except Exception as e:
            logger.warning(f"MatrixObserver: Health check failed: {e}")

        return False

    async def test_connection(self) -> Dict[str, Any]:
        """Test the connection to Matrix without fully connecting."""
        if not self.enabled:
            return {
                "success": False, 
                "error": "Matrix integration is disabled due to missing configuration"
            }

        # Check that all required configuration is present
        if not all([self.homeserver, self.user_id, self.password]):
            return {
                "success": False,
                "error": "Missing required Matrix configuration (homeserver, user_id, or password)"
            }

        temp_client = None
        try:
            logger.debug(f"MatrixObserver: Testing connection to {self.homeserver} for user {self.user_id}")
            
            # Create a temporary client for the test
            temp_client = AsyncClient(self.homeserver, self.user_id)
            
            # Create a temporary auth handler
            temp_auth_handler = MatrixAuthHandler(
                str(self.homeserver), str(self.user_id), str(self.password), self.store_path
            )

            # Attempt to login to test credentials
            access_token = await temp_auth_handler.login_with_retry(temp_client)

            if access_token:
                logger.debug(f"MatrixObserver: Connection test successful for {self.user_id}")
                return {
                    "success": True, 
                    "message": f"Successfully connected to {self.homeserver} as {self.user_id}"
                }
            else:
                error_message = "Failed to authenticate with provided credentials"
                logger.error(f"MatrixObserver: Connection test failed - {error_message}")
                return {"success": False, "error": error_message}

        except Exception as e:
            error_message = f"Connection test failed: {str(e)}"
            logger.error(f"MatrixObserver: {error_message}", exc_info=True)
            return {"success": False, "error": error_message}
        
        finally:
            if temp_client:
                try:
                    await temp_client.close()
                except Exception as e:
                    logger.warning(f"MatrixObserver: Error closing test client: {e}")

    async def _register_room_with_world_state(self, room_id: str, room_details: Dict[str, Any]):
        """Register a room with the world state manager."""
        if not self.world_state:
            return
            
        try:
            # Use add_channel instead of update_channel
            self.world_state.add_channel(
                channel_or_id=room_id,
                channel_type="matrix",
                name=room_details.get("name", room_id),
                status=room_details.get("status", "active")
            )
        except Exception as e:
            logger.error(f"MatrixObserver: Error registering room {room_id} with world state: {e}")

    async def get_status(self) -> Dict[str, Any]:
        """Get detailed status information."""
        base_status = await super().get_status()
        
        # Add component-specific status
        matrix_status = {
            "client_connected": self.client is not None,
            "sync_running": self.sync_task is not None and not self.sync_task.done(),
            "monitored_channels": len(self.channels_to_monitor),
        }
        
        if self.encryption_handler:
            matrix_status["failed_decryptions"] = len(self.encryption_handler.failed_decryption_events)
            matrix_status["pending_key_retries"] = len(self.encryption_handler.key_request_retries)

        base_status.update(matrix_status)
        return base_status
