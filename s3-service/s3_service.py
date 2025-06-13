#!/usr/bin/env python3
"""
S3 Service

A service wrapper for S3 integration that provides image and file upload capabilities.
Drop-in replacement for ArweaveService - provides the same interface but uses S3 storage.
"""

import logging
from typing import Optional
import httpx
from .s3_uploader_client import S3UploaderClient

logger = logging.getLogger(__name__)


class S3Service:
    """Service for uploading images and files to S3 - drop-in replacement for ArweaveService."""

    def __init__(self, s3_client: Optional[S3UploaderClient] = None):
        """
        Initialize S3 service.
        
        Args:
            s3_client: Optional S3UploaderClient instance. If not provided,
                      will create one from settings if available.
        """
        self.s3_client = s3_client
        
        # Create client from environment if not provided
        if not self.s3_client:
            # Try to create from environment variables
            import os
            s3_service_url = os.getenv("S3_SERVICE_URL", "http://localhost:8001")
            cloudfront_domain = os.getenv("CLOUDFRONT_DOMAIN", "https://cloudfront.example.com")
            s3_api_key = os.getenv("S3_SERVICE_API_KEY")
            
            if s3_service_url:
                self.s3_client = S3UploaderClient(
                    uploader_service_url=s3_service_url,
                    gateway_url=cloudfront_domain,
                    api_key=s3_api_key
                )
    
    def is_configured(self) -> bool:
        """Check if S3 service is properly configured."""
        return self.s3_client is not None

    def is_arweave_url(self, url: str) -> bool:
        """Check if a URL is an S3 URL (keeping method name for compatibility)."""
        if not url:
            return False
        # Check for CloudFront domain or common S3 patterns
        return (url.startswith("https://") and 
                (".amazonaws.com" in url or "cloudfront" in url.lower() or 
                 (self.s3_client and self.s3_client.gateway_url in url)))

    async def upload_image_data(self, image_data: bytes, filename: str = "image.png", content_type: str = "image/png") -> Optional[str]:
        """
        Upload image data to S3.
        
        Args:
            image_data: Raw image data bytes
            filename: Filename for the image
            content_type: MIME type of the image
            
        Returns:
            Public S3 URL or None if failed
        """
        if not self.s3_client:
            logger.error("S3Service: No client configured")
            return None
            
        try:
            # Create tags for the image
            tags = {
                "Content-Type": content_type,
                "App-Name": "Chatbot",
                "File-Name": filename,
            }
            
            # Upload to S3
            s3_path = await self.s3_client.upload_data(
                data=image_data,
                content_type=content_type,
                tags=tags
            )
            
            if s3_path:
                logger.info(f"S3Service: Successfully uploaded image ({len(image_data)} bytes) to S3")
                return self.s3_client.get_arweave_url(s3_path)
            else:
                logger.error("S3Service: Failed to upload image - no URL returned")
                return None
                
        except Exception as e:
            logger.error(f"S3Service: Error uploading image: {e}")
            return None

    async def upload_image(self, image_path: str) -> Optional[str]:
        """
        Upload an image file to S3.
        
        Args:
            image_path: Path to the image file
            
        Returns:
            Public S3 URL or None if failed
        """
        try:
            with open(image_path, 'rb') as f:
                image_data = f.read()
            
            # Determine content type based on file extension
            content_type = "image/png"  # default
            if image_path.lower().endswith('.jpg') or image_path.lower().endswith('.jpeg'):
                content_type = "image/jpeg"
            elif image_path.lower().endswith('.gif'):
                content_type = "image/gif"
            elif image_path.lower().endswith('.webp'):
                content_type = "image/webp"
            elif image_path.lower().endswith('.mp4'):
                content_type = "video/mp4"
            
            filename = image_path.split('/')[-1]  # Get filename from path
            
            return await self.upload_image_data(image_data, filename, content_type)
            
        except Exception as e:
            logger.error(f"S3Service: Error reading/uploading image file {image_path}: {e}")
            return None

    async def ensure_arweave_url(self, url: str) -> Optional[str]:
        """
        Ensure a URL is an S3 URL. If it's already an S3 URL, return it.
        If it's another URL, download and upload to S3.
        
        Args:
            url: URL to process
            
        Returns:
            S3 URL or None if failed
        """
        if not url:
            return None
            
        # If already an S3 URL, return it
        if self.is_arweave_url(url):
            return url
        
        # Download the image and upload to S3
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                
                # Get content type from response
                content_type = response.headers.get('content-type', 'image/png')
                
                # Extract filename from URL
                filename = url.split('/')[-1] if '/' in url else 'image'
                if '?' in filename:
                    filename = filename.split('?')[0]
                if not filename or '.' not in filename:
                    # Determine extension from content type
                    if 'jpeg' in content_type or 'jpg' in content_type:
                        filename = 'image.jpg'
                    elif 'gif' in content_type:
                        filename = 'image.gif'
                    elif 'webp' in content_type:
                        filename = 'image.webp'
                    else:
                        filename = 'image.png'
                
                return await self.upload_image_data(response.content, filename, content_type)
                
        except Exception as e:
            logger.error(f"S3Service: Error downloading/uploading image from {url}: {e}")
            return None

    async def download_file_data(self, url: str) -> Optional[bytes]:
        """
        Download file data from an S3 URL.
        
        Args:
            url: S3 URL
            
        Returns:
            File data bytes or None if failed
        """
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                return response.content
        except Exception as e:
            logger.error(f"S3Service: Error downloading file from {url}: {e}")
            return None

    async def upload_media_data(self, media_data: bytes, filename: str, content_type: str) -> Optional[str]:
        """
        Upload media data (image, video, etc.) to S3.
        
        Args:
            media_data: Raw media data bytes
            filename: Filename for the media file
            content_type: MIME type of the media (e.g., 'video/mp4', 'image/png')
            
        Returns:
            Public S3 URL or None if failed
        """
        if not self.s3_client:
            logger.error("S3Service: No client configured")
            return None
            
        try:
            # Create tags for the media - determine type from content_type
            media_type = "unknown"
            if content_type.startswith("image/"):
                media_type = "image"
            elif content_type.startswith("video/"):
                media_type = "video"
            elif content_type.startswith("audio/"):
                media_type = "audio"
                
            tags = {
                "Content-Type": content_type,
                "App-Name": "Chatbot",
                "File-Name": filename,
                "Media-Type": media_type,
            }
            
            # Upload to S3
            s3_path = await self.s3_client.upload_data(
                data=media_data,
                content_type=content_type,
                tags=tags
            )
            
            if s3_path:
                logger.info(f"S3Service: Successfully uploaded {media_type} ({len(media_data)} bytes) to S3")
                return self.s3_client.get_arweave_url(s3_path)
            else:
                logger.error("S3Service: Failed to upload media - no URL returned")
                return None
                
        except Exception as e:
            logger.error(f"S3Service: Error uploading {content_type} media: {e}")
            return None


# Global instance
s3_service = S3Service()

# Alias for drop-in replacement
ArweaveService = S3Service
arweave_service = s3_service
