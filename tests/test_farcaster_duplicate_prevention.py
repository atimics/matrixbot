#!/usr/bin/env python3
"""
Tests for Farcaster duplicate reply prevention and enhanced world state management.

This test suite validates the comprehensive duplicate prevention system including:
- Self-reply detection
- Thread-aware duplicate checking
- Atomic state updates
- Persistence functionality
- Race condition handling
"""

import asyncio
import pytest
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from chatbot.core.world_state.manager import WorldStateManager
from chatbot.core.world_state.structures import WorldStateData, FarcasterReplyState
from chatbot.core.world_state.persistence import WorldStatePersistence, ReplyMutex


class TestFarcasterReplyState:
    """Test the enhanced FarcasterReplyState functionality."""
    
    def test_has_replied_to_cast_basic(self):
        """Test basic cast reply tracking."""
        state = FarcasterReplyState()
        
        # Initially no replies
        assert not state.has_replied_to_cast("cast123")
        
        # Add a pending reply
        assert state.add_pending_reply("cast123")
        assert state.has_replied_to_cast("cast123")
        assert state.has_pending_reply("cast123")
        
        # Cannot add duplicate pending
        assert not state.add_pending_reply("cast123")
        
        # Confirm the reply
        state.confirm_reply("cast123", "thread456", "bot_fid")
        assert state.has_replied_to_cast("cast123")
        assert not state.has_pending_reply("cast123")
        
        # Cannot add pending after confirmed
        assert not state.add_pending_reply("cast123")
    
    def test_thread_participation_tracking(self):
        """Test thread participation and last reply tracking."""
        state = FarcasterReplyState()
        
        # Add replies to a thread
        state.confirm_reply("cast1", "thread1", "user1")
        state.confirm_reply("cast2", "thread1", "bot_fid")
        state.confirm_reply("cast3", "thread1", "user2")
        
        # Check thread participation
        assert "thread1" in state.thread_participation
        assert state.thread_participation["thread1"] == ["user1", "bot_fid", "user2"]
        
        # Check last reply tracking
        assert state.last_reply_in_thread["thread1"] == "user2"
        assert not state.was_last_to_reply_in_thread("thread1", "bot_fid")
        
        # Bot replies again
        state.confirm_reply("cast4", "thread1", "bot_fid")
        assert state.was_last_to_reply_in_thread("thread1", "bot_fid")
    
    def test_bot_cast_tracking(self):
        """Test bot's own cast tracking."""
        state = FarcasterReplyState()
        
        # Initially not a bot cast
        assert not state.is_bot_cast("cast123")
        
        # Add as bot cast
        state.add_bot_cast("cast123")
        assert state.is_bot_cast("cast123")
        
        # Cannot reply to own cast
        assert not state.add_pending_reply("cast123")
    
    def test_cleanup_old_entries(self):
        """Test cleanup of old state entries."""
        state = FarcasterReplyState()
        
        # Add many entries
        for i in range(12000):
            state.replied_to_casts.add(f"cast{i}")
        
        for i in range(6000):
            state.bot_own_casts.add(f"botcast{i}")
        
        # Trigger cleanup
        state.cleanup_old_entries()
        
        # Should be reduced in size
        assert len(state.replied_to_casts) <= 8000
        assert len(state.bot_own_casts) <= 4000


