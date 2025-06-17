"""
API Security middleware and authentication for the chatbot API server.

Implements API key authentication, CORS policy enforcement, and rate limiting
as recommended in the engineering report.
"""

import time
import hashlib
import logging
from typing import Dict, List, Optional, Tuple
from collections import defaultdict, deque
from datetime import datetime, timedelta

from fastapi import HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

logger = logging.getLogger(__name__)


class APIKeyAuth(HTTPBearer):
    """API Key authentication using Bearer token format."""
    
    def __init__(self, valid_api_keys: List[str], auto_error: bool = True):
        super().__init__(auto_error=auto_error)
        # Hash API keys for secure comparison
        self.valid_keys_hashed = {
            hashlib.sha256(key.encode()).hexdigest(): key[:8] + "..." 
            for key in valid_api_keys
        }
        logger.info(f"Initialized API key auth with {len(valid_api_keys)} keys")
    
    async def __call__(self, request: Request) -> Optional[HTTPAuthorizationCredentials]:
        """Validate API key from Authorization header."""
        credentials = await super().__call__(request)
        
        if not credentials:
            if self.auto_error:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="API key required",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return None
        
        # Hash the provided key and compare
        provided_key_hash = hashlib.sha256(credentials.credentials.encode()).hexdigest()
        
        if provided_key_hash not in self.valid_keys_hashed:
            if self.auto_error:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid API key",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return None
        
        # Log successful authentication (without exposing the key)
        key_preview = self.valid_keys_hashed[provided_key_hash]
        logger.debug(f"API key authenticated: {key_preview}")
        
        return credentials


class RateLimiter:
    """Token bucket rate limiter with per-client tracking."""
    
    def __init__(
        self, 
        requests_per_minute: int = 60, 
        burst_size: int = 10,
        cleanup_interval: int = 300  # 5 minutes
    ):
        self.requests_per_minute = requests_per_minute
        self.burst_size = burst_size
        self.cleanup_interval = cleanup_interval
        
        # Per-client token buckets: {client_id: (tokens, last_refill)}
        self.buckets: Dict[str, Tuple[float, float]] = {}
        self.last_cleanup = time.time()
        
        logger.info(
            f"Initialized rate limiter: {requests_per_minute} req/min, "
            f"burst: {burst_size}"
        )
    
    def _get_client_id(self, request: Request) -> str:
        """Get client identifier from request."""
        # Try to get from X-Forwarded-For header first (for reverse proxies)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take the first IP in the chain
            client_ip = forwarded_for.split(",")[0].strip()
        else:
            client_ip = request.client.host if request.client else "unknown"
        
        # Include user agent for additional uniqueness
        user_agent = request.headers.get("User-Agent", "")
        user_agent_hash = hashlib.md5(user_agent.encode()).hexdigest()[:8]
        
        return f"{client_ip}:{user_agent_hash}"
    
    def _refill_bucket(self, client_id: str) -> Tuple[float, float]:
        """Refill the token bucket for a client."""
        now = time.time()
        
        if client_id not in self.buckets:
            # New client gets full burst
            self.buckets[client_id] = (self.burst_size, now)
            return self.burst_size, now
        
        tokens, last_refill = self.buckets[client_id]
        
        # Calculate tokens to add based on time elapsed
        time_elapsed = now - last_refill
        tokens_to_add = time_elapsed * (self.requests_per_minute / 60.0)
        
        # Cap at burst size
        new_tokens = min(self.burst_size, tokens + tokens_to_add)
        
        self.buckets[client_id] = (new_tokens, now)
        return new_tokens, now
    
    def _cleanup_old_buckets(self):
        """Remove buckets for clients that haven't been seen recently."""
        now = time.time()
        if now - self.last_cleanup < self.cleanup_interval:
            return
        
        cutoff = now - self.cleanup_interval
        old_clients = [
            client_id for client_id, (_, last_refill) in self.buckets.items()
            if last_refill < cutoff
        ]
        
        for client_id in old_clients:
            del self.buckets[client_id]
        
        if old_clients:
            logger.debug(f"Cleaned up {len(old_clients)} old rate limit buckets")
        
        self.last_cleanup = now
    
    def is_allowed(self, request: Request) -> Tuple[bool, Dict[str, str]]:
        """Check if request is allowed and return rate limit headers."""
        client_id = self._get_client_id(request)
        
        # Cleanup old buckets periodically
        self._cleanup_old_buckets()
        
        # Refill bucket
        tokens, _ = self._refill_bucket(client_id)
        
        # Check if request is allowed
        if tokens >= 1.0:
            # Consume one token
            self.buckets[client_id] = (tokens - 1.0, self.buckets[client_id][1])
            
            headers = {
                "X-RateLimit-Limit": str(self.requests_per_minute),
                "X-RateLimit-Remaining": str(int(tokens - 1.0)),
                "X-RateLimit-Reset": str(int(time.time() + 60))
            }
            return True, headers
        else:
            # Rate limit exceeded
            headers = {
                "X-RateLimit-Limit": str(self.requests_per_minute),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(time.time() + 60)),
                "Retry-After": "60"
            }
            return False, headers


