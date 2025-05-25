import pytest
import pytest_asyncio
import asyncio
import uuid
import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

from message_bus import MessageBus
from image_cache_service import ImageCacheService
from prompt_constructor import (
    _get_s3_url_for_image,
    set_message_bus,
    build_messages_for_ai,
    current_message_bus
)
from event_definitions import (
    ImageCacheRequestEvent,
    ImageCacheResponseEvent,
    MatrixImageReceivedEvent
)
import database


class TestImageCacheIntegration:
    """Integration tests for the image cache service and prompt constructor."""

    @pytest_asyncio.fixture
    async def message_bus(self):
        """Create a real message bus for integration testing."""
        bus = MessageBus()
        yield bus
        await bus.shutdown()

    @pytest_asyncio.fixture
    async def temp_db_path(self, tmp_path):
        """Create a temporary database for testing."""
        db_file = tmp_path / "test_integration.db"
        await database.initialize_database(str(db_file))
        return str(db_file)

    @pytest_asyncio.fixture
    async def image_cache_service(self, message_bus, temp_db_path):
        """Create an ImageCacheService instance for integration testing."""
        with patch('image_cache_service.S3Service') as mock_s3_class:
            mock_s3_service = AsyncMock()
            mock_s3_service.upload_image = AsyncMock(return_value="https://s3.amazonaws.com/bucket/test_image.jpg")
            mock_s3_service.download_image = AsyncMock(return_value=b"fake_image_data")
            mock_s3_class.return_value = mock_s3_service
            
            service = ImageCacheService(message_bus, temp_db_path)
            
            # Start the service
            service_task = asyncio.create_task(service.run())
            await asyncio.sleep(0.1)  # Let service start
            
            yield service
            
            # Stop the service
            await service.stop()
            await service_task

    @pytest_asyncio.fixture
    async def mock_matrix_client(self):
        """Create a mock Matrix client for testing."""
        client = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_prompt_constructor_image_cache_integration(self, message_bus, image_cache_service, mock_matrix_client):
        """Test full integration between prompt constructor and image cache service."""
        # Set up the image cache service with Matrix client
        image_cache_service.set_matrix_client(mock_matrix_client)
        
        # Set up the prompt constructor with message bus
        set_message_bus(message_bus)
        
        # Mock Matrix media download
        with patch('image_cache_service.MatrixMediaUtils.download_media_simple', new_callable=AsyncMock) as mock_download:
            mock_download.return_value = b"fake_image_data"
            
            # Test image URL processing through prompt constructor
            image_url = "mxc://example.org/mediaId123"
            
            # Request S3 URL through prompt constructor
            s3_url = await _get_s3_url_for_image(image_url, message_bus)
            
            # Verify we got a valid S3 URL
            assert s3_url == "https://s3.amazonaws.com/bucket/test_image.jpg"
            
            # Verify the image was cached in database
            cache_key = hashlib.sha256(image_url.encode()).hexdigest()
            cached_result = await database.get_image_cache(image_cache_service.db_path, cache_key)
            assert cached_result is not None
            assert cached_result[1] == image_url
            assert cached_result[2] == s3_url

    @pytest.mark.asyncio
    async def test_prompt_constructor_cached_image(self, message_bus, image_cache_service, temp_db_path):
        """Test that prompt constructor uses cached images efficiently."""
        # Set up the prompt constructor with message bus
        set_message_bus(message_bus)
        
        # Pre-cache an image in the database
        image_url = "mxc://example.org/cached_image"
        cached_s3_url = "https://s3.amazonaws.com/bucket/cached_image.jpg"
        cache_key = hashlib.sha256(image_url.encode()).hexdigest()
        
        await database.store_image_cache(temp_db_path, cache_key, image_url, cached_s3_url)
        
        # Request the cached image through prompt constructor
        result_s3_url = await _get_s3_url_for_image(image_url, message_bus)
        
        # Verify we got the cached URL without any processing
        assert result_s3_url == cached_s3_url
        
        # Verify no S3 upload was attempted (since it was cached)
        assert not image_cache_service.s3_service.upload_image.called

    @pytest.mark.asyncio
    async def test_build_messages_with_images(self, message_bus, image_cache_service, mock_matrix_client):
        """Test building messages with images using the new architecture."""
        # Set up services
        image_cache_service.set_matrix_client(mock_matrix_client)
        set_message_bus(message_bus)
        
        # Mock Matrix media download
        with patch('image_cache_service.MatrixMediaUtils.download_media_simple', new_callable=AsyncMock) as mock_download:
            mock_download.return_value = b"fake_image_data"
            
            # Create a batch of user inputs with an image
            batched_inputs = [
                {
                    "name": "TestUser",
                    "content": "Look at this image!",
                    "image_url": "mxc://example.org/testImage"
                }
            ]
            
            # Build messages for AI
            messages = await build_messages_for_ai(
                historical_messages=[],
                current_batched_user_inputs=batched_inputs,
                bot_display_name="TestBot",
                db_path=image_cache_service.db_path,
                include_system_prompt=False  # Skip system prompt for simpler test
            )
            
            # Verify the message structure
            assert len(messages) == 1
            user_message = messages[0]
            assert user_message["role"] == "user"
            assert user_message["name"] == "TestUser"
            
            # Verify content is structured for vision
            content = user_message["content"]
            assert isinstance(content, list)
            assert len(content) == 2  # Text + image
            
            # Check text content
            text_part = content[0]
            assert text_part["type"] == "text"
            assert text_part["text"] == "Look at this image!"
            
            # Check image content
            image_part = content[1]
            assert image_part["type"] == "image_url"
            assert image_part["image_url"]["url"] == "https://s3.amazonaws.com/bucket/test_image.jpg"

    @pytest.mark.asyncio
    async def test_auto_cache_matrix_images(self, message_bus, image_cache_service, mock_matrix_client):
        """Test automatic caching of Matrix images when received."""
        # Set up the image cache service
        image_cache_service.set_matrix_client(mock_matrix_client)
        
        # Mock Matrix media download
        with patch('image_cache_service.MatrixMediaUtils.download_media_simple', new_callable=AsyncMock) as mock_download:
            mock_download.return_value = b"fake_image_data"
            
            # Create a Matrix image received event
            matrix_event = MatrixImageReceivedEvent(
                room_id="!room:example.org",
                event_id_matrix="$event123",
                sender_id="@user:example.org",
                sender_display_name="User",
                room_display_name="Test Room",
                image_url="mxc://example.org/autoCache"
            )
            
            # Publish the event to trigger auto-caching
            await message_bus.publish(matrix_event)
            
            # Give some time for background processing
            await asyncio.sleep(0.5)
            
            # Verify the image was cached
            cache_key = hashlib.sha256("mxc://example.org/autoCache".encode()).hexdigest()
            cached_result = await database.get_image_cache(image_cache_service.db_path, cache_key)
            assert cached_result is not None
            assert cached_result[1] == "mxc://example.org/autoCache"
            assert cached_result[2] == "https://s3.amazonaws.com/bucket/test_image.jpg"

    @pytest.mark.asyncio
    async def test_image_cache_error_handling(self, message_bus, image_cache_service):
        """Test error handling in image cache service."""
        # Set up the prompt constructor with message bus
        set_message_bus(message_bus)
        
        # Test with invalid URL that will fail download
        invalid_url = "mxc://invalid.server/nonexistent"
        
        # Mock download to return None (failure)
        with patch.object(image_cache_service, '_download_image_data', new_callable=AsyncMock) as mock_download:
            mock_download.return_value = None
            
            # Request processing of invalid image
            result = await _get_s3_url_for_image(invalid_url, message_bus)
            
            # Verify we get None for failed processing
            assert result is None

    @pytest.mark.asyncio
    async def test_timeout_handling(self, message_bus, image_cache_service):
        """Test timeout handling in prompt constructor."""
        # Set up the prompt constructor with message bus
        set_message_bus(message_bus)
        
        # Mock the image cache service to not respond
        with patch.object(image_cache_service, '_handle_image_cache_request') as mock_handler:
            # Make the handler not respond to simulate timeout
            mock_handler.return_value = None
            
            # Request with a very short timeout
            image_url = "mxc://example.org/timeout_test"
            
            with patch('prompt_constructor.asyncio.wait_for', side_effect=asyncio.TimeoutError):
                result = await _get_s3_url_for_image(image_url, message_bus)
                
                # Verify timeout is handled gracefully
                assert result is None

    @pytest.mark.asyncio
    async def test_http_image_processing(self, message_bus, image_cache_service):
        """Test processing of HTTP images through the cache service."""
        # Set up the prompt constructor with message bus
        set_message_bus(message_bus)
        
        # Test with HTTP URL
        http_url = "https://example.com/test_image.jpg"
        
        # Request S3 URL for HTTP image
        s3_url = await _get_s3_url_for_image(http_url, message_bus)
        
        # Verify we got a valid S3 URL
        assert s3_url == "https://s3.amazonaws.com/bucket/test_image.jpg"
        
        # Verify the S3 service download_image was called for HTTP
        image_cache_service.s3_service.download_image.assert_called_with(http_url)

    @pytest.mark.asyncio
    async def test_message_bus_cleanup(self, message_bus, image_cache_service):
        """Test that message bus subscriptions are cleaned up properly."""
        # Set up the prompt constructor with message bus
        set_message_bus(message_bus)
        
        # Make a request to establish subscriptions
        image_url = "mxc://example.org/cleanup_test"
        
        # Count initial subscribers
        initial_subscribers = len(message_bus._subscribers.get(ImageCacheResponseEvent.get_event_type(), []))
        
        # Make the request (this creates temporary subscription)
        with patch.object(image_cache_service, 'process_image_for_s3', new_callable=AsyncMock) as mock_process:
            mock_process.return_value = "https://s3.amazonaws.com/bucket/cleanup_test.jpg"
            
            result = await _get_s3_url_for_image(image_url, message_bus)
            
            # Verify request succeeded
            assert result is not None
        
        # Verify no lingering subscriptions (should be cleaned up)
        final_subscribers = len(message_bus._subscribers.get(ImageCacheResponseEvent.get_event_type(), []))
        assert final_subscribers == initial_subscribers  # Should be back to original count


