#!/usr/bin/env python3
"""
S3 Service Integration Example

This script demonstrates how to use the S3 service as a drop-in replacement 
for the Arweave service in the MatrixBot project.
"""

import asyncio
import os
import sys
import time
from typing import Optional

# Add the project root to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chatbot.integrations.arweave_uploader_client import ArweaveUploaderClient
from chatbot.tools.arweave_service import ArweaveService

# Import our S3 replacements
from s3_service.s3_uploader_client import S3UploaderClient
from s3_service.s3_service import S3Service


async def demonstrate_s3_replacement():
    """
    Demonstrate how to replace Arweave with S3 service.
    """
    print("🚀 S3 Service - Drop-in Replacement for Arweave Demo")
    print("=" * 60)
    
    # Configuration from environment
    s3_service_url = os.getenv("S3_SERVICE_URL", "http://localhost:8001")
    cloudfront_domain = os.getenv("CLOUDFRONT_DOMAIN", "https://your-cloudfront.com")
    s3_api_key = os.getenv("S3_SERVICE_API_KEY")
    
    print(f"S3 Service URL: {s3_service_url}")
    print(f"CloudFront Domain: {cloudfront_domain}")
    print(f"API Key configured: {'Yes' if s3_api_key else 'No'}")
    print()
    
    # Method 1: Direct S3 client usage
    print("1️⃣  Using S3UploaderClient directly:")
    print("-" * 40)
    
    s3_client = S3UploaderClient(
        uploader_service_url=s3_service_url,
        gateway_url=cloudfront_domain,
        api_key=s3_api_key
    )
    
    try:
        # Test service health
        wallet_info = await s3_client.get_wallet_info()
        if wallet_info:
            print(f"✅ S3 Service is healthy")
            print(f"   Address: {wallet_info.get('address')}")
            print(f"   Balance: {wallet_info.get('balance_ar')} AR")
            print(f"   Status: {wallet_info.get('status')}")
        else:
            print("❌ S3 Service is not accessible")
            return
            
        print()
        
        # Test data upload
        test_data = f"Hello from S3 service! Timestamp: {time.time()}"
        print(f"📤 Uploading test data: {test_data[:30]}...")
        
        s3_path = await s3_client.upload_data(
            data=test_data.encode('utf-8'),
            content_type="text/plain",
            tags={"App-Name": "S3-Demo", "Type": "Test"}
        )
        
        if s3_path:
            s3_url = s3_client.get_arweave_url(s3_path)
            print(f"✅ Upload successful!")
            print(f"   S3 Path: {s3_path}")
            print(f"   Public URL: {s3_url}")
            
            # Test download
            print(f"📥 Testing download...")
            downloaded_data = await download_and_verify(s3_url)
            if downloaded_data and downloaded_data.decode('utf-8') == test_data:
                print(f"✅ Download verification successful!")
            else:
                print(f"❌ Download verification failed")
        else:
            print(f"❌ Upload failed")
            
    except Exception as e:
        print(f"❌ Error with S3 client: {e}")
    
    print()
    
    # Method 2: Using S3Service wrapper (drop-in replacement for ArweaveService)
    print("2️⃣  Using S3Service wrapper (ArweaveService replacement):")
    print("-" * 60)
    
    s3_service = S3Service(s3_client)
    
    if not s3_service.is_configured():
        print("❌ S3Service is not configured")
        return
    
    print("✅ S3Service is configured")
    
    try:
        # Test image upload
        print("📤 Creating and uploading a test image...")
        
        # Create a simple test image (1x1 PNG)
        test_image_data = create_test_image()
        
        s3_image_url = await s3_service.upload_image_data(
            image_data=test_image_data,
            filename="test_image.png",
            content_type="image/png"
        )
        
        if s3_image_url:
            print(f"✅ Image upload successful!")
            print(f"   Image URL: {s3_image_url}")
            
            # Test URL checking
            is_s3_url = s3_service.is_arweave_url(s3_image_url)
            print(f"   Is S3 URL: {is_s3_url}")
            
        else:
            print(f"❌ Image upload failed")
            
        # Test external URL handling
        print("📤 Testing external URL upload...")
        external_url = "https://httpbin.org/image/png"
        
        try:
            s3_external_url = await s3_service.ensure_arweave_url(external_url)
            if s3_external_url:
                print(f"✅ External URL uploaded to S3!")
                print(f"   Original: {external_url}")
                print(f"   S3 URL: {s3_external_url}")
            else:
                print(f"❌ External URL upload failed")
        except Exception as e:
            print(f"❌ External URL upload error: {e}")
            
    except Exception as e:
        print(f"❌ Error with S3Service: {e}")
    
    print()
    
    # Method 3: Show how existing code works unchanged
    print("3️⃣  Drop-in replacement demonstration:")
    print("-" * 45)
    print("The S3 service can replace Arweave service with NO code changes!")
    print()
    print("Before (Arweave):")
    print("  client = ArweaveUploaderClient(arweave_url, gateway, key)")
    print("  service = ArweaveService(client)")
    print()
    print("After (S3):")
    print("  client = S3UploaderClient(s3_url, cloudfront, key)")
    print("  service = S3Service(client)")
    print()
    print("All method calls remain exactly the same! 🎉")
    
    print()
    print("🏁 Demo completed!")


