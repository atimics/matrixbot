"""
Comprehensive unit tests for the Arweave Service
Tests cover all critical improvements including API key validation, async handling, and error cases.
"""
import asyncio
import json
import os
import tempfile
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Dict, Any
import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException

# Import the main application and classes
from main import (
    app, ArweaveWalletManager, validate_api_key, 
    UploadResponse, WalletInfo, HealthResponse
)


class TestArweaveWalletManager:
    """Test the ArweaveWalletManager class functionality"""
    
    def test_initialization(self):
        """Test wallet manager initialization"""
        manager = ArweaveWalletManager("/fake/path", "https://test.arweave.net")
        assert manager.wallet_file_path == "/fake/path"
        assert manager.gateway_url == "https://test.arweave.net"
        assert manager.wallet is None
        
    @pytest.mark.asyncio
    async def test_initialize_wallet_file_not_found(self):
        """Test initialization when wallet file doesn't exist"""
        manager = ArweaveWalletManager("/nonexistent/wallet.json")
        await manager.initialize()
        assert manager.wallet is None
        assert not manager.is_ready()
        
    @pytest.mark.asyncio
    async def test_initialize_wallet_success(self):
        """Test successful wallet initialization"""
        # Create a temporary wallet file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as temp_file:
            # Mock wallet data
            wallet_data = {
                "d": "mock_private_key",
                "dp": "mock_dp",
                "dq": "mock_dq", 
                "e": "AQAB",
                "ext": True,
                "kty": "RSA",
                "n": "mock_n",
                "p": "mock_p",
                "q": "mock_q",
                "qi": "mock_qi"
            }
            json.dump(wallet_data, temp_file)
            temp_file_path = temp_file.name
            
        try:
            with patch('main.Wallet') as mock_wallet_class:
                mock_wallet = Mock()
                mock_wallet.address = "mock_address_123"
                mock_wallet.get_balance = AsyncMock(return_value=1000000000000)  # 1 AR in winston
                mock_wallet_class.return_value = mock_wallet
                
                manager = ArweaveWalletManager(temp_file_path)
                await manager.initialize()
                
                assert manager.wallet is not None
                assert manager.is_ready()
                assert manager.get_wallet_address() == "mock_address_123"
                
        finally:
            os.unlink(temp_file_path)
            
    @pytest.mark.asyncio
    async def test_get_balance_no_wallet(self):
        """Test getting balance when wallet is not initialized"""
        manager = ArweaveWalletManager("/fake/path")
        
        with pytest.raises(HTTPException) as exc_info:
            await manager.get_balance()
        
        assert exc_info.value.status_code == 503
        assert "Wallet not initialized" in str(exc_info.value.detail)
        
    @pytest.mark.asyncio
    async def test_get_balance_success(self):
        """Test successful balance retrieval"""
        manager = ArweaveWalletManager("/fake/path")
        mock_wallet = Mock()
        mock_wallet.get_balance = AsyncMock(return_value=2500000000000)  # 2.5 AR in winston
        manager.wallet = mock_wallet
        
        balance = await manager.get_balance()
        assert balance == 2.5
        
    @pytest.mark.asyncio
    async def test_get_balance_error(self):
        """Test balance retrieval error handling"""
        manager = ArweaveWalletManager("/fake/path")
        mock_wallet = Mock()
        mock_wallet.get_balance = AsyncMock(side_effect=Exception("Network error"))
        manager.wallet = mock_wallet
        
        with pytest.raises(HTTPException) as exc_info:
            await manager.get_balance()
        
        assert exc_info.value.status_code == 503
        assert "Could not fetch wallet balance" in str(exc_info.value.detail)


