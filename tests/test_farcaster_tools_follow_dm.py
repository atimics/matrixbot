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
async def test_send_farcaster_dm_tool_success():
    tool = SendFarcasterDMTool()
    mock_obs = AsyncMock()
    mock_obs.send_dm.return_value = {"success": True, "message_id": "dm789"}
    context = ActionContext(farcaster_observer=mock_obs)
    params = {"fid": 123, "content": "Hello DM"}
    res = await tool.execute(params, context)
    assert res["status"] == "success"
    assert res["message_id"] == "dm789"
    mock_obs.send_dm.assert_awaited_once_with(123, "Hello DM")

@pytest.mark.asyncio
async def test_send_farcaster_dm_tool_missing_params():
    tool = SendFarcasterDMTool()
    mock_obs = AsyncMock()
    context = ActionContext(farcaster_observer=mock_obs)
    res = await tool.execute({"fid": 123}, context)
    assert res["status"] == "failure"
    assert "Missing required parameters" in res["error"]
