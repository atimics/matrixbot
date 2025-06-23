#!/usr/bin/env python3
"""
S3 Service

A service wrapper for S3 integration that provides image and file upload capabilities.
This service wraps the S3Client and provides a simplified interface for the chatbot tools.
"""

import logging
from typing import Optional
import httpx
from ..integrations.s3_client import S3Client
from ..config import settings

logger = logging.getLogger(__name__)


class S3Service:
    """Service for uploading images and files to S3."""

    def __init__(self, s3_client: Optional[S3Client] = None):
        """
        Initialize S3 service.
        
        Args:
            s3_client: Optional S3Client instance. If not provided,
                      will create one from settings if available.
        """
        self.s3_client = s3_client
        
        # Create client from settings if not provided
        if not self.s3_client and all([
            settings.storage.s3_api_endpoint,
            settings.storage.s3_api_key,
            settings.storage.cloudfront_domain
        ]):
            self.s3_client = S3Client(
                s3_api_endpoint=settings.storage.s3_api_endpoint,
                s3_api_key=settings.storage.s3_api_key,
                cloudfront_domain=settings.storage.cloudfront_domain
            )
    
    def is_configured(self) -> bool:
        """Check if S3 service is properly configured."""
        return self.s3_client is not None

    def is_s3_url(self, url: str) -> bool:
        """Check if a URL is an S3 URL."""
        if not url:
            return False
        # Check for CloudFront domains and common S3 patterns
        return (
            url.startswith(settings.storage.cloudfront_domain) if settings.storage.cloudfront_domain else False
            or "amazonaws.com" in url.lower()
            or "cloudfront.net" in url.lower()
            or "s3" in url.lower()
        )

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
            # Create tags for the image (kept for compatibility, but S3 API might not use them)
            tags = {
                "Content-Type": content_type,
                "App-Name": "Chatbot",
                "File-Name": filename,
            }
            
            # Upload to S3
            s3_url = await self.s3_client.upload_data(
                data=image_data,
                content_type=content_type,
                tags=tags
            )
            
            if s3_url:
                return s3_url
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
            elif image_path.lower().endswith('.webm'):
                content_type = "video/webm"
            elif image_path.lower().endswith('.mov'):
                content_type = "video/quicktime"
            
            filename = image_path.split('/')[-1]  # Get filename from path
            
            return await self.upload_image_data(image_data, filename, content_type)
            
        except Exception as e:
            logger.error(f"S3Service: Error reading/uploading image file {image_path}: {e}")
            return None

    async def ensure_s3_url(self, url: str) -> Optional[str]:
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
        if self.is_s3_url(url):
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
            if self.s3_client:
                return await self.s3_client.download_image(url)
            else:
                # Fallback to direct download
                async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
                    response = await client.get(url)
                    response.raise_for_status()
                    return response.content
        except Exception as e:
            logger.error(f"S3Service: Error downloading file from {url}: {e}")
            return None

    def generate_embeddable_url(self, s3_url: str, title: str = "", description: str = "") -> str:
        """
        Generate an embeddable URL with metadata for social media.
        
        Args:
            s3_url: Original S3 URL
            title: Title for the embed
            description: Description for the embed
            
        Returns:
            Embeddable URL (for now, just returns the original URL)
        """
        # For S3, we might not need special embeddable URLs like Arweave
        # Just return the original URL, but this method is kept for compatibility
        return s3_url


# Global instance
s3_service = S3Service()
