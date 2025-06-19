#!/usr/bin/env python3
"""
Test script for persistent memory integration.

This script tests the complete integration of HistoryRecorder with MainOrchestrator
for persistent memory functionality.
"""

import asyncio
import logging
import tempfile
import time
from pathlib import Path

from chatbot.core.orchestration.main_orchestrator import MainOrchestrator, OrchestratorConfig
from chatbot.core.world_state.structures import MemoryEntry

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_persistent_memory_integration():
    """Test the complete persistent memory integration."""
    
    # Create temporary database for testing
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
        db_path = temp_db.name
    
    try:
        logger.info("Starting persistent memory integration test...")
        
        # Create orchestrator with test configuration
        config = OrchestratorConfig(
            db_path=db_path,
        )
        orchestrator = MainOrchestrator(config)
        
        # Test 1: Verify HistoryRecorder is initialized
        logger.info("Test 1: Verifying HistoryRecorder initialization...")
        assert orchestrator.history_recorder is not None
        assert orchestrator.world_state.history_recorder is not None
        logger.info("✓ HistoryRecorder correctly initialized and connected")
        
        # Test 2: Initialize the database
        logger.info("Test 2: Initializing database...")
        await orchestrator.history_recorder.initialize()
        logger.info("✓ Database initialized successfully")
        
        # Test 3: Test memory persistence
        logger.info("Test 3: Testing memory persistence...")
        
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
        logger.info("✓ Memory added to world state successfully")
        
        # Test 4: Test state restoration
        logger.info("Test 4: Testing state restoration...")
        
        # Create a new orchestrator instance with the same database
        config2 = OrchestratorConfig(db_path=db_path)
        orchestrator2 = MainOrchestrator(config2)
        await orchestrator2.history_recorder.initialize()
        
        # Restore persistent state
        await orchestrator2.world_state.restore_persistent_state()
        
        # Check if memories were restored (they'll be loaded on-demand)
        # For now, just verify the restore method runs without error
        logger.info("✓ State restoration completed without errors")
        
        # Test 5: Test research entry persistence
        logger.info("Test 5: Testing research entry persistence...")
        
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
        logger.info("✓ Research entry stored successfully")
        
        # Load and verify research entries
        research_entries = await orchestrator.history_recorder.load_research_entries()
        assert "ai_safety" in research_entries
        assert research_entries["ai_safety"]["title"] == "AI Safety Research"
        logger.info("✓ Research entry loaded successfully")
        
        # Test 6: Test state change recording
        logger.info("Test 6: Testing state change recording...")
        
        await orchestrator.history_recorder.record_user_input(
            "matrix:test_room",
            {"content": "Hello, how are you?", "sender": "@testuser:example.com"}
        )
        
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
        logger.info("✓ State changes recorded successfully")
        
        logger.info("All tests completed successfully! 🎉")
        
        # Cleanup
        try:
            Path(db_path).unlink()
            logger.info("Test database cleaned up")
        except:
            pass
            
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        # Cleanup on error
        try:
            Path(db_path).unlink()
        except:
            pass
        raise


async def test_memory_search_and_persistence():
    """Test memory search functionality with persistence."""
    
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
        db_path = temp_db.name
    
    try:
        logger.info("Testing memory search and persistence...")
        
        config = OrchestratorConfig(db_path=db_path)
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
        
        logger.info("✓ Memory search functionality working correctly")
        
        # Test persistence across sessions
        config2 = OrchestratorConfig(db_path=db_path)
        orchestrator2 = MainOrchestrator(config2)
        await orchestrator2.history_recorder.initialize()
        
        # Load memories directly from persistence
        persisted_memories = await orchestrator2.history_recorder.load_user_memories(user_id)
        assert len(persisted_memories) == 3
        logger.info("✓ Memories persisted correctly across sessions")
        
        # Cleanup
        Path(db_path).unlink()
        
    except Exception as e:
        logger.error(f"Memory search test failed: {e}", exc_info=True)
        try:
            Path(db_path).unlink()
        except:
            pass
        raise


async def main():
    """Run all persistent memory tests."""
    try:
        await test_persistent_memory_integration()
        await test_memory_search_and_persistence()
        logger.info("🎉 All persistent memory integration tests passed!")
    except Exception as e:
        logger.error(f"Tests failed: {e}")
        exit(1)


if __name__ == "__main__":
    asyncio.run(main())
