import logging
import uuid
import tempfile
import os
from typing import Dict, Any, List, Optional

from tool_base import AbstractTool, ToolResult
from event_definitions import OpenRouterInferenceRequestEvent
from s3_service import S3Service
from matrix_media_utils import MatrixMediaUtils  # Added for centralized media conversion

logger = logging.getLogger(__name__)


class DescribeImageTool(AbstractTool):
    """Tool to analyze and describe images in the conversation."""

    def __init__(self):
        self.s3_service = S3Service()

    def get_definition(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "describe_image",
                "description": (
                    "Analyze and describe an image that was recently shared in the conversation. "
                    "Can provide detailed analysis of visual content, objects, text, or specific aspects."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "analysis_type": {
                            "type": "string",
                            "enum": [
                                "general",
                                "detailed",
                                "objects",
                                "text_extraction",
                                "artistic_analysis",
                            ],
                            "description": "Type of analysis to perform on the image",
                        },
                        "specific_question": {
                            "type": "string",
                            "description": (
                                "Optional specific question about the image "
                                "(e.g., 'What color is the car?', 'How many people are in this photo?')"
                            ),
                        },
                    },
                    "required": ["analysis_type"],
                },
            },
        }

    def _convert_mxc_to_http(self, mxc_url: str) -> str:
        """Convert Matrix MXC URL to HTTP URL for downloading."""
        # Use centralized utility for simple conversion
        return MatrixMediaUtils.convert_mxc_to_http_simple(mxc_url)

    async def execute(
        self,
        room_id: str,
        arguments: Dict[str, Any],
        tool_call_id: Optional[str],
        llm_provider_info: Dict[str, Any],
        conversation_history_snapshot: List[Dict[str, Any]],
        last_user_event_id: Optional[str],
        db_path: Optional[str] = None,
        original_request_payload: Optional[Dict[str, Any]] = None,
        matrix_client = None  # Added for nio client download
    ) -> ToolResult:
        analysis_type = arguments.get("analysis_type", "general")
        specific_question = arguments.get("specific_question")

        # Look for recent images in conversation history
        recent_image_url: Optional[str] = None
        recent_image_event_id: Optional[str] = None

        # First, check for images in the standard format (from conversation history)
        for msg in reversed(conversation_history_snapshot):
            # Handle both dict and HistoricalMessage object formats
            if isinstance(msg, dict):
                msg_role = msg.get("role")
                msg_content = msg.get("content")
                msg_event_id = msg.get("event_id")
            else:
                # HistoricalMessage object - access attributes directly
                msg_role = getattr(msg, 'role', None)
                msg_content = getattr(msg, 'content', None)
                msg_event_id = getattr(msg, 'event_id', None)
            
            if msg_role == "user":
                # Check for image_url in structured content
                if isinstance(msg_content, list):
                    for item in msg_content:
                        if isinstance(item, dict) and item.get("type") == "image_url":
                            recent_image_url = item["image_url"].get("url")
                            recent_image_event_id = msg_event_id
                            break
                
                # Check for image_url in message metadata (from Matrix image events)
                elif isinstance(msg, dict) and "image_url" in msg:
                    recent_image_url = msg["image_url"]
                    recent_image_event_id = msg_event_id
                    break
                elif hasattr(msg, 'image_url'):
                    recent_image_url = getattr(msg, 'image_url', None)
                    recent_image_event_id = msg_event_id
                    break
                
                if recent_image_url:
                    break

        if not recent_image_url:
            return ToolResult(
                status="failure",
                result_for_llm_history="[Tool describe_image failed: No recent image found in conversation to analyze.]",
                error_message="No recent image found in conversation history",
            )

        logger.info(f"DescribeImageTool: Found image URL: {recent_image_url}")

        try:
            image_data = None
            
            # If it's an MXC URL, use the simple nio client download method first
            if recent_image_url.startswith("mxc://"):
                if matrix_client:
                    try:
                        logger.info(f"DescribeImageTool: Using nio client download method for: {recent_image_url}")
                        image_data = await MatrixMediaUtils.download_media_simple(recent_image_url, matrix_client)
                        if image_data:
                            logger.info(f"DescribeImageTool: Successfully downloaded image using nio client. Size: {len(image_data)} bytes")
                        else:
                            logger.warning(f"DescribeImageTool: Nio client download returned no data for: {recent_image_url}")
                    except Exception as e:
                        logger.warning(f"DescribeImageTool: Nio client download failed: {e}")
                
                # Fallback to HTTP conversion approach if nio client fails or is unavailable
                if not image_data:
                    logger.info("DescribeImageTool: Falling back to HTTP conversion approach")
                    # Extract server and media_id from mxc://server/media_id format
                    parts = recent_image_url[6:].split("/", 1)  # Remove "mxc://" and split
                    if len(parts) != 2:
                        logger.error(f"DescribeImageTool: Invalid MXC URL format: {recent_image_url}")
                        return ToolResult(
                            status="failure",
                            result_for_llm_history="[Tool describe_image failed: Invalid image URL format.]",
                            error_message="Invalid MXC URL format",
                        )
                    
                    server, media_id = parts
                    
                    # Try multiple Matrix media API versions as fallbacks
                    api_versions = ["v3", "v1", "r0"]
                    
                    for version in api_versions:
                        matrix_http_url = f"https://{server}/_matrix/media/{version}/download/{server}/{media_id}"
                        logger.info(f"DescribeImageTool: Trying to download image using {version} API: {matrix_http_url}")
                        
                        image_data = await self.s3_service.download_image(matrix_http_url)
                        if image_data:
                            logger.info(f"DescribeImageTool: Successfully downloaded image using Matrix media API {version}")
                            break
                        else:
                            logger.warning(f"DescribeImageTool: Failed to download image using Matrix media API {version}")
            else:
                # Non-MXC URL, try direct download
                image_data = await self.s3_service.download_image(recent_image_url)
            
            if not image_data:
                return ToolResult(
                    status="failure",
                    result_for_llm_history="[Tool describe_image failed: Could not download the image from any source.]",
                    error_message="Failed to download image from all attempted methods",
                )

            # Save image to temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as temp_file:
                temp_file.write(image_data)
                temp_file_path = temp_file.name

            try:
                # Upload image to S3
                logger.info(f"DescribeImageTool: Uploading image to S3")
                s3_url = await self.s3_service.upload_image(temp_file_path)
                if not s3_url:
                    return ToolResult(
                        status="failure",
                        result_for_llm_history="[Tool describe_image failed: Could not upload image to S3 for analysis.]",
                        error_message="Failed to upload image to S3",
                    )

                logger.info(f"DescribeImageTool: Image uploaded to S3: {s3_url}")

                # Prepare analysis prompt
                analysis_prompts = {
                    "general": "Provide a general description of this image, including the main subjects, setting, and overall composition.",
                    "detailed": (
                        "Provide a very detailed analysis of this image, including objects, people, colors, lighting, composition, and any text visible."
                    ),
                    "objects": "List and describe all the objects visible in this image, including their positions and characteristics.",
                    "text_extraction": "Extract and transcribe any text visible in this image, including signs, labels, documents, or writing.",
                    "artistic_analysis": "Analyze this image from an artistic perspective, including composition, color theory, style, and artistic techniques used.",
                }

                base_prompt = analysis_prompts.get(analysis_type, analysis_prompts["general"])
                if specific_question:
                    base_prompt += f" Additionally, please answer this specific question: {specific_question}"

                # Create vision request with S3 URL
                messages_payload = [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": base_prompt},
                            {"type": "image_url", "image_url": {"url": s3_url}},
                        ],
                    }
                ]

                request_id = str(uuid.uuid4())
                vision_request = OpenRouterInferenceRequestEvent(
                    request_id=request_id,
                    reply_to_service_event="image_analysis_response",
                    original_request_payload={
                        "room_id": room_id,
                        "tool_call_id": tool_call_id,
                        "analysis_type": analysis_type,
                        "image_url": s3_url,  # Use S3 URL instead of Matrix URL
                        "image_event_id": recent_image_event_id,
                        "original_matrix_url": recent_image_url,  # Keep reference to original
                    },
                    model_name="openai/gpt-4o",
                    messages_payload=messages_payload,
                    tools=None,
                    tool_choice=None,
                )

                return ToolResult(
                    status="requires_llm_followup",
                    result_for_llm_history=f"[Analyzing image with {analysis_type} analysis using uploaded S3 image...]",
                    commands_to_publish=[vision_request],
                )

            finally:
                # Clean up temporary file
                try:
                    os.unlink(temp_file_path)
                except OSError:
                    logger.warning(f"DescribeImageTool: Could not delete temporary file: {temp_file_path}")

        except Exception as e:
            logger.error(f"DescribeImageTool: Error processing image: {e}", exc_info=True)
            return ToolResult(
                status="failure",
                result_for_llm_history=f"[Tool describe_image failed: Error processing image - {str(e)}]",
                error_message=f"Error processing image: {str(e)}",
            )
