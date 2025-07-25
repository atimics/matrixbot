#!/usr/bin/env python3
"""
Tests for world state persistence functionality.

This test suite validates:
- State serialization and deserialization
- Backup creation and rotation
- Recovery from corrupted files
- Auto-save functionality
- Performance under load
"""

import asyncio
import json
import pytest
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from chatbot.core.world_state.manager import WorldStateManager
from chatbot.core.world_state.structures import WorldStateData, FarcasterReplyState, Channel, Message
from chatbot.core.world_state.persistence import WorldStatePersistence


class TestWorldStateSerialization:
    """Test serialization and deserialization of world state."""
    
    def test_farcaster_reply_state_serialization(self):
        """Test FarcasterReplyState serialization."""
        state = FarcasterReplyState()
        state.replied_to_casts.add("cast1")
        state.replied_to_casts.add("cast2")
        state.pending_replies.add("cast3")
        state.bot_own_casts.add("bot_cast1")
        state.replied_to_threads["thread1"] = {"cast1", "cast2"}
        state.last_reply_in_thread["thread1"] = "bot_fid"
        state.thread_participation["thread1"] = ["user1", "bot_fid"]
        
        # Create persistence manager for testing
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            temp_path = f.name
        
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                persistence = WorldStatePersistence(
                    state_file=temp_path,
                    backup_dir=temp_dir
                )
                
                # Test custom type serialization
                serialized = persistence._serialize_custom_types({
                    "test_set": state.replied_to_casts,
                    "nested": {
                        "another_set": state.pending_replies,
                        "regular_data": "string"
                    }
                })
                
                # Verify sets are converted to special format
                assert serialized["test_set"]["__type__"] == "set"
                assert "cast1" in serialized["test_set"]["data"]
                assert "cast2" in serialized["test_set"]["data"]
                
                # Test deserialization
                deserialized = persistence._deserialize_custom_types(serialized)
                assert isinstance(deserialized["test_set"], set)
                assert "cast1" in deserialized["test_set"]
                assert isinstance(deserialized["nested"]["another_set"], set)
                assert "cast3" in deserialized["nested"]["another_set"]
                
        finally:
            Path(temp_path).unlink(missing_ok=True)
    
    def test_world_state_data_serialization(self):
        """Test full WorldStateData serialization."""
        state = WorldStateData()
        
        # Add some test data
        state.farcaster_reply_state.replied_to_casts.add("test_cast")
        state.farcaster_reply_state.add_bot_cast("bot_cast")
        
        # Add a channel
        channel = Channel(
            id="test_channel",
            name="Test Channel",
            type="farcaster",
            status="active"
        )
        state.channels["test_channel"] = channel
        
        # Add a message
        message = Message(
            id="msg1",
            channel_type="farcaster",
            sender="test_user",
            content="test message",
            timestamp=time.time()
        )
        channel.recent_messages.append(message)
        
        # Test serialization
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            temp_path = f.name
        
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                persistence = WorldStatePersistence(
                    state_file=temp_path,
                    backup_dir=temp_dir
                )
                
                # Serialize
                serialized = persistence._serialize_state(state)
                
                # Verify structure
                assert "farcaster_reply_state" in serialized
                assert "channels" in serialized
                
                # Verify FarcasterReplyState is properly serialized
                farcaster_data = serialized["farcaster_reply_state"]
                assert "replied_to_casts" in farcaster_data
                
        finally:
            Path(temp_path).unlink(missing_ok=True)


