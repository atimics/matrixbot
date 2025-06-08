#!/usr/bin/env python3
"""
Arweave Service

A service wrapper for Arweave integration that provides image and file upload capabilities.
This service wraps the ArweaveUploaderClient and provides a simplified interface for the chatbot tools.
"""

import logging
from typing import Optional
import httpx
from ..integrations.arweave_uploader_client import ArweaveUploaderClient
from ..config import settings

logger = logging.getLogger(__name__)


class ArweaveService:
    """Service for uploading images and files to Arweave."""

    def __init__(self, arweave_client: Optional[ArweaveUploaderClient] = None):
        """
        Initialize Arweave service.
        
        Args:
            arweave_client: Optional ArweaveUploaderClient instance. If not provided,
                          will create one from settings if available.
        """
        self.arweave_client = arweave_client
        
        # Create client from settings if not provided
        if not self.arweave_client and settings.ARWEAVE_INTERNAL_UPLOADER_SERVICE_URL:
            self.arweave_client = ArweaveUploaderClient(
                uploader_service_url=settings.ARWEAVE_INTERNAL_UPLOADER_SERVICE_URL,
                gateway_url=settings.ARWEAVE_GATEWAY_URL,
            )
    
    def is_configured(self) -> bool:
        """Check if Arweave service is properly configured."""
        return self.arweave_client is not None
    
    def is_arweave_url(self, url: str) -> bool:
        """Check if a URL is an Arweave URL."""
        if not url:
            return False
        return url.startswith("https://arweave.net/") or url.startswith("https://ar.io/") or "arweave" in url.lower()
    
    async def upload_image_data(self, image_data: bytes, filename: str = "image.png", content_type: str = "image/png") -> Optional[str]:
        """
        Upload image data to Arweave.
        
        Args:
            image_data: Raw image data bytes
            filename: Filename for the image
            content_type: MIME type of the image
            
        Returns:
            Public Arweave URL or None if failed
        """
        if not self.arweave_client:
            logger.error("ArweaveService: No client configured")
            return None
            
        try:
            # Create tags for the image
            tags = {
                "Content-Type": content_type,
                "App-Name": "Chatbot",
                "File-Name": filename,
            }
            
            # Upload to Arweave
            tx_id = await self.arweave_client.upload_data(
                data=image_data,
                content_type=content_type,
                tags=tags
            )
            
            if tx_id:
                return self.arweave_client.get_arweave_url(tx_id)
            else:
                logger.error("ArweaveService: Failed to upload image - no transaction ID returned")
                return None
                
        except Exception as e:
            logger.error(f"ArweaveService: Error uploading image: {e}")
            return None
    
    async def upload_image(self, image_path: str) -> Optional[str]:
        """
        Upload an image file to Arweave.
        
        Args:
            image_path: Path to the image file
            
        Returns:
            Public Arweave URL or None if failed
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
            
            filename = image_path.split('/')[-1]  # Get filename from path
            
            return await self.upload_image_data(image_data, filename, content_type)
            
        except Exception as e:
            logger.error(f"ArweaveService: Error reading/uploading image file {image_path}: {e}")
            return None
    
    async def ensure_arweave_url(self, url: str) -> Optional[str]:
        """
        Ensure a URL is an Arweave URL. If it's already an Arweave URL, return it.
        If it's another URL, download and upload to Arweave.
        
        Args:
            url: URL to process
            
        Returns:
            Arweave URL or None if failed
        """
        if not url:
            return None
            
        # If already an Arweave URL, return it
        if self.is_arweave_url(url):
            return url
        
        # Download the image and upload to Arweave
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
            logger.error(f"ArweaveService: Error downloading/uploading image from {url}: {e}")
            return None
    
    async def download_file_data(self, url: str) -> Optional[bytes]:
        """
        Download file data from an Arweave URL.
        
        Args:
            url: Arweave URL
            
        Returns:
            File data bytes or None if failed
        """
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                return response.content
        except Exception as e:
            logger.error(f"ArweaveService: Error downloading file from {url}: {e}")
            return None


# Global instance
arweave_service = ArweaveService()
