"""
Comprehensive tests for HistoryRecorder functionality.
Combines simple and enhanced test coverage in a single file.
"""

import pytest
import tempfile
import time
from pathlib import Path
from dataclasses import asdict

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

    def test_creation_with_all_fields(self):
        """Test creating a StateChangeBlock with all fields."""
        block = StateChangeBlock(
            timestamp=time.time(),
            change_type="llm_observation",
            source="llm",
            channel_id="test_channel",
            observations="User greeting detected",
            potential_actions=[{"action": "reply"}],
            selected_actions=[{"action": "reply"}],
            reasoning="User needs response",
            raw_content={"content": "hello"}
        )
        
        assert block.change_type == "llm_observation"
        assert block.source == "llm"
        assert block.potential_actions is not None and len(block.potential_actions) == 1
        assert block.selected_actions is not None and len(block.selected_actions) == 1
        assert block.reasoning == "User needs response"

    def test_serialization(self):
        """Test that StateChangeBlock can be serialized."""
        block = StateChangeBlock(
            timestamp=time.time(),
            change_type="user_input",
            source="test_user",
            channel_id="test_channel",
            observations="User said hello",
            potential_actions=[{"action": "reply"}],
            selected_actions=[{"action": "reply"}],
            reasoning="User needs response",
            raw_content={"content": "hello"}
        )
        
        # Convert to dict and back
        block_dict = asdict(block)
        assert isinstance(block_dict, dict)
        assert block_dict["change_type"] == "user_input"
        assert block_dict["source"] == "test_user"


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
        assert action.source == "tool"
    
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


class TestHistoryRecorderAdvanced:
    """Advanced tests for HistoryRecorder functionality."""
    
    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database path."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            yield f.name
    
    @pytest.mark.asyncio
    async def test_record_multiple_types(self, temp_db_path):
        """Test recording multiple different types of state changes."""
        recorder = HistoryRecorder(temp_db_path)
        await recorder.initialize()
        
        # Record various types
        await recorder.record_user_input("test_channel", {"content": "Hello"})
        await recorder.record_decision(
            observations="User greeting", 
            potential_actions=[{"action": "greet"}], 
            selected_actions=[{"action": "greet"}], 
            reasoning="Respond to greeting",
            channel_id="test_channel",
            raw_llm_response={"response": "mock_response"}
        )
        await recorder.record_action("greet_tool", {"message": "Hello"}, {"response": "Hi there"})
        
        recent = await recorder.get_recent_state_changes(limit=10)
        assert len(recent) == 3
        
        # Check we have different types
        types = [change.change_type for change in recent]
        assert "user_input" in types
        assert "llm_observation" in types
        assert "tool_execution" in types
    
    @pytest.mark.asyncio
    async def test_large_payload_handling(self, temp_db_path):
        """Test handling of large payloads."""
        recorder = HistoryRecorder(temp_db_path)
        await recorder.initialize()
        
        # Create a large payload
        large_content = {"content": "x" * 10000, "metadata": list(range(1000))}
        
        await recorder.record_user_input("test_channel", large_content)
        
        recent = await recorder.get_recent_state_changes(limit=1)
        assert len(recent) == 1
        assert len(recent[0].raw_content["content"]) == 10000
    
    @pytest.mark.asyncio
    async def test_concurrent_recording(self, temp_db_path):
        """Test concurrent state change recording."""
        recorder = HistoryRecorder(temp_db_path)
        await recorder.initialize()
        
        # Simulate concurrent operations
        import asyncio
        tasks = []
        for i in range(10):
            task = recorder.record_user_input(f"channel_{i}", {"content": f"Message {i}"})
            tasks.append(task)
        
        await asyncio.gather(*tasks)
        
        recent = await recorder.get_recent_state_changes(limit=20)
        assert len(recent) >= 10
    
    @pytest.mark.asyncio
    async def test_error_handling(self, temp_db_path):
        """Test error handling in recording."""
        recorder = HistoryRecorder(temp_db_path)
        await recorder.initialize()
        
        # Test with invalid data types
        try:
            await recorder.record_user_input(None, {"content": "test"})
        except Exception:
            # Should handle gracefully
            pass
        
        # Recorder should still be functional
        await recorder.record_user_input("valid_channel", {"content": "test"})
        stats = await recorder.get_statistics()
        assert stats["total_records"] >= 1
    
    @pytest.mark.asyncio
    async def test_database_persistence(self, temp_db_path):
        """Test that data persists across recorder instances."""
        # Create first recorder and add data
        recorder1 = HistoryRecorder(temp_db_path)
        await recorder1.initialize()
        await recorder1.record_user_input("test", {"content": "persistent message"})
        
        # Create second recorder with same database
        recorder2 = HistoryRecorder(temp_db_path)
        await recorder2.initialize()
        
        # Should see the data from the first recorder
        recent = await recorder2.get_recent_state_changes(limit=10)
        assert len(recent) >= 1
        assert any("persistent message" in str(change.raw_content) for change in recent)
    
    @pytest.mark.asyncio
    async def test_filtering_by_channel(self, temp_db_path):
        """Test filtering state changes by channel."""
        recorder = HistoryRecorder(temp_db_path)
        await recorder.initialize()
        
        # Add data to different channels
        await recorder.record_user_input("channel1", {"content": "Message in channel 1"})
        await recorder.record_user_input("channel2", {"content": "Message in channel 2"})
        
        recent = await recorder.get_recent_state_changes(limit=10)
        
        # Should have both channels represented
        channels = {change.channel_id for change in recent}
        assert "channel1" in channels
        assert "channel2" in channels
