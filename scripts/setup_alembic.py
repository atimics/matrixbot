#!/usr/bin/env python3
"""
Alembic Setup Script for PostgreSQL Schema Management

This script initializes Alembic for managing database schema migrations
in the PostgreSQL environment. It creates the necessary configuration
and sets up the initial migration environment.

Usage:
    python scripts/setup_alembic.py
"""

import sys
from pathlib import Path

# Add the project root to the Python path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def setup_alembic():
    """Initialize Alembic for schema management."""
    import subprocess
    import os
    from chatbot.config import settings
    
    print("Setting up Alembic for PostgreSQL schema management...")
    
    # Change to project root directory
    os.chdir(project_root)
    
    try:
        # Initialize Alembic
        print("Initializing Alembic...")
        subprocess.run(["poetry", "run", "alembic", "init", "alembic"], check=True)
        
        # Update alembic.ini with PostgreSQL DSN
        alembic_ini_path = project_root / "alembic.ini"
        if alembic_ini_path.exists():
            print("Updating alembic.ini with PostgreSQL connection...")
            
            with open(alembic_ini_path, 'r') as f:
                content = f.read()
            
            # Replace the sqlalchemy.url line
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if line.startswith('sqlalchemy.url'):
                    lines[i] = f"sqlalchemy.url = {settings.postgres.dsn}"
                    break
            
            with open(alembic_ini_path, 'w') as f:
                f.write('\n'.join(lines))
            
            print("✅ Updated alembic.ini")
        
        # Update alembic/env.py to import our models
        env_py_path = project_root / "alembic" / "env.py"
        if env_py_path.exists():
            print("Updating alembic/env.py...")
            
            with open(env_py_path, 'r') as f:
                content = f.read()
            
            # Add imports and target_metadata
            imports_to_add = """
# Import your models here for autogenerate support
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from chatbot.core.persistence import DatabaseManager
"""
            
            # Find the target_metadata line and replace it
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if 'target_metadata = None' in line:
                    lines[i] = "target_metadata = None  # We'll manage schema manually for now"
                    break
                elif 'import os' in line:
                    lines[i] = line + imports_to_add
            
            with open(env_py_path, 'w') as f:
                f.write('\n'.join(lines))
            
            print("✅ Updated alembic/env.py")
        
        print("\n🎉 Alembic setup completed successfully!")
        print("\nNext steps:")
        print("1. Create your first migration: poetry run alembic revision -m 'Initial migration'")
        print("2. Apply migrations: poetry run alembic upgrade head")
        print("3. For future schema changes: poetry run alembic revision --autogenerate -m 'Description'")
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Error setting up Alembic: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    setup_alembic()
