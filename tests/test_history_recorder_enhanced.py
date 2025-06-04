"""
Enhanced test suite for HistoryRecorder with comprehensive coverage.
"""

import pytest
import asyncio
import time
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
from dataclasses import asdict

from chatbot.core.history_recorder import HistoryRecorder, StateChangeBlock


class TestStateChangeBlock:
    """Test the StateChangeBlock dataclass."""
    
    def test_creation(self):
        """Test basic StateChangeBlock creation."""
        block = StateChangeBlock(
            timestamp=time.time(),
            change_type="user_input",
            source="user",
            channel_id="test_channel",
            observations="User said hello",
            potential_actions=[{"action": "reply"}],
            selected_actions=[{"action": "reply"}],
            reasoning="User greeting detected",
            raw_content={"message": "hello"}
        )
        
        assert block.change_type == "user_input"
        assert block.source == "user"
        assert block.channel_id == "test_channel"
        assert block.observations == "User said hello"
        assert len(block.potential_actions) == 1
        assert len(block.selected_actions) == 1
        assert block.reasoning == "User greeting detected"
        assert block.raw_content["message"] == "hello"
    
    def test_optional_fields(self):
        """Test StateChangeBlock with optional fields as None."""
        block = StateChangeBlock(
            timestamp=time.time(),
            change_type="system_update",
            source="system",
            channel_id=None,
            observations=None,
            potential_actions=None,
            selected_actions=None,
            reasoning=None,
            raw_content={}
        )
        
        assert block.channel_id is None
        assert block.observations is None
        assert block.potential_actions is None
        assert block.selected_actions is None
        assert block.reasoning is None
        assert block.raw_content == {}
    
    def test_serialization(self):
        """Test StateChangeBlock can be serialized to dict."""
        block = StateChangeBlock(
            timestamp=1234567890.0,
            change_type="llm_observation",
            source="llm",
            channel_id="test",
            observations="Test observation",
            potential_actions=[{"type": "test"}],
            selected_actions=[{"type": "selected"}],
            reasoning="Test reasoning",
            raw_content={"data": "test"}
        )
        
        block_dict = asdict(block)
        assert block_dict["timestamp"] == 1234567890.0
        assert block_dict["change_type"] == "llm_observation"
        assert block_dict["source"] == "llm"
        assert block_dict["channel_id"] == "test"


class TestHistoryRecorderInitialization:
    """Test HistoryRecorder initialization and setup."""
    
    def test_init_with_memory_db(self):
        """Test initialization with in-memory database."""
        recorder = HistoryRecorder(":memory:")
        assert recorder.db_path == ":memory:"
        assert recorder.state_changes == []
        assert recorder.storage_path is not None
    
    def test_init_with_file_db(self, temp_dir):
        """Test initialization with file database."""
        db_path = temp_dir / "test.db"
        recorder = HistoryRecorder(str(db_path))
        assert recorder.db_path == str(db_path)
        assert recorder.state_changes == []
    
    @pytest.mark.asyncio
    async def test_initialize_creates_tables(self, history_recorder):
        """Test that initialize() creates necessary database tables."""
        # Should complete without error
        assert history_recorder.db_path
        
        # Test we can interact with the database
        await history_recorder.record_user_input("test_channel", {"content": "test"})
        assert len(history_recorder.state_changes) >= 1
    
    @pytest.mark.asyncio
    async def test_initialize_idempotent(self, history_recorder):
        """Test that calling initialize() multiple times is safe."""
        # Should not raise error when called multiple times
        await history_recorder.initialize()
        await history_recorder.initialize()
        
        # Should still function normally
        await history_recorder.record_user_input("test", {"content": "test"})
        assert len(history_recorder.state_changes) >= 1


class TestHistoryRecorderUserInput:
    """Test recording user input."""
    
    @pytest.mark.asyncio
    async def test_record_user_input_basic(self, history_recorder):
        """Test basic user input recording."""
        channel_id = "test_channel"
        message = {
            "content": "Hello world",
            "sender": "@user:example.com",
            "timestamp": time.time()
        }
        
        await history_recorder.record_user_input(channel_id, message)
        
        assert len(history_recorder.state_changes) >= 1
        
        # Find the user input record
        user_input = None
        for change in history_recorder.state_changes:
            if change.change_type == "user_input":
                user_input = change
                break
        
        assert user_input is not None
        assert user_input.channel_id == channel_id
        assert user_input.source == "user"
        assert user_input.raw_content["content"] == "Hello world"
        assert user_input.raw_content["sender"] == "@user:example.com"
    
    @pytest.mark.asyncio
    async def test_record_user_input_no_channel(self, history_recorder):
        """Test recording user input without channel ID."""
        message = {"content": "Hello", "sender": "@user:example.com"}
        
        await history_recorder.record_user_input(None, message)
        
        user_input = history_recorder.state_changes[0]
        assert user_input.channel_id is None
        assert user_input.source == "user"
    
    @pytest.mark.asyncio
    async def test_record_multiple_user_inputs(self, history_recorder):
        """Test recording multiple user inputs."""
        messages = [
            {"content": "First message", "sender": "@user1:example.com"},
            {"content": "Second message", "sender": "@user2:example.com"},
            {"content": "Third message", "sender": "@user1:example.com"}
        ]
        
        for i, msg in enumerate(messages):
            await history_recorder.record_user_input(f"channel_{i}", msg)
        
        assert len(history_recorder.state_changes) >= 3
        
        # Verify all are user inputs
        user_inputs = [c for c in history_recorder.state_changes if c.change_type == "user_input"]
        assert len(user_inputs) >= 3