class TestPersistenceOperations:
    """Test persistence save/load operations."""
    
    @pytest.fixture
    def temp_files(self):
        """Create temporary files for testing."""
        state_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json')
        state_file.close()
        
        backup_dir = tempfile.TemporaryDirectory()
        
        yield state_file.name, backup_dir.name
        
        # Cleanup
        Path(state_file.name).unlink(missing_ok=True)
        backup_dir.cleanup()
    
    @pytest.fixture
    def persistence_manager(self, temp_files):
        """Create a persistence manager for testing."""
        state_file, backup_dir = temp_files
        return WorldStatePersistence(
            state_file=state_file,
            backup_dir=backup_dir,
            max_backups=3,
            auto_save_interval=1
        )
    
    async def test_basic_save_load_cycle(self, persistence_manager):
        """Test basic save and load operations."""
        # Create test state
        original_state = WorldStateData()
        original_state.farcaster_reply_state.replied_to_casts.add("test_cast_123")
        original_state.farcaster_reply_state.add_bot_cast("bot_cast_456")
        original_state.farcaster_reply_state.last_reply_in_thread["thread1"] = "bot_fid"
        
        # Save state
        success = await persistence_manager.save_state(original_state)
        assert success
        
        # Verify file exists
        assert Path(persistence_manager.state_file).exists()
        
        # Load state
        loaded_state = await persistence_manager.load_state()
        assert loaded_state is not None
        
        # Verify data integrity
        assert "test_cast_123" in loaded_state.farcaster_reply_state.replied_to_casts
        assert loaded_state.farcaster_reply_state.is_bot_cast("bot_cast_456")
        assert loaded_state.farcaster_reply_state.last_reply_in_thread["thread1"] == "bot_fid"
    
    async def test_save_with_metadata(self, persistence_manager):
        """Test that saves include proper metadata."""
        state = WorldStateData()
        
        # Save state
        await persistence_manager.save_state(state)
        
        # Read raw file and check metadata
        with open(persistence_manager.state_file, 'r') as f:
            raw_data = json.load(f)
        
        assert "_metadata" in raw_data
        metadata = raw_data["_metadata"]
        assert "version" in metadata
        assert "timestamp" in metadata
        assert "saved_at" in metadata
        assert "schema_version" in metadata
    
    async def test_atomic_save_operation(self, persistence_manager):
        """Test that saves are atomic (no partial writes)."""
        state = WorldStateData()
        
        # Mock file operations to simulate failure during write
        original_move = persistence_manager.temp_file.replace
        
        write_count = 0
        def mock_replace(target):
            nonlocal write_count
            write_count += 1
            if write_count == 1:
                raise OSError("Simulated write failure")
            return original_move(target)
        
        with patch.object(persistence_manager.temp_file, 'replace', mock_replace):
            # First save should fail
            success = await persistence_manager.save_state(state)
            assert not success
            
            # File should not exist (atomic operation failed)
            assert not Path(persistence_manager.state_file).exists()
        
        # Second save should succeed
        success = await persistence_manager.save_state(state)
        assert success
        assert Path(persistence_manager.state_file).exists()
    
    async def test_load_nonexistent_file(self, persistence_manager):
        """Test loading when no state file exists."""
        result = await persistence_manager.load_state()
        assert result is None
    
    async def test_load_corrupted_file_without_backup(self, persistence_manager):
        """Test loading corrupted file when no backup exists."""
        # Create corrupted file
        with open(persistence_manager.state_file, 'w') as f:
            f.write("invalid json content")
        
        result = await persistence_manager.load_state()
        assert result is None


