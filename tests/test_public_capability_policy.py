from unittest.mock import AsyncMock, Mock

import pytest

from chatbot.core.ai_engine import ActionPlan, DecisionResult
from chatbot.core.orchestration.capability_policy import CapabilityPolicy
from chatbot.core.orchestration.main_orchestrator import TraditionalProcessor
from chatbot.tools.base import ActionContext, ToolInterface
from chatbot.tools.registry import ToolRegistry


class RecordingTool(ToolInterface):
    def __init__(self, name: str) -> None:
        self._name = name
        self.calls = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return f"Test tool {self._name}"

    @property
    def parameters_schema(self):
        return {}

    async def execute(self, params, context):
        self.calls.append(params)
        return {"status": "success", "message": "done"}


def make_processor(profile: str, registry: ToolRegistry):
    ai_engine = AsyncMock()
    context_manager = AsyncMock()
    processor = TraditionalProcessor(
        ai_engine=ai_engine,
        tool_registry=registry,
        rate_limiter=Mock(),
        context_manager=context_manager,
        action_context=ActionContext(),
        capability_policy=CapabilityPolicy(profile),
    )
    return processor, ai_engine, context_manager


def action(tool_name: str) -> ActionPlan:
    return ActionPlan(
        action_type=tool_name,
        parameters={"value": "from public chat"},
        reasoning="test",
        priority=5,
    )


@pytest.mark.asyncio
async def test_public_profile_blocks_privileged_tool_at_execution_boundary():
    registry = ToolRegistry()
    privileged_tool = RecordingTool("create_github_issue")
    registry.register_tool(privileged_tool)
    processor, _, context_manager = make_processor("public", registry)

    result = await processor._execute_action_and_return_result(
        action("create_github_issue")
    )

    assert result["status"] == "blocked"
    assert privileged_tool.calls == []
    audit_result = context_manager.add_tool_result.await_args.kwargs["result"]
    assert audit_result["status"] == "blocked"


@pytest.mark.asyncio
async def test_operator_profile_can_use_registered_tool():
    registry = ToolRegistry()
    operator_tool = RecordingTool("create_github_issue")
    registry.register_tool(operator_tool)
    processor, _, _ = make_processor("operator", registry)

    result = await processor._execute_action_and_return_result(
        action("create_github_issue")
    )

    assert result["status"] == "success"
    assert operator_tool.calls == [{"value": "from public chat"}]


@pytest.mark.asyncio
async def test_disabled_public_tool_stays_unavailable_at_execution_boundary():
    registry = ToolRegistry()
    reply_tool = RecordingTool("send_matrix_reply")
    registry.register_tool(reply_tool)
    registry.set_tool_enabled("send_matrix_reply", False)
    processor, _, _ = make_processor("public", registry)

    result = await processor._execute_action_and_return_result(
        action("send_matrix_reply")
    )

    assert result["status"] == "error"
    assert reply_tool.calls == []


@pytest.mark.asyncio
async def test_public_profile_blocks_external_matrix_media_parameter():
    registry = ToolRegistry()
    reply_tool = RecordingTool("send_matrix_reply")
    registry.register_tool(reply_tool)
    processor, _, context_manager = make_processor("public", registry)
    public_action = action("send_matrix_reply")
    public_action.parameters["image_url"] = "http://169.254.169.254/metadata"

    result = await processor._execute_action_and_return_result(public_action)

    assert result["status"] == "blocked"
    assert reply_tool.calls == []
    audit_result = context_manager.add_tool_result.await_args.kwargs["result"]
    assert "image_url" in audit_result["message"]


@pytest.mark.asyncio
async def test_public_profile_only_shows_allowed_tools_to_model():
    registry = ToolRegistry()
    registry.register_tool(RecordingTool("send_matrix_reply"))
    registry.register_tool(RecordingTool("create_github_issue"))
    processor, ai_engine, _ = make_processor("public", registry)
    ai_engine.make_decision.return_value = DecisionResult(
        selected_actions=[], reasoning="", observations="", cycle_id="cycle-1"
    )
    payload = {}

    await processor.process_payload(payload, [])

    assert "send_matrix_reply" in payload["available_tools"]
    assert "create_github_issue" not in payload["available_tools"]


def test_unknown_profile_fails_closed():
    with pytest.raises(ValueError, match="Unknown bot capability profile"):
        CapabilityPolicy("custom")
