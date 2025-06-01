#!/usr/bin/env python3
"""
Test Matrix S3 Integration

Tests for the Matrix observer S3 integration that uploads Matrix images to public URLs.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from nio import RoomMessageImage, MatrixRoom
from chatbot.integrations.matrix.observer import MatrixObserver
from chatbot.core.world_state import WorldStateManager
from chatbot.tools.s3_service import s3_service


class TestMatrixS3Integration:
    """Test Matrix Observer S3 integration."""

    @pytest.fixture
    def mock_world_state(self):
        """Create a mock world state manager."""
        world_state = MagicMock(spec=WorldStateManager)
        world_state.state = MagicMock()
        world_state.state.channels = {}
        return world_state

    @pytest.fixture
    def matrix_observer(self, mock_world_state):
        """Create a MatrixObserver instance for testing."""
        observer = MatrixObserver(mock_world_state)
        observer.client = AsyncMock()
        observer.user_id = "@test:example.com"
        return observer

    @pytest.fixture
    def mock_room(self):
        """Create a mock Matrix room."""
        room = MagicMock(spec=MatrixRoom)
        room.room_id = "!test:example.com"
        room.display_name = "Test Room"
        room.users = {}  # Empty users dict
        room.member_count = 2
        room.canonical_alias = None
        room.encrypted = False
        return room

    @pytest.fixture
    def mock_image_event(self):
        """Create a mock RoomMessageImage event."""
        event = MagicMock(spec=RoomMessageImage)
        event.event_id = "test_event_123"
        event.sender = "@sender:example.com"
        event.url = "mxc://example.com/image123"
        event.body = "test_image.jpg"
        return event

    @pytest.mark.asyncio
    async def test_matrix_image_s3_upload_success(self, matrix_observer, mock_room, mock_image_event):
        """Test successful Matrix image upload to S3."""
        # Mock Matrix client download response
        mock_download_response = MagicMock()
        mock_download_response.body = b"fake_image_data"
        matrix_observer.client.download.return_value = mock_download_response
        matrix_observer.client.mxc_to_http.return_value = "https://matrix.example.com/_matrix/media/r0/download/example.com/image123"
        
        # Mock S3 service upload
        with patch.object(s3_service, 'upload_image_data') as mock_s3_upload:
            mock_s3_upload.return_value = "https://cloudfront.example.com/public_image.jpg"
            
            # Process the message
            await matrix_observer._on_message(mock_room, mock_image_event)
            
            # Verify S3 upload was called with correct parameters
            mock_s3_upload.assert_called_once()
            call_args = mock_s3_upload.call_args
            
            # Check image data argument
            assert call_args[0][0] == b"fake_image_data"
            # Check filename argument  
            assert call_args[0][1] == "test_image.jpg"
            
            # Verify world state was updated with the S3 URL
            matrix_observer.world_state.add_message.assert_called_once()
            added_message = matrix_observer.world_state.add_message.call_args[0][1]
            assert added_message.image_urls == ["https://cloudfront.example.com/public_image.jpg"]

    @pytest.mark.asyncio
    async def test_matrix_image_s3_upload_failure_fallback(self, matrix_observer, mock_room, mock_image_event):
        """Test Matrix image S3 upload failure with fallback to Matrix URL."""
        # Mock Matrix client download response
        mock_download_response = MagicMock()
        mock_download_response.body = b"fake_image_data"
        matrix_observer.client.download.return_value = mock_download_response
        
        # Mock Matrix client URL conversion for fallback
        matrix_url = "https://matrix.example.com/_matrix/media/r0/download/example.com/image123"
        matrix_observer.client.mxc_to_http.return_value = matrix_url
        
        # Mock S3 service upload failure
        with patch.object(s3_service, 'upload_image_data') as mock_s3_upload:
            mock_s3_upload.return_value = None  # Simulate upload failure
            
            # Process the message
            await matrix_observer._on_message(mock_room, mock_image_event)
            
            # Verify S3 upload was attempted
            mock_s3_upload.assert_called_once()
            
            # Verify world state was updated with the original Matrix URL as fallback
            matrix_observer.world_state.add_message.assert_called_once()
            added_message = matrix_observer.world_state.add_message.call_args[0][1]
            assert added_message.image_urls == [matrix_url]

    @pytest.mark.asyncio
    async def test_matrix_image_mxc_conversion_failure(self, matrix_observer, mock_room, mock_image_event):
        """Test handling of MXC to HTTP conversion failure."""
        # Mock Matrix client MXC conversion failure
        matrix_observer.client.mxc_to_http.return_value = None
        
        # Process the message
        await matrix_observer._on_message(mock_room, mock_image_event)
        
        # Verify world state was updated with no image URLs
        matrix_observer.world_state.add_message.assert_called_once()
        added_message = matrix_observer.world_state.add_message.call_args[0][1]
        assert added_message.image_urls is None or added_message.image_urls == []

    @pytest.mark.asyncio
    async def test_matrix_image_nio_client_download(self, matrix_observer, mock_room, mock_image_event):
        """Test that nio client download method is used for Matrix media access."""
        # Mock nio client download to return binary data
        mock_download_response = MagicMock()
        mock_download_response.body = b"fake_image_data"
        mock_download_response.content_type = "image/jpeg"
        matrix_observer.client.download.return_value = mock_download_response
        
        # Mock S3 service to return a successful upload
        with patch.object(s3_service, 'upload_image_data', return_value="https://cloudfront.example.com/uploaded.jpg"):
            # Process the message
            await matrix_observer._on_message(mock_room, mock_image_event)
            
            # Verify that nio client download was called with the MXC URI
            matrix_observer.client.download.assert_called_once_with("mxc://example.com/image123")
            
            # Verify world state was updated with the S3 URL
            matrix_observer.world_state.add_message.assert_called_once()
            added_message = matrix_observer.world_state.add_message.call_args[0][1]
            assert added_message.image_urls == ["https://cloudfront.example.com/uploaded.jpg"]
