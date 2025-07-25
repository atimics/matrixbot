#!/usr/bin/env python3
"""
World State Persistence Manager

This module provides comprehensive persistence capabilities for the world state,
including save/load operations, backup management, and recovery mechanisms.
It ensures that critical bot state survives restarts and provides atomic operations
to prevent data corruption.
"""

import asyncio
import json
import logging
import os
import shutil
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Optional
from datetime import datetime, timezone

from .structures import WorldStateData, FarcasterReplyState

logger = logging.getLogger(__name__)


class WorldStatePersistence:
    """
    Manages persistence operations for WorldStateData with atomic saves and backup recovery.
    
    Features:
    - Atomic file operations to prevent corruption
    - Automatic backup rotation
    - JSON serialization with custom handling for sets and complex types
    - Recovery mechanisms for corrupted data
    - Background save operations
    """
    
    def __init__(self, 
                 state_file: str = "data/world_state.json",
                 backup_dir: str = "data/backups",
                 max_backups: int = 10,
                 auto_save_interval: float = 300.0):  # 5 minutes
        """
        Initialize persistence manager.
        
        Args:
            state_file: Primary state file path
            backup_dir: Directory for backup files
            max_backups: Maximum number of backup files to keep
            auto_save_interval: Seconds between automatic saves
        """
        self.state_file = Path(state_file)
        self.backup_dir = Path(backup_dir)
        self.temp_file = self.state_file.with_suffix('.tmp')
        self.max_backups = max_backups
        self.auto_save_interval = auto_save_interval
        
        # Ensure directories exist
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Background save task
        self._save_task: Optional[asyncio.Task] = None
        self._save_pending = False
        self._save_lock = asyncio.Lock()
        
    async def save_state(self, state: WorldStateData) -> bool:
        """
        Save world state to disk with atomic operations.
        
        Args:
            state: WorldStateData to save
            
        Returns:
            bool: True if successful, False otherwise
        """
        async with self._save_lock:
            try:
                # Convert to serializable format
                state_dict = self._serialize_state(state)
                
                # Add metadata
                state_dict['_metadata'] = {
                    'version': '1.0',
                    'timestamp': time.time(),
                    'saved_at': datetime.now(timezone.utc).isoformat(),
                    'schema_version': 1
                }
                
                # Write to temporary file first
                with open(self.temp_file, 'w', encoding='utf-8') as f:
                    json.dump(state_dict, f, indent=2, ensure_ascii=False)
                
                # Atomic move to final location
                shutil.move(str(self.temp_file), str(self.state_file))
                
                logger.debug(f"World state saved to {self.state_file}")
                return True
                
            except Exception as e:
                logger.error(f"Failed to save world state: {e}")
                # Clean up temp file if it exists
                if self.temp_file.exists():
                    self.temp_file.unlink()
                return False
    
    async def load_state(self) -> Optional[WorldStateData]:
        """
        Load world state from disk with recovery mechanisms.
        
        Returns:
            WorldStateData if successful, None if file doesn't exist or is corrupted
        """
        if not self.state_file.exists():
            logger.info("No saved state file found, starting with fresh state")
            return None
            
        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                state_dict = json.load(f)
            
            # Validate and migrate if needed
            state = self._deserialize_state(state_dict)
            logger.info(f"Loaded world state from {self.state_file}")
            return state
            
        except Exception as e:
            logger.error(f"Failed to load state from {self.state_file}: {e}")
            
            # Try to recover from backup
            recovery_state = await self._recover_from_backup()
            if recovery_state:
                logger.info("Successfully recovered state from backup")
                return recovery_state
            
            logger.warning("Could not recover state, starting fresh")
            return None
    
    async def backup_state(self, state: WorldStateData) -> bool:
        """
        Create a backup of the current state.
        
        Args:
            state: WorldStateData to backup
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_file = self.backup_dir / f"world_state_backup_{timestamp}.json"
            
            # Convert to serializable format
            state_dict = self._serialize_state(state)
            state_dict['_backup_metadata'] = {
                'created_at': datetime.now(timezone.utc).isoformat(),
                'backup_type': 'manual',
                'original_file': str(self.state_file)
            }
            
            with open(backup_file, 'w', encoding='utf-8') as f:
                json.dump(state_dict, f, indent=2, ensure_ascii=False)
            
            # Clean up old backups
            await self._cleanup_old_backups()
            
            logger.info(f"Created backup: {backup_file}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create backup: {e}")
            return False
    
    async def start_auto_save(self, get_state_func):
        """
        Start automatic saving in the background.
        
        Args:
            get_state_func: Function that returns the current WorldStateData
        """
        if self._save_task and not self._save_task.done():
            return
            
        self._save_task = asyncio.create_task(
            self._auto_save_loop(get_state_func)
        )
        logger.info(f"Started auto-save with {self.auto_save_interval}s interval")
    
    async def stop_auto_save(self):
        """Stop automatic saving."""
        if self._save_task:
            self._save_task.cancel()
            try:
                await self._save_task
            except asyncio.CancelledError:
                pass
            logger.info("Stopped auto-save")
    
    def schedule_save(self):
        """Mark that a save is needed (for batch saving)."""
        self._save_pending = True
    
    async def _auto_save_loop(self, get_state_func):
        """Background auto-save loop."""
        while True:
            try:
                await asyncio.sleep(self.auto_save_interval)
                
                if self._save_pending:
                    state = get_state_func()
                    if state:
                        success = await self.save_state(state)
                        if success:
                            self._save_pending = False
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Auto-save error: {e}")
                await asyncio.sleep(10)  # Wait before retrying
    
    async def _recover_from_backup(self) -> Optional[WorldStateData]:
        """Attempt to recover state from the most recent backup."""
        try:
            backup_files = list(self.backup_dir.glob("world_state_backup_*.json"))
            if not backup_files:
                logger.warning("No backup files found for recovery")
                return None
            
            # Sort by modification time, newest first
            backup_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
            
            for backup_file in backup_files:
                try:
                    logger.info(f"Attempting recovery from {backup_file}")
                    with open(backup_file, 'r', encoding='utf-8') as f:
                        state_dict = json.load(f)
                    
                    state = self._deserialize_state(state_dict)
                    logger.info(f"Successfully recovered from {backup_file}")
                    return state
                    
                except Exception as e:
                    logger.warning(f"Backup {backup_file} is corrupted: {e}")
                    continue
            
            logger.error("All backup files are corrupted")
            return None
            
        except Exception as e:
            logger.error(f"Recovery attempt failed: {e}")
            return None
    
    async def _cleanup_old_backups(self):
        """Remove old backup files beyond max_backups limit."""
        try:
            backup_files = list(self.backup_dir.glob("world_state_backup_*.json"))
            if len(backup_files) <= self.max_backups:
                return
                
            # Sort by modification time, oldest first
            backup_files.sort(key=lambda f: f.stat().st_mtime)
            
            # Remove oldest files
            for backup_file in backup_files[:-self.max_backups]:
                backup_file.unlink()
                logger.debug(f"Removed old backup: {backup_file}")
                
        except Exception as e:
            logger.error(f"Failed to cleanup old backups: {e}")
    
    def _serialize_state(self, state: WorldStateData) -> Dict[str, Any]:
        """
        Convert WorldStateData to JSON-serializable dictionary.
        
        Handles sets, custom objects, and complex nested structures.
        """
        try:
            # Convert to dict by accessing instance attributes
            state_dict = {}
            for attr_name in dir(state):
                if not attr_name.startswith('_') and not callable(getattr(state, attr_name)):
                    try:
                        attr_value = getattr(state, attr_name)
                        # Handle special types
                        if hasattr(attr_value, '__dataclass_fields__'):
                            # It's a dataclass, use asdict
                            state_dict[attr_name] = asdict(attr_value)
                        elif hasattr(attr_value, '__dict__'):
                            # For complex objects with __dict__, get attributes
                            obj_dict = {}
                            for sub_attr in dir(attr_value):
                                if not sub_attr.startswith('_') and not callable(getattr(attr_value, sub_attr)):
                                    obj_dict[sub_attr] = getattr(attr_value, sub_attr)
                            state_dict[attr_name] = obj_dict
                        else:
                            state_dict[attr_name] = attr_value
                    except Exception as e:
                        logger.debug(f"Skipping attribute {attr_name}: {e}")
                        continue
            
            # Handle special serialization for sets and complex types
            state_dict = self._serialize_custom_types(state_dict)
            
            return state_dict
            
        except Exception as e:
            logger.error(f"Serialization error: {e}")
            raise
    
    def _deserialize_state(self, state_dict: Dict[str, Any]) -> WorldStateData:
        """
        Convert dictionary back to WorldStateData.
        
        Handles migration of old formats and restoration of complex types.
        """
        try:
            # Remove metadata if present
            state_dict.pop('_metadata', None)
            state_dict.pop('_backup_metadata', None)
            
            # Handle custom type restoration
            state_dict = self._deserialize_custom_types(state_dict)
            
            # Create WorldStateData instance
            # Since WorldStateData uses specific types, we need to construct it properly
            return self._construct_world_state(state_dict)
            
        except Exception as e:
            logger.error(f"Deserialization error: {e}")
            raise
    
    def _serialize_custom_types(self, obj: Any) -> Any:
        """Recursively handle custom type serialization."""
        if isinstance(obj, set):
            return {"__type__": "set", "data": list(obj)}
        elif isinstance(obj, dict):
            return {k: self._serialize_custom_types(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._serialize_custom_types(item) for item in obj]
        else:
            return obj
    
    def _deserialize_custom_types(self, obj: Any) -> Any:
        """Recursively handle custom type deserialization."""
        if isinstance(obj, dict):
            if obj.get("__type__") == "set":
                return set(obj["data"])
            else:
                return {k: self._deserialize_custom_types(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._deserialize_custom_types(item) for item in obj]
        else:
            return obj
    
    def _construct_world_state(self, state_dict: Dict[str, Any]) -> WorldStateData:
        """
        Construct WorldStateData from dictionary with proper type conversion.
        """
        # Create new instance
        state = WorldStateData()
        
        # Update with loaded data
        for key, value in state_dict.items():
            if hasattr(state, key):
                # Special handling for FarcasterReplyState
                if key == 'farcaster_reply_state' and isinstance(value, dict):
                    farcaster_state = FarcasterReplyState()
                    for fk, fv in value.items():
                        if hasattr(farcaster_state, fk):
                            setattr(farcaster_state, fk, fv)
                    setattr(state, key, farcaster_state)
                else:
                    setattr(state, key, value)
        
        return state


class ReplyMutex:
    """
    Provides atomic operations for reply state management to prevent race conditions.
    """
    
    def __init__(self):
        self._locks: Dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()
    
    async def acquire_reply_lock(self, cast_hash: str):
        """
        Acquire a lock for a specific cast to prevent concurrent replies.
        
        Returns async context manager.
        """
        async with self._global_lock:
            if cast_hash not in self._locks:
                self._locks[cast_hash] = asyncio.Lock()
        
        return self._locks[cast_hash]
    
    async def safe_reply_with_state_update(self, 
                                         cast_hash: str,
                                         thread_hash: Optional[str],
                                         bot_fid: str,
                                         world_state_manager,
                                         reply_func,
                                         reply_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform a reply with atomic state updates.
        
        Args:
            cast_hash: Cast being replied to
            thread_hash: Thread the cast belongs to
            bot_fid: Bot's Farcaster ID
            world_state_manager: WorldStateManager instance
            reply_func: Async function to send the reply
            reply_params: Parameters for reply_func
            
        Returns:
            Reply result dictionary
        """
        lock = await self.acquire_reply_lock(cast_hash)
        
        async with lock:
            try:
                # Check if we can reply (atomic check)
                if not world_state_manager.state.farcaster_reply_state.add_pending_reply(
                    cast_hash, thread_hash
                ):
                    return {
                        "status": "skipped",
                        "message": "Already replied or reply pending",
                        "cast_hash": cast_hash,
                        "timestamp": time.time()
                    }
                
                # Send the reply
                result = await reply_func(**reply_params)
                
                if result.get("status") == "success":
                    # Confirm successful reply
                    world_state_manager.state.farcaster_reply_state.confirm_reply(
                        cast_hash, thread_hash, bot_fid
                    )
                    
                    # Schedule save
                    if hasattr(world_state_manager, 'persistence'):
                        world_state_manager.persistence.schedule_save()
                else:
                    # Remove pending on failure
                    world_state_manager.state.farcaster_reply_state.remove_pending_reply(cast_hash)
                
                return result
                
            except Exception as e:
                # Remove pending on exception
                world_state_manager.state.farcaster_reply_state.remove_pending_reply(cast_hash)
                logger.error(f"Reply operation failed for {cast_hash}: {e}")
                raise
    
    async def cleanup_old_locks(self, max_age_seconds: int = 3600):
        """Clean up old locks to prevent memory leaks."""
        # In a production system, you'd track lock creation times
        # For now, we'll just limit the total number
        async with self._global_lock:
            if len(self._locks) > 1000:
                # Keep only recent locks (this is a simplified approach)
                keys_to_remove = list(self._locks.keys())[:-500]
                for key in keys_to_remove:
                    if not self._locks[key].locked():
                        del self._locks[key]
