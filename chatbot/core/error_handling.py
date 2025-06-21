"""
Enhanced Error Handling System

Provides comprehensive error handling, logging, and recovery mechanisms
for the chatbot system.
"""

import asyncio
import logging
import traceback
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Type
from enum import Enum
from dataclasses import dataclass, field
from collections import defaultdict
import json

logger = logging.getLogger(__name__)


class ErrorSeverity(Enum):
    """Error severity levels for classification and response."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """Error categories for better organization and handling."""
    PLATFORM_CONNECTION = "platform_connection"
    AI_SERVICE = "ai_service"
    DATABASE = "database"
    TOOL_EXECUTION = "tool_execution"
    CONFIGURATION = "configuration"
    NETWORK = "network"
    VALIDATION = "validation"
    UNKNOWN = "unknown"


@dataclass
class ErrorContext:
    """Context information for error tracking and analysis."""
    error_id: str
    timestamp: datetime
    component: str
    operation: str
    error_type: str
    message: str
    severity: ErrorSeverity
    category: ErrorCategory
    recoverable: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    stack_trace: Optional[str] = None
    recovery_attempts: int = 0
    max_recovery_attempts: int = 3


class ChatbotError(Exception):
    """Base exception class for chatbot-specific errors."""
    
    def __init__(
        self,
        message: str,
        category: ErrorCategory = ErrorCategory.UNKNOWN,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        recoverable: bool = True,
        metadata: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message)
        self.message = message
        self.category = category
        self.severity = severity
        self.recoverable = recoverable
        self.metadata = metadata or {}
        self.timestamp = datetime.now()


class PlatformError(ChatbotError):
    """Platform-specific errors (Matrix, Farcaster, etc.)."""
    
    def __init__(self, message: str, platform: str, **kwargs):
        super().__init__(
            message,
            category=ErrorCategory.PLATFORM_CONNECTION,
            **kwargs
        )
        self.platform = platform
        self.metadata.update({"platform": platform})


class AIServiceError(ChatbotError):
    """AI service-related errors."""
    
    def __init__(self, message: str, service: str = "openrouter", **kwargs):
        super().__init__(
            message,
            category=ErrorCategory.AI_SERVICE,
            **kwargs
        )
        self.service = service
        self.metadata.update({"service": service})


class ToolError(ChatbotError):
    """Tool execution errors."""
    
    def __init__(self, message: str, tool_name: str, **kwargs):
        super().__init__(
            message,
            category=ErrorCategory.TOOL_EXECUTION,
            **kwargs
        )
        self.tool_name = tool_name
        self.metadata.update({"tool_name": tool_name})


class DatabaseError(ChatbotError):
    """Database operation errors."""
    
    def __init__(self, message: str, operation: str = "", **kwargs):
        super().__init__(
            message,
            category=ErrorCategory.DATABASE,
            **kwargs
        )
        self.operation = operation
        self.metadata.update({"operation": operation})


class ErrorHandlingManager:
    """Centralized error handling and recovery management."""
    
    def __init__(self):
        self.error_history: List[ErrorContext] = []
        self.error_counts = defaultdict(int)
        self.recovery_strategies = {}
        self.circuit_breakers = {}
        self.max_history = 1000
        
    def register_error(
        self,
        error: Exception,
        component: str,
        operation: str,
        context: Optional[Dict[str, Any]] = None
    ) -> ErrorContext:
        """Register an error for tracking and analysis."""
        
        # Generate unique error ID
        error_id = f"{component}_{operation}_{int(datetime.now().timestamp())}"
        
        # Determine error characteristics
        if isinstance(error, ChatbotError):
            category = error.category
            severity = error.severity
            recoverable = error.recoverable
            metadata = error.metadata
        else:
            category = self._categorize_error(error)
            severity = self._assess_severity(error, component)
            recoverable = self._is_recoverable(error)
            metadata = context or {}
        
        # Create error context
        error_context = ErrorContext(
            error_id=error_id,
            timestamp=datetime.now(),
            component=component,
            operation=operation,
            error_type=type(error).__name__,
            message=str(error),
            severity=severity,
            category=category,
            recoverable=recoverable,
            metadata=metadata,
            stack_trace=traceback.format_exc()
        )
        
        # Record error
        self.error_history.append(error_context)
        self.error_counts[f"{component}_{category.value}"] += 1
        
        # Cleanup old history
        if len(self.error_history) > self.max_history:
            self.error_history = self.error_history[-self.max_history:]
        
        # Log error with appropriate level
        self._log_error(error_context)
        
        return error_context
    
    async def handle_error(
        self,
        error: Exception,
        component: str,
        operation: str,
        context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Handle error with automatic recovery if possible."""
        
        error_context = self.register_error(error, component, operation, context)
        
        # Attempt recovery if error is recoverable
        if error_context.recoverable and error_context.recovery_attempts < error_context.max_recovery_attempts:
            return await self._attempt_recovery(error_context)
        
        # Critical errors should trigger alerts
        if error_context.severity == ErrorSeverity.CRITICAL:
            await self._handle_critical_error(error_context)
        
        return False
    
    def get_error_analytics(self, hours: int = 24) -> Dict[str, Any]:
        """Get error analytics for the specified time period."""
        
        cutoff_time = datetime.now() - timedelta(hours=hours)
        recent_errors = [
            err for err in self.error_history
            if err.timestamp >= cutoff_time
        ]
        
        # Analyze patterns
        category_counts = defaultdict(int)
        component_counts = defaultdict(int)
        severity_counts = defaultdict(int)
        
        for error in recent_errors:
            category_counts[error.category.value] += 1
            component_counts[error.component] += 1
            severity_counts[error.severity.value] += 1
        
        return {
            "total_errors": len(recent_errors),
            "time_period_hours": hours,
            "by_category": dict(category_counts),
            "by_component": dict(component_counts),
            "by_severity": dict(severity_counts),
            "recovery_rate": self._calculate_recovery_rate(recent_errors),
            "most_problematic_component": max(component_counts.items(), key=lambda x: x[1])[0] if component_counts else None,
            "recommendations": self._generate_recommendations(recent_errors)
        }
    
    def export_error_report(self, filepath: str, hours: int = 24) -> None:
        """Export detailed error report to file."""
        
        analytics = self.get_error_analytics(hours)
        cutoff_time = datetime.now() - timedelta(hours=hours)
        recent_errors = [
            {
                "error_id": err.error_id,
                "timestamp": err.timestamp.isoformat(),
                "component": err.component,
                "operation": err.operation,
                "error_type": err.error_type,
                "message": err.message,
                "severity": err.severity.value,
                "category": err.category.value,
                "recoverable": err.recoverable,
                "recovery_attempts": err.recovery_attempts,
                "metadata": err.metadata
            }
            for err in self.error_history
            if err.timestamp >= cutoff_time
        ]
        
        report = {
            "report_timestamp": datetime.now().isoformat(),
            "analytics": analytics,
            "errors": recent_errors
        }
        
        with open(filepath, 'w') as f:
            json.dump(report, f, indent=2)
        
        logger.debug(f"Error report exported to {filepath}")
    
    def _categorize_error(self, error: Exception) -> ErrorCategory:
        """Categorize error based on type and message."""
        
        error_msg = str(error).lower()
        error_type = type(error).__name__
        
        if "connection" in error_msg or "network" in error_msg:
            return ErrorCategory.NETWORK
        elif "database" in error_msg or "sqlite" in error_msg:
            return ErrorCategory.DATABASE
        elif "validation" in error_msg or "invalid" in error_msg:
            return ErrorCategory.VALIDATION
        elif "timeout" in error_msg or "rate limit" in error_msg:
            return ErrorCategory.AI_SERVICE
        else:
            return ErrorCategory.UNKNOWN
    
    def _assess_severity(self, error: Exception, component: str) -> ErrorSeverity:
        """Assess error severity based on error type and component."""
        
        error_msg = str(error).lower()
        
        # Critical errors
        if "critical" in error_msg or component in ["main_orchestrator", "world_state"]:
            return ErrorSeverity.CRITICAL
        
        # High severity
        elif "failed" in error_msg or "cannot" in error_msg:
            return ErrorSeverity.HIGH
        
        # Medium severity (default)
        else:
            return ErrorSeverity.MEDIUM
    
    def _is_recoverable(self, error: Exception) -> bool:
        """Determine if error is potentially recoverable."""
        
        error_msg = str(error).lower()
        
        # Non-recoverable conditions
        non_recoverable = [
            "permission denied",
            "invalid credentials",
            "not found",
            "invalid configuration"
        ]
        
        return not any(condition in error_msg for condition in non_recoverable)
    
    async def _attempt_recovery(self, error_context: ErrorContext) -> bool:
        """Attempt to recover from the error."""
        
        error_context.recovery_attempts += 1
        
        logger.debug(f"Attempting recovery for error {error_context.error_id} (attempt {error_context.recovery_attempts})")
        
        # Simple recovery strategies
        if error_context.category == ErrorCategory.NETWORK:
            await asyncio.sleep(2 ** error_context.recovery_attempts)  # Exponential backoff
            return True
        elif error_context.category == ErrorCategory.AI_SERVICE:
            await asyncio.sleep(1)  # Brief delay for AI service
            return True
        
        return False
    
    async def _handle_critical_error(self, error_context: ErrorContext) -> None:
        """Handle critical errors with special attention."""
        
        logger.critical(f"CRITICAL ERROR: {error_context.message}")
        logger.critical(f"Component: {error_context.component}, Operation: {error_context.operation}")
        
        # Could implement additional alerting mechanisms here:
        # - Send notifications
        # - Write to special log files
        # - Trigger emergency procedures
    
    def _log_error(self, error_context: ErrorContext) -> None:
        """Log error with appropriate level and formatting."""
        
        log_message = f"[{error_context.component}] {error_context.operation}: {error_context.message}"
        
        if error_context.severity == ErrorSeverity.CRITICAL:
            logger.critical(log_message)
        elif error_context.severity == ErrorSeverity.HIGH:
            logger.error(log_message)
        elif error_context.severity == ErrorSeverity.MEDIUM:
            logger.warning(log_message)
        else:
            logger.debug(log_message)
    
    def _calculate_recovery_rate(self, errors: List[ErrorContext]) -> float:
        """Calculate recovery success rate."""
        
        recoverable_errors = [err for err in errors if err.recoverable]
        if not recoverable_errors:
            return 0.0
        
        successful_recoveries = [
            err for err in recoverable_errors
            if err.recovery_attempts > 0 and err.recovery_attempts < err.max_recovery_attempts
        ]
        
        return len(successful_recoveries) / len(recoverable_errors)
    
    def _generate_recommendations(self, errors: List[ErrorContext]) -> List[str]:
        """Generate recommendations based on error patterns."""
        
        recommendations = []
        
        # Analyze error patterns
        category_counts = defaultdict(int)
        for error in errors:
            category_counts[error.category] += 1
        
        # Generate specific recommendations
        if category_counts[ErrorCategory.NETWORK] > 10:
            recommendations.append("Consider implementing more robust network retry mechanisms")
        
        if category_counts[ErrorCategory.AI_SERVICE] > 5:
            recommendations.append("Review AI service rate limiting and error handling")
        
        if category_counts[ErrorCategory.DATABASE] > 3:
            recommendations.append("Investigate database performance and connection issues")
        
        return recommendations


# Global error handler instance
error_handler = ErrorHandlingManager()


def handle_error(func):
    """Decorator for automatic error handling."""
    
    async def async_wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            component = func.__module__.split('.')[-1]
            operation = func.__name__
            await error_handler.handle_error(e, component, operation)
            raise
    
    def sync_wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            component = func.__module__.split('.')[-1]
            operation = func.__name__
            error_handler.register_error(e, component, operation)
            raise
    
    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    else:
        return sync_wrapper
