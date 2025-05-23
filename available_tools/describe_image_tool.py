import logging
import uuid
from typing import Dict, Any, List, Optional

from tool_base import AbstractTool, ToolResult
from event_definitions import OpenRouterInferenceRequestEvent

logger = logging.getLogger(__name__)


class DescribeImageTool(AbstractTool):
    """Tool to analyze and describe images in the conversation."""

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
    ) -> ToolResult:
        analysis_type = arguments.get("analysis_type", "general")
        specific_question = arguments.get("specific_question")

        recent_image_url: Optional[str] = None
        recent_image_event_id: Optional[str] = None

        for msg in reversed(conversation_history_snapshot):
            if msg.get("role") == "user" and "image_url" in str(msg.get("content", "")):
                content = msg.get("content")
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "image_url":
                            recent_image_url = item["image_url"].get("url")
                            recent_image_event_id = msg.get("event_id")
                            break
                if recent_image_url:
                    break

        if not recent_image_url:
            return ToolResult(
                status="failure",
                result_for_llm_history="[Tool describe_image failed: No recent image found in conversation to analyze.]",
                error_message="No recent image found in conversation history",
            )

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

        messages_payload = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": base_prompt},
                    {"type": "image_url", "image_url": {"url": recent_image_url}},
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
                "image_url": recent_image_url,
                "image_event_id": recent_image_event_id,
            },
            model_name="openai/gpt-4o",
            messages_payload=messages_payload,
            tools=None,
            tool_choice=None,
        )

        return ToolResult(
            status="requires_llm_followup",
            result_for_llm_history=f"[Analyzing image with {analysis_type} analysis...]",
            commands_to_publish=[vision_request],
        )
