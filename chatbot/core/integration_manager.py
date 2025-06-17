"""
Integration Manager

Centralized management of all service integrations.
Handles loading, connecting, and managing the lifecycle of integrations.
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple, Type
from pathlib import Path
import uuid

import aiosqlite
from cryptography.fernet import Fernet

from ..integrations.base import Integration, IntegrationError
from ..config import settings

logger = logging.getLogger(__name__)


class IntegrationManager:
    """Manages all service integrations for the chatbot"""
    
    def __init__(self, db_path: str, encryption_key: Optional[bytes] = None, world_state_manager=None):
        self.db_path = db_path
        self.world_state_manager = world_state_manager
        self.active_integrations: Dict[str, Integration] = {}
        self.integration_types: Dict[str, Type[Integration]] = {}
        
        # Add service-oriented tracking
        self.active_services: Dict[str, Any] = {}
        
        # For in-memory databases, we need to maintain a persistent connection
        self._persistent_db = None
        self._is_memory_db = db_path == ":memory:"
        
        # Initialize encryption for credentials
        if encryption_key:
            self.cipher = Fernet(encryption_key)
        else:
            # Generate a key for development - in production, this should come from a secure vault
            self.cipher = Fernet(Fernet.generate_key())
            logger.warning("Using generated encryption key - not suitable for production!")
            
    async def initialize(self):
        """Initialize the integration manager and database schema"""
        if self._is_memory_db:
            # For in-memory databases, create a persistent connection
            self._persistent_db = await aiosqlite.connect(self.db_path)
            
        await self._create_database_schema()
        await self._register_integration_types()
        logger.info("IntegrationManager initialized")
    
    async def _get_db_connection(self):
        """Get a database connection, reusing persistent connection for in-memory databases"""
        if self._is_memory_db and self._persistent_db:
            return self._persistent_db
        else:
            return aiosqlite.connect(self.db_path)
    
    async def _execute_db_operation(self, operation_func):
        """Execute a database operation with proper connection handling"""
        if self._is_memory_db:
            # Use persistent connection for in-memory database
            return await operation_func(self._persistent_db)
        else:
            # Use context manager for file databases
            async with aiosqlite.connect(self.db_path) as db:
                return await operation_func(db)
            
    async def cleanup(self):
        """Clean up resources"""
        if self._persistent_db:
            await self._persistent_db.close()
            self._persistent_db = None
        
    async def _create_database_schema(self):
        """Create the database tables for integration management"""
        if self._is_memory_db:
            # Use persistent connection for in-memory database
            db = self._persistent_db
            # Integrations table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS integrations (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    integration_type TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    is_active BOOLEAN DEFAULT TRUE,
                    config TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
            """)
            
            # Credentials table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS credentials (
                    id TEXT PRIMARY KEY,
                    integration_id TEXT NOT NULL,
                    credential_key TEXT NOT NULL,
                    credential_value_encrypted BLOB NOT NULL,
                    created_at REAL NOT NULL,
                    FOREIGN KEY (integration_id) REFERENCES integrations (id) ON DELETE CASCADE,
                    UNIQUE(integration_id, credential_key)
                )
            """)
            
            await db.commit()
        else:
            # Use regular connection for file databases
            async with aiosqlite.connect(self.db_path) as db:
                # Integrations table
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS integrations (
                        id TEXT PRIMARY KEY,
                        user_id TEXT,
                        integration_type TEXT NOT NULL,
                        display_name TEXT NOT NULL,
                        is_active BOOLEAN DEFAULT TRUE,
                        config TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL
                    )
                """)
                
                # Credentials table
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS credentials (
                        id TEXT PRIMARY KEY,
                        integration_id TEXT NOT NULL,
                        credential_key TEXT NOT NULL,
                        credential_value_encrypted BLOB NOT NULL,
                        status TEXT DEFAULT 'active',
                        created_at REAL NOT NULL,
                        updated_at REAL,
                        FOREIGN KEY (integration_id) REFERENCES integrations (id) ON DELETE CASCADE,
                        UNIQUE(integration_id, credential_key)
                    )
                """)
                
                # Add status column to existing credentials table if it doesn't exist
                try:
                    await db.execute("ALTER TABLE credentials ADD COLUMN status TEXT DEFAULT 'active'")
                    await db.execute("ALTER TABLE credentials ADD COLUMN updated_at REAL")
                    logger.info("Added status and updated_at columns to credentials table")
                except Exception:
                    # Columns already exist, which is fine
                    pass
                
                await db.commit()
            
    async def _register_integration_types(self):
        """Register available integration types"""
        # Import integration classes here to avoid circular imports
        try:
            from ..integrations.matrix.observer import MatrixObserver
            self.integration_types['matrix'] = MatrixObserver
        except ImportError as e:
            logger.warning(f"Failed to import MatrixObserver: {e}")
            
        try:
            from ..integrations.farcaster import FarcasterObserver
            self.integration_types['farcaster'] = FarcasterObserver
        except ImportError as e:
            logger.warning(f"Failed to import FarcasterObserver: {e}")
            
        logger.info(f"Registered integration types: {list(self.integration_types.keys())}")
        
    def get_available_integration_types(self) -> List[str]:
        """Get list of available integration types."""
        return list(self.integration_types.keys())
        
    async def add_integration(
        self,
        integration_type: str,
        display_name: str,
        config: Dict[str, Any],
        credentials: Dict[str, str],
        user_id: Optional[str] = None
    ) -> str:
        """
        Add a new integration configuration.
        
        Args:
            integration_type: Type of integration (e.g., 'farcaster', 'matrix')
            display_name: User-friendly name for this integration
            config: Non-sensitive configuration data
            credentials: Sensitive credentials to be encrypted
            user_id: Optional user ID for multi-user setups
            
        Returns:
            str: The integration ID
            
        Raises:
            IntegrationError: If the integration type is not supported
        """
        if integration_type not in self.integration_types:
            raise IntegrationError(f"Unsupported integration type: {integration_type}")
            
        integration_id = str(uuid.uuid4())
        current_time = asyncio.get_event_loop().time()
        
        async def db_operation(db):
            # Store integration configuration
            await db.execute("""
                INSERT INTO integrations (
                    id, user_id, integration_type, display_name, 
                    is_active, config, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                integration_id, user_id, integration_type, display_name,
                True, json.dumps(config), current_time, current_time
            ))
            
            # Store encrypted credentials
            for cred_key, cred_value in credentials.items():
                encrypted_value = self.cipher.encrypt(cred_value.encode())
                await db.execute("""
                    INSERT INTO credentials (
                        id, integration_id, credential_key, 
                        credential_value_encrypted, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                """, (
                    str(uuid.uuid4()), integration_id, cred_key,
                    encrypted_value, current_time
                ))
                
            await db.commit()
        
        await self._execute_db_operation(db_operation)
            
        logger.info(f"Added integration {display_name} ({integration_type}) with ID {integration_id}")
        return integration_id
        
    async def connect_integration(self, integration_id: str, world_state_manager=None) -> bool:
        """
        Connect a specific integration by ID.
        
        Args:
            integration_id: The integration ID to connect
            world_state_manager: Required for some integrations
            
        Returns:
            bool: True if connection was successful
        """
        if integration_id in self.active_integrations:
            logger.info(f"Integration {integration_id} is already connected")
            return True
            
        # Load integration from database
        integration_data = await self._load_integration_data(integration_id)
        if not integration_data:
            logger.error(f"Integration {integration_id} not found in database")
            return False
            
        # Create integration instance
        integration_class = self.integration_types[integration_data['integration_type']]
        config = json.loads(integration_data['config'])
        
        # Load credentials for this integration
        credentials = await self._load_credentials(integration_id)
        
        # Create integration with appropriate constructor
        if integration_data['integration_type'] == 'matrix':
            integration = integration_class(
                integration_id=integration_id,
                display_name=integration_data['display_name'],
                config=config,
                world_state_manager=world_state_manager
            )
        elif integration_data['integration_type'] == 'farcaster':
            integration = integration_class(
                integration_id=integration_id,
                display_name=integration_data['display_name'],
                config=config,
                api_key=credentials.get('api_key'),
                signer_uuid=credentials.get('signer_uuid'),
                bot_fid=credentials.get('bot_fid'),
                world_state_manager=world_state_manager
            )
        else:
            # Generic constructor for future integrations
            integration = integration_class(
                integration_id=integration_id,
                display_name=integration_data['display_name'],
                config=config
            )
        
        # Set credentials (this will update existing ones or set new ones)
        if hasattr(integration, 'set_credentials'):
            await integration.set_credentials(credentials)
        
        # Attempt connection
        try:
            await integration.connect()
            self.active_integrations[integration_id] = integration
            logger.info(f"Successfully connected integration {integration_id}")
            return True
        except Exception as e:
            logger.error(f"Error connecting integration {integration_id}: {e}")
            return False
            
    async def disconnect_integration(self, integration_id: str) -> None:
        """Disconnect a specific integration"""
        if integration_id in self.active_integrations:
            integration = self.active_integrations[integration_id]
            await integration.disconnect()
            del self.active_integrations[integration_id]
            logger.info(f"Disconnected integration {integration_id}")
            
    async def connect_all_active(self) -> Dict[str, bool]:
        """
        Connect all active integrations.
        
        Returns:
            Dict mapping integration_id to connection success status
        """
        results = {}
        
        async def db_operation(db):
            cursor = await db.execute("""
                SELECT id FROM integrations WHERE is_active = TRUE
            """)
            return await cursor.fetchall()
        
        rows = await self._execute_db_operation(db_operation)
            
        for row in rows:
            integration_id = row[0]
            success = await self.connect_integration(integration_id, self.world_state_manager)
            results[integration_id] = success
            
        logger.info(f"Connected {sum(results.values())}/{len(results)} active integrations")
        return results
        
    async def disconnect_all(self) -> None:
        """Disconnect all active integrations"""
        integration_ids = list(self.active_integrations.keys())
        for integration_id in integration_ids:
            await self.disconnect_integration(integration_id)
            
    async def start_all_services(self) -> None:
        """Start services for all active integrations"""
        # All integrations are already connected via connect_all_active()
        # The connect() method handles starting any necessary background services
        logger.info(f"All services ready for {len(self.active_integrations)} active integrations")
                
    async def stop_all_services(self) -> None:
        """Stop services for all active integrations"""
        # Services are stopped when integrations are disconnected
        # This method exists for API compatibility but delegates to disconnect_all()
        await self.disconnect_all()
        logger.info("All services stopped via disconnection")
            
    async def get_integration_status(self, integration_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed status for a specific integration"""
        if integration_id in self.active_integrations:
            integration = self.active_integrations[integration_id]
            return await integration.get_status()
        else:
            # Return basic info from database if not connected
            integration_data = await self._load_integration_data(integration_id)
            if integration_data:
                return {
                    "integration_id": integration_id,
                    "integration_type": integration_data['integration_type'],
                    "display_name": integration_data['display_name'],
                    "is_connected": False,
                    "is_active": integration_data['is_active']
                }
            return None
    
    def get_active_integrations(self) -> Dict[str, Integration]:
        """Get the dictionary of active integrations"""
        return self.active_integrations

    async def list_integrations(self) -> List[Dict[str, Any]]:
        """List all configured integrations with their status"""
        integrations = []
        
        async def db_operation(db):
            cursor = await db.execute("""
                SELECT id, integration_type, display_name, is_active 
                FROM integrations ORDER BY created_at
            """)
            return await cursor.fetchall()
        
        rows = await self._execute_db_operation(db_operation)
            
        for row in rows:
            integration_id, integration_type, display_name, is_active = row
            status = await self.get_integration_status(integration_id)
            integrations.append(status)
            
        return integrations
        
    async def test_integration_config(
        self,
        integration_type: str,
        config: Dict[str, Any],
        credentials: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        Test an integration configuration without saving it.
        
        Returns:
            Dict with 'success': bool and optional 'error': str
        """
        if integration_type not in self.integration_types:
            return {"success": False, "error": f"Unsupported integration type: {integration_type}"}
            
        try:
            # Create temporary integration instance
            integration_class = self.integration_types[integration_type]
            
            if integration_type == 'matrix':
                integration = integration_class(world_state_manager=self.world_state_manager)
            elif integration_type == 'farcaster':
                integration = integration_class(
                    api_key=credentials.get('api_key'),
                    signer_uuid=credentials.get('signer_uuid'),
                    bot_fid=credentials.get('bot_fid'),
                    world_state_manager=self.world_state_manager
                )
            else:
                integration = integration_class()
            
            if hasattr(integration, 'set_credentials'):
                await integration.set_credentials(credentials)
                
            result = await integration.test_connection()
            return {"success": result, "error": None if result else "Connection test failed"}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
            
    async def _load_integration_data(self, integration_id: str) -> Optional[Dict[str, Any]]:
        """Load integration configuration from database"""
        async def db_operation(db):
            cursor = await db.execute("""
                SELECT integration_type, display_name, is_active, config
                FROM integrations WHERE id = ?
            """, (integration_id,))
            return await cursor.fetchone()
            
        row = await self._execute_db_operation(db_operation)
            
        if row:
            return {
                "integration_type": row[0],
                "display_name": row[1],
                "is_active": bool(row[2]),
                "config": row[3]
            }
        return None
        
    async def _load_credentials(self, integration_id: str) -> Dict[str, str]:
        """Load and decrypt credentials for an integration"""
        credentials = {}
        
        async def db_operation(db):
            cursor = await db.execute("""
                SELECT credential_key, credential_value_encrypted, id
                FROM credentials 
                WHERE integration_id = ? AND status = 'active'
            """, (integration_id,))
            return await cursor.fetchall()
            
        rows = await self._execute_db_operation(db_operation)
        stale_credential_ids = []
            
        for row in rows:
            cred_key, encrypted_value, credential_id = row
            try:
                decrypted_value = self.cipher.decrypt(encrypted_value).decode()
                credentials[cred_key] = decrypted_value
            except Exception as e:
                logger.warning(f"Failed to decrypt credential '{cred_key}' for integration '{integration_id}': {e}")
                logger.info(f"Marking credential '{cred_key}' as stale due to decryption failure")
                stale_credential_ids.append(credential_id)
        
        # Mark failed credentials as stale
        if stale_credential_ids:
            await self._mark_credentials_stale(stale_credential_ids)
            
        return credentials
        
    async def update_credentials(self, integration_id: str, credentials: Dict[str, str]) -> None:
        """Update credentials for an existing integration"""
        async with aiosqlite.connect(self.db_path) as db:
            # First remove existing credentials for this integration
            await db.execute("""
                DELETE FROM credentials WHERE integration_id = ?
            """, (integration_id,))
            
            # Add new credentials
            for key, value in credentials.items():
                if value:  # Only store non-empty values
                    encrypted_value = self.cipher.encrypt(value.encode())
                    credential_id = str(uuid.uuid4())
                    await db.execute("""
                        INSERT INTO credentials (id, integration_id, credential_key, credential_value_encrypted, status, created_at, updated_at)
                        VALUES (?, ?, ?, ?, 'active', ?, ?)
                    """, (credential_id, integration_id, key, encrypted_value, time.time(), time.time()))
            
            await db.commit()
        
        logger.info(f"Updated {len(credentials)} credentials for integration {integration_id}")
        
        # If the integration is currently active, update its credentials
        await self.update_active_integration_credentials(integration_id, credentials)
        
    async def update_active_integration_credentials(self, integration_id: str, credentials: Dict[str, str]) -> None:
        """Update credentials for an active integration and notify it to reload"""
        if integration_id in self.active_integrations:
            integration = self.active_integrations[integration_id]
            if hasattr(integration, 'set_credentials'):
                try:
                    await integration.set_credentials(credentials)
                    logger.info(f"Updated credentials for active integration {integration_id}")
                except Exception as e:
                    logger.error(f"Failed to update credentials for active integration {integration_id}: {e}")
            else:
                logger.warning(f"Active integration {integration_id} does not support credential updates")
            
    async def clean_invalid_credentials(self, integration_id: str) -> None:
        """Clean up credentials that can't be decrypted (due to key changes)"""
        async def db_operation(db):
            cursor = await db.execute("""
                SELECT credential_key, credential_value_encrypted, rowid
                FROM credentials WHERE integration_id = ?
            """, (integration_id,))
            rows = await cursor.fetchall()
            
            invalid_rowids = []
            for row in rows:
                cred_key, encrypted_value, rowid = row
                try:
                    self.cipher.decrypt(encrypted_value).decode()
                except Exception:
                    logger.info(f"Marking invalid credential '{cred_key}' for cleanup (integration: {integration_id})")
                    invalid_rowids.append(rowid)
            
            # Remove invalid credentials
            if invalid_rowids:
                placeholders = ','.join(['?' for _ in invalid_rowids])
                await db.execute(f"""
                    DELETE FROM credentials WHERE rowid IN ({placeholders})
                """, invalid_rowids)
                await db.commit()
                logger.info(f"Cleaned up {len(invalid_rowids)} invalid credentials for integration '{integration_id}'")
        
        await self._execute_db_operation(db_operation)
        
    async def _mark_credentials_stale(self, credential_ids: List[str]) -> None:
        """Mark credentials as stale when decryption fails"""
        if not credential_ids:
            return
            
        async def db_operation(db):
            placeholders = ','.join(['?' for _ in credential_ids])
            await db.execute(f"""
                UPDATE credentials 
                SET status = 'stale', updated_at = ?
                WHERE id IN ({placeholders})
            """, [time.time()] + credential_ids)
            await db.commit()
            
        await self._execute_db_operation(db_operation)
        logger.info(f"Marked {len(credential_ids)} credentials as stale")
    
    async def delete_stale_credentials(self, integration_id: str) -> int:
        """Delete all stale credentials for an integration"""
        async def db_operation(db):
            cursor = await db.execute("""
                DELETE FROM credentials 
                WHERE integration_id = ? AND status = 'stale'
            """, (integration_id,))
            await db.commit()
            return cursor.rowcount
            
        deleted_count = await self._execute_db_operation(db_operation)
        logger.info(f"Deleted {deleted_count} stale credentials for integration {integration_id}")
        return deleted_count
    
    async def list_stale_credentials(self, integration_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all stale credentials, optionally filtered by integration"""
        async def db_operation(db):
            if integration_id:
                cursor = await db.execute("""
                    SELECT c.id, c.integration_id, c.credential_key, c.created_at, c.updated_at, i.display_name
                    FROM credentials c
                    JOIN integrations i ON c.integration_id = i.id
                    WHERE c.integration_id = ? AND c.status = 'stale'
                    ORDER BY c.updated_at DESC
                """, (integration_id,))
            else:
                cursor = await db.execute("""
                    SELECT c.id, c.integration_id, c.credential_key, c.created_at, c.updated_at, i.display_name
                    FROM credentials c
                    JOIN integrations i ON c.integration_id = i.id
                    WHERE c.status = 'stale'
                    ORDER BY c.updated_at DESC
                """)
            return await cursor.fetchall()
            
        rows = await self._execute_db_operation(db_operation)
        return [
            {
                "id": row[0],
                "integration_id": row[1],
                "credential_key": row[2],
                "created_at": row[3],
                "updated_at": row[4],
                "integration_name": row[5]
            }
            for row in rows
        ]

    async def remove_integration(self, integration_id: str) -> bool:
        """
        Remove an integration configuration from the database.
        
        Args:
            integration_id: The ID of the integration to remove.
            
        Returns:
            bool: True if removal was successful, False otherwise.
        """
        logger.info(f"Removing integration {integration_id}...")
        
        # First, ensure the integration is disconnected
        await self.disconnect_integration(integration_id)
        
        try:
            async def db_operation(db):
                cursor = await db.execute("DELETE FROM integrations WHERE id = ?", (integration_id,))
                await db.commit()
                return cursor.rowcount > 0

            removed = await self._execute_db_operation(db_operation)
            
            if removed:
                logger.info(f"Successfully removed integration {integration_id} from the database.")
            else:
                logger.warning(f"Attempted to remove integration {integration_id}, but it was not found in the database.")
            
            return removed
            
        except Exception as e:
            logger.error(f"Error removing integration {integration_id} from database: {e}", exc_info=True)
            return False
