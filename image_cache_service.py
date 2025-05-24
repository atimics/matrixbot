import asyncio
import logging
import os
import tempfile
import uuid
import hashlib
from typing import Optional, Dict, Any
from urllib.parse import urlparse

import database
from s3_service import S3Service
from matrix_media_utils import MatrixMediaUtils
from message_bus import MessageBus
from event_definitions import (
    MatrixImageReceivedEvent,
    ImageCacheRequestEvent,
    ImageCacheResponseEvent
)

logger = logging.getLogger(__name__)

class ImageCacheService:
    """
    Service that handles image downloading, caching, and uploading to S3.
    Provides a clean separation between Matrix gateway and image processing.
    """
    
    def __init__(self, message_bus: MessageBus, db_path: str):
        self.bus = message_bus
        self.db_path = db_path
        self._stop_event = asyncio.Event()
        
        # Initialize S3 service
        self.s3_service = None
        try:
            self.s3_service = S3Service()
            logger.info("ImageCacheService: S3Service initialized successfully")
        except Exception as e:
            logger.warning(f"ImageCacheService: S3Service initialization failed: {e}. Images will not be uploaded to S3.")
        
        # Matrix client reference (set by gateway during initialization)
        self._matrix_client = None
    
    def set_matrix_client(self, matrix_client):
        """Set the Matrix client for MXC URL downloads. Called by gateway service."""
        self._matrix_client = matrix_client
        logger.info("ImageCacheService: Matrix client reference set")
    
    async def _generate_cache_key(self, image_url: str) -> str:
        """Generate a consistent cache key for an image URL."""
        return hashlib.sha256(image_url.encode()).hexdigest()
    
    async def _download_image_data(self, image_url: str) -> Optional[bytes]:
        """Download image data from either MXC or HTTP URL."""
        if image_url.startswith("mxc://"):
            if not self._matrix_client:
                logger.error("ImageCacheService: No Matrix client available for MXC URL download")
                return None
            
            try:
                logger.info(f"ImageCacheService: Downloading MXC image: {image_url}")
                image_data = await MatrixMediaUtils.download_media_simple(image_url, self._matrix_client)
                if image_data:
                    logger.info(f"ImageCacheService: Successfully downloaded MXC image. Size: {len(image_data)} bytes")
                    return image_data
                else:
                    logger.warning(f"ImageCacheService: MXC download returned no data for: {image_url}")
                    return None
            except Exception as e:
                logger.error(f"ImageCacheService: Failed to download MXC image {image_url}: {e}")
                return None
        
        else:
            # HTTP/HTTPS URL
            if not self.s3_service:
                logger.error("ImageCacheService: S3Service not available for HTTP download")
                return None
            
            try:
                logger.info(f"ImageCacheService: Downloading HTTP image: {image_url}")
                image_data = await self.s3_service.download_image(image_url)
                if image_data:
                    logger.info(f"ImageCacheService: Successfully downloaded HTTP image. Size: {len(image_data)} bytes")
                    return image_data
                else:
                    logger.warning(f"ImageCacheService: HTTP download returned no data for: {image_url}")
                    return None
            except Exception as e:
                logger.error(f"ImageCacheService: Failed to download HTTP image {image_url}: {e}")
                return None
    
    async def _upload_to_s3(self, image_data: bytes, original_url: str) -> Optional[str]:
        """Upload image data to S3 and return the S3 URL."""
        if not self.s3_service:
            logger.error("ImageCacheService: S3Service not available for upload")
            return None
        
        try:
            # Determine file extension (default to jpg)
            file_extension = ".jpg"
            if original_url.lower().endswith(('.png', '.gif', '.webp')):
                file_extension = "." + original_url.split('.')[-1].lower()
            
            # Generate unique filename
            unique_filename = f"matrix_image_{uuid.uuid4()}{file_extension}"
            
            # Save to temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as temp_file:
                temp_file.write(image_data)
                temp_file_path = temp_file.name
            
            try:
                # Upload to S3
                s3_url = await self.s3_service.upload_image(temp_file_path, object_name=unique_filename)
                if s3_url:
                    logger.info(f"ImageCacheService: Successfully uploaded to S3: {s3_url}")
                    return s3_url
                else:
                    logger.error("ImageCacheService: S3 upload returned None")
                    return None
            finally:
                # Clean up temporary file
                try:
                    os.unlink(temp_file_path)
                except OSError as e:
                    logger.warning(f"ImageCacheService: Could not delete temporary file {temp_file_path}: {e}")
        
        except Exception as e:
            logger.error(f"ImageCacheService: Error uploading to S3: {e}")
            return None
    
    async def _cache_image(self, image_url: str, s3_url: str) -> None:
        """Store image cache mapping in database."""
        try:
            cache_key = await self._generate_cache_key(image_url)
            await database.store_image_cache(self.db_path, cache_key, image_url, s3_url)
            logger.info(f"ImageCacheService: Cached image mapping: {image_url} -> {s3_url}")
        except Exception as e:
            logger.error(f"ImageCacheService: Failed to cache image mapping: {e}")
    
    async def _get_cached_image(self, image_url: str) -> Optional[str]:
        """Retrieve cached S3 URL for an image."""
        try:
            cache_key = await self._generate_cache_key(image_url)
            cached_data = await database.get_image_cache(self.db_path, cache_key)
            if cached_data:
                s3_url = cached_data[2]  # Assuming (cache_key, original_url, s3_url) structure
                logger.info(f"ImageCacheService: Found cached image: {image_url} -> {s3_url}")
                return s3_url
            return None
        except Exception as e:
            logger.error(f"ImageCacheService: Failed to retrieve cached image: {e}")
            return None
    
    async def process_image_for_s3(self, image_url: str) -> Optional[str]:
        """
        Process an image URL and return an S3 URL.
        Checks cache first, downloads and uploads if not cached.
        """
        # Check cache first
        cached_s3_url = await self._get_cached_image(image_url)
        if cached_s3_url:
            return cached_s3_url
        
        # Download image data
        image_data = await self._download_image_data(image_url)
        if not image_data:
            logger.error(f"ImageCacheService: Failed to download image: {image_url}")
            return None
        
        # Upload to S3
        s3_url = await self._upload_to_s3(image_data, image_url)
        if not s3_url:
            logger.error(f"ImageCacheService: Failed to upload image to S3: {image_url}")
            return None
        
        # Cache the mapping
        await self._cache_image(image_url, s3_url)
        
        return s3_url
    
    async def _handle_image_cache_request(self, event: ImageCacheRequestEvent) -> None:
        """Handle incoming image cache requests."""
        s3_url = await self.process_image_for_s3(event.image_url)
        
        response = ImageCacheResponseEvent(
            request_id=event.request_id,
            original_url=event.image_url,
            s3_url=s3_url,
            success=s3_url is not None
        )
        
        await self.bus.publish(response)
    
    async def _handle_matrix_image_auto_cache(self, event: MatrixImageReceivedEvent) -> None:
        """Automatically cache images when they're received from Matrix."""
        # Process image in background without blocking
        asyncio.create_task(self.process_image_for_s3(event.image_url))
    
    async def run(self) -> None:
        """Main service loop."""
        logger.info("ImageCacheService: Starting...")
        
        # Subscribe to image cache requests
        self.bus.subscribe(ImageCacheRequestEvent.get_event_type(), self._handle_image_cache_request)
        
        # Auto-cache Matrix images when received
        self.bus.subscribe(MatrixImageReceivedEvent.get_event_type(), self._handle_matrix_image_auto_cache)
        
        await self._stop_event.wait()
        logger.info("ImageCacheService: Stopped.")
    
    async def stop(self) -> None:
        """Stop the service."""
        logger.info("ImageCacheService: Stop requested.")
        self._stop_event.set()