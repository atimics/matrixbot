#!/usr/bin/env python3
"""
Test script for the follower interaction system.
Validates follower profile management and interaction summaries.
"""

import asyncio
import logging
import os
import sys

# Add the project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from chatbot.core.world_state.manager import WorldStateManager
from chatbot.tools.follower_interaction_tools import (
    UpdateFollowerProfileTool,
    SearchFollowerProfilesTool,
    GenerateFollowerSummaryTool
)
from chatbot.tools.base import ActionContext

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def test_follower_profile_creation():
    """Test creating and updating follower profiles."""
    logger.info("Testing follower profile creation...")
    
    world_state_manager = WorldStateManager()
    context = ActionContext(world_state_manager=world_state_manager)
    
    # Create the tool
    update_tool = UpdateFollowerProfileTool()
    
    # Test profiles
    test_followers = [
        {
            "username": "cryptoenthusiast",
            "fid": "12345",
            "display_name": "Crypto Enthusiast",
            "bio": "DeFi researcher, building on Base, love exploring new protocols",
            "ai_summary": "Active DeFi researcher with strong technical background. Frequently asks thoughtful questions about protocol mechanics and enjoys discussing yield farming strategies. Values detailed, technical responses.",
            "interests": ["defi", "base", "yield-farming", "protocols"],
            "interaction_style": "technical"
        },
        {
            "username": "artcollector",
            "fid": "67890",
            "display_name": "NFT Artist",
            "bio": "Digital artist and NFT collector on Zora",
            "ai_summary": "Creative individual focused on the intersection of art and blockchain. Appreciates aesthetic and cultural aspects of Web3. Prefers friendly, supportive interactions.",
            "interests": ["nft", "art", "zora", "creativity"],
            "interaction_style": "supportive"
        },
        {
            "username": "newcomer",
            "fid": "11111",
            "display_name": "Farcaster Newbie",
            "bio": "New to Farcaster, learning about Web3",
            "ai_summary": "Recent arrival to the Farcaster ecosystem with genuine curiosity about Web3 technologies. Asks basic questions and appreciates beginner-friendly explanations.",
            "interests": ["learning", "web3", "beginner"],
            "interaction_style": "inquisitive"
        }
    ]
    
    # Add each follower
    success_count = 0
    for follower_data in test_followers:
        try:
            result = await update_tool.execute(follower_data, context)
            
            if result.get("status") == "success":
                success_count += 1
                logger.info(f"✅ Successfully added: {follower_data['username']}")
            else:
                logger.error(f"❌ Failed to add {follower_data['username']}: {result.get('error')}")
                
        except Exception as e:
            logger.error(f"❌ Exception adding {follower_data['username']}: {e}")
    
    logger.info(f"Added {success_count}/{len(test_followers)} follower profiles")
    return world_state_manager


async def test_follower_search(world_state_manager):
    """Test searching follower profiles."""
    logger.info("\nTesting follower profile search...")
    
    context = ActionContext(world_state_manager=world_state_manager)
    search_tool = SearchFollowerProfilesTool()
    
    test_queries = [
        "DeFi and protocols",
        "art and creativity", 
        "beginner questions",
        "technical discussions",
        "supportive community"
    ]
    
    for query in test_queries:
        logger.info(f"\nSearching for: '{query}'")
        
        try:
            result = await search_tool.execute({
                "query": query,
                "limit": 2
            }, context)
            
            if result.get("status") == "success":
                results = result.get("results", [])
                logger.info(f"Found {len(results)} matching followers")
                
                for i, follower in enumerate(results, 1):
                    logger.info(f"  {i}. @{follower['username']} ({follower.get('interaction_style', 'casual')})")
                    logger.info(f"     Summary: {follower.get('ai_summary', 'No summary')[:80]}...")
                    logger.info(f"     Interests: {', '.join(follower.get('interests', []))}")
            else:
                logger.error(f"Search failed: {result.get('error')}")
                
        except Exception as e:
            logger.error(f"Search error: {e}")


