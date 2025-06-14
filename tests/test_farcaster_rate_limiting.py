#!/usr/bin/env python3
"""
Test Farcaster Rate Limiting and Context Features

This test verifies that the Farcaster rate limiting and context improvements work correctly.
"""

import pytest
import asyncio
import time
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime, timedelta

from chatbot.integrations.farcaster.farcaster_observer import FarcasterObserver
from chatbot.tools.farcaster_tools import SendFarcasterPostTool
from chatbot.tools.base import ActionContext
from chatbot.core.world_state.payload_builder import PayloadBuilder
from chatbot.core.world_state.structures import WorldStateData


class TestFarcasterRateLimiting:
    """Test enhanced Farcaster rate limiting functionality."""

    @pytest.fixture
    def mock_observer(self):
        """Create a mock Farcaster observer with rate limiting capabilities."""
        observer = Mock(spec=FarcasterObserver)
        observer.api_client = AsyncMock()
        observer.bot_fid = "12345"
        observer.signer_uuid = "test-signer"
        
        # Mock the new rate limiting methods
        observer.get_recent_own_posts = AsyncMock()
        observer.check_post_timing = AsyncMock()
        observer.check_similar_recent_post = AsyncMock()
        observer._content_similarity = Mock()
        
        return observer

    @pytest.fixture
    def mock_context(self, mock_observer):
        """Create a mock action context."""
        context = Mock(spec=ActionContext)
        context.farcaster_observer = mock_observer
        context.world_state_manager = Mock()
        context.world_state_manager.has_sent_farcaster_post.return_value = False
        return context

    @pytest.mark.asyncio
    async def test_get_recent_own_posts(self, mock_observer):
        """Test fetching recent own posts."""
        # Setup mock API response
        mock_observer.api_client.get_casts_by_fid.return_value = {
            "casts": [
                {
                    "hash": "0x123",
                    "text": "Test post 1",
                    "timestamp": "2025-06-13T18:00:00Z",
                    "author": {"fid": "12345"}
                },
                {
                    "hash": "0x456", 
                    "text": "Test post 2",
                    "timestamp": "2025-06-13T17:30:00Z",
                    "author": {"fid": "12345"}
                }
            ]
        }
        
        # Create real observer instance for this test
        observer = FarcasterObserver(api_key="test", bot_fid="12345")
        observer.api_client = mock_observer.api_client
        
        # Test the method
        recent_posts = await observer.get_recent_own_posts(limit=2)
        
        assert len(recent_posts) == 2
        assert recent_posts[0]["hash"] == "0x123"
        assert recent_posts[0]["text"] == "Test post 1"
        assert recent_posts[1]["hash"] == "0x456"
        mock_observer.api_client.get_casts_by_fid.assert_called_once_with(fid="12345", limit=2)

    @pytest.mark.asyncio
    async def test_check_post_timing_can_post(self, mock_observer):
        """Test timing check when posting is allowed."""
        # Mock recent posts with old timestamp (more than 5 minutes ago)
        old_time = datetime.now().isoformat() + "Z"
        mock_observer.get_recent_own_posts.return_value = [
            {
                "timestamp": "2025-06-13T17:00:00Z",  # Old post
                "text": "Old post"
            }
        ]
        
        observer = FarcasterObserver(api_key="test", bot_fid="12345")
        observer.get_recent_own_posts = mock_observer.get_recent_own_posts
        
        with patch('chatbot.integrations.farcaster.farcaster_observer.settings') as mock_settings:
            mock_settings.FARCASTER_MIN_POST_INTERVAL_MINUTES = 1
            
            result = await observer.check_post_timing()
            
            assert result["can_post"] is True

    @pytest.mark.asyncio
    async def test_check_post_timing_rate_limited(self, mock_observer):
        """Test timing check when rate limited."""
        # Mock recent posts with very recent timestamp
        recent_time = datetime.now().isoformat() + "Z"
        mock_observer.get_recent_own_posts.return_value = [
            {
                "timestamp": recent_time,
                "text": "Very recent post"
            }
        ]
        
        observer = FarcasterObserver(api_key="test", bot_fid="12345")
        observer.get_recent_own_posts = mock_observer.get_recent_own_posts
        
        with patch('chatbot.integrations.farcaster.farcaster_observer.settings') as mock_settings:
            mock_settings.FARCASTER_MIN_POST_INTERVAL_MINUTES = 1
            
            result = await observer.check_post_timing()
            
            assert result["can_post"] is False
            assert "time_remaining_seconds" in result
            assert "minutes_remaining" in result
            assert "time_remaining_formatted" in result  # New formatted field

    @pytest.mark.asyncio
    async def test_timing_message_formatting(self, mock_observer):
        """Test that timing messages are formatted correctly for different durations."""
        # Test with recent timestamp that should trigger rate limiting
        recent_time = (datetime.now() - timedelta(seconds=30)).isoformat() + "Z"
        mock_observer.get_recent_own_posts.return_value = [
            {
                "timestamp": recent_time,
                "text": "Recent post"
            }
        ]
        
        observer = FarcasterObserver(api_key="test", bot_fid="12345")
        observer.get_recent_own_posts = mock_observer.get_recent_own_posts
        
        with patch('chatbot.integrations.farcaster.farcaster_observer.settings') as mock_settings:
            mock_settings.FARCASTER_MIN_POST_INTERVAL_MINUTES = 1
            
            result = await observer.check_post_timing()
            
            assert result["can_post"] is False
            # Should show seconds for short durations
            assert "second(s)" in result["time_remaining_formatted"]

    @pytest.mark.asyncio
    async def test_check_similar_recent_post(self, mock_observer):
        """Test duplicate content detection."""
        mock_observer.get_recent_own_posts.return_value = [
            {
                "timestamp": datetime.now().isoformat() + "Z",
                "text": "Hello world this is a test post"
            }
        ]
        
        observer = FarcasterObserver(api_key="test", bot_fid="12345")
        observer.get_recent_own_posts = mock_observer.get_recent_own_posts
        
        # Mock content similarity to return high similarity
        observer._content_similarity = Mock(return_value=0.8)
        
        with patch('chatbot.integrations.farcaster.farcaster_observer.settings') as mock_settings:
            mock_settings.FARCASTER_DUPLICATE_CHECK_HOURS = 1
            mock_settings.FARCASTER_RECENT_POSTS_LIMIT = 10
            
            # Test with similar content
            is_similar = await observer.check_similar_recent_post("Hello world this is a test message")
            
            assert is_similar is True

    @pytest.mark.asyncio
    async def test_content_similarity_calculation(self):
        """Test content similarity calculation."""
        observer = FarcasterObserver(api_key="test", bot_fid="12345")
        
        # Test identical content
        similarity = observer._content_similarity("hello world", "hello world")
        assert similarity == 1.0
        
        # Test completely different content
        similarity = observer._content_similarity("hello world", "foo bar")
        assert similarity == 0.0
        
        # Test partially similar content
        similarity = observer._content_similarity("hello world test", "hello world example")
        assert similarity > 0.5 and similarity < 1.0

    @pytest.mark.asyncio
    async def test_send_farcaster_post_rate_limited(self, mock_context):
        """Test that SendFarcasterPostTool respects rate limits."""
        tool = SendFarcasterPostTool()
        
        # Mock rate limiting check to return rate limited
        mock_context.farcaster_observer.check_post_timing.return_value = {
            "can_post": False,
            "minutes_remaining": 3.5,
            "time_remaining_seconds": 210
        }
        
        params = {"content": "Test post content"}
        result = await tool.execute(params, mock_context)
        
        assert result["status"] == "failure"
        assert "rate_limited" in result["action"]
        assert "3.5" in result["error"]

    @pytest.mark.asyncio
    async def test_send_farcaster_post_duplicate_detected(self, mock_context):
        """Test that SendFarcasterPostTool detects duplicates."""
        tool = SendFarcasterPostTool()
        
        # Mock timing check to pass but duplicate check to fail
        mock_context.farcaster_observer.check_post_timing.return_value = {"can_post": True}
        mock_context.farcaster_observer.check_similar_recent_post.return_value = True
        
        params = {"content": "Test post content"}
        result = await tool.execute(params, mock_context)
        
        assert result["status"] == "failure"
        assert "duplicate_prevention" in result["action"]
        assert "similar post" in result["error"].lower()

    def test_farcaster_context_in_payload(self):
        """Test that Farcaster context is included in payload."""
        builder = PayloadBuilder()
        world_state_data = WorldStateData()
        
        # Add some rate limit data
        world_state_data.rate_limits = {
            "farcaster_api": {
                "remaining": 245,
                "limit": 300,
                "reset_time": 1672531200,
                "last_updated": time.time()
            }
        }
        
        payload = builder.build_full_payload(world_state_data)
        
        assert "farcaster_context" in payload
        farcaster_context = payload["farcaster_context"]
        assert "rate_limits" in farcaster_context
        assert farcaster_context["rate_limits"]["remaining"] == 245
        assert farcaster_context["can_post_now"] is True

    def test_farcaster_node_paths_generation(self):
        """Test that Farcaster node paths include rate limiting nodes."""
        builder = PayloadBuilder()
        world_state_data = WorldStateData()
        
        # Add a Farcaster channel to trigger path generation
        from chatbot.core.world_state.structures import Channel
        farcaster_channel = Channel(
            id="farcaster:home",
            name="Farcaster Home",
            type="farcaster"
        )
        world_state_data.channels = {
            "farcaster": {"farcaster:home": farcaster_channel}
        }
        
        paths = list(builder._generate_farcaster_feed_paths(world_state_data))
        
        assert "farcaster.rate_limits" in paths
        assert "farcaster.recent_posts" in paths
        assert "farcaster.feeds.home" in paths


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
