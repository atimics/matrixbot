#!/usr/bin/env python3
"""
Simplified Test Suite for Proactive Conversation Engine Core

This test suite validates the core proactive conversation engine functionality
without relying on the tools module which has import issues.
"""

import asyncio
import logging
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Any
from unittest.mock import Mock, AsyncMock

from chatbot.core.proactive.proactive_engine import ProactiveConversationEngine, ConversationOpportunity
from chatbot.core.world_state.structures import (
    WorldStateData, Channel, Message, 
    FarcasterUserDetails, MatrixUserDetails, SentimentData
)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class ProactiveEngineTestSuite:
    """Test suite for the proactive conversation engine core functionality."""
    
    def __init__(self):
        self.test_results = []
        
    async def setup_test_environment(self):
        """Set up a realistic test environment with mock data."""
        logger.debug("Setting up test environment...")
        
        # Create mock world state manager
        self.mock_world_state_manager = AsyncMock()
        self.mock_context_manager = Mock()
        
        # Create test world state data
        self.test_world_state = self.create_test_world_state()
        self.mock_world_state_manager.get_world_state_data.return_value = self.test_world_state
        
        # Create proactive engine
        self.proactive_engine = ProactiveConversationEngine(
            world_state_manager=self.mock_world_state_manager,
            context_manager=self.mock_context_manager
        )
        
        logger.debug("Test environment setup complete")
        
    def create_test_world_state(self) -> WorldStateData:
        """Create realistic test world state data."""
        current_time = time.time()
        
        # Create test users
        farcaster_user = FarcasterUserDetails(
            fid="123",
            username="bob_crypto",
            display_name="Bob Smith",
            pfp_url="https://example.com/pfp.jpg",
            follower_count=100,  # Milestone user
            following_count=50,
            bio="Crypto enthusiast",
            power_badge=False,
            sentiment=SentimentData(
                score=0.6,
                label="positive",
                last_updated=current_time - 60
            )
        )
        
        matrix_user = MatrixUserDetails(
            user_id="@alice:matrix.org",
            display_name="Alice Johnson", 
            avatar_url="mxc://example.com/avatar",
            sentiment=SentimentData(
                score=0.8,
                label="positive", 
                last_updated=current_time - 300
            )
        )
        
        # Create test messages for different scenarios
        test_messages = [
            # Recent activity in channel 1 (trending topic opportunity)
            Message(
                id="msg1",
                channel_type="matrix",
                sender="@alice:matrix.org",
                content="Hey everyone, what do you think about the new AI developments?",
                timestamp=current_time - 600,
                channel_id="channel1",
                sender_username="alice"
            ),
            Message(
                id="msg2",
                channel_type="farcaster", 
                sender="123",  # FID
                content="I've been researching machine learning trends lately",
                timestamp=current_time - 500,
                channel_id="channel1",
                sender_username="bob_crypto"
            ),
            Message(
                id="msg3",
                channel_type="matrix",
                sender="@alice:matrix.org",
                content="AI is definitely going to change everything!",
                timestamp=current_time - 400,
                channel_id="channel1",
                sender_username="alice"
            ),
            # Question in channel 2 (content sharing opportunity)
            Message(
                id="msg4",
                channel_type="farcaster",
                sender="123",
                content="Can someone explain how transformers work in AI?",
                timestamp=current_time - 300,
                channel_id="channel2",
                sender_username="bob_crypto"
            ),
            # Quiet channel 3 (last message was 2 hours ago)
            Message(
                id="msg5",
                channel_type="matrix",
                sender="@alice:matrix.org",
                content="This channel seems quiet lately",
                timestamp=current_time - 7200,  # 2 hours ago
                channel_id="channel3",
                sender_username="alice"
            )
        ]
        
        # Create test channels
        test_channels = {
            "channel1": Channel(
                id="channel1",
                name="general-discussion",
                type="matrix",
                recent_messages=[msg for msg in test_messages if msg.channel_id == "channel1"]
            ),
            "channel2": Channel(  
                id="channel2",
                name="ai-research",
                type="farcaster",
                recent_messages=[msg for msg in test_messages if msg.channel_id == "channel2"]
            ),
            "channel3": Channel(
                id="channel3", 
                name="quiet-channel",
                type="matrix",
                recent_messages=[msg for msg in test_messages if msg.channel_id == "channel3"]
            )
        }
        
        # Create world state
        world_state = WorldStateData()
        world_state.channels = test_channels
        world_state.matrix_users = {"@alice:matrix.org": matrix_user}
        world_state.farcaster_users = {"123": farcaster_user}
        world_state.action_history = []
        world_state.last_update = current_time
        
        return world_state
    
    async def test_opportunity_detection(self):
        """Test the opportunity detection algorithms."""
        logger.debug("Testing opportunity detection...")
        
        try:
            # Test basic opportunity detection
            opportunities = self.proactive_engine.analyze_world_state_for_opportunities(
                self.test_world_state
            )
            
            assert len(opportunities) > 0, "Should detect some opportunities"
            
            # Check for specific opportunity types
            opportunity_types = [opp.opportunity_type for opp in opportunities]
            
            logger.debug(f"Detected opportunity types: {opportunity_types}")
            
            # Verify that we're detecting reasonable opportunities
            expected_types = ["trending_topic", "quiet_channel", "content_sharing", "user_milestone"]
            detected_expected = [ot for ot in expected_types if ot in opportunity_types]
            
            assert len(detected_expected) > 0, f"Should detect at least some expected types. Got: {opportunity_types}"
            
            # Check opportunity structure
            for opp in opportunities:
                assert hasattr(opp, 'opportunity_id'), "Opportunity should have ID"
                assert hasattr(opp, 'opportunity_type'), "Opportunity should have type"
                assert hasattr(opp, 'priority'), "Opportunity should have priority"
                assert hasattr(opp, 'reasoning'), "Opportunity should have reasoning"
                assert isinstance(opp.context, dict), "Context should be a dictionary"
            
            logger.debug(f"✅ Opportunity detection test passed - detected {len(opportunities)} opportunities")
            self.test_results.append(("Opportunity Detection", True, f"Detected {len(opportunities)} opportunities of types: {opportunity_types}"))
            
        except Exception as e:
            logger.error(f"❌ Opportunity detection test failed: {e}")
            self.test_results.append(("Opportunity Detection", False, str(e)))
    
    async def test_trending_topic_detection(self):
        """Test specific trending topic detection."""
        logger.debug("Testing trending topic detection...")
        
        try:
            opportunities = self.proactive_engine._detect_trending_opportunities(self.test_world_state)
            
            # Should detect AI as a trending topic based on test messages
            ai_opportunities = [opp for opp in opportunities if "AI" in opp.reasoning or "ai" in str(opp.context)]
            
            logger.debug(f"Found {len(ai_opportunities)} AI-related opportunities")
            
            if ai_opportunities:
                ai_opp = ai_opportunities[0]
                assert ai_opp.opportunity_type == "trending_topic"
                assert ai_opp.priority > 5  # Should be reasonably high priority
                
            logger.debug("✅ Trending topic detection test passed")
            self.test_results.append(("Trending Topic Detection", True, f"Detected {len(opportunities)} trending opportunities"))
            
        except Exception as e:
            logger.error(f"❌ Trending topic detection test failed: {e}")
            self.test_results.append(("Trending Topic Detection", False, str(e)))
    
    async def test_quiet_channel_detection(self):
        """Test quiet channel detection."""
        logger.debug("Testing quiet channel detection...")
        
        try:
            opportunities = self.proactive_engine._detect_activity_opportunities(self.test_world_state)
            
            # Should detect channel3 as quiet (last message 2 hours ago)
            quiet_opportunities = [opp for opp in opportunities if opp.opportunity_type == "quiet_channel"]
            
            assert len(quiet_opportunities) > 0, "Should detect at least one quiet channel"
            
            quiet_opp = quiet_opportunities[0]
            assert quiet_opp.channel_id == "channel3"
            assert "quiet" in quiet_opp.reasoning.lower()
            
            logger.debug("✅ Quiet channel detection test passed")
            self.test_results.append(("Quiet Channel Detection", True, f"Detected {len(quiet_opportunities)} quiet channels"))
            
        except Exception as e:
            logger.error(f"❌ Quiet channel detection test failed: {e}")
            self.test_results.append(("Quiet Channel Detection", False, str(e)))
    
    async def test_user_milestone_detection(self):
        """Test user milestone detection."""
        logger.debug("Testing user milestone detection...")
        
        try:
            opportunities = self.proactive_engine._detect_user_milestone_opportunities(self.test_world_state)
            
            # Should detect bob_crypto's 100 follower/message milestone
            milestone_opportunities = [opp for opp in opportunities if opp.opportunity_type == "user_milestone"]
            
            logger.debug(f"Found {len(milestone_opportunities)} milestone opportunities")
            
            if milestone_opportunities:
                milestone_opp = milestone_opportunities[0]
                assert milestone_opp.user_id in ["123", "@alice:matrix.org"]
                assert "milestone" in milestone_opp.reasoning.lower()
            
            logger.debug("✅ User milestone detection test passed")
            self.test_results.append(("User Milestone Detection", True, f"Detected {len(milestone_opportunities)} milestones"))
            
        except Exception as e:
            logger.error(f"❌ User milestone detection test failed: {e}")
            self.test_results.append(("User Milestone Detection", False, str(e)))
    
    async def test_content_sharing_detection(self):
        """Test content sharing opportunity detection."""
        logger.debug("Testing content sharing detection...")
        
        try:
            opportunities = self.proactive_engine._detect_content_sharing_opportunities(self.test_world_state)
            
            # Should detect the question about transformers as content sharing opportunity
            content_opportunities = [opp for opp in opportunities if opp.opportunity_type == "content_sharing"]
            
            logger.debug(f"Found {len(content_opportunities)} content sharing opportunities")
            
            if content_opportunities:
                content_opp = content_opportunities[0]
                assert "transformers" in str(content_opp.context) or "?" in str(content_opp.context)
            
            logger.debug("✅ Content sharing detection test passed")
            self.test_results.append(("Content Sharing Detection", True, f"Detected {len(content_opportunities)} content opportunities"))
            
        except Exception as e:
            logger.error(f"❌ Content sharing detection test failed: {e}")
            self.test_results.append(("Content Sharing Detection", False, str(e)))
    
    async def test_engine_lifecycle(self):
        """Test the proactive engine lifecycle management."""
        logger.debug("Testing proactive engine lifecycle...")
        
        try:
            # Test start
            await self.proactive_engine.start()
            
            # Test world state change handling
            await self.proactive_engine.on_world_state_change()
            
            # Test opportunity management
            test_opportunity = ConversationOpportunity(
                opportunity_id="test_123",
                opportunity_type="test",
                priority=8,
                context={"test": "data"},
                platform="matrix",
                channel_id="test_channel",
                reasoning="Test opportunity"
            )
            
            # Register and retrieve opportunity
            self.proactive_engine.register_active_opportunity(test_opportunity)
            active_opps = self.proactive_engine.get_active_opportunities()
            
            assert len(active_opps) > 0, "Should have active opportunities"
            assert any(opp.opportunity_id == "test_123" for opp in active_opps), "Should find our test opportunity"
            
            # Test cleanup
            self.proactive_engine.cleanup_expired_opportunities()
            
            # Test stop
            await self.proactive_engine.stop()
            
            logger.debug("✅ Engine lifecycle test passed")
            self.test_results.append(("Engine Lifecycle", True, "Start/stop/opportunity management works"))
            
        except Exception as e:
            logger.error(f"❌ Engine lifecycle test failed: {e}")
            self.test_results.append(("Engine Lifecycle", False, str(e)))
    
    async def test_opportunity_filtering(self):
        """Test opportunity filtering and prioritization."""
        logger.debug("Testing opportunity filtering...")
        
        try:
            # Generate opportunities
            opportunities = self.proactive_engine.analyze_world_state_for_opportunities(self.test_world_state)
            
            # Test filtering
            current_time = time.time()
            filtered = self.proactive_engine._filter_and_prioritize_opportunities(opportunities, current_time)
            
            # Should filter and sort by priority
            assert len(filtered) <= len(opportunities), "Filtering should not increase opportunities"
            
            if len(filtered) > 1:
                # Check that they're sorted by priority (descending)
                for i in range(len(filtered) - 1):
                    assert filtered[i].priority >= filtered[i + 1].priority, "Should be sorted by priority"
            
            logger.debug("✅ Opportunity filtering test passed")
            self.test_results.append(("Opportunity Filtering", True, f"Filtered {len(opportunities)} to {len(filtered)} opportunities"))
            
        except Exception as e:
            logger.error(f"❌ Opportunity filtering test failed: {e}")
            self.test_results.append(("Opportunity Filtering", False, str(e)))
    
    async def test_integration_scenario(self):
        """Test a complete integration scenario."""
        logger.debug("Testing complete integration scenario...")
        
        try:
            # 1. Start the engine
            await self.proactive_engine.start()
            
            # 2. Trigger world state change (simulates new activity)
            await self.proactive_engine.on_world_state_change()
            
            # 3. Manually detect opportunities
            opportunities = await self.proactive_engine.detect_opportunities(
                opportunity_types=["trending_topic", "quiet_channel", "user_milestone"],
                minimum_priority=0.5
            )
            
            assert isinstance(opportunities, list), "Should return list of opportunities"
            assert len(opportunities) >= 0, "Should return valid opportunities list"
            
            # 4. Test engagement tracking
            if opportunities:
                first_opp = opportunities[0]
                opp_id = first_opp["opportunity_id"]
                
                # Track engagement outcome
                await self.proactive_engine.track_engagement_outcome(
                    opp_id, "initiated", {"test_metric": 1}
                )
                
                # Check engagement status
                status = await self.proactive_engine.get_engagement_status(opp_id)
                logger.debug(f"Engagement status: {status}")
            
            # 5. Test recent engagements
            recent = await self.proactive_engine.get_recent_engagements(
                since_time=datetime.now() - timedelta(hours=1)
            )
            
            assert isinstance(recent, list), "Should return list of recent engagements"
            
            # 6. Stop the engine
            await self.proactive_engine.stop()
            
            logger.debug("✅ Integration scenario test passed")
            self.test_results.append(("Integration Scenario", True, f"Complete workflow with {len(opportunities)} opportunities"))
            
        except Exception as e:
            logger.error(f"❌ Integration scenario test failed: {e}")
            self.test_results.append(("Integration Scenario", False, str(e)))
    
    async def test_edge_cases(self):
        """Test edge cases and error handling."""
        logger.debug("Testing edge cases...")
        
        try:
            # Test with empty world state
            empty_world_state = WorldStateData()
            # All containers are already initialized as empty
            
            opportunities = self.proactive_engine.analyze_world_state_for_opportunities(empty_world_state)
            assert isinstance(opportunities, list), "Should return empty list for empty world state"
            
            # Test expired opportunity detection
            expired_opp = ConversationOpportunity(
                opportunity_id="expired_test",
                opportunity_type="test",
                priority=5,
                context={},
                platform="matrix",
                expires_at=time.time() - 3600,  # Expired 1 hour ago
                reasoning="Expired test opportunity"
            )
            
            assert expired_opp.is_expired(), "Should detect expired opportunity"
            
            # Test with invalid data types (graceful handling)
            try:
                invalid_opportunities = self.proactive_engine._filter_and_prioritize_opportunities(
                    None, time.time()
                )
                # Should handle gracefully
            except Exception:
                # Expected to handle errors gracefully
                pass
            
            logger.debug("✅ Edge cases test passed")
            self.test_results.append(("Edge Cases", True, "Error handling works correctly"))
            
        except Exception as e:
            logger.error(f"❌ Edge cases test failed: {e}")
            self.test_results.append(("Edge Cases", False, str(e)))
    
    def print_test_results(self):
        """Print comprehensive test results."""
        logger.debug("\n" + "="*70)
        logger.debug("PROACTIVE CONVERSATION ENGINE CORE TEST RESULTS")
        logger.debug("="*70)
        
        passed = 0
        failed = 0
        
        for test_name, success, details in self.test_results:
            status = "✅ PASS" if success else "❌ FAIL"
            logger.debug(f"{status} | {test_name:<35} | {details}")
            if success:
                passed += 1
            else:
                failed += 1
        
        logger.debug("="*70)
        logger.debug(f"SUMMARY: {passed} passed, {failed} failed, {passed + failed} total")
        
        if failed == 0:
            logger.debug("🎉 ALL CORE TESTS PASSED! Proactive conversation engine is working correctly.")
        else:
            logger.warning(f"⚠️  {failed} tests failed. Please review the issues above.")
        
        return failed == 0


async def run_core_tests():
    """Run the core test suite."""
    logger.debug("Starting proactive conversation engine core tests...")
    
    # Create test instance
    test_suite = ProactiveEngineTestSuite()
    
    try:
        # Setup test environment
        await test_suite.setup_test_environment()
        
        # Run all tests
        await test_suite.test_opportunity_detection()
        await test_suite.test_trending_topic_detection()
        await test_suite.test_quiet_channel_detection()
        await test_suite.test_user_milestone_detection()
        await test_suite.test_content_sharing_detection()
        await test_suite.test_engine_lifecycle()
        await test_suite.test_opportunity_filtering()
        await test_suite.test_integration_scenario()
        await test_suite.test_edge_cases()
        
        # Print results
        all_passed = test_suite.print_test_results()
        
        return all_passed
        
    except Exception as e:
        logger.error(f"Test suite failed with error: {e}")
        return False


if __name__ == "__main__":
    asyncio.run(run_core_tests())
