"""
S3 Client

This module provides integration with S3-compatible storage for permanent media storage.
Communicates with the S3 API service.
"""

import json
import logging
from typing import Dict, Optional

import httpx

logger = logging.getLogger(__name__)


class S3Client:
    """Client for uploading data to S3 via S3 API service."""

    def __init__(
        self, 
        s3_api_endpoint: str,
        s3_api_key: str,
        cloudfront_domain: str
    ):
        """
        Initialize S3 client.
        
        Args:
            s3_api_endpoint: S3 API endpoint URL
            s3_api_key: API key for S3 service
            cloudfront_domain: CloudFront domain for serving URLs
        """
        self.s3_api_endpoint = s3_api_endpoint.rstrip('/')
        self.s3_api_key = s3_api_key
        self.cloudfront_domain = cloudfront_domain.rstrip('/')

    def _get_headers(self) -> Dict[str, str]:
        """Get headers for requests including API key."""
        return {
            'x-api-key': self.s3_api_key,
            'Content-Type': 'application/json'
        }

    async def upload_data(
        self,
        data: bytes,
        content_type: str,
        tags: Optional[Dict[str, str]] = None,
    ) -> Optional[str]:
        """
        Upload data to S3 via the API service.

        Args:
            data: Raw data bytes to upload  
            content_type: MIME type of the data
            tags: Optional dictionary of metadata tags (not used in current S3 API but kept for compatibility)

        Returns:
            S3 URL or None if failed
        """
        try:
            # Encode data as base64
            import base64
            image_base64 = base64.b64encode(data).decode('utf-8')
            
            # Get file extension from content type
            image_type = self._get_file_extension(content_type)

            # Prepare the request payload
            payload = {
                "image": image_base64,
                "imageType": image_type,
            }

            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    self.s3_api_endpoint,
                    json=payload,
                    headers=self._get_headers(),
                )

                response.raise_for_status()
                result = response.json()

                # Parse response - handle both direct response and nested body
                response_data = result.body if isinstance(result.get('body'), dict) else result
                if isinstance(result.get('body'), str):
                    try:
                        response_data = json.loads(result['body'])
                    except json.JSONDecodeError:
                        response_data = result

                # Extract URL from response
                s3_url = response_data.get("url")

                if s3_url:
                    logger.info(f"S3Client: Successfully uploaded data to S3: {s3_url}")
                    return s3_url
                else:
                    logger.error(f"S3Client: Upload succeeded but no URL in response: {result}")
                    return None

        except httpx.HTTPStatusError as e:
            logger.error(f"S3Client: HTTP error during upload: {e.response.status_code} - {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"S3Client: Upload failed: {e}")
            return None

    def _get_file_extension(self, content_type: str) -> str:
        """Get file extension from content type."""
        mime_to_ext = {
            'image/png': 'png',
            'image/jpeg': 'jpg',
            'image/jpg': 'jpg',
            'image/gif': 'gif',
            'image/webp': 'webp',
            'video/mp4': 'mp4',
            'video/webm': 'webm',
            'video/quicktime': 'mov',
        }
        return mime_to_ext.get(content_type, 'png')

    def get_s3_url(self, url: str) -> str:
        """
        Return the S3 URL as-is (compatibility method).

        Args:
            url: S3 URL

        Returns:
            The same S3 URL
        """
        return url

    async def download_image(self, image_url: str, headers: Optional[Dict] = None, redirect_count: int = 0) -> bytes:
        """
        Download image data from an S3 URL.
        
        Args:
            image_url: S3 URL
            headers: Optional headers for the request
            redirect_count: Current redirect count (for recursion)
            
        Returns:
            Image data bytes
        """
        MAX_REDIRECTS = 5
        try:
            from urllib.parse import urlparse
            parsed_url = urlparse(image_url)
            
            # Use httpx for the request
            async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
                response = await client.get(image_url, headers=headers or {})
                
                # Handle redirects manually if needed
                if response.status_code in [301, 302, 307, 308] and redirect_count < MAX_REDIRECTS:
                    location = response.headers.get('location')
                    if location:
                        logger.warning(f"S3Client: Redirect ({response.status_code}) to: {location}")
                        return await self.download_image(location, headers, redirect_count + 1)
                    else:
                        raise Exception("Redirect without location header")
                
                response.raise_for_status()
                logger.info(f"S3Client: Image downloaded successfully from {image_url}")
                return response.content

        except Exception as e:
            logger.error(f"S3Client: Error downloading image from {image_url}: {e}")
            raise
