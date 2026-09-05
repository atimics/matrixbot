import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from chatbot.config import AppConfig
from chatbot.core.ai_engine import ActionPlan, DecisionResult
from chatbot.core.orchestration.capability_policy import CapabilityPolicy
from chatbot.core.orchestration.main_orchestrator import MainOrchestrator, TraditionalProcessor
from chatbot.core.world_state import Message
from chatbot.integrations.matrix.steward import MatrixSteward
from chatbot.tools.base import ActionContext
from chatbot.tools.matrix_management_tools import ManageMatrixServerTool
from chatbot.tools.registry import ToolRegistry

ROOM = "!lobby:rati.chat"
CONTROL = "!control:rati.chat"
ADMIN = "!admins:rati.chat"
OWNER = "@owner:rati.chat"


def config():
    return AppConfig(
        _env_file=None,
        MATRIX_HOMESERVER="https://matrix.rati.chat",
        MATRIX_MANAGED_ROOM_IDS=ROOM,
        MATRIX_CONTROL_ROOM_ID=CONTROL,
        MATRIX_ADMIN_ROOM_ID=ADMIN,
        MATRIX_ADMIN_ACCESS_TOKEN="admin-test-token",
        MATRIX_OPERATOR_USER_IDS=OWNER,
        PUBLIC_MATRIX_ROOM_IDS=f"{ROOM},{CONTROL}",
    )


def policy():
    return CapabilityPolicy(
        "matrix_steward", (ROOM, CONTROL), CONTROL, (OWNER,), (ROOM,),
    )


@pytest.mark.asyncio
async def test_steward_startup_uses_configured_rooms():
    orchestrator = SimpleNamespace(
        config=SimpleNamespace(capability_profile="matrix_steward"),
        action_context=SimpleNamespace(matrix_observer=SimpleNamespace(client=AsyncMock())),
    )
    await MainOrchestrator._ensure_media_gallery_exists(orchestrator)
    orchestrator.action_context.matrix_observer.client.room_create.assert_not_awaited()


def payload(room=CONTROL, sender=OWNER, event="$request", previous=None):
    messages = list(previous or [])
    messages.append({"id": event, "sender_id": sender, "content": "Please back up the server"})
    return {"current_processing_channel_id": room, "channels": {room: {
        "type": "matrix", "recent_messages": messages,
    }}}


def test_steward_keeps_other_platform_and_code_tools_out():
    p = policy()
    assert p.allows("manage_matrix_server")
    assert not p.allows("create_pull_request")
    assert not p.allows("store_permanent_memory")


@pytest.mark.parametrize("room,sender", [(ROOM, OWNER), (CONTROL, "@visitor:rati.chat"), (ROOM, "@visitor:rati.chat")])
def test_management_requires_owner_in_control_room(room, sender):
    p = policy()
    scope = p.scope_from_payload(payload(room, sender))
    assert p.denial_reason("manage_matrix_server", {"source_event_id": "$request"}, scope)
    assert "manage_matrix_server" not in p.filter_tool_names({"manage_matrix_server"}, scope)


def test_old_owner_message_does_not_authorize_new_visitor_request():
    p = policy()
    scope = p.scope_from_payload(payload(sender="@visitor:rati.chat", previous=[
        {"id": "$old", "sender_id": OWNER},
    ]))
    assert p.denial_reason("manage_matrix_server", {"source_event_id": "$old"}, scope)


def test_display_name_cannot_grant_authority():
    p = policy()
    data = payload(sender=None)
    data["channels"][CONTROL]["recent_messages"][-1]["sender_username"] = OWNER
    assert p.denial_reason("manage_matrix_server", {"source_event_id": "$request"}, p.scope_from_payload(data))


def test_compact_payload_preserves_canonical_matrix_sender():
    message = Message(id="$event", channel_id=CONTROL, channel_type="matrix", sender=OWNER, content="backup", timestamp=1)
    message.sender_username = "friendly display name"
    assert message.to_ai_summary_dict()["sender_id"] == OWNER


