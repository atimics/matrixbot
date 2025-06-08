#!/usr/bin/env python3
"""
Unit Tests for Proactive Conversation Functionality

Basic unit tests to validate that the proactive conversation system components
are working correctly.
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, AsyncMock

from chatbot.core.proactive.proactive_engine import ProactiveConversationEngine, ConversationOpportunity
from chatbot.core.world_state.structures import WorldStateData, Channel, Message, FarcasterUserDetails, SentimentData


class TestProactiveConversationEngine:
    """Unit tests for the ProactiveConversationEngine."""
    
    @pytest.fixture
    def mock_world_state_manager(self):
        """Create a mock world state manager."""
        mock = AsyncMock()
        mock.get_world_state_data.return_value = WorldStateData()
        return mock
    
    @pytest.fixture 
    def mock_context_manager(self):
        """Create a mock context manager."""
        return Mock()
    
    @pytest.fixture
    def proactive_engine(self, mock_world_state_manager, mock_context_manager):
        """Create a proactive conversation engine instance."""
        return ProactiveConversationEngine(
            world_state_manager=mock_world_state_manager,
            context_manager=mock_context_manager
        )
    
    def test_engine_initialization(self, proactive_engine):
        """Test that the engine initializes correctly."""
        assert proactive_engine is not None
        assert proactive_engine.world_state_manager is not None
        assert proactive_engine.context_manager is not None
        assert proactive_engine.get_active_opportunities() == []
    
    def test_conversation_opportunity_creation(self):
        """Test that ConversationOpportunity objects can be created."""
        opportunity = ConversationOpportunity(
            opportunity_id="test_123",
            opportunity_type="trending_topic",
            priority=8,
            context={"topic": "AI"},
            platform="farcaster",
            channel_id="test_channel",
            reasoning="Test opportunity"
        )
        
        assert opportunity.opportunity_id == "test_123"
        assert opportunity.opportunity_type == "trending_topic"
        assert opportunity.priority == 8
        assert opportunity.context["topic"] == "AI"
        assert opportunity.platform == "farcaster"
        assert opportunity.channel_id == "test_channel"
        assert opportunity.reasoning == "Test opportunity"
    
    def test_opportunity_expiration(self):
        """Test opportunity expiration logic."""
        # Create expired opportunity
        expired_opportunity = ConversationOpportunity(
            opportunity_id="expired_123",
            opportunity_type="test",
            priority=5,
            context={},
            platform="matrix",
            expires_at=time.time() - 3600,  # Expired 1 hour ago
            reasoning="Expired test opportunity"
        )
        
        assert expired_opportunity.is_expired()
        
        # Create non-expired opportunity  
        active_opportunity = ConversationOpportunity(
            opportunity_id="active_123",
            opportunity_type="test",
            priority=5,
            context={},
            platform="matrix",
            expires_at=time.time() + 3600,  # Expires in 1 hour
            reasoning="Active test opportunity"
        )
        
        assert not active_opportunity.is_expired()
    
    def test_analyze_empty_world_state(self, proactive_engine):
        """Test analyzing an empty world state."""
        empty_world_state = WorldStateData()
        
        opportunities = proactive_engine.analyze_world_state_for_opportunities(empty_world_state)
        
        assert isinstance(opportunities, list)
        # Empty world state should produce no opportunities or only very generic ones
        assert len(opportunities) >= 0
    
    def test_analyze_world_state_with_data(self, proactive_engine):
        """Test analyzing a world state with realistic data."""
        current_time = time.time()
        
        # Create test world state
        world_state = WorldStateData()
        
        # Add a test user
        world_state.farcaster_users["123"] = FarcasterUserDetails(
            fid="123",
            username="alice",
            display_name="Alice Johnson",
            follower_count=100,  # Milestone
            sentiment=SentimentData(
                score=0.8,
                label="positive",
                last_updated=current_time
            )
        )
        
        # Add a test channel with messages
        test_messages = [
            Message(
                id="msg1",
                channel_type="farcaster",
                sender="alice",
                content="What do you think about AI?",
                timestamp=current_time - 300,
                channel_id="test_channel"
            ),
            Message(
                id="msg2", 
                channel_type="farcaster",
                sender="alice",
                content="I'm really excited about machine learning!",
                timestamp=current_time - 200,
                channel_id="test_channel"
            )
        ]
        
        world_state.channels["test_channel"] = Channel(
            id="test_channel",
            name="ai-discussion",
            type="farcaster",
            recent_messages=test_messages
        )
        
        # Analyze for opportunities
        opportunities = proactive_engine.analyze_world_state_for_opportunities(world_state)
        
        assert isinstance(opportunities, list)
        assert len(opportunities) > 0  # Should detect some opportunities
        
        # Check that opportunities have required fields
        for opp in opportunities:
            assert hasattr(opp, 'opportunity_id')
            assert hasattr(opp, 'opportunity_type')
            assert hasattr(opp, 'priority')
            assert hasattr(opp, 'reasoning')
            assert isinstance(opp.context, dict)
    
    def test_opportunity_registration(self, proactive_engine):
        """Test registering and retrieving opportunities."""
        test_opportunity = ConversationOpportunity(
            opportunity_id="reg_test_123",
            opportunity_type="test",
            priority=7,
            context={"test": "data"},
            platform="matrix",
            channel_id="test_channel",
            reasoning="Test opportunity registration"
        )
        
        # Register opportunity
        proactive_engine.register_active_opportunity(test_opportunity)
        
        # Retrieve active opportunities
        active = proactive_engine.get_active_opportunities()
        
        assert len(active) == 1
        assert active[0].opportunity_id == "reg_test_123"
        assert active[0].opportunity_type == "test"
    
    def test_opportunity_cleanup(self, proactive_engine):
        """Test cleanup of expired opportunities."""
        # Add an expired opportunity
        expired_opportunity = ConversationOpportunity(
            opportunity_id="expired_test",
            opportunity_type="test",
            priority=5,
            context={},
            platform="matrix",
            expires_at=time.time() - 1000,  # Expired
            reasoning="Expired test opportunity"
        )
        
        proactive_engine.register_active_opportunity(expired_opportunity)
        
        # Verify expired opportunity was added to the internal storage (before cleanup)
        assert len(proactive_engine.active_opportunities) == 1
        
        # Add an active opportunity
        active_opportunity = ConversationOpportunity(
            opportunity_id="active_test",
            opportunity_type="test", 
            priority=5,
            context={},
            platform="matrix",
            expires_at=time.time() + 1000,  # Not expired
            reasoning="Active test opportunity"
        )
        
        proactive_engine.register_active_opportunity(active_opportunity)
        
        # Should have 2 opportunities in internal storage before cleanup
        assert len(proactive_engine.active_opportunities) == 2
        
        # But get_active_opportunities() should only return non-expired ones
        active_before_cleanup = proactive_engine.get_active_opportunities()
        assert len(active_before_cleanup) == 1  # Only the non-expired one
        
        # Cleanup expired opportunities
        proactive_engine.cleanup_expired_opportunities()
        
        # Should have 1 opportunity after cleanup
        active = proactive_engine.get_active_opportunities()
        assert len(active) == 1
        assert active[0].opportunity_id == "active_test"
    
    @pytest.mark.asyncio
    async def test_engine_lifecycle(self, proactive_engine):
        """Test engine start/stop lifecycle."""
        # Test start
        await proactive_engine.start()
        
        # Test world state change handling
        await proactive_engine.on_world_state_change()
        
        # Test stop
        await proactive_engine.stop()
        
        # Should complete without errors


class TestProactiveConversationTools:
    """Unit tests for proactive conversation tools (basic import/structure tests)."""
    
    def test_tools_import(self):
        """Test that proactive conversation tools can be imported."""
        try:
            from chatbot.tools.proactive_conversation_tools import (
                InitiateProactiveConversationTool,
                DetectConversationOpportunitiesTool,
                ScheduleProactiveEngagementTool,
                GetProactiveEngagementStatusTool
            )
            
            # Test that classes exist and are classes (not instantiated)
            assert InitiateProactiveConversationTool is not None
            assert DetectConversationOpportunitiesTool is not None
            assert ScheduleProactiveEngagementTool is not None
            assert GetProactiveEngagementStatusTool is not None
            
        except ImportError as e:
            pytest.fail(f"Failed to import proactive conversation tools: {e}")
    
    def test_tools_inheritance(self):
        """Test that tools properly inherit from ToolInterface."""
        from chatbot.tools.proactive_conversation_tools import InitiateProactiveConversationTool
        from chatbot.tools.base import ToolInterface
        
        # Test that the class is a subclass (don't instantiate)
        assert issubclass(InitiateProactiveConversationTool, ToolInterface)
        
        # Test that it has the required abstract methods defined
        assert hasattr(InitiateProactiveConversationTool, 'execute')
        assert hasattr(InitiateProactiveConversationTool, 'name')
        assert hasattr(InitiateProactiveConversationTool, 'description')
        assert hasattr(InitiateProactiveConversationTool, 'parameters_schema')


def test_proactive_imports():
    """Test that all proactive conversation components can be imported."""
    try:
        from chatbot.core.proactive.proactive_engine import ProactiveConversationEngine
        from chatbot.core.proactive.engagement_strategies import (
            EngagementStrategy,
            TrendingTopicStrategy,
            QuietChannelStrategy,
            UserMilestoneStrategy,
            ContentSharingStrategy
        )
        from chatbot.core.proactive import ConversationOpportunity
        
        # All imports should succeed
        assert ProactiveConversationEngine is not None
        assert EngagementStrategy is not None
        assert TrendingTopicStrategy is not None
        assert QuietChannelStrategy is not None
        assert UserMilestoneStrategy is not None
        assert ContentSharingStrategy is not None
        assert ConversationOpportunity is not None
        
    except ImportError as e:
        pytest.fail(f"Failed to import proactive conversation components: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
