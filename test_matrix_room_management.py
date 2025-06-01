#!/usr/bin/env python3
"""
Comprehensive Test Suite for Matrix Room Management - Phase 1.1

This test suite validates the advanced Matrix room management functionality including:
- Channel status tracking (active, left_by_bot, kicked, banned, invited)
- Pending Matrix invite management
- Matrix Observer room operations (join, leave, accept, react)
- Matrix Tools functionality and integration
- WorldState management for Matrix-related operations

Test Coverage:
1. WorldStateManager Tests - invite and status management
2. MatrixObserver Tests - room operations and event handling
3. Matrix Tools Tests - tool execution and parameter validation
4. Integration Tests - end-to-end functionality verification
"""

import asyncio
import time
import unittest
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Import the modules under test
from chatbot.core.world_state import Channel, WorldState, WorldStateManager
from chatbot.integrations.matrix.observer import MatrixObserver
from chatbot.tools.matrix_tools import (
    AcceptMatrixInviteTool,
    GetMatrixInvitesTool,
    JoinMatrixRoomTool,
    LeaveMatrixRoomTool,
    ReactToMatrixMessageTool,
)
from chatbot.tools.base import ActionContext


class TestWorldStateManagerMatrixFeatures(unittest.TestCase):
    """Test WorldStateManager Matrix-related functionality"""

    def setUp(self):
        """Set up test fixtures"""
        self.world_state_manager = WorldStateManager()
        self.test_room_id = "!testroom:matrix.org"
        self.test_inviter = "@inviter:matrix.org"
        self.test_room_name = "Test Room"

    def test_add_pending_matrix_invite(self):
        """Test adding pending Matrix invites"""
        invite_info = {
            "room_id": self.test_room_id,
            "inviter": self.test_inviter,
            "room_name": self.test_room_name,
        }

        # Add invite
        self.world_state_manager.add_pending_matrix_invite(invite_info)

        # Verify invite was added
        pending_invites = self.world_state_manager.get_pending_matrix_invites()
        self.assertEqual(len(pending_invites), 1)
        self.assertEqual(pending_invites[0]["room_id"], self.test_room_id)
        self.assertEqual(pending_invites[0]["inviter"], self.test_inviter)
        self.assertEqual(pending_invites[0]["room_name"], self.test_room_name)
        self.assertIn("timestamp", pending_invites[0])

    def test_add_duplicate_matrix_invite(self):
        """Test handling duplicate Matrix invites"""
        invite_info = {
            "room_id": self.test_room_id,
            "inviter": self.test_inviter,
            "room_name": self.test_room_name,
        }

        # Add invite twice
        self.world_state_manager.add_pending_matrix_invite(invite_info)
        updated_invite = invite_info.copy()
        updated_invite["room_name"] = "Updated Room Name"
        self.world_state_manager.add_pending_matrix_invite(updated_invite)

        # Should only have one invite, with updated information
        pending_invites = self.world_state_manager.get_pending_matrix_invites()
        self.assertEqual(len(pending_invites), 1)
        self.assertEqual(pending_invites[0]["room_name"], "Updated Room Name")

    def test_remove_pending_matrix_invite(self):
        """Test removing pending Matrix invites"""
        invite_info = {
            "room_id": self.test_room_id,
            "inviter": self.test_inviter,
            "room_name": self.test_room_name,
        }

        # Add and then remove invite
        self.world_state_manager.add_pending_matrix_invite(invite_info)
        self.assertEqual(len(self.world_state_manager.get_pending_matrix_invites()), 1)

        result = self.world_state_manager.remove_pending_matrix_invite(self.test_room_id)
        self.assertTrue(result)
        self.assertEqual(len(self.world_state_manager.get_pending_matrix_invites()), 0)

        # Try to remove non-existent invite
        result = self.world_state_manager.remove_pending_matrix_invite("!nonexistent:matrix.org")
        self.assertFalse(result)

    def test_update_channel_status(self):
        """Test updating channel status"""
        # First add a channel
        self.world_state_manager.add_channel(self.test_room_id, "matrix", self.test_room_name)

        # Verify initial status
        channel = self.world_state_manager.get_channel(self.test_room_id)
        self.assertIsNotNone(channel)
        self.assertEqual(channel.status, "active")

        # Update status
        self.world_state_manager.update_channel_status(self.test_room_id, "left_by_bot")
        channel = self.world_state_manager.get_channel(self.test_room_id)
        self.assertEqual(channel.status, "left_by_bot")
        self.assertGreater(channel.last_status_update, 0)

    def test_update_unknown_channel_status(self):
        """Test updating status for unknown channel with room name"""
        # Update status for unknown channel with room name
        self.world_state_manager.update_channel_status(
            "!unknown:matrix.org", "kicked", room_name="Unknown Room"
        )

        # Verify channel was created with the status
        channel = self.world_state_manager.get_channel("!unknown:matrix.org")
        self.assertIsNotNone(channel)
        self.assertEqual(channel.status, "kicked")
        self.assertEqual(channel.name, "Unknown Room")

    def test_add_channel_with_status(self):
        """Test adding channel with custom status"""
        self.world_state_manager.add_channel(self.test_room_id, "matrix", self.test_room_name, status="invited")

        channel = self.world_state_manager.get_channel(self.test_room_id)
        self.assertIsNotNone(channel)
        self.assertEqual(channel.status, "invited")
        self.assertGreater(channel.last_status_update, 0)

    def test_get_ai_optimized_payload_includes_invites(self):
        """Test that AI payload includes pending Matrix invites"""
        # Add some pending invites
        invite1 = {"room_id": "!room1:matrix.org", "inviter": "@user1:matrix.org", "room_name": "Room 1"}
        invite2 = {"room_id": "!room2:matrix.org", "inviter": "@user2:matrix.org", "room_name": "Room 2"}

        self.world_state_manager.add_pending_matrix_invite(invite1)
        self.world_state_manager.add_pending_matrix_invite(invite2)

        # Get AI payload
        payload = self.world_state_manager.get_ai_optimized_payload()

        # Verify invites are included
        self.assertIn("pending_matrix_invites", payload)
        self.assertEqual(len(payload["pending_matrix_invites"]), 2)
        self.assertIn("payload_stats", payload)
        self.assertEqual(payload["payload_stats"]["pending_invites_count"], 2)