class TestArchitecturalDecoupling:
    """Tests to verify the architectural decoupling is working correctly."""

    @pytest.mark.asyncio
    async def test_prompt_constructor_no_matrix_dependency(self):
        """Test that prompt constructor doesn't directly depend on Matrix client."""
        # This test verifies the refactoring removed tight coupling
        
        # Create a mock message bus
        mock_bus = MagicMock(spec=MessageBus)
        mock_bus.subscribe = MagicMock()
        mock_bus.unsubscribe = MagicMock()
        mock_bus.publish = AsyncMock()
        
        # Set up prompt constructor with message bus
        set_message_bus(mock_bus)
        
        # Verify the global reference is set correctly
        import prompt_constructor
        assert prompt_constructor.current_message_bus == mock_bus
        
        # Verify no direct Matrix client imports in prompt constructor
        import inspect
        prompt_constructor_source = inspect.getsource(prompt_constructor)
        
        # These should not appear in the source anymore
        assert "AsyncClient" not in prompt_constructor_source
        assert "matrix_client" not in prompt_constructor_source.replace("current_message_bus", "")
        assert "MatrixGatewayService" not in prompt_constructor_source

    @pytest.mark.asyncio
    async def test_image_cache_service_independence(self):
        """Test that ImageCacheService can work independently."""
        with patch('image_cache_service.S3Service') as mock_s3_class:
            mock_s3_service = AsyncMock()
            mock_s3_class.return_value = mock_s3_service
            
            # Create image cache service with minimal dependencies
            mock_bus = MagicMock(spec=MessageBus)
            temp_db = ":memory:"  # In-memory SQLite for testing
            
            await database.initialize_database(temp_db)
            
            service = ImageCacheService(mock_bus, temp_db)
            
            # Verify it initializes without Matrix client
            assert service._matrix_client is None
            assert service.s3_service is not None
            
            # Verify it can process HTTP images without Matrix client
            with patch.object(service, '_download_image_data', new_callable=AsyncMock) as mock_download:
                mock_download.return_value = b"test_data"
                mock_s3_service.upload_image.return_value = "https://s3.amazonaws.com/test.jpg"
                
                result = await service.process_image_for_s3("https://example.com/test.jpg")
                assert result == "https://s3.amazonaws.com/test.jpg"

    @pytest.mark.asyncio
    async def test_event_driven_communication(self):
        """Test that services communicate through events, not direct calls."""
        mock_bus = MagicMock(spec=MessageBus)
        mock_bus.publish = AsyncMock()
        
        # Create image cache service
        with patch('image_cache_service.S3Service'):
            service = ImageCacheService(mock_bus, ":memory:")
        
        # Create a request event
        request_event = ImageCacheRequestEvent(
            request_id="test-123",
            image_url="mxc://example.org/test"
        )
        
        # Mock the processing to return a result
        with patch.object(service, 'process_image_for_s3', new_callable=AsyncMock) as mock_process:
            mock_process.return_value = "https://s3.amazonaws.com/result.jpg"
            
            # Handle the request
            await service._handle_image_cache_request(request_event)
            
            # Verify response event was published
            mock_bus.publish.assert_called_once()
            published_event = mock_bus.publish.call_args[0][0]
            assert isinstance(published_event, ImageCacheResponseEvent)
            assert published_event.request_id == "test-123"
            assert published_event.success is True