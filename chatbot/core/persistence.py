"""
Consolidated Data Persistence Layer

Implements the engineering report recommendation to establish SQLite as the single source
of truth, with SQLModel for type safety and Alembic for database migrations.
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, Type
from contextlib import asynccontextmanager

import aiosqlite
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, Field, create_engine, select
from pydantic import BaseModel

logger = logging.getLogger(__name__)


# SQLModel definitions for type-safe database operations
class StateChangeRecord(SQLModel, table=True):
    """SQLModel for state change records."""
    
    __tablename__ = "state_changes"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: float = Field(description="Unix timestamp of the change")
    change_type: str = Field(description="Type of change (message, action, etc.)")
    channel_id: Optional[str] = Field(default=None, description="Associated channel")
    platform: Optional[str] = Field(default=None, description="Platform (matrix, farcaster)")
    data: str = Field(description="JSON-serialized change data")
    record_metadata: Optional[str] = Field(default=None, description="Additional metadata")
    
    # Indexes for performance
    class Config:
        schema_extra = {
            "indexes": [
                {"fields": ["timestamp"]},
                {"fields": ["change_type"]},
                {"fields": ["channel_id"]},
                {"fields": ["platform"]},
            ]
        }


class MessageRecord(SQLModel, table=True):
    """SQLModel for message records."""
    
    __tablename__ = "messages"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    message_id: str = Field(unique=True, description="Unique message identifier")
    channel_id: str = Field(description="Channel/room identifier")
    platform: str = Field(description="Platform (matrix, farcaster)")
    sender: str = Field(description="Message sender identifier")
    content: str = Field(description="Message content")
    timestamp: float = Field(description="Unix timestamp")
    parent_id: Optional[str] = Field(default=None, description="Parent message for replies")
    record_metadata: Optional[str] = Field(default=None, description="Additional message metadata")
    processed: bool = Field(default=False, description="Whether message has been processed")
    
    class Config:
        schema_extra = {
            "indexes": [
                {"fields": ["channel_id", "timestamp"]},
                {"fields": ["platform", "timestamp"]},
                {"fields": ["message_id"]},
                {"fields": ["processed"]},
            ]
        }


class ActionRecord(SQLModel, table=True):
    """SQLModel for action records."""
    
    __tablename__ = "actions"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    action_id: str = Field(unique=True, description="Unique action identifier")
    action_type: str = Field(description="Type of action executed")
    timestamp: float = Field(description="Unix timestamp")
    channel_id: Optional[str] = Field(default=None, description="Associated channel")
    platform: Optional[str] = Field(default=None, description="Platform")
    parameters: str = Field(description="JSON-serialized action parameters")
    result: Optional[str] = Field(default=None, description="JSON-serialized action result")
    success: bool = Field(default=False, description="Whether action succeeded")
    duration_ms: Optional[int] = Field(default=None, description="Execution duration")
    
    class Config:
        schema_extra = {
            "indexes": [
                {"fields": ["timestamp"]},
                {"fields": ["action_type"]},
                {"fields": ["success"]},
                {"fields": ["channel_id"]},
            ]
        }


class ConfigRecord(SQLModel, table=True):
    """SQLModel for configuration storage."""
    
    __tablename__ = "config"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    key: str = Field(unique=True, description="Configuration key")
    value: str = Field(description="Configuration value")
    category: str = Field(description="Configuration category")
    encrypted: bool = Field(default=False, description="Whether value is encrypted")
    updated_at: float = Field(description="Last update timestamp")
    
    class Config:
        schema_extra = {
            "indexes": [
                {"fields": ["category"]},
                {"fields": ["updated_at"]},
            ]
        }


class MemoryRecord(SQLModel, table=True):
    """SQLModel for user memory storage."""
    
    __tablename__ = "memories"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(description="User identifier")
    platform: str = Field(description="Platform (matrix, farcaster)")
    memory_type: str = Field(description="Type of memory (fact, preference, etc.)")
    content: str = Field(description="Memory content")
    importance: float = Field(default=0.5, description="Importance score (0-1)")
    timestamp: float = Field(description="When memory was created")
    last_accessed: Optional[float] = Field(default=None, description="Last access time")
    source_context: Optional[str] = Field(default=None, description="Source context")
    
    class Config:
        schema_extra = {
            "indexes": [
                {"fields": ["user_id", "platform"]},
                {"fields": ["memory_type"]},
                {"fields": ["importance"]},
                {"fields": ["timestamp"]},
            ]
        }


class UndecryptableEventRecord(SQLModel, table=True):
    """SQLModel for undecryptable Matrix events requiring retry."""
    
    __tablename__ = "undecryptable_events"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    event_id: str = Field(description="Matrix event ID")
    room_id: str = Field(description="Matrix room ID")
    sender: str = Field(description="Event sender user ID")
    timestamp: float = Field(description="Unix timestamp when event was received")
    retry_count: int = Field(default=0, description="Number of retry attempts")
    last_retry_time: float = Field(default=0, description="Unix timestamp of last retry")
    error_type: str = Field(default="megolm_session_missing", description="Type of decryption error")
    max_retries: int = Field(default=5, description="Maximum number of retries")
    
    class Config:
        schema_extra = {
            "indexes": [
                {"fields": ["room_id"]},
                {"fields": ["retry_count"]},
                {"fields": ["last_retry_time"]},
                {"fields": ["event_id", "room_id"], "unique": True},  # Composite unique constraint
            ]
        }


class DatabaseManager:
    """Centralized database manager with migrations and type safety."""
    
    def __init__(self, database_url: Optional[str] = None):
        if database_url is None:
            # Import settings here to avoid circular imports
            from ..config import settings
            # Ensure the path is absolute and properly formatted for SQLite async
            db_path = Path(settings.chatbot_db_path).resolve()
            self.database_url = f"sqlite+aiosqlite:///{db_path}"
        else:
            # If the provided URL doesn't look like a SQLAlchemy URL, assume it's a file path.
            if not database_url.startswith("sqlite"):
                self.database_url = f"sqlite+aiosqlite:///{database_url}"
                logger.debug(f"Interpreted database path as SQLite URL: {self.database_url}")
            else:
                self.database_url = database_url
        self.engine = None
        self.session_factory = None
        self._initialized = False
    
    async def initialize(self):
        """Initialize database connection and create tables."""
        if self._initialized:
            return
        
        # Create async engine
        self.engine = create_async_engine(
            self.database_url,
            echo=False,  # Set to True for SQL debugging
            connect_args={"check_same_thread": False} if "sqlite" in self.database_url else {}
        )
        
        # Create session factory
        self.session_factory = sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
        
        # Create tables
        async with self.engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        
        self._initialized = True
        logger.info("Database initialized successfully")
    
    @asynccontextmanager
    async def get_session(self):
        """Get database session context manager."""
        if not self._initialized:
            await self.initialize()
        
        async with self.session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()
    
    async def cleanup(self):
        """Cleanup database connections."""
        if self.engine:
            await self.engine.dispose()
        self._initialized = False


class ConsolidatedHistoryRecorder:
    """Consolidated history recorder using SQLModel for type safety."""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
    
    async def record_state_change(
        self,
        change_type: str,
        data: Dict[str, Any],
        channel_id: Optional[str] = None,
        platform: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """Record a state change with full type safety."""
        
        record = StateChangeRecord(
            timestamp=time.time(),
            change_type=change_type,
            channel_id=channel_id,
            platform=platform,
            data=json.dumps(data),
            record_metadata=json.dumps(metadata) if metadata else None
        )
        
        async with self.db_manager.get_session() as session:
            session.add(record)
            await session.commit()
            await session.refresh(record)
            return record.id
    
    async def record_message(
        self,
        message_id: str,
        channel_id: str,
        platform: str,
        sender: str,
        content: str,
        timestamp: Optional[float] = None,
        parent_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """Record a message."""
        
        record = MessageRecord(
            message_id=message_id,
            channel_id=channel_id,
            platform=platform,
            sender=sender,
            content=content,
            timestamp=timestamp or time.time(),
            parent_id=parent_id,
            record_metadata=json.dumps(metadata) if metadata else None
        )
        
        async with self.db_manager.get_session() as session:
            session.add(record)
            await session.commit()
            await session.refresh(record)
            return record.id
    
    async def record_action(
        self,
        action_id: str,
        action_type: str,
        parameters: Dict[str, Any],
        result: Optional[Dict[str, Any]] = None,
        success: bool = False,
        channel_id: Optional[str] = None,
        platform: Optional[str] = None,
        duration_ms: Optional[int] = None
    ) -> int:
        """Record an action execution."""
        
        record = ActionRecord(
            action_id=action_id,
            action_type=action_type,
            timestamp=time.time(),
            channel_id=channel_id,
            platform=platform,
            parameters=json.dumps(parameters),
            result=json.dumps(result) if result else None,
            success=success,
            duration_ms=duration_ms
        )
        
        async with self.db_manager.get_session() as session:
            session.add(record)
            await session.commit()
            await session.refresh(record)
            return record.id
    
    async def store_memory(
        self,
        user_id: str,
        platform: str,
        memory_type: str,
        content: str,
        importance: float = 0.5,
        source_context: Optional[str] = None
    ) -> int:
        """Store a user memory."""
        
        record = MemoryRecord(
            user_id=user_id,
            platform=platform,
            memory_type=memory_type,
            content=content,
            importance=importance,
            timestamp=time.time(),
            source_context=source_context
        )
        
        async with self.db_manager.get_session() as session:
            session.add(record)
            await session.commit()
            await session.refresh(record)
            return record.id
    
    async def get_recent_messages(
        self,
        channel_id: str,
        platform: str,
        limit: int = 50,
        before_timestamp: Optional[float] = None
    ) -> List[MessageRecord]:
        """Get recent messages for a channel."""
        
        async with self.db_manager.get_session() as session:
            query = select(MessageRecord).where(
                MessageRecord.channel_id == channel_id,
                MessageRecord.platform == platform
            )
            
            if before_timestamp:
                query = query.where(MessageRecord.timestamp < before_timestamp)
            
            query = query.order_by(MessageRecord.timestamp.desc()).limit(limit)
            
            result = await session.execute(query)
            return result.scalars().all()
    
    async def get_recent_actions(
        self,
        limit: int = 100,
        action_type: Optional[str] = None,
        channel_id: Optional[str] = None
    ) -> List[ActionRecord]:
        """Get recent actions."""
        
        async with self.db_manager.get_session() as session:
            query = select(ActionRecord)
            
            if action_type:
                query = query.where(ActionRecord.action_type == action_type)
            
            if channel_id:
                query = query.where(ActionRecord.channel_id == channel_id)
            
            query = query.order_by(ActionRecord.timestamp.desc()).limit(limit)
            
            result = await session.execute(query)
            return result.scalars().all()
    
    async def get_user_memories(
        self,
        user_id: str,
        platform: str,
        memory_type: Optional[str] = None,
        limit: int = 10
    ) -> List[MemoryRecord]:
        """Get user memories."""
        
        async with self.db_manager.get_session() as session:
            query = select(MemoryRecord).where(
                MemoryRecord.user_id == user_id,
                MemoryRecord.platform == platform
            )
            
            if memory_type:
                query = query.where(MemoryRecord.memory_type == memory_type)
            
            query = query.order_by(MemoryRecord.importance.desc(), MemoryRecord.timestamp.desc()).limit(limit)
            
            result = await session.execute(query)
            memories = result.scalars().all()
            
            # Update last accessed timestamp
            for memory in memories:
                memory.last_accessed = time.time()
            await session.commit()
            
            return memories
    
    async def export_for_training(
        self,
        start_timestamp: Optional[float] = None,
        end_timestamp: Optional[float] = None,
        output_file: Optional[str] = None
    ) -> Dict[str, Any]:
        """Export data for training purposes."""
        
        async with self.db_manager.get_session() as session:
            # Get state changes
            state_query = select(StateChangeRecord)
            if start_timestamp:
                state_query = state_query.where(StateChangeRecord.timestamp >= start_timestamp)
            if end_timestamp:
                state_query = state_query.where(StateChangeRecord.timestamp <= end_timestamp)
            
            state_result = await session.execute(state_query)
            state_changes = state_result.scalars().all()
            
            # Get messages
            msg_query = select(MessageRecord)
            if start_timestamp:
                msg_query = msg_query.where(MessageRecord.timestamp >= start_timestamp)
            if end_timestamp:
                msg_query = msg_query.where(MessageRecord.timestamp <= end_timestamp)
            
            msg_result = await session.execute(msg_query)
            messages = msg_result.scalars().all()
            
            # Get actions
            action_query = select(ActionRecord)
            if start_timestamp:
                action_query = action_query.where(ActionRecord.timestamp >= start_timestamp)
            if end_timestamp:
                action_query = action_query.where(ActionRecord.timestamp <= end_timestamp)
            
            action_result = await session.execute(action_query)
            actions = action_result.scalars().all()
        
        # Convert to exportable format
        export_data = {
            "export_timestamp": time.time(),
            "start_timestamp": start_timestamp,
            "end_timestamp": end_timestamp,
            "state_changes": [
                {
                    "timestamp": sc.timestamp,
                    "change_type": sc.change_type,
                    "channel_id": sc.channel_id,
                    "platform": sc.platform,
                    "data": json.loads(sc.data),
                    "metadata": json.loads(sc.record_metadata) if sc.record_metadata else None
                }
                for sc in state_changes
            ],
            "messages": [
                {
                    "message_id": msg.message_id,
                    "channel_id": msg.channel_id,
                    "platform": msg.platform,
                    "sender": msg.sender,
                    "content": msg.content,
                    "timestamp": msg.timestamp,
                    "parent_id": msg.parent_id,
                    "metadata": json.loads(msg.record_metadata) if msg.record_metadata else None
                }
                for msg in messages
            ],
            "actions": [
                {
                    "action_id": action.action_id,
                    "action_type": action.action_type,
                    "timestamp": action.timestamp,
                    "channel_id": action.channel_id,
                    "platform": action.platform,
                    "parameters": json.loads(action.parameters),
                    "result": json.loads(action.result) if action.result else None,
                    "success": action.success,
                    "duration_ms": action.duration_ms
                }
                for action in actions
            ]
        }
        
        if output_file:
            Path(output_file).parent.mkdir(parents=True, exist_ok=True)
            with open(output_file, 'w') as f:
                json.dump(export_data, f, indent=2)
            logger.info(f"Training data exported to {output_file}")
        
        return export_data
    
    async def cleanup_old_records(self, days_to_keep: int = 30):
        """Clean up old records to manage database size."""
        cutoff_timestamp = time.time() - (days_to_keep * 24 * 60 * 60)
        
        async with self.db_manager.get_session() as session:
            # Delete old state changes
            state_result = await session.execute(
                select(StateChangeRecord).where(StateChangeRecord.timestamp < cutoff_timestamp)
            )
            old_states = state_result.scalars().all()
            
            # Delete old messages (keep more recent ones)
            msg_cutoff = time.time() - (7 * 24 * 60 * 60)  # Keep messages for 7 days
            msg_result = await session.execute(
                select(MessageRecord).where(MessageRecord.timestamp < msg_cutoff)
            )
            old_messages = msg_result.scalars().all()
            
            # Delete records
            for record in old_states + old_messages:
                await session.delete(record)
            
            await session.commit()
            
            cleaned_count = len(old_states) + len(old_messages)
            logger.info(f"Cleaned up {cleaned_count} old records")
            return cleaned_count


# Migration utilities
class DatabaseMigrator:
    """Handle database schema migrations."""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
    
    async def get_schema_version(self) -> int:
        """Get current schema version."""
        try:
            async with self.db_manager.get_session() as session:
                result = await session.execute(
                    "SELECT value FROM config WHERE key = 'schema_version'"
                )
                version = result.scalar()
                return int(version) if version else 0
        except:
            return 0
    
    async def set_schema_version(self, version: int):
        """Set schema version."""
        async with self.db_manager.get_session() as session:
            # Upsert schema version
            config_record = ConfigRecord(
                key="schema_version",
                value=str(version),
                category="system",
                updated_at=time.time()
            )
            await session.merge(config_record)
            await session.commit()
    
    async def migrate(self):
        """Run database migrations."""
        current_version = await self.get_schema_version()
        target_version = 1  # Current schema version
        
        if current_version < target_version:
            logger.info(f"Migrating database from version {current_version} to {target_version}")
            
            # Run migrations
            if current_version < 1:
                await self._migrate_to_v1()
            
            await self.set_schema_version(target_version)
            logger.info("Database migration completed")
    
    async def _migrate_to_v1(self):
        """Migrate to version 1 (initial schema)."""
        # Create all tables
        async with self.db_manager.engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)


# Factory function
def create_database_manager(database_url: Optional[str] = None) -> DatabaseManager:
    """Create database manager with default configuration."""
    if database_url is None:
        database_url = "sqlite+aiosqlite:///data/chatbot.db"
    
    return DatabaseManager(database_url)


# Backward compatibility adapter

