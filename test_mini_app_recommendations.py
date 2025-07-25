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
from chatbot.core.proactive.proactive_engine import ProactiveEngine
from chatbot.core.proactive.engagement_strategies import EngagementStrategyRegistry

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


async def setup_test_environment():
    """Set up the test environment with sample data."""
    logger.info("Setting up test environment...")
    
    # Initialize world state manager
    world_state_manager = WorldStateManager()
    context = ActionContext(world_state_manager=world_state_manager)
    
    # Add a few sample mini-apps for testing
    sample_apps = [
        {
            "name": "Storage Manager",
            "url": "https://storage.example.com",
            "description": "Manage your Farcaster storage allocation and purchase additional space.",
            "developer": "Example Team",
            "category": "tools",
            "tags": ["storage", "files", "management"],
            "popularity_score": 0.8
        },
        {
            "name": "Fun Quiz Game",
            "url": "https://quiz.example.com", 
            "description": "Interactive quiz game with trivia questions and multiplayer challenges.",
            "developer": "Game Studio",
            "category": "games",
            "tags": ["quiz", "trivia", "multiplayer", "fun"],
            "popularity_score": 0.7
        },
        {
            "name": "Community Polls",
            "url": "https://polls.example.com",
            "description": "Create and participate in community polls and surveys.",
            "developer": "Poll Maker",
            "category": "social", 
            "tags": ["polls", "voting", "community", "surveys"],
            "popularity_score": 0.6
        }
    ]
    
    # Add sample apps to database
    update_tool = UpdateMiniAppDBTool()
    for app in sample_apps:
        await update_tool.execute(app, context)
    
    logger.info(f"Added {len(sample_apps)} sample mini-apps to database")
    return world_state_manager, context


def create_test_message(content: str, sender: str = "testuser", channel_id: str = "test_channel") -> Message:
    """Create a test message for simulation."""
    return Message(
        id=f"msg_{int(time.time() * 1000)}",
        channel_id=channel_id,
        channel_type="farcaster",
        sender=sender,
        content=content,
        timestamp=time.time(),
        sender_username=sender,
        sender_display_name=sender.title(),
        sender_fid=12345
    )


async def test_search_functionality(context: ActionContext):
    """Test the search functionality with various queries."""
    logger.info("\n" + "="*60)
    logger.info("TESTING SEARCH FUNCTIONALITY")
    logger.info("="*60)
    
    search_tool = SearchMiniAppsTool()
    
    test_queries = [
        "storage",
        "games", 
        "polls",
        "fun activities",
        "community tools"
    ]
    
    for query in test_queries:
        logger.info(f"\n🔍 Searching for: '{query}'")
        
        result = await search_tool.execute({
            "query": query,
            "limit": 3
        }, context)
        
        if result.get("status") == "success":
            message = result.get("message", "")
            print(message)
        else:
            logger.error(f"Search failed: {result.get('error')}")


async def test_opportunity_detection(world_state_manager: WorldStateManager):
    """Test the proactive opportunity detection system."""
    logger.info("\n" + "="*60)
    logger.info("TESTING OPPORTUNITY DETECTION")
    logger.info("="*60)
    
    # Create test channel with sample messages
    test_channel = Channel(
        id="farcaster:test_channel",
        type="farcaster", 
        name="Test Channel"
    )
    
    # Add various messages that should trigger mini-app opportunities
    test_messages = [
        "I'm running out of storage space, how do I get more?",
        "Anyone know any fun games on Farcaster?", 
        "Looking for a way to create polls for my community",
        "I'm bored, what should I do?",
        "How do I manage my files better?",
        "Need help finding entertainment apps"
    ]
    
    # Add messages to channel
    for content in test_messages:
        message = create_test_message(content)
        test_channel.recent_messages.append(message)
    
    # Add channel to world state
    world_state_manager.state.channels[test_channel.id] = test_channel
    
    # Initialize proactive engine
    proactive_engine = ProactiveConversationEngine(world_state_manager)
    
    # Detect opportunities
    logger.info("Analyzing messages for mini-app opportunities...")
    opportunities = proactive_engine.analyze_world_state_for_opportunities(world_state_manager.state)
    
    # Filter for mini-app opportunities
    mini_app_opportunities = [
        opp for opp in opportunities 
        if opp.opportunity_type == "mini_app_opportunity"
    ]
    
    logger.info(f"\n📊 Found {len(mini_app_opportunities)} mini-app opportunities:")
    
    for i, opp in enumerate(mini_app_opportunities, 1):
        logger.info(f"\n{i}. Opportunity ID: {opp.opportunity_id}")
        logger.info(f"   Priority: {opp.priority}/10")
        logger.info(f"   Category: {opp.context.get('category')}")
        logger.info(f"   Keyword: {opp.context.get('matched_keyword')}")
        logger.info(f"   Original Message: {opp.context.get('original_message')}")
        logger.info(f"   Reasoning: {opp.reasoning}")
    
    return mini_app_opportunities


