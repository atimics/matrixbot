import logging
import time
from typing import Any, Dict, List
from urllib.parse import urlparse

import httpx

from ..config import (  # To access OPENROUTER_API_KEY and OPENROUTER_MULTIMODAL_MODEL
    settings,
)
from ..tools.s3_service import s3_service
from .base import ActionContext, ToolInterface

logger = logging.getLogger(__name__)


async def ensure_publicly_accessible_image_url(image_url: str, context: ActionContext) -> str:
    """
    Ensure the image URL is publicly accessible. If it's a Matrix URL,
    download it and upload to S3 to make it accessible to external services.
    
    Args:
        image_url: The original image URL
        context: Action context containing Matrix client if needed
        
    Returns:
        A publicly accessible image URL
    """
    # Check if it's a Matrix URL that needs to be made public
    if "/_matrix/media/" in image_url or image_url.startswith("mxc://"):
        logger.info(f"Converting Matrix URL to public S3 URL: {image_url}")
        
        try:
            # First, try using the Matrix client's nio download method if available
            if context.matrix_observer and hasattr(context.matrix_observer, 'client'):
                matrix_client = context.matrix_observer.client
                if matrix_client:
                    try:
                        # For MXC URIs, use them directly with nio client
                        if image_url.startswith("mxc://"):
                            download_response = await matrix_client.download(image_url)
                        else:
                            # Extract MXC URI from HTTP URL if possible
                            # Example: https://chat.ratimics.com/_matrix/media/r0/download/chat.ratimics.com/CouMhkYwsXDOMYWPjqOSzRgk
                            # becomes: mxc://chat.ratimics.com/CouMhkYwsXDOMYWPjqOSzRgk
                            parts = image_url.split("/")
                            if len(parts) >= 2:
                                server_name = parts[-2]
                                media_id = parts[-1]
                                mxc_uri = f"mxc://{server_name}/{media_id}"
                                download_response = await matrix_client.download(mxc_uri)
                            else:
                                raise Exception("Cannot extract MXC URI from HTTP URL")
                        
                        if hasattr(download_response, "body") and download_response.body:
                            # Upload to S3
                            filename = "matrix_image.jpg"
                            if hasattr(download_response, "content_type"):
                                if "png" in download_response.content_type.lower():
                                    filename = "matrix_image.png"
                                elif "gif" in download_response.content_type.lower():
                                    filename = "matrix_image.gif"
                                elif "webp" in download_response.content_type.lower():
                                    filename = "matrix_image.webp"
                            
                            s3_url = await s3_service.upload_image_data(download_response.body, filename)
                            if s3_url:
                                logger.info(f"Successfully uploaded Matrix image to S3 via nio client: {s3_url}")
                                return s3_url
                        else:
                            logger.warning(f"Matrix nio client download failed for {image_url}")
                    except Exception as nio_error:
                        logger.warning(f"Matrix nio client download failed: {nio_error}")
                        # Fall through to HTTP method
            
            # Fallback: try HTTP download with authentication
            async with httpx.AsyncClient(timeout=30.0) as client:
                headers = {}
                if context.matrix_observer and hasattr(context.matrix_observer, 'client'):
                    matrix_client = context.matrix_observer.client
                    if matrix_client and matrix_client.access_token:
                        if image_url.startswith("mxc://"):
                            # Convert MXC to HTTP URL first
                            http_url = await matrix_client.mxc_to_http(image_url)
                            if http_url:
                                image_url = http_url
                        
                        # Add Matrix auth header
                        headers["Authorization"] = f"Bearer {matrix_client.access_token}"
                
                response = await client.get(image_url, headers=headers)
                response.raise_for_status()
                
                # Extract filename from URL or use default
                parsed_url = urlparse(image_url)
                filename = parsed_url.path.split('/')[-1] or "matrix_image.jpg"
                if not filename.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
                    filename += ".jpg"
                
                # Upload to S3
                s3_url = await s3_service.upload_image_data(response.content, filename)
                if s3_url:
                    logger.info(f"Successfully uploaded Matrix image to S3 via HTTP: {s3_url}")
                    return s3_url
                else:
                    logger.warning(f"Failed to upload Matrix image to S3, cannot process image")
                    raise Exception("Image not accessible - Matrix URL returned 404 and S3 upload failed")
                    
        except Exception as e:
            logger.error(f"Error converting Matrix URL to S3: {e}")
            # Instead of returning the inaccessible URL, raise an exception
            raise Exception(f"Cannot access Matrix image: {e}")
    
    # For non-Matrix URLs, return as-is
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
            # Include metadata in the result string for the action history
            result_with_metadata = f"Image description: {description} [Model: {openrouter_model}, URL: {image_url}]"
            context.world_state_manager.add_action_result(
                action_type="describe_image",
                parameters={"image_url": image_url, "prompt": prompt_text, "model_used": openrouter_model},
                result=result_with_metadata
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
