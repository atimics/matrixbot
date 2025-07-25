#!/usr/bin/env python3
"""
Initial Mini-App Database Population Script

This script populates the mini-app database with a curated list of 
high-quality Farcaster mini-apps for the recommendation system.
"""

import asyncio
import logging
import os
import sys

# Add the project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from chatbot.core.world_state.manager import WorldStateManager
from chatbot.tools.mini_app_tools import UpdateMiniAppDBTool
from chatbot.tools.base import ActionContext

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# Curated list of initial mini-apps
INITIAL_MINI_APPS = [
    {
        "name": "Farcaster Storage",
        "url": "https://storage.farcaster.xyz",
        "description": "Manage your Farcaster storage allocation, purchase additional storage units, and monitor usage across your account.",
        "developer": "Farcaster Team",
        "category": "tools",
        "tags": ["storage", "files", "management", "account"],
        "popularity_score": 0.9,
        "metadata": {"official": True, "type": "utility"}
    },
    {
        "name": "Warpcast",
        "url": "https://warpcast.com",
        "description": "The leading Farcaster client with rich features for browsing, posting, and managing your Farcaster experience.",
        "developer": "Merkle Manufactory",
        "category": "social",
        "tags": ["client", "posting", "social", "feed"],
        "popularity_score": 1.0,
        "metadata": {"official": True, "type": "client"}
    },
    {
        "name": "Paragraph",
        "url": "https://paragraph.xyz",
        "description": "Web3-native newsletter and blogging platform with integrated Farcaster publishing and crypto monetization.",
        "developer": "Paragraph",
        "category": "tools",
        "tags": ["writing", "newsletter", "publishing", "content", "monetization"],
        "popularity_score": 0.8,
        "metadata": {"type": "publishing"}
    },
    {
        "name": "Farcaster Polls",
        "url": "https://polls.farcaster.xyz",
        "description": "Create interactive polls and surveys that can be embedded in Farcaster casts for community engagement.",
        "developer": "Community",
        "category": "social",
        "tags": ["polls", "voting", "community", "engagement", "surveys"],
        "popularity_score": 0.7,
        "metadata": {"type": "engagement"}
    },
    {
        "name": "Zora",
        "url": "https://zora.co",
        "description": "Create, collect, and trade NFTs with seamless Farcaster integration for sharing and discovery.",
        "developer": "Zora",
        "category": "defi",
        "tags": ["nft", "art", "collecting", "trading", "marketplace"],
        "popularity_score": 0.8,
        "metadata": {"type": "marketplace"}
    },
    {
        "name": "Base Hunt",
        "url": "https://basehunt.xyz",
        "description": "Discover and explore the latest projects, apps, and opportunities on the Base blockchain ecosystem.",
        "developer": "Base Hunt",
        "category": "tools",
        "tags": ["discovery", "base", "blockchain", "projects", "exploration"],
        "popularity_score": 0.6,
        "metadata": {"type": "discovery"}
    },
    {
        "name": "Frames.js",
        "url": "https://framesjs.org",
        "description": "Developer toolkit for building interactive Farcaster Frames with React components and easy deployment.",
        "developer": "Frames.js Team",
        "category": "tools",
        "tags": ["development", "frames", "react", "toolkit", "interactive"],
        "popularity_score": 0.7,
        "metadata": {"type": "developer"}
    },
    {
        "name": "Supercast",
        "url": "https://supercast.xyz",
        "description": "Premium Farcaster client with advanced features, analytics, and power user tools for content creators.",
        "developer": "Supercast",
        "category": "social",
        "tags": ["client", "premium", "analytics", "creator", "advanced"],
        "popularity_score": 0.8,
        "metadata": {"type": "client"}
    },
    {
        "name": "Farcaster Wrapped",
        "url": "https://wrapped.farcaster.xyz",
        "description": "Generate beautiful year-in-review summaries of your Farcaster activity with shareable graphics.",
        "developer": "Community",
        "category": "social",
        "tags": ["analytics", "wrapped", "summary", "social", "sharing"],
        "popularity_score": 0.6,
        "metadata": {"type": "analytics"}
    },
    {
        "name": "Purple",
        "url": "https://purple.construction",
        "description": "Community-driven governance and discussion platform for Farcaster ecosystem improvements and proposals.",
        "developer": "Purple DAO",
        "category": "social",
        "tags": ["governance", "community", "discussion", "dao", "voting"],
        "popularity_score": 0.7,
        "metadata": {"type": "governance"}
    },
    {
        "name": "Flink",
        "url": "https://flink.fyi",
        "description": "Create beautiful link-in-bio pages with Farcaster integration and crypto payment support.",
        "developer": "Flink",
        "category": "tools",
        "tags": ["links", "bio", "profile", "monetization", "crypto"],
        "popularity_score": 0.6,
        "metadata": {"type": "profile"}
    },
    {
        "name": "Yoink",
        "url": "https://yoink.party",
        "description": "Fun social game where you can 'yoink' items from other users in a playful virtual economy.",
        "developer": "Yoink Team",
        "category": "games",
        "tags": ["game", "social", "economy", "fun", "interactive"],
        "popularity_score": 0.7,
        "metadata": {"type": "game"}
    },
    {
        "name": "Farcaster Directory",
        "url": "https://fdir.xyz",
        "description": "Comprehensive directory of users, channels, and projects in the Farcaster ecosystem for discovery.",
        "developer": "Community",
        "category": "tools",
        "tags": ["directory", "discovery", "users", "channels", "search"],
        "popularity_score": 0.6,
        "metadata": {"type": "directory"}
    },
    {
        "name": "Perl",
        "url": "https://perl.xyz",
        "description": "Social prediction markets where you can bet on outcomes and test your forecasting skills with friends.",
        "developer": "Perl",
        "category": "games",
        "tags": ["prediction", "betting", "social", "forecasting", "markets"],
        "popularity_score": 0.6,
        "metadata": {"type": "prediction"}
    },
    {
        "name": "Recaster",
        "url": "https://recaster.org",
        "description": "Analytics and tools for tracking cast performance, audience growth, and engagement metrics.",
        "developer": "Recaster",
        "category": "tools",
        "tags": ["analytics", "metrics", "performance", "growth", "tracking"],
        "popularity_score": 0.7,
        "metadata": {"type": "analytics"}
    }
]


