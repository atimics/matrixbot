"""
S3 Storage Service

Service wrapper for S3 storage that provides media upload capabilities.
Works alongside ArweaveService - S3 for primary storage, Arweave for NFT minting.
"""

import logging
from typing import Optional, Dict, Any
from pathlib import Path

from .s3_storage_client import S3StorageClient
from ..config import settings

logger = logging.getLogger(__name__)


class S3StorageService:
    """Service for uploading media to S3 while maintaining Arweave integration for NFTs"""

    def __init__(self, s3_client: Optional[S3StorageClient] = None):
        """
        Initialize S3 storage service.
        
        Args:
            s3_client: Optional S3StorageClient instance. If not provided,
                      will create one from settings if available.
        """
        self.s3_client = s3_client
        
        # Create client from settings if not provided
        if not self.s3_client:
            try:
                self.s3_client = S3StorageClient()
                logger.info("S3StorageService: Initialized with environment configuration")
            except ValueError as e:
                logger.warning(f"S3StorageService: Could not initialize - {e}")
                self.s3_client = None
    
    def is_configured(self) -> bool:
        """Check if S3 service is properly configured."""
        return self.s3_client is not None and self.s3_client.is_network_available()
    
    def is_s3_url(self, url: str) -> bool:
        """Check if a URL is an S3/CloudFront URL."""
        if not url or not self.s3_client:
            return False
        return self.s3_client.is_s3_url(url)
    
    async def upload_image_file(self, file_path: str) -> Optional[str]:
        """
        Upload an image file to S3.
        
        Args:
            file_path: Path to the image file
            
        Returns:
            Public S3 URL or None if failed
        """
        if not self.s3_client:
            logger.error("S3StorageService: No client configured")
            return None
            
        try:
            return await self.s3_client.upload_image(file_path)
        except Exception as e:
            logger.error(f"S3StorageService: Error uploading image file: {e}")
            return None

    async def upload_image_data(self, image_data: bytes, filename: str = "image.png", 
                               content_type: str = "image/png") -> Optional[str]:
        """
        Upload image data to S3.
        
        Args:
            image_data: Raw image data bytes
            filename: Filename for the image (used to determine type)
            content_type: MIME type of the image
            
        Returns:
            Public S3 URL or None if failed
        """
        if not self.s3_client:
            logger.error("S3StorageService: No client configured")
            return None
            
        try:
            # Extract file extension from filename or content_type
            if filename and '.' in filename:
                image_type = Path(filename).suffix.lower().lstrip('.')
            else:
                # Map content type to extension
                type_map = {
                    'image/png': 'png',
                    'image/jpeg': 'jpg',
                    'image/jpg': 'jpg', 
                    'image/gif': 'gif',
                    'video/mp4': 'mp4',
                    'video/webm': 'webm',
                    'video/quicktime': 'mov'
                }
                image_type = type_map.get(content_type, 'png')
            
            # Normalize jpeg to jpg
            if image_type == 'jpeg':
                image_type = 'jpg'
            
            return await self.s3_client.upload_image_data(image_data, image_type)
                
        except Exception as e:
            logger.error(f"S3StorageService: Error uploading image data: {e}")
            return None

    async def upload_video_data(self, video_data: bytes, filename: str = "video.mp4", 
                               content_type: str = "video/mp4") -> Optional[str]:
        """
        Upload video data to S3.
        
        Args:
            video_data: Raw video data bytes
            filename: Filename for the video (used to determine type)
            content_type: MIME type of the video
            
        Returns:
            Public S3 URL or None if failed
        """
        if not self.s3_client:
            logger.error("S3StorageService: No client configured")
            return None
            
        try:
            # Extract file extension from filename or content_type
            if filename and '.' in filename:
                video_type = Path(filename).suffix.lower().lstrip('.')
            else:
                # Map content type to extension
                type_map = {
                    'video/mp4': 'mp4',
                    'video/webm': 'webm',
                    'video/quicktime': 'mov',
                    'video/x-msvideo': 'avi'
                }
                video_type = type_map.get(content_type, 'mp4')
            
            return await self.s3_client.upload_video_data(video_data, video_type)
                
        except Exception as e:
            logger.error(f"S3StorageService: Error uploading video data: {e}")
            return None

    async def download_media(self, url: str, headers: Optional[Dict[str, str]] = None) -> Optional[bytes]:
        """
        Download media from a URL.
        
        Args:
            url: URL of the media to download
            headers: Optional HTTP headers
            
        Returns:
            Media data as bytes or None if failed
        """
        if not self.s3_client:
            logger.error("S3StorageService: No client configured")
            return None
            
        try:
            return await self.s3_client.download_image(url, headers)
        except Exception as e:
            logger.error(f"S3StorageService: Error downloading media: {e}")
            return None

    async def health_check(self) -> Dict[str, Any]:
        """
        Check the health of the S3 service.
        
        Returns:
            Health status dictionary
        """
        if not self.s3_client:
            return {
                "status": "error",
                "configured": False,
                "message": "S3 client not configured"
            }
        
        try:
            is_healthy = await self.s3_client.health_check()
            return {
                "status": "healthy" if is_healthy else "unhealthy",
                "configured": True,
                "network_available": self.s3_client.is_network_available(),
                "endpoint": self.s3_client.api_endpoint,
                "cloudfront": self.s3_client.cloudfront_domain
            }
        except Exception as e:
            return {
                "status": "error",
                "configured": True,
                "message": str(e)
            }

    def get_storage_info(self) -> Dict[str, Any]:
        """
        Get information about the S3 storage configuration.
        
        Returns:
            Storage configuration info
        """
        if not self.s3_client:
            return {
                "configured": False,
                "type": "s3",
                "message": "S3 client not configured"
            }
        
        return {
            "configured": True,
            "type": "s3",
            "endpoint": self.s3_client.api_endpoint,
            "cloudfront_domain": self.s3_client.cloudfront_domain,
            "network_available": self.s3_client.is_network_available()
        }
