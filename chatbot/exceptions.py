"""
Custom Exception Classes

This module defines custom exceptions for the chatbot application
to provide better error handling and debugging information.
"""

from typing import Dict, Any, Optional


class ChatbotBaseException(Exception):
    """Base exception for the chatbot application."""
    
    error_code: str = "CHATBOT_ERROR"
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for logging/API responses."""
        return {
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details,
            "type": self.__class__.__name__
        }


class ActionExecutionError(ChatbotBaseException):
    """Raised when an action fails to execute."""
    
    error_code = "ACTION_EXECUTION_ERROR"

    def __init__(
        self,
        action_type: str,
        params: dict,
        original_error: Exception,
        message: Optional[str] = None,
    ):
        self.action_type = action_type
        self.params = params
        self.original_error = original_error
        details = {
            "action_type": action_type,
            "params": params,
            "original_error": str(original_error)
        }
        error_msg = f"Error executing action '{action_type}': {original_error}"
        if message:
            error_msg = f"{message} - {error_msg}"
        super().__init__(error_msg, details)


class MatrixIntegrationError(ChatbotBaseException):
    """Raised for errors specific to Matrix integration."""
    error_code = "MATRIX_INTEGRATION_ERROR"


class AIResponseError(ChatbotBaseException):
    """Raised for errors in processing AI responses."""
    error_code = "AI_RESPONSE_ERROR"


class ConfigurationError(ChatbotBaseException):
    """Raised for configuration problems."""
    error_code = "CONFIG_ERROR"


class IntegrationError(ChatbotBaseException):
    """External service integration errors."""
    error_code = "INTEGRATION_ERROR"
    
    def __init__(self, service: str, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, details)
        self.service = service
        if details is None:
            self.details = {}
        self.details["service"] = service


class AIEngineError(ChatbotBaseException):
    """AI processing errors."""
    error_code = "AI_ERROR"


class ToolExecutionError(ChatbotBaseException):
    """Tool execution failures."""
    error_code = "TOOL_ERROR"
    
    def __init__(self, tool_name: str, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, details)
        self.tool_name = tool_name
        if details is None:
            self.details = {}
        self.details["tool_name"] = tool_name


class DatabaseError(ChatbotBaseException):
    """Database operation errors."""
    error_code = "DATABASE_ERROR"


class AuthenticationError(ChatbotBaseException):
    """Authentication and authorization errors."""
    error_code = "AUTH_ERROR"


class RateLimitError(ChatbotBaseException):
    """Rate limiting errors."""
    error_code = "RATE_LIMIT_ERROR"
    
    def __init__(self, message: str, retry_after: Optional[int] = None, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, details)
        self.retry_after = retry_after
        if details is None:
            self.details = {}
        if retry_after is not None:
            self.details["retry_after"] = retry_after


class ValidationError(ChatbotBaseException):
    """Input validation errors."""
    error_code = "VALIDATION_ERROR"


class TimeoutError(ChatbotBaseException):
    """Operation timeout errors."""
    error_code = "TIMEOUT_ERROR"


class FarcasterIntegrationError(ChatbotBaseException):
    """Raised for errors specific to Farcaster integration."""

    pass
