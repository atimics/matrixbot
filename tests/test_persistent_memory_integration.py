"""
Test suite for persistent memory integration.

Tests the complete integration of HistoryRecorder with MainOrchestrator
for persistent memory functionality across system restarts.
"""

import asyncio
import logging
import tempfile
import time
import pytest
from pathlib import Path

from chatbot.core.orchestration.main_orchestrator import MainOrchestrator, OrchestratorConfig
from chatbot.core.world_state.structures import MemoryEntry

# Configure logging for tests
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TestPersistentMemoryIntegration:
    """Test the complete persistent memory integration."""

    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database path for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
            db_path = temp_db.name
        yield db_path
        # Cleanup
        try:
            Path(db_path).unlink()
        except:
            pass

    @pytest.mark.asyncio
    async def test_history_recorder_initialization(self, temp_db_path):
        """Test that HistoryRecorder is properly initialized and connected."""
        config = OrchestratorConfig(db_path=temp_db_path)
        orchestrator = MainOrchestrator(config)
        
        # Verify HistoryRecorder is initialized
        assert orchestrator.history_recorder is not None
        assert orchestrator.world_state.history_recorder is not None
        
        # Initialize the database
        await orchestrator.history_recorder.initialize()
        
        logger.info("✓ HistoryRecorder correctly initialized and connected")

    @pytest.mark.asyncio
    async def test_memory_persistence_workflow(self, temp_db_path):
        """Test the complete memory persistence workflow."""
        config = OrchestratorConfig(db_path=temp_db_path)
        orchestrator = MainOrchestrator(config)
        await orchestrator.history_recorder.initialize()
        
        # Create a test memory entry
        test_memory = MemoryEntry(
            user_platform_id="matrix:@testuser:example.com",
            timestamp=time.time(),
            content="User likes discussing AI and machine learning topics",
            memory_type="preference",
            importance=0.8,
            ai_summary="User has strong interest in AI/ML"
        )
        
        # Add memory through world state manager (should persist automatically)
        orchestrator.world_state.add_user_memory(
            "matrix:@testuser:example.com",
            test_memory
        )
        
        # Give it a moment for async persistence
        await asyncio.sleep(0.1)
        
        # Verify memory is in world state
        memories = orchestrator.world_state.get_user_memories("matrix:@testuser:example.com")
        assert len(memories) >= 1
        assert memories[0].content == test_memory.content
        
        logger.info("✓ Memory added to world state and persisted successfully")

    @pytest.mark.asyncio
    async def test_state_restoration(self, temp_db_path):
        """Test state restoration across system restarts."""
        # First session: create and persist data
        config1 = OrchestratorConfig(db_path=temp_db_path)
        orchestrator1 = MainOrchestrator(config1)
        await orchestrator1.history_recorder.initialize()
        
        test_memory = MemoryEntry(
            user_platform_id="matrix:@persistent_user:example.com",
            timestamp=time.time(),
            content="This memory should persist across restarts",
            memory_type="fact",
            importance=0.9
        )
        
        orchestrator1.world_state.add_user_memory(
            "matrix:@persistent_user:example.com",
            test_memory
        )
        
        await asyncio.sleep(0.1)  # Allow persistence
        
        # Second session: restore state
        config2 = OrchestratorConfig(db_path=temp_db_path)
        orchestrator2 = MainOrchestrator(config2)
        await orchestrator2.history_recorder.initialize()
        
        # Restore persistent state
        await orchestrator2.world_state.restore_persistent_state()
        
        # Verify memories can be loaded from persistence
        persisted_memories = await orchestrator2.history_recorder.load_user_memories(
            "matrix:@persistent_user:example.com"
        )
        assert len(persisted_memories) >= 1
        assert persisted_memories[0].content == test_memory.content
        
        logger.info("✓ State restoration completed successfully")

    @pytest.mark.asyncio
    async def test_research_entry_persistence(self, temp_db_path):
        """Test research entry persistence functionality."""
        config = OrchestratorConfig(db_path=temp_db_path)
        orchestrator = MainOrchestrator(config)
        await orchestrator.history_recorder.initialize()
        
        research_data = {
            "title": "AI Safety Research",
            "content": "Important findings about AI alignment and safety measures",
            "source_url": "https://example.com/ai-safety",
            "confidence_level": 8,
            "tags": ["ai", "safety", "research"],
            "related_topics": ["alignment", "ethics"]
        }
        
        # Store research entry
        result = await orchestrator.history_recorder.store_research_entry(
            "ai_safety", research_data
        )
        assert result is True
        
        # Load and verify research entries
        research_entries = await orchestrator.history_recorder.load_research_entries()
        assert "ai_safety" in research_entries
        assert research_entries["ai_safety"]["title"] == "AI Safety Research"
        
        logger.info("✓ Research entry persistence working correctly")

    @pytest.mark.asyncio
    async def test_state_change_recording(self, temp_db_path):
        """Test that state changes are properly recorded."""
        config = OrchestratorConfig(db_path=temp_db_path)
        orchestrator = MainOrchestrator(config)
        await orchestrator.history_recorder.initialize()
        
        # Record user input
        await orchestrator.history_recorder.record_user_input(
            "matrix:test_room",
            {"content": "Hello, how are you?", "sender": "@testuser:example.com"}
        )
        
        # Record AI decision
        await orchestrator.history_recorder.record_decision(
            channel_id="matrix:test_room",
            observations="User is greeting",
            potential_actions=[{"action": "greet_back"}],
            selected_actions=[{"action": "greet_back"}],
            reasoning="Appropriate to respond to greeting",
            raw_llm_response={"type": "greeting_response"}
        )
        
        # Verify state changes were recorded
        state_changes = await orchestrator.history_recorder.get_recent_state_changes(limit=10)
        assert len(state_changes) >= 2
        
        # Verify types
        change_types = [change.change_type for change in state_changes]
        assert "user_input" in change_types
        assert "llm_observation" in change_types
        
        logger.info("✓ State changes recorded successfully")

    @pytest.mark.asyncio
    async def test_memory_search_functionality(self, temp_db_path):
        """Test memory search functionality with persistence."""
        config = OrchestratorConfig(db_path=temp_db_path)
        orchestrator = MainOrchestrator(config)
        await orchestrator.history_recorder.initialize()
        
        user_id = "matrix:@searchtest:example.com"
        
        # Add multiple memories
        memories = [
            MemoryEntry(
                user_platform_id=user_id,
                timestamp=time.time(),
                content="User loves machine learning and neural networks",
                memory_type="preference",
                importance=0.9
            ),
            MemoryEntry(
                user_platform_id=user_id,
                timestamp=time.time(),
                content="User works as a software engineer at a tech company",
                memory_type="fact",
                importance=0.7
            ),
            MemoryEntry(
                user_platform_id=user_id,
                timestamp=time.time(),
                content="User mentioned they have a cat named Whiskers",
                memory_type="observation",
                importance=0.5
            )
        ]
        
        for memory in memories:
            orchestrator.world_state.add_user_memory(user_id, memory)
        
        await asyncio.sleep(0.1)  # Allow persistence
        
        # Test search functionality
        ml_memories = orchestrator.world_state.search_user_memories(
            user_id, "machine learning", top_k=2
        )
        assert len(ml_memories) >= 1
        assert "machine learning" in ml_memories[0].content.lower()
        
        work_memories = orchestrator.world_state.search_user_memories(
            user_id, "software engineer", top_k=2
        )
        assert len(work_memories) >= 1
        assert "software engineer" in work_memories[0].content.lower()
        
        # Test persistence across sessions
        config2 = OrchestratorConfig(db_path=temp_db_path)
        orchestrator2 = MainOrchestrator(config2)
        await orchestrator2.history_recorder.initialize()
        
        # Load memories directly from persistence
        persisted_memories = await orchestrator2.history_recorder.load_user_memories(user_id)
        assert len(persisted_memories) == 3
        
        logger.info("✓ Memory search and persistence working correctly")

    @pytest.mark.asyncio
    async def test_full_integration_workflow(self, temp_db_path):
        """Test the complete integration workflow end-to-end."""
        # Session 1: Initialize and populate data
        config1 = OrchestratorConfig(db_path=temp_db_path)
        orchestrator1 = MainOrchestrator(config1)
        await orchestrator1.history_recorder.initialize()
        
        # Add user memories
        user_id = "matrix:@integration_test:example.com"
        memory = MemoryEntry(
            user_platform_id=user_id,
            timestamp=time.time(),
            content="Integration test memory",
            memory_type="test",
            importance=1.0
        )
        orchestrator1.world_state.add_user_memory(user_id, memory)
        
        # Add research data
        research_data = {
            "title": "Integration Test Research",
            "content": "Test research content",
            "confidence_level": 10
        }
        await orchestrator1.history_recorder.store_research_entry("integration_test", research_data)
        
        # Record state changes
        await orchestrator1.history_recorder.record_user_input(
            "integration_channel", {"content": "Integration test message"}
        )
        
        await asyncio.sleep(0.1)  # Allow persistence
        
        # Session 2: Restore and verify
        config2 = OrchestratorConfig(db_path=temp_db_path)
        orchestrator2 = MainOrchestrator(config2)
        await orchestrator2.history_recorder.initialize()
        await orchestrator2.world_state.restore_persistent_state()
        
        # Verify all data is accessible
        memories = await orchestrator2.history_recorder.load_user_memories(user_id)
        assert len(memories) >= 1
        
        research = await orchestrator2.history_recorder.load_research_entries()
        assert "integration_test" in research
        
        state_changes = await orchestrator2.history_recorder.get_recent_state_changes()
        assert len(state_changes) >= 1
        
        logger.info("✓ Full integration workflow completed successfully")


