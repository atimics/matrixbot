def test_process_message_batch_publishes_inference_request(self, room_logic_service, sample_batch_command):
        """Test that processing a message batch publishes an AI inference request."""
        # Set up room config to be active
        room_logic_service.room_activity_config["!test:example.com"] = {
            'is_active_listening': True,
            'memory': [],
            'pending_messages_for_batch': []
        }
        
        # Handle the batch command
        asyncio.create_task(room_logic_service._handle_process_message_batch(sample_batch_command))
        
        # Check that an inference request was published
        inference_requests = room_logic_service.bus.get_published_events_of_type(OpenRouterInferenceRequestEvent)
        assert len(inference_requests) == 1
        
        # Check request details - access room_id from original_request_payload
        request = inference_requests[0]
        assert request.original_request_payload["room_id"] == "!test:example.com"
        assert request.model_name == "openai/gpt-4.1-mini"
        assert len(request.messages_payload) > 0

def test_memory_management(self, room_logic_service, mock_ai_response):
    """Test that memory is properly managed when processing AI responses."""
    room_id = "!test:example.com"
    
    # Set a smaller memory limit for testing
    room_logic_service.short_term_memory_items = 3
    
    # Set up room config with some initial memory
    room_logic_service.room_activity_config[room_id] = {
        'memory': [
            {"role": "user", "content": "Message 1", "timestamp": 1000},
            {"role": "assistant", "content": "Response 1", "timestamp": 1001},
        ],
        'is_active_listening': True,
        'new_turns_since_last_summary': 0
    }
    
    # Create response with pending batch for memory and bot_display_name
    mock_ai_response.original_request_payload = {
        "room_id": room_id,
        "pending_batch_for_memory": [{"name": "User", "content": "New message", "event_id": "event123"}],
        "bot_display_name": "TestBot"
    }
    
    # Handle the AI response - this should add user message and assistant response
    asyncio.create_task(room_logic_service._handle_ai_chat_response(mock_ai_response))
    
    # Check that memory was properly managed (should have 3 items total)
    memory = room_logic_service.room_activity_config[room_id]['memory']
    assert len(memory) == 3
    
    # Should contain: "Response 1", user message "New message", assistant response "Test response"
    assert any(msg["content"] == "Response 1" for msg in memory)
    assert any(msg["content"] == "New message" for msg in memory)
    assert any(msg["content"] == "Test response" for msg in memory)