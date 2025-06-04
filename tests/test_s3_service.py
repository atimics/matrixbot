#!/usr/bin/env python3
"""
Test S3 Service Integration

Tests for the S3 service that uploads images to make them publicly accessible.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from chatbot.tools.s3_service import S3Service, s3_service


class TestS3Service:
    """Test the S3Service class."""

    def test_initialization_with_env_vars(self):
        """Test S3Service initialization with environment variables."""
        with patch.dict('os.environ', {
            'S3_API_ENDPOINT': 'https://test-endpoint.com',
            'S3_API_KEY': 'test-key',
            'CLOUDFRONT_DOMAIN': 'https://test-cloudfront.com'
        }):
            service = S3Service()
            assert service.s3_api_endpoint == 'https://test-endpoint.com'
            assert service.s3_api_key == 'test-key'
            # CloudFront domain should have https:// prefix stripped
            assert service.cloudfront_domain == 'test-cloudfront.com'

    def test_initialization_with_domain_no_protocol(self):
        """Test S3Service initialization with domain that has no protocol."""
        with patch.dict('os.environ', {
            'S3_API_ENDPOINT': 'https://test-endpoint.com',
            'S3_API_KEY': 'test-key',
            'CLOUDFRONT_DOMAIN': 'test-cloudfront.com'
        }):
            service = S3Service()
            assert service.s3_api_endpoint == 'https://test-endpoint.com'
            assert service.s3_api_key == 'test-key'
            # CloudFront domain should remain unchanged if no protocol
            assert service.cloudfront_domain == 'test-cloudfront.com'

    def test_initialization_missing_env_vars(self):
        """Test S3Service initialization fails with missing environment variables."""
        with patch.dict('os.environ', {}, clear=True):
            with pytest.raises(ValueError, match="S3_API_ENDPOINT and S3_API_KEY must be set"):
                S3Service()

    @pytest.mark.asyncio
    async def test_upload_image_from_url_success(self):
        """Test successful image upload from URL."""
        with patch.dict('os.environ', {
            'S3_API_ENDPOINT': 'https://test-endpoint.com',
            'S3_API_KEY': 'test-key',
            'CLOUDFRONT_DOMAIN': 'https://test-cloudfront.com'
        }):
            service = S3Service()
            
            # Mock the download and upload methods
            with patch.object(service, '_download_image') as mock_download, \
                 patch.object(service, '_upload_to_s3') as mock_upload:
                
                mock_download.return_value = b'fake_image_data'
                mock_upload.return_value = 'https://cloudfront.com/uploaded_image.jpg'
                
                result = await service.upload_image_from_url('https://example.com/image.jpg')
                
                assert result == 'https://cloudfront.com/uploaded_image.jpg'
                mock_download.assert_called_once()
                mock_upload.assert_called_once()

    @pytest.mark.asyncio
    async def test_upload_image_from_url_download_failure(self):
        """Test image upload failure when download fails."""
        with patch.dict('os.environ', {
            'S3_API_ENDPOINT': 'https://test-endpoint.com',
            'S3_API_KEY': 'test-key',
            'CLOUDFRONT_DOMAIN': 'https://test-cloudfront.com'
        }):
            service = S3Service()
            
            # Mock download failure
            with patch.object(service, '_download_image') as mock_download:
                mock_download.return_value = None
                
                result = await service.upload_image_from_url('https://example.com/image.jpg')
                
                assert result is None

    @pytest.mark.asyncio
    async def test_upload_image_data_success(self):
        """Test successful direct image data upload."""
        with patch.dict('os.environ', {
            'S3_API_ENDPOINT': 'https://test-endpoint.com',
            'S3_API_KEY': 'test-key',
            'CLOUDFRONT_DOMAIN': 'https://test-cloudfront.com'
        }):
            service = S3Service()
            
            # Mock the upload method
            with patch.object(service, '_upload_to_s3') as mock_upload:
                mock_upload.return_value = 'https://cloudfront.com/uploaded_image.jpg'
                
                result = await service.upload_image_data(b'fake_image_data', 'test.jpg')
                
                assert result == 'https://cloudfront.com/uploaded_image.jpg'
                mock_upload.assert_called_once()

    @pytest.mark.asyncio
    async def test_download_image_success(self):
        """Test successful image download."""
        with patch.dict('os.environ', {
            'S3_API_ENDPOINT': 'https://test-endpoint.com',
            'S3_API_KEY': 'test-key',
            'CLOUDFRONT_DOMAIN': 'https://test-cloudfront.com'
        }):
            service = S3Service()
            
            # Mock httpx client
            mock_response = MagicMock()
            mock_response.content = b'fake_image_data'
            mock_response.headers = {'content-type': 'image/jpeg'}
            
            with patch('httpx.AsyncClient') as mock_client_class:
                mock_client = AsyncMock()
                mock_client_class.return_value.__aenter__.return_value = mock_client
                mock_client.get.return_value = mock_response
                
                result = await service._download_image('https://example.com/image.jpg')
                
                assert result == b'fake_image_data'
                mock_client.get.assert_called_once_with('https://example.com/image.jpg')

    def test_get_file_extension_from_url(self):
        """Test file extension extraction from URL."""
        with patch.dict('os.environ', {
            'S3_API_ENDPOINT': 'https://test-endpoint.com',
            'S3_API_KEY': 'test-key',
            'CLOUDFRONT_DOMAIN': 'https://test-cloudfront.com'
        }):
            service = S3Service()
            
            # Test various URL formats
            assert service._get_file_extension('https://example.com/image.jpg') == '.jpg'
            assert service._get_file_extension('https://example.com/image.PNG') == '.png'
            assert service._get_file_extension('https://example.com/image.jpeg?v=123') == '.jpeg'
            assert service._get_file_extension('https://example.com/noextension') == '.jpg'

    def test_get_file_extension_from_filename(self):
        """Test file extension extraction from filename."""
        with patch.dict('os.environ', {
            'S3_API_ENDPOINT': 'https://test-endpoint.com',
            'S3_API_KEY': 'test-key',
            'CLOUDFRONT_DOMAIN': 'https://test-cloudfront.com'
        }):
            service = S3Service()
            
            # Test various filenames
            assert service._get_file_extension_from_filename('image.jpg') == '.jpg'
            assert service._get_file_extension_from_filename('image.PNG') == '.png'
            assert service._get_file_extension_from_filename('noextension') == '.jpg'
            assert service._get_file_extension_from_filename(None) == '.jpg'
            assert service._get_file_extension_from_filename('') == '.jpg'

    def test_generate_embeddable_url(self):
        """Test embeddable URL generation with fixed CloudFront domain."""
        with patch.dict('os.environ', {
            'S3_API_ENDPOINT': 'https://test-endpoint.com',
            'S3_API_KEY': 'test-key',
            'CLOUDFRONT_DOMAIN': 'https://test-cloudfront.com'  # Note: has https:// prefix
        }):
            service = S3Service()
            
            # CloudFront domain should be stripped of protocol
            assert service.cloudfront_domain == 'test-cloudfront.com'
            
            # Test embeddable URL generation
            image_url = 'https://test-cloudfront.com/images/test.jpg'
            embeddable_url = service.generate_embeddable_url(image_url, 'Test Title', 'Test Description')
            
            # Should not have double https:// in the URL
            assert 'https://https://' not in embeddable_url
            assert embeddable_url.startswith('https://test-cloudfront.com/embed/image/')
            assert 'title=Test%20Title' in embeddable_url
            assert 'description=Test%20Description' in embeddable_url

    def test_generate_embeddable_url_no_domain(self):
        """Test embeddable URL generation when no CloudFront domain is set."""
        with patch.dict('os.environ', {
            'S3_API_ENDPOINT': 'https://test-endpoint.com',
            'S3_API_KEY': 'test-key'
            # No CLOUDFRONT_DOMAIN set
        }):
            service = S3Service()
            
            image_url = 'https://example.com/image.jpg'
            embeddable_url = service.generate_embeddable_url(image_url)
            
            # Should return original URL when no domain is configured
            assert embeddable_url == image_url


class TestS3ServiceSingleton:
    """Test the S3 service singleton instance."""

    def test_singleton_instance_exists(self):
        """Test that the singleton instance is created."""
        # The singleton should be created when the module is imported
        # We just verify it exists and has the expected type
        assert s3_service is not None
        assert isinstance(s3_service, S3Service)
