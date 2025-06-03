import logging
import time
from typing import Any, Dict, List
from urllib.parse import urlparse

import httpx

from ..config import (  # To access OPENROUTER_API_KEY and OPENROUTER_MULTIMODAL_MODEL
    settings,
)
from .base import ActionContext, ToolInterface

logger = logging.getLogger(__name__)


async def ensure_publicly_accessible_image_url(image_url: str, context: ActionContext) -> str:
    """
    Ensure the image URL is publicly accessible.
    For Matrix URLs, download via nio client and upload to S3.
    """
    if not image_url.startswith("https://chat.ratimics.com/_matrix/media/"):
        return image_url
    
    try:
        # Extract server and media_id from Matrix URL
        # https://chat.ratimics.com/_matrix/media/r0/download/chat.ratimics.com/fZEbZIjeCUtTYtFGJqnaxlru
        parts = image_url.split('/')
        if len(parts) >= 2:
            server = parts[-2]  # chat.ratimics.com
            media_id = parts[-1]  # fZEbZIjeCUtTYtFGJqnaxlru
            mxc_uri = f"mxc://{server}/{media_id}"
            
            logger.info(f"Converting Matrix URL to MXC: {mxc_uri}")
            
            # Use Matrix client to download the media
            if hasattr(context, 'matrix_observer') and context.matrix_observer:
                try:
                    # Check if client is authenticated
                    if not context.matrix_observer.client.access_token:
                        logger.warning(f"Matrix client not authenticated, cannot download {mxc_uri}")
                        raise Exception("Matrix client not authenticated")
                    
                    # Use nio client's built-in download method with MXC URI
                    download_response = await context.matrix_observer.client.download(mxc_uri)
                    
                    if download_response and hasattr(download_response, 'body'):
                        # Upload to S3
                        if hasattr(context, 's3_service') and context.s3_service:
                            s3_url = await context.s3_service.upload_image_data(
                                download_response.body,
                                f"matrix_media_{media_id}.jpg"
                            )
                            logger.info(f"Successfully uploaded Matrix media to S3: {s3_url}")
                            return s3_url
                        else:
                            logger.warning("No S3 service available")
                    else:
                        logger.error(f"Failed to download Matrix media: {mxc_uri}")
                        
                except Exception as e:
                    logger.error(f"Error downloading Matrix media via nio client: {e}")
            else:
                logger.warning("No Matrix observer available for media download")
                
    except Exception as e:
        logger.error(f"Error processing Matrix URL {image_url}: {e}")
    
    # If all else fails, return original URL
    logger.warning(f"Could not convert Matrix URL to S3, returning original: {image_url}")
    return image_url


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
            error_msg = (
                "Missing required parameter 'image_url' for describe_image tool."
            )
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        if not settings.OPENROUTER_API_KEY:
            error_msg = "OpenRouter API key not configured."
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Ensure the image URL is publicly accessible (convert Matrix URLs to S3)
        try:
            public_image_url = await ensure_publicly_accessible_image_url(image_url, context)
            logger.info(f"Using public image URL: {public_image_url}")
        except Exception as e:
            error_msg = f"Failed to access image: {e}"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        openrouter_model = (
            settings.OPENROUTER_MULTIMODAL_MODEL
        )  # Or settings.AI_MODEL if it's multimodal

        payload = {
            "model": openrouter_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt_text},
                        {
                            "type": "image_url",
                            "image_url": {"url": public_image_url},
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
            "HTTP-Referer": settings.YOUR_SITE_URL
            or "https://github.com/ratimics/chatbot",  # From config
            "X-Title": settings.YOUR_SITE_NAME or "Ratimics Chatbot",  # From config
        }

        try:
            async with httpx.AsyncClient(
                timeout=90.0
            ) as client:  # Increased timeout for image processing
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    json=payload,
                    headers=headers,
                )

            if response.status_code != 200:
                error_details = response.text
                logger.error(
                    f"DescribeImageTool: OpenRouter API HTTP {response.status_code} error: {error_details}"
                )
                return {
                    "status": "failure",
                    "error": f"OpenRouter API Error: {response.status_code} - {error_details[:200]}",
                    "timestamp": time.time(),
                }

            response.raise_for_status()  # Should be caught by the above if not 200, but good practice
            result_data = response.json()

            description = (
                result_data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )

            if not description:
                logger.warning(
                    f"DescribeImageTool: Received empty description for {image_url}"
                )
                return {
                    "status": "failure",
                    "error": "Received an empty description from the AI model.",
                    "image_url": image_url,
                    "timestamp": time.time(),
                }

            logger.info(f"DescribeImageTool: Successfully described image {image_url}")
            
            result = {
                "status": "success",
                "image_url": image_url,
                "public_image_url": public_image_url,
                "description": description,
                "prompt_used": prompt_text,
                "model_used": openrouter_model,
                "timestamp": time.time(),
            }
            
            # Record this action result in world state for AI visibility
            # Store the plain description as the result for action history
            context.world_state_manager.add_action_result(
                action_type="describe_image",
                parameters={"image_url": image_url, "prompt": prompt_text},
                result=description
            )
            
            return result

        except httpx.HTTPStatusError as e:
            logger.error(
                f"DescribeImageTool: HTTPStatusError while calling OpenRouter: {e.response.text}",
                exc_info=True,
            )
            return {
                "status": "failure",
                "error": f"OpenRouter API HTTPStatusError: {e.response.status_code} - {e.response.text[:200]}",
                "timestamp": time.time(),
            }
        except Exception as e:
            logger.error(
                f"DescribeImageTool: Error describing image {image_url}: {e}",
                exc_info=True,
            )
            return {
                "status": "failure",
                "error": str(e),
                "image_url": image_url,
                "timestamp": time.time(),
            }
