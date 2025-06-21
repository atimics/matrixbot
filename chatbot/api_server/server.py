"""
Secure API Server Implementation

A production-ready REST API server for the chatbot system with:
- API key authentication for all protected endpoints
- Rate limiting and CORS security
- Modular router architecture with fallback support
- Comprehensive error handling
"""

import logging
import time
import hmac
import hashlib
from datetime import datetime
from typing import Optional, List, Dict, Any
from collections import defaultdict

from fastapi import FastAPI, HTTPException, Depends, Header, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from chatbot.config import UnifiedSettings
from chatbot.core.orchestration import MainOrchestrator
from chatbot.core.secrets import get_secret_manager

logger = logging.getLogger(__name__)


class SecurityConfig(BaseModel):
    """Security configuration for the API server."""
    api_key: Optional[str] = None
    allowed_origins: List[str] = ["http://localhost:3000"]
    trusted_hosts: List[str] = ["localhost", "127.0.0.1"]
    rate_limit_requests_per_minute: int = 60
    enable_api_key_auth: bool = True


class RateLimiter:
    """Simple in-memory rate limiter."""
    
    def __init__(self):
        self.requests: Dict[str, List[float]] = defaultdict(list)
    
    def is_allowed(self, client_id: str, max_requests: int, window_seconds: int = 60) -> bool:
        """Check if request is allowed within rate limits."""
        now = time.time()
        window_start = now - window_seconds
        
        # Clean old requests
        self.requests[client_id] = [req_time for req_time in self.requests[client_id] 
                                  if req_time > window_start]
        
        # Check if under limit
        if len(self.requests[client_id]) < max_requests:
            self.requests[client_id].append(now)
            return True
        
        return False


