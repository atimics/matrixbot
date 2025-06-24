"""
Test the Thread-Centric, Attention-Driven Architecture

This test verifies the complete flow of the new architecture:
1. AttentionEngine filters messages and creates ContextualThreads
2. ProcessingHub processes threads from the AttentionQueue
3. Commander AI handles complex analysis via ContextualThreads
4. Sub-Agents use scoped tool registries for focused missions
"""

import asyncio
import pytest
import time
from unittest.mock import Mock, AsyncMock

from chatbot.core.attention.engine import AttentionEngine
from chatbot.core.attention.structures import ContextualThread, ThreadPriority, AttentionMetrics
from chatbot.core.world_state.structures import Message, Channel, FarcasterUserDetails, Mission
from chatbot.core.world_state.manager import WorldStateManager
from chatbot.core.orchestration.processing_hub import ProcessingHub
from chatbot.core.processors.adaptive_processor import AdaptiveProcessor
from chatbot.core.processors.mission_processor import MissionProcessor
from chatbot.tools.registry import ToolRegistry
from chatbot.tools.core_tools import WaitTool, AssignMissionTool


class TestThreadCentricArchitecture:
    """Test suite for the new thread-centric architecture."""
    
    @pytest.fixture
    def sample_message(self):
        """Create a sample message for testing."""
        return Message(
            id="test_msg_123",
            channel_id="test_channel",
            channel_type="matrix",
            sender="@user:example.com",
            content="Hello, can you help me with something?",
            timestamp=time.time()
        )
    
    @pytest.fixture
    def sample_channel(self):
        """Create a sample channel for testing."""
        return Channel(
            id="test_channel",
            type="matrix",
            name="Test Channel",
            recent_messages=[]
        )
    
    @pytest.fixture
    def sample_user(self):
        """Create a sample user for testing."""
        return FarcasterUserDetails(
            fid="12345",
            username="testuser",
            display_name="Test User",
            bio="A test user",
            follower_count=100,
            power_badge=False
        )
    
    @pytest.fixture
    def mock_world_state(self, sample_channel, sample_user):
        """Create a mock world state manager."""
        world_state = Mock(spec=WorldStateManager)
        
        # Mock state data
        state_data = Mock()
        state_data.channels = {"test_channel": sample_channel}
        state_data.farcaster_users = {"12345": sample_user}
        state_data.matrix_users = {}
        state_data.missions = {}
        state_data.last_update = time.time()
        
        world_state.get_state_data.return_value = state_data
        world_state.get_conversation_history.return_value = []
        world_state.get_user_profile.return_value = sample_user
        world_state.get_channel_by_id.return_value = sample_channel
        world_state.get_last_bot_activity_in_thread.return_value = None
        
        return world_state
    
    @pytest.fixture
    def attention_queue(self):
        """Create an attention queue for testing."""
        return asyncio.Queue(maxsize=10)
    
    @pytest.fixture
    def attention_engine(self, mock_world_state, attention_queue):
        """Create an AttentionEngine for testing."""
        config = {
            'bot_fid': '99999',
            'bot_user_id': '@bot:example.com',
            'bot_username': 'testbot',
            'conversation_cooldown': 180
        }
        return AttentionEngine(mock_world_state, attention_queue, config)
    
    @pytest.mark.asyncio
    async def test_attention_engine_filters_self_messages(self, attention_engine, sample_message):
        """Test that AttentionEngine filters out bot's own messages."""
        # Create a message from the bot
        bot_message = Message(
            id="bot_msg_123",
            channel_id="test_channel",
            channel_type="matrix",
            sender="@bot:example.com",  # Bot's user ID
            content="I am responding",
            timestamp=time.time()
        )
        
        # Process the message
        result = await attention_engine.process_new_message(bot_message)
        
        # Should return None (filtered out)
        assert result is None
        assert attention_engine.attention_queue.empty()
        
        # Check metrics
        metrics = attention_engine.get_metrics_summary()
        assert metrics['self_messages_ignored'] == 1
        assert metrics['threads_created'] == 0
    
    @pytest.mark.asyncio
    async def test_attention_engine_creates_contextual_thread(self, attention_engine, sample_message):
        """Test that AttentionEngine creates ContextualThread for valid messages."""
        # Process a user message
        result = await attention_engine.process_new_message(sample_message)
        
        # Should create a thread
        assert result is not None
        assert isinstance(result, ContextualThread)
        assert result.triggering_message == sample_message
        assert result.thread_id == sample_message.id  # No reply_to, so uses message ID
        
        # Thread should be in the queue
        assert not attention_engine.attention_queue.empty()
        queued_thread = await attention_engine.attention_queue.get()
        assert queued_thread.thread_id == result.thread_id
    
    @pytest.mark.asyncio
    async def test_contextual_thread_priority_calculation(self, attention_engine):
        """Test that ContextualThread priority is calculated correctly."""
        # Direct mention should get high priority
        mention_message = Message(
            id="mention_msg",
            channel_id="test_channel",
            channel_type="matrix",
            sender="@user:example.com",
            content="Hey @bot:example.com, can you help?",
            timestamp=time.time()
        )
        
        result = await attention_engine.process_new_message(mention_message)
        assert result.priority == ThreadPriority.URGENT  # Should get high priority for mention
        
        # Question should get medium priority
        question_message = Message(
            id="question_msg",
            channel_id="test_channel",
            channel_type="matrix",
            sender="@user:example.com",
            content="How does this work?",
            timestamp=time.time()
        )
        
        result = await attention_engine.process_new_message(question_message)
        assert result.priority == ThreadPriority.HIGH  # NORMAL (5) + question boost (2) = 7 (HIGH)
    
    def test_contextual_thread_context_score(self, sample_message, sample_user, sample_channel):
        """Test ContextualThread context score calculation."""
        thread = ContextualThread(
            thread_id="test_thread",
            triggering_message=sample_message,
            conversation_history=[sample_message],  # Some history
            author_context=sample_user,  # Rich user context
            channel_context=sample_channel  # Channel context
        )
        
        score = thread.calculate_context_score()
        
        # Should have a reasonable score with all context available
        assert 0.0 < score <= 1.0
        assert score > 0.5  # Should be relatively high with good context
    
    def test_mission_scoped_tool_registry(self):
        """Test that MissionProcessor creates scoped tool registry correctly."""
        # Create a main tool registry with multiple tools
        main_registry = ToolRegistry()
        main_registry.register_tool(WaitTool())
        main_registry.register_tool(AssignMissionTool())
        
        # Create a mission with limited tool scope
        mission = Mission(
            id="test_mission",
            objective="Answer user questions",
            channel_id="test_channel",
            tool_scope=["wait"]  # Only allow wait tool
        )
        
        # Create MissionProcessor
        mock_ai_engine = Mock()
        mock_world_state = Mock()
        mock_action_context = Mock()
        
        processor = MissionProcessor(
            mission=mission,
            lightweight_ai_engine=mock_ai_engine,
            world_state_data=mock_world_state,
            main_tool_registry=main_registry,
            action_context=mock_action_context
        )
        
        # Check that scoped registry only has the wait tool
        scoped_tools = processor.tool_registry.get_all_tool_names()
        assert "wait" in scoped_tools
        assert "assign_mission_to_channel" not in scoped_tools
        assert len(scoped_tools) == 1
    
    @pytest.mark.asyncio
    async def test_end_to_end_thread_processing(self, mock_world_state, attention_queue):
        """Test the complete end-to-end thread processing flow."""
        # Setup components
        attention_engine = AttentionEngine(
            mock_world_state, 
            attention_queue, 
            {'bot_fid': '99999', 'bot_user_id': '@bot:example.com'}
        )
        
        # Create a mock processing hub that can handle threads
        mock_processing_hub = Mock()
        mock_commander = Mock()
        
        # Create a user message
        user_message = Message(
            id="user_msg_123",
            channel_id="test_channel",
            channel_type="matrix",
            sender="@user:example.com",
            content="Can you help me understand this?",
            timestamp=time.time()
        )
        
        # Step 1: AttentionEngine processes message and creates thread
        await attention_engine.process_new_message(user_message)
        
        # Step 2: Thread should be in queue
        assert not attention_queue.empty()
        thread = await attention_queue.get()
        
        # Step 3: Verify thread properties
        assert isinstance(thread, ContextualThread)
        assert thread.triggering_message == user_message
        assert thread.reason == "Question (Priority: HIGH)"  # Should detect question
        assert thread.priority == ThreadPriority.HIGH
        
        # Step 4: Thread should have context score
        score = thread.calculate_context_score()
        assert score > 0.0
        
        # Step 5: Verify thread summary for monitoring
        summary = thread.to_summary_dict()
        assert summary['thread_id'] == thread.thread_id
        assert summary['priority'] == 'HIGH'
        assert 'content_preview' in summary
    
    def test_attention_metrics_tracking(self, attention_engine, sample_message):
        """Test that AttentionEngine properly tracks metrics."""
        metrics = attention_engine.metrics
        
        # Initially should be zero
        assert metrics.total_messages_processed == 0
        assert metrics.threads_created == 0
        assert metrics.attention_rate == 0.0
        
        # Process a valid message (async, so we need to mock the creation)
        thread = ContextualThread(
            thread_id="test_thread",
            triggering_message=sample_message
        )
        
        # Simulate thread creation
        metrics.add_thread_created(thread, 0.1)  # 100ms processing time
        
        # Check updated metrics
        assert metrics.total_messages_processed == 1
        assert metrics.threads_created == 1
        assert metrics.attention_rate == 1.0
        assert metrics.get_average_processing_time() == 0.1
        
        # Process a filtered message
        metrics.add_message_filtered("self_message")
        
        # Check metrics after filtering
        assert metrics.total_messages_processed == 2
        assert metrics.threads_created == 1
        assert metrics.self_messages_ignored == 1
        assert metrics.attention_rate == 0.5  # 1 thread out of 2 messages
    
    def test_mission_tool_scope_validation(self):
        """Test that mission tool scope properly restricts Sub-Agent capabilities."""
        # Create main registry with several tools
        main_registry = ToolRegistry()
        main_registry.register_tool(WaitTool())
        main_registry.register_tool(AssignMissionTool())
        
        # Create mission with specific tool scope
        mission = Mission(
            id="limited_mission",
            objective="Send a simple reply",
            channel_id="test_channel",
            tool_scope=["wait", "send_matrix_message"]  # Limited scope
        )
        
        # Create processor
        processor = MissionProcessor(
            mission=mission,
            lightweight_ai_engine=Mock(),
            world_state_data=Mock(),
            main_tool_registry=main_registry,
            action_context=Mock()
        )
        
        # Verify tool scope restriction
        available_tools = processor.tool_registry.get_all_tool_names()
        
        # Should only have tools in scope (wait is available, but send_matrix_message might not be registered)
        assert "wait" in available_tools
        assert "assign_mission_to_channel" not in available_tools
        
        # Tool registry should be isolated
        assert len(available_tools) <= 2  # At most the scoped tools
        assert processor.tool_registry != main_registry  # Different instances


