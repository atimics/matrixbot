"""
Enhanced Security Module for API Server

Provides authentication, authorization, and security utilities for the API server.
"""

import hashlib
import hmac
import logging
import time
from typing import Optional

from fastapi import HTTPException, Request, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from ..config import settings

logger = logging.getLogger(__name__)

# Security scheme for API key authentication
security = HTTPBearer(auto_error=False)


class APIKeyAuth:
    """Enhanced API key authentication with rate limiting and logging."""
    
    def __init__(self):
        self.api_key = getattr(settings, 'API_SERVER_KEY', None)
        self.require_auth = getattr(settings, 'API_REQUIRE_AUTH', True)
        
    def __call__(self, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> bool:
        """Validate API key authentication."""
        # Skip authentication if not required (development mode only)
        if not self.require_auth:
            logger.warning("API authentication is disabled - development mode only")
            return True
            
        # Check if API key is configured
        if not self.api_key:
            logger.error("API_SERVER_KEY not configured but authentication is required")
            raise HTTPException(
                status_code=500,
                detail="Server configuration error - contact administrator"
            )
        
        # Check if credentials provided
        if not credentials:
            raise HTTPException(
                status_code=401,
                detail="Missing authentication credentials"
            )
        
        # Validate API key
        if not self._validate_api_key(credentials.credentials):
            logger.warning(f"Invalid API key attempt from client")
            raise HTTPException(
                status_code=401,
                detail="Invalid API key"
            )
        
        return True
    
    def _validate_api_key(self, provided_key: str) -> bool:
        """Securely validate API key using constant-time comparison."""
        if not provided_key or not self.api_key:
            return False
        
        # Use HMAC for constant-time comparison to prevent timing attacks
        expected = hmac.new(b"api_key_validation", self.api_key.encode(), hashlib.sha256).hexdigest()
        provided = hmac.new(b"api_key_validation", provided_key.encode(), hashlib.sha256).hexdigest()
        
        return hmac.compare_digest(expected, provided)


class RateLimitedAPIKeyAuth:
    """API key authentication with built-in rate limiting."""
    
    def __init__(self, max_requests_per_minute: int = 60):
        self.api_key_auth = APIKeyAuth()
        self.max_requests = max_requests_per_minute
        self.request_history = {}
        
    async def __call__(self, request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> bool:
        """Validate API key with rate limiting."""
        # First validate the API key
        is_valid = self.api_key_auth(credentials)
        
        if not is_valid:
            return False
        
        # Apply rate limiting
        client_ip = self._get_client_ip(request)
        current_time = time.time()
        
        # Clean old requests
        self._clean_old_requests(current_time)
        
        # Check rate limit
        if client_ip in self.request_history:
            recent_requests = len([
                req_time for req_time in self.request_history[client_ip]
                if current_time - req_time < 60  # Last minute
            ])
            
            if recent_requests >= self.max_requests:
                logger.warning(f"Rate limit exceeded for client {client_ip}")
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded - too many requests"
                )
        
        # Record this request
        if client_ip not in self.request_history:
            self.request_history[client_ip] = []
        self.request_history[client_ip].append(current_time)
        
        return True
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP address from request."""
        # Check for forwarded headers first (reverse proxy)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        # Fallback to direct connection IP
        return request.client.host if request.client else "unknown"
    
    def _clean_old_requests(self, current_time: float):
        """Remove requests older than 1 minute."""
        cutoff_time = current_time - 60
        for client_ip in list(self.request_history.keys()):
            self.request_history[client_ip] = [
                req_time for req_time in self.request_history[client_ip]
                if req_time > cutoff_time
            ]
            # Remove empty entries
            if not self.request_history[client_ip]:
                del self.request_history[client_ip]


# Create instances for use in dependencies
api_key_auth = APIKeyAuth()
rate_limited_auth = RateLimitedAPIKeyAuth()


def require_api_key() -> bool:
    """Dependency that requires valid API key authentication."""
    return Depends(api_key_auth)


def require_api_key_with_rate_limit() -> bool:
    """Dependency that requires API key with rate limiting."""
    return Depends(rate_limited_auth)


def validate_admin_access(authenticated: bool = Depends(api_key_auth)) -> bool:
    """Enhanced dependency for admin-level operations."""
    if not authenticated:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # Additional admin checks could be added here
    # For now, valid API key = admin access
    return True