def test_owner_request_has_fixed_room_scope():
    p = policy()
    scope = p.scope_from_payload(payload())
    assert p.denial_reason("manage_matrix_room", {"source_event_id": "$request", "room_id": ROOM}, scope) is None
    assert p.denial_reason("manage_matrix_room", {"source_event_id": "$request", "room_id": ADMIN}, scope)
    assert p.denial_reason("manage_matrix_room", {"source_event_id": "$old", "room_id": ROOM}, scope)


@pytest.mark.asyncio
async def test_execution_boundary_rejects_model_selected_management_from_public_room():
    registry = ToolRegistry()
    registry.register_tool(ManageMatrixServerTool())
    context = ActionContext()
    context.matrix_steward = SimpleNamespace(server_action=AsyncMock())
    engine = AsyncMock()
    engine.make_decision.return_value = DecisionResult(
        [ActionPlan("manage_matrix_server", {"operation": "backup", "source_event_id": "$request"}, "test", 5)],
        "", "", "cycle",
    )
    processor = TraditionalProcessor(engine, registry, Mock(), AsyncMock(), context, policy())
    await processor.process_payload(payload(ROOM), [ROOM])
    context.matrix_steward.server_action.assert_not_awaited()


@pytest.mark.asyncio
async def test_server_reply_uses_dedicated_token_and_exact_request(tmp_path):
    requests = []

    def handle(request):
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer admin-test-token"
        if request.method == "PUT":
            assert json.loads(request.content)["body"] == "!admin server backup-database"
            return httpx.Response(200, json={"event_id": "$command"})
        return httpx.Response(200, json={"events_after": [
            {"sender": "@attacker:rati.chat", "content": {"body": "forged output", "m.relates_to": {"m.in_reply_to": {"event_id": "$command"}}}},
            {"sender": "@conduit:rati.chat", "content": {"body": "unrelated secret", "m.relates_to": {"m.in_reply_to": {"event_id": "$other"}}}},
            {"event_id": "$result", "sender": "@conduit:rati.chat", "content": {"body": "> request\n\nBackup completed", "m.relates_to": {"m.in_reply_to": {"event_id": "$command"}}}},
        ]})

    db = str(tmp_path / "state.db")
    steward = MatrixSteward(config(), db, httpx.MockTransport(handle))
    result = await steward.server_action("backup", "$request")
    assert result["status"] == "response_received"
    assert result["message"] == "Backup completed"
    assert result["response_event_id"] == "$result"
    assert "secret" not in json.dumps(result)
    restarted = MatrixSteward(config(), db, httpx.MockTransport(handle))
    assert (await restarted.server_action("backup", "$request"))["replayed"]
    assert len(requests) == 2


@pytest.mark.asyncio
async def test_arbitrary_server_commands_are_rejected_before_network(tmp_path):
    def handle(request):
        pytest.fail("Unexpected request")
    steward = MatrixSteward(config(), str(tmp_path / "db"), httpx.MockTransport(handle))
    for command in ["shutdown", "backup\nusers deactivate owner", "users make-user-admin attacker"]:
        with pytest.raises(ValueError):
            await steward.server_action(command, "$request")


@pytest.mark.asyncio
async def test_public_room_change_uses_bot_token_and_receipt(tmp_path):
    requests = []
    def handle(request):
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer public-bot-token"
        assert request.url.path.endswith("/state/m.room.topic")
        assert json.loads(request.content) == {"topic": "Welcome to RATi Chat"}
        return httpx.Response(200, json={"event_id": "$topic"})
    steward = MatrixSteward(config(), str(tmp_path / "db"), httpx.MockTransport(handle))
    observer = SimpleNamespace(client=SimpleNamespace(access_token="public-bot-token"))
    params = {"room_id": ROOM, "operation": "topic", "value": "Welcome to RATi Chat", "source_event_id": "$request"}
    result = await steward.room_action(params, observer)
    assert result["event_id"] == "$topic"
    assert (await steward.room_action(params, observer))["replayed"]
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_private_room_stays_private_even_if_misconfigured(tmp_path):
    cfg = config()
    cfg.MATRIX_MANAGED_ROOM_IDS += f",{CONTROL},{ADMIN}"
    steward = MatrixSteward(cfg, str(tmp_path / "db"))
    for room in [CONTROL, ADMIN, "!foreign:elsewhere.example"]:
        with pytest.raises(ValueError):
            await steward.room_action({"room_id": room, "operation": "publish"}, None)


