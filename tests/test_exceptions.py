"""
Test suite for custom exception classes.
"""

import pytest
from unittest.mock import Mock

from chatbot.exceptions import (
    ChatbotBaseException,
    ActionExecutionError,
    MatrixIntegrationError,
    AIResponseError,
    ConfigurationError,
    FarcasterIntegrationError
)


class TestChatbotBaseException:
    """Test the base exception class."""
    
    def test_inheritance(self):
        """Test that ChatbotBaseException inherits from Exception."""
        exc = ChatbotBaseException("test message")
        assert isinstance(exc, Exception)
        assert str(exc) == "test message"
    
    def test_custom_message(self):
        """Test custom message handling."""
        message = "Custom error message"
        exc = ChatbotBaseException(message)
        assert str(exc) == message


class TestActionExecutionError:
    """Test ActionExecutionError handling."""
    
    def test_basic_creation(self):
        """Test basic error creation."""
        action_type = "send_message"
        params = {"content": "test"}
        original_error = ValueError("Original error")
        
        exc = ActionExecutionError(action_type, params, original_error)
        
        assert exc.action_type == action_type
        assert exc.params == params
        assert exc.original_error == original_error
        assert action_type in str(exc)
        assert "test" in str(exc)
        assert "Original error" in str(exc)
    
    def test_with_custom_message(self):
        """Test error creation with custom message."""
        action_type = "send_message"
        params = {"content": "test"}
        original_error = ValueError("Original error")
        custom_message = "Custom failure message"
        
        exc = ActionExecutionError(
            action_type, params, original_error, custom_message
        )
        
        assert custom_message in str(exc)
        assert "Details:" in str(exc)
    
    def test_inheritance(self):
        """Test inheritance from ChatbotBaseException."""
        exc = ActionExecutionError("test", {}, Exception())
        assert isinstance(exc, ChatbotBaseException)
        assert isinstance(exc, Exception)
    
    def test_empty_params(self):
        """Test with empty parameters."""
        exc = ActionExecutionError("test_action", {}, ValueError("test"))
        assert exc.params == {}
        assert "test_action" in str(exc)
    
    def test_complex_params(self):
        """Test with complex parameter structure."""
        params = {
            "nested": {"key": "value"},
            "list": [1, 2, 3],
            "string": "test"
        }
        exc = ActionExecutionError("complex_action", params, RuntimeError("complex"))
        assert exc.params == params
        # Ensure params are represented in string format
        assert "nested" in str(exc)


class TestMatrixIntegrationError:
    """Test Matrix-specific error handling."""
    
    def test_creation(self):
        """Test basic creation."""
        message = "Matrix connection failed"
        exc = MatrixIntegrationError(message)
        assert str(exc) == message
        assert isinstance(exc, ChatbotBaseException)
    
    def test_inheritance_chain(self):
        """Test full inheritance chain."""
        exc = MatrixIntegrationError("test")
        assert isinstance(exc, MatrixIntegrationError)
        assert isinstance(exc, ChatbotBaseException)
        assert isinstance(exc, Exception)


class TestAIResponseError:
    """Test AI response error handling."""
    
    def test_creation(self):
        """Test basic creation."""
        message = "Invalid AI response format"
        exc = AIResponseError(message)
        assert str(exc) == message
        assert isinstance(exc, ChatbotBaseException)
    
    def test_json_parsing_scenario(self):
        """Test typical JSON parsing error scenario."""
        message = "Failed to parse JSON: Invalid format"
        exc = AIResponseError(message)
        assert "JSON" in str(exc)
        assert "Invalid format" in str(exc)


class TestConfigurationError:
    """Test configuration error handling."""
    
    def test_creation(self):
        """Test basic creation."""
        message = "Missing required configuration: API_KEY"
        exc = ConfigurationError(message)
        assert str(exc) == message
        assert isinstance(exc, ChatbotBaseException)
    
    def test_missing_env_var_scenario(self):
        """Test missing environment variable scenario."""
        message = "Environment variable MATRIX_PASSWORD not set"
        exc = ConfigurationError(message)
        assert "MATRIX_PASSWORD" in str(exc)
        assert "not set" in str(exc)


class TestFarcasterIntegrationError:
    """Test Farcaster-specific error handling."""
    
    def test_creation(self):
        """Test basic creation."""
        message = "Farcaster API rate limit exceeded"
        exc = FarcasterIntegrationError(message)
        assert str(exc) == message
        assert isinstance(exc, ChatbotBaseException)
    
    def test_api_error_scenario(self):
        """Test API error scenario."""
        message = "Neynar API returned 429: Rate limit exceeded"
        exc = FarcasterIntegrationError(message)
        assert "429" in str(exc)
        assert "Rate limit" in str(exc)


class TestExceptionUsagePatterns:
    """Test common exception usage patterns."""
    
    def test_exception_chaining(self):
        """Test exception chaining patterns."""
        try:
            raise ValueError("Original problem")
        except ValueError as e:
            action_error = ActionExecutionError("test_action", {}, e)
            assert action_error.original_error == e
            assert isinstance(action_error.__cause__, type(None))  # Not chained by default
    
    def test_exception_with_cause(self):
        """Test exception with explicit cause."""
        original = ValueError("Root cause")
        try:
            raise MatrixIntegrationError("Integration failed") from original
        except MatrixIntegrationError as e:
            assert e.__cause__ == original
    
    def test_reraise_pattern(self):
        """Test common re-raise pattern."""
        def problematic_function():
            raise ValueError("Something went wrong")
        
        def wrapper_function():
            try:
                problematic_function()
            except ValueError as e:
                raise ActionExecutionError("wrapper_action", {"test": True}, e)
        
        with pytest.raises(ActionExecutionError) as exc_info:
            wrapper_function()
        
        assert exc_info.value.action_type == "wrapper_action"
        assert isinstance(exc_info.value.original_error, ValueError)
    
    def test_multiple_exception_types(self):
        """Test handling multiple exception types."""
        exceptions = [
            MatrixIntegrationError("Matrix error"),
            FarcasterIntegrationError("Farcaster error"),
            AIResponseError("AI error"),
            ConfigurationError("Config error")
        ]
        
        for exc in exceptions:
            assert isinstance(exc, ChatbotBaseException)
            # Test that each has its specific type
            assert type(exc).__name__ in str(type(exc))
    
    @pytest.mark.error_handling
    def test_exception_in_async_context(self):
        """Test exceptions work properly in async contexts."""
        async def async_function():
            raise MatrixIntegrationError("Async error")
        
        async def test_async():
            with pytest.raises(MatrixIntegrationError):
                await async_function()
        
        # This would be run in an actual async test
        import asyncio
        asyncio.run(test_async())
    
    def test_exception_serialization(self):
        """Test that exceptions can be converted to strings properly."""
        exc = ActionExecutionError(
            "test_action",
            {"param1": "value1", "param2": 123},
            RuntimeError("Original error message")
        )
        
        exc_str = str(exc)
        assert "test_action" in exc_str
        assert "param1" in exc_str
        assert "value1" in exc_str
        assert "Original error message" in exc_str
        
        # Test that we can recreate meaningful information from string
        assert len(exc_str) > 10  # Should be substantial
        assert exc_str != "ActionExecutionError"  # Should not be just class name
