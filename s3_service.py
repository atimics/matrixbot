import asyncio
import logging
import os
import json
from typing import Optional, Dict, Any
from urllib.parse import urlparse
import httpx
import base64
from pathlib import Path

logger = logging.getLogger(__name__)

class S3Service:
    def __init__(self):
        self.logger = logger

        # Load environment variables
        self.S3_API_KEY = os.getenv('S3_API_KEY')
        self.S3_API_ENDPOINT = os.getenv('S3_API_ENDPOINT')
        self.CLOUDFRONT_DOMAIN = os.getenv('CLOUDFRONT_DOMAIN')

        # Validate environment variables
        if not self.S3_API_KEY or not self.S3_API_ENDPOINT or not self.CLOUDFRONT_DOMAIN:
            raise ValueError('Missing one or more required environment variables (S3_API_KEY, S3_API_ENDPOINT, CLOUDFRONT_DOMAIN)')

    async def upload_image(self, file_path: str, object_name: Optional[str] = None) -> Optional[str]:
        """
        Upload an image file to S3 and return the CloudFront URL.
        
        Args:
            file_path: Path to the image file to upload
            object_name: Optional custom name for the uploaded object (currently unused but kept for compatibility)
            
        Returns:
            CloudFront URL of the uploaded image, or None if upload failed
        """
        try:
            # Check if file exists
            if not Path(file_path).exists():
                self.logger.error(f"Error: File not found at path '{file_path}'")
                return None

            # Read the image file
            with open(file_path, 'rb') as f:
                image_buffer = f.read()
            
            image_base64 = base64.b64encode(image_buffer).decode('utf-8')
            image_type = Path(file_path).suffix.lstrip('.').lower()  # e.g., 'png', 'jpg'

            # Validate image type
            valid_image_types = ['png', 'jpg', 'jpeg', 'gif', 'mp4']
            if image_type not in valid_image_types:
                self.logger.error(f"Error: Unsupported image type '.{image_type}'. Supported types: {', '.join(valid_image_types)}")
                return None

            # Prepare the request payload
            payload = {
                'image': image_base64,
                'imageType': image_type,
            }

            headers = {
                'Content-Type': 'application/json',
                'x-api-key': self.S3_API_KEY,
            }

            # Send POST request to upload the image
            async with httpx.AsyncClient() as client:
                response = await client.post(self.S3_API_ENDPOINT, json=payload, headers=headers)
                
                if response.status_code == 200:
                    try:
                        result = response.json()
                        response_data = json.loads(result['body']) if 'body' in result else result
                        
                        if not response_data or 'url' not in response_data:
                            self.logger.error(f"Invalid S3 response format - missing URL. Response data: {json.dumps(result)}")
                            return None
                        
                        self.logger.info('Upload Successful!')
                        self.logger.info(f"Image URL: {response_data['url']}")
                        return response_data['url']
                    except (json.JSONDecodeError, KeyError) as error:
                        self.logger.error(f"Failed to parse S3 response: {error}")
                        self.logger.error(f"Raw response data: {response.text}")
                        return None
                else:
                    self.logger.error(f"Unexpected response status: {response.status_code}. Response: {response.text}")
                    return None

        except Exception as error:
            self.logger.error(f"Error uploading image: {error}")
            return None

    async def download_image(self, image_url: str, headers: Optional[Dict[str, str]] = None, redirect_count: int = 0) -> Optional[bytes]:
        """
        Download an image from a URL and return the image data as bytes.
        
        Args:
            image_url: URL of the image to download
            headers: Optional headers to include in the request
            redirect_count: Internal counter for handling redirects
            
        Returns:
            Image data as bytes, or None if download failed
        """
        MAX_REDIRECTS = 5
        try:
            if redirect_count > MAX_REDIRECTS:
                self.logger.error("Too many redirects")
                return None

            async with httpx.AsyncClient() as client:
                response = await client.get(image_url, headers=headers or {}, follow_redirects=True)
                
                if response.status_code == 200:
                    buffer = response.content
                    self.logger.info(f"Image downloaded successfully from '{image_url}'")
                    return buffer
                else:
                    self.logger.error(f"Failed to download image. Status code: {response.status_code}")
                    return None

        except Exception as error:
            self.logger.error(f"Error downloading image: {error}")
            return None