#!/usr/bin/env python3
"""
S3 Service Test Script

Simple test to verify S3 service configuration and functionality.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from chatbot.tools.s3_service import S3Service
from chatbot.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_s3_service():
    """Test S3 service configuration and basic functionality."""
    
    print("=== S3 Service Test ===")
    
    # Check configuration
    print(f"S3_API_ENDPOINT: {settings.S3_API_ENDPOINT}")
    print(f"S3_API_KEY: {'***' if settings.S3_API_KEY else 'NOT SET'}")
    print(f"CLOUDFRONT_DOMAIN: {settings.CLOUDFRONT_DOMAIN}")
    
    if not all([settings.S3_API_ENDPOINT, settings.S3_API_KEY, settings.CLOUDFRONT_DOMAIN]):
        print("❌ ERROR: S3 configuration incomplete. Please set S3_API_ENDPOINT, S3_API_KEY, and CLOUDFRONT_DOMAIN in your .env file")
        return False
    
    # Initialize service
    s3_service = S3Service()
    
    if not s3_service.is_configured():
        print("❌ ERROR: S3 service not properly configured")
        return False
    
    print("✅ S3 service configured successfully")
    
    # Test with a small sample image data
    print("\n=== Testing Upload ===")
    
    # Create a simple 1x1 PNG image (smallest possible)
    sample_png_data = bytes([
        0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,  # PNG signature
        0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,  # IHDR chunk
        0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,  # 1x1 dimensions
        0x08, 0x06, 0x00, 0x00, 0x00, 0x1F, 0x15, 0xC4,  # RGBA, CRC
        0x89, 0x00, 0x00, 0x00, 0x0A, 0x49, 0x44, 0x41,  # IDAT chunk
        0x54, 0x08, 0xD7, 0x63, 0x00, 0x00, 0x00, 0x02,  # compressed data
        0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45,  # CRC, IEND
        0x4E, 0x44, 0xAE, 0x42, 0x60, 0x82                # chunk
    ])
    
    try:
        s3_url = await s3_service.upload_image_data(
            sample_png_data, 
            "test_image.png", 
            "image/png"
        )
        
        if s3_url:
            print(f"✅ Upload successful: {s3_url}")
            
            # Test URL accessibility
            print(f"\n=== Testing Download ===")
            try:
                downloaded_data = await s3_service.download_file_data(s3_url)
                if downloaded_data and len(downloaded_data) > 0:
                    print(f"✅ Download successful: {len(downloaded_data)} bytes")
                    return True
                else:
                    print("❌ Downloaded data is empty")
                    return False
            except Exception as e:
                print(f"❌ Download failed: {e}")
                return False
        else:
            print("❌ Upload failed - no URL returned")
            return False
            
    except Exception as e:
        print(f"❌ Upload failed: {e}")
        return False


if __name__ == "__main__":
    try:
        success = asyncio.run(test_s3_service())
        if success:
            print("\n🎉 All S3 tests passed!")
            exit(0)
        else:
            print("\n💥 S3 tests failed!")
            exit(1)
    except KeyboardInterrupt:
        print("\n⏹️  Test interrupted")
        exit(1)
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        exit(1)
