"""Capability profiles for AI-selected tool execution."""

from typing import Collection


PUBLIC_BOT_ALLOWED_TOOLS = frozenset(
    {
        "wait",
        "send_matrix_message",
        "send_matrix_reply",
        "react_to_matrix_message",
        "send_farcaster_reply",
        "like_farcaster_post",
    }
)

PUBLIC_BOT_BLOCKED_PARAMETERS = {
    "send_matrix_message": frozenset({"image_url"}),
    "send_matrix_reply": frozenset({"image_url"}),
}


class CapabilityPolicy:
    """Apply a hard capability ceiling to model-selected actions."""

    SUPPORTED_PROFILES = frozenset({"public", "operator"})

    def __init__(self, profile: str = "public") -> None:
        normalized_profile = profile.strip().lower()
        if normalized_profile not in self.SUPPORTED_PROFILES:
            supported = ", ".join(sorted(self.SUPPORTED_PROFILES))
            raise ValueError(
                f"Unknown bot capability profile '{profile}'. Supported profiles: {supported}"
            )
        self.profile = normalized_profile

    def allows(self, tool_name: str) -> bool:
        """Return whether this profile permits a model-selected tool."""
        if self.profile == "operator":
            return True
        return tool_name in PUBLIC_BOT_ALLOWED_TOOLS

    def filter_tool_names(self, tool_names: Collection[str]) -> set[str]:
        """Return the names that may be shown to and used by the model."""
        return {tool_name for tool_name in tool_names if self.allows(tool_name)}

    def denial_reason(self, tool_name: str, parameters: dict) -> str | None:
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
        return None