class TestMatrixObserverRoomManagement(unittest.TestCase):
    """Test MatrixObserver room management functionality"""

    def setUp(self):
        """Set up test fixtures"""
        self.world_state_manager = WorldStateManager()
        self.matrix_observer = MatrixObserver(self.world_state_manager)
        
        # Mock the nio client
        self.mock_client = AsyncMock()
        self.matrix_observer.client = self.mock_client
        self.matrix_observer.user_id = "@testbot:matrix.org"

    @pytest.mark.asyncio
    async def test_join_room_success(self):
        """Test successful room joining"""
        room_id = "!testroom:matrix.org"
        room_alias = "#testroom:matrix.org"

        # Mock successful join response
        mock_response = MagicMock()
        mock_response.room_id = room_id
        self.mock_client.join.return_value = mock_response

        # Mock room in client.rooms
        mock_room = MagicMock()
        mock_room.display_name = "Test Room"
        mock_room.name = "Test Room"
        mock_room.canonical_alias = room_alias
        self.mock_client.rooms = {room_id: mock_room}

        # Execute join
        result = await self.matrix_observer.join_room(room_alias)

        # Verify result
        self.assertTrue(result["success"])
        self.assertEqual(result["room_id"], room_id)
        self.assertIn(room_id, self.matrix_observer.channels_to_monitor)

        # Verify client was called
        self.mock_client.join.assert_called_once_with(room_alias)

    @pytest.mark.asyncio
    async def test_join_room_failure(self):
        """Test failed room joining"""
        room_alias = "#testroom:matrix.org"

        # Mock failed join response
        mock_response = MagicMock()
        del mock_response.room_id  # Simulate failure by not having room_id
        self.mock_client.join.return_value = mock_response

        # Execute join
        result = await self.matrix_observer.join_room(room_alias)

        # Verify failure result
        self.assertFalse(result["success"])
        self.assertIn("error", result)

    @pytest.mark.asyncio
    async def test_leave_room_success(self):
        """Test successful room leaving"""
        room_id = "!testroom:matrix.org"
        reason = "Test leaving"

        # Add room to monitoring first
        self.matrix_observer.channels_to_monitor.append(room_id)
        self.world_state_manager.add_channel(room_id, "matrix", "Test Room")

        # Mock successful leave response
        self.mock_client.room_leave.return_value = MagicMock()

        # Execute leave
        result = await self.matrix_observer.leave_room(room_id, reason)

        # Verify result
        self.assertTrue(result["success"])
        self.assertEqual(result["room_id"], room_id)
        self.assertEqual(result["reason"], reason)
        self.assertNotIn(room_id, self.matrix_observer.channels_to_monitor)

        # Verify client was called
        self.mock_client.room_leave.assert_called_once_with(room_id, reason)

        # Verify channel status was updated
        channel = self.world_state_manager.get_channel(room_id)
        self.assertEqual(channel.status, "left_by_bot")

    @pytest.mark.asyncio
    async def test_accept_invite_success(self):
        """Test successful invite acceptance"""
        room_id = "!testroom:matrix.org"

        # Mock pending invite
        self.mock_client.invited_rooms = {room_id: MagicMock()}

        # Mock successful join response
        mock_response = MagicMock()
        mock_response.room_id = room_id
        self.mock_client.join.return_value = mock_response

        # Add pending invite to world state
        invite_info = {"room_id": room_id, "inviter": "@inviter:matrix.org", "room_name": "Test Room"}
        self.world_state_manager.add_pending_matrix_invite(invite_info)

        # Execute accept
        result = await self.matrix_observer.accept_invite(room_id)

        # Verify result
        self.assertTrue(result["success"])
        self.assertEqual(result["room_id"], room_id)
        self.assertIn(room_id, self.matrix_observer.channels_to_monitor)

        # Verify invite was removed from pending
        pending_invites = self.world_state_manager.get_pending_matrix_invites()
        self.assertEqual(len(pending_invites), 0)

    @pytest.mark.asyncio
    async def test_accept_invite_no_pending(self):
        """Test accepting invite when no pending invite exists"""
        room_id = "!testroom:matrix.org"

        # No pending invite
        self.mock_client.invited_rooms = {}

        # Execute accept
        result = await self.matrix_observer.accept_invite(room_id)

        # Verify failure result
        self.assertFalse(result["success"])
        self.assertIn("No pending invitation", result["error"])

    @pytest.mark.asyncio
    async def test_react_to_message_success(self):
        """Test successful message reaction"""
        room_id = "!testroom:matrix.org"
        event_id = "$event:matrix.org"
        emoji = "👍"

        # Mock successful reaction response
        from nio import RoomSendResponse
        mock_response = RoomSendResponse(event_id="$reaction:matrix.org")
        self.mock_client.room_send.return_value = mock_response

        # Execute reaction
        result = await self.matrix_observer.react_to_message(room_id, event_id, emoji)

        # Verify result
        self.assertTrue(result["success"])
        self.assertEqual(result["room_id"], room_id)
        self.assertEqual(result["reacted_to"], event_id)
        self.assertEqual(result["emoji"], emoji)

        # Verify client was called with correct parameters
        self.mock_client.room_send.assert_called_once()
        call_args = self.mock_client.room_send.call_args
        self.assertEqual(call_args[1]["room_id"], room_id)
        self.assertEqual(call_args[1]["message_type"], "m.reaction")

        # Verify reaction content structure
        content = call_args[1]["content"]
        self.assertEqual(content["m.relates_to"]["event_id"], event_id)
        self.assertEqual(content["m.relates_to"]["key"], emoji)
        self.assertEqual(content["m.relates_to"]["rel_type"], "m.annotation")

    @pytest.mark.asyncio
    async def test_react_to_message_failure(self):
        """Test failed message reaction"""
        room_id = "!testroom:matrix.org"
        event_id = "$event:matrix.org"
        emoji = "👍"

        # Mock failed reaction response
        from nio import RoomSendError
        mock_response = RoomSendError("Failed to send reaction")
        self.mock_client.room_send.return_value = mock_response

        # Execute reaction
        result = await self.matrix_observer.react_to_message(room_id, event_id, emoji)

        # Verify failure result
        self.assertFalse(result["success"])
        self.assertIn("error", result)


