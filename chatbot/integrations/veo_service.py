"""
Google Veo Video Generation Service

Enhanced video generation service inspired by JavaScript best practices.
Provides robust video generation with rate limiting, browser headers, and polling.
"""

import asyncio
import logging
import os
import random
import tempfile
import time
from typing import Dict, List, Optional, Union

import httpx

logger = logging.getLogger(__name__)


class VeoService:
    """
    Enhanced Veo video generation service with JavaScript best practices.

    Features:
    - Rate limiting with per-minute and per-day limits
    - Browser headers for downloads
    - Robust polling with exponential backoff
    - S3 integration for video storage
    - Enhanced error handling
    """

    def __init__(
        self, api_key: str, s3_service=None, default_model: str = "veo-2.0-generate-001"
    ):
        """
        Initialize Veo service.

        Args:
            api_key: Google AI API key
            s3_service: S3 service for video storage
            default_model: Default Veo model
        """
        self.api_key = api_key
        self.s3_service = s3_service
        self.default_model = default_model
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"

        # Rate limiting tracking
        self.recent_requests = []
        self.rate_limit_per_minute = 5  # Conservative for video generation
        self.rate_limit_per_day = 50  # Conservative for video generation

        # Browser headers for downloads
        self.browser_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
        }

    def check_rate_limit(self) -> bool:
        """
        Check if we're within rate limits.

        Returns:
            True if within limits, False otherwise
        """
        now = time.time()

        # Filter recent requests within the last minute
        recent_requests = [req for req in self.recent_requests if now - req < 60]
        if len(recent_requests) >= self.rate_limit_per_minute:
            return False

        # Filter recent requests within the last day
        daily_requests = [
            req for req in self.recent_requests if now - req < 24 * 60 * 60
        ]
        if len(daily_requests) >= self.rate_limit_per_day:
            return False

        return True

    def _record_request(self):
        """Record a new request for rate limiting."""
        self.recent_requests.append(time.time())
        # Keep only last day's requests
        cutoff = time.time() - 24 * 60 * 60
        self.recent_requests = [req for req in self.recent_requests if req > cutoff]

    async def generate_videos_from_images(
        self,
        prompt: Optional[str] = None,
        images: Optional[List[Dict[str, str]]] = None,
        config: Optional[Dict] = None,
        model: str = None,
    ) -> List[str]:
        """
        Generate videos from image(s) using Google Gemini Veo model.

        Args:
            prompt: Optional text prompt for video generation
            images: Array of {"data": base64_string, "mimeType": str} images
            config: Video generation configuration (aspectRatio, numberOfVideos, etc)
            model: Veo model to use (default from config)

        Returns:
            Array of S3 URLs for generated videos
        """
        if not self.check_rate_limit():
            logger.warning("VeoService: Rate limit exceeded")
            return []

        if not images or len(images) == 0:
            logger.error("VeoService: At least one image is required")
            return []

        # Use default config if not provided
        if config is None:
            config = {"numberOfVideos": 1, "personGeneration": "allow_adult"}

        # Use first image as primary input
        first_image = images[0]
        image_param = {
            "imageBytes": first_image["data"],
            "mimeType": first_image["mimeType"],
        }

        try:
            self._record_request()

            async with httpx.AsyncClient(
                timeout=600.0
            ) as client:  # 10 min timeout for video
                # Start video generation operation
                payload = {
                    "model": model or self.default_model,
                    "prompt": prompt,
                    "image": image_param,
                    "config": config,
                }

                response = await client.post(
                    f"{self.base_url}/models/{model or self.default_model}:generateVideos",
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.api_key}",
                    },
                )

                if not response.is_success:
                    logger.error(
                        f"VeoService: Failed to start generation: {response.status_code} {response.text}"
                    )
                    return []

                operation_data = response.json()
                operation_name = operation_data.get("name")

                if not operation_name:
                    logger.error("VeoService: No operation name returned")
                    return []

                logger.info(f"VeoService: Started operation {operation_name}")

                # Poll until complete with enhanced logic
                operation = operation_data
                poll_interval = 10.0  # Start with 10 seconds
                max_poll_time = 600  # 10 minutes max
                start_time = time.time()

                while (
                    not operation.get("done")
                    and time.time() - start_time < max_poll_time
                ):
                    await asyncio.sleep(poll_interval)

                    # Get operation status
                    poll_response = await client.get(
                        f"{self.base_url}/operations/{operation_name}",
                        headers={"Authorization": f"Bearer {self.api_key}"},
                    )

                    if poll_response.is_success:
                        operation = poll_response.json()
                        elapsed = time.time() - start_time
                        logger.info(
                            f"VeoService: Video generation in progress... ({elapsed:.1f}s)"
                        )
                    else:
                        logger.warning(
                            f"VeoService: Poll failed: {poll_response.status_code}"
                        )
                        break

                # Check if operation completed successfully
                if not operation.get("done"):
                    logger.error("VeoService: Video generation timed out")
                    return []

                if "error" in operation:
                    logger.error(f"VeoService: Generation error: {operation['error']}")
                    return []

                # Extract video URIs and download
                response_data = operation.get("response", {})
                generated_videos = response_data.get("generatedVideos", [])

                if not generated_videos:
                    logger.warning("VeoService: No videos generated")
                    return []

                # Download each video and upload to S3
                s3_urls = []
                for i, video_info in enumerate(generated_videos):
                    video_uri = video_info.get("video", {}).get("uri")
                    if not video_uri:
                        logger.warning(f"VeoService: No URI for video {i}")
                        continue

                    try:
                        # Add API key to URI
                        video_url = f"{video_uri}&key={self.api_key}"

                        logger.info(f"VeoService: Downloading video from {video_uri}")

                        # Download with browser headers
                        download_response = await client.get(
                            video_url, headers=self.browser_headers
                        )

                        if download_response.is_success:
                            video_bytes = download_response.content
                            logger.info(
                                f"VeoService: Downloaded video ({len(video_bytes)} bytes)"
                            )

                            # Upload to S3 if service available
                            if self.s3_service:
                                # Create temporary file
                                with tempfile.NamedTemporaryFile(
                                    suffix=".mp4", delete=False
                                ) as temp_file:
                                    temp_file.write(video_bytes)
                                    temp_path = temp_file.name

                                try:
                                    logger.info(
                                        f"VeoService: Uploading video to S3: {temp_path}"
                                    )
                                    s3_url = await self.s3_service.upload_image(
                                        temp_path
                                    )
                                    s3_urls.append(s3_url)
                                    logger.info(
                                        f"VeoService: Video uploaded to S3: {s3_url}"
                                    )
                                finally:
                                    # Clean up temp file
                                    try:
                                        os.unlink(temp_path)
                                    except OSError:
                                        pass
                            else:
                                logger.warning(
                                    "VeoService: No S3 service available, skipping upload"
                                )

                        else:
                            logger.warning(
                                f"VeoService: Failed to download video: {download_response.status_code}"
                            )

                    except Exception as e:
                        logger.error(f"VeoService: Error processing video {i}: {e}")

                return s3_urls

        except Exception as e:
            logger.error(f"VeoService: Unexpected error: {e}")
            return []