class TestAPIKeyValidation:
    """Test API key validation functionality"""
    
    def test_validate_api_key_no_key_configured(self):
        """Test validation when no API key is configured"""
        with patch.dict(os.environ, {}, clear=True):
            # Should not raise any exception
            validate_api_key("any_key")
            validate_api_key(None)
            
    def test_validate_api_key_valid(self):
        """Test validation with correct API key"""
        with patch.dict(os.environ, {"ARWEAVE_SERVICE_API_KEY": "secret123"}):
            # Import after setting env var to get updated API_KEY
            from importlib import reload
            import main
            reload(main)
            
            # Should not raise any exception
            main.validate_api_key("secret123")
            
    def test_validate_api_key_invalid(self):
        """Test validation with incorrect API key"""
        with patch.dict(os.environ, {"ARWEAVE_SERVICE_API_KEY": "secret123"}):
            from importlib import reload
            import main
            reload(main)
            
            with pytest.raises(HTTPException) as exc_info:
                main.validate_api_key("wrong_key")
            
            assert exc_info.value.status_code == 401
            assert "Invalid API Key" in str(exc_info.value.detail)
            
    def test_validate_api_key_missing(self):
        """Test validation when API key is required but not provided"""
        with patch.dict(os.environ, {"ARWEAVE_SERVICE_API_KEY": "secret123"}):
            from importlib import reload
            import main
            reload(main)
            
            with pytest.raises(HTTPException) as exc_info:
                main.validate_api_key(None)
            
            assert exc_info.value.status_code == 401
            assert "Invalid API Key" in str(exc_info.value.detail)


