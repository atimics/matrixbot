#!/usr/bin/env python3
"""
Test Matrix Arweave Integration

Tests for the Matrix observer Arweave integration that uploads Matrix images to public URLs.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from nio import RoomMessageImage, MatrixRoom
from chatbot.integrations.matrix.observer import MatrixObserver
from chatbot.core.world_state import WorldStateManager
from chatbot.tools.arweave_service import arweave_service


class TestMatrixArweaveIntegration:
    """Test Matrix Observer Arweave integration."""

    @pytest.fixture
    def mock_world_state(self):
        """Create a mock world state manager."""
        mock_world_state = MagicMock(spec=WorldStateManager)
        mock_state = MagicMock()
        mock_state.channels = {}
        mock_world_state.state = mock_state
        return mock_world_state

    @pytest.fixture
    def mock_arweave_client(self):
        """Create a mock Arweave client."""
        mock_client = AsyncMock()
        mock_client.upload_data = AsyncMock(return_value="test_tx_id")
        mock_client.get_arweave_url.return_value = "https://arweave.net/test_tx_id"
        return mock_client

    @pytest.fixture
    def matrix_observer(self, mock_world_state, mock_arweave_client):
        """Create a Matrix observer with mocked dependencies."""
        observer = MatrixObserver(mock_world_state, mock_arweave_client)
        observer.client = AsyncMock()
        observer.user_id = "@testbot:example.com"  # Set bot user ID different from test message sender
        return observer

    def _create_mock_room(self, room_id="!test:example.com", display_name="Test Room"):
        """Create a properly mocked Matrix room object."""
        mock_room = MagicMock(spec=MatrixRoom)
        mock_room.room_id = room_id
        mock_room.display_name = display_name
        mock_room.name = display_name
        mock_room.canonical_alias = f"#test:example.com"
        mock_room.alt_aliases = []
        mock_room.topic = "Test topic"
        mock_room.avatar = None
        mock_room.member_count = 5
        mock_room.encrypted = False
        mock_room.join_rule = "invite"
        mock_room.users = {"@test1:example.com": MagicMock(), "@test2:example.com": MagicMock()}
        mock_room.power_levels = MagicMock()
        mock_room.power_levels.users = {"@test1:example.com": 50}
        mock_room.creation_time = None
        return mock_room

    def _create_mock_message(self, sender="@test:example.com", body="test_image.jpg", 
                           url="mxc://example.com/test123", mimetype="image/jpeg"):
        """Create a mock image message."""
        mock_message = MagicMock(spec=RoomMessageImage)
        mock_message.sender = sender
        mock_message.body = body
        mock_message.url = url
        mock_message.mimetype = mimetype
        mock_message.event_id = "$test_event_id"
        return mock_message

    @pytest.mark.asyncio
    async def test_image_message_processing_with_arweave(self, matrix_observer, mock_arweave_client):
        """Test that image messages are processed and uploaded to Arweave."""
        # Create a mock image message
        mock_room = self._create_mock_room()
        mock_message = self._create_mock_message()

        # Mock the matrix client download response
        mock_download_response = MagicMock()
        mock_download_response.body = b"fake_image_data"
        mock_download_response.content_type = "image/jpeg"
        matrix_observer.client.download = AsyncMock(return_value=mock_download_response)
        matrix_observer.client.access_token = "fake_token"  # Make client authenticated

        # Mock arweave client methods
        mock_arweave_client.upload_data.return_value = "test_tx_id"
        mock_arweave_client.get_arweave_url.return_value = "https://arweave.net/test_tx_id"

        # Process the message
        await matrix_observer._on_message(mock_room, mock_message)

        # Verify Arweave upload was called
        mock_arweave_client.upload_data.assert_called_once()
        args, kwargs = mock_arweave_client.upload_data.call_args
        assert args[0] == b"fake_image_data"  # image data
        assert args[1] == "image/jpeg"  # content type

    @pytest.mark.asyncio
    async def test_image_message_processing_no_arweave_service(self, matrix_observer):
        """Test image message processing when Arweave service is not available."""
        # Create a mock image message
        mock_room = self._create_mock_room()
        mock_message = self._create_mock_message()

        # Mock the matrix client download response
        mock_download_response = MagicMock()
        mock_download_response.body = b"fake_image_data"
        matrix_observer.client.download.return_value = mock_download_response

        # Mock arweave service to not be configured
        with patch.object(arweave_service, 'is_configured') as mock_configured:
            mock_configured.return_value = False

            # Process the message - should not raise error
            await matrix_observer._on_message(mock_room, mock_message)

    @pytest.mark.asyncio
    async def test_image_message_processing_upload_failure(self, matrix_observer):
        """Test image message processing when Arweave upload fails."""
        # Create a mock image message
        mock_room = self._create_mock_room()
        mock_message = self._create_mock_message()

        # Mock the matrix client download response
        mock_download_response = MagicMock()
        mock_download_response.body = b"fake_image_data"
        matrix_observer.client.download.return_value = mock_download_response

        # Mock arweave service upload to fail
        with patch.object(arweave_service, 'upload_image_data', new_callable=AsyncMock) as mock_upload:
            mock_upload.return_value = None  # Upload failed

            # Process the message - should handle failure gracefully
            await matrix_observer._on_message(mock_room, mock_message)

    @pytest.mark.asyncio
    async def test_image_message_processing_download_failure(self, matrix_observer):
        """Test image message processing when Matrix download fails."""
        # Create a mock image message
        mock_room = self._create_mock_room()
        mock_message = self._create_mock_message()

        # Mock the matrix client download to fail
        matrix_observer.client.download.return_value = None

        # Process the message - should handle failure gracefully
        await matrix_observer._on_message(mock_room, mock_message)

        # Verify no Arweave upload was attempted
        with patch.object(arweave_service, 'upload_image_data') as mock_upload:
            mock_upload.assert_not_called()
