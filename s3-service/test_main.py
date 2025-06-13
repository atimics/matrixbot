"""
Test suite for the S3 Service.
"""

import json
import os
import pytest
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient
import httpx

# Import our S3 service
from main import app, s3_manager


class TestS3Manager:
    """Test the S3Manager class"""
    
    def test_initialization(self):
        """Test S3Manager initialization"""
        from main import S3Manager
        manager = S3Manager("test_key", "https://api.example.com", "https://cdn.example.com")
        assert manager.api_key == "test_key"
        assert manager.api_endpoint == "https://api.example.com"
        assert manager.cloudfront_domain == "https://cdn.example.com"
    
    def test_is_ready(self):
        """Test S3Manager readiness check"""
        from main import S3Manager
        
        # Test with all required values
        manager = S3Manager("key", "https://api.example.com", "https://cdn.example.com")
        assert manager.is_ready() == True
        
        # Test with missing values
        manager_incomplete = S3Manager("", "https://api.example.com", "https://cdn.example.com")
        assert manager_incomplete.is_ready() == False
    
    @pytest.mark.asyncio
    async def test_upload_data_success(self):
        """Test successful data upload"""
        from main import S3Manager
        
        manager = S3Manager("test_key", "https://api.example.com", "https://cdn.example.com")
        
        # Mock the httpx client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "body": json.dumps({"url": "https://cdn.example.com/test-image.png"})
        }
        
        with patch.object(manager, 'client') as mock_client:
            mock_client.post = AsyncMock(return_value=mock_response)
            
            result = await manager.upload_data(b"test data", "image/png")
            
            assert result == "https://cdn.example.com/test-image.png"
            mock_client.post.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_upload_data_failure(self):
        """Test failed data upload"""
        from main import S3Manager
        
        manager = S3Manager("test_key", "https://api.example.com", "https://cdn.example.com")
        
        # Mock failed response
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        
        with patch.object(manager, 'client') as mock_client:
            mock_client.post = AsyncMock(return_value=mock_response)
            
            result = await manager.upload_data(b"test data", "image/png")
            
            assert result is None
    
    @pytest.mark.asyncio
    async def test_download_data_success(self):
        """Test successful data download"""
        from main import S3Manager
        
        manager = S3Manager("test_key", "https://api.example.com", "https://cdn.example.com")
        
        # Mock successful download
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"downloaded data"
        
        with patch.object(manager, 'client') as mock_client:
            mock_client.get = AsyncMock(return_value=mock_response)
            
            result = await manager.download_data("https://example.com/file.png")
            
            assert result == b"downloaded data"
            mock_client.get.assert_called_once_with("https://example.com/file.png", follow_redirects=True)


