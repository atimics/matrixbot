import pytest
import time
from unittest.mock import AsyncMock

import nio
from chatbot.tools.matrix_tools import SendMatrixReplyTool, SendMatrixMessageTool
from chatbot.tools.base import ActionContext
from chatbot.integrations.matrix.observer import MatrixObserver
from chatbot.core.world_state import WorldStateManager, WorldState, Message

# ---- Tests for Matrix Tools ----
@pytest.mark.asyncio
async def test_send_matrix_reply_tool_success():
    # Setup dummy observer
    dummy_obs = type("DummyObs", (), {})()
    dummy_obs.send_reply = AsyncMock(return_value={"success": True, "event_id": "evt123"})

    context = ActionContext(matrix_observer=dummy_obs)
    tool = SendMatrixReplyTool()

    params = {"channel_id": "!room:server", "content": "Hello!", "reply_to_id": "origevt"}
    result = await tool.execute(params, context)

    assert result["status"] == "success"
    assert result["event_id"] == "evt123"
    dummy_obs.send_reply.assert_awaited_once_with("!room:server", "Hello!", "origevt")

@pytest.mark.asyncio
async def test_send_matrix_reply_tool_missing_params():
    dummy_obs = type("DummyObs", (), {})()
    dummy_obs.send_reply = AsyncMock()
    context = ActionContext(matrix_observer=dummy_obs)
    tool = SendMatrixReplyTool()

    # Missing all params
    res = await tool.execute({}, context)
    assert res["status"] == "failure"
    assert "Missing required parameters" in res["error"]

@pytest.mark.asyncio
async def test_send_matrix_message_tool_success():
    # Setup dummy observer
    dummy_obs = type("DummyObs", (), {})()
    dummy_obs.send_message = AsyncMock(return_value={"success": True, "event_id": "msg456"})

    context = ActionContext(matrix_observer=dummy_obs)
    tool = SendMatrixMessageTool()
    params = {"channel_id": "!room:server", "content": "Announcement"}
    result = await tool.execute(params, context)

    assert result["status"] == "success"
    assert result["event_id"] == "msg456"
    dummy_obs.send_message.assert_awaited_once_with("!room:server", "Announcement")

@pytest.mark.asyncio
async def test_send_matrix_message_tool_missing_params():
    dummy_obs = type("DummyObs", (), {})()
    dummy_obs.send_message = AsyncMock()
    context = ActionContext(matrix_observer=dummy_obs)
    tool = SendMatrixMessageTool()

    res = await tool.execute({}, context)
    assert res["status"] == "failure"
    assert "Missing required parameters" in res["error"]

# ---- Tests for MatrixObserver basic methods ----
def test_matrix_observer_user_and_room_details_empty(monkeypatch):
    wsm = WorldStateManager()
    obs = MatrixObserver(world_state_manager=wsm)
    # No client initialized -> empty dicts
    assert obs.get_room_details() == {}
    assert obs.get_user_details() == {}

# Simulate a dummy client with rooms and users for details
class DummyUser:
    def __init__(self, user_id, display_name=None, avatar_url=None):
        self.user_id = user_id
        self.display_name = display_name
        self.avatar_url = avatar_url

class DummyRoom:
    def __init__(self, room_id, name, users, power_levels=None):
        self.room_id = room_id
        self.display_name = name
        self.name = name
        self.users = {u.user_id: u for u in users}
        # Power levels stub
        pl_dict = power_levels or {}
        self.power_levels = type("PL", (), {"users": pl_dict})
        # Timeline stub for last_message_time
        self.timeline = type("Timeline", (), {"events": []})()

@pytest.mark.asyncio
async def test_matrix_observer_room_and_user_details(monkeypatch):
    wsm = WorldStateManager()
    obs = MatrixObserver(world_state_manager=wsm)
    # Create dummy client with 2 rooms and users
    user_a = DummyUser("@alice:server", display_name="Alice", avatar_url="urlA")
    user_b = DummyUser("@bob:server", display_name="Bob", avatar_url="urlB")
    room1 = DummyRoom("!r1:server", "Room1", [user_a, user_b], power_levels={"@alice:server": 50})
    room2 = DummyRoom("!r2:server", "Room2", [user_b], power_levels={})

    # Assign client with rooms
    class DummyClient:
        def __init__(self, rooms): self.rooms = {r.room_id: r for r in rooms}
    obs.client = DummyClient([room1, room2])

    # Test get_room_details
    rd = obs.get_room_details()
    # Ensure room details extracted correctly (keys present)
    assert set(rd.keys()) == {"!r1:server", "!r2:server"}
    assert rd["!r1:server"]["name"] == "Room1"

    # Test get_user_details
    ud = obs.get_user_details()
    assert "@alice:server" in ud and "@bob:server" in ud
    assert ud["@alice:server"]["display_name"] == "Alice"
    assert ":server" in ud["@bob:server"]["user_id"]