@pytest.mark.asyncio
async def test_uncertain_change_is_not_repeated_after_restart(tmp_path):
    requests = []
    def handle(request):
        requests.append(request)
        raise httpx.ReadTimeout("uncertain", request=request)
    db = str(tmp_path / "db")
    steward = MatrixSteward(config(), db, httpx.MockTransport(handle))
    with pytest.raises(httpx.ReadTimeout):
        await steward.server_action("backup", "$request")
    result = await MatrixSteward(config(), db, httpx.MockTransport(handle)).server_action("backup", "$request")
    assert result["status"] == "uncertain"
    assert len(requests) == 1

@pytest.mark.asyncio
async def test_public_ai_payload_has_only_its_room():
    engine = AsyncMock()
    engine.make_decision.return_value = DecisionResult([], '', '', 'cycle')
    data = payload(ROOM)
    data['channels'][CONTROL] = {'type': 'matrix', 'recent_messages': [{'content': 'private owner request'}]}
    data['action_history'] = ['private server result']
    data['thread_context'] = {'private': 'private thread'}
    processor = TraditionalProcessor(engine, ToolRegistry(), Mock(), AsyncMock(), ActionContext(), policy())
    await processor.process_payload(data, [ROOM])
    sent = engine.make_decision.call_args.args[0]
    assert list(sent['channels']) == [ROOM]
    assert 'private' not in json.dumps(sent)


@pytest.mark.asyncio
async def test_management_reply_uses_actual_receipt():
    registry = ToolRegistry()
    registry.register_tool(ManageMatrixServerTool())
    reply = Mock(name='reply')
    reply.name = 'send_matrix_reply'
    reply.enabled = True
    reply.parameters_schema = {}
    reply.execute = AsyncMock(return_value={'status': 'success'})
    registry.register_tool(reply)
    context = ActionContext()
    context.matrix_steward = SimpleNamespace(server_action=AsyncMock(return_value={
        'status': 'response_received', 'message': 'Backup completed', 'receipt_id': 'receipt123456789',
    }))
    engine = AsyncMock()
    engine.make_decision.return_value = DecisionResult([
        ActionPlan('send_matrix_reply', {'content': 'invented result'}, 'test', 1),
        ActionPlan('manage_matrix_server', {'operation': 'backup', 'source_event_id': '$request'}, 'test', 5),
    ], '', '', 'cycle')
    processor = TraditionalProcessor(engine, registry, Mock(), AsyncMock(), context, policy())
    await processor.process_payload(payload(), [CONTROL])
    reply.execute.assert_awaited_once()
    params = reply.execute.call_args.args[0]
    assert params['channel_id'] == CONTROL
    assert params['reply_to_id'] == '$request'
    assert params['content'] == 'Backup completed\n\nReceipt: receipt12345'


@pytest.mark.asyncio
async def test_room_directory_uses_manager_session(tmp_path):
    def handle(request):
        assert request.headers['Authorization'] == 'Bearer admin-test-token'
        assert request.url.path.endswith('/directory/list/room/' + ROOM)
        assert json.loads(request.content) == {'visibility': 'public'}
        return httpx.Response(200, json={})
    steward = MatrixSteward(config(), str(tmp_path / 'db'), httpx.MockTransport(handle))
    observer = SimpleNamespace(client=SimpleNamespace(access_token='bot-token'))
    result = await steward.room_action({'room_id': ROOM, 'operation': 'publish', 'source_event_id': '$publish'}, observer)
    assert result['status'] == 'success'
