"""
Tests for API security middleware and authentication.
"""

import pytest
import time
from unittest.mock import Mock, patch
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from starlette.responses import JSONResponse

from chatbot.api_server.security import (
    APIKeyAuth, RateLimiter, SecurityMiddleware, RequestLoggingMiddleware,
    setup_cors_middleware, create_api_security_setup
)


class TestAPIKeyAuth:
    """Test API key authentication."""
    
    def test_initialization(self):
        """Test API key auth initialization."""
        keys = ["test-key-1", "test-key-2"]
        auth = APIKeyAuth(keys)
        
        assert len(auth.valid_keys_hashed) == 2
        # Keys should be hashed, not stored in plain text
        assert "test-key-1" not in str(auth.valid_keys_hashed)
    
    @pytest.mark.asyncio
    async def test_valid_api_key(self):
        """Test authentication with valid API key."""
        keys = ["test-key-12345678901234567890"]
        auth = APIKeyAuth(keys, auto_error=False)
        
        # Mock request with valid Authorization header
        mock_request = Mock()
        mock_request.headers = {"Authorization": "Bearer test-key-12345678901234567890"}
        
        # Mock the parent class method
        with patch.object(auth.__class__.__bases__[0], '__call__', return_value=Mock(credentials="test-key-12345678901234567890")):
            result = await auth(mock_request)
            assert result is not None
            assert result.credentials == "test-key-12345678901234567890"
    
    @pytest.mark.asyncio
    async def test_invalid_api_key(self):
        """Test authentication with invalid API key."""
        keys = ["valid-key-12345678901234567890"]
        auth = APIKeyAuth(keys, auto_error=False)
        
        mock_request = Mock()
        
        with patch.object(auth.__class__.__bases__[0], '__call__', return_value=Mock(credentials="invalid-key")):
            result = await auth(mock_request)
            assert result is None
    
    @pytest.mark.asyncio
    async def test_missing_api_key_with_auto_error(self):
        """Test missing API key with auto_error=True."""
        keys = ["test-key"]
        auth = APIKeyAuth(keys, auto_error=True)
        
        mock_request = Mock()
        
        with patch.object(auth.__class__.__bases__[0], '__call__', return_value=None):
            with pytest.raises(Exception):  # Should raise HTTPException
                await auth(mock_request)


class TestRateLimiter:
    """Test rate limiting functionality."""
    
    def test_initialization(self):
        """Test rate limiter initialization."""
        limiter = RateLimiter(requests_per_minute=60, burst_size=10)
        
        assert limiter.requests_per_minute == 60
        assert limiter.burst_size == 10
        assert len(limiter.buckets) == 0
    
    def test_client_id_generation(self):
        """Test client ID generation from request."""
        limiter = RateLimiter()
        
        # Mock request
        mock_request = Mock()
        mock_request.client.host = "192.168.1.1"
        mock_request.headers = {"User-Agent": "TestAgent/1.0"}
        
        client_id = limiter._get_client_id(mock_request)
        
        assert "192.168.1.1" in client_id
        assert len(client_id.split(":")) == 2  # IP:hash format
    
    def test_client_id_with_forwarded_header(self):
        """Test client ID with X-Forwarded-For header."""
        limiter = RateLimiter()
        
        mock_request = Mock()
        mock_request.client.host = "10.0.0.1"  # Internal IP
        mock_request.headers = {
            "X-Forwarded-For": "203.0.113.1, 198.51.100.1",
            "User-Agent": "TestAgent/1.0"
        }
        
        client_id = limiter._get_client_id(mock_request)
        
        # Should use the first IP from X-Forwarded-For
        assert "203.0.113.1" in client_id
        assert "10.0.0.1" not in client_id
    
    def test_token_bucket_refill(self):
        """Test token bucket refill mechanism."""
        limiter = RateLimiter(requests_per_minute=60, burst_size=5)
        client_id = "test-client"
        
        # First refill - should get full burst
        tokens, timestamp = limiter._refill_bucket(client_id)
        assert tokens == 5
        
        # Immediate refill - no time passed, same tokens
        tokens2, _ = limiter._refill_bucket(client_id)
        assert tokens2 == 5
        
        # Simulate time passing
        past_time = timestamp - 60  # 1 minute ago
        limiter.buckets[client_id] = (0, past_time)
        
        tokens3, _ = limiter._refill_bucket(client_id)
        assert tokens3 == 5  # Should be refilled to burst size
    
    def test_rate_limiting_allowed(self):
        """Test successful request within rate limits."""
        limiter = RateLimiter(requests_per_minute=60, burst_size=5)
        
        mock_request = Mock()
        mock_request.client.host = "192.168.1.1"
        mock_request.headers = {"User-Agent": "TestAgent/1.0"}
        
        allowed, headers = limiter.is_allowed(mock_request)
        
        assert allowed is True
        assert "X-RateLimit-Limit" in headers
        assert "X-RateLimit-Remaining" in headers
        assert headers["X-RateLimit-Limit"] == "60"
    
    def test_rate_limiting_exceeded(self):
        """Test rate limit exceeded scenario."""
        limiter = RateLimiter(requests_per_minute=60, burst_size=2)
        
        mock_request = Mock()
        mock_request.client.host = "192.168.1.1"
        mock_request.headers = {"User-Agent": "TestAgent/1.0"}
        
        # Use up the burst allowance
        limiter.is_allowed(mock_request)  # 1 token left
        limiter.is_allowed(mock_request)  # 0 tokens left
        
        # This should be blocked
        allowed, headers = limiter.is_allowed(mock_request)
        
        assert allowed is False
        assert "Retry-After" in headers
        assert headers["X-RateLimit-Remaining"] == "0"
    
    def test_bucket_cleanup(self):
        """Test cleanup of old client buckets."""
        limiter = RateLimiter(cleanup_interval=1)  # 1 second cleanup interval
        
        # Add a bucket
        limiter.buckets["old-client"] = (5, time.time() - 300)  # 5 minutes ago
        limiter.buckets["recent-client"] = (5, time.time())     # Now
        
        assert len(limiter.buckets) == 2
        
        # Trigger cleanup
        limiter.last_cleanup = time.time() - 2  # Force cleanup
        limiter._cleanup_old_buckets()
        
        # Old client should be removed
        assert "old-client" not in limiter.buckets
        assert "recent-client" in limiter.buckets


