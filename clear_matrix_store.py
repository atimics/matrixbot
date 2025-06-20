#!/usr/bin/env python3
"""
Clear Matrix Store Script

This script safely clears the Matrix encryption store and token to fix
Megolm decryption errors and start with a fresh session.
"""

import os
import shutil
from pathlib import Path

def clear_matrix_store():
    """Clear Matrix store and token files."""
    print("🔧 Clearing Matrix encryption store...")
    
    # Matrix store directory
    matrix_store_path = Path("matrix_store")
    if matrix_store_path.exists():
        print(f"📁 Removing {matrix_store_path}")
        shutil.rmtree(matrix_store_path)
        print("✅ Matrix store directory removed")
    else:
        print("ℹ️  Matrix store directory doesn't exist")
    
    # Matrix token file
    token_file = Path("matrix_token.json")
    if token_file.exists():
        print(f"📄 Removing {token_file}")
        token_file.unlink()
        print("✅ Matrix token file removed")
    else:
        print("ℹ️  Matrix token file doesn't exist")
    
    # Data directory token file (alternative location)
    data_token_file = Path("data/matrix_token.json")
    if data_token_file.exists():
        print(f"📄 Removing {data_token_file}")
        data_token_file.unlink()
        print("✅ Data directory token file removed")
    else:
        print("ℹ️  Data directory token file doesn't exist")
    
    print("🎉 Matrix store cleared successfully!")
    print()
    print("📋 Next steps:")
    print("1. Restart the chatbot - it will create a fresh Matrix session")
    print("2. In your Matrix client, verify the new bot session in encrypted rooms")
    print("3. This will resolve Megolm decryption errors")

if __name__ == "__main__":
    clear_matrix_store()
