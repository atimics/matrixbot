#!/usr/bin/env python3
"""
Generate a secure master key for the Farcaster Signer Service

This script generates a cryptographically secure master key that can be used
to encrypt signer private keys at rest.
"""

import os
import base64
from cryptography.fernet import Fernet

def generate_master_key():
    """Generate a new Fernet-compatible master key."""
    key = Fernet.generate_key()
    return key.decode('utf-8')

def main():
    print("🔐 Farcaster Signer Service - Master Key Generator")
    print("=" * 60)
    print()
    
    # Generate the key
    master_key = generate_master_key()
    
    print("✅ Generated secure master key:")
    print(f"   {master_key}")
    print()
    
    print("📝 Add this to your .env file:")
    print(f"   SIGNER_MASTER_KEY={master_key}")
    print()
    
    print("🚨 SECURITY WARNINGS:")
    print("   1. Keep this key secret and secure")
    print("   2. For production, use AWS KMS or Azure Key Vault instead")
    print("   3. If you lose this key, you'll lose access to your signer keys")
    print("   4. Never commit this key to version control")
    print()
    
    print("🏭 For production environments:")
    print("   - Use AWS Secrets Manager or Azure Key Vault")
    print("   - Set USE_CLOUD_HSM=true in your environment")
    print("   - Configure appropriate IAM/RBAC permissions")

if __name__ == "__main__":
    main()
