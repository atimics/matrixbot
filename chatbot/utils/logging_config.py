"""
Enhanced logging configuration with structured logging support.

This module provides a centralized logging configuration that supports:
- JSON structured logging for production
- Human-readable logging for development
- Proper log levels and filtering
- Integration with monitoring systems
"""

import json
import logging
import logging.config
import os
import sys
from datetime import datetime
from typing import Any, Dict, Optional

import structlog
from pythonjsonlogger import jsonlogger


class StructuredFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter with additional context."""
    
    def add_fields(self, log_record: Dict[str, Any], record: logging.LogRecord, message_dict: Dict[str, Any]):
        super().add_fields(log_record, record, message_dict)
        
        # Add timestamp
        log_record['timestamp'] = datetime.utcnow().isoformat()
        
        # Add service information
        log_record['service'] = 'ratichat'
        log_record['version'] = os.getenv('APP_VERSION', 'unknown')
        
        # Add environment
        log_record['environment'] = os.getenv('ENVIRONMENT', 'development')
        
        # Add request ID if available (for tracing)
        request_id = getattr(record, 'request_id', None)
        if request_id:
            log_record['request_id'] = request_id
        
        # Add user context if available
        user_id = getattr(record, 'user_id', None)
        if user_id:
            log_record['user_id'] = user_id


class ColoredFormatter(logging.Formatter):
    """Colored formatter for development console output."""
    
    # Color codes
    COLORS = {
        'DEBUG': '\033[36m',     # Cyan
        'INFO': '\033[32m',      # Green
        'WARNING': '\033[33m',   # Yellow
        'ERROR': '\033[31m',     # Red
        'CRITICAL': '\033[35m',  # Magenta
    }
    RESET = '\033[0m'
    
    def format(self, record):
        log_color = self.COLORS.get(record.levelname, '')
        record.levelname = f"{log_color}{record.levelname}{self.RESET}"
        return super().format(record)


def setup_logging(
    log_level: str = "INFO",
    log_format: str = "text",
    log_file: Optional[str] = None,
    enable_request_logging: bool = True
) -> None:
    """
    Set up application logging with structured output.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: Output format ('json' for structured logging, 'text' for human-readable)
        log_file: Optional file path for log output
        enable_request_logging: Whether to enable HTTP request logging
    """
    
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer() if log_format == "json" else structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        context_class=dict,
        cache_logger_on_first_use=True,
    )
    
    # Configure standard logging
    handlers = []
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    if log_format == "json":
        console_handler.setFormatter(StructuredFormatter(
            '%(asctime)s %(name)s %(levelname)s %(message)s'
        ))
    else:
        console_handler.setFormatter(ColoredFormatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
    handlers.append(console_handler)
    
    # File handler if specified
    if log_file:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(StructuredFormatter(
            '%(asctime)s %(name)s %(levelname)s %(message)s'
        ))
        handlers.append(file_handler)
    
    # Root logger configuration
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        handlers=handlers,
        format='%(message)s'
    )
    
    # Reduce noise from third-party libraries
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('matrix').setLevel(logging.INFO)
    
    # Reduce noise from nio (Matrix Python SDK) - set all nio loggers to WARNING
    # This covers nio.rooms, nio.events, nio.client, nio.crypto, etc.
    logging.getLogger('nio').setLevel(logging.WARNING)
    
    # Enable request logging if specified
    if enable_request_logging:
        logging.getLogger('chatbot.api_server').setLevel(logging.INFO)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    Get a configured logger instance.
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        Configured logger instance
    """
    return structlog.get_logger(name)


def log_with_context(**context):
    """
    Decorator to add context to all log messages in a function.
    
    Usage:
        @log_with_context(user_id="123", request_id="abc")
        def my_function():
            logger.debug("This will include user_id and request_id")
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            logger = get_logger(func.__module__)
            with logger.bind(**context):
                return func(*args, **kwargs)
        return wrapper
    return decorator


# Performance monitoring
class PerformanceLogger:
    """Logger for performance metrics and monitoring."""
    
    def __init__(self):
        self.logger = get_logger("performance")
    
    def log_api_call(self, method: str, endpoint: str, duration_ms: float, status_code: int):
        """Log API call performance metrics."""
        self.logger.debug(
            "api_call",
            method=method,
            endpoint=endpoint,
            duration_ms=duration_ms,
            status_code=status_code,
            metric_type="api_performance"
        )
    
    def log_ai_generation(self, model: str, tokens: int, duration_ms: float, success: bool):
        """Log AI generation performance metrics."""
        self.logger.debug(
            "ai_generation",
            model=model,
            tokens=tokens,
            duration_ms=duration_ms,
            success=success,
            metric_type="ai_performance"
        )
    
    def log_database_query(self, query_type: str, duration_ms: float, rows_affected: int = 0):
        """Log database query performance metrics."""
        self.logger.debug(
            "database_query",
            query_type=query_type,
            duration_ms=duration_ms,
            rows_affected=rows_affected,
            metric_type="database_performance"
        )


# Global performance logger instance
performance_logger = PerformanceLogger()


# Initialize logging based on environment variables
def init_logging():
    """Initialize logging based on environment configuration."""
    log_level = os.getenv('LOG_LEVEL', 'INFO')
    log_format = os.getenv('LOG_FORMAT', 'text')
    log_file = os.getenv('LOG_FILE')
    
    setup_logging(
        log_level=log_level,
        log_format=log_format,
        log_file=log_file
    )


# Auto-initialize if this module is imported
if __name__ != "__main__":
    init_logging()