class TestEndpoints:
    """Test FastAPI endpoints"""
    
    def setup_method(self):
        """Set up test client"""
        self.client = TestClient(app)
    
    def test_health_endpoint(self):
        """Test health check endpoint"""
        with patch.object(s3_manager, 'is_ready', return_value=True):
            response = self.client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert data["wallet_ready"] == True
    
    def test_wallet_info_endpoint(self):
        """Test wallet info endpoint"""
        with patch.object(s3_manager, 'is_ready', return_value=True), \
             patch.object(s3_manager, 'cloudfront_domain', "https://cdn.example.com"):
            
            response = self.client.get("/wallet")
            assert response.status_code == 200
            data = response.json()
            assert data["address"] == "https://cdn.example.com"
            assert data["balance_ar"] == 1.0
            assert data["status"] == "ready"
    
    def test_wallet_info_not_ready(self):
        """Test wallet info when S3 not ready"""
        with patch.object(s3_manager, 'is_ready', return_value=False):
            response = self.client.get("/wallet")
            assert response.status_code == 503
    
    def test_upload_file_success(self):
        """Test successful file upload"""
        with patch.object(s3_manager, 'is_ready', return_value=True), \
             patch.object(s3_manager, 'upload_data', new_callable=AsyncMock) as mock_upload, \
             patch.object(s3_manager, 'cloudfront_domain', "https://cdn.example.com"):
            
            mock_upload.return_value = "https://cdn.example.com/test-file.png"
            
            files = {"file": ("test.png", b"test content", "image/png")}
            response = self.client.post("/upload", files=files)
            
            assert response.status_code == 200
            data = response.json()
            assert data["arweave_url"] == "https://cdn.example.com/test-file.png"
            assert data["transaction_id"] == "https://cdn.example.com/test-file.png"
            assert data["data_size"] == 12  # len(b"test content")
            assert data["content_type"] == "image/png"
            assert data["upload_status"] == "submitted"
    
    def test_upload_file_not_ready(self):
        """Test file upload when S3 not ready"""
        with patch.object(s3_manager, 'is_ready', return_value=False):
            files = {"file": ("test.png", b"test content", "image/png")}
            response = self.client.post("/upload", files=files)
            assert response.status_code == 503
    
    def test_upload_file_with_api_key(self):
        """Test file upload with API key authentication"""
        with patch.dict(os.environ, {"S3_SERVICE_API_KEY": "secret123"}):
            # Reload the module to pick up the new environment variable
            from importlib import reload
            import main
            reload(main)
            
            files = {"file": ("test.png", b"test content", "image/png")}
            headers = {"X-API-Key": "secret123"}
            
            with patch.object(main.s3_manager, 'is_ready', return_value=True), \
                 patch.object(main.s3_manager, 'upload_data', new_callable=AsyncMock) as mock_upload, \
                 patch.object(main.s3_manager, 'cloudfront_domain', "https://cdn.example.com"):
                
                mock_upload.return_value = "https://cdn.example.com/test-file.png"
                
                client = TestClient(main.app)
                response = client.post("/upload", files=files, headers=headers)
                
                assert response.status_code == 200
    
    def test_upload_file_invalid_api_key(self):
        """Test file upload with invalid API key"""
        with patch.dict(os.environ, {"S3_SERVICE_API_KEY": "secret123"}):
            from importlib import reload
            import main
            reload(main)
            
            files = {"file": ("test.png", b"test content", "image/png")}
            headers = {"X-API-Key": "wrong_key"}
            
            client = TestClient(main.app)
            response = client.post("/upload", files=files, headers=headers)
            
            assert response.status_code == 401
            assert "Invalid API Key" in response.json()["detail"]
    
    def test_upload_data_success(self):
        """Test successful data upload"""
        with patch('main.API_KEY', "test-api-key"), \
             patch.object(s3_manager, 'is_ready', return_value=True), \
             patch.object(s3_manager, 'upload_data', new_callable=AsyncMock) as mock_upload, \
             patch.object(s3_manager, 'cloudfront_domain', "https://cdn.example.com"):
            
            mock_upload.return_value = "https://cdn.example.com/test-data.txt"
            
            data = {
                "data": "Hello, S3!",
                "content_type": "text/plain"
            }
            
            # Include proper authentication header
            headers = {"x-api-key": "test-api-key"}
            response = self.client.post("/upload/data", data=data, headers=headers)
            
            assert response.status_code == 200
            response_data = response.json()
            assert response_data["arweave_url"] == "https://cdn.example.com/test-data.txt"
            assert response_data["transaction_id"] == "https://cdn.example.com/test-data.txt"
            assert response_data["data_size"] == 10  # len("Hello, S3!".encode('utf-8'))
            assert response_data["content_type"] == "text/plain"
    
    def test_upload_data_with_tags(self):
        """Test data upload with custom tags"""
        with patch('main.API_KEY', "test-api-key"), \
             patch.object(s3_manager, 'is_ready', return_value=True), \
             patch.object(s3_manager, 'upload_data', new_callable=AsyncMock) as mock_upload, \
             patch.object(s3_manager, 'cloudfront_domain', "https://cdn.example.com"):
            
            mock_upload.return_value = "https://cdn.example.com/test-data.txt"
            
            data = {
                "data": "Hello, S3!",
                "content_type": "text/plain",
                "tags": json.dumps({"category": "test", "version": "1.0"})
            }
            
            # Include proper authentication header
            headers = {"x-api-key": "test-api-key"}
            response = self.client.post("/upload/data", data=data, headers=headers)
            
            assert response.status_code == 200
            # Tags should be parsed but not cause errors (S3 doesn't use them the same way)
    
    def test_upload_data_with_invalid_tags(self):
        """Test data upload with invalid JSON tags"""
        with patch('main.API_KEY', "test-api-key"), \
             patch.object(s3_manager, 'is_ready', return_value=True), \
             patch.object(s3_manager, 'upload_data', new_callable=AsyncMock) as mock_upload, \
             patch.object(s3_manager, 'cloudfront_domain', "https://cdn.example.com"):
            
            mock_upload.return_value = "https://cdn.example.com/test-data.txt"
            
            data = {
                "data": "Hello, S3!",
                "content_type": "text/plain",
                "tags": "invalid json"
            }
            
            # Include proper authentication header
            headers = {"x-api-key": "test-api-key"}
            response = self.client.post("/upload/data", data=data, headers=headers)
            
            # Should still succeed, just ignore invalid tags
            assert response.status_code == 200
    
    def test_upload_empty_file(self):
        """Test upload of empty file"""
        with patch.object(s3_manager, 'is_ready', return_value=True):
            files = {"file": ("empty.txt", b"", "text/plain")}
            response = self.client.post("/upload", files=files)
            assert response.status_code == 400
            assert "Empty file provided" in response.json()["detail"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
