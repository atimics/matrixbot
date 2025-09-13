"""
Error handling utilities and decorators.

Provides consistent error handling patterns, retry logic,
and error recovery mechanisms throughout the application.
"""

import asyncio
import functools
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Type, Union
from dataclasses import dataclass

from ..exceptions import (
    ChatbotBaseException, 
    IntegrationError, 
    RateLimitError, 
    TimeoutError,
    AIEngineError,
    ToolExecutionError
)


logger = logging.getLogger(__name__)


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_attempts: int = 3
    base_delay: float = 1.0
    backoff_factor: float = 2.0
    max_delay: float = 60.0
    jitter: bool = True
    retryable_exceptions: tuple = (
        IntegrationError,
        RateLimitError, 
        TimeoutError,
        ConnectionError,
        OSError
    )


class ErrorHandler:
    """Central error handling and recovery system."""
    
    def __init__(self):
        self.error_counts: Dict[str, int] = {}
        self.last_errors: Dict[str, Dict[str, Any]] = {}
    
    def record_error(self, component: str, error: Exception, context: Optional[Dict[str, Any]] = None):
        """Record an error occurrence for tracking and analysis."""
        error_key = f"{component}:{type(error).__name__}"
        self.error_counts[error_key] = self.error_counts.get(error_key, 0) + 1
        
        self.last_errors[error_key] = {
            "timestamp": time.time(),
            "error": str(error),
            "context": context or {},
            "count": self.error_counts[error_key]
        }
        
        logger.error(
            f"Error in {component}: {error}",
            extra={
                "component": component,
                "error_type": type(error).__name__,
                "error_count": self.error_counts[error_key],
                "context": context
            }
        )
    
    def get_error_summary(self) -> Dict[str, Any]:
        """Get a summary of recorded errors."""
        return {
            "total_errors": sum(self.error_counts.values()),
            "error_types": len(self.error_counts),
            "error_counts": self.error_counts.copy(),
            "recent_errors": [
                {**details, "error_key": key}
                for key, details in self.last_errors.items()
                if time.time() - details["timestamp"] < 3600  # Last hour
            ]
        }


# Global error handler instance
error_handler = ErrorHandler()


def handle_errors(
    retry_config: Optional[RetryConfig] = None,
    component: Optional[str] = None,
    fallback_result: Any = None,
    log_errors: bool = True
):
    """
    Decorator for consistent error handling with retries and fallbacks.
    
    Args:
        retry_config: Configuration for retry behavior
        component: Component name for error tracking
        fallback_result: Value to return if all retries fail
        log_errors: Whether to log errors
    """
    if retry_config is None:
        retry_config = RetryConfig()
    
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            comp_name = component or f"{func.__module__}.{func.__name__}"
            last_error = None
            
            for attempt in range(retry_config.max_attempts):
                try:
                    return await func(*args, **kwargs)
                    
                except retry_config.retryable_exceptions as e:
                    last_error = e
                    
                    if log_errors:
                        error_handler.record_error(
                            comp_name, e, 
                            {"attempt": attempt + 1, "args": str(args)[:200]}
                        )
                    
                    # Check if this is the last attempt
                    if attempt >= retry_config.max_attempts - 1:
                        break
                    
                    # Calculate delay with exponential backoff and jitter
                    delay = min(
                        retry_config.base_delay * (retry_config.backoff_factor ** attempt),
                        retry_config.max_delay
                    )
                    
                    if retry_config.jitter:
                        import random
                        delay *= (0.5 + random.random() * 0.5)  # 50-100% of calculated delay
                    
                    # Special handling for rate limit errors
                    if isinstance(e, RateLimitError) and e.retry_after is not None:
                        delay = max(delay, e.retry_after)
                    
                    logger.info(f"Retrying {comp_name} in {delay:.2f}s (attempt {attempt + 1}/{retry_config.max_attempts})")
                    await asyncio.sleep(delay)
                
                except Exception as e:
                    # Non-retryable error
                    if log_errors:
                        error_handler.record_error(comp_name, e, {"args": str(args)[:200]})
                    
                    if isinstance(e, ChatbotBaseException):
                        raise  # Re-raise our custom exceptions
                    else:
                        # Wrap unknown exceptions
                        raise IntegrationError(
                            service=comp_name,
                            message=f"Unexpected error in {comp_name}: {e}",
                            details={"original_error": str(e), "error_type": type(e).__name__}
                        )
            
            # All retries exhausted
            if fallback_result is not None:
                logger.warning(f"All retries exhausted for {comp_name}, returning fallback result")
                return fallback_result
            
            # Re-raise the last error
            if last_error:
                raise last_error
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            comp_name = component or f"{func.__module__}.{func.__name__}"
            last_error = None
            
            for attempt in range(retry_config.max_attempts):
                try:
                    return func(*args, **kwargs)
                    
                except retry_config.retryable_exceptions as e:
                    last_error = e
                    
                    if log_errors:
                        error_handler.record_error(
                            comp_name, e, 
                            {"attempt": attempt + 1, "args": str(args)[:200]}
                        )
                    
                    if attempt >= retry_config.max_attempts - 1:
                        break
                    
                    delay = min(
                        retry_config.base_delay * (retry_config.backoff_factor ** attempt),
                        retry_config.max_delay
                    )
                    
                    if retry_config.jitter:
                        import random
                        delay *= (0.5 + random.random() * 0.5)
                    
                    if isinstance(e, RateLimitError) and e.retry_after is not None:
                        delay = max(delay, e.retry_after)
                    
                    logger.info(f"Retrying {comp_name} in {delay:.2f}s")
                    time.sleep(delay)
                
                except Exception as e:
                    if log_errors:
                        error_handler.record_error(comp_name, e, {"args": str(args)[:200]})
                    
                    if isinstance(e, ChatbotBaseException):
                        raise
                    else:
                        raise IntegrationError(
                            service=comp_name,
                            message=f"Unexpected error in {comp_name}: {e}",
                            details={"original_error": str(e), "error_type": type(e).__name__}
                        )
            
            if fallback_result is not None:
                logger.warning(f"All retries exhausted for {comp_name}, returning fallback result")
                return fallback_result
            
            if last_error:
                raise last_error
        
        # Return appropriate wrapper based on whether function is async
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def safe_execute(
    func: Callable,
    *args,
    fallback_result: Any = None,
    error_message: Optional[str] = None,
    component: Optional[str] = None,
    **kwargs
) -> Any:
    """
    Safely execute a function with error handling.
    
    Args:
        func: Function to execute
        *args: Arguments for the function
        fallback_result: Value to return on error
        error_message: Custom error message
        component: Component name for error tracking
        **kwargs: Keyword arguments for the function
    """
    comp_name = component or f"{func.__module__}.{func.__name__}"
    
    try:
        return func(*args, **kwargs)
    except Exception as e:
        error_handler.record_error(comp_name, e)
        
        if error_message:
            logger.error(f"{error_message}: {e}")
        
        if fallback_result is not None:
            return fallback_result
        
        if isinstance(e, ChatbotBaseException):
            raise
        else:
            raise IntegrationError(
                service=comp_name,
                message=f"Error in {comp_name}: {e}",
                details={"original_error": str(e)}
            )


