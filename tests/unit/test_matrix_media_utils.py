"""Tests for MatrixMediaUtils."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from matrix_media_utils import MatrixMediaUtils


@pytest.mark.unit
class TestMatrixMediaUtils:
    """Test MatrixMediaUtils functionality."""

    @pytest.mark.asyncio
    async def test_download_media_simple_success(self):
        """Test successful media download."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.body = b"test image data"
        mock_client.download.return_value = mock_response
        
        result = await MatrixMediaUtils.download_media_simple(
            "mxc://matrix.org/test123",
            mock_client
        )
        
        assert result == b"test image data"
        mock_client.download.assert_called_once_with("mxc://matrix.org/test123")

    @pytest.mark.asyncio
    async def test_download_media_simple_invalid_mxc_url(self):
        """Test download with invalid MXC URL."""
        mock_client = AsyncMock()
        
        # Test non-mxc URL
        result = await MatrixMediaUtils.download_media_simple(
            "https://example.com/image.jpg",
            mock_client
        )
        assert result is None
        mock_client.download.assert_not_called()
        
        # Test empty URL
        result = await MatrixMediaUtils.download_media_simple("", mock_client)
        assert result is None
        
        # Test None URL
        result = await MatrixMediaUtils.download_media_simple(None, mock_client)
        assert result is None

    @pytest.mark.asyncio
    async def test_download_media_simple_no_client(self):
        """Test download without matrix client."""
        result = await MatrixMediaUtils.download_media_simple(
            "mxc://matrix.org/test123",
            None
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_download_media_simple_empty_response(self):
        """Test download with empty response body."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.body = None
        mock_client.download.return_value = mock_response
        
        result = await MatrixMediaUtils.download_media_simple(
            "mxc://matrix.org/test123",
            mock_client
        )
        
        assert result is None

    @pytest.mark.asyncio
    async def test_download_media_simple_no_response(self):
        """Test download with no response object."""
        mock_client = AsyncMock()
        mock_client.download.return_value = None
        
        result = await MatrixMediaUtils.download_media_simple(
            "mxc://matrix.org/test123",
            mock_client
        )
        
        assert result is None

    @pytest.mark.asyncio
    async def test_download_media_simple_exception(self):
        """Test download with exception."""
        mock_client = AsyncMock()
        mock_client.download.side_effect = Exception("Network error")
        
        result = await MatrixMediaUtils.download_media_simple(
            "mxc://matrix.org/test123",
            mock_client
        )
        
        assert result is None

    @pytest.mark.asyncio
    async def test_download_media_simple_large_file(self):
        """Test download of large file."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        # Simulate a large file (1MB)
        large_data = b"x" * (1024 * 1024)
        mock_response.body = large_data
        mock_client.download.return_value = mock_response
        
        result = await MatrixMediaUtils.download_media_simple(
            "mxc://matrix.org/largefile",
            mock_client
        )
        
        assert result == large_data
        assert len(result) == 1024 * 1024

    @pytest.mark.asyncio
    async def test_download_media_simple_various_mxc_formats(self):
        """Test download with various valid MXC URL formats."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.body = b"test data"
        mock_client.download.return_value = mock_response
        
        valid_urls = [
            "mxc://matrix.org/test123",
            "mxc://example.com/media456",
            "mxc://sub.domain.com/file789"
        ]
        
        for url in valid_urls:
            result = await MatrixMediaUtils.download_media_simple(url, mock_client)
            assert result == b"test data"
        
        assert mock_client.download.call_count == len(valid_urls)