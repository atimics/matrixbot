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
import uuid

import aiosqlite
from cryptography.fernet import Fernet

from ..integrations.base import Integration, IntegrationError
from ..config import settings


logger = logging.getLogger(__name__)


class IntegrationManager:
    """Manages all service integrations for the chatbot"""
    
    def __init__(self, db_path: str, encryption_key: Optional[str] = None, world_state_manager=None):
        self.db_path = db_path
        self.world_state_manager = world_state_manager
        self.active_integrations: Dict[str, Integration] = {}
        self.integration_types: Dict[str, Type[Integration]] = {}
        
        # For in-memory databases, we need to maintain a persistent connection
        self._persistent_db = None
        self._is_memory_db = db_path == ":memory:"
        
        # Initialize encryption for credentials
        if encryption_key:
            # encryption_key should be a base64-encoded string suitable for Fernet
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
        
        # Load credentials for this integration (with environment fallback)
        credentials = await self._load_credentials(integration_id)
        
        # Check if we have minimum required credentials after fallback
        if not self._validate_credentials(integration_data['integration_type'], credentials):
            logger.error(f"Integration {integration_id} missing required credentials even after environment fallback")
            return False
        
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
            
            # If connection fails, check if we have environment fallback credentials and retry
            if self._has_env_fallback_credentials(integration_data['integration_type']):
                logger.info(f"Connection failed - trying to update credentials from environment and retry for {integration_id}")
                try:
                    # Force reload credentials from environment
                    env_credentials = await self._get_env_credentials(integration_data['integration_type'])
                    if env_credentials and self._validate_credentials(integration_data['integration_type'], env_credentials):
                        # Update stored credentials
                        await self.update_credentials(integration_id, env_credentials)
                        
                        # Update integration credentials and retry connection
                        if hasattr(integration, 'set_credentials'):
                            await integration.set_credentials(env_credentials)
                        
                        # Retry connection
                        await integration.connect()
                        self.active_integrations[integration_id] = integration
                        logger.info(f"Successfully connected integration {integration_id} after updating credentials from environment")
                        return True
                except Exception as retry_e:
                    logger.error(f"Failed to connect integration {integration_id} even after environment credential update: {retry_e}")
            
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
        """Load and decrypt credentials for an integration, with environment fallback"""
        credentials = {}
        
        async def db_operation(db):
            cursor = await db.execute("""
                SELECT credential_key, credential_value_encrypted
                FROM credentials WHERE integration_id = ?
            """, (integration_id,))
            return await cursor.fetchall()
            
        rows = await self._execute_db_operation(db_operation)
        
        # Track invalid credentials for cleanup
        invalid_credentials = []
        encryption_failed = False
            
        for row in rows:
            cred_key, encrypted_value = row
            try:
                decrypted_value = self.cipher.decrypt(encrypted_value).decode()
                credentials[cred_key] = decrypted_value
            except Exception as e:
                logger.warning(f"Failed to decrypt credential '{cred_key}' for integration '{integration_id}': {e}")
                logger.warning("This usually happens when the encryption key has changed. Will fall back to environment variables.")
                invalid_credentials.append(cred_key)
                encryption_failed = True
        
        # Get integration type to determine environment fallback
        integration_data = await self._load_integration_data(integration_id)
        if integration_data:
            integration_type = integration_data['integration_type']
            
            # Apply environment variable fallbacks
            credentials = await self._apply_env_fallbacks(integration_type, credentials)
            
            # If encryption failed and we got valid credentials from environment, update stored credentials
            if encryption_failed and self._validate_credentials(integration_type, credentials):
                logger.info(f"Encryption key changed - updating stored credentials for integration '{integration_id}' from environment variables")
                try:
                    await self.update_credentials(integration_id, credentials)
                    logger.info(f"Successfully updated stored credentials for integration '{integration_id}'")
                except Exception as e:
                    logger.error(f"Failed to update stored credentials for integration '{integration_id}': {e}")
        
        # Clean up invalid credentials after we've potentially updated them
        if invalid_credentials:
            logger.info(f"Cleaning up {len(invalid_credentials)} invalid credentials for integration '{integration_id}'")
            await self.clean_invalid_credentials(integration_id)
            
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
        
    def get_active_integrations(self) -> Dict[str, Integration]:
        """Get currently active integration instances"""
        return self.active_integrations.copy()
    
    async def connect_all(self) -> Dict[str, bool]:
        """Connect all active integrations (alias for connect_all_active)"""
        return await self.connect_all_active()
    
    def get_observers(self) -> List[Integration]:
        """Get list of active integration instances (observers)"""
        return list(self.active_integrations.values())
    
    def get_available_integration_types(self) -> List[str]:
        """Get list of available integration types"""
        return list(self.integration_types.keys())
    
    async def _apply_env_fallbacks(self, integration_type: str, credentials: Dict[str, str]) -> Dict[str, str]:
        """Apply environment variable fallbacks for missing or invalid credentials"""
        
        if integration_type == 'farcaster':
            # Check if we have any valid credentials, if not fall back to environment
            # Also apply fallback if credentials are empty strings or invalid
            if (not credentials.get('api_key') or not credentials['api_key'].strip()) and settings.farcaster.neynar_api_key:
                logger.info("Falling back to environment variables for Farcaster credentials")
                credentials['api_key'] = settings.farcaster.neynar_api_key
                
            if (not credentials.get('signer_uuid') or not credentials['signer_uuid'].strip()) and settings.farcaster.bot_signer_uuid:
                credentials['signer_uuid'] = settings.farcaster.bot_signer_uuid
                
            if (not credentials.get('bot_fid') or not credentials['bot_fid'].strip()) and settings.farcaster.bot_fid:
                credentials['bot_fid'] = settings.farcaster.bot_fid
                
        elif integration_type == 'matrix':
            # Check if we have any valid credentials, if not fall back to environment
            # Also apply fallback if credentials are empty strings or invalid
            if (not credentials.get('homeserver') or not credentials['homeserver'].strip()) and settings.matrix.homeserver:
                logger.info("Falling back to environment variables for Matrix credentials")
                credentials['homeserver'] = settings.matrix.homeserver
                
            if (not credentials.get('user_id') or not credentials['user_id'].strip()) and settings.matrix.user_id:
                credentials['user_id'] = settings.matrix.user_id
                
            if (not credentials.get('password') or not credentials['password'].strip()) and settings.matrix.password:
                credentials['password'] = settings.matrix.password
        
        return credentials
    
    def _validate_credentials(self, integration_type: str, credentials: Dict[str, str]) -> bool:
        """Validate that required credentials are present for the integration type"""
        if integration_type == 'farcaster':
            return bool(credentials.get('api_key'))  # Minimum requirement
        elif integration_type == 'matrix':
            return bool(credentials.get('homeserver') and 
                       credentials.get('user_id') and 
                       credentials.get('password'))
        return True  # For unknown types, assume valid
    
    def _has_env_fallback_credentials(self, integration_type: str) -> bool:
        """Check if environment variables are available for fallback"""
        
        if integration_type == 'farcaster':
            return bool(settings.farcaster.neynar_api_key)
        elif integration_type == 'matrix':
            return bool(settings.matrix.homeserver and 
                       settings.matrix.user_id and 
                       settings.matrix.password)
        return False
    
    async def remove_integration(self, integration_id: str) -> bool:
        """
        Remove an integration configuration completely.
        
        Args:
            integration_id: The integration ID to remove
            
        Returns:
            bool: True if removal was successful
        """
        try:
            # First disconnect if it's currently active
            if integration_id in self.active_integrations:
                await self.disconnect_integration(integration_id)
            
            # Remove from database (credentials will be removed due to CASCADE)
            async def db_operation(db):
                cursor = await db.execute("""
                    DELETE FROM integrations WHERE id = ?
                """, (integration_id,))
                await db.commit()
                return cursor.rowcount > 0
            
            removed = await self._execute_db_operation(db_operation)
            
            if removed:
                logger.info(f"Successfully removed integration {integration_id}")
                return True
            else:
                logger.warning(f"Integration {integration_id} not found for removal")
                return False
                
        except Exception as e:
            logger.error(f"Error removing integration {integration_id}: {e}")
            return False
        
    async def update_integration_config(
        self,
        integration_id: str,
        display_name: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        is_active: Optional[bool] = None
    ) -> bool:
        """
        Update an integration's configuration.
        
        Args:
            integration_id: The integration ID to update
            display_name: New display name (optional)
            config: New configuration data (optional)
            is_active: New active status (optional)
            
        Returns:
            bool: True if update was successful
        """
        try:
            updates = []
            params = []
            
            if display_name is not None:
                updates.append("display_name = ?")
                params.append(display_name)
                
            if config is not None:
                updates.append("config = ?")
                params.append(json.dumps(config))
                
            if is_active is not None:
                updates.append("is_active = ?")
                params.append(is_active)
                
            if not updates:
                logger.warning(f"No updates provided for integration {integration_id}")
                return False
                
            updates.append("updated_at = ?")
            params.append(time.time())
            params.append(integration_id)
            
            async def db_operation(db):
                cursor = await db.execute(f"""
                    UPDATE integrations 
                    SET {', '.join(updates)}
                    WHERE id = ?
                """, params)
                await db.commit()
                return cursor.rowcount > 0
            
            updated = await self._execute_db_operation(db_operation)
            
            if updated:
                logger.info(f"Successfully updated integration {integration_id}")
                
                # If the integration is currently active and we're deactivating it, disconnect
                if is_active is False and integration_id in self.active_integrations:
                    await self.disconnect_integration(integration_id)
                    
                return True
            else:
                logger.warning(f"Integration {integration_id} not found for update")
                return False
                
        except Exception as e:
            logger.error(f"Error updating integration {integration_id}: {e}")
            return False
    
    async def _get_env_credentials(self, integration_type: str) -> Dict[str, str]:
        """Get credentials from environment variables for the specified integration type"""
        
        credentials = {}
        
        if integration_type == 'farcaster':
            if settings.farcaster.neynar_api_key:
                credentials['api_key'] = settings.farcaster.neynar_api_key
            if settings.farcaster.bot_signer_uuid:
                credentials['signer_uuid'] = settings.farcaster.bot_signer_uuid
            if settings.farcaster.bot_fid:
                credentials['bot_fid'] = settings.farcaster.bot_fid
                
        elif integration_type == 'matrix':
            if settings.matrix.homeserver:
                credentials['homeserver'] = settings.matrix.homeserver
            if settings.matrix.user_id:
                credentials['user_id'] = settings.matrix.user_id
            if settings.matrix.password:
                credentials['password'] = settings.matrix.password
        
        return credentials