class TestEndpoints:
    """Test FastAPI endpoints"""
    
    def setup_method(self):
        """Setup test client for each test"""
        self.client = TestClient(app)
        
    def test_health_check_wallet_not_ready(self):
        """Test health check when wallet is not ready"""
        with patch('main.wallet_manager') as mock_manager:
            mock_manager.is_ready.return_value = False
            mock_manager.get_wallet_address.return_value = None
            
            response = self.client.get("/health")
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "unhealthy"
            assert data["wallet_ready"] is False
            assert data["wallet_address"] is None
            
    def test_health_check_wallet_ready(self):
        """Test health check when wallet is ready"""
        with patch('main.wallet_manager') as mock_manager:
            mock_manager.is_ready.return_value = True
            mock_manager.get_wallet_address.return_value = "test_address_123"
            
            response = self.client.get("/health")
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert data["wallet_ready"] is True
            assert data["wallet_address"] == "test_address_123"
            
    def test_get_wallet_info_not_ready(self):
        """Test wallet info endpoint when wallet is not ready"""
        with patch('main.wallet_manager') as mock_manager:
            mock_manager.is_ready.return_value = False
            
            response = self.client.get("/wallet")
            
            assert response.status_code == 503
            assert "Wallet not initialized" in response.json()["detail"]
            
    def test_get_wallet_info_success(self):
        """Test successful wallet info retrieval"""
        with patch('main.wallet_manager') as mock_manager:
            mock_manager.is_ready.return_value = True
            mock_manager.get_wallet_address.return_value = "test_address_123"
            mock_manager.get_balance = AsyncMock(return_value=1.5)
            
            response = self.client.get("/wallet")
            
            assert response.status_code == 200
            data = response.json()
            assert data["address"] == "test_address_123"
            assert data["balance_ar"] == 1.5
            assert data["status"] == "ready"
            
    def test_upload_file_wallet_not_ready(self):
        """Test file upload when wallet is not ready"""
        with patch('main.wallet_manager') as mock_manager:
            mock_manager.is_ready.return_value = False
            
            files = {"file": ("test.txt", b"test content", "text/plain")}
            response = self.client.post("/upload", files=files)
            
            assert response.status_code == 503
            assert "Wallet not initialized" in response.json()["detail"]
            
    def test_upload_file_empty_file(self):
        """Test file upload with empty file"""
        with patch('main.wallet_manager') as mock_manager:
            mock_manager.is_ready.return_value = True
            
            files = {"file": ("empty.txt", b"", "text/plain")}
            response = self.client.post("/upload", files=files)
            
            assert response.status_code == 400
            assert "Empty file provided" in response.json()["detail"]
            
    def test_upload_file_success(self):
        """Test successful file upload"""
        with patch('main.wallet_manager') as mock_manager, \
             patch('main.Transaction') as mock_transaction_class, \
             patch('asyncio.to_thread') as mock_to_thread:
            
            # Setup mocks
            mock_manager.is_ready.return_value = True
            mock_manager.get_wallet_address.return_value = "test_address_123"
            mock_manager.wallet = Mock()
            
            mock_transaction = Mock()
            mock_transaction.id = "test_transaction_id_123"
            mock_transaction.add_tag = Mock()
            mock_transaction.sign = Mock()
            mock_transaction.send = Mock()
            mock_transaction_class.return_value = mock_transaction
            
            mock_to_thread.return_value = asyncio.Future()
            mock_to_thread.return_value.set_result(None)
            
            files = {"file": ("test.txt", b"test content", "text/plain")}
            response = self.client.post("/upload", files=files)
            
            assert response.status_code == 200
            data = response.json()
            assert data["transaction_id"] == "test_transaction_id_123"
            assert data["wallet_address"] == "test_address_123"
            assert data["data_size"] == 12  # len(b"test content")
            assert data["content_type"] == "text/plain"
            assert data["upload_status"] == "submitted"
            assert "arweave.net/test_transaction_id_123" in data["arweave_url"]
            
            # Verify async handling was used
            mock_to_thread.assert_called_once()
            
    def test_upload_file_with_api_key(self):
        """Test file upload with API key authentication"""
        with patch.dict(os.environ, {"ARWEAVE_SERVICE_API_KEY": "secret123"}), \
             patch('main.wallet_manager') as mock_manager, \
             patch('main.Transaction') as mock_transaction_class, \
             patch('asyncio.to_thread') as mock_to_thread:
            
            # Reload main to pick up new env var
            from importlib import reload
            import main
            reload(main)
            
            # Setup mocks
            mock_manager.is_ready.return_value = True
            mock_manager.get_wallet_address.return_value = "test_address_123"
            mock_manager.wallet = Mock()
            
            mock_transaction = Mock()
            mock_transaction.id = "test_transaction_id_123"
            mock_transaction.add_tag = Mock()
            mock_transaction.sign = Mock()
            mock_transaction.send = Mock()
            mock_transaction_class.return_value = mock_transaction
            
            mock_to_thread.return_value = asyncio.Future()
            mock_to_thread.return_value.set_result(None)
            
            files = {"file": ("test.txt", b"test content", "text/plain")}
            headers = {"X-API-Key": "secret123"}
            
            client = TestClient(main.app)
            response = client.post("/upload", files=files, headers=headers)
            
            assert response.status_code == 200
            
    def test_upload_file_invalid_api_key(self):
        """Test file upload with invalid API key"""
        with patch.dict(os.environ, {"ARWEAVE_SERVICE_API_KEY": "secret123"}):
            from importlib import reload
            import main
            reload(main)
            
            files = {"file": ("test.txt", b"test content", "text/plain")}
            headers = {"X-API-Key": "wrong_key"}
            
            client = TestClient(main.app)
            response = client.post("/upload", files=files, headers=headers)
            
            assert response.status_code == 401
            assert "Invalid API Key" in response.json()["detail"]
            
    def test_upload_file_with_tags(self):
        """Test file upload with custom tags"""
        with patch('main.wallet_manager') as mock_manager, \
             patch('main.Transaction') as mock_transaction_class, \
             patch('asyncio.to_thread') as mock_to_thread:
            
            # Setup mocks
            mock_manager.is_ready.return_value = True
            mock_manager.get_wallet_address.return_value = "test_address_123"
            mock_manager.wallet = Mock()
            
            mock_transaction = Mock()
            mock_transaction.id = "test_transaction_id_123"
            mock_transaction.add_tag = Mock()
            mock_transaction.sign = Mock()
            mock_transaction.send = Mock()
            mock_transaction_class.return_value = mock_transaction
            
            mock_to_thread.return_value = asyncio.Future()
            mock_to_thread.return_value.set_result(None)
            
            tags = json.dumps({"category": "test", "version": "1.0"})
            files = {"file": ("test.txt", b"test content", "text/plain")}
            data = {"tags": tags}
            
            response = self.client.post("/upload", files=files, data=data)
            
            assert response.status_code == 200
            
            # Verify tags were added
            expected_calls = [
                (('Content-Type', 'text/plain'),),
                (('File-Name', 'test.txt'),),
                (('category', 'test'),),
                (('version', '1.0'),)
            ]
            mock_transaction.add_tag.assert_has_calls(expected_calls, any_order=True)
            
    def test_upload_data_success(self):
        """Test successful data upload"""
        with patch('main.wallet_manager') as mock_manager, \
             patch('main.Transaction') as mock_transaction_class, \
             patch('asyncio.to_thread') as mock_to_thread:
            
            # Setup mocks
            mock_manager.is_ready.return_value = True
            mock_manager.get_wallet_address.return_value = "test_address_123"
            mock_manager.wallet = Mock()
            
            mock_transaction = Mock()
            mock_transaction.id = "test_data_transaction_id"
            mock_transaction.add_tag = Mock()
            mock_transaction.sign = Mock()
            mock_transaction.send = Mock()
            mock_transaction_class.return_value = mock_transaction
            
            mock_to_thread.return_value = asyncio.Future()
            mock_to_thread.return_value.set_result(None)
            
            data = {
                "data": "Hello, Arweave!",
                "content_type": "text/plain"
            }
            
            response = self.client.post("/upload/data", data=data)
            
            assert response.status_code == 200
            response_data = response.json()
            assert response_data["transaction_id"] == "test_data_transaction_id"
            assert response_data["wallet_address"] == "test_address_123"
            assert response_data["data_size"] == 15  # len("Hello, Arweave!".encode('utf-8'))
            assert response_data["content_type"] == "text/plain"
            
            # Verify async handling was used
            mock_to_thread.assert_called_once()
            
    def test_upload_data_with_invalid_tags(self):
        """Test data upload with invalid JSON tags"""
        with patch('main.wallet_manager') as mock_manager, \
             patch('main.Transaction') as mock_transaction_class, \
             patch('asyncio.to_thread') as mock_to_thread:
            
            # Setup mocks
            mock_manager.is_ready.return_value = True
            mock_manager.get_wallet_address.return_value = "test_address_123"
            mock_manager.wallet = Mock()
            
            mock_transaction = Mock()
            mock_transaction.id = "test_transaction_id"
            mock_transaction.add_tag = Mock()
            mock_transaction.sign = Mock()
            mock_transaction.send = Mock()
            mock_transaction_class.return_value = mock_transaction
            
            mock_to_thread.return_value = asyncio.Future()
            mock_to_thread.return_value.set_result(None)
            
            data = {
                "data": "Test data",
                "content_type": "text/plain",
                "tags": "invalid json {{"
            }
            
            response = self.client.post("/upload/data", data=data)
            
            # Should still succeed, just ignore invalid tags
            assert response.status_code == 200
            
    def test_upload_transaction_error(self):
        """Test upload when transaction sending fails"""
        with patch('main.wallet_manager') as mock_manager, \
             patch('main.Transaction') as mock_transaction_class, \
             patch('asyncio.to_thread') as mock_to_thread:
            
            # Setup mocks
            mock_manager.is_ready.return_value = True
            mock_manager.wallet = Mock()
            
            mock_transaction = Mock()
            mock_transaction.sign = Mock()
            mock_transaction.send = Mock()
            mock_transaction_class.return_value = mock_transaction
            
            # Make asyncio.to_thread raise an exception
            mock_to_thread.side_effect = Exception("Network error")
            
            files = {"file": ("test.txt", b"test content", "text/plain")}
            response = self.client.post("/upload", files=files)
            
            assert response.status_code == 500
            assert "Upload failed" in response.json()["detail"]


