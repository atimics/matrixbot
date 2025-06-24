#!/usr/bin/env python3
"""
Test script for enhanced Farcaster search functionality.
"""
import asyncio
import os
import sys
import json
from typing import Dict, Any

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from chatbot.integrations.farcaster.neynar_api_client import NeynarAPIClient


async def test_enhanced_search():
    """Test the enhanced search functionality with various parameters."""
    
    # Get API key from environment or config
    api_key = os.getenv("NEYNAR_API_KEY")
    if not api_key:
        try:
            with open("data/config.json", "r") as f:
                config = json.load(f)
                api_key = config.get("neynar_api_key")
        except FileNotFoundError:
            print("Error: NEYNAR_API_KEY not found in environment or config.json")
            return
    
    if not api_key:
        print("Error: No API key found")
        return
    
    print("Testing Enhanced Farcaster Search Functionality")
    print("=" * 50)
    
    # Initialize API client
    client = NeynarAPIClient(api_key=api_key)
    
    try:
        # Test 1: Basic semantic search
        print("\n1. Testing basic semantic search (hybrid mode):")
        result = await client.search_casts(
            query="bitcoin price prediction",
            mode="hybrid",
            sort_type="algorithmic",
            limit=5
        )
        print(f"Found {len(result.get('casts', []))} casts")
        if result.get('casts'):
            print(f"First cast: {result['casts'][0].get('text', '')[:100]}...")
        
        # Test 2: Literal search with operators
        print("\n2. Testing literal search with operators:")
        result = await client.search_casts(
            query='"machine learning" + AI',
            mode="literal", 
            sort_type="desc_chron",
            limit=3
        )
        print(f"Found {len(result.get('casts', []))} casts")
        
        # Test 3: Channel-specific search
        print("\n3. Testing channel-specific search:")
        result = await client.search_casts(
            query="gm",
            channel_id="degen",
            mode="semantic",
            limit=5
        )
        print(f"Found {len(result.get('casts', []))} casts in degen channel")
        
        # Test 4: Date-filtered search
        print("\n4. Testing date-filtered search:")
        result = await client.search_casts(
            query="crypto after:2024-12-01",
            mode="hybrid",
            sort_type="algorithmic",
            limit=5
        )
        print(f"Found {len(result.get('casts', []))} casts after Dec 1, 2024")
        
        # Test 5: Author-specific search
        print("\n5. Testing author-specific search:")
        # Using a well-known FID like Vitalik (FID 5)
        result = await client.search_casts(
            query="ethereum",
            author_fid=5,
            mode="semantic",
            limit=3
        )
        print(f"Found {len(result.get('casts', []))} casts by author FID 5")
        
        print("\n✅ All tests completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(test_enhanced_search())