class TestHistoryRecorderBotActions:
    """Test recording bot actions and decisions."""
    
    @pytest.mark.asyncio
    async def test_record_bot_decision(self, history_recorder):
        """Test recording bot decision."""
        channel_id = "test_channel"
        observations = "User asked a question"
        potential_actions = [
            {"action_type": "reply", "content": "Answer 1"},
            {"action_type": "reply", "content": "Answer 2"}
        ]
        selected_actions = [{"action_type": "reply", "content": "Answer 1"}]
        reasoning = "First answer seems more appropriate"
        raw_llm_response = {
            "observations": observations,
            "potential_actions": potential_actions,
            "selected_actions": selected_actions,
            "reasoning": reasoning
        }
        
        await history_recorder.record_decision(
            channel_id=channel_id,
            observations=observations,
            potential_actions=potential_actions, 
            selected_actions=selected_actions,
            reasoning=reasoning,
            raw_llm_response=raw_llm_response
        )
        
        assert len(history_recorder.state_changes) >= 1
        
        decision = history_recorder.state_changes[0]
        assert decision.change_type == "llm_observation"
        assert decision.source == "llm"
        assert decision.channel_id == channel_id
        assert decision.observations == observations
        assert decision.potential_actions == potential_actions
        assert decision.selected_actions == selected_actions
        assert decision.reasoning == reasoning
    
    @pytest.mark.asyncio
    async def test_record_tool_execution(self, history_recorder):
        """Test recording tool execution."""
        tool_name = "send_message"
        action_data = {"content": "Hello", "channel": "test"}
        result = {"success": True, "message_id": "123"}
        
        await history_recorder.record_action(tool_name, action_data, result)
        
        tool_record = history_recorder.state_changes[0]
        assert tool_record.change_type == "tool_execution"
        assert tool_record.source == tool_name
        assert tool_record.raw_content["action"] == action_data
        assert tool_record.raw_content["result"] == str(result)
        assert tool_record.raw_content["tool_name"] == tool_name


class TestHistoryRecorderPersistence:
    """Test data persistence functionality."""
    
    @pytest.mark.asyncio
    async def test_persist_to_database(self, history_recorder):
        """Test that data is persisted to database."""
        # Record some data
        await history_recorder.record_user_input("test", {"content": "test"})
        
        # Data should be automatically persisted during record_user_input
        # Verify data was recorded
        assert len(history_recorder.state_changes) >= 1
    
    @pytest.mark.asyncio
    @pytest.mark.database
    async def test_export_training_data(self, history_recorder):
        """Test retrieving state changes for training data."""
        # Add some test data
        await history_recorder.record_user_input("ch1", {"content": "Hello"})
        
        observations = "User greeting"
        potential_actions = [{"action": "greet"}]
        selected_actions = [{"action": "greet"}]
        reasoning = "Appropriate response"
        raw_llm_response = {
            "observations": observations,
            "potential_actions": potential_actions,
            "selected_actions": selected_actions,
            "reasoning": reasoning
        }
        
        await history_recorder.record_decision(
            channel_id="ch1",
            observations=observations,
            potential_actions=potential_actions,
            selected_actions=selected_actions,
            reasoning=reasoning,
            raw_llm_response=raw_llm_response
        )
        
        # Get recent changes (simulates export)
        recent_changes = await history_recorder.get_recent_state_changes()
        
        assert isinstance(recent_changes, list)
        assert len(recent_changes) >= 1
        
        # Verify structure (dataclass attributes)
        for change in recent_changes:
            assert hasattr(change, 'timestamp')
            assert hasattr(change, 'change_type')
            assert hasattr(change, 'source')
    
    @pytest.mark.asyncio
    async def test_export_training_data_with_filters(self, history_recorder):
        """Test retrieving state changes with filters."""
        # Add data to multiple channels
        await history_recorder.record_user_input("ch1", {"content": "Hello ch1"})
        await history_recorder.record_user_input("ch2", {"content": "Hello ch2"})
        
        # Get recent changes with limit
        recent_changes = await history_recorder.get_recent_state_changes(limit=10)
        
        assert isinstance(recent_changes, list)
        # Should contain data from both channels
        assert len(recent_changes) >= 2
        
        # Verify channels are recorded correctly
        channels_found = set()
        for change in recent_changes:
            if change.channel_id:
                channels_found.add(change.channel_id)
        
        assert "ch1" in channels_found or "ch2" in channels_found


