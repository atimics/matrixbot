#!/usr/bin/env python3
"""
Matrix Diagnostics Script

This script helps diagnose Matrix connection and sending issues.
It performs various health checks and tests to identify problems.
"""

import asyncio
import logging
import os
import sys
import time
from typing import Dict, Any

# Add the parent directory to Python path to import chatbot modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from chatbot.integrations.matrix import MatrixObserver
from chatbot.core.world_state import WorldStateManager
from chatbot.config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_matrix_connection():
    """Test basic Matrix connection and authentication."""
    logger.info("🔍 Testing Matrix connection...")
    
    wsm = WorldStateManager()
    observer = MatrixObserver(world_state_manager=wsm)
    
    try:
        # Test connection
        await observer.connect()
        logger.info("✅ Matrix connection successful")
        
        # Test health check
        is_healthy = await observer.check_connection_health()
        logger.info(f"🏥 Connection health: {'✅ Healthy' if is_healthy else '❌ Unhealthy'}")
        
        # Test whoami
        if observer.client:
            whoami_response = await observer.client.whoami()
            logger.info(f"👤 Authenticated as: {whoami_response.user_id if hasattr(whoami_response, 'user_id') else 'Unknown'}")
        
        return observer
        
    except Exception as e:
        logger.error(f"❌ Matrix connection failed: {e}")
        return None


async def test_room_access(observer: MatrixObserver, room_id: str):
    """Test access to a specific room."""
    logger.info(f"🏠 Testing room access: {room_id}")
    
    try:
        # Check room permissions
        permissions = await observer.check_room_permissions(room_id)
        logger.info(f"🔐 Room permissions: {permissions}")
        
        # Try to get room details
        if observer.client and room_id in observer.client.rooms:
            room = observer.client.rooms[room_id]
            logger.info(f"📋 Room name: {room.display_name or room.name or 'Unknown'}")
            logger.info(f"👥 Member count: {len(room.users)}")
            logger.info(f"🔒 Encrypted: {getattr(room, 'encrypted', False)}")
        else:
            logger.warning("⚠️ Room not found in client rooms")
        
    except Exception as e:
        logger.error(f"❌ Room access test failed: {e}")


async def test_message_sending(observer: MatrixObserver, room_id: str):
    """Test sending messages to a room."""
    logger.info(f"📤 Testing message sending to: {room_id}")
    
    test_content = f"🤖 Matrix diagnostic test message - {int(time.time())}"
    
    try:
        # Test simple message
        result = await observer.send_message(room_id, test_content)
        if result.get("success"):
            logger.info(f"✅ Simple message sent: {result.get('event_id')}")
        else:
            logger.error(f"❌ Simple message failed: {result.get('error')}")
        
        # Test formatted message
        formatted_result = await observer.send_formatted_message(
            room_id, 
            test_content, 
            f"<p><strong>{test_content}</strong></p>"
        )
        if formatted_result.get("success"):
            logger.info(f"✅ Formatted message sent: {formatted_result.get('event_id')}")
        else:
            logger.error(f"❌ Formatted message failed: {formatted_result.get('error')}")
        
    except Exception as e:
        logger.error(f"❌ Message sending test failed: {e}")


async def diagnose_server_issues():
    """Diagnose potential server-side issues."""
    logger.info("🌐 Diagnosing server issues...")
    
    import httpx
    
    homeserver = settings.MATRIX_HOMESERVER
    logger.info(f"🏠 Homeserver: {homeserver}")
    
    try:
        # Test basic connectivity
        async with httpx.AsyncClient() as client:
            # Test server versions
            versions_url = f"{homeserver}/_matrix/client/versions"
            response = await client.get(versions_url)
            logger.info(f"📋 Server versions response: {response.status_code}")
            if response.status_code == 200:
                logger.info(f"✅ Server is reachable")
                data = response.json()
                logger.info(f"🔢 Supported versions: {data.get('versions', [])}")
            else:
                logger.error(f"❌ Server unreachable: {response.status_code}")
            
            # Test server discovery
            wellknown_url = f"{homeserver}/.well-known/matrix/client"
            try:
                wellknown_response = await client.get(wellknown_url)
                if wellknown_response.status_code == 200:
                    logger.info(f"✅ Server discovery working")
                    logger.info(f"📋 Well-known: {wellknown_response.json()}")
                else:
                    logger.warning(f"⚠️ Server discovery failed: {wellknown_response.status_code}")
            except:
                logger.warning("⚠️ Server discovery not available")
    
    except Exception as e:
        logger.error(f"❌ Server diagnostic failed: {e}")


async def main():
    """Main diagnostic routine."""
    logger.info("🚀 Starting Matrix diagnostics...")
    
    # Check environment variables
    logger.info("🔧 Checking configuration...")
    required_vars = ["MATRIX_HOMESERVER", "MATRIX_USER_ID", "MATRIX_PASSWORD"]
    for var in required_vars:
        value = getattr(settings, var, None)
        if value:
            # Mask password for security
            display_value = "***" if "PASSWORD" in var else value
            logger.info(f"✅ {var}: {display_value}")
        else:
            logger.error(f"❌ {var}: Not set")
    
    # Test server connectivity
    await diagnose_server_issues()
    
    # Test Matrix connection
    observer = await test_matrix_connection()
    if not observer:
        logger.error("❌ Cannot proceed without Matrix connection")
        return
    
    # Test room access if specified
    room_id = os.getenv("TEST_ROOM_ID", "!zBaUOGAwGyzOEGWJFd:chat.ratimics.com")
    if room_id:
        await test_room_access(observer, room_id)
        await test_message_sending(observer, room_id)
    
    # Cleanup
    try:
        await observer.disconnect()
        logger.info("🧹 Cleanup completed")
    except:
        pass
    
    logger.info("✅ Diagnostics completed")


if __name__ == "__main__":
    asyncio.run(main())
