#!/usr/bin/env python3
"""
Arweave Wallet Generator

This script generates a new Arweave wallet and saves it to a specified location.
Use this to create wallet files for the arweave-service.

Usage:
    python generate_wallet.py [output_path]
    
Example:
    python generate_wallet.py ./arweave_wallet_data/arweave_wallet.json
"""

import argparse
import json
import os
import sys

try:
    from arweave import Wallet
except ImportError:
    print("ERROR: arweave-python-client not installed.")
    print("Install it with: pip install arweave-python-client")
    sys.exit(1)

def generate_wallet(output_path: str) -> bool:
    """
    Generate a new Arweave wallet and save it to the specified path.
    
    Args:
        output_path: Path where the wallet JSON file should be saved
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Ensure the directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Generate a new wallet
        print("🔐 Generating new Arweave wallet...")
        
        # Create wallet with no parameters to generate a new one
        wallet = Wallet()
        
        # Get the wallet's JWK data
        jwk_data = wallet.jwk
        
        # Save the JWK data to the specified path
        print(f"💾 Saving wallet to: {output_path}")
        with open(output_path, 'w') as f:
            json.dump(jwk_data, f, indent=2)
        
        # Verify the wallet was saved correctly
        if os.path.exists(output_path):
            # Test loading the wallet to ensure it's valid
            test_wallet = Wallet(output_path)
            print("✅ Wallet generated successfully!")
            print(f"📍 Wallet Address: {test_wallet.address}")
            print(f"📁 Wallet File: {output_path}")
            print("")
            print("⚠️  IMPORTANT SECURITY NOTES:")
            print("   1. Back up this wallet file securely")
            print("   2. The wallet needs AR tokens to perform transactions")
            print("   3. Fund the wallet at: https://faucet.arweave.net (testnet) or buy AR tokens")
            print("   4. Keep the wallet file secure - anyone with access can spend your AR")
            return True
        else:
            print("❌ ERROR: Wallet file was not created")
            return False
            
    except Exception as e:
        print(f"❌ ERROR: Failed to generate wallet: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(
        description="Generate a new Arweave wallet for the arweave-service"
    )
    parser.add_argument(
        "output_path",
        nargs="?",
        default="./arweave_wallet_data/arweave_wallet.json",
        help="Output path for the wallet file (default: ./arweave_wallet_data/arweave_wallet.json)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing wallet file if it exists"
    )
    
    args = parser.parse_args()
    
    # Check if file already exists
    if os.path.exists(args.output_path) and not args.force:
        print(f"❌ ERROR: Wallet file already exists at {args.output_path}")
        print("Use --force to overwrite, or specify a different path")
        sys.exit(1)
    
    # Generate the wallet
    success = generate_wallet(args.output_path)
    
    if success:
        print("")
        print("🚀 Next steps:")
        print("   1. Fund the wallet with AR tokens")
        print("   2. Start the arweave-service with docker-compose up arweave-service")
        print("   3. Test uploads with the service API endpoints")
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