class TestWorldStatePersistence:
    """Test world state persistence functionality."""
    
    @pytest.fixture
    def temp_state_file(self):
        """Create a temporary state file for testing."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            temp_path = f.name
        yield temp_path
        # Cleanup
        Path(temp_path).unlink(missing_ok=True)
    
    @pytest.fixture
    def temp_backup_dir(self):
        """Create a temporary backup directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir
    
    @pytest.fixture
    def persistence_manager(self, temp_state_file, temp_backup_dir):
        """Create a persistence manager for testing."""
        return WorldStatePersistence(
            state_file=temp_state_file,
            backup_dir=temp_backup_dir,
            max_backups=3,
            auto_save_interval=1  # 1 second for testing
        )
    
    @pytest.mark.asyncio
    async def test_save_and_load_state(self, persistence_manager):
        """Test basic save and load functionality."""
        # Create a test state
        state = WorldStateData()
        state.farcaster_reply_state.replied_to_casts.add("test_cast")
        state.farcaster_reply_state.add_bot_cast("bot_cast")
        
        # Save the state
        success = await persistence_manager.save_state(state)
        assert success
        
        # Load the state
        loaded_state = await persistence_manager.load_state()
        assert loaded_state is not None
        assert "test_cast" in loaded_state.farcaster_reply_state.replied_to_casts
        assert loaded_state.farcaster_reply_state.is_bot_cast("bot_cast")
    
    @pytest.mark.asyncio
    async def test_backup_creation(self, persistence_manager):
        """Test backup creation and rotation."""
        state = WorldStateData()
        
        # Create multiple backups
        for i in range(5):
            state.farcaster_reply_state.replied_to_casts.add(f"cast{i}")
            success = await persistence_manager.backup_state(state)
            assert success
            await asyncio.sleep(0.1)  # Ensure different timestamps
        
        # Check backup files exist and old ones are cleaned up
        backup_files = list(Path(persistence_manager.backup_dir).glob("world_state_backup_*.json"))
        assert len(backup_files) <= persistence_manager.max_backups
    
    @pytest.mark.asyncio
    async def test_corrupted_state_recovery(self, persistence_manager, temp_state_file):
        """Test recovery from corrupted state file."""
        # Create a valid backup first
        state = WorldStateData()
        state.farcaster_reply_state.replied_to_casts.add("recovery_test")
        await persistence_manager.backup_state(state)
        
        # Corrupt the main state file
        with open(temp_state_file, 'w') as f:
            f.write("invalid json content")
        
        # Should recover from backup
        loaded_state = await persistence_manager.load_state()
        assert loaded_state is not None
        assert "recovery_test" in loaded_state.farcaster_reply_state.replied_to_casts
    
    @pytest.mark.asyncio
    async def test_auto_save_functionality(self, persistence_manager):
        """Test automatic save functionality."""
        state_container = {"state": WorldStateData()}
        state_container["state"].farcaster_reply_state.replied_to_casts.add("auto_save_test")
        
        # Start auto-save
        await persistence_manager.start_auto_save(lambda: state_container["state"])
        
        # Schedule a save and wait
        persistence_manager.schedule_save()
        await asyncio.sleep(2)  # Wait for auto-save interval
        
        # Stop auto-save
        await persistence_manager.stop_auto_save()
        
        # Load and verify
        loaded_state = await persistence_manager.load_state()
        assert loaded_state is not None
        assert "auto_save_test" in loaded_state.farcaster_reply_state.replied_to_casts


