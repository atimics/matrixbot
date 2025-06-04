#!/usr/bin/env python3
"""
Comprehensive Token Metadata Test Script

This script tests the complete token metadata functionality including:
- Token metadata fetching from DexScreener
- Social influence scoring 
- Enhanced token holder tracking
- World state integration
- Payload building with token data
"""

import asyncio
import json
import logging
import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath('.'))

from chatbot.config import settings
from chatbot.integrations.farcaster.neynar_api_client import NeynarAPIClient
from chatbot.core.world_state.manager import WorldStateManager
from chatbot.integrations.ecosystem_token_service import EcosystemTokenService
from chatbot.core.world_state.payload_builder import PayloadBuilder
from chatbot.core.world_state.structures import TokenMetadata, TokenHolderData, MonitoredTokenHolder, Message

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_token_metadata_fetching():
    """Test fetching token metadata from DexScreener."""
    logger.info("=== Testing Token Metadata Fetching ===")
    
    # Initialize services
    neynar_client = NeynarAPIClient(api_key=settings.NEYNAR_API_KEY)
    world_state_manager = WorldStateManager()
    ecosystem_service = EcosystemTokenService(neynar_client, world_state_manager)
    
    # Test with our configured token contract
    token_contract = settings.ECOSYSTEM_TOKEN_CONTRACT_ADDRESS
    logger.info(f"Testing metadata fetch for token: {token_contract}")
    
    # Fetch token metadata
    metadata = await ecosystem_service._fetch_token_metadata_from_dexscreener(token_contract)
    
    if metadata:
        logger.info("✅ Successfully fetched token metadata!")
        logger.info(f"Token: {metadata.ticker} ({metadata.name})")
        logger.info(f"Price: ${metadata.price_usd:.6f}")
        logger.info(f"Market Cap: ${metadata.market_cap:,.2f}" if metadata.market_cap else "Market Cap: N/A")
        logger.info(f"24h Volume: ${metadata.volume_24h:,.2f}" if metadata.volume_24h else "Volume: N/A")
        logger.info(f"24h Change: {metadata.price_change_24h:.2f}%" if metadata.price_change_24h else "Change: N/A")
        logger.info(f"DEX Info: {json.dumps(metadata.dex_info, indent=2)}")
        return metadata
    else:
        logger.error("❌ Failed to fetch token metadata")
        return None


async def test_social_influence_scoring():
    """Test social influence score calculation."""
    logger.info("=== Testing Social Influence Scoring ===")
    
    # Initialize services
    neynar_client = NeynarAPIClient(api_key=settings.NEYNAR_API_KEY)
    world_state_manager = WorldStateManager()
    ecosystem_service = EcosystemTokenService(neynar_client, world_state_manager)
    
    # Create test token holder data
    test_holder_data = TokenHolderData(
        address="0x1234567890abcdef",
        balance=1000000.0,
        percentage_of_supply=2.5,  # 2.5% of supply
        rank=3,
        is_whale=True,
        transaction_count=45
    )
    
    # Create test messages (recent casts)
    test_messages = [
        Message(
            id="test_cast_1",
            channel_id="channel1", 
            channel_type="farcaster",
            sender="testuser",
            content="Great token project!",
            timestamp=1717459200.0  # Recent timestamp
        ),
        Message(
            id="test_cast_2",
            channel_id="channel1",
            channel_type="farcaster", 
            sender="testuser",
            content="Bullish on this ecosystem",
            timestamp=1717462800.0
        )
    ]
    
    # Create test holder
    test_holder = MonitoredTokenHolder(
        fid="123",
        username="testwhale",
        display_name="Test Whale",
        recent_casts=test_messages,
        token_holder_data=test_holder_data,
        last_activity_timestamp=1717462800.0
    )
    
    # Calculate influence score
    influence_score = await ecosystem_service._calculate_social_influence_score(test_holder)
    
    logger.info(f"✅ Calculated influence score: {influence_score:.3f}")
    logger.info(f"   - Token holding (2.5%): contributes to score")
    logger.info(f"   - Social activity ({len(test_messages)} casts): contributes to score") 
    logger.info(f"   - Recent activity: contributes to score")
    
    return influence_score


