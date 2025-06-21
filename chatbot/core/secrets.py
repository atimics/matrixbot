"""
Secure Secret Management System

Implements secure handling of API keys, passwords, and other sensitive configuration
as recommended in the engineering report. Supports multiple backends including
environment variables, HashiCorp Vault, and local encrypted storage.
"""

import os
import json
import base64
import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, Union
from pathlib import Path
from dataclasses import dataclass
from enum import Enum

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from chatbot.exceptions import ConfigurationError

logger = logging.getLogger(__name__)


class SecretBackend(Enum):
    """Supported secret management backends."""
    ENVIRONMENT = "environment"
    VAULT = "vault"
    ENCRYPTED_FILE = "encrypted_file"
    KUBERNETES = "kubernetes"


@dataclass
class SecretConfig:
    """Configuration for secret management."""
    backend: SecretBackend = SecretBackend.ENVIRONMENT
    vault_url: Optional[str] = None
    vault_token: Optional[str] = None
    vault_path: str = "secret/ratichat"
    secrets_file: str = "data/secrets.enc"
    master_password: Optional[str] = None


class SecretProvider(ABC):
    """Abstract base class for secret providers."""
    
    @abstractmethod
    async def get_secret(self, key: str) -> Optional[str]:
        """Get a secret value by key."""
        pass
    
    @abstractmethod
    async def set_secret(self, key: str, value: str) -> bool:
        """Set a secret value."""
        pass
    
    @abstractmethod
    async def delete_secret(self, key: str) -> bool:
        """Delete a secret."""
        pass
    
    @abstractmethod
    async def list_secrets(self) -> list[str]:
        """List available secret keys."""
        pass


class EnvironmentSecretProvider(SecretProvider):
    """Environment variable-based secret provider."""
    
    async def get_secret(self, key: str) -> Optional[str]:
        """Get secret from environment variable."""
        return os.getenv(key)
    
    async def set_secret(self, key: str, value: str) -> bool:
        """Set environment variable (in-memory only)."""
        os.environ[key] = value
        return True
    
    async def delete_secret(self, key: str) -> bool:
        """Delete environment variable."""
        if key in os.environ:
            del os.environ[key]
            return True
        return False
    
    async def list_secrets(self) -> list[str]:
        """List environment variables that look like secrets."""
        secret_patterns = ["_API_KEY", "_TOKEN", "_PASSWORD", "_SECRET"]
        return [key for key in os.environ.keys() 
                if any(pattern in key.upper() for pattern in secret_patterns)]


class EncryptedFileSecretProvider(SecretProvider):
    """Encrypted file-based secret provider."""
    
    def __init__(self, config: SecretConfig):
        self.config = config
        self._fernet = None
        self._secrets_cache = {}
    
    async def _get_fernet(self) -> Fernet:
        """Get or create Fernet cipher instance."""
        if self._fernet is None:
            key = await self._load_or_create_key()
            self._fernet = Fernet(key)
        return self._fernet

    async def _load_or_create_key(self) -> bytes:
        """Load encryption key from environment variable."""
        env_key = os.getenv("RATICHAT_ENCRYPTION_KEY")
        if not env_key:
            raise ConfigurationError(
                "FATAL: The RATICHAT_ENCRYPTION_KEY environment variable is not set. "
                "The application cannot start without it. Please generate a key and set it.\n"
                "Generate a new key with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
            )
        try:
            # The key in the environment should be Base64 encoded for safety
            return base64.b64decode(env_key)
        except Exception as e:
            raise ConfigurationError(f"Invalid RATICHAT_ENCRYPTION_KEY format: {e}. It must be a valid Base64 encoded string.")

    async def _load_secrets(self) -> Dict[str, str]:
        """Load and decrypt secrets from file."""
        if self._secrets_cache:
            return self._secrets_cache
        
        secrets_file = Path(self.config.secrets_file)
        if not secrets_file.exists():
            return {}
        
        try:
            fernet = await self._get_fernet()
            
            with open(secrets_file, 'rb') as f:
                encrypted_data = f.read()
            
            decrypted_data = fernet.decrypt(encrypted_data)
            secrets = json.loads(decrypted_data.decode())
            
            self._secrets_cache = secrets
            return secrets
            
        except Exception as e:
            logger.error(f"Failed to load secrets: {e}")
            return {}
    
    async def _save_secrets(self, secrets: Dict[str, str]) -> bool:
        """Encrypt and save secrets to file."""
        try:
            fernet = await self._get_fernet()
            
            # Serialize and encrypt
            data = json.dumps(secrets).encode()
            encrypted_data = fernet.encrypt(data)
            
            # Ensure directory exists
            secrets_file = Path(self.config.secrets_file)
            secrets_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Write encrypted data
            with open(secrets_file, 'wb') as f:
                f.write(encrypted_data)
            
            # Set restrictive permissions
            secrets_file.chmod(0o600)
            
            # Update cache
            self._secrets_cache = secrets
            return True
            
        except Exception as e:
            logger.error(f"Failed to save secrets: {e}")
            return False
    
    async def get_secret(self, key: str) -> Optional[str]:
        """Get secret from encrypted file."""
        secrets = await self._load_secrets()
        return secrets.get(key)
    
    async def set_secret(self, key: str, value: str) -> bool:
        """Set secret in encrypted file."""
        secrets = await self._load_secrets()
        secrets[key] = value
        return await self._save_secrets(secrets)
    
    async def delete_secret(self, key: str) -> bool:
        """Delete secret from encrypted file."""
        secrets = await self._load_secrets()
        if key in secrets:
            del secrets[key]
            return await self._save_secrets(secrets)
        return False
    
    async def list_secrets(self) -> list[str]:
        """List secret keys."""
        secrets = await self._load_secrets()
        return list(secrets.keys())


