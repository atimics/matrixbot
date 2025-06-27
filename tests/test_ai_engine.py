"""
Tests for AI decision engine functionality.
"""
import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock, Mock
from chatbot.core.ai_engine import AIDecisionEngine


class TestAIDecisionEngine:
    """Test the AI decision engine with various scenarios."""
    
    def test_initialization_with_config(self):
        """Test initialization with custom config."""
        engine = AIDecisionEngine(api_key="test_key", model="claude-3-haiku")
        
        assert engine.api_key == "test_key"
        assert engine.model == "claude-3-haiku"
        assert engine.base_url is not None
    
    def test_initialization_without_api_key(self):
        """Test initialization fails without API key."""
        with pytest.raises(TypeError):
            # Should fail because api_key is required parameter
            AIDecisionEngine()
    
    @pytest.mark.asyncio
    async def test_make_decision_successful_response(self):
        """Test successful decision making with mocked response."""
        engine = AIDecisionEngine(api_key="test_key")
        
        # Mock response data that matches current JSON structure
        mock_response_data = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "observations": "Test observation",
                        "potential_actions": [],
                        "selected_actions": [{
                            "action_type": "wait",
                            "parameters": {},
                            "reasoning": "No action needed",
                            "priority": 1
                        }],
                        "reasoning": "Test reasoning"
                    })
                }
            }]
        }
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status = MagicMock()
        
        # Mock httpx.AsyncClient properly
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            
            # Set up the async context manager
            mock_client_class.return_value = mock_client
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            
            result = await engine.make_decision({"test": "state"}, "test_cycle")
            
            assert result.cycle_id == "test_cycle"
            assert result.observations == "Test observation"
            assert len(result.selected_actions) == 1
            assert result.selected_actions[0].action_type == "wait"
    
    @pytest.mark.asyncio
    async def test_make_decision_invalid_json_response(self):
        """Test handling of invalid JSON response."""
        engine = AIDecisionEngine(api_key="test_key")
        
        # Mock response for initial request (invalid JSON)
        mock_invalid_response_data = {
            "choices": [{
                "message": {
                    "content": "Invalid JSON response"
                }
            }]
        }
        
        # Mock response for recovery request (valid JSON)
        mock_recovery_response_data = {
            "choices": [{
                "message": {
                    "content": '{"reasoning": "Error recovery response", "selected_actions": [{"action_type": "wait", "details": {}}]}'
                }
            }]
        }
        
        mock_invalid_response = Mock()
        mock_invalid_response.status_code = 200
        mock_invalid_response.json.return_value = mock_invalid_response_data
        mock_invalid_response.raise_for_status = Mock()
        
        mock_recovery_response = Mock()
        mock_recovery_response.status_code = 200
        mock_recovery_response.json.return_value = mock_recovery_response_data
        mock_recovery_response.raise_for_status = Mock()
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            # First call returns invalid JSON, second call (recovery) returns valid JSON
            mock_client.post = AsyncMock(side_effect=[mock_invalid_response, mock_recovery_response])
            
            # Set up the async context manager properly
            mock_client_class.return_value = mock_client
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            
            result = await engine.make_decision({"test": "state"}, "test_cycle")
            
            # Should handle invalid JSON gracefully via error recovery
            assert result.cycle_id == "test_cycle"
            assert result.reasoning == "Error recovery response"
            assert len(result.selected_actions) == 1
            assert result.selected_actions[0].action_type == "wait"
            
            # Verify that two HTTP requests were made (original + recovery)
            assert mock_client.post.call_count == 2
    
    @pytest.mark.asyncio
    async def test_make_decision_http_error(self):
        """Test handling of HTTP errors."""
        engine = AIDecisionEngine(api_key="test_key")
        
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.raise_for_status = Mock()
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            
            # Set up the async context manager properly
            mock_client_class.return_value = mock_client
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            
            result = await engine.make_decision({"test": "state"}, "test_cycle")
            
            assert result.cycle_id == "test_cycle"
            assert len(result.selected_actions) == 0
            assert "API Error" in result.reasoning
    
    @pytest.mark.asyncio
    async def test_make_decision_network_exception(self):
        """Test handling of network exceptions."""
        engine = AIDecisionEngine(api_key="test_key")
        
        # Mock the error recovery system to return None (failed recovery)
        with patch.object(engine.error_recovery, 'handle_ai_failure', return_value=None) as mock_recovery:
            # Mock the performance monitor to prevent any issues there
            with patch('chatbot.core.ai_engine.performance_monitor'):
                with patch('httpx.AsyncClient') as mock_client_class:
                    mock_client = AsyncMock()
                    mock_client.post = AsyncMock(side_effect=Exception("Network timeout"))
                    
                    # Set up the async context manager properly
                    mock_client_class.return_value = mock_client
                    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                    mock_client.__aexit__ = AsyncMock(return_value=None)
                    
                    result = await engine.make_decision({"test": "state"}, "test_cycle")
                    
                    assert result.cycle_id == "test_cycle"
                    assert len(result.selected_actions) == 0
                    assert "error" in result.reasoning.lower()
                    
                    # Verify that error recovery was attempted
                    mock_recovery.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_make_decision_no_choices_in_response(self):
        """Test handling of response with no choices."""
        engine = AIDecisionEngine(api_key="test_key")
        
        mock_response_data = {
            "choices": []
        }
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status = Mock()
        
        # Mock the error recovery system to prevent hanging
        with patch.object(engine.error_recovery, 'handle_ai_failure', return_value=None) as mock_recovery:
            # Mock the performance monitor to prevent any issues there
            with patch('chatbot.core.ai_engine.performance_monitor'):
                with patch('httpx.AsyncClient') as mock_client_class:
                    mock_client = AsyncMock()
                    mock_client.post = AsyncMock(return_value=mock_response)
                    
                    # Set up the async context manager properly
                    mock_client_class.return_value = mock_client
                    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                    mock_client.__aexit__ = AsyncMock(return_value=None)
                    
                    result = await engine.make_decision({"test": "state"}, "test_cycle")
                    
                    assert result.cycle_id == "test_cycle"
                    assert len(result.selected_actions) == 0
    
    def test_cleanup(self):
        """Test cleanup method (if it exists)."""
        engine = AIDecisionEngine(api_key="test_key")
        # Current implementation doesn't have cleanup method, so just verify it doesn't crash
        # If cleanup method is added later, this test should be updated
        assert engine.api_key == "test_key"

    @pytest.mark.asyncio
    async def test_mission_oriented_decision_making(self):
        """Test that AI engine properly handles mission-oriented state management."""
        engine = AIDecisionEngine(api_key="test_key")
        
        # Mock world state with an active mission to prevent repetitive loops
        world_state_with_mission = {
            "current_mission": {
                "id": "mission_123",
                "objective": "Analyze user's codebase structure",
                "status": "active",
                "key_results": ["Acknowledged user request"],
                "priority": 8,
                "created_at": 1703000000,
                "updated_at": 1703000001,
                "context": {"user_id": "test_user", "channel_id": "test_channel"}
            },
            "action_history": [{
                "action_type": "send_matrix_message",
                "parameters": {"message": "I'll analyze your codebase structure"},
                "timestamp": 1703000001,
                "channel_id": "test_channel"
            }],
            "channels": {
                "test_channel": {
                    "name": "Test Channel",
                    "messages": [{"id": "msg_1", "content": "Please analyze my repo", "sender": "test_user"}]
                }
            }
        }
        
        # Mock response showing mission-aware decision making
        mock_response_data = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "observations": "Active mission detected: Analyze user's codebase structure. User request already acknowledged.",
                        "potential_actions": [
                            {"action_type": "get_codebase_structure", "reasoning": "Continue mission progress"},
                            {"action_type": "update_mission_status", "reasoning": "Track progress"}
                        ],
                        "selected_actions": [{
                            "action_type": "get_codebase_structure",
                            "parameters": {"repository": "user_repo"},
                            "reasoning": "Advancing active mission by gathering codebase data",
                            "priority": 9
                        }],
                        "reasoning": "Continuing active mission rather than re-acknowledging user request"
                    })
                }
            }]
        }
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status = MagicMock()
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            
            result = await engine.make_decision(world_state_with_mission, "mission_cycle_27")
            
            assert result.cycle_id == "mission_cycle_27"
            assert "active mission" in result.observations.lower()
            assert len(result.selected_actions) == 1
            assert result.selected_actions[0].action_type == "get_codebase_structure"
            assert "advancing active mission" in result.selected_actions[0].reasoning.lower()

    @pytest.mark.asyncio
    async def test_action_loop_prevention(self):
        """Test prevention of repetitive action loops identified in the engineering report."""
        engine = AIDecisionEngine(api_key="test_key")
        
        # World state showing the bot has already replied but mission is not updated
        world_state_with_loop_risk = {
            "current_processing_channel_id": "test_channel",
            "action_history": [
                {
                    "action_type": "send_matrix_message",
                    "parameters": {"message": "I'll help you with that", "event_id": "$original_user_msg"},
                    "timestamp": 1703000000,
                    "channel_id": "test_channel"
                },
                {
                    "action_type": "send_matrix_message", 
                    "parameters": {"message": "Let me analyze your request", "event_id": "$original_user_msg"},
                    "timestamp": 1703000060,
                    "channel_id": "test_channel"
                }
            ],
            "channels": {
                "test_channel": {
                    "name": "Test Channel",
                    "messages": [
                        {"id": "$original_user_msg", "content": "Help me debug this code", "sender": "test_user", "timestamp": 1702999900},
                        {"id": "$bot_reply_1", "content": "I'll help you with that", "sender": "ratichat", "timestamp": 1703000000},
                        {"id": "$bot_reply_2", "content": "Let me analyze your request", "sender": "ratichat", "timestamp": 1703000060}
                    ]
                }
            }
        }
        
        # Mock response showing loop detection and prevention
        mock_response_data = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "observations": "User request from test_user detected. Action history shows I've already replied twice to the same message. Risk of repetitive loop detected.",
                        "potential_actions": [
                            {"action_type": "send_matrix_message", "reasoning": "Already done - would create loop"},
                            {"action_type": "set_mission_goal", "reasoning": "Establish clear objective"},
                            {"action_type": "wait", "reasoning": "Avoid repetitive actions"}
                        ],
                        "selected_actions": [{
                            "action_type": "set_mission_goal",
                            "parameters": {
                                "objective": "Debug user's code issue", 
                                "key_results": ["Gather code details", "Identify problem", "Provide solution"],
                                "priority": 7
                            },
                            "reasoning": "Setting mission to prevent action loops and provide clear direction",
                            "priority": 8
                        }],
                        "reasoning": "Detected potential action loop. Setting mission to provide structure and prevent repetitive replies."
                    })
                }
            }]
        }
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status = MagicMock()
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            
            result = await engine.make_decision(world_state_with_loop_risk, "loop_prevention_cycle")
            
            assert result.cycle_id == "loop_prevention_cycle"
            assert "loop" in result.observations.lower() or "repetitive" in result.observations.lower()
            assert len(result.selected_actions) == 1
            assert result.selected_actions[0].action_type == "set_mission_goal"
            assert "prevent" in result.reasoning.lower()

    @pytest.mark.asyncio
    async def test_network_timeout_with_retry_logic(self):
        """Test enhanced network error handling with retry mechanisms."""
        engine = AIDecisionEngine(api_key="test_key")
        
        # Mock httpx.ReadTimeout specifically (as mentioned in the report)
        import httpx
        
        # First call fails with ReadTimeout, second succeeds
        mock_success_response_data = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "observations": "Network recovered, proceeding with analysis",
                        "selected_actions": [{
                            "action_type": "wait",
                            "parameters": {},
                            "reasoning": "Network timeout recovered",
                            "priority": 1
                        }],
                        "reasoning": "Successfully recovered from network timeout"
                    })
                }
            }]
        }
        
        mock_success_response = MagicMock()
        mock_success_response.status_code = 200
        mock_success_response.json.return_value = mock_success_response_data
        mock_success_response.raise_for_status = MagicMock()
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            # First call raises ReadTimeout, second call succeeds
            mock_client.post = AsyncMock(side_effect=[
                httpx.ReadTimeout("Request timed out"),
                mock_success_response
            ])
            
            mock_client_class.return_value = mock_client
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            
            result = await engine.make_decision({"test": "state"}, "retry_cycle")
            
            # Should handle the timeout and retry
            assert result.cycle_id == "retry_cycle"
            # Verify that two requests were made (original + retry)
            assert mock_client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_proactive_opportunity_handling(self):
        """Test handling of proactive opportunities as mentioned in the report."""
        engine = AIDecisionEngine(api_key="test_key")
        
        world_state_with_opportunities = {
            "proactive_opportunities": [
                {
                    "opportunity_id": "opp_123",
                    "opportunity_type": "quiet_channel",
                    "priority": 8,
                    "channel_id": "dev_channel",
                    "platform": "farcaster",
                    "reasoning": "Channel has been inactive for 3 hours, could benefit from engagement",
                    "context": {"last_activity": 1702990000},
                    "expires_at": 1703010000
                },
                {
                    "opportunity_id": "opp_124", 
                    "opportunity_type": "trending_topic",
                    "priority": 6,
                    "channel_id": "ai_discussion",
                    "platform": "matrix",
                    "reasoning": "AI discussions trending across multiple channels",
                    "context": {"topic": "transformer_architectures"},
                    "expires_at": 1703008000
                }
            ],
            "channels": {
                "dev_channel": {"name": "Development", "platform": "farcaster"},
                "ai_discussion": {"name": "AI Discussion", "platform": "matrix"}
            }
        }
        
        mock_response_data = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "observations": "High-priority proactive opportunity detected: quiet_channel in dev_channel. AI discussions trending in ai_discussion.",
                        "potential_actions": [
                            {"action_type": "search_casts", "reasoning": "Find relevant content for quiet channel"},
                            {"action_type": "send_farcaster_post", "reasoning": "Engage quiet channel"},
                            {"action_type": "expand_node", "reasoning": "Get more context on trending topic"}
                        ],
                        "selected_actions": [{
                            "action_type": "search_casts",
                            "parameters": {"query": "development tips", "channel": "dev_channel"},
                            "reasoning": "Addressing high-priority quiet channel opportunity",
                            "priority": 8
                        }],
                        "reasoning": "Prioritizing high-value proactive engagement opportunity"
                    })
                }
            }]
        }
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status = MagicMock()
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            
            result = await engine.make_decision(world_state_with_opportunities, "proactive_cycle")
            
            assert result.cycle_id == "proactive_cycle"
            assert "proactive opportunity" in result.observations.lower()
            assert len(result.selected_actions) == 1
            assert result.selected_actions[0].action_type == "search_casts"
            assert "quiet channel" in result.selected_actions[0].reasoning.lower()

    @pytest.mark.asyncio
    async def test_feedback_loop_prevention(self):
        """Test prevention of bot responding to its own messages (feedback loop from report)."""
        engine = AIDecisionEngine(api_key="test_key")
        
        world_state_with_self_reply = {
            "current_processing_channel_id": "test_channel",
            "channels": {
                "test_channel": {
                    "name": "Test Channel",
                    "messages": [
                        {"id": "$user_msg", "content": "Help me with this", "sender": "user123", "timestamp": 1703000000},
                        {"id": "$bot_reply", "content": "I'll help you analyze that", "sender": "ratichat", "timestamp": 1703000060},
                        {"id": "$bot_self_reply", "content": "Let me provide more details", "sender": "ratichat", "timestamp": 1703000120, "reply_to": "$bot_reply"}
                    ]
                }
            },
            "action_history": [
                {
                    "action_type": "send_matrix_message",
                    "parameters": {"message": "I'll help you analyze that", "event_id": "$user_msg"},
                    "timestamp": 1703000060
                },
                {
                    "action_type": "send_matrix_message", 
                    "parameters": {"message": "Let me provide more details", "event_id": "$bot_reply"},
                    "timestamp": 1703000120
                }
            ]
        }
        
        mock_response_data = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "observations": "Recent messages show I replied to my own message. This is a feedback loop pattern that should be avoided.",
                        "potential_actions": [
                            {"action_type": "send_matrix_message", "reasoning": "Would continue feedback loop - avoid"},
                            {"action_type": "wait", "reasoning": "Break feedback loop"},
                            {"action_type": "expand_node", "reasoning": "Gather more context before acting"}
                        ],
                        "selected_actions": [{
                            "action_type": "wait",
                            "parameters": {},
                            "reasoning": "Preventing feedback loop by not responding to my own messages",
                            "priority": 1
                        }],
                        "reasoning": "Detected feedback loop pattern - avoiding self-reply to prevent infinite conversation cycle"
                    })
                }
            }]
        }
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status = MagicMock()
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            
            result = await engine.make_decision(world_state_with_self_reply, "feedback_prevention_cycle")
            
            assert result.cycle_id == "feedback_prevention_cycle"
            assert "feedback loop" in result.observations.lower() or "self" in result.observations.lower()
            assert len(result.selected_actions) == 1
            assert result.selected_actions[0].action_type == "wait"
            assert "feedback loop" in result.reasoning.lower()

    @pytest.mark.asyncio
    async def test_state_staleness_detection(self):
        """Test detection of stale state where user_waiting_for_reply persists incorrectly."""
        engine = AIDecisionEngine(api_key="test_key")
        
        stale_world_state = {
            "current_processing_channel_id": "help_channel",
            "situation": "user_waiting_for_reply",  # This should transition after first reply
            "channels": {
                "help_channel": {
                    "name": "Help Channel",
                    "messages": [
                        {"id": "$user_request", "content": "Can you analyze my code?", "sender": "developer", "timestamp": 1703000000}
                    ]
                }
            },
            "action_history": [
                # Shows we already replied - state should have transitioned
                {
                    "action_type": "send_matrix_message",
                    "parameters": {"message": "I'll analyze your code for you", "event_id": "$user_request"},
                    "timestamp": 1703000030,
                    "result": "Message sent successfully"
                },
                {
                    "action_type": "get_codebase_structure",
                    "parameters": {"repository": "user_repo"},
                    "timestamp": 1703000090,
                    "result": "Codebase structure retrieved"
                }
            ]
        }
        
        mock_response_data = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "observations": "State appears stale: marked as 'user_waiting_for_reply' but action history shows I already replied and began analysis. Should transition to task execution mode.",
                        "potential_actions": [
                            {"action_type": "send_matrix_message", "reasoning": "Would be duplicate - already replied"},
                            {"action_type": "set_mission_goal", "reasoning": "Formalize the analysis task"},
                            {"action_type": "analyze_and_propose_change", "reasoning": "Continue with code analysis"}
                        ],
                        "selected_actions": [{
                            "action_type": "set_mission_goal",
                            "parameters": {
                                "objective": "Complete code analysis for developer",
                                "key_results": ["Code structure analyzed", "Issues identified", "Recommendations provided"],
                                "priority": 7
                            },
                            "reasoning": "Formalizing task to transition from stale 'waiting for reply' state to active mission",
                            "priority": 8
                        }],
                        "reasoning": "Detected stale state - transitioning from 'user_waiting_for_reply' to structured mission execution"
                    })
                }
            }]
        }
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status = MagicMock()
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            
            result = await engine.make_decision(stale_world_state, "state_transition_cycle")
            
            assert result.cycle_id == "state_transition_cycle"
            assert "stale" in result.observations.lower() or "transition" in result.observations.lower()
            assert len(result.selected_actions) == 1
            assert result.selected_actions[0].action_type == "set_mission_goal"
            assert "mission" in result.reasoning.lower() and "transition" in result.reasoning.lower()
