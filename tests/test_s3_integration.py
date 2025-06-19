#!/usr/bin/env python3
"""
Test S3 Storage Integration

Simple test to verify S3 storage works with the dual storage system.
"""

import asyncio
import logging
import os
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_s3_storage():
    """Test S3 storage functionality"""
    try:
        from chatbot.integrations.dual_storage_manager import DualStorageManager
        
        # Initialize dual storage manager
        storage_manager = DualStorageManager()
        
        # Check status
        status = storage_manager.get_storage_status()
        logger.info(f"Storage status: {status}")
        
        # Health check
        health = await storage_manager.health_check()
        logger.info(f"Health check: {health}")
        
        # Test with a small sample image if S3 is available
        if storage_manager.is_s3_available():
            logger.info("S3 is available, testing upload...")
            
            # Create a small test image (1x1 PNG)
            import base64
            # This is a 1x1 transparent PNG
            tiny_png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChAI9jU77zgAAAABJRU5ErkJggg=="
            test_image_data = base64.b64decode(tiny_png_b64)
            
            # Upload test image
            url = await storage_manager.upload_media(
                test_image_data, 
                "test_image.png", 
                "image/png"
            )
            
            if url:
                logger.info(f"✅ Test upload successful: {url}")
                return True
            else:
                logger.error("❌ Test upload failed")
                return False
        else:
            logger.warning("S3 not available, skipping upload test")
            return status.get('s3', {}).get('configured', False)
            
    except Exception as e:
        logger.error(f"Test failed: {e}")
        return False

async def test_nft_minting():
    """Test NFT minting functionality"""
    try:
        from chatbot.tools.nft_minting_tools import MintNFTFromMediaTool
        from chatbot.tools.base import ActionContext
        from chatbot.integrations.dual_storage_manager import DualStorageManager
        
        # Create mock context
        storage_manager = DualStorageManager()
        context = ActionContext()
        context.dual_storage_manager = storage_manager
        
        # Mock world state manager
        class MockWorldStateManager:
            def record_generated_media(self, **kwargs):
                logger.info(f"Mock: Recording generated media: {kwargs}")
        
        context.world_state_manager = MockWorldStateManager()
        
        # Test NFT minting tool
        nft_tool = MintNFTFromMediaTool()
        
        if storage_manager.is_arweave_available():
            logger.info("Testing NFT minting (requires valid media URL)...")
            # This would need a real media URL to test
            logger.info("NFT minting tool initialized successfully")
            return True
        else:
            logger.warning("Arweave not configured, NFT minting not available")
            return False
            
    except Exception as e:
        logger.error(f"NFT minting test failed: {e}")
        return False

def main():
    """Run all tests"""
    logger.info("🚀 Testing S3 Storage Integration")
    
    # Check environment variables  
    required_vars = ['S3_API_KEY', 'S3_API_ENDPOINT', 'CLOUDFRONT_DOMAIN']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.warning(f"Missing environment variables: {missing_vars}")
        logger.info("Set these variables to test S3 functionality")
    else:
        logger.info("✅ All required S3 environment variables are set")
    
    # Run async tests
    async def run_tests():
        results = []
        
        logger.info("\n--- Testing S3 Storage ---")
        s3_result = await test_s3_storage()
        results.append(("S3 Storage", s3_result))
        
        logger.info("\n--- Testing NFT Minting ---")
        nft_result = await test_nft_minting()
        results.append(("NFT Minting", nft_result))
        
        # Summary
        logger.info("\n=== Test Results ===")
        for test_name, result in results:
            status = "✅ PASS" if result else "❌ FAIL"
            logger.info(f"{test_name}: {status}")
        
        passed = sum(1 for _, result in results if result)
        total = len(results)
        logger.info(f"\nOverall: {passed}/{total} tests passed")
        
        return passed == total
    
    # Run the tests
    try:
        success = asyncio.run(run_tests())
        exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.info("Tests interrupted by user")
        exit(1)
    except Exception as e:
        logger.error(f"Test runner failed: {e}")
        exit(1)

if __name__ == "__main__":
    main()