class TestBackupManagement:
    """Test backup creation and management."""
    
    @pytest.fixture
    def temp_files(self):
        """Create temporary files for testing."""
        state_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json')
        state_file.close()
        
        backup_dir = tempfile.TemporaryDirectory()
        
        yield state_file.name, backup_dir.name
        
        # Cleanup
        Path(state_file.name).unlink(missing_ok=True)
        backup_dir.cleanup()
    
    async def test_backup_creation(self, temp_files):
        """Test backup file creation."""
        state_file, backup_dir = temp_files
        persistence = WorldStatePersistence(
            state_file=state_file,
            backup_dir=backup_dir,
            max_backups=5
        )
        
        state = WorldStateData()
        state.farcaster_reply_state.replied_to_casts.add("backup_test")
        
        # Create backup
        success = await persistence.backup_state(state)
        assert success
        
        # Verify backup file exists
        backup_files = list(Path(backup_dir).glob("world_state_backup_*.json"))
        assert len(backup_files) == 1
        
        # Verify backup content
        with open(backup_files[0], 'r') as f:
            backup_data = json.load(f)
        
        assert "_backup_metadata" in backup_data
        assert "farcaster_reply_state" in backup_data
    
    async def test_backup_rotation(self, temp_files):
        """Test that old backups are removed when limit is exceeded."""
        state_file, backup_dir = temp_files
        persistence = WorldStatePersistence(
            state_file=state_file,
            backup_dir=backup_dir,
            max_backups=3
        )
        
        state = WorldStateData()
        
        # Create 5 backups
        for i in range(5):
            state.farcaster_reply_state.replied_to_casts.add(f"backup_{i}")
            await persistence.backup_state(state)
            await asyncio.sleep(0.01)  # Ensure different timestamps
        
        # Should only have 3 backups (max_backups)
        backup_files = list(Path(backup_dir).glob("world_state_backup_*.json"))
        assert len(backup_files) <= 3
    
    async def test_backup_recovery(self, temp_files):
        """Test recovery from backup files."""
        state_file, backup_dir = temp_files
        persistence = WorldStatePersistence(
            state_file=state_file,
            backup_dir=backup_dir
        )
        
        # Create a backup
        state = WorldStateData()
        state.farcaster_reply_state.replied_to_casts.add("recovery_test")
        await persistence.backup_state(state)
        
        # Corrupt main state file
        with open(state_file, 'w') as f:
            f.write("corrupted content")
        
        # Should recover from backup
        recovered_state = await persistence.load_state()
        assert recovered_state is not None
        assert "recovery_test" in recovered_state.farcaster_reply_state.replied_to_casts
    
    async def test_multiple_corrupted_backups(self, temp_files):
        """Test recovery when some backup files are corrupted."""
        state_file, backup_dir = temp_files
        persistence = WorldStatePersistence(
            state_file=state_file,
            backup_dir=backup_dir
        )
        
        # Create good backup
        state = WorldStateData()
        state.farcaster_reply_state.replied_to_casts.add("good_backup")
        await persistence.backup_state(state)
        
        # Create corrupted backups (with newer timestamps)
        await asyncio.sleep(0.01)
        backup_path_1 = Path(backup_dir) / "world_state_backup_20240101_120001.json"
        with open(backup_path_1, 'w') as f:
            f.write("corrupted backup 1")
        
        await asyncio.sleep(0.01)
        backup_path_2 = Path(backup_dir) / "world_state_backup_20240101_120002.json"
        with open(backup_path_2, 'w') as f:
            f.write("corrupted backup 2")
        
        # Corrupt main state file
        with open(state_file, 'w') as f:
            f.write("corrupted main file")
        
        # Should skip corrupted backups and recover from good one
        recovered_state = await persistence.load_state()
        assert recovered_state is not None
        assert "good_backup" in recovered_state.farcaster_reply_state.replied_to_casts