async def test_summary_generation():
    """Test AI summary generation for new followers."""
    logger.info("\nTesting AI summary generation...")
    
    world_state_manager = WorldStateManager()
    context = ActionContext(world_state_manager=world_state_manager)
    
    summary_tool = GenerateFollowerSummaryTool()
    
    test_case = {
        "username": "devbuilder",
        "bio": "Full-stack developer building on Farcaster. Love React and TypeScript.",
        "recent_casts": [
            "Just deployed my first Frame on Farcaster! The developer experience is amazing.",
            "Working on a new project using frames.js - anyone have tips for optimization?",
            "gm builders! What's everyone working on today?"
        ],
        "interaction_context": "Asked technical questions about Frames development, very engaged with developer tools"
    }
    
    try:
        result = await summary_tool.execute(test_case, context)
        
        if result.get("status") == "success":
            logger.info("✅ Generated AI summary:")
            logger.info(f"Summary: {result.get('ai_summary')}")
            logger.info(f"Interests: {result.get('interests')}")
            logger.info(f"Style: {result.get('interaction_style')}")
        else:
            logger.error(f"❌ Summary generation failed: {result.get('error')}")
            
    except Exception as e:
        logger.error(f"❌ Summary generation error: {e}")


async def interactive_follower_demo(world_state_manager):
    """Interactive demo for follower profile management."""
    print("\n👥 Interactive Follower Profile Demo")
    print("=" * 50)
    print("This system helps manage follower relationships with AI summaries")
    print()
    
    context = ActionContext(world_state_manager=world_state_manager)
    search_tool = SearchFollowerProfilesTool()
    
    print("Try searching for follower types:")
    print("- 'technical developers'")
    print("- 'art and creativity'") 
    print("- 'beginner friendly'")
    print("- 'DeFi experts'")
    print()
    
    while True:
        try:
            query = input("\n🔍 Search for followers: ").strip()
            
            if query.lower() in ['quit', 'exit', 'q']:
                break
                
            if not query:
                continue
                
            print(f"\nSearching for followers interested in: '{query}'...")
            
            result = await search_tool.execute({
                "query": query,
                "limit": 3
            }, context)
            
            if result.get("status") == "success":
                results = result.get("results", [])
                
                if results:
                    print(f"\n📋 Found {len(results)} matching followers:")
                    for i, follower in enumerate(results, 1):
                        print(f"\n{i}. @{follower['username']} ({follower.get('interaction_count', 0)} interactions)")
                        print(f"   Style: {follower.get('interaction_style', 'casual')}")
                        print(f"   Summary: {follower.get('ai_summary', 'No summary')}")
                        print(f"   Interests: {', '.join(follower.get('interests', []))}")
                else:
                    print("No matching followers found.")
            else:
                print(f"❌ Search failed: {result.get('error')}")
                
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"❌ Error: {e}")
    
    print("\n👋 Thanks for testing the follower interaction system!")


async def main():
    """Main function to test the follower interaction system."""
    print("🤖 Follower Interaction Management System Test")
    print("=" * 60)
    print("Testing AI-powered follower profile management and relationship building")
    print()
    
    # Test profile creation
    world_state_manager = await test_follower_profile_creation()
    
    if world_state_manager:
        # Test search functionality
        await test_follower_search(world_state_manager)
        
        # Test summary generation
        await test_summary_generation()
        
        # Show current profile count
        profile_count = len(world_state_manager.state.follower_profiles)
        print(f"\n📊 Total follower profiles in database: {profile_count}")
        
        # Interactive demo
        print("\n" + "=" * 60)
        response = input("Would you like to try the interactive follower search demo? (y/n): ").strip().lower()
        
        if response in ['y', 'yes']:
            await interactive_follower_demo(world_state_manager)
        
        print("\n✅ Follower interaction system is ready!")
        print("🎯 This system helps build meaningful relationships with followers")
        print("💡 AI summaries enable personalized, relevant interactions")
    else:
        print("\n❌ Test failed. Please check the logs for errors.")


if __name__ == "__main__":
    asyncio.run(main())