class VaultSecretProvider(SecretProvider):
    """HashiCorp Vault secret provider."""
    
    def __init__(self, config: SecretConfig):
        self.config = config
        self._client = None
    
    async def _get_client(self):
        """Get or create Vault client."""
        if self._client is None:
            try:
                import hvac
                self._client = hvac.Client(
                    url=self.config.vault_url,
                    token=self.config.vault_token
                )
            except ImportError:
                raise ImportError("hvac library required for Vault support")
        return self._client
    
    async def get_secret(self, key: str) -> Optional[str]:
        """Get secret from Vault."""
        try:
            client = await self._get_client()
            response = client.secrets.kv.v2.read_secret_version(
                path=self.config.vault_path
            )
            data = response['data']['data']
            return data.get(key)
        except Exception as e:
            logger.error(f"Failed to get secret from Vault: {e}")
            return None
    
    async def set_secret(self, key: str, value: str) -> bool:
        """Set secret in Vault."""
        try:
            client = await self._get_client()
            
            # Get existing secrets
            try:
                response = client.secrets.kv.v2.read_secret_version(
                    path=self.config.vault_path
                )
                existing_data = response['data']['data']
            except:
                existing_data = {}
            
            # Update with new secret
            existing_data[key] = value
            
            # Write back to Vault
            client.secrets.kv.v2.create_or_update_secret(
                path=self.config.vault_path,
                secret=existing_data
            )
            return True
            
        except Exception as e:
            logger.error(f"Failed to set secret in Vault: {e}")
            return False
    
    async def delete_secret(self, key: str) -> bool:
        """Delete secret from Vault."""
        try:
            client = await self._get_client()
            
            # Get existing secrets
            response = client.secrets.kv.v2.read_secret_version(
                path=self.config.vault_path
            )
            existing_data = response['data']['data']
            
            if key in existing_data:
                del existing_data[key]
                
                # Write back to Vault
                client.secrets.kv.v2.create_or_update_secret(
                    path=self.config.vault_path,
                    secret=existing_data
                )
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to delete secret from Vault: {e}")
            return False
    
    async def list_secrets(self) -> list[str]:
        """List secret keys in Vault."""
        try:
            client = await self._get_client()
            response = client.secrets.kv.v2.read_secret_version(
                path=self.config.vault_path
            )
            data = response['data']['data']
            return list(data.keys())
        except Exception as e:
            logger.error(f"Failed to list secrets from Vault: {e}")
            return []


