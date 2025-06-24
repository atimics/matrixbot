#!/usr/bin/env python3
"""
Test the Commander/Sub-Agent Architecture Integration

This module tests the integration between the ProcessingHub, AdaptiveProcessor (Commander AI),
and MissionProcessor (Sub-Agent) to ensure the new architecture works correctly.
"""

import asyncio
import logging
import pytest
import pytest_asyncio
import tempfile
import time
from unittest.mock import Mock, AsyncMock

from chatbot.core.container import DependencyContainer
from chatbot.core.world_state.structures import Mission, Channel, Message, WorldStateData
from chatbot.config import settings

logger = logging.getLogger(__name__)


class TestCommanderSubAgentArchitecture:
    """Test the Commander/Sub-Agent architecture integration."""

    @pytest_asyncio.fixture
    async def container(self):
        """Create a dependency container for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_db:
            db_path = tmp_db.name

        container = DependencyContainer(db_path=db_path)
        
        # Mock settings to avoid API dependencies
        original_api_key = settings.openrouter_api_key
        settings.openrouter_api_key = "test_api_key"
        
        try:
            await container.initialize()
            yield container
        finally:
            await container.cleanup()
            settings.openrouter_api_key = original_api_key

    @pytest.mark.asyncio
    async def test_container_initialization(self, container):
        """Test that the container properly initializes the Commander/Sub-Agent architecture."""
        # Verify processing hub is initialized
        assert container.processing_hub is not None
        
        # Verify Commander and Sub-Agent components are configured
        hub = container.processing_hub
        assert hub.commander_processor is not None
        assert hub.lightweight_ai_engine is not None
        assert hub.tool_registry is not None
        
        # Verify architecture mode
        assert hub.current_processing_mode == "commander_sub_agent"

    @pytest.mark.asyncio 
    async def test_channel_categorization(self, container):
        """Test channel categorization into mission vs strategic channels."""
        hub = container.processing_hub
        world_state_manager = container.world_state_manager
        
        # Create test channels
        channel_with_mission = Channel(
            id="test_channel_mission",
            name="Channel with Mission",
            type="matrix"
        )
        # Simulate active mission assignment  
        channel_with_mission.current_mission_id = 'mission_123'
        
        channel_strategic = Channel(
            id="test_channel_strategic", 
            name="Strategic Channel",
            type="matrix"
        )
        
        # Add channels to world state
        world_state_data = world_state_manager.get_state_data()
        world_state_data.channels["test_channel_mission"] = channel_with_mission
        world_state_data.channels["test_channel_strategic"] = channel_strategic
        
        # Test categorization
        active_channels = ["test_channel_mission", "test_channel_strategic"]
        mission_channels, strategic_channels = await hub._categorize_channels(active_channels)
        
        assert "test_channel_mission" in mission_channels
        assert "test_channel_strategic" in strategic_channels
        assert len(mission_channels) == 1
        assert len(strategic_channels) == 1

    @pytest.mark.asyncio
    async def test_mission_context_generation(self, container):
        """Test mission context generation for Sub-Agents."""
        hub = container.processing_hub
        world_state_manager = container.world_state_manager
        
        # Create test mission
        mission = Mission(
            id="test_mission",
            objective="Test mission objective",
            status="active",
            channel_id="test_channel"
        )
        
        # Create test channel with messages
        channel = Channel(
            id="test_channel",
            name="Test Channel", 
            type="matrix"
        )
        channel.recent_messages = [
            Message(
                id="msg1",
                content="Test message 1",
                channel_type="matrix",
                sender="user1",
                timestamp=time.time()
            )
        ]
        
        # Add to world state
        world_state_data = world_state_manager.get_state_data()
        world_state_data.missions = {"test_mission": mission}
        world_state_data.channels["test_channel"] = channel
        
        # Test context generation
        context = hub._get_mission_context("test_mission", "test_channel")
        
        assert context["mission_id"] == "test_mission"
        assert context["channel_id"] == "test_channel"
        assert context["mission_data"] is not None
        assert context["channel_data"] is not None
        assert len(context["recent_messages"]) == 1

    @pytest.mark.asyncio
    async def test_world_state_summary_generation(self, container):
        """Test world state summary generation for strategic analysis."""
        hub = container.processing_hub
        world_state_manager = container.world_state_manager
        
        # Add some test data
        world_state_data = world_state_manager.get_state_data()
        world_state_data.channels["channel1"] = Channel(id="channel1", name="Test", type="matrix")
        world_state_data.missions = {"mission1": Mission(id="mission1", objective="Test")}
        
        # Test summary generation
        summary = hub._get_world_state_summary()
        
        assert "total_channels" in summary
        assert "active_missions" in summary
        assert "recent_activity_count" in summary
        assert "timestamp" in summary
        assert summary["total_channels"] == 1
        assert summary["active_missions"] == 1

    @pytest.mark.asyncio
    async def test_system_capacity_info(self, container):
        """Test system capacity information generation."""
        hub = container.processing_hub
        
        # Test capacity info
        capacity = hub._get_system_capacity_info()
        
        assert "active_sub_agents" in capacity
        assert "max_concurrent_missions" in capacity  
        assert "cycle_count" in capacity
        assert "processing_mode" in capacity
        assert capacity["processing_mode"] == "commander_sub_agent"

    @pytest.mark.asyncio
    async def test_completed_mission_cleanup(self, container):
        """Test cleanup of completed missions and Sub-Agents.""" 
        hub = container.processing_hub
        world_state_manager = container.world_state_manager
        
        # Create completed mission
        completed_mission = Mission(
            id="completed_mission",
            objective="Completed task",
            status="completed"
        )
        
        # Add to world state and tracking
        world_state_data = world_state_manager.get_state_data()
        world_state_data.missions = {"completed_mission": completed_mission}
        
        # Simulate active sub-agent
        mock_sub_agent = Mock()
        hub.active_sub_agents["completed_mission"] = mock_sub_agent
        hub.sub_agent_performance["completed_mission"] = {"tasks_completed": 5}
        
        # Test cleanup
        await hub._cleanup_completed_missions()
        
        # Verify cleanup
        assert "completed_mission" not in hub.active_sub_agents
        assert "completed_mission" not in hub.sub_agent_performance

    def test_architecture_mode_configuration(self, container):
        """Test that the architecture is properly configured to Commander/Sub-Agent mode."""
        hub = container.processing_hub
        
        # Verify mode
        assert hub.current_processing_mode == "commander_sub_agent"
        
        # Verify components
        assert hub.commander_processor is not None
        assert hub.lightweight_ai_engine is not None
        
        # Verify legacy components are marked deprecated
        assert hub.traditional_processor is None
        assert hub.node_processor is None

    def test_performance_tracking_initialization(self, container):
        """Test that performance tracking is properly initialized."""
        hub = container.processing_hub
        
        # Verify tracking structures
        assert isinstance(hub.active_sub_agents, dict)
        assert isinstance(hub.sub_agent_performance, dict)
        assert isinstance(hub.payload_size_history, list)
        
        # Verify initially empty
        assert len(hub.active_sub_agents) == 0
        assert len(hub.sub_agent_performance) == 0


if __name__ == "__main__":
    # Enable logging for debugging
    logging.basicConfig(level=logging.DEBUG)
    
    # Run tests
    pytest.main([__file__, "-v"])
