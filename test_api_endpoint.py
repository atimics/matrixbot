#!/usr/bin/env python3
"""
Test script to verify the corrected Neynar API endpoint
"""

import asyncio
import os
import logging
from chatbot.integrations.farcaster.neynar_api_client import NeynarAPIClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_corrected_api_endpoint():
    """Test the corrected get_casts_by_fid endpoint"""
    
    # Check if we have API key in environment
    api_key = os.getenv("NEYNAR_API_KEY")
    if not api_key:
        logger.warning("NEYNAR_API_KEY not set in environment. Using placeholder API key for endpoint validation.")
        api_key = "test_key_123"
    
    client = NeynarAPIClient(api_key=api_key)
    
    try:
        # Test with a known FID (e.g., FID 1 is dwr.eth, a well-known account)
        logger.info("Testing get_casts_by_fid with corrected endpoint...")
        test_fid = 1  # dwr.eth
        
        # This will likely fail due to authentication, but we can check if the endpoint is formed correctly
        try:
            response = await client.get_casts_by_fid(test_fid, limit=5)
            logger.info(f"Success! Response keys: {list(response.keys()) if isinstance(response, dict) else 'Not a dict'}")
        except Exception as e:
            logger.info(f"Expected error (likely auth-related): {e}")
            # Check if the error indicates the endpoint is correct vs incorrect
            error_str = str(e).lower()
            if "404" in error_str or "not found" in error_str:
                logger.error("❌ 404 error suggests the endpoint path might still be incorrect")
            elif "401" in error_str or "unauthorized" in error_str or "forbidden" in error_str:
                logger.info("✅ Auth error suggests the endpoint path is correct")
            else:
                logger.info(f"Other error: {error_str}")
    
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(test_corrected_api_endpoint())
