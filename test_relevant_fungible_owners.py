#!/usr/bin/env python3
"""
Test script to verify the get_relevant_fungible_owners method in NeynarAPIClient
"""

import asyncio
import os
import logging
from chatbot.integrations.farcaster.neynar_api_client import NeynarAPIClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_get_relevant_fungible_owners():
    """Test the get_relevant_fungible_owners method"""
    
    # Get API key from environment
    api_key = os.getenv("NEYNAR_API_KEY")
    if not api_key:
        logger.error("NEYNAR_API_KEY environment variable is required")
        return
    
    # Initialize client
    client = NeynarAPIClient(api_key=api_key)
    
    try:
        # Test with a well-known contract (example: using a Base token)
        test_cases = [
            {
                "name": "Base network token",
                "contract_address": "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",  # USDC on Base
                "network": "base",
                "viewer_fid": None
            },
            {
                "name": "Base network token with viewer context",
                "contract_address": "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",  # USDC on Base
                "network": "base", 
                "viewer_fid": 3  # Using dan's FID as an example
            },
            {
                "name": "Ethereum mainnet token",
                "contract_address": "0xa0b86a33e6441e03e58f3b55f46419b9a272b1a8", # Example ETH token
                "network": "ethereum",
                "viewer_fid": None
            }
        ]
        
        for case in test_cases:
            logger.info(f"\n--- Testing: {case['name']} ---")
            logger.info(f"Contract: {case['contract_address']}")
            logger.info(f"Network: {case['network']}")
            logger.info(f"Viewer FID: {case['viewer_fid']}")
            
            try:
                result = await client.get_relevant_fungible_owners(
                    contract_address=case['contract_address'],
                    network=case['network'],
                    viewer_fid=case['viewer_fid']
                )
                
                if result:
                    logger.info("✅ API call successful")
                    logger.info(f"Response contains keys: {list(result.keys())}")
                    
                    # Check for expected response structure
                    if "top_relevant_fungible_owners_hydrated" in result:
                        hydrated_count = len(result["top_relevant_fungible_owners_hydrated"])
                        logger.info(f"Top relevant hydrated owners: {hydrated_count}")
                        
                        # Show first few usernames if available
                        if hydrated_count > 0:
                            first_users = result["top_relevant_fungible_owners_hydrated"][:3]
                            usernames = [user.get("username", "unknown") for user in first_users]
                            logger.info(f"Sample usernames: {usernames}")
                    
                    if "all_relevant_fungible_owners_dehydrated" in result:
                        dehydrated_count = len(result["all_relevant_fungible_owners_dehydrated"]) 
                        logger.info(f"All relevant dehydrated owners: {dehydrated_count}")
                        
                        if dehydrated_count > 0:
                            first_users = result["all_relevant_fungible_owners_dehydrated"][:3]
                            usernames = [user.get("username", "unknown") for user in first_users]
                            logger.info(f"Sample usernames (dehydrated): {usernames}")
                
                else:
                    logger.warning("❌ API call returned None")
                    
            except Exception as e:
                logger.error(f"❌ Error testing {case['name']}: {e}")
            
            # Add a small delay between requests to be respectful
            await asyncio.sleep(1)
    
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(test_get_relevant_fungible_owners())
