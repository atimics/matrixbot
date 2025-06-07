#!/usr/bin/env python3
"""
Test Arweave Service Integration

Tests for the Arweave service that uploads images to make them publicly accessible.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from chatbot.tools.arweave_service import ArweaveService
from chatbot.integrations.arweave_uploader_client import ArweaveUploaderClient


class TestArweaveService:
    """Test the ArweaveService class."""

    def test_initialization_with_client(self):
        """Test ArweaveService initialization with a client."""
        mock_client = MagicMock(spec=ArweaveUploaderClient)
        service = ArweaveService(arweave_client=mock_client)
        assert service.arweave_client == mock_client

    def test_is_configured(self):
        """Test that is_configured returns true when a client is present."""
        mock_client = MagicMock(spec=ArweaveUploaderClient)
        service = ArweaveService(arweave_client=mock_client)
        assert service.is_configured() is True

    def test_is_not_configured(self):
        """Test that is_configured returns false when no client is present."""
        service = ArweaveService()
        assert service.is_configured() is False

    @pytest.mark.asyncio
    async def test_upload_image_data_success(self):
        """Test successful image data upload."""
        mock_client = AsyncMock(spec=ArweaveUploaderClient)
        mock_client.upload_data.return_value = "some_tx_id"
        mock_client.get_arweave_url.return_value = "https://arweave.net/some_tx_id"
        
        service = ArweaveService(arweave_client=mock_client)
        
        result = await service.upload_image_data(b'fake_image_data', 'test.png', 'image/png')
        
        assert result == "https://arweave.net/some_tx_id"
        mock_client.upload_data.assert_called_once()
        mock_client.get_arweave_url.assert_called_once_with("some_tx_id")

    @pytest.mark.asyncio
    async def test_upload_image_data_failure(self):
        """Test image data upload failure."""
        mock_client = AsyncMock(spec=ArweaveUploaderClient)
        mock_client.upload_data.return_value = None
        
        service = ArweaveService(arweave_client=mock_client)
        
        result = await service.upload_image_data(b'fake_image_data', 'test.png', 'image/png')
        
        assert result is None
        mock_client.upload_data.assert_called_once()

    def test_is_arweave_url(self):
        """Test the is_arweave_url method."""
        service = ArweaveService()
        assert service.is_arweave_url("https://arweave.net/some_tx_id") is True
        assert service.is_arweave_url("https://ar.io/some_tx_id") is True
        assert service.is_arweave_url("http://example.com/image.png") is False
        assert service.is_arweave_url(None) is False
