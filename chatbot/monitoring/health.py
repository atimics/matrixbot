"""
Health check system for monitoring external services and system status.

Provides comprehensive health monitoring for all external dependencies
and system components.
"""

import asyncio
import logging
import time
from enum import Enum
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import aiohttp
import aiosqlite
from pathlib import Path

from ..config import settings
from ..exceptions import IntegrationError, DatabaseError
from ..utils.error_handling import safe_execute_async


logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health status levels."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthCheckResult:
    """Result of a health check."""
    service: str
    status: HealthStatus
    message: str
    timestamp: datetime
    response_time: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "service": self.service,
            "status": self.status.value,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "response_time": self.response_time,
            "metadata": self.metadata
        }


class HealthChecker:
    """Manages health checks for all services."""
    
    def __init__(self):
        self.checks: Dict[str, Callable] = {}
        self.last_results: Dict[str, HealthCheckResult] = {}
        self.check_history: Dict[str, List[HealthCheckResult]] = {}
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=10.0)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session
    
    async def close(self):
        """Close HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
    
    def register_check(self, name: str, check_func: Callable):
        """Register a health check function."""
        self.checks[name] = check_func
        if name not in self.check_history:
            self.check_history[name] = []
    
    def unregister_check(self, name: str):
        """Unregister a health check."""
        self.checks.pop(name, None)
    
    async def check_service(self, service_name: str) -> HealthCheckResult:
        """Run health check for a specific service."""
        if service_name not in self.checks:
            return HealthCheckResult(
                service=service_name,
                status=HealthStatus.UNKNOWN,
                message=f"No health check registered for {service_name}",
                timestamp=datetime.now()
            )
        
        check_func = self.checks[service_name]
        start_time = time.time()
        
        try:
            result = await check_func()
            result.response_time = time.time() - start_time
            
            # Store result
            self.last_results[service_name] = result
            self.check_history[service_name].append(result)
            
            # Keep only last 100 results per service
            if len(self.check_history[service_name]) > 100:
                self.check_history[service_name] = self.check_history[service_name][-100:]
            
            return result
            
        except Exception as e:
            result = HealthCheckResult(
                service=service_name,
                status=HealthStatus.UNHEALTHY,
                message=f"Health check failed: {e}",
                timestamp=datetime.now(),
                response_time=time.time() - start_time,
                metadata={"error": str(e), "error_type": type(e).__name__}
            )
            
            self.last_results[service_name] = result
            self.check_history[service_name].append(result)
            
            logger.error(f"Health check failed for {service_name}: {e}")
            return result
    
    async def check_all(self) -> List[HealthCheckResult]:
        """Run all registered health checks."""
        if not self.checks:
            return []
        
        tasks = [
            self.check_service(service_name) 
            for service_name in self.checks.keys()
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle any exceptions from gather
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                service_name = list(self.checks.keys())[i]
                final_results.append(HealthCheckResult(
                    service=service_name,
                    status=HealthStatus.UNHEALTHY,
                    message=f"Health check execution failed: {result}",
                    timestamp=datetime.now(),
                    metadata={"error": str(result)}
                ))
            else:
                final_results.append(result)
        
        return final_results
    
    def get_service_status(self, service_name: str) -> Optional[HealthCheckResult]:
        """Get the last health check result for a service."""
        return self.last_results.get(service_name)
    
    def get_overall_status(self) -> HealthStatus:
        """Get overall system health status."""
        if not self.last_results:
            return HealthStatus.UNKNOWN
        
        statuses = [result.status for result in self.last_results.values()]
        
        if all(status == HealthStatus.HEALTHY for status in statuses):
            return HealthStatus.HEALTHY
        elif any(status == HealthStatus.UNHEALTHY for status in statuses):
            return HealthStatus.UNHEALTHY
        else:
            return HealthStatus.DEGRADED
    
    def get_service_uptime(self, service_name: str, hours: int = 24) -> float:
        """Calculate service uptime percentage over the last N hours."""
        if service_name not in self.check_history:
            return 0.0
        
        cutoff_time = datetime.now() - timedelta(hours=hours)
        recent_checks = [
            check for check in self.check_history[service_name]
            if check.timestamp > cutoff_time
        ]
        
        if not recent_checks:
            return 0.0
        
        healthy_checks = sum(
            1 for check in recent_checks 
            if check.status == HealthStatus.HEALTHY
        )
        
        return (healthy_checks / len(recent_checks)) * 100.0


# Global health checker instance
health_checker = HealthChecker()


# Health check implementations
async def check_openrouter_health() -> HealthCheckResult:
    """Check OpenRouter API connectivity."""
    if not settings.OPENROUTER_API_KEY:
        return HealthCheckResult(
            service="openrouter",
            status=HealthStatus.UNKNOWN,
            message="OpenRouter API key not configured",
            timestamp=datetime.now()
        )
    
    session = await health_checker._get_session()
    
    try:
        headers = {
            "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }
        
        # Make a lightweight request to check API health
        async with session.get(
            "https://openrouter.ai/api/v1/models",
            headers=headers
        ) as response:
            if response.status == 200:
                data = await response.json()
                model_count = len(data.get("data", []))
                return HealthCheckResult(
                    service="openrouter",
                    status=HealthStatus.HEALTHY,
                    message="API responding normally",
                    timestamp=datetime.now(),
                    metadata={"available_models": model_count, "status_code": response.status}
                )
            else:
                return HealthCheckResult(
                    service="openrouter",
                    status=HealthStatus.DEGRADED,
                    message=f"API returned status {response.status}",
                    timestamp=datetime.now(),
                    metadata={"status_code": response.status}
                )
                
    except asyncio.TimeoutError:
        return HealthCheckResult(
            service="openrouter",
            status=HealthStatus.UNHEALTHY,
            message="API request timed out",
            timestamp=datetime.now(),
            metadata={"error": "timeout"}
        )
    except Exception as e:
        return HealthCheckResult(
            service="openrouter",
            status=HealthStatus.UNHEALTHY,
            message=f"API check failed: {e}",
            timestamp=datetime.now(),
            metadata={"error": str(e)}
        )


async def check_database_health() -> HealthCheckResult:
    """Check database connectivity and performance."""
    db_path = settings.CHATBOT_DB_PATH
    
    if not db_path:
        return HealthCheckResult(
            service="database",
            status=HealthStatus.UNKNOWN,
            message="Database path not configured",
            timestamp=datetime.now()
        )
    
    try:
        # Check if database file exists and is accessible
        db_file = Path(db_path)
        if not db_file.exists():
            return HealthCheckResult(
                service="database",
                status=HealthStatus.UNHEALTHY,
                message=f"Database file does not exist: {db_path}",
                timestamp=datetime.now(),
                metadata={"db_path": db_path}
            )
        
        # Test database connection and simple query
        start_time = time.time()
        async with aiosqlite.connect(db_path) as db:
            await db.execute("SELECT 1")
            await db.commit()
        
        query_time = time.time() - start_time
        
        # Check database file size
        file_size = db_file.stat().st_size
        
        return HealthCheckResult(
            service="database",
            status=HealthStatus.HEALTHY,
            message="Database responding normally",
            timestamp=datetime.now(),
            metadata={
                "db_path": db_path,
                "file_size_mb": round(file_size / (1024 * 1024), 2),
                "query_time": round(query_time * 1000, 2)  # ms
            }
        )
        
    except Exception as e:
        return HealthCheckResult(
            service="database",
            status=HealthStatus.UNHEALTHY,
            message=f"Database check failed: {e}",
            timestamp=datetime.now(),
            metadata={"db_path": db_path, "error": str(e)}
        )


async def check_matrix_health() -> HealthCheckResult:
    """Check Matrix homeserver connectivity."""
    if not settings.MATRIX_HOMESERVER:
        return HealthCheckResult(
            service="matrix",
            status=HealthStatus.UNKNOWN,
            message="Matrix homeserver not configured",
            timestamp=datetime.now()
        )
    
    session = await health_checker._get_session()
    
    try:
        # Check Matrix homeserver version endpoint
        url = f"{settings.MATRIX_HOMESERVER}/_matrix/federation/v1/version"
        
        async with session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                server_name = data.get("server", {}).get("name", "unknown")
                server_version = data.get("server", {}).get("version", "unknown")
                
                return HealthCheckResult(
                    service="matrix",
                    status=HealthStatus.HEALTHY,
                    message="Matrix homeserver responding",
                    timestamp=datetime.now(),
                    metadata={
                        "homeserver": settings.MATRIX_HOMESERVER,
                        "server_name": server_name,
                        "server_version": server_version,
                        "status_code": response.status
                    }
                )
            else:
                return HealthCheckResult(
                    service="matrix",
                    status=HealthStatus.DEGRADED,
                    message=f"Matrix homeserver returned status {response.status}",
                    timestamp=datetime.now(),
                    metadata={"homeserver": settings.MATRIX_HOMESERVER, "status_code": response.status}
                )
                
    except asyncio.TimeoutError:
        return HealthCheckResult(
            service="matrix",
            status=HealthStatus.UNHEALTHY,
            message="Matrix homeserver request timed out",
            timestamp=datetime.now(),
            metadata={"homeserver": settings.MATRIX_HOMESERVER, "error": "timeout"}
        )
    except Exception as e:
        return HealthCheckResult(
            service="matrix",
            status=HealthStatus.UNHEALTHY,
            message=f"Matrix homeserver check failed: {e}",
            timestamp=datetime.now(),
            metadata={"homeserver": settings.MATRIX_HOMESERVER, "error": str(e)}
        )


async def check_farcaster_health() -> HealthCheckResult:
    """Check Farcaster/Neynar API connectivity."""
    if not settings.NEYNAR_API_KEY:
        return HealthCheckResult(
            service="farcaster",
            status=HealthStatus.UNKNOWN,
            message="Farcaster API key not configured",
            timestamp=datetime.now()
        )
    
    session = await health_checker._get_session()
    
    try:
        headers = {
            "accept": "application/json",
            "api_key": settings.NEYNAR_API_KEY
        }
        
        # Check Neynar API health
        async with session.get(
            "https://api.neynar.com/v2/farcaster/user/bulk",
            headers=headers,
            params={"fids": "1"}  # Minimal request
        ) as response:
            if response.status == 200:
                return HealthCheckResult(
                    service="farcaster",
                    status=HealthStatus.HEALTHY,
                    message="Farcaster API responding normally",
                    timestamp=datetime.now(),
                    metadata={"status_code": response.status}
                )
            elif response.status == 429:
                return HealthCheckResult(
                    service="farcaster",
                    status=HealthStatus.DEGRADED,
                    message="Farcaster API rate limited",
                    timestamp=datetime.now(),
                    metadata={"status_code": response.status}
                )
            else:
                return HealthCheckResult(
                    service="farcaster",
                    status=HealthStatus.DEGRADED,
                    message=f"Farcaster API returned status {response.status}",
                    timestamp=datetime.now(),
                    metadata={"status_code": response.status}
                )
                
    except asyncio.TimeoutError:
        return HealthCheckResult(
            service="farcaster",
            status=HealthStatus.UNHEALTHY,
            message="Farcaster API request timed out",
            timestamp=datetime.now(),
            metadata={"error": "timeout"}
        )
    except Exception as e:
        return HealthCheckResult(
            service="farcaster",
            status=HealthStatus.UNHEALTHY,
            message=f"Farcaster API check failed: {e}",
            timestamp=datetime.now(),
            metadata={"error": str(e)}
        )


# Register default health checks
def register_default_health_checks():
    """Register all default health checks."""
    health_checker.register_check("openrouter", check_openrouter_health)
    health_checker.register_check("database", check_database_health)
    health_checker.register_check("matrix", check_matrix_health)
    health_checker.register_check("farcaster", check_farcaster_health)


# Auto-register on import
register_default_health_checks()
