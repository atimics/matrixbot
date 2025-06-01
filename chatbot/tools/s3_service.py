#!/usr/bin/env python3
"""
S3 Service

This service handles uploading images to S3 via a proxy API and returns public URLs
that can be accessed by external services like AI models.
"""

import json
import logging
import os
import uuid
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class S3Service:
    """Service for uploading images to S3 and getting public URLs."""

    def __init__(self):
        self.s3_api_endpoint = os.getenv("S3_API_ENDPOINT")
        self.s3_api_key = os.getenv("S3_API_KEY")
        self.cloudfront_domain = os.getenv("CLOUDFRONT_DOMAIN")

        if not all([self.s3_api_endpoint, self.s3_api_key]):
            raise ValueError(
                "S3_API_ENDPOINT and S3_API_KEY must be set in environment"
            )

        logger.info(f"S3Service initialized with endpoint: {self.s3_api_endpoint}")

    def is_s3_url(self, url: str) -> bool:
        """
        Check if a URL is already an S3/CloudFront URL.

        Args:
            url: The URL to check

        Returns:
            True if the URL is already an S3/CloudFront URL
        """
        if not url:
            return False

        # Check for CloudFront domain
        if self.cloudfront_domain and self.cloudfront_domain.lower() in url.lower():
            return True

        # Check for common S3 patterns
        s3_patterns = [
            ".amazonaws.com",
            "cloudfront.net",
            "s3.amazonaws.com",
            "s3-",
        ]

        return any(pattern in url.lower() for pattern in s3_patterns)

    async def ensure_s3_url(
        self,
        image_url: str,
        original_filename: Optional[str] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> str:
        """
        Ensure an image URL is hosted on S3. If it's already an S3 URL, return it as-is.
        If it's an external URL, download and upload it to S3.

        Args:
            image_url: The URL to check/convert
            original_filename: Optional original filename for the image
            http_client: Optional httpx client with authentication

        Returns:
            S3 URL (either the original if already S3, or newly uploaded)
        """
        if not image_url:
            logger.warning("ensure_s3_url called with empty image_url")
            return image_url

        # If already an S3 URL, return as-is
        if self.is_s3_url(image_url):
            logger.debug(f"URL is already S3: {image_url}")
            return image_url

        # Download and upload to S3
        logger.info(f"Converting external URL to S3: {image_url}")
        s3_url = await self.upload_image_from_url(image_url, original_filename, http_client)

        if s3_url:
            logger.info(f"Successfully converted to S3: {s3_url}")
            return s3_url
        else:
            logger.warning(f"Failed to upload to S3, returning original URL: {image_url}")
            return image_url

    async def upload_image_from_url(
        self,
        image_url: str,
        original_filename: Optional[str] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> Optional[str]:
        """
        Download an image from a URL and upload it to S3, returning the public CloudFront URL.

        Args:
            image_url: The URL to download the image from
            original_filename: Optional original filename for the image
            http_client: Optional httpx client with authentication (for Matrix URLs)

        Returns:
            Public CloudFront URL if successful, None otherwise
        """
        try:
            # Generate a unique filename
            file_extension = self._get_file_extension(image_url, original_filename)
            unique_filename = f"{uuid.uuid4()}{file_extension}"

            # Download the image
            image_data = await self._download_image(image_url, http_client)
            if not image_data:
                logger.error(f"Failed to download image from {image_url}")
                return None

            # Upload to S3
            s3_url = await self._upload_to_s3(image_data, unique_filename)
            if not s3_url:
                logger.error("Failed to upload image to S3")
                return None

            # The API returns the full CloudFront URL, so return it directly
            logger.info(f"Successfully uploaded image to S3: {s3_url}")
            return s3_url

        except Exception as e:
            logger.error(f"Error uploading image from URL {image_url}: {e}")
            return None

    async def upload_image_data(
        self, image_data: bytes, filename: Optional[str] = None
    ) -> Optional[str]:
        """
        Upload image data directly to S3, returning the public CloudFront URL.

        Args:
            image_data: Raw image bytes
            filename: Optional filename for the image

        Returns:
            Public CloudFront URL if successful, None otherwise
        """
        try:
            # Generate a unique filename
            file_extension = self._get_file_extension_from_filename(filename)
            unique_filename = f"{uuid.uuid4()}{file_extension}"

            # Upload to S3
            s3_url = await self._upload_to_s3(image_data, unique_filename)
            if not s3_url:
                logger.error("Failed to upload image to S3")
                return None

            # The API returns the full CloudFront URL, so return it directly
            logger.info(f"Successfully uploaded image data to S3: {s3_url}")
            return s3_url

        except Exception as e:
            logger.error(f"Error uploading image data: {e}")
            return None

    async def _download_image(
        self, image_url: str, http_client: Optional[httpx.AsyncClient] = None
    ) -> Optional[bytes]:
        """Download image from URL."""
        try:
            # Use provided client (with auth) or create a new one
            if http_client:
                response = await http_client.get(image_url)
            else:
                async with httpx.AsyncClient() as client:
                    response = await client.get(image_url)

            response.raise_for_status()

            # Verify it's an image
            content_type = response.headers.get("content-type", "")
            if not content_type.startswith("image/"):
                logger.warning(f"URL does not appear to be an image: {content_type}")

            return response.content

        except Exception as e:
            logger.error(f"Error downloading image from {image_url}: {e}")
            return None

    async def _upload_to_s3(self, image_data: bytes, filename: str) -> Optional[str]:
        """Upload image data to S3 via the proxy API."""
        try:
            # Convert to base64 (matching JavaScript implementation)
            import base64

            image_base64 = base64.b64encode(image_data).decode("utf-8")

            # Extract image type from filename
            image_type = filename.split(".")[-1].lower() if "." in filename else "jpg"

            # Validate image type
            valid_image_types = ["png", "jpg", "jpeg", "gif", "mp4"]
            if image_type not in valid_image_types:
                logger.warning(
                    f"Unsupported image type: {image_type}, defaulting to jpg"
                )
                image_type = "jpg"

            # Prepare JSON payload (matching JavaScript implementation)
            payload = {"image": image_base64, "imageType": image_type}

            headers = {"Content-Type": "application/json", "x-api-key": self.s3_api_key}

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.s3_api_endpoint, json=payload, headers=headers, timeout=30.0
                )

                response.raise_for_status()
                result = response.json()

                # Handle nested response structure from JavaScript
                response_data = result.get("body")
                if response_data and isinstance(response_data, str):
                    try:
                        response_data = json.loads(response_data)
                    except json.JSONDecodeError:
                        response_data = result
                else:
                    response_data = result

                # Extract URL from response
                if not response_data or not response_data.get("url"):
                    logger.error(
                        f"Invalid S3 response format - missing URL. Response: {result}"
                    )
                    return None

                logger.info(f"S3 upload successful! Image URL: {response_data['url']}")
                return response_data[
                    "url"
                ]  # Return the full CloudFront URL from the API response

        except Exception as e:
            logger.error(f"Error uploading to S3: {e}")
            return None

    def _get_file_extension(self, url: str, filename: Optional[str] = None) -> str:
        """Extract file extension from URL or filename."""
        if filename:
            return self._get_file_extension_from_filename(filename)

        # Try to extract from URL
        url_parts = url.split("/")[-1].split("?")[0]  # Remove query params
        if "." in url_parts:
            return "." + url_parts.split(".")[-1].lower()

        # Default to .jpg if can't determine
        return ".jpg"

    def _get_file_extension_from_filename(self, filename: Optional[str]) -> str:
        """Extract file extension from filename."""
        if not filename:
            return ".jpg"

        if "." in filename:
            return "." + filename.split(".")[-1].lower()

        return ".jpg"


# Create a singleton instance
s3_service = S3Service()
