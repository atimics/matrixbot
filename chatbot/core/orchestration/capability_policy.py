"""Capability profiles for AI-selected tool execution."""

from dataclasses import dataclass
from typing import Any, Collection, Mapping


PUBLIC_BOT_ALLOWED_TOOLS = frozenset(
    {
        "wait",
        "send_matrix_reply",
        "react_to_matrix_message",
        "send_farcaster_reply",
        "like_farcaster_post",
    }
)

PUBLIC_BOT_BLOCKED_PARAMETERS = {
    "send_matrix_reply": frozenset({"image_url"}),
}


@dataclass(frozen=True)
class ExecutionScope:
    """Destinations and source messages available in one processing cycle."""

    channel_id: str | None
    channel_type: str | None
    message_ids: frozenset[str]


class CapabilityPolicy:
    """Apply a hard capability ceiling to model-selected actions."""

    SUPPORTED_PROFILES = frozenset({"public", "operator"})

    def __init__(
        self,
        profile: str = "public",
        approved_matrix_room_ids: Collection[str] = (),
    ) -> None:
        normalized_profile = profile.strip().lower()
        if normalized_profile not in self.SUPPORTED_PROFILES:
            supported = ", ".join(sorted(self.SUPPORTED_PROFILES))
            raise ValueError(
                f"Unknown bot capability profile '{profile}'. Supported profiles: {supported}"
            )
        self.profile = normalized_profile
        self.approved_matrix_room_ids = frozenset(
            room_id.strip()
            for room_id in approved_matrix_room_ids
            if room_id and room_id.strip()
        )

    def allows(self, tool_name: str) -> bool:
        """Return whether this profile permits a model-selected tool."""
        if self.profile == "operator":
            return True
        return tool_name in PUBLIC_BOT_ALLOWED_TOOLS

    def filter_tool_names(self, tool_names: Collection[str]) -> set[str]:
        """Return the names that may be shown to and used by the model."""
        return {tool_name for tool_name in tool_names if self.allows(tool_name)}

    def scope_from_payload(self, payload: Mapping[str, Any]) -> ExecutionScope:
        """Build the public action scope from the current source channel."""
        channel_id = payload.get("current_processing_channel_id")
        channels = payload.get("channels")
        if not isinstance(channel_id, str) or not isinstance(channels, Mapping):
            return ExecutionScope(None, None, frozenset())

        channel = channels.get(channel_id)
        if not isinstance(channel, Mapping):
            return ExecutionScope(None, None, frozenset())

        channel_type = channel.get("type")
        if not isinstance(channel_type, str):
            channel_type = None

        recent_messages = channel.get("recent_messages")
        if not isinstance(recent_messages, list):
            recent_messages = []
        message_ids = frozenset(
            message["id"]
            for message in recent_messages
            if isinstance(message, Mapping)
            and isinstance(message.get("id"), str)
            and message["id"]
        )
        return ExecutionScope(channel_id, channel_type, message_ids)

    def denial_reason(
        self,
        tool_name: str,
        parameters: dict,
        execution_scope: ExecutionScope | None = None,
    ) -> str | None:
        """Return a reason when an action exceeds the active profile."""
        if not self.allows(tool_name):
            return (
                f"Tool '{tool_name}' is blocked by the "
                f"'{self.profile}' capability profile"
            )
        if self.profile == "operator":
            return None

        blocked_parameters = PUBLIC_BOT_BLOCKED_PARAMETERS.get(tool_name, frozenset())
        supplied_blocked = sorted(
            name for name in blocked_parameters if parameters.get(name) is not None
        )
        if supplied_blocked:
            names = ", ".join(supplied_blocked)
            return (
                f"Tool '{tool_name}' parameters are blocked by the "
                f"'{self.profile}' capability profile: {names}"
            )

        if tool_name == "wait":
            return None

        if tool_name in {"send_matrix_reply", "react_to_matrix_message"}:
            return self._matrix_denial_reason(
                tool_name, parameters, execution_scope
            )

        if tool_name in {"send_farcaster_reply", "like_farcaster_post"}:
            return self._farcaster_denial_reason(
                tool_name, parameters, execution_scope
            )
        return None

    def _matrix_denial_reason(
        self,
        tool_name: str,
        parameters: dict,
        execution_scope: ExecutionScope | None,
    ) -> str | None:
        room_parameter = (
            "channel_id" if tool_name == "send_matrix_reply" else "room_id"
        )
        event_parameter = (
            "reply_to_id" if tool_name == "send_matrix_reply" else "event_id"
        )
        room_id = parameters.get(room_parameter)
        event_id = parameters.get(event_parameter)

        if not room_id or not event_id:
            return (
                f"Tool '{tool_name}' requires an explicit Matrix room and "
                "source event in the public capability profile"
            )
        if execution_scope is None or execution_scope.channel_type != "matrix":
            return f"Tool '{tool_name}' requires a current Matrix source context"
        if not self.approved_matrix_room_ids:
            return "The public capability profile has no approved Matrix rooms"
        if room_id not in self.approved_matrix_room_ids:
            return f"Matrix room '{room_id}' is outside the approved public rooms"
        if room_id != execution_scope.channel_id:
            return f"Matrix room '{room_id}' is outside the current source context"
        if event_id not in execution_scope.message_ids:
            return f"Matrix event '{event_id}' is outside the current source context"
        return None

    def _farcaster_denial_reason(
        self,
        tool_name: str,
        parameters: dict,
        execution_scope: ExecutionScope | None,
    ) -> str | None:
        target_parameter = (
            "reply_to_hash" if tool_name == "send_farcaster_reply" else "cast_hash"
        )
        target_hash = parameters.get(target_parameter)

        if not target_hash:
            return f"Tool '{tool_name}' requires an explicit Farcaster target"
        if execution_scope is None or execution_scope.channel_type != "farcaster":
            return f"Tool '{tool_name}' requires a current Farcaster source context"
        if target_hash not in execution_scope.message_ids:
            return (
                f"Farcaster target '{target_hash}' is outside the current "
                "source context"
            )
        return None
