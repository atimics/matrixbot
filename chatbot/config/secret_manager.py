"""
Secure Secret Management System

This module provides secure handling of sensitive configuration values
like API keys, passwords, and tokens. It supports multiple backends
including environment variables, HashiCorp Vault, and AWS Secrets Manager.
"""

import os
import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Optional, Any, List
from dataclasses import dataclass
from enum import Enum
from cryptography.fernet import Fernet
import base64

logger = logging.getLogger(__name__)


class SecretBackend(Enum):
    """Available secret management backends."""
    ENVIRONMENT = "environment"
    VAULT = "vault"
    AWS_SECRETS = "aws_secrets"
    LOCAL_ENCRYPTED = "local_encrypted"


@dataclass
class SecretConfig:
    """Configuration for secret management."""
    backend: SecretBackend
    vault_url: Optional[str] = None
    vault_token: Optional[str] = None
    aws_region: Optional[str] = None
    encryption_key_path: Optional[str] = None
    local_secrets_path: Optional[str] = None


class SecretProviderInterface(ABC):
    """Interface for secret providers."""
    
    @abstractmethod
    async def get_secret(self, key: str) -> Optional[str]:
        """Get a secret value by key."""
        pass
    
    @abstractmethod
    async def set_secret(self, key: str, value: str) -> bool:
        """Set a secret value."""
        pass
    
    @abstractmethod
    async def list_secrets(self) -> List[str]:
        """List available secret keys."""
        pass
    
    @abstractmethod
    async def delete_secret(self, key: str) -> bool:
        """Delete a secret."""
        pass


class EnvironmentSecretProvider(SecretProviderInterface):
    """Secret provider using environment variables."""
    
    async def get_secret(self, key: str) -> Optional[str]:
        """Get secret from environment variable."""
        return os.getenv(key)
    
    async def set_secret(self, key: str, value: str) -> bool:
        """Set environment variable (not persistent)."""
        os.environ[key] = value
        return True
    
    async def list_secrets(self) -> List[str]:
        """List environment variables (filtered by common secret patterns)."""
        secret_patterns = ['KEY', 'TOKEN', 'SECRET', 'PASSWORD', 'API']
        return [
            key for key in os.environ.keys()
            if any(pattern in key.upper() for pattern in secret_patterns)
        ]
    
    async def delete_secret(self, key: str) -> bool:
        """Delete environment variable."""
        if key in os.environ:
            del os.environ[key]
            return True
        return False


class LocalEncryptedSecretProvider(SecretProviderInterface):
    """Secret provider using local encrypted file storage."""
    
    def __init__(self, secrets_path: str, encryption_key_path: str):
        self.secrets_path = Path(secrets_path)
        self.encryption_key_path = Path(encryption_key_path)
        self._fernet = None
        self._ensure_setup()
    
    def _ensure_setup(self):
        """Ensure encryption key and secrets file exist."""
        # Create directories
        self.secrets_path.parent.mkdir(parents=True, exist_ok=True)
        self.encryption_key_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Generate encryption key if it doesn't exist
        if not self.encryption_key_path.exists():
            key = Fernet.generate_key()
            with open(self.encryption_key_path, 'wb') as f:
                f.write(key)
            os.chmod(self.encryption_key_path, 0o600)  # Read-only for owner
            logger.info(f"Generated new encryption key at {self.encryption_key_path}")
        
        # Load encryption key
        with open(self.encryption_key_path, 'rb') as f:
            key = f.read()
        self._fernet = Fernet(key)
        
        # Create empty secrets file if it doesn't exist
        if not self.secrets_path.exists():
            self._save_secrets({})
    
    def _load_secrets(self) -> Dict[str, str]:
        """Load and decrypt secrets from file."""
        if not self.secrets_path.exists():
            return {}
        
        try:
            with open(self.secrets_path, 'rb') as f:
                encrypted_data = f.read()
            
            if not encrypted_data:
                return {}
            
            decrypted_data = self._fernet.decrypt(encrypted_data)
            return json.loads(decrypted_data.decode())
        except Exception as e:
            logger.error(f"Failed to load secrets: {e}")
            return {}
    
    def _save_secrets(self, secrets: Dict[str, str]):
        """Encrypt and save secrets to file."""
        try:
            data = json.dumps(secrets).encode()
            encrypted_data = self._fernet.encrypt(data)
            
            with open(self.secrets_path, 'wb') as f:
                f.write(encrypted_data)
            
            os.chmod(self.secrets_path, 0o600)  # Read-only for owner
        except Exception as e:
            logger.error(f"Failed to save secrets: {e}")
            raise
    
    async def get_secret(self, key: str) -> Optional[str]:
        """Get decrypted secret by key."""
        secrets = self._load_secrets()
        return secrets.get(key)
    
    async def set_secret(self, key: str, value: str) -> bool:
        """Encrypt and store secret."""
        try:
            secrets = self._load_secrets()
            secrets[key] = value
            self._save_secrets(secrets)
            return True
        except Exception as e:
            logger.error(f"Failed to set secret {key}: {e}")
            return False
    
    async def list_secrets(self) -> List[str]:
        """List available secret keys."""
        secrets = self._load_secrets()
        return list(secrets.keys())
    
    async def delete_secret(self, key: str) -> bool:
        """Delete secret."""
        try:
            secrets = self._load_secrets()
            if key in secrets:
                del secrets[key]
                self._save_secrets(secrets)
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to delete secret {key}: {e}")
            return False


