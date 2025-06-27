#!/usr/bin/env python3
"""
PostgreSQL Migration Test Suite

This comprehensive test validates the PostgreSQL migration implementation,
ensuring that all functionality works correctly with the new database backend.

The test suite covers:
1. Database connection and initialization
2. All CRUD operations for each data model
3. Data type conversions (especially JSON fields to JSONB)
4. Connection pooling behavior
5. Concurrent access patterns
6. Migration from SQLite (if applicable)

Usage:
    python test_postgresql_migration.py [--use-docker] [--cleanup]
"""

import asyncio
import json
import logging
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, Any, List

# Add the project root to the Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import our components
from chatbot.core.persistence import DatabaseManager, IntegrationRecord, StateChangeRecord
from chatbot.config import settings


class PostgreSQLMigrationTest:
    """Comprehensive test suite for PostgreSQL migration."""
    
    def __init__(self, use_docker: bool = False):
        self.use_docker = use_docker
        self.db_manager = None
        self.test_results = {
            'passed': 0,
            'failed': 0,
            'errors': []
        }
    
    async def run_all_tests(self) -> bool:
        """Run the complete test suite."""
        try:
            logger.info("🚀 Starting PostgreSQL Migration Test Suite")
            logger.info("=" * 60)
            
            # Setup
            await self._setup_test_environment()
            
            # Run test categories
            await self._test_database_initialization()
            await self._test_integration_operations()
            await self._test_credential_operations()
            await self._test_state_change_operations()
            await self._test_undecryptable_event_operations()
            await self._test_replied_to_cast_operations()
            await self._test_config_operations()
            await self._test_json_data_handling()
            await self._test_concurrent_operations()
            await self._test_connection_pooling()
            
            # Cleanup
            await self._cleanup_test_environment()
            
            # Print results
            self._print_test_results()
            
            return self.test_results['failed'] == 0
            
        except Exception as e:
            logger.error(f"Test suite failed with error: {e}")
            return False
    
    async def _setup_test_environment(self):
        """Set up the test environment."""
        logger.info("Setting up test environment...")
        
        # Use external DSN for tests running outside Docker
        logger.info(f"PostgreSQL External DSN: {settings.postgres.external_dsn}")
        
        # Initialize database manager with external connection
        self.db_manager = DatabaseManager()
        # Override the DSN for external access
        self.db_manager.dsn = settings.postgres.external_dsn
        await self.db_manager.initialize()
        
        logger.info("✅ Test environment setup complete")
    
    async def _cleanup_test_environment(self):
        """Clean up test environment."""
        logger.info("Cleaning up test environment...")
        
        if self.db_manager:
            # Clean up test data
            await self._cleanup_test_data()
            await self.db_manager.close()
        
        logger.info("✅ Test environment cleanup complete")
    
    async def _cleanup_test_data(self):
        """Remove test data from database."""
        try:
            # Delete test integrations (this will cascade to credentials)
            test_integration_ids = ["test_integration_1", "test_integration_2", "concurrent_test_1", "concurrent_test_2"]
            for integration_id in test_integration_ids:
                await self.db_manager.delete_integration(integration_id)
            
            # Delete test config values
            test_config_keys = ["test_config_key", "test_json_config", "concurrent_config_1", "concurrent_config_2"]
            for key in test_config_keys:
                await self.db_manager.delete_config_value(key)
            
            logger.info("✅ Test data cleanup complete")
        except Exception as e:
            logger.warning(f"Test data cleanup had issues: {e}")
    
    def _assert_true(self, condition: bool, message: str):
        """Assert that condition is True."""
        if condition:
            self.test_results['passed'] += 1
            logger.info(f"✅ {message}")
        else:
            self.test_results['failed'] += 1
            error_msg = f"❌ FAILED: {message}"
            logger.error(error_msg)
            self.test_results['errors'].append(error_msg)
    
    def _assert_equal(self, actual: Any, expected: Any, message: str):
        """Assert that actual equals expected."""
        self._assert_true(actual == expected, f"{message} (expected: {expected}, got: {actual})")
    
    def _assert_not_none(self, value: Any, message: str):
        """Assert that value is not None."""
        self._assert_true(value is not None, message)
    
    async def _test_database_initialization(self):
        """Test database initialization."""
        logger.info("\n📊 Testing Database Initialization")
        
        # Test that connection pool is established
        self._assert_not_none(self.db_manager.pool, "Connection pool is established")
        
        # Test that we can execute a simple query
        try:
            async def test_query(cur):
                await cur.execute("SELECT 1 as test_value")
                result = await cur.fetchone()
                return result[0] if result else None
            
            result = await self.db_manager._execute_operation(test_query)
            self._assert_equal(result, 1, "Simple query execution works")
        except Exception as e:
            self._assert_true(False, f"Database query failed: {e}")
    
    async def _test_integration_operations(self):
        """Test integration CRUD operations."""
        logger.info("\n🔗 Testing Integration Operations")
        
        # Test create integration
        config_data = {
            "api_key": "test_key_123",
            "settings": {"auto_reply": True, "cooldown": 300}
        }
        
        integration = await self.db_manager.create_integration(
            integration_id="test_integration_1",
            integration_type="matrix",
            display_name="Test Matrix Integration",
            config=config_data,
            user_id="test_user"
        )
        
        self._assert_not_none(integration, "Integration creation successful")
        self._assert_equal(integration.id, "test_integration_1", "Integration ID correct")
        self._assert_equal(integration.config, config_data, "Integration config preserved")
        
        # Test get integration
        retrieved = await self.db_manager.get_integration("test_integration_1")
        self._assert_not_none(retrieved, "Integration retrieval successful")
        self._assert_equal(retrieved.display_name, "Test Matrix Integration", "Retrieved integration data correct")
        
        # Test list integrations
        integrations = await self.db_manager.list_integrations()
        self._assert_true(len(integrations) >= 1, "Integration listing works")
        
        # Test update integration
        updated_config = {"api_key": "updated_key_456", "new_setting": "value"}
        updated = await self.db_manager.update_integration(
            "test_integration_1",
            config=updated_config,
            display_name="Updated Test Integration"
        )
        
        self._assert_not_none(updated, "Integration update successful")
        self._assert_equal(updated.config, updated_config, "Integration config updated correctly")
        self._assert_equal(updated.display_name, "Updated Test Integration", "Integration display name updated")
    
    async def _test_credential_operations(self):
        """Test credential operations."""
        logger.info("\n🔐 Testing Credential Operations")
        
        encrypted_value = b"encrypted_credential_data"
        
        # Test create credential
        credential = await self.db_manager.create_credential(
            credential_id="test_cred_1",
            integration_id="test_integration_1",
            credential_key="password",
            encrypted_value=encrypted_value
        )
        
        self._assert_not_none(credential, "Credential creation successful")
        self._assert_equal(credential.credential_key, "password", "Credential key correct")
        self._assert_equal(credential.credential_value_encrypted, encrypted_value, "Encrypted value preserved")
        
        # Test get credentials
        credentials = await self.db_manager.get_credentials("test_integration_1")
        self._assert_true(len(credentials) >= 1, "Credential retrieval works")
        self._assert_equal(credentials[0].credential_key, "password", "Retrieved credential correct")
    
    async def _test_state_change_operations(self):
        """Test state change operations."""
        logger.info("\n📝 Testing State Change Operations")
        
        raw_content = {"event_type": "message", "content": "Test message", "metadata": {"channel": "test"}}
        
        # Test create state change
        state_change = await self.db_manager.create_state_change(
            timestamp=time.time(),
            change_type="message_received",
            source="matrix",
            raw_content=json.dumps(raw_content),
            channel_id="test_channel",
            observations="User sent a test message"
        )
        
        self._assert_not_none(state_change, "State change creation successful")
        self._assert_equal(state_change.change_type, "message_received", "State change type correct")
        self._assert_equal(state_change.channel_id, "test_channel", "Channel ID preserved")
        
        # Test get state changes
        state_changes = await self.db_manager.get_state_changes(channel_id="test_channel")
        self._assert_true(len(state_changes) >= 1, "State change retrieval works")
    
    async def _test_undecryptable_event_operations(self):
        """Test undecryptable event operations."""
        logger.info("\n🔒 Testing Undecryptable Event Operations")
        
        event_data = {"event_type": "m.room.encrypted", "sender": "@user:matrix.org"}
        
        # Test create undecryptable event
        event = await self.db_manager.create_undecryptable_event(
            event_id="$test_event_123",
            room_id="!test_room:matrix.org",
            sender="@user:matrix.org",
            timestamp=time.time(),
            event_data=event_data
        )
        
        self._assert_not_none(event, "Undecryptable event creation successful")
        self._assert_equal(event.event_id, "$test_event_123", "Event ID correct")
        self._assert_equal(event.retry_count, 0, "Initial retry count correct")
        
        # Test update retry count
        updated_event = await self.db_manager.update_undecryptable_event_retry(
            "$test_event_123", 1, time.time()
        )
        
        self._assert_not_none(updated_event, "Event retry update successful")
        self._assert_equal(updated_event.retry_count, 1, "Retry count updated correctly")
    
    async def _test_replied_to_cast_operations(self):
        """Test replied-to cast operations."""
        logger.info("\n💬 Testing Replied-to Cast Operations")
        
        # Test add replied-to cast
        await self.db_manager.add_replied_to_cast("original_hash_123", "reply_hash_456")
        
        # Test has replied to
        has_replied = await self.db_manager.has_replied_to("original_hash_123")
        self._assert_true(has_replied, "Replied-to cast tracking works")
        
        # Test get replied-to cast info
        info = await self.db_manager.get_replied_to_cast_info("original_hash_123")
        self._assert_not_none(info, "Replied-to cast info retrieval works")
        self._assert_equal(info["reply_cast_hash"], "reply_hash_456", "Reply hash preserved")
    
    async def _test_config_operations(self):
        """Test configuration operations."""
        logger.info("\n⚙️ Testing Configuration Operations")
        
        # Test set config value
        test_config = {"feature_enabled": True, "timeout": 300}
        await self.db_manager.set_config_value("test_config_key", test_config)
        
        # Test get config value
        retrieved_config = await self.db_manager.get_config_value("test_config_key")
        self._assert_not_none(retrieved_config, "Config value retrieval works")
        self._assert_equal(retrieved_config, test_config, "Config value preserved correctly")
        
        # Test get config with default
        default_value = await self.db_manager.get_config_value("nonexistent_key", "default")
        self._assert_equal(default_value, "default", "Default value works for missing keys")
        
        # Test delete config value
        deleted = await self.db_manager.delete_config_value("test_config_key")
        self._assert_true(deleted, "Config value deletion works")
    
    async def _test_json_data_handling(self):
        """Test JSON/JSONB data handling."""
        logger.info("\n📊 Testing JSON Data Handling")
        
        # Complex JSON structure
        complex_json = {
            "nested": {
                "array": [1, 2, 3, {"inner": "value"}],
                "boolean": True,
                "null_value": None
            },
            "unicode": "🚀 Testing unicode characters",
            "numbers": {"int": 42, "float": 3.14159}
        }
        
        # Test storing complex JSON in config
        await self.db_manager.set_config_value("test_json_config", complex_json)
        retrieved_json = await self.db_manager.get_config_value("test_json_config")
        
        self._assert_equal(retrieved_json, complex_json, "Complex JSON data preserved accurately")
        
        # Test JSON in integration config
        integration = await self.db_manager.create_integration(
            integration_id="test_integration_2",
            integration_type="farcaster",
            display_name="JSON Test Integration",
            config=complex_json
        )
        
        self._assert_equal(integration.config, complex_json, "JSON in integration config preserved")
    
    async def _test_concurrent_operations(self):
        """Test concurrent database operations."""
        logger.info("\n⚡ Testing Concurrent Operations")
        
        # Create multiple concurrent tasks
        async def concurrent_task(task_id: int):
            try:
                # Create integration
                integration = await self.db_manager.create_integration(
                    integration_id=f"concurrent_test_{task_id}",
                    integration_type="test",
                    display_name=f"Concurrent Test {task_id}",
                    config={"task_id": task_id}
                )
                
                # Set config value
                await self.db_manager.set_config_value(f"concurrent_config_{task_id}", {"value": task_id})
                
                # Get config value
                retrieved = await self.db_manager.get_config_value(f"concurrent_config_{task_id}")
                
                return integration is not None and retrieved is not None
            except Exception as e:
                logger.error(f"Concurrent task {task_id} failed: {e}")
                return False
        
        # Run concurrent tasks
        tasks = [concurrent_task(i) for i in range(1, 6)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        successful_tasks = sum(1 for result in results if result is True)
        self._assert_equal(successful_tasks, 5, "All concurrent operations completed successfully")
    
    async def _test_connection_pooling(self):
        """Test connection pooling behavior."""
        logger.info("\n🏊 Testing Connection Pooling")
        
        # Test that we can execute multiple operations simultaneously
        async def pool_task(task_id: int):
            try:
                async def simple_query(cur):
                    await cur.execute("SELECT %s as task_id", (task_id,))
                    result = await cur.fetchone()
                    return result[0] if result else None
                
                result = await self.db_manager._execute_operation(simple_query)
                return result == task_id
            except Exception as e:
                logger.error(f"Pool task {task_id} failed: {e}")
                return False
        
        # Run many tasks to test pool behavior
        pool_tasks = [pool_task(i) for i in range(1, 11)]
        pool_results = await asyncio.gather(*pool_tasks, return_exceptions=True)
        
        successful_pool_tasks = sum(1 for result in pool_results if result is True)
        self._assert_equal(successful_pool_tasks, 10, "Connection pool handles concurrent requests")
    
    def _print_test_results(self):
        """Print final test results."""
        logger.info("\n" + "=" * 60)
        logger.info("📊 PostgreSQL Migration Test Results")
        logger.info("=" * 60)
        
        total_tests = self.test_results['passed'] + self.test_results['failed']
        success_rate = (self.test_results['passed'] / total_tests * 100) if total_tests > 0 else 0
        
        logger.info(f"✅ Passed: {self.test_results['passed']}")
        logger.info(f"❌ Failed: {self.test_results['failed']}")
        logger.info(f"📈 Success Rate: {success_rate:.1f}%")
        
        if self.test_results['failed'] == 0:
            logger.info("\n🎉 All tests passed! PostgreSQL migration is ready for production.")
        else:
            logger.error("\n⚠️ Some tests failed. Please review the errors above:")
            for error in self.test_results['errors']:
                logger.error(f"   {error}")
        
        logger.info("=" * 60)


async def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="PostgreSQL Migration Test Suite")
    parser.add_argument("--use-docker", action="store_true", help="Use Docker PostgreSQL instance")
    parser.add_argument("--cleanup", action="store_true", help="Only run cleanup")
    
    args = parser.parse_args()
    
    test_suite = PostgreSQLMigrationTest(use_docker=args.use_docker)
    
    if args.cleanup:
        # Run cleanup only
        await test_suite._setup_test_environment()
        await test_suite._cleanup_test_environment()
        return
    
    # Run full test suite
    success = await test_suite.run_all_tests()
    
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
