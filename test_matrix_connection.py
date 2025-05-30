#!/usr/bin/env python3
"""
Test Matrix Connection

Simple script to test Matrix login and connection issues.
"""

import asyncio
import logging
import os
from pathlib import Path
from nio import AsyncClient, LoginResponse
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()

async def test_matrix_connection():
    """Test Matrix connection and login"""
    
    # Get configuration
    homeserver = os.getenv("MATRIX_HOMESERVER")
    user_id = os.getenv("MATRIX_USER_ID")
    password = os.getenv("MATRIX_PASSWORD")
    device_name = os.getenv("DEVICE_NAME", "test_bot")
    device_id = os.getenv("MATRIX_DEVICE_ID")
    
    logger.info(f"Testing connection to {homeserver} as {user_id}")
    logger.info(f"Device name: {device_name}, Device ID: {device_id}")
    
    # Create store directory
    store_path = Path("test_matrix_store")
    store_path.mkdir(exist_ok=True)
    
    # Create client
    client = AsyncClient(
        homeserver, 
        user_id,
        device_id=device_id,
        store_path=str(store_path)
    )
    
    try:
        logger.info("Attempting login...")
        response = await client.login(
            password=password,
            device_name=device_name
        )
        
        if isinstance(response, LoginResponse):
            logger.info(f"✅ Login successful!")
            logger.info(f"   User ID: {response.user_id}")
            logger.info(f"   Device ID: {response.device_id}")
            logger.info(f"   Access Token: {response.access_token[:20]}...")
            
            # Test whoami
            whoami_response = await client.whoami()
            if hasattr(whoami_response, 'user_id'):
                logger.info(f"✅ Whoami successful: {whoami_response.user_id}")
            else:
                logger.error(f"❌ Whoami failed: {whoami_response}")
                
        else:
            logger.error(f"❌ Login failed: {response}")
            if hasattr(response, 'status_code'):
                logger.error(f"   Status code: {response.status_code}")
            if hasattr(response, 'message'):
                logger.error(f"   Message: {response.message}")
    
    except Exception as e:
        logger.error(f"❌ Exception during login: {e}")
        import traceback
        logger.error(traceback.format_exc())
    
    finally:
        await client.close()
        logger.info("Connection closed")

if __name__ == "__main__":
    asyncio.run(test_matrix_connection())
