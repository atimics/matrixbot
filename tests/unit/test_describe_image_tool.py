import pytest
from unittest.mock import patch, AsyncMock
from available_tools.describe_image_tool import DescribeImageTool
from event_definitions import OpenRouterInferenceRequestEvent

@pytest.fixture
def describe_image_tool():
    # Mock the S3 environment variables and S3Service methods
    with patch.dict('os.environ', {
        'S3_API_KEY': 'fake_s3_key',
        'S3_API_ENDPOINT': 'https://fake-s3-endpoint.com',
        'CLOUDFRONT_DOMAIN': 'https://fake-cloudfront.com'
    }), patch('available_tools.describe_image_tool.S3Service') as mock_s3_class:
        # Create mock S3Service instance
        mock_s3_instance = AsyncMock()
        mock_s3_instance.download_image.return_value = b'fake_image_data'
        mock_s3_instance.upload_image.return_value = 'https://fake-cloudfront.com/fake-image.jpg'
        mock_s3_class.return_value = mock_s3_instance
        
        tool = DescribeImageTool()
        tool.s3_service = mock_s3_instance  # Ensure the tool uses our mock
        return tool


def test_tool_definition(describe_image_tool):
    definition = describe_image_tool.get_definition()
    assert definition["function"]["name"] == "describe_image"
    assert "analysis_type" in definition["function"]["parameters"]["properties"]


@pytest.mark.asyncio
async def test_execute_with_recent_image(describe_image_tool):
    conversation_history = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "What do you see?"},
                {"type": "image_url", "image_url": {"url": "mxc://server/image123"}},
            ],
            "event_id": "$image_event",
        }
    ]

    result = await describe_image_tool.execute(
        room_id="!room:server",
        arguments={"analysis_type": "detailed"},
        tool_call_id="tool_call_1",
        llm_provider_info={},
        conversation_history_snapshot=conversation_history,
        last_user_event_id=None,
    )

    assert result.status == "requires_llm_followup"
    assert result.commands_to_publish is not None
    assert len(result.commands_to_publish) == 1
    assert isinstance(result.commands_to_publish[0], OpenRouterInferenceRequestEvent)