class TestMatrixTools(unittest.TestCase):
    """Test Matrix tools functionality"""

    def setUp(self):
        """Set up test fixtures"""
        self.mock_matrix_observer = AsyncMock()
        self.mock_world_state_manager = MagicMock()
        
        # Create action context
        self.action_context = MagicMock()
        self.action_context.matrix_observer = self.mock_matrix_observer
        self.action_context.world_state_manager = self.mock_world_state_manager

    @pytest.mark.asyncio
    async def test_join_matrix_room_tool_success(self):
        """Test JoinMatrixRoomTool success case"""
        tool = JoinMatrixRoomTool()
        room_identifier = "#testroom:matrix.org"
        room_id = "!testroom:matrix.org"

        # Mock successful observer response
        self.mock_matrix_observer.join_room.return_value = {
            "success": True,
            "room_id": room_id,
            "room_identifier": room_identifier,
        }

        # Execute tool
        params = {"room_identifier": room_identifier}
        result = await tool.execute(params, self.action_context)

        # Verify result
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["room_id"], room_id)
        self.mock_matrix_observer.join_room.assert_called_once_with(room_identifier)

    @pytest.mark.asyncio
    async def test_join_matrix_room_tool_missing_params(self):
        """Test JoinMatrixRoomTool with missing parameters"""
        tool = JoinMatrixRoomTool()

        # Execute tool without parameters
        params = {}
        result = await tool.execute(params, self.action_context)

        # Verify failure result
        self.assertEqual(result["status"], "failure")
        self.assertIn("Missing required parameter", result["error"])

    @pytest.mark.asyncio
    async def test_leave_matrix_room_tool_success(self):
        """Test LeaveMatrixRoomTool success case"""
        tool = LeaveMatrixRoomTool()
        room_id = "!testroom:matrix.org"
        reason = "Test reason"

        # Mock successful observer response
        self.mock_matrix_observer.leave_room.return_value = {
            "success": True,
            "room_id": room_id,
            "reason": reason,
        }

        # Execute tool
        params = {"room_id": room_id, "reason": reason}
        result = await tool.execute(params, self.action_context)

        # Verify result
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["room_id"], room_id)
        self.mock_matrix_observer.leave_room.assert_called_once_with(room_id, reason)

    @pytest.mark.asyncio
    async def test_accept_matrix_invite_tool_success(self):
        """Test AcceptMatrixInviteTool success case"""
        tool = AcceptMatrixInviteTool()
        room_id = "!testroom:matrix.org"

        # Mock successful observer response
        self.mock_matrix_observer.accept_invite.return_value = {
            "success": True,
            "room_id": room_id,
        }

        # Execute tool
        params = {"room_id": room_id}
        result = await tool.execute(params, self.action_context)

        # Verify result
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["room_id"], room_id)
        self.mock_matrix_observer.accept_invite.assert_called_once_with(room_id)

    @pytest.mark.asyncio
    async def test_get_matrix_invites_tool(self):
        """Test GetMatrixInvitesTool"""
        tool = GetMatrixInvitesTool()

        # Mock pending invites
        mock_invites = [
            {"room_id": "!room1:matrix.org", "inviter": "@user1:matrix.org", "room_name": "Room 1"},
            {"room_id": "!room2:matrix.org", "inviter": "@user2:matrix.org", "room_name": "Room 2"},
        ]
        self.mock_matrix_observer.get_pending_invites_from_world_state.return_value = {
            "success": True,
            "invites": mock_invites,
            "count": 2,
        }

        # Execute tool
        params = {}
        result = await tool.execute(params, self.action_context)

        # Verify result
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["count"], 2)
        self.assertEqual(len(result["invites"]), 2)

    @pytest.mark.asyncio
    async def test_react_to_matrix_message_tool_success(self):
        """Test ReactToMatrixMessageTool success case"""
        tool = ReactToMatrixMessageTool()
        room_id = "!testroom:matrix.org"
        event_id = "$event:matrix.org"
        emoji = "👍"

        # Mock successful observer response
        self.mock_matrix_observer.react_to_message.return_value = {
            "success": True,
            "event_id": "$reaction:matrix.org",
            "room_id": room_id,
            "reacted_to": event_id,
            "emoji": emoji,
        }

        # Execute tool
        params = {"room_id": room_id, "event_id": event_id, "emoji": emoji}
        result = await tool.execute(params, self.action_context)

        # Verify result
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["room_id"], room_id)
        self.assertEqual(result["event_id"], event_id)
        self.assertEqual(result["emoji"], emoji)
        self.mock_matrix_observer.react_to_message.assert_called_once_with(room_id, event_id, emoji)

        # Verify action was recorded in world state
        self.mock_world_state_manager.add_action_result.assert_called_once()

    @pytest.mark.asyncio
    async def test_react_to_matrix_message_tool_missing_params(self):
        """Test ReactToMatrixMessageTool with missing parameters"""
        tool = ReactToMatrixMessageTool()

        # Execute tool with missing parameters
        params = {"room_id": "!testroom:matrix.org"}  # Missing event_id and emoji
        result = await tool.execute(params, self.action_context)

        # Verify failure result
        self.assertEqual(result["status"], "failure")
        self.assertIn("Missing required parameters", result["error"])

    @pytest.mark.asyncio
    async def test_matrix_tool_no_observer(self):
        """Test Matrix tool behavior when observer is not configured"""
        tool = JoinMatrixRoomTool()

        # Create context without matrix observer
        context_no_observer = MagicMock()
        context_no_observer.matrix_observer = None

        # Execute tool
        params = {"room_identifier": "#testroom:matrix.org"}
        result = await tool.execute(params, context_no_observer)

        # Verify failure result
        self.assertEqual(result["status"], "failure")
        self.assertIn("Matrix integration", result["error"])


