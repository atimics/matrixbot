import logging
import re
import time
from typing import Any, Dict, List
from urllib.parse import urlparse

import httpx

from ..config import (  # To access OPENROUTER_API_KEY and OPENROUTER_MULTIMODAL_MODEL
    settings,
)
from .base import ActionContext, ToolInterface

logger = logging.getLogger(__name__)


async def ensure_publicly_accessible_image_url(image_url: str, context: ActionContext) -> tuple[str, bool]:
    """
    Ensure the image URL is publicly accessible.
    For Matrix URLs, download via nio client and upload to Arweave.
    Returns tuple of (url, is_accessible)
    """
    import re
    
    # Check if this is a Matrix media URL using a generic pattern
    matrix_url_pattern = r"https://([^/]+)/_matrix/media/(?:r0|v3)/download/([^/]+)/(.+)"
    matrix_match = re.match(matrix_url_pattern, image_url)
    
    if not matrix_match:
        # For non-Matrix URLs, verify accessibility
        is_accessible = await _verify_image_accessibility(image_url)
        return image_url, is_accessible
    
    try:
        # Extract server and media_id from Matrix URL generically
        server_name = matrix_match.group(2)  # Server hosting the media
        media_id = matrix_match.group(3)     # Media ID
        mxc_uri = f"mxc://{server_name}/{media_id}"
        
        logger.info(f"Converting Matrix URL to MXC: {mxc_uri}")
        
        # Use Matrix client to download the media
        if hasattr(context, 'matrix_observer') and context.matrix_observer:
            try:
                # Check if client is authenticated
                if not context.matrix_observer.client.access_token:
                    logger.warning(f"Matrix client not authenticated, cannot download {mxc_uri}")
                    # Fall back to trying the original URL
                    is_accessible = await _verify_image_accessibility(image_url)
                    return image_url, is_accessible
                
                # Use nio client's built-in download method with MXC URI
                download_response = await context.matrix_observer.client.download(mxc_uri)
                
                if download_response and hasattr(download_response, 'body'):
                    # Upload to Arweave
                    if hasattr(context, 'arweave_service') and context.arweave_service:
                        arweave_url = await context.arweave_service.upload_image_data(
                            download_response.body,
                            f"matrix_media_{media_id}.jpg"
                        )
                        logger.info(f"Successfully uploaded Matrix media to Arweave: {arweave_url}")
                        return arweave_url, True
                    else:
                        logger.warning("No Arweave service available")
                        # Fall back to trying the original URL
                        is_accessible = await _verify_image_accessibility(image_url)
                        return image_url, is_accessible
                else:
                    logger.error(f"Failed to download Matrix media: {mxc_uri}")
                    # Fall back to trying the original URL
                    is_accessible = await _verify_image_accessibility(image_url)
                    return image_url, is_accessible
                    
            except Exception as e:
                logger.error(f"Error downloading Matrix media via nio client: {e}")
                # Fall back to trying the original URL
                is_accessible = await _verify_image_accessibility(image_url)
                return image_url, is_accessible
        else:
            logger.warning("No Matrix observer available for media download")
            # Fall back to trying the original URL
            is_accessible = await _verify_image_accessibility(image_url)
            return image_url, is_accessible
            
    except Exception as e:
        logger.error(f"Error processing Matrix URL {image_url}: {e}")
        # Fall back to trying the original URL
        is_accessible = await _verify_image_accessibility(image_url)
        return image_url, is_accessible


async def _verify_image_accessibility(image_url: str) -> bool:
    """
    Verify that an image URL is accessible by making a HEAD request.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.head(image_url)
            if response.status_code == 200:
                content_type = response.headers.get('content-type', '').lower()
                if content_type.startswith('image/'):
                    return True
                else:
                    logger.warning(f"URL {image_url} is accessible but not an image (content-type: {content_type})")
                    return False
            else:
                logger.warning(f"Image URL {image_url} returned status code: {response.status_code}")
                return False
    except Exception as e:
        logger.warning(f"Failed to verify image accessibility for {image_url}: {e}")
        return False


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
            "to generate an appropriate response or take further actions. "
            "IMPORTANT: When using this tool for images from messages, always use the URL from the message's "
            "image_urls array, NOT the content field which contains only the filename."
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

        # Ensure the image URL is publicly accessible (convert Matrix URLs to Arweave)
        try:
            public_image_url, is_accessible = await ensure_publicly_accessible_image_url(image_url, context)
            
            if not is_accessible:
                error_msg = f"Image is not accessible: {image_url}"
                logger.error(error_msg)
                return {"status": "failure", "error": error_msg, "timestamp": time.time()}
            
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