class TestAutoSave:
    """Test automatic save functionality."""
    
    @pytest.fixture
    def temp_files(self):
        """Create temporary files for testing."""
        state_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json')
        state_file.close()
        
        backup_dir = tempfile.TemporaryDirectory()
        
        yield state_file.name, backup_dir.name
        
        # Cleanup
        Path(state_file.name).unlink(missing_ok=True)
        backup_dir.cleanup()
    
    async def test_auto_save_basic(self, temp_files):
        """Test basic auto-save functionality."""
        state_file, backup_dir = temp_files
        persistence = WorldStatePersistence(
            state_file=state_file,
            backup_dir=backup_dir,
            auto_save_interval=0.1  # 100ms for testing
        )
        
        state_container = {"state": WorldStateData()}
        state_container["state"].farcaster_reply_state.replied_to_casts.add("auto_save_test")
        
        # Start auto-save
        await persistence.start_auto_save(lambda: state_container["state"])
        
        # Schedule save and wait
        persistence.schedule_save()
        await asyncio.sleep(0.2)  # Wait for auto-save interval
        
        # Stop auto-save
        await persistence.stop_auto_save()
        
        # Verify state was saved
        assert Path(state_file).exists()
        loaded_state = await persistence.load_state()
        assert loaded_state is not None
        assert "auto_save_test" in loaded_state.farcaster_reply_state.replied_to_casts
    
    async def test_auto_save_only_when_pending(self, temp_files):
        """Test that auto-save only saves when changes are pending."""
        state_file, backup_dir = temp_files
        persistence = WorldStatePersistence(
            state_file=state_file,
            backup_dir=backup_dir,
            auto_save_interval=0.1
        )
        
        state = WorldStateData()
        save_count = 0
        
        async def counting_get_state():
            nonlocal save_count
            save_count += 1
            return state
        
        # Start auto-save
        await persistence.start_auto_save(counting_get_state)
        
        # Wait without scheduling save
        await asyncio.sleep(0.2)
        
        # Should not have called get_state (no pending save)
        assert save_count == 0
        
        # Schedule save
        persistence.schedule_save()
        await asyncio.sleep(0.2)
        
        # Now should have saved
        assert save_count > 0
        
        await persistence.stop_auto_save()
    
    async def test_auto_save_error_handling(self, temp_files):
        """Test auto-save error handling."""
        state_file, backup_dir = temp_files
        persistence = WorldStatePersistence(
            state_file=state_file,
            backup_dir=backup_dir,
            auto_save_interval=0.1
        )
        
        def failing_get_state():
            raise Exception("State access error")
        
        # Start auto-save with failing state getter
        await persistence.start_auto_save(failing_get_state)
        
        # Schedule save and wait
        persistence.schedule_save()
        await asyncio.sleep(0.2)
        
        # Auto-save should handle error gracefully and continue
        await persistence.stop_auto_save()
        
        # No file should be created due to errors
        assert not Path(state_file).exists()