class SecurityMiddleware(BaseHTTPMiddleware):
    """Security middleware for API protection."""
    
    def __init__(
        self, 
        app,
        rate_limiter: Optional[RateLimiter] = None,
        enable_security_headers: bool = True
    ):
        super().__init__(app)
        self.rate_limiter = rate_limiter
        self.enable_security_headers = enable_security_headers
        
        logger.info("Initialized security middleware")
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request through security checks."""
        start_time = time.time()
        
        # Rate limiting
        if self.rate_limiter:
            allowed, rate_headers = self.rate_limiter.is_allowed(request)
            if not allowed:
                logger.warning(
                    f"Rate limit exceeded for {request.client.host if request.client else 'unknown'} "
                    f"on {request.method} {request.url.path}"
                )
                return Response(
                    content="Rate limit exceeded",
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    headers=rate_headers
                )
        
        # Process request
        response = await call_next(request)
        
        # Add security headers
        if self.enable_security_headers:
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["X-XSS-Protection"] = "1; mode=block"
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            # Don't add HSTS for development, but could be enabled in production
            # response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        # Add rate limit headers if applicable
        if self.rate_limiter and 'rate_headers' in locals():
            for key, value in rate_headers.items():
                response.headers[key] = value
        
        # Add timing header
        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = str(process_time)
        
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for detailed request/response logging."""
    
    def __init__(self, app, log_bodies: bool = False):
        super().__init__(app)
        self.log_bodies = log_bodies
        
    async def dispatch(self, request: Request, call_next) -> Response:
        """Log request and response details."""
        start_time = time.time()
        
        # Log request
        client_ip = request.client.host if request.client else "unknown"
        logger.info(
            f"Request: {request.method} {request.url.path} "
            f"from {client_ip} "
            f"User-Agent: {request.headers.get('User-Agent', 'unknown')}"
        )
        
        # Log request body for debugging (careful with sensitive data)
        if self.log_bodies and request.method in ["POST", "PUT", "PATCH"]:
            try:
                body = await request.body()
                if body:
                    # Mask potential secrets
                    body_str = body.decode()
                    # Simple masking for common secret patterns
                    import re
                    body_str = re.sub(r'"(password|token|key|secret)":\s*"[^"]*"', r'"\1": "***"', body_str)
                    logger.debug(f"Request body: {body_str[:500]}...")  # Limit size
            except Exception as e:
                logger.debug(f"Could not log request body: {e}")
        
        # Process request
        try:
            response = await call_next(request)
            
            # Log response
            process_time = time.time() - start_time
            logger.info(
                f"Response: {response.status_code} "
                f"for {request.method} {request.url.path} "
                f"in {process_time:.3f}s"
            )
            
            return response
            
        except Exception as e:
            process_time = time.time() - start_time
            logger.error(
                f"Request failed: {request.method} {request.url.path} "
                f"from {client_ip} "
                f"in {process_time:.3f}s: {str(e)}"
            )
            raise


def setup_cors_middleware(app, allowed_origins: List[str]):
    """Set up CORS middleware with specific origins."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        allow_headers=["*"],
        expose_headers=["X-RateLimit-*", "X-Process-Time"]
    )
    
    logger.info(f"CORS configured for origins: {allowed_origins}")


def create_api_security_setup(
    api_keys: List[str],
    cors_origins: List[str],
    rate_limit_rpm: int = 60,
    rate_limit_burst: int = 10,
    enable_request_logging: bool = True
) -> Tuple[APIKeyAuth, List]:
    """Create complete API security setup."""
    
    # Create API key authenticator
    api_key_auth = APIKeyAuth(api_keys)
    
    # Create middleware stack
    middleware = []
    
    # Rate limiter
    rate_limiter = RateLimiter(
        requests_per_minute=rate_limit_rpm,
        burst_size=rate_limit_burst
    )
    
    # Security middleware
    security_middleware = SecurityMiddleware(
        app=None,  # Will be set by FastAPI
        rate_limiter=rate_limiter,
        enable_security_headers=True
    )
    middleware.append(security_middleware)
    
    # Request logging middleware
    if enable_request_logging:
        logging_middleware = RequestLoggingMiddleware(
            app=None,  # Will be set by FastAPI
            log_bodies=False  # Set to True for debugging, but be careful with secrets
        )
        middleware.append(logging_middleware)
    
    logger.info("API security setup complete")
    
    return api_key_auth, middleware
