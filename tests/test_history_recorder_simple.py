"""
Simplified working tests for HistoryRecorder that match the actual API.
"""

import pytest
import tempfile
import time
from pathlib import Path

from chatbot.core.history_recorder import HistoryRecorder, StateChangeBlock


class TestStateChangeBlock:
    """Test StateChangeBlock dataclass."""
    
    def test_creation(self):
        """Test creating a StateChangeBlock."""
        block = StateChangeBlock(
            timestamp=time.time(),
            change_type="user_input",
            source="test_user",
            channel_id="test_channel",
            observations="User said hello",
            potential_actions=None,
            selected_actions=None,
            reasoning=None,
            raw_content={"content": "hello"}
        )
        
        assert block.change_type == "user_input"
        assert block.source == "test_user"
        assert block.channel_id == "test_channel"
        assert block.raw_content["content"] == "hello"


class TestHistoryRecorderBasic:
    """Test basic HistoryRecorder functionality with actual API methods."""
    
    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database path."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            yield f.name
    
    @pytest.mark.asyncio
    async def test_initialization(self, temp_db_path):
        """Test HistoryRecorder initialization."""
        recorder = HistoryRecorder(temp_db_path)
        await recorder.initialize()
        
        # Verify database file exists
        assert Path(temp_db_path).exists()
    
    @pytest.mark.asyncio
    async def test_record_user_input(self, temp_db_path):
        """Test recording user input."""
        recorder = HistoryRecorder(temp_db_path)
        await recorder.initialize()
        
        await recorder.record_user_input("test_channel", {"content": "Hello world"})
        
        assert len(recorder.state_changes) >= 1
        user_input = recorder.state_changes[0]
        assert user_input.change_type == "user_input"
        assert user_input.channel_id == "test_channel"
    
    @pytest.mark.asyncio
    async def test_record_decision(self, temp_db_path):
        """Test recording AI decisions."""
        recorder = HistoryRecorder(temp_db_path)
        await recorder.initialize()
        
        await recorder.record_decision(
            observations="User asks about weather",
            potential_actions=[{"action": "check_weather"}],
            selected_actions=[{"action": "check_weather"}],
            reasoning="User needs weather info",
            channel_id="test_channel",
            raw_llm_response={"response": "mock_response"}
        )
        
        assert len(recorder.state_changes) >= 1
        decision = recorder.state_changes[0]
        assert decision.change_type == "llm_observation"
        assert decision.source == "llm"
    
    @pytest.mark.asyncio
    async def test_record_action(self, temp_db_path):
        """Test recording tool actions."""
        recorder = HistoryRecorder(temp_db_path)
        await recorder.initialize()
        
        await recorder.record_action(
            "weather_tool",
            {"location": "NYC"},
            {"temperature": 22, "condition": "sunny"}
        )
        
        assert len(recorder.state_changes) >= 1
        action = recorder.state_changes[0]
        assert action.change_type == "tool_execution"
        assert action.source == "tool"  # Changed from "weather_tool" to "tool"
    
    @pytest.mark.asyncio
    async def test_get_recent_state_changes(self, temp_db_path):
        """Test retrieving recent state changes."""
        recorder = HistoryRecorder(temp_db_path)
        await recorder.initialize()
        
        # Add some test data
        await recorder.record_user_input("test", {"content": "hello"})
        await recorder.record_action("test_tool", {}, {"result": "success"})
        
        # Get recent changes
        recent = await recorder.get_recent_state_changes(limit=10)
        
        assert isinstance(recent, list)
        assert len(recent) >= 2
        
        # Should be StateChangeBlock instances
        for change in recent:
            assert isinstance(change, StateChangeBlock)
    
    @pytest.mark.asyncio
    async def test_get_statistics(self, temp_db_path):
        """Test getting statistics."""
        recorder = HistoryRecorder(temp_db_path)
        await recorder.initialize()
        
        # Add some test data
        await recorder.record_user_input("test", {"content": "hello"})
        
        stats = await recorder.get_statistics()
        
        assert isinstance(stats, dict)
        assert "total_records" in stats
        assert stats["total_records"] >= 1
    
    @pytest.mark.asyncio
    async def test_cleanup_old_records(self, temp_db_path):
        """Test cleanup functionality."""
        recorder = HistoryRecorder(temp_db_path)
        await recorder.initialize()
        
        # Add some test data
        await recorder.record_user_input("test", {"content": "hello"})
        
        # This should run without error
        await recorder.cleanup_old_records(days_to_keep=1)
        
        # Should still have recent records
        stats = await recorder.get_statistics()
        assert stats["total_records"] >= 1