class VaultSecretProvider(SecretProviderInterface):
    """Secret provider using HashiCorp Vault."""
    
    def __init__(self, vault_url: str, vault_token: str, mount_path: str = "secret"):
        self.vault_url = vault_url.rstrip('/')
        self.vault_token = vault_token
        self.mount_path = mount_path
        self._client = None
    
    async def _get_client(self):
        """Get or create Vault client."""
        if self._client is None:
            try:
                import hvac
                self._client = hvac.Client(url=self.vault_url, token=self.vault_token)
                if not self._client.is_authenticated():
                    raise Exception("Vault authentication failed")
            except ImportError:
                raise Exception("hvac library required for Vault integration. Install with: pip install hvac")
        return self._client
    
    async def get_secret(self, key: str) -> Optional[str]:
        """Get secret from Vault."""
        try:
            client = await self._get_client()
            response = client.secrets.kv.v2.read_secret_version(
                path=key,
                mount_point=self.mount_path
            )
            return response['data']['data'].get('value')
        except Exception as e:
            logger.error(f"Failed to get secret {key} from Vault: {e}")
            return None
    
    async def set_secret(self, key: str, value: str) -> bool:
        """Set secret in Vault."""
        try:
            client = await self._get_client()
            client.secrets.kv.v2.create_or_update_secret(
                path=key,
                secret={'value': value},
                mount_point=self.mount_path
            )
            return True
        except Exception as e:
            logger.error(f"Failed to set secret {key} in Vault: {e}")
            return False
    
    async def list_secrets(self) -> List[str]:
        """List secrets in Vault."""
        try:
            client = await self._get_client()
            response = client.secrets.kv.v2.list_secrets(
                path='',
                mount_point=self.mount_path
            )
            return response['data']['keys']
        except Exception as e:
            logger.error(f"Failed to list secrets from Vault: {e}")
            return []
    
    async def delete_secret(self, key: str) -> bool:
        """Delete secret from Vault."""
        try:
            client = await self._get_client()
            client.secrets.kv.v2.delete_metadata_and_all_versions(
                path=key,
                mount_point=self.mount_path
            )
            return True
        except Exception as e:
            logger.error(f"Failed to delete secret {key} from Vault: {e}")
            return False


class SecretManager:
    """Main secret management interface."""
    
    def __init__(self, config: SecretConfig):
        self.config = config
        self.provider = self._create_provider()
    
    def _create_provider(self) -> SecretProviderInterface:
        """Create secret provider based on configuration."""
        if self.config.backend == SecretBackend.ENVIRONMENT:
            return EnvironmentSecretProvider()
        
        elif self.config.backend == SecretBackend.LOCAL_ENCRYPTED:
            secrets_path = self.config.local_secrets_path or "data/secrets.enc"
            key_path = self.config.encryption_key_path or "data/secrets.key"
            return LocalEncryptedSecretProvider(secrets_path, key_path)
        
        elif self.config.backend == SecretBackend.VAULT:
            if not self.config.vault_url or not self.config.vault_token:
                raise ValueError("Vault URL and token required for Vault backend")
            return VaultSecretProvider(self.config.vault_url, self.config.vault_token)
        
        else:
            raise ValueError(f"Unsupported secret backend: {self.config.backend}")
    
    async def get_secret(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get secret with optional default value."""
        value = await self.provider.get_secret(key)
        return value if value is not None else default
    
    async def set_secret(self, key: str, value: str) -> bool:
        """Set secret value."""
        return await self.provider.set_secret(key, value)
    
    async def get_multiple_secrets(self, keys: List[str]) -> Dict[str, Optional[str]]:
        """Get multiple secrets efficiently."""
        result = {}
        for key in keys:
            result[key] = await self.provider.get_secret(key)
        return result
    
    async def list_secrets(self) -> List[str]:
        """List available secrets."""
        return await self.provider.list_secrets()
    
    async def delete_secret(self, key: str) -> bool:
        """Delete secret."""
        return await self.provider.delete_secret(key)
    
    async def rotate_secret(self, key: str, new_value: str) -> bool:
        """Rotate secret value (set new value and optionally backup old)."""
        # Could be extended to backup old values
        return await self.provider.set_secret(key, new_value)
    
    def get_backend_info(self) -> Dict[str, Any]:
        """Get information about the current backend."""
        return {
            "backend": self.config.backend.value,
            "provider_type": type(self.provider).__name__,
            "vault_url": self.config.vault_url if self.config.backend == SecretBackend.VAULT else None,
            "local_path": self.config.local_secrets_path if self.config.backend == SecretBackend.LOCAL_ENCRYPTED else None
        }


def create_secret_manager() -> SecretManager:
    """Create secret manager based on environment configuration."""
    # Determine backend from environment
    backend_str = os.getenv("SECRET_BACKEND", "environment").lower()
    
    if backend_str == "local_encrypted":
        backend = SecretBackend.LOCAL_ENCRYPTED
    elif backend_str == "vault":
        backend = SecretBackend.VAULT
    else:
        backend = SecretBackend.ENVIRONMENT
    
    config = SecretConfig(
        backend=backend,
        vault_url=os.getenv("VAULT_URL"),
        vault_token=os.getenv("VAULT_TOKEN"),
        aws_region=os.getenv("AWS_REGION"),
        encryption_key_path=os.getenv("SECRET_ENCRYPTION_KEY_PATH"),
        local_secrets_path=os.getenv("LOCAL_SECRETS_PATH")
    )
    
    return SecretManager(config)


# Global secret manager instance
secret_manager = create_secret_manager()
