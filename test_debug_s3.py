#!/usr/bin/env python3
"""
Debug test to see what parameters are being passed to S3 service
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from nio import RoomMessageImage, MatrixRoom
from chatbot.integrations.matrix.observer import MatrixObserver
from chatbot.core.world_state import WorldStateManager
from chatbot.tools.s3_service import s3_service


@pytest.mark.asyncio
async def test_debug_s3_call():
    """Debug test to see S3 service call parameters."""
    # Create mocks
    mock_world_state = MagicMock(spec=WorldStateManager)
    mock_world_state.state = MagicMock()
    mock_world_state.state.channels = {}
    
    matrix_observer = MatrixObserver(mock_world_state)
    matrix_observer.client = AsyncMock()
    matrix_observer.user_id = "@test:example.com"
    
    mock_room = MagicMock(spec=MatrixRoom)
    mock_room.room_id = "!test:example.com"
    mock_room.display_name = "Test Room"
    mock_room.users = {}
    mock_room.member_count = 2
    mock_room.canonical_alias = None
    mock_room.encrypted = False
    
    mock_image_event = MagicMock(spec=RoomMessageImage)
    mock_image_event.event_id = "test_event_123"
    mock_image_event.sender = "@sender:example.com"
    mock_image_event.url = "mxc://example.com/image123"
    mock_image_event.body = "test_image.jpg"
    
    # Mock Matrix client response
    matrix_observer.client.mxc_to_http.return_value = "https://matrix.example.com/_matrix/media/r0/download/example.com/image123"
    matrix_observer.client.access_token = "test_token"
    
    # Debug mock for S3 service
    def debug_s3_upload(*args, **kwargs):
        print(f"S3 upload called with args: {args}")
        print(f"S3 upload called with kwargs: {kwargs}")
        return "https://cloudfront.example.com/public_image.jpg"
    
    with patch.object(s3_service, 'upload_image_from_url', side_effect=debug_s3_upload):
        await matrix_observer._on_message(mock_room, mock_image_event)


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_debug_s3_call())
