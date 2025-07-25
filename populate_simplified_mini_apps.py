#!/usr/bin/env python3
"""
Simplified Mini-App Database Population Script

This script populates the mini-app database with a curated list of 
Farcaster mini-apps using AI-generated summaries. Each entry is a 
"digital index card" with name, URL, and AI-crafted summary.
"""

import asyncio
import logging
import os
import sys

# Add the project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from chatbot.core.world_state.manager import WorldStateManager
from chatbot.tools.mini_app_tools import UpdateMiniAppSummaryTool
from chatbot.tools.base import ActionContext

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# Curated list with AI-generated summaries
MINI_APPS_WITH_AI_SUMMARIES = [
    {
        "name": "Farcaster Storage",
        "url": "https://storage.farcaster.xyz",
        "ai_summary": "Official tool for managing your Farcaster storage allocation. Perfect if you're running out of space for casts, need to purchase additional storage units, or want to monitor your account usage. Essential for active Farcaster users who cast frequently or share media content."
    },
    {
        "name": "Warpcast",
        "url": "https://warpcast.com",
        "ai_summary": "The flagship Farcaster client with the most polished experience. Great for newcomers to Farcaster or anyone wanting a clean, feature-rich interface for browsing feeds, posting casts, and managing social connections. Think of it as the 'Twitter app' of Farcaster."
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
        "name": "Supercast",
        "url": "https://supercast.xyz",
        "ai_summary": "Premium Farcaster client designed for power users and content creators. Offers advanced analytics, scheduling tools, and enhanced features that aren't available in basic clients. Great for influencers, businesses, or serious Farcaster users who want detailed insights into their engagement."
    },
    {
        "name": "Base Hunt",
        "url": "https://basehunt.xyz",
        "ai_summary": "Discovery platform for the Base blockchain ecosystem. Perfect for crypto enthusiasts who want to explore new DeFi protocols, discover emerging projects, or stay on top of Base ecosystem developments. Think Product Hunt but specifically for Base blockchain apps."
    },
    {
        "name": "Frames.js",
        "url": "https://framesjs.org",
        "ai_summary": "Developer toolkit for building interactive Farcaster Frames using React. Essential for developers who want to create engaging, interactive content for Farcaster. Provides components, templates, and deployment tools to build everything from simple polls to complex mini-games."
    },
    {
        "name": "Purple",
        "url": "https://purple.construction",
        "ai_summary": "Community governance platform for Farcaster ecosystem discussions and proposals. Great for community leaders, protocol contributors, or anyone who wants to participate in shaping the future of Farcaster. Vote on proposals, discuss improvements, and engage with core contributors."
    },
    {
        "name": "Flink",
        "url": "https://flink.fyi",
        "ai_summary": "Link-in-bio tool optimized for Web3 creators. Perfect for influencers, content creators, or businesses who want a beautiful landing page that supports crypto payments and integrates with their Farcaster profile. Think Linktree but with built-in Web3 functionality."
    },
    {
        "name": "Yoink",
        "url": "https://yoink.party",
        "ai_summary": "Playful social game where you can 'steal' virtual items from other users in a fun, non-destructive way. Great for adding some lighthearted entertainment to your Farcaster experience. Perfect for communities that enjoy casual gaming and social interaction."
    },
    {
        "name": "Recaster",
        "url": "https://recaster.org",
        "ai_summary": "Analytics platform for tracking your Farcaster performance and growth. Ideal for content creators, marketers, or anyone curious about their Farcaster metrics. See which casts perform best, track follower growth, and understand your audience engagement patterns."
    },
    {
        "name": "Airstack",
        "url": "https://airstack.xyz",
        "ai_summary": "Comprehensive Web3 social data platform that includes Farcaster analytics and insights. Perfect for developers building Farcaster apps, researchers studying social networks, or anyone who wants deep data about Farcaster user behavior and social graphs."
    },
    {
        "name": "Bountycaster",
        "url": "https://bountycaster.xyz",
        "ai_summary": "Bounty platform for posting and completing tasks within the Farcaster community. Great for freelancers looking for gigs, project owners who need specific tasks completed, or anyone wanting to monetize their skills within the Farcaster ecosystem."
    },
    {
        "name": "Perl",
        "url": "https://perl.xyz",
        "ai_summary": "Social prediction markets where you can bet on future events with friends and community members. Perfect for people who enjoy forecasting, want to put their predictions to the test with real stakes, or like engaging in friendly competition around current events."
    },
    {
        "name": "Eventcaster",
        "url": "https://eventcaster.xyz",
        "ai_summary": "Event discovery and promotion platform built specifically for the Farcaster community. Ideal for event organizers wanting to promote meetups, conferences, or virtual gatherings, and for community members looking to discover interesting events to attend."
    }
]