async def populate_mini_app_database():
    """Populate the mini-app database with initial entries."""
    logger.info("Starting mini-app database population...")
    
    try:
        # Initialize world state manager
        world_state_manager = WorldStateManager()
        
        # Create action context
        context = ActionContext(world_state_manager=world_state_manager)
        
        # Create the update tool
        update_tool = UpdateMiniAppDBTool()
        
        # Add each mini-app to the database
        success_count = 0
        for app_data in INITIAL_MINI_APPS:
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
        
        logger.info(f"Database population complete! Added {success_count}/{len(INITIAL_MINI_APPS)} mini-apps")
        
        # Display summary
        total_apps = len(world_state_manager.state.mini_app_database)
        logger.info(f"Total mini-apps in database: {total_apps}")
        
        # Show apps by category
        categories = {}
        for app in world_state_manager.state.mini_app_database.values():
            category = app.category
            categories[category] = categories.get(category, 0) + 1
        
        logger.info("Apps by category:")
        for category, count in categories.items():
            logger.info(f"  {category}: {count} apps")
            
        return success_count
        
    except Exception as e:
        logger.error(f"Error during database population: {e}", exc_info=True)
        return 0


async def test_search_functionality():
    """Test the search functionality with sample queries."""
    logger.info("\nTesting search functionality...")
    
    try:
        # Initialize world state manager
        world_state_manager = WorldStateManager()
        context = ActionContext(world_state_manager=world_state_manager)
        
        # Import search tool
        from chatbot.tools.mini_app_tools import SearchMiniAppsTool
        search_tool = SearchMiniAppsTool()
        
        # Test queries
        test_queries = [
            {"query": "storage", "expected_category": "tools"},
            {"query": "games", "expected_category": "games"},
            {"query": "polls", "expected_category": "social"},
            {"query": "nft", "expected_category": "defi"},
            {"query": "analytics", "expected_category": "tools"}
        ]
        
        for test in test_queries:
            logger.info(f"\nTesting search for: '{test['query']}'")
            
            result = await search_tool.execute({
                "query": test["query"],
                "limit": 3
            }, context)
            
            if result.get("status") == "success":
                results = result.get("results", [])
                logger.info(f"Found {len(results)} results")
                
                for i, app in enumerate(results, 1):
                    logger.info(f"  {i}. {app['name']} ({app['category']})")
            else:
                logger.error(f"Search failed: {result.get('error', 'Unknown error')}")
                
    except Exception as e:
        logger.error(f"Error during search testing: {e}", exc_info=True)


async def main():
    """Main function to populate the database and test functionality."""
    print("🚀 Farcaster Mini-App Database Setup")
    print("=" * 50)
    
    # Populate the database
    success_count = await populate_mini_app_database()
    
    if success_count > 0:
        # Test search functionality
        await test_search_functionality()
        
        print("\n" + "=" * 50)
        print("✅ Setup complete! The mini-app recommendation system is ready.")
        print(f"📱 {success_count} mini-apps available for recommendations")
        print("\nThe system will now proactively recommend relevant apps when users express needs!")
    else:
        print("\n❌ Setup failed. Please check the logs for errors.")


if __name__ == "__main__":
    asyncio.run(main())
