"""
Database Persistence Layer

This module provides a centralized database interface that serves as the single 
source of truth for all database operations in the system. It uses psycopg
(PostgreSQL) with connection pooling for high-performance concurrent access.
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional, Callable
from pathlib import Path
from dataclasses import dataclass

import psycopg
from psycopg_pool import AsyncConnectionPool
from chatbot.config import settings

logger = logging.getLogger(__name__)


# Data Models (using dataclasses for type safety)
@dataclass
class IntegrationRecord:
    """Data model for integration configurations."""
    id: str
    user_id: Optional[str]
    integration_type: str
    display_name: str
    is_active: bool
    config: Dict[str, Any]
    created_at: float
    updated_at: float


@dataclass
class CredentialRecord:
    """Data model for encrypted credentials."""
    id: str
    integration_id: str
    credential_key: str
    credential_value_encrypted: bytes
    created_at: float


@dataclass
class StateChangeRecord:
    """Data model for state change history."""
    id: Optional[int]
    timestamp: float
    change_type: str
    source: str
    channel_id: Optional[str]
    observations: Optional[str]
    potential_actions: Optional[str]  # JSON string
    selected_actions: Optional[str]   # JSON string
    reasoning: Optional[str]
    raw_content: str  # JSON string
    created_at: Optional[str] = None


@dataclass
class UndecryptableEventRecord:
    """Data model for undecryptable Matrix events."""
    id: Optional[int]
    event_id: str
    room_id: str
    sender: str
    timestamp: float
    retry_count: int
    last_retry: Optional[float]
    event_data: Dict[str, Any]


class DatabaseManager:
    """
    Centralized database manager providing high-performance PostgreSQL operations.
    
    This class serves as the single interface for all database interactions,
    using psycopg with connection pooling for concurrent access.
    """
    
    def __init__(self):
        self.dsn = settings.postgres.dsn
        self.pool: Optional[AsyncConnectionPool] = None
        
    async def initialize(self) -> None:
        """Initialize the async connection pool and create tables."""
        try:
            self.pool = AsyncConnectionPool(
                conninfo=self.dsn,
                min_size=settings.postgres.min_pool_size,
                max_size=settings.postgres.max_pool_size
            )
            await self.pool.open()
            logger.info("DatabaseManager: PostgreSQL connection pool established.")
            await self._create_tables()
            logger.info(f"DatabaseManager initialized with PostgreSQL database: {settings.postgres.dbname}")
            
        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL connection pool: {e}")
            raise
    
    async def close(self) -> None:
        """Close the connection pool."""
        if self.pool:
            await self.pool.close()
            self.pool = None
            logger.info("DatabaseManager: PostgreSQL connection pool closed.")
    
    async def _execute_operation(self, operation_func: Callable):
        """Execute a database operation with a connection from the pool."""
        if not self.pool:
            raise RuntimeError("Database pool is not initialized.")
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                return await operation_func(cur)
    
    async def _create_tables(self) -> None:
        """Create all database tables using PostgreSQL syntax."""
        async def create_tables_operation(cur):
            # Integrations table
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS integrations (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    integration_type TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    is_active BOOLEAN DEFAULT TRUE,
                    config JSONB NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Credentials table
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS credentials (
                    id TEXT PRIMARY KEY,
                    integration_id TEXT NOT NULL,
                    credential_key TEXT NOT NULL,
                    credential_value_encrypted BYTEA NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (integration_id) REFERENCES integrations (id) ON DELETE CASCADE,
                    UNIQUE(integration_id, credential_key)
                )
            """)
            
            # State changes table
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS state_changes (
                    id SERIAL PRIMARY KEY,
                    timestamp REAL NOT NULL,
                    change_type TEXT NOT NULL,
                    source TEXT NOT NULL,
                    channel_id TEXT,
                    observations TEXT,
                    potential_actions JSONB,
                    selected_actions JSONB,
                    reasoning TEXT,
                    raw_content JSONB NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Undecryptable events table
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS undecryptable_events (
                    id SERIAL PRIMARY KEY,
                    event_id TEXT UNIQUE NOT NULL,
                    room_id TEXT NOT NULL,
                    sender TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    retry_count INTEGER DEFAULT 0,
                    last_retry REAL,
                    event_data JSONB NOT NULL
                )
            """)
            
            # Replied-to casts table for duplicate prevention
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS replied_to_casts (
                    original_cast_hash TEXT PRIMARY KEY NOT NULL,
                    reply_cast_hash TEXT NOT NULL,
                    replied_at REAL NOT NULL
                )
            """)
            
            # Pending feedback actions table for enhanced sentiment analysis
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS pending_feedback_actions (
                    reply_event_id TEXT PRIMARY KEY NOT NULL,
                    original_event_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    feedback_threshold_time REAL NOT NULL DEFAULT 3600
                )
            """)
            
            # Key-value store table for unified configuration
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS key_value_store (
                    key TEXT PRIMARY KEY,
                    value JSONB NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create trigger to update timestamp on key_value_store updates
            await cur.execute("""
                CREATE OR REPLACE FUNCTION update_modified_column()
                RETURNS TRIGGER AS $$
                BEGIN
                    NEW.updated_at = CURRENT_TIMESTAMP;
                    RETURN NEW;
                END;
                $$ language 'plpgsql'
            """)
            
            await cur.execute("""
                DROP TRIGGER IF EXISTS update_key_value_timestamp ON key_value_store
            """)
            
            await cur.execute("""
                CREATE TRIGGER update_key_value_timestamp 
                BEFORE UPDATE ON key_value_store
                FOR EACH ROW EXECUTE FUNCTION update_modified_column()
            """)
        
        await self._execute_operation(create_tables_operation)
    
    # Integration Management Methods
    async def create_integration(
        self,
        integration_id: str,
        integration_type: str,
        display_name: str,
        config: Dict[str, Any],
        user_id: Optional[str] = None,
        is_active: bool = True
    ) -> IntegrationRecord:
        """Create a new integration record."""
        current_time = time.time()
        
        async def create_operation(cur):
            await cur.execute("""
                INSERT INTO integrations (
                    id, user_id, integration_type, display_name, 
                    is_active, config, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                integration_id, user_id, integration_type, display_name,
                is_active, json.dumps(config), current_time, current_time
            ))
        
        await self._execute_operation(create_operation)
        
        integration = IntegrationRecord(
            id=integration_id,
            user_id=user_id,
            integration_type=integration_type,
            display_name=display_name,
            is_active=is_active,
            config=config,
            created_at=current_time,
            updated_at=current_time
        )
        
        logger.info(f"Created integration: {display_name} ({integration_type})")
        return integration
    
    async def get_integration(self, integration_id: str) -> Optional[IntegrationRecord]:
        """Get an integration by ID."""
        async def get_operation(cur):
            await cur.execute("""
                SELECT id, user_id, integration_type, display_name, is_active, config, 
                       EXTRACT(EPOCH FROM created_at), EXTRACT(EPOCH FROM updated_at)
                FROM integrations WHERE id = %s
            """, (integration_id,))
            return await cur.fetchone()
        
        row = await self._execute_operation(get_operation)
        
        if row:
            return IntegrationRecord(
                id=row[0],
                user_id=row[1],
                integration_type=row[2],
                display_name=row[3],
                is_active=bool(row[4]),
                config=row[5] if isinstance(row[5], dict) else json.loads(row[5]),
                created_at=float(row[6]),
                updated_at=float(row[7])
            )
        return None
    
    async def list_integrations(self, user_id: Optional[str] = None, is_active: Optional[bool] = None) -> List[IntegrationRecord]:
        """List integrations with optional filtering."""
        async def list_operation(cur):
            query = """
                SELECT id, user_id, integration_type, display_name, is_active, config, 
                       EXTRACT(EPOCH FROM created_at), EXTRACT(EPOCH FROM updated_at)
                FROM integrations
            """
            params = []
            conditions = []
            
            if user_id is not None:
                conditions.append("user_id = %s")
                params.append(user_id)
            if is_active is not None:
                conditions.append("is_active = %s")
                params.append(is_active)
            
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            
            query += " ORDER BY created_at"
            
            await cur.execute(query, params)
            return await cur.fetchall()
        
        rows = await self._execute_operation(list_operation)
        
        integrations = []
        for row in rows:
            integrations.append(IntegrationRecord(
                id=row[0],
                user_id=row[1],
                integration_type=row[2],
                display_name=row[3],
                is_active=bool(row[4]),
                config=row[5] if isinstance(row[5], dict) else json.loads(row[5]),
                created_at=float(row[6]),
                updated_at=float(row[7])
            ))
        
        return integrations
    
    async def update_integration(
        self,
        integration_id: str,
        config: Optional[Dict[str, Any]] = None,
        is_active: Optional[bool] = None,
        display_name: Optional[str] = None
    ) -> Optional[IntegrationRecord]:
        """Update an integration record."""
        # First get the current record
        current = await self.get_integration(integration_id)
        if not current:
            return None
        
        # Prepare updates
        updates = []
        params = []
        
        if config is not None:
            updates.append("config = %s")
            params.append(json.dumps(config))
            current.config = config
        
        if is_active is not None:
            updates.append("is_active = %s")
            params.append(is_active)
            current.is_active = is_active
        
        if display_name is not None:
            updates.append("display_name = %s")
            params.append(display_name)
            current.display_name = display_name
        
        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            current.updated_at = time.time()
            params.append(integration_id)  # WHERE clause parameter
            
            async def update_operation(cur):
                await cur.execute(
                    f"UPDATE integrations SET {', '.join(updates)} WHERE id = %s",
                    params
                )
            
            await self._execute_operation(update_operation)
        
        return current
    
    async def delete_integration(self, integration_id: str) -> bool:
        """Delete an integration and its credentials."""
        async def delete_operation(cur):
            # Delete credentials first (CASCADE should handle this, but be explicit)
            await cur.execute("DELETE FROM credentials WHERE integration_id = %s", (integration_id,))
            
            # Delete integration
            await cur.execute("DELETE FROM integrations WHERE id = %s", (integration_id,))
            return cur.rowcount > 0
        
        deleted = await self._execute_operation(delete_operation)
        
        if deleted:
            logger.info(f"Deleted integration: {integration_id}")
        
        return deleted
    
    # Credential Management Methods
    async def create_credential(
        self,
        credential_id: str,
        integration_id: str,
        credential_key: str,
        encrypted_value: bytes
    ) -> CredentialRecord:
        """Create a new credential record."""
        current_time = time.time()
        
        async def create_operation(cur):
            await cur.execute("""
                INSERT INTO credentials (id, integration_id, credential_key, credential_value_encrypted, created_at)
                VALUES (%s, %s, %s, %s, %s)
            """, (credential_id, integration_id, credential_key, encrypted_value, current_time))
        
        await self._execute_operation(create_operation)
        
        return CredentialRecord(
            id=credential_id,
            integration_id=integration_id,
            credential_key=credential_key,
            credential_value_encrypted=encrypted_value,
            created_at=current_time
        )
    
    async def get_credentials(self, integration_id: str) -> List[CredentialRecord]:
        """Get all credentials for an integration."""
        async def get_operation(cur):
            await cur.execute("""
                SELECT id, integration_id, credential_key, credential_value_encrypted, 
                       EXTRACT(EPOCH FROM created_at)
                FROM credentials WHERE integration_id = %s
            """, (integration_id,))
            return await cur.fetchall()
        
        rows = await self._execute_operation(get_operation)
        
        credentials = []
        for row in rows:
            credentials.append(CredentialRecord(
                id=row[0],
                integration_id=row[1],
                credential_key=row[2],
                credential_value_encrypted=row[3],
                created_at=float(row[4])
            ))
        
        return credentials
    
    async def delete_credentials(self, integration_id: str) -> int:
        """Delete all credentials for an integration."""
        async def delete_operation(cur):
            await cur.execute("DELETE FROM credentials WHERE integration_id = %s", (integration_id,))
            return cur.rowcount
        
        deleted_count = await self._execute_operation(delete_operation)
        return deleted_count
    
    # State Change Management Methods
    async def create_state_change(
        self,
        timestamp: float,
        change_type: str,
        source: str,
        raw_content: str,
        channel_id: Optional[str] = None,
        observations: Optional[str] = None,
        potential_actions: Optional[str] = None,
        selected_actions: Optional[str] = None,
        reasoning: Optional[str] = None
    ) -> StateChangeRecord:
        """Create a new state change record."""
        async def create_operation(cur):
            await cur.execute("""
                INSERT INTO state_changes (
                    timestamp, change_type, source, channel_id,
                    observations, potential_actions, selected_actions,
                    reasoning, raw_content
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                timestamp, change_type, source, channel_id,
                observations, potential_actions, selected_actions,
                reasoning, raw_content
            ))
            result = await cur.fetchone()
            return result[0] if result else None
        
        record_id = await self._execute_operation(create_operation)
        
        return StateChangeRecord(
            id=record_id,
            timestamp=timestamp,
            change_type=change_type,
            source=source,
            channel_id=channel_id,
            observations=observations,
            potential_actions=potential_actions,
            selected_actions=selected_actions,
            reasoning=reasoning,
            raw_content=raw_content
        )
    
    async def get_state_changes(
        self,
        channel_id: Optional[str] = None,
        change_type: Optional[str] = None,
        since_timestamp: Optional[float] = None,
        limit: int = 100
    ) -> List[StateChangeRecord]:
        """Get state changes with optional filtering."""
        async def get_operation(cur):
            query = """
                SELECT id, timestamp, change_type, source, channel_id,
                       observations, potential_actions, selected_actions,
                       reasoning, raw_content, created_at
                FROM state_changes
            """
            
            conditions = []
            params = []
            
            if channel_id:
                conditions.append("channel_id = %s")
                params.append(channel_id)
            if change_type:
                conditions.append("change_type = %s")
                params.append(change_type)
            if since_timestamp:
                conditions.append("timestamp >= %s")
                params.append(since_timestamp)
            
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            
            query += " ORDER BY timestamp DESC LIMIT %s"
            params.append(limit)
            
            await cur.execute(query, params)
            return await cur.fetchall()
        
        rows = await self._execute_operation(get_operation)
        
        state_changes = []
        for row in rows:
            state_changes.append(StateChangeRecord(
                id=row[0],
                timestamp=row[1],
                change_type=row[2],
                source=row[3],
                channel_id=row[4],
                observations=row[5],
                potential_actions=row[6],
                selected_actions=row[7],
                reasoning=row[8],
                raw_content=row[9],
                created_at=str(row[10]) if row[10] else None
            ))
        
        return state_changes
    
    # Undecryptable Event Management Methods
    async def create_undecryptable_event(
        self,
        event_id: str,
        room_id: str,
        sender: str,
        timestamp: float,
        event_data: Dict[str, Any]
    ) -> UndecryptableEventRecord:
        """Create a new undecryptable event record."""
        async def create_operation(cur):
            await cur.execute("""
                INSERT INTO undecryptable_events (event_id, room_id, sender, timestamp, retry_count, event_data)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (event_id, room_id, sender, timestamp, 0, json.dumps(event_data)))
            result = await cur.fetchone()
            return result[0] if result else None
        
        record_id = await self._execute_operation(create_operation)
        
        return UndecryptableEventRecord(
            id=record_id,
            event_id=event_id,
            room_id=room_id,
            sender=sender,
            timestamp=timestamp,
            retry_count=0,
            last_retry=None,
            event_data=event_data
        )
    
    async def get_undecryptable_events(
        self,
        room_id: Optional[str] = None,
        max_retries: Optional[int] = None
    ) -> List[UndecryptableEventRecord]:
        """Get undecryptable events with optional filtering."""
        async def get_operation(cur):
            query = """
                SELECT id, event_id, room_id, sender, timestamp, retry_count, last_retry, event_data
                FROM undecryptable_events
            """
            
            conditions = []
            params = []
            
            if room_id:
                conditions.append("room_id = %s")
                params.append(room_id)
            if max_retries is not None:
                conditions.append("retry_count <= %s")
                params.append(max_retries)
            
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            
            await cur.execute(query, params)
            return await cur.fetchall()
        
        rows = await self._execute_operation(get_operation)
        
        events = []
        for row in rows:
            events.append(UndecryptableEventRecord(
                id=row[0],
                event_id=row[1],
                room_id=row[2],
                sender=row[3],
                timestamp=row[4],
                retry_count=row[5],
                last_retry=row[6],
                event_data=row[7] if isinstance(row[7], dict) else json.loads(row[7])
            ))
        
        return events
    
    async def update_undecryptable_event_retry(
        self,
        event_id: str,
        retry_count: int,
        last_retry: float
    ) -> Optional[UndecryptableEventRecord]:
        """Update retry information for an undecryptable event."""
        async def update_operation(cur):
            await cur.execute("""
                UPDATE undecryptable_events 
                SET retry_count = %s, last_retry = %s
                WHERE event_id = %s
            """, (retry_count, last_retry, event_id))
            return cur.rowcount > 0
        
        updated = await self._execute_operation(update_operation)
        
        if updated:
            # Return the updated record
            async def get_operation(cur):
                await cur.execute("""
                    SELECT id, event_id, room_id, sender, timestamp, retry_count, last_retry, event_data
                    FROM undecryptable_events WHERE event_id = %s
                """, (event_id,))
                return await cur.fetchone()
            
            row = await self._execute_operation(get_operation)
            
            if row:
                return UndecryptableEventRecord(
                    id=row[0],
                    event_id=row[1],
                    room_id=row[2],
                    sender=row[3],
                    timestamp=row[4],
                    retry_count=row[5],
                    last_retry=row[6],
                    event_data=row[7] if isinstance(row[7], dict) else json.loads(row[7])
                )
        
        return None

    # Replied-to Casts Management Methods (for duplicate prevention)
    async def add_replied_to_cast(self, original_cast_hash: str, reply_cast_hash: str) -> None:
        """
        Add a record indicating a cast has been replied to.
        
        Args:
            original_cast_hash: The hash of the original cast that was replied to
            reply_cast_hash: The hash of the reply cast that was sent
        """
        async def db_operation(cur):
            await cur.execute(
                """INSERT INTO replied_to_casts (original_cast_hash, reply_cast_hash, replied_at) 
                   VALUES (%s, %s, %s) ON CONFLICT (original_cast_hash) DO NOTHING""",
                (original_cast_hash, reply_cast_hash, time.time())
            )
        
        await self._execute_operation(db_operation)
        logger.debug(f"Recorded reply to cast {original_cast_hash} with reply hash {reply_cast_hash}")

    async def has_replied_to(self, original_cast_hash: str) -> bool:
        """
        Check if a cast has already been replied to from the persistent store.
        
        Args:
            original_cast_hash: The hash of the original cast to check
            
        Returns:
            True if the bot has already replied to this cast, False otherwise
        """
        async def db_operation(cur) -> bool:
            await cur.execute(
                "SELECT 1 FROM replied_to_casts WHERE original_cast_hash = %s LIMIT 1",
                (original_cast_hash,)
            )
            result = await cur.fetchone()
            return result is not None
        
        result = await self._execute_operation(db_operation)
        logger.debug(f"Persistent cache check for cast {original_cast_hash}: {'found' if result else 'not found'}")
        return result

    async def get_replied_to_cast_info(self, original_cast_hash: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a replied-to cast.
        
        Args:
            original_cast_hash: The hash of the original cast
            
        Returns:
            Dictionary with reply information or None if not found
        """
        async def db_operation(cur) -> Optional[Dict[str, Any]]:
            await cur.execute(
                "SELECT reply_cast_hash, replied_at FROM replied_to_casts WHERE original_cast_hash = %s",
                (original_cast_hash,)
            )
            row = await cur.fetchone()
            if row:
                return {
                    "original_cast_hash": original_cast_hash,
                    "reply_cast_hash": row[0],
                    "replied_at": row[1]
                }
            return None
        
        return await self._execute_operation(db_operation)

    # Configuration and State Management Methods
    async def set_config_value(self, key: str, value: Any) -> None:
        """Store a configuration value in the key-value store."""
        async def set_operation(cur):
            await cur.execute("""
                INSERT INTO key_value_store (key, value) VALUES (%s, %s)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP
            """, (key, json.dumps(value)))
        
        await self._execute_operation(set_operation)
    
    async def get_config_value(self, key: str, default: Any = None) -> Any:
        """Retrieve a configuration value from the key-value store."""
        async def get_operation(cur):
            await cur.execute("""
                SELECT value FROM key_value_store WHERE key = %s
            """, (key,))
            return await cur.fetchone()
        
        result = await self._execute_operation(get_operation)
        
        if result:
            try:
                return result[0] if isinstance(result[0], (dict, list)) else json.loads(result[0])
            except (json.JSONDecodeError, TypeError):
                logger.error(f"Failed to decode JSON for config key {key}")
                return default
        return default
    
    async def delete_config_value(self, key: str) -> bool:
        """Delete a configuration value from the key-value store."""
        async def delete_operation(cur):
            await cur.execute("DELETE FROM key_value_store WHERE key = %s", (key,))
            return cur.rowcount > 0
        
        return await self._execute_operation(delete_operation)
