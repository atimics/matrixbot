"""
Test the enhanced rate limiting functionality in NeynarAPIClient.
"""
import pytest
import time
from unittest.mock import Mock, patch
from chatbot.integrations.farcaster.neynar_api_client import NeynarAPIClient


class MockResponse:
    """Mock HTTP response with headers and status code."""
    def __init__(self, status_code=200, headers=None):
        self.status_code = status_code
        self.headers = headers or {}


@pytest.fixture
def api_client():
    """Create a NeynarAPIClient instance for testing."""
    return NeynarAPIClient(api_key="test_key")


class TestNeynarRateLimiting:
    """Test enhanced rate limiting functionality."""

    def test_update_rate_limits_basic(self, api_client):
        """Test basic rate limit header parsing."""
        headers = {
            'x-ratelimit-limit': '100',
            'x-ratelimit-remaining': '50',
            'x-ratelimit-reset': '1640995200'  # 2022-01-01 00:00:00 UTC
        }
        response = MockResponse(headers=headers)
        
        api_client._update_rate_limits(response)
        
        rate_info = api_client.rate_limit_info
        assert rate_info['limit'] == 100
        assert rate_info['remaining'] == 50
        assert rate_info['reset'] == 1640995200  # Field is 'reset', not 'reset_time'
        assert 'retry_after' not in rate_info

    def test_update_rate_limits_with_retry_after(self, api_client):
        """Test rate limit parsing with retry-after header."""
        headers = {
            'x-ratelimit-limit': '100',
            'x-ratelimit-remaining': '0',
            'x-ratelimit-reset': '1640995200',
            'x-ratelimit-retry-after': '300'  # 5 minutes
        }
        response = MockResponse(headers=headers)
        
        api_client._update_rate_limits(response)
        
        rate_info = api_client.rate_limit_info
        assert rate_info['limit'] == 100
        assert rate_info['remaining'] == 0
        assert rate_info['reset'] == 1640995200  # Field is 'reset', not 'reset_time'
        assert rate_info['retry_after'] == 300

    def test_update_rate_limits_with_standard_retry_after(self, api_client):
        """Test rate limit parsing with standard retry-after header."""
        headers = {
            'x-ratelimit-limit': '100',
            'x-ratelimit-remaining': '5',
            'x-ratelimit-reset': '1640995200',
            'retry-after': '120'  # 2 minutes
        }
        response = MockResponse(headers=headers)
        
        api_client._update_rate_limits(response)
        
        rate_info = api_client.rate_limit_info
        assert rate_info['limit'] == 100
        assert rate_info['remaining'] == 5
        assert rate_info['reset'] == 1640995200  # Field is 'reset', not 'reset_time'
        assert rate_info['retry_after'] == 120

    @patch('chatbot.integrations.farcaster.neynar_api_client.logger')
    def test_rate_limit_warning_low_remaining(self, mock_logger, api_client):
        """Test warning log when remaining requests are very low."""
        headers = {
            'x-ratelimit-limit': '100',
            'x-ratelimit-remaining': '5',  # Low remaining
            'x-ratelimit-reset': '1640995200'
        }
        response = MockResponse(headers=headers)
        
        api_client._update_rate_limits(response)
        
        # Should log warning for low remaining requests
        mock_logger.warning.assert_called_once()
        warning_call = mock_logger.warning.call_args[0][0]
        assert "Farcaster API rate limit approaching" in warning_call
        assert "5 requests remaining" in warning_call

    @patch('chatbot.integrations.farcaster.neynar_api_client.logger')
    def test_rate_limit_info_moderate_remaining(self, mock_logger, api_client):
        """Test info log when remaining requests are moderate."""
        headers = {
            'x-ratelimit-limit': '100',
            'x-ratelimit-remaining': '25',  # Moderate remaining
            'x-ratelimit-reset': '1640995200'
        }
        response = MockResponse(headers=headers)
        
        api_client._update_rate_limits(response)
        
        # Should log info for moderate remaining requests
        mock_logger.info.assert_called_once()
        info_call = mock_logger.info.call_args[0][0]
        assert "Farcaster API rate limit status" in info_call
        assert "25 requests remaining" in info_call

    @patch('chatbot.integrations.farcaster.neynar_api_client.logger')
    def test_rate_limit_no_warning_high_remaining(self, mock_logger, api_client):
        """Test no warning/info log when remaining requests are high."""
        headers = {
            'x-ratelimit-limit': '100',
            'x-ratelimit-remaining': '75',  # High remaining
            'x-ratelimit-reset': '1640995200'
        }
        response = MockResponse(headers=headers)
        
        api_client._update_rate_limits(response)
        
        # Should not log warning or info for high remaining requests
        mock_logger.warning.assert_not_called()
        mock_logger.info.assert_not_called()

    def test_rate_limit_invalid_headers(self, api_client):
        """Test handling of invalid or missing headers."""
        headers = {
            'x-ratelimit-limit': 'invalid',
            'x-ratelimit-remaining': 'also-invalid'
        }
        response = MockResponse(headers=headers)
        
        # Should not raise exception on invalid headers
        api_client._update_rate_limits(response)
        
        # rate_limit_info should remain unchanged or have default values
        assert api_client.rate_limit_info is not None

    def test_rate_limit_missing_headers(self, api_client):
        """Test handling when rate limit headers are completely missing."""
        headers = {}  # No rate limit headers
        response = MockResponse(headers=headers)
        
        # Should not raise exception on missing headers
        api_client._update_rate_limits(response)
        
        # rate_limit_info should remain unchanged or have default values
        assert api_client.rate_limit_info is not None

    def test_rate_limit_timestamp_update(self, api_client):
        """Test that last_updated timestamp is properly set."""
        headers = {
            'x-ratelimit-limit': '100',
            'x-ratelimit-remaining': '50',
            'x-ratelimit-reset': '1640995200'
        }
        response = MockResponse(headers=headers)
        
        before_time = time.time()
        api_client._update_rate_limits(response)
        after_time = time.time()
        
        rate_info = api_client.rate_limit_info
        assert 'last_updated_client' in rate_info  # Field is 'last_updated_client', not 'last_updated'
        assert before_time <= rate_info['last_updated_client'] <= after_time