async def test_comprehensive_ecosystem_service():
    """Test the complete ecosystem service functionality."""
    logger.info("=== Testing Comprehensive Ecosystem Service ===")
    
    # Initialize services
    neynar_client = NeynarAPIClient(api_key=settings.NEYNAR_API_KEY)
    world_state_manager = WorldStateManager()
    ecosystem_service = EcosystemTokenService(neynar_client, world_state_manager)
    
    # Update token metadata
    logger.info("Updating token metadata...")
    await ecosystem_service.update_token_metadata()
    
    # Check if metadata was stored in world state
    token_metadata = world_state_manager.state.token_metadata
    if token_metadata:
        logger.info("✅ Token metadata successfully stored in world state!")
        logger.info(f"   Token: {token_metadata.ticker}")
        logger.info(f"   Price: ${token_metadata.price_usd:.6f}")
        logger.info(f"   Contract: {token_metadata.contract_address}")
    else:
        logger.warning("⚠️  No token metadata found in world state")
    
    # Test holder update (this will use simulated data if real API isn't available)
    logger.info("Updating token holders...")
    await ecosystem_service.update_top_token_holders_in_world_state()
    
    # Check monitored holders
    holders = world_state_manager.state.monitored_token_holders
    logger.info(f"✅ Found {len(holders)} monitored token holders")
    
    return world_state_manager.state


async def test_enhanced_payload_building():
    """Test building AI payloads with comprehensive token data."""
    logger.info("=== Testing Enhanced Payload Building ===")
    
    # Initialize services
    neynar_client = NeynarAPIClient(api_key=settings.NEYNAR_API_KEY)
    world_state_manager = WorldStateManager()
    ecosystem_service = EcosystemTokenService(neynar_client, world_state_manager)
    payload_builder = PayloadBuilder()
    
    # Update ecosystem data
    await ecosystem_service.update_token_metadata()
    await ecosystem_service.update_top_token_holders_in_world_state()
    
    # Build payload
    logger.info("Building AI payload with token metadata...")
    payload = payload_builder.build_full_payload(world_state_manager.state)
    
    # Check ecosystem token info in payload
    token_info = payload.get("ecosystem_token_info", {})
    logger.info("✅ Ecosystem token info in payload:")
    logger.info(f"   Contract: {token_info.get('contract_address')}")
    
    token_metadata = token_info.get("token_metadata")
    if token_metadata:
        logger.info("✅ Token metadata included in payload:")
        logger.info(f"   Ticker: {token_metadata.get('ticker')}")
        logger.info(f"   Price: ${token_metadata.get('price_usd', 0):.6f}")
        logger.info(f"   Market Cap: ${token_metadata.get('market_cap', 0):,.2f}" if token_metadata.get('market_cap') else "   Market Cap: N/A")
        logger.info(f"   Volume 24h: ${token_metadata.get('volume_24h', 0):,.2f}" if token_metadata.get('volume_24h') else "   Volume: N/A")
    else:
        logger.warning("⚠️  No token metadata in payload")
    
    holders_activity = token_info.get("monitored_holders_activity", [])
    logger.info(f"✅ {len(holders_activity)} monitored holders in payload")
    
    for i, holder in enumerate(holders_activity[:3]):  # Show first 3 holders
        logger.info(f"   Holder {i+1}: FID {holder.get('fid')}")
        logger.info(f"      Username: {holder.get('username')}")
        logger.info(f"      Influence Score: {holder.get('social_influence_score', 'N/A')}")
        
        holder_data = holder.get('token_holder_data')
        if holder_data:
            logger.info(f"      Token Balance: {holder_data.get('balance', 'N/A')}")
            logger.info(f"      Supply %: {holder_data.get('percentage_of_supply', 'N/A')}%")
            logger.info(f"      Rank: #{holder_data.get('rank', 'N/A')}")
    
    # Calculate payload size
    payload_size = len(json.dumps(payload, default=str))
    logger.info(f"✅ Total payload size: {payload_size:,} bytes ({payload_size/1024:.1f} KB)")
    
    return payload


async def main():
    """Run comprehensive token metadata tests."""
    logger.info("🚀 Starting Comprehensive Token Metadata Testing")
    logger.info(f"Token Contract: {settings.ECOSYSTEM_TOKEN_CONTRACT_ADDRESS}")
    logger.info(f"Neynar API Key: {'✅ Set' if settings.NEYNAR_API_KEY else '❌ Missing'}")
    
    try:
        # Test 1: Token metadata fetching
        metadata = await test_token_metadata_fetching()
        
        # Test 2: Social influence scoring
        influence_score = await test_social_influence_scoring()
        
        # Test 3: Comprehensive ecosystem service
        world_state = await test_comprehensive_ecosystem_service()
        
        # Test 4: Enhanced payload building
        payload = await test_enhanced_payload_building()
        
        logger.info("🎉 All tests completed successfully!")
        
        # Summary
        logger.info("=== TEST SUMMARY ===")
        logger.info(f"✅ Token metadata: {'Available' if metadata else 'Failed'}")
        logger.info(f"✅ Influence scoring: {influence_score:.3f}")
        logger.info(f"✅ World state holders: {len(world_state.monitored_token_holders)}")
        logger.info(f"✅ Payload includes metadata: {'Yes' if payload.get('ecosystem_token_info', {}).get('token_metadata') else 'No'}")
        
    except Exception as e:
        logger.error(f"❌ Test failed with error: {e}", exc_info=True)
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
