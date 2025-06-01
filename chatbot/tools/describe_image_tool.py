import logging
import time
import httpx
from typing import Any, Dict, List

from .base import ActionContext, ToolInterface
from ..config import settings  # To access OPENROUTER_API_KEY and OPENROUTER_MULTIMODAL_MODEL

logger = logging.getLogger(__name__)

class DescribeImageTool(ToolInterface):
    """
    Tool for analyzing an image from a URL and providing a textual description
    using a multimodal AI model via OpenRouter.
    """

    @property
    def name(self) -> str:
        return "describe_image"

    @property
    def description(self) -> str:
        return (
            "Analyzes an image from a given URL and provides a textual description of its content. "
            "Use this tool when a message includes an image_url and you need to understand what the image depicts "
            "to generate an appropriate response or take further actions."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "image_url": "string - The public URL of the image to be described.",
            "prompt_text": "string (optional) - Specific question or prompt for analyzing the image (e.g., 'What color is the car?', 'Is there a cat in this image?'). Defaults to 'Describe this image in detail.'",
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        logger.info(f"Executing tool '{self.name}' with params: {params}")

        image_url = params.get("image_url")
        prompt_text = params.get("prompt_text", "Describe this image in detail.")

        if not image_url:
            error_msg = "Missing required parameter 'image_url' for describe_image tool."
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        if not settings.OPENROUTER_API_KEY:
            error_msg = "OpenRouter API key not configured."
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}
        
        openrouter_model = settings.OPENROUTER_MULTIMODAL_MODEL  # Or settings.AI_MODEL if it's multimodal

        payload = {
            "model": openrouter_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt_text},
                        {
                            "type": "image_url",
                            "image_url": {"url": image_url},
                        },
                    ],
                }
            ],
            "max_tokens": 1024,  # Adjust as needed
            "temperature": 0.7,
        }

        headers = {
            "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": settings.YOUR_SITE_URL or "https://github.com/ratimics/chatbot",  # From config
            "X-Title": settings.YOUR_SITE_NAME or "Ratimics Chatbot",  # From config
        }

        try:
            async with httpx.AsyncClient(timeout=90.0) as client:  # Increased timeout for image processing
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    json=payload,
                    headers=headers,
                )
            
            if response.status_code != 200:
                error_details = response.text
                logger.error(f"DescribeImageTool: OpenRouter API HTTP {response.status_code} error: {error_details}")
                return {
                    "status": "failure",
                    "error": f"OpenRouter API Error: {response.status_code} - {error_details[:200]}",
                    "timestamp": time.time(),
                }

            response.raise_for_status()  # Should be caught by the above if not 200, but good practice
            result_data = response.json()
            
            description = result_data.get("choices", [{}])[0].get("message", {}).get("content", "")

            if not description:
                logger.warning(f"DescribeImageTool: Received empty description for {image_url}")
                return {
                    "status": "failure",
                    "error": "Received an empty description from the AI model.",
                    "image_url": image_url,
                    "timestamp": time.time(),
                }

            logger.info(f"DescribeImageTool: Successfully described image {image_url}")
            return {
                "status": "success",
                "image_url": image_url,
                "description": description,
                "prompt_used": prompt_text,
                "model_used": openrouter_model,
                "timestamp": time.time(),
            }

        except httpx.HTTPStatusError as e:
            logger.error(f"DescribeImageTool: HTTPStatusError while calling OpenRouter: {e.response.text}", exc_info=True)
            return {
                "status": "failure",
                "error": f"OpenRouter API HTTPStatusError: {e.response.status_code} - {e.response.text[:200]}",
                "timestamp": time.time(),
            }
        except Exception as e:
            logger.error(f"DescribeImageTool: Error describing image {image_url}: {e}", exc_info=True)
            return {
                "status": "failure",
                "error": str(e),
                "image_url": image_url,
                "timestamp": time.time(),
            }
