#!/usr/bin/env python3
"""
Tests for PHASE 1.2 Enhanced Farcaster Content Discovery & Proactive Engagement tools.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
import time

from chatbot.tools.farcaster_tools import (
    GetUserTimelineTool,
    SearchCastsTool,
    GetTrendingCastsTool,
    GetCastByUrlTool,
)
from chatbot.tools.base import ActionContext


@pytest.fixture
def mock_context():
    """Create a mock ActionContext with a FarcasterObserver."""
    context = MagicMock(spec=ActionContext)
    context.farcaster_observer = AsyncMock()
    context.world_state_manager = None
    return context


@pytest.fixture
def sample_cast_data():
    """Sample cast data structure."""
    return {
        "id": "cast123",
        "content": "This is a test cast",
        "user": {
            "fid": 123,
            "username": "testuser",
            "display_name": "Test User"
        },
        "timestamp": int(time.time()),
        "hash": "0xabcdef123456",
        "reactions": {"likes": 5, "recasts": 2},
        "replies": 0
    }


class TestGetUserTimelineTool:
    """Test the GetUserTimelineTool."""

    @pytest.fixture
    def tool(self):
        return GetUserTimelineTool()

    def test_tool_properties(self, tool):
        assert tool.name == "get_user_timeline"
        assert "timeline" in tool.description.lower()
        assert "user_identifier" in tool.parameters_schema
        assert "limit" in tool.parameters_schema

    @pytest.mark.asyncio
    async def test_execute_success_with_username(self, tool, mock_context, sample_cast_data):
        # Setup mock response
        mock_context.farcaster_observer.get_user_casts.return_value = {
            "success": True,
            "casts": [sample_cast_data],
            "error": None
        }

        params = {"user_identifier": "testuser", "limit": 5}
        result = await tool.execute(params, mock_context)

        assert result["status"] == "success"
        assert result["user_identifier"] == "testuser"
        assert len(result["casts"]) == 1
        assert result["casts"][0] == sample_cast_data
        mock_context.farcaster_observer.get_user_casts.assert_called_once_with(
            user_identifier="testuser", limit=5
        )

    @pytest.mark.asyncio
    async def test_execute_success_with_fid(self, tool, mock_context, sample_cast_data):
        # Setup mock response
        mock_context.farcaster_observer.get_user_casts.return_value = {
            "success": True,
            "casts": [sample_cast_data],
            "error": None
        }

        params = {"user_identifier": "123"}
        result = await tool.execute(params, mock_context)

        assert result["status"] == "success"
        assert result["user_identifier"] == "123"
        mock_context.farcaster_observer.get_user_casts.assert_called_once_with(
            user_identifier="123", limit=10  # default limit
        )

    @pytest.mark.asyncio
    async def test_execute_missing_user_identifier(self, tool, mock_context):
        params = {"limit": 5}
        result = await tool.execute(params, mock_context)

        assert result["status"] == "failure"
        assert "user_identifier" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_no_farcaster_observer(self, tool):
        context = MagicMock(spec=ActionContext)
        context.farcaster_observer = None
        
        params = {"user_identifier": "testuser"}
        result = await tool.execute(params, context)

        assert result["status"] == "failure"
        assert "not configured" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_observer_error(self, tool, mock_context):
        # Setup mock to return error
        mock_context.farcaster_observer.get_user_casts.return_value = {
            "success": False,
            "casts": [],
            "error": "User not found"
        }

        params = {"user_identifier": "nonexistent"}
        result = await tool.execute(params, mock_context)

        assert result["status"] == "failure"
        assert "User not found" in result["error"]


class TestSearchCastsTool:
    """Test the SearchCastsTool."""

    @pytest.fixture
    def tool(self):
        return SearchCastsTool()

    def test_tool_properties(self, tool):
        assert tool.name == "search_casts"
        assert "search" in tool.description.lower()
        assert "query" in tool.parameters_schema
        assert "channel_id" in tool.parameters_schema
        assert "limit" in tool.parameters_schema

    @pytest.mark.asyncio
    async def test_execute_success_with_channel(self, tool, mock_context, sample_cast_data):
        # Setup mock response
        mock_context.farcaster_observer.search_casts.return_value = {
            "success": True,
            "casts": [sample_cast_data],
            "error": None
        }

        params = {"query": "AI development", "channel_id": "dev", "limit": 3}
        result = await tool.execute(params, mock_context)

        assert result["status"] == "success"
        assert result["query"] == "AI development"
        assert result["channel_id"] == "dev"
        assert len(result["casts"]) == 1
        mock_context.farcaster_observer.search_casts.assert_called_once_with(
            query="AI development", channel_id="dev", limit=3
        )

    @pytest.mark.asyncio
    async def test_execute_success_without_channel(self, tool, mock_context, sample_cast_data):
        # Setup mock response
        mock_context.farcaster_observer.search_casts.return_value = {
            "success": True,
            "casts": [sample_cast_data],
            "error": None
        }

        params = {"query": "blockchain"}
        result = await tool.execute(params, mock_context)

        assert result["status"] == "success"
        assert result["query"] == "blockchain"
        assert result["channel_id"] is None
        mock_context.farcaster_observer.search_casts.assert_called_once_with(
            query="blockchain", channel_id=None, limit=10
        )

    @pytest.mark.asyncio
    async def test_execute_missing_query(self, tool, mock_context):
        params = {"channel_id": "dev"}
        result = await tool.execute(params, mock_context)

        assert result["status"] == "failure"
        assert "query" in result["error"]


class TestGetTrendingCastsTool:
    """Test the GetTrendingCastsTool."""

    @pytest.fixture
    def tool(self):
        return GetTrendingCastsTool()

    def test_tool_properties(self, tool):
        assert tool.name == "get_trending_casts"
        assert "trending" in tool.description.lower()
        assert "channel_id" in tool.parameters_schema
        assert "timeframe_hours" in tool.parameters_schema
        assert "limit" in tool.parameters_schema

    @pytest.mark.asyncio
    async def test_execute_success_with_channel(self, tool, mock_context, sample_cast_data):
        # Setup mock response
        mock_context.farcaster_observer.get_trending_casts.return_value = {
            "success": True,
            "casts": [sample_cast_data],
            "error": None
        }

        params = {"channel_id": "memes", "timeframe_hours": 6, "limit": 5}
        result = await tool.execute(params, mock_context)

        assert result["status"] == "success"
        assert result["channel_id"] == "memes"
        assert result["timeframe_hours"] == 6
        assert len(result["casts"]) == 1
        mock_context.farcaster_observer.get_trending_casts.assert_called_once_with(
            channel_id="memes", timeframe_hours=6, limit=5
        )

    @pytest.mark.asyncio
    async def test_execute_success_global_trending(self, tool, mock_context, sample_cast_data):
        # Setup mock response
        mock_context.farcaster_observer.get_trending_casts.return_value = {
            "success": True,
            "casts": [sample_cast_data],
            "error": None
        }

        params = {}  # Use all defaults
        result = await tool.execute(params, mock_context)

        assert result["status"] == "success"
        assert result["channel_id"] is None
        assert result["timeframe_hours"] == 24  # default
        mock_context.farcaster_observer.get_trending_casts.assert_called_once_with(
            channel_id=None, timeframe_hours=24, limit=10
        )


class TestGetCastByUrlTool:
    """Test the GetCastByUrlTool."""

    @pytest.fixture
    def tool(self):
        return GetCastByUrlTool()

    def test_tool_properties(self, tool):
        assert tool.name == "get_cast_by_url"
        assert "url" in tool.description.lower()
        assert "farcaster_url" in tool.parameters_schema

    @pytest.mark.asyncio
    async def test_execute_success(self, tool, mock_context, sample_cast_data):
        # Setup mock response
        mock_context.farcaster_observer.get_cast_by_url.return_value = {
            "success": True,
            "cast": sample_cast_data,
            "error": None
        }

        url = "https://warpcast.com/testuser/0xabcdef123456"
        params = {"farcaster_url": url}
        result = await tool.execute(params, mock_context)

        assert result["status"] == "success"
        assert result["url"] == url
        assert result["cast"] == sample_cast_data
        mock_context.farcaster_observer.get_cast_by_url.assert_called_once_with(
            farcaster_url=url
        )

    @pytest.mark.asyncio
    async def test_execute_invalid_url(self, tool, mock_context):
        # Setup mock response for invalid URL
        mock_context.farcaster_observer.get_cast_by_url.return_value = {
            "success": False,
            "cast": None,
            "error": "Invalid Farcaster URL"
        }

        url = "https://invalid-url.com"
        params = {"farcaster_url": url}
        result = await tool.execute(params, mock_context)

        assert result["status"] == "failure"
        assert "Invalid Farcaster URL" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_missing_url(self, tool, mock_context):
        params = {}
        result = await tool.execute(params, mock_context)

        assert result["status"] == "failure"
        assert "farcaster_url" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_cast_not_found(self, tool, mock_context):
        # Setup mock response for cast not found
        mock_context.farcaster_observer.get_cast_by_url.return_value = {
            "success": False,
            "cast": None,
            "error": "Cast not found"
        }

        url = "https://warpcast.com/testuser/0xnonexistent"
        params = {"farcaster_url": url}
        result = await tool.execute(params, mock_context)

        assert result["status"] == "failure"
        assert "Cast not found" in result["error"]


@pytest.mark.asyncio
async def test_integration_content_discovery_workflow(mock_context, sample_cast_data):
    """Test an integrated workflow using multiple content discovery tools."""
    
    # Setup tools
    user_timeline_tool = GetUserTimelineTool()
    search_tool = SearchCastsTool()
    trending_tool = GetTrendingCastsTool()
    url_tool = GetCastByUrlTool()
    
    # Mock responses
    mock_context.farcaster_observer.get_user_casts.return_value = {
        "success": True, "casts": [sample_cast_data], "error": None
    }
    mock_context.farcaster_observer.search_casts.return_value = {
        "success": True, "casts": [sample_cast_data], "error": None
    }
    mock_context.farcaster_observer.get_trending_casts.return_value = {
        "success": True, "casts": [sample_cast_data], "error": None
    }
    mock_context.farcaster_observer.get_cast_by_url.return_value = {
        "success": True, "cast": sample_cast_data, "error": None
    }
    
    # 1. Get user timeline
    timeline_result = await user_timeline_tool.execute(
        {"user_identifier": "dwr.eth", "limit": 5}, mock_context
    )
    assert timeline_result["status"] == "success"
    
    # 2. Search for relevant content
    search_result = await search_tool.execute(
        {"query": "AI development", "channel_id": "dev"}, mock_context
    )
    assert search_result["status"] == "success"
    
    # 3. Get trending content
    trending_result = await trending_tool.execute(
        {"channel_id": "memes", "timeframe_hours": 6}, mock_context
    )
    assert trending_result["status"] == "success"
    
    # 4. Resolve cast from URL
    url_result = await url_tool.execute(
        {"farcaster_url": "https://warpcast.com/dwr/0xabcdef"}, mock_context
    )
    assert url_result["status"] == "success"
    
    # Verify all tools were called
    assert mock_context.farcaster_observer.get_user_casts.called
    assert mock_context.farcaster_observer.search_casts.called
    assert mock_context.farcaster_observer.get_trending_casts.called
    assert mock_context.farcaster_observer.get_cast_by_url.called
