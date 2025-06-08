#!/usr/bin/env python3
"""
Setup Farcaster Integration

This script ensures that a Farcaster integration is configured in the database.
It will create one if it doesn't exist, using credentials from the environment.
"""

import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from chatbot.core.integration_manager import IntegrationManager
from chatbot.config import settings


async def setup_farcaster_integration():
    """Setup Farcaster integration in the database."""
    print("Setting up Farcaster integration...")
    
    # Initialize integration manager
    integration_manager = IntegrationManager(settings.CHATBOT_DB_PATH)
    await integration_manager.initialize()
    print("✓ Integration Manager initialized")
    
    # Check if we already have a Farcaster integration
    integrations = await integration_manager.list_integrations()
    farcaster_integrations = [i for i in integrations if i.get('integration_type') == 'farcaster']
    
    if farcaster_integrations:
        print(f"✓ Found {len(farcaster_integrations)} existing Farcaster integration(s)")
        for integration in farcaster_integrations:
            print(f"  - {integration['display_name']} ({integration['integration_id']})")
            print(f"    Connected: {integration.get('is_connected', False)}")
            print(f"    Active: {integration.get('is_active', False)}")
        
        # Let's check if we can connect to the integration
        print("\nTesting connection to existing Farcaster integration...")
        from chatbot.core.world_state.manager import WorldStateManager
        world_state_manager = WorldStateManager()
        
        for integration in farcaster_integrations:
            integration_id = integration['integration_id']
            try:
                success = await integration_manager.connect_integration(integration_id, world_state_manager)
                print(f"  - Connection test for {integration['display_name']}: {'SUCCESS' if success else 'FAILED'}")
                
                if success:
                    # Get the actual integration instance to check its API client
                    if integration_id in integration_manager.active_integrations:
                        instance = integration_manager.active_integrations[integration_id]
                        has_api_client = hasattr(instance, 'api_client') and instance.api_client is not None
                        print(f"    API Client initialized: {has_api_client}")
                        if hasattr(instance, 'api_key'):
                            print(f"    API Key configured: {bool(instance.api_key)}")
                        if hasattr(instance, 'enabled'):
                            print(f"    Integration enabled: {instance.enabled}")
                            
            except Exception as e:
                print(f"  - Connection test for {integration['display_name']}: ERROR - {e}")
        
        return True
    
    # Check if we have Farcaster credentials configured
    if not settings.NEYNAR_API_KEY:
        print("⚠️  No Farcaster API key configured in environment")
        print("   Set NEYNAR_API_KEY to configure Farcaster integration")
        # Create a dummy integration for testing purposes
        print("   Creating dummy Farcaster integration for testing...")
        credentials = {
            "api_key": "dummy_api_key_for_testing",
            "signer_uuid": "dummy-signer-uuid",
            "bot_fid": "123456"
        }
    else:
        print("✓ Found Farcaster credentials in environment")
        credentials = {
            "api_key": settings.NEYNAR_API_KEY,
            "signer_uuid": settings.FARCASTER_BOT_SIGNER_UUID or "default-signer",
            "bot_fid": settings.FARCASTER_BOT_FID or "123456"
        }
    
    # Add Farcaster integration
    try:
        integration_id = await integration_manager.add_integration(
            integration_type="farcaster",
            display_name="Main Farcaster Bot",
            config={
                "bot_username": settings.FARCASTER_BOT_USERNAME or "unknown",
                "enabled": True
            },
            credentials=credentials
        )
        print(f"✓ Farcaster integration created with ID: {integration_id}")
        
        # Verify the integration was created
        integrations = await integration_manager.list_integrations()
        farcaster_integrations = [i for i in integrations if i.get('integration_type') == 'farcaster']
        print(f"✓ Verified: {len(farcaster_integrations)} Farcaster integration(s) now configured")
        
    except Exception as e:
        print(f"✗ Error creating Farcaster integration: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    return True


async def main():
    """Main function."""
    success = await setup_farcaster_integration()
    if success:
        print("\n✅ Farcaster integration setup completed successfully!")
    else:
        print("\n❌ Farcaster integration setup failed!")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