class TestMatrixIntegration(unittest.TestCase):
    """Integration tests for Matrix room management"""

    def setUp(self):
        """Set up integration test fixtures"""
        self.world_state_manager = WorldStateManager()

    def test_end_to_end_invite_workflow(self):
        """Test complete invite workflow from reception to acceptance"""
        room_id = "!testroom:matrix.org"
        inviter = "@inviter:matrix.org"
        room_name = "Test Room"

        # Step 1: Receive invite (simulates MatrixObserver processing an invite event)
        invite_info = {
            "room_id": room_id,
            "inviter": inviter,
            "room_name": room_name,
            "timestamp": time.time(),
        }
        self.world_state_manager.add_pending_matrix_invite(invite_info)

        # Verify invite is pending
        pending_invites = self.world_state_manager.get_pending_matrix_invites()
        self.assertEqual(len(pending_invites), 1)

        # Step 2: Accept invite (simulates successful room join)
        self.world_state_manager.remove_pending_matrix_invite(room_id)
        self.world_state_manager.add_channel(room_id, "matrix", room_name, status="active")

        # Verify invite is no longer pending and room is active
        pending_invites = self.world_state_manager.get_pending_matrix_invites()
        self.assertEqual(len(pending_invites), 0)

        channel = self.world_state_manager.get_channel(room_id)
        self.assertIsNotNone(channel)
        self.assertEqual(channel.status, "active")
        self.assertEqual(channel.name, room_name)

    def test_end_to_end_leave_workflow(self):
        """Test complete leave workflow"""
        room_id = "!testroom:matrix.org"
        room_name = "Test Room"

        # Step 1: Add active channel
        self.world_state_manager.add_channel(room_id, "matrix", room_name, status="active")

        # Step 2: Leave room (simulates successful room leave)
        self.world_state_manager.update_channel_status(room_id, "left_by_bot")

        # Verify channel status was updated
        channel = self.world_state_manager.get_channel(room_id)
        self.assertIsNotNone(channel)
        self.assertEqual(channel.status, "left_by_bot")

    def test_end_to_end_kick_workflow(self):
        """Test complete kick workflow"""
        room_id = "!testroom:matrix.org"
        room_name = "Test Room"

        # Step 1: Add active channel
        self.world_state_manager.add_channel(room_id, "matrix", room_name, status="active")

        # Step 2: Get kicked (simulates MatrixObserver processing a kick event)
        self.world_state_manager.update_channel_status(room_id, "kicked")

        # Verify channel status was updated
        channel = self.world_state_manager.get_channel(room_id)
        self.assertIsNotNone(channel)
        self.assertEqual(channel.status, "kicked")

    def test_channel_status_transitions(self):
        """Test various channel status transitions"""
        room_id = "!testroom:matrix.org"
        room_name = "Test Room"

        # Start with invited status
        self.world_state_manager.add_channel(room_id, "matrix", room_name, status="invited")
        channel = self.world_state_manager.get_channel(room_id)
        self.assertEqual(channel.status, "invited")

        # Transition to active (accepted invite)
        self.world_state_manager.update_channel_status(room_id, "active")
        channel = self.world_state_manager.get_channel(room_id)
        self.assertEqual(channel.status, "active")

        # Transition to left_by_bot
        self.world_state_manager.update_channel_status(room_id, "left_by_bot")
        channel = self.world_state_manager.get_channel(room_id)
        self.assertEqual(channel.status, "left_by_bot")

        # Verify timestamp updates
        self.assertGreater(channel.last_status_update, 0)


if __name__ == "__main__":
    # Run the tests
    unittest.main()
