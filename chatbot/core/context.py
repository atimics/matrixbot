#!/usr/bin/env python3
"""
Context Manager

This module manages conversation context with an evolving world state in the system prompt,
while permanently storing all valid state change blocks for later use as training data or memory.
"""

import asyncio
import json
import logging
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from sqlmodel import desc, select

from .history_recorder import StateChangeBlock
from .persistence import (
    ConsolidatedHistoryRecorder,
    DatabaseManager,
    StateChangeRecord,
)
from .world_state import WorldStateManager

logger = logging.getLogger(__name__)


@dataclass
class ConversationContext:
    """Represents the conversation context structure"""

    world_state: Dict[str, Any]
    user_messages: List[Dict[str, Any]]
    assistant_messages: List[Dict[str, Any]]
    system_prompt: str
    last_update: float


class ContextManager:
    """Manages conversation context with evolving world state and permanent state storage"""

    def __init__(self, world_state_manager: WorldStateManager, db_manager: DatabaseManager):
        self.world_state = world_state_manager
        self.contexts: Dict[str, ConversationContext] = {}

        # Use ConsolidatedHistoryRecorder for state change persistence
        self.history_recorder = ConsolidatedHistoryRecorder(db_manager)
        # Track state changes in-memory for easy inspection
        self.state_changes: List[StateChangeBlock] = []

        # Initialize storage directory (ensure parent directories exist)
        self.storage_path = Path("context_storage")
        self.storage_path.mkdir(parents=True, exist_ok=True)

        logger.info(
            "ContextManager: Initialized with ConsolidatedHistoryRecorder for state persistence"
        )

    async def get_context(self, channel_id: str) -> ConversationContext:
        """Get or create conversation context for a channel"""
        if channel_id not in self.contexts:
            await self._initialize_context(channel_id)

        # Update world state in system prompt
        await self._update_world_state_in_context(channel_id)

        return self.contexts[channel_id]

    async def _initialize_context(self, channel_id: str):
        """Initialize a new conversation context"""
        world_state_dict = self.world_state.to_dict()

        context = ConversationContext(
            world_state=world_state_dict,
            user_messages=[],
            assistant_messages=[],
            system_prompt=await self._build_world_state_system_prompt(world_state_dict),
            last_update=time.time(),
        )

        self.contexts[channel_id] = context
        logger.info(f"ContextManager: Initialized context for channel {channel_id}")

    async def _update_world_state_in_context(self, channel_id: str):
        """Update the world state in the system prompt"""
        if channel_id not in self.contexts:
            return

        context = self.contexts[channel_id]
        current_world_state = self.world_state.to_dict()

        # Only update if world state has changed
        if current_world_state != context.world_state:
            context.world_state = current_world_state
            context.system_prompt = await self._build_world_state_system_prompt(
                current_world_state
            )
            context.last_update = time.time()

            logger.debug(
                f"ContextManager: Updated world state in context for {channel_id}"
            )

    async def _build_world_state_system_prompt(
        self, world_state: Dict[str, Any]
    ) -> str:
        """Build system prompt with embedded world state"""
        return f"""You are an AI assistant with access to the current world state.

CURRENT WORLD STATE:
{json.dumps(world_state, indent=2)}

Your responses should be in the following JSON format:
{{
  "observations": "What you notice about the current state",
  "potential_actions": [
    {{
      "action_type": "send_matrix_reply",
      "parameters": {{"channel_id": "...", "reply_to_id": "...", "content": "..."}},
      "reasoning": "Why this action makes sense",
      "priority": 8
    }}
  ],
  "selected_actions": [
    // The top 1-3 actions you want to execute this cycle
  ],
  "reasoning": "Overall reasoning for your selections"
}}

Available action types:
- send_matrix_reply: Send a reply to a Matrix message
- add_context: Add context about users or chat rooms to the world state
- analyze_url: Analyze a URL for content
- observe: Make observations about the current state
- wait: Take no action this cycle

Base your decisions on the current world state and user messages."""

    async def add_user_message(self, channel_id: str, message: Dict[str, Any]):
        """Add a user message to the conversation context"""
        context = await self.get_context(channel_id)
        context.user_messages.append(
            {**message, "timestamp": time.time(), "type": "user"}
        )

        # Store as state change
        await self._store_state_change(
            StateChangeBlock(
                timestamp=time.time(),
                change_type="user_input",
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
        """Add an assistant message to the conversation context"""
        context = await self.get_context(channel_id)

        # Parse LLM response if it's in our expected format
        parsed_response = await self._parse_llm_response(message.get("content", ""))

        assistant_msg = {
            **message,
            "timestamp": time.time(),
            "type": "assistant",
            "parsed_response": parsed_response,
        }

        context.assistant_messages.append(assistant_msg)

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
                    raw_content=message,
                )
            )

        logger.debug(f"ContextManager: Added assistant message to {channel_id}")

    async def _parse_llm_response(self, content: str) -> Optional[Dict[str, Any]]:
        """Parse LLM response for structured data"""
        try:
            # Try to extract JSON from the response
            content = content.strip()

            # Look for JSON block
            if content.startswith("{") and content.endswith("}"):
                parsed = json.loads(content)

                # Validate structure
                required_fields = ["observations"]
                if all(field in parsed for field in required_fields):
                    return parsed

            # Try to find JSON within markdown code blocks

            json_match = re.search(
                r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL
            )
            if json_match:
                parsed = json.loads(json_match.group(1))
                required_fields = ["observations"]
                if all(field in parsed for field in required_fields):
                    return parsed

        except (json.JSONDecodeError, KeyError) as e:
            logger.debug(
                f"ContextManager: Could not parse LLM response as structured data: {e}"
            )

        return None

    async def add_tool_result(
        self, channel_id: str, tool_name: str, result: Dict[str, Any]
    ):
        """Add a tool execution result"""
        await self._store_state_change(
            StateChangeBlock(
                timestamp=time.time(),
                change_type="tool_execution",
                source=tool_name,
                channel_id=channel_id,
                observations=result.get("observations"),
                potential_actions=None,
                selected_actions=None,
                reasoning=result.get("reasoning"),
                raw_content=result,
            )
        )

        logger.debug(
            f"ContextManager: Added tool result from {tool_name} to {channel_id}"
        )

    async def add_world_state_update(
        self, update_type: str, update_data: Dict[str, Any]
    ):
        """Add a world state update"""
        await self._store_state_change(
            StateChangeBlock(
                timestamp=time.time(),
                change_type="world_update",
                source="system",
                channel_id=update_data.get("channel_id"),
                observations=None,
                potential_actions=None,
                selected_actions=None,
                reasoning=f"World state update: {update_type}",
                raw_content=update_data,
            )
        )

        logger.debug(f"ContextManager: Added world state update: {update_type}")

    async def _store_state_change(self, state_change: StateChangeBlock):
        """Permanently store a state change block using ConsolidatedHistoryRecorder"""
        # Record in-memory state changes list
        self.state_changes.append(state_change)
        # Persist state change using ConsolidatedHistoryRecorder
        data_to_store = {
            "source": state_change.source,
            "observations": state_change.observations,
            "potential_actions": state_change.potential_actions,
            "selected_actions": state_change.selected_actions,
            "reasoning": state_change.reasoning,
            "raw_content": state_change.raw_content,
        }

        await self.history_recorder.record_state_change(
            change_type=state_change.change_type,
            data=data_to_store,
            channel_id=state_change.channel_id,
        )

    async def get_conversation_messages(
        self, channel_id: str, include_system: bool = True
    ) -> List[Dict[str, Any]]:
        """Get conversation messages formatted for LLM API"""
        context = await self.get_context(channel_id)
        messages = []

        if include_system:
            messages.append({"role": "system", "content": context.system_prompt})

        # Interleave user and assistant messages chronologically
        all_messages = []
        all_messages.extend([{**msg, "role": "user"} for msg in context.user_messages])
        all_messages.extend(
            [{**msg, "role": "assistant"} for msg in context.assistant_messages]
        )

        # Sort by timestamp
        all_messages.sort(key=lambda x: x.get("timestamp", 0))

        for msg in all_messages:
            messages.append(
                {
                    "role": msg["role"],
                    "content": msg.get("content", ""),
                    "name": msg.get("name"),
                    "timestamp": msg.get("timestamp"),
                }
            )

        return messages

    async def get_state_changes(
        self,
        channel_id: Optional[str] = None,
        change_type: Optional[str] = None,
        since_timestamp: Optional[float] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Retrieve stored state changes with filtering using ConsolidatedHistoryRecorder"""
        async with self.history_recorder.db_manager.get_session() as session:
            query = select(StateChangeRecord).order_by(desc(StateChangeRecord.timestamp))
            if channel_id:
                query = query.where(StateChangeRecord.channel_id == channel_id)
            if change_type:
                query = query.where(StateChangeRecord.change_type == change_type)
            if since_timestamp:
                query = query.where(StateChangeRecord.timestamp > since_timestamp)

            query = query.limit(limit)
            result = await session.execute(query)
            records = result.scalars().all()

            state_changes = []
            for record in records:
                data = json.loads(record.data)
                state_changes.append(
                    {
                        "timestamp": record.timestamp,
                        "change_type": record.change_type,
                        "channel_id": record.channel_id,
                        "source": data.get("source"),
                        "observations": data.get("observations"),
                        "potential_actions": data.get("potential_actions"),
                        "selected_actions": data.get("selected_actions"),
                        "reasoning": data.get("reasoning"),
                        "raw_content": data.get("raw_content"),
                    }
                )
            return state_changes

    async def export_state_changes_for_training(
        self, output_path: str, format: str = "jsonl"
    ) -> str:
        """Export state changes for training or analysis using ConsolidatedHistoryRecorder"""
        await self.history_recorder.export_for_training(
            output_file=output_path
        )

        if format == "jsonl":
            with open(output_path, "r") as f:
                data = json.load(f)
            
            state_changes = data.get("state_changes", [])
            with open(output_path, "w") as f:
                for item in state_changes:
                    f.write(json.dumps(item) + "\n")
            return f"Exported {len(state_changes)} state changes to {output_path} in jsonl format."
        else:
            return f"Exported data to {output_path} in json format."

    async def clear_context(self, channel_id: str):
        """Clear conversation context for a channel (but keep state changes)"""
        if channel_id in self.contexts:
            del self.contexts[channel_id]
            logger.info(f"ContextManager: Cleared context for {channel_id}")

    async def get_context_summary(self, channel_id: str) -> Dict[str, Any]:
        """Get a summary of the conversation context"""
        if channel_id not in self.contexts:
            return {"error": "Context not found"}

        context = self.contexts[channel_id]

        return {
            "channel_id": channel_id,
            "user_message_count": len(context.user_messages),
            "assistant_message_count": len(context.assistant_messages),
            "last_update": context.last_update,
            "world_state_keys": list(context.world_state.keys()),
            "system_prompt_length": len(context.system_prompt),
        }