async def download_and_verify(url: str) -> Optional[bytes]:
    """Download data from URL for verification."""
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            if response.status_code == 200:
                return response.content
            else:
                print(f"Download failed: {response.status_code}")
                return None
    except Exception as e:
        print(f"Download error: {e}")
        return None


def create_test_image() -> bytes:
    """Create a minimal test PNG image."""
    # Minimal 1x1 PNG image (base64 decoded)
    import base64
    png_data = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
    return base64.b64decode(png_data)


def print_migration_guide():
    """Print migration guide for existing projects."""
    print()
    print("📋 MIGRATION GUIDE")
    print("=" * 50)
    print()
    print("To migrate from Arweave to S3 service:")
    print()
    print("1. Environment Variables:")
    print("   OLD: ARWEAVE_INTERNAL_UPLOADER_SERVICE_URL")
    print("   NEW: S3_SERVICE_URL")
    print()
    print("   OLD: ARWEAVE_GATEWAY_URL") 
    print("   NEW: CLOUDFRONT_DOMAIN")
    print()
    print("   ADD: S3_API_KEY, S3_API_ENDPOINT")
    print()
    print("2. Docker Compose:")
    print("   Replace 'arweave-service' with 's3-service'")
    print("   Update environment variables")
    print()
    print("3. Code Changes:")
    print("   Option A: Import aliases (no changes needed)")
    print("     from s3_service.s3_uploader_client import ArweaveUploaderClient")
    print("     from s3_service.s3_service import ArweaveService")
    print()
    print("   Option B: Update imports")
    print("     from s3_service.s3_uploader_client import S3UploaderClient")
    print("     from s3_service.s3_service import S3Service")
    print()
    print("4. Benefits:")
    print("   ✅ No blockchain fees")
    print("   ✅ Faster uploads")
    print("   ✅ Better reliability")
    print("   ✅ Familiar S3 ecosystem")
    print("   ✅ CloudFront CDN benefits")


if __name__ == "__main__":
    print()
    print("🔄 S3 Service Demo & Migration Guide")
    print("=" * 60)
    
    # Check if required environment variables are set
    required_vars = ["S3_API_KEY", "S3_API_ENDPOINT", "CLOUDFRONT_DOMAIN"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print()
        print("⚠️  Missing required environment variables:")
        for var in missing_vars:
            print(f"   - {var}")
        print()
        print("Please set these variables before running the demo:")
        print("export S3_API_KEY='your-s3-api-key'")
        print("export S3_API_ENDPOINT='https://your-s3-api.com/upload'")
        print("export CLOUDFRONT_DOMAIN='https://your-cloudfront.com'")
        print("export S3_SERVICE_URL='http://localhost:8001'  # optional")
        print("export S3_SERVICE_API_KEY='your-service-key'   # optional")
        print()
        print_migration_guide()
    else:
        asyncio.run(demonstrate_s3_replacement())
        print_migration_guide()
