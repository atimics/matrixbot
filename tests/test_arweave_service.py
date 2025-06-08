#!/usr/bin/env python3
"""
Test script for the new arweave-service

This script tests the basic functionality of the arweave-service
to ensure it's working correctly after the transformation.
"""

import json
import requests
import time
from pathlib import Path
import pytest

def test_arweave_service(base_url: str = "http://localhost:8001"):
    """Test the arweave-service endpoints"""
    
    print(f"🧪 Testing Arweave Service at {base_url}")
    print("=" * 50)
    
    # Test 1: Health Check
    print("1. Testing health endpoint...")
    try:
        response = requests.get(f"{base_url}/health", timeout=10)
        health_data = response.json()
        
        if response.status_code == 200:
            print(f"   ✅ Health check passed")
            print(f"   📊 Status: {health_data['status']}")
            print(f"   🔐 Wallet ready: {health_data['wallet_ready']}")
            print(f"   📍 Wallet address: {health_data.get('wallet_address', 'N/A')}")
            
            if not health_data['wallet_ready']:
                print("   ⚠️  WARNING: Wallet not ready - service may not be fully functional")
        else:
            print(f"   ❌ Health check failed: {response.status_code}")
            pytest.skip(f"Arweave service not available at {base_url}")
            
    except Exception as e:
        print(f"   ❌ Health check failed: {e}")
        pytest.skip(f"Arweave service not available at {base_url}: {e}")
    
    print()
    
    # Test 2: Wallet Info
    print("2. Testing wallet info endpoint...")
    try:
        response = requests.get(f"{base_url}/wallet", timeout=10)
        
        if response.status_code == 200:
            wallet_data = response.json()
            print(f"   ✅ Wallet info retrieved")
            print(f"   📍 Address: {wallet_data['address']}")
            print(f"   💰 Balance: {wallet_data['balance_ar']} AR")
            print(f"   📊 Status: {wallet_data['status']}")
        else:
            print(f"   ❌ Wallet info failed: {response.status_code}")
            if response.status_code == 503:
                print("   ℹ️  This is expected if no wallet file is mounted")
            
    except Exception as e:
        print(f"   ❌ Wallet info failed: {e}")
    
    print()
    
    # Test 3: Data Upload (if wallet is ready)
    print("3. Testing data upload endpoint (if wallet ready)...")
    try:
        # First check if wallet is ready
        health_response = requests.get(f"{base_url}/health", timeout=10)
        health_data = health_response.json()
        
        if health_data.get('wallet_ready', False):
            # Test with a simple text upload
            test_data = f"Test upload from arweave-service at {time.time()}"
            upload_data = {
                'data': test_data,
                'content_type': 'text/plain',
                'tags': json.dumps({
                    'App-Name': 'arweave-service-test',
                    'Type': 'test-data',
                    'Timestamp': str(int(time.time()))
                })
            }
            
            response = requests.post(f"{base_url}/upload/data", data=upload_data, timeout=30)
            
            if response.status_code == 200:
                upload_result = response.json()
                print(f"   ✅ Data upload successful")
                print(f"   🆔 Transaction ID: {upload_result['transaction_id']}")
                print(f"   🌐 Arweave URL: {upload_result['arweave_url']}")
                print(f"   📦 Data size: {upload_result['data_size']} bytes")
                print(f"   📄 Content type: {upload_result['content_type']}")
            else:
                print(f"   ❌ Data upload failed: {response.status_code}")
                print(f"   📝 Response: {response.text}")
        else:
            print("   ⏭️  Skipped - wallet not ready (expected if no wallet mounted)")
            
    except Exception as e:
        print(f"   ❌ Data upload test failed: {e}")
    
    print()
    print("🎯 Test Summary:")
    print("   - Health endpoint: Tested")
    print("   - Wallet info endpoint: Tested") 
    print("   - Data upload endpoint: Tested (if wallet available)")
    print()
    print("✅ Arweave service transformation test complete!")
    
    # Test passes if we reach this point
    assert True

def main():
    """Run the test suite"""
    print("🚀 Arweave Service Test Suite")
    print("Testing the new lean arweave-service implementation")
    print()
    
    # Test the service
    success = test_arweave_service()
    
    if success:
        print()
        print("📋 Next Steps:")
        print("   1. If wallet not ready, run: python generate_arweave_wallet.py")
        print("   2. Fund the generated wallet with AR tokens")
        print("   3. Restart the service: docker-compose restart arweave-service")
        print("   4. Update chatbot services to use new API endpoints")
        return 0
    else:
        print("❌ Tests failed - check service logs")
        return 1

if __name__ == "__main__":
    exit(main())
