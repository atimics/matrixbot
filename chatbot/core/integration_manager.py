"""
Integration Manager

Centralized management of all service integrations.
Handles loading, connecting, and managing the lifecycle of integrations.
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional, Type
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
        
        # Initialize encryption for credentials
        if encryption_key:
            self.cipher = Fernet(encryption_key)
        else:
            # Generate a key for development - in production, this should come from a secure vault
            self.cipher = Fernet(Fernet.generate_key())
            logger.warning("Using generated encryption key - not suitable for production!")
            
    async def initialize(self):
        """Initialize the integration manager and database schema"""
        await self._create_database_schema()
        await self._register_integration_types()
        logger.info("IntegrationManager initialized")
        
    async def _create_database_schema(self):
        """Create the database tables for integration management"""
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
                    created_at REAL NOT NULL,
                    FOREIGN KEY (integration_id) REFERENCES integrations (id) ON DELETE CASCADE,
                    UNIQUE(integration_id, credential_key)
                )
            """)
            
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
        
        async with aiosqlite.connect(self.db_path) as db:
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
        
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT id FROM integrations WHERE is_active = TRUE
            """)
            rows = await cursor.fetchall()
            
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
            
    async def list_integrations(self) -> List[Dict[str, Any]]:
        """List all configured integrations with their status"""
        integrations = []
        
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT id, integration_type, display_name, is_active 
                FROM integrations ORDER BY created_at
            """)
            rows = await cursor.fetchall()
            
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
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT integration_type, display_name, is_active, config
                FROM integrations WHERE id = ?
            """, (integration_id,))
            row = await cursor.fetchone()
            
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
        
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT credential_key, credential_value_encrypted
                FROM credentials WHERE integration_id = ?
            """, (integration_id,))
            rows = await cursor.fetchall()
            
        for row in rows:
            cred_key, encrypted_value = row
            try:
                decrypted_value = self.cipher.decrypt(encrypted_value).decode()
                credentials[cred_key] = decrypted_value
            except Exception as e:
                logger.warning(f"Failed to decrypt credential '{cred_key}' for integration '{integration_id}': {e}")
                logger.warning(f"This usually happens when the encryption key has changed. Credential will be skipped.")
                # Skip this credential - it will need to be re-added with the new key
            
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
                        INSERT INTO credentials (id, integration_id, credential_key, credential_value_encrypted, created_at)
                        VALUES (?, ?, ?, ?, ?)
                    """, (credential_id, integration_id, key, encrypted_value, time.time()))
            
            await db.commit()
        
        logger.info(f"Updated {len(credentials)} credentials for integration {integration_id}")
        
    async def clean_invalid_credentials(self, integration_id: str) -> None:
        """Clean up credentials that can't be decrypted (due to key changes)"""
        async with aiosqlite.connect(self.db_path) as db:
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

    def get_available_integration_types(self) -> List[str]:
        """Get list of available integration types"""
        return list(self.integration_types.keys())
        
    def get_active_integrations(self) -> Dict[str, Integration]:
        """Get currently active integration instances"""
        return self.active_integrations.copy()
    
    async def connect_all(self) -> Dict[str, bool]:
        """Connect all active integrations (alias for connect_all_active)"""
        return await self.connect_all_active()
    
    def get_observers(self) -> List[Integration]:
        """Get list of active integration instances (observers)"""
        return list(self.active_integrations.values())
