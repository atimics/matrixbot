#!/usr/bin/env python3
"""
Test the S3 service endpoints similar to the Arweave service test.
"""

import json
import os
import sys
import time
import requests
from typing import Optional


def test_s3_service(base_url: str = "http://localhost:8001"):
    """Test the S3 service endpoints"""
    print(f"🧪 Testing S3 Service at {base_url}")
    print("=" * 60)
    
    # Test 1: Health Check
    print("1. Testing health endpoint...")
    try:
        response = requests.get(f"{base_url}/health", timeout=10)
        if response.status_code == 200:
            health_data = response.json()
            print(f"   ✅ Health check passed")
            print(f"   📊 Status: {health_data.get('status')}")
            print(f"   🔗 Service ready: {health_data.get('wallet_ready')}")
            print(f"   🌐 Address: {health_data.get('wallet_address')}")
        else:
            print(f"   ❌ Health check failed: {response.status_code}")
            print(f"   📝 Response: {response.text}")
    except Exception as e:
        print(f"   ❌ Health check failed: {e}")
    
    print()
    
    # Test 2: Service Info (Wallet equivalent)
    print("2. Testing service info endpoint...")
    try:
        response = requests.get(f"{base_url}/wallet", timeout=10)
        if response.status_code == 200:
            wallet_data = response.json()
            print(f"   ✅ Service info retrieved")
            print(f"   🏠 Address: {wallet_data.get('address')}")
            print(f"   💰 Balance: {wallet_data.get('balance_ar')} AR")
            print(f"   📡 Status: {wallet_data.get('status')}")
        else:
            print(f"   ❌ Service info failed: {response.status_code}")
            print(f"   📝 Response: {response.text}")
            if response.status_code == 503:
                print("   ℹ️  This is expected if S3 service is not configured")
            
    except Exception as e:
        print(f"   ❌ Service info failed: {e}")
    
    print()
    
    # Test 3: Data Upload (if service is ready)
    print("3. Testing data upload endpoint (if service ready)...")
    try:
        # First check if service is ready
        health_response = requests.get(f"{base_url}/health", timeout=10)
        health_data = health_response.json()
        
        if health_data.get('wallet_ready', False):
            # Test with a simple text upload
            test_data = f"Test upload from S3 service at {time.time()}"
            upload_data = {
                'data': test_data,
                'content_type': 'text/plain',
                'tags': json.dumps({
                    'App-Name': 's3-service-test',
                    'Type': 'test-data',
                    'Timestamp': str(int(time.time()))
                })
            }
            
            response = requests.post(f"{base_url}/upload/data", data=upload_data, timeout=30)
            
            if response.status_code == 200:
                upload_result = response.json()
                print(f"   ✅ Data upload successful")
                print(f"   🆔 Transaction ID: {upload_result['transaction_id']}")
                print(f"   🌐 S3 URL: {upload_result['arweave_url']}")
                print(f"   📦 Data size: {upload_result['data_size']} bytes")
                print(f"   📄 Content type: {upload_result['content_type']}")
                
                # Test download
                s3_url = upload_result['arweave_url']
                print(f"   📥 Testing download from: {s3_url}")
                download_response = requests.get(s3_url, timeout=10)
                if download_response.status_code == 200:
                    downloaded_text = download_response.text
                    if downloaded_text == test_data:
                        print(f"   ✅ Download verification successful")
                    else:
                        print(f"   ❌ Download content mismatch")
                        print(f"   Expected: {test_data[:50]}...")
                        print(f"   Got: {downloaded_text[:50]}...")
                else:
                    print(f"   ⚠️  Download test failed: {download_response.status_code}")
                    
            else:
                print(f"   ❌ Data upload failed: {response.status_code}")
                print(f"   📝 Response: {response.text}")
        else:
            print(f"   ⏭️  Skipping upload test - service not ready")
            print(f"   💡 Check S3_API_KEY, S3_API_ENDPOINT, and CLOUDFRONT_DOMAIN")
            
    except Exception as e:
        print(f"   ❌ Upload test failed: {e}")
    
    print()
    
    # Test 4: File Upload
    print("4. Testing file upload endpoint...")
    try:
        health_response = requests.get(f"{base_url}/health", timeout=10)
        health_data = health_response.json()
        
        if health_data.get('wallet_ready', False):
            # Create a test file
            test_file_content = f"Test file upload at {time.time()}"
            
            files = {'file': ('test.txt', test_file_content.encode(), 'text/plain')}
            data = {
                'tags': json.dumps({
                    'App-Name': 's3-service-test',
                    'Type': 'test-file'
                })
            }
            
            response = requests.post(f"{base_url}/upload", files=files, data=data, timeout=30)
            
            if response.status_code == 200:
                upload_result = response.json()
                print(f"   ✅ File upload successful")
                print(f"   🆔 Transaction ID: {upload_result['transaction_id']}")
                print(f"   🌐 S3 URL: {upload_result['arweave_url']}")
                print(f"   📦 File size: {upload_result['data_size']} bytes")
                print(f"   📄 Content type: {upload_result['content_type']}")
            else:
                print(f"   ❌ File upload failed: {response.status_code}")
                print(f"   📝 Response: {response.text}")
        else:
            print(f"   ⏭️  Skipping file upload test - service not ready")
            
    except Exception as e:
        print(f"   ❌ File upload test failed: {e}")
    
    print()
    
    # Test 5: API Key Authentication (if configured)
    print("5. Testing API key authentication...")
    api_key = os.getenv("S3_SERVICE_API_KEY")
    if api_key:
        try:
            # Test with correct API key
            headers = {"X-API-Key": api_key}
            test_data = "API key test data"
            upload_data = {'data': test_data, 'content_type': 'text/plain'}
            
            response = requests.post(f"{base_url}/upload/data", data=upload_data, headers=headers, timeout=10)
            if response.status_code == 200:
                print(f"   ✅ API key authentication working")
            else:
                print(f"   ❌ API key test failed: {response.status_code}")
                
            # Test with wrong API key
            wrong_headers = {"X-API-Key": "wrong-key"}
            response = requests.post(f"{base_url}/upload/data", data=upload_data, headers=wrong_headers, timeout=10)
            if response.status_code == 401:
                print(f"   ✅ API key validation working (rejected wrong key)")
            else:
                print(f"   ⚠️  API key validation might not be working properly")
                
        except Exception as e:
            print(f"   ❌ API key test failed: {e}")
    else:
        print(f"   ⏭️  No S3_SERVICE_API_KEY set, skipping API key test")
    
    print()
    print("🏁 S3 Service testing completed!")
    print()
    
    # Print configuration help
    print("💡 Configuration Tips:")
    print("   - Set S3_API_KEY: Your S3 upload service API key")
    print("   - Set S3_API_ENDPOINT: Your S3 upload service endpoint")
    print("   - Set CLOUDFRONT_DOMAIN: Your CloudFront distribution URL")
    print("   - Set S3_SERVICE_API_KEY: Optional API key for this service")


def print_comparison():
    """Print comparison between Arweave and S3 service."""
    print()
    print("🔄 Arweave vs S3 Service Comparison")
    print("=" * 60)
    print()
    print("Feature                 | Arweave Service    | S3 Service")
    print("-" * 60)
    print("Upload Speed           | Slow (blockchain)  | Fast (direct S3)")
    print("Cost                   | AR tokens needed   | S3 storage costs")
    print("Availability           | Network dependent  | High (AWS/CDN)")
    print("Permanence             | Permanent          | Configurable")
    print("API Compatibility      | Original           | 100% compatible")
    print("Setup Complexity       | Wallet required    | Environment vars")
    print("Performance            | Variable           | Consistent")
    print("Global Access          | Yes                | Yes (CloudFront)")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test S3 service endpoints")
    parser.add_argument("--url", default="http://localhost:8001", 
                       help="Base URL of the S3 service (default: http://localhost:8001)")
    parser.add_argument("--compare", action="store_true",
                       help="Show comparison between Arweave and S3 service")
    
    args = parser.parse_args()
    
    if args.compare:
        print_comparison()
    
    test_s3_service(args.url)