@pytest.mark.integration
class TestPersistentMemoryPerformance:
    """Test performance aspects of persistent memory."""

    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database path for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
            db_path = temp_db.name
        yield db_path
        try:
            Path(db_path).unlink()
        except:
            pass

    @pytest.mark.asyncio
    async def test_bulk_memory_operations(self, temp_db_path):
        """Test performance with bulk memory operations."""
        config = OrchestratorConfig(db_path=temp_db_path)
        orchestrator = MainOrchestrator(config)
        await orchestrator.history_recorder.initialize()
        
        user_id = "matrix:@bulk_test:example.com"
        
        # Add many memories
        start_time = time.time()
        for i in range(50):  # Reasonable test size
            memory = MemoryEntry(
                user_platform_id=user_id,
                timestamp=time.time(),
                content=f"Bulk test memory {i}",
                memory_type="test",
                importance=0.5
            )
            orchestrator.world_state.add_user_memory(user_id, memory)
        
        await asyncio.sleep(0.5)  # Allow persistence
        end_time = time.time()
        
        # Should complete reasonably quickly
        assert end_time - start_time < 10.0  # Less than 10 seconds
        
        # Verify memories were persisted
        memories = await orchestrator.history_recorder.load_user_memories(user_id, limit=100)
        assert len(memories) >= 50
        
        logger.info(f"✓ Bulk operations completed in {end_time - start_time:.2f} seconds")
