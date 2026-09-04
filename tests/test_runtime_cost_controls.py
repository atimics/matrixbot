"""Tests for state-change and external API cost controls."""

from unittest.mock import MagicMock

from chatbot.core.orchestration.processing_hub import ProcessingHub
from chatbot.integrations.farcaster.neynar_api_client import NeynarAPIClient


def make_processing_hub() -> ProcessingHub:
    """Build the processing hub with small local test doubles."""
    return ProcessingHub(
        world_state_manager=MagicMock(),
        payload_builder=MagicMock(),
        rate_limiter=MagicMock(),
    )


def test_state_hash_ignores_derived_clock_and_observation_counters() -> None:
    """An idle state keeps one fingerprint across observation cycles."""
    hub = make_processing_hub()
    first = {
        "channels": {},
        "system_status": {
            "matrix_connected": True,
            "last_observation_cycle": 100.0,
            "total_cycles": 1,
        },
        "recent_activity": {"current_time": 100.0},
    }
    second = {
        "channels": {},
        "system_status": {
            "matrix_connected": True,
            "last_observation_cycle": 102.0,
            "total_cycles": 2,
        },
        "recent_activity": {"current_time": 102.0},
    }

    assert hub._hash_state(first) == hub._hash_state(second)


def test_state_hash_changes_for_a_new_message() -> None:
    """A new chat message creates a fresh decision fingerprint."""
    hub = make_processing_hub()
    first = {"channels": {"room": {"recent_messages": []}}}
    second = {
        "channels": {
            "room": {
                "recent_messages": [
                    {"id": "event-1", "sender": "@alice:rati.chat"}
                ]
            }
        }
    }

    assert hub._hash_state(first) != hub._hash_state(second)


def test_neynar_uses_current_api_key_header() -> None:
    """Neynar requests use its current authentication header."""
    client = NeynarAPIClient(api_key="test-key")

    assert client._get_headers()["x-api-key"] == "test-key"
    assert "api_key" not in client._get_headers()
