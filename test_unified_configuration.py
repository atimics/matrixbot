#!/usr/bin/env python3
"""
Demonstration of Unified Configuration Storage

This script shows how the new DatabaseManager can be used to consolidate
scattered configuration files into a unified key-value store, addressing
Recommendation 4 from the engineering report.
"""

import asyncio
import logging
import tempfile
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import our persistence components
from chatbot.core.persistence import DatabaseManager

async def test_unified_configuration():
    """Test the unified configuration storage system."""
    logger.info("Testing Unified Configuration Storage...")
    
    # Create a temporary database for testing
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as temp_file:
        test_db_path = temp_file.name
    
    try:
        # Initialize database manager
        logger.info("Step 1: Initializing DatabaseManager")
        db_manager = DatabaseManager(test_db_path)
        await db_manager.initialize()
        
        # Test storing various configuration types
        logger.info("Step 2: Storing various configuration values")
        
        # Matrix configuration (replaces matrix_token.json)
        await db_manager.set_config_value("matrix.session_token", "encrypted_token_data_here")
        await db_manager.set_config_value("matrix.user_id", "@ratichat:chat.ratimics.com")
        await db_manager.set_config_value("matrix.homeserver", "https://chat.ratimics.com")
        
        # Farcaster observer state (replaces observer_state.json)
        await db_manager.set_config_value("farcaster.last_check_time", 1750835065.0)
        await db_manager.set_config_value("farcaster.observer_enabled", True)
        
        # General bot configuration (replaces config.json fragments)
        await db_manager.set_config_value("bot.name", "RatiChat")
        await db_manager.set_config_value("bot.version", "0.0.3")
        await db_manager.set_config_value("bot.features", ["matrix", "farcaster", "arweave"])
        
        # API rate limits
        await db_manager.set_config_value("rate_limits.openrouter.requests_per_hour", 1000)
        await db_manager.set_config_value("rate_limits.neynar.requests_per_hour", 500)
        
        logger.info("✅ Configuration values stored successfully")
        
        # Test retrieving configuration values
        logger.info("Step 3: Retrieving configuration values")
        
        matrix_token = await db_manager.get_config_value("matrix.session_token")
        farcaster_last_check = await db_manager.get_config_value("farcaster.last_check_time")
        bot_features = await db_manager.get_config_value("bot.features")
        nonexistent = await db_manager.get_config_value("does.not.exist", "default_value")
        
        logger.info(f"Matrix token: {matrix_token[:20]}...")
        logger.info(f"Farcaster last check: {farcaster_last_check}")
        logger.info(f"Bot features: {bot_features}")
        logger.info(f"Nonexistent (with default): {nonexistent}")
        
        # Validate retrieved values
        assert matrix_token == "encrypted_token_data_here", "Matrix token mismatch"
        assert farcaster_last_check == 1750835065.0, "Farcaster timestamp mismatch"
        assert bot_features == ["matrix", "farcaster", "arweave"], "Bot features mismatch"
        assert nonexistent == "default_value", "Default value not returned"
        
        logger.info("✅ Configuration retrieval tests passed")
        
        # Test configuration updates
        logger.info("Step 4: Testing configuration updates")
        
        # Update an existing value
        await db_manager.set_config_value("farcaster.last_check_time", 1750835100.0)
        updated_time = await db_manager.get_config_value("farcaster.last_check_time")
        
        assert updated_time == 1750835100.0, "Configuration update failed"
        logger.info(f"Updated farcaster last check time: {updated_time}")
        
        # Test configuration deletion
        logger.info("Step 5: Testing configuration deletion")
        
        deleted = await db_manager.delete_config_value("rate_limits.openrouter.requests_per_hour")
        assert deleted, "Configuration deletion failed"
        
        deleted_value = await db_manager.get_config_value("rate_limits.openrouter.requests_per_hour", "NOT_FOUND")
        assert deleted_value == "NOT_FOUND", "Deleted value still exists"
        
        logger.info("✅ Configuration deletion test passed")
        
        # Demonstrate the benefits
        logger.info("Step 6: Demonstrating unified storage benefits")
        
        # Show how this replaces multiple files
        logger.info("\n" + "="*60)
        logger.info("UNIFIED CONFIGURATION BENEFITS")
        logger.info("="*60)
        logger.info("Before (scattered files):")
        logger.info("  - data/config.json")
        logger.info("  - matrix_store/matrix_token.json")
        logger.info("  - data/farcaster_state/observer_state.json")
        logger.info("  - Various other config files...")
        logger.info("")
        logger.info("After (unified database):")
        logger.info("  - All configuration in database key-value store")
        logger.info("  - Atomic updates and transactions")
        logger.info("  - Centralized backup and restore")
        logger.info("  - Consistent error handling")
        logger.info("  - No file system race conditions")
        logger.info("="*60)
        
        # Clean up
        await db_manager.close()
        logger.info("✅ DatabaseManager closed successfully")
        
        logger.info("🎉 Unified Configuration Storage is working correctly!")
        
    finally:
        # Clean up
        if Path(test_db_path).exists():
            Path(test_db_path).unlink()
            logger.info(f"Cleaned up test database: {test_db_path}")

async def demonstrate_migration_pattern():
    """Demonstrate how to migrate from file-based to database-based configuration."""
    logger.info("\n" + "="*60)
    logger.info("CONFIGURATION MIGRATION PATTERN")
    logger.info("="*60)
    
    # This is a conceptual example of how existing code could be migrated
    logger.info("Example migration for Farcaster observer state:")
    logger.info("")
    logger.info("OLD CODE:")
    logger.info("  # Read from observer_state.json")
    logger.info("  with open('data/farcaster_state/observer_state.json', 'r') as f:")
    logger.info("      state = json.load(f)")
    logger.info("      last_check_time = state.get('last_check_time', 0)")
    logger.info("")
    logger.info("NEW CODE:")
    logger.info("  # Read from unified database")
    logger.info("  last_check_time = await db_manager.get_config_value(")
    logger.info("      'farcaster.last_check_time', 0)")
    logger.info("")
    logger.info("Benefits:")
    logger.info("  ✅ No file I/O operations")
    logger.info("  ✅ Automatic type serialization/deserialization")
    logger.info("  ✅ Built-in default value handling")
    logger.info("  ✅ Database transactions for consistency")
    logger.info("  ✅ Centralized error handling")
    logger.info("="*60)

if __name__ == "__main__":
    asyncio.run(test_unified_configuration())
    asyncio.run(demonstrate_migration_pattern())
