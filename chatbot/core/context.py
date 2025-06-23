#!/usr/bin/env python3
"""
Context Manager - DEPRECATED

This module has been fully deprecated in favor of PayloadBuilder for context management.
It now only serves as a delegation layer to HistoryRecorder for message storage.

All context construction for AI should use PayloadBuilder, which provides:
- Full payload construction with intelligent filtering
- Node-based payload construction for large datasets
- Optimized context delivery without stateful storage

This class remains only for compatibility with existing message storage workflows.
"""

import logging
import time
from typing import Any, Dict, List, Optional

from .world_state import WorldStateManager
from .history_recorder import HistoryRecorder, StateChangeBlock

logger = logging.getLogger(__name__)


class ContextManager:
    """
    DEPRECATED: Context Manager now only delegates to HistoryRecorder.
    Use PayloadBuilder for AI context construction instead.
    """

    def __init__(self, world_state_manager: WorldStateManager, db_path: str):
        self.world_state = world_state_manager
        self.db_path = db_path
        self.history_recorder = HistoryRecorder(db_path)
        logger.info("ContextManager: Initialized (DEPRECATED - use PayloadBuilder for context)")

    async def _store_state_change(self, state_change: StateChangeBlock):
        """Store state change using HistoryRecorder"""
        try:
            await self.history_recorder.record_state_change(state_change)
            logger.debug(f"ContextManager: Stored state change: {state_change.change_type}")
        except Exception as e:
            logger.error(f"ContextManager: Failed to store state change: {e}")

    async def add_user_message(self, channel_id: str, message: Dict[str, Any]):
        """Add a user message - delegates to HistoryRecorder"""
        await self._store_state_change(
            StateChangeBlock(
                timestamp=time.time(),
                change_type="user_message",
                source="user",
                channel_id=channel_id,
                observations=None,
                potential_actions=None,
                selected_actions=None,
                reasoning=None,
                raw_content=message,
            )
        )
        logger.debug(f"ContextManager: Added user message to {channel_id}")

    async def add_assistant_message(self, channel_id: str, message: Dict[str, Any]):
        """Add an assistant message - delegates to HistoryRecorder"""
        # Parse LLM response if it's in our expected format
        parsed_response = await self._parse_llm_response(message.get("content", ""))

        assistant_msg = {
            **message,
            "timestamp": time.time(),
            "type": "assistant",
            "parsed_response": parsed_response,
        }

        # Store as state change if it contains valid structured response
        if parsed_response:
            await self._store_state_change(
                StateChangeBlock(
                    timestamp=time.time(),
                    change_type="llm_observation",
                    source="llm",
                    channel_id=channel_id,
                    observations=parsed_response.get("observations"),
                    potential_actions=parsed_response.get("potential_actions"),
                    selected_actions=parsed_response.get("selected_actions"),
                    reasoning=parsed_response.get("reasoning"),
                    raw_content=assistant_msg,
                )
            )

        logger.debug(f"ContextManager: Added assistant message to {channel_id}")

    async def _parse_llm_response(self, content: str) -> Optional[Dict[str, Any]]:
        """Parse LLM response for structured data"""
        try:
            # Try to extract JSON from the response
            content = content.strip()

            # Look for JSON block
            if "```json" in content:
                start = content.find("```json") + 7
                end = content.find("```", start)
                if end != -1:
                    json_content = content[start:end].strip()
                    import json
                    parsed = json.loads(json_content)
                    if isinstance(parsed, dict):
                        return parsed

            return None
        except Exception as e:
            logger.debug(f"ContextManager: Could not parse LLM response as structured data: {e}")
            return None

    async def add_tool_result(self, channel_id: str, tool_name: str, result: Any):
        """Add tool result - delegates to HistoryRecorder"""
        await self._store_state_change(
            StateChangeBlock(
                timestamp=time.time(),
                change_type="tool_result",
                source="tool",
                channel_id=channel_id,
                observations=None,
                potential_actions=None,
                selected_actions=[{"tool": tool_name, "result": str(result)[:1000]}],
                reasoning=f"Tool {tool_name} executed",
                raw_content={"tool": tool_name, "result": result},
            )
        )
        logger.debug(f"ContextManager: Added tool result from {tool_name} to {channel_id}")

    async def add_world_state_update(self, update_type: str, update_data: Any):
        """Add world state update - delegates to HistoryRecorder"""
        await self._store_state_change(
            StateChangeBlock(
                timestamp=time.time(),
                change_type="world_state_update",
                source="system",
                channel_id=None,
                observations=f"World state update: {update_type}",
                potential_actions=None,
                selected_actions=[{"action": "world_state_update", "type": update_type}],
                reasoning=f"World state updated: {update_type}",
                raw_content=update_data,
            )
        )
        logger.debug(f"ContextManager: Added world state update: {update_type}")

    async def get_state_changes(
        self,
        channel_id: Optional[str] = None,
        change_type: Optional[str] = None,
        since_timestamp: Optional[float] = None,
        limit: int = 100,
    ) -> List[StateChangeBlock]:
        """Retrieve stored state changes with filtering using HistoryRecorder"""
        # Note: since_timestamp filtering is not supported by HistoryRecorder yet
        # This is a compatibility method that delegates to HistoryRecorder
        return await self.history_recorder.get_recent_state_changes(
            channel_id=channel_id,
            change_type=change_type,
            limit=limit
        )

    async def export_state_changes_for_training(
        self, output_path: str, format: str = "jsonl"
    ) -> str:
        """Export state changes for training or analysis using HistoryRecorder"""
        return await self.history_recorder.export_state_changes_for_training(
            output_path=output_path,
            format=format
        )