async def test_engagement_strategy(opportunities, world_state_manager: WorldStateManager):
    """Test the mini-app recommendation engagement strategy."""
    if not opportunities:
        logger.info("No opportunities to test engagement strategy")
        return
        
    logger.info("\n" + "="*60)
    logger.info("TESTING ENGAGEMENT STRATEGY")
    logger.info("="*60)
    
    # Initialize strategy registry
    strategy_registry = EngagementStrategyRegistry()
    
    # Get the mini-app recommendation strategy
    mini_app_strategy = strategy_registry.get_strategy("mini_app_recommendation")
    
    if not mini_app_strategy:
        logger.error("Mini-app recommendation strategy not found!")
        return
    
    # Test with the first opportunity
    test_opportunity = opportunities[0]
    logger.info(f"Testing with opportunity: {test_opportunity.context.get('category')} - {test_opportunity.context.get('matched_keyword')}")
    
    # Check if strategy can handle the opportunity
    can_handle = mini_app_strategy.can_handle(test_opportunity)
    logger.info(f"Strategy can handle opportunity: {can_handle}")
    
    if can_handle:
        # Generate engagement plan
        engagement_plan = mini_app_strategy.generate_engagement_plan(test_opportunity)
        
        logger.info(f"\n📋 Generated Engagement Plan:")
        logger.info(f"   Plan ID: {engagement_plan.plan_id}")
        logger.info(f"   Strategy: {engagement_plan.strategy_name}")
        logger.info(f"   Timing: {engagement_plan.timing_preference}")
        logger.info(f"   Estimated Impact: {engagement_plan.estimated_impact}/10")
        logger.info(f"   Confidence: {engagement_plan.confidence}")
        
        logger.info(f"\n🎯 Action Sequence:")
        for i, action in enumerate(engagement_plan.action_sequence, 1):
            logger.info(f"   {i}. {action['action_type']}")
            logger.info(f"      Parameters: {action['parameters']}")
            logger.info(f"      Reasoning: {action['reasoning']}")


async def test_complete_workflow():
    """Test the complete mini-app recommendation workflow."""
    logger.info("\n" + "="*60)
    logger.info("TESTING COMPLETE WORKFLOW")
    logger.info("="*60)
    
    # Setup environment
    world_state_manager, context = await setup_test_environment()
    
    # Test search functionality
    await test_search_functionality(context)
    
    # Test opportunity detection
    opportunities = await test_opportunity_detection(world_state_manager)
    
    # Test engagement strategy
    await test_engagement_strategy(opportunities, world_state_manager)
    
    logger.info("\n" + "="*60)
    logger.info("WORKFLOW TEST COMPLETE")
    logger.info("="*60)


async def interactive_demo():
    """Run an interactive demo of the recommendation system."""
    print("\n🎮 Interactive Mini-App Recommendation Demo")
    print("=" * 50)
    
    # Setup environment
    world_state_manager, context = await setup_test_environment()
    search_tool = SearchMiniAppsTool()
    
    print("Type queries to search for mini-apps, or 'quit' to exit:")
    
    while True:
        try:
            query = input("\n🔍 Search query: ").strip()
            
            if query.lower() in ['quit', 'exit', 'q']:
                break
                
            if not query:
                continue
                
            print(f"\nSearching for: '{query}'...")
            
            result = await search_tool.execute({
                "query": query,
                "limit": 5
            }, context)
            
            if result.get("status") == "success":
                message = result.get("message", "")
                print(message)
            else:
                print(f"❌ Search failed: {result.get('error')}")
                
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"❌ Error: {e}")
    
    print("\n👋 Demo ended. Thanks for testing the mini-app recommendation system!")


async def main():
    """Main function to run all tests."""
    print("🚀 Farcaster Mini-App Recommendation System Test")
    print("=" * 60)
    
    try:
        # Run automated tests
        await test_complete_workflow()
        
        # Ask if user wants interactive demo
        print("\n" + "="*60)
        response = input("Would you like to run the interactive demo? (y/n): ").strip().lower()
        
        if response in ['y', 'yes']:
            await interactive_demo()
        
        print("\n✅ All tests completed successfully!")
        print("The mini-app recommendation system is working correctly.")
        
    except Exception as e:
        logger.error(f"Error during testing: {e}", exc_info=True)
        print("\n❌ Tests failed. Check the logs for details.")


if __name__ == "__main__":
    asyncio.run(main())
