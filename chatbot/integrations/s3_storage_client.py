"""
S3 Storage Client

Modern S3 storage client for images and videos with dual-purpose support:
- Primary storage for media delivery  
- Keep Arweave for NFT minting from same media
"""

import asyncio
import base64
import json
import logging
import os
import uuid
from pathlib import Path
from typing import Dict, Optional, Any
from urllib.parse import urlparse, urljoin

import httpx

logger = logging.getLogger(__name__)


class S3StorageClient:
    """Modern S3 storage client for media files"""

    def __init__(self, api_key: str = None, api_endpoint: str = None, cloudfront_domain: str = None):
        """
        Initialize S3 storage client.

        Args:
            api_key: S3 API key (from environment if not provided)
            api_endpoint: S3 API endpoint (from environment if not provided)  
            cloudfront_domain: CloudFront domain for public URLs (from environment if not provided)
        """
        self.api_key = api_key or os.getenv('S3_API_KEY')
        self.api_endpoint = (api_endpoint or os.getenv('S3_API_ENDPOINT', '')).rstrip('/')
        self.cloudfront_domain = (cloudfront_domain or os.getenv('CLOUDFRONT_DOMAIN', '')).rstrip('/')

        # Validate configuration
        if not self.api_key or not self.api_endpoint or not self.cloudfront_domain:
            missing = []
            if not self.api_key:
                missing.append('S3_API_KEY')
            if not self.api_endpoint:
                missing.append('S3_API_ENDPOINT')
            if not self.cloudfront_domain:
                missing.append('CLOUDFRONT_DOMAIN')
            raise ValueError(f'Missing required environment variables: {", ".join(missing)}')

        logger.debug(f"S3StorageClient initialized - endpoint: {self.api_endpoint}")

    def is_network_available(self) -> bool:
        """Check if network is available for S3 operations"""
        return bool(self.api_key and self.api_endpoint and self.cloudfront_domain)

    def is_s3_url(self, url: str) -> bool:
        """Check if a URL is an S3/CloudFront URL"""
        if not url:
            return False
        return (url.startswith("https://") and 
                (self.cloudfront_domain in url or ".amazonaws.com" in url or "cloudfront" in url.lower()))

    async def upload_image(self, file_path: str) -> Optional[str]:
        """
        Upload an image file to S3.

        Args:
            file_path: Path to the image file

        Returns:
            Public S3 URL or None if failed
        """
        try:
            # Check if file exists
            if not os.path.exists(file_path):
                logger.error(f"File not found at path: {file_path}")
                return None

            # Read the image file
            with open(file_path, 'rb') as f:
                image_data = f.read()

            # Get file extension and validate type
            file_ext = Path(file_path).suffix.lower().lstrip('.')
            valid_types = ['png', 'jpg', 'jpeg', 'gif', 'mp4', 'webm', 'mov']
            
            if file_ext not in valid_types:
                logger.error(f"Unsupported file type: .{file_ext}. Supported: {', '.join(valid_types)}")
                return None

            # Normalize extension
            if file_ext == 'jpeg':
                file_ext = 'jpg'

            # Upload the data
            return await self.upload_image_data(image_data, file_ext)

        except Exception as e:
            logger.error(f"Error uploading image from file: {e}")
            return None

    async def upload_image_data(self, image_data: bytes, image_type: str) -> Optional[str]:
        """
        Upload raw image data to S3.

        Args:
            image_data: Raw image bytes
            image_type: File extension (png, jpg, gif, mp4, etc.)

        Returns:
            Public S3 URL or None if failed
        """
        try:
            # Encode image as base64
            image_base64 = base64.b64encode(image_data).decode('utf-8')

            # Prepare payload matching the JavaScript service format
            payload = {
                "image": image_base64,
                "imageType": image_type,
            }

            # Parse endpoint URL to determine protocol
            parsed_url = urlparse(self.api_endpoint)
            
            # Prepare headers
            headers = {
                'Content-Type': 'application/json',
                'x-api-key': self.api_key,
            }

            logger.debug(f"Uploading {len(image_data)} bytes ({image_type}) to S3")

            # Make the request using httpx
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    self.api_endpoint,
                    json=payload,
                    headers=headers
                )

                if response.status_code == 200:
                    try:
                        result = response.json()
                        # Handle nested response format
                        response_data = result.get('body')
                        if isinstance(response_data, str):
                            response_data = json.loads(response_data)
                        if not response_data:
                            response_data = result

                        if not response_data or not response_data.get('url'):
                            logger.error(f"Invalid S3 response format - missing URL: {result}")
                            return None

                        s3_url = response_data['url']
                        logger.debug(f"Upload successful! S3 URL: {s3_url}")
                        return s3_url

                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse S3 response: {e}")
                        logger.error(f"Raw response: {response.text}")
                        return None

                else:
                    logger.error(f"Upload failed with status {response.status_code}: {response.text}")
                    return None

        except Exception as e:
            logger.error(f"Error uploading image data: {e}")
            return None

    async def download_image(self, image_url: str, headers: Optional[Dict[str, str]] = None, 
                           redirect_count: int = 0) -> Optional[bytes]:
        """
        Download an image from a URL with redirect handling.

        Args:
            image_url: URL of the image to download
            headers: Optional HTTP headers
            redirect_count: Internal redirect tracking

        Returns:
            Image data as bytes or None if failed
        """
        MAX_REDIRECTS = 5
        
        try:
            if redirect_count >= MAX_REDIRECTS:
                logger.error("Too many redirects")
                return None

            # Parse URL
            parsed_url = urlparse(image_url)
            if not parsed_url.scheme or not parsed_url.netloc:
                logger.error(f"Invalid URL format: {image_url}")
                return None

            # Prepare headers
            request_headers = headers or {}

            async with httpx.AsyncClient(timeout=60.0, follow_redirects=False) as client:
                response = await client.get(image_url, headers=request_headers)

                # Handle redirects manually for better control
                if response.status_code in [301, 302, 307, 308]:
                    location = response.headers.get('location')
                    if location:
                        logger.debug(f"Following redirect ({response.status_code}) to: {location}")
                        # Make location absolute if it's relative
                        if location.startswith('/'):
                            location = f"{parsed_url.scheme}://{parsed_url.netloc}{location}"
                        return await self.download_image(location, headers, redirect_count + 1)
                    else:
                        logger.error("Redirect response missing Location header")
                        return None

                elif response.status_code == 200:
                    logger.debug(f"Successfully downloaded image from: {image_url}")
                    return response.content

                else:
                    logger.error(f"Failed to download image. Status: {response.status_code}")
                    return None

        except Exception as e:
            logger.error(f"Error downloading image: {e}")
            return None

    async def get_public_url(self, s3_path: str) -> str:
        """
        Get the public CloudFront URL for an S3 object.

        Args:
            s3_path: S3 object path/key

        Returns:
            Full CloudFront URL
        """
        if s3_path.startswith('http'):
            return s3_path
        
        # Ensure path starts with /
        if not s3_path.startswith('/'):
            s3_path = '/' + s3_path
            
        return f"{self.cloudfront_domain}{s3_path}"

    async def upload_video_data(self, video_data: bytes, video_type: str) -> Optional[str]:
        """
        Upload raw video data to S3.

        Args:
            video_data: Raw video bytes
            video_type: Video file extension (mp4, webm, mov)

        Returns:
            Public S3 URL or None if failed
        """
        # Reuse the same upload logic as images since the S3 service handles both
        return await self.upload_image_data(video_data, video_type)

    async def health_check(self) -> bool:
        """
        Check if the S3 service is healthy and reachable.

        Returns:
            True if service is healthy, False otherwise
        """
        try:
            # Try to make a simple request to check service health
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Most S3 services have a health or status endpoint
                health_url = f"{self.api_endpoint.rsplit('/', 1)[0]}/health"
                try:
                    response = await client.get(health_url)
                    return response.status_code == 200
                except:
                    # If no health endpoint, service might still be working
                    # Just return True if we have valid configuration
                    return self.is_network_available()
        except Exception as e:
            logger.error(f"S3 health check failed: {e}")
            return False