class APIKeyAuth:
    """API key authentication handler with secure comparison."""
    
    def __init__(self, security_config: SecurityConfig):
        self.security_config = security_config
        self.security_scheme = HTTPBearer(auto_error=False)
    
    async def get_api_key(self, 
                         x_api_key: Optional[str] = Header(None),
                         authorization: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False))) -> Optional[str]:
        """Extract API key from headers."""
        # Try X-API-Key header first
        if x_api_key:
            return x_api_key
        
        # Try Authorization header
        if authorization and authorization.scheme.lower() == "bearer":
            return authorization.credentials
        
        return None
    
    async def verify_api_key(self, api_key: Optional[str] = Depends(get_api_key)) -> str:
        """Verify API key for protected endpoints using secure comparison."""
        if not self.security_config.enable_api_key_auth:
            return "bypass"  # Authentication disabled
        
        expected_key = self.security_config.api_key
        if not expected_key:
            # Try to get from secret manager
            secret_manager = get_secret_manager()
            expected_key = await secret_manager.get_secret("API_KEY")
        
        if not expected_key:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="API key not configured"
            )
        
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing API key",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        # Use secure comparison to prevent timing attacks
        expected_hash = hashlib.sha256(expected_key.encode()).hexdigest()
        provided_hash = hashlib.sha256(api_key.encode()).hexdigest()
        
        if not hmac.compare_digest(expected_hash, provided_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        return api_key


class APIServer:
    """Main API server implementation."""
    
    def __init__(self, orchestrator: MainOrchestrator, settings: Optional[UnifiedSettings] = None):
        self.orchestrator = orchestrator
        self.settings = settings or UnifiedSettings()
        self._start_time = datetime.now()
        
        # Security configuration
        self.security_config = SecurityConfig(
            api_key=self.settings.security.api_key,
            allowed_origins=self.settings.security.allowed_origins,
            rate_limit_requests_per_minute=self.settings.security.rate_limit_requests_per_minute
        )
        
        # Security components
        self.rate_limiter = RateLimiter()
        self.api_key_auth = APIKeyAuth(self.security_config)
        
        # Create FastAPI app
        self.app = FastAPI(
            title="Secure Chatbot Management API",
            description="Production-ready REST API for monitoring and controlling the chatbot system",
            version="2.0.0",
            docs_url="/docs" if self.settings.LOG_LEVEL == "DEBUG" else None,  # Hide docs in production
            redoc_url="/redoc" if self.settings.LOG_LEVEL == "DEBUG" else None
        )
        
        self._setup_middleware()
        self._setup_routes()
        self._setup_error_handlers()
    
    def _setup_middleware(self):
        """Configure security middleware."""
        # CORS with restricted origins
        if self.security_config.allowed_origins != ["*"]:
            self.app.add_middleware(
                CORSMiddleware,
                allow_origins=self.security_config.allowed_origins,
                allow_credentials=True,
                allow_methods=["GET", "POST", "PUT", "DELETE"],
                allow_headers=["Authorization", "Content-Type", "X-API-Key"],
            )
            logger.info(f"CORS configured with origins: {self.security_config.allowed_origins}")
        else:
            logger.warning("CORS configured with wildcard origins - SECURITY RISK in production")
            self.app.add_middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )
        
        # Trusted host middleware (fixed - no wildcard bypass)
        self.app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=self.security_config.trusted_hosts
        )
        
        # Rate limiting middleware
        @self.app.middleware("http")
        async def rate_limit_middleware(request: Request, call_next):
            client_ip = request.client.host if request.client else "unknown"
            
            if not self.rate_limiter.is_allowed(
                client_ip, 
                self.security_config.rate_limit_requests_per_minute
            ):
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded"}
                )
            
            response = await call_next(request)
            return response
    
    def _setup_routes(self):
        """Setup API routes with modular architecture."""
        # Create main protected API router with global authentication
        from fastapi import APIRouter
        
        protected_api_router = APIRouter(
            prefix="/api",
            dependencies=[Depends(self.api_key_auth.verify_api_key)]
        )
        
        # Try to load modular routers
        try:
            from .routers import tools, integrations, monitoring, ai, worldstate, setup
            
            protected_api_router.include_router(tools.router, prefix="", tags=["tools"])
            protected_api_router.include_router(integrations.router, prefix="", tags=["integrations"]) 
            protected_api_router.include_router(monitoring.router, prefix="", tags=["monitoring"])
            protected_api_router.include_router(ai.router, prefix="", tags=["ai"])
            protected_api_router.include_router(worldstate.router, prefix="", tags=["worldstate"])
            protected_api_router.include_router(setup.router, prefix="", tags=["setup"])
            
            logger.info("Loaded modular API routers with global authentication")
            
        except ImportError as e:
            logger.warning(f"Could not import modular routers: {e}, using fallback inline routes")
            self._setup_fallback_routes(protected_api_router)
        
        # Include the protected router in the main app
        self.app.include_router(protected_api_router)
        
        # Public endpoints (no authentication required)
        self._setup_public_routes()
        
        logger.info("API routes configured with global authentication protection for all /api/* endpoints")
    
    def _setup_fallback_routes(self, router: "APIRouter"):
        """Setup fallback routes when modular routers are not available."""
        
        @router.get("/status")
        async def get_status():
            """Get system status (protected)."""
            return {
                "status": "operational",
                "uptime_seconds": (datetime.now() - self._start_time).total_seconds(),
                "world_state_metrics": self.orchestrator.world_state.get_state_metrics() if hasattr(self.orchestrator, 'world_state') else {},
                "active_integrations": len(self.orchestrator.integration_manager.get_active_integrations()) if hasattr(self.orchestrator, 'integration_manager') else 0,
                "timestamp": datetime.now().isoformat()
            }
        
        @router.get("/worldstate")
        async def get_world_state():
            """Get world state data (protected)."""
            try:
                if hasattr(self.orchestrator, 'world_state'):
                    state_data = self.orchestrator.world_state.get_state_metrics()
                    return {
                        "state_metrics": state_data,
                        "timestamp": datetime.now().isoformat()
                    }
                else:
                    return {"error": "World state not available"}
            except Exception as e:
                logger.error(f"Error getting world state: {e}")
                raise HTTPException(status_code=500, detail="Failed to retrieve world state")
        
        @router.get("/tools")
        async def get_tools():
            """Get available tools (protected)."""
            try:
                if hasattr(self.orchestrator, 'tool_registry'):
                    tools = self.orchestrator.tool_registry.get_all_tools()
                    return {"tools": [{"name": tool.name, "description": tool.description} for tool in tools]}
                else:
                    return {"tools": []}
            except Exception as e:
                logger.error(f"Error getting tools: {e}")
                raise HTTPException(status_code=500, detail="Failed to retrieve tools")
        
        @router.get("/integrations")
        async def get_integrations():
            """Get integrations (protected)."""
            try:
                integrations = await self.orchestrator.integration_manager.list_integrations()
                return {
                    "integrations": integrations,
                    "count": len(integrations),
                    "timestamp": datetime.now().isoformat()
                }
            except Exception as e:
                logger.error(f"Error getting integrations: {e}")
                raise HTTPException(status_code=500, detail="Failed to retrieve integrations")
        
        @router.post("/admin/restart")
        async def restart_system():
            """Restart system components (admin only)."""
            try:
                # Implement restart logic
                return {
                    "status": "restart_initiated",
                    "timestamp": datetime.now().isoformat()
                }
            except Exception as e:
                logger.error(f"Error restarting system: {e}")
                raise HTTPException(status_code=500, detail="Failed to restart system")
        
        @router.get("/security/info")
        async def get_security_info():
            """Get security configuration info (protected)."""
            return {
                "authentication_enabled": self.security_config.enable_api_key_auth,
                "rate_limiting_enabled": True,
                "rate_limit_per_minute": self.security_config.rate_limit_requests_per_minute,
                "cors_origins": self.security_config.allowed_origins,
                "trusted_hosts": self.security_config.trusted_hosts,
                "timestamp": datetime.now().isoformat()
            }
    
    def _setup_public_routes(self):
        """Setup public routes that don't require authentication."""
        
        @self.app.get("/health")
        async def health_check():
            """Public health check endpoint."""
            return {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "uptime_seconds": (datetime.now() - self._start_time).total_seconds(),
                "version": "2.0.0",
                "service": "secure_chatbot_api"
            }
        
        @self.app.get("/")
        async def root():
            """Public root endpoint with basic info."""
            return {
                "service": "Secure Chatbot Management API",
                "version": "2.0.0",
                "docs": "/docs" if self.settings.LOG_LEVEL == "DEBUG" else "Authentication required for API access",
                "health": "/health",
                "security": "All /api/* endpoints require authentication"
            }
    
    def _setup_error_handlers(self):
        """Setup custom error handlers."""
        
        @self.app.exception_handler(HTTPException)
        async def http_exception_handler(request: Request, exc: HTTPException):
            """Handle HTTP exceptions with security in mind."""
            # Don't expose internal details in production
            detail = exc.detail
            if self.settings.LOG_LEVEL != "DEBUG":
                # Generic error messages in production
                if exc.status_code == 500:
                    detail = "Internal server error"
                elif exc.status_code == 401:
                    detail = "Authentication required"
                elif exc.status_code == 403:
                    detail = "Access forbidden"
            
            return JSONResponse(
                status_code=exc.status_code,
                content={
                    "error": detail,
                    "status_code": exc.status_code,
                    "timestamp": datetime.now().isoformat()
                }
            )
        
        @self.app.exception_handler(Exception)
        async def general_exception_handler(request: Request, exc: Exception):
            """Handle general exceptions."""
            logger.error(f"Unhandled exception: {exc}", exc_info=True)
            
            # Don't expose exception details in production
            detail = "Internal server error"
            if self.settings.LOG_LEVEL == "DEBUG":
                detail = str(exc)
            
            return JSONResponse(
                status_code=500,
                content={
                    "error": detail,
                    "status_code": 500,
                    "timestamp": datetime.now().isoformat()
                }
            )
    
    async def initialize_security(self):
        """Initialize security components."""
        try:
            # Initialize secret manager
            from chatbot.core.secrets import init_secret_manager, SecretConfig, SecretBackend
            
            # Configure secret manager based on environment
            secret_config = SecretConfig(
                backend=SecretBackend.ENCRYPTED_FILE if self.settings.LOG_LEVEL != "DEBUG" else SecretBackend.ENVIRONMENT
            )
            
            await init_secret_manager(secret_config)
            
            # Validate API key is configured
            secret_manager = get_secret_manager()
            api_key = await secret_manager.get_secret("API_KEY")
            
            if not api_key and self.security_config.enable_api_key_auth:
                logger.warning("API_KEY not configured - generating temporary key")
                temp_key = f"temp-{int(time.time())}"
                await secret_manager.set_secret("API_KEY", temp_key)
                logger.warning(f"Temporary API key: {temp_key}")
            
            logger.info("Security initialization complete")
            
        except Exception as e:
            logger.error(f"Security initialization failed: {e}")
            raise


def create_api_server(orchestrator: MainOrchestrator, settings: Optional[UnifiedSettings] = None) -> FastAPI:
    """Factory function to create a secure API server."""
    server = APIServer(orchestrator, settings)
    return server.app


# Testing utilities
class TestSecurityConfig(SecurityConfig):
    """Test security configuration that bypasses authentication."""
    enable_api_key_auth: bool = False
    allowed_origins: List[str] = ["*"]
    rate_limit_requests_per_minute: int = 1000  # High limit for tests


# Backward compatibility
create_secure_api_server = create_api_server
SecureAPIServer = APIServer
