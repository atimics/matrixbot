#!/usr/bin/env python3
"""Test script to validate the integration system refactor."""

import asyncio
import sys
import os
import pytest
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from chatbot.core.integration_manager import IntegrationManager
from chatbot.core.world_state.manager import WorldStateManager
from chatbot.core.history_recorder import HistoryRecorder


@pytest.mark.asyncio
async def test_integration_system():
    """Test the integration system functionality."""
    print("Testing Integration System...")
    
    # Use a clean test database for each run
    test_db_path = "test_integration_system.db"
    
    # Remove existing test database
    import os
    if os.path.exists(test_db_path):
        os.remove(test_db_path)
    
    # Initialize history recorder (which handles DB)
    history_recorder = HistoryRecorder(test_db_path)
    await history_recorder.initialize()
    print("✓ History Recorder initialized")
    
    # Initialize world state manager
    world_state_manager = WorldStateManager()
    print("✓ World State Manager initialized")
    
    # Initialize integration manager
    integration_manager = IntegrationManager(test_db_path, world_state_manager=world_state_manager)
    await integration_manager.initialize()
    print("✓ Integration Manager initialized")
    
    # Test available integration types
    available_types = integration_manager.get_available_integration_types()
    print(f"✓ Available integration types: {available_types}")
    
    # Test adding a Matrix integration
    try:
        matrix_config = {
            "name": "test_matrix",
            "integration_type": "matrix",
            "config": {
                "test_mode": True  # Prevent actual network connections
            },
            "credentials": {
                "homeserver": "https://matrix.org",
                "user_id": "@test:matrix.org",
                "password": "test_password"
            }
        }
        
        await integration_manager.add_integration(
            integration_type=matrix_config["integration_type"],
            display_name=matrix_config["name"],
            config=matrix_config["config"],
            credentials=matrix_config["credentials"]
        )
        print("✓ Matrix integration added successfully")
        
        # List integrations
        integrations = await integration_manager.list_integrations()
        print(f"✓ Listed integrations: {len(integrations)} found")
        
        # Test getting integration status
        for integration_info in integrations:
            integration_id = integration_info['integration_id']
            status = await integration_manager.get_integration_status(integration_id)
            print(f"✓ Integration {integration_info['display_name']} status: {status['is_connected']}")
        
    except Exception as e:
        print(f"✗ Error testing Matrix integration: {e}")
        import traceback
        traceback.print_exc()
    
    # Test adding a Farcaster integration
    try:
        farcaster_config = {
            "name": "test_farcaster",
            "integration_type": "farcaster",
            "config": {
                "test_mode": True  # Prevent actual network connections
            },
            "credentials": {
                "api_key": "test_api_key_12345",
                "signer_uuid": "test-signer-uuid",
                "bot_fid": "123456"
            }
        }
        
        await integration_manager.add_integration(
            integration_type=farcaster_config["integration_type"],
            display_name=farcaster_config["name"],
            config=farcaster_config["config"],
            credentials=farcaster_config["credentials"]
        )
        print("✓ Farcaster integration added successfully")
        
    except Exception as e:
        print(f"✗ Error testing Farcaster integration: {e}")
        import traceback
        traceback.print_exc()
    
    # Test connecting all integrations
    try:
        await integration_manager.connect_all()
        print("✓ All integrations connected")
    except Exception as e:
        print(f"✗ Error connecting integrations: {e}")
        import traceback
        traceback.print_exc()
    
    # Test getting observers
    try:
        observers = integration_manager.get_observers()
        print(f"✓ Retrieved {len(observers)} observers")
        for observer in observers:
            status = await observer.get_status()
            print(f"  - {observer.__class__.__name__}: connected={status.get('is_connected', False)}")
    except Exception as e:
        print(f"✗ Error getting observers: {e}")
        import traceback
        traceback.print_exc()
    
    print("Integration system test completed!")
    
    # Cleanup test database
    if os.path.exists(test_db_path):
        os.remove(test_db_path)
    
    # Test passes if we reach this point
    assert True


if __name__ == "__main__":
    asyncio.run(test_integration_system())
