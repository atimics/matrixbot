#!/usr/bin/env python3
"""
Test script for simplified Farcaster mini-app recommendation feature.

Tests the streamlined workflow:
1. Database population with AI summaries
2. Natural language search functionality
3. Proactive recommendation detection
4. End-to-end recommendation generation
"""

import asyncio
import logging
import os
import sys

# Add the project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from chatbot.core.world_state.manager import WorldStateManager
from chatbot.tools.mini_app_tools import UpdateMiniAppSummaryTool, SearchMiniAppsTool
from chatbot.tools.base import ActionContext

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# Test data - sample mini-apps with AI-generated summaries (digital index cards)
TEST_MINI_APPS = [
    {
        "name": "Warpcast",
        "url": "https://warpcast.com",
        "ai_summary": "The flagship Farcaster client with the most polished experience. Great for newcomers to Farcaster or anyone wanting a clean, feature-rich interface for browsing feeds, posting casts, and managing social connections. Think of it as the 'Twitter app' of Farcaster."
    },
    {
        "name": "Farcaster Storage",
        "url": "https://storage.farcaster.xyz",
        "ai_summary": "Official tool for managing your Farcaster storage allocation. Perfect if you're running out of space for casts, need to purchase additional storage units, or want to monitor your account usage. Essential for active Farcaster users who cast frequently or share media content."
    },
    {
        "name": "Paragraph",
        "url": "https://paragraph.xyz",
        "ai_summary": "Web3-native newsletter and blogging platform that integrates beautifully with Farcaster. Perfect for content creators, writers, or anyone who wants to monetize their writing through crypto. You can publish long-form content and automatically share it to your Farcaster feed."
    },
    {
        "name": "Zora",
        "url": "https://zora.co",
        "ai_summary": "NFT marketplace and creation platform with seamless Farcaster integration. Ideal for artists wanting to mint and sell digital art, collectors looking to discover new NFTs, or anyone interested in the intersection of social media and digital ownership. Share your creations directly to Farcaster."
    },
    {
        "name": "Bountycaster",
        "url": "https://bountycaster.xyz",
        "ai_summary": "Bounty platform for posting and completing tasks within the Farcaster community. Great for freelancers looking for gigs, project owners who need specific tasks completed, or anyone wanting to monetize their skills within the Farcaster ecosystem."
    },
    {
        "name": "Yoink",
        "url": "https://yoink.party",
        "ai_summary": "Playful social game where you can 'steal' virtual items from other users in a fun, non-destructive way. Great for adding some lighthearted entertainment to your Farcaster experience. Perfect for communities that enjoy casual gaming and social interaction."
    },
    {
        "name": "Airstack",
        "url": "https://airstack.xyz",
        "ai_summary": "Comprehensive Web3 social data platform that includes Farcaster analytics and insights. Perfect for developers building Farcaster apps, researchers studying social networks, or anyone who wants deep data about Farcaster user behavior and social graphs."
    }
]


async def test_database_population():
    """Test adding mini-apps to the simplified database."""
    logger.info("Testing simplified database population...")
    
    # Initialize world state manager
    world_state_manager = WorldStateManager()
    context = ActionContext(world_state_manager=world_state_manager)
    
    # Create the update tool
    update_tool = UpdateMiniAppSummaryTool()
    
    # Test adding mini-apps
    for app_data in TEST_MINI_APPS:
        result = await update_tool.execute(app_data, context)
        
        if result.get("status") == "success":
            logger.info(f"✅ Successfully added: {app_data['name']}")
        else:
            logger.error(f"❌ Failed to add {app_data['name']}: {result}")
    
    # Verify the apps are in the database
    total_apps = len(world_state_manager.state.mini_app_database)
    logger.info(f"Total mini-apps in database: {total_apps}")
    
    return world_state_manager


async def test_search_functionality(world_state_manager):
    """Test the simplified search functionality with natural language queries."""
    logger.info("Testing simplified search functionality...")
    
    context = ActionContext(world_state_manager=world_state_manager)
    search_tool = SearchMiniAppsTool()
    
    # Test various natural language queries
    test_queries = [
        ("storage space running out", "Should find Farcaster Storage"),
        ("fun games entertainment", "Should find Yoink"),
        ("analytics track performance", "Should find Airstack"),
        ("create content writing", "Should find Paragraph"),
        ("NFT art marketplace", "Should find Zora"),
        ("work freelance tasks", "Should find Bountycaster"),
        ("beginner new to farcaster", "Should find Warpcast")
    ]
    
    for query, expected in test_queries:
        logger.info(f"\nTesting query: '{query}' ({expected})")
        
        result = await search_tool.execute({
            "query": query,
            "limit": 3
        }, context)
        
        if result.get("status") == "success":
            logger.info(f"✅ Search successful")
            message = result.get("message", "")
            logger.info(f"Response: {message[:200]}...")
            
            results = result.get("results", [])
            logger.info(f"Found {len(results)} apps")
            for app in results:
                logger.info(f"  - {app['name']}: {app['ai_summary'][:50]}...")
        else:
            logger.error(f"❌ Search failed: {result}")


