"""
Dual Storage Manager

Manages both S3 (primary media storage) and Arweave (NFT minting) storage.
Media is uploaded to S3 for fast delivery, with option to mint NFTs on Arweave from same media.
"""

import logging
from typing import Optional, Dict, Any, Tuple

from .s3_storage_service import S3StorageService
from .arweave_uploader_client import ArweaveUploaderClient
from ..tools.arweave_service import ArweaveService
from ..config import settings

logger = logging.getLogger(__name__)


class DualStorageManager:
    """Manages dual storage: S3 for media delivery, Arweave for NFT minting"""

    def __init__(self, 
                 s3_service: Optional[S3StorageService] = None,
                 arweave_service: Optional[ArweaveService] = None):
        """
        Initialize dual storage manager.
        
        Args:
            s3_service: S3 service instance (created from config if not provided)
            arweave_service: Arweave service instance (created from config if not provided)
        """
        # Initialize S3 service
        self.s3_service = s3_service
        if not self.s3_service:
            try:
                self.s3_service = S3StorageService()
                if self.s3_service.is_configured():
                    logger.info("DualStorageManager: S3 service initialized")
                else:
                    logger.warning("DualStorageManager: S3 service not properly configured")
                    self.s3_service = None
            except Exception as e:
                logger.error(f"DualStorageManager: Failed to initialize S3 service: {e}")
                self.s3_service = None

        # Initialize Arweave service (keep existing for NFT minting)
        self.arweave_service = arweave_service
        if not self.arweave_service:
            self.arweave_service = ArweaveService()
            if self.arweave_service.is_configured():
                logger.info("DualStorageManager: Arweave service initialized")
            else:
                logger.debug("DualStorageManager: Arweave service not configured (optional for NFT-only)")

        # Configuration
        self.use_s3_primary = getattr(settings, 'USE_S3_FOR_MEDIA', True)
        logger.debug(f"DualStorageManager: S3 primary storage: {self.use_s3_primary}")

    def is_s3_available(self) -> bool:
        """Check if S3 storage is available"""
        return self.s3_service is not None and self.s3_service.is_configured()

    def is_arweave_available(self) -> bool:
        """Check if Arweave storage is available"""
        return self.arweave_service is not None and self.arweave_service.is_configured()

    async def upload_media(self, media_data: bytes, filename: str = "media.png", 
                          content_type: str = "image/png") -> Optional[str]:
        """
        Upload media using the primary storage method (S3 by default).
        
        Args:
            media_data: Raw media bytes
            filename: Filename (used to determine type)
            content_type: MIME type
            
        Returns:
            Public URL or None if failed
        """
        if self.use_s3_primary and self.is_s3_available():
            logger.debug(f"Uploading media to S3: {filename}")
            
            # Determine if it's video or image
            is_video = content_type.startswith('video/') or any(
                filename.lower().endswith(ext) for ext in ['.mp4', '.webm', '.mov', '.avi']
            )
            
            if is_video:
                return await self.s3_service.upload_video_data(media_data, filename, content_type)
            else:
                return await self.s3_service.upload_image_data(media_data, filename, content_type)
        
        elif self.is_arweave_available():
            logger.debug(f"Falling back to Arweave for media upload: {filename}")
            return await self.arweave_service.upload_image_data(media_data, filename, content_type)
        
        else:
            logger.error("No storage services available for media upload")
            return None

    async def upload_media_file(self, file_path: str) -> Optional[str]:
        """
        Upload a media file using the primary storage method.
        
        Args:
            file_path: Path to the media file
            
        Returns:
            Public URL or None if failed
        """
        if self.use_s3_primary and self.is_s3_available():
            logger.debug(f"Uploading file to S3: {file_path}")
            return await self.s3_service.upload_image_file(file_path)
        
        elif self.is_arweave_available():
            logger.debug(f"Falling back to Arweave for file upload: {file_path}")
            return await self.arweave_service.upload_image(file_path)
        
        else:
            logger.error("No storage services available for file upload")
            return None

    async def mint_nft_from_media(self, media_data: bytes, filename: str = "nft.png",
                                 content_type: str = "image/png", 
                                 tags: Optional[Dict[str, str]] = None) -> Optional[str]:
        """
        Upload media to Arweave specifically for NFT minting.
        This is separate from primary storage to ensure permanence for NFTs.
        
        Args:
            media_data: Raw media bytes
            filename: Filename for the NFT
            content_type: MIME type
            tags: Optional Arweave tags for the NFT
            
        Returns:
            Arweave URL or None if failed
        """
        if not self.is_arweave_available():
            logger.error("Arweave service not available for NFT minting")
            return None
        
        logger.debug(f"Minting NFT on Arweave: {filename}")
        return await self.arweave_service.upload_image_data(media_data, filename, content_type)

    async def upload_dual(self, media_data: bytes, filename: str = "media.png",
                         content_type: str = "image/png") -> Tuple[Optional[str], Optional[str]]:
        """
        Upload media to both S3 and Arweave for maximum redundancy.
        Useful for important media that needs both fast delivery and permanence.
        
        Args:
            media_data: Raw media bytes
            filename: Filename
            content_type: MIME type
            
        Returns:
            Tuple of (s3_url, arweave_url) - either may be None if that service failed
        """
        s3_url = None
        arweave_url = None
        
        # Upload to S3 for fast delivery
        if self.is_s3_available():
            try:
                s3_url = await self.upload_media(media_data, filename, content_type)
                if s3_url:
                    logger.debug(f"Successfully uploaded to S3: {s3_url}")
            except Exception as e:
                logger.error(f"Failed to upload to S3: {e}")
        
        # Upload to Arweave for permanence
        if self.is_arweave_available():
            try:
                arweave_url = await self.mint_nft_from_media(media_data, filename, content_type)
                if arweave_url:
                    logger.debug(f"Successfully uploaded to Arweave: {arweave_url}")
            except Exception as e:
                logger.error(f"Failed to upload to Arweave: {e}")
        
        return s3_url, arweave_url

    def get_storage_status(self) -> Dict[str, Any]:
        """
        Get the status of both storage services.
        
        Returns:
            Status dictionary with info about both services
        """
        return {
            "s3": {
                "available": self.is_s3_available(),
                "configured": self.s3_service is not None,
                "primary": self.use_s3_primary,
                "info": self.s3_service.get_storage_info() if self.s3_service else None
            },
            "arweave": {
                "available": self.is_arweave_available(),
                "configured": self.arweave_service is not None,
                "nft_ready": self.is_arweave_available()
            },
            "dual_storage": {
                "primary_service": "s3" if self.use_s3_primary else "arweave",
                "nft_minting": self.is_arweave_available(),
                "fast_delivery": self.is_s3_available()
            }
        }

    async def health_check(self) -> Dict[str, Any]:
        """
        Perform health checks on both storage services.
        
        Returns:
            Health status for both services
        """
        status = {
            "timestamp": None,
            "s3": {"status": "not_configured"},
            "arweave": {"status": "not_configured"},
            "overall": "unknown"
        }
        
        import time
        status["timestamp"] = time.time()
        
        # Check S3 health
        if self.s3_service:
            try:
                status["s3"] = await self.s3_service.health_check()
            except Exception as e:
                status["s3"] = {"status": "error", "message": str(e)}
        
        # Check Arweave health (simpler check since it's for NFTs)
        if self.arweave_service:
            status["arweave"] = {
                "status": "configured" if self.is_arweave_available() else "not_configured",
                "configured": self.is_arweave_available()
            }
        
        # Determine overall status
        s3_ok = status["s3"].get("status") == "healthy"
        arweave_ok = status["arweave"].get("status") == "configured"
        
        if s3_ok and arweave_ok:
            status["overall"] = "healthy"
        elif s3_ok or arweave_ok:
            status["overall"] = "partial"
        else:
            status["overall"] = "unhealthy"
        
        return status