class TestReplyMutex:
    """Test atomic reply operations with mutex protection."""
    
    @pytest.fixture
    def reply_mutex(self):
        """Create a ReplyMutex for testing."""
        return ReplyMutex()
    
    @pytest.mark.asyncio
    async def test_acquire_reply_lock(self, reply_mutex):
        """Test lock acquisition for specific casts."""
        cast_hash = "test_cast_123"
        
        # Acquire lock
        lock = await reply_mutex.acquire_reply_lock(cast_hash)
        assert lock is not None
        
        # Should get same lock for same cast
        lock2 = await reply_mutex.acquire_reply_lock(cast_hash)
        assert lock is lock2
    
    @pytest.mark.asyncio
    async def test_safe_reply_with_state_update(self, reply_mutex):
        """Test atomic reply operation with state updates."""
        # Mock world state manager
        world_state_manager = MagicMock()
        world_state_manager.state.farcaster_reply_state.add_pending_reply.return_value = True
        
        # Mock reply function
        async def mock_reply_func(content, reply_to_hash):
            await asyncio.sleep(0.1)  # Simulate network delay
            return {"status": "success", "cast_hash": f"reply_{reply_to_hash}"}
        
        # Execute atomic reply
        result = await reply_mutex.safe_reply_with_state_update(
            cast_hash="original_cast",
            thread_hash="thread_123",
            bot_fid="bot_456",
            world_state_manager=world_state_manager,
            reply_func=mock_reply_func,
            reply_params={"content": "test reply", "reply_to_hash": "original_cast"}
        )
        
        # Verify result
        assert result["status"] == "success"
        
        # Verify state manager calls
        world_state_manager.state.farcaster_reply_state.add_pending_reply.assert_called_once()
        world_state_manager.state.farcaster_reply_state.confirm_reply.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_duplicate_reply_prevention(self, reply_mutex):
        """Test that duplicate replies are prevented."""
        # Mock world state manager that already has the reply
        world_state_manager = MagicMock()
        world_state_manager.state.farcaster_reply_state.add_pending_reply.return_value = False
        
        async def mock_reply_func(content, reply_to_hash):
            return {"status": "success"}
        
        # Execute atomic reply
        result = await reply_mutex.safe_reply_with_state_update(
            cast_hash="duplicate_cast",
            thread_hash="thread_123",
            bot_fid="bot_456",
            world_state_manager=world_state_manager,
            reply_func=mock_reply_func,
            reply_params={"content": "duplicate reply", "reply_to_hash": "duplicate_cast"}
        )
        
        # Should be skipped
        assert result["status"] == "skipped"
        assert "Already replied or reply pending" in result["message"]
        
        # Reply function should not be called
        world_state_manager.state.farcaster_reply_state.confirm_reply.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_reply_failure_rollback(self, reply_mutex):
        """Test rollback on reply failure."""
        world_state_manager = MagicMock()
        world_state_manager.state.farcaster_reply_state.add_pending_reply.return_value = True
        
        async def failing_reply_func(content, reply_to_hash):
            raise Exception("Network error")
        
        # Execute atomic reply that fails
        with pytest.raises(Exception, match="Network error"):
            await reply_mutex.safe_reply_with_state_update(
                cast_hash="failing_cast",
                thread_hash="thread_123",
                bot_fid="bot_456",
                world_state_manager=world_state_manager,
                reply_func=failing_reply_func,
                reply_params={"content": "failing reply", "reply_to_hash": "failing_cast"}
            )
        
        # Verify rollback
        world_state_manager.state.farcaster_reply_state.remove_pending_reply.assert_called_once()
        world_state_manager.state.farcaster_reply_state.confirm_reply.assert_not_called()