async def safe_execute_async(
    func: Callable,
    *args,
    fallback_result: Any = None,
    error_message: Optional[str] = None,
    component: Optional[str] = None,
    **kwargs
) -> Any:
    """Async version of safe_execute."""
    comp_name = component or f"{func.__module__}.{func.__name__}"
    
    try:
        if asyncio.iscoroutinefunction(func):
            return await func(*args, **kwargs)
        else:
            return func(*args, **kwargs)
    except Exception as e:
        error_handler.record_error(comp_name, e)
        
        if error_message:
            logger.error(f"{error_message}: {e}")
        
        if fallback_result is not None:
            return fallback_result
        
        if isinstance(e, ChatbotBaseException):
            raise
        else:
            raise IntegrationError(
                service=comp_name,
                message=f"Error in {comp_name}: {e}",
                details={"original_error": str(e)}
            )


def circuit_breaker(
    failure_threshold: int = 5,
    timeout: float = 60.0,
    recovery_timeout: float = 30.0
):
    """
    Circuit breaker pattern for external service calls.
    
    Args:
        failure_threshold: Number of failures before opening circuit
        timeout: How long to keep circuit open
        recovery_timeout: How long to wait before attempting recovery
    """
    
    class CircuitState:
        def __init__(self):
            self.failure_count = 0
            self.last_failure_time = 0.0
            self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    
    circuits: Dict[str, CircuitState] = {}
    
    def decorator(func: Callable) -> Callable:
        circuit_name = f"{func.__module__}.{func.__name__}"
        
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            if circuit_name not in circuits:
                circuits[circuit_name] = CircuitState()
            
            circuit = circuits[circuit_name]
            current_time = time.time()
            
            # Check circuit state
            if circuit.state == "OPEN":
                if current_time - circuit.last_failure_time > recovery_timeout:
                    circuit.state = "HALF_OPEN"
                    logger.info(f"Circuit breaker {circuit_name} entering HALF_OPEN state")
                else:
                    raise IntegrationError(
                        service=circuit_name,
                        message=f"Circuit breaker is OPEN for {circuit_name}",
                        details={"state": "OPEN", "retry_after": recovery_timeout}
                    )
            
            try:
                result = await func(*args, **kwargs)
                
                # Success - reset circuit
                if circuit.state == "HALF_OPEN":
                    circuit.state = "CLOSED"
                    circuit.failure_count = 0
                    logger.info(f"Circuit breaker {circuit_name} reset to CLOSED state")
                
                return result
                
            except Exception as e:
                circuit.failure_count += 1
                circuit.last_failure_time = current_time
                
                if circuit.failure_count >= failure_threshold:
                    circuit.state = "OPEN"
                    logger.warning(
                        f"Circuit breaker {circuit_name} opened after {circuit.failure_count} failures"
                    )
                
                raise
        
        return wrapper
    return decorator


def create_error_response(
    error: Exception,
    include_details: bool = False
) -> Dict[str, Any]:
    """Create a standardized error response."""
    if isinstance(error, ChatbotBaseException):
        response = error.to_dict()
    else:
        response = {
            "error_code": "UNKNOWN_ERROR",
            "message": str(error),
            "type": type(error).__name__,
            "details": {}
        }
    
    response["timestamp"] = time.time()
    
    if not include_details:
        # Remove sensitive details for external responses
        response.pop("details", None)
    
    return response