class SecretManager:
    """Main secret management interface."""
    
    def __init__(self, config: Optional[SecretConfig] = None):
        self.config = config or SecretConfig()
        self._provider = None
    
    async def _get_provider(self) -> SecretProvider:
        """Get the configured secret provider."""
        if self._provider is None:
            if self.config.backend == SecretBackend.ENVIRONMENT:
                self._provider = EnvironmentSecretProvider()
            elif self.config.backend == SecretBackend.ENCRYPTED_FILE:
                self._provider = EncryptedFileSecretProvider(self.config)
            elif self.config.backend == SecretBackend.VAULT:
                self._provider = VaultSecretProvider(self.config)
            else:
                raise ValueError(f"Unsupported secret backend: {self.config.backend}")
        
        return self._provider
    
    async def get_secret(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get a secret value."""
        provider = await self._get_provider()
        value = await provider.get_secret(key)
        return value if value is not None else default
    
    async def set_secret(self, key: str, value: str) -> bool:
        """Set a secret value."""
        provider = await self._get_provider()
        return await provider.set_secret(key, value)
    
    async def delete_secret(self, key: str) -> bool:
        """Delete a secret."""
        provider = await self._get_provider()
        return await provider.delete_secret(key)
    
    async def list_secrets(self) -> list[str]:
        """List available secrets."""
        provider = await self._get_provider()
        return await provider.list_secrets()
    
    async def get_required_secret(self, key: str) -> str:
        """Get a required secret, raising an error if not found."""
        value = await self.get_secret(key)
        if value is None:
            raise ValueError(f"Required secret '{key}' not found")
        return value
    
    async def migrate_secrets(self, from_backend: SecretBackend, to_backend: SecretBackend):
        """Migrate secrets from one backend to another."""
        # Create temporary configs for migration
        from_config = SecretConfig(backend=from_backend)
        to_config = SecretConfig(backend=to_backend)
        
        # Create providers
        from_manager = SecretManager(from_config)
        to_manager = SecretManager(to_config)
        
        # Get all secrets from source
        from_provider = await from_manager._get_provider()
        to_provider = await to_manager._get_provider()
        
        secret_keys = await from_provider.list_secrets()
        
        # Migrate each secret
        migrated = 0
        for key in secret_keys:
            value = await from_provider.get_secret(key)
            if value is not None:
                success = await to_provider.set_secret(key, value)
                if success:
                    migrated += 1
                    logger.debug(f"Migrated secret: {key}")
                else:
                    logger.error(f"Failed to migrate secret: {key}")
        
        logger.debug(f"Migrated {migrated}/{len(secret_keys)} secrets")
        return migrated
    
    def create_fernet_key(self) -> str:
        """Create a new Fernet encryption key."""
        key = Fernet.generate_key()
        return key.decode()
    
    async def validate_configuration(self) -> Dict[str, Any]:
        """Validate secret manager configuration."""
        status = {
            "backend": self.config.backend.value,
            "accessible": False,
            "secret_count": 0,
            "errors": []
        }
        
        try:
            provider = await self._get_provider()
            secrets = await provider.list_secrets()
            status["accessible"] = True
            status["secret_count"] = len(secrets)
        except Exception as e:
            status["errors"].append(str(e))
        
        return status


# Global secret manager instance
_secret_manager = None


def get_secret_manager(config: Optional[SecretConfig] = None) -> SecretManager:
    """Get the global secret manager instance."""
    global _secret_manager
    if _secret_manager is None:
        _secret_manager = SecretManager(config)
    return _secret_manager


async def init_secret_manager(config: Optional[SecretConfig] = None):
    """Initialize the global secret manager."""
    global _secret_manager
    _secret_manager = SecretManager(config)
    
    # Validate configuration
    status = await _secret_manager.validate_configuration()
    if not status["accessible"]:
        logger.warning(f"Secret manager not accessible: {status['errors']}")
    else:
        logger.debug(f"Secret manager initialized with {status['secret_count']} secrets")


# Convenience functions
async def get_secret(key: str, default: Optional[str] = None) -> Optional[str]:
    """Get a secret using the global secret manager."""
    manager = get_secret_manager()
    return await manager.get_secret(key, default)


async def set_secret(key: str, value: str) -> bool:
    """Set a secret using the global secret manager."""
    manager = get_secret_manager()
    return await manager.set_secret(key, value)
