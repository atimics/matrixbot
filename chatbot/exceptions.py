"""
Custom Exception Classes

This module defines custom exceptions for the chatbot application
to provide better error handling and debugging information.
"""

from typing import Optional


class ChatbotBaseException(Exception):
    """Base exception for the chatbot application."""

    pass


class ActionExecutionError(ChatbotBaseException):
    """Raised when an action fails to execute."""

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
        details = f"Error executing action '{action_type}' with params {params}: {original_error}"
        if message:
            super().__init__(f"{message} - Details: {details}")
        else:
            super().__init__(details)


class MatrixIntegrationError(ChatbotBaseException):
    """Raised for errors specific to Matrix integration."""

    pass


class AIResponseError(ChatbotBaseException):
    """Raised for errors in processing AI responses."""

    pass


class ConfigurationError(ChatbotBaseException):
    """Raised for configuration problems."""

    pass


class FarcasterIntegrationError(ChatbotBaseException):
    """Raised for errors specific to Farcaster integration."""

    pass
