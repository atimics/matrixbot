"""
Test media action tracking and result recording.
"""
import pytest
import time
from unittest.mock import Mock, AsyncMock, patch
from chatbot.core.world_state import WorldState, WorldStateManager, ActionHistory
from chatbot.tools.media_generation_tools import GenerateImageTool
from chatbot.tools.describe_image_tool import DescribeImageTool
from chatbot.core.orchestrator import ActionContext


class TestMediaActionTracking:
    """Test that media actions are properly tracked and recorded"""

    def test_world_state_recent_media_actions(self):
        """Test the recent media actions tracking"""
        ws = WorldState()
        
        # Add some media actions to history
        current_time = time.time()
        
        # Add a describe_image action
        describe_action = ActionHistory(
            action_type="describe_image",
            parameters={"image_url": "http://example.com/test.jpg", "prompt": "What's this?"},
            result="A test image",
            timestamp=current_time - 100,
            metadata={"image_url": "http://example.com/test.jpg"}
        )
        ws.action_history.append(describe_action)
        
        # Add a generate_image action
        generate_action = ActionHistory(
            action_type="generate_image", 
            parameters={"prompt": "A red car"},
            result="http://s3.amazonaws.com/generated_car.jpg",
            timestamp=current_time - 50,
            metadata={"image_url": "http://s3.amazonaws.com/generated_car.jpg"}
        )
        ws.action_history.append(generate_action)
        
        # Get recent media actions
        media_actions = ws.get_recent_media_actions(lookback_seconds=200)
        
        assert len(media_actions["recent_media_actions"]) == 2
        assert "http://example.com/test.jpg" in media_actions["images_recently_described"]
        assert len(media_actions["recent_generations"]) == 1
        assert media_actions["summary"]["total_recent_media_actions"] == 2

    def test_to_dict_for_ai_includes_media_actions(self):
        """Test that to_dict_for_ai includes recent media actions"""
        ws = WorldState()
        
        # Add a media action
        action = ActionHistory(
            action_type="describe_image",
            parameters={"image_url": "http://test.com/image.jpg"},
            result="Test description",
            timestamp=time.time() - 60
        )
        ws.action_history.append(action)
        
        ai_dict = ws.to_dict_for_ai()
        
        assert "recent_media_actions" in ai_dict
        assert "recent_media_actions" in ai_dict["recent_media_actions"]
        assert "images_recently_described" in ai_dict["recent_media_actions"]
        assert "summary" in ai_dict["recent_media_actions"]

    @pytest.mark.asyncio
    async def test_generate_image_tool_records_action(self):
        """Test that GenerateImageTool records its results properly"""
        tool = GenerateImageTool()
        
        # Mock the context and world state manager
        mock_context = Mock()
        mock_world_state_manager = Mock()
        mock_arweave_service = Mock()
        
        mock_context.world_state_manager = mock_world_state_manager
        mock_context.arweave_service = mock_arweave_service
        
        # Mock successful Arweave upload
        mock_arweave_service.upload_image_data = AsyncMock(return_value="https://arweave.net/test_image_id")
        
        # Mock settings
        with patch('chatbot.tools.media_generation_tools.settings') as mock_settings:
            mock_settings.GOOGLE_API_KEY = "test_key"
            mock_settings.USE_GOOGLE_FOR_IMAGE_GENERATION = True
            
            # Mock Google client
            with patch('chatbot.tools.media_generation_tools.GoogleAIMediaClient') as mock_google_class:
                mock_google_client = AsyncMock()
                mock_google_client.generate_image_gemini = AsyncMock(return_value=b"fake_image_data")
                mock_google_class.return_value = mock_google_client
                
                # Execute the tool
                result = await tool.execute(
                    {"prompt": "A test robot"}, 
                    mock_context
                )
                
                # Verify the tool was successful
                assert result["status"] == "success"
                assert "s3_image_url" in result
                
                # Verify that add_action_result was called
                mock_world_state_manager.add_action_result.assert_called_once()
                call_args = mock_world_state_manager.add_action_result.call_args
                
                assert call_args[1]["action_type"] == "generate_image"
                assert call_args[1]["parameters"]["prompt"] == "A test robot"
                assert call_args[1]["result"] == "http://s3.example.com/test.jpg"

    @pytest.mark.asyncio
    async def test_describe_image_tool_records_action(self):
        """Test that DescribeImageTool records its results properly"""
        tool = DescribeImageTool()
        
        # Mock the context and world state manager
        mock_context = Mock()
        mock_world_state_manager = Mock()
        mock_context.world_state_manager = mock_world_state_manager
        
        # Mock settings
        with patch('chatbot.tools.describe_image_tool.settings') as mock_settings:
            mock_settings.OPENROUTER_API_KEY = "test_key"
            mock_settings.OPENROUTER_MULTIMODAL_MODEL = "test_model"
            mock_settings.YOUR_SITE_URL = "http://test.com"
            mock_settings.YOUR_SITE_NAME = "Test"
            
            # Mock httpx response
            with patch('chatbot.tools.describe_image_tool.httpx.AsyncClient') as mock_client_class:
                mock_client = AsyncMock()
                
                # Mock HEAD response for image accessibility check
                mock_head_response = Mock()
                mock_head_response.status_code = 200
                mock_head_response.headers = {'content-type': 'image/jpeg'}
                mock_client.head = AsyncMock(return_value=mock_head_response)
                
                # Mock POST response for OpenRouter API
                mock_post_response = Mock()
                mock_post_response.status_code = 200
                mock_post_response.json.return_value = {
                    "choices": [{"message": {"content": "A test image description"}}]
                }
                mock_client.post = AsyncMock(return_value=mock_post_response)
                mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)
                
                # Execute the tool
                result = await tool.execute(
                    {"image_url": "http://example.com/test.jpg", "prompt_text": "What's this?"}, 
                    mock_context
                )
                
                # Verify the tool was successful
                assert result["status"] == "success"
                assert "description" in result
                
                # Verify that add_action_result was called
                mock_world_state_manager.add_action_result.assert_called_once()
                call_args = mock_world_state_manager.add_action_result.call_args
                
                assert call_args[1]["action_type"] == "describe_image"
                assert call_args[1]["parameters"]["image_url"] == "http://example.com/test.jpg"
                assert call_args[1]["result"] == "A test image description"

    @pytest.mark.asyncio
    async def test_describe_image_tool_handles_inaccessible_image(self):
        """Test that DescribeImageTool fails gracefully when image is not accessible"""
        tool = DescribeImageTool()
        
        # Mock the context and world state manager
        mock_context = Mock()
        mock_world_state_manager = Mock()
        mock_context.world_state_manager = mock_world_state_manager
        
        # Mock settings
        with patch('chatbot.tools.describe_image_tool.settings') as mock_settings:
            mock_settings.OPENROUTER_API_KEY = "test_key"
            mock_settings.OPENROUTER_MULTIMODAL_MODEL = "test_model"
            mock_settings.YOUR_SITE_URL = "http://test.com"
            mock_settings.YOUR_SITE_NAME = "Test"
            
            # Mock httpx response with inaccessible image (404 error)
            with patch('chatbot.tools.describe_image_tool.httpx.AsyncClient') as mock_client_class:
                mock_client = AsyncMock()
                
                # Mock HEAD response for image accessibility check (404 error)
                mock_head_response = Mock()
                mock_head_response.status_code = 404
                mock_client.head = AsyncMock(return_value=mock_head_response)
                
                mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)
                
                # Execute the tool
                result = await tool.execute(
                    {"image_url": "http://example.com/nonexistent.jpg", "prompt_text": "What's this?"}, 
                    mock_context
                )
                
                # Verify the tool failed gracefully
                assert result["status"] == "failure"
                assert "not accessible" in result["error"]
                
                # Verify that add_action_result was NOT called since the image wasn't accessible
                mock_world_state_manager.add_action_result.assert_not_called()