class TestIntegrationWithWorldStateManager:
    """Test persistence integration with WorldStateManager."""
    
    @pytest.fixture
    def temp_state_file(self):
        """Create temporary state file."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            temp_path = f.name
        yield temp_path
        Path(temp_path).unlink(missing_ok=True)
    
    async def test_manager_persistence_lifecycle(self, temp_state_file):
        """Test complete persistence lifecycle with WorldStateManager."""
        # Create first manager instance
        manager1 = WorldStateManager(enable_persistence=True, state_file=temp_state_file)
        await manager1.initialize()
        
        # Add some state
        manager1.state.farcaster_reply_state.replied_to_casts.add("persistent_cast")
        manager1.add_bot_cast("persistent_bot_cast")
        manager1.state.farcaster_reply_state.update_thread_context("thread1", "user123")
        
        # Create backup
        backup_success = await manager1.create_backup()
        assert backup_success
        
        # Shutdown first manager (should save state)
        await manager1.shutdown()
        
        # Create second manager instance
        manager2 = WorldStateManager(enable_persistence=True, state_file=temp_state_file)
        await manager2.initialize()
        
        # Verify state was restored
        assert manager2.has_replied_to_cast("persistent_cast")
        assert manager2.is_bot_cast("persistent_bot_cast")
        assert manager2.state.farcaster_reply_state.last_reply_in_thread["thread1"] == "user123"
        
        # Clean up
        await manager2.shutdown()
    
    async def test_manager_auto_save_integration(self, temp_state_file):
        """Test auto-save integration with manager operations."""
        manager = WorldStateManager(enable_persistence=True, state_file=temp_state_file)
        await manager.initialize()
        
        # Perform operations that should trigger save scheduling
        manager.add_bot_cast("auto_save_cast")
        manager.update_thread_context("auto_thread", "user456")
        
        # Wait for auto-save
        await asyncio.sleep(1.5)  # Auto-save interval is typically 1 second
        
        # Verify state was persisted
        assert Path(temp_state_file).exists()
        
        # Load directly with persistence manager to verify
        if manager.persistence:
            loaded_state = await manager.persistence.load_state()
            assert loaded_state is not None
            assert loaded_state.farcaster_reply_state.is_bot_cast("auto_save_cast")
        
        await manager.shutdown()


class TestPerformance:
    """Test persistence performance under load."""
    
    async def test_large_state_serialization_performance(self):
        """Test serialization performance with large state."""
        state = WorldStateData()
        
        # Add large amount of data
        for i in range(10000):
            state.farcaster_reply_state.replied_to_casts.add(f"cast_{i}")
            
        for i in range(1000):
            state.farcaster_reply_state.bot_own_casts.add(f"bot_cast_{i}")
            
        for i in range(100):
            thread_id = f"thread_{i}"
            state.farcaster_reply_state.replied_to_threads[thread_id] = {f"cast_{j}" for j in range(i, i+10)}
            state.farcaster_reply_state.thread_participation[thread_id] = [f"user_{k}" for k in range(5)]
        
        # Time serialization
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            temp_path = f.name
        
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                persistence = WorldStatePersistence(
                    state_file=temp_path,
                    backup_dir=temp_dir
                )
                
                start_time = time.time()
                success = await persistence.save_state(state)
                save_time = time.time() - start_time
                
                assert success
                assert save_time < 5.0  # Should complete within 5 seconds
                
                # Test loading performance
                start_time = time.time()
                loaded_state = await persistence.load_state()
                load_time = time.time() - start_time
                
                assert loaded_state is not None
                assert load_time < 5.0  # Should complete within 5 seconds
                
                # Verify data integrity
                assert len(loaded_state.farcaster_reply_state.replied_to_casts) == 10000
                assert len(loaded_state.farcaster_reply_state.bot_own_casts) == 1000
                
        finally:
            Path(temp_path).unlink(missing_ok=True)
    
    async def test_concurrent_persistence_operations(self):
        """Test concurrent persistence operations."""
        with tempfile.TemporaryDirectory() as temp_dir:
            state_files = []
            managers = []
            
            try:
                # Create multiple managers with different state files
                for i in range(5):
                    state_file = Path(temp_dir) / f"state_{i}.json"
                    state_files.append(state_file)
                    
                    manager = WorldStateManager(enable_persistence=True, state_file=str(state_file))
                    await manager.initialize()
                    managers.append(manager)
                
                # Perform concurrent operations
                async def worker(manager, worker_id):
                    for j in range(100):
                        cast_hash = f"worker_{worker_id}_cast_{j}"
                        manager.state.farcaster_reply_state.replied_to_casts.add(cast_hash)
                        
                        if j % 10 == 0:
                            # Trigger save occasionally
                            if manager.persistence:
                                manager.persistence.schedule_save()
                        
                        await asyncio.sleep(0.001)  # Small delay
                
                # Run workers concurrently
                tasks = [worker(manager, i) for i, manager in enumerate(managers)]
                await asyncio.gather(*tasks)
                
                # Allow time for auto-saves
                await asyncio.sleep(2)
                
                # Verify all managers have their data
                for i, manager in enumerate(managers):
                    expected_casts = {f"worker_{i}_cast_{j}" for j in range(100)}
                    actual_casts = manager.state.farcaster_reply_state.replied_to_casts
                    assert expected_casts.issubset(actual_casts)
                
            finally:
                # Clean up
                for manager in managers:
                    await manager.shutdown()


if __name__ == "__main__":
    # Run tests manually if needed
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