class TestAsyncHandling:
    """Test that async improvements are working correctly"""
    
    @pytest.mark.asyncio
    async def test_async_transaction_send(self):
        """Test that transaction.send() is properly wrapped with asyncio.to_thread"""
        
        with patch('main.wallet_manager') as mock_manager, \
             patch('main.Transaction') as mock_transaction_class, \
             patch('asyncio.to_thread') as mock_to_thread:
            
            # Setup mocks
            mock_manager.is_ready.return_value = True
            mock_manager.wallet = Mock()
            
            mock_transaction = Mock()
            mock_transaction.id = "test_id"
            mock_transaction.add_tag = Mock()
            mock_transaction.sign = Mock()
            mock_transaction.send = Mock()  # This should be blocking
            mock_transaction_class.return_value = mock_transaction
            
            # Mock asyncio.to_thread to return a future
            future = asyncio.Future()
            future.set_result(None)
            mock_to_thread.return_value = future
            
            # Import the function we need to test
            from main import upload_to_arweave
            
            # Create a mock file upload
            class MockFile:
                filename = "test.txt"
                content_type = "text/plain"
                async def read(self):
                    return b"test content"
            
            # Call the upload function
            await upload_to_arweave(MockFile(), None, None)
            
            # Verify that asyncio.to_thread was called with the send method
            mock_to_thread.assert_called_once()
            args = mock_to_thread.call_args[0]
            assert args[0] == mock_transaction.send


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
