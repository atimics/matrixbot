"""Integration-manager lifecycle tests with no external network access."""

from typing import Any, Dict

import pytest

from chatbot.core.integration_manager import IntegrationManager
from chatbot.core.world_state.manager import WorldStateManager
from chatbot.integrations.base import Integration


class DummyIntegration(Integration):
    def __init__(
        self,
        integration_id: str,
        display_name: str,
        config: Dict[str, Any],
    ):
        super().__init__(integration_id, display_name, config)
        self.connected = False

    @property
    def integration_type(self) -> str:
        return "dummy"

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    async def get_status(self) -> Dict[str, Any]:
        return {
            "integration_id": self.integration_id,
            "is_connected": self.connected,
        }

    async def test_connection(self) -> bool:
        return True


@pytest.mark.asyncio
async def test_integration_system_lifecycle() -> None:
    manager = IntegrationManager(
        ":memory:", world_state_manager=WorldStateManager()
    )
    await manager.initialize()
    manager.integration_types["dummy"] = DummyIntegration

    try:
        integration_id = await manager.add_integration(
            integration_type="dummy",
            display_name="Test integration",
            config={},
            credentials={"token": "not-a-real-secret"},
        )

        configured = await manager.list_integrations()
        assert [item["integration_id"] for item in configured] == [integration_id]

        assert await manager.connect_integration(integration_id)
        assert (await manager.get_integration_status(integration_id))[
            "is_connected"
        ]

        assert await manager.remove_integration(integration_id)
        assert await manager.get_integration_status(integration_id) is None
        assert manager.get_observers() == []
    finally:
        await manager.disconnect_all()
        await manager.cleanup()