async def populate_simplified_database():
    """Populate the database with AI-curated mini-app summaries."""
    logger.info("Starting simplified mini-app database population...")
    
    try:
        # Initialize world state manager
        world_state_manager = WorldStateManager()
        
        # Create action context
        context = ActionContext(world_state_manager=world_state_manager)
        
        # Create the update tool
        update_tool = UpdateMiniAppSummaryTool()
        
        # Add each mini-app to the database
        success_count = 0
        for app_data in MINI_APPS_WITH_AI_SUMMARIES:
            try:
                logger.info(f"Adding mini-app: {app_data['name']}")
                
                result = await update_tool.execute(app_data, context)
                
                if result.get("status") == "success":
                    success_count += 1
                    logger.info(f"✅ Successfully added: {app_data['name']}")
                else:
                    logger.error(f"❌ Failed to add {app_data['name']}: {result.get('error', 'Unknown error')}")
                    
            except Exception as e:
                logger.error(f"❌ Exception adding {app_data['name']}: {e}")
        
        logger.info(f"Database population complete! Added {success_count}/{len(MINI_APPS_WITH_AI_SUMMARIES)} mini-apps")
        
        # Display summary
        total_apps = len(world_state_manager.state.mini_app_database)
        logger.info(f"Total mini-apps in database: {total_apps}")
        
        # Show sample of what's in the database
        logger.info("\nSample mini-apps:")
        for i, (key, app) in enumerate(list(world_state_manager.state.mini_app_database.items())[:3]):
            logger.info(f"  {i+1}. {app.name}")
            logger.info(f"     URL: {app.url}")
            logger.info(f"     Summary: {app.ai_summary[:100]}...")
            
        return success_count
        
    except Exception as e:
        logger.error(f"Error during database population: {e}", exc_info=True)
        return 0


async def test_simplified_search():
    """Test the simplified search functionality."""
    logger.info("\nTesting simplified search functionality...")
    
    try:
        # Initialize world state manager
        world_state_manager = WorldStateManager()
        context = ActionContext(world_state_manager=world_state_manager)
        
        # Import search tool
        from chatbot.tools.mini_app_tools import SearchMiniAppsTool
        search_tool = SearchMiniAppsTool()
        
        # Test natural language queries
        test_queries = [
            "storage space running out",
            "fun games entertainment",
            "analytics track performance",
            "create content writing",
            "developer tools building"
        ]
        
        for query in test_queries:
            logger.info(f"\nTesting search for: '{query}'")
            
            result = await search_tool.execute({
                "query": query,
                "limit": 2
            }, context)
            
            if result.get("status") == "success":
                results = result.get("results", [])
                logger.info(f"Found {len(results)} results")
                
                for i, app in enumerate(results, 1):
                    logger.info(f"  {i}. {app['name']}")
                    logger.info(f"     Summary: {app['ai_summary'][:80]}...")
            else:
                logger.error(f"Search failed: {result.get('error', 'Unknown error')}")
                
    except Exception as e:
        logger.error(f"Error during search testing: {e}", exc_info=True)


async def interactive_search_demo():
    """Run an interactive demo with natural language queries."""
    print("\n🔍 Interactive Natural Language Search Demo")
    print("=" * 50)
    print("Try natural language queries like:")
    print("- 'I need more storage space'")
    print("- 'fun games to play'")
    print("- 'tools for content creators'")
    print("- 'analytics and tracking'")
    print()
    
    try:
        # Setup environment
        world_state_manager = WorldStateManager()
        context = ActionContext(world_state_manager=world_state_manager)
        
        from chatbot.tools.mini_app_tools import SearchMiniAppsTool
        search_tool = SearchMiniAppsTool()
        
        print("Type natural language queries, or 'quit' to exit:")
        
        while True:
            try:
                query = input("\n💬 What do you need? ").strip()
                
                if query.lower() in ['quit', 'exit', 'q']:
                    break
                    
                if not query:
                    continue
                    
                print(f"\nSearching for apps that help with: '{query}'...")
                
                result = await search_tool.execute({
                    "query": query,
                    "limit": 3
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
        
        print("\n👋 Thanks for testing the simplified recommendation system!")
        
    except Exception as e:
        logger.error(f"Error during interactive demo: {e}", exc_info=True)


async def main():
    """Main function to populate database and test functionality."""
    print("🚀 Simplified Farcaster Mini-App Recommendation System")
    print("=" * 60)
    print("Each app is a 'digital index card' with name, URL, and AI summary")
    print()
    
    # Populate the database
    success_count = await populate_simplified_database()
    
    if success_count > 0:
        # Test search functionality
        await test_simplified_search()
        
        print("\n" + "=" * 60)
        response = input("Would you like to try the interactive search demo? (y/n): ").strip().lower()
        
        if response in ['y', 'yes']:
            await interactive_search_demo()
        
        print("\n✅ Setup complete! The simplified mini-app recommendation system is ready.")
        print(f"📱 {success_count} mini-apps with AI summaries available")
        print("\nThe system uses intelligent text matching on rich AI summaries!")
    else:
        print("\n❌ Setup failed. Please check the logs for errors.")


if __name__ == "__main__":
    asyncio.run(main())
