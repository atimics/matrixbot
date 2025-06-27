#!/usr/bin/env python3
"""
SQLite to PostgreSQL Migration Script

This script migrates data from the existing SQLite database to the new PostgreSQL database.
It handles data transformation, type conversion, and ensures data integrity during the migration.

Usage:
    python scripts/migrate_sqlite_to_pg.py [--dry-run] [--backup-dir /path/to/backup]

Features:
    - Backs up existing SQLite database before migration
    - Transforms SQLite data types to PostgreSQL equivalents
    - Handles JSON data conversion from TEXT to JSONB
    - Provides detailed logging and progress tracking
    - Supports dry-run mode for testing
    - Validates data integrity after migration
"""

import asyncio
import json
import logging
import shutil
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

import psycopg

# Add the project root to the Python path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from chatbot.config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('migration.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class SQLiteToPostgresMigrator:
    """Handles migration from SQLite to PostgreSQL."""
    
    def __init__(self, sqlite_path: str, dry_run: bool = False, backup_dir: Optional[str] = None):
        self.sqlite_path = sqlite_path
        # Use external DSN for migration scripts running outside Docker
        self.postgres_dsn = settings.postgres.external_dsn
        self.dry_run = dry_run
        self.backup_dir = backup_dir
        self.migration_stats = {
            'tables_migrated': 0,
            'total_rows_migrated': 0,
            'start_time': None,
            'end_time': None
        }
    
    async def migrate(self) -> bool:
        """Execute the complete migration process."""
        try:
            logger.info("Starting SQLite to PostgreSQL migration...")
            self.migration_stats['start_time'] = datetime.now()
            
            # Step 1: Backup existing database
            if not self.dry_run:
                await self._backup_database()
            
            # Step 2: Verify PostgreSQL connection
            await self._verify_postgres_connection()
            
            # Step 3: Get table schemas and data from SQLite
            tables_data = await self._extract_sqlite_data()
            
            # Step 4: Migrate data to PostgreSQL
            if not self.dry_run:
                await self._migrate_data_to_postgres(tables_data)
            else:
                logger.info("DRY RUN: Would migrate the following tables:")
                for table_name, data in tables_data.items():
                    logger.info(f"  - {table_name}: {len(data)} rows")
            
            # Step 5: Validate migration
            if not self.dry_run:
                await self._validate_migration(tables_data)
            
            self.migration_stats['end_time'] = datetime.now()
            duration = self.migration_stats['end_time'] - self.migration_stats['start_time']
            
            logger.info(f"Migration completed successfully in {duration}")
            logger.info(f"Migrated {self.migration_stats['tables_migrated']} tables with {self.migration_stats['total_rows_migrated']} total rows")
            
            return True
            
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            return False
    
    async def _backup_database(self) -> None:
        """Create a backup of the SQLite database."""
        backup_dir = Path(self.backup_dir) if self.backup_dir else Path("data/backups")
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"chatbot_backup_{timestamp}.db"
        
        logger.info(f"Creating backup at {backup_path}")
        shutil.copy2(self.sqlite_path, backup_path)
        logger.info("Backup completed successfully")
    
    async def _verify_postgres_connection(self) -> None:
        """Verify that PostgreSQL connection works."""
        try:
            conn = await psycopg.AsyncConnection.connect(self.postgres_dsn)
            await conn.close()
            logger.info("PostgreSQL connection verified successfully")
        except Exception as e:
            raise Exception(f"Failed to connect to PostgreSQL: {e}")
    
    async def _extract_sqlite_data(self) -> Dict[str, List[Dict[str, Any]]]:
        """Extract all data from SQLite database."""
        logger.info("Extracting data from SQLite database...")
        
        if not Path(self.sqlite_path).exists():
            logger.info("SQLite database does not exist. Starting with empty migration.")
            return {}
        
        tables_data = {}
        
        # Connect to SQLite database
        conn = sqlite3.connect(self.sqlite_path)
        conn.row_factory = sqlite3.Row  # Enable column access by name
        cursor = conn.cursor()
        
        try:
            # Get all table names
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
            tables = [row[0] for row in cursor.fetchall()]
            
            for table_name in tables:
                logger.info(f"Extracting data from table: {table_name}")
                
                # Get all rows from table
                cursor.execute(f"SELECT * FROM {table_name}")
                rows = cursor.fetchall()
                
                # Convert to list of dictionaries
                table_data = []
                for row in rows:
                    row_dict = {}
                    for key in row.keys():
                        value = row[key]
                        # Handle JSON columns that are stored as TEXT in SQLite
                        if key in ['config', 'event_data', 'potential_actions', 'selected_actions', 'raw_content']:
                            if isinstance(value, str):
                                try:
                                    value = json.loads(value)
                                except json.JSONDecodeError:
                                    # Keep as string if not valid JSON
                                    pass
                        row_dict[key] = value
                    table_data.append(row_dict)
                
                tables_data[table_name] = table_data
                logger.info(f"Extracted {len(table_data)} rows from {table_name}")
        
        finally:
            conn.close()
        
        return tables_data
    
    async def _migrate_data_to_postgres(self, tables_data: Dict[str, List[Dict[str, Any]]]) -> None:
        """Migrate extracted data to PostgreSQL."""
        logger.info("Migrating data to PostgreSQL...")
        
        conn = await psycopg.AsyncConnection.connect(self.postgres_dsn)
        
        try:
            for table_name, rows in tables_data.items():
                if not rows:
                    logger.info(f"Skipping empty table: {table_name}")
                    continue
                
                logger.info(f"Migrating {len(rows)} rows to table: {table_name}")
                
                async with conn.cursor() as cur:
                    # Clear existing data in PostgreSQL table
                    await cur.execute(f"DELETE FROM {table_name}")
                    logger.info(f"Cleared existing data from {table_name}")
                    
                    # Insert data
                    for row in rows:
                        await self._insert_row_to_postgres(cur, table_name, row)
                    
                    # Reset sequences for SERIAL columns
                    await self._reset_sequences(cur, table_name)
                
                await conn.commit()
                self.migration_stats['tables_migrated'] += 1
                self.migration_stats['total_rows_migrated'] += len(rows)
                logger.info(f"Successfully migrated table: {table_name}")
        
        finally:
            await conn.close()
    
    async def _insert_row_to_postgres(self, cursor, table_name: str, row: Dict[str, Any]) -> None:
        """Insert a single row into PostgreSQL table."""
        columns = list(row.keys())
        placeholders = ["%s"] * len(columns)
        values = []
        
        for col, value in row.items():
            # Handle special transformations
            if table_name == "integrations" and col in ["created_at", "updated_at"]:
                # Convert Unix timestamp to PostgreSQL timestamp
                if isinstance(value, (int, float)):
                    value = datetime.fromtimestamp(value)
            elif col in ['config', 'potential_actions', 'selected_actions', 'raw_content', 'event_data']:
                # Ensure JSON fields are properly formatted
                if not isinstance(value, (dict, list)):
                    try:
                        value = json.loads(value) if isinstance(value, str) else value
                    except json.JSONDecodeError:
                        # Keep as-is if not valid JSON
                        pass
            values.append(value)
        
        query = f"""
            INSERT INTO {table_name} ({', '.join(columns)}) 
            VALUES ({', '.join(placeholders)})
        """
        
        try:
            await cursor.execute(query, values)
        except Exception as e:
            logger.error(f"Failed to insert row into {table_name}: {e}")
            logger.error(f"Row data: {row}")
            raise
    
    async def _reset_sequences(self, cursor, table_name: str) -> None:
        """Reset PostgreSQL sequences for SERIAL columns."""
        # Tables that have SERIAL primary keys
        serial_tables = {
            'state_changes': 'id',
            'undecryptable_events': 'id'
        }
        
        if table_name in serial_tables:
            id_column = serial_tables[table_name]
            sequence_name = f"{table_name}_{id_column}_seq"
            
            try:
                await cursor.execute(f"""
                    SELECT setval('{sequence_name}', 
                                  COALESCE((SELECT MAX({id_column}) FROM {table_name}), 1), 
                                  false)
                """)
                logger.info(f"Reset sequence for {table_name}")
            except Exception as e:
                logger.warning(f"Could not reset sequence for {table_name}: {e}")
    
    async def _validate_migration(self, original_data: Dict[str, List[Dict[str, Any]]]) -> None:
        """Validate that migration was successful."""
        logger.info("Validating migration...")
        
        conn = await psycopg.AsyncConnection.connect(self.postgres_dsn)
        
        try:
            async with conn.cursor() as cur:
                for table_name, original_rows in original_data.items():
                    # Count rows in PostgreSQL
                    await cur.execute(f"SELECT COUNT(*) FROM {table_name}")
                    result = await cur.fetchone()
                    pg_count = result[0] if result else 0
                    
                    original_count = len(original_rows)
                    
                    if pg_count == original_count:
                        logger.info(f"✅ {table_name}: {pg_count} rows (validated)")
                    else:
                        logger.error(f"❌ {table_name}: Expected {original_count} rows, found {pg_count}")
                        raise Exception(f"Row count mismatch for table {table_name}")
        
        finally:
            await conn.close()
        
        logger.info("Migration validation completed successfully")


async def main():
    """Main entry point for the migration script."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Migrate SQLite database to PostgreSQL")
    parser.add_argument("--dry-run", action="store_true", help="Perform a dry run without actual migration")
    parser.add_argument("--backup-dir", type=str, help="Directory to store backup files")
    parser.add_argument("--sqlite-path", type=str, default="data/chatbot.db", help="Path to SQLite database")
    
    args = parser.parse_args()
    
    migrator = SQLiteToPostgresMigrator(
        sqlite_path=args.sqlite_path,
        dry_run=args.dry_run,
        backup_dir=args.backup_dir
    )
    
    success = await migrator.migrate()
    
    if success:
        logger.info("Migration completed successfully!")
        if not args.dry_run:
            logger.info("You can now update your application configuration to use PostgreSQL.")
    else:
        logger.error("Migration failed!")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