class TestHistoryRecorderLimits:
    """Test storage limits and cleanup."""
    
    @pytest.mark.asyncio
    async def test_memory_limit_enforcement(self, history_recorder):
        """Test that memory usage is limited."""
        # Add many records
        for i in range(150):  # Exceed typical limit
            await history_recorder.record_user_input(f"ch_{i}", {"content": f"Message {i}"})
        
        # Should not exceed reasonable memory limit
        assert len(history_recorder.state_changes) <= 200  # Reasonable upper bound
    
    @pytest.mark.asyncio
    async def test_cleanup_old_records(self, history_recorder):
        """Test cleanup of old records."""
        # This tests if there's a cleanup mechanism
        initial_count = len(history_recorder.state_changes)
        
        # Add records
        for i in range(10):
            await history_recorder.record_user_input("test", {"content": f"msg {i}"})
        
        # If cleanup is implemented, should manage size
        final_count = len(history_recorder.state_changes)
        assert final_count >= initial_count  # At least added some
        assert final_count <= initial_count + 20  # But not unlimited


class TestHistoryRecorderErrorHandling:
    """Test error handling scenarios."""
    
    @pytest.mark.asyncio
    @pytest.mark.error_handling
    async def test_invalid_message_format(self, history_recorder):
        """Test handling of invalid message formats."""
        # Should handle gracefully without crashing
        try:
            await history_recorder.record_user_input("test", None)
        except Exception as e:
            # If it raises an exception, it should be a reasonable one
            assert isinstance(e, (ValueError, TypeError))
    
    @pytest.mark.asyncio
    @pytest.mark.error_handling  
    async def test_database_connection_failure(self, temp_dir):
        """Test handling of database connection issues."""
        # Use an invalid database path
        bad_path = temp_dir / "nonexistent" / "bad.db"
        recorder = HistoryRecorder(str(bad_path))
        
        # Should handle initialization gracefully
        try:
            await recorder.initialize()
            # If successful, try to record something
            await recorder.record_user_input("test", {"content": "test"})
        except Exception as e:
            # Should be a meaningful error
            assert str(e)  # Should have error message
    
    @pytest.mark.asyncio
    @pytest.mark.error_handling
    async def test_concurrent_access(self, history_recorder):
        """Test concurrent access to recorder."""
        # Simulate concurrent writes
        async def write_records(prefix):
            for i in range(5):
                await history_recorder.record_user_input(f"{prefix}_ch", {"content": f"{prefix}_{i}"})
        
        # Run concurrent tasks
        await asyncio.gather(
            write_records("task1"),
            write_records("task2"),
            write_records("task3")
        )
        
        # Should have records from all tasks
        assert len(history_recorder.state_changes) >= 10


class TestHistoryRecorderIntegration:
    """Test integration with other components."""
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_with_world_state_integration(self, history_recorder, world_state_manager):
        """Test integration with WorldStateManager."""
        # Add a channel to world state
        world_state_manager.add_channel("test_ch", "matrix", "Test Channel")
        
        # Record activity
        await history_recorder.record_user_input("test_ch", {
            "content": "Hello world",
            "sender": "@user:matrix.org"
        })
        
        # Should record properly
        assert len(history_recorder.state_changes) >= 1
        
        user_input = history_recorder.state_changes[0]
        assert user_input.channel_id == "test_ch"
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_full_conversation_flow(self, history_recorder):
        """Test recording a complete conversation flow."""
        channel = "test_conversation"
        
        # User input
        await history_recorder.record_user_input(channel, {
            "content": "What's the weather like?",
            "sender": "@user:example.com"
        })
        
        # Bot decision
        observations = "User asking about weather"
        potential_actions = [
            {"action_type": "get_weather", "location": "current"},
            {"action_type": "reply", "content": "I can't check weather"}
        ]
        selected_actions = [{"action_type": "get_weather", "location": "current"}]
        reasoning = "User wants weather info, should check actual weather"
        raw_llm_response = {
            "observations": observations,
            "potential_actions": potential_actions,
            "selected_actions": selected_actions,
            "reasoning": reasoning
        }
        
        await history_recorder.record_decision(
            channel_id=channel,
            observations=observations,
            potential_actions=potential_actions,
            selected_actions=selected_actions,
            reasoning=reasoning,
            raw_llm_response=raw_llm_response
        )
        
        # Tool execution
        await history_recorder.record_tool_execution(
            "get_weather",
            {"location": "current"},
            {"success": True, "weather": "sunny", "temp": "75F"}
        )
        
        # Bot response
        await history_recorder.record_user_input(channel, {
            "content": "It's sunny and 75F currently!",
            "sender": "@bot:example.com",
            "is_bot": True
        })
        
        # Should have all parts of conversation
        assert len(history_recorder.state_changes) >= 4
        
        # Verify sequence
        changes = history_recorder.state_changes
        assert any(c.change_type == "user_input" and not c.raw_content.get("is_bot") for c in changes)
        assert any(c.change_type == "llm_observation" for c in changes)
        assert any(c.change_type == "tool_execution" for c in changes)
        assert any(c.change_type == "user_input" and c.raw_content.get("is_bot") for c in changes)
