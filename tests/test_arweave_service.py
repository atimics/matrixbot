#!/usr/bin/env python3
"""
Test Arweave Service Integration

Tests for the Arweave service that uploads images to make them publicly accessible.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from chatbot.tools.arweave_service import ArweaveService, arweave_service


class TestArweaveService:
    """Test the ArweaveService class."""

    def test_initialization_with_client(self):
        """Test ArweaveService initialization with provided client."""
        mock_client = MagicMock()
        service = ArweaveService(arweave_client=mock_client)
        
        assert service.arweave_client == mock_client
        assert service.is_configured() is True

    def test_initialization_without_client(self):
        """Test ArweaveService initialization without client."""
        service = ArweaveService()
        
        # Without configuration, should not be configured
        assert service.is_configured() is False

    @patch('chatbot.tools.arweave_service.settings.ARWEAVE_UPLOADER_API_ENDPOINT', 'https://test-endpoint.com')
    @patch('chatbot.tools.arweave_service.settings.ARWEAVE_UPLOADER_API_KEY', 'test-key')
    def test_initialization_with_env_vars(self):
        """Test ArweaveService initialization with environment variables."""
        with patch('chatbot.tools.arweave_service.ArweaveUploaderClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            
            service = ArweaveService()
            
            assert service.is_configured() is True
            mock_client_class.assert_called_once()

    def test_is_arweave_url(self):
        """Test URL validation for Arweave URLs."""
        service = ArweaveService()
        
        # Valid Arweave URLs
        assert service.is_arweave_url("https://arweave.net/abc123") is True
        assert service.is_arweave_url("https://ar.io/def456") is True
        assert service.is_arweave_url("https://test.arweave.dev/ghi789") is True
        
        # Invalid URLs
        assert service.is_arweave_url("https://example.com/image.jpg") is False
        assert service.is_arweave_url("") is False
        assert service.is_arweave_url(None) is False

    @pytest.mark.asyncio
    async def test_upload_image_data_success(self):
        """Test successful image data upload."""
        mock_client = AsyncMock()
        mock_client.upload_data = AsyncMock(return_value="test_tx_id")
        mock_client.get_arweave_url = MagicMock(return_value="https://arweave.net/test_tx_id")
        
        service = ArweaveService(arweave_client=mock_client)
        
        image_data = b"fake_image_data"
        result = await service.upload_image_data(image_data, "test.png", "image/png")
        
        assert result == "https://arweave.net/test_tx_id"
        mock_client.upload_data.assert_called_once()
        mock_client.get_arweave_url.assert_called_once_with("test_tx_id")

    @pytest.mark.asyncio
    async def test_upload_image_data_no_client(self):
        """Test image data upload without client."""
        service = ArweaveService()
        
        image_data = b"fake_image_data"
        result = await service.upload_image_data(image_data, "test.png", "image/png")
        
        assert result is None

    @pytest.mark.asyncio
    async def test_upload_image_data_upload_failure(self):
        """Test image data upload when Arweave upload fails."""
        mock_client = AsyncMock()
        mock_client.upload_data = AsyncMock(return_value=None)  # Upload failed
        
        service = ArweaveService(arweave_client=mock_client)
        
        image_data = b"fake_image_data"
        result = await service.upload_image_data(image_data, "test.png", "image/png")
        
        assert result is None

    @pytest.mark.asyncio
    async def test_ensure_arweave_url_already_arweave(self):
        """Test ensure_arweave_url with URL that's already on Arweave."""
        service = ArweaveService()
        
        arweave_url = "https://arweave.net/existing_tx_id"
        result = await service.ensure_arweave_url(arweave_url)
        
        assert result == arweave_url

    @pytest.mark.asyncio
    async def test_ensure_arweave_url_download_and_upload(self):
        """Test ensure_arweave_url with external URL that needs to be uploaded."""
        mock_client = AsyncMock()
        mock_client.upload_data = AsyncMock(return_value="new_tx_id")
        mock_client.get_arweave_url = MagicMock(return_value="https://arweave.net/new_tx_id")
        
        service = ArweaveService(arweave_client=mock_client)
        
        with patch('httpx.AsyncClient') as mock_httpx:
            mock_response = MagicMock()
            mock_response.content = b"fake_image_content"
            mock_response.headers = {'content-type': 'image/jpeg'}
            mock_response.raise_for_status = MagicMock()
            
            mock_httpx.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
            
            result = await service.ensure_arweave_url("https://example.com/image.jpg")
            
            assert result == "https://arweave.net/new_tx_id"

    @pytest.mark.asyncio
    async def test_download_file_data_success(self):
        """Test successful file download."""
        service = ArweaveService()
        
        with patch('httpx.AsyncClient') as mock_httpx:
            mock_response = MagicMock()
            mock_response.content = b"fake_file_content"
            mock_response.raise_for_status = MagicMock()
            
            mock_httpx.return_value.__aenter__.return_value.get.return_value = mock_response
            
            result = await service.download_file_data("https://arweave.net/test_tx_id")
            
            assert result == b"fake_file_content"


class TestArweaveServiceSingleton:
    """Test the global arweave_service instance."""

    def test_singleton_exists(self):
        """Test that the global arweave_service instance exists."""
        assert arweave_service is not None
        assert isinstance(arweave_service, ArweaveService)