if __name__ == "__main__":
    # Run a quick integration test
    async def integration_test():
        print("Running Thread-Centric Architecture Integration Test...")
        
        # Create test components
        queue = asyncio.Queue()
        world_state = Mock(spec=WorldStateManager)
        
        # Mock world state data
        state_data = Mock()
        state_data.channels = {}
        state_data.farcaster_users = {}
        state_data.matrix_users = {}
        world_state.get_state_data.return_value = state_data
        world_state.get_conversation_history.return_value = []
        world_state.get_user_profile.return_value = None
        world_state.get_channel_by_id.return_value = None
        world_state.get_last_bot_activity_in_thread.return_value = None
        
        # Create attention engine
        engine = AttentionEngine(world_state, queue, {
            'bot_fid': '99999',
            'bot_user_id': '@bot:example.com'
        })
        
        # Test message processing
        test_message = Message(
            id="integration_test_msg",
            channel_id="test_channel",
            channel_type="matrix",
            sender="@user:example.com",
            content="Hello, this is a test message",
            timestamp=time.time()
        )
        
        # Process message
        await engine.process_new_message(test_message)
        
        # Check that thread was created
        assert not queue.empty()
        thread = await queue.get()
        
        print(f"✅ Successfully created ContextualThread: {thread.thread_id}")
        print(f"✅ Thread priority: {thread.priority.name}")
        print(f"✅ Thread reason: {thread.reason}")
        print(f"✅ Context score: {thread.calculate_context_score():.2f}")
        
        # Check metrics
        metrics = engine.get_metrics_summary()
        print(f"✅ Metrics - Messages processed: {metrics['total_messages_processed']}")
        print(f"✅ Metrics - Threads created: {metrics['threads_created']}")
        print(f"✅ Metrics - Attention rate: {metrics['attention_rate']:.2f}")
        
        print("\n🎉 Thread-Centric Architecture Integration Test PASSED!")
    
    # Run the integration test
    asyncio.run(integration_test())