class TestSecurityMiddleware:
    """Test security middleware.""" 
    
    @pytest.mark.asyncio
    async def test_security_headers(self):
        """Test security headers are added."""
        app = FastAPI()
        
        @app.get("/test")
        async def test_endpoint():
            return {"message": "test"}
        
        # Add security middleware
        rate_limiter = RateLimiter(requests_per_minute=60, burst_size=10)
        app.add_middleware(SecurityMiddleware, rate_limiter=rate_limiter)
        
        client = TestClient(app)
        response = client.get("/test")
        
        assert response.status_code == 200
        assert "X-Content-Type-Options" in response.headers
        assert "X-Frame-Options" in response.headers
        assert "X-XSS-Protection" in response.headers
        assert "X-Process-Time" in response.headers
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
    
    @pytest.mark.asyncio
    async def test_rate_limiting_middleware(self):
        """Test rate limiting through middleware."""
        app = FastAPI()
        
        @app.get("/test")
        async def test_endpoint():
            return {"message": "test"}
        
        # Add security middleware with restrictive rate limit
        rate_limiter = RateLimiter(requests_per_minute=60, burst_size=1)
        app.add_middleware(SecurityMiddleware, rate_limiter=rate_limiter)
        
        client = TestClient(app)
        
        # First request should succeed
        response1 = client.get("/test")
        assert response1.status_code == 200
        assert "X-RateLimit-Remaining" in response1.headers
        
        # Second immediate request should be rate limited
        response2 = client.get("/test")
        assert response2.status_code == 429
        assert "Retry-After" in response2.headers


class TestRequestLoggingMiddleware:
    """Test request logging middleware."""
    
    @pytest.mark.asyncio
    async def test_request_logging(self):
        """Test request logging functionality."""
        app = FastAPI()
        
        @app.get("/test")
        async def test_endpoint():
            return {"message": "test"}
        
        # Add logging middleware
        app.add_middleware(RequestLoggingMiddleware, log_bodies=False)
        
        client = TestClient(app)
        
        with patch('chatbot.api_server.security.logger') as mock_logger:
            response = client.get("/test", headers={"User-Agent": "TestClient/1.0"})
            
            assert response.status_code == 200
            # Check that logging methods were called
            mock_logger.info.assert_called()
            
            # Verify log messages contain expected information
            log_calls = [call[0][0] for call in mock_logger.info.call_args_list]
            request_log = next((call for call in log_calls if "Request:" in call), None)
            response_log = next((call for call in log_calls if "Response:" in call), None)
            
            assert request_log is not None
            assert "GET /test" in request_log
            assert "TestClient/1.0" in request_log
            
            assert response_log is not None
            assert "200" in response_log


class TestSecuritySetup:
    """Test complete security setup."""
    
    def test_api_security_setup(self):
        """Test complete API security setup."""
        api_keys = ["test-key-1", "test-key-2"]
        cors_origins = ["http://localhost:3000", "https://app.example.com"]
        
        api_key_auth, middleware = create_api_security_setup(
            api_keys=api_keys,
            cors_origins=cors_origins,
            rate_limit_rpm=30,
            rate_limit_burst=5
        )
        
        assert isinstance(api_key_auth, APIKeyAuth)
        assert len(middleware) == 2  # Security and logging middleware
        
        # Check that API key auth was configured correctly
        assert len(api_key_auth.valid_keys_hashed) == 2
    
    def test_cors_setup(self):
        """Test CORS middleware setup."""
        app = FastAPI()
        allowed_origins = ["http://localhost:3000", "https://app.example.com"]
        
        setup_cors_middleware(app, allowed_origins)
        
        # Verify CORS middleware was added (check middleware stack)
        cors_middleware = None
        for middleware in app.user_middleware:
            if "CORSMiddleware" in str(middleware.cls):
                cors_middleware = middleware
                break
        
        assert cors_middleware is not None