class TestEnhancedWorldStateManager:
    """Test the enhanced WorldStateManager functionality."""
    
    @pytest.fixture
    def temp_state_file(self):
        """Create a temporary state file for testing."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            temp_path = f.name
        yield temp_path
        Path(temp_path).unlink(missing_ok=True)
    
    @pytest.fixture
    async def world_state_manager(self, temp_state_file):
        """Create an enhanced WorldStateManager for testing."""
        manager = WorldStateManager(enable_persistence=True, state_file=temp_state_file)
        await manager.initialize()
        yield manager
        await manager.shutdown()
    
    @pytest.mark.asyncio
    async def test_initialization_with_persistence(self, world_state_manager):
        """Test manager initialization with persistence."""
        assert world_state_manager.persistence is not None
        assert world_state_manager.reply_mutex is not None
    
    @pytest.mark.asyncio
    async def test_farcaster_reply_methods(self, world_state_manager):
        """Test enhanced Farcaster reply management methods."""
        cast_hash = "test_cast_123"
        thread_hash = "thread_456"
        bot_fid = "bot_789"
        
        # Initially no reply
        assert not world_state_manager.has_replied_to_cast(cast_hash)
        assert not world_state_manager.has_pending_reply_to_cast(cast_hash)
        assert not world_state_manager.is_bot_cast(cast_hash)
        
        # Add pending reply
        world_state_manager.state.farcaster_reply_state.add_pending_reply(cast_hash, thread_hash)
        assert world_state_manager.has_pending_reply_to_cast(cast_hash)
        assert world_state_manager.has_replied_to_cast(cast_hash)  # Should include pending
        
        # Confirm reply
        world_state_manager.state.farcaster_reply_state.confirm_reply(cast_hash, thread_hash, bot_fid)
        assert world_state_manager.has_replied_to_cast(cast_hash)
        assert not world_state_manager.has_pending_reply_to_cast(cast_hash)
        assert world_state_manager.was_last_to_reply_in_thread(thread_hash, bot_fid)
    
    @pytest.mark.asyncio
    async def test_bot_cast_tracking(self, world_state_manager):
        """Test bot cast tracking functionality."""
        bot_cast_hash = "bot_cast_123"
        
        # Add bot cast
        world_state_manager.add_bot_cast(bot_cast_hash)
        assert world_state_manager.is_bot_cast(bot_cast_hash)
    
    @pytest.mark.asyncio
    async def test_atomic_reply_to_cast_self_prevention(self, world_state_manager):
        """Test atomic reply prevents self-replies."""
        bot_cast_hash = "bot_cast_123"
        bot_fid = "bot_456"
        
        # Mark as bot cast
        world_state_manager.add_bot_cast(bot_cast_hash)
        
        async def mock_reply_func(content, reply_to_hash):
            return {"status": "success"}
        
        # Attempt to reply to own cast
        result = await world_state_manager.atomic_reply_to_cast(
            cast_hash=bot_cast_hash,
            thread_hash=None,
            bot_fid=bot_fid,
            reply_func=mock_reply_func,
            reply_params={"content": "self reply", "reply_to_hash": bot_cast_hash}
        )
        
        # Should be skipped
        assert result["status"] == "skipped"
        assert "Cannot reply to own cast" in result["message"]
    
    @pytest.mark.asyncio
    async def test_atomic_reply_to_cast_last_reply_prevention(self, world_state_manager):
        """Test atomic reply prevents consecutive bot replies."""
        cast_hash = "cast_123"
        thread_hash = "thread_456"
        bot_fid = "bot_789"
        
        # Set bot as last to reply in thread
        world_state_manager.state.farcaster_reply_state.update_thread_context(thread_hash, bot_fid)
        
        async def mock_reply_func(content, reply_to_hash):
            return {"status": "success"}
        
        # Attempt to reply when bot was last
        result = await world_state_manager.atomic_reply_to_cast(
            cast_hash=cast_hash,
            thread_hash=thread_hash,
            bot_fid=bot_fid,
            reply_func=mock_reply_func,
            reply_params={"content": "consecutive reply", "reply_to_hash": cast_hash}
        )
        
        # Should be skipped
        assert result["status"] == "skipped"
        assert "Bot was last to reply in thread" in result["message"]
    
    @pytest.mark.asyncio
    async def test_persistence_across_restart(self, temp_state_file):
        """Test state persistence across manager restarts."""
        cast_hash = "persistent_cast"
        bot_fid = "bot_123"
        
        # Create first manager and add state
        manager1 = WorldStateManager(enable_persistence=True, state_file=temp_state_file)
        await manager1.initialize()
        
        manager1.state.farcaster_reply_state.confirm_reply(cast_hash, None, bot_fid)
        manager1.add_bot_cast("bot_cast_123")
        
        await manager1.shutdown()
        
        # Create second manager and verify state is restored
        manager2 = WorldStateManager(enable_persistence=True, state_file=temp_state_file)
        await manager2.initialize()
        
        assert manager2.has_replied_to_cast(cast_hash)
        assert manager2.is_bot_cast("bot_cast_123")
        
        await manager2.shutdown()
    
    @pytest.mark.asyncio
    async def test_get_farcaster_reply_stats(self, world_state_manager):
        """Test reply statistics functionality."""
        # Add some test data
        state = world_state_manager.state.farcaster_reply_state
        state.replied_to_casts.add("cast1")
        state.replied_to_casts.add("cast2")
        state.pending_replies.add("cast3")
        state.bot_own_casts.add("bot_cast1")
        state.replied_to_threads["thread1"] = {"cast1"}
        state.thread_participation["thread1"] = ["user1", "bot_fid"]
        
        # Get stats
        stats = world_state_manager.get_farcaster_reply_stats()
        
        assert stats["total_replied_casts"] == 2
        assert stats["pending_replies"] == 1
        assert stats["tracked_bot_casts"] == 1
        assert stats["total_replied_threads"] == 1
        assert stats["active_threads"] == 1


class TestRaceConditions:
    """Test race condition handling in concurrent scenarios."""
    
    @pytest.fixture
    async def world_state_manager(self):
        """Create a manager for race condition testing."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            temp_path = f.name
        
        manager = WorldStateManager(enable_persistence=True, state_file=temp_path)
        await manager.initialize()
        yield manager
        await manager.shutdown()
        Path(temp_path).unlink(missing_ok=True)
    
    @pytest.mark.asyncio
    async def test_concurrent_reply_attempts(self, world_state_manager):
        """Test that concurrent reply attempts to the same cast are handled correctly."""
        cast_hash = "concurrent_cast"
        thread_hash = "concurrent_thread"
        bot_fid = "bot_123"
        
        reply_count = 0
        
        async def mock_reply_func(content, reply_to_hash):
            nonlocal reply_count
            await asyncio.sleep(0.1)  # Simulate network delay
            reply_count += 1
            return {"status": "success", "cast_hash": f"reply_{reply_count}"}
        
        # Start multiple concurrent reply attempts
        tasks = []
        for i in range(5):
            task = asyncio.create_task(
                world_state_manager.atomic_reply_to_cast(
                    cast_hash=cast_hash,
                    thread_hash=thread_hash,
                    bot_fid=bot_fid,
                    reply_func=mock_reply_func,
                    reply_params={"content": f"reply {i}", "reply_to_hash": cast_hash}
                )
            )
            tasks.append(task)
        
        # Wait for all tasks to complete
        results = await asyncio.gather(*tasks)
        
        # Only one should succeed, others should be skipped
        success_count = sum(1 for r in results if r["status"] == "success")
        skip_count = sum(1 for r in results if r["status"] == "skipped")
        
        assert success_count == 1
        assert skip_count == 4
        assert reply_count == 1  # Reply function should only be called once
    
    @pytest.mark.asyncio
    async def test_state_consistency_under_load(self, world_state_manager):
        """Test state consistency under high load scenarios."""
        # Simulate many concurrent operations
        tasks = []
        
        for i in range(100):
            cast_hash = f"load_test_cast_{i}"
            
            # Some operations add pending replies
            if i % 3 == 0:
                task = asyncio.create_task(
                    asyncio.to_thread(
                        world_state_manager.state.farcaster_reply_state.add_pending_reply,
                        cast_hash
                    )
                )
                tasks.append(task)
            
            # Some operations confirm replies
            elif i % 3 == 1:
                task = asyncio.create_task(
                    asyncio.to_thread(
                        world_state_manager.state.farcaster_reply_state.confirm_reply,
                        cast_hash, None, "bot_fid"
                    )
                )
                tasks.append(task)
            
            # Some operations add bot casts
            else:
                task = asyncio.create_task(
                    asyncio.to_thread(world_state_manager.add_bot_cast, cast_hash)
                )
                tasks.append(task)
        
        # Wait for all operations to complete
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Verify state is still consistent
        stats = world_state_manager.get_farcaster_reply_stats()
        assert isinstance(stats["total_replied_casts"], int)
        assert isinstance(stats["pending_replies"], int)
        assert isinstance(stats["tracked_bot_casts"], int)


if __name__ == "__main__":
    # Run tests manually if needed
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