async def test_proactive_detection():
    """Test proactive opportunity detection for mini-app recommendations."""
    logger.info("Testing proactive opportunity detection...")
    
    # Import the proactive engine
    try:
        from chatbot.core.proactive.proactive_engine import ProactiveEngine
        
        # Initialize world state manager
        world_state_manager = WorldStateManager()
        proactive_engine = ProactiveEngine(world_state_manager)
        
        # Test messages that should trigger mini-app recommendations
        test_messages = [
            "I'm running out of storage space on Farcaster",
            "What are some fun things to do on Farcaster?",
            "I want to start creating content",
            "Are there any games I can play?",
            "How can I track my Farcaster analytics?",
            "I'm looking for NFT platforms",
            "Where can I find freelance work?"
        ]
        
        for message_content in test_messages:
            logger.info(f"\nTesting message: '{message_content}'")
            
            # Create a simple message-like structure
            message_data = {
                "content": message_content,
                "sender": "testuser",
                "channel_id": "test_channel"
            }
            
            try:
                # Test opportunity detection
                opportunities = await proactive_engine._detect_mini_app_opportunities(message_data)
                
                if opportunities:
                    logger.info(f"✅ Detected {len(opportunities)} mini-app opportunities")
                    for opp in opportunities:
                        logger.info(f"  - Type: {opp.get('type')}")
                        logger.info(f"  - Context: {opp.get('context', {}).get('detected_need', 'N/A')}")
                else:
                    logger.info("ℹ️  No mini-app opportunities detected")
                    
            except Exception as e:
                logger.error(f"❌ Error detecting opportunities: {e}")
    
    except ImportError:
        logger.info("ℹ️  ProactiveEngine not available - skipping proactive detection test")


async def test_engagement_strategy():
    """Test the mini-app recommendation engagement strategy."""
    logger.info("Testing mini-app recommendation engagement strategy...")
    
    # Initialize world state manager and populate it
    world_state_manager = await test_database_population()
    
    try:
        # Import engagement strategy
        from chatbot.core.proactive.engagement_strategies import MiniAppRecommendationStrategy
        
        strategy = MiniAppRecommendationStrategy()
        
        # Test opportunity
        test_opportunity = {
            "type": "mini_app_recommendation",
            "context": {
                "detected_need": "storage",
                "user_query": "I'm running out of storage space"
            }
        }
        
        # Test if strategy can handle this opportunity
        can_handle = strategy.can_handle(test_opportunity)
        logger.info(f"Strategy can handle opportunity: {can_handle}")
        
        if can_handle:
            # Generate engagement plan
            engagement_plan = await strategy.generate_engagement_plan(
                test_opportunity, 
                world_state_manager
            )
            
            if engagement_plan:
                logger.info(f"✅ Generated engagement plan:")
                logger.info(f"  - Priority: {engagement_plan.get('priority')}")
                logger.info(f"  - Action: {engagement_plan.get('action_type')}")
                logger.info(f"  - Message: {engagement_plan.get('message', '')[:100]}...")
            else:
                logger.error("❌ Failed to generate engagement plan")
    
    except ImportError:
        logger.info("ℹ️  MiniAppRecommendationStrategy not available - skipping strategy test")


async def test_end_to_end_workflow():
    """Test the complete end-to-end workflow."""
    logger.info("Testing complete end-to-end workflow...")
    
    try:
        # 1. Setup database
        logger.info("1. Setting up database...")
        world_state_manager = await test_database_population()
        
        # 2. Test search
        logger.info("\n2. Testing search...")
        await test_search_functionality(world_state_manager)
        
        # 3. Test proactive detection
        logger.info("\n3. Testing proactive detection...")
        await test_proactive_detection()
        
        # 4. Test engagement strategy
        logger.info("\n4. Testing engagement strategy...")
        await test_engagement_strategy()
        
        logger.info("\n✅ End-to-end workflow test completed successfully!")
        
    except Exception as e:
        logger.error(f"❌ End-to-end test failed: {e}", exc_info=True)


async def interactive_test():
    """Run an interactive test session."""
    print("\n🔍 Interactive Mini-App Recommendation Test")
    print("=" * 50)
    
    # Setup
    world_state_manager = await test_database_population()
    context = ActionContext(world_state_manager=world_state_manager)
    search_tool = SearchMiniAppsTool()
    
    print("Try natural language queries like:")
    print("- 'I need more storage space'")
    print("- 'fun games to play'")
    print("- 'analytics and tracking'")
    print("\nType queries, or 'quit' to exit:")
    
    while True:
        try:
            query = input("\n💬 Query: ").strip()
            
            if query.lower() in ['quit', 'exit', 'q']:
                break
                
            if not query:
                continue
                
            result = await search_tool.execute({
                "query": query,
                "limit": 3
            }, context)
            
            if result.get("status") == "success":
                print(result.get("message", ""))
            else:
                print(f"❌ Search failed: {result.get('error')}")
                
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"❌ Error: {e}")
    
    print("\n👋 Interactive test complete!")


async def main():
    """Main test function."""
    print("🚀 Simplified Farcaster Mini-App Recommendation System Test")
    print("=" * 65)
    print("Testing the streamlined approach with AI summaries as the 'brain'")
    print()
    
    try:
        # Run all tests
        await test_end_to_end_workflow()
        
        # Offer interactive test
        print("\n" + "=" * 65)
        response = input("Would you like to try the interactive test? (y/n): ").strip().lower()
        
        if response in ['y', 'yes']:
            await interactive_test()
        
        print("\n✅ All tests completed!")
        
    except Exception as e:
        logger.error(f"❌ Test suite failed: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())
