#!/usr/bin/env python3
"""
Comprehensive Test Suite for Proactive Conversation System

This test suite validates the proactive conversation system implementation,
including opportunity detection, engagement planning, and tool functionality.
"""

import asyncio
import json
import logging
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Any
from unittest.mock import Mock, AsyncMock, MagicMock

from chatbot.core.proactive.proactive_engine import ProactiveConversationEngine, ConversationOpportunity
from chatbot.core.world_state.structures import WorldStateData, Channel, Message, FarcasterUserDetails, MatrixUserDetails, SentimentData
from chatbot.tools.proactive_conversation_tools import (
    InitiateProactiveConversationTool,
    DetectConversationOpportunitiesTool, 
    ScheduleProactiveEngagementTool,
    GetProactiveEngagementStatusTool
)
from chatbot.tools.base import ActionContext

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class TestProactiveSystem:
    """Comprehensive test suite for the proactive conversation system."""
    
    def __init__(self):
        self.test_results = []
        
    async def setup_test_environment(self):
        """Set up a realistic test environment with mock data."""
        logger.info("Setting up test environment...")
        
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
        
        # Add the proactive engine to the world state manager (for tool access)
        self.mock_world_state_manager.proactive_engine = self.proactive_engine
        
        # Create test action context
        self.test_context = ActionContext(
            world_state_manager=self.mock_world_state_manager,
            context_manager=self.mock_context_manager,
            ai_client=Mock(),
            action_record_id="test_action_123"
        )
        
        logger.info("Test environment setup complete")
        
    def create_test_world_state(self) -> WorldStateData:
        """Create realistic test world state data."""
        current_time = time.time()
        
        world_state = WorldStateData()
        
        # Add some test Farcaster users with sentiment data
        world_state.farcaster_users["123"] = FarcasterUserDetails(
            fid="123",
            username="alice", 
            display_name="Alice Johnson",
            follower_count=250,
            sentiment=SentimentData(
                label="positive",
                score=0.8,
                last_analyzed=current_time - 300
            )
        )
        
        world_state.farcaster_users["456"] = FarcasterUserDetails(
            fid="456",
            username="bob",
            display_name="Bob Smith", 
            follower_count=1000,  # Milestone user
            sentiment=SentimentData(
                label="neutral",
                score=0.6,
                last_analyzed=current_time - 60
            )
        )
        
        # Create test messages for different scenarios
        test_messages = [
            # Recent activity in channel 1
            Message(
                id="msg1",
                content="Hey everyone, what do you think about the new AI developments?",
                sender="alice",
                sender_username="alice",
                sender_fid=123,
                timestamp=current_time - 600,
                channel_id="channel1",
                channel_type="farcaster"
            ),
            Message(
                id="msg2", 
                content="I've been researching machine learning trends lately",
                sender="bob",
                sender_username="bob",
                sender_fid=456,
                timestamp=current_time - 500,
                channel_id="channel1",
                channel_type="farcaster"
            ),
            Message(
                id="msg3",
                content="AI is definitely going to change everything!",
                sender="alice", 
                sender_username="alice",
                sender_fid=123,
                timestamp=current_time - 400,
                channel_id="channel1",
                channel_type="farcaster"
            ),
            # Question in channel 2 (content sharing opportunity)
            Message(
                id="msg4",
                content="Can someone explain how transformers work in AI?",
                sender="bob",
                sender_username="bob",
                sender_fid=456,
                timestamp=current_time - 300,
                channel_id="channel2",
                channel_type="farcaster"
            ),
            # Quiet channel 3 (last message was 2 hours ago)
            Message(
                id="msg5",
                content="This channel seems quiet lately",
                sender="alice",
                sender_username="alice", 
                sender_fid=123,
                timestamp=current_time - 7200,  # 2 hours ago
                channel_id="channel3",
                channel_type="farcaster"
            )
        ]
        
        # Create test channels
        test_channels = {
            "channel1": Channel(
                id="channel1",
                name="general-discussion",
                type="farcaster", 
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
                type="farcaster",
                recent_messages=[msg for msg in test_messages if msg.channel_id == "channel3"]
            )
        }
        
        # Add channels to world state
        world_state.channels = test_channels
        
        # Add system status
        world_state.system_status = {
            "matrix_connected": True,
            "farcaster_connected": True,
            "last_observation_cycle": current_time - 60,
            "total_cycles": 42
        }
        
        world_state.last_update = current_time
        
        return world_state
    
    async def test_opportunity_detection(self):
        """Test the opportunity detection algorithms."""
        logger.info("Testing opportunity detection...")
        
        try:
            # Test basic opportunity detection
            opportunities = self.proactive_engine.analyze_world_state_for_opportunities(
                self.test_world_state
            )
            
            assert len(opportunities) > 0, "Should detect some opportunities"
            
            # Check for specific opportunity types
            opportunity_types = [opp.opportunity_type for opp in opportunities]
            
            # Should detect trending topic (AI discussion in channel1)
            assert "trending_topic" in opportunity_types, "Should detect trending topic"
            
            # Should detect quiet channel (channel3)  
            assert "quiet_channel" in opportunity_types, "Should detect quiet channel"
            
            # Should detect content sharing opportunity (question in channel2)
            assert "content_sharing" in opportunity_types, "Should detect content sharing opportunity"
            
            # Should detect user milestone (bob with 100 messages)
            assert "user_milestone" in opportunity_types, "Should detect user milestone"
            
            logger.info(f"✅ Opportunity detection test passed - detected {len(opportunities)} opportunities")
            self.test_results.append(("Opportunity Detection", True, f"Detected {len(opportunities)} opportunities"))
            
        except Exception as e:
            logger.error(f"❌ Opportunity detection test failed: {e}")
            self.test_results.append(("Opportunity Detection", False, str(e)))
    
    async def test_proactive_tools(self):
        """Test the proactive conversation tools."""
        logger.info("Testing proactive conversation tools...")
        
        # Test DetectConversationOpportunitiesTool
        await self.test_detect_opportunities_tool()
        
        # Test InitiateProactiveConversationTool
        await self.test_initiate_conversation_tool()
        
        # Test ScheduleProactiveEngagementTool
        await self.test_schedule_engagement_tool()
        
        # Test GetProactiveEngagementStatusTool
        await self.test_engagement_status_tool()
    
    async def test_detect_opportunities_tool(self):
        """Test the DetectConversationOpportunitiesTool."""
        try:
            tool = DetectConversationOpportunitiesTool()
            
            result = await tool.execute(
                context=self.test_context,
                analysis_scope="current_context",
                minimum_priority=0.3,
                max_opportunities=10
            )
            
            assert result["status"] == "success", f"Tool should succeed: {result.get('message', '')}"
            assert result["opportunities_found"] > 0, "Should find opportunities"
            assert "opportunities" in result, "Should include opportunities list"
            
            logger.info(f"✅ DetectConversationOpportunitiesTool test passed - found {result['opportunities_found']} opportunities")
            self.test_results.append(("DetectConversationOpportunitiesTool", True, f"Found {result['opportunities_found']} opportunities"))
            
        except Exception as e:
            logger.error(f"❌ DetectConversationOpportunitiesTool test failed: {e}")
            self.test_results.append(("DetectConversationOpportunitiesTool", False, str(e)))
    
    async def test_initiate_conversation_tool(self):
        """Test the InitiateProactiveConversationTool."""
        try:
            tool = InitiateProactiveConversationTool()
            
            result = await tool.execute(
                context=self.test_context,
                opportunity_type="trending_topic",
                channel_id="channel1",
                engagement_strategy="trending_topic_discussion",
                message_content="I noticed there's been great discussion about AI here! What aspects are you most excited about?",
                context_data={
                    "topic_keywords": ["AI", "machine learning"],
                    "timing_sensitivity": "immediate"
                }
            )
            
            assert result["status"] == "success", f"Tool should succeed: {result.get('message', '')}"
            assert "opportunity_id" in result, "Should return opportunity ID"
            assert result["channel_id"] == "channel1", "Should match requested channel"
            
            logger.info("✅ InitiateProactiveConversationTool test passed")
            self.test_results.append(("InitiateProactiveConversationTool", True, "Successfully initiated proactive conversation"))
            
        except Exception as e:
            logger.error(f"❌ InitiateProactiveConversationTool test failed: {e}")
            self.test_results.append(("InitiateProactiveConversationTool", False, str(e)))
    
    async def test_schedule_engagement_tool(self):
        """Test the ScheduleProactiveEngagementTool."""
        try:
            tool = ScheduleProactiveEngagementTool()
            
            # Schedule for 1 hour from now
            scheduled_time = (datetime.now() + timedelta(hours=1)).isoformat()
            
            result = await tool.execute(
                context=self.test_context,
                opportunity_id="test_opportunity_123",
                engagement_strategy="milestone_celebration",
                scheduled_time=scheduled_time,
                message_template="Congratulations on reaching 100 messages, {username}! 🎉",
                priority_score=0.8,
                context_data={"user_id": "user2", "milestone_type": "message_count"}
            )
            
            assert result["status"] == "success", f"Tool should succeed: {result.get('message', '')}"
            assert result["opportunity_id"] == "test_opportunity_123", "Should match opportunity ID"
            
            logger.info("✅ ScheduleProactiveEngagementTool test passed")
            self.test_results.append(("ScheduleProactiveEngagementTool", True, "Successfully scheduled engagement"))
            
        except Exception as e:
            logger.error(f"❌ ScheduleProactiveEngagementTool test failed: {e}")
            self.test_results.append(("ScheduleProactiveEngagementTool", False, str(e)))
    
    async def test_engagement_status_tool(self):
        """Test the GetProactiveEngagementStatusTool."""
        try:
            tool = GetProactiveEngagementStatusTool()
            
            # Test getting general engagement status
            result = await tool.execute(
                context=self.test_context,
                time_range_hours=24,
                include_metrics=True
            )
            
            assert result["status"] == "success", f"Tool should succeed: {result.get('message', '')}"
            assert "total_engagements" in result, "Should include total engagements"
            assert "success_rate" in result, "Should include success rate"
            
            logger.info("✅ GetProactiveEngagementStatusTool test passed")
            self.test_results.append(("GetProactiveEngagementStatusTool", True, "Successfully retrieved engagement status"))
            
        except Exception as e:
            logger.error(f"❌ GetProactiveEngagementStatusTool test failed: {e}")
            self.test_results.append(("GetProactiveEngagementStatusTool", False, str(e)))
    
    async def test_engine_lifecycle(self):
        """Test the proactive engine lifecycle management."""
        logger.info("Testing proactive engine lifecycle...")
        
        try:
            # Test start
            await self.proactive_engine.start()
            
            # Test world state change handling
            await self.proactive_engine.on_world_state_change()
            
            # Test stop
            await self.proactive_engine.stop()
            
            logger.info("✅ Engine lifecycle test passed")
            self.test_results.append(("Engine Lifecycle", True, "Start/stop/world state change handling works"))
            
        except Exception as e:
            logger.error(f"❌ Engine lifecycle test failed: {e}")
            self.test_results.append(("Engine Lifecycle", False, str(e)))
    
    async def test_integration_scenario(self):
        """Test a complete integration scenario."""
        logger.info("Testing complete integration scenario...")
        
        try:
            # 1. Start the engine
            await self.proactive_engine.start()
            
            # 2. Trigger world state change (simulates new activity)
            await self.proactive_engine.on_world_state_change()
            
            # 3. Detect opportunities using tool
            detect_tool = DetectConversationOpportunitiesTool()
            opportunities_result = await detect_tool.execute(
                context=self.test_context,
                analysis_scope="comprehensive",
                minimum_priority=0.5
            )
            
            assert opportunities_result["status"] == "success", "Should detect opportunities"
            assert opportunities_result["opportunities_found"] > 0, "Should find opportunities"
            
            # 4. Initiate proactive conversation based on detected opportunity
            if opportunities_result["opportunities"]:
                first_opportunity = opportunities_result["opportunities"][0]
                
                initiate_tool = InitiateProactiveConversationTool()
                initiate_result = await initiate_tool.execute(
                    context=self.test_context,
                    opportunity_type=first_opportunity["opportunity_type"],
                    channel_id=first_opportunity["channel_id"],
                    engagement_strategy="trending_topic_discussion",
                    message_content=f"I noticed {first_opportunity['reasoning']} - what are your thoughts?"
                )
                
                assert initiate_result["status"] == "success", "Should initiate conversation"
                
                # 5. Check engagement status
                status_tool = GetProactiveEngagementStatusTool()
                status_result = await status_tool.execute(
                    context=self.test_context,
                    opportunity_id=initiate_result["opportunity_id"]
                )
                
                assert status_result["status"] in ["success", "not_found"], "Should check status"
            
            # 6. Stop the engine
            await self.proactive_engine.stop()
            
            logger.info("✅ Integration scenario test passed")
            self.test_results.append(("Integration Scenario", True, "Complete workflow executed successfully"))
            
        except Exception as e:
            logger.error(f"❌ Integration scenario test failed: {e}")
            self.test_results.append(("Integration Scenario", False, str(e)))
    
    async def test_edge_cases(self):
        """Test edge cases and error handling."""
        logger.info("Testing edge cases...")
        
        try:
            # Test with empty world state
            empty_world_state = WorldStateData(
                channels={},
                matrix_users={},
                farcaster_users={},
                action_history=[],
                last_updated=time.time()
            )
            
            opportunities = self.proactive_engine.analyze_world_state_for_opportunities(empty_world_state)
            assert isinstance(opportunities, list), "Should return empty list for empty world state"
            
            # Test tool with invalid parameters
            detect_tool = DetectConversationOpportunitiesTool()
            result = await detect_tool.execute(
                context=self.test_context,
                minimum_priority=2.0  # Invalid range
            )
            
            # Should handle gracefully (either error or clamp value)
            assert "status" in result, "Should return status"
            
            logger.info("✅ Edge cases test passed")
            self.test_results.append(("Edge Cases", True, "Error handling works correctly"))
            
        except Exception as e:
            logger.error(f"❌ Edge cases test failed: {e}")
            self.test_results.append(("Edge Cases", False, str(e)))
    
    def print_test_results(self):
        """Print comprehensive test results."""
        logger.info("\n" + "="*60)
        logger.info("PROACTIVE CONVERSATION SYSTEM TEST RESULTS")
        logger.info("="*60)
        
        passed = 0
        failed = 0
        
        for test_name, success, details in self.test_results:
            status = "✅ PASS" if success else "❌ FAIL"
            logger.info(f"{status} | {test_name:<30} | {details}")
            if success:
                passed += 1
            else:
                failed += 1
        
        logger.info("="*60)
        logger.info(f"SUMMARY: {passed} passed, {failed} failed, {passed + failed} total")
        
        if failed == 0:
            logger.info("🎉 ALL TESTS PASSED! Proactive conversation system is working correctly.")
        else:
            logger.warning(f"⚠️  {failed} tests failed. Please review the issues above.")
        
        return failed == 0


async def run_comprehensive_tests():
    """Run the comprehensive test suite."""
    logger.info("Starting comprehensive proactive conversation system tests...")
    
    # Create test instance
    test_suite = TestProactiveSystem()
    
    try:
        # Setup test environment
        await test_suite.setup_test_environment()
        
        # Run all tests
        await test_suite.test_opportunity_detection()
        await test_suite.test_proactive_tools()
        await test_suite.test_engine_lifecycle()
        await test_suite.test_integration_scenario()
        await test_suite.test_edge_cases()
        
        # Print results
        all_passed = test_suite.print_test_results()
        
        return all_passed
        
    except Exception as e:
        logger.error(f"Test suite failed with error: {e}")
        return False


if __name__ == "__main__":
    asyncio.run(run_comprehensive_tests())
