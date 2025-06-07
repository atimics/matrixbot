import pytest
import time
from unittest.mock import AsyncMock
from chatbot.tools.farcaster_tools import (
    FollowFarcasterUserTool,
    UnfollowFarcasterUserTool,
    SendFarcasterDMTool
)
from chatbot.tools.base import ActionContext

@pytest.mark.asyncio
async def test_follow_farcaster_user_tool_success():
    tool = FollowFarcasterUserTool()
    mock_obs = AsyncMock()
    mock_obs.follow_user.return_value = {"success": True, "fid": 42}
    context = ActionContext(farcaster_observer=mock_obs)
    res = await tool.execute({"fid": 42}, context)
    assert res["status"] == "success"
    assert res["fid"] == 42
    mock_obs.follow_user.assert_awaited_once_with(42)

@pytest.mark.asyncio
async def test_follow_farcaster_user_tool_missing_param():
    tool = FollowFarcasterUserTool()
    mock_obs = AsyncMock()
    context = ActionContext(farcaster_observer=mock_obs)
    res = await tool.execute({}, context)
    assert res["status"] == "failure"
    assert "Missing required parameter" in res["error"]

@pytest.mark.asyncio
async def test_unfollow_farcaster_user_tool_success():
    tool = UnfollowFarcasterUserTool()
    mock_obs = AsyncMock()
    mock_obs.unfollow_user.return_value = {"success": True, "fid": 99}
    context = ActionContext(farcaster_observer=mock_obs)
    res = await tool.execute({"fid": 99}, context)
    assert res["status"] == "success"
    assert res["fid"] == 99
    mock_obs.unfollow_user.assert_awaited_once_with(99)

@pytest.mark.asyncio
async def test_unfollow_farcaster_user_tool_missing_param():
    tool = UnfollowFarcasterUserTool()
    mock_obs = AsyncMock()
    context = ActionContext(farcaster_observer=mock_obs)
    res = await tool.execute({}, context)
    assert res["status"] == "failure"
    assert "Missing required parameter" in res["error"]

@pytest.mark.asyncio
async def test_send_farcaster_dm_tool_deprecated():
    """Test that DM tool now returns failure since DM functionality is not supported."""
    tool = SendFarcasterDMTool()
    mock_obs = AsyncMock()
    context = ActionContext(farcaster_observer=mock_obs)
    params = {"fid": 123, "content": "Hello DM"}
    res = await tool.execute(params, context)
    assert res["status"] == "failure"
    assert "not supported by the API" in res["error"]
    # Ensure the observer method is not called since functionality is deprecated
    mock_obs.send_dm.assert_not_called()

@pytest.mark.asyncio
async def test_send_farcaster_dm_tool_missing_params_deprecated():
    """Test that DM tool returns failure for missing params (but still due to deprecation)."""
    tool = SendFarcasterDMTool()
    mock_obs = AsyncMock()
    context = ActionContext(farcaster_observer=mock_obs)
    res = await tool.execute({"fid": 123}, context)
    assert res["status"] == "failure"
    assert "not supported by the API" in res["error"]
