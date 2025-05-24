import pytest
import pytest_asyncio
import asyncio
import os
import tempfile
import uuid
import hashlib
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from typing import Optional

from message_bus import MessageBus
from image_cache_service import ImageCacheService
from event_definitions import (
    ImageCacheRequestEvent,
    ImageCacheResponseEvent,
    MatrixImageReceivedEvent
)
import database


class TestImageCacheService:
    """Unit tests for ImageCacheService."""

    @pytest_asyncio.fixture
    async def mock_message_bus(self):
        """Create a mock message bus."""
        bus = MagicMock(spec=MessageBus)
        bus.publish = AsyncMock()
        bus.subscribe = MagicMock()
        bus.unsubscribe = MagicMock()
        return bus

    @pytest_asyncio.fixture
    async def temp_db_path(self, tmp_path):
        """Create a temporary database for testing."""
        db_file = tmp_path / "test_image_cache.db"
        await database.initialize_database(str(db_file))
        return str(db_file)

    @pytest_asyncio.fixture
    async def image_cache_service(self, mock_message_bus, temp_db_path):
        """Create an ImageCacheService instance for testing."""
        with patch('image_cache_service.S3Service') as mock_s3_class:
            mock_s3_service = AsyncMock()
            mock_s3_class.return_value = mock_s3_service
            
            service = ImageCacheService(mock_message_bus, temp_db_path)
            service.s3_service = mock_s3_service
            yield service

    @pytest_asyncio.fixture
    async def mock_matrix_client(self):
        """Create a mock Matrix client."""
        client = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_initialization_with_s3_success(self, mock_message_bus, temp_db_path):
        """Test successful initialization with S3 service."""
        with patch('image_cache_service.S3Service') as mock_s3_class:
            mock_s3_service = AsyncMock()
            mock_s3_class.return_value = mock_s3_service
            
            service = ImageCacheService(mock_message_bus, temp_db_path)
            
            assert service.bus == mock_message_bus
            assert service.db_path == temp_db_path
            assert service.s3_service == mock_s3_service
            assert service._matrix_client is None

    @pytest.mark.asyncio
    async def test_initialization_with_s3_failure(self, mock_message_bus, temp_db_path):
        """Test initialization when S3 service fails to initialize."""
        with patch('image_cache_service.S3Service', side_effect=Exception("S3 init failed")):
            service = ImageCacheService(mock_message_bus, temp_db_path)
            
            assert service.s3_service is None

    @pytest.mark.asyncio
    async def test_set_matrix_client(self, image_cache_service, mock_matrix_client):
        """Test setting the Matrix client reference."""
        image_cache_service.set_matrix_client(mock_matrix_client)
        
        assert image_cache_service._matrix_client == mock_matrix_client

    @pytest.mark.asyncio
    async def test_generate_cache_key(self, image_cache_service):
        """Test cache key generation."""
        url = "mxc://example.org/mediaId123"
        expected_key = hashlib.sha256(url.encode()).hexdigest()
        
        cache_key = await image_cache_service._generate_cache_key(url)
        
        assert cache_key == expected_key
        assert len(cache_key) == 64  # SHA256 hex digest length

    @pytest.mark.asyncio
    async def test_download_mxc_image_success(self, image_cache_service, mock_matrix_client):
        """Test successful MXC image download."""
        image_cache_service.set_matrix_client(mock_matrix_client)
        mxc_url = "mxc://example.org/mediaId123"
        test_data = b"fake_image_data"
        
        with patch('image_cache_service.MatrixMediaUtils.download_media_simple', new_callable=AsyncMock) as mock_download:
            mock_download.return_value = test_data
            
            result = await image_cache_service._download_image_data(mxc_url)
            
            assert result == test_data
            mock_download.assert_called_once_with(mxc_url, mock_matrix_client)

    @pytest.mark.asyncio
    async def test_download_mxc_image_no_client(self, image_cache_service):
        """Test MXC image download when no Matrix client is available."""
        mxc_url = "mxc://example.org/mediaId123"
        
        result = await image_cache_service._download_image_data(mxc_url)
        
        assert result is None

    @pytest.mark.asyncio
    async def test_download_http_image_success(self, image_cache_service):
        """Test successful HTTP image download."""
        http_url = "https://example.com/image.jpg"
        test_data = b"fake_image_data"
        
        image_cache_service.s3_service.download_image = AsyncMock(return_value=test_data)
        
        result = await image_cache_service._download_image_data(http_url)
        
        assert result == test_data
        image_cache_service.s3_service.download_image.assert_called_once_with(http_url)

    @pytest.mark.asyncio
    async def test_download_http_image_no_s3(self, image_cache_service):
        """Test HTTP image download when S3 service is unavailable."""
        image_cache_service.s3_service = None
        http_url = "https://example.com/image.jpg"
        
        result = await image_cache_service._download_image_data(http_url)
        
        assert result is None

    @pytest.mark.asyncio
    async def test_upload_to_s3_success(self, image_cache_service):
        """Test successful S3 upload."""
        image_data = b"fake_image_data"
        original_url = "mxc://example.org/mediaId123"
        expected_s3_url = "https://s3.amazonaws.com/bucket/matrix_image_uuid.jpg"
        
        image_cache_service.s3_service.upload_image = AsyncMock(return_value=expected_s3_url)
        
        with patch('tempfile.NamedTemporaryFile') as mock_temp_file, \
             patch('os.unlink') as mock_unlink:
            
            mock_file = MagicMock()
            mock_file.__enter__ = MagicMock(return_value=mock_file)
            mock_file.__exit__ = MagicMock(return_value=None)
            mock_file.name = "/tmp/test_file.jpg"
            mock_file.write = MagicMock()
            mock_temp_file.return_value = mock_file
            
            result = await image_cache_service._upload_to_s3(image_data, original_url)
            
            assert result == expected_s3_url
            mock_file.write.assert_called_once_with(image_data)
            image_cache_service.s3_service.upload_image.assert_called_once()
            mock_unlink.assert_called_once_with("/tmp/test_file.jpg")

    @pytest.mark.asyncio
    async def test_upload_to_s3_no_s3_service(self, image_cache_service):
        """Test S3 upload when S3 service is unavailable."""
        image_cache_service.s3_service = None
        image_data = b"fake_image_data"
        original_url = "mxc://example.org/mediaId123"
        
        result = await image_cache_service._upload_to_s3(image_data, original_url)
        
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_image_success(self, image_cache_service, temp_db_path):
        """Test successful image caching to database."""
        image_url = "mxc://example.org/mediaId123"
        s3_url = "https://s3.amazonaws.com/bucket/image.jpg"
        
        with patch('database.store_image_cache', new_callable=AsyncMock) as mock_store:
            mock_store.return_value = True
            
            await image_cache_service._cache_image(image_url, s3_url)
            
            expected_cache_key = hashlib.sha256(image_url.encode()).hexdigest()
            mock_store.assert_called_once_with(temp_db_path, expected_cache_key, image_url, s3_url)

    @pytest.mark.asyncio
    async def test_get_cached_image_success(self, image_cache_service, temp_db_path):
        """Test successful retrieval of cached image."""
        image_url = "mxc://example.org/mediaId123"
        s3_url = "https://s3.amazonaws.com/bucket/image.jpg"
        cache_key = hashlib.sha256(image_url.encode()).hexdigest()
        
        with patch('database.get_image_cache', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = (cache_key, image_url, s3_url, 1234567890.0)
            
            result = await image_cache_service._get_cached_image(image_url)
            
            assert result == s3_url
            mock_get.assert_called_once_with(temp_db_path, cache_key)

    @pytest.mark.asyncio
    async def test_get_cached_image_not_found(self, image_cache_service, temp_db_path):
        """Test retrieval of cached image when not found."""
        image_url = "mxc://example.org/mediaId123"
        cache_key = hashlib.sha256(image_url.encode()).hexdigest()
        
        with patch('database.get_image_cache', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None
            
            result = await image_cache_service._get_cached_image(image_url)
            
            assert result is None
            mock_get.assert_called_once_with(temp_db_path, cache_key)

    @pytest.mark.asyncio
    async def test_process_image_for_s3_cached(self, image_cache_service):
        """Test processing image that's already cached."""
        image_url = "mxc://example.org/mediaId123"
        cached_s3_url = "https://s3.amazonaws.com/bucket/cached_image.jpg"
        
        with patch.object(image_cache_service, '_get_cached_image', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = cached_s3_url
            
            result = await image_cache_service.process_image_for_s3(image_url)
            
            assert result == cached_s3_url
            mock_get.assert_called_once_with(image_url)

    @pytest.mark.asyncio
    async def test_process_image_for_s3_full_flow(self, image_cache_service, mock_matrix_client):
        """Test full image processing flow for uncached image."""
        image_cache_service.set_matrix_client(mock_matrix_client)
        image_url = "mxc://example.org/mediaId123"
        image_data = b"fake_image_data"
        s3_url = "https://s3.amazonaws.com/bucket/new_image.jpg"
        
        with patch.object(image_cache_service, '_get_cached_image', new_callable=AsyncMock) as mock_get_cached, \
             patch.object(image_cache_service, '_download_image_data', new_callable=AsyncMock) as mock_download, \
             patch.object(image_cache_service, '_upload_to_s3', new_callable=AsyncMock) as mock_upload, \
             patch.object(image_cache_service, '_cache_image', new_callable=AsyncMock) as mock_cache:
            
            mock_get_cached.return_value = None
            mock_download.return_value = image_data
            mock_upload.return_value = s3_url
            
            result = await image_cache_service.process_image_for_s3(image_url)
            
            assert result == s3_url
            mock_get_cached.assert_called_once_with(image_url)
            mock_download.assert_called_once_with(image_url)
            mock_upload.assert_called_once_with(image_data, image_url)
            mock_cache.assert_called_once_with(image_url, s3_url)

    @pytest.mark.asyncio
    async def test_process_image_for_s3_download_failure(self, image_cache_service):
        """Test image processing when download fails."""
        image_url = "mxc://example.org/mediaId123"
        
        with patch.object(image_cache_service, '_get_cached_image', new_callable=AsyncMock) as mock_get_cached, \
             patch.object(image_cache_service, '_download_image_data', new_callable=AsyncMock) as mock_download:
            
            mock_get_cached.return_value = None
            mock_download.return_value = None
            
            result = await image_cache_service.process_image_for_s3(image_url)
            
            assert result is None

    @pytest.mark.asyncio
    async def test_handle_image_cache_request(self, image_cache_service, mock_message_bus):
        """Test handling of image cache request event."""
        request_id = str(uuid.uuid4())
        image_url = "mxc://example.org/mediaId123"
        s3_url = "https://s3.amazonaws.com/bucket/image.jpg"
        
        request_event = ImageCacheRequestEvent(
            request_id=request_id,
            image_url=image_url
        )
        
        with patch.object(image_cache_service, 'process_image_for_s3', new_callable=AsyncMock) as mock_process:
            mock_process.return_value = s3_url
            
            await image_cache_service._handle_image_cache_request(request_event)
            
            mock_process.assert_called_once_with(image_url)
            
            # Verify response was published
            mock_message_bus.publish.assert_called_once()
            published_event = mock_message_bus.publish.call_args[0][0]
            assert isinstance(published_event, ImageCacheResponseEvent)
            assert published_event.request_id == request_id
            assert published_event.original_url == image_url
            assert published_event.s3_url == s3_url
            assert published_event.success is True

    @pytest.mark.asyncio
    async def test_handle_image_cache_request_failure(self, image_cache_service, mock_message_bus):
        """Test handling of image cache request when processing fails."""
        request_id = str(uuid.uuid4())
        image_url = "mxc://example.org/mediaId123"
        
        request_event = ImageCacheRequestEvent(
            request_id=request_id,
            image_url=image_url
        )
        
        with patch.object(image_cache_service, 'process_image_for_s3', new_callable=AsyncMock) as mock_process:
            mock_process.return_value = None
            
            await image_cache_service._handle_image_cache_request(request_event)
            
            # Verify failure response was published
            mock_message_bus.publish.assert_called_once()
            published_event = mock_message_bus.publish.call_args[0][0]
            assert isinstance(published_event, ImageCacheResponseEvent)
            assert published_event.request_id == request_id
            assert published_event.original_url == image_url
            assert published_event.s3_url is None
            assert published_event.success is False

    @pytest.mark.asyncio
    async def test_handle_matrix_image_auto_cache(self, image_cache_service):
        """Test automatic caching of Matrix images."""
        matrix_event = MatrixImageReceivedEvent(
            room_id="!room:example.org",
            event_id_matrix="$event123",
            sender_id="@user:example.org",
            sender_display_name="User",
            room_display_name="Test Room",
            image_url="mxc://example.org/mediaId123"
        )
        
        with patch.object(image_cache_service, 'process_image_for_s3', new_callable=AsyncMock) as mock_process:
            with patch('asyncio.create_task') as mock_create_task:
                await image_cache_service._handle_matrix_image_auto_cache(matrix_event)
                
                mock_create_task.assert_called_once()
                # Verify that the task was created with the correct coroutine
                call_args = mock_create_task.call_args[0][0]
                assert asyncio.iscoroutine(call_args)

    @pytest.mark.asyncio
    async def test_service_lifecycle(self, image_cache_service, mock_message_bus):
        """Test service start and stop lifecycle."""
        # Mock the event subscriptions
        mock_message_bus.subscribe = MagicMock()
        
        # Create a task to run the service
        run_task = asyncio.create_task(image_cache_service.run())
        
        # Give it a moment to start
        await asyncio.sleep(0.1)
        
        # Verify subscriptions were set up
        expected_calls = [
            (ImageCacheRequestEvent.get_event_type(), image_cache_service._handle_image_cache_request),
            (MatrixImageReceivedEvent.get_event_type(), image_cache_service._handle_matrix_image_auto_cache)
        ]
        
        for expected_call in expected_calls:
            mock_message_bus.subscribe.assert_any_call(*expected_call)
        
        # Stop the service
        await image_cache_service.stop()
        
        # Wait for the run task to complete
        await run_task
        
        assert image_cache_service._stop_event.is_set()


class TestImageCacheDatabase:
    """Test the database functions for image caching."""

    @pytest_asyncio.fixture
    async def temp_db_path(self, tmp_path):
        """Create a temporary database for testing."""
        db_file = tmp_path / "test_image_cache_db.db"
        await database.initialize_database(str(db_file))
        return str(db_file)

    @pytest.mark.asyncio
    async def test_store_and_get_image_cache(self, temp_db_path):
        """Test storing and retrieving image cache data."""
        cache_key = "test_cache_key_123"
        original_url = "mxc://example.org/mediaId123"
        s3_url = "https://s3.amazonaws.com/bucket/image.jpg"
        
        # Store the cache entry
        success = await database.store_image_cache(temp_db_path, cache_key, original_url, s3_url)
        assert success is True
        
        # Retrieve the cache entry
        result = await database.get_image_cache(temp_db_path, cache_key)
        assert result is not None
        assert result[0] == cache_key
        assert result[1] == original_url
        assert result[2] == s3_url
        assert isinstance(result[3], float)  # timestamp

    @pytest.mark.asyncio
    async def test_store_image_cache_replace(self, temp_db_path):
        """Test that storing with the same cache key replaces the entry."""
        cache_key = "test_cache_key_456"
        original_url = "mxc://example.org/mediaId456"
        s3_url_1 = "https://s3.amazonaws.com/bucket/image1.jpg"
        s3_url_2 = "https://s3.amazonaws.com/bucket/image2.jpg"
        
        # Store first entry
        await database.store_image_cache(temp_db_path, cache_key, original_url, s3_url_1)
        
        # Store second entry with same key
        await database.store_image_cache(temp_db_path, cache_key, original_url, s3_url_2)
        
        # Retrieve and verify it was replaced
        result = await database.get_image_cache(temp_db_path, cache_key)
        assert result[2] == s3_url_2

    @pytest.mark.asyncio
    async def test_get_image_cache_not_found(self, temp_db_path):
        """Test retrieving non-existent cache entry."""
        result = await database.get_image_cache(temp_db_path, "nonexistent_key")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_image_cache(self, temp_db_path):
        """Test deleting image cache entry."""
        cache_key = "test_cache_key_789"
        original_url = "mxc://example.org/mediaId789"
        s3_url = "https://s3.amazonaws.com/bucket/image3.jpg"
        
        # Store the cache entry
        await database.store_image_cache(temp_db_path, cache_key, original_url, s3_url)
        
        # Verify it exists
        result = await database.get_image_cache(temp_db_path, cache_key)
        assert result is not None
        
        # Delete it
        deleted = await database.delete_image_cache(temp_db_path, cache_key)
        assert deleted is True
        
        # Verify it's gone
        result = await database.get_image_cache(temp_db_path, cache_key)
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_image_cache_not_found(self, temp_db_path):
        """Test deleting non-existent cache entry."""
        deleted = await database.delete_image_cache(temp_db_path, "nonexistent_key")
        assert deleted is False

    @pytest.mark.asyncio
    async def test_cleanup_old_image_cache(self, temp_db_path):
        """Test cleaning up old image cache entries."""
        import time
        
        # Create some cache entries with different timestamps
        current_time = time.time()
        old_time = current_time - (86400 * 31)  # 31 days ago
        
        # Store old entry
        with patch('time.time', return_value=old_time):
            await database.store_image_cache(temp_db_path, "old_key", "old_url", "old_s3")
        
        # Store recent entry
        await database.store_image_cache(temp_db_path, "new_key", "new_url", "new_s3")
        
        # Clean up entries older than 30 days
        cleaned_count = await database.cleanup_old_image_cache(temp_db_path, max_age_seconds=86400 * 30)
        assert cleaned_count == 1
        
        # Verify old entry is gone and new entry remains
        old_result = await database.get_image_cache(temp_db_path, "old_key")
        new_result = await database.get_image_cache(temp_db_path, "new_key")
        
        assert old_result is None
        assert new_result is not None