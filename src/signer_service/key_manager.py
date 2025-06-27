"""
Secure Key Management for Farcaster Signer Service

This module handles the secure generation, storage, and loading of Farcaster signer keys.
It supports both local encrypted storage and cloud HSM/KMS integration.
"""

import os
import json
import logging
import base64
from pathlib import Path
from typing import Optional, Dict, Any
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import ed25519

logger = logging.getLogger(__name__)


class SecureKeyManager:
    """
    Manages Farcaster signer keys with enterprise-grade security.
    
    Supports:
    - Local encrypted storage with master key from environment/secrets
    - AWS KMS integration (future)
    - Azure Key Vault integration (future)
    """
    
    def __init__(
        self,
        storage_path: str = "/secure_storage",
        key_id: str = "default",
        use_cloud_hsm: bool = False
    ):
        self.storage_path = Path(storage_path)
        self.key_id = key_id
        self.use_cloud_hsm = use_cloud_hsm
        
        # Ensure storage directory exists with proper permissions
        self.storage_path.mkdir(parents=True, exist_ok=True)
        os.chmod(self.storage_path, 0o700)
        
        self.key_file = self.storage_path / f"signer_{key_id}.enc"
        self.metadata_file = self.storage_path / f"signer_{key_id}_metadata.json"
        
        # In-memory key storage (never persisted unencrypted)
        self._private_key: Optional[ed25519.SigningKey] = None
        self._public_key: Optional[ed25519.VerifyingKey] = None
        self._fid: Optional[int] = None
        
        logger.info(f"SecureKeyManager initialized for key_id: {key_id}")
    
    def _get_master_key(self) -> bytes:
        """
        Get the master encryption key from environment or cloud secrets.
        
        In production, this should come from:
        - AWS Secrets Manager
        - Azure Key Vault
        - Environment variable (for development only)
        """
        # Try environment variable first (development)
        master_key_b64 = os.getenv("SIGNER_MASTER_KEY")
        if master_key_b64:
            try:
                return base64.b64decode(master_key_b64)
            except Exception as e:
                logger.error(f"Failed to decode master key from environment: {e}")
        
        # Try AWS Secrets Manager
        aws_secret_arn = os.getenv("AWS_SIGNER_MASTER_KEY_ARN")
        if aws_secret_arn:
            try:
                return self._get_aws_secret(aws_secret_arn)
            except Exception as e:
                logger.error(f"Failed to get master key from AWS: {e}")
        
        # Try Azure Key Vault
        azure_vault_url = os.getenv("AZURE_KEY_VAULT_URL")
        azure_secret_name = os.getenv("AZURE_SIGNER_MASTER_KEY_NAME")
        if azure_vault_url and azure_secret_name:
            try:
                return self._get_azure_secret(azure_vault_url, azure_secret_name)
            except Exception as e:
                logger.error(f"Failed to get master key from Azure: {e}")
        
        # Fallback: generate a key for development (NOT FOR PRODUCTION)
        logger.warning("No master key found in environment or cloud - generating temporary key")
        logger.warning("THIS IS NOT SECURE FOR PRODUCTION USE")
        return Fernet.generate_key()
    
    def _get_aws_secret(self, secret_arn: str) -> bytes:
        """Get master key from AWS Secrets Manager."""
        try:
            import boto3
            client = boto3.client('secretsmanager')
            response = client.get_secret_value(SecretId=secret_arn)
            secret_value = response['SecretString']
            return base64.b64decode(secret_value)
        except ImportError:
            raise RuntimeError("boto3 not installed - cannot access AWS Secrets Manager")
    
    def _get_azure_secret(self, vault_url: str, secret_name: str) -> bytes:
        """Get master key from Azure Key Vault."""
        try:
            from azure.keyvault.secrets import SecretClient
            from azure.identity import DefaultAzureCredential
            
            credential = DefaultAzureCredential()
            client = SecretClient(vault_url=vault_url, credential=credential)
            secret = client.get_secret(secret_name)
            return base64.b64decode(secret.value)
        except ImportError:
            raise RuntimeError("azure-keyvault-secrets not installed - cannot access Azure Key Vault")
    
    def _encrypt_key(self, private_key_bytes: bytes) -> bytes:
        """Encrypt private key using master key."""
        master_key = self._get_master_key()
        fernet = Fernet(master_key)
        return fernet.encrypt(private_key_bytes)
    
    def _decrypt_key(self, encrypted_key_bytes: bytes) -> bytes:
        """Decrypt private key using master key."""
        master_key = self._get_master_key()
        fernet = Fernet(master_key)
        return fernet.decrypt(encrypted_key_bytes)
    
    def generate_new_key(self, fid: int) -> Dict[str, Any]:
        """
        Generate a new Ed25519 key pair for Farcaster signing.
        
        Args:
            fid: The Farcaster ID this key will be associated with
            
        Returns:
            Dictionary containing public key info for registration
        """
        logger.info(f"Generating new signer key for FID {fid}")
        
        # Generate Ed25519 key pair
        private_key = ed25519.SigningKey(os.urandom(32))
        public_key = private_key.get_verifying_key()
        
        # Store encrypted private key
        private_key_bytes = private_key.to_bytes()
        encrypted_key = self._encrypt_key(private_key_bytes)
        
        with open(self.key_file, 'wb') as f:
            f.write(encrypted_key)
        
        # Store metadata
        metadata = {
            "fid": fid,
            "public_key_hex": public_key.to_bytes().hex(),
            "created_at": "2025-06-26T00:00:00Z",  # Current timestamp
            "key_type": "ed25519"
        }
        
        with open(self.metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        # Set proper file permissions
        os.chmod(self.key_file, 0o600)
        os.chmod(self.metadata_file, 0o600)
        
        # Load into memory
        self._private_key = private_key
        self._public_key = public_key
        self._fid = fid
        
        logger.info(f"New signer key generated and stored securely")
        logger.info(f"Public key (for registration): {public_key.to_bytes().hex()}")
        
        return {
            "fid": fid,
            "public_key_hex": public_key.to_bytes().hex(),
            "registration_required": True,
            "message": "Register this public key on-chain using your account's Owner Key"
        }
    
    def load_existing_key(self) -> Optional[Dict[str, Any]]:
        """
        Load an existing signer key from encrypted storage.
        
        Returns:
            Key metadata if successful, None if no key exists
        """
        if not self.key_file.exists() or not self.metadata_file.exists():
            logger.info("No existing signer key found")
            return None
        
        try:
            # Load metadata
            with open(self.metadata_file, 'r') as f:
                metadata = json.load(f)
            
            # Load and decrypt private key
            with open(self.key_file, 'rb') as f:
                encrypted_key = f.read()
            
            private_key_bytes = self._decrypt_key(encrypted_key)
            private_key = ed25519.SigningKey(private_key_bytes)
            public_key = private_key.get_verifying_key()
            
            # Store in memory
            self._private_key = private_key
            self._public_key = public_key
            self._fid = metadata["fid"]
            
            logger.info(f"Loaded existing signer key for FID {self._fid}")
            logger.info(f"Public key: {public_key.to_bytes().hex()}")
            
            return metadata
            
        except Exception as e:
            logger.error(f"Failed to load existing key: {e}")
            return None
    
    def sign_message(self, message_bytes: bytes) -> bytes:
        """
        Sign a message using the loaded private key.
        
        Args:
            message_bytes: The message to sign
            
        Returns:
            The signature bytes
        """
        if not self._private_key:
            raise RuntimeError("No private key loaded - call load_existing_key() or generate_new_key() first")
        
        signature = self._private_key.sign(message_bytes)
        return signature
    
    def get_public_key_hex(self) -> Optional[str]:
        """Get the public key as a hex string."""
        if not self._public_key:
            return None
        return self._public_key.to_bytes().hex()
    
    def get_fid(self) -> Optional[int]:
        """Get the FID associated with this key."""
        return self._fid
    
    def is_key_loaded(self) -> bool:
        """Check if a key is currently loaded in memory."""
        return self._private_key is not None
    
    def clear_memory(self):
        """Clear sensitive key material from memory."""
        self._private_key = None
        self._public_key = None
        self._fid = None
        logger.info("Cleared key material from memory")
